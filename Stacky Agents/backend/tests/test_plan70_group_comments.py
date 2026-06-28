"""Plan 70 F3 — Grupo comentarios: provider vs AdoClient en _post_phase_comment.

Cubre la lógica de dispatch (provider puerto sin ``fmt`` vs AdoClient legacy con
``fmt="html"``) directamente sobre la función, que es donde vive la bifurcación.
Los endpoints (fetch_comments en /sync y /comments) se validan vía import smoke
+ centinela F12.
"""
from __future__ import annotations

from unittest.mock import MagicMock


def test_post_phase_comment_with_provider_calls_post_comment_without_fmt(monkeypatch):
    import api.tickets as tickets

    marker_phase = "funcional"
    # El marker real vive en _ISSUE_PHASE_MARKERS; forzamos uno conocido
    marker = tickets._ISSUE_PHASE_MARKERS.get(marker_phase)
    assert marker, "fixture: _ISSUE_PHASE_MARKERS['funcional'] debe existir"

    provider = MagicMock(name="gitlab")
    provider.name = "gitlab"
    provider.comment_exists.return_value = False

    tickets._post_phase_comment(provider, ado_id=42, phase=marker_phase, html_content="<p>x</p>")

    provider.comment_exists.assert_called_once_with(str(42), marker)
    provider.post_comment.assert_called_once_with(str(42), f"{marker}\n<p>x</p>")


def test_post_phase_comment_with_provider_skips_when_marker_exists(monkeypatch):
    import api.tickets as tickets

    provider = MagicMock(name="gitlab")
    provider.name = "gitlab"
    provider.comment_exists.return_value = True  # ya posteado

    tickets._post_phase_comment(provider, ado_id=42, phase="funcional", html_content="<p>x</p>")

    provider.comment_exists.assert_called_once()
    provider.post_comment.assert_not_called()  # idempotencia


def test_post_phase_comment_with_adoclient_keeps_fmt_html():
    """Con un AdoClient legacy (sin atributo 'name' del puerto), conserva fmt='html'."""
    import api.tickets as tickets

    ado = MagicMock(name="adoclient")
    # AdoClient NO tiene atributo 'name' (el puerto sí). Simulamos eso.
    del ado.name
    ado.comment_exists.return_value = False

    tickets._post_phase_comment(ado, ado_id=42, phase="funcional", html_content="<p>x</p>")

    ado.post_comment.assert_called_once()
    # El arg keyword 'fmt' debe estar presente y valer "html"
    _, kwargs = ado.post_comment.call_args
    assert kwargs.get("fmt") == "html"


def test_post_phase_comment_unknown_phase_is_noop():
    import api.tickets as tickets

    provider = MagicMock(name="gitlab")
    provider.name = "gitlab"
    tickets._post_phase_comment(provider, ado_id=42, phase="inexistente", html_content="x")
    provider.post_comment.assert_not_called()
