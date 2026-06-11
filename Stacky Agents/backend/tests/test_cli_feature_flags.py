"""Tests de cli_feature_flags — resolución por proyecto (Fase 2)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_disabled_master_always_false():
    from services import cli_feature_flags as f

    assert f.project_enabled(enabled=False, projects_csv="P", project_name="P") is False
    assert f.project_enabled(enabled=False, projects_csv="", project_name="P") is False


def test_empty_allowlist_applies_to_all():
    from services import cli_feature_flags as f

    assert f.project_enabled(enabled=True, projects_csv="", project_name="Cualquiera") is True
    assert f.project_enabled(enabled=True, projects_csv=None, project_name=None) is True


def test_allowlist_matches_case_insensitive_trim():
    from services import cli_feature_flags as f

    assert f.project_enabled(enabled=True, projects_csv=" Pacifico , Otro ", project_name="pacifico") is True
    assert f.project_enabled(enabled=True, projects_csv="Pacifico", project_name="Otro") is False


def test_allowlist_with_no_project_name_is_false():
    from services import cli_feature_flags as f

    # Con allowlist específica y sin nombre de proyecto, no se puede afirmar match.
    assert f.project_enabled(enabled=True, projects_csv="Pacifico", project_name=None) is False
