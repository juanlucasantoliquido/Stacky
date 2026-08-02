"""Plan 284 — Minería determinista del corpus de tickets para documentación.

Barre los tickets del proyecto y los clasifica en señal vs ruido con criterios
auditables (sin LLM). El resultado alimenta el contexto del Documentador.

Por qué el triage NO lo hace el LLM: un scoring por LLM sobre 228 tickets es
caro, no reproducible y no auditable. Esto es aritmética sobre campos que ya
están en la tabla: se puede explicar, testear y discutir.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Umbrales del triage. Constantes con nombre: son el contrato auditable.
MIN_DESCRIPTION_CHARS = 200      # 112 de 228 tickets caen debajo (medido 2026-08-01)
MIN_TITLE_CHARS = 15
STRONG_SIGNAL_CHARS = 800

# Títulos que no aportan nada aunque el ticket exista.
_NOISE_TITLE_RE = re.compile(
    r"^\s*(test|prueba|tmp|temp|borrar|delete|asdf|xxx+|aaa+|sin titulo|untitled|todo)\b",
    re.IGNORECASE,
)
# Tickets sintéticos del propio Stacky (no son historia del proyecto).
_SYNTHETIC_TRACKERS = frozenset({"demo"})


# ── FIX C3 (bloqueante de la v1) ──────────────────────────────────────────
# La v1 hacía: _SYNTHETIC_ADO_IDS = frozenset({-7}) y evaluaba `external_id in
# _SYNTHETIC_ADO_IDS`. Estaba mal por DOS motivos, ambos medidos en la base viva
# el 2026-08-01:
#   1) -7 es sentinela de **ado_id** (doc_documenter._CONVERSATION_ADO_ID), NO de
#      external_id. La fila cuyo external_id == -7 tiene ado_id == -2: es otro
#      sentinela distinto.
#   2) No son "unos pocos": hay **103 filas con ado_id < 0** de 228.
# Con el frozenset de un elemento, el filtro capturaba ~1 de 103.
# Regla correcta: cualquier id negativo es sintético. Es aritmética, no catálogo.
def _es_sintetico(ado_id: int | None, external_id: int | None) -> bool:
    """True si el ticket es interno de Stacky (ids sentinela negativos)."""
    for v in (ado_id, external_id):
        try:
            if v is not None and int(v) < 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


# ── FIX C13 — estados que marcan un ticket como CERRADO/OBSOLETO ──────────
# El operador pidió explícitamente distinguir "obsoletos". La v1 aceptaba
# `ado_state` como parámetro y NUNCA lo usaba. Estos son los estados REALES
# medidos en la base viva (2026-08-01), con su conteo:
#   Active 109 | opened 63 | Done 23 | Doing 12 | Reviewed by Dev 11
#   To Do 6 | Done by dev 2 | New 1 | Done by AI 1
# Un ticket cerrado NO es basura: documenta lo que YA se hizo, que es
# justamente la historia que buscamos. Pero un ticket cerrado y ADEMÁS flaco
# no aporta nada. Por eso el cierre no penaliza solo: modula.
_CLOSED_STATES = frozenset({
    "done", "done by dev", "done by ai", "closed", "resolved", "completed",
})
_ACTIVE_STATES = frozenset({
    "active", "opened", "doing", "new", "to do", "reviewed by dev",
})


@dataclass
class TicketVerdict:
    ticket_id: int
    external_id: int | None
    tracker_type: str
    title: str
    verdict: str            # "signal" | "noise"
    reasons: list[str] = field(default_factory=list)
    score: int = 0


def classify_ticket(*, ticket_id: int, ado_id: int | None,
                    external_id: int | None, tracker_type: str,
                    title: str, description: str, ado_state: str,
                    work_item_type: str) -> TicketVerdict:
    """Veredicto determinista de un ticket. PURA, sin I/O. Nunca lanza.

    Puntuación (suma de enteros; >= 2 => "signal"):
      +2  len(description) >= STRONG_SIGNAL_CHARS      (descripción rica)
      +1  len(description) >= MIN_DESCRIPTION_CHARS    (descripción mínima)
      +1  len(title.strip()) >= MIN_TITLE_CHARS        (título descriptivo)
      +1  work_item_type no vacío y distinto de "Task" (épicas/features documentan mejor)
      +1  ado_state cerrado Y descripción >= MIN_DESCRIPTION_CHARS
          (un ticket TERMINADO y bien descrito es la mejor historia que existe)
      -2  ado_state cerrado Y descripción < MIN_DESCRIPTION_CHARS
          (cerrado y flaco = obsoleto, exactamente la "basura" del pedido)
      -3  tracker_type en _SYNTHETIC_TRACKERS
      -3  _es_sintetico(ado_id, external_id)
      -2  el título matchea _NOISE_TITLE_RE
      -2  description vacía

    `reasons` guarda un string por regla aplicada (auditoría: el operador puede
    leer POR QUÉ un ticket quedó afuera).
    """
    reasons: list[str] = []
    score = 0
    desc = (description or "").strip()
    ttl = (title or "").strip()
    estado = (ado_state or "").strip().lower()

    if len(desc) >= STRONG_SIGNAL_CHARS:
        score += 2
        reasons.append(f"descripcion_extensa:{len(desc)}")
    if len(desc) >= MIN_DESCRIPTION_CHARS:
        score += 1
        reasons.append(f"descripcion_suficiente:{len(desc)}")
    if len(ttl) >= MIN_TITLE_CHARS:
        score += 1
        reasons.append(f"titulo_descriptivo:{len(ttl)}")
    wit = (work_item_type or "").strip()
    if wit and wit.lower() != "task":
        score += 1
        reasons.append(f"tipo_jerarquico:{wit}")
    if estado in _CLOSED_STATES:
        if len(desc) >= MIN_DESCRIPTION_CHARS:
            score += 1
            reasons.append(f"cerrado_y_documentado:{estado}")
        else:
            score -= 2
            reasons.append(f"cerrado_sin_contenido:{estado}")
    if (tracker_type or "").strip().lower() in _SYNTHETIC_TRACKERS:
        score -= 3
        reasons.append("tracker_sintetico")
    if _es_sintetico(ado_id, external_id):
        score -= 3
        reasons.append("ticket_interno_de_stacky")
    if _NOISE_TITLE_RE.match(ttl):
        score -= 2
        reasons.append("titulo_ruido")
    if not desc:
        score -= 2
        reasons.append("sin_descripcion")

    verdict = "signal" if score >= 2 else "noise"
    return TicketVerdict(ticket_id=ticket_id, external_id=external_id,
                         tracker_type=(tracker_type or ""), title=ttl,
                         verdict=verdict, reasons=reasons, score=score)


def mine_project_tickets(project_name: str, *, max_tickets: int | None = None,
                         scope: str = "project") -> dict:
    """Barre los tickets y devuelve el resumen del triage.

    `scope`:
      - "project" (default): sólo los del proyecto, con match CASE-INSENSITIVE.
      - "all": todo el corpus, sin filtro de proyecto.

    Salida (forma GARANTIZADA, todas las claves siempre presentes):
      {"enabled": bool, "scope": str, "total": int, "signal": int, "noise": int,
       "by_tracker": {tracker: int}, "verdicts": [TicketVerdict...],
       "truncated": bool}

    Con la flag OFF devuelve la forma completa con enabled=False y ceros.
    Nunca lanza: ante error de DB loguea y devuelve la forma vacía.

    SOLO LECTURA: session.query(...) sin add/delete/commit.
    """
    from config import config as _cfg
    empty = {"enabled": False, "scope": scope, "total": 0, "signal": 0,
             "noise": 0, "by_tracker": {}, "verdicts": [], "total_rows": 0,
             "truncated": False}
    if not bool(getattr(_cfg, "STACKY_DOCS_TICKET_MINING_ENABLED", False)):
        return empty
    cap = int(max_tickets if max_tickets is not None
              else getattr(_cfg, "STACKY_DOCS_TICKET_MINING_MAX", 500))
    try:
        from sqlalchemy import func
        from db import session_scope
        from models import Ticket
        verdicts: list[TicketVerdict] = []
        by_tracker: dict[str, int] = {}
        with session_scope() as session:
            q = session.query(Ticket)
            if scope != "all":
                # FIX C24: 'p' (49 filas) y 'P' (44) son el MISMO proyecto
                # partido en dos claves porque la comparación de SQLite es
                # sensible a mayúsculas. Un == exacto pierde la mitad del
                # corpus sin avisar. Comparamos en minúsculas.
                q = q.filter(func.lower(Ticket.stacky_project_name)
                             == (project_name or "").strip().lower())
            q = q.order_by(Ticket.id)
            total_rows = q.count()
            for t in q.limit(cap).all():
                v = classify_ticket(
                    ticket_id=t.id, ado_id=t.ado_id, external_id=t.external_id,
                    tracker_type=t.tracker_type or "", title=t.title or "",
                    description=t.description or "", ado_state=t.ado_state or "",
                    work_item_type=t.work_item_type or "")
                verdicts.append(v)
                key = v.tracker_type or "desconocido"
                by_tracker[key] = by_tracker.get(key, 0) + 1
        signal = sum(1 for v in verdicts if v.verdict == "signal")
        return {"enabled": True, "scope": scope, "total": len(verdicts),
                "signal": signal, "noise": len(verdicts) - signal,
                "by_tracker": by_tracker, "verdicts": verdicts,
                # Plan 285 F3.1 — `total_rows` se calculaba, se usaba solo para
                # el booleano de abajo y se tiraba. Sin el, el bloque no puede
                # decir CUANTOS tickets faltaron.
                "total_rows": total_rows,
                "truncated": total_rows > cap}
    except Exception as exc:
        logger.warning("doc_ticket_mining: barrido fallo para %s: %s", project_name, exc)
        return dict(empty, enabled=True)


def build_tickets_context_block(mining: dict, *, max_chars: int = 12000
                                ) -> dict | None:
    """Context block con SOLO los tickets 'signal'. None si no hay ninguno.

    Las claves del dict devuelto son las que consume prompt_builder.render_blocks
    (verificado: usa `kind`, `title`, `content`; ignora el resto).
    """
    verdicts = (mining or {}).get("verdicts") or []
    signal = [v for v in verdicts if getattr(v, "verdict", "") == "signal"]
    if not signal:
        return None
    lineas: list[str] = []
    usado = 0
    truncado = False
    for v in signal:
        motivos = ", ".join(v.reasons[:3])
        ident = v.external_id if v.external_id is not None else v.ticket_id
        linea = f"[{v.tracker_type or 'desconocido'}#{ident}] {v.title} — {motivos}"
        if usado + len(linea) + 1 > max_chars:
            truncado = True
            break
        lineas.append(linea)
        usado += len(linea) + 1
    cuerpo = "\n".join(lineas)
    if truncado:
        cuerpo += "\n[...corpus truncado]"
    total = int(mining.get("total", 0) or 0)
    ruido = int(mining.get("noise", 0) or 0)

    # ── Plan 285 F3.1 — el truncamiento deja de ser silencioso ───────────────
    # Son DOS ejes independientes, no uno:
    #   1) el cap SQL: `total` YA viene recortado a max_tickets, asi que decir
    #      "se barrieron N" con N recortado es una afirmacion falsa;
    #   2) el cap de caracteres de ESTE bloque: el cuerpo lista menos 'signal'
    #      de los que hay.
    # Declarar "COMPLETO" con cualquiera de los dos activo cambia una afirmacion
    # falsa por otra mas enfatica. Ademas `total` cuenta signal+noise mientras
    # el cuerpo lista SOLO signal: la asimetria tambien se declara.
    truncado_sql = bool(mining.get("truncated", False))
    total_rows = int(mining.get("total_rows", total) or total)
    if not truncado_sql and not truncado:
        encabezado = (
            f"Se barrieron los {total} tickets del proyecto (barrido COMPLETO). "
            f"{len(signal)} aportan historia documentable y {ruido} se "
            f"descartaron por ruido/obsolescencia. Abajo se listan los "
            f"{len(lineas)} 'signal'."
        )
    else:
        encabezado = (
            f"Se leyeron {total} tickets; {len(signal)} aportan historia "
            f"documentable y {ruido} se descartaron por ruido/obsolescencia."
        )
        if truncado_sql:
            encabezado += (
                f" ATENCION: barrido TRUNCADO — se leyeron {total} de "
                f"{total_rows} tickets, faltan {max(0, total_rows - total)}. NO "
                f"afirmes cobertura total de la historia del proyecto."
            )
        if truncado:
            encabezado += (
                f" ATENCION: la lista de abajo se corto por tamano (TRUNCADO): "
                f"se muestran {len(lineas)} de {len(signal)} tickets 'signal'."
            )
    return {
        "id": "tickets-signal",
        "kind": "tickets-signal",
        "title": "HISTORIA DEL PROYECTO SEGÚN SUS TICKETS (triage determinista)",
        "content": (
            encabezado + "\n"
            f"Usá estos tickets como CONTEXTO HISTÓRICO. No los cites como "
            f"archivo:línea: no son código, y una cita inventada te va a hacer "
            f"rechazar el archivo por el gate de citas.\n\n" + cuerpo
        ),
        "source": {"type": "tickets", "readonly": True},
    }


def build_triage_report(mining: dict, *, max_noise: int = 50) -> dict:
    """Plan 285 F3 — resumen AUDITABLE del triage, para el operador.

    Devuelve SIEMPRE las mismas keys:
      {"total", "total_rows", "truncated", "signal", "noise", "by_tracker",
       "noise_sample": [{"external_id","tracker_type","title","score","reasons"}],
       "reason_counts": {"<motivo>": int}}

    `mining["verdicts"]` son dataclasses TicketVerdict, NO dicts: se leen con
    getattr. noise_sample lleva los PEORES primero (score ascendente) hasta
    max_noise. reason_counts cuenta sobre TODO el barrido, no sobre la muestra:
    si contara sobre la muestra, el operador leeria un histograma sesgado.
    Nunca lanza: ante basura devuelve la forma vacia.
    """
    vacio = {"total": 0, "total_rows": 0, "truncated": False, "signal": 0,
             "noise": 0, "by_tracker": {}, "noise_sample": [],
             "reason_counts": {}}
    try:
        m = mining or {}
        verdicts = m.get("verdicts") or []
        total = int(m.get("total", 0) or 0)
        reason_counts: dict[str, int] = {}
        noise: list = []
        for v in verdicts:
            for r in (getattr(v, "reasons", None) or []):
                # Los motivos con dato pegado ("descripcion_extensa:900") se
                # agrupan por su prefijo: un histograma con 200 claves de una
                # sola ocurrencia no le sirve a nadie.
                clave = str(r).split(":", 1)[0]
                reason_counts[clave] = reason_counts.get(clave, 0) + 1
            if getattr(v, "verdict", "") == "noise":
                noise.append(v)
        noise.sort(key=lambda v: int(getattr(v, "score", 0) or 0))
        muestra = [{
            "external_id": getattr(v, "external_id", None),
            "ticket_id": getattr(v, "ticket_id", None),
            "tracker_type": getattr(v, "tracker_type", "") or "desconocido",
            "title": getattr(v, "title", "") or "(sin titulo)",
            "score": int(getattr(v, "score", 0) or 0),
            "reasons": list(getattr(v, "reasons", None) or []),
        } for v in noise[:max(0, int(max_noise))]]
        return {
            "total": total,
            "total_rows": int(m.get("total_rows", total) or total),
            "truncated": bool(m.get("truncated", False)),
            "signal": int(m.get("signal", 0) or 0),
            "noise": int(m.get("noise", len(noise)) or 0),
            "by_tracker": dict(m.get("by_tracker") or {}),
            "noise_sample": muestra,
            "reason_counts": reason_counts,
        }
    except Exception as exc:
        logger.warning("doc_ticket_mining: build_triage_report fallo: %s", exc)
        return vacio
