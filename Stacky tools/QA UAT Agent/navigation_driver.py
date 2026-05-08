"""
navigation_driver.py — Mecanismos robustos de navegación WebForms para QA UAT Agent.

PROBLEMA RESUELTO
-----------------
ASP.NET WebForms expone tres mecanismos de postback para navegar a pantallas
hijas (FrmDetalleClie, FrmGestion, FrmDetalleLote, FrmAgendaJudicial, etc.):

  1. window.__doPostBack(target, argument)
       → Gestionado por ScriptManager/PageRequestManager.
       → BLOQUEADO cuando el control no está en asyncPostBackTriggers.
       → Causa BLOCKED flaky, especialmente en modo headless.

  2. HTMLFormElement.prototype.submit.call(form)
       → Bypass directo de ScriptManager.
       → Siempre funciona — full page postback.
       → MECANISMO PRIMARIO de este módulo.

  3. page.locator(selector).click()
       → Para navegación via <a> o botones simples.
       → MECANISMO AUXILIAR para links directos.

ESTRATEGIA DE RETRY
-------------------
Cada función ejecuta hasta `retries` intentos con backoff exponencial:
  intento 1 → espera 1s
  intento 2 → espera 2s
  intento 3 → espera 4s

Cada intento fallido captura un screenshot con nombre descriptivo para
evidencia forense. El error_code distingue el tipo de falla:

  NAV_SUCCESS           — navegación exitosa
  NAV_TIMEOUT           — URL esperada no apareció dentro de timeout_ms
  NAV_AUTH_EXPIRED      — redirigido a FrmLogin (sesión expirada)
  NAV_FORM_NOT_FOUND    — no se encontró el formulario ASP.NET en el DOM
  NAV_PLAYWRIGHT_ERROR  — excepción inesperada de Playwright

USO EN SCRIPTS PYTHON
---------------------
    from navigation_driver import NavigationDriver, NavigationResult

    driver = NavigationDriver(page, evidence_dir=Path("evidence/119"))

    result = await driver.via_form_submit(
        eventtarget="ctl00$c$GridObligaciones",
        eventargument="Select$0",
        wait_url_contains="FrmDetalleClie",
        timeout_ms=45_000,
        retries=3,
        screenshot_prefix="P04",
    )
    if not result.ok:
        raise AssertionError(f"Navigation blocked: {result.error_code} ({result.attempts} attempts)")

USO EN SPECS GENERADOS
----------------------
El TypeScript helper en playwright/helpers/webforms_nav.ts expone
navigateViaFormSubmit() con el mismo contrato.

La acción 'navigate_webforms' en el template genera código que usa ese helper.

CONTRATO DE RETORNO (NavigationResult)
---------------------------------------
    {
      "ok": bool,
      "method": "form_submit" | "dopostback" | "link_click",
      "attempts": int,
      "elapsed_ms": int,
      "error_code": str | None,      # None si ok=True
      "screenshots": list[str],      # rutas de screenshots de intentos fallidos
      "url_before": str,
      "url_after": str,
    }

VARIABLES DE ENTORNO
--------------------
  QA_NAV_STRATEGY     — "form_submit" (default) | "dopostback" | "link_click"
  QA_NAV_RETRIES      — cantidad de reintentos (default: 3)
  QA_NAV_TIMEOUT_MS   — timeout por intento en ms (default: 45000)
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.navigation_driver")

_TOOL_VERSION = "1.0.0"

# ── Defaults (overridable via env vars) ───────────────────────────────────────
_DEFAULT_STRATEGY   = os.environ.get("QA_NAV_STRATEGY", "form_submit")
_DEFAULT_RETRIES    = int(os.environ.get("QA_NAV_RETRIES", "3"))
_DEFAULT_TIMEOUT_MS = int(os.environ.get("QA_NAV_TIMEOUT_MS", "45000"))

# Backoff delays por intento (segundos)
_RETRY_BACKOFF_S = [1, 2, 4, 8]

# Pantallas hijas conocidas que requieren form.submit() en vez de goto()
# Cualquier pantalla que no esté en este set puede usar goto() directo.
# Extender esta lista cuando se descubran nuevas pantallas hijas.
CHILD_SCREENS: frozenset[str] = frozenset({
    "FrmDetalleClie.aspx",
    "FrmDetalleLote.aspx",
    "FrmGestion.aspx",
    "FrmAgendaJudicial.aspx",
    "FrmJDemanda.aspx",
    "FrmJConvenio.aspx",
    "FrmJEmbargo.aspx",
    "FrmDetalleLiquidacion.aspx",
    "FrmAvanzarFlow.aspx",
    "FrmIframeWorkflow.aspx",
    "WorkflowFrame.aspx",
})


# ── Tipos de resultado ────────────────────────────────────────────────────────

@dataclass
class NavigationResult:
    """Resultado de una operación de navegación WebForms."""
    ok: bool
    method: str                          # "form_submit" | "dopostback" | "link_click"
    attempts: int                        # cantidad de intentos realizados
    elapsed_ms: int                      # tiempo total en ms
    error_code: Optional[str] = None     # None si ok=True
    error_detail: Optional[str] = None   # mensaje detallado del error
    screenshots: list = field(default_factory=list)  # rutas de screenshots de fallas
    url_before: str = ""
    url_after: str = ""

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "method": self.method,
            "attempts": self.attempts,
            "elapsed_ms": self.elapsed_ms,
            "error_code": self.error_code,
            "error_detail": self.error_detail,
            "screenshots": self.screenshots,
            "url_before": self.url_before,
            "url_after": self.url_after,
        }


# ── JavaScript de navegación (inline en evaluate) ────────────────────────────

# JS que ejecuta el form.submit() directo, bypaseando ScriptManager.
# Funciona en cualquier página ASP.NET WebForms con un <form> estándar.
_JS_FORM_SUBMIT = """
(function(eventtarget, eventargument) {
    var form = document.querySelector('form');
    if (!form) return { ok: false, error: 'FORM_NOT_FOUND' };

    // Setear __EVENTTARGET y __EVENTARGUMENT como ASP.NET espera
    var etEl = form['__EVENTTARGET'];
    var eaEl = form['__EVENTARGUMENT'];

    if (!etEl) {
        // Algunos forms no tienen estos hidden fields si no los necesitan.
        // Crearlos on-the-fly para el submit.
        etEl = document.createElement('input');
        etEl.type = 'hidden';
        etEl.name = '__EVENTTARGET';
        form.appendChild(etEl);
    }
    if (!eaEl) {
        eaEl = document.createElement('input');
        eaEl.type = 'hidden';
        eaEl.name = '__EVENTARGUMENT';
        form.appendChild(eaEl);
    }

    etEl.value = eventtarget;
    eaEl.value = eventargument;

    // Usar el prototype directamente para bypassear cualquier override del ScriptManager
    HTMLFormElement.prototype.submit.call(form);
    return { ok: true, error: null };
})
"""

# JS que intenta __doPostBack (fallback — puede ser bloqueado por ScriptManager)
_JS_DOPOSTBACK = """
(function(eventtarget, eventargument) {
    if (typeof window.__doPostBack !== 'function') {
        return { ok: false, error: 'DOPOSTBACK_NOT_AVAILABLE' };
    }
    try {
        window.__doPostBack(eventtarget, eventargument);
        return { ok: true, error: null };
    } catch(e) {
        return { ok: false, error: 'DOPOSTBACK_EXCEPTION', detail: String(e) };
    }
})
"""


# ── NavigationDriver ──────────────────────────────────────────────────────────

class NavigationDriver:
    """
    Driver de navegación WebForms para QA UAT.

    Encapsula los tres mecanismos de navegación con retry y evidencia forense.
    Requiere una instancia de page de Playwright (async).

    Uso:
        driver = NavigationDriver(page, evidence_dir=Path("evidence/119"))
        result = await driver.via_form_submit("ctl00$c$GridObligaciones", "Select$0", "FrmDetalleClie")
    """

    def __init__(
        self,
        page: object,
        evidence_dir: Optional[Path] = None,
        scenario_id: str = "nav",
    ) -> None:
        self.page = page
        self.evidence_dir = evidence_dir or Path("evidence")
        self.scenario_id = scenario_id

    async def via_form_submit(
        self,
        eventtarget: str,
        eventargument: str,
        wait_url_contains: str,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        retries: int = _DEFAULT_RETRIES,
        screenshot_prefix: str = "nav",
    ) -> NavigationResult:
        """
        Navega via HTMLFormElement.prototype.submit.call() — mecanismo primario.

        Bypasea ScriptManager. Funciona en headless y headful.
        Realiza hasta `retries` intentos con backoff exponencial.
        """
        return await self._execute_nav(
            method="form_submit",
            js_trigger=_JS_FORM_SUBMIT,
            eventtarget=eventtarget,
            eventargument=eventargument,
            wait_url_contains=wait_url_contains,
            timeout_ms=timeout_ms,
            retries=retries,
            screenshot_prefix=screenshot_prefix,
        )

    async def via_dopostback(
        self,
        eventtarget: str,
        eventargument: str,
        wait_url_contains: str,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        retries: int = _DEFAULT_RETRIES,
        screenshot_prefix: str = "nav",
    ) -> NavigationResult:
        """
        Navega via window.__doPostBack() — fallback, puede ser bloqueado por ScriptManager.

        Usar solo cuando form_submit no está disponible o cuando el target
        está en asyncPostBackTriggers (UpdatePanel).
        """
        return await self._execute_nav(
            method="dopostback",
            js_trigger=_JS_DOPOSTBACK,
            eventtarget=eventtarget,
            eventargument=eventargument,
            wait_url_contains=wait_url_contains,
            timeout_ms=timeout_ms,
            retries=retries,
            screenshot_prefix=screenshot_prefix,
        )

    async def via_link_click(
        self,
        selector: str,
        wait_url_contains: str,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
        retries: int = _DEFAULT_RETRIES,
        screenshot_prefix: str = "nav",
    ) -> NavigationResult:
        """
        Navega haciendo click en un <a> o botón.
        Para navegaciones simples que no requieren postback.
        """
        started = time.time()
        url_before = str(self.page.url) if hasattr(self.page, 'url') else ""
        screenshots: list[str] = []

        for attempt in range(1, retries + 1):
            try:
                locator = self.page.locator(selector)
                await locator.scroll_into_view_if_needed()
                await locator.click()
                await self.page.wait_for_url(
                    lambda u, _wuc=wait_url_contains: _wuc.lower() in u.lower(),
                    timeout=timeout_ms,
                )
                await self.page.wait_for_load_state("load", timeout=15_000)
                url_after = str(self.page.url) if hasattr(self.page, 'url') else ""
                return NavigationResult(
                    ok=True,
                    method="link_click",
                    attempts=attempt,
                    elapsed_ms=int((time.time() - started) * 1000),
                    url_before=url_before,
                    url_after=url_after,
                )
            except Exception as exc:
                scr = await self._screenshot(f"{screenshot_prefix}_link_attempt_{attempt}")
                if scr:
                    screenshots.append(scr)
                error_code = _classify_error(str(exc), await self._current_url())
                if error_code == "NAV_AUTH_EXPIRED" or attempt == retries:
                    return NavigationResult(
                        ok=False,
                        method="link_click",
                        attempts=attempt,
                        elapsed_ms=int((time.time() - started) * 1000),
                        error_code=error_code,
                        error_detail=str(exc)[:500],
                        screenshots=screenshots,
                        url_before=url_before,
                        url_after=await self._current_url(),
                    )
                await asyncio.sleep(_RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)])

        return NavigationResult(
            ok=False, method="link_click", attempts=retries,
            elapsed_ms=int((time.time() - started) * 1000),
            error_code="NAV_TIMEOUT", screenshots=screenshots,
        )

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _execute_nav(
        self,
        method: str,
        js_trigger: str,
        eventtarget: str,
        eventargument: str,
        wait_url_contains: str,
        timeout_ms: int,
        retries: int,
        screenshot_prefix: str,
    ) -> NavigationResult:
        started = time.time()
        url_before = await self._current_url()
        screenshots: list[str] = []

        for attempt in range(1, retries + 1):
            logger.debug(
                "navigation_driver: %s attempt %d/%d — target=%s arg=%s wait=%s",
                method, attempt, retries, eventtarget, eventargument, wait_url_contains,
            )
            try:
                # Ejecutar el JS de navegación
                js_result = await self.page.evaluate(
                    f"{js_trigger}(arguments[0], arguments[1])",
                    [eventtarget, eventargument],
                )
                if isinstance(js_result, dict) and not js_result.get("ok"):
                    error = js_result.get("error", "JS_UNKNOWN_ERROR")
                    logger.warning("navigation_driver: JS returned error=%s", error)
                    if error == "FORM_NOT_FOUND":
                        return NavigationResult(
                            ok=False, method=method, attempts=attempt,
                            elapsed_ms=int((time.time() - started) * 1000),
                            error_code="NAV_FORM_NOT_FOUND",
                            error_detail=f"No <form> element found in DOM on attempt {attempt}",
                            screenshots=screenshots,
                            url_before=url_before,
                            url_after=await self._current_url(),
                        )
                    # Otro error JS (ej: DOPOSTBACK_NOT_AVAILABLE) — screenshot + retry
                    scr = await self._screenshot(
                        f"{screenshot_prefix}_{method}_js_fail_{attempt}"
                    )
                    if scr:
                        screenshots.append(scr)
                    if attempt == retries or "NOT_AVAILABLE" in error:
                        _ec = "NAV_DOPOSTBACK_NOT_AVAILABLE" if "NOT_AVAILABLE" in error else "NAV_JS_ERROR"
                        return NavigationResult(
                            ok=False, method=method, attempts=attempt,
                            elapsed_ms=int((time.time() - started) * 1000),
                            error_code=_ec,
                            error_detail=f"JS returned error={error}",
                            screenshots=screenshots,
                            url_before=url_before,
                            url_after=await self._current_url(),
                        )
                    delay = _RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)]
                    await asyncio.sleep(delay)
                    continue

                # Esperar a que la URL cambie al destino esperado
                await self.page.wait_for_url(
                    lambda u, _wuc=wait_url_contains: _wuc.lower() in u.lower(),
                    timeout=timeout_ms,
                )
                await self.page.wait_for_load_state("load", timeout=15_000)

                url_after = await self._current_url()
                logger.info(
                    "navigation_driver: %s OK (attempt %d) → %s",
                    method, attempt, url_after,
                )
                return NavigationResult(
                    ok=True,
                    method=method,
                    attempts=attempt,
                    elapsed_ms=int((time.time() - started) * 1000),
                    url_before=url_before,
                    url_after=url_after,
                )

            except Exception as exc:
                current_url = await self._current_url()
                error_code = _classify_error(str(exc), current_url)
                scr = await self._screenshot(
                    f"{screenshot_prefix}_{method}_attempt_{attempt}"
                )
                if scr:
                    screenshots.append(scr)

                logger.warning(
                    "navigation_driver: %s attempt %d failed — %s: %s",
                    method, attempt, error_code, str(exc)[:200],
                )

                # Auth expirada — no reintentar, es un error de entorno
                if error_code == "NAV_AUTH_EXPIRED":
                    return NavigationResult(
                        ok=False,
                        method=method,
                        attempts=attempt,
                        elapsed_ms=int((time.time() - started) * 1000),
                        error_code="NAV_AUTH_EXPIRED",
                        error_detail="Session expired — redirected to FrmLogin. Re-run global.setup.",
                        screenshots=screenshots,
                        url_before=url_before,
                        url_after=current_url,
                    )

                if attempt == retries:
                    return NavigationResult(
                        ok=False,
                        method=method,
                        attempts=attempt,
                        elapsed_ms=int((time.time() - started) * 1000),
                        error_code=error_code,
                        error_detail=str(exc)[:500],
                        screenshots=screenshots,
                        url_before=url_before,
                        url_after=current_url,
                    )

                # Backoff antes del próximo intento
                delay = _RETRY_BACKOFF_S[min(attempt - 1, len(_RETRY_BACKOFF_S) - 1)]
                logger.debug("navigation_driver: retry in %ds", delay)
                await asyncio.sleep(delay)

        # No debería llegar aquí
        return NavigationResult(
            ok=False, method=method, attempts=retries,
            elapsed_ms=int((time.time() - started) * 1000),
            error_code="NAV_TIMEOUT", screenshots=screenshots,
        )

    async def _current_url(self) -> str:
        try:
            return str(self.page.url) if hasattr(self.page, "url") else ""
        except Exception:
            return ""

    async def _screenshot(self, name: str) -> Optional[str]:
        """Captura screenshot de falla. Retorna ruta o None si falla."""
        try:
            self.evidence_dir.mkdir(parents=True, exist_ok=True)
            path = self.evidence_dir / f"{name}.png"
            await self.page.screenshot(path=str(path))
            return str(path)
        except Exception as exc:
            logger.debug("navigation_driver: screenshot failed: %s", exc)
            return None


# ── Clasificador de errores ───────────────────────────────────────────────────

def _classify_error(exc_str: str, current_url: str) -> str:
    """Clasifica el tipo de error de navegación a partir del mensaje de excepción."""
    exc_lower = exc_str.lower()
    url_lower = current_url.lower()

    if "frmlogin" in url_lower or "login" in url_lower:
        return "NAV_AUTH_EXPIRED"
    if "timeout" in exc_lower or "timed out" in exc_lower:
        return "NAV_TIMEOUT"
    if "form_not_found" in exc_lower or "cannot read" in exc_lower:
        return "NAV_FORM_NOT_FOUND"
    return "NAV_PLAYWRIGHT_ERROR"


# ── Función utilitaria para scripts one-shot ──────────────────────────────────

async def navigate_via_form_submit(
    page: object,
    eventtarget: str,
    eventargument: str,
    wait_url_contains: str,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    retries: int = _DEFAULT_RETRIES,
    evidence_dir: Optional[Path] = None,
    screenshot_prefix: str = "nav",
) -> NavigationResult:
    """
    Función de conveniencia para usar sin instanciar NavigationDriver.

    Equivalente a NavigationDriver(page).via_form_submit(...).

    Esta función es la que deben usar los scripts one-shot generados
    por UserInterfaceQA2.0 en vez de inline evaluate() con form.submit.
    """
    driver = NavigationDriver(
        page=page,
        evidence_dir=evidence_dir or Path("evidence"),
        scenario_id=screenshot_prefix,
    )
    return await driver.via_form_submit(
        eventtarget=eventtarget,
        eventargument=eventargument,
        wait_url_contains=wait_url_contains,
        timeout_ms=timeout_ms,
        retries=retries,
        screenshot_prefix=screenshot_prefix,
    )


# ── Utilidad: ¿pantalla hija? ─────────────────────────────────────────────────

def is_child_screen(screen_name: str) -> bool:
    """
    Retorna True si la pantalla requiere navegación via form.submit()
    en vez de page.goto().

    Usado por playwright_test_generator.py para decidir qué acción
    de navegación generar en el .spec.ts.
    """
    # Normalizar: aceptar con o sin ruta
    name = screen_name.split("/")[-1].split("\\")[-1]
    return name in CHILD_SCREENS


def register_child_screen(screen_name: str) -> None:
    """
    Registra una nueva pantalla hija en tiempo de ejecución.

    Para uso desde el learning_store cuando un nuevo caso demuestra
    que una pantalla requiere form.submit().
    """
    global CHILD_SCREENS
    CHILD_SCREENS = CHILD_SCREENS | frozenset({screen_name})
    logger.info("navigation_driver: registered new child screen: %s", screen_name)


# ── CLI para diagnóstico ──────────────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    import argparse
    import asyncio as _asyncio

    parser = argparse.ArgumentParser(
        description="navigation_driver — diagnóstico de navegación WebForms"
    )
    parser.add_argument("--list-child-screens", action="store_true",
                        help="Listar pantallas hijas conocidas")
    parser.add_argument("--is-child", metavar="SCREEN",
                        help="Verificar si una pantalla es hija")
    args = parser.parse_args()

    if args.list_child_screens:
        print("Pantallas hijas conocidas (requieren form.submit):")
        for s in sorted(CHILD_SCREENS):
            print(f"  - {s}")
    elif args.is_child:
        result = is_child_screen(args.is_child)
        print(f"{args.is_child}: {'CHILD (form.submit)' if result else 'DIRECT (goto)'}")
    else:
        parser.print_help()
