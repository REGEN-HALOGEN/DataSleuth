"""Open regular files beneath approved roots and extract text with a deadline."""

from contextlib import contextmanager
from typing import BinaryIO
import os
from pathlib import Path
import stat
import subprocess
import sys

from app.scanners.discovery import (
    SUPPORTED_EXTENSIONS,
    approved_directory,
    open_directory,
)

MAX_INPUT_BYTES = 32 * 1024**2


class ReadFailure(ValueError):
    """A fixed reason code suitable for storing with file metadata."""


@contextmanager
def open_local_input(
    configured_path: str, roots: tuple[Path, ...], relative_path: Path, limit: int
):
    if not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd:
        raise ReadFailure("platform_unsupported")
    source = approved_directory(configured_path, roots)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or ".." in relative_path.parts
    ):
        raise ReadFailure("invalid_path")
    try:
        with open_directory(source / relative_path.parent) as parent:
            original = os.stat(relative_path.name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISREG(original.st_mode) or original.st_nlink != 1:
                raise ReadFailure("skipped_special")
            descriptor = os.open(
                relative_path.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=parent,
            )
            with os.fdopen(descriptor, "rb") as handle:
                current = os.fstat(handle.fileno())
                if (
                    not stat.S_ISREG(current.st_mode)
                    or current.st_nlink != 1
                    or (original.st_dev, original.st_ino)
                    != (current.st_dev, current.st_ino)
                ):
                    raise ReadFailure("changed")
                if current.st_size > limit:
                    raise ReadFailure("too_large")
                try:
                    yield handle
                finally:
                    final = os.fstat(handle.fileno())
                    if (final.st_size, final.st_mtime_ns, final.st_ctime_ns) != (
                        current.st_size,
                        current.st_mtime_ns,
                        current.st_ctime_ns,
                    ):
                        raise ReadFailure("changed")
    except OSError:
        raise ReadFailure("unreadable") from None


def extract_text(
    configured_path: str,
    roots: tuple[Path, ...],
    relative_path: Path,
    *,
    max_file_size: int,
    timeout: int,
) -> str:
    limit = min(max_file_size, MAX_INPUT_BYTES)
    with open_local_input(configured_path, roots, relative_path, limit) as handle:
        return parse_input(handle, relative_path.suffix.lower(), limit, timeout)


def parse_input(
    handle: BinaryIO,
    extension: str,
    limit: int,
    timeout: int,
    *,
    validate_only: bool = False,
) -> str:
    if extension not in SUPPORTED_EXTENSIONS:
        raise ReadFailure("unsupported")
    try:
        command = [
            sys.executable,
            "-I",
            "-m",
            "app.scanners.extract",
            extension,
            str(limit),
        ]
        if validate_only:
            command.append("validate")
        result = subprocess.run(
            command,
            stdin=handle,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
            env={"OPENPYXL_DEFUSEDXML": "True"},
        )
    except subprocess.TimeoutExpired:
        raise ReadFailure("timeout") from None
    except OSError:
        raise ReadFailure("parser_unavailable") from None
    if result.returncode:
        reason = {1: "malformed", 2: "parser_limit", 3: "encrypted"}.get(
            result.returncode, "parser_failed"
        )
        raise ReadFailure(reason)
    return result.stdout.decode("utf-8")
