"""Authenticated launch, persisted progress, and cancellation."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.api.auth import require_browser_origin
from app.api.sources import Operator
from app.models.scan import ScanJob
from app.workers.queue import ScanError, cancel, enqueue, notify

router = APIRouter(prefix="/api/v1/scans", tags=["scans"])


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: UUID
    confirmed: Literal[True]


class ScanResponse(BaseModel):
    id: UUID
    source_id: UUID
    status: str
    started_at: datetime
    finished_at: datetime | None
    attempts: int
    cancel_requested: bool
    files_discovered: int
    files_processed: int
    files_skipped: int
    files_failed: int
    findings_created: int
    inventory_limited: bool
    error_summary: str | None


@router.post(
    "",
    status_code=202,
    response_model=ScanResponse,
    dependencies=[Depends(require_browser_origin)],
)
def start_scan(payload: ScanRequest, request: Request, operator: Operator):
    try:
        job = enqueue(request.app.state.sessions, payload.source_id, operator.id)
    except ScanError as error:
        raise HTTPException(409, str(error)) from None
    notify(request.app.state.redis)
    return job


@router.get("", response_model=list[ScanResponse])
def list_scans(
    request: Request,
    operator: Operator,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    with request.app.state.sessions() as db:
        return db.scalars(
            select(ScanJob)
            .order_by(ScanJob.started_at.desc(), ScanJob.id)
            .limit(limit)
            .offset(offset)
        ).all()


@router.get("/{job_id}", response_model=ScanResponse)
def get_scan(job_id: UUID, request: Request, operator: Operator):
    with request.app.state.sessions() as db:
        job = db.get(ScanJob, job_id)
        if job is None:
            raise HTTPException(404, "Scan not found")
        return job


@router.post(
    "/{job_id}/cancel",
    response_model=ScanResponse,
    dependencies=[Depends(require_browser_origin)],
)
def cancel_scan(job_id: UUID, request: Request, operator: Operator):
    job = cancel(request.app.state.sessions, job_id, operator.id)
    if job is None:
        raise HTTPException(404, "Scan not found")
    notify(request.app.state.redis)
    return job
