# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: freeform-20260505-001641\tests\P01_navegar_a_frmagenda_y_seleccionar_un_cliente_activ.spec.ts >> ADO--1 | P01 — Navegar a FrmAgenda y seleccionar un cliente activo del lote >> p01 navegar_a_frmagenda_y_seleccionar_un_cliente_activo_del_lote
- Location: evidence\freeform-20260505-001641\tests\P01_navegar_a_frmagenda_y_seleccionar_un_cliente_activ.spec.ts:70:7

# Error details

```
TimeoutError: locator.selectOption: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('#c_ddlEmpresa')
    - locator resolved to <select tabindex="-1" class="col s3 " id="c_ddlEmpresa" name="ctl00$c$ddlEmpresa">…</select>
  - attempting select option action
    2 × did not find some options
    - retrying select option action
    - waiting 20ms
    2 × did not find some options
    - retrying select option action
      - waiting 100ms
    19 × did not find some options
     - retrying select option action
       - waiting 500ms

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
  36  |     target: "table_agenda_usu",
  37  |     tipo: "visible",
  38  |     expected: null,
  39  |     selector: "#c_GridAgendaUsu"
  40  |   },
  41  | 
  42  | ];
  43  | const ASSERTIONS_OUT_PATH = 'evidence/-1/P01/assertions_P01.json';
  44  | 
  45  | // STEP_BBOXES — accumulates bounding boxes of interacted elements per step.
  46  | // Written by test.afterEach to evidence/<ticket>/<sid>/step_bboxes.json and
  47  | // consumed by screenshot_annotator.py (Fase 2) to draw red boxes on screenshots.
  48  | type StepBboxEntry = {
  49  |   step_index: number;
  50  |   screenshot_path: string;
  51  |   target: string;
  52  |   bbox: { x: number; y: number; width: number; height: number } | null;
  53  | };
  54  | const STEP_BBOXES: StepBboxEntry[] = [];
  55  | const STEP_BBOXES_OUT_PATH = 'evidence/-1/P01/step_bboxes.json';
  56  | 
  57  | test.describe('ADO--1 | P01 — Navegar a FrmAgenda y seleccionar un cliente activo del lote', () => {
  58  | 
  59  |   test.beforeEach(async ({ page }) => {
  60  |     // SETUP: login via FrmLogin.aspx (AIS rendered controls)
  61  |     // Use noWaitAfter + waitForURL to avoid actionTimeout race on ASP.NET PostBack navigation
  62  |     await page.goto(`${BASE_URL}FrmLogin.aspx`, { waitUntil: 'load' });
  63  |     await page.fill('#c_abfUsuario', USER);
  64  |     await page.fill('#c_abfContrasena', PASS);
  65  |     await page.locator('#c_btnOk').click({ noWaitAfter: true });
  66  |     await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
  67  |     await page.waitForLoadState('load', { timeout: 20000 });
  68  |   });
  69  | 
  70  |   test('p01 navegar_a_frmagenda_y_seleccionar_un_cliente_activo_del_lote', async ({ page }) => {
  71  |     // DATA: N/A
  72  | 
  73  |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  74  |     
  75  |     // - El lote 0000036010900360006D debe estar disponible.
  76  |     
  77  |     // - El agente 1 debe estar activo.
  78  |     
  79  | 
  80  |     // SETUP
  81  |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  82  |     await page.screenshot({ path: 'evidence/-1/P01/step_00_setup.png' });
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
  122 |     await page.screenshot({ path: 'screenshots/P01_panel_expanded.png' });
  123 | 
  124 |     // ACTION
  125 |     
  126 |     
  127 |     // [STEP 01] navigate to FrmAgenda.aspx
  128 |     console.log('[STEP 01] navigate FrmAgenda.aspx');
  129 |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  130 |     await page.screenshot({ path: 'evidence/-1/P01/step_01_after.png' });
  131 |     
  132 |     
  133 |     
  134 |     // [STEP 02] select 0000036010900360006D in select_empresa
  135 |     console.log('[STEP 02] select select_empresa');
> 136 |     await page.locator("#c_ddlEmpresa").selectOption('0000036010900360006D', { force: true });;
      |                                         ^ TimeoutError: locator.selectOption: Timeout 10000ms exceeded.
  137 |     await page.screenshot({ path: 'evidence/-1/P01/step_02_after.png' });
  138 |     STEP_BBOXES.push({ step_index: 2, screenshot_path: 'evidence/-1/P01/step_02_after.png', target: "select_empresa", bbox: await page.locator("#c_ddlEmpresa").boundingBox().catch(() => null) });
  139 |     
  140 |     
  141 |     
  142 |     // [STEP 03] fill input_corredor with "1"
  143 |     console.log('[STEP 03] fill input_corredor');
  144 |     await page.locator("#c_abfCorredor").fill('1', { force: true });;
  145 |     await page.screenshot({ path: 'evidence/-1/P01/step_03_after.png' });
  146 |     STEP_BBOXES.push({ step_index: 3, screenshot_path: 'evidence/-1/P01/step_03_after.png', target: "input_corredor", bbox: await page.locator("#c_abfCorredor").boundingBox().catch(() => null) });
  147 |     
  148 |     
  149 |     
  150 |     // [STEP 04] click link_c_btnok
  151 |     console.log('[STEP 04] click link_c_btnok');
  152 |     await page.locator("#c_btnOk").click({ force: true });
  153 |     await page.waitForLoadState('load');
  154 |     await page.screenshot({ path: 'evidence/-1/P01/step_04_after.png' });
  155 |     STEP_BBOXES.push({ step_index: 4, screenshot_path: 'evidence/-1/P01/step_04_after.png', target: "link_c_btnok", bbox: await page.locator("#c_btnOk").boundingBox().catch(() => null) });
  156 |     
  157 |     
  158 | 
  159 |     // ASSERTIONS
  160 |     
  161 |     
  162 |     await expect(page.locator('#c_GridAgendaUsu'), 'P01: table_agenda_usu debe ser visible').toBeVisible();
  163 |     
  164 |     
  165 | 
  166 |     // CLEANUP
  167 |     await page.context().clearCookies();
  168 |   });
  169 | 
  170 |   test.afterEach(async ({ page }) => {
  171 |     // Capture final state screenshot first — fail-safe even if the page is
  172 |     // mid-PostBack.
  173 |     try {
  174 |       await page.screenshot({
  175 |         path: 'evidence/-1/P01/step_final_state.png',
  176 |       });
  177 |     } catch (_e) {
  178 |       // ignore — page may be closed or navigating
  179 |     }
  180 | 
  181 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  182 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  183 |     // relying on Playwright's pass/fail (which conflates product defects
  184 |     // with pipeline defects).
  185 |     const captured: any[] = [];
  186 |     for (const probe of ORACLE_PROBES) {
  187 |       const entry: any = {
  188 |         oracle_id: probe.oracle_id,
  189 |         target: probe.target,
  190 |         tipo: probe.tipo,
  191 |         expected: probe.expected,
  192 |       };
  193 |       try {
  194 |         if (probe.selector === null) {
  195 |           // Whole-page oracle: capture the body text once (truncated).
  196 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  197 |           entry.actual_text = bodyText.slice(0, 4000);
  198 |           entry.visible = true;
  199 |         } else {
  200 |           const loc = page.locator(probe.selector);
  201 |           // count
  202 |           const count = await loc.count();
  203 |           entry.count = count;
  204 |           if (count === 0) {
  205 |             entry.visible = false;
  206 |             entry.actual_text = null;
  207 |           } else {
  208 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  209 |             // value (form controls)
  210 |             try {
  211 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  212 |             } catch (_e) { /* not a form control */ }
  213 |             // textContent
  214 |             try {
  215 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  216 |               entry.actual_text = txt.slice(0, 1000);
  217 |             } catch (_e) {
  218 |               entry.actual_text = null;
  219 |             }
  220 |             // disabled / state
  221 |             try {
  222 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  223 |             } catch (_e) { /* ignore */ }
  224 |           }
  225 |         }
  226 |       } catch (e: any) {
  227 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  228 |       }
  229 |       captured.push(entry);
  230 |     }
  231 | 
  232 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
  233 |     // must not break the test runner.
  234 |     try {
  235 |       const outPath = path.resolve(process.cwd(), ASSERTIONS_OUT_PATH);
  236 |       fs.mkdirSync(path.dirname(outPath), { recursive: true });
```