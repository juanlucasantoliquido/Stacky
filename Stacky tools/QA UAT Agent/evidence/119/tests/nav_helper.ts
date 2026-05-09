// ADO-119 | QA UAT | RF-006 — Corredor Principal y Riesgo de Cliente en Datos de Identificación
// Shared navigation helper — navega FrmBusqueda → FrmDetalleClie.aspx
// NO contiene lógica de login — auth restaurada desde .auth/agenda.json via globalSetup

import { Page } from '@playwright/test';

export const BASE_URL = (process.env.AGENDA_WEB_BASE_URL ?? 'http://localhost:35017/AgendaWeb/').replace(/\/$/, '') + '/';

/** CLCOD de MONTEZUMA — tiene OGCORREDOR y CLRIESGOSIS con valores */
export const CLCOD_MONTEZUMA = '4127924112345393';

/** CLCOD de cliente de test — sin OGCORREDOR ni CLRIESGOSIS (CLCOD=8868788139968904 verificado: tiene RDEUDA) */
export const CLCOD_SIN_DATOS = '8868788139968904';

const NAV_TIMEOUT   = 30000;  // 30s — UpdatePanel AJAX puede tardar
const LOAD_TIMEOUT  = 45000;  // 45s — FrmDetalleClie es complejo

/**
 * Navega a FrmDetalleClie.aspx para el cliente indicado.
 * Flujo: FrmBusqueda → (busca por CLCOD) → GridPersonas → GridObligaciones → FrmDetalleClie
 */
export async function navigateToDetalleClie(page: Page, clcod: string): Promise<void> {
  // 1. FrmBusqueda
  await page.goto(BASE_URL + 'FrmBusqueda.aspx', { waitUntil: 'load', timeout: LOAD_TIMEOUT });

  // 2. Buscar por código de cliente — esperar respuesta UpdatePanel (POST al mismo recurso)
  await page.locator('#c_abfCodCliente').fill(clcod);
  await Promise.all([
    page.waitForResponse(
      r => r.url().includes('FrmBusqueda') && r.request().method() === 'POST',
      { timeout: NAV_TIMEOUT }
    ),
    page.locator('#c_btnOk').click(),
  ]);

  // 3. Esperar GridPersonas (UpdatePanel actualiza DOM tras el AJAX)
  await page.waitForSelector('#c_GridPersonas tbody tr', { timeout: NAV_TIMEOUT });

  // 4. Click en primera fila de GridPersonas — espera UpdatePanel GridObligaciones
  const personaRow = page.locator('#c_GridPersonas tbody tr').first();
  const personaSelBtnCount = await personaRow.locator('input[type=button], a, button').count();
  const personaClickTarget = personaSelBtnCount > 0
    ? personaRow.locator('input[type=button], a, button').first()
    : personaRow;

  await Promise.all([
    page.waitForResponse(
      r => r.url().includes('FrmBusqueda') && r.request().method() === 'POST',
      { timeout: NAV_TIMEOUT }
    ),
    personaClickTarget.click(),
  ]);

  // 5. Esperar GridObligaciones con al menos una fila
  await page.waitForSelector('#c_GridObligaciones tbody tr', { timeout: NAV_TIMEOUT });

  // 6. Click en primera obligación — provoca Redireccionar("FrmDetalleClie.aspx")
  //    que en contexto UpdatePanel resulta en window.location = "FrmDetalleClie.aspx"
  const obligRow = page.locator('#c_GridObligaciones tbody tr').first();
  const obligSelBtnCount = await obligRow.locator('input[type=button], a, button').count();
  const obligClickTarget = obligSelBtnCount > 0
    ? obligRow.locator('input[type=button], a, button').first()
    : obligRow;

  await Promise.all([
    page.waitForURL('**/FrmDetalleClie.aspx**', { timeout: LOAD_TIMEOUT }),
    obligClickTarget.click(),
  ]);

  // 7. Esperar carga completa de FrmDetalleClie
  await page.waitForLoadState('load', { timeout: LOAD_TIMEOUT });
}
