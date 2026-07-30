"""Plan 262 F4 — route_allowlist: rutas permitidas, ruta segura y validacion de la URL.

20 casos. El par derivada-permisiva / configurada-estricta ES el gate: una
implementacion siempre estricta convierte fallos funcionales reales en ROUTE_ERROR
reintentable (= falsos verdes, INV-1); una siempre permisiva no valida nada.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import route_allowlist as ra
from navigation_driver import CHILD_SCREENS

_TOOL_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PY = _TOOL_ROOT / "route_allowlist.py"

_BASE = "http://localhost:35017/AgendaWeb/"


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    monkeypatch.setenv("AGENDA_WEB_BASE_URL", _BASE)
    monkeypatch.delenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", raising=False)
    monkeypatch.delenv("STACKY_QA_UAT_SAFE_ROUTE", raising=False)


# ── Derivacion de la allowlist ────────────────────────────────────────────────

def test_allowlist_derivada_incluye_child_screens():
    rutas, _ = ra.effective_allowlist()
    faltantes = sorted(s for s in CHILD_SCREENS if s.lower() not in {r.lower() for r in rutas})
    assert faltantes == [], f"la derivada no incluye estas pantallas hijas: {faltantes}"


def test_allowlist_derivada_incluye_login_path():
    rutas, _ = ra.effective_allowlist()
    assert "frmlogin.aspx" in {r.lower() for r in rutas}


def test_allowlist_configurada_reemplaza_la_derivada(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmUno.aspx,FrmDos.aspx")
    rutas, _ = ra.effective_allowlist()
    bajas = {r.lower() for r in rutas}
    assert bajas == {"frmuno.aspx", "frmdos.aspx"}


def test_allowlist_configurada_auto_incluye_la_ruta_segura(monkeypatch):
    """Una ruta segura fuera de la allowlist es un bucle garantizado."""
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmUno.aspx")
    monkeypatch.setenv("STACKY_QA_UAT_SAFE_ROUTE", "FrmSegura.aspx")
    rutas, _ = ra.effective_allowlist()
    assert "frmsegura.aspx" in {r.lower() for r in rutas}


def test_source_es_derived_sin_config():
    assert ra.effective_allowlist()[1] == "derived"


def test_source_es_configured_con_config(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmUno.aspx")
    assert ra.effective_allowlist()[1] == "configured"


# ── Normalizacion ─────────────────────────────────────────────────────────────

def test_ruta_relativa_normaliza():
    assert ra.normalize_route("FrmBusqueda.aspx") == "FrmBusqueda.aspx"
    assert ra.normalize_route("./FrmBusqueda.aspx") == "FrmBusqueda.aspx"


def test_ruta_con_slash_inicial_normaliza():
    assert ra.normalize_route("/AgendaWeb/FrmBusqueda.aspx") == "FrmBusqueda.aspx"


def test_ruta_absoluta_de_la_base_normaliza():
    assert ra.normalize_route(_BASE + "FrmBusqueda.aspx") == "FrmBusqueda.aspx"


def test_query_y_fragmento_se_descartan():
    """La allowlist es de RUTAS, no de parametros."""
    assert ra.normalize_route("FrmDetalleClie.aspx?id=42#tab2") == "FrmDetalleClie.aspx"


def test_case_insensitive():
    """IIS no distingue mayusculas en el path."""
    v = ra.is_allowed("frmlogin.aspx")
    assert v.allowed is True, v.reason


# ── Rechazos ──────────────────────────────────────────────────────────────────

def test_host_ajeno_no_permitido():
    v = ra.is_allowed("http://otro:8080/x.aspx")
    assert v.allowed is False
    assert v.reason == "foreign_host"


def test_path_base_ajeno_no_permitido():
    v = ra.is_allowed("http://localhost:35017/OtraApp/x.aspx")
    assert v.allowed is False
    assert v.reason == "outside_base_path"


def test_vacia_es_unparseable():
    v = ra.is_allowed("")
    assert v.allowed is False
    assert v.reason == "unparseable"


def test_basura_no_lanza():
    for basura in ("::::", None, "   ", "?????"):
        v = ra.is_allowed(basura)
        assert v.allowed is False, f"{basura!r} no deberia estar permitida"
        assert v.reason == "unparseable", f"{basura!r} dio {v.reason}"


# ── EL GATE: permisiva derivada vs estricta configurada ───────────────────────

def test_derivada_es_permisiva_con_aspx_desconocido():
    """Rechazar rutas legitimas convertiria fallos funcionales en ROUTE_ERROR
    reintentable, o sea falsos verdes. INV-1 lo prohibe."""
    v = ra.is_allowed("FrmPantallaNuevaQueNadieDeclaro.aspx")
    assert v.allowed is True
    assert v.reason == "in_allowlist"
    assert v.source == "derived"


def test_configurada_es_estricta_con_aspx_desconocido(monkeypatch):
    monkeypatch.setenv("STACKY_QA_UAT_ROUTE_ALLOWLIST", "FrmUno.aspx,FrmDos.aspx")
    v = ra.is_allowed("FrmPantallaNuevaQueNadieDeclaro.aspx")
    assert v.allowed is False
    assert v.reason == "not_in_allowlist"
    assert v.source == "configured"


# ── Ruta segura ───────────────────────────────────────────────────────────────

def test_safe_route_vacia_es_la_base():
    """Siempre hay una ruta segura valida."""
    assert ra.safe_route_url() == _BASE


def test_safe_route_child_screen_se_detecta(monkeypatch):
    """Un goto() a una pantalla hija es NAV_DEVIATION garantizado."""
    monkeypatch.setenv("STACKY_QA_UAT_SAFE_ROUTE", "FrmDetalleClie.aspx")
    assert ra.is_child_screen("FrmDetalleClie.aspx") is True
    assert ra.is_child_screen("FrmBusqueda.aspx") is False


def test_child_screens_no_se_duplican():
    """El modulo NO define su propia copia: delega en navigation_driver."""
    texto = _MODULE_PY.read_text(encoding="utf-8")
    assert "FrmDetalleClie.aspx" not in texto, (
        "route_allowlist copio la lista de pantallas hijas en vez de importarla"
    )
