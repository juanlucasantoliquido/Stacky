"""Aísla el logging de pytest (Plan 145 / V7): setea STACKY_TEST_MODE antes de
que cualquier módulo de app importe/instale el FileHandler, para que los tests
no escriban en backend/data/logs/. También asegura backend/ en sys.path."""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("STACKY_TEST_MODE", "1")


import socket as _socket

import pytest


_REAL_CONNECT = _socket.socket.connect
_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


@pytest.fixture(autouse=True)
def _no_network_egress(monkeypatch):
    """Plan 154 F5.i — bajo STACKY_TEST_MODE, todo connect() saliente
    no-loopback falla con mensaje accionable. Un test que necesite red real
    no existe en este repo por diseño: mockear el cliente HTTP."""
    if os.environ.get("STACKY_TEST_MODE", "").strip().lower() not in ("1", "true", "yes"):
        yield
        return

    def _guarded_connect(self, address):
        host = None
        if isinstance(address, tuple) and address:
            host = address[0]
            if isinstance(host, bytes):
                host = host.decode("utf-8", "replace")
        if host in _LOOPBACK_HOSTS or self.family not in (_socket.AF_INET, _socket.AF_INET6):
            return _REAL_CONNECT(self, address)
        raise RuntimeError(
            f"[plan154 guard-red] egress de red bloqueado en tests: destino {address!r}. "
            "Mockea el cliente HTTP (requests/urllib) o usa loopback."
        )

    monkeypatch.setattr(_socket.socket, "connect", _guarded_connect)
    yield


# Plan 154 F5.i (adicion v2) — DESVIACION DOCUMENTADA respecto del texto del plan:
# la version original neutralizaba app._startup_sync de forma GLOBAL vía un autouse.
# Eso clobbea a tests que invocan _startup_sync DIRECTAMENTE para ejercitar el
# circuit-breaker (test_plan148_ado_sync_breaker / _jira_sync_breaker parchean solo
# el interno _ado_sync y llaman la funcion real) -> 6 rojos. La hermeticidad de
# create_app() que pedia C1 ya la entrega el gate F5.ii (call-site en app.py salta
# _startup_sync bajo STACKY_TEST_MODE) y, como backstop de egress real, el guard de
# sockets _no_network_egress de arriba (bloquea cualquier connect() a dev.azure.com).
# No hace falta un no-op global del simbolo: seria redundante y degradaria la suite.
