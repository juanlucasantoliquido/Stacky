"""services/dbcompare_config_import.py — Plan 157 F1/F2: agente local determinista
que parsea connection strings de `web.config`/XMLConfig (o un datasource suelto) del
producto RS y devuelve las conexiones detectadas con la contraseña SEPARADA y
enmascarable.

SEGURIDAD (Plan 157 §3.2, instrucción de la organización):
  - Parseo 100% LOCAL, sin red, sin LLM: solo stdlib (`xml.etree.ElementTree` + str).
    Este módulo NO importa requests/urllib/socket ni nada de LLM.
  - La contraseña en claro existe SOLO como valor de retorno de las funciones de
    parseo y como valor transitorio del cache de import (F2). NUNCA es atributo de
    `ParsedConnection`, NUNCA está en `masked_raw`, NUNCA se persiste a disco.
  - `masked_raw` es el ÚNICO string derivado del crudo que puede ir a logs/UI:
    reemplaza el value de cualquier key sensible por `****`.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

# Keys cuyo value es una credencial (case-insensitive).
SENSITIVE_KEYS = ("password", "pwd")


@dataclass
class ParsedConnection:
    """Conexión detectada. NUNCA contiene la contraseña en claro (va aparte)."""

    name: str = ""
    engine: str = ""  # "sqlserver" | "oracle" | "" (no inferible → el operador elige)
    host: str = ""
    port: int | None = None
    database: str = ""
    username: str = ""
    integrated_security: bool = False
    has_password: bool = False
    masked_raw: str = ""


def _split_kv(raw: str) -> dict[str, str]:
    """Parte por `;`; cada par por el primer `=`. Keys → lower+trim; values → trim.
    Duplicados: gana el último."""
    out: dict[str, str] = {}
    for segment in raw.split(";"):
        if "=" not in segment:
            continue
        k, v = segment.split("=", 1)
        key = k.strip().lower()
        if key:
            out[key] = v.strip()
    return out


def _to_int_or_none(text: str) -> int | None:
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def _infer_engine(provider_name: str, keys: dict[str, str]) -> str:
    """Reglas LITERALES en orden (Plan 157 F1, C1 v2 + resolución de contradicción
    interna del plan: el set SQL-Server-positivo incluye `server`/`database` porque
    el test `test_sqlserver_user_pass` los usa; Oracle sigue SIN adivinarse por vibra)."""
    pn = (provider_name or "").lower()
    if "oracle" in pn:
        return "oracle"
    if "sqlclient" in pn or "sqlserver" in pn:
        return "sqlserver"
    # Sin provider concluyente: mirar las keys ya parseadas.
    # SQL-Server-positivas (todas literales, ninguna aplica a Oracle EZConnect/TNS).
    if any(k in keys for k in ("initial catalog", "integrated security", "server", "database")):
        return "sqlserver"
    # Oracle SOLO por señal literal fuerte (C1 v2): EZConnect lleva `/`, TNS descriptor
    # empieza con `(description=`.
    ds = keys.get("data source", "")
    if "/" in ds or "(description=" in ds.lower():
        return "oracle"
    return ""


def _sqlserver_host_port_db(keys: dict[str, str]) -> tuple[str, int | None, str]:
    ds = ""
    for cand in ("data source", "server", "addr", "address"):
        val = keys.get(cand, "")
        if val:
            ds = val
            break
    host = ds.strip()
    port: int | None = None
    if "," in ds:  # host,puerto — gana sobre instancia nombrada (host\INST,1433)
        host_part, port_part = ds.split(",", 1)
        host = host_part.strip()
        port = _to_int_or_none(port_part)
    elif "\\" in ds:  # instancia nombrada: host completo, sin puerto
        host = ds.strip()
        port = None
    database = keys.get("initial catalog") or keys.get("database") or ""
    return host, port, database.strip()


def _oracle_host_port_db(keys: dict[str, str]) -> tuple[str, int | None, str]:
    ds = keys.get("data source", "")
    if "/" in ds:
        left, service = ds.split("/", 1)
        database = service.strip()
        if ":" in left:
            host_part, port_str = left.rsplit(":", 1)
            return host_part.strip(), _to_int_or_none(port_str), database
        return left.strip(), None, database
    return ds.strip(), None, ""


def _mask(raw: str) -> str:
    """Reconstruye el crudo reemplazando el value de las keys sensibles por `****`.
    Preserva el texto de la key y el resto de los segmentos."""
    out: list[str] = []
    for segment in raw.split(";"):
        if "=" in segment:
            k, v = segment.split("=", 1)
            if k.strip().lower() in SENSITIVE_KEYS and v.strip() != "":
                out.append(f"{k}=****")
                continue
        out.append(segment)
    return ";".join(out)


def parse_connection_string(
    raw: str, provider_name: str = "", name: str = ""
) -> tuple[ParsedConnection, str | None]:
    """Devuelve (ParsedConnection, password_o_None). La password en claro se
    retorna POR SEPARADO — nunca dentro de ParsedConnection ni en masked_raw."""
    keys = _split_kv(raw or "")
    engine = _infer_engine(provider_name, keys)

    password: str | None = None
    for sk in SENSITIVE_KEYS:
        val = keys.get(sk, "")
        if val != "":
            password = val
            break

    intsec = keys.get("integrated security", "").strip().lower()
    integrated_security = intsec in ("sspi", "true", "yes")
    has_password = bool(password)
    if integrated_security:
        has_password = False

    if engine == "oracle":
        host, port, database = _oracle_host_port_db(keys)
    else:  # "sqlserver" o "" → parseo estilo SQL Server (default seguro)
        host, port, database = _sqlserver_host_port_db(keys)

    username = keys.get("user id") or keys.get("uid") or keys.get("user") or ""

    pc = ParsedConnection(
        name=name or "",
        engine=engine,
        host=host,
        port=port,
        database=database,
        username=username.strip(),
        integrated_security=integrated_security,
        has_password=has_password,
        masked_raw=_mask(raw or ""),
    )
    return pc, password


def parse_webconfig(xml_text: str) -> list[tuple[ParsedConnection, str | None]]:
    """Parsea `<connectionStrings><add name= connectionString= providerName=/>`.
    Degrada a [] si el XML es inválido (NUNCA lanza)."""
    try:
        root = ET.fromstring(xml_text)
    except Exception:  # noqa: BLE001 — XML inválido: degradar a vacío, sin crash
        return []
    results: list[tuple[ParsedConnection, str | None]] = []
    for elem in root.iter():
        tag = elem.tag.split("}")[-1]  # descartar namespace {...}add
        if tag != "add":
            continue
        cs = elem.get("connectionString")
        if not cs:
            continue  # <add key= value=> de appSettings u otro: se ignora
        results.append(
            parse_connection_string(
                cs, provider_name=elem.get("providerName") or "", name=elem.get("name") or ""
            )
        )
    return results


def preview_dict(pc: ParsedConnection) -> dict:
    """Dict SEGURO para viajar al browser: campos estructurados SIN password y SIN
    `masked_raw`. Excluir masked_raw es deliberado — contiene `Password=****`, que el
    detector de egreso (`\\S{4,}` tras `password=`) marcaría como secreto y dispararía
    el self-check fail-closed (F2/F3). El wizard usa los campos estructurados, no el
    crudo enmascarado."""
    d = asdict(pc)
    d.pop("masked_raw", None)
    return d


# ──────────────────────────────────────────────────────────────────────────────
# Cache transitoria de import (Plan 157 F2). El password vive SOLO acá, en memoria
# del proceso, con TTL y cap. NUNCA a disco.
# ──────────────────────────────────────────────────────────────────────────────

_IMPORT_CACHE: dict[str, dict] = {}
_CACHE_LOCK = threading.Lock()
_MAX_IMPORTS = 32
_TTL_SEC = 600


def sweep_expired(ttl_sec: int = _TTL_SEC) -> None:
    """Borra toda entrada con antigüedad > ttl_sec. Invocada lazy desde
    stash_parsed/pop_parsed (C3 v2: no requiere thread de background)."""
    now = time.monotonic()
    with _CACHE_LOCK:
        expired = [k for k, v in _IMPORT_CACHE.items() if now - v.get("ts", now) > ttl_sec]
        for k in expired:
            _IMPORT_CACHE.pop(k, None)


def stash_parsed(conns_with_pw: list[tuple[ParsedConnection, str | None]]) -> str:
    """Guarda las conexiones+passwords transitoriamente y devuelve un import_id."""
    sweep_expired()  # barrido lazy PRIMERO (C3 v2)
    with _CACHE_LOCK:
        if len(_IMPORT_CACHE) >= _MAX_IMPORTS:
            # descartar la entrada más vieja (cap anti-crecimiento, C3 v2)
            oldest = min(_IMPORT_CACHE, key=lambda k: _IMPORT_CACHE[k].get("ts", 0.0))
            _IMPORT_CACHE.pop(oldest, None)
        import_id = uuid.uuid4().hex
        _IMPORT_CACHE[import_id] = {
            "ts": time.monotonic(),
            "items": list(conns_with_pw),
        }
    return import_id


def pop_parsed(import_id: str, index: int) -> tuple[ParsedConnection | None, str | None]:
    """Recupera items[index] y lo reemplaza por un tombstone (None, None) DENTRO de la
    entrada (descarta SOLO ese índice, C4 v2 — permite confirmar 2+ conexiones del
    mismo web.config). Si todos los índices quedaron consumidos, borra la entrada. Si
    no existe o el índice ya fue consumido/es inválido → (None, None)."""
    sweep_expired()
    with _CACHE_LOCK:
        entry = _IMPORT_CACHE.get(import_id)
        if entry is None:
            return None, None
        items = entry["items"]
        if index < 0 or index >= len(items):
            return None, None
        pc, pw = items[index]
        if pc is None:  # ya consumido (tombstone)
            return None, None
        items[index] = (None, None)
        if all(it[0] is None for it in items):
            _IMPORT_CACHE.pop(import_id, None)
        return pc, pw


def _cache_size() -> int:
    """Solo para tests."""
    with _CACHE_LOCK:
        return len(_IMPORT_CACHE)


def _clear_cache() -> None:
    """Solo para tests: deja el cache en estado limpio."""
    with _CACHE_LOCK:
        _IMPORT_CACHE.clear()
