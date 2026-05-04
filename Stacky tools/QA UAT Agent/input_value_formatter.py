"""
input_value_formatter.py — Transform raw scenario fill values into the format
required by each native HTML5 input type.

Pure stdlib, no LLM, no I/O. Used by `playwright_test_generator.py` to avoid
the class of test-pipeline bugs where the scenario carries a value in human
format ("01/01/2026", "19000101") but Playwright `fill()` is invoked against
an `<input type="date">` that requires ISO 8601 (`YYYY-MM-DD`). Without this
transform the run blows up with `element is not visible` after Playwright
retries the fill for 10s.

Design rules:
- Deterministic. Same input → same output. No external state.
- Lossless on success (`text`, `email`, `password`, `tel`, `url`, `search`,
  `password`, unknown types) — these passthrough as identity.
- Strict on date/time/month/number/color: if the value cannot be parsed,
  return `(None, error_label)`. The generator escalates this to a
  `blocked` scenario with `reason=input_value_unparseable_for_type`,
  rather than letting Playwright fail at runtime.

Public API:
    format_value(input_type, raw_value) -> (formatted_str, error_label)

`error_label` is None on success; on failure it is one of the labels in
`UNPARSEABLE_LABELS` to drive the blocked-scenario reason.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

_TOOL_VERSION = "1.0.0"

# Date input formats accepted (priority order). All produce ISO 8601 YYYY-MM-DD.
_DATE_PATTERNS = (
    "%Y-%m-%d",      # 2026-01-01 (already ISO)
    "%Y%m%d",        # 19000101
    "%d/%m/%Y",      # 01/01/2026
    "%d-%m-%Y",      # 01-01-2026
    "%m/%d/%Y",      # 01/31/2026 (US, last to avoid ambiguity)
)

# Time input formats accepted. Always produce HH:MM (24h, no seconds).
_TIME_PATTERNS = (
    "%H:%M",         # 14:30
    "%H:%M:%S",      # 14:30:00
    "%I:%M %p",      # 02:30 PM
    "%H%M",          # 1430
)

# Month input formats accepted. Always produce YYYY-MM.
_MONTH_PATTERNS = (
    "%Y-%m",         # 2026-01 (already ISO)
    "%m/%Y",         # 01/2026
    "%Y%m",          # 202601
)

UNPARSEABLE_LABELS = {
    "date": "input_value_unparseable_for_type:date",
    "time": "input_value_unparseable_for_type:time",
    "month": "input_value_unparseable_for_type:month",
    "datetime-local": "input_value_unparseable_for_type:datetime-local",
    "week": "input_value_unparseable_for_type:week",
    "number": "input_value_unparseable_for_type:number",
    "range": "input_value_unparseable_for_type:range",
    "color": "input_value_unparseable_for_type:color",
    "email": "input_value_unparseable_for_type:email",
    "url": "input_value_unparseable_for_type:url",
}

# Identity types: pass value through unchanged.
_IDENTITY_TYPES = frozenset({
    "text", "password", "search", "tel", "email", "url",
    "hidden", "submit", "reset", "button", "checkbox", "radio",
    "file", None, "",
})


def format_value(
    input_type: Optional[str],
    raw_value,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Transform `raw_value` into the canonical string Playwright needs to fill
    an input of `input_type`.

    Returns:
        (formatted_value, error_label)
        - On success: (str, None).
        - On unparseable date/time/month/number/color: (None, label).

    Edge cases:
    - raw_value=None → ("", None) for identity types (Playwright accepts empty
      fills); (None, label) for strict types so the generator can refuse the
      step.
    - input_type unknown / None → identity passthrough on str(raw_value).
    """
    # Normalize input_type to lowercase string for comparison
    itype = (input_type or "").strip().lower() or None

    # Identity passthrough
    if itype in _IDENTITY_TYPES:
        if raw_value is None:
            return "", None
        return str(raw_value), None

    # Strict types: raw_value=None is unparseable
    if raw_value is None or (isinstance(raw_value, str) and not raw_value.strip()):
        return None, UNPARSEABLE_LABELS.get(itype, f"input_value_unparseable_for_type:{itype}")

    raw_str = str(raw_value).strip()

    if itype == "date":
        return _format_date(raw_str)
    if itype == "time":
        return _format_time(raw_str)
    if itype == "month":
        return _format_month(raw_str)
    if itype == "datetime-local":
        return _format_datetime_local(raw_str)
    if itype == "week":
        return _format_week(raw_str)
    if itype in ("number", "range"):
        return _format_number(raw_str, itype)
    if itype == "color":
        return _format_color(raw_str)

    # Unknown type → identity passthrough (don't break working flows).
    return raw_str, None


# ── Date / time formatters ─────────────────────────────────────────────────────

def _format_date(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse various human formats and return ISO YYYY-MM-DD."""
    for fmt in _DATE_PATTERNS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d"), None
        except ValueError:
            continue
    return None, UNPARSEABLE_LABELS["date"]


def _format_time(raw: str) -> Tuple[Optional[str], Optional[str]]:
    for fmt in _TIME_PATTERNS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%H:%M"), None
        except ValueError:
            continue
    return None, UNPARSEABLE_LABELS["time"]


def _format_month(raw: str) -> Tuple[Optional[str], Optional[str]]:
    for fmt in _MONTH_PATTERNS:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m"), None
        except ValueError:
            continue
    return None, UNPARSEABLE_LABELS["month"]


def _format_datetime_local(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """ISO 8601 local datetime: YYYY-MM-DDTHH:MM"""
    patterns = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M")
    for fmt in patterns:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%dT%H:%M"), None
        except ValueError:
            continue
    return None, UNPARSEABLE_LABELS["datetime-local"]


def _format_week(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """ISO week: YYYY-Www. Accept YYYY-Www or YYYY-MM-DD (compute week)."""
    if re.match(r"^\d{4}-W\d{2}$", raw):
        return raw, None
    try:
        dt = datetime.strptime(raw, "%Y-%m-%d")
        iso_year, iso_week, _ = dt.isocalendar()
        return f"{iso_year:04d}-W{iso_week:02d}", None
    except ValueError:
        return None, UNPARSEABLE_LABELS["week"]


def _format_number(raw: str, itype: str) -> Tuple[Optional[str], Optional[str]]:
    """Strip thousands separators (.|, ); accept integers and decimals.
    Output: canonical "123" or "123.45"."""
    cleaned = raw.replace(" ", "")
    # If both `.` and `,` present, infer locale: last separator is decimal.
    if "." in cleaned and "," in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        # Heuristic: if exactly one `,` and 1-2 digits after, treat as decimal.
        parts = cleaned.split(",")
        if len(parts) == 2 and 1 <= len(parts[1]) <= 2:
            cleaned = parts[0] + "." + parts[1]
        else:
            cleaned = cleaned.replace(",", "")
    elif cleaned.count(".") >= 2:
        # Multiple dots = locale thousand separators (es-AR: 1.000.000).
        cleaned = cleaned.replace(".", "")
    try:
        # Force canonical representation
        if "." in cleaned:
            return str(float(cleaned)), None
        return str(int(cleaned)), None
    except ValueError:
        return None, UNPARSEABLE_LABELS.get(itype, UNPARSEABLE_LABELS["number"])


# ── Color ──────────────────────────────────────────────────────────────────────

_COLOR_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")
_COLOR_HEX_SHORT_RE = re.compile(r"^#?([0-9a-fA-F]{3})$")
_NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
    "cyan": "#00ffff", "magenta": "#ff00ff", "gray": "#808080",
    "grey": "#808080", "orange": "#ffa500",
}


def _format_color(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """HTML5 `<input type=color>` requires `#rrggbb` lowercase."""
    cleaned = raw.strip().lower()
    if cleaned in _NAMED_COLORS:
        return _NAMED_COLORS[cleaned], None
    m = _COLOR_HEX_RE.match(cleaned)
    if m:
        return "#" + m.group(1).lower(), None
    m = _COLOR_HEX_SHORT_RE.match(cleaned)
    if m:
        # Expand #abc → #aabbcc
        s = m.group(1).lower()
        return f"#{s[0]*2}{s[1]*2}{s[2]*2}", None
    return None, UNPARSEABLE_LABELS["color"]
