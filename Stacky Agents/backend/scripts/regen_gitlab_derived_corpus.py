"""Plan 249 F0 — regenerador determinista del corpus GitLab DERIVADO (nivel A).

No vendoriza nada desde una ruta externa: el nivel A se define por una RECETA
(`to_gitlab_yaml(parse_ado_yaml(<golden ADO>))`) que cualquiera puede reproducir con
`python scripts/regen_gitlab_derived_corpus.py`. Correrlo dos veces deja el arbol
byte-identico.

Uso:
    cd "Stacky Agents/backend"
    .venv/Scripts/python.exe scripts/regen_gitlab_derived_corpus.py
"""
from __future__ import annotations

import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

ADO_GOLDEN_DIR = os.path.join(_BACKEND, "tests", "fixtures", "cicd_nl", "golden")
GITLAB_DERIVED_DIR = os.path.join(_BACKEND, "tests", "fixtures", "cicd_gitlab", "derived")

PROVENANCE_HEADER_FMT = (
    "# DERIVADO - NO EDITAR A MANO.\n"
    "# origen: backend/tests/fixtures/cicd_nl/golden/%s\n"
    "# generado por: backend/scripts/regen_gitlab_derived_corpus.py\n"
    "# receta: to_gitlab_yaml(parse_ado_yaml(<origen>))\n"
)


def derived_name(ado_name: str) -> str:
    """'agendaweb-ci.yml' -> 'agendaweb-ci.gitlab-ci.yml'."""
    base = ado_name[:-4] if ado_name.endswith(".yml") else ado_name
    return "%s.gitlab-ci.yml" % base


def render_derived(ado_yaml_text: str) -> str:
    from services.pipeline_renderers import parse_ado_yaml, to_gitlab_yaml  # noqa: PLC0415

    return to_gitlab_yaml(parse_ado_yaml(ado_yaml_text))


def main() -> int:
    os.makedirs(GITLAB_DERIVED_DIR, exist_ok=True)
    for nombre in sorted(os.listdir(ADO_GOLDEN_DIR)):
        if not nombre.endswith(".yml"):
            continue
        origen = os.path.join(ADO_GOLDEN_DIR, nombre)
        with open(origen, "r", encoding="utf-8") as fh:
            ado = fh.read()
        contenido = (PROVENANCE_HEADER_FMT % nombre) + render_derived(ado)
        destino = os.path.join(GITLAB_DERIVED_DIR, derived_name(nombre))
        with open(destino, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(contenido)
        print("escrito %s" % os.path.basename(destino))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
