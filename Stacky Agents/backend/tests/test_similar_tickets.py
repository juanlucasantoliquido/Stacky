"""Tests del servicio similar_tickets (Sprint S2).

Cubre:
  - extract_keywords: tokenización, filtrado de stopwords + cortos.
  - _build_wiql: estructura de la query + escape de comillas.
  - find_similar_tickets con AdoClient mockeado: happy path + edge cases.
  - inject_into_blocks: idempotencia + propagación del bloque.
  - Defensive: AdoClient ausente / falla → retorna [] sin propagar.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")


# ── extract_keywords ─────────────────────────────────────────────────────────


def test_extract_keywords_filters_stopwords_and_short():
    from services.similar_tickets import extract_keywords

    kws = extract_keywords("El RF-013 - Selección de Medio de Contacto en Gestión")
    # "El", "de", "en" stopwords; "RF" en stopwords; "-" filtrado por regex
    assert "Selección" in kws
    assert "Medio" in kws
    assert "Contacto" in kws
    assert "Gestión" in kws
    assert "el" not in [k.lower() for k in kws]
    assert "de" not in [k.lower() for k in kws]
    assert "rf" not in [k.lower() for k in kws]


def test_extract_keywords_dedupes_case_insensitive():
    from services.similar_tickets import extract_keywords

    kws = extract_keywords("Cliente cliente CLIENTE")
    # Solo una vez (primera ocurrencia gana)
    lowercase = [k.lower() for k in kws]
    assert lowercase.count("cliente") == 1


def test_extract_keywords_sorts_by_length_desc():
    from services.similar_tickets import extract_keywords

    kws = extract_keywords("Ordenamiento telefonos efectividad contacto")
    # Más larga primero
    assert len(kws[0]) >= len(kws[-1])


def test_extract_keywords_empty_title():
    from services.similar_tickets import extract_keywords

    assert extract_keywords("") == []
    assert extract_keywords(None) == []  # type: ignore[arg-type]


# ── _build_wiql ──────────────────────────────────────────────────────────────


def test_build_wiql_includes_keywords_and_exclude():
    from services.similar_tickets import _build_wiql

    wiql = _build_wiql(
        project="Strategist_Pacifico",
        keywords=["Cliente", "Domicilios"],
        exclude_id=99,
        max_results=10,
    )
    assert "[System.TeamProject] = 'Strategist_Pacifico'" in wiql
    assert "CONTAINS 'Cliente'" in wiql
    assert "CONTAINS 'Domicilios'" in wiql
    assert "[System.Id] <> 99" in wiql
    assert "ORDER BY [System.ChangedDate] DESC" in wiql


def test_build_wiql_escapes_single_quotes():
    from services.similar_tickets import _build_wiql

    wiql = _build_wiql(
        project="Proj's",
        keywords=["O'Brien"],
        exclude_id=None,
        max_results=10,
    )
    # WIQL escapa duplicando comilla simple
    assert "Proj''s" in wiql
    assert "O''Brien" in wiql


# ── find_similar_tickets ─────────────────────────────────────────────────────


class _FakeAdoClient:
    """Stub que simula AdoClient.fetch_open_work_items + work_item_url."""

    def __init__(self, results: list[dict]):
        self._results = results
        self.last_wiql: str | None = None

    def fetch_open_work_items(self, wiql=None):
        self.last_wiql = wiql
        return self._results

    def work_item_url(self, ado_id):
        return f"https://dev.azure.com/x/y/_workitems/edit/{ado_id}"


def _stub_ado_client(monkeypatch, fake):
    """Reemplaza la clase AdoClient en el módulo services.ado_client."""
    import services.ado_client as _ado_client
    monkeypatch.setattr(_ado_client, "AdoClient", lambda *a, **kw: fake)


def test_find_similar_tickets_returns_normalized_results(monkeypatch):
    from services.similar_tickets import find_similar_tickets

    fake = _FakeAdoClient([
        {
            "id": 148,
            "fields": {
                "System.Title": "RF-013 - Selección de Medio de Contacto",
                "System.State": "Done",
                "System.WorkItemType": "Task",
            },
        },
        {
            "id": 145,
            "fields": {
                "System.Title": "RF-010 - Ordenamiento de obligaciones",
                "System.State": "Doing",
                "System.WorkItemType": "Task",
            },
        },
    ])
    _stub_ado_client(monkeypatch, fake)

    similars = find_similar_tickets(
        current_ado_id=149,
        current_title="Ordenamiento de Telefonos por Efectividad de Contacto",
        project="Strategist_Pacifico",
    )

    assert len(similars) == 2
    assert similars[0].ado_id == 148
    assert similars[0].state == "Done"
    assert similars[0].work_item_type == "Task"
    assert "148" in similars[0].url
    # La WIQL debe excluir 149
    assert "[System.Id] <> 149" in (fake.last_wiql or "")


def test_find_similar_tickets_excludes_self(monkeypatch):
    """Aunque AdoClient devuelva el current_ado_id, debe filtrarlo."""
    from services.similar_tickets import find_similar_tickets

    fake = _FakeAdoClient([
        {"id": 149, "fields": {"System.Title": "self", "System.State": "x", "System.WorkItemType": "Task"}},
        {"id": 148, "fields": {"System.Title": "other", "System.State": "y", "System.WorkItemType": "Task"}},
    ])
    _stub_ado_client(monkeypatch, fake)

    similars = find_similar_tickets(
        current_ado_id=149,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    ids = [s.ado_id for s in similars]
    assert 149 not in ids
    assert 148 in ids


def test_find_similar_tickets_empty_title_returns_empty(monkeypatch):
    from services.similar_tickets import find_similar_tickets

    fake = _FakeAdoClient([])
    _stub_ado_client(monkeypatch, fake)

    # Sin keywords útiles
    assert find_similar_tickets(current_ado_id=1, current_title="", project="P") == []
    assert find_similar_tickets(current_ado_id=1, current_title="el la de", project="P") == []


def test_find_similar_tickets_swallows_ado_errors(monkeypatch):
    """Si AdoClient.fetch_open_work_items raise, retornamos [] sin propagar."""
    from services.similar_tickets import find_similar_tickets

    class _BrokenClient:
        def fetch_open_work_items(self, wiql=None):
            raise RuntimeError("ADO down")
        def work_item_url(self, ado_id):
            return ""

    _stub_ado_client(monkeypatch, _BrokenClient())

    similars = find_similar_tickets(
        current_ado_id=1,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    assert similars == []


def test_find_similar_tickets_swallows_constructor_errors(monkeypatch):
    """Si AdoClient() raise (e.g. config missing), retornamos [] sin propagar."""
    from services.similar_tickets import find_similar_tickets
    import services.ado_client as _ado_client

    def _broken_init(*a, **kw):
        raise RuntimeError("ADO config missing")

    monkeypatch.setattr(_ado_client, "AdoClient", _broken_init)

    similars = find_similar_tickets(
        current_ado_id=1,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    assert similars == []


# ── build_similar_tickets_block + inject_into_blocks ─────────────────────────


def test_build_block_returns_none_when_no_matches(monkeypatch):
    from services.similar_tickets import build_similar_tickets_block

    fake = _FakeAdoClient([])
    _stub_ado_client(monkeypatch, fake)

    block = build_similar_tickets_block(
        current_ado_id=149,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    assert block is None


def test_build_block_includes_tickets_and_metadata(monkeypatch):
    from services.similar_tickets import build_similar_tickets_block, SIMILAR_BLOCK_ID

    fake = _FakeAdoClient([
        {"id": 148, "fields": {"System.Title": "Selección de Medio", "System.State": "Done", "System.WorkItemType": "Task"}},
    ])
    _stub_ado_client(monkeypatch, fake)

    block = build_similar_tickets_block(
        current_ado_id=149,
        current_title="Ordenamiento telefonos efectividad contacto",
        project="P",
    )
    assert block is not None
    assert block["id"] == SIMILAR_BLOCK_ID
    assert "ADO-148" in block["content"]
    assert block["metadata"]["count"] == 1
    assert block["metadata"]["tickets"][0]["ado_id"] == 148


def test_inject_is_idempotent(monkeypatch):
    from services.similar_tickets import SIMILAR_BLOCK_ID, inject_into_blocks

    fake = _FakeAdoClient([
        {"id": 148, "fields": {"System.Title": "x", "System.State": "Done", "System.WorkItemType": "Task"}},
    ])
    _stub_ado_client(monkeypatch, fake)

    blocks, info1 = inject_into_blocks(
        [],
        current_ado_id=149,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    assert info1 and info1.get("injected") is True
    assert any(b.get("id") == SIMILAR_BLOCK_ID for b in blocks)

    blocks2, info2 = inject_into_blocks(
        blocks,  # ya contiene el bloque
        current_ado_id=149,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    assert info2 == {"skipped": "already_present"}
    assert len(blocks2) == len(blocks)


def test_inject_returns_unchanged_when_no_matches(monkeypatch):
    from services.similar_tickets import inject_into_blocks

    fake = _FakeAdoClient([])
    _stub_ado_client(monkeypatch, fake)

    initial = [{"id": "operator-note", "kind": "editable", "content": "x"}]
    blocks, info = inject_into_blocks(
        initial,
        current_ado_id=149,
        current_title="Ordenamiento telefonos",
        project="P",
    )
    assert info is None
    assert blocks == initial
