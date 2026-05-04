# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 65\tests\P05_ruc_parcial_quot20quot.spec.ts >> ADO-65 | P05 — RUC = parcial &quot;20&quot; >> p05 ruc_=_parcial_&quot;20&quot;
- Location: evidence\65\tests\P05_ruc_parcial_quot20quot.spec.ts:58:7

# Error details

```
TimeoutError: locator.click: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]')

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
          - generic [ref=e28]: "2"
        - generic [ref=e30]:
          - generic [ref=e31]: "Realizado Hoy:"
          - generic [ref=e32]: "0"
        - generic [ref=e34]:
          - generic [ref=e35]: "Total en Agenda:"
          - generic [ref=e36]: "2"
        - generic [ref=e38]:
          - generic [ref=e39]: "Barrido Realizado:"
          - generic [ref=e40]: 0%
        - generic [ref=e42]:
          - generic [ref=e43]: "Clientes Asignados:"
          - generic [ref=e44]: "10430"
  - list [ref=e45]:
    - listitem [ref=e46]:
      - generic [ref=e47]:
        - generic: format_list_bulleted
        - text: Cobranza Prejudicial
      - list [ref=e49]:
        - listitem [ref=e50]:
          - link "event Agenda Personal" [ref=e51] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgenda.aspx
            - generic: event
            - text: Agenda Personal
        - listitem [ref=e52]:
          - link "event_note Pooles de Trabajo" [ref=e53] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgenda.aspx?q=rh3wPkybH+atHWY9zjvV4w==
            - generic: event_note
            - text: Pooles de Trabajo
        - listitem [ref=e54]:
          - link "search Busqueda de Clientes" [ref=e55] [cursor=pointer]:
            - /url: /AgendaWeb/FrmBusqueda.aspx
            - generic: search
            - text: Busqueda de Clientes
        - listitem [ref=e56]:
          - link "date_range Agenda de Grupo" [ref=e57] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgendaEquipo.aspx
            - generic: date_range
            - text: Agenda de Grupo
        - listitem [ref=e58]:
          - list [ref=e59]:
            - listitem [ref=e60]:
              - generic [ref=e61] [cursor=pointer]:
                - generic: format_list_bulleted
                - text: Supervision
            - listitem [ref=e62]:
              - list [ref=e63]:
                - listitem [ref=e64]:
                  - generic [ref=e65] [cursor=pointer]:
                    - generic: format_list_bulleted
                    - text: Reportes Operativos
    - listitem [ref=e66]:
      - generic [ref=e67]:
        - generic: format_list_bulleted
        - text: Cobranza Judicial
      - list [ref=e69]:
        - listitem [ref=e70]:
          - link "event Agenda De Demandas" [ref=e71] [cursor=pointer]:
            - /url: /AgendaWeb/FrmAgendaJudicial.aspx
            - generic: event
            - text: Agenda De Demandas
        - listitem [ref=e72]:
          - link "search Buscar Demandas" [ref=e73] [cursor=pointer]:
            - /url: /AgendaWeb/FrmBusquedaJudicial.aspx
            - generic: search
            - text: Buscar Demandas
        - listitem [ref=e74]:
          - link "rule Validar Gastos" [ref=e75] [cursor=pointer]:
            - /url: /AgendaWeb/FrmValidacionGastosJudicial.aspx
            - generic: rule
            - text: Validar Gastos
        - listitem [ref=e76]:
          - link "confirmation_number Liquidar Gastos" [ref=e77] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidarGastos.aspx
            - generic: confirmation_number
            - text: Liquidar Gastos
        - listitem [ref=e78]:
          - link "switch_account Reasignar Abogado" [ref=e79] [cursor=pointer]:
            - /url: /AgendaWeb/FrmJReasignarAbogado.aspx
            - generic: switch_account
            - text: Reasignar Abogado
        - listitem [ref=e80]:
          - list [ref=e81]:
            - listitem [ref=e82]:
              - generic [ref=e83] [cursor=pointer]:
                - generic: format_list_bulleted
                - text: Reportes Operativos
            - listitem [ref=e84]:
              - list [ref=e85]:
                - listitem [ref=e86]:
                  - generic [ref=e87] [cursor=pointer]:
                    - generic: format_list_bulleted
                    - text: Reportes OBI
    - listitem [ref=e88]:
      - generic [ref=e89]:
        - generic: format_list_bulleted
        - text: Facturación y Gastos
      - list [ref=e91]:
        - listitem [ref=e92]:
          - link "rule Validar Facturas" [ref=e93] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FiScu1K/9opoNFBT3rUlgpvM=
            - generic: rule
            - text: Validar Facturas
        - listitem [ref=e94]:
          - link "rule Validar Notas de Gastos" [ref=e95] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FieWKk8YQotwBcHU/2DP3KIw=
            - generic: rule
            - text: Validar Notas de Gastos
        - listitem [ref=e96]:
          - link "receipt Facturas" [ref=e97] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiHOOp6prF5Vq+94RnI70taQ=
            - generic: receipt
            - text: Facturas
        - listitem [ref=e98]:
          - link "confirmation_number Notas de Gastos" [ref=e99] [cursor=pointer]:
            - /url: /AgendaWeb/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiEmPUsCvT75NbJGKOtz0/0Y=
            - generic: confirmation_number
            - text: Notas de Gastos
    - listitem [ref=e100]:
      - separator [ref=e101]
    - listitem [ref=e102]:
      - link "settings Administrador" [ref=e103] [cursor=pointer]:
        - /url: /AgendaWeb/FrmAdministrador.aspx
        - generic: settings
        - text: Administrador
    - listitem [ref=e104]
    - listitem [ref=e105]
  - generic [ref=e106]:
    - generic [ref=e110]:
      - link "Acciones" [ref=e111] [cursor=pointer]:
        - /url: "#!"
      - link "chevron_right Avanzar" [ref=e112] [cursor=pointer]:
        - /url: javascript:__doPostBack('ctl00$btnNext','')
        - generic: chevron_right
        - text: Avanzar
    - list [ref=e113]:
      - listitem [ref=e114]:
        - generic [ref=e115] [cursor=pointer]:
          - generic [ref=e116]: search
          - generic [ref=e117]: Búsqueda Avanzada
    - generic [ref=e118]:
      - generic [ref=e119]:
        - generic [ref=e120]: Agendados por Usuario
        - link "grid_on Agendados por Usuario" [ref=e122] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnExportExcelAgUsu','')
          - generic: grid_on
          - text: Agendados por Usuario
      - table [ref=e124]:
        - rowgroup [ref=e125]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda" [ref=e126]:
            - columnheader "Cliente" [ref=e127]:
              - link "Cliente" [ref=e128] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
            - columnheader "Lote" [ref=e129]:
              - link "Lote" [ref=e130] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
            - columnheader "Fecha" [ref=e131]:
              - link "Fecha" [ref=e132] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
            - columnheader "Hora" [ref=e133]:
              - link "Hora" [ref=e134] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e135]:
              - link "Recomendación" [ref=e136] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e137]:
              - link "Nivel Mora" [ref=e138] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e139]:
              - link "Prima" [ref=e140] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e141]:
              - link "Moneda" [ref=e142] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGMONEDA')
        - rowgroup [ref=e143]:
          - row "MONTEZUMA GARRIDO NATALIA 4127924112345393 20/03/2026 10:00:00 OECA - Cerrar Cuenta y Enviar Carpeta Recup Act Ciclo 9 48882,83 US.D" [ref=e144]:
            - cell "MONTEZUMA GARRIDO NATALIA" [ref=e145] [cursor=pointer]
            - cell "4127924112345393" [ref=e146] [cursor=pointer]
            - cell "20/03/2026" [ref=e147] [cursor=pointer]
            - cell "10:00:00" [ref=e148] [cursor=pointer]
            - cell "OECA - Cerrar Cuenta y Enviar Carpeta Recup Act" [ref=e149] [cursor=pointer]
            - cell "Ciclo 9" [ref=e150] [cursor=pointer]
            - cell "48882,83" [ref=e151] [cursor=pointer]
            - cell "US.D" [ref=e152] [cursor=pointer]
        - rowgroup
      - generic [ref=e154]: Agendados por Motor Experto
      - table [ref=e157]:
        - rowgroup [ref=e158]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda" [ref=e159]:
            - columnheader "Cliente" [ref=e160]:
              - link "Cliente" [ref=e161] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
            - columnheader "Lote" [ref=e162]:
              - link "Lote" [ref=e163] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
            - columnheader "Fecha" [ref=e164]:
              - link "Fecha" [ref=e165] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
            - columnheader "Hora" [ref=e166]:
              - link "Hora" [ref=e167] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e168]:
              - link "Recomendación" [ref=e169] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e170]:
              - link "Nivel Mora" [ref=e171] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e172]:
              - link "Prima" [ref=e173] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e174]:
              - link "Moneda" [ref=e175] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGMONEDA')
```

# Test source

```ts
  1   | // ADO-65 P05 — RUC = parcial &quot;20&quot;
  2   | // Generated by playwright_test_generator.py v1.1.0
  3   | // DO NOT EDIT MANUALLY — regenerate with: python playwright_test_generator.py --scenarios evidence/65/scenarios.json --ui-maps cache/ui_maps/ --out evidence/65/tests/
  4   | // Screen: FrmAgenda.aspx
  5   | 
  6   | import { test, expect } from '@playwright/test';
  7   | import * as fs from 'fs';
  8   | import * as path from 'path';
  9   | 
  10  | const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
  11  | const USER = process.env.AGENDA_WEB_USER!;
  12  | const PASS = process.env.AGENDA_WEB_PASS!;
  13  | 
  14  | if (!BASE_URL) throw new Error('AGENDA_WEB_BASE_URL env var is required');
  15  | if (!USER) throw new Error('AGENDA_WEB_USER env var is required');
  16  | if (!PASS) throw new Error('AGENDA_WEB_PASS env var is required');
  17  | 
  18  | // ORACLE_PROBES — generated from scenario.oraculos × ui_map.
  19  | // Consumed by the test.afterEach hook to write
  20  | // evidence/<ticket>/<sid>/assertions_<sid>.json with the actual values
  21  | // captured from the live DOM, regardless of whether the test passed,
  22  | // failed, or threw. uat_assertion_evaluator.py reads this file as the
  23  | // primary source of truth for expected/actual reconciliation; without
  24  | // it every oracle would default to status=review.
  25  | type OracleProbe = {
  26  |   oracle_id: number;
  27  |   target: string;
  28  |   tipo: string;
  29  |   expected: string | number | null;
  30  |   selector: string | null;  // CSS-ish; null for whole-page oracles
  31  | };
  32  | const ORACLE_PROBES: OracleProbe[] = [
  33  | 
  34  |   {
  35  |     oracle_id: 0,
  36  |     target: "table_agenda_usu",
  37  |     tipo: "page_contains_text",
  38  |     expected: "20",
  39  |     selector: null
  40  |   },
  41  | 
  42  | ];
  43  | const ASSERTIONS_OUT_PATH = 'evidence/65/P05/assertions_P05.json';
  44  | 
  45  | test.describe('ADO-65 | P05 — RUC = parcial &quot;20&quot;', () => {
  46  | 
  47  |   test.beforeEach(async ({ page }) => {
  48  |     // SETUP: login via FrmLogin.aspx (AIS rendered controls)
  49  |     // Use noWaitAfter + waitForURL to avoid actionTimeout race on ASP.NET PostBack navigation
  50  |     await page.goto(`${BASE_URL}FrmLogin.aspx`, { waitUntil: 'load' });
  51  |     await page.fill('#c_abfUsuario', USER);
  52  |     await page.fill('#c_abfContrasena', PASS);
  53  |     await page.locator('#c_btnOk').click({ noWaitAfter: true });
  54  |     await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
  55  |     await page.waitForLoadState('load', { timeout: 20000 });
  56  |   });
  57  | 
  58  |   test('p05 ruc_=_parcial_&quot;20&quot;', async ({ page }) => {
  59  |     // DATA: CLNUMDOC LIKE '20%'
  60  | 
  61  |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  62  |     
  63  | 
  64  |     // SETUP
  65  |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  66  |     await page.screenshot({ path: 'evidence/65/P05/step_00_setup.png' });
  67  | 
  68  |     // Expand "Búsqueda Avanzada" panel if collapsed
  69  |     const advancedPanel = page.locator('#c_pnlBusqueda');
  70  |     const isVisible = await advancedPanel.isVisible();
  71  |     if (!isVisible) {
> 72  |       await page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').click();
      |                                                                                                                                     ^ TimeoutError: locator.click: Timeout 10000ms exceeded.
  73  |       await advancedPanel.waitFor({ state: 'visible', timeout: 5000 });
  74  |     }
  75  |     await page.screenshot({ path: 'screenshots/P05_panel_expanded.png' });
  76  | 
  77  |     // ACTION
  78  |     
  79  |     
  80  |     // [STEP 01] fill input_ruc with "20"
  81  |     console.log('[STEP 01] fill input_ruc');
  82  |     await page.locator("#c_abfRUC").fill('20');;
  83  |     await page.screenshot({ path: 'evidence/65/P05/step_01_after.png' });
  84  |     
  85  |     
  86  |     
  87  |     // [STEP 02] click link_btnnext
  88  |     console.log('[STEP 02] click link_btnnext');
  89  |     await page.locator("#btnNext").click();
  90  |     await page.waitForLoadState('load');
  91  |     await page.screenshot({ path: 'evidence/65/P05/step_02_after.png' });
  92  |     
  93  |     
  94  | 
  95  |     // ASSERTIONS
  96  |     
  97  |     
  98  |     await expect(page.locator('body'), 'P05: página debe contener "20"').toContainText('20');
  99  |     
  100 |     
  101 | 
  102 |     // CLEANUP
  103 |     await page.context().clearCookies();
  104 |   });
  105 | 
  106 |   test.afterEach(async ({ page }) => {
  107 |     // Capture final state screenshot first — fail-safe even if the page is
  108 |     // mid-PostBack.
  109 |     try {
  110 |       await page.screenshot({
  111 |         path: 'evidence/65/P05/step_final_state.png',
  112 |       });
  113 |     } catch (_e) {
  114 |       // ignore — page may be closed or navigating
  115 |     }
  116 | 
  117 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  118 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  119 |     // relying on Playwright's pass/fail (which conflates product defects
  120 |     // with pipeline defects).
  121 |     const captured: any[] = [];
  122 |     for (const probe of ORACLE_PROBES) {
  123 |       const entry: any = {
  124 |         oracle_id: probe.oracle_id,
  125 |         target: probe.target,
  126 |         tipo: probe.tipo,
  127 |         expected: probe.expected,
  128 |       };
  129 |       try {
  130 |         if (probe.selector === null) {
  131 |           // Whole-page oracle: capture the body text once (truncated).
  132 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  133 |           entry.actual_text = bodyText.slice(0, 4000);
  134 |           entry.visible = true;
  135 |         } else {
  136 |           const loc = page.locator(probe.selector);
  137 |           // count
  138 |           const count = await loc.count();
  139 |           entry.count = count;
  140 |           if (count === 0) {
  141 |             entry.visible = false;
  142 |             entry.actual_text = null;
  143 |           } else {
  144 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  145 |             // value (form controls)
  146 |             try {
  147 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  148 |             } catch (_e) { /* not a form control */ }
  149 |             // textContent
  150 |             try {
  151 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  152 |               entry.actual_text = txt.slice(0, 1000);
  153 |             } catch (_e) {
  154 |               entry.actual_text = null;
  155 |             }
  156 |             // disabled / state
  157 |             try {
  158 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  159 |             } catch (_e) { /* ignore */ }
  160 |           }
  161 |         }
  162 |       } catch (e: any) {
  163 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  164 |       }
  165 |       captured.push(entry);
  166 |     }
  167 | 
  168 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
  169 |     // must not break the test runner.
  170 |     try {
  171 |       const outPath = path.resolve(process.cwd(), ASSERTIONS_OUT_PATH);
  172 |       fs.mkdirSync(path.dirname(outPath), { recursive: true });
```