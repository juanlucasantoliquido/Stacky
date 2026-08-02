"""Aísla el logging de pytest (Plan 145 / V7): setea STACKY_TEST_MODE antes de
que cualquier módulo de app importe/instale el FileHandler, para que los tests
no escriban en backend/data/logs/. También asegura backend/ en sys.path.

Plan 258 F5 — se SUMA (no reemplaza) un guard que falla ruidosamente si algún
handler de logging quedó apuntando al log del operador. El `setdefault` de
STACKY_TEST_MODE y el guard de red del plan 154 quedan exactamente como estaban.
"""
import logging
import os
import sys
from pathlib import Path

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("STACKY_TEST_MODE", "1")


import socket as _socket

import pytest


_REAL_CONNECT = _socket.socket.connect
_REAL_GETADDRINFO = _socket.getaddrinfo
_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def _hosts_locales() -> frozenset[str]:
    """Nombres que resuelven a esta misma máquina. Se calculan UNA vez, con el
    getaddrinfo real, antes de instalar el guard."""
    nombres = set()
    for fn in (_socket.gethostname, _socket.getfqdn):
        try:
            v = fn()
        except Exception:  # noqa: BLE001 — best-effort
            continue
        if v:
            nombres.add(str(v).strip().lower().rstrip("."))
    return frozenset(nombres)


_HOSTS_LOCALES = _hosts_locales()


def _es_destino_local(host) -> bool:
    """True para loopback, bind sin host y el nombre de esta máquina."""
    if host is None:
        return True                       # getaddrinfo(None, port) = bind pasivo
    if isinstance(host, bytes):
        host = host.decode("utf-8", "replace")
    h = str(host).strip().lower().rstrip(".")
    if not h:
        return True
    if h in _LOOPBACK_HOSTS or h in _HOSTS_LOCALES:
        return True
    return h.startswith("127.") or h in ("0.0.0.0", "::", "::1")


@pytest.fixture(autouse=True)
def _no_network_egress(monkeypatch):
    """Plan 154 F5.i — bajo STACKY_TEST_MODE, todo egress no-loopback falla con
    mensaje accionable. Un test que necesite red real no existe en este repo por
    diseño: mockear el cliente HTTP.

    Plan 291 [ADICIÓN ARQUITECTO 3] — el guard enganchaba SOLO `socket.connect`,
    y por ahí se escapaba lo que muere ANTES, en la resolución DNS. Medido el
    2026-08-02: `tests/test_plan218_tracker_contract.py::[gitlab]` emite un
    request HTTPS real y revienta en `getaddrinfo` contra `gl.test`, o sea que
    `connect()` nunca se llega a ejecutar y el guard ni se entera.

    Ahora se enganchan LOS DOS, no se muda uno por el otro: `getaddrinfo` ataja
    el caso por nombre (que es el 99 % del egress real) y `connect` sigue
    atajando el destino por IP literal, donde no hay resolución que interceptar.
    """
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

    def _guarded_getaddrinfo(host, port, *args, **kwargs):
        if _es_destino_local(host):
            return _REAL_GETADDRINFO(host, port, *args, **kwargs)
        raise RuntimeError(
            f"[plan154 guard-red] resolución DNS bloqueada en tests: host {host!r} "
            f"(puerto {port!r}). Mockea el cliente HTTP (requests/urllib) o usa loopback."
        )

    monkeypatch.setattr(_socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(_socket, "getaddrinfo", _guarded_getaddrinfo)
    yield


# ---------------------------------------------------------------------------
# Plan 258 F5 — guard: ningún handler de logging puede apuntar a data/logs/
# ---------------------------------------------------------------------------
# El agujero está CERRADO desde el 2026-07-16 (plan 145, commit f00f161f):
# `install_file_log_handler` redirige a %TEMP%/stacky-test-logs/ en test-mode.
# Este guard NO lo reimplementa ni cambia su firma (`local_file_logging.py` es
# frontera del plan 257): solo impide que se reabra EN SILENCIO. Si aparece un
# handler al log real, la corrida falla NOMBRÁNDOLO, en vez de contaminar mudo.

_LOGS_DEL_OPERADOR = Path(_BACKEND) / "data" / "logs"


def _handlers_apuntando_al_log_del_operador() -> list[str]:
    """Rutas de los FileHandler activos que escriben bajo backend/data/logs/.

    Recorre el root logger Y los loggers con nombre: un handler instalado en
    `stacky.loquesea` no aparece en `logging.getLogger().handlers`.
    """
    try:
        objetivo = _LOGS_DEL_OPERADOR.resolve()
    except OSError:  # pragma: no cover
        objetivo = _LOGS_DEL_OPERADOR

    vistos: set[int] = set()
    ofensores: list[str] = []
    candidatos = [logging.getLogger()]
    candidatos += [lg for lg in logging.Logger.manager.loggerDict.values()
                   if isinstance(lg, logging.Logger)]
    for lg in candidatos:
        for h in list(getattr(lg, "handlers", []) or []):
            if id(h) in vistos:
                continue
            vistos.add(id(h))
            destino = getattr(h, "baseFilename", None)
            if not destino:
                continue
            try:
                p = Path(str(destino)).resolve()
            except OSError:  # pragma: no cover
                continue
            if p.parent == objetivo:
                ofensores.append(str(p))
    return sorted(ofensores)


@pytest.fixture
def guard_log_handlers():
    """Expone el detector a los tests (plan 258 F5). Devuelve la lista de rutas
    ofensoras, vacía cuando el aislamiento está sano."""
    return _handlers_apuntando_al_log_del_operador


@pytest.fixture(scope="session", autouse=True)
def _guard_log_del_operador():
    yield
    ofensores = _handlers_apuntando_al_log_del_operador()
    assert not ofensores, (
        "[plan258 F5] un handler de logging quedó apuntando al log del operador "
        f"({_LOGS_DEL_OPERADOR}): {ofensores}. El plan 145 redirige a "
        "%TEMP%/stacky-test-logs/ bajo STACKY_TEST_MODE; si esto salta, el "
        "aislamiento se reabrió. NO lo silencies con una allowlist."
    )


# Plan 154 F5.i (adicion v2) — DESVIACION DOCUMENTADA respecto del texto del plan:
# la version original neutralizaba app._startup_sync de forma GLOBAL vía un autouse.
# Eso clobbea a tests que invocan _startup_sync DIRECTAMENTE para ejercitar el
# circuit-breaker (test_plan148_ado_sync_breaker / _jira_sync_breaker parchean solo
# el interno _ado_sync y llaman la funcion real) -> 6 rojos. La hermeticidad de
# create_app() que pedia C1 ya la entrega el gate F5.ii (call-site en app.py salta
# _startup_sync bajo STACKY_TEST_MODE) y, como backstop de egress real, el guard de
# sockets _no_network_egress de arriba (bloquea cualquier connect() a dev.azure.com).
# No hace falta un no-op global del simbolo: seria redundante y degradaria la suite.
