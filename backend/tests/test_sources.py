"""Source permissions, path validation and auditing against PostgreSQL."""

from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.manage_users import create_member
from app.models.organisation import LOCAL_ORGANISATION
from app.core.auth import COOKIE_NAME, new_token, token_digest
from app.main import app
from app.models.auth import BrowserSession
from app.models.source import AuditEvent

PREFIX = "/api/v1/sources"
ORIGIN = {"Origin": "http://127.0.0.1:5173"}


def test_source_lifecycle_and_access(services, tmp_path, monkeypatch):
    root = tmp_path / "approved"
    root.mkdir()
    monkeypatch.setenv("ALLOWED_SCAN_ROOTS", json.dumps([str(root)]))

    with TestClient(app) as client:
        assert client.get(PREFIX).status_code == 401
        tokens = {}
        with app.state.sessions.begin() as db:
            actor = None
            for role in ("analyst", "viewer"):
                user = create_member(
                    db,
                    organisation_id=LOCAL_ORGANISATION,
                    username=f"source-{uuid4().hex}",
                    role=role,
                    password_hash="unused",
                )
                db.add(user)
                db.flush()
                if role == "analyst":
                    actor = user.id
                token = new_token()
                tokens[role] = token
                db.add(
                    BrowserSession(
                        organisation_id=LOCAL_ORGANISATION,
                        token_digest=token_digest(token),
                        user_id=user.id,
                        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
                    )
                )

        payload = {"name": " Synthetic folder ", "configured_path": str(root)}
        client.cookies.set(COOKIE_NAME, tokens["viewer"])
        assert client.get(PREFIX).status_code == 403
        assert client.post(PREFIX, headers=ORIGIN, json=payload).status_code == 403

        client.cookies.set(COOKIE_NAME, tokens["analyst"])
        assert client.post(PREFIX, json=payload).status_code == 403
        denied = client.post(
            PREFIX, headers=ORIGIN, json=payload | {"configured_path": str(tmp_path)}
        )
        assert denied.status_code == 422
        assert str(tmp_path) not in denied.text
        created = client.post(PREFIX, headers=ORIGIN, json=payload)
        assert created.status_code == 201
        assert created.headers["cache-control"] == "no-store"
        source = created.json()
        assert source["name"] == "Synthetic folder"
        assert source["enabled"] is True
        assert client.post(PREFIX, headers=ORIGIN, json=payload).status_code == 409
        href = f"{PREFIX}/{source['id']}"
        assert client.get(href).json() == source
        assert source in client.get(PREFIX).json()
        assert (
            client.patch(
                href, headers=ORIGIN, json={"configured_path": str(tmp_path)}
            ).status_code
            == 422
        )
        assert (
            client.patch(href, headers=ORIGIN, json={"enabled": False}).json()[
                "enabled"
            ]
            is False
        )
        app.state.scan_roots = {}
        assert (
            client.patch(href, headers=ORIGIN, json={"enabled": True}).status_code
            == 422
        )
        with app.state.sessions() as db:
            events = db.scalars(
                select(AuditEvent).where(AuditEvent.actor_id == actor)
            ).all()
            assert {event.action for event in events} == {"created", "updated"}
            assert all(str(event.entity_id) == source["id"] for event in events)
