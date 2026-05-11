/**
 * global.setup.ts — ONE-TIME login for QA UAT Playwright suite.
 *
 * SINGLE SOURCE OF TRUTH FOR CREDENTIALS
 * ----------------------------------------
 * Credentials come EXCLUSIVELY from environment variables:
 *   AGENDA_WEB_BASE_URL   — e.g. http://localhost:35017/AgendaWeb/
 *   AGENDA_WEB_USER       — login username
 *   AGENDA_WEB_PASS       — login password
 *
 * NO credentials may appear in any .spec.ts file, template, playbook or
 * scenario JSON.  This file is the ONLY place where login occurs.
 *
 * MAX LOGIN ATTEMPTS: 1 (hard enforcement)
 * ----------------------------------------
 * If login fails, globalSetup throws immediately.
 * There is NO retry, NO alternative credential, NO fallback user.
 * If the error is "wrong password", fix the env var — do not work around it.
 *
 * CREDENTIAL FINGERPRINTING
 * -------------------------
 * The auth cache is tagged with a fingerprint derived from (user, baseURL).
 * If the fingerprint changes between runs, the cache is invalidated before
 * the validation probe — preventing stale auth from a previous user/URL.
 *
 * SAFETY NOTES:
 *   - This file NEVER manages IIS Express, Visual Studio or any process.
 *   - If login fails (AgendaWeb not running), globalSetup throws and no
 *     spec runs.  The Python preflight should have caught this earlier.
 */

import { chromium, FullConfig } from '@playwright/test';
import * as crypto from 'crypto';
import * as fs from 'fs';
import * as path from 'path';
import { validateAuthState } from './auth_state_validator';

/** Selectors for AIS-rendered login form on FrmLogin.aspx */
const LOGIN_USER_SEL  = '#c_abfUsuario';
const LOGIN_PASS_SEL  = '#c_abfContrasena';
const LOGIN_BTN_SEL   = '#c_btnOk';

/** Fingerprint file lives next to agenda.json */
const AUTH_FINGERPRINT_FILE = '.auth/agenda.fingerprint.json';

/** Compute a short credential fingerprint (user + baseURL). Never includes password. */
function _credentialFingerprint(user: string, baseURL: string): string {
  return crypto.createHash('sha256')
    .update(`${user}|${baseURL}`)
    .digest('hex')
    .slice(0, 16);
}

async function globalSetup(_config: FullConfig): Promise<void> {
  // ── STEP 1: Read and validate credentials from env ───────────────────────
  // HARD RULE: credentials come ONLY from env vars. No defaults, no fallbacks.
  const baseURL = (process.env.AGENDA_WEB_BASE_URL ?? '').replace(/\/$/, '') + '/';
  const user    = (process.env.AGENDA_WEB_USER ?? '').trim();
  const pass    = (process.env.AGENDA_WEB_PASS ?? '').trim();

  if (!process.env.AGENDA_WEB_BASE_URL) {
    throw new Error(
      '[globalSetup] BLOCKED: AGENDA_WEB_BASE_URL is not set. ' +
      'Set it to e.g. http://localhost:35017/AgendaWeb/ before running QA UAT.',
    );
  }
  if (!user) {
    throw new Error(
      '[globalSetup] BLOCKED: AGENDA_WEB_USER is not set. ' +
      'Set the correct username environment variable before running QA UAT.',
    );
  }
  if (!pass) {
    throw new Error(
      '[globalSetup] BLOCKED: AGENDA_WEB_PASS is not set. ' +
      'Set the correct password environment variable before running QA UAT.',
    );
  }

  const fingerprint = _credentialFingerprint(user, baseURL);
  console.log(`[globalSetup] Credential fingerprint: ${fingerprint} (user=${user}, url=${baseURL})`);

  // Auth file lives at <tool-root>/.auth/agenda.json
  // __dirname is <tool-root>/playwright/ so we go one level up.
  const authFile        = path.join(__dirname, '..', '.auth', 'agenda.json');
  const fingerprintFile = path.join(__dirname, '..', AUTH_FINGERPRINT_FILE);
  fs.mkdirSync(path.dirname(authFile), { recursive: true });

  // ── STEP 2: Fingerprint check — invalidate cache if credentials changed ──
  // This prevents stale auth from a previous user/URL contaminating the run.
  if (fs.existsSync(authFile) && fs.existsSync(fingerprintFile)) {
    try {
      const stored = JSON.parse(fs.readFileSync(fingerprintFile, 'utf8'));
      if (stored.fingerprint !== fingerprint) {
        console.log(
          `[globalSetup] Credential fingerprint changed (${stored.fingerprint} → ${fingerprint}). ` +
          'Invalidating auth cache.',
        );
        fs.unlinkSync(authFile);
        fs.unlinkSync(fingerprintFile);
      }
    } catch (_) {
      // Corrupt fingerprint file — invalidate both
      try { fs.unlinkSync(authFile); } catch (_) {}
      try { fs.unlinkSync(fingerprintFile); } catch (_) {}
    }
  } else if (fs.existsSync(authFile) && !fs.existsSync(fingerprintFile)) {
    // Auth cache without fingerprint (pre-hardening) — invalidate to be safe
    console.log('[globalSetup] No fingerprint found for existing auth cache — invalidating.');
    try { fs.unlinkSync(authFile); } catch (_) {}
  }

  // ── STEP 3: Cache check: validate existing auth via HTTP probe ───────────
  if (fs.existsSync(authFile)) {
    const validation = await validateAuthState(authFile, baseURL);
    if (validation.valid) {
      console.log(
        `[globalSetup] Auth still valid (${validation.reason}, ${validation.elapsed_ms}ms). Skipping login.`,
      );
      return;
    }
    console.log(`[globalSetup] Auth invalid: ${validation.reason} — ${validation.message}`);
    // Remove stale auth file before attempting fresh login
    try { fs.unlinkSync(authFile); } catch (_) {}
    try { fs.unlinkSync(fingerprintFile); } catch (_) {}
  }

  // ── STEP 4: Real login — MAX 1 ATTEMPT, NO RETRY ─────────────────────────
  // If this fails for any reason (wrong password, server down, selector
  // changed), globalSetup throws and Playwright aborts all specs.
  // Do NOT add retry logic here. Fix the credentials or the server.
  console.log(`[globalSetup] Logging into ${baseURL}FrmLogin.aspx (attempt 1/1) ...`);

  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext();
    const page    = await context.newPage();

    const loginURL = `${baseURL}FrmLogin.aspx`;
    await page.goto(loginURL, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    await page.fill(LOGIN_USER_SEL, user,  { timeout: 10_000 });
    await page.fill(LOGIN_PASS_SEL, pass);
    await page.locator(LOGIN_BTN_SEL).click({ noWaitAfter: true });

    // Wait for redirect away from FrmLogin.aspx (successful auth).
    // If this times out, the credentials are wrong or the server is down.
    // There is NO retry — the error message is final.
    let loginSucceeded = false;
    try {
      await page.waitForURL(/FrmAgenda|FrmMain/, { timeout: 25_000 });
      await page.waitForLoadState('domcontentloaded', { timeout: 15_000 });
      loginSucceeded = !page.url().toLowerCase().includes('frmlogin');
    } catch (waitErr) {
      // Timeout or navigation error — still on login page
      loginSucceeded = false;
    }

    if (!loginSucceeded) {
      // HARD FAIL — 1 attempt exhausted. Do not retry.
      throw new Error(
        `[globalSetup] BLOCKED_LOGIN_FAILED — Login failed on the single allowed attempt. ` +
        `Current URL: ${page.url()}. ` +
        'Fix AGENDA_WEB_USER / AGENDA_WEB_PASS and retry. ' +
        'login_count=1, retry=false.',
      );
    }

    // Persist auth state
    await context.storageState({ path: authFile });

    // Persist credential fingerprint alongside the auth file
    fs.writeFileSync(fingerprintFile, JSON.stringify({
      fingerprint,
      user,
      base_url: baseURL,
      created_at: new Date().toISOString(),
    }, null, 2), 'utf8');

    console.log(`[globalSetup] Auth saved → ${authFile} (fingerprint: ${fingerprint})`);
  } finally {
    await browser.close();
  }
}

export default globalSetup;
