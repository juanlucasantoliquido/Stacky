"""Plan 267 F2 — Tests del matcher determinista. 15 casos.

Todos los casos corren contra DEVOPS_ACTION_CATALOG **completo** (las 23 acciones
con sus 23 listas de `phrases` literales de F0), no contra un subconjunto: es la
unica forma de que el ranking sea el real.
"""
from __future__ import annotations

import pathlib

from services.devops_action_catalog import (
    DEVOPS_ACTION_CATALOG,
    DevOpsAction,
    canonical_reach,
)
from services.devops_action_matcher import (
    MAX_MATCHES,
    ActionMatch,
    is_ambiguous,
    match_intent,
    normalize_text,
)

CAT = list(DEVOPS_ACTION_CATALOG)

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "services"
    / "devops_action_matcher.py"
)


def _fake(action_id: str, phrases: tuple[str, ...]) -> DevOpsAction:
    return DevOpsAction(
        id=action_id, label=action_id, summary="s", section_id=None,
        nav_path="/x", effect="read", impact="none", targets_environment=False,
        health_key="", flag_key="", reach=canonical_reach("read"),
        params=(), phrases=phrases,
    )


def test_normalize_quita_acentos_y_puntuacion():
    assert normalize_text("¿Disparar la Pipeline?") == "disparar la pipeline"


def test_normalize_none_y_vacio():
    assert normalize_text(None) == ""
    assert normalize_text("   ") == ""


def test_match_frase_exacta():
    m = match_intent("disparar la pipeline", CAT)
    assert m, "sin matches"
    assert m[0].action_id == "devops.pipeline.trigger", m[0]
    assert m[0].score == 1.0, m[0].score


def test_typo_no_matchea():
    """[C2] Era ROJO el dia 1 con el _phrase_score del v1 (daba 0.667)."""
    assert match_intent("Quiero DISPARAR la píplain", CAT) == []


def test_frase_con_ruido_si_matchea():
    m = match_intent("Quiero disparar la pipeline de QA", CAT)
    assert m[0].action_id == "devops.pipeline.trigger", m[0]


def test_match_parcial_supera_umbral():
    m = match_intent("ver los logs", CAT)
    assert m[0].action_id == "devops.logs.tail", m[0]


def test_lectura_y_escritura_no_se_confunden():
    hist = match_intent("historial de despliegues", CAT)
    assert hist[0].action_id == "devops.deployments.history", hist[0]
    assert "devops.deployment.execute" not in {x.action_id for x in hist}

    exe = match_intent("hacer el despliegue", CAT)
    assert exe[0].action_id == "devops.deployment.execute", exe[0]
    assert "devops.deployments.history" not in {x.action_id for x in exe}


def test_sin_match_devuelve_vacio():
    assert match_intent("receta de milanesas", CAT) == []


def test_texto_vacio_devuelve_vacio():
    assert match_intent("", CAT) == []
    assert match_intent(None, CAT) == []


def test_solo_stopwords_devuelve_vacio():
    """Sin tokens de contenido no hay match: hits/len(tokens) nunca divide por 0."""
    assert match_intent("quiero que me des el la de", CAT) == []


def test_orden_estable_ante_empate():
    a = _fake("devops.zzz.uno", ("frase compartida exacta",))
    b = _fake("devops.zzz.dos", ("frase compartida exacta",))
    salidas = []
    for _ in range(5):
        m = match_intent("frase compartida exacta", [a, b])
        salidas.append([x.action_id for x in m])
    assert all(s == salidas[0] for s in salidas), salidas
    assert salidas[0][0] == "devops.zzz.uno", salidas[0]


def test_tope_de_tres_matches():
    muchos = [_fake(f"devops.zzz.n{i}", ("frase compartida exacta",)) for i in range(8)]
    assert len(match_intent("frase compartida exacta", muchos)) == MAX_MATCHES == 3


def test_is_ambiguous_true_y_false():
    m = [ActionMatch("a", 0.90, "x"), ActionMatch("b", 0.85, "y")]
    assert is_ambiguous(m) is True
    m2 = [ActionMatch("a", 0.90, "x"), ActionMatch("b", 0.60, "y")]
    assert is_ambiguous(m2) is False
    assert is_ambiguous([ActionMatch("a", 1.0, "x")]) is False
    assert is_ambiguous([]) is False


def test_no_importa_flask_ni_red():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    assert "requests" not in src
    assert "flask" not in src
    assert "urllib" not in src


def test_score_acotado():
    """Universo determinista: las 23 acciones x cada phrase x cada phrase
    truncada a su primera palabra. Nada de "200 frases generadas" [v1]."""
    from services.devops_action_matcher import _phrase_score

    for a in DEVOPS_ACTION_CATALOG:
        for ph in (*a.phrases, a.label):
            for texto in (ph, ph.split(" ")[0]):
                s = _phrase_score(normalize_text(texto), ph)
                assert 0.0 <= s <= 1.0, (a.id, ph, texto, s)
