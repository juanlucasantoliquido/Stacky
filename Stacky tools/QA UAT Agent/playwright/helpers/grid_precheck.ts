/**
 * playwright/helpers/grid_precheck.ts — Grid pre-check helper for QA UAT Agent.
 *
 * PROBLEM IT SOLVES
 * -----------------
 * When a test navigates to a screen that shows a grid (e.g. GridObligaciones in
 * FrmDetalleClie.aspx), the grid may be empty because the test client has no
 * associated records. In that case Playwright would time out waiting for a row
 * to interact with, which looks like a product failure — it's not. The test data
 * state is the issue.
 *
 * SOLUTION
 * --------
 * Before any interaction with a grid, call precheckGrid(). It:
 *   1. Waits for the grid to become visible (respects QA_UAT_GRID_TIMEOUT_MS env, default 5 s).
 *   2. Counts non-empty rows (rows that don't match the "no data" text).
 *   3. Returns a structured result. If the grid is empty or not found, the caller
 *      should throw so Playwright classifies the test as BLOCKED, not FAIL.
 *   4. Optionally writes a nav_precheck_result.json file for the Python pipeline
 *      to import as a structured event in execution.jsonl.
 *
 * USAGE IN GENERATED SPECS
 * ------------------------
 *   import { precheckGrid } from '../../playwright/helpers/grid_precheck';
 *
 *   const pre = await precheckGrid(page, 'GridObligaciones', '#GridObligaciones', {
 *     outPath: 'evidence/120/P04/nav_precheck_result.json',
 *   });
 *   if (!pre.ok) {
 *     throw new Error(`[${pre.reason}] Grid '${pre.grid_alias}' no está listo: ${pre.reason}`);
 *   }
 *   // grid has rows — proceed with interaction
 *
 * REASON CODES
 * ------------
 *   GRID_EMPTY          — Grid is visible but has zero non-empty rows (no test data for client).
 *   GRID_TIMEOUT        — Grid did not become visible within timeoutMs (rendering/nav issue).
 *   SELECTOR_NOT_FOUND  — The selector matched nothing in the DOM (screen mismatch / wrong UI map).
 */

import * as fs from 'fs';
import * as path from 'path';

// ── Types ─────────────────────────────────────────────────────────────────────

export interface GridPrecheckResult {
  ok: boolean;
  verdict: 'PASS' | 'BLOCKED';
  category: 'NAV';
  /** null when ok=true */
  reason: 'GRID_EMPTY' | 'GRID_TIMEOUT' | 'SELECTOR_NOT_FOUND' | null;
  grid_alias: string;
  selector: string;
  row_count: number;
  elapsed_ms: number;
}

export interface GridPrecheckOptions {
  /**
   * Timeout for grid visibility in ms.
   * Defaults to QA_UAT_GRID_TIMEOUT_MS env var (5000 when unset).
   */
  timeoutMs?: number;
  /**
   * Text present in "no data" rows of the grid.
   * Default: "No hay datos"
   */
  emptyText?: string;
  /**
   * If set, the result is written as JSON to this path.
   * Consumed by uat_test_runner.py → emitted as nav_precheck_result event
   * in execution.jsonl.
   */
  outPath?: string;
}

// ── Main export ───────────────────────────────────────────────────────────────

/**
 * Check that a grid element exists, is visible, and has at least one non-empty row.
 *
 * @param page       Playwright Page object
 * @param gridAlias  Human-readable alias for logging (e.g. "GridObligaciones")
 * @param selector   CSS selector for the grid element (e.g. "#GridObligaciones")
 * @param opts       Optional configuration
 */
export async function precheckGrid(
  page: any,
  gridAlias: string,
  selector: string,
  opts: GridPrecheckOptions = {},
): Promise<GridPrecheckResult> {
  const timeoutMs = opts.timeoutMs ?? Number(process.env['QA_UAT_GRID_TIMEOUT_MS'] ?? 5_000);
  const emptyText = opts.emptyText ?? 'No hay datos';
  const started = Date.now();

  // Step 1: Wait for grid to be visible.
  try {
    await page.locator(selector).waitFor({ state: 'visible', timeout: timeoutMs });
  } catch (err: any) {
    const elapsed = Date.now() - started;
    const msg = String(err?.message ?? '');
    // Distinguish timeout from "element not found" (selector returns 0 matches).
    const reason: GridPrecheckResult['reason'] =
      msg.toLowerCase().includes('timeout') ? 'GRID_TIMEOUT' : 'SELECTOR_NOT_FOUND';
    const result: GridPrecheckResult = {
      ok: false,
      verdict: 'BLOCKED',
      category: 'NAV',
      reason,
      grid_alias: gridAlias,
      selector,
      row_count: 0,
      elapsed_ms: elapsed,
    };
    _writeResult(opts.outPath, result);
    return result;
  }

  // Step 2: Count non-empty rows.
  let rowCount = 0;
  try {
    rowCount = await page
      .locator(selector)
      .locator('tbody tr')
      .filter({ hasNotText: emptyText })
      .count();
  } catch (_) {
    // If row counting fails (e.g. grid renders without a <tbody>), treat as 0.
    // The grid is visible but we can't enumerate rows — safest to block.
  }

  const elapsed = Date.now() - started;
  const result: GridPrecheckResult =
    rowCount > 0
      ? {
          ok: true,
          verdict: 'PASS',
          category: 'NAV',
          reason: null,
          grid_alias: gridAlias,
          selector,
          row_count: rowCount,
          elapsed_ms: elapsed,
        }
      : {
          ok: false,
          verdict: 'BLOCKED',
          category: 'NAV',
          reason: 'GRID_EMPTY',
          grid_alias: gridAlias,
          selector,
          row_count: 0,
          elapsed_ms: elapsed,
        };

  _writeResult(opts.outPath, result);
  return result;
}

// ── Internal helpers ──────────────────────────────────────────────────────────

function _writeResult(outPath: string | undefined, result: GridPrecheckResult): void {
  if (!outPath) return;
  try {
    const dir = path.dirname(outPath);
    fs.mkdirSync(dir, { recursive: true });
    fs.writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf8');
  } catch (_) {
    // Best-effort — never fail the test because of evidence writing.
  }
}
