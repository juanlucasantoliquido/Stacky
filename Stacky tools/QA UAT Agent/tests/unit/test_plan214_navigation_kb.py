"""Plan 214 F1 — inventario determinista de la KB de navegación + curador de playbooks.

Contrato probado:
  navigation_kb.load_contract_screens / kb_inventory  → puros, sin red, nunca lanzan.
  playbook_curator.validate_playbook / curate         → validan ANTES de promover.

Comando:
  cd "N:\\GIT\\RS\\STACKY\\Stacky\\Stacky tools\\QA UAT Agent"
  & "..\\..\\Stacky Agents\\backend\\.venv\\Scripts\\python.exe" -m pytest tests\\unit\\test_plan214_navigation_kb.py -q
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import navigation_kb
import playbook_curator


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_root(tmp_path: Path, contracts: str | None = None,
               ui_maps: list[str] | None = None,
               playbooks: dict[str, dict] | None = None) -> Path:
    if contracts is not None:
        (tmp_path / "navigation_contracts.yml").write_text(contracts, encoding="utf-8")
    for name in (ui_maps or []):
        d = tmp_path / "cache" / "ui_maps"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{name}.json").write_text("{}", encoding="utf-8")
    for slug, body in (playbooks or {}).items():
        d = tmp_path / "cache" / "playbooks"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{slug}.json").write_text(json.dumps(body), encoding="utf-8")
    return tmp_path


def _valid_playbook() -> dict:
    """Playbook con la forma que REALMENTE emite session_to_playbook.run()."""
    return {
        "schema_version": "playbook/1.0",
        "tool_version": "test",
        "goal_slug": "alta_obligacion",
        "goal_label": "alta de obligacion",
        "recorded_at": "2026-07-26T00:00:00Z",
        "session_source": "evidence/recordings/x/session.json",
        "entry_screen": "FrmAgenda.aspx",
        "target_screen": "FrmDetalleClie.aspx",
        "navigation_path": [],
        "navigation_steps": [{"kind": "menu", "target": "FrmBusqueda.aspx"}],
        "action_steps": [{"accion": "click", "target": "btnGuardar"}],
        "parameterizable_fields": {},
    }


# ── navigation_kb.kb_inventory ────────────────────────────────────────────────

def test_inventory_vacio(tmp_path):
    inv = navigation_kb.kb_inventory(root=tmp_path)
    assert inv["ok"] is True
    assert inv["screens_declared"] == []
    assert inv["ui_maps"] == []
    assert inv["playbooks"] == []
    assert inv["playbooks_total"] == 0
    assert inv["coverage_pct"] == 0.0


def test_inventory_cruza_bien(tmp_path):
    root = _make_root(
        tmp_path,
        contracts="_meta:\n  v: 1\nA.aspx:\n  screen_type: list\nB.aspx:\n  screen_type: detail\n",
        ui_maps=["A.aspx"],
        playbooks={"p1": _valid_playbook()},
    )
    inv = navigation_kb.kb_inventory(root=root)
    assert inv["screens_declared"] == ["A.aspx", "B.aspx"]
    assert inv["missing_ui_maps"] == ["B.aspx"]
    assert inv["coverage_pct"] == 50.0
    assert inv["playbooks_total"] == 1
    # `_meta` NO es una pantalla: el filtro es por sufijo .aspx
    assert "_meta" not in inv["screens_declared"]


def test_yaml_corrupto_no_lanza(tmp_path):
    (tmp_path / "navigation_contracts.yml").write_text(
        "a: [1, 2\n  b: : : \n\t\x00basura", encoding="utf-8")
    inv = navigation_kb.kb_inventory(root=tmp_path)
    assert inv["ok"] is True
    assert inv["screens_declared"] == []
    assert inv["coverage_pct"] == 0.0


def test_inventory_del_arbol_real_no_lanza():
    """Control anti-inerte: el inventario corre contra la KB REAL del tool."""
    inv = navigation_kb.kb_inventory()
    assert inv["ok"] is True
    assert len(inv["screens_declared"]) >= 5
    assert inv["playbooks_total"] >= 1
    assert 0.0 <= inv["coverage_pct"] <= 100.0


# ── playbook_curator.validate_playbook ────────────────────────────────────────

def test_curator_valida_required(tmp_path):
    """Un playbook al que le falta una key portante se RECHAZA y se renombra."""
    bad = _valid_playbook()
    del bad["navigation_steps"]
    pb = tmp_path / "roto.json"
    pb.write_text(json.dumps(bad), encoding="utf-8")

    res = playbook_curator.validate_playbook_file(pb)

    assert res["ok"] is False
    assert res["error"] == "playbook_schema_invalid"
    assert "navigation_steps" in res["missing"]
    assert not pb.exists()
    assert (tmp_path / "roto.rejected.json").exists()


def test_curator_no_rechaza_los_playbooks_reales():
    """Anti-destrucción (bug del plan): el curador NO debe rechazar la KB viva.

    El schema declara `playbook_id` y `arrival_assertions` como required, pero
    session_to_playbook.run() NUNCA los emite y ninguno de los playbooks del
    árbol los tiene. Validar por el `required` crudo del schema renombraría el
    100% de la KB a `.rejected.json`. El curador valida el contrato EFECTIVO del
    productor y reporta la diferencia como `schema_drift`, sin destruir nada.
    """
    real = sorted((playbook_curator._TOOL_ROOT / "cache" / "playbooks").glob("*.json"))
    assert real, "la KB real no puede estar vacía para este control"
    for path in real:
        data = json.loads(path.read_text(encoding="utf-8"))
        res = playbook_curator.validate_playbook(data)
        assert res["ok"] is True, f"{path.name} rechazado: {res}"
        # y la deriva contra el schema queda REPORTADA, no silenciada
        assert "playbook_id" in res["schema_drift"]
        assert "arrival_assertions" in res["schema_drift"]


def test_curator_dry_run_no_escribe(tmp_path, monkeypatch):
    """dry_run=True no deja ningún archivo nuevo en cache/playbooks/."""
    out_dir = tmp_path / "cache" / "playbooks"
    out_dir.mkdir(parents=True)

    calls = {}

    def _fake_run(session_dir, dry_run=False, verbose=False):
        calls["dry_run"] = dry_run
        return {"ok": True, "dry_run": dry_run,
                "playbook_path": str(out_dir / "alta_obligacion.json"),
                "goal_slug": "alta_obligacion"}

    monkeypatch.setattr(playbook_curator.session_to_playbook, "run", _fake_run)

    res = playbook_curator.curate(tmp_path / "sesion", dry_run=True)

    assert res["ok"] is True
    assert res["dry_run"] is True
    assert res["validated"] is False
    assert calls["dry_run"] is True
    assert list(out_dir.glob("*.json")) == []


def test_curator_promueve_playbook_valido(tmp_path, monkeypatch):
    """Camino feliz completo: run() escribe, el curador valida y confirma."""
    out_dir = tmp_path / "cache" / "playbooks"
    out_dir.mkdir(parents=True)
    written = out_dir / "alta_obligacion.json"
    written.write_text(json.dumps(_valid_playbook()), encoding="utf-8")

    monkeypatch.setattr(
        playbook_curator.session_to_playbook, "run",
        lambda session_dir, dry_run=False, verbose=False: {
            "ok": True, "playbook_path": str(written), "goal_slug": "alta_obligacion"},
    )

    res = playbook_curator.curate(tmp_path / "sesion", dry_run=False)

    assert res["ok"] is True
    assert res["validated"] is True
    assert Path(res["playbook_path"]) == written
    assert written.exists()


def test_curator_propaga_error_del_conversor(tmp_path, monkeypatch):
    monkeypatch.setattr(
        playbook_curator.session_to_playbook, "run",
        lambda session_dir, dry_run=False, verbose=False: {
            "ok": False, "error": "session_not_found", "message": "no hay session.json"},
    )
    res = playbook_curator.curate(tmp_path / "sesion", dry_run=False)
    assert res["ok"] is False
    assert res["error"] == "session_not_found"
