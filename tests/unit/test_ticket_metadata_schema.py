"""Tests unitarios de ticket_metadata_schema (Pydantic)."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestTicketColor:
    @pytest.mark.parametrize("ok_hex", [
        "#000000", "#ffffff", "#abcdef", "#123456", "#AABBCC", "  #abcdef  ",
    ])
    def test_color_valido(self, ok_hex):
        from ticket_metadata_schema import TicketColor
        c = TicketColor(hex=ok_hex)
        assert c.hex == ok_hex.strip().lower()

    @pytest.mark.parametrize("bad_hex", [
        "red", "#abc", "#12345", "#1234567", "rgb(0,0,0)", "", "#gggggg", "abcdef",
    ])
    def test_color_invalido(self, bad_hex):
        from ticket_metadata_schema import TicketColor
        with pytest.raises(Exception):
            TicketColor(hex=bad_hex)

    def test_color_no_string_rechazado(self):
        from ticket_metadata_schema import TicketColor
        with pytest.raises(Exception):
            TicketColor(hex=123456)   # type: ignore[arg-type]


class TestTicketUserTags:
    def test_tags_lowercase_trim_dedup_preserva_orden(self):
        from ticket_metadata_schema import TicketUserTags
        t = TicketUserTags(tags=["BUG", " Frontend ", "bug", "urgente", "Frontend"])
        assert t.tags == ["bug", "frontend", "urgente"]

    def test_tags_aceptan_tildes_ñ_y_guiones(self):
        from ticket_metadata_schema import TicketUserTags
        t = TicketUserTags(tags=["año-crítico", "niño", "módulo_x", "crítico-2026"])
        assert set(t.tags) == {"año-crítico", "niño", "módulo_x", "crítico-2026"}

    @pytest.mark.parametrize("bad_tag", [
        "tag con espacio", "tag!", "tag@foo", "tag/bar", "tag.dot", "tag#hash",
    ])
    def test_tag_invalido_rechazado(self, bad_tag):
        from ticket_metadata_schema import TicketUserTags
        with pytest.raises(Exception):
            TicketUserTags(tags=[bad_tag])

    def test_tags_vacios_y_whitespace_se_descartan(self):
        from ticket_metadata_schema import TicketUserTags
        t = TicketUserTags(tags=["", "   ", "bug"])
        assert t.tags == ["bug"]

    def test_tag_excede_32_chars(self):
        from ticket_metadata_schema import TicketUserTags
        with pytest.raises(Exception):
            TicketUserTags(tags=["x" * 33])

    def test_limite_20_tags_por_ticket(self):
        from ticket_metadata_schema import TicketUserTags
        TicketUserTags(tags=[f"tag{i}" for i in range(20)])   # OK
        with pytest.raises(Exception):
            TicketUserTags(tags=[f"tag{i}" for i in range(21)])

    def test_lista_vacia_ok(self):
        from ticket_metadata_schema import TicketUserTags
        assert TicketUserTags(tags=[]).tags == []

    def test_none_equivale_a_vacio(self):
        from ticket_metadata_schema import TicketUserTags
        assert TicketUserTags(tags=None).tags == []

    def test_non_list_rechazado(self):
        from ticket_metadata_schema import TicketUserTags
        with pytest.raises(Exception):
            TicketUserTags(tags="bug,frontend")   # type: ignore[arg-type]


class TestTicketMetadata:
    def test_minimal_ticket_solo_id(self):
        from ticket_metadata_schema import TicketMetadata
        m = TicketMetadata(ticket_id="27698")
        assert m.ticket_id == "27698"
        assert m.color is None
        assert m.user_tags.tags == []
        assert m.updated_at   # autogenerado

    def test_to_dict_roundtrip(self):
        from ticket_metadata_schema import TicketMetadata, TicketColor, TicketUserTags
        m = TicketMetadata(
            ticket_id="27698",
            color=TicketColor(hex="#abcdef"),
            user_tags=TicketUserTags(tags=["bug", "frontend"]),
        )
        d = m.to_dict()
        assert d["ticket_id"] == "27698"
        assert d["color"]["hex"] == "#abcdef"
        assert d["user_tags"]["tags"] == ["bug", "frontend"]


class TestTicketMetadataStoreModel:
    def test_default_vacio(self):
        from ticket_metadata_schema import TicketMetadataStore
        s = TicketMetadataStore()
        assert s.version == 1
        assert s.tickets == {}

    def test_carga_desde_dict(self):
        from ticket_metadata_schema import TicketMetadataStore
        s = TicketMetadataStore(**{
            "version": 1,
            "tickets": {
                "27698": {"ticket_id": "27698",
                          "color": {"hex": "#abcdef"},
                          "user_tags": {"tags": ["bug"]}}
            },
        })
        assert "27698" in s.tickets
        assert s.tickets["27698"].color.hex == "#abcdef"
