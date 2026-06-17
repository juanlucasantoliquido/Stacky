"""TDD — I0.2: estimate_complexity en harness/complexity.py.

Criterios de aceptación:
- clasificación por tamaño (título+descripción corta → S, larga → L/XL)
- palabras-señal elevan la complejidad
- presencia de muchos bloques → L/XL
- determinismo: misma entrada → mismo resultado
- flag OFF → devuelve None (no-op en el caller)
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blocks(n: int, content_len: int = 50) -> list[dict]:
    return [{"kind": "auto", "title": f"Bloque {i}", "content": "x" * content_len} for i in range(n)]


# ---------------------------------------------------------------------------
# Tests básicos de clasificación
# ---------------------------------------------------------------------------

class TestEstimateComplexityBasic:
    def test_empty_input_returns_S(self):
        from harness.complexity import estimate_complexity
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Fix bug",
            ticket_description="",
            blocks=[],
        )
        assert result == "S"

    def test_short_title_no_desc_S(self):
        from harness.complexity import estimate_complexity
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Fix typo",
            ticket_description="Corregir el texto del botón.",
            blocks=[],
        )
        assert result == "S"

    def test_long_description_raises_to_M(self):
        from harness.complexity import estimate_complexity
        # ~300 chars de descripción
        desc = "Descripción de la tarea. " * 15
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Tarea normal",
            ticket_description=desc,
            blocks=[],
        )
        assert result in ("M", "L", "XL")

    def test_many_bullets_raise_complexity(self):
        from harness.complexity import estimate_complexity
        # 8 líneas con guión = criterios de aceptación
        bullets = "\n".join(f"- criterio {i}" for i in range(8))
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Feature",
            ticket_description=bullets,
            blocks=[],
        )
        assert result in ("M", "L", "XL")

    def test_many_blocks_raise_complexity(self):
        from harness.complexity import estimate_complexity
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Tarea",
            ticket_description="Descripción normal.",
            blocks=_blocks(12),
        )
        assert result in ("L", "XL")

    def test_very_large_blocks_XL(self):
        from harness.complexity import estimate_complexity
        # Bloques grandes = muchos tokens
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Tarea grande",
            ticket_description="",
            blocks=_blocks(5, content_len=4000),
        )
        assert result in ("L", "XL")


# ---------------------------------------------------------------------------
# Palabras-señal
# ---------------------------------------------------------------------------

class TestSignalWords:
    @pytest.mark.parametrize("word", ["migración", "refactor", "integración", "migration", "refactoring"])
    def test_signal_word_upgrades_complexity(self, word):
        from harness.complexity import estimate_complexity
        result = estimate_complexity(
            agent_type="developer",
            ticket_title=f"Tarea de {word} del módulo",
            ticket_description="Descripción breve.",
            blocks=[],
        )
        # Debe ser al menos M (no S)
        assert result in ("M", "L", "XL"), f"Esperaba >=M para palabra '{word}', got {result}"

    def test_signal_word_in_description(self):
        from harness.complexity import estimate_complexity
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Tarea",
            ticket_description="Se requiere una refactorización completa del módulo.",
            blocks=[],
        )
        assert result in ("M", "L", "XL")


# ---------------------------------------------------------------------------
# Determinismo
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_result(self):
        from harness.complexity import estimate_complexity
        kwargs = dict(
            agent_type="developer",
            ticket_title="Tarea con migración de base de datos",
            ticket_description="Se debe integrar el nuevo módulo con el sistema existente.",
            blocks=_blocks(3),
        )
        results = {estimate_complexity(**kwargs) for _ in range(5)}
        assert len(results) == 1, f"No determinista: {results}"


# ---------------------------------------------------------------------------
# Escala válida
# ---------------------------------------------------------------------------

class TestValidScale:
    @pytest.mark.parametrize("size", ["S", "M", "L", "XL"])
    def test_result_always_valid(self, size):
        from harness.complexity import estimate_complexity
        # Solo verificamos que el contrato de retorno es válido
        result = estimate_complexity(
            agent_type="developer",
            ticket_title="Test",
            ticket_description="desc",
            blocks=[],
        )
        assert result in ("S", "M", "L", "XL")
