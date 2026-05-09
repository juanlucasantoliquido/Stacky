"""
selector_contract_validator.py — Pre-generator alias/selector contract enforcement.

Sprint 2 — Screen Detection + UI Map Contract.

ROLE IN PIPELINE
----------------
Called AFTER uat_scenario_compiler and BEFORE playwright_test_generator.
If validation fails, the pipeline must NOT generate any .spec.ts file.

The validator answers one question: do the aliases requested by the compiler
actually exist in the UI map for the target screen?

If any alias is missing  → BLOCKED GEN SELECTOR_ALIAS_NOT_IN_UI_MAP
If any alias targets a decorative element with a click/fill action
                         → BLOCKED GEN DECORATIVE_ELEMENT_ACTION
If the UI map file is absent
                         → BLOCKED GEN UI_MAP_MISSING

PUBLIC API
----------
    validate_selector_contract(
        screen, aliases_requested, ui_map_path,
        scenario_id=None, evidence_dir=None, run_id=None
    ) -> SelectorContractResult

    SelectorContractResult.decision: "ALLOW" | "BLOCKED"

ARTIFACT
--------
When evidence_dir and run_id are provided, the result is persisted as:
    evidence_dir / run_id / selector_contract.json

JSONL EVENT
-----------
The caller (qa_uat_pipeline._run_pipeline_stages) should emit:
    {
      "event": "selector_contract_validation",
      "screen": "...",
      "scenario_id": "...",
      "aliases_requested": [...],
      "aliases_available": [...],
      "missing_aliases": [...],
      "decision": "ALLOW"|"BLOCKED",
      "category": "GEN"|null,
      "reason": "SELECTOR_ALIAS_NOT_IN_UI_MAP"|"DECORATIVE_ELEMENT_ACTION"|"UI_MAP_MISSING"|null,
      "artifact_path": "..."
    }
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

_logger = logging.getLogger("stacky.qa_uat.selector_contract_validator")

# Actions that are invalid on decorative elements
_DECORATIVE_BLOCKED_ACTIONS = frozenset({"click", "fill", "type", "check", "uncheck", "select"})


# ── Result contract ────────────────────────────────────────────────────────────

@dataclass
class SelectorContractResult:
    """Structured result of selector contract validation.

    decision == "ALLOW" means the generator may proceed.
    decision == "BLOCKED" means no .spec.ts must be written.
    """

    valid: bool
    screen: str
    aliases_requested: list = field(default_factory=list)
    aliases_available: list = field(default_factory=list)
    missing_aliases: list = field(default_factory=list)
    decorative_action_attempts: list = field(default_factory=list)
    decision: str = "ALLOW"          # "ALLOW" | "BLOCKED"
    category: Optional[str] = None   # "GEN" when blocked
    reason: Optional[str] = None     # machine-readable block reason
    artifact_path: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "schema_version": "selector_contract/1.0",
            "valid": self.valid,
            "screen": self.screen,
            "aliases_requested": self.aliases_requested,
            "aliases_available": self.aliases_available,
            "missing_aliases": self.missing_aliases,
            "decorative_action_attempts": self.decorative_action_attempts,
            "decision": self.decision,
            "category": self.category,
            "reason": self.reason,
        }


# ── Core validator ─────────────────────────────────────────────────────────────

def validate_selector_contract(
    screen: str,
    aliases_requested: list,
    ui_map_path: str,
    scenario_id: Optional[str] = None,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
    action_map: Optional[dict] = None,
) -> SelectorContractResult:
    """Validate that all requested aliases exist in the UI map.

    Parameters
    ----------
    screen : str
        Target screen filename (e.g. 'FrmDetalleClie.aspx').
    aliases_requested : list[str]
        Aliases the compiler/generator intends to use.
    ui_map_path : str
        Absolute path to the UI map JSON file for this screen.
    scenario_id : str | None
        Scenario ID for logging and artifact naming (e.g. 'RF-008-CA-01').
    evidence_dir : Path | None
        Base evidence directory. If provided along with run_id, the artifact
        selector_contract.json is written there.
    run_id : str | None
        Run identifier for artifact path (e.g. ticket_id or freeform run_id).
    action_map : dict | None
        Optional mapping {alias: action} so the validator can check decorative
        element constraints. E.g. {"btnGuardar": "click", "msg_titulo": "visible"}.
        If None, decorative action check is skipped.

    Returns
    -------
    SelectorContractResult
        Contains decision, reason, and full evidence lists.
    """
    # ── Guard: UI map file must exist ─────────────────────────────────────────
    ui_map_file = Path(ui_map_path)
    if not ui_map_file.is_file():
        _logger.warning(
            "selector_contract: UI map missing for %s at %s", screen, ui_map_path
        )
        result = SelectorContractResult(
            valid=False,
            screen=screen,
            aliases_requested=list(aliases_requested),
            aliases_available=[],
            missing_aliases=list(aliases_requested),
            decision="BLOCKED",
            category="GEN",
            reason="UI_MAP_MISSING",
        )
        _persist_artifact(result, evidence_dir, run_id, scenario_id)
        return result

    # ── Load UI map ────────────────────────────────────────────────────────────
    try:
        ui_data = json.loads(ui_map_file.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        _logger.error("selector_contract: failed to parse UI map at %s: %s", ui_map_path, exc)
        result = SelectorContractResult(
            valid=False,
            screen=screen,
            aliases_requested=list(aliases_requested),
            aliases_available=[],
            missing_aliases=list(aliases_requested),
            decision="BLOCKED",
            category="GEN",
            reason="UI_MAP_MISSING",
        )
        _persist_artifact(result, evidence_dir, run_id, scenario_id)
        return result

    # Build index of available aliases from elements + grids
    aliases_available: list[str] = []
    alias_meta: dict[str, dict] = {}   # alias → element metadata

    for el in ui_data.get("elements", []):
        alias = el.get("alias_semantic")
        if alias:
            aliases_available.append(alias)
            alias_meta[alias] = {
                "is_decorative": el.get("is_decorative", False),
                "is_interactive": el.get("is_interactive", True),
                "role": el.get("role", ""),
            }

    for grid in ui_data.get("grids", []):
        alias = grid.get("alias_semantic")
        if alias:
            aliases_available.append(alias)
            alias_meta[alias] = {
                "is_decorative": False,
                "is_interactive": True,
                "role": "grid",
            }

    available_set = set(aliases_available)

    # ── Rule 1: missing aliases ────────────────────────────────────────────────
    missing = [a for a in aliases_requested if a not in available_set]

    # ── Rule 2: decorative element action ─────────────────────────────────────
    decorative_violations: list[str] = []
    if action_map:
        for alias, action in action_map.items():
            if alias in alias_meta:
                meta = alias_meta[alias]
                if meta.get("is_decorative") and action.lower() in _DECORATIVE_BLOCKED_ACTIONS:
                    decorative_violations.append(f"{alias}:{action}")

    # ── Decision ───────────────────────────────────────────────────────────────
    if missing:
        _logger.warning(
            "selector_contract: BLOCKED — screen=%s missing_aliases=%s",
            screen, missing,
        )
        result = SelectorContractResult(
            valid=False,
            screen=screen,
            aliases_requested=list(aliases_requested),
            aliases_available=aliases_available,
            missing_aliases=missing,
            decorative_action_attempts=decorative_violations,
            decision="BLOCKED",
            category="GEN",
            reason="SELECTOR_ALIAS_NOT_IN_UI_MAP",
        )
    elif decorative_violations:
        _logger.warning(
            "selector_contract: BLOCKED — decorative action on %s", decorative_violations
        )
        result = SelectorContractResult(
            valid=False,
            screen=screen,
            aliases_requested=list(aliases_requested),
            aliases_available=aliases_available,
            missing_aliases=[],
            decorative_action_attempts=decorative_violations,
            decision="BLOCKED",
            category="GEN",
            reason="DECORATIVE_ELEMENT_ACTION",
        )
    else:
        _logger.debug(
            "selector_contract: ALLOW — screen=%s all %d aliases present",
            screen, len(aliases_requested),
        )
        result = SelectorContractResult(
            valid=True,
            screen=screen,
            aliases_requested=list(aliases_requested),
            aliases_available=aliases_available,
            missing_aliases=[],
            decorative_action_attempts=[],
            decision="ALLOW",
            category=None,
            reason=None,
        )

    _persist_artifact(result, evidence_dir, run_id, scenario_id)
    return result


# ── Artifact persistence ───────────────────────────────────────────────────────

def _persist_artifact(
    result: SelectorContractResult,
    evidence_dir: Optional[Path],
    run_id: Optional[str],
    scenario_id: Optional[str],
) -> None:
    """Write selector_contract.json to evidence dir. No-op if dir/run_id absent."""
    if evidence_dir is None or run_id is None:
        return
    try:
        artifact_dir = evidence_dir / str(run_id)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        # Include scenario_id in filename when provided to avoid collisions
        filename = (
            f"selector_contract_{scenario_id}.json"
            if scenario_id
            else "selector_contract.json"
        )
        artifact_file = artifact_dir / filename
        payload = {
            **result.to_dict(),
            "run_id": run_id,
            "scenario_id": scenario_id,
        }
        artifact_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.artifact_path = str(artifact_file)
        _logger.debug("selector_contract artifact written: %s", artifact_file)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("selector_contract: could not write artifact: %s", exc)


# ── Batch validation helper ────────────────────────────────────────────────────

def validate_all_scenarios(
    scenarios: list,
    ui_maps_dir: Path,
    evidence_dir: Optional[Path] = None,
    run_id: Optional[str] = None,
) -> dict:
    """Validate selector contracts for all compiled scenarios in one pass.

    Parameters
    ----------
    scenarios : list[dict]
        List of compiled scenario dicts, each with at minimum:
        - id: str
        - screen: str (or inferred from ui_maps_dir contents)
        - steps: list[dict] with alias_semantic and action fields
    ui_maps_dir : Path
        Directory containing <screen>.json UI map files.
    evidence_dir : Path | None
        If provided, artifacts are written per scenario.
    run_id : str | None
        Run identifier for artifact paths.

    Returns
    -------
    dict with:
        ok: bool — True only if ALL scenarios ALLOW
        results: list[SelectorContractResult]
        blocked_count: int
        allow_count: int
        first_blocked_reason: str | None
    """
    results = []
    blocked = []
    for scenario in scenarios:
        screen = scenario.get("screen", "")
        scenario_id = scenario.get("id", "unknown")
        # Collect aliases from scenario steps
        aliases: list[str] = []
        action_map: dict[str, str] = {}
        for step in scenario.get("steps", []):
            alias = step.get("alias_semantic") or step.get("alias")
            action = step.get("action", "")
            if alias:
                aliases.append(alias)
                if alias not in action_map:
                    action_map[alias] = action

        ui_map_path = str(ui_maps_dir / f"{screen}.json") if screen else ""
        r = validate_selector_contract(
            screen=screen,
            aliases_requested=aliases,
            ui_map_path=ui_map_path,
            scenario_id=scenario_id,
            evidence_dir=evidence_dir,
            run_id=run_id,
            action_map=action_map if action_map else None,
        )
        results.append(r)
        if r.decision == "BLOCKED":
            blocked.append(r)

    return {
        "ok": len(blocked) == 0,
        "results": results,
        "blocked_count": len(blocked),
        "allow_count": len(results) - len(blocked),
        "first_blocked_reason": blocked[0].reason if blocked else None,
        "first_blocked_screen": blocked[0].screen if blocked else None,
    }


__all__ = [
    "validate_selector_contract",
    "validate_all_scenarios",
    "SelectorContractResult",
]
