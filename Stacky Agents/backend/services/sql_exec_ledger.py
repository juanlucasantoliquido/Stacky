"""Plan 200 R4 — Bitácora append-only de ejecuciones SQL por ambiente.

Ejecutar un script contra una base es irreversible. Lo mínimo que se le debe al
operador es poder responder, meses después y sin dudar: *qué* se corrió, *dónde*,
*cuándo* y *con qué resultado*.

Por eso la bitácora es **tamper-evident**: cada entrada encadena el hash de la
anterior. No impide que alguien edite el archivo — impide que lo edite sin que se
note, que es lo que importa cuando la pregunta es "¿esto se ejecutó en PROD o no?".

Calca la receta del Plan 198 (JSONL en `data_dir()`, escritura atómica, líneas
corruptas salteadas) y le suma la cadena de hash.
"""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

_LOCK = threading.Lock()
MAX_ROWS = 500
_LEDGER_REL = "db_compare/sql_exec_ledger.jsonl"

# ALLOWLIST estricta: cualquier clave fuera de esta lista se DESCARTA. Es la
# garantía de que un secreto no entra a la bitácora "por accidente" porque
# alguien lo agregó al dict de la llamada.
ENTRY_FIELDS = (
    "alias", "engine", "ticket_ref", "incident_id", "script_sha256", "statement_count",
    "dry_run", "result_ok", "rows_affected", "error", "duration_ms", "executed_by",
    "executed_at", "source", "prev_hash", "entry_hash",
)


def _path() -> Path:
    return runtime_paths.data_dir() / _LEDGER_REL


def _canonical(entry: dict) -> str:
    """Serialización estable para hashear: sin `entry_hash`, claves ordenadas."""
    body = {k: entry.get(k) for k in ENTRY_FIELDS if k != "entry_hash"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _hash(prev_hash: str, entry: dict) -> str:
    return hashlib.sha256((prev_hash + _canonical(entry)).encode("utf-8")).hexdigest()


def _read_all() -> list[dict]:
    ruta = _path()
    if not ruta.exists():
        return []
    filas: list[dict] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            fila = json.loads(linea)
        except (ValueError, TypeError):
            # Una línea corrupta no puede tapar la bitácora entera: se saltea.
            # La cadena la va a marcar como rota, que es el aviso correcto.
            continue
        if isinstance(fila, dict):
            filas.append(fila)
    return filas


def _write_all(filas: list[dict]) -> None:
    ruta = _path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".jsonl.tmp")
    tmp.write_text(
        "".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas),
        encoding="utf-8",
    )
    tmp.replace(ruta)


def append_exec(entry: dict) -> None:
    with _LOCK:
        filas = _read_all()
        prev_hash = filas[-1].get("entry_hash") if filas else "GENESIS"
        limpio = {k: entry.get(k) for k in ENTRY_FIELDS if k not in ("prev_hash", "entry_hash")}
        limpio["executed_at"] = entry.get("executed_at") or datetime.now(timezone.utc).isoformat()
        limpio["source"] = entry.get("source") or "stacky"
        limpio["dry_run"] = bool(entry.get("dry_run", False))
        limpio["prev_hash"] = prev_hash
        limpio["entry_hash"] = _hash(prev_hash, limpio)
        filas.append(limpio)
        _write_all(filas[-MAX_ROWS:])


def list_execs(alias=None, ticket_ref=None, script_sha256=None, limit=50) -> list[dict]:
    filas = _read_all()
    if alias is not None:
        filas = [r for r in filas if r.get("alias") == alias]
    if ticket_ref is not None:
        filas = [r for r in filas if r.get("ticket_ref") == ticket_ref]
    if script_sha256 is not None:
        filas = [r for r in filas if r.get("script_sha256") == script_sha256]
    filas.sort(key=lambda r: r.get("executed_at") or "", reverse=True)
    return filas[: max(1, min(limit, MAX_ROWS))]


def find_executed(alias: str, script_sha256: str) -> dict | None:
    """La ejecución REAL y exitosa más reciente de ese script en ese ambiente.

    Un dry-run no cuenta (no tocó nada) y un fallo tampoco (no quedó aplicado):
    tratarlos como "ya ejecutado" bloquearía el reintento legítimo.
    """
    for r in list_execs(alias=alias, script_sha256=script_sha256, limit=MAX_ROWS):
        if r.get("result_ok") and not r.get("dry_run"):
            return r
    return None


def verify_chain() -> bool:
    """False si alguien editó, borró o reordenó una línea."""
    filas = _read_all()
    prev = "GENESIS"
    for r in filas:
        cuerpo = {k: r.get(k) for k in ENTRY_FIELDS if k != "entry_hash"}
        cuerpo["prev_hash"] = prev
        if _hash(prev, cuerpo) != r.get("entry_hash"):
            return False
        prev = r.get("entry_hash")
    return True
