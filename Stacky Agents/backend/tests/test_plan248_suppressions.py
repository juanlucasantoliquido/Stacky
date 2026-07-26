"""Plan 248 F4 — supresiones que persisten pero no ciegan. 7 tests.

NINGUN test escribe en el data dir real: `runtime_paths.data_dir` va monkeypatcheado a tmp_path.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services import pipeline_audit_suppressions as sup
from services.cicd_audit_core import audit_yaml, evidence_fingerprint

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"


@pytest.fixture(autouse=True)
def _data_dir_aislado(tmp_path, monkeypatch):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield


def _sec006_de(nombre: str):
    crudo = (GOLDEN / nombre).read_text(encoding="utf-8")
    report = audit_yaml(crudo, provider="ado")
    return crudo, [f for f in report.findings if f.code == "SEC006"][0]


def test_reason_vacio_es_rechazado():
    with pytest.raises(ValueError):
        sup.add_suppression({"pipeline_key": "p", "code": "SEC006",
                             "location": "steps[1]", "reason": "   "})


def test_supresion_oculta_el_hallazgo():
    crudo, hallazgo = _sec006_de("security-scan-online.yml")
    sup.add_suppression({
        "pipeline_key": "p1", "code": hallazgo.code, "location": hallazgo.location,
        "evidence_fingerprint": evidence_fingerprint(
            hallazgo.code, hallazgo.location, hallazgo.evidence),
        "reason": "el script hace el gate por dentro",
    })
    report = audit_yaml(crudo, provider="ado", pipeline_key="p1",
                        suppressions=sup.list_suppressions("p1"))
    assert "SEC006" not in {f.code for f in report.findings}
    assert "SEC006" in {f.code for f in report.suppressed}
    assert report.counts["warning"] == len([f for f in report.findings if f.severity == "warning"])


def test_supresion_caduca_si_cambia_la_evidencia():
    """EL test que distingue una supresion de una VENDA."""
    crudo, hallazgo = _sec006_de("security-scan-online.yml")
    sup.add_suppression({
        "pipeline_key": "p1", "code": hallazgo.code, "location": hallazgo.location,
        "evidence_fingerprint": evidence_fingerprint(
            hallazgo.code, hallazgo.location, hallazgo.evidence),
        "reason": "evaluado en 2026",
    })
    mutado = crudo.replace("continueOnError: true", "allow_failure: true")
    report = audit_yaml(mutado, provider="ado", pipeline_key="p1",
                        suppressions=sup.list_suppressions("p1"))
    assert "SEC006" in {f.code for f in report.findings}


def test_supresion_no_derrama_a_otra_pipeline():
    crudo, hallazgo = _sec006_de("security-scan-online.yml")
    sup.add_suppression({
        "pipeline_key": "OTRA", "code": hallazgo.code, "location": hallazgo.location,
        "evidence_fingerprint": evidence_fingerprint(
            hallazgo.code, hallazgo.location, hallazgo.evidence),
        "reason": "otra pipeline",
    })
    report = audit_yaml(crudo, provider="ado", pipeline_key="p1",
                        suppressions=sup.list_suppressions())
    assert "SEC006" in {f.code for f in report.findings}


def test_retencion_500():
    for i in range(sup.MAX_ROWS + 1):
        sup.add_suppression({"pipeline_key": "p%d" % i, "code": "SEC006",
                             "location": "steps[0]", "reason": "x"})
    filas = sup.list_suppressions()
    assert len(filas) == sup.MAX_ROWS
    assert filas[0]["pipeline_key"] == "p1"   # la mas vieja fue expulsada


def test_remove_suppression_devuelve_false_si_no_existe():
    assert sup.remove_suppression("nope", "SEC006", "steps[0]") is False
    sup.add_suppression({"pipeline_key": "p1", "code": "SEC006",
                         "location": "steps[0]", "reason": "x"})
    assert sup.remove_suppression("p1", "SEC006", "steps[0]") is True
    assert sup.list_suppressions("p1") == []


def test_ledger_corrupto_no_rompe_la_auditoria():
    sup.add_suppression({"pipeline_key": "p1", "code": "SEC006",
                         "location": "steps[0]", "reason": "x"})
    ruta = sup._ledger_path()
    ruta.write_text(ruta.read_text(encoding="utf-8") + "{esto no es json\n", encoding="utf-8")
    filas = sup.list_suppressions()
    assert len(filas) == 1
    crudo = (GOLDEN / "security-scan-online.yml").read_text(encoding="utf-8")
    report = audit_yaml(crudo, provider="ado", pipeline_key="p1", suppressions=filas)
    assert report.ok is True
    json.dumps(report.to_dict())
