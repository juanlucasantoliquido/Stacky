"""Plan 215 F2 — store de config de publish por (workspace, slug)."""
from __future__ import annotations

import pytest

from services import publish_config_store as store


@pytest.fixture(autouse=True)
def _tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "store_path", lambda: tmp_path / "publish_configs.json")
    yield


def test_load_missing_returns_default():
    cfg = store.load_config("C:\\ws", "mi-sln")
    assert cfg == store.default_config()
    assert cfg["mode"] == "auto"
    assert cfg["updated_at"] is None


def test_save_and_reload_roundtrip():
    saved = store.save_config("C:\\ws", "mi-sln", {"mode": "build_only", "configuration": "Debug"})
    assert saved["mode"] == "build_only"
    assert saved["updated_at"] is not None
    again = store.load_config("C:\\ws", "mi-sln")
    assert again["mode"] == "build_only"
    assert again["configuration"] == "Debug"


def test_save_merges_partial_input_over_default():
    saved = store.save_config("C:\\ws", "s", {"configuration": "Staging"})
    assert saved["mode"] == "auto"
    assert saved["extra_args"] == []
    assert saved["register_as_deploy_app"] is False


def test_invalid_mode_rejected():
    with pytest.raises(ValueError) as exc:
        store.save_config("C:\\ws", "s", {"mode": "deployar"})
    assert "mode" in str(exc.value)


def test_extra_args_with_space_or_semicolon_rejected():
    with pytest.raises(ValueError):
        store.save_config("C:\\ws", "s", {"extra_args": ["-p:X=Y; rm -rf /"]})
    with pytest.raises(ValueError):
        store.save_config("C:\\ws", "s", {"extra_args": ["/p:A=B C"]})
    with pytest.raises(ValueError):
        store.save_config("C:\\ws", "s", {"extra_args": ["ok"] * 9})


def test_extra_args_valid_msbuild_property_accepted():
    saved = store.save_config("C:\\ws", "s", {"extra_args": ["/p:Platform=AnyCPU"]})
    assert saved["extra_args"] == ["/p:Platform=AnyCPU"]


def test_project_csproj_must_be_project_file():
    with pytest.raises(ValueError):
        store.save_config("C:\\ws", "s", {"project_csproj": "C:\\ws\\leeme.txt"})
    saved = store.save_config("C:\\ws", "s", {"project_csproj": "C:\\ws\\A\\A.csproj"})
    assert saved["project_csproj"].endswith(".csproj")


def test_corrupt_json_degrades_to_empty(tmp_path):
    (tmp_path / "publish_configs.json").write_text("{no es json", encoding="utf-8")
    assert store.load_config("C:\\ws", "s") == store.default_config()


def test_two_workspaces_do_not_collide():
    store.save_config("C:\\ws1", "s", {"configuration": "Debug"})
    store.save_config("C:\\ws2", "s", {"configuration": "Release"})
    assert store.load_config("C:\\ws1", "s")["configuration"] == "Debug"
    assert store.load_config("C:\\ws2", "s")["configuration"] == "Release"
