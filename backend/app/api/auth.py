"""Browser authentication and authorization dependencies."""

from datetime import datetime, timedelta, timezone
import hmac
from threading import BoundedSemaphore
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, SecretStr
from redis.exceptions import RedisError
from sqlalchemy import delete, select

from app.core.auth import (
    COOKIE_NAME,
    TOKEN_PATTERN,
    new_token,
    normalize_username,
    password_hasher,
    token_digest,
    verify_password,
)
from app.models.auth import BrowserSession, User
from app.models.organisation import Membership, Organisation, LOCAL_ORGANISATION

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])
SESSION_LIFETIME = timedelta(hours=8)
password_checks = BoundedSemaphore(4)


class Credentials(BaseModel):
    organisation_id: UUID = LOCAL_ORGANISATION
    username: str = Field(max_length=128)
    password: SecretStr = Field(min_length=1, max_length=256)


class Account(BaseModel):
    id: UUID
    username: str
    role: str


class SessionAccount(Account):
    organisation_name: str
    organisation_id: UUID


def require_browser_origin(request: Request) -> None:
    if request.headers.get("origin") not in request.app.state.browser_origins:
        raise HTTPException(403, "Request origin is not allowed")


def apply_login_limit(request: Request, username: str) -> None:
    # A global ceiling also limits attempts that rotate account names.
    redis = request.app.state.redis
    global_key = "datasleuth:auth:login:global"
    account_digest = hmac.digest(
        request.app.state.login_limit_key, username.encode("ascii"), "sha256"
    ).hex()
    account_key = f"datasleuth:auth:login:{account_digest}"
    try:
        with redis.pipeline() as pipe:
            pipe.incr(global_key).expire(global_key, 60, nx=True)
            pipe.incr(account_key).expire(account_key, 60, nx=True)
            global_count, _, account_count, _ = pipe.execute()
    except RedisError:
        raise HTTPException(503, "Sign-in is temporarily unavailable") from None
    if global_count > 60 or account_count > 10:
        raise HTTPException(
            429, "Too many sign-in attempts", headers={"Retry-After": "60"}
        )


def request_digest(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME, "")
    if TOKEN_PATTERN.fullmatch(token):
        return token_digest(token)
    return None


def check_expected_organisation(request: Request, organisation_id: UUID) -> None:
    expected = request.headers.get("X-DataSleuth-Organisation")
    if expected is not None and expected != str(organisation_id):
        raise HTTPException(409, "Session organisation changed. Refresh the page.")


def current_user(request: Request) -> SessionAccount:
    digest = request_digest(request)
    if digest:
        with request.app.state.sessions() as db:
            user = (
                db.execute(
                    select(
                        User.id,
                        User.username,
                        Membership.role,
                        Membership.organisation_id,
                        Organisation.name.label("organisation_name"),
                    )
                    .join(Membership, Membership.user_id == User.id)
                    .join(Organisation, Organisation.id == Membership.organisation_id)
                    .join(
                        BrowserSession,
                        (BrowserSession.user_id == User.id)
                        & (
                            BrowserSession.organisation_id == Membership.organisation_id
                        ),
                    )
                    .where(
                        BrowserSession.token_digest == digest,
                        BrowserSession.expires_at > datetime.now(timezone.utc),
                        User.active.is_(True),
                    )
                )
                .mappings()
                .one_or_none()
            )
            if user is not None:
                check_expected_organisation(request, user["organisation_id"])
                return SessionAccount.model_validate(user)
    raise HTTPException(401, "Sign-in required")


def require_roles(*allowed: str):
    def authorize(
        user: Annotated[SessionAccount, Depends(current_user)],
    ) -> SessionAccount:
        if user.role not in allowed:
            raise HTTPException(403, "Permission denied")
        return user

    return authorize


@router.post(
    "/login",
    response_model=SessionAccount,
    dependencies=[Depends(require_browser_origin)],
)
def login(credentials: Credentials, request: Request, response: Response):
    try:
        username = normalize_username(credentials.username)
    except ValueError:
        username = ""
    apply_login_limit(request, username)
    password = credentials.password.get_secret_value()
    now = datetime.now(timezone.utc)
    with request.app.state.sessions.begin() as db:
        user = db.scalar(select(User).where(User.username == username))
        encoded = user.password_hash if user else request.app.state.dummy_password_hash
        if not password_checks.acquire(blocking=False):
            raise HTTPException(503, "Sign-in is temporarily unavailable")
        try:
            valid = verify_password(encoded, password)
            if not valid or user is None or not user.active:
                raise HTTPException(401, "Invalid username or password")
            # Serialize session issuance against a concurrent local password reset.
            db.refresh(user, with_for_update=True)
            if not user.active or user.password_hash != encoded:
                raise HTTPException(401, "Invalid username or password")
            if password_hasher.check_needs_rehash(encoded):
                user.password_hash = password_hasher.hash(password)
        finally:
            password_checks.release()
        db.execute(delete(BrowserSession).where(BrowserSession.expires_at <= now))
        previous = request_digest(request)
        if previous:
            db.execute(
                delete(BrowserSession).where(BrowserSession.token_digest == previous)
            )
        membership = db.get(
            Membership, (credentials.organisation_id, user.id), with_for_update=True
        )
        if membership is None:
            raise HTTPException(401, "Invalid username or password")
        account = SessionAccount(
            id=user.id,
            username=user.username,
            organisation_name=db.get(Organisation, membership.organisation_id).name,
            role=membership.role,
            organisation_id=membership.organisation_id,
        )
        token = new_token()
        db.add(
            BrowserSession(
                token_digest=token_digest(token),
                organisation_id=membership.organisation_id,
                user_id=user.id,
                expires_at=now + SESSION_LIFETIME,
            )
        )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        path="/api/v1",
        httponly=True,
        secure=request.app.state.secure_cookies,
        samesite="strict",
    )
    return account


@router.get("/me", response_model=SessionAccount)
def me(user: Annotated[SessionAccount, Depends(current_user)]):
    return user


@router.get("/users", response_model=list[Account])
def list_users(
    request: Request, admin: Annotated[SessionAccount, Depends(require_roles("admin"))]
):
    with request.app.state.sessions() as db:
        return (
            db.execute(
                select(User.id, User.username, Membership.role)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.organisation_id == admin.organisation_id)
                .order_by(User.username)
            )
            .mappings()
            .all()
        )


@router.post("/logout", status_code=204, dependencies=[Depends(require_browser_origin)])
def logout(request: Request, response: Response):
    digest = request_digest(request)
    if digest:
        with request.app.state.sessions.begin() as db:
            session = db.get(BrowserSession, digest, with_for_update=True)
            if session is not None:
                check_expected_organisation(request, session.organisation_id)
                db.delete(session)
    response.delete_cookie(
        COOKIE_NAME,
        path="/api/v1",
        httponly=True,
        secure=request.app.state.secure_cookies,
        samesite="strict",
    )
