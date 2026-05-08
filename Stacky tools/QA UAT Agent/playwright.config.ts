import { defineConfig, devices } from '@playwright/test';

/**
 * playwright.config.ts — Configuración de Playwright para el pipeline QA UAT
 *
 * Credenciales leídas exclusivamente de variables de entorno.
 * NUNCA hardcodear usuarios/passwords aquí.
 *
 * Variables requeridas:
 *   AGENDA_WEB_BASE_URL  — URL base del Agenda Web (default: http://localhost:35017/AgendaWeb/)
 *   AGENDA_WEB_USER      — Usuario de login (ej: PABLO)
 *   AGENDA_WEB_PASS      — Password de login
 *
 * Variables opcionales:
 *   STACKY_QA_UAT_HEADLESS      — 1=headless (default), 0=headed
 *   STACKY_QA_UAT_SLOW_MO       — milisegundos de pausa entre acciones (default: 0).
 *   QA_UAT_MAX_TOTAL_MINUTES    — minutos máximos para toda la suite (default: 10)
 *   QA_UAT_MAX_BROWSER_LAUNCHES — máximo de lanzamientos de browser (default: 1)
 *   QA_UAT_MAX_LOGIN_ATTEMPTS   — máximo de intentos de login (default: 1)
 *   QA_UAT_STEP_TIMEOUT_MS      — timeout por acción individual en ms (default: 15000)
 *
 * ARQUITECTURA DE AUTH (globalSetup + storageState)
 * -------------------------------------------------
 * El login se hace UNA SOLA VEZ en playwright/global.setup.ts y se guarda
 * en .auth/agenda.json.  Cada spec restaura la sesión desde el archivo —
 * NO hay login en test.beforeEach.
 *
 * AgendaWeb debe estar LEVANTADA MANUALMENTE antes de correr QA UAT.
 * La URL canónica es: http://localhost:35017/AgendaWeb/
 * QA UAT Agent NUNCA inicia ni detiene IIS Express ni Visual Studio.
 */

const headless = process.env.STACKY_QA_UAT_HEADLESS !== '0';
const baseURL = process.env.AGENDA_WEB_BASE_URL ?? 'http://localhost:35017/AgendaWeb/';
const slowMo = parseInt(process.env.STACKY_QA_UAT_SLOW_MO ?? '0', 10);
const maxTotalMinutes = parseInt(process.env.QA_UAT_MAX_TOTAL_MINUTES ?? '10', 10);
const stepTimeoutMs = parseInt(process.env.QA_UAT_STEP_TIMEOUT_MS ?? '15000', 10);

export default defineConfig({
  testDir: './evidence',
  testMatch: '**/*.spec.ts',

  // Un solo lanzamiento de browser por ejecución — sin paralelismo.
  workers: 1,
  fullyParallel: false,

  // Sin reintentos — el dossier registra el resultado real de cada spec.
  retries: 0,

  // globalSetup: login único al inicio de la suite.
  // Guarda la sesión en .auth/agenda.json para que todos los specs la reutilicen.
  // Si el archivo tiene menos de 30 minutos, se omite el login (caché de auth).
  globalSetup: './playwright/global.setup',

  reporter: [
    ['list'],
    ['json', { outputFile: 'evidence/.playwright-report.json' }],
  ],

  use: {
    baseURL,
    headless,
    launchOptions: {
      slowMo,
    },
    // Auth restaurada desde globalSetup — no hay login en specs.
    storageState: '.auth/agenda.json',
    // Capturar evidencia siempre
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    screenshot: 'on',
    // Timeout por acción individual (configurable via QA_UAT_STEP_TIMEOUT_MS)
    actionTimeout: stepTimeoutMs,
    // Timeout de navegación
    navigationTimeout: 20_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Timeout por test = QA_UAT_MAX_TOTAL_MINUTES * 60s dividido por estimación de tests.
  // El pipeline pasa --timeout por CLI para sobreescribir si necesita más.
  // Sin el globalSetup login overhead, 60s por test es suficiente para la mayoría.
  timeout: Math.max(60_000, maxTotalMinutes * 60_000),
});
