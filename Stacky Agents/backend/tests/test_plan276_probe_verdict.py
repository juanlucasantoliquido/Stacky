"""tests/test_plan276_probe_verdict.py — Plan 276 F4.

Mata el falso verde que costó una jornada: "Probar conexión" en VERDE con el
listado de issues roto. Dos defectos medidos:

P0-3 — `api/global_config.py` calculaba `ok = bool(checks["auth"] and checks["read"])`
y después devolvía `{"ok": True}` hardcodeado, TIRANDO el veredicto. Y el `except`
del listado era un `pass`.

Rótulo que afirma — `services/local_diagnostics.py` rotulaba el check
"<label> alcanzable", que es un NOMBRE, no un veredicto: se pintaba igual sin
haber hecho ping.
"""
import pytest

from services import local_diagnostics as ld
from services.tracker_provider import TrackerApiError

TRACKER = {
    "type": "gitlab",
    "base_url": "https://gl.interno",
    "project": "grupo/proyecto",
    "ca_bundle": "",
}


class _ClienteFalso:
    """Doble del cliente: NO se mockea la clase GitLabClient entera desde afuera,
    se le dan respuestas a `_request`. Así el resto del camino real se ejecuta."""

    def __init__(self, user=None, issues=None, headers=None, error_user=None, error_read=None):
        self._user = user if user is not None else {"id": 7, "username": "u"}
        self._issues = issues if issues is not None else [{"iid": 1}]
        self._headers = headers if headers is not None else {"X-Total": "53"}
        self._error_user = error_user
        self._error_read = error_read

    def _project_path(self):
        return "grupo%2Fproyecto"

    def _request(self, method, path, params=None, **kw):
        if path == "/user":
            if self._error_user:
                raise self._error_user
            return self._user, {}
        if self._error_read:
            raise self._error_read
        return self._issues, self._headers


def _parchear_cliente(monkeypatch, cliente):
    monkeypatch.setattr(ld, "get_active_project", lambda: "RIPLEY")
    monkeypatch.setattr(ld, "get_project_config", lambda _p: {"issue_tracker": TRACKER})
    import services.gitlab_client as gc

    monkeypatch.setattr(gc, "GitLabClient", lambda **kw: cliente)
    import services.project_context as pc

    monkeypatch.setattr(pc, "resolve_project_context", lambda _p: None)


# ── Los 4 sub-veredictos ──────────────────────────────────────────────────────

def test_los_cuatro_en_verde_dan_status_ok(monkeypatch):
    _parchear_cliente(monkeypatch, _ClienteFalso())
    r = ld._check_tracker()
    assert r["status"] == "ok", r
    assert r["detail"]["tls"] is True
    assert r["detail"]["auth"] is True
    assert r["detail"]["proyecto_legible"] is True
    assert r["detail"]["items"] == 53


def test_auth_ok_pero_lectura_rota_da_error_y_nombra_el_proyecto(monkeypatch):
    """EL GATE CONTRA EL DEFECTO: hoy esto daba VERDE ("alcanzable")."""
    _parchear_cliente(
        monkeypatch,
        _ClienteFalso(error_read=TrackerApiError(404, "Project Not Found", kind="not_found")),
    )
    r = ld._check_tracker()
    assert r["status"] == "error", r
    assert "grupo/proyecto" in r["message"], f"el mensaje no nombra el proyecto: {r['message']}"
    assert r["detail"]["auth"] is True and r["detail"]["proyecto_legible"] is False


def test_kind_tls_pone_tls_en_falso_y_nombra_el_certificado(monkeypatch):
    _parchear_cliente(
        monkeypatch,
        _ClienteFalso(error_user=TrackerApiError(0, "handshake", kind="tls")),
    )
    r = ld._check_tracker()
    assert r["status"] == "error"
    assert r["detail"]["tls"] is False
    assert "Certificado de la empresa" in r["message"], (
        f"el mensaje no dice qué campo revisar: {r['message']}"
    )


def test_el_rotulo_ya_no_afirma_el_veredicto(monkeypatch):
    """'gitlab alcanzable' era el NOMBRE del check; nunca se hizo ping."""
    _parchear_cliente(monkeypatch, _ClienteFalso())
    r = ld._check_tracker()
    assert "alcanzable" not in r["label"].lower(), f"el rótulo sigue afirmando: {r['label']}"
    assert "TLS" in r["label"]


def test_x_total_ausente_cae_a_len_issues(monkeypatch):
    _parchear_cliente(monkeypatch, _ClienteFalso(issues=[{"iid": 1}, {"iid": 2}], headers={}))
    r = ld._check_tracker()
    assert r["detail"]["items"] == 2


def test_con_la_flag_off_vuelve_el_rotulo_de_hoy(monkeypatch):
    monkeypatch.setattr(ld.config, "STACKY_TRACKER_PROBE_STRICT_ENABLED", False, raising=False)
    _parchear_cliente(monkeypatch, _ClienteFalso())
    r = ld._check_tracker()
    assert "alcanzable" in r["label"].lower(), f"con OFF el rótulo debe ser el de hoy: {r['label']}"


# ── El endpoint global: `ok` deja de ser True hardcodeado ─────────────────────

def _app_client(monkeypatch, tmp_path):
    # P2-6: DATABASE_URL ANTES de create_app() o `create_all` corre contra la BD
    # real del operador (181 MB).
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'plan276probe.db'}")
    monkeypatch.setenv("STACKY_SKIP_STARTUP_SYNC", "1")
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_ok_del_endpoint_es_false_cuando_la_lectura_falla(monkeypatch, tmp_path):
    """EL GATE: hoy devuelve {"ok": True} aunque `read` sea False."""
    import api.global_config as gcfg

    monkeypatch.setattr(
        gcfg, "GitLabClient",
        lambda **kw: _ClienteFalso(error_read=TrackerApiError(404, "nope", kind="not_found")),
    )
    monkeypatch.setattr(gcfg, "_read_env", lambda: {})
    cli = _app_client(monkeypatch, tmp_path)
    resp = cli.post("/api/global-config/test-connection", json={
        "tracker_type": "gitlab", "gitlab_url": "https://gl.interno",
        "gitlab_project": "grupo/proyecto",
    })
    body = resp.get_json()
    assert body["ok"] is False, f"el veredicto calculado se sigue tirando: {body}"
    assert body["checks"]["read"] is False
    assert body["checks"].get("read_error"), "el fallo del listado se sigue tragando"


def test_ok_sigue_siendo_true_para_ado_sin_nameerror(monkeypatch, tmp_path):
    """GATE DEL NameError: la línea del `return` es COMPARTIDA por todos los
    tipos de tracker y `ok` solo existía en la rama GitLab."""
    import api.global_config as gcfg

    monkeypatch.setattr(gcfg, "_read_env", lambda: {"ADO_ORG": "org", "ADO_PAT": "pat"})

    class _Resp:
        status = 200

        def read(self):
            return b'{"count": 1, "value": [{"name": "P"}]}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(gcfg.urllib.request, "urlopen", lambda *a, **kw: _Resp())
    cli = _app_client(monkeypatch, tmp_path)
    resp = cli.post("/api/global-config/test-connection", json={
        "tracker_type": "azure_devops", "organization": "org", "pat": "pat",
    })
    body = resp.get_json()
    assert resp.status_code == 200, body
    assert "NameError" not in str(body), f"NameError para ADO: {body}"
    assert body["ok"] is True, body
    assert body["checks"] is None, "las ramas no-GitLab no tienen sub-checks"


def test_token_read_only_no_pone_el_check_en_rojo(monkeypatch, tmp_path):
    """C6 — `write_permission=False` con auth y read en verde ⇒ ok is True.
    Un token de solo lectura es válido para LEER issues; si votara, sería el
    mismo falso veredicto que el plan combate, con el signo invertido."""
    import api.global_config as gcfg

    class _SinEscritura(_ClienteFalso):
        def _request(self, method, path, params=None, **kw):
            if "/members/all/" in path:
                return {"access_level": 20}, {}     # Reporter: no puede escribir
            return super()._request(method, path, params=params, **kw)

    monkeypatch.setattr(gcfg, "GitLabClient", lambda **kw: _SinEscritura())
    monkeypatch.setattr(gcfg, "_read_env", lambda: {})
    cli = _app_client(monkeypatch, tmp_path)
    resp = cli.post("/api/global-config/test-connection", json={
        "tracker_type": "gitlab", "gitlab_url": "https://gl.interno",
        "gitlab_project": "grupo/proyecto",
    })
    body = resp.get_json()
    assert body["checks"]["write_permission"] is False
    assert body["ok"] is True, f"un token read-only NO puede poner el check en rojo: {body}"
