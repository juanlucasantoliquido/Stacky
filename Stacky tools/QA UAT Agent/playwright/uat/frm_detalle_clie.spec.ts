import { test, expect, Page, Locator } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { navigateViaFormSubmit } from '../helpers/webforms_nav';
import { FrmDetalleCliePage } from '../flows/cliente_flow';

const BASE_URL = normalizeBaseUrl(process.env.AGENDA_WEB_BASE_URL || 'http://localhost:35017/AgendaWeb/');
const CLCOD = process.env.QA_UAT_DETALLE_CLIE_CLCOD || process.env.QA_UAT_CLCOD || '4127924112345393';
const EVIDENCE_DIR = process.env.QA_UAT_DETALLE_CLIE_EVIDENCE_DIR ||
  path.join('evidence', 'manual', `frm_detalle_clie_${CLCOD}_${timestampId()}`);

const SEL_BUSQ_CLIE = '#c_abfCodCliente, [id$="abfCodCliente"]';
const SEL_BUSQ_BTN = '#c_btnOk, #c_btnBuscar, [id$="btnOk"], [id$="btnBuscar"]';
const SEL_GRID_PERSONAS = '#c_GridPersonas, [id$="GridPersonas"]';
const SEL_GRID_OBLIGACIONES = '#c_GridObligaciones, [id$="GridObligaciones"]';

test.describe('QA UAT discovery - FrmDetalleClie read-only', () => {
  test('carga desde busqueda, muestra datos base y permite seleccionar obligacion', async ({ page }) => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    page.setDefaultTimeout(15_000);

    await openDetalleCliente(page);
    const detalle = new FrmDetalleCliePage(page, BASE_URL);
    await detalle.assertLoaded();
    await screenshot(page, '01_detalle_loaded');

    await expect(detalle.byAspId('abfDocumento')).toBeVisible();
    await expect(detalle.byAspId('abfAtrasoTotal')).toBeVisible();
    await waitForRows(page, SEL_GRID_OBLIGACIONES, 20_000, `DATA_DETALLE_SIN_OBLIGACIONES cliente=${CLCOD}`);

    await detalle.selectFirstObligacion();
    await screenshot(page, '02_obligacion_selected');
    await expect(detalle.byAspId('lblsSaldoDeuda')).toBeVisible();
  });

  test('abre modales principales sin ejecutar escrituras', async ({ page }) => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    page.setDefaultTimeout(15_000);

    await openDetalleCliente(page);
    const detalle = new FrmDetalleCliePage(page, BASE_URL);
    await detalle.assertLoaded();

    await maybeStep('abrir compromisos', detalle.byAspId('btnCompromisos'), async () => {
      await detalle.openCompromisos();
      await expect(detalle.byAspId('GridObligacionesCompromisos')).toBeVisible({ timeout: 10_000 });
      await screenshot(page, '03_modal_compromisos_readonly');
      await clickIfVisible(page, '#c_btnCancelarModalCompromisos, [id$="btnCancelarModalCompromisos"]');
    });

    await maybeStep('abrir convenios', detalle.byAspId('btnConvenios'), async () => {
      await detalle.openConvenios();
      await expect(detalle.byAspId('GridObligacionesConvenios')).toBeVisible({ timeout: 10_000 });
      await screenshot(page, '04_modal_convenios_readonly');
      await clickIfVisible(page, '#c_btnCancelarConvenios, [id$="btnCancelarConvenios"]');
    });

    await maybeStep('abrir notas', detalle.byAspId('btnNotas'), async () => {
      await detalle.openNotas();
      await screenshot(page, '05_modal_notas_readonly');
      await clickIfVisible(page, '#c_btnCerrarModalComentarios, [id$="btnCerrarModalComentarios"], #c_btnCerrarNota, [id$="btnCerrarNota"]');
    });

    await maybeStep('abrir documentos', detalle.byAspId('btnDocumento'), async () => {
      await detalle.openDocumento();
      await screenshot(page, '06_modal_documentos_readonly');
      await clickIfVisible(page, '#c_btnCloseDocumento, [id$="btnCloseDocumento"], #c_btnCerrarDocumento, [id$="btnCerrarDocumento"]');
    });
  });

  test('validacion de ejecutar sin accion no debe persistir datos', async ({ page }) => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    page.setDefaultTimeout(15_000);

    await openDetalleCliente(page);
    const detalle = new FrmDetalleCliePage(page, BASE_URL);
    await detalle.assertLoaded();

    const executeVisible = await detalle.byAspId('btnEjecutar').isVisible().catch(() => false);
    test.skip(!executeVisible, 'El usuario QA no tiene visible la seccion Accion / Agendar.');

    const body = await detalle.validateEjecutarRequiresAction();
    await screenshot(page, '07_ejecutar_validation_only');
    expect(body).not.toMatch(/Se ha efectuado la Acci[oó]n|Se ha efectuado la Agenda/i);
    expect(body).not.toMatch(/Server Error|Runtime Error/i);
  });
});

async function openDetalleCliente(page: Page): Promise<void> {
  await page.goto(BASE_URL + 'FrmBusqueda.aspx', { waitUntil: 'domcontentloaded', timeout: 30_000 });
  await assertLoggedIn(page);
  await expect(page.locator(SEL_BUSQ_CLIE).first()).toBeVisible({ timeout: 10_000 });

  await page.locator(SEL_BUSQ_CLIE).first().fill(CLCOD);
  await clickAndSettle(page, page.locator(SEL_BUSQ_BTN).first(), 20_000);
  await waitForRows(page, SEL_GRID_PERSONAS, 20_000, `DATA_SEARCH_RESULTS_EMPTY cliente=${CLCOD}`);
  await screenshot(page, '00_busqueda_cliente');

  await clickAndSettle(page, gridRows(page, SEL_GRID_PERSONAS).first().locator('td').first(), 20_000);
  await waitForRows(page, SEL_GRID_OBLIGACIONES, 20_000, `DATA_CLIENTE_SIN_OBLIGACIONES_INTERMEDIA cliente=${CLCOD}`);

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
}

async function maybeStep(label: string, locator: Locator, body: () => Promise<void>): Promise<void> {
  const visible = await locator.isVisible().catch(() => false);
  test.skip(!visible, `${label}: control no visible para el usuario/datos actuales.`);
  await test.step(label, body);
}

async function clickAndSettle(page: Page, locator: Locator, timeoutMs: number): Promise<void> {
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
    const body = await page.locator('body').innerText({ timeout: 3_000 }).catch(() => '');
    throw new Error(`${emptyCode}. url=${page.url()} body=${body.slice(0, 700)}`);
  }
  return gridRows(page, gridSelector).count();
}

async function assertLoggedIn(page: Page): Promise<void> {
  if (page.url().toLowerCase().includes('frmlogin')) {
    throw new Error(`ENV_AUTH_EXPIRED redirected to login. url=${page.url()}`);
  }
}

async function clickIfVisible(page: Page, selector: string): Promise<void> {
  const target = page.locator(selector).first();
  const visible = await target.isVisible().catch(() => false);
  if (!visible) return;
  await target.click({ noWaitAfter: true }).catch(() => undefined);
  await waitForAspNetIdle(page, 5_000);
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

function gridRows(page: Page, gridSelector: string): Locator {
  return page.locator(gridSelector).first().locator('tbody tr');
}
