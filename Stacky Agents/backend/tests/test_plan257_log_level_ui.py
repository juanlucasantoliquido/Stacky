"""Plan 257 F4 — `LOG_LEVEL` desde la UI, en caliente y sin reiniciar.

Hoy es la unica configuracion del operador que exige editar un `.env` y
reiniciar el servicio, perdiendo cualquier corrida en vuelo. Eso viola el riel
duro "toda configuracion del operador se cambia desde la interfaz".

Decision de arquitectura congelada (C14): `LOG_LEVEL` NO es una FlagSpec. El
hot-apply del panel de flags solo hace `setattr(config, key, val)` — no ejecuta
efectos secundarios — asi que registrarla ahi diria "aplicado" mientras el
logging no cambia: un falso verde nuevo. Va por UN solo camino,
`api/global_config.py`, que es quien llama `apply_log_level`.

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan257_log_level_ui.py -v
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import services.local_file_logging as lfl  # noqa: E402


@pytest.fixture(autouse=True)
def _nivel_restaurado():
    """El nivel del logger raiz es estado GLOBAL del proceso: sin restaurarlo,
    un test que baje a DEBUG contamina a todos los que siguen."""
    raiz = logging.getLogger()
    previo = raiz.level
    yield
    raiz.setLevel(previo)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")
    monkeypatch.setenv("STACKY_OUTPUT_WATCHER_ENABLED", "false")

    tmp_env = tmp_path / ".env"
    tmp_env.write_text("ADO_ORG=demo\n", encoding="utf-8")
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
        yield c, tmp_env
    stop_stale_recovery()
    stop_manifest_watcher()


# ── apply_log_level (el simbolo) ────────────────────────────────────────────


def test_apply_log_level_valida_antes_de_tocar_nada():
    logging.getLogger().setLevel(logging.INFO)

    resultado = lfl.apply_log_level("TRACE")

    assert resultado["ok"] is False
    assert resultado["error"]
    assert logging.getLogger().level == logging.INFO


# ── el endpoint ─────────────────────────────────────────────────────────────


def test_put_log_level_valido_cambia_en_caliente(client):
    c, _ = client
    logging.getLogger().setLevel(logging.INFO)
    assert not logging.getLogger().isEnabledFor(logging.DEBUG)

    resp = c.put("/api/global-config", json={"LOG_LEVEL": "DEBUG"})

    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert logging.getLogger().isEnabledFor(logging.DEBUG)


def test_put_log_level_invalido_devuelve_400_y_no_cambia_nada(client):
    c, tmp_env = client
    logging.getLogger().setLevel(logging.INFO)

    resp = c.put("/api/global-config", json={"LOG_LEVEL": "TRACE"})

    assert resp.status_code == 400
    assert logging.getLogger().level == logging.INFO
    assert "LOG_LEVEL" not in tmp_env.read_text(encoding="utf-8")


def test_put_log_level_persiste_en_env(client):
    c, tmp_env = client

    resp = c.put("/api/global-config", json={"LOG_LEVEL": "WARNING"})

    assert resp.status_code == 200
    assert resp.get_json()["persisted"] is True
    assert "LOG_LEVEL=WARNING" in tmp_env.read_text(encoding="utf-8")
    # Las demas claves del archivo no se tocan.
    assert "ADO_ORG=demo" in tmp_env.read_text(encoding="utf-8")


def test_put_log_level_env_no_escribible_aplica_igual_con_persisted_false(client, monkeypatch):
    c, _ = client
    logging.getLogger().setLevel(logging.INFO)

    def _boom(_updates):
        raise OSError("disco de solo lectura")

    monkeypatch.setattr("api.global_config._write_env", _boom)

    resp = c.put("/api/global-config", json={"LOG_LEVEL": "DEBUG"})

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["ok"] is True
    assert body["persisted"] is False
    assert body.get("message")
    assert logging.getLogger().isEnabledFor(logging.DEBUG)


def test_cambio_de_nivel_se_audita_y_no_se_throttlea(client, caplog):
    c, _ = client
    logging.getLogger().setLevel(logging.INFO)
    caplog.set_level(logging.WARNING, logger="api.global_config")

    c.put("/api/global-config", json={"LOG_LEVEL": "ERROR"})

    auditoria = [r for r in caplog.records if "LOG_LEVEL" in r.getMessage()]
    assert auditoria, "el cambio de nivel no dejo registro de auditoria"
    # Exento del throttle a proposito: es un evento unico del operador.
    assert getattr(auditoria[0], "_stacky_throttle_decision", None) is True
    # Se audita ANTES de aplicar: subir a ERROR no puede ocultar su propio registro.
    assert auditoria[0].levelno == logging.WARNING


def test_get_global_config_incluye_log_level(client):
    c, _ = client

    body = c.get("/api/global-config").get_json()

    assert "LOG_LEVEL" in body["config"]


def test_log_level_no_esta_en_flag_registry():
    """Guardia de C14: si alguien lo registra, vuelve el hot-apply mudo."""
    from services.harness_flags import FLAG_REGISTRY

    assert "LOG_LEVEL" not in {spec.key for spec in FLAG_REGISTRY}
