"""Plan 259 F3 — GitLabClient tiene que descifrar el token que F1 escribe, y
seguir leyendo los archivos en texto plano que ya existan hoy.

DATOS PERSONALES / RIESGO DECLARADO (hallazgo C7 / E11): `read_secret_from_file`
NO es solo lectura — cuando encuentra el secreto en claro lo cifra y REESCRIBE el
archivo (services/secrets_store.py:277-279), atándolo al usuario de Windows via
DPAPI. Este archivo cubre las DOS condiciones de la aprobación:
  * `test_plano_se_migra_a_dpapi_en_disco`  -> el efecto queda DECLARADO, no oculto.
  * `test_archivo_solo_lectura_sigue_dando_el_token` -> el FALLBACK al lector plano
    evita que una instalación que hoy anda se rompa (archivo de solo lectura,
    disco lleno, credencial compartida entre usuarios de Windows).

NINGUN test de este archivo toca un archivo de credencial real: todo en tmp_path.
"""
from __future__ import annotations

import json
import os
import stat

import pytest

import project_manager
from services import project_context as project_context_mod
from services.gitlab_client import GitLabClient
from services.tracker_provider import TrackerConfigError

# Literales con forma de token, partidos a proposito: un literal entero tipo
# token BLOQUEA el push (push-protection). Gotcha de la casa.
_TOK_CIFRADO = "glpat-" + "XYZ0DEPRUEBA"
_TOK_PLANO = "glpat-" + "PLANO0DEPRUEBA"
_TOK_VIEJO = "glpat-" + "VIEJO0DEPRUEBA"
_TOK_ENV = "env-" + "token0deprueba"


@pytest.fixture(autouse=True)
def _sin_env_gitlab(monkeypatch):
    """La precedencia env > archivo esta DOCUMENTADA (gl-10) y testeada aparte;
    en el resto de los tests el entorno tiene que estar limpio o taparia el archivo."""
    for var in ("GITLAB_TOKEN", "GITLAB_URL", "GITLAB_PROJECT"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def proj(tmp_path, monkeypatch):
    """Carpeta de proyecto aislada, con PROJECTS_DIR redirigido a tmp_path."""
    projects = tmp_path / "projects"
    projects.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(project_context_mod, "PROJECTS_DIR", projects)
    base = projects / "GLPROJ"
    (base / "auth").mkdir(parents=True)
    return base


def _plain(base, payload: dict):
    path = base / "auth" / "gitlab_auth.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _client(base):
    return GitLabClient(base_url="https://gitlab.com", project="acme/api", auth_path=str(base))


# ── camino nuevo: DPAPI ──────────────────────────────────────────────────────

def test_lee_token_cifrado_dpapi(proj):
    project_manager.write_gitlab_auth(name="GLPROJ", url="https://gitlab.com", token=_TOK_CIFRADO)
    assert _client(proj)._token == _TOK_CIFRADO


# ── backward-compat: texto plano de hoy ──────────────────────────────────────

def test_lee_token_plano_legacy(proj):
    _plain(proj, {"token": _TOK_PLANO})
    assert _client(proj)._token == _TOK_PLANO


def test_lee_private_token_legacy(proj):
    _plain(proj, {"private_token": _TOK_VIEJO})
    assert _client(proj)._token == _TOK_VIEJO


def test_archivo_corrupto_no_lanza(proj):
    (proj / "auth" / "gitlab_auth.json").write_text("{no es json", encoding="utf-8")
    with pytest.raises(TrackerConfigError):
        _client(proj)


def test_env_sigue_ganando(proj, monkeypatch):
    """Congela la precedencia DOCUMENTADA en el paso gl-10-env-precedencia."""
    project_manager.write_gitlab_auth(name="GLPROJ", url="https://gitlab.com", token=_TOK_CIFRADO)
    monkeypatch.setenv("GITLAB_TOKEN", _TOK_ENV)
    assert _client(proj)._token == _TOK_ENV


def test_sin_token_error_claro(proj):
    with pytest.raises(TrackerConfigError) as exc:
        _client(proj)
    assert str(exc.value) == (
        "GitLab: no se encontró GITLAB_TOKEN ni archivo auth/gitlab_auth.json"
    )


# ── las DOS condiciones de la aprobación del operador ────────────────────────

def test_plano_se_migra_a_dpapi_en_disco(proj):
    """Declara el efecto, no lo esconde: el archivo del operador CAMBIA.
    Afirma ESTADO OBSERVABLE (el archivo en disco), no una llamada espiada."""
    path = _plain(proj, {"token": _TOK_PLANO})
    assert _client(proj)._token == _TOK_PLANO

    despues = path.read_text(encoding="utf-8")
    assert _TOK_PLANO not in despues, "el token quedo en claro: la migracion no corrio"
    assert json.loads(despues).get("token_format"), "falta token_format tras migrar"


def test_archivo_solo_lectura_sigue_dando_el_token(proj):
    """LA REGRESION QUE HAY QUE EVITAR. Sin el fallback al lector plano de F3,
    un gitlab_auth.json de solo lectura pasa de FUNCIONAR a TrackerConfigError."""
    path = _plain(proj, {"token": _TOK_PLANO})
    os.chmod(path, stat.S_IREAD)
    try:
        assert _client(proj)._token == _TOK_PLANO
        # y el archivo del operador NO se toco (la migracion no pudo escribir)
        assert json.loads(path.read_text(encoding="utf-8")) == {"token": _TOK_PLANO}
    finally:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
