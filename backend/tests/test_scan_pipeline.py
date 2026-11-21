"""Connect inventory, extraction, detection, and PostgreSQL with synthetic files."""

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.manage_users import create_member
from app.models.organisation import LOCAL_ORGANISATION
from app.core.config import load_config
from app.db.session import create_database
from app.models.scan import DataFingerprint, Finding, ScanJob, ScannedFile
from app.models.source import AuditEvent, ScanSource
from app.scanners.pipeline import ScanError, execute_scan


@pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="WSL/Linux scanner")
def test_end_to_end_scan_and_versioned_findings(services, tmp_path):
    config = load_config()
    config["ALLOWED_SCAN_ROOTS"] = json.dumps([str(tmp_path)])
    config["HMAC_KEY"] = f"synthetic-scan-test-key-{uuid4().hex}"
    config["HMAC_KEY_VERSION"] = "1"
    value = "synthetic-match@example.invalid"
    (tmp_path / "one.txt").write_text(value)
    (tmp_path / "two.csv").write_text(value.upper())
    (tmp_path / "bad.json").write_text("{malformed")
    (tmp_path / "skipped.bin").write_bytes(b"0")
    engine, sessions = create_database(config["DATABASE_URL"])
    try:
        with sessions.begin() as db:
            analyst = create_member(
                db,
                organisation_id=LOCAL_ORGANISATION,
                username=f"test-{uuid4().hex}",
                role="analyst",
                password_hash="unused",
            )
            viewer = create_member(
                db,
                organisation_id=LOCAL_ORGANISATION,
                username=f"test-{uuid4().hex}",
                role="viewer",
                password_hash="unused",
            )
            source = ScanSource(
                organisation_id=LOCAL_ORGANISATION,
                name="Synthetic scan",
                configured_path=str(tmp_path),
            )
            db.add_all([analyst, viewer, source])
            db.flush()
            analyst_id, viewer_id, source_id = analyst.id, viewer.id, source.id

        with pytest.raises(ScanError, match="active administrator or analyst"):
            execute_scan(sessions, config, source_id, viewer_id)
        job_ids = (
            execute_scan(sessions, config, source_id, analyst_id),
            execute_scan(
                sessions, config | {"HMAC_KEY_VERSION": "2"}, source_id, analyst_id
            ),
        )
        with sessions() as db:
            first = db.get(ScanJob, job_ids[0])
            assert first.status == "completed_with_errors"
            assert (
                first.files_discovered,
                first.files_processed,
                first.files_skipped,
                first.files_failed,
            ) == (4, 2, 1, 1)
            assert first.findings_created == 2
            assert dict(
                db.execute(
                    select(ScannedFile.relative_path, ScannedFile.parse_status).where(
                        ScannedFile.scan_job_id == first.id
                    )
                ).all()
            ) == {
                "one.txt": "parsed",
                "two.csv": "parsed",
                "bad.json": "malformed",
                "skipped.bin": "unsupported",
            }
            results = db.execute(
                select(
                    Finding.masked_evidence,
                    DataFingerprint.key_version,
                    DataFingerprint.id,
                )
                .join(DataFingerprint, DataFingerprint.id == Finding.fingerprint_id)
                .join(ScannedFile, ScannedFile.id == Finding.scanned_file_id)
                .where(ScannedFile.scan_job_id.in_(job_ids))
            ).all()
            assert len(results) == 4
            assert {masked for masked, _, _ in results} == {"[redacted]"}
            assert (
                len(
                    {
                        fingerprint_id
                        for _, version, fingerprint_id in results
                        if version == 1
                    }
                )
                == 1
            )
            assert len({fingerprint_id for _, _, fingerprint_id in results}) == 2
            assert (
                len(
                    db.scalars(
                        select(AuditEvent).where(AuditEvent.entity_id.in_(job_ids))
                    ).all()
                )
                == 2
            )

        failed_id = execute_scan(
            sessions, config | {"ALLOWED_SCAN_ROOTS": "[]"}, source_id, analyst_id
        )
        with sessions() as db:
            failed = db.get(ScanJob, failed_id)
            assert (failed.status, failed.error_summary) == (
                "failed",
                "source_unavailable",
            )
    finally:
        engine.dispose()
