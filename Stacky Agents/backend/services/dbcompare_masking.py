"""Plan 181 — Masking determinista de secretos/PII en el data-diff (presentación).

DOCTRINA (doc 181 §3.1): protege la PRESENTACIÓN, nunca el motor. El diff compara
valores reales; el run persiste crudo; los scripts DML del bundle llevan valores
reales (generate_parity_bundle re-lee el run de disco: api/db_compare.py:274 ->
emit_data_scripts, dbcompare_scripts.py). Este módulo transforma COPIAS de la
respuesta HTTP y nada más. Revelar = override HITL persistido (MaskingPrefs v1).
Tabla de superficies cubiertas/no-cubiertas: doc 181 §3.1."""
from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from runtime_paths import data_dir

PREFS_VERSION = 1
MASKED_PLACEHOLDER = "••••"
_SUFFIX_MIN_LEN = 8  # fix C4: el sufijo de 2 chars SOLO si len>=8 (un secreto de
                     # 5-7 chars con sufijo revelaría hasta ~1/3 de su contenido)
_PREFS_LOCK = threading.Lock()

_NAME_PATTERNS = tuple(re.compile(p, re.IGNORECASE) for p in (
    r"password|passwd|pwd",
    r"secret",
    r"token",
    r"api[_-]?key",
    r"contrase",
    r"credencial",
    r"conn(ection)?[_-]?str(ing)?",
    r"cadena[_-]?conexion",
    r"clave[_-]?(secreta|privada|api|acceso)",  # 'clave' a secas EXCLUIDA (glossary.py:33: clave = key de parámetro RS)
))

_VALUE_PATTERNS = (
    re.compile(r"^eyJ[A-Za-z0-9_-]{10,}\."),          # JWT
    re.compile(r"(password|pwd)\s*=", re.IGNORECASE),  # connection string embebida
)

_VALUE_SAMPLE_ROWS = 50  # muestreo determinista: las listas vienen ordenadas por PK
                         # (dbcompare_data.py:168-170) => mismo plan en cada GET


def column_name_is_sensitive(name: str) -> bool:
    return any(p.search(name or "") for p in _NAME_PATTERNS)


def value_is_sensitive(value) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(p.search(text) for p in _VALUE_PATTERNS)


def mask_value(value):
    """Regla EXACTA (golden, fix C4): None -> None (la nulidad no es secreto y el
    grid distingue NULL); len(str) < 8 -> '••••' pelado; si no -> '••••' + últimos
    2 chars (distinguibilidad sin revelar una fracción significativa)."""
    if value is None:
        return None
    text = str(value)
    if len(text) < _SUFFIX_MIN_LEN:
        return MASKED_PLACEHOLDER
    return MASKED_PLACEHOLDER + text[-2:]


def _override_key(schema: str, table: str, column: str) -> str:
    # Clave CANÓNICA UPPERCASE (fix C3): única forma guardada y única buscada.
    return f"{schema}.{table}.{column}".upper()


def masking_plan(table_diff: dict, prefs: dict) -> dict[str, str]:
    """dict columna -> 'masked'|'visible' para UN DataDiff v1 de tabla
    (shape dbcompare_data.py:197-211). Precedencia: override prefs > nombre >
    valor > visible. PURA: no lee disco."""
    schema = table_diff.get("schema") or ""
    table = table_diff.get("table") or ""
    overrides = prefs.get("overrides") or {}
    plan: dict[str, str] = {}
    for col in table_diff.get("columns") or []:
        override = overrides.get(_override_key(schema, table, col))
        if override and override.get("state") in ("visible", "masked"):
            plan[col] = override["state"]
            continue
        if column_name_is_sensitive(col):
            plan[col] = "masked"
            continue
        plan[col] = "visible"
    # Segunda línea por VALOR: solo columnas aún visibles sin override explícito.
    for col, state in plan.items():
        if state != "visible":
            continue
        if _override_key(schema, table, col) in overrides:
            continue  # el humano ya decidió: no re-enmascarar por valor
        if _any_sampled_value_sensitive(table_diff, col):
            plan[col] = "masked"
    return plan


def _any_sampled_value_sensitive(table_diff: dict, col: str) -> bool:
    for row in (table_diff.get("only_source") or [])[:_VALUE_SAMPLE_ROWS]:
        if value_is_sensitive(row.get(col)):
            return True
    for row in (table_diff.get("only_target") or [])[:_VALUE_SAMPLE_ROWS]:
        if value_is_sensitive(row.get(col)):
            return True
    for ch in (table_diff.get("changed") or [])[:_VALUE_SAMPLE_ROWS]:
        cell = (ch.get("cells") or {}).get(col)
        if cell and (value_is_sensitive(cell.get("source")) or value_is_sensitive(cell.get("target"))):
            return True
        if value_is_sensitive((ch.get("pk") or {}).get(col)):
            return True
    return False


def apply_masking(table_diff: dict, plan: dict[str, str]) -> dict:
    """Devuelve una COPIA del DataDiff de tabla con las columnas 'masked'
    enmascaradas en LAS CUATRO apariciones (KPI-1): filas planas de only_source
    y only_target (que mezclan pk+data cols, dbcompare_data.py:177-178),
    changed[].cells[col].source/target (:182-186) y changed[].pk[col] (:188).
    NO muta el original (KPI-6). Agrega masked_columns (aditivo, SOLO respuesta;
    con flag ON el campo está SIEMPRE — [] si nada se enmascaró, C9)."""
    masked_cols = sorted(c for c, s in plan.items() if s == "masked")
    if not masked_cols:
        out = dict(table_diff)
        out["masked_columns"] = []
        return out
    out = copy.deepcopy(table_diff)
    masked = set(masked_cols)
    for key in ("only_source", "only_target"):
        for row in out.get(key) or []:
            for col in list(row):
                if col in masked:
                    row[col] = mask_value(row[col])
    for ch in out.get("changed") or []:
        for col, cell in (ch.get("cells") or {}).items():
            if col in masked:
                cell["source"] = mask_value(cell.get("source"))
                cell["target"] = mask_value(cell.get("target"))
        pk = ch.get("pk") or {}
        for col in list(pk):
            if col in masked:
                pk[col] = mask_value(pk[col])
    out["masked_columns"] = masked_cols
    return out


# ---------------------------------------------------------------------------
# F2 — MaskingPrefs v1: store en disco (atómico, sin cache, clave canónica)
# ---------------------------------------------------------------------------


def _prefs_path() -> Path:
    d = data_dir() / "db_compare"
    d.mkdir(parents=True, exist_ok=True)
    return d / "masking_prefs.json"


def load_prefs() -> dict:
    """SIEMPRE relee de disco (cero estado en memoria — KPI-3): el archivo es
    chico y esto garantiza que un override sobreviva reinicios sin caches."""
    path = _prefs_path()
    if not path.exists():
        return {"version": PREFS_VERSION, "overrides": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": PREFS_VERSION, "overrides": {}}
    if doc.get("version") != PREFS_VERSION or not isinstance(doc.get("overrides"), dict):
        return {"version": PREFS_VERSION, "overrides": {}}
    return doc


def set_override(schema: str, table: str, column: str, state: str) -> dict:
    """state: 'visible'|'masked' setea; 'auto' elimina el override. Retorna prefs.
    La clave se guarda SIEMPRE en su forma canónica UPPERCASE (fix C3)."""
    if state not in ("visible", "masked", "auto"):
        raise ValueError(f"state inválido: {state!r} (visible|masked|auto)")
    key = _override_key(schema, table, column)
    with _PREFS_LOCK:
        prefs = load_prefs()
        if state == "auto":
            prefs["overrides"].pop(key, None)
        else:
            prefs["overrides"][key] = {
                "state": state,
                "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        path = _prefs_path()
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
    return prefs


# ---------------------------------------------------------------------------
# F3 — Transformación de salida: gate + apply_to_run_response
# ---------------------------------------------------------------------------


def masking_enabled() -> bool:
    import config as _config
    return bool(getattr(_config.config, "STACKY_DB_COMPARE_ENABLED", False)) and bool(
        getattr(_config.config, "STACKY_DB_COMPARE_MASKING_ENABLED", False)
    )


def apply_to_run_response(run: dict) -> dict:
    """Punto de aplicación para el RUN COMPLETO (doc 181 §3.1, tabla de
    superficies). Con flag OFF o sin data_diff: retorna EL MISMO objeto sin copia
    ni campo aditivo => jsonify byte-idéntico a main (KPI-2). Con ON: copia
    superficial del run + data_diff transformado."""
    if not masking_enabled():
        return run
    data_diff = run.get("data_diff")
    if not data_diff or not isinstance(data_diff.get("tables"), dict):
        return run
    prefs = load_prefs()
    out_tables = {}
    for key, result in data_diff["tables"].items():
        if not isinstance(result, dict) or "error" in result or "columns" not in result:
            out_tables[key] = result  # errores y shapes no-diff pasan tal cual
            continue
        plan = masking_plan(result, prefs)
        out_tables[key] = apply_masking(result, plan)
    out_run = dict(run)
    out_data_diff = dict(data_diff)
    out_data_diff["tables"] = out_tables
    out_run["data_diff"] = out_data_diff
    return out_run
