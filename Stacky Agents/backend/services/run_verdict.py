"""Plan 269 F0 — veredicto por evidencia. Módulo PURO.

Sin DB, sin red, sin disco, sin imports de `db`/`models`. Se testea solo.
(F8 agrega abajo dos funciones de conteo que sí importan DB, pero de forma
PEREZOSA y adentro de la función: la parte pura no se contamina.)

El plan 254 respondió "POR QUÉ terminó así" mirando el proceso. Este módulo
responde la otra mitad que pidió el operador: "¿produjo resultados y cumplió
su objetivo?". El veredicto es una DIMENSIÓN SEPARADA de `stacky_status`: no
es un estado nuevo y NUNCA cambia uno.
"""
from __future__ import annotations

from dataclasses import dataclass

# Los 3 niveles, de mejor a peor. Cerrado: no se agregan niveles.
VERDICT_LEVELS = ("exito", "advertencia", "error_real")

# Causa del veredicto. Cerrado. Toda causa mapea a exactamente un nivel.
# Son NUEVE. `cancelado_por_el_operador` está separada de
# `cierre_sucio_pendiente_de_revision` porque un run que el humano cortó a mano
# NO cerró mal, y decirle al operador "el proceso cerró mal" es mentirle.
VERDICT_CAUSES = (
    "cierre_limpio_con_entrega",           # exito
    "verde_sin_evidencia",                 # advertencia
    "evidencia_indeterminada",             # advertencia
    "cierre_sucio_pendiente_de_revision",  # advertencia
    "cancelado_por_el_operador",           # advertencia
    "falso_rojo_probable",                 # advertencia  ← el caso que pidió el operador
    "espera_cuota",                        # advertencia
    "error_sin_entrega_suficiente",        # error_real
    "bloqueado_antes_de_empezar",          # error_real
)

# Nombres de las señales de evidencia. Cerrado y ORDENADO (el orden se usa para
# serializar las listas presentes/ausentes/desconocidas de forma determinista).
EVIDENCE_SIGNALS = (
    "publicado_en_tracker",
    "cambio_en_repo",
    "gate_aceptacion_ok",
    "verificacion_ok",
    "entregable_presente",
)

# Peso de cada señal. Las 3 "fuertes" valen 2 porque son objetivas y externas al
# propio agente (una fila en agent_html_publish, un PR abierto, un gate que
# corrió). Las 2 "débiles" valen 1: un archivo en disco o una verificación
# pueden ser parciales.
_PESO = {
    "publicado_en_tracker": 2,
    "cambio_en_repo": 2,
    "gate_aceptacion_ok": 2,
    "verificacion_ok": 1,
    "entregable_presente": 1,
}
UMBRAL_ENTREGA = 2  # fuerza mínima para considerar que "produjo resultados"

# Nivel base derivado del estado terminal. `cancelled` es advertencia: el humano
# lo cortó, no es un fallo del sistema (y tiene causa propia).
# Las CLAVES son exactamente los 4 TERMINAL_STATUSES de
# services/status_vocabulary.py:11. Los 2 NO terminales (`idle`, `running`,
# status_vocabulary.py:14) NO están acá A PROPÓSITO: ver `_NO_TERMINALES`.
_STATUS_TO_BASE = {
    "completed": "exito",
    "needs_review": "advertencia",
    "cancelled": "advertencia",
    "error": "error_real",
}

# Un run que NO terminó no tiene veredicto. Devolver "advertencia" para un run
# en curso pintaba "Con advertencias" TODA la lista de corridas activas.
_NO_TERMINALES = frozenset({"idle", "running"})

_CAUSE_TO_LEVEL = {
    "cierre_limpio_con_entrega": "exito",
    "verde_sin_evidencia": "advertencia",
    "evidencia_indeterminada": "advertencia",
    "cierre_sucio_pendiente_de_revision": "advertencia",
    "cancelado_por_el_operador": "advertencia",
    "falso_rojo_probable": "advertencia",
    "espera_cuota": "advertencia",
    "error_sin_entrega_suficiente": "error_real",
    "bloqueado_antes_de_empezar": "error_real",
}

# Marcador que F6 escribe en el `reason` de cada corrección manual. Es el dato
# con el que verdict_agreement() mide si el veredicto está calibrado.
CORRECTION_MARKER = "[269] corrección manual de falso rojo"


@dataclass(frozen=True)
class EvidenceSignals:
    """Tri-estado por señal: True=presente, False=ausente, None=DESCONOCIDA.

    `None` es un valor de primera clase: significa "no pude mirar". Nunca se
    convierte en False silenciosamente (eso sería inventar evidencia negativa)
    ni en True (eso sería inventar un verde)."""

    publicado_en_tracker: bool | None = None
    cambio_en_repo: bool | None = None
    gate_aceptacion_ok: bool | None = None
    verificacion_ok: bool | None = None
    entregable_presente: bool | None = None

    def get(self, name: str) -> bool | None:
        return getattr(self, name, None)


@dataclass(frozen=True)
class RunVerdict:
    level: str                       # ∈ VERDICT_LEVELS
    cause: str                       # ∈ VERDICT_CAUSES
    strength: int                    # fuerza de entrega acumulada
    present: tuple[str, ...] = ()    # señales True, en orden de EVIDENCE_SIGNALS
    absent: tuple[str, ...] = ()     # señales False
    unknown: tuple[str, ...] = ()    # señales None

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "cause": self.cause,
            "strength": self.strength,
            "present": list(self.present),
            "absent": list(self.absent),
            "unknown": list(self.unknown),
        }


def delivery_strength(signals: EvidenceSignals) -> int:
    """Suma los pesos de las señales PRESENTES. `None` y `False` suman 0.

    Que None y False sumen igual es deliberado: la ignorancia no puede sumar
    confianza (principio P2)."""
    return sum(_PESO[name] for name in EVIDENCE_SIGNALS if signals.get(name) is True)


def _peor(a: str, b: str) -> str:
    """Devuelve el PEOR de dos niveles base. Nunca el mejor.

    Es el mecanismo que hace que el invariante I1 valga en TODOS los call-sites
    y no solo adentro de esta función."""
    return a if VERDICT_LEVELS.index(a) >= VERDICT_LEVELS.index(b) else b


def evaluate_verdict(
    *,
    run_status: str,                       # OBLIGATORIO. El estado del RUN manda.
    ticket_status: str | None = None,      # opcional. Solo puede EMPEORAR.
    outcome_reason: str | None = None,
    signals: EvidenceSignals | None = None,
) -> RunVerdict | None:
    """Devuelve un RunVerdict, o None si el run NO terminó. Puro y determinístico.

    CONTRATO — LEER ANTES DE CABLEAR.

    Está PROHIBIDO el patrón que colapsa las dos dimensiones en una:

        estado = (getattr(ticket, "stacky_status", None) or ex.status or "")   # ← BUG

    Eso rompe el invariante de negocio. Un ticket que hoy está `completed`
    (segundo intento OK, o el operador lo cerró a mano) con una ejecución vieja
    de `status="error"` producía veredicto `exito` / `cierre_limpio_con_entrega`.
    Y como el historial lista EJECUCIONES (N filas por ticket), TODAS las
    corridas fallidas de un ticket ya cerrado se pintaban "Terminó bien" al lado
    del chip "Error". Es el falso VERDE que P1 prohíbe. Un test que solo pruebe
    esta función NO puede ver ese bug: vive en la costura.

    REGLA innegociable:
      · El veredicto se ANCLA en `run_status`. Es la única fuente del nivel base.
      · `ticket_status` es una señal SECUNDARIA que solo puede EMPEORAR el nivel
        (`_peor`), jamás mejorarlo. Un ticket verde NO blanquea un run rojo.
      · Con esto I1 vale ESTRUCTURALMENTE en todo call-site: si `run_status ==
        "error"`, base es `error_real` y ninguna regla puede devolver `exito`.

    `None` para `idle`/`running`. Un run en curso NO tiene veredicto —
    devolverle "advertencia" pintaba de amarillo toda la lista de corridas
    activas. La UI no dibuja chip (describeVerdict(null) → null, F3).

    ORDEN DE PRECEDENCIA OBLIGATORIO — se evalúa en este orden y se devuelve en
    el PRIMER match. Sin este orden, dos reglas pueden matchear y el resultado
    es ambiguo para un modelo menor.

      0. run_status ∈ {"idle","running"} o vacío       → None (sin veredicto)
      1. outcome_reason == "preflight_blocked"        → bloqueado_antes_de_empezar (error_real)
      2. outcome_reason == "quota_exhausted"          → espera_cuota (advertencia)
      3. base == "error_real" y fuerza >= UMBRAL      → falso_rojo_probable (advertencia)
      4. base == "error_real"                         → error_sin_entrega_suficiente (error_real)
      5. run_status == "cancelled"                    → cancelado_por_el_operador (advertencia)
      6. base == "advertencia"                        → cierre_sucio_pendiente_de_revision
      7. base == "exito" y fuerza >= UMBRAL           → cierre_limpio_con_entrega (exito)
      8. base == "exito" y hay alguna señal None      → evidencia_indeterminada (advertencia)
      9. base == "exito" (resto)                      → verde_sin_evidencia (advertencia)

    Nota sobre 7 antes de 8: si ya hay UMBRAL de evidencia PRESENTE, una señal
    desconocida al lado no borra la evidencia que sí está. No fabrica un verde
    porque el base ya era verde (la regla 7 es inalcanzable desde un estado rojo:
    ahí está la garantía ESTRUCTURAL del invariante I1).

    Nota sobre 5 después de 3/4: un `cancelled` nunca llega a base "error_real",
    así que el orden entre ellas no cambia nada; se deja explícito para que el
    lector no tenga que razonarlo.

    Un `run_status` desconocido (ni terminal ni no-terminal) cae a base
    "advertencia" — nunca a un verde.
    """
    estado = (run_status or "").strip()
    if not estado or estado in _NO_TERMINALES:
        return None

    sig = signals or EvidenceSignals()
    base = _STATUS_TO_BASE.get(estado, "advertencia")

    # El ticket solo EMPEORA. Si el ticket está peor que el run (p.ej. el
    # operador marcó la incidencia `error` sobre un run `completed`), el
    # veredicto baja. Si el ticket está MEJOR, se IGNORA: un ticket verde jamás
    # blanquea un run rojo. Un ticket no terminal o desconocido no opina.
    t_estado = (ticket_status or "").strip()
    if t_estado in _STATUS_TO_BASE:
        base = _peor(base, _STATUS_TO_BASE[t_estado])

    fuerza = delivery_strength(sig)

    present = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is True)
    absent = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is False)
    unknown = tuple(n for n in EVIDENCE_SIGNALS if sig.get(n) is None)

    if outcome_reason == "preflight_blocked":
        cause = "bloqueado_antes_de_empezar"
    elif outcome_reason == "quota_exhausted":
        cause = "espera_cuota"
    elif base == "error_real" and fuerza >= UMBRAL_ENTREGA:
        cause = "falso_rojo_probable"
    elif base == "error_real":
        cause = "error_sin_entrega_suficiente"
    elif estado == "cancelled":
        cause = "cancelado_por_el_operador"
    elif base == "advertencia":
        cause = "cierre_sucio_pendiente_de_revision"
    elif fuerza >= UMBRAL_ENTREGA:
        cause = "cierre_limpio_con_entrega"
    elif unknown:
        cause = "evidencia_indeterminada"
    else:
        cause = "verde_sin_evidencia"

    return RunVerdict(
        level=_CAUSE_TO_LEVEL[cause],
        cause=cause,
        strength=fuerza,
        present=present,
        absent=absent,
        unknown=unknown,
    )


# ── F8 — KPI medido. READ-ONLY, bajo demanda, sin loops ───────────────────────

_EMPTY_COUNTS_KEYS = (
    "days", "limit", "sampled", "exito", "advertencia", "error_real",
    "falso_rojo_probable",
)


def _counts_base(days: int, limit: int) -> dict:
    """Las SIETE claves, siempre. `falso_rojo_probable` arranca en None porque
    sin evidencia no se puede afirmar que no haya falsos rojos (P2 aplicado al
    propio KPI del plan: la ignorancia no se reporta como buena noticia)."""
    return {
        "days": days, "limit": limit, "sampled": True,
        "exito": 0, "advertencia": 0, "error_real": 0,
        "falso_rojo_probable": None,
    }


def count_by_level(days: int = 30, limit: int = 200) -> dict:
    """Cuántas corridas terminadas de los últimos N días caen en cada nivel.

    READ-ONLY: no escribe una sola fila. Bajo demanda: NO corre en un loop ni en
    un daemon. Nunca lanza: ante cualquier fallo devuelve las 7 claves con los
    niveles en 0 y `falso_rojo_probable` en None.

    MUESTRA ACOTADA, no censo:
      · Toma como mucho `limit` ejecuciones terminadas (default 200, el mismo
        tope de run_reconciliation.scan_recent, services/run_reconciliation.py:168).
      · Resuelve la evidencia con services.run_evidence.collect_for_executions,
        que trae su propio presupuesto de tiempo: si se agota, las señales quedan
        None y el conteo lo refleja. NO se reimplementa la recolección.
      · Cada fila se juzga con evaluate_verdict(run_status=..., ticket_status=...).
      · Si los colectores están OFF, `falso_rojo_probable` es None, NO 0.
      · Declara `sampled` y `limit` para que nadie lea el número como un total
        del histórico.

    Vive acá y no en un módulo nuevo para que este archivo siga siendo el único
    dueño del vocabulario del veredicto. La parte pura no se contamina: los
    imports de DB son perezosos y locales.
    """
    out = _counts_base(days, limit)
    try:
        from datetime import datetime, timedelta

        from db import session_scope
        from models import AgentExecution
        from services.run_evidence import collectors_enabled, collect_for_executions

        desde = datetime.utcnow() - timedelta(days=int(days))
        with session_scope() as session:
            rows = (
                session.query(AgentExecution)
                .filter(AgentExecution.started_at >= desde)
                .filter(AgentExecution.status.notin_(tuple(sorted(_NO_TERMINALES))))
                .order_by(AgentExecution.started_at.desc())
                .limit(int(limit))
                .all()
            )
            con_colectores = bool(collectors_enabled())
            signals_by_id = collect_for_executions(session, rows) if con_colectores else {}
            if con_colectores:
                out["falso_rojo_probable"] = 0
            for ex in rows:
                meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
                ticket = getattr(ex, "ticket", None)
                v = evaluate_verdict(
                    run_status=(ex.status or ""),
                    ticket_status=getattr(ticket, "stacky_status", None),
                    outcome_reason=meta.get("outcome_reason"),
                    signals=signals_by_id.get(ex.id),
                )
                if v is None:
                    continue
                if v.level in out:
                    out[v.level] = int(out[v.level]) + 1
                if con_colectores and v.cause == "falso_rojo_probable":
                    out["falso_rojo_probable"] = int(out["falso_rojo_probable"]) + 1
        return out
    except Exception:  # noqa: BLE001 — un KPI jamás tumba a su llamador
        return _counts_base(days, limit)


def verdict_agreement(days: int = 30) -> dict:
    """Precisión OBSERVADA del veredicto `falso_rojo_probable`. READ-ONLY.

    propuestos  = corridas de los últimos N días con cause == falso_rojo_probable
    confirmados = TicketStatusEvent de esos tickets cuyo `reason` empieza con
                  CORRECTION_MARKER (el operador apretó el botón de F6)
    ratio       = confirmados / propuestos, o None si propuestos == 0

    Bajo demanda: NO corre en loop ni en daemon. No escribe una sola fila.
    Nunca lanza: ante cualquier fallo devuelve las 3 claves en 0/None.

    RIEL DURO: este número se MUESTRA, jamás se usa para auto-ajustar `_PESO` ni
    `UMBRAL_ENTREGA`. Stacky no se auto-tunea: le da al operador la evidencia
    para que ÉL decida si mover el umbral en un plan futuro. Vigilado por
    `test_agreement_no_muta_los_pesos`.
    """
    out = {"days": days, "propuestos": 0, "confirmados": 0, "ratio": None}
    try:
        from datetime import datetime, timedelta

        from db import session_scope
        from models import AgentExecution
        # OJO: TicketStatusEvent NO vive en models.py — se declara en
        # services/ticket_status.py:79. Importarlo de models da ImportError
        # (medido). Sus columnas son `old_status`/`new_status`, no from_/to_.
        from services.run_evidence import collect_for_executions
        from services.ticket_status import TicketStatusEvent

        desde = datetime.utcnow() - timedelta(days=int(days))
        with session_scope() as session:
            rows = (
                session.query(AgentExecution)
                .filter(AgentExecution.started_at >= desde)
                .filter(AgentExecution.status.notin_(tuple(sorted(_NO_TERMINALES))))
                .order_by(AgentExecution.started_at.desc())
                .limit(200)
                .all()
            )
            signals_by_id = collect_for_executions(session, rows)
            tickets_propuestos: set[int] = set()
            for ex in rows:
                meta = ex.metadata_dict if isinstance(ex.metadata_dict, dict) else {}
                ticket = getattr(ex, "ticket", None)
                v = evaluate_verdict(
                    run_status=(ex.status or ""),
                    ticket_status=getattr(ticket, "stacky_status", None),
                    outcome_reason=meta.get("outcome_reason"),
                    signals=signals_by_id.get(ex.id),
                )
                if v is not None and v.cause == "falso_rojo_probable":
                    out["propuestos"] = int(out["propuestos"]) + 1
                    if getattr(ex, "ticket_id", None) is not None:
                        tickets_propuestos.add(int(ex.ticket_id))

            if tickets_propuestos:
                eventos = (
                    session.query(TicketStatusEvent)
                    .filter(TicketStatusEvent.ticket_id.in_(sorted(tickets_propuestos)))
                    .all()
                )
                out["confirmados"] = sum(
                    1 for e in eventos
                    if str(getattr(e, "reason", "") or "").startswith(CORRECTION_MARKER)
                )

        if out["propuestos"]:
            out["ratio"] = round(int(out["confirmados"]) / int(out["propuestos"]), 4)
        return out
    except Exception:  # noqa: BLE001
        return {"days": days, "propuestos": 0, "confirmados": 0, "ratio": None}
