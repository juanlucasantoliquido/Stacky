# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 116\tests\P04_visibilidad_pacifico.spec.ts >> ADO-116 | P04 — Visibilidad Pacifico >> p04 visibilidad_pacifico
- Location: evidence\116\tests\P04_visibilidad_pacifico.spec.ts:80:7

# Error details

```
Error: P04: panel_timer debe ser visible

expect(locator).toBeVisible() failed

Locator:  locator('#updTimer')
Expected: visible
Received: hidden
Timeout:  5000ms

Call log:
  - P04: panel_timer debe ser visible with timeout 5000ms
  - waiting for locator('#updTimer')
    9 × locator resolved to <div id="updTimer">…</div>
      - unexpected value "hidden"

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
        - generic [active] [ref=e92] [cursor=pointer]:
          - generic [ref=e93]: search
          - generic [ref=e94]: Búsqueda Avanzada
        - generic [ref=e97]:
          - generic [ref=e98]:
            - generic [ref=e99]:
              - textbox "Desde" [ref=e100]
              - generic [ref=e101]: Desde
            - generic [ref=e102]:
              - textbox "Hasta" [ref=e103]
              - generic [ref=e104]: Hasta
            - generic [ref=e105]:
              - generic [ref=e106]: Empresa
              - combobox "Todas" [ref=e109] [cursor=pointer]:
                - generic "Todas" [ref=e110]
            - generic [ref=e112]:
              - generic [ref=e113]: Perfil
              - combobox "Todos" [ref=e116] [cursor=pointer]:
                - generic "Todos" [ref=e117]
          - generic [ref=e119]:
            - generic [ref=e120]:
              - generic [ref=e121]: Región
              - combobox "Todas" [ref=e124] [cursor=pointer]:
                - generic "Todas" [ref=e125]
            - generic [ref=e127]:
              - generic [ref=e128]: Recomendación
              - combobox "Todas" [ref=e131] [cursor=pointer]:
                - generic "Todas" [ref=e132]
            - generic [ref=e134]:
              - generic [ref=e135]: Nivel de Mora
              - combobox "Todos" [ref=e138] [cursor=pointer]:
                - generic "Todos" [ref=e139]
            - generic [ref=e141]:
              - generic [ref=e142]: Tipo de Cliente
              - combobox "Todos" [ref=e145] [cursor=pointer]:
                - generic "Todos" [ref=e146]
          - generic [ref=e148]:
            - generic [ref=e149]:
              - generic [ref=e150]: Débito Automático
              - combobox "Todos" [ref=e153] [cursor=pointer]:
                - generic "Todos" [ref=e154]
            - generic [ref=e156]:
              - textbox "Corredor:" [ref=e157]
              - generic [ref=e158]: "Corredor:"
            - generic [ref=e159]:
              - textbox "Nombre de Cliente" [ref=e160]
              - generic [ref=e161]: Nombre de Cliente
            - generic [ref=e162]:
              - textbox "RUC" [ref=e163]
              - generic [ref=e164]: RUC
          - link "search Filtrar" [ref=e167] [cursor=pointer]:
            - /url: javascript:__doPostBack('ctl00$c$btnOk','')
            - generic: search
            - text: Filtrar
    - generic [ref=e168]:
      - generic [ref=e170]: Agendados por Usuario
      - table [ref=e173]:
        - rowgroup [ref=e174]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda RUC Corredor Débito Auto." [ref=e175]:
            - columnheader "Cliente" [ref=e176]:
              - link "Cliente" [ref=e177] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
            - columnheader "Lote" [ref=e178]:
              - link "Lote" [ref=e179] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
            - columnheader "Fecha" [ref=e180]:
              - link "Fecha" [ref=e181] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
            - columnheader "Hora" [ref=e182]:
              - link "Hora" [ref=e183] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e184]:
              - link "Recomendación" [ref=e185] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e186]:
              - link "Nivel Mora" [ref=e187] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e188]:
              - link "Prima" [ref=e189] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e190]:
              - link "Moneda" [ref=e191] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGMONEDA')
            - columnheader "RUC" [ref=e192]:
              - link "RUC" [ref=e193] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLNUMDOC')
            - columnheader "Corredor" [ref=e194]:
              - link "Corredor" [ref=e195] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGCORREDOR')
            - columnheader "Débito Auto." [ref=e196]:
              - link "Débito Auto." [ref=e197] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$OGDEBAUT')
      - generic [ref=e199]: Agendados por Motor Experto
      - table [ref=e202]:
        - rowgroup [ref=e203]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora Prima Moneda RUC Corredor Débito Auto." [ref=e204]:
            - columnheader "Cliente" [ref=e205]:
              - link "Cliente" [ref=e206] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
            - columnheader "Lote" [ref=e207]:
              - link "Lote" [ref=e208] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
            - columnheader "Fecha" [ref=e209]:
              - link "Fecha" [ref=e210] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
            - columnheader "Hora" [ref=e211]:
              - link "Hora" [ref=e212] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e213]:
              - link "Recomendación" [ref=e214] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e215]:
              - link "Nivel Mora" [ref=e216] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
            - columnheader "Prima" [ref=e217]:
              - link "Prima" [ref=e218] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LODEUDA')
            - columnheader "Moneda" [ref=e219]:
              - link "Moneda" [ref=e220] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGMONEDA')
            - columnheader "RUC" [ref=e221]:
              - link "RUC" [ref=e222] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLNUMDOC')
            - columnheader "Corredor" [ref=e223]:
              - link "Corredor" [ref=e224] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGCORREDOR')
            - columnheader "Débito Auto." [ref=e225]:
              - link "Débito Auto." [ref=e226] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$OGDEBAUT')
```

# Test source

```ts
  45  |     target: "panel_timer_session",
  46  |     tipo: "invisible",
  47  |     expected: null,
  48  |     selector: "#TimerSession"
  49  |   },
  50  | 
  51  | ];
  52  | const ASSERTIONS_OUT_PATH = 'evidence/116/P04/assertions_P04.json';
  53  | 
  54  | // STEP_BBOXES — accumulates bounding boxes of interacted elements per step.
  55  | // Written by test.afterEach to evidence/<ticket>/<sid>/step_bboxes.json and
  56  | // consumed by screenshot_annotator.py (Fase 2) to draw red boxes on screenshots.
  57  | type StepBboxEntry = {
  58  |   step_index: number;
  59  |   screenshot_path: string;
  60  |   target: string;
  61  |   bbox: { x: number; y: number; width: number; height: number } | null;
  62  | };
  63  | const STEP_BBOXES: StepBboxEntry[] = [];
  64  | const STEP_BBOXES_OUT_PATH = 'evidence/116/P04/step_bboxes.json';
  65  | 
  66  | 
  67  | test.describe('ADO-116 | P04 — Visibilidad Pacifico', () => {
  68  | 
  69  |   test.beforeEach(async ({ page }) => {
  70  |     // SETUP: login via FrmLogin.aspx (AIS rendered controls)
  71  |     // Use noWaitAfter + waitForURL to avoid actionTimeout race on ASP.NET PostBack navigation
  72  |     await page.goto(`${BASE_URL}FrmLogin.aspx`, { waitUntil: 'load' });
  73  |     await page.fill('#c_abfUsuario', USER);
  74  |     await page.fill('#c_abfContrasena', PASS);
  75  |     await page.locator('#c_btnOk').click({ noWaitAfter: true });
  76  |     await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
  77  |     await page.waitForLoadState('load', { timeout: 20000 });
  78  |   });
  79  | 
  80  |   test('p04 visibilidad_pacifico', async ({ page }) => {
  81  |     // DATA: N/A
  82  | 
  83  |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  84  |     
  85  |     // - El usuario PACIFICO debe estar logueado con perfil 361.
  86  |     
  87  |     // - El usuario no 0010 debe estar logueado.
  88  |     
  89  | 
  90  |     // SETUP
  91  |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  92  |     await page.screenshot({ path: 'evidence/116/P04/step_00_setup.png' });
  93  | 
  94  |     // Expand "Búsqueda Avanzada" panel only when needed.
  95  |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  96  |     const advancedPanel = page.locator('#c_pnlBusqueda');
  97  |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  98  |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  99  |     if (!filtersReady) {
  100 |       const toggleByHeader = page.locator('.collapsible-header:has-text("Búsqueda Avanzada"), li:has-text("Búsqueda Avanzada") .collapsible-header').first();
  101 |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  102 |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  103 | 
  104 |       if (await toggleByHeader.count()) {
  105 |         await toggleByHeader.scrollIntoViewIfNeeded();
  106 |         await toggleByHeader.click({ timeout: 5000, force: true });
  107 |       } else if (await toggleByData.count()) {
  108 |         await toggleByData.click({ timeout: 5000, force: true });
  109 |       } else if (await toggleByText.count()) {
  110 |         await toggleByText.click({ timeout: 5000, force: true });
  111 |       }
  112 | 
  113 |       if (await advancedPanel.count()) {
  114 |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  115 |       }
  116 |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  117 | 
  118 |       // Last-resort fallback for legacy WebForms layouts where the toggle
  119 |       // exists but does not update aria/visibility attributes consistently.
  120 |       if (!filtersReady && await advancedPanel.count()) {
  121 |         await page.evaluate(() => {
  122 |           const pnl = document.querySelector('#c_pnlBusqueda') as HTMLElement | null;
  123 |           if (pnl) {
  124 |             pnl.style.display = 'block';
  125 |             pnl.classList.add('active');
  126 |           }
  127 |         });
  128 |         filtersReady = await firstFilter.first().isVisible().catch(() => false);
  129 |       }
  130 |     }
  131 |     console.log('Advanced filters ready:', filtersReady);
  132 |     await page.screenshot({ path: 'screenshots/P04_panel_expanded.png' });
  133 | 
  134 |     // ACTION
  135 |     
  136 |     
  137 |     // [STEP 01] wait visible panel_agenda
  138 |     await expect(page.locator('#c_updAgenda')).toBeVisible({ timeout: 10000 });
  139 |     
  140 |     
  141 | 
  142 |     // ASSERTIONS
  143 |     
  144 |     
> 145 |     await expect(page.locator('#updTimer'), 'P04: panel_timer debe ser visible').toBeVisible();
      |                                                                                  ^ Error: P04: panel_timer debe ser visible
  146 |     
  147 |     
  148 |     
  149 |     await expect(page.locator('#TimerSession'), 'P04: panel_timer_session no debe ser visible').toBeHidden();
  150 |     
  151 |     
  152 | 
  153 |     // CLEANUP
  154 |     await page.context().clearCookies();
  155 |   });
  156 | 
  157 |   test.afterEach(async ({ page }) => {
  158 |     // Capture final state screenshot first — fail-safe even if the page is
  159 |     // mid-PostBack.
  160 |     try {
  161 |       await page.screenshot({
  162 |         path: 'evidence/116/P04/step_final_state.png',
  163 |       });
  164 |     } catch (_e) {
  165 |       // ignore — page may be closed or navigating
  166 |     }
  167 | 
  168 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  169 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  170 |     // relying on Playwright's pass/fail (which conflates product defects
  171 |     // with pipeline defects).
  172 |     const captured: any[] = [];
  173 |     for (const probe of ORACLE_PROBES) {
  174 |       const entry: any = {
  175 |         oracle_id: probe.oracle_id,
  176 |         target: probe.target,
  177 |         tipo: probe.tipo,
  178 |         expected: probe.expected,
  179 |       };
  180 |       try {
  181 |         if (probe.selector === null) {
  182 |           // Whole-page oracle: capture the body text once (truncated).
  183 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  184 |           entry.actual_text = bodyText.slice(0, 4000);
  185 |           entry.visible = true;
  186 |         } else {
  187 |           const loc = page.locator(probe.selector);
  188 |           // count
  189 |           const count = await loc.count();
  190 |           entry.count = count;
  191 |           if (count === 0) {
  192 |             entry.visible = false;
  193 |             entry.actual_text = null;
  194 |           } else {
  195 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  196 |             // value (form controls)
  197 |             try {
  198 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  199 |             } catch (_e) { /* not a form control */ }
  200 |             // textContent
  201 |             try {
  202 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  203 |               entry.actual_text = txt.slice(0, 1000);
  204 |             } catch (_e) {
  205 |               entry.actual_text = null;
  206 |             }
  207 |             // disabled / state
  208 |             try {
  209 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  210 |             } catch (_e) { /* ignore */ }
  211 |           }
  212 |         }
  213 |       } catch (e: any) {
  214 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  215 |       }
  216 |       captured.push(entry);
  217 |     }
  218 | 
  219 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
  220 |     // must not break the test runner.
  221 |     try {
  222 |       const outPath = path.resolve(process.cwd(), ASSERTIONS_OUT_PATH);
  223 |       fs.mkdirSync(path.dirname(outPath), { recursive: true });
  224 |       fs.writeFileSync(
  225 |         outPath,
  226 |         JSON.stringify(
  227 |           { scenario_id: 'P04', assertions: captured },
  228 |           null, 2,
  229 |         ),
  230 |         'utf-8',
  231 |       );
  232 |     } catch (e) {
  233 |       console.error('[afterEach] could not persist assertions json:', e);
  234 |     }
  235 | 
  236 |     // Persist step_bboxes.json for screenshot_annotator.py (Fase 2).
  237 |     // Non-fatal: if this fails the pipeline continues without annotations.
  238 |     if (STEP_BBOXES.length > 0) {
  239 |       try {
  240 |         const bboxOutPath = path.resolve(process.cwd(), STEP_BBOXES_OUT_PATH);
  241 |         fs.mkdirSync(path.dirname(bboxOutPath), { recursive: true });
  242 |         fs.writeFileSync(bboxOutPath, JSON.stringify(STEP_BBOXES, null, 2), 'utf-8');
  243 |       } catch (e) {
  244 |         console.error('[afterEach] could not persist step_bboxes json:', e);
  245 |       }
```