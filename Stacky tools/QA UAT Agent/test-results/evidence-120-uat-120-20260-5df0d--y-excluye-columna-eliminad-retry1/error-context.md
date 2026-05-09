# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: evidence\120\uat-120-20260509T213329Z-cc5262\tests\P12_exportacion_incluye_nuevos_campos_y_excluye_column.spec.ts >> ADO-120 | P12 — Exportacion incluye nuevos campos y excluye columna eliminada (si aplica) >> p12 exportacion_incluye_nuevos_campos_y_excluye_columna_eliminad
- Location: evidence\120\uat-120-20260509T213329Z-cc5262\tests\P12_exportacion_incluye_nuevos_campos_y_excluye_column.spec.ts:180:7

# Error details

```
TimeoutError: page.goto: Timeout 20000ms exceeded.
Call log:
  - navigating to "http://localhost:35017/AgendaWeb/FrmDetalleClie.aspx", waiting until "domcontentloaded"

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
      - generic [ref=e15]: Detalle de Cliente
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
    - link "chevron_left agenda personal" [ref=e118] [cursor=pointer]:
      - /url: javascript:__doPostBack('ctl00$btnBack','')
      - generic: chevron_left
      - text: agenda personal
    - generic [ref=e121]:
      - generic [ref=e122]:
        - generic [ref=e123]:
          - generic [ref=e124]:
            - textbox "Apellidos y Nombre" [ref=e125]
            - generic [ref=e126]: Apellidos y Nombre
          - generic [ref=e127]:
            - textbox "Usuario" [ref=e128]
            - generic [ref=e129]: Usuario
          - generic [ref=e130]:
            - textbox "Documento" [ref=e131]
            - generic [ref=e132]: Documento
          - generic [ref=e133]:
            - textbox "Perfil" [ref=e134]
            - generic [ref=e135]: Perfil
          - generic [ref=e136]:
            - textbox "Núm. Cliente" [ref=e137]
            - generic [ref=e138]: Núm. Cliente
          - generic [ref=e139]:
            - textbox "Nivel de Mora" [ref=e140]
            - generic [ref=e141]: Nivel de Mora
          - generic [ref=e142]:
            - textbox "Categoria Cliente" [ref=e143]
            - generic [ref=e144]: Categoria Cliente
          - generic [ref=e145]:
            - textbox "Tipo Cliente" [ref=e146]
            - generic [ref=e147]: Tipo Cliente
        - generic [ref=e149]:
          - textbox "Atraso Total" [ref=e150]
          - generic [ref=e151]: Atraso Total
        - table [ref=e157]:
          - rowgroup [ref=e158]:
            - row "Teléfono" [ref=e159]:
              - columnheader "Teléfono" [ref=e160]
      - generic [ref=e162]:
        - link "COMPROMISOS" [ref=e163] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnCompromisos','')
        - link "Convenios" [ref=e164] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnConvenios','')
        - link "PASAR A JUDICIAL" [ref=e165] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnPasajeJudicial','')
        - link "Judicial" [ref=e166] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnJudicial','')
        - link "Documentación" [ref=e167] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnDocumento','')
        - link "FICHA" [ref=e168] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnFicha','')
        - link "NOTAS" [ref=e169] [cursor=pointer]:
          - /url: javascript:__doPostBack('ctl00$c$btnNotas','')
    - generic [ref=e172]:
      - generic [ref=e173]: PVIG
      - generic [ref=e174]: PINC
      - generic [ref=e175]: DLOC
      - generic [ref=e176]: INAC
      - generic [ref=e177]: CREF
    - generic [ref=e179]:
      - list [ref=e181]:
        - listitem [ref=e182]:
          - link "Datos Generales" [ref=e183] [cursor=pointer]:
            - /url: "#c_tabGenerales"
        - listitem [ref=e184]:
          - link "Relaciones" [ref=e185] [cursor=pointer]:
            - /url: "#c_tabRelaciones"
        - listitem [ref=e186]:
          - link "Contactos" [ref=e187] [cursor=pointer]:
            - /url: "#c_tabContactos"
        - listitem [ref=e188]:
          - link "Pagos" [ref=e189] [cursor=pointer]:
            - /url: "#c_tabPagos"
        - listitem [ref=e190]:
          - link "Garantías" [ref=e191] [cursor=pointer]:
            - /url: "#c_tabGarantias"
        - listitem [ref=e192]:
          - link "Scoring" [ref=e193] [cursor=pointer]:
            - /url: "#c_tabScorings"
        - listitem [ref=e194]:
          - link "Datos Historicos" [ref=e195] [cursor=pointer]:
            - /url: "#c_tabHistoricos"
        - listitem [ref=e196]
      - generic [ref=e198]:
        - generic [ref=e199]:
          - generic [ref=e201]: Obligación *
          - table [ref=e204]:
            - rowgroup [ref=e205]:
              - row "Cód. Obligación Producto Días Mora Ingreso Judicial Moneda Región Oficina Fecha Inicio Fecha Venc. Fecha Mora Fecha Últ. Pago Monto Últ. Pago Fecha Castigo Monto Castigo Fec. Prim. Impago Tipo Cuenta Débito Cuenta Débito Es Judicial Fecha Prox Venc Importe Prox Venc Fecha Mora Motivo No Cobro" [ref=e206]:
                - columnheader [ref=e207]
                - columnheader [ref=e208]
                - columnheader "Cód. Obligación" [ref=e209]
                - columnheader "Producto" [ref=e210]
                - columnheader "Días Mora" [ref=e211]
                - columnheader "Ingreso Judicial" [ref=e212]
                - columnheader "Moneda" [ref=e213]
                - columnheader "Región" [ref=e214]
                - columnheader "Oficina" [ref=e215]
                - columnheader "Fecha Inicio" [ref=e216]
                - columnheader "Fecha Venc." [ref=e217]
                - columnheader "Fecha Mora" [ref=e218]
                - columnheader "Fecha Últ. Pago" [ref=e219]
                - columnheader "Monto Últ. Pago" [ref=e220]
                - columnheader "Fecha Castigo" [ref=e221]
                - columnheader "Monto Castigo" [ref=e222]
                - columnheader "Fec. Prim. Impago" [ref=e223]
                - columnheader "Tipo Cuenta Débito" [ref=e224]
                - columnheader "Cuenta Débito" [ref=e225]
                - columnheader "Es Judicial" [ref=e226]
                - columnheader "Fecha Prox Venc" [ref=e227]
                - columnheader "Importe Prox Venc" [ref=e228]
                - columnheader "Fecha Mora" [ref=e229]
                - columnheader "Motivo No Cobro" [ref=e230]
          - generic [ref=e231]:
            - generic [ref=e232]: Gestiones
            - link "event_note Ver Comentarios" [ref=e234] [cursor=pointer]:
              - /url: javascript:__doPostBack('ctl00$c$btnVerComentariosGestion','')
              - generic: event_note
              - text: Ver Comentarios
          - table [ref=e236]:
            - rowgroup [ref=e237]:
              - row "Fecha Hora TAR Nota Figura Usuario Obligación" [ref=e238]:
                - columnheader "Fecha" [ref=e239]
                - columnheader "Hora" [ref=e240]
                - columnheader "TAR" [ref=e241]
                - columnheader "Nota" [ref=e242]
                - columnheader "Figura" [ref=e243]
                - columnheader "Usuario" [ref=e244]
                - columnheader "Obligación" [ref=e245]
        - generic [ref=e246]:
          - generic [ref=e248]: Detalle Deuda
          - table [ref=e250]:
            - rowgroup [ref=e251]:
              - row "Saldo Pasivo" [ref=e252]:
                - columnheader "Saldo Pasivo" [ref=e253]:
                  - generic [ref=e254]: Saldo Pasivo
            - rowgroup [ref=e255]:
              - row "Pasivo Vista" [ref=e256]:
                - cell "Pasivo Vista" [ref=e257]:
                  - generic [ref=e258]: Pasivo Vista
                - cell [ref=e259]
              - row "Pasivo No Vista" [ref=e261]:
                - cell "Pasivo No Vista" [ref=e262]:
                  - generic [ref=e263]: Pasivo No Vista
                - cell [ref=e264]
            - rowgroup [ref=e266]:
              - row "Deuda" [ref=e267]:
                - columnheader "Deuda" [ref=e268]:
                  - generic [ref=e269]: Deuda
            - rowgroup [ref=e270]:
              - row "Fecha de Entrada" [ref=e271]:
                - cell "Fecha de Entrada" [ref=e272]:
                  - generic [ref=e273]: Fecha de Entrada
                - cell [ref=e274]
              - row "Fecha de Mora" [ref=e276]:
                - cell "Fecha de Mora" [ref=e277]:
                  - generic [ref=e278]: Fecha de Mora
                - cell [ref=e279]
              - row "Días de Mora" [ref=e281]:
                - cell "Días de Mora" [ref=e282]:
                  - generic [ref=e283]: Días de Mora
                - cell [ref=e284]
              - row "Saldo Deuda" [ref=e286]:
                - cell "Saldo Deuda" [ref=e287]:
                  - generic [ref=e288]: Saldo Deuda
                - cell [ref=e289]
              - row "Saldo Capital" [ref=e291]:
                - cell "Saldo Capital" [ref=e292]:
                  - generic [ref=e293]: Saldo Capital
                - cell [ref=e294]
              - row "Atraso Total" [ref=e296]:
                - cell "Atraso Total" [ref=e297]:
                  - generic [ref=e298]: Atraso Total
                - cell [ref=e299]
              - row "Atraso Total (Conv)" [ref=e301]:
                - cell "Atraso Total (Conv)" [ref=e302]:
                  - generic [ref=e303]: Atraso Total (Conv)
                - cell [ref=e304]
              - row "Atraso Capital" [ref=e306]:
                - cell "Atraso Capital" [ref=e307]:
                  - generic [ref=e308]: Atraso Capital
                - cell [ref=e309]
              - row "Atraso Int. Normal" [ref=e311]:
                - cell "Atraso Int. Normal" [ref=e312]:
                  - generic [ref=e313]: Atraso Int. Normal
                - cell [ref=e314]
              - row "Atraso Int. Puniorio" [ref=e316]:
                - cell "Atraso Int. Puniorio" [ref=e317]:
                  - generic [ref=e318]: Atraso Int. Puniorio
                - cell [ref=e319]
              - row "Atraso Gtos. Cobranza" [ref=e321]:
                - cell "Atraso Gtos. Cobranza" [ref=e322]:
                  - generic [ref=e323]: Atraso Gtos. Cobranza
                - cell [ref=e324]
              - row "Atraso Seguro" [ref=e326]:
                - cell "Atraso Seguro" [ref=e327]:
                  - generic [ref=e328]: Atraso Seguro
                - cell [ref=e329]
              - row "Atraso Impuesto" [ref=e331]:
                - cell "Atraso Impuesto" [ref=e332]:
                  - generic [ref=e333]: Atraso Impuesto
                - cell [ref=e334]
              - row "Atraso Otros Conceptos" [ref=e336]:
                - cell "Atraso Otros Conceptos" [ref=e337]:
                  - generic [ref=e338]: Atraso Otros Conceptos
                - cell [ref=e339]
              - row "Monto mínimo a pagar" [ref=e341]:
                - cell "Monto mínimo a pagar" [ref=e342]:
                  - generic [ref=e343]: Monto mínimo a pagar
                - cell [ref=e344]
  - list [ref=e349]:
    - listitem [ref=e350]:
      - generic [ref=e351] [cursor=pointer]:
        - generic [ref=e352]: settings
        - generic [ref=e353]: Acción / Agendar
```

# Test source

```ts
  61  | 
  62  |   {
  63  |     oracle_id: 0,
  64  |     target: "archivo_exportado",
  65  |     tipo: "page_contains_text",
  66  |     expected: "OGCANAL",
  67  |     selector: null
  68  |   },
  69  | 
  70  |   {
  71  |     oracle_id: 1,
  72  |     target: "archivo_exportado",
  73  |     tipo: "page_contains_text",
  74  |     expected: "OGMEDIOPAGO",
  75  |     selector: null
  76  |   },
  77  | 
  78  |   {
  79  |     oracle_id: 2,
  80  |     target: "archivo_exportado",
  81  |     tipo: "page_contains_text",
  82  |     expected: "OGDEBAUT_DESC",
  83  |     selector: null
  84  |   },
  85  | 
  86  |   {
  87  |     oracle_id: 3,
  88  |     target: "archivo_exportado",
  89  |     tipo: "page_contains_text",
  90  |     expected: "DESALDOFAVOR",
  91  |     selector: null
  92  |   },
  93  | 
  94  |   {
  95  |     oracle_id: 4,
  96  |     target: "archivo_exportado",
  97  |     tipo: "page_contains_text",
  98  |     expected: "OGCUOTA",
  99  |     selector: null
  100 |   },
  101 | 
  102 |   {
  103 |     oracle_id: 5,
  104 |     target: "archivo_exportado",
  105 |     tipo: "page_contains_text",
  106 |     expected: "OGMONTOCUOTA",
  107 |     selector: null
  108 |   },
  109 | 
  110 |   {
  111 |     oracle_id: 6,
  112 |     target: "archivo_exportado",
  113 |     tipo: "page_contains_text",
  114 |     expected: "OGCORREDOR",
  115 |     selector: null
  116 |   },
  117 | 
  118 |   {
  119 |     oracle_id: 7,
  120 |     target: "archivo_exportado",
  121 |     tipo: "page_contains_text",
  122 |     expected: "OGNROCUOTAS",
  123 |     selector: null
  124 |   },
  125 | 
  126 |   {
  127 |     oracle_id: 8,
  128 |     target: "archivo_exportado",
  129 |     tipo: "page_not_contains_text",
  130 |     expected: "OGFECPASAJEJUD",
  131 |     selector: null
  132 |   },
  133 | 
  134 | ];
  135 | const ASSERTIONS_OUT_PATH = 'evidence/120/P12/assertions_P12.json';
  136 | 
  137 | // STEP_BBOXES — accumulates bounding boxes of interacted elements per step.
  138 | // Written by test.afterEach to evidence/<ticket>/<sid>/step_bboxes.json and
  139 | // consumed by screenshot_annotator.py (Fase 2) to draw red boxes on screenshots.
  140 | type StepBboxEntry = {
  141 |   step_index: number;
  142 |   screenshot_path: string;
  143 |   target: string;
  144 |   bbox: { x: number; y: number; width: number; height: number } | null;
  145 | };
  146 | const STEP_BBOXES: StepBboxEntry[] = [];
  147 | const STEP_BBOXES_OUT_PATH = 'evidence/120/P12/step_bboxes.json';
  148 | 
  149 | 
  150 | // TARGET_SCREEN for this spec (declared by scenario — not inferred at runtime).
  151 | // The runner validates that the playbook/navigation arrives at this exact screen.
  152 | const TARGET_SCREEN = 'FrmDetalleClie.aspx';
  153 | 
  154 | test.describe('ADO-120 | P12 — Exportacion incluye nuevos campos y excluye columna eliminada (si aplica)', () => {
  155 | 
  156 |   test.beforeEach(async ({ page }) => {
  157 |     // Auth is restored from storageState (written by playwright/global.setup.ts).
  158 |     // NO login here — the session is already established.
  159 |     // beforeEach navigates to the DECLARED target screen (not a hardcoded fallback).
  160 |     // If we are redirected to login, the session expired — fail immediately.
> 161 |     await page.goto(`${BASE_URL}${TARGET_SCREEN}`, { waitUntil: 'domcontentloaded', timeout: 20_000 });
      |                ^ TimeoutError: page.goto: Timeout 20000ms exceeded.
  162 |     await waitForAgendaStable(page);
  163 |     const beforeEachUrl = page.url().toLowerCase();
  164 |     if (beforeEachUrl.includes('frmlogin')) {
  165 |       throw new Error(
  166 |         `[${TARGET_SCREEN}] Session expired before test start. ` +
  167 |         'Re-run the pipeline to refresh auth (global.setup.ts). ' +
  168 |         'DO NOT re-run login in specs.',
  169 |       );
  170 |     }
  171 |     // Verify we actually reached the target screen (not a redirect to another page).
  172 |     if (!beforeEachUrl.includes(TARGET_SCREEN.toLowerCase().replace('.aspx', ''))) {
  173 |       throw new Error(
  174 |         `[WRONG_SCREEN] Expected to reach ${TARGET_SCREEN} but landed on: ${page.url()}. ` +
  175 |         'Verify the playbook navigation steps and the declared target_screen.',
  176 |       );
  177 |     }
  178 |   });
  179 | 
  180 |   test('p12 exportacion_incluye_nuevos_campos_y_excluye_columna_eliminad', async ({ page }) => {
  181 |     // DATA: N/A
  182 | 
  183 |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  184 |     
  185 |     // - El usuario ha cargado la lista con datos en la Vista Obligaciones de la instancia Pacifico.
  186 |     
  187 | 
  188 |     // ── Exception & network listener setup ──────────────────────────────────
  189 |     // stepRef permite a los listeners pasivos (response / pageerror / console)
  190 |     // registrar en qué step de acción ocurrió el evento, sin pasar `page` al
  191 |     // cierre del listener.
  192 | 
  193 | 
  194 |     // SETUP
  195 |     await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded' });
  196 |     await waitForAgendaStable(page);
  197 | 
  198 |     await page.screenshot({ path: 'evidence/120/P12/step_00_setup.png' });
  199 | 
  200 |     // TARGET SCREEN VALIDATION — fail fast if wrong screen reached after navigation.
  201 |     {
  202 |       const setupUrl = page.url().toLowerCase();
  203 |       if (setupUrl.includes('frmlogin')) {
  204 |         throw new Error(
  205 |           `[BLOCKED_LOGIN_FAILED] Navigation to ${TARGET_SCREEN} redirected to login page. ` +
  206 |           'Session is invalid. Re-run the pipeline (do NOT add login logic to specs).',
  207 |         );
  208 |       }
  209 |       if (!setupUrl.includes(TARGET_SCREEN.toLowerCase().replace('.aspx', ''))) {
  210 |         throw new Error(
  211 |           `[BLOCKED_WRONG_SCREEN] Expected: ${TARGET_SCREEN} — Got: ${page.url()}. ` +
  212 |           'Check the playbook navigation steps or the declared target_screen.',
  213 |         );
  214 |       }
  215 |     }
  216 | 
  217 |     // Expand "Búsqueda Avanzada" panel only when needed.
  218 |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  219 |     const advancedPanel = page.locator('#c_pnlBusqueda');
  220 |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  221 |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  222 |     if (!filtersReady) {
  223 |       const toggleByHeader = page.locator('.collapsible-header:has-text("Búsqueda Avanzada"), li:has-text("Búsqueda Avanzada") .collapsible-header').first();
  224 |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  225 |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  226 | 
  227 |       if (await toggleByHeader.count()) {
  228 |         await toggleByHeader.scrollIntoViewIfNeeded();
  229 |         await toggleByHeader.click({ timeout: 5000 });
  230 |       } else if (await toggleByData.count()) {
  231 |         await toggleByData.scrollIntoViewIfNeeded();
  232 |         await toggleByData.click({ timeout: 5000 });
  233 |       } else if (await toggleByText.count()) {
  234 |         await toggleByText.click({ timeout: 5000 });
  235 |       }
  236 | 
  237 |       if (await advancedPanel.count()) {
  238 |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  239 |       }
  240 |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  241 | 
  242 |       // Last-resort fallback for legacy WebForms layouts where the toggle
  243 |       // exists but does not update aria/visibility attributes consistently.
  244 |       if (!filtersReady && await advancedPanel.count()) {
  245 |         await page.evaluate(() => {
  246 |           const pnl = document.querySelector('#c_pnlBusqueda') as HTMLElement | null;
  247 |           if (pnl) {
  248 |             pnl.style.display = 'block';
  249 |             pnl.classList.add('active');
  250 |           }
  251 |         });
  252 |         filtersReady = await firstFilter.first().isVisible().catch(() => false);
  253 |       }
  254 |     }
  255 |     console.log('Advanced filters ready:', filtersReady);
  256 |     await page.screenshot({ path: 'screenshots/P12_panel_expanded.png' });
  257 | 
  258 |     // ACTION
  259 |     
  260 |     
  261 |     // [STEP 01] navigate to FrmBusqueda.aspx
```