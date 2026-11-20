"""Create development secrets once; never overwrite existing configuration."""

import os
import secrets
from pathlib import Path

root = Path(__file__).resolve().parent.parent
path = root / ".env"
postgres = secrets.token_hex(32)
redis = secrets.token_hex(32)
content = f"""POSTGRES_PASSWORD={postgres}
DATABASE_URL=postgresql+psycopg://datasleuth:{postgres}@127.0.0.1:5432/datasleuth
REDIS_PASSWORD={redis}
REDIS_URL=redis://:{redis}@127.0.0.1:6379/0
APPLICATION_SECRET={secrets.token_hex(32)}
HMAC_KEY={secrets.token_hex(32)}
HMAC_KEY_VERSION=1
ALLOWED_SCAN_ROOTS=[]
MAX_FILE_SIZE_BYTES=10485760
MAX_SCAN_DEPTH=10
MAX_FILES_PER_SCAN=10000
MAX_PROCESSING_SECONDS_PER_FILE=30
LOG_LEVEL=INFO
BROWSER_ORIGIN=http://127.0.0.1:5173
"""
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    raise SystemExit(".env already exists; preserved without changes.")
with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as file:
    file.write(content)
print("Created .env; no scan roots are approved.")
