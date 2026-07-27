"""Plan 253 F6 — compactacion asistida: la UNICA pieza destructiva del plan.

Contrato HITL innegociable: nada se borra ni se compacta sin una confirmacion
explicita del operador que transporte el conteo exacto que se le mostro, con
copia de respaldo previa y con la base en su convencion de nombre de siempre.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import sqlite3  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_tokens():
    from services import confirm_token

    confirm_token.reset_for_tests()
    yield
    confirm_token.reset_for_tests()


@pytest.fixture
def base_de_archivo(tmp_path, monkeypatch):
    """Base SQLite real en tmp_path, con historial vencido para purgar."""
    from services import db_backup, db_maintenance

    path = tmp_path / "stacky_agents.db"
    backups = tmp_path / "backups"

    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE system_logs (id INTEGER PRIMARY KEY, timestamp TEXT, "
        "level TEXT, source TEXT, action TEXT)"
    )
    for i in range(50):
        conn.execute(
            "INSERT INTO system_logs (timestamp, level, source, action) VALUES (?,?,?,?)",
            ("2020-01-01 00:00:00.000000", "INFO", "viejo", f"a{i}"),
        )
    conn.commit()
    conn.close()

    monkeypatch.setattr(db_backup, "sqlite_db_path", lambda *_a, **_k: path)
    monkeypatch.setattr(db_backup, "backups_dir", lambda: backups)
    monkeypatch.setattr(db_maintenance, "_sqlite_path", lambda: path)
    # La purga retroactiva usa el engine global (en RAM): en estos casos no
    # aporta y enmascararia el efecto del VACUUM sobre la base de archivo.
    monkeypatch.setattr(db_maintenance, "purge_syslog_batched", lambda **_k: 0)
    return path, backups


def _stats_y_token():
    from services.db_maintenance import db_stats, issue_compact_token

    stats = db_stats()
    return stats, issue_compact_token(stats)


def _flag_on(monkeypatch):
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_DB_COMPACT_ENABLED", True)


def test_compact_sin_confirmacion_devuelve_409(base_de_archivo, monkeypatch):
    from services.db_maintenance import CompactError, compact_db

    _flag_on(monkeypatch)
    with pytest.raises(CompactError) as exc:
        compact_db(token="", purge_retroactive=False)
    assert exc.value.reason == "confirmation_invalid"


def test_compact_con_confirmacion_vencida_devuelve_409(base_de_archivo, monkeypatch):
    from services import confirm_token
    from services.db_maintenance import CompactError, compact_db

    _flag_on(monkeypatch)
    _stats, token = _stats_y_token()
    confirm_token.expire_token_for_tests(token)

    with pytest.raises(CompactError) as exc:
        compact_db(token=token, purge_retroactive=False)
    assert exc.value.reason == "confirmation_invalid"


def test_confirmacion_es_de_un_solo_uso(base_de_archivo, monkeypatch):
    from services.db_maintenance import CompactError, compact_db

    _flag_on(monkeypatch)
    _stats, token = _stats_y_token()

    assert compact_db(token=token, purge_retroactive=False)["ok"] is True

    with pytest.raises(CompactError) as exc:
        compact_db(token=token, purge_retroactive=False)
    assert exc.value.reason == "confirmation_invalid"


def test_compact_hace_backup_antes_de_vacuum(base_de_archivo, monkeypatch):
    from services.db_maintenance import compact_db

    path, backups = base_de_archivo
    _flag_on(monkeypatch)
    _stats, token = _stats_y_token()

    orden: list[str] = []
    from services import db_maintenance

    real_backup = db_maintenance._forzar_backup

    def _spy_backup():
        orden.append("backup")
        return real_backup()

    monkeypatch.setattr(db_maintenance, "_forzar_backup", _spy_backup)

    real_connect = sqlite3.connect

    def _spy_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)

        def _trace(sql):
            texto = str(sql).strip().upper()
            if texto.startswith("VACUUM"):
                orden.append("vacuum")
            elif "WAL_CHECKPOINT" in texto:
                orden.append("checkpoint")

        conn.set_trace_callback(_trace)
        return conn

    monkeypatch.setattr(sqlite3, "connect", _spy_connect)
    result = compact_db(token=token, purge_retroactive=False)

    assert result["ok"] is True
    assert "backup" in orden and "vacuum" in orden
    assert orden.index("backup") < orden.index("vacuum"), "el respaldo va ANTES del VACUUM"
    assert orden.index("checkpoint") < orden.index("vacuum"), "el checkpoint va ANTES del VACUUM"
    assert list(backups.glob("stacky_agents-*.db")), "no quedo copia de respaldo"


def test_compact_aborta_si_falla_el_backup(base_de_archivo, monkeypatch):
    from services import db_maintenance
    from services.db_maintenance import CompactError, compact_db

    path, _backups = base_de_archivo
    _flag_on(monkeypatch)
    _stats, token = _stats_y_token()

    antes = path.read_bytes()
    monkeypatch.setattr(
        db_maintenance, "_forzar_backup",
        lambda: {"ok": False, "reason": "disco lleno", "backup_path": None},
    )

    with pytest.raises(CompactError) as exc:
        compact_db(token=token, purge_retroactive=False)
    assert exc.value.reason == "backup_failed"
    assert path.read_bytes() == antes, "el archivo original NO debe tocarse si el respaldo falla"


def test_compact_aborta_si_no_hay_espacio_en_disco(base_de_archivo, monkeypatch):
    from services import db_maintenance
    from services.db_maintenance import CompactError, compact_db

    _flag_on(monkeypatch)
    _stats, token = _stats_y_token()

    class _SinEspacio:
        total = 1
        used = 1
        free = 1

    monkeypatch.setattr(db_maintenance.shutil, "disk_usage", lambda *_a, **_k: _SinEspacio())
    llamadas: list[str] = []
    monkeypatch.setattr(db_maintenance, "_forzar_backup",
                        lambda: llamadas.append("backup") or {"ok": True})

    with pytest.raises(CompactError) as exc:
        compact_db(token=token, purge_retroactive=False)
    assert exc.value.reason == "insufficient_disk_space"
    assert llamadas == [], "el espacio se chequea ANTES de respaldar"


def test_compact_respeta_flag_off(base_de_archivo, monkeypatch):
    from config import config as config_obj
    from services.db_maintenance import CompactError, compact_db

    monkeypatch.setattr(config_obj, "STACKY_DB_COMPACT_ENABLED", False)
    _stats, token = _stats_y_token()

    with pytest.raises(CompactError) as exc:
        compact_db(token=token, purge_retroactive=False)
    assert exc.value.reason == "compact_disabled"


def test_backup_usa_la_convencion_de_nombre_existente(base_de_archivo, monkeypatch):
    from services import db_backup
    from services.db_maintenance import compact_db

    _path, backups = base_de_archivo
    _flag_on(monkeypatch)
    _stats, token = _stats_y_token()

    compact_db(token=token, purge_retroactive=False)

    copias = list(backups.glob("*.db"))
    assert copias, "no se genero copia de respaldo"
    for copia in copias:
        assert db_backup._BACKUP_RE.match(copia.name), (
            f"{copia.name} no matchea la convencion; el pruning nunca la borraria"
        )
        assert db_backup._date_from_backup(copia) is not None


def test_db_stats_reporta_journal_mode_y_filas_por_tabla(base_de_archivo):
    from services.db_maintenance import db_stats

    stats = db_stats()

    assert stats["available"] is True
    assert stats["journal_mode"] == "wal"
    assert stats["rows_by_table"]["system_logs"] == 50
    assert stats["purgeable_rows"] == 50
    assert stats["size_bytes"] > 0
    assert stats["page_size"] > 0


def test_db_stats_no_disponible_si_la_base_no_es_de_archivo(monkeypatch):
    from services import db_maintenance

    monkeypatch.setattr(db_maintenance, "_sqlite_path", lambda: None)
    stats = db_maintenance.db_stats()
    assert stats == {"available": False, "reason": "non_sqlite_database"}
