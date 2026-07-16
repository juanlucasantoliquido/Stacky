"""Tests de services.claude_workspace_trust (Plan 144 F2/F3, cierra D1).

Preflight de confianza de workspace para el binario `claude`: lee/normaliza/
escribe `projects[key].hasTrustDialogAccepted` en `~/.claude.json`. Puro
sobre `tmp_path` como `home` — no toca el ~/.claude.json real del operador.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def test_missing_claude_json_untrusted(tmp_path):
    from services.claude_workspace_trust import read_workspace_trust

    result = read_workspace_trust(str(tmp_path), home=str(tmp_path / "home_missing"))
    assert result.trusted is False
    assert result.present is False
    assert result.error is not None


def test_project_absent_untrusted(tmp_path):
    from services.claude_workspace_trust import read_workspace_trust

    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"projects": {}}), encoding="utf-8")

    result = read_workspace_trust(str(tmp_path / "ws"), home=str(home))
    assert result.trusted is False
    assert result.present is False
    assert result.error is None


def test_project_present_true(tmp_path):
    from services.claude_workspace_trust import _normalize_project_key, read_workspace_trust

    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    key = _normalize_project_key(str(ws))
    (home / ".claude.json").write_text(
        json.dumps({"projects": {key: {"hasTrustDialogAccepted": True}}}), encoding="utf-8"
    )

    result = read_workspace_trust(str(ws), home=str(home))
    assert result.trusted is True
    assert result.present is True


def test_project_present_false(tmp_path):
    from services.claude_workspace_trust import _normalize_project_key, read_workspace_trust

    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    key = _normalize_project_key(str(ws))
    (home / ".claude.json").write_text(
        json.dumps({"projects": {key: {"hasTrustDialogAccepted": False}}}), encoding="utf-8"
    )

    result = read_workspace_trust(str(ws), home=str(home))
    assert result.trusted is False
    assert result.present is True


def test_normalize_uses_forward_slashes():
    from services.claude_workspace_trust import _normalize_project_key

    key = _normalize_project_key(r"C:\a\b")
    assert "\\" not in key


def test_set_workspace_trusted_writes_and_backups(tmp_path):
    from services.claude_workspace_trust import read_workspace_trust, set_workspace_trusted

    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text(json.dumps({"projects": {}}), encoding="utf-8")

    result = set_workspace_trusted(str(ws), home=str(home))
    assert result.trusted is True
    assert result.error is None
    assert (home / ".claude.json.stacky.bak").exists()

    reread = read_workspace_trust(str(ws), home=str(home))
    assert reread.trusted is True


def test_set_refuses_unreadable_json(tmp_path):
    from services.claude_workspace_trust import set_workspace_trusted

    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude.json").write_text("{ not valid json !!", encoding="utf-8")

    result = set_workspace_trusted(str(ws), home=str(home))
    assert result.error is not None
    assert (home / ".claude.json").read_text(encoding="utf-8") == "{ not valid json !!"


def test_autoset_idempotent(tmp_path):
    """F3 — llamar set_workspace_trusted dos veces deja un solo entry True y
    no corrompe otros keys de projects."""
    from services.claude_workspace_trust import (
        _normalize_project_key,
        read_workspace_trust,
        set_workspace_trusted,
    )

    ws = tmp_path / "ws"
    ws.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    other_key = "C:/some/other/project"
    (home / ".claude.json").write_text(
        json.dumps({"projects": {other_key: {"hasTrustDialogAccepted": True, "marker": "keep-me"}}}),
        encoding="utf-8",
    )

    set_workspace_trusted(str(ws), home=str(home))
    set_workspace_trusted(str(ws), home=str(home))

    data = json.loads((home / ".claude.json").read_text(encoding="utf-8"))
    key = _normalize_project_key(str(ws))
    assert data["projects"][key]["hasTrustDialogAccepted"] is True
    assert data["projects"][other_key]["marker"] == "keep-me"
    assert len(data["projects"]) == 2
    assert read_workspace_trust(str(ws), home=str(home)).trusted is True
