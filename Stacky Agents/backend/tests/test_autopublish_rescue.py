"""Tests F2/F3 (plan 47) — rescate enganchado en autopublish_epic_from_run."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api import tickets

# Cuerpo real bajo el heading RF (no vacío): con STACKY_EPIC_GATE_ENABLED=true
# (default ON desde 2026-07-15) un RF sin contenido clasifica rf_empty_body y
# bloquea needs_review; estos tests prueban rescate/recovery, no el gate, así
# que el fixture necesita ser una épica genuinamente completa.
_VALID_EPIC = "<h1>Épica</h1>\n<h2>RF-01 algo</h2>\n<p>El módulo procesa el algo end-to-end.</p>"


def _publish_ok(**_kw):
    return SimpleNamespace(ado_id=123, url="http://x/123")


def _call(output, **extra):
    return tickets.autopublish_epic_from_run(
        output=output,
        brief="brief",
        project_name="Proj",
        already_published_id=None,
        **extra,
    )


def test_rescue_disabled_returns_epic_not_in_output(monkeypatch):
    # STACKY_ARTIFACT_RESCUE_ENABLED pasó a default ON el 2026-07-15 (barrido de
    # flags): se fuerza OFF acá para seguir cubriendo ese camino explícitamente.
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "false")
    with patch("services.artifact_rescue.find_rescued_html") as m_find:
        res = _call("narración sin épica alguna")
    assert res.error and res.error.startswith("epic_not_in_output")
    assert res.ado_id is None
    assert res.skipped is False
    m_find.assert_not_called()


def test_rescue_enabled_with_disk_artifact_publishes(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.resolve_outputs_dir", return_value="/x"), \
         patch("services.artifact_rescue.find_rescued_html", return_value=_VALID_EPIC), \
         patch("api.tickets._publish_epic_to_ado", side_effect=_publish_ok):
        res = _call("narración")
    assert res.ado_id == 123
    assert res.error is None
    assert res.skipped is False


def test_rescue_enabled_no_artifact_falls_back_to_error(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.resolve_outputs_dir", return_value="/x"), \
         patch("services.artifact_rescue.find_rescued_html", return_value=None):
        res = _call("narración")
    assert res.error and res.error.startswith("epic_not_in_output")


def test_rescue_enabled_but_rescued_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.resolve_outputs_dir", return_value="/x"), \
         patch("services.artifact_rescue.find_rescued_html", return_value="hola"):
        res = _call("narración")
    assert res.error and res.error.startswith("epic_not_in_output")


def test_rescue_exception_falls_back_safely(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.resolve_outputs_dir", return_value="/x"), \
         patch("services.artifact_rescue.find_rescued_html", side_effect=RuntimeError("boom")):
        res = _call("narración")
    assert res.error and res.error.startswith("epic_not_in_output")


def test_already_published_skips_rescue(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.find_rescued_html") as m_find:
        res = tickets.autopublish_epic_from_run(
            output="narración", brief="b", project_name="P",
            already_published_id=99,
        )
    assert res.skipped is True
    assert res.ado_id == 99
    m_find.assert_not_called()


def test_valid_output_does_not_trigger_rescue(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.find_rescued_html") as m_find, \
         patch("api.tickets._publish_epic_to_ado", side_effect=_publish_ok):
        res = _call(_VALID_EPIC)
    assert res.ado_id == 123
    m_find.assert_not_called()


def test_run_started_at_passed_as_min_mtime(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.resolve_outputs_dir", return_value="/x"), \
         patch("services.artifact_rescue.find_rescued_html", return_value=None) as m_find:
        _call("narración", run_started_at=12345.0)
    assert m_find.call_args.kwargs["min_mtime"] == 12345.0


# ── F3 ────────────────────────────────────────────────────────────────────────

def test_recovery_method_inline_on_valid_output(monkeypatch):
    with patch("api.tickets._publish_epic_to_ado", side_effect=_publish_ok):
        res = _call(_VALID_EPIC)
    assert res.recovery_method == "published_inline"


def test_recovery_method_rescued_on_disk_artifact(monkeypatch):
    monkeypatch.setenv("STACKY_ARTIFACT_RESCUE_ENABLED", "true")
    with patch("services.artifact_rescue.resolve_outputs_dir", return_value="/x"), \
         patch("services.artifact_rescue.find_rescued_html", return_value=_VALID_EPIC), \
         patch("api.tickets._publish_epic_to_ado", side_effect=_publish_ok):
        res = _call("narración")
    assert res.recovery_method == "rescued_from_disk"


def test_recovery_method_none_on_unrecoverable(monkeypatch):
    monkeypatch.delenv("STACKY_ARTIFACT_RESCUE_ENABLED", raising=False)
    res = _call("narración")
    assert res.recovery_method is None
