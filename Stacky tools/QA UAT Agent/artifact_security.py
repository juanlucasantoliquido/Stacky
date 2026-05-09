"""
artifact_security.py — PII masking, secrets redaction, and prompt injection detection.

Protects artifacts and prompts from leaking PII, secrets, and being vulnerable
to prompt injection attacks from external content (tickets, comments, HTML, logs).

Usage:
    from artifact_security import mask_pii, redact_secrets, detect_prompt_injection

    clean_text, pii_items = mask_pii(ticket_description)
    clean_data, secrets_found = redact_secrets(payload_dict)
    result = detect_prompt_injection(html_content, source="page_html")

All functions are pure / side-effect-free. Logging is always done by the caller.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Union

_logger = logging.getLogger("stacky.qa_uat.artifact_security")

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class PromptInjectionResult:
    risk: str                   # "none" | "low" | "medium" | "high"
    patterns: list[str]         # patterns detected
    source: str                 # origin of the analyzed text
    decision: str               # "allow" | "sanitize_and_continue" | "block"
    sanitized_text: str | None  # sanitized text when decision != "allow"


# ── PII detection ─────────────────────────────────────────────────────────────

# Chilean RUT: 12.345.678-9 or 12345678-9 or 12345678-K
_RUT_PATTERN = re.compile(
    r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dKk]\b"
)

# Argentine / generic DNI: 8-digit numbers in common document contexts
_DNI_PATTERN = re.compile(
    r"\b(?:dni|cedula|cc|nid)[:\s#]*\d{6,10}\b",
    re.IGNORECASE,
)

# Email addresses
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# Phone numbers (international and local formats)
_PHONE_PATTERN = re.compile(
    r"\+56[\s\-]?9[\s\-]?\d{4}[\s\-]?\d{4}\b"         # Chilean mobile: +56 9 XXXX XXXX
    r"|\b(?:\+?56|0)[2-9][\s\-]?\d{4}[\s\-]?\d{4}\b"  # Chilean landline / mobile (no +)
    r"|\b(?:\+?1[\s\-]?)?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}\b"  # NANP
    r"|\b\+\d{1,3}[\s\-]\d{6,12}\b"                    # Generic intl
)

# Credit / debit card numbers (Luhn-alike groupings)
_CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"
)

# Bank account numbers in context keywords
_ACCOUNT_PATTERN = re.compile(
    r"\b(?:cuenta|account|cta|iban|bban)[:\s#]*\d{8,22}\b",
    re.IGNORECASE,
)

# Street addresses (simplified heuristic: Av/Calle/Jr + number)
_ADDRESS_PATTERN = re.compile(
    r"\b(?:av(?:enida)?|calle|jr|carrera|pasaje|blvd)\.?\s+[A-Za-z\s]{3,30}\s+\d{1,6}\b",
    re.IGNORECASE,
)

_PII_RULES: list[tuple[re.Pattern, str]] = [
    (_RUT_PATTERN,     "rut"),
    (_DNI_PATTERN,     "dni"),
    (_EMAIL_PATTERN,   "email"),
    (_PHONE_PATTERN,   "phone"),
    (_CARD_PATTERN,    "card_number"),
    (_ACCOUNT_PATTERN, "bank_account"),
    (_ADDRESS_PATTERN, "address"),
]

_MASK_TOKEN = "[REDACTED-{kind}]"


def mask_pii(text: str, policy: str = "default") -> tuple[str, list[dict]]:
    """
    Detect and mask PII in *text*.

    Returns (masked_text, findings) where findings is a list of dicts:
        {"kind": "email", "original_length": 22, "position": 45}

    The original value is never stored in findings.
    policy is reserved for future per-tenant rules; currently "default" only.
    """
    if not isinstance(text, str):
        return str(text), []

    findings: list[dict] = []
    result = text

    for pattern, kind in _PII_RULES:
        for match in reversed(list(pattern.finditer(result))):
            token = _MASK_TOKEN.format(kind=kind.upper())
            findings.append({
                "kind": kind,
                "original_length": len(match.group()),
                "position": match.start(),
            })
            result = result[: match.start()] + token + result[match.end():]

    return result, findings


# ── Secrets redaction ─────────────────────────────────────────────────────────

# Bearer / JWT tokens
_BEARER_PATTERN = re.compile(
    r"\bBearer\s+([A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+|[A-Za-z0-9+/=]{20,})\b",
    re.IGNORECASE,
)

# API keys with known prefixes
_API_KEY_PATTERN = re.compile(
    r"\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36}|glpat-[A-Za-z0-9_\-]{20,}"
    r"|AIza[A-Za-z0-9_\-]{35}|AKIA[A-Z0-9]{16}|xoxb-[A-Za-z0-9\-]{50,})\b"
)

# Passwords in query strings or JSON
_PASSWORD_QUERY_PATTERN = re.compile(
    r"(?i)(?:password|passwd|pwd|secret|token|apikey|api_key)[=:\"'\s]+([^\s&\"'<>]{6,64})"
)

# Connection strings with embedded credentials
_CONN_STRING_PATTERN = re.compile(
    r"(?i)(?:User\s+Id|uid|Password|pwd)\s*=\s*([^;\"'\s]{4,64})"
)

_SECRET_REDACT = "[SECRET-REDACTED]"

_SECRET_RULES: list[tuple[re.Pattern, str]] = [
    (_BEARER_PATTERN,        "bearer_token"),
    (_API_KEY_PATTERN,       "api_key"),
    (_PASSWORD_QUERY_PATTERN, "password_in_query"),
    (_CONN_STRING_PATTERN,   "connection_string_credential"),
]


def _redact_str(text: str) -> tuple[str, list[str]]:
    """Redact secrets from a string value. Returns (clean, list_of_found_kinds)."""
    found: list[str] = []
    result = text
    for pattern, kind in _SECRET_RULES:
        new = pattern.sub(lambda m: m.group(0).replace(m.group(1) if m.lastindex else m.group(0), _SECRET_REDACT), result)
        if new != result:
            found.append(kind)
        result = new
    return result, found


def redact_secrets(data: Union[dict, str]) -> tuple[Union[dict, str], list[str]]:
    """
    Detect and redact secrets from *data* (dict or string).

    For dicts, recursively redacts string values.
    Returns (clean_data, list_of_found_secret_kinds).
    """
    all_found: list[str] = []

    if isinstance(data, str):
        clean, found = _redact_str(data)
        return clean, found

    if isinstance(data, dict):
        clean_dict: dict = {}
        for key, value in data.items():
            if isinstance(value, str):
                clean_val, found = _redact_str(value)
                clean_dict[key] = clean_val
                all_found.extend(found)
            elif isinstance(value, dict):
                clean_val, found = redact_secrets(value)
                clean_dict[key] = clean_val
                all_found.extend(found)
            elif isinstance(value, list):
                clean_list = []
                for item in value:
                    if isinstance(item, (str, dict)):
                        clean_item, found = redact_secrets(item)
                        clean_list.append(clean_item)
                        all_found.extend(found)
                    else:
                        clean_list.append(item)
                clean_dict[key] = clean_list
            else:
                clean_dict[key] = value
        return clean_dict, all_found

    return data, []


# ── Prompt injection detection ────────────────────────────────────────────────

_INJECTION_PATTERNS_HIGH: list[tuple[str, re.Pattern]] = [
    ("ignore_previous_instructions",
     re.compile(r"ignore\s+(?:all\s+)?previous\s+instructions?", re.IGNORECASE)),
    ("ignore_all_prior",
     re.compile(r"ignore\s+all\s+prior", re.IGNORECASE)),
    ("disregard_your",
     re.compile(r"disregard\s+your\s+(?:instructions?|rules?|guidelines?)", re.IGNORECASE)),
    ("override_system_prompt",
     re.compile(r"override\s+(?:the\s+)?system\s+prompt", re.IGNORECASE)),
    ("your_new_instructions",
     re.compile(r"your\s+new\s+instructions?\s*(?:are|:)", re.IGNORECASE)),
]

_INJECTION_PATTERNS_MEDIUM: list[tuple[str, re.Pattern]] = [
    ("you_are_now",
     re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE)),
    ("act_as_if",
     re.compile(r"\bact\s+as\s+if\b", re.IGNORECASE)),
    ("pretend_you_are",
     re.compile(r"\bpretend\s+(?:you\s+are|to\s+be)\b", re.IGNORECASE)),
    ("html_comment_instruction",
     re.compile(r"<!--.*(?:ignore|disregard|pretend|you\s+are|instructions?).*-->",
                re.IGNORECASE | re.DOTALL)),
]

_INJECTION_PATTERNS_LOW: list[tuple[str, re.Pattern]] = [
    ("new_role_assignment",
     re.compile(r"\byour\s+(?:role|purpose|task)\s+is\s+now\b", re.IGNORECASE)),
    ("assistant_persona",
     re.compile(r"\bfrom\s+now\s+on\b", re.IGNORECASE)),
]

# Detect base64 or hex payloads embedded in text
_BASE64_EMBEDDED = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")
_HEX_EMBEDDED = re.compile(r"\b(?:[0-9a-fA-F]{2}\s?){20,}\b")


def _check_encoded_payload(text: str) -> list[str]:
    """Try to decode base64/hex blobs and check for injection patterns inside."""
    found: list[str] = []
    for match in _BASE64_EMBEDDED.finditer(text):
        try:
            decoded = base64.b64decode(match.group() + "==").decode("utf-8", errors="ignore")
            for name, pat in (_INJECTION_PATTERNS_HIGH + _INJECTION_PATTERNS_MEDIUM):
                if pat.search(decoded):
                    found.append(f"base64_encoded_{name}")
        except (binascii.Error, ValueError):
            pass
    return found


def detect_prompt_injection(text: str, source: str) -> PromptInjectionResult:
    """
    Detect prompt injection patterns in *text* from *source*.

    Decision logic:
        high pattern found      → "block"
        medium pattern found    → "sanitize_and_continue"
        low / encoded only      → "sanitize_and_continue"
        none found              → "allow"

    The sanitized_text strips or replaces the matched injection patterns.
    """
    if not isinstance(text, str):
        return PromptInjectionResult(
            risk="none", patterns=[], source=source,
            decision="allow", sanitized_text=None,
        )

    found_patterns: list[str] = []
    risk = "none"

    # High-risk patterns
    for name, pat in _INJECTION_PATTERNS_HIGH:
        if pat.search(text):
            found_patterns.append(name)
            risk = "high"

    # Medium-risk patterns (only escalate if not already high)
    for name, pat in _INJECTION_PATTERNS_MEDIUM:
        if pat.search(text):
            found_patterns.append(name)
            if risk == "none":
                risk = "medium"

    # Low-risk patterns
    for name, pat in _INJECTION_PATTERNS_LOW:
        if pat.search(text):
            found_patterns.append(name)
            if risk == "none":
                risk = "low"

    # Encoded payloads
    encoded_hits = _check_encoded_payload(text)
    if encoded_hits:
        found_patterns.extend(encoded_hits)
        if risk in ("none", "low"):
            risk = "medium"

    # Decision
    if risk == "high":
        decision = "block"
    elif risk in ("medium", "low"):
        decision = "sanitize_and_continue"
    else:
        decision = "allow"

    # Build sanitized text (strip injection segments)
    sanitized: str | None = None
    if decision != "allow":
        sanitized = text
        for _, pat in (_INJECTION_PATTERNS_HIGH + _INJECTION_PATTERNS_MEDIUM + _INJECTION_PATTERNS_LOW):
            sanitized = pat.sub("[INJECTION-REMOVED]", sanitized)

    return PromptInjectionResult(
        risk=risk,
        patterns=found_patterns,
        source=source,
        decision=decision,
        sanitized_text=sanitized,
    )


# ── Security check composite ──────────────────────────────────────────────────

def run_security_check(
    text: str,
    source: str,
    exec_logger=None,
    policy: str = "default",
) -> dict:
    """
    Run all three security checks on *text* from *source*.

    Emits a security_check event to exec_logger if provided.
    Returns a result dict compatible with the execution.jsonl event schema.

    Decision precedence:
      - If injection risk is "high" → block
      - If secrets found → sanitize_and_continue
      - If PII found → sanitize_and_continue
      - Otherwise → allow
    """
    _, pii_items = mask_pii(text, policy=policy)
    _, secrets_found = redact_secrets(text)
    injection_result = detect_prompt_injection(text, source=source)

    pii_found = len(pii_items) > 0
    has_secrets = len(secrets_found) > 0

    # Aggregate decision
    if injection_result.decision == "block":
        decision = "block"
    elif has_secrets or pii_found or injection_result.decision == "sanitize_and_continue":
        decision = "sanitize_and_continue"
    else:
        decision = "allow"

    event: dict = {
        "event": "security_check",
        "source": source,
        "pii_found": pii_found,
        "pii_kinds": [item["kind"] for item in pii_items],
        "secrets_found": has_secrets,
        "secret_kinds": secrets_found,
        "injection_risk": injection_result.risk,
        "injection_patterns": injection_result.patterns,
        "decision": decision,
    }

    if exec_logger is not None:
        try:
            exec_logger.event("security_check", event)
        except Exception:  # noqa: BLE001
            pass

    return event
