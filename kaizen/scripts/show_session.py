#!/usr/bin/env python3
"""Muestra un resumen legible de una sesión. 'kaizen show'. stdlib pura, solo-lectura.

Reúne objetivo, propuesta, evaluación y decisión en una vista compacta. Si existe
session.output.json lo usa; si no, lee los artefactos sueltos.

Uso:
    python scripts/show_session.py <session_id>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
enable_utf8()

SESSIONS = ROOT / "sessions"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: python scripts/show_session.py <session_id>", file=sys.stderr)
        return 2
    sid = argv[0]
    sdir = SESSIONS / sid
    if not sdir.is_dir():
        print("ERROR: no existe la sesión %s" % sid, file=sys.stderr)
        return 1

    session = load(sdir / "session.json")
    proposal = load(sdir / "proposal.json")
    evaluation = load(sdir / "evaluation.json")
    decision = load(sdir / "decision.json")

    print("=" * 66)
    print("Sesión: %s" % sid)
    print("=" * 66)
    print("Objetivo : %s" % session.get("objective", "—"))
    print("Modo     : %s   Adapter: %s   Tags: %s" % (
        session.get("mode", "—"), session.get("adapter", "—"),
        ", ".join(session.get("tags", [])) or "—"))
    if session.get("parent_session"):
        print("Madre    : %s" % session["parent_session"])
    print("-" * 66)
    if proposal:
        print("Propuesta: %s" % proposal.get("title", "—"))
        print("  %s" % proposal.get("summary", ""))
        rev = proposal.get("reversibility", {})
        print("  rollback: %s" % rev.get("rollback", "—"))
        print("  métrica : %s" % proposal.get("success_metric", "—"))
    if evaluation:
        print("-" * 66)
        print("Evaluación: total=%s  confianza=%s  bloqueantes=%s" % (
            evaluation.get("total"), evaluation.get("confidence"),
            evaluation.get("blocking") or "ninguno"))
        for f in evaluation.get("findings", []):
            print("  - %s" % f)
    if decision:
        print("-" * 66)
        print("Decisión : %s (por %s)  escalado=%s" % (
            decision.get("verdict"), decision.get("decided_by"),
            decision.get("escalated_to_human")))
        print("  %s" % decision.get("rationale", ""))
        if decision.get("child_session"):
            print("  hija: %s" % decision["child_session"])
    else:
        print("-" * 66)
        print("Decisión : (sin correr el gate todavía)")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
