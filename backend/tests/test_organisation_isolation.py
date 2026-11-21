"""Exercise tenant boundaries through the real session, queue, scanner and DB."""

import csv
from io import StringIO
import json
import os
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.auth import password_hasher
from app.core.config import load_config
from app.main import app
from app.manage_users import create_member
from app.models.organisation import Membership, Organisation
from app.models.scan import DataFingerprint, Finding, ScanJob
from app.models.source import AuditEvent
from app.scanners import pipeline
from app.workers.queue import claim_next

PREFIX = "/api/v1"
HEADERS = {"Origin": "http://127.0.0.1:5173"}
PASSWORD = "synthetic tenant test passphrase"


def login(client, user, org):
    return client.post(
        f"{PREFIX}/auth/login",
        json={
            "username": user.username,
            "password": PASSWORD,
            "organisation_id": str(org),
        },
        headers=HEADERS,
    )


@pytest.fixture
def tenants(services, tmp_path, monkeypatch):
    orgs = [
        Organisation(id=uuid4(), name=label) for label in ("Synthetic A", "Synthetic B")
    ]
    roots = {
        org.id: tmp_path / suffix for org, suffix in zip(orgs, ("a", "b"), strict=True)
    }
    for root in roots.values():
        root.mkdir()
        (root / "synthetic.txt").write_text(
            "same@example.invalid\nsame@example.invalid"
        )
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", "[]")
    monkeypatch.setenv(
        "ORGANISATION_SCAN_ROOTS",
        json.dumps({str(k): [str(v)] for k, v in roots.items()}),
    )
    a, b = roots
    with TestClient(app) as client:
        with app.state.sessions.begin() as db:
            db.add_all(orgs)
            db.flush()
            hashed = password_hasher.hash(PASSWORD)
            two_roles = create_member(
                db,
                username=f"shared-{uuid4().hex}",
                password_hash=hashed,
                role="admin",
                organisation_id=a,
            )
            private = create_member(
                db,
                username=f"private-{uuid4().hex}",
                password_hash=hashed,
                role="analyst",
                organisation_id=b,
            )
            db.add(Membership(user_id=two_roles.id, organisation_id=b, role="viewer"))
        yield client, roots, two_roles, private


def register(client, root):
    return client.post(
        f"{PREFIX}/sources",
        headers=HEADERS,
        json={"name": "Synthetic", "configured_path": str(root)},
    )


def scan(client, source_id, org):
    launch = client.post(
        f"{PREFIX}/scans",
        headers=HEADERS,
        json={"source_id": source_id, "confirmed": True},
    )
    assert launch.status_code == 202
    job_id = UUID(launch.json()["id"])
    cfg = load_config()
    claim = claim_next(
        app.state.sessions,
        pipeline.lease_duration(cfg),
        job_id=job_id,
        organisation_ids=(org,),
    )
    assert claim is not None
    pipeline.run_claim(app.state.sessions, cfg, claim)
    assert client.get(f"{PREFIX}/scans/{job_id}").json()["findings_created"] == 2
    return str(job_id)


@pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="WSL/Linux scanner")
def test_isolation_through_scan_review_export_and_auth(tenants):
    client, roots, shared, private = tenants
    a, b = roots
    assert login(client, private, a).status_code == 401
    assert login(client, private, b).status_code == 200
    foreign = register(client, roots[b]).json()["id"]
    foreign_job = scan(client, foreign, b)
    foreign_finding = client.get(f"{PREFIX}/findings").json()["items"][0]["id"]
    with app.state.sessions() as db:
        foreign_digest = db.scalar(
            select(DataFingerprint.digest).where(DataFingerprint.organisation_id == b)
        )

    assert login(client, shared, b).json()["role"] == "viewer"
    assert client.get(f"{PREFIX}/sources").status_code == 403
    assert login(client, shared, a).json()["role"] == "admin"
    assert [x["id"] for x in client.get(f"{PREFIX}/auth/users").json()] == [
        str(shared.id)
    ]
    assert (
        client.get(
            f"{PREFIX}/sources", headers={"X-DataSleuth-Organisation": str(b)}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{PREFIX}/auth/logout",
            headers={**HEADERS, "X-DataSleuth-Organisation": str(b)},
        ).status_code
        == 409
    )
    assert register(client, roots[b]).status_code == 422
    source = register(client, roots[a]).json()["id"]
    job = scan(client, source, a)
    findings = client.get(f"{PREFIX}/findings").json()
    assert findings["total"] == 2 and {x["scan_id"] for x in findings["items"]} == {job}
    own = findings["items"][0]["id"]
    assert client.get(f"{PREFIX}/findings/{own}").json()["related_count"] == 1
    assert client.get(f"{PREFIX}/findings/{own}/related").json()["total"] == 1
    for url in (
        f"sources/{foreign}",
        f"scans/{foreign_job}",
        f"findings/{foreign_finding}",
        f"findings/{foreign_finding}/related",
    ):
        assert client.get(f"{PREFIX}/{url}").status_code == 404
    assert (
        client.patch(
            f"{PREFIX}/sources/{foreign}", headers=HEADERS, json={"enabled": False}
        ).status_code
        == 404
    )
    assert (
        client.post(f"{PREFIX}/scans/{foreign_job}/cancel", headers=HEADERS).status_code
        == 404
    )
    assert (
        client.post(
            f"{PREFIX}/scans",
            headers=HEADERS,
            json={"confirmed": True, "source_id": foreign},
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{PREFIX}/findings/{foreign_finding}/review",
            headers=HEADERS,
            json={"status": "confirmed"},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"{PREFIX}/findings/{own}/review",
            headers=HEADERS,
            json={"status": "confirmed"},
        ).status_code
        == 200
    )
    assert [x["id"] for x in client.get(f"{PREFIX}/sources").json()] == [source]
    assert [x["id"] for x in client.get(f"{PREFIX}/scans").json()] == [job]
    assert client.get(f"{PREFIX}/overview").json()["findings_awaiting_review"] == 1
    assert (
        client.post(
            f"{PREFIX}/findings/search", json={"scan_id": foreign_job}, headers=HEADERS
        ).json()["total"]
        == 0
    )
    for fmt in ("json", "csv"):
        url = f"{PREFIX}/reports/findings.{fmt}"
        report = client.post(url, headers=HEADERS, json={})
        if fmt == "json":
            assert report.json()["scan_references"] == [job]
        else:
            rows = list(csv.DictReader(StringIO(report.text)))
            assert [row["scan_id"] for row in rows[1:]] == [job, job]
        empty = client.post(url, json={"source_id": foreign}, headers=HEADERS)
        assert empty.status_code == 200 and foreign_finding not in empty.text
    with app.state.sessions.begin() as db:
        own_fp = db.scalar(
            select(DataFingerprint).where(DataFingerprint.organisation_id == a)
        )
        assert own_fp.digest != foreign_digest
        assert set(
            db.scalars(
                select(AuditEvent.organisation_id).where(
                    AuditEvent.actor_id == shared.id
                )
            )
        ) == {a}
        with pytest.raises(IntegrityError), db.begin_nested():
            db.get(Finding, UUID(foreign_finding)).fingerprint_id = own_fp.id
            db.flush()
        db.delete(db.get(Membership, (a, shared.id)))
    assert client.get(f"{PREFIX}/auth/me").status_code == 401
    assert login(client, shared, b).json()["role"] == "viewer"


@pytest.mark.skipif(os.open not in os.supports_dir_fd, reason="WSL/Linux scanner")
def test_worker_rechecks_membership_before_committing(tenants, monkeypatch):
    client, roots, shared, _ = tenants
    a, b = roots
    assert login(client, shared, a).status_code == 200
    source = register(client, roots[a]).json()["id"]
    job = client.post(
        f"{PREFIX}/scans",
        headers=HEADERS,
        json={"confirmed": True, "source_id": source},
    ).json()["id"]
    cfg = load_config()
    duration = pipeline.lease_duration(cfg)
    assert (
        claim_next(
            app.state.sessions, duration, organisation_ids=(b,), job_id=UUID(job)
        )
        is None
    )
    claim = claim_next(
        app.state.sessions, duration, organisation_ids=(a,), job_id=UUID(job)
    )
    original = pipeline.process_file

    def revoke(*args):
        result = original(*args)
        with app.state.sessions.begin() as db:
            db.get(Membership, (a, shared.id)).role = "viewer"
        return result

    monkeypatch.setattr(pipeline, "process_file", revoke)
    pipeline.run_claim(app.state.sessions, cfg, claim)
    with app.state.sessions() as db:
        stored = db.get(ScanJob, UUID(job))
        assert (stored.status, stored.findings_created, stored.files_processed) == (
            "failed",
            0,
            0,
        )
    assert client.get(f"{PREFIX}/scans").status_code == 403


def test_console_membership_lifecycle(tenants, monkeypatch, capsys):
    from app.manage_organisations import main

    client, _, shared, _ = tenants

    def manage(*args):
        monkeypatch.setattr("sys.argv", ["manage_organisations", *args])
        main()
        return capsys.readouterr().out

    org = UUID(manage("create", "Synthetic CLI").split()[-1])
    manage("grant", str(org), shared.username, "analyst")
    assert login(client, shared, org).json()["role"] == "analyst"
    manage("grant", str(org), shared.username, "viewer")
    assert client.get(f"{PREFIX}/scans").status_code == 403
    manage("revoke", str(org), shared.username)
    assert client.get(f"{PREFIX}/auth/me").status_code == 401
