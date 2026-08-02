"""tests/test_plan296_session.py - Plan 296 F3.

La sesion como maquina de estados cerrada, el runtime PEGADO a la sesion, y el
turno. 21 casos declarados, 21 colectados (sin parametrize).

FIXTURE DE AISLAMIENTO OBLIGATORIA (C6): `save_client_profile` escribe directo
en `projects_dir()/<NAME>/config.json` SIN pasar por el seam de lectura, y
`record_event` anexa a `data/config_transfer_events.jsonl`. Sin los DOS setattr
(`client_profile.projects_dir` Y `project_manager.PROJECTS_DIR`) mas el
monkeypatch de `record_event`, un pytest de este archivo pisaria el config.json
REAL de un proyecto del operador. Molde calcado de tests/test_client_profile.py:18-32.

MOLDE DE APP (C17): no hay fixture `app`/`client` en tests/conftest.py; cada
archivo construye la suya con create_app() + flip de flag + TESTING=True +
restauracion en el yield. Molde: tests/test_plan93_preflight_endpoint.py:25-45.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_FLAG = "STACKY_PROFILE_COPILOT_ENABLED"


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


def _sembrar(env, nombre="DEMO", *, perfil=None, tracker="azure_devops"):
    carpeta = env["projects_dir"] / nombre.upper()
    carpeta.mkdir(parents=True, exist_ok=True)
    cfg = {"name": nombre, "issue_tracker": {"type": tracker}}
    if perfil is not None:
        cfg["client_profile"] = perfil
    (carpeta / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return nombre


def _app(monkeypatch, *, flag=True):
    import config as cfg
    from app import create_app

    monkeypatch.setattr(cfg.config, _FLAG, flag, raising=False)
    app = create_app()
    app.config["TESTING"] = True
    return app


# ── Maquina de estados (modulo puro) ─────────────────────────────────────────

# 1
def test_estado_inicial_es_eleccion_de_runtime():
    from services.profile_copilot_session import ProfileCopilotSession

    assert ProfileCopilotSession().state == "eleccion_runtime"


# 2
def test_sin_runtime_no_se_puede_diagnosticar():
    from services.profile_copilot_session import ProfileCopilotSession, advance

    s = ProfileCopilotSession()
    nueva, motivo = advance(s, "preguntando")
    assert motivo == "transicion_ilegal", f"motivo real: {motivo!r}"
    assert nueva.state == "eleccion_runtime"


# 3
def test_elegir_runtime_valido_pasa_a_diagnostico():
    from services.profile_copilot_session import ProfileCopilotSession, elegir_runtime

    s, motivo = elegir_runtime(ProfileCopilotSession(), "codex_cli", explicito=False)
    assert motivo == "", f"motivo real: {motivo!r}"
    assert s.state == "diagnostico"
    assert s.runtime_elegido == "codex_cli"


# 4
def test_elegir_runtime_desconocido_devuelve_motivo():
    from services.profile_copilot_session import ProfileCopilotSession, elegir_runtime

    base = ProfileCopilotSession()
    s, motivo = elegir_runtime(base, "gpt5_cli", explicito=True)
    assert motivo == "runtime_desconocido", f"motivo real: {motivo!r}"
    assert s == base, "la sesion cambio pese al runtime desconocido"


# 5
def test_cambio_de_runtime_sin_bandera_no_cambia_nada():
    """P4 - el candado. Ni siquiera en fallo se cambia de runtime solo."""
    from services.profile_copilot_session import ProfileCopilotSession, elegir_runtime

    base = ProfileCopilotSession(state="diagnostico", runtime_elegido="claude_code_cli")
    s, motivo = elegir_runtime(base, "codex_cli", explicito=False)
    assert motivo == "cambio_de_runtime_requiere_confirmacion", f"motivo real: {motivo!r}"
    assert s.runtime_elegido == "claude_code_cli", f"cambio solo a {s.runtime_elegido!r}"


# 6
def test_cambio_de_runtime_con_bandera_explicita_si_cambia():
    from services.profile_copilot_session import ProfileCopilotSession, elegir_runtime

    base = ProfileCopilotSession(state="diagnostico", runtime_elegido="claude_code_cli")
    s, motivo = elegir_runtime(base, "codex_cli", explicito=True)
    assert motivo == "", f"motivo real: {motivo!r}"
    assert s.runtime_elegido == "codex_cli"


# 7
def test_advance_ignora_campos_inventados():
    from services.profile_copilot_session import ProfileCopilotSession, advance

    s = ProfileCopilotSession(state="diagnostico", runtime_elegido="codex_cli")
    nueva, motivo = advance(s, "preguntando", campo_inventado=1)
    assert motivo == ""
    assert not hasattr(nueva, "campo_inventado")
    assert nueva.state == "preguntando"


# 8
def test_advance_desde_terminal_no_hace_nada():
    from services.profile_copilot_session import ProfileCopilotSession, advance

    s = ProfileCopilotSession(state="aplicado")
    nueva, motivo = advance(s, "preguntando")
    assert motivo == "estado_terminal", f"motivo real: {motivo!r}"
    assert nueva is s or nueva == s


# 9
def test_can_transition_nunca_lanza():
    from services.profile_copilot_session import can_transition

    for origen in (None, 123, "", "inventado"):
        for destino in (None, 123, "", "diagnostico"):
            assert can_transition(origen, destino) in (True, False)


# 10
def test_session_from_dict_ignora_claves_desconocidas_y_no_lanza():
    from services.profile_copilot_session import session_from_dict

    s = session_from_dict({"state": "diagnostico", "runtime_elegido": "codex_cli",
                           "clave_inventada": [1, 2, 3]})
    assert s.state == "diagnostico"
    assert s.runtime_elegido == "codex_cli"
    assert not hasattr(s, "clave_inventada")
    for basura in (None, 42, "texto", [], {"state": "inexistente"}):
        assert session_from_dict(basura).state == "eleccion_runtime"


# 11
def test_round_trip_dict():
    from services.profile_copilot_session import (
        ProfileCopilotSession,
        session_from_dict,
        session_to_dict,
    )

    s = ProfileCopilotSession(
        state="preguntando", proyecto="DEMO", runtime_elegido="codex_cli",
        tracker_type="azure_devops", pregunta_actual="language.primary",
        respondidas=("code_layout.roots",),
        respuestas=(("code_layout.roots", "src"),),
        patch_ref="abc", turnos=3,
    )
    assert session_from_dict(session_to_dict(s)) == s


# 12
def test_sesion_serializada_entra_en_el_tope():
    from services.profile_copilot_session import (
        MAX_SESSION_BYTES,
        ProfileCopilotSession,
        session_to_dict,
    )

    respuestas = tuple((f"p{i}", "x" * 100) for i in range(40))
    s = ProfileCopilotSession(
        state="preguntando", proyecto="DEMO", runtime_elegido="codex_cli",
        respondidas=tuple(f"p{i}" for i in range(40)), respuestas=respuestas, turnos=40,
    )
    tamano = len(json.dumps(session_to_dict(s), ensure_ascii=False))
    assert tamano <= MAX_SESSION_BYTES, (
        f"una sesion llena mide {tamano} bytes y el tope es {MAX_SESSION_BYTES}"
    )


# ── Endpoints ────────────────────────────────────────────────────────────────

# 13
def test_endpoint_ficha_404_con_flag_off(env, monkeypatch):
    app = _app(monkeypatch, flag=False)
    r = app.test_client().get("/api/runtimes/profile")
    assert r.status_code == 404, f"status real: {r.status_code}"


# 14
def test_endpoint_ficha_devuelve_tres_fichas_con_flag_on(env, monkeypatch):
    app = _app(monkeypatch, flag=True)
    r = app.test_client().get("/api/runtimes/profile")
    assert r.status_code == 200, f"status real: {r.status_code}"
    body = r.get_json()
    assert len(body["runtimes"]) == 3, f"fichas: {len(body['runtimes'])}"
    assert "recomendacion" in body


# 15
def test_las_rutas_finales_son_las_declaradas(env, monkeypatch):
    """C7 - api_bp YA pone /api. Copiar la URL final al decorador produce
    /api/api/... y todos los tests de endpoint fallan sin explicacion."""
    import re

    app = _app(monkeypatch, flag=True)
    reglas = {str(r.rule) for r in app.url_map.iter_rules()}
    # Werkzeug conserva el conversor en el texto de la regla
    # (`/api/projects/<string:project_name>/...`). Se normaliza para comparar
    # contra la URL tal como la escribe el cliente HTTP.
    normalizadas = {re.sub(r"<[a-z]+:", "<", s) for s in reglas}

    esperadas = {
        "/api/runtimes/profile",
        "/api/projects/<project_name>/client-profile/copilot/state",
        "/api/projects/<project_name>/client-profile/copilot/turn",
    }
    faltantes = esperadas - normalizadas
    assert faltantes == set(), (
        f"rutas del copiloto que no existen: {sorted(faltantes)}. "
        f"Reglas con 'copilot/' registradas: "
        f"{sorted(x for x in normalizadas if 'copilot/' in x)}"
    )

    # DEUDA AJENA MEDIDA en el commit base: `api/ado_manager.py:40` declara
    # `@bp.post("/api/projects/<project_name>/tasks")` con el "/api" puesto a
    # mano y api_bp lo vuelve a poner. Existe desde 45d7dc45 (2026-05-26), es de
    # otro modulo y corregirlo cambiaria una URL que ya tiene consumidor: queda
    # DECLARADA como baseline congelado, no borrada. El criterio es DELTA
    # (mismo trato que el plan le da a las suites rojas de fabrica): este plan no
    # puede agregar ni una regla nueva con /api/api/.
    _DEUDA_API_API = {"/api/api/projects/<project_name>/tasks"}
    dobles = {x for x in normalizadas if x.startswith("/api/api/")}
    nuevas = dobles - _DEUDA_API_API
    assert nuevas == set(), (
        f"reglas NUEVAS con /api/api/: {sorted(nuevas)}. "
        f"api_bp ya pone el prefijo: el decorador no lo lleva."
    )
    assert not any("copilot" in x or "runtimes" in x for x in dobles), (
        f"el copiloto del 296 duplico el prefijo: {sorted(dobles)}"
    )


# 16
def test_endpoint_turn_rechaza_runtime_desconocido_con_400_y_lista_validos(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch, flag=True)
    r = app.test_client().post(
        "/api/projects/DEMO/client-profile/copilot/turn", json={"runtime": "gpt5_cli"}
    )
    assert r.status_code == 400, f"status real: {r.status_code}"
    body = r.get_json()
    assert body["error"] == "runtime_desconocido", f"error real: {body!r}"
    assert "claude_code_cli" in body["validos"], f"validos: {body.get('validos')}"


# 17
def test_endpoint_turn_409_al_cambiar_runtime_sin_bandera(env, monkeypatch):
    _sembrar(env)
    app = _app(monkeypatch, flag=True)
    c = app.test_client()

    primero = c.post("/api/projects/DEMO/client-profile/copilot/turn",
                     json={"runtime": "claude_code_cli"})
    assert primero.status_code == 200, f"status real: {primero.status_code}"
    sesion = primero.get_json()["session"]

    segundo = c.post("/api/projects/DEMO/client-profile/copilot/turn",
                     json={"session": sesion, "runtime": "codex_cli"})
    assert segundo.status_code == 409, f"status real: {segundo.status_code}"
    body = segundo.get_json()
    assert body["error"] == "cambio_de_runtime_requiere_confirmacion", f"body: {body!r}"
    assert body["runtime_elegido"] == "claude_code_cli", (
        f"el 409 reporto {body.get('runtime_elegido')!r} en vez del original"
    )


# 18
def test_endpoint_turn_sesion_demasiado_grande_da_400(env, monkeypatch):
    from services.profile_copilot_session import MAX_SESSION_BYTES

    _sembrar(env)
    app = _app(monkeypatch, flag=True)
    gorda = {"state": "diagnostico", "runtime_elegido": "codex_cli",
             "motivo_detencion": "z" * (MAX_SESSION_BYTES + 100)}
    r = app.test_client().post("/api/projects/DEMO/client-profile/copilot/turn",
                               json={"session": gorda})
    assert r.status_code == 400, f"status real: {r.status_code}"
    assert r.get_json()["error"] == "sesion_demasiado_grande", f"body: {r.get_json()!r}"


# 19
def test_endpoint_turn_proyecto_inexistente_da_404(env, monkeypatch):
    app = _app(monkeypatch, flag=True)
    r = app.test_client().post("/api/projects/NOEXISTE/client-profile/copilot/turn",
                               json={"runtime": "codex_cli"})
    assert r.status_code == 404, f"status real: {r.status_code}"
    assert r.get_json()["error"] == "Proyecto 'NOEXISTE' no encontrado", (
        f"texto real: {r.get_json()!r}"
    )


# 20
def test_endpoint_turn_no_escribe_el_perfil(env, monkeypatch):
    import services.client_profile as cp

    def _boom(*a, **kw):
        raise AssertionError("el turno NO puede escribir el perfil")

    monkeypatch.setattr(cp, "save_client_profile", _boom)

    _sembrar(env)
    app = _app(monkeypatch, flag=True)
    c = app.test_client()
    sesion = None
    for _ in range(5):
        r = c.post("/api/projects/DEMO/client-profile/copilot/turn",
                   json={"session": sesion, "runtime": "codex_cli", "respuesta": "src"})
        assert r.status_code == 200, f"status real: {r.status_code} body={r.get_json()!r}"
        sesion = r.get_json()["session"]


# 21
def test_state_pasa_los_procesos_detectados_al_banco(env, monkeypatch):
    """C1 - el endpoint arma `procesos_detectados` desde las MISMAS dos fuentes
    de services/ que usa la ruta autodetect_process_catalog, y se lo pasa al
    banco. Con las fuentes caidas la pregunta degrada a texto libre y el
    endpoint sigue respondiendo 200."""
    import api.profile_copilot as pc

    _sembrar(env)
    app = _app(monkeypatch, flag=True)

    monkeypatch.setattr(pc, "_procesos_detectados", lambda _p: ("Mul2Bane",))
    r = app.test_client().get("/api/projects/DEMO/client-profile/copilot/state")
    assert r.status_code == 200, f"status real: {r.status_code}"
    preguntas = r.get_json()["preguntas"]
    procesos = [p for p in preguntas if p["seccion"] == "process_catalog"]
    assert len(procesos) == 1, f"preguntas de procesos: {len(procesos)}"
    assert procesos[0]["tipo"] == "eleccion", f"tipo real: {procesos[0]['tipo']!r}"
    assert "Mul2Bane" in procesos[0]["opciones"], f"opciones: {procesos[0]['opciones']}"

    def _revienta(_p):
        raise RuntimeError("fuente caida")

    monkeypatch.setattr(pc, "_procesos_detectados", _revienta)
    r2 = app.test_client().get("/api/projects/DEMO/client-profile/copilot/state")
    assert r2.status_code == 200, f"status real: {r2.status_code}"
    procesos2 = [p for p in r2.get_json()["preguntas"] if p["seccion"] == "process_catalog"]
    assert procesos2[0]["tipo"] == "texto", f"tipo real: {procesos2[0]['tipo']!r}"
