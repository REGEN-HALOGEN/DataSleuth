"""Exercise the durable queue, worker process, and cooperative cancellation."""

from datetime import datetime, timedelta, timezone
import json
import os
import subprocess
import sys
import time
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest
from redis import Redis
from sqlalchemy import select

from app.manage_users import create_member
from app.models.organisation import LOCAL_ORGANISATION
from app.core.auth import COOKIE_NAME, new_token, token_digest
from app.core.config import load_config
from app.main import app
from app.models.auth import BrowserSession
from app.models.scan import Finding, ScanJob, ScannedFile
from app.models.source import AuditEvent, ScanSource
from app.scanners import pipeline
from app.workers.queue import MAX_ATTEMPTS, WAKE_KEY, cancel, claim_next, enqueue

ORIGIN = {"Origin": "http://127.0.0.1:5173"}
PREFIX = "/api/v1/scans"
WSL_ONLY = pytest.mark.skipif(
    os.open not in os.supports_dir_fd, reason="WSL/Linux scanner"
)
DURATION = timedelta(minutes=5)


@pytest.fixture
def stack(services, tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("queue-fixture@example.invalid")
    (tmp_path / "b.txt").write_text("queue-fixture@example.invalid")
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", json.dumps([str(tmp_path)]))
    with TestClient(app) as client:
        sessions = app.state.sessions
        with sessions.begin() as db:
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
                name="Queue fixture",
                configured_path=str(tmp_path),
            )
            db.add_all([user, viewer, source])
            db.flush()
            tokens = {}
            for role, account in (("analyst", user), ("viewer", viewer)):
                token = new_token()
                db.add(
                    BrowserSession(
                        organisation_id=LOCAL_ORGANISATION,
                        user_id=account.id,
                        token_digest=token_digest(token),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                    )
                )
                tokens[role] = token
        yield client, sessions, source, user, tokens


@WSL_ONLY
def test_api_and_real_worker_process(stack):
    client, _, source, _, tokens = stack
    data = {"source_id": str(source.id), "confirmed": True}
    assert client.get(PREFIX).status_code == 401
    client.cookies.set(COOKIE_NAME, tokens["viewer"])
    assert client.post(PREFIX, json=data, headers=ORIGIN).status_code == 403
    client.cookies.set(COOKIE_NAME, tokens["analyst"])
    assert client.post(PREFIX, json=data).status_code == 403
    assert (
        client.post(
            PREFIX, json=data | {"confirmed": False}, headers=ORIGIN
        ).status_code
        == 422
    )
    assert (
        client.post(
            PREFIX, json=data | {"path": "/outside"}, headers=ORIGIN
        ).status_code
        == 422
    )
    queued = client.post(PREFIX, json=data, headers=ORIGIN)
    assert queued.status_code == 202
    details = queued.json()
    assert details["status"] == "queued"
    assert client.post(PREFIX, json=data, headers=ORIGIN).status_code == 409
    with Redis.from_url(load_config()["REDIS_URL"]) as redis:
        assert redis.lpop(WAKE_KEY) == b"ready"
        # Consume the notification before the worker starts. PostgreSQL still has the job.

    worker = subprocess.Popen(
        [sys.executable, "-m", "app.workers.scan"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 12
        href = f"{PREFIX}/{details['id']}"
        while time.monotonic() < deadline:
            assert worker.poll() is None
            result = client.get(href).json()
            if result["status"] not in {"queued", "running"}:
                break
            time.sleep(0.1)
        assert result["status"] == "completed"
        assert result["attempts"] == 1
        assert result["files_processed"] == result["findings_created"] == 2
        assert result in client.get(PREFIX).json()
        assert (
            client.post(f"{href}/cancel", headers=ORIGIN).json()["status"]
            == "completed"
        )
    finally:
        worker.terminate()
        worker.wait(timeout=6)

    pending = client.post(PREFIX, json=data, headers=ORIGIN).json()
    cancelled = client.post(f"{PREFIX}/{pending['id']}/cancel", headers=ORIGIN).json()
    assert (cancelled["status"], cancelled["attempts"]) == ("cancelled", 0)


@WSL_ONLY
def test_stale_worker_cannot_duplicate_file_results(stack, monkeypatch):
    _, sessions, source, user, _ = stack
    config = load_config()
    job_id = enqueue(sessions, source.id, user.id, LOCAL_ORGANISATION).id
    first_claim = claim_next(sessions, DURATION, job_id=job_id)
    process = pipeline.process_file
    replacement_claim = None

    def expire_after_first_commit(entry, *args):
        nonlocal replacement_claim
        if entry.relative_path.name == "b.txt":
            with sessions.begin() as db:
                job = db.get(ScanJob, job_id)
                assert job.files_processed == 1
                job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
            replacement_claim = claim_next(sessions, DURATION, job_id=job_id)
        return process(entry, *args)

    with monkeypatch.context() as patch:
        patch.setattr(pipeline, "process_file", expire_after_first_commit)
        pipeline.run_claim(sessions, config, first_claim)
    assert (
        replacement_claim is not None and replacement_claim.token != first_claim.token
    )
    pipeline.run_claim(sessions, config, replacement_claim)
    with sessions() as db:
        job = db.get(ScanJob, job_id)
        assert (
            job.status,
            job.attempts,
            job.files_processed,
            job.findings_created,
        ) == ("completed", 2, 2, 2)
        results = db.scalars(
            select(Finding)
            .join(ScannedFile, ScannedFile.id == Finding.scanned_file_id)
            .where(ScannedFile.scan_job_id == job_id)
        ).all()
        assert len(results) == 2


@WSL_ONLY
def test_running_cancellation_discards_in_flight_result(stack, monkeypatch):
    _, sessions, source, user, _ = stack
    job_id = enqueue(sessions, source.id, user.id, LOCAL_ORGANISATION).id
    claim = claim_next(sessions, DURATION, job_id=job_id)
    process = pipeline.process_file

    def cancel_during_read(*args):
        cancel(sessions, job_id, user.id, LOCAL_ORGANISATION)
        return process(*args)

    monkeypatch.setattr(pipeline, "process_file", cancel_during_read)
    pipeline.run_claim(sessions, load_config(), claim)
    with sessions() as db:
        job = db.get(ScanJob, job_id)
        assert (job.status, job.files_processed, job.findings_created) == (
            "cancelled",
            0,
            0,
        )
        assert set(
            db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == job_id))
        ) == {"queued", "cancel_requested"}


def test_retry_limit_is_terminal(stack):
    _, sessions, source, user, _ = stack
    job_id = enqueue(sessions, source.id, user.id, LOCAL_ORGANISATION).id
    claim_next(sessions, DURATION, job_id=job_id)
    with sessions.begin() as db:
        job = db.get(ScanJob, job_id)
        job.attempts = MAX_ATTEMPTS
        job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert claim_next(sessions, DURATION, job_id=job_id) is None
    with sessions() as db:
        job = db.get(ScanJob, job_id)
        assert (job.status, job.error_summary) == ("failed", "retry_limit")


@WSL_ONLY
def test_worker_interrupt_releases_active_claim(stack, monkeypatch):
    from app.workers import scan

    _, sessions, source, user, _ = stack
    job_id = enqueue(sessions, source.id, user.id, LOCAL_ORGANISATION).id

    def interrupted(*args, **kwargs):
        scan.interrupt(None, None)

    monkeypatch.setattr(scan, "run_claim", interrupted)
    scan.run_worker(sessions, None, load_config())
    replacement = claim_next(sessions, DURATION, job_id=job_id)
    assert replacement is not None
    pipeline.run_claim(sessions, load_config(), replacement)
    with sessions() as db:
        job = db.get(ScanJob, job_id)
        assert (job.status, job.attempts, job.files_processed) == ("completed", 2, 2)
