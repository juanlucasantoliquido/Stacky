"""Plan 208 F4 — Esquema `by_work_item_type` + fuentes de los selectores.

Valida el schema nuevo (retrocompatible), el warning no bloqueante contra los
estados reales del tracker, y que el GET del perfil exponga `work_item_types` y
`valid_states` para poblar los dropdowns (P7: nunca texto libre).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_STATES = ["Ready for Dev", "In Progress", "Blocked", "Code Review", "Ready for QA"]


class FakeProvider:
    name = "azure_devops"

    def fetch_states(self):
        return list(_STATES)


def _machine(cell) -> dict:
    return {
        "tracker_state_machine": {
            "developer": {
                "input_states": ["Ready for Dev"],
                "in_progress": "In Progress",
                "next_state_ok": "Code Review",
                "by_work_item_type": cell,
            }
        }
    }


# ── Validación de esquema ────────────────────────────────────────────────────

def test_valida_by_work_item_type_ok():
    from services.client_profile import _check_tracker_state_machine

    errors, _warnings = _check_tracker_state_machine(
        _machine({"Task": {"in_progress": "In Progress", "next_state_ok": "Code Review"},
                  "Epic": {"next_state_ok": "Resolved"}})["tracker_state_machine"]
    )
    assert errors == []


def test_ausente_es_retrocompatible():
    from services.client_profile import _check_tracker_state_machine

    errors, _ = _check_tracker_state_machine(
        {"developer": {"input_states": ["Ready for Dev"], "next_state_ok": "Code Review"}}
    )
    assert errors == [], "un perfil legacy (sin by_work_item_type) sigue siendo válido"


@pytest.mark.parametrize(
    "cell, fragmento",
    [
        (["no", "soy", "dict"], "by_work_item_type debe ser un objeto"),
        ({"Task": "no soy dict"}, "by_work_item_type.Task debe ser un objeto"),
        ({"Task": {"next_state_ok": 42}}, "by_work_item_type.Task.next_state_ok debe ser string"),
        ({"Task": {"in_progress": ["x"]}}, "by_work_item_type.Task.in_progress debe ser string"),
    ],
)
def test_rechaza_by_work_item_type_no_dict(cell, fragmento):
    from services.client_profile import _check_tracker_state_machine

    errors, _ = _check_tracker_state_machine(_machine(cell)["tracker_state_machine"])
    assert any(fragmento in e for e in errors), f"esperaba '{fragmento}' en {errors}"


def test_warning_estado_fuera_de_tracker():
    from harness.task_states import validate_states_against_tracker

    warnings = validate_states_against_tracker(
        _machine({"Task": {"next_state_ok": "Estado Inventado"}}), _STATES
    )
    matches = [w for w in warnings if w["value"] == "Estado Inventado"]
    assert len(matches) == 1
    assert matches[0]["reason"] == "state_not_in_tracker"
    assert matches[0]["work_item_type"] == "Task"
    assert matches[0]["agent_type"] == "developer"


# ── Endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)

    from app import create_app
    import project_manager
    import services.client_profile as cp
    import api.client_profile as api_cp

    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(cp, "projects_dir", lambda: projects_dir)
    monkeypatch.setattr(api_cp, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(api_cp, "get_tracker_provider", lambda project: FakeProvider(),
                        raising=True)

    pdir = projects_dir / "RSPACIFICO"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "config.json").write_text(
        json.dumps({"name": "RSPACIFICO", "display_name": "RSPACIFICO",
                    "issue_tracker": {"type": "azure_devops"}}, indent=2),
        encoding="utf-8",
    )

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def test_get_devuelve_work_item_types_y_valid_states(client):
    from db import init_db, session_scope
    from models import Ticket

    init_db()
    with session_scope() as s:
        s.add(Ticket(ado_id=99400, project="Strategist_Pacifico",
                     stacky_project_name="RSPACIFICO", title="t",
                     work_item_type="Impediment", stacky_status="idle"))

    r = client.get("/api/projects/RSPACIFICO/client-profile")
    assert r.status_code == 200
    body = r.get_json()

    assert body["valid_states"] == _STATES, "los estados salen del tracker real (fetch_states)"
    wits = body["work_item_types"]
    assert "Impediment" in wits, "los tipos ya sincronizados del proyecto deben aparecer"
    for canonical in ("Epic", "Task", "Bug", "User Story"):
        assert canonical in wits, f"falta el tipo canónico {canonical}"
    assert len(wits) == len({w.casefold() for w in wits}), "sin duplicados case-insensitive"

    with session_scope() as s:
        row = s.query(Ticket).filter(Ticket.ado_id == 99400).one_or_none()
        if row is not None:
            s.delete(row)


def test_put_persiste_by_work_item_type_y_reaparece_en_get(client):
    profile = {
        "schema_version": 1,
        "tracker_state_machine": {
            "developer": {
                "input_states": ["Ready for Dev"],
                "in_progress": "In Progress",
                "next_state_ok": "Code Review",
                "by_work_item_type": {"Task": {"next_state_ok": "Ready for QA"}},
            }
        },
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["ok"] is True

    got = client.get("/api/projects/RSPACIFICO/client-profile").get_json()
    cell = got["profile"]["tracker_state_machine"]["developer"]["by_work_item_type"]
    assert cell == {"Task": {"next_state_ok": "Ready for QA"}}


def test_put_con_estado_inexistente_avisa_sin_bloquear(client):
    profile = {
        "schema_version": 1,
        "tracker_state_machine": {
            "developer": {
                "input_states": ["Ready for Dev"],
                "next_state_ok": "Code Review",
                "by_work_item_type": {"Bug": {"next_state_ok": "Estado Fantasma"}},
            }
        },
    }
    r = client.put("/api/projects/RSPACIFICO/client-profile", json={"profile": profile})

    assert r.status_code == 200, "un estado desconocido AVISA, no bloquea el guardado"
    warnings = r.get_json()["state_warnings"]
    assert any(w["value"] == "Estado Fantasma" and w.get("work_item_type") == "Bug"
               for w in warnings), warnings
