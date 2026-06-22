#!/usr/bin/env python3
"""Promueve la decisión de una sesión aceptada a un ADR-lite en decisions/. stdlib pura.

decisions/ es el registro append-only de decisiones que sientan precedente (ver decisions/README).
Este script toma una sesión con verdict 'accept' y escribe decisions/NNNN-<slug>.md con el
formato ADR-lite, de forma idempotente (no re-promueve la misma sesión).

Uso:
    python scripts/promote_decision.py <session_id>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "sessions"
DECISIONS = ROOT / "decisions"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def next_adr_number() -> int:
    nums = [int(m.group(1)) for p in DECISIONS.glob("[0-9]*.md")
            for m in [re.match(r"^(\d+)-", p.name)] if m]
    return (max(nums) + 1) if nums else 1


def already_promoted(session_id: str) -> Path | None:
    marker = "session: %s" % session_id
    for p in DECISIONS.glob("[0-9]*.md"):
        if marker in p.read_text(encoding="utf-8"):
            return p
    return None


def main(argv: list[str]) -> int:
    if not argv:
        print("uso: python scripts/promote_decision.py <session_id>", file=sys.stderr)
        return 2
    session_id = argv[0]
    sdir = SESSIONS / session_id
    decision_path = sdir / "decision.json"
    if not decision_path.exists():
        print("ERROR: la sesión no tiene decision.json", file=sys.stderr)
        return 1
    decision = load_json(decision_path)
    if decision.get("verdict") != "accept":
        print("ERROR: solo se promueven decisiones 'accept' (verdict=%s)" %
              decision.get("verdict"), file=sys.stderr)
        return 1

    existing = already_promoted(session_id)
    if existing:
        print(existing.relative_to(ROOT).as_posix())  # idempotente
        return 0

    proposal = load_json(sdir / "proposal.json") if (sdir / "proposal.json").exists() else {}
    session = load_json(sdir / "session.json")

    number = next_adr_number()
    slug = re.sub(r"[^a-z0-9]+", "-", session.get("objective", session_id).lower()).strip("-")
    adr_path = DECISIONS / ("%04d-%s.md" % (number, slug))
    rollback = proposal.get("reversibility", {}).get("rollback", "—")

    content = (
        "# ADR %04d — %s\n\n"
        "- session: %s\n"
        "- Fecha (UTC): %s\n"
        "- Veredicto: %s (por %s)\n\n"
        "## Contexto\n%s\n\n"
        "## Decisión\n%s\n\n"
        "## Consecuencias / rollback\n%s\n"
    ) % (
        number, proposal.get("title", session.get("objective", session_id)),
        session_id, decision.get("decided_utc", "—"),
        decision.get("verdict"), decision.get("decided_by", "—"),
        proposal.get("motivation", "—"),
        decision.get("rationale", "—"),
        rollback,
    )
    adr_path.write_text(content, encoding="utf-8")
    print(adr_path.relative_to(ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
