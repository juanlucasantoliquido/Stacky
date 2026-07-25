"""tests/test_plan218_capability_unavailable.py -- Plan 218 F6.

Degradación DECLARADA: una capacidad que el proveedor activo no tiene se manifiesta
como un 200 accionable, nunca como un 500 mudo ni como un silencio.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_module  # noqa: E402

_API_DIR = _BACKEND / "api"

# Los 4 `except NotImplementedError` LEGÍTIMOS que el centinela NO debe empujar a borrar
# (C2: el criterio del v1 exigía degradar el manejo de errores de endpoints ajenos al plan).
_EXCEPT_LEGITIMOS = (
    "api/agents.py", "api/ci.py", "api/pipeline_generator.py",
)


class _FakeProvider:
    def __init__(self, name):
        self.name = name


@pytest.fixture
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_endpoint_de_sync_devuelve_200_con_available_false(client, monkeypatch):
    monkeypatch.setattr(config_module.config, "STACKY_CAPABILITY_DEGRADATION_ENABLED", True)

    with patch("api.tickets._provider_for_ticket", return_value=_FakeProvider("gitlab")):
        resp = client.post("/api/tickets/sync")

    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["available"] is False
    assert body["capability"] == "tracker.sync.full"
    assert body["provider"] == "gitlab"
    assert body["workaround"], "la degradación debe decirle al operador qué hacer"


def test_endpoint_de_sync_ado_no_cambia(client, monkeypatch):
    """Regresión: con provider ADO el endpoint se comporta exactamente igual que antes."""
    monkeypatch.setattr(config_module.config, "STACKY_CAPABILITY_DEGRADATION_ENABLED", True)

    with patch("api.tickets._provider_for_ticket", return_value=_FakeProvider("azure_devops")), \
         patch("api.tickets._ado_client_for_ticket", return_value=object()), \
         patch("api.tickets.sync_tickets", return_value={"created": 0, "updated": 0}) as fake_sync:
        resp = client.post("/api/tickets/sync")

    assert fake_sync.called, "el path ADO debe seguir yendo a sync_tickets legacy"
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert "available" not in body


def test_flag_off_restaura_excepcion_legacy(client, monkeypatch):
    """Rollback por flag: vuelve la RESPUESTA legacy (500 'unexpected').

    No se reintroduce el `raise NotImplementedError` que esta fase sacó del dominio:
    lo que el operador recupera es la forma HTTP anterior, que es lo que consumían
    sus clientes (P11).
    """
    monkeypatch.setattr(config_module.config, "STACKY_CAPABILITY_DEGRADATION_ENABLED", False)

    with patch("api.tickets._provider_for_ticket", return_value=_FakeProvider("gitlab")):
        resp = client.post("/api/tickets/sync")

    assert resp.status_code == 500
    body = resp.get_json()
    assert body["ok"] is False
    assert body["error"] == "unexpected"


def test_no_quedan_RAISE_notimplementederror_en_api():
    """C2: el centinela caza `raise NotImplementedError`, NO la mención del símbolo."""
    import re

    patron = re.compile(r"raise\s+NotImplementedError")
    ofensores = []
    for archivo in sorted(_API_DIR.glob("*.py")):
        for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
            if patron.search(linea):
                ofensores.append(f"api/{archivo.name}:{n}")

    assert ofensores == [], (
        "un endpoint no puede morir con NotImplementedError: usá CapabilityUnavailable "
        f"(Plan 218 F6). Sitios: {ofensores}"
    )


def test_los_4_except_legitimos_siguen_en_pie():
    """Guard anti-celo: nadie borra un `except NotImplementedError` legítimo para
    poner un grep en cero."""
    total = 0
    por_archivo = {}
    for archivo in sorted(_API_DIR.glob("*.py")):
        n = sum(
            1 for linea in archivo.read_text(encoding="utf-8").splitlines()
            if "except NotImplementedError" in linea
        )
        if n:
            por_archivo[f"api/{archivo.name}"] = n
            total += n

    assert total == 4, f"los 4 except legítimos cambiaron: {por_archivo}"
    for esperado in _EXCEPT_LEGITIMOS:
        assert esperado in por_archivo, f"desapareció el except legítimo de {esperado}"
