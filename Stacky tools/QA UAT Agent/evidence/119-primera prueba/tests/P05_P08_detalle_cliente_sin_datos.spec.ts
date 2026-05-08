// ADO-119 P05+P08 — Corredor Principal y Riesgo de Cliente vacios (lote sin datos)
// v3 — navigation via FrmAgenda row[0] (OCHOA — no OGCORREDOR/CLRIESGOSIS in dev)
// FrmDetalleClie renders inline after row click — URL stays FrmAgenda.aspx (PostBack)
import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
if (!BASE_URL) throw new Error("AGENDA_WEB_BASE_URL env var is required");

const SKIP_TEXT = "MONTEZUMA"; // Skip the client WITH data

/** Navigate via FrmAgenda — click first row that does NOT contain skipText. */
async function navViaAgendaEmptyRow(page: Page, skipText: string): Promise<boolean> {
  await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 12000 });

  const allRows = page.locator("table tbody tr");
  const rowCount = await allRows.count();
  let targetIdx = -1;
  for (let i = 0; i < rowCount; i++) {
    const text = (await allRows.nth(i).textContent() || "").toUpperCase();
    const visible = await allRows.nth(i).isVisible().catch(() => false);
    if (visible && !text.includes(skipText.toUpperCase()) && text.trim().length > 0) {
      targetIdx = i;
      break;
    }
  }
  if (targetIdx === -1) return false;

  await allRows.nth(targetIdx).click({ noWaitAfter: true });
  await page.waitForLoadState("load", { timeout: 20000 });

  const detected =
    (await page.title()).includes("Detalle") ||
    (await page.locator("text=Datos de Identificacion").count()) > 0 ||
    (await page.locator('[id*="abfCorredorPrincipal"]').count()) > 0;
  return detected;
}

async function readField(page: Page, fieldPattern: string): Promise<string> {
  const el = page.locator(`[id*="${fieldPattern}"]`).first();
  return el.evaluate((node: any) => {
    if (node.value !== undefined && node.value !== "") return node.value;
    return (node.textContent || "").replace(/\s+/g, " ").trim();
  });
}

// ─── P05 ─────────────────────────────────────────────────────────────────────
test.describe("ADO-119 P05 — Corredor Principal vacio para lote sin OGCORREDOR (OCHOA)", () => {
  test("p05 corredor_principal_vacio_sin_error", async ({ page }) => {
    const ok = await navViaAgendaEmptyRow(page, SKIP_TEXT);
    await page.screenshot({ path: "evidence/119/P05/step_00_navigation.png" });
    if (!ok) throw new Error("BLOCKED: No se encontro fila sin MONTEZUMA en FrmAgenda para P05");

    await page.screenshot({ path: "evidence/119/P05/step_01_frm_detalle.png" });

    const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
    await expect(corredor, "P05: abfCorredorPrincipal visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P05/step_02_corredor_visible.png" });

    const val = await readField(page, "abfCorredorPrincipal");
    expect(
      val === "" || val === "-" || val === "\u2013",
      `P05: Corredor Principal debe estar vacio — got '${val}'`
    ).toBe(true);
    await page.screenshot({ path: "evidence/119/P05/step_03_corredor_empty.png" });
  });
});

// ─── P08 ─────────────────────────────────────────────────────────────────────
test.describe("ADO-119 P08 — Riesgo de Cliente vacio para lote sin CLRIESGOSIS (OCHOA)", () => {
  test("p08 riesgo_cliente_vacio_sin_error", async ({ page }) => {
    const ok = await navViaAgendaEmptyRow(page, SKIP_TEXT);
    await page.screenshot({ path: "evidence/119/P08/step_00_navigation.png" });
    if (!ok) throw new Error("BLOCKED: No se encontro fila sin MONTEZUMA en FrmAgenda para P08");

    await page.screenshot({ path: "evidence/119/P08/step_01_frm_detalle.png" });

    const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
    await expect(riesgo, "P08: abfRiesgoCliente visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P08/step_02_riesgo_visible.png" });

    const val = await readField(page, "abfRiesgoCliente");
    expect(
      val === "" || val === "-" || val === "\u2013",
      `P08: Riesgo de Cliente debe estar vacio — got '${val}'`
    ).toBe(true);
    await page.screenshot({ path: "evidence/119/P08/step_03_riesgo_empty.png" });
  });
});
