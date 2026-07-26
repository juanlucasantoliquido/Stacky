"""Plan 250 F3 — blueprint, ritual HITL y los 8 candados de /commit. 11 tests.

/commit es la UNICA ruta de todo el plan que escribe en un sistema real del operador:
`get_repo_writer(...).commit_file(...)` termina en `ado_provider.commit_file`
(services/ado_provider.py:146), que desde el plan 95 F1.a hace un push REAL por la Git
Pushes API. Por eso estos tests nunca dejan llegar la ejecucion al writer sin haber
pasado por: flag propia OFF -> confirm -> rama != default -> sha del before -> recompilar
en el servidor -> gates. Ningun test de este archivo toca la red (el guard de egress del
conftest lo garantiza) ni un provider real.
"""
from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"
STEPS = "stages[0].jobs[0].steps"
BASE = "/api/pipeline-editor"


def _yaml() -> str:
    return (GOLDEN / "ci-cd-online.yml").read_text(encoding="utf-8")


def _intent() -> dict:
    return {"verb": "set_task_input", "target_path": STEPS, "anchor_ref": "VSBuild@1",
            "task_ref": "VSBuild@1", "inputs": {"configuration": "Debug"}}


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flags(monkeypatch, tmp_path):
    import config as cfg
    import runtime_paths

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_NL_EDIT_ENABLED", True, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield


class _WriterFake:
    name = "fake"

    def __init__(self):
        self.llamadas = []

    def commit_file(self, path, content, branch, message):
        self.llamadas.append({"path": path, "content": content, "branch": branch,
                              "message": message})
        return {"sha": "abc123", "branch": branch, "path": path,
                "web_url": "https://example/x", "status": "create"}


def _sin_red(monkeypatch, writer=None, default_branch="main"):
    """Corta los DOS unicos seams que saldrian a la red desde /commit."""
    import api.pipeline_editor as pe  # noqa: PLC0415
    import services.ado_pipeline_definitions as apd  # noqa: PLC0415
    import services.repo_writer as rw  # noqa: PLC0415

    monkeypatch.setattr(apd, "_default_branch", lambda _p, _proj: default_branch)
    fake = writer if writer is not None else _WriterFake()
    monkeypatch.setattr(rw, "get_repo_writer", lambda project=None: fake)
    assert pe.STALE_CHECK == "no_verificable"
    return fake


def _body_commit(app, **extra) -> dict:
    crudo = _yaml()
    plan = app.test_client().post(BASE + "/plan",
                                  json={"yaml": crudo, "intent": _intent()})
    assert plan.status_code == 200, plan.get_json()
    p = plan.get_json()
    body = {"yaml": crudo, "intent": _intent(), "project": "P",
            "path": "pipelines/ci-cd-online.yml", "branch": "feature/edicion",
            "message": "editar", "before_sha256": p["before_sha256"],
            "approved_after_sha256": p["after_sha256"], "confirm": True}
    body.update(extra)
    return body


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_endpoints_404_con_flag_off(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_NL_EDIT_ENABLED", False,
                        raising=False)
    c = app.test_client()
    assert c.get(BASE + "/verbs").status_code == 404
    assert c.post(BASE + "/plan", json={}).status_code == 404
    assert c.post(BASE + "/commit", json={}).status_code == 404
    assert c.post(BASE + "/interpret", json={}).status_code == 404


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_plan_devuelve_hunks_y_review(app):
    r = app.test_client().post(BASE + "/plan", json={"yaml": _yaml(), "intent": _intent()})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["hunks"], body
    assert body["review"]["ok"] is True
    assert body["review"]["preservation"]["comments_after"] == 47
    assert body["before_sha256"] and body["after_sha256"]


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_plan_no_escribe_nada(app):
    ruta = GOLDEN / "ci-cd-online.yml"
    antes = ruta.read_bytes()
    r = app.test_client().post(BASE + "/plan", json={"yaml": _yaml(), "intent": _intent()})
    assert r.status_code == 200
    assert ruta.read_bytes() == antes, "/plan no puede tocar el disco"


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_commit_sin_confirm_es_400(app, monkeypatch):
    """KPI-4."""
    writer = _sin_red(monkeypatch)
    body = _body_commit(app, confirm=False)
    r = app.test_client().post(BASE + "/commit", json=body)
    assert r.status_code == 400
    assert r.get_json()["error"] == "confirm=True requerido (HITL)"
    assert writer.llamadas == [], "NO se puede haber escrito nada"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_commit_sobre_rama_default_es_400(app, monkeypatch):
    writer = _sin_red(monkeypatch, default_branch="main")
    body = _body_commit(app, branch="main")
    r = app.test_client().post(BASE + "/commit", json=body)
    assert r.status_code == 400
    assert r.get_json()["error"] == "rama_default_prohibida"
    assert writer.llamadas == []


def test_commit_con_rama_default_irresoluble_es_400(app, monkeypatch):
    """No poder saber cual es la rama por defecto NO habilita a escribir en ella."""
    import services.ado_pipeline_definitions as apd

    writer = _WriterFake()
    _sin_red(monkeypatch, writer=writer)

    def _explota(_p, _proj):
        raise RuntimeError("sin credenciales")

    monkeypatch.setattr(apd, "_default_branch", _explota)
    r = app.test_client().post(BASE + "/commit", json=_body_commit(app))
    assert r.status_code == 400
    assert r.get_json()["error"] == "rama_default_desconocida"
    assert writer.llamadas == []


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_commit_con_before_sha_incoherente_es_400(app, monkeypatch):
    writer = _sin_red(monkeypatch)
    body = _body_commit(app, before_sha256="0" * 64)
    r = app.test_client().post(BASE + "/commit", json=body)
    assert r.status_code == 400
    assert r.get_json()["error"] == "before_incoherente"
    assert writer.llamadas == []


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_commit_ignora_el_yaml_del_cliente(app, monkeypatch):
    """El servidor RECOMPILA desde el intent: lo que se commitea nunca es lo que
    manda el cliente."""
    writer = _sin_red(monkeypatch)
    body = _body_commit(app)
    body["yaml_final"] = "stages: [] # payload malicioso ignorado"
    r = app.test_client().post(BASE + "/commit", json=body)
    assert r.status_code == 200, r.get_json()
    assert len(writer.llamadas) == 1
    contenido = writer.llamadas[0]["content"]
    assert "payload malicioso" not in contenido
    assert "configuration: Debug" in contenido
    assert contenido.count("#") >= 47, "los comentarios viajan al repo intactos"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_commit_con_review_en_rojo_es_422(app, monkeypatch):
    writer = _sin_red(monkeypatch)
    crudo = _yaml()
    intent = {"verb": "add_step", "target_path": STEPS, "position": "end",
              "task_ref": "PowerShell@2", "display_name": "Inline",
              "inputs": {"targetType": "inline", "script": "Write-Host hola"}}
    plan = app.test_client().post(BASE + "/plan", json={"yaml": crudo, "intent": intent})
    assert plan.status_code == 200
    assert plan.get_json()["review"]["ok"] is False
    r = app.test_client().post(BASE + "/commit", json={
        "yaml": crudo, "intent": intent, "project": "P", "path": "p.yml",
        "branch": "feature/x", "before_sha256": plan.get_json()["before_sha256"],
        "confirm": True})
    assert r.status_code == 422
    assert r.get_json()["error"] == "gates_en_rojo"
    assert writer.llamadas == []


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_commit_404_con_flag_de_commit_off(app, monkeypatch):
    """C2 — el candado 0. De fabrica el sistema VE y DIFFEA pero NO escribe."""
    import config as cfg

    writer = _sin_red(monkeypatch)
    body = _body_commit(app)
    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED", False,
                        raising=False)
    c = app.test_client()
    assert c.post(BASE + "/commit", json=body).status_code == 404
    assert c.post(BASE + "/plan", json={"yaml": _yaml(),
                                        "intent": _intent()}).status_code == 200
    assert c.get(BASE + "/verbs").status_code == 200
    assert writer.llamadas == []


def test_default_de_fabrica_no_escribe():
    """El default del codigo (no el del test) es OFF: sin encenderla a mano, no hay push."""
    import importlib

    import config

    modulo = importlib.reload(config)
    assert modulo.Config().STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED is False
    assert modulo.Config().STACKY_PIPELINE_NL_EDIT_ENABLED is True


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_stale_check_se_declara_no_verificable(app, monkeypatch):
    _sin_red(monkeypatch)
    r = app.test_client().post(BASE + "/commit", json=_body_commit(app))
    assert r.status_code == 200
    body = r.get_json()
    assert body["stale_check"] == "no_verificable"
    assert "no puede saberlo" in body["stale_check_reason"]
    assert "validado" not in body["stale_check_reason"]


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_provider_sin_repo_writer_es_400(app, monkeypatch):
    """C9 — get_repo_writer lanza RuntimeError (repo_writer.py:37-41). Sin el try
    seria un 500 mudo."""
    import services.ado_pipeline_definitions as apd
    import services.repo_writer as rw

    monkeypatch.setattr(apd, "_default_branch", lambda _p, _proj: "main")

    def _explota(project=None):
        raise RuntimeError("El provider 'x' no implementa RepoWriter (falta commit_file).")

    monkeypatch.setattr(rw, "get_repo_writer", _explota)
    r = app.test_client().post(BASE + "/commit", json=_body_commit(app))
    assert r.status_code == 400
    assert r.get_json()["error"] == "provider_sin_escritura"
    assert "RepoWriter" in r.get_json()["detail"]


def test_commit_con_diff_distinto_al_aprobado_es_409(app, monkeypatch):
    writer = _sin_red(monkeypatch)
    body = _body_commit(app, approved_after_sha256="f" * 64)
    r = app.test_client().post(BASE + "/commit", json=body)
    assert r.status_code == 409
    assert r.get_json()["error"] == "diff_cambio"
    assert writer.llamadas == []
