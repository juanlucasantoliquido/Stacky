"""
Tests para:
  - El endpoint POST /api/tickets/<id>/qa_action (transiciones manuales post-rechazo).
  - El fallback de _extract_qa_findings cuando el QA no respeta el formato de lista.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# ── _extract_qa_findings fallback ──────────────────────────────────────────

class TestExtractQaFindingsFallback:
    def test_lista_estructurada_tiene_prioridad(self):
        from output_validator import _extract_qa_findings
        content = """
# Reporte QA
Veredicto: RECHAZADO

## Observaciones
- Falla en la validación de email
- No se guarda el teléfono
"""
        findings = _extract_qa_findings(content)
        assert len(findings) == 2
        assert "validación de email" in findings[0]
        assert not any("Motivo capturado" in f for f in findings)

    def test_fallback_captura_parrafo_post_rechazado(self):
        """Sin sección ## Observaciones, debe capturar el párrafo tras 'RECHAZADO'."""
        from output_validator import _extract_qa_findings
        content = """
# Reporte QA
Veredicto: RECHAZADO
La implementación no maneja correctamente el caso de cliente dado de baja:
la grilla muestra el teléfono aún cuando se marca como borrado.
Se debe filtrar por el flag activo antes de mostrarlo.

Criterios evaluados: 3/5.
"""
        findings = _extract_qa_findings(content)
        assert len(findings) == 1
        assert findings[0].startswith("[Motivo capturado sin formato de lista]")
        assert "cliente dado de baja" in findings[0]

    def test_fallback_sentinel_cuando_ni_parrafo_hay(self):
        """RECHAZADO presente pero sin texto → sentinel."""
        from output_validator import _extract_qa_findings
        content = "# Reporte QA\n\nRECHAZADO\n\n## Otra sección sin nada\n"
        findings = _extract_qa_findings(content)
        assert len(findings) == 1
        assert "no documentó el motivo" in findings[0]

    def test_no_rechazado_no_activa_fallback(self):
        """Si el veredicto no es RECHAZADO, no se fuerza un finding."""
        from output_validator import _extract_qa_findings
        content = "# Reporte QA\nVeredicto: APROBADO\n\nTodo OK."
        findings = _extract_qa_findings(content)
        assert findings == []

    def test_truncado_si_es_muy_largo(self):
        from output_validator import _extract_qa_findings
        long_paragraph = "A" * 1000
        content = f"# Reporte\nRECHAZADO\n{long_paragraph}\n"
        findings = _extract_qa_findings(content)
        assert len(findings) == 1
        # El finding tiene prefijo [Motivo ...] + texto truncado con "..."
        assert findings[0].endswith("...")


# ── Endpoint qa_action ─────────────────────────────────────────────────────

@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    """
    Carga dashboard_server con un runtime aislado y sin watchers.
    Mantenemos la configuración mínima para que `_get_runtime` devuelva paths
    apuntando a tmp_path.
    """
    monkeypatch.setenv("STACKY_TEST_MODE", "1")

    # Armamos un mini proyecto en tmp_path
    project_dir = tmp_path / "projects" / "TEST"
    (project_dir / "tickets" / "asignada").mkdir(parents=True)
    (project_dir / "state").mkdir(parents=True)

    # Stub mínimo para _get_runtime ANTES de importar el server
    import dashboard_server as ds

    state_path = project_dir / "state" / "seen_tickets.json"
    # Seed state.json con un ticket rechazado
    state_path.write_text(json.dumps({
        "tickets": {
            "1001": {"estado": "tester_completado",
                     "last_qa_verdict": "RECHAZADO",
                     "rework_count": 0},
            "1002": {"estado": "dev_en_proceso"},
        },
        "last_run": None,
    }), encoding="utf-8")

    def fake_runtime():
        return {
            "name":          "TEST",
            "tickets_base":  str(project_dir / "tickets"),
            "workspace_root": str(tmp_path),
            "state_path":    str(state_path),
            "agents":        {},
        }

    monkeypatch.setattr(ds, "_get_runtime", fake_runtime)

    # Forzar que pipeline_events.emit sea no-op en los tests
    import pipeline_events as pe
    monkeypatch.setattr(pe, "emit", lambda **k: None)

    ds.app.testing = True
    return ds.app.test_client(), state_path


class TestQaActionEndpoint:
    def test_transicion_valida_reenviar_pm(self, flask_app):
        client, state_path = flask_app
        r = client.post("/api/tickets/1001/qa_action",
                        json={"action": "reenviar_pm"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["to_state"] == "pm_revision_en_proceso"
        # Verificar persistencia en state.json
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["tickets"]["1001"]["estado"] == "pm_revision_en_proceso"

    def test_transicion_valida_volver_dev(self, flask_app):
        client, state_path = flask_app
        r = client.post("/api/tickets/1001/qa_action",
                        json={"action": "volver_dev"})
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["to_state"] == "qa_rework"

    def test_transicion_invalida_desde_estado_incorrecto(self, flask_app):
        """#1002 está en 'dev_en_proceso' — no debe aceptar acciones QA."""
        client, _ = flask_app
        r = client.post("/api/tickets/1002/qa_action",
                        json={"action": "reenviar_pm"})
        assert r.status_code == 400
        data = r.get_json()
        assert data["ok"] is False
        assert "transición inválida" in data["error"] or "inválida" in data["error"]
        assert data["current_state"] == "dev_en_proceso"

    def test_accion_desconocida_devuelve_400(self, flask_app):
        client, _ = flask_app
        r = client.post("/api/tickets/1001/qa_action",
                        json={"action": "hacer_magia"})
        assert r.status_code == 400
        assert "valid_actions" in r.get_json()

    def test_ticket_inexistente_devuelve_404(self, flask_app):
        client, _ = flask_app
        r = client.post("/api/tickets/9999/qa_action",
                        json={"action": "reenviar_pm"})
        assert r.status_code == 404

    def test_missing_action_devuelve_400(self, flask_app):
        client, _ = flask_app
        r = client.post("/api/tickets/1001/qa_action", json={})
        assert r.status_code == 400

    def test_endpoint_valid_transitions_devuelve_tabla(self, flask_app):
        client, _ = flask_app
        r = client.get("/api/pipeline/valid_transitions")
        assert r.status_code == 200
        data = r.get_json()
        assert "transitions" in data
        # Algunos keys canónicos
        assert "qa_rework" in data["transitions"]
        assert data["transitions"]["qa_rework"] == "dev_rework_en_proceso"
