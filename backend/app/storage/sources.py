"""Scanner input contract; adapters hand the parser a bounded, seekable input."""

from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol
from uuid import UUID

from app.scanners.discovery import Inventory, InventoryEntry, SourcePathError, discover
from app.scanners.readers import ReadFailure, open_local_input
from app.models.source import ScanSource
from app.storage.supabase import PrivateBucket


class SourceInput(Protocol):
    def inventory(self, config: dict[str, str]) -> Inventory: ...

    def open_input(
        self, entry: InventoryEntry, limit: int
    ) -> AbstractContextManager[BinaryIO]: ...


@dataclass(frozen=True)
class LocalDirectory:
    path: str
    roots: tuple[Path, ...]

    def inventory(self, config: dict[str, str]) -> Inventory:
        return discover(
            self.path,
            self.roots,
            max_depth=int(config["MAX_SCAN_DEPTH"]),
            max_entries=int(config["MAX_FILES_PER_SCAN"]),
            max_file_size=int(config["MAX_FILE_SIZE_BYTES"]),
        )

    def open_input(self, entry: InventoryEntry, limit: int):
        return open_local_input(self.path, self.roots, entry.relative_path, limit)


@dataclass(frozen=True)
class PrivateDocument:
    bucket: PrivateBucket
    org_id: UUID
    source_id: UUID
    extension: str
    size: int
    digest: str

    @property
    def label(self):
        return Path("document" + self.extension)

    def inventory(self, config):
        state = (
            "eligible"
            if self.size <= int(config["MAX_FILE_SIZE_BYTES"])
            else "too_large"
        )
        return Inventory([InventoryEntry(self.label, self.size, state)], False)

    def open_input(self, entry, limit):
        if entry.relative_path != self.label or entry.size_bytes != self.size:
            raise ReadFailure("changed")
        return self.bucket.open_verified(
            self.org_id, self.source_id, self.size, self.digest, limit
        )


def source_input(
    source: ScanSource, roots: tuple[Path, ...], bucket: PrivateBucket | None
) -> SourceInput:
    if source.configured_path is not None:
        return LocalDirectory(source.configured_path, roots)
    if bucket is None or not source.document_ready(bucket.namespace):
        raise SourcePathError("Document is unavailable.")
    return PrivateDocument(
        bucket,
        source.organisation_id,
        source.id,
        source.extension,
        source.size_bytes,
        source.content_digest,
    )
