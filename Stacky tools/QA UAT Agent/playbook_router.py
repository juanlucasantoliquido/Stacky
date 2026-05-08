"""
playbook_router.py — Deterministic playbook resolver for QA UAT Agent.

Maps a scenario (screen + goal/action description) to a cached playbook
WITHOUT using LLM or dynamic browser exploration.

Algorithm (score-based, no ML):
  1. Load cache/playbooks/index.json.
  2. For each candidate playbook entry:
     a. +3  if target screen matches.
     b. +2  for each confidence_keyword found in the scenario text.
     c. +1  for each tag found in the scenario text.
  3. Return the playbook with the highest score, IF score >= MIN_CONFIDENCE_SCORE.
  4. If no match >= threshold → return None (caller must decide: BLOCKED or fallback).

CLI:
    python playbook_router.py --screen FrmAgenda.aspx --scenario "buscar cliente por RUT"
    python playbook_router.py --rebuild-index     # scans cache/playbooks/ and rebuilds index.json

Output: JSON to stdout.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.playbook_router")

_TOOL_VERSION = "1.0.0"
_PLAYBOOKS_DIR = Path(__file__).parent / "cache" / "playbooks"
_INDEX_FILE = _PLAYBOOKS_DIR / "index.json"
# Minimum score to consider a match confident.
# Screen match alone = 3, so a screen + 1 keyword = 5 (confident).
MIN_CONFIDENCE_SCORE = 4


# ── Public API ─────────────────────────────────────────────────────────────────

def resolve(
    screen: str,
    scenario_text: str,
    index_path: Optional[Path] = None,
) -> dict:
    """Find the best matching playbook for a given screen + scenario description.

    Returns:
        {
          "ok": true,
          "playbook_id": "agregar_usuario_nuevo",
          "playbook_file": "cache/playbooks/agregar_usuario_nuevo.json",
          "score": 7,
          "matched_keywords": ["agregar usuario", "gestion usuarios"]
        }
        or
        {
          "ok": false,
          "error": "NO_PLAYBOOK_MATCH",
          "reason": "NO_PLAYBOOK_OR_UI_MAP",
          "message": "..."
        }
    """
    started = time.time()
    index_path = index_path or _INDEX_FILE

    # Load index
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _no_match(f"Índice de playbooks no encontrado en {index_path}. "
                         "Ejecutá 'python playbook_router.py --rebuild-index'.")
    except Exception as exc:
        return _no_match(f"No se pudo leer el índice de playbooks: {exc}")

    playbooks = index.get("playbooks") or {}
    if not playbooks:
        return _no_match("El índice de playbooks está vacío.")

    text_lower = (scenario_text or "").lower()
    screen_norm = (screen or "").lower()

    best_id: Optional[str] = None
    best_score: int = 0
    best_keywords: list = []

    for pb_id, pb_meta in playbooks.items():
        score = 0
        matched_kw: list = []

        # Screen match — strongest signal
        pb_screen = (pb_meta.get("screen") or "").lower()
        pb_entry  = (pb_meta.get("entry_screen") or "").lower()
        if pb_screen and pb_screen == screen_norm:
            score += 3
        elif pb_entry and pb_entry == screen_norm:
            score += 2

        # Confidence keywords
        for kw in (pb_meta.get("confidence_keywords") or []):
            if kw.lower() in text_lower:
                score += 2
                matched_kw.append(kw)

        # Tags
        for tag in (pb_meta.get("tags") or []):
            if tag.lower() in text_lower:
                score += 1

        if score > best_score:
            best_score = score
            best_id = pb_id
            best_keywords = matched_kw

    if best_id is None or best_score < MIN_CONFIDENCE_SCORE:
        _sc_preview = repr(scenario_text[:80])
        return _no_match(
            f"No hay playbook con score suficiente (mejor: {best_score}, "
            f"mínimo requerido: {MIN_CONFIDENCE_SCORE}) para screen={screen!r}, "
            f"scenario={_sc_preview}. "
            "Grabá el flujo una vez o bajá MIN_CONFIDENCE_SCORE si el threshold es muy estricto."
        )

    pb_meta = playbooks[best_id]
    return {
        "ok": True,
        "playbook_id": best_id,
        "playbook_file": pb_meta.get("file", f"cache/playbooks/{best_id}.json"),
        "score": best_score,
        "matched_keywords": best_keywords,
        "goal_label": pb_meta.get("goal_label", best_id),
        "required_data": pb_meta.get("required_data", []),
        "elapsed_ms": int((time.time() - started) * 1000),
    }


def load_playbook(playbook_file: str) -> Optional[dict]:
    """Load a playbook JSON file. Returns None on error."""
    try:
        p = _PLAYBOOKS_DIR.parent.parent / playbook_file
        if not p.is_file():
            p = Path(playbook_file)
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not load playbook %s: %s", playbook_file, exc)
        return None


def rebuild_index(playbooks_dir: Optional[Path] = None) -> dict:
    """Scan the playbooks directory and rebuild index.json.

    Called with: python playbook_router.py --rebuild-index
    Returns the rebuilt index dict.
    """
    pb_dir = playbooks_dir or _PLAYBOOKS_DIR
    playbooks: dict = {}

    for pb_file in sorted(pb_dir.glob("*.json")):
        if pb_file.name == "index.json":
            continue
        try:
            pb = json.loads(pb_file.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Skipping %s (parse error): %s", pb_file.name, exc)
            continue

        slug = pb.get("goal_slug") or pb_file.stem
        playbooks[slug] = {
            "file": f"cache/playbooks/{pb_file.name}",
            "screen": pb.get("target_screen", ""),
            "entry_screen": pb.get("entry_screen", ""),
            "tags": pb.get("tags") or _extract_tags_from_slug(slug),
            "required_data": _extract_required_data(pb),
            "confidence_keywords": pb.get("confidence_keywords") or _infer_keywords(pb),
            "goal_label": pb.get("goal_label", slug.replace("_", " ")),
        }
        logger.info("Indexed playbook: %s (screen=%s)", slug, playbooks[slug]["screen"])

    index = {
        "$schema": "playbook_index/1.0",
        "_last_updated": _today(),
        "playbooks": playbooks,
    }
    _INDEX_FILE.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Rebuilt playbook index: %d entries → %s", len(playbooks), _INDEX_FILE)
    return index


# ── Helpers ────────────────────────────────────────────────────────────────────

def _no_match(message: str) -> dict:
    return {
        "ok": False,
        "error": "NO_PLAYBOOK_MATCH",
        "reason": "NO_PLAYBOOK_OR_UI_MAP",
        "message": message,
    }


def _extract_tags_from_slug(slug: str) -> list:
    """'agregar_usuario_nuevo' → ['agregar', 'usuario', 'nuevo']"""
    return [w for w in re.split(r"[_\-\s]+", slug.lower()) if w]


def _extract_required_data(pb: dict) -> list:
    """Extract parameterizable field names from playbook action_steps."""
    fields = []
    for step in (pb.get("action_steps") or []):
        for pf in (step.get("parameterizable_fields") or []):
            name = pf.get("name") or pf.get("field")
            if name and name not in fields:
                fields.append(name)
    return fields


def _infer_keywords(pb: dict) -> list:
    """Derive confidence keywords from goal_label + target_screen + action labels."""
    kws = []
    label = (pb.get("goal_label") or "").lower()
    if label:
        kws.append(label)
    screen = (pb.get("target_screen") or "").lower().replace(".aspx", "").replace("frm", "")
    if screen:
        kws.append(screen)
    for step in (pb.get("action_steps") or []):
        lbl = (step.get("label") or "").lower()
        if lbl and len(lbl) > 3:
            kws.append(lbl)
    return list(dict.fromkeys(kws))[:8]  # deduplicate, limit to 8


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    import sys
    p = argparse.ArgumentParser(description="Playbook router for QA UAT Agent")
    p.add_argument("--screen", default="", help="Target screen (e.g. FrmAgenda.aspx)")
    p.add_argument("--scenario", default="", help="Scenario description text")
    p.add_argument("--rebuild-index", action="store_true", dest="rebuild",
                   help="Scan cache/playbooks/ and rebuild index.json")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s: %(message)s")

    if args.rebuild:
        result = rebuild_index()
        print(json.dumps({"ok": True, "indexed": len(result["playbooks"])},
                         ensure_ascii=False, indent=2))
        return

    result = resolve(screen=args.screen, scenario_text=args.scenario)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
