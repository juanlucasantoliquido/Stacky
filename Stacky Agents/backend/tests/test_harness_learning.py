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


# ── F1 — T9..T16 ─────────────────────────────────────────────────────────────

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "harness_metadata_sample.json"


def _md(bloque: str) -> dict:
    """Metadata REAL congelada en el fixture de F1.0. Prohibido inventar claves."""
    import json

    return json.loads(_FIXTURE.read_text(encoding="utf-8"))[bloque]


def _seed_execution(project: str, *, metadata: dict, title: str = "Ticket de prueba",
                    work_item_type: str | None = "Bug") -> tuple[int, int]:
    """Crea un Ticket + AgentExecution reales y devuelve (ticket_id, execution_id)."""
    from db import session_scope
    from models import AgentExecution, Ticket

    with session_scope() as s:
        t = Ticket(
            ado_id=_seed_execution.counter,
            project=project,
            stacky_project_name=project,
            title=title,
            work_item_type=work_item_type,
        )
        _seed_execution.counter += 1
        s.add(t)
        s.flush()
        e = AgentExecution(
            ticket_id=t.id,
            agent_type="developer",
            status="completed",
            input_context_json="{}",   # NOT NULL en el modelo
            started_by="test",         # NOT NULL en el modelo
        )
        e.metadata_dict = metadata
        s.add(e)
        s.flush()
        return t.id, e.id


_seed_execution.counter = 900001


def test_harvest_extracts_criterion_fail(app_ctx):
    """T9 — cosecha los criterios incumplidos usando el FIXTURE REAL de F1.0."""
    from services.harness_learning import harvest_from_execution, list_patterns

    tid, eid = _seed_execution("HL_H_CRIT", metadata=_md("con_senales"))
    n = harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    )
    assert n > 0
    kinds = {p.signal_kind for p in list_patterns("HL_H_CRIT", min_confidence=0.0)}
    assert "criterion_fail" in kinds
    assert "contract_fail" in kinds      # precondition_failure.check
    assert "verifier_fail" in kinds      # validation_playbook.degraded_reason
    assert "run_failure" in kinds        # failure_kind


def test_harvest_extracts_repair_success_with_hint(app_ctx):
    """T10 — el repair exitoso deja un patrón con remedy_hint no vacío."""
    from services.harness_learning import harvest_from_execution, list_patterns

    tid, eid = _seed_execution("HL_H_REP", metadata=_md("con_senales"))
    harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    )
    repairs = [
        p for p in list_patterns("HL_H_REP", min_confidence=0.0)
        if p.signal_kind == "repair_success"
    ]
    assert repairs, "no se cosechó ningún repair_success"
    assert any(p.remedy_hint.strip() for p in repairs)


def test_harvest_is_noop_without_signals(app_ctx):
    """T11 — metadata sin señales → 0 patrones, sin excepción."""
    from services.harness_learning import harvest_from_execution, list_patterns

    tid, eid = _seed_execution("HL_H_VACIO", metadata=_md("sin_senales"))
    assert harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    ) == 0
    assert list_patterns("HL_H_VACIO", min_confidence=0.0) == []

    # …y metadata literalmente vacía tampoco rompe
    tid2, eid2 = _seed_execution("HL_H_VACIO2", metadata={})
    assert harvest_from_execution(
        ticket_id=tid2, execution_id=eid2, final_status="error", agent_type="qa"
    ) == 0


def test_harvest_never_raises(app_ctx):
    """T12 — metadata corrupta y ejecución inexistente no propagan excepción."""
    from services.harness_learning import harvest_from_execution

    tid, eid = _seed_execution("HL_H_CORR", metadata=_md("corrupta"))
    harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="error", agent_type="developer"
    )  # no debe lanzar
    # ejecución / ticket inexistentes
    assert harvest_from_execution(
        ticket_id=-1, execution_id=-1, final_status="error", agent_type=None, error="x"
    ) == 0


def test_classify_ticket_kind_uses_work_item_type(app_ctx):
    """T13 — GATE de B6: el 2º parámetro es el WORK ITEM TYPE, no un Ticket.type.

    `Ticket.type` NO EXISTE en el modelo (los campos reales son work_item_type y
    local_work_item_type). El plan v2 hacía getattr(ticket,"type",None), que
    devuelve None SIEMPRE y EN SILENCIO: con esa versión, este test falla.
    """
    from services.harness_learning import classify_ticket_kind

    assert classify_ticket_kind("lo que sea", "Bug") == "bug"
    assert classify_ticket_kind("lo que sea", "Feature") == "feature"
    assert classify_ticket_kind("lo que sea", "Task") == "task"
    # el tipo del tracker MANDA sobre el título
    assert classify_ticket_kind("nueva funcionalidad de reportes", "Bug") == "bug"
    # sin tipo, cae al título
    assert classify_ticket_kind("Error al calcular el saldo", None) == "bug"
    assert classify_ticket_kind("Nueva funcionalidad de exportación", None) == "feature"
    assert classify_ticket_kind("", None) == "unknown"

    # …y el harvest lo toma del campo REAL del ticket, no de un "type" inexistente
    from services.harness_learning import harvest_from_execution, list_patterns

    tid, eid = _seed_execution(
        "HL_H_KIND", metadata=_md("con_senales"), title="da igual", work_item_type="Bug"
    )
    harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    )
    pats = list_patterns("HL_H_KIND", min_confidence=0.0)
    assert pats and all(p.ticket_kind == "bug" for p in pats)


def test_flag_off_does_not_harvest(app_ctx, monkeypatch):
    """T14 — flag OFF → 0 y cero escrituras."""
    from config import config as cfg
    from services import memory_store
    from services.harness_learning import HARNESS_PATTERN_SCOPE, harvest_from_execution

    monkeypatch.setattr(cfg, "STACKY_HARNESS_LEARNING_HARVEST_ENABLED", False, raising=False)
    antes = len(memory_store.list_observations(scope=HARNESS_PATTERN_SCOPE, limit=500))
    tid, eid = _seed_execution("HL_H_OFF", metadata=_md("con_senales"))
    assert harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    ) == 0
    despues = len(memory_store.list_observations(scope=HARNESS_PATTERN_SCOPE, limit=500))
    assert despues == antes, "con la flag OFF se escribieron observaciones"


def test_harvest_signature_matches_post_hook_contract(app_ctx):
    """T15 — GATE contra el defecto que mató a v1: la firma imaginada.

    register_post_hook documenta literalmente:
      fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)
    """
    import inspect

    from services.harness_learning import harvest_from_execution

    sig = inspect.signature(harvest_from_execution)
    kw = {
        n for n, p in sig.parameters.items()
        if p.kind is inspect.Parameter.KEYWORD_ONLY
    }
    assert {"ticket_id", "execution_id", "final_status", "agent_type", "error"} <= kw
    assert any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    ), "falta **kwargs: el chokepoint puede pasar claves adicionales"
    # y no exige nada posicional
    assert not [
        n for n, p in sig.parameters.items()
        if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    ]


def test_hook_is_registered_in_app(app_ctx):
    """T16 — GATE anti-"construido y jamás cableado".

    Se verifica por AST y no por grep: un grep cuenta también comentarios y
    strings. Se ancla por SÍMBOLO (harness_learning + register), no por línea.
    """
    import ast

    src = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    cableado = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (
            isinstance(fn, ast.Attribute)
            and fn.attr == "register"
            and isinstance(fn.value, ast.Name)
            and fn.value.id == "harness_learning"
        ):
            cableado = True
            break
    assert cableado, (
        "F1 no está cableada: app.py no llama harness_learning.register(...). "
        "El gate de implementado no es que exista el símbolo, es que exista un "
        "consumidor de PRODUCCIÓN."
    )


# ── F3 — T17..T23 ────────────────────────────────────────────────────────────


def test_confidence_grows_with_occurrences(app_ctx):
    """T17 — monotonía y techo en 1.0."""
    from services.harness_learning import compute_confidence

    vals = [compute_confidence(n, 0) for n in (1, 2, 3, 4, 5)]
    assert vals == sorted(vals) and len(set(vals)) == 5
    assert compute_confidence(5, 0) == 1.0
    assert compute_confidence(50, 0) == 1.0, "la base debe topear en 1.0"
    assert compute_confidence(0, 0) == 0.0


def test_confidence_decays_with_age(app_ctx):
    """T18 — half-life de 30 días."""
    from services.harness_learning import compute_confidence

    hoy = compute_confidence(5, 0)
    un_hl = compute_confidence(5, 30)
    dos_hl = compute_confidence(5, 60)
    assert hoy == 1.0
    assert un_hl == 0.5
    assert dos_hl == 0.25
    # 6 ocurrencias hace 120 días: base topea en 1.0 y decae 4 half-lives.
    # 1.0 * 0.5**4 = 0.0625 y round(0.0625, 3) == 0.062 — NO 0.063: Python usa
    # banker's rounding y 0.0625 cae exactamente en el medio. El plan escribía
    # 0.063; el valor real de la fórmula es 0.062.
    assert compute_confidence(6, 120) == 0.062
    assert compute_confidence(6, 120) < 0.5, "un patrón rancio no se inyecta"


def test_single_occurrence_below_default_threshold(app_ctx):
    """T19 — 1 ocurrencia hoy = 0.2 < 0.5: el sistema arranca SILENCIOSO."""
    from services.harness_learning import compute_confidence

    assert compute_confidence(1, 0) == 0.2
    assert compute_confidence(1, 0) < 0.5


def test_three_occurrences_reach_threshold(app_ctx):
    """T20 — 3 ocurrencias hoy = 0.6 >= 0.5: fija el PUNTO DE ENCENDIDO.

    Es lo que sostiene el riesgo asumido de §4-bis: la inyección nace ON pero es
    inerte hasta que hay evidencia repetida.
    """
    from services.harness_learning import compute_confidence

    assert compute_confidence(2, 0) == 0.4 and compute_confidence(2, 0) < 0.5
    assert compute_confidence(3, 0) == 0.6
    assert compute_confidence(3, 0) >= 0.5


def test_dismissed_pattern_is_never_listed(app_ctx):
    """T21 — un patrón en "rejected" no aparece en list_patterns."""
    from services import memory_store
    from services.harness_learning import (
        PATTERN_STATUS_DISMISSED,
        is_suppressed,
        list_patterns,
        persist_pattern,
    )

    mid = persist_pattern(_pattern(project="HL_DISM", signal_key="senal descartable"))
    assert [p for p in list_patterns("HL_DISM", min_confidence=0.0)]

    assert memory_store.set_status(mid, PATTERN_STATUS_DISMISSED) is True
    assert list_patterns("HL_DISM", min_confidence=0.0) == []
    assert is_suppressed(memory_store.get(mid)["status"]) is True


def test_dismissed_status_is_in_all_statuses(app_ctx):
    """T22 — "rejected" pertenece a la taxonomía; "dismissed" NO existe."""
    from services import memory_store
    from services.harness_learning import PATTERN_STATUS_ACTIVE, PATTERN_STATUS_DISMISSED

    assert PATTERN_STATUS_DISMISSED in memory_store.ALL_STATUSES
    assert PATTERN_STATUS_ACTIVE in memory_store.ALL_STATUSES
    assert "dismissed" not in memory_store.ALL_STATUSES


def test_dismissed_pattern_is_not_resurrected_by_reharvest(app_ctx):
    """T23 — GATE de la decisión (b): el descarte del operador es DE POR VIDA.

    Es el único test que recorre el mecanismo entero por el camino de
    PRODUCCIÓN: cosecha con harvest_from_execution, descarta, y VUELVE A
    COSECHAR la misma ejecución. Un test que fabrique la fila a mano no prueba
    nada de esto — el defecto vive en el camino, no en el dato:
    upsert_by_topic_key pisa `status` incondicionalmente, así que sin el guard
    de persist_pattern la re-cosecha reactivaría el patrón en silencio.
    """
    from services import memory_store
    from services.harness_learning import (
        HARNESS_PATTERN_SCOPE,
        PATTERN_STATUS_DISMISSED,
        harvest_from_execution,
        list_patterns,
    )

    proj = "HL_NORESU"
    tid, eid = _seed_execution(proj, metadata=_md("con_senales"))

    # 1) cosecha por el camino de producción
    assert harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    ) > 0
    activos = memory_store.list_observations(
        project=proj, scope=HARNESS_PATTERN_SCOPE, status="active", limit=500
    )
    assert activos, "la primera cosecha no dejó nada que descartar"
    victima = activos[0]
    topic = victima["topic_key"]
    rev_al_descartar = victima["revision_count"]

    # 2) el operador lo descarta
    assert memory_store.set_status(victima["memory_id"], PATTERN_STATUS_DISMISSED) is True

    # 3) vuelve a correr la MISMA ejecución (el escenario real: el run se repite)
    harvest_from_execution(
        ticket_id=tid, execution_id=eid, final_status="completed", agent_type="developer"
    )

    fila = memory_store.get(victima["memory_id"])
    assert fila["status"] == PATTERN_STATUS_DISMISSED, (
        "la re-cosecha RESUCITÓ un patrón descartado: falta el guard de "
        "is_dismissed_topic en persist_pattern"
    )
    assert fila["revision_count"] == rev_al_descartar, (
        "la re-cosecha tocó la fila descartada (revision_count creció)"
    )
    assert all(
        p.signal_key != fila["title"] for p in list_patterns(proj, min_confidence=0.0)
    ), "el patrón descartado volvió a list_patterns"

    # y tampoco se creó un DUPLICADO con el mismo topic_key en otro estado
    mismo_topic = [
        r for r in memory_store.list_observations(
            project=proj, scope=HARNESS_PATTERN_SCOPE, limit=500
        )
        if r["topic_key"] == topic
    ]
    assert len(mismo_topic) == 1, (
        f"la re-cosecha creó {len(mismo_topic)} filas para el mismo topic_key"
    )


def test_verifier_fail_only_on_degraded_status(app_ctx):
    """T24 — el playbook sólo es señal de fallo cuando está "degraded".

    Defecto encontrado MIDIENDO, no leyendo: el enum del productor es
    VALID_STATUSES = {"agent_provided", "enriched", "degraded", "disabled"}
    (services/validation_playbook.py) y **"ok" NO EXISTE en él**. Una condición
    `status != "ok"` — la que el plan proponía — cosecha como fallo TODOS los
    estados, incluido "enriched", que es el de ÉXITO: 15 filas "enriched" contra
    6 "degraded" en la DB real. Este test se ancla al enum del PRODUCTOR, así que
    si mañana agrega un estado nuevo, rompe acá y no en silencio.
    """
    from services.harness_learning import _extract_signals
    from services.validation_playbook import VALID_STATUSES

    assert "ok" not in VALID_STATUSES, (
        'el extractor NO puede compararse contra "ok": no está en el enum'
    )
    assert "degraded" in VALID_STATUSES

    def kinds(status, reason=None):
        md = {"validation_playbook": {"status": status, "degraded_reason": reason}}
        return {k for k, _key, _r in _extract_signals(md)}

    assert kinds("degraded", "no_grounding") == {"verifier_fail"}
    for sano in VALID_STATUSES - {"degraded"}:
        assert "verifier_fail" not in kinds(sano), (
            f'el estado "{sano}" no es un fallo y se estaba cosechando como tal'
        )

    # …y la clave usada es el motivo, no el status
    sigs = _extract_signals(
        {"validation_playbook": {"status": "degraded", "degraded_reason": "no_grounding"}}
    )
    assert ("verifier_fail", "no_grounding", "") in sigs
