"""El CA bundle también en la superficie GLOBAL de configuración.

Tercer constructor de `GitLabClient` del repo (`api/global_config.py:342`).
Los otros dos ya lo reciben: la sonda de diagnóstico y el provider de tickets.
Sin el bundle, "Probar conexión" de la pantalla de configuración global falla
con SSLError contra un GitLab cuya CA no está en el almacén de la máquina —
aunque el proyecto ya lo tenga configurado y funcionando.

`auth_path` NO se cablea acá A PROPÓSITO: esta ruta es GLOBAL y `GITLAB_TOKEN`
está deliberadamente excluido de ella por ser secreto (`global_config.py:77,93`).
Hacerla caer al token del proyecto activo daría un VERDE que no prueba lo que
el botón dice probar.

═══ ENDURECIDO POR EL PLAN 276 F10 ═══

Este archivo MOCKEABA LA CLASE `GitLabClient` ENTERA ⇒ el constructor real (donde se
resuelve el bundle y se monta el adapter TLS) nunca corría, y el test quedaba verde
con el TLS roto. Ahora usa un DOBLE PARCIAL con el constructor real, corre con
`truststore.inject_into_ssl()` como producción, y `_BUNDLE` apunta al certificado
REAL del repo (la ruta inventada `C:/certs/...` no existe, y desde F3 una ruta
declarada inexistente lanza — correctamente).
"""
from __future__ import annotations

import json
import os
import ssl
import sys
from pathlib import Path

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore  # noqa: E402

truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

# Certificado REAL del repo: desde F2 el constructor lo PARSEA.
_BUNDLE = str(Path(__file__).resolve().parents[2] / "deployment" / "srvcgit01-hoja.pem")


@pytest.fixture()
def client():
    from flask import Flask
    from api.global_config import bp
    application = Flask(__name__)
    application.register_blueprint(bp)
    application.config["TESTING"] = True
    return application.test_client()


class _FakeClient:
    """DOBLE PARCIAL (Plan 276 F10): corre el constructor REAL y mockea el transporte.

    Antes era una clase vacía que reemplazaba a `GitLabClient`: el bundle "llegaba"
    a un `__init__` que no hacía nada con él. Ahora hereda del cliente real, así que
    si el bundle no se puede cargar en un contexto OpenSSL, este test SE ROMPE.
    """

    ultimo_kwargs: dict = {}
    ultima_instancia = None

    def __new__(cls, **kwargs):
        from services.gitlab_client import GitLabClient

        cls.ultimo_kwargs = dict(kwargs)
        os.environ.setdefault("GITLAB_TOKEN", "dummy-para-aislar-tls")

        class _ClienteSinRed(GitLabClient):
            def _request(self, *_a, **_k):
                return ({"id": 1, "username": "u", "name": "U"}, {"X-Total": "1"})

        inst = _ClienteSinRed(**kwargs)     # constructor REAL (incluye el adapter)
        cls.ultima_instancia = inst
        return inst


def _sembrar(monkeypatch, tmp_path):
    from api import global_config as gc
    monkeypatch.setattr(gc, "_ENV_PATH", tmp_path / ".env")
    _FakeClient.ultimo_kwargs = {}
    _FakeClient.ultima_instancia = None
    monkeypatch.setenv("GITLAB_TOKEN", "dummy-para-aislar-tls")
    monkeypatch.setattr(gc, "GitLabClient", _FakeClient)


def test_el_test_de_conexion_global_pasa_el_ca_bundle(client, monkeypatch, tmp_path):
    """El defecto: global_config construía el cliente sin ca_bundle."""
    _sembrar(monkeypatch, tmp_path)

    client.post(
        "/global-config/test-connection",
        data=json.dumps({
            "tracker_type": "gitlab",
            "gitlab_url": "https://gl.example",
            "gitlab_project": "grp/proj",
            "gitlab_ca_bundle": _BUNDLE,
        }),
        content_type="application/json",
    )

    kw = _FakeClient.ultimo_kwargs
    assert kw, "GitLabClient nunca se construyó desde global_config"
    assert kw.get("ca_bundle") == _BUNDLE, (
        f"la config global NO pasó el bundle: ca_bundle={kw.get('ca_bundle')!r}"
    )


def test_el_bundle_cae_a_la_variable_de_entorno(client, monkeypatch, tmp_path):
    """Sin el campo en el body, se usa STACKY_GITLAB_CA_BUNDLE del .env."""
    _sembrar(monkeypatch, tmp_path)
    (tmp_path / ".env").write_text(f"STACKY_GITLAB_CA_BUNDLE={_BUNDLE}\n", encoding="utf-8")

    client.post(
        "/global-config/test-connection",
        data=json.dumps({
            "tracker_type": "gitlab",
            "gitlab_url": "https://gl.example",
            "gitlab_project": "grp/proj",
        }),
        content_type="application/json",
    )

    kw = _FakeClient.ultimo_kwargs
    assert kw.get("ca_bundle") == _BUNDLE, f"ca_bundle={kw.get('ca_bundle')!r}"


def test_sin_bundle_no_se_inventa_valor(client, monkeypatch, tmp_path):
    """GitLab.com no necesita bundle: no mandar basura al cliente."""
    _sembrar(monkeypatch, tmp_path)

    client.post(
        "/global-config/test-connection",
        data=json.dumps({
            "tracker_type": "gitlab",
            "gitlab_url": "https://gitlab.com",
            "gitlab_project": "grp/proj",
        }),
        content_type="application/json",
    )

    kw = _FakeClient.ultimo_kwargs
    assert kw, "GitLabClient nunca se construyó"
    assert not kw.get("ca_bundle"), f"ca_bundle espurio: {kw.get('ca_bundle')!r}"


def test_el_bundle_es_una_clave_gestionada_y_no_un_secreto():
    """Debe round-tripear por la pantalla global (es una ruta, no un token)."""
    from api import global_config as gc

    assert "STACKY_GITLAB_CA_BUNDLE" in gc._MANAGED_KEYS, (
        "STACKY_GITLAB_CA_BUNDLE no es gestionada: no se puede configurar por UI"
    )
    assert "STACKY_GITLAB_CA_BUNDLE" not in gc._SECRET_KEYS, (
        "el bundle es una RUTA, no un secreto: ocultarlo impide verificarlo"
    )
