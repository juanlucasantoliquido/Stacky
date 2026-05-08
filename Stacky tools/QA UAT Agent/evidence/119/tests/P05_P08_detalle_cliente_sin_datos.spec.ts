// ADO-119 P05+P08 — Corredor Principal y Riesgo de Cliente vacíos (lote sin datos)
// Generated for QA UAT by UserInterfaceQA2.0 — 2026-05-08
// Auth: restored from .auth/agenda.json (set by global.setup.ts — no login here)
// Playbook: busqueda_detalle_cliente — navigate via FrmAgenda first available row
// Screen: FrmDetalleClie.aspx
// Data: any lote accessible to PABLO that is NOT 4127924112345393 (no OGCORREDOR/CLRIESGOSIS)

import { test, expect } from "@playwright/test";

const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
if (!BASE_URL) throw new Error("AGENDA_WEB_BASE_URL env var is required");

// Navigate to FrmDetalleClie via FrmAgenda (first available row in user agenda)
// This gives us a lote different from 4127924112345393 (which is the only one with data)
async function navViaAgenda(page: any): Promise<boolean> {
  await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 15000 });

  // Try GridAgendaUsu rows first
  for (const gridSel of ["#c_GridAgendaUsu", "#c_GridAgendaAut"]) {
    const rows = page.locator(`${gridSel} tbody tr`);
    const cnt = await rows.count();
    if (cnt > 0) {
      // Click avanzar button if present
      const avanzar = page.locator("#c_btnAvanzar");
      if (await avanzar.count() > 0 && await avanzar.isVisible()) {
        await avanzar.click({ noWaitAfter: true });
        try {
          await page.waitForURL(/FrmDetalleClie/, { timeout: 12000 });
          await page.waitForLoadState("load", { timeout: 15000 });
          if (page.url().includes("FrmDetalleClie") ||
              (await page.locator("#c_abfApellidoNombre").count()) > 0) {
            return true;
          }
        } catch { /* continue */ }
      }

      // Otherwise click first grid row
      try {
        await rows.first().click({ noWaitAfter: true });
        await page.waitForLoadState("load", { timeout: 15000 });
        if (page.url().includes("FrmDetalleClie") ||
            (await page.locator("#c_abfApellidoNombre").count()) > 0) {
          return true;
        }
      } catch { /* continue */ }
    }
  }

  // Fallback: FrmBusqueda empty search
  await page.goto(`${BASE_URL}FrmBusqueda.aspx`, { waitUntil: "load" });
  await page.locator("#c_btnOk").click({ noWaitAfter: true });
  await page.waitForLoadState("load", { timeout: 20000 });
  const rows2 = page.locator("#c_GridPersonas tbody tr");
  if (await rows2.count() > 0) {
    await rows2.first().click({ noWaitAfter: true });
    await page.waitForLoadState("load", { timeout: 15000 });
    const gridOblig = page.locator("#c_GridObligaciones tbody tr");
    if (await gridOblig.count() > 0) {
      await gridOblig.first().click({ noWaitAfter: true });
      try { await page.waitForURL(/FrmDetalleClie/, { timeout: 12000 }); } catch { /* ok */ }
      await page.waitForLoadState("load", { timeout: 15000 });
    }
    return (await page.locator("#c_abfApellidoNombre").count()) > 0;
  }
  return false;
}

test.describe("ADO-119 P05 — Corredor Principal vacio para lote sin OGCORREDOR", () => {
  test("p05 corredor_principal_vacio_sin_error", async ({ page }) => {
    const ok = await navViaAgenda(page);
    await page.screenshot({ path: "evidence/119/P05/step_00_navigation.png" });

    if (!ok) {
      await page.screenshot({ path: "evidence/119/P05/step_BLOCKED.png" });
      throw new Error("BLOCKED: Could not navigate to FrmDetalleClie for P05 empty-data test");
    }

    await page.screenshot({ path: "evidence/119/P05/step_01_frm_detalle.png" });

    // Assert: abfCorredorPrincipal is visible (InstanciaPacifico=1 always shows it)
    const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
    await expect(corredor, "P05: abfCorredorPrincipal debe ser visible (Pacifico instance)").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P05/step_02_corredor_visible.png" });

    // Assert: value is empty or dash (no OGCORREDOR for this lote)
    const val = await corredor.evaluate((el: any) =>
      (el as any).value !== undefined ? (el as any).value : ((el as any).textContent || "").trim()
    );
    expect(
      val === "" || val === "-" || val === "–",
      `P05: Corredor Principal debe estar vacio — got '${val}'`
    ).toBe(true);

    // Assert: page loaded without errors
    const errorEl = await page.locator(".error, .aisError, [class*=error]").count();
    expect(errorEl, "P05: no debe haber errores en pantalla").toBe(0);

    await page.screenshot({ path: "evidence/119/P05/step_03_corredor_empty.png" });
  });
});

test.describe("ADO-119 P08 — Riesgo de Cliente vacio para lote sin CLRIESGOSIS", () => {
  test("p08 riesgo_cliente_vacio_sin_error", async ({ page }) => {
    const ok = await navViaAgenda(page);
    await page.screenshot({ path: "evidence/119/P08/step_00_navigation.png" });

    if (!ok) {
      await page.screenshot({ path: "evidence/119/P08/step_BLOCKED.png" });
      throw new Error("BLOCKED: Could not navigate to FrmDetalleClie for P08 empty-data test");
    }

    await page.screenshot({ path: "evidence/119/P08/step_01_frm_detalle.png" });

    // Assert: abfRiesgoCliente is visible
    const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
    await expect(riesgo, "P08: abfRiesgoCliente debe ser visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P08/step_02_riesgo_visible.png" });

    // Assert: value is empty or dash
    const val = await riesgo.evaluate((el: any) =>
      (el as any).value !== undefined ? (el as any).value : ((el as any).textContent || "").trim()
    );
    expect(
      val === "" || val === "-" || val === "–",
      `P08: Riesgo de Cliente debe estar vacio — got '${val}'`
    ).toBe(true);

    // Assert: no errors
    const errorEl = await page.locator(".error, .aisError, [class*=error]").count();
    expect(errorEl, "P08: no debe haber errores en pantalla").toBe(0);

    await page.screenshot({ path: "evidence/119/P08/step_03_riesgo_empty.png" });
  });
});
