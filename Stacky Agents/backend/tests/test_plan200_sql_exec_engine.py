"""Plan 200 R3/R4 — Motor de ejecución SQL HITL + bitácora tamper-evident.

Ver Stacky Agents/docs/200_PLAN_CONSOLA_POR_INCIDENCIA_MARCADO_DE_DESPLIEGUE_SQL_Y_EJECUCION_HITL_POR_AMBIENTE_CON_BITACORA_DE_TRAZABILIDAD.md §F5/§F6.

Es la única capacidad del producto que ESCRIBE en una base del operador, así que
cada candado tiene su test y ninguno se prueba "por inspección": la flag apagada,
el ambiente sin opt-in, el fingerprint que no coincide, el script que cambió en
disco, la re-ejecución del mismo sha, y que el password no se filtre al mensaje
de error.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_ALIAS = "test-exec"
_PASSWORD = "s3cr3t0-del-operador"


@pytest.fixture
def fake_keyring(monkeypatch):
    import services.dbcompare_registry as reg

    store: dict = {}

    class _FakeKeyring:
        @staticmethod
        def set_password(service, alias, password):
            store[(service, alias)] = password

        @staticmethod
        def get_password(service, alias):
            return store.get((service, alias))

        @staticmethod
        def delete_password(service, alias):
            store.pop((service, alias), None)

    monkeypatch.setattr(reg, "keyring", _FakeKeyring())
    return store


@pytest.fixture
def entorno(fake_keyring, tmp_path, monkeypatch):
    """Ambiente sqlite `test-exec` con opt-in de escritura ENCENDIDO."""
    import runtime_paths
    import services.dbcompare_registry as reg
    import services.sql_exec_ledger as ledger

    monkeypatch.setattr(reg, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(ledger.runtime_paths, "data_dir", lambda: tmp_path, raising=False)

    db = tmp_path / "exec.db"
    reg.upsert_environment(_ALIAS, "sqlite", "localhost", 0, str(db), "user")
    reg.set_password(_ALIAS, _PASSWORD)
    reg.set_exec_allowed(_ALIAS, True)

    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_SQL_EXEC_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod.config, "STACKY_DB_COMPARE_ENABLED", True, raising=False)
    monkeypatch.setattr(config_mod.config, "STACKY_SQL_EXEC_LEDGER_ENABLED", True, raising=False)
    return {"db": db, "tmp_path": tmp_path}


def _correr(sql, **kwargs):
    from services import sql_exec_engine

    parametros = {
        "alias": _ALIAS,
        "sql_text": sql,
        "dry_run": False,
        "ticket_ref": None,
        "incident_id": None,
        "confirm_fingerprint": sql_exec_engine.script_fingerprint(sql),
        "executed_by": "operador",
    }
    parametros.update(kwargs)
    return sql_exec_engine.execute_script(**parametros)


def _tablas(db: Path) -> set:
    import sqlite3

    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Los 4 candados
# ---------------------------------------------------------------------------

def test_flag_off_lanza_permission(entorno, monkeypatch):
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_SQL_EXEC_ENABLED", False, raising=False)

    with pytest.raises(PermissionError, match="sql_exec_disabled"):
        _correr("CREATE TABLE t (id INTEGER)")


def test_env_no_exec_allowed_lanza(entorno):
    # Registrar un ambiente para COMPARARLO no habilita ESCRIBIRLE.
    import services.dbcompare_registry as reg

    reg.set_exec_allowed(_ALIAS, False)

    with pytest.raises(PermissionError, match="env_not_exec_allowed"):
        _correr("CREATE TABLE t (id INTEGER)")


def test_el_optin_de_escritura_arranca_apagado(entorno):
    import services.dbcompare_registry as reg

    reg.upsert_environment("test-otro", "sqlite", "localhost", 0, "x.db", "user")

    assert reg.exec_allowed("test-otro") is False


def test_editar_el_ambiente_no_revoca_el_permiso(entorno):
    # Un upsert de mantenimiento (cambiar notas) no puede apagar el opt-in en
    # silencio: el operador creería que sigue habilitado.
    import services.dbcompare_registry as reg

    reg.upsert_environment(_ALIAS, "sqlite", "localhost", 0, str(entorno["db"]), "user",
                           notes="nota nueva")

    assert reg.exec_allowed(_ALIAS) is True


def test_fingerprint_mismatch(entorno):
    with pytest.raises(ValueError, match="fingerprint_mismatch"):
        _correr("CREATE TABLE t (id INTEGER)", confirm_fingerprint="0" * 64)


# ---------------------------------------------------------------------------
# Dry-run: nunca muta
# ---------------------------------------------------------------------------

def test_dry_run_no_muta(entorno):
    res = _correr("CREATE TABLE t_dry (id INTEGER)", dry_run=True)

    assert res.dry_run is True
    assert res.statement_count == 1
    # La aserción que importa: la tabla NO existe.
    assert "t_dry" not in _tablas(entorno["db"])


def test_dry_run_previsualiza_aun_ya_ejecutado(entorno):
    sql = "CREATE TABLE t_prev (id INTEGER)"
    _correr(sql)

    res = _correr(sql, dry_run=True)

    # No lanza already_executed: previsualizar algo ya aplicado es legítimo.
    assert res.ok is True
    assert res.dry_run is True


def test_partial_effects_flag_con_ddl(entorno):
    # En Oracle/MySQL el DDL auto-commitea: prometer atomicidad ahí sería mentir.
    ddl = _correr("CREATE TABLE t_ddl (id INTEGER)", dry_run=True)
    dml = _correr("UPDATE algo SET x = 1", dry_run=True)

    assert ddl.partial_effects_possible is True
    assert dml.partial_effects_possible is False


# ---------------------------------------------------------------------------
# Ejecución real
# ---------------------------------------------------------------------------

def test_ejecucion_real_crea_y_commitea(entorno):
    import sqlite3

    res = _correr("CREATE TABLE t_real (id INTEGER); INSERT INTO t_real VALUES (1)")

    assert res.ok is True, res.error
    assert res.statement_count == 2
    # Conexión NUEVA: si no commiteó, acá no hay nada.
    con = sqlite3.connect(entorno["db"])
    try:
        assert con.execute("SELECT COUNT(*) FROM t_real").fetchone()[0] == 1
    finally:
        con.close()


def test_error_hace_rollback_y_scrub(entorno):
    import sqlite3

    _correr("CREATE TABLE t_roll (id INTEGER)")

    res = _correr("INSERT INTO t_roll VALUES (1); ESTO NO ES SQL")

    assert res.ok is False
    assert res.error
    # El password del operador jamás puede viajar en el mensaje del driver.
    assert _PASSWORD not in res.error
    # Y el DML parcial se revirtió: la fila no quedó.
    con = sqlite3.connect(entorno["db"])
    try:
        assert con.execute("SELECT COUNT(*) FROM t_roll").fetchone()[0] == 0
    finally:
        con.close()


def test_el_ddl_NO_se_revierte_y_por_eso_existe_el_aviso(entorno):
    """La atomicidad del DDL es una promesa que no se puede cumplir.

    El plan lo documenta para Oracle/MySQL (auto-commit del DDL), pero el driver
    pysqlite se comporta igual: la tabla creada por la primera sentencia queda,
    aunque la segunda falle y haya rollback.

    Este test existe para que `partial_effects_possible` no sea un adorno: si
    algún día el DDL SÍ se revirtiera, queremos enterarnos por acá y no seguir
    avisando de un riesgo inexistente.
    """
    res = _correr("CREATE TABLE t_ddl_parcial (id INTEGER); ESTO NO ES SQL")

    assert res.ok is False
    assert "t_ddl_parcial" in _tablas(entorno["db"])


def test_split_statements_false_bloque_unico(entorno):
    # PL/SQL: un BEGIN..END con `;` internos va como UN statement.
    bloque = "BEGIN\n  UPDATE x SET a = 1;\n  UPDATE y SET b = 2;\nEND;"

    res = _correr(bloque, dry_run=True, split_statements=False)

    assert res.statement_count == 1


def test_split_ignora_punto_y_coma_en_literales(entorno):
    # Un split ingenuo parte acá al medio y ejecuta basura.
    sql = "INSERT INTO t VALUES ('a;b'); INSERT INTO t VALUES ('c')"

    res = _correr(sql, dry_run=True)

    assert res.statement_count == 2


def test_split_ignora_punto_y_coma_en_comentarios(entorno):
    sql = "SELECT 1 -- ojo; esto es un comentario\n; SELECT 2"

    res = _correr(sql, dry_run=True)

    assert res.statement_count == 2


# ---------------------------------------------------------------------------
# Idempotencia y bitácora
# ---------------------------------------------------------------------------

def test_idempotencia_bloquea_sin_force(entorno):
    sql = "CREATE TABLE t_idem (id INTEGER)"
    _correr(sql)

    with pytest.raises(RuntimeError, match="already_executed"):
        _correr(sql)


def test_force_permite_reejecutar(entorno):
    sql = "CREATE TABLE t_force (id INTEGER)"
    _correr(sql)

    res = _correr(sql, force=True)

    # Vuelve a correr de verdad (falla porque la tabla ya existe, pero CORRIÓ:
    # no lo frenó la idempotencia).
    assert res.dry_run is False
    assert res.ok is False
    assert "t_force" in (res.error or "")


def test_un_fallo_no_bloquea_el_reintento(entorno):
    # Un script que falló no quedó aplicado: tratarlo como "ya ejecutado"
    # impediría corregir el ambiente y reintentar.
    sql = "INSERT INTO no_existe VALUES (1)"
    primero = _correr(sql)
    assert primero.ok is False

    segundo = _correr(sql)

    assert segundo.ok is False  # falla igual, pero NO por already_executed


def test_ledger_registra_ok_y_error(entorno):
    from services import sql_exec_ledger

    _correr("CREATE TABLE t_led (id INTEGER)")
    _correr("ESTO TAMPOCO ES SQL")

    filas = sql_exec_ledger.list_execs(alias=_ALIAS)

    assert len(filas) == 2
    assert {f["result_ok"] for f in filas} == {True, False}


def test_el_ledger_nunca_guarda_el_password(entorno):
    from services import sql_exec_ledger

    _correr("ESTO NO ES SQL")

    crudo = json.dumps(sql_exec_ledger.list_execs(alias=_ALIAS))

    assert _PASSWORD not in crudo


def test_ledger_best_effort_no_tumba(entorno, monkeypatch):
    """El efecto en la base YA ocurrió: un fallo del ledger no puede ser un 500."""
    from services import sql_exec_ledger

    def _boom(*a, **k):
        raise OSError("disco lleno")

    monkeypatch.setattr(sql_exec_ledger, "append_exec", _boom)

    res = _correr("CREATE TABLE t_bestef (id INTEGER)")

    assert res.ok is True
    # Pero no queda mudo: sin este aviso el operador re-ejecutaría a ciegas.
    assert res.ledger_write_failed is True


# ---------------------------------------------------------------------------
# F6 — cadena de hash
# ---------------------------------------------------------------------------

def test_append_y_cadena_valida(entorno):
    from services import sql_exec_ledger

    for i in range(3):
        sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": f"sha{i}", "result_ok": True})

    filas = sql_exec_ledger.list_execs(alias=_ALIAS, limit=10)

    assert len(filas) == 3
    assert all(f.get("entry_hash") for f in filas)
    assert sql_exec_ledger.verify_chain() is True


def test_tamper_detectado(entorno):
    """Editar una línea a mano tiene que NOTARSE."""
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "sha", "result_ok": True})
    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "sha2", "result_ok": True})

    ruta = sql_exec_ledger._path()
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    doc = json.loads(lineas[0])
    doc["alias"] = "PROD-mentira"
    lineas[0] = json.dumps(doc, ensure_ascii=False)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    assert sql_exec_ledger.verify_chain() is False


def test_borrar_una_linea_del_medio_tambien_se_detecta(entorno):
    from services import sql_exec_ledger

    for i in range(3):
        sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": f"s{i}", "result_ok": True})

    ruta = sql_exec_ledger._path()
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    ruta.write_text(lineas[0] + "\n" + lineas[2] + "\n", encoding="utf-8")

    assert sql_exec_ledger.verify_chain() is False


def test_solo_se_guardan_los_campos_de_la_allowlist(entorno):
    # Una clave de más en el dict de la llamada no puede terminar en el archivo.
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({
        "alias": _ALIAS, "script_sha256": "sha", "result_ok": True,
        "password": "NO-DEBE-ESTAR", "connection_string": "TAMPOCO",
    })

    crudo = sql_exec_ledger._path().read_text(encoding="utf-8")

    assert "NO-DEBE-ESTAR" not in crudo
    assert "TAMPOCO" not in crudo


def test_find_executed(entorno):
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "abc", "result_ok": True,
                                 "dry_run": False})

    assert sql_exec_ledger.find_executed(_ALIAS, "abc") is not None
    assert sql_exec_ledger.find_executed(_ALIAS, "otro") is None


def test_find_executed_ignora_dry_run_y_fallos(entorno):
    # Un dry-run no tocó nada y un fallo no quedó aplicado: ninguno de los dos
    # puede bloquear la ejecución real.
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "d", "result_ok": True,
                                 "dry_run": True})
    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "f", "result_ok": False,
                                 "dry_run": False})

    assert sql_exec_ledger.find_executed(_ALIAS, "d") is None
    assert sql_exec_ledger.find_executed(_ALIAS, "f") is None


def test_una_linea_corrupta_no_tapa_la_bitacora(entorno):
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "ok", "result_ok": True})
    ruta = sql_exec_ledger._path()
    ruta.write_text(ruta.read_text(encoding="utf-8") + "{ esto no es json\n", encoding="utf-8")

    assert len(sql_exec_ledger.list_execs(alias=_ALIAS)) == 1


# ---------------------------------------------------------------------------
# Rutas HTTP (F5 §3 / F6)
# ---------------------------------------------------------------------------

@pytest.fixture
def client(entorno, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()


def _script_en_disco(tmp_path, sql: str):
    """Un .sql servible por `ticket_output`, con su sha real."""
    import hashlib

    salida = tmp_path / "outputs"
    salida.mkdir(exist_ok=True)
    archivo = salida / "cambio.sql"
    archivo.write_text(sql, encoding="utf-8")
    sha = hashlib.sha256(archivo.read_bytes()).hexdigest()
    ref = {"source": "ticket_output", "output_dir": str(salida), "name": "cambio.sql", "sha256": sha}
    return archivo, ref, sha


def test_route_404_con_el_master_apagado(client, entorno, monkeypatch):
    # Flag OFF = la feature NO EXISTE. Un 403 confirmaría que está ahí, apagada.
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_SQL_EXEC_ENABLED", False, raising=False)

    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/execute-script", json={})

    assert resp.status_code == 404


def test_route_sin_confirm_es_400(client, entorno):
    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/execute-script",
                       json={"script_ref": {"x": 1}, "fingerprint": "abc"})

    assert resp.status_code == 400


def test_route_ejecucion_por_referencia_stale_409(client, entorno):
    """TOCTOU: el .sql cambió entre el preview y el click."""
    archivo, ref, sha = _script_en_disco(entorno["tmp_path"], "CREATE TABLE t_ruta (id INTEGER)")
    archivo.write_text("DROP TABLE algo_importante", encoding="utf-8")

    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/execute-script", json={
        "confirm": True, "script_ref": ref, "fingerprint": sha,
    })

    assert resp.status_code in (404, 409), resp.get_json()
    # El SQL alterado NO se ejecutó.
    assert "algo_importante" not in str(_tablas(entorno["db"]))


def test_route_ejecuta_y_queda_en_el_ledger(client, entorno):
    from services import sql_exec_ledger

    _archivo, ref, sha = _script_en_disco(entorno["tmp_path"], "CREATE TABLE t_ruta_ok (id INTEGER)")

    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/execute-script", json={
        "confirm": True, "script_ref": ref, "fingerprint": sha, "ticket_ref": "T-1",
    })

    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["ok"] is True
    assert "t_ruta_ok" in _tablas(entorno["db"])
    assert sql_exec_ledger.find_executed(_ALIAS, sha) is not None


def test_route_ambiente_sin_optin_es_403(client, entorno):
    import services.dbcompare_registry as reg

    reg.set_exec_allowed(_ALIAS, False)
    _archivo, ref, sha = _script_en_disco(entorno["tmp_path"], "CREATE TABLE t_no (id INTEGER)")

    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/execute-script", json={
        "confirm": True, "script_ref": ref, "fingerprint": sha,
    })

    assert resp.status_code == 403, resp.get_json()


def test_route_toggle_exec_allowed(client, entorno):
    import services.dbcompare_registry as reg

    reg.set_exec_allowed(_ALIAS, False)

    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/exec-allowed", json={"allowed": True})

    assert resp.status_code == 200
    assert reg.exec_allowed(_ALIAS) is True


def test_route_toggle_funciona_con_el_master_apagado(client, entorno, monkeypatch):
    # El operador prepara el ambiente ANTES de habilitar la capacidad.
    import config as config_mod
    import services.dbcompare_registry as reg

    monkeypatch.setattr(config_mod.config, "STACKY_SQL_EXEC_ENABLED", False, raising=False)

    resp = client.post(f"/api/db-compare/environments/{_ALIAS}/exec-allowed", json={"allowed": True})

    assert resp.status_code == 200
    assert reg.exec_allowed(_ALIAS) is True


def test_route_ledger_devuelve_chain_ok(client, entorno):
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "x", "result_ok": True})

    cuerpo = client.get("/api/db-compare/sql-exec-ledger").get_json()

    assert cuerpo["ok"] is True
    assert len(cuerpo["entries"]) == 1
    assert cuerpo["chain_ok"] is True


def test_route_ledger_avisa_si_lo_editaron(client, entorno):
    from services import sql_exec_ledger

    sql_exec_ledger.append_exec({"alias": _ALIAS, "script_sha256": "x", "result_ok": True})
    ruta = sql_exec_ledger._path()
    doc = json.loads(ruta.read_text(encoding="utf-8").splitlines()[0])
    doc["result_ok"] = False
    ruta.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")

    assert client.get("/api/db-compare/sql-exec-ledger").get_json()["chain_ok"] is False


def test_route_ledger_404_con_su_flag_apagada(client, entorno, monkeypatch):
    import config as config_mod

    monkeypatch.setattr(config_mod.config, "STACKY_SQL_EXEC_LEDGER_ENABLED", False, raising=False)

    assert client.get("/api/db-compare/sql-exec-ledger").status_code == 404
