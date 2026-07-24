"""tests/test_mg_secret_backend.py — Plan 217 F1c (C3).

Valida `tools/migrar_mantis_gitlab/secret_backend.py`: backend enchufable de
secretos (dpapi | env | prompt | auto), portabilidad fuera de Windows.
"""
from __future__ import annotations

import sys

import pytest

from services import secrets_store
from tools.migrar_mantis_gitlab.secret_backend import (
    SecretPromptRequired,
    resolve_secret,
)


def test_backend_invalido_lanza_value_error():
    with pytest.raises(ValueError, match="telepathy"):
        resolve_secret("cualquier_ruta.json", "gitlab_token", "telepathy")


def test_backend_env_var_seteada(monkeypatch):
    monkeypatch.setenv("MG_GITLAB_TOKEN", "shhh-secreto")
    value = resolve_secret("no_importa.json", "gitlab_token", "env")
    assert value == "shhh-secreto"


def test_backend_env_var_ausente_lanza_prompt_required(monkeypatch):
    monkeypatch.delenv("MG_GITLAB_TOKEN", raising=False)
    with pytest.raises(SecretPromptRequired):
        resolve_secret("no_importa.json", "gitlab_token", "env")


def test_backend_prompt_siempre_lanza_prompt_required():
    with pytest.raises(SecretPromptRequired):
        resolve_secret("no_importa.json", "gitlab_token", "prompt")


def test_backend_dpapi_archivo_inexistente_lanza_prompt_required_en_cualquier_plataforma(tmp_path):
    """Regla dura: 'dpapi' con auth_file inexistente debe fallar con
    SecretPromptRequired, sin explotar antes con un error de plataforma
    (esto se prueba en CUALQUIER SO, no solo fuera de Windows)."""
    inexistente = tmp_path / "no_existe" / "gitlab_auth.json"
    with pytest.raises(SecretPromptRequired):
        resolve_secret(str(inexistente), "gitlab_token", "dpapi")


@pytest.mark.skipif(sys.platform != "win32", reason="DPAPI real sólo disponible en Windows")
def test_backend_dpapi_camino_feliz_en_windows(tmp_path):
    auth_file = tmp_path / "gitlab_auth.json"
    payload: dict = {}
    secrets_store.set_encrypted_secret(payload, "gitlab_token", "el-token-real", format_field="token_format")
    secrets_store.write_json_file(auth_file, payload)

    value = resolve_secret(str(auth_file), "gitlab_token", "dpapi")
    assert value == "el-token-real"


def test_backend_auto_windows_usa_dpapi(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    called = {}

    def _fake_dpapi(auth_file, field):
        called["auth_file"] = auth_file
        called["field"] = field
        return "valor-dpapi"

    import tools.migrar_mantis_gitlab.secret_backend as secret_backend_mod
    monkeypatch.setattr(secret_backend_mod, "_resolve_dpapi", _fake_dpapi)

    value = resolve_secret("ruta.json", "gitlab_token", "auto")
    assert value == "valor-dpapi"
    assert called == {"auth_file": "ruta.json", "field": "gitlab_token"}


def test_backend_auto_no_windows_usa_env(monkeypatch, caplog):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("MG_GITLAB_TOKEN", "valor-env")

    with caplog.at_level("WARNING", logger="migrar_mantis_gitlab.secret_backend"):
        value = resolve_secret("ruta.json", "gitlab_token", "auto")

    assert value == "valor-env"
    assert any("DPAPI" in rec.message for rec in caplog.records)


def test_backend_auto_no_windows_sin_env_cae_a_prompt(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("MG_GITLAB_TOKEN", raising=False)

    with pytest.raises(SecretPromptRequired):
        resolve_secret("ruta.json", "gitlab_token", "auto")
