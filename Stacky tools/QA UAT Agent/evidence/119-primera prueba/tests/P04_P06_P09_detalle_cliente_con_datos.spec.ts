// ADO-119 P04+P06+P09 — Corredor Principal y Riesgo de Cliente en FrmDetalleClie
// v3 — navigation via FrmAgenda row by text (Python qa_119_pablo_v2 confirmed this path)
// FrmDetalleClie renders inline after row click — URL stays FrmAgenda.aspx (PostBack)
// Detection: title contains "Detalle" OR body text contains "Datos de Identificacion"
// Data: MONTEZUMA GARRIDO NATALIA = CLCOD 4127924112345393 — OGCORREDOR=Corredor 1 | CLRIESGOSIS=BAJO
import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
if (!BASE_URL) throw new Error("AGENDA_WEB_BASE_URL env var is required");

const TARGET_CLIENT_TEXT = "MONTEZUMA";
const EXPECTED_CORREDOR = "Corredor 1";
const EXPECTED_RIESGO = "BAJO";

/** Navigate to FrmAgenda and click the row containing targetText.
 *  Returns the page (FrmDetalleClie renders inline — URL stays FrmAgenda). */
async function navViaAgendaRow(page: Page, targetText: string): Promise<boolean> {
  await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: "load" });
  await page.waitForLoadState("networkidle", { timeout: 12000 });

  // Find a visible tbody tr containing the target text
  const allRows = page.locator("table tbody tr");
  const rowCount = await allRows.count();
  let targetIdx = -1;
  for (let i = 0; i < rowCount; i++) {
    const text = (await allRows.nth(i).textContent() || "").toUpperCase();
    const visible = await allRows.nth(i).isVisible().catch(() => false);
    if (visible && text.includes(targetText.toUpperCase())) {
      targetIdx = i;
      break;
    }
  }
  if (targetIdx === -1) return false;

  await allRows.nth(targetIdx).click({ noWaitAfter: true });
  await page.waitForLoadState("load", { timeout: 20000 });

  // Detection: FrmDetalleClie renders inline — check by content, not URL
  const detected =
    (await page.title()).includes("Detalle") ||
    (await page.locator("text=Datos de Identificacion").count()) > 0 ||
    (await page.locator('[id*="abfCorredorPrincipal"]').count()) > 0;
  return detected;
}

/** Read value from AISBusinessField (ReadOnly span or input). */
async function readField(page: Page, fieldPattern: string): Promise<string> {
  const el = page.locator(`[id*="${fieldPattern}"]`).first();
  return el.evaluate((node: any) => {
    if (node.value !== undefined && node.value !== "") return node.value;
    return (node.textContent || "").replace(/\s+/g, " ").trim();
  });
}

// ─── P04 ─────────────────────────────────────────────────────────────────────
test.describe("ADO-119 P04 — Corredor Principal muestra Corredor 1 para MONTEZUMA", () => {
  test("p04 corredor_principal_muestra_valor_correcto", async ({ page }) => {
    const ok = await navViaAgendaRow(page, TARGET_CLIENT_TEXT);
    await page.screenshot({ path: "evidence/119/P04/step_00_navigation.png" });
    if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P04`);

    await page.screenshot({ path: "evidence/119/P04/step_01_frm_detalle.png" });

    const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
    await expect(corredor, "P04: abfCorredorPrincipal visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P04/step_02_corredor_visible.png" });

    const val = await readField(page, "abfCorredorPrincipal");
    await page.screenshot({ path: "evidence/119/P04/step_03_corredor_value.png" });
    expect(val, `P04: Corredor Principal debe ser '${EXPECTED_CORREDOR}' — got '${val}'`).toBe(EXPECTED_CORREDOR);
  });
});

// ─── P06 ─────────────────────────────────────────────────────────────────────
test.describe("ADO-119 P06 — Riesgo de Cliente muestra BAJO para MONTEZUMA", () => {
  test("p06 riesgo_cliente_muestra_valor_correcto", async ({ page }) => {
    const ok = await navViaAgendaRow(page, TARGET_CLIENT_TEXT);
    await page.screenshot({ path: "evidence/119/P06/step_00_navigation.png" });
    if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P06`);

    await page.screenshot({ path: "evidence/119/P06/step_01_frm_detalle.png" });

    const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
    await expect(riesgo, "P06: abfRiesgoCliente visible").toBeVisible({ timeout: 10000 });
    await page.screenshot({ path: "evidence/119/P06/step_02_riesgo_visible.png" });

    const val = await readField(page, "abfRiesgoCliente");
    await page.screenshot({ path: "evidence/119/P06/step_03_riesgo_value.png" });
    expect(val, `P06: Riesgo de Cliente debe ser '${EXPECTED_RIESGO}' — got '${val}'`).toBe(EXPECTED_RIESGO);
  });
});

// ─── P09 ─────────────────────────────────────────────────────────────────────
test.describe("ADO-119 P09 — Ambos campos son de solo lectura (FieldState=ReadOnly)", () => {
  test("p09 campos_son_readonly_no_editables", async ({ page }) => {
    const ok = await navViaAgendaRow(page, TARGET_CLIENT_TEXT);
    await page.screenshot({ path: "evidence/119/P09/step_00_navigation.png" });
    if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P09`);

    await page.screenshot({ path: "evidence/119/P09/step_01_frm_detalle.png" });

    const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
    await expect(corredor, "P09: abfCorredorPrincipal visible").toBeVisible({ timeout: 10000 });
    const corredorEditable = await corredor.isEditable().catch(() => false);
    expect(corredorEditable, "P09: abfCorredorPrincipal NO debe ser editable").toBe(false);

    const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
    await expect(riesgo, "P09: abfRiesgoCliente visible").toBeVisible({ timeout: 10000 });
    const riesgoEditable = await riesgo.isEditable().catch(() => false);
    expect(riesgoEditable, "P09: abfRiesgoCliente NO debe ser editable").toBe(false);

    await page.screenshot({ path: "evidence/119/P09/step_02_readonly_verified.png" });
  });
});
