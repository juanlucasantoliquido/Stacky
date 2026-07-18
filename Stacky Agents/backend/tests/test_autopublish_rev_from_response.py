"""Tests Plan 153 F4 — rev desde la respuesta del POST; el GET extra es fallback."""
from __future__ import annotations

import os
from unittest.mock import patch

# OBLIGATORIO antes de cualquier import de módulos de la app:
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


class _FakeRevClient:
    def __init__(self, rev_val: int):
        self.rev_val = rev_val
        self.get_calls = 0

    def get_work_item(self, ado_id, fields=None):
        self.get_calls += 1
        return {"fields": {"System.Rev": self.rev_val}}


def _run_autopublish(monkeypatch, published_rev, fake_client):
    from api import tickets
    from api.tickets import _PublishedEpic

    monkeypatch.setenv("STACKY_EPIC_SUMMARY_ENABLED", "off")
    monkeypatch.setenv("STACKY_ADO_EDIT_LEARNING_ENABLED", "true")

    published = _PublishedEpic(ado_id=1, title="T", url="u", rev=published_rev)
    with patch.object(tickets, "_looks_like_epic", return_value=True):
        with patch.object(tickets, "_epic_gate_enabled", return_value=False):
            with patch.object(tickets, "_publish_epic_to_ado", return_value=published):
                with patch.object(tickets, "_ado_client_for_ticket", return_value=fake_client):
                    return tickets.autopublish_epic_from_run(
                        output="<h1>Epic</h1>", brief="b", project_name="p",
                        already_published_id=None,
                    )


def test_rev_de_respuesta_evita_get(monkeypatch):
    fake = _FakeRevClient(rev_val=999)  # no deberia usarse
    result = _run_autopublish(monkeypatch, published_rev=1, fake_client=fake)
    assert result.baseline_rev == 1
    assert fake.get_calls == 0  # la respuesta ya trajo rev: cero GET extra


def test_sin_rev_en_respuesta_cae_al_get(monkeypatch):
    fake = _FakeRevClient(rev_val=7)
    result = _run_autopublish(monkeypatch, published_rev=None, fake_client=fake)
    assert result.baseline_rev == 7
    assert fake.get_calls == 1  # sin rev en la respuesta: fallback al GET (1 sola vez)


class _FakeAdoCreate:
    def create_work_item(self, work_item_type, title, description):
        return {
            "id": 1,
            "rev": 3,
            "fields": {"System.Title": title},
            "_links": {},
        }

    def work_item_url(self, ado_id):
        return f"https://ado/{ado_id}"


def test_publish_epic_helper_captura_rev():
    from api import tickets
    from api.tickets import _publish_epic_to_ado

    with patch.object(tickets, "_provider_for_ticket", return_value=None):
        with patch.object(tickets, "_ado_client_for_ticket", return_value=_FakeAdoCreate()):
            with patch.object(tickets, "_persist_epic_ticket"):
                with patch.object(tickets, "_epic_brief_save"):
                    published = _publish_epic_to_ado(
                        description_html="<h2>T</h2>", brief="b", project_name="p", title="T",
                    )

    assert published.rev == 3  # el helper extrae el rev de la respuesta de creación
