"""Manage local directory sources through authenticated, privileged endpoints."""

from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import SessionAccount, require_browser_origin, require_roles
from app.models.organisation import owned_row
from app.models.source import AuditEvent, ScanSource
from app.scanners.discovery import SourcePathError, approved_directory

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])
Operator = Annotated[SessionAccount, Depends(require_roles("admin", "analyst"))]
SourceName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=128, pattern=r"^[^\x00]+$"
    ),
]
SourcePath = Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: SourceName
    configured_path: SourcePath


class SourceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: SourceName | None = None
    enabled: bool | None = None

    @model_validator(mode="after")
    def validate_update(self):
        if not self.model_fields_set or any(
            getattr(self, field) is None for field in self.model_fields_set
        ):
            raise ValueError("Supply a name or enabled state.")
        return self


class SourceResponse(BaseModel):
    id: UUID
    name: str
    configured_path: str | None
    extension: str | None
    upload_state: str | None
    size_bytes: int | None
    expires_at: datetime | None
    enabled: bool
    created_at: datetime
    updated_at: datetime


def validated_path(value: str, roots: tuple[Path, ...]) -> str:
    try:
        return str(approved_directory(value, roots))
    except SourcePathError as error:
        raise HTTPException(422, str(error)) from None


def get_source(
    db: Session, source_id: UUID, organisation_id: UUID, *, lock: bool = False
) -> ScanSource:
    source = owned_row(db, ScanSource, source_id, organisation_id, lock=lock)
    if source is None:
        raise HTTPException(404, "Scan source not found")
    return source


@router.get("", response_model=list[SourceResponse])
def list_sources(request: Request, operator: Operator):
    with request.app.state.sessions() as db:
        return db.scalars(
            select(ScanSource)
            .where(ScanSource.organisation_id == operator.organisation_id)
            .order_by(ScanSource.name, ScanSource.id)
        ).all()


@router.get("/{source_id}", response_model=SourceResponse)
def read_source(source_id: UUID, request: Request, operator: Operator):
    with request.app.state.sessions() as db:
        return get_source(db, source_id, operator.organisation_id)


@router.post(
    "",
    status_code=201,
    response_model=SourceResponse,
    dependencies=[Depends(require_browser_origin)],
)
def create_source(payload: SourceCreate, request: Request, operator: Operator):
    path = validated_path(
        payload.configured_path,
        request.app.state.scan_roots.get(operator.organisation_id, ()),
    )
    try:
        with request.app.state.sessions.begin() as db:
            source = ScanSource(
                organisation_id=operator.organisation_id,
                name=payload.name,
                configured_path=path,
            )
            db.add(source)
            db.flush()
            db.add(
                AuditEvent(
                    organisation_id=operator.organisation_id,
                    actor_id=operator.id,
                    entity_type="scan_source",
                    entity_id=source.id,
                    action="created",
                )
            )
            db.refresh(source)
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(409, "This directory is already registered") from None
    return source


@router.patch(
    "/{source_id}",
    response_model=SourceResponse,
    dependencies=[Depends(require_browser_origin)],
)
def update_source(
    source_id: UUID, payload: SourceUpdate, request: Request, operator: Operator
):
    with request.app.state.sessions.begin() as db:
        source = get_source(db, source_id, operator.organisation_id, lock=True)
        if payload.enabled is True and source.configured_path is None:
            bucket = request.app.state.bucket
            if not source.document_ready(bucket.namespace if bucket else None):
                raise HTTPException(409, "This document is unavailable.")
        elif payload.enabled is True:
            validated_path(
                source.configured_path,
                request.app.state.scan_roots.get(operator.organisation_id, ()),
            )
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(source, field, value)
        if db.is_modified(source):
            db.add(
                AuditEvent(
                    organisation_id=operator.organisation_id,
                    actor_id=operator.id,
                    entity_type="scan_source",
                    entity_id=source.id,
                    action="updated",
                )
            )
        db.flush()
        db.refresh(source)
    return source
