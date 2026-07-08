"""tests/test_plan105_console_prompt.py — Plan 105 F3.

Tests del prompt de consola (build_console_prompt).
"""
from __future__ import annotations

import pytest

from services.remote_console_prompt import build_console_prompt


class TestF3ConsolePrompt:
    """F3 — Tests del prompt builder."""

    def test_f3_prompt_contains_alias_url_and_message(self):
        """Prompt contiene alias, base_url y message."""
        prompt = build_console_prompt("srv1", "http://localhost:8000", "list processes", 123, write_enabled=False)
        assert "srv1" in prompt
        assert "http://localhost:8000" in prompt
        assert "list processes" in prompt

    def test_f3_prompt_read_only_wording(self):
        """Con write_enabled=False incluye 'SOLO LECTURA' y NO 'ESCRITURA'."""
        prompt = build_console_prompt("srv1", "http://localhost:8000", "test", 123, write_enabled=False)
        assert "SOLO LECTURA" in prompt
        assert "ESCRITURA (el operador lo habilitó)" not in prompt

    def test_f3_prompt_write_wording(self):
        """Con write_enabled=True incluye 'ESCRITURA'."""
        prompt = build_console_prompt("srv1", "http://localhost:8000", "test", 123, write_enabled=True)
        assert "LECTURA+ESCRITURA" in prompt
        assert "el operador lo habilitó" in prompt

    def test_f3_prompt_no_placeholders_left(self):
        """No quedan {{CONVERSATION_ID}} ni {{server_alias}} sin interpolar."""
        prompt = build_console_prompt("srv1", "http://localhost:8000", "test", 456, write_enabled=False)
        assert "{{CONVERSATION_ID}}" not in prompt
        assert "{{server_alias}}" not in prompt
        # El conversation_id aparece en el JSON del curl (con escape backslash)
        assert "conversation_id" in prompt and "456" in prompt
        assert "srv1" in prompt

    def test_f3_prompt_never_mentions_password(self):
        """'password' aparece solo en 'NUNCA pidas ni uses passwords' (1 vez)."""
        prompt = build_console_prompt("srv1", "http://localhost:8000", "test", 123, write_enabled=False)
        count = prompt.count("password")
        assert count == 1, f"Se esperaba 1 mención de 'password', hay {count}"
        assert "SR_PASS" not in prompt
