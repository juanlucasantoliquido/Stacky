"""tests/test_plan186_lint_fixes.py — Plan 186 F3.

Autofixes deterministas (cirugía de líneas, nunca re-dump) para PL002/PL003/PL005.
KPI-5 reforzado (C3): el fix parsea, re-lintea sin ese código, NO aumenta errores,
NO introduce códigos nuevos, y cambia <=3 líneas.
"""
from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.pipeline_lint import lint_yaml  # noqa: E402


def _first_fix(rep, code):
    return next((f for f in rep.findings if f.code == code and f.fix is not None), None)


def _changed_lines(old, new):
    diff = difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="")
    return [d for d in diff
            if (d.startswith("+") or d.startswith("-"))
            and not d.startswith("+++") and not d.startswith("---")]


def _assert_kpi5(yaml_text, provider, code):
    rep = lint_yaml(yaml_text, provider)
    finding = _first_fix(rep, code)
    assert finding is not None, f"{code}: no hay finding con fix en {provider}"
    new_yaml = finding.fix.new_yaml
    # (a) parsea
    yaml.safe_load(new_yaml)
    # re-lint
    rep2 = lint_yaml(new_yaml, provider)
    codes2 = [f.code for f in rep2.findings]
    codes1 = [f.code for f in rep.findings]
    # (b) no contiene ese código en esa línea (basta: el código desaparece o baja)
    assert codes2.count(code) < codes1.count(code), f"{code}: el fix no eliminó la ocurrencia"
    # (c) counts error MENOR
    assert rep2.counts["error"] < rep.counts["error"], f"{code}: el fix no bajó los errores"
    # (d) no introduce códigos nuevos
    nuevos = set(codes2) - set(codes1)
    assert not nuevos, f"{code}: el fix introdujo códigos nuevos {nuevos}"
    # (e) <=3 líneas cambiadas
    changed = _changed_lines(yaml_text, new_yaml)
    assert len(changed) <= 3, f"{code}: {len(changed)} líneas cambiadas: {changed}"


# ── corpus (mismos rotos de F1, con vecinos que fuerzan la seguridad del fix) ──

Y_PL002_ADO = (
    "stages:\n"
    "- stage: A\n  jobs:\n  - job: J1\n    steps:\n    - script: echo hi\n"
    "- stage: A\n  jobs:\n  - job: J2\n    steps:\n    - script: echo hi\n"
)
Y_PL002_GITLAB = (
    "stages:\n- build\n"
    "myjob:\n  stage: build\n  script:\n  - echo a\n"
    "myjob:\n  stage: build\n  script:\n  - echo b\n"
)
Y_PL003_ADO = (
    "stages:\n- stage: A\n  dependsOn: Zzz\n  jobs:\n  - job: J\n"
    "    steps:\n    - script: echo hi\n"
)
Y_PL003_GITLAB = (
    "stages:\n- build\nmyjob:\n  stage: build\n  needs:\n  - ghost\n"
    "  script:\n  - echo hi\n"
)
Y_PL005_ADO = "stages:\n- stage: A\n  jobs:\n  - job: Empty\n"
Y_PL005_GITLAB = "stages:\n- build\nemptyjob:\n  stage: build\n"


def test_fix_pl002_ado():
    _assert_kpi5(Y_PL002_ADO, "ado", "PL002")


def test_fix_pl002_gitlab():
    _assert_kpi5(Y_PL002_GITLAB, "gitlab", "PL002")


def test_fix_pl003_ado():
    _assert_kpi5(Y_PL003_ADO, "ado", "PL003")


def test_fix_pl003_gitlab():
    _assert_kpi5(Y_PL003_GITLAB, "gitlab", "PL003")


def test_fix_pl005_ado():
    _assert_kpi5(Y_PL005_ADO, "ado", "PL005")


def test_fix_pl005_gitlab():
    _assert_kpi5(Y_PL005_GITLAB, "gitlab", "PL005")


def test_fix_pl002_renombra_la_segunda_no_la_primera():
    # C3: un tercer stage con dependsOn: A debe seguir resolviendo tras el fix.
    y = (
        "stages:\n"
        "- stage: A\n  jobs:\n  - job: J1\n    steps:\n    - script: echo hi\n"
        "- stage: A\n  jobs:\n  - job: J2\n    steps:\n    - script: echo hi\n"
        "- stage: C\n  dependsOn: A\n  jobs:\n  - job: J3\n    steps:\n    - script: echo hi\n"
    )
    rep = lint_yaml(y, "ado")
    fx = _first_fix(rep, "PL002")
    assert fx is not None
    rep2 = lint_yaml(fx.fix.new_yaml, "ado")
    codes2 = [f.code for f in rep2.findings]
    assert "PL003" not in codes2  # dependsOn: A sigue resolviendo (se renombró la 2.ª)
    assert "PL002" not in codes2
    # la PRIMERA definición sigue llamándose A
    assert "- stage: A\n" in fx.fix.new_yaml


def test_fix_none_si_linea_no_localizada():
    # needs en forma de dict (- job: ghost): el fix no puede localizar "- ghost" → fix None, sin crash.
    y = (
        "stages:\n- build\nmyjob:\n  stage: build\n  needs:\n  - job: ghost\n"
        "  script:\n  - echo hi\n"
    )
    rep = lint_yaml(y, "gitlab")
    pl003 = [f for f in rep.findings if f.code == "PL003"]
    assert pl003, "debía detectar PL003 (needs dict roto)"
    assert all(f.fix is None for f in pl003)


def test_fixes_omitidos_yaml_gigante():
    # C9: YAML > 200 KB → todos los fix None y fixes_omitted True.
    padding = "# " + ("A" * 300_000) + "\n"
    y = padding + Y_PL002_ADO
    rep = lint_yaml(y, "ado")
    assert rep.fixes_omitted is True
    assert all(f.fix is None for f in rep.findings)
