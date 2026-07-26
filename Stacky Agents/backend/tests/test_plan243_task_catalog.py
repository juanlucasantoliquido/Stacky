"""Plan 243 F0 — catálogo de tareas ADO por perfil + corpus dorado.

Comando (§7.1 del plan):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan243_task_catalog.py -q

Regla dura del plan (C20): la extracción del catálogo es SIEMPRE por yaml.safe_load,
NUNCA por grep/regex. Un regex sobre los 9 golden devuelve 12 refs porque dos viven
dentro de comentarios — y una de esas dos es IISWebAppDeploymentOnMachineGroup@0,
la causa raíz de ADO-369, justo la que RS002 existe para prohibir.
"""
from __future__ import annotations

import io
import os
import re

import pytest
import yaml

from services.cicd_task_catalog import (
    CATALOG_VERSION,
    PROFILE_DOTNET_FRAMEWORK as P,
    TASK_CATALOG,
    extract_task_dicts,
    extract_task_refs,
    get_task,
    is_allowed,
    validate_inputs,
)

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "cicd_nl", "golden")
SOURCE_DIR = r"N:\GIT\RS\RSPACIFICO\pipelines"

GOLDEN_FILES = (
    "agendaweb-ci.yml",
    "bootstrap-server-environment.yml",
    "cd-deploy-test.yml",
    "ci-batch.yml",
    "ci-cd-online.yml",
    "ci-dacpac.yml",
    "nightly-build-online.yml",
    "pr-validation-online.yml",
    "security-scan-online.yml",
)

PROVENANCE_PREFIX = "# fuente: RSPACIFICO/pipelines/"


def _read_golden(name: str) -> str:
    with io.open(os.path.join(GOLDEN_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _corpus_task_dicts():
    """Todos los dicts `task:` VIVOS del corpus, por yaml.safe_load. Nunca regex."""
    out = []
    for name in GOLDEN_FILES:
        doc = yaml.safe_load(_read_golden(name))
        out.extend(extract_task_dicts(doc))
    return out


# ── 1. El catálogo cubre el corpus (impide que se pudra) ──────────────────────

def test_catalogo_cubre_todas_las_tareas_del_corpus():
    refs = {t["task"] for t in _corpus_task_dicts()}
    # Criterio binario del plan: exactamente 10 refs distintas VIVAS.
    assert len(refs) == 10, "refs vivas encontradas: %s" % sorted(refs)
    faltantes = sorted(r for r in refs if not is_allowed(P, r))
    assert faltantes == [], "tareas del corpus fuera del catálogo: %s" % faltantes
    assert len(TASK_CATALOG[P]) == 10


# ── 2. La trampa del regex (C20) ──────────────────────────────────────────────

def test_tareas_comentadas_no_entran_al_catalogo():
    # Viven en comentarios: agendaweb-ci.yml:142 y ci-dacpac.yml:102.
    assert is_allowed(P, "IISWebAppDeploymentOnMachineGroup@0") is False
    assert is_allowed(P, "SqlAzureDacpacDeployment@1") is False


# ── 3. Los inputs reales del corpus son aceptados ─────────────────────────────

def test_inputs_del_corpus_son_aceptados():
    problemas = []
    for t in _corpus_task_dicts():
        errores = validate_inputs(P, t["task"], dict(t.get("inputs") or {}))
        if errores:
            problemas.append((t["task"], errores))
    assert problemas == [], "el catálogo rechaza inputs reales: %s" % problemas


# ── 4. Alucinaciones típicas rechazadas (C5) ──────────────────────────────────

def test_tarea_desconocida_rechazada():
    assert is_allowed(P, "MSBuild@1") is False
    assert is_allowed(P, "VSBuild@2") is False
    # el input real es msbuildArgs, no msbuildArguments
    errores = validate_inputs(P, "VSBuild@1", {"solution": "x.sln", "platform": "Any CPU",
                                               "configuration": "Release",
                                               "msbuildArguments": "/p:X=1"})
    assert any("msbuildArguments" in e for e in errores)


# ── 5. Toda evidencia es un anclaje archivo:línea real ────────────────────────

def test_evidence_formato_archivo_linea():
    for ref, spec in TASK_CATALOG[P].items():
        assert re.match(r"^.+:\d+$", spec.evidence), "%s -> %r" % (ref, spec.evidence)


# ── 6. Perfil desconocido: nunca excepción ────────────────────────────────────

def test_perfil_desconocido_no_lanza():
    assert get_task("perfil_inexistente", "VSBuild@1") is None
    assert is_allowed("perfil_inexistente", "VSBuild@1") is False
    assert validate_inputs("perfil_inexistente", "VSBuild@1", {}) != []


# ── 7. Procedencia del corpus vendorizado (C22) ───────────────────────────────

def test_golden_tiene_header_de_procedencia():
    for name in GOLDEN_FILES:
        primera = _read_golden(name).splitlines()[0]
        assert primera.startswith(PROVENANCE_PREFIX), "%s -> %r" % (name, primera)
        assert name in primera


# ── 8. Guardia de deriva contra el original (C22) ─────────────────────────────

def test_corpus_dorado_no_derivo():
    if not os.path.isdir(SOURCE_DIR):
        pytest.skip("fuente %s no disponible en esta máquina" % SOURCE_DIR)
    derivados = []
    for name in GOLDEN_FILES:
        with io.open(os.path.join(SOURCE_DIR, name), "r", encoding="utf-8") as fh:
            original = fh.read()
        copia = _read_golden(name).split("\n", 1)[1]  # sin el header de procedencia
        if copia.replace("\r\n", "\n") != original.replace("\r\n", "\n"):
            derivados.append(name)
    assert derivados == [], "el corpus vendorizado derivó del original: %s" % derivados


# ── Extra: contrato del módulo ────────────────────────────────────────────────

def test_version_del_catalogo_declarada():
    assert CATALOG_VERSION == "243.1"
    assert extract_task_refs(_read_golden("ci-cd-online.yml")) == (
        "NuGetToolInstaller@1", "NuGetCommand@2", "VSBuild@1",
        "DotNetCoreCLI@2", "PublishTestResults@2", "PublishBuildArtifacts@1",
    )
