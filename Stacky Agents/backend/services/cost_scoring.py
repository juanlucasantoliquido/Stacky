"""Plan 242 F2 — Scoring de eficiencia economica. PURO, determinista, sin LLM.

Responde la pregunta que ningun total responde: "este gasto, ¿estuvo bien?".
Un run de 0,80 USD puede ser excelente (epica compleja resuelta de una) o
pesimo (typo, tercer reintento); la diferencia la da la COHORTE.

Guardarrailes:
  G3 — sin LLM, sin red, sin shell-out: solo aritmetica sobre filas ya
       persistidas.
  G4 — sin dato -> None. Un score sin componentes computables es None con
       grade "N/D", JAMAS 0 con grade E (que significaria "malisimo").
  G5 — determinismo: sin random, sin iterar sets sin ordenar, sin datetime.now.
  G7 — github_copilot es suscripcion plana: cost_kind "nominal" no se puntua
       por precio y NUNCA entra en billable.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from harness.pricing import _load_prices

# Pesos: suman EXACTAMENTE 1.00. Hay un test que lo verifica.
W_COST_POSITION = 0.35   # que tan barato fue respecto de su cohorte
W_OUTCOME       = 0.25   # sirvio o no sirvio
W_CACHE         = 0.15   # cuanto reuso de cache logro
W_UNIT_COST     = 0.15   # USD por 1k tokens de salida vs la mediana de la cohorte
W_REWORK        = 0.10   # cuantas veces hubo que repetirlo

_WEIGHTS: dict[str, float] = {
    "cost_position": W_COST_POSITION,
    "outcome": W_OUTCOME,
    "cache": W_CACHE,
    "unit_cost": W_UNIT_COST,
    "rework": W_REWORK,
}

# Cortes de nota. Inclusivos por abajo. Test explicito de los bordes.
_GRADE_CUTS: tuple[tuple[float, str], ...] = (
    (85.0, "A"), (70.0, "B"), (55.0, "C"), (40.0, "D"), (0.0, "E"),
)

_CACHE_TARGET_RATIO = 0.50    # 50% de tokens leidos de cache == componente perfecto

_BILLABLE_KINDS: frozenset[str] = frozenset({"reported", "estimated"})

# Tabla CERRADA de estados -> componente de resultado.
_OUTCOME_TABLE: dict[str, float | None] = {
    "completed": 100.0,
    "error": 0.0, "failed": 0.0,
    "cancelled": 20.0, "canceled": 20.0,
    "timeout": 10.0,
    "running": None, "pending": None, "queued": None,
}
_OUTCOME_DEFAULT = 50.0       # estado desconocido: ni premio ni castigo

# Tabla CERRADA de rework: cuantas ejecuciones ANTERIORES hubo del mismo par.
_REWORK_TABLE: dict[int, float] = {0: 100.0, 1: 60.0, 2: 30.0}
_REWORK_FLOOR = 0.0           # 3 o mas

# Motivos de "componente no evaluado": vocabulario CERRADO (test lo verifica).
_MOTIVOS: dict[str, str] = {
    "sin_costo": "sin costo registrado",
    "cohorte_chica": "cohorte con menos de 3 runs",
    "sin_cache": "sin tokens de entrada o de cache",
    "sin_salida": "sin tokens de salida",
    "sin_ticket": "ejecución sin ticket asociado",
    "en_curso": "ejecución aún en curso",
}

_MIN_COHORT_FOR_POSITION = 3


@dataclass
class CohortStats:
    """Referencia contra la que se puntua UNA ejecucion. La arma build_cohorts()."""
    key: str                        # "<agent_type>|<model_family>"
    n: int
    costs_sorted: list[float]       # costos facturables de la cohorte, ORDENADOS asc
    median_unit_cost: float | None  # mediana de usd_per_ktok_out de la cohorte
    median_cost_usd: float | None = None


@dataclass
class ExecutionScore:
    execution_id: int
    ticket_id: int | None
    agent_type: str | None
    runtime: str | None
    model: str | None
    cost_usd: float | None
    cost_kind: str
    score: float | None             # 0..100 redondeado a 2 decimales; None si nada computable
    grade: str                      # "A".."E" o "N/D"
    components: dict[str, float]    # solo los componentes COMPUTADOS, 0..100 c/u
    weights_used: dict[str, float]  # pesos RENORMALIZADOS efectivamente aplicados
    reasons: list[str]              # espanol, cada una con su numero
    cohort_key: str
    cohort_n: int
    confidence: str                 # "alta" | "media" | "baja"


@dataclass
class TicketScore:
    ticket_id: int
    ado_id: int | None
    runs: int
    billable_usd: float
    score: float | None
    grade: str
    rework_penalty: float
    reasons: list[str]
    worst_execution_id: int | None


# ── helpers ─────────────────────────────────────────────────────────────────

def _median(values: list[float]) -> float | None:
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    mid = n // 2
    return v[mid] if n % 2 else (v[mid - 1] + v[mid]) / 2.0


def model_family(model: str | None) -> str:
    """Prefijo mas largo del catalogo de precios que matchea el modelo.

    Reusa la MISMA regla que `cost_analytics.input_price_per_mtok` para que
    haya una sola definicion de "familia de modelo" en todo el plan.
    """
    if not model:
        return "(sin modelo)"
    best, best_len = None, -1
    for prefix in _load_prices():
        if model.startswith(prefix) and len(prefix) > best_len:
            best, best_len = prefix, len(prefix)
    return best if best is not None else "(otro)"


def cohort_key_for(rec) -> str:
    agent = getattr(rec, "agent_type", None) or "(sin agente)"
    return f"{agent}|{model_family(getattr(getattr(rec, 'row', None), 'model', None))}"


def grade_for(score: float | None) -> str:
    if score is None:
        return "N/D"
    for umbral, letra in _GRADE_CUTS:
        if score >= umbral:
            return letra
    return "E"


def percent_rank(sorted_values: list[float], x: float) -> float | None:
    """Midrank: (menores + 0.5*iguales) / n.

    Se usa midrank y no `menores/n` para que, si TODOS los valores son iguales,
    pr = 0.5 y el componente de 50 (neutro) en vez de 100 (falso merito).
    """
    n = len(sorted_values)
    if n == 0:
        return None
    menores = sum(1 for v in sorted_values if v < x)
    iguales = sum(1 for v in sorted_values if v == x)
    return (menores + 0.5 * iguales) / n


def _unit_cost(row) -> float | None:
    cost = getattr(row, "cost_usd", None)
    to = getattr(row, "tokens_out", None)
    if cost is None or to is None or to <= 0:
        return None
    return cost / (to / 1000.0)


def build_cohorts(records) -> dict[str, CohortStats]:
    """Agrupa por "<agent_type>|<familia de modelo>". Solo entran costos
    FACTURABLES: un costo que nadie paga no puede ser la referencia de 'caro'."""
    acc: dict[str, dict] = {}
    for r in records:
        key = cohort_key_for(r)
        d = acc.setdefault(key, {"costs": [], "units": [], "n": 0})
        d["n"] += 1
        row = getattr(r, "row", None)
        kind = getattr(row, "cost_kind", "") or ""
        cost = getattr(row, "cost_usd", None)
        if kind in _BILLABLE_KINDS and cost is not None:
            d["costs"].append(float(cost))
            u = _unit_cost(row)
            if u is not None:
                d["units"].append(u)
    return {
        k: CohortStats(key=k, n=acc[k]["n"], costs_sorted=sorted(acc[k]["costs"]),
                       median_unit_cost=_median(acc[k]["units"]),
                       median_cost_usd=_median(acc[k]["costs"]))
        for k in sorted(acc)
    }


# ── scoring de una ejecucion ────────────────────────────────────────────────

def score_execution(record, cohorts: dict[str, CohortStats],
                    prev_runs: int = 0) -> ExecutionScore:
    row = getattr(record, "row", None)
    cost_usd = getattr(row, "cost_usd", None)
    cost_kind = getattr(row, "cost_kind", "") or "unknown"
    status = (getattr(record, "status", None) or "").lower()
    verdict = (getattr(record, "verdict", None) or "").lower() or None
    ticket_id = getattr(record, "ticket_id", None)

    key = cohort_key_for(record)
    cohorte = cohorts.get(key)
    cohort_n = cohorte.n if cohorte else 0

    comps: dict[str, float] = {}
    reasons: list[str] = []
    faltantes: list[tuple[str, str]] = []

    # (1) cost_position — ¿fue barato para lo que es?
    if cost_usd is None:
        faltantes.append(("cost_position", _MOTIVOS["sin_costo"]))
    elif cost_kind == "nominal":
        faltantes.append(("cost_position", _MOTIVOS["sin_costo"]))
    elif cohorte is None or cohorte.n < _MIN_COHORT_FOR_POSITION:
        faltantes.append(("cost_position", _MOTIVOS["cohorte_chica"]))
    else:
        pr = percent_rank(cohorte.costs_sorted, float(cost_usd))
        if pr is None:
            faltantes.append(("cost_position", _MOTIVOS["cohorte_chica"]))
        else:
            comps["cost_position"] = round(100.0 * (1.0 - pr), 2)
            reasons.append(
                f"Costó {cost_usd:.4f} USD: percentil {pr * 100:.0f} de su cohorte "
                f"'{key}' ({cohorte.n} runs) — "
                f"{'más barato' if pr < 0.5 else 'más caro'} que la mediana."
            )

    # (2) outcome — ¿sirvió?
    if status in _OUTCOME_TABLE:
        base = _OUTCOME_TABLE[status]
    else:
        base = _OUTCOME_DEFAULT
    if base is None:
        faltantes.append(("outcome", _MOTIVOS["en_curso"]))
    else:
        # Un run que "completó" pero cuyo contrato dio fail NO es un exito economico.
        if verdict == "fail":
            base = min(base, 30.0)
        base = max(0.0, min(100.0, base))
        comps["outcome"] = round(base, 2)
        verdicto_txt = f" con veredicto '{verdict}'" if verdict else ""
        reasons.append(f"Estado final '{status or 'desconocido'}'{verdicto_txt} → "
                       f"{base:.0f}/100 en resultado.")

    # (3) cache — ¿reusó contexto?
    cr = getattr(row, "cache_read_tokens", None)
    ti = getattr(row, "tokens_in", None)
    if cr is None or ti is None or (cr + ti) == 0:
        faltantes.append(("cache", _MOTIVOS["sin_cache"]))
    else:
        ratio = cr / (cr + ti)
        valor = round(100.0 * min(1.0, ratio / _CACHE_TARGET_RATIO), 2)
        comps["cache"] = valor
        reasons.append(f"Leyó {cr} tokens de cache sobre {cr + ti} de entrada "
                       f"({ratio * 100:.1f}%) → {valor:.0f}/100 en reuso.")

    # (4) unit_cost — ¿cuánto costó cada unidad de salida?
    if cost_usd is None or cost_kind == "nominal":
        faltantes.append(("unit_cost", _MOTIVOS["sin_costo"]))
    else:
        unit = _unit_cost(row)
        if unit is None:
            faltantes.append(("unit_cost", _MOTIVOS["sin_salida"]))
        elif cohorte is None or cohorte.median_unit_cost is None or cohorte.median_unit_cost <= 0:
            faltantes.append(("unit_cost", _MOTIVOS["cohorte_chica"]))
        elif unit <= 0:
            comps["unit_cost"] = 100.0
            reasons.append(f"0.0000 USD por 1k tokens de salida vs "
                           f"{cohorte.median_unit_cost:.4f} de su cohorte (0.0×).")
        else:
            valor = round(100.0 * min(1.0, cohorte.median_unit_cost / unit), 2)
            comps["unit_cost"] = valor
            razon_x = unit / cohorte.median_unit_cost
            reasons.append(f"{unit:.4f} USD por 1k tokens de salida vs "
                           f"{cohorte.median_unit_cost:.4f} de su cohorte ({razon_x:.1f}×).")

    # (5) rework — ¿fue el primer intento?
    if ticket_id is None:
        faltantes.append(("rework", _MOTIVOS["sin_ticket"]))
    else:
        valor = _REWORK_TABLE.get(int(prev_runs), _REWORK_FLOOR)
        comps["rework"] = valor
        reasons.append(f"Es el intento #{int(prev_runs) + 1} de este ticket con el "
                       f"agente '{getattr(record, 'agent_type', None) or '(sin dato)'}' → "
                       f"{valor:.0f}/100 en rework.")

    # Razon especial de suscripcion plana (G7).
    if cost_kind == "nominal":
        reasons.append("Runtime de suscripción plana (github_copilot): el costo es "
                       "nominal, no facturable — no se puntúa el precio.")

    for nombre, motivo in faltantes:
        reasons.append(f"Componente '{nombre}' no evaluado: {motivo}.")

    # Renormalizacion (regla unica, sin excepciones).
    if not comps:
        return ExecutionScore(
            execution_id=getattr(record, "execution_id", 0), ticket_id=ticket_id,
            agent_type=getattr(record, "agent_type", None),
            runtime=getattr(row, "runtime", None), model=getattr(row, "model", None),
            cost_usd=cost_usd, cost_kind=cost_kind, score=None, grade="N/D",
            components={}, weights_used={},
            reasons=["Sin datos suficientes para puntuar: no hay costo, ni estado "
                     "terminal, ni tokens."] + reasons,
            cohort_key=key, cohort_n=cohort_n, confidence="baja")

    peso_total = sum(_WEIGHTS[n] for n in comps)
    weights_used = {n: _WEIGHTS[n] / peso_total for n in comps}
    score = round(sum(weights_used[n] * comps[n] for n in comps), 2)
    score = min(100.0, max(0.0, score))

    n_comp = len(comps)
    if n_comp >= 4 and cohort_n >= 20:
        confidence = "alta"
    elif n_comp >= 3 and cohort_n >= 5:
        confidence = "media"
    else:
        confidence = "baja"
    if confidence == "baja":
        reasons.append(f"Confianza baja: {n_comp} componentes evaluados sobre una "
                       f"cohorte de {cohort_n} runs.")

    return ExecutionScore(
        execution_id=getattr(record, "execution_id", 0), ticket_id=ticket_id,
        agent_type=getattr(record, "agent_type", None),
        runtime=getattr(row, "runtime", None), model=getattr(row, "model", None),
        cost_usd=cost_usd, cost_kind=cost_kind, score=score, grade=grade_for(score),
        components=comps, weights_used=weights_used, reasons=reasons,
        cohort_key=key, cohort_n=cohort_n, confidence=confidence)


# ── scoring de un ticket ────────────────────────────────────────────────────

def _ordenar_runs(records) -> list:
    """Determinismo: por started_at y, ante empate, por execution_id asc."""
    return sorted(records, key=lambda r: (getattr(r, "started_at", None) or 0,
                                          getattr(r, "execution_id", 0)))


def score_ticket(records, cohorts: dict[str, CohortStats]) -> TicketScore:
    """C8 — la cohorte entra POR PARAMETRO, nunca se construye local.

    v1 hacia `build_cohorts(records_del_ticket)`: una cohorte armada con las
    ejecuciones de UN SOLO ticket casi siempre tiene n < 3, y `cost_position`
    devuelve None por debajo de 3. Resultado: el componente de MAYOR PESO
    (0,35) quedaba en None para practicamente todos los tickets. El caller le
    pasa la cohorte GLOBAL, que es la unica referencia con sentido.
    """
    records = list(records)
    if not records:
        raise ValueError("score_ticket requiere al menos una ejecucion")

    ordenados = _ordenar_runs(records)
    vistos: dict[str, int] = {}
    scores: list[tuple[int, float | None]] = []
    for r in ordenados:
        agent = getattr(r, "agent_type", None) or "(sin dato)"
        prev = vistos.get(agent, 0)
        vistos[agent] = prev + 1
        s = score_execution(r, cohorts, prev_runs=prev)
        scores.append((getattr(r, "execution_id", 0), s.score))

    validos = [(eid, s) for eid, s in scores if s is not None]
    ticket_id = getattr(ordenados[0], "ticket_id", None)
    ado_id = getattr(ordenados[0], "ado_id", None)

    billable = 0.0
    for r in ordenados:
        row = getattr(r, "row", None)
        kind = getattr(row, "cost_kind", "") or ""
        cost = getattr(row, "cost_usd", None)
        if kind in _BILLABLE_KINDS and cost is not None:
            billable += float(cost)

    runs_extra = sum(max(0, c - 1) for c in vistos.values())
    rework_penalty = min(20.0, 4.0 * runs_extra)

    reasons: list[str] = []
    if rework_penalty > 0:
        reasons.append(f"Penalidad de rework: -{rework_penalty:.0f} puntos por "
                       f"{runs_extra} ejecución(es) repetida(s) del mismo agente.")

    if not validos:
        reasons.append("Ninguna de las ejecuciones de este ticket tuvo datos "
                       "suficientes para puntuar.")
        return TicketScore(ticket_id=ticket_id, ado_id=ado_id, runs=len(ordenados),
                           billable_usd=round(billable, 6), score=None, grade="N/D",
                           rework_penalty=rework_penalty, reasons=reasons,
                           worst_execution_id=None)

    base = sum(s for _, s in validos) / len(validos)
    score = round(min(100.0, max(0.0, base - rework_penalty)), 2)
    # Empate de score -> el execution_id mas chico (DETERMINISMO).
    worst = min(validos, key=lambda t: (t[1], t[0]))[0]
    reasons.append(f"Promedio de {len(validos)} ejecución(es) puntuada(s): "
                   f"{base:.2f}/100.")

    return TicketScore(ticket_id=ticket_id, ado_id=ado_id, runs=len(ordenados),
                       billable_usd=round(billable, 6), score=score,
                       grade=grade_for(score), rework_penalty=rework_penalty,
                       reasons=reasons, worst_execution_id=worst)


# ── payload del endpoint ────────────────────────────────────────────────────

def _orden_peores_primero(items: list[dict]) -> list[dict]:
    """score asc (peores primero); los score=None van al FINAL por id asc."""
    con = [x for x in items if x.get("score") is not None]
    sin = [x for x in items if x.get("score") is None]
    con.sort(key=lambda d: (d["score"], d.get("execution_id") or d.get("ticket_id") or 0))
    sin.sort(key=lambda d: (d.get("execution_id") or d.get("ticket_id") or 0))
    return con + sin


def score_payload(records, top_n: int = 50) -> dict:
    records = list(records)
    cohorts = build_cohorts(records)

    # prev_runs por (ticket_id, agent_type), en orden determinista.
    vistos: dict[tuple, int] = {}
    execs: list[dict] = []
    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "N/D": 0}
    runs_scored = 0
    for r in _ordenar_runs(records):
        clave = (getattr(r, "ticket_id", None), getattr(r, "agent_type", None))
        prev = vistos.get(clave, 0)
        vistos[clave] = prev + 1
        s = score_execution(r, cohorts, prev_runs=prev)
        grade_distribution[s.grade] = grade_distribution.get(s.grade, 0) + 1
        if s.score is not None:
            runs_scored += 1
        execs.append(asdict(s))

    por_ticket: dict[int, list] = {}
    for r in records:
        tid = getattr(r, "ticket_id", None)
        if tid is not None:
            por_ticket.setdefault(tid, []).append(r)
    tickets = [asdict(score_ticket(por_ticket[t], cohorts)) for t in sorted(por_ticket)]

    return {
        "cohorts": {k: {"n": c.n, "median_cost_usd": c.median_cost_usd,
                        "median_unit_cost": (round(c.median_unit_cost, 6)
                                             if c.median_unit_cost is not None else None)}
                    for k, c in cohorts.items()},
        "executions": _orden_peores_primero(execs)[:top_n],
        "tickets": _orden_peores_primero(tickets)[:top_n],
        "grade_distribution": grade_distribution,
        "runs_total": len(records),
        "runs_scored": runs_scored,
    }
