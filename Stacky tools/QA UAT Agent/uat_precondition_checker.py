"""
uat_precondition_checker.py — Verify QA environment preconditions before running UAT tests.

SPEC: PHASE3_QA_UAT_ROADMAP.md §3.3
CLI:
    python uat_precondition_checker.py --scenarios evidence/70/scenarios.json [--verbose]

Checks (all read-only, SELECT only):
  1. RIDIOMA scripts applied (IDs extracted from ticket preconditions)
  2. Required test data exists in BD QA (from ScenarioSpec.datos_requeridos)
  3. Environment vars for BD are set

DB credentials (NEVER via CLI — evitar logs):
  RS_QA_DB_USER — read-only user (e.g. RSPACIFICOREAD)
  RS_QA_DB_PASS — password
  RS_QA_DB_DSN  — Data Source=aisbddev02...;Pooling=True

Output JSON to stdout:
{
  "ok": true,
  "ticket_id": 70,
  "summary": {"total": 6, "ok": 5, "blocked": 1},
  "results": {
    "P01": {"ok": true, "missing": []},
    "P04": {"ok": false, "missing": [{"tipo": "ridioma", "recurso": "IDTEXTO=9296", "hint": "..."}]}
  }
}

Error codes: db_credentials_missing, db_unreachable, invalid_scenarios_json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.precondition_checker")

_TOOL_VERSION = "1.0.0"

# Required env vars for DB connection
_DB_ENV_VARS = ("RS_QA_DB_USER", "RS_QA_DB_PASS", "RS_QA_DB_DSN")

# Regex to extract RIDIOMA IDTEXTO from precondition strings
# Matches: "RIDIOMA 9296", "INSERTs RIDIOMA 9296-9298", "RIDIOMA 9296,9297,9298"
_RIDIOMA_RE = re.compile(r'(?:RIDIOMA|IDTEXTO)[=\s]+(\d+(?:[-,]\d+)*)', re.IGNORECASE)

# Supported tabla checks (safe-listed for SELECT queries)
_SAFE_TABLES = frozenset({
    "RAGEN", "RIDIOMA", "RAGTIP", "RAGMOT", "RAGCAL",
    "RACOMI", "RACON", "RAGPAR", "RASIST", "RAGTIP",
})


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        scenarios_path=Path(args.scenarios),
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


# ── Core logic ────────────────────────────────────────────────────────────────

def run(
    scenarios_path: Path,
    verbose: bool = False,
    _db_connector=None,  # injectable for testing — callable() -> connection
) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()

    # Load scenarios JSON
    try:
        scenarios_data = json.loads(scenarios_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_scenarios_json", f"Cannot read scenarios: {exc}")

    if not scenarios_data.get("ok") or not isinstance(scenarios_data.get("scenarios"), list):
        return _err("invalid_scenarios_json", "scenarios.json missing 'ok' or 'scenarios'")

    scenarios = scenarios_data["scenarios"]
    ticket_id = scenarios_data.get("ticket_id", 0)

    # Check DB credentials
    missing_env = [v for v in _DB_ENV_VARS if not os.getenv(v)]
    if missing_env:
        return _err(
            "db_credentials_missing",
            f"Missing env vars: {', '.join(missing_env)}. "
            f"Load from Tools/Stacky/.secrets/qa_db.env before running.",
        )

    # Try connecting to DB (or use injectable connector)
    try:
        connector = _db_connector or _get_db_connector()
        connection = connector()
    except Exception as exc:
        return _err("db_unreachable", f"Cannot connect to BD QA: {exc}")

    results = {}
    blocked_count = 0

    try:
        for scenario in scenarios:
            scenario_id = scenario.get("scenario_id", "?")
            missing = []

            # Check 1: RIDIOMA scripts from preconditions
            ridioma_ids = _extract_ridioma_ids(scenario.get("precondiciones") or [])
            for idtexto in ridioma_ids:
                ok = _check_ridioma(connection, idtexto, verbose=verbose)
                if not ok:
                    missing.append({
                        "tipo": "ridioma",
                        "recurso": f"RIDIOMA.IDTEXTO={idtexto}",
                        "hint": (
                            f"Ejecutar INSERTs RIDIOMA para IDTEXTO={idtexto}. "
                            "Ver análisis técnico del ticket."
                        ),
                    })

            # Check 2: Required test data from datos_requeridos
            for data_req in (scenario.get("datos_requeridos") or []):
                tabla = data_req.get("tabla", "")
                filtro = data_req.get("filtro", "")
                if not tabla or not filtro:
                    continue
                if tabla not in _SAFE_TABLES:
                    logger.warning("Tabla '%s' not in safe-list, skipping data check", tabla)
                    continue
                ok = _check_test_data(connection, tabla, filtro, verbose=verbose)
                if not ok:
                    missing.append({
                        "tipo": "test_data",
                        "recurso": f"{tabla} WHERE {filtro}",
                        "hint": (
                            f"No se encontraron registros en {tabla} con condición: {filtro}. "
                            "Verificar que los datos de prueba estén disponibles en BD QA."
                        ),
                    })

            result_ok = len(missing) == 0
            if not result_ok:
                blocked_count += 1

            results[scenario_id] = {
                "ok": result_ok,
                "missing": missing,
            }

    finally:
        try:
            connection.close()
        except Exception:
            pass

    total = len(scenarios)
    ok_count = total - blocked_count

    return {
        "ok": True,
        "ticket_id": ticket_id,
        "summary": {
            "total": total,
            "ok": ok_count,
            "blocked": blocked_count,
        },
        "results": results,
        "elapsed_s": round(time.time() - started, 2),
    }


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_db_connector():
    """
    Returns a factory function that creates a pyodbc connection using env vars.
    The connection uses account RSPACIFICOREAD (SELECT only — account policy enforced by DB).
    """
    import importlib
    try:
        pyodbc = importlib.import_module("pyodbc")
    except ImportError:
        raise ImportError(
            "pyodbc not installed. Run: pip install pyodbc. "
            "Also requires ODBC driver for SQL Server."
        )

    dsn = os.environ["RS_QA_DB_DSN"]
    user = os.environ["RS_QA_DB_USER"]
    password = os.environ["RS_QA_DB_PASS"]

    def connect():
        conn_str = f"{dsn};UID={user};PWD={password};ApplicationIntent=ReadOnly"
        conn = pyodbc.connect(conn_str, timeout=10)
        conn.autocommit = True  # SELECT only — no transactions needed
        return conn

    return connect


def _check_ridioma(connection, idtexto: int, verbose: bool = False) -> bool:
    """Check that RIDIOMA has at least one row with IDTEXTO=idtexto."""
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM RIDIOMA WHERE IDTEXTO = ?",
            (idtexto,),
        )
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        logger.debug("RIDIOMA IDTEXTO=%d → count=%d", idtexto, count)
        return count > 0
    except Exception as exc:
        logger.warning("RIDIOMA check failed for IDTEXTO=%d: %s", idtexto, exc)
        return False


def _check_test_data(connection, tabla: str, filtro: str, verbose: bool = False) -> bool:
    """
    Check that tabla WHERE filtro returns at least 1 row.
    SECURITY: tabla is validated against _SAFE_TABLES before this call.
    filtro is appended to the query but never executed as raw DDL/DML.
    """
    try:
        # NOTE: tabla is from _SAFE_TABLES (safe-listed). filtro comes from scenarios.json
        # which is generated by the pipeline, not from external user input.
        query = f"SELECT COUNT(*) FROM {tabla} WHERE {filtro}"  # nosec
        cursor = connection.cursor()
        cursor.execute(query)
        row = cursor.fetchone()
        count = row[0] if row else 0
        cursor.close()
        logger.debug("%s WHERE %s → count=%d", tabla, filtro, count)
        return count > 0
    except Exception as exc:
        logger.warning("Data check failed for %s WHERE %s: %s", tabla, filtro, exc)
        return False


# ── RIDIOMA ID extraction ─────────────────────────────────────────────────────

def _extract_ridioma_ids(precondiciones: list) -> list:
    """
    Extract RIDIOMA IDTEXTO values from precondition strings.

    Examples:
      "INSERTs RIDIOMA 9296-9298 aplicados" → [9296, 9297, 9298]
      "RIDIOMA 9296,9297" → [9296, 9297]
      "RIDIOMA 9296" → [9296]
    """
    ids = []
    for prec in precondiciones:
        for match in _RIDIOMA_RE.finditer(str(prec)):
            raw = match.group(1)
            if "-" in raw:
                parts = raw.split("-")
                try:
                    start, end = int(parts[0]), int(parts[-1])
                    ids.extend(range(start, end + 1))
                except ValueError:
                    pass
            elif "," in raw:
                for part in raw.split(","):
                    try:
                        ids.append(int(part.strip()))
                    except ValueError:
                        pass
            else:
                try:
                    ids.append(int(raw))
                except ValueError:
                    pass
    return list(dict.fromkeys(ids))  # deduplicate, preserve order


# ── Error helper ──────────────────────────────────────────────────────────────

def _err(error: str, message: str) -> dict:
    return {"ok": False, "error": error, "message": message}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="UAT Precondition Checker — verifies BD and environment before running tests."
    )
    p.add_argument(
        "--scenarios",
        required=True,
        help="Path to scenarios.json (output of uat_scenario_compiler.py).",
    )
    p.add_argument("--verbose", action="store_true", help="Debug logging to stderr.")
    return p.parse_args()


if __name__ == "__main__":
    main()
