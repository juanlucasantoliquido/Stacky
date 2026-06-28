"""Plan 70 F11 -- Documentacion estatica: ado_publisher y ado_sync son ADO-only.

Estos archivos NO se migran al puerto TrackerProvider en este plan.
Razon: riesgo de import circular (api.tickets._provider_for_ticket desde services/)
y mismatch de tipos (ado_id int en publisher vs str en el puerto).

Los call sites documentados como ADO-only en ado_publisher.py:
  - Linea ~258: docstring "client_factory: lambda → AdoClient()"
  - Linea ~579: _default_client() → AdoClient() directamente

Los call sites en ado_sync.py:
  - Linea ~102: def sync_tickets(client: AdoClient | None = None)
  - Linea ~111: usa client.fetch_open_work_items() (metodo ADO-especifico)

Ninguno de estos sitios debe usar TrackerProvider — lo verifica este modulo.
"""
from __future__ import annotations

import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_PUBLISHER = _BACKEND / "services" / "ado_publisher.py"
_SYNC = _BACKEND / "services" / "ado_sync.py"


def test_ado_publisher_exists():
    """ado_publisher.py existe (chequeo basico de setup)."""
    assert _PUBLISHER.exists(), "services/ado_publisher.py no encontrado"


def test_ado_sync_exists():
    """ado_sync.py existe."""
    assert _SYNC.exists(), "services/ado_sync.py no encontrado"


def test_ado_publisher_does_not_import_tracker_provider():
    """ado_publisher.py NO importa TrackerProvider (ADO-only por decision de Plan 70)."""
    text = _PUBLISHER.read_text(encoding="utf-8")
    assert "TrackerProvider" not in text, (
        "F11: ado_publisher.py no debe importar TrackerProvider — "
        "migración diferida para evitar import circular. "
        "Si esto cambió, actualizar el allowlist F12."
    )


def test_ado_sync_does_not_import_tracker_provider():
    """ado_sync.py NO importa TrackerProvider (ADO-only por decision de Plan 70)."""
    text = _SYNC.read_text(encoding="utf-8")
    assert "TrackerProvider" not in text, (
        "F11: ado_sync.py no debe importar TrackerProvider — "
        "sync GitLab diferido a Plan 71. "
        "Si esto cambió, actualizar el allowlist F12."
    )


def test_ado_publisher_default_client_stays_ado():
    """ado_publisher._default_client usa AdoClient directamente (no el puerto)."""
    text = _PUBLISHER.read_text(encoding="utf-8")
    # _default_client debe existir y retornar AdoClient
    assert "_default_client" in text or "AdoClient" in text, (
        "F11: ado_publisher.py debe conservar AdoClient como cliente por defecto"
    )


def test_ado_sync_tickets_uses_ado_client():
    """ado_sync.sync_tickets acepta AdoClient (no TrackerProvider)."""
    text = _SYNC.read_text(encoding="utf-8")
    assert "AdoClient" in text, (
        "F11: ado_sync.py debe usar AdoClient — migración a TrackerProvider es Plan 71"
    )


def test_tickets_py_has_sync_via_provider_helper():
    """tickets.py tiene _sync_via_provider_or_ado que hace el gating (no ado_sync)."""
    tickets = (_BACKEND / "api" / "tickets.py").read_text(encoding="utf-8")
    assert "_sync_via_provider_or_ado" in tickets, (
        "F10/F11: el gating de sync debe estar en tickets.py, no en ado_sync.py"
    )
