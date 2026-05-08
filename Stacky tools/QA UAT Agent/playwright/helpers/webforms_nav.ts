/**
 * playwright/helpers/webforms_nav.ts — Navegación robusta para pantallas hijas ASP.NET WebForms.
 *
 * PROBLEMA QUE RESUELVE
 * ----------------------
 * Las pantallas hijas de Agenda Web (FrmDetalleClie, FrmDetalleLote, FrmGestion, etc.)
 * se abren via postback de grilla — no tienen una URL directa navegable con goto().
 *
 * window.__doPostBack() es el mecanismo nativo de ASP.NET, pero ScriptManager lo
 * intercepta y puede rechazarlo en modo headless cuando el control no está en
 * asyncPostBackTriggers. Esto causa failures tipo BLOCKED_NAV.
 *
 * SOLUCIÓN: HTMLFormElement.prototype.submit.call(form)
 * -------------------------------------------------------
 * Bypasea ScriptManager completamente → siempre ejecuta un full page postback.
 * Funciona en headless y headful. Determinístico en todas las configuraciones.
 *
 * FUNCIONES EXPORTADAS
 * ---------------------
 *   navigateViaFormSubmit(page, eventTarget, eventArgument, waitUrlContains, opts?)
 *     → Mecanismo primario. Siempre usar para pantallas hijas.
 *
 *   navigateViaDoPostBack(page, eventTarget, eventArgument, waitUrlContains, opts?)
 *     → Fallback para casos UpdatePanel donde ScriptManager sí está activo.
 *
 *   isChildScreenNavResult(result) → type guard
 *
 * USO EN SPECS GENERADOS
 * -----------------------
 *   import { navigateViaFormSubmit } from '../../playwright/helpers/webforms_nav';
 *
 *   // Ejemplo: abrir FrmDetalleClie desde GridObligaciones fila 0
 *   const navResult = await navigateViaFormSubmit(
 *     page,
 *     'ctl00$c$GridObligaciones',
 *     'Select$0',
 *     'FrmDetalleClie',
 *     { timeoutMs: 45_000, maxAttempts: 3, screenshotDir: 'evidence/119/P04' }
 *   );
 *   if (!navResult.ok) {
 *     throw new Error(`[BLOCKED_NAV] ${navResult.errorCode}: ${navResult.errorDetail}`);
 *   }
 */

import * as fs from 'fs';
import * as path from 'path';

// ── Tipos ─────────────────────────────────────────────────────────────────────

export interface WebFormsNavOptions {
  /** Timeout por intento en ms (default: 45000) */
  timeoutMs?: number;
  /** Número máximo de intentos (default: 3) */
  maxAttempts?: number;
  /** Directorio donde guardar screenshots de intentos fallidos */
  screenshotDir?: string;
  /** Prefijo para los screenshots (default: "nav") */
  screenshotPrefix?: string;
}

export interface WebFormsNavResult {
  ok: boolean;
  method: 'form_submit' | 'dopostback';
  attempts: number;
  elapsedMs: number;
  errorCode: string | null;
  errorDetail: string | null;
  screenshots: string[];
  urlBefore: string;
  urlAfter: string;
}

// ── Constantes ────────────────────────────────────────────────────────────────

/** Backoff entre reintentos en ms */
const RETRY_BACKOFF_MS = [1_000, 2_000, 4_000, 8_000];

// ── Función principal: form.submit() ─────────────────────────────────────────

/**
 * Navega a una pantalla hija via HTMLFormElement.prototype.submit.call().
 *
 * Bypasea ScriptManager/UpdatePanel. Funciona siempre en headless.
 * Es el mecanismo PRIMARIO para pantallas hijas en Agenda Web.
 *
 * @param page            Instancia de Page de Playwright
 * @param eventTarget     Valor de __EVENTTARGET (ej: "ctl00$c$GridObligaciones")
 * @param eventArgument   Valor de __EVENTARGUMENT (ej: "Select$0")
 * @param waitUrlContains Fragmento de URL que debe aparecer tras la navegación
 * @param opts            Opciones opcionales (timeoutMs, maxAttempts, screenshotDir)
 */
export async function navigateViaFormSubmit(
  page: any,
  eventTarget: string,
  eventArgument: string,
  waitUrlContains: string,
  opts: WebFormsNavOptions = {},
): Promise<WebFormsNavResult> {
  const timeoutMs       = opts.timeoutMs       ?? 45_000;
  const maxAttempts     = opts.maxAttempts      ?? 3;
  const screenshotDir   = opts.screenshotDir    ?? 'evidence';
  const screenshotPrefix = opts.screenshotPrefix ?? 'nav';

  const urlBefore    = page.url() as string;
  const startedAt    = Date.now();
  const screenshots: string[] = [];

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      // ── FORM SUBMIT (bypass ScriptManager) ─────────────────────────────
      const jsResult: { ok: boolean; error: string | null } = await page.evaluate(
        ([et, ea]: [string, string]) => {
          const form = document.querySelector('form') as HTMLFormElement | null;
          if (!form) return { ok: false, error: 'FORM_NOT_FOUND' };

          // Setear __EVENTTARGET / __EVENTARGUMENT como ASP.NET espera
          let etEl = (form as any)['__EVENTTARGET'] as HTMLInputElement | null;
          let eaEl = (form as any)['__EVENTARGUMENT'] as HTMLInputElement | null;

          if (!etEl) {
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

          etEl.value = et;
          eaEl.value = ea;

          // Bypass directo — ScriptManager no puede interceptar esto
          HTMLFormElement.prototype.submit.call(form);
          return { ok: true, error: null };
        },
        [eventTarget, eventArgument] as [string, string],
      );

      if (!jsResult.ok) {
        const errorCode = _mapJsError(jsResult.error ?? 'UNKNOWN');
        // FORM_NOT_FOUND no tiene sentido reintentar
        if (jsResult.error === 'FORM_NOT_FOUND') {
          return _failResult('form_submit', attempt, startedAt, errorCode,
            'No <form> element found in DOM.', screenshots, urlBefore, page.url());
        }
        // Otro error JS — seguir con backoff
        const scr = await _screenshot(page, screenshotDir, `${screenshotPrefix}_form_attempt_${attempt}`);
        if (scr) screenshots.push(scr);
        await _sleep(RETRY_BACKOFF_MS[Math.min(attempt - 1, RETRY_BACKOFF_MS.length - 1)]);
        continue;
      }

      // ── ESPERAR URL DESTINO ────────────────────────────────────────────
      await page.waitForURL(
        (url: URL) => url.toString().toLowerCase().includes(waitUrlContains.toLowerCase()),
        { timeout: timeoutMs },
      );
      await page.waitForLoadState('load', { timeout: 15_000 });

      const urlAfter = page.url() as string;
      const authExpired = urlAfter.toLowerCase().includes('frmlogin');
      if (authExpired) {
        return _failResult('form_submit', attempt, startedAt, 'NAV_AUTH_EXPIRED',
          'Session expired — redirected to FrmLogin. Re-run global.setup.', screenshots, urlBefore, urlAfter);
      }

      return {
        ok: true,
        method: 'form_submit',
        attempts: attempt,
        elapsedMs: Date.now() - startedAt,
        errorCode: null,
        errorDetail: null,
        screenshots,
        urlBefore,
        urlAfter,
      };

    } catch (err: any) {
      const currentUrl = _safePageUrl(page);
      const errorCode  = _classifyError(err, currentUrl);

      const scr = await _screenshot(page, screenshotDir, `${screenshotPrefix}_form_attempt_${attempt}`);
      if (scr) screenshots.push(scr);

      // Auth expirada — no reintentar
      if (errorCode === 'NAV_AUTH_EXPIRED') {
        return _failResult('form_submit', attempt, startedAt, errorCode,
          'Session expired — redirected to FrmLogin. Re-run global.setup.',
          screenshots, urlBefore, currentUrl);
      }

      if (attempt === maxAttempts) {
        return _failResult('form_submit', attempt, startedAt, errorCode,
          String(err?.message ?? err).slice(0, 500), screenshots, urlBefore, currentUrl);
      }

      await _sleep(RETRY_BACKOFF_MS[Math.min(attempt - 1, RETRY_BACKOFF_MS.length - 1)]);
    }
  }

  // Fallback defensivo — no debería llegar aquí
  return _failResult('form_submit', maxAttempts, startedAt, 'NAV_TIMEOUT',
    'All attempts exhausted.', screenshots, urlBefore, _safePageUrl(page));
}

// ── Función secundaria: __doPostBack() ────────────────────────────────────────

/**
 * Navega via window.__doPostBack() — fallback para controles en UpdatePanel.
 *
 * ADVERTENCIA: puede ser bloqueado por ScriptManager en algunas configuraciones.
 * Preferir navigateViaFormSubmit() salvo que el control use UpdatePanel explícitamente.
 */
export async function navigateViaDoPostBack(
  page: any,
  eventTarget: string,
  eventArgument: string,
  waitUrlContains: string,
  opts: WebFormsNavOptions = {},
): Promise<WebFormsNavResult> {
  const timeoutMs       = opts.timeoutMs       ?? 45_000;
  const maxAttempts     = opts.maxAttempts      ?? 3;
  const screenshotDir   = opts.screenshotDir    ?? 'evidence';
  const screenshotPrefix = opts.screenshotPrefix ?? 'nav_dpb';

  const urlBefore = page.url() as string;
  const startedAt = Date.now();
  const screenshots: string[] = [];

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const jsResult: { ok: boolean; error: string | null } = await page.evaluate(
        ([et, ea]: [string, string]) => {
          if (typeof (window as any).__doPostBack !== 'function') {
            return { ok: false, error: 'DOPOSTBACK_NOT_AVAILABLE' };
          }
          try {
            (window as any).__doPostBack(et, ea);
            return { ok: true, error: null };
          } catch (e: any) {
            return { ok: false, error: 'DOPOSTBACK_EXCEPTION: ' + String(e) };
          }
        },
        [eventTarget, eventArgument] as [string, string],
      );

      if (!jsResult.ok) {
        const scr = await _screenshot(page, screenshotDir, `${screenshotPrefix}_attempt_${attempt}`);
        if (scr) screenshots.push(scr);
        if (jsResult.error?.includes('NOT_AVAILABLE') || attempt === maxAttempts) {
          return _failResult('dopostback', attempt, startedAt,
            _mapJsError(jsResult.error ?? 'UNKNOWN'),
            jsResult.error ?? 'Unknown JS error', screenshots, urlBefore, _safePageUrl(page));
        }
        await _sleep(RETRY_BACKOFF_MS[Math.min(attempt - 1, RETRY_BACKOFF_MS.length - 1)]);
        continue;
      }

      await page.waitForURL(
        (url: URL) => url.toString().toLowerCase().includes(waitUrlContains.toLowerCase()),
        { timeout: timeoutMs },
      );
      await page.waitForLoadState('load', { timeout: 15_000 });

      const urlAfter = page.url() as string;
      if (urlAfter.toLowerCase().includes('frmlogin')) {
        return _failResult('dopostback', attempt, startedAt, 'NAV_AUTH_EXPIRED',
          'Session expired.', screenshots, urlBefore, urlAfter);
      }

      return {
        ok: true, method: 'dopostback', attempts: attempt,
        elapsedMs: Date.now() - startedAt, errorCode: null, errorDetail: null,
        screenshots, urlBefore, urlAfter,
      };

    } catch (err: any) {
      const currentUrl = _safePageUrl(page);
      const errorCode  = _classifyError(err, currentUrl);
      const scr = await _screenshot(page, screenshotDir, `${screenshotPrefix}_attempt_${attempt}`);
      if (scr) screenshots.push(scr);
      if (errorCode === 'NAV_AUTH_EXPIRED' || attempt === maxAttempts) {
        return _failResult('dopostback', attempt, startedAt, errorCode,
          String(err?.message ?? err).slice(0, 500), screenshots, urlBefore, currentUrl);
      }
      await _sleep(RETRY_BACKOFF_MS[Math.min(attempt - 1, RETRY_BACKOFF_MS.length - 1)]);
    }
  }

  return _failResult('dopostback', maxAttempts, startedAt, 'NAV_TIMEOUT',
    'All attempts exhausted.', screenshots, urlBefore, _safePageUrl(page));
}

// ── Type guard ────────────────────────────────────────────────────────────────

export function isWebFormsNavResult(v: unknown): v is WebFormsNavResult {
  return (
    typeof v === 'object' && v !== null &&
    'ok' in v && 'method' in v && 'attempts' in v
  );
}

// ── Helpers internos ──────────────────────────────────────────────────────────

function _failResult(
  method: 'form_submit' | 'dopostback',
  attempts: number,
  startedAt: number,
  errorCode: string,
  errorDetail: string,
  screenshots: string[],
  urlBefore: string,
  urlAfter: string,
): WebFormsNavResult {
  return {
    ok: false, method, attempts,
    elapsedMs: Date.now() - startedAt,
    errorCode, errorDetail, screenshots, urlBefore, urlAfter,
  };
}

function _classifyError(err: any, currentUrl: string): string {
  const msg = String(err?.message ?? err).toLowerCase();
  const url = currentUrl.toLowerCase();
  if (url.includes('frmlogin') || url.includes('login')) return 'NAV_AUTH_EXPIRED';
  if (msg.includes('timeout') || msg.includes('timed out'))  return 'NAV_TIMEOUT';
  if (msg.includes('form_not_found'))                        return 'NAV_FORM_NOT_FOUND';
  return 'NAV_PLAYWRIGHT_ERROR';
}

function _mapJsError(jsError: string): string {
  if (jsError === 'FORM_NOT_FOUND')           return 'NAV_FORM_NOT_FOUND';
  if (jsError.includes('NOT_AVAILABLE'))      return 'NAV_DOPOSTBACK_NOT_AVAILABLE';
  if (jsError.includes('DOPOSTBACK_EXCEPTION')) return 'NAV_DOPOSTBACK_EXCEPTION';
  return 'NAV_JS_ERROR';
}

function _safePageUrl(page: any): string {
  try { return String(page.url()); } catch { return ''; }
}

async function _screenshot(page: any, dir: string, name: string): Promise<string | null> {
  try {
    fs.mkdirSync(dir, { recursive: true });
    const filePath = path.join(dir, `${name}.png`);
    await page.screenshot({ path: filePath });
    return filePath;
  } catch {
    return null;
  }
}

async function _sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
