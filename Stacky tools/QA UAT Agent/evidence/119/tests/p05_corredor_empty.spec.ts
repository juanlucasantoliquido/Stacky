/**
 * p05_corredor_empty.spec.ts — ADO-119 | P05 | CA-05
 * Lote sin OGCORREDOR en ninguna obligación: campo Corredor Principal vacío, sin error.
 *
 * Cliente: APELLIDO DE TEST (CLCOD 1000001118137685)
 *   - OGCORREDOR = NULL en ambas obligaciones (V000000000218D, V000000000218P)
 *   - GetCorredorPrincipal retorna 0 filas → abfCorredorPrincipal.Value = ""
 *
 * Oracle: abfCorredorPrincipal.visible=true, value='' (vacío o guión), pantalla sin error
 * NO contiene lógica de login — auth desde .auth/agenda.json (globalSetup)
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { navigateToDetalleClie, CLCOD_SIN_DATOS } from './nav_helper';

const RUN_ID   = `20260508-qa119-v5-${new Date().toTimeString().replace(/[^0-9]/g, '').slice(0, 6)}`;
const EVIDENCE = path.resolve(__dirname, '..', 'P05');
const SCENARIO = 'P05';
const CA       = 'CA-05';

test.use({ storageState: '.auth/agenda.json' });

test(`${SCENARIO} — ${CA} — Corredor Principal vacío para lote sin OGCORREDOR`, async ({ page }) => {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  // ── Step 1: Navigate ────────────────────────────────────────────────────
  await navigateToDetalleClie(page, CLCOD_SIN_DATOS);
  const currentUrl = page.url();
  expect(currentUrl).toContain('FrmDetalleClie');

  // ── Step 2: Screenshot inicial ──────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P05_01_initial.png`), fullPage: false });

  // ── Step 3: Verificar no hay error de aplicación ─────────────────────────
  const errorText = page.locator('.aisMensajeError, [id*=error], .alert-danger');
  const errorCount = await errorText.count();
  const hasAppError = errorCount > 0 && await errorText.first().isVisible().catch(() => false);

  // ── Step 4: Verificar campo abfCorredorPrincipal ─────────────────────────
  const corredor      = page.locator('#c_abfCorredorPrincipal');
  const corredorFound = await corredor.count() > 0;
  let corredorVisible  = false;
  let corredorValue    = '';

  if (corredorFound) {
    corredorVisible = await corredor.isVisible();
    try { corredorValue = await corredor.inputValue(); } catch { corredorValue = await corredor.textContent() ?? ''; }
  }

  // ── Step 5: Screenshot campo ────────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P05_02_campo.png`), fullPage: false });

  // ── Step 6: Assertions JSON ─────────────────────────────────────────────
  const emptyValue = corredorValue.trim() === '' || corredorValue.trim() === '-';
  const assertions = {
    scenario: SCENARIO, ca: CA, run_id: RUN_ID,
    clcod: CLCOD_SIN_DATOS, url: currentUrl,
    corredor_found: corredorFound, corredor_visible: corredorVisible,
    corredor_value: corredorValue, has_app_error: hasAppError,
    empty_or_dash: emptyValue,
    pass: corredorFound && corredorVisible && emptyValue && !hasAppError,
    oracle: 'abfCorredorPrincipal visible, vacío o guión, sin error de aplicación',
  };
  fs.writeFileSync(path.join(EVIDENCE, `assertions_${SCENARIO}.json`), JSON.stringify(assertions, null, 2), 'utf8');

  // ── Step 7: Asserts ─────────────────────────────────────────────────────
  expect(hasAppError, `${SCENARIO}: pantalla no debe mostrar error de aplicación`).toBe(false);
  expect(corredorFound,   `${SCENARIO}: #c_abfCorredorPrincipal debe existir en DOM`).toBe(true);
  expect(corredorVisible, `${SCENARIO}: #c_abfCorredorPrincipal debe ser visible`).toBe(true);
  expect(emptyValue, `${SCENARIO}: Corredor Principal debe estar vacío o mostrar guión (sin OGCORREDOR). Valor actual: '${corredorValue}'`).toBe(true);
});
