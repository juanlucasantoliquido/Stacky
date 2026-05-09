"""
migrate_legacy_evidence.py — Reconstruct execution.jsonl from legacy evidence artifacts.

For tickets 116, 119, 120 (and any other pre-Fase2 run) where execution.jsonl is absent,
this script reconstructs a synthetic JSONL from existing artifacts:
  - dossier.json        → verdict, scenario results
  - runner_output.json  → pass/fail/blocked counts per spec
  - scenarios.json      → compiled scenarios + out_of_scope
  - effective_config.json → run config snapshot

The output is marked with legacy=true so log_analyzer can distinguish estimated
from authoritative records.

Usage
-----
    # Migrate all tickets under evidence/
    python scripts/migrate_legacy_evidence.py --all

    # Migrate specific ticket(s)
    python scripts/migrate_legacy_evidence.py --ticket 116 --ticket 119 --ticket 120

    # Dry-run: show what would be written without writing
    python scripts/migrate_legacy_evidence.py --all --dry-run

    # Force overwrite existing execution.jsonl
    python scripts/migrate_legacy_evidence.py --all --force

Output
------
For each evidence/<ticket>/ that lacks execution.jsonl (or when --force),
writes execution.jsonl with synthetic events tagged legacy=true.
Prints a summary of what was migrated.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_TOOL_ROOT = Path(__file__).parent.parent
_EVIDENCE_ROOT = _TOOL_ROOT / "evidence"


# ── JSONL helpers ─────────────────────────────────────────────────────────────

def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event(seq: int, event_name: str, data: dict, **kwargs) -> dict:
    rec = {
        "ts": _utcnow(),
        "session_id": kwargs.get("session_id", "legacy"),
        "seq": seq,
        "event": event_name,
    }
    for field in ("stage", "scenario_id", "ok", "duration_ms"):
        if field in kwargs:
            rec[field] = kwargs[field]
    rec["data"] = data
    return rec


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")


# ── Reconstruction logic ──────────────────────────────────────────────────────

def _load_json(path: Path) -> Optional[dict]:
    """Load a JSON file, returning None on any error."""
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _reconstruct(ticket_dir: Path, ticket_id: str, force: bool, dry_run: bool) -> dict:
    """Reconstruct execution.jsonl for a single ticket evidence directory."""
    jsonl_path = ticket_dir / "execution.jsonl"

    if jsonl_path.is_file() and not force:
        return {"ticket_id": ticket_id, "status": "skipped", "reason": "already_exists"}

    dossier = _load_json(ticket_dir / "dossier.json")
    runner = _load_json(ticket_dir / "runner_output.json")
    scenarios = _load_json(ticket_dir / "scenarios.json")
    config = _load_json(ticket_dir / "effective_config.json")

    if not any([dossier, runner, scenarios]):
        return {"ticket_id": ticket_id, "status": "skipped", "reason": "no_artifacts_found"}

    session_id = ticket_id
    seq = 0
    records: list[dict] = []

    def emit(event_name: str, data: dict, **kw) -> None:
        nonlocal seq
        seq += 1
        records.append(_event(seq, event_name, {**data, "legacy": True},
                              session_id=session_id, **kw))

    # ── session_start ─────────────────────────────────────────────────────────
    emit("session_start", {
        "params": {
            "ticket_id": ticket_id,
            "source": "legacy_migration",
            "legacy": True,
            "migrated_at": _utcnow(),
            "artifacts_found": {
                "dossier.json": dossier is not None,
                "runner_output.json": runner is not None,
                "scenarios.json": scenarios is not None,
                "effective_config.json": config is not None,
            },
        },
        "pid": 0,
        "python": "legacy",
        "cwd": str(ticket_dir),
    })

    # ── reader ────────────────────────────────────────────────────────────────
    emit("stage_start", {"params": {}}, stage="reader")
    emit("stage_end", {"result_summary": {"legacy": True}}, stage="reader", ok=True, duration_ms=0)

    # ── compiler (from scenarios.json) ───────────────────────────────────────
    if scenarios:
        compiled = scenarios.get("compiled", len(scenarios.get("scenarios") or []))
        out_of_scope = scenarios.get("out_of_scope",
                                     len(scenarios.get("out_of_scope_items") or []))
        emit("stage_start", {"params": {}}, stage="compiler")
        emit("stage_end", {
            "result_summary": {"scenario_count": compiled, "out_of_scope": out_of_scope, "legacy": True}
        }, stage="compiler", ok=True, duration_ms=0)
        emit("compiler_summary", {
            "compiled": compiled,
            "scenario_count": compiled,
            "out_of_scope": out_of_scope,
            "out_of_scope_count": out_of_scope,
            "legacy": True,
        })

    # ── runner (from runner_output.json) ─────────────────────────────────────
    if runner:
        pass_c = runner.get("pass", runner.get("pass_count", 0))
        fail_c = runner.get("fail", runner.get("fail_count", 0))
        blocked_c = runner.get("blocked", runner.get("blocked_count", 0))
        total_c = runner.get("total", runner.get("total_count", pass_c + fail_c + blocked_c))
        emit("stage_start", {"params": {}}, stage="runner")
        emit("stage_end", {
            "result_summary": {"pass": pass_c, "fail": fail_c, "blocked": blocked_c,
                               "total": total_c, "legacy": True}
        }, stage="runner", ok=True, duration_ms=0)

        # Emit per-scenario playwright_run_end events
        for run in (runner.get("runs") or []):
            status = run.get("status", "blocked")
            scenario_id = run.get("scenario_id", "")
            seq += 1
            records.append(_event(
                seq, "playwright_run_end",
                {"status": status, "return_code": 0 if status == "pass" else 1,
                 "assertion_failures": run.get("assertion_failures", []),
                 "reason": run.get("reason"), "legacy": True},
                session_id=session_id,
                scenario_id=scenario_id,
                ok=(status == "pass"),
                duration_ms=run.get("duration_ms", 0),
            ))

    # ── session_end (from dossier.json verdict) ───────────────────────────────
    verdict = "UNKNOWN"
    category = None
    if dossier:
        verdict = dossier.get("verdict", "UNKNOWN")
        category = dossier.get("category")

    emit("legacy_import", {
        "source": "dossier.json" if dossier else "runner_output.json",
        "confidence": "estimated",
        "legacy": True,
    })
    emit("session_end", {
        "ok": verdict in ("PASS", "MIXED"),
        "verdict": verdict,
        "category": category,
        "reason": "legacy_migration",
        "elapsed_s": None,
        "stages_summary": {},
        "legacy": True,
    }, ok=(verdict in ("PASS", "MIXED")))

    if dry_run:
        return {
            "ticket_id": ticket_id,
            "status": "dry_run",
            "events_would_write": len(records),
            "verdict": verdict,
        }

    _write_jsonl(jsonl_path, records)
    return {
        "ticket_id": ticket_id,
        "status": "migrated",
        "events_written": len(records),
        "verdict": verdict,
        "path": str(jsonl_path),
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrar evidencia legacy a execution.jsonl",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--all", action="store_true",
                   help="Migrar todos los tickets bajo evidence/")
    g.add_argument("--ticket", action="append", metavar="ID",
                   help="Ticket(s) específicos a migrar (puede repetirse)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo mostrar qué se haría, sin escribir")
    parser.add_argument("--force", action="store_true",
                        help="Sobreescribir execution.jsonl existente")
    parser.add_argument("--evidence-root", default=str(_EVIDENCE_ROOT),
                        help=f"Directorio raíz de evidencia (default: {_EVIDENCE_ROOT})")
    args = parser.parse_args()

    evidence_root = Path(args.evidence_root)
    if not evidence_root.is_dir():
        sys.stderr.write(f"ERROR: evidence root no existe: {evidence_root}\n")
        sys.exit(1)

    # Collect ticket dirs to process
    if args.all:
        ticket_dirs = [
            d for d in evidence_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
    else:
        ticket_dirs = []
        for tid in (args.ticket or []):
            td = evidence_root / tid
            if not td.is_dir():
                sys.stderr.write(f"WARNING: evidence/{tid}/ no existe — saltando\n")
                continue
            ticket_dirs.append(td)

    if not ticket_dirs:
        print("No hay directorios de evidencia a procesar.")
        sys.exit(0)

    results = []
    for td in sorted(ticket_dirs):
        result = _reconstruct(td, td.name, force=args.force, dry_run=args.dry_run)
        results.append(result)

    # Summary
    migrated = [r for r in results if r["status"] == "migrated"]
    dry = [r for r in results if r["status"] == "dry_run"]
    skipped = [r for r in results if r["status"] == "skipped"]

    print(f"\n{'[DRY-RUN] ' if args.dry_run else ''}Migración completada:")
    print(f"  Procesados : {len(results)}")
    print(f"  Migrados   : {len(migrated) + len(dry)}")
    print(f"  Saltados   : {len(skipped)}")
    if skipped:
        for r in skipped:
            print(f"    - {r['ticket_id']}: {r['reason']}")

    for r in results:
        status = r["status"]
        tid = r["ticket_id"]
        if status in ("migrated", "dry_run"):
            n = r.get("events_written") or r.get("events_would_write", 0)
            verdict = r.get("verdict", "?")
            prefix = "[DRY] " if status == "dry_run" else "      "
            print(f"  {prefix}{tid}: {n} events, verdict={verdict}")


if __name__ == "__main__":
    main()
