"""
screenshot_annotator.py — Draw bounding-box annotations on evidence screenshots.

Fase 2 of the QA UAT Agent improvement plan (SDD_QA_UAT_MEJORAS.md).

For each step that recorded a bounding box in `step_bboxes.json`, this tool
opens the corresponding screenshot and draws a red box (3 px border) around
the interacted element using Pillow.

Annotated images are saved alongside the original as:
  step_NN_after_annotated.png   (original step_NN_after.png is NEVER overwritten)

Design decisions:
- Pillow is optional. If not installed, the tool returns ok=True with
  annotated=0 and reason="pillow_not_available". The pipeline is never
  blocked.
- The step_bboxes.json file is also optional per scenario. Missing file →
  that scenario is silently skipped.
- A single bbox failure does not block the rest; errors are collected and
  returned in the output.

CLI:
    python screenshot_annotator.py --evidence-dir evidence/65 [--verbose]
    python screenshot_annotator.py --scenario-dir evidence/65/P01 [--verbose]

Output: JSON to stdout
    {"ok": true, "annotated": 3, "skipped": 0, "errors": [], "annotated_paths": [...]}
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.screenshot_annotator")

# Box style (box border, no fill)
_BOX_COLOR = "#FF0000"   # red
_BOX_WIDTH = 3            # pixels
_ANNOTATED_SUFFIX = "_annotated"


# ── Public API ────────────────────────────────────────────────────────────────

def annotate_scenario(
    scenario_dir: Path,
    verbose: bool = False,
) -> dict:
    """Annotate all screenshots for a single scenario directory.

    Reads `step_bboxes.json` from `scenario_dir`. For each entry with a
    non-null bbox, opens the screenshot and saves an annotated copy.

    Returns:
        {"ok": True, "annotated": N, "skipped": M, "errors": [...], "annotated_paths": [...]}
    """
    if verbose:
        logger.setLevel(logging.DEBUG)

    # Check Pillow availability first — fail gracefully
    try:
        from PIL import Image, ImageDraw  # noqa: F401
    except ImportError:
        logger.warning("Pillow not installed — skipping annotation for %s", scenario_dir)
        return {
            "ok": True,
            "annotated": 0,
            "skipped": 0,
            "errors": ["pillow_not_available"],
            "annotated_paths": [],
        }

    bboxes_path = scenario_dir / "step_bboxes.json"
    if not bboxes_path.is_file():
        logger.debug("No step_bboxes.json in %s — skipping", scenario_dir)
        return {
            "ok": True,
            "annotated": 0,
            "skipped": 0,
            "errors": [],
            "annotated_paths": [],
        }

    try:
        entries = json.loads(bboxes_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": True,
            "annotated": 0,
            "skipped": 0,
            "errors": [f"step_bboxes_parse_error: {exc}"],
            "annotated_paths": [],
        }

    annotated = 0
    skipped = 0
    errors: list = []
    annotated_paths: list = []

    for entry in entries:
        if not isinstance(entry, dict):
            skipped += 1
            continue

        bbox = entry.get("bbox")
        if not bbox or not isinstance(bbox, dict):
            skipped += 1
            continue

        # Resolve screenshot path — can be absolute or relative to CWD
        raw_path = entry.get("screenshot_path", "")
        screenshot_path = Path(raw_path)
        if not screenshot_path.is_absolute():
            # Try relative to scenario_dir first, then CWD
            candidate = scenario_dir / screenshot_path
            if candidate.is_file():
                screenshot_path = candidate
            # else: keep as-is and let the is_file check below handle it

        if not screenshot_path.is_file():
            logger.debug("Screenshot not found: %s — skipping step", screenshot_path)
            skipped += 1
            continue

        result = _annotate_single(
            screenshot_path=screenshot_path,
            bbox=bbox,
            target=entry.get("target", ""),
        )
        if result["ok"]:
            annotated += 1
            annotated_paths.append(result["annotated_path"])
        else:
            errors.append(result["error"])
            skipped += 1

    return {
        "ok": True,
        "annotated": annotated,
        "skipped": skipped,
        "errors": errors,
        "annotated_paths": annotated_paths,
    }


def annotate_evidence_dir(
    evidence_dir: Path,
    verbose: bool = False,
) -> dict:
    """Annotate all scenario subdirectories under `evidence_dir`.

    Iterates over immediate subdirectories (P01, P02, …) and calls
    `annotate_scenario` for each one that contains step_bboxes.json.

    Returns an aggregated result.
    """
    if verbose:
        logger.setLevel(logging.DEBUG)

    # Check Pillow once at top level for a cleaner message
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        logger.warning("Pillow not installed — no screenshots will be annotated")
        return {
            "ok": True,
            "annotated": 0,
            "skipped": 0,
            "errors": ["pillow_not_available"],
            "annotated_paths": [],
        }

    if not evidence_dir.is_dir():
        return {
            "ok": False,
            "error": "evidence_dir_not_found",
            "message": f"Directory not found: {evidence_dir}",
        }

    total_annotated = 0
    total_skipped = 0
    all_errors: list = []
    all_paths: list = []

    # Iterate scenario subdirs (non-recursive — only one level deep)
    for scenario_dir in sorted(evidence_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        result = annotate_scenario(scenario_dir=scenario_dir, verbose=verbose)
        total_annotated += result.get("annotated", 0)
        total_skipped += result.get("skipped", 0)
        all_errors.extend(result.get("errors", []))
        all_paths.extend(result.get("annotated_paths", []))

    return {
        "ok": True,
        "annotated": total_annotated,
        "skipped": total_skipped,
        "errors": all_errors,
        "annotated_paths": all_paths,
    }


# ── Internal helpers ─────────────────────────────────────────────────────────

def _annotate_single(
    screenshot_path: Path,
    bbox: dict,
    target: str = "",
) -> dict:
    """Draw a bounding-box on one screenshot and save the annotated copy.

    The annotated file is placed next to the original with `_annotated`
    inserted before the extension:  step_01_after.png → step_01_after_annotated.png

    Returns {"ok": True, "annotated_path": str} or {"ok": False, "error": str}.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return {"ok": False, "error": "pillow_not_available"}

    try:
        x = int(bbox.get("x", 0))
        y = int(bbox.get("y", 0))
        width = int(bbox.get("width", 0))
        height = int(bbox.get("height", 0))

        if width <= 0 or height <= 0:
            return {"ok": False, "error": f"invalid_bbox_dimensions: w={width} h={height}"}

        with Image.open(screenshot_path) as img:
            # Work on a copy so we never corrupt the original
            annotated = img.copy()
            draw = ImageDraw.Draw(annotated)

            # Draw box border — multiple rectangles for thickness
            for offset in range(_BOX_WIDTH):
                draw.rectangle(
                    [x - offset, y - offset, x + width + offset, y + height + offset],
                    outline=_BOX_COLOR,
                )

            # Build annotated file path
            stem = screenshot_path.stem  # e.g. "step_01_after"
            annotated_path = screenshot_path.parent / f"{stem}{_ANNOTATED_SUFFIX}{screenshot_path.suffix}"
            annotated.save(str(annotated_path))

        logger.debug(
            "Annotated %s → %s (bbox: x=%d y=%d w=%d h=%d target=%s)",
            screenshot_path.name,
            annotated_path.name,
            x, y, width, height, target,
        )
        return {"ok": True, "annotated_path": str(annotated_path)}

    except Exception as exc:
        return {"ok": False, "error": f"annotation_failed: {exc}"}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    if args.scenario_dir:
        result = annotate_scenario(
            scenario_dir=Path(args.scenario_dir),
            verbose=args.verbose,
        )
    elif args.evidence_dir:
        result = annotate_evidence_dir(
            evidence_dir=Path(args.evidence_dir),
            verbose=args.verbose,
        )
    else:
        result = {"ok": False, "error": "missing_argument", "message": "Provide --evidence-dir or --scenario-dir"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Annotate evidence screenshots with bounding boxes from step_bboxes.json"
    )
    group = p.add_mutually_exclusive_group()
    group.add_argument("--evidence-dir", help="Evidence directory containing scenario subdirs (e.g. evidence/65)")
    group.add_argument("--scenario-dir", help="Single scenario directory (e.g. evidence/65/P01)")
    p.add_argument("--verbose", action="store_true", help="Debug logging to stderr")
    return p.parse_args()


if __name__ == "__main__":
    main()
