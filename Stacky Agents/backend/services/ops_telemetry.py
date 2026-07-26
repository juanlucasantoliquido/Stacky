"""Plan 171 F2 — Orquestación fina de la telemetría operativa.

Capa delgada que carga registros vía `cost_analytics`, persiste/lee los umbrales en
`data_dir()/telemetry/` y compone los payloads de la API. Separa I/O de lógica: el
cálculo vive entero en `run_signals` (puro), y los endpoints quedan de 10 líneas.

Read-only sobre la DB: la única escritura es el JSON de umbrales que edita el operador.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
from pathlib import Path

import runtime_paths  # data_dir() se llama EN CADA operación (testabilidad)
from services import cost_analytics as ca
from services import run_signals as rs

logger = logging.getLogger("stacky_agents.ops_telemetry")

_THRESHOLDS_LOCK = threading.Lock()
_THRESHOLDS_FILENAME = "ops_thresholds.json"


def telemetry_root() -> Path:
    return runtime_paths.data_dir() / "telemetry"


def _thresholds_path() -> Path:
    return telemetry_root() / _THRESHOLDS_FILENAME


def _read_overrides() -> dict:
    """Lectura tolerante: ausente/corrupto/no-dict → {} (nunca rompe la página)."""
    try:
        path = _thresholds_path()
        if not path.is_file():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        logger.debug("umbrales ilegibles, se usan los defaults", exc_info=True)
        return {}


def _resolve_stall_minutes(effective: dict) -> dict:
    """`stall_minutes=None` significa "usar el timeout del sistema".

    El import es LOCAL a propósito: `run_signals` sigue puro y esta capa de I/O es
    la única que conoce la fuente única del timeout.
    """
    if effective.get("stall_minutes") is None:
        try:
            from services.ticket_status import EXECUTION_TIMEOUT_MINUTES

            effective["stall_minutes"] = int(EXECUTION_TIMEOUT_MINUTES)
        except Exception:  # noqa: BLE001
            logger.debug("no se pudo leer EXECUTION_TIMEOUT_MINUTES", exc_info=True)
            effective["stall_minutes"] = 120
    return effective


def load_thresholds() -> dict:
    """Efectivo = defaults + overrides conocidos, con `stall_minutes` SIEMPRE int."""
    return _resolve_stall_minutes(rs.merge_thresholds(_read_overrides()))


# ── Validación del POST (§4.8) ───────────────────────────────────────────────

def _as_float_in(value, low: float, high: float):
    number = float(value)
    if number < low or number > high:
        raise ValueError
    return number


def _validate(key: str, value):
    """Devuelve el valor normalizado o lanza ValueError (el caller arma el mensaje)."""
    if key in ("error_rate_warn", "error_rate_delta"):
        if isinstance(value, bool):
            raise ValueError
        return _as_float_in(value, 0.0, 1.0)
    if key in ("min_runs", "baseline_min_runs"):
        if isinstance(value, bool) or int(value) != float(value) or int(value) < 1:
            raise ValueError
        return int(value)
    if key == "stall_minutes":
        if value is None:
            return None
        if isinstance(value, bool) or int(value) != float(value) or int(value) < 1:
            raise ValueError
        return int(value)
    if key == "p90_regression_factor":
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
        if number < 1.0:
            raise ValueError
        return number
    if key == "p90_min_seconds":
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
        if number < 0:
            raise ValueError
        return number
    if key == "daily_budget_usd":
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError
        number = float(value)
        if number <= 0:
            raise ValueError
        return number
    raise ValueError


def save_thresholds(patch: dict) -> dict:
    """Valida y persiste SOLO claves conocidas. Devuelve el efectivo nuevo.

    Lanza `ValueError("invalid_thresholds:<clave>")` en el PRIMER fallo (clave
    desconocida incluida). `schema_version` NO es editable: se ignora si viene.
    """
    patch = patch if isinstance(patch, dict) else {}
    clean: dict = {}
    for key, value in patch.items():
        if key == "schema_version":
            continue  # no editable
        try:
            clean[key] = _validate(key, value)
        except (ValueError, TypeError):
            raise ValueError(f"invalid_thresholds:{key}") from None

    with _THRESHOLDS_LOCK:
        stored = _read_overrides()
        stored.update(clean)
        # Se persisten solo claves conocidas (una clave rara del disco no sobrevive).
        stored = {k: v for k, v in stored.items()
                  if k in rs.DEFAULT_THRESHOLDS and k != "schema_version"}
        root = telemetry_root()
        root.mkdir(parents=True, exist_ok=True)
        _thresholds_path().write_text(
            json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return load_thresholds()


# ── Payloads ─────────────────────────────────────────────────────────────────

def _points(filters: "ca.CostFilters") -> list:
    return [rs.from_exec_record(r) for r in ca.load_records(filters)]


def ops_summary(filters: "ca.CostFilters", *, baseline_enabled: bool) -> dict:
    points = _points(filters)
    body = rs.summarize_groups(points)
    thresholds = load_thresholds()
    now = rs._utcnow()

    breaches, stalls = rs.evaluate_thresholds(points, thresholds, now)

    regressions: list = []
    if baseline_enabled:
        base_filters = dataclasses.replace(
            filters,
            days=rs.CURRENT_WINDOW_DAYS + rs.BASELINE_WINDOW_DAYS,
            date_from=None,
            date_to=None,
        )
        current, baseline = rs.split_windows(_points(base_filters), now)
        regressions = rs.detect_regressions(current, baseline, thresholds)
        breaches = breaches + regressions

    return {
        "enabled": True,
        "generated_at": now.isoformat() + "Z",
        "window_days": getattr(filters, "days", 30),
        "totals": body["totals"],
        "groups": body["groups"],
        "baseline": {
            "enabled": bool(baseline_enabled),
            "current_days": rs.CURRENT_WINDOW_DAYS,
            "baseline_days": rs.BASELINE_WINDOW_DAYS,
            "regressions": regressions,
        },
        "breaches": rs.sort_breaches(breaches),
        "stalls": stalls,
        "thresholds": thresholds,
    }


def ops_trends(filters: "ca.CostFilters") -> dict:
    days = int(getattr(filters, "days", 30) or 30)
    return {
        "enabled": True,
        "days": days,
        "series": rs.daily_series(_points(filters), days, rs._utcnow()),
    }


def evolution_signals() -> dict:
    """Contrato hacia la serie RSI: señal operativa de la ventana de 7 días."""
    now = rs._utcnow()
    all_points = _points(ca.CostFilters(days=rs.CURRENT_WINDOW_DAYS + rs.BASELINE_WINDOW_DAYS))
    current, baseline = rs.split_windows(all_points, now)
    thresholds = load_thresholds()

    body = rs.summarize_groups(current)
    regressions = rs.detect_regressions(current, baseline, thresholds)
    breaches, stalls = rs.evaluate_thresholds(current, thresholds, now)

    return {
        "schema_version": 1,
        "generated_at": now.isoformat() + "Z",
        "window_days": rs.CURRENT_WINDOW_DAYS,
        "groups": body["groups"],
        "regressions": regressions,
        "breaches": rs.sort_breaches(breaches + regressions),
        "stalls": stalls,
    }
