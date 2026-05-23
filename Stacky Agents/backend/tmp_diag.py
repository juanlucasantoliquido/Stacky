"""Compatibility wrapper for the in-app diagnostics screen.

The production diagnostic surface is GET /api/diag/local. This script remains
only as a small CLI fallback for support sessions launched from the backend dir.
"""
from __future__ import annotations

import json

from services.local_diagnostics import run_local_diagnostics


if __name__ == "__main__":
    print(json.dumps(run_local_diagnostics(), indent=2, ensure_ascii=False))
