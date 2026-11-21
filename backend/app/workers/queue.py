"""Durable scan state in PostgreSQL, with bounded Redis wake-up notifications."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from redis.exceptions import RedisError
from sqlalchemy import or_, select

from app.models.organisation import LOCAL_ORGANISATION, operator_membership, owned_row
from app.models.scan import ScanJob
from app.models.source import AuditEvent, ScanSource

WAKE_KEY = "datasleuth:scan:wake"
MAX_ATTEMPTS = 3
ACTIVE_STATUSES = {"queued", "running"}


class ScanError(ValueError):
    """A sanitized reason why a scan could not be started or stored."""


@dataclass(frozen=True)
class Claim:
    organisation_id: UUID
    job_id: UUID
    token: UUID
    duration: timedelta


def notify(redis) -> None:
    try:
        with redis.pipeline() as pipe:
            pipe.lpush(WAKE_KEY, "ready").ltrim(WAKE_KEY, 0, 63).execute()
    except RedisError:
        # Jobs are already durable. The worker will poll PostgreSQL.
        return


def audit(db, job: ScanJob, actor_id: UUID, action: str) -> None:
    db.add(
        AuditEvent(
            organisation_id=job.organisation_id,
            actor_id=actor_id,
            entity_type="scan_job",
            entity_id=job.id,
            action=action,
        )
    )


def enqueue(
    sessions,
    source_id: UUID,
    actor_id: UUID,
    organisation_id: UUID,
    *,
    namespace: str | None = None,
    local_access: bool = True,
) -> ScanJob:
    with sessions.begin() as db:
        if operator_membership(db, actor_id, organisation_id) is None:
            raise ScanError("An active administrator or analyst is required.")
        source = owned_row(db, ScanSource, source_id, organisation_id, lock=True)
        if source is None or not source.can_scan(namespace, local_access):
            raise ScanError("Choose an enabled scan source.")
        active_job = db.scalar(
            select(ScanJob.id)
            .where(
                ScanJob.organisation_id == organisation_id,
                ScanJob.source_id == source_id,
                ScanJob.status.in_(ACTIVE_STATUSES),
            )
            .limit(1)
        )
        if active_job is not None:
            raise ScanError("This source already has an active scan.")
        job = ScanJob(
            organisation_id=organisation_id,
            source_id=source_id,
            created_by=actor_id,
            status="queued",
        )
        db.add(job)
        db.flush()
        audit(db, job, actor_id, "queued")
    return job


def finish(job: ScanJob, status: str, reason: str | None = None) -> None:
    job.status = status
    job.error_summary = reason
    job.finished_at = datetime.now(timezone.utc)
    job.lease_token = None
    job.lease_until = None


def claim_next(
    sessions,
    duration: timedelta,
    *,
    organisation_ids=(LOCAL_ORGANISATION,),
    job_id: UUID | None = None,
    namespace: str | None = None,
) -> Claim | None:
    with sessions.begin() as db:
        now = datetime.now(timezone.utc)
        accessible = ScanSource.configured_path.is_not(
            None
        ) & ScanSource.organisation_id.in_(organisation_ids)
        if namespace is not None:
            accessible |= ScanSource.storage_namespace == namespace
        query = (
            select(ScanJob)
            .join(ScanSource, ScanSource.id == ScanJob.source_id)
            .where(
                accessible,
                or_(
                    ScanJob.status == "queued",
                    (ScanJob.status == "running")
                    & or_(
                        ScanJob.lease_until.is_(None),
                        ScanJob.lease_until <= now,
                    ),
                ),
            )
        )
        if job_id is not None:
            query = query.where(ScanJob.id == job_id)
        job = db.scalar(
            query.order_by(ScanJob.started_at, ScanJob.id)
            .limit(1)
            .with_for_update(skip_locked=True, of=ScanJob)
        )
        if job is None:
            return None
        if job.cancel_requested:
            finish(job, "cancelled")
            return None
        if job.attempts >= MAX_ATTEMPTS:
            finish(job, "failed", "retry_limit")
            return None
        job.attempts += 1
        job.status = "running"
        job.lease_token = uuid4()
        job.lease_until = now + duration
        job.error_summary = None
        return Claim(job.organisation_id, job.id, job.lease_token, duration)


def leased_job(db, claim: Claim) -> ScanJob | None:
    job = owned_row(db, ScanJob, claim.job_id, claim.organisation_id, lock=True)
    if job is None or job.status != "running" or job.lease_token != claim.token:
        return None
    if job.cancel_requested:
        finish(job, "cancelled")
        return None
    if operator_membership(db, job.created_by, job.organisation_id) is None:
        finish(job, "failed", "source_unavailable")
        return None
    job.lease_until = datetime.now(timezone.utc) + claim.duration
    return job


def cancel(
    sessions, job_id: UUID, actor_id: UUID, organisation_id: UUID
) -> ScanJob | None:
    with sessions.begin() as db:
        if operator_membership(db, actor_id, organisation_id) is None:
            return None
        job = owned_row(db, ScanJob, job_id, organisation_id, lock=True)
        if (
            job is not None
            and job.status in ACTIVE_STATUSES
            and not job.cancel_requested
        ):
            job.cancel_requested = True
            audit(db, job, actor_id, "cancel_requested")
            if job.status == "queued":
                finish(job, "cancelled")
        return job
