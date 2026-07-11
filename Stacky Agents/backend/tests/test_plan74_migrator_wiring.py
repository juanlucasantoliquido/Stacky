"""Plan 74 F9 — Tests de wiring del migrador (flag + harness_defaults.env + rutas).

4 casos.
"""
import pathlib
import pytest


# ── Caso 1: GET /health con flag OFF → 503 ───────────────────────────────────

def test_health_flag_off():
    import config as cfg
    original = getattr(cfg.config, "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", False)
    cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = False
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.get("/api/migrator/health")
        assert r.status_code == 503
    finally:
        cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = original


# ── Caso 2: GET /health con flag ON → 200 ─────────────────────────────────────

def test_health_flag_on():
    import config as cfg
    original = getattr(cfg.config, "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", False)
    cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = True
    try:
        from app import create_app
        app = create_app()
        app.config["TESTING"] = True
        with app.test_client() as c:
            r = c.get("/api/migrator/health")
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
    finally:
        cfg.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED = original


# ── Caso 3: harness_defaults.env contiene las 2 líneas ───────────────────────

def test_harness_defaults_env_contiene_flags():
    backend = pathlib.Path(__file__).resolve().parents[1]
    env_file = backend / "harness_defaults.env"
    text = env_file.read_text(encoding="utf-8")
    assert "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false" in text, (
        "STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false no está en harness_defaults.env"
    )
    assert "STACKY_MIGRATOR_EPIC_POLICY=auto" in text, (
        "STACKY_MIGRATOR_EPIC_POLICY=auto no está en harness_defaults.env"
    )


# ── Caso 4: config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED default True ────────
# Activación operador 2026-07-10: promovida a capacidad opt-in default ON.

def test_config_default_on():
    """config.py: STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED lee True por defecto sin env var."""
    import os
    orig = os.environ.pop("STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED", None)
    try:
        import importlib
        import config as cfg_mod
        importlib.reload(cfg_mod)
        assert cfg_mod.config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED is True
    finally:
        if orig is not None:
            os.environ["STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED"] = orig
        import importlib
        import config as cfg_mod2
        importlib.reload(cfg_mod2)
