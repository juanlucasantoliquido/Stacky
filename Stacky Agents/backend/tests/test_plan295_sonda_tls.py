"""Plan 295 F5 — la sonda de configuración habla el TLS del proyecto.

POR QUÉ. `services/gitlab_setup_check.py:32-33` usaba `requests.get(...)` pelado y
NACE ROTO contra un GitLab self-hosted con CA interna: `app.py:26` llama
`truststore.inject_into_ssl()`, que reemplaza `ssl.SSLContext` para TODO el proceso
(ver el docstring de `services/tls_openssl_context.py:3-13`). El síntoma MIENTE:
`chk-instancia = fail` con "No se pudo llegar a esa dirección" -- o sea culpa a la
RED -- mientras el sync real funciona perfecto porque el cliente sí monta el
adaptador OpenSSL.

NINGÚN CASO TOCA LA RED: todos monkeypatchean `requests.Session.get` / `.mount`.
Tampoco se usa BD ni `create_app()`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import requests

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import gitlab_setup_check as gsc  # noqa: E402

_BASE = "https://gitlab.interno.empresa"
_IDS_ESPERADOS = {
    "chk-flag", "chk-tls", "chk-instancia", "chk-token", "chk-scope", "chk-proyecto",
}


def _pem_real() -> str:
    """Un PEM que OpenSSL puede cargar de verdad (no un placeholder): así el test
    ejercita `crear_contexto_openssl` real y no una versión parcheada."""
    import certifi

    return certifi.where()


class _RespuestaFalsa:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _sin_red(monkeypatch, *, get):
    """Sustituye Session.get y registra los mount() del adaptador OpenSSL.

    Se FILTRA por tipo a propósito: `requests.Session.__init__` monta sus dos
    adaptadores por defecto ("http://" y "https://") antes de que corra nada de
    este plan. Sin el filtro, `montados[0]` sería siempre el default y el assert
    de la fase pasaría o fallaría por una razón ajena.
    """
    montados: list[tuple] = []
    original_mount = requests.Session.mount

    def _mount(self, prefijo, adaptador):
        if type(adaptador).__name__ == "_AdaptadorOpenSSL":
            montados.append((prefijo, adaptador))
        return original_mount(self, prefijo, adaptador)

    monkeypatch.setattr(requests.Session, "mount", _mount)
    monkeypatch.setattr(requests.Session, "get", get)
    return montados


def _por_id(checks: list[dict], cid: str) -> dict:
    encontrados = [c for c in checks if c["id"] == cid]
    assert encontrados, (
        f"no hay ningún resultado con id {cid!r} "
        f"(ids: {', '.join(c['id'] for c in checks)})"
    )
    return encontrados[0]


# ------------------------------------------------------------------ casos ---
def test_1_ssl_error_da_chk_tls_fail_y_habla_de_certificado(monkeypatch):
    def _get(self, url, **kw):
        raise requests.exceptions.SSLError("certificate verify failed")

    _sin_red(monkeypatch, get=_get)
    checks = gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True)
    tls = _por_id(checks, "chk-tls")
    assert tls["status"] == "fail"
    assert "certificado" in tls["message"].lower()


def test_2_el_mensaje_no_dice_que_no_se_pudo_llegar(monkeypatch):
    """La mentira de hoy: un cert que no cierra salía como problema de RED."""
    def _get(self, url, **kw):
        raise requests.exceptions.SSLError("certificate verify failed")

    _sin_red(monkeypatch, get=_get)
    checks = gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True)
    assert "no se pudo llegar" not in _por_id(checks, "chk-tls")["message"].lower()


def test_3_con_ssl_error_los_otros_cuatro_quedan_unknown(monkeypatch):
    def _get(self, url, **kw):
        raise requests.exceptions.SSLError("certificate verify failed")

    _sin_red(monkeypatch, get=_get)
    checks = gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True)
    for cid in ("chk-instancia", "chk-token", "chk-scope", "chk-proyecto"):
        assert _por_id(checks, cid)["status"] == "unknown", cid


def test_4_el_ca_bundle_llega_hasta_el_mount(monkeypatch):
    """EL caso que prueba que la fase hizo algo. Los demás prueban que no rompió."""
    def _get(self, url, **kw):
        return _RespuestaFalsa(200, {"username": "juan", "scopes": ["api"]})

    montados = _sin_red(monkeypatch, get=_get)
    gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True, ca_bundle=_pem_real())
    assert montados, "no se montó ningún adaptador: el ca_bundle nunca llegó"
    prefijo, adaptador = montados[0]
    assert prefijo == _BASE, f"se montó para {prefijo!r}, no para la base del proyecto"
    assert type(adaptador).__name__ == "_AdaptadorOpenSSL", type(adaptador).__name__


def test_5_bundle_inexistente_da_fail_sin_tocar_la_red(monkeypatch, tmp_path):
    def _get(self, url, **kw):
        raise AssertionError("no debió llamarse: el bundle declarado no se pudo leer")

    _sin_red(monkeypatch, get=_get)
    inexistente = str(tmp_path / "no-existe.pem")
    checks = gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True, ca_bundle=inexistente)
    assert _por_id(checks, "chk-tls")["status"] == "fail"
    assert len(checks) == 6


def test_6_camino_feliz_da_chk_tls_ok(monkeypatch):
    def _get(self, url, **kw):
        return _RespuestaFalsa(200, {"username": "juan", "scopes": ["api"],
                                     "name_with_namespace": "grupo / proy"})

    _sin_red(monkeypatch, get=_get)
    checks = gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True)
    tls = _por_id(checks, "chk-tls")
    assert tls["status"] == "ok"
    assert "cerró" in tls["message"]


@pytest.mark.parametrize(
    "escenario",
    ["url_invalida", "redirige", "transporte_muerto", "sin_token", "sin_proyecto", "completo"],
)
def test_7_los_seis_resultados_en_los_seis_caminos_de_salida(monkeypatch, escenario):
    """[v2, C11] El docstring de run_gitlab_checks exige la MISMA cantidad de
    resultados en TODOS los caminos: la UI pinta la lista que recibe. Son SEIS
    caminos (`:68`, `:88`, `:98`, `:105`, `:151` y el `return out` FINAL), no
    cuatro ni cinco. Parchear 5 de 6 deja una lista corta sin error visible."""
    base, proyecto, token = _BASE, "grupo/proy", "tok"

    if escenario == "url_invalida":
        base = "gitlab.interno.empresa"          # sin esquema
        def _get(self, url, **kw):
            raise AssertionError("no debió tocar la red")
    elif escenario == "redirige":
        def _get(self, url, **kw):
            return _RespuestaFalsa(302)
    elif escenario == "transporte_muerto":
        def _get(self, url, **kw):
            raise requests.exceptions.ConnectionError("host caído")
    elif escenario == "sin_token":
        token = ""
        def _get(self, url, **kw):
            return _RespuestaFalsa(200, {})
    elif escenario == "sin_proyecto":
        proyecto = ""
        def _get(self, url, **kw):
            return _RespuestaFalsa(200, {"username": "juan", "scopes": ["api"]})
    else:
        def _get(self, url, **kw):
            return _RespuestaFalsa(200, {"username": "juan", "scopes": ["api"],
                                         "name_with_namespace": "grupo / proy"})

    _sin_red(monkeypatch, get=_get)
    checks = gsc.run_gitlab_checks(base, proyecto, token, True)
    assert len(checks) == 6, f"{escenario}: {len(checks)} resultados -> {[c['id'] for c in checks]}"
    assert {c["id"] for c in checks} == _IDS_ESPERADOS, escenario


def test_8_allow_redirects_false_se_conserva(monkeypatch):
    """Un 30x reenviaría el header PRIVATE-TOKEN a otro host."""
    vistos: list[dict] = []

    def _get(self, url, **kw):
        vistos.append(kw)
        return _RespuestaFalsa(200, {"username": "juan", "scopes": ["api"],
                                     "name_with_namespace": "grupo / proy"})

    _sin_red(monkeypatch, get=_get)
    gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True)
    assert vistos, "no se hizo ningún GET"
    for kw in vistos:
        assert kw["allow_redirects"] is False


def test_9_el_bundle_declarado_por_ENTORNO_tambien_llega_al_mount(monkeypatch):
    """[v2, C10] `resolver_ca_bundle` acepta el bundle por parámetro O por
    STACKY_GITLAB_CA_BUNDLE / REQUESTS_CA_BUNDLE (tls_pinning.py:64-91). Si la
    sonda salteara ese resolvedor, hablaría un TLS DISTINTO del que usa el sync
    cuando el operador configuró el certificado por entorno."""
    def _get(self, url, **kw):
        return _RespuestaFalsa(200, {"username": "juan", "scopes": ["api"],
                                     "name_with_namespace": "grupo / proy"})

    montados = _sin_red(monkeypatch, get=_get)
    monkeypatch.setenv("STACKY_GITLAB_CA_BUNDLE", _pem_real())
    # campo del proyecto VACÍO a propósito: el bundle sólo puede venir del entorno.
    gsc.run_gitlab_checks(_BASE, "grupo/proy", "tok", True, ca_bundle=None)
    assert montados, (
        "con el campo vacío y STACKY_GITLAB_CA_BUNDLE puesto, el adaptador NO se montó: "
        "la sonda saltea resolver_ca_bundle y habla otro TLS que el sync"
    )
    assert montados[0][0] == _BASE
