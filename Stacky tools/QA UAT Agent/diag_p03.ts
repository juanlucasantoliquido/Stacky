import { chromium } from '@playwright/test';
import * as fs from 'fs';

(async () => {
  const BASE_URL = process.env.AGENDA_WEB_BASE_URL!;
  const USER    = process.env.AGENDA_WEB_USER!;
  const PASS    = process.env.AGENDA_WEB_PASS!;

  const browser = await chromium.launch({ headless: false, slowMo: 400 });
  const page    = await browser.newPage();

  // 1. Login
  await page.goto(BASE_URL + 'FrmLogin.aspx', { waitUntil: 'load' });
  await page.fill('#c_txtLoginName', USER);
  await page.fill('#c_txtPassword',  PASS);
  await page.click('#c_btnLogin');
  await page.waitForLoadState('load');

  // 2. FrmAgenda → FrmAdministrador
  await page.goto(BASE_URL + 'FrmAgenda.aspx', { waitUntil: 'load' });
  await page.locator('#c_251').click();
  await page.waitForLoadState('load');

  // 3. FrmAdministrador → FrmGestionUsuarios
  await page.waitForSelector('#c_251', { state: 'visible', timeout: 10000 }).catch(() => {});
  await page.goto(BASE_URL + 'FrmGestionUsuarios.aspx', { waitUntil: 'load' });

  // 4. Click tab Usuarios
  await page.locator('a[href="#c_tabUsuario"]').click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'diag_01_tab.png' });

  // 5. Click Agregar
  await page.locator('#c_btnAgregarUsuario').click();
  await page.waitForTimeout(5000);
  await page.screenshot({ path: 'diag_02_after_agregar.png' });

  // 6. Dump HTML
  const html = await page.content();
  fs.writeFileSync('diag_page.html', html, 'utf-8');
  console.log('Guardado: diag_page.html, diag_01_tab.png, diag_02_after_agregar.png');

  // 7. Check what buttons are visible
  for (const sel of ['#c_btnGuardarUsuario','#c_btnCancelarUsuario','#c_pnlEditUsuario','form','[id*=Guardar]','[id*=guardar]']) {
    const count   = await page.locator(sel).count();
    const visible = count > 0 ? await page.locator(sel).first().isVisible().catch(() => false) : false;
    console.log(  : count= visible=);
  }

  await browser.close();
})();
