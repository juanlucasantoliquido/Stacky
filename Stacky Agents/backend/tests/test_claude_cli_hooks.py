"""Tests de F1.4 — hooks de Claude Code generados por Stacky + endpoint."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_write_run_settings_generates_posttooluse_hook(tmp_path):
    from services import claude_cli_hooks

    settings_path = claude_cli_hooks.write_run_settings(tmp_path, port=5050)
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text(encoding="utf-8"))

    hooks = settings["hooks"]["PostToolUse"]
    assert hooks[0]["matcher"] == "Write|Edit"
    command = hooks[0]["hooks"][0]["command"]
    assert hooks[0]["hooks"][0]["type"] == "command"
    # El comando referencia el script generado en el mismo run_dir.
    assert str(tmp_path) in command

    # El settings SOLO define hooks: no debe tocar permisos (decisión §5.3).
    assert set(settings.keys()) == {"hooks"}

    # El script existe y apunta al endpoint local de validación.
    script_name = (
        claude_cli_hooks.HOOK_SCRIPT_PS1 if os.name == "nt" else claude_cli_hooks.HOOK_SCRIPT_SH
    )
    script = (tmp_path / script_name).read_text(encoding="utf-8")
    assert "/api/agents/validate-artifact" in script
    assert "5050" in script
    assert "pending-task" in script


def test_cleanup_removes_ephemeral_files(tmp_path):
    from services import claude_cli_hooks

    claude_cli_hooks.write_run_settings(tmp_path, port=5050)
    claude_cli_hooks.cleanup_run_settings(tmp_path)
    assert not (tmp_path / claude_cli_hooks.SETTINGS_FILENAME).exists()
    assert not (tmp_path / claude_cli_hooks.HOOK_SCRIPT_PS1).exists()
    assert not (tmp_path / claude_cli_hooks.HOOK_SCRIPT_SH).exists()


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_validate_artifact_endpoint(client, tmp_path):
    # path faltante → 400
    r = client.post("/api/agents/validate-artifact", json={})
    assert r.status_code == 400

    # pending-task.json roto → valid false con error exacto
    rf = tmp_path / "Agentes" / "outputs" / "epic-206" / "RF-001"
    rf.mkdir(parents=True)
    pt = rf / "pending-task.json"
    pt.write_text("{broken", encoding="utf-8")
    r = client.post("/api/agents/validate-artifact", json={"path": str(pt)})
    assert r.status_code == 200
    body = r.get_json()
    assert body["valid"] is False
    assert body["kind"] == "pending_task"
    # Plan 149 F6 — el mensaje ahora se clasifica (empty/truncated/malformed) vía
    # classify_json_failure; "{broken" (sin cierre) clasifica como "truncado".
    assert any("truncad" in e for e in body["errors"])

    # archivo no-artifact → valid true, kind other
    other = tmp_path / "notas.md"
    other.write_text("x", encoding="utf-8")
    r = client.post("/api/agents/validate-artifact", json={"path": str(other)})
    assert r.get_json()["valid"] is True
    assert r.get_json()["kind"] == "other"
