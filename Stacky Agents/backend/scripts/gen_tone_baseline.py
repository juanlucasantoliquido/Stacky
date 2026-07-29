"""Plan 267 §4.11 [C32/C33/C35] — Congela el censo de severidad de las
confirmaciones escritas a mano en frontend/src/components/devops/*.tsx.

POR QUE EXISTE: F7 recablea confirmaciones escritas a mano a confirmaciones
DERIVADAS del catalogo. El `tone` deja de estar al lado del boton y pasa a salir
de `a.impact === 'high' ? 'danger' : 'default'`. Si al declarar una accion alguien
pone impact bajo donde el codigo de hoy dice danger, la confirmacion se AFLOJA en
silencio. Esto lo vuelve un dato y un test, en vez de un paso manual.

TRES REGLAS DURAS, cada una es un bloqueante corregido:

  [C35] BARRE el directorio, NO una lista. Emite una entrada por cada archivo con
        >= 1 `askConfirm({`. Prohibido hardcodear nombres: es exactamente el error
        que dejo VariablesSection.tsx invisible en dos pasadas seguidas de critica.

  [C32] El patron de severidad es AGNOSTICO DE COMILLAS:
        tone:\\s*['\"]danger['\"]
        Con la comilla simple sola pierde 2 de 7, incluido SolutionPublisherSection
        -- el archivo con MAS confirmaciones y el que publica en el tracker real.
        Y NO se usa "danger" a secas: hay `tone={... : "danger"}` de StatusChip
        (un badge de estado, no una confirmacion) que el prefijo `tone:` no matchea.

  [C35] Salida con sort_keys e indent, claves = nombre de archivo PELADO, para que
        el .json sea diffeable.

Uso (una sola vez, desde `Stacky Agents`; su salida se commitea tal cual):

    backend\\.venv\\Scripts\\python.exe backend/scripts/gen_tone_baseline.py

Verificacion OBLIGATORIA despues de correrlo: comparar el .json contra la tabla
literal de §4.11 del plan (7 claves; danger 1/1/0/1/2/1/1; askConfirm 2/4/2/1/2/5/2).
Si no coincide, el bug esta en el generador, no en el repo. Un baseline generado
por un script con un bug es un falso verde permanente. Por eso el script tambien
imprime la tabla y sale != 0 si no coincide con el censo esperado.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

_ASK_CONFIRM = re.compile(r"askConfirm\(\{")
_DANGER = re.compile(r"tone:\s*['\"]danger['\"]")

# Censo medido el 2026-07-29 barriendo el directorio. Esta tabla NO la produce el
# generador: esta escrita a mano a proposito, para que un generador con un bug no
# pueda autocertificarse.
_ESPERADO = {
    "BuildWorkshopSection.tsx": {"askConfirm": 2, "danger": 1},
    "PipelineBuilderSection.tsx": {"askConfirm": 4, "danger": 1},
    "ProductionFlow.tsx": {"askConfirm": 2, "danger": 0},
    "RemoteConsoleSection.tsx": {"askConfirm": 1, "danger": 1},
    "ServersSection.tsx": {"askConfirm": 2, "danger": 2},
    "SolutionPublisherSection.tsx": {"askConfirm": 5, "danger": 1},
    "VariablesSection.tsx": {"askConfirm": 2, "danger": 1},
}


def _frontend_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[2] / "frontend"


def censar() -> dict[str, dict[str, int]]:
    """Barre components/devops/*.tsx. Una entrada por archivo con >=1 askConfirm({."""
    devops_dir = _frontend_root() / "src" / "components" / "devops"
    out: dict[str, dict[str, int]] = {}
    for path in sorted(devops_dir.glob("*.tsx")):
        src = path.read_text(encoding="utf-8")
        confirmaciones = len(_ASK_CONFIRM.findall(src))
        if confirmaciones == 0:
            continue
        out[path.name] = {
            "askConfirm": confirmaciones,
            "danger": len(_DANGER.findall(src)),
        }
    return out


def main() -> int:
    censo = censar()
    destino = _frontend_root() / "src" / "__tests__" / "toneBaseline.json"
    destino.write_text(
        json.dumps(censo, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"escrito: {destino}")
    total_ac = sum(v["askConfirm"] for v in censo.values())
    total_dg = sum(v["danger"] for v in censo.values())
    for nombre in sorted(censo):
        v = censo[nombre]
        print(f"  {nombre:34s} askConfirm={v['askConfirm']}  danger={v['danger']}")
    print(f"  {'TOTAL':34s} askConfirm={total_ac}  danger={total_dg}")

    if censo != _ESPERADO:
        print("\nDISCREPANCIA con el censo esperado:")
        for nombre in sorted(set(censo) | set(_ESPERADO)):
            if censo.get(nombre) != _ESPERADO.get(nombre):
                print(f"  {nombre}: medido={censo.get(nombre)} esperado={_ESPERADO.get(nombre)}")
        print(
            "Si el repo cambio a proposito, actualiza _ESPERADO en el MISMO commit "
            "y explica por que. Si no, el bug esta en el generador."
        )
        return 1
    print("\nOK: coincide con el censo esperado (7 claves, 18 askConfirm, 7 danger)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
