"""El `ca_bundle` de GitLab viaja de la UI hasta el cliente HTTP.

CAMINO COMPLETO, que es lo único que prueba algo acá: que el input exista en el
modal no sirve de nada si el endpoint descarta el campo en silencio — que es
exactamente lo que pasaba: `initialize_gitlab_project` armaba el dict
`issue_tracker` con type/base_url/project/auth_file/group y NADA MÁS, así que un
`gitlab_ca_bundle` enviado por el modal se perdía sin un solo error.

Cadena cubierta:
  POST /api/init_project → config.json (issue_tracker.ca_bundle)
  PATCH /api/projects/<n> → persiste y permite BORRAR
  GET  /api/projects → echo-back para que el modal relea el valor
  _probe_gitlab → GitLabClient(ca_bundle=...) → requests(verify=<ruta>)

AISLAMIENTO: PROJECTS_DIR a tmp en los TRES módulos que lo importan por valor y
el .env de los dos writers a tmp (el alta GitLab persiste la perilla del motor).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import project_manager
from services import project_context as project_context_mod


@pytest.fixture(autouse=True)
def _env_aislado(tmp_path_factory, monkeypatch):
    """NUNCA el .env real del operador."""
    import api.global_config as agc
    import api.harness_flags as ahf
    from config import config as cfg

    env_file = tmp_path_factory.mktemp("env") / ".env"
    env_file.write_text("# env de test\n", encoding="utf-8")
    monkeypatch.setattr(ahf, "_ENV_PATH", env_file)
    monkeypatch.setattr(agc, "_ENV_PATH", env_file)
    monkeypatch.setattr(cfg, "STACKY_GITLAB_ENABLED", False, raising=False)


@pytest.fixture()
def proyectos(tmp_path, monkeypatch):
    import api.projects as api_projects

    projects = tmp_path / "projects"
    projects.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    # Plan 276 F10 — el bundle del test tiene que ser un certificado REAL.
    # Antes era el literal "-----BEGIN CERTIFICATE-----\nx\n-----END...", que
    # nunca se parseaba porque el camino TLS estaba mockeado: el `verify=` viajaba
    # como un string y nadie lo abría. Ahora el constructor de GitLabClient carga el
    # bundle en un contexto OpenSSL de verdad, así que un PEM falso lanza
    # CaBundleInvalido — correctamente. Se usa la hoja real del repo (no se generan
    # certificados: no hay `cryptography` ni `openssl` en este venv, medido).
    bundle = tmp_path / "ca-bundle-migrador.pem"
    _hoja_real = (
        Path(__file__).resolve().parents[2] / "deployment" / "srvcgit01-hoja.pem"
    )
    assert _hoja_real.is_file(), (
        f"falta el certificado de referencia del repo: {_hoja_real}. "
        "Si se renombró, actualizá esta ruta (ver deployment/README_certificados.md)."
    )
    bundle.write_bytes(_hoja_real.read_bytes())
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(project_context_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_projects, "PROJECTS_DIR", projects)
    return {"dir": projects, "ws": str(ws), "bundle": bundle}


@pytest.fixture(scope="module")
def _app(tmp_path_factory):
    """Plan 276 F9/P2-6 — `DATABASE_URL` va ANTES de `create_app()`.

    Sin eso, `create_app()` hace `create_all` contra la BD REAL del operador
    (181 MB de datos de cliente): un test de UI escribiendo en la base de
    producción. Ese era el defecto.

    Y `create_app()` es de scope MÓDULO porque cuesta ~1,3 s cada vez y estos tests
    no comparten nada por la BD (trabajan sobre `config.json` en tmp, aislado por
    test en la fixture `proyectos`). Con 6 tests eso era ~8 s de puro arranque.
    """
    import os

    ruta = tmp_path_factory.mktemp("cabundle_ui") / "cabundle_ui.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{ruta.as_posix()}"
    os.environ["STACKY_SKIP_STARTUP_SYNC"] = "1"
    import db as db_mod

    assert "pytest" in str(db_mod.engine.url), (
        f"la BD del test NO está aislada de la del operador: {db_mod.engine.url}"
    )
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(_app):
    with _app.test_client() as c:
        yield c


def _body(ws: str, name: str = "GLCAB", **extra) -> dict:
    body = {
        "name": name,
        "workspace_root": ws,
        "tracker_type": "gitlab",
        "gitlab_url": "https://gl.example",
        "gitlab_project": "acme/api",
    }
    body.update(extra)
    return body


def _tracker(proyectos, name: str = "GLCAB") -> dict:
    cfg = json.loads(
        (proyectos["dir"] / name.upper() / "config.json").read_text(encoding="utf-8")
    )
    return cfg.get("issue_tracker") or {}


# ── persistencia: el campo NO puede descartarse en silencio ────────────────


def test_el_alta_persiste_el_ca_bundle(client, proyectos):
    r = client.post("/api/init_project",
                    json=_body(proyectos["ws"], gitlab_ca_bundle=str(proyectos["bundle"])))
    assert r.status_code == 200, r.get_json()
    assert _tracker(proyectos).get("ca_bundle") == str(proyectos["bundle"]), (
        f"issue_tracker={_tracker(proyectos)}"
    )


def test_la_edicion_persiste_el_ca_bundle(client, proyectos):
    client.post("/api/init_project", json=_body(proyectos["ws"]))
    r = client.patch("/api/projects/GLCAB",
                     json={"tracker_type": "gitlab",
                           "gitlab_ca_bundle": str(proyectos["bundle"])})
    assert r.status_code == 200, r.get_json()
    assert _tracker(proyectos).get("ca_bundle") == str(proyectos["bundle"])


def test_la_edicion_permite_borrar_el_ca_bundle(client, proyectos):
    client.post("/api/init_project",
                json=_body(proyectos["ws"], gitlab_ca_bundle=str(proyectos["bundle"])))
    # Plan 276 F10 — GUARDAR PRIMERO Y PROBARLO. Sin este assert intermedio, el
    # test pasaba igual si el alta NUNCA guardó el bundle: un assert de AUSENCIA no
    # distingue "se borró bien" de "nunca se guardó". Era un falso verde.
    assert _tracker(proyectos).get("ca_bundle") == str(proyectos["bundle"]), (
        "el alta no guardó el bundle, así que el borrado de abajo no prueba nada: "
        f"issue_tracker={_tracker(proyectos)}"
    )
    r = client.patch("/api/projects/GLCAB",
                     json={"tracker_type": "gitlab", "gitlab_ca_bundle": ""})
    assert r.status_code == 200, r.get_json()
    assert not _tracker(proyectos).get("ca_bundle"), (
        "un string vacío debe BORRAR el bundle, no conservarlo"
    )


def test_no_enviar_el_campo_conserva_el_valor(client, proyectos):
    """PATCH parcial: si la clave no viaja, el valor guardado sobrevive."""
    client.post("/api/init_project",
                json=_body(proyectos["ws"], gitlab_ca_bundle=str(proyectos["bundle"])))
    r = client.patch("/api/projects/GLCAB",
                     json={"tracker_type": "gitlab", "gitlab_project": "acme/otro"})
    assert r.status_code == 200, r.get_json()
    assert _tracker(proyectos).get("ca_bundle") == str(proyectos["bundle"])


def test_el_echo_back_devuelve_el_ca_bundle(client, proyectos):
    """Sin echo-back el modal abre vacío y el operador lo borra sin querer."""
    client.post("/api/init_project",
                json=_body(proyectos["ws"], gitlab_ca_bundle=str(proyectos["bundle"])))
    data = client.get("/api/projects").get_json()
    fila = next(p for p in (data if isinstance(data, list) else data["projects"])
                if p["name"] == "GLCAB")
    assert fila.get("gitlab_ca_bundle") == str(proyectos["bundle"]), f"fila={fila}"


# ── el valor guardado LLEGA al cliente HTTP ────────────────────────────────


def test_el_ca_bundle_guardado_llega_a_requests(client, proyectos, monkeypatch):
    """El eslabón final: config del proyecto → GitLabClient → verify= de requests."""
    from services import gitlab_client as gl
    from services import local_diagnostics as ld

    client.post("/api/init_project",
                json=_body(proyectos["ws"], gitlab_ca_bundle=str(proyectos["bundle"])))

    capturado: dict = {}

    class _Resp:
        status_code, ok, content = 200, True, b"{}"
        headers = {"Content-Type": "application/json"}

        def json(self):
            return {"id": 1}

    monkeypatch.setenv("GITLAB_TOKEN", "t0ken")
    # Plan 276 F10 — DOBLE PARCIAL, no mock de la clase. Se mockea
    # `requests.Session.request` (el seam NUEVO, F2) y NO el constructor: así el
    # `__init__` real corre y el montaje del adapter TLS se ejercita de verdad.
    # Mockear `gl.requests.request` (el seam viejo) dejaba este test verde sin
    # ejecutar una sola línea del camino TLS — y después de F2 no capturaba nada.
    monkeypatch.setattr(gl.requests.Session, "request",
                        lambda self, *a, **k: (capturado.update(k), _Resp())[1])

    creados: list = []
    _ctor_real = gl.GitLabClient.__init__

    def _espia_ctor(self, *a, **kw):
        _ctor_real(self, *a, **kw)
        creados.append(self)

    monkeypatch.setattr(gl.GitLabClient, "__init__", _espia_ctor)

    ld._probe_gitlab("GLCAB", _tracker(proyectos))

    assert capturado.get("verify") == str(proyectos["bundle"].resolve()), (
        f"verify={capturado.get('verify')!r}: el bundle guardado NO llegó a requests"
    )
    # El eslabón que F2 agrega: el bundle guardado también tiene que llegar al
    # ssl_context del adapter, montado en el prefijo de ESTE GitLab.
    assert creados, "no se construyó ningún GitLabClient: el camino no se ejecutó"
    cli = creados[0]
    assert cli._contexto_tls is not None, "el bundle guardado no llegó al contexto TLS"
    assert "https://gl.example" in cli._session.adapters, (
        f"el adapter no se montó en el prefijo del proyecto: {list(cli._session.adapters)}"
    )
