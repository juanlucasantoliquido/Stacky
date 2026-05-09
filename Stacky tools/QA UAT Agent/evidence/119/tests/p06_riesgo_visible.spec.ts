/**
 * p06_riesgo_visible.spec.ts — ADO-119 | P06 | CA-06
 * Lote con clasificación de riesgo asignada: campo Riesgo de Cliente visible con valor correcto.
 *
 * Cliente: MONTEZUMA (CLCOD 4127924112345393)
 *   - CLRIESGOSIS = 'BAJO' en RCLIE
 *   - abfRiesgoCliente.Value = 'BAJO'
 *
 * Oracle: abfRiesgoCliente.visible=true, value='BAJO'
 * NO contiene lógica de login — auth desde .auth/agenda.json (globalSetup)
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { navigateToDetalleClie, CLCOD_MONTEZUMA } from './nav_helper';

const RUN_ID   = `20260508-qa119-v5-${new Date().toTimeString().replace(/[^0-9]/g, '').slice(0, 6)}`;
const EVIDENCE = path.resolve(__dirname, '..', 'P06');
const SCENARIO = 'P06';
const CA       = 'CA-06';

test.use({ storageState: '.auth/agenda.json' });

test(`${SCENARIO} — ${CA} — Riesgo de Cliente visible con clasificación correcta (MONTEZUMA)`, async ({ page }) => {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  // ── Step 1: Navigate ────────────────────────────────────────────────────
  await navigateToDetalleClie(page, CLCOD_MONTEZUMA);
  const currentUrl = page.url();
  expect(currentUrl).toContain('FrmDetalleClie');

  // ── Step 2: Screenshot inicial ──────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P06_01_initial.png`), fullPage: false });

  // ── Step 3: Verificar campo abfRiesgoCliente ─────────────────────────────
  const riesgo      = page.locator('#c_abfRiesgoCliente');
  const riesgoFound = await riesgo.count() > 0;
  let riesgoVisible  = false;
  let riesgoValue    = '';
  let riesgoReadonly = false;

  if (riesgoFound) {
    riesgoVisible  = await riesgo.isVisible();
    try { riesgoValue = await riesgo.inputValue(); } catch { riesgoValue = await riesgo.textContent() ?? ''; }
    riesgoReadonly = !(await riesgo.isEditable());
  }

  // ── Step 4: Screenshot campo ────────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P06_02_campo.png`), fullPage: false });

  // ── Step 5: Assertions JSON ─────────────────────────────────────────────
  const assertions = {
    scenario: SCENARIO, ca: CA, run_id: RUN_ID,
    clcod: CLCOD_MONTEZUMA, url: currentUrl,
    riesgo_found: riesgoFound, riesgo_visible: riesgoVisible,
    riesgo_value: riesgoValue, riesgo_readonly: riesgoReadonly,
    expected_value: 'BAJO',
    pass: riesgoFound && riesgoVisible && riesgoValue.trim() === 'BAJO',
    oracle: 'abfRiesgoCliente visible con valor BAJO para MONTEZUMA',
  };
  fs.writeFileSync(path.join(EVIDENCE, `assertions_${SCENARIO}.json`), JSON.stringify(assertions, null, 2), 'utf8');

  // ── Step 6: Asserts ─────────────────────────────────────────────────────
  expect(riesgoFound,   `${SCENARIO}: #c_abfRiesgoCliente debe existir en DOM`).toBe(true);
  expect(riesgoVisible, `${SCENARIO}: #c_abfRiesgoCliente debe ser visible`).toBe(true);
  expect(riesgoValue.trim(), `${SCENARIO}: Riesgo de Cliente debe ser 'BAJO'`).toBe('BAJO');
});
