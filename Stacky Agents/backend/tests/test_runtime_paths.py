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


# --- helpers de fabricación de layout (paths, sin crear dirs) ---
def _embedded_module_path(root: Path) -> Path:
    # <root>/Tools/Stacky/Stacky Agents/backend/runtime_paths.py  → parents[4]==root
    return root / "Tools" / "Stacky" / "Stacky Agents" / "backend" / "runtime_paths.py"

def _standalone_module_path(root: Path) -> Path:
    # <root>/STACKY/Stacky/Stacky Agents/backend/runtime_paths.py → parents[4]==root, NO embebido
    return root / "STACKY" / "Stacky" / "Stacky Agents" / "backend" / "runtime_paths.py"


def test_source_layout_repo_root_matches_embedded(monkeypatch, tmp_path):
    """El helper devuelve <repo> SOLO si el layout embebido Tools/Stacky/... calza."""
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _embedded_module_path(tmp_path).resolve())
    assert runtime_paths._source_layout_repo_root() == tmp_path.resolve()


def test_source_layout_repo_root_none_when_standalone(monkeypatch, tmp_path):
    """Checkout no embebido (overshoot) → None (NO ruta mal formada)."""
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _standalone_module_path(tmp_path).resolve())
    assert runtime_paths._source_layout_repo_root() is None


def test_source_layout_repo_root_none_when_shallow(monkeypatch):
    """[ADICIÓN ARQUITECTO] Módulo con <5 niveles de padres → None, sin crash.

    Blinda el caso borde documentado en §4 (`parents[4]` IndexError → None) que
    v1 afirmaba cubrir sin test. Un checkout raro (p. ej. módulo en la raíz de
    una unidad) no debe tumbar la resolución."""
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: Path("C:/x/runtime_paths.py"))  # sólo 1 nivel de padre
    assert runtime_paths._source_layout_repo_root() is None


def test_not_frozen_embedded_layout_uses_repo_root(monkeypatch, tmp_path):
    """No congelado + layout embebido + sin proyecto → devuelve <repo> embebido."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _embedded_module_path(tmp_path).resolve())
    assert runtime_paths.repo_root() == tmp_path.resolve()


def test_not_frozen_standalone_returns_sentinel(monkeypatch, tmp_path):
    """No congelado + checkout no embebido + sin proyecto → sentinel, NO parents[4] (V2)."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _standalone_module_path(tmp_path).resolve())
    result = runtime_paths.repo_root()
    assert result == runtime_paths._UNRESOLVED_REPO_ROOT
    assert not result.exists()


def test_active_project_wins_even_not_frozen(monkeypatch, tmp_path):
    """CLAVE: en dev el workspace_root del proyecto activo gana sobre parents[4]."""
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: tmp_path)
    # aunque el layout embebido resolviera, el proyecto activo tiene prioridad
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _embedded_module_path(tmp_path / "other").resolve())
    assert runtime_paths.repo_root() == tmp_path


def test_warning_throttled_non_frozen_standalone(monkeypatch, caplog):
    """El WARNING 'no resoluble' se emite UNA vez también en dev standalone."""
    import logging
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: False)
    monkeypatch.setattr(runtime_paths, "_active_workspace_root", lambda: None)
    monkeypatch.setattr(runtime_paths, "_module_path",
                        lambda: _standalone_module_path(Path("Z:/nope")).resolve())
    with caplog.at_level(logging.WARNING, logger="stacky.runtime_paths"):
        for _ in range(5):
            runtime_paths.repo_root()
    warnings = [r for r in caplog.records if "no resoluble" in r.getMessage()]
    assert len(warnings) == 1


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
