"""
log_analyzer.py — CLI para analizar y extraer insights de execution.jsonl

Procesa los archivos execution.jsonl generados por ExecutionLogger y produce
reportes de debugging, métricas de calidad y datasets para aprendizaje.

USO
---
    # Resumen de una sesión
    python log_analyzer.py summary --session freeform-20260506-120000

    # Resumen de todas las sesiones
    python log_analyzer.py summary --all

    # Errores de las últimas N sesiones
    python log_analyzer.py errors --last 10

    # Métricas de llamadas LLM (costo/latencia/modelos)
    python log_analyzer.py llm-stats --all

    # Flakiness por escenario (cuántas veces falla vs pasa)
    python log_analyzer.py flakiness --all

    # Tests más lentos
    python log_analyzer.py slow-tests --all --top 20

    # Exportar dataset para aprendizaje (JSONL con un objeto por ejecución de spec)
    python log_analyzer.py export-dataset --all --out dataset.jsonl

    # Listar sesiones disponibles
    python log_analyzer.py list

FILTROS GLOBALES
----------------
    --session <run_id>      Solo esa sesión
    --last N                Solo las N sesiones más recientes
    --all                   Todas las sesiones (default implícito cuando no hay filtro)
    --from YYYY-MM-DD       Solo sesiones desde esa fecha
    --to YYYY-MM-DD         Solo sesiones hasta esa fecha
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

_TOOL_ROOT = Path(__file__).parent
_EVIDENCE_ROOT = _TOOL_ROOT / "evidence"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Análisis de logs de ejecución del QA UAT Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Filtros comunes
    def _add_filters(p: argparse.ArgumentParser) -> None:
        g = p.add_mutually_exclusive_group()
        g.add_argument("--session", help="session_id específico")
        g.add_argument("--last", type=int, metavar="N", help="N sesiones más recientes")
        g.add_argument("--all", action="store_true", help="Todas las sesiones")
        p.add_argument("--from", dest="from_date", metavar="YYYY-MM-DD",
                       help="Solo sesiones desde esta fecha")
        p.add_argument("--to", dest="to_date", metavar="YYYY-MM-DD",
                       help="Solo sesiones hasta esta fecha")
        p.add_argument("--evidence-root", default=str(_EVIDENCE_ROOT),
                       help="Directorio raíz de evidencia")

    # Subcomandos
    p_list = sub.add_parser("list", help="Listar sesiones disponibles")
    _add_filters(p_list)

    p_summary = sub.add_parser("summary", help="Resumen de ejecuciones")
    _add_filters(p_summary)

    p_errors = sub.add_parser("errors", help="Listar errores y excepciones")
    _add_filters(p_errors)
    p_errors.add_argument("--include-playwright", action="store_true",
                           help="Incluir assertion failures de Playwright")

    p_llm = sub.add_parser("llm-stats", help="Estadísticas de llamadas LLM")
    _add_filters(p_llm)

    p_flaky = sub.add_parser("flakiness", help="Análisis de flakiness por escenario")
    _add_filters(p_flaky)
    p_flaky.add_argument("--min-runs", type=int, default=2,
                          help="Mínimo de ejecuciones para incluir (default: 2)")

    p_slow = sub.add_parser("slow-tests", help="Tests más lentos")
    _add_filters(p_slow)
    p_slow.add_argument("--top", type=int, default=10, help="Top N más lentos (default: 10)")

    p_export = sub.add_parser("export-dataset", help="Exportar dataset para aprendizaje")
    _add_filters(p_export)
    p_export.add_argument("--out", default="dataset.jsonl",
                           help="Archivo de salida (default: dataset.jsonl)")

    p_stage_times = sub.add_parser("stage-times", help="Tiempos promedio por stage")
    _add_filters(p_stage_times)

    args = parser.parse_args()
    evidence_root = Path(args.evidence_root)

    sessions = _load_sessions(
        evidence_root=evidence_root,
        session_id=args.session if hasattr(args, "session") else None,
        last_n=args.last if hasattr(args, "last") else None,
        from_date=args.from_date if hasattr(args, "from_date") else None,
        to_date=args.to_date if hasattr(args, "to_date") else None,
    )

    if args.command == "list":
        _cmd_list(sessions)
    elif args.command == "summary":
        _cmd_summary(sessions)
    elif args.command == "errors":
        _cmd_errors(sessions, include_playwright=args.include_playwright)
    elif args.command == "llm-stats":
        _cmd_llm_stats(sessions)
    elif args.command == "flakiness":
        _cmd_flakiness(sessions, min_runs=args.min_runs)
    elif args.command == "slow-tests":
        _cmd_slow_tests(sessions, top_n=args.top)
    elif args.command == "export-dataset":
        _cmd_export_dataset(sessions, out_path=Path(args.out))
    elif args.command == "stage-times":
        _cmd_stage_times(sessions)


# ── Session loading ───────────────────────────────────────────────────────────

class Session:
    """Representa una sesión de ejecución y sus eventos."""
    def __init__(self, session_id: str, log_path: Path) -> None:
        self.session_id = session_id
        self.log_path = log_path
        self._events: Optional[list] = None

    @property
    def events(self) -> list:
        if self._events is None:
            self._events = list(_read_jsonl(self.log_path))
        return self._events

    def events_of(self, *event_types: str) -> list:
        return [e for e in self.events if e.get("event") in event_types]

    @property
    def session_start(self) -> Optional[dict]:
        evts = self.events_of("session_start")
        return evts[0] if evts else None

    @property
    def session_end(self) -> Optional[dict]:
        evts = self.events_of("session_end")
        return evts[0] if evts else None

    @property
    def started_at(self) -> Optional[str]:
        s = self.session_start
        return s["ts"] if s else None

    @property
    def verdict(self) -> str:
        end = self.session_end
        if end:
            return (end.get("data") or {}).get("verdict") or "UNKNOWN"
        return "INCOMPLETE"

    @property
    def ok(self) -> Optional[bool]:
        end = self.session_end
        if end:
            return end.get("ok")
        return None

    @property
    def elapsed_s(self) -> Optional[float]:
        end = self.session_end
        if end:
            return (end.get("data") or {}).get("elapsed_s")
        return None

    @property
    def source(self) -> str:
        s = self.session_start
        if s:
            return (s.get("data") or {}).get("source", "ticket")
        return "unknown"


def _load_sessions(
    evidence_root: Path,
    session_id: Optional[str] = None,
    last_n: Optional[int] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> list[Session]:
    """Cargar sesiones desde evidence_root/*/execution.jsonl."""
    if not evidence_root.is_dir():
        return []

    sessions = []
    for log_path in sorted(evidence_root.rglob("execution.jsonl")):
        sid = log_path.parent.name
        if session_id and sid != session_id:
            continue
        sessions.append(Session(sid, log_path))

    # Filtrar por fecha usando el session_id (que contiene timestamp en freeform)
    if from_date:
        sessions = [s for s in sessions if _session_date(s) >= from_date]
    if to_date:
        sessions = [s for s in sessions if _session_date(s) <= to_date]

    # Ordenar por fecha descendente (más reciente primero) basándose en mtime del archivo
    sessions.sort(key=lambda s: s.log_path.stat().st_mtime, reverse=True)

    if last_n:
        sessions = sessions[:last_n]

    return sessions


def _session_date(s: Session) -> str:
    """Extraer fecha YYYY-MM-DD del timestamp de inicio de sesión o del nombre del archivo."""
    if s.started_at:
        return s.started_at[:10]
    # Fallback: usar mtime
    try:
        mtime = s.log_path.stat().st_mtime
        return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return "0000-00-00"


def _read_jsonl(path: Path) -> Iterator[dict]:
    """Leer un archivo JSONL línea por línea, tolerante a errores."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    sys.stderr.write(f"[log_analyzer] JSONL parse error at {path}:{i}: {exc}\n")
    except OSError as exc:
        sys.stderr.write(f"[log_analyzer] Cannot read {path}: {exc}\n")


# ── Commands ──────────────────────────────────────────────────────────────────

def _cmd_list(sessions: list[Session]) -> None:
    if not sessions:
        print("No sessions found.")
        return
    print(f"{'SESSION ID':<45}  {'DATE':<10}  {'VERDICT':<10}  {'OK':<5}  {'ELAPSED':>8}")
    print("-" * 90)
    for s in sessions:
        date = _session_date(s)
        verdict = s.verdict
        ok = str(s.ok) if s.ok is not None else "—"
        elapsed = f"{s.elapsed_s:.1f}s" if s.elapsed_s is not None else "—"
        print(f"{s.session_id:<45}  {date:<10}  {verdict:<10}  {ok:<5}  {elapsed:>8}")
    print(f"\n{len(sessions)} sessions total.")


def _cmd_summary(sessions: list[Session]) -> None:
    if not sessions:
        print("No sessions found.")
        return

    total = len(sessions)
    pass_c = sum(1 for s in sessions if s.verdict == "PASS")
    fail_c = sum(1 for s in sessions if s.verdict == "FAIL")
    mixed_c = sum(1 for s in sessions if s.verdict == "MIXED")
    blocked_c = sum(1 for s in sessions if s.verdict == "BLOCKED")
    incomplete_c = sum(1 for s in sessions if s.verdict == "INCOMPLETE")
    elapsed_vals = [s.elapsed_s for s in sessions if s.elapsed_s is not None]
    avg_elapsed = sum(elapsed_vals) / len(elapsed_vals) if elapsed_vals else None

    # Playwright run counts
    all_pw = []
    for s in sessions:
        all_pw.extend(s.events_of("playwright_run_end"))
    pw_pass = sum(1 for e in all_pw if (e.get("data") or {}).get("status") == "pass")
    pw_fail = sum(1 for e in all_pw if (e.get("data") or {}).get("status") == "fail")
    pw_blocked = sum(1 for e in all_pw if (e.get("data") or {}).get("status") == "blocked")

    print("\n=== QA UAT Agent — Execution Summary ===")
    print(f"  Sessions analyzed : {total}")
    print(f"  PASS              : {pass_c}  ({_pct(pass_c, total)})")
    print(f"  FAIL              : {fail_c}  ({_pct(fail_c, total)})")
    print(f"  MIXED             : {mixed_c}  ({_pct(mixed_c, total)})")
    print(f"  BLOCKED           : {blocked_c}  ({_pct(blocked_c, total)})")
    print(f"  INCOMPLETE        : {incomplete_c}  ({_pct(incomplete_c, total)})")
    print(f"  Avg elapsed       : {f'{avg_elapsed:.1f}s' if avg_elapsed else '—'}")
    print(f"\n  Playwright specs:")
    print(f"    PASS    : {pw_pass}  ({_pct(pw_pass, len(all_pw))})")
    print(f"    FAIL    : {pw_fail}  ({_pct(pw_fail, len(all_pw))})")
    print(f"    BLOCKED : {pw_blocked}  ({_pct(pw_blocked, len(all_pw))})")
    print(f"    Total   : {len(all_pw)}")


def _cmd_errors(sessions: list[Session], include_playwright: bool = False) -> None:
    if not sessions:
        print("No sessions found.")
        return

    error_events: list[dict] = []
    for s in sessions:
        for e in s.events_of("error", "stage_error", "llm_error"):
            error_events.append({"session_id": s.session_id, "event": e})
        if include_playwright:
            for e in s.events_of("playwright_assertion", "playwright_timeout"):
                error_events.append({"session_id": s.session_id, "event": e})

    if not error_events:
        print("No errors found.")
        return

    print(f"\n=== Errors ({len(error_events)} total) ===\n")
    for item in error_events:
        e = item["event"]
        sid = item["session_id"]
        ts = e.get("ts", "")[:19]
        evt = e.get("event", "")
        data = e.get("data") or {}
        stage = e.get("stage", "")
        scenario = e.get("scenario_id", "")

        print(f"[{ts}] {sid}")
        print(f"  event    : {evt}")
        if stage:
            print(f"  stage    : {stage}")
        if scenario:
            print(f"  scenario : {scenario}")
        if data.get("code"):
            print(f"  code     : {data['code']}")
        if data.get("message"):
            print(f"  message  : {data['message'][:200]}")
        if data.get("exception"):
            print(f"  exception: {data['exception']}")
        if data.get("detail"):
            print(f"  detail   : {str(data['detail'])[:300]}")
        if data.get("stack"):
            # Solo primeras 3 líneas del stack
            stack_lines = data["stack"].strip().split("\n")[:3]
            for sl in stack_lines:
                print(f"    {sl}")
        print()


def _cmd_llm_stats(sessions: list[Session]) -> None:
    if not sessions:
        print("No sessions found.")
        return

    calls: list[dict] = []
    responses: list[dict] = []
    errors: list[dict] = []

    for s in sessions:
        for e in s.events_of("llm_call"):
            calls.append(e.get("data") or {})
        for e in s.events_of("llm_response"):
            responses.append(e.get("data") or {})
        for e in s.events_of("llm_error"):
            errors.append(e.get("data") or {})

    if not calls and not responses:
        print("No LLM calls found.")
        return

    # Estadísticas por modelo
    by_model: dict[str, list] = defaultdict(list)
    for r in responses:
        model = r.get("model", "unknown")
        duration = r.get("duration_ms", 0)
        by_model[model].append(duration)

    # Estadísticas por backend
    by_backend: dict[str, int] = Counter(c.get("backend", "unknown") for c in calls)

    print("\n=== LLM Statistics ===")
    print(f"  Total calls     : {len(calls)}")
    print(f"  Total responses : {len(responses)}")
    print(f"  Total errors    : {len(errors)}")
    print(f"\n  By model:")
    for model, durations in sorted(by_model.items()):
        avg = sum(durations) / len(durations)
        max_d = max(durations)
        min_d = min(durations)
        print(f"    {model:<35}  calls={len(durations):>4}  avg={avg/1000:.2f}s  "
              f"min={min_d/1000:.2f}s  max={max_d/1000:.2f}s")
    print(f"\n  By backend:")
    for backend, count in by_backend.most_common():
        print(f"    {backend:<25}  {count}")

    if errors:
        print(f"\n  Error breakdown:")
        err_codes = Counter(e.get("error", "unknown")[:80] for e in errors)
        for code, count in err_codes.most_common(10):
            print(f"    {count:>4}x  {code}")


def _cmd_flakiness(sessions: list[Session], min_runs: int = 2) -> None:
    if not sessions:
        print("No sessions found.")
        return

    # scenario_id → [status, ...]
    history: dict[str, list[str]] = defaultdict(list)
    for s in sessions:
        for e in s.events_of("playwright_run_end"):
            data = e.get("data") or {}
            sid = e.get("scenario_id") or data.get("scenario_id", "UNKNOWN")
            status = data.get("status", "blocked")
            history[sid].append(status)

    if not history:
        print("No playwright runs found.")
        return

    # Calcular flakiness: escenarios con al menos 1 pass Y 1 fail
    flaky = []
    stable_pass = []
    stable_fail = []
    for sid, statuses in history.items():
        if len(statuses) < min_runs:
            continue
        has_pass = "pass" in statuses
        has_fail = "fail" in statuses or "blocked" in statuses
        pass_rate = statuses.count("pass") / len(statuses)
        if has_pass and has_fail:
            flaky.append((sid, statuses, pass_rate))
        elif has_pass:
            stable_pass.append((sid, statuses, pass_rate))
        else:
            stable_fail.append((sid, statuses, pass_rate))

    flaky.sort(key=lambda x: x[2])  # Más inestables primero

    print("\n=== Flakiness Report ===")
    print(f"  Scenarios analyzed (min {min_runs} runs): {len([s for s in history if len(history[s]) >= min_runs])}")
    print(f"  Flaky (mixed pass/fail)  : {len(flaky)}")
    print(f"  Stable PASS              : {len(stable_pass)}")
    print(f"  Stable FAIL/BLOCKED      : {len(stable_fail)}")

    if flaky:
        print(f"\n  Flaky scenarios (ordered by instability):")
        print(f"  {'SCENARIO':<30}  {'RUNS':>5}  {'PASS%':>6}  HISTORY")
        print(f"  {'-'*80}")
        for sid, statuses, pass_rate in flaky:
            hist_str = " ".join("✓" if s == "pass" else "✗" for s in statuses[-10:])
            print(f"  {sid:<30}  {len(statuses):>5}  {pass_rate*100:>5.1f}%  {hist_str}")

    if stable_fail:
        print(f"\n  Consistently failing:")
        for sid, statuses, _ in stable_fail[:10]:
            fail_reasons = Counter(s for s in statuses if s != "pass")
            print(f"    {sid:<30}  {len(statuses)} runs  {dict(fail_reasons)}")


def _cmd_slow_tests(sessions: list[Session], top_n: int = 10) -> None:
    if not sessions:
        print("No sessions found.")
        return

    runs: list[tuple[str, str, int]] = []  # (session_id, scenario_id, duration_ms)
    for s in sessions:
        for e in s.events_of("playwright_run_end"):
            data = e.get("data") or {}
            scenario_id = e.get("scenario_id") or "UNKNOWN"
            duration_ms = e.get("duration_ms") or 0
            status = data.get("status", "")
            runs.append((s.session_id, scenario_id, duration_ms, status))

    if not runs:
        print("No playwright runs found.")
        return

    runs.sort(key=lambda x: x[2], reverse=True)

    print(f"\n=== Top {top_n} Slowest Playwright Test Runs ===")
    print(f"  {'DURATION':>10}  {'STATUS':<8}  {'SCENARIO':<30}  SESSION ID")
    print(f"  {'-'*90}")
    for session_id, scenario_id, duration_ms, status in runs[:top_n]:
        duration_s = duration_ms / 1000
        print(f"  {duration_s:>9.1f}s  {status:<8}  {scenario_id:<30}  {session_id}")

    # Promedio por escenario
    by_scenario: dict[str, list[int]] = defaultdict(list)
    for _, scenario_id, duration_ms, _ in runs:
        by_scenario[scenario_id].append(duration_ms)

    print(f"\n  Average duration by scenario:")
    avgs = [(sid, sum(durs)/len(durs), len(durs)) for sid, durs in by_scenario.items()]
    avgs.sort(key=lambda x: x[1], reverse=True)
    for sid, avg, count in avgs[:top_n]:
        print(f"    {sid:<30}  avg={avg/1000:.1f}s  runs={count}")


def _cmd_stage_times(sessions: list[Session]) -> None:
    """Tiempo promedio y p95 por stage del pipeline."""
    if not sessions:
        print("No sessions found.")
        return

    stage_durations: dict[str, list[int]] = defaultdict(list)
    for s in sessions:
        for e in s.events_of("stage_end"):
            stage = e.get("stage", "unknown")
            duration_ms = e.get("duration_ms")
            if duration_ms is not None:
                stage_durations[stage].append(duration_ms)

    if not stage_durations:
        print("No stage timing data found.")
        return

    print(f"\n=== Stage Timing Statistics ===")
    print(f"  {'STAGE':<25}  {'RUNS':>5}  {'AVG':>8}  {'MIN':>8}  {'MAX':>8}  {'P95':>8}")
    print(f"  {'-'*75}")

    stage_order = ["reader", "ui_map", "compiler", "preconditions", "generator",
                   "runner", "annotator", "evaluator", "failure_analyzer", "dossier", "publisher"]
    all_stages = stage_order + [s for s in sorted(stage_durations) if s not in stage_order]

    for stage in all_stages:
        if stage not in stage_durations:
            continue
        durs = stage_durations[stage]
        avg = sum(durs) / len(durs)
        mn = min(durs)
        mx = max(durs)
        sorted_durs = sorted(durs)
        p95_idx = max(0, int(len(sorted_durs) * 0.95) - 1)
        p95 = sorted_durs[p95_idx]
        print(f"  {stage:<25}  {len(durs):>5}  {avg/1000:>7.1f}s  {mn/1000:>7.1f}s  "
              f"{mx/1000:>7.1f}s  {p95/1000:>7.1f}s")


def _cmd_export_dataset(sessions: list[Session], out_path: Path) -> None:
    """Exportar dataset de aprendizaje: un objeto JSONL por ejecución de spec."""
    if not sessions:
        print("No sessions found.")
        return

    records: list[dict] = []
    for s in sessions:
        session_start = s.session_start
        session_params = (session_start.get("data") or {}) if session_start else {}

        for e in s.events_of("playwright_run_end"):
            data = e.get("data") or {}
            scenario_id = e.get("scenario_id") or "UNKNOWN"

            # Contexto LLM: qué se llamó durante esta sesión para este escenario
            llm_calls_in_session = [
                {
                    "model": le.get("data", {}).get("model"),
                    "backend": le.get("data", {}).get("backend"),
                    "duration_ms": le.get("duration_ms"),
                }
                for le in s.events_of("llm_call")
            ]

            # Stage times de la sesión
            stage_times = {
                ev.get("stage"): ev.get("duration_ms")
                for ev in s.events_of("stage_end")
                if ev.get("stage") and ev.get("duration_ms") is not None
            }

            record = {
                "session_id": s.session_id,
                "scenario_id": scenario_id,
                "ts": e.get("ts"),
                "status": data.get("status"),
                "duration_ms": e.get("duration_ms"),
                "return_code": data.get("return_code"),
                "assertion_failures": data.get("assertion_failures") or [],
                "assertion_failure_count": len(data.get("assertion_failures") or []),
                "reason": data.get("reason"),
                "verdict": s.verdict,
                "pipeline_ok": s.ok,
                "pipeline_elapsed_s": s.elapsed_s,
                "source": s.source,
                "headed": session_params.get("headed"),
                "timeout_ms": session_params.get("timeout_ms"),
                "llm_call_count": len(llm_calls_in_session),
                "stage_times": stage_times,
                "has_playwright_output": (
                    _EVIDENCE_ROOT / s.session_id / scenario_id / "playwright_output.txt"
                ).is_file(),
            }
            records.append(record)

    with out_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    print(f"Dataset exported: {out_path} ({len(records)} records from {len(sessions)} sessions)")


# ── Utils ──────────────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0%"
    return f"{n*100/total:.1f}%"


if __name__ == "__main__":
    main()
