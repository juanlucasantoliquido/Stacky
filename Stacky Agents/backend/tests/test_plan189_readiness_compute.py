"""tests/test_plan189_readiness_compute.py — Plan 189 F1 (KPI-1).

Los 5+ escenarios golden del semáforo de reversibilidad, con deploy_store
monkeypatcheado en memoria (nada de disco/ledger real). compute_rollback_readiness
es PURO: dado (app, ledger) devuelve `ready`/`to_version`/`candidates`/`reasons`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


def _patch_store(monkeypatch, *, app, current, retained, locked=False):
    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: app)
    monkeypatch.setattr("services.deploy_store.last_success_version", lambda *a, **k: current)
    monkeypatch.setattr("services.deploy_store.retained_versions", lambda *a, **k: list(retained))
    monkeypatch.setattr("services.deploy_store.is_locked", lambda *a, **k: locked)


def _app(target_cfg=None):
    targets = {"__local__": target_cfg} if target_cfg is not None else {}
    return {"id": "miapp", "targets": targets}


def test_ready_con_candidatas(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    _patch_store(monkeypatch, app=_app({"install_path": "D:/x"}),
                 current="v3", retained=["v3", "v2", "v1"])
    r = compute_rollback_readiness("miapp", "__local__")
    assert r["ready"] is True
    assert r["to_version"] == "v2"
    assert r["candidates"] == ["v2", "v1"]
    assert r["reasons"] == []
    assert r["current_version"] == "v3"


def test_sin_retenidas(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    _patch_store(monkeypatch, app=_app({"install_path": "D:/x"}),
                 current=None, retained=[])
    r = compute_rollback_readiness("miapp", "__local__")
    assert r["ready"] is False
    assert r["reasons"] == ["sin_versiones_retenidas"]
    assert r["to_version"] is None


def test_solo_version_actual(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    _patch_store(monkeypatch, app=_app({"install_path": "D:/x"}),
                 current="v3", retained=["v3"])
    r = compute_rollback_readiness("miapp", "__local__")
    assert r["ready"] is False
    assert r["reasons"] == ["solo_version_actual"]
    assert r["candidates"] == []


def test_target_sin_cfg(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    # app sin el target pedido → cfg None; damos candidatas para AISLAR la razón.
    _patch_store(monkeypatch, app=_app(None), current=None, retained=["v2"])
    r = compute_rollback_readiness("miapp", "__local__")
    assert "sin_target_cfg" in r["reasons"]
    assert r["ready"] is False
    assert r["protected"] is False


def test_run_en_curso(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    _patch_store(monkeypatch, app=_app({"install_path": "D:/x"}),
                 current="v3", retained=["v3", "v2"], locked=True)
    r = compute_rollback_readiness("miapp", "__local__")
    assert "run_en_curso" in r["reasons"]
    assert r["ready"] is False
    assert r["locked"] is True


def test_none_si_app_inexistente(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    monkeypatch.setattr("services.deploy_store.get_app", lambda _aid: None)
    assert compute_rollback_readiness("nope", "__local__") is None


def test_protected_no_baja_ready(monkeypatch):
    from services.rollback_readiness import compute_rollback_readiness

    _patch_store(monkeypatch, app=_app({"install_path": "D:/x", "protected": True}),
                 current="v3", retained=["v3", "v2"])
    r = compute_rollback_readiness("miapp", "__local__")
    assert r["ready"] is True
    assert r["protected"] is True


def test_sin_imports_de_ejecucion():
    """El servicio JAMÁS importa ejecutores/red: garantía por AST (no por substring,
    porque el docstring MENCIONA los módulos prohibidos con fines documentales)."""
    import ast

    src = Path(ROOT, "services", "rollback_readiness.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [n.name for n in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            imported.append(base)
            imported += [f"{base}.{n.name}" for n in node.names]
    joined = " ".join(imported)
    assert "deploy_executor" not in joined, f"import prohibido: {imported}"
    assert "remote_exec" not in joined, f"import prohibido: {imported}"
    assert "requests" not in imported, f"import prohibido: {imported}"
