"""Plan 209 F3 — compute_and_attach + post-hook de completación.

Gate de scope (flag + user-facing), persistencia correcta en metadata_json
(json.loads → mutar → json.dumps, NUNCA item-assignment sobre el str) y el
registro en el seam runtime-agnóstico `ticket_status.on_execution_end`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import validation_playbook as vp  # noqa: E402

_CATALOG = [{"name": "IncHost", "kind": "batch",
             "purpose": "Asignar obligaciones al host y mostrarlas en el inicio"}]

_HTML_A = f"""<section data-stacky="validation-playbook" data-confidence="0.9">
  <h2>{vp.SECTION_TITLE}</h2>
  <ol><li data-source="func-docs:alta">Entrar a Clientes. <em>Resultado esperado:</em> ficha</li></ol>
  <p data-sources>Fuentes: func-docs:alta</p>
</section>"""


class FakeExecution:
    """Espeja el shape real: `metadata_json` es un str (columna Text), no un dict."""

    def __init__(self, metadata_json=None):
        self.id = 1
        self.metadata_json = metadata_json
        self.html_output_path = None
        self.ticket = None


@pytest.fixture(autouse=True)
def _sin_docs(monkeypatch):
    from services import docs_rag

    monkeypatch.setattr(docs_rag, "search", lambda *a, **kw: [], raising=True)


def _meta(execution) -> dict:
    return json.loads(execution.metadata_json or "{}")


def test_attach_persiste_metadata():
    ex = FakeExecution()
    pb = vp.compute_and_attach(execution=ex, agent_type="functional", html=_HTML_A,
                               project_name="RSPACIFICO", process_catalog=_CATALOG)

    assert isinstance(ex.metadata_json, str), "metadata_json debe seguir siendo un str serializado"
    stored = _meta(ex)["validation_playbook"]
    assert stored["status"] in vp.VALID_STATUSES
    assert stored["status"] == pb.status == "agent_provided"
    assert stored["steps"][0]["source"] == "func-docs:alta"


def test_attach_preserva_metadata_previa():
    ex = FakeExecution(metadata_json=json.dumps({"otra_cosa": 42}))
    vp.compute_and_attach(execution=ex, agent_type="functional", html=_HTML_A,
                          project_name="RSPACIFICO", process_catalog=None)

    meta = _meta(ex)
    assert meta["otra_cosa"] == 42, "no se puede pisar la metadata que ya existía"
    assert "validation_playbook" in meta


def test_attach_metadata_corrupta_no_rompe():
    ex = FakeExecution(metadata_json="{no es json")
    pb = vp.compute_and_attach(execution=ex, agent_type="functional", html=_HTML_A,
                               project_name="RSPACIFICO", process_catalog=None)

    assert pb.status == "agent_provided"
    assert "validation_playbook" in _meta(ex)


def test_flag_off_no_escribe(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_VALIDATION_PLAYBOOK_ENABLED", False, raising=False)
    ex = FakeExecution()
    pb = vp.compute_and_attach(execution=ex, agent_type="functional", html=_HTML_A,
                               project_name="RSPACIFICO", process_catalog=_CATALOG)

    assert pb.status == "disabled"
    assert ex.metadata_json is None, "con flag OFF no se escribe nada"


def test_gate_no_user_facing_disabled():
    ex = FakeExecution()
    pb = vp.compute_and_attach(execution=ex, agent_type="devops", html=_HTML_A,
                               project_name="RSPACIFICO", process_catalog=_CATALOG)

    assert pb.status == "disabled"
    assert pb.degraded_reason == "not_applicable"
    assert ex.metadata_json is None, "B no corre para agentes no-producto"


def test_detect_gana_sobre_build(monkeypatch):
    llamadas = []
    monkeypatch.setattr(vp, "build_from_grounding",
                        lambda **kw: llamadas.append(kw) or vp.ValidationPlaybook(
                            status="degraded", steps=[], sources=[], confidence=0.0,
                            degraded_reason="no_grounding"),
                        raising=True)

    ex = FakeExecution()
    pb = vp.compute_and_attach(execution=ex, agent_type="functional", html=_HTML_A,
                               project_name="RSPACIFICO", process_catalog=None)

    assert pb.status == "agent_provided"
    assert llamadas == [], "si A ya trajo pasos, B no debe correr"


def test_build_corre_si_falta_la_seccion():
    ex = FakeExecution()
    pb = vp.compute_and_attach(execution=ex, agent_type="functional",
                               html="<p>deliverable sin la seccion</p>",
                               project_name="RSPACIFICO", process_catalog=_CATALOG)

    assert pb.status in {"enriched", "degraded"}
    assert _meta(ex)["validation_playbook"]["status"] == pb.status


def test_warning_ungrounded_emite_log(caplog):
    html = f'<section data-stacky="validation-playbook"><h2>{vp.SECTION_TITLE}</h2>' \
           f'<ol><li data-source="func-docs:x">ok</li><li>sin fuente</li></ol></section>'
    ex = FakeExecution()
    with caplog.at_level("WARNING", logger="stacky_agents.validation_playbook"):
        pb = vp.compute_and_attach(execution=ex, agent_type="functional", html=html,
                                   project_name="RSPACIFICO", process_catalog=None)

    mensajes = [r.getMessage() for r in caplog.records]
    assert any(m == "validation_playbook.ungrounded_step: paso 2 sin fuente" for m in mensajes), \
        mensajes
    assert len(pb.steps) == 1, "el paso huérfano no se publica"


def test_register_agrega_post_hook():
    capturados = []
    vp.register(capturados.append)

    assert len(capturados) == 1
    assert capturados[0] is vp.validation_playbook_post_hook


def test_post_hook_gate_no_user_facing_no_toca_db(monkeypatch):
    import db
    from services import agent_html_output

    def _no_debe_llamarse(*a, **kw):
        raise AssertionError("el gate debe cortar ANTES de abrir sesión o leer disco")

    monkeypatch.setattr(db, "session_scope", _no_debe_llamarse, raising=True)
    monkeypatch.setattr(agent_html_output, "read_and_validate", _no_debe_llamarse, raising=True)

    vp.validation_playbook_post_hook(ticket_id=1, execution_id=1, final_status="completed",
                                     agent_type="devops")


def test_post_hook_flag_off_no_toca_db(monkeypatch):
    import db
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_VALIDATION_PLAYBOOK_ENABLED", False, raising=False)
    monkeypatch.setattr(
        db, "session_scope",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no debe abrir sesión")),
        raising=True,
    )

    vp.validation_playbook_post_hook(ticket_id=1, execution_id=1, final_status="completed",
                                     agent_type="functional")


def test_post_hook_no_lanza_sin_html():
    """Ejecución inexistente / sin comment.html: nunca rompe el cierre."""
    from db import init_db

    init_db()
    vp.validation_playbook_post_hook(ticket_id=999999, execution_id=999999,
                                     final_status="completed", agent_type="functional")


def test_post_hook_end_to_end_persiste():
    from db import init_db, session_scope
    from models import AgentExecution, Ticket

    init_db()
    with session_scope() as s:
        t = Ticket(ado_id=99600, project="Strategist_Pacifico",
                   stacky_project_name="RSPACIFICO", title="Asignar obligacion",
                   work_item_type="Task", stacky_status="running")
        s.add(t)
        s.flush()
        e = AgentExecution(ticket_id=t.id, agent_type="functional", status="completed",
                           input_context_json="{}", started_by="tester@local")
        s.add(e)
        s.flush()
        tid, eid = t.id, e.id

    vp.validation_playbook_post_hook(ticket_id=tid, execution_id=eid,
                                     final_status="completed", agent_type="functional")

    with session_scope() as s:
        row = s.get(AgentExecution, eid)
        meta = json.loads(row.metadata_json or "{}")
    assert "validation_playbook" in meta, "el hook debe persistir el playbook"
    assert meta["validation_playbook"]["status"] in {"enriched", "degraded"}

    with session_scope() as s:
        s.delete(s.get(AgentExecution, eid))
    with session_scope() as s:
        s.delete(s.get(Ticket, tid))
