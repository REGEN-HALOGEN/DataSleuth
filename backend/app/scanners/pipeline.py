"""Run a confirmed local scan and persist metadata and masked occurrences."""

from datetime import timedelta
import hmac
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.organisation import LOCAL_ORGANISATION, owned_row
from app.core.config import organisation_roots
from app.models.scan import DataFingerprint, Finding, ScannedFile
from app.models.source import ScanSource
from app.scanners.detection import Candidate, DetectionLimit, detect
from app.scanners.discovery import InventoryEntry, SourcePathError
from app.scanners.readers import MAX_INPUT_BYTES, ReadFailure, parse_input
from app.storage.sources import SourceInput, source_input
from app.storage.supabase import PrivateBucket, StorageUnavailable
from app.workers.queue import Claim, ScanError, claim_next, enqueue, finish, leased_job

FILE_FAILURES = frozenset(
    {
        "changed",
        "unreadable",
        "timeout",
        "malformed",
        "parser_failed",
        "parser_unavailable",
        "finding_limit",
        "platform_unsupported",
    }
)


def store_findings(
    db,
    scanned_file: ScannedFile,
    candidates: list[Candidate],
    key_version: int,
    scheme: int,
) -> None:
    fingerprints = {}
    # Acquire matching fingerprint keys in a stable order across concurrent scans.
    for category, fingerprint in sorted(
        {(c.category, c.fingerprint) for c in candidates}
    ):
        fields = {
            "organisation_id": scanned_file.organisation_id,
            "scheme": scheme,
            "category": category,
            "key_version": key_version,
            "digest": fingerprint,
        }
        db.execute(
            insert(DataFingerprint)
            .values(**fields)
            .on_conflict_do_nothing(
                index_elements=[
                    "organisation_id",
                    "scheme",
                    "category",
                    "key_version",
                    "digest",
                ]
            )
        )
        fingerprints[category, fingerprint] = db.scalar(
            select(DataFingerprint.id).filter_by(**fields)
        )
    db.add_all(
        [
            Finding(
                organisation_id=scanned_file.organisation_id,
                scanned_file_id=scanned_file.id,
                fingerprint_id=fingerprints[candidate.category, candidate.fingerprint],
                category=candidate.category,
                detector_version=candidate.detector_version,
                confidence=candidate.confidence,
                location=candidate.location,
                masked_evidence=candidate.masked_evidence,
            )
            for candidate in candidates
        ]
    )


def process_file(
    entry: InventoryEntry,
    source: SourceInput,
    config: dict[str, str],
    fingerprint_key: bytes,
):
    if entry.status != "eligible":
        return entry.status, []
    try:
        limit = min(int(config["MAX_FILE_SIZE_BYTES"]), MAX_INPUT_BYTES)
        with source.open_input(entry, limit) as handle:
            text = parse_input(
                handle,
                entry.relative_path.suffix.lower(),
                limit,
                int(config["MAX_PROCESSING_SECONDS_PER_FILE"]),
            )
        return "parsed", detect(text, fingerprint_key)
    except ReadFailure as error:
        return str(error), []
    except DetectionLimit:
        return "finding_limit", []


def lease_duration(config: dict[str, str]) -> timedelta:
    return timedelta(seconds=int(config["MAX_PROCESSING_SECONDS_PER_FILE"]) + 120)


def snapshot_inventory(sessions, config, claim, adapter) -> bool:
    with sessions.begin() as db:
        job = leased_job(db, claim)
        if job is None:
            return False
        if job.inventory_ready:
            return True

    inventory = adapter.inventory(config)
    pending = []
    invalid_names = 0
    for entry in inventory.entries:
        relative = entry.relative_path.as_posix()
        try:
            relative.encode("utf-8")
        except UnicodeEncodeError:
            invalid_names += 1
            continue
        pending.append(
            {
                "organisation_id": claim.organisation_id,
                "scan_job_id": claim.job_id,
                "relative_path": relative,
                "size_bytes": entry.size_bytes,
                "parse_status": "pending"
                if entry.status == "eligible"
                else entry.status,
            }
        )
    with sessions.begin() as db:
        job = leased_job(db, claim)
        if job is None:
            return False
        if pending:
            db.execute(
                insert(ScannedFile).on_conflict_do_nothing(
                    index_elements=["scan_job_id", "relative_path"]
                ),
                pending,
            )
        statuses = db.scalars(
            select(ScannedFile.parse_status).where(
                ScannedFile.organisation_id == claim.organisation_id,
                ScannedFile.scan_job_id == job.id,
            )
        ).all()
        job.files_discovered = len(statuses) + invalid_names
        job.files_processed = statuses.count("parsed")
        job.files_failed = sum(status in FILE_FAILURES for status in statuses)
        job.files_skipped = (
            len(statuses)
            - job.files_processed
            - job.files_failed
            - statuses.count("pending")
            + invalid_names
        )
        job.inventory_limited = inventory.entry_limit_reached
        job.inventory_ready = True
    return True


def process_pending(
    sessions, config, claim, adapter, version, scheme, fingerprint_key
) -> None:
    with sessions() as db:
        pending = db.execute(
            select(ScannedFile.id, ScannedFile.relative_path, ScannedFile.size_bytes)
            .where(
                ScannedFile.organisation_id == claim.organisation_id,
                ScannedFile.scan_job_id == claim.job_id,
                ScannedFile.parse_status == "pending",
            )
            .order_by(ScannedFile.relative_path)
        ).all()
    for file_id, relative, size in pending:
        with sessions.begin() as db:
            if leased_job(db, claim) is None:
                return
        status, candidates = process_file(
            InventoryEntry(Path(relative), size, "eligible"),
            adapter,
            config,
            fingerprint_key,
        )
        with sessions.begin() as db:
            job = leased_job(db, claim)
            if job is None:
                return
            scanned_file = owned_row(db, ScannedFile, file_id, claim.organisation_id)
            scanned_file.parse_status = status
            if status == "parsed":
                job.files_processed += 1
                job.findings_created += len(candidates)
                if candidates:
                    store_findings(db, scanned_file, candidates, version, scheme)
            elif status in FILE_FAILURES:
                job.files_failed += 1
            else:
                job.files_skipped += 1
    with sessions.begin() as db:
        job = leased_job(db, claim)
        if job is not None:
            finish(
                job,
                "completed_with_errors"
                if job.files_failed or job.inventory_limited
                else "completed",
            )


def run_claim(
    sessions,
    config: dict[str, str],
    claim: Claim,
    *,
    roots: tuple[Path, ...] | None = None,
) -> None:
    if roots is None:
        roots = organisation_roots(config).get(claim.organisation_id, ())
    version = int(config["HMAC_KEY_VERSION"])
    try:
        with sessions.begin() as db:
            job = leased_job(db, claim)
            if job is None:
                return
            source = owned_row(db, ScanSource, job.source_id, claim.organisation_id)
            bucket = PrivateBucket.from_config(config)
            if source is None or not source.can_scan(
                bucket.namespace if bucket else None, True
            ):
                finish(job, "failed", "source_unavailable")
                return
            if job.fingerprint_key_version not in (None, version):
                finish(job, "failed", "fingerprint_version_changed")
                return
            job.fingerprint_key_version = version
            scheme = job.fingerprint_scheme
            master = config["HMAC_KEY"].encode("utf-8")
            if scheme == 2:
                fingerprint_key = hmac.digest(
                    master,
                    b"datasleuth/organisation-fingerprint/v2\0"
                    + claim.organisation_id.bytes,
                    "sha256",
                )
            elif scheme == 1 and claim.organisation_id == LOCAL_ORGANISATION:
                fingerprint_key = master
            else:
                finish(job, "failed", "fingerprint_scheme_unknown")
                return
            adapter = source_input(source, roots, bucket)
        if snapshot_inventory(sessions, config, claim, adapter):
            process_pending(
                sessions, config, claim, adapter, version, scheme, fingerprint_key
            )
    except SourcePathError:
        with sessions.begin() as db:
            job = leased_job(db, claim)
            if job is not None:
                finish(job, "failed", "source_unavailable")
    except (SQLAlchemyError, StorageUnavailable):
        # Leave the persisted lease intact. An available worker can retry it.
        raise ScanError("Scan storage temporarily unavailable.") from None


def execute_scan(
    sessions,
    config: dict[str, str],
    source_id: UUID,
    actor_id: UUID,
    organisation_id: UUID = LOCAL_ORGANISATION,
) -> UUID:
    """Run a confirmed local scan synchronously from trusted code."""
    bucket = PrivateBucket.from_config(config)
    namespace = bucket.namespace if bucket else None
    job = enqueue(sessions, source_id, actor_id, organisation_id, namespace=namespace)
    claim = claim_next(
        sessions,
        lease_duration(config),
        organisation_ids=(organisation_id,),
        namespace=namespace,
        job_id=job.id,
    )
    if claim is not None:
        run_claim(sessions, config, claim)
    return job.id
