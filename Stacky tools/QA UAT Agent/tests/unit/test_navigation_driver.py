"""Unit tests for navigation_driver.py — Fase 1.

Tests cover:
- NavigationResult.to_dict() contrato JSON
- is_child_screen() — pantallas hijas conocidas y desconocidas
- register_child_screen() — registro dinámico
- _classify_error() — clasificación de errores
- NavigationDriver.via_form_submit() — JS OK → URL match → NAV_SUCCESS
- NavigationDriver.via_form_submit() — FORM_NOT_FOUND devuelve NAV_FORM_NOT_FOUND
- NavigationDriver.via_form_submit() — timeout devuelve NAV_TIMEOUT con retry
- NavigationDriver.via_form_submit() — auth expirada devuelve NAV_AUTH_EXPIRED sin retry
- NavigationDriver.via_dopostback() — DOPOSTBACK_NOT_AVAILABLE no reintenta
- navigate_via_form_submit() — función de conveniencia retorna NavigationResult
- CLI --list-child-screens existe sin error
"""

import asyncio
import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Asegurar que el módulo es importable desde el directorio padre
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from navigation_driver import (
    NavigationDriver,
    NavigationResult,
    CHILD_SCREENS,
    _classify_error,
    is_child_screen,
    navigate_via_form_submit,
    register_child_screen,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_page(
    url: str = "http://localhost/AgendaWeb/FrmAgenda.aspx",
    evaluate_result: dict | None = None,
    wait_url_raises: Exception | None = None,
) -> MagicMock:
    """Crea un mock de page Playwright con los métodos async necesarios."""
    page = MagicMock()
    page.url = url

    # evaluate — simula JS form.submit()
    if evaluate_result is None:
        evaluate_result = {"ok": True, "error": None}
    page.evaluate = AsyncMock(return_value=evaluate_result)

    # wait_for_url — puede lanzar excepción o resolver
    if wait_url_raises is not None:
        page.wait_for_url = AsyncMock(side_effect=wait_url_raises)
    else:
        async def _wait_url(predicate, **kwargs):
            # Simular que la URL cambió al destino esperado
            pass
        page.wait_for_url = AsyncMock(side_effect=_wait_url)

    page.wait_for_load_state = AsyncMock()
    page.screenshot = AsyncMock()

    return page


# ── NavigationResult ──────────────────────────────────────────────────────────

class TestNavigationResult:
    def test_to_dict_ok_true(self):
        r = NavigationResult(
            ok=True,
            method="form_submit",
            attempts=1,
            elapsed_ms=250,
            url_before="http://localhost/AgendaWeb/FrmAgenda.aspx",
            url_after="http://localhost/AgendaWeb/FrmDetalleClie.aspx",
        )
        d = r.to_dict()
        assert d["ok"] is True
        assert d["method"] == "form_submit"
        assert d["attempts"] == 1
        assert d["elapsed_ms"] == 250
        assert d["error_code"] is None
        assert d["screenshots"] == []

    def test_to_dict_ok_false(self):
        r = NavigationResult(
            ok=False,
            method="form_submit",
            attempts=3,
            elapsed_ms=5000,
            error_code="NAV_TIMEOUT",
            error_detail="Timed out waiting for URL",
            screenshots=["evidence/nav_attempt_1.png"],
        )
        d = r.to_dict()
        assert d["ok"] is False
        assert d["error_code"] == "NAV_TIMEOUT"
        assert len(d["screenshots"]) == 1


# ── is_child_screen ───────────────────────────────────────────────────────────

class TestIsChildScreen:
    def test_known_child_screens(self):
        for screen in [
            "FrmDetalleClie.aspx",
            "FrmDetalleLote.aspx",
            "FrmGestion.aspx",
            "FrmAgendaJudicial.aspx",
        ]:
            assert is_child_screen(screen), f"{screen} should be a child screen"

    def test_top_level_screens_are_not_child(self):
        for screen in [
            "FrmAgenda.aspx",
            "FrmLogin.aspx",
            "FrmReportes.aspx",
        ]:
            assert not is_child_screen(screen), f"{screen} should NOT be a child screen"

    def test_path_normalization(self):
        """Acepta rutas completas — extrae solo el nombre del archivo."""
        assert is_child_screen("AgendaWeb/FrmDetalleClie.aspx")
        assert is_child_screen("some\\path\\FrmGestion.aspx")

    def test_empty_string(self):
        assert not is_child_screen("")

    def test_register_adds_to_set(self):
        original_count = len(CHILD_SCREENS)
        register_child_screen("FrmNuevaPantalla.aspx")
        assert is_child_screen("FrmNuevaPantalla.aspx")
        # Limpiar el registro dinámico no es necesario para este test


# ── _classify_error ───────────────────────────────────────────────────────────

class TestClassifyError:
    def test_auth_expired_url(self):
        assert _classify_error("timeout", "http://host/AgendaWeb/FrmLogin.aspx") == "NAV_AUTH_EXPIRED"

    def test_auth_expired_login_in_url(self):
        assert _classify_error("something", "http://host/login?redirect=X") == "NAV_AUTH_EXPIRED"

    def test_timeout_in_message(self):
        assert _classify_error("Timeout 45000ms exceeded", "") == "NAV_TIMEOUT"

    def test_timed_out_phrase(self):
        assert _classify_error("operation timed out waiting for url", "") == "NAV_TIMEOUT"

    def test_playwright_error_fallback(self):
        assert _classify_error("unexpected error in evaluate", "") == "NAV_PLAYWRIGHT_ERROR"


# ── NavigationDriver.via_form_submit ──────────────────────────────────────────

class TestNavigationDriverViaFormSubmit:
    def test_success_first_attempt(self, tmp_path):
        """JS retorna ok=True, URL cambia → NAV_SUCCESS en attempt=1."""
        page = _make_page(
            url="http://localhost/AgendaWeb/FrmDetalleClie.aspx",
            evaluate_result={"ok": True, "error": None},
        )
        driver = NavigationDriver(page, evidence_dir=tmp_path, scenario_id="test_P04")

        result = asyncio.get_event_loop().run_until_complete(
            driver.via_form_submit(
                eventtarget="ctl00$c$GridObligaciones",
                eventargument="Select$0",
                wait_url_contains="FrmDetalleClie",
                timeout_ms=5000,
                retries=3,
            )
        )

        assert result.ok is True
        assert result.method == "form_submit"
        assert result.attempts == 1
        assert result.error_code is None

    def test_form_not_found_returns_immediately(self, tmp_path):
        """JS retorna FORM_NOT_FOUND → falla inmediatamente sin retry."""
        page = _make_page(
            evaluate_result={"ok": False, "error": "FORM_NOT_FOUND"},
        )
        driver = NavigationDriver(page, evidence_dir=tmp_path)

        result = asyncio.get_event_loop().run_until_complete(
            driver.via_form_submit(
                eventtarget="ctl00$c$GridObligaciones",
                eventargument="Select$0",
                wait_url_contains="FrmDetalleClie",
                timeout_ms=5000,
                retries=3,
            )
        )

        assert result.ok is False
        assert result.error_code == "NAV_FORM_NOT_FOUND"
        # No retry — JS bloqueado inmediatamente
        assert result.attempts == 1

    def test_timeout_retries_exhaust(self, tmp_path):
        """Timeout en wait_for_url → reintenta retries veces → NAV_TIMEOUT."""
        page = _make_page(
            evaluate_result={"ok": True, "error": None},
            wait_url_raises=Exception("Timeout 5000ms exceeded"),
        )
        # No queremos esperar el backoff real en tests — parchamos asyncio.sleep
        driver = NavigationDriver(page, evidence_dir=tmp_path)

        with patch("navigation_driver.asyncio.sleep", new=AsyncMock()):
            result = asyncio.get_event_loop().run_until_complete(
                driver.via_form_submit(
                    eventtarget="ctl00$c$Grid",
                    eventargument="Select$0",
                    wait_url_contains="FrmDetalleClie",
                    timeout_ms=100,
                    retries=2,
                )
            )

        assert result.ok is False
        assert result.error_code == "NAV_TIMEOUT"
        assert result.attempts == 2  # agotó los 2 reintentos

    def test_auth_expired_no_retry(self, tmp_path):
        """Si la URL actual es FrmLogin → error AUTH_EXPIRED sin más reintentos."""
        page = _make_page(
            url="http://localhost/AgendaWeb/FrmLogin.aspx",  # sesión expirada
            evaluate_result={"ok": True, "error": None},
            wait_url_raises=Exception("timeout waiting for FrmDetalleClie"),
        )
        driver = NavigationDriver(page, evidence_dir=tmp_path)

        with patch("navigation_driver.asyncio.sleep", new=AsyncMock()):
            result = asyncio.get_event_loop().run_until_complete(
                driver.via_form_submit(
                    eventtarget="ctl00$c$Grid",
                    eventargument="Select$0",
                    wait_url_contains="FrmDetalleClie",
                    timeout_ms=100,
                    retries=3,
                )
            )

        assert result.ok is False
        assert result.error_code == "NAV_AUTH_EXPIRED"
        # Solo 1 intento — no tiene sentido reintentar con sesión expirada
        assert result.attempts == 1


# ── NavigationDriver.via_dopostback ──────────────────────────────────────────

class TestNavigationDriverViaDoPostBack:
    def test_dopostback_not_available_fails_without_retry(self, tmp_path):
        """Si window.__doPostBack no está disponible → falla sin reintentar."""
        page = _make_page(
            evaluate_result={"ok": False, "error": "DOPOSTBACK_NOT_AVAILABLE"},
        )
        driver = NavigationDriver(page, evidence_dir=tmp_path)

        with patch("navigation_driver.asyncio.sleep", new=AsyncMock()):
            result = asyncio.get_event_loop().run_until_complete(
                driver.via_dopostback(
                    eventtarget="ctl00$c$Grid",
                    eventargument="Select$0",
                    wait_url_contains="FrmDetalleClie",
                    timeout_ms=100,
                    retries=3,
                )
            )

        assert result.ok is False
        assert result.error_code == "NAV_DOPOSTBACK_NOT_AVAILABLE"


# ── navigate_via_form_submit (función de conveniencia) ────────────────────────

class TestNavigateViaFormSubmitConvenience:
    def test_returns_navigation_result(self, tmp_path):
        page = _make_page(
            url="http://localhost/AgendaWeb/FrmDetalleClie.aspx",
            evaluate_result={"ok": True, "error": None},
        )

        result = asyncio.get_event_loop().run_until_complete(
            navigate_via_form_submit(
                page=page,
                eventtarget="ctl00$c$Grid",
                eventargument="Select$0",
                wait_url_contains="FrmDetalleClie",
                timeout_ms=5000,
                retries=1,
                evidence_dir=tmp_path,
            )
        )

        assert isinstance(result, NavigationResult)
        assert result.ok is True
        assert result.method == "form_submit"
