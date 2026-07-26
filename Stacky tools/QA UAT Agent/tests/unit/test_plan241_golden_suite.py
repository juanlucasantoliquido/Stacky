"""test_plan241_golden_suite.py — Plan 241 F9.

Congela los tickets que corren en verde como suite de regresion reproducible.
Sin esto, cualquier cambio futuro puede reintroducir un falso verde y nadie se
entera hasta que alguien mire una captura (asi se descubrio el del ADO-366).
"""
import json

import pytest

from golden_suite import record, verify, load_expected


def _fake_runner(verdict="PASS", verified=2, p01="verified"):
    def _run(ticket_id, mode="dry-run", verbose=False):
        return {
            "ok": True, "ticket_id": ticket_id, "verdict": verdict,
            "stages": {"functional_verdict": {
                "ok": True, "skipped": False, "verified": verified,
                "criteria": [{"id": "P01", "status": p01},
                             {"id": "P02", "status": "verified"}],
            }},
        }
    return _run


def test_record_congela_el_esperado(tmp_path):
    out = record([367], golden_dir=tmp_path, runner=_fake_runner())
    assert out["ok"] is True
    data = json.loads((tmp_path / "expected.json").read_text(encoding="utf-8"))
    assert data["367"]["verdict"] == "PASS"
    assert data["367"]["verified"] == 2
    assert data["367"]["scenarios"]["P01"] == "verified"


def test_verify_sin_cambios_es_ok(tmp_path):
    record([367], golden_dir=tmp_path, runner=_fake_runner())
    res = verify(golden_dir=tmp_path, runner=_fake_runner())
    assert res["ok"] is True
    assert res["diffs"] == []
    assert res["checked"] == 1


def test_verify_detecta_diff_por_escenario(tmp_path):
    record([367], golden_dir=tmp_path, runner=_fake_runner())
    res = verify(golden_dir=tmp_path,
                 runner=_fake_runner(verdict="MIXED", verified=1, p01="not_verifiable"))
    assert res["ok"] is False
    fields = {d["field"] for d in res["diffs"]}
    assert "verdict" in fields
    assert "verified" in fields
    assert "scenario:P01" in fields


def test_verify_sin_golden_grabado(tmp_path):
    res = verify(golden_dir=tmp_path, runner=_fake_runner())
    assert res["ok"] is False
    assert res["error"] == "no_golden_recorded"
    assert load_expected(tmp_path) == {}


def test_no_lanza_si_el_runner_explota(tmp_path):
    def _boom(ticket_id, mode="dry-run", verbose=False):
        raise RuntimeError("pipeline exploto")
    out = record([367], golden_dir=tmp_path, runner=_boom)
    assert out["ok"] is True                     # el modulo NUNCA lanza
    data = load_expected(tmp_path)
    assert data["367"]["verdict"] == "BLOCKED"
    assert "error" in data["367"]


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
