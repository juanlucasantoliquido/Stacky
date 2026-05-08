/**
 * auth_state_validator.ts — Validate .auth/agenda.json before running specs.
 *
 * Called optionally from globalSetup AFTER checking the cache age.
 * Performs a lightweight HTTP probe against a known authenticated page
 * to verify the session is still valid — WITHOUT opening a full browser.
 *
 * Strategy:
 *   1. Check if .auth/agenda.json exists and is < AUTH_CACHE_MINUTES old (done in global.setup.ts).
 *   2. If age is OK, do a HEAD/GET against BASE_URL+FrmAgenda.aspx with the stored cookies.
 *   3. If response redirects to FrmLogin → session expired → need re-login.
 *   4. If response is 200/302→non-login → session valid → skip login.
 *
 * This validator is used by global.setup.ts to decide whether to skip login.
 *
 * Export:
 *   validateAuthState(authFile, baseURL): Promise<AuthValidationResult>
 */

import * as fs from 'fs';
import * as http from 'http';
import * as https from 'https';
import * as url from 'url';

export interface AuthValidationResult {
  valid: boolean;
  /** Why the session was deemed valid or invalid */
  reason: 'CACHE_VALID' | 'SESSION_EXPIRED' | 'PROBE_FAILED' | 'AUTH_FILE_MISSING' | 'AUTH_FILE_STALE';
  elapsed_ms: number;
  message: string;
}

/** Minutes before the cached auth file is considered stale without probing. */
const AUTH_CACHE_MINUTES = 30;

/** Probe target — lightweight authenticated page. */
const PROBE_PATH = 'FrmAgenda.aspx';

/** HTTP timeout for the auth probe (ms). */
const PROBE_TIMEOUT_MS = 5_000;

/**
 * Validate the auth state stored in `authFile`.
 *
 * Returns a result indicating whether the session can be reused.
 * Never throws — all errors are caught and mapped to valid=false.
 */
export async function validateAuthState(
  authFile: string,
  baseURL: string,
): Promise<AuthValidationResult> {
  const t0 = Date.now();

  // ── Step 1: file existence ────────────────────────────────────────────────
  if (!fs.existsSync(authFile)) {
    return result(false, 'AUTH_FILE_MISSING', 'Auth file not found — login required.', t0);
  }

  // ── Step 2: freshness check ───────────────────────────────────────────────
  try {
    const ageSec = (Date.now() - fs.statSync(authFile).mtimeMs) / 1000;
    if (ageSec >= AUTH_CACHE_MINUTES * 60) {
      return result(false, 'AUTH_FILE_STALE',
        `Auth file is ${Math.round(ageSec)}s old (> ${AUTH_CACHE_MINUTES * 60}s). Re-login required.`, t0);
    }
  } catch (e: any) {
    return result(false, 'PROBE_FAILED', `Cannot stat auth file: ${e?.message}`, t0);
  }

  // ── Step 3: read stored cookies ───────────────────────────────────────────
  let cookies: string;
  try {
    const state = JSON.parse(fs.readFileSync(authFile, 'utf-8'));
    const cookieEntries: any[] = state?.cookies ?? [];
    cookies = cookieEntries
      .map((c: any) => `${encodeURIComponent(c.name)}=${encodeURIComponent(c.value)}`)
      .join('; ');
  } catch (e: any) {
    return result(false, 'PROBE_FAILED', `Cannot parse auth file: ${e?.message}`, t0);
  }

  if (!cookies) {
    return result(false, 'AUTH_FILE_MISSING', 'Auth file has no cookies — login required.', t0);
  }

  // ── Step 4: HTTP probe ────────────────────────────────────────────────────
  const probeURL = baseURL.replace(/\/$/, '') + '/' + PROBE_PATH;

  try {
    const probeResult = await _httpHead(probeURL, cookies, PROBE_TIMEOUT_MS);

    // Redirect to FrmLogin → session expired
    if (probeResult.redirectedToLogin) {
      return result(false, 'SESSION_EXPIRED',
        `Auth probe redirected to login page. Session expired.`, t0);
    }

    // 200 or non-login redirect → valid
    return result(true, 'CACHE_VALID',
      `Auth valid (HTTP ${probeResult.statusCode} on ${PROBE_PATH})`, t0);

  } catch (e: any) {
    // Network error — cannot determine session status. Treat as stale to be safe.
    return result(false, 'PROBE_FAILED',
      `Auth probe failed: ${e?.message ?? String(e)}`, t0);
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function result(
  valid: boolean,
  reason: AuthValidationResult['reason'],
  message: string,
  t0: number,
): AuthValidationResult {
  return { valid, reason, elapsed_ms: Date.now() - t0, message };
}

interface ProbeResult {
  statusCode: number;
  redirectedToLogin: boolean;
}

function _httpHead(targetURL: string, cookieHeader: string, timeoutMs: number): Promise<ProbeResult> {
  return new Promise((resolve, reject) => {
    const parsed = new url.URL(targetURL);
    const lib = parsed.protocol === 'https:' ? https : http;

    const req = lib.request(
      {
        method: 'GET',
        host: parsed.hostname,
        port: parsed.port || (parsed.protocol === 'https:' ? 443 : 80),
        path: parsed.pathname + parsed.search,
        headers: { Cookie: cookieHeader, Connection: 'close' },
        timeout: timeoutMs,
      },
      (res) => {
        // Drain the response body to free the socket
        res.resume();
        const locationHeader = (res.headers['location'] ?? '').toString().toLowerCase();
        const redirectedToLogin =
          (res.statusCode ?? 0) >= 300 &&
          (res.statusCode ?? 0) < 400 &&
          locationHeader.includes('frmlogin');

        resolve({ statusCode: res.statusCode ?? 0, redirectedToLogin });
      },
    );

    req.on('timeout', () => { req.destroy(); reject(new Error(`Probe timeout (${timeoutMs}ms)`)); });
    req.on('error', reject);
    req.end();
  });
}
