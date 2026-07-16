"""Plan 121 F2 — núcleo puro de services/egress_sentinel.py (sin DB, sin red)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.egress_sentinel import (
    build_scan_prompt,
    make_sentinel_metadata,
    mask_excerpt,
    parse_scan_response,
    should_scan,
    truncate_middle,
)


def test_mask_excerpt_never_returns_full_value():
    for n in range(1, 51):
        value = "x" * n
        masked = mask_excerpt(value)
        assert masked != value
        # nunca más de 4 chars originales contiguos del inicio
        assert not masked.startswith(value[:5]) or len(value) <= 4


def test_truncate_middle_zero_means_unlimited():
    text = "a" * 100
    assert truncate_middle(text, 0) == text


def test_truncate_middle_cuts_long_text():
    text = "a" * 1000
    out = truncate_middle(text, 100)
    assert len(out) < len(text)
    assert "recortado" in out


def test_build_scan_prompt_contains_markers_and_kind():
    system, user = build_scan_prompt("hola secreto", kind="manual")
    assert "JSON" in system
    assert "kind: manual" in user
    assert "<<<TEXTO_AUDITADO_INICIO>>>" in user
    assert "<<<TEXTO_AUDITADO_FIN>>>" in user
    assert "hola secreto" in user


def test_parse_valid_json():
    raw = '{"findings": [{"data_class": "secrets", "severity": "critical", "excerpt": "password=hunter2", "rationale": "clave en claro"}]}'
    findings = parse_scan_response(raw)
    assert len(findings) == 1
    assert findings[0]["data_class"] == "secrets"
    assert findings[0]["severity"] == "critical"
    assert "password=hunter2" not in findings[0]["excerpt_masked"]
    assert findings[0]["excerpt_masked"].startswith("pass")


def test_parse_json_with_fences():
    raw = '```json\n{"findings": []}\n```'
    assert parse_scan_response(raw) == []


def test_parse_garbage_returns_empty():
    assert parse_scan_response("esto no es json en absoluto") == []


def test_parse_discards_invalid_items():
    raw = (
        '{"findings": ['
        '{"severity": "critical", "excerpt": "sin data_class"},'
        '{"data_class": "pii", "severity": "nope", "excerpt": "abcdef"}'
        ']}'
    )
    findings = parse_scan_response(raw)
    assert len(findings) == 1
    assert findings[0]["data_class"] == "pii"
    assert findings[0]["severity"] == "info"


def test_make_sentinel_metadata_shape():
    clean = make_sentinel_metadata([], model="qwen3:32b", scanned_chars=10, deterministic_classes=[])
    assert clean["status"] == "clean"
    assert clean["findings"] == []
    assert clean["version"] == 1

    dirty = make_sentinel_metadata(
        [{"data_class": "secrets", "severity": "critical", "excerpt_masked": "pass…***", "rationale": "x"}],
        model="qwen3:32b", scanned_chars=20, deterministic_classes=["secrets"],
    )
    assert dirty["status"] == "findings"
    assert dirty["deterministic_classes"] == ["secrets"]


def test_should_scan_skips_already_scanned_and_empty():
    assert should_scan({"metadata": {"egress_sentinel": {}}, "input_context_text": "algo"}) == (False, "already_scanned")
    assert should_scan({"metadata": {}, "input_context_text": "   "}) == (False, "empty_context")
    assert should_scan({"metadata": {}, "input_context_text": "algo real"}) == (True, "ok")
