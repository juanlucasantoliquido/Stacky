"""services/ci_run_ledger.py — Plan 191. Bitácora durable de corridas CI disparadas.

JSONL local (data_dir()/ci_runs.jsonl) con lock y retención. Patrón de la casa:
deploy_store.py:98-158 / incident_store.py. PURO local: cero red, cero provider.

Contrato de campos (ALLOWLIST estricta ENTRY_FIELDS): jamás puede colarse un secreto
por accidente porque las claves fuera del contrato se DESCARTAN al escribir.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import runtime_paths
from services.ledger_writer import ENV_PROD, event_env, stamp_event

logger = logging.getLogger("stacky.ci_run_ledger")

MAX_ROWS = 500           # retención dura: al superar, se conservan los 500 más nuevos
_LOCK = threading.Lock()

# ALLOWLIST — los únicos campos que pueden persistirse. last_status/finished_at los
# escribe SOLO update_run_status; append_run los inicializa en None.
# Plan 258 F1 — `env` y `schema_version` son ADITIVOS y van acá SÍ o SÍ: la
# allowlist es cerrada (`_clean_entry` proyecta solo estas claves), así que un
# campo que no esté declarado se DESCARTA EN SILENCIO al escribir (plan 258 C4).
ENTRY_FIELDS: tuple[str, ...] = (
    "project", "tracker_type", "ref", "sha", "pipeline_id",
    "web_url", "triggered_at", "source", "last_status", "finished_at",
    "env", "schema_version",
)


def _ledger_path() -> Path:
    # Plan 258 F1 — la ruta la decide el portero: en test-mode se aísla y jamás
    # cae en backend/data/. El mecanismo de escritura de acá NO se toca.
    from services.ledger_writer import ledger_path
    return ledger_path("ci_runs")


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
    mismo write (reescritura atómica).

    Plan 258 F1 — se sella DESPUÉS de `_clean_entry` (desviación documentada del
    texto del plan, que decía "antes"): `_clean_entry` es quien completa
    `triggered_at`, que es una clave OBLIGATORIA. Sellando antes, un trigger
    legítimo que no trae `triggered_at` sería rechazado por el propio portero.
    Como `env`/`schema_version` ya están en ENTRY_FIELDS, un `env` explícito del
    llamador también sobrevive a la proyección."""
    clean = stamp_event("ci_runs", _clean_entry(entry))
    if clean is None:
        return                      # evento inválido: no se escribe, ya se logueó a error
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


def update_run_status(pipeline_id: str, status: str, finished_at: str | None = None,
                      project: str | None = None) -> bool:
    """[ADICIÓN ARQUITECTO] — setea last_status (+ finished_at si viene) del entry con
    ese pipeline_id (el más reciente por triggered_at si hubiera duplicados). Reescritura
    atómica bajo _LOCK. Devuelve False (no-op silencioso) si el id no está. Solo estos 2
    campos son actualizables.

    Plan 258 F3 — BUG REAL corregido: la reconciliación era SOLO por
    `pipeline_id`, y en la evidencia medida el id 42 se repite 6 veces entre
    proyectos, así que el cierre de un proyecto podía escribirse sobre la corrida
    de otro. Con `project` la clave es `(project, pipeline_id)`.

    BACKWARD-COMPATIBLE: `project=None` conserva EXACTAMENTE el comportamiento
    anterior (el más reciente con ese id, sin importar el proyecto) y deja un
    warning. Ningún llamador viejo se rompe."""
    with _LOCK:
        rows = _read_rows()
        # candidatos con ese pipeline_id
        idxs = [i for i, r in enumerate(rows) if str(r.get("pipeline_id")) == str(pipeline_id)]
        if project is None:
            if len(idxs) > 1:
                logger.warning(
                    "update_run_status(%s) sin project y hay %d corridas con ese id: "
                    "se cierra la más reciente. Pasá project para reconciliar exacto.",
                    pipeline_id, len(idxs),
                )
        else:
            idxs = [i for i in idxs if str(rows[i].get("project")) == str(project)]
        if not idxs:
            return False
        # el más reciente por triggered_at
        target = max(idxs, key=lambda i: str(rows[i].get("triggered_at") or ""))
        rows[target]["last_status"] = status
        if finished_at is not None:
            rows[target]["finished_at"] = finished_at
        _write_rows(rows)
        return True


def _parse_iso(valor: object) -> datetime | None:
    """ISO-8601 tolerante. Un `triggered_at` ilegible NO es un huérfano: no se
    puede afirmar su edad, y este plan no inventa datos."""
    if not isinstance(valor, str) or not valor.strip():
        return None
    crudo = valor.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(crudo)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def orphan_ci_runs(*, older_than_h: float = 24.0, now: datetime | None = None) -> list[dict]:
    """Plan 258 F3 — corridas de CI con env='prod' sin `last_status` y con más de
    `older_than_h` horas desde `triggered_at`. `now` es inyectable para que el
    test no dependa del reloj.

    SOLO 'prod' (plan 258 C11): las 8 líneas de fixture de hoy tienen todas más
    de 24 h y contaminarían el reporte desde el minuto uno. `unknown` tampoco
    entra: no hay evidencia de que sea una corrida real del operador.

    Hoy este reporte devuelve **0 huérfanos** — y esa es la verdad: no hay ni una
    corrida real en el ledger. El mecanismo de cierre ya existe y ya está
    cableado (`update_run_status` + `api/ci.py`); lo que faltaba era VISIBILIDAD.
    """
    from services.ledger_writer import _flag  # noqa: PLC0415

    if not _flag("STACKY_LEDGER_ORPHAN_REPORT_ENABLED", True):
        return []

    ahora = now or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        ahora = ahora.replace(tzinfo=timezone.utc)
    corte = ahora - timedelta(hours=float(older_than_h))

    with _LOCK:
        rows = _read_rows()

    huerfanos: list[dict] = []
    for fila in rows:
        if event_env("ci_runs", fila) != ENV_PROD:
            continue
        if fila.get("last_status"):
            continue
        disparo = _parse_iso(fila.get("triggered_at"))
        if disparo is None or disparo > corte:
            continue
        huerfanos.append({
            "project": fila.get("project"),
            "tracker_type": fila.get("tracker_type"),
            "pipeline_id": fila.get("pipeline_id"),
            "ref": fila.get("ref"),
            "web_url": fila.get("web_url"),
            "triggered_at": fila.get("triggered_at"),
            "age_hours": round((ahora - disparo).total_seconds() / 3600.0, 1),
        })
    huerfanos.sort(key=lambda h: h["age_hours"], reverse=True)
    return huerfanos
