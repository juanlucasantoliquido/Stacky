"""Plan 283 F4 - El cliente de Microsoft Graph, con CERO red.

Los 11 casos corren con transporte falso. R1 (que los scope o el ingreso por
codigo funcionen en el tenant del operador) NO se puede materializar aca: es un
riesgo de RUNTIME, que se cubre con el smoke manual S1.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import ast
import json
import os
import pathlib
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402
import requests  # noqa: E402

from services.graph_client import (  # noqa: E402
    DEFAULT_TENANT,
    GRAPH_TIMEOUT_S,
    GraphApiError,
    GraphClient,
    GraphConfigError,
    _kind_for_status,
)

_MODULO = pathlib.Path(__file__).resolve().parents[1] / "services" / "graph_client.py"


class _Respuesta:
    def __init__(self, status: int, cuerpo=None, texto: str = ""):
        self.status_code = status
        self._cuerpo = cuerpo
        self.text = texto if texto else (json.dumps(cuerpo) if cuerpo is not None else "")

    def json(self):
        if self._cuerpo is None:
            raise ValueError("sin cuerpo JSON")
        return self._cuerpo


class _TransporteFalso:
    """Seam de test. Cuenta invocaciones y devuelve respuestas programadas."""

    def __init__(self, respuestas=None, excepcion=None):
        self.llamadas: list[dict] = []
        self._respuestas = list(respuestas or [])
        self._excepcion = excepcion

    def request(self, method, url, *, headers=None, params=None, data=None, timeout=None):
        self.llamadas.append({
            "method": method, "url": url, "headers": headers,
            "params": params, "data": data, "timeout": timeout,
        })
        if self._excepcion is not None:
            raise self._excepcion
        if not self._respuestas:
            return _Respuesta(200, {})
        siguiente = self._respuestas.pop(0)
        return siguiente() if callable(siguiente) else siguiente


def _cliente(transport, tmp_path=None, client_id="app-123"):
    return GraphClient(
        tenant="contoso.onmicrosoft.com",
        client_id=client_id,
        auth_path=(tmp_path / "graph_auth.json") if tmp_path else None,
        transport=transport,
    )


def test_1_el_constructor_no_hace_red():
    fake = _TransporteFalso()
    cliente = GraphClient(client_id="app-123", transport=fake)
    assert fake.llamadas == [], "el constructor hizo red"
    # Y el tenant por defecto se resuelve ACA, no en la configuracion.
    assert DEFAULT_TENANT == "common"
    assert cliente._tenant == "common"


def test_2_start_device_login_devuelve_codigo_y_direccion():
    fake = _TransporteFalso([_Respuesta(200, {
        "user_code": "ABCD-EFGH",
        "verification_uri": "https://microsoft.com/devicelogin",
        "device_code": "dc-secreto",
        "expires_in": 900,
        "interval": 5,
    })])
    salida = _cliente(fake).start_device_login()

    assert salida["user_code"] == "ABCD-EFGH"
    assert salida["verification_uri"] == "https://microsoft.com/devicelogin"
    assert salida["device_code"] == "dc-secreto"
    assert len(fake.llamadas) == 1
    assert fake.llamadas[0]["url"].endswith("/oauth2/v2.0/devicecode")

    # Sin identificador de aplicacion es un problema de CONFIGURACION, no de API.
    with pytest.raises(GraphConfigError):
        _cliente(_TransporteFalso(), client_id="").start_device_login()


def test_3_authorization_pending_no_es_error():
    fake = _TransporteFalso([_Respuesta(400, {"error": "authorization_pending"})])
    salida = _cliente(fake).poll_device_login("dc-secreto")
    assert salida["estado"] == "pending"
    assert salida["detalle"]


def test_4_el_refresh_se_guarda_cifrado(tmp_path):
    from services import secrets_store

    destino = tmp_path / "graph_auth.json"
    fake = _TransporteFalso([_Respuesta(200, {
        "refresh_token": "REFRESCO-EN-CLARO-0123456789", "access_token": "a", "expires_in": 3600,
    })])
    cliente = _cliente(fake, tmp_path=tmp_path)

    # GUARD POSITIVO, PRIMERO: el valor SI llega al payload en memoria. Sin
    # esto, el assert de ausencia de abajo pasaria contra un archivo vacio.
    payload_prueba: dict = {}
    secrets_store.set_encrypted_secret(
        payload_prueba, "refresh_token", "REFRESCO-EN-CLARO-0123456789",
        format_field="refresh_token_format",
    )
    assert payload_prueba["refresh_token"], "el cifrador no escribio nada"

    salida = cliente.poll_device_login("dc-secreto")
    assert salida["estado"] == "ok"
    assert destino.is_file(), "no se escribio el archivo de credencial"
    crudo = destino.read_bytes()
    assert len(crudo) > 20
    assert b"REFRESCO-EN-CLARO-0123456789" not in crudo, "la credencial quedo en claro"

    # Y se relee: el ciclo cierra.
    assert cliente._leer_refresh() == "REFRESCO-EN-CLARO-0123456789"


def test_5_sin_archivo_de_credencial_es_config_error(tmp_path):
    cliente = _cliente(_TransporteFalso(), tmp_path=tmp_path)
    with pytest.raises(GraphConfigError):
        cliente._access_token()
    # Y NO un GraphApiError: distinguirlos es lo que deja que la sonda diga
    # "falta configurar" en vez de "Microsoft fallo".
    try:
        cliente._access_token()
    except GraphConfigError as exc:
        assert not isinstance(exc, GraphApiError)


def _cliente_autenticado(tmp_path, respuestas):
    """Cliente con credencial ya guardada; la 1a respuesta es la renovacion."""
    from services import secrets_store

    payload: dict = {}
    secrets_store.set_encrypted_secret(
        payload, "refresh_token", "refresco", format_field="refresh_token_format"
    )
    secrets_store.write_json_file(tmp_path / "graph_auth.json", payload)
    fake = _TransporteFalso([_Respuesta(200, {"access_token": "acceso"})] + list(respuestas))
    return _cliente(fake, tmp_path=tmp_path), fake


def test_6_list_events_normaliza_las_fechas_a_naive_utc(tmp_path):
    cliente, fake = _cliente_autenticado(tmp_path, [_Respuesta(200, {"value": [
        {"id": "ev-1", "subject": "Semanal",
         "start": {"dateTime": "2026-08-03T14:00:00Z"},
         "end": {"dateTime": "2026-08-03T15:00:00Z"},
         "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/x"}},
        {"id": "ev-2", "subject": "Sin online",
         "start": {"dateTime": "2026-08-04T09:30:00.0000000"},
         "end": {"dateTime": "2026-08-04T10:00:00.0000000"}},
    ]})])

    eventos = cliente.list_events(
        desde=datetime(2026, 8, 1), hasta=datetime(2026, 8, 15)
    )
    assert len(eventos) == 2
    assert eventos[0]["start_at"] == datetime(2026, 8, 3, 14, 0, 0)
    assert eventos[0]["start_at"].tzinfo is None, "quedo con zona horaria"
    assert eventos[1]["start_at"] == datetime(2026, 8, 4, 9, 30, 0)
    # El encabezado de zona horaria viaja en la llamada de lectura.
    lectura = fake.llamadas[-1]
    assert lectura["headers"]["Prefer"] == 'outlook.timezone="UTC"'


def test_7_get_transcript_con_404_devuelve_none(tmp_path):
    cliente, _fake = _cliente_autenticado(tmp_path, [_Respuesta(404, {"error": {"code": "x"}})])
    assert cliente.get_transcript(meeting_id="reunion-1") is None

    # Y una reunion con lista vacia tambien: no hay transcripcion, no hay error.
    cliente2, _f2 = _cliente_autenticado(tmp_path, [_Respuesta(200, {"value": []})])
    assert cliente2.get_transcript(meeting_id="reunion-2") is None

    # GUARD POSITIVO: cuando SI hay, se devuelve el texto.
    cliente3, _f3 = _cliente_autenticado(tmp_path, [
        _Respuesta(200, {"value": [{"id": "t-1"}]}),
        _Respuesta(200, None, texto="WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nAna: hola\n"),
    ])
    assert "WEBVTT" in (cliente3.get_transcript(meeting_id="reunion-3") or "")


def test_8_un_401_da_graph_api_error_con_kind_auth(tmp_path):
    cliente, _fake = _cliente_autenticado(tmp_path, [_Respuesta(401, {"error": "invalid"})])
    with pytest.raises(GraphApiError) as exc:
        cliente.list_events(desde=datetime(2026, 8, 1), hasta=datetime(2026, 8, 2))
    assert exc.value.status == 401
    assert exc.value.kind == "auth"
    assert _kind_for_status(403) == "auth"
    assert _kind_for_status(404) == "not_found"
    assert _kind_for_status(500) == "server"
    assert _kind_for_status(200) == "unknown"


def test_9_un_429_da_kind_rate_limited(tmp_path):
    cliente, _fake = _cliente_autenticado(tmp_path, [_Respuesta(429, {})])
    with pytest.raises(GraphApiError) as exc:
        cliente.list_events(desde=datetime(2026, 8, 1), hasta=datetime(2026, 8, 2))
    assert exc.value.status == 429
    assert exc.value.kind == "rate_limited"
    assert _kind_for_status(429) == "rate_limited"


def test_10_cero_red_a_nivel_modulo_por_ast():
    """El modulo no dispara ninguna llamada HTTP al importarse.

    Guard positivo primero: el detector encuentra el defecto en un fuente que SI
    llama a nivel modulo.
    """
    def _llamadas_de_modulo(fuente: str) -> list[str]:
        arbol = ast.parse(fuente)
        encontradas: list[str] = []
        for nodo in arbol.body:                      # SOLO el nivel superior
            # Lo que pasa DENTRO de una funcion o de una clase no corre al
            # importar: `requests.Session()` en `__init__` es legitimo y no
            # cuenta. Por eso la poda es del nodo entero, no de cada hijo (ese
            # era el defecto de la primera version de este detector).
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            for hijo in ast.walk(nodo):
                if isinstance(hijo, ast.Call) and isinstance(hijo.func, ast.Attribute):
                    receptor = getattr(hijo.func.value, "id", "")
                    if receptor == "requests":
                        encontradas.append(hijo.func.attr)
        return encontradas

    # GUARD POSITIVO, PRIMERO.
    assert _llamadas_de_modulo("import requests\nX = requests.get('http://x')\n") == ["get"]

    assert _llamadas_de_modulo(_MODULO.read_text(encoding="utf-8")) == []


def test_11_toda_llamada_al_transporte_pasa_timeout(tmp_path):
    """(a) Por AST: ninguna llamada al transporte se olvida el `timeout=`.
    (b) En vivo: un transporte que se cuelga da `GraphApiError(kind="timeout")`,
    no una excepcion cruda que suba hasta la capa web."""
    def _sin_timeout(fuente: str) -> list[str]:
        faltantes: list[str] = []
        for nodo in ast.walk(ast.parse(fuente)):
            if not isinstance(nodo, ast.Call) or not isinstance(nodo.func, ast.Attribute):
                continue
            if nodo.func.attr not in ("get", "post", "put", "delete", "request"):
                continue
            # SOLO las llamadas al transporte: un `dict.get(...)` tambien
            # "termina en get" y contarlo daria un gate que nadie puede pasar.
            receptor = ast.unparse(nodo.func.value)
            if "_transport" not in receptor:
                continue
            if not any(kw.arg == "timeout" for kw in nodo.keywords):
                faltantes.append(f"{receptor}.{nodo.func.attr}")
        return faltantes

    # GUARD POSITIVO, PRIMERO: el detector encuentra el olvido.
    sucio = "class C:\n    def f(self):\n        self._transport.post('u', data={})\n"
    assert _sin_timeout(sucio) == ["self._transport.post"]

    assert _sin_timeout(_MODULO.read_text(encoding="utf-8")) == []
    assert GRAPH_TIMEOUT_S == 20

    # (b) El cuelgue se traduce, no se propaga crudo.
    colgado = _TransporteFalso(excepcion=requests.exceptions.Timeout("se colgo"))
    with pytest.raises(GraphApiError) as exc:
        _cliente(colgado, tmp_path=tmp_path).start_device_login()
    assert exc.value.kind == "timeout"
    assert exc.value.status == 0

    caido = _TransporteFalso(excepcion=requests.exceptions.ConnectionError("sin ruta"))
    with pytest.raises(GraphApiError) as exc2:
        _cliente(caido, tmp_path=tmp_path).start_device_login()
    assert exc2.value.kind == "network"
