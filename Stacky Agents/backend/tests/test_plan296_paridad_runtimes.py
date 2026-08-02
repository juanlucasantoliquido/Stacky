"""tests/test_plan296_paridad_runtimes.py - Plan 296 F7.

Paridad de los 3 runtimes, la deuda del comentario, y la VERIFICACION de los
guardianes (C15: F0..F5 ya los registraron; esta fase no los crea, los verifica).

13 casos declarados; el #4 y el #5 estan parametrizados sobre RUNTIMES (3 cada
uno) => 13 - 2 + 6 = 17 colectados.

FIXTURE DE AISLAMIENTO (C6): los casos 6 y 7 recorren `apply`.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_FLAG = "STACKY_PROFILE_COPILOT_ENABLED"
_FLAG_APPLY = "STACKY_PROFILE_COPILOT_APPLY_ENABLED"

_LOS_SIETE = (
    "tests/test_plan296_flags.py",
    "tests/test_plan296_runtime_profile.py",
    "tests/test_plan296_completitud.py",
    "tests/test_plan296_session.py",
    "tests/test_plan296_propuesta.py",
    "tests/test_plan296_apply.py",
    "tests/test_plan296_paridad_runtimes.py",
)


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
    carpeta = pdir / "DEMO"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "config.json").write_text(
        json.dumps({"name": "DEMO", "issue_tracker": {"type": "azure_devops"}}),
        encoding="utf-8",
    )
    return {"projects_dir": pdir, "eventos": eventos}


def _app(monkeypatch, *, flag=True, apply_flag=True):
    import config as cfg
    from app import create_app

    monkeypatch.setattr(cfg.config, _FLAG, flag, raising=False)
    monkeypatch.setattr(cfg.config, _FLAG_APPLY, apply_flag, raising=False)
    app = create_app()
    app.config["TESTING"] = True
    return app


def _url(sufijo: str) -> str:
    return f"/api/projects/DEMO/client-profile/copilot/{sufijo}"


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_fallo_no_cambia_el_runtime_elegido(env, monkeypatch):
    """K5 - ante un fallo del runtime elegido, `runtime_elegido` queda INTACTO y
    `cambio_sugerido` aparece SIN haberse aplicado."""
    import services.runtime_profile as rp

    original = rp.binary_availability

    def _roto(runtime: str):
        d = original(runtime)
        if runtime == "codex_cli":
            d = dict(d, requiere_binario=True, binario="codex", binario_resoluble=False)
        return d

    monkeypatch.setattr(rp, "binary_availability", _roto)

    app = _app(monkeypatch)
    r = app.test_client().post(_url("turn"), json={"runtime": "codex_cli"})
    assert r.status_code == 200, f"status real: {r.status_code} body={r.get_json()!r}"
    body = r.get_json()
    assert body["runtime_elegido"] == "codex_cli", (
        f"el fallo cambio el runtime a {body['runtime_elegido']!r}"
    )
    assert body["session"]["runtime_elegido"] == "codex_cli"
    assert body["advertencia"], "un runtime no disponible sin advertencia es una ausencia muda"
    if body["cambio_sugerido"] is not None:
        assert body["cambio_sugerido"]["runtime"] != "codex_cli"
        assert body["cambio_sugerido"]["motivo"], "sugerencia sin motivo"


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_cambio_de_runtime_exige_bandera_explicita(env, monkeypatch):
    app = _app(monkeypatch)
    c = app.test_client()
    primero = c.post(_url("turn"), json={"runtime": "claude_code_cli"})
    assert primero.status_code == 200, f"status real: {primero.status_code}"
    sesion = primero.get_json()["session"]

    segundo = c.post(_url("turn"), json={"session": sesion, "runtime": "codex_cli"})
    assert segundo.status_code == 409, f"status real: {segundo.status_code}"
    assert segundo.get_json()["runtime_elegido"] == "claude_code_cli"
    assert sesion["runtime_elegido"] == "claude_code_cli", "la sesion enviada se mutó"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_la_preferencia_persistida_no_cambia_ante_un_fallo(env, monkeypatch):
    import api.profile_copilot as pc
    import services.runtime_profile as rp

    guardados: list[dict] = []
    monkeypatch.setattr(pc, "save_run_preference",
                        lambda proyecto, sel: guardados.append(dict(sel)) or True)

    original = rp.binary_availability
    monkeypatch.setattr(
        rp, "binary_availability",
        lambda runtime: dict(original(runtime), requiere_binario=True,
                             binario="x", binario_resoluble=False),
    )

    app = _app(monkeypatch)
    c = app.test_client()
    primero = c.post(_url("turn"), json={"runtime": "codex_cli"})
    assert primero.status_code == 200, f"status real: {primero.status_code}"
    sesion = primero.get_json()["session"]
    c.post(_url("turn"), json={"session": sesion, "respuesta": "src"})

    distintos = [g for g in guardados if g.get("runtime") != "codex_cli"]
    assert distintos == [], f"se persistio un runtime distinto ante el fallo: {distintos}"


# ── 4 (parametrizado x3) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("runtime", ["claude_code_cli", "codex_cli", "github_copilot"])
def test_el_motor_conversacional_da_la_misma_pregunta_para_los_tres_runtimes(
    env, monkeypatch, runtime
):
    """La prueba DURA de la paridad determinista: mismo proyecto, mismo estado,
    misma pregunta, con cualquiera de los 3 runtimes."""
    app = _app(monkeypatch)
    r = app.test_client().post(_url("turn"), json={"runtime": runtime})
    assert r.status_code == 200, f"status real: {r.status_code}"
    pregunta = r.get_json()["pregunta"]
    assert pregunta is not None, "el motor no ofrecio ninguna pregunta"
    assert pregunta["id"] == "code_layout.roots", (
        f"con {runtime} la primera pregunta fue {pregunta['id']!r}"
    )


# ── 5 (parametrizado x3) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("runtime", ["claude_code_cli", "codex_cli", "github_copilot"])
def test_el_diff_es_identico_para_los_tres_runtimes(env, monkeypatch, runtime):
    app = _app(monkeypatch)
    sesion = {"state": "diagnostico", "proyecto": "DEMO", "runtime_elegido": runtime}
    r = app.test_client().post(
        _url("propose"),
        json={"session": sesion, "propuesta": {"language": {"primary": "python"}}},
    )
    assert r.status_code == 200, f"status real: {r.status_code}"
    token = r.get_json()["patch"]["confirm_token"]
    # El token es sha256 del patch canonico: si dependiera del runtime, este
    # literal cambiaria por runtime y el caso fallaria para dos de los tres.
    from services.profile_patch import build_profile_patch

    esperado = build_profile_patch(
        proyecto="DEMO", base={}, propuesta={"language": {"primary": "python"}}
    ).confirm_token
    assert token == esperado, f"con {runtime} el token fue {token!r}, se esperaba {esperado!r}"


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_ningun_camino_llama_a_run_agent(env, monkeypatch):
    """C8 - las DOS flags ENCENDIDAS explicitamente y el assert de 200 sobre el
    apply: con la flag de apply OFF el paso 2 corta con 403 antes de tocar nada
    y el gate pasaria POR AUSENCIA DE CAMINO."""
    import agent_runner
    from services.profile_patch import build_profile_patch, patch_to_dict

    def _boom(*a, **kw):
        raise AssertionError("el copiloto del perfil NO puede llamar a run_agent")

    monkeypatch.setattr(agent_runner, "run_agent", _boom)

    app = _app(monkeypatch, flag=True, apply_flag=True)
    c = app.test_client()

    turno = c.post(_url("turn"), json={"runtime": "codex_cli"})
    assert turno.status_code == 200, f"turn: {turno.status_code}"
    sesion = turno.get_json()["session"]

    propuesta = c.post(_url("propose"),
                       json={"session": sesion, "propuesta": {"language": {"primary": "python"}}})
    assert propuesta.status_code == 200, f"propose: {propuesta.status_code}"

    patch = patch_to_dict(build_profile_patch(
        proyecto="DEMO", base={}, propuesta={"language": {"primary": "python"}}
    ))
    aplicar = c.post(_url("apply"), json={
        "session": sesion, "patch": patch,
        "confirm_token": patch["confirm_token"], "confirmaciones_sensibles": [],
    })
    assert aplicar.status_code == 200, (
        f"apply devolvio {aplicar.status_code}: si fuera 403, el gate no probo nada. "
        f"body={aplicar.get_json()!r}"
    )


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_ningun_camino_llama_a_copilot_bridge_invoke(env, monkeypatch):
    """C8 - ancla P3: el motor es DETERMINISTA y no depende de ningun LLM."""
    import copilot_bridge
    from services.profile_patch import build_profile_patch, patch_to_dict

    def _boom(*a, **kw):
        raise AssertionError("el copiloto del perfil NO puede llamar a copilot_bridge.invoke")

    monkeypatch.setattr(copilot_bridge, "invoke", _boom)

    app = _app(monkeypatch, flag=True, apply_flag=True)
    c = app.test_client()

    turno = c.post(_url("turn"), json={"runtime": "github_copilot"})
    assert turno.status_code == 200, f"turn: {turno.status_code}"
    sesion = turno.get_json()["session"]

    propuesta = c.post(_url("propose"),
                       json={"session": sesion, "propuesta": {"language": {"primary": "python"}}})
    assert propuesta.status_code == 200, f"propose: {propuesta.status_code}"

    patch = patch_to_dict(build_profile_patch(
        proyecto="DEMO", base={}, propuesta={"language": {"primary": "python"}}
    ))
    aplicar = c.post(_url("apply"), json={
        "session": sesion, "patch": patch,
        "confirm_token": patch["confirm_token"], "confirmaciones_sensibles": [],
    })
    assert aplicar.status_code == 200, (
        f"apply devolvio {aplicar.status_code}: si fuera 403, el gate no probo nada. "
        f"body={aplicar.get_json()!r}"
    )


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_el_guard_de_llamadas_si_detecta_una_llamada_real(monkeypatch):
    """C8 - CONTRASTE NEGATIVO. Se instala el MISMO guard y se llama a
    run_agent A PROPOSITO: si el guard no lanzara, los casos 6 y 7 serian
    adorno y pasarian por no poder fallar."""
    import agent_runner

    def _boom(*a, **kw):
        raise AssertionError("el copiloto del perfil NO puede llamar a run_agent")

    monkeypatch.setattr(agent_runner, "run_agent", _boom)
    with pytest.raises(AssertionError):
        agent_runner.run_agent(agent_type="x", ticket_id=1, context_blocks=[], user="u")


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_no_hay_ningun_501_en_api_agents():
    """Ancla la correccion del comentario de agent_runner.py:317."""
    ruta = _BACKEND / "api" / "agents.py"
    lineas = ruta.read_text(encoding="utf-8", errors="ignore").splitlines()
    ofensoras = [f"{i}: {l.strip()}" for i, l in enumerate(lineas, 1) if "501" in l]
    assert ofensoras == [], f"api/agents.py menciona 501 en: {ofensoras}"


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_valid_runtimes_de_agents_coincide_con_runtimes_de_capabilities():
    from api.agents import _VALID_RUNTIMES
    from services.runtime_capabilities import RUNTIMES

    assert _VALID_RUNTIMES == set(RUNTIMES), (
        f"_VALID_RUNTIMES={sorted(_VALID_RUNTIMES)} vs RUNTIMES={sorted(RUNTIMES)}"
    )


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_los_dos_ratchets_registran_los_mismos_siete_archivos():
    ps1 = (_BACKEND / "scripts" / "run_harness_tests.ps1").read_text(encoding="utf-8")
    sh = (_BACKEND / "scripts" / "run_harness_tests.sh").read_text(encoding="utf-8")

    patron = re.compile(r"tests/test_plan296_[a-z_]+\.py")
    en_ps1 = set(patron.findall(ps1))
    en_sh = set(patron.findall(sh))

    assert en_ps1 == en_sh, (
        f"los dos ratchets divergen. Diferencia simetrica: "
        f"{sorted(en_ps1.symmetric_difference(en_sh))}"
    )
    assert en_ps1 == set(_LOS_SIETE), (
        f"faltan o sobran archivos del 296 en el ratchet: "
        f"{sorted(set(_LOS_SIETE).symmetric_difference(en_ps1))}"
    )


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_ningun_test_del_296_esta_en_el_allowlist():
    """test_allowlist_no_se_solapa_con_ratchet (test_harness_ratchet_meta.py:56)
    se pone rojo si un archivo esta en los dos lados."""
    allowlist = _BACKEND / "tests" / "harness_ratchet_allowlist.txt"
    texto = allowlist.read_text(encoding="utf-8", errors="ignore") if allowlist.exists() else ""
    ofensores = [nombre for nombre in _LOS_SIETE
                 if pathlib.Path(nombre).name in texto]
    assert ofensores == [], f"archivos del 296 en el allowlist Y en el ratchet: {ofensores}"


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_el_comentario_de_agent_runner_ya_no_dice_bloqueado():
    ruta = _BACKEND / "agent_runner.py"
    lineas = ruta.read_text(encoding="utf-8", errors="ignore").splitlines()
    sobrevive = [f"{i}: {l.strip()}" for i, l in enumerate(lineas, 1)
                 if "bloqueado en endpoint" in l]
    assert sobrevive == [], (
        f"el comentario FALSO sigue vivo (no hay ningun 501 en api/agents.py y "
        f"agent_runner despacha claude_code_cli normalmente): {sobrevive}"
    )
