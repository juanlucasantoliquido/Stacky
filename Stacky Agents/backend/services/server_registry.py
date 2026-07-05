"""services/server_registry.py — Plan 91: registro de servidores DevOps.

Persistencia: JSON en data_dir()/devops_servers.json (patrón project_manager.py:34,87)
con SOLO {alias, host, domain, username, notes, last_connected_at}. El password vive
EXCLUSIVAMENTE en el Credential Manager del SO via keyring (service=KEYRING_SERVICE,
key=alias). get_credential(alias) es EL punto de consumo para la extension remota futura
(89_PLAN_INICIALIZACION_AMBIENTES_DEVOPS.md:958-960: "remoto exigiria credenciales y
otro plan" — este es ese plan). NUNCA loggear passwords.
"""
import json
import logging
import re
import socket
import subprocess
import sys
import threading
from datetime import datetime, timezone

try:
    import keyring  # backend Windows: Credential Manager
except ImportError:  # keyring no instalado — NUNCA fallback a texto plano (§3.1)
    keyring = None

from runtime_paths import data_dir

logger = logging.getLogger(__name__)

KEYRING_SERVICE = "stacky-devops"
MAX_SERVERS = 100
_ALIAS_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}$")
# C2: hostname/FQDN/IP, opcional :puerto. SIN espacios, sin '/', sin comillas —
# el host se interpola en TERMSRV/{host} y mstsc /v:{host} (F4).
_HOST_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,252}(:\d{1,5})?$")
_LOCK = threading.Lock()  # C7: serializa load→mutate→save del JSON

_PUBLIC_KEYS = ("alias", "host", "domain", "username", "notes", "last_connected_at")


def _registry_path():
    return data_dir() / "devops_servers.json"


def keyring_available() -> bool:
    return keyring is not None


def validate_alias(alias: str) -> bool:
    return bool(isinstance(alias, str) and _ALIAS_RE.match(alias))


def validate_host(host: str) -> bool:  # C2
    return bool(isinstance(host, str) and _HOST_RE.match(host))


def _load() -> list[dict]:
    path = _registry_path()
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            logger.warning("devops_servers.json no es una lista; se ignora")
            return []
        return [d for d in data if isinstance(d, dict)]
    except Exception as exc:  # noqa: BLE001 — JSON corrupto: degradar a vacío, sin crash
        logger.warning("devops_servers.json inválido (%s); se ignora", type(exc).__name__)
        return []


def _save(servers: list[dict]) -> None:
    # §3.1: assert defensivo — ningún dict puede contener "password".
    for s in servers:
        if "password" in s:
            raise ValueError("server_registry: 'password' JAMÁS se persiste en el JSON")
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(servers, indent=2, ensure_ascii=False), encoding="utf-8")


def _public(server: dict) -> dict:
    return {k: server.get(k) for k in _PUBLIC_KEYS if k in server}


def list_servers() -> list[dict]:
    servers = _load()
    out = []
    for s in sorted(servers, key=lambda x: x.get("alias", "")):
        item = _public(s)
        item["has_password"] = has_password(s.get("alias", ""))
        out.append(item)
    return out


def get_server(alias: str) -> dict | None:
    for s in _load():
        if s.get("alias") == alias:
            return _public(s)
    return None


def upsert_server(alias: str, host: str, domain: str, username: str, notes: str) -> dict:
    if not validate_alias(alias):
        raise ValueError(
            "alias inválido: solo letras/dígitos y _.- (1-64 chars, empieza alfanumérico)"
        )
    if not validate_host(host):  # C2
        raise ValueError(
            "host inválido: solo letras/dígitos/punto/guión y ':puerto' opcional"
        )
    if not isinstance(username, str) or not username.strip():
        raise ValueError("username es obligatorio")
    domain = domain if isinstance(domain, str) else ""
    notes = notes if isinstance(notes, str) else ""
    with _LOCK:
        servers = _load()
        existing = next((s for s in servers if s.get("alias") == alias), None)
        if existing is None and len(servers) >= MAX_SERVERS:
            raise ValueError(f"límite de {MAX_SERVERS} servidores alcanzado")
        record = {
            "alias": alias,
            "host": host,
            "domain": domain,
            "username": username,
            "notes": notes,
        }
        if existing is not None:
            # Preserva last_connected_at existente al actualizar.
            if existing.get("last_connected_at"):
                record["last_connected_at"] = existing["last_connected_at"]
            servers = [record if s.get("alias") == alias else s for s in servers]
        else:
            servers.append(record)
        _save(servers)
    return _public(record)


def _forget_termsrv(host: str) -> None:  # C3 — cleanup best-effort, solo win32
    if sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["cmdkey", f"/delete:TERMSRV/{host}"],
            capture_output=True, timeout=10,
        )
    except Exception:  # noqa: BLE001 — best-effort: si no existía o falla, silencio
        pass


def delete_server(alias: str) -> bool:
    with _LOCK:
        servers = _load()
        target = next((s for s in servers if s.get("alias") == alias), None)
        if target is None:
            return False
        servers = [s for s in servers if s.get("alias") != alias]
        _save(servers)
    # C4: capturar Exception GENÉRICA (el fake de tests no tiene namespace `errors`
    # y la credencial puede no existir).
    if keyring is not None:
        try:
            keyring.delete_password(KEYRING_SERVICE, alias)
        except Exception:  # noqa: BLE001
            pass
    _forget_termsrv(target.get("host", ""))  # C3
    return True


def set_password(alias: str, password: str) -> None:
    if not keyring_available():
        raise RuntimeError("keyring no disponible")
    keyring.set_password(KEYRING_SERVICE, alias, password)


def clear_password(alias: str) -> None:  # C6 — borra SOLO la credencial, no el server
    if keyring is None:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, alias)
    except Exception:  # noqa: BLE001 — no había credencial o keyring ausente: no-op
        pass


def touch_last_connected(alias: str) -> None:  # [ADICIÓN ARQUITECTO]
    with _LOCK:
        servers = _load()
        found = False
        for s in servers:
            if s.get("alias") == alias:
                s["last_connected_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                found = True
                break
        if found:
            _save(servers)


def has_password(alias: str) -> bool:
    if not keyring_available() or not alias:
        return False
    try:
        return keyring.get_password(KEYRING_SERVICE, alias) is not None
    except Exception:  # noqa: BLE001
        return False


def get_credential(alias: str) -> tuple[str, str, str] | None:
    """CONTRATO para consumo futuro (extensión remota 88/89/90, §3.10).
    Devuelve (username, domain, password) o None si no hay servidor o no hay password.
    """
    server = get_server(alias)
    if server is None or not keyring_available():
        return None
    try:
        password = keyring.get_password(KEYRING_SERVICE, alias)
    except Exception:  # noqa: BLE001
        return None
    if password is None:
        return None
    return (server.get("username", ""), server.get("domain", ""), password)


def test_connectivity(host: str, port: int = 3389, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        socket.getaddrinfo(host, port)
    except Exception as exc:  # noqa: BLE001
        return (False, f"DNS: no resuelve {host}")
    try:
        conn = socket.create_connection((host, port), timeout=timeout)
        conn.close()
        return (True, f"TCP {port} OK")
    except Exception as exc:  # noqa: BLE001
        return (False, f"TCP {port}: {exc}")
