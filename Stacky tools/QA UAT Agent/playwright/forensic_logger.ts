/**
 * playwright/forensic_logger.ts — Escritor de eventos forenses desde Playwright.
 *
 * Escribe eventos al archivo JSONL definido por QA_UAT_FORENSIC_RUN_DIR.
 * Si la variable no está seteada, los eventos se omiten silenciosamente.
 *
 * Archivos de salida:
 *   ${QA_UAT_FORENSIC_RUN_DIR}/playwright/actions.jsonl
 *   ${QA_UAT_FORENSIC_RUN_DIR}/playwright/network.jsonl
 *   ${QA_UAT_FORENSIC_RUN_DIR}/playwright/console.jsonl
 *   ${QA_UAT_FORENSIC_RUN_DIR}/playwright/screenshots.jsonl
 *
 * Schema de evento (alineado con event_schema.py v1.0):
 * {
 *   "ts": "ISO8601",
 *   "run_id": "uat-70-...",
 *   "ticket_id": 70,
 *   "scenario_id": "P01",
 *   "source": "playwright",
 *   "event_type": "playwright.goto.completed",
 *   "category": "page_goto",
 *   "stage": "runner",
 *   "action": "goto",
 *   "status": "completed",
 *   "level": "info",
 *   "step_id": "step_001",
 *   "selector": null,
 *   "url_before": "...",
 *   "url_after": "...",
 *   "started_at": "...",
 *   "finished_at": "...",
 *   "duration_ms": 1234,
 *   "error": null,
 *   "payload": {},
 *   "artifact_refs": []
 * }
 */

import * as fs from 'fs';
import * as path from 'path';
import * as crypto from 'crypto';

// ── Config ────────────────────────────────────────────────────────────────────

const RUN_DIR: string | undefined = process.env.QA_UAT_FORENSIC_RUN_DIR;
const RUN_ID: string = process.env.QA_UAT_FORENSIC_RUN_ID ?? 'unknown';
const TICKET_ID: string = process.env.QA_UAT_FORENSIC_TICKET_ID ?? '0';

// ── Paths ─────────────────────────────────────────────────────────────────────

function getPwDir(): string | null {
  if (!RUN_DIR) return null;
  const d = path.join(RUN_DIR, 'playwright');
  try {
    fs.mkdirSync(d, { recursive: true });
  } catch (_) { /* ignore */ }
  return d;
}

const PW_DIR: string | null = getPwDir();

// ── Sequence counter ───────────────────────────────────────────────────────────

let _seq = 0;
function nextSeq(): number { return ++_seq; }

// ── Core writer ───────────────────────────────────────────────────────────────

function _utcnow(): string {
  return new Date().toISOString().replace(/(\.\d{3})\d*Z/, '$1Z');
}

function _writeEvent(file: string, event: Record<string, unknown>): void {
  if (!PW_DIR) return;
  try {
    const line = JSON.stringify(event) + '\n';
    fs.appendFileSync(path.join(PW_DIR, file), line, 'utf8');
  } catch (_) { /* never throw from logger */ }
}

// ── Public API ─────────────────────────────────────────────────────────────────

export interface ActionEvent {
  scenario_id: string;
  step_id?: string;
  action: string;
  category: string;
  selector?: string | null;
  url_before?: string | null;
  url_after?: string | null;
  started_at?: string;
  finished_at?: string;
  duration_ms?: number;
  status: 'intent' | 'completed' | 'failed';
  error?: string | null;
  payload?: Record<string, unknown>;
  artifact_refs?: string[];
}

export function logAction(evt: ActionEvent): void {
  const record: Record<string, unknown> = {
    seq: nextSeq(),
    ts: _utcnow(),
    run_id: RUN_ID,
    ticket_id: TICKET_ID,
    scenario_id: evt.scenario_id,
    source: 'playwright',
    event_type: `playwright.${evt.action}.${evt.status}`,
    category: evt.category,
    stage: 'runner',
    action: evt.action,
    status: evt.status,
    level: evt.status === 'failed' ? 'error' : 'info',
    step_id: evt.step_id ?? null,
    selector: _redactSelector(evt.selector ?? null),
    url_before: evt.url_before ?? null,
    url_after: evt.url_after ?? null,
    started_at: evt.started_at ?? null,
    finished_at: evt.finished_at ?? null,
    duration_ms: evt.duration_ms ?? null,
    error: evt.error ?? null,
    payload: evt.payload ?? {},
    artifact_refs: evt.artifact_refs ?? [],
  };
  _writeEvent('actions.jsonl', record);
}

export interface NetworkEvent {
  scenario_id: string;
  method: string;
  url: string;
  status?: number | null;
  resource_type?: string;
  duration_ms?: number;
  failure?: string | null;
  request_headers?: Record<string, string>;
  response_headers?: Record<string, string>;
  event_kind: 'request' | 'response' | 'failure';
}

export function logNetwork(evt: NetworkEvent): void {
  const record: Record<string, unknown> = {
    seq: nextSeq(),
    ts: _utcnow(),
    run_id: RUN_ID,
    ticket_id: TICKET_ID,
    scenario_id: evt.scenario_id,
    source: 'browser_network',
    event_type: `network.${evt.event_kind}`,
    category: evt.event_kind === 'request' ? 'network_request' : 'network_response',
    stage: 'runner',
    method: evt.method,
    url: _redactUrl(evt.url),
    status: evt.status ?? null,
    resource_type: evt.resource_type ?? null,
    duration_ms: evt.duration_ms ?? null,
    failure: evt.failure ?? null,
    request_headers: _redactHeaders(evt.request_headers ?? {}),
    response_headers: _redactHeaders(evt.response_headers ?? {}),
  };
  _writeEvent('network.jsonl', record);
}

export interface ConsoleEvent {
  scenario_id: string;
  console_type: string;
  text: string;
  location?: string;
  is_error?: boolean;
}

export function logConsole(evt: ConsoleEvent): void {
  const record: Record<string, unknown> = {
    seq: nextSeq(),
    ts: _utcnow(),
    run_id: RUN_ID,
    ticket_id: TICKET_ID,
    scenario_id: evt.scenario_id,
    source: 'browser_console',
    event_type: evt.is_error ? 'browser.pageerror' : 'browser.console',
    category: 'console_log',
    stage: 'runner',
    console_type: evt.console_type,
    text: evt.text.slice(0, 500),
    location: evt.location ?? null,
    is_error: evt.is_error ?? false,
  };
  _writeEvent('console.jsonl', record);
}

export interface ScreenshotEvent {
  scenario_id: string;
  step_id?: string;
  path: string;
  reason: 'scenario_start' | 'failure' | 'blocker' | 'step' | 'final';
  sha256?: string;
  size_bytes?: number;
}

export function logScreenshot(evt: ScreenshotEvent): void {
  const record: Record<string, unknown> = {
    seq: nextSeq(),
    ts: _utcnow(),
    run_id: RUN_ID,
    ticket_id: TICKET_ID,
    scenario_id: evt.scenario_id,
    source: 'playwright',
    event_type: 'playwright.screenshot.captured',
    category: 'page_screenshot',
    stage: 'runner',
    step_id: evt.step_id ?? null,
    screenshot_path: evt.path,
    reason: evt.reason,
    sha256: evt.sha256 ?? null,
    size_bytes: evt.size_bytes ?? null,
  };
  _writeEvent('screenshots.jsonl', record);
}

// ── Redaction helpers ─────────────────────────────────────────────────────────

const SENSITIVE_HEADER_NAMES = new Set([
  'authorization', 'cookie', 'set-cookie', 'proxy-authorization',
  'x-api-key', 'x-auth-token', 'x-access-token',
]);

function _redactHeaders(headers: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(headers)) {
    out[k] = SENSITIVE_HEADER_NAMES.has(k.toLowerCase()) ? '***REDACTED***' : v;
  }
  return out;
}

function _redactSelector(sel: string | null): string | null {
  if (!sel) return sel;
  // Redact fill values embedded in selectors (unlikely but defensive)
  return sel.slice(0, 300);
}

function _redactUrl(url: string): string {
  // Remove password from URL if present (http://user:pass@host)
  try {
    const u = new URL(url);
    if (u.password) u.password = '***REDACTED***';
    return u.toString();
  } catch (_) {
    return url.slice(0, 500);
  }
}

// ── SHA256 helper (for screenshots) ──────────────────────────────────────────

export function sha256File(filePath: string): string | null {
  try {
    const buf = fs.readFileSync(filePath);
    return crypto.createHash('sha256').update(buf).digest('hex');
  } catch (_) {
    return null;
  }
}

export function fileSizeBytes(filePath: string): number | null {
  try {
    return fs.statSync(filePath).size;
  } catch (_) {
    return null;
  }
}
