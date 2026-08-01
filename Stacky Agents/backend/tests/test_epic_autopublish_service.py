"""Plan 278 F1/F2/F2-bis/F6-bis — el publicador unico, agnostico de runtime.

Cubre services/epic_autopublish.py: el post-hook que publica la Epica/Issue del
brief en los 3 runtimes (Claude CLI, Codex CLI, GitHub Copilot), su sellado de
metadata, su degradacion en las DOS capas (fila + ticket) y su claim atomico.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_EPIC_HTML = "<h2>Epica</h2><p>RF-01: el sistema hace algo.</p>"


# ── helpers ───────────────────────────────────────────────────────────────────

def _res(**kw):
    """Construye un _AutopublishResult real (NamedTuple de api/tickets.py:7229)."""
    from api.tickets import _AutopublishResult
    base = dict(ado_id=None, error=None, skipped=False, grounding_warnings=[],
                epic_summary=None, recovery_method=None, published_html=None,
                baseline_rev=None)
    base.update(kw)
    return _AutopublishResult(**base)


# La DB en memoria es COMPARTIDA entre tests (db.py la remapea a
# cache=shared) y `tickets` tiene UNIQUE(stacky_project_name, tracker_type,
# external_id). Cada run necesita su propio ado_id o el 2o test explota con
# IntegrityError — que es un fallo del fixture, no del servicio.
_ADO_SEQ = [-1000]


def _mk_run(*, blocks=None, metadata=None, status="completed", ado_id=None,
            output=_EPIC_HTML, agent_type="business", started_at=None):
    """Crea Ticket + AgentExecution reales en la sqlite en memoria."""
    from db import init_db, session_scope
    from models import AgentExecution, Ticket
    init_db()
    if blocks is None:
        blocks = [{"id": "brief", "content": "BRIEF X"}]
    if ado_id is None:
        _ADO_SEQ[0] -= 1
        ado_id = _ADO_SEQ[0]
    with session_scope() as session:
        ticket = Ticket(ado_id=ado_id, project="ProyDemo", title="Brief Pool",
                        stacky_project_name="ProyDemo", stacky_status="running")
        session.add(ticket)
        session.flush()
        row = AgentExecution(ticket_id=ticket.id, agent_type=agent_type,
                             status=status, started_by="test@test.com",
                             output=output,
                             started_at=started_at or datetime.utcnow())
        row.input_context = blocks
        row.metadata_dict = metadata or {}
        session.add(row)
        session.flush()
        return ticket.id, row.id


def _fire(ticket_id, execution_id, *, final_status="completed", agent_type="business"):
    from services import epic_autopublish
    epic_autopublish.maybe_autopublish_epic(
        ticket_id=ticket_id, execution_id=execution_id,
        final_status=final_status, agent_type=agent_type, error=None,
    )


# ── F1 ────────────────────────────────────────────────────────────────────────

def test_publica_cuando_hay_bloque_brief():
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=4242))) as pub:
        _fire(tid, eid)
    pub.assert_called_once()
    assert pub.call_args.kwargs["brief"] == "BRIEF X"
    assert pub.call_args.kwargs["project_name"] == "ProyDemo"


def test_no_publica_sin_bloque_brief():
    # Chat interactivo del BusinessAgent: no hay bloque brief -> no es brief->epica.
    tid, eid = _mk_run(blocks=[{"id": "chat", "content": "hola"}])
    with patch("api.tickets.autopublish_epic_from_run", MagicMock()) as pub:
        _fire(tid, eid)
    assert pub.call_count == 0


def test_no_publica_para_business_en_pool_sin_brief():
    # Sub-disparo DECLARADO (C6): hoy una run business sobre ado_id=-8 entra igual
    # al closure del runner y publica con brief="". Manana NO publica. Es mejor,
    # y se congela aca en vez de esconderse.
    tid, eid = _mk_run(ado_id=-8, blocks=[{"id": "contexto", "content": "x"}])
    with patch("api.tickets.autopublish_epic_from_run", MagicMock()) as pub:
        _fire(tid, eid)
    assert pub.call_count == 0


def test_no_publica_si_ya_esta_sellado():
    tid, eid = _mk_run(metadata={"epic_ado_id": 999})
    with patch("api.tickets.autopublish_epic_from_run", MagicMock()) as pub:
        _fire(tid, eid)
    assert pub.call_count == 0


def test_no_publica_con_flag_off():
    from config import config
    tid, eid = _mk_run()
    with patch.object(config, "STACKY_EPIC_AUTOPUBLISH_BACKEND", False):
        with patch("api.tickets.autopublish_epic_from_run", MagicMock()) as pub:
            _fire(tid, eid)
    assert pub.call_count == 0


@pytest.mark.parametrize("estado", ["running", "error", "cancelled"])
def test_no_publica_en_estado_no_terminal(estado):
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run", MagicMock()) as pub:
        _fire(tid, eid, final_status=estado)
    assert pub.call_count == 0


def test_bifurca_a_issue_con_flag_on():
    from config import config
    tid, eid = _mk_run(metadata={"work_item_type": "Issue"})
    with patch.object(config, "STACKY_ISSUE_FROM_BRIEF_ENABLED", True):
        with patch("api.tickets.publish_issue_from_run",
                   MagicMock(return_value=_res(ado_id=7))) as pub_issue, \
             patch("api.tickets.autopublish_epic_from_run", MagicMock()) as pub_epic:
            _fire(tid, eid)
    pub_issue.assert_called_once()
    assert pub_epic.call_count == 0
    # publish_issue_from_run NO acepta run_started_at (api/tickets.py:7695).
    assert "run_started_at" not in pub_issue.call_args.kwargs


def test_run_started_at_sale_de_spawn_epoch_sellado():
    tid, eid = _mk_run(metadata={"spawn_epoch": 1234567890.5})
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=1))) as pub:
        _fire(tid, eid)
    assert pub.call_args.kwargs["run_started_at"] == 1234567890.5


def test_run_started_at_fallback_es_utc():
    # Sin spawn_epoch: started_at es un datetime NAIVE. .timestamp() lo leeria
    # como hora LOCAL (desfase de horas en Windows). Debe declararse UTC.
    tid, eid = _mk_run(started_at=datetime(2026, 1, 1, 0, 0, 0))
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=1))) as pub:
        _fire(tid, eid)
    assert pub.call_args.kwargs["run_started_at"] == 1767225600.0


def test_una_excepcion_del_publicador_no_propaga():
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(side_effect=RuntimeError("boom"))):
        _fire(tid, eid)   # no debe levantar: el hook nunca tumba on_execution_end


# ── F2 — sellado (9 filas) y degradacion en las DOS capas ─────────────────────

def _read(execution_id):
    from db import session_scope
    from models import AgentExecution
    with session_scope() as session:
        row = session.get(AgentExecution, execution_id)
        return row.status, dict(row.metadata_dict or {})


def _ticket_status(ticket_id):
    from db import session_scope
    from models import Ticket
    with session_scope() as session:
        return session.get(Ticket, ticket_id).stacky_status


def test_error_del_publicador_degrada_a_needs_review():
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(error="epic_not_in_output: narracion"))):
        _fire(tid, eid)
    assert _ticket_status(tid) == "needs_review"
    _, md = _read(eid)
    assert md["epic_publish_error"].startswith("epic_not_in_output")


def test_exito_sella_epic_ado_id_sin_pisar_metadata_previa():
    previa = {"runtime": "codex_cli", "work_item_type": "Epic", "spawn_epoch": 111.0}
    tid, eid = _mk_run(metadata=dict(previa))
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=555))):
        _fire(tid, eid)
    _, md = _read(eid)
    assert md["epic_ado_id"] == 555
    for k, v in previa.items():
        assert md[k] == v, f"el hook piso metadata previa: {k}"


def test_sella_grounding_warnings_epic_summary_y_epic_recovery():
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=1, grounding_warnings=["w1"],
                                           epic_summary={"s": 1},
                                           recovery_method="rescued_from_disk"))):
        _fire(tid, eid)
    _, md = _read(eid)
    assert md["grounding_warnings"] == ["w1"]
    assert md["epic_summary"] == {"s": 1}
    assert md["epic_recovery"] == "rescued_from_disk"


def test_sella_epic_baseline_html_y_rev_solo_en_epica_no_skipped():
    # Plan 60 F1: sin esto el aprendizaje bidireccional se queda sin baseline.
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=1, published_html="<h2>E</h2>",
                                           baseline_rev=3))):
        _fire(tid, eid)
    _, md = _read(eid)
    assert md["epic_baseline_html"] == "<h2>E</h2>"
    assert md["epic_baseline_rev"] == 3

    # skipped=True -> 0 sellos de baseline.
    tid2, eid2 = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=2, skipped=True,
                                           published_html="<h2>E</h2>", baseline_rev=9))):
        _fire(tid2, eid2)
    _, md2 = _read(eid2)
    assert "epic_baseline_html" not in md2
    assert "epic_baseline_rev" not in md2

    # is_issue=True -> 0 sellos de baseline.
    from config import config
    tid3, eid3 = _mk_run(metadata={"work_item_type": "Issue"})
    with patch.object(config, "STACKY_ISSUE_FROM_BRIEF_ENABLED", True), \
         patch("api.tickets.publish_issue_from_run",
               MagicMock(return_value=_res(ado_id=3, published_html="<h2>E</h2>",
                                           baseline_rev=9))):
        _fire(tid3, eid3)
    _, md3 = _read(eid3)
    assert "epic_baseline_html" not in md3
    assert "epic_baseline_rev" not in md3


def test_el_hook_no_llama_on_execution_end():
    # El hook corre DENTRO de _run_post_hooks. Llamar on_execution_end para
    # degradar re-dispararia todos los post-hooks, incluido este => recursion.
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "services" / "epic_autopublish.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        assert not (isinstance(node, ast.Attribute) and node.attr == "on_execution_end")
        assert not (isinstance(node, ast.Name) and node.id == "on_execution_end")


def test_fallo_de_publicacion_degrada_TAMBIEN_la_fila():
    # Sin esto la fila queda 'completed' mientras el ticket dice 'needs_review'.
    tid, eid = _mk_run()
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(error="ado 500"))):
        _fire(tid, eid)
    estado, md = _read(eid)
    assert estado == "needs_review"
    assert md.get("failure_kind"), "falta failure_kind: paridad con _mark_terminal"


# ── F2-bis — claim atomico: a lo sumo UNA publicacion por ejecucion ───────────

def test_claim_lo_gana_uno_solo():
    from services import epic_autopublish
    _, eid = _mk_run()
    assert epic_autopublish._claim(eid) is True
    assert epic_autopublish._claim(eid) is False


def test_dos_on_execution_end_publican_una_sola_vez():
    # epic_ado_id queda SIN sellar (simula el fallo de la 1a y el reintento de la
    # 2a): la unica defensa que queda en pie es el claim.
    tid, eid = _mk_run()
    pub = MagicMock(return_value=_res(ado_id=None, skipped=True))
    with patch("api.tickets.autopublish_epic_from_run", pub):
        _fire(tid, eid)
        _fire(tid, eid)
    _, md = _read(eid)
    assert "epic_ado_id" not in md, "precondicion: el sello NO debe ser quien corta"
    assert pub.call_count == 1


def test_claim_concurrente_desde_dos_hilos():
    import threading
    tid, eid = _mk_run()
    barrier = threading.Barrier(2)
    pub = MagicMock(return_value=_res(ado_id=None, skipped=True))
    errores: list = []

    def _worker():
        try:
            barrier.wait(timeout=10)
            _fire(tid, eid)
        except Exception as exc:  # noqa: BLE001
            errores.append(exc)

    with patch("api.tickets.autopublish_epic_from_run", pub):
        hilos = [threading.Thread(target=_worker) for _ in range(2)]
        for h in hilos:
            h.start()
        for h in hilos:
            h.join(timeout=30)

    assert not errores, f"el hook propago una excepcion: {errores}"
    assert pub.call_count == 1


# ── F6-bis — la paridad de MECANISMO se vuelve medible ───────────────────────

def test_sella_epic_publish_con_outcome_published():
    tid, eid = _mk_run(metadata={"runtime": "github_copilot", "work_item_type": "Epic"})
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(ado_id=1, recovery_method="published_inline"))):
        _fire(tid, eid)
    _, md = _read(eid)
    sello = md["epic_publish"]
    assert sello["outcome"] == "published"
    assert sello["runtime"] == "github_copilot"
    assert sello["work_item_type"] == "Epic"
    assert sello["error_kind"] is None
    assert sello["recovery_method"] == "published_inline"
    assert sello["at"]


def test_sella_epic_publish_con_outcome_failed_y_error_kind():
    # El error_kind se deriva del PREFIJO de res.error (api/tickets.py emite
    # "epic_not_in_output: ..."), sin parsear el texto completo.
    tid, eid = _mk_run(metadata={"runtime": "codex_cli"})
    with patch("api.tickets.autopublish_epic_from_run",
               MagicMock(return_value=_res(error="epic_not_in_output: narracion del agente"))):
        _fire(tid, eid)
    _, md = _read(eid)
    sello = md["epic_publish"]
    assert sello["outcome"] == "failed"
    assert sello["error_kind"] == "epic_not_in_output"
    assert sello["runtime"] == "codex_cli"
