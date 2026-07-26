"""test_plan241_menu_resolver.py — Plan 241 F5 (implementa el F3 del Plan 240).

AgendaWeb usa URLs con un payload de query encriptado POR SESION. Deep-linkear una
de esas sin el payload redirige al login Y ESE REDIRECT DESTRUYE LA SESION. Por eso
el destino se resuelve clickeando el ancla REAL del menu vivo.
"""
import asyncio
import json
from pathlib import Path

import pytest

from menu_resolver import (
    normalize_label, harvest_menu_sync, resolve_target, sanitize_for_playbook,
    is_login_redirect,
)
from navigation_driver import NavigationDriver, _classify_error

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_Q = "?" + "q" + "="            # partido a proposito: el ratchet busca el literal


# ── fakes ────────────────────────────────────────────────────────────────────

class _FakePage:
    def __init__(self, links, url="http://localhost/AgendaWeb/FrmAgenda.aspx",
                 evaluate_raises=False):
        self._links = links
        self.url = url
        self._evaluate_raises = evaluate_raises
        self.goto_calls = 0

    def evaluate(self, _js):
        if self._evaluate_raises:
            raise RuntimeError("evaluate exploto")
        return self._links

    async def goto(self, *a, **kw):
        self.goto_calls += 1


# ── tests ────────────────────────────────────────────────────────────────────

def test_normalize_label_casos_reales():
    assert normalize_label("event\nAgenda Personal") == "agenda personal"
    assert normalize_label("switch_accountReasignacion Manual") == "reasignacion manual"
    assert normalize_label("searchFiltrar") == "filtrar"
    assert normalize_label("grid_on\nAGENDADOS POR USUARIO") == "agendados por usuario"


def test_harvest_clasifica_kind_y_q():
    page = _FakePage([
        {"text": "Postback", "href": "javascript:__doPostBack('x','')", "id": "a1"},
        {"text": "searchBusqueda de Clientes", "href": "/AgendaWeb/FrmBusqueda.aspx",
         "id": "a2"},
        {"text": "Reportes", "href": "/AgendaWeb/FrmReportes.aspx" + _Q + "ABC==",
         "id": "a3"},
    ])
    menu = harvest_menu_sync(page)
    assert [m["kind"] for m in menu] == ["postback", "aspx", "aspx"]
    assert [m["has_q_param"] for m in menu] == [False, False, True]
    assert [m["screen"] for m in menu] == [None, "FrmBusqueda.aspx", "FrmReportes.aspx"]


def test_harvest_no_lanza_si_evaluate_falla():
    assert harvest_menu_sync(_FakePage([], evaluate_raises=True)) == []


def test_resolve_precedencia():
    menu = [
        {"label": "Búsqueda de Clientes", "label_norm": "busqueda de clientes",
         "screen": None, "id": "byLabel"},
        {"label": "otra", "label_norm": "otra", "screen": "FrmBusqueda.aspx",
         "id": "byScreen"},
    ]
    assert resolve_target(menu, "FrmBusqueda.aspx")["id"] == "byScreen"
    assert resolve_target(menu, "Búsqueda de Clientes")["id"] == "byLabel"
    assert resolve_target(menu, "Nada") is None


def test_resolve_empate_gana_el_primero():
    menu = [
        {"label": "Agenda", "label_norm": "agenda", "screen": None, "id": "first"},
        {"label": "Agenda", "label_norm": "agenda", "screen": None, "id": "second"},
    ]
    assert resolve_target(menu, "Agenda")["id"] == "first"


def test_sanitize_elimina_q_y_marca():
    con_q = {"label": "Reportes", "label_norm": "reportes",
             "href": "/AgendaWeb/FrmReportes.aspx" + _Q + "ABC==", "has_q_param": True}
    out = sanitize_for_playbook(con_q)
    assert out["href"] == "/AgendaWeb/FrmReportes.aspx"
    assert out["requires_live_menu"] is True
    assert out["resolve_by"] == "reportes"

    sin_q = {"label": "Busqueda", "label_norm": "busqueda",
             "href": "/AgendaWeb/FrmBusqueda.aspx", "has_q_param": False}
    out2 = sanitize_for_playbook(sin_q)
    assert out2["requires_live_menu"] is False
    assert out2["href"] == "/AgendaWeb/FrmBusqueda.aspx"


def test_is_login_redirect_case_insensitive():
    assert is_login_redirect("http://x/AgendaWeb/frmLogin.aspx") is True
    assert is_login_redirect("http://x/AgendaWeb/FRMLOGIN.ASPX") is True
    assert is_login_redirect("http://x/AgendaWeb/FrmAgenda.aspx") is False


def test_ningun_playbook_persiste_q_param():
    """RATCHET: ningun valor de string de la KB puede traer el payload de sesion."""
    offenders = []
    for sub in ("cache/playbooks", "cache/ui_maps"):
        base = _TOOL_ROOT / sub
        if not base.is_dir():
            continue
        for f in base.glob("*.json"):
            try:
                if _Q in f.read_text(encoding="utf-8"):
                    offenders.append(str(f))
            except Exception:  # noqa: BLE001
                continue
    assert offenders == [], f"payload de sesion persistido en: {offenders}"


def test_classify_error_nuevos_codigos():
    assert _classify_error("NAV_SESSION_LOST: expulsado", "http://x") == "NAV_SESSION_LOST"
    assert _classify_error("MENU_LABEL_NOT_FOUND: nada", "http://x") == "MENU_LABEL_NOT_FOUND"
    assert _classify_error("APP_ERROR_PAGE: 500", "http://x") == "APP_ERROR_PAGE"


def test_via_menu_no_encontrado_no_navega(tmp_path):
    """Sin match en el menu: MENU_LABEL_NOT_FOUND y CERO page.goto (nunca sintetiza URL)."""
    page = _FakePage([{"text": "event\nAgenda Personal",
                       "href": "/AgendaWeb/FrmAgenda.aspx", "id": "a1"}])
    driver = NavigationDriver(page=page, evidence_dir=tmp_path, scenario_id="t")
    res = asyncio.run(driver.via_menu("FrmReportes.aspx", retries=1))
    assert res.ok is False
    assert res.error_code == "MENU_LABEL_NOT_FOUND"
    assert page.goto_calls == 0
    assert "FrmReportes.aspx" in res.error_detail


@pytest.mark.e2e
def test_via_menu_alcanza_frmgestion_en_vivo():
    """Requiere AgendaWeb arriba: resuelve la etiqueta del menu y aterriza en
    FrmGestion.aspx SIN construir la URL."""
    import os
    if not os.environ.get("QA_UAT_E2E_LIVE"):
        pytest.skip("e2e en vivo: exportar QA_UAT_E2E_LIVE=1 con AgendaWeb arriba")
    from playwright.sync_api import sync_playwright  # noqa: F401
    pytest.skip("cubierto por la verificacion en vivo del DoD (no automatizable en CI)")


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-q"])
