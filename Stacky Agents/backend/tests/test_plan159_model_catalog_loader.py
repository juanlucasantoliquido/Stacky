"""tests/test_plan159_model_catalog_loader.py — Plan 159 v2 F0.

Loader del catálogo único de modelos/efforts (frozen-aware vía
runtime_paths.backend_root) + caché por mtime + caché copilot con TTL.
9 casos. Fixture autouse resetea los cachés módulo-level (C11b, test-order
pollution del repo).
"""
import json
import re
from pathlib import Path

import pytest

import runtime_paths
from services import model_catalog


@pytest.fixture(autouse=True)
def _reset_catalog_caches():
    model_catalog._cache.update(data=None, loaded_at=0.0, mtime=None)
    model_catalog._copilot_cache.update(models=None, loaded_at=0.0, error=None)
    yield


def _write_catalog(path: Path, claude_model_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({
            "runtimes": {
                "claude_code_cli": {
                    "source": "static_config_file",
                    "default_model": claude_model_id,
                    "default_effort": "medium",
                    "models": [{"id": claude_model_id, "label": claude_model_id}],
                    "efforts": [{"id": "medium", "label": "medium"}],
                    "effort_support": {},
                }
            }
        }),
        encoding="utf-8",
    )


def test_loads_real_file_claude_code_cli_has_sonnet5():
    result = model_catalog.load_model_catalog(force_refresh=True)
    assert result["fallback_used"] is False
    ids = {m["id"] for m in result["runtimes"]["claude_code_cli"]["models"]}
    assert "claude-sonnet-5" in ids  # guarda de regresión del bug original


def test_missing_file_falls_back_to_emergency(monkeypatch, tmp_path):
    monkeypatch.setattr(model_catalog, "_catalog_path", lambda: tmp_path / "no_existe.json")
    result = model_catalog.load_model_catalog(force_refresh=True)
    assert result["fallback_used"] is True
    assert result["runtimes"]["claude_code_cli"]["models"]  # no vacío


def test_malformed_json_falls_back(monkeypatch, tmp_path):
    broken = tmp_path / "model_catalog.json"
    broken.write_text("{ esto no es json valido ", encoding="utf-8")
    monkeypatch.setattr(model_catalog, "_catalog_path", lambda: broken)
    result = model_catalog.load_model_catalog(force_refresh=True)
    assert result["fallback_used"] is True
    assert result["error"]  # mensaje presente, sin excepción


def test_cache_reused_within_ttl(monkeypatch, tmp_path):
    path = tmp_path / "model_catalog.json"
    _write_catalog(path, "claude-sonnet-5")
    monkeypatch.setattr(model_catalog, "_catalog_path", lambda: path)
    # Congelar el reloj: ambas llamadas caen dentro del TTL.
    monkeypatch.setattr(model_catalog.time, "time", lambda: 1000.0)

    reads = {"n": 0}
    real_read = Path.read_text

    def counting_read(self, *a, **k):
        reads["n"] += 1
        return real_read(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", counting_read)

    first = model_catalog.load_model_catalog()
    second = model_catalog.load_model_catalog()
    assert reads["n"] == 1  # segunda llamada NO relee disco
    assert first is second


def test_cache_invalidated_on_mtime_change(monkeypatch, tmp_path):
    import os
    path = tmp_path / "model_catalog.json"
    _write_catalog(path, "modelo-viejo")
    monkeypatch.setattr(model_catalog, "_catalog_path", lambda: path)

    first = model_catalog.load_model_catalog()
    assert first["runtimes"]["claude_code_cli"]["default_model"] == "modelo-viejo"

    # Editar en disco + cambiar mtime explícitamente (KPI-2: sin restart, sin force_refresh).
    _write_catalog(path, "modelo-nuevo")
    os.utime(path, (2_000_000_000, 2_000_000_000))

    second = model_catalog.load_model_catalog()
    assert second["runtimes"]["claude_code_cli"]["default_model"] == "modelo-nuevo"


def test_path_resolves_via_runtime_paths_backend_root(monkeypatch, tmp_path):
    # C1: en el deploy congelado backend_root() = dir del exe; el JSON vive ahí.
    _write_catalog(tmp_path / "config" / "model_catalog.json", "modelo-frozen-test")
    monkeypatch.setattr(runtime_paths, "backend_root", lambda: tmp_path)
    result = model_catalog.load_model_catalog(force_refresh=True)
    ids = {m["id"] for m in result["runtimes"]["claude_code_cli"]["models"]}
    assert "modelo-frozen-test" in ids


def test_catalog_default_model_matches_config_literal():
    # C6 anti-drift: el default del JSON no puede divergir de config.py en silencio.
    config_text = (Path(__file__).resolve().parent.parent / "config.py").read_text(encoding="utf-8")
    m = re.search(r'os\.getenv\(\s*"CLAUDE_CODE_CLI_MODEL",\s*"([^"]+)"\)', config_text)
    assert m is not None, "no se encontró el literal default de CLAUDE_CODE_CLI_MODEL en config.py"
    config_default = m.group(1)

    result = model_catalog.load_model_catalog(force_refresh=True)
    assert result["runtimes"]["claude_code_cli"]["default_model"] == config_default


def test_effort_support_consistent_with_models():
    # C6 anti-drift: consistencia interna del JSON de claude_code_cli.
    result = model_catalog.load_model_catalog(force_refresh=True)
    cc = result["runtimes"]["claude_code_cli"]
    model_ids = {m["id"] for m in cc["models"]}
    effort_ids = {e["id"] for e in cc["efforts"]}
    for model_id, efforts in cc["effort_support"].items():
        assert model_id in model_ids, f"effort_support refiere modelo inexistente: {model_id}"
        for eff in efforts:
            assert eff in effort_ids, f"effort_support refiere effort inexistente: {eff}"


def test_copilot_models_cached_single_network_call(monkeypatch):
    import copilot_bridge
    calls = {"n": 0}

    def fake_list(timeout_sec=5):
        calls["n"] += 1
        return [{"id": "gpt-x", "name": "GPT X"}]

    monkeypatch.setattr(copilot_bridge, "list_copilot_models", fake_list)

    first = model_catalog.get_copilot_models_cached()
    second = model_catalog.get_copilot_models_cached()
    assert calls["n"] == 1  # segunda llamada usa caché
    assert first["models"] and first["models"][0]["id"] == "gpt-x"
    assert second["error"] is None

    third = model_catalog.get_copilot_models_cached(force_refresh=True)
    assert calls["n"] == 2  # refresh fuerza red
    assert third["models"][0]["id"] == "gpt-x"
