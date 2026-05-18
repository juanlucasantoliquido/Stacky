"""Tests del comment indexer de PM Intelligence Suite.

Sin red. Mock de AdoClient.fetch_comments via objeto stub.
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


@pytest.fixture(autouse=True)
def _pm_tables_ready():
    """Garantiza que las tablas PM existan, sin levantar la app Flask completa.

    Crear la app entera dispara watcher threads que interfieren con otros tests
    en la misma corrida. Solo necesitamos init_db.
    """
    from db import init_db, session_scope
    from services.pm.models import PmWorkItemComment

    init_db()
    yield
    with session_scope() as session:
        session.query(PmWorkItemComment).delete()


class FakeAdoClient:
    """Stub de AdoClient para tests — solo necesita fetch_comments."""
    def __init__(self, comments_by_id: dict[int, list[dict]]):
        self._map = comments_by_id

    def fetch_comments(self, ado_id: int, top: int = 20):  # noqa: ARG002
        return list(self._map.get(int(ado_id), []))


# ── html_to_text ──────────────────────────────────────────────────────────────

def test_html_to_text_strips_basic_tags():
    from services.pm.pm_comment_indexer import html_to_text
    assert html_to_text("<p>Hola <b>mundo</b></p>") == "Hola mundo"


def test_html_to_text_handles_line_breaks():
    from services.pm.pm_comment_indexer import html_to_text
    result = html_to_text("<p>uno</p><p>dos</p>")
    assert "uno" in result and "dos" in result
    assert "\n" in result


def test_html_to_text_empty_returns_empty():
    from services.pm.pm_comment_indexer import html_to_text
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


# ── sanitize (html strip + PII mask) ──────────────────────────────────────────

def test_sanitize_removes_email():
    from services.pm.pm_comment_indexer import sanitize_comment_text
    result = sanitize_comment_text("<p>Contactame a juan.perez@empresa.com gracias</p>")
    assert "juan.perez@empresa.com" not in result
    assert "ZZZ_PII_" in result


def test_sanitize_removes_dni():
    from services.pm.pm_comment_indexer import sanitize_comment_text
    result = sanitize_comment_text("<p>El cliente con DNI 12345678 reclamó</p>")
    assert "12345678" not in result
    assert "ZZZ_PII_" in result


def test_sanitize_preserves_safe_text():
    from services.pm.pm_comment_indexer import sanitize_comment_text
    result = sanitize_comment_text("<p>El ticket está listo para QA</p>")
    assert "ticket" in result
    assert "QA" in result
    assert "ZZZ_PII_" not in result


def test_sanitize_empty_input_returns_empty():
    from services.pm.pm_comment_indexer import sanitize_comment_text
    assert sanitize_comment_text("") == ""
    assert sanitize_comment_text(None) == ""


# ── index_comments_for_work_item ──────────────────────────────────────────────

def test_index_persists_sanitized_comments():
    from db import session_scope
    from services.pm.models import PmWorkItemComment
    from services.pm.pm_comment_indexer import index_comments_for_work_item

    client = FakeAdoClient({
        100: [
            {"author": "dev1", "date": "2026-05-15", "text": "<p>Listo, mando mail a a@b.com</p>"},
            {"author": "dev2", "date": "2026-05-16", "text": "<p>OK</p>"},
        ]
    })

    result = index_comments_for_work_item(client=client, ado_id=100, project="TestPM")
    assert result["inserted"] == 2
    assert result["skipped_duplicates"] == 0

    with session_scope() as session:
        rows = session.query(PmWorkItemComment).filter(PmWorkItemComment.ado_id == 100).all()
        assert len(rows) == 2
        # PII masked
        assert all("a@b.com" not in (r.text_plain or "") for r in rows)
        # ai_analyzed siempre False en Fase 1
        assert all(r.ai_analyzed is False for r in rows)
        assert all(r.sentiment_label is None for r in rows)


def test_index_is_idempotent():
    from db import session_scope
    from services.pm.models import PmWorkItemComment
    from services.pm.pm_comment_indexer import index_comments_for_work_item

    comments = {200: [{"author": "x", "date": "2026-05-15", "text": "<p>algo</p>"}]}
    client = FakeAdoClient(comments)

    r1 = index_comments_for_work_item(client=client, ado_id=200, project="TestPM")
    assert r1["inserted"] == 1
    assert r1["skipped_duplicates"] == 0

    r2 = index_comments_for_work_item(client=client, ado_id=200, project="TestPM")
    assert r2["inserted"] == 0
    assert r2["skipped_duplicates"] == 1

    with session_scope() as session:
        count = session.query(PmWorkItemComment).filter(PmWorkItemComment.ado_id == 200).count()
        assert count == 1


def test_index_skips_empty_comments():
    from db import session_scope
    from services.pm.models import PmWorkItemComment
    from services.pm.pm_comment_indexer import index_comments_for_work_item

    client = FakeAdoClient({
        300: [
            {"author": "dev", "date": "2026-05-15", "text": ""},
            {"author": "dev", "date": "2026-05-15", "text": "<p>   </p>"},
            {"author": "dev", "date": "2026-05-15", "text": "<p>real comment</p>"},
        ]
    })
    r = index_comments_for_work_item(client=client, ado_id=300, project="TestPM")
    assert r["inserted"] == 1

    with session_scope() as session:
        count = session.query(PmWorkItemComment).filter(PmWorkItemComment.ado_id == 300).count()
        assert count == 1


def test_index_handles_ado_error_gracefully():
    from services.ado_client import AdoApiError
    from services.pm.pm_comment_indexer import index_comments_for_work_item

    class FailingClient:
        def fetch_comments(self, ado_id, top=20):  # noqa: ARG002
            raise AdoApiError("simulated 503")

    r = index_comments_for_work_item(client=FailingClient(), ado_id=999, project="TestPM")
    assert r["inserted"] == 0
    assert "error" in r


# ── bulk indexing ─────────────────────────────────────────────────────────────

def test_index_bulk_aggregates_totals():
    from services.pm.pm_comment_indexer import index_comments_bulk

    client = FakeAdoClient({
        400: [{"author": "a", "date": "2026-05-15", "text": "<p>uno</p>"}],
        401: [
            {"author": "b", "date": "2026-05-16", "text": "<p>dos</p>"},
            {"author": "c", "date": "2026-05-16", "text": "<p>tres</p>"},
        ],
    })
    totals = index_comments_bulk(
        client=client, project="TestPM", ado_ids=[400, 401], top_per_item=20,
    )
    assert totals["inserted"] == 3
    assert totals["total_fetched"] == 3
    assert totals["errors"] == []


def test_index_bulk_continues_after_error_on_one_item():
    from services.ado_client import AdoApiError
    from services.pm.pm_comment_indexer import index_comments_bulk

    class PartialClient:
        def fetch_comments(self, ado_id: int, top: int = 20):  # noqa: ARG002
            if ado_id == 500:
                raise AdoApiError("boom")
            return [{"author": "x", "date": "2026-05-15", "text": "<p>ok</p>"}]

    totals = index_comments_bulk(
        client=PartialClient(), project="TestPM", ado_ids=[500, 501], top_per_item=20,
    )
    assert totals["inserted"] == 1
    assert len(totals["errors"]) == 1
    assert totals["errors"][0]["ado_id"] == 500
