"""Plan 176 F7 — ¿La migración quedó completa, y no tocó lo que no debía?

Después de correr los scripts, el operador queda con una pregunta que hoy nadie
contesta con evidencia: ¿se aplicó todo lo que confirmé, y sigue intacto todo lo
que excluí? El replay de Pacífico lo verificaba re-comparando y aseverando el
residual. Esto lo hace desde el triage.

Las expectativas salen solas de lo que el operador ya decidió:

    confirmado  ⇒ esa diferencia TIENE que haber desaparecido
    excluido    ⇒ esa diferencia TIENE que seguir ahí
    pendiente   ⇒ no se afirma nada (no decidió, no se le inventa una expectativa)

Que un excluido siga difiriendo no es un fallo: es la prueba de que la migración
respetó la curación. Al revés —un excluido que desapareció— sí lo es.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir
from services.dbcompare_triage import item_key_for_schema_item

__all__ = [
    "CLOSURE_VERSION",
    "derive_expectations",
    "evaluate_closure",
    "start_closure",
    "load_linkage",
]

CLOSURE_VERSION = 1

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")


def _closure_dir() -> Path:
    return Path(data_dir()) / "db_compare" / "closure"


def _path_for(run_id: str) -> Path:
    if not run_id or not _RUN_ID_RE.match(str(run_id)):
        raise ValueError(f"run_id inválido: {run_id!r}")
    return _closure_dir() / f"{run_id}.json"


# ---------------------------------------------------------------------------
# Puro
# ---------------------------------------------------------------------------

def derive_expectations(old_diff: dict, triage: dict) -> list:
    """Traduce las decisiones del operador a expectativas verificables."""
    decisiones = (triage or {}).get("items") or {}
    esperadas: list = []

    for item in (old_diff or {}).get("items") or []:
        clave = item_key_for_schema_item(item)
        decision = (decisiones.get(clave) or {}).get("decision")
        if decision == "confirmado":
            esperadas.append({"item_key": clave, "expectation": "resuelto"})
        elif decision == "excluido":
            esperadas.append({"item_key": clave, "expectation": "persiste"})
        # pendiente: no se afirma nada. Inventarle una expectativa a algo que el
        # operador no decidió sería fabricar un veredicto.

    esperadas.sort(key=lambda e: e["item_key"])
    return esperadas


def evaluate_closure(old_run: dict, new_run: dict, triage: dict) -> dict:
    """Compara las expectativas contra el diff nuevo. Puro y determinista."""
    old_diff = (old_run or {}).get("diff") or {}
    nuevas = {
        item_key_for_schema_item(i)
        for i in ((new_run or {}).get("diff") or {}).get("items") or []
    }

    esperadas = derive_expectations(old_diff, triage)
    resultados: list = []
    for e in esperadas:
        presente = e["item_key"] in nuevas
        if e["expectation"] == "resuelto":
            estado = "ok" if not presente else "violado"
        else:
            estado = "ok" if presente else "violado"
        resultados.append({**e, "status": estado})

    total_items = len((old_diff.get("items") or []))
    return {
        "version": CLOSURE_VERSION,
        "old_run_id": (old_run or {}).get("run_id"),
        "verification_run_id": (new_run or {}).get("run_id"),
        "results": resultados,
        "summary": {
            "ok": sum(1 for r in resultados if r["status"] == "ok"),
            "violado": sum(1 for r in resultados if r["status"] == "violado"),
            "sin_expectativa": max(0, total_items - len(resultados)),
        },
    }


# ---------------------------------------------------------------------------
# Linkage persistido
# ---------------------------------------------------------------------------

def load_linkage(old_run_id: str) -> dict | None:
    try:
        path = _path_for(old_run_id)
        if not path.is_file():
            return None
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _persistir_linkage(old_run_id: str, verification_run_id: str) -> dict:
    doc = {
        "version": CLOSURE_VERSION,
        "old_run_id": old_run_id,
        "verification_run_id": verification_run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _path_for(old_run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return doc


def start_closure(old_run_id: str) -> dict:
    """Lanza el re-compare de verificación y lo deja linkeado a la corrida vieja.

    Se marca `initiated_by="closure"` para que en la línea de tiempo se distinga
    del radar automático y de una comparación que pidió el operador.
    """
    from services import dbcompare_runs

    viejo = dbcompare_runs.get_run(old_run_id)
    if viejo is None:
        raise ValueError(f"run_not_found:{old_run_id}")
    if viejo.get("status") != "done":
        raise ValueError(f"run_not_done:{viejo.get('status')}")

    nuevo = dbcompare_runs.create_run(
        viejo.get("source_alias") or "",
        viejo.get("target_alias") or "",
        mode="fresh",
        initiated_by="closure",
    )
    verification_run_id = nuevo.get("run_id")
    _persistir_linkage(old_run_id, verification_run_id)
    return {"verification_run_id": verification_run_id}
