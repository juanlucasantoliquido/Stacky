/**
 * playwright/helpers/session_guard.ts — Sprint N5-03.
 *
 * Verifies the session artifact (storageState + fingerprint) BEFORE the spec
 * attempts to navigate. Avoids the 45-second NAV_TIMEOUT charade that occurs
 * when the session is already dead and every postback redirects to FrmLogin.
 *
 * EXPECTED ARTIFACTS (written by playwright/global.setup.ts)
 * -----------------------------------------------------------
 *   .auth/agenda.json                    Playwright storageState (cookies/LS)
 *   .auth/agenda.fingerprint.json        { fingerprint, created_at, user, base_url }
 *
 * BEHAVIOR
 * --------
 *   - File missing             → throws ENV STORAGESTATE_MISSING.
 *   - File older than TTL      → throws ENV STORAGESTATE_EXPIRED.
 *   - File present and fresh   → no-op.
 *
 * The thrown Error message is structured so the runner / failure analyzer
 * can extract `category=ENV reason=…` deterministically.
 */

import * as fs from 'fs';
import * as path from 'path';

// ── Defaults ────────────────────────────────────────────────────────────────

const DEFAULT_AUTH_FILE = '.auth/agenda.fingerprint.json';

// ── Public API ──────────────────────────────────────────────────────────────

export interface SessionFingerprint {
  fingerprint?: string;
  created_at?: string;
  user?: string;
  base_url?: string;
}

export interface SessionGuardResult {
  ok: boolean;
  fingerprintPath: string;
  ageMinutes: number | null;
  maxAgeMinutes: number;
  reason: string | null;
}

/**
 * Verify the auth fingerprint is present and not older than `maxAgeMinutes`.
 *
 * Throws a structured `Error` on failure so the spec runtime crashes loud and
 * classified instead of waiting for a downstream NAV_TIMEOUT.
 */
export async function verifyStorageStateValid(
  maxAgeMinutes: number,
  authFilePath?: string,
): Promise<void> {
  const result = inspectStorageState(maxAgeMinutes, authFilePath);
  if (result.ok) return;

  if (result.reason === 'STORAGESTATE_MISSING') {
    throw new Error(
      `[SESSION_MISSING] No fingerprint at ${result.fingerprintPath}. ` +
      'Run global.setup.ts before executing specs. ' +
      'category=ENV reason=STORAGESTATE_MISSING',
    );
  }

  if (result.reason === 'STORAGESTATE_EXPIRED') {
    const age = result.ageMinutes !== null ? `${result.ageMinutes.toFixed(1)}m` : 'unknown';
    throw new Error(
      `[SESSION_EXPIRED] storageState is ${age} old (max: ${result.maxAgeMinutes}m). ` +
      'Re-run the pipeline to refresh. ' +
      'category=ENV reason=STORAGESTATE_EXPIRED',
    );
  }

  // Unparseable / corrupted file
  throw new Error(
    `[SESSION_INVALID] Could not parse fingerprint at ${result.fingerprintPath}. ` +
    `reason=${result.reason} category=ENV`,
  );
}

/**
 * Inspect the fingerprint and return a structured outcome. Pure-ish — does
 * filesystem IO but never throws. Designed for unit testing and for callers
 * that want to decide their own throwing policy.
 */
export function inspectStorageState(
  maxAgeMinutes: number,
  authFilePath?: string,
): SessionGuardResult {
  const fp = path.resolve(authFilePath || process.env.QA_UAT_AUTH_FINGERPRINT || DEFAULT_AUTH_FILE);

  if (!fs.existsSync(fp)) {
    return {
      ok: false,
      fingerprintPath: fp,
      ageMinutes: null,
      maxAgeMinutes,
      reason: 'STORAGESTATE_MISSING',
    };
  }

  let parsed: SessionFingerprint = {};
  try {
    const raw = fs.readFileSync(fp, 'utf-8');
    parsed = JSON.parse(raw) as SessionFingerprint;
  } catch (_e) {
    return {
      ok: false,
      fingerprintPath: fp,
      ageMinutes: null,
      maxAgeMinutes,
      reason: 'STORAGESTATE_UNPARSEABLE',
    };
  }

  if (!parsed || typeof parsed !== 'object' || !parsed.created_at) {
    return {
      ok: false,
      fingerprintPath: fp,
      ageMinutes: null,
      maxAgeMinutes,
      reason: 'STORAGESTATE_MISSING_CREATED_AT',
    };
  }

  const createdMs = Date.parse(parsed.created_at);
  if (isNaN(createdMs)) {
    return {
      ok: false,
      fingerprintPath: fp,
      ageMinutes: null,
      maxAgeMinutes,
      reason: 'STORAGESTATE_INVALID_CREATED_AT',
    };
  }

  const ageMinutes = (Date.now() - createdMs) / 60_000;
  if (ageMinutes < 0) {
    // Clock skew / file dated in the future — treat as suspicious but valid.
    return {
      ok: true,
      fingerprintPath: fp,
      ageMinutes,
      maxAgeMinutes,
      reason: null,
    };
  }
  if (ageMinutes > maxAgeMinutes) {
    return {
      ok: false,
      fingerprintPath: fp,
      ageMinutes,
      maxAgeMinutes,
      reason: 'STORAGESTATE_EXPIRED',
    };
  }
  return {
    ok: true,
    fingerprintPath: fp,
    ageMinutes,
    maxAgeMinutes,
    reason: null,
  };
}
