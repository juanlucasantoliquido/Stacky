"""Plan 249 F1 — catálogo de constructos GitLab CI codificado como DATO. 11 tests."""
from __future__ import annotations

import yaml

from services import pipeline_lint
from services.cicd_gitlab_catalog import (
    GITLAB_CATALOG_VERSION,
    KEYWORD_CATALOG,
    ROOT_KEYWORDS,
    SCOPE_JOB,
    WHEN_VALUES,
    get_keyword,
    hidden_job_names,
    is_deprecated,
    is_known_keyword,
    job_dicts,
    stage_index_map,
)

# El YAML de evidencia de §2.3: tres defectos que el lint de hoy aprueba.
GL_EVIDENCIA = """\
stages: [build, deploy]
.base:
  image: mvn:3
build:
  stage: build
  extends: .base
  needs: [deploy]
  script: [mvn package]
deploy:
  stage: deploy
  environment: production
  script: [./deploy.sh]
ghost:
  stage: nonexistent
  script: [echo hi]
"""


def _doc():
    return yaml.safe_load(GL_EVIDENCIA)


def test_root_keywords_coincide_con_lint_gitlab_reserved():
    """Impide que los dos conjuntos diverjan."""
    assert set(ROOT_KEYWORDS) == pipeline_lint._GITLAB_RESERVED


def test_catalogo_no_lanza_ante_desconocido():
    assert get_keyword("inventada", SCOPE_JOB) is None
    assert is_known_keyword("inventada", SCOPE_JOB) is False
    assert get_keyword("stage", "scope_inventado") is None


def test_when_values_es_enum_cerrado():
    assert get_keyword("when", SCOPE_JOB).allowed_values == WHEN_VALUES


def test_only_except_declaradas_deprecadas():
    assert is_deprecated("only") is True
    assert is_deprecated("except") is True
    assert get_keyword("only", SCOPE_JOB).deprecated_by == "rules"
    assert get_keyword("except", SCOPE_JOB).deprecated_by == "rules"


def test_environment_declara_su_gate():
    assert get_keyword("environment", SCOPE_JOB).requires_gate == "when"


def test_job_dicts_excluye_ocultos_y_reservadas():
    assert set(job_dicts(_doc())) == {"build", "deploy", "ghost"}


def test_hidden_job_names_encuentra_templates():
    assert hidden_job_names(_doc()) == (".base",)


def test_stage_index_map_incluye_implicitos():
    assert stage_index_map(_doc()) == {".pre": -1, "build": 0, "deploy": 1, ".post": 2}


def test_extraccion_por_safe_load_no_por_regex():
    """Test negativo del P4: un `needs` COMENTADO no existe."""
    texto = "stages: [build]\nbuild:\n  stage: build\n  # needs: [fantasma]\n  script: [ok]\n"
    jobs = job_dicts(yaml.safe_load(texto))
    assert "needs" in texto            # el grep SI lo ve
    assert "needs" not in jobs["build"]  # el arbol parseado NO


def test_version_del_catalogo_declarada():
    assert GITLAB_CATALOG_VERSION == "249.1"


def test_todo_keyword_tiene_evidence():
    for scope, tabla in KEYWORD_CATALOG.items():
        for nombre, spec in tabla.items():
            assert spec.evidence.strip(), (scope, nombre)
            assert spec.scope == scope
