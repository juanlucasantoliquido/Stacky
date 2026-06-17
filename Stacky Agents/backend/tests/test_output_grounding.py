"""G1.2 — Tests del grounding determinista de referencias del output.

Tests TDD para services/grounding.py.
Valida: extracción de rutas/IDs, exclusión de rutas de creación, flag OFF.
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures: parchea el flag directamente en config (evita contaminación de caché)
# ---------------------------------------------------------------------------

@pytest.fixture
def grounding_enabled(monkeypatch):
    import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod.config, "STACKY_OUTPUT_GROUNDING_ENABLED", True)

@pytest.fixture
def grounding_disabled(monkeypatch):
    import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod.config, "STACKY_OUTPUT_GROUNDING_ENABLED", False)


# ---------------------------------------------------------------------------
# Imports bajo test
# ---------------------------------------------------------------------------

def _check(text: str, repo_root=None, ado_resolver=None):
    from services.grounding import check_references
    return check_references(text, repo_root=repo_root, ado_resolver=ado_resolver)


# ---------------------------------------------------------------------------
# Flag OFF — byte-idéntico
# ---------------------------------------------------------------------------


class TestGroundingFlagOff:
    def test_flag_off_returns_clean(self, grounding_disabled):
        """Con flag OFF, check_references devuelve resultado limpio (sin checks)."""
        result = _check("modificar `src/main.py` — ver el archivo `src/utils.py`")
        assert result.clean is True
        assert result.checked_paths == 0
        assert result.checked_ids == 0


# ---------------------------------------------------------------------------
# Extracción de rutas en contexto de modificación
# ---------------------------------------------------------------------------


class TestGroundingUnresolvedPaths:
    def test_modify_nonexistent_path_marked(self, tmp_path, grounding_enabled):
        """Ruta en 'modificar X' que no existe → unresolved_paths."""
        result = _check(
            "Hay que modificar `src/controllers/user.py` para agregar la validación.",
            repo_root=tmp_path,  # directorio vacío → archivo no existe
        )
        assert "src/controllers/user.py" in result.unresolved_paths

    def test_existing_file_not_marked(self, tmp_path, grounding_enabled):
        """Ruta de archivo existente → NO en unresolved_paths."""
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("# code", encoding="utf-8")
        result = _check(
            "modificar `src/main.py` para agregar la feature.",
            repo_root=tmp_path,
        )
        assert "src/main.py" not in result.unresolved_paths

    def test_create_path_not_marked(self, tmp_path, grounding_enabled):
        """Ruta en 'crear X' → NO marcada como no anclada (falso positivo)."""
        result = _check(
            "Crear el archivo `src/services/new_service.py` con la interfaz.",
            repo_root=tmp_path,
        )
        assert "src/services/new_service.py" not in result.unresolved_paths

    def test_output_limpio_sin_marcas(self, tmp_path, grounding_enabled):
        """Output sin referencias de archivos → GroundingResult limpio."""
        result = _check(
            "Se completó la tarea correctamente. El sistema funciona.",
            repo_root=tmp_path,
        )
        assert result.clean is True
        assert result.unresolved_paths == []
        assert result.unresolved_ids == []

    def test_to_metadata_estructura(self, tmp_path, grounding_enabled):
        """to_metadata() devuelve dict con clave 'grounding'."""
        result = _check(
            "modificar `src/missing.py`.",
            repo_root=tmp_path,
        )
        meta = result.to_metadata()
        assert "grounding" in meta
        assert "unresolved_paths" in meta["grounding"]
        assert "unresolved_ids" in meta["grounding"]


# ---------------------------------------------------------------------------
# Extracción de IDs ADO
# ---------------------------------------------------------------------------


class TestGroundingUnresolvedIds:
    def test_unresolved_id_marked(self, grounding_enabled):
        """ID que no resuelve → marcado en unresolved_ids."""
        def _resolver(id_str: str) -> bool:
            return False  # ningún ID existe

        result = _check(
            "El parent-id es #12345, ver work-item #67890.",
            ado_resolver=_resolver,
        )
        assert len(result.unresolved_ids) > 0

    def test_resolved_id_not_marked(self, grounding_enabled):
        """ID que resuelve → NO en unresolved_ids."""
        def _resolver(id_str: str) -> bool:
            return True  # todos existen

        result = _check(
            "work-item #12345 tiene el requerimiento.",
            ado_resolver=_resolver,
        )
        assert "12345" not in result.unresolved_ids

    def test_resolver_error_skips_id(self, grounding_enabled):
        """Si el resolver lanza excepción → ID no marcado (fail-open)."""
        def _resolver_error(id_str: str) -> bool:
            raise ConnectionError("ADO down")

        result = _check(
            "work-item #12345 tiene el requerimiento.",
            ado_resolver=_resolver_error,
        )
        # No debe marcar como no anclado ante error transitorio.
        assert "12345" not in result.unresolved_ids


# ---------------------------------------------------------------------------
# Con REPAIR=true y Q1.1 disponible → pase correctivo anotado
# ---------------------------------------------------------------------------


class TestGroundingRepair:
    def test_repair_flag_off_only_annotates(self, tmp_path, grounding_enabled):
        """Sin REPAIR flag: solo anota, sin pase correctivo."""
        result = _check(
            "modificar `src/missing.py`.",
            repo_root=tmp_path,
        )
        # El resultado existe pero no hay repair_attempted.
        assert "src/missing.py" in result.unresolved_paths

    def test_repair_flag_on_no_q11_only_annotates(self, tmp_path, grounding_enabled, monkeypatch):
        """REPAIR=true pero Q1.1 no disponible → solo anota."""
        import config as _cfg_mod
        monkeypatch.setattr(_cfg_mod.config, "STACKY_OUTPUT_GROUNDING_REPAIR", True)
        monkeypatch.setattr(_cfg_mod.config, "STACKY_CRITERIA_REPAIR_ENABLED", False)
        result = _check(
            "modificar `src/missing.py`.",
            repo_root=tmp_path,
        )
        # Sin Q1.1: solo anota.
        assert "src/missing.py" in result.unresolved_paths


# ---------------------------------------------------------------------------
# Helpers de extracción internos
# ---------------------------------------------------------------------------


class TestGroundingInternals:
    def test_extract_read_paths_basic(self):
        """_extract_read_paths detecta rutas en contexto de modificación."""
        from services.grounding import _extract_read_paths
        paths = _extract_read_paths("modificar `src/app.py` y ver `lib/utils.js`")
        assert "src/app.py" in paths

    def test_extract_create_paths_basic(self):
        """_extract_create_paths detecta rutas de creación."""
        from services.grounding import _extract_create_paths
        paths = _extract_create_paths("Crear el archivo `src/nuevo.py` con la clase.")
        assert "src/nuevo.py" in paths

    def test_create_excluded_from_read(self):
        """Las rutas de creación no aparecen en las de lectura (exclusión)."""
        from services.grounding import _extract_create_paths, _extract_read_paths
        text = "Crear `nuevo.py`. Modificar `existente.py`."
        create = _extract_create_paths(text)
        read = _extract_read_paths(text)
        # La exclusión ocurre en check_references, pero verificamos los conjuntos
        assert "existente.py" in read
        assert "nuevo.py" in create

    def test_looks_like_file_path_rejects_short(self):
        """Cadenas cortas sin extensión/separador → False."""
        from services.grounding import _looks_like_file_path
        assert _looks_like_file_path("ab") is False
        assert _looks_like_file_path("") is False

    def test_looks_like_file_path_accepts_with_ext(self):
        """Cadenas con extensión → True."""
        from services.grounding import _looks_like_file_path
        assert _looks_like_file_path("app.py") is True
        assert _looks_like_file_path("src/utils.ts") is True
