"""Plan 251 F4 — endpoint SOLO LECTURA de la matriz. 13 tests, CERO red."""
from __future__ import annotations

from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "cicd_nl" / "golden"
RUTA = "/api/pipeline-environments/analyze"


def _leer(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture(autouse=True)
def _flag_on(monkeypatch, tmp_path):
    import config as cfg
    import runtime_paths

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", True,
                        raising=False)
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    yield


class _ProviderFake:
    name = "fake"

    def __init__(self, items):
        self._items = items
        self.llamadas = 0

    def list_variables_scoped(self):
        self.llamadas += 1
        return list(self._items)

    def list_variables(self):
        self.llamadas += 1
        return list(self._items)


def _mock_provider(monkeypatch, items):
    from services import ci_variables

    prov = _ProviderFake(items)
    monkeypatch.setattr(ci_variables, "get_variables_provider", lambda project=None: prov)
    return prov


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f4_flag_off_404(app, monkeypatch):
    import config as cfg

    monkeypatch.setattr(cfg.config, "STACKY_PIPELINE_ENV_MATRIX_ENABLED", False,
                        raising=False)
    r = app.test_client().post(RUTA, json={"yaml_text": "a: 1", "provider": "azure_devops"})
    assert r.status_code == 404


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f4_no_json_400(app):
    r = app.test_client().post(RUTA, data="no soy json",
                               content_type="text/plain")
    assert r.status_code == 400


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f4_yaml_vacio_400(app):
    r = app.test_client().post(RUTA, json={"yaml_text": "  ", "provider": "azure_devops"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "yaml_text_requerido"


def test_f4_provider_invalido_400(app):
    r = app.test_client().post(RUTA, json={"yaml_text": "a: 1", "provider": "jenkins"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "provider_no_soportado"


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f4_yaml_gigante_400(app):
    r = app.test_client().post(RUTA, json={"yaml_text": "x" * 500_001,
                                           "provider": "azure_devops"})
    assert r.status_code == 400
    assert r.get_json()["error"] == "yaml_demasiado_grande"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_f4_happy_bootstrap(app):
    r = app.test_client().post(RUTA, json={
        "yaml_text": _leer("bootstrap-server-environment.yml"),
        "provider": "azure_devops", "resolve": False})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["environments"] == ["Test", "Production"]
    assert body["pending_count"] > 0
    assert any(x["kind"] == "server" for x in body["requirements"])
    assert isinstance(body["cells"], list)
    assert body["pending_fingerprint"]


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f4_happy_cd_deploy(app):
    r = app.test_client().post(RUTA, json={
        "yaml_text": _leer("cd-deploy-test.yml"),
        "provider": "azure_devops", "resolve": False})
    assert r.status_code == 200
    assert r.get_json()["environments"] == ["Test"]


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f4_resolve_false_no_toca_proveedor(app, monkeypatch):
    prov = _mock_provider(monkeypatch, [{"key": "X", "environment_scope": "*"}])
    r = app.test_client().post(RUTA, json={
        "yaml_text": _leer("cd-deploy-test.yml"),
        "provider": "azure_devops", "resolve": False})
    assert r.status_code == 200
    assert prov.llamadas == 0


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f4_degradacion_visible(app, monkeypatch):
    from services import ci_variables

    def _explota(project=None):
        raise ci_variables.VariablesUnavailableError("ADO sin definition")

    monkeypatch.setattr(ci_variables, "get_variables_provider", _explota)
    r = app.test_client().post(RUTA, json={
        "yaml_text": _leer("cd-deploy-test.yml"), "provider": "azure_devops"})
    assert r.status_code == 200, "degradar, no romper"
    assert r.get_json()["degraded"], "la degradacion se muestra intacta"


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f4_ningun_valor_en_la_respuesta(app, monkeypatch):
    """KPI-3 (a) — nombre secreto."""
    _mock_provider(monkeypatch, [
        {"key": "DB_PASSWORD", "is_secret": True, "value": "S3cr3t!XYZ",
         "environment_scope": "*"}])
    yml = ("variables:\n  DB_PASSWORD: 'p4ssw0rd'\nsteps:\n- task: VSBuild@1\n"
           "  inputs:\n    solution: '$(DB_PASSWORD)'\n")
    r = app.test_client().post(RUTA, json={"yaml_text": yml, "provider": "azure_devops"})
    assert r.status_code == 200
    crudo = r.get_data(as_text=True)
    assert "S3cr3t!XYZ" not in crudo
    assert "p4ssw0rd" not in crudo


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f4_secreto_con_nombre_inocente_no_sale(app):
    """KPI-3 (b), C5 — el nombre NO matchea `looks_secret`: solo la red A
    incondicional lo salva. Este es el test que la v1 no tenia."""
    yml = ("variables:\n  SONAR_HOST: 'glpat-AAAAAAAAAAAAAAAAAAAA'\nsteps:\n"
           "- task: VSBuild@1\n  inputs:\n    solution: '$(SONAR_HOST)'\n")
    r = app.test_client().post(RUTA, json={"yaml_text": yml, "provider": "azure_devops",
                                           "resolve": False})
    assert r.status_code == 200
    assert "glpat-AAAAAAAAAAAAAAAAAAAA" not in r.get_data(as_text=True)


def test_f4_password_arbitrario_bajo_nombre_inocente_no_sale(app):
    """ADVERSARIAL — ninguna de las DOS redes del plan cubre este caso: el valor no
    tiene un prefijo de token conocido y el nombre no suena a secreto."""
    yml = ("variables:\n  SONAR_HOST: 'Xk7#pQ2mZr9Lw4Tv'\nsteps:\n"
           "- task: VSBuild@1\n  inputs:\n    solution: '$(SONAR_HOST)'\n")
    r = app.test_client().post(RUTA, json={"yaml_text": yml, "provider": "azure_devops",
                                           "resolve": False})
    assert r.status_code == 200
    assert "Xk7#pQ2mZr9Lw4Tv" not in r.get_data(as_text=True)


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f4_health_tiene_env_matrix_enabled(app):
    r = app.test_client().get("/api/devops/health")
    assert r.status_code == 200
    assert "env_matrix_enabled" in r.get_json()


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f4_ruta_registrada(app):
    reglas = {str(r) for r in app.url_map.iter_rules()}
    assert RUTA in reglas


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_f4_endpoint_sin_logger_ni_print():
    """C1 — el gate va con `\\bprint\\(`: `Blueprint(` contiene literalmente `print(`
    y volvia el criterio de la v1 imposible por construccion."""
    import re as _re

    fuente = (Path(__file__).resolve().parent.parent / "api"
              / "pipeline_environments.py").read_text(encoding="utf-8")
    assert "Blueprint(" in fuente, "el archivo abre con Blueprint(: el gotcha es real"
    assert _re.search(r"\blogger\.", fuente) is None
    assert _re.search(r"\bprint\(", fuente) is None


def test_f4_cero_llm_en_todo_el_plan():
    """KPI-5 — paridad trivial de los 3 runtimes: 0 llamadas a modelo."""
    raiz = Path(__file__).resolve().parent.parent
    for rel in ("services/pipeline_environments.py", "services/pipeline_env_resolver.py",
                "api/pipeline_environments.py"):
        fuente = (raiz / rel).read_text(encoding="utf-8")
        for prohibido in ("invoke_local_llm", "llm_router", "copilot_bridge",
                          "claude_code_cli", "codex_cli"):
            assert prohibido not in fuente, (rel, prohibido)
