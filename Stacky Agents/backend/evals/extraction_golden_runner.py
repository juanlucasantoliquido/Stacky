"""Plan 49 — Golden-set determinista de EXTRACTORES PUROS del arnés.

Hermano de evals/golden_runner.py, pero en vez de juzgar el CONTRATO juzga la
EXTRACCIÓN cruda: funciones puras sobre string (_extract_epic_html /
_looks_like_epic) y la validación pura de campos del pending-task.json.

Sin LLM, sin red, sin reloj, sin datos personales. Determinismo total.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from api.tickets import (
    _PENDING_TASK_REQUIRED_FIELDS,
    PENDING_TASK_STATUS_CANONICAL,
    _extract_epic_html,
    _looks_like_epic,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "extraction_fixtures"

# canónico + alias legacy (tickets.py:53 _PENDING_TASK_STATUS_PENDING_ALIASES).
_STATUS_OK = {PENDING_TASK_STATUS_CANONICAL, "pending"}


@dataclass
class ExtractionCase:
    name: str
    kind: str
    raw: str
    expect: dict
    source: Path


def load_cases() -> list[ExtractionCase]:
    if not _FIXTURES_DIR.exists():
        return []
    cases = []
    for fx in sorted(_FIXTURES_DIR.glob("*.json")):
        d = json.loads(fx.read_text(encoding="utf-8"))
        cases.append(
            ExtractionCase(
                name=d["name"],
                kind=d.get("kind", "epic"),
                raw=d.get("raw", ""),
                expect=d.get("expect", {}),
                source=fx,
            )
        )
    return cases


def _validate_pending_task_payload(raw: str | None) -> dict:
    """Pura: parsea el raw y reporta patologías. Nunca lanza."""
    out = {
        "json_ok": False,
        "missing_fields": sorted(_PENDING_TASK_REQUIRED_FIELDS),
        "status_canonical": False,
    }
    if not raw:
        return out
    try:
        payload = json.loads(raw)
    except (ValueError, TypeError):
        return out  # json_ok=False, missing_fields=todos
    out["json_ok"] = True
    if not isinstance(payload, dict):
        return out
    out["missing_fields"] = sorted(_PENDING_TASK_REQUIRED_FIELDS - set(payload.keys()))
    out["status_canonical"] = payload.get("status") in _STATUS_OK
    return out


def _evaluate_pending_task(case: ExtractionCase) -> list[str]:
    res = _validate_pending_task_payload(case.raw)
    reasons: list[str] = []
    exp = case.expect
    if "json_ok" in exp and res["json_ok"] != exp["json_ok"]:
        reasons.append(f"json_ok={res['json_ok']}, esperado {exp['json_ok']}")
    if "missing_fields" in exp and sorted(res["missing_fields"]) != sorted(exp["missing_fields"]):
        reasons.append(f"missing_fields={res['missing_fields']}, esperado {exp['missing_fields']}")
    if "status_canonical" in exp and res["status_canonical"] != exp["status_canonical"]:
        reasons.append(f"status_canonical={res['status_canonical']}, esperado {exp['status_canonical']}")
    return reasons


def evaluate(case: ExtractionCase) -> list[str]:
    """Devuelve lista de razones de fallo; vacía == OK."""
    reasons: list[str] = []
    if case.kind == "epic":
        html = _extract_epic_html(case.raw)
        for sub in case.expect.get("extracted_html_contains", []):
            if sub not in html:
                reasons.append(f"falta substring {sub!r} en HTML extraido")
        for sub in case.expect.get("extracted_html_excludes", []):
            if sub in html:
                reasons.append(f"substring prohibido {sub!r} presente")
        exp = case.expect.get("looks_like_epic")
        if exp is not None and _looks_like_epic(html) != exp:
            reasons.append(f"looks_like_epic={_looks_like_epic(html)}, esperado {exp}")
    elif case.kind == "pending_task":
        reasons.extend(_evaluate_pending_task(case))
    else:
        reasons.append(f"kind desconocido: {case.kind}")
    return reasons
