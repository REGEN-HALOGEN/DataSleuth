"""Persisted scanner state and masked findings."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base


class ScanJob(Base):
    __tablename__ = "scan_jobs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("scan_sources.id"), index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    inventory_ready: Mapped[bool] = mapped_column(default=False)
    fingerprint_key_version: Mapped[int | None]
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    files_discovered: Mapped[int] = mapped_column(default=0)
    files_processed: Mapped[int] = mapped_column(default=0)
    files_skipped: Mapped[int] = mapped_column(default=0)
    files_failed: Mapped[int] = mapped_column(default=0)
    findings_created: Mapped[int] = mapped_column(default=0)
    inventory_limited: Mapped[bool] = mapped_column(default=False)
    error_summary: Mapped[str | None] = mapped_column(String(40))


class ScannedFile(Base):
    __tablename__ = "scanned_files"
    __table_args__ = (UniqueConstraint("scan_job_id", "relative_path"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scan_job_id: Mapped[UUID] = mapped_column(ForeignKey("scan_jobs.id"), index=True)
    relative_path: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    parse_status: Mapped[str] = mapped_column(String(32))


class DataFingerprint(Base):
    __tablename__ = "data_fingerprints"
    __table_args__ = (UniqueConstraint("category", "key_version", "digest"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(32))
    key_version: Mapped[int]
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scanned_file_id: Mapped[UUID] = mapped_column(
        ForeignKey("scanned_files.id"), index=True
    )
    fingerprint_id: Mapped[UUID] = mapped_column(
        ForeignKey("data_fingerprints.id"), index=True
    )
    category: Mapped[str] = mapped_column(String(32))
    detector_version: Mapped[int]
    confidence: Mapped[float]
    location: Mapped[int]
    masked_evidence: Mapped[str] = mapped_column(String(32))
