"""El CA bundle tiene que llegar al camino de TICKETS, no solo a la sonda.

Contexto del defecto (reproducido en vivo contra srvcgit01 con RIPLEY):
tras cablear `ca_bundle` en `services/local_diagnostics.py`, el check de
diagnóstico quedó VERDE pero la lista de tickets seguía vacía. Causa: de los tres
constructores de `GitLabClient` del repo, solo la sonda recibía el bundle.
`services/gitlab_provider.py::GitLabTrackerProvider.__init__` —el que realmente
lista issues— lo construía sin `ca_bundle`, así que toda llamada moría con
`SSLError` contra un GitLab cuya CA no está en el almacén de la máquina.

Verificado en vivo: con bundle, `GET /projects/<path>/issues` devuelve
`X-Total: 1009`; sin bundle, `SSLError`. El gate de abajo prueba el cableado,
no la red.

═══ ENDURECIDO POR EL PLAN 276 F10 ═══

Este archivo MOCKEABA LA CLASE `GitLabClient` ENTERA, así que no ejercitaba una sola
línea del camino TLS: el constructor real —que es donde se resuelve el bundle y se
monta el adapter— nunca corría. Un test así queda verde con el TLS roto, que es
exactamente lo que pasó.

Ahora usa un DOBLE PARCIAL: el constructor REAL se ejecuta (envuelto por un espía
que registra los kwargs) y solo se mockea el transporte. Y `_BUNDLE` pasó de una
ruta inventada (`C:/certs/...`, que no existe) al certificado REAL del repo, porque
desde F2/F3 una ruta declarada inexistente lanza `CaBundleInvalido` — como debe.
"""
from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_CLASE_SSL_ANTES = ssl.SSLContext
import truststore  # noqa: E402

truststore.inject_into_ssl()
assert ssl.SSLContext is not _CLASE_SSL_ANTES, (
    "truststore no se inyectó: este archivo NO está probando producción"
)

import config  # noqa: E402
from services import gitlab_provider as gp  # noqa: E402
from services import project_context as pc  # noqa: E402
from services import tracker_provider as tp  # noqa: E402

# Certificado REAL del repo: el constructor lo PARSEA desde F2. No se generan
# certificados (este venv no tiene `cryptography` ni `openssl`, medido).
_BUNDLE = str(Path(__file__).resolve().parents[2] / "deployment" / "srvcgit01-hoja.pem")
_AUTH = str(Path("proyectos") / "RIPLEY" / "auth" / "gitlab_auth.json")
_CFG = {
    "issue_tracker": {
        "type": "gitlab",
        "base_url": "https://gl.example",
        "project": "grp/proj",
        "auth_file": "auth/gitlab_auth.json",
        "ca_bundle": _BUNDLE,
    }
}


class _FakeClient:
    """DOBLE PARCIAL (Plan 276 F10): registra los kwargs y corre el constructor REAL.

    Antes esto reemplazaba `GitLabClient` por una clase vacía, con lo cual el
    constructor de verdad —donde se resuelve el bundle y se monta el adapter TLS—
    nunca se ejecutaba y el test quedaba verde con el TLS roto. Ahora hereda del
    cliente real: si el bundle no se puede cargar, este test SE ROMPE, que es
    justamente lo que tiene que pasar.
    """

    ultimo_kwargs: dict = {}
    ultima_instancia = None

    def __new__(cls, **kwargs):
        from services.gitlab_client import GitLabClient

        cls.ultimo_kwargs = dict(kwargs)
        os.environ.setdefault("GITLAB_TOKEN", "dummy-para-aislar-tls")
        inst = GitLabClient(**kwargs)      # constructor REAL
        cls.ultima_instancia = inst
        return inst


def _sembrar(monkeypatch):
    _FakeClient.ultimo_kwargs = {}
    _FakeClient.ultima_instancia = None
    monkeypatch.setenv("GITLAB_TOKEN", "dummy-para-aislar-tls")
    monkeypatch.setattr(gp, "GitLabClient", _FakeClient)
    monkeypatch.setattr(config.config, "STACKY_GITLAB_ENABLED", True, raising=False)
    monkeypatch.setattr(
        config.config, "STACKY_TRACKER_TARGET_PER_PROJECT_ENABLED", True, raising=False
    )
    monkeypatch.setattr(pc, "_config_for_project_name", lambda _n: _CFG, raising=False)
    monkeypatch.setattr(pc, "get_active_project", lambda: "RIPLEY", raising=False)
    monkeypatch.setattr(
        pc,
        "resolve_project_context",
        lambda *_a, **_k: SimpleNamespace(
            tracker_type="gitlab",
            tracker_project="grp/proj",
            base_url="https://gl.example",
            tracker_group=None,
            organization=None,
            auth_path=_AUTH,
        ),
    )


def test_build_tracker_target_expone_el_ca_bundle():
    """Si el destino no lo transporta, el provider no puede recibirlo."""
    tgt = pc.TrackerTarget(
        tracker_type="gitlab",
        project_path="grp/proj",
        base_url="https://gl.example",
        organization=None,
        group=None,
        auth_path=_AUTH,
    )
    assert hasattr(tgt, "ca_bundle"), (
        "TrackerTarget no transporta ca_bundle: el bundle no puede llegar "
        "al provider de tickets"
    )


def test_el_provider_de_tickets_recibe_el_ca_bundle(monkeypatch):
    """El defecto: solo la sonda lo recibía; el listador de issues no."""
    _sembrar(monkeypatch)

    tp.get_tracker_provider("RIPLEY")

    kw = _FakeClient.ultimo_kwargs
    assert kw, "GitLabClient nunca se construyó desde el provider de tickets"
    assert kw.get("ca_bundle") == _BUNDLE, (
        f"el provider de tickets NO recibió el bundle: ca_bundle={kw.get('ca_bundle')!r}"
    )
    # Plan 276 F10 — y el bundle no solo LLEGA: se APLICA. El constructor real corrió,
    # así que se puede verificar el eslabón que antes ningún test tocaba.
    cli = _FakeClient.ultima_instancia
    assert cli._contexto_tls is not None, "el bundle llegó pero no se cargó en un contexto TLS"
    assert cli._contexto_tls.cert_store_stats()["x509"] >= 1
    assert "https://gl.example" in cli._session.adapters, (
        f"el adapter no se montó en el prefijo del proyecto: {list(cli._session.adapters)}"
    )


def test_el_provider_de_tickets_conserva_auth_path_y_destino(monkeypatch):
    """Agregar el bundle no puede degradar lo que ya funcionaba."""
    _sembrar(monkeypatch)

    tp.get_tracker_provider("RIPLEY")

    kw = _FakeClient.ultimo_kwargs
    assert kw.get("auth_path") == _AUTH, f"auth_path={kw.get('auth_path')!r}"
    assert kw.get("base_url") == "https://gl.example", f"base_url={kw.get('base_url')!r}"
    assert kw.get("project") == "grp/proj", f"project={kw.get('project')!r}"


def test_sin_ca_bundle_declarado_el_provider_sigue_funcionando(monkeypatch):
    """Un proyecto GitLab.com sin bundle no debe romperse ni recibir basura."""
    _sembrar(monkeypatch)
    sin_bundle = {"issue_tracker": dict(_CFG["issue_tracker"])}
    sin_bundle["issue_tracker"].pop("ca_bundle")
    monkeypatch.setattr(pc, "_config_for_project_name", lambda _n: sin_bundle, raising=False)

    tp.get_tracker_provider("RIPLEY")

    kw = _FakeClient.ultimo_kwargs
    assert kw, "GitLabClient nunca se construyó"
    assert not kw.get("ca_bundle"), f"ca_bundle espurio: {kw.get('ca_bundle')!r}"
