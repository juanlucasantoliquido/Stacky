import { defineConfig, devices } from '@playwright/test';

/**
 * playwright.config.ts — Configuración de Playwright para el pipeline QA UAT
 *
 * Credenciales leídas exclusivamente de variables de entorno.
 * NUNCA hardcodear usuarios/passwords aquí.
 *
 * Variables requeridas:
 *   AGENDA_WEB_BASE_URL  — URL base del Agenda Web (ej: http://localhost/AgendaWeb/)
 *   AGENDA_WEB_USER      — Usuario de login (ej: PABLO)
 *   AGENDA_WEB_PASS      — Password de login
 *
 * Variables opcionales:
 *   STACKY_QA_UAT_HEADLESS — 1=headless (default), 0=headed
 */

const headless = process.env.STACKY_QA_UAT_HEADLESS !== '0';
const baseURL = process.env.AGENDA_WEB_BASE_URL ?? 'http://localhost/AgendaWeb/';

export default defineConfig({
  testDir: './evidence',
  testMatch: '**/*.spec.ts',

  // MVP: sin paralelismo — ejecución en serie
  workers: 1,
  fullyParallel: false,

  // No reintentos en MVP — el dossier registra el resultado real
  retries: 0,

  reporter: [
    ['list'],
    ['json', { outputFile: 'evidence/.playwright-report.json' }],
  ],

  use: {
    baseURL,
    headless,
    // Capturar evidencia siempre — sin importar el resultado
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'on',
    // Timeout por acción individual
    actionTimeout: 10_000,
    // Timeout de navegación
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Timeout global por test (puede sobreescribirse con --timeout-ms en uat_test_runner.py).
  // 90s elegido para acomodar: login ASP.NET WebForms (~10-25s) + 2-3 navegaciones a
  // FrmAgenda.aspx (~5-15s c/u) + acciones encadenadas + screenshots por paso.
  // El budget anterior de 30s reventaba en P01/P05 por carrera login + nav, no por
  // bug de producto. Para tests donde el escenario es realmente lento, pasar
  // --timeout-ms en CLI (uat_test_runner / qa_uat_pipeline).
  timeout: 90_000,
});
