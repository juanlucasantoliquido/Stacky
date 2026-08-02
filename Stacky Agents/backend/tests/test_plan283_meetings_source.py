"""Plan 283 F5 - Dos fuentes, un contrato, y la sonda de tres sub-veredictos.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import ast
import os
import pathlib
from datetime import datetime

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

from services.graph_client import GraphApiError  # noqa: E402
from services.meetings_source import (  # noqa: E402
    MeetingRecord,
    from_graph_event,
    from_manual,
    list_upcoming,
    probe_graph,
)

_SERVICES = pathlib.Path(__file__).resolve().parents[1] / "services"

EVENTO_GRAPH = {
    "id": "AAMkAGI2...=",
    "subject": "Semanal de proyecto",
    "start": {"dateTime": "2026-08-03T14:00:00.0000000", "timeZone": "UTC"},
    "end": {"dateTime": "2026-08-03T15:00:00.0000000", "timeZone": "UTC"},
    "organizer": {"emailAddress": {"name": "Ana Gomez", "address": "ana@contoso.com"}},
    "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/xyz"},
}


class _ClienteFalso:
    def __init__(self, eventos=None, excepcion=None, acceso_ok=True):
        self._eventos = eventos if eventos is not None else []
        self._excepcion = excepcion
        self._acceso_ok = acceso_ok
        self.llamadas = 0

    def list_events(self, *, desde, hasta):
        self.llamadas += 1
        if self._excepcion is not None:
            raise self._excepcion
        return list(self._eventos)

    def _access_token(self) -> str:
        if not self._acceso_ok:
            raise GraphApiError(401, "sesion vencida", kind="auth")
        return "acceso"


@pytest.fixture(autouse=True)
def _flags_encendidas(monkeypatch):
    from config import config as _cfg

    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_ENABLED", True, raising=False)
    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_GRAPH_ENABLED", True, raising=False)
    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_GRAPH_CLIENT_ID", "app-123", raising=False)
    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_GRAPH_TENANT", "", raising=False)
    yield


def test_1_from_graph_event_da_fechas_naive_utc():
    registro = from_graph_event(EVENTO_GRAPH)

    assert isinstance(registro, MeetingRecord)
    assert registro.source == "graph"
    assert registro.external_id == "AAMkAGI2...="
    assert registro.subject == "Semanal de proyecto"
    assert registro.organizer == "Ana Gomez"
    assert registro.started_at == datetime(2026, 8, 3, 14, 0, 0)
    assert registro.started_at.tzinfo is None, "quedo con zona horaria"
    assert registro.ended_at == datetime(2026, 8, 3, 15, 0, 0)
    assert registro.join_url.startswith("https://teams.microsoft.com/")


def test_2_evento_sin_reunion_en_linea_no_lanza():
    presencial = {k: v for k, v in EVENTO_GRAPH.items() if k != "onlineMeeting"}
    registro = from_graph_event(presencial)
    assert registro.join_url is None
    assert registro.subject == "Semanal de proyecto"

    # Y un evento vacio tampoco revienta: degrada con un titulo por defecto.
    vacio = from_graph_event({})
    assert vacio.subject == "Reunion sin titulo"
    assert vacio.started_at is None
    assert vacio.external_id is None


def test_3_con_la_conexion_apagada_el_estado_es_apagado(monkeypatch):
    from config import config as _cfg

    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_GRAPH_ENABLED", False, raising=False)
    salida = list_upcoming(project="P283")
    assert salida["estado"] == "apagado"
    assert salida["reuniones"] == []
    assert salida["detalle"], "la degradacion tiene que decir POR QUE"

    # El master tambien apaga, y con otro mensaje.
    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_ENABLED", False, raising=False)
    assert list_upcoming(project="P283")["estado"] == "apagado"


def test_4_sin_identificador_de_aplicacion_es_sin_credenciales(monkeypatch):
    from config import config as _cfg

    monkeypatch.setattr(_cfg, "STACKY_MEETINGS_GRAPH_CLIENT_ID", "", raising=False)
    salida = list_upcoming(project="P283")
    assert salida["estado"] == "sin_credenciales"
    assert salida["reuniones"] == []
    assert "identificador" in salida["detalle"].lower()


def test_5_con_transporte_falso_devuelve_ok_y_las_reuniones():
    otro = dict(EVENTO_GRAPH, id="ev-2", subject="Retro",
                start={"dateTime": "2026-08-01T09:00:00Z"},
                end={"dateTime": "2026-08-01T10:00:00Z"})
    cliente = _ClienteFalso(eventos=[EVENTO_GRAPH, otro])

    salida = list_upcoming(project="P283", client=cliente)
    assert salida["estado"] == "ok"
    assert len(salida["reuniones"]) == 2
    assert cliente.llamadas == 1
    # Orden por fecha ascendente: la retro (1/8) va antes que la semanal (3/8).
    assert salida["reuniones"][0]["subject"] == "Retro"
    assert salida["reuniones"][0]["started_at"] == "2026-08-01T09:00:00Z"


def test_6_un_401_da_estado_error_y_dice_que_hay_que_reingresar():
    cliente = _ClienteFalso(excepcion=GraphApiError(401, "invalid_grant", kind="auth"))
    salida = list_upcoming(project="P283", client=cliente)

    assert salida["estado"] == "error"
    assert salida["reuniones"] == []
    assert "ingreso" in salida["detalle"].lower()
    # Y NO filtra el valor de ninguna credencial en el mensaje.
    assert "app-123" not in salida["detalle"]
    assert "refresh" not in salida["detalle"].lower()


def test_7_d7_ningun_hilo_ningun_temporizador_ningun_loop():
    """Gate de D7: si este modulo arrancara algo en reposo, las flags de lectura
    NO podrian nacer ON (categoria A de la regla de flags). Guard positivo
    primero, contra un fuente que SI define un ciclo."""
    def _ofensas(fuente: str) -> list[str]:
        encontradas: list[str] = []
        arbol = ast.parse(fuente)
        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.name.endswith("_loop"):
                encontradas.append(f"def {nodo.name}")
            if isinstance(nodo, ast.Attribute) and nodo.attr in ("Thread", "Timer"):
                receptor = getattr(nodo.value, "id", "")
                if receptor in ("threading", "th"):
                    encontradas.append(f"{receptor}.{nodo.attr}")
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    if alias.name.split(".")[0] in ("threading", "schedule", "sched"):
                        encontradas.append(f"import {alias.name}")
            if isinstance(nodo, ast.ImportFrom) and (nodo.module or "").split(".")[0] in (
                "threading", "schedule", "sched"
            ):
                encontradas.append(f"from {nodo.module}")
        return encontradas

    # GUARD POSITIVO, PRIMERO.
    sucio = "import threading\ndef _tick_loop():\n    threading.Thread(target=None).start()\n"
    assert set(_ofensas(sucio)) == {"import threading", "def _tick_loop", "threading.Thread"}

    vigilados = [
        _SERVICES / "meetings_source.py",
        _SERVICES / "meetings_store.py",
        _SERVICES / "meeting_minutes.py",
        _SERVICES / "graph_client.py",
        _SERVICES / "transcript_parser.py",
    ]
    for ruta in vigilados:
        assert ruta.is_file(), f"falta {ruta.name}: el gate estaria vigilando el aire"
        ofensas = _ofensas(ruta.read_text(encoding="utf-8"))
        assert ofensas == [], f"{ruta.name} arranca trabajo en reposo: {ofensas}"


def test_8_from_manual_sin_fechas_no_lanza():
    registro = from_manual(subject="Reunion pegada a mano")
    assert registro.source == "manual"
    assert registro.started_at is None
    assert registro.ended_at is None
    assert registro.external_id is None
    assert registro.join_url is None
    assert from_manual(subject="   ").subject == "Reunion sin titulo"

    # La sonda tambien degrada sin lanzar, y da los TRES sub-veredictos.
    sonda = probe_graph(project="P283", client=_ClienteFalso(eventos=[EVENTO_GRAPH]))
    assert set(sonda) == {"config", "auth", "calendario", "detalle"}
    assert sonda["config"] is True and sonda["auth"] is True and sonda["calendario"] is True

    # Con la sesion vencida, `auth` cae y `calendario` NO se declara verde.
    caida = probe_graph(project="P283", client=_ClienteFalso(acceso_ok=False))
    assert caida["auth"] is False
    assert caida["calendario"] is False
