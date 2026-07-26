"""Plan 176 F4 — Precondiciones read-only derivadas del diff de esquema.

Poner un NOT NULL sobre una columna que tiene NULLs, o crear una PK sobre datos
duplicados, hace fallar el ALTER a mitad de la migración. El replay de Pacífico
lo chequeaba a mano en PowerShell antes de correr nada. Este módulo deriva esas
consultas del propio diff, para que el operador las corra ANTES y no descubra el
problema con la migración empezada.

Dos garantías que no se negocian:

1. **Derivar y exportar son puros.** No abren conexión ni ejecutan nada. La
   ejecución vive en `evaluate_gates` y solo pasa cuando el operador la pide.
2. **Toda gate pasa por `validate_select_only` antes de ejecutarse**, gate por
   gate. La garantía de solo-lectura es ESE guard, no una propiedad del motor.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir
from services import dbcompare_sqlnames as sqlnames

logger = logging.getLogger("stacky.services.dbcompare_gates")

__all__ = [
    "GATES_VERSION",
    "derive_gates",
    "evaluate_gates",
    "gates_export_sql",
    "load_results",
]

GATES_VERSION = 1
_MAX_GATES_PER_EVAL = 50

_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,200}$")

# Tabla CERRADA: kind del diff → tipo de gate. Los nombres se copian LITERALES de
# `_KIND_SEVERITY` (services/dbcompare_diff.py) y hay un test anti-drift que lo
# fuerza: un kind mal escrito derivaría cero gates sin que nadie se entere.
_GATE_RULES: dict = {
    "column_nullable_tightened": "null_count",
    "pk_changed": "duplicate_key",
    "unique_added": "duplicate_key",
    "table_removed": "rowcount",
}


def _gates_dir() -> Path:
    return Path(data_dir()) / "db_compare" / "gates"


def _path_for(run_id: str) -> Path:
    if not run_id or not _RUN_ID_RE.match(str(run_id)):
        raise ValueError(f"run_id inválido: {run_id!r}")
    return _gates_dir() / f"{run_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Derivación (PURA)
# ---------------------------------------------------------------------------

def _cols_de_unique(detail: dict) -> list:
    destino = (detail or {}).get("target") or {}
    if isinstance(destino, dict):
        return list(destino.get("columns") or [])
    return []


def _sql_null_count(schema: str, tabla: str, columna: str, dialect: str) -> str:
    return (f"SELECT COUNT(*) FROM {sqlnames.qualified(schema, tabla, dialect)} "
            f"WHERE {sqlnames.quote_ident(columna, dialect)} IS NULL")


def _sql_duplicate_key(schema: str, tabla: str, columnas: list, dialect: str) -> str:
    cols = ", ".join(sqlnames.quote_ident(c, dialect) for c in columnas)
    base = (f"SELECT COUNT(*) FROM (SELECT {cols} "
            f"FROM {sqlnames.qualified(schema, tabla, dialect)} "
            f"GROUP BY {cols} HAVING COUNT(*) > 1)")
    # Oracle no admite el alias de subconsulta acá; el resto lo exige.
    return base if dialect == "oracle" else base + " t"


def _sql_rowcount(schema: str, tabla: str, dialect: str) -> str:
    return f"SELECT COUNT(*) FROM {sqlnames.qualified(schema, tabla, dialect)}"


def derive_gates(diff: dict, target_alias: str) -> list:
    """Deriva las precondiciones del diff. Determinista, sin I/O.

    El orden es el de `diff["items"]`, así los `gate_id` no bailan entre
    corridas del mismo par.
    """
    dialect = (diff or {}).get("engine") or "sqlserver"
    gates: list = []
    seq = 0

    def _agregar(kind_gate: str, schema: str, nombre: str, sql: str,
                 check: str, descripcion: str) -> None:
        nonlocal seq
        seq += 1
        gates.append({
            "gate_id": f"g{seq:03d}_{kind_gate}_{schema}.{nombre}",
            "item_key": f"table:{schema}.{nombre}",
            "kind": kind_gate,
            "description": descripcion,
            "sql": sql,
            "check": check,
            "target_alias": target_alias,
        })

    for item in (diff or {}).get("items") or []:
        schema = item.get("schema") or ""
        nombre = item.get("name") or ""

        if item.get("action") == "removed" and \
                _GATE_RULES.get("table_removed") and item.get("object_type") == "table":
            _agregar("rowcount", schema, nombre,
                     _sql_rowcount(schema, nombre, dialect), "info_rowcount",
                     f"Cuántas filas tiene {schema}.{nombre} antes de eliminarla")
            continue

        for cambio in item.get("changes") or []:
            kind = cambio.get("kind")
            regla = _GATE_RULES.get(kind)
            if not regla:
                continue
            detail = cambio.get("detail") or {}

            if regla == "null_count":
                columna = detail.get("column")
                if not columna:
                    continue
                _agregar("null_count", schema, nombre,
                         _sql_null_count(schema, nombre, columna, dialect),
                         "expect_zero",
                         f"Filas con {columna} en NULL (el destino la exige NOT NULL)")

            elif regla == "duplicate_key":
                columnas = (list(detail.get("target") or [])
                            if kind == "pk_changed" else _cols_de_unique(detail))
                if not columnas:
                    # Sin columnas no hay consulta posible: mejor ninguna gate
                    # que una gate rota que el operador cree que verificó algo.
                    continue
                etiqueta = "la PK" if kind == "pk_changed" else "el UNIQUE"
                _agregar("duplicate_key", schema, nombre,
                         _sql_duplicate_key(schema, nombre, columnas, dialect),
                         "expect_zero",
                         f"Valores duplicados en {', '.join(columnas)} "
                         f"({etiqueta} nueva los prohíbe)")

    return gates


def gates_export_sql(diff: dict, target_alias: str, engine: str) -> str:
    """Todas las gates como SQL comentado, para correrlas afuera de Stacky."""
    gates = derive_gates(diff, target_alias)

    lineas = [
        f"-- Precondiciones de migración — destino {target_alias} ({engine})",
        "-- Generado por Stacky. Solo SELECT: nada de esto modifica la base.",
        "",
    ]
    if not gates:
        lineas.append("-- Sin precondiciones: ningún cambio del diff requiere verificación previa.")
        return "\n".join(lineas) + "\n"

    for g in gates:
        lineas.append(f"-- GATE {g['gate_id']}: {g['description']}")
        if g["check"] == "expect_zero":
            lineas.append("-- esperado: 0")
        else:
            lineas.append("-- informativo: no hay valor correcto, es para que lo veas")
        lineas.append(g["sql"] + ";")
        lineas.append("")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Persistencia de resultados
# ---------------------------------------------------------------------------

def _vacio(run_id: str) -> dict:
    return {"version": GATES_VERSION, "run_id": run_id, "results": {}}


def load_results(run_id: str) -> dict:
    try:
        path = _path_for(run_id)
        if not path.is_file():
            return _vacio(run_id)
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("results"), dict):
            return _vacio(run_id)
        return doc
    except Exception:  # noqa: BLE001 — leer resultados nunca tumba el GET
        return _vacio(run_id)


def _persistir(run_id: str, doc: dict) -> None:
    path = _path_for(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Evaluación (SOLO a pedido explícito del operador)
# ---------------------------------------------------------------------------

def _scalar(engine, sql: str):
    from sqlalchemy import text

    with engine.connect() as conn:
        fila = conn.execute(text(sql)).fetchone()
    return int(fila[0]) if fila and fila[0] is not None else 0


def evaluate_gates(run_id: str, gate_ids: list | None = None) -> dict:
    """Ejecuta las precondiciones contra el destino y persiste pass/fail.

    Ningún código llama a esto solo: es siempre un click del operador.
    """
    from services import dbcompare_engine, dbcompare_runs
    from services.db_query import validate_select_only

    run = dbcompare_runs.get_run(run_id)
    if run is None:
        raise ValueError(f"run_not_found:{run_id}")
    if run.get("status") != "done":
        raise ValueError(f"run_not_done:{run.get('status')}")

    destino = run.get("target_alias") or ""
    gates = derive_gates(run.get("diff") or {}, destino)
    if gate_ids is not None:
        pedidas = set(gate_ids)
        gates = [g for g in gates if g["gate_id"] in pedidas]
    if len(gates) > _MAX_GATES_PER_EVAL:
        raise ValueError(f"too_many_gates:{len(gates)}>{_MAX_GATES_PER_EVAL}")

    doc = load_results(run_id)
    doc.setdefault("results", {})

    engine = None
    password = None
    for g in gates:
        # (i) El guard de solo-lectura, gate por gate. Es LA garantía: no se
        # delega en que el motor "no vaya a mutar nada".
        veredicto = validate_select_only(g["sql"])
        if not getattr(veredicto, "ok", False):
            doc["results"][g["gate_id"]] = {
                "status": "error", "value": None,
                "detail": "la consulta no pasó el guard de solo-lectura: "
                          + "; ".join(getattr(veredicto, "errors", None) or ["rechazada"]),
                "checked_at": _now_iso(),
            }
            continue

        try:
            if engine is None:
                engine = dbcompare_engine.open_engine(destino)
                cred = None
                try:
                    from services import dbcompare_registry

                    cred = dbcompare_registry.get_credential(destino)
                except Exception:  # noqa: BLE001
                    cred = None
                password = (cred or {}).get("password")
            valor = _scalar(engine, g["sql"])
        except Exception as exc:  # noqa: BLE001
            detalle = str(exc)
            try:
                detalle = dbcompare_engine._scrub(detalle, password)
            except Exception:  # noqa: BLE001
                detalle = "error de conexión"
            doc["results"][g["gate_id"]] = {
                "status": "error", "value": None, "detail": detalle,
                "checked_at": _now_iso(),
            }
            continue

        if g["check"] == "expect_zero":
            estado = "pass" if valor == 0 else "fail"
            detalle = ("sin filas que bloqueen el cambio" if valor == 0
                       else f"{valor} fila(s) impiden aplicar el cambio")
        else:
            estado = "info"
            detalle = f"{valor} fila(s)"

        doc["results"][g["gate_id"]] = {
            "status": estado, "value": valor, "detail": detalle,
            "checked_at": _now_iso(),
        }

    _persistir(run_id, doc)
    return doc
