"""
test_docs_api.py — Tests del Blueprint /api/docs (Feature #3 DocTree)
=====================================================================

Cubre:
  - GET /api/docs/index → 200 con estructura correcta.
  - GET /api/docs/content?path=docs/valid.md → 200 con contenido.
  - GET /api/docs/content?path=../../secrets.env → 400 path_traversal_blocked.
  - GET /api/docs/content?path=docs/no_existe.md → 404 not_found.
  - GET /api/docs/content sin param → 400 missing_param.

Criterios de aceptación: CA-3.4 (seguridad).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import services.doc_indexer as indexer
from app import create_app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def patched_root(tmp_path, monkeypatch):
    """Reemplaza STACKY_AGENTS_ROOT con tmp_path y crea archivos de prueba."""
    monkeypatch.setattr(indexer, "STACKY_AGENTS_ROOT", tmp_path)
    indexer.invalidate_cache()

    # Crear archivo válido en docs/
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "sample.md").write_text("# Sample Doc\n\n## Sección\n\nContenido.", encoding="utf-8")

    # Archivo en raíz
    (tmp_path / "README.md").write_text("# README\n", encoding="utf-8")

    yield tmp_path
    indexer.invalidate_cache()


@pytest.fixture()
def client(patched_root):
    """Flask test client con STACKY_AGENTS_ROOT patcheado."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ── Tests: GET /api/docs/index ────────────────────────────────────────────────

class TestDocsIndex:
    def test_returns_200_with_roots(self, client):
        resp = client.get("/api/docs/index")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "indexed_at" in data
        assert "roots" in data
        assert len(data["roots"]) == 3

    def test_root_ids(self, client):
        resp = client.get("/api/docs/index")
        data = resp.get_json()
        ids = [r["id"] for r in data["roots"]]
        assert "technical-docs" in ids
        assert "agents" in ids
        assert "roadmaps" in ids

    def test_technical_docs_has_sample(self, client):
        resp = client.get("/api/docs/index")
        data = resp.get_json()
        tech = next(r for r in data["roots"] if r["id"] == "technical-docs")
        labels = [c["label"] for c in tech["children"]]
        assert "sample.md" in labels

    def test_sample_has_headings(self, client):
        resp = client.get("/api/docs/index")
        data = resp.get_json()
        tech = next(r for r in data["roots"] if r["id"] == "technical-docs")
        sample = next(c for c in tech["children"] if c["label"] == "sample.md")
        assert len(sample["headings"]) >= 2
        assert sample["headings"][0]["level"] == 1


# ── Tests: GET /api/docs/content ─────────────────────────────────────────────

class TestDocsContent:
    def test_valid_file_returns_200(self, client):
        resp = client.get("/api/docs/content?path=docs/sample.md")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "Sample Doc" in data["content"]
        assert data["encoding"] == "utf-8"
        assert data["path"] == "docs/sample.md"

    def test_path_traversal_returns_400(self, client):
        """CA-3.4 — path traversal → 400 path_traversal_blocked."""
        resp = client.get("/api/docs/content?path=../../secrets.env")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["ok"] is False
        assert data["error"] == "path_traversal_blocked"

    def test_path_traversal_backend_env(self, client):
        """../../backend/.env también debe ser bloqueado."""
        resp = client.get("/api/docs/content?path=../../backend/.env")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "path_traversal_blocked"

    def test_nonexistent_file_returns_404(self, client):
        resp = client.get("/api/docs/content?path=docs/no_existe.md")
        assert resp.status_code == 404
        data = resp.get_json()
        assert data["ok"] is False
        assert data["error"] == "not_found"

    def test_missing_param_returns_400(self, client):
        resp = client.get("/api/docs/content")
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "missing_param"

    def test_valid_root_md(self, client):
        resp = client.get("/api/docs/content?path=README.md")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "README" in data["content"]


# ── Tests: GET /api/docs/sources (Plan 268 F0.2) ──────────────────────────────

class TestDocsSourcesFlags:
    def test_sources_expone_graph_explorer_enabled(self, client):
        """Plan 268 F0.2 — el payload de /sources transporta la flag del explorador."""
        resp = client.get("/api/docs/sources")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "graph_explorer_enabled" in data
        assert isinstance(data["graph_explorer_enabled"], bool)


# ===========================================================================
# Plan 284 F5.3 - aprobacion human-in-the-loop del paso a IMPLEMENTAR
# ===========================================================================

class TestPlan284StageApprove:
    """El camino POR DEFECTO del producto pasa por aca: con STAGES=ON y
    AUTOAPPLY=OFF todo run se detiene en awaiting_approval, asi que este
    endpoint es la unica salida."""

    def _registrar_run(self, state="awaiting_approval"):
        from services import doc_documenter
        run_id = "run284test"
        doc_documenter._run_registry[run_id] = {
            "state": state, "project": "P", "runtime": "claude_code_cli",
            "target_root": "/tmp/x", "branch": "stacky/doc-x",
            "operator_note": "", "stages": [], "written": [], "skipped": [],
        }
        return run_id

    def test_plan284_approve_404_con_stages_off(self, client, monkeypatch):
        from config import config
        monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", False)
        run_id = self._registrar_run()
        r = client.post("/api/docs/documenter/stage/approve",
                        json={"run": run_id, "approve": True})
        assert r.status_code == 404
        body = r.get_json()
        # Capacidad desactivada, NO "permiso denegado" (mono-operador, sin auth).
        assert body["error"] == "pipeline_stages_disabled"
        assert "desactivada" in body["message"].lower()
        assert "permiso" not in body["message"].lower()

    def test_plan284_approve_409_si_no_espera(self, client, monkeypatch):
        from config import config
        from services import doc_documenter
        monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
        run_id = self._registrar_run(state="running")
        r = client.post("/api/docs/documenter/stage/approve",
                        json={"run": run_id, "approve": True})
        assert r.status_code == 409
        # AUSENCIA: el run NO cambio de estado.
        assert doc_documenter._run_registry[run_id]["state"] == "running"
        # PRESENCIA: y sigue existiendo.
        assert doc_documenter.get_run(run_id) is not None

    def test_plan284_approve_true_reanuda(self, client, monkeypatch):
        from config import config
        from services import doc_documenter
        monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
        monkeypatch.setattr(doc_documenter, "_resume_after_approval",
                            lambda *a, **k: None)
        run_id = self._registrar_run()
        r = client.post("/api/docs/documenter/stage/approve",
                        json={"run": run_id, "approve": True})
        assert r.status_code == 200
        assert r.get_json()["state"] != "awaiting_approval"
        assert doc_documenter._run_registry[run_id]["state"] != "awaiting_approval"

    def test_plan284_approve_false_cancela_y_descarta(self, client, monkeypatch):
        from config import config
        from services import doc_documenter
        monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)

        llamadas = []
        monkeypatch.setattr(doc_documenter, "discard_doc_branch",
                            lambda root, branch: llamadas.append((root, branch)))
        monkeypatch.setattr(doc_documenter, "_persist_run_report", lambda *a, **k: None)

        run_id = self._registrar_run()
        r = client.post("/api/docs/documenter/stage/approve",
                        json={"run": run_id, "approve": False})
        assert r.status_code == 200
        assert r.get_json()["state"] == "cancelled_by_operator"
        assert doc_documenter._run_registry[run_id]["state"] == "cancelled_by_operator"
        # La rama se descarta EXACTAMENTE una vez.
        assert len(llamadas) == 1

    def test_plan284_approve_404_run_inexistente(self, client, monkeypatch):
        from config import config
        monkeypatch.setattr(config, "STACKY_DOCS_PIPELINE_STAGES_ENABLED", True)
        r = client.post("/api/docs/documenter/stage/approve",
                        json={"run": "no_existe_284", "approve": True})
        assert r.status_code == 404
        assert r.get_json()["error"] == "run_not_found"
