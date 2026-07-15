"""Plan 137 F3/F4/F5 — pipeline v2 del Documentador: short-circuit, persistencia, preview.

Tests corridos por archivo con el venv real del repo (backend/.venv, py3.13).
"""
from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest


# ---------------------------------------------------------------------------
# C9 — fixture anti test-order pollution para _run_registry
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_run_registry():
    from services import doc_documenter
    snapshot = dict(doc_documenter._run_registry)
    yield
    doc_documenter._run_registry.clear()
    doc_documenter._run_registry.update(snapshot)


# ---------------------------------------------------------------------------
# F3 — short-circuit de modos sin targets
# ---------------------------------------------------------------------------

def test_should_invoke_mode_tabla_completa():
    from services.doc_documenter import DocumenterMode, DocumenterPlan, should_invoke_mode

    plan_vacio = DocumenterPlan(
        status="ok", modes=[], notes_to_normalize=[], notes_to_update=[],
    )
    plan_lleno = DocumenterPlan(
        status="ok", modes=[], notes_to_normalize=["a.md"], notes_to_update=["b.md"],
    )

    assert should_invoke_mode(DocumenterMode.NORMALIZAR, plan_vacio, 0) == (False, "sin_notas_para_normalizar")
    assert should_invoke_mode(DocumenterMode.NORMALIZAR, plan_lleno, 0)[0] is True
    assert should_invoke_mode(DocumenterMode.ACTUALIZAR, plan_vacio, 0) == (False, "sin_notas_stale")
    assert should_invoke_mode(DocumenterMode.ACTUALIZAR, plan_lleno, 0)[0] is True
    assert should_invoke_mode(DocumenterMode.ENRIQUECER, plan_vacio, 0) == (False, "sin_huerfanas")
    assert should_invoke_mode(DocumenterMode.ENRIQUECER, plan_vacio, 3)[0] is True
    assert should_invoke_mode(DocumenterMode.RECONSTRUIR, plan_vacio, 0) == (True, "")
    assert should_invoke_mode(DocumenterMode.RECONSTRUIR, plan_lleno, 5) == (True, "")
    assert should_invoke_mode(DocumenterMode.COMPLETAR, plan_vacio, 0) == (True, "")
    assert should_invoke_mode(DocumenterMode.COMPLETAR, plan_lleno, 5) == (True, "")


def test_short_circuit_no_invoca_modos_sin_targets(monkeypatch, tmp_path, clean_run_registry):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)

    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, DocumenterPlan

    plan = DocumenterPlan(
        status="ok", modes=[DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER],
        notes_to_normalize=[], notes_to_update=[],
    )
    monkeypatch.setattr(doc_documenter, "plan_documenter_run", lambda *a, **k: plan)
    monkeypatch.setattr(
        doc_documenter, "_resolve_target_paths",
        lambda project_name: (str(tmp_path), str(tmp_path), str(tmp_path)),
    )

    import services.doc_graph as doc_graph
    monkeypatch.setattr(doc_graph, "build_graph", lambda project_name=None, **kwargs: {"orphans": []})

    invoked: list[str] = []

    def _spy_invoke(mode, ctx, project_name, runtime, **kwargs):
        invoked.append(str(mode.value))
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _spy_invoke)

    report = doc_documenter.run_documenter("p", "mock")

    assert invoked == []
    assert report["modes_skipped"] == [
        {"mode": "NORMALIZAR", "reason": "sin_notas_para_normalizar"},
        {"mode": "ENRIQUECER", "reason": "sin_huerfanas"},
    ]


def test_flag_off_invoca_todos_los_modos(monkeypatch, tmp_path, clean_run_registry):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)

    from services import doc_documenter
    from services.doc_documenter import DocumenterMode, DocumenterPlan

    plan = DocumenterPlan(
        status="ok", modes=[DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER],
        notes_to_normalize=[], notes_to_update=[],
    )
    monkeypatch.setattr(doc_documenter, "plan_documenter_run", lambda *a, **k: plan)
    monkeypatch.setattr(
        doc_documenter, "_resolve_target_paths",
        lambda project_name: (str(tmp_path), str(tmp_path), str(tmp_path)),
    )

    invoked: list[str] = []

    def _spy_invoke(mode, ctx, project_name, runtime, **kwargs):
        invoked.append(str(mode.value))
        return []

    monkeypatch.setattr(doc_documenter, "invoke_documenter", _spy_invoke)

    report = doc_documenter.run_documenter("p", "mock")

    assert invoked == ["NORMALIZAR", "ENRIQUECER"]
    assert report["modes_skipped"] == []


# ---------------------------------------------------------------------------
# F4 — historial persistente de corridas
# ---------------------------------------------------------------------------

def test_persist_y_get_run_desde_disco(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("abc123", {
        "state": "completed", "written": [], "skipped": [], "modes": [],
        "branch": None, "degraded": True,
    })
    rec = doc_documenter.get_run("abc123")
    assert rec is not None
    assert rec["state"] == "completed"


def test_list_runs_ordena_y_limita(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    for i, run_id in enumerate(["r1", "r2", "r3"]):
        doc_documenter._persist_run_report(run_id, {
            "state": "completed", "written": [], "skipped": [], "modes": [],
            "branch": None, "degraded": False,
        })
        path = doc_documenter._runs_dir() / f"{run_id}.json"
        os.utime(path, (1000 + i * 10, 1000 + i * 10))

    runs = doc_documenter.list_runs(2)
    assert len(runs) == 2
    assert runs[0]["run_id"] == "r3"


def test_persistencia_flag_off_inerte(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", False)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("x1", {"state": "completed"})
    assert doc_documenter.list_runs() == []
    assert not (tmp_path / "documenter_runs" / "x1.json").exists()


def test_persist_es_upsert(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("r1", {"state": "running", "written": [], "skipped": [], "modes": []})
    doc_documenter._persist_run_report("r1", {"state": "completed", "written": [], "skipped": [], "modes": []})
    files = list(doc_documenter._runs_dir().glob("r1.json"))
    assert len(files) == 1
    assert doc_documenter.get_run("r1")["state"] == "completed"


def test_retencion_100(monkeypatch, tmp_path):
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    for i in range(102):
        doc_documenter._persist_run_report(f"r{i}", {
            "state": "completed", "written": [], "skipped": [], "modes": [],
        })
    remaining = list(doc_documenter._runs_dir().glob("*.json"))
    assert len(remaining) == 100


def test_list_runs_agrega_citas(monkeypatch, tmp_path):
    # A1 — list_runs() agrega citations_ok/citations_total sumando por archivo.
    import config
    monkeypatch.setattr(config.config, "STACKY_DOCS_DOCUMENTER_V2_ENABLED", True)
    import runtime_paths
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)

    from services import doc_documenter
    doc_documenter._persist_run_report("rcit", {
        "state": "completed", "written": [], "skipped": [], "modes": [],
        "branch": None, "degraded": False,
        "files": [
            {"citations": {"total": 3, "ok": 2, "bad": ["x"]}},
            {"citations": {"total": 1, "ok": 1, "bad": []}},
        ],
    })
    runs = doc_documenter.list_runs()
    assert len(runs) == 1
    assert runs[0]["citations_ok"] == 3
    assert runs[0]["citations_total"] == 4


# ---------------------------------------------------------------------------
# F5 — preview por archivo en el reporte
# ---------------------------------------------------------------------------

def test_apply_proposals_incluye_preview(tmp_path):
    from services.doc_documenter import DocProposal, apply_proposals
    long_content = "x" * 5000
    prop = DocProposal(path="out.md", action="create", content=long_content,
                       marks_ok=True, sources=[])
    result = apply_proposals([prop], str(tmp_path), None, workspace_root=str(tmp_path))
    assert len(result.files[0]["content_preview"]) == 4000
