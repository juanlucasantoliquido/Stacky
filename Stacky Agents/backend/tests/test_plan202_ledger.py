"""Plan 202 E1 — ledger durable de la Fragua Nocturna. 8 tests.

Todo corre contra `tmp_path` (monkeypatch de runtime_paths.data_dir): el ledger
NUNCA toca backend/data durante los tests.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture(autouse=True)
def _data_dir(monkeypatch, tmp_path):
    import runtime_paths

    from services import night_foundry_ledger as L

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    L.reset_inflight()
    yield tmp_path
    L.reset_inflight()


def _L():
    from services import night_foundry_ledger as L

    return L


def _ledger_lines(tmp_path):
    p = tmp_path / "night_foundry" / "ledger.jsonl"
    if not p.exists():
        return []
    return [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_upsert_crea_pending(_data_dir):
    L = _L()
    ih = L.compute_input_hash("auditor", "branch:impl/x", "abc")
    item = L.upsert_item("auditor", "branch:impl/x", ih, night="2026-07-26")
    assert item["state"] == "pending"
    assert item["lane"] == "auditor"
    assert item["attempts"] == 0
    assert item["input_hash"] == ih
    # campos EXACTOS de ENTRY_FIELDS, ni uno mas ni uno menos
    assert set(item.keys()) == set(L.ENTRY_FIELDS)
    assert len(_ledger_lines(_data_dir)) == 1


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_allowlist_descarta_claves_ajenas(_data_dir):
    L = _L()
    sucio = {k: None for k in L.ENTRY_FIELDS}
    sucio["password"] = "supersecreto"
    sucio["ado_pat"] = "tok"
    limpio = L._sanitize(sucio)
    assert "password" not in limpio and "ado_pat" not in limpio
    # y el camino real de escritura tampoco filtra
    ih = L.compute_input_hash("package", "plan:199", "sig")
    L.upsert_item("package", "plan:199", ih, night="2026-07-26")
    fila = json.loads(_ledger_lines(_data_dir)[0])
    assert set(fila.keys()) == set(L.ENTRY_FIELDS)


# ── 3 · KPI-1 ────────────────────────────────────────────────────────────────
def test_dedup_done_no_recrea(_data_dir):
    L = _L()
    ih = L.compute_input_hash("package", "plan:199", "sig")
    a = L.upsert_item("package", "plan:199", ih, night="2026-07-26")
    L.record_result(a["id"], "done", output_ref="packages/x.json", cost_tokens=0)
    b = L.upsert_item("package", "plan:199", ih, night="2026-07-27")
    assert b["state"] == "done"
    assert b["id"] == a["id"]
    assert len(_ledger_lines(_data_dir)) == 1


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_failed_reencola_hasta_max_attempts(_data_dir):
    L = _L()
    ih = L.compute_input_hash("auditor", "branch:impl/y", "tip")
    it = L.upsert_item("auditor", "branch:impl/y", ih, night="2026-07-26")
    L.claim_next()  # attempts -> 1
    L.record_result(it["id"], "failed", error="boom")
    re1 = L.upsert_item("auditor", "branch:impl/y", ih, night="2026-07-26")
    assert re1["state"] == "pending", "failed con attempts<MAX debe re-encolarse"

    # agotar los intentos
    for _ in range(L.MAX_ATTEMPTS):
        L.claim_next()
    L.record_result(it["id"], "failed", error="boom")
    re2 = L.upsert_item("auditor", "branch:impl/y", ih, night="2026-07-26")
    assert re2["state"] == "failed", "con attempts>=MAX_ATTEMPTS queda failed"
    assert len(_ledger_lines(_data_dir)) == 1


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_claim_next_orden_de_carril(_data_dir):
    L = _L()
    L.upsert_item("reconciler", "plan:150", L.compute_input_hash("reconciler", "plan:150", "s"),
                  night="2026-07-26")
    L.upsert_item("auditor", "branch:impl/z", L.compute_input_hash("auditor", "branch:impl/z", "s"),
                  night="2026-07-26")
    L.upsert_item("critic", "plan:151", L.compute_input_hash("critic", "plan:151", "s"),
                  night="2026-07-26")
    assert L.claim_next()["lane"] == "critic"
    assert L.claim_next()["lane"] == "auditor"
    assert L.claim_next()["lane"] == "reconciler"
    assert L.claim_next() is None


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_retencion_max_rows(monkeypatch, _data_dir):
    """MAX_ROWS bajado a 10 para no pagar 2000 reescrituras completas del ledger:
    lo que se prueba es la POLITICA (recortar conservando los mas nuevos)."""
    L = _L()
    monkeypatch.setattr(L, "MAX_ROWS", 10)
    for i in range(15):
        L.upsert_item("package", f"plan:{i:03d}",
                      L.compute_input_hash("package", f"plan:{i:03d}", "s"), night="2026-07-26")
    lineas = _ledger_lines(_data_dir)
    assert len(lineas) == 10
    targets = [json.loads(l)["target"] for l in lineas]
    assert targets[0] == "plan:005" and targets[-1] == "plan:014"


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_lineas_corruptas_se_saltean(_data_dir):
    L = _L()
    ih = L.compute_input_hash("package", "plan:199", "s")
    L.upsert_item("package", "plan:199", ih, night="2026-07-26")
    p = _data_dir / "night_foundry" / "ledger.jsonl"
    p.write_text(p.read_text(encoding="utf-8") + "{esto no es json\n", encoding="utf-8")
    filas = L._read_all()
    assert len(filas) == 1 and filas[0]["target"] == "plan:199"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_spent_tokens_suma_done_y_failed(_data_dir):
    L = _L()
    a = L.upsert_item("critic", "plan:1", L.compute_input_hash("critic", "plan:1", "s"), night="N")
    b = L.upsert_item("critic", "plan:2", L.compute_input_hash("critic", "plan:2", "s"), night="N")
    c = L.upsert_item("critic", "plan:3", L.compute_input_hash("critic", "plan:3", "s"), night="N")
    L.record_result(a["id"], "done", cost_tokens=500)
    L.record_result(b["id"], "failed", cost_tokens=300, error="x")
    L.record_result(c["id"], "pending")  # pending NO suma
    assert L.spent_tokens("N") == 800
    assert L.spent_tokens("otra-noche") == 0


# ── 9 · anti-re-claim (bug real hallado construyendo E1) ─────────────────────
def test_claim_next_no_devuelve_dos_veces_el_mismo_item(_data_dir):
    """`claim_next` acepta `claimed` como candidato (resume de huerfanos, KPI-4);
    sin el registro _INFLIGHT eso devolvia el MISMO item indefinidamente."""
    L = _L()
    L.upsert_item("auditor", "branch:impl/a", L.compute_input_hash("auditor", "branch:impl/a", "s"),
                  night="N")
    primero = L.claim_next()
    assert primero is not None
    assert L.claim_next() is None, "no debe re-entregar un item ya en vuelo"
    # tras el resultado vuelve a estar disponible solo si no quedo terminal
    L.record_result(primero["id"], "pending")
    assert L.claim_next()["id"] == primero["id"]


def test_resume_reclama_huerfano_de_otra_corrida(_data_dir):
    """Un `claimed` que quedo de una corrida ANTERIOR (otro proceso) si se re-clama."""
    L = _L()
    it = L.upsert_item("package", "plan:9", L.compute_input_hash("package", "plan:9", "s"), night="N")
    L.claim_next()
    L.reset_inflight()  # simula proceso nuevo: el ledger sigue con el item claimed
    otra = L.claim_next()
    assert otra is not None and otra["id"] == it["id"] and otra["attempts"] == 2


# ── 10 · lane invalido ───────────────────────────────────────────────────────
def test_lane_invalido_lanza(_data_dir):
    L = _L()
    with pytest.raises(ValueError):
        L.upsert_item("inventado", "plan:1", "hash", night="N")
