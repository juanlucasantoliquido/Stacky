"""Plan 211 F0 — Las 2 flags del inspector/barrido, cableadas en los 5 lugares."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEYS = ("STACKY_DEV_POST_BUILD_INSPECT_ENABLED", "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED")


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_both_flags_registered_and_curated():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _KEYS:
        assert key in by_key, f"{key} no está en FLAG_REGISTRY"
        assert by_key[key].type == "bool"
        assert by_key[key].default is True
        assert key in _CATEGORY_KEYS["devops"]
        assert key in _CURATED_DEFAULTS_ON


def test_config_defaults_on():
    from config import config as cfg

    for key in _KEYS:
        assert getattr(cfg, key) is True


def test_health_exposes_both_flags(client):
    body = client.get("/api/devops/health").get_json()

    assert isinstance(body["post_build_inspect_enabled"], bool)
    assert isinstance(body["port_residue_scan_enabled"], bool)


def test_modules_import_clean():
    from services import (dev_build_contributors, port_residue_scanner,
                          post_build_inspector)

    assert post_build_inspector.inspect_projects([], workspace_root="x") == []
    assert port_residue_scanner.scan_files_for_foreign_tokens([], {}, workspace_root="x") == []
    assert callable(dev_build_contributors.register)


def test_registro_en_app():
    fuente = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "dev_build_contributors.register" in fuente


def test_scanner_sin_shell_true():
    fuente = (ROOT / "services" / "port_residue_scanner.py").read_text(encoding="utf-8")

    assert "shell=True" not in fuente
