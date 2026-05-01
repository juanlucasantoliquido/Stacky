"""
estimation_store.py — F2. Persiste entradas de estimación vs. realidad por ticket
y expone métricas de calibración.

Archivo: ``data/estimations.json`` (esquema v1).

Operaciones principales:
  - ``record_estimate(ticket_id, scoring, ...)``     → guarda la estimación inicial.
  - ``record_actual(ticket_id, duration_minutes, per_stage, rework_cycles)``
                                                      → cierra una entry con
                                                        valores reales.
  - ``compute_accuracy(days, project)``              → estadísticas de precisión.
  - ``suggest_delta_calibration(...)``               → recomienda delta_pct por
                                                        proyecto (solo si hay
                                                        ``min_samples``).

Concurrencia:
  - ``threading.RLock`` intra-proceso.
  - Escritura atómica temp + replace.
  - No hay file lock cross-process (F2 se usa desde el dashboard y watchers
    dentro del mismo proceso Flask). Si en el futuro se comparte con el daemon
    en otro proceso, migrar al patrón de ``pipeline_state.save_state``.
"""

from __future__ import annotations

import json
import logging
import statistics
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ticket_scoring import TicketScoring

logger = logging.getLogger("stacky.estimations")

_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BASE_DIR / "data"
_STORE_PATH = _DATA_DIR / "estimations.json"

_lock = threading.RLock()


# ── I/O seguro ───────────────────────────────────────────────────────────────

def _load() -> dict[str, Any]:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _STORE_PATH.exists():
        data = {"version": 1, "entries": [], "calibration": {
            "last_computed_at": None,
            "global_suggested_delta_pct": 0.0,
            "by_project": {},
        }}
        _save(data)
        return data
    try:
        with _STORE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error("estimations: no se pudo leer %s: %s", _STORE_PATH, e)
        data = {"version": 1, "entries": [], "calibration": {}}
    # Defaults
    data.setdefault("version", 1)
    data.setdefault("entries", [])
    data.setdefault("calibration", {
        "last_computed_at": None,
        "global_suggested_delta_pct": 0.0,
        "by_project": {},
    })
    return data


def _save(data: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _STORE_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            import os
            os.fsync(f.fileno())
        except OSError:
            pass
    tmp.replace(_STORE_PATH)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── API pública ──────────────────────────────────────────────────────────────

def record_estimate(
    ticket_id: str,
    scoring: TicketScoring,
    *,
    project: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """
    Registra (o reemplaza si ya existe) la estimación inicial de un ticket.
    Retorna la entry resultante.
    """
    with _lock:
        data = _load()
        entries: list[dict[str, Any]] = data["entries"]
        idx = _find_entry_index(entries, ticket_id)

        base: dict[str, Any] = {
            "ticket_id":             ticket_id,
            "project":               project,
            "created_at":            created_at or _now_iso(),
            "closed_at":             None,
            "score":                 scoring.score,
            "complexity":            scoring.complexity,
            "factors":               scoring.factors.to_dict(),
            "modules_detected":      list(scoring.modules_detected),
            "similar_tickets_count": scoring.similar_tickets_count,
            "estimated_minutes":     scoring.estimated_minutes,
            "delta_pct_applied":     scoring.delta_pct_applied,
            "delta_source":          scoring.delta_source,
            # F2 Fase 1/2 — qué motor produjo la estimación.
            "estimation_method":     getattr(scoring, "estimation_method", "heuristic"),
            "per_stage":             {
                stage: {"estimated": mins, "actual": None}
                for stage, mins in scoring.per_stage_minutes.items()
            },
            "actual_minutes":        None,
            "deviation_pct":         None,
            "rework_cycles":         0,
            "corrections_sent":      0,
            "first_attempt_approved": None,
        }

        if idx is not None:
            # Preservar valores ya actualizados ("actual*") si existían
            prev = entries[idx]
            for k in ("closed_at", "actual_minutes", "deviation_pct",
                      "rework_cycles", "corrections_sent", "first_attempt_approved"):
                if prev.get(k) is not None:
                    base[k] = prev[k]
            # Preservar actuals por stage
            for stage, meta in (prev.get("per_stage") or {}).items():
                if stage in base["per_stage"]:
                    base["per_stage"][stage]["actual"] = meta.get("actual")
            entries[idx] = base
        else:
            entries.append(base)

        _save(data)
        logger.info("estimations: estimate guardada para #%s (score=%s, est=%dm)",
                    ticket_id, scoring.score, scoring.estimated_minutes)
        return base


def record_actual(
    ticket_id: str,
    *,
    actual_minutes: float | None = None,
    per_stage_actual: dict[str, float] | None = None,
    rework_cycles: int | None = None,
    corrections_sent: int | None = None,
    first_attempt_approved: bool | None = None,
    closed_at: str | None = None,
) -> dict[str, Any] | None:
    """
    Actualiza la entry de un ticket con los valores reales al cerrar el pipeline.
    Si la entry no existe, retorna None (llamador debería haber hecho
    ``record_estimate`` primero; podemos decidir crear una entry "stub" pero
    preferimos no perder contexto silenciosamente).
    """
    with _lock:
        data = _load()
        idx = _find_entry_index(data["entries"], ticket_id)
        if idx is None:
            logger.warning("estimations: record_actual sin entry previa para #%s", ticket_id)
            return None

        entry = data["entries"][idx]
        entry["closed_at"] = closed_at or _now_iso()

        if actual_minutes is not None:
            entry["actual_minutes"] = round(float(actual_minutes), 1)
        if rework_cycles is not None:
            entry["rework_cycles"] = int(rework_cycles)
        if corrections_sent is not None:
            entry["corrections_sent"] = int(corrections_sent)
        if first_attempt_approved is not None:
            entry["first_attempt_approved"] = bool(first_attempt_approved)

        if per_stage_actual:
            for stage, actual in per_stage_actual.items():
                slot = entry["per_stage"].setdefault(stage, {"estimated": None, "actual": None})
                slot["actual"] = round(float(actual), 1) if actual is not None else None

        # Calcular deviation_pct
        est = entry.get("estimated_minutes")
        act = entry.get("actual_minutes")
        if est and act and est > 0:
            entry["deviation_pct"] = round((act - est) / est * 100.0, 2)

        _save(data)
        logger.info("estimations: actuals guardados para #%s (actual=%sm, dev=%s%%)",
                    ticket_id, entry.get("actual_minutes"), entry.get("deviation_pct"))

    # Fuera del lock: hook de re-entrenamiento del modelo de regresión
    # (Fase 2). Best-effort — no debe romper ``record_actual``.
    try:
        if entry.get("actual_minutes") is not None:
            n_closed = sum(
                1 for e in data.get("entries", [])
                if e.get("actual_minutes") is not None
            )
            from estimation_model import maybe_retrain_after_close
            maybe_retrain_after_close(n_closed)
    except Exception as e:
        logger.debug("estimations: maybe_retrain_after_close falló: %s", e)

    return entry


def get_entry(ticket_id: str) -> dict[str, Any] | None:
    with _lock:
        data = _load()
        idx = _find_entry_index(data["entries"], ticket_id)
        return data["entries"][idx] if idx is not None else None


def maybe_close_from_state(ticket_id: str, state_entry: dict[str, Any]) -> bool:
    """
    Hook idempotente: si la entry existe, el ticket está en estado ``completado``
    y aún no tiene ``actual_minutes``, calcula los actuals desde ``state_entry``
    (timing por stage ya lo persiste ``pipeline_state.set_ticket_state``).

    Retorna True si se cerró la entry, False si no hizo nada.
    """
    entry = get_entry(ticket_id)
    if entry is None:
        return False
    if entry.get("actual_minutes") is not None:
        return False  # ya cerrada
    estado = (state_entry or {}).get("estado", "")
    if estado != "completado":
        return False

    per_stage_actual: dict[str, float] = {}
    total_seconds = 0.0
    for stage in ("pm", "dev", "tester", "doc", "pm_revision", "dba", "tl", "dev_rework"):
        dur = (state_entry or {}).get(f"{stage}_duration_sec")
        if dur is not None:
            try:
                dur_min = float(dur) / 60.0
            except (TypeError, ValueError):
                continue
            # Agrupar dev_rework dentro de dev para mantener 3 slots canónicos
            target = "dev" if stage in ("dev", "dev_rework") else \
                     "pm" if stage in ("pm", "pm_revision") else stage
            if target in ("pm", "dev", "tester"):
                per_stage_actual[target] = per_stage_actual.get(target, 0.0) + dur_min
            total_seconds += float(dur)

    actual_minutes = round(total_seconds / 60.0, 1) if total_seconds > 0 else None
    rework_cycles = int((state_entry or {}).get("rework_count", 0) or 0)

    # Determinar first_attempt_approved
    last_verdict = (state_entry or {}).get("last_qa_verdict", "")
    first_attempt_approved = (rework_cycles == 0 and last_verdict in ("APROBADO", ""))

    record_actual(
        ticket_id,
        actual_minutes=actual_minutes,
        per_stage_actual=per_stage_actual or None,
        rework_cycles=rework_cycles,
        first_attempt_approved=first_attempt_approved,
        closed_at=(state_entry or {}).get("completado_at") or _now_iso(),
    )
    return True


def list_entries(
    *, project: str | None = None,
    days: int | None = None,
    closed_only: bool = False,
) -> list[dict[str, Any]]:
    with _lock:
        data = _load()
        entries = list(data["entries"])

    if project:
        entries = [e for e in entries if e.get("project") == project]
    if closed_only:
        entries = [e for e in entries if e.get("closed_at")]
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        def _created(e: dict[str, Any]) -> datetime:
            try:
                return datetime.fromisoformat(e["created_at"])
            except Exception:
                return datetime.min.replace(tzinfo=timezone.utc)
        entries = [e for e in entries if _created(e) >= cutoff]
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return entries


# ── Métricas / calibración ───────────────────────────────────────────────────

def compute_accuracy(*, days: int = 30, project: str | None = None) -> dict[str, Any]:
    """Devuelve métricas de precisión: mean deviation, samples, dentro de ±20%, etc."""
    entries = list_entries(project=project, days=days, closed_only=True)
    deviations = [abs(e["deviation_pct"]) for e in entries
                  if isinstance(e.get("deviation_pct"), (int, float))]
    samples = len(deviations)

    if not samples:
        return {
            "samples": 0,
            "mean_abs_deviation_pct": None,
            "median_abs_deviation_pct": None,
            "within_10pct": 0,
            "within_20pct": 0,
            "within_30pct": 0,
            "by_factor": {},
        }

    within_10 = sum(1 for d in deviations if d <= 10)
    within_20 = sum(1 for d in deviations if d <= 20)
    within_30 = sum(1 for d in deviations if d <= 30)

    # Desvío por factor: promedio del factor entre tickets ordenados por magnitud de deviation
    by_factor: dict[str, dict[str, float]] = {}
    factor_keys = ["tech_complexity", "uncertainty", "impact", "files_affected",
                   "functional_risk", "external_dep"]
    for fk in factor_keys:
        vals = [(e.get("factors") or {}).get(fk) for e in entries]
        nums = [v for v in vals if isinstance(v, (int, float))]
        if nums:
            by_factor[fk] = {
                "avg":    round(statistics.fmean(nums), 1),
                "stdev":  round(statistics.pstdev(nums), 1) if len(nums) > 1 else 0.0,
            }

    return {
        "samples":                samples,
        "mean_abs_deviation_pct": round(statistics.fmean(deviations), 2),
        "median_abs_deviation_pct": round(statistics.median(deviations), 2),
        "within_10pct":           round(within_10 / samples, 3),
        "within_20pct":           round(within_20 / samples, 3),
        "within_30pct":           round(within_30 / samples, 3),
        "by_factor":              by_factor,
    }


def suggest_delta_calibration(*, min_samples: int = 20,
                              project: str | None = None,
                              days: int = 90) -> dict[str, Any]:
    """
    Sugiere un ``delta_pct`` basado en la deviation promedio real (signada).

    Regla: si tickets reales tardan +18% respecto a lo estimado, sugiere delta=+18.
    Requiere ``min_samples`` para evitar calibraciones ruidosas.
    """
    entries = list_entries(project=project, days=days, closed_only=True)
    signed = [e["deviation_pct"] for e in entries
              if isinstance(e.get("deviation_pct"), (int, float))]
    samples = len(signed)

    if samples < min_samples:
        return {
            "suggested_delta_pct": None,
            "samples":             samples,
            "min_samples_required": min_samples,
            "mean_signed_deviation_pct": (round(statistics.fmean(signed), 2)
                                          if signed else None),
            "reason":              f"Insuficientes samples ({samples} < {min_samples})",
        }

    mean_dev = statistics.fmean(signed)
    return {
        "suggested_delta_pct":         round(mean_dev, 2),
        "samples":                     samples,
        "min_samples_required":        min_samples,
        "mean_signed_deviation_pct":   round(mean_dev, 2),
        "mean_abs_deviation_pct":      round(statistics.fmean([abs(d) for d in signed]), 2),
    }


def apply_calibration(*, global_delta_pct: float | None = None,
                      project_deltas: dict[str, float] | None = None) -> dict[str, Any]:
    """
    Persiste delta calibrado en ``calibration`` del store. No modifica entries.
    El consumidor debe leer ``load_calibration()`` antes de scorear nuevos tickets.
    """
    with _lock:
        data = _load()
        cal = data.setdefault("calibration", {})
        cal["last_computed_at"] = _now_iso()
        if global_delta_pct is not None:
            cal["global_suggested_delta_pct"] = round(float(global_delta_pct), 2)
        if project_deltas:
            by_project = cal.setdefault("by_project", {})
            for proj, delta in project_deltas.items():
                prev = by_project.setdefault(proj, {})
                prev["suggested_delta_pct"] = round(float(delta), 2)
                prev["applied_at"] = _now_iso()
        _save(data)
        return dict(cal)


def load_calibration() -> dict[str, Any]:
    with _lock:
        data = _load()
        return dict(data.get("calibration") or {})


# ── Internals ────────────────────────────────────────────────────────────────

def _find_entry_index(entries: list[dict[str, Any]], ticket_id: str) -> int | None:
    for i, e in enumerate(entries):
        if e.get("ticket_id") == ticket_id:
            return i
    return None
