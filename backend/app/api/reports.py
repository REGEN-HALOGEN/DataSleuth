"""Download bounded metadata-only reports with fixed masked evidence."""

import csv
from datetime import datetime, timezone
from io import StringIO
import json
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.auth import require_browser_origin
from app.api.findings import (
    Category,
    FindingScope,
    ReviewStatus,
    finding_conditions,
    findings_query,
)
from app.api.sources import Operator
from app.models.scan import Finding, ScannedFile, ScanJob
from app.models.source import AuditEvent

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
MAX_ROWS = 10_000


class ReportRow(BaseModel):
    finding_id: UUID
    source_id: UUID
    scan_id: UUID
    file_id: UUID
    scan_submitted_at: datetime
    size_bytes: int | None
    category: Category
    detector_version: int
    confidence: float
    location: int
    review_status: ReviewStatus
    reviewed_at: datetime | None
    masked_evidence: Literal["[redacted]"] = "[redacted]"


class FindingReport(BaseModel):
    report_id: UUID
    generated_at: datetime
    scope: Literal["scan", "source", "inventory"]
    filters: dict[str, str | float]
    scan_references: list[UUID]
    row_count: int
    findings: list[ReportRow]


def encode_csv(report: FindingReport) -> str:
    output = StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "record_type",
            "report_id",
            "generated_at",
            "scope",
            "filters",
            "scan_references",
            "row_count",
            *ReportRow.model_fields,
        ],
    )
    writer.writeheader()
    writer.writerow(
        {
            "record_type": "report",
            "report_id": report.report_id,
            "generated_at": report.generated_at.isoformat(),
            "scope": report.scope,
            "filters": json.dumps(report.filters, separators=(",", ":")),
            "scan_references": json.dumps(
                [str(value) for value in report.scan_references]
            ),
            "row_count": report.row_count,
        }
    )
    for row in report.findings:
        writer.writerow({"record_type": "finding", **row.model_dump(mode="json")})
    return output.getvalue()


@router.post("/findings.{format}", dependencies=[Depends(require_browser_origin)])
def export_findings(
    format: Literal["csv", "json"],
    filters: FindingScope,
    request: Request,
    operator: Operator,
):
    with request.app.state.sessions.begin() as db:
        # Select only structured fields. No arbitrary source labels, paths, or
        # review text enter the downloadable payload in either format.
        rows = (
            db.execute(
                findings_query(
                    operator.organisation_id,
                    Finding.id.label("finding_id"),
                    ScanJob.source_id,
                    ScanJob.id.label("scan_id"),
                    ScannedFile.id.label("file_id"),
                    ScanJob.started_at.label("scan_submitted_at"),
                    ScannedFile.size_bytes,
                    Finding.category,
                    Finding.detector_version,
                    Finding.confidence,
                    Finding.location,
                    Finding.review_status,
                    Finding.reviewed_at,
                )
                .where(*finding_conditions(filters))
                .order_by(ScanJob.started_at.desc(), Finding.id)
                .limit(MAX_ROWS + 1)
            )
            .mappings()
            .all()
        )
        if len(rows) > MAX_ROWS:
            raise HTTPException(
                422, "Narrow the filters to export at most 10,000 findings."
            )
        items = [ReportRow.model_validate(row) for row in rows]
        report = FindingReport(
            report_id=uuid4(),
            generated_at=datetime.now(timezone.utc),
            scope="scan"
            if filters.scan_id
            else "source"
            if filters.source_id
            else "inventory",
            filters=filters.model_dump(mode="json", exclude_none=True),
            scan_references=sorted({row.scan_id for row in items}),
            row_count=len(items),
            findings=items,
        )
        body = encode_csv(report) if format == "csv" else report.model_dump_json()
        db.add(
            AuditEvent(
                organisation_id=operator.organisation_id,
                actor_id=operator.id,
                entity_type="finding_report",
                entity_id=report.report_id,
                action=f"export_{format}",
            )
        )
    return Response(
        body,
        media_type="text/csv" if format == "csv" else "application/json",
        headers={
            "Content-Disposition": f'attachment; filename="datasleuth-findings.{format}"'
        },
    )
