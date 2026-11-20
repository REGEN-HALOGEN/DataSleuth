"""Run a confirmed local scan and persist metadata and masked occurrences."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError

from app.models.auth import User
from app.models.scan import DataFingerprint, Finding, ScanJob, ScannedFile
from app.models.source import AuditEvent, ScanSource
from app.scanners.detection import Candidate, DetectionLimit, detect
from app.scanners.discovery import InventoryEntry, SourcePathError, discover
from app.scanners.readers import ReadFailure, extract_text

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


class ScanError(ValueError):
    """A sanitized reason why a scan could not be started or stored."""


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


def execute_scan(
    sessions, config: dict[str, str], source_id: UUID, actor_id: UUID
) -> UUID:
    """Run an approved and explicitly confirmed source by ID from trusted code."""
    roots = tuple(Path(value) for value in json.loads(config["ALLOWED_SCAN_ROOTS"]))
    with sessions.begin() as db:
        user = db.get(User, actor_id)
        if user is None or not user.active or user.role not in {"admin", "analyst"}:
            raise ScanError("An active administrator or analyst is required.")
        source = db.get(ScanSource, source_id)
        if source is None or not source.enabled:
            raise ScanError("Choose an enabled scan source.")
        path = source.configured_path
        job = ScanJob(source_id=source.id, created_by=user.id, status="running")
        db.add(job)
        db.flush()
        job_id = job.id
        db.add(
            AuditEvent(
                actor_id=user.id,
                entity_type="scan_job",
                entity_id=job_id,
                action="started",
            )
        )

    try:
        inventory = discover(
            path,
            roots,
            max_depth=int(config["MAX_SCAN_DEPTH"]),
            max_entries=int(config["MAX_FILES_PER_SCAN"]),
            max_file_size=int(config["MAX_FILE_SIZE_BYTES"]),
        )
        with sessions.begin() as db:
            job = db.get(ScanJob, job_id)
            job.files_discovered = len(inventory.entries)
            job.inventory_limited = inventory.entry_limit_reached

        for entry in inventory.entries:
            relative = entry.relative_path.as_posix()
            if (
                not relative.encode("utf-8", errors="ignore").decode("utf-8")
                == relative
            ):
                with sessions.begin() as db:
                    db.get(ScanJob, job_id).files_skipped += 1
                continue
            status, candidates = process_file(entry, path, roots, config)
            with sessions.begin() as db:
                job = db.get(ScanJob, job_id)
                scanned_file = ScannedFile(
                    scan_job_id=job_id,
                    relative_path=relative,
                    size_bytes=entry.size_bytes,
                    parse_status=status,
                )
                db.add(scanned_file)
                if status == "parsed":
                    job.files_processed += 1
                    job.findings_created += len(candidates)
                    if candidates:
                        db.flush()
                        store_findings(
                            db,
                            scanned_file,
                            candidates,
                            int(config["HMAC_KEY_VERSION"]),
                        )
                elif status in FILE_FAILURES:
                    job.files_failed += 1
                else:
                    job.files_skipped += 1
        with sessions.begin() as db:
            job = db.get(ScanJob, job_id)
            job.status = (
                "completed_with_errors"
                if job.files_failed or job.inventory_limited
                else "completed"
            )
            job.finished_at = datetime.now(timezone.utc)
    except (SourcePathError, SQLAlchemyError) as error:
        try:
            with sessions.begin() as db:
                job = db.get(ScanJob, job_id)
                job.status = "failed"
                job.error_summary = (
                    "source_unavailable"
                    if isinstance(error, SourcePathError)
                    else "storage_unavailable"
                )
                job.finished_at = datetime.now(timezone.utc)
        except SQLAlchemyError:
            raise ScanError("Scan state could not be stored.") from None
    return job_id
