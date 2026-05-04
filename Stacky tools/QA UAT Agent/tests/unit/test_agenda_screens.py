"""Unit tests for agenda_screens.py — Fase 1 Agenda-expert refactor.

Validates the single source of truth for the supported-screen catalogue.
The four MVP screens are fixed by SPEC; if a future screen is added these
tests must be updated alongside the catalogue.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


# ── SUPPORTED_SCREENS contents ────────────────────────────────────────────────


def test_supported_screens_contains_exactly_four_canonical_screens():
    """The MVP scope is fixed at 4 screens. Adding one is a deliberate change
    that must propagate to every consumer."""
    from agenda_screens import SUPPORTED_SCREENS

    assert SUPPORTED_SCREENS == frozenset({
        "FrmAgenda.aspx",
        "FrmDetalleLote.aspx",
        "FrmGestion.aspx",
        "Login.aspx",
    })


def test_supported_screens_is_immutable():
    """frozenset prevents accidental mutation by downstream code."""
    from agenda_screens import SUPPORTED_SCREENS

    assert isinstance(SUPPORTED_SCREENS, frozenset)


# ── is_supported() ────────────────────────────────────────────────────────────


def test_is_supported_canonical_match():
    from agenda_screens import is_supported

    assert is_supported("FrmAgenda.aspx") is True
    assert is_supported("Login.aspx") is True


def test_is_supported_case_insensitive():
    """LLM output and CLI input may use any casing; the catalogue is
    case-insensitive on lookup."""
    from agenda_screens import is_supported

    assert is_supported("frmagenda.aspx") is True
    assert is_supported("FRMAGENDA.ASPX") is True
    assert is_supported("FrMaGeNdA.AsPx") is True


def test_is_supported_rejects_unknown():
    from agenda_screens import is_supported

    assert is_supported("FrmUnknown.aspx") is False
    assert is_supported("FrmAgenda") is False  # missing extension
    assert is_supported("") is False


def test_is_supported_handles_non_string_inputs():
    """Robustness against malformed LLM output — never raise."""
    from agenda_screens import is_supported

    assert is_supported(None) is False
    assert is_supported(123) is False
    assert is_supported(["FrmAgenda.aspx"]) is False


# ── extract_from_text() ───────────────────────────────────────────────────────


def test_extract_from_text_finds_single_mention():
    from agenda_screens import extract_from_text

    text = "Pantalla FrmAgenda.aspx — RF-003 búsqueda con filtros"
    assert extract_from_text(text) == ["FrmAgenda.aspx"]


def test_extract_from_text_finds_multiple_mentions():
    from agenda_screens import extract_from_text

    text = "Test sobre FrmAgenda.aspx y luego navegar a FrmDetalleLote.aspx"
    found = extract_from_text(text)
    assert "FrmAgenda.aspx" in found
    assert "FrmDetalleLote.aspx" in found
    assert len(found) == 2


def test_extract_from_text_case_insensitive():
    from agenda_screens import extract_from_text

    text = "Login en FRMAGENDA.ASPX y validar login.aspx funciona"
    found = extract_from_text(text)
    assert "FrmAgenda.aspx" in found
    assert "Login.aspx" in found


def test_extract_from_text_returns_canonical_capitalisation():
    """Even when the source text uses lowercase, output preserves the
    canonical case — that's what URL building needs."""
    from agenda_screens import extract_from_text

    found = extract_from_text("ver pantalla frmagenda.aspx")
    assert found == ["FrmAgenda.aspx"]


def test_extract_from_text_deterministic_order():
    """Two calls with the same input must return the same ordered list so
    that pipeline UI-map runs are reproducible."""
    from agenda_screens import extract_from_text

    text = "FrmGestion.aspx, FrmAgenda.aspx, FrmDetalleLote.aspx"
    first = extract_from_text(text)
    second = extract_from_text(text)
    assert first == second
    assert first == sorted(first)


def test_extract_from_text_empty_inputs_return_empty_list():
    from agenda_screens import extract_from_text

    assert extract_from_text("") == []
    assert extract_from_text(None) == []
    assert extract_from_text(12345) == []


def test_extract_from_text_no_supported_screen_mentioned():
    from agenda_screens import extract_from_text

    text = "Test plan without any specific screen reference"
    assert extract_from_text(text) == []


# ── normalize() ──────────────────────────────────────────────────────────────


def test_normalize_returns_canonical_form():
    from agenda_screens import normalize

    assert normalize("frmagenda.aspx") == "FrmAgenda.aspx"
    assert normalize("FRMAGENDA.ASPX") == "FrmAgenda.aspx"
    assert normalize("FrmAgenda.aspx") == "FrmAgenda.aspx"


def test_normalize_returns_none_for_unsupported():
    from agenda_screens import normalize

    assert normalize("FrmUnknown.aspx") is None
    assert normalize("") is None
    assert normalize(None) is None
