"""Read-only, bounded filesystem inventory."""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import stat

SUPPORTED_EXTENSIONS = frozenset(
    {".txt", ".csv", ".log", ".json", ".pdf", ".xlsx", ".xlsm"}
)


class SourcePathError(ValueError):
    """A source cannot be accessed under the current policy."""


def approved_directory(value: str, roots: tuple[Path, ...]) -> Path:
    try:
        requested = Path(value)
        if not requested.is_absolute() or ".." in requested.parts:
            raise ValueError
        # Require the stored path to identify the actual directory without aliases.
        if not any(requested.parts[: len(root.parts)] == root.parts for root in roots):
            raise ValueError
        resolved = requested.resolve(strict=True)
        if requested.parts != resolved.parts:
            raise ValueError
        if not resolved.is_dir():
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise SourcePathError(
            "Choose an existing directory inside an approved scan root."
        ) from None
    return resolved


@contextmanager
def open_directory(path: Path):
    # Descriptor-relative opens prevent a path component being swapped for a
    # symlink between validation and enumeration.
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


@dataclass(frozen=True)
class InventoryEntry:
    relative_path: Path
    size_bytes: int | None
    status: str


@dataclass(frozen=True)
class Inventory:
    entries: list[InventoryEntry]
    entry_limit_reached: bool


def discover(
    configured_path: str,
    roots: tuple[Path, ...],
    *,
    max_depth: int,
    max_entries: int,
    max_file_size: int,
) -> Inventory:
    if not hasattr(os, "O_NOFOLLOW") or os.scandir not in os.supports_fd:
        raise SourcePathError("Safe file discovery requires the WSL or Linux backend.")
    source = approved_directory(configured_path, roots)
    entries: list[InventoryEntry] = []
    examined = 0
    limited = False

    def walk(descriptor: int, prefix: Path, depth: int) -> None:
        nonlocal examined, limited
        with os.scandir(descriptor) as directory:
            for entry in directory:
                if examined >= max_entries:
                    limited = True
                    return
                examined += 1
                path = prefix / entry.name
                try:
                    metadata = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(metadata.st_mode):
                        if depth >= max_depth:
                            entries.append(InventoryEntry(path, None, "depth_limit"))
                            continue
                        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                        child = os.open(entry.name, flags, dir_fd=descriptor)
                        try:
                            walk(child, path, depth + 1)
                        finally:
                            os.close(child)
                        if limited:
                            return
                        continue
                except OSError:
                    entries.append(InventoryEntry(path, None, "unreadable"))
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    entries.append(InventoryEntry(path, None, "skipped_special"))
                elif metadata.st_size > max_file_size:
                    entries.append(InventoryEntry(path, metadata.st_size, "too_large"))
                elif path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    entries.append(
                        InventoryEntry(path, metadata.st_size, "unsupported")
                    )
                else:
                    entries.append(InventoryEntry(path, metadata.st_size, "eligible"))

    try:
        with open_directory(source) as descriptor:
            walk(descriptor, Path(), 0)
    except (OSError, RecursionError):
        raise SourcePathError(
            "The approved directory could not be inventoried safely."
        ) from None
    return Inventory(entries, limited)
