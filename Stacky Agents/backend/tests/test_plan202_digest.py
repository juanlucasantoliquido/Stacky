"""Plan 202 E6 — digest triado: rank + dedup + veredicto de mergeabilidad."""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    import runtime_paths

    from services import night_foundry_ledger as L

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    L.reset_inflight()
    yield tmp_path
    L.reset_inflight()


def _D():
    from services import night_foundry_digest as D

    return D


def _L():
    from services import night_foundry_ledger as L

    return L


class _Fake:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _item(lane, target, state="done", output_ref=None, cost=0, night="N"):
    L = _L()
    it = L.upsert_item(lane, target, L.compute_input_hash(lane, target, target), night=night)
    L.record_result(it["id"], state, output_ref=output_ref, cost_tokens=cost,
                    error=None if state != "failed" else "x")
    return it


# ═══════════════════ mergeabilidad ═══════════════════════════════════════════

def test_mergeability_clean_conflict_y_error(monkeypatch):
    D = _D()
    monkeypatch.setattr(D, "_run", lambda args, **kw: _Fake(0, "abc123tree"))
    assert D.mergeability("impl/x") == {"verdict": "clean", "mergeable": True,
                                        "conflict_paths": []}

    salida = ("CONFLICT (content): Merge conflict in Stacky Agents/backend/app.py\n"
              "  both modified: Stacky Agents/backend/config.py\n")
    monkeypatch.setattr(D, "_run", lambda args, **kw: _Fake(1, salida))
    r = D.mergeability("impl/x")
    assert r["verdict"] == "conflict" and r["mergeable"] is False
    # rutas COMPLETAS: todas las de este repo tienen un espacio ("Stacky Agents/…")
    assert r["conflict_paths"] == ["Stacky Agents/backend/app.py",
                                   "Stacky Agents/backend/config.py"]


def test_mergeability_rc_error_es_unknown(monkeypatch):
    """[C7] rc>1 es un ERROR de git (ref inexistente), NO un conflicto."""
    D = _D()
    monkeypatch.setattr(D, "_run", lambda args, **kw: _Fake(128, "fatal: not a valid object"))
    r = D.mergeability("rama-que-no-existe")
    assert r == {"verdict": "unknown", "mergeable": None, "conflict_paths": []}

    def _boom(args, **kw):
        raise OSError("git no esta")

    monkeypatch.setattr(D, "_run", _boom)
    assert D.mergeability("x")["verdict"] == "unknown"


def test_mergeability_real_contra_el_repo():
    """Anclaje REAL: `git merge-tree --write-tree` corre de verdad con el git
    instalado y no toca el working tree ni los refs."""
    import subprocess

    D = _D()
    from services import night_foundry_planner as P

    antes = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                           cwd=str(P._repo_root())).stdout
    r = D.mergeability("HEAD", base="main")
    despues = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True,
                             cwd=str(P._repo_root())).stdout
    assert antes == despues, "merge-tree modifico el working tree"
    assert r["verdict"] in ("clean", "conflict"), r
    assert isinstance(r["conflict_paths"], list)


def test_parse_conflict_paths():
    D = _D()
    salida = ("CONFLICT (content): Merge conflict in Stacky Agents/backend/app.py\n"
              "  both modified: Stacky Agents/docs/x.md\n"
              "sin conflicto aca\n")
    assert D._parse_conflict_paths(salida) == ["Stacky Agents/backend/app.py",
                                               "Stacky Agents/docs/x.md"]
    assert D._parse_conflict_paths("nada que ver") == []


def test_dedup_by_key_conserva_mejor_kind():
    D = _D()
    ds = [{"dedup_key": "plan:1", "kind": "review"},
          {"dedup_key": "plan:1", "kind": "merge"},
          {"dedup_key": "plan:2", "kind": "reconcile"}]
    out = {d["dedup_key"]: d["kind"] for d in D._dedup_by_key(ds)}
    assert out == {"plan:1": "merge", "plan:2": "reconcile"}


# ═══════════════════ KPI-7 · digest triado ═══════════════════════════════════

def test_digest_mergeabilidad_y_dedup(monkeypatch, _entorno):
    D = _D()
    _item("auditor", "branch:impl/limpia")
    _item("auditor", "branch:impl/conflictiva")
    # dos items del MISMO target ⇒ una sola decision
    _item("package", "plan:199", output_ref="packages/plan-199.json")
    _item("critic", "plan:199", output_ref="docs/199.md")

    def _merge(branch, base="main"):
        if "conflictiva" in branch:
            return {"verdict": "conflict", "mergeable": False,
                    "conflict_paths": ["Stacky Agents/backend/app.py"]}
        return {"verdict": "clean", "mergeable": True, "conflict_paths": []}

    monkeypatch.setattr(D, "mergeability", _merge)
    dig = D.build_digest("N", budget=40000, stopped_reason="queue_empty")

    por_target = {d["target"]: d for d in dig["decisions"]}
    assert por_target["branch:impl/limpia"]["mergeable"] is True
    assert por_target["branch:impl/conflictiva"]["mergeable"] is False
    assert por_target["branch:impl/conflictiva"]["conflict_paths"] == [
        "Stacky Agents/backend/app.py"]
    assert len([d for d in dig["decisions"] if d["target"] == "plan:199"]) == 1
    # de las dos, gana el kind de mas valor: implement (1) < review (2)
    assert por_target["plan:199"]["kind"] == "implement"


def test_ranking_por_kind(monkeypatch):
    D = _D()
    monkeypatch.setattr(D, "mergeability",
                        lambda b, base="main": {"verdict": "clean", "mergeable": True,
                                                "conflict_paths": []})
    _item("reconciler", "plan:1")
    _item("critic", "plan:2")
    _item("package", "plan:3")
    _item("auditor", "branch:impl/z")
    dig = D.build_digest("N", budget=1000, stopped_reason="queue_empty")
    assert [d["kind"] for d in dig["decisions"]] == ["merge", "implement", "review", "reconcile"]
    assert [d["rank"] for d in dig["decisions"]] == [1, 2, 3, 4]


def test_digest_solo_incluye_done(monkeypatch):
    D = _D()
    monkeypatch.setattr(D, "mergeability",
                        lambda b, base="main": {"verdict": "clean", "mergeable": True,
                                                "conflict_paths": []})
    _item("package", "plan:1", state="done")
    _item("package", "plan:2", state="pending")
    _item("package", "plan:3", state="failed")
    dig = D.build_digest("N", budget=1000, stopped_reason="queue_empty")
    assert [d["target"] for d in dig["decisions"]] == ["plan:1"]
    assert dig["counts"]["package"] == 1
    assert dig["counts"]["failed"] == 1


def test_budget_exhausted_se_refleja(monkeypatch):
    D = _D()
    _item("package", "plan:1", cost=500)
    dig = D.build_digest("N", budget=500, stopped_reason="budget")
    assert dig["budget_exhausted"] is True
    assert dig["spent_tokens"] == 500 and dig["budget_tokens"] == 500

    dig2 = D.build_digest("N", budget=500, stopped_reason="queue_empty")
    assert dig2["budget_exhausted"] is False


def test_digest_escribe_archivo_y_cumple_contrato(_entorno):
    D = _D()
    _item("package", "plan:1", output_ref="packages/p.json", night="2026-07-26")
    dig = D.build_digest("2026-07-26", budget=40000, stopped_reason="queue_empty")
    p = _entorno / "night_foundry" / "digests" / "digest-2026-07-26.json"
    assert p.exists()
    en_disco = json.loads(p.read_text(encoding="utf-8"))
    assert en_disco == dig
    for k in ("night", "generated_at", "budget_tokens", "spent_tokens", "budget_exhausted",
              "stopped_reason", "counts", "decisions"):
        assert k in dig, k
    for k in ("rank", "kind", "title", "target", "verdict", "mergeable", "conflict_paths",
              "package_ref", "cost_tokens", "dedup_key"):
        assert k in dig["decisions"][0], k


def test_digest_reporta_turno_no_disponible():
    """Extension aditiva del contrato §5.2: `unavailable` como stopped_reason, para
    que una noche que no corrio NO se lea como 'noche tranquila'."""
    D = _D()
    dig = D.build_digest("N", budget=40000, stopped_reason="unavailable")
    assert dig["stopped_reason"] == "unavailable"
    assert dig["budget_exhausted"] is False
    assert dig["decisions"] == []


def test_latest_digest_devuelve_el_mas_reciente(_entorno):
    D = _D()
    _item("package", "plan:1")
    D.build_digest("2026-07-24", budget=1, stopped_reason="queue_empty")
    D.build_digest("2026-07-26", budget=1, stopped_reason="queue_empty")
    D.build_digest("2026-07-25", budget=1, stopped_reason="queue_empty")
    assert D.latest_digest()["night"] == "2026-07-26"


def test_latest_digest_vacio_si_no_hay(_entorno):
    D = _D()
    assert D.latest_digest() == {}
