"""Plan 283 F0 - Censo de baseline del modulo de reuniones.

Congela POR MEDICION el estado "antes", para que ninguna fase posterior pueda
declararse verde contra una foto imaginaria. Cinco de los seis casos se
INVIERTEN a medida que las fases construyen (la columna "cierra en" del plan);
el sexto es un INVARIANTE que discrimina desde F1 en adelante.

PROHIBIDO `xfail` en este plan (v2/C4): un xfail(strict=False) que pasa reporta
`xpassed`, y ningun criterio "N passed" lo cuenta.

Cabecera obligatoria: DATABASE_URL en memoria ANTES de importar nada de la app,
para no escribir en la base viva del operador (R8).
"""
from __future__ import annotations

import os
import pathlib
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
FRONTEND_SRC = BACKEND_ROOT.parent / "frontend" / "src"

# Las 5 keys que introduce F1. Se declaran UNA vez y se reusan en 3 casos.
KEYS_283 = frozenset({
    "STACKY_MEETINGS_ENABLED",
    "STACKY_MEETINGS_GRAPH_ENABLED",
    "STACKY_MEETINGS_PUBLISH_ENABLED",
    "STACKY_MEETINGS_GRAPH_TENANT",
    "STACKY_MEETINGS_GRAPH_CLIENT_ID",
})

_EXCLUDED_DIRS = {
    ".venv", "venv", "__pycache__", "node_modules", "data", "dist", "build",
    "projects", "run_state", "reports", ".git",
}


def _archivos_de_produccion() -> list[tuple[str, str]]:
    """(ruta relativa POSIX, texto) del codigo PRODUCTIVO backend + frontend.

    Excluye backend/tests/ (los tests nombran lo que auditan: contarlos seria
    un censo circular) y los directorios que no son codigo de la app.
    """
    salida: list[tuple[str, str]] = []
    for path in sorted(BACKEND_ROOT.rglob("*.py")):
        if _EXCLUDED_DIRS & set(path.parts):
            continue
        rel = path.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith("tests/"):
            continue
        salida.append((rel, path.read_text(encoding="utf-8", errors="ignore")))
    if FRONTEND_SRC.exists():
        for patron in ("*.ts", "*.tsx"):
            for path in sorted(FRONTEND_SRC.rglob(patron)):
                if _EXCLUDED_DIRS & set(path.parts) or "__tests__" in path.parts:
                    continue
                rel = "frontend/src/" + path.relative_to(FRONTEND_SRC).as_posix()
                salida.append((rel, path.read_text(encoding="utf-8", errors="ignore")))
    return salida


def test_1_codigo_graph_en_produccion():
    """Caso 1 - se INVIERTE en F4.

    Antes de F4: CERO archivos de produccion mencionan el servicio de Graph.
    Despues de F4: EXACTAMENTE uno, y es `services/graph_client.py`.
    """
    archivos = _archivos_de_produccion()
    # Guard positivo: el barrido tiene que estar leyendo algo de verdad. Sin
    # esto, un rglob roto haria pasar el assert de ausencia por lista vacia.
    assert len(archivos) > 100, f"el barrido solo vio {len(archivos)} archivos"

    ofensores = sorted(rel for rel, txt in archivos if "graph.microsoft.com" in txt)
    assert ofensores == ["services/graph_client.py"], (
        f"Se esperaba exactamente 1 archivo de produccion con el host de Graph; "
        f"hay {len(ofensores)}: {ofensores}"
    )


def test_2_tab_reuniones():
    """Caso 2 - se INVIERTE en F9. `TAB_PATHS` de routes.ts declara `reuniones`."""
    texto = (FRONTEND_SRC / "services" / "routes.ts").read_text(encoding="utf-8")
    # Guard positivo: el archivo es el que creemos (si no, todo assert es vacuo).
    assert "TAB_PATHS" in texto and "incidencias" in texto, "routes.ts no tiene la forma esperada"

    assert re.search(r"\breuniones:\s*\"/reuniones\"", texto), (
        "TAB_PATHS no declara la ruta de reuniones"
    )
    assert '"reuniones"' in texto, "el tipo Tab no incluye 'reuniones'"


def test_3_las_5_flags_del_plan():
    """Caso 3 - se INVIERTE en F1. Las 5 keys viven en FLAG_REGISTRY."""
    from services.harness_flags import FLAG_REGISTRY

    registradas = {s.key for s in FLAG_REGISTRY}
    # Guard positivo: el registro se cargo de verdad.
    assert len(registradas) > 300, f"FLAG_REGISTRY trajo solo {len(registradas)} keys"

    faltantes = sorted(KEYS_283 - registradas)
    assert faltantes == [], f"keys del plan sin registrar: {faltantes}"


def test_4_las_tablas():
    """Caso 4 - se INVIERTE en F2. `meetings` y `meeting_action_items` existen."""
    import db

    db.init_db()
    tablas = set(db.Base.metadata.tables)
    # Guard positivo: el metadata tiene las tablas de siempre.
    assert "tickets" in tablas, "init_db() no registro ni la tabla tickets"

    faltantes = sorted({"meetings", "meeting_action_items"} - tablas)
    assert faltantes == [], f"tablas del plan sin crear: {faltantes}"


def test_5_las_5_keys_en_los_congelados():
    """Caso 5 - se INVIERTE PARCIALMENTE en F1.

    Reemplaza al `test_baseline_flags_suites_verdes` del v1 (v2/C1+C17), que
    lanzaba un subproceso pytest anidado de 22 s para congelar un numero que
    otra sesion puede mover en cualquier momento. Un baseline se MIDE al
    empezar, no se hornea en un test.

    Reparto exacto tras F1:
      - `_CURATED_DEFAULTS_ON`      -> las 2 bool que nacen ON
      - `_REQUIRES_MAP_FROZEN`      -> las 4 hijas
      - `RESERVED_KEYS`             -> ninguna (todas tienen consumidor real)
      - `_EXPECTED_RESTART_REQUIRED`-> ninguna (el plan no toca app.py)
    """
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON
    from tests.test_harness_flags_requires import _REQUIRES_MAP_FROZEN
    from tests.test_harness_flags_restart_required import _EXPECTED_RESTART_REQUIRED
    from tests.test_flag_wiring import RESERVED_KEYS

    curadas = KEYS_283 & set(_CURATED_DEFAULTS_ON)
    assert curadas == {"STACKY_MEETINGS_ENABLED", "STACKY_MEETINGS_GRAPH_ENABLED"}, (
        f"solo las 2 bool ON van curadas; hay {sorted(curadas)}"
    )

    aristas = {k: v for k, v in _REQUIRES_MAP_FROZEN.items() if k in KEYS_283}
    assert aristas == {
        "STACKY_MEETINGS_GRAPH_ENABLED": "STACKY_MEETINGS_ENABLED",
        "STACKY_MEETINGS_PUBLISH_ENABLED": "STACKY_MEETINGS_ENABLED",
        "STACKY_MEETINGS_GRAPH_TENANT": "STACKY_MEETINGS_ENABLED",
        "STACKY_MEETINGS_GRAPH_CLIENT_ID": "STACKY_MEETINGS_ENABLED",
    }, f"aristas requires inesperadas: {aristas}"

    assert KEYS_283 & set(RESERVED_KEYS) == set(), "ninguna key del plan es reservada"
    assert KEYS_283 & set(_EXPECTED_RESTART_REQUIRED) == set(), (
        "el plan no toca app.py: ninguna key puede exigir reinicio"
    )


def test_6_las_5_keys_no_agravan_el_rojo_ajeno_de_ayuda():
    """Caso 6 - INVARIANTE. Discrimina desde F1: si F1 registra las 5 flags sin
    escribir su ayuda llana, este test se pone ROJO.

    `tests/test_harness_flags_help.py` ya esta rojo por ~80 flags AJENAS sin
    entrada en PLAIN_HELP. Ese rojo es de CONJUNTO: sumarle 5 entradas no sube
    el conteo de tests fallados. Por eso el criterio no es un numero sino un
    invariante sobre el CONJUNTO.
    """
    from services.harness_flags import FLAG_REGISTRY
    from services.harness_flags_help import PLAIN_HELP

    faltantes = {s.key for s in FLAG_REGISTRY} - set(PLAIN_HELP)

    # GUARD POSITIVO, PRIMERO: prueba que el calculo funciona y que el rojo
    # ajeno existe de verdad. Sin esto, el assert siguiente pasaria por
    # accidente si `faltantes` fuera vacio por un bug de lectura.
    assert len(faltantes) > 0, (
        "el rojo ajeno de la ayuda desaparecio: revisar si el calculo sigue midiendo algo"
    )

    print(f"[plan283] flags sin ayuda llana (VOLATIL, ajeno): {len(faltantes)}")

    propias = sorted(KEYS_283 & faltantes)
    assert propias == [], f"keys de este plan sin entrada en la ayuda llana: {propias}"
