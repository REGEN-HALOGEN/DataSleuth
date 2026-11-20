"""Path policy and traversal checks with synthetic fixture files."""

import os

import pytest

from app.scanners.discovery import SourcePathError, approved_directory, discover


def test_requires_an_explicit_approved_root(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    other = tmp_path / "approved-other"
    other.mkdir()
    for requested, roots in [
        (root, ()),
        (other, (root,)),
        (root / ".." / "approved", (root,)),
        ("approved", (root,)),
        (root / "missing", (root,)),
    ]:
        with pytest.raises(SourcePathError, match="approved scan root"):
            approved_directory(str(requested), roots)
    assert approved_directory(str(root), (root,)) == root


@pytest.mark.skipif(
    os.scandir not in os.supports_fd, reason="descriptor-based WSL/Linux inventory"
)
def test_discovery_skips_symlinks_and_bounds_depth_count_and_size(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("synthetic fixture")
    (root / "linked-directory").symlink_to(outside, target_is_directory=True)
    (root / "linked-file.txt").symlink_to(outside / "private.txt")
    (root / "alpha.CSV").write_text("a,b")
    (root / "unsupported.bin").write_bytes(b"x")
    (root / "large.txt").write_bytes(b"12345")
    nested = root / "one" / "two"
    nested.mkdir(parents=True)
    (nested / "hidden.txt").write_text("x")
    with pytest.raises(SourcePathError):
        approved_directory(str(root / "linked-directory"), (root,))

    limits = {"max_depth": 1, "max_entries": 30, "max_file_size": 4}
    result = discover(str(root), (root,), **limits)
    assert not result.entry_limit_reached
    assert {e.relative_path.as_posix(): e.status for e in result.entries} == {
        "alpha.CSV": "eligible",
        "large.txt": "too_large",
        "unsupported.bin": "unsupported",
        "linked-directory": "skipped_special",
        "linked-file.txt": "skipped_special",
        "one/two": "depth_limit",
    }
    assert (outside / "private.txt").read_text() == "synthetic fixture"
    result = discover(str(root), (root,), **(limits | {"max_entries": 1}))
    assert result.entry_limit_reached
    assert len(result.entries) <= 1


@pytest.mark.skipif(
    os.scandir not in os.supports_fd, reason="descriptor-based WSL/Linux inventory"
)
def test_enumeration_rejects_symlink_swap_after_validation(tmp_path, monkeypatch):
    from app.scanners import discovery

    source = tmp_path / "approved"
    source.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("synthetic fixture")
    validate = discovery.approved_directory

    def swap(path, roots):
        validated = validate(path, roots)
        source.rename(tmp_path / "original")
        source.symlink_to(outside, target_is_directory=True)
        return validated

    monkeypatch.setattr(discovery, "approved_directory", swap)
    with pytest.raises(SourcePathError, match="could not be inventoried safely"):
        discover(str(source), (source,), max_depth=3, max_entries=10, max_file_size=100)
    with pytest.raises(SourcePathError, match="approved scan root"):
        validate(str(outside), (source,))
