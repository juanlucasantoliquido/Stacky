/**
 * Sprint N5-03 — arrival_validator.test.ts
 *
 * Page-mock unit coverage for ArrivalValidator. These tests do NOT spin up a
 * real browser — they pass an inline mock object that fulfils the shape used
 * by the validator (url(), title(), locator(...).first().isVisible(...)).
 *
 * Runner: any TS test runner with a `test/expect` API. The fixture is
 * deliberately framework-agnostic so the file works under Playwright Test,
 * Jest, Vitest, or Node's built-in test runner.
 */

import { ArrivalValidator, AssertionSpec } from '../arrival_validator';

// ── Minimal mock page ────────────────────────────────────────────────────────

interface MockState {
  url: string;
  title: string;
  visibleSelectors: Set<string>;
}

function makePage(state: MockState): any {
  return {
    url: () => state.url,
    title: async () => state.title,
    locator: (selector: string) => ({
      first: () => ({
        isVisible: async (_opts?: any) => state.visibleSelectors.has(selector),
        innerText: async (_opts?: any) => '',
      }),
    }),
    screenshot: async (_opts: any) => Buffer.from(''),
  };
}

// ── url_contains ─────────────────────────────────────────────────────────────

export async function test_url_contains_pass() {
  const page = makePage({
    url: 'http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx?clcod=1',
    title: 'Detalle Cliente',
    visibleSelectors: new Set(),
  });
  const assertions: AssertionSpec[] = [
    { assertion_id: 'a', type: 'url_contains', expected_value: 'FrmDetalleClie', description: '', severity: 'hard', category_on_fail: 'NAV' },
  ];
  const r = await ArrivalValidator.validateAll(page, assertions);
  if (!r.ok || r.passed.length !== 1) throw new Error('url_contains should pass');
}

export async function test_url_contains_fail_with_category() {
  const page = makePage({ url: 'http://localhost:35017/AgendaWeb/FrmBusqueda.aspx', title: '', visibleSelectors: new Set() });
  const assertions: AssertionSpec[] = [
    { assertion_id: 'a', type: 'url_contains', expected_value: 'FrmDetalleClie', description: '', severity: 'hard', category_on_fail: 'NAV' },
  ];
  const r = await ArrivalValidator.validateAll(page, assertions);
  if (r.ok || r.errors[0].category !== 'NAV') throw new Error('expected NAV failure');
}

// ── no_aspnet_error ──────────────────────────────────────────────────────────

export async function test_no_aspnet_error_detects_ysod_title() {
  const page = makePage({ url: 'http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx', title: 'Runtime Error', visibleSelectors: new Set() });
  const ok = await ArrivalValidator.checkNoAspnetError(page);
  if (ok) throw new Error('Runtime Error title should fail no_aspnet_error');
}

export async function test_no_aspnet_error_detects_errors_aspx_url() {
  const page = makePage({ url: 'http://localhost:35017/AgendaWeb/Errors.aspx?code=500', title: '', visibleSelectors: new Set() });
  const ok = await ArrivalValidator.checkNoAspnetError(page);
  if (ok) throw new Error('Errors.aspx URL should fail no_aspnet_error');
}

export async function test_no_aspnet_error_clean_page() {
  const page = makePage({ url: 'http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx', title: 'Detalle Cliente', visibleSelectors: new Set() });
  const ok = await ArrivalValidator.checkNoAspnetError(page);
  if (!ok) throw new Error('clean page should pass no_aspnet_error');
}

// ── no_login_redirect ────────────────────────────────────────────────────────

export async function test_no_login_redirect_detects_frmlogin() {
  const page = makePage({ url: 'http://localhost:35017/AgendaWeb/FrmLogin.aspx', title: '', visibleSelectors: new Set() });
  const ok = await ArrivalValidator.checkNoLoginRedirect(page);
  if (ok) throw new Error('FrmLogin URL should fail no_login_redirect');
}

// ── dom_visible ──────────────────────────────────────────────────────────────

export async function test_dom_visible_pass() {
  const page = makePage({ url: '', title: '', visibleSelectors: new Set(['#c_pnlDetalle']) });
  const r = await ArrivalValidator.validateAll(page, [
    { assertion_id: 'panel', type: 'dom_visible', selector: '#c_pnlDetalle', description: '', severity: 'hard', category_on_fail: 'APP' },
  ]);
  if (!r.ok) throw new Error('dom_visible should pass when selector is visible');
}

export async function test_dom_visible_fail_with_category_app() {
  const page = makePage({ url: '', title: '', visibleSelectors: new Set() });
  const r = await ArrivalValidator.validateAll(page, [
    { assertion_id: 'panel', type: 'dom_visible', selector: '#c_pnlDetalle', description: '', severity: 'hard', category_on_fail: 'APP' },
  ]);
  if (r.ok || r.errors[0].category !== 'APP') throw new Error('expected APP failure');
}
