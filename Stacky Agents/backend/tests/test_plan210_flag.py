"""Plan 210 F0 — Flag del gate de build + campo de perfil con default seguro."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_KEY = "STACKY_DEV_BUILD_VERIFY_ENABLED"


@pytest.fixture(scope="module")
def client():
    from app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_flag_registered_and_curated():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    spec = next((s for s in FLAG_REGISTRY if s.key == _KEY), None)
    assert spec is not None
    assert spec.type == "bool"
    assert spec.default is True
    assert _KEY in _CATEGORY_KEYS["devops"]
    assert _KEY in _CURATED_DEFAULTS_ON


def test_config_default_on():
    from config import config as cfg

    assert getattr(cfg, _KEY) is True


def test_health_exposes_dev_build_verify_enabled(client):
    body = client.get("/api/devops/health").get_json()

    assert "dev_build_verify_enabled" in body
    assert isinstance(body["dev_build_verify_enabled"], bool)


def test_default_profile_has_allow_csproj_entry_false():
    path = ROOT / "services" / "client_profile_defaults" / "azure_devops.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert data["build"]["allow_csproj_entry"] is False, \
        "el default seguro es NO aceptar un .csproj suelto como entrada de build"


def test_module_imports_clean():
    from services.dev_build_verify import _not_verified

    v = _not_verified("x")
    assert v.gate_ok is False
    assert v.ok is False
    assert v.reason == "not_verified", "una razón desconocida cae al default seguro"


def test_nucleo_sin_red_ni_llm():
    fuente = (ROOT / "services" / "dev_build_verify.py").read_text(encoding="utf-8")
    imports = [ln for ln in fuente.splitlines() if ln.strip().startswith(("import ", "from "))]

    for prohibido in ("requests", "urllib", "copilot", "llm"):
        assert not any(prohibido in ln for ln in imports), \
            f"el núcleo del gate no puede importar {prohibido}"


def test_no_existe_la_key_inventada_summary_path():
    """El path del resumen se DERIVA de base_dir; `_summary_path` no existe en el 201."""
    fuente = (ROOT / "services" / "dev_build_verify.py").read_text(encoding="utf-8")

    assert "_summary_path" not in fuente
