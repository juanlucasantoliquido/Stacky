/**
 * playwright/helpers/navigation_executor.ts — Sprint N5-03.
 *
 * Runtime executor for a validated NavigationPlan. Iterates over plan.steps,
 * runs each method against the Playwright Page, verifies intermediate
 * assertions, and finally runs the plan's arrival_assertions.
 *
 * INPUT: a NavigationPlan/1.0 object validated by navigation_plan_validator.py.
 * OUTPUT: a NavigationResult capturing what happened — never throws on its own;
 *         callers decide whether the failure flips the test red.
 *
 * Each step emits granular evidence:
 *   evidence/<ticket>/<scenario>/<prefix>_step_<NN>_<state>.png
 * and (when emitEvents is true) a JSON line to stdout that the spec runtime
 * can scoop into execution.jsonl in Sprint N5-06.
 */

import * as fs from 'fs';
import * as path from 'path';

import {
  ArrivalValidator,
  AssertionSpec,
  ArrivalValidationResult,
  AssertionCategory,
} from './arrival_validator';

import { navigateViaFormSubmit } from './webforms_nav';

// ── Types ───────────────────────────────────────────────────────────────────

export type NavigationStrategy = 'direct_entry' | 'deeplink' | 'human_path' | 'playbook';

export type NavigationMethod =
  | 'goto_direct'
  | 'goto_deeplink'
  | 'form_submit'
  | 'dopostback'
  | 'link_click'
  | 'menu_click'
  | 'row_click'
  | 'tab_click'
  | 'button_click'
  | 'fill'
  | 'select'
  | 'check'
  | 'wait';

export interface NavigationStep {
  step_index: number;
  method: NavigationMethod;
  description: string;
  target_url?: string | null;
  eventtarget?: string | null;
  eventargument?: string | null;
  selector?: string | null;
  wait_url_contains?: string | null;
  timeout_ms?: number;
  retries?: number;
  data_bindings?: Record<string, string>;
  intermediate_assertions?: AssertionSpec[];
  screenshot_label?: string;
}

export interface SessionRequirements {
  require_valid_storagestate?: boolean;
  storagestate_max_age_minutes?: number;
}

export interface NavigationPlan {
  plan_version: string;
  ticket_id: number | string;
  scenario_id: string;
  target_screen: string;
  lane: string;
  strategy: NavigationStrategy;
  path_id?: string | null;
  playbook_id?: string | null;
  entrypoint?: string | null;
  deeplink_url?: string | null;
  steps: NavigationStep[];
  arrival_assertions: AssertionSpec[];
  session_requirements?: SessionRequirements;
}

export interface NavigationStepResult {
  step_index: number;
  method: NavigationMethod;
  description: string;
  ok: boolean;
  attempts: number;
  elapsedMs: number;
  url_before: string;
  url_after: string;
  intermediate_assertions_passed: string[];
  intermediate_assertions_failed: string[];
  screenshots: string[];
  errorCode?: string | null;
  category?: AssertionCategory | null;
  reason?: string | null;
  isTerminal?: boolean | null;
  detail?: string | null;
}

export interface NavigationResult {
  ok: boolean;
  strategy: NavigationStrategy;
  stepsCompleted: number;
  stepsFailed: number;
  failedStep: number | null;
  errorCode: string | null;
  category: AssertionCategory | null;
  reason: string | null;
  isTerminal: boolean | null;
  detail: string | null;
  elapsedMs: number;
  screenshots: string[];
  arrivalAssertionsPassed: string[];
  arrivalAssertionsFailed: string[];
  stepResults: NavigationStepResult[];
  arrivalResult: ArrivalValidationResult | null;
}

export interface NavigationExecutorOptions {
  evidenceDir: string;
  screenshotPrefix?: string;
  emitEvents?: boolean;
  baseUrl?: string;
  /** Optional bag of data to satisfy `data_bindings` on `fill`/`select` steps. */
  data?: Record<string, string>;
}

type NavErrorClassification = {
  code: string;
  category: AssertionCategory;
  reason: string;
  isTerminal: boolean;
  detail: string;
};

// ── Public entry point ──────────────────────────────────────────────────────

export async function executeNavigationPlan(
  page: any,
  plan: NavigationPlan,
  options: NavigationExecutorOptions,
): Promise<NavigationResult> {
  const started = Date.now();
  const prefix = options.screenshotPrefix || 'nav';
  ensureDir(options.evidenceDir);

  const stepResults: NavigationStepResult[] = [];
  const allScreens: string[] = [];
  let arrivalResult: ArrivalValidationResult | null = null;

  for (const step of plan.steps) {
    if (options.emitEvents) {
      emitEvent('navigation_step_started', {
        ticket_id: plan.ticket_id,
        scenario_id: plan.scenario_id,
        step_index: step.step_index,
        method: step.method,
        url_before: safePageUrl(page),
      });
    }
    const result = await runStep(page, step, plan, options, prefix);
    stepResults.push(result);
    allScreens.push(...result.screenshots);

    if (options.emitEvents) {
      emitEvent(result.ok ? 'navigation_step_completed' : 'navigation_step_failed', {
        ticket_id: plan.ticket_id,
        scenario_id: plan.scenario_id,
        step_index: step.step_index,
        method: step.method,
        ok: result.ok,
        attempts: result.attempts,
        elapsed_ms: result.elapsedMs,
        url_before: result.url_before,
        url_after: result.url_after,
        error_code: result.errorCode ?? null,
        category: result.category ?? null,
        reason: result.reason ?? null,
      });
    }

    if (!result.ok) {
      const fail: NavigationResult = {
        ok: false,
        strategy: plan.strategy,
        stepsCompleted: stepResults.filter(s => s.ok).length,
        stepsFailed: 1,
        failedStep: step.step_index,
        errorCode: result.errorCode ?? 'NAV_STEP_FAILED',
        category: result.category ?? 'NAV',
        reason: result.reason ?? 'HUMAN_PATH_STEP_FAILED',
        isTerminal: result.isTerminal ?? true,
        detail: result.detail ?? `step ${step.step_index} failed`,
        elapsedMs: Date.now() - started,
        screenshots: allScreens,
        arrivalAssertionsPassed: [],
        arrivalAssertionsFailed: [],
        stepResults,
        arrivalResult: null,
      };
      // Sprint N5-06: persist evidence artifacts even on failure paths so
      // the runner / triage always has the granular step record.
      writeStepResultsArtifact(plan, fail, options);
      writeArrivalArtifact(plan, null, options, page);
      return fail;
    }
  }

  // ── All steps OK — run arrival assertions ─────────────────────────────────
  const arrivalShot = path.join(options.evidenceDir, `${prefix}_arrival_failed.png`);
  arrivalResult = await ArrivalValidator.validateAll(page, plan.arrival_assertions, {
    screenshotOnFail: arrivalShot,
  });
  if (arrivalResult.screenshotPath) allScreens.push(arrivalResult.screenshotPath);

  if (!arrivalResult.ok) {
    const firstError = arrivalResult.errors.find(e => e.severity === 'hard') ?? arrivalResult.errors[0];
    const arrivalClassification = classifyArrivalFailure(firstError, arrivalResult);
    const fail: NavigationResult = {
      ok: false,
      strategy: plan.strategy,
      stepsCompleted: stepResults.length,
      stepsFailed: 0,
      failedStep: null,
      errorCode: arrivalClassification.code,
      category: arrivalClassification.category,
      reason: arrivalClassification.reason,
      isTerminal: arrivalClassification.isTerminal,
      detail: firstError ? `${firstError.assertion_id}: ${firstError.detail ?? firstError.actual}` : 'arrival validation failed',
      elapsedMs: Date.now() - started,
      screenshots: allScreens,
      arrivalAssertionsPassed: arrivalResult.passed,
      arrivalAssertionsFailed: arrivalResult.failed,
      stepResults,
      arrivalResult,
    };
    writeStepResultsArtifact(plan, fail, options);
    writeArrivalArtifact(plan, arrivalResult, options, page);
    return fail;
  }

  const success: NavigationResult = {
    ok: true,
    strategy: plan.strategy,
    stepsCompleted: stepResults.length,
    stepsFailed: 0,
    failedStep: null,
    errorCode: null,
    category: null,
    reason: null,
    isTerminal: null,
    detail: null,
    elapsedMs: Date.now() - started,
    screenshots: allScreens,
    arrivalAssertionsPassed: arrivalResult.passed,
    arrivalAssertionsFailed: arrivalResult.failed,
    stepResults,
    arrivalResult,
  };
  writeStepResultsArtifact(plan, success, options);
  writeArrivalArtifact(plan, arrivalResult, options, page);
  return success;
}

// ── Sprint N5-06: evidence artifacts ─────────────────────────────────────────

function writeStepResultsArtifact(
  plan: NavigationPlan,
  result: NavigationResult,
  options: NavigationExecutorOptions,
): void {
  try {
    const out = path.join(options.evidenceDir, 'navigation_step_results.json');
    fs.mkdirSync(path.dirname(out), { recursive: true });
    const payload = {
      schema_version: '1.0',
      ticket_id: plan.ticket_id,
      scenario_id: plan.scenario_id,
      target_screen: plan.target_screen,
      strategy: plan.strategy,
      navigation_ok: result.ok,
      elapsed_ms_total: result.elapsedMs,
      failed_step: result.failedStep,
      error_code: result.errorCode,
      category: result.category,
      reason: result.reason,
      is_terminal: result.isTerminal,
      final_url: result.stepResults.length > 0 ? result.stepResults[result.stepResults.length - 1].url_after : '',
      steps: result.stepResults.map(s => ({
        step_index: s.step_index,
        method: s.method,
        description: s.description,
        ok: s.ok,
        attempts: s.attempts,
        elapsed_ms: s.elapsedMs,
        url_before: s.url_before,
        url_after: s.url_after,
        intermediate_assertions_passed: s.intermediate_assertions_passed,
        intermediate_assertions_failed: s.intermediate_assertions_failed,
        screenshots: s.screenshots,
        error_code: s.errorCode ?? null,
        category: s.category ?? null,
        reason: s.reason ?? null,
        is_terminal: s.isTerminal ?? null,
        detail: s.detail ?? null,
      })),
    };
    fs.writeFileSync(out, JSON.stringify(payload, null, 2), 'utf-8');
  } catch (_e) {
    // best-effort — never let evidence writing break the navigation
  }
}

function writeArrivalArtifact(
  plan: NavigationPlan,
  arrival: ArrivalValidationResult | null,
  options: NavigationExecutorOptions,
  page: any,
): void {
  try {
    const out = path.join(options.evidenceDir, 'arrival_assertions.json');
    fs.mkdirSync(path.dirname(out), { recursive: true });
    const declared = Array.isArray(plan.arrival_assertions) ? plan.arrival_assertions : [];
    const passed = new Set(arrival?.passed ?? []);
    const failedById = new Map(
      (arrival?.errors ?? []).map(e => [e.assertion_id, e]),
    );

    let safeUrl = '';
    try { safeUrl = page.url ? String(page.url()) : ''; } catch (_e) { safeUrl = ''; }

    const records = declared.map(spec => {
      const ok = passed.has(spec.assertion_id);
      const err = failedById.get(spec.assertion_id);
      return {
        assertion_id: spec.assertion_id,
        type: spec.type,
        expected: (spec.expected_value ?? null) as string | null,
        actual: err ? err.actual : (ok ? safeUrl : null),
        passed: ok,
        severity: spec.severity ?? 'hard',
        category_on_fail: spec.category_on_fail ?? null,
        selector: spec.selector ?? null,
        elapsed_ms: arrival?.elapsedMs ?? 0,
        detail: err?.detail ?? null,
      };
    });

    const payload = {
      schema_version: '1.0',
      ticket_id: plan.ticket_id,
      scenario_id: plan.scenario_id,
      target_screen: plan.target_screen,
      navigation_strategy: plan.strategy,
      all_passed: arrival ? arrival.ok : false,
      elapsed_ms: arrival?.elapsedMs ?? 0,
      timestamp: new Date().toISOString(),
      screenshot_path: arrival?.screenshotPath ?? null,
      diagnostics: arrival?.diagnostics ?? null,
      assertions: records,
    };
    fs.writeFileSync(out, JSON.stringify(payload, null, 2), 'utf-8');
  } catch (_e) {
    // best-effort
  }
}

// ── Internals ───────────────────────────────────────────────────────────────

function allowedAttempts(step: NavigationStep): number {
  const rawAllowed = Number(
    process.env.QA_UAT_MAX_NAVIGATION_RETRIES ?? process.env.QA_NAV_RETRIES ?? 0,
  );
  const allowedRetries = Number.isFinite(rawAllowed) ? Math.max(0, rawAllowed) : 0;
  const requestedRetries = Number(step.retries ?? 0);
  const retries = Number.isFinite(requestedRetries)
    ? Math.min(Math.max(0, requestedRetries), allowedRetries)
    : 0;
  return retries + 1;
}

async function runStep(
  page: any,
  step: NavigationStep,
  plan: NavigationPlan,
  options: NavigationExecutorOptions,
  prefix: string,
): Promise<NavigationStepResult> {
  const started = Date.now();
  const urlBefore = page.url();
  const timeoutMs = step.timeout_ms ?? 45_000;
  const maxAttempts = allowedAttempts(step);
  const idx = String(step.step_index).padStart(2, '0');
  const baseUrl = options.baseUrl ?? '';
  const screenshots: string[] = [];

  // Pre-step screenshot — best-effort.
  const preShot = path.join(options.evidenceDir, `${prefix}_step_${idx}_pre.png`);
  await safeScreenshot(page, preShot, screenshots);

  let attempt = 0;
  let lastError: NavErrorClassification | null = null;

  while (attempt < maxAttempts) {
    attempt += 1;
    try {
      await executeMethod(page, step, plan, baseUrl, timeoutMs, options.data ?? {});

      // wait_url_contains — verify navigation landed.
      if (step.wait_url_contains) {
        await page.waitForURL(
          (url: any) => String(url).toLowerCase().includes(String(step.wait_url_contains).toLowerCase()),
          { timeout: timeoutMs },
        );
      }

      // Intermediate assertions check.
      const interResult = await ArrivalValidator.validateAll(page, step.intermediate_assertions, {
        screenshotOnFail: path.join(options.evidenceDir, `${prefix}_step_${idx}_assert_failed.png`),
      });
      if (interResult.screenshotPath) screenshots.push(interResult.screenshotPath);

      if (!interResult.ok) {
        const firstHard = interResult.errors.find(e => e.severity === 'hard') ?? interResult.errors[0];
        lastError = {
          code: 'INTERMEDIATE_ASSERTION_FAILED',
          category: (firstHard?.category ?? 'NAV') as AssertionCategory,
          reason: reasonForAssertion(firstHard),
          isTerminal: true,
          detail: firstHard ? `${firstHard.assertion_id}: ${firstHard.actual}` : 'intermediate assertion failed',
        };
        // Intermediate-assertion failure: do NOT retry (data/env failure).
        break;
      }

      // Success.
      const postShot = path.join(options.evidenceDir, `${prefix}_step_${idx}_completed.png`);
      await safeScreenshot(page, postShot, screenshots);
      return {
        step_index: step.step_index,
        method: step.method,
        description: step.description,
        ok: true,
        attempts: attempt,
        elapsedMs: Date.now() - started,
        url_before: urlBefore,
        url_after: page.url(),
        intermediate_assertions_passed: interResult.passed,
        intermediate_assertions_failed: interResult.failed,
        screenshots,
      };
    } catch (e: any) {
      lastError = await classifyStepError(e, page);
      if (!isRetriable(lastError) || attempt >= maxAttempts) {
        break;
      }
      // Linear backoff (≤ 4s) — kept short because the timeout already
      // governs the long wait inside executeMethod.
      await sleep(Math.min(1_000 * attempt, 4_000));
    }
  }

  const failShot = path.join(options.evidenceDir, `${prefix}_step_${idx}_failed.png`);
  await safeScreenshot(page, failShot, screenshots);

  return {
    step_index: step.step_index,
    method: step.method,
    description: step.description,
    ok: false,
    attempts: attempt,
    elapsedMs: Date.now() - started,
    url_before: urlBefore,
    url_after: page.url(),
    intermediate_assertions_passed: [],
    intermediate_assertions_failed: [],
    screenshots,
    errorCode: lastError?.code ?? 'NAV_STEP_FAILED',
    category: lastError?.category ?? 'NAV',
    reason: lastError?.reason ?? 'HUMAN_PATH_STEP_FAILED',
    isTerminal: lastError?.isTerminal ?? true,
    detail: lastError?.detail ?? 'step failed without diagnostic',
  };
}

async function executeMethod(
  page: any,
  step: NavigationStep,
  plan: NavigationPlan,
  baseUrl: string,
  timeoutMs: number,
  data: Record<string, string>,
): Promise<void> {
  const join = (target: string) => {
    if (!target) return baseUrl || '';
    if (/^https?:\/\//i.test(target)) return target;
    if (!baseUrl) return target;
    if (baseUrl.endsWith('/') && target.startsWith('/')) return baseUrl + target.slice(1);
    if (!baseUrl.endsWith('/') && !target.startsWith('/')) return baseUrl + '/' + target;
    return baseUrl + target;
  };

  switch (step.method) {
    case 'goto_direct': {
      const url = join(step.target_url || plan.target_screen);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
      return;
    }
    case 'goto_deeplink': {
      const url = join(step.target_url || plan.deeplink_url || plan.target_screen);
      await page.goto(url, { waitUntil: 'domcontentloaded', timeout: timeoutMs });
      return;
    }
    case 'form_submit': {
      if (!step.eventtarget) throw new Error('form_submit step is missing eventtarget');
      const r = await navigateViaFormSubmit(
        page,
        step.eventtarget,
        step.eventargument || '',
        step.wait_url_contains || step.target_url || plan.target_screen,
        { timeoutMs, maxAttempts: allowedAttempts(step) },
      );
      if (!r.ok) throw new Error(`form_submit failed: ${r.errorCode}`);
      return;
    }
    case 'fill': {
      if (!step.selector) throw new Error('fill step is missing selector');
      const value = resolveValue(step, data);
      await page.locator(step.selector).first().fill(value);
      return;
    }
    case 'select': {
      if (!step.selector) throw new Error('select step is missing selector');
      const value = resolveValue(step, data);
      await page.locator(step.selector).first().selectOption(value);
      return;
    }
    case 'check': {
      if (!step.selector) throw new Error('check step is missing selector');
      await page.locator(step.selector).first().check();
      return;
    }
    case 'button_click':
    case 'link_click':
    case 'menu_click':
    case 'tab_click':
    case 'row_click': {
      if (!step.selector) throw new Error(`${step.method} step is missing selector`);
      await page.locator(step.selector).first().scrollIntoViewIfNeeded().catch(() => null);
      await page.locator(step.selector).first().click({ timeout: timeoutMs, noWaitAfter: true });
      await waitForAspNetIdle(page, Math.min(timeoutMs, 15_000));
      return;
    }
    case 'dopostback': {
      if (!step.eventtarget) throw new Error('dopostback step is missing eventtarget');
      await page.evaluate(
        (args: { et: string; ea: string }) => {
          const form = document.querySelector('form') as HTMLFormElement | null;
          if (!form) throw new Error('FORM_NOT_FOUND');

          let etEl = form.querySelector('input[name="__EVENTTARGET"]') as HTMLInputElement | null;
          let eaEl = form.querySelector('input[name="__EVENTARGUMENT"]') as HTMLInputElement | null;

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

          etEl.value = args.et;
          eaEl.value = args.ea;
          HTMLFormElement.prototype.submit.call(form);
        },
        { et: step.eventtarget, ea: step.eventargument || '' },
      );
      await waitForAspNetIdle(page, Math.min(timeoutMs, 15_000));
      return;
    }
    case 'wait': {
      // wait step ensures AJAX/UpdatePanel PostBacks are fully complete before proceeding.
      // waitForLoadState('networkidle') waits until no network requests for 500ms,
      // which correctly handles ASP.NET UpdatePanel async PostBacks.
      await page.waitForLoadState('networkidle', { timeout: timeoutMs }).catch(() => null);
      return;
    }
    default: {
      throw new Error(`Unsupported method: ${step.method}`);
    }
  }
}

function resolveValue(step: NavigationStep, data: Record<string, string>): string {
  const bindings = step.data_bindings || {};
  const dataKey = bindings.value;
  if (dataKey && data[dataKey] !== undefined) return String(data[dataKey]);
  if (dataKey) return String(dataKey);
  return '';
}

async function classifyStepError(
  e: any,
  page: any,
): Promise<NavErrorClassification> {
  const msg = (e && e.message ? e.message : String(e)) as string;
  const lower = msg.toLowerCase();
  const currentUrl = safePageUrl(page);
  const url = currentUrl.toLowerCase();
  const title = (await safePageTitle(page)).toLowerCase();
  if (url.includes('frmlogin')) {
    return {
      code: 'NAV_AUTH_EXPIRED',
      category: 'ENV',
      reason: 'SESSION_EXPIRED_LOGIN_REDIRECT',
      isTerminal: true,
      detail: msg,
    };
  }
  if (
    lower.includes('runtime error') || lower.includes('server error') ||
    title.includes('runtime error') || title.includes('server error')
  ) {
    return {
      code: 'NAV_SERVER_ERROR',
      category: 'ENV',
      reason: 'ASPNET_APPPOOL_ERROR',
      isTerminal: true,
      detail: msg,
    };
  }
  if (url.includes('errors.aspx') || url.includes('error.aspx')) {
    return {
      code: 'NAV_SERVER_ERROR',
      category: 'ENV',
      reason: 'ASPNET_REDIRECT_TO_ERRORS_PAGE',
      isTerminal: true,
      detail: msg,
    };
  }
  if (lower.includes('grid_empty') || lower.includes('grid empty') || lower.includes('no rows') || lower.includes('search_results_empty')) {
    return {
      code: 'NAV_DATA_GRID_EMPTY',
      category: 'DATA',
      reason: 'SEARCH_RESULTS_EMPTY',
      isTerminal: true,
      detail: msg,
    };
  }
  if (lower.includes('form_not_found') || lower.includes('form not found') || lower.includes('cannot read')) {
    return {
      code: 'NAV_FORM_NOT_FOUND',
      category: 'NAV',
      reason: 'ASPNET_FORM_MISSING',
      isTerminal: true,
      detail: msg,
    };
  }
  if (lower.includes('timeout') || lower.includes('timed out')) {
    return {
      code: 'NAV_TIMEOUT',
      category: 'NAV',
      reason: 'NAVIGATION_TIMEOUT',
      isTerminal: false,
      detail: msg,
    };
  }
  return {
    code: 'NAV_PLAYWRIGHT_ERROR',
    category: 'NAV',
    reason: 'PLAYWRIGHT_EXCEPTION',
    isTerminal: false,
    detail: msg,
  };
}

function classifyArrivalFailure(
  firstError: any,
  arrivalResult: ArrivalValidationResult,
): NavErrorClassification {
  const reason = reasonForAssertion(firstError);
  const category = (firstError?.category ?? 'NAV') as AssertionCategory;
  const code =
    reason === 'ASPNET_APPPOOL_ERROR' || reason === 'ASPNET_REDIRECT_TO_ERRORS_PAGE'
      ? 'NAV_SERVER_ERROR'
      : reason === 'SESSION_EXPIRED_LOGIN_REDIRECT'
        ? 'NAV_AUTH_EXPIRED'
        : reason === 'SEARCH_RESULTS_EMPTY'
          ? 'NAV_DATA_GRID_EMPTY'
          : 'ARRIVAL_ASSERTION_FAILED';
  return {
    code,
    category,
    reason,
    isTerminal: true,
    detail: firstError
      ? `${firstError.assertion_id}: ${firstError.detail ?? firstError.actual}`
      : `arrival validation failed at ${arrivalResult.diagnostics.currentUrl}`,
  };
}

function isRetriable(error: NavErrorClassification): boolean {
  return !error.isTerminal && (error.code === 'NAV_TIMEOUT' || error.code === 'NAV_PLAYWRIGHT_ERROR');
}

function reasonForAssertion(firstError: any): string {
  const type = String(firstError?.type ?? '');
  const actual = String(firstError?.actual ?? '').toLowerCase();
  const category = String(firstError?.category ?? 'NAV');
  if (type === 'no_login_redirect' || actual.includes('redirected_to_login')) {
    return 'SESSION_EXPIRED_LOGIN_REDIRECT';
  }
  if (type === 'no_aspnet_error' || type === 'no_500_response' || actual.includes('aspnet_error') || actual.includes('http_5')) {
    return 'ASPNET_APPPOOL_ERROR';
  }
  if (category === 'DATA') {
    return 'SEARCH_RESULTS_EMPTY';
  }
  return 'ARRIVAL_ASSERTION_FAILED';
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

function ensureDir(dir: string): void {
  try { fs.mkdirSync(dir, { recursive: true }); } catch (_e) { /* best-effort */ }
}

async function waitForAspNetIdle(page: any, timeoutMs: number): Promise<void> {
  try {
    await page.waitForFunction(
      () => {
        const manager = (window as any).Sys?.WebForms?.PageRequestManager?.getInstance?.();
        return !manager || !manager.get_isInAsyncPostBack();
      },
      null,
      { timeout: timeoutMs },
    );
  } catch (_e) {
    // Some full postbacks detach the old execution context. The explicit
    // per-step assertions still own the final wait/diagnostic.
  }
}

async function safeScreenshot(page: any, filePath: string, sink: string[]): Promise<void> {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    await page.screenshot({ path: filePath });
    sink.push(filePath);
  } catch (_e) {
    // best-effort
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function emitEvent(event: string, data: Record<string, any>): void {
  try {
    // The runner harvests stdout lines that look like JSON events.
    // Use a marker prefix so the line is unambiguous and easy to grep.
    process.stdout.write(
      `[nav-event] ${JSON.stringify({ event, ...data, ts: new Date().toISOString() })}\n`,
    );
  } catch (_e) {
    // never let logging break navigation
  }
}
