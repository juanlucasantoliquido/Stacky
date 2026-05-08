"""
FA-33 — Cost preview pre-Run.

Estima costo y latencia de un Run antes de hacer click. El operador decide
informado: "este va a costar $0.42 y tardar ~12s".

Implementación: tabla de pricing por modelo (USD por 1M tokens) + estimación
de tokens del prompt. Para tokens de salida, asumimos un ratio típico por agente.
"""
from __future__ import annotations

from dataclasses import dataclass

# Precios USD por 1M tokens (fuente: Anthropic + OpenAI, snapshot abril 2026).
# Conservadores para no sub-estimar.
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5":   {"input": 1.00,  "output": 5.00},
    "claude-sonnet-4-6":  {"input": 3.00,  "output": 15.00},
    "claude-opus-4-7":    {"input": 15.00, "output": 75.00},
    "mock-1.0":           {"input": 0.00,  "output": 0.00},
    # Copilot exposes these models behind a flat subscription; the numbers
    # below are nominal OpenAI list prices (USD / 1M) used only for UI hints.
    "gpt-4o":             {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":        {"input": 0.15,  "output": 0.60},
    "o1":                 {"input": 15.00, "output": 60.00},
    "o1-mini":            {"input": 3.00,  "output": 12.00},
    "claude-3.5-sonnet":  {"input": 3.00,  "output": 15.00},
    "claude-3.7-sonnet":  {"input": 3.00,  "output": 15.00},
    "gemini-2.0-flash-001": {"input": 0.10, "output": 0.40},
}

# Ratio típico de tokens out/in observado por agente (puede actualizarse con telemetría).
OUTPUT_RATIO: dict[str, float] = {
    "business":   0.6,
    "functional": 0.45,
    "technical":  0.55,
    "developer":  0.40,
    "qa":         0.35,
}

# Latencia típica (ms) por modelo + agente — proxy grosero.
LATENCY_BASE_MS: dict[str, int] = {
    "claude-haiku-4-5":   1200,
    "claude-sonnet-4-6":  3500,
    "claude-opus-4-7":    8000,
    "mock-1.0":           1600,
    "gpt-4o":             2500,
    "gpt-4o-mini":        1200,
    "o1":                 12000,
    "o1-mini":            5000,
    "claude-3.5-sonnet":  3500,
    "claude-3.7-sonnet":  3500,
    "gemini-2.0-flash-001": 1200,
}


@dataclass
class CostEstimate:
    model: str
    tokens_in_estimated: int
    tokens_out_estimated: int
    cost_usd_in: float
    cost_usd_out: float
    cost_usd_total: float
    latency_ms_estimated: int

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "tokens_in": self.tokens_in_estimated,
            "tokens_out": self.tokens_out_estimated,
            "cost_usd_in": round(self.cost_usd_in, 4),
            "cost_usd_out": round(self.cost_usd_out, 4),
            "cost_usd_total": round(self.cost_usd_total, 4),
            "latency_ms": self.latency_ms_estimated,
        }


def _approx_tokens(text: str) -> int:
    """Aproximación: 1 token ≈ 4 caracteres (válido para ES + código)."""
    return max(1, len(text) // 4)


def _estimate_input_tokens(blocks: list[dict]) -> int:
    total = 0
    for b in blocks:
        if b.get("content"):
            total += _approx_tokens(b["content"])
        for it in b.get("items") or []:
            if it.get("selected"):
                total += _approx_tokens(it.get("label", ""))
        # Coste fijo por bloque: heading + framing
        total += 20
    # Coste fijo por system prompt + framing del agente
    total += 600
    return total


def estimate(*, agent_type: str, blocks: list[dict], model: str = "claude-sonnet-4-6") -> CostEstimate:
    pricing = PRICING.get(model, PRICING["claude-sonnet-4-6"])
    tokens_in = _estimate_input_tokens(blocks)
    ratio = OUTPUT_RATIO.get(agent_type, 0.4)
    tokens_out = int(tokens_in * ratio)

    cost_in = tokens_in * pricing["input"] / 1_000_000.0
    cost_out = tokens_out * pricing["output"] / 1_000_000.0

    latency = LATENCY_BASE_MS.get(model, 3000) + tokens_out * 4  # ~250 tok/s

    return CostEstimate(
        model=model,
        tokens_in_estimated=tokens_in,
        tokens_out_estimated=tokens_out,
        cost_usd_in=cost_in,
        cost_usd_out=cost_out,
        cost_usd_total=cost_in + cost_out,
        latency_ms_estimated=latency,
    )
