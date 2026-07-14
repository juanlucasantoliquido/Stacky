"""services/dbcompare_deps_preflight.py — Plan 125 F0.

Preflight determinista para saber, SIN importar nada, si los modulos de las
fases 122/123/124 del Comparador de BD ya existen en este checkout. Existe
porque este plan (125) se desarrolla en un worktree aislado que puede no
tener todavia el codigo mergeado de los planes de los que depende (solo su
contrato en papel). F1/F2/F4 de este plan son puros y no necesitan nada de
esto; F3 (wrapper por run_id), F5 (API) y F6 (montaje UI) lo consultan antes
de asumir que un modulo ajeno existe.

No es autonomia ni funcionalidad de negocio: es infraestructura de gating,
sin flags, sin impacto de runtime, sin trabajo del operador.
"""
from __future__ import annotations

import importlib
import importlib.util

REQUIRED_MODULES = {
    "diff_engine": "services.dbcompare_diff",  # Plan 123 F1: diff_snapshots
    "runs_store": "services.dbcompare_runs",  # Plan 123 F2: get_run/list_runs
    "api_blueprint": "api.db_compare",  # Plan 122 F4 / 123 F3: blueprint Flask
}


def check_dependencies() -> dict:
    """Reporta, por componente, si el modulo existe (find_spec) sin importarlo."""
    result: dict = {}
    for key, module_name in REQUIRED_MODULES.items():
        result[key] = importlib.util.find_spec(module_name) is not None
    result["all_present"] = all(result[key] for key in REQUIRED_MODULES)
    return result


def require_or_gap(component: str) -> None:
    """Marcador ejecutable de que una fase depende de `component`.

    NO lanza si el componente esta ausente (esa decision es del caller, que
    debe llamar check_dependencies() y documentar el gap). Solo valida que
    `component` sea una key conocida, para atajar typos en el nombre.
    """
    if component not in REQUIRED_MODULES:
        raise KeyError(
            f"componente desconocido: {component!r}; usar uno de {tuple(REQUIRED_MODULES)}"
        )
