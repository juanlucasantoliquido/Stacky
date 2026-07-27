"""Plan 253 — Concurrencia SQLite: WAL, barrera de escrituras de arranque y
reintento por unidad de trabajo.

F0 escribe estos casos en ROJO (los simbolos no existen todavia); F2/F3/F4 los
ponen en verde. La DB de los tests es la compartida EN MEMORIA, donde
`PRAGMA journal_mode=WAL` devuelve `memory` (medido, E7 del plan): por eso todo
lo que verifica WAL de verdad corre sobre una DB de ARCHIVO en `tmp_path`.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import sqlite3  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import pytest  # noqa: E402

_MEM_URI = "file:stacky_shared_mem?mode=memory&cache=shared"


@pytest.fixture(autouse=True)
def _reset_startup_barrier():
    """La barrera es estado de MODULO: se desarma antes y despues de cada test."""
    import db as db_mod

    for name in ("_BARRIER_ARMED", "_STARTUP_WRITES_DONE"):
        ev = getattr(db_mod, name, None)
        if ev is not None:
            ev.clear()
    yield
    for name in ("_BARRIER_ARMED", "_STARTUP_WRITES_DONE"):
        ev = getattr(db_mod, name, None)
        if ev is not None:
            ev.clear()


# ── F2 — PRAGMAs de concurrencia ────────────────────────────────────────────


def test_apply_sqlite_pragmas_pone_wal_en_db_de_archivo(tmp_path):
    import db as db_mod

    conn = sqlite3.connect(str(tmp_path / "wal.db"))
    try:
        state = db_mod.apply_sqlite_pragmas(conn)
    finally:
        conn.close()

    assert state["journal_mode_effective"] == "wal"
    assert state["wal_status"] == "ok"
    assert int(state["busy_timeout_ms"]) >= 15000


def test_apply_sqlite_pragmas_reporta_in_memory_sin_warning():
    import db as db_mod

    conn = sqlite3.connect(_MEM_URI, uri=True)
    try:
        state = db_mod.apply_sqlite_pragmas(conn)
    finally:
        conn.close()

    # Una base en RAM NO es un rechazo del filesystem: es su propio estado.
    assert state["wal_status"] == "in_memory"
    assert state["journal_mode_effective"] == "memory"


def test_busy_timeout_efectivo_en_el_engine_global():
    from db import engine

    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("PRAGMA busy_timeout")
        value = cur.fetchone()[0]
        cur.close()
    finally:
        raw.close()

    assert int(value) >= 15000


def test_lector_sobrevive_a_escritor_concurrente(tmp_path):
    import db as db_mod

    path = tmp_path / "race.db"
    setup = sqlite3.connect(str(path))
    db_mod.apply_sqlite_pragmas(setup)
    setup.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    setup.commit()
    setup.close()

    errors: list = []
    writer_in_txn = threading.Event()

    def _writer():
        conn = sqlite3.connect(str(path))
        db_mod.apply_sqlite_pragmas(conn)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO t (v) VALUES ('x')")
            writer_in_txn.set()
            time.sleep(0.5)
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            errors.append(("writer", repr(exc)))
            writer_in_txn.set()
        finally:
            conn.close()

    th = threading.Thread(target=_writer, name="plan253-writer")
    th.start()
    assert writer_in_txn.wait(timeout=5.0)

    try:
        reader = sqlite3.connect(str(path))
        db_mod.apply_sqlite_pragmas(reader)
        try:
            reader.execute("SELECT count(*) FROM t").fetchone()
        finally:
            reader.close()
    except sqlite3.OperationalError as exc:
        errors.append(("reader", repr(exc)))

    th.join(timeout=10)
    assert errors == [], f"la lectura concurrente fallo: {errors}"


def test_backup_semanal_conserva_lo_commiteado_en_wal(tmp_path, monkeypatch):
    """Con WAL, una copia plana del .db deja fuera el sidecar y pierde datos."""
    from services import db_backup

    source = tmp_path / "stacky_agents.db"
    backups = tmp_path / "backups"

    conn = sqlite3.connect(str(source))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO t (v) VALUES ('commiteado-en-wal')")
    conn.commit()
    # La conexion queda ABIERTA: sin checkpoint, la fila vive en el `-wal`.

    monkeypatch.setattr(db_backup, "sqlite_db_path", lambda *_a, **_k: source)
    monkeypatch.setattr(db_backup, "backups_dir", lambda: backups)
    try:
        result = db_backup.ensure_weekly_backup()
    finally:
        conn.close()

    assert result["ok"] is True and result["skipped"] is False
    target = tmp_path / "backups" / os.path.basename(result["backup_path"])
    check = sqlite3.connect(str(target))
    try:
        rows = check.execute("SELECT v FROM t").fetchall()
    finally:
        check.close()
    assert rows == [("commiteado-en-wal",)], "el respaldo perdio lo que estaba en el sidecar"


def test_synchronous_normal_es_opt_in(tmp_path, monkeypatch):
    import db as db_mod
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED", False)
    conn = sqlite3.connect(str(tmp_path / "sync_off.db"))
    try:
        assert db_mod.apply_sqlite_pragmas(conn)["synchronous"] == 2  # FULL
    finally:
        conn.close()

    monkeypatch.setattr(config_obj, "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED", True)
    conn = sqlite3.connect(str(tmp_path / "sync_on.db"))
    try:
        assert db_mod.apply_sqlite_pragmas(conn)["synchronous"] == 1  # NORMAL
    finally:
        conn.close()


# ── F3 — barrera de escrituras de arranque ──────────────────────────────────


def test_barrera_de_escrituras_de_arranque_existe_y_se_libera():
    import db as db_mod

    db_mod.arm_startup_writes()
    assert db_mod.wait_for_startup_writes(0.05) is False
    db_mod.mark_startup_writes_done()
    assert db_mod.wait_for_startup_writes(0.05) is True


def test_barrera_no_armada_devuelve_true_inmediato():
    import db as db_mod

    started = time.monotonic()
    assert db_mod.wait_for_startup_writes(0.05) is True
    assert (time.monotonic() - started) < 0.02


def _watcher(tmp_path):
    from db import init_db
    from services.output_watcher import AdoOutputWatcher

    init_db()   # la tabla `tickets` debe existir o el scan falla por otra causa
    outputs = tmp_path / "Agentes" / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    return AdoOutputWatcher(outputs_dir=outputs)


def test_scan_once_omite_round_si_el_arranque_escribe(tmp_path, monkeypatch):
    import db as db_mod
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_STARTUP_WRITE_BARRIER_WAIT_S", 0.1)
    watcher = _watcher(tmp_path)
    db_mod.arm_startup_writes()

    result = watcher.scan_once()

    assert result == {"skipped_startup_writes_pending": True}
    assert watcher.stats.scans == 0, "un round omitido NO cuenta como scan"


def _artefacto_estable(watcher, ado_id: int) -> None:
    """Deja un comment.html YA estable (mtime envejecido) que el watcher procesaria."""
    ado_dir = watcher.outputs_dir / str(ado_id)
    ado_dir.mkdir(parents=True, exist_ok=True)
    target = ado_dir / "comment.html"
    target.write_text(f"<p>artefacto ADO-{ado_id}</p>", encoding="utf-8")
    old = time.time() - 3600
    os.utime(target, (old, old))


def test_scan_once_no_cachea_mtime_al_omitir(tmp_path, monkeypatch):
    import db as db_mod
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_STARTUP_WRITE_BARRIER_WAIT_S", 0.1)
    watcher = _watcher(tmp_path)
    _artefacto_estable(watcher, 4242)

    # Control: sin barrera armada, el artefacto SI se procesa y SI se cachea.
    watcher.scan_once()
    assert watcher._seen_b, "control invalido: el artefacto no llego a procesarse"

    watcher._seen_b.clear()
    db_mod.arm_startup_writes()
    watcher.scan_once()

    assert watcher._seen_b == {}, "el round omitido NO debe cachear mtime"
    assert watcher._seen_a == {}


def test_carrera_real_de_arranque(tmp_path, monkeypatch):
    """Reproduce E6: el escritor de arranque (_startup_sync) vs el primer scan.

    Corre contra la base REAL del engine (compartida en RAM con cache=shared),
    que es donde `database table is locked` aparece de verdad.
    """
    import db as db_mod
    from config import config as config_obj
    from sqlalchemy import text as sa_text

    from db import init_db, session_scope

    init_db()

    monkeypatch.setattr(config_obj, "STACKY_STARTUP_WRITE_BARRIER_WAIT_S", 10.0)
    watcher = _watcher(tmp_path)
    _artefacto_estable(watcher, 253253)

    writer_errors: list = []
    writer_in_txn = threading.Event()

    def _startup_writer():
        db_mod.arm_startup_writes()
        try:
            with session_scope() as session:
                for i in range(200):
                    session.execute(
                        sa_text(
                            "INSERT INTO tickets (ado_id, project, title, created_at) "
                            "VALUES (:a, :p, :t, :c)"
                        ),
                        {"a": 990000 + i, "p": "plan253", "t": "carrera", "c": "2026-07-26 00:00:00"},
                    )
                writer_in_txn.set()
                time.sleep(0.3)
        except Exception as exc:  # noqa: BLE001
            writer_errors.append(repr(exc))
            writer_in_txn.set()
        finally:
            db_mod.mark_startup_writes_done()

    th = threading.Thread(target=_startup_writer, name="plan253-startup-writer")
    th.start()
    assert writer_in_txn.wait(timeout=10.0)
    watcher.scan_once()
    th.join(timeout=20)

    assert writer_errors == []
    assert watcher.stats.errors == 0, "el watcher no debe registrar errores por la carrera"


# ── F4 — reintento por unidad de trabajo ────────────────────────────────────


def _lock_error():
    from sqlalchemy.exc import OperationalError

    return OperationalError(
        "SELECT tickets.id FROM tickets", {}, Exception("database table is locked: tickets")
    )


def test_run_with_retry_reintenta_solo_lock_y_solo_unidades_completas(monkeypatch):
    import db as db_mod

    monkeypatch.setattr(db_mod.time, "sleep", lambda *_a, **_k: None)

    calls = {"n": 0}

    def _flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _lock_error()
        return "ok"

    assert db_mod.run_with_retry(_flaky, attempts=3, base_delay_s=0.0, label="t") == "ok"
    assert calls["n"] == 3

    boom = {"n": 0}

    def _bug():
        boom["n"] += 1
        raise ValueError("bug real, no es un lock")

    with pytest.raises(ValueError):
        db_mod.run_with_retry(_bug, attempts=3, base_delay_s=0.0, label="t")
    assert boom["n"] == 1, "una excepcion que no es lock se re-lanza en el PRIMER intento"


def _reset_lock_stats():
    import db as db_mod

    with db_mod._LOCK_STATS_LOCK:
        for k in db_mod._LOCK_STATS:
            db_mod._LOCK_STATS[k] = 0


def test_run_with_retry_agota_y_relanza(monkeypatch):
    import db as db_mod
    from sqlalchemy.exc import OperationalError

    monkeypatch.setattr(db_mod.time, "sleep", lambda *_a, **_k: None)
    _reset_lock_stats()

    calls = {"n": 0}

    def _siempre_lock():
        calls["n"] += 1
        raise _lock_error()

    with pytest.raises(OperationalError):
        db_mod.run_with_retry(_siempre_lock, attempts=3, base_delay_s=0.0, label="t")

    assert calls["n"] == 3
    assert db_mod.lock_stats()["exhausted"] == 1
    assert db_mod.lock_stats()["retried"] == 2


def test_run_with_retry_no_reintenta_valueerror():
    import db as db_mod

    calls = {"n": 0}

    def _bug():
        calls["n"] += 1
        raise ValueError("no es un lock")

    with pytest.raises(ValueError):
        db_mod.run_with_retry(_bug, attempts=5, base_delay_s=0.0, label="t")
    assert calls["n"] == 1


def test_run_with_retry_respeta_flag_off(monkeypatch):
    import db as db_mod
    from sqlalchemy.exc import OperationalError
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_SQLITE_LOCK_RETRY_ENABLED", False)
    calls = {"n": 0}

    def _siempre_lock():
        calls["n"] += 1
        raise _lock_error()

    with pytest.raises(OperationalError):
        db_mod.run_with_retry(_siempre_lock, attempts=5, base_delay_s=0.0, label="t")
    assert calls["n"] == 1, "con la flag apagada fn() corre UNA sola vez"


def test_run_with_retry_abre_sesion_nueva_por_intento(monkeypatch):
    """Blinda C5: se reintenta la unidad de trabajo, NUNCA una query suelta."""
    import db as db_mod
    from db import init_db, session_scope

    init_db()
    monkeypatch.setattr(db_mod.time, "sleep", lambda *_a, **_k: None)

    sesiones: list = []   # se guardan las REFERENCIAS: comparar id() reciclados miente

    def _unit():
        with session_scope() as session:
            sesiones.append(session)
            if len(sesiones) < 3:
                raise _lock_error()
            return "ok"

    assert db_mod.run_with_retry(_unit, attempts=3, base_delay_s=0.0, label="t") == "ok"
    assert len(sesiones) == 3
    assert len({id(s) for s in sesiones}) == 3, "cada intento debe abrir una Session NUEVA"


def test_syslog_reencola_batch_antes_de_descartar(monkeypatch):
    import queue as _queue

    import db as db_mod
    from db import init_db, session_scope
    from models import SystemLog
    from services import stacky_logger as sl

    init_db()
    monkeypatch.setattr(db_mod.time, "sleep", lambda *_a, **_k: None)

    # Instancia SIN thread writer: el batch se persiste llamando el metodo a mano.
    slog = object.__new__(sl._StackyLogger)
    slog._q = _queue.Queue(maxsize=100)

    perdidos: list = []
    monkeypatch.setattr(sl._std, "exception", lambda *a, **k: perdidos.append(a))

    real_scope = session_scope

    def _siempre_lock():
        raise _lock_error()

    events = [sl.LogEvent(level="ERROR", source="plan253_probe", action="persist")]

    # 1) el batch falla por lock en todos los intentos -> se REENCOLA, no se pierde
    monkeypatch.setattr(db_mod, "session_scope", _siempre_lock)
    slog._persist_batch(events)
    assert perdidos == [], "un batch reencolado NO debe reportarse como perdido"
    assert slog._q.qsize() == 1

    # 2) con la base sana, el segundo intento persiste de verdad
    monkeypatch.setattr(db_mod, "session_scope", real_scope)
    drenado = [slog._q.get_nowait()]
    slog._persist_batch(drenado)
    assert perdidos == []
    with real_scope() as session:
        assert session.query(SystemLog).filter(SystemLog.source == "plan253_probe").count() >= 1

    # 3) un batch YA reencolado que vuelve a fallar SI se descarta, y se avisa
    monkeypatch.setattr(db_mod, "session_scope", _siempre_lock)
    slog._persist_batch(drenado)
    assert perdidos, "el segundo fallo del mismo batch debe reportarse"
    assert slog._q.qsize() == 0


# ── F8 — huella de regresion ────────────────────────────────────────────────


def test_plan253_fingerprint_registrada():
    """Una clase de error con 72 ocurrencias en un dia no puede quedar sin guardian."""
    from pathlib import Path

    from services.error_fingerprints import load_fingerprints

    backend_root = Path(__file__).resolve().parent.parent
    por_id = {fp["id"]: fp for fp in load_fingerprints()}

    for fid in ("sqlite_table_locked_startup", "syslog_batch_persist_failed"):
        assert fid in por_id, f"falta la huella {fid}"
        fp = por_id[fid]
        assert fp["status"] == "resolved"
        assert fp["log_guarded"] is True
        ruta = fp["guard_test"].split("::")[0]
        assert (backend_root / ruta).exists(), f"{fid}: el guardian {ruta} no existe"

    # El escaner de arranque debe alarmar si el patron reaparece en un log fresco.
    from services.error_fingerprints import scan_text

    hits = scan_text(
        "2026-07-27 00:00:01 ERROR [stacky.output_watcher] "
        "(sqlite3.OperationalError) database table is locked: tickets"
    )
    assert "sqlite_table_locked_startup" in hits
