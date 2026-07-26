"""Plan 176 F1 — Triage del diff: la decisión humana sobre cada diferencia.

Comparar dos bases produce ruido: diferencias que hay que migrar mezcladas con
otras que son legítimas (una tabla de prueba, algo ya migrado a mano, un objeto
obsoleto). Hasta ahora eso se curaba en un markdown fuera del producto. Acá cada
ítem lleva su decisión — confirmado, excluido o pendiente — con nota y fecha,
persistida por corrida, y los generadores de scripts la respetan.

Contrato Triage v1 (`data_dir()/db_compare/triage/<run_id>.json`):

    {"version": 1, "run_id": "...", "items": {"<item_key>": {...}}, "updated_at": "..."}

La `item_key` es estable entre corridas del mismo par (no lleva run_id ni
timestamps): re-comparar no pierde lo que el operador ya decidió.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir
from services.dbcompare_sqlvalues import normalize_value

__all__ = [
    "DECISIONS",
    "TRIAGE_VERSION",
    "item_key_for_schema_item",
    "item_key_for_data_row",
    "load_triage",
    "set_decision",
    "triage_summary",
    "excluded_keys",
    "attach_item_keys",
    "exclusions_markdown",
]

DECISIONS = ("confirmado", "excluido", "pendiente")
TRIAGE_VERSION = 1
_NOTE_MAX_CHARS = 2000

# El run_id llega por URL y se usa como nombre de archivo: se restringe al
# alfabeto que produce dbcompare_runs, así no hay forma de escribir fuera.
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


def _triage_dir() -> Path:
    return Path(data_dir()) / "db_compare" / "triage"


def _path_for(run_id: str) -> Path:
    if not run_id or not _RUN_ID_RE.match(str(run_id)):
        raise ValueError(f"run_id inválido: {run_id!r}")
    return _triage_dir() / f"{run_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Claves de ítem
# ---------------------------------------------------------------------------

def item_key_for_schema_item(item: dict) -> str:
    """`<object_type>:<schema>.<name>` — estable entre corridas del mismo par."""
    return "{}:{}.{}".format(
        (item or {}).get("object_type") or "",
        (item or {}).get("schema") or "",
        (item or {}).get("name") or "",
    )


def item_key_for_data_row(schema: str, table: str, pk: dict) -> str:
    """`data:<schema>.<table>:<pk canónica>`.

    La PK se normaliza con la MISMA función que usa el diff de datos, así la key
    no cambia porque un driver devuelva 1 y otro Decimal('1').
    """
    canon = {str(k): normalize_value(v) for k, v in (pk or {}).items()}
    return "data:{}.{}:{}".format(
        schema or "", table or "",
        json.dumps(canon, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
    )


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------

def _empty(run_id: str) -> dict:
    return {"version": TRIAGE_VERSION, "run_id": run_id, "items": {}, "updated_at": None}


def load_triage(run_id: str) -> dict:
    """Devuelve el doc Triage v1. Nunca lanza: sin archivo o corrupto ⇒ vacío."""
    try:
        path = _path_for(run_id)
        if not path.is_file():
            return _empty(run_id)
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("items"), dict):
            return _empty(run_id)
        doc.setdefault("version", TRIAGE_VERSION)
        doc.setdefault("run_id", run_id)
        doc.setdefault("updated_at", None)
        return doc
    except Exception:  # noqa: BLE001 — leer el triage nunca puede tumbar el GET
        return _empty(run_id)


def set_decision(run_id: str, item_key: str, decision: str, note: str = "") -> dict:
    """Registra (o borra) la decisión de un ítem y devuelve el doc completo.

    `pendiente` no se guarda: es la ausencia de decisión. Guardarlo dejaría dos
    representaciones del mismo estado y el resumen empezaría a mentir.
    """
    if decision not in DECISIONS:
        raise ValueError(f"decisión inválida: {decision!r} (válidas: {DECISIONS})")

    path = _path_for(run_id)
    doc = load_triage(run_id)

    if decision == "pendiente":
        doc["items"].pop(item_key, None)
    else:
        doc["items"][item_key] = {
            "decision": decision,
            "note": (note or "")[:_NOTE_MAX_CHARS],
            "decided_at": _now_iso(),
        }
    doc["updated_at"] = _now_iso()

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return doc


# ---------------------------------------------------------------------------
# Lecturas derivadas
# ---------------------------------------------------------------------------

def triage_summary(triage: dict, total_items: int) -> dict:
    """Cuántos confirmados, excluidos y cuántos quedan sin decidir."""
    decisiones = [v.get("decision") for v in (triage or {}).get("items", {}).values()]
    confirmados = sum(1 for d in decisiones if d == "confirmado")
    excluidos = sum(1 for d in decisiones if d == "excluido")
    return {
        "confirmado": confirmados,
        "excluido": excluidos,
        # max(0, …): si el diff encogió entre corridas, un negativo sería mentira.
        "pendiente": max(0, int(total_items or 0) - confirmados - excluidos),
    }


def excluded_keys(triage: dict) -> set[str]:
    return {
        k for k, v in (triage or {}).get("items", {}).items()
        if v.get("decision") == "excluido"
    }


def _pk_from_row(row: dict, pk_cols: list) -> dict:
    return {c: row.get(c) for c in (pk_cols or []) if c in row}


def attach_item_keys(run: dict) -> dict:
    """Agrega `item_key` a cada ítem del diff y a cada fila del data-diff, in place.

    Tiene que correr ANTES del enmascarado (plan 181): ese enmascara los valores
    de PK, así que el frontend no puede derivar la key de una fila de datos. El
    backend es el único emisor posible.
    """
    if not isinstance(run, dict):
        return run

    try:
        items = ((run.get("diff") or {}).get("items")) or []
        for item in items:
            if isinstance(item, dict):
                item["item_key"] = item_key_for_schema_item(item)
    except Exception:  # noqa: BLE001
        pass

    try:
        tablas = ((run.get("data_diff") or {}).get("tables")) or {}
        for tabla in tablas.values():
            if not isinstance(tabla, dict) or tabla.get("error"):
                continue
            schema = tabla.get("schema") or ""
            nombre = tabla.get("table") or ""
            pk_cols = tabla.get("pk_cols") or []
            for lado in ("only_source", "only_target"):
                for fila in tabla.get(lado) or []:
                    if isinstance(fila, dict):
                        fila["item_key"] = item_key_for_data_row(
                            schema, nombre, _pk_from_row(fila, pk_cols))
            for cambio in tabla.get("changed") or []:
                if isinstance(cambio, dict):
                    cambio["item_key"] = item_key_for_data_row(
                        schema, nombre, cambio.get("pk") or {})
    except Exception:  # noqa: BLE001
        pass

    return run


def exclusions_markdown(run_id: str, triage: dict) -> str:
    """Markdown determinista con lo que el operador decidió NO migrar."""
    excluidos = sorted(
        (k, v) for k, v in (triage or {}).get("items", {}).items()
        if v.get("decision") == "excluido"
    )

    lineas = [f"# Exclusiones del triage — {run_id}", ""]
    if not excluidos:
        lineas.append("Sin exclusiones.")
        return "\n".join(lineas) + "\n"

    lineas += [f"{len(excluidos)} ítem(s) marcados para NO migrar.", "",
               "| Ítem | Nota | Decidido |", "|---|---|---|"]
    for key, dato in excluidos:
        nota = (dato.get("note") or "").replace("|", "\\|").replace("\n", " ")
        lineas.append(f"| `{key}` | {nota or '—'} | {dato.get('decided_at') or '—'} |")
    return "\n".join(lineas) + "\n"
