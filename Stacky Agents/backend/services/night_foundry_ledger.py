"""services/night_foundry_ledger.py — Plan 202 E1 (La Fragua Nocturna F0/TMV).

Bitacora JSONL durable de work items de la Fragua. EXTIENDE el patron de la casa
(`services/deploy_store.py`: lock de modulo + `data_dir()` + jsonl + tolerar JSON
corrupto) agregando escritura atomica tmp+replace, retencion por MAX_ROWS y una
ALLOWLIST estricta de campos.

PURO: cero imports de red, providers o LLM. Los datos viven en
`data_dir()/night_foundry/` (NUNCA bajo `docs/`, para no contaminar el indexador
de documentacion que hace `docs_dir.rglob("*.md")`).

Contrato CONGELADO del work item: §5.1 del plan 202.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

logger = logging.getLogger(__name__)

MAX_ROWS = 2000
MAX_ATTEMPTS = 2
_LOCK = threading.Lock()

ENTRY_FIELDS = (
    "id",           # str: identificador unico del item (uuid4 hex[:12])
    "input_hash",   # str: sha256(f"{lane}|{target}|{input_signature}")[:16]
    "lane",         # str: critic | auditor | package | reconciler | proposer
    "target",       # str: "plan:199" | "branch:impl/devops"
    "state",        # str: pending | claimed | done | failed | skipped
    "output_ref",   # str|None: ruta relativa a data_dir()/night_foundry/, sha o None
    "cost_tokens",  # int
    "attempts",     # int
    "night",        # str: YYYY-MM-DD
    "created_at",   # str: ISO-8601 UTC
    "updated_at",   # str: ISO-8601 UTC
    "error",        # str|None
)

VALID_LANES = frozenset({"critic", "auditor", "package", "reconciler", "proposer"})
VALID_STATES = frozenset({"pending", "claimed", "done", "failed", "skipped"})

# Orden de valor para el operador: primero lo que des-atasca mas.
_LANE_ORDER = {"critic": 0, "auditor": 1, "package": 2, "reconciler": 3, "proposer": 4}

# Items entregados por claim_next EN ESTE PROCESO y todavia sin resultado.
# [BUG REAL DEL PLAN 202, hallado corriendo E1] `claim_next` acepta como candidato
# tanto `pending` como `claimed` — esto ultimo es a proposito, para re-clamar los
# huerfanos de una noche que se cayo (KPI-4). Pero sin este registro, dos llamadas
# consecutivas devuelven el MISMO item (queda `claimed` y sigue siendo el primero
# por orden de carril): cualquier consumidor que no marque resultado de inmediato
# entra en bucle. El `seen` de run_night tapaba el sintoma solo dentro del loop.
# Es de PROCESO a proposito: los huerfanos de OTRA corrida no estan aca y siguen
# siendo re-clamables, que es exactamente lo que pide la resumibilidad.
_INFLIGHT: set[str] = set()


def foundry_dir() -> Path:
    d = Path(runtime_paths.data_dir()) / "night_foundry"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ledger_path() -> Path:
    return foundry_dir() / "ledger.jsonl"


def compute_input_hash(lane: str, target: str, input_signature: str) -> str:
    """Fingerprint CONGELADO de dedup/resumibilidad (§5.3)."""
    return hashlib.sha256(f"{lane}|{target}|{input_signature}".encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all() -> list[dict]:
    p = _ledger_path()
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001 — linea corrupta: saltear, nunca crashear
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _write_all(rows: list[dict]) -> None:
    rows = rows[-MAX_ROWS:]  # retencion: conservar los mas nuevos
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    target = _ledger_path()
    tmp = target.with_suffix(".jsonl.tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        os.replace(tmp, target)  # atomico en el mismo volumen
    except OSError:
        # Windows: si el operador tiene el .jsonl abierto, replace puede fallar.
        # Degradar a escritura directa antes que perder la corrida entera.
        logger.warning("night_foundry: replace atomico fallo; escritura directa")
        target.write_text(payload, encoding="utf-8")
        try:
            tmp.unlink()
        except OSError:
            pass


def _sanitize(entry: dict) -> dict:
    """ALLOWLIST estricta: cualquier clave fuera de ENTRY_FIELDS se DESCARTA.
    Garantiza que jamas se persista un secreto por accidente."""
    return {k: entry.get(k) for k in ENTRY_FIELDS}


def upsert_item(lane: str, target: str, input_hash: str, *, night: str) -> dict:
    """Encola un item `pending` salvo que el fingerprint ya este resuelto.

    Reglas §5.3: `done` -> dedup (devuelve el done, no crea); `failed` con
    attempts<MAX_ATTEMPTS -> re-encola `pending` (mismo id); `claimed` -> se deja
    (lo re-clamara `claim_next` en la proxima corrida); ausente -> crea `pending`.
    """
    if lane not in VALID_LANES:
        raise ValueError(f"lane invalido: {lane}")
    with _LOCK:
        rows = _read_all()
        for r in rows:
            if r.get("input_hash") != input_hash:
                continue
            if r.get("state") == "done":
                return r
            if r.get("state") == "failed" and int(r.get("attempts", 0) or 0) < MAX_ATTEMPTS:
                r["state"] = "pending"
                r["updated_at"] = _now()
                _write_all(rows)
                return r
            return r
        item = _sanitize({
            "id": uuid.uuid4().hex[:12], "input_hash": input_hash, "lane": lane,
            "target": target, "state": "pending", "output_ref": None, "cost_tokens": 0,
            "attempts": 0, "night": night, "created_at": _now(), "updated_at": _now(),
            "error": None,
        })
        rows.append(item)
        _write_all(rows)
        return item


def claim_next(exclude_ids: set[str] | None = None) -> dict | None:
    """Toma el primer `pending` (o `claimed` huerfano) por orden de carril y luego FIFO.

    `exclude_ids` son los ids ya vistos/salteados en ESTA corrida (p. ej. un critic
    sin dispatch o sin presupuesto). Se excluyen del candidato para NO re-clamarlos
    en bucle. La exclusion NO se persiste: la proxima noche vuelven a ser clamables.
    """
    excluded = set(exclude_ids or set())
    with _LOCK:
        excluded |= _INFLIGHT
        rows = _read_all()
        cands = [r for r in rows
                 if r.get("state") in ("pending", "claimed") and r.get("id") not in excluded]
        if not cands:
            return None
        cands.sort(key=lambda r: (_LANE_ORDER.get(r.get("lane"), 9), r.get("created_at") or ""))
        pick = cands[0]
        pick["state"] = "claimed"
        pick["attempts"] = int(pick.get("attempts", 0) or 0) + 1
        pick["updated_at"] = _now()
        _write_all(rows)
        _INFLIGHT.add(pick["id"])
        return dict(pick)


def reset_inflight() -> None:
    """Vacia el registro de items en vuelo de ESTE proceso. La usan los tests y el
    arranque de una corrida nueva; nunca toca el ledger en disco."""
    with _LOCK:
        _INFLIGHT.clear()


def record_result(item_id: str, state: str, *, output_ref=None, cost_tokens=0, error=None) -> None:
    if state not in VALID_STATES:
        raise ValueError(state)
    with _LOCK:
        rows = _read_all()
        for r in rows:
            if r.get("id") == item_id:
                r["state"] = state
                r["output_ref"] = output_ref
                r["cost_tokens"] = int(cost_tokens or 0)
                r["error"] = error
                r["updated_at"] = _now()
                break
        _write_all(rows)
        _INFLIGHT.discard(item_id)


def list_items(night: str | None = None, state: str | None = None) -> list[dict]:
    rows = _read_all()
    if night is not None:
        rows = [r for r in rows if r.get("night") == night]
    if state is not None:
        rows = [r for r in rows if r.get("state") == state]
    return rows


def spent_tokens(night: str) -> int:
    return sum(int(r.get("cost_tokens", 0) or 0)
               for r in list_items(night=night)
               if r.get("state") in ("done", "failed"))
