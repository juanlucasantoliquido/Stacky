"""A0 — Tests para services.app_version.get_app_version()."""
from __future__ import annotations

import json
import pytest
import importlib


def _reset_cache(monkeypatch):
    """Fuerza recalculo en cada test."""
    monkeypatch.setattr("services.app_version._CACHED_VERSION", None, raising=False)


def test_version_from_version_txt(tmp_path, monkeypatch):
    """Fuente 1: VERSION.txt existe → devuelve su primera línea stripped."""
    _reset_cache(monkeypatch)
    version_file = tmp_path / "VERSION.txt"
    version_file.write_text("1.2.3\n", encoding="utf-8")

    import services.app_version as mod
    monkeypatch.setattr(mod, "_version_txt_path", lambda: version_file)
    monkeypatch.setattr(mod, "_package_json_path", lambda: tmp_path / "nonexistent.json")

    result = mod.get_app_version()
    assert result == "1.2.3"


def test_version_from_package_json_fallback(tmp_path, monkeypatch):
    """Fuente 2: VERSION.txt ausente pero package.json presente → usa version del json."""
    _reset_cache(monkeypatch)
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"version": "0.9.1", "name": "stacky"}), encoding="utf-8")

    import services.app_version as mod
    monkeypatch.setattr(mod, "_version_txt_path", lambda: tmp_path / "nonexistent.txt")
    monkeypatch.setattr(mod, "_package_json_path", lambda: pkg)

    result = mod.get_app_version()
    assert result == "0.9.1"


def test_version_unknown_when_no_sources(tmp_path, monkeypatch):
    """Fuente 3: ningún archivo disponible → 0.0.0-unknown."""
    _reset_cache(monkeypatch)
    import services.app_version as mod
    monkeypatch.setattr(mod, "_version_txt_path", lambda: tmp_path / "no.txt")
    monkeypatch.setattr(mod, "_package_json_path", lambda: tmp_path / "no.json")

    result = mod.get_app_version()
    assert result == "0.0.0-unknown"


def test_version_invalid_json_falls_through(tmp_path, monkeypatch):
    """JSON malformado en package.json → cae a 0.0.0-unknown sin crash."""
    _reset_cache(monkeypatch)
    pkg = tmp_path / "package.json"
    pkg.write_text("{not valid json}", encoding="utf-8")

    import services.app_version as mod
    monkeypatch.setattr(mod, "_version_txt_path", lambda: tmp_path / "no.txt")
    monkeypatch.setattr(mod, "_package_json_path", lambda: pkg)

    result = mod.get_app_version()
    assert result == "0.0.0-unknown"
