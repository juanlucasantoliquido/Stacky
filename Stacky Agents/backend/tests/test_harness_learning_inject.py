"""Plan 35 F2 — reinyección de patrones como pista podable (prioridad 45).

Numeración POR ARCHIVO: I1..I9.

Comando:
  & "…/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning_inject.py" -q
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


def _seed(project, *, signal_key, veces=1, agent_type="developer", ticket_kind="bug",
          signal_kind="criterion_fail", remedy=""):
    """Persiste un patrón `veces` veces: cada upsert sube revision_count, que es
    de donde sale `occurrences` y por lo tanto la confianza."""
    from services.harness_learning import HarnessPattern, persist_pattern

    p = HarnessPattern(
        project=project, agent_type=agent_type, ticket_kind=ticket_kind,
        signal_kind=signal_kind, signal_key=signal_key, remedy_hint=remedy,
        occurrences=1, confidence=0.0, last_seen="2026-08-01",
    )
    mid = ""
    for _ in range(veces):
        mid = persist_pattern(p)
    return mid


def test_hint_block_lists_top_patterns_by_confidence(app_ctx):
    """I1 — con 8 patrones se inyectan los 5 de mayor confianza."""
    from services.harness_learning import build_pattern_hint_block

    proj = "HLI_TOP"
    # 8 patrones con ocurrencias 8..1 → confianzas decrecientes
    for i, veces in enumerate([8, 7, 6, 5, 4, 3, 2, 1]):
        _seed(proj, signal_key=f"senal numero {i}", veces=veces)

    block = build_pattern_hint_block(
        project=proj, agent_type="developer", ticket_title="algo",
        work_item_type="Bug", max_patterns=5, min_confidence=0.0,
    )
    assert block is not None
    lineas = [l for l in block["content"].splitlines() if l.strip().startswith("-")]
    assert len(lineas) == 5, f"esperaba 5 pistas, hay {len(lineas)}"
    # las 3 de menor confianza (ocurrencias 3, 2 y 1) no entran
    assert "senal numero 7" not in block["content"]
    assert "senal numero 0" in block["content"]


def test_hint_block_filters_by_agent_and_ticket_kind(app_ctx):
    """I2 — un patrón de otro agente o de otro tipo de ticket no se inyecta."""
    from services.harness_learning import build_pattern_hint_block

    proj = "HLI_SEG"
    _seed(proj, signal_key="propio del developer bug", veces=5,
          agent_type="developer", ticket_kind="bug")
    _seed(proj, signal_key="del qa", veces=5, agent_type="qa", ticket_kind="bug")
    _seed(proj, signal_key="de una feature", veces=5,
          agent_type="developer", ticket_kind="feature")

    block = build_pattern_hint_block(
        project=proj, agent_type="developer", ticket_title="x",
        work_item_type="Bug", max_patterns=10, min_confidence=0.0,
    )
    assert block is not None
    assert "propio del developer bug" in block["content"]
    assert "del qa" not in block["content"]
    assert "de una feature" not in block["content"]


def test_no_patterns_returns_none(app_ctx):
    """I3 — sin patrones devuelve None, NO un bloque vacío (costo cero)."""
    from services.harness_learning import build_pattern_hint_block

    assert build_pattern_hint_block(
        project="HLI_NADA", agent_type="developer", ticket_title="x",
        work_item_type="Bug", max_patterns=5, min_confidence=0.0,
    ) is None
    # y tampoco inyecta cuando los patrones existen pero no llegan al umbral
    _seed("HLI_BAJO", signal_key="visto una sola vez", veces=1)   # confianza 0.2
    assert build_pattern_hint_block(
        project="HLI_BAJO", agent_type="developer", ticket_title="x",
        work_item_type="Bug", max_patterns=5, min_confidence=0.5,
    ) is None


def test_block_priority_is_registered_in_the_engine(app_ctx):
    """I4 — ANTI-FALSO-VERDE: la prioridad se consulta al MOTOR, no a una constante.

    _DEFAULT_PRIORITY es 50: un bloque NO registrado en _BLOCK_PRIORITY recibe 50
    por accidente. Por eso el valor elegido es 45 — si el registro se olvida,
    _block_priority devuelve 50 y este test falla. Con 50 el test no podría
    distinguir "registrado" de "olvidado".
    """
    from services.context_enrichment import _DEFAULT_PRIORITY, _block_priority
    from services.harness_learning import HARNESS_PATTERN_BLOCK_ID

    prio = _block_priority({"id": HARNESS_PATTERN_BLOCK_ID})
    assert prio == 45
    assert prio != _DEFAULT_PRIORITY, (
        "la prioridad coincide con el default: el bloque NO está registrado en "
        "_BLOCK_PRIORITY y el test sería un falso verde"
    )


def test_block_priority_is_below_acceptance_criteria(app_ctx):
    """I5 — la pista se poda ANTES que criterios, contrato y few-shot."""
    from services.context_enrichment import (
        _BLOCK_PRIORITY,
        _HIGH_PRIORITY_THRESHOLD,
        _block_priority,
    )
    from services.harness_learning import HARNESS_PATTERN_BLOCK_ID

    prio = _block_priority({"id": HARNESS_PATTERN_BLOCK_ID})
    assert prio < _BLOCK_PRIORITY["acceptance-criteria"]      # 45 < 74
    assert prio < _BLOCK_PRIORITY["acceptance-contract"]      # 45 < 76
    assert prio < _BLOCK_PRIORITY["few-shot-approved"]        # 45 < 55
    assert prio < _HIGH_PRIORITY_THRESHOLD                    # nunca es fuente de verdad
    assert prio > _BLOCK_PRIORITY["ado-similar-tickets"]      # 45 > 40


def test_block_shape_is_a_dict_with_id(app_ctx):
    """I6 — el bloque es un dict con kind/id/title/content; `Block` no existe."""
    import services.context_enrichment as ce
    from services.harness_learning import HARNESS_PATTERN_BLOCK_ID, build_pattern_hint_block

    _seed("HLI_SHAPE", signal_key="una senal cualquiera", veces=5)
    block = build_pattern_hint_block(
        project="HLI_SHAPE", agent_type="developer", ticket_title="x",
        work_item_type="Bug", max_patterns=5, min_confidence=0.0,
    )
    assert isinstance(block, dict)
    assert set(block) >= {"kind", "id", "title", "content"}
    assert block["id"] == HARNESS_PATTERN_BLOCK_ID == "harness-patterns"
    assert block["kind"] == "text"
    assert "priority" not in block, "la prioridad NO es un campo del bloque"
    assert not hasattr(ce, "Block"), "no existe ninguna clase Block en el motor"


def test_flag_off_no_block(app_ctx, monkeypatch):
    """I7 — con la flag OFF, enrich_blocks no agrega el bloque."""
    from config import config as cfg
    from services import context_enrichment as ce
    from services.harness_learning import HARNESS_PATTERN_BLOCK_ID

    _seed("HLI_OFF", signal_key="senal que no debe inyectarse", veces=5)

    monkeypatch.setattr(cfg, "STACKY_HARNESS_LEARNING_INJECT_ENABLED", False, raising=False)
    blocks, _ = ce.enrich_blocks(
        ticket_id=None, agent_type="developer", raw_blocks=[], project_ctx=None
    )
    assert not any(b.get("id") == HARNESS_PATTERN_BLOCK_ID for b in blocks)


def test_list_patterns_runs_one_query(app_ctx, monkeypatch):
    """I8 — GATE de costo: build_pattern_hint_block hace UNA sola query.

    El camino caliente corre en cada run de los 3 runtimes. Con el filtro de
    confianza en Python (decisión (a)), el techo debe seguir siendo
    1 query + N deserializaciones, nunca N queries.
    """
    from services import harness_learning as hl
    from services import memory_store

    proj = "HLI_QUERY"
    for i in range(12):
        _seed(proj, signal_key=f"senal {i}", veces=5)

    llamadas = []
    real = memory_store.list_observations

    def spy(**kwargs):
        llamadas.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(memory_store, "list_observations", spy)
    block = hl.build_pattern_hint_block(
        project=proj, agent_type="developer", ticket_title="x",
        work_item_type="Bug", max_patterns=5, min_confidence=0.0,
    )
    assert block is not None
    assert len(llamadas) == 1, f"esperaba 1 query, hubo {len(llamadas)}: {llamadas}"
    # y va acotada: proyecto + scope + status + limit
    kw = llamadas[0]
    assert kw["project"] == proj
    assert kw["scope"] == hl.HARNESS_PATTERN_SCOPE
    assert kw["status"] == hl.PATTERN_STATUS_ACTIVE
    assert int(kw["limit"]) > 0


def test_enrich_blocks_calls_the_builder(app_ctx):
    """I9 — GATE anti-"construido y jamás cableado", por AST.

    No alcanza con que el símbolo exista: tiene que haber un consumidor de
    PRODUCCIÓN. Se verifica por AST y no por grep, que contaría comentarios y
    strings.
    """
    import ast

    ruta = Path(__file__).resolve().parents[1] / "services" / "context_enrichment.py"
    tree = ast.parse(ruta.read_text(encoding="utf-8"))

    llamado = any(
        isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "build_pattern_hint_block"
        for n in ast.walk(tree)
    )
    assert llamado, (
        "F2 no está cableada: context_enrichment no llama a "
        "build_pattern_hint_block. El bloque nunca llegaría a un run real."
    )

    # y la prioridad está registrada en el mapa del motor, no en una constante local
    from services.context_enrichment import _BLOCK_PRIORITY

    assert _BLOCK_PRIORITY.get("harness-patterns") == 45
