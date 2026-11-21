"""Exercise authenticated uploads and the worker against disposable Supabase Storage."""

from datetime import datetime, timedelta, timezone
import os
from uuid import UUID, uuid4
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
import httpx
import pytest

from app.core.auth import COOKIE_NAME, new_token, token_digest
from app.core.config import load_config
from app.main import app
from app.manage_users import create_member
from app.models.auth import BrowserSession
from app.models.organisation import Organisation
from app.models.scan import ScanJob
from app.models.source import ScanSource
from app.scanners.pipeline import lease_duration, run_claim
from app.storage.retention import purge_due
from app.storage.supabase import MEDIA_TYPES, PrivateBucket, StorageUnavailable
from app.workers.queue import ScanError, claim_next
from test_scanner_content import synthetic_files

DOC = "/api/v1/documents"
ORIGIN = {"Origin": "http://127.0.0.1:5173"}


@pytest.fixture
def storage(services, monkeypatch):
    for name in (
        "SUPABASE_STORAGE_URL",
        "SUPABASE_STORAGE_BUCKET",
        "SUPABASE_STORAGE_KEY",
    ):
        value = os.getenv(f"DATASLEUTH_TEST_{name}")
        if not value:
            pytest.skip(
                "Set DATASLEUTH_TEST_SUPABASE_STORAGE_* for disposable storage integration."
            )
        if name.endswith("URL") and urlsplit(value).hostname != "127.0.0.1":
            pytest.fail("Use a disposable loopback storage service.")
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(
        "UPLOAD_INTEGRITY_KEY", "synthetic-storage-integrity-key-for-disposable-checks"
    )
    monkeypatch.setenv("UPLOAD_ORG_QUOTA_BYTES", str(1024 * 1024))
    with TestClient(app) as client:
        identities = []
        with app.state.sessions.begin() as db:
            for role in ("analyst", "analyst", "viewer"):
                org = Organisation(name="Synthetic", id=uuid4())
                db.add(org)
                db.flush()
                user = create_member(
                    db,
                    username=f"storage-{uuid4().hex}",
                    password_hash="unused",
                    role=role,
                    organisation_id=org.id,
                )
                token = new_token()
                db.add(
                    BrowserSession(
                        user_id=user.id,
                        organisation_id=org.id,
                        token_digest=token_digest(token),
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                    )
                )
                identities.append((org.id, token))
        client.cookies.set(COOKIE_NAME, identities[0][1])
        yield client, identities, app.state.bucket


def reserve(client, ext, size):
    return client.post(
        DOC,
        headers=ORIGIN,
        json={"name": "Synthetic input", "extension": ext, "size_bytes": size},
    )


def put(client, ref, data, media):
    return client.put(
        f"{DOC}/{ref}/content", headers={**ORIGIN, "Content-Type": media}, content=data
    )


def launch(client, ref):
    return client.post(
        "/api/v1/scans", headers=ORIGIN, json={"source_id": ref, "confirmed": True}
    )


def claim(job, bucket):
    return claim_next(
        app.state.sessions,
        lease_duration(load_config()),
        job_id=UUID(job),
        organisation_ids=(),
        namespace=bucket.namespace,
    )


def test_private_round_trip_and_fenced_retry(storage, monkeypatch):
    client, identities, bucket = storage
    org, token = identities[0]
    data = b"synthetic-upload@example.invalid\n" * 2
    reservation = reserve(client, ".txt", len(data))
    assert reservation.status_code == 201
    ref = reservation.json()["id"]
    client.cookies.set(COOKIE_NAME, identities[1][1])
    assert put(client, ref, data, "text/plain").status_code == 404
    assert client.delete(f"{DOC}/{ref}", headers=ORIGIN).status_code == 404
    client.cookies.set(COOKIE_NAME, identities[2][1])
    assert reserve(client, ".txt", 10).status_code == 403
    client.cookies.set(COOKIE_NAME, token)
    assert launch(client, ref).status_code == 409
    assert put(client, ref, data, "text/plain").json()["upload_state"] == "ready"
    assert put(client, ref, data, "text/plain").status_code == 409
    assert (
        httpx.get(f"{bucket.url}/object/public/{bucket.bucket}/{org}/{ref}").status_code
        >= 400
    )
    job = launch(client, ref).json()["id"]
    assert client.delete(f"{DOC}/{ref}", headers=ORIGIN).status_code == 409
    first = claim(job, bucket)

    def unavailable(*args):
        raise StorageUnavailable

    with monkeypatch.context() as patch:
        patch.setattr(PrivateBucket, "open_verified", unavailable)
        with pytest.raises(ScanError):
            run_claim(app.state.sessions, load_config(), first)
    with app.state.sessions.begin() as db:
        stored = db.get(ScanJob, UUID(job))
        assert stored.inventory_ready and stored.files_processed == 0
        stored.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    replacement = claim(job, bucket)
    run_claim(app.state.sessions, load_config(), first)
    run_claim(app.state.sessions, load_config(), replacement)
    result = client.get(f"/api/v1/scans/{job}").json()
    assert (
        result["attempts"],
        result["files_processed"],
        result["findings_created"],
    ) == (2, 1, 2)
    assert (
        client.delete(f"{DOC}/{ref}", headers=ORIGIN).json()["upload_state"]
        == "deleting"
    )
    with monkeypatch.context() as patch:
        patch.setattr(PrivateBucket, "delete", unavailable)
        purge_due(app.state.sessions, bucket)
    with app.state.sessions.begin() as db:
        source = db.get(ScanSource, UUID(ref))
        assert source.upload_state == "deleting" and not source.enabled
        source.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    purge_due(app.state.sessions, bucket)
    assert client.get(f"/api/v1/sources/{ref}").json()["upload_state"] == "deleted"
    with bucket.client() as provider:
        assert (
            provider.get(
                f"object/authenticated/{bucket.bucket}/{org}/{ref}"
            ).status_code
            >= 400
        )
    report = client.post(
        "/api/v1/reports/findings.json", headers=ORIGIN, json={"scan_id": job}
    )
    assert report.json()["row_count"] == 2 and data.decode().strip() not in report.text


def test_ingress_limits_and_expiry(storage):
    client, idents, bucket = storage
    params = {"name": "Synthetic", "extension": ".json", "size_bytes": 4}
    assert client.post(DOC, json=params).status_code == 403
    assert (
        client.post(
            DOC, json=params | {"url": "https://example.invalid"}, headers=ORIGIN
        ).status_code
        == 422
    )
    assert reserve(client, ".json", 1024 * 1024 + 1).status_code == 409
    assert reserve(client, ".exe", 4).status_code == 422
    ref = reserve(client, ".json", 4).json()["id"]
    assert put(client, ref, b"null", "text/plain").status_code == 415
    assert put(client, ref, b"12345", "application/json").status_code == 413
    assert put(client, ref, b"oops", "application/json").status_code == 422
    assert put(client, ref, b"null", "application/json").status_code == 200
    with app.state.sessions.begin() as db:
        db.get(ScanSource, UUID(ref)).expires_at = datetime.now(
            timezone.utc
        ) - timedelta(seconds=1)
    assert launch(client, ref).status_code == 409
    purge_due(app.state.sessions, bucket)
    assert client.get(f"/api/v1/sources/{ref}").json()["upload_state"] == "deleted"


def test_changed_object_fails_before_parsing(storage, monkeypatch):
    client, idents, bucket = storage
    org, _ = idents[0]
    ref = reserve(client, ".txt", 4).json()["id"]
    assert put(client, ref, b"good", "text/plain").status_code == 200
    with bucket.client() as provider:
        assert provider.put(
            f"object/{bucket.bucket}/{org}/{ref}",
            headers={"Content-Type": "text/plain"},
            content=b"else",
        ).is_success
    import app.storage.supabase as transport

    original = transport.TemporaryFile
    handles = []

    def scratch():
        handles.append(original())
        return handles[-1]

    monkeypatch.setattr(transport, "TemporaryFile", scratch)
    job = launch(client, ref).json()["id"]
    run_claim(app.state.sessions, load_config(), claim(job, bucket))
    result = client.get(f"/api/v1/scans/{job}").json()
    assert result["files_failed"] == 1 and result["findings_created"] == 0
    assert len(handles) == 1 and handles[0].closed


def test_supported_document_formats(storage, tmp_path):
    client, _, bucket = storage
    synthetic_files(tmp_path)
    for ext, media in MEDIA_TYPES.items():
        data = (tmp_path / f"input{ext}").read_bytes()
        ref = reserve(client, ext, len(data)).json()["id"]
        assert put(client, ref, data, media).status_code == 200, ext
        job = launch(client, ref).json()["id"]
        run_claim(app.state.sessions, load_config(), claim(job, bucket))
        result = client.get(f"/api/v1/scans/{job}").json()
        assert result["status"] == "completed" and result["findings_created"] > 0, ext


def test_endpoint_configuration_fails_closed():
    for url in (
        "https://example.invalid/storage/v1",
        "http://example.supabase.co/storage/v1",
        "https://a.supabase.co/storage/v1?url=unsafe",
    ):
        with pytest.raises(ValueError):
            PrivateBucket.from_config(
                {
                    "SUPABASE_STORAGE_URL": url,
                    "SUPABASE_STORAGE_BUCKET": "private",
                    "SUPABASE_STORAGE_KEY": "synthetic",
                    "UPLOAD_INTEGRITY_KEY": "synthetic-integrity-key-for-url-validation",
                }
            )


def test_abandoned_upload_and_unknown_write_outcome(storage, monkeypatch):
    client, identities, bucket = storage
    ref = reserve(client, ".txt", 4).json()["id"]
    abandoned = reserve(client, ".txt", 4).json()["id"]
    org = identities[0][0]
    original = PrivateBucket.upload

    def lost_reply(self, *args):
        original(self, *args)
        raise StorageUnavailable

    monkeypatch.setattr(PrivateBucket, "upload", lost_reply)
    assert put(client, ref, b"test", "text/plain").status_code == 503
    assert launch(client, ref).status_code == 409
    with app.state.sessions.begin() as db:
        for item in (ref, abandoned):
            db.get(ScanSource, UUID(item)).expires_at = datetime.now(
                timezone.utc
            ) - timedelta(seconds=1)
    purge_due(app.state.sessions, bucket)
    for item in (ref, abandoned):
        assert client.get(f"/api/v1/sources/{item}").json()["upload_state"] == "deleted"
    with bucket.client() as provider:
        assert (
            provider.get(
                f"object/authenticated/{bucket.bucket}/{org}/{ref}"
            ).status_code
            >= 400
        )


def test_refuses_public_bucket_before_writing():
    from io import BytesIO
    from contextlib import contextmanager

    bucket = PrivateBucket(
        "http://127.0.0.1:25000", "public-test", "synthetic", b"synthetic-key", 24, 1024
    )
    calls = []

    def respond(request):
        calls.append(request.method)
        return httpx.Response(
            200, stream=httpx.ByteStream(b'{"id":"public-test","public":true}')
        )

    @contextmanager
    def fake_client(self):
        with httpx.Client(
            base_url=bucket.url, transport=httpx.MockTransport(respond)
        ) as client:
            yield client

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(PrivateBucket, "client", fake_client)
        with pytest.raises(StorageUnavailable):
            bucket.upload(uuid4(), uuid4(), ".txt", 4, BytesIO(b"test"))
    assert calls == ["GET"]
