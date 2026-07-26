"""Plan 249 F2 — reglas semánticas de perfil GitLab GL000..GL011.

Nivel B del corpus (§2.5): un `repro` y un `contra_repro` por regla. Las dos tablas son el
gate de completitud: una regla sin cualquiera de los dos rompe un test.
"""
from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from services import pipeline_lint
from services.cicd_semantic_rules import (
    MODE_AUDIT,
    MODE_NL_STRICT,
    SEV_ERROR,
    _GL_NL_STRICT_ONLY,
    check_semantics,
)

BACKEND = Path(__file__).resolve().parent.parent
DERIVED = BACKEND / "tests" / "fixtures" / "cicd_gitlab" / "derived"
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"

# Inventario de runners fijo para que GL007 sea evaluable en los repros.
RUNNERS = ["docker"]

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

_SANO = "stages: [build]\nbuild:\n  stage: build\n  image: alpine\n  script: [make]\n"

GL_REPROS: dict = {
    "GL000": "esto: [no cierra\n",
    "GL001": "stages: [build]\nb:\n  stage: fantasma\n  image: alpine\n  script: [make]\n",
    "GL002": ("stages: [build, deploy]\n"
              "b:\n  stage: build\n  image: alpine\n  needs: [d]\n  script: [make]\n"
              "d:\n  stage: deploy\n  image: alpine\n  script: [ship]\n"),
    "GL003": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n"
              "  rules:\n  - if: '$CI_COMMIT_BRANCH == \"main\"'\n  only: [main]\n"
              "  script: [make]\n"),
    "GL004": "stages: [build]\nb:\n  stage: build\n  image: alpine\n  only: [main]\n  script: [make]\n",
    "GL005": ("stages: [deploy]\nd:\n  stage: deploy\n  image: alpine\n"
              "  environment: production\n  script: [ship]\n"),
    "GL006": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n"
              "  extends: .fantasma\n  script: [make]\n"),
    "GL007": "stages: [build]\nb:\n  stage: build\n  tags: [windows]\n  script: [make]\n",
    "GL008": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n  script: [make]\n"
              "  artifacts:\n    paths: [reportes/x.txt]\n"),
    "GL009": "stages: [build]\nb:\n  stage: build\n  script: [make]\n",
    "GL010": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n"
              "  inventada: 1\n  script: [make]\n"),
    "GL011": "stages: [build]\nb:\n  stage: build\n  image: alpine\n  script: [\"echo 'no-op'\"]\n",
}

GL_CONTRA_REPROS: dict = {
    "GL000": _SANO,
    "GL001": "stages: [build, fantasma]\nb:\n  stage: fantasma\n  image: alpine\n  script: [make]\n",
    "GL002": ("stages: [build, deploy]\n"
              "d:\n  stage: build\n  image: alpine\n  script: [prep]\n"
              "b:\n  stage: deploy\n  image: alpine\n  needs: [d]\n  script: [make]\n"),
    "GL003": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n"
              "  rules:\n  - if: '$CI_COMMIT_BRANCH == \"main\"'\n  script: [make]\n"),
    "GL004": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n"
              "  rules:\n  - if: '$CI_COMMIT_BRANCH == \"main\"'\n  script: [make]\n"),
    "GL005": ("stages: [deploy]\nd:\n  stage: deploy\n  image: alpine\n"
              "  environment: production\n  when: manual\n  script: [ship]\n"),
    "GL006": ("stages: [build]\n.base:\n  image: alpine\n"
              "b:\n  stage: build\n  image: alpine\n  extends: .base\n  script: [make]\n"),
    "GL007": "stages: [build]\nb:\n  stage: build\n  tags: [docker]\n  script: [make]\n",
    "GL008": ("stages: [build]\nb:\n  stage: build\n  image: alpine\n"
              "  script: [make reportes]\n  artifacts:\n    paths: [reportes/x.txt]\n"),
    "GL009": _SANO,
    "GL010": _SANO,
    "GL011": _SANO,
}


def _codes(texto: str, mode: str = MODE_NL_STRICT, runners=RUNNERS) -> set:
    return {f.code for f in check_semantics(
        texto, profile="", provider="gitlab", mode=mode, known_runner_tags=runners)}


# ── Nivel B: las dos mitades de la prueba ────────────────────────────────────

def test_repro_de_cada_regla_dispara_su_regla():
    """K7: 12/12. Una regla sin repro rompe el test."""
    assert set(GL_REPROS) == {"GL%03d" % n for n in range(12)}
    for code, texto in sorted(GL_REPROS.items()):
        assert code in _codes(texto), (code, sorted(_codes(texto)))


def test_todo_contra_repro_NO_dispara_su_regla():
    """K8: 12/12. Ley de no-vacuidad: la mitad que nadie prueba y es la que atrapa la
    regla que dispara sobre todo."""
    assert set(GL_CONTRA_REPROS) == set(GL_REPROS)
    for code, texto in sorted(GL_CONTRA_REPROS.items()):
        assert code not in _codes(texto), (code, sorted(_codes(texto)))


def test_ley_de_severidad_sobre_nivel_A():
    """K9: 0. Lo que Stacky emite no puede violar sus propias reglas duras."""
    for path in sorted(DERIVED.glob("*.yml")):
        findings = check_semantics(path.read_text(encoding="utf-8"), profile="",
                                   provider="gitlab", mode=MODE_AUDIT)
        errores = [f.code for f in findings if f.severity == SEV_ERROR]
        assert errores == [], (path.name, errores)


# ── Comportamiento de las reglas ─────────────────────────────────────────────

def test_yaml_de_evidencia_dispara_gl001_gl002_gl005():
    """K4: 3/3 sobre el YAML que el lint de hoy aprueba."""
    assert {"GL001", "GL002", "GL005"} <= _codes(GL_EVIDENCIA, mode=MODE_AUDIT)


def test_gl002_no_marca_needs_en_el_mismo_stage():
    texto = ("stages: [build]\n"
             "a:\n  stage: build\n  image: alpine\n  script: [x]\n"
             "b:\n  stage: build\n  image: alpine\n  needs: [a]\n  script: [y]\n")
    assert "GL002" not in _codes(texto)


def test_gl001_acepta_pre_y_post():
    texto = ("stages: [build]\n"
             "a:\n  stage: .pre\n  image: alpine\n  script: [x]\n"
             "b:\n  stage: .post\n  image: alpine\n  script: [y]\n")
    assert "GL001" not in _codes(texto)


def test_gl005_se_apaga_con_when_manual():
    assert "GL005" not in _codes(GL_CONTRA_REPROS["GL005"])
    con_rules = ("stages: [deploy]\nd:\n  stage: deploy\n  image: alpine\n"
                 "  environment: production\n"
                 "  rules:\n  - if: '$CI_COMMIT_BRANCH == \"main\"'\n    when: manual\n"
                 "  script: [ship]\n")
    assert "GL005" not in _codes(con_rules)


def test_gl006_se_omite_si_hay_include():
    texto = "include:\n- local: x.yml\n" + GL_EVIDENCIA
    assert "GL006" not in _codes(texto)


def test_gl007_no_evalua_sin_inventario():
    texto = GL_REPROS["GL007"]
    assert "GL007" not in _codes(texto, runners=None)
    assert "GL007" in _codes(texto, runners=["docker"])


def test_nl_strict_only_no_aparece_en_audit():
    for texto in list(GL_REPROS.values()) + [GL_EVIDENCIA]:
        codigos = _codes(texto, mode=MODE_AUDIT)
        assert not (codigos & set(_GL_NL_STRICT_ONLY)), sorted(codigos)


def test_gl000_usa_codigo_gitlab_no_rs000():
    roto = "esto: [no cierra\n"
    gigante = "a: 1\n" * 200000
    for texto in (roto, gigante):
        assert _codes(texto, mode=MODE_AUDIT) == {"GL000"}
        ado = {f.code for f in check_semantics(texto, profile="dotnet_framework")}
        assert ado == {"RS000"}


def test_gl011_detecta_el_derivado_vacio():
    """Une F0 con F2 sobre evidencia real: el artefacto PRE-F3 es el que GL011 caza."""
    pre_f3 = ("stages:\n- Build\nBuildJob:\n  stage: Build\n  script:\n  - echo 'no-op'\n")
    assert "GL011" in _codes(pre_f3)
    # Y el derivado POST-F3 ya no lo dispara: es la prueba de que F3 arreglo el defecto.
    actual = (DERIVED / "ci-cd-online.gitlab-ci.yml").read_text(encoding="utf-8")
    assert "GL011" not in _codes(actual)


def test_provider_invalido_lanza():
    with pytest.raises(ValueError):
        check_semantics("a: 1", profile="", provider="bitbucket")


def test_ado_sigue_identico_sin_provider():
    """P6: la firma vieja se comporta byte-identico."""
    for path in sorted(GOLDEN.glob("*.yml")):
        texto = path.read_text(encoding="utf-8")
        viejo = check_semantics(texto, profile="dotnet_framework")
        nuevo = check_semantics(texto, profile="dotnet_framework", provider="ado")
        assert viejo == nuevo, path.name
        assert all(f.code.startswith("RS") for f in viejo), path.name


def test_no_solapa_con_pl():
    for code in ("GL001", "GL002", "GL010", "GL011"):
        reporte = pipeline_lint.lint_yaml(GL_REPROS[code], "gitlab")
        errores = [f for f in reporte.findings if f.severity == SEV_ERROR]
        assert errores == [], (code, [f.code for f in errores])


def test_pureza_sin_red_ni_disco():
    """DoD 11b — se prueba que el codigo NO ABRE nada, no que el texto no diga `open`."""
    def _boom(*a, **k):
        raise AssertionError("el camino GitLab no puede tocar disco ni red")

    real_open = builtins.open
    fallos = []
    builtins.open = _boom
    try:
        for code, texto in sorted(GL_REPROS.items()):
            try:
                check_semantics(texto, profile="", provider="gitlab",
                                mode=MODE_NL_STRICT, known_runner_tags=RUNNERS)
            except Exception as exc:  # noqa: BLE001
                fallos.append((code, str(exc)))
    finally:
        builtins.open = real_open
    assert fallos == []
