"""Plan 283 F1 - Un caso por PATA de las 5 flags del modulo de reuniones.

Por que existe este archivo (v2/C1). El criterio "70 passed" de las 3 suites de
flags es de NO-REGRESION, no de cobertura: los 3 archivos iteran
`for spec in FLAG_REGISTRY` DENTRO de un unico test y no tienen ni un
`parametrize`, asi que 5 flags nuevas aportan CERO casos. Un "70 passed" con
tres patas sin hacer da exactamente el mismo numero. Este archivo es el gate que
SI discrimina: 7 casos, uno por pata.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar la app (R8).
"""
from __future__ import annotations

import os
import pathlib
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]

# key -> default EFECTIVO declarado en backend/config.py
DEFAULTS_283: dict[str, object] = {
    "STACKY_MEETINGS_ENABLED": True,
    "STACKY_MEETINGS_GRAPH_ENABLED": True,
    "STACKY_MEETINGS_PUBLISH_ENABLED": False,
    "STACKY_MEETINGS_GRAPH_TENANT": "",
    "STACKY_MEETINGS_GRAPH_CLIENT_ID": "",
}
KEYS_283 = frozenset(DEFAULTS_283)
MASTER = "STACKY_MEETINGS_ENABLED"
HIJAS = KEYS_283 - {MASTER}
BOOL_ON = {"STACKY_MEETINGS_ENABLED", "STACKY_MEETINGS_GRAPH_ENABLED"}


def test_pata_1_config_py_declara_el_default_efectivo():
    """Pata 1 - `backend/config.py` tiene el `os.getenv` con el default real."""
    import config

    # Precondicion explicita: si el operador exporto una de estas variables, lo
    # que mediriamos seria su entorno, no el codigo. Se dice, no se adivina.
    exportadas = sorted(k for k in KEYS_283 if k in os.environ)
    assert exportadas == [], (
        f"estas keys estan en el entorno y taparian el default del codigo: {exportadas}"
    )

    for key, esperado in sorted(DEFAULTS_283.items()):
        assert hasattr(config.Config, key), f"{key} no es atributo de Config"
        valor = getattr(config.Config, key)
        assert valor == esperado, f"{key}: default efectivo {valor!r}, se esperaba {esperado!r}"
        assert type(valor) is type(esperado), f"{key}: tipo {type(valor)}, se esperaba {type(esperado)}"

    # Y el literal del default esta en el fuente (no es un atributo de clase
    # calculado en otro lado): protege contra un getenv con el default cambiado.
    src = (BACKEND_ROOT / "config.py").read_text(encoding="utf-8")
    assert re.search(r'"STACKY_MEETINGS_ENABLED",\s*"true"', src)
    assert re.search(r'"STACKY_MEETINGS_GRAPH_ENABLED",\s*"true"', src)
    assert re.search(r'"STACKY_MEETINGS_PUBLISH_ENABLED",\s*"false"', src)
    assert 'os.getenv("STACKY_MEETINGS_GRAPH_TENANT", "")' in src
    assert 'os.getenv("STACKY_MEETINGS_GRAPH_CLIENT_ID", "")' in src


def test_pata_2_categorizadas_en_capacidades_optin():
    """Pata 2 - las 5 keys estan en `capacidades_optin` y ninguna cae en `otros`."""
    from services.harness_flags import _CATEGORY_KEYS, categorize

    optin = set(_CATEGORY_KEYS["capacidades_optin"])
    faltantes = sorted(KEYS_283 - optin)
    assert faltantes == [], f"keys sin categorizar en capacidades_optin: {faltantes}"

    for key in sorted(KEYS_283):
        cat = categorize(key)
        assert cat == "capacidades_optin", f"{key} cayo en la categoria {cat!r}"

    # Guard positivo: `categorize` sabe devolver "otros" de verdad. Sin esto, un
    # categorize que devolviera siempre "capacidades_optin" pasaria el assert.
    assert categorize("STACKY_MEETINGS_KEY_QUE_NO_EXISTE") == "otros"


def test_pata_3_registradas_con_tipo_y_grafo_valido():
    """Pata 3 - `FLAG_REGISTRY` + reglas R1-R4 de `validate_requires_graph`."""
    from services.harness_flags import FLAG_REGISTRY, validate_requires_graph

    specs = {s.key: s for s in FLAG_REGISTRY if s.key in KEYS_283}
    faltantes = sorted(KEYS_283 - set(specs))
    assert faltantes == [], f"keys sin FlagSpec: {faltantes}"

    for key in sorted(BOOL_ON | {"STACKY_MEETINGS_PUBLISH_ENABLED"}):
        assert specs[key].type == "bool", f"{key}: type={specs[key].type!r}"
    for key in ("STACKY_MEETINGS_GRAPH_TENANT", "STACKY_MEETINGS_GRAPH_CLIENT_ID"):
        assert specs[key].type == "str", f"{key}: type={specs[key].type!r}"

    # R4: profundidad maxima 1. Las 4 hijas cuelgan del master; el master no.
    assert specs[MASTER].requires is None, "el master NO puede declarar requires (R4)"
    for key in sorted(HIJAS):
        assert specs[key].requires == MASTER, f"{key}: requires={specs[key].requires!r}"

    # Ninguna reservada: las 5 tienen consumidor real (pata 7).
    for key in sorted(KEYS_283):
        assert specs[key].reserved is False, f"{key} quedo marcada reserved"

    assert validate_requires_graph() == [], "el grafo de requires quedo invalido"


def test_pata_4_tienen_ayuda_llana():
    """Pata 4 - cobertura en `PLAIN_HELP` (la CALIDAD la mide test_plan283_help_limpio)."""
    from services.harness_flags_help import PLAIN_HELP, plain_help_for

    faltantes = sorted(KEYS_283 - set(PLAIN_HELP))
    assert faltantes == [], f"keys sin ayuda llana: {faltantes}"

    for key in sorted(KEYS_283):
        ayuda = plain_help_for(key)
        assert ayuda is not None and set(ayuda) == {"what", "on_effect", "off_effect", "example"}

    # Guard positivo: el lookup sabe devolver None. Sin esto, un plain_help_for
    # que devolviera siempre un dict haria pasar el assert de arriba.
    assert plain_help_for("STACKY_MEETINGS_KEY_QUE_NO_EXISTE") is None


def test_pata_5_biyeccion_de_default_declarado():
    """Pata 5 - `default_is_known(spec)` es `spec.default is not None`, NO `is True`.

    Consecuencia dura y contraintuitiva: declarar `default=""` o `default=0` en
    una flag `str`/numerica la mete en `known_keys` y ROMPE
    `test_default_known_only_for_curated`, que exige igualdad de conjuntos con
    `_CURATED_DEFAULTS_ON`. Por eso las 2 `str` y la de publicacion NO declaran
    `default=` en ningun caso.
    """
    from services.harness_flags import FLAG_REGISTRY, declared_default, default_is_known
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    specs = {s.key: s for s in FLAG_REGISTRY if s.key in KEYS_283}

    conocidas = {k for k, s in specs.items() if default_is_known(s)}
    assert conocidas == BOOL_ON, (
        f"solo las 2 bool que nacen ON pueden tener default declarado; hay {sorted(conocidas)}"
    )

    # El corolario que el v1 se perdia: el predicado es `is not None`.
    for key in sorted(KEYS_283 - BOOL_ON):
        assert specs[key].default is None, f"{key} declara default={specs[key].default!r}"

    # Y el panel no miente: las 2 `str` resuelven al type-zero "" que es
    # EXACTAMENTE lo que config.py devuelve.
    for key in ("STACKY_MEETINGS_GRAPH_TENANT", "STACKY_MEETINGS_GRAPH_CLIENT_ID"):
        assert declared_default(specs[key]) == "", f"{key}: hint de UI distinto del default real"

    # La otra mitad de la biyeccion: las 2 ON estan curadas, las otras 3 no.
    assert KEYS_283 & set(_CURATED_DEFAULTS_ON) == BOOL_ON


def test_pata_6_las_4_aristas_en_el_mapa_congelado():
    """Pata 6 - `_REQUIRES_MAP_FROZEN` trae las 4 aristas, exactas."""
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN

    propias = {k: v for k, v in _REQUIRES_MAP_FROZEN.items() if k in KEYS_283}
    assert propias == {k: MASTER for k in HIJAS}, f"aristas congeladas: {propias}"
    assert MASTER not in _REQUIRES_MAP_FROZEN, "el master no puede tener arista (R4)"


def test_pata_7_consumidor_real_y_prohibicion_de_app_py():
    """Pata 7 - cada key aparece LITERAL en `config.py`, y NINGUNA en `app.py`.

    Lo segundo no es cosmetico: `test_harness_flags_restart_required.py:233-245`
    exige que toda key `STACKY_*` que aparezca como token en `app.py` declare
    `restart_required=True`. Este plan no arranca ningun daemon (D7), asi que no
    toca `app.py` y ninguna key necesita reinicio.
    """
    config_src = (BACKEND_ROOT / "config.py").read_text(encoding="utf-8")
    app_src = (BACKEND_ROOT / "app.py").read_text(encoding="utf-8")

    # GUARD POSITIVO, PRIMERO: una key inventada NO aparece. Sin esto, un lector
    # de archivo roto (o un `in` sobre una cadena vacia) haria pasar todo.
    assert "STACKY_MEETINGS_KEY_QUE_NO_EXISTE" not in config_src
    assert len(config_src) > 10_000 and len(app_src) > 10_000, "los fuentes no se leyeron"

    sin_consumidor = sorted(k for k in KEYS_283 if k not in config_src)
    assert sin_consumidor == [], f"keys sin consumidor real en config.py: {sin_consumidor}"

    en_app = sorted(k for k in KEYS_283 if k in app_src)
    assert en_app == [], (
        f"keys de este plan mencionadas en app.py: {en_app}. "
        "Exigirian restart_required=True; el plan no arranca daemons."
    )
