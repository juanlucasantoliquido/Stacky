#!/usr/bin/env python3
"""Chequeo agregado de Kaizen para CI — 'kaizen check'. stdlib pura.

Corre, en orden, los guards existentes y agrega un veredicto único:
  1. doctor      (salud estructural)
  2. selfcheck   (consistencia de sesiones cerradas)
  3. validate    (cada sesión cerrada cumple los contratos)

Exit 0 sólo si TODO pasa. Pensado como un único comando para un pipeline.
Uso:
    python scripts/check.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
INDEX = ROOT / "sessions" / "_index.json"


def run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          cwd=str(ROOT)).returncode


def main(argv: list[str]) -> int:
    failures = 0

    print("### check 1/3: doctor ###")
    failures += run("doctor.py") != 0

    print("\n### check 2/3: selfcheck ###")
    failures += run("selfcheck.py") != 0

    print("\n### check 3/3: validate de sesiones cerradas ###")
    closed = []
    if INDEX.exists():
        closed = [s["id"] for s in json.loads(INDEX.read_text(encoding="utf-8"))
                  .get("sessions", []) if s.get("status") == "closed"]
    val_fail = 0
    for sid in closed:
        if run("validate.py", sid) != 0:
            val_fail += 1
            print("  -> validate FALLÓ en %s" % sid)
    print("validate: %d/%d sesiones cerradas OK" % (len(closed) - val_fail, len(closed)))
    failures += val_fail > 0

    print("\n" + "=" * 48)
    if failures:
        print("CHECK: FALLÓ (%d grupo(s) con error)" % failures)
        return 1
    print("CHECK: TODO VERDE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
