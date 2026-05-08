# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 119\tests\P04_P06_P09_detalle_cliente_con_datos.spec.ts >> ADO-119 P06 — Riesgo de Cliente muestra BAJO para MONTEZUMA >> p06 riesgo_cliente_muestra_valor_correcto
- Location: evidence\119\tests\P04_P06_P09_detalle_cliente_con_datos.spec.ts:76:7

# Error details

```
TimeoutError: page.goto: Timeout 20000ms exceeded.
Call log:
  - navigating to "http://localhost:35017/AgendaWeb/FrmAgenda.aspx", waiting until "load"

```

# Test source

```ts
  1   | // ADO-119 P04+P06+P09 — Corredor Principal y Riesgo de Cliente en FrmDetalleClie
  2   | // v3 — navigation via FrmAgenda row by text (Python qa_119_pablo_v2 confirmed this path)
  3   | // FrmDetalleClie renders inline after row click — URL stays FrmAgenda.aspx (PostBack)
  4   | // Detection: title contains "Detalle" OR body text contains "Datos de Identificacion"
  5   | // Data: MONTEZUMA GARRIDO NATALIA = CLCOD 4127924112345393 — OGCORREDOR=Corredor 1 | CLRIESGOSIS=BAJO
  6   | import { test, expect, Page } from "@playwright/test";
  7   | 
  8   | const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
  9   | if (!BASE_URL) throw new Error("AGENDA_WEB_BASE_URL env var is required");
  10  | 
  11  | const TARGET_CLIENT_TEXT = "MONTEZUMA";
  12  | const EXPECTED_CORREDOR = "Corredor 1";
  13  | const EXPECTED_RIESGO = "BAJO";
  14  | 
  15  | /** Navigate to FrmAgenda and click the row containing targetText.
  16  |  *  Returns the page (FrmDetalleClie renders inline — URL stays FrmAgenda). */
  17  | async function navViaAgendaRow(page: Page, targetText: string): Promise<boolean> {
> 18  |   await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: "load" });
      |              ^ TimeoutError: page.goto: Timeout 20000ms exceeded.
  19  |   await page.waitForLoadState("networkidle", { timeout: 12000 });
  20  | 
  21  |   // Find a visible tbody tr containing the target text
  22  |   const allRows = page.locator("table tbody tr");
  23  |   const rowCount = await allRows.count();
  24  |   let targetIdx = -1;
  25  |   for (let i = 0; i < rowCount; i++) {
  26  |     const text = (await allRows.nth(i).textContent() || "").toUpperCase();
  27  |     const visible = await allRows.nth(i).isVisible().catch(() => false);
  28  |     if (visible && text.includes(targetText.toUpperCase())) {
  29  |       targetIdx = i;
  30  |       break;
  31  |     }
  32  |   }
  33  |   if (targetIdx === -1) return false;
  34  | 
  35  |   await allRows.nth(targetIdx).click({ noWaitAfter: true });
  36  |   await page.waitForLoadState("load", { timeout: 20000 });
  37  | 
  38  |   // Detection: FrmDetalleClie renders inline — check by content, not URL
  39  |   const detected =
  40  |     (await page.title()).includes("Detalle") ||
  41  |     (await page.locator("text=Datos de Identificacion").count()) > 0 ||
  42  |     (await page.locator('[id*="abfCorredorPrincipal"]').count()) > 0;
  43  |   return detected;
  44  | }
  45  | 
  46  | /** Read value from AISBusinessField (ReadOnly span or input). */
  47  | async function readField(page: Page, fieldPattern: string): Promise<string> {
  48  |   const el = page.locator(`[id*="${fieldPattern}"]`).first();
  49  |   return el.evaluate((node: any) => {
  50  |     if (node.value !== undefined && node.value !== "") return node.value;
  51  |     return (node.textContent || "").replace(/\s+/g, " ").trim();
  52  |   });
  53  | }
  54  | 
  55  | // ─── P04 ─────────────────────────────────────────────────────────────────────
  56  | test.describe("ADO-119 P04 — Corredor Principal muestra Corredor 1 para MONTEZUMA", () => {
  57  |   test("p04 corredor_principal_muestra_valor_correcto", async ({ page }) => {
  58  |     const ok = await navViaAgendaRow(page, TARGET_CLIENT_TEXT);
  59  |     await page.screenshot({ path: "evidence/119/P04/step_00_navigation.png" });
  60  |     if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P04`);
  61  | 
  62  |     await page.screenshot({ path: "evidence/119/P04/step_01_frm_detalle.png" });
  63  | 
  64  |     const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
  65  |     await expect(corredor, "P04: abfCorredorPrincipal visible").toBeVisible({ timeout: 10000 });
  66  |     await page.screenshot({ path: "evidence/119/P04/step_02_corredor_visible.png" });
  67  | 
  68  |     const val = await readField(page, "abfCorredorPrincipal");
  69  |     await page.screenshot({ path: "evidence/119/P04/step_03_corredor_value.png" });
  70  |     expect(val, `P04: Corredor Principal debe ser '${EXPECTED_CORREDOR}' — got '${val}'`).toBe(EXPECTED_CORREDOR);
  71  |   });
  72  | });
  73  | 
  74  | // ─── P06 ─────────────────────────────────────────────────────────────────────
  75  | test.describe("ADO-119 P06 — Riesgo de Cliente muestra BAJO para MONTEZUMA", () => {
  76  |   test("p06 riesgo_cliente_muestra_valor_correcto", async ({ page }) => {
  77  |     const ok = await navViaAgendaRow(page, TARGET_CLIENT_TEXT);
  78  |     await page.screenshot({ path: "evidence/119/P06/step_00_navigation.png" });
  79  |     if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P06`);
  80  | 
  81  |     await page.screenshot({ path: "evidence/119/P06/step_01_frm_detalle.png" });
  82  | 
  83  |     const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
  84  |     await expect(riesgo, "P06: abfRiesgoCliente visible").toBeVisible({ timeout: 10000 });
  85  |     await page.screenshot({ path: "evidence/119/P06/step_02_riesgo_visible.png" });
  86  | 
  87  |     const val = await readField(page, "abfRiesgoCliente");
  88  |     await page.screenshot({ path: "evidence/119/P06/step_03_riesgo_value.png" });
  89  |     expect(val, `P06: Riesgo de Cliente debe ser '${EXPECTED_RIESGO}' — got '${val}'`).toBe(EXPECTED_RIESGO);
  90  |   });
  91  | });
  92  | 
  93  | // ─── P09 ─────────────────────────────────────────────────────────────────────
  94  | test.describe("ADO-119 P09 — Ambos campos son de solo lectura (FieldState=ReadOnly)", () => {
  95  |   test("p09 campos_son_readonly_no_editables", async ({ page }) => {
  96  |     const ok = await navViaAgendaRow(page, TARGET_CLIENT_TEXT);
  97  |     await page.screenshot({ path: "evidence/119/P09/step_00_navigation.png" });
  98  |     if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P09`);
  99  | 
  100 |     await page.screenshot({ path: "evidence/119/P09/step_01_frm_detalle.png" });
  101 | 
  102 |     const corredor = page.locator('[id*="abfCorredorPrincipal"]').first();
  103 |     await expect(corredor, "P09: abfCorredorPrincipal visible").toBeVisible({ timeout: 10000 });
  104 |     const corredorEditable = await corredor.isEditable().catch(() => false);
  105 |     expect(corredorEditable, "P09: abfCorredorPrincipal NO debe ser editable").toBe(false);
  106 | 
  107 |     const riesgo = page.locator('[id*="abfRiesgoCliente"]').first();
  108 |     await expect(riesgo, "P09: abfRiesgoCliente visible").toBeVisible({ timeout: 10000 });
  109 |     const riesgoEditable = await riesgo.isEditable().catch(() => false);
  110 |     expect(riesgoEditable, "P09: abfRiesgoCliente NO debe ser editable").toBe(false);
  111 | 
  112 |     await page.screenshot({ path: "evidence/119/P09/step_02_readonly_verified.png" });
  113 |   });
  114 | });
  115 | 
```