"""tests/test_plan131_incident_agent.py — Plan 131 F2.

Agente unificado IncidentAnalyst (clase + prompt) y bootstrap del `.agent.md`
(C10: sincronía con _AGENT_TEMPLATE_MD + fallback frozen).
"""
from pathlib import Path

import pytest

_REQUIRED_HEADINGS = (
    "RESUMEN EJECUTIVO",
    "CONTEXTO DE NEGOCIO",
    "ANALISIS FUNCIONAL",
    "ANALISIS TECNICO",
    "PASOS DE REPRODUCCION",
    "CRITERIOS DE ACEPTACION",
    "ARCHIVOS Y MODULOS PROBABLES",
    "EPICA RELACIONADA",
    "PRIORIDAD Y ESTIMACION",
)


def test_agent_registered_with_incident_type():
    import agents
    agent = agents.get("incident")
    assert agent is not None
    assert agent.type == "incident"
    prompt = agent.system_prompt()
    assert "EPICA RELACIONADA" in prompt
    assert "PASOS DE REPRODUCCION" in prompt


def test_list_agents_includes_incident_without_breaking_shape():
    import agents
    described = agents.list_agents()
    incident_entries = [d for d in described if d["type"] == "incident"]
    assert len(incident_entries) == 1
    entry = incident_entries[0]
    assert {"type", "name", "description", "icon", "inputs", "outputs", "default_blocks"} <= set(entry)


def test_ensure_incident_agent_file_creates_from_repo_template(tmp_path, monkeypatch):
    from services import incident_context
    monkeypatch.setattr(incident_context, "stacky_agents_dir", lambda: tmp_path)
    dest = incident_context.ensure_incident_agent_file()
    assert dest == tmp_path / "IncidentAnalyst.agent.md"
    assert dest.exists()
    assert "stacky_agent_type: incident" in dest.read_text(encoding="utf-8")


def test_ensure_incident_agent_file_does_not_overwrite_existing(tmp_path, monkeypatch):
    from services import incident_context
    monkeypatch.setattr(incident_context, "stacky_agents_dir", lambda: tmp_path)
    dest = tmp_path / "IncidentAnalyst.agent.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("CONTENIDO EDITADO POR EL OPERADOR", encoding="utf-8")

    result = incident_context.ensure_incident_agent_file()
    assert result == dest
    assert dest.read_text(encoding="utf-8") == "CONTENIDO EDITADO POR EL OPERADOR"


def test_committed_agent_md_byte_identical_to_template_and_has_headings():
    from services import incident_context
    backend_root = Path(__file__).resolve().parent.parent
    committed = backend_root / "agents" / "IncidentAnalyst.agent.md"
    assert committed.exists()
    committed_text = committed.read_text(encoding="utf-8")
    assert committed_text == incident_context._AGENT_TEMPLATE_MD
    for heading in _REQUIRED_HEADINGS:
        assert heading in committed_text, f"heading faltante: {heading}"


def test_ensure_incident_agent_file_frozen_fallback_writes_template(tmp_path, monkeypatch):
    """C10 — deploy congelado: el .agent.md del repo no es legible → usa
    _AGENT_TEMPLATE_MD directo (constante bundleada)."""
    from services import incident_context
    monkeypatch.setattr(incident_context, "stacky_agents_dir", lambda: tmp_path)

    def _raise_oserror(self, *a, **kw):
        raise OSError("simulated frozen deploy: repo template unreachable")

    monkeypatch.setattr(Path, "read_text", _raise_oserror)

    dest = incident_context.ensure_incident_agent_file()
    assert dest.exists()
    # read_text está parcheado a nivel global; leemos en bytes para no chocar.
    assert dest.read_bytes().decode("utf-8") == incident_context._AGENT_TEMPLATE_MD
