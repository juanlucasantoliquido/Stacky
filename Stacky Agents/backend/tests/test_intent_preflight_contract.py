"""Plan 41 F0 — Contrato del Brief de Intención (módulo puro)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.intent_preflight import from_model_json, to_payload  # noqa: E402

_FULL = json.dumps({
    "objective": "Generar la épica de facturación",
    "deliverables": ["Épica con RFs"],
    "assumptions": [{"text": "el batch es FacturacionNocturna", "impact": "high",
                     "needs_confirmation": True}],
    "open_questions": ["¿Qué tracker?"],
    "areas": ["proceso FacturacionNocturna"],
    "confidence": 0.7,
})


def test_from_model_json_parses_full_payload():
    b = from_model_json(_FULL)
    assert b.objective == "Generar la épica de facturación"
    assert b.deliverables == ["Épica con RFs"]
    assert b.assumptions[0].impact == "high"
    assert b.assumptions[0].needs_confirmation is True
    assert b.confidence == 0.7


def test_from_model_json_tolerates_fences():
    raw = "Acá va:\n```json\n" + _FULL + "\n```\nlisto"
    b = from_model_json(raw)
    assert b.objective == "Generar la épica de facturación"


def test_from_model_json_empty_is_confidence_zero():
    assert from_model_json("").confidence == 0.0
    assert from_model_json("no soy json").confidence == 0.0
    assert from_model_json(None).confidence == 0.0


def test_invalid_impact_defaults_to_medium():
    raw = json.dumps({"assumptions": [{"text": "x", "impact": "urgent"}]})
    b = from_model_json(raw)
    assert b.assumptions[0].impact == "medium"


def test_to_payload_is_json_serializable():
    b = from_model_json(_FULL)
    json.dumps(to_payload(b))  # no debe lanzar


def test_to_payload_redacts_secrets():
    raw = json.dumps({
        "objective": "usar el PAT ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
        "areas": ["contactar admin@empresa.com"],
        "confidence": 0.6,
    })
    payload = to_payload(from_model_json(raw))
    blob = json.dumps(payload)
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in blob
    assert "admin@empresa.com" not in blob
