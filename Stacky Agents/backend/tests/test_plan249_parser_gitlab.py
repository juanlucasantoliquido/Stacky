"""Plan 249 F4 — el parser deja de corromper y el round-trip se cierra sobre un subset
ENUMERADO (no prometido). K5, K6."""
from __future__ import annotations

from pathlib import Path

from services.pipeline_renderers import (
    GITLAB_ROUNDTRIP_SUBSET,
    GITLAB_UNSUPPORTED_CONSTRUCTS,
    parse_gitlab_yaml,
    scan_unsupported,
    to_gitlab_yaml,
)

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
DERIVED = BACKEND / "tests" / "fixtures" / "cicd_gitlab" / "derived"

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


def _cuerpo(path: Path) -> str:
    """El YAML sin el header de procedencia (que es un comentario, no parte del contrato)."""
    lineas = [ln for ln in path.read_text(encoding="utf-8").splitlines()
              if not ln.startswith("#")]
    return "\n".join(lineas) + "\n"


def test_k5_job_oculto_no_se_promueve():
    """K5: 0. `.base` es un TEMPLATE: GitLab nunca lo ejecuta."""
    spec = parse_gitlab_yaml(GL_EVIDENCIA)
    nombres = [jb.name for st in spec.stages for jb in st.jobs]
    nombres += [dp.name for st in spec.stages for dp in st.deployments]
    assert ".base" not in nombres
    assert "" not in [st.name for st in spec.stages]


def test_k6_extends_no_es_unsupported_en_gitlab():
    """K6: 0. En GitLab `extends` es keyword de primera clase."""
    assert "extends" not in scan_unsupported(GL_EVIDENCIA, provider="gitlab")


def test_scan_unsupported_ado_sin_cambios():
    """P6 — llamarla como hoy da el resultado de hoy."""
    esperado = {
        "ci-batch.yml": ("matrix",),
        "bootstrap-server-environment.yml": ("compile_time_expression",),
    }
    for path in sorted(GOLDEN.glob("*.yml")):
        texto = path.read_text(encoding="utf-8")
        sin_kwarg = scan_unsupported(texto)
        assert sin_kwarg == scan_unsupported(texto, provider="ado")
        assert sin_kwarg == esperado.get(path.name, ()), path.name


def test_scan_unsupported_gitlab_declara_include():
    texto = "include:\n- local: x.yml\nstages: [build]\nb:\n  stage: build\n  script: [make]\n"
    assert scan_unsupported(texto, provider="gitlab") == ("include",)


def test_needs_se_recupera_al_spec():
    texto = ("stages: [build]\n"
             "a:\n  stage: build\n  script: [x]\n"
             "b:\n  stage: build\n  needs: [a]\n  script: [y]\n")
    spec = parse_gitlab_yaml(texto)
    por_nombre = {jb.name: jb for st in spec.stages for jb in st.jobs}
    assert por_nombre["b"].depends_on == ("a",)


def test_environment_se_recupera_al_spec():
    texto = ("stages: [deploy]\nd:\n  stage: deploy\n  environment: staging\n  script: [ship]\n")
    spec = parse_gitlab_yaml(texto)
    deployments = [dp for st in spec.stages for dp in st.deployments]
    assert len(deployments) == 1
    assert deployments[0].environment == "staging"


def test_roundtrip_idempotente_sobre_nivel_A():
    """Conjunto FINITO y NOMBRADO: los 9 derivados post-F3."""
    for path in sorted(DERIVED.glob("*.yml")):
        cuerpo = _cuerpo(path)
        assert to_gitlab_yaml(parse_gitlab_yaml(cuerpo)) == cuerpo, path.name


def test_roundtrip_idempotente_sobre_nivel_B():
    """Los repros que sólo usan keywords del subset. Los de afuera se excluyen POR LISTA."""
    from tests.test_plan249_reglas_gitlab import GL_REPROS

    fuera_del_subset = {"GL000", "GL003", "GL004", "GL006", "GL008", "GL010"}
    probados = 0
    for code, texto in sorted(GL_REPROS.items()):
        if code in fuera_del_subset:
            continue
        rt = to_gitlab_yaml(parse_gitlab_yaml(texto))
        assert to_gitlab_yaml(parse_gitlab_yaml(rt)) == rt, code
        probados += 1
    assert probados == len(GL_REPROS) - len(fuera_del_subset)


def test_subset_de_roundtrip_es_cerrado():
    assert GITLAB_ROUNDTRIP_SUBSET == {
        "root": ("stages", "variables"),
        "job": ("stage", "script", "image", "tags", "variables", "services",
                "artifacts.paths", "needs", "rules.if", "when", "environment"),
    }
    unicas = set(GITLAB_ROUNDTRIP_SUBSET["root"]) | set(GITLAB_ROUNDTRIP_SUBSET["job"])
    assert len(unicas) == 12


def test_unsupported_gitlab_no_crece_en_silencio():
    assert GITLAB_UNSUPPORTED_CONSTRUCTS == (
        "include", "workflow", "default", "parallel", "trigger", "pages",
        "cache", "before_script", "after_script", "secrets", "id_tokens", "release",
    )
    assert len(GITLAB_UNSUPPORTED_CONSTRUCTS) == 12
