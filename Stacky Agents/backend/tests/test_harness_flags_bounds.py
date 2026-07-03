"""Plan 83 — Bounds declarativos min_value/max_value para flags numéricas del arnés.

F0: FlagSpec.min_value/max_value + value_in_bounds + validate_bounds_registry + exposición
    en read_current() (in_bounds fail-open, unset para env_only sin configurar).
F1: mapa curado y CONGELADO de bounds + perfiles dentro de bounds + centinela de
    harness_defaults.env.
F2: apply_updates rechaza valores fuera de rango (ValueError 400 en el PUT).
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


# ---------------------------------------------------------------------------
# F0 — FlagSpec.min_value/max_value + value_in_bounds + validate_bounds_registry
# ---------------------------------------------------------------------------

def test_flagspec_bounds_default_none():
    from services.harness_flags import FlagSpec

    spec = FlagSpec(key="X", type="int", label="l", description="d", group="global")
    assert spec.min_value is None and spec.max_value is None


def test_value_in_bounds_no_bounds_true():
    from services.harness_flags import FlagSpec, value_in_bounds

    spec = FlagSpec(key="X", type="int", label="l", description="d", group="global")
    assert value_in_bounds(spec, -999) is True
    assert value_in_bounds(spec, 0) is True
    assert value_in_bounds(spec, 999) is True


def test_value_in_bounds_min_only():
    from services.harness_flags import FlagSpec, value_in_bounds

    spec = FlagSpec(key="X", type="int", label="l", description="d", group="global", min_value=1)
    assert value_in_bounds(spec, 0) is False
    assert value_in_bounds(spec, 1) is True
    assert value_in_bounds(spec, 50) is True


def test_value_in_bounds_min_and_max():
    from services.harness_flags import FlagSpec, value_in_bounds

    spec = FlagSpec(
        key="X", type="float", label="l", description="d", group="global",
        min_value=0, max_value=1,
    )
    assert value_in_bounds(spec, -0.1) is False
    assert value_in_bounds(spec, 0) is True
    assert value_in_bounds(spec, 1) is True
    assert value_in_bounds(spec, 1.5) is False


def test_value_in_bounds_non_numeric_fail_open():
    from services.harness_flags import FlagSpec, value_in_bounds

    spec = FlagSpec(key="X", type="int", label="l", description="d", group="global", min_value=1)
    assert value_in_bounds(spec, "abc") is True
    assert value_in_bounds(spec, None) is True


def test_value_in_bounds_non_numeric_type_true():
    from services.harness_flags import FlagSpec, value_in_bounds

    spec = FlagSpec(
        key="X", type="csv", label="l", description="d", group="global",
        min_value=1, max_value=10,
    )
    assert value_in_bounds(spec, "a,b,c") is True


def test_validate_bounds_registry_ok():
    from services.harness_flags import validate_bounds_registry

    assert validate_bounds_registry() == []


def test_read_current_exposes_bounds_fields():
    from services.harness_flags import read_current

    result = read_current()
    assert len(result) > 0
    for row in result:
        assert "min_value" in row
        assert "max_value" in row
        assert "in_bounds" in row


def test_read_current_unset_env_only_in_bounds_true(monkeypatch):
    from services import harness_flags
    from services.harness_flags import FlagSpec, read_current

    test_spec = FlagSpec(
        key="STACKY_TEST_BOUNDS_ENV_ONLY", type="int", label="t", description="t",
        group="global", env_only=True, min_value=1,
    )
    monkeypatch.setattr(
        harness_flags, "FLAG_REGISTRY", harness_flags.FLAG_REGISTRY + (test_spec,)
    )
    monkeypatch.setattr(
        harness_flags, "_REGISTRY_INDEX",
        {**harness_flags._REGISTRY_INDEX, test_spec.key: test_spec},
    )
    monkeypatch.delenv(test_spec.key, raising=False)

    result = {r["key"]: r for r in read_current()}
    assert result[test_spec.key]["in_bounds"] is True

    monkeypatch.setenv(test_spec.key, "0")
    result = {r["key"]: r for r in read_current()}
    assert result[test_spec.key]["in_bounds"] is False


# ---------------------------------------------------------------------------
# F1 — Mapa curado y CONGELADO de bounds + perfiles + harness_defaults.env
# ---------------------------------------------------------------------------

# Filas que sobrevivieron el procedimiento F1 (verificadas contra el consumidor real,
# ver comentarios en services/harness_flags.py junto a cada min_value/max_value).
#
# DESVÍOS respecto a la tabla propuesta en el plan (el código manda, no la tabla):
#   - STACKY_MAX_CONCURRENT_RUNS: min=0 no 1 — run_slots.py confirma "0 = ilimitado
#     (retro-compat)", NO "bloquea todo run".
#   - STACKY_CLI_FEWSHOT_K: min=0 no 1 — few_shot.pick_examples con k=0 da lista
#     vacía (benigno); solo k negativo es un bug real (slicing negativo).
#   - STACKY_UNBLOCKER_COMPLETED_CAP: min=0 no 1 — api/tickets.py ya clampa a 0 y
#     con cap=0 el recorte se salta entero (0 = sin cota), no "vacía el panel".
#   - STACKY_ADO_EDIT_SWEEP_HOURS: min=1 no 0 — a diferencia de los demás *_HOURS,
#     app.py NO gatea `if hours > 0`; 0 produce un busy-loop real (`time.sleep(0)`).
#
# DESCARTADAS (sin consumidor real en código, procedimiento F1 paso 4 — NO llevan
# bounds; ver comentario de descarte junto al FlagSpec en harness_flags.py):
#   - STACKY_BUDGET_PER_TICKET_USD — declarada pero nunca leída.
#   - STACKY_CRITERIA_REPAIR_MAX_RETRIES — el pase corre una única vez hardcodeado;
#     el budget real que se usa es CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES.
#   - STACKY_TRANSIENT_RUN_RETRY_MAX — la propia label dice "G2.2 - DIFERIDO".
#   - STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES — solo mencionada en un docstring.
_FROZEN_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "CLAUDE_CODE_CLI_AUTOCORRECT_MAX_RETRIES": (0, None),
    "CODEX_CLI_AUTOCORRECT_MAX_RETRIES": (0, None),
    "STACKY_CONTEXT_BUDGET_TOKENS": (0, None),
    "STACKY_MEMORY_REVIEW_SWEEP_HOURS": (0, None),
    "STACKY_MEMORY_DIRECTIVE_MAX_CHARS": (0, None),
    "STACKY_RUNAWAY_MAX_TURNS": (0, None),
    "STACKY_RUNAWAY_MAX_COST_USD": (0, None),
    "STACKY_MAX_CONCURRENT_RUNS": (0, None),
    "STACKY_SELF_REVIEW_MIN_SCORE": (0, 1),
    "STACKY_DIGEST_INTERVAL_HOURS": (0, None),
    "STACKY_EVALS_INTERVAL_HOURS": (0, None),
    "STACKY_RUN_CACHE_DAYS": (0, None),
    "STACKY_ADO_READ_CACHE_TTL_SEC": (0, None),
    "STACKY_ORPHAN_REAPER_INTERVAL_SEC": (0, None),
    "STACKY_STALL_WATCHDOG_SECONDS": (0, None),
    "STACKY_CLI_FEWSHOT_K": (0, None),
    "STACKY_EXEC_VERIFICATION_TIMEOUT_S": (1, None),
    "STACKY_EXEC_VERIFICATION_BUDGET_S": (1, None),
    "STACKY_EXEC_REPAIR_MAX_RETRIES": (0, None),
    "STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS": (1, None),
    "STACKY_UNBLOCKER_COMPLETED_CAP": (0, None),
    "STACKY_RAG_CATALOG_TOP_K": (1, None),
    "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF": (0, 1),
    "STACKY_QUALITY_CONVERGENCE_MAX_ITERATIONS": (1, None),
    "STACKY_ADO_EDIT_SWEEP_HOURS": (1, None),
}


def test_bounds_map_is_frozen():
    from services.harness_flags import FLAG_REGISTRY

    actual = {
        s.key: (s.min_value, s.max_value)
        for s in FLAG_REGISTRY
        if s.min_value is not None or s.max_value is not None
    }
    assert actual == _FROZEN_BOUNDS


def test_validate_bounds_registry_ok_after_population():
    from services.harness_flags import validate_bounds_registry

    assert validate_bounds_registry() == []


def test_profiles_values_within_bounds():
    from services.harness_flags import _REGISTRY_INDEX, value_in_bounds
    from services.harness_profiles import PROFILES

    for profile_name, preset in PROFILES.items():
        for key, raw_value in preset.items():
            spec = _REGISTRY_INDEX.get(key)
            if spec is None:
                continue
            assert value_in_bounds(spec, raw_value) is True, (
                f"perfil {profile_name!r}: {key}={raw_value!r} fuera de bounds"
            )


def test_harness_defaults_env_within_bounds():
    from services.harness_flags import _REGISTRY_INDEX, _cast, value_in_bounds

    env_path = Path(__file__).parent.parent / "harness_defaults.env"
    if not env_path.exists():
        pytest.skip(f"harness_defaults.env no existe en este entorno: {env_path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw_value = line.partition("=")
        key = key.strip()
        raw_value = raw_value.strip()
        spec = _REGISTRY_INDEX.get(key)
        if spec is None or spec.type not in ("int", "float"):
            continue
        try:
            typed_value = _cast(spec, raw_value)
        except ValueError:
            continue
        assert value_in_bounds(spec, typed_value) is True, (
            f"harness_defaults.env: {key}={raw_value!r} fuera de bounds"
        )


# ---------------------------------------------------------------------------
# F2 — apply_updates rechaza valores fuera de rango
# ---------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """Flask test client con _ENV_PATH apuntando a un tmp .env (mismo patrón que
    tests/test_harness_flags.py; no hay conftest.py compartido en este repo)."""
    monkeypatch.setenv("STACKY_REAPER_ENABLED", "false")
    monkeypatch.setenv("STACKY_MANIFEST_WATCHER_ENABLED", "false")

    tmp_env = tmp_path / ".env"
    tmp_env.write_text("", encoding="utf-8")
    monkeypatch.setattr("api.global_config._ENV_PATH", tmp_env)
    monkeypatch.setattr("api.harness_flags._ENV_PATH", tmp_env, raising=False)

    from app import create_app
    from services.ticket_status import stop_stale_recovery
    from services.manifest_watcher import stop_manifest_watcher

    app = create_app()
    app.config.update(TESTING=True)
    stop_stale_recovery()
    stop_manifest_watcher()
    with app.test_client() as c:
        yield c, tmp_env
    stop_stale_recovery()
    stop_manifest_watcher()


def _first_key_with_min() -> str:
    for key, (lo, _hi) in _FROZEN_BOUNDS.items():
        if lo is not None:
            return key
    raise AssertionError("ninguna key con min_value en el mapa congelado")


def _first_key_with_max() -> str:
    for key, (_lo, hi) in _FROZEN_BOUNDS.items():
        if hi is not None:
            return key
    raise AssertionError("ninguna key con max_value en el mapa congelado")


def test_apply_updates_rejects_below_min():
    from services.harness_flags import apply_updates, _REGISTRY_INDEX

    key = _first_key_with_min()
    lo = _REGISTRY_INDEX[key].min_value
    with pytest.raises(ValueError) as exc_info:
        apply_updates({key: lo - 1})
    msg = str(exc_info.value)
    assert "fuera de rango" in msg


def test_apply_updates_accepts_boundary():
    from services.harness_flags import apply_updates, _REGISTRY_INDEX

    key = _first_key_with_min()
    lo = _REGISTRY_INDEX[key].min_value
    result = apply_updates({key: lo})
    assert result[key] == lo


def test_apply_updates_rejects_above_max():
    from services.harness_flags import apply_updates, _REGISTRY_INDEX

    key = "INTENT_PREFLIGHT_AUTO_APPROVE_MIN_CONF"
    if key not in _FROZEN_BOUNDS or _FROZEN_BOUNDS[key][1] is None:
        key = "STACKY_SELF_REVIEW_MIN_SCORE"
    if key not in _FROZEN_BOUNDS or _FROZEN_BOUNDS[key][1] is None:
        key = _first_key_with_max()
    hi = _REGISTRY_INDEX[key].max_value
    with pytest.raises(ValueError) as exc_info:
        apply_updates({key: hi + 0.5})
    assert "fuera de rango" in str(exc_info.value)


def test_apply_updates_no_bounds_unchanged(monkeypatch):
    from services import harness_flags
    from services.harness_flags import FlagSpec, apply_updates

    spec = FlagSpec(key="STACKY_TEST_NO_BOUNDS", type="int", label="t", description="t", group="global")
    monkeypatch.setitem(harness_flags._REGISTRY_INDEX, "STACKY_TEST_NO_BOUNDS", spec)

    result = apply_updates({"STACKY_TEST_NO_BOUNDS": -5})
    assert result == {"STACKY_TEST_NO_BOUNDS": -5}


def test_put_endpoint_returns_400_out_of_bounds(client):
    from services.harness_flags import _REGISTRY_INDEX

    c, tmp_env = client
    key = _first_key_with_min()
    lo = _REGISTRY_INDEX[key].min_value

    resp = c.put(
        "/api/harness-flags",
        json={"updates": {key: lo - 1}},
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "fuera de rango" in body["error"]
    assert key not in tmp_env.read_text(encoding="utf-8")
