"""Plan 202 E4 — workers deterministas por carril (auditor / package / reconciler).

El auditor es AUDIT-ONLY DURO: GIT-ONLY, cero pytest, cero checkout. La prueba de
KPI-5 corre contra el repo REAL (sin mockear git) para que no sea un falso verde.
"""
from __future__ import annotations

import json
import subprocess

import pytest


@pytest.fixture(autouse=True)
def _data_dir(monkeypatch, tmp_path):
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield tmp_path


def _W():
    from services import night_foundry_workers as W

    return W


class _Fake:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


# ═══════════════════ KPI-5 · AUDIT-ONLY contra el repo REAL ══════════════════

def test_auditor_readonly_arbol_intacto(_data_dir):
    """KPI-5 sin mocks: el auditor corre git de verdad contra este repo y deja el
    working tree IDENTICO. Si algun dia alguien mete un comando que escribe, esto
    se pone rojo."""
    W = _W()
    from services import night_foundry_planner as P

    antes = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                           text=True, cwd=str(P._repo_root())).stdout
    res = W.run_auditor("HEAD", base="main")
    despues = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                             text=True, cwd=str(P._repo_root())).stdout
    assert antes == despues, "el auditor modifico el working tree"
    assert res["readonly_ok"] is True
    assert res["cost_tokens"] == 0
    assert res["output_ref"].startswith("audits/")
    reporte = json.loads((_data_dir / "night_foundry" / res["output_ref"]).read_text(encoding="utf-8"))
    assert reporte["base"] == "main" and reporte["branch"] == "HEAD"
    assert isinstance(reporte["changed_py"], list)


def test_auditor_marca_readonly_false_si_el_arbol_cambio(monkeypatch, _data_dir):
    W = _W()
    llamadas = {"n": 0}

    def _run_mock(args, **kw):
        if args[:2] == ["status", "--porcelain"]:
            llamadas["n"] += 1
            return _Fake(" M archivo.py" if llamadas["n"] > 1 else "")
        return _Fake("")

    monkeypatch.setattr(W, "_run", _run_mock)
    res = W.run_auditor("impl/x")
    assert res["readonly_ok"] is False


def test_auditor_reporta_diffstat_y_test_files(monkeypatch, _data_dir):
    W = _W()

    def _run_mock(args, **kw):
        if args[:2] == ["diff", "--stat"]:
            return _Fake(" backend/x.py | 3 +--\n 1 file changed")
        if args[:2] == ["diff", "--name-only"]:
            return _Fake("Stacky Agents/backend/services/x.py\n"
                         "Stacky Agents/backend/tests/test_algo.py\n"
                         "Stacky Agents/frontend/src/y.tsx")
        return _Fake("")

    monkeypatch.setattr(W, "_run", _run_mock)
    res = W.run_auditor("impl/x")
    rep = json.loads((_data_dir / "night_foundry" / res["output_ref"]).read_text(encoding="utf-8"))
    assert rep["test_files"] == ["Stacky Agents/backend/tests/test_algo.py"]
    assert rep["changed_py"] == ["Stacky Agents/backend/services/x.py",
                                "Stacky Agents/backend/tests/test_algo.py"]
    assert "1 file changed" in rep["diffstat"]


def test_auditor_nunca_invoca_pytest_ni_muta(monkeypatch, _data_dir):
    """[C3] El auditor F0 NO corre los tests de la rama (eso es del refutador F3, que
    necesita checkout propio). Se verifica sobre el UNICO seam de subproceso."""
    W = _W()
    vistos: list[list[str]] = []
    _VERBOS_OK = {"status", "diff", "rev-parse", "ls-tree", "cat-file", "for-each-ref"}

    def _run_mock(args, **kw):
        vistos.append(list(args))
        return _Fake("")

    monkeypatch.setattr(W, "_run", _run_mock)
    W.run_auditor("impl/x")
    assert vistos, "el auditor no llamo a git"
    for argv in vistos:
        assert argv[0] in _VERBOS_OK, f"verbo git no read-only: {argv}"
        plano = " ".join(argv)
        assert "pytest" not in plano and "checkout" not in plano


def test_auditor_escribe_solo_en_audits(monkeypatch, _data_dir):
    W = _W()
    monkeypatch.setattr(W, "_run", lambda args, **kw: _Fake(""))
    W.run_auditor("impl/devops")
    creados = sorted(p.relative_to(_data_dir).as_posix()
                     for p in (_data_dir / "night_foundry").rglob("*") if p.is_file())
    assert creados and all(c.startswith("night_foundry/audits/") for c in creados), creados


# ═══════════════════ constructor de paquetes ═════════════════════════════════

_DOC = """# Plan 999 — algo

- **Estado:** CRITICADO v2 — 2026-01-01

## E1 — primera etapa

**Archivos:** CREAR `Stacky Agents/backend/services/algo.py`; EDITAR
`Stacky Agents/backend/app.py`.

**Tests PRIMERO:** `tests/test_plan999_algo.py` con test_uno y test_dos.
Corre test_plan999_algo.py.

**Criterio de aceptacion (binario):** el ratchet queda verde y HARNESS_TEST_FILES
registra el archivo nuevo. KPI-1 verificado.

### F0 — base
"""


def test_build_package_extrae_secciones(_data_dir, tmp_path):
    W = _W()
    doc = tmp_path / "999_PLAN_ALGO.md"
    doc.write_text(_DOC, encoding="utf-8")
    res = W.build_package("999", doc)
    pkg = json.loads((_data_dir / "night_foundry" / res["output_ref"]).read_text(encoding="utf-8"))
    assert pkg["plan"] == "999"
    assert "Stacky Agents/backend/services/algo.py" in pkg["files_to_touch"]
    assert "test_plan999_algo.py" in pkg["tests_to_write"]
    assert any(f.startswith("E1") for f in pkg["phase_checklist"])
    assert pkg["gates"], "los criterios/gates no pueden salir vacios"
    assert res["output_ref"].startswith("packages/")
    assert res["cost_tokens"] == 0


def test_build_package_matchea_gotchas(_data_dir, tmp_path):
    W = _W()
    doc = tmp_path / "999_PLAN_ALGO.md"
    doc.write_text(_DOC, encoding="utf-8")
    res = W.build_package("999", doc)
    pkg = json.loads((_data_dir / "night_foundry" / res["output_ref"]).read_text(encoding="utf-8"))
    assert "ratchet" in pkg["gotchas"] and "HARNESS_TEST_FILES" in pkg["gotchas"]


def test_build_package_sobre_el_doc_real_202(_data_dir):
    """Anclaje REAL: el constructor arma un paquete util del doc 202 de verdad."""
    W = _W()
    from services import night_foundry_planner as P

    res = W.build_package("202", P._doc_for("202"))
    pkg = json.loads((_data_dir / "night_foundry" / res["output_ref"]).read_text(encoding="utf-8"))
    assert len(pkg["files_to_touch"]) >= 3, pkg["files_to_touch"]
    assert "test_plan202_ledger.py" in pkg["tests_to_write"]
    assert any(f.startswith("E") for f in pkg["phase_checklist"])
    assert "ratchet" in pkg["gotchas"]


def test_build_package_no_escribe_codigo_de_producto(_data_dir, tmp_path):
    """R1: el paquete propone tests como TEXTO; no crea ningun .py ejecutable."""
    W = _W()
    doc = tmp_path / "999_PLAN_ALGO.md"
    doc.write_text(_DOC, encoding="utf-8")
    W.build_package("999", doc)
    escritos = [p for p in (_data_dir / "night_foundry").rglob("*") if p.is_file()]
    assert escritos and all(p.suffix == ".json" for p in escritos), escritos


# ═══════════════════ reconciliador ═══════════════════════════════════════════

def test_reconciler_detecta_drift(monkeypatch, _data_dir, tmp_path):
    W = _W()
    from services import night_foundry_planner as P

    doc = tmp_path / "310_PLAN_D.md"
    doc.write_text("# X\n\n- **Estado:** IMPLEMENTADO\n\n"
                   "`Stacky Agents/backend/services/fantasma.py` y "
                   "`Stacky Agents/backend/app.py`\n", encoding="utf-8")
    monkeypatch.setattr(P, "_main_tree_files",
                        lambda base="main": {"Stacky Agents/backend/app.py"})
    r = W.run_reconciler("310", doc)
    assert r["declared"] == "IMPLEMENTADO"
    assert [d["file"] for d in r["drift"]] == ["Stacky Agents/backend/services/fantasma.py"]
    assert r["cost_tokens"] == 0


def test_reconciler_sin_drift_cuando_archivo_en_main(monkeypatch, _data_dir, tmp_path):
    W = _W()
    from services import night_foundry_planner as P

    doc = tmp_path / "311_PLAN_OK.md"
    doc.write_text("# X\n\n- **Estado:** IMPLEMENTADO\n\n`Stacky Agents/backend/app.py`\n",
                   encoding="utf-8")
    monkeypatch.setattr(P, "_main_tree_files",
                        lambda base="main": {"Stacky Agents/backend/app.py"})
    assert W.run_reconciler("311", doc)["drift"] == []


def test_reconciler_falla_cerrado_sin_main(monkeypatch, _data_dir, tmp_path):
    """Sin arbol de `main` legible NO se denuncia drift inventado."""
    W = _W()
    from services import night_foundry_planner as P

    doc = tmp_path / "312_PLAN_X.md"
    doc.write_text("# X\n\n- **Estado:** IMPLEMENTADO\n\n`Stacky Agents/backend/nada.py`\n",
                   encoding="utf-8")
    monkeypatch.setattr(P, "_main_tree_files", lambda base="main": None)
    r = W.run_reconciler("312", doc)
    assert r["drift"] == [] and r["unknown"] is True


def test_reconciler_no_escribe_archivos(monkeypatch, _data_dir, tmp_path):
    W = _W()
    from services import night_foundry_planner as P

    doc = tmp_path / "313_PLAN.md"
    doc.write_text("# X\n\n- **Estado:** IMPLEMENTADO\n\n`Stacky Agents/backend/x.py`\n",
                   encoding="utf-8")
    monkeypatch.setattr(P, "_main_tree_files", lambda base="main": set())
    W.run_reconciler("313", doc)
    d = _data_dir / "night_foundry"
    assert not d.exists() or not [p for p in d.rglob("*") if p.is_file()]
