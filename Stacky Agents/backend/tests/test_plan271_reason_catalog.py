# backend/tests/test_plan271_reason_catalog.py
"""Plan 271 F6 — puente entre el catálogo Python (ALL_FINAL_STATE_REASONS) y
el mapa TypeScript (finalStateOutcome.ts). Es lo que impide que vuelva a pasar
C8 (dos catálogos que divergen sin que nadie se entere)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_TS_PATH = ROOT.parent / "frontend" / "src" / "utils" / "finalStateOutcome.ts"


def test_toda_razon_del_backend_tiene_etiqueta_en_el_frontend():
    from services.final_state_resolver import ALL_FINAL_STATE_REASONS

    ts = _TS_PATH.read_text(encoding="utf-8")
    faltan = sorted(
        r for r in ALL_FINAL_STATE_REASONS
        if f"\n  {r}:" not in ts and f" {r}:" not in ts
    )
    assert faltan == [], f"razones sin etiqueta en la UI: {faltan}"


def test_el_ts_no_tiene_keys_huerfanas_fuera_del_catalogo():
    import re

    from services.final_state_resolver import ALL_FINAL_STATE_REASONS

    ts = _TS_PATH.read_text(encoding="utf-8")
    start = ts.index("FINAL_STATE_REASON_LABELS")
    body = ts[start:ts.index("\n};", start)]
    keys = set(re.findall(r"^\s*([a-z_][a-z0-9_]*):\s*\{", body, re.MULTILINE))
    huerfanas = sorted(keys - ALL_FINAL_STATE_REASONS)
    assert huerfanas == [], f"keys en el .ts que no están en ALL_FINAL_STATE_REASONS: {huerfanas}"
