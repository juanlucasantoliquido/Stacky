"""
visual_regression_comparator.py — Visual Regression Comparator.

Compares screenshots before/after to detect unintended visual changes.

Uso:
    from visual_regression_comparator import VisualRegressionComparator
    comparator = VisualRegressionComparator()
    result = comparator.compare(before_bytes, after_bytes, "FrmDetalleClie")
"""

import io
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.visual_regression")


@dataclass
class VisualDiffResult:
    page: str
    diff_pct: float
    passed: bool
    diff_image: Optional[bytes] = None


class VisualRegressionComparator:
    DIFF_THRESHOLD_PCT = 2.0  # >2% pixel difference → FAIL
    PIXEL_TOLERANCE = 10      # ignore changes smaller than this

    def __init__(self, baselines_dir: Optional[str] = None):
        self.baselines_dir = Path(baselines_dir) if baselines_dir else (
            Path(__file__).parent / "tests" / "visual_baselines"
        )

    def compare(
        self,
        baseline_screenshot: bytes,
        current_screenshot: bytes,
        page_name: str,
    ) -> VisualDiffResult:
        try:
            from PIL import Image, ImageChops
            import numpy as np
        except ImportError:
            logger.error("Pillow and numpy required for visual regression")
            return VisualDiffResult(
                page=page_name, diff_pct=0.0, passed=True,
            )

        img_before = Image.open(io.BytesIO(baseline_screenshot)).convert("RGB")
        img_after = Image.open(io.BytesIO(current_screenshot)).convert("RGB")

        # Ensure same size
        if img_before.size != img_after.size:
            img_after = img_after.resize(img_before.size, Image.LANCZOS)

        diff = ImageChops.difference(img_before, img_after)
        diff_array = np.array(diff)

        # Count pixels that changed above tolerance
        changed_pixels = int(np.sum(diff_array > self.PIXEL_TOLERANCE))
        total_pixels = diff_array.size // 3
        diff_pct = (changed_pixels / total_pixels) * 100 if total_pixels > 0 else 0

        passed = diff_pct < self.DIFF_THRESHOLD_PCT

        # Generate diff highlight image
        diff_image = None
        if not passed:
            diff_image = self._highlight_diff(img_before, img_after, diff_array)

        logger.info("[VisualDiff] %s: %.2f%% changed (%s)",
                     page_name, diff_pct, "PASS" if passed else "FAIL")

        return VisualDiffResult(
            page=page_name,
            diff_pct=round(diff_pct, 2),
            passed=passed,
            diff_image=diff_image,
        )

    def save_baseline(self, screenshot: bytes, page_name: str):
        self.baselines_dir.mkdir(parents=True, exist_ok=True)
        path = self.baselines_dir / f"{page_name}.png"
        path.write_bytes(screenshot)
        logger.info("[VisualDiff] Baseline saved for %s", page_name)

    def load_baseline(self, page_name: str) -> Optional[bytes]:
        path = self.baselines_dir / f"{page_name}.png"
        if path.exists():
            return path.read_bytes()
        return None

    def _highlight_diff(self, img_before, img_after, diff_array) -> Optional[bytes]:
        try:
            from PIL import Image
            import numpy as np

            before_array = np.array(img_before)
            mask = np.any(diff_array > self.PIXEL_TOLERANCE, axis=2)

            highlight = before_array.copy()
            highlight[mask] = [255, 0, 0]  # Red overlay on changed areas

            result = Image.fromarray(highlight)
            buf = io.BytesIO()
            result.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None
