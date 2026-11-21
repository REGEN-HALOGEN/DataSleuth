"""Authentication checks against explicitly selected disposable services."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from contextlib import closing
from sqlalchemy import update

from app.manage_users import create_member
from app.models.organisation import LOCAL_ORGANISATION, Membership
from app.core.auth import COOKIE_NAME, password_hasher, token_digest
from app.main import app
from app.models.auth import BrowserSession, User

ORIGIN = "http://127.0.0.1:5173"
PASSWORD = "synthetic passphrase for authentication tests"
PREFIX = "/api/v1/auth"


@pytest.fixture
def accounts(services):
    suffix = uuid4().hex
    encoded = password_hasher.hash(PASSWORD)
    from app.core.config import load_config
    from app.db.session import create_database

    engine, sessions = create_database(load_config()["DATABASE_URL"])
    try:
        with sessions.begin() as db:
            users = [
                create_member(
                    db,
                    organisation_id=LOCAL_ORGANISATION,
                    username=f"test-{role}-{suffix}",
                    role=role,
                    password_hash=encoded,
                )
                for role in ("admin", "analyst", "viewer")
            ]
            db.add_all(users)
    finally:
        engine.dispose()
    return dict(zip(("admin", "analyst", "viewer"), users, strict=True))


def post_login(client, username, password=PASSWORD, origin=ORIGIN):
    return client.post(
        f"{PREFIX}/login",
        json={"username": username, "password": password},
        headers={"Origin": origin},
    )


def test_login_rotation_logout_and_protected_endpoints(accounts):
    admin = accounts["admin"]
    with TestClient(app) as client, closing(TestClient(app)) as other:
        assert client.get(f"{PREFIX}/me").status_code == 401
        assert client.get(f"{PREFIX}/users").status_code == 401
        response = post_login(client, admin.username.upper())
        assert response.status_code == 200
        assert response.json() == {
            "id": str(admin.id),
            "organisation_id": str(LOCAL_ORGANISATION),
            "organisation_name": "Local organisation",
            "username": admin.username,
            "role": "admin",
        }
        assert response.headers["cache-control"] == "no-store"
        assert "httponly" in response.headers["set-cookie"].lower()
        assert "samesite=strict" in response.headers["set-cookie"].lower()
        first_token = client.cookies[COOKIE_NAME]
        with app.state.sessions() as db:
            session = db.get(BrowserSession, token_digest(first_token))
            assert session is not None and session.user_id == admin.id
            assert db.get(BrowserSession, first_token) is None
            assert db.get(User, admin.id).password_hash.startswith("$argon2id$")
        assert client.get(f"{PREFIX}/me").status_code == 200
        response = client.get(f"{PREFIX}/users")
        assert response.status_code == 200
        assert all(set(user) == {"id", "username", "role"} for user in response.json())

        assert post_login(client, admin.username).status_code == 200
        second_token = client.cookies[COOKIE_NAME]
        assert first_token != second_token
        other.cookies.set(COOKIE_NAME, first_token)
        assert other.get(f"{PREFIX}/me").status_code == 401
        assert client.post(f"{PREFIX}/logout").status_code == 403
        assert client.get(f"{PREFIX}/me").status_code == 200
        assert (
            client.post(f"{PREFIX}/logout", headers={"Origin": ORIGIN}).status_code
            == 204
        )
        other.cookies.set(COOKIE_NAME, second_token)
        assert other.get(f"{PREFIX}/me").status_code == 401
        assert client.get(f"{PREFIX}/me").status_code == 401


@pytest.mark.parametrize("role", ["analyst", "viewer"])
def test_role_changes_expiry_and_disabled_accounts(accounts, role):
    user = accounts[role]
    with TestClient(app) as client:
        assert post_login(client, user.username).status_code == 200
        assert client.get(f"{PREFIX}/users").status_code == 403
        with app.state.sessions.begin() as db:
            db.execute(
                update(Membership)
                .where(
                    Membership.user_id == user.id,
                    Membership.organisation_id == LOCAL_ORGANISATION,
                )
                .values(role="admin")
            )
        assert client.get(f"{PREFIX}/users").status_code == 200
        with app.state.sessions.begin() as db:
            session = db.get(BrowserSession, token_digest(client.cookies[COOKIE_NAME]))
            session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        assert client.get(f"{PREFIX}/me").status_code == 401
        assert post_login(client, user.username).status_code == 200
        with app.state.sessions.begin() as db:
            db.execute(update(User).where(User.id == user.id).values(active=False))
        assert client.get(f"{PREFIX}/me").status_code == 401
        assert post_login(client, user.username).status_code == 401


def test_bad_credentials_origin_and_login_throttling(accounts):
    username = accounts["viewer"].username
    with TestClient(app) as client:
        assert (
            post_login(client, username, origin="http://localhost:5173").status_code
            == 403
        )
        missing_user = post_login(client, f"absent-{uuid4().hex}")
        for _ in range(10):
            failure = post_login(client, username, password="wrong")
            assert failure.status_code == 401
            assert failure.json() == missing_user.json()
        assert post_login(client, username).status_code == 429
        assert COOKIE_NAME not in client.cookies


def test_malformed_body_does_not_echo_password(monkeypatch):
    monkeypatch.setattr(app.state, "browser_origins", {ORIGIN}, raising=False)
    response = TestClient(app).post(
        f"{PREFIX}/login",
        json={"username": [], "password": {"synthetic-secret": "private"}},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "Invalid request"}
    assert response.headers["cache-control"] == "no-store"


def test_secure_cookie_for_https_origin(accounts, monkeypatch):
    origin = "https://127.0.0.1:5173"
    monkeypatch.setenv("BROWSER_ORIGIN", origin)
    with TestClient(app, base_url=origin) as client:
        response = post_login(client, accounts["viewer"].username, origin=origin)
        assert response.status_code == 200
        assert "; secure" in response.headers["set-cookie"].lower()
        assert client.get(f"{PREFIX}/me").status_code == 200


def test_login_fails_closed_if_throttling_unavailable(accounts, monkeypatch):
    from redis.exceptions import RedisError

    with TestClient(app) as client:

        def unavailable():
            raise RedisError("synthetic credential")

        monkeypatch.setattr(app.state.redis, "pipeline", unavailable)
        response = post_login(client, accounts["viewer"].username)
        assert response.status_code == 503
        assert "synthetic credential" not in response.text
        assert COOKIE_NAME not in client.cookies


def test_local_admin_reset_revokes_sessions(accounts, monkeypatch):
    from app import manage_users

    admin = accounts["admin"]
    replacement = "synthetic replacement passphrase"
    with TestClient(app) as client:
        assert post_login(client, admin.username).status_code == 200
        monkeypatch.setattr(
            "sys.argv", ["manage_users", "--reset-admin-password", admin.username]
        )
        monkeypatch.setattr(manage_users, "getpass", lambda prompt: replacement)
        manage_users.main()
        assert client.get(f"{PREFIX}/me").status_code == 401
        assert post_login(client, admin.username).status_code == 401
        assert (
            post_login(client, admin.username, password=replacement).status_code == 200
        )
