"""tests/test_plan108_prompt_hardening.py — Plan 108 F2: prohibición explícita
de tools locales en el contrato de la consola remota (build_console_prompt)."""
from __future__ import annotations

from services.remote_console_prompt import build_console_prompt


class TestPromptHardening:
    """F2 — el agente CLI no puede "interpretar" que sus tools locales sirven
    para responder sobre el servidor."""

    def test_prompt_prohibits_local_tools(self):
        prompt = build_console_prompt("srv1", "http://localhost:8000", "hola", 123, write_enabled=False)
        assert "PROHIBIDO usar tus herramientas locales" in prompt
        assert "Esta máquina NO es el servidor" in prompt

    def test_prompt_keeps_exec_contract(self):
        """No-regresión Plan 105 F3: sigue el endpoint /exec y el alias interpolado."""
        prompt = build_console_prompt("srv1", "http://localhost:8000", "hola", 123, write_enabled=False)
        assert "/api/devops/console/exec" in prompt
        assert "srv1" in prompt

    def test_prompt_write_mode_text_unchanged(self):
        prompt_write = build_console_prompt("srv1", "http://localhost:8000", "x", 1, write_enabled=True)
        assert "LECTURA+ESCRITURA" in prompt_write
        prompt_read = build_console_prompt("srv1", "http://localhost:8000", "x", 1, write_enabled=False)
        assert "SOLO LECTURA" in prompt_read
