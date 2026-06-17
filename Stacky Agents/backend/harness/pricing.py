"""V0.5 — Normalización de costo multi-proveedor (pricing fallback).

PURO: no toca disco ni DB. Estima costo USD desde tokens cuando el CLI no
reporta `total_cost_usd`. Costo reportado por el CLI SIEMPRE gana (este módulo
solo se usa como fallback).

Match por prefijo de model id: el prefijo más largo que matchea gana.
Sin match o sin tokens → None (NUNCA inventar 0.0).

Override por env `STACKY_PRICING_JSON`: JSON con el mismo shape
{ "model-prefix": [input_usd_per_mtok, output_usd_per_mtok], ... }.
Malformado → log warn + tabla default (nunca crash).
"""
from __future__ import annotations

import json
import logging
import os

logger = logging.getLogger("stacky.harness.pricing")

# USD por millón de tokens (input, output). Match por prefijo de model id.
# Anthropic: catálogo oficial 2026 (sonnet-4-6 = 3/15, haiku-4-5 = 1/5).
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4": (5.0, 25.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
    "claude-fable-5": (10.0, 50.0),
    # OpenAI / codex (estimaciones; ajustar con la tabla vigente del proveedor).
    "gpt-5": (1.25, 10.0),
    "gpt-4.1": (2.0, 8.0),
    "o4": (1.1, 4.4),
    "o3": (2.0, 8.0),
}

_MTOK = 1_000_000.0


def _load_prices() -> dict[str, tuple[float, float]]:
    """Devuelve la tabla de precios efectiva (default + override por env)."""
    raw = os.getenv("STACKY_PRICING_JSON")
    if not raw:
        return DEFAULT_PRICES
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("STACKY_PRICING_JSON no es un objeto JSON")
        merged = dict(DEFAULT_PRICES)
        for k, v in parsed.items():
            if (
                isinstance(v, (list, tuple))
                and len(v) == 2
                and all(isinstance(x, (int, float)) for x in v)
            ):
                merged[str(k)] = (float(v[0]), float(v[1]))
            else:
                raise ValueError(f"precio inválido para {k!r}: {v!r}")
        return merged
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        logger.warning(
            "STACKY_PRICING_JSON malformado (%s); usando tabla default", exc
        )
        return DEFAULT_PRICES


def estimate_cost(
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    """Estima el costo USD de un run desde tokens.

    Returns None si no hay model, no hay tokens, o el modelo no matchea
    ningún prefijo conocido (nunca devuelve 0.0 por desconocimiento).
    """
    if not model:
        return None
    if input_tokens is None and output_tokens is None:
        return None

    prices = _load_prices()
    # Prefijo más largo que matchea gana (desambiguación determinista).
    match: tuple[float, float] | None = None
    match_len = -1
    for prefix, price in prices.items():
        if model.startswith(prefix) and len(prefix) > match_len:
            match = price
            match_len = len(prefix)
    if match is None:
        return None

    in_price, out_price = match
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    return round((in_tok * in_price + out_tok * out_price) / _MTOK, 6)
