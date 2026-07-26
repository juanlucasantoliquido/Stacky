"""golden_suite.py — Regresion E2E reproducible (Plan 241 F9).

POR QUE. Sin un ratchet, cualquier cambio futuro puede reintroducir un falso verde y
nadie se entera hasta que alguien mire una captura — que es EXACTAMENTE como se
descubrio el falso positivo del ADO-366.

golden/expected.json:
    {"<ado_id>": {"verdict": str, "verified": int, "scenarios": {"P01": "pass", ...}}}

REGLA DURA: `--record` NUNCA corre en automatico. Grabar un esperado es una decision
del operador; si no, se congelaria un falso verde como si fuera la verdad.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger("stacky.qa_uat.golden_suite")

_TOOL_ROOT = Path(__file__).resolve().parent
_GOLDEN_DIR = _TOOL_ROOT / "golden"
_EXPECTED_NAME = "expected.json"


def _expected_path(golden_dir=None) -> Path:
    return Path(golden_dir or _GOLDEN_DIR) / _EXPECTED_NAME


def load_expected(golden_dir=None) -> dict:
    """Lee golden/expected.json. {} si no existe o no parsea. NUNCA lanza."""
    try:
        p = _expected_path(golden_dir)
        if not p.is_file():
            return {}
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _snapshot_of(result: dict) -> dict:
    """Reduce un resultado del pipeline al subconjunto REPRODUCIBLE."""
    res = result if isinstance(result, dict) else {}
    stages = res.get("stages") if isinstance(res.get("stages"), dict) else {}
    fv = (stages.get("functional_verdict") or {}) if isinstance(stages, dict) else {}
    scenarios: dict = {}
    for c in (fv.get("criteria") or []):
        if isinstance(c, dict) and c.get("id"):
            scenarios[str(c["id"])] = str(c.get("status") or "")
    return {
        "verdict": str(res.get("verdict") or ""),
        "verified": int(fv.get("verified") or 0),
        "scenarios": scenarios,
    }


def _run_ticket(ado_id: int, runner=None) -> dict:
    """Corre el pipeline para un ticket y devuelve su snapshot. NUNCA lanza."""
    try:
        if runner is None:
            from qa_uat_pipeline import run as runner  # type: ignore[assignment]
        result = runner(ticket_id=int(ado_id), mode="dry-run", verbose=False)
        return _snapshot_of(result)
    except Exception as exc:  # noqa: BLE001
        return {"verdict": "BLOCKED", "verified": 0, "scenarios": {},
                "error": f"{type(exc).__name__}: {exc}"[:200]}


def record(ado_ids: list, *, golden_dir=None, runner=None) -> dict:
    """Corre y GRABA el esperado. OPT-IN EXPLICITO del operador. NUNCA lanza."""
    try:
        expected = load_expected(golden_dir)
        for ado_id in (ado_ids or []):
            expected[str(ado_id)] = _run_ticket(ado_id, runner=runner)
        base = Path(golden_dir or _GOLDEN_DIR)
        base.mkdir(parents=True, exist_ok=True)
        _expected_path(base).write_text(
            json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8")
        return {"ok": True, "recorded": [str(i) for i in (ado_ids or [])],
                "path": str(_expected_path(base)), "expected": expected}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "recorded": [], "path": None,
                "error": f"{type(exc).__name__}: {exc}"[:200]}


def verify(ado_ids=None, *, golden_dir=None, runner=None) -> dict:
    """Corre y COMPARA contra el esperado; diff por escenario. NUNCA lanza."""
    try:
        expected = load_expected(golden_dir)
        if not expected:
            return {"ok": False, "error": "no_golden_recorded", "checked": 0,
                    "diffs": [],
                    "detail": ("no hay golden grabado: corre `--record <ids>` una vez, "
                               "a conciencia, para congelar el esperado")}
        ids = [str(i) for i in (ado_ids or expected.keys())]
        diffs: list = []
        for ado_id in ids:
            want = expected.get(ado_id)
            if want is None:
                diffs.append({"ado_id": ado_id, "field": "__missing__",
                              "expected": None, "actual": "sin esperado grabado"})
                continue
            got = _run_ticket(int(ado_id), runner=runner)
            if got.get("verdict") != want.get("verdict"):
                diffs.append({"ado_id": ado_id, "field": "verdict",
                              "expected": want.get("verdict"), "actual": got.get("verdict")})
            if int(got.get("verified") or 0) != int(want.get("verified") or 0):
                diffs.append({"ado_id": ado_id, "field": "verified",
                              "expected": want.get("verified"), "actual": got.get("verified")})
            w_sc = want.get("scenarios") or {}
            g_sc = got.get("scenarios") or {}
            for sid in sorted(set(w_sc) | set(g_sc)):
                if w_sc.get(sid) != g_sc.get(sid):
                    diffs.append({"ado_id": ado_id, "field": f"scenario:{sid}",
                                  "expected": w_sc.get(sid), "actual": g_sc.get(sid)})
        return {"ok": not diffs, "checked": len(ids), "diffs": diffs}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "checked": 0, "diffs": [],
                "error": f"{type(exc).__name__}: {exc}"[:200]}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Suite golden reproducible del QA UAT (Plan 241 F9)")
    ap.add_argument("--record", nargs="+", type=int, default=None,
                    help="OPT-IN: corre esos tickets y CONGELA su veredicto esperado")
    ap.add_argument("--verify", nargs="*", type=int, default=None,
                    help="Corre y compara contra el golden (default: los ids grabados)")
    args = ap.parse_args()
    if args.record:
        out = record(args.record)
    else:
        out = verify(args.verify or None)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out.get("ok") else 1)


if __name__ == "__main__":
    main()
