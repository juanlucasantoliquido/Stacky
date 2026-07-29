"""Plan 259 F0 — Tests del registro puro de guias de configuracion.

El modulo bajo prueba (services/setup_guides.py) es PURO: sin flask, sin config,
sin IO, sin red. Estos tests congelan su contenido: el 100 % del texto que ve el
operador queda bajo test y ningun runtime puede "redactarlo distinto".
"""
from __future__ import annotations

import json
import pathlib

import pytest

from services.setup_guides import (
    GITLAB_GUIDE,
    SETUP_GUIDES,
    guide_as_dict,
    guide_exists,
    guide_for,
)

_MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "services" / "setup_guides.py"

# Los 12 pasos de la guia GitLab, en orden. Si se agrega/renombra un paso hay que
# tocar esta lista a mano: es la definicion, no un derivado.
_GITLAB_STEP_IDS = (
    "gl-01-instancia",
    "gl-02-token",
    "gl-03-rol",
    "gl-04-project-path",
    "gl-05-issues",
    "gl-06-grupo",
    "gl-07-stacky-alta",
    "gl-08-motor",
    "gl-09-donde-queda",
    "gl-10-env-precedencia",
    "gl-11-ssl",
    "gl-12-verificar",
)

# Regla determinista, sin juicio (Plan 259 v2, hallazgo C14): estos terminos son
# jerga y no van en el texto que lee el operador.
_JERGA_PROHIBIDA = ("PAT", "namespace", "endpoint", "payload", "scope")

# Excepcion literal: 'scopes' entrecomillado es el ROTULO que GitLab muestra en
# pantalla, asi que el operador lo necesita para encontrar el control.
_JERGA_PERMITIDA_LITERAL = ("'scopes'",)


def test_modulo_es_puro():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    for prohibido in ("import flask", "import config", "import requests", "open(", "Path("):
        assert prohibido not in src, (
            f"services/setup_guides.py debe ser PURO y contiene {prohibido!r}"
        )


def test_gitlab_tiene_los_12_pasos():
    assert len(GITLAB_GUIDE.steps) == 12
    assert tuple(s.id for s in GITLAB_GUIDE.steps) == _GITLAB_STEP_IDS


def test_ids_de_paso_unicos():
    for provider, guide in SETUP_GUIDES.items():
        step_ids = [s.id for s in guide.steps]
        check_ids = [c.id for c in guide.checks]
        assert len(step_ids) == len(set(step_ids)), f"ids de paso repetidos en {provider}"
        assert len(check_ids) == len(set(check_ids)), f"ids de check repetidos en {provider}"


def test_cada_check_apunta_a_un_paso_existente():
    """Este es el invariante que hace UTIL la verificacion: un chequeo que falla
    tiene que poder senalar el paso concreto que lo arregla."""
    for provider, guide in SETUP_GUIDES.items():
        step_ids = {s.id for s in guide.steps}
        for check in guide.checks:
            assert check.fixes_step in step_ids, (
                f"{provider}: el check {check.id} apunta a {check.fixes_step!r}, "
                f"que no es un paso de la guia"
            )


def test_campos_no_vacios():
    for provider, guide in SETUP_GUIDES.items():
        assert guide.summary.strip(), f"{provider} sin summary"
        assert guide.display_name.strip(), f"{provider} sin display_name"
        assert guide.required_fields, f"{provider} sin required_fields"
        for step in guide.steps:
            assert step.title.strip(), f"{provider}/{step.id} sin title"
            assert step.detail.strip(), f"{provider}/{step.id} sin detail"
            assert step.where in {"gitlab", "stacky", "windows"}, (
                f"{provider}/{step.id}: where={step.where!r} fuera del enum"
            )
        for check in guide.checks:
            assert check.title.strip(), f"{provider}/{check.id} sin title"


def test_titulos_acotados():
    for provider, guide in SETUP_GUIDES.items():
        for step in guide.steps:
            assert len(step.title) <= 90, (
                f"{provider}/{step.id}: title de {len(step.title)} chars (max 90)"
            )


def test_sin_jerga():
    for provider, guide in SETUP_GUIDES.items():
        for step in guide.steps:
            texto = step.detail
            for literal in _JERGA_PERMITIDA_LITERAL:
                texto = texto.replace(literal, "")
            for termino in _JERGA_PROHIBIDA:
                assert termino not in texto, (
                    f"{provider}/{step.id}: el detail usa jerga {termino!r}. "
                    f"Reescribilo en llano (o agregalo a _JERGA_PERMITIDA_LITERAL "
                    f"si es un rotulo literal de la pantalla)."
                )


def test_guide_as_dict_serializa_y_es_json():
    d = guide_as_dict("gitlab")
    assert d is not None
    json.dumps(d)  # no debe lanzar
    assert len(d) == 6
    assert set(d) == {
        "provider",
        "display_name",
        "summary",
        "required_fields",
        "steps",
        "checks",
    }
    assert len(d["steps"]) == 12
    assert len(d["checks"]) == 5


def test_guide_as_dict_desconocido_es_none():
    assert guide_as_dict("azure_devops") is None
    assert guide_exists("azure_devops") is False
    assert guide_for("azure_devops") is None


@pytest.mark.parametrize(
    "anclaje",
    [
        "STACKY_GITLAB_ENABLED",
        "GITLAB_TOKEN",
        "gitlab_auth.json",
        "/api/v4/version",
        "'api'",
    ],
)
def test_menciona_los_anclajes_operativos(anclaje):
    """Blinda que la guia no pierda los datos duros al reescribir la prosa."""
    texto = " ".join(
        f"{s.title} {s.detail} {s.trap}" for s in GITLAB_GUIDE.steps
    )
    assert anclaje in texto, f"la guia GitLab ya no menciona {anclaje!r}"
