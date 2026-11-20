"""Configuration is validated without displaying secret values."""

import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[3]


def load_config() -> dict[str, str]:
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
    if any(not value or "replace_with_" in value for value in values.values()):
        raise ValueError("Missing or placeholder configuration; check .env.")
    try:
        origin = os.getenv("BROWSER_ORIGIN", "http://127.0.0.1:5173")
        browser = urlsplit(origin)
        if (
            browser.scheme not in ("http", "https")
            or browser.hostname not in ("127.0.0.1", "localhost")
            or browser.username is not None
            or origin != f"{browser.scheme}://{browser.netloc}"
            or browser.port == 0
        ):
            raise ValueError
        values["BROWSER_ORIGIN"] = origin
        db = make_url(values["DATABASE_URL"])
        redis = urlsplit(values["REDIS_URL"])
        roots = json.loads(values["ALLOWED_SCAN_ROOTS"])
        numbers = [
            int(values[n])
            for n in (
                "HMAC_KEY_VERSION",
                "MAX_FILE_SIZE_BYTES",
                "MAX_SCAN_DEPTH",
                "MAX_FILES_PER_SCAN",
                "MAX_PROCESSING_SECONDS_PER_FILE",
            )
        ]
        if (
            db.drivername != "postgresql+psycopg"
            or db.host not in ("127.0.0.1", "localhost")
            or db.password != values["POSTGRES_PASSWORD"]
            or redis.scheme != "redis"
            or redis.hostname not in ("127.0.0.1", "localhost")
            or redis.password != values["REDIS_PASSWORD"]
            or not isinstance(roots, list)
            or any(not isinstance(p, str) or not Path(p).is_absolute() for p in roots)
            or any(n <= 0 for n in numbers)
            or values["LOG_LEVEL"] not in ("DEBUG", "INFO", "WARNING", "ERROR")
            or min(len(values["APPLICATION_SECRET"]), len(values["HMAC_KEY"])) < 32
        ):
            raise ValueError
    except (TypeError, ValueError, KeyError):
        raise ValueError(
            "Invalid configuration; check .env without sharing secrets."
        ) from None
    return values
