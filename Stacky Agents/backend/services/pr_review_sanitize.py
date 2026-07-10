"""pr_review_sanitize.py — Plan 110. Saneo de diffs antes de mandarlos a un modelo
(secretos técnicos + PII básica: email, C1).
PURO: sin flask, sin IO, sin config. Determinístico y testeable."""
from __future__ import annotations
import re

_TRUNCATION_MARKER = "\n\n[... diff truncado por tamaño; ver la PR completa en el tracker ...]"

_SECRET_PATTERNS = [
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                 # AWS access key id
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),             # GitHub PAT
    re.compile(r"\bglpat-[A-Za-z0-9\-_]{20,}\b"),        # GitLab PAT
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"),    # Slack token
    re.compile(r"(?i)(password\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(secret\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)\S+"),
    # user:pass@host — group1 = prefijo "://user:" a CONSERVAR; la contraseña
    # (fuera del grupo, seguida de @ vía lookahead) se enmascara sin leak.
    re.compile(r"(://[^:@/\s]+:)[^@/\s]+(?=@)"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),  # PII: email (C1)
]
_MASK = "***REDACTED***"


def redact_secrets(text: str) -> str:
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        if pat.groups >= 1:
            out = pat.sub(lambda m: m.group(1) + _MASK, out)
        else:
            out = pat.sub(_MASK, out)
    return out


def truncate(text: str, max_chars: int) -> tuple[str, bool]:
    if text is None:
        return "", False
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[:max_chars] + _TRUNCATION_MARKER, True


def sanitize_diff(text: str, max_chars: int) -> tuple[str, bool]:
    """Redacta secretos y luego trunca. Retorna (texto_saneado, truncated)."""
    return truncate(redact_secrets(text or ""), max_chars)
