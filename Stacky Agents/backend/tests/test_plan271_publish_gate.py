# backend/tests/test_plan271_publish_gate.py
"""Plan 271 F4 — el gate de publish deja de bloquear el cambio de estado
cuando no había nada que publicar. Cierra RC-2."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import pytest


@pytest.fixture(autouse=True)
def _init_app_for_schema():
    from app import create_app

    create_app()


def _flag(monkeypatch, value: bool):
    import config as _config
    monkeypatch.setattr(_config.config, "STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED", value, raising=False)


@pytest.mark.parametrize("publish_result,flag_on,expected_blocks", [
    ({"ok": True}, True, False),
    ({"skipped": True, "reason": "html_output_path_missing"}, True, False),
    ({"skipped": True, "reason": "auto_publish_disabled"}, True, False),
    ({"skipped": True, "reason": "ado_publisher_unavailable"}, True, False),
    ({"skipped": True, "reason": "already_terminal_no_html"}, True, False),
    ({"ok": False, "event": "publish.failed", "reason": "ADO 400"}, True, True),
    ({"ok": False, "event": "publish.idempotent_replay"}, True, True),
    ({"skipped": True, "reason": "html_output_path_missing"}, False, True),
])
def test_publish_gate_blocks_tabla_de_verdad(monkeypatch, publish_result, flag_on, expected_blocks):
    from services.agent_completion_internal import _publish_gate_blocks

    _flag(monkeypatch, flag_on)
    assert _publish_gate_blocks(publish_result) is expected_blocks
