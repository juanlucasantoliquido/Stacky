"""Plan 51 F2 — Golden-set a mano del linter de catálogo + idempotencia + NO-OP."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from evals.catalog_diff_runner import load_cases, evaluate  # noqa: E402
from harness.epic_gate import golden_catalog_diff  # noqa: E402

_CASES = load_cases()


def test_fixtures_present():
    assert len(_CASES) >= 6


@pytest.mark.parametrize("case", _CASES, ids=[c.name for c in _CASES])
def test_golden_case(case):
    reasons = evaluate(case)
    assert not reasons, f"{case.name}: {reasons}"


def test_idempotent():
    html = "<p>proceso Fantasma1 y proceso Fantasma2</p>"
    catalog = [{"name": "RSCore"}]
    assert golden_catalog_diff(html, catalog) == golden_catalog_diff(html, catalog)


def test_noop_without_catalog_or_html():
    assert golden_catalog_diff("<p>proceso X</p>", []) == []
    assert golden_catalog_diff("", [{"name": "X"}]) == []


def test_result_always_sorted():
    html = "<p>proceso Zeta, proceso Alfa, proceso Beta</p>"
    out = golden_catalog_diff(html, [{"name": "RSCore"}])
    assert out == sorted(out)
