"""Plan 214 F2 — espera de idle ASP.NET (WebForms-safe) en el driver.

`wait_aspnet_idle` es una espera CORTA y acotada que NUNCA lanza: devuelve True
si la página quedó idle (readyState complete + sin async postback del
PageRequestManager) y False si se agotó el presupuesto.

Comando:
  cd "N:\\GIT\\RS\\STACKY\\Stacky\\Stacky tools\\QA UAT Agent"
  & "..\\..\\Stacky Agents\\backend\\.venv\\Scripts\\python.exe" -m pytest tests\\unit\\test_plan214_webforms_idle.py -q
"""
import asyncio
import os
import sys
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from navigation_driver import _ASPNET_IDLE_JS, wait_aspnet_idle


def _page(evaluate_side_effect=None, evaluate_return=None) -> MagicMock:
    page = MagicMock()
    page.url = "http://localhost/AgendaWeb/FrmAgenda.aspx"
    if evaluate_side_effect is not None:
        page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    else:
        page.evaluate = AsyncMock(return_value=evaluate_return)
    return page


def test_idle_inmediato():
    page = _page(evaluate_return=True)
    started = time.monotonic()
    assert asyncio.run(wait_aspnet_idle(page, timeout_ms=3000)) is True
    assert (time.monotonic() - started) < 0.3
    assert page.evaluate.await_count == 1


def test_idle_tras_polls():
    page = _page(evaluate_side_effect=[False, False, True])
    assert asyncio.run(wait_aspnet_idle(page, timeout_ms=3000)) is True
    assert page.evaluate.await_count == 3


def test_timeout_devuelve_false():
    page = _page(evaluate_return=False)
    assert asyncio.run(wait_aspnet_idle(page, timeout_ms=300)) is False


def test_evaluate_lanza_no_rompe():
    page = _page(evaluate_side_effect=RuntimeError("Execution context was destroyed"))
    assert asyncio.run(wait_aspnet_idle(page, timeout_ms=300)) is False


def test_js_contempla_page_request_manager():
    """El JS debe mirar readyState Y el PageRequestManager (UpdatePanel)."""
    assert "readyState" in _ASPNET_IDLE_JS
    assert "PageRequestManager" in _ASPNET_IDLE_JS
    assert "get_isInAsyncPostBack" in _ASPNET_IDLE_JS
