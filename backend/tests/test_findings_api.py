"""Verify review and related occurrences without exposing source values."""

import csv
from io import StringIO
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.manage_users import create_member
from app.models.organisation import LOCAL_ORGANISATION
from app.core.auth import COOKIE_NAME, new_token, token_digest
from app.main import app
from app.models.auth import BrowserSession
from app.models.scan import DataFingerprint, Finding, ScannedFile, ScanJob
from app.models.source import AuditEvent, ScanSource

PREFIX = "/api/v1/findings"
ORIGIN = {"Origin": "http://127.0.0.1:5173"}


def test_filtered_masked_findings_review_and_exports(services, monkeypatch):
    with TestClient(app) as client:
        with app.state.sessions.begin() as db:
            user = create_member(
                db,
                organisation_id=LOCAL_ORGANISATION,
                username=f"analyst-{uuid4().hex}",
                role="analyst",
                password_hash="unused",
            )
            viewer = create_member(
                db,
                organisation_id=LOCAL_ORGANISATION,
                username=f"viewer-{uuid4().hex}",
                role="viewer",
                password_hash="unused",
            )
            source = ScanSource(
                organisation_id=LOCAL_ORGANISATION,
                name="Synthetic inventory",
                configured_path=f"/private-fixture/{uuid4().hex}",
            )
            fingerprint = DataFingerprint(
                organisation_id=LOCAL_ORGANISATION,
                category="email",
                key_version=1,
                digest=uuid4().hex * 2,
            )
            db.add_all([user, viewer, source, fingerprint])
            db.flush()
            tokens = {}
            for role, account in (("analyst", user), ("viewer", viewer)):
                token = new_token()
                tokens[role] = token
                db.add(
                    BrowserSession(
                        organisation_id=LOCAL_ORGANISATION,
                        user_id=account.id,
                        token_digest=token_digest(token),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                    )
                )
            job = ScanJob(
                organisation_id=LOCAL_ORGANISATION,
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
                    organisation_id=LOCAL_ORGANISATION,
                    scan_job_id=job.id,
                    relative_path=filename,
                    parse_status="parsed",
                )
                db.add(file)
                db.flush()
                finding = Finding(
                    organisation_id=LOCAL_ORGANISATION,
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
        report_path = "/api/v1/reports/findings"
        filters = {"scan_id": str(job.id), "review_status": "needs_review"}
        assert client.post(f"{report_path}.json", json=filters).status_code == 403
        json_report = client.post(f"{report_path}.json", headers=ORIGIN, json=filters)
        assert json_report.status_code == 200
        document = json_report.json()
        assert document["scope"] == "scan"
        assert document["filters"] == filters
        assert document["scan_references"] == [str(job.id)]
        assert document["row_count"] == 2
        assert {item["masked_evidence"] for item in document["findings"]} == {
            "[redacted]"
        }
        csv_report = client.post(f"{report_path}.csv", headers=ORIGIN, json=filters)
        assert csv_report.status_code == 200
        assert "attachment" in csv_report.headers["content-disposition"]
        assert csv_report.headers["cache-control"] == "no-store"
        rows = list(csv.DictReader(StringIO(csv_report.text)))
        assert [row["record_type"] for row in rows] == ["report", "finding", "finding"]
        assert rows[0]["row_count"] == "2"
        for response in (json_report, csv_report):
            for private_value in (
                fingerprint.digest,
                source.configured_path,
                "fixture-copy@example.invalid",
                "fixture_%_one",
            ):
                assert private_value not in response.text
        empty = client.post(
            f"{report_path}.csv", headers=ORIGIN, json=filters | {"category": "ifsc"}
        )
        assert list(csv.DictReader(StringIO(empty.text)))[0]["row_count"] == "0"
        from app.api import reports

        with monkeypatch.context() as patch:
            patch.setattr(reports, "MAX_ROWS", 1)
            assert (
                client.post(
                    f"{report_path}.json", headers=ORIGIN, json=filters
                ).status_code
                == 422
            )
        with app.state.sessions() as db:
            audits = db.scalars(
                select(AuditEvent).where(
                    AuditEvent.actor_id == user.id,
                    AuditEvent.entity_type == "finding_report",
                )
            ).all()
            assert sorted(event.action for event in audits) == [
                "export_csv",
                "export_csv",
                "export_json",
            ]

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
