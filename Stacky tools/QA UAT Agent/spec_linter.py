"""
spec_linter.py — Pre-execution linter for generated Playwright spec files.

Enforces: no generated spec may contain login logic.
Login is ONLY allowed in playwright/global.setup.ts.

The linter scans every .spec.ts in the target directory and fails immediately
if it finds any of the forbidden patterns listed in FORBIDDEN_PATTERNS.
If a violation is found the pipeline MUST NOT continue to the runner stage.

CLI:
    python spec_linter.py --specs-dir evidence/<ticket>/tests/
    python spec_linter.py --spec-file path/to/some.spec.ts

Output (stdout JSON):
    {"ok": true,  "checked": 3, "violations": []}
    {"ok": false, "verdict": "BLOCKED",
     "reason": "INVALID_GENERATED_SPEC_LOGIN_LOGIC",
     "message": "...", "violations": [...]}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Dict

_TOOL_VERSION = "1.0.0"

# ── Forbidden patterns ────────────────────────────────────────────────────────
# Each entry: (regex_pattern, human_description)
# All patterns are matched case-insensitively against the FULL file content.
FORBIDDEN_PATTERNS: List[tuple] = [
    # Login page navigation
    (r'FrmLogin\.aspx',           "Navigation to FrmLogin.aspx"),
    # ASP.NET login-form field IDs (old and new)
    (r'txtUsuario',               "Legacy login selector txtUsuario"),
    (r'txtPassword',              "Legacy login selector txtPassword"),
    (r'txtContrasena',            "Legacy login selector txtContrasena"),
    # AIS login selectors used by global.setup.ts
    (r'c_abfUsuario',             "Login selector c_abfUsuario"),
    (r'c_abfContrasena',          "Login selector c_abfContrasena"),
    (r'c_btnOk.*login|login.*c_btnOk',  "Login button c_btnOk used in login context"),
    # Playwright auth manipulation
    (r'clearCookies',             "clearCookies call (auth reset)"),
    (r'storageState\s*\(\s*\{',   "storageState write (auth persistence)"),
    (r'context\.clearCookies',    "context.clearCookies (auth reset)"),
    # Credential usage in fill actions
    (r'fill\s*\([^,]+,\s*(?:user|username|usuario|login)\b', "fill() with credential username"),
    (r'fill\s*\([^,]+,\s*(?:pass|password|contrasena|contraseña)\b',
     "fill() with credential password"),
    # Direct env var reads for credentials
    (r'process\.env\.AGENDA_WEB_USER',  "Reads AGENDA_WEB_USER env (login only in global.setup.ts)"),
    (r'process\.env\.AGENDA_WEB_PASS',  "Reads AGENDA_WEB_PASS env (login only in global.setup.ts)"),
    # force:true on page navigation (login bypass hack)
    (r'goto\s*\([^)]+,\s*\{[^}]*force\s*:\s*true', "goto with force:true (auth bypass)"),
    # waitForURL targeting login
    (r'waitForURL\s*\([^)]*[Ll]ogin',  "waitForURL targeting login page"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE | re.DOTALL), desc)
             for p, desc in FORBIDDEN_PATTERNS]


def lint_file(spec_path: Path) -> List[Dict]:
    """Lint a single .spec.ts file. Returns list of violation dicts (empty = OK)."""
    try:
        content = spec_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [{"file": str(spec_path), "pattern": "FILE_READ_ERROR",
                 "description": str(exc), "line": None}]

    violations = []
    lines = content.splitlines()
    for pattern, description in _COMPILED:
        for i, line in enumerate(lines, start=1):
            if pattern.search(line):
                violations.append({
                    "file": str(spec_path),
                    "line": i,
                    "pattern": pattern.pattern,
                    "description": description,
                    "excerpt": line.strip()[:120],
                })
    return violations


def lint_directory(specs_dir: Path) -> dict:
    """Lint all .spec.ts files in a directory."""
    spec_files = sorted(specs_dir.glob("*.spec.ts"))
    if not spec_files:
        return {
            "ok": True,
            "checked": 0,
            "violations": [],
            "message": f"No .spec.ts files found in {specs_dir}",
        }

    all_violations = []
    for spec_file in spec_files:
        all_violations.extend(lint_file(spec_file))

    return _build_result(len(spec_files), all_violations)


def lint_single(spec_path: Path) -> dict:
    """Lint a single .spec.ts file."""
    violations = lint_file(spec_path)
    return _build_result(1, violations)


def _build_result(checked: int, violations: list) -> dict:
    if not violations:
        return {
            "ok": True,
            "checked": checked,
            "violations": [],
        }
    return {
        "ok": False,
        "verdict": "BLOCKED",
        "reason": "INVALID_GENERATED_SPEC_LOGIN_LOGIC",
        "message": (
            "El spec generado intenta manejar login. "
            "El login solo puede ocurrir en playwright/global.setup.ts. "
            f"Se encontraron {len(violations)} violación(es) en {checked} spec(s)."
        ),
        "checked": checked,
        "violations": violations,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Lint generated .spec.ts files for login violations")
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--specs-dir", help="Directory containing .spec.ts files to lint")
    group.add_argument("--spec-file", help="Single .spec.ts file to lint")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.specs_dir:
        result = lint_directory(Path(args.specs_dir))
    else:
        result = lint_single(Path(args.spec_file))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
