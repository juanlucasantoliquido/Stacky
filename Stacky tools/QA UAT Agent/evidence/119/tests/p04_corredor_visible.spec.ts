/**
 * p04_corredor_visible.spec.ts — ADO-119 | P04 | CA-04
 * Lote con una sola obligación con OGCORREDOR asignado: campo Corredor Principal visible con ese valor.
 *
 * Cliente: MONTEZUMA (CLCOD 4127924112345393)
 *   - OGCORREDOR = 'Corredor 1' (obligación MOR0024967 / MOR0026973)
 *   - GetCorredorPrincipal retorna 'Corredor 1'
 *
 * Oracle: abfCorredorPrincipal.visible=true, value='Corredor 1'
 * NO contiene lógica de login — auth desde .auth/agenda.json (globalSetup)
 * REGLA: sin credenciales hardcodeadas.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';
import { navigateToDetalleClie, BASE_URL, CLCOD_MONTEZUMA } from './nav_helper';

const RUN_ID     = `20260508-qa119-v5-${new Date().toTimeString().replace(/[^0-9]/g, '').slice(0, 6)}`;
const EVIDENCE   = path.resolve(__dirname, '..', 'P04');
const SCENARIO   = 'P04';
const CA         = 'CA-04';

test.use({ storageState: '.auth/agenda.json' });

test(`${SCENARIO} — ${CA} — Corredor Principal visible con valor correcto (MONTEZUMA)`, async ({ page }) => {
  // Ensure evidence dir exists
  fs.mkdirSync(EVIDENCE, { recursive: true });

  // ── Step 1: Navigate to FrmDetalleClie for MONTEZUMA ───────────────────
  await navigateToDetalleClie(page, CLCOD_MONTEZUMA);
  const currentUrl = page.url();
  expect(currentUrl).toContain('FrmDetalleClie');

  // ── Step 2: Screenshot inicial ──────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P04_01_initial.png`), fullPage: false });

  // ── Step 3: Verificar campo abfCorredorPrincipal ─────────────────────────
  const corredor = page.locator('#c_abfCorredorPrincipal');
  const corredorCount = await corredor.count();
  const corredorFound = corredorCount > 0;
  let corredorVisible = false;
  let corredorValue   = '';
  let corredorReadonly = false;

  if (corredorFound) {
    corredorVisible  = await corredor.isVisible();
    try { corredorValue = await corredor.inputValue(); } catch { corredorValue = await corredor.textContent() ?? ''; }
    corredorReadonly = !(await corredor.isEditable());
  }

  // ── Step 4: Screenshot campo ────────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE, `${RUN_ID}_P04_02_campo.png`), fullPage: false });

  // ── Step 5: Assertions JSON ─────────────────────────────────────────────
  const assertions = {
    scenario: SCENARIO, ca: CA, run_id: RUN_ID,
    clcod: CLCOD_MONTEZUMA, url: currentUrl,
    corredor_found: corredorFound, corredor_visible: corredorVisible,
    corredor_value: corredorValue, corredor_readonly: corredorReadonly,
    expected_value: 'Corredor 1',
    pass: corredorFound && corredorVisible && corredorValue.trim() === 'Corredor 1',
    oracle: 'abfCorredorPrincipal visible con valor Corredor 1 para MONTEZUMA',
  };
  fs.writeFileSync(path.join(EVIDENCE, `assertions_${SCENARIO}.json`), JSON.stringify(assertions, null, 2), 'utf8');

  // ── Step 6: Asserts ─────────────────────────────────────────────────────
  expect(corredorFound,   `${SCENARIO}: #c_abfCorredorPrincipal debe existir en DOM`).toBe(true);
  expect(corredorVisible, `${SCENARIO}: #c_abfCorredorPrincipal debe ser visible`).toBe(true);
  expect(corredorValue.trim(), `${SCENARIO}: Corredor Principal debe ser 'Corredor 1'`).toBe('Corredor 1');
});
