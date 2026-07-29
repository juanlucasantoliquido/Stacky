"""Plan 259 F7 — Encender el motor GitLab en el mismo acto de creacion.

REGLA DE LA FASE (v2, hallazgos C1+C8): el criterio principal de cada test es
ESTADO OBSERVABLE — el valor de `config.config.STACKY_GITLAB_ENABLED` y el
contenido del `.env`. Un spy sobre `set_flag_values` puede acompañar, NUNCA ser
la unica asercion. Asi nacio el falso verde de la v1: 6 tests en verde espiando
`apply_updates`, que segun su propio docstring "no persiste ni aplica".

AISLAMIENTO: `api.harness_flags._ENV_PATH` se monkeypatchea a tmp_path. NINGUN
test de este archivo escribe en el `.env` real del operador.
"""
from __future__ import annotations

import json
import pathlib

import pytest

import project_manager
from services import project_context as project_context_mod


@pytest.fixture()
def env_aislado(tmp_path, monkeypatch):
    """El .env redirigido a tmp_path + el default de la flag restaurado.

    Se aislan LOS DOS writers de .env del backend: el del arnes
    (api.harness_flags._ENV_PATH) y el de la config global
    (api.global_config._ENV_PATH), que es el dueño canonico de
    STACKY_GITLAB_ENABLED. Los dos apuntan a backend_root()/.env, o sea al .env
    REAL del operador: sin este aislamiento un test se lo reescribe.
    """
    import api.global_config as agc
    import api.harness_flags as ahf
    from config import config as cfg

    env_file = tmp_path / ".env"
    env_file.write_text("# env de test\n", encoding="utf-8")
    monkeypatch.setattr(ahf, "_ENV_PATH", env_file)
    monkeypatch.setattr(agc, "_ENV_PATH", env_file)
    monkeypatch.setattr(cfg, "STACKY_GITLAB_ENABLED", False, raising=False)
    return env_file


@pytest.fixture()
def proyectos(tmp_path, monkeypatch):
    import api.projects as api_projects

    projects = tmp_path / "projects"
    projects.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(project_context_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_projects, "PROJECTS_DIR", projects)
    return {"dir": projects, "ws": str(ws)}


@pytest.fixture()
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _gitlab_body(ws: str, name: str = "GLPROJ", **extra) -> dict:
    body = {
        "name": name,
        "workspace_root": ws,
        "tracker_type": "gitlab",
        "gitlab_url": "https://gitlab.com",
        "gitlab_project": "acme/api",
    }
    body.update(extra)
    return body


def _cfg(proyectos, name: str) -> dict:
    return json.loads(
        (proyectos["dir"] / name.upper() / "config.json").read_text(encoding="utf-8")
    )


# ── el motor se enciende DE VERDAD (estado observable) ───────────────────────

def test_enciende_de_verdad(env_aislado):
    """ROJO con la F7 de v1: es la prueba del hallazgo C1."""
    from api.projects import _enable_gitlab_engine
    from config import config as cfg

    assert cfg.STACKY_GITLAB_ENABLED is False
    result = _enable_gitlab_engine()

    assert result["changed"] is True
    assert cfg.STACKY_GITLAB_ENABLED is True, "la perilla no quedo encendida en el singleton"
    assert "STACKY_GITLAB_ENABLED=true" in env_aislado.read_text(encoding="utf-8")


def test_apply_updates_solo_no_alcanza(env_aislado, monkeypatch):
    """Centinela de la trampa: congela POR QUE existe set_flag_values. Si alguien
    "simplifica" volviendo a apply_updates a secas, este test lo dice por nombre.

    Se usa una flag REGISTRADA (STACKY_SETUP_GUIDE_VERIFY_ENABLED) porque
    apply_updates rechaza toda key fuera de FLAG_REGISTRY — y STACKY_GITLAB_ENABLED
    NO esta en ese registro (ver test_gitlab_enabled_no_esta_en_el_registro_del_arnes).
    """
    from services.harness_flags import apply_updates
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_SETUP_GUIDE_VERIFY_ENABLED", True, raising=False)
    antes = env_aislado.read_text(encoding="utf-8")
    apply_updates({"STACKY_SETUP_GUIDE_VERIFY_ENABLED": False})

    assert cfg.STACKY_SETUP_GUIDE_VERIFY_ENABLED is True, (
        "apply_updates NO deberia aplicar al singleton"
    )
    assert env_aislado.read_text(encoding="utf-8") == antes, (
        "apply_updates NO deberia escribir el .env"
    )


def test_gitlab_enabled_no_esta_en_el_registro_del_arnes():
    """SUPUESTO FALSO DEL PLAN, congelado (medido ejecutando).

    El plan 259 F7.b manda encender la perilla con
    `set_flag_values({"STACKY_GITLAB_ENABLED": True})`. Eso NO puede funcionar:
    STACKY_GITLAB_ENABLED no esta en FLAG_REGISTRY, asi que apply_updates la
    rechaza con ValueError y _enable_gitlab_engine devolveria SIEMPRE
    {"changed": False, "error": "Flag desconocida: ..."} — el mismo falso verde
    que el hallazgo C1 vino a matar, ahora por otra puerta.

    Su dueño canonico es api/global_config.py (_MANAGED_KEYS), y el docstring de
    api/harness_flags.py prohibe explicitamente que una key este en los dos
    ("dos endpoints no deben escribir la misma key"). Por eso
    _enable_gitlab_engine usa el writer de global_config + hot-apply propio.

    SI algun dia se registra la flag en FLAG_REGISTRY, este test se pone rojo y
    avisa que _enable_gitlab_engine se puede simplificar a set_flag_values.
    """
    from services.harness_flags import _REGISTRY_INDEX
    from api.global_config import _MANAGED_KEYS

    assert "STACKY_GITLAB_ENABLED" not in _REGISTRY_INDEX
    assert "STACKY_GITLAB_ENABLED" in _MANAGED_KEYS


def test_no_toca_si_ya_estaba_on(env_aislado, monkeypatch):
    from api.projects import _enable_gitlab_engine
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_GITLAB_ENABLED", True, raising=False)
    antes = env_aislado.read_text(encoding="utf-8")

    result = _enable_gitlab_engine()
    assert result == {"changed": False, "already_on": True}
    assert env_aislado.read_text(encoding="utf-8") == antes


def test_falla_no_rompe_el_alta(env_aislado, proyectos, client, monkeypatch):
    """Best-effort: si la persistencia de la perilla falla, el proyecto igual se
    crea y el error viaja en la respuesta."""
    import api.global_config as agc

    def boom(*a, **kw):
        raise RuntimeError("disco lleno")

    monkeypatch.setattr(agc, "_write_env", boom)
    resp = client.post("/api/init_project", json=_gitlab_body(proyectos["ws"]))

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _cfg(proyectos, "GLPROJ")["issue_tracker"]["type"] == "gitlab"
    assert resp.get_json()["gitlab_engine"]["error"]


def test_checkbox_destildada_no_enciende(env_aislado, proyectos, client):
    from config import config as cfg

    resp = client.post(
        "/api/init_project",
        json=_gitlab_body(proyectos["ws"], gitlab_enable_engine=False),
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert cfg.STACKY_GITLAB_ENABLED is False
    assert resp.get_json()["gitlab_engine"]["skipped"] is True
    assert _cfg(proyectos, "GLPROJ")["issue_tracker"]["type"] == "gitlab"


def test_no_se_dispara_en_otros_trackers(env_aislado, proyectos, client):
    """Cubre tambien C2: el `return` compartido no puede tirar NameError."""
    from config import config as cfg

    casos = [
        {"tracker_type": "azure_devops", "organization": "ACME", "ado_project": "Proj"},
        {"tracker_type": "jira", "jira_url": "https://acme.atlassian.net", "jira_key": "ACME"},
        {"tracker_type": "mantis", "mantis_url": "https://mantis.acme", "mantis_project_id": "7"},
    ]
    for i, extra in enumerate(casos):
        body = {"name": f"OTRO{i}", "workspace_root": proyectos["ws"], **extra}
        resp = client.post("/api/init_project", json=body)
        assert resp.status_code == 200, f"{extra['tracker_type']}: {resp.get_data(as_text=True)}"
        assert "gitlab_engine" not in resp.get_json()
        assert cfg.STACKY_GITLAB_ENABLED is False


def test_no_se_dispara_en_patch(env_aislado, proyectos, client):
    """Encender una perilla global es del ALTA, no de la edicion."""
    from config import config as cfg

    client.post("/api/init_project", json=_gitlab_body(proyectos["ws"], gitlab_enable_engine=False))
    assert cfg.STACKY_GITLAB_ENABLED is False

    resp = client.patch("/api/projects/GLPROJ", json={"display_name": "Otro"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert cfg.STACKY_GITLAB_ENABLED is False


# ── no-regresion de la extraccion F7.a (el endpoint que usa medio sistema) ────

def test_endpoint_de_flags_sigue_igual(env_aislado, client):
    from config import config as cfg

    resp = client.put(
        "/api/harness-flags", json={"updates": {"STACKY_SETUP_GUIDE_ENABLED": False}}
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "applied" in body and "restart_required_keys" in body
    assert cfg.STACKY_SETUP_GUIDE_ENABLED is False
    assert "STACKY_SETUP_GUIDE_ENABLED=false" in env_aislado.read_text(encoding="utf-8")
    # devolver la flag a su default ON para no contaminar otros tests del archivo
    client.put("/api/harness-flags", json={"updates": {"STACKY_SETUP_GUIDE_ENABLED": True}})


def test_endpoint_400_si_key_desconocida(env_aislado, client):
    """El ValueError de apply_updates sigue siendo el UNICO camino a 400."""
    resp = client.put(
        "/api/harness-flags", json={"updates": {"STACKY_NO_EXISTE_ESTA_KEY_259": True}}
    )
    assert resp.status_code == 400, resp.get_data(as_text=True)


def test_endpoint_500_si_falla_persistir(env_aislado, client, monkeypatch):
    """Congela el BORDE del try: si _write_env lanza ValueError, el endpoint da
    500, NO 400. Sin este test, meter la persistencia adentro del try pasa
    desapercibido y cambia el contrato HTTP en silencio."""
    import api.harness_flags as ahf

    def boom(_updates):
        raise ValueError("disco lleno")

    monkeypatch.setattr(ahf, "_write_env", boom)
    resp = client.put(
        "/api/harness-flags", json={"updates": {"STACKY_SETUP_GUIDE_ENABLED": False}}
    )
    assert resp.status_code == 500, resp.get_data(as_text=True)


# ── el default de config.py NO se movio ──────────────────────────────────────

def test_default_de_config_no_se_movio():
    src = (pathlib.Path(__file__).resolve().parents[1] / "config.py").read_text(encoding="utf-8")
    assert '"STACKY_GITLAB_ENABLED", "false"' in src
