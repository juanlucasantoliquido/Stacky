"""tests/test_plan296_apply.py - Plan 296 F5.

El copiloto EJECUTA: aplica el diff con confirmacion explicita. Flag OFF de
fabrica, causal (B). 17 casos declarados, 17 colectados.

FIXTURE DE AISLAMIENTO OBLIGATORIA (C6). El problema MEDIDO:
`save_client_profile` NO pasa por el seam de lectura: escribe directo en
`projects_dir()/<NAME>/config.json` (client_profile.py:415) y EXIGE que ese
archivo ya exista (:416-417). Ademas `record_event` anexa a
`data/config_transfer_events.jsonl`. Sin aislar, este archivo o bien da 404 (no
hay proyecto) o PISA el config.json real de un proyecto del operador y deja
rastro en su data/. Molde calcado de tests/test_client_profile.py:18-32.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_FLAG = "STACKY_PROFILE_COPILOT_ENABLED"
_FLAG_APPLY = "STACKY_PROFILE_COPILOT_APPLY_ENABLED"
_URL = "/api/projects/DEMO/client-profile/copilot/apply"

_TRES_REQUERIDAS = {
    "code_layout": {"roots": ["src"]},
    "language": {"primary": "python"},
    "tracker_state_machine": {"functional": {"next_state_ok": "Active"}},
}


@pytest.fixture()
def env(tmp_path, monkeypatch):
    import project_manager
    import services.client_profile as cp

    pdir = tmp_path / "projects"
    pdir.mkdir(parents=True, exist_ok=True)
    # LOS DOS: la escritura sale de projects_dir(); el 404 del endpoint sale de
    # get_project_config(), que mira project_manager.PROJECTS_DIR.
    monkeypatch.setattr(cp, "projects_dir", lambda: pdir)
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", pdir)
    # La auditoria no debe tocar el data/ del operador.
    eventos: list[dict] = []
    monkeypatch.setattr(
        "api.profile_copilot.record_event", lambda **kw: eventos.append(kw) or {}
    )
    return {"projects_dir": pdir, "eventos": eventos, "tmp_path": tmp_path}


def _sembrar(env, nombre="DEMO", *, perfil=None):
    carpeta = env["projects_dir"] / nombre.upper()
    carpeta.mkdir(parents=True, exist_ok=True)
    cfg = {"name": nombre, "issue_tracker": {"type": "azure_devops"}}
    if perfil is not None:
        cfg["client_profile"] = perfil
    (carpeta / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _leer_perfil(env, nombre="DEMO") -> dict:
    ruta = env["projects_dir"] / nombre.upper() / "config.json"
    return json.loads(ruta.read_text(encoding="utf-8")).get("client_profile") or {}


def _app(monkeypatch, *, flag=True, apply_flag=True):
    import config as cfg
    from app import create_app

    monkeypatch.setattr(cfg.config, _FLAG, flag, raising=False)
    monkeypatch.setattr(cfg.config, _FLAG_APPLY, apply_flag, raising=False)
    app = create_app()
    app.config["TESTING"] = True
    return app


def _patch(base: dict, propuesta: dict) -> dict:
    from services.profile_patch import build_profile_patch, patch_to_dict

    return patch_to_dict(build_profile_patch(proyecto="DEMO", base=base, propuesta=propuesta))


_SESION_CONFIRMANDO = {
    "state": "confirmando", "proyecto": "DEMO", "runtime_elegido": "codex_cli",
}


def _body(patch: dict, *, sensibles=(), token=None, sesion=None):
    return {
        "session": dict(sesion or _SESION_CONFIRMANDO),
        "patch": patch,
        "confirm_token": patch["confirm_token"] if token is None else token,
        "confirmaciones_sensibles": list(sensibles),
    }


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_apply_404_con_flag_maestra_off(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch, flag=False, apply_flag=True)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 404, f"status real: {r.status_code}"


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_apply_403_con_flag_de_apply_off_y_nombra_la_flag(env, monkeypatch):
    """403 = FLAG APAGADA, no permiso: Stacky es mono-operador sin roles."""
    _sembrar(env)
    app = _app(monkeypatch, flag=True, apply_flag=False)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 403, f"status real: {r.status_code}"
    body = r.get_json()
    assert body["error"] == "apply_deshabilitado", f"body: {body!r}"
    assert body["flag"] == _FLAG_APPLY, f"flag reportada: {body.get('flag')!r}"
    assert _FLAG_APPLY in json.dumps(body), "el body no nombra la flag que hay que encender"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_apply_con_flag_off_no_escribe(env, monkeypatch):
    import services.client_profile as cp

    def _boom(*a, **kw):
        raise AssertionError("con la flag OFF no se puede escribir")

    monkeypatch.setattr(cp, "save_client_profile", _boom)
    _sembrar(env)
    app = _app(monkeypatch, flag=True, apply_flag=False)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 403, f"status real: {r.status_code}"


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_token_desactualizado_da_409_y_no_escribe(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    p = _patch({}, {"language": {"primary": "python"}})
    r = app.test_client().post(_URL, json=_body(p, token="token-viejo"))
    assert r.status_code == 409, f"status real: {r.status_code}"
    assert r.get_json()["error"] == "patch_desactualizado", f"body: {r.get_json()!r}"
    assert _leer_perfil(env) == {}, "escribio pese al token desactualizado"


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_seccion_sensible_sin_confirmar_da_409_y_no_escribe(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    p = _patch({}, {"tracker_state_machine": {"functional": {"next_state_ok": "Active"}}})
    r = app.test_client().post(_URL, json=_body(p, sensibles=()))
    assert r.status_code == 409, f"status real: {r.status_code}"
    body = r.get_json()
    assert body["error"] == "confirmacion_faltante", f"body: {body!r}"
    assert "tracker_state_machine" in body["secciones"], f"secciones: {body.get('secciones')}"
    assert _leer_perfil(env) == {}, "escribio sin la confirmacion por seccion"


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_seccion_sensible_confirmada_se_aplica(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    p = _patch({}, {"tracker_state_machine": {"functional": {"next_state_ok": "Active"}}})
    r = app.test_client().post(_URL, json=_body(p, sensibles=("tracker_state_machine",)))
    assert r.status_code == 200, f"status real: {r.status_code} body={r.get_json()!r}"
    assert _leer_perfil(env)["tracker_state_machine"]["functional"]["next_state_ok"] == "Active"


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_perfil_invalido_da_400_y_no_escribe(env, monkeypatch):
    """El patch fuerza `code_layout.functional` a una forma que rompe el tipo del
    hijo: el rechazo de F4 no lo ve (code_layout SI es dict) y lo tiene que
    frenar la validacion del paso 8."""
    from services.profile_patch import patch_from_dict

    _sembrar(env)
    app = _app(monkeypatch)
    crudo = {
        "proyecto": "DEMO",
        "cambios": [{"path": ["code_layout"], "existia": False, "antes": None,
                     "despues": ["src"], "motivo": "forzado", "sensible": False}],
        "rechazos": [], "confirm_token": "", "version": "1",
    }
    crudo["confirm_token"] = patch_from_dict(crudo).confirm_token
    r = app.test_client().post(_URL, json=_body(crudo))
    assert r.status_code == 400, f"status real: {r.status_code} body={r.get_json()!r}"
    assert r.get_json()["error"] == "perfil_invalido", f"body: {r.get_json()!r}"
    assert _leer_perfil(env) == {}, "escribio un perfil invalido"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_patch_vacio_da_400(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    r = app.test_client().post(_URL, json=_body(_patch({}, {})))
    assert r.status_code == 400, f"status real: {r.status_code}"
    assert r.get_json()["error"] == "patch_vacio", f"body: {r.get_json()!r}"


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_de_perfil_vacio_a_perfil_valido_en_una_sesion(env, monkeypatch):
    """K3 (reforzado por C12). El TERCER assert es el unico que NO pasaba antes
    del plan: `validate_client_profile({}).ok` ya era True porque las secciones
    requeridas ausentes son WARNINGS, no errors."""
    from services.client_profile import _REQUIRED_SECTIONS, validate_client_profile

    _sembrar(env, perfil={})
    app = _app(monkeypatch)
    p = _patch({}, json.loads(json.dumps(_TRES_REQUERIDAS)))
    r = app.test_client().post(_URL, json=_body(p, sensibles=("tracker_state_machine",)))
    assert r.status_code == 200, f"status real: {r.status_code} body={r.get_json()!r}"

    final = _leer_perfil(env)
    assert set(_REQUIRED_SECTIONS) <= set(final), (
        f"faltan requeridas: {sorted(set(_REQUIRED_SECTIONS) - set(final))}"
    )
    v = validate_client_profile(final)
    assert v.ok is True, f"errors: {v.errors}"
    sobrevivientes = [
        w for w in v.warnings if " ausente" in w and w.startswith("client_profile.")
    ]
    assert sobrevivientes == [], f"warnings de seccion ausente sobrevivientes: {sobrevivientes}"


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_apply_preserva_secciones_no_tocadas(env, monkeypatch):
    previo = {"devops_pipeline_drafts": [{"name": "ci"}], "language": {"primary": "csharp"}}
    _sembrar(env, perfil=previo)
    app = _app(monkeypatch)
    p = _patch(previo, {"language": {"primary": "python"}})
    r = app.test_client().post(_URL, json=_body(p))
    assert r.status_code == 200, f"status real: {r.status_code} body={r.get_json()!r}"

    final = _leer_perfil(env)
    assert final["devops_pipeline_drafts"] == [{"name": "ci"}], f"final: {final}"
    assert final["language"]["primary"] == "python"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_apply_registra_evento_de_auditoria(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    p = _patch({}, {"language": {"primary": "python"}})
    r = app.test_client().post(_URL, json=_body(p))
    assert r.status_code == 200, f"status real: {r.status_code}"

    assert len(env["eventos"]) == 1, f"eventos: {env['eventos']}"
    evento = env["eventos"][0]
    assert evento["action"] == "profile_copilot_apply", f"action: {evento['action']!r}"
    assert evento["detail"]["runtime_elegido"] == "codex_cli", f"detail: {evento['detail']}"
    assert "language.primary" in evento["detail"]["paths"], f"paths: {evento['detail']['paths']}"


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_apply_nunca_escribe_una_clave_de_secret_keys(env, monkeypatch):
    """Doble candado: F4 lo saca del patch; si se FUERZA a mano, el paso 8 lo
    bloquea via validate_client_profile (client_profile.py:285-290)."""
    from services.profile_patch import patch_from_dict

    _sembrar(env)
    app = _app(monkeypatch)
    crudo = {
        "proyecto": "DEMO",
        "cambios": [{"path": ["database", "password"], "existia": False, "antes": None,
                     "despues": "hunter2", "motivo": "forzado a mano", "sensible": True}],
        "rechazos": [], "confirm_token": "", "version": "1",
    }
    crudo["confirm_token"] = patch_from_dict(crudo).confirm_token
    r = app.test_client().post(_URL, json=_body(crudo, sensibles=("database",)))
    assert r.status_code == 400, f"status real: {r.status_code} body={r.get_json()!r}"
    body = r.get_json()
    assert body["error"] == "perfil_invalido", f"body: {body!r}"
    assert any("secretos" in e for e in body["errors"]), f"errors: {body['errors']}"
    assert _leer_perfil(env) == {}, "escribio una credencial"


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_apply_deja_la_sesion_en_estado_terminal(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 200, f"status real: {r.status_code}"
    assert r.get_json()["session"]["state"] == "aplicado", (
        f"estado real: {r.get_json()['session']['state']!r}"
    )


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_apply_no_cambia_el_runtime_elegido(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 200, f"status real: {r.status_code}"
    assert r.get_json()["session"]["runtime_elegido"] == "codex_cli", (
        f"el apply cambio el runtime a {r.get_json()['session']['runtime_elegido']!r}"
    )


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_el_apply_escribe_dentro_de_tmp_path_y_no_fuera(env, monkeypatch):
    """C6 - prueba directa de que el aislamiento es efectivo."""
    import services.client_profile as cp

    _sembrar(env)
    app = _app(monkeypatch)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 200, f"status real: {r.status_code}"

    destino = env["projects_dir"] / "DEMO" / "config.json"
    contenido = json.loads(destino.read_text(encoding="utf-8"))
    assert contenido["client_profile"]["language"]["primary"] == "python"

    resuelto = pathlib.Path(cp.projects_dir()).resolve()
    tmp = pathlib.Path(env["tmp_path"]).resolve()
    assert str(resuelto).startswith(str(tmp)), (
        f"projects_dir() resolvio a {resuelto}, FUERA de {tmp}"
    )


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_la_auditoria_no_toca_el_data_real(env, monkeypatch):
    from runtime_paths import data_dir

    real = pathlib.Path(data_dir())
    antes = sorted(p.name for p in real.iterdir()) if real.is_dir() else []

    _sembrar(env)
    app = _app(monkeypatch)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 200, f"status real: {r.status_code}"

    assert len(env["eventos"]) == 1, f"eventos: {env['eventos']}"
    despues = sorted(p.name for p in real.iterdir()) if real.is_dir() else []
    assert despues == antes, f"aparecieron archivos en el data/ real: {set(despues) - set(antes)}"


# ── 17 ───────────────────────────────────────────────────────────────────────
def test_sin_la_fixture_el_proyecto_no_existe(env, monkeypatch):
    """Prueba de CONTRASTE: sin sembrar DEMO el apply da 404 con el texto de
    api/client_profile.py:170. Demuestra que el aislamiento es efectivo y que el
    404 no viene de otra rama del codigo."""
    app = _app(monkeypatch)
    r = app.test_client().post(_URL, json=_body(_patch({}, {"language": {"primary": "python"}})))
    assert r.status_code == 404, f"status real: {r.status_code}"
    assert r.get_json()["error"] == "Proyecto 'DEMO' no encontrado", (
        f"texto real: {r.get_json()!r}"
    )
