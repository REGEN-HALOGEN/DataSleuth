"""Reconcile durable deletion requests and expire abandoned or retained bytes."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.scan import ScanJob
from app.models.source import ScanSource
from app.storage.supabase import PrivateBucket, StorageUnavailable
from app.workers.queue import ACTIVE_STATUSES


def active_scan(source_id, organisation_id):
    return (
        select(ScanJob.id)
        .where(
            ScanJob.source_id == source_id,
            ScanJob.organisation_id == organisation_id,
            ScanJob.status.in_(ACTIVE_STATUSES),
        )
        .exists()
    )


def purge_due(sessions, bucket: PrivateBucket, *, batch=8):
    for _ in range(batch):
        now = datetime.now(timezone.utc)
        with sessions.begin() as db:
            source = db.scalar(
                select(ScanSource)
                .where(
                    ScanSource.storage_namespace == bucket.namespace,
                    ScanSource.upload_state.in_(("pending", "ready", "deleting")),
                    ScanSource.expires_at <= now,
                    ~active_scan(ScanSource.id, ScanSource.organisation_id),
                )
                .order_by(ScanSource.expires_at, ScanSource.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if source is None:
                return
            source.enabled = False
            source.upload_state = "deleting"
            try:
                bucket.delete(source.organisation_id, source.id)
            except StorageUnavailable:
                source.expires_at = now + timedelta(minutes=1)
            else:
                source.upload_state = "deleted"
                source.content_digest = None
