"""Authenticated Supabase Storage transport. The caller supplies only opaque IDs."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import hmac
import json
import re
from tempfile import TemporaryFile
from time import monotonic
from typing import BinaryIO
from urllib.parse import urlsplit
from uuid import UUID

import httpx

from app.scanners.readers import ReadFailure

CHUNK = 64 * 1024
TRANSFER_SECONDS = 45
MEDIA_TYPES = {
    ".txt": "text/plain",
    ".log": "text/plain",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroenabled.12",
}


class StorageUnavailable(Exception):
    """Provider or its privacy configuration is unavailable."""


@dataclass(frozen=True)
class PrivateBucket:
    url: str
    bucket: str
    key: str = field(repr=False)
    integrity_key: bytes = field(repr=False)
    retention_hours: int
    quota_bytes: int

    @classmethod
    def from_config(cls, config):
        url, bucket, key = (
            config.get(name, "")
            for name in (
                "SUPABASE_STORAGE_URL",
                "SUPABASE_STORAGE_BUCKET",
                "SUPABASE_STORAGE_KEY",
            )
        )
        integrity = config.get("UPLOAD_INTEGRITY_KEY", "")
        if not any((url, bucket, key, integrity)):
            return None
        parsed = urlsplit(url)
        hosted = re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co/storage/v1", url)
        local = (
            parsed.hostname == "127.0.0.1"
            and re.fullmatch(r"http://127\.0\.0\.1:[0-9]+(?:/storage/v1)?", url)
            and parsed.port
        )
        if (
            not (hosted or local)
            or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", bucket)
            or not key
            or key.strip() != key
            or not key.isascii()
            or len(integrity) < 32
            or integrity == key
            or "replace_with_" in integrity
        ):
            raise ValueError("Invalid storage configuration")
        hours = int(config.get("UPLOAD_RETENTION_HOURS", "24"))
        quota = int(config.get("UPLOAD_ORG_QUOTA_BYTES", str(128 * 1024**2)))
        if not 1 <= hours <= 8760 or quota < 1:
            raise ValueError("Invalid retention or quota")
        return cls(url, bucket, key, integrity.encode(), hours, quota)

    @property
    def namespace(self):
        return sha256(f"{self.url}/{self.bucket}".encode()).hexdigest()

    def checksum(self, org: UUID, source: UUID):
        return hmac.new(
            self.integrity_key,
            b"datasleuth/document/v1\x00" + org.bytes + source.bytes,
            "sha256",
        )

    @contextmanager
    def client(self):
        headers = {"apikey": self.key, "Accept-Encoding": "identity"}
        if not self.key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {self.key}"
        try:
            with httpx.Client(
                base_url=self.url + "/",
                headers=headers,
                trust_env=False,
                follow_redirects=False,
                timeout=5,
            ) as client:
                yield client
        except httpx.HTTPError:
            raise StorageUnavailable from None

    def check_private(self, client):
        deadline = monotonic() + 5
        with client.stream("GET", f"bucket/{self.bucket}") as response:
            if response.status_code != 200:
                raise StorageUnavailable
            metadata = bytearray()
            for chunk in response.iter_raw():
                metadata.extend(chunk)
                if monotonic() >= deadline or len(metadata) > 16_384:
                    raise StorageUnavailable
        try:
            info = json.loads(metadata)
        except (ValueError, RecursionError):
            raise StorageUnavailable from None
        if (
            not isinstance(info, dict)
            or info.get("id") != self.bucket
            or info.get("public") is not False
        ):
            raise StorageUnavailable

    def upload(
        self, org: UUID, source: UUID, extension: str, size: int, handle: BinaryIO
    ):
        deadline = monotonic() + TRANSFER_SECONDS

        def chunks():
            while chunk := handle.read(CHUNK):
                if monotonic() >= deadline:
                    raise StorageUnavailable
                yield chunk

        with self.client() as client:
            self.check_private(client)
            with client.stream(
                "POST",
                f"object/{self.bucket}/{org}/{source}",
                content=chunks(),
                headers={
                    "Content-Length": str(size),
                    "Content-Type": MEDIA_TYPES[extension],
                    "x-upsert": "false",
                    "Cache-Control": "no-store",
                },
            ) as response:
                if response.status_code not in (200, 201):
                    raise StorageUnavailable

    @contextmanager
    def open_verified(
        self, org: UUID, source: UUID, size: int, digest: str, limit: int
    ):
        if size > limit:
            raise ReadFailure("too_large")
        deadline = monotonic() + TRANSFER_SECONDS
        with TemporaryFile() as scratch:
            checksum = self.checksum(org, source)
            count = 0
            with self.client() as client:
                self.check_private(client)
                with client.stream(
                    "GET", f"object/authenticated/{self.bucket}/{org}/{source}"
                ) as response:
                    if response.status_code != 200:
                        raise StorageUnavailable
                    for chunk in response.iter_raw():
                        if monotonic() >= deadline:
                            raise StorageUnavailable
                        count += len(chunk)
                        if count > size:
                            raise ReadFailure("changed")
                        checksum.update(chunk)
                        scratch.write(chunk)
            if count != size or not hmac.compare_digest(checksum.hexdigest(), digest):
                raise ReadFailure("changed")
            scratch.seek(0)
            yield scratch

    def delete(self, org: UUID, source: UUID):
        with self.client() as client:
            with client.stream(
                "DELETE",
                f"object/{self.bucket}",
                json={"prefixes": [f"{org}/{source}"]},
            ) as response:
                if response.status_code != 200:
                    raise StorageUnavailable
