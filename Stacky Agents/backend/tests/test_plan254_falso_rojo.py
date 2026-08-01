"""Plan 254 F0 — reproduce el FALSO ROJO: trabajo entregado marcado como error.

Evidencia (stacky-2026-07-25.log):
    11:56:03 ERROR [claude_code_cli] [exec=161] claude code cli exited with code 1
    11:56:03 INFO  [stacky.ticket_status] ticket_id=673: 'completed' -> 'error'

El ticket estaba en 'completed' (lo puso el propio agente vía PATCH
/api/tickets/by-ado/{id}/stacky-status) y Stacky lo pisó con el exit code.

Criterio de F0 (rojo primero): 5 de estos casos FALLAN antes de F1 (1, 5, 6, 7 y
8) y 3 PASAN ya (2, 3 y 4 — describen el comportamiento a PRESERVAR). Si alguno
de esos tres falla antes de tocar nada, el diagnóstico está mal y hay que frenar.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture()
def db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    from app import create_app  # noqa: F401 — fuerza el wiring de la app/DB
    from db import init_db

    create_app()
    init_db()
    yield


_ADO_SEQ = [254_000]


# Bajo pytest la base es un shared-cache in-memory (db.py:27-29), donde el
# thread `stacky-syslog-writer` le devuelve SQLITE_LOCKED
# ("database table is locked") a cualquier otra conexion que lea o escriba.
# Ese codigo NO lo cubre el busy_timeout. Toda unidad de trabajo de este archivo
# va envuelta en run_with_retry (plan 253 F4), que reintenta con una sesion
# NUEVA por intento. No es un verde blando: si la operacion falla por algo que
# no es un lock, o si se agotan los intentos, la excepcion se propaga.
def _con_reintento(fn, label: str):
    from db import run_with_retry

    return run_with_retry(fn, label=f"plan254 {label}")


def _on_execution_end(ticket_status, **kwargs):
    """`on_execution_end` reintentado como unidad de trabajo completa.

    `set_status` abre su propia `session_scope()` (ticket_status.py:163), asi que
    si el flush choca contra el lock del shared-cache, la transaccion se revierte
    entera y los post-hooks NO llegan a correr: reintentar es seguro e idempotente.
    """
    return _con_reintento(
        lambda: ticket_status.on_execution_end(**kwargs), "on_execution_end"
    )


def _new_ticket(stacky_status: str = "completed") -> int:
    """Ticket fresco con ado_id propio (el discriminador real es (ado_id, project))."""
    from db import session_scope
    from models import Ticket

    _ADO_SEQ[0] += 1

    def _unit() -> int:
        with session_scope() as session:
            t = Ticket(
                ado_id=_ADO_SEQ[0],
                project="PLAN254",
                title="plan 254 fixture",
                ado_state="Active",
                stacky_status=stacky_status,
            )
            session.add(t)
            session.flush()
            return t.id

    return _con_reintento(_unit, "alta de ticket")


def _last_event(ticket_id: int):
    """Último TicketStatusEvent del ticket, como dict (con metadata parseada)."""
    from db import session_scope
    from services.ticket_status import TicketStatusEvent

    def _unit():
        with session_scope() as session:
            row = (
                session.query(TicketStatusEvent)
                .filter(TicketStatusEvent.ticket_id == ticket_id)
                .order_by(TicketStatusEvent.id.desc())
                .first()
            )
            if row is None:
                return None
            return {
                "old_status": row.old_status,
                "new_status": row.new_status,
                "reason": row.reason,
                "metadata": json.loads(row.metadata_json) if row.metadata_json else None,
            }

    return _con_reintento(_unit, "lectura del ultimo evento")


# ── 1. EL BUG ─────────────────────────────────────────────────────────────────


def test_on_execution_end_no_degrada_completed_a_error(db):
    """El caso literal del log del 07-25: 'completed' NO puede caer a 'error'."""
    from services import ticket_status

    tid = _new_ticket("completed")
    _on_execution_end(
        ticket_status,
        ticket_id=tid,
        execution_id=1610,
        final_status="error",
        agent_type="developer",
        error="claude code cli exited with code 1",
    )
    assert ticket_status.get_current_status(tid) == "completed"


# ── 2/3/4. LO QUE HAY QUE PRESERVAR (verde ya, antes de F1) ───────────────────


def test_on_execution_end_si_permite_error_desde_running(db):
    """El guard NO es un cheque en blanco: un run que falla de verdad va a error."""
    from services import ticket_status

    tid = _new_ticket("running")
    _on_execution_end(
        ticket_status,
        ticket_id=tid, execution_id=1611, final_status="error",
        agent_type="developer", error="build roto",
    )
    assert ticket_status.get_current_status(tid) == "error"


def test_on_execution_end_permite_completed_a_needs_review(db):
    """Escalar a revisión humana NO destruye trabajo: sigue permitido."""
    from services import ticket_status

    tid = _new_ticket("completed")
    _on_execution_end(
        ticket_status,
        ticket_id=tid, execution_id=1612, final_status="needs_review",
        agent_type="developer",
    )
    assert ticket_status.get_current_status(tid) == "needs_review"


def test_on_execution_end_permite_completed_a_cancelled(db):
    """C3 — human-in-the-loop: cancelar es del OPERADOR y siempre gana."""
    from services import ticket_status

    tid = _new_ticket("completed")
    _on_execution_end(
        ticket_status,
        ticket_id=tid, execution_id=1613, final_status="cancelled",
        agent_type="developer",
    )
    assert ticket_status.get_current_status(tid) == "cancelled"


# ── 5. TAXONOMÍA (F2) ─────────────────────────────────────────────────────────


def test_on_execution_end_registra_outcome_reason(db):
    """El metadata del cambio de estado lleva un outcome_reason del vocabulario."""
    from services import ticket_status
    from services.run_outcome import OUTCOME_REASONS, classify_outcome_reason

    reason = classify_outcome_reason(return_code=1, result_ok_seen=True)
    tid = _new_ticket("running")
    _on_execution_end(
        ticket_status,
        ticket_id=tid, execution_id=1614, final_status="needs_review",
        agent_type="developer", metadata_override={"outcome_reason": reason},
    )
    ev = _last_event(tid)
    assert ev is not None
    assert ev["metadata"]["outcome_reason"] in OUTCOME_REASONS


# ── 6. AUDITORÍA DEL BLOQUEO ──────────────────────────────────────────────────


def test_degradacion_bloqueada_se_audita(db):
    """Un guard silencioso sería un falso verde nuevo: tiene que dejar rastro."""
    from db import run_with_retry, session_scope
    from models import SystemLog
    from services import ticket_status
    from services.stacky_logger import logger as stacky_logger

    tid = _new_ticket("completed")
    _on_execution_end(
        ticket_status,
        ticket_id=tid, execution_id=1615, final_status="error",
        agent_type="developer", error="claude code cli exited with code 1",
    )

    def _leer_auditoria() -> list[tuple[str, str]]:
        # Unidad de trabajo COMPLETA con sesion propia: es el contrato de
        # run_with_retry (db.py:178). Los atributos se materializan DENTRO de
        # la sesion; afuera quedarian expirados.
        with session_scope() as session:
            filas = (
                session.query(SystemLog)
                .filter(SystemLog.action == "downgrade_blocked")
                .filter(SystemLog.ticket_id == tid)
                .all()
            )
            return [((r.level or "").lower(), r.context_json or "") for r in filas]

    # El writer de SystemLog es asincronico (thread `stacky-syslog-writer`) y
    # bajo pytest la base es un shared-cache in-memory, donde su escritura le da
    # SQLITE_LOCKED al lector: `database table is locked: system_logs`. El
    # busy_timeout NO cubre ese codigo, por eso la lectura va envuelta en
    # run_with_retry (plan 253 F4), que reintenta con una sesion nueva.
    # Poll acotado: NO es un verde blando — si la fila no aparece nunca, falla.
    rows: list[tuple[str, str]] = []
    level = ""
    context = ""
    for _ in range(20):
        stacky_logger.flush_now(timeout=2.0)
        rows = run_with_retry(_leer_auditoria, label="plan254 lectura de auditoria")
        if rows:
            level, context = rows[0]
            break
        time.sleep(0.1)

    assert rows, "el bloqueo no dejó SystemLog"
    assert level == "warning"
    # El estado que se QUISO escribir tiene que quedar registrado.
    assert "error" in context


# ── 7. LOS POST-HOOKS SIGUEN CORRIENDO (C4) ───────────────────────────────────


def test_degradacion_bloqueada_corre_los_post_hooks(db):
    """C4 — si el guard salteara _run_post_hooks se rompería el sync con ADO."""
    from services import ticket_status

    seen: list[dict] = []

    def _spy(**kwargs):
        seen.append(kwargs)

    ticket_status.register_post_hook(_spy)
    try:
        tid = _new_ticket("completed")
        _on_execution_end(
        ticket_status,
            ticket_id=tid, execution_id=1616, final_status="error",
            agent_type="developer", error="claude code cli exited with code 1",
        )
    finally:
        ticket_status._POST_HOOKS.remove(_spy)

    assert seen, "el post-hook NO corrió con el guard activo"
    assert seen[-1]["final_status"] == "completed", (
        "el post-hook recibió el estado PEDIDO en vez del EFECTIVO"
    )


# ── F1-bis. EL VERDE PRESERVADO NO ES UN VERDE LIMPIO (C6) ────────────────────


def test_bloqueo_sella_pending_review(db):
    """Sin este sello, F1 cambiaría un falso ROJO por un falso VERDE."""
    from services import ticket_status

    tid = _new_ticket("completed")
    _on_execution_end(
        ticket_status,
        ticket_id=tid, execution_id=1617, final_status="error",
        agent_type="developer", error="claude code cli exited with code 1",
    )
    ev = _last_event(tid)
    assert ev is not None
    blocked = (ev["metadata"] or {}).get("blocked_downgrade")
    assert blocked is not None, "el evento no lleva blocked_downgrade"
    assert blocked["pending_review"] is True
    assert blocked["kind"] == "dirty_close_preserved_success"
    assert blocked["from"] == "completed" and blocked["to"] == "error"
    # El estado NO se toca: Stacky marca y muestra, decide el humano.
    assert ev["new_status"] == "completed"


# ── 8. CONTRATO CON EL VOCABULARIO (C3) ───────────────────────────────────────


def test_guard_solo_usa_estados_del_vocabulario():
    """Sin esto, un literal inventado ('published'/'failed') deja el guard INERTE."""
    from services import ticket_status
    from services.status_vocabulary import VALID_TICKET_STATUSES

    usados = ticket_status._SUCCESS_TERMINALS | ticket_status._NEVER_DOWNGRADE_TO
    assert usados <= VALID_TICKET_STATUSES, (
        f"el guard usa estados que NO existen: {sorted(usados - VALID_TICKET_STATUSES)}"
    )
    # Riel duro: cancelar es del operador y jamás se bloquea.
    assert "cancelled" not in ticket_status._NEVER_DOWNGRADE_TO
    assert "needs_review" not in ticket_status._NEVER_DOWNGRADE_TO


# ── 9. PLAN 280 F1-bis — EL WEBHOOK QUE PINTA DE ROJO UNA CORRIDA EXITOSA ─────
#
# Segundo falso rojo, independiente del clasificador y con la misma tesis: el
# trabajo se hizo y el camino de REPORTE lo destruye.
#
# `AgentExecution.duration_ms` (models.py:330) es un METODO sin @property, y
# `services/webhooks.py:219` lo consume como si fuera un campo:
#     round((row.duration_ms or 0) / 1000, 3) if row.duration_ms else None
# Un bound method es SIEMPRE truthy, asi que el guard pasa y la division
# explota con TypeError. Ese TypeError escapa por `agent_runner.py:1011`
# (llamada DESNUDA, a diferencia de claude_code_cli_runner.py:82 y
# codex_cli_runner.py:72 que la envuelven) y cae en el `except` de :1069,
# que marca la corrida `error`.
#
# Medido en la BD viva: ejecuciones 164, 165, 166 y 167 (2026-07-26, agente
# incident_dev, outputs de 7382/5621/3999/4859 chars, contrato passed:true
# score:100) con error_message EXACTAMENTE igual al TypeError de abajo.


def test_duration_ms_sigue_siendo_metodo_no_property():
    """Guard de PRESENCIA del defecto: fija la forma real de models.py:330.

    Sin este assert, el test de abajo podria pasar por accidente el dia que
    alguien convierta `duration_ms` en @property (lo que romperia a su vez
    AgentExecution.to_dict y ado_publisher.py:60, que ya lo llaman con
    parentesis). Si este assert falla, el fix de webhooks.py hay que revisarlo.
    """
    from models import AgentExecution

    assert not isinstance(
        AgentExecution.__dict__.get("duration_ms"), property
    ), "duration_ms paso a ser property: revisar webhooks.py y to_dict"


def test_payload_del_webhook_no_revienta_con_una_corrida_completa():
    """Reproduce el TypeError de las ejecuciones 164-167. ROJO antes del fix.

    El payload V2 se arma sobre una corrida EXITOSA (started/completed
    poblados, 49.308 s de duracion real, como las 4 corridas medidas).
    """
    from datetime import datetime, timedelta

    from models import AgentExecution
    from services.webhooks import _compact_execution_payload

    row = AgentExecution()
    row.id = 164
    row.ticket_id = 812
    row.agent_type = "incident_dev"
    row.status = "completed"
    row.started_at = datetime(2026, 7, 26, 17, 12, 0)
    row.completed_at = row.started_at + timedelta(seconds=49.308)
    row.metadata_json = '{"runtime": "github_copilot", "vscode_bridge": true}'

    payload = _compact_execution_payload(row)

    # 49308 ms / 1000 = 49.308 s — el valor que el webhook debia publicar.
    assert payload["duration_s"] == 49.308, (
        f"duration_s mal calculado: {payload['duration_s']!r}"
    )


def test_el_webhook_del_path_copilot_no_puede_tumbar_la_corrida():
    """Defensa en profundidad: `fire_for_execution` va envuelta en los 3 paths.

    claude_code_cli_runner.py:82 y codex_cli_runner.py:72 ya la protegen; las
    tres llamadas de agent_runner.py (797, 1011, 1072) estaban DESNUDAS. Se
    verifica por AST: toda llamada a `fire_for_execution` debe estar dentro de
    un `ast.Try`. Se cuenta primero la PRESENCIA para que el test no pase por
    accidente si el simbolo se renombra y el censo deja de ver nada.
    """
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    archivos = [
        backend / "agent_runner.py",
        backend / "services" / "claude_code_cli_runner.py",
        backend / "services" / "codex_cli_runner.py",
    ]

    # "Protegida" NO es "estar dentro de cualquier try": la llamada de
    # agent_runner.py:1011 vive dentro del try GIGANTE de la funcion, cuyo
    # except es justamente el que marca la corrida `error` (:1069). Eso es el
    # bug, no la defensa. El criterio real es una guarda DEDICADA: el try
    # inmediatamente envolvente tiene un cuerpo corto, como
    # claude_code_cli_runner.py:81-84 (cuerpo = 1 sentencia).
    MAX_CUERPO_GUARDA = 2

    total = 0
    desnudas: list[str] = []
    for path in archivos:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        padre: dict[int, ast.AST] = {}
        for nodo in ast.walk(tree):
            for hijo in ast.iter_child_nodes(nodo):
                padre[id(hijo)] = nodo

        for nodo in ast.walk(tree):
            if not isinstance(nodo, ast.Call):
                continue
            fn = nodo.func
            if (getattr(fn, "attr", None) or getattr(fn, "id", None)) != "fire_for_execution":
                continue
            total += 1

            # Subir hasta el primer Try que contenga a la llamada EN SU BODY.
            actual: ast.AST | None = nodo
            guarda: ast.Try | None = None
            while actual is not None:
                p = padre.get(id(actual))
                if isinstance(p, ast.Try) and any(
                    actual is stmt for stmt in p.body
                ):
                    guarda = p
                    break
                actual = p
            if guarda is None or len(guarda.body) > MAX_CUERPO_GUARDA:
                desnudas.append(f"{path.name}:{nodo.lineno}")

    assert total >= 5, f"el censo AST no ve las llamadas conocidas (vio {total})"
    assert desnudas == [], (
        f"fire_for_execution sin guarda DEDICADA (un webhook puede tumbar la "
        f"corrida): {desnudas}"
    )


# ── 10. PLAN 280 F1/F2 — EL DESENLACE MIRA EL TRABAJO ENTREGADO ──────────────
#
# `classify_outcome_reason` RECIBE el output (`last_result_text`,
# run_outcome.py:61) y lo usa SOLO para buscar marcadores de cuota (:91). La
# regla 8 (:99), la que decide "hubo trabajo pese al cierre sucio", no lo mira.
# Por eso la ejecucion 212 —19.593 chars de analisis tecnico entregado— quedo
# etiquetada `cli_failure`, que el propio modulo define (:22) como "rc != 0 SIN
# evidencia de trabajo".
#
# Y `outcome_reason_to_status` (:113), que ya mapea dirty_exit_after_work ->
# needs_review, tiene CERO referencias de produccion (censo AST). El plan 254
# escribio la respuesta correcta y nunca la cableo.


def test_has_delivered_work_usa_evidencia_objetiva():
    """G2: el trabajo se prueba con artefacto, no con el auto-reporte del agente."""
    from services.run_outcome import WORK_EVIDENCE_MIN_CHARS, has_delivered_work

    assert WORK_EVIDENCE_MIN_CHARS == 200
    # Sin nada: no hay trabajo.
    assert has_delivered_work() is False
    assert has_delivered_work(output="   ") is False
    assert has_delivered_work(output="x" * 199) is False
    # Output real por encima del umbral.
    assert has_delivered_work(output="x" * 200) is True
    # Un archivo escrito alcanza aunque el output sea corto.
    assert has_delivered_work(output="", artifact_count=1) is True
    # Las señales clasicas se siguen respetando.
    assert has_delivered_work(result_ok_seen=True) is True
    assert has_delivered_work(ticket_already_terminal=True) is True


def test_regla8_mira_el_trabajo_entregado_ejecucion_212():
    """Reproduce la ejecucion 212: rc=1, sin result ok, 19.593 chars entregados.

    Antes del fix devolvia 'cli_failure' -> 'error'. Es EL caso del operador:
    el analisis tecnico se genero, se valido y se reporto como fallo.
    """
    from services.run_outcome import classify_outcome_reason

    # Guard de PRESENCIA: sin trabajo, el veredicto duro NO cambia.
    assert classify_outcome_reason(return_code=1, work_delivered=False) == "cli_failure"

    reason = classify_outcome_reason(
        return_code=1,
        result_ok_seen=False,
        stall_fired=False,
        last_result_text="x" * 19593,
        work_delivered=True,
    )
    assert reason == "dirty_exit_after_work", (
        f"19.593 chars de trabajo entregado clasificados como {reason!r}"
    )


def test_stall_con_trabajo_entregado_no_es_cuelgue():
    """Regla 5: el watchdog cerro una sesion ociosa que YA habia entregado."""
    from services.run_outcome import classify_outcome_reason

    assert classify_outcome_reason(
        return_code=-15, stall_fired=True, work_delivered=False
    ) == "stall_no_work"
    assert classify_outcome_reason(
        return_code=-15, stall_fired=True, work_delivered=True
    ) == "stall_after_work"


def test_reconciliar_estado_es_un_TECHO_nunca_un_ascenso():
    """La taxonomia solo puede BAJAR a needs_review. Riel G1 + gate de calidad.

    La ejecucion 210 tiene reason=clean_exit (la taxonomia diria 'completed')
    pero su estado real es needs_review porque _evaluate_output_quality la
    degrado por contrato. Una sustitucion la ascenderia de vuelta y destruiria
    el gate de calidad. El techo la deja intacta.
    """
    from services.run_outcome import reconciliar_estado

    # Rescata el falso ROJO (execs 186-189, 211, 212).
    assert reconciliar_estado("error", "needs_review") == "needs_review"
    # Tapa el falso VERDE (execs 190 y 213, vivos en produccion).
    assert reconciliar_estado("completed", "needs_review") == "needs_review"
    # NO asciende: preserva la degradacion por calidad (exec 210).
    assert reconciliar_estado("needs_review", "completed") == "needs_review"
    # Un error genuino sigue siendo error.
    assert reconciliar_estado("error", "error") == "error"
    # Jamas fabrica un verde.
    for actual in ("error", "needs_review", "completed", "cancelled"):
        for tax in ("completed", "needs_review", "error"):
            assert reconciliar_estado(actual, tax) != "completed" or actual == "completed"


def test_ningun_reason_con_trabajo_termina_en_completed_automatico():
    """K5/K7: invariante duro. Stacky no declara exito por su cuenta."""
    from services.run_outcome import outcome_reason_to_status

    for reason in ("dirty_exit_after_work", "stall_after_work"):
        assert outcome_reason_to_status(reason) == "needs_review"
        assert outcome_reason_to_status(reason) != "completed"


def test_outcome_reason_to_status_dejo_de_ser_codigo_muerto():
    """K1: el censo AST de REFERENCIAS pasa de 0 a >=1 en produccion.

    Se cuenta por REFERENCIA (Name/Attribute/ImportFrom) y no solo por Call,
    porque una llamada por alias haria dar CERO a un censo de llamadas.
    """
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    prod = 0
    control = 0
    for path in backend.rglob("*.py"):
        partes = path.parts
        if "__pycache__" in partes or "venv" in partes or ".venv" in partes:
            continue
        if "tests" in partes or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for nodo in ast.walk(tree):
            if isinstance(nodo, ast.FunctionDef):
                continue  # la DEFINICION no es consumo
            nombres: list[str] = []
            if isinstance(nodo, ast.Name):
                nombres = [nodo.id]
            elif isinstance(nodo, ast.Attribute):
                nombres = [nodo.attr]
            elif isinstance(nodo, ast.ImportFrom):
                nombres = [a.name for a in nodo.names]
            if "outcome_reason_to_status" in nombres:
                prod += 1
            if "classify_outcome_reason" in nombres:
                control += 1

    # Guard de PRESENCIA: si el censo no ve lo que SI existe, esta roto y el
    # assert de abajo pasaria por accidente.
    assert control >= 4, f"el censo AST esta roto: vio {control} refs de control"
    assert prod >= 1, "outcome_reason_to_status sigue sin consumidores de produccion"


def test_codex_puede_producir_dirty_exit_after_work_sin_tocar_su_call_site():
    """C1(b) — la derivacion desde `last_result_text` le da paridad GRATIS a codex.

    codex_cli_runner.py:804 pasa `last_result_text` pero NO `result_ok_seen` ni
    `work_delivered` (quedan en su default False). Antes de este plan eso hacia
    que codex NUNCA pudiera producir `dirty_exit_after_work`: todo rc!=0 con
    trabajo entregado caia en `cli_failure` -> `error`. Reproduce la forma EXACTA
    de esa llamada.
    """
    from services.run_outcome import classify_outcome_reason

    # Guard de PRESENCIA: con output corto sigue siendo un fallo real.
    assert classify_outcome_reason(
        return_code=1, stall_fired=False, stderr_excerpt="", last_result_text="ups",
    ) == "cli_failure"

    # Misma firma que codex_cli_runner.py:804, ahora con trabajo entregado.
    assert classify_outcome_reason(
        return_code=1,
        stall_fired=False,
        stderr_excerpt="",
        last_result_text="x" * 5000,
    ) == "dirty_exit_after_work"


def test_un_cierre_sucio_con_trabajo_no_puede_terminar_en_completed():
    """C3 — cierra la divergencia entre los dos traductores.

    `_classify_run_outcome` manda `dirty_exit_after_work` a la familia
    `success`, donde `_evaluate_output_quality` puede devolver 'completed'.
    Sin el techo de F2, la MISMA razon daria 'completed' en Claude y
    'needs_review' en Codex. Las ejecuciones 190 y 213 son ese falso verde,
    vivo en produccion.
    """
    from services.claude_code_cli_runner import _REASON_TO_RUN_KIND
    from services.run_outcome import outcome_reason_to_status, reconciliar_estado

    for reason in ("dirty_exit_after_work", "stall_after_work"):
        # La familia del runner efectivamente lo rutea como exito...
        assert _REASON_TO_RUN_KIND[reason] == "success"
        # ...y aun asi el techo impide el verde, venga de donde venga.
        for estado_previo in ("completed", "error", "failed", "needs_review"):
            final = reconciliar_estado(estado_previo, outcome_reason_to_status(reason))
            assert final == "needs_review", (
                f"{reason} desde {estado_previo!r} termino en {final!r}"
            )


def test_el_techo_esta_cableado_en_el_runner_de_claude():
    """K1 en el sitio que importa: el runner CONSUME el traductor, no lo ignora.

    Se verifica por AST sobre el archivo del runner (no por grep: un grep sobre
    el comentario que explica el fix lo daria por cableado).
    """
    import ast
    from pathlib import Path

    runner = Path(__file__).resolve().parent.parent / "services" / "claude_code_cli_runner.py"
    tree = ast.parse(runner.read_text(encoding="utf-8"))

    simbolos: set[str] = set()
    for nodo in ast.walk(tree):
        if isinstance(nodo, ast.ImportFrom):
            simbolos.update(a.name for a in nodo.names)
        elif isinstance(nodo, ast.Name):
            simbolos.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            simbolos.add(nodo.attr)

    # Guard de PRESENCIA: el censo ve lo que ya existia antes de este plan.
    assert "classify_outcome_reason" in simbolos, "el censo AST del runner esta roto"
    assert "outcome_reason_to_status" in simbolos, "el techo NO esta cableado"
    assert "reconciliar_estado" in simbolos, "el reconciliador NO esta cableado"
    assert "has_delivered_work" in simbolos, "el runner no computa la evidencia"
