"""Exercise the documented demo against a disposable database and real worker."""

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select

from app.core.auth import COOKIE_NAME, new_token, token_digest
from app.main import app
from app.models.auth import BrowserSession, User
from app.models.scan import ScannedFile

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = {"Origin": "http://127.0.0.1:5173"}
SOURCE_API = "/api/v1/sources"
SCAN_API = "/api/v1/scans"
FINDINGS_API = "/api/v1/findings"
REPORT_API = "/api/v1/reports/findings"
MAX_FILE_BYTES = 64 * 1024
DEMO_IDENTIFIERS = ("inventory-demo@example.invalid", "ZZZPZ0000Z")


def file_metadata(folder):
    return {
        file.name: (file.stat().st_size, file.stat().st_mtime_ns)
        for file in folder.iterdir()
    }


@pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="WSL/Linux scanner")
def test_synthetic_scan_review_export_and_restart(services, tmp_path, monkeypatch):
    folder = tmp_path / "demo"
    seed = [
        sys.executable,
        str(ROOT / "scripts/seed_demo.py"),
        str(folder),
        "--max-file-size-bytes",
        str(MAX_FILE_BYTES),
    ]
    subprocess.run(seed, check=True, capture_output=True, timeout=15)
    baseline = file_metadata(folder)
    assert subprocess.run(seed, capture_output=True, timeout=15).returncode == 1
    assert file_metadata(folder) == baseline
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", json.dumps([str(folder)]))
    monkeypatch.setenv("MAX_FILE_SIZE_BYTES", str(MAX_FILE_BYTES))

    token = new_token()
    with TestClient(app) as client:
        with app.state.sessions.begin() as db:
            user = User(
                username=f"demo-{uuid4().hex}", role="analyst", password_hash="unused"
            )
            db.add(user)
            db.flush()
            username = user.username
            db.add(
                BrowserSession(
                    user_id=user.id,
                    token_digest=token_digest(token),
                    expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                )
            )
        client.cookies.set(COOKIE_NAME, token)
        source = client.post(
            SOURCE_API,
            headers=ORIGIN,
            json={"name": "Demo data", "configured_path": str(folder)},
        )
        assert source.status_code == 201
        launch = client.post(
            SCAN_API,
            headers=ORIGIN,
            json={"source_id": source.json()["id"], "confirmed": True},
        )
        assert launch.status_code == 202 and launch.json()["status"] == "queued"
        job_url = f"{SCAN_API}/{launch.json()['id']}"
        worker = subprocess.Popen(
            [sys.executable, "-m", "app.workers.scan"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                result = client.get(job_url).json()
                if result["status"] not in {"queued", "running"}:
                    break
                assert time.monotonic() < deadline and worker.poll() is None
                time.sleep(0.1)
        finally:
            worker.terminate()
            worker.wait(timeout=8)

        unreadable = not os.access(folder / "demo-unreadable.txt", os.R_OK)
        assert result["status"] == "completed_with_errors"
        assert result["files_discovered"] == 9
        assert result["files_processed"] == (5 if unreadable else 6)
        assert result["files_skipped"] == 2
        assert result["files_failed"] == (2 if unreadable else 1)
        assert result["findings_created"] == 6
        with app.state.sessions() as db:
            files = dict(
                db.execute(
                    select(ScannedFile.relative_path, ScannedFile.parse_status).where(
                        ScannedFile.scan_job_id == result["id"]
                    )
                ).all()
            )
            assert files["demo-malformed.json"] == "malformed"
            assert files["demo-unsupported.bin"] == "unsupported"
            assert files["demo-oversized.log"] == "too_large"
            if unreadable:
                assert files["demo-unreadable.txt"] == "unreadable"
        assert file_metadata(folder) == baseline

        filtered = client.get(
            FINDINGS_API,
            params={
                "scan_id": result["id"],
                "category": "email",
                "min_confidence": 0.9,
            },
        ).json()
        assert filtered["total"] == 5
        email_id = filtered["items"][0]["id"]
        related = client.get(f"{FINDINGS_API}/{email_id}/related").json()
        assert related["total"] == 4
        assert len({row["relative_path"] for row in related["items"]}) == 4
        pan = client.get(
            FINDINGS_API, params={"scan_id": result["id"], "category": "pan"}
        ).json()
        assert pan["total"] == 1
        pan_id = pan["items"][0]["id"]
        for identifier, status in ((email_id, "confirmed"), (pan_id, "false_positive")):
            review = client.patch(
                f"{FINDINGS_API}/{identifier}/review",
                headers=ORIGIN,
                json={"status": status},
            )
            assert review.json()["review_status"] == status

        for extension in ("csv", "json"):
            report = client.post(
                f"{REPORT_API}.{extension}",
                headers=ORIGIN,
                json={"scan_id": result["id"]},
            )
            assert report.status_code == 200
            assert "[redacted]" in report.text
            assert all(value not in report.text for value in DEMO_IDENTIFIERS)
            if extension == "json":
                assert report.json()["row_count"] == 6
            else:
                assert len(list(csv.DictReader(StringIO(report.text)))) == 7

    # A new application lifecycle reconnects to the same persisted database.
    with TestClient(app) as restarted:
        restarted.cookies.set(COOKIE_NAME, token)
        assert restarted.get(job_url).json() == result
        for identifier, status in ((email_id, "confirmed"), (pan_id, "false_positive")):
            detail = restarted.get(f"{FINDINGS_API}/{identifier}").json()
            assert detail["masked_evidence"] == "[redacted]"
            assert detail["review_status"] == status
            assert detail["history"][0]["reviewer"] == username
