"""tests/test_plan186_lint_variables.py — Plan 186 F2.

Reglas de variables y secretos PL010..PL014 (walk C4 sobre el árbol parseado).
PL012(b) usa el criterio CANÓNICO de services.secret_masking (prefijo + >=8).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.pipeline_lint import lint_yaml  # noqa: E402


def _codes(rep):
    return [f.code for f in rep.findings]


# ── PL010 — variable referenciada sin declarar ────────────────────────────────

def test_pl010_ref_sin_declarar_ado():
    y = (
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo $(FANTASMA)\n"
    )
    assert "PL010" in _codes(lint_yaml(y, "ado"))


def test_pl010_ref_sin_declarar_gitlab():
    y = "stages:\n- build\nj:\n  stage: build\n  script:\n  - echo $FANTASMA\n"
    assert "PL010" in _codes(lint_yaml(y, "gitlab"))


def test_pl010_respeta_whitelist_ci_predefinidas():
    y = (
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo $(Build.BuildId)\n"
    )
    assert "PL010" not in _codes(lint_yaml(y, "ado"))


def test_pl010_respeta_known_variables():
    y = (
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo $(MY_VAR)\n"
    )
    assert "PL010" not in _codes(lint_yaml(y, "ado", known_variables=["MY_VAR"]))


def test_pl010_comentario_no_genera_ref():
    # C4: el walk es sobre el árbol parseado; los comentarios NO generan refs.
    y = (
        "# usa $(FANTASMA)\n"
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo hola\n"
    )
    assert "PL010" not in _codes(lint_yaml(y, "ado"))


# ── PL011 — variable declarada nunca usada ────────────────────────────────────

def test_pl011_declarada_sin_uso_info():
    y = (
        "variables:\n  UNUSED: hola\n"
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo hi\n"
    )
    assert "PL011" in _codes(lint_yaml(y, "ado"))


# ── PL012 — posible secreto hardcodeado ───────────────────────────────────────

def test_pl012_secreto_por_nombre():
    y = (
        "variables:\n  DEPLOY_TOKEN: " + ("x" * 16) + "\n"
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo hi\n"
    )
    assert "PL012" in _codes(lint_yaml(y, "ado"))


def test_pl012_valor_corto_no_reporta():
    y = (
        "variables:\n  DEPLOY_TOKEN: abc\n"
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo hi\n"
    )
    assert "PL012" not in _codes(lint_yaml(y, "ado"))


def test_pl012_secreto_por_prefijo_de_valor():
    # ADICIÓN 1 + criterio canónico secret_masking (prefijo + >=8). Literal PARTIDO.
    val = "ghp_" + ("x" * 20)
    y = (
        "variables:\n  MI_VAR: " + val + "\n"
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo hi\n"
    )
    assert "PL012" in _codes(lint_yaml(y, "ado"))


# ── PL013 — secreto usado que NO está en la caja fuerte 94 ─────────────────────

_PL013_YAML = (
    "stages:\n- stage: A\n  jobs:\n  - job: J\n"
    "    steps:\n    - script: deploy --key $(DEPLOY_TOKEN)\n"
)


def test_pl013_secreto_fuera_de_caja_fuerte():
    assert "PL013" in _codes(lint_yaml(_PL013_YAML, "ado", known_variables=["OTHER"]))


def test_pl013_omitida_si_known_variables_none():
    assert "PL013" not in _codes(lint_yaml(_PL013_YAML, "ado", known_variables=None))


# ── PL014 — echo de un nombre secreto ─────────────────────────────────────────

def test_pl014_echo_de_secreto():
    y = (
        "stages:\n- stage: A\n  jobs:\n  - job: J\n"
        "    steps:\n    - script: echo $(API_KEY)\n"
    )
    assert "PL014" in _codes(lint_yaml(y, "ado"))
