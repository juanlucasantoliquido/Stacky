"""services/ci_log_view.py — Plan 193. Tail acotado + masking de logs CI. PURO.

Reusa el masking canónico de services.secret_masking (Plan 195): NO redefine la
lista de prefijos de token (un solo TOKEN_VALUE_PREFIXES en la casa). Sin red, sin
config, sin imports de proveedores.
"""
from __future__ import annotations

from services.secret_masking import mask_token_values

MAX_LOG_CHARS = 200_000


def tail_and_mask(text: str, max_chars: int = MAX_LOG_CHARS) -> dict:
    """ORDEN OBLIGATORIO (KPI-2): (1) mask sobre el texto COMPLETO — así un token que
    quedaría partido justo en el borde del tail no escapa; (2) tail de los últimos
    max_chars.

    Devuelve {"log": str, "truncated": bool, "chars_total": int} donde chars_total es
    el largo del texto ORIGINAL (pre-mask, pre-tail). C3 — semántica CONGELADA e
    intencional: chars_total pre-mask, truncated post-mask; NO "corregir" esta
    asimetría.
    """
    total = len(text or "")
    masked = mask_token_values(text or "")
    truncated = len(masked) > max_chars
    return {
        "log": masked[-max_chars:] if truncated else masked,
        "truncated": truncated,
        "chars_total": total,
    }
