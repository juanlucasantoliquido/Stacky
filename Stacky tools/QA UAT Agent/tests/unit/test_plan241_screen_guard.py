"""test_plan241_screen_guard.py — Plan 241 F0.

Un PASS en la pantalla equivocada es imposible, y el veredicto final del run lo
produce functional_verdict (no el runner).
"""
import pytest

from screen_guard import verify_screen
from functional_verdict import build_functional_verdict


# ── verify_screen ────────────────────────────────────────────────────────────

def test_pantalla_correcta_ok():
    res = verify_screen(
        {"url": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
         "title": "Busqueda de Clientes", "anchor_present": True},
        "FrmBusqueda.aspx",
    )
    assert res["ok"] is True
    assert res["code"] == ""


def test_pantalla_equivocada():
    """Caso REAL del ADO-366: el criterio es de FrmDetalleClie y el run aterrizo
    en FrmAgenda => PASS en la pantalla equivocada."""
    res = verify_screen(
        {"url": "http://localhost:35017/AgendaWeb/FrmAgenda.aspx",
         "title": "Agenda Personal", "anchor_present": True},
        "FrmDetalleClie.aspx",
    )
    assert res["ok"] is False
    assert res["code"] == "NAV_WRONG_SCREEN"
    detail = res["detail"].lower()
    assert "frmdetalleclie" in detail
    assert "frmagenda" in detail


def test_login_redirect_es_session_lost():
    res = verify_screen(
        {"url": "http://localhost:35017/AgendaWeb/frmLogin.aspx",
         "title": "Login", "anchor_present": None},
        "FrmBusqueda.aspx",
    )
    assert res["ok"] is False
    assert res["code"] == "NAV_SESSION_LOST"


def test_url_ok_pero_sin_ancla_es_wrong_screen():
    res = verify_screen(
        {"url": "http://localhost:35017/AgendaWeb/FrmBusqueda.aspx",
         "title": "Busqueda", "anchor_present": False},
        "FrmBusqueda.aspx",
    )
    assert res["ok"] is False
    assert res["code"] == "NAV_WRONG_SCREEN"


def test_expected_vacio_no_bloquea():
    for expected in ("", None):
        res = verify_screen({"url": "http://x/FrmAgenda.aspx"}, expected)
        assert res["ok"] is True, expected
        assert res["code"] == ""


# ── gate terminal del veredicto ──────────────────────────────────────────────

def test_verdict_final_sale_del_funcional():
    """Runner PASS + 0 criterios verificados => MIXED/NO_FUNCTIONAL_ASSERTION."""
    fv = build_functional_verdict([], {"verdict": "PASS", "category": None})
    assert fv["verdict"] == "MIXED"
    assert fv["reason"] == "NO_FUNCTIONAL_ASSERTION"
    assert fv["verified"] == 0


def test_verdict_pass_requiere_verified():
    criteria = [
        {"id": "P01", "status": "verified",
         "discrimination": {"proven": True, "negative_control": "20"}},
        {"id": "P02", "status": "verified",
         "discrimination": {"proven": True, "negative_control": "0"}},
    ]
    fv = build_functional_verdict(criteria, {"verdict": "PASS", "category": None})
    assert fv["verdict"] == "PASS"
    assert fv["verified"] == 2
    assert fv["violated"] == 0


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
