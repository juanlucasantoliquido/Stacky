"""Tests para services/ado_context.

Cubre:
  - is_enrichment_enabled: default + variantes de ADO_CONTEXT_ENRICH_AGENTS
  - build_ado_context_blocks: comments-only, attachments-only, mixto, errores
  - mime_type derivado por extensión
  - tope ADO_CONTEXT_ATTACH_MAX_TEXT_FILES
  - enrich: idempotencia, agent allow-list, return_stats
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── Helpers / fakes ──────────────────────────────────────────────────────────

class _FakeAdoClient:
    """Doble de AdoClient con respuestas configurables y contador de llamadas."""

    def __init__(
        self,
        comments=None,
        attachments=None,
        comments_raises: Exception | None = None,
        attachments_raises: Exception | None = None,
    ) -> None:
        self._comments = comments or []
        self._attachments = attachments or []
        self._comments_raises = comments_raises
        self._attachments_raises = attachments_raises
        self.calls: dict[str, int] = {"fetch_comments": 0, "fetch_attachments": 0}

    def fetch_comments(self, ado_id, top=20):
        self.calls["fetch_comments"] += 1
        if self._comments_raises is not None:
            raise self._comments_raises
        return list(self._comments)

    def fetch_attachments(self, ado_id, max_text_bytes=65_536):
        self.calls["fetch_attachments"] += 1
        if self._attachments_raises is not None:
            raise self._attachments_raises
        return list(self._attachments)


@pytest.fixture
def patch_client(monkeypatch):
    """Inyecta un FakeAdoClient en el módulo services.ado_client."""
    from services import ado_client as ado_client_module

    fake_holder: dict[str, _FakeAdoClient] = {}

    def _install(client: _FakeAdoClient) -> None:
        fake_holder["client"] = client
        monkeypatch.setattr(ado_client_module, "AdoClient", lambda *a, **kw: client)

    return _install


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Asegura que las env vars del módulo no contaminen entre tests."""
    monkeypatch.delenv("ADO_CONTEXT_ENRICH_AGENTS", raising=False)
    monkeypatch.delenv("ADO_CONTEXT_ATTACH_MAX_TEXT_FILES", raising=False)


# ── is_enrichment_enabled ────────────────────────────────────────────────────

def test_default_enriches_all_known_agents():
    from services import ado_context

    for a in ("business", "functional", "technical", "developer", "qa", "debug", "pr-review", "custom"):
        assert ado_context.is_enrichment_enabled(a) is True


def test_unknown_agent_is_not_enriched_by_default():
    from services import ado_context
    assert ado_context.is_enrichment_enabled("nonexistent-agent") is False


def test_env_all_enables_every_agent(monkeypatch):
    from services import ado_context
    monkeypatch.setenv("ADO_CONTEXT_ENRICH_AGENTS", "all")
    assert ado_context.is_enrichment_enabled("any-thing") is True


def test_env_off_disables_enrichment(monkeypatch):
    from services import ado_context
    monkeypatch.setenv("ADO_CONTEXT_ENRICH_AGENTS", "off")
    assert ado_context.is_enrichment_enabled("technical") is False


def test_env_csv_subset(monkeypatch):
    from services import ado_context
    monkeypatch.setenv("ADO_CONTEXT_ENRICH_AGENTS", "qa,developer")
    assert ado_context.is_enrichment_enabled("qa") is True
    assert ado_context.is_enrichment_enabled("developer") is True
    assert ado_context.is_enrichment_enabled("functional") is False


# ── build_ado_context_blocks ─────────────────────────────────────────────────

def test_build_blocks_with_comments_only(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        comments=[
            {"author": "Alice", "date": "2026-05-01", "text": "<p>Primero.</p>"},
            {"author": "Bob", "date": "2026-05-02", "text": "<p>Segundo.</p>"},
        ],
    ))
    blocks, stats = ado_context.build_ado_context_blocks(123)
    assert stats["comments_count"] == 2
    assert stats["attachments_count"] == 0
    assert len(blocks) == 1
    b = blocks[0]
    assert b["id"] == "ado-comments"
    assert b["title"] == "Comentarios ADO del ticket"
    assert "Alice" in b["content"] and "Bob" in b["content"]
    assert "Primero" in b["content"]


def test_build_blocks_skips_empty_comment_text(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        comments=[
            {"author": "Alice", "date": "2026-05-01", "text": "<p>Útil.</p>"},
            {"author": "Bot", "date": "2026-05-02", "text": "<br/>"},  # vacío tras strip
        ],
    ))
    _, stats = ado_context.build_ado_context_blocks(123)
    assert stats["comments_count"] == 1


def test_build_blocks_with_attachments_metadata(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        attachments=[
            {
                "name": "captura.png",
                "url": "https://dev.azure.com/x/_apis/wit/attachments/abc",
                "size": 2048,
                "text_content": None,
            },
            {
                "name": "informe.pdf",
                "url": "https://dev.azure.com/x/_apis/wit/attachments/def",
                "size": 1024 * 1024,
                "text_content": None,
            },
        ],
    ))
    blocks, stats = ado_context.build_ado_context_blocks(456)
    assert stats["attachments_count"] == 2
    assert stats["attachments_text_inlined"] == 0
    assert len(blocks) == 1
    idx = blocks[0]
    assert idx["id"] == "ado-attachments-index"
    # mime types presentes (derivados por extensión)
    assert "image/png" in idx["content"]
    assert "application/pdf" in idx["content"]
    # URLs incluidas
    assert "abc" in idx["content"]
    assert "def" in idx["content"]
    # Tamaños humanizados
    assert "KB" in idx["content"] or "B" in idx["content"]


def test_build_blocks_inlines_text_attachments(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        attachments=[
            {"name": "log.txt", "url": "u1", "size": 50, "text_content": "ERROR foo\n"},
            {"name": "data.json", "url": "u2", "size": 80, "text_content": '{"a":1}'},
        ],
    ))
    blocks, stats = ado_context.build_ado_context_blocks(789)
    assert stats["attachments_count"] == 2
    assert stats["attachments_text_inlined"] == 2
    # 1 índice + 2 bloques con contenido
    ids = [b["id"] for b in blocks]
    assert "ado-attachments-index" in ids
    assert "ado-attachment-log.txt" in ids
    assert "ado-attachment-data.json" in ids


def test_build_blocks_respects_text_inline_cap(patch_client, monkeypatch):
    from services import ado_context
    monkeypatch.setenv("ADO_CONTEXT_ATTACH_MAX_TEXT_FILES", "1")
    patch_client(_FakeAdoClient(
        attachments=[
            {"name": "a.txt", "url": "ua", "size": 10, "text_content": "A"},
            {"name": "b.txt", "url": "ub", "size": 10, "text_content": "B"},
            {"name": "c.txt", "url": "uc", "size": 10, "text_content": "C"},
        ],
    ))
    blocks, stats = ado_context.build_ado_context_blocks(11)
    assert stats["attachments_count"] == 3
    assert stats["attachments_text_inlined"] == 1


def test_build_blocks_swallows_errors(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        comments_raises=RuntimeError("ado boom"),
        attachments_raises=RuntimeError("ado boom 2"),
    ))
    blocks, stats = ado_context.build_ado_context_blocks(99)
    assert blocks == []
    assert stats["comments_count"] == 0
    assert stats["attachments_count"] == 0
    assert any("fetch_comments_failed" in e for e in stats["errors"])
    assert any("fetch_attachments_failed" in e for e in stats["errors"])


def test_build_blocks_uses_explicit_mime_hint(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        attachments=[
            {
                "name": "weird-no-ext",
                "url": "u",
                "size": 100,
                "mime_type": "application/x-custom",
                "text_content": None,
            },
        ],
    ))
    blocks, _ = ado_context.build_ado_context_blocks(1)
    assert "application/x-custom" in blocks[0]["content"]


# ── enrich ──────────────────────────────────────────────────────────────────

def test_enrich_skips_disabled_agent(patch_client, monkeypatch):
    from services import ado_context
    monkeypatch.setenv("ADO_CONTEXT_ENRICH_AGENTS", "qa")
    patch_client(_FakeAdoClient(
        comments=[{"author": "A", "date": "d", "text": "<p>x</p>"}],
    ))

    blocks, stats = ado_context.enrich(
        ticket_id=1,
        agent_type="business",
        existing_blocks=[{"id": "x", "kind": "text"}],
        ado_id=10,
        return_stats=True,
    )
    assert stats["skipped"] is True
    assert stats["skipped_reason"] == "agent_not_in_enrich_list"
    # No alteró los bloques.
    assert len(blocks) == 1


def test_enrich_default_includes_all_agents(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        comments=[{"author": "A", "date": "d", "text": "<p>y</p>"}],
    ))
    # business no estaba en la lista vieja — ahora SÍ debe enriquecerse.
    blocks, stats = ado_context.enrich(
        ticket_id=1,
        agent_type="business",
        existing_blocks=[],
        ado_id=10,
        return_stats=True,
    )
    assert stats["skipped"] is False
    assert stats["comments_count"] == 1
    assert any(b.get("id") == "ado-comments" for b in blocks)


def test_enrich_idempotent_when_blocks_already_present(patch_client):
    from services import ado_context
    fake = _FakeAdoClient(comments=[{"author": "A", "date": "d", "text": "<p>z</p>"}])
    patch_client(fake)
    existing = [
        {"id": "ado-comments", "kind": "text", "title": "ya estaba", "content": "x"},
    ]
    blocks, stats = ado_context.enrich(
        ticket_id=1,
        agent_type="qa",
        existing_blocks=existing,
        ado_id=10,
        return_stats=True,
    )
    assert stats["skipped"] is True
    assert stats["skipped_reason"] == "already_enriched"
    # No se llamó a la API.
    assert fake.calls["fetch_comments"] == 0


def test_enrich_legacy_signature_still_returns_list(patch_client):
    """El call site existente no usa return_stats — debe seguir devolviendo lista."""
    from services import ado_context
    patch_client(_FakeAdoClient())
    out = ado_context.enrich(
        ticket_id=1,
        agent_type="developer",
        existing_blocks=[{"id": "x"}],
        ado_id=10,
    )
    assert isinstance(out, list)
    assert out[0]["id"] == "x"


def test_enrich_logs_counts(patch_client):
    from services import ado_context
    patch_client(_FakeAdoClient(
        comments=[{"author": "A", "date": "d", "text": "<p>c1</p>"}],
        attachments=[{"name": "x.png", "url": "u", "size": 10}],
    ))
    captured: list[tuple[str, str]] = []

    def log(level, msg):
        captured.append((level, msg))

    blocks, stats = ado_context.enrich(
        ticket_id=1, agent_type="qa", existing_blocks=[], ado_id=42, log=log, return_stats=True
    )
    assert stats["comments_count"] == 1
    assert stats["attachments_count"] == 1
    info_msgs = " | ".join(m for lvl, m in captured if lvl == "info")
    assert "1 comentarios" in info_msgs and "1 adjuntos" in info_msgs
