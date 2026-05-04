"""Unit tests for agenda_glossary.py — Fase 1 Agenda-expert refactor.

Validates loader, per-screen view builder, and prompt-block formatter. All
tests use the bundled `data/agenda_glossary.json` shipped with the tool;
custom paths exercise the cache-miss / corrupt-file fallbacks.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


@pytest.fixture(autouse=True)
def _reset_glossary_cache():
    """Each test starts with a clean cache so that `path` overrides don't
    bleed between tests."""
    import agenda_glossary

    agenda_glossary.reset_cache()
    yield
    agenda_glossary.reset_cache()


# ── load_glossary() ──────────────────────────────────────────────────────────


def test_load_glossary_returns_dict_with_expected_keys():
    from agenda_glossary import load_glossary

    data = load_glossary()
    assert isinstance(data, dict)
    assert data.get("schema_version") == "glossary/1.0"
    assert "screens" in data
    assert "domain_terms" in data


def test_load_glossary_contains_all_supported_screens():
    """The glossary MUST cover every screen in the catalogue, otherwise
    `glossary_for_screen` returns empty results in production."""
    from agenda_glossary import load_glossary
    from agenda_screens import SUPPORTED_SCREENS

    data = load_glossary()
    screens = data.get("screens") or {}
    for screen in SUPPORTED_SCREENS:
        assert screen in screens, f"Glossary missing entry for {screen}"


def test_load_glossary_caches(tmp_path):
    """Two calls with the same path return the same object — cache works."""
    from agenda_glossary import load_glossary

    first = load_glossary()
    second = load_glossary()
    assert first is second


def test_load_glossary_missing_file_returns_empty_skeleton(tmp_path):
    """A missing glossary file must NOT raise — the pipeline survives."""
    from agenda_glossary import load_glossary

    missing = tmp_path / "does_not_exist.json"
    data = load_glossary(missing)
    assert data["screens"] == {}
    assert data["domain_terms"] == []


def test_load_glossary_corrupt_file_returns_empty_skeleton(tmp_path):
    from agenda_glossary import load_glossary

    bad = tmp_path / "bad.json"
    bad.write_text("{ this is not valid json", encoding="utf-8")

    data = load_glossary(bad)
    assert data["screens"] == {}
    assert data["domain_terms"] == []


# ── glossary_for_screen() ────────────────────────────────────────────────────


def test_glossary_for_screen_frmagenda_includes_legacy_filter_keywords():
    """The merged keyword set MUST cover every token previously hardcoded in
    `_postprocess_compiled_spec` so the post-processor behaviour is preserved
    after the refactor.
    """
    from agenda_glossary import glossary_for_screen

    view = glossary_for_screen("FrmAgenda.aspx")
    keywords = set(view["filter_keywords"])
    legacy = {
        "filtro", "buscar", "búsqueda", "debito", "débito",
        "corredor", "nombre de cliente", "ruc", "campos",
    }
    missing = legacy - keywords
    assert not missing, f"Glossary missing legacy keywords: {missing}"


def test_glossary_for_screen_frmagenda_returns_filter_action_button():
    from agenda_glossary import glossary_for_screen

    view = glossary_for_screen("FrmAgenda.aspx")
    assert view["filter_action_button"] == "link_c_btnok"


def test_glossary_for_screen_frmagenda_returns_misroute_map():
    from agenda_glossary import glossary_for_screen

    view = glossary_for_screen("FrmAgenda.aspx")
    assert view["common_misroutes"].get("link_btnnext") == "link_c_btnok"


def test_glossary_for_screen_frmagenda_returns_filter_input_aliases():
    from agenda_glossary import glossary_for_screen

    view = glossary_for_screen("FrmAgenda.aspx")
    aliases = set(view["filter_input_aliases"])
    expected = {
        "select_debito_auto", "input_corredor",
        "input_nombre_cliente", "input_ruc",
    }
    assert expected.issubset(aliases), (
        f"Filter aliases missing required entries; got {aliases}"
    )


def test_glossary_for_screen_unknown_returns_empty_view():
    """Unknown screens must yield a benign empty view, not raise."""
    from agenda_glossary import glossary_for_screen

    view = glossary_for_screen("FrmDoesNotExist.aspx")
    assert view["filter_keywords"] == []
    assert view["filter_input_aliases"] == []
    assert view["filter_action_button"] is None
    assert view["common_misroutes"] == {}
    assert view["domain_terms"] == []


def test_glossary_for_screen_filters_domain_terms_by_screen():
    """Domain terms tagged for FrmGestion only must NOT appear under
    FrmAgenda's view."""
    from agenda_glossary import glossary_for_screen

    agenda = glossary_for_screen("FrmAgenda.aspx")
    detalle = glossary_for_screen("FrmDetalleLote.aspx")

    agenda_terms = {t["term"] for t in agenda["domain_terms"]}
    detalle_terms = {t["term"] for t in detalle["domain_terms"]}

    # 'corredor' is Agenda-only per the glossary
    assert "corredor" in agenda_terms
    assert "corredor" not in detalle_terms


def test_glossary_for_screen_keywords_are_lowercase_and_sorted():
    """The merged list is normalised so the post-processor can compare
    against `desc.lower()` directly."""
    from agenda_glossary import glossary_for_screen

    view = glossary_for_screen("FrmAgenda.aspx")
    kws = view["filter_keywords"]
    assert kws == sorted(kws)
    for kw in kws:
        assert kw == kw.lower(), f"Keyword {kw!r} not lowercase"


# ── domain_terms_for_prompt() ────────────────────────────────────────────────


def test_domain_terms_for_prompt_returns_text_block():
    from agenda_glossary import domain_terms_for_prompt

    text = domain_terms_for_prompt(screen="FrmAgenda.aspx")
    assert isinstance(text, str)
    assert "DOMAIN GLOSSARY" in text
    # Spot-check that key terms make it through
    assert "lote" in text.lower()
    assert "ruc" in text.lower()


def test_domain_terms_for_prompt_respects_char_budget():
    from agenda_glossary import domain_terms_for_prompt

    text = domain_terms_for_prompt(screen=None, char_budget=200)
    assert len(text) <= 250  # 200 budget + small slack for truncation marker


def test_domain_terms_for_prompt_unknown_screen_returns_empty():
    from agenda_glossary import domain_terms_for_prompt

    text = domain_terms_for_prompt(screen="FrmUnknown.aspx")
    assert text == ""


def test_domain_terms_for_prompt_filters_by_screen():
    """Terms whose `applies_to_screens` does NOT include the requested
    screen must be excluded."""
    from agenda_glossary import domain_terms_for_prompt

    detalle = domain_terms_for_prompt(screen="FrmDetalleLote.aspx")
    agenda = domain_terms_for_prompt(screen="FrmAgenda.aspx")

    assert "corredor" in agenda.lower()
    assert "corredor" not in detalle.lower()


def test_domain_terms_for_prompt_no_glossary_returns_empty(tmp_path):
    from agenda_glossary import domain_terms_for_prompt

    missing = tmp_path / "missing.json"
    text = domain_terms_for_prompt(screen="FrmAgenda.aspx", path=missing)
    assert text == ""


def test_glossary_screens_match_supported_screens():
    """Cross-validation between the two Fase-1 modules: every screen the
    catalogue claims to support MUST have a glossary entry."""
    from agenda_screens import SUPPORTED_SCREENS
    from agenda_glossary import load_glossary

    data = load_glossary()
    documented = set((data.get("screens") or {}).keys())
    assert SUPPORTED_SCREENS.issubset(documented), (
        f"Screens missing from glossary: {SUPPORTED_SCREENS - documented}"
    )
