"""
Tests para ado_manager — AdoManager facade + operations.

Usa un FakeHttpClient para no necesitar credenciales ADO.
Cobertura: get_ticket_context, publish_comment (dedupe/published),
update_state (guard ok/fail), create_ticket_idempotent (new/existing),
search_work_items, validaciones de inputs.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from ado_manager.operations import (
    HttpClient,
    get_ticket_context,
    publish_comment,
    update_state,
    create_ticket_idempotent,
    search_work_items,
)
from ado_manager.dedupe import DedupeCache
from ado_manager.manager import AdoManager


# ── Fake HTTP Client ──────────────────────────────────────────────────────────


class FakeHttpClient:
    """Cliente HTTP falso para tests. Responde con datos configurables."""

    def __init__(self, responses: dict[str, Any] | None = None):
        self._responses: dict[str, Any] = responses or {}
        self.calls: list[dict[str, Any]] = []

    def _record(self, method: str, url: str, payload: Any = None) -> dict[str, Any]:
        self.calls.append({"method": method, "url": url, "payload": payload})
        for pattern, resp in self._responses.items():
            if pattern in url:
                return resp
        return {}

    def get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        return self._record("GET", url)

    def post(self, url: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return self._record("POST", url, payload)

    def patch(self, url: str, payload: Any, **kwargs: Any) -> dict[str, Any]:
        return self._record("PATCH", url, payload)


# ── get_ticket_context ────────────────────────────────────────────────────────


def test_get_ticket_context_ok():
    client = FakeHttpClient(
        responses={
            "workItems/1234?": {
                "fields": {
                    "System.Title": "Mi ticket",
                    "System.State": "Technical review",
                    "System.Description": "Desc",
                }
            },
            "workItems/1234/comments": {
                "comments": [
                    {"id": 99, "text": "Comentario", "createdBy": {"displayName": "Dev"}}
                ]
            },
        }
    )
    ctx = get_ticket_context(client, "UbimiaPacifico", "Strategist_Pacifico", 1234)
    assert ctx.id == 1234
    assert ctx.title == "Mi ticket"
    assert ctx.state == "Technical review"
    assert len(ctx.comments) == 1
    assert ctx.comments[0].comment_id == 99


def test_get_ticket_context_invalid_id():
    client = FakeHttpClient()
    with pytest.raises(ValueError):
        get_ticket_context(client, "org", "proj", -1)


def test_get_ticket_context_zero_id():
    client = FakeHttpClient()
    with pytest.raises(ValueError):
        get_ticket_context(client, "org", "proj", 0)


# ── publish_comment ───────────────────────────────────────────────────────────


def test_publish_comment_first_time():
    client = FakeHttpClient(
        responses={"comments?": {"id": 55}}
    )
    cache = DedupeCache()  # in-memory, vacío
    result = publish_comment(
        client, "org", "proj", 1234, "## Análisis", cache, auto_html=False
    )
    assert result.dedupe == "PUBLISHED"
    assert result.comment_id == 55
    assert result.work_item_id == 1234


def test_publish_comment_deduped():
    client = FakeHttpClient(responses={"comments?": {"id": 55}})
    cache = DedupeCache()
    # Primera publicación
    publish_comment(client, "org", "proj", 1234, "## Análisis", cache, auto_html=False)
    # Segunda — debe ser DEDUPED
    result = publish_comment(
        client, "org", "proj", 1234, "## Análisis", cache, auto_html=False
    )
    assert result.dedupe == "DEDUPED"
    assert result.comment_id is None


def test_publish_comment_empty_body():
    client = FakeHttpClient()
    cache = DedupeCache()
    with pytest.raises(ValueError):
        publish_comment(client, "org", "proj", 1234, "", cache, auto_html=False)


def test_publish_comment_different_bodies_both_published():
    client = FakeHttpClient(responses={"comments?": {"id": 1}})
    cache = DedupeCache()
    r1 = publish_comment(client, "org", "proj", 1, "Body A", cache, auto_html=False)
    r2 = publish_comment(client, "org", "proj", 1, "Body B", cache, auto_html=False)
    assert r1.dedupe == "PUBLISHED"
    assert r2.dedupe == "PUBLISHED"


# ── update_state ──────────────────────────────────────────────────────────────


def test_update_state_no_guard():
    client = FakeHttpClient(responses={"workItems/1?": {}})
    result = update_state(client, "org", "proj", 1, "To Do")
    assert result.success is True
    assert result.new_state == "To Do"


def test_update_state_guard_matches():
    client = FakeHttpClient(
        responses={
            "workItems/42?$": {
                "fields": {
                    "System.Title": "T",
                    "System.State": "Technical review",
                    "System.Description": "",
                }
            },
            "workItems/42/comments": {"comments": []},
            "workItems/42?api": {},
        }
    )
    result = update_state(
        client, "org", "proj", 42, "To Do",
        expected_current_state="Technical review"
    )
    assert result.success is True
    assert result.previous_state == "Technical review"


def test_update_state_guard_mismatch():
    client = FakeHttpClient(
        responses={
            "workItems/42?$": {
                "fields": {
                    "System.Title": "T",
                    "System.State": "Done",
                    "System.Description": "",
                }
            },
            "workItems/42/comments": {"comments": []},
        }
    )
    result = update_state(
        client, "org", "proj", 42, "To Do",
        expected_current_state="Technical review"
    )
    assert result.success is False
    assert "Done" in result.reason
    assert "Technical review" in result.reason


def test_update_state_empty_state():
    client = FakeHttpClient()
    with pytest.raises(ValueError):
        update_state(client, "org", "proj", 1, "")


# ── create_ticket_idempotent ──────────────────────────────────────────────────


def test_create_ticket_new():
    client = FakeHttpClient(
        responses={
            "wiql": {"workItems": []},
            "workItems/$Task": {"id": 777},
        }
    )
    result = create_ticket_idempotent(
        client, "org", "proj", "Nuevo ticket", "Task"
    )
    assert result.created is True
    assert result.work_item_id == 777


def test_create_ticket_existing():
    client = FakeHttpClient(
        responses={
            "wiql": {"workItems": [{"id": 42, "title": "Ticket existente"}]},
        }
    )
    result = create_ticket_idempotent(
        client, "org", "proj", "Ticket existente", "Task"
    )
    assert result.created is False
    assert result.work_item_id == 42
    assert "42" in result.reason


def test_create_ticket_empty_title():
    client = FakeHttpClient()
    with pytest.raises(ValueError):
        create_ticket_idempotent(client, "org", "proj", "", "Task")


# ── search_work_items ─────────────────────────────────────────────────────────


def test_search_work_items_ok():
    client = FakeHttpClient(
        responses={
            "wiql": {"workItems": [{"id": 1}, {"id": 2}]}
        }
    )
    result = search_work_items(
        client, "org", "proj",
        "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = 'proj'"
    )
    assert result.total == 2
    assert len(result.items) == 2


def test_search_work_items_empty_query():
    client = FakeHttpClient()
    with pytest.raises(ValueError):
        search_work_items(client, "org", "proj", "")


# ── AdoManager facade ─────────────────────────────────────────────────────────


def test_ado_manager_facade_publish(tmp_path):
    client = FakeHttpClient(responses={"comments?": {"id": 88}})
    mgr = AdoManager(
        org="UbimiaPacifico",
        project="Strategist_Pacifico",
        client=client,
        dedupe_cache_path=str(tmp_path / "dedupe.jsonl"),
    )
    result = mgr.publish_comment(999, "## Test", auto_html=False)
    assert result.dedupe == "PUBLISHED"
    assert result.comment_id == 88


def test_ado_manager_facade_deduped(tmp_path):
    client = FakeHttpClient(responses={"comments?": {"id": 88}})
    mgr = AdoManager(
        org="UbimiaPacifico",
        project="Strategist_Pacifico",
        client=client,
        dedupe_cache_path=str(tmp_path / "dedupe.jsonl"),
    )
    mgr.publish_comment(999, "## Test", auto_html=False)
    result = mgr.publish_comment(999, "## Test", auto_html=False)
    assert result.dedupe == "DEDUPED"
