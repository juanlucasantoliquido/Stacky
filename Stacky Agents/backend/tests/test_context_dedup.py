"""Tests TDD para I0.1 — Dedup léxico de hechos repetidos entre bloques de contexto.

Spec (doc 27 §I0.1):
- Flag OFF (default) → _dedup_blocks es identidad (byte-idéntico).
- Flag ON → líneas idénticas en bloques de menor prioridad se eliminan cuando
  ya aparecen en bloques de mayor prioridad.
- Bloques de prioridad alta (ado-epic-structured, client-profile, modal_user_input)
  NUNCA se podan.
- Dedup + budget conviven (dedup corre antes, budget sobre el resultado).
- Best-effort: cualquier excepción interna → devuelve bloques sin tocar.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _log(*_a, **_k):
    pass


# ---------------------------------------------------------------------------
# Helpers de fixtures
# ---------------------------------------------------------------------------

def _block(id_: str, content: str) -> dict:
    return {"id": id_, "content": content}


# ---------------------------------------------------------------------------
# Test 1: Flag OFF → byte-idéntico (devuelve la misma lista, sin copia)
# ---------------------------------------------------------------------------

def test_dedup_flag_off_returns_same_list(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", False, raising=False)

    blocks = [
        _block("ado-epic-structured", "línea repetida\ncontenido épica"),
        _block("ado-comments", "línea repetida\notro comentario"),
    ]
    result = ce._dedup_blocks(blocks, project_name="P", log=_log)
    # Cuando el flag está OFF debe ser byte-idéntico: misma referencia de lista.
    assert result is blocks


# ---------------------------------------------------------------------------
# Test 2: Flag ON → línea presente en bloque de alta prioridad se elimina
# del bloque de menor prioridad.
# ---------------------------------------------------------------------------

def test_dedup_removes_duplicate_line_from_low_priority(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "", raising=False)

    blocks = [
        _block("ado-epic-structured", "línea repetida\ncontenido épica"),
        _block("ado-comments", "línea repetida\ncomentario propio"),
    ]
    result = ce._dedup_blocks(blocks, project_name="P", log=_log)

    epic_content = next(b["content"] for b in result if b["id"] == "ado-epic-structured")
    comment_content = next(b["content"] for b in result if b["id"] == "ado-comments")

    # La épica permanece intacta (prioridad alta).
    assert "línea repetida" in epic_content
    # La línea duplicada se eliminó del comentario (prioridad baja).
    assert "línea repetida" not in comment_content
    # Pero el contenido propio del comentario se conserva.
    assert "comentario propio" in comment_content


# ---------------------------------------------------------------------------
# Test 3: Bloques de alta prioridad nunca se podan, aunque contengan duplicados
# entre sí o la "fuente" sea de menor prioridad.
# ---------------------------------------------------------------------------

def test_dedup_never_poda_high_priority_blocks(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "", raising=False)

    # Todos los bloques de alta prioridad tienen la misma línea.
    blocks = [
        _block("ado-epic-structured", "dato clave\népica"),
        _block("client-profile", "dato clave\nperfil"),
        _block("modal_user_input", "dato clave\nuser input"),
    ]
    result = ce._dedup_blocks(blocks, project_name="P", log=_log)

    # Ninguno de los bloques de alta prioridad fue tocado.
    for b in result:
        assert "dato clave" in b["content"], f"bloque {b['id']} fue podado incorrectamente"


# ---------------------------------------------------------------------------
# Test 4: Dedup es normalizado (mayúsculas, espacios extra no impiden el match).
# ---------------------------------------------------------------------------

def test_dedup_case_and_whitespace_insensitive(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "", raising=False)

    blocks = [
        _block("ado-epic-structured", "LÍNEA REPETIDA"),
        _block("ado-comments", "línea repetida   "),   # trailing spaces + lower
    ]
    result = ce._dedup_blocks(blocks, project_name="P", log=_log)

    comment_content = next(b["content"] for b in result if b["id"] == "ado-comments")
    # La línea (normalizada) fue detectada como duplicada y eliminada.
    assert comment_content.strip() == ""


# ---------------------------------------------------------------------------
# Test 5: Dedup + budget conviven — dedup corre antes y el budget opera
# sobre el resultado ya depurado.
# ---------------------------------------------------------------------------

def test_dedup_then_budget_pipeline(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    # Habilitar ambos: dedup + budget.
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "", raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_PROJECTS", "", raising=False)
    # Budget amplio para que no descarte nada por tokens.
    monkeypatch.setattr(config, "STACKY_CONTEXT_BUDGET_TOKENS", 100_000, raising=False)

    repeated = "hecho repetido"
    blocks = [
        _block("ado-epic-structured", f"{repeated}\n" + "E" * 100),
        _block("ado-comments", f"{repeated}\n" + "C" * 100),
    ]
    # enrich_blocks aplica dedup y luego budget internamente.
    # Usamos _dedup_blocks directo para verificar la primera etapa.
    deduped = ce._dedup_blocks(blocks, project_name="P", log=_log)

    comment_content = next(b["content"] for b in deduped if b["id"] == "ado-comments")
    assert repeated not in comment_content


# ---------------------------------------------------------------------------
# Test 6: Línea única (no repetida) no se elimina nunca.
# ---------------------------------------------------------------------------

def test_dedup_unique_lines_preserved(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "", raising=False)

    blocks = [
        _block("ado-epic-structured", "solo en épica"),
        _block("ado-comments", "solo en comentario"),
    ]
    result = ce._dedup_blocks(blocks, project_name="P", log=_log)

    assert any("solo en épica" in b["content"] for b in result)
    assert any("solo en comentario" in b["content"] for b in result)


# ---------------------------------------------------------------------------
# Test 7: Bloques sin campo "content" (ítems seleccionados) no rompen el dedup.
# ---------------------------------------------------------------------------

def test_dedup_block_without_content_field(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "", raising=False)

    blocks = [
        {"id": "ado-epic-structured", "items": [{"label": "criterio", "selected": True}]},
        _block("ado-comments", "criterio\notro"),
    ]
    # No debe lanzar excepción.
    result = ce._dedup_blocks(blocks, project_name="P", log=_log)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Test 8: Allowlist de proyectos — con flag ON y proyecto no en la lista,
# comportamiento byte-idéntico.
# ---------------------------------------------------------------------------

def test_dedup_project_allowlist_respected(monkeypatch):
    from config import config
    from services import context_enrichment as ce

    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", True, raising=False)
    monkeypatch.setattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "OTRO_PROYECTO", raising=False)

    blocks = [
        _block("ado-epic-structured", "línea repetida"),
        _block("ado-comments", "línea repetida"),
    ]
    result = ce._dedup_blocks(blocks, project_name="MI_PROYECTO", log=_log)
    # Mi proyecto no está en la allowlist → byte-idéntico.
    assert result is blocks
