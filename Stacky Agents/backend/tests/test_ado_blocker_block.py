"""Plan 133 F3 — Bloque 'ado-blocker' server-side dentro de build_ado_context_blocks."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class _FakeAdoClient:
    def __init__(self, comments=None, attachments=None):
        self._comments = comments or []
        self._attachments = attachments or []

    def fetch_comments(self, ado_id, top=30):
        return list(self._comments)

    def fetch_attachments(self, ado_id, max_text_bytes=65_536):
        return list(self._attachments)


def _build(monkeypatch, comments, flag_on=True):
    from config import config
    from services import ado_context, project_context

    monkeypatch.setattr(config, "STACKY_ADO_BLOCKER_BLOCK_ENABLED", flag_on)
    monkeypatch.setattr(
        project_context, "build_ado_client", lambda **kwargs: _FakeAdoClient(comments)
    )
    return ado_context.build_ado_context_blocks(331)


def test_sin_marcador_identidad(monkeypatch):
    blocks, stats = _build(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-13", "text": "avance normal"},
    ])
    ids = [b.get("id") for b in blocks]
    assert "ado-blocker" not in ids
    assert ids == ["ado-comments"]


def test_con_marcador_agrega_bloque(monkeypatch):
    blocks, stats = _build(monkeypatch, comments=[
        {"author": "Dev", "date": "2026-07-13", "text": "🚫 BLOQUEANTE TÉCNICO: falta X"},
    ])
    ids = [b.get("id") for b in blocks]
    assert ids == ["ado-blocker", "ado-comments"]
    blocker = blocks[0]
    assert "Dev" in blocker["content"]
    assert "falta X" in blocker["content"]


def test_flag_off_identidad_aun_con_marcador(monkeypatch):
    blocks, stats = _build(
        monkeypatch,
        comments=[{"author": "Dev", "date": "2026-07-13", "text": "🚫 BLOQUEANTE TÉCNICO: x"}],
        flag_on=False,
    )
    ids = [b.get("id") for b in blocks]
    assert "ado-blocker" not in ids
    assert ids == ["ado-comments"]


def test_toma_el_mas_reciente(monkeypatch):
    blocks, stats = _build(monkeypatch, comments=[
        {"author": "Viejo", "date": "2026-07-01", "text": "🚫 BLOQUEANTE TÉCNICO: viejo"},
        {"author": "Nuevo", "date": "2026-07-13", "text": "🚫 BLOQUEANTE TÉCNICO: nuevo"},
    ])
    blocker = blocks[0]
    assert blocker["id"] == "ado-blocker"
    assert "Nuevo" in blocker["content"]
    assert "nuevo" in blocker["content"]
    assert "Viejo" not in blocker["content"]
