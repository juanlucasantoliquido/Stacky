"""tests/test_plan296_propuesta.py - Plan 296 F4.

Se ve antes de aplicarse: el diff del perfil.

15 casos declarados; el #4 esta parametrizado sobre las 6 claves de _SECRET_KEYS
=> 15 - 1 + 6 = 20 colectados.

FIXTURE DE AISLAMIENTO (C6): el endpoint toca `get_project_config`.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_FLAG = "STACKY_PROFILE_COPILOT_ENABLED"
_URL = "/api/projects/DEMO/client-profile/copilot/propose"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import project_manager
    import services.client_profile as cp

    pdir = tmp_path / "projects"
    pdir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cp, "projects_dir", lambda: pdir)
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", pdir)
    eventos: list[dict] = []
    monkeypatch.setattr(
        "api.profile_copilot.record_event", lambda **kw: eventos.append(kw) or {}
    )
    return {"projects_dir": pdir, "eventos": eventos}


def _sembrar(env, nombre="DEMO", *, perfil=None):
    carpeta = env["projects_dir"] / nombre.upper()
    carpeta.mkdir(parents=True, exist_ok=True)
    cfg = {"name": nombre, "issue_tracker": {"type": "azure_devops"}}
    if perfil is not None:
        cfg["client_profile"] = perfil
    (carpeta / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _app(monkeypatch, *, flag=True):
    import config as cfg
    from app import create_app

    monkeypatch.setattr(cfg.config, _FLAG, flag, raising=False)
    app = create_app()
    app.config["TESTING"] = True
    return app


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_diff_lista_path_antes_y_despues():
    from services.profile_patch import build_profile_patch

    p = build_profile_patch(
        proyecto="DEMO",
        base={"language": {"primary": "csharp"}},
        propuesta={"language": {"primary": "python"}},
    )
    assert len(p.cambios) == 1, f"cambios: {p.cambios}"
    c = p.cambios[0]
    assert c.path == ("language", "primary"), f"path real: {c.path}"
    assert c.antes == "csharp"
    assert c.despues == "python"
    assert c.motivo.strip(), "un cambio sin motivo no se puede revisar"


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_sin_cambio_real_no_genera_entrada():
    from services.profile_patch import build_profile_patch

    igual = {"language": {"primary": "python"}, "code_layout": {"roots": ["src"]}}
    p = build_profile_patch(proyecto="DEMO", base=igual, propuesta=json.loads(json.dumps(igual)))
    assert p.cambios == (), f"propuso lo ya escrito: {p.cambios}"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_secreto_va_a_rechazos_no_a_cambios():
    from services.profile_patch import build_profile_patch

    p = build_profile_patch(
        proyecto="DEMO", base={}, propuesta={"database": {"password": "x"}}
    )
    assert p.cambios == (), f"un secreto llego a cambios: {p.cambios}"
    assert any("password" in r for r in p.rechazos), f"rechazos: {p.rechazos}"


# ── 4 (parametrizado x6) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("clave", sorted(
    __import__("services.client_profile", fromlist=["_SECRET_KEYS"])._SECRET_KEYS
))
def test_las_seis_claves_de_secret_keys_se_rechazan(clave):
    """P6 - el copiloto NO toca credenciales, nunca."""
    from services.profile_patch import build_profile_patch

    p = build_profile_patch(
        proyecto="DEMO", base={}, propuesta={"database": {clave: "valor"}}
    )
    assert p.cambios == (), f"{clave} llego a cambios: {p.cambios}"
    assert any(clave in r for r in p.rechazos), f"{clave} sin rechazo. rechazos: {p.rechazos}"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_seccion_sensible_marca_sensible_true():
    from services.profile_patch import build_profile_patch

    for seccion in ("tracker_state_machine", "state_flow", "database"):
        p = build_profile_patch(
            proyecto="DEMO", base={}, propuesta={seccion: {"algo": "nuevo"}}
        )
        assert len(p.cambios) == 1, f"{seccion}: {p.cambios}"
        assert p.cambios[0].sensible is True, f"{seccion} no quedo marcada como sensible"


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_seccion_comun_marca_sensible_false():
    from services.profile_patch import build_profile_patch

    p = build_profile_patch(proyecto="DEMO", base={}, propuesta={"language": {"primary": "python"}})
    assert p.cambios[0].sensible is False


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_confirm_token_es_estable():
    from services.profile_patch import build_profile_patch

    propuesta = {"language": {"primary": "python"}, "code_layout": {"roots": ["src"]}}
    a = build_profile_patch(proyecto="DEMO", base={}, propuesta=json.loads(json.dumps(propuesta)))
    b = build_profile_patch(proyecto="DEMO", base={}, propuesta=json.loads(json.dumps(propuesta)))
    assert a.confirm_token == b.confirm_token
    assert len(a.confirm_token) == 32, f"largo real: {len(a.confirm_token)}"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_confirm_token_cambia_si_cambia_un_valor():
    from services.profile_patch import build_profile_patch

    a = build_profile_patch(proyecto="DEMO", base={}, propuesta={"language": {"primary": "python"}})
    b = build_profile_patch(proyecto="DEMO", base={}, propuesta={"language": {"primary": "csharp"}})
    assert a.confirm_token != b.confirm_token


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_confirm_token_no_depende_del_orden_de_las_keys():
    from services.profile_patch import build_profile_patch

    uno = {"language": {"primary": "python"}, "build": {"command": "make"}}
    otro = {"build": {"command": "make"}, "language": {"primary": "python"}}
    a = build_profile_patch(proyecto="DEMO", base={}, propuesta=uno)
    b = build_profile_patch(proyecto="DEMO", base={}, propuesta=otro)
    assert a.confirm_token == b.confirm_token, (
        f"el token depende del orden: {a.confirm_token} vs {b.confirm_token}"
    )


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_aplicar_sobre_no_muta_la_base():
    from services.profile_patch import aplicar_sobre, build_profile_patch

    base = {"language": {"primary": "csharp"}, "build": {"command": "make"}}
    antes = json.dumps(base, sort_keys=True)
    p = build_profile_patch(proyecto="DEMO", base=base, propuesta={"language": {"primary": "python"}})
    aplicar_sobre(base, p)
    assert json.dumps(base, sort_keys=True) == antes, "aplicar_sobre muto la base"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_aplicar_sobre_preserva_secciones_no_tocadas():
    from services.profile_patch import aplicar_sobre, build_profile_patch

    base = {"build": {"command": "make"}, "language": {"primary": "csharp"}}
    p = build_profile_patch(proyecto="DEMO", base=base, propuesta={"language": {"primary": "python"}})
    resultado = aplicar_sobre(base, p)
    assert resultado["build"] == {"command": "make"}, f"resultado: {resultado}"
    assert resultado["language"]["primary"] == "python"


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_no_dict_en_seccion_tipada_va_a_rechazos():
    from services.profile_patch import build_profile_patch

    p = build_profile_patch(proyecto="DEMO", base={}, propuesta={"code_layout": ["src"]})
    assert p.cambios == (), f"cambios: {p.cambios}"
    assert any("code_layout" in r for r in p.rechazos), f"rechazos: {p.rechazos}"


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_endpoint_propose_no_escribe(env, monkeypatch):
    import services.client_profile as cp

    def _boom(*a, **kw):
        raise AssertionError("propose es READ-ONLY")

    monkeypatch.setattr(cp, "save_client_profile", _boom)
    _sembrar(env)
    app = _app(monkeypatch, flag=True)
    r = app.test_client().post(_URL, json={"propuesta": {"language": {"primary": "python"}}})
    assert r.status_code == 200, f"status real: {r.status_code} body={r.get_json()!r}"
    assert r.get_json()["patch"]["cambios"], "el patch vino vacio"


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_endpoint_propose_devuelve_validacion_previa_del_resultado(env, monkeypatch):
    """El usuario ve el diff Y el veredicto de validacion del RESULTADO, antes de
    decidir. Si no valida, el boton de aplicar queda deshabilitado CON motivo."""
    _sembrar(env)
    app = _app(monkeypatch, flag=True)
    r = app.test_client().post(
        _URL, json={"propuesta": {"tracker_state_machine": {"functional": ["New"]}}}
    )
    assert r.status_code == 200, f"status real: {r.status_code}"
    validacion = r.get_json()["validacion_previa"]
    assert validacion["ok"] is False, f"validacion_previa: {validacion}"
    assert any("tracker_state_machine" in e for e in validacion["errors"]), (
        f"errors no menciona la seccion: {validacion['errors']}"
    )


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_endpoint_propose_404_con_flag_off(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch, flag=False)
    r = app.test_client().post(_URL, json={"propuesta": {}})
    assert r.status_code == 404, f"status real: {r.status_code}"
