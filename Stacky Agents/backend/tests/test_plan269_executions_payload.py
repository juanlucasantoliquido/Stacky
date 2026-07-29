"""Plan 269 F2 — El veredicto en los DOS payloads de ejecuciones.

TOCA LA DB (sqlite en memoria) => correr POR ARCHIVO.
CERO RED: no se llama a ADO ni a GitLab; la evidencia sale de la tabla local.

10 casos (§5 F2). El caso 9 es el GATE DEL FALSO VERDE en el BORDE (A3): un test
de nucleo no puede ver un bug de costura.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

UI_FLAG = "STACKY_UI_RUN_VERDICT_BADGE_ENABLED"
CORE_FLAG = "STACKY_RUN_VERDICT_ENABLED"
_ADO_BASE = 6950


@pytest.fixture
def client(monkeypatch):
    import app as app_module

    tmp = tempfile.TemporaryDirectory()
    monkeypatch.setenv("STACKY_REPO_ROOT", tmp.name)
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setattr(app_module, "_startup_sync", lambda logger: None)
    app = app_module.create_app()
    app.config.update(TESTING=True)
    from services.ticket_status import stop_stale_recovery

    stop_stale_recovery()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    tmp.cleanup()


def _sembrar(ado_id, *, run_status="error", stacky_status="completed",
            verdict_col=None, publicar=None, minutos=0):
    """Devuelve (ticket_id, execution_id). `publicar` = status de agent_html_publish."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(ado_id=ado_id, project="P269", title=f"t-{ado_id}",
                   ado_state="Active", stacky_status=stacky_status,
                   tracker_type="azure_devops", work_item_type="Bug")
        s.add(t)
        s.flush()
        ex = AgentExecution(
            ticket_id=t.id, agent_type="developer", status=run_status,
            input_context_json="[]", started_by="test",
            started_at=datetime.utcnow() - timedelta(minutes=minutos),
            verdict=verdict_col,
        )
        s.add(ex)
        s.flush()
        tid, exid = t.id, ex.id

    if publicar is not None:
        _publicar(exid, tid, ado_id, publicar)
    return tid, exid


def _publicar(execution_id, ticket_id, ado_id, status="ok"):
    """Helper de siembra de agent_html_publish. Las 7 columnas NOT NULL del
    modelo (services/ado_publisher.py:134-149): omitir una da IntegrityError."""
    from db import session_scope
    from services.ado_publisher import AgentHtmlPublish

    with session_scope() as s:
        s.add(AgentHtmlPublish(
            execution_id=execution_id, ticket_id=ticket_id, ado_id=ado_id,
            html_path="x", html_sha256=f"sha{execution_id}", status=status,
            triggered_by="test",
        ))
        s.flush()


def _lista(client, exec_id):
    r = client.get("/api/executions?limit=200")
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json()
    filas = data if isinstance(data, list) else data.get("items", [])
    return next((i for i in filas if i.get("id") == exec_id), None)


def _historial(client, exec_id, include_total=False):
    url = "/api/executions/history?limit=200"
    if include_total:
        url += "&include_total=1"
    r = client.get(url)
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json()
    filas = data.get("items", []) if isinstance(data, dict) else data
    return next((i for i in filas if i.get("id") == exec_id), None)


# ── Casos ─────────────────────────────────────────────────────────────────────

def test_1_flag_off_no_agrega_la_clave(client, monkeypatch):
    from config import config as cfg

    _, exid = _sembrar(_ADO_BASE + 1)
    monkeypatch.setattr(cfg, UI_FLAG, False)
    item = _lista(client, exid)
    assert item is not None
    assert "run_verdict" not in item, "con la flag OFF no debe existir ni con None"


def test_2_flag_nucleo_off_tambien_apaga(client, monkeypatch):
    from config import config as cfg

    _, exid = _sembrar(_ADO_BASE + 2)
    monkeypatch.setattr(cfg, UI_FLAG, True)
    monkeypatch.setattr(cfg, CORE_FLAG, False)
    item = _lista(client, exid)
    assert item is not None
    assert "run_verdict" not in item, "la dependencia en codigo no funciono"


def test_3_flag_on_agrega_la_clave_con_las_6_subclaves(client):
    _, exid = _sembrar(_ADO_BASE + 3)
    item = _lista(client, exid)
    assert item is not None
    assert isinstance(item.get("run_verdict"), dict)
    assert set(item["run_verdict"]) == {
        "level", "cause", "strength", "present", "absent", "unknown",
    }


def test_4_no_pisa_el_verdict_del_modelo(client):
    """La columna `verdict` (revision humana) y `run_verdict` conviven."""
    _, exid = _sembrar(_ADO_BASE + 4, verdict_col="approved")
    item = _lista(client, exid)
    assert item is not None
    assert item["verdict"] == "approved", "se piso un campo vivo de otro tipo"
    assert isinstance(item["run_verdict"], dict)


def test_5_history_endpoint_tambien_trae_run_verdict(client):
    """Sin esto, toda F4 es decorado inerte: la pagina consume ESTE endpoint."""
    _, exid = _sembrar(_ADO_BASE + 5)
    item = _historial(client, exid)
    assert item is not None, "la ejecucion no aparecio en /history"
    assert isinstance(item.get("run_verdict"), dict)
    con_total = _historial(client, exid, include_total=True)
    assert con_total is not None
    assert isinstance(con_total.get("run_verdict"), dict)


def test_6_colector_que_lanza_no_rompe_ninguno_de_los_dos(client, monkeypatch):
    """El enriquecimiento JAMAS rompe el listado: degrada a {} y sigue.

    _verdicts_for_batch importa collect_for_executions DENTRO de la funcion, asi
    que parchear el atributo del modulo de origen alcanza.
    """
    from services import run_evidence

    _, exid = _sembrar(_ADO_BASE + 6)

    def _boom(session, executions):
        raise RuntimeError("colector roto")

    monkeypatch.setattr(run_evidence, "collect_for_executions", _boom)

    item = _lista(client, exid)
    assert item is not None, "el listado se rompio"
    assert "run_verdict" not in item, "con el colector roto no se inventa veredicto"

    hist = _historial(client, exid)
    assert hist is not None, "el historial se rompio"

    # Y el payload del 254 sale IGUAL que sin el colector roto (criterio delta;
    # `outcome_reason` la promueve _with_outcome solo si el metadata la trae, asi
    # que exigir su presencia absoluta seria un falso rojo del propio test).
    monkeypatch.undo()
    sano = _lista(client, exid)
    assert sano is not None
    for k in ("outcome_reason", "outcome_actionable"):
        assert (k in item) == (k in sano), f"el colector roto cambio la clave {k} del 254"
        assert item.get(k) == sano.get(k)


def test_7_no_pisa_claves_del_254(client, monkeypatch):
    from config import config as cfg

    _, exid = _sembrar(_ADO_BASE + 7)
    con = _lista(client, exid)
    monkeypatch.setattr(cfg, UI_FLAG, False)
    sin = _lista(client, exid)
    assert con is not None and sin is not None
    for k in ("outcome_reason", "outcome_actionable"):
        assert con.get(k) == sin.get(k), f"el 269 cambio la clave {k} del 254"


def test_8_run_en_curso_no_trae_veredicto(client):
    _, exid = _sembrar(_ADO_BASE + 8, run_status="running")
    item = _lista(client, exid)
    assert item is not None
    assert "run_verdict" not in item, "un run en curso NO tiene veredicto"
    hist = _historial(client, exid)
    assert hist is not None
    assert "run_verdict" not in hist


def test_9_ticket_completed_no_blanquea_un_run_error(client):
    """A3 — EL GATE DEL FALSO VERDE, EN EL BORDE.

    Dos ejecuciones del MISMO ticket `completed`, CADA UNA con su propia fila
    `ok` en agent_html_publish. El unico factor que difiere es
    AgentExecution.status, que es exactamente la variable que se quiere aislar:
    si B (error) sale advertencia/falso_rojo_probable y A (completed) sale
    exito/cierre_limpio_con_entrega, queda probado que el nivel lo manda el RUN
    y que el stacky_status del ticket NO blanqueo a B.
    """
    from datetime import datetime as _dt

    from db import session_scope
    from models import AgentExecution, Ticket

    ado_id = _ADO_BASE + 9
    with session_scope() as s:
        t = Ticket(ado_id=ado_id, project="P269", title="contraste",
                   ado_state="Active", stacky_status="completed",
                   tracker_type="azure_devops", work_item_type="Bug")
        s.add(t)
        s.flush()
        a = AgentExecution(ticket_id=t.id, agent_type="developer",
                           status="completed", input_context_json="[]",
                           started_by="test", started_at=_dt.utcnow())
        b = AgentExecution(ticket_id=t.id, agent_type="developer",
                           status="error", input_context_json="[]",
                           started_by="test", started_at=_dt.utcnow())
        s.add(a)
        s.add(b)
        s.flush()
        tid, a_id, b_id = t.id, a.id, b.id

    # DOS filas ok, una por ejecucion: evidencia identica en las dos.
    _publicar(a_id, tid, ado_id, "ok")
    _publicar(b_id, tid, ado_id, "ok")

    for buscar in (_lista, _historial):
        item_b = buscar(client, b_id)
        assert item_b is not None, f"{buscar.__name__}: falta la ejecucion error"
        assert item_b["run_verdict"]["level"] == "advertencia", (
            f"{buscar.__name__}: FALSO VERDE — el ticket completed blanqueo un run error: "
            f"{item_b['run_verdict']}"
        )
        assert item_b["run_verdict"]["cause"] == "falso_rojo_probable"

        item_a = buscar(client, a_id)
        assert item_a is not None
        assert item_a["run_verdict"]["level"] == "exito", (
            f"{buscar.__name__}: la ejecucion completed con evidencia deberia ser exito: "
            f"{item_a['run_verdict']}"
        )
        assert item_a["run_verdict"]["cause"] == "cierre_limpio_con_entrega"


def test_10_sin_n_mas_uno(client, monkeypatch):
    """Se mide el DELTA de queries entre flag ON y OFF sobre el MISMO lote, con 3
    y con 30 ejecuciones. El delta no puede crecer con el tamano del lote.

    Se mide el delta y no el absoluto para no cargarle a este plan el lazy-load
    preexistente de executions_history.
    """
    from sqlalchemy import event

    from config import config as cfg
    from db import engine

    def _contar(url):
        n = {"q": 0}

        def _hook(conn, cursor, statement, params, context, executemany):
            n["q"] += 1

        event.listen(engine, "before_cursor_execute", _hook)
        try:
            client.get(url)
        finally:
            event.remove(engine, "before_cursor_execute", _hook)
        return n["q"]

    def _delta(url):
        monkeypatch.setattr(cfg, UI_FLAG, True)
        con = _contar(url)
        monkeypatch.setattr(cfg, UI_FLAG, False)
        sin = _contar(url)
        monkeypatch.setattr(cfg, UI_FLAG, True)
        return con - sin

    for i in range(3):
        _sembrar(_ADO_BASE + 20 + i)
    d3 = _delta("/api/executions?limit=3")
    for i in range(27):
        _sembrar(_ADO_BASE + 30 + i)
    d30 = _delta("/api/executions?limit=30")

    # El gate mide la PROPIEDAD que importa: el costo extra no escala con el
    # lote. Un N+1 real daria d30 ~ d3 + 27 (una query por fila nueva), asi que
    # una tolerancia FIJA y chica lo sigue atrapando; exigir igualdad exacta era
    # flaky (medido: 2 rojas de 18 corridas por una query de warm-up del pool,
    # no por un N+1). La tolerancia es fija a proposito: si fuera proporcional al
    # lote, el gate dejaria de medir.
    TOLERANCIA_FIJA = 2
    assert d30 <= d3 + TOLERANCIA_FIJA, (
        f"el costo extra del veredicto CRECE con el lote: {d3} queries con 3 filas "
        f"y {d30} con 30 (delta {d30 - d3}, tolerancia {TOLERANCIA_FIJA}). "
        "Eso es un N+1: el colector tiene que resolver el lote entero de una."
    )
