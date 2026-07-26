"""test_plan241_epic_rollup.py — Plan 241 F7.

Una epica no da BLOCKED/missing_technical_analysis: da un veredicto agregado real
de sus tasks hijas.
"""
import pytest

from epic_rollup import rollup


def test_sin_hijas_ejecutadas():
    res = rollup(61, [])
    assert res["verdict"] == "SKIPPED"
    assert res["reason"] == "NO_EXECUTABLE_CHILDREN"

    res2 = rollup(61, [{"ado_id": 65, "verdict": ""}])
    assert res2["verdict"] == "SKIPPED"


def test_alguna_hija_fail_manda():
    res = rollup(61, [
        {"ado_id": 65, "verdict": "PASS", "verified": 3},
        {"ado_id": 70, "verdict": "FAIL", "verified": 1},
        {"ado_id": 99, "verdict": "BLOCKED"},
    ])
    assert res["verdict"] == "FAIL"
    assert res["reason"] == "CHILD_ACCEPTANCE_VIOLATED"


def test_blocked_sin_fail_es_mixed():
    res = rollup(61, [
        {"ado_id": 65, "verdict": "PASS", "verified": 2},
        {"ado_id": 70, "verdict": "BLOCKED"},
    ])
    assert res["verdict"] == "MIXED"
    assert res["reason"] == "PARTIAL_EPIC_COVERAGE"


def test_todas_pass():
    res = rollup(61, [
        {"ado_id": 65, "verdict": "PASS", "verified": 2},
        {"ado_id": 70, "verdict": "PASS", "verified": 4},
    ])
    assert res["verdict"] == "PASS"
    assert res["reason"] == "EPIC_ACCEPTANCE_MET"
    assert res["verified_total"] == 6


def test_children_siempre_presente():
    """Una epica en verde con una hija sin correr es un falso verde: el campo
    `children` lo hace VISIBLE siempre, pase lo que pase."""
    for children in ([], [{"ado_id": 65, "verdict": "PASS"}],
                     [{"ado_id": 65, "verdict": "FAIL"}],
                     [{"ado_id": 65, "verdict": "BLOCKED"}]):
        res = rollup(61, children)
        assert "children" in res
        assert isinstance(res["children"], list)
        assert res["children_total"] == len(children)


def test_epica_61_con_65_y_70():
    """Caso real: 65 y 70 son hijas de 61 (parent=61 verificado) y ya corren."""
    res = rollup(61, [
        {"ado_id": 65, "verdict": "PASS", "verified": 3, "run_id": "uat-65-x"},
        {"ado_id": 70, "verdict": "MIXED", "verified": 1, "run_id": "uat-70-y"},
    ])
    assert res["epic_id"] == 61
    assert res["verdict"] == "MIXED"
    assert [c["ado_id"] for c in res["children"]] == [65, 70]
    assert res["children_pass"] == 1


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
