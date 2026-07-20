"""services/env_apply_ledger.py — Plan 198. Bitácora durable de applies de ambientes.

JSONL local (data_dir()/env_applies.jsonl) con lock y retención. RECETA CONGELADA del
Plan 191 (services/ci_run_ledger.py) aplicada a OTRO dominio: cada apply de carpetas
(local o remoto) del layout del catálogo. PURO local: cero red, cero provider, cero
import de environment_remote.

Contrato de campos (ALLOWLIST estricta ENTRY_FIELDS): jamás puede colarse un secreto
por accidente porque las claves fuera del contrato se DESCARTAN al escribir. Los `paths`
son rutas RELATIVAS del catálogo (ya visibles en la UI del plan); se capean a 200 items.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

MAX_ROWS = 500           # C4 — calca el 191: retención dura, se conservan los 500 más nuevos
_PATHS_CAP = 200         # tope de rutas persistidas por entry (privacidad + tamaño)
_LOCK = threading.Lock()

# ALLOWLIST — los únicos campos que pueden persistirse. paths_truncated lo calcula
# append_apply (nunca se confía en el valor del caller). ignored_count = ADICIÓN
# ARQUITECTO (auditoría fiel de pedido vs aprobado).
ENTRY_FIELDS: tuple[str, ...] = (
    "root", "server_alias", "paths", "paths_truncated", "fingerprint",
    "sandbox_active", "result_ok", "created_count", "ignored_count",
    "applied_at", "source",
)


def _ledger_path() -> Path:
    return Path(runtime_paths.data_dir()) / "env_applies.jsonl"


def _read_rows() -> list[dict]:
    """Lee todas las líneas válidas; tolera (saltea) líneas corruptas."""
    path = _ledger_path()
    if not path.exists():
        return []
    rows: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw)
        except Exception:  # noqa: BLE001 — línea corrupta: se salta
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _write_rows(rows: list[dict]) -> None:
    """Reescritura atómica: tmp + replace (mismo volumen)."""
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    tmp.write_text(text + ("\n" if rows else ""), encoding="utf-8")
    tmp.replace(path)


def _clean_entry(entry: dict) -> dict:
    """Proyecta SOLO ENTRY_FIELDS (ALLOWLIST). Normaliza `paths` a lista de str con
    cap _PATHS_CAP y calcula `paths_truncated`. Defaults: applied_at=now(UTC),
    source='stacky'."""
    out = {k: entry.get(k) for k in ENTRY_FIELDS}

    raw_paths = entry.get("paths") or []
    if not isinstance(raw_paths, (list, tuple)):
        raw_paths = [raw_paths]
    norm = [str(p) for p in raw_paths]
    if len(norm) > _PATHS_CAP:
        out["paths"] = norm[:_PATHS_CAP]
        out["paths_truncated"] = True
    else:
        out["paths"] = norm
        out["paths_truncated"] = False

    if not out.get("applied_at"):
        out["applied_at"] = datetime.now(timezone.utc).isoformat()
    if out.get("source") is None:
        out["source"] = entry.get("source", "stacky")
    return out


def append_apply(entry: dict) -> None:
    """Agrega un apply (best-effort desde el hook del apply). Aplica la ALLOWLIST
    ENTRY_FIELDS (claves fuera del contrato se descartan), el cap de `paths` y la
    retención MAX_ROWS en el mismo write (reescritura atómica). JAMÁS lanza al caller
    del apply: eso lo garantiza el try/except del hook en api/devops.py."""
    clean = _clean_entry(entry)
    with _LOCK:
        rows = _read_rows()
        rows.append(clean)
        if len(rows) > MAX_ROWS:
            rows = rows[-MAX_ROWS:]  # conservar los MÁS NUEVOS (últimos escritos)
        _write_rows(rows)


def list_applies(
    root: str | None = None,
    server_alias: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """Semántica EXACTA:
    (1) leer todas las líneas válidas;
    (2) si root no es None, filtrar entry["root"] == root (igualdad exacta);
    (3) si server_alias no es None, filtrar entry["server_alias"] == server_alias;
    (4) SORT por entry["applied_at"] DESCENDENTE (ISO-8601 UTC ordena
        lexicográficamente; nunca confiar en el orden del archivo);
    (5) limit acotado a [1, MAX_ROWS] (0/negativo → 1; > MAX_ROWS → MAX_ROWS)."""
    with _LOCK:
        rows = _read_rows()
    if root is not None:
        rows = [r for r in rows if r.get("root") == root]
    if server_alias is not None:
        rows = [r for r in rows if r.get("server_alias") == server_alias]
    rows.sort(key=lambda r: str(r.get("applied_at") or ""), reverse=True)
    if limit < 1:
        limit = 1
    elif limit > MAX_ROWS:
        limit = MAX_ROWS
    return rows[:limit]


def last_fingerprint(root: str, server_alias: str | None) -> str | None:
    """Fingerprint del apply MÁS RECIENTE (por applied_at) para ese (root, server_alias).
    None si no hay historial. Igualdad exacta en ambos ejes (server_alias None = local)."""
    with _LOCK:
        rows = _read_rows()
    matching = [
        r for r in rows
        if r.get("root") == root and r.get("server_alias") == server_alias
    ]
    if not matching:
        return None
    matching.sort(key=lambda r: str(r.get("applied_at") or ""), reverse=True)
    fp = matching[0].get("fingerprint")
    return fp if isinstance(fp, str) else None
