"""Verify review and related occurrences without exposing source values."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.auth import COOKIE_NAME, new_token, token_digest
from app.main import app
from app.models.auth import BrowserSession, User
from app.models.scan import DataFingerprint, Finding, ScannedFile, ScanJob
from app.models.source import ScanSource

PREFIX = "/api/v1/findings"
ORIGIN = {"Origin": "http://127.0.0.1:5173"}


def test_filtered_masked_findings_and_audited_review(services):
    with TestClient(app) as client:
        with app.state.sessions.begin() as db:
            user = User(
                username=f"analyst-{uuid4().hex}",
                role="analyst",
                password_hash="unused",
            )
            viewer = User(
                username=f"viewer-{uuid4().hex}", role="viewer", password_hash="unused"
            )
            source = ScanSource(
                name="Synthetic inventory",
                configured_path=f"/private-fixture/{uuid4().hex}",
            )
            fingerprint = DataFingerprint(
                category="email", key_version=1, digest=uuid4().hex * 2
            )
            db.add_all([user, viewer, source, fingerprint])
            db.flush()
            tokens = {}
            for account in (user, viewer):
                token = new_token()
                tokens[account.role] = token
                db.add(
                    BrowserSession(
                        user_id=account.id,
                        token_digest=token_digest(token),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                    )
                )
            job = ScanJob(
                source_id=source.id,
                created_by=user.id,
                status="completed",
                files_processed=2,
                findings_created=2,
            )
            db.add(job)
            db.flush()
            fixtures = []
            for filename in ("fixture_%_one.txt", "fixture-copy@example.invalid.csv"):
                file = ScannedFile(
                    scan_job_id=job.id, relative_path=filename, parse_status="parsed"
                )
                db.add(file)
                db.flush()
                finding = Finding(
                    scanned_file_id=file.id,
                    fingerprint_id=fingerprint.id,
                    category="email",
                    detector_version=1,
                    confidence=0.9,
                    location=1,
                    masked_evidence="[redacted]",
                )
                db.add(finding)
                fixtures.append(finding)
            db.flush()

        href = f"{PREFIX}/{fixtures[0].id}"
        assert client.get(href).status_code == 401
        client.cookies.set(COOKIE_NAME, tokens["viewer"])
        assert client.get(href).status_code == 403
        client.cookies.set(COOKIE_NAME, tokens["analyst"])
        overview = client.get("/api/v1/overview").json()
        assert overview["files_processed"] >= 2
        assert overview["findings_awaiting_review"] >= 2
        assert any(row["id"] == str(job.id) for row in overview["recent_scans"])
        assert any(
            row["category"] == "email" and row["count"] >= 2
            for row in overview["categories"]
        )
        filtered = client.get(
            PREFIX,
            params={"scan_id": str(job.id), "extension": "txt", "min_confidence": 0.9},
        )
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.headers["cache-control"] == "no-store"
        assert str(fingerprint.id) not in filtered.text
        assert fingerprint.digest not in filtered.text
        assert source.configured_path not in filtered.text
        assert (
            client.get(
                PREFIX, params={"scan_id": str(job.id), "limit": 1, "offset": 1}
            ).json()["total"]
            == 2
        )
        searched = client.post(
            f"{PREFIX}/search",
            headers=ORIGIN,
            json={"term": "%", "scan_id": str(job.id)},
        )
        assert searched.json()["total"] == 1
        day = job.started_at.date().isoformat()
        bounded = client.get(
            PREFIX, params={"scan_id": str(job.id), "scan_from": day, "scan_to": day}
        )
        assert bounded.json()["total"] == 2
        assert (
            client.get(
                PREFIX, params={"scan_from": "2026-12-02", "scan_to": "2026-12-01"}
            ).status_code
            == 422
        )
        assert client.get(href).json()["review_status"] == "needs_review"
        related = client.get(f"{href}/related").json()
        assert related["total"] == 1
        assert related["items"][0]["id"] == str(fixtures[1].id)
        assert "fixture-copy@example.invalid" not in str(related)

        assert (
            client.patch(f"{href}/review", json={"status": "confirmed"}).status_code
            == 403
        )
        assert (
            client.patch(
                f"{href}/review", headers=ORIGIN, json={"status": "invalid"}
            ).status_code
            == 422
        )
        for status in ("confirmed", "confirmed", "follow_up"):
            assert (
                client.patch(
                    f"{href}/review", headers=ORIGIN, json={"status": status}
                ).json()["review_status"]
                == status
            )
        detail = client.get(href).json()
        assert detail["review_status"] == "follow_up"
        assert [event["status"] for event in detail["history"]] == [
            "follow_up",
            "confirmed",
        ]
        assert all(event["reviewer"] == user.username for event in detail["history"])
        assert detail["related_count"] == 1
        assert (
            client.get("/api/v1/overview").json()["findings_awaiting_review"]
            == overview["findings_awaiting_review"] - 1
        )
