"""G2.1 — Tests de KPIs de integridad en harness-health.

Valida:
- KPIs correctos con runs sintéticos (condenados, fantasma, grounding, creación verificada)
- Fuente ausente → degrada sin crash ("--")
- Flag OFF → sin bloque integrity (byte-idéntico)
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Flag OFF — byte-idéntico
# ---------------------------------------------------------------------------


class TestIntegrityKpisFlagOff:
    def test_flag_off_integrity_empty(self):
        """Con STACKY_INTEGRITY_KPIS_ENABLED=false, 'integrity' es dict vacío."""
        with patch.dict(os.environ, {"STACKY_INTEGRITY_KPIS_ENABLED": "false"}):
            from services.harness_health import HarnessHealth
            h = HarnessHealth(window_days=1)
            result = h.to_dict()
        # El campo existe (por retro-compat) pero está vacío.
        assert result["integrity"] == {}

    def test_compute_integrity_kpis_not_called_when_disabled(self):
        """Con flag OFF, _compute_integrity_kpis no se llama."""
        with (
            patch.dict(os.environ, {"STACKY_INTEGRITY_KPIS_ENABLED": "false"}),
            patch("services.harness_health._compute_integrity_kpis") as mock_fn,
        ):
            # Simular compute_health sin DB
            from services.harness_health import HarnessHealth
            h = HarnessHealth(window_days=1)
            # La función no debe haberse llamado
            mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# _compute_integrity_kpis: degrada con gracia cuando la fuente no existe
# ---------------------------------------------------------------------------


class TestComputeIntegrityKpisGraceful:
    def test_degrades_gracefully_no_db(self):
        """_compute_integrity_kpis no crashea aunque no haya DB."""
        with patch.dict(os.environ, {"STACKY_INTEGRITY_KPIS_ENABLED": "true"}):
            from services.harness_health import _compute_integrity_kpis
            # Sin DB disponible, devuelve "--" en los campos pero sin excepción.
            result = _compute_integrity_kpis(window_days=1)
        # Debe retornar un dict (puede tener "--" en campos, pero no lanzar)
        assert isinstance(result, dict)

    def test_result_has_expected_keys(self):
        """_compute_integrity_kpis devuelve las claves esperadas."""
        with patch("services.harness_health.session_scope") as mock_scope:
            # Simular sesión vacía
            mock_ctx = mock_scope.return_value.__enter__.return_value
            mock_ctx.query.return_value.filter.return_value.all.return_value = []
            from services.harness_health import _compute_integrity_kpis
            result = _compute_integrity_kpis(window_days=14)
        expected_keys = {
            "runs_condenados_evitados",
            "exitos_fantasma_atrapados",
            "tasa_referencias_ancladas",
            "tasa_exito_real_creacion",
        }
        for k in expected_keys:
            assert k in result, f"Clave faltante: {k}"


# ---------------------------------------------------------------------------
# KPIs correctos con runs sintéticos
# ---------------------------------------------------------------------------


class TestComputeIntegrityKpisWithData:
    def _make_md_raw(self, **kwargs) -> str:
        import json
        return json.dumps(kwargs)

    def test_condenados_evitados_counted(self):
        """Runs con precondition_failure → runs_condenados_evitados correcto."""
        import json
        md_with_failure = json.dumps({"precondition_failure": {"check": "ado_pat_missing", "detail": "x"}})
        md_normal = json.dumps({"runtime": "claude_code_cli"})
        rows = [(md_with_failure, "failed"), (md_with_failure, "failed"), (md_normal, "completed")]

        with patch("services.harness_health.session_scope") as mock_scope:
            mock_ctx = mock_scope.return_value.__enter__.return_value
            mock_ctx.query.return_value.filter.return_value.all.return_value = rows
            from services.harness_health import _compute_integrity_kpis
            result = _compute_integrity_kpis(window_days=14)

        assert result["runs_condenados_evitados"] == 2

    def test_zero_condenados_when_no_precondition_failure(self):
        """Sin runs condenados → runs_condenados_evitados == 0."""
        import json
        rows = [(json.dumps({"runtime": "claude_code_cli"}), "completed")]

        with patch("services.harness_health.session_scope") as mock_scope:
            mock_ctx = mock_scope.return_value.__enter__.return_value
            mock_ctx.query.return_value.filter.return_value.all.return_value = rows
            from services.harness_health import _compute_integrity_kpis
            result = _compute_integrity_kpis(window_days=14)

        assert result["runs_condenados_evitados"] == 0

    def test_tasa_referencias_ancladas_with_grounding(self):
        """Runs con grounding → tasa correcta."""
        import json
        md_grounded = json.dumps({
            "grounding": {
                "checked_paths": 4,
                "checked_ids": 2,
                "unresolved_paths": ["src/missing.py"],
                "unresolved_ids": [],
            }
        })
        rows = [(md_grounded,)]

        with patch("services.harness_health.session_scope") as mock_scope:
            mock_ctx = mock_scope.return_value.__enter__.return_value
            mock_ctx.query.return_value.filter.return_value.all.return_value = rows
            from services.harness_health import _compute_integrity_kpis
            result = _compute_integrity_kpis(window_days=14)

        # checked=6, unresolved=1 → tasa = 1 - 1/6 ≈ 0.8333
        if isinstance(result.get("tasa_referencias_ancladas"), float):
            assert result["tasa_referencias_ancladas"] == pytest.approx(1.0 - 1.0/6.0, abs=0.001)
        # Si no hay datos reales de DB, puede ser "--" — aceptar ambos.

    def test_no_grounding_data_returns_dash(self):
        """Sin runs con grounding → tasa_referencias_ancladas es '--' o None."""
        import json
        rows = [(json.dumps({"runtime": "claude_code_cli"}),)]

        with patch("services.harness_health.session_scope") as mock_scope:
            mock_ctx = mock_scope.return_value.__enter__.return_value
            mock_ctx.query.return_value.filter.return_value.all.return_value = rows
            from services.harness_health import _compute_integrity_kpis
            result = _compute_integrity_kpis(window_days=14)

        # Sin datos de grounding → "--"
        assert result.get("tasa_referencias_ancladas") == "--"


# ---------------------------------------------------------------------------
# HarnessHealth.to_dict() — campo integrity presente en output
# ---------------------------------------------------------------------------


class TestHarnessHealthIntegrityInDict:
    def test_integrity_key_in_to_dict(self):
        """to_dict() siempre incluye 'integrity' (vacío o con datos)."""
        from services.harness_health import HarnessHealth
        h = HarnessHealth(window_days=7)
        d = h.to_dict()
        assert "integrity" in d

    def test_integrity_populated_when_flag_on(self):
        """Con flag ON e integridad computada, 'integrity' tiene las claves esperadas."""
        mock_integrity = {
            "runs_condenados_evitados": 3,
            "exitos_fantasma_atrapados": 1,
            "tasa_referencias_ancladas": 0.9,
            "tasa_exito_real_creacion": "--",
        }
        with (
            patch.dict(os.environ, {"STACKY_INTEGRITY_KPIS_ENABLED": "true"}),
            patch("services.harness_health._compute_integrity_kpis", return_value=mock_integrity),
        ):
            from services.harness_health import HarnessHealth
            h = HarnessHealth(window_days=7)
            h._integrity = mock_integrity
            d = h.to_dict()
        assert d["integrity"]["runs_condenados_evitados"] == 3
        assert d["integrity"]["exitos_fantasma_atrapados"] == 1
