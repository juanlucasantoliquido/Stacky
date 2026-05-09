# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: evidence\120\uat-120-20260509T213329Z-cc5262\tests\P13_consistencia_de_nombre_del_corredor_con_rf_006_cor.spec.ts >> ADO-120 | P13 — Consistencia de "Nombre del Corredor" con RF-006 (Corredor Principal en cabecera) >> p13 consistencia_de_"nombre_del_corredor"_con_rf-006_(corredor_p
- Location: evidence\120\uat-120-20260509T213329Z-cc5262\tests\P13_consistencia_de_nombre_del_corredor_con_rf_006_cor.spec.ts:108:7

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
  1   | // ADO-120 P13 — Consistencia de "Nombre del Corredor" con RF-006 (Corredor Principal en cabecera)
  2   | // Generated by playwright_test_generator.py v1.1.0
  3   | // DO NOT EDIT MANUALLY — regenerate with: python playwright_test_generator.py --scenarios evidence/120/scenarios.json --ui-maps cache/ui_maps/ --out evidence/120/tests/
  4   | // Screen: FrmDetalleClie.aspx
  5   | 
  6   | 
  7   | import { test, expect } from '@playwright/test';
  8   | import * as fs from 'fs';
  9   | import * as path from 'path';
  10  | 
  11  | 
  12  | const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
  13  | 
  14  | if (!BASE_URL) throw new Error('AGENDA_WEB_BASE_URL env var is required');
  15  | 
  16  | 
  17  | 
  18  | // NOTE: AGENDA_WEB_USER / AGENDA_WEB_PASS are used only by playwright/global.setup.ts
  19  | // for the one-time login.  Specs restore auth from storageState — no login here.
  20  | 
  21  | /**
  22  |  * waitForAgendaStable — Wait for AgendaWeb / ASP.NET WebForms to settle.
  23  |  *
  24  |  * Replaces raw waitForLoadState('load') which misses UpdatePanel async PostBacks.
  25  |  * Strategy:
  26  |  *   1. Wait for DOM content parsed (domcontentloaded — fast, reliable).
  27  |  *   2. Wait for ASP.NET PageRequestManager async PostBack to finish (UpdatePanel).
  28  |  *   3. Fail-safe: if Sys is not available, resolve immediately (static pages).
  29  |  */
  30  | async function waitForAgendaStable(page: any, timeout = 10_000): Promise<void> {
  31  |   await page.waitForLoadState('domcontentloaded').catch(() => null);
  32  |   await page.waitForFunction(
  33  |     () => {
  34  |       try {
  35  |         const prm = (window as any).Sys?.WebForms?.PageRequestManager?.getInstance?.();
  36  |         return !prm || !prm.get_isInAsyncPostBack();
  37  |       } catch (_) {
  38  |         return true;  // Sys not available — page is stable
  39  |       }
  40  |     },
  41  |     null,
  42  |     { timeout },
  43  |   ).catch(() => null);  // Never fail the test on this wait — it's best-effort
  44  | }
  45  | 
  46  | // ORACLE_PROBES — generated from scenario.oraculos × ui_map.
  47  | // Consumed by the test.afterEach hook to write
  48  | // evidence/<ticket>/<sid>/assertions_<sid>.json with the actual values
  49  | // captured from the live DOM, regardless of whether the test passed,
  50  | // failed, or threw. uat_assertion_evaluator.py reads this file as the
  51  | // primary source of truth for expected/actual reconciliation; without
  52  | // it every oracle would default to status=review.
  53  | type OracleProbe = {
  54  |   oracle_id: number;
  55  |   target: string;
  56  |   tipo: string;
  57  |   expected: string | number | null;
  58  |   selector: string | null;  // CSS-ish; null for whole-page oracles
  59  | };
  60  | const ORACLE_PROBES: OracleProbe[] = [
  61  | 
  62  | ];
  63  | const ASSERTIONS_OUT_PATH = 'evidence/120/P13/assertions_P13.json';
  64  | 
  65  | // STEP_BBOXES — accumulates bounding boxes of interacted elements per step.
  66  | // Written by test.afterEach to evidence/<ticket>/<sid>/step_bboxes.json and
  67  | // consumed by screenshot_annotator.py (Fase 2) to draw red boxes on screenshots.
  68  | type StepBboxEntry = {
  69  |   step_index: number;
  70  |   screenshot_path: string;
  71  |   target: string;
  72  |   bbox: { x: number; y: number; width: number; height: number } | null;
  73  | };
  74  | const STEP_BBOXES: StepBboxEntry[] = [];
  75  | const STEP_BBOXES_OUT_PATH = 'evidence/120/P13/step_bboxes.json';
  76  | 
  77  | 
  78  | // TARGET_SCREEN for this spec (declared by scenario — not inferred at runtime).
  79  | // The runner validates that the playbook/navigation arrives at this exact screen.
  80  | const TARGET_SCREEN = 'FrmDetalleClie.aspx';
  81  | 
  82  | test.describe('ADO-120 | P13 — Consistencia de "Nombre del Corredor" con RF-006 (Corredor Principal en cabecera)', () => {
  83  | 
  84  |   test.beforeEach(async ({ page }) => {
  85  |     // Auth is restored from storageState (written by playwright/global.setup.ts).
  86  |     // NO login here — the session is already established.
  87  |     // beforeEach navigates to the DECLARED target screen (not a hardcoded fallback).
  88  |     // If we are redirected to login, the session expired — fail immediately.
> 89  |     await page.goto(`${BASE_URL}${TARGET_SCREEN}`, { waitUntil: 'domcontentloaded', timeout: 20_000 });
      |                ^ TimeoutError: page.goto: Timeout 20000ms exceeded.
  90  |     await waitForAgendaStable(page);
  91  |     const beforeEachUrl = page.url().toLowerCase();
  92  |     if (beforeEachUrl.includes('frmlogin')) {
  93  |       throw new Error(
  94  |         `[${TARGET_SCREEN}] Session expired before test start. ` +
  95  |         'Re-run the pipeline to refresh auth (global.setup.ts). ' +
  96  |         'DO NOT re-run login in specs.',
  97  |       );
  98  |     }
  99  |     // Verify we actually reached the target screen (not a redirect to another page).
  100 |     if (!beforeEachUrl.includes(TARGET_SCREEN.toLowerCase().replace('.aspx', ''))) {
  101 |       throw new Error(
  102 |         `[WRONG_SCREEN] Expected to reach ${TARGET_SCREEN} but landed on: ${page.url()}. ` +
  103 |         'Verify the playbook navigation steps and the declared target_screen.',
  104 |       );
  105 |     }
  106 |   });
  107 | 
  108 |   test('p13 consistencia_de_"nombre_del_corredor"_con_rf-006_(corredor_p', async ({ page }) => {
  109 |     // DATA: lote = 'V000000201605P'
  110 | 
  111 |     // PRECONDITIONS (informational — verified by uat_precondition_checker.py before this test)
  112 |     
  113 |     // - El lote con obligación V000000201605P debe existir en la base de datos.
  114 |     
  115 |     // - El Corredor Principal debe estar definido en la cabecera del Detalle de Cliente.
  116 |     
  117 | 
  118 |     // ── Exception & network listener setup ──────────────────────────────────
  119 |     // stepRef permite a los listeners pasivos (response / pageerror / console)
  120 |     // registrar en qué step de acción ocurrió el evento, sin pasar `page` al
  121 |     // cierre del listener.
  122 | 
  123 | 
  124 |     // SETUP
  125 |     await page.goto(`${BASE_URL}FrmDetalleClie.aspx`, { waitUntil: 'domcontentloaded' });
  126 |     await waitForAgendaStable(page);
  127 | 
  128 |     await page.screenshot({ path: 'evidence/120/P13/step_00_setup.png' });
  129 | 
  130 |     // TARGET SCREEN VALIDATION — fail fast if wrong screen reached after navigation.
  131 |     {
  132 |       const setupUrl = page.url().toLowerCase();
  133 |       if (setupUrl.includes('frmlogin')) {
  134 |         throw new Error(
  135 |           `[BLOCKED_LOGIN_FAILED] Navigation to ${TARGET_SCREEN} redirected to login page. ` +
  136 |           'Session is invalid. Re-run the pipeline (do NOT add login logic to specs).',
  137 |         );
  138 |       }
  139 |       if (!setupUrl.includes(TARGET_SCREEN.toLowerCase().replace('.aspx', ''))) {
  140 |         throw new Error(
  141 |           `[BLOCKED_WRONG_SCREEN] Expected: ${TARGET_SCREEN} — Got: ${page.url()}. ` +
  142 |           'Check the playbook navigation steps or the declared target_screen.',
  143 |         );
  144 |       }
  145 |     }
  146 | 
  147 |     // Expand "Búsqueda Avanzada" panel only when needed.
  148 |     // Some Agenda layouts don't expose data-toggle attrs, so use resilient fallback.
  149 |     const advancedPanel = page.locator('#c_pnlBusqueda');
  150 |     const firstFilter = page.locator('#c_ddlDebitoAuto, #c_abfCorredor, #c_abfNombreCliente, #c_abfRUC, #c_btnOk');
  151 |     let filtersReady = await firstFilter.first().isVisible().catch(() => false);
  152 |     if (!filtersReady) {
  153 |       const toggleByHeader = page.locator('.collapsible-header:has-text("Búsqueda Avanzada"), li:has-text("Búsqueda Avanzada") .collapsible-header').first();
  154 |       const toggleByData = page.locator('[data-toggle="collapse"][href="#c_pnlBusqueda"], [data-toggle="collapse"][data-target="#c_pnlBusqueda"]').first();
  155 |       const toggleByText = page.getByText('Búsqueda Avanzada', { exact: false }).first();
  156 | 
  157 |       if (await toggleByHeader.count()) {
  158 |         await toggleByHeader.scrollIntoViewIfNeeded();
  159 |         await toggleByHeader.click({ timeout: 5000 });
  160 |       } else if (await toggleByData.count()) {
  161 |         await toggleByData.scrollIntoViewIfNeeded();
  162 |         await toggleByData.click({ timeout: 5000 });
  163 |       } else if (await toggleByText.count()) {
  164 |         await toggleByText.click({ timeout: 5000 });
  165 |       }
  166 | 
  167 |       if (await advancedPanel.count()) {
  168 |         await advancedPanel.waitFor({ state: 'visible', timeout: 5000 }).catch(() => {});
  169 |       }
  170 |       filtersReady = await firstFilter.first().isVisible().catch(() => false);
  171 | 
  172 |       // Last-resort fallback for legacy WebForms layouts where the toggle
  173 |       // exists but does not update aria/visibility attributes consistently.
  174 |       if (!filtersReady && await advancedPanel.count()) {
  175 |         await page.evaluate(() => {
  176 |           const pnl = document.querySelector('#c_pnlBusqueda') as HTMLElement | null;
  177 |           if (pnl) {
  178 |             pnl.style.display = 'block';
  179 |             pnl.classList.add('active');
  180 |           }
  181 |         });
  182 |         filtersReady = await firstFilter.first().isVisible().catch(() => false);
  183 |       }
  184 |     }
  185 |     console.log('Advanced filters ready:', filtersReady);
  186 |     await page.screenshot({ path: 'screenshots/P13_panel_expanded.png' });
  187 | 
  188 |     // ACTION
  189 |     
```