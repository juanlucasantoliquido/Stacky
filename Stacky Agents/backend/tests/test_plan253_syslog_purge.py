"""Plan 253 F5 — purga en lotes del historial + loop de mantenimiento compartido.

La retencion de 90 dias era DECLARATIVA (nadie llamaba a la purga) y
`system_logs` llego a 367.532 filas / 148 MB. Aca se verifica que ahora sea
EFECTIVA, en lotes, y sin `DELETE ... LIMIT` (que no compila en este SQLite).
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from datetime import datetime, timedelta  # noqa: E402


def _limpiar_syslog():
    from db import init_db, session_scope
    from models import SystemLog

    init_db()
    with session_scope() as session:
        session.query(SystemLog).delete(synchronize_session=False)


def _sembrar(n: int, *, dias: int, source: str = "plan253_purge") -> None:
    from db import session_scope
    from models import SystemLog

    ts = datetime.utcnow() - timedelta(days=dias)
    with session_scope() as session:
        for i in range(n):
            session.add(SystemLog(timestamp=ts, level="INFO", source=source, action=f"a{i}"))


def _contar(source: str = "plan253_purge") -> int:
    from db import session_scope
    from models import SystemLog

    with session_scope() as session:
        return session.query(SystemLog).filter(SystemLog.source == source).count()


def test_purge_borra_solo_lo_mas_viejo_que_retencion():
    from services.db_maintenance import purge_syslog_batched

    _limpiar_syslog()
    _sembrar(3, dias=100)
    _sembrar(2, dias=10)

    borradas = purge_syslog_batched(days=90)

    assert borradas == 3
    assert _contar() == 2


def test_purge_en_lotes_no_excede_batch_size():
    from services.db_maintenance import purge_syslog_batched

    _limpiar_syslog()
    _sembrar(12000, dias=100)

    from db import session_scope
    from models import SystemLog

    with session_scope() as session:
        antes = session.query(SystemLog).count()

    borradas = purge_syslog_batched(days=90, batch_size=5000)

    with session_scope() as session:
        despues = session.query(SystemLog).count()

    assert borradas == 12000
    assert antes - despues == 12000
    assert _contar() == 0
    # El techo por lote se verifica en test_purge_no_usa_delete_limit (3 DELETE).
    assert purge_syslog_batched(days=90, batch_size=5000) == 0


def test_purge_no_usa_delete_limit():
    """Blinda E9: `DELETE ... LIMIT` da `near "limit": syntax error` en este SQLite."""
    import re

    from sqlalchemy import event

    from db import engine
    from services.db_maintenance import purge_syslog_batched

    _limpiar_syslog()
    _sembrar(12000, dias=100)

    sentencias: list[str] = []

    def _capturar(conn, cursor, statement, parameters, context, executemany):
        if "system_logs" in statement and statement.strip().upper().startswith("DELETE"):
            sentencias.append(statement)

    event.listen(engine, "before_cursor_execute", _capturar)
    try:
        purge_syslog_batched(days=90, batch_size=5000)
    finally:
        event.remove(engine, "before_cursor_execute", _capturar)

    assert sentencias, "no se emitio ningun DELETE sobre system_logs"
    for sql in sentencias:
        assert "id IN (" in sql.replace("\n", " ")
        assert not re.search(r"DELETE\s+FROM\s+system_logs\s+WHERE\s+timestamp\s*<\s*[:?]\w*\s+LIMIT",
                             sql, re.IGNORECASE)
    # 12.000 filas con lotes de 5.000 => 3 pasadas (5000 + 5000 + 2000).
    assert len(sentencias) == 3


def test_purge_respeta_flag_off(monkeypatch):
    from config import config as config_obj
    from services.db_maintenance import register_syslog_purge_task
    from services.maintenance import iter_maintenance_tasks

    register_syslog_purge_task()
    task = next(t for t in iter_maintenance_tasks() if t.name == "syslog_purge")

    monkeypatch.setattr(config_obj, "STACKY_SYSLOG_AUTO_PURGE_ENABLED", False)
    assert task.enabled() is False

    monkeypatch.setattr(config_obj, "STACKY_SYSLOG_AUTO_PURGE_ENABLED", True)
    assert task.enabled() is True
    # `interval_s` es LAZY: un cambio desde la UI aplica en la vuelta siguiente.
    monkeypatch.setattr(config_obj, "STACKY_SYSLOG_PURGE_INTERVAL_S", 900)
    assert task.interval_s() == 900


def test_retention_days_sale_de_config_no_del_modulo(monkeypatch):
    """La retencion se resuelve EN EL CUERPO, no en el default del argumento."""
    from config import config as config_obj
    from services.stacky_logger import logger as stacky_logger

    _limpiar_syslog()
    _sembrar(4, dias=30)

    monkeypatch.setattr(config_obj, "STACKY_SYSLOG_RETENTION_DAYS", 90)
    assert stacky_logger.purge_old_logs() == 0, "con 90 dias no vence nada de 30 dias"

    monkeypatch.setattr(config_obj, "STACKY_SYSLOG_RETENTION_DAYS", 7)
    assert stacky_logger.purge_old_logs() == 4, "con 7 dias el mismo lote SI vence"


def test_purge_old_logs_con_dias_explicitos_sigue_funcionando():
    """Backward-compat del llamador de la API de purga (api/logs.py)."""
    from services.stacky_logger import logger as stacky_logger

    _limpiar_syslog()
    _sembrar(5, dias=100)
    _sembrar(2, dias=1)

    assert stacky_logger.purge_old_logs(days=90) == 5
    assert _contar() == 2


def test_maintenance_task_registrada_una_sola_vez():
    from services.db_maintenance import register_syslog_purge_task
    from services.maintenance import iter_maintenance_tasks

    register_syslog_purge_task()
    register_syslog_purge_task()

    nombres = [t.name for t in iter_maintenance_tasks()]
    assert nombres.count("syslog_purge") == 1
