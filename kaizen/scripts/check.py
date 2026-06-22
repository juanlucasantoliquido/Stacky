#!/usr/bin/env python3
"""Chequeo agregado de Kaizen para CI — 'kaizen check'. stdlib pura.

Corre, en orden, los guards existentes y agrega un veredicto unico:
  1. doctor      (salud estructural)
  2. selfcheck   (consistencia de sesiones cerradas)
  3. validate    (cada sesion cerrada cumple los contratos)
  4. test_core   (logica pura — percentile, decisions, dashboard, metrics, archive, etc.)
  5. test_aotl   (maquinaria del loop — guardrail, gate, apply/rollback, aotl_state, forensic)

El conteo de tests es DINAMICO: se extrae del output real de los runners (no hardcodeado).
Exit 0 solo si TODO pasa. Pensado como un unico comando para un pipeline.
Uso:
    python scripts/check.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
INDEX = ROOT / "sessions" / "_index.json"


def run(script: str, *args: str) -> int:
    return subprocess.run([sys.executable, str(SCRIPTS / script), *args],
                          cwd=str(ROOT)).returncode


def run_and_capture(script: str, *args: str) -> tuple[int, str]:
    """Corre script y devuelve (returncode, stdout+stderr combinado)."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = result.stdout + result.stderr
    print(output, end="")
    return result.returncode, output


def _parse_test_count(output: str) -> int:
    """Extrae el total de tests del output de test_core.py o test_aotl.py.

    test_core.py imprime: '85 OK, 0 FAIL'
    test_aotl.py imprime: '50/50 verdes.'
    Devuelve 0 si no puede parsear (fallo silencioso).
    """
    # Patron para test_core: '<N> OK, <M> FAIL'
    m = re.search(r"(\d+)\s+OK,\s+\d+\s+FAIL", output)
    if m:
        return int(m.group(1))
    # Patron para test_aotl: '<N>/<N> verdes.'
    m = re.search(r"(\d+)/\d+\s+verdes\.", output)
    if m:
        return int(m.group(1))
    return 0


def main(argv: list[str]) -> int:
    failures = 0

    print("### check 1/5: doctor ###")
    failures += run("doctor.py") != 0

    print("\n### check 2/5: selfcheck ###")
    failures += run("selfcheck.py") != 0

    print("\n### check 3/5: validate de sesiones cerradas ###")
    closed = []
    if INDEX.exists():
        closed = [s["id"] for s in json.loads(INDEX.read_text(encoding="utf-8"))
                  .get("sessions", []) if s.get("status") == "closed"]
    val_fail = 0
    for sid in closed:
        if run("validate.py", sid) != 0:
            val_fail += 1
            print("  -> validate FALLO en %s" % sid)
    print("validate: %d/%d sesiones cerradas OK" % (len(closed) - val_fail, len(closed)))
    failures += val_fail > 0

    print("\n### check 4/5: test_core (logica pura) ###")
    rc4, out4 = run_and_capture("test_core.py")
    failures += rc4 != 0
    core_count = _parse_test_count(out4)

    print("\n### check 5/5: test_aotl (maquinaria del loop) ###")
    rc5, out5 = run_and_capture("test_aotl.py")
    failures += rc5 != 0
    aotl_count = _parse_test_count(out5)

    total = core_count + aotl_count
    total_str = ("%d tests unitarios" % total) if total > 0 else "N tests unitarios"

    print("\n" + "=" * 48)
    if failures:
        print("CHECK: FALLO (%d grupo(s) con error)" % failures)
        return 1
    print("CHECK: TODO VERDE  [5/5 grupos OK | %s]" % total_str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
