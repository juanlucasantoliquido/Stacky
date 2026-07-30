"""Plan 260 F2 — núcleo PURO del plan de declaración (sin red, sin I/O).

Decide, a partir de una matriz ya construida, qué nombres declarar (con valor
vacío) y cuáles saltar, y por qué. El módulo 251 (pipeline_environments.py)
queda intacto: esto vive en un módulo NUEVO aparte.
"""
from __future__ import annotations

import re

from services.pipeline_environments import (
    Cell,
    PROVIDER_ADO,
    PROVIDER_GITLAB,
    Requirement,
)


def _req(name, kind="variable", is_secret=False, provider=PROVIDER_ADO, confidence="alta"):
    return Requirement(
        name=name, kind=kind, provider=provider, is_secret=is_secret,
        declared_default=None, per_environment=True, confidence=confidence, evidence=(),
    )


class _FakeMatrix:
    """EnvMatrix minimal para F2: plan_declaration solo lee .requirements y .cells."""

    def __init__(self, requirements, cells):
        self.requirements = tuple(requirements)
        self.cells = tuple(cells)


def _fake_matrix(requirements, cells):
    return _FakeMatrix(requirements, cells)


def test_f2_modulo_puro():
    """Gotcha recurrido 6 veces en esta casa: el gate se escribe con \\bprint\\(,
    no con la subcadena suelta, porque un símbolo legítimo puede contenerla
    (Blueprint( es el caso real). El test verifica su propio gate."""
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent / "services"
           / "pipeline_env_declare.py").read_text(encoding="utf-8")

    # Auto-test del propio gate: "Blueprint(" no debe disparar \bprint\(.
    assert re.search(r"\bprint\(", "Blueprint(") is None

    assert re.search(r"\bprint\(", src) is None, "no debe imprimir nada"
    assert re.search(r"\blogger\.", src) is None, "no debe loggear nada"
    assert "requests" not in src, "no debe hacer red"
    assert "import yaml" not in src, "no debe parsear YAML (eso es del 251)"


def test_f2_solo_declara_lo_que_falta():
    from services.pipeline_env_declare import plan_declaration

    req = _req("YA_DEFINIDA")
    matrix = _fake_matrix([req], [
        Cell(requirement="YA_DEFINIDA", environment="prod", state="definido",
             source="caja_fuerte", note=None),
    ])
    plan = plan_declaration(matrix, PROVIDER_ADO)
    assert plan.items == ()


def test_f2_salta_server_deploy_path_service_connection_parameter():
    from services.pipeline_env_declare import plan_declaration

    reqs = [
        _req("SERVIDOR", kind="server"),
        _req("RUTA", kind="deploy_path"),
        _req("CONEXION", kind="service_connection"),
        _req("PARAM", kind="parameter"),
    ]
    cells = [Cell(requirement=r.name, environment="prod", state="falta",
                  source="ninguna", note=None) for r in reqs]
    matrix = _fake_matrix(reqs, cells)
    plan = plan_declaration(matrix, PROVIDER_ADO)

    assert plan.items == ()
    skipped_by_key = dict(plan.skipped)
    for r in reqs:
        assert r.name in skipped_by_key, f"{r.name} no aparece en skipped"
        assert skipped_by_key[r.name], f"{r.name} sin motivo"


def test_f2_key_invalida_va_a_skipped():
    from services.pipeline_env_declare import plan_declaration

    req = _req("$(SONAR_TOKEN)", kind="service_connection")
    matrix = _fake_matrix([req], [
        Cell(requirement=req.name, environment="prod", state="falta",
             source="ninguna", note=None),
    ])
    plan = plan_declaration(matrix, PROVIDER_ADO)
    assert plan.items == ()
    assert req.name in dict(plan.skipped)


def test_f2_secret_se_conserva_en_ambos_proveedores():
    from services.pipeline_env_declare import plan_declaration

    req = _req("DB_PASSWORD", kind="secret", is_secret=True)
    matrix = _fake_matrix([req], [
        Cell(requirement=req.name, environment="prod", state="falta",
             source="ninguna", note=None),
    ])
    for provider in (PROVIDER_ADO, PROVIDER_GITLAB):
        plan = plan_declaration(matrix, provider)
        assert len(plan.items) == 1
        assert plan.items[0].secret is True, f"{provider}: secret debe conservarse True"


def test_f2_note_gitlab_avisa_del_masking():
    from services.pipeline_env_declare import plan_declaration

    req = _req("DB_PASSWORD", kind="secret", is_secret=True)
    matrix = _fake_matrix([req], [
        Cell(requirement=req.name, environment="prod", state="falta",
             source="ninguna", note=None),
    ])
    plan = plan_declaration(matrix, PROVIDER_GITLAB)
    assert "enmascar" in plan.items[0].note.lower() or "masking" in plan.items[0].note.lower()

    plan_ado = plan_declaration(matrix, PROVIDER_ADO)
    # ADO no tiene concepto de masking: la nota no debe inventar uno.
    assert "enmascar" not in (plan_ado.items[0].note or "").lower()


def test_f2_determinista():
    from services.pipeline_env_declare import plan_declaration

    reqs = [_req("B_VAR"), _req("A_VAR"), _req("C_VAR", kind="secret", is_secret=True)]
    cells = [Cell(requirement=r.name, environment="prod", state="falta",
                  source="ninguna", note=None) for r in reqs]
    matrix = _fake_matrix(reqs, cells)
    plan1 = plan_declaration(matrix, PROVIDER_ADO)
    plan2 = plan_declaration(matrix, PROVIDER_ADO)
    assert plan1 == plan2
    # orden determinista (por key)
    assert [i.key for i in plan1.items] == sorted(i.key for i in plan1.items)


def test_f2_ningun_placeholder():
    from pathlib import Path

    from services.pipeline_env_declare import plan_declaration

    req = _req("ALGO")
    matrix = _fake_matrix([req], [
        Cell(requirement=req.name, environment="prod", state="falta",
             source="ninguna", note=None),
    ])
    plan = plan_declaration(matrix, PROVIDER_ADO)
    for item in plan.items:
        assert not hasattr(item, "value")

    src = (Path(__file__).resolve().parent.parent / "services"
           / "pipeline_env_declare.py").read_text(encoding="utf-8")
    for placeholder in ("CHANGEME", "TODO", "xxx"):
        assert placeholder not in src, f"placeholder prohibido '{placeholder}' en el módulo"
