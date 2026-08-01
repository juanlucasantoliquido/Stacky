"""Plan 279 F0 — Censo congelado y guarda anti-falso-verde.

Congela el estado al que el plan lleva el catalogo, para que cualquier deriva
posterior sea VISIBLE. Nace ROJO a proposito y se pone verde al terminar F3: es
el ratchet del plan, no un gate de arranque.

[C1] El caso 3 vigila que el guard hermano (tests/test_devops_action_catalog.py)
se EDITE de 7 a 8 y NO se borre: borrarlo dejaria nacer una escritura fuera del
conteo con los dos tests en verde.

[C2] Este archivo NO gatea K1 (que el catalogo llegue al turno del agente): un
grep/substring sobre api/devops_agent.py lo satisface un comentario. K1 se mide
SOLO en tests/test_plan279_agent_turn.py casos 3 y 8 (ast + comportamiento).
"""
from __future__ import annotations

import pathlib

from services.devops_action_catalog import DEVOPS_ACTION_CATALOG, get_action

#: Los 6 ids que F3 agrega. Literales: si uno cambia de nombre, este test cae.
_IDS_NUEVOS = (
    "devops.pipeline_new.draft",
    "devops.pipeline_new.lint",
    "devops.pipeline_new.explain",
    "devops.pipeline_new.preflight",
    "devops.pipeline_new.secrets",
    "devops.pipeline_new.commit",
)

_SUITE_HERMANA = (
    pathlib.Path(__file__).resolve().parent / "test_devops_action_catalog.py"
)


def test_catalogo_tiene_29_acciones_al_terminar_el_plan():
    assert len(DEVOPS_ACTION_CATALOG) == 29, len(DEVOPS_ACTION_CATALOG)


def test_las_6_acciones_nuevas_existen():
    faltantes = [i for i in _IDS_NUEVOS if get_action(i) is None]
    assert faltantes == [], faltantes


def test_la_suite_hermana_cuenta_8_escrituras():
    """[C1] El ratchet se APRIETA, no se borra.

    tests/test_devops_action_catalog.py::test_palette_actions_excluye_ejecucion_de_escritura
    congela las escrituras POR IGUALDAD. F3 lo edita de `== 7` a `== 8`.
    Si alguien lo borra, lo comenta o lo relaja a `>=`, este caso lo caza.
    """
    assert _SUITE_HERMANA.exists(), f"no existe {_SUITE_HERMANA}"
    src = _SUITE_HERMANA.read_text(encoding="utf-8")
    assert "assert len(escrituras) == 8" in src, (
        "el guard hermano dejo de decir `assert len(escrituras) == 8`: "
        "se esperaba que F3 lo EDITARA de 7 a 8, no que lo borrara ni lo "
        "relajara a >=."
    )


def test_lectura_y_escritura_siguen_separadas():
    escrituras = [a for a in DEVOPS_ACTION_CATALOG if a.effect == "write"]
    lecturas = [a for a in DEVOPS_ACTION_CATALOG if a.effect == "read"]
    assert len(escrituras) == 8, sorted(a.id for a in escrituras)
    assert len(lecturas) == 21, len(lecturas)
