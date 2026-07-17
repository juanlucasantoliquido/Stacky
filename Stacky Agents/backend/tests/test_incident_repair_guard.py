"""tests/test_incident_repair_guard.py — Plan 160 F0.

Guard anti-narración del pase correctivo del resolutor de incidencias.
Espejo de tests/test_epic_narration_guard.py (predicado de disparo +
flag de gobierno), pero para _looks_like_incident/_extract_epic_html_raw
y el agent_type=="incident" del pase correctivo embebido en
claude_code_cli_runner.py. NO arranca subprocesos ni toca red/DB real:
prueba la lógica pura + endpoints con run mockeado, al estilo
test_stall_watchdog.
"""
from __future__ import annotations


NARRATION_OUTPUT = (
    "Voy a leer los archivos adjuntos de la incidencia.\n\n"
    "Rol adoptado: Analista de Incidencias.\n\n"
    "Ya reuní el contexto de negocio y funcional. Genero el desglose "
    "y lo guardo en el archivo de salida."
)

VALID_INCIDENT_HTML = (
    "<h1>Error al guardar cliente duplicado</h1>"
    "<h2>RESUMEN EJECUTIVO</h2><p>Resumen.</p>"
    "<h2>ANALISIS FUNCIONAL</h2><p>Detalle funcional.</p>"
    "<h2>ANALISIS TECNICO</h2><p>Detalle técnico.</p>"
    "<h2>PASOS DE REPRODUCCION</h2><p>1. Paso uno.</p>"
    "<h2>CRITERIOS DE ACEPTACION</h2><p>Criterio uno.</p>"
)

REPAIR_META_SENT = {"attempted": True, "reason": "narration_not_incident", "sent": True}


def _incident_repair_should_fire(current_output: str) -> bool:
    """Espejo de la condición de disparo del pase correctivo de incidencia
    en claude_code_cli_runner.py (Plan 160 F0)."""
    from api.tickets import _extract_epic_html_raw, _looks_like_incident

    return not _looks_like_incident(_extract_epic_html_raw(current_output))


def _make_fake_run(output_text: str):
    class _FakeRun:
        output = output_text
        project_name = "Pacifico"

        @property
        def metadata_dict(self):
            return {"incident_repair": dict(REPAIR_META_SENT)}

    return _FakeRun()


def test_incident_repair_fires_on_narration():
    """Narración pura como output del último turno -> se pide el reintento."""
    assert _incident_repair_should_fire(NARRATION_OUTPUT) is True


def test_incident_repair_does_not_fire_on_valid_incident():
    """Output ya es un desglose válido (>=3 de 4 secciones + heading) -> NO
    se reintenta (no malgastar turnos/costo)."""
    assert _incident_repair_should_fire(VALID_INCIDENT_HTML) is False


def test_incident_repair_send_message_only_on_narration():
    """Simula el closure: send_fn se invoca SOLO ante narración, una vez."""
    sent: list[str] = []

    def fake_send(msg: str) -> bool:
        sent.append(msg)
        return True

    if _incident_repair_should_fire(NARRATION_OUTPUT):
        fake_send("Re-emití AHORA ... EXCLUSIVAMENTE el HTML del desglose ...")
    assert len(sent) == 1
    assert "HTML del desglose" in sent[0]

    sent.clear()
    if _incident_repair_should_fire(VALID_INCIDENT_HTML):
        fake_send("no debería enviarse")
    assert sent == []


def test_incident_repair_flag_exists_default_on():
    """El flag de gobierno existe y viene ON por default (mismo patrón que
    STACKY_EPIC_REPAIR_ENABLED)."""
    from config import config

    assert isinstance(config.STACKY_INCIDENT_REPAIR_ENABLED, bool)
    assert config.STACKY_INCIDENT_REPAIR_ENABLED is True


def test_incident_preview_repair_field_present_when_repaired(monkeypatch):
    """GET /incident-preview: si metadata["incident_repair"] existe en el
    run, el campo "repair" del JSON de fallo lo refleja (diagnóstico
    accionable, Plan 160 F0). Fallo sigue en incident_not_in_output."""
    from services import incident_store

    incident = incident_store.create_incident(text="algo se rompió", files=[])

    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda *a, **k: _make_fake_run(NARRATION_OUTPUT))
    monkeypatch.setattr(t_mod.config.config, "STACKY_INCIDENT_RESOLVER_ENABLED", True)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    data = resp.get_json()
    assert data["error"] == "incident_not_in_output"
    assert data["repair"] == REPAIR_META_SENT


def test_incident_preview_ok_includes_repair_field(monkeypatch):
    """[ADICIÓN ARQUITECTO] GET /incident-preview OK: si el run fue reparado
    (metadata["incident_repair"].attempted) y el HTML quedó válido, la
    respuesta OK también incluye "repair" — el modal muestra la nota de
    transparencia (cero acciones automáticas invisibles)."""
    from services import incident_store

    incident = incident_store.create_incident(text="algo se rompió", files=[])

    import api.tickets as t_mod
    monkeypatch.setattr(t_mod, "_get_run_for_preview", lambda *a, **k: _make_fake_run(VALID_INCIDENT_HTML))
    monkeypatch.setattr(t_mod.config.config, "STACKY_INCIDENT_RESOLVER_ENABLED", True)

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    resp = client.get(f"/api/tickets/incident-preview?execution_id=1&incident_id={incident['id']}")
    data = resp.get_json()
    assert data["ok"] is True
    assert data["repair"] == REPAIR_META_SENT
