#!/usr/bin/env python3
"""Reporte forense de eficiencia de Kaizen — stdlib pura.

Lee el índice de sesiones (sessions/_index.json) y el log forense global
(sessions/_forensic.jsonl) y produce un resumen analizable:
  - conteo de sesiones y distribución de veredictos
  - tasa de aceptación y de escalado a humano
  - eficiencia: duración (elapsed_ms) por run, eventos por run, errores/warnings
  - línea de tiempo por sesión (eventos clave)

Uso:
    python scripts/metrics.py            # reporte de texto
    python scripts/metrics.py --json     # salida JSON para análisis programático
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
enable_utf8()

INDEX = ROOT / "sessions" / "_index.json"
FORENSIC = ROOT / "sessions" / "_forensic.jsonl"


def read_index() -> list[dict]:
    if not INDEX.exists():
        return []
    return json.loads(INDEX.read_text(encoding="utf-8")).get("sessions", [])


def read_forensic() -> list[dict]:
    if not FORENSIC.exists():
        return []
    out = []
    for line in FORENSIC.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def summarize(index: list[dict], events: list[dict]) -> dict:
    verdicts: dict[str, int] = {}
    for s in index:
        v = s.get("verdict", "(sin correr)")
        verdicts[v] = verdicts.get(v, 0) + 1

    # Agrupar eventos por run_id.
    runs: dict[str, list[dict]] = {}
    for e in events:
        runs.setdefault(e.get("run_id", "?"), []).append(e)

    run_stats = []
    for run_id, evs in runs.items():
        evs_sorted = sorted(evs, key=lambda e: e.get("seq", 0))
        elapsed = max((e.get("elapsed_ms", 0) for e in evs), default=0)
        end = next((e for e in evs_sorted if e.get("event") == "run.end"), None)
        run_stats.append({
            "run_id": run_id,
            "session_id": evs_sorted[0].get("session_id"),
            "run_kind": evs_sorted[0].get("run_kind"),
            "events": len(evs),
            "elapsed_ms": elapsed,
            "errors": sum(1 for e in evs if e.get("level") == "ERROR"),
            "warnings": sum(1 for e in evs if e.get("level") == "WARN"),
            "verdict": (end or {}).get("data", {}).get("verdict"),
        })

    n_runs = len(run_stats)
    avg_elapsed = round(sum(r["elapsed_ms"] for r in run_stats) / n_runs, 2) if n_runs else 0
    avg_events = round(sum(r["events"] for r in run_stats) / n_runs, 2) if n_runs else 0

    elapsed_sorted = sorted(r["elapsed_ms"] for r in run_stats)

    def _median(xs):
        if not xs:
            return 0
        m = len(xs) // 2
        return xs[m] if len(xs) % 2 else round((xs[m - 1] + xs[m]) / 2, 2)

    median_elapsed = _median(elapsed_sorted)
    min_elapsed = elapsed_sorted[0] if elapsed_sorted else 0
    max_elapsed = elapsed_sorted[-1] if elapsed_sorted else 0
    accepted = verdicts.get("accept", 0)
    decided = sum(v for k, v in verdicts.items() if k in ("accept", "reject", "iterate"))
    escalations = sum(1 for e in events if e.get("event") == "decision.written"
                      and e.get("data", {}).get("escalated"))

    return {
        "sessions_total": len(index),
        "verdict_distribution": verdicts,
        "acceptance_rate": round(accepted / decided, 3) if decided else None,
        "runs_total": n_runs,
        "avg_elapsed_ms": avg_elapsed,
        "median_elapsed_ms": median_elapsed,
        "min_elapsed_ms": min_elapsed,
        "max_elapsed_ms": max_elapsed,
        "avg_events_per_run": avg_events,
        "total_errors": sum(r["errors"] for r in run_stats),
        "total_warnings": sum(r["warnings"] for r in run_stats),
        "escalations_to_human": escalations,
        "runs": sorted(run_stats, key=lambda r: r["run_id"]),
    }


def print_report(summary: dict) -> None:
    print("=" * 64)
    print("KAIZEN — Reporte Forense de Eficiencia")
    print("=" * 64)
    print("Sesiones totales:        %d" % summary["sessions_total"])
    print("Veredictos:              %s" % summary["verdict_distribution"])
    print("Tasa de aceptación:      %s" % summary["acceptance_rate"])
    print("Runs del arnés:          %d" % summary["runs_total"])
    print("Duración por run (ms):   media=%.2f mediana=%.2f min=%.2f max=%.2f" % (
        summary["avg_elapsed_ms"], summary["median_elapsed_ms"],
        summary["min_elapsed_ms"], summary["max_elapsed_ms"]))
    print("Eventos medios por run:  %.2f" % summary["avg_events_per_run"])
    print("Errores / Warnings:      %d / %d" %
          (summary["total_errors"], summary["total_warnings"]))
    print("Escalados a humano:      %d" % summary["escalations_to_human"])
    print("-" * 64)
    print("Detalle por run:")
    for r in summary["runs"]:
        print("  [%s] %s | %s | ev=%d t=%.1fms err=%d warn=%d verdict=%s" % (
            r["run_kind"], r["session_id"], r["run_id"], r["events"],
            r["elapsed_ms"], r["errors"], r["warnings"], r["verdict"]))
    print("=" * 64)


def main(argv: list[str]) -> int:
    index = read_index()
    events = read_forensic()
    summary = summarize(index, events)
    if "--json" in argv:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print_report(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
