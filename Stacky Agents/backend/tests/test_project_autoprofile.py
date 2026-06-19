"""Plan 42 F5 — Auto-perfilado de proyecto desde docs locales.

Tests con árbol fixture en tmp_path (NUNCA el repo real).
Criterio de no-inventar: con árbol vacío → process_catalog vacío.

Tests:
1. test_empty_docs_root_returns_empty_catalog
2. test_no_dirs_match_pattern
3. test_detects_technical_master_index
4. test_extracts_process_from_headings
5. test_no_invention_with_no_process_headings
6. test_detects_functional_online
7. test_endpoint_returns_404_when_flag_off
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ---------------------------------------------------------------------------
# Tests de draft_profile_from_docs (función pura, usa árbol tmp_path)
# ---------------------------------------------------------------------------

def test_empty_docs_root_returns_empty_catalog(tmp_path):
    """Árbol vacío → catalogo de procesos vacío (no se inventa nada)."""
    from services.project_autoprofile import draft_profile_from_docs
    result = draft_profile_from_docs(tmp_path)
    assert result["process_catalog"] == []
    assert result["docs_indexes"] == {}


def test_no_dirs_match_pattern(tmp_path):
    """Directorio que no matchea técnica/funcional → sin índices."""
    from services.project_autoprofile import draft_profile_from_docs
    (tmp_path / "documentos").mkdir()
    (tmp_path / "documentos" / "readme.md").write_text("# Readme")
    result = draft_profile_from_docs(tmp_path)
    assert result["docs_indexes"] == {}
    assert result["process_catalog"] == []


def test_detects_technical_master_index(tmp_path):
    """Un subdir 'tecnica' con un archivo INDEX.md → docs_indexes.technical_master apunta a él."""
    from services.project_autoprofile import draft_profile_from_docs
    tech = tmp_path / "tecnica"
    tech.mkdir()
    (tech / "INDEX_TECNICO.md").write_text("# Índice Técnico\n## Módulo A\n")
    result = draft_profile_from_docs(tmp_path)
    assert "technical_master" in result["docs_indexes"]
    assert "INDEX_TECNICO.md" in result["docs_indexes"]["technical_master"]


def test_extracts_process_from_headings(tmp_path):
    """Heading h2 con palabra 'batch' → proceso en catalog (nombre real del heading)."""
    from services.project_autoprofile import draft_profile_from_docs
    tech = tmp_path / "tecnica"
    tech.mkdir()
    md = tech / "procesos.md"
    md.write_text(
        "# Procesos del sistema\n\n"
        "## Cierre batch nocturno\n\n"
        "Descripción del proceso.\n\n"
        "### Facturación batch mensual\n\n"
        "Otro proceso.\n"
    )
    result = draft_profile_from_docs(tmp_path)
    names = [p["name"] for p in result["process_catalog"]]
    assert any("batch" in n.lower() for n in names), f"Expected batch in {names}"
    # Verificar que no se inventan nombres: cada name extraído aparece en el texto fuente.
    md_text = md.read_text(encoding="utf-8", errors="replace")
    assert all(n in md_text for n in names), (
        f"Nombres inventados detectados: {[n for n in names if n not in md_text]}"
    )


def test_no_invention_with_no_process_headings(tmp_path):
    """Un .md sin headings de proceso → catalog vacío (no se inventa)."""
    from services.project_autoprofile import draft_profile_from_docs
    tech = tmp_path / "técnica"
    tech.mkdir()
    (tech / "modulo.md").write_text(
        "# Módulo de autenticación\n\n## Descripción\n\nSin procesos batch.\n"
    )
    result = draft_profile_from_docs(tmp_path)
    assert result["process_catalog"] == []


def test_detects_functional_online(tmp_path):
    """Un subdir 'funcional' con archivo INDEX_ONLINE.md → docs_indexes.functional_online."""
    from services.project_autoprofile import draft_profile_from_docs
    func = tmp_path / "funcional"
    func.mkdir()
    (func / "INDEX_ONLINE.md").write_text("# Índice Online\n")
    result = draft_profile_from_docs(tmp_path)
    assert "functional_online" in result["docs_indexes"]
    assert "INDEX_ONLINE.md" in result["docs_indexes"]["functional_online"]


# ---------------------------------------------------------------------------
# Test de endpoint (flag OFF → 404)
# ---------------------------------------------------------------------------

def test_endpoint_returns_404_when_flag_off(monkeypatch):
    """Con STACKY_PROJECT_AUTOPROFILE_ENABLED=false → 404 feature_disabled."""
    monkeypatch.setenv("STACKY_PROJECT_AUTOPROFILE_ENABLED", "false")
    from app import create_app
    app = create_app()
    with app.test_client() as client:
        resp = client.get(
            "/api/agents/autoprofile/mi-proyecto",
            headers={"X-User-Email": "test@test.com"},
        )
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["error"] == "feature_disabled"
