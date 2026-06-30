"""Plan 49 F0-F2 — golden-set de extractores puros del arnés."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/

import pytest

from evals.extraction_golden_runner import evaluate, load_cases


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.name)
def test_extraction_golden(case):
    reasons = evaluate(case)
    assert not reasons, f"{case.name}: " + "; ".join(reasons)


def test_corpus_no_vacio():
    assert load_cases(), "el corpus de extraccion no puede estar vacio"


def test_corpus_cubre_minimos_k1():
    cases = load_cases()
    epic = [c for c in cases if c.kind == "epic"]
    pt = [c for c in cases if c.kind == "pending_task"]
    assert len(epic) >= 7, f"se esperaban >=7 fixtures epic, hay {len(epic)}"
    assert len(pt) >= 4, f"se esperaban >=4 fixtures pending_task, hay {len(pt)}"
    assert len(cases) >= 8
