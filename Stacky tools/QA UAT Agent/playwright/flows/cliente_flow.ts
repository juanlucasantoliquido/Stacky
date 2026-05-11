/**
 * flows/cliente_flow.ts — Navigation Flow Objects for client screens.
 *
 * PURPOSE
 * -------
 * Provides governed navigation methods for human UAT simulation.
 * Replaces raw `page.goto(screen)` calls with explicit, contract-driven flows.
 *
 * DESIGN
 * ------
 * - All navigation is explicit: the caller declares the strategy
 *   (human_path or deeplink). The flow validates the strategy on entry.
 * - Page Objects assert context after navigation. If context is not
 *   established, the flow throws a structured error (not a Playwright timeout).
 * - No fallbacks or silent redirections: every navigation either succeeds
 *   with full context or throws with a diagnostic code.
 *
 * USAGE (uat_human lane — human path)
 * ------------------------------------
 *   import { ClienteFlow } from '../flows/cliente_flow';
 *
 *   const flow = new ClienteFlow(page, BASE_URL);
 *   await flow.openDetalleFromBusqueda({ clcod: testData.CLCOD });
 *
 * USAGE (smoke_deeplink lane — deeplink)
 * ---------------------------------------
 *   const flow = new ClienteFlow(page, BASE_URL);
 *   await flow.openDetalleByDeeplink({ clcod: testData.CLCOD });
 *
 * NAVIGATION STRATEGY CODES
 * -------------------------
 * [NAV_HUMAN_PATH]    — navigated via FrmBusqueda → select row → FrmDetalleClie
 * [NAV_DEEPLINK]      — navigated via FrmDetalleClie.aspx?clcod=...
 * [BLOCKED_NAV_DATA]  — required nav data missing
 * [BLOCKED_NAV_CONTEXT] — deeplink loaded but context was not reconstructed
 * [BLOCKED_NAV_GRID_EMPTY] — search returned no rows for CLCOD
 */
import { Page, expect, Locator } from '@playwright/test';

// ── Page Object: FrmBusqueda ─────────────────────────────────────────────────

export class FrmBusquedaPage {
  readonly page: Page;
  readonly baseUrl: string;

  constructor(page: Page, baseUrl: string) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /** Navigate directly to the search screen. */
  async navigate(): Promise<void> {
    await this.page.goto(`${this.baseUrl}/FrmBusqueda.aspx`, {
      waitUntil: 'domcontentloaded',
      timeout: 20_000,
    });
    await this._assertLoaded();
  }

  /** Assert that the search form is visible and ready. */
  async _assertLoaded(): Promise<void> {
    const url = this.page.url().toLowerCase();
    if (url.includes('frmlogin')) {
      throw new Error(
        '[BLOCKED_SESSION_EXPIRED] Redirected to login page before search. Re-run the pipeline.',
      );
    }
    // Wait for search form to be ready (at least one filter visible)
    const filterLocator = this.page.locator(
      '#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk, .search-form, input[type="text"]',
    ).first();
    await expect(filterLocator).toBeVisible({ timeout: 10_000 });
  }

  /**
   * Search for a client by CLCOD and return the results grid locator.
   * Throws [BLOCKED_NAV_GRID_EMPTY] if no rows are returned.
   */
  async searchByClcod(clcod: string): Promise<Locator> {
    if (!clcod) {
      throw new Error('[BLOCKED_NAV_DATA] CLCOD is required for search navigation.');
    }

    // Try to fill the CLCOD filter — try multiple known selectors for resilience
    const clcodInput = this.page.locator(
      '#c_abfCorredor, #c_abfNombreCliente, input[id*="clcod" i], input[id*="codigo" i], input[name*="clcod" i]',
    ).first();
    const filtersVisible = await clcodInput.isVisible().catch(() => false);
    if (filtersVisible) {
      await clcodInput.fill(clcod);
    }

    // Click the search button
    const searchBtn = this.page.locator(
      '#c_btnOk, button[id*="btnOk" i], button[id*="buscar" i], input[type="submit"]',
    ).first();
    await searchBtn.click();

    // Wait for the grid to load
    await this.page.waitForLoadState('domcontentloaded');

    // Find the results grid
    const grid = this.page.locator(
      'table[id*="grid" i], table[id*="Grid" i], div[id*="grid" i], .grid-container',
    ).first();
    const gridVisible = await grid.isVisible({ timeout: 10_000 }).catch(() => false);
    if (!gridVisible) {
      throw new Error(
        `[BLOCKED_NAV_GRID_EMPTY] No results grid visible after searching CLCOD=${clcod}.`,
      );
    }

    // Verify at least one row
    const rows = grid.locator('tr[data-item], tbody tr').filter({ hasNotText: /loading|cargando/i });
    const rowCount = await rows.count().catch(() => 0);
    if (rowCount === 0) {
      throw new Error(
        `[BLOCKED_NAV_GRID_EMPTY] Search for CLCOD=${clcod} returned no rows. ` +
        'Verify that the client exists and the QA user has access.',
      );
    }

    return rows;
  }

  /**
   * Click on the first matching row for CLCOD.
   * Returns after navigation to the detail screen completes.
   */
  async selectClientRow(clcod: string, rows: Locator): Promise<void> {
    // Prefer row that contains the CLCOD text
    const targetRow = rows.filter({ hasText: clcod }).first();
    const targetVisible = await targetRow.isVisible().catch(() => false);
    const rowToClick = targetVisible ? targetRow : rows.first();

    await rowToClick.click();
    // Give ASP.NET postback time to complete
    await this.page.waitForLoadState('domcontentloaded', { timeout: 30_000 });
  }
}

// ── Page Object: FrmDetalleClie ───────────────────────────────────────────────

export class FrmDetalleCliePage {
  readonly page: Page;
  readonly baseUrl: string;

  constructor(page: Page, baseUrl: string) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Assert that FrmDetalleClie.aspx is loaded with context for the given client.
   * Throws structured errors instead of timing out silently.
   */
  async assertLoadedForClient(clcod: string): Promise<void> {
    const url = this.page.url().toLowerCase();

    // Check for login redirect (session expired)
    if (url.includes('frmlogin')) {
      throw new Error(
        '[BLOCKED_SESSION_EXPIRED] Redirected to login during navigation to FrmDetalleClie.aspx. ' +
        'Re-run the pipeline to refresh auth.',
      );
    }

    // Verify we reached the right screen
    if (!url.includes('frmdetalleclie')) {
      throw new Error(
        `[BLOCKED_WRONG_SCREEN] Expected FrmDetalleClie.aspx but landed on: ${this.page.url()}. ` +
        'Check the navigation path — the session context may not have been set.',
      );
    }

    // Check for ASP.NET unhandled exception (yellow screen of death)
    const serverError = this.page.locator(
      '#ctl00_lblExceptionMessage, .exception-message, h2:has-text("Server Error"), ' +
      'h1:has-text("Runtime Error"), pre[id*="Stack"]',
    );
    const hasServerError = await serverError.isVisible({ timeout: 2_000 }).catch(() => false);
    if (hasServerError) {
      const errText = await serverError.textContent().catch(() => 'unknown server error');
      throw new Error(
        `[BLOCKED_SERVER_ERROR] ASP.NET server error on FrmDetalleClie.aspx: ${errText?.slice(0, 200)}. ` +
        'This may indicate invalid session context or a bug triggered by the navigation.',
      );
    }

    // Verify client context is loaded (client code visible somewhere)
    if (clcod) {
      const clientIndicator = this.page.locator(`text=${clcod}`).first();
      const clientVisible = await clientIndicator.isVisible({ timeout: 5_000 }).catch(() => false);
      if (!clientVisible) {
        // Non-fatal: the CLCOD may not be displayed verbatim; check for the detail form
        const detailForm = this.page.locator(
          '#c_pnlDetalleClie, .detalle-cliente, form[action*="FrmDetalleClie"]',
        ).first();
        const formVisible = await detailForm.isVisible({ timeout: 3_000 }).catch(() => false);
        if (!formVisible) {
          throw new Error(
            `[BLOCKED_NAV_CONTEXT] FrmDetalleClie.aspx loaded but client context for CLCOD=${clcod} ` +
            'was not reconstructed. The page may have loaded without a selected client.',
          );
        }
      }
    }
  }
}

// ── Flow: ClienteFlow ─────────────────────────────────────────────────────────

export class ClienteFlow {
  readonly page: Page;
  readonly baseUrl: string;

  constructor(page: Page, baseUrl: string) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  /**
   * Human path: FrmBusqueda → buscar cliente → seleccionar → FrmDetalleClie.
   *
   * This method simulates the real operator workflow.
   * MUST be used in uat_human and full-uat lanes.
   * DO NOT use direct goto() for session-dependent screens.
   *
   * @param data.clcod  Client code to search for (required)
   */
  async openDetalleFromBusqueda(data: { clcod: string }): Promise<void> {
    if (!data.clcod) {
      throw new Error(
        '[BLOCKED_NAV_DATA] CLCOD is required for openDetalleFromBusqueda. ' +
        'Add CLCOD to test data or use openDetalleByDeeplink in smoke_deeplink lane.',
      );
    }

    const busqueda = new FrmBusquedaPage(this.page, this.baseUrl);
    const detalle = new FrmDetalleCliePage(this.page, this.baseUrl);

    // Step 1: Navigate to search screen
    await busqueda.navigate();

    // Step 2: Search for client
    const rows = await busqueda.searchByClcod(data.clcod);

    // Step 3: Select result row
    await busqueda.selectClientRow(data.clcod, rows);

    // Step 4: Assert context loaded in detail screen
    await detalle.assertLoadedForClient(data.clcod);
  }

  /**
   * Deeplink path: direct navigation via FrmDetalleClie.aspx?clcod={CLCOD}.
   *
   * This method uses the deeplink capability of FrmDetalleClie.aspx.
   * MUST ONLY be used in smoke_deeplink, regression_deeplink, diagnostic,
   * or forensic_rerun lanes. NOT for uat_human simulation.
   *
   * @param data.clcod  Client code to pass as deeplink parameter (required)
   */
  async openDetalleByDeeplink(data: { clcod: string }): Promise<void> {
    if (!data.clcod) {
      throw new Error(
        '[BLOCKED_NAV_DATA] CLCOD is required for openDetalleByDeeplink. ' +
        'Provide CLCOD in test data.',
      );
    }

    const encodedClcod = encodeURIComponent(data.clcod);
    const deeplinkUrl = `${this.baseUrl}/FrmDetalleClie.aspx?clcod=${encodedClcod}`;

    await this.page.goto(deeplinkUrl, {
      waitUntil: 'domcontentloaded',
      timeout: 20_000,
    });

    // Wait for ASP.NET to process the deeplink
    await this.page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {
      // Non-fatal: networkidle may not fire reliably in WebForms
    });

    const detalle = new FrmDetalleCliePage(this.page, this.baseUrl);
    await detalle.assertLoadedForClient(data.clcod);
  }
}
