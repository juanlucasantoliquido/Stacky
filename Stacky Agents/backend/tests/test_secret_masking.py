"""Tests de services.secret_masking — Plan 195 (módulo de masking común de la serie
DevOps 186-193). Contenido CONGELADO en el roadmap §6.

Cubre: masking de valores prefijo-de-token (>=8 chars), no-masking de tokens cortos,
strip de claves por sufijo y por literal, recursividad, y pureza del módulo.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.secret_masking import (  # noqa: E402
    MASK_PLACEHOLDER,
    mask_token_values,
    strip_secret_keys,
)


def test_mask_prefijo():
    # Literal PARTIDO para esquivar el push-protection de GitHub (gotcha conocido).
    token = "ghp_" + "x" * 20
    out = mask_token_values(f"deploy con {token} adentro")
    assert MASK_PLACEHOLDER in out
    assert token not in out


def test_mask_corto_no():
    # Prefijo + 3 chars (<8) → NO matchea → texto intacto.
    short = "ghp_" + "abc"
    out = mask_token_values(f"valor {short} corto")
    assert MASK_PLACEHOLDER not in out
    assert short in out


def test_strip_por_sufijo_y_literal():
    got = strip_secret_keys({"deploy_token": "a", "password": "b", "host": "c"})
    assert got == {"deploy_token": "<omitido>", "password": "<omitido>", "host": "c"}


def test_strip_recursivo():
    got = strip_secret_keys(
        {"targets": [{"api_key": "x", "name": "ok"}], "meta": {"secret": "z", "kind": "web"}}
    )
    assert got == {
        "targets": [{"api_key": "<omitido>", "name": "ok"}],
        "meta": {"secret": "<omitido>", "kind": "web"},
    }


def test_puro():
    import services.secret_masking as sm

    source = Path(sm.__file__).read_text(encoding="utf-8")
    assert "import requests" not in source
    assert "from services" not in source
