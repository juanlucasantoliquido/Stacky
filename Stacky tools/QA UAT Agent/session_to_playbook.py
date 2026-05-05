"""
session_to_playbook.py — Convert a session_recorder recording into a
replay-ready Playbook JSON that the playwright_test_generator can use
directly without UI-map lookup or LLM inference.

Recording-to-Replay pipeline (Fase 8):
  session_recorder.py → session.json → THIS TOOL → cache/playbooks/{slug}.json
                                                   form_knowledge.json (updated)
                                                   cache/learned_edges.json (updated)

CLI:
    python session_to_playbook.py --session evidence/recordings/20260505_104714/ [--verbose]
    python session_to_playbook.py --session evidence/recordings/latest/ [--dry-run]

Output: JSON to stdout
    {"ok": true, "playbook_path": "...", "goal_slug": "...", "steps": N}
    {"ok": false, "error": "<code>", "message": "..."}

Exit codes:
    0 — playbook created/updated successfully
    1 — hard error (session not found, JSON invalid)
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.session_to_playbook")

_TOOL_VERSION = "1.0.0"
_TOOL_ROOT = Path(__file__).resolve().parent
_CACHE_DIR = _TOOL_ROOT / "cache"
_PLAYBOOKS_DIR = _CACHE_DIR / "playbooks"
_FORM_KNOWLEDGE_PATH = _TOOL_ROOT / "form_knowledge.json"
_LEARNED_EDGES_PATH = _CACHE_DIR / "learned_edges.json"


# ── Public API ────────────────────────────────────────────────────────────────

def run(
    session_dir: Path,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    """Convert a session.json into a cache/playbooks/{slug}.json playbook.

    Also updates form_knowledge.json and cache/learned_edges.json as side effects.

    Returns a result dict with ok/error.
    """
    started = time.time()

    session_file = session_dir / "session.json"
    if not session_file.is_file():
        # Try latest.txt pointer (Windows)
        latest_ptr = _TOOL_ROOT / "evidence" / "recordings" / "latest.txt"
        if latest_ptr.is_file():
            alt_dir = Path(latest_ptr.read_text(encoding="utf-8").strip())
            alt_file = alt_dir / "session.json"
            if alt_file.is_file():
                session_file = alt_file
                session_dir = alt_dir
        if not session_file.is_file():
            return _err("session_not_found", f"No session.json found in {session_dir}")

    try:
        session: dict = json.loads(session_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return _err("invalid_session_json", f"Cannot parse session.json: {exc}")

    goal = session.get("goal", "") or session.get("inferred_goal_action", "") or "recorded_action"
    goal_slug = _slugify(goal)
    if not goal_slug:
        goal_slug = f"recording_{session_dir.name}"

    nav_path: list[str] = session.get("navigation_path") or []
    transitions: list[dict] = session.get("transitions") or []
    discovered_selectors: dict[str, dict] = session.get("discovered_selectors") or {}
    form_fields: dict[str, dict] = session.get("form_fields") or {}
    recorded_at: str = session.get("recorded_at", "")

    if len(nav_path) < 2:
        return _err("empty_navigation", "session.json navigation_path has fewer than 2 screens")

    entry_screen = nav_path[0] if nav_path[0] != "FrmLogin.aspx" else (nav_path[1] if len(nav_path) > 1 else nav_path[0])
    target_screen = nav_path[-1]

    # ── Build navigation_steps ────────────────────────────────────────────────
    # For each transition, find the trigger selector (may need recovery).
    try:
        from navigation_graph_learner import _recover_trigger_from_discovered
    except ImportError:
        _recover_trigger_from_discovered = None  # type: ignore

    navigation_steps: list[dict] = []
    navigation_steps.append({"action": "goto", "screen": entry_screen})

    for tr in transitions:
        src = tr.get("from", "")
        tgt = tr.get("to", "")
        if tgt == "FrmLogin.aspx" or src == "FrmLogin.aspx":
            continue  # login handled by pipeline
        trigger_sel = (tr.get("trigger_selector") or "").strip()
        trigger_label = (tr.get("trigger_label") or "").strip()

        # Recover empty trigger_selector from discovered_selectors
        if not trigger_sel and _recover_trigger_from_discovered is not None:
            trigger_sel, trigger_label_recovered = _recover_trigger_from_discovered(tr, discovered_selectors)
            if trigger_sel and not trigger_label:
                trigger_label = trigger_label_recovered

        if trigger_sel:
            navigation_steps.append({
                "action": "click",
                "selector": trigger_sel,
                "label": trigger_label or tgt,
                "wait_after": "load",
            })
        elif src != entry_screen:
            # No trigger found — emit a goto as fallback (direct URL navigation)
            navigation_steps.append({
                "action": "goto",
                "screen": tgt,
                "_note": "trigger_selector not recovered — using direct URL navigation",
            })

        # After navigating to the target, wait for a known stable element
        stable_sel = _find_stable_element(tgt, discovered_selectors)
        if stable_sel:
            navigation_steps.append({
                "action": "waitFor",
                "selector": stable_sel,
                "timeout_ms": 10000,
            })

    # ── Build parameterizable_fields from form_fields ─────────────────────────
    # form_fields[screen][selector] = {label, last_value, input_type, field_name}
    # We use the target screen's fields. Legacy schema (value→selector) is
    # handled too, for backwards compat with recordings before 1.2.0.
    target_form_fields = form_fields.get(target_screen, {})
    parameterizable_fields: dict[str, dict] = {}
    action_steps_fill: list[dict] = []

    for selector, meta in target_form_fields.items():
        if isinstance(meta, dict):
            # New schema: {label, last_value, input_type, field_name}
            field_name_raw = meta.get("field_name") or meta.get("label") or ""
            param_key = _to_param_key(field_name_raw, selector)
            source = _infer_source(param_key, meta.get("input_type", "text"), meta.get("last_value", ""))
            parameterizable_fields[param_key] = {
                "selector":   selector,
                "label":      meta.get("label", ""),
                "input_type": meta.get("input_type", "text"),
                "required":   _is_required(selector, param_key),
                "source":     source,
                "default":    _infer_default(source, meta.get("last_value", "")),
            }
            action_steps_fill.append({
                "action":   "fill",
                "selector": selector,
                "field":    param_key,
                "source":   source,
            })
        else:
            # Legacy schema: value (str) → selector — skip (unusable)
            logger.debug("session_to_playbook: skipping legacy form_field key=%s", selector)

    # ── Discover action_steps from discovered_selectors on target screen ──────
    # Look for buttons that were visible and likely interacted with.
    target_disc = discovered_selectors.get(target_screen, {})
    action_steps: list[dict] = _build_action_steps(target_disc, action_steps_fill)

    # ── Assemble playbook ────────────────────────────────────────────────────
    playbook = {
        "schema_version": "playbook/1.0",
        "tool_version": _TOOL_VERSION,
        "goal_slug": goal_slug,
        "goal_label": goal,
        "recorded_at": recorded_at,
        "session_source": str(session_file),
        "entry_screen": entry_screen,
        "target_screen": target_screen,
        "navigation_path": nav_path,
        "navigation_steps": navigation_steps,
        "action_steps": action_steps,
        "parameterizable_fields": parameterizable_fields,
    }

    # ── Write playbook ────────────────────────────────────────────────────────
    if not dry_run:
        _PLAYBOOKS_DIR.mkdir(parents=True, exist_ok=True)
        playbook_path = _PLAYBOOKS_DIR / f"{goal_slug}.json"
        playbook_path.write_text(json.dumps(playbook, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("session_to_playbook: wrote playbook → %s", playbook_path)

        # Update form_knowledge.json with target screen entry
        _update_form_knowledge(target_screen, target_disc, parameterizable_fields, action_steps)
    else:
        playbook_path = _PLAYBOOKS_DIR / f"{goal_slug}.json"

    elapsed = int((time.time() - started) * 1000)
    return {
        "ok": True,
        "playbook_path": str(playbook_path),
        "goal_slug": goal_slug,
        "goal_label": goal,
        "entry_screen": entry_screen,
        "target_screen": target_screen,
        "navigation_steps": len(navigation_steps),
        "action_steps": len(action_steps),
        "parameterizable_fields": list(parameterizable_fields.keys()),
        "dry_run": dry_run,
        "elapsed_ms": elapsed,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_stable_element(screen: str, discovered_selectors: dict) -> str:
    """Find a stable, recognizable element to wait for after navigating to a screen."""
    disc = discovered_selectors.get(screen, {})
    # Prefer a tab link, a button, or a grid header — something meaningful
    preference_keys = ["usuarios", "roles", "grid", "btn", "tab"]
    for pref in preference_keys:
        for key, sel in disc.items():
            if pref in key.lower() and sel and sel.startswith("#"):
                return sel
    # Fallback: first #id selector found
    for sel in disc.values():
        if sel and sel.startswith("#"):
            return sel
    return ""


def _to_param_key(field_name: str, selector: str) -> str:
    """Convert a field name or selector to an uppercase param key.

    #c_abfMdCodigo → USUARIO_CODIGO (via selector)
    "codigo"       → USUARIO_CODIGO (via field_name)
    """
    # Try from field_name first
    if field_name:
        slug = re.sub(r'[^a-z0-9]+', '_', field_name.lower()).strip('_')
        if slug:
            return slug.upper()
    # Derive from selector: #c_abfMdCodigo → md_codigo → MD_CODIGO
    if selector:
        sel_clean = re.sub(r'^#c_abf|^#c_ddl|^#c_chk|^#c_', '', selector, flags=re.IGNORECASE)
        slug = re.sub(r'([A-Z])', r'_\1', sel_clean).lower().strip('_')
        slug = re.sub(r'[^a-z0-9]+', '_', slug).strip('_')
        if slug:
            return slug.upper()
    return "FIELD_UNKNOWN"


def _infer_source(param_key: str, input_type: str, last_value: str) -> str:
    """Infer how the field value should be obtained during replay."""
    key_lower = param_key.lower()
    # RUT / document number patterns → usually provided by test data
    if any(kw in key_lower for kw in ("rut", "doc", "num_doc", "cedula", "dni", "codigo", "nombre")):
        return "provided"
    # Numeric fields with small values → infer
    if input_type in ("number",) or (last_value.isdigit() and len(last_value) <= 6):
        return "infer_numeric"
    # Checkboxes, selects → provided
    if input_type in ("checkbox", "select", "select-one"):
        return "provided"
    # Fields that look like usernames or unique codes
    if any(kw in key_lower for kw in ("login", "usuario", "user", "md_codigo", "mdcodigo")):
        return "infer_unique"
    if last_value:
        return "provided"
    return "infer_unique"


def _infer_default(source: str, last_value: str) -> str:
    """Provide a sensible default for fields that don't come from test data."""
    if source == "infer_numeric":
        # Use the recorded value if it's numeric, else "100"
        return last_value if (last_value and last_value.isdigit()) else "100"
    if source == "infer_unique":
        return "QA_{{RUN_ID}}"
    return last_value or ""


def _is_required(selector: str, param_key: str) -> bool:
    """Heuristic: consider a field required if it contains 'nombre', 'codigo', 'rut'."""
    combined = (selector + param_key).lower()
    required_keywords = ("nombre", "codigo", "rut", "doc", "mdnombre", "mdcodigo")
    return any(kw in combined for kw in required_keywords)


def _build_action_steps(target_disc: dict, fill_steps: list[dict]) -> list[dict]:
    """Build the action_steps list: button clicks + fill steps.

    Priority: look for 'agregar' / 'add' buttons as the trigger, then
    fill steps in order, then 'guardar' / 'save'.
    """
    steps: list[dict] = []

    # Opening action: agregar / add
    for key_pattern in ("add_agregar", "btn_agregar", "agregar", "add_"):
        for key, sel in target_disc.items():
            if key_pattern in key.lower() and sel:
                steps.append({
                    "action": "click",
                    "selector": sel,
                    "label": key.replace("_", " ").strip(),
                    "_note": "open/add trigger",
                })
                steps.append({"action": "wait", "ms": 2000, "_note": "wait for form to render (PostBack)"})
                break
        if steps:
            break

    # Tab activation if we see tab selectors
    for key, sel in target_disc.items():
        if "usuarios" in key.lower() and sel and ("has-text" in sel or sel.startswith("a[")):
            steps.insert(0, {
                "action": "click",
                "selector": sel,
                "label": "tab Usuarios",
                "_note": "activate Users tab before interacting",
            })
            steps.insert(1, {"action": "wait", "ms": 500})
            break

    # Fill steps
    steps.extend(fill_steps)

    # Closing action: guardar / save
    for key_pattern in ("guardar", "save", "btn_guardar", "btnguardar"):
        for key, sel in target_disc.items():
            if key_pattern in key.lower() and sel:
                steps.append({
                    "action": "click",
                    "selector": sel,
                    "label": key.replace("_", " ").strip(),
                    "_note": "save / submit",
                    "wait_after": "networkidle",
                })
                break
        else:
            continue
        break

    return steps


def _update_form_knowledge(
    screen: str,
    discovered: dict,
    param_fields: dict,
    action_steps: list[dict],
) -> None:
    """Merge knowledge about `screen` into form_knowledge.json."""
    try:
        knowledge: dict = {}
        if _FORM_KNOWLEDGE_PATH.is_file():
            knowledge = json.loads(_FORM_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("session_to_playbook: cannot load form_knowledge.json: %s", exc)
        return

    # Build selectors dict from discovered + param_fields
    selectors: dict[str, str] = {}
    for key, sel in discovered.items():
        if sel and sel.startswith("#"):
            selectors[key] = sel

    # Also add param_fields selectors with readable names
    for param_key, meta in param_fields.items():
        sel = meta.get("selector", "")
        label = meta.get("label") or param_key.lower()
        alias = re.sub(r'[^a-z0-9]+', '_', label.lower()).strip('_')
        if sel and alias:
            selectors[alias] = sel

    screen_entry = knowledge.setdefault(screen, {})
    # Merge selectors — don't overwrite existing curated entries
    existing_selectors = screen_entry.setdefault("selectors", {})
    for alias, sel in selectors.items():
        existing_selectors.setdefault(alias, sel)

    # Add/update playbook reference
    screen_entry["playbook_source"] = "session_to_playbook"
    screen_entry.setdefault("notas", []).append(
        f"Selectores actualizados automáticamente por session_to_playbook v{_TOOL_VERSION}"
    )

    # Remove duplicate notas
    notas = screen_entry.get("notas", [])
    screen_entry["notas"] = list(dict.fromkeys(notas))

    # Update meta
    knowledge.setdefault("_meta", {})["last_updated"] = time.strftime("%Y-%m-%d")

    try:
        _FORM_KNOWLEDGE_PATH.write_text(
            json.dumps(knowledge, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("session_to_playbook: updated form_knowledge.json for %s", screen)
    except Exception as exc:
        logger.warning("session_to_playbook: cannot write form_knowledge.json: %s", exc)


def _slugify(text: str) -> str:
    """Convert text to a filename-safe lowercase slug."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r'[^\w\s-]', '', text.lower())
    slug = re.sub(r'[\s_-]+', '_', slug)
    return slug[:60].strip('_')


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert a session_recorder recording into a replay-ready playbook (Fase 8)."
    )
    p.add_argument(
        "--session", required=True,
        help="Path to a recording directory (containing session.json). "
             "Use evidence/recordings/latest/ for the most recent recording.",
    )
    p.add_argument("--dry-run", action="store_true",
                   help="Print the playbook without writing files.")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    result = run(
        session_dir=Path(args.session),
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
