from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

ROOT = Path(__file__).parent.parent.parent


def test_contracts_v2_schema_valid_for_migrated_screens():
    from validate_navigation_contracts import validate_contracts

    result = validate_contracts(
        contracts_path=ROOT / "navigation_contracts.yml",
        schema_path=ROOT / "schemas" / "NavigationContracts.v2.schema.json",
    )

    assert result["ok"] is True, result
    assert result["screens_validated"] >= 11
    assert result["screens_v2"] >= 6
    assert result["screens_v1_legacy"] >= 1
    assert not result["errors"]
