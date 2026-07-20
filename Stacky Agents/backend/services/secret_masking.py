"""services/secret_masking.py — Plan 195 (serie DevOps 186-193). Masking canónico.

Única fuente de: prefijos de token conocidos, placeholder, sufijos de clave secreta.
Consumidores: 186 (PL012b), 188 (evidencia), 190 (notes export), 193 (logs CI).
PURO: sin red, sin config, sin imports de servicios.
"""
from __future__ import annotations

import re

TOKEN_VALUE_PREFIXES = ("ghp_", "github_pat_", "glpat-", "xoxb-", "xoxp-", "AKIA", "eyJhbGciOi")
MASK_PLACEHOLDER = "<posible-secreto-omitido>"
SECRET_KEY_SUFFIXES = ("_token", "_pat", "_password", "_secret", "_key", "_apikey")

_TOKEN_RE = re.compile(
    "(" + "|".join(re.escape(p) for p in TOKEN_VALUE_PREFIXES) + r")[A-Za-z0-9_./+-]{8,}"
)


def mask_token_values(text: str) -> str:
    """Reemplaza por MASK_PLACEHOLDER toda substring prefijo-de-token + >=8 chars del set."""
    return _TOKEN_RE.sub(MASK_PLACEHOLDER, text or "")


def strip_secret_keys(obj):
    """Copia profunda de dict/list; claves cuyo lower() termina en SECRET_KEY_SUFFIXES o está
    en {"pat","token","password","secret","auth_header","api_key"} → "<omitido>"."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if kl in {"pat", "token", "password", "secret", "auth_header", "api_key"} or \
               kl.endswith(SECRET_KEY_SUFFIXES):
                out[k] = "<omitido>"
            else:
                out[k] = strip_secret_keys(v)
        return out
    if isinstance(obj, list):
        return [strip_secret_keys(x) for x in obj]
    return obj
