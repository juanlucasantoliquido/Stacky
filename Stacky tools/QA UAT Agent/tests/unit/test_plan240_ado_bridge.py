"""Tests del bridge ADO solo-lectura — Plan 240 F5 (+ C11, C14, C16)."""
from pathlib import Path

import stacky_ado_bridge as bridge
import uat_ticket_reader as reader
from stacky_ado_bridge import _BACKEND, _READ_ONLY_METHODS, _WORK_ITEM_FIELDS


def test_backend_path_resuelto():
    assert str(_BACKEND).replace("\\", "/").endswith("Stacky Agents/backend")
    assert _BACKEND.is_dir(), f"no existe: {_BACKEND}"


def test_bridge_available_true_aqui():
    assert bridge.bridge_available() is True


def test_bridge_solo_lectura():
    """Guardian de HITL: ningun metodo de escritura, ni en el set ni en el texto."""
    assert _READ_ONLY_METHODS == {"get_work_item", "fetch_comments", "fetch_attachments"}
    src = Path(bridge.__file__).read_text(encoding="utf-8")
    # (C11) nombres construidos por concatenacion para no introducirlos como
    # literales en este archivo y colisionar con el mismo gate.
    forbidden = ["create_" + "work_item", "post_" + "comment",
                 "update_work_item_" + "state", "upload_" + "attachment"]
    hits = [f for f in forbidden if f in src]
    assert hits == [], f"el bridge menciona metodos de escritura: {hits}"


def test_campos_explicitos_incluyen_description():
    """C14: sin System.Description el veredicto funcional nace muerto."""
    assert "System.Description" in _WORK_ITEM_FIELDS
    assert "System.Title" in _WORK_ITEM_FIELDS


def test_fetch_work_item_shape(monkeypatch):
    captured = {}

    class _FakeClient:
        def get_work_item(self, ado_id, fields=None):
            captured["fields"] = fields
            return {"id": ado_id, "fields": {"System.Title": "T", "System.Description": "D"}}

    monkeypatch.setattr(bridge, "_client", lambda: _FakeClient())
    res = bridge.fetch_work_item(367)
    assert res["ok"] is True
    assert res["source"] == "stacky_dpapi"
    assert res["work_item"]["id"] == 367
    # C14: debe pasar la lista explicita, jamas None
    assert captured["fields"] == _WORK_ITEM_FIELDS


def test_fetch_no_lanza_si_ado_falla(monkeypatch):
    class _Boom:
        def get_work_item(self, *a, **kw):
            raise RuntimeError("ado caido")

    monkeypatch.setattr(bridge, "_client", lambda: _Boom())
    res = bridge.fetch_work_item(1)
    assert res["ok"] is False
    assert res["error"] == "RuntimeError"
    assert "ado caido" in res["message"]


def test_reader_usa_bridge_primero(monkeypatch):
    calls = []
    monkeypatch.setattr(reader, "_ado_run", lambda *a, **kw: calls.append(a) or {"ok": True})
    monkeypatch.setattr(bridge, "bridge_available", lambda: True)
    monkeypatch.setattr(
        bridge, "fetch_work_item",
        lambda tid: {"ok": True, "work_item": {"id": tid}, "source": "stacky_dpapi"},
    )
    monkeypatch.setenv("STACKY_QA_UAT_ADO_BRIDGE_ENABLED", "true")
    out = reader._ado_get(Path("ado.py"), 367)
    assert out["source"] == "stacky_dpapi"
    assert calls == [], "no debia tocar el CLI legacy"


def test_reader_cae_al_cli_si_bridge_no_disponible(monkeypatch):
    calls = []

    def fake_run(ado_path, args):
        calls.append(args)
        return {"ok": True, "work_item": {"id": 367}}

    monkeypatch.setattr(reader, "_ado_run", fake_run)
    monkeypatch.setattr(bridge, "bridge_available", lambda: False)
    monkeypatch.setenv("STACKY_QA_UAT_ADO_BRIDGE_ENABLED", "true")
    out = reader._ado_get(Path("ado.py"), 367)
    assert len(calls) == 1
    assert out["source"] == "ado_cli"


def test_reader_flag_off_usa_cli(monkeypatch):
    calls = []
    monkeypatch.setattr(reader, "_ado_run",
                        lambda ap, args: calls.append(args) or {"ok": True})

    def _boom():
        raise AssertionError("no debia consultar el bridge con la flag OFF")

    monkeypatch.setattr(bridge, "bridge_available", _boom)
    monkeypatch.setenv("STACKY_QA_UAT_ADO_BRIDGE_ENABLED", "false")
    out = reader._ado_get(Path("ado.py"), 367)
    assert len(calls) == 1
    assert out["source"] == "ado_cli"
