"""Password hashing and opaque session identifiers."""

import hashlib
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

password_hasher = PasswordHasher()
USERNAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.-]{2,63}", re.ASCII)
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}", re.ASCII)
COOKIE_NAME = "datasleuth_session"


def normalize_username(value: str) -> str:
    value = value.strip().lower()
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValueError("Use 3–64 letters, digits, dots, underscores or hyphens.")
    return value


def verify_password(encoded: str, password: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except VerifyMismatchError:
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)
