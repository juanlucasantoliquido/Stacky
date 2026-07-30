"""
test_plan274_data_cache_wired.py — Plan 274 F6.

Conecta `test_data_cache.py` (huerfano #8): dejar de re-ejecutar el mismo SELECT
contra la BD del operador en cada corrida cuando el dato no cambio.

CONTEXTO REAL, PARA NO SOBRE-DISEÑAR: la resolucion de datos por SQL YA esta
cableada y funciona (`data_resolver.resolve_fields()` corre SELECT via sqlcmd,
con whitelist de tablas en `sql_query_guard.py`). No hay que construir el camino
SQL: existe. El gap es que su resultado se tira.

CACHE-ASIDE POR CAMPO, no por hash de query: `_entry_file(field)` escribe UN
ARCHIVO POR CAMPO y `get_data`/`store_data`/`invalidate` toman `field: str`. Una
clave agregada (hash de tabla+columnas+filtros) rompe `invalidate(field)`, impide
reusar los N-1 campos ya resueltos cuando uno cambia, y tira la metadata
`source`/`notes` que el modulo ya persiste.

Todo con doble de `_run_sqlcmd`: NINGUN test toca la BD.
"""
from __future__ import annotations

from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _aislar_cache(tmp_path, monkeypatch):
    """Cada test con su propio directorio de cache: cero contaminacion cruzada."""
    import test_data_cache
    monkeypatch.setattr(test_data_cache, "_CACHE_DIR", tmp_path / "cache")
    test_data_cache._CACHE_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("QA_UAT_FORCE_RUN", raising=False)
    monkeypatch.setenv("STACKY_QA_UAT_DATA_CACHE_ENABLED", "true")
    # Nombres REALES que lee _get_db_creds (data_resolver.py:492-497). Sin los
    # tres, `db_available` es False y el loop ni llega a _run_sqlcmd: el test
    # mediria otra cosa y daria un falso rojo.
    monkeypatch.setenv("RS_QA_DB_SERVER", "srv")
    monkeypatch.setenv("RS_QA_DB_USER", "usr")
    monkeypatch.setenv("RS_QA_DB_PASS", "pwd")


@pytest.fixture()
def sqlcmd(monkeypatch):
    """Doble de _run_sqlcmd que cuenta invocaciones. Devuelve (value, error)."""
    llamadas = []
    estado = {"value": "42", "error": None}

    def _fake(query, server, user, pwd):
        llamadas.append(query)
        return estado["value"], estado["error"]

    import data_resolver
    monkeypatch.setattr(data_resolver, "_run_sqlcmd", _fake)
    return llamadas, estado


def _resolver(campos: list[str]):
    import data_resolver
    return data_resolver.resolve_fields(
        # RCLIE esta en la whitelist de sql_query_guard; una tabla fuera de la
        # whitelist se bloquea ANTES de llegar a _run_sqlcmd y el test medieria
        # otra cosa.
        [{"field": c, "hint_query": f"SELECT TOP 1 {c} FROM RCLIE"} for c in campos],
        verbose=False)


def test_la_api_del_modulo_es_la_que_creemos():
    """CENTINELA ANTI-AttributeError: el v1 llamaba `put_data`, que NO EXISTE."""
    import test_data_cache
    assert hasattr(test_data_cache, "store_data") is True
    assert hasattr(test_data_cache, "put_data") is False, (
        "el modulo NO tiene put_data; la API real es store_data(field, value, "
        "source=, notes=, ttl_hours=)")
    assert hasattr(test_data_cache, "get_data") is True
    assert test_data_cache._DEFAULT_TTL_HOURS == 8, (
        "el TTL sale del modulo (8 h), no se inventa uno nuevo")


def test_segunda_llamada_no_toca_sqlcmd(sqlcmd):
    llamadas, _ = sqlcmd
    _resolver(["CLCOD"])
    assert len(llamadas) == 1
    _resolver(["CLCOD"])
    assert len(llamadas) == 1, (
        f"la segunda resolucion del mismo campo volvio a la BD ({len(llamadas)} "
        "invocaciones); el cache no esta conectado")


def test_cachea_por_campo_no_por_query(sqlcmd):
    """DISCRIMINA el diseño del v1 (clave agregada) del correcto (por campo)."""
    llamadas, _ = sqlcmd
    _resolver(["CLCOD", "EMCOD"])
    assert len(llamadas) == 2
    _resolver(["EMCOD"])
    assert len(llamadas) == 2, (
        "pedir SOLO el segundo campo volvio a consultar: con clave agregada "
        "habria 1 invocacion nueva; cacheando por campo tiene que haber 0")


def test_force_run_ignora_el_cache(sqlcmd, monkeypatch):
    llamadas, _ = sqlcmd
    _resolver(["CLCOD"])
    monkeypatch.setenv("QA_UAT_FORCE_RUN", "true")
    _resolver(["CLCOD"])
    assert len(llamadas) == 2, (
        "QA_UAT_FORCE_RUN=true tiene que saltar el cache (test_data_cache.py:72)")


def test_flag_off_no_cachea(sqlcmd, monkeypatch):
    llamadas, _ = sqlcmd
    monkeypatch.setenv("STACKY_QA_UAT_DATA_CACHE_ENABLED", "false")
    _resolver(["CLCOD"])
    _resolver(["CLCOD"])
    assert len(llamadas) == 2, "con la flag OFF no se puede cachear nada"


def test_cache_roto_no_rompe(sqlcmd, monkeypatch):
    """Un cache roto NUNCA debe romper una resolucion que funcionaba."""
    llamadas, _ = sqlcmd
    import test_data_cache

    def _boom(field):
        raise RuntimeError("JSON corrupto")

    monkeypatch.setattr(test_data_cache, "get_data", _boom)
    res = _resolver(["CLCOD"])
    assert len(llamadas) == 1, "se resolvio igual por SQL"
    assert res.resolved.get("CLCOD") == "42"


def test_resultado_vacio_no_se_cachea(sqlcmd):
    """Cachear un 'no encontre' 8 h esconderia un dato que aparecio despues."""
    llamadas, estado = sqlcmd
    estado["value"] = None
    _resolver(["CLCOD"])
    _resolver(["CLCOD"])
    assert len(llamadas) == 2, "un resultado vacio no se puede cachear"


def test_error_de_sql_no_se_cachea(sqlcmd):
    """Cachear un error 8 h esconde una BD caida."""
    llamadas, estado = sqlcmd
    estado["error"] = "Login failed for user"
    _resolver(["CLCOD"])
    _resolver(["CLCOD"])
    assert len(llamadas) == 2, "un error de SQL no se puede cachear"
