#!/usr/bin/env python3
"""Lista las sesiones del índice con su estado y veredicto. stdlib pura, solo-lectura.

Uso:
    python scripts/list_sessions.py                 # todas
    python scripts/list_sessions.py --status open   # filtra por estado
    python scripts/list_sessions.py --verdict accept
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


def get_opt(argv: list[str], name: str) -> str | None:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return None


def main(argv: list[str]) -> int:
    if not INDEX.exists():
        print("(sin índice de sesiones)")
        return 0
    sessions = json.loads(INDEX.read_text(encoding="utf-8")).get("sessions", [])
    f_status = get_opt(argv, "--status")
    f_verdict = get_opt(argv, "--verdict")

    rows = []
    for s in sessions:
        if f_status and s.get("status") != f_status:
            continue
        if f_verdict and s.get("verdict") != f_verdict:
            continue
        rows.append(s)

    print("%-3s %-44s %-9s %-8s %s" % ("#", "id", "status", "verdict", "objetivo"))
    print("-" * 100)
    for i, s in enumerate(rows, 1):
        print("%-3d %-44s %-9s %-8s %s" % (
            i, s.get("id", "?"), s.get("status", "?"),
            s.get("verdict", "-"), s.get("objective", "")))
    print("-" * 100)
    print("total: %d sesión(es)%s" % (
        len(rows),
        "" if not (f_status or f_verdict) else " (filtradas de %d)" % len(sessions)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
