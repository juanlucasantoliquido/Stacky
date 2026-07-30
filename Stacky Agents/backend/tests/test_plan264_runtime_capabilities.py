"""Plan 264 F1 — la única matriz de capacidades de runtime/modelo/effort.

services/runtime_capabilities.py es la ÚNICA fuente de "qué admite cada
herramienta, cómo degrada y qué efecto tiene HOY". Reemplaza las 12 copias de
la lista de efforts y NORMALIZA el catálogo vivo (que hoy trae codex_cli
incompleto: efforts=[], default_effort=None, models=[""]).

Test-first: este archivo se escribe ANTES que el módulo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

import config  # noqa: E402
from services.runtime_capabilities import (  # noqa: E402
    CODEX_EFFORT_TURN_FACTOR,
    EFFORT_MODE,
    EFFORT_ORDER,
    EFFORTS,
    RUNTIMES,
    capabilities_for,
    clamp_selection,
    codex_turn_budget,
    is_valid_effort,
)


# ---------------------------------------------------------------------------
# 1-3 — vocabulario de validación
# ---------------------------------------------------------------------------

def test_01_efforts_tuple_is_the_vocabulary():
    assert EFFORTS == ("low", "medium", "high", "xhigh", "max")
    assert EFFORT_ORDER["low"] < EFFORT_ORDER["max"]
    assert RUNTIMES == ("claude_code_cli", "codex_cli", "github_copilot")


def test_02_is_valid_effort_normalizes_case_and_space():
    assert is_valid_effort("HIGH ") is True


def test_03_is_valid_effort_rejects_bad_values():
    assert is_valid_effort("turbo") is False
    assert is_valid_effort(None) is False
    assert is_valid_effort("") is False


# ---------------------------------------------------------------------------
# 4-8 — capabilities_for
# ---------------------------------------------------------------------------

def test_04_claude_effort_mode_nativo():
    assert capabilities_for("claude_code_cli")["effort_mode"] == "nativo"


def test_05_codex_effort_mode_presupuesto_turnos():
    assert capabilities_for("codex_cli")["effort_mode"] == "presupuesto_turnos"
    assert EFFORT_MODE["codex_cli"] == "presupuesto_turnos"


def test_06_copilot_does_not_support_effort():
    caps = capabilities_for("github_copilot")
    assert caps["supports_effort"] is False
    assert caps["efforts"] == []


def test_07_unknown_runtime_known_false_no_raise():
    caps = capabilities_for("inventado")
    assert caps["known"] is False


def test_08_capabilities_for_survives_catalog_crash(monkeypatch):
    import services.model_catalog as model_catalog

    def _raise(*a, **kw):
        raise RuntimeError("catalogo caido (simulado por el test)")

    monkeypatch.setattr(model_catalog, "load_model_catalog", _raise)
    caps = capabilities_for("claude_code_cli")
    for key in (
        "runtime", "known", "effort_mode", "effort_effective_now",
        "supports_model", "supports_effort", "models", "efforts",
        "default_model", "default_effort", "effort_note",
    ):
        assert key in caps, f"falta la clave {key!r} del contrato"


# ---------------------------------------------------------------------------
# 9-15 — clamp_selection
# ---------------------------------------------------------------------------

def test_09_clamp_opus_without_allow_opus_caps_to_sonnet():
    result = clamp_selection("claude_code_cli", "claude-opus-4-8", "max")
    assert result["model"] == "claude-sonnet-5"
    assert result["degraded"] is True


def test_10_clamp_opus_with_allow_opus_keeps_opus():
    result = clamp_selection(
        "claude_code_cli", "claude-opus-4-8", "max", allow_opus=True
    )
    assert result["model"] == "claude-opus-4-8"


def test_11_clamp_haiku_degrades_effort_to_high():
    result = clamp_selection("claude_code_cli", "claude-haiku-4-5", "max")
    assert result["effort"] == "high"
    assert result["degraded"] is True


def test_12_clamp_copilot_no_effort_at_all():
    result = clamp_selection("github_copilot", None, "high")
    assert result["effort"] is None
    assert result["degraded"] is True
    assert result["reason"]


def test_13_clamp_codex_conserves_requested_effort():
    result = clamp_selection("codex_cli", None, "high")
    assert result["effort"] == "high"


def test_14_clamp_invalid_effort_falls_to_normalized_default():
    result = clamp_selection("claude_code_cli", None, "turbo")
    caps = capabilities_for("claude_code_cli")
    assert result["effort"] == caps["default_effort"]
    assert result["effort"] is not None
    assert result["degraded"] is True


def test_15_effort_requested_always_carries_the_original():
    result = clamp_selection("claude_code_cli", "claude-opus-4-8", "max")
    assert result["effort_requested"] == "max"


# ---------------------------------------------------------------------------
# 16-20 — codex_turn_budget
# ---------------------------------------------------------------------------

def test_16_zero_cap_stays_unlimited_for_every_effort():
    assert codex_turn_budget("max", 0) == 0
    assert codex_turn_budget("low", 0) == 0


def test_17_budget_never_exceeds_cap():
    for e in EFFORTS:
        assert codex_turn_budget(e, 40) <= 40


def test_18_low_is_strictly_less_than_max():
    assert codex_turn_budget("low", 40) < codex_turn_budget("max", 40)
    assert codex_turn_budget("low", 40) == 20
    assert codex_turn_budget("max", 40) == 40


def test_19_none_or_invalid_effort_keeps_cap_unchanged():
    assert codex_turn_budget(None, 40) == 40
    assert codex_turn_budget("turbo", 40) == 40


def test_20_never_zero_with_positive_cap():
    assert codex_turn_budget("medium", 1) >= 1


# ---------------------------------------------------------------------------
# 21 — flag OFF: passthrough sin tocar nada
# ---------------------------------------------------------------------------

def test_21_flag_off_returns_unchanged_and_not_degraded(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_RUNTIME_CAPABILITIES_ENABLED", False)
    result = clamp_selection("claude_code_cli", "claude-opus-4-8", "turbo")
    assert result["model"] == "claude-opus-4-8"
    assert result["effort"] == "turbo"
    assert result["degraded"] is False


# ---------------------------------------------------------------------------
# 22-23 — [FIX C3] normalización no vacua del catálogo incompleto de Codex
# ---------------------------------------------------------------------------

def test_22_efforts_non_vacuous_per_runtime():
    for runtime in RUNTIMES:
        caps = capabilities_for(runtime)
        if caps["effort_mode"] != "no_aplica":
            assert caps["efforts"], f"{runtime}: efforts vacío (bug C3)"
            assert {e["id"] for e in caps["efforts"]} == set(EFFORTS)
            assert caps["default_effort"] in EFFORTS
        else:
            assert caps["efforts"] == []


def test_23_codex_models_never_expose_empty_id():
    caps = capabilities_for("codex_cli")
    assert all((m.get("id") or "").strip() for m in caps["models"])
    assert caps["default_model"] != ""


# ---------------------------------------------------------------------------
# 24 — [FIX C7] equivalencia EXACTA con la fórmula de hoy (codex_cli_runner.py:591-592)
# ---------------------------------------------------------------------------

def test_24_matches_todays_formula_for_every_cap_and_effort():
    for cap in (0, 1, 5, 40, 41):
        for e in EFFORTS:
            expected = max(1, cap // 2) if (cap > 0 and e == "low") else cap
            assert codex_turn_budget(e, cap) == expected, (e, cap)


# ---------------------------------------------------------------------------
# 25 — [FIX C8] effort_effective_now e effort_note honestos
# ---------------------------------------------------------------------------

def test_25_effort_effective_now_reflects_the_real_cap(monkeypatch):
    monkeypatch.setattr(config.config, "STACKY_RUNAWAY_MAX_TURNS", 0)
    caps_sin_cap = capabilities_for("codex_cli")

    monkeypatch.setattr(config.config, "STACKY_RUNAWAY_MAX_TURNS", 40)
    caps_con_cap = capabilities_for("codex_cli")

    assert caps_sin_cap["effort_effective_now"] is False
    assert caps_con_cap["effort_effective_now"] is True
    assert caps_sin_cap["effort_note"] != caps_con_cap["effort_note"]
    assert "registrada" in caps_sin_cap["effort_note"]


# ---------------------------------------------------------------------------
# 26 — [FIX C4] el catálogo por HTTP declara la capacidad
# ---------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    from app import create_app
    from services import run_slots
    from services.manifest_watcher import stop_manifest_watcher
    from services.ticket_status import stop_stale_recovery

    run_slots._reset_for_tests()
    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c
    stop_stale_recovery()
    stop_manifest_watcher()
    run_slots._reset_for_tests()


def test_26_http_endpoint_enriches_the_catalog_with_capabilities(client):
    resp = client.get("/api/agents/model-catalog")
    assert resp.status_code == 200
    data = resp.get_json()
    runtimes = data["runtimes"]

    for rt in ("claude_code_cli", "codex_cli", "github_copilot"):
        assert "effort_mode" in runtimes[rt], f"{rt}: sin effort_mode en la respuesta HTTP"

    assert len(runtimes["codex_cli"]["efforts"]) == 5
    assert runtimes["github_copilot"]["efforts"] == []
    # El bridge de copilot puede fallar en test (sin red real): lo que importa
    # es que la clave "models" siga presente (el enriquecido no la borra).
    assert "models" in runtimes["github_copilot"]
