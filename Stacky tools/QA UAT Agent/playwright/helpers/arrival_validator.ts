/**
 * playwright/helpers/arrival_validator.ts — Sprint N5-03.
 *
 * Typed assertion checks executed after a navigation step (or batch of steps)
 * to verify the target screen was actually reached and is in a healthy state.
 *
 * WHY THIS EXISTS
 * ---------------
 * Before this helper, the spec relied on `page.url().includes(...)` to confirm
 * arrival. That post-hoc check misses three failure modes that look identical
 * to "wrong URL":
 *
 *   1. ASP.NET YSOD (Yellow Screen of Death) — the URL may still contain the
 *      target screen, but the body is an exception page.
 *   2. Silent session expiry — the URL flips to FrmLogin.aspx, but only briefly
 *      before the next step navigates away again.
 *   3. HTTP 5xx response — the page renders an error layout, not the screen.
 *
 * ArrivalValidator turns those into deterministic, classified failures with
 * an explicit category (NAV / ENV / DATA / APP).
 *
 * INTEGRATION
 * -----------
 *   import { ArrivalValidator, AssertionSpec } from './arrival_validator';
 *
 *   const result = await ArrivalValidator.validateAll(page, plan.arrival_assertions, {
 *     screenshotOnFail: 'evidence/120/P02/arrival_failed.png',
 *   });
 *   if (!result.ok) { throw new Error(...); }
 */

import * as fs from 'fs';
import * as path from 'path';

// ── Types ───────────────────────────────────────────────────────────────────

export type AssertionType =
  | 'url_contains'
  | 'url_not_contains'
  | 'dom_visible'
  | 'dom_not_visible'
  | 'dom_text_contains'
  | 'page_title_contains'
  | 'page_title_not_contains'
  | 'no_aspnet_error'
  | 'no_login_redirect'
  | 'no_500_response';

export type AssertionSeverity = 'hard' | 'soft';
export type AssertionCategory = 'NAV' | 'ENV' | 'DATA' | 'APP';

export interface AssertionSpec {
  assertion_id: string;
  type: AssertionType;
  description?: string;
  selector?: string | null;
  expected_value?: string | null;
  timeout_ms?: number;
  severity?: AssertionSeverity;
  category_on_fail?: AssertionCategory;
}

export interface AssertionError {
  assertion_id: string;
  type: AssertionType;
  actual: string;
  expected: string;
  category: AssertionCategory;
  severity: AssertionSeverity;
  detail?: string;
}

export interface ArrivalValidationResult {
  ok: boolean;
  passed: string[];
  failed: string[];
  errors: AssertionError[];
  diagnostics: ArrivalDiagnostics;
  elapsedMs: number;
  evaluatedAt: string;
  screenshotPath?: string | null;
}

export interface ArrivalDiagnostics {
  currentUrl: string;
  pageTitle: string;
  aspnetErrorDetected: boolean;
  loginRedirectDetected: boolean;
  httpStatus: number | null;
}

export interface ArrivalValidatorOptions {
  /** When set, a screenshot is captured on the FIRST hard failure. */
  screenshotOnFail?: string;
  /** Override for default timeout per assertion (ms). */
  defaultTimeoutMs?: number;
  /** Optional status captured by a response listener immediately after nav. */
  responseStatus?: number | null;
}

// ── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_TIMEOUT_MS = 10_000;

/** ASP.NET YSOD / custom-error markers — pattern set §4.3 of roadmap. */
const ASPNET_TITLE_MARKERS = [
  'Runtime Error',
  "Server Error in '/' Application",
  'Application Error',
  'Server Error',
];

const ASPNET_URL_MARKERS = ['Errors.aspx', 'Error.aspx'];

const ASPNET_DOM_MARKERS = [
  "h1:has-text('Server Error')",
  "#ctl00_c_lblError",
  ".errorContainer",
];

// ── Class ───────────────────────────────────────────────────────────────────

export class ArrivalValidator {
  /**
   * Evaluate every assertion in order; collect passes and failures.
   *
   * Hard-severity failures mark the overall result `ok=false`. Soft failures
   * are recorded in `failed` + `errors` but do not flip `ok`. Callers decide
   * whether to throw — by convention the runtime does throw on hard failures
   * inside `executeNavigationPlan`.
   */
  static async validateAll(
    page: any,
    assertions: AssertionSpec[] | null | undefined,
    options: ArrivalValidatorOptions = {},
  ): Promise<ArrivalValidationResult> {
    const started = Date.now();
    const list = Array.isArray(assertions) ? assertions : [];
    const passed: string[] = [];
    const failed: string[] = [];
    const errors: AssertionError[] = [];
    let screenshotPath: string | null | undefined = undefined;
    const diagnostics: ArrivalDiagnostics = {
      currentUrl: safePageUrl(page),
      pageTitle: await safePageTitle(page),
      aspnetErrorDetected: false,
      loginRedirectDetected: false,
      httpStatus: options.responseStatus ?? null,
    };

    for (const spec of list) {
      const severity: AssertionSeverity = spec.severity ?? 'hard';
      const category: AssertionCategory = spec.category_on_fail ?? 'NAV';
      const timeoutMs = spec.timeout_ms ?? options.defaultTimeoutMs ?? DEFAULT_TIMEOUT_MS;
      let ok = false;
      let actual = '';
      let detail = '';

      try {
        switch (spec.type) {
          case 'url_contains': {
            const cur = page.url();
            actual = cur;
            ok = !!spec.expected_value && cur.toLowerCase().includes(String(spec.expected_value).toLowerCase());
            break;
          }
          case 'url_not_contains': {
            const cur = page.url();
            actual = cur;
            ok = !spec.expected_value || !cur.toLowerCase().includes(String(spec.expected_value).toLowerCase());
            break;
          }
          case 'dom_visible': {
            if (!spec.selector) { ok = false; detail = 'selector is required'; break; }
            // waitFor({state:'visible'}) correctly waits up to timeoutMs for the
            // element to appear and become visible. isVisible() is a snapshot
            // that does NOT wait — it would fail immediately on async PostBacks.
            ok = await page.locator(spec.selector).first()
              .waitFor({ state: 'visible', timeout: timeoutMs })
              .then(() => true)
              .catch(() => false);
            actual = ok ? 'visible' : 'not visible';
            break;
          }
          case 'dom_not_visible': {
            if (!spec.selector) { ok = false; detail = 'selector is required'; break; }
            const visible = await page.locator(spec.selector).first()
              .waitFor({ state: 'visible', timeout: timeoutMs })
              .then(() => true)
              .catch(() => false);
            ok = !visible;
            actual = visible ? 'visible' : 'not visible';
            break;
          }
          case 'dom_text_contains': {
            if (!spec.selector) { ok = false; detail = 'selector is required'; break; }
            const text = (await page.locator(spec.selector).first().innerText({ timeout: timeoutMs }).catch(() => '')) || '';
            actual = text.slice(0, 200);
            ok = !!spec.expected_value && text.includes(String(spec.expected_value));
            break;
          }
          case 'page_title_contains': {
            const title = (await page.title().catch(() => '')) || '';
            actual = title;
            ok = !!spec.expected_value && title.includes(String(spec.expected_value));
            break;
          }
          case 'page_title_not_contains': {
            const title = (await page.title().catch(() => '')) || '';
            actual = title;
            ok = !spec.expected_value || !title.includes(String(spec.expected_value));
            break;
          }
          case 'no_aspnet_error': {
            ok = await ArrivalValidator.checkNoAspnetError(page);
            diagnostics.aspnetErrorDetected = !ok;
            diagnostics.pageTitle = await safePageTitle(page);
            diagnostics.currentUrl = safePageUrl(page);
            actual = ok ? 'clean' : 'aspnet_error_detected';
            break;
          }
          case 'no_login_redirect': {
            ok = await ArrivalValidator.checkNoLoginRedirect(page);
            diagnostics.loginRedirectDetected = !ok;
            diagnostics.currentUrl = safePageUrl(page);
            actual = ok ? 'clean' : 'redirected_to_login';
            break;
          }
          case 'no_500_response': {
            // Best-effort: this assertion is informational at validateAll-time
            // because the original response is no longer reachable through
            // page.url(). The check is genuine when called immediately after a
            // navigation with the captured Response object (see helper below).
            ok = options.responseStatus ? options.responseStatus < 500 : await ArrivalValidator.checkNo500Response(page);
            diagnostics.httpStatus = options.responseStatus ?? diagnostics.httpStatus;
            actual = ok ? 'clean' : `http_${options.responseStatus ?? '5xx'}_detected`;
            break;
          }
          default: {
            ok = false;
            detail = `unknown assertion type: ${spec.type}`;
          }
        }
      } catch (e: any) {
        ok = false;
        detail = (e && e.message ? e.message : String(e)).slice(0, 200);
      }

      if (ok) {
        passed.push(spec.assertion_id);
      } else {
        failed.push(spec.assertion_id);
        errors.push({
          assertion_id: spec.assertion_id,
          type: spec.type,
          actual,
          expected: String(spec.expected_value ?? ''),
          category,
          severity,
          detail: detail || undefined,
        });
        if (severity === 'hard' && options.screenshotOnFail && screenshotPath === undefined) {
          try {
            const dir = path.dirname(options.screenshotOnFail);
            if (dir) { fs.mkdirSync(dir, { recursive: true }); }
            await page.screenshot({ path: options.screenshotOnFail });
            screenshotPath = options.screenshotOnFail;
          } catch (_e) {
            screenshotPath = null;
          }
        }
      }
    }

    const hardFailures = errors.filter(e => e.severity === 'hard');
    return {
      ok: hardFailures.length === 0,
      passed,
      failed,
      errors,
      diagnostics: {
        ...diagnostics,
        currentUrl: safePageUrl(page),
        pageTitle: await safePageTitle(page),
      },
      elapsedMs: Date.now() - started,
      evaluatedAt: new Date().toISOString(),
      screenshotPath: screenshotPath ?? null,
    };
  }

  // ── Individual checks (also exposed for unit testing) ─────────────────────

  static async checkUrlContains(page: any, expected: string): Promise<boolean> {
    if (!expected) return true;
    return page.url().toLowerCase().includes(expected.toLowerCase());
  }

  static async checkDomVisible(page: any, selector: string, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<boolean> {
    return page.locator(selector).first()
      .waitFor({ state: 'visible', timeout: timeoutMs })
      .then(() => true)
      .catch(() => false);
  }

  static async checkNoAspnetError(page: any): Promise<boolean> {
    try {
      const title = (await page.title().catch(() => '')) || '';
      for (const marker of ASPNET_TITLE_MARKERS) {
        if (title.includes(marker)) return false;
      }
      const url = page.url() || '';
      for (const marker of ASPNET_URL_MARKERS) {
        if (url.includes(marker)) return false;
      }
      for (const sel of ASPNET_DOM_MARKERS) {
        const visible = await page.locator(sel).first().isVisible({ timeout: 250 }).catch(() => false);
        if (visible) return false;
      }
      return true;
    } catch (_e) {
      // Detector itself fails open — never block on a detector glitch.
      return true;
    }
  }

  static async checkNoLoginRedirect(page: any): Promise<boolean> {
    try {
      const url = (page.url() || '').toLowerCase();
      if (url.includes('frmlogin')) return false;
      // Also catch the in-page login panel (silent session timeout).
      const loginPanel = await page.locator('#ctl00_c_pnlLogin, #c_pnlLogin').first().isVisible({ timeout: 250 }).catch(() => false);
      return !loginPanel;
    } catch (_e) {
      return true;
    }
  }

  static async checkNo500Response(page: any): Promise<boolean> {
    // Without a captured Response, we approximate by inspecting the rendered
    // page for the YSOD signature. Real 5xx detection happens via the
    // response-listener installed in the spec template.
    return ArrivalValidator.checkNoAspnetError(page);
  }
}

// ── Convenience wrapper preserving the legacy function-form ──────────────────

export async function validateArrivalAssertions(
  page: any,
  assertions: AssertionSpec[] | null | undefined,
  options: ArrivalValidatorOptions = {},
): Promise<ArrivalValidationResult> {
  return ArrivalValidator.validateAll(page, assertions, options);
}

function safePageUrl(page: any): string {
  try { return String(page.url ? page.url() : ''); } catch (_e) { return ''; }
}

async function safePageTitle(page: any): Promise<string> {
  try {
    if (!page || typeof page.title !== 'function') return '';
    const value = page.title();
    if (value && typeof value.catch === 'function') {
      return String((await value.catch(() => '')) || '');
    }
    return String((await value) || '');
  } catch (_e) {
    return '';
  }
}
