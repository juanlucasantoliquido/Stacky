"""
test_doc_indexer.py — Tests de doc_indexer (Feature #3 DocTree)
===============================================================

Cubre:
  - build_index() con fixture de tmp_path: verifica árbol correcto y headings.
  - read_content() path traversal → ValueError.
  - read_content() archivo inexistente → FileNotFoundError.
  - read_content() archivo válido → contenido correcto.
  - Cache TTL: build_index() reutiliza cache.
  - invalidate_cache(): fuerza re-scan.

Criterios de aceptación: CA-3.4 (seguridad), CA-3.5 (gracioso sin archivos).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

# ── path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import services.doc_indexer as indexer


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_md(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_roots(tmp_path, monkeypatch):
    """
    Reemplaza STACKY_AGENTS_ROOT por tmp_path para todos los tests de este módulo.
    Invalida el cache antes y después de cada test.
    """
    monkeypatch.setattr(indexer, "STACKY_AGENTS_ROOT", tmp_path)
    indexer.invalidate_cache()
    yield
    indexer.invalidate_cache()


# ── Tests: build_index ────────────────────────────────────────────────────────

class TestBuildIndex:
    def test_three_root_sections(self, tmp_path):
        """El índice siempre devuelve exactamente 3 secciones raíz."""
        result = indexer.build_index()
        ids = [r["id"] for r in result["roots"]]
        assert ids == ["technical-docs", "agents", "roadmaps"]

    def test_technical_docs_indexed(self, tmp_path):
        """Archivos en docs/ aparecen en 'technical-docs'."""
        _write_md(tmp_path / "docs" / "00_VISION.md", "# Vision\n\n## Filosofia\n\nTexto.")
        _write_md(tmp_path / "docs" / "01_ARCH.md", "# Arquitectura\n\nContenido.")

        result = indexer.build_index()
        tech = next(r for r in result["roots"] if r["id"] == "technical-docs")
        labels = [c["label"] for c in tech["children"]]
        assert "00_VISION.md" in labels
        assert "01_ARCH.md" in labels

    def test_headings_extracted(self, tmp_path):
        """Headings H1 y H2 son extraídos correctamente."""
        _write_md(
            tmp_path / "docs" / "test.md",
            "# Mi Título Principal\n\n## Sección Uno\n\n### Ignorar H3\n\n## Sección Dos\n"
        )
        result = indexer.build_index()
        tech = next(r for r in result["roots"] if r["id"] == "technical-docs")
        doc = tech["children"][0]
        assert len(doc["headings"]) == 3  # H1, H2, H2 (H3 ignorado)
        assert doc["headings"][0] == {"level": 1, "text": "Mi Título Principal", "anchor": "mi-ttulo-principal"}
        assert doc["headings"][1]["text"] == "Sección Uno"
        assert doc["headings"][2]["text"] == "Sección Dos"

    def test_roadmaps_indexed(self, tmp_path):
        """*.md en raíz aparecen en 'roadmaps'."""
        _write_md(tmp_path / "README.md", "# README\n")
        _write_md(tmp_path / "MejorasStackyAgent.md", "# Mejoras\n")

        result = indexer.build_index()
        roadmaps = next(r for r in result["roots"] if r["id"] == "roadmaps")
        labels = [c["label"] for c in roadmaps["children"]]
        assert "README.md" in labels
        assert "MejorasStackyAgent.md" in labels

    def test_agents_empty_without_vscode_dir(self):
        """Sin VSCODE_PROMPTS_DIR, la sección agents está vacía con nota."""
        result = indexer.build_index(vscode_prompts_dir=None)
        agents = next(r for r in result["roots"] if r["id"] == "agents")
        assert agents["children"] == []
        assert "note" in agents
        assert agents["note"] == "VSCODE_PROMPTS_DIR no configurado"

    def test_agents_indexed_from_vscode_dir(self, tmp_path):
        """*.agent.md en vscode_prompts_dir aparecen en 'agents'."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        _write_md(prompts_dir / "DevPacifico.agent.md", "# Dev Agent\n")
        _write_md(prompts_dir / "Analista.agent.md", "# Analista\n")

        result = indexer.build_index(vscode_prompts_dir=str(prompts_dir))
        agents = next(r for r in result["roots"] if r["id"] == "agents")
        labels = [c["label"] for c in agents["children"]]
        assert "DevPacifico.agent.md" in labels
        assert "Analista.agent.md" in labels

    def test_excludes_node_modules(self, tmp_path):
        """node_modules/ no se indexa."""
        _write_md(tmp_path / "docs" / "node_modules" / "some.md", "# Ignorar\n")
        _write_md(tmp_path / "docs" / "real.md", "# Real\n")

        result = indexer.build_index()
        tech = next(r for r in result["roots"] if r["id"] == "technical-docs")
        labels = [c["label"] for c in tech["children"]]
        assert "real.md" in labels
        assert "some.md" not in labels

    def test_excludes_venv(self, tmp_path):
        """.venv/ no se indexa."""
        _write_md(tmp_path / "docs" / ".venv" / "site.md", "# Venv\n")
        _write_md(tmp_path / "docs" / "ok.md", "# OK\n")

        result = indexer.build_index()
        tech = next(r for r in result["roots"] if r["id"] == "technical-docs")
        labels = [c["label"] for c in tech["children"]]
        assert "ok.md" in labels
        assert "site.md" not in labels

    def test_empty_docs_graceful(self, tmp_path):
        """Sin archivos, las secciones tienen children vacíos (CA-3.5)."""
        result = indexer.build_index()
        for root in result["roots"]:
            assert isinstance(root["children"], list)

    def test_path_in_node_is_relative(self, tmp_path):
        """El campo 'path' en cada nodo es relativo (ej: 'docs/00_VISION.md')."""
        _write_md(tmp_path / "docs" / "sub" / "spec.md", "# Spec\n")
        result = indexer.build_index()
        tech = next(r for r in result["roots"] if r["id"] == "technical-docs")
        assert tech["children"][0]["path"] == "docs/sub/spec.md"

    def test_indexed_at_present(self):
        """El índice incluye indexed_at en formato ISO."""
        result = indexer.build_index()
        assert "indexed_at" in result
        assert "T" in result["indexed_at"]  # formato ISO básico


class TestCache:
    def test_cache_reused_within_ttl(self, tmp_path):
        """Segunda llamada dentro del TTL devuelve el mismo objeto (cache hit)."""
        result1 = indexer.build_index()
        result2 = indexer.build_index()
        assert result1 is result2  # mismo objeto en memoria

    def test_invalidate_cache_forces_rebuild(self, tmp_path):
        """invalidate_cache() fuerza que el siguiente build_index reconstruya."""
        result1 = indexer.build_index()
        indexer.invalidate_cache()
        result2 = indexer.build_index()
        # Son dicts distintos (no el mismo objeto)
        assert result1 is not result2


# ── Tests: read_content ───────────────────────────────────────────────────────

class TestReadContent:
    def test_valid_docs_file(self, tmp_path):
        """Lee correctamente un archivo en docs/."""
        _write_md(tmp_path / "docs" / "sample.md", "# Sample\n\nContenido real.")
        content = indexer.read_content("docs/sample.md")
        assert "Contenido real." in content

    def test_valid_root_md(self, tmp_path):
        """Lee correctamente un .md en la raíz de STACKY_AGENTS_ROOT."""
        _write_md(tmp_path / "README.md", "# README\n")
        content = indexer.read_content("README.md")
        assert "README" in content

    def test_path_traversal_dotdot_blocked(self, tmp_path):
        """../../ en el path → ValueError con path_traversal_blocked."""
        with pytest.raises(ValueError, match="path_traversal_blocked"):
            indexer.read_content("../../secrets.env")

    def test_path_traversal_embedded_blocked(self, tmp_path):
        """docs/../../../secrets → ValueError."""
        with pytest.raises(ValueError, match="path_traversal_blocked"):
            indexer.read_content("docs/../../../secrets.env")

    def test_file_not_found(self, tmp_path):
        """Archivo inexistente dentro de docs/ → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            indexer.read_content("docs/no_existe.md")

    def test_agents_path_without_vscode_dir(self, tmp_path):
        """agents/ sin vscode_dir → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            indexer.read_content("agents/Dev.agent.md", vscode_prompts_dir=None)

    def test_agents_path_with_vscode_dir(self, tmp_path):
        """agents/ con vscode_dir válido → contenido correcto."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "Dev.agent.md").write_text("# Dev Agent\n", encoding="utf-8")

        content = indexer.read_content("agents/Dev.agent.md", vscode_prompts_dir=str(prompts_dir))
        assert "Dev Agent" in content

    def test_agents_traversal_blocked(self, tmp_path):
        """agents/../../secrets → ValueError."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        with pytest.raises(ValueError, match="path_traversal_blocked"):
            indexer.read_content("agents/../../secrets.env", vscode_prompts_dir=str(prompts_dir))

    def test_empty_path_blocked(self, tmp_path):
        """Path vacío → ValueError."""
        with pytest.raises(ValueError):
            indexer.read_content("")


# ── Tests: project docs sources ───────────────────────────────────────────────

class TestProjectDocs:
    def _patch_project(self, monkeypatch, cfg: dict):
        monkeypatch.setattr(
            indexer,
            "_project_manager",
            lambda: (
                lambda: cfg["name"],
                lambda name: cfg if name == cfg["name"] else None,
            ),
        )

    def test_lists_project_docs_source(self, tmp_path, monkeypatch):
        """workspace_root/docs aparece como fuente seleccionable del proyecto."""
        workspace = tmp_path / "workspace"
        _write_md(workspace / "docs" / "guide.md", "# Guide\n")
        cfg = {
            "name": "ACME",
            "display_name": "ACME App",
            "workspace_root": str(workspace),
        }
        self._patch_project(monkeypatch, cfg)

        result = indexer.list_doc_sources(project_name="ACME")
        assert result["default_source_id"] == "project-docs:docs"
        assert any(s["id"] == "project-docs:docs" for s in result["sources"])

    def test_project_docs_index_is_nested(self, tmp_path, monkeypatch):
        """Los docs del proyecto se devuelven como árbol de carpetas."""
        workspace = tmp_path / "workspace"
        _write_md(workspace / "docs" / "api" / "contracts.md", "# Contracts\n\n## V1\n")
        cfg = {
            "name": "ACME",
            "display_name": "ACME App",
            "workspace_root": str(workspace),
        }
        self._patch_project(monkeypatch, cfg)

        result = indexer.build_project_docs_index(
            project_name="ACME",
            source_id="project-docs:docs",
        )
        root = result["roots"][0]
        api_folder = root["children"][0]
        assert api_folder["kind"] == "folder"
        assert api_folder["label"] == "api"
        assert api_folder["children"][0]["label"] == "contracts.md"
        assert api_folder["children"][0]["headings"][0]["text"] == "Contracts"

    def test_read_project_doc_content(self, tmp_path, monkeypatch):
        """Lee contenido desde la carpeta docs seleccionada del proyecto."""
        workspace = tmp_path / "workspace"
        _write_md(workspace / "docs" / "guide.md", "# Guide\n\nContenido proyecto.")
        cfg = {
            "name": "ACME",
            "display_name": "ACME App",
            "workspace_root": str(workspace),
        }
        self._patch_project(monkeypatch, cfg)

        content = indexer.read_project_doc_content(
            "guide.md",
            project_name="ACME",
            source_id="project-docs:docs",
        )
        assert "Contenido proyecto." in content

    def test_project_doc_traversal_blocked(self, tmp_path, monkeypatch):
        """La lectura de docs del proyecto bloquea path traversal."""
        workspace = tmp_path / "workspace"
        _write_md(workspace / "docs" / "guide.md", "# Guide\n")
        cfg = {
            "name": "ACME",
            "display_name": "ACME App",
            "workspace_root": str(workspace),
        }
        self._patch_project(monkeypatch, cfg)

        with pytest.raises(ValueError, match="path_traversal_blocked"):
            indexer.read_project_doc_content(
                "../secret.md",
                project_name="ACME",
                source_id="project-docs:docs",
            )

    def test_configured_docs_paths_override_autodiscovery(self, tmp_path, monkeypatch):
        """docs_paths explícitos se exponen como Técnica / Funcional y evitan autodiscovery."""
        workspace = tmp_path / "workspace"
        technical = tmp_path / "client-docs" / "technical"
        functional = tmp_path / "client-docs" / "functional"
        _write_md(workspace / "docs" / "legacy.md", "# Legacy\n")
        _write_md(technical / "architecture.md", "# Architecture\n")
        _write_md(functional / "manual.md", "# Manual\n")
        cfg = {
            "name": "ACME",
            "display_name": "ACME App",
            "workspace_root": str(workspace),
            "docs_paths": {
                "technical": str(technical),
                "functional": str(functional),
            },
        }
        self._patch_project(monkeypatch, cfg)

        result = indexer.list_doc_sources(project_name="ACME")
        source_ids = [s["id"] for s in result["sources"]]
        assert result["default_source_id"] == "project-docs:technical"
        assert "project-docs:technical" in source_ids
        assert "project-docs:functional" in source_ids
        assert "project-docs:docs" not in source_ids

    def test_configured_docs_index_uses_backend_label(self, tmp_path, monkeypatch):
        """El root del índice usa el label de la fuente configurada."""
        workspace = tmp_path / "workspace"
        technical = tmp_path / "client-docs" / "technical"
        _write_md(technical / "architecture.md", "# Architecture\n")
        cfg = {
            "name": "ACME",
            "display_name": "ACME App",
            "workspace_root": str(workspace),
            "docs_paths": {"technical": str(technical), "functional": ""},
        }
        self._patch_project(monkeypatch, cfg)

        result = indexer.build_project_docs_index(
            project_name="ACME",
            source_id="project-docs:technical",
        )
        root = result["roots"][0]
        assert root["label"] == "📐 Técnica"
        assert root["children"][0]["label"] == "architecture.md"
