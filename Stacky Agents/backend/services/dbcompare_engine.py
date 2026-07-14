"""services/dbcompare_engine.py — Plan 122 F2: motor de conexión read-only por alias
para el Comparador de BD entre ambientes (serie 122-126).

Drivers opcionales y lazy: sin pyodbc/oracledb instalados, Stacky arranca y funciona
igual (driver_status() reporta qué falta + hint de instalación). NINGÚN `import pyodbc`
/`import oracledb` a nivel módulo — SQLAlchemy los resuelve recién en create_engine()/
connect().
"""
from __future__ import annotations

import importlib.util
import re
import time

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from config import Config
from services import dbcompare_registry

_PROBE_SQL = {"sqlserver": "SELECT 1", "oracle": "SELECT 1 FROM DUAL", "sqlite": "SELECT 1"}

_DRIVER_MODULE = {"sqlserver": "pyodbc", "oracle": "oracledb"}

_NETWORK_ISSUE_RE = re.compile(
    r"timeout|network-related|could not be found|no such host|actively refused|unreachable",
    re.IGNORECASE,
)


class DbCompareEngineError(RuntimeError):
    """Error accionable al abrir/probar una conexión read-only de un ambiente."""


def driver_status() -> dict:
    out = {}
    for engine_kind, module_name in _DRIVER_MODULE.items():
        available = importlib.util.find_spec(module_name) is not None
        out[engine_kind] = {
            "module": module_name,
            "available": available,
            "install_hint": (
                f'cd "Stacky Agents/backend" && .venv\\Scripts\\pip install {module_name}'
            ),
        }
    return out


def build_sqlalchemy_url(env: dict, password: str) -> URL:
    engine_kind = env["engine"]
    if engine_kind == "sqlserver":
        return URL.create(
            "mssql+pyodbc",
            username=env["username"],
            password=password,
            host=env["host"],
            port=env["port"],
            database=env["database"],
            query={
                "driver": env.get("odbc_driver") or "ODBC Driver 17 for SQL Server",
                "TrustServerCertificate": "yes",
            },
        )
    if engine_kind == "oracle":
        return URL.create(
            "oracle+oracledb",
            username=env["username"],
            password=password,
            host=env["host"],
            port=env["port"],
            query={"service_name": env["database"]},
        )
    if engine_kind == "sqlite":
        return URL.create("sqlite", database=env["database"])
    raise DbCompareEngineError(f"engine desconocido: {engine_kind!r}")


def _scrub(message: str, password: str | None) -> str:
    if password and password in message:
        return message.replace(password, "***")
    return message


def _classify_likely_network(message: str) -> bool:
    return bool(_NETWORK_ISSUE_RE.search(message or ""))


def open_engine(alias: str, *, timeout_sec: int | None = None):
    cred = dbcompare_registry.get_credential(alias)
    if cred is None:
        raise DbCompareEngineError(
            f"credencial faltante: registrá el ambiente '{alias}' y guardale un password "
            "(POST /api/db-compare/environments/<alias>/password)."
        )
    engine_kind = cred["engine"]
    if engine_kind != "sqlite":
        status = driver_status().get(engine_kind, {})
        if not status.get("available"):
            raise DbCompareEngineError(
                f"falta el driver '{status.get('module')}' para el motor '{engine_kind}'. "
                f"Instalalo con: {status.get('install_hint')}"
            )

    timeout = timeout_sec if timeout_sec is not None else Config.STACKY_DB_COMPARE_CONNECT_TIMEOUT_SEC
    password = cred["password"]
    url = build_sqlalchemy_url(cred, password)

    if engine_kind == "sqlserver":
        connect_args = {"timeout": timeout}
    elif engine_kind == "oracle":
        connect_args = {"tcp_connect_timeout": timeout}
    else:
        connect_args = {}

    try:
        engine = create_engine(
            url, pool_pre_ping=True, pool_size=1, max_overflow=0, future=True,
            connect_args=connect_args,
        )
    except Exception as exc:  # noqa: BLE001 — nunca dejar pasar el password crudo
        raise DbCompareEngineError(_scrub(str(exc), password)) from exc

    dbcompare_registry.touch_last_used(alias)
    return engine


def test_connection(alias: str) -> dict:
    cred = dbcompare_registry.get_credential(alias)
    password = cred.get("password") if cred else None
    try:
        engine = open_engine(alias)
    except Exception as exc:  # noqa: BLE001 — test_connection NUNCA lanza (contrato F2)
        msg = _scrub(str(exc), password)
        return {
            "ok": False,
            "error": msg,
            "install_hint": None,
            "likely_network": _classify_likely_network(msg),
        }

    engine_kind = cred["engine"] if cred else "sqlite"
    started = time.monotonic()
    try:
        with engine.connect() as conn:
            conn.execute(text(_PROBE_SQL.get(engine_kind, "SELECT 1")))
            server_version = getattr(engine.dialect, "server_version_info", None)
        latency_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": True,
            "engine": engine_kind,
            "server_version": str(server_version or ""),
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001 — test_connection NUNCA lanza
        msg = _scrub(str(exc), password)
        driver_hint = None
        status = driver_status().get(engine_kind)
        if status and not status.get("available"):
            driver_hint = status.get("install_hint")
        return {
            "ok": False,
            "error": msg,
            "install_hint": driver_hint,
            "likely_network": _classify_likely_network(msg),
        }
    finally:
        engine.dispose()
