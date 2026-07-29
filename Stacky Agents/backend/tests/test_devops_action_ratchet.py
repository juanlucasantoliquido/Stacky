"""Plan 267 F8 — Ratchet anti-deriva del catalogo de acciones DevOps.

13 tests (v4: -t14, duplicado exacto del t17b de F0 [C40]).

Reglas ESTRUCTURALES sobre el catalogo: no puede nacer una accion DevOps mal
declarada, ni una escritura sin flag, ni una seccion que el frontend tenga y el
catalogo no.
"""
from __future__ import annotations

import pathlib
import re

from services.devops_action_catalog import DEVOPS_ACTION_CATALOG, DEVOPS_SECTION_IDS
from services.devops_action_matcher import _content_tokens, normalize_text

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_DEVOPS_PAGE = (
    _BACKEND.parent / "frontend" / "src" / "pages" / "DevOpsPage.tsx"
)

_WRITES = tuple(a for a in DEVOPS_ACTION_CATALOG if a.effect == "write")
_READS = tuple(a for a in DEVOPS_ACTION_CATALOG if a.effect == "read")


def test_write_declara_impacto():
    for a in _WRITES:
        assert a.impact != "none", a.id


def test_targets_environment_exige_param_environment():
    for a in DEVOPS_ACTION_CATALOG:
        if not a.targets_environment:
            continue
        env = next((p for p in a.params if p.name == "environment"), None)
        assert env is not None, a.id
        assert env.type == "enum", (a.id, env.type)
        assert env.required is True, a.id
        assert env.enum_values, a.id


def test_environment_implica_targets():
    for a in DEVOPS_ACTION_CATALOG:
        if any(p.name == "environment" for p in a.params):
            assert a.targets_environment is True, a.id


def test_read_no_tiene_impacto_alto():
    for a in _READS:
        assert a.impact == "none", (a.id, a.impact)


def test_write_tiene_flag_key():
    """Nada que escriba puede quedar sin flag que lo gatee."""
    for a in _WRITES:
        assert a.flag_key != "", a.id


def test_health_key_existe_en_health_payload():
    from api.devops import _health_payload

    keys = set(_health_payload().keys())
    for a in DEVOPS_ACTION_CATALOG:
        if a.health_key:
            assert a.health_key in keys, (a.id, a.health_key)


def test_flag_key_existe_en_el_registro():
    from services.harness_flags import FLAG_REGISTRY

    registradas = {s.key for s in FLAG_REGISTRY}
    for a in DEVOPS_ACTION_CATALOG:
        if a.flag_key:
            assert a.flag_key in registradas, (a.id, a.flag_key)


def test_section_ids_espejan_el_tsx():
    """Guarda contra el drift mas caro: una seccion nueva en el .tsx que el
    catalogo no declara."""
    assert _DEVOPS_PAGE.exists(), f"no existe {_DEVOPS_PAGE}"
    src = _DEVOPS_PAGE.read_text(encoding="utf-8")
    ids = set(re.findall(r"^\s*id: '([a-z0-9-]+)',", src, re.M))
    assert ids, "la regex de ids dejo de matchear: falso verde evitado"
    assert ids == set(DEVOPS_SECTION_IDS), {
        "solo_en_tsx": sorted(ids - set(DEVOPS_SECTION_IDS)),
        "solo_en_catalogo": sorted(set(DEVOPS_SECTION_IDS) - ids),
    }


def test_nav_path_de_seccion_es_devops_slug():
    for a in DEVOPS_ACTION_CATALOG:
        if a.section_id is not None:
            assert a.nav_path == f"/devops/{a.section_id}", (a.id, a.nav_path)


def test_ninguna_accion_escribe_sin_confirmacion_posible():
    """La tarjeta necesita el `summary` para explicar que va a pasar."""
    for a in _WRITES:
        assert a.summary.strip(), a.id


def test_write_no_es_ejecutable_desde_la_paleta():
    """I-REACH / KPI-9. El mensaje LISTA los ids ofensores por nombre."""
    ofensores = sorted(a.id for a in _WRITES if "palette-run" in a.reach)
    assert not ofensores, (
        "estas acciones de ESCRITURA quedaron ejecutables desde la paleta "
        f"global (a un fuzzy-match + Enter de distancia): {ofensores}"
    )


def test_frases_no_colisionan_entre_read_y_write():
    """[C3 + C24] La superficie protegida es la MISMA que la evaluada: el
    matcher puntua (*phrases, label), asi que el guard mira los dos."""
    def universo(a):
        return tuple((*a.phrases, a.label))

    choques = []
    for r in _READS:
        for w in _WRITES:
            for pr in universo(r):
                tr = set(_content_tokens(normalize_text(pr)))
                if not tr:
                    continue
                for pw in universo(w):
                    tw = set(_content_tokens(normalize_text(pw)))
                    if not tw:
                        continue
                    if tr <= tw or tw <= tr:
                        choques.append((r.id, pr, w.id, pw))
    assert not choques, f"colisiones read/write: {choques}"


def test_reach_incluye_button_siempre():
    """Guardarrail de "sin eliminar la posibilidad de hacerlo manualmente"."""
    for a in DEVOPS_ACTION_CATALOG:
        assert "button" in a.reach, a.id
