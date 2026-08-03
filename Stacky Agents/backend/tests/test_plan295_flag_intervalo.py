"""Plan 295 F10 — el intervalo de auto-sync pasa a ser del operador.

POR QUÉ. El plan 292 MIDIÓ que subir el intervalo de 45 s a 180 s baja el tráfico
contra el GitLab del operador un 75 %. Aplicar esa recomendación exigía editar
`frontend/src/hooks/useTicketSync.ts:40` y RECOMPILAR el frontend.

Y era una PERILLA FANTASMA: `api/tickets.py` publicaba `ticket_sync_interval_ms`
en `/api/tickets/config/frontend` leyéndolo de `os.environ` -- nunca de
`config.config` --, así que el panel de flags no podía moverla, y del otro lado
NINGÚN consumidor leía el valor publicado.

Este archivo NACE VERDE, y eso importa: dos de los seis guardianes de una flag
numérica viven en archivos ROJOS DE FÁBRICA (`test_harness_flags_bounds.py` 1F/17P
y `test_harness_flags_help.py` 4F/4P). Un criterio de CONTEO sobre ellos sale IGUAL
con el cableado puesto y sin él. Por eso el caso 8 los asertá por CONTENIDO acá.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

KEY = "STACKY_TICKET_SYNC_INTERVAL_MS"
BOUNDS = (5000, 3600000)


def _spec():
    from services.harness_flags import FLAG_REGISTRY

    return next((s for s in FLAG_REGISTRY if s.key == KEY), None)


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan295.db'}")
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path))

    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


# ------------------------------------------------------------------ casos ---
def test_1_la_flag_esta_registrada():
    from services.harness_flags import FLAG_REGISTRY

    assert KEY in {s.key for s in FLAG_REGISTRY}, (
        f"{KEY} no está en FLAG_REGISTRY ({len(FLAG_REGISTRY)} specs)"
    )


def test_2_es_int_con_los_bounds_declarados():
    spec = _spec()
    assert spec is not None
    assert spec.type == "int"
    assert (spec.min_value, spec.max_value) == BOUNDS


def test_3_NO_declara_default_la_regla_dura_de_las_numericas():
    """`default_is_known(spec)` es literalmente `spec.default is not None`.
    Declararlo metería esta key en el conjunto que test_default_known_only_for_curated
    exige que sea EXACTAMENTE _CURATED_DEFAULTS_ON, que es sólo para booleanas ON."""
    assert _spec().default is None


def test_4_esta_categorizada_y_en_la_categoria_REAL():
    """[v2, C2] `_CATEGORY_KEYS["global"]` NO EXISTE: hay 20 categorías y ninguna se
    llama así. La del 292 vive en `paridad_proveedores`. El `group="global"` de la
    FlagSpec es OTRO campo (433 specs lo usan) y ahí sí es válido."""
    from services.harness_flags import _CATEGORY_KEYS, categorize

    assert "global" not in _CATEGORY_KEYS, "si esto falla, la premisa de C2 cambió"
    assert KEY in _CATEGORY_KEYS["paridad_proveedores"]
    assert categorize(KEY) != "otros", "cayó en el fallback de categorize()"


def test_5_tiene_plain_help_con_los_cuatro_campos():
    from services.harness_flags_help import plain_help_for

    d = plain_help_for(KEY)
    assert isinstance(d, dict) and d, f"plain_help_for({KEY}) devolvió {d!r}"
    assert all(str(v).strip() for v in d.values()), d


def test_6_flag_en_180000_llega_al_endpoint(cliente, monkeypatch):
    import config as _config

    monkeypatch.setattr(_config.config, KEY, 180000, raising=False)
    data = cliente.get("/api/tickets/config/frontend").get_json()
    assert data["ticket_sync_interval_ms"] == 180000


def test_7_el_endpoint_YA_NO_lee_os_environ(cliente, monkeypatch):
    """EL caso que prueba la fase. Los 1-5 prueban el registro y el 6 la lectura;
    este prueba que la VIEJA fuente dejó de mandar. Sin él, un endpoint que leyera
    las dos fuentes pasaría el 6 igual."""
    import config as _config

    monkeypatch.setenv(KEY, "999")
    monkeypatch.setattr(_config.config, KEY, 180000, raising=False)
    data = cliente.get("/api/tickets/config/frontend").get_json()
    assert data["ticket_sync_interval_ms"] == 180000, (
        "el endpoint sigue leyendo el ENTORNO: la perilla es inmovible desde el panel"
    )


def test_8_los_seis_guardianes_de_la_flag_numerica():
    """[ADICIÓN ARQUITECTO 2 — Plan 295 F10] Los SEIS guardianes de una flag
    numérica, asertados por CONTENIDO en un archivo VERDE.

    POR QUÉ NO ALCANZA CON "correr los guardianes y pedir delta cero":
    test_harness_flags_bounds.py está ROJO DE FÁBRICA (1 failed, 17 passed: le
    faltan numéricas del plan 284 a _FROZEN_BOUNDS) y test_harness_flags_help.py
    también (4 failed, 4 passed). Un criterio de CONTEO sobre un archivo rojo no
    discrimina: sale igual con la entrada y sin ella. Este caso sí.

    Es reutilizable tal cual por la próxima flag numérica: cambiá KEY y BOUNDS.
    """
    from services.harness_flags import _CATEGORY_KEYS, categorize
    from services.harness_flags_help import PLAIN_HELP
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    from tests.test_harness_flags_bounds import _FROZEN_BOUNDS
    import config as _config

    spec = _spec()

    # G1 — el valor efectivo vive en config.py y conserva el 45000 histórico.
    assert getattr(_config.config, KEY, None) == 45000, "G1 config.py"

    # G2 — la FlagSpec existe, es int, con bounds, escribible y SIN default=.
    assert spec is not None, "G2 FlagSpec ausente"
    assert spec.type == "int" and (spec.min_value, spec.max_value) == BOUNDS, "G2 tipo/bounds"
    assert spec.env_only is False, "G2 env_only=True la dejaría fuera del panel"
    assert spec.default is None, "G2 una numérica NO declara default= (ver G6)"
    assert spec.requires is None, "G2 sin requires => no toca _REQUIRES_MAP_FROZEN"

    # G3 — categorizada, y en la categoría REAL (NO existe _CATEGORY_KEYS["global"]).
    assert KEY in _CATEGORY_KEYS["paridad_proveedores"], "G3 categoría"
    assert categorize(KEY) != "otros", "G3 cayó en el fallback"

    # G4 — PLAIN_HELP escrito A MANO (no se deriva de description), 4 campos llenos.
    assert KEY in PLAIN_HELP, "G4 PLAIN_HELP ausente"
    ayuda = PLAIN_HELP[KEY]
    for campo in ("what", "on_effect", "off_effect", "example"):
        assert str(getattr(ayuda, campo, "")).strip(), f"G4 PlainHelp.{campo} vacío"

    # G5 — _FROZEN_BOUNDS. ESTE es el que el archivo rojo NO puede vigilar.
    assert _FROZEN_BOUNDS.get(KEY) == BOUNDS, (
        f"G5 _FROZEN_BOUNDS[{KEY}] = {_FROZEN_BOUNDS.get(KEY)!r}, se esperaba {BOUNDS}. "
        "test_bounds_map_is_frozen NO puede avisarte: ya está rojo por el plan 284."
    )

    # G6 — _CURATED_DEFAULTS_ON es SOLO para booleanas ON: la numérica NO va.
    assert KEY not in _CURATED_DEFAULTS_ON, (
        "G6 una numérica en _CURATED_DEFAULTS_ON pone rojo "
        "test_default_known_only_for_curated"
    )
