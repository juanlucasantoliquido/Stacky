"""Plan 242 F1 — Motor estadistico PURO. stdlib only (math, statistics).

Convierte una lista de `ExecRecord` (Plan 142 + senales del 242 F0) en
distribuciones, histogramas y outliers, por metrica y por dimension.

Guardarrailes que aplican aca:
  G1 — cero dependencias nuevas: solo `math`, `statistics`, `dataclasses`.
  G4 — sin dato -> None, JAMAS 0.0 inventado. Un percentil sobre lista vacia
       es None, no 0. Nunca se divide sin verificar el denominador.
  G5 — determinismo: las claves de `by_dimension` salen ordenadas, y los
       desempates de `rework_index` son explicitos.

Convivencia con el Plan 171 (C3): `run_signals.percentile_nearest_rank` es
*nearest-rank* (devuelve un valor observado real, que es lo que corresponde
para comparar contra un umbral de alerta); `cost_stats.percentile` es
*interpolacion lineal* (las distribuciones de costo son continuas y de cola
larga, y el nearest-rank sobre muestras chicas salta de escalon). Dan numeros
distintos para el mismo dataset y eso es CORRECTO. Prohibido que una llame a
la otra o "unificarlas" desde este plan.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass

_METRICS: tuple[str, ...] = (
    "cost_usd", "tokens_in", "tokens_out", "cache_read_tokens",
    "cache_creation_tokens", "duration_s", "tokens_total", "usd_per_ktok_out",
)
_DIMENSIONS: tuple[str, ...] = (
    "runtime", "model", "agent_type", "project", "work_item_type", "priority",
)
_PERCENTILES: tuple[int, ...] = (50, 75, 90, 95, 99)

# Solo reported+estimated son facturables (espejo de cost_analytics._billable,
# duplicado a proposito para no importar cost_analytics desde un modulo puro).
_BILLABLE_KINDS: frozenset[str] = frozenset({"reported", "estimated"})

_ROUND = 6


@dataclass
class Distribution:
    n: int                      # cantidad de valores NO nulos
    n_missing: int              # cantidad de None descartados
    total: float | None         # suma; None si n == 0
    minimum: float | None
    maximum: float | None
    mean: float | None
    median: float | None
    stdev: float | None         # MUESTRAL (n-1); None si n < 2
    q1: float | None
    q3: float | None
    iqr: float | None           # q3 - q1; None si n < 2
    cv: float | None            # stdev / mean; None si n<2 o mean == 0
    mad: float | None           # mediana(|x - mediana|); None si n == 0
    p50: float | None
    p75: float | None
    p90: float | None
    p95: float | None
    p99: float | None


@dataclass
class HistBin:
    lo: float
    hi: float
    count: int


@dataclass
class OutlierReport:
    method: str                 # "tukey" | "mad"
    fence_low: float | None
    fence_high: float | None
    indices: list[int]          # posiciones (en la lista ORIGINAL, incluyendo None)
    n_outliers: int
    applicable: bool            # False si IQR==0 / MAD==0 -> no se declara ningun outlier
    reason: str                 # explicacion en espanol cuando applicable is False


# ── helpers internos ────────────────────────────────────────────────────────

def _r(x: float | None) -> float | None:
    return None if x is None else round(float(x), _ROUND)


def _clean(values) -> list[float]:
    return [float(x) for x in values if x is not None]


# ── percentil e indicadores ─────────────────────────────────────────────────

def percentile(sorted_values: list[float], q: float) -> float | None:
    """Interpolacion lineal, metodo "inclusivo" (equivalente a numpy.percentile
    con interpolation="linear"), definido a mano porque numpy NO es dependencia.

    `sorted_values` DEBE venir ordenado ascendentemente.
    """
    if not sorted_values:
        return None
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    idx = (q / 100.0) * (n - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return float(sorted_values[int(idx)])
    frac = idx - lo
    return float(sorted_values[lo]) + (float(sorted_values[hi]) - float(sorted_values[lo])) * frac


def describe(values) -> Distribution:
    """Estadistica descriptiva completa. Los None NO participan de ningun
    calculo y se cuentan en `n_missing`."""
    values = list(values)
    limpios = _clean(values)
    n = len(limpios)
    n_missing = len(values) - n

    if n == 0:
        return Distribution(n=0, n_missing=n_missing, total=None, minimum=None,
                            maximum=None, mean=None, median=None, stdev=None,
                            q1=None, q3=None, iqr=None, cv=None, mad=None,
                            p50=None, p75=None, p90=None, p95=None, p99=None)

    ordenados = sorted(limpios)
    mean = statistics.fmean(limpios)
    median = statistics.median(limpios)
    stdev = statistics.stdev(limpios) if n >= 2 else None
    q1 = percentile(ordenados, 25)
    q3 = percentile(ordenados, 75)
    iqr = (q3 - q1) if n >= 2 else None
    # OJO: mean puede ser 0.0 legitimamente (todos los costos reportados en 0).
    cv = (stdev / mean) if (n >= 2 and stdev is not None and mean != 0) else None
    mad = statistics.median([abs(x - median) for x in limpios])
    pct = {p: percentile(ordenados, p) for p in _PERCENTILES}

    return Distribution(
        n=n, n_missing=n_missing, total=_r(sum(limpios)),
        minimum=_r(ordenados[0]), maximum=_r(ordenados[-1]),
        mean=_r(mean), median=_r(median), stdev=_r(stdev),
        q1=_r(q1), q3=_r(q3), iqr=_r(iqr), cv=_r(cv), mad=_r(mad),
        p50=_r(pct[50]), p75=_r(pct[75]), p90=_r(pct[90]),
        p95=_r(pct[95]), p99=_r(pct[99]),
    )


def histogram(values, bins: int = 10) -> list[HistBin]:
    """Histograma canonico del plan. Misma semantica que
    `cost_analytics.distribution` (Plan 199) pero sobre CUALQUIER metrica, no
    solo cost_usd; un test fija que ambos coinciden."""
    limpios = _clean(values)
    if not limpios:
        return []
    lo, hi = min(limpios), max(limpios)
    if lo == hi:
        # Todo el mismo valor: UN solo bin de ancho 0 (si no, dividiriamos por 0).
        return [HistBin(lo=_r(lo), hi=_r(hi), count=len(limpios))]

    try:
        bins = int(bins or 1)
    except (TypeError, ValueError):
        bins = 10
    bins = max(1, min(bins, 100))          # clamp duro
    ancho = (hi - lo) / bins
    conteos = [0] * bins
    for x in limpios:
        i = int(math.floor((x - lo) / ancho))
        if i >= bins:                      # el maximo exacto cae en el ultimo bin
            i = bins - 1
        conteos[i] += 1
    return [HistBin(lo=_r(lo + i * ancho), hi=_r(lo + (i + 1) * ancho), count=conteos[i])
            for i in range(bins)]


def _indices_fuera(values, bajo: float, alto: float) -> list[int]:
    """Posiciones de la lista ORIGINAL (con sus None) fuera de las vallas."""
    return [i for i, v in enumerate(values)
            if v is not None and (float(v) < bajo or float(v) > alto)]


def tukey_outliers(values) -> OutlierReport:
    values = list(values)
    limpios = _clean(values)
    if len(limpios) < 4:
        return OutlierReport("tukey", None, None, [], 0, False,
                             "menos de 4 muestras")
    ordenados = sorted(limpios)
    q1 = percentile(ordenados, 25)
    q3 = percentile(ordenados, 75)
    iqr = q3 - q1
    if iqr == 0:
        return OutlierReport("tukey", None, None, [], 0, False,
                             "IQR = 0 (distribucion degenerada)")
    fence_low = q1 - 1.5 * iqr
    fence_high = q3 + 1.5 * iqr
    idx = _indices_fuera(values, fence_low, fence_high)
    return OutlierReport("tukey", _r(fence_low), _r(fence_high), idx, len(idx), True, "")


def mad_outliers(values, threshold: float = 3.5) -> OutlierReport:
    values = list(values)
    limpios = _clean(values)
    if len(limpios) < 4:
        return OutlierReport("mad", None, None, [], 0, False, "menos de 4 muestras")
    median = statistics.median(limpios)
    mad = statistics.median([abs(x - median) for x in limpios])
    if mad == 0:
        # NUNCA se divide por MAD sin verificar que no sea 0.
        return OutlierReport("mad", None, None, [], 0, False,
                             "MAD = 0 (mas de la mitad de los valores son identicos)")
    ancho = threshold * mad / 0.6745       # 0.6745 = constante de consistencia normal
    fence_low = median - ancho
    fence_high = median + ancho
    idx = _indices_fuera(values, fence_low, fence_high)
    return OutlierReport("mad", _r(fence_low), _r(fence_high), idx, len(idx), True, "")


# ── proyeccion de ExecRecord ────────────────────────────────────────────────

def metric_value(rec, metric: str) -> float | None:
    """Valor de una metrica para un ExecRecord. None si falta CUALQUIER insumo:
    jamas se suma ni se divide contra un 0 inventado."""
    row = getattr(rec, "row", None)
    if metric == "cost_usd":
        return getattr(row, "cost_usd", None)
    if metric == "tokens_in":
        return getattr(row, "tokens_in", None)
    if metric == "tokens_out":
        return getattr(row, "tokens_out", None)
    if metric == "cache_read_tokens":
        return getattr(row, "cache_read_tokens", None)
    if metric == "cache_creation_tokens":
        sig = getattr(rec, "signals", None)
        return getattr(sig, "cache_creation_tokens", None) if sig is not None else None
    if metric == "duration_s":
        return getattr(rec, "duration_s", None)
    if metric == "tokens_total":
        ti = getattr(row, "tokens_in", None)
        to = getattr(row, "tokens_out", None)
        return None if (ti is None or to is None) else ti + to
    if metric == "usd_per_ktok_out":
        cost = getattr(row, "cost_usd", None)
        to = getattr(row, "tokens_out", None)
        if cost is None or to is None or to <= 0:
            return None
        return _r(cost / (to / 1000.0))
    raise ValueError(f"metrica desconocida: {metric}")


def dimension_key(rec, dimension: str) -> str:
    """String, NUNCA None: el ausente se mapea a una etiqueta explicita.

    No se reusa `cost_analytics._dim_key` porque aquella soporta ticket/day y
    no soporta work_item_type/priority; duplicar la tabla aca es mas barato y
    mas seguro que cambiar la del 142.
    """
    row = getattr(rec, "row", None)
    if dimension == "runtime":
        return getattr(row, "runtime", None) or "(sin dato)"
    if dimension == "model":
        return getattr(row, "model", None) or "(sin dato)"
    if dimension == "agent_type":
        return getattr(rec, "agent_type", None) or "(sin dato)"
    if dimension == "project":
        return getattr(rec, "project", None) or "(sin proyecto)"
    if dimension == "work_item_type":
        return getattr(rec, "work_item_type", None) or "(sin tipo)"
    if dimension == "priority":
        p = getattr(rec, "priority", None)
        return "(sin prioridad)" if p is None else str(p)
    raise ValueError(f"dimension desconocida: {dimension}")


def by_dimension(records, dimension: str, metric: str) -> dict[str, Distribution]:
    """Distribucion de `metric` agrupada por `dimension`. Claves ORDENADAS."""
    grupos: dict[str, list] = {}
    for r in records:
        grupos.setdefault(dimension_key(r, dimension), []).append(metric_value(r, metric))
    return {k: describe(grupos[k]) for k in sorted(grupos)}


# ── indicadores compuestos ──────────────────────────────────────────────────

def cache_efficiency(records) -> dict:
    """Cuanto contexto se reuso y cuanto costo escribirlo."""
    cache_read_total = 0
    cache_creation_total = 0
    tokens_in_total = 0
    runs_with_cache_data = 0
    savings = 0.0
    for r in records:
        row = getattr(r, "row", None)
        cr = getattr(row, "cache_read_tokens", None)
        if cr is not None:
            cache_read_total += int(cr)
            runs_with_cache_data += 1
        ti = getattr(row, "tokens_in", None)
        if ti is not None:
            tokens_in_total += int(ti)
        sig = getattr(r, "signals", None)
        cc = getattr(sig, "cache_creation_tokens", None) if sig is not None else None
        if cc is not None:
            cache_creation_total += int(cc)
        cs = getattr(row, "cache_savings_usd", None)
        if cs is not None:
            savings += float(cs)

    denom = cache_read_total + tokens_in_total
    return {
        "cache_read_total": cache_read_total,
        "cache_creation_total": cache_creation_total,
        "tokens_in_total": tokens_in_total,
        "runs_with_cache_data": runs_with_cache_data,
        "cache_read_ratio": _r(cache_read_total / denom) if denom else None,
        "cache_savings_usd_total": _r(savings) or 0.0,
        "cache_write_overhead_ratio": (_r(cache_creation_total / cache_read_total)
                                       if cache_read_total else None),
    }


def rework_index(records) -> dict:
    """El rework es un costo real y hay que nombrarlo.

    "El primero del par" = el de `started_at` mas antiguo; empate de
    `started_at` se rompe por `execution_id` ascendente (determinismo).
    """
    pares: dict[tuple, list] = {}
    orphan_runs = 0
    total_runs_con_ticket = 0
    for r in records:
        tid = getattr(r, "ticket_id", None)
        if tid is None:
            orphan_runs += 1
            continue
        total_runs_con_ticket += 1
        pares.setdefault((tid, getattr(r, "agent_type", None)), []).append(r)

    rework_runs = 0
    rework_cost = 0.0
    filas = []
    for (tid, agent), runs in pares.items():
        # Orden determinista: por fecha y, ante empate, por id ascendente.
        runs_ord = sorted(runs, key=lambda x: (getattr(x, "started_at", None) or 0,
                                               getattr(x, "execution_id", 0)))
        extra = runs_ord[1:]
        rework_runs += len(extra)
        costo_par = 0.0
        for r in extra:
            row = getattr(r, "row", None)
            kind = getattr(row, "cost_kind", "") or ""
            cost = getattr(row, "cost_usd", None)
            if kind in _BILLABLE_KINDS and cost is not None:
                costo_par += float(cost)
        rework_cost += costo_par
        if len(runs_ord) > 1:
            filas.append({"ticket_id": tid, "agent_type": agent or "(sin dato)",
                          "runs": len(runs_ord), "cost_usd": _r(costo_par)})

    filas.sort(key=lambda d: (-d["runs"], d["ticket_id"]))
    return {
        "pairs_total": len(pares),
        "pairs_with_rework": len(filas),
        "rework_runs": rework_runs,
        "rework_ratio": (_r(rework_runs / total_runs_con_ticket)
                         if total_runs_con_ticket else None),
        "rework_cost_usd": _r(rework_cost) or 0.0,
        "top_rework": filas[:10],
        "orphan_runs": orphan_runs,
    }


def stats_payload(records, metrics=_METRICS, dimensions=_DIMENSIONS,
                  bins: int = 10, dimension_metric: str = "cost_usd") -> dict:
    """Arma el dict que consume el endpoint. 100% JSON-serializable."""
    records = list(records)
    out_metrics = {}
    for m in metrics:
        valores = [metric_value(r, m) for r in records]
        out_metrics[m] = {
            "overall": asdict(describe(valores)),
            "histogram": [asdict(b) for b in histogram(valores, bins=bins)],
            "outliers_tukey": asdict(tukey_outliers(valores)),
            "outliers_mad": asdict(mad_outliers(valores)),
        }
    return {
        "metrics": out_metrics,
        "by_dimension": {d: {k: asdict(v)
                             for k, v in by_dimension(records, d, dimension_metric).items()}
                         for d in dimensions},
        "cache_efficiency": cache_efficiency(records),
        "rework": rework_index(records),
        "runs_total": len(records),
    }
