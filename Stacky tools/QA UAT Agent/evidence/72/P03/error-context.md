# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: 72\tests\P03_filtro_debito_auto_no.spec.ts >> ADO-72 | P03 — Filtro Débito Auto = No >> p03 filtro_débito_auto_=_no
- Location: evidence\72\tests\P03_filtro_debito_auto_no.spec.ts:80:7

# Error details

```
TimeoutError: locator.selectOption: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('#c_ddlDebitoAuto')

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
          - link "USUARIO TEST" [ref=e21] [cursor=pointer]:
            - /url: FrmCambioPass.aspx
        - generic [ref=e23]:
          - generic [ref=e24]: "Pendiente de Hoy:"
          - generic [ref=e25]: "0"
        - generic [ref=e27]:
          - generic [ref=e28]: "Pendiente de otros Días:"
          - generic [ref=e29]: "17"
        - generic [ref=e31]:
          - generic [ref=e32]: "Realizado Hoy:"
          - generic [ref=e33]: "2"
        - generic [ref=e35]:
          - generic [ref=e36]: "Total en Agenda:"
          - generic [ref=e37]: "19"
        - generic [ref=e39]:
          - generic [ref=e40]: "Barrido Realizado:"
          - generic [ref=e41]: 11%
        - generic [ref=e43]:
          - generic [ref=e44]: "Clientes Asignados:"
          - generic [ref=e45]: "0"
  - list [ref=e46]:
    - listitem [ref=e47]:
      - generic [ref=e48]:
        - generic: format_list_bulleted
        - text: Cobranza Prejudicial
      - list [ref=e50]:
        - listitem [ref=e51]:
          - link "event Agenda Personal" [ref=e52] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmAgenda.aspx
            - generic: event
            - text: Agenda Personal
        - listitem [ref=e53]:
          - link "event_note Pooles de Trabajo" [ref=e54] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmAgenda.aspx?q=rh3wPkybH+atHWY9zjvV4w==
            - generic: event_note
            - text: Pooles de Trabajo
        - listitem [ref=e55]:
          - link "search Busqueda de Clientes" [ref=e56] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmBusqueda.aspx
            - generic: search
            - text: Busqueda de Clientes
        - listitem [ref=e57]:
          - link "date_range Agenda de Grupo" [ref=e58] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmAgendaEquipo.aspx
            - generic: date_range
            - text: Agenda de Grupo
        - listitem [ref=e59]:
          - list [ref=e60]:
            - listitem [ref=e61]:
              - generic [ref=e62] [cursor=pointer]:
                - generic: format_list_bulleted
                - text: Supervision
            - listitem [ref=e63]:
              - list [ref=e64]:
                - listitem [ref=e65]:
                  - generic [ref=e66] [cursor=pointer]:
                    - generic: format_list_bulleted
                    - text: Reportes Operativos
                - listitem [ref=e67]:
                  - list [ref=e68]:
                    - listitem [ref=e69]:
                      - generic [ref=e70] [cursor=pointer]:
                        - generic: format_list_bulleted
                        - text: Reportes OBI
    - listitem [ref=e71]:
      - generic [ref=e72]:
        - generic: format_list_bulleted
        - text: Cobranza Judicial
      - list [ref=e74]:
        - listitem [ref=e75]:
          - link "event Agenda De Demandas" [ref=e76] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmAgendaJudicial.aspx
            - generic: event
            - text: Agenda De Demandas
        - listitem [ref=e77]:
          - link "search Buscar Demandas" [ref=e78] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmBusquedaJudicial.aspx
            - generic: search
            - text: Buscar Demandas
        - listitem [ref=e79]:
          - link "rule Validar Gastos" [ref=e80] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmValidacionGastosJudicial.aspx
            - generic: rule
            - text: Validar Gastos
        - listitem [ref=e81]:
          - link "confirmation_number Liquidar Gastos" [ref=e82] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmLiquidarGastos.aspx
            - generic: confirmation_number
            - text: Liquidar Gastos
        - listitem [ref=e83]:
          - link "switch_account Reasignar Abogado" [ref=e84] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmJReasignarAbogado.aspx
            - generic: switch_account
            - text: Reasignar Abogado
        - listitem [ref=e85]:
          - list [ref=e86]:
            - listitem [ref=e87]:
              - generic [ref=e88] [cursor=pointer]:
                - generic: format_list_bulleted
                - text: Reportes Operativos
            - listitem [ref=e89]:
              - list [ref=e90]:
                - listitem [ref=e91]:
                  - generic [ref=e92] [cursor=pointer]:
                    - generic: format_list_bulleted
                    - text: Reportes OBI
    - listitem [ref=e93]:
      - generic [ref=e94]:
        - generic: format_list_bulleted
        - text: Facturación y Gastos
      - list [ref=e96]:
        - listitem [ref=e97]:
          - link "rule Validar Facturas" [ref=e98] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FiScu1K/9opoNFBT3rUlgpvM=
            - generic: rule
            - text: Validar Facturas
        - listitem [ref=e99]:
          - link "rule Validar Notas de Gastos" [ref=e100] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=V7lQE0kItNVN2Y7dSl7FieWKk8YQotwBcHU/2DP3KIw=
            - generic: rule
            - text: Validar Notas de Gastos
        - listitem [ref=e101]:
          - link "receipt Facturas" [ref=e102] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiHOOp6prF5Vq+94RnI70taQ=
            - generic: receipt
            - text: Facturas
        - listitem [ref=e103]:
          - link "confirmation_number Notas de Gastos" [ref=e104] [cursor=pointer]:
            - /url: /AgendaWebRipleyCHI/FrmLiquidaciones.aspx?q=ught2GWZJBvaEArAcf6NiEmPUsCvT75NbJGKOtz0/0Y=
            - generic: confirmation_number
            - text: Notas de Gastos
    - listitem [ref=e105]:
      - separator [ref=e106]
    - listitem [ref=e107]:
      - link "settings Administrador" [ref=e108] [cursor=pointer]:
        - /url: /AgendaWebRipleyCHI/FrmAdministrador.aspx
        - generic: settings
        - text: Administrador
    - listitem [ref=e109]
    - listitem [ref=e110]
  - generic [ref=e111]:
    - generic [ref=e115]:
      - link "Acciones" [ref=e116] [cursor=pointer]:
        - /url: "#!"
      - link "chevron_right Avanzar" [ref=e117] [cursor=pointer]:
        - /url: javascript:__doPostBack('ctl00$btnNext','')
        - generic: chevron_right
        - text: Avanzar
    - list [ref=e118]:
      - listitem [ref=e119]:
        - generic [active] [ref=e120] [cursor=pointer]:
          - generic [ref=e121]: search
          - generic [ref=e122]: Búsqueda Avanzada
        - generic [ref=e125]:
          - generic [ref=e126]:
            - generic [ref=e127]:
              - textbox "Desde" [ref=e128]
              - generic [ref=e129]: Desde
            - generic [ref=e130]:
              - textbox "Hasta" [ref=e131]
              - generic [ref=e132]: Hasta
            - generic [ref=e133]:
              - generic [ref=e134]: Empresa
              - combobox "Todas" [ref=e137] [cursor=pointer]:
                - generic "Todas" [ref=e138]
            - generic [ref=e140]:
              - generic [ref=e141]: Perfil
              - combobox "Todos" [ref=e144] [cursor=pointer]:
                - generic "Todos" [ref=e145]
          - generic [ref=e147]:
            - generic [ref=e148]:
              - generic [ref=e149]: Región
              - combobox "Todas" [ref=e152] [cursor=pointer]:
                - generic "Todas" [ref=e153]
            - generic [ref=e155]:
              - generic [ref=e156]: Recomendación
              - combobox "Todas" [ref=e159] [cursor=pointer]:
                - generic "Todas" [ref=e160]
            - generic [ref=e162]:
              - generic [ref=e163]: Nivel de Mora
              - combobox "Sin Asignar" [ref=e166] [cursor=pointer]:
                - generic "Sin Asignar" [ref=e167]
            - generic [ref=e169]:
              - generic [ref=e170]: Tipo de Cliente
              - combobox "Todos" [ref=e173] [cursor=pointer]:
                - generic "Todos" [ref=e174]
          - generic [ref=e176]:
            - generic [ref=e177]:
              - textbox "Ventil" [ref=e178]
              - generic [ref=e179]: Ventil
            - generic [ref=e180]:
              - generic [ref=e181]: Campaña
              - combobox "Todas" [ref=e184] [cursor=pointer]:
                - generic "Todas" [ref=e185]
          - link "search Filtrar" [ref=e189] [cursor=pointer]:
            - /url: javascript:__doPostBack('ctl00$c$btnOk','')
            - generic: search
            - text: Filtrar
    - generic [ref=e190]:
      - generic [ref=e192]: Agendados por Usuario
      - table [ref=e195]:
        - rowgroup [ref=e196]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora" [ref=e197]:
            - columnheader "Cliente" [ref=e198]:
              - link "Cliente" [ref=e199] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$CLIENTE')
            - columnheader "Lote" [ref=e200]:
              - link "Lote" [ref=e201] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$LOCOD')
            - columnheader "Fecha" [ref=e202]:
              - link "Fecha" [ref=e203] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGFECREC')
            - columnheader "Hora" [ref=e204]:
              - link "Hora" [ref=e205] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e206]:
              - link "Recomendación" [ref=e207] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e208]:
              - link "Nivel Mora" [ref=e209] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaUsu','Sort$NIVELMORA')
      - generic [ref=e210]:
        - generic [ref=e211]: Agendados por Motor Experto
        - link "grid_on Agendados por Motor Experto" [ref=e213] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnExportExcelAg','')
          - generic: grid_on
          - text: Agendados por Motor Experto
      - table [ref=e215]:
        - rowgroup [ref=e216]:
          - row "Cliente Lote Fecha Hora Recomendación Nivel Mora" [ref=e217]:
            - columnheader "Cliente" [ref=e218]:
              - link "Cliente" [ref=e219] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$CLIENTE')
            - columnheader "Lote" [ref=e220]:
              - link "Lote" [ref=e221] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$LOCOD')
            - columnheader "Fecha" [ref=e222]:
              - link "Fecha" [ref=e223] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGFECREC')
            - columnheader "Hora" [ref=e224]:
              - link "Hora" [ref=e225] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$AGHORAREC')
            - columnheader "Recomendación" [ref=e226]:
              - link "Recomendación" [ref=e227] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$RECOMENDACION')
            - columnheader "Nivel Mora" [ref=e228]:
              - link "Nivel Mora" [ref=e229] [cursor=pointer]:
                - /url: javascript:__doPostBack('ctl00$c$GridAgendaAut','Sort$NIVELMORA')
        - rowgroup [ref=e230]:
          - row "6499714 6499714 6499714 6499714 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e231]:
            - cell "6499714 6499714 6499714" [ref=e232] [cursor=pointer]
            - cell "6499714" [ref=e233] [cursor=pointer]
            - cell "03/12/2025" [ref=e234] [cursor=pointer]
            - cell "14:53:44" [ref=e235] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e236] [cursor=pointer]
            - cell [ref=e237] [cursor=pointer]
          - row "12406972 12406972 12406972 12406972 03/12/2025 14:53:45 EDPP - Compromiso de pago" [ref=e238]:
            - cell "12406972 12406972 12406972" [ref=e239] [cursor=pointer]
            - cell "12406972" [ref=e240] [cursor=pointer]
            - cell "03/12/2025" [ref=e241] [cursor=pointer]
            - cell "14:53:45" [ref=e242] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e243] [cursor=pointer]
            - cell [ref=e244] [cursor=pointer]
          - row "12266465 12266465 12266465 12266465 03/12/2025 14:53:45 EDPP - Compromiso de pago" [ref=e245]:
            - cell "12266465 12266465 12266465" [ref=e246] [cursor=pointer]
            - cell "12266465" [ref=e247] [cursor=pointer]
            - cell "03/12/2025" [ref=e248] [cursor=pointer]
            - cell "14:53:45" [ref=e249] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e250] [cursor=pointer]
            - cell [ref=e251] [cursor=pointer]
          - row "19559074 19559074 19559074 19559074 03/12/2025 14:53:45 EDPP - Compromiso de pago" [ref=e252]:
            - cell "19559074 19559074 19559074" [ref=e253] [cursor=pointer]
            - cell "19559074" [ref=e254] [cursor=pointer]
            - cell "03/12/2025" [ref=e255] [cursor=pointer]
            - cell "14:53:45" [ref=e256] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e257] [cursor=pointer]
            - cell [ref=e258] [cursor=pointer]
          - row "12272340 12272340 12272340 12272340 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e259]:
            - cell "12272340 12272340 12272340" [ref=e260] [cursor=pointer]
            - cell "12272340" [ref=e261] [cursor=pointer]
            - cell "03/12/2025" [ref=e262] [cursor=pointer]
            - cell "14:53:44" [ref=e263] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e264] [cursor=pointer]
            - cell [ref=e265] [cursor=pointer]
          - row "12261570 12261570 12261570 12261570 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e266]:
            - cell "12261570 12261570 12261570" [ref=e267] [cursor=pointer]
            - cell "12261570" [ref=e268] [cursor=pointer]
            - cell "03/12/2025" [ref=e269] [cursor=pointer]
            - cell "14:53:44" [ref=e270] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e271] [cursor=pointer]
            - cell [ref=e272] [cursor=pointer]
          - row "12285038 12285038 12285038 12285038 03/12/2025 14:53:44 EDPP - Compromiso de pago" [ref=e273]:
            - cell "12285038 12285038 12285038" [ref=e274] [cursor=pointer]
            - cell "12285038" [ref=e275] [cursor=pointer]
            - cell "03/12/2025" [ref=e276] [cursor=pointer]
            - cell "14:53:44" [ref=e277] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e278] [cursor=pointer]
            - cell [ref=e279] [cursor=pointer]
          - row "10396023 10396023 10396023 10396023 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e280]:
            - cell "10396023 10396023 10396023" [ref=e281] [cursor=pointer]
            - cell "10396023" [ref=e282] [cursor=pointer]
            - cell "03/12/2025" [ref=e283] [cursor=pointer]
            - cell "14:53:43" [ref=e284] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e285] [cursor=pointer]
            - cell [ref=e286] [cursor=pointer]
          - row "15471591 15471591 15471591 15471591 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e287]:
            - cell "15471591 15471591 15471591" [ref=e288] [cursor=pointer]
            - cell "15471591" [ref=e289] [cursor=pointer]
            - cell "03/12/2025" [ref=e290] [cursor=pointer]
            - cell "14:53:43" [ref=e291] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e292] [cursor=pointer]
            - cell [ref=e293] [cursor=pointer]
          - row "12256873 12256873 12256873 12256873 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e294]:
            - cell "12256873 12256873 12256873" [ref=e295] [cursor=pointer]
            - cell "12256873" [ref=e296] [cursor=pointer]
            - cell "03/12/2025" [ref=e297] [cursor=pointer]
            - cell "14:53:43" [ref=e298] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e299] [cursor=pointer]
            - cell [ref=e300] [cursor=pointer]
          - row "12242167 12242167 12242167 12242167 03/12/2025 14:53:43 EDPP - Compromiso de pago" [ref=e301]:
            - cell "12242167 12242167 12242167" [ref=e302] [cursor=pointer]
            - cell "12242167" [ref=e303] [cursor=pointer]
            - cell "03/12/2025" [ref=e304] [cursor=pointer]
            - cell "14:53:43" [ref=e305] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e306] [cursor=pointer]
            - cell [ref=e307] [cursor=pointer]
          - row "12326138 12326138 12326138 12326138 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e308]:
            - cell "12326138 12326138 12326138" [ref=e309] [cursor=pointer]
            - cell "12326138" [ref=e310] [cursor=pointer]
            - cell "03/12/2025" [ref=e311] [cursor=pointer]
            - cell "14:53:42" [ref=e312] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e313] [cursor=pointer]
            - cell [ref=e314] [cursor=pointer]
          - row "12271212 12271212 12271212 12271212 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e315]:
            - cell "12271212 12271212 12271212" [ref=e316] [cursor=pointer]
            - cell "12271212" [ref=e317] [cursor=pointer]
            - cell "03/12/2025" [ref=e318] [cursor=pointer]
            - cell "14:53:42" [ref=e319] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e320] [cursor=pointer]
            - cell [ref=e321] [cursor=pointer]
          - row "16417065 16417065 16417065 16417065 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e322]:
            - cell "16417065 16417065 16417065" [ref=e323] [cursor=pointer]
            - cell "16417065" [ref=e324] [cursor=pointer]
            - cell "03/12/2025" [ref=e325] [cursor=pointer]
            - cell "14:53:42" [ref=e326] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e327] [cursor=pointer]
            - cell [ref=e328] [cursor=pointer]
          - row "12405368 12405368 12405368 12405368 03/12/2025 14:53:42 EDPP - Compromiso de pago" [ref=e329]:
            - cell "12405368 12405368 12405368" [ref=e330] [cursor=pointer]
            - cell "12405368" [ref=e331] [cursor=pointer]
            - cell "03/12/2025" [ref=e332] [cursor=pointer]
            - cell "14:53:42" [ref=e333] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e334] [cursor=pointer]
            - cell [ref=e335] [cursor=pointer]
          - row "15317201 15317201 15317201 15317201 03/12/2025 14:53:41 EDPP - Compromiso de pago" [ref=e336]:
            - cell "15317201 15317201 15317201" [ref=e337] [cursor=pointer]
            - cell "15317201" [ref=e338] [cursor=pointer]
            - cell "03/12/2025" [ref=e339] [cursor=pointer]
            - cell "14:53:41" [ref=e340] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e341] [cursor=pointer]
            - cell [ref=e342] [cursor=pointer]
          - row "12355359 12355359 12355359 12355359 03/12/2025 14:53:40 EDPP - Compromiso de pago" [ref=e343]:
            - cell "12355359 12355359 12355359" [ref=e344] [cursor=pointer]
            - cell "12355359" [ref=e345] [cursor=pointer]
            - cell "03/12/2025" [ref=e346] [cursor=pointer]
            - cell "14:53:40" [ref=e347] [cursor=pointer]
            - cell "EDPP - Compromiso de pago" [ref=e348] [cursor=pointer]
            - cell [ref=e349] [cursor=pointer]
        - rowgroup
```

# Test source

```ts
  35  |   {
  36  |     oracle_id: 0,
  37  |     target: "table_agenda_aut",
  38  |     tipo: "count_eq",
  39  |     expected: 2,
  40  |     selector: "#c_GridAgendaAut"
  41  |   },
  42  | 
  43  |   {
  44  |     oracle_id: 1,
  45  |     target: "table_agenda_usu",
  46  |     tipo: "count_eq",
  47  |     expected: 2,
  48  |     selector: "#c_GridAgendaUsu"
  49  |   },
  50  | 
  51  | ];
  52  | const ASSERTIONS_OUT_PATH = 'evidence/72/P03/assertions_P03.json';
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
  64  | const STEP_BBOXES_OUT_PATH = 'evidence/72/P03/step_bboxes.json';
  65  | 
  66  | 
  67  | test.describe('ADO-72 | P03 — Filtro Débito Auto = No', () => {
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
  80  |   test('p03 filtro_débito_auto_=_no', async ({ page }) => {
  81  |     // DATA: N/A
  82  | 
  83  |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  84  |     
  85  | 
  86  |     // SETUP
  87  |     await page.goto(`${BASE_URL}FrmAgenda.aspx`, { waitUntil: 'load' });
  88  |     await page.screenshot({ path: 'evidence/72/P03/step_00_setup.png' });
  89  | 
  90  |     // Expand "Búsqueda Avanzada" panel only when needed.
  91  |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  92  |     const advancedPanel = page.locator('#c_pnlBusqueda');
  93  |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  94  |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  95  |     if (!filtersReady) {
  96  |       const toggleByHeader = page.locator('.collapsible-header:has-text("Búsqueda Avanzada"), li:has-text("Búsqueda Avanzada") .collapsible-header').first();
  97  |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  98  |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  99  | 
  100 |       if (await toggleByHeader.count()) {
  101 |         await toggleByHeader.scrollIntoViewIfNeeded();
  102 |         await toggleByHeader.click({ timeout: 5000, force: true });
  103 |       } else if (await toggleByData.count()) {
  104 |         await toggleByData.click({ timeout: 5000, force: true });
  105 |       } else if (await toggleByText.count()) {
  106 |         await toggleByText.click({ timeout: 5000, force: true });
  107 |       }
  108 | 
  109 |       if (await advancedPanel.count()) {
  110 |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  111 |       }
  112 |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  113 | 
  114 |       // Last-resort fallback for legacy WebForms layouts where the toggle
  115 |       // exists but does not update aria/visibility attributes consistently.
  116 |       if (!filtersReady && await advancedPanel.count()) {
  117 |         await page.evaluate(() => {
  118 |           const pnl = document.querySelector('#c_pnlBusqueda') as HTMLElement | null;
  119 |           if (pnl) {
  120 |             pnl.style.display = 'block';
  121 |             pnl.classList.add('active');
  122 |           }
  123 |         });
  124 |         filtersReady = await firstFilter.first().isVisible().catch(() => false);
  125 |       }
  126 |     }
  127 |     console.log('Advanced filters ready:', filtersReady);
  128 |     await page.screenshot({ path: 'screenshots/P03_panel_expanded.png' });
  129 | 
  130 |     // ACTION
  131 |     
  132 |     
  133 |     // [STEP 01] select No in select_debito_auto
  134 |     console.log('[STEP 01] select select_debito_auto');
> 135 |     await page.locator("#c_ddlDebitoAuto").selectOption('No', { force: true });;
      |                                            ^ TimeoutError: locator.selectOption: Timeout 10000ms exceeded.
  136 |     await page.screenshot({ path: 'evidence/72/P03/step_01_after.png' });
  137 |     STEP_BBOXES.push({ step_index: 1, screenshot_path: 'evidence/72/P03/step_01_after.png', target: "select_debito_auto", bbox: await page.locator("#c_ddlDebitoAuto").boundingBox().catch(() => null) });
  138 |     
  139 |     
  140 |     
  141 |     
  142 |     // [STEP 02] click link_c_btnok
  143 |     console.log('[STEP 02] click link_c_btnok');
  144 |     await page.locator("#c_btnOk").click({ force: true });
  145 |     await page.waitForLoadState('load');
  146 |     await page.screenshot({ path: 'evidence/72/P03/step_02_after.png' });
  147 |     STEP_BBOXES.push({ step_index: 2, screenshot_path: 'evidence/72/P03/step_02_after.png', target: "link_c_btnok", bbox: await page.locator("#c_btnOk").boundingBox().catch(() => null) });
  148 |     
  149 |     
  150 |     
  151 | 
  152 |     // ASSERTIONS
  153 |     
  154 |     
  155 |     {
  156 |       const rowCount = await page.locator('#c_GridAgendaAut tbody tr').count();
  157 |       await expect(rowCount, 'P03: table_agenda_aut rows debe ser == 2').toBe(2);
  158 |     }
  159 |     
  160 |     
  161 |     
  162 |     {
  163 |       const rowCount = await page.locator('#c_GridAgendaUsu tbody tr').count();
  164 |       await expect(rowCount, 'P03: table_agenda_usu rows debe ser == 2').toBe(2);
  165 |     }
  166 |     
  167 |     
  168 | 
  169 |     // CLEANUP
  170 |     await page.context().clearCookies();
  171 |   });
  172 | 
  173 |   test.afterEach(async ({ page }) => {
  174 |     // Capture final state screenshot first — fail-safe even if the page is
  175 |     // mid-PostBack.
  176 |     try {
  177 |       await page.screenshot({
  178 |         path: 'evidence/72/P03/step_final_state.png',
  179 |       });
  180 |     } catch (_e) {
  181 |       // ignore — page may be closed or navigating
  182 |     }
  183 | 
  184 |     // ASSERTIONS EVIDENCE — capture actual values for every oracle so
  185 |     // uat_assertion_evaluator.py can reconcile expected vs actual without
  186 |     // relying on Playwright's pass/fail (which conflates product defects
  187 |     // with pipeline defects).
  188 |     const captured: any[] = [];
  189 |     for (const probe of ORACLE_PROBES) {
  190 |       const entry: any = {
  191 |         oracle_id: probe.oracle_id,
  192 |         target: probe.target,
  193 |         tipo: probe.tipo,
  194 |         expected: probe.expected,
  195 |       };
  196 |       try {
  197 |         if (probe.selector === null) {
  198 |           // Whole-page oracle: capture the body text once (truncated).
  199 |           const bodyText = (await page.locator('body').innerText({ timeout: 2000 })) || '';
  200 |           entry.actual_text = bodyText.slice(0, 4000);
  201 |           entry.visible = true;
  202 |         } else {
  203 |           const loc = page.locator(probe.selector);
  204 |           // count
  205 |           const count = await loc.count();
  206 |           entry.count = count;
  207 |           if (count === 0) {
  208 |             entry.visible = false;
  209 |             entry.actual_text = null;
  210 |           } else {
  211 |             entry.visible = await loc.first().isVisible({ timeout: 2000 });
  212 |             // value (form controls)
  213 |             try {
  214 |               entry.value = await loc.first().inputValue({ timeout: 1000 });
  215 |             } catch (_e) { /* not a form control */ }
  216 |             // textContent
  217 |             try {
  218 |               const txt = (await loc.first().innerText({ timeout: 1500 })) || '';
  219 |               entry.actual_text = txt.slice(0, 1000);
  220 |             } catch (_e) {
  221 |               entry.actual_text = null;
  222 |             }
  223 |             // disabled / state
  224 |             try {
  225 |               entry.state = (await loc.first().isDisabled({ timeout: 500 })) ? 'disabled' : 'enabled';
  226 |             } catch (_e) { /* ignore */ }
  227 |           }
  228 |         }
  229 |       } catch (e: any) {
  230 |         entry.capture_error = String(e && e.message ? e.message : e).slice(0, 300);
  231 |       }
  232 |       captured.push(entry);
  233 |     }
  234 | 
  235 |     // Persist assertions_<sid>.json. mkdir is safe-recursive; failures here
```