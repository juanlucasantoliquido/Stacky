"""Plan 41 F1 — Generador del pre-vuelo (LLM inyectado, sin LLM real)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.intent_preflight import (  # noqa: E402
    PreflightRuntimeUnavailable,
    generate_intent_brief,
)

_VALID = json.dumps({"objective": "X", "deliverables": [], "assumptions": [],
                     "open_questions": [], "areas": [], "confidence": 0.6})


def _gen(invoke, brief_text="hacé la épica"):
    return generate_intent_brief(
        brief_text=brief_text, context_summary="ctx", runtime="claude_code_cli",
        project_name="P", invoke_short_llm=invoke, log=lambda *a, **k: None,
    )


def test_generate_returns_brief_from_fake_llm():
    b = _gen(lambda s, u, rt, p: _VALID)
    assert b is not None
    assert b.objective == "X"


def test_generate_empty_brief_returns_none():
    assert _gen(lambda *a: _VALID, brief_text="") is None


def test_generate_runtime_unavailable_returns_none():
    def _raise(*a):
        raise PreflightRuntimeUnavailable("CLI no logueada")
    assert _gen(_raise) is None


def test_generate_never_raises_on_garbage():
    def _boom(*a):
        raise RuntimeError("kaboom")
    assert _gen(_boom) is None


def test_generate_garbage_json_is_low_confidence():
    b = _gen(lambda *a: "no soy json")
    assert b is not None
    assert b.confidence == 0.0
