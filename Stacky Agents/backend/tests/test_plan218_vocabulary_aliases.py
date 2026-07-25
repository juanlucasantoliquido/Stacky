"""tests/test_plan218_vocabulary_aliases.py -- Plan 218 F5.

Vocabulario canónico + alias de compatibilidad. ADITIVO: cero renombres (P6).
El riesgo que estos tests cubren es R5: renombrar campos `ado_*` rompería 495 usos
en 88 archivos del frontend.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import config as config_module  # noqa: E402

from services.tracker_vocabulary import (  # noqa: E402
    CANONICAL_FIELDS,
    LEGACY_ALIASES,
    to_canonical,
    with_legacy_aliases,
)

# Las 16 claves EXACTAS que Ticket.to_dict() emitía antes del Plan 218 (models.py:80-98).
_CLAVES_LEGACY_16 = [
    "id", "ado_id", "external_id", "project", "stacky_project_name", "tracker_type",
    "title", "description", "ado_state", "ado_url", "priority", "work_item_type",
    "parent_ado_id", "last_synced_at", "stacky_status", "assigned_to_ado",
]

# Las 5 canónicas que ESTA fase agrega (external_id y tracker_type ya se emitían).
_CANONICAS_NUEVAS = [
    "tracker_state", "item_url", "parent_external_id", "assignee", "item_type",
]


def _ticket():
    from models import Ticket

    return Ticket(
        id=1, ado_id=4242, external_id=4242, project="Strategist_Pacifico",
        stacky_project_name="RSPACIFICO", tracker_type="azure_devops",
        title="Título", description="<p>desc</p>", ado_state="Active",
        ado_url="https://dev.azure.com/o/p/_workitems/edit/4242", priority=2,
        work_item_type="Task", parent_ado_id=99,
        last_synced_at=datetime(2026, 7, 25, 10, 0, 0),
        stacky_status="idle", assigned_to_ado="alguien@ejemplo.test",
    )


def test_with_legacy_aliases_es_superconjunto():
    original = {"external_id": 5, "tracker_state": "Active", "title": "T"}
    resultado = with_legacy_aliases(original)

    for clave, valor in original.items():
        assert resultado[clave] == valor
    assert resultado["ado_id"] == 5
    assert resultado["ado_state"] == "Active"


def test_with_legacy_aliases_es_idempotente():
    payload = {"external_id": 5, "item_url": "http://x", "assignee": "a"}
    una = with_legacy_aliases(payload)
    dos = with_legacy_aliases(una)
    assert una == dos


def test_to_canonical_acepta_legacy():
    assert to_canonical({"ado_id": 5})["external_id"] == 5
    assert to_canonical({"ado_state": "Active"})["tracker_state"] == "Active"
    assert to_canonical({"work_item_type": "Bug"})["item_type"] == "Bug"


def test_to_canonical_prefiere_canonico():
    payload = {"ado_id": 5, "external_id": 9, "ado_state": "Old", "tracker_state": "New"}
    canonico = to_canonical(payload)
    assert canonico["external_id"] == 9
    assert canonico["tracker_state"] == "New"


def test_ticket_to_dict_mantiene_las_16_claves_legacy(monkeypatch):
    monkeypatch.setattr(config_module.config, "STACKY_CANONICAL_VOCABULARY_ENABLED", True)
    payload = _ticket().to_dict()

    faltantes = [k for k in _CLAVES_LEGACY_16 if k not in payload]
    assert faltantes == [], f"el payload perdió claves legacy: {faltantes}"
    assert payload["ado_id"] == 4242
    assert payload["ado_state"] == "Active"
    assert payload["parent_ado_id"] == 99
    assert payload["assigned_to_ado"] == "alguien@ejemplo.test"
    assert payload["project"] == "Strategist_Pacifico"


def test_ticket_to_dict_agrega_las_5_canonicas_nuevas(monkeypatch):
    monkeypatch.setattr(config_module.config, "STACKY_CANONICAL_VOCABULARY_ENABLED", True)
    payload = _ticket().to_dict()

    faltantes = [k for k in _CANONICAS_NUEVAS if k not in payload]
    assert faltantes == [], f"faltan canónicas nuevas: {faltantes}"
    assert payload["tracker_state"] == payload["ado_state"]
    assert payload["item_url"] == payload["ado_url"]
    assert payload["parent_external_id"] == payload["parent_ado_id"]
    assert payload["assignee"] == payload["assigned_to_ado"]
    assert payload["item_type"] == payload["work_item_type"]


def test_tracker_project_mapea_a_project():
    assert to_canonical({"project": "X"})["tracker_project"] == "X"
    assert LEGACY_ALIASES["tracker_project"] == "project"
    assert "stacky_project_name" not in CANONICAL_FIELDS


def test_flag_off_devuelve_payload_original(monkeypatch):
    """Con la flag apagada, el payload es EXACTAMENTE el de antes del plan."""
    ticket = _ticket()

    monkeypatch.setattr(config_module.config, "STACKY_CANONICAL_VOCABULARY_ENABLED", False)
    apagado = ticket.to_dict()
    assert sorted(apagado) == sorted(_CLAVES_LEGACY_16)

    monkeypatch.setattr(config_module.config, "STACKY_CANONICAL_VOCABULARY_ENABLED", True)
    encendido = ticket.to_dict()

    # Superconjunto ESTRICTO: cada clave legacy conserva su valor exacto.
    for clave, valor in apagado.items():
        assert encendido[clave] == valor, f"la clave legacy {clave} cambió de valor"
    assert set(apagado) < set(encendido)
