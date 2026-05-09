/**
 * p09_readonly_fields.spec.ts — ADO-119 | P09 | CA-09
 * Ambos campos (Corredor Principal y Riesgo de Cliente) son de solo lectura para cualquier perfil.
 *
 * Cliente: MONTEZUMA (CLCOD 4127924112345393) — perfil gestor PACIFICO
 * Oracle: abfCorredorPrincipal.isEditable()=false, abfRiesgoCliente.isEditable()=false
 * NO contiene lógica de login — auth desde .auth/agenda.json (globalSetup)
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { navigateToDetalleClie, CLCOD_MONTEZUMA } from './nav_helper';

const RUN_ID   = `20260508-qa119-v5-${new Date().toTimeString().replace(/[^0-9]/g, '').slice(0, 6)}`;
const EVIDENCE = path.resolve(__dirname, '..', 'P09');
const SCENARIO = 'P09';
const CA       = 'CA-09';

test.use({ storageState: '.auth/agenda.json' });

test(`${SCENARIO} — ${CA} — Corredor Principal y Riesgo de Cliente son de solo lectura`, async ({ page }) => {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  // ── Step 1: Navigate ────────────────────────────────────────────────────
  await navigateToDetalleClie(page, CLCOD_MONTEZUMA);
  const currentUrl = page.url();
  expect(currentUrl).toContain('FrmDetalleClie');

  // ── Step 2: Screenshot inicial ──────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P09_01_initial.png`), fullPage: false });

  // ── Step 3: Verificar readonly — abfCorredorPrincipal ───────────────────
  const corredor   = page.locator('#c_abfCorredorPrincipal');
  const corredorOk = await corredor.count() > 0;
  let corredorEditable = true;
  let corredorReadonly = false;
  let corredorValue    = '';

  if (corredorOk) {
    corredorEditable = await corredor.isEditable();
    corredorReadonly = !corredorEditable;
    try { corredorValue = await corredor.inputValue(); } catch { corredorValue = ''; }
    // Also check 'readonly' attribute as alternative indicator
    const roAttr = await corredor.getAttribute('readonly');
    if (roAttr !== null) corredorReadonly = true;
  }

  // ── Step 4: Verificar readonly — abfRiesgoCliente ─────────────────────
  const riesgo   = page.locator('#c_abfRiesgoCliente');
  const riesgoOk = await riesgo.count() > 0;
  let riesgoEditable = true;
  let riesgoReadonly = false;
  let riesgoValue    = '';

  if (riesgoOk) {
    riesgoEditable = await riesgo.isEditable();
    riesgoReadonly = !riesgoEditable;
    try { riesgoValue = await riesgo.inputValue(); } catch { riesgoValue = ''; }
    const roAttr = await riesgo.getAttribute('readonly');
    if (roAttr !== null) riesgoReadonly = true;
  }

  // ── Step 5: Screenshot con estado de campos ──────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P09_02_readonly.png`), fullPage: false });

  // ── Step 6: Assertions JSON ─────────────────────────────────────────────
  const assertions = {
    scenario: SCENARIO, ca: CA, run_id: RUN_ID,
    clcod: CLCOD_MONTEZUMA, url: currentUrl,
    corredor_found: corredorOk, corredor_readonly: corredorReadonly,
    corredor_editable: corredorEditable, corredor_value: corredorValue,
    riesgo_found: riesgoOk, riesgo_readonly: riesgoReadonly,
    riesgo_editable: riesgoEditable, riesgo_value: riesgoValue,
    pass: corredorOk && corredorReadonly && riesgoOk && riesgoReadonly,
    oracle: 'abfCorredorPrincipal y abfRiesgoCliente son de solo lectura (isEditable=false o readonly attr)',
  };
  fs.writeFileSync(path.join(EVIDENCE, `assertions_${SCENARIO}.json`), JSON.stringify(assertions, null, 2), 'utf8');

  // ── Step 7: Asserts ─────────────────────────────────────────────────────
  expect(corredorOk, `${SCENARIO}: #c_abfCorredorPrincipal debe existir en DOM`).toBe(true);
  expect(corredorReadonly,
    `${SCENARIO}: #c_abfCorredorPrincipal debe ser de solo lectura (isEditable=false o attr readonly). Editable: ${corredorEditable}`
  ).toBe(true);

  expect(riesgoOk, `${SCENARIO}: #c_abfRiesgoCliente debe existir en DOM`).toBe(true);
  expect(riesgoReadonly,
    `${SCENARIO}: #c_abfRiesgoCliente debe ser de solo lectura (isEditable=false o attr readonly). Editable: ${riesgoEditable}`
  ).toBe(true);
});
