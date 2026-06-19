"""Plan 42 F1 — Índice técnico (technical_master) en bloque client-profile.

El perfil del cliente ya se serializa completo en build_client_profile_block;
estos tests verifican que docs_indexes.technical_master está presente en el
content del bloque cuando el perfil lo tiene, y ausente cuando no.

Tests:
1. test_block_includes_technical_master_when_present
2. test_block_omits_technical_master_when_absent
3. test_block_still_includes_functional_indexes
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BASE_PROFILE = {
    "schema_version": 2,
    "terminology": {"product_name": "TestProd", "client_label": ""},
    "docs_indexes": {
        "functional_online": "docs/funcional/INDEX_ONLINE.md",
        "functional_batch": "docs/funcional/INDEX_BATCH.md",
    },
    "database": {},
    "build": {},
    "conventions": {},
}


def _profile_with_tech(**extra_docs):
    p = {**_BASE_PROFILE, "docs_indexes": {**_BASE_PROFILE["docs_indexes"], **extra_docs}}
    return p


def _build_block(profile: dict) -> dict | None:
    from services import context_enrichment as ce
    from services.client_profile import load_client_profile, get_project_tracker_type, merge_with_defaults

    with patch("services.context_enrichment._inject_client_profile_block") as _mock:
        pass  # solo importamos

    with (
        patch("services.client_profile.load_client_profile", return_value=profile),
        patch("services.client_profile.get_project_tracker_type", return_value="ado"),
        patch("services.client_profile.merge_with_defaults", return_value=profile),
    ):
        return ce.build_client_profile_block("test-project")


def test_block_includes_technical_master_when_present():
    """Cuando el perfil tiene technical_master, aparece en el content del bloque."""
    profile = _profile_with_tech(technical_master="docs/tecnica/MASTER.md")
    os.environ["STACKY_INJECT_CLIENT_PROFILE"] = "true"
    block = _build_block(profile)
    assert block is not None, "Debería construirse el bloque"
    assert "technical_master" in block["content"], (
        "technical_master debería aparecer en el content del client-profile"
    )
    assert "docs/tecnica/MASTER.md" in block["content"]


def test_block_omits_technical_master_when_absent():
    """Cuando el perfil NO tiene technical_master, no aparece en el content."""
    profile = _BASE_PROFILE  # sin technical_master
    os.environ["STACKY_INJECT_CLIENT_PROFILE"] = "true"
    block = _build_block(profile)
    assert block is not None
    assert "technical_master" not in block["content"], (
        "Sin technical_master en el perfil, no debería aparecer en el content"
    )


def test_block_still_includes_functional_indexes():
    """Los índices funcionales siguen presentes cuando se agrega technical_master."""
    profile = _profile_with_tech(technical_master="docs/tecnica/MASTER.md")
    os.environ["STACKY_INJECT_CLIENT_PROFILE"] = "true"
    block = _build_block(profile)
    assert block is not None
    assert "functional_online" in block["content"]
    assert "functional_batch" in block["content"]
