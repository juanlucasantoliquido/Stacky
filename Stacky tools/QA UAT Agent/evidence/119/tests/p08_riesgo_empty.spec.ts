/**
 * p08_riesgo_empty.spec.ts — ADO-119 | P08 | CA-08
 * Lote sin clasificación de riesgo: campo Riesgo de Cliente vacío, sin error.
 *
 * Cliente: APELLIDO DE TEST (CLCOD 1000001118137685)
 *   - CLRIESGOSIS = NULL en RCLIE
 *   - abfRiesgoCliente.Value = ""
 *
 * Oracle: abfRiesgoCliente.visible=true, value='' (vacío o guión), pantalla sin error
 * NO contiene lógica de login — auth desde .auth/agenda.json (globalSetup)
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { navigateToDetalleClie, CLCOD_SIN_DATOS } from './nav_helper';

const RUN_ID   = `20260508-qa119-v5-${new Date().toTimeString().replace(/[^0-9]/g, '').slice(0, 6)}`;
const EVIDENCE = path.resolve(__dirname, '..', 'P08');
const SCENARIO = 'P08';
const CA       = 'CA-08';

test.use({ storageState: '.auth/agenda.json' });

test(`${SCENARIO} — ${CA} — Riesgo de Cliente vacío para lote sin CLRIESGOSIS`, async ({ page }) => {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  // ── Step 1: Navigate ────────────────────────────────────────────────────
  await navigateToDetalleClie(page, CLCOD_SIN_DATOS);
  const currentUrl = page.url();
  expect(currentUrl).toContain('FrmDetalleClie');

  // ── Step 2: Screenshot inicial ──────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P08_01_initial.png`), fullPage: false });

  // ── Step 3: Verificar no hay error de aplicación ─────────────────────────
  const errorText  = page.locator('.aisMensajeError, [id*=error], .alert-danger');
  const hasAppError = await errorText.count() > 0 && await errorText.first().isVisible().catch(() => false);

  // ── Step 4: Verificar campo abfRiesgoCliente ─────────────────────────────
  const riesgo      = page.locator('#c_abfRiesgoCliente');
  const riesgoFound = await riesgo.count() > 0;
  let riesgoVisible  = false;
  let riesgoValue    = '';

  if (riesgoFound) {
    riesgoVisible = await riesgo.isVisible();
    try { riesgoValue = await riesgo.inputValue(); } catch { riesgoValue = await riesgo.textContent() ?? ''; }
  }

  // ── Step 5: Screenshot campo ────────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P08_02_campo.png`), fullPage: false });

  // ── Step 6: Assertions JSON ─────────────────────────────────────────────
  const emptyValue = riesgoValue.trim() === '' || riesgoValue.trim() === '-';
  const assertions = {
    scenario: SCENARIO, ca: CA, run_id: RUN_ID,
    clcod: CLCOD_SIN_DATOS, url: currentUrl,
    riesgo_found: riesgoFound, riesgo_visible: riesgoVisible,
    riesgo_value: riesgoValue, has_app_error: hasAppError,
    empty_or_dash: emptyValue,
    pass: riesgoFound && riesgoVisible && emptyValue && !hasAppError,
    oracle: 'abfRiesgoCliente visible, vacío o guión, sin error de aplicación',
  };
  fs.writeFileSync(path.join(EVIDENCE, `assertions_${SCENARIO}.json`), JSON.stringify(assertions, null, 2), 'utf8');

  // ── Step 7: Asserts ─────────────────────────────────────────────────────
  expect(hasAppError, `${SCENARIO}: pantalla no debe mostrar error de aplicación`).toBe(false);
  expect(riesgoFound,   `${SCENARIO}: #c_abfRiesgoCliente debe existir en DOM`).toBe(true);
  expect(riesgoVisible, `${SCENARIO}: #c_abfRiesgoCliente debe ser visible`).toBe(true);
  expect(emptyValue, `${SCENARIO}: Riesgo de Cliente debe estar vacío o mostrar guión (sin CLRIESGOSIS). Valor actual: '${riesgoValue}'`).toBe(true);
});
