"""Plan 279 F4 — Tests del contrato del agente (prompt del copiloto).

7 casos. PUROS: no tocan flask, ni la DB, ni la red, ni ningun modelo.
"""
from __future__ import annotations

from services.pipeline_copilot_prompt import build_copilot_prompt
from services.pipeline_session import TRANSITIONS, PipelineSession

_BASE = "http://localhost:5000"


def _prompt(session: PipelineSession, *, commit_enabled: bool = False,
            message: str = "necesito una pipeline de python") -> str:
    return build_copilot_prompt(
        session, _BASE, message, 42, commit_enabled=commit_enabled
    )


def test_el_prompt_nombra_el_estado_actual():
    p = _prompt(PipelineSession(state="draft"))
    assert "draft" in p, p[:400]
    # Y no miente diciendo que esta en otro estado.
    assert "intake" not in p.split("PEDIDO DEL OPERADOR")[0].replace("draft", "")


def test_el_prompt_lista_solo_las_transiciones_legales():
    p = _prompt(PipelineSession(state="draft"))
    cabecera = p.split("PEDIDO DEL OPERADOR")[0]
    legales = TRANSITIONS["draft"]          # ("review", "failed")
    for d in legales:
        assert d in cabecera, (d, cabecera)
    # 'committed' NO es alcanzable desde 'draft': no puede figurar como destino.
    assert "committed" not in cabecera, cabecera


def test_el_prompt_incluye_la_url_de_propose():
    p = _prompt(PipelineSession())
    assert f"{_BASE}/api/devops/actions/propose" in p, p[:600]


def test_con_commit_off_el_prompt_prohibe_la_accion_de_commit():
    off = _prompt(PipelineSession(state="confirm"), commit_enabled=False)
    assert "devops.pipeline_new.commit" in off
    assert "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED" in off, (
        "con la flag OFF el prompt debe NOMBRAR la flag que el operador tiene "
        "que activar por UI, no morir en un 'no puedo'"
    )
    # Guard: con la flag ON esa prohibicion NO aparece (si no, el assert de
    # arriba pasaria con un texto que esta siempre).
    on = _prompt(PipelineSession(state="confirm"), commit_enabled=True)
    assert "STACKY_PIPELINE_COPILOT_COMMIT_ENABLED" not in on, on


def test_el_prompt_incluye_la_regla_de_no_pedir_valores():
    p = _prompt(PipelineSession())
    assert (
        "Los valores de variables y secretos los maneja Stacky; NUNCA pidas ni "
        "escribas un valor."
    ) in p, p[:900]


def test_los_nombres_de_variables_aparecen_pero_ningun_valor():
    """K3 desde el lado del prompt: el agente maneja HANDLES, no secretos."""
    s = PipelineSession(state="secrets",
                        missing_variables=("DB_PASSWORD", "API_TOKEN"))
    p = _prompt(s)
    assert "DB_PASSWORD" in p
    assert "API_TOKEN" in p
    # Guard discriminante: una sesion SIN variables no las nombra.
    vacio = _prompt(PipelineSession(state="secrets"))
    assert "DB_PASSWORD" not in vacio


def test_en_confirm_el_prompt_trae_el_deshacer():
    """[ADICION ARQUITECTO] K7: el deshacer viaja en el prompt ANTES de confirmar."""
    s = PipelineSession(state="confirm", provider="ado", branch="feature/x",
                        project="Proyecto")
    p = _prompt(s)
    assert "azure-pipelines.yml" in p, p[:900]
    assert "feature/x" in p
    assert "Antes de pedir confirmacion, decile al operador como deshacer esto:" in p

    # En 'intake' NO hay nada que deshacer todavia: la frase no aparece.
    temprano = _prompt(PipelineSession(state="intake", provider="ado",
                                       branch="feature/x"))
    assert "Antes de pedir confirmacion, decile al operador como deshacer esto:" \
        not in temprano
    assert "azure-pipelines.yml" not in temprano
