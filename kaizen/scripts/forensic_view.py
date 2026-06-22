#!/usr/bin/env python3
"""Visor de la traza forense de una sesión — línea de tiempo legible. stdlib pura, solo-lectura.

Lee sessions/<id>/forensic.jsonl y la renderiza como timeline con fase, nivel, tiempo y datos
clave. Útil para auditar una sesión puntual sin parsear JSON a mano.

Uso:
    python scripts/forensic_view.py <session_id>
    python scripts/forensic_view.py <session_id> --errors   # solo WARN/ERROR
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

_KEY_FIELDS = ("verdict", "total", "confidence", "artifact", "missing", "status",
               "escalate_to_human", "escalated", "sha256")


def fmt_data(data: dict) -> str:
    parts = []
    for k in _KEY_FIELDS:
        if k in data:
            v = data[k]
            if k == "sha256" and isinstance(v, str):
                v = v[:12]
            parts.append("%s=%s" % (k, v))
    return "  ".join(parts)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    only_problems = "--errors" in argv
    if not args:
        print("uso: python scripts/forensic_view.py <session_id> [--errors]", file=sys.stderr)
        return 2
    session_id = args[0]
    log = SESSIONS / session_id / "forensic.jsonl"
    if not log.exists():
        print("ERROR: no hay traza forense para %s" % session_id, file=sys.stderr)
        return 1

    events = [json.loads(l) for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
    print("=" * 70)
    print("Traza forense — %s" % session_id)
    print("Eventos: %d  |  runs: %d" %
          (len(events), len({e.get("run_id") for e in events})))
    print("=" * 70)
    last_run = None
    for e in events:
        if only_problems and e.get("level") == "INFO":
            continue
        if e.get("run_id") != last_run:
            last_run = e.get("run_id")
            print("-- run %s (%s) --" % (last_run, e.get("run_kind")))
        mark = {"INFO": " ", "WARN": "!", "ERROR": "X"}.get(e.get("level"), "?")
        print(" %s seq=%-2d +%8.2fms [%-8s] %-18s %s" % (
            mark, e.get("seq"), e.get("elapsed_ms", 0), e.get("phase"),
            e.get("event"), fmt_data(e.get("data", {}))))
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
