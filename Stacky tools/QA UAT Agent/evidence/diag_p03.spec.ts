import { test, expect } from '@playwright/test';
import * as fs from 'fs';

const BASE_URL = process.env.AGENDA_WEB_BASE_URL ?? '';
const USER     = process.env.AGENDA_WEB_USER ?? '';
const PASS     = process.env.AGENDA_WEB_PASS ?? '';

test('diag-p03-agregar-usuario', async ({ page }) => {
  // Login
  await page.goto(BASE_URL + 'FrmLogin.aspx', { waitUntil: 'load' });
  await page.fill('#c_txtLoginName', USER);
  await page.fill('#c_txtPassword',  PASS);
  await page.click('#c_btnLogin');
  await page.waitForLoadState('load');

  // Navegar: Agenda → Administrador → GestionUsuarios (via menu link)
  await page.goto(BASE_URL + 'FrmAgenda.aspx', { waitUntil: 'load' });
  await page.locator('#c_251').click();
  await page.waitForLoadState('load');
  // Desde administrador navegar a gestion usuarios via link
  await page.locator('#c_251').click();
  await page.waitForLoadState('load');
  await page.screenshot({ path: 'evidence/freeform-20260505-103348/diag_01_gestion.png' });

  // Tab Usuarios
  await page.locator('a[href="#c_tabUsuario"]').click();
  await page.waitForTimeout(2000);
  await page.screenshot({ path: 'evidence/freeform-20260505-103348/diag_02_tab.png' });

  // Click Agregar
  await page.locator('#c_btnAgregarUsuario').click();
  await page.waitForTimeout(6000);
  await page.screenshot({ path: 'evidence/freeform-20260505-103348/diag_03_after_agregar.png' });

  // Dump HTML
  const html = await page.content();
  fs.writeFileSync('evidence/freeform-20260505-103348/diag_page.html', html, 'utf-8');

  // Check buttons
  const checks: Record<string,{count:number,visible:boolean}> = {};
  for (const sel of ['#c_btnGuardarUsuario','#c_btnCancelarUsuario','#c_pnlEditUsuario',
                     '[id*=Guardar]','[id*=guardar]','[id*=Usuario]','button[type=submit]',
                     'input[type=submit]','#c_divEditUsuario','#c_formUsuario']) {
    const count   = await page.locator(sel).count();
    const visible = count > 0 ? await page.locator(sel).first().isVisible().catch(() => false) : false;
    checks[sel] = { count, visible };
    console.log(`  ${sel}: count=${count} visible=${visible}`);
  }
  // Always pass — this is a diagnostic
  expect(true).toBe(true);
});
