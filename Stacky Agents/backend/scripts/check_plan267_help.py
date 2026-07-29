"""Plan 267 §4.1 [C10 + C28] — Verificador de las 3 entradas de PLAIN_HELP.

POR QUE EXISTE: tests/test_harness_flags_help.py arrastra 4 fallos ajenos
preexistentes (medido: 4 failed / 4 passed), y los 4 rojos son EXACTAMENTE las 4
reglas que las entradas nuevas deben cumplir. Un modelo menor no puede distinguir
su propio error del rojo preexistente, asi que ese archivo NO es criterio de
aceptacion de ninguna fase de este plan; este verificador si lo es, porque mira
SOLO las 3 claves del plan 267.

POR QUE ES UN .py Y NO UN `python -c "..."` [C28]: el cuerpo multilinea funciona
en PowerShell pero ROMPE en cmd.exe ("No se esperaba k en este momento"), que
corta el argumento en el primer salto de linea. Asi corre igual en PowerShell,
cmd y bash:

    backend\\.venv\\Scripts\\python.exe backend/scripts/check_plan267_help.py

Aceptacion binaria: imprime OK y sale con codigo 0.
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from services.harness_flags_help import PLAIN_HELP  # noqa: E402

# Denylist congelada de tests/test_harness_flags_help.py: 15 palabras, match por
# palabra completa e insensible a mayusculas.
DENYLIST = (
    "MCP", "TF-IDF", "LLM", "stdin", "stdout", "endpoint", "frontmatter",
    "prompt", "token", "regex", "backend", "frontend", "gate", "hook", "runtime",
)
LIMITES = {"what": 200, "on_effect": 240, "off_effect": 240, "example": 300}
CLAVES = (
    "STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
    "STACKY_DEVOPS_ACTION_NL_ENABLED",
    "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED",
)

_KEY_RE = re.compile(r"\b[A-Z]+_[A-Z0-9_]+\b")
_PHASE_RE = re.compile(r"\bF\d")


def main() -> int:
    errores: list[str] = []
    for clave in CLAVES:
        ayuda = PLAIN_HELP.get(clave)
        if ayuda is None:
            errores.append(f"{clave}: FALTA")
            continue
        for campo, maximo in LIMITES.items():
            valor = getattr(ayuda, campo)
            if not valor or len(valor) > maximo:
                errores.append(
                    f"{clave}.{campo}: largo {len(valor)} > {maximo} o vacio"
                )
        for campo in ("on_effect", "off_effect"):
            if not getattr(ayuda, campo).startswith("Si "):
                errores.append(f"{clave}.{campo}: no empieza con 'Si '")
        texto = " ".join(
            [ayuda.what, ayuda.on_effect, ayuda.off_effect, ayuda.example]
        )
        for palabra in DENYLIST:
            if re.search(r"\b" + re.escape(palabra) + r"\b", texto, re.I):
                errores.append(f"{clave}: jerga prohibida {palabra!r}")
        if _KEY_RE.search(texto):
            errores.append(f"{clave}: cita una clave en mayusculas")
        if _PHASE_RE.search(texto):
            errores.append(f"{clave}: cita una fase")

    print("OK" if not errores else "\n".join(errores))
    return 1 if errores else 0


if __name__ == "__main__":
    raise SystemExit(main())
