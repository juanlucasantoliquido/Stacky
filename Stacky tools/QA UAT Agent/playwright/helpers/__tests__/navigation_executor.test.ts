/**
 * Sprint N5-03 — navigation_executor.test.ts
 *
 * Page-mock coverage for executeNavigationPlan. Verifies:
 *   - Happy path (every step + arrival assertions pass).
 *   - A failing step short-circuits with the correct errorCode + category.
 *   - Failed-step screenshot is captured.
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  executeNavigationPlan,
  NavigationPlan,
} from '../navigation_executor';

// ── Mock page ────────────────────────────────────────────────────────────────

interface MockPageState {
  url: string;
  title: string;
  visibleSelectors: Set<string>;
  fillThrows?: boolean;
  clickThrows?: boolean;
  gotoLatestUrl?: string;
  screenshots: string[];
}

function makePage(state: MockPageState): any {
  return {
    url: () => state.url,
    title: async () => state.title,
    goto: async (url: string, _opts: any) => {
      state.url = url;
      state.gotoLatestUrl = url;
    },
    waitForURL: async (_pred: any, _opts: any) => undefined,
    waitForLoadState: async (_state: any) => undefined,
    locator: (selector: string) => ({
      first: () => ({
        isVisible: async (_opts?: any) => state.visibleSelectors.has(selector),
        innerText: async (_opts?: any) => '',
        scrollIntoViewIfNeeded: async () => undefined,
        click: async (_opts?: any) => {
          if (state.clickThrows) throw new Error('click failed (timeout)');
        },
        fill: async (_val: string) => {
          if (state.fillThrows) throw new Error('fill failed');
        },
        selectOption: async (_val: string) => undefined,
        check: async () => undefined,
      }),
    }),
    screenshot: async (opts: any) => {
      if (opts && opts.path) {
        fs.mkdirSync(path.dirname(opts.path), { recursive: true });
        fs.writeFileSync(opts.path, '');
        state.screenshots.push(opts.path);
      }
    },
    evaluate: async (_fn: any, _args: any) => undefined,
  };
}

function tmpEvidenceDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'n503-exec-'));
}

function basePlan(): NavigationPlan {
  return {
    plan_version: '1.0',
    ticket_id: 120,
    scenario_id: 'P02',
    target_screen: 'FrmDetalleClie.aspx',
    lane: 'uat_human',
    strategy: 'human_path',
    entrypoint: 'FrmBusqueda.aspx',
    steps: [
      { step_index: 1, method: 'goto_direct', description: 'go to busqueda', target_url: 'FrmBusqueda.aspx', wait_url_contains: 'FrmBusqueda', timeout_ms: 5_000, retries: 0 },
      { step_index: 2, method: 'fill', description: 'fill clcod', selector: '#c_abfCliente', data_bindings: { value: 'CLCOD' }, timeout_ms: 5_000, retries: 0 },
      { step_index: 3, method: 'button_click', description: 'click buscar', selector: '#c_btnBuscar', timeout_ms: 5_000, retries: 0 },
    ],
    arrival_assertions: [
      { assertion_id: 'no_aspnet_error', type: 'no_aspnet_error', description: '', severity: 'hard', category_on_fail: 'ENV' },
      { assertion_id: 'url_contains_busqueda', type: 'url_contains', expected_value: 'FrmBusqueda', description: '', severity: 'hard', category_on_fail: 'NAV' },
    ],
    session_requirements: { require_valid_storagestate: false, storagestate_max_age_minutes: 120 },
  };
}

// ── Happy path ───────────────────────────────────────────────────────────────

export async function test_execute_navigation_plan_happy_path() {
  const evidence = tmpEvidenceDir();
  const state: MockPageState = {
    url: 'about:blank',
    title: '',
    visibleSelectors: new Set(['#c_abfCliente', '#c_btnBuscar']),
    screenshots: [],
  };
  const page = makePage(state);
  const result = await executeNavigationPlan(page, basePlan(), {
    evidenceDir: evidence,
    screenshotPrefix: 'nav',
    emitEvents: false,
    baseUrl: 'http://localhost:35017/AgendaWeb/',
    data: { CLCOD: '12345' },
  });
  if (!result.ok) throw new Error('happy path should pass: ' + JSON.stringify(result));
  if (result.stepsCompleted !== 3) throw new Error('expected 3 steps completed');
  if (!result.arrivalResult || !result.arrivalResult.ok) throw new Error('arrival should pass');
}

// ── Failure on step 2 ────────────────────────────────────────────────────────

export async function test_execute_navigation_plan_failure_step_2() {
  const evidence = tmpEvidenceDir();
  const state: MockPageState = {
    url: 'about:blank',
    title: '',
    visibleSelectors: new Set(),
    fillThrows: true,
    screenshots: [],
  };
  const page = makePage(state);
  const result = await executeNavigationPlan(page, basePlan(), {
    evidenceDir: evidence,
    screenshotPrefix: 'nav',
    emitEvents: false,
    baseUrl: 'http://localhost:35017/AgendaWeb/',
    data: { CLCOD: '12345' },
  });
  if (result.ok) throw new Error('should have failed at step 2');
  if (result.failedStep !== 2) throw new Error('expected failedStep=2');
  if (!result.errorCode) throw new Error('errorCode required');
  // Screenshot for the failed step must exist.
  const hasFailedShot = result.screenshots.some(s => s.includes('step_02_failed'));
  if (!hasFailedShot) throw new Error('failed step screenshot missing');
}

// ── Arrival assertion failure ────────────────────────────────────────────────

export async function test_execute_navigation_plan_arrival_failure_classifies_env() {
  const evidence = tmpEvidenceDir();
  const state: MockPageState = {
    url: 'http://localhost:35017/AgendaWeb/FrmBusqueda.aspx',
    title: 'Runtime Error',   // triggers no_aspnet_error failure
    visibleSelectors: new Set(['#c_abfCliente', '#c_btnBuscar']),
    screenshots: [],
  };
  const page = makePage(state);
  const result = await executeNavigationPlan(page, basePlan(), {
    evidenceDir: evidence,
    baseUrl: 'http://localhost:35017/AgendaWeb/',
    data: { CLCOD: '12345' },
  });
  if (result.ok) throw new Error('arrival should fail when title is Runtime Error');
  if (result.category !== 'ENV') throw new Error(`expected category=ENV, got ${result.category}`);
  if (result.errorCode !== 'ARRIVAL_ASSERTION_FAILED') throw new Error('expected ARRIVAL_ASSERTION_FAILED');
}
