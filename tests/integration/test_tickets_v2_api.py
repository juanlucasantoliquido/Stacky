"""
Tests de `/api/tickets/v2` — endpoint unificado scan + metadata (FASE 4).

Cobertura:
    * Estructura de respuesta (ok/tickets/count/metadata_status).
    * Merge correcto scan ⟷ metadata (con y sin metadata en store).
    * Indicadores derivados: has_commits, has_notes, metadata_stale.
    * Query params: ?metadata, ?fields, ?project.
    * Helper `_is_metadata_stale` (unidad).
    * Backward compat con /api/tickets clásico.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest import mock

import pytest

from dashboard_server import _is_metadata_stale, app
from ticket_metadata_store import get_store, reset_singleton_for_tests


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singletons(tmp_path, monkeypatch):
    """Aísla cada test: store singleton + data dir → tmp_path."""
    import ticket_metadata_store as _tms

    monkeypatch.setattr(_tms, "_DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(_tms, "_STORE_PATH", tmp_path / "data" / "ticket_metadata.json")
    monkeypatch.setattr(_tms, "_LOCK_PATH", tmp_path / "data" / "ticket_metadata.json.lock")
    reset_singleton_for_tests()
    yield
    reset_singleton_for_tests()


@pytest.fixture
def client():
    """Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as cli:
        yield cli


@pytest.fixture
def store():
    """Store singleton re-creado tras reset."""
    return get_store()


@pytest.fixture
def mock_scan(monkeypatch):
    """Monkeypatcha `_scan_tickets` para tests deterministas.

    Devuelve un callable que acepta una lista de tickets a simular, de forma
    que cada test controla exactamente qué tickets aparecen.
    """
    import dashboard_server as _ds

    state: Dict[str, List[Dict[str, Any]]] = {"tickets": []}

    def _set_tickets(tickets: List[Dict[str, Any]]) -> None:
        state["tickets"] = tickets

    monkeypatch.setattr(_ds, "_scan_tickets", lambda: list(state["tickets"]))
    return _set_tickets


@pytest.fixture
def mock_runtime(monkeypatch):
    """Monkeypatcha `_get_runtime` a un proyecto conocido."""
    import dashboard_server as _ds

    monkeypatch.setattr(_ds, "_get_runtime", lambda: {
        "name": "TESTPROJ",
        "display_name": "TESTPROJ",
        "workspace_root": "/fake",
        "tickets_base": "/fake/tickets",
        "state_path": "/fake/state.json",
        "agents": {},
    })


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fake_ticket(ticket_id: str, estado: str = "dev_en_proceso", **extra) -> Dict[str, Any]:
    """Construye un ticket similar al output de _scan_tickets()."""
    base = {
        "ticket_id": ticket_id,
        "titulo": f"Ticket {ticket_id}",
        "estado_tracker": estado,
        "asignado": "Juan Luca",
        "estado_base": estado,
        "pipeline_estado": estado,
        "folder": f"/fake/{ticket_id}",
        "pm_files": {},
        "dev_completado": False,
        "has_placeholders": False,
        "error": None,
        "intentos_pm": 0,
        "intentos_dev": 0,
        "intentos_tester": 0,
        "priority": 1,
    }
    base.update(extra)
    return base


# ── Tests: _is_metadata_stale (unit) ─────────────────────────────────────────


class TestIsMetadataStale:
    """Cubre el helper `_is_metadata_stale` aisladamente."""

    def test_none_is_stale(self):
        assert _is_metadata_stale(None) is True

    def test_empty_string_is_stale(self):
        assert _is_metadata_stale("") is True

    def test_malformed_is_stale(self):
        assert _is_metadata_stale("not-a-date") is True

    def test_fresh_is_not_stale(self):
        fresh = datetime.now(timezone.utc).isoformat()
        assert _is_metadata_stale(fresh) is False

    def test_just_under_threshold_is_not_stale(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        assert _is_metadata_stale(ts, threshold_minutes=15) is False

    def test_over_threshold_is_stale(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        assert _is_metadata_stale(ts, threshold_minutes=15) is True

    def test_custom_threshold(self):
        ts = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        assert _is_metadata_stale(ts, threshold_minutes=1) is True
        assert _is_metadata_stale(ts, threshold_minutes=10) is False

    def test_naive_datetime_is_accepted(self):
        """ISO sin tzinfo se trata como UTC — no debe crashear."""
        ts = datetime.utcnow().replace(microsecond=0).isoformat()
        # No lanza excepción; devuelve bool
        assert isinstance(_is_metadata_stale(ts), bool)


# ── Tests: /api/tickets/v2 ───────────────────────────────────────────────────


class TestTicketsV2Basic:
    """Forma y contenido básico de la respuesta."""

    def test_response_structure(self, client, mock_runtime, mock_scan):
        """GET /api/tickets/v2 devuelve ok/tickets/count/metadata_status."""
        mock_scan([_fake_ticket("27698")])
        resp = client.get("/api/tickets/v2")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "tickets" in data
        assert "count" in data
        assert "metadata_status" in data
        assert isinstance(data["tickets"], list)

    def test_count_matches_tickets(self, client, mock_runtime, mock_scan):
        """`count` siempre matchea `len(tickets)`."""
        mock_scan([_fake_ticket(str(i)) for i in range(5)])
        resp = client.get("/api/tickets/v2")
        data = resp.get_json()
        assert data["count"] == len(data["tickets"]) == 5

    def test_empty_scan_empty_response(self, client, mock_runtime, mock_scan):
        """Sin tickets en scan → count=0, tickets=[]."""
        mock_scan([])
        resp = client.get("/api/tickets/v2")
        data = resp.get_json()
        assert data["count"] == 0
        assert data["tickets"] == []

    def test_metadata_status_shape(self, client, mock_runtime, mock_scan):
        """`metadata_status` tiene los 4 campos esperados."""
        mock_scan([])
        resp = client.get("/api/tickets/v2")
        status = resp.get_json()["metadata_status"]
        assert set(status.keys()) == {
            "last_indexed_at", "indexed_count", "indexing_error", "running"
        }


class TestTicketsV2MetadataMerge:
    """Merge scan + metadata."""

    def test_ticket_without_metadata_has_defaults(self, client, mock_runtime, mock_scan):
        """Ticket sin metadata en store → defaults None/False/[]."""
        mock_scan([_fake_ticket("99999")])
        resp = client.get("/api/tickets/v2?metadata=true")
        data = resp.get_json()
        t = data["tickets"][0]
        assert t["ticket_id"] == "99999"
        assert t["color"] is None
        assert t["user_tags"] == []
        assert t["commits_count"] is None
        assert t["last_commit_hash"] is None
        assert t["notes_count"] is None
        assert t["has_commits"] is False
        assert t["has_notes"] is False
        assert t["metadata_stale"] is True  # sin last_indexed_at

    def test_ticket_with_metadata_exposes_fields(self, client, store, mock_runtime, mock_scan):
        """Ticket con metadata en store → campos visibles en v2."""
        store.set_color("27698", "#ff0000")
        store.add_user_tag("27698", "urgente")
        store.add_user_tag("27698", "refactor")
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2?metadata=true")
        t = next((x for x in resp.get_json()["tickets"]
                  if x["ticket_id"] == "27698"), None)
        assert t is not None
        assert t["color"] == "#ff0000"
        assert set(t["user_tags"]) == {"urgente", "refactor"}
        # Sin indexer run todavía
        assert t["has_commits"] is False
        assert t["has_notes"] is False

    def test_scan_fields_preserved(self, client, store, mock_runtime, mock_scan):
        """El merge no pisa campos del scan original."""
        store.set_color("27698", "#aabbcc")
        mock_scan([_fake_ticket(
            "27698", estado="dev_en_proceso", asignado="Juan Luca",
        )])

        resp = client.get("/api/tickets/v2")
        t = resp.get_json()["tickets"][0]
        assert t["pipeline_estado"] == "dev_en_proceso"
        assert t["asignado"] == "Juan Luca"
        assert t["color"] == "#aabbcc"  # metadata no pisó scan

    def test_has_commits_true_when_indexer_set_count(self, client, store, mock_runtime, mock_scan):
        """`has_commits` derivado de commits_count > 0."""
        store.bulk_update({"27698": {
            "commits_count": 3,
            "last_commit_hash": "a73cf35",
            "last_commit_at": datetime.now(timezone.utc).isoformat(),
            "last_indexed_at": datetime.now(timezone.utc).isoformat(),
        }})
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2")
        t = resp.get_json()["tickets"][0]
        assert t["commits_count"] == 3
        assert t["last_commit_hash"] == "a73cf35"
        assert t["has_commits"] is True
        assert t["metadata_stale"] is False

    def test_has_notes_true_when_notes_count_positive(self, client, store, mock_runtime, mock_scan):
        store.bulk_update({"27698": {
            "notes_count": 2,
            "last_note_at": datetime.now(timezone.utc).isoformat(),
            "last_indexed_at": datetime.now(timezone.utc).isoformat(),
        }})
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2")
        t = resp.get_json()["tickets"][0]
        assert t["has_notes"] is True
        assert t["notes_count"] == 2

    def test_metadata_stale_when_last_indexed_old(self, client, store, mock_runtime, mock_scan):
        """last_indexed_at > 15 min ⇒ metadata_stale=True."""
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        store.bulk_update({"27698": {"last_indexed_at": old_ts}})
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2")
        t = resp.get_json()["tickets"][0]
        assert t["metadata_stale"] is True

    def test_metadata_stale_false_when_recent(self, client, store, mock_runtime, mock_scan):
        fresh = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat()
        store.bulk_update({"27698": {"last_indexed_at": fresh}})
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2")
        t = resp.get_json()["tickets"][0]
        assert t["metadata_stale"] is False


class TestTicketsV2QueryParams:
    """Query params ?metadata, ?fields, ?project."""

    def test_metadata_false_skips_merge(self, client, store, mock_runtime, mock_scan):
        """?metadata=false omite campos de metadata."""
        store.set_color("27698", "#ff0000")
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2?metadata=false")
        t = resp.get_json()["tickets"][0]
        assert "color" not in t
        assert "has_commits" not in t
        assert "user_tags" not in t
        # Pero los campos de scan sí están
        assert t["ticket_id"] == "27698"
        assert t["pipeline_estado"] == "dev_en_proceso"

    @pytest.mark.parametrize("val", ["false", "FALSE", "0", "no", "off"])
    def test_metadata_falsy_values(self, client, store, mock_runtime, mock_scan, val):
        """?metadata acepta false/0/no/off (case-insensitive)."""
        mock_scan([_fake_ticket("27698")])
        resp = client.get(f"/api/tickets/v2?metadata={val}")
        t = resp.get_json()["tickets"][0]
        assert "color" not in t

    def test_fields_whitelist(self, client, store, mock_runtime, mock_scan):
        """?fields=a,b,c limita a esos campos + ticket_id."""
        store.set_color("27698", "#ff0000")
        mock_scan([_fake_ticket("27698")])

        resp = client.get("/api/tickets/v2?fields=color,pipeline_estado,has_commits")
        t = resp.get_json()["tickets"][0]
        assert set(t.keys()) == {"ticket_id", "color", "pipeline_estado", "has_commits"}

    def test_fields_always_includes_ticket_id(self, client, mock_runtime, mock_scan):
        """ticket_id se auto-incluye aunque no esté en ?fields."""
        mock_scan([_fake_ticket("27698")])
        resp = client.get("/api/tickets/v2?fields=color")
        t = resp.get_json()["tickets"][0]
        assert "ticket_id" in t

    def test_project_matches_active(self, client, mock_runtime, mock_scan):
        """?project= que matchea el runtime → devuelve tickets normales."""
        mock_scan([_fake_ticket("27698")])
        resp = client.get("/api/tickets/v2?project=TESTPROJ")
        data = resp.get_json()
        assert data["count"] == 1
        assert data["project"] == "TESTPROJ"

    def test_project_case_insensitive(self, client, mock_runtime, mock_scan):
        mock_scan([_fake_ticket("27698")])
        resp = client.get("/api/tickets/v2?project=testproj")
        assert resp.get_json()["count"] == 1

    def test_project_mismatch_returns_empty(self, client, mock_runtime, mock_scan):
        """?project=<otro> → count=0, filter_mismatch=true."""
        mock_scan([_fake_ticket("27698")])
        resp = client.get("/api/tickets/v2?project=OTRO_PROJECT")
        data = resp.get_json()
        assert data["count"] == 0
        assert data["tickets"] == []
        assert data.get("filter_mismatch") is True


class TestTicketsV2BackwardCompat:
    """v2 no rompe /api/tickets clásico."""

    def test_api_tickets_still_exists(self, client, mock_runtime, mock_scan):
        """/api/tickets sigue respondiendo el formato viejo."""
        mock_scan([_fake_ticket("27698")])
        resp = client.get("/api/tickets")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        # Sin envoltura ok/tickets/count — formato original
        assert data[0]["ticket_id"] == "27698"

    def test_v2_includes_all_scan_fields(self, client, mock_runtime, mock_scan):
        """v2 NO elimina ningún campo que /api/tickets retornaba."""
        scan_ticket = _fake_ticket("27698",
                                   dev_completado=True,
                                   priority=5,
                                   intentos_dev=2)
        mock_scan([scan_ticket])

        legacy = client.get("/api/tickets").get_json()[0]
        v2_item = client.get("/api/tickets/v2").get_json()["tickets"][0]

        # Todos los keys de legacy aparecen en v2
        missing = set(legacy.keys()) - set(v2_item.keys())
        assert not missing, f"v2 perdió campos vs /api/tickets: {missing}"


class TestTicketsV2ErrorHandling:
    """Degradación grácil ante fallas."""

    def test_store_failure_degrades_gracefully(self, client, mock_runtime, mock_scan, monkeypatch):
        """Si store.get_all() crashea, v2 devuelve scan con metadata=defaults."""
        mock_scan([_fake_ticket("27698")])

        def _boom():
            raise RuntimeError("store muerto")

        from ticket_metadata_store import _TicketMetadataStore
        monkeypatch.setattr(_TicketMetadataStore, "get_all", lambda self: _boom())

        resp = client.get("/api/tickets/v2?metadata=true")
        # No 500: degrada a defaults
        assert resp.status_code == 200
        data = resp.get_json()
        t = data["tickets"][0]
        assert t["color"] is None
        assert t["user_tags"] == []
        assert t["metadata_stale"] is True
