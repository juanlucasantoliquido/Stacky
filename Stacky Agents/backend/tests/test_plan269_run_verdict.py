"""Plan 269 F0 + F8 — Tests del veredicto por evidencia.

F0 es PURO: sin DB, sin red, sin disco. F8 agrega 9 tests de los contadores
(que sí tocan DB, con dobles).

29 casos: 20 de F0 + 9 de F8.
"""
from __future__ import annotations

import itertools
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.run_outcome import OUTCOME_REASONS  # noqa: E402
from services.run_verdict import (  # noqa: E402
    CORRECTION_MARKER,
    EVIDENCE_SIGNALS,
    UMBRAL_ENTREGA,
    VERDICT_CAUSES,
    VERDICT_LEVELS,
    EvidenceSignals,
    _CAUSE_TO_LEVEL,
    _NO_TERMINALES,
    _PESO,
    _STATUS_TO_BASE,
    count_by_level,
    delivery_strength,
    evaluate_verdict,
    verdict_agreement,
)


@pytest.fixture(autouse=True, scope="module")
def _db_lista():
    """Las tablas tienen que existir antes de sembrar: sin init_db() la sqlite en
    memoria esta vacia y cualquier INSERT da OperationalError (medido)."""
    from db import init_db

    init_db()
    return True

# Los 9 reasons reales + None (el plan lo midió: len(OUTCOME_REASONS) == 9).
_REASONS = [r[0] if isinstance(r, tuple) else r for r in OUTCOME_REASONS] + [None]
_TRI = (True, False, None)
# 3^5 = 243 combinaciones de evidencia.
_EVIDENCIA = [
    EvidenceSignals(**dict(zip(EVIDENCE_SIGNALS, combo)))
    for combo in itertools.product(_TRI, repeat=5)
]


def test_1_todo_nivel_pertenece_al_vocabulario():
    estados = list(_STATUS_TO_BASE) + ["basura"]
    for estado in estados:
        for sig in _EVIDENCIA:
            for reason in _REASONS:
                v = evaluate_verdict(run_status=estado, outcome_reason=reason, signals=sig)
                assert v is not None
                assert v.level in VERDICT_LEVELS
                assert v.cause in VERDICT_CAUSES


def test_2_I1_un_error_jamas_recibe_exito():
    """INVARIANTE DURO del plan."""
    for sig in _EVIDENCIA:
        for reason in _REASONS:
            v = evaluate_verdict(run_status="error", outcome_reason=reason, signals=sig)
            assert v is not None
            assert v.level != "exito", f"falso VERDE con {reason=} {sig=}"


def test_3_I1b_el_ticket_completed_no_blanquea_un_run_error():
    """Grilla COMPLETA: 243 evidencias x 7 ticket_status x 10 reasons = 17.010."""
    from services.status_vocabulary import VALID_TICKET_STATUSES

    tickets = list(VALID_TICKET_STATUSES) + ["basura"]
    assert len(tickets) == 7, f"se esperaban 7 ticket_status, hay {len(tickets)}"
    casos = 0
    for t in tickets:
        for sig in _EVIDENCIA:
            for reason in _REASONS:
                v = evaluate_verdict(
                    run_status="error", ticket_status=t,
                    outcome_reason=reason, signals=sig,
                )
                casos += 1
                assert v is not None
                assert v.level != "exito", f"el ticket {t!r} blanqueo un run error"
    assert casos == 17010, f"grilla incompleta: {casos} casos (se esperaban 17.010)"

    # Caso testigo explicito del plan.
    v = evaluate_verdict(
        run_status="error", ticket_status="completed",
        signals=EvidenceSignals(publicado_en_tracker=True),
    )
    assert v is not None
    assert v.cause == "falso_rojo_probable"
    assert v.level == "advertencia"


def test_4_el_ticket_solo_empeora_nunca_mejora():
    for run in _STATUS_TO_BASE:
        for t in list(_STATUS_TO_BASE) + ["basura", None, ""]:
            for sig in _EVIDENCIA[::17]:   # muestra determinista de la grilla
                sin_t = evaluate_verdict(run_status=run, signals=sig)
                con_t = evaluate_verdict(run_status=run, ticket_status=t, signals=sig)
                assert sin_t is not None and con_t is not None
                assert VERDICT_LEVELS.index(con_t.level) >= VERDICT_LEVELS.index(sin_t.level), (
                    f"el ticket {t!r} MEJORO el veredicto de un run {run!r}"
                )


def test_5_I2_desconocido_nunca_mejora():
    # None y False suman IGUAL en delivery_strength: la ignorancia no puede sumar
    # confianza. Los pesos son 2/2/2/1/1 y el umbral 2.
    assert delivery_strength(EvidenceSignals()) == 0
    assert delivery_strength(EvidenceSignals(**{n: False for n in EVIDENCE_SIGNALS})) == 0
    assert delivery_strength(EvidenceSignals(**{n: True for n in EVIDENCE_SIGNALS})) == 8
    assert UMBRAL_ENTREGA == 2

    for señal in EVIDENCE_SIGNALS:
        for estado in _STATUS_TO_BASE:
            con_none = evaluate_verdict(
                run_status=estado, signals=EvidenceSignals(**{señal: None}),
            )
            con_false = evaluate_verdict(
                run_status=estado, signals=EvidenceSignals(**{señal: False}),
            )
            assert con_none is not None and con_false is not None
            assert VERDICT_LEVELS.index(con_none.level) >= VERDICT_LEVELS.index(con_false.level)


def test_6_falso_rojo_probable_con_publicacion():
    v = evaluate_verdict(
        run_status="error", signals=EvidenceSignals(publicado_en_tracker=True),
    )
    assert v is not None
    assert v.cause == "falso_rojo_probable"
    assert v.level == "advertencia"
    assert v.strength == 2


def test_7_falso_rojo_probable_con_dos_debiles():
    v = evaluate_verdict(
        run_status="error",
        signals=EvidenceSignals(verificacion_ok=True, entregable_presente=True),
    )
    assert v is not None
    assert v.strength == 2
    assert v.cause == "falso_rojo_probable"


def test_8_error_con_una_sola_debil_sigue_siendo_error():
    v = evaluate_verdict(
        run_status="error", signals=EvidenceSignals(entregable_presente=True),
    )
    assert v is not None
    assert v.strength == 1
    assert v.cause == "error_sin_entrega_suficiente"
    assert v.level == "error_real"


def test_9_preflight_gana_sobre_toda_evidencia():
    todas = EvidenceSignals(**{n: True for n in EVIDENCE_SIGNALS})
    v = evaluate_verdict(
        run_status="completed", outcome_reason="preflight_blocked", signals=todas,
    )
    assert v is not None
    assert v.cause == "bloqueado_antes_de_empezar"
    assert v.level == "error_real"


def test_10_cuota_gana_sobre_error():
    v = evaluate_verdict(run_status="error", outcome_reason="quota_exhausted")
    assert v is not None
    assert v.cause == "espera_cuota"
    assert v.level == "advertencia"


def test_11_verde_sin_evidencia_es_advertencia():
    v = evaluate_verdict(
        run_status="completed",
        signals=EvidenceSignals(**{n: False for n in EVIDENCE_SIGNALS}),
    )
    assert v is not None
    assert v.cause == "verde_sin_evidencia"
    assert v.level == "advertencia"


def test_12_verde_con_desconocidas_es_advertencia():
    v = evaluate_verdict(
        run_status="completed",
        signals=EvidenceSignals(**{n: None for n in EVIDENCE_SIGNALS}),
    )
    assert v is not None
    assert v.cause == "evidencia_indeterminada"
    assert v.level == "advertencia"


def test_13_verde_con_entrega_es_exito():
    v = evaluate_verdict(
        run_status="completed", signals=EvidenceSignals(publicado_en_tracker=True),
    )
    assert v is not None
    assert v.cause == "cierre_limpio_con_entrega"
    assert v.level == "exito"


def test_14_needs_review_es_advertencia():
    for sig in _EVIDENCIA[::29]:
        v = evaluate_verdict(run_status="needs_review", signals=sig)
        assert v is not None
        assert v.cause == "cierre_sucio_pendiente_de_revision"
        assert v.level == "advertencia"


def test_15_cancelado_no_dice_cierre_sucio():
    for sig in _EVIDENCIA[::29]:
        v = evaluate_verdict(run_status="cancelled", signals=sig)
        assert v is not None
        assert v.cause == "cancelado_por_el_operador"
        assert v.level == "advertencia"
        assert v.cause != "cierre_sucio_pendiente_de_revision"


def test_16_no_terminal_no_tiene_veredicto():
    for estado in (*sorted(_NO_TERMINALES), "", "   "):
        for sig in _EVIDENCIA[::37]:
            for reason in _REASONS:
                assert evaluate_verdict(
                    run_status=estado, outcome_reason=reason, signals=sig,
                ) is None


def test_17_listas_present_absent_unknown_particionan():
    for sig in _EVIDENCIA:
        v = evaluate_verdict(run_status="completed", signals=sig)
        assert v is not None
        p, a, u = set(v.present), set(v.absent), set(v.unknown)
        assert p | a | u == set(EVIDENCE_SIGNALS)
        assert not (p & a) and not (p & u) and not (a & u)


def test_18_causa_mapea_a_un_solo_nivel():
    assert set(_CAUSE_TO_LEVEL) == set(VERDICT_CAUSES)
    assert len(VERDICT_CAUSES) == 9
    assert all(v in VERDICT_LEVELS for v in _CAUSE_TO_LEVEL.values())


def test_19_no_agrega_estados_al_vocabulario():
    from services.status_vocabulary import VALID_TICKET_STATUSES

    for nivel in VERDICT_LEVELS:
        assert nivel not in VALID_TICKET_STATUSES
    assert set(_STATUS_TO_BASE) | set(_NO_TERMINALES) == set(VALID_TICKET_STATUSES)


def test_20_espejo_ts_no_tiene_drift():
    """A2 — el .ts de F3 debe nombrar TODAS las causas y señales del .py."""
    ts = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "runVerdict.ts"
    if not ts.is_file():          # F3 todavia no implementada: no rompe F0
        pytest.skip("runVerdict.ts aun no existe (F3 pendiente)")
    texto = ts.read_text(encoding="utf-8")
    faltan = [n for n in (*VERDICT_CAUSES, *EVIDENCE_SIGNALS, *VERDICT_LEVELS) if n not in texto]
    assert not faltan, f"drift Python->TS: la UI no conoce {faltan}"


# ── F8 — los contadores ───────────────────────────────────────────────────────

_SIETE = {"days", "limit", "sampled", "exito", "advertencia", "error_real",
          "falso_rojo_probable"}


def test_21_count_by_level_declara_las_7_claves_siempre():
    out = count_by_level()
    assert set(out) == _SIETE, f"faltan/sobran claves: {set(out) ^ _SIETE}"
    assert out["sampled"] is True
    assert "falso_rojo_probable" in out


def test_22_count_by_level_nunca_lanza(monkeypatch):
    import services.run_verdict as rv

    def _boom(*a, **kw):
        raise RuntimeError("db caida")

    monkeypatch.setattr("db.session_scope", _boom, raising=False)
    out = rv.count_by_level(days=7, limit=5)
    assert set(out) == _SIETE
    assert out["exito"] == 0 and out["advertencia"] == 0 and out["error_real"] == 0
    assert out["falso_rojo_probable"] is None


def test_23_count_by_level_no_escribe(monkeypatch):
    """Cualquier intento de escritura revienta el test, no el conteo."""
    import db as db_mod

    real = db_mod.session_scope

    class _NoWrite:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            if name in ("add", "add_all", "merge", "delete", "commit", "flush"):
                def _prohibido(*a, **kw):
                    raise AssertionError(f"count_by_level llamo a session.{name}")
                return _prohibido
            return getattr(self._inner, name)

    class _Ctx:
        def __enter__(self):
            self._cm = real()
            return _NoWrite(self._cm.__enter__())

        def __exit__(self, *exc):
            return self._cm.__exit__(*exc)

    monkeypatch.setattr(db_mod, "session_scope", lambda: _Ctx())
    out = count_by_level(days=1, limit=3)
    assert set(out) == _SIETE


def test_24_count_by_level_usa_los_colectores(monkeypatch):
    """El KPI no puede ser un cero estructural: tiene que consultar evidencia."""
    from datetime import datetime

    from db import session_scope
    from models import AgentExecution, Ticket
    from services import run_evidence

    with session_scope() as s:
        t = Ticket(ado_id=6901, project="P269", title="t", ado_state="Active",
                   stacky_status="error", tracker_type="azure_devops",
                   work_item_type="Bug")
        s.add(t)
        s.flush()
        ex = AgentExecution(ticket_id=t.id, agent_type="developer", status="error",
                            input_context_json="[]", started_by="test",
                            started_at=datetime.utcnow())
        s.add(ex)
        s.flush()
        exec_id = ex.id

    monkeypatch.setattr(
        run_evidence, "collect_for_executions",
        lambda session, executions: {
            e.id: EvidenceSignals(publicado_en_tracker=True) for e in executions
        },
    )
    out = count_by_level(days=1, limit=200)
    assert out["falso_rojo_probable"] is not None
    assert out["falso_rojo_probable"] >= 1, (
        f"el KPI no vio el falso rojo sembrado (exec {exec_id}): {out}"
    )


def test_25_count_by_level_esta_acotado(monkeypatch):
    """El conteo no crece con la antiguedad del proyecto."""
    from services import run_evidence

    vistos = {}

    def _spy(session, executions):
        vistos["n"] = len(executions)
        return {}

    monkeypatch.setattr(run_evidence, "collect_for_executions", _spy)
    count_by_level(days=3650, limit=7)
    assert vistos.get("n", 0) <= 7, f"collect_for_executions recibio {vistos}"


def test_26_count_by_level_sin_colectores_reporta_null(monkeypatch):
    """Sin evidencia NO se afirma 'no hay falsos rojos': se dice que no se sabe."""
    from services import run_evidence

    monkeypatch.setattr(run_evidence, "collectors_enabled", lambda: False)
    out = count_by_level(days=1, limit=5)
    assert out["falso_rojo_probable"] is None
    for nivel in ("exito", "advertencia", "error_real"):
        assert isinstance(out[nivel], int)


def test_27_agreement_declara_las_3_claves_siempre():
    out = verdict_agreement(days=30)
    assert set(out) == {"days", "propuestos", "confirmados", "ratio"}
    if out["propuestos"] == 0:
        assert out["ratio"] is None, "0 de 0 no es 0% de acierto, es 'no se'"


def test_28_agreement_cuenta_solo_el_marcador_del_269(monkeypatch):
    from datetime import datetime

    from db import session_scope
    from models import AgentExecution, Ticket
    from services import run_evidence
    # TicketStatusEvent se declara en services/ticket_status.py:79, NO en models.
    from services.ticket_status import TicketStatusEvent

    with session_scope() as s:
        t = Ticket(ado_id=6902, project="P269", title="t2", ado_state="Active",
                   stacky_status="error", tracker_type="azure_devops",
                   work_item_type="Bug")
        s.add(t)
        s.flush()
        tid = t.id
        s.add(AgentExecution(ticket_id=tid, agent_type="developer", status="error",
                             input_context_json="[]", started_by="test",
                             started_at=datetime.utcnow()))
        s.add(TicketStatusEvent(ticket_id=tid, old_status="error",
                                new_status="completed", changed_by="op",
                                reason="cierre manual"))
        s.flush()

    monkeypatch.setattr(
        run_evidence, "collect_for_executions",
        lambda session, executions: {
            e.id: EvidenceSignals(publicado_en_tracker=True) for e in executions
        },
    )
    sin_marcador = verdict_agreement(days=1)
    assert sin_marcador["propuestos"] >= 1
    base_confirmados = sin_marcador["confirmados"]

    with session_scope() as s:
        s.add(TicketStatusEvent(ticket_id=tid, old_status="error",
                                new_status="completed", changed_by="op",
                                reason=f"{CORRECTION_MARKER} (execution 1)"))
        s.flush()

    con_marcador = verdict_agreement(days=1)
    assert con_marcador["confirmados"] == base_confirmados + 1, (
        "solo el marcador del 269 cuenta como acuerdo con el veredicto"
    )


def test_29_agreement_no_muta_los_pesos():
    """Riel duro: el sistema NO se auto-calibra, solo informa."""
    antes_peso = dict(_PESO)
    antes_umbral = UMBRAL_ENTREGA
    verdict_agreement(days=30)
    count_by_level(days=30)
    import services.run_verdict as rv

    assert dict(rv._PESO) == antes_peso
    assert rv.UMBRAL_ENTREGA == antes_umbral

