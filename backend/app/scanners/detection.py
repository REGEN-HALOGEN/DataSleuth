"""Deterministic potential-match detectors and versioned keyed correlation."""

from dataclasses import dataclass
from hashlib import sha256
from hmac import digest
import re

DETECTORS = (
    (
        "email",
        re.compile(
            r"(?<![\w.+-])[\w.+-]{1,64}@[a-z0-9-]{1,63}(?:\.[a-z0-9-]{1,63}){0,12}\.[a-z]{2,63}(?![\w-])",
            re.I | re.ASCII,
        ),
        90,
    ),
    (
        "phone_in",
        re.compile(r"(?<![\d+])(?:\+91[ -]?)?[6-9]\d{4}[ -]?\d{5}(?!\d)", re.ASCII),
        75,
    ),
    (
        "pan",
        re.compile(
            r"(?<![A-Z0-9])[A-Z]{3}[ABCFGHLJPT][A-Z]\d{4}[A-Z](?![A-Z0-9])",
            re.I | re.ASCII,
        ),
        85,
    ),
    (
        "aadhaar",
        re.compile(
            r"\b(?:aadhaar|aadhar|uidai)\b[ \t:#-]{0,12}([2-9]\d{3}[ -]?\d{4}[ -]?\d{4})(?!\d)",
            re.I | re.ASCII,
        ),
        70,
    ),
    (
        "ifsc",
        re.compile(r"(?<![A-Z0-9])[A-Z]{4}0[A-Z0-9]{6}(?![A-Z0-9])", re.I | re.ASCII),
        75,
    ),
    (
        "bank_account",
        re.compile(
            r"\b(?:bank account|account (?:no\.?|number)|a/c no\.?)\b[ \t.:#-]{0,12}(\d{9,18})(?!\d)",
            re.I | re.ASCII,
        ),
        65,
    ),
)
FINDING_LIMIT = 1000


@dataclass(frozen=True)
class Candidate:
    category: str
    detector_version: int
    confidence: float
    location: int
    masked_evidence: str
    fingerprint: str


class DetectionLimit(ValueError):
    pass


def detect(text: str, key: bytes) -> list[Candidate]:
    findings = []
    for location, line in enumerate(text.splitlines(), start=1):
        for category, pattern, confidence in DETECTORS:
            for match in pattern.finditer(line):
                value = match.group(1) if match.lastindex else match.group()
                if category in {"phone_in", "aadhaar", "bank_account"}:
                    value = "".join(
                        character
                        for character in value
                        if character.isascii() and character.isdecimal()
                    )
                    if category == "phone_in":
                        value = "91" + value[-10:]
                    if len(set(value)) == 1:
                        continue
                else:
                    value = value.lower()
                if len(findings) >= FINDING_LIMIT:
                    raise DetectionLimit
                fingerprint = digest(
                    key, f"{category}\0{value}".encode("utf-8"), sha256
                ).hex()
                findings.append(
                    Candidate(
                        category,
                        1,
                        confidence / 100,
                        location,
                        "[redacted]",
                        fingerprint,
                    )
                )
    return findings
