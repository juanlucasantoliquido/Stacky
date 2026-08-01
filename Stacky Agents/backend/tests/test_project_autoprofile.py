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

Colisión de schema (defecto vivo, ajeno al plan 42): el draft emitía
schema_version=2 mientras services/client_profile.SCHEMA_VERSION sigue en 1, y
validate_client_profile rechaza toda versión mayor a la soportada. Como el
draft es "parcial apto para merge con el perfil base" (docstring del módulo),
ese 2 viajaba al client_profile y save_client_profile lo rechazaba con 400.

8. test_draft_profile_valida_contra_client_profile   (ida y vuelta)
9. test_draft_profile_declara_el_schema_de_client_profile
10. test_validador_sigue_rechazando_schema_futuro    (guarda del rechazo legítimo)
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


# ---------------------------------------------------------------------------
# Colisión de schema_version entre el autoprofiler y el client_profile.
# IDA Y VUELTA: el perfil se GENERA con el autoprofiler y se valida con el
# validador real. Fabricar el dict a mano probaría la suposición, no el bug.
# ---------------------------------------------------------------------------

def _fixture_docs_root(tmp_path):
    """Árbol de docs realista: técnica con índice y un heading de proceso."""
    tech = tmp_path / "tecnica"
    tech.mkdir()
    (tech / "INDEX_TECNICO.md").write_text(
        "# Índice Técnico\n\n## Cierre batch nocturno\n", encoding="utf-8"
    )
    func = tmp_path / "funcional"
    func.mkdir()
    (func / "INDEX_ONLINE.md").write_text("# Índice Online\n", encoding="utf-8")
    return tmp_path


def test_draft_profile_valida_contra_client_profile(tmp_path):
    """El draft generado por el autoprofiler DEBE pasar validate_client_profile.

    Con schema_version=2 hardcodeado, el validador cortaba en
    `schema_version N más nuevo que el soportado` y save_client_profile
    devolvía 400 al mergearlo al perfil del proyecto.
    """
    from services.client_profile import validate_client_profile
    from services.project_autoprofile import draft_profile_from_docs

    draft = draft_profile_from_docs(_fixture_docs_root(tmp_path))

    # GUARDA POSITIVA: el draft declara la versión de schema. Sin este assert,
    # borrar la clave haría pasar la validación por AUSENCIA y no por acuerdo.
    assert "schema_version" in draft, (
        "el draft dejó de declarar schema_version: la validación de abajo "
        "pasaría por ausencia, no porque los schemas coincidan"
    )
    assert isinstance(draft["schema_version"], int)

    result = validate_client_profile(draft)
    assert result.ok, f"el draft del autoprofiler no valida: {result.errors}"
    assert not result.errors


def test_draft_profile_declara_el_schema_de_client_profile(tmp_path):
    """El draft declara EXACTAMENTE el schema de client_profile, no un literal.

    Se asierta contra la constante importada (no contra el número 1) para que
    el día que client_profile suba de versión, este test agarre la divergencia
    en lugar de congelarla.
    """
    from services.client_profile import SCHEMA_VERSION
    from services.project_autoprofile import draft_profile_from_docs

    draft = draft_profile_from_docs(_fixture_docs_root(tmp_path))
    assert draft["schema_version"] == SCHEMA_VERSION


def test_validador_sigue_rechazando_schema_futuro(tmp_path):
    """El arreglo NO puede ser aflojar el validador: una versión realmente
    futura se sigue rechazando."""
    from services.client_profile import SCHEMA_VERSION, validate_client_profile
    from services.project_autoprofile import draft_profile_from_docs

    draft = draft_profile_from_docs(_fixture_docs_root(tmp_path))
    draft["schema_version"] = SCHEMA_VERSION + 1

    result = validate_client_profile(draft)
    assert not result.ok
    assert any("más nuevo que el soportado" in e for e in result.errors), result.errors
