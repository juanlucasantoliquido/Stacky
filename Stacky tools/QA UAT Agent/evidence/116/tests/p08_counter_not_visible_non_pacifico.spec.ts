/**
 * p08_counter_not_visible_non_pacifico.spec.ts
 * P08 — CA-08: El contador "Promesas a Vencer en 7 días" NO debe aparecer
 * para un usuario de instancia estándar (no Pacifico).
 *
 * Usuario primario: PABLO (PEEMPRESA=0001 — no es instancia Pacifico)
 * Playbook: frmagenda_resumen_actividad
 * Target screen: FrmAgenda.aspx
 * Oracle: counter_visible === false
 *
 * REGLA: este spec NO hace login. La sesión la provee global.setup.ts via storageState.
 * REGLA: no contiene password, usuario hardcodeado ni force:true.
 */
import { test, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

const BASE_URL = (process.env.AGENDA_WEB_BASE_URL ?? 'http://localhost:35017/AgendaWeb/').replace(/\/$/, '') + '/';
const EVIDENCE_DIR = path.resolve(__dirname, '..', 'P08');

test.use({
  storageState: '.auth/agenda.json',
});

test('P08 — CA-08 — Contador NO visible para usuario no-Pacifico', async ({ page }) => {

  // ── Step 1: Navigate to FrmAgenda.aspx ─────────────────────────────────
  await page.goto(BASE_URL + 'FrmAgenda.aspx', { waitUntil: 'load', timeout: 20000 });
  await page.waitForLoadState('domcontentloaded');

  const currentUrl = page.url();

  // ── Step 2: Verify we are on the correct screen ─────────────────────────
  expect(currentUrl).toContain('FrmAgenda');

  // ── Step 3: Screenshot inicial ──────────────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE_DIR, 'P08-01-initial.png'), fullPage: false });

  // ── Step 4: Check barraResumen present (standard counters) ──────────────
  const barraCount = await page.locator('.barraResumen').count();
  const barraFound = barraCount > 0;

  let barraHtml = '';
  if (barraFound) {
    barraHtml = await page.locator('.barraResumen').first().innerHTML();
  }

  // ── Step 5: Check counter NOT visible ───────────────────────────────────
  // The specific counter for Pacifico should NOT appear for non-Pacifico users
  const counterByText = await page.getByText(/Promesas.*Vencer/i).count();
  const counterByText2 = await page.locator('text=/Promesas a Vencer/i').count();
  const counterVisible = counterByText > 0 || counterByText2 > 0;

  // ── Step 6: Screenshot counter state ───────────────────────────────────
  await page.screenshot({ path: path.join(EVIDENCE_DIR, 'P08-02-counter-check.png'), fullPage: false });

  // ── Step 7: Write barraResumen HTML for forensics ───────────────────────
  fs.writeFileSync(path.join(EVIDENCE_DIR, 'barraResumen.html'), barraHtml || '(not found)', 'utf8');

  // ── Step 8: Write assertions JSON ───────────────────────────────────────
  const assertions = {
    scenario: 'P08',
    ca: 'CA-08',
    run_id: 'uat-116-20260508-002',
    primary_user: process.env.AGENDA_WEB_USER ?? '(not set)',
    url: currentUrl,
    barra_found: barraFound,
    counter_visible: counterVisible,
    expected_counter_visible: false,
    pass: !counterVisible,
    oracle: 'counter_visible === false (user is NOT Pacifico instance)',
  };
  fs.writeFileSync(path.join(EVIDENCE_DIR, 'assertions_P08.json'), JSON.stringify(assertions, null, 2), 'utf8');

  // ── Step 9: Assert counter NOT visible ──────────────────────────────────
  expect(counterVisible, `Counter "Promesas a Vencer" should NOT be visible for non-Pacifico user (${assertions.primary_user})`).toBe(false);
});
