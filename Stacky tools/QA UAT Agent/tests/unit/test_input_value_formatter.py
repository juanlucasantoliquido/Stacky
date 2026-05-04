"""Unit tests for input_value_formatter.py (M3).

These tests pin the canonical output for every HTML5 input type the
playwright_test_generator may encounter, so future refactors cannot regress
the date/time/number/color formatting logic.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
os.environ.setdefault("STACKY_LLM_BACKEND", "mock")

from input_value_formatter import format_value, UNPARSEABLE_LABELS


# ── date ───────────────────────────────────────────────────────────────────────

def test_date_iso_passthrough():
    assert format_value("date", "2026-01-31") == ("2026-01-31", None)


def test_date_compact_yyyymmdd():
    """Ticket 70 P04 used '19000101' — the regression that motivated M3."""
    assert format_value("date", "19000101") == ("1900-01-01", None)


def test_date_dd_slash_mm_slash_yyyy():
    assert format_value("date", "31/01/2026") == ("2026-01-31", None)


def test_date_dd_dash_mm_dash_yyyy():
    assert format_value("date", "31-01-2026") == ("2026-01-31", None)


def test_date_unparseable_returns_label():
    val, err = format_value("date", "tomorrow")
    assert val is None
    assert err == UNPARSEABLE_LABELS["date"]


def test_date_none_value_returns_label():
    val, err = format_value("date", None)
    assert val is None
    assert err == UNPARSEABLE_LABELS["date"]


def test_date_empty_string_returns_label():
    val, err = format_value("date", "   ")
    assert val is None
    assert err == UNPARSEABLE_LABELS["date"]


# ── time ───────────────────────────────────────────────────────────────────────

def test_time_hhmm_passthrough():
    assert format_value("time", "14:30") == ("14:30", None)


def test_time_with_seconds_drops_them():
    assert format_value("time", "14:30:45") == ("14:30", None)


def test_time_compact_hhmm():
    assert format_value("time", "1430") == ("14:30", None)


def test_time_unparseable():
    val, err = format_value("time", "abc")
    assert val is None and err == UNPARSEABLE_LABELS["time"]


# ── month ──────────────────────────────────────────────────────────────────────

def test_month_iso_passthrough():
    assert format_value("month", "2026-01") == ("2026-01", None)


def test_month_mm_slash_yyyy():
    assert format_value("month", "01/2026") == ("2026-01", None)


def test_month_compact():
    assert format_value("month", "202601") == ("2026-01", None)


def test_month_unparseable():
    val, err = format_value("month", "Q1")
    assert val is None and err == UNPARSEABLE_LABELS["month"]


# ── number ─────────────────────────────────────────────────────────────────────

def test_number_integer():
    assert format_value("number", "42") == ("42", None)


def test_number_with_thousand_separator_dot():
    """1.000.000 (es-AR) → 1000000."""
    assert format_value("number", "1.000.000") == ("1000000", None)


def test_number_decimal_comma():
    """1,5 → 1.5"""
    assert format_value("number", "1,5") == ("1.5", None)


def test_number_mixed_es_locale():
    """1.234,56 → 1234.56 (Spanish locale: dot=thousand, comma=decimal)."""
    assert format_value("number", "1.234,56") == ("1234.56", None)


def test_number_mixed_en_locale():
    """1,234.56 → 1234.56 (English: comma=thousand, dot=decimal)."""
    assert format_value("number", "1,234.56") == ("1234.56", None)


def test_number_unparseable():
    val, err = format_value("number", "abc")
    assert val is None and err == UNPARSEABLE_LABELS["number"]


# ── color ──────────────────────────────────────────────────────────────────────

def test_color_hex6_with_hash():
    assert format_value("color", "#FF0000") == ("#ff0000", None)


def test_color_hex6_no_hash():
    assert format_value("color", "FF00FF") == ("#ff00ff", None)


def test_color_hex3_expands():
    assert format_value("color", "#abc") == ("#aabbcc", None)


def test_color_named():
    assert format_value("color", "red") == ("#ff0000", None)


def test_color_unparseable():
    val, err = format_value("color", "burgundy")
    assert val is None and err == UNPARSEABLE_LABELS["color"]


# ── identity types ─────────────────────────────────────────────────────────────

def test_text_identity():
    assert format_value("text", "anything goes") == ("anything goes", None)


def test_password_identity():
    assert format_value("password", "S3cr3t!") == ("S3cr3t!", None)


def test_unknown_type_identity():
    """Unknown types must passthrough (don't break new-type forward compat)."""
    assert format_value("future-type-x", "raw value") == ("raw value", None)


def test_text_none_value_returns_empty_string():
    """Identity types accept None → empty string (Playwright fill('') is valid)."""
    assert format_value("text", None) == ("", None)


def test_input_type_none_passthrough():
    """When the UI map has no input_type field (legacy), don't touch the value."""
    assert format_value(None, "01/01/2026") == ("01/01/2026", None)


# ── datetime-local & week ──────────────────────────────────────────────────────

def test_datetime_local_iso_passthrough():
    assert format_value("datetime-local", "2026-01-31T14:30") == ("2026-01-31T14:30", None)


def test_datetime_local_dd_slash_mm():
    assert format_value("datetime-local", "31/01/2026 14:30") == ("2026-01-31T14:30", None)


def test_week_passthrough():
    assert format_value("week", "2026-W05") == ("2026-W05", None)


def test_week_from_iso_date():
    """Reasonable: 2026-01-26 is Monday of ISO week 5 → 2026-W05."""
    val, err = format_value("week", "2026-01-26")
    assert err is None
    assert val.startswith("2026-W")
