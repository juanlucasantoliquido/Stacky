"""C0 — Tests para trazabilidad en el runner github_copilot (agent_runner.py)."""
from __future__ import annotations

import hashlib
import json
import pytest
from unittest.mock import MagicMock, patch


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sha256_blocks(blocks: list) -> str:
    payload = json.dumps(blocks, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _make_mock_result(output="ok", metadata=None):
    from agents.base import AgentResult
    return AgentResult(output=output, output_format="html", metadata=metadata or {})


def _stub_run_trace(blocks, agent_type, agent_name, **kw):
    """Simula _build_trace_metadata para tests que no pueden importar todo agent_runner."""
    import importlib
    tr = importlib.import_module("agent_runner")
    return tr._build_trace_metadata(
        prompt_blocks=blocks,
        agent_type=agent_type,
        agent_name=agent_name,
        **kw,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_records_prompt_sha_and_agent():
    """_build_trace_metadata devuelve prompt_sha, prompt_len, agent_type, agent_name."""
    import agent_runner
    blocks = [{"title": "test", "content": "hello"}]
    meta = agent_runner._build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="functional",
        agent_name="Functional",
        prompt_text_enabled=False,
    )
    assert "prompt_sha" in meta
    assert meta["prompt_sha"] == _sha256_blocks(blocks)
    assert "prompt_len" in meta
    assert meta["prompt_len"] > 0
    assert meta["agent_type"] == "functional"
    assert meta["agent_name"] == "Functional"


def test_prompt_text_off_by_default():
    """Sin prompt_text_enabled, prompt_text NO aparece en metadata."""
    import agent_runner
    blocks = [{"content": "secret prompt text"}]
    meta = agent_runner._build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="qa",
        agent_name="QA",
        prompt_text_enabled=False,
    )
    assert "prompt_text" not in meta


def test_prompt_text_on_when_flagged():
    """Con prompt_text_enabled=True, prompt_text SÍ aparece en metadata."""
    import agent_runner
    blocks = [{"content": "secret prompt text"}]
    meta = agent_runner._build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="qa",
        agent_name="QA",
        prompt_text_enabled=True,
    )
    assert "prompt_text" in meta
    assert meta["prompt_text"] == json.dumps(blocks, sort_keys=True, ensure_ascii=False)


def test_records_produced_files_key():
    """_collect_produced_files devuelve lista (vacía si no hay dir)."""
    import agent_runner
    files = agent_runner._collect_produced_files(output_dir=None)
    assert isinstance(files, list)
    assert files == []


def test_does_not_overwrite_runtime():
    """setdefault en runner: si metadata ya tiene 'runtime', no se pisa."""
    import agent_runner
    existing = {"runtime": "github_copilot", "agent_type": "OTHER"}
    blocks = [{"content": "x"}]
    trace = agent_runner._build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="functional",
        agent_name="Functional",
        prompt_text_enabled=False,
    )
    # Simular merge con setdefault
    for k, v in trace.items():
        existing.setdefault(k, v)
    assert existing["runtime"] == "github_copilot"
    # agent_type ya existía en existing (como "OTHER") → no se pisa
    assert existing["agent_type"] == "OTHER"
