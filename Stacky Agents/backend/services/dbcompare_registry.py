"""services/dbcompare_registry.py — Plan 122 F1: registro de ambientes de BD para el
Comparador de BD entre ambientes (serie 122-126).

Persistencia: JSON en data_dir()/db_compare/environments.json con TODO menos el
password. El password vive EXCLUSIVAMENTE en el Credential Manager del SO vía
keyring (service=KEYRING_SERVICE_DBCOMPARE, key=alias) — espejo del patrón Plan 91
(services/server_registry.py). NUNCA loggear ni persistir passwords en texto plano.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

try:
    import keyring  # backend Windows: Credential Manager
except ImportError:  # keyring no instalado — NUNCA fallback a texto plano
    keyring = None

from runtime_paths import data_dir
from services.server_registry import validate_alias, validate_host

logger = logging.getLogger(__name__)

KEYRING_SERVICE_DBCOMPARE = "stacky-dbcompare"
_REGISTRY_FILENAME = "db_compare/environments.json"
ENGINES = ("sqlserver", "oracle")  # sqlite se acepta SOLO si alias empieza con "test-"
_LOCK = threading.Lock()

_PUBLIC_KEYS = (
    "alias", "engine", "host", "port", "database", "username", "odbc_driver",
    "schema_filter", "notes", "created_at", "last_used_at",
)


def _registry_path():
    return data_dir() / _REGISTRY_FILENAME


def _now_iso() -> str:
    # mismo idioma que services/db_query.py:177 (record_audit_event)
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def keyring_available() -> bool:
    return keyring is not None


def _load() -> list[dict]:
    path = _registry_path()
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("db_compare/environments.json no es una lista; se ignora")
            return []
        return [d for d in data if isinstance(d, dict)]
    except Exception as exc:  # noqa: BLE001 — JSON corrupto: degradar a vacío, sin crash
        logger.warning("db_compare/environments.json inválido (%s); se ignora", type(exc).__name__)
        return []


def _save(environments: list[dict]) -> None:
    for e in environments:
        if "password" in e:
            raise ValueError("dbcompare_registry: 'password' JAMÁS se persiste en el JSON")
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(environments, indent=2, ensure_ascii=False), encoding="utf-8")


def _public(env: dict) -> dict:
    out = {k: env.get(k) for k in _PUBLIC_KEYS if k in env}
    out["has_password"] = has_password(env.get("alias", ""))
    return out


def _validate_engine(alias: str, engine: str) -> None:
    if engine == "sqlite":
        if not alias.startswith("test-"):
            raise ValueError(
                "engine 'sqlite' solo se acepta para alias que empiecen con 'test-' "
                "(reservado a tests/demo)"
            )
        return
    if engine not in ENGINES:
        raise ValueError(f"engine inválido: '{engine}' — debe ser uno de {ENGINES!r} (o 'sqlite' para alias 'test-*')")


def _validate_port(port) -> int:
    try:
        port_int = int(port)
    except (TypeError, ValueError):
        raise ValueError("port debe ser un entero")
    if not (1 <= port_int <= 65535):
        raise ValueError("port debe estar en el rango [1, 65535]")
    return port_int


def list_environments() -> list[dict]:
    envs = _load()
    return [_public(e) for e in sorted(envs, key=lambda x: x.get("alias", ""))]


def get_environment(alias: str) -> dict | None:
    for e in _load():
        if e.get("alias") == alias:
            return _public(e)
    return None


def upsert_environment(
    alias: str,
    engine: str,
    host: str,
    port,
    database: str,
    username: str,
    odbc_driver: str = "ODBC Driver 17 for SQL Server",
    schema_filter: list[str] | None = None,
    notes: str = "",
) -> dict:
    if not validate_alias(alias):
        raise ValueError(
            "alias inválido: solo letras/dígitos y _.- (1-64 chars, empieza alfanumérico)"
        )
    _validate_engine(alias, engine)
    if engine != "sqlite" and not validate_host(host):
        raise ValueError(
            "host inválido: solo letras/dígitos/punto/guión y ':puerto' opcional"
        )
    port_int = _validate_port(port) if engine != "sqlite" else (int(port) if port else 0)
    if not isinstance(database, str) or not database.strip():
        raise ValueError("database es obligatorio")
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username es obligatorio")
    schema_filter_val = list(schema_filter) if schema_filter else None
    notes = notes if isinstance(notes, str) else ""
    odbc_driver = odbc_driver if isinstance(odbc_driver, str) and odbc_driver.strip() else "ODBC Driver 17 for SQL Server"

    with _LOCK:
        envs = _load()
        existing = next((e for e in envs if e.get("alias") == alias), None)
        record = {
            "alias": alias,
            "engine": engine,
            "host": host,
            "port": port_int,
            "database": database,
            "username": username,
            "odbc_driver": odbc_driver,
            "schema_filter": schema_filter_val,
            "notes": notes,
            "created_at": existing.get("created_at") if existing else _now_iso(),
            "last_used_at": existing.get("last_used_at") if existing else None,
        }
        if existing is not None:
            envs = [record if e.get("alias") == alias else e for e in envs]
        else:
            envs.append(record)
        _save(envs)
    return _public(record)


def delete_environment(alias: str) -> bool:
    with _LOCK:
        envs = _load()
        target = next((e for e in envs if e.get("alias") == alias), None)
        if target is None:
            return False
        envs = [e for e in envs if e.get("alias") != alias]
        _save(envs)
    clear_password(alias)
    return True


def set_password(alias: str, password: str) -> None:
    if not keyring_available():
        raise RuntimeError("keyring no disponible")
    keyring.set_password(KEYRING_SERVICE_DBCOMPARE, alias, password)


def clear_password(alias: str) -> None:
    if keyring is None:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE_DBCOMPARE, alias)
    except Exception:  # noqa: BLE001 — no había credencial o keyring ausente: no-op
        pass


def has_password(alias: str) -> bool:
    if not keyring_available() or not alias:
        return False
    try:
        return keyring.get_password(KEYRING_SERVICE_DBCOMPARE, alias) is not None
    except Exception:  # noqa: BLE001
        return False


def get_credential(alias: str) -> dict | None:
    """SOLO para uso interno del engine (F2). Devuelve {**env, "password": str} o None."""
    env = None
    for e in _load():
        if e.get("alias") == alias:
            env = e
            break
    if env is None or not keyring_available():
        return None
    try:
        password = keyring.get_password(KEYRING_SERVICE_DBCOMPARE, alias)
    except Exception:  # noqa: BLE001
        return None
    if password is None:
        return None
    return {**env, "password": password}


def touch_last_used(alias: str) -> None:
    with _LOCK:
        envs = _load()
        found = False
        for e in envs:
            if e.get("alias") == alias:
                e["last_used_at"] = _now_iso()
                found = True
                break
        if found:
            _save(envs)
