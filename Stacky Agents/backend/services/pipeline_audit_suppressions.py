"""services/pipeline_audit_suppressions.py — Plan 248 F4.

Supresiones que PERSISTEN pero no CIEGAN: el `evidence_fingerprint` es parte de la clave,
así que la decisión vale para el hecho que el operador evaluó, no para el lugar donde
estaba. Si la evidencia cambia, la supresión deja de matchear y el hallazgo REAPARECE.

Patrón copiado de `services/ci_run_ledger.py` (ledger JSONL con allowlist + retención).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import runtime_paths

from services.cicd_audit_core import evidence_fingerprint

ENTRY_FIELDS: tuple = ("pipeline_key", "code", "location", "evidence_fingerprint",
                       "reason", "created_at", "created_by")
MAX_ROWS = 500
_LOCK = threading.Lock()


def _ledger_path() -> Path:
    return Path(runtime_paths.data_dir()) / "pipeline_audit_suppressions.jsonl"


def _read_rows() -> list:
    """Lee todas las líneas válidas; tolera (saltea) líneas corruptas."""
    path = _ledger_path()
    if not path.exists():
        return []
    out = []
    try:
        for linea in path.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea:
                continue
            try:
                fila = json.loads(linea)
            except Exception:
                continue
            if isinstance(fila, dict):
                out.append(fila)
    except OSError:
        return []
    return out


def _write_rows(rows: list) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    texto = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    tmp.write_text(texto + ("\n" if rows else ""), encoding="utf-8")
    tmp.replace(path)


def _clean_entry(entry: dict) -> dict:
    out = {k: entry.get(k) for k in ENTRY_FIELDS}
    if not out.get("created_at"):
        out["created_at"] = datetime.now(timezone.utc).isoformat()
    if not out.get("created_by"):
        out["created_by"] = "operador"
    return out


def add_suppression(entry: dict) -> None:
    """`reason` vacío -> ValueError. HITL sin excepción: nadie suprime sin escribir por qué."""
    reason = str((entry or {}).get("reason") or "").strip()
    if not reason:
        raise ValueError("suprimir un hallazgo exige un motivo escrito (reason no vacio)")
    for campo in ("pipeline_key", "code", "location"):
        if not str((entry or {}).get(campo) or "").strip():
            raise ValueError("falta %s" % campo)
    clean = _clean_entry(dict(entry))
    clean["reason"] = reason
    with _LOCK:
        rows = _read_rows()
        rows.append(clean)
        if len(rows) > MAX_ROWS:
            rows = rows[-MAX_ROWS:]
        _write_rows(rows)


def list_suppressions(pipeline_key: object = None) -> list:
    with _LOCK:
        rows = _read_rows()
    if pipeline_key is None:
        return rows
    return [r for r in rows if r.get("pipeline_key") == pipeline_key]


def remove_suppression(pipeline_key: str, code: str, location: str) -> bool:
    with _LOCK:
        rows = _read_rows()
        quedan = [r for r in rows
                  if not (r.get("pipeline_key") == pipeline_key
                          and r.get("code") == code
                          and r.get("location") == location)]
        if len(quedan) == len(rows):
            return False
        _write_rows(quedan)
        return True


def apply_suppressions(findings: tuple, suppressions: list, *, pipeline_key: object = None) -> tuple:
    """→ (visibles, suprimidos).

    Una supresión matchea SOLO si coinciden los CUATRO: pipeline_key, code, location y
    evidence_fingerprint. Sin el fingerprint sería una venda permanente.
    """
    if not suppressions:
        return tuple(findings), ()
    claves = set()
    for s in suppressions:
        if not isinstance(s, dict):
            continue
        claves.add((
            s.get("pipeline_key"),
            s.get("code"),
            s.get("location"),
            s.get("evidence_fingerprint"),
        ))
    visibles, suprimidos = [], []
    for f in findings:
        clave = (pipeline_key, f.code, f.location,
                 evidence_fingerprint(f.code, f.location, f.evidence))
        if clave in claves:
            suprimidos.append(f)
        else:
            visibles.append(f)
    return tuple(visibles), tuple(suprimidos)
