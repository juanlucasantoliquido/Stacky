"""Plan 35 — Aprendizaje del arnés: patrones reutilizables.

Numeración POR ARCHIVO (v3/B1): F0 aporta T1..T8, F1 aporta T9..T16,
F3 aporta T17..T23. El test de registro de flags vive en
tests/test_harness_flags.py y NO cuenta acá.

Comando:
  & "…/backend/venv/Scripts/python.exe" -m pytest "tests/test_harness_learning.py" -q
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


def _pattern(**over):
    """HarnessPattern con valores por defecto sanos; `over` pisa lo que haga falta."""
    from services.harness_learning import HarnessPattern

    base = dict(
        project="HL_T",
        agent_type="developer",
        ticket_kind="bug",
        signal_kind="criterion_fail",
        signal_key="CA-01 el importe se muestra sin redondeo",
        remedy_hint="",
        occurrences=1,
        confidence=0.0,
        last_seen="2026-08-01",
    )
    base.update(over)
    return HarnessPattern(**base)


# ── F0 — T1..T8 ──────────────────────────────────────────────────────────────


def test_pattern_topic_key_is_stable(app_ctx):
    """T1 — misma tupla → misma key; distinto signal_key → distinta."""
    from services.harness_learning import pattern_topic_key

    a = _pattern()
    b = _pattern()
    c = _pattern(signal_key="CA-02 otra cosa distinta")

    assert pattern_topic_key(a) == pattern_topic_key(b)
    assert pattern_topic_key(a) != pattern_topic_key(c)
    # y cambia con cada componente de la tupla
    assert pattern_topic_key(a) != pattern_topic_key(_pattern(agent_type="qa"))
    assert pattern_topic_key(a) != pattern_topic_key(_pattern(ticket_kind="feature"))
    assert pattern_topic_key(a) != pattern_topic_key(_pattern(signal_kind="verifier_fail"))
    assert pattern_topic_key(a) != pattern_topic_key(_pattern(project="OTRO"))


def test_persist_is_idempotent_by_topic_key(app_ctx):
    """T2 — persistir dos veces NO crea dos observaciones."""
    from services import memory_store
    from services.harness_learning import HARNESS_PATTERN_SCOPE, persist_pattern

    p = _pattern(project="HL_IDEM")
    first = persist_pattern(p)
    second = persist_pattern(p)

    assert first and first == second
    rows = memory_store.list_observations(
        project="HL_IDEM", scope=HARNESS_PATTERN_SCOPE, limit=50
    )
    assert len(rows) == 1, f"esperaba 1 observación, hay {len(rows)}"


def test_persist_increments_revision_count(app_ctx):
    """T3 — el 2º persist deja revision_count == 2 (occurrences es DERIVABLE)."""
    from services import memory_store
    from services.harness_learning import persist_pattern

    p = _pattern(project="HL_REV")
    mid = persist_pattern(p)
    assert memory_store.get(mid)["revision_count"] == 1
    persist_pattern(p)
    assert memory_store.get(mid)["revision_count"] == 2


def test_persist_redacts_secrets(app_ctx):
    """T4 — un PAT en el remedy_hint se guarda enmascarado y sin el valor original."""
    from services import memory_store
    from services.harness_learning import persist_pattern

    pat = "glpat-" + "A1b2C3d4E5f6G7h8I9j0"
    mid = persist_pattern(
        _pattern(project="HL_SEC", remedy_hint=f"reintentar con el token {pat}")
    )
    row = memory_store.get(mid)
    blob = (row["content"] or "") + (row["title"] or "")
    assert "***REDACTED***" in blob
    assert pat not in blob


def test_persist_passes_required_type(app_ctx):
    """T5 — la observación persistida tiene type == "pattern" (gate anti-TypeError)."""
    from services import memory_store
    from services.harness_learning import HARNESS_PATTERN_TYPE, persist_pattern

    mid = persist_pattern(_pattern(project="HL_TYPE"))
    assert memory_store.get(mid)["type"] == HARNESS_PATTERN_TYPE == "pattern"


def test_harness_pattern_scope_is_never_injected(app_ctx):
    """T6 — el scope reservado NO entra a get_context_for_run con sus defaults.

    Fija como CONTRATO lo que hoy es sólo un default: INJECT_SCOPES es allowlist
    y "harness_pattern" queda afuera por construcción.
    """
    from services import memory_store
    from services.harness_learning import HARNESS_PATTERN_SCOPE, persist_pattern

    marca = "MARCADORINYECCIONHL"
    persist_pattern(_pattern(project="HL_INJ", signal_key=marca))

    # Guarda POSITIVA en el mismo test: una observación de scope inyectable SÍ entra.
    memory_store.save_observation(
        project="HL_INJ",
        type="bugfix",
        title=f"control positivo {marca}",
        content=f"este texto SI debe inyectarse {marca}",
        scope="project",
    )
    ctx = memory_store.get_context_for_run(
        project="HL_INJ", agent_type="developer", query_text=marca
    )
    assert marca in ctx["content"], "el control positivo no se inyectó: el test no prueba nada"

    # …y ninguno de los ids inyectados es del scope reservado.
    for mid in ctx["memory_ids"]:
        assert memory_store.get(mid)["scope"] != HARNESS_PATTERN_SCOPE


def test_normalize_signal_key_bounds_topic_key(app_ctx):
    """T7 — un criterio largo produce un topic_key ≤ 200 chars y estable."""
    from services.harness_learning import normalize_signal_key, pattern_topic_key

    largo = (
        "CA-01: Cliente con SCOBLIGACION cargado abre pestana Scoring columna "
        "Obligacion aparece inmediatamente despues de Cod. Cliente con el valor "
        "de SCOBLIGACION y ademas se valida el redondeo y el formato de moneda"
    )
    assert len(largo) > 200
    k1 = normalize_signal_key(largo)
    k2 = normalize_signal_key("  " + largo.upper() + "  ")
    assert k1 == k2, "la normalización no es estable ante espacios/mayúsculas"

    topic = pattern_topic_key(_pattern(project="P" * 80, signal_key=largo))
    assert len(topic) <= 200, f"topic_key de {len(topic)} chars no entra en String(200)"

    # dos criterios con el MISMO prefijo largo no colisionan
    otro = largo[:-10] + "OTRA COSA DISTINTA"
    assert normalize_signal_key(largo) != normalize_signal_key(otro)


def test_empty_project_is_not_persisted(app_ctx):
    """T8 — project="" → "" y cero filas."""
    from services import memory_store
    from services.harness_learning import HARNESS_PATTERN_SCOPE, persist_pattern

    # Ojo: list_observations(project="") NO filtra por proyecto — el chequeo es
    # `if project:` y "" es falsy, así que devolvería TODO el scope. Se cuenta el
    # delta del scope completo, que es lo que de verdad se quiere probar.
    antes = len(memory_store.list_observations(scope=HARNESS_PATTERN_SCOPE, limit=500))
    assert persist_pattern(_pattern(project="")) == ""
    assert persist_pattern(_pattern(project="   ")) == ""
    despues = memory_store.list_observations(scope=HARNESS_PATTERN_SCOPE, limit=500)
    assert len(despues) == antes, "un project vacío escribió una observación"
    assert all((r.get("project") or "").strip() for r in despues)
