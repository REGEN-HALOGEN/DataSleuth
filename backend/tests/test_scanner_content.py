"""Read-only document extraction and privacy checks using synthetic data."""

import os
from pathlib import Path
import subprocess
from zipfile import ZipFile

import openpyxl
import pymupdf
import pytest

from app.scanners.detection import detect
from app.scanners.readers import ReadFailure, extract_text

WSL_ONLY = pytest.mark.skipif(
    os.open not in os.supports_dir_fd, reason="WSL/Linux reader"
)
SYNTHETIC_EMAIL = "fixture-person@example.invalid"
KEY = b"synthetic-key-for-detector-tests"


@pytest.mark.parametrize(
    ("text", "category"),
    [
        (SYNTHETIC_EMAIL, "email"),
        ("+91 98765 43210", "phone_in"),
        ("ABCPD1234Z", "pan"),
        ("Aadhaar: 2345 6789 1234", "aadhaar"),
        ("TEST0123456", "ifsc"),
        ("Bank account: 012345678912", "bank_account"),
    ],
)
def test_detector_outputs_only_masked_evidence_and_keyed_digest(text, category):
    finding = next(item for item in detect(text, KEY) if item.category == category)
    assert finding.masked_evidence == "[redacted]"
    assert text not in repr(finding)
    assert 0 < finding.confidence <= 1
    rotated = next(
        item
        for item in detect(text, b"another fixture key")
        if item.category == category
    )
    assert rotated.fingerprint != finding.fingerprint


def test_detector_context_boundaries_and_normalization():
    assert not detect("2345 6789 1234 and Aadhaar: 2222 2222 2222", KEY)
    assert not detect("mail@domain and ABCXD1234Z and 12345 43210", KEY)
    assert detect(SYNTHETIC_EMAIL, KEY) == detect(SYNTHETIC_EMAIL.upper(), KEY)
    assert detect("9876543210", KEY) == detect("+91 98765 43210", KEY)


def synthetic_files(root):
    (root / "input.txt").write_text(SYNTHETIC_EMAIL)
    (root / "input.log").write_text(SYNTHETIC_EMAIL)
    (root / "input.csv").write_text(f"email,name\n{SYNTHETIC_EMAIL},fixture\n")
    (root / "input.json").write_text(
        r'{"email": "fixture-person\u0040example.invalid"}'
    )
    with pymupdf.open() as document:
        document.new_page().insert_text((72, 72), SYNTHETIC_EMAIL)
        document.save(root / "input.pdf")
        document.save(
            root / "encrypted.pdf",
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="synthetic-owner-passphrase",
            user_pw="synthetic-user-passphrase",
        )
    workbook = openpyxl.Workbook()
    workbook.active.append(
        [SYNTHETIC_EMAIL, '=HYPERLINK("https://example.invalid","formula")']
    )
    workbook.save(root / "input.xlsx")
    workbook.close()
    with (
        ZipFile(root / "input.xlsx") as source,
        ZipFile(root / "input.xlsm", "w") as target,
    ):
        for member in source.infolist():
            data = source.read(member)
            if member.filename == "[Content_Types].xml":
                data = data.replace(
                    b"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
                    b"application/vnd.ms-excel.sheet.macroEnabled.main+xml",
                )
            target.writestr(member.filename, data)
        target.writestr("xl/vbaProject.bin", b"synthetic macro marker")


def extract(root, name, **overrides):
    limits = {"max_file_size": 1_000_000, "timeout": 10} | overrides
    return extract_text(str(root), (root,), Path(name), **limits)


@WSL_ONLY
def test_supported_readers_and_encrypted_pdf(tmp_path):
    synthetic_files(tmp_path)
    for suffix in ("txt", "log", "csv", "json", "pdf", "xlsx", "xlsm"):
        text = extract(tmp_path, f"input.{suffix}")
        assert SYNTHETIC_EMAIL in text
        assert "HYPERLINK" not in text
        assert "synthetic macro marker" not in text
    with pytest.raises(ReadFailure, match="encrypted"):
        extract(tmp_path, "encrypted.pdf")


@WSL_ONLY
def test_limits_malformed_inputs_and_link_rejection(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside synthetic fixture")
    (source / "symlink.txt").symlink_to(outside)
    os.link(outside, source / "hardlink.txt")
    (source / "large.txt").write_bytes(b"a" * 5)
    (source / "expanded.txt").write_bytes(b"a" * 1_000_001)
    (source / "bad.json").write_text("{invalid")
    (source / "bad.csv").write_text('"unclosed')
    for path, reason, overrides in (
        ("../outside.txt", "invalid_path", {}),
        ("symlink.txt", "skipped_special", {}),
        ("hardlink.txt", "skipped_special", {}),
        ("large.txt", "too_large", {"max_file_size": 4}),
        ("expanded.txt", "parser_limit", {"max_file_size": 2_000_000}),
        ("bad.json", "malformed", {}),
        ("bad.csv", "malformed", {}),
    ):
        with pytest.raises(ReadFailure, match=reason):
            extract(source, path, **overrides)
    assert outside.read_text() == "outside synthetic fixture"

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            "parser", 1, stderr=b"synthetic sensitive input"
        )

    monkeypatch.setattr(subprocess, "run", timeout)
    with pytest.raises(ReadFailure, match="^timeout$"):
        extract(source, "large.txt")
