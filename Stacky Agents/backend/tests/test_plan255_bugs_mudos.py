"""Plan 255 F0 — los 3 bugs MUDOS que la auditoria de ~16 MB de logs probo.

Evidencia (stacky-2026-07-17 .. stacky-2026-07-26):
    50 WARNING [harness.resume] harness.resume.resolve fallo (arranque en frio):
       Query.filter() being called on a Query which already has LIMIT or OFFSET
     4 NameError: name 'ado_id' is not defined      -> api/agents.py run_incident_dev
     1 NameError: name 'data_dir' is not defined    -> services/telemetry_harvest.py
  1016 WARNING sweep_recent_runs: error general: cannot import name 'Execution'

Criterio de F0 (rojo primero): antes de los fixes FALLAN los casos 1, 3, 6, 7, 8
y 9; PASAN los casos 4 y 5 (describen el comportamiento a PRESERVAR).

El caso 2 era el TEST-GUARDIA anti-falso-rojo (C3): con el fixture completo,
antes del fix, `caplog` tenia que traer `already has LIMIT or OFFSET applied`.
Se corrio y dio VERDE antes de tocar `harness/resume.py`, probando que el rojo
de los casos 1 y 3 era el rojo correcto (el query roto) y no un gate cortando
antes. Cumplido su proposito, se elimina en el mismo commit del fix, como manda
el plan; queda esta constancia en su lugar.

Bajo pytest la base es un shared-cache in-memory (db.py:27-29), donde el thread
`stacky-syslog-writer` le devuelve SQLITE_LOCKED ("database table is locked") a
cualquier otra conexion. Ese codigo NO lo cubre el busy_timeout. Toda unidad de
trabajo va envuelta en `run_with_retry` (plan 253 F4), que reintenta con una
sesion NUEVA por intento.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Sustrato comun ────────────────────────────────────────────────────────────


@pytest.fixture()
def db():
    from app import create_app  # noqa: F401 — fuerza el wiring de la app/DB
    from db import init_db

    create_app()
    init_db()
    yield


def _con_reintento(fn, label: str):
    from db import run_with_retry

    return run_with_retry(fn, label=f"plan255 {label}")


_ADO_SEQ = [255_000]


def _new_ticket() -> int:
    from db import session_scope
    from models import Ticket

    _ADO_SEQ[0] += 1

    def _unit() -> int:
        with session_scope() as session:
            t = Ticket(
                ado_id=_ADO_SEQ[0],
                project="PLAN255",
                title="plan 255 fixture",
                ado_state="Active",
                stacky_status="completed",
            )
            session.add(t)
            session.flush()
            return t.id

    return _con_reintento(_unit, "alta de ticket")


def _new_execution(ticket_id: int, *, session_id: str | None,
                   runtime: str = "claude_code_cli",
                   agent_type: str = "developer",
                   status: str = "completed",
                   session_key: str = "session_id") -> int:
    """Ejecucion sembrada con la metadata EXACTA que mira `resolve`.

    Sin `metadata["runtime"]` coincidente y sin la clave del session ref del
    runtime, el loop de `resolve` no matchea y el resultado es (None, None)
    aunque el query funcione (fixture obligatorio del plan, corrige C3).
    """
    from db import session_scope
    from models import AgentExecution

    md: dict = {"runtime": runtime}
    if session_id is not None:
        md[session_key] = session_id

    def _unit() -> int:
        with session_scope() as session:
            row = AgentExecution(
                ticket_id=ticket_id,
                agent_type=agent_type,
                status=status,
                input_context_json=json.dumps([{"id": "a", "content": "x"}]),
                output="salida previa",
                metadata_json=json.dumps(md),
                started_by="tests",
            )
            session.add(row)
            session.flush()
            return row.id

    return _con_reintento(_unit, "alta de ejecucion")


@contextmanager
def _resume_flags(monkeypatch, *, enabled: bool = True, projects: str = ""):
    """Gate 3 de `resolve`: se parchea la INSTANCIA `config.config`.

    Nunca el modulo: `getattr` del modulo devuelve el default y mata el branch
    (gotcha de la casa). Tampoco `importlib.reload(config)`: contamina la suite.
    """
    from config import config

    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_ENABLED", enabled, raising=False)
    monkeypatch.setattr(config, "CLAUDE_CODE_CLI_RESUME_PROJECTS", projects, raising=False)
    yield


def _resolve(**kwargs):
    """`resolve` reintentado como unidad de trabajo.

    `resolve` traga sus propias excepciones y devuelve (None, None), asi que un
    SQLITE_LOCKED del shared-cache se veria como "no hay sesion previa". Se
    reintenta un numero acotado de veces y se devuelve el PRIMER resultado con
    session ref. Si el codigo esta roto, todos los intentos dan (None, None) y
    la asercion falla igual: no es un verde blando.
    """
    import time

    from harness import resume

    ultimo = (None, None)
    for intento in range(5):
        ultimo = resume.resolve(**kwargs)
        if ultimo[0] is not None:
            return ultimo
        time.sleep(0.05 * (intento + 1))
    return ultimo


# ── 1-5. Bug (A): el resume esta MUERTO desde el 2026-07-17 ───────────────────


def test_resume_resolve_con_execution_id_devuelve_la_sesion_previa(db, monkeypatch):
    """El caso NORMAL: el runner siempre pasa `execution_id` (la corrida actual).

    Hoy `.filter()` despues de `.limit(5)` revienta, `resolve` lo traga y
    devuelve (None, None): el runner arranca en frio. El criterio binario es el
    VALOR DE RETORNO, no la ausencia de un log (C3).
    """
    tid = _new_ticket()
    _new_execution(tid, session_id="sess-AAAA")
    actual = _new_execution(tid, session_id="sess-ACTUAL")

    with _resume_flags(monkeypatch):
        sid, delta = _resolve(
            runtime="claude_code_cli", ticket_id=tid, agent_type="developer",
            project="PLAN255", execution_id=actual,
        )

    assert sid == "sess-AAAA"
    assert delta is None or isinstance(delta, str)


def test_resume_resolve_excluye_la_ejecucion_actual(db, monkeypatch):
    """Fija la SEMANTICA, no solo la ausencia de excepcion."""
    tid = _new_ticket()
    _new_execution(tid, session_id="sess-VIEJA")
    _new_execution(tid, session_id="sess-MEDIA")
    nueva = _new_execution(tid, session_id="sess-NUEVA")

    with _resume_flags(monkeypatch):
        sid, _ = _resolve(
            runtime="claude_code_cli", ticket_id=tid, agent_type="developer",
            project="PLAN255", execution_id=nueva,
        )

    assert sid == "sess-MEDIA"


def test_resume_resolve_sin_execution_id_sigue_funcionando(db, monkeypatch):
    """El path que HOY si anda no se puede romper con el fix."""
    tid = _new_ticket()
    _new_execution(tid, session_id="sess-UNICA")

    with _resume_flags(monkeypatch):
        sid, _ = _resolve(
            runtime="claude_code_cli", ticket_id=tid, agent_type="developer",
            project="PLAN255", execution_id=None,
        )

    assert sid == "sess-UNICA"


def test_resume_sin_flag_no_loguea_y_devuelve_none(db, monkeypatch, caplog):
    """Guarda 3 (kill-switch): sin flag no se toca la base y no se loguea nada."""
    from harness import resume

    tid = _new_ticket()
    _new_execution(tid, session_id="sess-IGNORADA")

    caplog.set_level(logging.DEBUG, logger="harness.resume")
    caplog.clear()
    with _resume_flags(monkeypatch, enabled=False):
        sid, delta = resume.resolve(
            runtime="claude_code_cli", ticket_id=tid, agent_type="developer",
            project="PLAN255", execution_id=None,
        )

    assert (sid, delta) == (None, None)
    assert [r for r in caplog.records if r.name == "harness.resume"] == []


def test_resume_delta_prefix_acotado_a_20000_chars(db, monkeypatch, caplog):
    """DoD: un delta gigante es PEOR que no reanudar — se descarta y se avisa."""
    from harness import resume
    from services import delta_prompt

    tid = _new_ticket()
    _new_execution(tid, session_id="sess-DELTA")

    monkeypatch.setattr(
        delta_prompt, "build_delta_prompt", lambda *a, **k: "x" * 25_000
    )
    monkeypatch.setattr(
        delta_prompt, "compute_diff",
        lambda prev, cur: type("D", (), {"is_delta_eligible": True, "change_ratio": 0.5})(),
    )

    caplog.set_level(logging.INFO, logger="harness.resume")
    with _resume_flags(monkeypatch):
        sid, delta = _resolve(
            runtime="claude_code_cli", ticket_id=tid, agent_type="developer",
            project="PLAN255", execution_id=None,
            current_blocks=[{"id": "a", "content": "y"}],
        )

    assert sid == "sess-DELTA"
    assert delta is None, "un delta de 25 000 chars tiene que descartarse"
    assert any("delta" in r.getMessage().lower() and r.levelno == logging.INFO
               for r in caplog.records)


# ── 6. Bug (B): NameError 'ado_id' en run_incident_dev ────────────────────────


def _fake_ticket(ado_id=666):
    t = MagicMock()
    t.id = 1
    t.work_item_type = "Issue"
    t.ado_id = ado_id
    t.title = "[INC] Falla X"
    t.description = "<p>desglose</p>"
    return t


def test_run_incident_dev_resuelve_el_ado_id(caplog):
    """4 NameError el 2026-07-26: el resolutor devolvia 202 y NUNCA linkeaba.

    El nombre correcto es `ticket_ado_id` (asignado en el mismo cuerpo de
    funcion). La unica asignacion de `ado_id` vive en el cuerpo de la clase
    `_TicketSnapshot`, y los bindings de class-body NO son visibles desde el
    scope de la funcion que la contiene.
    """
    import config as cfg
    from app import create_app

    llamadas: list = []

    @contextmanager
    def _fake_scope():
        sess = MagicMock()
        sess.get.return_value = _fake_ticket(ado_id=666)
        yield sess

    app = create_app()
    app.config["TESTING"] = True

    import agent_runner as ar
    from services import incident_store as istore

    original = getattr(cfg.config, "STACKY_INCIDENT_DEV_RESOLVER_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = True
    caplog.set_level(logging.DEBUG, logger="stacky.api.agents")
    caplog.clear()
    try:
        with patch("db.session_scope", _fake_scope), \
             patch.object(ar, "run_agent", MagicMock(return_value=77)), \
             patch.object(istore, "find_by_tracker_id",
                          lambda tracker_id: llamadas.append(tracker_id) or None):
            with app.test_client() as client:
                resp = client.post("/api/agents/run-incident-dev", json={"ticket_id": 1})
    finally:
        cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = original

    assert resp.status_code == 202
    assert llamadas == [666], "find_by_tracker_id no recibio el ADO id del ticket"
    assert "NameError" not in caplog.text


# ── 7-8. Bug (C): NameError 'data_dir' en telemetry_harvest ───────────────────


def test_telemetry_harvest_ledger_path_resuelve():
    """Con la configuracion por defecto el ledger de cosecha NUNCA se escribia."""
    import runtime_paths
    from services import telemetry_harvest as th

    path = th._ledger_path()
    assert path.name == "telemetry_harvest.jsonl"
    assert path.parent == Path(runtime_paths.data_dir())


def test_telemetry_harvest_append_escribe_el_ledger(tmp_path, monkeypatch):
    """El contenido y la higiene del ledger son del plan 258; aca solo que SE ESCRIBE.

    `monkeypatch.setattr` sin `raising=False` a proposito: si el modulo no
    importo `data_dir` a nivel modulo, esto revienta con AttributeError — que es
    exactamente el bug. Con `raising=False` se CREARIA el global y el test seria
    un falso verde.
    """
    from services import telemetry_harvest as th

    monkeypatch.setattr(th, "data_dir", lambda: tmp_path)

    run = th.HarvestedRun(
        runtime="codex_cli", session_id="sess-L", model="gpt-5",
        tokens_in=10, tokens_out=20, cache_read_tokens=0,
        total_cost_usd=0.5, cost_estimated=False, started_at=None,
        project_hint=None, cwd=None, artifact="rollout-x.jsonl",
        source_format="codex_rollout", num_events=1,
    )
    res = th.append_to_ledger([run], {}, attributed_only=False)

    ledger = tmp_path / "telemetry_harvest.jsonl"
    assert res["appended"] == 1
    assert ledger.is_file()
    lineas = [l for l in ledger.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lineas) == 1
    assert json.loads(lineas[0])["dedup_key"] == "codex_cli:sess-L"


# ── 9. Bug (D): 1016 fallos estructurales tragados a nivel warning ────────────


def test_sweep_recent_runs_loguea_importerror_como_error(caplog):
    """Un ImportError es un fallo ESTRUCTURAL: no se arregla solo, no es transitorio.

    Mecanismo de inyeccion literal (C13): se llama SIN `_db_runs` para entrar en
    la rama `if _db_runs is None:` — con `_db_runs=[...]` el import nunca se
    alcanza y el test verdea sin probar nada.
    """
    import db as db_mod
    from services import ado_edit_learning as ael

    def _raise_import_error(*_a, **_kw):
        raise ImportError("cannot import name 'Execution' from 'models'")

    caplog.set_level(logging.DEBUG, logger="stacky_agents.services.ado_edit_learning")
    caplog.clear()
    with patch.object(db_mod, "session_scope", _raise_import_error):
        assert ael.sweep_recent_runs() == 0

    propios = [r for r in caplog.records
               if r.name == "stacky_agents.services.ado_edit_learning"]
    errores = [r for r in propios if r.levelno == logging.ERROR]
    assert len(errores) == 1, f"esperaba 1 registro ERROR, hubo {len(propios)}: " \
                              f"{[(r.levelname, r.getMessage()) for r in propios]}"
    assert "ESTRUCTURAL" in errores[0].getMessage()
