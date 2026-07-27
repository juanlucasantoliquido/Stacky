"""Plan 253 F7 — guard de concurrencia CONSULTABLE en /api/diag/health.

Un fix de concurrencia que no se puede consultar es un fix que se asume. Aca se
verifica que el operador pueda ver, en SU maquina, si la base quedo en lectura
y escritura simultaneas, cuanta espera tiene, si la barrera de arranque se armo
y si hubo bloqueos que agotaron los reintentos.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

_SUBCLAVES = {
    "sqlite_file", "db_size_bytes", "wal_size_bytes", "journal_mode_effective",
    "wal_status", "busy_timeout_ms", "synchronous", "startup_writes",
    "lock_stats", "maintenance", "create_app_count",
}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client (mismo patron que tests/test_harness_flags_bounds.py)."""
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")

    tmp_env = tmp_path / ".env"
    tmp_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("api.global_config._ENV_PATH", tmp_env)
    monkeypatch.setattr("api.harness_flags._ENV_PATH", tmp_env, raising=False)

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


def test_health_expone_db_runtime(client):
    payload = client.get("/api/diag/health").get_json()

    assert "db_runtime" in payload
    assert set(payload["db_runtime"]) == _SUBCLAVES
    assert set(payload["db_runtime"]["startup_writes"]) == {"armed", "done"}
    assert set(payload["db_runtime"]["lock_stats"]) == {"retried", "recovered", "exhausted"}


def test_health_reporta_in_memory_bajo_pytest(client):
    """Blinda C4 desde el otro lado: una base en RAM NO es un rechazo del disco."""
    db_runtime = client.get("/api/diag/health").get_json()["db_runtime"]

    assert db_runtime["wal_status"] == "in_memory"
    assert db_runtime["journal_mode_effective"] == "memory"
    assert int(db_runtime["busy_timeout_ms"]) >= 15000


def test_health_avisa_si_wal_fue_rechazado(client, monkeypatch):
    import db as db_mod

    monkeypatch.setattr(db_mod, "sqlite_concurrency_state", lambda: {
        "journal_mode_effective": "delete",
        "wal_status": "rejected",
        "busy_timeout_ms": 15000,
        "synchronous": 2,
        "last_applied_at": 0.0,
    })

    payload = client.get("/api/diag/health").get_json()

    assert payload["db_runtime"]["wal_status"] == "rejected"
    assert any("simultánea" in w for w in payload["warnings"]), payload["warnings"]
    assert payload["healthy"] is False


def test_health_avisa_si_hubo_locks_agotados(client, monkeypatch):
    import db as db_mod

    monkeypatch.setattr(db_mod, "lock_stats",
                        lambda: {"retried": 6, "recovered": 3, "exhausted": 3})

    payload = client.get("/api/diag/health").get_json()

    assert payload["db_runtime"]["lock_stats"]["exhausted"] == 3
    assert any("3 operaciones se perdieron" in w for w in payload["warnings"]), payload["warnings"]


def test_health_no_rompe_si_la_base_no_es_sqlite(client, monkeypatch):
    import services.db_backup as backup_mod

    monkeypatch.setattr(backup_mod, "sqlite_db_path", lambda *_a, **_k: None)

    response = client.get("/api/diag/health")

    assert response.status_code == 200
    assert response.get_json()["db_runtime"]["sqlite_file"] is None


def test_health_es_solo_lectura(client):
    primero = client.get("/api/diag/health").get_json()["db_runtime"]
    segundo = client.get("/api/diag/health").get_json()["db_runtime"]

    assert primero["lock_stats"] == segundo["lock_stats"]
    assert primero["startup_writes"] == segundo["startup_writes"]


# ── F6 — los mismos candados, vistos desde la interfaz web ───────────────────


def test_endpoint_compact_sin_confirmacion_devuelve_409(client, monkeypatch):
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_DB_COMPACT_ENABLED", True)
    response = client.post("/api/diag/db/compact", json={})

    assert response.status_code == 409
    assert response.get_json()["error"] in ("confirmation_invalid", "non_sqlite_database")


def test_endpoint_compact_con_flag_off_devuelve_409(client, monkeypatch):
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_DB_COMPACT_ENABLED", False)
    response = client.post("/api/diag/db/compact", json={"confirm_token": "x"})

    assert response.status_code == 409
    assert response.get_json()["error"] == "compact_disabled"


def test_endpoint_db_stats_no_emite_confirmacion_con_flag_off(client, monkeypatch):
    from config import config as config_obj

    monkeypatch.setattr(config_obj, "STACKY_DB_COMPACT_ENABLED", False)
    payload = client.get("/api/diag/db/stats").get_json()

    assert payload["compact_enabled"] is False
    assert payload["confirm_token"] is None
