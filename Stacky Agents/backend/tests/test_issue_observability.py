"""Plan 52 F4 — paridad de observabilidad Issue ≈ Epic: publish_issue_from_run
devuelve grounding_warnings y epic_summary poblados (reusando las helpers de la
épica), para que el finalizador los selle en metadata también para Issues.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

# HTML que pasa _looks_like_epic (h1 + RF) pero dispara warnings de grounding
# (sin secciones esperadas / confidence baja según _epic_grounding_warnings).
_EPIC_HTML = "<h1>Epica X</h1><h2>RF-1</h2><p>algo</p>"


def _published():
    pub = MagicMock()
    pub.ado_id = 555
    pub.url = "http://ado/555"
    return pub


def test_publish_issue_from_run_emits_grounding_warnings():
    from api import tickets
    with patch.object(tickets, "_publish_issue_to_ado", return_value=_published()), \
         patch.object(tickets, "_post_phase_comment"), \
         patch.object(tickets, "_ado_client_for_ticket"), \
         patch.dict(os.environ, {"STACKY_EPIC_GROUNDING_PREFLIGHT_ENABLED": "true"}):
        res = tickets.publish_issue_from_run(
            output=_EPIC_HTML, brief="b", project_name="P", already_published_id=None,
        )
    assert res.error is None
    assert res.grounding_warnings  # no vacío: la épica mínima dispara warnings


def test_publish_issue_from_run_emits_epic_summary_when_enabled():
    from api import tickets
    with patch.object(tickets, "_publish_issue_to_ado", return_value=_published()), \
         patch.object(tickets, "_post_phase_comment"), \
         patch.object(tickets, "_ado_client_for_ticket"), \
         patch.dict(os.environ, {"STACKY_EPIC_SUMMARY_ENABLED": "true"}):
        res = tickets.publish_issue_from_run(
            output=_EPIC_HTML, brief="b", project_name="P", already_published_id=None,
        )
    assert res.epic_summary is not None


def test_publish_issue_from_run_no_summary_when_disabled():
    from api import tickets
    with patch.object(tickets, "_publish_issue_to_ado", return_value=_published()), \
         patch.object(tickets, "_post_phase_comment"), \
         patch.object(tickets, "_ado_client_for_ticket"), \
         patch.dict(os.environ, {"STACKY_EPIC_SUMMARY_ENABLED": "false"}):
        res = tickets.publish_issue_from_run(
            output=_EPIC_HTML, brief="b", project_name="P", already_published_id=None,
        )
    assert res.epic_summary is None


def test_publish_issue_from_run_skipped_keeps_defaults():
    from api import tickets
    with patch.object(tickets, "_publish_issue_to_ado") as pub:
        res = tickets.publish_issue_from_run(
            output=_EPIC_HTML, brief="b", project_name="P", already_published_id=123,
        )
    assert res.skipped is True
    assert res.grounding_warnings == []
    assert res.epic_summary is None
    pub.assert_not_called()
