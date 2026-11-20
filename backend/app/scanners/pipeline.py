"""Run a confirmed local scan and persist metadata and masked occurrences."""

from datetime import timedelta
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.auth import User
from app.models.scan import DataFingerprint, Finding, ScannedFile
from app.models.source import ScanSource
from app.scanners.detection import Candidate, DetectionLimit, detect
from app.scanners.discovery import InventoryEntry, SourcePathError, discover
from app.scanners.readers import ReadFailure, extract_text
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
    db, scanned_file: ScannedFile, candidates: list[Candidate], key_version: int
) -> None:
    fingerprints = {}
    # Acquire matching fingerprint keys in a stable order across concurrent scans.
    for category, fingerprint in sorted(
        {(c.category, c.fingerprint) for c in candidates}
    ):
        fields = {
            "category": category,
            "key_version": key_version,
            "digest": fingerprint,
        }
        db.execute(
            insert(DataFingerprint)
            .values(**fields)
            .on_conflict_do_nothing(
                index_elements=["category", "key_version", "digest"]
            )
        )
        fingerprints[category, fingerprint] = db.scalar(
            select(DataFingerprint.id).filter_by(**fields)
        )
    db.add_all(
        [
            Finding(
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
    entry: InventoryEntry, path: str, roots: tuple[Path, ...], config: dict[str, str]
):
    if entry.status != "eligible":
        return entry.status, []
    try:
        text = extract_text(
            path,
            roots,
            entry.relative_path,
            max_file_size=int(config["MAX_FILE_SIZE_BYTES"]),
            timeout=int(config["MAX_PROCESSING_SECONDS_PER_FILE"]),
        )
        return "parsed", detect(text, config["HMAC_KEY"].encode("utf-8"))
    except ReadFailure as error:
        return str(error), []
    except DetectionLimit:
        return "finding_limit", []


def lease_duration(config: dict[str, str]) -> timedelta:
    return timedelta(seconds=int(config["MAX_PROCESSING_SECONDS_PER_FILE"]) + 120)


def snapshot_inventory(sessions, config, claim, path, roots) -> bool:
    with sessions.begin() as db:
        job = leased_job(db, claim)
        if job is None:
            return False
        if job.inventory_ready:
            return True

    inventory = discover(
        path,
        roots,
        max_depth=int(config["MAX_SCAN_DEPTH"]),
        max_entries=int(config["MAX_FILES_PER_SCAN"]),
        max_file_size=int(config["MAX_FILE_SIZE_BYTES"]),
    )
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
            select(ScannedFile.parse_status).where(ScannedFile.scan_job_id == job.id)
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


def process_pending(sessions, config, claim, path, roots, version) -> None:
    with sessions() as db:
        pending = db.execute(
            select(ScannedFile.id, ScannedFile.relative_path, ScannedFile.size_bytes)
            .where(
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
            InventoryEntry(Path(relative), size, "eligible"), path, roots, config
        )
        with sessions.begin() as db:
            job = leased_job(db, claim)
            if job is None:
                return
            scanned_file = db.get(ScannedFile, file_id)
            scanned_file.parse_status = status
            if status == "parsed":
                job.files_processed += 1
                job.findings_created += len(candidates)
                if candidates:
                    store_findings(db, scanned_file, candidates, version)
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


def run_claim(sessions, config: dict[str, str], claim: Claim) -> None:
    roots = tuple(Path(value) for value in json.loads(config["ALLOWED_SCAN_ROOTS"]))
    version = int(config["HMAC_KEY_VERSION"])
    try:
        with sessions.begin() as db:
            job = leased_job(db, claim)
            if job is None:
                return
            source = db.get(ScanSource, job.source_id)
            user = db.get(User, job.created_by)
            if (
                source is None
                or not source.enabled
                or user is None
                or not user.active
                or user.role not in {"admin", "analyst"}
            ):
                finish(job, "failed", "source_unavailable")
                return
            if job.fingerprint_key_version not in (None, version):
                finish(job, "failed", "fingerprint_version_changed")
                return
            job.fingerprint_key_version = version
            path = source.configured_path
        if snapshot_inventory(sessions, config, claim, path, roots):
            process_pending(sessions, config, claim, path, roots, version)
    except SourcePathError:
        with sessions.begin() as db:
            job = leased_job(db, claim)
            if job is not None:
                finish(job, "failed", "source_unavailable")
    except SQLAlchemyError:
        # Leave the persisted lease intact. An available worker can retry it.
        raise ScanError("Scan storage temporarily unavailable.") from None


def execute_scan(
    sessions, config: dict[str, str], source_id: UUID, actor_id: UUID
) -> UUID:
    """Run a confirmed local scan synchronously from trusted code."""
    job = enqueue(sessions, source_id, actor_id)
    claim = claim_next(sessions, lease_duration(config), job_id=job.id)
    if claim is not None:
        run_claim(sessions, config, claim)
    return job.id
