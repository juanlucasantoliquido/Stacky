"""tests/test_incident_vision.py — Plan 166 F2.

Visión de capturas: extrae texto de imágenes adjuntas con un endpoint de
visión OpenAI-compatible ANTES del análisis, y lo mete inline en el
manifiesto de adjuntos.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import requests

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import runtime_paths
from services import incident_store


# ── 1-3. extract_text_from_image ────────────────────────────────────────────


class _FakeResp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body or {}

    def json(self):
        return self._body


def test_extract_returns_text_on_200(tmp_path, monkeypatch):
    from services import incident_vision

    img = tmp_path / "shot.png"
    img.write_bytes(b"fakepngbytes")

    def _fake_post(url, headers=None, json=None, timeout=None, **kw):
        return _FakeResp(200, {"choices": [{"message": {"content": "ERROR 500 en login"}}]})

    monkeypatch.setattr(requests, "post", _fake_post)
    text = incident_vision.extract_text_from_image(
        img, "image/png", endpoint="http://x/v1/chat/completions", model="llava",
    )
    assert text == "ERROR 500 en login"


def test_extract_returns_none_on_error(tmp_path, monkeypatch):
    from services import incident_vision

    img = tmp_path / "shot.png"
    img.write_bytes(b"fakepngbytes")

    def _fake_post(url, headers=None, json=None, timeout=None, **kw):
        raise requests.exceptions.ConnectionError("no route")

    monkeypatch.setattr(requests, "post", _fake_post)
    text = incident_vision.extract_text_from_image(
        img, "image/png", endpoint="http://x/v1/chat/completions", model="llava",
    )
    assert text is None


def test_extract_returns_none_on_non_200(tmp_path, monkeypatch):
    from services import incident_vision

    img = tmp_path / "shot.png"
    img.write_bytes(b"fakepngbytes")

    def _fake_post(url, headers=None, json=None, timeout=None, **kw):
        return _FakeResp(404, {})

    monkeypatch.setattr(requests, "post", _fake_post)
    text = incident_vision.extract_text_from_image(
        img, "image/png", endpoint="http://x/v1/chat/completions", model="llava",
    )
    assert text is None


# ── 4-5-7. enrich_incident_with_ocr ─────────────────────────────────────────


def _create_incident_with_images(tmp_path, monkeypatch, n_images=1):
    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    files = [(f"shot{i}.png", b"fakebytes") for i in range(n_images)]
    return incident_store.create_incident("incidencia con capturas", files)


def _set_vision_config(monkeypatch, *, ocr_enabled=True, endpoint="http://x/v1/chat/completions", model="llava"):
    import config as cfg
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_VISION_OCR_ENABLED", ocr_enabled, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_VISION_ENDPOINT", endpoint, raising=False)
    monkeypatch.setattr(cfg.config, "STACKY_INCIDENT_VISION_MODEL", model, raising=False)


def test_enrich_sets_ocr_text_on_image_files(tmp_path, monkeypatch):
    from services import incident_vision

    incident = _create_incident_with_images(tmp_path, monkeypatch, n_images=1)
    _set_vision_config(monkeypatch)
    monkeypatch.setattr(
        incident_vision, "extract_text_from_image",
        lambda *a, **kw: "texto ocr de prueba",
    )

    result = incident_vision.enrich_incident_with_ocr(incident["id"])
    assert result["files"][0]["ocr_text"] == "texto ocr de prueba"

    persisted = incident_store.get_incident(incident["id"])
    assert persisted["files"][0]["ocr_text"] == "texto ocr de prueba"


def test_enrich_noop_without_endpoint(tmp_path, monkeypatch):
    from services import incident_vision

    incident = _create_incident_with_images(tmp_path, monkeypatch, n_images=1)
    _set_vision_config(monkeypatch, endpoint="", model="")

    result = incident_vision.enrich_incident_with_ocr(incident["id"])
    assert "ocr_text" not in result["files"][0]


def test_enrich_respects_image_cap(tmp_path, monkeypatch):
    from services import incident_vision

    incident = _create_incident_with_images(tmp_path, monkeypatch, n_images=8)
    _set_vision_config(monkeypatch)

    calls = {"n": 0}

    def _counting_extract(*a, **kw):
        calls["n"] += 1
        return f"ocr-{calls['n']}"

    monkeypatch.setattr(incident_vision, "extract_text_from_image", _counting_extract)
    incident_vision.enrich_incident_with_ocr(incident["id"])
    assert calls["n"] == incident_vision._MAX_IMAGES_PER_INCIDENT


# ── 6. build_attachments_manifest incluye el OCR ────────────────────────────


def test_manifest_includes_ocr_text(tmp_path, monkeypatch):
    from services import incident_context

    monkeypatch.setattr(runtime_paths, "data_dir", lambda: tmp_path)
    incident = incident_store.create_incident("incidencia con captura", [("shot.png", b"fakebytes")])
    files = incident["files"]
    files[0]["ocr_text"] = "ERROR 500 en login"
    incident_store.update_incident(incident["id"], files=files)
    updated = incident_store.get_incident(incident["id"])

    manifest = incident_context.build_attachments_manifest(updated)
    assert "texto extraído de la captura" in manifest.lower()
    assert "ERROR 500 en login" in manifest


# ── 8. F2b — refuerzo del prompt de IncidentAgent ───────────────────────────


def test_incident_prompt_mentions_vision_section():
    from agents.incident import IncidentAgent

    prompt = IncidentAgent().system_prompt()
    assert "Texto extraído de las capturas (visión)" in prompt
