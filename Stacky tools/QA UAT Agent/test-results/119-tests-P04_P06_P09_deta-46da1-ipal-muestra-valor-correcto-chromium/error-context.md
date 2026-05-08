# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 119\tests\P04_P06_P09_detalle_cliente_con_datos.spec.ts >> ADO-119 P04 — Corredor Principal muestra Corredor 1 para MONTEZUMA >> p04 corredor_principal_muestra_valor_correcto
- Location: evidence\119\tests\P04_P06_P09_detalle_cliente_con_datos.spec.ts:57:7

# Error details

```
Error: BLOCKED: MONTEZUMA row not found in FrmAgenda for P04
```

# Page snapshot

```yaml
- generic [ref=e2]:
  - navigation [ref=e3]:
    - generic [ref=e4]:
      - list [ref=e5]:
        - listitem [ref=e6]:
          - link "menu" [ref=e7] [cursor=pointer]:
            - /url: "#"
            - generic: menu
      - generic [ref=e8]:
        - img [ref=e9]
        - img [ref=e10]
      - generic [ref=e11]:
        - generic [ref=e13] [cursor=pointer]:
          - generic: logout
          - text: Salir
        - img [ref=e14]
      - generic [ref=e15]: Agenda Personal
      - generic [ref=e17]:
        - generic [ref=e18]:
          - generic [ref=e19]: "Usuario:"
          - generic [ref=e20]: USUARIO TEST
        - generic [ref=e22]:
          - generic [ref=e23]: "Pendiente de Hoy:"
          - generic [ref=e24]: "0"
        - generic [ref=e26]:
          - generic [ref=e27]: "Pendiente de otros Días:"
          - generic [ref=e28]: "3"
        - generic [ref=e30]:
          - generic [ref=e31]: "Realizado Hoy:"
          - generic [ref=e32]: "0"
        - generic [ref=e34]:
          - generic [ref=e35]: "Total en Agenda:"
          - generic [ref=e36]: "3"
        - generic [ref=e38]:
          - generic [ref=e39]: "Barrido Realizado:"
          - generic [ref=e40]: 0%
        - generic [ref=e42]:
          - generic [ref=e43]: "Clientes Asignados:"
          - generic [ref=e44]: "10430"
        - generic [ref=e46]:
          - generic [ref=e47]: "Total Compromisos a vencer:"
          - generic [ref=e48]: "0"
        - generic [ref=e50]:
          - generic [ref=e51]: "Promesas a Vencer en 7 días:"
          - generic [ref=e52]: "0"
  - list [ref=e53]:
    - listitem [ref=e54]:
      - generic [ref=e55]:
        - generic: format_list_bulleted
        - text: Cobranza Prejudicial
      - list [ref=e57]:
        - listitem [ref=e58]:
          - link "event Agenda Personal" [ref=e59] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgenda.aspx
            - generic: event
            - text: Agenda Personal
        - listitem [ref=e60]:
          - link "event_note Pooles de Trabajo" [ref=e61] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgenda.aspx?q=rh3wPkybH+atHWY9zjvV4w==
            - generic: event_note
            - text: Pooles de Trabajo
        - listitem [ref=e62]:
          - link "search Busqueda de Clientes" [ref=e63] [cursor=pointer]:
            - /url: /AgendaWeb/FrmBusqueda.aspx
            - generic: search
            - text: Busqueda de Clientes
        - listitem [ref=e64]:
          - link "date_range Agenda de Grupo" [ref=e65] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgendaEquipo.aspx
            - generic: date_range
            - text: Agenda de Grupo
        - listitem [ref=e66]:
          - list [ref=e67]:
            - listitem [ref=e68]:
              - generic [ref=e69] [cursor=pointer]:
                - generic: format_list_bulleted
                - text: Supervision
            - listitem [ref=e70]:
              - list [ref=e71]:
                - listitem [ref=e72]:
                  - generic [ref=e73] [cursor=pointer]:
                    - generic: format_list_bulleted
                    - text: Reportes Operativos
    - listitem [ref=e74]:
      - generic [ref=e75]:
        - generic: format_list_bulleted
        - text: Cobranza Judicial
      - list [ref=e77]:
        - listitem [ref=e78]:
          - link "event Agenda De Demandas" [ref=e79] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgendaJudicial.aspx
            - generic: event
            - text: Agenda De Demandas
        - listitem [ref=e80]:
          - link "search Buscar Demandas" [ref=e81] [cursor=pointer]:
            - /url: /AgendaWeb/FrmBusquedaJudicial.aspx
            - generic: search
            - text: Buscar Demandas
        - listitem [ref=e82]:
          - link "rule Validar Gastos" [ref=e83] [cursor=pointer]:
            - /url: /AgendaWeb/FrmValidacionGastosJudicial.aspx
            - generic: rule
            - text: Validar Gastos
        - listitem [ref=e84]:
          - link "confirmation_number Liquidar Gastos" [ref=e85] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidarGastos.aspx
            - generic: confirmation_number
            - text: Liquidar Gastos
        - listitem [ref=e86]:
          - link "switch_account Reasignar Abogado" [ref=e87] [cursor=pointer]:
            - /url: /AgendaWeb/FrmJReasignarAbogado.aspx
            - generic: switch_account
            - text: Reasignar Abogado
        - listitem [ref=e88]:
          - list [ref=e89]:
            - listitem [ref=e90]:
              - generic [ref=e91] [cursor=pointer]:
                - generic: format_list_bulleted
                - text: Reportes Operativos
            - listitem [ref=e92]:
              - list [ref=e93]:
                - listitem [ref=e94]:
                  - generic [ref=e95] [cursor=pointer]:
                    - generic: format_list_bulleted
                    - text: Reportes OBI
    - listitem [ref=e96]:
      - generic [ref=e97]:
        - generic: format_list_bulleted
        - text: Facturación y Gastos
      - list [ref=e99]:
        - listitem [ref=e100]:
          - link "rule Validar Facturas" [ref=e101] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FiScu1K/9opoNFBT3rUlgpvM=
            - generic: rule
            - text: Validar Facturas
        - listitem [ref=e102]:
          - link "rule Validar Notas de Gastos" [ref=e103] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FieWKk8YQotwBcHU/2DP3KIw=
            - generic: rule
            - text: Validar Notas de Gastos
        - listitem [ref=e104]:
          - link "receipt Facturas" [ref=e105] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiHOOp6prF5Vq+94RnI70taQ=
            - generic: receipt
            - text: Facturas
        - listitem [ref=e106]:
          - link "confirmation_number Notas de Gastos" [ref=e107] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiEmPUsCvT75NbJGKOtz0/0Y=
            - generic: confirmation_number
            - text: Notas de Gastos
    - listitem [ref=e108]:
      - separator [ref=e109]
    - listitem [ref=e110]:
      - link "settings Administrador" [ref=e111] [cursor=pointer]:
        - /url: /AgendaWeb/FrmAdministrador.aspx
        - generic: settings
        - text: Administrador
    - listitem [ref=e112]
    - listitem [ref=e113]
  - generic [ref=e114]:
    - generic [ref=e118]:
      - link "Acciones" [ref=e119] [cursor=pointer]:
        - /url: "#!"
      - link "chevron_right Avanzar" [ref=e120] [cursor=pointer]:
        - /url: javascript:__doPostBack('ctl00$btnNext','')
        - generic: chevron_right
        - text: Avanzar
    - list [ref=e121]:
      - listitem [ref=e122]:
        - generic [ref=e123] [cursor=pointer]:
          - generic [ref=e124]: search
          - generic [ref=e125]: Búsqueda Avanzada
    - generic [ref=e126]:
      - generic [ref=e127]:
        - generic [ref=e128]: Agendados por Usuario
        - link "grid_on Agendados por Usuario" [ref=e130] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnExportExcelAgUsu','')
          - generic: grid_on
          - text: Agendados por Usuario
      - table [ref=e132]:
        - rowgroup [ref=e133]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda RUC Corredor Débito Auto." [ref=e134]:
            - columnheader "Cliente" [ref=e135]:
              - link "Cliente" [ref=e136] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
            - columnheader "Lote" [ref=e137]:
              - link "Lote" [ref=e138] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
            - columnheader "Fecha" [ref=e139]:
              - link "Fecha" [ref=e140] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
            - columnheader "Hora" [ref=e141]:
              - link "Hora" [ref=e142] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e143]:
              - link "Recomendación" [ref=e144] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e145]:
              - link "Nivel Mora" [ref=e146] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e147]:
              - link "Prima" [ref=e148] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e149]:
              - link "Moneda" [ref=e150] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGMONEDA')
            - columnheader "RUC" [ref=e151]:
              - link "RUC" [ref=e152] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLNUMDOC')
            - columnheader "Corredor" [ref=e153]:
              - link "Corredor" [ref=e154] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGCORREDOR')
            - columnheader "Débito Auto." [ref=e155]:
              - link "Débito Auto." [ref=e156] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGDEBAUT')
        - rowgroup [ref=e157]:
          - row "OCHOA MARQUEZ HUGO 1011240108601559 29/10/2025 10:00:00 TRT6 - Llamada advertencia pase a judicial Ciclo 3 1355030,88 US.D 1011240108601559 N" [ref=e158]:
            - cell "OCHOA MARQUEZ HUGO" [ref=e159] [cursor=pointer]
            - cell "1011240108601559" [ref=e160] [cursor=pointer]
            - cell "29/10/2025" [ref=e161] [cursor=pointer]
            - cell "10:00:00" [ref=e162] [cursor=pointer]
            - cell "TRT6 - Llamada advertencia pase a judicial" [ref=e163] [cursor=pointer]
            - cell "Ciclo 3" [ref=e164] [cursor=pointer]
            - cell "1355030,88" [ref=e165] [cursor=pointer]
            - cell "US.D" [ref=e166] [cursor=pointer]
            - cell "1011240108601559" [ref=e167] [cursor=pointer]
            - cell [ref=e168] [cursor=pointer]
            - cell "N" [ref=e169] [cursor=pointer]
          - row "MONTEZUMA GARRIDO NATALIA 4127924112345393 20/03/2026 10:00:00 OECA - Cerrar Cuenta y Enviar Carpeta Recup Act Ciclo 9 48882,83 US.D 4127924112345393 Corredor 1 N" [ref=e170]:
            - cell "MONTEZUMA GARRIDO NATALIA" [ref=e171] [cursor=pointer]
            - cell "4127924112345393" [ref=e172] [cursor=pointer]
            - cell "20/03/2026" [ref=e173] [cursor=pointer]
            - cell "10:00:00" [ref=e174] [cursor=pointer]
            - cell "OECA - Cerrar Cuenta y Enviar Carpeta Recup Act" [ref=e175] [cursor=pointer]
            - cell "Ciclo 9" [ref=e176] [cursor=pointer]
            - cell "48882,83" [ref=e177] [cursor=pointer]
            - cell "US.D" [ref=e178] [cursor=pointer]
            - cell "4127924112345393" [ref=e179] [cursor=pointer]
            - cell "Corredor 1" [ref=e180] [cursor=pointer]
            - cell "N" [ref=e181] [cursor=pointer]
        - rowgroup
      - generic [ref=e183]: Agendados por Motor Experto
      - table [ref=e186]:
        - rowgroup [ref=e187]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda RUC Corredor Débito Auto." [ref=e188]:
            - columnheader "Cliente" [ref=e189]:
              - link "Cliente" [ref=e190] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
            - columnheader "Lote" [ref=e191]:
              - link "Lote" [ref=e192] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
            - columnheader "Fecha" [ref=e193]:
              - link "Fecha" [ref=e194] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
            - columnheader "Hora" [ref=e195]:
              - link "Hora" [ref=e196] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e197]:
              - link "Recomendación" [ref=e198] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e199]:
              - link "Nivel Mora" [ref=e200] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e201]:
              - link "Prima" [ref=e202] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e203]:
              - link "Moneda" [ref=e204] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGMONEDA')
            - columnheader "RUC" [ref=e205]:
              - link "RUC" [ref=e206] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLNUMDOC')
            - columnheader "Corredor" [ref=e207]:
              - link "Corredor" [ref=e208] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGCORREDOR')
            - columnheader "Débito Auto." [ref=e209]:
              - link "Débito Auto." [ref=e210] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGDEBAUT')
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
  18  |   await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: "load" });
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
> 60  |     if (!ok) throw new Error(`BLOCKED: MONTEZUMA row not found in FrmAgenda for P04`);
      |                    ^ Error: BLOCKED: MONTEZUMA row not found in FrmAgenda for P04
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