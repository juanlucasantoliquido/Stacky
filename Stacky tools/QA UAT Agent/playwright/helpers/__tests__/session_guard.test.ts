/**
 * Sprint N5-03 — session_guard.test.ts
 *
 * Three behavioral cases (roadmap §5.3.5):
 *   - missing fingerprint file        → STORAGESTATE_MISSING
 *   - fingerprint older than maxAge   → STORAGESTATE_EXPIRED
 *   - fingerprint fresh               → no throw, ok=true
 */

import * as fs from 'fs';
import * as os from 'os';
import * as path from 'path';

import {
  inspectStorageState,
  verifyStorageStateValid,
} from '../session_guard';

function tmpFingerprint(content: object | null): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'n503-'));
  const fp = path.join(dir, 'agenda.fingerprint.json');
  if (content !== null) {
    fs.writeFileSync(fp, JSON.stringify(content), 'utf-8');
  }
  return fp;
}

export async function test_session_guard_missing_file() {
  const fp = tmpFingerprint(null); // not actually created
  const result = inspectStorageState(120, fp);
  if (result.ok || result.reason !== 'STORAGESTATE_MISSING') {
    throw new Error('expected STORAGESTATE_MISSING');
  }
  let threw = false;
  try {
    await verifyStorageStateValid(120, fp);
  } catch (e: any) {
    threw = true;
    if (!String(e.message).includes('STORAGESTATE_MISSING')) {
      throw new Error('expected error message to mention STORAGESTATE_MISSING');
    }
  }
  if (!threw) throw new Error('verifyStorageStateValid should have thrown');
}

export async function test_session_guard_expired() {
  // 3 hours in the past
  const created = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString();
  const fp = tmpFingerprint({ fingerprint: 'abc', created_at: created, user: 'qauser' });
  const result = inspectStorageState(120, fp);
  if (result.ok || result.reason !== 'STORAGESTATE_EXPIRED') {
    throw new Error(`expected STORAGESTATE_EXPIRED, got ${result.reason}`);
  }
  let threw = false;
  try {
    await verifyStorageStateValid(120, fp);
  } catch (e: any) {
    threw = true;
    if (!String(e.message).includes('SESSION_EXPIRED')) {
      throw new Error('error must include SESSION_EXPIRED');
    }
  }
  if (!threw) throw new Error('verifyStorageStateValid should have thrown');
}

export async function test_session_guard_valid() {
  const created = new Date(Date.now() - 10 * 60 * 1000).toISOString(); // 10m
  const fp = tmpFingerprint({ fingerprint: 'abc', created_at: created, user: 'qauser' });
  const result = inspectStorageState(120, fp);
  if (!result.ok) throw new Error(`expected ok=true, got ${JSON.stringify(result)}`);
  await verifyStorageStateValid(120, fp); // must not throw
}
