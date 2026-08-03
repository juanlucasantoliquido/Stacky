"""Plan 295 F12 — ninguna de las once fases ató nada a un runtime.

Los tres runtimes (Codex CLI, Claude Code CLI, GitHub Copilot Pro) tienen que
comportarse IGUAL con todo lo que este plan construyó: es Python puro del backend y
TypeScript puro del frontend, y ningún test invoca un CLI de agente.

También congela los dos límites de arquitectura que el plan promete no cruzar:
`services/` NO importa de `api/`, y `provider_capabilities` sigue siendo PURO.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_RUNTIMES = ("codex", "claude_code", "github_copilot")

# Menciones de runtime MEDIDAS al implementar el plan 295. Es un RATCHET: sólo
# puede bajar. Un absoluto "cero" sería un falso rojo -- estos dos archivos ya
# nombraban runtimes ANTES de este plan, y el plan no los tocó:
#   * api/tickets.py:7074  — docstring de un endpoint ajeno
#   * api/tickets.py:8565  — "publishable_runtime", de otro plan
#   * api/phase6.py:192    — resolve_run_selection(runtime="github_copilot") HARDCODEADO,
#                            con project_name=None. F9 NO lo cambió y lo declara como
#                            deuda en §D-4 del plan: el webhook de CI corre el
#                            DebugAgent SIEMPRE con Copilot, ignorando la selección
#                            del proyecto. Excluirlo en silencio sería un gate vacío;
#                            con el motivo escrito y un tope que sólo baja, es un
#                            ratchet honesto.
_TOPE_MENCIONES_RUNTIME: dict[str, int] = {
    "services/provider_capabilities.py": 0,
    "services/gitlab_setup_check.py": 0,
    "services/integration_breaker.py": 0,
    "api/setup_guide.py": 0,
    # MEDIDO por SUBCADENA, no por línea: `grep -c` cuenta LÍNEAS y la línea 8565
    # trae dos ocurrencias. Contar mal el baseline de un ratchet lo vuelve un falso
    # rojo el día que alguien lo corra en frío.
    "api/tickets.py": 3,   # preexistentes, ajenas a este plan
    "api/phase6.py": 2,    # preexistentes (:192 y su import), ver §D-4
}


def _fuente(rel: str) -> str:
    return (_BACKEND / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", sorted(_TOPE_MENCIONES_RUNTIME))
def test_1_ningun_archivo_gana_menciones_de_runtime(rel):
    texto = _fuente(rel).lower()
    n = sum(texto.count(r) for r in _RUNTIMES)
    assert n <= _TOPE_MENCIONES_RUNTIME[rel], (
        f"{rel} pasó de {_TOPE_MENCIONES_RUNTIME[rel]} a {n} menciones de runtime. "
        "Nada de este plan puede depender de un runtime concreto: si agregaste una "
        "mención legítima, bajá el tope sólo con la justificación escrita."
    )


def test_2_gitlab_setup_check_no_importa_de_api():
    fuente = _fuente("services/gitlab_setup_check.py")
    assert "from api" not in fuente and "import api" not in fuente


def test_3_integration_breaker_no_importa_de_api():
    fuente = _fuente("services/integration_breaker.py")
    assert "from api" not in fuente and "import api" not in fuente


def test_4_provider_capabilities_sigue_siendo_puro():
    """Su propio docstring (:1-11) lo declara: sin red, sin DB, sin importar
    adaptadores. El mapa de F3 guarda STRINGS y resolverlos es trabajo del test."""
    fuente = _fuente("services/provider_capabilities.py")
    for prohibido in ("import requests", "session_scope", "from services.gitlab_provider",
                      "from services.ado_provider"):
        assert prohibido not in fuente, f"provider_capabilities dejó de ser puro: {prohibido}"


def test_5_las_tres_flags_nuevas_estan_completas():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS, categorize
    from services.harness_flags_help import PLAIN_HELP

    nuevas = (
        "STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED",
        "STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED",
        "STACKY_TICKET_SYNC_INTERVAL_MS",
    )
    keys = {s.key for s in FLAG_REGISTRY}
    for k in nuevas:
        assert k in keys, f"{k} no está en FLAG_REGISTRY"
        assert k in _CATEGORY_KEYS["paridad_proveedores"], f"{k} sin categoría"
        assert categorize(k) != "otros", f"{k} cayó en el fallback de categorize()"
        assert k in PLAIN_HELP, f"{k} sin PLAIN_HELP"


def test_6_ninguna_de_las_tres_declara_requires():
    """Con `requires=` habría que tocar _REQUIRES_MAP_FROZEN, que este plan no toca."""
    from services.harness_flags import FLAG_REGISTRY

    idx = {s.key: s for s in FLAG_REGISTRY}
    for k in ("STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED",
              "STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED",
              "STACKY_TICKET_SYNC_INTERVAL_MS"):
        assert idx[k].requires is None, f"{k} declara requires={idx[k].requires!r}"


def test_7_solo_la_booleanas_ON_declaran_default():
    """La regla dura que separa las dos booleanas ON de la numérica."""
    from services.harness_flags import FLAG_REGISTRY

    idx = {s.key: s for s in FLAG_REGISTRY}
    assert idx["STACKY_GITLAB_SYNC_ERRORS_ROUTED_ENABLED"].default is True
    assert idx["STACKY_WEBHOOK_TICKET_AUTOCREATE_ENABLED"].default is True
    assert idx["STACKY_TICKET_SYNC_INTERVAL_MS"].default is None
