// ADO-119 P04+P06+P09 — Corredor Principal y Riesgo de Cliente en FrmDetalleClie
// Generated for QA UAT by UserInterfaceQA2.0 — 2026-05-08
// Auth: restored from .auth/agenda.json (set by global.setup.ts — no login here)
// Playbook: busqueda_detalle_cliente — navigate via FrmBusqueda with CLCOD=4127924112345393
// Screen: FrmDetalleClie.aspx
// Data: CLCOD=4127924112345393 | OGCORREDOR=Corredor 1 | CLRIESGOSIS=BAJO (verified in BD)

import { test, expect } from "@playwright/test";

const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
if (!BASE_URL) throw new Error("AGENDA_WEB_BASE_URL env var is required");

const CLCOD_WITH_DATA = "4127924112345393";
const EXPECTED_CORREDOR = "Corredor 1";
const EXPECTED_RIESGO = "BAJO";

// Helper: navigate to FrmDetalleClie for a specific CLCOD via FrmBusqueda
async function navToDetalle(page: any, clcod: string): Promise<boolean> {
  await page.goto(`${BASE_URL}FrmBusqueda.aspx`, { waitUntil: "load" });
  // Fill CLCOD in search field
  await page.fill("#c_abfCodCliente", clcod);
  await page.locator("#c_btnOk").click({ noWaitAfter: true });
  await page.waitForLoadState("load", { timeout: 20000 });

  // Wait for GridPersonas to populate
  const gridPersonas = page.locator("#c_GridPersonas tbody tr");
  try {
    await gridPersonas.first().waitFor({ state: "visible", timeout: 15000 });
  } catch {
    return false;
  }

  // Click first row -> GridObligaciones updates
  await gridPersonas.first().click({ noWaitAfter: true });
  await page.waitForLoadState("load", { timeout: 15000 });

  // If GridObligaciones visible, click first row -> FrmDetalleClie
  const gridOblig = page.locator("#c_GridObligaciones tbody tr");
  const gridObligCount = await gridOblig.count();
  if (gridObligCount > 0) {
    await gridOblig.first().click({ noWaitAfter: true });
    try {
      await page.waitForURL(/FrmDetalleClie/, { timeout: 15000 });
    } catch {
      // may redirect without URL change (token-based URL)
    }
    await page.waitForLoadState("load", { timeout: 15000 });
  }

  // Detect FrmDetalleClie by stable selector or title
  const onDetalle =
    page.url().includes("FrmDetalleClie") ||
    (await page.locator("#c_abfApellidoNombre").count()) > 0;
  return onDetalle;
}

test.describe("ADO-119 P04 — Corredor Principal muestra OGCORREDOR de la obligacion (lote con datos)", () => {
  test("p04 corredor_principal_muestra_valor_correcto", async ({ page }) => {
    // Navigate to lote with OGCORREDOR='Corredor 1'
    const ok = await navToDetalle(page, CLCOD_WITH_DATA);
    await page.screenshot({ path: "evidence/119/P04/step_00_navigation.png" });

    if (!ok) {
      // Save BLOCKED evidence and skip assertion
      await page.screenshot({ path: "evidence/119/P04/step_BLOCKED.png" });
      throw new Error("BLOCKED: Could not navigate to FrmDetalleClie for CLCOD=" + CLCOD_WITH_DATA);
    }

    await page.screenshot({ path: "evidence/119/P04/step_01_frm_detalle.png" });

    // Assert: abfCorredorPrincipal is visible
    const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
    await expect(corredor, "P04: abfCorredorPrincipal debe ser visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P04/step_02_corredor_visible.png" });

    // Assert: value matches expected OGCORREDOR
    const val = await corredor.evaluate((el: any) =>
      (el as any).value !== undefined && (el as any).value !== ""
        ? (el as any).value
        : ((el as any).textContent || "").replace(/\s+/g, " ").trim()
    );
    await page.screenshot({ path: "evidence/119/P04/step_03_corredor_value.png" });
    expect(val, `P04: Corredor Principal debe ser '${EXPECTED_CORREDOR}' — got '${val}'`).toBe(EXPECTED_CORREDOR);
  });
});

test.describe("ADO-119 P06 — Riesgo de Cliente muestra CLRIESGOSIS del lote (lote con datos)", () => {
  test("p06 riesgo_cliente_muestra_valor_correcto", async ({ page }) => {
    const ok = await navToDetalle(page, CLCOD_WITH_DATA);
    await page.screenshot({ path: "evidence/119/P06/step_00_navigation.png" });

    if (!ok) {
      await page.screenshot({ path: "evidence/119/P06/step_BLOCKED.png" });
      throw new Error("BLOCKED: Could not navigate to FrmDetalleClie for CLCOD=" + CLCOD_WITH_DATA);
    }

    await page.screenshot({ path: "evidence/119/P06/step_01_frm_detalle.png" });

    // Assert: abfRiesgoCliente is visible
    const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
    await expect(riesgo, "P06: abfRiesgoCliente debe ser visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P06/step_02_riesgo_visible.png" });

    // Assert: value matches expected CLRIESGOSIS
    const val = await riesgo.evaluate((el: any) =>
      (el as any).value !== undefined && (el as any).value !== ""
        ? (el as any).value
        : ((el as any).textContent || "").replace(/\s+/g, " ").trim()
    );
    await page.screenshot({ path: "evidence/119/P06/step_03_riesgo_value.png" });
    expect(val, `P06: Riesgo de Cliente debe ser '${EXPECTED_RIESGO}' — got '${val}'`).toBe(EXPECTED_RIESGO);
  });
});

test.describe("ADO-119 P09 — Ambos campos son de solo lectura", () => {
  test("p09 campos_son_readonly_no_editables", async ({ page }) => {
    const ok = await navToDetalle(page, CLCOD_WITH_DATA);
    await page.screenshot({ path: "evidence/119/P09/step_00_navigation.png" });

    if (!ok) {
      await page.screenshot({ path: "evidence/119/P09/step_BLOCKED.png" });
      throw new Error("BLOCKED: Could not navigate to FrmDetalleClie for P09");
    }

    await page.screenshot({ path: "evidence/119/P09/step_01_frm_detalle.png" });

    // Assert: abfCorredorPrincipal is NOT editable (ReadOnly or Disabled)
    const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
    await expect(corredor, "P09: abfCorredorPrincipal visible").toBeVisible({ timeout: 10000 });
    const corredorEditable = await corredor.isEditable().catch(() => false);
    expect(corredorEditable, "P09: abfCorredorPrincipal NO debe ser editable (ReadOnly)").toBe(false);

    // Assert: abfRiesgoCliente is NOT editable
    const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
    await expect(riesgo, "P09: abfRiesgoCliente visible").toBeVisible({ timeout: 10000 });
    const riesgoEditable = await riesgo.isEditable().catch(() => false);
    expect(riesgoEditable, "P09: abfRiesgoCliente NO debe ser editable (ReadOnly)").toBe(false);

    await page.screenshot({ path: "evidence/119/P09/step_02_readonly_verified.png" });
  });
});
