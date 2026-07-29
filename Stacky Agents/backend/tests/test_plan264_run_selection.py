"""Plan 264 F3 — resolve_run_selection(): una sola cascada de precedencia.

Los 11 call sites que hoy no eligen nada (de 17 totales fuera de tests/evals)
pasan a resolver herramienta/modelo/effort por esta misma cascada, sin
duplicar lógica. Precedencia: explícito > preferencia > adaptativo (piso) >
default del catálogo.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import config  # noqa: E402
from services.runtime_capabilities import RUNTIMES, resolve_run_selection  # noqa: E402


@pytest.fixture(autouse=True)
def _prefs_enabled(monkeypatch):
    """Default de este archivo: la flag de preferencias ON (default real del
    plan); los tests puntuales que la necesitan OFF la vuelven a pisar."""
    monkeypatch.setattr(config.config, "STACKY_RUN_SELECTION_PREFS_ENABLED", True)
    monkeypatch.setattr(config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True)


def _stub_preference(monkeypatch, project_name, value):
    """Evita depender del archivo real de preferencias: mockea
    load_run_preference directamente para estos tests de PRECEDENCIA (F4 ya
    prueba el round-trip real contra el store)."""
    import services.runtime_capabilities as rc

    def _fake(pn):
        return value if pn == project_name else None

    monkeypatch.setattr(rc, "load_run_preference", _fake)


# ---------------------------------------------------------------------------
# 1-5 — precedencia
# ---------------------------------------------------------------------------

def test_01_explicito_gana_a_preferencia(monkeypatch):
    _stub_preference(monkeypatch, "proyA", {"model": "claude-haiku-4-5", "effort": "low"})
    sel = resolve_run_selection(
        runtime="claude_code_cli", model="claude-sonnet-5", project_name="proyA",
    )
    assert sel["origen_model"] == "explicito"
    assert sel["model"] == "claude-sonnet-5"


def test_02_preferencia_gana_a_adaptativo(monkeypatch):
    _stub_preference(monkeypatch, "proyA", {"model": None, "effort": "low"})
    sel = resolve_run_selection(
        runtime="claude_code_cli", project_name="proyA", adaptive_effort="high",
    )
    assert sel["origen_effort"] == "preferencia"
    assert sel["effort"] == "low"


def test_03_adaptativo_gana_a_default(monkeypatch):
    _stub_preference(monkeypatch, "proyA", None)
    sel = resolve_run_selection(
        runtime="claude_code_cli", project_name="proyA", adaptive_effort="high",
    )
    assert sel["origen_effort"] == "adaptativo"
    assert sel["effort"] == "high"


def test_04_sin_nada_cae_al_default_normalizado_no_nulo(monkeypatch):
    """[FIX C3] la versión vieja pasaba con None == None y tapaba el catálogo
    vacío de Codex; acá el default tiene que ser NO nulo para todo runtime con
    supports_effort."""
    _stub_preference(monkeypatch, None, None)
    from services.runtime_capabilities import capabilities_for

    for runtime in RUNTIMES:
        caps = capabilities_for(runtime)
        sel = resolve_run_selection(runtime=runtime)
        if caps["supports_effort"]:
            assert sel["origen_effort"] == "default_catalogo"
            assert sel["effort"] == caps["default_effort"]
            assert sel["effort"] is not None, f"{runtime}: default_effort nulo (bug C3)"


def test_05_explicito_no_se_sobreescribe_por_adaptativo(monkeypatch):
    _stub_preference(monkeypatch, None, None)
    sel = resolve_run_selection(
        runtime="claude_code_cli", effort="low", adaptive_effort="high",
    )
    assert sel["effort"] == "low", "el humano no se sobreescribe"


# ---------------------------------------------------------------------------
# 6-7 — runtimes especiales
# ---------------------------------------------------------------------------

def test_06_github_copilot_no_tiene_effort(monkeypatch):
    _stub_preference(monkeypatch, None, None)
    sel = resolve_run_selection(runtime="github_copilot")
    assert sel["effort"] is None
    assert sel["degraded"] is True


def test_07_runtime_desconocido_no_lanza_cae_a_defaults(monkeypatch):
    _stub_preference(monkeypatch, None, None)
    sel = resolve_run_selection(runtime="runtime_inventado")
    assert sel["runtime"] == "runtime_inventado"
    # No lanza y devuelve un dict con las claves del contrato.
    for key in ("model", "effort", "effort_requested", "degraded", "reason",
                "origen_model", "origen_effort"):
        assert key in sel


# ---------------------------------------------------------------------------
# 8 — flag de preferencias OFF: el paso 2 se saltea
# ---------------------------------------------------------------------------

def test_08_flag_prefs_off_never_uses_preferencia(monkeypatch, tmp_path):
    # Con la flag OFF, load_run_preference() real corta ANTES de tocar el
    # store (primer chequeo de su propio cuerpo) — no hace falta stubear un
    # valor: el punto es que ni con datos guardados de verdad se lea.
    import api.preferences as prefs_mod

    monkeypatch.setattr(prefs_mod, "_PREFS_FILE", tmp_path / "preferences.json")
    monkeypatch.setattr(config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True)
    prefs_mod.write_ui_pref("runSelection.proyA", {"model": "claude-haiku-4-5", "effort": "low"})

    monkeypatch.setattr(config.config, "STACKY_RUN_SELECTION_PREFS_ENABLED", False)
    sel = resolve_run_selection(
        runtime="claude_code_cli", project_name="proyA", adaptive_effort="high",
    )
    assert sel["origen_effort"] != "preferencia"
    assert sel["origen_effort"] == "adaptativo"


# ---------------------------------------------------------------------------
# 9 — [KPI-2] cobertura AST: TODAS las llamadas a run_agent( pasan ambos overrides
# ---------------------------------------------------------------------------

# Allowlist máx. 2, con motivo escrito (regla del plan §5 F3).
_ALLOWLIST_RUN_AGENT_CALLS: dict[str, str] = {
    "services/variant_generator.py:188": (
        "Plan 169 — el optimizador de variantes define su propio model/effort "
        "por variante (variant.get('model')); no pasa por la cascada de F3."
    ),
}


def _iter_run_agent_calls(py_files: list[Path]):
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
                if name == "run_agent":
                    yield path, node


def test_09_kpi2_every_run_agent_call_passes_both_overrides():
    scope_dirs = [ROOT / "api", ROOT / "services"]
    scope_dirs.append(ROOT / "agent_runner.py")
    py_files: list[Path] = []
    for d in scope_dirs:
        if d.is_file():
            py_files.append(d)
        else:
            py_files.extend(sorted(d.rglob("*.py")))

    total_calls = 0
    faltantes: list[str] = []
    for path, call in _iter_run_agent_calls(py_files):
        rel = path.relative_to(ROOT).as_posix()
        total_calls += 1
        kw_names = {kw.arg for kw in call.keywords}
        missing = {"model_override", "effort_override"} - kw_names
        if not missing:
            continue
        allow_key = f"{rel}:{call.lineno}"
        if allow_key in _ALLOWLIST_RUN_AGENT_CALLS:
            continue
        faltantes.append(f"{allow_key}: faltan {sorted(missing)}")

    assert total_calls >= 17, f"esperaba >=17 llamadas a run_agent(, hay {total_calls}"
    assert len(_ALLOWLIST_RUN_AGENT_CALLS) <= 2
    assert faltantes == [], "\n".join(faltantes)
