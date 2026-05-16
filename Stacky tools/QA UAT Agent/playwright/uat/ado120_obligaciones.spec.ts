import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { spawnSync } from 'child_process';
import { navigateViaFormSubmit } from '../helpers/webforms_nav';

const BASE_URL = normalizeBaseUrl(process.env.AGENDA_WEB_BASE_URL || 'http://localhost:35017/AgendaWeb/');
const CLCOD = process.env.QA_UAT_ADO120_CLCOD || process.env.QA_UAT_CLCOD || '4127924112345393';
const EVIDENCE_DIR = process.env.QA_UAT_ADO120_EVIDENCE_DIR ||
  path.join('evidence', '120', `ado120_${timestampId()}`);

const SEL_BUSQ_CLIE = '#c_abfCodCliente';
const SEL_BUSQ_BTN = '#c_btnOk, #c_btnBuscar';
const SEL_GRID_PERSONAS = '#c_GridPersonas';
const SEL_GRID_OBLIGACIONES = '#c_GridObligaciones';

type HeaderCheck = {
  key: string;
  label: string;
  patterns: RegExp[];
  foundIndex?: number;
  foundText?: string;
};

type GridHeader = {
  index: number;
  text: string;
};

const NEW_COLUMN_CHECKS: HeaderCheck[] = [
  { key: 'OGCANAL', label: 'Canal de venta', patterns: [/canal/] },
  { key: 'OGMEDIOPAGO', label: 'Medio de cobro de ultimo pago', patterns: [/medio.*(cobro|pago)/, /(cobro|pago).*medio/] },
  { key: 'OGDEBAUT_DESC', label: 'Afiliado al Debito Automatico', patterns: [/(deb|debit).*auto/, /automatico/] },
  { key: 'DESALDOFAVOR', label: 'Saldo a favor disponible', patterns: [/saldo.*favor/] },
  { key: 'OGCUOTA', label: 'Cuota', patterns: [/^cuota$/] },
  { key: 'OGMONTOCUOTA', label: 'Monto de la Cuota', patterns: [/monto.*cuota/] },
  { key: 'OGCORREDOR', label: 'Nombre del Corredor', patterns: [/corredor/] },
  { key: 'OGNROCUOTAS', label: 'Numero de Cuotas', patterns: [/(nro|numero|num).*cuota/, /cuotas/] },
];
const REQUIRED_BATCH_FIELDS = ['OGCANAL', 'OGMEDIOPAGO', 'DESALDOFAVOR', 'OGCUOTA', 'OGMONTOCUOTA', 'OGCORREDOR'];

test.describe('ADO-120 RF-007 - Lista de Obligaciones', () => {
  test.afterAll(() => {
    if (process.env.QA_UAT_SKIP_FOCUSED_PUBLISH === 'true') return;
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    const script = path.resolve('focused_ado120_publisher.py');
    const result = spawnSync(
      process.env.PYTHON || 'python',
      [script, '--evidence-dir', EVIDENCE_DIR, '--mode', 'auto'],
      { encoding: 'utf8', env: process.env },
    );
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'focused_publish_result.json'),
      JSON.stringify({ status: result.status, stdout: result.stdout, stderr: result.stderr }, null, 2),
      'utf8',
    );
    expect(result.status, `focused_ado120_publisher failed: ${result.stderr || result.stdout}`).toBe(0);
  });

  test('valida columnas nuevas, ausencia de ingreso judicial y solo lectura', async ({ page }) => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    page.setDefaultTimeout(15_000);

    await openDetalleCliente(page);
    await screenshot(page, '01_detalle_cliente_obligaciones');

    await waitForRows(page, SEL_GRID_OBLIGACIONES, 20_000, `DATA_CLIENTE_SIN_OBLIGACIONES cliente=${CLCOD}`);

    const headerRecords = await getGridHeaders(page);
    const headers = headerRecords.map((h) => h.text).filter(Boolean);
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'grid_headers.json'),
      JSON.stringify({ clcod: CLCOD, url: page.url(), headers, header_records: headerRecords }, null, 2),
      'utf8',
    );

    const normalizedHeaders = headerRecords.map((h) => normalize(h.text));
    const judicialHeader = normalizedHeaders.find((h) =>
      h.includes('ingreso judicial') || h.includes('pasaje judicial') || h.includes('fecha ingreso judicial'));
    expect(judicialHeader, `La columna Fecha de ingreso judicial no debe estar en headers=${JSON.stringify(headers)}`).toBeUndefined();

    const checks = resolveColumnChecks(headerRecords);
    const missing = checks.filter((c) => c.foundIndex === undefined).map((c) => c.label);
    expect(missing, `Faltan columnas nuevas. Headers reales=${JSON.stringify(headers)}`).toEqual([]);

    const readonly = await assertColumnsReadonly(page, checks);
    expect(readonly.editableCells, `Las columnas nuevas deben ser solo lectura: ${JSON.stringify(readonly.editableCells)}`).toEqual([]);

    const firstRowValues = await extractFirstRowValues(page, checks);
    const debitoValue = firstRowValues['OGDEBAUT_DESC'] || '';
    expect(['', '-', 'si', 'no']).toContain(normalize(debitoValue));

    const summary = {
      ticket: 120,
      clcod: CLCOD,
      verdict: 'PASS_STRUCTURAL',
      url: page.url(),
      checked_at: new Date().toISOString(),
      assertions: {
        judicial_header_absent: true,
        new_columns_present: checks.map((c) => ({ key: c.key, label: c.label, index: c.foundIndex, text: c.foundText })),
        readonly_columns: true,
        debito_auto_value_allowed: debitoValue,
      },
      first_row_values: firstRowValues,
      evidence_dir: EVIDENCE_DIR,
    };
    const missingBatchFields = missingRequiredBatchFields(firstRowValues);
    fs.writeFileSync(
      path.join(EVIDENCE_DIR, 'data_readiness.json'),
      JSON.stringify({
        clcod: CLCOD,
        status: missingBatchFields.length ? 'BLOCKED_DATA' : 'OK',
        missing_batch_fields: missingBatchFields,
        required_batch_fields: REQUIRED_BATCH_FIELDS,
      }, null, 2),
      'utf8',
    );
    fs.writeFileSync(path.join(EVIDENCE_DIR, 'summary.json'), JSON.stringify(summary, null, 2), 'utf8');
    await screenshot(page, '02_ado120_validado');
  });
});

async function openDetalleCliente(page: Page): Promise<void> {
  await page.goto(BASE_URL + 'FrmBusqueda.aspx', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await assertLoggedIn(page);
  await expect(page.locator(SEL_BUSQ_CLIE)).toBeVisible({ timeout: 10_000 });

  await page.locator(SEL_BUSQ_CLIE).fill(CLCOD);
  await clickAndSettle(page, page.locator(SEL_BUSQ_BTN).first(), 20_000);
  await waitForRows(page, SEL_GRID_PERSONAS, 20_000, `DATA_SEARCH_RESULTS_EMPTY cliente=${CLCOD}`);
  await screenshot(page, '00_busqueda_cliente');

  await clickAndSettle(page, page.locator(`${SEL_GRID_PERSONAS} tbody tr`).first().locator('td').first(), 20_000);
  await waitForRows(page, SEL_GRID_OBLIGACIONES, 20_000, `DATA_CLIENTE_SIN_OBLIGACIONES_INTERMEDIA cliente=${CLCOD}`);
  await screenshot(page, '00b_obligaciones_intermedia');

  const nav = await navigateViaFormSubmit(
    page,
    'ctl00$c$GridObligaciones',
    'Select$0',
    'FrmDetalleClie',
    { timeoutMs: 45_000, maxAttempts: 2, screenshotDir: EVIDENCE_DIR, screenshotPrefix: 'nav_detalle' },
  );
  if (!nav.ok) {
    throw new Error(`NAV_${nav.errorCode}: ${nav.errorDetail} urlBefore=${nav.urlBefore} urlAfter=${nav.urlAfter}`);
  }
  await assertLoggedIn(page);
  await waitForRows(page, SEL_GRID_OBLIGACIONES, 20_000, `DATA_DETALLE_SIN_OBLIGACIONES cliente=${CLCOD}`);
}

async function getGridHeaders(page: Page): Promise<GridHeader[]> {
  return page.locator(`${SEL_GRID_OBLIGACIONES} th`).evaluateAll((nodes) =>
    nodes.map((n, index) => ({ index, text: (n.textContent || '').replace(/\s+/g, ' ').trim() })),
  );
}

function resolveColumnChecks(headers: GridHeader[]): HeaderCheck[] {
  return NEW_COLUMN_CHECKS.map((check) => {
    const foundHeader = headers.find((header) => {
      const text = normalize(header.text);
      return check.patterns.some((pattern) => pattern.test(text));
    });
    return {
      ...check,
      foundIndex: foundHeader?.index,
      foundText: foundHeader?.text,
    };
  });
}

async function assertColumnsReadonly(page: Page, checks: HeaderCheck[]): Promise<{ editableCells: unknown[] }> {
  return page.evaluate(
    ({ gridSelector, columnChecks }) => {
      const grid = document.querySelector(gridSelector);
      const firstRow = grid?.querySelector('tbody tr');
      const cells = Array.from(firstRow?.querySelectorAll('td') || []);
      const editableCells = [];
      for (const check of columnChecks) {
        if (check.foundIndex === undefined) continue;
        const cell = cells[check.foundIndex];
        if (!cell) {
          editableCells.push({ key: check.key, reason: 'cell_not_found', index: check.foundIndex });
          continue;
        }
        const editable = cell.querySelector('input:not([type="hidden"]), select, textarea, button, [contenteditable="true"]');
        if (editable) {
          editableCells.push({
            key: check.key,
            index: check.foundIndex,
            tag: editable.tagName,
            html: (editable as HTMLElement).outerHTML.slice(0, 250),
          });
        }
      }
      return { editableCells };
    },
    { gridSelector: SEL_GRID_OBLIGACIONES, columnChecks: checks },
  );
}

async function extractFirstRowValues(page: Page, checks: HeaderCheck[]): Promise<Record<string, string>> {
  return page.evaluate(
    ({ gridSelector, columnChecks }) => {
      const grid = document.querySelector(gridSelector);
      const firstRow = grid?.querySelector('tbody tr');
      const cells = Array.from(firstRow?.querySelectorAll('td') || []);
      const values: Record<string, string> = {};
      for (const check of columnChecks) {
        if (check.foundIndex === undefined) continue;
        values[check.key] = (cells[check.foundIndex]?.textContent || '').replace(/\s+/g, ' ').trim();
      }
      return values;
    },
    { gridSelector: SEL_GRID_OBLIGACIONES, columnChecks: checks },
  );
}

async function waitForRows(page: Page, gridSelector: string, timeoutMs: number, emptyCode: string): Promise<number> {
  const ok = await page.waitForFunction(
    (selector: string) => {
      const grid = document.querySelector(selector);
      return !!grid && grid.querySelectorAll('tbody tr').length > 0;
    },
    gridSelector,
    { timeout: timeoutMs },
  ).then(() => true).catch(() => false);

  if (!ok) {
    await screenshot(page, `blocked_${sanitize(emptyCode)}`);
    const body = await safeInnerText(page.locator('body'));
    throw new Error(`${emptyCode}. url=${page.url()} body=${body.slice(0, 700)}`);
  }
  return page.locator(`${gridSelector} tbody tr`).count();
}

async function clickAndSettle(page: Page, locator: ReturnType<Page['locator']>, timeoutMs: number): Promise<void> {
  await locator.click({ noWaitAfter: true, timeout: timeoutMs });
  await waitForAspNetIdle(page, Math.min(timeoutMs, 15_000));
}

async function waitForAspNetIdle(page: Page, timeoutMs: number): Promise<void> {
  await page.waitForFunction(
    () => {
      const manager = (window as any).Sys?.WebForms?.PageRequestManager?.getInstance?.();
      return !manager || !manager.get_isInAsyncPostBack();
    },
    null,
    { timeout: timeoutMs },
  ).catch(() => undefined);
}

async function assertLoggedIn(page: Page): Promise<void> {
  if (page.url().toLowerCase().includes('frmlogin')) {
    throw new Error(`ENV_AUTH_EXPIRED redirected to login. url=${page.url()}`);
  }
}

async function safeInnerText(locator: ReturnType<Page['locator']>): Promise<string> {
  return locator.innerText({ timeout: 3_000 }).catch(() => '');
}

async function screenshot(page: Page, label: string): Promise<void> {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  await page.screenshot({ path: path.join(EVIDENCE_DIR, `${label}.png`), fullPage: true }).catch(() => undefined);
}

function normalizeBaseUrl(value: string): string {
  return value.endsWith('/') ? value : `${value}/`;
}

function timestampId(): string {
  return new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14);
}

function sanitize(value: string): string {
  return value.replace(/[^a-z0-9_-]+/gi, '_').slice(0, 80);
}

function missingRequiredBatchFields(values: Record<string, string>): string[] {
  return REQUIRED_BATCH_FIELDS.filter((key) => {
    const value = (values[key] || '').trim();
    return value === '' || value === '-' || value === '0';
  });
}

function normalize(value: string): string {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase();
}
