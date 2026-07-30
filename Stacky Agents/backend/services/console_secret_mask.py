"""Plan 265 F4.5 — Enmascarado de secretos ANTES de que un diff salga del
proceso (KPI-6). Puro, sin IO.

Detecta por FORMA, no por nombre de archivo: valores a la derecha de una clave
cuyo nombre sugiere secreto (password, pwd, secret, token, apikey, pat,
connectionstring), y cadenas largas de alta entropia con prefijos conocidos de
proveedores reales (GitHub, GitLab, AWS, Slack, OpenAI-style). Reemplaza
SIEMPRE por el mismo marcador fijo. NUNCA lanza. Idempotente.
"""
from __future__ import annotations

import re

_MASK = "***MASKED***"

# Clave conocida = sugiere secreto, seguida de separador (":" o "=", con o sin
# comillas) y un valor sin espacios/`;`/comillas. Cubre tambien las cadenas de
# conexion completas (solo la porcion Password=/Pwd= queda enmascarada; el
# resto de la cadena de conexion permanece legible).
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|pwd|secret|token|api[_-]?key|pat|connectionstring|"
    r"conn(?:ection)?[_-]?str(?:ing)?)\b(\s*[:=]\s*)(\"?)([^\s;\"']+)(\"?)"
)

# Prefijos conocidos de tokens reales de alta entropia (GitHub, GitLab, AWS,
# Slack, estilo OpenAI). Lista deliberadamente chica: mejor enmascarar de mas
# en estos formatos inconfundibles que arriesgar falsos positivos en prosa.
_KNOWN_PREFIX_RE = re.compile(
    r"\b("
    r"ghp_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|glpat-[A-Za-z0-9_-]{20,}"
    r"|sk-[A-Za-z0-9]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r")\b"
)


def mask_secrets(text: str) -> tuple[str, int]:
    """Reemplaza secretos por un marcador. Devuelve (texto_enmascarado, cantidad).

    Detecta por FORMA, no por nombre de archivo (un secreto en un .cs tambien
    es un secreto): cadenas largas de alta entropia con prefijos conocidos,
    valores a la derecha de una clave cuyo nombre sugiere secreto (password,
    pwd, secret, token, apikey, pat, connectionstring), y cadenas de conexion
    completas. Reemplaza SIEMPRE por el mismo marcador fijo. NUNCA lanza.
    Idempotente: mask_secrets(mask_secrets(x)[0]) == mask_secrets(x)[0].
    """
    if not text:
        return (text, 0)

    count = 0

    def _kv_sub(m: re.Match) -> str:
        nonlocal count
        count += 1
        return f"{m.group(1)}{m.group(2)}{m.group(3)}{_MASK}{m.group(5)}"

    masked = _KEY_VALUE_RE.sub(_kv_sub, text)

    def _prefix_sub(_m: re.Match) -> str:
        nonlocal count
        count += 1
        return _MASK

    masked = _KNOWN_PREFIX_RE.sub(_prefix_sub, masked)

    return masked, count
