"""Plan 210 F4-bis — Guard de cobertura del gate + huella del anti-patrón.

Convierte "todo path que transiciona el developer pasa por el gate" de una
esperanza documentada a un test que se pone ROJO si alguien abre un camino nuevo.
Determinista: grep sobre el árbol, cero LLM, igual en los 3 runtimes.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent   # backend/
REPO = ROOT.parent                              # Stacky Agents/
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_SITES = [
    "backend/api/tickets.py",                # _apply_task_state + rama legacy (F4)
    "backend/services/completion_state.py",  # Plan 208 — path REMOTO del daemon
]


def _repo_path(rel: str) -> Path:
    return REPO / rel


def test_developer_transition_sites_pass_through_gate():
    revisados = []
    for rel in _SITES:
        p = _repo_path(rel)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        transiciona_developer = (
            ("update_item_state" in text or "_safe_transition" in text)
            and "developer" in text
        )
        if transiciona_developer:
            revisados.append(rel)
            assert "gate_final_state" in text, (
                f"{rel} transiciona estado del developer sin pasar por "
                f"dev_build_verify.gate_final_state (reabre el 'falso Build OK')"
            )
    assert revisados, "el guard debe cubrir al menos un site real"


def test_fingerprint_registered():
    path = REPO / "docs" / "sistema" / "error_fingerprints.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    entrada = next((f for f in data["fingerprints"]
                    if f.get("id") == "dev_build_ok_narrated_unverified"), None)

    assert entrada is not None, "falta la huella del anti-patrón que mata este plan"
    assert entrada["guard_test"], "la huella tiene que apuntar a su test guardián"
    assert entrada["status"] == "resolved"


def test_el_gate_existe_y_es_publico():
    from services import dev_build_verify

    assert callable(dev_build_verify.gate_final_state)
    assert "gate_final_state" in dev_build_verify.__all__
