"""Reserve, stream and retire private, immutable single-document sources."""

import asyncio
from datetime import datetime, timedelta, timezone
from tempfile import TemporaryFile
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from starlette.concurrency import run_in_threadpool

from app.api.auth import require_browser_origin
from app.api.sources import Operator, SourceName, SourceResponse, get_source
from app.models.organisation import Organisation, operator_membership
from app.models.source import AuditEvent, ScanSource
from app.scanners.readers import ReadFailure, parse_input
from app.storage.retention import active_scan
from app.storage.supabase import MEDIA_TYPES, StorageUnavailable

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])
origin = [Depends(require_browser_origin)]


class Reservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: SourceName
    extension: str = Field(max_length=5)
    size_bytes: int = Field(gt=0, strict=True)


def bucket_for(request):
    bucket = request.app.state.bucket
    if bucket is None:
        raise HTTPException(503, "Private uploads are unavailable.")
    return bucket


def audit(db, source, actor, action):
    db.add(
        AuditEvent(
            organisation_id=source.organisation_id,
            actor_id=actor.id,
            entity_type="scan_source",
            entity_id=source.id,
            action=action,
        )
    )


@router.get("/capabilities")
def capabilities(request: Request, operator: Operator):
    return {
        "enabled": request.app.state.bucket is not None,
        "max_bytes": request.app.state.upload_limit,
        "media_types": MEDIA_TYPES,
    }


@router.post("", status_code=201, response_model=SourceResponse, dependencies=origin)
def reserve(payload: Reservation, request: Request, operator: Operator):
    bucket = bucket_for(request)
    if (
        payload.extension not in MEDIA_TYPES
        or payload.size_bytes > request.app.state.upload_limit
    ):
        raise HTTPException(422, "Unsupported file type or size.")
    with request.app.state.sessions.begin() as db:
        # Serialize quota reservations for one organisation, including pending uploads.
        db.get(Organisation, operator.organisation_id, with_for_update=True)
        count, size = db.execute(
            select(
                func.count(), func.coalesce(func.sum(ScanSource.size_bytes), 0)
            ).where(
                ScanSource.organisation_id == operator.organisation_id,
                ScanSource.upload_state.in_(("ready", "pending", "deleting")),
            )
        ).one()
        if count >= 1024 or size + payload.size_bytes > bucket.quota_bytes:
            raise HTTPException(409, "Organisation upload quota exceeded.")
        source = ScanSource(
            organisation_id=operator.organisation_id,
            name=payload.name,
            enabled=False,
            upload_state="pending",
            extension=payload.extension,
            size_bytes=payload.size_bytes,
            storage_namespace=bucket.namespace,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        db.add(source)
        db.flush()
        audit(db, source, operator, "upload_reserved")
        return source


def pending_source(db, source_id, operator, bucket, *, lock=False):
    source = get_source(db, source_id, operator.organisation_id, lock=lock)
    if (
        source.storage_namespace != bucket.namespace
        or source.configured_path is not None
    ):
        raise HTTPException(404, "Document not found.")
    if source.upload_state != "pending" or source.expires_at <= datetime.now(
        timezone.utc
    ):
        raise HTTPException(409, "Upload reservation is no longer pending.")
    return source


def upload_metadata(sessions, source_id, operator, bucket):
    with sessions() as db:
        source = pending_source(db, source_id, operator, bucket)
        return source.size_bytes, source.extension


def publish(
    sessions, bucket, source_id, operator, handle, digest, extension, size, timeout
):
    handle.seek(0)
    try:
        parse_input(handle, extension, size, timeout, validate_only=True)
    except ReadFailure:
        raise HTTPException(
            422, "Document content does not match an accepted format."
        ) from None
    handle.seek(0)
    with sessions.begin() as db:
        if operator_membership(db, operator.id, operator.organisation_id) is None:
            raise HTTPException(403, "Operator access is required.")
        source = pending_source(db, source_id, operator, bucket, lock=True)
        try:
            bucket.upload(operator.organisation_id, source_id, extension, size, handle)
        except StorageUnavailable:
            # The provider may have received the bytes even when its response was lost.
            source.upload_state = "deleting"
            source.expires_at = datetime.now(timezone.utc) + timedelta(minutes=2)
        else:
            source.upload_state = "ready"
            source.content_digest = digest
            source.enabled = True
            source.expires_at = datetime.now(timezone.utc) + timedelta(
                hours=bucket.retention_hours
            )
            audit(db, source, operator, "uploaded")
            db.flush()
            db.refresh(source)
            return source
    raise HTTPException(503, "Upload could not be confirmed. Register a new document.")


@router.put("/{source_id}/content", response_model=SourceResponse, dependencies=origin)
async def upload(source_id: UUID, request: Request, operator: Operator):
    bucket = bucket_for(request)
    sessions = request.app.state.sessions
    size, extension = await run_in_threadpool(
        upload_metadata, sessions, source_id, operator, bucket
    )
    content_type = (
        request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    )
    if (
        content_type != MEDIA_TYPES[extension]
        or request.headers.get("content-encoding", "identity") != "identity"
    ):
        raise HTTPException(415, "Incorrect document media type.")
    length = request.headers.get("content-length")
    if (
        size > request.app.state.upload_limit
        or length is not None
        and length != str(size)
    ):
        raise HTTPException(413, "Incorrect upload size.")
    if not request.app.state.upload_slots.acquire(blocking=False):
        raise HTTPException(429, "Upload capacity is busy.")
    try:
        with TemporaryFile() as scratch:
            total = 0
            digest = bucket.checksum(operator.organisation_id, source_id)
            async with asyncio.timeout(45):
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > size:
                        raise HTTPException(413, "Upload exceeds reserved size.")
                    digest.update(chunk)
                    await run_in_threadpool(scratch.write, chunk)
            if total != size:
                raise HTTPException(422, "Incomplete upload.")
            return await run_in_threadpool(
                publish,
                sessions,
                bucket,
                source_id,
                operator,
                scratch,
                digest.hexdigest(),
                extension,
                size,
                request.app.state.parser_timeout,
            )
    except TimeoutError:
        raise HTTPException(408, "Upload timed out.") from None
    finally:
        request.app.state.upload_slots.release()


@router.delete(
    "/{source_id}", status_code=202, response_model=SourceResponse, dependencies=origin
)
def remove(source_id: UUID, request: Request, operator: Operator):
    bucket = bucket_for(request)
    with request.app.state.sessions.begin() as db:
        source = get_source(db, source_id, operator.organisation_id, lock=True)
        if source.storage_namespace != bucket.namespace:
            raise HTTPException(404, "Document not found.")
        if source.upload_state in ("deleting", "deleted"):
            return source
        if db.scalar(select(active_scan(source.id, source.organisation_id))):
            raise HTTPException(409, "Finish or cancel the active scan first.")
        source.upload_state = "deleting"
        source.enabled = False
        source.expires_at = datetime.now(timezone.utc)
        audit(db, source, operator, "deletion_requested")
        db.flush()
        db.refresh(source)
        return source
