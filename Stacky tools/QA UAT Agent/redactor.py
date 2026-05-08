"""
redactor.py — Redacción de secretos para QA UAT Agent.

Garantiza que NINGÚN secreto aparezca en texto claro en logs, eventos,
artifacts, stdout, stderr, headers HTTP ni transcripts de PowerShell.

Estrategia:
  - Patrones de clave sensible (password, token, pat, secret, etc.).
  - Variables de entorno conocidas (AGENDA_WEB_PASS, ADO_PAT, etc.).
  - Redacción in-place en strings (regex) y en dicts (recursivo).
  - Redacción de headers HTTP.
  - Hash prefix para passwords (primeros 8 hex del sha256) sin exponer el valor.

Regla absoluta:
  Ningún módulo de QA UAT Agent debe loguear secretos directamente.
  Todo texto que pueda contener secretos debe pasar por redact_text() o redact_dict().
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

# ── Patrones de clave sensible ─────────────────────────────────────────────────

# Campos cuyo VALUE debe redactarse (case-insensitive key matching)
_SENSITIVE_KEY_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(password|passwd|pass|pwd)\b", re.IGNORECASE),
    re.compile(r"\b(token|pat|secret|apikey|api_key)\b", re.IGNORECASE),
    re.compile(r"\b(authorization|auth)\b", re.IGNORECASE),
    re.compile(r"\b(cookie|set.cookie)\b", re.IGNORECASE),
    re.compile(r"\b(AGENDA_WEB_PASS|RS_QA_DB_PASS|ADO_PAT)\b"),
    re.compile(r"\b(credential|cred|private.key|privatekey)\b", re.IGNORECASE),
]

# Regex que busca pares KEY=VALUE o KEY: VALUE en texto libre
_KV_PATTERNS: list[re.Pattern] = [
    # KEY=VALUE  (env var style)
    re.compile(
        r'((?:password|passwd|pass|pwd|token|pat|secret|apikey|api_key|'
        r'authorization|auth|cookie|set.cookie|AGENDA_WEB_PASS|RS_QA_DB_PASS|ADO_PAT|'
        r'credential|cred|private.?key)\s*[=:]\s*)([^\s\'"&;|,\]}\n]+)',
        re.IGNORECASE,
    ),
    # "password": "value"  or  'password': 'value'  (JSON style)
    re.compile(
        r"""(["'](?:password|passwd|pass|pwd|token|pat|secret|apikey|api_key|"""
        r"""authorization|auth|cookie|credential|cred|private.?key)["']\s*:\s*)"""
        r"""(["'][^"']*["'])""",
        re.IGNORECASE,
    ),
    # Authorization: Bearer <token>
    re.compile(
        r"(Authorization:\s*(?:Bearer|Basic|Token|PAT)\s+)([^\s\n]+)",
        re.IGNORECASE,
    ),
]

_REDACTED_PLACEHOLDER = "***REDACTED***"

# ── Redacción de texto libre ───────────────────────────────────────────────────

def redact_text(text: str) -> tuple[str, list[str]]:
    """
    Redactar secretos en texto libre (stdout, stderr, logs, etc.).

    Devuelve (texto_redactado, lista_de_campos_redactados).
    """
    if not text:
        return text, []

    redacted_fields: list[str] = []
    result = text

    for pattern in _KV_PATTERNS:
        def _replace(m: re.Match) -> str:  # noqa: E731
            key_part = m.group(1)
            redacted_fields.append(key_part.strip().rstrip("=:").strip("\"'").lower())
            return f"{key_part}{_REDACTED_PLACEHOLDER}"
        result = pattern.sub(_replace, result)

    return result, sorted(set(redacted_fields))


def is_sensitive_key(key: str) -> bool:
    """Determinar si una clave de dict o variable de entorno es sensible."""
    for p in _SENSITIVE_KEY_PATTERNS:
        if p.search(key):
            return True
    return False


# ── Redacción de dicts (recursiva) ─────────────────────────────────────────────

def redact_dict(obj: Any, _depth: int = 0) -> tuple[Any, list[str], bool]:
    """
    Redactar secretos en un objeto (dict, list, str, etc.) recursivamente.

    Devuelve (objeto_redactado, campos_redactados, redaction_applied).
    Seguro ante ciclos (profundidad máx 20).
    """
    if _depth > 20:
        return obj, [], False

    redacted_fields: list[str] = []
    applied = False

    if isinstance(obj, dict):
        new_dict = {}
        for k, v in obj.items():
            if isinstance(k, str) and is_sensitive_key(k):
                new_dict[k] = _redact_value(v)
                redacted_fields.append(k)
                applied = True
            else:
                new_v, sub_fields, sub_applied = redact_dict(v, _depth + 1)
                new_dict[k] = new_v
                redacted_fields.extend(sub_fields)
                if sub_applied:
                    applied = True
        return new_dict, sorted(set(redacted_fields)), applied

    elif isinstance(obj, list):
        new_list = []
        for item in obj:
            new_item, sub_fields, sub_applied = redact_dict(item, _depth + 1)
            new_list.append(new_item)
            redacted_fields.extend(sub_fields)
            if sub_applied:
                applied = True
        return new_list, sorted(set(redacted_fields)), applied

    elif isinstance(obj, str):
        new_text, sub_fields = redact_text(obj)
        if sub_fields:
            applied = True
            redacted_fields.extend(sub_fields)
        return new_text, sorted(set(redacted_fields)), applied

    return obj, [], False


def _redact_value(value: Any) -> str:
    """
    Redactar el valor de un campo sensible.

    Para strings, guarda hash prefix (8 hex). Para otros tipos, solo placeholder.
    """
    if isinstance(value, str) and value:
        h = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return _REDACTED_PLACEHOLDER
    return _REDACTED_PLACEHOLDER


def password_hash_prefix(password: str) -> str:
    """Devuelve los primeros 8 hex del sha256 de la password (para auditoría)."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()[:8]


def build_password_redaction_record(password: str) -> dict:
    """
    Construir registro de auditoría para un password sin exponer el valor.

    Ejemplo:
      {
        "password_present": true,
        "password_hash_prefix": "a1b2c3d4",
        "redacted": true
      }
    """
    return {
        "password_present": bool(password),
        "password_hash_prefix": password_hash_prefix(password) if password else None,
        "redacted": True,
    }


# ── Redacción de headers HTTP ──────────────────────────────────────────────────

_SENSITIVE_HEADER_NAMES = frozenset({
    "authorization",
    "cookie",
    "set-cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
    "x-access-token",
})


def redact_headers(headers: dict) -> tuple[dict, list[str]]:
    """Redactar headers HTTP sensibles. Devuelve (headers_redactados, campos_redactados)."""
    redacted: dict = {}
    fields: list[str] = []
    for k, v in headers.items():
        if k.lower() in _SENSITIVE_HEADER_NAMES:
            redacted[k] = _REDACTED_PLACEHOLDER
            fields.append(k.lower())
        else:
            redacted[k] = v
    return redacted, fields


# ── Redacción de env vars ──────────────────────────────────────────────────────

def redact_env(env: dict) -> tuple[dict, list[str]]:
    """
    Redactar variables de entorno sensibles para logging.

    Devuelve (env_redactado, lista_de_vars_redactadas).
    """
    redacted: dict = {}
    fields: list[str] = []
    for k, v in env.items():
        if is_sensitive_key(k):
            redacted[k] = _REDACTED_PLACEHOLDER
            fields.append(k)
        else:
            redacted[k] = v
    return redacted, sorted(fields)


# ── Verificación post-redacción ────────────────────────────────────────────────

# Tokens de alta entropía mínima para detectar posibles secretos sin redactar
_MIN_ENTROPY_LEN = 20  # chars
_HIGH_ENTROPY_CHARS = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")

def scan_for_unredacted_secrets(text: str) -> list[str]:
    """
    Escanear texto por posibles secretos sin redactar.

    Devuelve lista de advertencias (no los valores en sí).
    Heurístico básico — no perfecto, pero actúa como red de seguridad.
    """
    result_warnings: list[str] = []

    # Buscar patrones KEY=valor aún presente
    for p in _KV_PATTERNS:
        for m in p.finditer(text):
            key = m.group(1).strip().rstrip("=:").strip("\"'").lower()
            val = m.group(2)
            # Normalizar: quitar comillas y escapes JSON (\n, \t, etc.) del valor capturado
            val_clean = val.strip("\"'").replace("\\n", "").replace("\\t", "").strip()
            # Ignorar si ya está redactado, o es un valor vacío / no-secreto
            if _REDACTED_PLACEHOLDER in val_clean:
                continue
            if val_clean in ("", "null", "none", "true", "false", "undefined"):
                continue
            # Ignorar valores muy cortos (< 4 chars) — no son secretos reales
            if len(val_clean) < 4:
                continue
            result_warnings.append(f"posible secreto sin redactar en clave: {key!r}")

    return result_warnings
