"""Plan 198 F1 — Productor: hook best-effort en environment_apply_route.

Cada apply (local O remoto, exitoso O fallido) deja 1 entry en el ledger. El hook
JAMÁS rompe el apply (try/except): con append roto la respuesta HTTP es IDÉNTICA.
Las validaciones HITL (confirm/fingerprint/sandbox_ack) NO registran (no hubo mutación).

Flask test client; apply_environment / apply_environment_remote / resolve_remote_layout /
_validate_remote_target / _load_env_context / layout_fingerprint monkeypatcheados
(mismo estilo que F0 y que los tests de environments).
"""
from __future__ import annotations

import pytest

import config
import runtime_paths


@pytest.fixture()
def _tmp_data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture()
def app():
    from app import create_app
    _app = create_app()
    _app.config["TESTING"] = True
    return _app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def _setup(monkeypatch, _tmp_data_dir):
    """Flags ON + contexto y fingerprint deterministas. rel_paths = ['a/b', 'a/c']."""
    import api.devops as devops

    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENVIRONMENTS_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENV_APPLY_LEDGER_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_DEVOPS_ENV_SANDBOX_ENABLED", True)

    def _ctx(body):
        return ("C:/amb", ["a/b", "a/c"], False, body.get("server_alias")), None

    monkeypatch.setattr(devops, "_load_env_context", _ctx)
    monkeypatch.setattr(devops, "layout_fingerprint", lambda root, rel: "FP")
    return devops


def _body(**over):
    b = {"project": "p", "confirm": True, "fingerprint": "FP", "paths": ["a/b"]}
    b.update(over)
    return b


# ---------------------------------------------------------------------------
# KPI-1 — persistencia en las 3 salidas
# ---------------------------------------------------------------------------

def test_kpi1_apply_local_ok_persiste(client, monkeypatch, _setup, _tmp_data_dir):
    monkeypatch.setattr(
        _setup, "apply_environment",
        lambda root, approved: {"created": list(approved), "skipped_existing": [],
                                "conflicts": [], "unsafe": [], "failed": []},
    )
    resp = client.post("/api/devops/environments/apply", json=_body())
    assert resp.status_code == 200

    from services.env_apply_ledger import list_applies
    rows = list_applies(root="C:/amb")
    assert len(rows) == 1
    assert rows[0]["server_alias"] is None
    assert rows[0]["result_ok"] is True
    assert rows[0]["created_count"] == 1
    assert rows[0]["paths"] == ["a/b"]
    assert rows[0]["fingerprint"] == "FP"


def test_kpi1_apply_remoto_ok_persiste(client, monkeypatch, _setup, _tmp_data_dir):
    import services.environment_remote as remote
    from api import devops_agent

    monkeypatch.setattr(devops_agent, "_validate_remote_target", lambda alias: None)
    monkeypatch.setattr(remote, "resolve_remote_layout",
                        lambda root, approved: ([(p, f"/abs/{p}") for p in approved], []))
    monkeypatch.setattr(remote, "apply_environment_remote",
                        lambda alias, root, pairs, **kw: {"created": [r for r, _ in pairs],
                                                          "skipped_existing": [], "conflicts": [],
                                                          "unsafe": [], "failed": [], "remote": True})
    resp = client.post("/api/devops/environments/apply", json=_body(server_alias="srv"))
    assert resp.status_code == 200

    from services.env_apply_ledger import list_applies
    rows = list_applies(root="C:/amb", server_alias="srv")
    assert len(rows) == 1
    assert rows[0]["server_alias"] == "srv"
    assert rows[0]["result_ok"] is True
    assert rows[0]["created_count"] == 1


def test_kpi1_apply_remoto_fallido_persiste(client, monkeypatch, _setup, _tmp_data_dir):
    import services.environment_remote as remote
    from api import devops_agent

    monkeypatch.setattr(devops_agent, "_validate_remote_target", lambda alias: None)
    monkeypatch.setattr(remote, "resolve_remote_layout",
                        lambda root, approved: ([(p, f"/abs/{p}") for p in approved], []))
    monkeypatch.setattr(remote, "apply_environment_remote",
                        lambda alias, root, pairs, **kw: {"ok": False, "error": "winrm_denied",
                                                          "remote": True})
    resp = client.post("/api/devops/environments/apply", json=_body(server_alias="srv"))
    # La respuesta HTTP mantiene su status de error original (502 default del mapa).
    assert resp.status_code == 502
    assert resp.get_json().get("ok") is False

    from services.env_apply_ledger import list_applies
    rows = list_applies(root="C:/amb", server_alias="srv")
    assert len(rows) == 1
    assert rows[0]["result_ok"] is False
    assert rows[0]["created_count"] == 0


def test_ignored_count_registrado(client, monkeypatch, _setup, _tmp_data_dir):
    """ADICIÓN — paths pedidos fuera del layout → ignored_count fiel (pedido vs aprobado)."""
    monkeypatch.setattr(
        _setup, "apply_environment",
        lambda root, approved: {"created": list(approved), "skipped_existing": [],
                                "conflicts": [], "unsafe": [], "failed": []},
    )
    # paths con 2 fuera del layout (rel_paths = ['a/b', 'a/c']).
    resp = client.post("/api/devops/environments/apply", json=_body(paths=["a/b", "x", "y"]))
    assert resp.status_code == 200

    from services.env_apply_ledger import list_applies
    rows = list_applies(root="C:/amb")
    assert len(rows) == 1
    assert rows[0]["ignored_count"] == 2
    assert rows[0]["created_count"] == 1


def test_kpi1_append_roto_no_rompe_apply(client, monkeypatch, _setup, _tmp_data_dir):
    monkeypatch.setattr(
        _setup, "apply_environment",
        lambda root, approved: {"created": list(approved), "skipped_existing": [],
                                "conflicts": [], "unsafe": [], "failed": []},
    )
    # Corrida de control (append funciona).
    resp_ok = client.post("/api/devops/environments/apply", json=_body())
    ok_bytes = resp_ok.get_data()

    # Ahora append_apply lanza: la respuesta debe ser IDÉNTICA byte a byte.
    import services.env_apply_ledger as ledger

    def _boom(entry):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(ledger, "append_apply", _boom)
    resp_broken = client.post("/api/devops/environments/apply", json=_body())
    assert resp_broken.status_code == 200
    assert resp_broken.get_data() == ok_bytes


# ---------------------------------------------------------------------------
# HITL intacto — no registran + respuestas byte-idénticas
# ---------------------------------------------------------------------------

def test_validaciones_hitl_no_registran(client, monkeypatch, _setup, _tmp_data_dir):
    resp = client.post("/api/devops/environments/apply", json=_body(confirm=False))
    assert resp.status_code == 400

    from services.env_apply_ledger import list_applies
    assert list_applies() == []


def test_hitl_intacto(client, monkeypatch, _setup, _tmp_data_dir):
    # (1) confirm faltante → 400 con el mensaje EXACTO.
    r1 = client.post("/api/devops/environments/apply", json=_body(confirm=False))
    assert r1.status_code == 400
    assert r1.get_json()["error"] == "confirm=True requerido (HITL)"

    # (2) fingerprint distinto al del layout → 409 plan_stale.
    r2 = client.post("/api/devops/environments/apply", json=_body(fingerprint="WRONG"))
    assert r2.status_code == 409
    assert r2.get_json()["kind"] == "plan_stale"

    # (3) root_override sin sandbox_ack → 400 sandbox_ack_required.
    r3 = client.post("/api/devops/environments/apply",
                     json=_body(root_override="C:/sb", sandbox_ack=False))
    assert r3.status_code == 400
    assert r3.get_json()["kind"] == "sandbox_ack_required"

    # Ninguna guarda HITL registró nada.
    from services.env_apply_ledger import list_applies
    assert list_applies() == []
