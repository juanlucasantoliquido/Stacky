"""Plan 72 F0 — Tests de funciones puras ci_trigger_rules.

10 casos según el plan:
  1. validate_trigger_credentials("gitlab", {"api"}) → (True, "ok")
  2. validate_trigger_credentials("gitlab", {"read_api"}) → (False, msg con "api")
  3. validate_trigger_credentials("azure_devops", {"vso.build_execute"}) → (True, "ok")
  4. [C3'] scopes None → (True, ...) ; set() → (True, ...)
  5. normalize_ref("develop") → ("branch", "develop")
  6. normalize_ref("abc1234") → ("sha", "abc1234") ; "zzzzzzz" → ("branch", "zzzzzzz")
  7. normalize_ref("") → ValueError ; normalize_ref("a b") → ValueError
  8. should_trigger("develop", "abc123", [], 60) → (True, None)
  9. should_trigger con trigger reciente (ref, sha match en ventana) → (False, "99")
  10. should_trigger con trigger fuera de ventana (>60s) → (True, None)
"""
from __future__ import annotations

import time

import pytest

from services.ci_trigger_rules import (
    normalize_ref,
    should_trigger,
    validate_trigger_credentials,
)


# ---------------------------------------------------------------------------
# Caso 1 — gitlab scope "api" completo → ok
# ---------------------------------------------------------------------------
def test_validate_credentials_gitlab_ok():
    ok, msg = validate_trigger_credentials("gitlab", {"api"})
    assert ok is True
    assert msg == "ok"


# ---------------------------------------------------------------------------
# Caso 2 — gitlab scope incompleto → False con "api" en mensaje
# ---------------------------------------------------------------------------
def test_validate_credentials_gitlab_missing_scope():
    ok, msg = validate_trigger_credentials("gitlab", {"read_api"})
    assert ok is False
    assert "api" in msg


# ---------------------------------------------------------------------------
# Caso 3 — azure_devops scope completo → ok
# ---------------------------------------------------------------------------
def test_validate_credentials_ado_ok():
    ok, msg = validate_trigger_credentials("azure_devops", {"vso.build_execute"})
    assert ok is True
    assert msg == "ok"


# ---------------------------------------------------------------------------
# Caso 4 — [C3'] None y set() son no-verificables → no bloquear
# ---------------------------------------------------------------------------
def test_validate_credentials_none_not_blocking():
    ok, msg = validate_trigger_credentials("gitlab", None)
    assert ok is True
    assert "no verificables" in msg or "runtime" in msg


def test_validate_credentials_empty_set_not_blocking():
    ok, msg = validate_trigger_credentials("gitlab", set())
    assert ok is True
    assert "no verificables" in msg or "runtime" in msg


# ---------------------------------------------------------------------------
# Caso 5 — normalize_ref branch
# ---------------------------------------------------------------------------
def test_normalize_ref_branch():
    kind, value = normalize_ref("develop")
    assert kind == "branch"
    assert value == "develop"


# ---------------------------------------------------------------------------
# Caso 6 — normalize_ref sha vs no-hex
# ---------------------------------------------------------------------------
def test_normalize_ref_sha_7hex():
    kind, value = normalize_ref("abc1234")
    assert kind == "sha"
    assert value == "abc1234"


def test_normalize_ref_non_hex_is_branch():
    kind, value = normalize_ref("zzzzzzz")
    assert kind == "branch"
    assert value == "zzzzzzz"


# ---------------------------------------------------------------------------
# Caso 7 — normalize_ref ValueError
# ---------------------------------------------------------------------------
def test_normalize_ref_empty_raises():
    with pytest.raises(ValueError):
        normalize_ref("")


def test_normalize_ref_space_raises():
    with pytest.raises(ValueError):
        normalize_ref("a b")


def test_normalize_ref_dotdot_raises():
    with pytest.raises(ValueError):
        normalize_ref("branch..other")


# ---------------------------------------------------------------------------
# Caso 8 — should_trigger sin historial → (True, None)
# ---------------------------------------------------------------------------
def test_should_trigger_no_history():
    fire, existing = should_trigger("develop", "abc123", [], 60)
    assert fire is True
    assert existing is None


# ---------------------------------------------------------------------------
# Caso 9 — trigger reciente con (ref, sha) en ventana → (False, "99")
# ---------------------------------------------------------------------------
def test_should_trigger_recent_match():
    now = time.time()
    recent = [{"ref": "develop", "sha": "abc123", "pipeline_id": "99", "ts": now}]
    fire, existing = should_trigger("develop", "abc123", recent, 60)
    assert fire is False
    assert existing == "99"


# ---------------------------------------------------------------------------
# Caso 10 — trigger fuera de ventana (>60s) → (True, None)
# ---------------------------------------------------------------------------
def test_should_trigger_outside_window():
    old_ts = time.time() - 120  # 2 minutos atrás
    recent = [{"ref": "develop", "sha": "abc123", "pipeline_id": "99", "ts": old_ts}]
    fire, existing = should_trigger("develop", "abc123", recent, 60)
    assert fire is True
    assert existing is None
