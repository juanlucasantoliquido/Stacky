"""Plan 290 F5 — el master switch de GitLab aplica EN CALIENTE y persiste.

`_write_env` escribe el archivo de configuracion y os.environ pero NUNCA hace
setattr sobre el singleton `config.config`, que es de donde leen los 5
consumidores (tracker_provider.py:133, ci_provider.py:121, ci_variables.py:87,
ci_preflight.py:39, ci_logs_provider.py:38). Sin ese setattr un panel diria
"guardado" y el motor seguiria con el valor viejo hasta reiniciar.

Los dos ultimos casos son el sentinela del FALSO VERDE ESPEJO: aplicar en
caliente algo que no se persistio es tan malo como persistir algo que no aplica.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="module")
def app_ctx():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture
def cliente(app_ctx, tmp_path, monkeypatch):
    """El `.env` REAL del operador no se toca nunca: `_ENV_PATH` va a un temporal.

    Y el `setattr` sobre el singleton se restaura al salir: dejarlo pisado
    contamina cualquier test posterior del mismo proceso.
    """
    from api import global_config
    from config import config

    env = tmp_path / ".env"
    env.write_text("STACKY_OTRA_COSA=1\n", encoding="utf-8")
    monkeypatch.setattr(global_config, "_ENV_PATH", env)
    previo = getattr(config, "STACKY_GITLAB_ENABLED", False)
    yield app_ctx.test_client(), env
    monkeypatch.setattr(config, "STACKY_GITLAB_ENABLED", previo)


def _valor_vivo():
    from config import config

    return getattr(config, "STACKY_GITLAB_ENABLED", None)


def test_put_enciende_y_aplica_en_caliente(cliente):
    """Las DOS cosas en el MISMO test: el singleton y el archivo."""
    c, env = cliente
    r = c.put("/api/global-config", json={"STACKY_GITLAB_ENABLED": "true"})
    assert r.status_code == 200
    assert r.get_json()["persisted"] is True
    assert _valor_vivo() is True
    assert "STACKY_GITLAB_ENABLED=true" in env.read_text(encoding="utf-8")


def test_put_apaga_y_aplica_en_caliente(cliente):
    c, env = cliente
    c.put("/api/global-config", json={"STACKY_GITLAB_ENABLED": "true"})
    r = c.put("/api/global-config", json={"STACKY_GITLAB_ENABLED": "false"})
    assert r.status_code == 200
    assert _valor_vivo() is False
    assert "STACKY_GITLAB_ENABLED=false" in env.read_text(encoding="utf-8")


def test_get_devuelve_la_clave(cliente):
    c, _env = cliente
    c.put("/api/global-config", json={"STACKY_GITLAB_ENABLED": "true"})
    r = c.get("/api/global-config")
    assert r.status_code == 200
    assert "STACKY_GITLAB_ENABLED" in (r.get_json().get("config") or {})


def test_valor_basura_no_enciende(cliente):
    """No alcanza con ser un string no vacio: la tabla de valores verdaderos es
    la MISMA que la de config.py:1297-1299."""
    c, _env = cliente
    r = c.put("/api/global-config", json={"STACKY_GITLAB_ENABLED": "quizas"})
    assert r.status_code == 200
    assert _valor_vivo() is False


def test_si_no_persiste_no_aplica_en_caliente(cliente, monkeypatch):
    """Sentinela del falso verde espejo: con el disco lleno o el archivo de solo
    lectura, el motor NO puede quedar ON con el archivo sin escribir — al
    reiniciar volveria a OFF y el operador no se enteraria."""
    from api import global_config
    from config import config

    monkeypatch.setattr(config, "STACKY_GITLAB_ENABLED", False)

    def _revienta(_updates):
        raise OSError("read-only file system")

    monkeypatch.setattr(global_config, "_write_env", _revienta)
    c, _env = cliente
    r = c.put("/api/global-config", json={"STACKY_GITLAB_ENABLED": "true"})
    assert r.status_code == 200
    assert r.get_json()["persisted"] is False
    assert _valor_vivo() is False, "quedo ON con el archivo sin escribir"


def test_log_level_invalido_no_toca_gitlab(cliente, monkeypatch):
    """El `return 400` de :219-225 corta ANTES de persistir nada. Un setattr mal
    ubicado encenderia GitLab en un pedido que devuelve 400."""
    from config import config

    monkeypatch.setattr(config, "STACKY_GITLAB_ENABLED", False)
    c, _env = cliente
    r = c.put(
        "/api/global-config",
        json={"LOG_LEVEL": "TRACE", "STACKY_GITLAB_ENABLED": "true"},
    )
    assert r.status_code == 400
    assert _valor_vivo() is False
