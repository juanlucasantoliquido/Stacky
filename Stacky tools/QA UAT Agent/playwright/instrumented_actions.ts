/**
 * playwright/instrumented_actions.ts — Wrappers de acciones Playwright con logging forense.
 *
 * Provee wrappers instrumentados para las acciones más comunes de Playwright.
 * Cada wrapper:
 *   1. Emite evento *.intent (antes de ejecutar).
 *   2. Ejecuta la acción real.
 *   3. Emite *.completed o *.failed.
 *   4. Nunca suprime excepciones (la acción falla igual si Playwright falla).
 *
 * Uso en specs generados:
 *   import { loggedGoto, loggedClick, loggedFill, ... } from '../../playwright/instrumented_actions';
 *
 * SEGURIDAD: loggedFill redacta el valor antes de loguearlo si el campo es sensitivo
 * (password, contraseña, pass, secret, token, etc.).
 *
 * Variables de entorno requeridas por forensic_logger.ts:
 *   QA_UAT_FORENSIC_RUN_DIR    — directorio del run (evidence/<ticket>/<run_id>)
 *   QA_UAT_FORENSIC_RUN_ID     — run_id canónico
 *   QA_UAT_FORENSIC_TICKET_ID  — ticket_id
 */

import { Page, Locator } from '@playwright/test';
import { logAction, logScreenshot, sha256File, fileSizeBytes } from './forensic_logger';

// ── Fill value redaction ───────────────────────────────────────────────────────

const SENSITIVE_FILL_PATTERNS = [
  /password|contraseña|contrasena|pass|pwd|secret|token|pat|apikey/i,
];

function _isSensitiveFill(selector: string, value: string): boolean {
  return SENSITIVE_FILL_PATTERNS.some(p => p.test(selector));
}

function _redactFillValue(selector: string, value: string): string {
  if (_isSensitiveFill(selector, value)) return '***REDACTED***';
  // Truncate long values (not redact, just limit)
  return value.slice(0, 200);
}

// ── Timestamp helpers ─────────────────────────────────────────────────────────

function _now(): string {
  return new Date().toISOString().replace(/(\.\d{3})\d*Z/, '$1Z');
}

function _durationMs(startedAt: string): number {
  return Date.now() - new Date(startedAt).getTime();
}

let _stepCounter = 0;
function _nextStepId(): string {
  return `step_${String(++_stepCounter).padStart(3, '0')}`;
}

// ── loggedGoto ────────────────────────────────────────────────────────────────

export async function loggedGoto(
  page: Page,
  url: string,
  options: Parameters<Page['goto']>[1],
  ctx: { scenario_id: string },
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();
  const urlBefore = page.url();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'goto',
    category: 'page_goto',
    url_before: urlBefore,
    started_at: startedAt,
    status: 'intent',
    payload: { url },
  });

  try {
    await page.goto(url, options);
    const urlAfter = page.url();
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'goto',
      category: 'page_goto',
      url_before: urlBefore,
      url_after: urlAfter,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { url, final_url: urlAfter },
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'goto',
      category: 'page_goto',
      url_before: urlBefore,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
    });
    throw err;
  }
}

// ── loggedClick ───────────────────────────────────────────────────────────────

export async function loggedClick(
  locator: Locator,
  selector: string,
  options: Parameters<Locator['click']>[0],
  ctx: { scenario_id: string; page: Page },
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();
  const urlBefore = ctx.page.url();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'click',
    category: 'page_click',
    selector,
    url_before: urlBefore,
    started_at: startedAt,
    status: 'intent',
    payload: { selector },
  });

  try {
    await locator.click(options);
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'click',
      category: 'page_click',
      selector,
      url_before: urlBefore,
      url_after: ctx.page.url(),
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'click',
      category: 'page_click',
      selector,
      url_before: urlBefore,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
    });
    throw err;
  }
}

// ── loggedFill ────────────────────────────────────────────────────────────────

export async function loggedFill(
  locator: Locator,
  selector: string,
  value: string,
  options: Parameters<Locator['fill']>[1],
  ctx: { scenario_id: string; page: Page },
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();
  const urlBefore = ctx.page.url();
  const isSensitive = _isSensitiveFill(selector, value);
  const loggedValue = _redactFillValue(selector, value);

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'fill',
    category: 'page_fill',
    selector,
    url_before: urlBefore,
    started_at: startedAt,
    status: 'intent',
    payload: { selector, value: loggedValue, redacted: isSensitive },
  });

  try {
    await locator.fill(value, options);
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'fill',
      category: 'page_fill',
      selector,
      url_before: urlBefore,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { selector, value: loggedValue, redacted: isSensitive },
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'fill',
      category: 'page_fill',
      selector,
      url_before: urlBefore,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
      payload: { selector, value: loggedValue, redacted: isSensitive },
    });
    throw err;
  }
}

// ── loggedSelect ──────────────────────────────────────────────────────────────

export async function loggedSelect(
  locator: Locator,
  selector: string,
  value: string | string[],
  ctx: { scenario_id: string; page: Page },
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();
  const urlBefore = ctx.page.url();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'select',
    category: 'page_select',
    selector,
    url_before: urlBefore,
    started_at: startedAt,
    status: 'intent',
    payload: { selector, value: Array.isArray(value) ? value : [value] },
  });

  try {
    await locator.selectOption(Array.isArray(value) ? value : value);
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'select',
      category: 'page_select',
      selector,
      url_before: urlBefore,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { selector, value: Array.isArray(value) ? value : [value] },
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'select',
      category: 'page_select',
      selector,
      url_before: urlBefore,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
    });
    throw err;
  }
}

// ── loggedWait ────────────────────────────────────────────────────────────────

export async function loggedWait(
  page: Page,
  waitType: string,
  ctx: { scenario_id: string },
  fn: () => Promise<void>,
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'wait',
    category: 'page_wait',
    started_at: startedAt,
    status: 'intent',
    payload: { wait_type: waitType },
  });

  try {
    await fn();
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'wait',
      category: 'page_wait',
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { wait_type: waitType },
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'wait',
      category: 'page_wait',
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
    });
    throw err;
  }
}

// ── loggedExpectVisible ───────────────────────────────────────────────────────

export async function loggedExpectVisible(
  locator: Locator,
  selector: string,
  ctx: { scenario_id: string; page: Page },
  options?: { timeout?: number },
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'assert_visible',
    category: 'page_assertion',
    selector,
    url_before: ctx.page.url(),
    started_at: startedAt,
    status: 'intent',
    payload: { assertion: 'toBeVisible', selector },
  });

  try {
    const { expect } = await import('@playwright/test');
    await expect(locator).toBeVisible(options);
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'assert_visible',
      category: 'page_assertion',
      selector,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { assertion: 'toBeVisible', selector, result: 'pass' },
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'assert_visible',
      category: 'page_assertion',
      selector,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
      payload: { assertion: 'toBeVisible', selector, result: 'fail' },
    });
    throw err;
  }
}

// ── loggedExpectText ──────────────────────────────────────────────────────────

export async function loggedExpectText(
  locator: Locator,
  selector: string,
  expectedText: string | RegExp,
  ctx: { scenario_id: string; page: Page },
  options?: { timeout?: number },
): Promise<void> {
  const stepId = _nextStepId();
  const startedAt = _now();
  const expectedStr = typeof expectedText === 'string' ? expectedText : expectedText.toString();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: stepId,
    action: 'assert_text',
    category: 'page_assertion',
    selector,
    url_before: ctx.page.url(),
    started_at: startedAt,
    status: 'intent',
    payload: { assertion: 'toContainText', selector, expected: expectedStr.slice(0, 200) },
  });

  try {
    const { expect } = await import('@playwright/test');
    await expect(locator).toContainText(expectedText, options);
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'assert_text',
      category: 'page_assertion',
      selector,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { assertion: 'toContainText', selector, expected: expectedStr.slice(0, 200), result: 'pass' },
    });
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: stepId,
      action: 'assert_text',
      category: 'page_assertion',
      selector,
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
      payload: { assertion: 'toContainText', selector, expected: expectedStr.slice(0, 200), result: 'fail' },
    });
    throw err;
  }
}

// ── loggedScreenshot ──────────────────────────────────────────────────────────

export async function loggedScreenshot(
  page: Page,
  destPath: string,
  ctx: { scenario_id: string },
  reason: 'scenario_start' | 'failure' | 'blocker' | 'step' | 'final' = 'step',
  stepId?: string,
): Promise<string> {
  const startedAt = _now();
  const sid = stepId ?? _nextStepId();

  logAction({
    scenario_id: ctx.scenario_id,
    step_id: sid,
    action: 'screenshot',
    category: 'page_screenshot',
    started_at: startedAt,
    status: 'intent',
    payload: { dest_path: destPath, reason },
  });

  try {
    await page.screenshot({ path: destPath, fullPage: false });
    const sha = sha256File(destPath);
    const size = fileSizeBytes(destPath);

    logAction({
      scenario_id: ctx.scenario_id,
      step_id: sid,
      action: 'screenshot',
      category: 'page_screenshot',
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'completed',
      payload: { dest_path: destPath, reason, sha256: sha, size_bytes: size },
    });

    logScreenshot({
      scenario_id: ctx.scenario_id,
      step_id: sid,
      path: destPath,
      reason,
      sha256: sha ?? undefined,
      size_bytes: size ?? undefined,
    });

    return destPath;
  } catch (err: any) {
    logAction({
      scenario_id: ctx.scenario_id,
      step_id: sid,
      action: 'screenshot',
      category: 'page_screenshot',
      started_at: startedAt,
      finished_at: _now(),
      duration_ms: _durationMs(startedAt),
      status: 'failed',
      error: String(err?.message ?? err).slice(0, 300),
    });
    throw err;
  }
}

// ── Browser event listeners setup ─────────────────────────────────────────────

/**
 * setupPageListeners — Registrar listeners forenses en la página.
 *
 * Llama a esta función en test.beforeEach para capturar:
 *   - Mensajes de consola del browser
 *   - Errores de página (uncaught exceptions)
 *   - Network requests y responses
 *
 * Los eventos se escriben directamente a los JSONL files.
 */
export function setupPageListeners(
  page: Page,
  ctx: { scenario_id: string },
  options: { captureNetwork?: boolean; captureConsole?: boolean } = {},
): void {
  const { captureNetwork = true, captureConsole = true } = options;

  if (captureConsole) {
    page.on('console', (msg) => {
      const { logConsole } = require('./forensic_logger');
      logConsole({
        scenario_id: ctx.scenario_id,
        console_type: msg.type(),
        text: msg.text().slice(0, 500),
        location: msg.location()?.url ?? undefined,
        is_error: msg.type() === 'error',
      });
    });

    page.on('pageerror', (err) => {
      const { logConsole } = require('./forensic_logger');
      logConsole({
        scenario_id: ctx.scenario_id,
        console_type: 'pageerror',
        text: err.message.slice(0, 500),
        is_error: true,
      });
    });
  }

  if (captureNetwork) {
    const requestTimes = new Map<string, number>();

    page.on('request', (request) => {
      const { logNetwork } = require('./forensic_logger');
      const reqId = request.url() + request.method() + Date.now();
      requestTimes.set(reqId, Date.now());
      logNetwork({
        scenario_id: ctx.scenario_id,
        method: request.method(),
        url: request.url(),
        resource_type: request.resourceType(),
        request_headers: request.headers() as Record<string, string>,
        event_kind: 'request',
      });
    });

    page.on('response', (response) => {
      const { logNetwork } = require('./forensic_logger');
      logNetwork({
        scenario_id: ctx.scenario_id,
        method: response.request().method(),
        url: response.url(),
        status: response.status(),
        resource_type: response.request().resourceType(),
        response_headers: response.headers() as Record<string, string>,
        event_kind: 'response',
      });
    });

    page.on('requestfailed', (request) => {
      const { logNetwork } = require('./forensic_logger');
      logNetwork({
        scenario_id: ctx.scenario_id,
        method: request.method(),
        url: request.url(),
        resource_type: request.resourceType(),
        failure: request.failure()?.errorText ?? 'unknown',
        event_kind: 'failure',
      });
    });
  }
}
