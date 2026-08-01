"""Plan 279 F2 — Tests de la maquina de estados de creacion de pipeline.

11 casos. PUROS: no tocan flask, ni la DB, ni la red.
"""
from __future__ import annotations

import json

from services.pipeline_session import (
    MAX_SESSION_BYTES,
    PIPELINE_SESSION_STATES,
    TERMINAL_STATES,
    TRANSITIONS,
    PipelineSession,
    advance,
    can_transition,
    next_question,
    session_from_dict,
    session_to_dict,
    undo_hint,
)


def test_hay_exactamente_8_estados():
    """KPI K5: la maquina de estados es CERRADA."""
    assert len(PIPELINE_SESSION_STATES) == 8, PIPELINE_SESSION_STATES
    assert len(set(PIPELINE_SESSION_STATES)) == 8, "hay estados duplicados"


def test_toda_clave_de_transitions_es_un_estado():
    fuera = [k for k in TRANSITIONS if k not in PIPELINE_SESSION_STATES]
    assert fuera == [], fuera
    faltan = [s for s in PIPELINE_SESSION_STATES if s not in TRANSITIONS]
    assert faltan == [], faltan


def test_todo_destino_de_transitions_es_un_estado():
    fuera = sorted({
        d for destinos in TRANSITIONS.values()
        for d in destinos if d not in PIPELINE_SESSION_STATES
    })
    assert fuera == [], fuera


def test_los_terminales_no_tienen_salida():
    for t in TERMINAL_STATES:
        assert TRANSITIONS[t] == (), (t, TRANSITIONS[t])


def test_can_transition_acepta_las_legales():
    assert can_transition("intake", "discovery") is True
    assert can_transition("discovery", "draft") is True
    assert can_transition("draft", "review") is True
    assert can_transition("review", "confirm") is True
    assert can_transition("confirm", "committed") is True


def test_can_transition_rechaza_las_ilegales():
    assert can_transition("intake", "committed") is False
    assert can_transition("intake", "confirm") is False
    assert can_transition("committed", "draft") is False
    assert can_transition("failed", "intake") is False
    # NUNCA lanza, ni con vocabulario inventado.
    assert can_transition("inventado", "draft") is False
    assert can_transition("draft", "inventado") is False
    assert can_transition("", "") is False


def test_advance_ilegal_devuelve_la_sesion_original_y_motivo():
    s = PipelineSession(state="intake", project="P")
    nueva, motivo = advance(s, "committed")
    assert nueva is s, "una transicion ilegal NO puede devolver una sesion nueva"
    assert motivo, "una transicion ilegal debe declarar el motivo"

    # Guard del caso borde: terminal -> terminal se rechaza con motivo propio.
    t = PipelineSession(state="committed")
    nueva_t, motivo_t = advance(t, "failed")
    assert nueva_t is t
    assert motivo_t == "estado_terminal", motivo_t

    # Y la legal SI avanza y aplica los campos.
    ok, sin_motivo = advance(s, "discovery", provider="ado", stack="python")
    assert sin_motivo == ""
    assert ok.state == "discovery"
    assert ok.provider == "ado"
    assert ok.stack == "python"
    assert s.state == "intake", "la original es frozen: no se muta"


def test_session_from_dict_es_tolerante():
    por_defecto = PipelineSession()
    assert session_from_dict(None) == por_defecto
    assert session_from_dict({}) == por_defecto
    assert session_from_dict({"state": "inventado"}) == por_defecto
    assert session_from_dict("no soy un dict") == por_defecto  # type: ignore[arg-type]
    assert session_from_dict({"state": 7}) == por_defecto  # type: ignore[dict-item]
    # Un dict valido SI se respeta (si no, el test de arriba pasaria por accidente).
    vivo = session_from_dict({"state": "draft", "provider": "gitlab"})
    assert vivo.state == "draft"
    assert vivo.provider == "gitlab"


def test_roundtrip_to_dict_from_dict():
    s = PipelineSession(
        state="confirm", provider="ado", stack="python", project="Proyecto",
        branch="feature/x", draft_ref="draft-1",
        missing_variables=("DB_PASSWORD", "API_TOKEN"),
        open_questions=("que rama?",), last_action_id="devops.pipeline_new.commit",
        retries=1, failure_reason="",
    )
    d = session_to_dict(s)
    assert session_from_dict(d) == s
    crudo = json.dumps(d)
    assert len(crudo.encode("utf-8")) <= MAX_SESSION_BYTES
    # undo_hint NO se serializa: se DERIVA (si viajara, podria quedar desfasado).
    assert "undo_hint" not in d
    assert undo_hint(s), "pero undo_hint() SI lo calcula desde provider+branch"


def test_next_question_es_determinista_y_vacia_si_no_faltan():
    assert next_question(PipelineSession()) == ""
    assert next_question(PipelineSession(open_questions=())) == ""
    s = PipelineSession(open_questions=("primera", "segunda", "tercera"))
    assert next_question(s) == "primera"
    assert next_question(s) == "primera", "no puede depender del orden de llamada"


def test_undo_hint_nombra_el_archivo_y_la_rama():
    """[ADICION ARQUITECTO] K7: el operador confirma VIENDO su deshacer."""
    ado = PipelineSession(state="confirm", provider="ado", branch="feature/x",
                          project="Proyecto")
    texto = undo_hint(ado)
    assert "azure-pipelines.yml" in texto, texto
    assert "feature/x" in texto, texto

    gitlab = PipelineSession(state="confirm", provider="gitlab", branch="feature/x")
    assert ".gitlab-ci.yml" in undo_hint(gitlab)
    assert "azure-pipelines.yml" not in undo_hint(gitlab)

    # Sin provider, sin rama, o con un provider fuera del vocabulario: "" —
    # NUNCA un nombre de archivo inventado.
    assert undo_hint(PipelineSession(provider="", branch="feature/x")) == ""
    assert undo_hint(PipelineSession(provider="ado", branch="")) == ""
    assert undo_hint(PipelineSession(provider="jenkins", branch="feature/x")) == ""
