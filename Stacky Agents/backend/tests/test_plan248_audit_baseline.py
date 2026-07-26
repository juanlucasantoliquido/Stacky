"""Plan 248 F3 — orquestador + baseline congelado (el gate anti-falso-positivo). 12 tests.

El generador del baseline vive ACA (el archivo de test es quien ya tiene permiso de tocar
disco), NO dentro de `cicd_audit_core.py`, que es un modulo PURO.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from services.cicd_audit_core import (
    AUDIT_RULES,
    MODE_AUDIT,
    SEV_ERROR,
    audit_yaml,
    evidence_fingerprint,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "cicd_nl"
GOLDEN = FIXTURES / "golden"
BASELINE = FIXTURES / "audit_baseline.json"


def _filas_actuales() -> list:
    filas = []
    for path in sorted(GOLDEN.glob("*.yml")):
        report = audit_yaml(path.read_text(encoding="utf-8"), provider="ado", mode=MODE_AUDIT)
        for f in report.findings:
            filas.append({
                "file": path.name,
                "code": f.code,
                "location": f.location,
                "line": f.line,
                "severity": f.severity,
                "evidence_fingerprint": evidence_fingerprint(f.code, f.location, f.evidence),
                "veredicto": "REAL",
            })
    return filas


def test_emit_baseline():
    """Sólo corre con STACKY_EMIT_AUDIT_BASELINE=1. En una corrida normal NO escribe nada."""
    if os.getenv("STACKY_EMIT_AUDIT_BASELINE") != "1":
        pytest.skip("solo con STACKY_EMIT_AUDIT_BASELINE=1")
    BASELINE.write_text(
        json.dumps(_filas_actuales(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _baseline() -> list:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def _clave(fila: dict) -> tuple:
    return (fila["file"], fila["code"], fila["location"], fila["line"], fila["severity"])


def test_baseline_congelada():
    esperadas = [_clave(f) for f in _baseline()]
    actuales = [_clave(f) for f in _filas_actuales()]
    assert actuales == esperadas


def test_ley_de_severidad():
    """EL CAPSTONE: los 9 pipelines de PRODUCCION tienen 0 hallazgos SEV_ERROR."""
    for path in sorted(GOLDEN.glob("*.yml")):
        report = audit_yaml(path.read_text(encoding="utf-8"), provider="ado")
        assert report.counts[SEV_ERROR] == 0, path.name
        assert report.ok is True, path.name


def test_baseline_sin_falsos_positivos():
    for fila in _baseline():
        assert fila["veredicto"] == "REAL", fila


def test_toda_regla_error_tiene_cero_hits():
    """No alcanza con que el total sea 0: tiene que ser 0 POR REGLA."""
    con_error = {c for c, spec in AUDIT_RULES.items() if spec.severity_audit == SEV_ERROR}
    vistos = set()
    for path in sorted(GOLDEN.glob("*.yml")):
        report = audit_yaml(path.read_text(encoding="utf-8"), provider="ado")
        vistos.update(f.code for f in report.findings)
    assert not (con_error & vistos), con_error & vistos


def test_todo_hallazgo_tiene_ancla_y_remediacion():
    """KPI-2 — un hallazgo sin ancla es una opinion."""
    for path in sorted(GOLDEN.glob("*.yml")):
        report = audit_yaml(path.read_text(encoding="utf-8"), provider="ado")
        for f in report.findings:
            assert f.location, (path.name, f.code)
            assert f.remediation, (path.name, f.code)
            assert f.line is not None or f.location, (path.name, f.code)


def test_auditoria_funciona_sin_246_ni_247(monkeypatch):
    """La auditoria no depende de que 246/247 esten instalados."""
    import builtins

    real_import = builtins.__import__

    def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in ("services.pipeline_inventory", "services.pipeline_profiler"):
            raise ImportError("no instalado")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    actuales = [_clave(f) for f in _filas_actuales()]
    assert actuales == [_clave(f) for f in _baseline()]


def test_yaml_gigante_no_cuelga():
    report = audit_yaml("a: 1\n" * 200000, provider="ado")
    assert len(report.findings) == 1
    assert report.findings[0].code == "AUD000"


def test_yaml_roto_no_lanza():
    report = audit_yaml("a: [\n", provider="ado")
    assert report.ok is True
    assert [f.code for f in report.findings] == ["AUD000"]


def test_toda_regla_dispara_sobre_su_repro():
    """C4 — el capstone que faltaba: una regla que nunca dispara es PEOR que no tenerla."""
    for code, spec in sorted(AUDIT_RULES.items()):
        report = audit_yaml(spec.repro[1], provider=spec.repro[0], mode=spec.modes[0])
        emitidos = {f.code for f in report.findings}
        assert code in emitidos, (code, sorted(emitidos))


def test_toda_regla_declara_repro():
    assert len(AUDIT_RULES) == 12
    for code, spec in AUDIT_RULES.items():
        assert spec.repro and spec.repro[1].strip(), code


def test_ningun_repro_dispara_otra_regla_de_seguridad():
    """Gate mecanico de la no-duplicacion (§4.3)."""
    for code, spec in sorted(AUDIT_RULES.items()):
        report = audit_yaml(spec.repro[1], provider=spec.repro[0], mode=spec.modes[0])
        sec = {f.code for f in report.findings if f.code.startswith("SEC")}
        if code.startswith("SEC"):
            assert sec == {code}, (code, sorted(sec))
        else:
            assert not sec, (code, sorted(sec))


def test_sec002_no_duplica_pl014():
    """C5 — dos codigos para el mismo hecho es exactamente lo que §4.3 prohibe."""
    from services.pipeline_lint import lint_yaml

    texto = "steps:\n- script: echo $(API_KEY)\n"
    reporte_lint = lint_yaml(texto, provider="ado")
    codigos_lint = [f.code for f in getattr(reporte_lint, "findings", reporte_lint)]
    assert "PL014" in codigos_lint

    report = audit_yaml(texto, provider="ado")
    assert "SEC002" not in {f.code for f in report.findings}
