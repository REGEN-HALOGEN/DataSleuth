"""Protected masked findings, review history, and related occurrences."""

from datetime import date, datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.auth import require_browser_origin
from app.api.sources import Operator
from app.models.auth import User
from app.models.scan import Finding, ScannedFile, ScanJob
from app.models.source import AuditEvent, ScanSource
from app.scanners.detection import redact_metadata

router = APIRouter(prefix="/api/v1/findings", tags=["findings"])
ReviewStatus = Literal["needs_review", "confirmed", "false_positive", "follow_up"]
Category = Literal["email", "phone_in", "pan", "aadhaar", "ifsc", "bank_account"]
Extension = Literal["txt", "log", "csv", "json", "pdf", "xlsx", "xlsm"]
REVIEW_ACTIONS = {
    f"review_{status}": status
    for status in (
        "needs_review",
        "confirmed",
        "false_positive",
        "follow_up",
    )
}


class FindingFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Category | None = None
    review_status: ReviewStatus | None = None
    source_id: UUID | None = None
    scan_id: UUID | None = None
    scan_from: date | None = None
    scan_to: date | None = None
    extension: Extension | None = None
    min_confidence: Annotated[float, Field(ge=0, le=1)] | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 25
    offset: Annotated[int, Field(ge=0, le=10_000_000)] = 0

    @model_validator(mode="after")
    def validate_scan_range(self):
        if self.scan_from and self.scan_to and self.scan_from > self.scan_to:
            raise ValueError("The start date must be on or before the end date.")
        return self


class FindingSearch(FindingFilters):
    term: Annotated[str, Field(max_length=160, pattern=r"^[^\x00]*$")] = ""


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: ReviewStatus


class FindingItem(BaseModel):
    id: UUID
    source_id: UUID
    source_name: str
    scan_id: UUID
    scan_submitted_at: datetime
    relative_path: str
    size_bytes: int | None
    category: Category
    detector_version: int
    confidence: float
    location: int
    masked_evidence: str
    review_status: ReviewStatus
    reviewed_at: datetime | None

    @field_validator("relative_path", "source_name")
    @classmethod
    def redact_detectable_metadata(cls, value: str) -> str:
        return redact_metadata(value)


class FindingPage(BaseModel):
    items: list[FindingItem]
    total: int


class ReviewEvent(BaseModel):
    status: ReviewStatus
    reviewer: str
    reviewed_at: datetime


class FindingDetail(FindingItem):
    history: list[ReviewEvent]
    related_count: int


# Explicit projection keeps digests, candidate values, and absolute paths out of responses.
FINDING_FIELDS = (
    Finding.id,
    ScanSource.id.label("source_id"),
    ScanSource.name.label("source_name"),
    ScanJob.id.label("scan_id"),
    ScanJob.started_at.label("scan_submitted_at"),
    ScannedFile.relative_path,
    ScannedFile.size_bytes,
    Finding.category,
    Finding.detector_version,
    Finding.confidence,
    Finding.location,
    Finding.masked_evidence,
    Finding.review_status,
    Finding.reviewed_at,
)


def findings_query(*columns):
    return (
        select(*columns)
        .select_from(Finding)
        .join(ScannedFile, Finding.scanned_file_id == ScannedFile.id)
        .join(ScanJob, ScannedFile.scan_job_id == ScanJob.id)
        .join(ScanSource, ScanJob.source_id == ScanSource.id)
    )


def page(db: Session, conditions: list, limit: int, offset: int) -> FindingPage:
    total = db.scalar(findings_query(func.count()).where(*conditions))
    rows = db.execute(
        findings_query(*FINDING_FIELDS)
        .where(*conditions)
        .order_by(ScanJob.started_at.desc(), Finding.id)
        .offset(offset)
        .limit(limit)
    ).mappings()
    return FindingPage(
        items=[FindingItem.model_validate(row) for row in rows], total=total
    )


def filtered_page(request: Request, filters: FindingFilters, term: str = ""):
    conditions = [
        column == value
        for column, value in (
            (Finding.category, filters.category),
            (Finding.review_status, filters.review_status),
            (ScanJob.source_id, filters.source_id),
            (ScanJob.id, filters.scan_id),
        )
        if value is not None
    ]
    scan_date = func.date(func.timezone("UTC", ScanJob.started_at))
    if filters.scan_from is not None:
        conditions.append(scan_date >= filters.scan_from)
    if filters.scan_to is not None:
        conditions.append(scan_date <= filters.scan_to)
    if filters.extension:
        conditions.append(
            func.lower(ScannedFile.relative_path).endswith(f".{filters.extension}")
        )
    if filters.min_confidence is not None:
        conditions.append(Finding.confidence >= filters.min_confidence)
    if term.strip():
        conditions.append(
            or_(
                func.lower(ScannedFile.relative_path).contains(
                    term.strip().lower(), autoescape=True
                ),
                func.lower(ScanSource.name).contains(
                    term.strip().lower(), autoescape=True
                ),
            )
        )
    with request.app.state.sessions() as db:
        return page(db, conditions, filters.limit, filters.offset)


@router.get("", response_model=FindingPage)
def list_findings(
    request: Request, operator: Operator, filters: Annotated[FindingFilters, Query()]
):
    return filtered_page(request, filters)


@router.post(
    "/search",
    response_model=FindingPage,
    dependencies=[Depends(require_browser_origin)],
)
def search_findings(payload: FindingSearch, request: Request, operator: Operator):
    return filtered_page(request, payload, payload.term)


def related_conditions(job_finding: Finding):
    return [
        Finding.fingerprint_id == job_finding.fingerprint_id,
        Finding.id != job_finding.id,
    ]


@router.get("/{finding_id}", response_model=FindingDetail)
def finding_detail(finding_id: UUID, request: Request, operator: Operator):
    with request.app.state.sessions() as db:
        finding = db.get(Finding, finding_id)
        if finding is None:
            raise HTTPException(404, "Finding not found")
        row = (
            db.execute(findings_query(*FINDING_FIELDS).where(Finding.id == finding_id))
            .mappings()
            .one()
        )
        history = db.execute(
            select(AuditEvent.action, User.username, AuditEvent.created_at)
            .join(User, User.id == AuditEvent.actor_id)
            .where(
                AuditEvent.entity_type == "finding",
                AuditEvent.entity_id == finding_id,
                AuditEvent.action.in_(REVIEW_ACTIONS),
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id)
            .limit(50)
        )
        related_count = db.scalar(
            select(func.count())
            .select_from(Finding)
            .where(*related_conditions(finding))
        )
        return FindingDetail(
            **row,
            history=[
                ReviewEvent(
                    status=REVIEW_ACTIONS[action],
                    reviewer=username,
                    reviewed_at=created_at,
                )
                for action, username, created_at in history
            ],
            related_count=related_count,
        )


@router.get("/{finding_id}/related", response_model=FindingPage)
def related_findings(
    finding_id: UUID,
    request: Request,
    operator: Operator,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0, le=10_000_000)] = 0,
):
    with request.app.state.sessions() as db:
        finding = db.get(Finding, finding_id)
        if finding is None:
            raise HTTPException(404, "Finding not found")
        return page(db, related_conditions(finding), limit, offset)


@router.patch(
    "/{finding_id}/review",
    response_model=FindingItem,
    dependencies=[Depends(require_browser_origin)],
)
def review_finding(
    finding_id: UUID, payload: ReviewRequest, request: Request, operator: Operator
):
    with request.app.state.sessions.begin() as db:
        finding = db.get(Finding, finding_id, with_for_update=True)
        if finding is None:
            raise HTTPException(404, "Finding not found")
        if finding.review_status != payload.status:
            now = datetime.now(timezone.utc)
            finding.review_status = payload.status
            finding.reviewed_by = operator.id
            finding.reviewed_at = now
            db.add(
                AuditEvent(
                    actor_id=operator.id,
                    entity_type="finding",
                    entity_id=finding.id,
                    action=f"review_{payload.status}",
                    created_at=now,
                )
            )
            db.flush()
        return (
            db.execute(findings_query(*FINDING_FIELDS).where(Finding.id == finding_id))
            .mappings()
            .one()
        )
