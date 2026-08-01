"""Plan 267 F0 — Tests del contrato del catalogo de acciones DevOps.

22 tests (v4: -t19 duplicado [C40]). PUROS: no tocan flask, ni la DB, ni la red.
"""
from __future__ import annotations

import json
import pathlib

from services.devops_action_catalog import (
    DEVOPS_ACTION_CATALOG,
    DEVOPS_SECTION_IDS,
    EFFECTS,
    IMPACTS,
    MASTER_HEALTH_KEY,
    REACHES,
    assistant_actions,
    canonical_reach,
    catalog_payload,
    get_action,
    palette_actions,
    param_of,
    visible_actions,
)

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "services"
    / "devops_action_catalog.py"
)


def _all_health_on() -> dict:
    """Health sintetico con el master y TODOS los health_key del catalogo en True."""
    h = {MASTER_HEALTH_KEY: True}
    for a in DEVOPS_ACTION_CATALOG:
        if a.health_key:
            h[a.health_key] = True
    return h


def test_catalog_no_vacio_y_al_menos_23():
    assert len(DEVOPS_ACTION_CATALOG) >= 23


def test_ids_unicos():
    ids = {a.id for a in DEVOPS_ACTION_CATALOG}
    assert len(ids) == len(DEVOPS_ACTION_CATALOG)


def test_ids_con_prefijo_devops():
    for a in DEVOPS_ACTION_CATALOG:
        assert a.id.startswith("devops."), a.id
        assert a.id.count(".") == 2, a.id


def test_effect_e_impact_en_vocabulario():
    for a in DEVOPS_ACTION_CATALOG:
        assert a.effect in EFFECTS, (a.id, a.effect)
        assert a.impact in IMPACTS, (a.id, a.impact)


def test_section_id_conocida_o_none():
    for a in DEVOPS_ACTION_CATALOG:
        assert a.section_id is None or a.section_id in DEVOPS_SECTION_IDS, (
            a.id,
            a.section_id,
        )


def test_nav_path_arranca_con_slash():
    for a in DEVOPS_ACTION_CATALOG:
        assert a.nav_path.startswith("/"), (a.id, a.nav_path)


def test_todas_declaran_project():
    for a in DEVOPS_ACTION_CATALOG:
        assert param_of(a, "project") is not None, a.id


def test_params_nombres_unicos_por_accion():
    for a in DEVOPS_ACTION_CATALOG:
        names = [p.name for p in a.params]
        assert len(set(names)) == len(names), (a.id, names)


def test_enum_declara_valores():
    for a in DEVOPS_ACTION_CATALOG:
        for p in a.params:
            if p.type == "enum":
                assert len(p.enum_values) > 0, (a.id, p.name)


def test_phrases_minimo_tres():
    for a in DEVOPS_ACTION_CATALOG:
        assert len(a.phrases) >= 3, (a.id, a.phrases)


def test_get_action_desconocida_devuelve_none():
    assert get_action("nope") is None
    assert get_action("") is None
    assert get_action(None) is None  # type: ignore[arg-type]


def test_visible_actions_filtra_por_health():
    health = {MASTER_HEALTH_KEY: True, "servers_enabled": True}
    ids = {a.id for a in visible_actions(health)}
    assert "devops.servers.list" in ids
    assert "devops.logs.tail" in ids
    assert "devops.incidents.list" in ids
    assert "devops.pipeline.trigger" not in ids


def test_visible_actions_health_none():
    out = visible_actions(None)
    assert {a.id for a in out} == {"devops.logs.tail", "devops.incidents.list"}


def test_catalog_payload_serializa():
    payload = catalog_payload(_all_health_on())
    dumped = json.dumps(payload)
    assert dumped
    assert payload["version"] == "1"
    assert payload["count"] == len(payload["actions"])


def test_modulo_no_importa_flask_ni_config():
    src = _MODULE_PATH.read_text(encoding="utf-8")
    assert "import flask" not in src
    assert "from flask" not in src
    assert "import config" not in src


def test_master_apagado_deja_solo_las_de_afuera():
    """[C6] Con el panel apagado no se ofrecen acciones que navegan a la nada."""
    health = {
        MASTER_HEALTH_KEY: False,
        "servers_enabled": True,
        "trigger_enabled": True,
    }
    out = visible_actions(health)
    assert len(out) == 2, [a.id for a in out]
    assert {a.id for a in out} == {"devops.logs.tail", "devops.incidents.list"}


def test_reach_no_vacio_y_en_vocabulario():
    for a in DEVOPS_ACTION_CATALOG:
        assert a.reach, a.id
        assert set(a.reach) <= set(REACHES), (a.id, a.reach)


def test_reach_es_canonico_para_su_effect():
    """[C23] `reach` es DERIVADO. Caza a quien escriba una tupla literal."""
    for a in DEVOPS_ACTION_CATALOG:
        esperado = canonical_reach(a.effect)
        assert a.reach == esperado, (
            f"{a.id}: reach={a.reach} pero canonical_reach({a.effect!r})={esperado}"
        )


def test_todas_alcanzan_el_boton():
    for a in DEVOPS_ACTION_CATALOG:
        assert "button" in a.reach, a.id


def test_label_y_summary_no_vacios():
    """[C24] Campos obligatorios; `label` entra al ranking del matcher."""
    for a in DEVOPS_ACTION_CATALOG:
        assert a.label.strip(), a.id
        assert a.summary.strip(), a.id


def test_palette_actions_excluye_ejecucion_de_escritura():
    health = _all_health_on()
    ofrecidas = palette_actions(health)
    escrituras = {a.id for a in ofrecidas if a.effect == "write"}
    # Plan 279 [C1]: el ratchet se APRIETA de 7 a 8 (nace devops.pipeline_new.commit).
    # PROHIBIDO borrarlo, comentarlo o relajarlo a `>=`: es el guard que impide que
    # nazca una escritura fuera del conteo. tests/test_plan279_baseline.py caso 3
    # vigila que esta linea siga diciendo exactamente `== 8`.
    assert len(escrituras) == 8, sorted(escrituras)
    ejecutables = [a for a in ofrecidas if "palette-run" in a.reach]
    assert [a.id for a in ejecutables if a.effect == "write"] == []


def test_assistant_actions_es_el_universo_del_matcher():
    health = _all_health_on()
    assert len(assistant_actions(health)) == len(DEVOPS_ACTION_CATALOG)
    # canonical_reach NUNCA lanza, ni con un effect fuera de vocabulario.
    for effect in ("read", "write", "algo-raro", ""):
        out = canonical_reach(effect)
        assert isinstance(out, tuple) and out
