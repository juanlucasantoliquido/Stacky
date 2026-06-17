"""C1 — Tests de paridad de trazabilidad entre runners CLI."""
from __future__ import annotations

import json
import hashlib
import pytest


def _sha256_blocks(blocks: list) -> str:
    payload = json.dumps(blocks, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_claude_runner_records_agent_and_sha():
    """_build_trace_metadata importado en claude_code_cli_runner produce keys esperadas."""
    from agent_runner import _build_trace_metadata
    blocks = [{"title": "epic", "content": "do X"}]
    meta = _build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="developer",
        agent_name="Dev",
        prompt_text_enabled=False,
    )
    assert meta["agent_type"] == "developer"
    assert meta["agent_name"] == "Dev"
    assert meta["prompt_sha"] == _sha256_blocks(blocks)
    assert "prompt_text" not in meta


def test_codex_runner_records_agent_and_sha():
    """_build_trace_metadata tiene paridad con el runner codex."""
    from agent_runner import _build_trace_metadata
    blocks = [{"title": "task", "content": "implement Y"}]
    meta = _build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="qa",
        agent_name="QA",
        prompt_text_enabled=False,
    )
    assert meta["agent_type"] == "qa"
    assert meta["prompt_sha"] == _sha256_blocks(blocks)


def test_cli_prompt_text_gated():
    """prompt_text no aparece en CLI runners a menos que STACKY_TRACE_PROMPT_TEXT_ENABLED=true."""
    from agent_runner import _build_trace_metadata

    blocks = [{"content": "secret content"}]

    # OFF
    meta_off = _build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="functional",
        agent_name="Functional",
        prompt_text_enabled=False,
    )
    assert "prompt_text" not in meta_off

    # ON
    meta_on = _build_trace_metadata(
        prompt_blocks=blocks,
        agent_type="functional",
        agent_name="Functional",
        prompt_text_enabled=True,
    )
    assert "prompt_text" in meta_on
    assert "secret content" in meta_on["prompt_text"]
