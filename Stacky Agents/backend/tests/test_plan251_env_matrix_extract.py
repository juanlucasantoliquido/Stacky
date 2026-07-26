"""Plan 251 F1 — nucleo PURO de deteccion. 17 tests sobre el corpus dorado REAL.

El riesgo nº1 de este plan no es fallar: es producir RUIDO. 40 filas basura matan el
KPI-2 y el operador deja de mirar la matriz para siempre.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from services import pipeline_environments as pe
from services.secret_masking import MASK_PLACEHOLDER

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
ADO = pe.PROVIDER_ADO


def _leer(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


def _por_kind(reqs, kind):
    return [r for r in reqs if r.kind == kind]


def _nombres(reqs):
    return {r.name for r in reqs}


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f1_bootstrap_detecta_los_8_parametros():
    reqs = pe.extract_requirements(_leer("bootstrap-server-environment.yml"), ADO)
    params = _por_kind(reqs, "parameter")
    assert len(params) == 8
    assert _nombres(params) == {
        "targetEnvironment", "agentPool", "component", "skipIis",
        "iisPort", "iisHostHeader", "seedConfigs", "whatIf"}


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f1_bootstrap_iisport_default_cero():
    reqs = pe.extract_requirements(_leer("bootstrap-server-environment.yml"), ADO)
    port = next(r for r in reqs if r.name == "iisPort" and r.kind == "parameter")
    assert port.declared_default == "0"
    juntos = " ".join(e.excerpt for e in port.evidence)
    assert "confirmar con infraestructura" in juntos


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f1_bootstrap_servidor_desde_parametro():
    """C13 — el pool sale del DEFAULT de un parametro: es una SUPOSICION y se declara."""
    reqs = pe.extract_requirements(_leer("bootstrap-server-environment.yml"), ADO)
    srv = next(r for r in reqs if r.kind == "server")
    assert srv.name == "TEST-Server"
    assert len(srv.evidence) >= 2, "la del pool y la del parametro"
    assert "default" in srv.note
    assert "agentPool" in srv.note


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f1_bootstrap_compile_time_vars_no_faltan():
    """skipIisArg/seedConfigsArg/whatIfArg estan DECLARADAS dentro de un `${{ if }}`."""
    reqs = pe.extract_requirements(_leer("bootstrap-server-environment.yml"), ADO)
    for nombre in ("skipIisArg", "seedConfigsArg", "whatIfArg"):
        r = next((x for x in reqs if x.name == nombre), None)
        assert r is not None, nombre
        assert r.declared_default is not None, "esta declarada, no falta"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_f1_cd_deploy_variables_declaradas_no_se_piden():
    reqs = pe.extract_requirements(_leer("cd-deploy-test.yml"), ADO)
    for nombre in ("buildConfiguration", "buildPlatform"):
        r = next(x for x in reqs if x.name == nombre)
        assert r.declared_default is not None


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f1_cd_deploy_pool_literal():
    reqs = pe.extract_requirements(_leer("cd-deploy-test.yml"), ADO)
    srv = next(r for r in reqs if r.kind == "server")
    assert srv.name == "TEST-Server"
    assert srv.confidence == "alta"


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f1_cd_deploy_rutas_absolutas():
    """C2 — vienen EMBEBIDAS en el displayName, no son el string entero: confianza
    baja SIEMPRE, y por eso terminan en `manual`, nunca en `falta`."""
    reqs = pe.extract_requirements(_leer("cd-deploy-test.yml"), ADO)
    rutas = {r.name: r for r in _por_kind(reqs, "deploy_path")}
    assert "C:\\AIS\\AgendaWeb\\Web" in rutas
    assert "C:\\AIS\\Procesos\\Exes" in rutas
    for r in rutas.values():
        assert r.per_environment is True
        assert r.confidence == "baja"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f1_powershell_no_es_variable_de_pipeline():
    reqs = pe.extract_requirements(_leer("cd-deploy-test.yml"), ADO)
    for basura in ("slns", "s", "LASTEXITCODE"):
        assert basura not in _nombres(reqs)


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f1_predefinidas_de_ado_nunca_se_piden():
    reqs = pe.extract_requirements(_leer("nightly-build-online.yml"), ADO)
    for pred in ("Agent.JobStatus", "Build.BuildNumber",
                 "Build.ArtifactStagingDirectory", "Agent.TempDirectory"):
        assert pred not in _nombres(reqs)


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f1_secreto_por_nombre():
    """Red B: el nombre delata el secreto."""
    yml = ("variables:\n  DB_PASSWORD: 'p4ss'\nsteps:\n"
           "- script: echo hola\n- task: VSBuild@1\n  inputs:\n"
           "    solution: '$(DB_PASSWORD)'\n")
    reqs = pe.extract_requirements(yml, ADO)
    r = next(x for x in reqs if x.name == "DB_PASSWORD")
    assert r.is_secret is True
    assert r.kind == "secret"
    assert r.declared_default == MASK_PLACEHOLDER
    assert "p4ss" not in repr(reqs)


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f1_valor_token_nombre_inocente():
    """C5 — el hueco de seguridad REAL: `looks_secret` no matchea el nombre, asi que
    solo la red A (incondicional) lo salva."""
    yml = ("variables:\n  SONAR_HOST: 'glpat-AAAAAAAAAAAAAAAAAAAA'\n"
           "steps:\n- task: VSBuild@1\n  inputs:\n    solution: '$(SONAR_HOST)'\n")
    reqs = pe.extract_requirements(yml, ADO)
    r = next(x for x in reqs if x.name == "SONAR_HOST")
    assert r.is_secret is False, "por NOMBRE no es secreto"
    assert r.declared_default == MASK_PLACEHOLDER
    assert "glpat-AAAAAAAAAAAAAAAAAAAA" not in repr(reqs)


def test_f1_password_arbitrario_bajo_nombre_inocente_tampoco_sale():
    """ADVERSARIAL — el caso que NINGUNA de las dos redes del plan cubre.

    `mask_token_values` conoce 7 PREFIJOS (secret_masking.py:11) y `looks_secret`
    decide por NOMBRE: un password que no es un token conocido, bajo un nombre que no
    suena a secreto, salia VERBATIM. Lo cierra la red A' (forma generica) de este plan.
    """
    yml = ("variables:\n  SONAR_HOST: 'Xk7#pQ2mZr9Lw4Tv'\n"
           "steps:\n- task: VSBuild@1\n  inputs:\n    solution: '$(SONAR_HOST)'\n")
    reqs = pe.extract_requirements(yml, ADO)
    r = next(x for x in reqs if x.name == "SONAR_HOST")
    assert r.declared_default == MASK_PLACEHOLDER
    assert "Xk7#pQ2mZr9Lw4Tv" not in repr(reqs)


def test_f1_la_red_de_forma_no_tapa_valores_legitimos():
    """CONTROL NEGATIVO de la red A': si tapara valores normales seria peor que el
    problema. Ninguno de estos se enmascara."""
    legitimos = ("Release", "Any CPU", "windows-2022", "AgendaWeb-drop",
                 "trunk/OnLine/Soluciones/AgendaWeb.sln", "us-east-1",
                 "$(Build.ArtifactStagingDirectory)", "C:\\AIS\\AgendaWeb\\Web",
                 "succeededOrFailed()", "6.x", "High")
    for v in legitimos:
        assert pe.looks_like_credential_value(v) is False, v
    for v in ("Xk7#pQ2mZr9Lw4Tv", "aB3dEf6hIj9kLm2nOp5q"):
        assert pe.looks_like_credential_value(v) is True, v


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f1_declared_default_de_variable_no_secreta():
    yml = ("variables:\n  REGION: 'us-east'\nsteps:\n- task: VSBuild@1\n"
           "  inputs:\n    solution: '$(REGION)'\n")
    reqs = pe.extract_requirements(yml, ADO)
    r = next(x for x in reqs if x.name == "REGION")
    assert r.declared_default == "us-east"
    assert r.is_secret is False


# ── 13 ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("archivo", sorted(p.name for p in GOLDEN.glob("*.yml")))
def test_f1_corpus_dorado_sin_ruido(archivo):
    """KPI-6 — los 9 YAML reales, no los 3 que se abrieron a mano."""
    reqs = pe.extract_requirements(_leer(archivo), ADO)
    assert len(reqs) <= 40, "%s produce %d requirements: es ruido" % (archivo, len(reqs))
    for r in reqs:
        assert r.name, archivo
        assert r.name.strip() == r.name, (archivo, r.name)
        assert " " not in r.name, (archivo, r.name)
        assert not r.name.startswith("$"), (archivo, r.name)
        assert pe.is_ado_predefined(r.name) is False, (archivo, r.name)
        assert r.kind in pe.VALUE_KINDS, (archivo, r.kind)
        assert r.confidence in pe.CONFIDENCE, (archivo, r.confidence)


def test_f1_corpus_dorado_no_inventa_rutas_de_msbuild():
    """REGRESION MEDIDA: con la regex de una sola rama, `msbuildArgs: >-` metia
    `/p:WebPublishMethod=Package` y 4 hermanos como "rutas de despliegue" en 4 de los
    9 goldens. 5 filas basura por archivo."""
    for archivo in sorted(p.name for p in GOLDEN.glob("*.yml")):
        for r in pe.extract_requirements(_leer(archivo), ADO):
            if r.kind == "deploy_path":
                assert not r.name.startswith("/p:"), (archivo, r.name)


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_f1_service_connection_ado():
    yml = ("steps:\n- task: AzureWebApp@1\n  inputs:\n"
           "    azureSubscription: 'MiSub'\n")
    reqs = pe.extract_requirements(yml, ADO)
    sc = _por_kind(reqs, "service_connection")
    assert [r.name for r in sc] == ["MiSub"]


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_f1_determinista():
    texto = _leer("bootstrap-server-environment.yml")
    a = pe.extract_requirements(texto, ADO)
    b = pe.extract_requirements(texto, ADO)
    c = pe.extract_requirements(texto, ADO)
    assert a == b == c


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_f1_yaml_invalido_devuelve_vacio():
    assert pe.extract_requirements("a: [", ADO) == ()
    assert pe.extract_requirements("", ADO) == ()
    assert pe.extract_requirements("- solo una lista", ADO) == ()
    assert pe.extract_requirements("a: 1", "proveedor_raro") == ()


# ── 17 ───────────────────────────────────────────────────────────────────────
def test_f1_modulo_puro():
    """El gate va con `\\bprint\\(`, NUNCA con `print(` a secas.

    El plan corrigio ese gotcha para `Blueprint(` en F3/F4 (C1) y se olvido de aplicarlo
    aca: su propia funcion `pending_fingerprint(` contiene literalmente la subcadena
    `print(`, asi que el criterio de F1 era imposible por construccion.
    """
    import re as _re

    fuente = (BACKEND / "services" / "pipeline_environments.py").read_text(encoding="utf-8")
    for prohibido in ("import flask", "from flask", "import requests", "from requests",
                      "invoke_local_llm"):
        assert prohibido not in fuente, prohibido
    assert _re.search(r"\blogger\.", fuente) is None
    assert _re.search(r"\bprint\(", fuente) is None
    assert _re.search(r"\bprint\(", "pending_fingerprint(cells)") is None, \
        "el gate no puede matchear su propio simbolo"
    # y NO greppea el texto crudo: camina el documento parseado
    for prohibido in ("yaml_text.find", "yaml_text.split"):
        assert prohibido not in fuente, prohibido


def test_f1_gitlab_tags_son_servidores():
    yml = ("stages: [build]\nbuild:\n  stage: build\n  tags: ['docker', 'linux']\n"
           "  script:\n    - echo $MI_VAR\n")
    reqs = pe.extract_requirements(yml, pe.PROVIDER_GITLAB)
    assert {r.name for r in _por_kind(reqs, "server")} == {"docker", "linux"}
    assert "CI_COMMIT_SHA" not in _nombres(reqs)
