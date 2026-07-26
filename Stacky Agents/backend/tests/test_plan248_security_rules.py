"""Plan 248 F1 — las 8 reglas SEC. 28 tests (16 positivo/negativo + 12 numerados)."""
from __future__ import annotations

from pathlib import Path

import pytest

from services.cicd_audit_core import AUDIT_RULES, MODE_AUDIT, SEV_ERROR
from services.cicd_security_rules import check_security

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"


def _codes(yaml_text: str, provider: str = "ado", mode: str = MODE_AUDIT) -> list:
    findings, _notes = check_security(yaml_text, provider=provider, mode=mode)
    return [f.code for f in findings]


def _repro(code: str) -> str:
    return AUDIT_RULES[code].repro[1]


def _golden(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


# ── SEC001 ────────────────────────────────────────────────────────────────────

def test_sec001_positivo_token_literal_en_arguments():
    assert "SEC001" in _codes(_repro("SEC001"))


def test_sec001_negativo_valor_corto_no_dispara():
    assert "SEC001" not in _codes(
        "steps:\n- task: PowerShell@2\n  inputs:\n    arguments: '-Token abc'\n")


# ── SEC002 ────────────────────────────────────────────────────────────────────

def test_sec002_positivo_write_host_con_ref_secreta():
    assert "SEC002" in _codes(_repro("SEC002"))


def test_sec002_negativo_echo_lo_cubre_pl014():
    """C5 — con `echo`, SEC002 NO emite: ese hecho ya es PL014."""
    assert "SEC002" not in _codes(
        "steps:\n- task: PowerShell@2\n  inputs:\n    script: 'echo $(API_TOKEN)'\n")


# ── SEC003 ────────────────────────────────────────────────────────────────────

def test_sec003_positivo_vmimage_latest():
    assert "SEC003" in _codes(_repro("SEC003"))


def test_sec003_negativo_vmimage_pineada():
    assert "SEC003" not in _codes(
        "pool:\n  vmImage: 'windows-2022'\nsteps:\n- script: echo hola\n")


# ── SEC004 ────────────────────────────────────────────────────────────────────

def test_sec004_positivo_persist_credentials_true():
    assert "SEC004" in _codes(_repro("SEC004"))


def test_sec004_negativo_checkout_sin_persist():
    assert "SEC004" not in _codes("steps:\n- checkout: self\n")


# ── SEC005 ────────────────────────────────────────────────────────────────────

def test_sec005_positivo_deploy_sin_parametrizar_con_publish():
    assert "SEC005" in _codes(_repro("SEC005"))


def test_sec005_negativo_sin_publish_no_dispara():
    assert "SEC005" not in _codes(
        "steps:\n- task: VSBuild@1\n  inputs:\n    msbuildArgs: "
        "'/p:DeployOnBuild=true /p:AutoParameterizationWebConfigConnectionStrings=false'\n")


# ── SEC006 ────────────────────────────────────────────────────────────────────

def test_sec006_positivo_continue_on_error_en_scan():
    assert "SEC006" in _codes(_repro("SEC006"))


def test_sec006_negativo_continue_on_error_en_paso_neutro():
    assert "SEC006" not in _codes(
        "steps:\n- task: CopyFiles@2\n  displayName: 'Copiar binarios'\n"
        "  continueOnError: true\n  inputs:\n    Contents: '**/*.dll'\n")


# ── SEC007 ────────────────────────────────────────────────────────────────────

def test_sec007_positivo_pr_activo_con_pool_selfhosted():
    assert "SEC007" in _codes(_repro("SEC007"))


def test_sec007_negativo_pr_none_con_pool_selfhosted():
    assert "SEC007" not in _codes(
        "pr: none\npool:\n  name: 'MI-SERVIDOR'\nsteps:\n- script: echo hola\n")


# ── SEC008 ────────────────────────────────────────────────────────────────────

def test_sec008_positivo_environment_produccion_literal():
    assert "SEC008" in _codes(_repro("SEC008"))


def test_sec008_negativo_environment_test():
    assert "SEC008" not in _codes(_repro("SEC008").replace("'Produccion'", "'Test'"))


# ── Los 3 tests anti-regex (§2.3) ─────────────────────────────────────────────

def test_environment_produccion_en_comentario_no_dispara_sec008():
    crudo = _golden("agendaweb-ci.yml")
    assert "Production" in crudo          # el grep SI da hits
    assert "SEC008" not in _codes(crudo)  # el arbol parseado NO


def test_connection_string_en_comentario_no_dispara_sec001():
    crudo = _golden("ci-dacpac.yml")
    assert "SQL_CONNECTION_STRING" in crudo
    assert "SEC001" not in _codes(crudo)


def test_task_machine_group_en_comentario_no_existe():
    from services.cicd_task_catalog import extract_task_dicts
    import yaml as _yaml

    doc = _yaml.safe_load(_golden("agendaweb-ci.yml"))
    refs = {str(t.get("task")) for t in extract_task_dicts(doc)}
    assert "IISWebAppDeploymentOnMachineGroup@0" in _golden("agendaweb-ci.yml")
    assert "IISWebAppDeploymentOnMachineGroup@0" not in refs


# ── Los hallazgos reales contra su fixture y su linea exacta ──────────────────

def test_sec003_dispara_en_ci_dacpac():
    findings, _ = check_security(_golden("ci-dacpac.yml"), provider="ado")
    sec003 = [f for f in findings if f.code == "SEC003"]
    assert len(sec003) == 1
    assert sec003[0].line == 38
    assert "ubuntu-latest" in sec003[0].evidence


def test_sec006_dispara_en_security_scan():
    findings, _ = check_security(_golden("security-scan-online.yml"), provider="ado")
    sec006 = [f for f in findings if f.code == "SEC006"]
    assert len(sec006) == 1
    assert sec006[0].line == 56


def test_sec005_dispara_una_vez_por_pipeline():
    for nombre in ("ci-cd-online.yml", "cd-deploy-test.yml", "agendaweb-ci.yml",
                   "nightly-build-online.yml"):
        findings, _ = check_security(_golden(nombre), provider="ado")
        assert len([f for f in findings if f.code == "SEC005"]) == 1, nombre


def test_sec007_no_dispara_en_el_corpus():
    for path in sorted(GOLDEN.glob("*.yml")):
        findings, _ = check_security(path.read_text(encoding="utf-8"), provider="ado")
        assert not [f for f in findings if f.code == "SEC007"], path.name


def test_sec008_se_abstiene_con_environment_dinamico():
    findings, notes = check_security(
        _golden("bootstrap-server-environment.yml"), provider="ado")
    assert not [f for f in findings if f.code == "SEC008"]
    assert len([n for n in notes if n.startswith("SEC008")]) == 1


def test_mode_invalido_lanza_valueerror():
    with pytest.raises(ValueError):
        check_security("a: 1", provider="ado", mode="modo_inventado")


def test_sec006_matchea_display_name_con_acento_y_mayuscula():
    """C12 — sin `.lower()` la regla da 0 hits y queda inerte."""
    findings, _ = check_security(_golden("security-scan-online.yml"), provider="ado")
    assert len([f for f in findings if f.code == "SEC006"]) == 1


def test_sec006_no_matchea_latest_como_test():
    """C12 — `test` es PALABRA, no substring: `latest` no debe matchear."""
    assert "SEC006" not in _codes(
        "steps:\n- task: Docker@2\n  displayName: 'Publicar imagen latest'\n"
        "  continueOnError: true\n")


def test_sec005_line_y_location_apuntan_al_mismo_publish():
    """C11 — cd-deploy-test.yml tiene 4 PublishBuildArtifacts@1."""
    crudo = _golden("cd-deploy-test.yml")
    assert crudo.count("PublishBuildArtifacts@1") == 4
    findings, _ = check_security(crudo, provider="ado")
    sec005 = [f for f in findings if f.code == "SEC005"][0]
    assert sec005.line == 99
    assert sec005.location.startswith("stages[0].")


def test_sec_en_nl_strict_sube_la_severidad_declarada():
    from services.cicd_audit_core import MODE_NL_STRICT

    findings, _ = check_security(_repro("SEC003"), provider="ado", mode=MODE_NL_STRICT)
    sec003 = [f for f in findings if f.code == "SEC003"]
    assert sec003 and sec003[0].severity == SEV_ERROR
