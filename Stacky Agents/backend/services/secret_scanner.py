"""Shared secret scanner for generated artifacts and memory validation."""
from __future__ import annotations

import re
from dataclasses import dataclass


SECRET_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"ghp_[A-Za-z0-9]{30,}", re.IGNORECASE),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}", re.IGNORECASE),
    re.compile(r"AIza[0-9A-Za-z\-_]{30,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"Authorization:\s*Basic\s+[A-Za-z0-9+/=]{20,}", re.IGNORECASE),
    re.compile(r"\bADO_PAT\s*[=:]\s*\S+", re.IGNORECASE),
)


@dataclass(frozen=True)
class SecretMatch:
    pattern: str
    start: int
    end: int

    def to_dict(self) -> dict:
        return {"pattern": self.pattern, "start": self.start, "end": self.end}


def find_secret(text: str | None) -> SecretMatch | None:
    payload = text or ""
    for pattern in SECRET_PATTERNS:
        match = pattern.search(payload)
        if match:
            return SecretMatch(pattern=pattern.pattern, start=match.start(), end=match.end())
    return None


def scan_secrets(text: str | None) -> str | None:
    """Return the matching regex pattern, or None when the text is clean."""
    match = find_secret(text)
    return match.pattern if match else None
