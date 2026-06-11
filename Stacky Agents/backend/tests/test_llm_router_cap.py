"""F3.2 / §5.2 — Cap duro de routing de modelos.

Regla dura: simples -> claude-haiku-4-5; complejas -> claude-sonnet-4-6;
NUNCA un modelo superior a Sonnet 4.6 (ni Opus ni Fable), en ningun runtime,
ni siquiera por override del operador.

Backend anthropic para ejercitar el path Claude del router.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ["LLM_BACKEND"] = "anthropic"

from services import llm_router  # noqa: E402

_FORBIDDEN = re.compile(r"opus|fable", re.IGNORECASE)
_CAP = "claude-sonnet-4-6"


def _blocks(tokens_approx: int) -> list[dict]:
    """Genera un bloque cuyo content estimado ~= tokens_approx (4 chars/token)."""
    return [{"content": "x" * (tokens_approx * 4)}]


def test_clamp_model_maps_forbidden_to_sonnet():
    assert llm_router.clamp_model("claude-opus-4-7") == _CAP
    assert llm_router.clamp_model("claude-opus-9-9") == _CAP
    assert llm_router.clamp_model("claude-fable-5") == _CAP


def test_clamp_model_preserves_allowed():
    assert llm_router.clamp_model("claude-haiku-4-5") == "claude-haiku-4-5"
    assert llm_router.clamp_model("claude-sonnet-4-6") == "claude-sonnet-4-6"


def test_fingerprint_xl_does_not_return_opus():
    d = llm_router.decide(
        agent_type="developer",
        blocks=_blocks(100),
        fingerprint_complexity="XL",
        backend="anthropic",
    )
    assert not _FORBIDDEN.search(d.model)
    assert d.model == _CAP


def test_large_context_does_not_return_opus():
    d = llm_router.decide(
        agent_type="developer",
        blocks=_blocks(40_000),
        backend="anthropic",
    )
    assert not _FORBIDDEN.search(d.model)
    assert d.model == _CAP


def test_operator_override_to_opus_is_clamped():
    d = llm_router.decide(
        agent_type="developer",
        blocks=_blocks(100),
        override="claude-opus-4-7",
        backend="anthropic",
    )
    assert d.model == _CAP
    # El reason debe dejar rastro del clamp para auditoria.
    assert "clamp" in d.reason.lower()


def test_qa_small_context_is_haiku():
    d = llm_router.decide(
        agent_type="qa",
        blocks=_blocks(1_000),
        backend="anthropic",
    )
    assert d.model == "claude-haiku-4-5"


def test_no_typical_input_returns_forbidden_model():
    """Property-style: barrido sobre el espacio de inputs tipicos del path Claude."""
    agents = ["business", "functional", "technical", "developer", "qa", "unknown"]
    sizes = [200, 2_500, 5_000, 9_000, 13_000, 35_000]
    fps = [None, "S", "M", "L", "XL"]
    overrides = [None, "claude-opus-4-7", "claude-fable-9"]
    for a in agents:
        for s in sizes:
            for fp in fps:
                for ov in overrides:
                    d = llm_router.decide(
                        agent_type=a,
                        blocks=_blocks(s),
                        fingerprint_complexity=fp,
                        override=ov,
                        backend="anthropic",
                    )
                    assert not _FORBIDDEN.search(d.model), (
                        f"router devolvio modelo prohibido {d.model} "
                        f"para agent={a} size={s} fp={fp} override={ov}"
                    )


def test_claude_models_catalog_has_no_opus():
    for m in llm_router.CLAUDE_MODELS:
        assert not _FORBIDDEN.search(m), f"CLAUDE_MODELS contiene modelo prohibido: {m}"
