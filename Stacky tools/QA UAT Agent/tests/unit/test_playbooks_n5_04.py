"""Sprint N5-04 — Playbook schema + router + arrival_assertions tests.

Three mandatory tests from roadmap §5.4.4:

  * test_playbook_schema_valid          — every *.json playbook validates
                                          against Playbook.schema.json
  * test_playbook_router_finds_detalle  — router resolves
                                          FrmDetalleClie.aspx + "abrir cliente"
                                          to open_detalle_cliente_from_busqueda
  * test_playbook_arrival_assertions_complete
                                        — every playbook with a schema_version
                                          declares no_aspnet_error AND
                                          url_contains

The router test is exercised in-place (not in a tmp dir) because rebuilding
the index is a deterministic operation already covered by router unit
tests; we want this test to verify the live cache/playbooks/ shape.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

ROOT = Path(__file__).parent.parent.parent
PLAYBOOKS_DIR = ROOT / "cache" / "playbooks"
SCHEMAS_DIR = ROOT / "schemas"
NAV_PLAN_SCHEMA = SCHEMAS_DIR / "NavigationPlan.schema.json"
PLAYBOOK_SCHEMA = SCHEMAS_DIR / "Playbook.schema.json"

# Playbooks that follow the new Sprint N5-04 schema. Legacy playbooks
# (without schema_version=="1.0") use a different, pre-existing shape and
# are not the target of this sprint.
N504_PLAYBOOK_FILES = [
    "open_detalle_cliente_from_busqueda.json",
    "open_busqueda_directa.json",
    "open_agenda_personal.json",
]


def _load_pb(name: str) -> dict:
    return json.loads((PLAYBOOKS_DIR / name).read_text(encoding="utf-8-sig"))


# ── 1. Schema validation ─────────────────────────────────────────────────────

def _has_jsonschema() -> bool:
    try:
        import jsonschema  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _has_jsonschema(), reason="jsonschema not installed")
@pytest.mark.parametrize("playbook_file", N504_PLAYBOOK_FILES)
def test_playbook_schema_valid(playbook_file):
    """Roadmap §5.4.4 — every Sprint N5-04 playbook validates against
    Playbook.schema.json (which cross-refs NavigationPlan/1.0)."""
    from jsonschema import Draft202012Validator, RefResolver
    nav_schema = json.loads(NAV_PLAN_SCHEMA.read_text(encoding="utf-8"))
    pb_schema = json.loads(PLAYBOOK_SCHEMA.read_text(encoding="utf-8"))
    store = {
        nav_schema["$id"]: nav_schema,
        pb_schema["$id"]: pb_schema,
    }
    resolver = RefResolver.from_schema(pb_schema, store=store)
    validator = Draft202012Validator(pb_schema, resolver=resolver)
    pb = _load_pb(playbook_file)
    errors = sorted(validator.iter_errors(pb), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        pytest.fail(
            f"{playbook_file} fails schema: {first.message} at "
            f"/{'/'.join(str(p) for p in first.path)}"
        )


def test_playbook_schema_basic_required_fields():
    """Sanity check without jsonschema — required fields are present."""
    required = {
        "playbook_id", "schema_version", "target_screen", "goal_slug",
        "navigation_steps", "action_steps", "arrival_assertions",
    }
    for name in N504_PLAYBOOK_FILES:
        pb = _load_pb(name)
        missing = required - set(pb.keys())
        assert not missing, f"{name} missing fields: {missing}"
        assert pb["schema_version"] == "1.0", name


# ── 2. Router resolves FrmDetalleClie + "abrir cliente" ─────────────────────

def test_playbook_router_finds_detalle():
    """Roadmap §5.4.3 — `python playbook_router.py --rebuild-index` followed
    by a query for `FrmDetalleClie.aspx + 'abrir cliente'` returns the
    Sprint N5-04 playbook `open_detalle_cliente_from_busqueda` with
    score >= 4."""
    import playbook_router as router

    result = router.resolve(
        screen="FrmDetalleClie.aspx",
        scenario_text="quiero abrir cliente y ver su detalle",
    )
    assert result["ok"] is True, result
    assert result["score"] >= 4, result
    # The new playbook must win (score-wise) over the legacy one.
    assert result["playbook_id"] in {
        "abrir_detalle_cliente",                # rebuilt from new playbook
        "open_detalle_cliente_from_busqueda",   # if router index is by file stem
    }, result


def test_playbook_router_finds_busqueda_smoke():
    """Direct-entry smoke playbook also wins for its own screen + keyword."""
    import playbook_router as router
    result = router.resolve(
        screen="FrmBusqueda.aspx",
        scenario_text="smoke busqueda — abrir pantalla de busqueda",
    )
    assert result["ok"] is True, result
    assert result["score"] >= 4, result


# ── 3. arrival_assertions completeness ──────────────────────────────────────

def test_playbook_arrival_assertions_complete():
    """Roadmap §5.4.4 — every N5-04 playbook declares at minimum
    `no_aspnet_error` and `url_contains` arrival_assertions (AP-07)."""
    required_types = {"no_aspnet_error", "url_contains"}
    for name in N504_PLAYBOOK_FILES:
        pb = _load_pb(name)
        types = {a.get("type") for a in pb.get("arrival_assertions", [])}
        missing = required_types - types
        assert not missing, (
            f"{name} arrival_assertions missing required types: {missing}. "
            f"Got: {sorted(types)}"
        )


def test_playbook_arrival_assertions_have_severity_and_category():
    """Each arrival assertion declares severity + category_on_fail so the
    runtime can classify failures correctly (AP-05)."""
    for name in N504_PLAYBOOK_FILES:
        pb = _load_pb(name)
        for i, a in enumerate(pb.get("arrival_assertions", [])):
            assert a.get("severity") in ("hard", "soft"), f"{name}#{i}"
            assert a.get("category_on_fail") in ("NAV", "ENV", "DATA", "APP"), f"{name}#{i}"


# ── Bonus: navigation_step typed-ness (cross-refs NavigationPlan/1.0) ───────

def test_playbook_navigation_steps_use_typed_methods():
    """Every navigation_step uses a method from the NavigationPlan/1.0 enum
    so executeNavigationPlan() can dispatch deterministically."""
    nav_schema = json.loads(NAV_PLAN_SCHEMA.read_text(encoding="utf-8"))
    allowed_methods = set(
        nav_schema["$defs"]["NavigationStep"]["properties"]["method"]["enum"]
    )
    for name in N504_PLAYBOOK_FILES:
        pb = _load_pb(name)
        for step in pb.get("navigation_steps", []):
            assert step.get("method") in allowed_methods, (
                f"{name} step_index={step.get('step_index')} method="
                f"{step.get('method')!r} not in {sorted(allowed_methods)}"
            )


def test_playbook_index_is_in_sync_with_files():
    """index.json must reference every Sprint N5-04 playbook (either by its
    goal_slug or by an obvious mapping). Catches a stale rebuild."""
    index = json.loads((PLAYBOOKS_DIR / "index.json").read_text(encoding="utf-8"))
    indexed_files = {meta.get("file", "") for meta in index["playbooks"].values()}
    for name in N504_PLAYBOOK_FILES:
        assert any(name in f for f in indexed_files), (
            f"index.json does not reference {name}. "
            "Run: python playbook_router.py --rebuild-index"
        )
