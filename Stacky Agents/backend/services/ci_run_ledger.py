"""services/ci_run_ledger.py — Plan 191. Bitácora durable de corridas CI disparadas.

JSONL local (data_dir()/ci_runs.jsonl) con lock y retención. Patrón de la casa:
deploy_store.py:98-158 / incident_store.py. PURO local: cero red, cero provider.

Contrato de campos (ALLOWLIST estricta ENTRY_FIELDS): jamás puede colarse un secreto
por accidente porque las claves fuera del contrato se DESCARTAN al escribir.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

MAX_ROWS = 500           # retención dura: al superar, se conservan los 500 más nuevos
_LOCK = threading.Lock()

# ALLOWLIST — los únicos campos que pueden persistirse. last_status/finished_at los
# escribe SOLO update_run_status; append_run los inicializa en None.
ENTRY_FIELDS: tuple[str, ...] = (
    "project", "tracker_type", "ref", "sha", "pipeline_id",
    "web_url", "triggered_at", "source", "last_status", "finished_at",
)


def _ledger_path() -> Path:
    return Path(runtime_paths.data_dir()) / "ci_runs.jsonl"


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
    """Proyecta SOLO ENTRY_FIELDS; last_status/finished_at inicializados en None."""
    out = {k: entry.get(k) for k in ENTRY_FIELDS}
    if not out.get("triggered_at"):
        out["triggered_at"] = datetime.now(timezone.utc).isoformat()
    if "source" not in entry or out.get("source") is None:
        out["source"] = entry.get("source", "stacky")
    return out


def append_run(entry: dict) -> None:
    """Agrega una corrida (best-effort desde el hook del trigger). Aplica la ALLOWLIST
    ENTRY_FIELDS (claves fuera del contrato se descartan) y la retención MAX_ROWS en el
    mismo write (reescritura atómica)."""
    clean = _clean_entry(entry)
    with _LOCK:
        rows = _read_rows()
        rows.append(clean)
        if len(rows) > MAX_ROWS:
            rows = rows[-MAX_ROWS:]  # conservar las MÁS NUEVAS (últimas escritas)
        _write_rows(rows)


def list_runs(project: str | None = None, limit: int = 50) -> list[dict]:
    """C2 — semántica EXACTA:
    (1) leer todas las líneas válidas;
    (2) si project no es None, filtrar entry["project"] == project (igualdad exacta);
    (3) SORT por entry["triggered_at"] DESCENDENTE (ISO-8601 UTC ordena
        lexicográficamente; nunca confiar en el orden del archivo);
    (4) limit acotado a [1, MAX_ROWS] (0/negativo → 1; > MAX_ROWS → MAX_ROWS)."""
    with _LOCK:
        rows = _read_rows()
    if project is not None:
        rows = [r for r in rows if r.get("project") == project]
    rows.sort(key=lambda r: str(r.get("triggered_at") or ""), reverse=True)
    if limit < 1:
        limit = 1
    elif limit > MAX_ROWS:
        limit = MAX_ROWS
    return rows[:limit]


def update_run_status(pipeline_id: str, status: str, finished_at: str | None = None) -> bool:
    """[ADICIÓN ARQUITECTO] — setea last_status (+ finished_at si viene) del entry con
    ese pipeline_id (el más reciente por triggered_at si hubiera duplicados). Reescritura
    atómica bajo _LOCK. Devuelve False (no-op silencioso) si el id no está. Solo estos 2
    campos son actualizables."""
    with _LOCK:
        rows = _read_rows()
        # candidatos con ese pipeline_id
        idxs = [i for i, r in enumerate(rows) if str(r.get("pipeline_id")) == str(pipeline_id)]
        if not idxs:
            return False
        # el más reciente por triggered_at
        target = max(idxs, key=lambda i: str(rows[i].get("triggered_at") or ""))
        rows[target]["last_status"] = status
        if finished_at is not None:
            rows[target]["finished_at"] = finished_at
        _write_rows(rows)
        return True
