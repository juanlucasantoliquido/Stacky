# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: freeform-20260505-001641\tests\P_compromiso_pago.spec.ts >> freeform-001641 | Crear compromiso de pago >> P01 | Agenda carga con clientes visibles
- Location: evidence\freeform-20260505-001641\tests\P_compromiso_pago.spec.ts:22:7

# Error details

```
TimeoutError: page.fill: Timeout 10000ms exceeded.
Call log:
  - waiting for locator('#c_txtUsuario')

```

# Page snapshot

```yaml
- generic [ref=e11]:
  - generic [ref=e14]: person
  - generic [ref=e16]:
    - generic [ref=e17]: person
    - textbox "Usuario" [active] [ref=e18]
    - generic [ref=e19]: Usuario
  - generic [ref=e21]:
    - generic [ref=e22]: lock_outline
    - textbox "Contraseña" [ref=e23]
    - generic [ref=e24]: Contraseña
  - generic [ref=e26]:
    - generic [ref=e27]: public
    - generic [ref=e28]: Dominio
    - combobox "AIS" [ref=e31] [cursor=pointer]:
      - generic "AIS" [ref=e32]
  - link "Entrar" [ref=e36] [cursor=pointer]:
    - /url: javascript:__doPostBack('ctl00$c$btnOk','')
```

# Test source

```ts
  1  | import { test, expect, Page } from '@playwright/test';
  2  | import * as fs from 'fs';
  3  | import * as path from 'path';
  4  | 
  5  | // Free-form QA UAT: Crear compromiso de pago
  6  | // Run ID: freeform-20260505-001641
  7  | const BASE_URL = process.env.AGENDA_WEB_BASE_URL || 'http://localhost:35017/AgendaWeb/';
  8  | const EV_DIR   = 'evidence/freeform-20260505-001641';
  9  | 
  10 | test.describe('freeform-001641 | Crear compromiso de pago', () => {
  11 |   let page: Page;
  12 | 
  13 |   test.beforeAll(async ({ browser }) => {
  14 |     const ctx = await browser.newContext({
  15 |       recordVideo: { dir: EV_DIR + '/P_compromiso/' },
  16 |     });
  17 |     page = await ctx.newPage();
  18 |   });
  19 | 
  20 |   test.afterAll(async () => { await page.context().close(); });
  21 | 
  22 |   test('P01 | Agenda carga con clientes visibles', async () => {
  23 |     await page.goto(BASE_URL + 'FrmAgenda.aspx');
  24 |     if (page.url().includes('FrmLogin') || page.url().includes('Login')) {
> 25 |       await page.fill('#c_txtUsuario', process.env.AGENDA_WEB_USER || 'PABLO');
     |                  ^ TimeoutError: page.fill: Timeout 10000ms exceeded.
  26 |       await page.fill('#c_txtPassword', process.env.AGENDA_WEB_PASS || 'PABLO');
  27 |       await page.click('#c_btnIngresar');
  28 |       await page.waitForURL(/FrmAgenda/, { timeout: 15000 });
  29 |     }
  30 |     await page.locator('#c_GridAgendaUsu').waitFor({ state: 'visible', timeout: 15000 });
  31 |     const rows = await page.locator('#c_GridAgendaUsu tbody tr').count();
  32 |     console.log('[INFO] Filas en agenda:', rows);
  33 |     expect(rows).toBeGreaterThanOrEqual(1);
  34 |     fs.mkdirSync(path.join(EV_DIR, 'P_compromiso'), { recursive: true });
  35 |     await page.screenshot({ path: EV_DIR + '/P_compromiso/step01_agenda.png' });
  36 |   });
  37 | 
  38 |   test('P02 | Click primera fila abre FrmDetalleClie', async () => {
  39 |     const firstCell = page.locator('#c_GridAgendaUsu tbody tr').first().locator('td').first();
  40 |     const nombre = await firstCell.innerText().catch(() => 'N/A');
  41 |     console.log('[INFO] Abriendo cliente:', nombre.trim());
  42 |     await firstCell.click();
  43 |     await page.waitForURL(/FrmDetalleClie/, { timeout: 20000 });
  44 |     await page.screenshot({ path: EV_DIR + '/P_compromiso/step02_detalle.png' });
  45 |     expect(page.url()).toContain('FrmDetalleClie');
  46 |   });
  47 | 
  48 |   test('P03 | Clic en Compromisos abre popup', async () => {
  49 |     expect(page.url()).toContain('FrmDetalleClie');
  50 |     const compBtn = page.locator('a:has-text("Compromisos"), button:has-text("Compromisos")').first();
  51 |     const visible = await compBtn.isVisible({ timeout: 8000 }).catch(() => false);
  52 |     if (!visible) {
  53 |       const links = await page.locator('a').allInnerTexts();
  54 |       const ids = await page.locator('[id]').evaluateAll((els: Element[]) => els.map((e) => (e as HTMLElement).id).filter(Boolean));
  55 |       console.log('[DEBUG] Links:', links.filter((l) => l.trim()).join(' | '));
  56 |       console.log('[DEBUG] IDs btn/tab/comp:', ids.filter((id) => /btn|tab|comp/i.test(id)).join(' | '));
  57 |       await page.screenshot({ path: EV_DIR + '/P_compromiso/step03_debug.png' });
  58 |       throw new Error('Boton Compromisos no encontrado - ver step03_debug.png');
  59 |     }
  60 |     await compBtn.click();
  61 |     await page.waitForTimeout(2000);
  62 |     await page.screenshot({ path: EV_DIR + '/P_compromiso/step03_popup.png' });
  63 |     const content = await page.content();
  64 |     expect(content.toLowerCase()).toMatch(/compromi/);
  65 |     console.log('[PASS] Popup Compromisos abierto');
  66 |   });
  67 | });
  68 | 
```