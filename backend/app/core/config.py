"""Configuration is validated without displaying secret values."""

import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID

from app.models.organisation import LOCAL_ORGANISATION
from app.storage.supabase import PrivateBucket

from dotenv import load_dotenv
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[3]


def organisation_roots(config: dict[str, str]) -> dict[UUID, tuple[Path, ...]]:
    """Global legacy roots belong exclusively to the original local organisation."""
    grants = json.loads(config.get("ORGANISATION_SCAN_ROOTS", "{}"))
    if not isinstance(grants, dict):
        raise ValueError
    roots = {
        LOCAL_ORGANISATION: tuple(
            Path(p) for p in json.loads(config["ALLOWED_SCAN_ROOTS"])
        )
    }
    for key, paths in grants.items():
        org = UUID(key)
        if org in roots or not isinstance(paths, list):
            raise ValueError
        roots[org] = tuple(Path(p) for p in paths)

    if grants:
        # A differently cased WSL mount path can refer to the same directory.
        # Compare ancestor device/inode identities before granting filesystem access.
        identities = []
        for org, directories in roots.items():
            for directory in directories:
                if (
                    not directory.is_absolute()
                    or directory.resolve(strict=True) != directory
                    or not directory.is_dir()
                ):
                    raise ValueError
                ancestors = []
                for path in (directory, *directory.parents):
                    stat = path.stat()
                    ancestors.append((stat.st_dev, stat.st_ino))
                for other_org, other in identities:
                    if org != other_org and (
                        ancestors[0] in other or other[0] in ancestors
                    ):
                        raise ValueError
                identities.append((org, ancestors))
    return {} if config.get("DATASLEUTH_MODE") == "hosted" else roots


def deployment_mode() -> str:
    mode = os.getenv("DATASLEUTH_MODE", "local")
    if mode not in ("local", "hosted"):
        raise ValueError("Invalid deployment mode.")
    return mode


def database_url(*, migration: bool = False) -> str:
    hosted = deployment_mode() == "hosted"
    if not hosted:
        load_dotenv(ROOT / ".env", override=False)
    name = "MIGRATION_DATABASE_URL" if hosted and migration else "DATABASE_URL"
    value = os.getenv(name, "")
    try:
        db = make_url(value)
        if (
            db.drivername != "postgresql+psycopg"
            or not db.database
            or not db.host
            or not db.password
            or "replace_with_" in value
        ):
            raise ValueError
        if hosted:
            if (
                db.query.get("sslmode") != "verify-full"
                or db.port not in (None, 5432)
                or {"host", "hostaddr", "service", "port"}.intersection(db.query)
            ):
                raise ValueError
        elif (
            db.host not in ("127.0.0.1", "localhost")
            or db.password != os.getenv("POSTGRES_PASSWORD")
            or {"host", "hostaddr", "service"}.intersection(db.query)
        ):
            raise ValueError
    except (ArgumentError, ValueError, TypeError):
        raise ValueError("Invalid database configuration.") from None
    return value


def load_config(*, service: str = "api") -> dict[str, str]:
    mode = deployment_mode()
    hosted = mode == "hosted"
    if not hosted:
        load_dotenv(ROOT / ".env", override=False)
    names = (
        "POSTGRES_PASSWORD",
        "DATABASE_URL",
        "REDIS_PASSWORD",
        "REDIS_URL",
        "APPLICATION_SECRET",
        "HMAC_KEY",
        "HMAC_KEY_VERSION",
        "ALLOWED_SCAN_ROOTS",
        "MAX_FILE_SIZE_BYTES",
        "MAX_SCAN_DEPTH",
        "MAX_FILES_PER_SCAN",
        "MAX_PROCESSING_SECONDS_PER_FILE",
        "LOG_LEVEL",
    )
    values = {name: os.getenv(name, "") for name in names}
    required = set(names)
    if hosted:
        required -= {"POSTGRES_PASSWORD", "REDIS_PASSWORD", "ALLOWED_SCAN_ROOTS"}
        required -= (
            {"HMAC_KEY", "HMAC_KEY_VERSION"}
            if service == "api"
            else {"APPLICATION_SECRET"}
        )
        values["ALLOWED_SCAN_ROOTS"] = os.getenv("ALLOWED_SCAN_ROOTS", "[]")
    if any(not values[name] or "replace_with_" in values[name] for name in required):
        raise ValueError(
            "Missing or placeholder configuration; check environment settings."
        )
    try:
        values["DATASLEUTH_MODE"] = mode
        values["DATABASE_URL"] = database_url()
        if service == "api" or not hosted:
            origin = os.getenv(
                "BROWSER_ORIGIN", "" if hosted else "http://127.0.0.1:5173"
            )
            browser = urlsplit(origin)
            if (
                not browser.hostname
                or browser.username is not None
                or origin != f"{browser.scheme}://{browser.netloc}"
                or browser.port == 0
                or (
                    hosted
                    and (
                        browser.scheme != "https"
                        or not re.fullmatch(r"[a-z0-9.-]+", browser.hostname)
                    )
                )
                or (
                    not hosted
                    and (
                        browser.scheme not in ("http", "https")
                        or browser.hostname not in ("127.0.0.1", "localhost")
                    )
                )
            ):
                raise ValueError
            values["BROWSER_ORIGIN"] = origin
        redis = urlsplit(values["REDIS_URL"])
        if hosted:
            # Render's authenticated private Key Value endpoint uses plaintext TCP.
            render_private = redis.scheme == "redis" and re.fullmatch(
                r"red-[a-z0-9-]+", redis.hostname or ""
            )
            if (
                not redis.password
                or redis.query
                or redis.fragment
                or not redis.hostname
                or not (redis.scheme == "rediss" or render_private)
            ):
                raise ValueError
        elif (
            redis.scheme != "redis"
            or redis.hostname not in ("127.0.0.1", "localhost")
            or redis.password != values["REDIS_PASSWORD"]
        ):
            raise ValueError
        roots = json.loads(values["ALLOWED_SCAN_ROOTS"])
        numbers = [
            int(values[n])
            for n in (
                "MAX_FILE_SIZE_BYTES",
                "MAX_SCAN_DEPTH",
                "MAX_FILES_PER_SCAN",
                "MAX_PROCESSING_SECONDS_PER_FILE",
            )
            if n in required
        ]
        if "HMAC_KEY_VERSION" in required:
            numbers.append(int(values["HMAC_KEY_VERSION"]))
        if (
            not isinstance(roots, list)
            or any(not isinstance(p, str) or not Path(p).is_absolute() for p in roots)
            or any(n <= 0 for n in numbers)
            or values["LOG_LEVEL"] not in ("DEBUG", "INFO", "WARNING", "ERROR")
            or any(
                len(values[name]) < 32
                for name in ("APPLICATION_SECRET", "HMAC_KEY")
                if name in required
            )
        ):
            raise ValueError
        values["ORGANISATION_SCAN_ROOTS"] = os.getenv("ORGANISATION_SCAN_ROOTS", "{}")
        organisation_roots(values)
        for name in (
            "SUPABASE_STORAGE_URL",
            "SUPABASE_STORAGE_BUCKET",
            "SUPABASE_STORAGE_KEY",
            "UPLOAD_INTEGRITY_KEY",
            "UPLOAD_RETENTION_HOURS",
            "UPLOAD_ORG_QUOTA_BYTES",
        ):
            if name in os.environ:
                values[name] = os.environ[name]
        bucket = PrivateBucket.from_config(values)
        if hosted and (
            roots
            or json.loads(values["ORGANISATION_SCAN_ROOTS"]) != {}
            or bucket is None
            or not bucket.url.startswith("https://")
        ):
            raise ValueError
    except (TypeError, ValueError, KeyError, OSError, RuntimeError):
        raise ValueError(
            "Invalid configuration; check .env without sharing secrets."
        ) from None
    return values
