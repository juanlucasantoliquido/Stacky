"""Plan 202 E2/E3 — planner de cola derivada + gate anti-deuda-de-papel.

Dos clases de test conviven a proposito:
  * los que siembran un `docs/` de mentira en tmp_path (logica de derivacion), y
  * los ANCLAJE REAL (sin monkeypatch de `_docs_dir` ni de `_git`), que son los
    unicos que impiden el falso verde que ya hundio la v1 de este plan: tests que
    monkeypatchean `_docs_dir` pasan en verde aunque la Fragua sea un no-op en
    produccion porque el path apunta a una carpeta inexistente.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _ledger_en_tmp(monkeypatch, tmp_path):
    import runtime_paths

    from services import night_foundry_ledger as L

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path / "data")
    L.reset_inflight()
    yield
    L.reset_inflight()


def _P():
    from services import night_foundry_planner as P

    return P


def _sembrar(monkeypatch, tmp_path, docs: dict[str, str]):
    """Crea un docs/ falso y apunta el planner ahi. Devuelve el Path."""
    P = _P()
    d = tmp_path / "docs"
    d.mkdir(parents=True, exist_ok=True)
    for nombre, contenido in docs.items():
        (d / nombre).write_text(contenido, encoding="utf-8")
    monkeypatch.setattr(P, "_docs_dir", lambda: d)
    # la disponibilidad tambien consulta git; los tests que mockean `_git` con un
    # lambda ciego dejarian `_is_git_worktree()` en False y la Fragua no derivaria
    # nada. La disponibilidad tiene sus propios tests (real / congelado / sin docs).
    monkeypatch.setattr(P, "_is_git_worktree", lambda: True)
    return d


_V1 = "# Plan X\n\n- **Estado:** PROPUESTO v1 — 2026-01-01\n\ncuerpo\n"
_V2 = "# Plan X\n\n- **Estado:** CRITICADO v2 — 2026-01-01\n\ncuerpo\n"
_IMPL = "# Plan X\n\n- **Estado:** IMPLEMENTADO — 2026-01-01\n\ncuerpo\n"


# ═══════════════════ ANCLAJE REAL (sin monkeypatch) ═══════════════════════════

def test_docs_dir_resuelve_a_carpeta_de_planes():
    """[C1] El bug que hundio la v1: `app_root()/"docs"` = backend/docs, INEXISTENTE.
    Este test corre contra el arbol REAL, sin monkeypatch."""
    P = _P()
    d = P._docs_dir()
    assert d.exists() and d.is_dir(), f"_docs_dir() no existe: {d}"
    assert d.name == "docs" and d.parent.name == "Stacky Agents"
    planes = list(d.glob("[0-9]*_PLAN_*.md"))
    assert len(planes) > 50, f"solo {len(planes)} planes en {d}"
    assert any(p.name.startswith("202_") for p in planes)


def test_plan_docs_reales_no_vacio_y_status_line_legible():
    """Anclaje real: el parser de status line funciona sobre los docs de verdad."""
    P = _P()
    docs = P._plan_docs()
    assert len(docs) > 50
    con_estado = [d for d in docs if P._status_line(d.read_text(encoding="utf-8", errors="replace"))]
    assert len(con_estado) > 50, "el parser de Estado: no engancha con los docs reales"


def test_order_block_numbers_real_sobre_hojas_de_ruta():
    """[BUG REAL DEL PLAN] la ventana fija de 8 lineas del §E0 servia para el doc 195
    pero NO para el 197 (su linea de orden cae 8 lineas debajo del encabezado).
    Anclaje REAL: ambas hojas de ruta deben rendir numeros de plan."""
    P = _P()
    rutas = P._roadmap_docs()
    assert len(rutas) >= 2, f"no encontre las hojas de ruta reales: {rutas}"
    con_orden = {r.name[:3]: P._order_block_numbers(r) for r in rutas}
    for nn in ("195", "197"):
        coincide = [v for k, v in con_orden.items() if k == nn]
        assert coincide and coincide[0], f"la hoja de ruta {nn} no rindio numeros: {con_orden}"


def test_count_backlog_real_no_explota():
    """Anclaje real: el gate lee los 200+ docs verdaderos sin romper."""
    P = _P()
    b = P._count_backlog()
    assert b["v1_uncriticized"] >= 0 and b["v2_unimplemented"] >= 0
    assert b["v1_uncriticized"] + b["v2_unimplemented"] > 0, "0 y 0 huele a lectura vacia"


def test_fragua_disponible_en_dev_real():
    P = _P()
    disp = P.foundry_availability()
    assert disp["available"] is True, disp


# ═══════════════════ Guard de deploy CONGELADO (E2, riesgo abierto) ═══════════

def test_fragua_no_disponible_en_congelado(monkeypatch):
    """En PyInstaller `backend_root()` es el dir del .exe ⇒ backend_root().parent/'docs'
    colapsa sobre app_root()/'docs' (el path inexistente de la v1) y ademas no hay repo
    git. La Fragua debe fallar CERRADO y VISIBLE, nunca degradar en silencio."""
    P = _P()
    import runtime_paths

    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    disp = P.foundry_availability()
    assert disp["available"] is False
    assert disp["reason_code"] == "frozen_deploy"
    assert disp["reason"], "el motivo tiene que ser legible para el operador"
    # y no deriva NADA (fail-closed, no un escaneo de una carpeta vacia)
    assert P.derive_candidates() == []
    assert P.plan_night("2026-07-26")["enqueued"] == {
        "critic": 0, "auditor": 0, "package": 0, "reconciler": 0, "proposer": 0,
        "skipped_dedup": 0,
    }


def test_docs_dir_ausente_es_no_disponible(monkeypatch, tmp_path):
    P = _P()
    monkeypatch.setattr(P, "_docs_dir", lambda: tmp_path / "no-existe")
    disp = P.foundry_availability()
    assert disp["available"] is False and disp["reason_code"] == "docs_dir_missing"


# ═══════════════════ Derivacion ══════════════════════════════════════════════

def test_deriva_critic_de_v1_sin_criticar(monkeypatch, tmp_path):
    P = _P()
    _sembrar(monkeypatch, tmp_path, {
        "301_PLAN_UNO.md": _V1,
        "302_PLAN_DOS.md": _V2,
        # [C2] v1 GENUINO que MENCIONA "CRITICADO v2" en su PROSA: sigue siendo critic
        "303_PLAN_TRES.md": _V1 + "\nEste plan sera CRITICADO v2 mas adelante.\n",
    })
    monkeypatch.setattr(P, "_git", lambda args: "")
    monkeypatch.setattr(P, "_main_tree_files", lambda base="main": set())
    cands = [c for c in P.derive_candidates() if c[0] == "critic"]
    targets = {c[1] for c in cands}
    assert targets == {"plan:301", "plan:303"}, targets


def test_deriva_auditor_de_ramas_impl(monkeypatch, tmp_path):
    P = _P()
    _sembrar(monkeypatch, tmp_path, {"301_PLAN_UNO.md": _V2})

    def _git_mock(args):
        if args[:1] == ["for-each-ref"]:
            return "impl/devops aaaa1111\nimpl/ux bbbb2222"
        return ""

    monkeypatch.setattr(P, "_git", _git_mock)
    monkeypatch.setattr(P, "_main_tree_files", lambda base="main": set())
    aud = [c for c in P.derive_candidates() if c[0] == "auditor"]
    assert sorted(aud) == [("auditor", "branch:impl/devops", "aaaa1111"),
                           ("auditor", "branch:impl/ux", "bbbb2222")]


def test_deriva_reconciler_por_drift(monkeypatch, tmp_path):
    P = _P()
    doc = (_IMPL + "\nArchivos: `Stacky Agents/backend/services/fantasma.py` y "
                   "`Stacky Agents/backend/app.py`\n")
    _sembrar(monkeypatch, tmp_path, {"310_PLAN_DRIFT.md": doc})
    monkeypatch.setattr(P, "_git", lambda args: "tipsha")
    monkeypatch.setattr(P, "_main_tree_files",
                        lambda base="main": {"Stacky Agents/backend/app.py"})
    rec = [c for c in P.derive_candidates() if c[0] == "reconciler"]
    assert [c[1] for c in rec] == ["plan:310"]


def test_sin_drift_cuando_todo_esta_en_main(monkeypatch, tmp_path):
    P = _P()
    doc = _IMPL + "\nArchivos: `Stacky Agents/backend/app.py`\n"
    _sembrar(monkeypatch, tmp_path, {"311_PLAN_OK.md": doc})
    monkeypatch.setattr(P, "_git", lambda args: "tipsha")
    monkeypatch.setattr(P, "_main_tree_files",
                        lambda base="main": {"Stacky Agents/backend/app.py"})
    assert [c for c in P.derive_candidates() if c[0] == "reconciler"] == []


def test_drift_no_deriva_si_main_no_se_puede_leer(monkeypatch, tmp_path):
    """Fail-closed: sin arbol de `main` legible NO se inventan candidatos."""
    P = _P()
    doc = _IMPL + "\nArchivos: `Stacky Agents/backend/services/fantasma.py`\n"
    _sembrar(monkeypatch, tmp_path, {"312_PLAN_X.md": doc})
    monkeypatch.setattr(P, "_git", lambda args: "")
    assert P._derive_drift_candidates() == []


# ═══════════════════ plan_night / idempotencia ═══════════════════════════════

def test_planner_idempotente_no_duplica(monkeypatch, tmp_path):
    """KPI-1: dos corridas sobre el MISMO estado no duplican work items."""
    P = _P()
    from services import night_foundry_ledger as L

    _sembrar(monkeypatch, tmp_path, {"301_PLAN_UNO.md": _V1, "302_PLAN_DOS.md": _V1})
    monkeypatch.setattr(P, "_git", lambda args: "")
    monkeypatch.setattr(P, "_main_tree_files", lambda base="main": set())

    P.plan_night("2026-07-26")
    n1 = len(L.list_items())
    assert n1 == 2
    P.plan_night("2026-07-27")
    assert len(L.list_items()) == n1, "la 2a corrida no debe agregar items"


def test_proposer_no_se_encola_en_f0(monkeypatch, tmp_path):
    """KPI-6: con backlog de papel, CERO items del carril proponedor."""
    P = _P()
    docs = {f"3{i:02d}_PLAN_V2_{i}.md": _V2 for i in range(9)}
    docs["399_PLAN_V1.md"] = _V1
    _sembrar(monkeypatch, tmp_path, docs)
    monkeypatch.setattr(P, "_git", lambda args: "")
    monkeypatch.setattr(P, "_main_tree_files", lambda base="main": set())
    res = P.plan_night("2026-07-26")
    assert res["enqueued"]["proposer"] == 0
    assert res["gate"]["proposer_allowed"] is False


# ═══════════════════ E3 · gate anti-deuda-de-papel ═══════════════════════════

def test_gate_bloquea_por_v1_sin_criticar(monkeypatch, tmp_path):
    P = _P()
    _sembrar(monkeypatch, tmp_path, {"301_PLAN_UNO.md": _V1})
    g = P.foundry_backlog_gate()
    assert g["proposer_allowed"] is False and "v1" in g["reason"]


def test_gate_bloquea_por_v2_sin_implementar(monkeypatch, tmp_path):
    P = _P()
    _sembrar(monkeypatch, tmp_path, {f"3{i:02d}_PLAN_V2_{i}.md": _V2 for i in range(9)})
    g = P.foundry_backlog_gate()
    assert g["proposer_allowed"] is False
    assert "sin implementar" in g["reason"]
    assert g["metrics"]["v2_unimplemented"] == 9


def test_gate_bloquea_por_ratio(monkeypatch, tmp_path):
    P = _P()
    from services import night_foundry_ledger as L

    _sembrar(monkeypatch, tmp_path, {"301_PLAN_IMPL.md": _IMPL})
    for i in range(2):
        L.upsert_item("auditor", f"branch:b{i}",
                      L.compute_input_hash("auditor", f"branch:b{i}", "s"), night="N")
    g = P.foundry_backlog_gate("N")
    assert g["proposer_ceiling"] == 0 and g["proposer_allowed"] is False
    assert "1:3" in g["reason"]


def test_gate_permite_cuando_backlog_limpio(monkeypatch, tmp_path):
    P = _P()
    from services import night_foundry_ledger as L

    _sembrar(monkeypatch, tmp_path, {"301_PLAN_IMPL.md": _IMPL})
    for i in range(6):
        L.upsert_item("auditor", f"branch:b{i}",
                      L.compute_input_hash("auditor", f"branch:b{i}", "s"), night="N")
    g = P.foundry_backlog_gate("N")
    assert g["proposer_allowed"] is True and g["proposer_ceiling"] == 2


# ═══════════════════ §E0 · helpers deterministas ═════════════════════════════

def test_extract_files_rutas_backtick():
    P = _P()
    t = ("tocar `Stacky Agents/backend/app.py` y `Stacky Agents/frontend/src/x.tsx`, "
         "y otra vez `Stacky Agents/backend/app.py`; `no/es/del/repo.py` no cuenta")
    assert P._extract_files(t) == ["Stacky Agents/backend/app.py",
                                   "Stacky Agents/frontend/src/x.tsx"]


def test_extract_tests_nombres():
    P = _P()
    assert P._extract_tests("corre test_uno.py y test_dos.py y de nuevo test_uno.py") == [
        "test_dos.py", "test_uno.py"]


def test_extract_phases_En_Fn():
    P = _P()
    t = "## E1 — ledger\n\ntexto\n\n### F0 — base\n\n#### E12 — otra\n"
    fases = P._extract_phases(t)
    assert any(f.startswith("E1") for f in fases) and any(f.startswith("F0") for f in fases)


def test_match_gotchas_in_repo_no_lee_memoria():
    P = _P()
    assert P._match_gotchas("un doc sin nada especial") == []
    m = P._match_gotchas("hay que tocar el ratchet y HARNESS_TEST_FILES")
    assert "ratchet" in m and "HARNESS_TEST_FILES" in m


def test_doc_for_encuentra_por_prefijo(monkeypatch, tmp_path):
    P = _P()
    d = _sembrar(monkeypatch, tmp_path, {"305_PLAN_ALGO.md": _V2})
    assert P._doc_for("305") == d / "305_PLAN_ALGO.md"
    with pytest.raises(FileNotFoundError):
        P._doc_for("999")


def test_derive_package_primer_no_implementado(monkeypatch, tmp_path):
    P = _P()
    ruta = ("# Hoja de ruta\n\n- **Estado:** CRITICADO v2\n\n"
            "## 9. Orden de implementacion\n\n"
            "- **Orden de implementacion:** 401 -> 402 -> 403\n")
    d = _sembrar(monkeypatch, tmp_path, {
        "195_PLAN_HOJA.md": ruta,
        "401_PLAN_A.md": _IMPL,
        "402_PLAN_B.md": _V2,
        "403_PLAN_C.md": _V2,
    })
    assert d.exists()
    cands = P._derive_package_candidates()
    assert [c[1] for c in cands] == ["plan:402"], cands
