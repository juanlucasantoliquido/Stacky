"""Plan 51 F2 — Golden-set determinista del linter de catálogo (procesos
inventados). Hermano de evals/extraction_golden_runner.py.

Cada fixture: {name, html, catalog, expect_unknown}. Compara
golden_catalog_diff(html, catalog) contra expect_unknown.

Sin LLM, sin red, sin reloj, sin datos personales. Determinismo total.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from harness.epic_gate import golden_catalog_diff

_FIXTURES_DIR = Path(__file__).resolve().parent / "catalog_diff_fixtures"


@dataclass
class CatalogCase:
    name: str
    html: str
    catalog: list
    expect_unknown: list
    source: Path


def load_cases() -> list[CatalogCase]:
    if not _FIXTURES_DIR.exists():
        return []
    cases = []
    for fx in sorted(_FIXTURES_DIR.glob("*.json")):
        d = json.loads(fx.read_text(encoding="utf-8"))
        cases.append(
            CatalogCase(
                name=d["name"],
                html=d.get("html", ""),
                catalog=d.get("catalog", []),
                expect_unknown=d.get("expect_unknown", []),
                source=fx,
            )
        )
    return cases


def evaluate(case: CatalogCase) -> list[str]:
    """Devuelve lista de razones de fallo; vacía == OK."""
    got = golden_catalog_diff(case.html, case.catalog)
    if sorted(got) != sorted(case.expect_unknown):
        return [f"unknown={got}, esperado {case.expect_unknown}"]
    return []
