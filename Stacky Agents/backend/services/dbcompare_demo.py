"""Plan 183 — Sandbox de demostración del comparador (par sqlite RS-like).

Usa el carril sqlite `test-*` YA existente (dbcompare_registry.py:80-89, cuyo
mensaje dice literal "(reservado a tests/demo)") — CERO cambios al motor.
Seed y delete son SIEMPRE por click del operador (HITL). El DDL/filas viven
en este módulo como código (nada empaquetado — apto PyInstaller).

Credencial (fix C1 v2): open_engine exige get_credential != None
(dbcompare_engine.py:88-94; dbcompare_registry.py:210,216-217) — el seed
guarda una password dummy "demo" en keyring (jamás usada en la URL sqlite,
dbcompare_engine.py:74), igual que el fixture del 122
(tests/test_plan122_dbcompare_snapshot.py:66).
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from runtime_paths import data_dir
from services import dbcompare_registry

DEMO_ALIAS_PREFIX = "test-demo-"
DEMO_DEV_ALIAS = "test-demo-dev"
DEMO_TEST_ALIAS = "test-demo-test"
DEMO_DUMMY_PASSWORD = "demo"
_DEMO_DIRNAME = "db_compare/demo"

# §4.2 lado ORIGEN (demo_dev.db) — orden literal, una sentencia por string.
_DEV_STATEMENTS: tuple[str, ...] = (
    "CREATE TABLE RPARAM (CLAVE TEXT NOT NULL PRIMARY KEY, VALOR TEXT NOT NULL, SCOPE TEXT NOT NULL DEFAULT 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('CONN_LEGACY', 'Server=db01;Password=demo123;', 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('MAX_REINTENTOS', '5', 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('MONEDA_DEFECTO', 'PEN', 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('TIMEOUT_SESION', '30', 'GLOBAL')",
    "CREATE TABLE RIDIOMA (CODIGO TEXT NOT NULL, IDIOMA TEXT NOT NULL, TEXTO TEXT NOT NULL, MODULO TEXT, PRIMARY KEY (CODIGO, IDIOMA))",
    "INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO, MODULO) VALUES ('MSG_BIENVENIDA', 'EN', 'Welcome', 'COBRANZA')",
    "INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO, MODULO) VALUES ('MSG_BIENVENIDA', 'ES', 'Bienvenido', 'COBRANZA')",
    "CREATE TABLE RTABL (ID INTEGER NOT NULL PRIMARY KEY, DESCRIPCION TEXT NOT NULL, ACTIVO INTEGER DEFAULT 1, MONTO_TOPE NUMERIC(10,2))",
    "INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (1, 'ESTADOS_COBRANZA', 1, 1000.50)",
    "INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (2, 'TIPOS_MONEDA', 1, 99.99)",
    "CREATE INDEX IX_RTABL_DESCRIPCION ON RTABL (DESCRIPCION)",
    "CREATE TABLE RESTILO (ID INTEGER NOT NULL PRIMARY KEY, COLOR TEXT DEFAULT 'AZUL')",
    "INSERT INTO RESTILO (ID, COLOR) VALUES (1, 'AZUL')",
    "CREATE TABLE RCREDENCIAL (ID INTEGER NOT NULL PRIMARY KEY, USUARIO TEXT NOT NULL, PASSWORD TEXT)",
    "INSERT INTO RCREDENCIAL (ID, USUARIO, PASSWORD) VALUES (1, 'svc_batch', 'hunter2-dev')",
    "CREATE TABLE RLOG (FECHA TEXT, MENSAJE TEXT)",
    "INSERT INTO RLOG (FECHA, MENSAJE) VALUES ('2026-01-01', 'arranque')",
    "CREATE TABLE RSOLO_DEV (ID INTEGER NOT NULL PRIMARY KEY, NOMBRE TEXT)",
    "CREATE VIEW VRESUMEN AS SELECT CLAVE, VALOR FROM RPARAM",
)

# §4.2 lado DESTINO (demo_test.db) — el que "driftea", orden literal.
_TEST_STATEMENTS: tuple[str, ...] = (
    "CREATE TABLE RPARAM (CLAVE TEXT NOT NULL PRIMARY KEY, VALOR TEXT NOT NULL, SCOPE TEXT NOT NULL DEFAULT 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('CONN_LEGACY', 'Server=db02;Password=demo456;', 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('MONEDA_DEFECTO', 'USD', 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('PARAM_HUERFANO', '1', 'GLOBAL')",
    "INSERT INTO RPARAM (CLAVE, VALOR, SCOPE) VALUES ('TIMEOUT_SESION', '30', 'GLOBAL')",
    "CREATE TABLE RIDIOMA (CODIGO TEXT NOT NULL, IDIOMA TEXT NOT NULL, TEXTO TEXT NOT NULL, PRIMARY KEY (CODIGO, IDIOMA))",
    "INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO) VALUES ('MSG_BIENVENIDA', 'EN', 'Welcome')",
    "INSERT INTO RIDIOMA (CODIGO, IDIOMA, TEXTO) VALUES ('MSG_BIENVENIDA', 'ES', 'Bienvenido')",
    "CREATE TABLE RTABL (ID INTEGER NOT NULL PRIMARY KEY, DESCRIPCION TEXT, ACTIVO INTEGER DEFAULT 0, MONTO_TOPE NUMERIC(10,2))",
    "INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (1, 'ESTADOS_COBRANZA', 1, 1000.50)",
    "INSERT INTO RTABL (ID, DESCRIPCION, ACTIVO, MONTO_TOPE) VALUES (2, 'TIPOS_MONEDA', 1, 99.99)",
    "CREATE TABLE RESTILO (ID INTEGER NOT NULL PRIMARY KEY, COLOR TEXT DEFAULT 'ROJO')",
    "INSERT INTO RESTILO (ID, COLOR) VALUES (1, 'AZUL')",
    "CREATE TABLE RCREDENCIAL (ID INTEGER NOT NULL PRIMARY KEY, USUARIO TEXT NOT NULL, PASSWORD TEXT)",
    "INSERT INTO RCREDENCIAL (ID, USUARIO, PASSWORD) VALUES (1, 'svc_batch', 'hunter2-test')",
    "CREATE TABLE RLOG (FECHA TEXT, MENSAJE TEXT)",
    "INSERT INTO RLOG (FECHA, MENSAJE) VALUES ('2026-01-01', 'arranque')",
    "CREATE TABLE RSOLO_TEST (ID INTEGER NOT NULL PRIMARY KEY, NOMBRE TEXT)",
    "CREATE VIEW VRESUMEN AS SELECT CLAVE, VALOR, SCOPE FROM RPARAM",
)


def _demo_dir() -> Path:
    d = data_dir() / _DEMO_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_demo_db(path: Path, statements: tuple[str, ...]) -> None:
    tmp = path.with_suffix(".db.tmp")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    try:
        for stmt in statements:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()
    os.replace(str(tmp), str(path))


def _alias_is_foreign(alias: str, demo_root: Path) -> bool:
    """Fix C4: True si el alias existe y su database apunta FUERA del sandbox."""
    env = dbcompare_registry.get_environment(alias)
    if env is None:
        return False
    try:
        return not Path(str(env.get("database") or "")).resolve().is_relative_to(
            demo_root.resolve()
        )
    except (OSError, ValueError):
        return True


def seed_demo_environments() -> dict:
    """Idempotente: SIEMPRE recrea desde cero (archivos por tmp+os.replace,
    registro por upsert, password dummy por set_password). Orden: guards →
    archivos → registro → password (§9.2). Una interrupción deja estados
    detectables por demo_status() y el próximo seed repara."""
    if not dbcompare_registry.keyring_available():
        raise RuntimeError(
            "keyring no disponible: el sandbox necesita guardar una credencial "
            "dummy (mismo requisito que cualquier ambiente)."
        )
    demo_root = _demo_dir()
    for alias in (DEMO_DEV_ALIAS, DEMO_TEST_ALIAS):
        if _alias_is_foreign(alias, demo_root):
            raise ValueError(
                f"el alias '{alias}' está ocupado por un ambiente ajeno al sandbox; "
                "renombralo o borralo antes de sembrar."
            )
    dev_path = demo_root / "demo_dev.db"
    test_path = demo_root / "demo_test.db"
    _write_demo_db(dev_path, _DEV_STATEMENTS)
    _write_demo_db(test_path, _TEST_STATEMENTS)
    for alias, path in ((DEMO_DEV_ALIAS, dev_path), (DEMO_TEST_ALIAS, test_path)):
        dbcompare_registry.upsert_environment(
            alias=alias,
            engine="sqlite",
            host="",
            port=None,
            database=str(path),
            username="demo",
            notes="Ambiente de demostración de Stacky (plan 183). Quitable con 'Quitar demo'.",
        )
        dbcompare_registry.set_password(alias, DEMO_DUMMY_PASSWORD)  # fix C1
    return {
        "aliases": [DEMO_DEV_ALIAS, DEMO_TEST_ALIAS],
        "paths": [str(dev_path), str(test_path)],
    }


def demo_status() -> dict:
    envs = {e["alias"] for e in dbcompare_registry.list_environments()}
    dev_file = data_dir() / _DEMO_DIRNAME / "demo_dev.db"
    test_file = data_dir() / _DEMO_DIRNAME / "demo_test.db"
    from services import dbcompare_runs

    demo_runs = [
        r["run_id"]
        for r in dbcompare_runs.list_runs(200)
        if str(r.get("source_alias", "")).startswith(DEMO_ALIAS_PREFIX)
        or str(r.get("target_alias", "")).startswith(DEMO_ALIAS_PREFIX)
    ]
    return {
        "registered": DEMO_DEV_ALIAS in envs and DEMO_TEST_ALIAS in envs,
        "files_present": dev_file.exists() and test_file.exists(),
        "aliases": [DEMO_DEV_ALIAS, DEMO_TEST_ALIAS],
        "run_count": len(demo_runs),
    }


def delete_demo() -> dict:
    """Guard doble (§3.1): (1) desregistra SOLO aliases test-demo-*; (2) borra
    SOLO data_dir()/db_compare/demo/ tras verificar contención canónica. El
    rmtree es tolerante a locks de Windows (fix C3): reporta error sin 500 y
    queda re-ejecutable."""
    removed_aliases = []
    for env in dbcompare_registry.list_environments():
        alias = str(env.get("alias") or "")
        if alias.startswith(DEMO_ALIAS_PREFIX):  # GUARD 1: prefijo
            if dbcompare_registry.delete_environment(alias):
                removed_aliases.append(alias)
    demo_root = (data_dir() / _DEMO_DIRNAME).resolve()
    files_removed = False
    error = None
    if demo_root.exists():
        # GUARD 2: contención canónica — jamás borrar fuera del sandbox.
        if not demo_root.is_relative_to((data_dir() / "db_compare").resolve()):
            raise RuntimeError(f"guard de contención violado: {demo_root}")
        for p in demo_root.rglob("*"):
            if not p.resolve().is_relative_to(demo_root):
                raise RuntimeError(f"guard de contención violado: {p}")
        try:
            shutil.rmtree(demo_root)
            files_removed = True
        except OSError as exc:  # fix C3: .db lockeado por una corrida activa (Windows)
            error = (
                "no se pudieron borrar los archivos del sandbox (¿corrida activa "
                f"usándolos?); reintentá al terminar. Detalle: {exc}"
            )
    return {
        "removed_aliases": removed_aliases,
        "files_removed": files_removed,
        "error": error,
    }
