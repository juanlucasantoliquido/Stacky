"""tests/test_plan294_intent.py — Plan 294 F3.

El contrato `PipelineIntent`: el objeto declarativo que el asistente llena y que
se traduce a lo que el generador (plan 73) ya sabe leer. El asistente NO
renderiza YAML: `intent_to_spec` es el UNICO puente.

R3 es el riel duro de este archivo: `variables` y `required_secrets` llevan
NOMBRES, jamas valores. Un elemento con "=" o ":" es exactamente la forma en que
un valor se cuela en una lista de nombres, y `intent_to_dict` lo rechaza.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


def _intent_base(**over):
    from services.pipeline_intent import PipelineIntent

    campos = dict(
        project="RecoveryStrategy",
        repository="RecoveryStrategy",
        provider="ado",
        default_branch="main",
        stack="dotnet",
        goal="ejecutar_tests",
        pipeline_kind="ci",
        triggers=("main",),
        stages=("test",),
        build_command="dotnet build",
        test_command="dotnet test",
        runtime="claude_code_cli",
    )
    campos.update(over)
    return PipelineIntent(**campos)


def test_round_trip_exacto():
    from services.pipeline_intent import intent_from_dict, intent_to_dict

    i = _intent_base()
    assert intent_from_dict(intent_to_dict(i)) == i


def test_campo_desconocido_se_ignora():
    from services.pipeline_intent import intent_from_dict, intent_to_dict

    d = intent_to_dict(_intent_base())
    d["campo_que_no_existe"] = "cualquier cosa"
    assert intent_from_dict(d) == _intent_base()


def test_r3_una_variable_con_igual_es_un_valor_colado():
    from services.pipeline_intent import intent_to_dict

    with pytest.raises(ValueError):
        intent_to_dict(_intent_base(variables=("API_KEY=secreto",)))


def test_r3_un_secreto_con_dos_puntos_es_un_valor_colado():
    from services.pipeline_intent import intent_to_dict

    with pytest.raises(ValueError):
        intent_to_dict(_intent_base(required_secrets=("TOKEN: abc",)))


def test_intent_to_spec_produce_un_spec_valido_en_los_tres_stacks():
    from services.pipeline_intent import intent_to_spec
    from services.pipeline_spec import dict_to_spec

    for stack, build, test in (
        ("python", "pip install -r requirements.txt", "pytest"),
        ("node", "npm run build", "npm test"),
        ("dotnet", "dotnet build", "dotnet test"),
    ):
        i = _intent_base(
            stack=stack, goal="ci_completo", pipeline_kind="ci",
            stages=("build", "test"), build_command=build, test_command=test,
        )
        spec = dict_to_spec(intent_to_spec(i))
        assert spec.validate() == [], f"{stack}: {spec.validate()}"


def test_proposed_path_sale_de_pipeline_filename():
    from services.pipeline_intent import intent_to_dict
    from services.pipeline_session import PIPELINE_FILENAME

    ado = intent_to_dict(_intent_base(provider="ado"))
    gitlab = intent_to_dict(_intent_base(provider="gitlab"))
    assert ado["proposed_path"] == PIPELINE_FILENAME["ado"] == "azure-pipelines.yml"
    assert gitlab["proposed_path"] == PIPELINE_FILENAME["gitlab"] == ".gitlab-ci.yml"


def test_validate_intent_exige_objetivo():
    from services.pipeline_intent import validate_intent

    motivos = validate_intent(_intent_base(goal=""))
    assert motivos and all(m.strip() for m in motivos)


def test_modificar_existente_exige_la_clave_del_inventario():
    from services.pipeline_intent import validate_intent

    motivos = validate_intent(
        _intent_base(goal="modificar_existente", existing_pipeline_key="")
    )
    assert motivos, "modificar_existente sin clave del inventario deberia dar motivo"


def test_el_modulo_no_toca_red_ni_modelo():
    fuente = (_BACKEND / "services" / "pipeline_intent.py").read_text(encoding="utf-8")
    for prohibida in ("requests", "urllib", "ado_client", "gitlab_client"):
        assert prohibida not in fuente, f"pipeline_intent.py menciona {prohibida}"


def test_c12_el_puente_de_variables_es_un_dict_con_valores_vacios():
    """PipelineSpec.variables es un dict; PipelineIntent.variables es una tupla de
    NOMBRES. La cadena vacia es a proposito: el nombre viaja al archivo, el valor
    NUNCA. `required_secrets` no entra al spec: viaja aparte, solo para el aviso
    'te falta cargar X' del paso de revision."""
    from services.pipeline_intent import intent_to_spec

    i = _intent_base(
        variables=("NUGET_FEED", "SIGNING_KEY"), required_secrets=("SIGNING_KEY",)
    )
    spec = intent_to_spec(i)
    assert spec["variables"] == {"NUGET_FEED": "", "SIGNING_KEY": ""}
    assert isinstance(spec["variables"], dict)
    assert "required_secrets" not in spec


def test_c4_el_vocabulario_de_runtime_son_los_tres_ids_reales():
    from services.pipeline_intent import WIZARD_RUNTIME_IDS, validate_intent

    assert WIZARD_RUNTIME_IDS == ("claude_code_cli", "codex_cli", "github_copilot")

    inventado = validate_intent(_intent_base(runtime="claude"))
    assert any("runtime" in m or "asistente" in m.lower() for m in inventado), inventado

    real = validate_intent(_intent_base(runtime="claude_code_cli"))
    assert not any("runtime" in m for m in real), real
