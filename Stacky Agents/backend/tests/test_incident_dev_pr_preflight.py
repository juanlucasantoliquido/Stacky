"""Chequeo PREVIO de repo git + resultado visible del auto-PR del Dev Resolutor.

Pedido del operador (2026-08-02): "el auto PR no lo estoy viendo y deberia estar
en el ticket cuando lo voy a lanzar, para tildar o no hacer el PR
automaticamente, y deberia indicarme el resultado. Antes debe hacer un chequeo de
que reconoce el repo git."

Cubre las DOS mitades que faltaban:
  1. `incident_dev_pr.preflight_repo()` — dice si el auto-PR PUEDE correr y, si no,
     POR QUE (degradacion visible: el tilde se deshabilita con motivo, nunca se
     esconde en silencio).
  2. `GET /api/incidents/dev-pr/preflight` y `GET /api/incidents/dev-pr/result/<id>`
     — el unico canal por el que la UI puede enterarse del resultado. Antes de
     esto el resultado SOLO existia como comentario en la Issue del tracker
     (incident_dev_autocommit.py:176) y en un JSON en disco que nadie leia.

Sin red, sin git real: se parchean `resolve_repo_root` / `remote_origin_url` /
`resolve_project_context` del propio modulo.
"""
import pytest


# ── Fixtures ──────────────────────────────────────────────────────────────────

class _Ctx:
    def __init__(self, ws="/repo/ws", tracker="gitlab", name="RSPACIFICO"):
        self.workspace_root = ws
        self.tracker_type = tracker
        self.stacky_project_name = name


@pytest.fixture
def flags_on():
    import config as cfg
    o1 = getattr(cfg.config, "STACKY_INCIDENT_DEV_RESOLVER_ENABLED", False)
    o2 = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = True
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = True
    yield
    cfg.config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED = o1
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o2


class _FakeMRP:
    """Lo que devuelve la FABRICA. El preflight NO tiene su propia lista de
    trackers con puerto MR: le pregunta a merge_request_provider."""
    def __init__(self, name="gitlab"):
        self.name = name


_SIN_DAR = object()


def _det(repo_root, *, reason=None, es_subdirectorio=False, pista=None):
    """Resultado de `detect_repo`. `repo_root=None` == la carpeta no esta bajo git."""
    return {
        "ok": bool(repo_root),
        "reason": None if repo_root else (reason or "no_es_repo_git"),
        "repo_root": repo_root,
        "workspace_root": "/ws",
        "es_subdirectorio": es_subdirectorio,
        "pista": pista,
    }


def _patch(monkeypatch, *, ctx=None, repo_root="/repo", origin="https://gitlab.local/g/p.git",
           wrong=False, mrp=_SIN_DAR, mrp_exc=None):
    from services import incident_dev_pr as mod
    from services import merge_request_provider as mrp_mod
    from services import project_context
    monkeypatch.setattr(project_context, "resolve_project_context",
                        lambda *a, **k: ctx, raising=False)
    # La AUTO-DETECCION de git tiene su propia suite con git real
    # (test_incident_dev_pr_deteccion_git.py). Aca se sustituye su resultado para
    # ejercitar el RESTO del preflight sin depender del disco.
    monkeypatch.setattr(mod, "detect_repo", lambda ws: _det(repo_root if ws else None,
                                                            reason=None if ws else "sin_workspace"))
    monkeypatch.setattr(mod, "remote_origin_url", lambda rr: origin)

    def _factory(project=None):
        if mrp_exc:
            raise mrp_exc
        return _FakeMRP() if mrp is _SIN_DAR else mrp

    monkeypatch.setattr(mrp_mod, "get_merge_request_provider", _factory)
    from services import incident_dev_autocommit as auto
    monkeypatch.setattr(auto, "_worktree_maps_to_wrong_repo", lambda o, p: wrong)
    return mod


# ── 1. preflight_repo ─────────────────────────────────────────────────────────

def test_preflight_ok_con_repo_git_y_tracker_gitlab(flags_on, monkeypatch):
    mod = _patch(monkeypatch, ctx=_Ctx())
    r = mod.preflight_repo("RSPACIFICO")
    assert r["ok"] is True
    assert r["reason"] is None
    assert r["repo_root"] == "/repo"
    assert r["origin"] == "https://gitlab.local/g/p.git"
    assert r["tracker_type"] == "gitlab"
    assert r["provider_label"] == "gitlab"


def test_preflight_el_proveedor_sale_de_la_fabrica_no_del_ctx(flags_on, monkeypatch):
    """El label NO se deriva del `tracker_type` declarado: sale del provider que
    la fabrica realmente devolvio. Si alguna vez divergen, manda la fabrica,
    que es la que va a abrir el PR."""
    mod = _patch(monkeypatch, ctx=_Ctx(tracker="gitlab"), mrp=_FakeMRP("azure_devops"))
    r = mod.preflight_repo("X")
    assert r["ok"] is True
    assert r["tracker_type"] == "gitlab"
    assert r["provider_label"] == "azure_devops"


def test_preflight_ok_con_proyecto_sin_tracker_declarado(flags_on, monkeypatch):
    """Un proyecto sin `issue_tracker.type` explicito NO se bloquea: la fabrica
    le pone el default y el preflight respeta lo que ella diga."""
    mod = _patch(monkeypatch, ctx=_Ctx(tracker=""), mrp=_FakeMRP("azure_devops"))
    r = mod.preflight_repo("X")
    assert r["ok"] is True
    assert r["tracker_type"] is None
    assert r["provider_label"] == "azure_devops"


def test_preflight_flag_off_da_motivo_y_no_ok(monkeypatch):
    import config as cfg
    o = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = False
    try:
        mod = _patch(monkeypatch, ctx=_Ctx())
        r = mod.preflight_repo("X")
        assert r["ok"] is False
        assert r["reason"] == "feature_disabled"
        assert r["message"]  # motivo VISIBLE, nunca vacio
    finally:
        cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o


def test_preflight_sin_proyecto(flags_on, monkeypatch):
    mod = _patch(monkeypatch, ctx=None)
    r = mod.preflight_repo(None)
    assert r["ok"] is False
    assert r["reason"] == "sin_proyecto"
    assert r["message"]


def test_preflight_sin_workspace_root(flags_on, monkeypatch):
    mod = _patch(monkeypatch, ctx=_Ctx(ws=None))
    r = mod.preflight_repo("X")
    assert r["ok"] is False
    assert r["reason"] == "sin_workspace"
    assert "workspace" in r["message"].lower()


def test_preflight_workspace_que_no_es_repo_git(flags_on, monkeypatch):
    mod = _patch(monkeypatch, ctx=_Ctx(), repo_root=None)
    r = mod.preflight_repo("X")
    assert r["ok"] is False
    assert r["reason"] == "no_es_repo_git"
    assert r["repo_root"] is None
    assert "git" in r["message"].lower()


def test_preflight_tracker_sin_puerto_de_pr(flags_on, monkeypatch):
    """La fabrica lanza (tracker sin puerto MR, credenciales ausentes, flag del
    proveedor apagada...) y el motivo REAL llega al operador, no un generico."""
    mod = _patch(monkeypatch, ctx=_Ctx(tracker="jira"),
                 mrp_exc=RuntimeError("tracker 'jira' sin puerto formal"))
    r = mod.preflight_repo("X")
    assert r["ok"] is False
    assert r["reason"] == "tracker_sin_pr"
    assert r["provider_label"] is None
    assert "jira" in r["message"]      # el detalle de la fabrica, no un generico


def test_preflight_remoto_ajeno_bloquea_antes_de_lanzar(flags_on, monkeypatch):
    """La MISMA guardia que aborta el post-hook (incident_dev_autocommit.py:117),
    corrida ANTES de que el operador tilde: si no, tilda y se entera al final."""
    mod = _patch(monkeypatch, ctx=_Ctx(), wrong=True)
    r = mod.preflight_repo("X")
    assert r["ok"] is False
    assert r["reason"] == "remoto_ajeno"


def test_preflight_sin_origin_es_aviso_no_bloqueo(flags_on, monkeypatch):
    """El auto-PR commitea por REST con el PAT del tracker, no por `git push`:
    la falta de `origin` no impide abrir el PR, solo apaga la guardia de mapeo."""
    mod = _patch(monkeypatch, ctx=_Ctx(), origin=None)
    r = mod.preflight_repo("X")
    assert r["ok"] is True
    assert r["warning"] == "sin_origin"


def test_preflight_nunca_lanza_si_el_contexto_explota(flags_on, monkeypatch):
    from services import project_context
    from services import incident_dev_pr as mod

    def _boom(*a, **k):
        raise RuntimeError("proyecto roto")

    monkeypatch.setattr(project_context, "resolve_project_context", _boom, raising=False)
    r = mod.preflight_repo("X")
    assert r["ok"] is False
    assert r["reason"] == "sin_proyecto"


# ── 2. Endpoints ──────────────────────────────────────────────────────────────

@pytest.fixture
def client(flags_on):
    from app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_endpoint_preflight_devuelve_200_y_el_contrato(client, monkeypatch):
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "preflight_repo",
                        lambda project=None: {"ok": True, "reason": None, "message": "",
                                              "repo_root": "/repo", "origin": "o",
                                              "workspace_root": "/ws",
                                              "tracker_type": "gitlab",
                                              "provider_label": "GitLab",
                                              "project": "X", "warning": None})
    resp = client.get("/api/incidents/dev-pr/preflight?project=X")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["provider_label"] == "GitLab"


def test_endpoint_preflight_no_rompe_la_ui_cuando_falla(client, monkeypatch):
    """200 SIEMPRE: `api.get` del frontend LANZA en non-2xx y dejaria el tilde
    en el limbo. El fallo se comunica en el body, no en el status."""
    from services import incident_dev_pr as mod

    def _boom(project=None):
        raise RuntimeError("catastrofe")

    monkeypatch.setattr(mod, "preflight_repo", _boom)
    resp = client.get("/api/incidents/dev-pr/preflight")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["reason"] == "error_interno"
    assert data["message"]


def test_endpoint_result_sin_intent_dice_no_solicitado(client, monkeypatch):
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "get_intent", lambda eid: None)
    resp = client.get("/api/incidents/dev-pr/result/99")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["found"] is False
    assert data["status"] == "no_solicitado"


def test_endpoint_result_intent_sin_status_es_pendiente(client, monkeypatch):
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "get_intent",
                        lambda eid: {"open_pr": True, "repo_root": "/r",
                                     "baseline": {"entries": {"a": "1"}}})
    data = client.get("/api/incidents/dev-pr/result/7").get_json()
    assert data["found"] is True
    assert data["status"] == "pendiente"


def test_endpoint_result_devuelve_url_del_pr_abierto(client, monkeypatch):
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "get_intent",
                        lambda eid: {"open_pr": True, "status": "opened",
                                     "pr_url": "https://gitlab.local/g/p/-/merge_requests/9",
                                     "pr_id": 9, "branch": "stacky/incidencia-1-exec-7",
                                     "files_committed": ["a.py", "test_a.py"],
                                     "baseline": {"entries": {"a": "1"}}})
    data = client.get("/api/incidents/dev-pr/result/7").get_json()
    assert data["status"] == "opened"
    assert data["pr_url"].endswith("/merge_requests/9")
    assert data["pr_id"] == 9
    assert data["files_committed"] == ["a.py", "test_a.py"]


def test_endpoint_result_no_filtra_el_baseline(client, monkeypatch):
    """El intent guarda un hash por archivo dirty del working tree: mandarlo a la
    UI es kilobytes por poll y expone el arbol entero del operador."""
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "get_intent",
                        lambda eid: {"open_pr": True, "status": "opened",
                                     "baseline": {"entries": {"secreto.txt": "abc"}}})
    data = client.get("/api/incidents/dev-pr/result/7").get_json()
    # Mitad de contraste: sin esto el assert de AUSENCIA pasa contra un 404.
    assert data["found"] is True and data["status"] == "opened"
    assert "baseline" not in data
    assert "secreto.txt" not in resp_text(data)


def test_endpoint_result_expone_el_error_legible(client, monkeypatch):
    from services import incident_dev_pr as mod
    monkeypatch.setattr(mod, "get_intent",
                        lambda eid: {"open_pr": True, "status": "error",
                                     "error": "401 Unauthorized del tracker"})
    data = client.get("/api/incidents/dev-pr/result/7").get_json()
    assert data["status"] == "error"
    assert "401" in data["error"]


def test_endpoint_result_por_ticket_toma_la_ULTIMA_ejecucion(client, monkeypatch):
    """El resultado tiene que sobrevivir a un F5: si sólo se pudiera consultar
    por `execution_id` guardado en memoria del navegador, el operador que recarga
    pierde el resultado del PR para siempre."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock, patch
    from services import incident_dev_pr as mod

    ejecuciones = [type("E", (), {"id": 7})(), type("E", (), {"id": 9})()]

    @contextmanager
    def _scope():
        s = MagicMock()
        q = s.query.return_value.filter.return_value.order_by.return_value
        q.first.return_value = ejecuciones[-1]      # la más reciente
        yield s

    monkeypatch.setattr(mod, "result_for_execution",
                        lambda eid: {"ok": True, "found": True, "status": "opened",
                                     "terminal": True, "execution_id": eid,
                                     "pr_url": "https://x/mr/1"})
    with patch("db.session_scope", _scope):
        data = client.get("/api/incidents/dev-pr/result-by-ticket/1").get_json()
    assert data["execution_id"] == 9
    assert data["status"] == "opened"


def test_endpoint_result_por_ticket_sin_ejecuciones(client, monkeypatch):
    from contextlib import contextmanager
    from unittest.mock import MagicMock, patch

    @contextmanager
    def _scope():
        s = MagicMock()
        s.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
        yield s

    with patch("db.session_scope", _scope):
        data = client.get("/api/incidents/dev-pr/result-by-ticket/1").get_json()
    assert data["found"] is False
    assert data["status"] == "no_solicitado"


def resp_text(data):
    import json
    return json.dumps(data, ensure_ascii=False)


# ── 3. El lanzamiento no puede quedarse mudo ──────────────────────────────────

def _launch(monkeypatch, *, repo_root, open_pr=True, execution_id=4242):
    """POST /api/agents/run-incident-dev sin tocar git, DB real ni runner."""
    from contextlib import contextmanager
    from unittest.mock import MagicMock, patch

    ticket = MagicMock()
    ticket.id = 1
    ticket.work_item_type = "Issue"
    ticket.ado_id = 555
    ticket.title = "[INC] Falla X"
    ticket.description = "d"

    @contextmanager
    def _fake_scope():
        s = MagicMock()
        s.get.return_value = ticket
        yield s

    import agent_runner as ar
    from services import incident_dev_pr, merge_request_provider, project_context

    ctx = MagicMock()
    ctx.workspace_root = "/ws"
    ctx.tracker_type = "gitlab"
    ctx.stacky_project_name = "X"
    record = MagicMock()

    from app import create_app
    app = create_app()
    app.config["TESTING"] = True

    with patch("db.session_scope", _fake_scope), \
         patch.object(ar, "run_agent", MagicMock(return_value=execution_id)), \
         patch.object(project_context, "resolve_project_context", MagicMock(return_value=ctx)), \
         patch.object(merge_request_provider, "get_merge_request_provider",
                      MagicMock(return_value=_FakeMRP("gitlab"))), \
         patch.object(incident_dev_pr, "detect_repo", MagicMock(return_value=_det(repo_root))), \
         patch.object(incident_dev_pr, "remote_origin_url", MagicMock(return_value=None)), \
         patch.object(incident_dev_pr, "snapshot_worktree",
                      MagicMock(return_value={"head": "a", "entries": {}})), \
         patch.object(incident_dev_pr, "record_intent", record):
        with app.test_client() as c:
            resp = c.post("/api/agents/run-incident-dev",
                          json={"ticket_id": 1, "runtime": "github_copilot",
                                "open_pr": open_pr})
    return resp, record


def test_lanzar_con_repo_ok_declara_el_auto_pr_aceptado(client, monkeypatch):
    resp, record = _launch(monkeypatch, repo_root="/repo")
    assert resp.status_code == 202, resp.get_json()
    data = resp.get_json()
    assert data["auto_pr"]["requested"] is True
    assert data["auto_pr"]["accepted"] is True
    assert data["auto_pr"]["reason"] is None
    record.assert_called_once()


def test_lanzar_sin_repo_git_NO_queda_mudo(client, monkeypatch):
    """Regresion del defecto reportado: sin repo git, `api/agents.py:1330` no
    registraba intent y el post-hook cortaba en `get_intent()->None`
    (incident_dev_autocommit.py:88). El operador tildaba y no pasaba NADA.
    Ahora se registra un intent `skipped` con motivo y la respuesta lo declara."""
    resp, record = _launch(monkeypatch, repo_root=None)
    assert resp.status_code == 202, resp.get_json()
    data = resp.get_json()
    assert data["auto_pr"]["requested"] is True
    assert data["auto_pr"]["accepted"] is False
    assert data["auto_pr"]["reason"] == "no_es_repo_git"
    assert data["auto_pr"]["message"]
    # y el resultado queda consultable por el endpoint, no solo en un log
    record.assert_called_once()
    args, _ = record.call_args
    assert args[1]["status"] == "skipped"
    assert args[1]["open_pr"] is False


def test_lanzar_sin_tildar_no_declara_nada_del_auto_pr(client, monkeypatch):
    resp, record = _launch(monkeypatch, repo_root="/repo", open_pr=False)
    assert resp.status_code == 202
    assert resp.get_json()["auto_pr"]["requested"] is False
    record.assert_not_called()


# ── 4. El run que FALLA tampoco puede quedarse mudo ───────────────────────────
# Evidencia real medida en la base viva del operador (2026-08-02):
#   data/incident_dev_pr/{164,165,166,167}.json -> {"open_pr": true, ...} SIN
#   `status`, y agent_executions 164..167 con agent_type='incident_dev' y
#   status='error'. O sea: el operador tildo "Abrir PR" CUATRO veces el
#   2026-07-26, los cuatro runs fallaron, el post-hook corto en
#   `final_status != "completed"` (incident_dev_autocommit.py:84) y salio SIN
#   marcar el intent ni avisar nada. Los intents quedaron huerfanos para
#   siempre: cualquier lector los veria "pendiente" eternamente.

def _post_hook(monkeypatch, *, intent, final_status, agent_type="incident_dev", flag=True):
    from unittest.mock import MagicMock
    import config as cfg
    from services import incident_dev_autocommit as mod
    from services import incident_dev_pr

    o = getattr(cfg.config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = flag
    mark = MagicMock()
    monkeypatch.setattr(incident_dev_pr, "get_intent", MagicMock(return_value=intent))
    monkeypatch.setattr(incident_dev_pr, "mark_intent", mark)
    monkeypatch.setattr(mod, "_ticket_ado_id_and_project", MagicMock(return_value=(100, "p")))
    monkeypatch.setattr(mod, "_comment_issue_safe", MagicMock())
    try:
        mod.maybe_open_pr_for_incident_dev(
            ticket_id=5, execution_id=164, final_status=final_status,
            agent_type=agent_type, error="boom",
        )
    finally:
        cfg.config.STACKY_INCIDENT_DEV_PR_ENABLED = o
    return mark


def test_run_en_error_marca_el_intent_en_vez_de_dejarlo_huerfano(monkeypatch):
    mark = _post_hook(monkeypatch, intent={"open_pr": True}, final_status="error")
    mark.assert_called_once()
    assert mark.call_args.kwargs["status"] == "skipped"
    assert "error" in mark.call_args.kwargs["error"]


def test_run_no_completado_cualquiera_marca_el_intent(monkeypatch):
    mark = _post_hook(monkeypatch, intent={"open_pr": True}, final_status="needs_review")
    mark.assert_called_once()
    assert mark.call_args.kwargs["status"] == "skipped"


def test_run_en_error_sin_tilde_no_marca_nada(monkeypatch):
    """Sin consentimiento no hay nada que reportar."""
    mark = _post_hook(monkeypatch, intent={"open_pr": False}, final_status="error")
    mark.assert_not_called()


def test_run_en_error_ya_marcado_no_se_re_marca(monkeypatch):
    """Idempotencia: el post-hook puede dispararse mas de una vez."""
    mark = _post_hook(monkeypatch, intent={"open_pr": True, "status": "skipped"},
                      final_status="error")
    mark.assert_not_called()


def test_otro_agente_en_error_no_toca_el_intent(monkeypatch):
    mark = _post_hook(monkeypatch, intent={"open_pr": True}, final_status="error",
                      agent_type="developer")
    mark.assert_not_called()


def test_flag_off_no_marca_nada_aunque_el_run_falle(monkeypatch):
    mark = _post_hook(monkeypatch, intent={"open_pr": True}, final_status="error", flag=False)
    mark.assert_not_called()
