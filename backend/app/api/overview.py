"""Operational overview from persisted scanner and review data."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select

from app.api.sources import Operator
from app.models.scan import Finding, ScanJob
from app.models.source import ScanSource
from app.scanners.detection import redact_metadata

router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


class RecentScan(BaseModel):
    id: UUID
    source_name: str
    started_at: datetime
    status: str
    files_processed: int
    findings_created: int

    @field_validator("source_name")
    @classmethod
    def redact_source(cls, value: str) -> str:
        return redact_metadata(value)


class CategoryCount(BaseModel):
    category: str
    count: int


class OverviewResponse(BaseModel):
    sources: int
    scans: int
    files_processed: int
    findings_awaiting_review: int
    recent_scans: list[RecentScan]
    categories: list[CategoryCount]


@router.get("", response_model=OverviewResponse)
def overview(request: Request, operator: Operator):
    with request.app.state.sessions() as db:
        sources = db.scalar(
            select(func.count())
            .select_from(ScanSource)
            .where(ScanSource.organisation_id == operator.organisation_id)
        )
        scans, files = db.execute(
            select(
                func.count(ScanJob.id),
                func.coalesce(func.sum(ScanJob.files_processed), 0),
            ).where(ScanJob.organisation_id == operator.organisation_id)
        ).one()
        needs_review = db.scalar(
            select(func.count(Finding.id)).where(
                Finding.organisation_id == operator.organisation_id,
                Finding.review_status == "needs_review",
            )
        )
        recent = db.execute(
            select(
                ScanJob.id,
                ScanSource.name.label("source_name"),
                ScanJob.started_at,
                ScanJob.status,
                ScanJob.files_processed,
                ScanJob.findings_created,
            )
            .join(ScanSource, ScanJob.source_id == ScanSource.id)
            .where(ScanJob.organisation_id == operator.organisation_id)
            .order_by(ScanJob.started_at.desc(), ScanJob.id)
            .limit(5)
        ).mappings()
        count = func.count(Finding.id)
        categories = db.execute(
            select(Finding.category, count.label("count"))
            .where(Finding.organisation_id == operator.organisation_id)
            .group_by(Finding.category)
            .order_by(count.desc(), Finding.category)
        ).mappings()
        return OverviewResponse(
            sources=sources,
            scans=scans,
            files_processed=files,
            findings_awaiting_review=needs_review,
            recent_scans=[RecentScan.model_validate(row) for row in recent],
            categories=[CategoryCount.model_validate(row) for row in categories],
        )
