# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 116\tests\P02_unidad_promesa_no_lote.spec.ts >> ADO-116 | P02 — Unidad promesa (no lote) >> p02 unidad_promesa_(no_lote)
- Location: evidence\116\tests\P02_unidad_promesa_no_lote.spec.ts:72:7

# Error details

```
Error: page.waitForURL: net::ERR_ABORTED; maybe frame was detached?
=========================== logs ===========================
waiting for navigation until "load"
============================================================
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
          - generic [ref=e20]: PACIFICO
        - generic [ref=e22]:
          - generic [ref=e23]: "Pendiente de Hoy:"
          - generic [ref=e24]: "0"
        - generic [ref=e26]:
          - generic [ref=e27]: "Pendiente de otros Días:"
          - generic [ref=e28]: "0"
        - generic [ref=e30]:
          - generic [ref=e31]: "Realizado Hoy:"
          - generic [ref=e32]: "0"
        - generic [ref=e34]:
          - generic [ref=e35]: "Total en Agenda:"
          - generic [ref=e36]: "0"
        - generic [ref=e38]:
          - generic [ref=e39]: "Barrido Realizado:"
          - generic [ref=e40]: 0%
        - generic [ref=e42]:
          - generic [ref=e43]: "Clientes Asignados:"
          - generic [ref=e44]: "494"
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
                  - list [ref=e75]:
                    - listitem [ref=e76]:
                      - generic [ref=e77] [cursor=pointer]:
                        - generic: format_list_bulleted
                        - text: Reportes OBI
    - listitem [ref=e78]:
      - separator [ref=e79]
    - listitem [ref=e80]:
      - link "settings Administrador" [ref=e81] [cursor=pointer]:
        - /url: /AgendaWeb/FrmAdministrador.aspx
        - generic: settings
        - text: Administrador
    - listitem [ref=e82]
    - listitem [ref=e83]
  - generic [ref=e84]:
    - link "Acciones" [ref=e89] [cursor=pointer]:
      - /url: "#!"
    - list [ref=e90]:
      - listitem [ref=e91]:
        - generic [ref=e92] [cursor=pointer]:
          - generic [ref=e93]: search
          - generic [ref=e94]: Búsqueda Avanzada
    - generic [ref=e95]:
      - generic [ref=e97]: Agendados por Usuario
      - table [ref=e100]:
        - rowgroup [ref=e101]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda RUC Corredor Débito Auto." [ref=e102]:
            - columnheader "Cliente" [ref=e103]:
              - link "Cliente" [ref=e104] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
            - columnheader "Lote" [ref=e105]:
              - link "Lote" [ref=e106] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
            - columnheader "Fecha" [ref=e107]:
              - link "Fecha" [ref=e108] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
            - columnheader "Hora" [ref=e109]:
              - link "Hora" [ref=e110] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e111]:
              - link "Recomendación" [ref=e112] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e113]:
              - link "Nivel Mora" [ref=e114] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e115]:
              - link "Prima" [ref=e116] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e117]:
              - link "Moneda" [ref=e118] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGMONEDA')
            - columnheader "RUC" [ref=e119]:
              - link "RUC" [ref=e120] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLNUMDOC')
            - columnheader "Corredor" [ref=e121]:
              - link "Corredor" [ref=e122] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGCORREDOR')
            - columnheader "Débito Auto." [ref=e123]:
              - link "Débito Auto." [ref=e124] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGDEBAUT')
      - generic [ref=e126]: Agendados por Motor Experto
      - table [ref=e129]:
        - rowgroup [ref=e130]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda RUC Corredor Débito Auto." [ref=e131]:
            - columnheader "Cliente" [ref=e132]:
              - link "Cliente" [ref=e133] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
            - columnheader "Lote" [ref=e134]:
              - link "Lote" [ref=e135] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
            - columnheader "Fecha" [ref=e136]:
              - link "Fecha" [ref=e137] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
            - columnheader "Hora" [ref=e138]:
              - link "Hora" [ref=e139] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e140]:
              - link "Recomendación" [ref=e141] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e142]:
              - link "Nivel Mora" [ref=e143] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e144]:
              - link "Prima" [ref=e145] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e146]:
              - link "Moneda" [ref=e147] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGMONEDA')
            - columnheader "RUC" [ref=e148]:
              - link "RUC" [ref=e149] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLNUMDOC')
            - columnheader "Corredor" [ref=e150]:
              - link "Corredor" [ref=e151] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGCORREDOR')
            - columnheader "Débito Auto." [ref=e152]:
              - link "Débito Auto." [ref=e153] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGDEBAUT')
```

# Test source

```ts
  1   | // ADO-116 P02 — Unidad promesa (no lote)
  2   | // Generated by playwright_test_generator.py v1.1.0
  3   | // DO NOT EDIT MANUALLY — regenerate with: python playwright_test_generator.py --scenarios evidence/116/scenarios.json --ui-maps cache/ui_maps/ --out evidence/116/tests/
  4   | // Screen: FrmAgenda.aspx
  5   | 
  6   | 
  7   | import { test, expect } from '@playwright/test';
  8   | import * as fs from 'fs';
  9   | import * as path from 'path';
  10  | 
  11  | const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
  12  | const USER = process.env.AGENDA_WEB_USER!;
  13  | const PASS = process.env.AGENDA_WEB_PASS!;
  14  | 
  15  | if (!BASE_URL) throw new Error('AGENDA_WEB_BASE_URL env var is required');
  16  | if (!USER) throw new Error('AGENDA_WEB_USER env var is required');
  17  | if (!PASS) throw new Error('AGENDA_WEB_PASS env var is required');
  18  | 
  19  | // ORACLE_PROBES — generated from scenario.oraculos × ui_map.
  20  | // Consumed by the test.afterEach hook to write
  21  | // evidence/<ticket>/<sid>/assertions_<sid>.json with the actual values
  22  | // captured from the live DOM, regardless of whether the test passed,
  23  | // failed, or threw. uat_assertion_evaluator.py reads this file as the
  24  | // primary source of truth for expected/actual reconciliation; without
  25  | // it every oracle would default to status=review.
  26  | type OracleProbe = {
  27  |   oracle_id: number;
  28  |   target: string;
  29  |   tipo: string;
  30  |   expected: string | number | null;
  31  |   selector: string | null;  // CSS-ish; null for whole-page oracles
  32  | };
  33  | const ORACLE_PROBES: OracleProbe[] = [
  34  | 
  35  |   {
  36  |     oracle_id: 0,
  37  |     target: "table_agenda_usu",
  38  |     tipo: "count_gt",
  39  |     expected: 0,
  40  |     selector: "#c_GridAgendaUsu"
  41  |   },
  42  | 
  43  | ];
  44  | const ASSERTIONS_OUT_PATH = 'evidence/116/P02/assertions_P02.json';
  45  | 
  46  | // STEP_BBOXES — accumulates bounding boxes of interacted elements per step.
  47  | // Written by test.afterEach to evidence/<ticket>/<sid>/step_bboxes.json and
  48  | // consumed by screenshot_annotator.py (Fase 2) to draw red boxes on screenshots.
  49  | type StepBboxEntry = {
  50  |   step_index: number;
  51  |   screenshot_path: string;
  52  |   target: string;
  53  |   bbox: { x: number; y: number; width: number; height: number } | null;
  54  | };
  55  | const STEP_BBOXES: StepBboxEntry[] = [];
  56  | const STEP_BBOXES_OUT_PATH = 'evidence/116/P02/step_bboxes.json';
  57  | 
  58  | 
  59  | test.describe('ADO-116 | P02 — Unidad promesa (no lote)', () => {
  60  | 
  61  |   test.beforeEach(async ({ page }) => {
  62  |     // SETUP: login via FrmLogin.aspx (AIS rendered controls)
  63  |     // Use noWaitAfter + waitForURL to avoid actionTimeout race on ASP.NET PostBack navigation
  64  |     await page.goto(`${BASE_URL}FrmLogin.aspx`, { waitUntil: 'load' });
  65  |     await page.fill('#c_abfUsuario', USER);
  66  |     await page.fill('#c_abfContrasena', PASS);
  67  |     await page.locator('#c_btnOk').click({ noWaitAfter: true });
> 68  |     await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
      |                ^ Error: page.waitForURL: net::ERR_ABORTED; maybe frame was detached?
  69  |     await page.waitForLoadState('load', { timeout: 20000 });
  70  |   });
  71  | 
  72  |   test('p02 unidad_promesa_(no_lote)', async ({ page }) => {
  73  |     // DATA: N/A
  74  | 
  75  |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  76  |     
  77  |     // - El lote 10003269210997120010 debe estar disponible en la agenda.
  78  |     
  79  | 
  80  |     // SETUP
  81  |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  82  |     await page.screenshot({ path: 'evidence/116/P02/step_00_setup.png' });
  83  | 
  84  |     // Expand "Búsqueda Avanzada" panel only when needed.
  85  |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  86  |     const advancedPanel = page.locator('#c_pnlBusqueda');
  87  |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  88  |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  89  |     if (!filtersReady) {
  90  |       const toggleByHeader = page.locator('.collapsible-header:has-text("Búsqueda Avanzada"), li:has-text("Búsqueda Avanzada") .collapsible-header').first();
  91  |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  92  |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  93  | 
  94  |       if (await toggleByHeader.count()) {
  95  |         await toggleByHeader.scrollIntoViewIfNeeded();
  96  |         await toggleByHeader.click({ timeout: 5000, force: true });
  97  |       } else if (await toggleByData.count()) {
  98  |         await toggleByData.click({ timeout: 5000, force: true });
  99  |       } else if (await toggleByText.count()) {
  100 |         await toggleByText.click({ timeout: 5000, force: true });
  101 |       }
  102 | 
  103 |       if (await advancedPanel.count()) {
  104 |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  105 |       }
  106 |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  107 | 
  108 |       // Last-resort fallback for legacy WebForms layouts where the toggle
  109 |       // exists but does not update aria/visibility attributes consistently.
  110 |       if (!filtersReady && await advancedPanel.count()) {
  111 |         await page.evaluate(() => {
  112 |           const pnl = document.querySelector('#c_pnlBusqueda') as HTMLElement | null;
  113 |           if (pnl) {
  114 |             pnl.style.display = 'block';
  115 |             pnl.classList.add('active');
  116 |           }
  117 |         });
  118 |         filtersReady = await firstFilter.first().isVisible().catch(() => false);
  119 |       }
  120 |     }
  121 |     console.log('Advanced filters ready:', filtersReady);
  122 |     await page.screenshot({ path: 'screenshots/P02_panel_expanded.png' });
  123 | 
  124 |     // ACTION
  125 |     
  126 |     
  127 |     // [STEP 01] click link_element
  128 |     console.log('[STEP 01] click link_element');
  129 |     await page.locator("text='Moneda'").click({ force: true });
  130 |     await page.waitForLoadState('load');
  131 |     await page.screenshot({ path: 'evidence/116/P02/step_01_after.png' });
  132 |     STEP_BBOXES.push({ step_index: 1, screenshot_path: 'evidence/116/P02/step_01_after.png', target: "link_element", bbox: await page.locator("text='Moneda'").boundingBox().catch(() => null) });
  133 |     
  134 |     
  135 |     
  136 | 
  137 |     // ASSERTIONS
  138 |     
  139 |     
  140 |     {
  141 |       const rowCount = await page.locator('#c_GridAgendaUsu tbody tr').count();
  142 |       await expect(rowCount, 'P02: table_agenda_usu rows debe ser > 0').toBeGreaterThan(0);
  143 |     }
  144 |     
  145 |     
  146 | 
  147 |     // CLEANUP
  148 |     await page.context().clearCookies();
  149 |   });
  150 | 
  151 |   test.afterEach(async ({ page }) => {
  152 |     // Capture final state screenshot first — fail-safe even if the page is
  153 |     // mid-PostBack.
  154 |     try {
  155 |       await page.screenshot({
  156 |         path: 'evidence/116/P02/step_final_state.png',
  157 |       });
  158 |     } catch (_e) {
  159 |       // ignore — page may be closed or navigating
  160 |     }
  161 | 
  162 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  163 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  164 |     // relying on Playwright's pass/fail (which conflates product defects
  165 |     // with pipeline defects).
  166 |     const captured: any[] = [];
  167 |     for (const probe of ORACLE_PROBES) {
  168 |       const entry: any = {
```