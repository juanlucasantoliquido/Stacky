#!/usr/bin/env python3
"""Kaizen — CLI unificado. Punto de entrada único para operar el ciclo. stdlib pura, portable.

Despacha a los scripts de scripts/ preservando argumentos y código de salida. Pensado para que
CUALQUIER agente u operador ejecute una sesión completa con un solo comando raíz.

Subcomandos:
    new <objetivo> [--mode m] [--adapter a] [--parent id]   crea una sesión
    run <session_id>                                        corre el gate determinista + forense
    validate <session_id> [--strict]                        valida artefactos contra contratos
    spawn-child <session_id>                                crea la hija de una sesión 'iterate'
    promote <session_id>                                    promueve una decisión 'accept' a ADR-lite
    view <session_id> [--errors]                            muestra la traza forense de la sesión
    metrics [--json]                                        reporte forense de eficiencia
    selfcheck                                               guard de consistencia/regresión
    apply <session_id> [--rollback]                         aplica/revierte el change_set (AOTL)
    loop [--engine claude|mock] [--forever] [...]           loop de automejora AI-driven (AOTL)
    dashboard [--port N] [--host H]                         sin --port: genera dashboard/index.html estático (file://)
                                                            con --port: dashboard HTTP en vivo del loop
    help                                                    esta ayuda

Ejemplos:
    python kaizen.py new "mejorar mensajes de error"
    python kaizen.py run 2026-06-21T1925Z__mejorar-mensajes-de-error
    python kaizen.py loop --engine claude --forever        # automejora constante AI-driven
    python kaizen.py dashboard                              # genera dashboard/index.html estático
    python kaizen.py dashboard --port 8765                  # http://127.0.0.1:8765
    python kaizen.py metrics
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"

# subcomando -> script
DISPATCH = {
    "new": "new_session.py",
    "run": "run_session.py",
    "list": "list_sessions.py",
    "show": "show_session.py",
    "validate": "validate.py",
    "spawn-child": "spawn_child.py",
    "promote": "promote_decision.py",
    "view": "forensic_view.py",
    "metrics": "metrics.py",
    "selfcheck": "selfcheck.py",
    "doctor": "doctor.py",
    "adapter": "adapter_info.py",
    "check": "check.py",
    "archive": "archive.py",
    "apply": "apply.py",
    "loop": "autoloop.py",
    "dashboard": "dashboard.py",
}


def print_help() -> None:
    print(__doc__.strip())


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("help", "-h", "--help"):
        print_help()
        return 0
    cmd, rest = argv[0], argv[1:]

    # Bifurcación especial para dashboard: sin --port/--host genera estático (file://)
    if cmd == "dashboard" and not any(a.startswith("--port") or a.startswith("--host") for a in rest):
        result = subprocess.run([sys.executable, str(SCRIPTS / "dashboard_static.py"), *rest], cwd=str(ROOT))
        return result.returncode

    script = DISPATCH.get(cmd)
    if not script:
        print("ERROR: subcomando desconocido %r\n" % cmd, file=sys.stderr)
        print_help()
        return 2
    # Despacho transparente: mismo intérprete, mismo cwd raíz, pasa args y propaga exit code.
    result = subprocess.run([sys.executable, str(SCRIPTS / script), *rest], cwd=str(ROOT))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
