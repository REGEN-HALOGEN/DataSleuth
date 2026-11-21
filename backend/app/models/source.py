"""Operator-configured local scan sources."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.auth import Base
from app.models.organisation import Owned


class ScanSource(Owned, Base):
    __tablename__ = "scan_sources"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    __table_args__ = (
        UniqueConstraint("organisation_id", "id"),
        UniqueConstraint("organisation_id", "configured_path"),
        CheckConstraint(
            "(configured_path IS NOT NULL AND upload_state IS NULL AND storage_namespace IS NULL AND extension IS NULL AND size_bytes IS NULL AND content_digest IS NULL AND expires_at IS NULL) OR "
            "(configured_path IS NULL AND upload_state IS NOT NULL AND upload_state IN ('pending','ready','deleting','deleted') AND storage_namespace IS NOT NULL AND extension IS NOT NULL AND size_bytes IS NOT NULL AND size_bytes > 0 AND expires_at IS NOT NULL AND (upload_state = 'ready' OR NOT enabled) AND (upload_state <> 'ready' OR content_digest IS NOT NULL))",
            name="ck_scan_source_storage",
        ),
        Index(
            "ix_scan_source_retention",
            "storage_namespace",
            "upload_state",
            "expires_at",
        ),
    )
    name: Mapped[str] = mapped_column(String(128))
    configured_path: Mapped[str | None] = mapped_column(Text)
    upload_state: Mapped[str | None] = mapped_column(String(12))
    storage_namespace: Mapped[str | None] = mapped_column(String(64))
    extension: Mapped[str | None] = mapped_column(String(5))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    content_digest: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def can_scan(self, namespace: str | None, local_access: bool) -> bool:
        if not self.enabled:
            return False
        if self.configured_path is not None:
            return local_access
        return self.document_ready(namespace)

    def document_ready(self, namespace: str | None) -> bool:
        return (
            namespace is not None
            and self.storage_namespace == namespace
            and self.upload_state == "ready"
            and self.expires_at > datetime.now(timezone.utc)
        )


class AuditEvent(Owned, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[UUID] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
