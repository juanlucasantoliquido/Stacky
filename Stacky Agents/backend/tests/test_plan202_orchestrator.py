"""Plan 202 E5 — orquestador serializado: 1 item por iteracion, corte duro por
presupuesto, resumibilidad y kill-switches redundantes."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _entorno(monkeypatch, tmp_path):
    import runtime_paths

    from services import night_foundry_ledger as L

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    for env in ("STACKY_NIGHT_FOUNDRY_HARD_DISABLE", "STACKY_EVOLUTION_HARD_DISABLE"):
        monkeypatch.delenv(env, raising=False)
    L.reset_inflight()
    yield tmp_path
    L.reset_inflight()


def _O():
    from services import night_foundry_orchestrator as O

    return O


def _L():
    from services import night_foundry_ledger as L

    return L


def _sembrar(lane: str, n: int, night: str = "N") -> list[dict]:
    L = _L()
    return [L.upsert_item(lane, f"plan:{i:03d}",
                          L.compute_input_hash(lane, f"plan:{i:03d}", "s"), night=night)
            for i in range(n)]


def _estados(night="N") -> dict[str, int]:
    L = _L()
    out: dict[str, int] = {}
    for r in L.list_items(night=night):
        out[r["state"]] = out.get(r["state"], 0) + 1
    return out


# ═══════════════════ KPI-2 · serializacion ═══════════════════════════════════

def test_orquestador_serializa_uno_por_iteracion(monkeypatch):
    """5 items, corte forzado tras el 2do ⇒ 2 done + 3 pending. Cero colision."""
    O = _O()
    _sembrar("package", 5)
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: {"output_ref": "packages/x.json", "cost_tokens": 0})
    llamadas = {"n": 0}

    def _stop(night, budget):
        llamadas["n"] += 1
        return (llamadas["n"] > 2, "budget")

    monkeypatch.setattr(O, "should_stop", _stop)
    res = O.run_night("N", budget=99999)
    assert res["stopped_reason"] == "budget"
    assert _estados() == {"done": 2, "pending": 3}


# ═══════════════════ KPI-3 · corte duro por presupuesto ══════════════════════

def test_corte_duro_por_presupuesto(monkeypatch):
    O = _O()
    _sembrar("package", 3)
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: {"output_ref": None, "cost_tokens": 500})
    res = O.run_night("N", budget=1000)
    assert res["stopped_reason"] == "budget"
    assert res["spent_tokens"] == 1000
    assert _estados() == {"done": 2, "pending": 1}


# ═══════════════════ KPI-4 · resumibilidad ═══════════════════════════════════

def test_resume_por_hash_no_reejecuta_done(monkeypatch):
    O = _O()
    L = _L()
    a, b = _sembrar("package", 2)
    L.record_result(a["id"], "done", output_ref="packages/ya.json", cost_tokens=7)
    L.claim_next()  # deja `b` claimed y huerfano
    L.reset_inflight()  # simula que la corrida se murio

    corridos: list[str] = []

    def _fake(item):
        corridos.append(item["id"])
        return {"output_ref": None, "cost_tokens": 0}

    monkeypatch.setattr(O, "run_deterministic_item", _fake)
    O.run_night("N", budget=99999)
    assert corridos == [b["id"]], "el done no debe re-ejecutarse; el claimed si"
    finales = {r["id"]: r for r in L.list_items(night="N")}
    assert finales[a["id"]]["state"] == "done"
    assert finales[a["id"]]["output_ref"] == "packages/ya.json"
    assert finales[b["id"]]["state"] == "done"


# ═══════════════════ KPI-8 · kill-switches redundantes ═══════════════════════

def test_killswitches_detienen_todo(monkeypatch, _entorno):
    O = _O()
    _sembrar("package", 3)
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: pytest.fail("no debio procesarse nada"))

    stop = _entorno / "night_foundry" / "STOP"
    stop.parent.mkdir(parents=True, exist_ok=True)
    stop.write_text("", encoding="utf-8")
    res = O.run_night("N", budget=99999)
    assert res["stopped_reason"] == "stop_file"
    assert _estados() == {"pending": 3}

    stop.unlink()
    monkeypatch.setenv("STACKY_EVOLUTION_HARD_DISABLE", "1")
    assert O.run_night("N", budget=99999)["stopped_reason"] == "hard_disable"
    assert _estados() == {"pending": 3}


def test_hard_disable_propio_detiene(monkeypatch):
    """[C9] El kill-switch PROPIO es independiente del nombre que reserva el 167."""
    O = _O()
    _sembrar("package", 2)
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: pytest.fail("no debio procesarse nada"))
    monkeypatch.setenv("STACKY_NIGHT_FOUNDRY_HARD_DISABLE", "1")
    assert O.run_night("N", budget=99999)["stopped_reason"] == "hard_disable"
    assert _estados() == {"pending": 2}


# ═══════════════════ carril critic ═══════════════════════════════════════════

def test_critic_sin_dispatch_no_bucle(monkeypatch):
    """[C6] Sin runtime Claude los critic quedan pending y el loop TERMINA.
    Sin el guard `seen`+`exclude_ids` esto seria un bucle infinito (el skip suma 0
    tokens, asi que el presupuesto nunca cortaria)."""
    O = _O()
    _sembrar("critic", 3)
    res = O.run_night("N", budget=99999, dispatch_critic=None)
    assert res["stopped_reason"] == "queue_empty"
    assert _estados() == {"pending": 3}


def test_critic_precarga_presupuesto_no_excede(monkeypatch):
    """El costo real de una critica solo se sabe post-hoc: se PRE-RESERVA."""
    O = _O()
    L = _L()
    critic = L.upsert_item("critic", "plan:900",
                           L.compute_input_hash("critic", "plan:900", "s"), night="N")
    _sembrar("package", 1)
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: {"output_ref": None, "cost_tokens": 10})
    llamado = {"n": 0}

    def _dispatch(item):
        llamado["n"] += 1
        return {"output_ref": None, "cost_tokens": O.CRITIC_EST_TOKENS}

    res = O.run_night("N", budget=1000, dispatch_critic=_dispatch)
    assert llamado["n"] == 0, "el critic no debia dispatcharse: no entra en el techo"
    assert res["stopped_reason"] == "budget"
    finales = {r["id"]: r["state"] for r in L.list_items(night="N")}
    assert finales[critic["id"]] == "pending"


def test_critic_con_dispatch_corre_y_cobra(monkeypatch):
    O = _O()
    L = _L()
    it = L.upsert_item("critic", "plan:901",
                       L.compute_input_hash("critic", "plan:901", "s"), night="N")
    res = O.run_night("N", budget=99999,
                      dispatch_critic=lambda item: {"output_ref": "docs/901.md",
                                                    "cost_tokens": 4321})
    assert res["spent_tokens"] == 4321
    fila = [r for r in L.list_items(night="N") if r["id"] == it["id"]][0]
    assert fila["state"] == "done" and fila["output_ref"] == "docs/901.md"


# ═══════════════════ fallos y post-condiciones ═══════════════════════════════

def test_item_que_lanza_queda_failed(monkeypatch):
    O = _O()

    def _boom(item):
        raise RuntimeError("revento el worker")

    _sembrar("package", 2)
    monkeypatch.setattr(O, "run_deterministic_item", _boom)
    res = O.run_night("N", budget=99999)
    assert res["stopped_reason"] == "queue_empty"
    assert _estados() == {"failed": 2}
    L = _L()
    assert all("revento el worker" in (r["error"] or "") for r in L.list_items(night="N"))


def test_readonly_violado_marca_failed(monkeypatch):
    """KPI-5, la mitad que el doc dejaba sin cablear: el worker devuelve
    `readonly_ok False` y el ORQUESTADOR tiene que marcar el item failed."""
    O = _O()
    L = _L()
    it = L.upsert_item("auditor", "branch:impl/x",
                       L.compute_input_hash("auditor", "branch:impl/x", "s"), night="N")
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: {"output_ref": "audits/x.json", "cost_tokens": 0,
                                      "readonly_ok": False})
    O.run_night("N", budget=99999)
    fila = [r for r in L.list_items(night="N") if r["id"] == it["id"]][0]
    assert fila["state"] == "failed"
    assert "read-only" in (fila["error"] or "").lower()


def test_run_night_se_niega_en_congelado(monkeypatch):
    """La Fragua no corre en deploy congelado: falla CERRADA y VISIBLE."""
    O = _O()
    import runtime_paths

    _sembrar("package", 2)
    monkeypatch.setattr(runtime_paths, "is_frozen", lambda: True)
    monkeypatch.setattr(O, "run_deterministic_item",
                        lambda item: pytest.fail("no debio procesarse nada"))
    res = O.run_night("N", budget=99999)
    assert res["stopped_reason"] == "unavailable"
    assert res["unavailable_reason_code"] == "frozen_deploy"
    assert res["unavailable_reason"], "el motivo tiene que llegar al operador"
    assert _estados() == {"pending": 2}


# ═══════════════════ ruteo de carriles deterministas ═════════════════════════

def test_run_deterministic_item_rutea_cada_carril(monkeypatch, tmp_path):
    O = _O()
    from services import night_foundry_planner as P
    from services import night_foundry_workers as W

    doc = tmp_path / "777_PLAN_X.md"
    doc.write_text("# X\n\n- **Estado:** CRITICADO v2\n", encoding="utf-8")
    monkeypatch.setattr(P, "_doc_for", lambda nn: doc)
    monkeypatch.setattr(W, "run_auditor", lambda b, base="main": {"output_ref": "audits/a.json",
                                                                 "cost_tokens": 0,
                                                                 "readonly_ok": True})
    monkeypatch.setattr(W, "build_package", lambda nn, d: {"output_ref": f"packages/{nn}.json",
                                                           "cost_tokens": 0})
    monkeypatch.setattr(W, "run_reconciler", lambda nn, d: {"plan": nn, "drift": [],
                                                            "cost_tokens": 0})
    assert O.run_deterministic_item({"lane": "auditor", "target": "branch:impl/x"})[
        "output_ref"] == "audits/a.json"
    assert O.run_deterministic_item({"lane": "package", "target": "plan:777"})[
        "output_ref"] == "packages/777.json"
    r = O.run_deterministic_item({"lane": "reconciler", "target": "plan:777"})
    assert r["output_ref"] is None and r["reconciler"]["plan"] == "777"
    with pytest.raises(ValueError):
        O.run_deterministic_item({"lane": "critic", "target": "plan:777"})
