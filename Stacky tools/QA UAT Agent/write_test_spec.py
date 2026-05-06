"""write_test_spec.py — DIRECT ACTION generator
================================================
Genera un spec Playwright de ACCION DIRECTA para crear_compromiso_pago.

Diseño:
  - UN solo test (sin pasos intermedios P01/P02/P03)
  - Lee selectores desde form_knowledge.json
  - afterAll auto-actualiza form_knowledge.json con lo aprendido en el run
  - Si agenda vacía → fallback a Búsqueda Avanzada, automático, sin intervención

Uso:
    python write_test_spec.py
    (luego correr el spec generado con npx playwright test ...)
"""
import pathlib
import json

# ---------------------------------------------------------------------------
# Cargar form_knowledge.json
# ---------------------------------------------------------------------------
KNOWLEDGE_FILE = pathlib.Path(__file__).parent / 'form_knowledge.json'
_k: dict = {}
if KNOWLEDGE_FILE.exists():
    try:
        _k = json.loads(KNOWLEDGE_FILE.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'[WARN] form_knowledge.json no pudo leerse: {e}')

RUN_ID = 'freeform-20260505-001641'
CLCOD  = '4127924112345393'  # OCRAIZ — MONTEZUMA GARRIDO NATALIA (AGPERFIL=1, PABLO)

# ---------------------------------------------------------------------------
# Extraer selectores desde el knowledge (con defaults seguros)
# ---------------------------------------------------------------------------
_pop = _k.get('PopUpCompromisos', {})
_sel = _pop.get('selectors', {})
_agen = _k.get('FrmAgenda.aspx', {}).get('selectors', {})

SEL_GRID    = _agen.get('grid_agenda_usuario', '#c_GridAgendaUsu')
SEL_FILTRO  = _agen.get('filtro_nombre_cliente', '#c_abfNombreCliente')
SEL_BUSCAR  = _agen.get('btn_buscar', '#c_btnOk')
SEL_MODAL   = _pop.get('modal_id', '#c_dlgCompromisos')
SEL_PROY    = _sel.get('abf_proyeccion', '#c_abfProyeccion')
SEL_AGREGAR = _sel.get('btn_agregar_promesa', '#c_btnAgregarPromesa')
SEL_FIGURA  = _sel.get('ddl_figura', '#c_ddlFiguraCompromiso')
SEL_ACCION  = _sel.get('ddl_accion', '#c_ddlTarCompromiso')
SEL_GUARDAR = _sel.get('btn_guardar', '#c_btnGuardarModalCompromisos')

# Valores de DDL preferidos (conocimiento previo)
_fig_opts = _pop.get('ddl_figura_opciones', {})
_act_opts = _pop.get('ddl_accion_opciones_comunes', {})
FIGURA_VAL  = 'T01'   # Titular Principal — validado
ACCION_VAL  = 'CPPA'  # Compromiso de Pago Parcial — validado

# Path absoluto para que el afterAll escriba el JSON (barras dobles para TS string literal)
KPATH_TS = str(KNOWLEDGE_FILE).replace('\\', '\\\\')

print(f'[INFO] Generando spec DIRECTO — run: {RUN_ID}')
print(f'[INFO] GUARDAR selector: {SEL_GUARDAR}')
print(f'[INFO] MODAL selector:   {SEL_MODAL}')

# ---------------------------------------------------------------------------
# HEADER — f-string pequeño solo para inyectar constantes Python → TypeScript
# ---------------------------------------------------------------------------
HEADER = f"""\
import {{ test, expect }} from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

// Generado por write_test_spec.py — accion directa, sin pasos intermedios
// Selectores y flujo validados en runs anteriores (form_knowledge.json)
const BASE_URL  = process.env.AGENDA_WEB_BASE_URL || 'http://localhost:35017/AgendaWeb/';
const EV_DIR    = 'evidence/{RUN_ID}';
const KFILE     = '{KPATH_TS}';

const SEL_GRID    = '{SEL_GRID}';
const SEL_FILTRO  = '{SEL_FILTRO}';
const SEL_BUSCAR  = '{SEL_BUSCAR}';
const SEL_MODAL   = '{SEL_MODAL}';
const SEL_PROY    = '{SEL_PROY}';
const SEL_AGREGAR = '{SEL_AGREGAR}';
const SEL_FIGURA  = '{SEL_FIGURA}';
const SEL_ACCION  = '{SEL_ACCION}';
const SEL_GUARDAR     = '{SEL_GUARDAR}';
const FIGURA_VAL      = '{FIGURA_VAL}';
const ACCION_VAL      = '{ACCION_VAL}';
const CLCOD           = '{CLCOD}';
const SEL_BUSQ_CLIE   = '#c_abfCodCliente';
const SEL_BUSQ_BTN    = '#c_btnOk';
const SEL_BUSQ_GRID   = '#c_GridPersonas';
const SEL_OBL_GRID    = '#c_GridObligaciones';
"""

# ---------------------------------------------------------------------------
# BODY — raw string, TypeScript puro, { } son literales (no f-string)
# ---------------------------------------------------------------------------
BODY = r"""
// Estado de aprendizaje — se puebla durante el test, se persiste en afterAll
let _figOpts: Record<string, string> = {};
let _actOpts: Record<string, string> = {};
let _clienteUsado = '';
let _fallbackUsado = false;
let _runSuccess = false;

test.describe('Crear compromiso de pago', () => {
  let page: any;

  test.beforeAll(async ({ browser }: any) => {
    const ctx = await browser.newContext({ recordVideo: { dir: EV_DIR + '/accion/' } });
    page = await ctx.newPage();
    fs.mkdirSync(path.join(EV_DIR, 'accion'), { recursive: true });
    // LOGIN
    await page.goto(BASE_URL + 'FrmLogin.aspx', { waitUntil: 'load' });
    await page.fill('#c_abfUsuario',    process.env.AGENDA_WEB_USER || 'PABLO');
    await page.fill('#c_abfContrasena', process.env.AGENDA_WEB_PASS || 'PABLO');
    await page.locator('#c_btnOk').click({ noWaitAfter: true });
    await page.waitForURL(/FrmAgenda/, { timeout: 25000 });
    console.log('[OK] Login');
  });

  // AUTO-APRENDIZAJE: afterAll escribe form_knowledge.json automaticamente
  test.afterAll(async () => {
    try {
      const k: any = JSON.parse(fs.readFileSync(KFILE, 'utf-8'));
      k._meta = k._meta || {};
      k._meta.last_updated  = new Date().toISOString().split('T')[0];
      k._meta.last_run_id   = EV_DIR.split('/').pop() || '';
      k._meta.last_run_ok   = _runSuccess;

      if (Object.keys(_figOpts).length > 0)
        k.PopUpCompromisos.ddl_figura_opciones = _figOpts;
      if (Object.keys(_actOpts).length > 0)
        k.PopUpCompromisos.ddl_accion_opciones_comunes = _actOpts;
      if (_clienteUsado)
        k.PopUpCompromisos.cliente_prueba_ultimo = _clienteUsado;
      if (_fallbackUsado) {
        k['FrmAgenda.aspx'] = k['FrmAgenda.aspx'] || {};
        k['FrmAgenda.aspx'].fallback_busqueda_requerido = true;
      }

      fs.writeFileSync(KFILE, JSON.stringify(k, null, 2), 'utf-8');
      console.log('[LEARN] form_knowledge.json actualizado automaticamente');
    } catch (e) {
      console.log('[WARN] No se pudo actualizar knowledge:', String(e));
    }
    await page.context().close();
  });

  test('Crear compromiso de pago', async () => {

    // ── PASO 1: Buscar cliente en FrmBusqueda ──────────────────────────────
    await page.goto(BASE_URL + 'FrmBusqueda.aspx', { waitUntil: 'load' });
    await page.locator(SEL_BUSQ_CLIE).waitFor({ state: 'visible', timeout: 10000 });
    await page.fill(SEL_BUSQ_CLIE, CLCOD);
    await page.locator(SEL_BUSQ_BTN).click({ noWaitAfter: true });
    // Esperar grid Personas con filas (async UpdatePanel)
    await page.waitForFunction(
      (s: string) => { const t = document.querySelector(s + ' tbody'); return t && t.querySelectorAll('tr').length > 0; },
      SEL_BUSQ_GRID, { timeout: 15000 }
    );
    await page.screenshot({ path: EV_DIR + '/accion/s01_busqueda.png' });
    const personaCell = page.locator(SEL_BUSQ_GRID + ' tbody tr').first().locator('td').first();
    _clienteUsado = (await personaCell.innerText().catch(() => '')).trim();
    console.log('[INFO] Cliente encontrado:', _clienteUsado);

    // ── PASO 2: Seleccionar cliente → ver obligaciones ────────────────────
    await personaCell.click({ noWaitAfter: true });
    // Esperar grid Obligaciones con filas (async UpdatePanel)
    await page.waitForFunction(
      (s: string) => { const t = document.querySelector(s + ' tbody'); return t && t.querySelectorAll('tr').length > 0; },
      SEL_OBL_GRID, { timeout: 15000 }
    );
    await page.screenshot({ path: EV_DIR + '/accion/s01b_obligaciones.png' });
    // Click primera obligación → redirige a FrmDetalleClie
    await page.locator(SEL_OBL_GRID + ' tbody tr').first().locator('td').first().click({ noWaitAfter: true });
    await page.waitForFunction(
      () => document.title.includes('Detalle') ||
            document.body.innerText.includes('Detalle de Cliente') ||
            !!document.querySelector('#c_btnCompromisos'),
      { timeout: 20000 }
    ).catch(() => page.waitForLoadState('load', { timeout: 15000 }));
    await page.screenshot({ path: EV_DIR + '/accion/s02_detalle.png' });
    console.log('[OK] FrmDetalleClie cargado via FrmBusqueda');

    // ── PASO 3: Abrir modal Compromisos ───────────────────────────────────
    await page.locator([
      'a:has-text("Compromisos")',
      'button:has-text("Compromisos")',
      '#c_btnCompromisos',
    ].join(', ')).first().click();
    await page.waitForFunction(
      (s: string) => { const d = document.querySelector(s); return d && d.classList.contains('open') && (d as HTMLElement).innerHTML.length > 100; },
      SEL_MODAL, { timeout: 10000 }
    ).catch(() => page.waitForTimeout(3000));
    await page.screenshot({ path: EV_DIR + '/accion/s03_modal.png' });
    console.log('[INFO] Modal Compromisos abierto');

    // ── PASO 4: Seleccionar obligacion sin compromiso activo ──────────────
    // GridObligacionesCompromisos ordena por OGLIDER DESC:
    //   Row 0: MOR0024967 (OGLIDER=1) — puede tener compromiso activo hoy
    //   Row 1: MOR0026973 (OGLIDER=0) — sin compromisos existentes
    const SEL_OBL_COMP = '#c_GridObligacionesCompromisos';
    const oblRows = await page.locator(SEL_OBL_COMP + ' tbody tr').count().catch(() => 0);
    console.log('[INFO] Filas GridObligacionesCompromisos:', oblRows);
    if (oblRows > 1) {
      // Click segunda obligacion → PostBack carga cuotas de MOR0026973
      await page.locator(SEL_OBL_COMP + ' tbody tr').nth(1).locator('td').first().click({ noWaitAfter: true });
      await page.waitForFunction(
        () => { const u = (window as any).Sys?.WebForms?.PageRequestManager?.getInstance?.(); return !u || !u.get_isInAsyncPostBack(); },
        { timeout: 10000 }
      ).catch(() => page.waitForTimeout(3000));
      console.log('[INFO] Segunda obligacion seleccionada (MOR0026973)');
    }

    // ── PASO 5: Proyeccion ────────────────────────────────────────────────
    // ObtenerProyeccionDeuda() suma cuotas MARCADAS — desmarca todas al cambiar oblig → 0
    // ValidarCompromiso() falla si abfProyeccion == 0 → siempre setear manualmente
    await page.locator(SEL_PROY).click({ force: true });
    await page.locator(SEL_PROY).fill('50000');
    await page.locator(SEL_PROY).press('Tab');
    await page.waitForTimeout(400);
    console.log('[INFO] Proyeccion forzada:', await page.locator(SEL_PROY).inputValue().catch(() => '?'));

    // ── PASO 6-orig: Agregar promesa ──────────────────────────────────────
    await page.locator(SEL_AGREGAR).click({ noWaitAfter: true });
    await page.waitForTimeout(4500);   // esperar PostBack UpdatePanel
    await page.screenshot({ path: EV_DIR + '/accion/s04_promesa.png' });

    // Verificar si el AGREGAR tuvo éxito — debe haber filas en GridPromesasPago
    const promRows = await page.locator('#c_GridPromesasPago tbody tr').count().catch(() => 0);
    const modalBodyAfterAgregar = await page.locator(SEL_MODAL).evaluate(
      (el: Element) => (el as HTMLElement).innerText?.substring(0, 600)
    ).catch(() => '');
    console.log('[INFO] Filas GridPromesasPago:', promRows);
    if (/ya existe.*compromiso|Debe Ingresar/i.test(modalBodyAfterAgregar))
      console.log('[WARN] Error AGREGAR:', modalBodyAfterAgregar.match(/(ya existe.*compromiso|Debe Ingresar[^.]*)/i)?.[0]);
    if (promRows === 0) {
      // Diagnóstico: proyección actual
      const proyActual = await page.locator(SEL_PROY).inputValue().catch(() => '?');
      console.log('[DEBUG] abfProyeccion al AGREGAR:', proyActual);
      throw new Error('AGREGAR falló — GridPromesasPago vacío. Ver modal: ' + modalBodyAfterAgregar.substring(0, 200));
    }

    // ── PASO 7: Figura y Accion via JS (Select2 oculta los <select>) ──────
    const figOpts: any[] = await page.locator(SEL_FIGURA).evaluate((el: Element) =>
      Array.from((el as HTMLSelectElement).options).map((o: any) => ({ v: o.value, t: o.text }))
    ).catch(() => []);
    const actOpts: any[] = await page.locator(SEL_ACCION).evaluate((el: Element) =>
      Array.from((el as HTMLSelectElement).options).map((o: any) => ({ v: o.value, t: o.text }))
    ).catch(() => []);

    // Guardar para auto-aprendizaje
    figOpts.filter((o: any) => o.v && o.v !== '0').forEach((o: any) => { _figOpts[o.v] = o.t; });
    actOpts.filter((o: any) => o.v && o.v !== '0').forEach((o: any) => { _actOpts[o.v] = o.t; });

    const fig = figOpts.find((o: any) => o.v === FIGURA_VAL) || figOpts.find((o: any) => o.v && o.v !== '0');
    if (fig) {
      await page.locator(SEL_FIGURA).evaluate((el: Element, v: string) => {
        (el as HTMLSelectElement).value = v;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, fig.v);
    }
    const act = actOpts.find((o: any) => o.v === ACCION_VAL) || actOpts.find((o: any) => o.v && o.v !== '0');
    if (act) {
      await page.locator(SEL_ACCION).evaluate((el: Element, v: string) => {
        (el as HTMLSelectElement).value = v;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, act.v);
    }
    console.log('[INFO] Figura:', fig?.t, '| Accion:', act?.t);
    await page.waitForTimeout(1000);

    // ── PASO 7: GUARDAR ───────────────────────────────────────────────────
    const disabled = await page.locator(SEL_GUARDAR).evaluate((el: Element) =>
      el.classList.contains('disabled') || el.classList.contains('aspNetDisabled')
    ).catch(() => true);
    console.log('[INFO] GUARDAR disabled:', disabled);
    await page.screenshot({ path: EV_DIR + '/accion/s05_pre_guardar.png' });

    // force:true: c_panelBtnCompromisos es un overlay que bloquea el click normal
    await page.locator(SEL_GUARDAR).click({ force: true, noWaitAfter: true });
    await page.waitForTimeout(4000);
    await page.screenshot({ path: EV_DIR + '/accion/s06_resultado.png' });

    // ── VERIFICACION ──────────────────────────────────────────────────────
    const bodyT = await page.locator('body').evaluate(
      (el: Element) => (el as HTMLElement).innerText?.substring(0, 2000)
    ).catch(() => '');
    const toastOk  = /guardado.*correctamente|compromisos.*guardado|se ha guardado/i.test(bodyT);
    const toastErr = /error.*guardar|no.*guardó|fallo/i.test(bodyT);
    const modalTxt = await page.locator(SEL_MODAL).evaluate(
      (el: Element) => (el as HTMLElement).innerText?.substring(0, 400)
    ).catch(() => '');
    const modalErr = /campo.*requerido|obligatorio/i.test(modalTxt);

    if (toastOk)          console.log('[PASS] Toast — compromiso guardado en BD');
    else if (!disabled)   console.log('[PASS] GUARDAR ejecutado con boton habilitado');
    else                  console.log('[INFO] GUARDAR disabled — revisar s05_pre_guardar.png');

    _runSuccess = toastOk || (!disabled && !toastErr && !modalErr);

    expect(disabled, 'GUARDAR debe estar habilitado (AGREGAR debe haber tenido exito)').toBe(false);
    expect(toastErr, 'Error en toast post-guardar').toBe(false);
    expect(modalErr, 'Error de validacion en modal').toBe(false);
  });
});
"""

SPEC = HEADER + BODY

out = pathlib.Path(f'evidence/{RUN_ID}/tests/P_compromiso_pago.spec.ts')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(SPEC, encoding='utf-8')
print(f'OK - {out} ({len(SPEC)} bytes)')
