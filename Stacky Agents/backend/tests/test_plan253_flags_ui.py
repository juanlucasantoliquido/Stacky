"""Plan 253 F1 — las 9 flags de la seccion 4 existen DE VERDAD en la UI.

Declarar el atributo en config.py no alcanza: la UI se alimenta de
services/harness_flags.py. Este archivo cubre los 6 lugares del cableado.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import importlib  # noqa: E402

# Tabla UNICA de la seccion 4 del plan: key -> categoria esperada.
PLAN253_FLAGS = {
    "STACKY_SQLITE_WAL_ENABLED": "base_datos",
    "STACKY_SQLITE_BUSY_TIMEOUT_MS": "base_datos",
    "STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED": "base_datos",
    "STACKY_STARTUP_WRITE_BARRIER_WAIT_S": "fiabilidad_ciclo_vida",
    "STACKY_SQLITE_LOCK_RETRY_ENABLED": "fiabilidad_ciclo_vida",
    "STACKY_SYSLOG_AUTO_PURGE_ENABLED": "observabilidad_notif",
    "STACKY_SYSLOG_PURGE_INTERVAL_S": "observabilidad_notif",
    "STACKY_SYSLOG_RETENTION_DAYS": "observabilidad_notif",
    "STACKY_DB_COMPACT_ENABLED": "base_datos",
}

# Las UNICAS 3 bool default ON (las otras 2 bool son OFF por excepcion dura).
PLAN253_DEFAULTS_ON = {
    "STACKY_SQLITE_WAL_ENABLED",
    "STACKY_SQLITE_LOCK_RETRY_ENABLED",
    "STACKY_SYSLOG_AUTO_PURGE_ENABLED",
}


def test_las_9_flags_estan_en_el_registry():
    from services.harness_flags import FLAG_REGISTRY

    keys = {s.key for s in FLAG_REGISTRY}
    missing = sorted(set(PLAN253_FLAGS) - keys)
    assert missing == [], f"flags del plan 253 ausentes del registry: {missing}"
    assert len(PLAN253_FLAGS) == 9


def test_las_9_flags_tienen_categoria():
    from services.harness_flags import categorize

    for key, expected in PLAN253_FLAGS.items():
        actual = categorize(key)
        assert actual != "otros", f"{key} cayo en la categoria catch-all"
        assert actual == expected, f"{key}: categoria {actual!r}, esperada {expected!r}"


def test_las_9_flags_tienen_ayuda_llana():
    from services.harness_flags_help import PLAIN_HELP

    missing = sorted(set(PLAN253_FLAGS) - set(PLAIN_HELP))
    assert missing == [], f"flags del plan 253 sin ayuda llana: {missing}"


def test_defaults_on_declarados_son_exactamente_tres():
    from services.harness_flags import FLAG_REGISTRY

    declared = {
        s.key
        for s in FLAG_REGISTRY
        if s.key in PLAN253_FLAGS and s.default is True
    }
    assert declared == PLAN253_DEFAULTS_ON, (
        f"Extras: {sorted(declared - PLAN253_DEFAULTS_ON)}; "
        f"Faltantes: {sorted(PLAN253_DEFAULTS_ON - declared)}"
    )
    # Las 2 bool OFF y las 4 numericas NO declaran `default=`: default_is_known()
    # es `spec.default is not None` (type-agnostico) y las volveria "curadas".
    otros = {s.key for s in FLAG_REGISTRY if s.key in PLAN253_FLAGS and s.default is not None}
    assert otros == PLAN253_DEFAULTS_ON


def test_config_expone_los_9_atributos():
    from config import config

    missing = [k for k in PLAN253_FLAGS if not hasattr(config, k)]
    assert missing == [], f"config no expone: {missing}"
    # Defaults EFECTIVOS de la seccion 4.
    assert config.STACKY_SQLITE_WAL_ENABLED is True
    assert config.STACKY_SQLITE_BUSY_TIMEOUT_MS == 15000
    assert config.STACKY_SQLITE_SYNCHRONOUS_NORMAL_ENABLED is False
    assert float(config.STACKY_STARTUP_WRITE_BARRIER_WAIT_S) == 30.0
    assert config.STACKY_SQLITE_LOCK_RETRY_ENABLED is True
    assert config.STACKY_SYSLOG_AUTO_PURGE_ENABLED is True
    assert config.STACKY_SYSLOG_PURGE_INTERVAL_S == 21600
    assert config.STACKY_SYSLOG_RETENTION_DAYS == 90
    assert config.STACKY_DB_COMPACT_ENABLED is False


def test_retention_days_respeta_env_var_historica(monkeypatch):
    """Sin la key nueva, vale la env var historica SYSLOG_RETENTION_DAYS."""
    monkeypatch.delenv("STACKY_SYSLOG_RETENTION_DAYS", raising=False)
    monkeypatch.setenv("SYSLOG_RETENTION_DAYS", "7")

    import config as config_mod

    try:
        reloaded = importlib.reload(config_mod)
        assert reloaded.config.STACKY_SYSLOG_RETENTION_DAYS == 7
    finally:
        # Dejar el modulo config como estaba: otros tests del mismo proceso leen
        # `config.config` y un reload sucio los contaminaria.
        monkeypatch.delenv("SYSLOG_RETENTION_DAYS", raising=False)
        importlib.reload(config_mod)
