"""Tests de runtime_paths.repo_root() — resolución frozen-aware.

Cubre la causa raíz C1 del plan PLAN_FIX_REGISTRO_COMPLETION_OPENCHAT.md:
en un deploy congelado que arranca ANTES de que haya proyecto activo,
repo_root() NO debe caer al fallback `parents[4]` (que apunta a
`<repo>/Tools/Stacky` en deploys embebidos) sino devolver un sentinel
inexistente, y debe re-resolver al `workspace_root` cuando el proyecto se
activa.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import runtime_paths  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Aísla de STACKY_REPO_ROOT y rearma el throttle del warning."""
    monkeypatch.delenv("STACKY_REPO_ROOT", raising=False)
    runtime_paths._warned_unresolved_repo_root = False
    yield
    runtime_paths._warned_unresolved_repo_root = False


def test_env_override_wins_even_when_frozen(monkeypatch, tmp_path):
    """STACKY_REPO_ROOT tiene prioridad sobre todo, incluso congelado."""
    monkeypatch.setenv("STACKY_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    assert runtime_paths.repo_root() == tmp_path.resolve()


def test_not_frozen_uses_source_layout(monkeypatch):
    """Layout de fuentes → parents[4] desde backend/runtime_paths.py."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    expected = Path(runtime_paths.__file__).resolve().parents[4]
    assert runtime_paths.repo_root() == expected


def test_frozen_with_active_project_uses_workspace_root(monkeypatch, tmp_path):
    """Congelado + proyecto activo → workspace_root del proyecto."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: tmp_path)
    assert runtime_paths.repo_root() == tmp_path


def test_frozen_without_active_project_returns_nonexistent_sentinel(monkeypatch):
    """Congelado sin proyecto activo → sentinel inexistente, NO parents[4]."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)

    result = runtime_paths.repo_root()

    assert result == runtime_paths._UNRESOLVED_REPO_ROOT
    assert not result.exists()
    # Y crucialmente NO es el viejo fallback parents[4] (<repo>/Tools/Stacky).
    assert result != Path(runtime_paths.__file__).resolve().parents[4]


def test_frozen_re_resolves_when_project_activates_later(monkeypatch, tmp_path):
    """Construcción sin proyecto activo (sentinel) → luego se activa → re-resuelve.

    Reproduce la secuencia del watcher arrancando antes que el operador active
    el proyecto. Valida también que el warning se rearma para futuros baches.
    """
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)

    active = {"ws": None}
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: active["ws"])

    # 1) Arranque sin proyecto: sentinel.
    assert runtime_paths.repo_root() == runtime_paths._UNRESOLVED_REPO_ROOT
    assert runtime_paths._warned_unresolved_repo_root is True

    # 2) El operador activa el proyecto: re-resuelve al workspace_root.
    active["ws"] = tmp_path
    assert runtime_paths.repo_root() == tmp_path
    # El throttle se rearmó al resolver con éxito.
    assert runtime_paths._warned_unresolved_repo_root is False

    # 3) Si vuelve a quedar sin proyecto, vuelve al sentinel (y re-avisa).
    active["ws"] = None
    assert runtime_paths.repo_root() == runtime_paths._UNRESOLVED_REPO_ROOT
    assert runtime_paths._warned_unresolved_repo_root is True


def test_warning_throttled_to_single_emit(monkeypatch, caplog):
    """El WARNING se emite una sola vez mientras persiste el estado no-resuelto."""
    import logging

    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)

    with caplog.at_level(logging.WARNING, logger="stacky.runtime_paths"):
        for _ in range(5):
            runtime_paths.repo_root()

    warnings = [r for r in caplog.records if "no resoluble" in r.getMessage()]
    assert len(warnings) == 1
