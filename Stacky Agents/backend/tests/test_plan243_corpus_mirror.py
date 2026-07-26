"""Plan 243 F3.5 — espejo contra el corpus: "¿en qué se diferencia de uno que YA funciona?".

Comando (§7.1 del plan):
    .venv\\Scripts\\python.exe -m pytest tests/test_plan243_corpus_mirror.py -q

G1-G3 responden "¿está bien formado y no viola ninguna regla conocida?". Ninguno
responde la pregunta que de verdad se hace el operador frente a un draft generado:
"¿esto se parece a un pipeline que anda?". El caso típico no es un YAML roto: es uno
correcto al que le falta un paso.

Determinista, sin LLM, sin red. NUNCA bloquea: es info, no un gate.
"""
from __future__ import annotations

import io
import os

from services.cicd_corpus_mirror import (
    MIRROR_VERSION,
    SEVERITY,
    SpineDiff,
    nearest_golden,
    task_spine,
)
from services.cicd_task_catalog import PROFILE_DOTNET_FRAMEWORK as P
from services.pipeline_lint import SEV_INFO

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "cicd_nl", "golden")


def _golden(name: str) -> str:
    with io.open(os.path.join(GOLDEN_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _yaml_con(refs) -> str:
    """YAML mínimo con una espina de tareas dada."""
    pasos = "\n".join(
        "  - task: %s\n    inputs: {k: v}" % ref for ref in refs
    )
    return "pool:\n  vmImage: 'windows-2022'\nsteps:\n%s\n" % pasos


# ── 1. La espina es exacta y ordenada ─────────────────────────────────────────

def test_espina_exacta_de_ci_cd_online():
    assert task_spine(_golden("ci-cd-online.yml")) == (
        "NuGetToolInstaller@1",       # :70
        "NuGetCommand@2",             # :75
        "VSBuild@1",                  # :85
        "DotNetCoreCLI@2",            # :100
        "PublishTestResults@2",       # :112
        "PublishBuildArtifacts@1",    # :121
    )


# ── 2. El caso que ningún gate ve: falta un paso ──────────────────────────────

def test_draft_sin_publish_reporta_missing():
    draft = _yaml_con([
        "NuGetToolInstaller@1", "NuGetCommand@2", "VSBuild@1",
        "DotNetCoreCLI@2", "PublishTestResults@2", "PublishCodeCoverageResults@2",
    ])
    diff = nearest_golden(draft, profile=P)
    assert diff is not None
    assert diff.missing == ("PublishBuildArtifacts@1",)
    assert diff.extra == ()
    assert "PublishBuildArtifacts@1" in diff.hint
    assert diff.reference.endswith(".yml")


def test_draft_identico_a_un_golden_no_inventa_faltantes():
    """Si el draft calca un pipeline real, el espejo no tiene nada que señalar.

    Contracara honesta del test anterior: un build+test SIN publicar artefacto es
    exactamente pr-validation-online.yml, un pipeline real que hoy corre. Reportarle
    'te falta publicar' sería una falsa alarma.
    """
    diff = nearest_golden(_golden("pr-validation-online.yml"), profile=P)
    assert diff is not None
    assert diff.similarity == 1.0
    assert diff.missing == () and diff.extra == ()


# ── 3. Determinismo: el empate se resuelve alfabéticamente ────────────────────

def test_empate_resuelve_alfabetico():
    # agendaweb-ci.yml y nightly-build-online.yml tienen EXACTAMENTE el mismo conjunto
    # de refs, así que cualquier draft empata contra los dos.
    draft = _yaml_con(task_spine(_golden("agendaweb-ci.yml")))
    primero = nearest_golden(draft, profile=P)
    assert primero is not None
    assert primero.reference == "agendaweb-ci.yml"
    # 20 corridas, mismo resultado: sin azar ni orden de listdir.
    for _ in range(20):
        assert nearest_golden(draft, profile=P) == primero


# ── 4. Sin referencia razonable: silencio ─────────────────────────────────────

def test_sin_referencia_razonable_devuelve_none():
    otro_stack = _yaml_con(["Docker@2", "KubernetesManifest@1", "HelmDeploy@0"])
    assert nearest_golden(otro_stack, profile=P) is None
    # Sin tareas no hay nada que comparar.
    assert nearest_golden("steps: []\n", profile=P) is None
    assert nearest_golden("", profile=P) is None
    # Perfil sin corpus: tampoco inventa.
    assert nearest_golden(_golden("ci-cd-online.yml"), profile="perfil_inexistente") is None


# ── 5. Nunca es un gate ───────────────────────────────────────────────────────

def test_nunca_emite_severidad_error():
    assert SEVERITY == SEV_INFO
    entradas = [
        _golden(n) for n in sorted(os.listdir(GOLDEN_DIR))
    ] + [
        _yaml_con(["VSBuild@1"]),
        _yaml_con(["Docker@2"]),
        "esto: [no cierra\n",          # YAML inválido
        "",                            # vacío
        "- una lista suelta\n",        # ni siquiera es un mapping
    ]
    for texto in entradas:
        diff = nearest_golden(texto, profile=P)   # no lanza nunca
        assert diff is None or isinstance(diff, SpineDiff)
        if diff is not None:
            assert diff.severity == SEV_INFO
            assert 0.0 <= diff.similarity <= 1.0


# ── Contrato ──────────────────────────────────────────────────────────────────

def test_orden_cambiado_se_detecta_sin_marcar_faltantes():
    espina = list(task_spine(_golden("ci-cd-online.yml")))
    invertida = _yaml_con(list(reversed(espina)))
    diff = nearest_golden(invertida, profile=P)
    assert diff is not None
    assert diff.missing == () and diff.extra == ()
    assert diff.order_changed is True
    assert diff.similarity == 1.0


def test_version_declarada_y_yaml_invalido_no_lanza():
    assert MIRROR_VERSION == "243.1"
    assert nearest_golden("esto: [no cierra\n", profile=P) is None
