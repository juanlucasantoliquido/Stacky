"""tests/test_plan276_client_limits.py — Plan 276 F9 (los P2 del cliente).

P2-1: el techo de páginas (per_page=100 x page_cap=40 = 4.000 ítems) truncaba el
listado EN SILENCIO. El operador veía una lista incompleta sin ninguna señal, y el
gate de visibilidad de F12 daría "no vacío pero mentiroso".

P2-2: un dict con HTTP 200 que no es un ítem (un `{"message": ...}`) se appendeaba
como issue FANTASMA y llegaba al grafo.

P2-3: `Retry-After` sin clamp. Un servidor que responde `86400` colgaba el worker
un día entero.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import gitlab_client as gl   # noqa: E402


class _Resp:
    def __init__(self, body, headers=None, status=200):
        self._body = body
        self.status_code = status
        self.ok = 200 <= status < 400
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.content = b"{}"

    def json(self):
        return self._body

    @property
    def text(self):
        return "x"


@pytest.fixture()
def cliente(monkeypatch):
    monkeypatch.setenv("GITLAB_TOKEN", "dummy")
    monkeypatch.delenv("STACKY_GITLAB_CA_BUNDLE", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    return gl.GitLabClient(base_url="https://gl.interno", project="g/p")


# ── P2-1: el techo avisa ──────────────────────────────────────────────────────

def test_se_avisa_al_llegar_al_techo_de_paginas(cliente, caplog):
    """EL GATE CONTRA EL DEFECTO: hoy se trunca sin decir nada."""
    # X-Next-Page SIEMPRE presente ⇒ el `while` sale por el cap, no por fin de datos.
    def _fake(self, *a, **k):
        return _Resp([{"iid": 1}], {"X-Next-Page": "99"})

    with patch("requests.Session.request", _fake), caplog.at_level("WARNING"):
        cliente._request_paginated("/issues", page_cap=3)

    mensajes = [r.getMessage() for r in caplog.records]
    assert any("TRUNCADO" in m for m in mensajes), f"se truncó en silencio: {mensajes}"
    assert any("techo de 3 páginas" in m for m in mensajes), mensajes


def test_no_se_avisa_si_no_se_llego_al_techo(cliente, caplog):
    """Anti-ruido: sin este caso, el warning se emitiría siempre y dejaría de
    significar algo."""
    def _fake(self, *a, **k):
        return _Resp([{"iid": 1}], {"X-Next-Page": ""})

    with patch("requests.Session.request", _fake), caplog.at_level("WARNING"):
        cliente._request_paginated("/issues", page_cap=40)

    assert not any("TRUNCADO" in r.getMessage() for r in caplog.records), (
        f"warning espurio: {[r.getMessage() for r in caplog.records]}"
    )


# ── P2-2: el issue fantasma ───────────────────────────────────────────────────

def test_el_dict_sin_id_ni_iid_se_descarta(cliente, caplog):
    def _fake(self, *a, **k):
        return _Resp({"message": "403 Forbidden"}, {"X-Next-Page": ""})

    with patch("requests.Session.request", _fake), caplog.at_level("WARNING"):
        res = cliente._request_paginated("/issues")

    assert res == [], f"se appendeó un issue fantasma: {res}"
    assert any("sin 'id' ni 'iid'" in r.getMessage() for r in caplog.records)


def test_el_dict_con_id_se_conserva(cliente):
    """Anti-celo: un ítem legítimo devuelto como dict suelto NO se descarta."""
    def _fake(self, *a, **k):
        return _Resp({"id": 7, "iid": 3, "title": "t"}, {"X-Next-Page": ""})

    with patch("requests.Session.request", _fake):
        res = cliente._request_paginated("/issues")

    assert len(res) == 1 and res[0]["id"] == 7, res


# ── P2-3: el clamp del Retry-After ────────────────────────────────────────────

def test_retry_after_de_un_dia_se_recorta_a_30s(cliente, caplog):
    """EL GATE: `86400` colgaba el worker 24 horas."""
    esperas: list = []
    llamadas = [0]

    def _fake(self, *a, **k):
        llamadas[0] += 1
        if llamadas[0] == 1:
            return _Resp({"message": "rate"}, {"Retry-After": "86400"}, status=429)
        return _Resp({"id": 1}, {})

    with patch("requests.Session.request", _fake), \
         patch("time.sleep", lambda s: esperas.append(s)), \
         caplog.at_level("WARNING"):
        cliente._request("GET", "/projects/1")

    assert esperas and esperas[0] <= 30.0, f"esperas={esperas}"
    assert any("se recorta" in r.getMessage() for r in caplog.records), (
        f"se recortó sin avisar: {[r.getMessage() for r in caplog.records]}"
    )


def test_retry_after_razonable_se_respeta_tal_cual(cliente):
    """Anti-celo: no se rompe el backoff legítimo del servidor."""
    esperas: list = []
    llamadas = [0]

    def _fake(self, *a, **k):
        llamadas[0] += 1
        if llamadas[0] == 1:
            return _Resp({"message": "rate"}, {"Retry-After": "2"}, status=429)
        return _Resp({"id": 1}, {})

    with patch("requests.Session.request", _fake), \
         patch("time.sleep", lambda s: esperas.append(s)):
        cliente._request("GET", "/projects/1")

    assert esperas == [2.0], f"esperas={esperas}"
