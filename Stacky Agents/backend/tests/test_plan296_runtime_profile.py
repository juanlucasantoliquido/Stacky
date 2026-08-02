"""tests/test_plan296_runtime_profile.py - Plan 296 F1.

La ficha COMPLETA de cada runtime: 7 de 7 campos, disponibilidad medida SIN
disparar una corrida y SIN depender del gate de preflight en ninguno de sus dos
estados.

17 casos declarados; el #2 esta parametrizado sobre los dos estados de la flag
=> 17 - 1 + 2 = 18 colectados.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

_BACKEND = pathlib.Path(__file__).resolve().parents[1]


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_ficha_tiene_los_siete_campos_para_los_tres_runtimes():
    """K1: 2 de 7 -> 7 de 7."""
    from services.runtime_capabilities import RUNTIMES
    from services.runtime_profile import FICHA_CAMPOS, runtime_profile

    assert len(FICHA_CAMPOS) == 7, f"FICHA_CAMPOS tiene {len(FICHA_CAMPOS)} campos"
    for r in RUNTIMES:
        ficha = runtime_profile(r)
        faltantes = [c for c in FICHA_CAMPOS if c not in ficha]
        assert faltantes == [], f"{r}: la ficha no trae {faltantes}"


# ── 2 (parametrizado x2) ─────────────────────────────────────────────────────
@pytest.mark.parametrize("gate", [True, False])
def test_disponibilidad_no_depende_del_gate_de_preflight(monkeypatch, gate):
    """K2 - `run_preflight.check` devuelve ok=True SIN VERIFICAR NADA cuando
    STACKY_RUN_PREFLIGHT_GATE_ENABLED esta OFF (run_preflight.py:82-83). Una
    lectura de disponibilidad basada en `check()` mentiria. Esta ficha no lo usa,
    y se verifica en LOS DOS estados de la flag."""
    import config as _config_mod
    from services import run_preflight
    from services.runtime_profile import runtime_profile

    monkeypatch.setattr(
        _config_mod.config, "STACKY_RUN_PREFLIGHT_GATE_ENABLED", gate, raising=False
    )
    monkeypatch.setattr(run_preflight, "_binary_resolvable", lambda _: False)

    ficha = runtime_profile("codex_cli")
    assert ficha["disponible"] is False, (
        f"con el gate={gate} y el binario irresoluble, la ficha dijo "
        f"disponible={ficha['disponible']!r}; motivo={ficha['disponibilidad_motivo']!r}"
    )
    assert ficha["disponibilidad_motivo"], "un no-disponible sin motivo es una ausencia muda"


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_disponibilidad_no_dispara_ninguna_corrida(monkeypatch):
    import agent_runner
    from services.runtime_profile import all_runtime_profiles

    def _boom(*a, **kw):
        raise AssertionError("no debe correrse")

    monkeypatch.setattr(agent_runner, "run_agent", _boom)
    fichas = all_runtime_profiles()
    assert len(fichas) == 3


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_copilot_no_requiere_binario_ni_repo():
    from services.runtime_profile import binary_availability

    d = binary_availability("github_copilot")
    assert d["requiere_binario"] is False
    assert d["requiere_repo_git"] is False


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_cli_requieren_repo_git():
    from services.runtime_profile import binary_availability

    for r in ("claude_code_cli", "codex_cli"):
        assert binary_availability(r)["requiere_repo_git"] is True, f"{r}"


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_exige_agente_vscode_es_true_solo_para_los_dos_cli():
    """C2 - MEDIDO: solo api/agents.py:480 rechaza. Los otros tres caminos
    auto-rellenan."""
    from services.runtime_profile import EXIGE_AGENTE_VSCODE

    assert EXIGE_AGENTE_VSCODE["github_copilot"] is False
    assert EXIGE_AGENTE_VSCODE["claude_code_cli"] is True
    assert EXIGE_AGENTE_VSCODE["codex_cli"] is True


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_exige_agente_vscode_declara_su_alcance():
    """C2 - un plan que se llama 'con los ojos abiertos' no puede exagerar una
    exigencia: el alcance tiene que estar escrito."""
    from services.runtime_profile import runtime_profile

    alcance = runtime_profile("codex_cli")["capacidades"]["exige_agente_vscode_alcance"]
    assert alcance and alcance.strip(), "alcance vacio"
    bajo = alcance.lower()
    assert "picas" in bajo or "pica" in bajo, f"el alcance no menciona las epicas: {alcance!r}"
    assert "incidencia" in bajo, f"el alcance no menciona las incidencias: {alcance!r}"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_agente_vscode_por_defecto_trae_los_tres_caminos():
    """C2 - api/agents.py:858, :1069, :1261 auto-rellenan."""
    from services.runtime_profile import AGENTE_VSCODE_POR_DEFECTO

    assert set(AGENTE_VSCODE_POR_DEFECTO.values()) == {
        "BusinessAgent.agent.md",
        "IncidentAnalyst.agent.md",
        "IncidentDevResolver.agent.md",
    }, f"valores reales: {sorted(AGENTE_VSCODE_POR_DEFECTO.values())}"


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_asistencia_llm_es_la_misma_para_los_tres():
    """Correccion v2: LLM_BACKEND es un eje DISTINTO del runtime elegido."""
    from services.runtime_capabilities import RUNTIMES
    from services.runtime_profile import runtime_profile

    vistas = [runtime_profile(r)["capacidades"]["asistencia_llm"] for r in RUNTIMES]
    assert vistas[0] == vistas[1] == vistas[2], f"asistencia_llm difiere por runtime: {vistas}"
    motivo = vistas[0]["motivo"]
    assert motivo and "LLM_BACKEND" in motivo, f"el motivo no nombra LLM_BACKEND: {motivo!r}"


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_asistencia_llm_nunca_lanza_sin_config(monkeypatch):
    from services.runtime_profile import asistencia_llm

    class _ConfigInaccesible:
        def __getattr__(self, nombre):
            raise RuntimeError("config inaccesible")

    monkeypatch.setitem(sys.modules, "config", _ConfigInaccesible())
    d = asistencia_llm()
    assert d["llm_backend"] == "desconocido", f"llm_backend={d['llm_backend']!r}"


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_runtime_desconocido_devuelve_ficha_completa_y_no_disponible():
    from services.runtime_profile import FICHA_CAMPOS, runtime_profile

    ficha = runtime_profile("gpt5_cli")
    faltantes = [c for c in FICHA_CAMPOS if c not in ficha]
    assert faltantes == [], f"ficha incompleta para un runtime desconocido: {faltantes}"
    assert ficha["conocido"] is False
    assert ficha["disponible"] is False
    assert ficha["disponibilidad_motivo"], "sin motivo es una ausencia muda"


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_binary_availability_nunca_lanza(monkeypatch):
    from services import run_preflight
    from services.runtime_profile import binary_availability

    def _boom(*a, **kw):
        raise RuntimeError("resolucion rota")

    monkeypatch.setattr(run_preflight, "_get_runtime_bin", _boom)
    d = binary_availability("codex_cli")
    assert d["binario_resoluble"] is False, f"devolvio {d!r}"


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_recomendar_no_devuelve_runtime_no_disponible():
    from services.runtime_capabilities import RUNTIMES
    from services.runtime_profile import recomendar_runtime

    fichas = [{"runtime": r, "disponible": False} for r in RUNTIMES]
    assert recomendar_runtime(fichas)["runtime"] is None


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_recomendar_explica_el_motivo():
    from services.runtime_profile import recomendar_runtime

    uno = [
        {"runtime": "claude_code_cli", "disponible": False},
        {"runtime": "codex_cli", "disponible": False},
        {"runtime": "github_copilot", "disponible": True},
    ]
    varios = [
        {"runtime": "claude_code_cli", "disponible": True},
        {"runtime": "codex_cli", "disponible": True},
        {"runtime": "github_copilot", "disponible": True},
    ]
    ninguno = [{"runtime": r, "disponible": False} for r in
               ("claude_code_cli", "codex_cli", "github_copilot")]

    r_uno = recomendar_runtime(uno)
    assert r_uno["runtime"] == "github_copilot"
    assert r_uno["motivo"], "sin motivo"

    r_varios = recomendar_runtime(varios)
    assert r_varios["runtime"] == "claude_code_cli", (
        f"con varios disponibles gana el primero del orden de RUNTIMES; "
        f"devolvio {r_varios['runtime']!r}"
    )
    assert r_varios["motivo"], "sin motivo"

    r_ninguno = recomendar_runtime(ninguno)
    assert r_ninguno["runtime"] is None
    assert r_ninguno["motivo"], "sin motivo"


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_capacidades_conserva_las_once_claves_de_capabilities_for():
    from services.runtime_capabilities import RUNTIMES, capabilities_for
    from services.runtime_profile import runtime_profile

    for r in RUNTIMES:
        base = set(capabilities_for(r))
        assert len(base) == 11, f"capabilities_for({r}) devolvio {len(base)} claves"
        perdidas = base - set(runtime_profile(r)["capacidades"])
        assert perdidas == set(), f"{r}: la ficha perdio {sorted(perdidas)}"


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_no_importa_la_capa_web():
    """C5 - por AST, NO por texto. El gate por `"api." not in getsource(...)` era
    False por construccion: el docstring del propio modulo nombra el patron."""
    from services import runtime_profile

    src = pathlib.Path(runtime_profile.__file__).read_text(encoding="utf-8")
    arbol = ast.parse(src)
    ofensores: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            ofensores += [a.name for a in nodo.names if a.name.split(".")[0] == "api"]
        elif isinstance(nodo, ast.ImportFrom):
            if (nodo.module or "").split(".")[0] == "api":
                ofensores.append(nodo.module)
    assert ofensores == [], f"services/ no puede importar api/. Ofensores: {ofensores}"


# ── 17 ───────────────────────────────────────────────────────────────────────
def test_cada_campo_declarativo_tiene_su_anclaje_vivo():
    """[ADICION ARQUITECTO] - la ficha no puede envejecer mintiendo. Si alguien
    renombra el error, cambia el default o borra la rama, la ficha se pone ROJA
    en vez de mentir. Es el antidoto directo al defecto que hundio a C2."""
    from services.runtime_profile import FICHA_ANCLAJES

    assert len(FICHA_ANCLAJES) == 10, f"se esperaban 10 anclajes, hay {len(FICHA_ANCLAJES)}"
    muertos: list[str] = []
    for ruta, literal, campo in FICHA_ANCLAJES:
        archivo = _BACKEND / ruta
        if not archivo.is_file():
            muertos.append(f"{ruta} (archivo inexistente) -> {campo}")
            continue
        if literal not in archivo.read_text(encoding="utf-8", errors="ignore"):
            muertos.append(f"{ruta}::{literal!r} -> {campo}")
    assert muertos == [], f"Anclajes de la ficha que ya no existen en el codigo: {muertos}"
