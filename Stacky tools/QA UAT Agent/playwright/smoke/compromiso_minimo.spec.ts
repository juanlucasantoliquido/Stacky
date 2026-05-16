import { test, expect, Page, Locator } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const BASE_URL = normalizeBaseUrl(process.env.AGENDA_WEB_BASE_URL || 'http://localhost:35017/AgendaWeb/');
const CLCOD = process.env.QA_UAT_COMPROMISO_CLCOD || process.env.QA_UAT_CLCOD || '7780380119179197';
const MONTO = process.env.QA_UAT_COMPROMISO_MONTO || '50000';
const EVIDENCE_DIR = process.env.QA_UAT_COMPROMISO_EVIDENCE_DIR ||
  path.join('evidence', 'manual', `compromiso_${CLCOD}_${timestampId()}`);

const SEL_BUSQ_CLIE = '#c_abfCodCliente';
const SEL_BUSQ_BTN = '#c_btnOk, #c_btnBuscar';
const SEL_GRID_PERSONAS = '#c_GridPersonas';
const SEL_GRID_OBLIGACIONES = '#c_GridObligaciones';
const SEL_BTN_COMPROMISOS = '#c_btnCompromisos, a:has-text("Compromisos"), button:has-text("Compromisos")';
const SEL_MODAL = '#c_dlgCompromisos';
const SEL_GRID_OBL_COMP = '#c_GridObligacionesCompromisos';
const SEL_GRID_PROMESAS = '#c_GridPromesasPago';
const SEL_PROYECCION = '#c_abfProyeccion';
const SEL_AGREGAR = '#c_btnAgregarPromesa';
const SEL_FIGURA = '#c_ddlFiguraCompromiso';
const SEL_ACCION = '#c_ddlTarCompromiso';
const SEL_GUARDAR = '#c_btnGuardarModalCompromisos';

test.describe('QA UAT smoke - crear compromiso minimo', () => {
  test('login, busqueda cliente y creacion de compromiso', async ({ page }) => {
    fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
    page.setDefaultTimeout(12_000);

    await page.goto(BASE_URL + 'FrmBusqueda.aspx', { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await assertLoggedIn(page);
    await expect(page.locator(SEL_BUSQ_CLIE)).toBeVisible({ timeout: 10_000 });
    await screenshot(page, '01_busqueda_loaded');

    await page.locator(SEL_BUSQ_CLIE).fill(CLCOD);
    await clickAndSettle(page, page.locator(SEL_BUSQ_BTN).first(), 20_000);
    await waitForRows(page, SEL_GRID_PERSONAS, 20_000, `DATA_SEARCH_RESULTS_EMPTY cliente=${CLCOD}`);
    await screenshot(page, '02_cliente_encontrado');

    const personaRow = page.locator(`${SEL_GRID_PERSONAS} tbody tr`).first();
    const personaText = await safeInnerText(personaRow);
    if (!personaText.includes(CLCOD)) {
      throw new Error(`DATA_WRONG_CLIENT_ROW expected ${CLCOD}, got: ${personaText.slice(0, 240)}`);
    }
    await clickAndSettle(page, personaRow.locator('td').first(), 20_000);
    await waitForRows(page, SEL_GRID_OBLIGACIONES, 20_000, `DATA_CLIENTE_SIN_OBLIGACIONES cliente=${CLCOD}`);
    await screenshot(page, '03_obligaciones_cargadas');

    await clickAndSettle(page, page.locator(`${SEL_GRID_OBLIGACIONES} tbody tr`).first().locator('td').first(), 25_000);
    await waitForDetalle(page);
    await screenshot(page, '04_detalle_cliente');

    await clickAndSettle(page, page.locator(SEL_BTN_COMPROMISOS).first(), 20_000);
    await waitForModalOpen(page);
    const obligationRows = await waitForRows(page, SEL_GRID_OBL_COMP, 20_000, `DATA_SIN_OBLIGACIONES_COMPROMISO cliente=${CLCOD}`);
    await screenshot(page, '05_modal_compromisos');

    const added = await addPromiseOnFirstAvailableObligation(page, obligationRows);
    await setSelectValue(page, SEL_FIGURA, 'T01', 'FIGURA_COMPROMISO');
    await setSelectValue(page, SEL_ACCION, 'CPPA', 'ACCION_COMPROMISO');
    await waitForAspNetIdle(page, 5_000);
    await screenshot(page, '08_promesa_lista_para_guardar');

    const disabled = await isDisabled(page.locator(SEL_GUARDAR));
    expect(disabled, `Guardar debe quedar habilitado despues de agregar promesa. Obligacion usada=${added.rowIndex}`).toBe(false);

    const successSeen = await saveAndWaitSuccess(page);
    await screenshot(page, '09_after_guardar');
    expect(successSeen, 'Debe aparecer confirmacion de compromiso guardado correctamente').toBe(true);
  });
});

async function addPromiseOnFirstAvailableObligation(
  page: Page,
  obligationRows: number,
): Promise<{ rowIndex: number; promRows: number }> {
  const maxRows = Math.min(obligationRows, 8);
  let lastDiagnostic = '';

  for (let rowIndex = 0; rowIndex < maxRows; rowIndex += 1) {
    const row = page.locator(`${SEL_GRID_OBL_COMP} tbody tr`).nth(rowIndex);
    await clickAndSettle(page, row.locator('td').first(), 12_000).catch(() => undefined);
    await waitForAspNetIdle(page, 8_000);

    const existingPromises = await rowCount(page, SEL_GRID_PROMESAS);
    if (existingPromises > 0) {
      lastDiagnostic = `row=${rowIndex} already has ${existingPromises} promise rows`;
      continue;
    }

    await fillProjection(page);
    await screenshot(page, `06_row_${rowIndex}_projection`);
    await clickAndSettle(page, page.locator(SEL_AGREGAR), 20_000);
    await waitForAspNetIdle(page, 12_000);

    const promRows = await rowCount(page, SEL_GRID_PROMESAS);
    const modalText = await safeInnerText(page.locator(SEL_MODAL));
    lastDiagnostic = modalText.slice(0, 500);
    await screenshot(page, `07_row_${rowIndex}_after_agregar`);

    if (promRows > 0 && !/ya existe un compromiso|debe ingresar|campo requerido/i.test(modalText)) {
      return { rowIndex, promRows };
    }
  }

  throw new Error(`APP_NO_SE_PUDO_AGREGAR_PROMESA cliente=${CLCOD}. Ultimo diagnostico: ${lastDiagnostic}`);
}

async function fillProjection(page: Page): Promise<void> {
  const input = page.locator(SEL_PROYECCION);
  await expect(input).toBeVisible({ timeout: 10_000 });
  await input.click({ force: true });
  await input.fill(MONTO);
  await input.press('Tab').catch(() => undefined);
  await page.waitForTimeout(300);
  const value = await input.inputValue().catch(() => '');
  if (!value || value === '0') {
    throw new Error(`APP_PROYECCION_NO_CARGADA expected monto=${MONTO}, got=${value}`);
  }
}

async function setSelectValue(page: Page, selector: string, preferred: string, label: string): Promise<void> {
  const result = await page.locator(selector).evaluate(
    (el: Element, preferredValue: string) => {
      const select = el as HTMLSelectElement;
      const options = Array.from(select.options).map((o) => ({ value: o.value, text: o.text }));
      const option = options.find((o) => o.value === preferredValue) ||
        options.find((o) => o.value && o.value !== '0');
      if (!option) return { ok: false, selected: null, options };
      select.value = option.value;
      select.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true, selected: option, options };
    },
    preferred,
  );
  if (!result.ok || !result.selected) {
    throw new Error(`${label}_NO_OPTION_AVAILABLE options=${JSON.stringify(result.options)}`);
  }
}

async function saveAndWaitSuccess(page: Page): Promise<boolean> {
  await page.locator(SEL_GUARDAR).click({ force: true, noWaitAfter: true, timeout: 15_000 });
  await waitForAspNetIdle(page, 15_000);
  const successPattern = /guardado.*correctamente|compromisos? de pagos se ha guardado|se ha guardado/i;
  const errorPattern = /error|critical|campo requerido|obligatorio|no se puede|ya existe/i;

  const success = await page.waitForFunction(
    (source: string) => new RegExp(source, 'i').test(document.body.innerText || ''),
    successPattern.source,
    { timeout: 10_000 },
  ).then(() => true).catch(() => false);

  if (success) return true;

  const body = await safeInnerText(page.locator('body'));
  if (errorPattern.test(body)) {
    throw new Error(`APP_GUARDAR_COMPROMISO_ERROR ${body.slice(0, 800)}`);
  }
  return false;
}

async function waitForDetalle(page: Page): Promise<void> {
  await Promise.race([
    page.waitForURL((url) => String(url).toLowerCase().includes('frmdetalleclie'), { timeout: 30_000 }),
    page.locator('#c_btnCompromisos').waitFor({ state: 'visible', timeout: 30_000 }),
  ]);
  await assertLoggedIn(page);
}

async function waitForModalOpen(page: Page): Promise<void> {
  await page.waitForFunction(
    (selector: string) => {
      const el = document.querySelector(selector) as HTMLElement | null;
      if (!el) return false;
      const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      return (visible || el.classList.contains('open')) && (el.innerText || '').length > 20;
    },
    SEL_MODAL,
    { timeout: 15_000 },
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
  return rowCount(page, gridSelector);
}

async function rowCount(page: Page, gridSelector: string): Promise<number> {
  return page.locator(`${gridSelector} tbody tr`).count().catch(() => 0);
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

async function assertLoggedIn(page: Page): Promise<void> {
  if (page.url().toLowerCase().includes('frmlogin')) {
    throw new Error(`ENV_AUTH_EXPIRED redirected to login. url=${page.url()}`);
  }
}

async function isDisabled(locator: Locator): Promise<boolean> {
  return locator.evaluate((el: Element) => {
    const anyEl = el as HTMLButtonElement;
    return !!anyEl.disabled ||
      el.classList.contains('disabled') ||
      el.classList.contains('aspNetDisabled') ||
      el.getAttribute('aria-disabled') === 'true';
  }).catch(() => true);
}

async function safeInnerText(locator: Locator): Promise<string> {
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
