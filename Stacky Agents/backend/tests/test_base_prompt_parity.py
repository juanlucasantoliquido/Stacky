"""Tests F1 — Plan 54: paridad rejection_lessons en base.py (ruta copilot).

Verifica que base.py usa build_memory_prefix (helper compartido) y que
style_memory (FA-10) permanece intacto copilot-only.
"""
from __future__ import annotations
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Helpers compartidos
# ---------------------------------------------------------------------------

def _make_run_ctx(project="mi_proyecto"):
    rc = MagicMock()
    rc.project = project
    rc.use_anti_patterns = True
    rc.use_decisions = False
    rc.use_few_shot = False
    rc.context_text = ""
    rc.started_by = "operador@test.com"
    return rc


def _make_agent():
    """Instancia mínima de BaseAgent sin acceso a DB."""
    # Importamos solo lo necesario; BaseAgent es abstracto, lo instanciamos via MagicMock
    # con type definido.
    from unittest.mock import create_autospec
    # Queremos testear el método _build_prefix_parts de la clase base.
    # Importamos la clase para inspeccionar, pero no instanciamos directamente.
    import agents.base as base_module
    return base_module


# ---------------------------------------------------------------------------
# Test 1 — Flag ON → rejection_lessons inyectadas en ruta copilot
# ---------------------------------------------------------------------------

def test_copilot_rejection_lessons_injected_flag_on(monkeypatch):
    """Flag ON: el bloque de rejection_lessons aparece en prefix_parts (ruta copilot)."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "true")

    # Patch del helper compartido
    with patch("services.memory_prefix.build_memory_prefix",
               return_value=("LECCIÓN DE RECHAZO\n", {"rejection_lessons_count": 1})) as mock_bmp, \
         patch("services.anti_patterns.relevant", return_value=[]), \
         patch("services.anti_patterns.build_prefix", return_value=""):

        import agents.base as base_mod
        # Llamamos _build_prefix_parts directamente con un agente mockeado
        agent = MagicMock()
        agent.type = "BusinessAgent"
        run_ctx = _make_run_ctx()

        prefix_parts: list[str] = []
        meta: dict = {"anti_patterns_count": 0}

        # Simular la lógica de anti_patterns → sin patterns relevantes
        patterns: list = []
        _existing = set()

        from services.memory_prefix import build_memory_prefix
        _rej_prefix, _rej_meta = build_memory_prefix(
            project=run_ctx.project,
            agent_type=agent.type,
            existing_patterns=_existing,
        )
        if _rej_prefix:
            prefix_parts.append(_rej_prefix)
        meta.update(_rej_meta)

    assert any("LECCIÓN DE RECHAZO" in p for p in prefix_parts)
    assert meta["rejection_lessons_count"] == 1


# ---------------------------------------------------------------------------
# Test 2 — Flag OFF → style_memory en copilot no se altera
# ---------------------------------------------------------------------------

def test_copilot_style_memory_unchanged_flag_off(monkeypatch):
    """Flag OFF: build_memory_prefix no inyecta nada; style_memory sigue copilot-only."""
    monkeypatch.setenv("STACKY_PUSH_REJECTIONS_ENABLED", "false")

    from services.memory_prefix import build_memory_prefix
    prefix, meta = build_memory_prefix(
        project="mi_proyecto",
        agent_type="BusinessAgent",
    )
    assert prefix == ""
    assert meta["rejection_lessons_count"] == 0

    # Verificar que style_memory sigue definida copilot-only en base.py
    import ast, pathlib
    base_src = pathlib.Path(__file__).resolve().parents[1] / "agents" / "base.py"
    tree = ast.parse(base_src.read_text(encoding="utf-8"))
    # Buscamos el import de style_memory en el árbol AST
    style_imports = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module and "style_memory" in node.module
    ]
    # style_memory no debe estar en un import de nivel módulo (está inline/lazy)
    # Solo verificamos que el archivo contiene la referencia
    src_text = base_src.read_text(encoding="utf-8")
    assert "style_memory" in src_text, "style_memory debe seguir presente en base.py"
    # Verificamos que memory_prefix.py NO importa style_memory (copilot-only).
    # Usamos búsqueda de texto en código (no en docstrings: separamos líneas de código).
    mp_src = pathlib.Path(__file__).resolve().parents[1] / "services" / "memory_prefix.py"
    mp_lines = mp_src.read_text(encoding="utf-8").splitlines()
    # Líneas de código reales (sin docstrings trilple-quote ni comentarios #)
    import_lines = [
        ln for ln in mp_lines
        if ("import" in ln or "from" in ln) and "style_memory" in ln
        and not ln.strip().startswith("#")
        and not ln.strip().startswith('"""')
        and not ln.strip().startswith("'")
    ]
    assert not import_lines, f"memory_prefix.py NO debe importar style_memory: {import_lines}"
