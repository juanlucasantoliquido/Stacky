"""Sonda GitLab del diagnóstico de tracker — los DOS motores.

Contexto del defecto (reproducido en vivo con el proyecto RIPLEY):
`services/local_diagnostics.py::_check_tracker` ramificaba `jira / mantis / else`
sin rama `gitlab`, así que un proyecto GitLab caía al `else`, llamaba `_probe_ado`
y moría en el guard de `services/project_context.py:298-301` con el mensaje
"El proyecto 'RIPLEY' no usa Azure DevOps (tracker_type=gitlab)" — sin haber
tocado GitLab ni una vez.

El segundo motor (`services/connection_doctor.py::probe_tracker`) SÍ tenía rama
gitlab, pero construía `GitLabClient` SIN `auth_path`, y por eso nunca encontraba
el token de proyecto (vive en `backend/projects/<N>/auth/gitlab_auth.json`),
fallando con TrackerConfigError. Los dos caminos se cubren acá.

═══ ENDURECIDO POR EL PLAN 276 F10 ═══

Este archivo MOCKEABA LA CLASE `GitLabClient` ENTERA ⇒ el constructor real (donde se
resuelve el bundle y se monta el adapter TLS) nunca corría, y el test quedaba verde
con el TLS roto. Ahora usa un DOBLE PARCIAL con el constructor real y corre con
`truststore.inject_into_ssl()`, como producción.
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

from services import connection_doctor as cd  # noqa: E402
from services import gitlab_client as gl_mod  # noqa: E402
from services import local_diagnostics as ld  # noqa: E402
from services import project_context as pc  # noqa: E402

_AUTH = str(Path("proyectos") / "RIPLEY" / "auth" / "gitlab_auth.json")
# Certificado REAL del repo: desde F2 el constructor lo PARSEA.
_BUNDLE = str(Path(__file__).resolve().parents[2] / "deployment" / "srvcgit01-hoja.pem")

# La clase REAL, capturada ANTES de que `_sembrar` parchee `gl_mod.GitLabClient`.
# Si el doble parcial heredara de `gl_mod.GitLabClient` en tiempo de ejecución,
# heredaría de SÍ MISMO y daría RecursionError (pasó, y el mensaje engaña: parece la
# trampa de truststore y no lo es).
_CLIENTE_REAL = gl_mod.GitLabClient
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
    """DOBLE PARCIAL (Plan 276 F10): corre el constructor REAL, mockea el transporte.

    Antes era una clase vacía: el `auth_path` y el `ca_bundle` "llegaban" a un
    `__init__` que no hacía nada con ellos, así que el camino TLS no se ejercitaba.
    """

    ultimo_kwargs: dict = {}
    ultima_instancia = None

    def __new__(cls, **kwargs):
        cls.ultimo_kwargs = dict(kwargs)
        os.environ.setdefault("GITLAB_TOKEN", "dummy-para-aislar-tls")

        class _ClienteSinRed(_CLIENTE_REAL):
            def _request(self, *_a, **_k):
                return ({"id": 1, "username": "u"}, {"X-Total": "7"})

        # `auth_path` apunta a un archivo inexistente en el test; el token dummy de
        # la env lo cubre (regla antifalso-verde #5) y además evita que el cliente
        # LEA y REESCRIBA el archivo de credenciales real.
        inst = _ClienteSinRed(**kwargs)     # constructor REAL (incluye el adapter)
        cls.ultima_instancia = inst
        return inst


def _sembrar(monkeypatch, *, con_cliente=True):
    monkeypatch.setattr(ld, "get_active_project", lambda: "RIPLEY")
    monkeypatch.setattr(ld, "get_project_config", lambda _n: _CFG)
    monkeypatch.setattr(
        pc, "resolve_project_context", lambda *_a, **_k: SimpleNamespace(auth_path=_AUTH)
    )
    if con_cliente:
        _FakeClient.ultimo_kwargs = {}
        monkeypatch.setattr(gl_mod, "GitLabClient", _FakeClient)


# ── Motor 1: services/local_diagnostics.py (alimenta GET /api/diag/local) ──


def test_check_tracker_gitlab_no_usa_el_probe_de_ado(monkeypatch):
    """El defecto original: gitlab ruteado al `else` de Azure DevOps."""
    _sembrar(monkeypatch)
    llamado = []
    monkeypatch.setattr(ld, "_probe_ado", lambda *a, **k: llamado.append("ado"))

    r = ld._check_tracker()

    assert llamado == [], f"gitlab fue ruteado al probe de ADO. message={r['message']!r}"
    assert r["status"] == "ok", f"status={r['status']!r} message={r['message']!r}"


def test_check_tracker_gitlab_rotula_con_el_nombre_propio(monkeypatch):
    """El dict de labels no tenía la clave `gitlab` ⇒ rotulaba 'gitlab alcanzable'.

    PLAN 276 F4 — la afirmación de este test cambió, y el motivo va por escrito:
    antes exigía el literal "GitLab alcanzable". Ese rótulo era un NOMBRE que
    AFIRMABA el veredicto ("alcanzable") sin haber hecho ningún ping, y se
    pintaba igual con el listado de issues roto — el falso verde que el plan 276
    vino a matar. La INTENCIÓN original (que el rótulo use el nombre propio
    "GitLab" y no la clave cruda "gitlab") se conserva y se sigue verificando;
    lo que se agrega es que el rótulo YA NO puede afirmar el resultado.
    """
    _sembrar(monkeypatch)
    monkeypatch.setattr(ld, "_probe_ado", lambda *a, **k: None)

    r = ld._check_tracker()

    assert "GitLab" in r["label"], f"no usa el nombre propio: label={r['label']!r}"
    assert "gitlab alcanzable" != r["label"].lower(), "volvió el rótulo con la clave cruda"
    assert "alcanzable" not in r["label"].lower(), (
        f"el rótulo vuelve a AFIRMAR el veredicto: label={r['label']!r}"
    )


def test_check_tracker_gitlab_construye_el_cliente_con_auth_path(monkeypatch):
    """Sin auth_path el cliente no encuentra el token POR PROYECTO y explota."""
    _sembrar(monkeypatch)
    monkeypatch.setattr(ld, "_probe_ado", lambda *a, **k: None)

    ld._check_tracker()

    kw = _FakeClient.ultimo_kwargs
    assert kw, "GitLabClient nunca se construyó: el camino gitlab no se ejecutó"
    assert kw.get("auth_path") == _AUTH, f"auth_path={kw.get('auth_path')!r}"
    assert kw.get("base_url") == "https://gl.example"
    assert kw.get("project") == "grp/proj"


# ── Motor 2: services/connection_doctor.py (alimenta /api/devops/connections) ──


def test_connection_doctor_gitlab_construye_el_cliente_con_auth_path(monkeypatch):
    """Mismo bug del token en el OTRO motor (connection_doctor.py:259)."""
    _sembrar(monkeypatch)
    monkeypatch.setattr("project_manager.get_active_project", lambda: "RIPLEY")
    monkeypatch.setattr("project_manager.get_project_config", lambda _n: _CFG)
    monkeypatch.setattr(ld, "_probe_ado", lambda *a, **k: None)

    r = cd.probe_tracker()

    kw = _FakeClient.ultimo_kwargs
    assert kw, "GitLabClient nunca se construyó desde connection_doctor"
    assert kw.get("auth_path") == _AUTH, f"auth_path={kw.get('auth_path')!r}"
    assert r["status"] == "ok", f"status={r['status']!r} detail={r.get('detail')!r}"
