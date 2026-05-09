import base64, json, os, datetime

BASE = r'N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent'
EV = os.path.join(BASE, 'evidence', '120')
NOW = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')

def b64img(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('utf-8')

# Screenshots
ss = {}
for tid in ['P01','P03','P05','P06','P07','P08','P11','P12']:
    p = os.path.join(EV, tid, 'screenshot_failure.png')
    ss[tid] = b64img(p) if os.path.exists(p) else None

# Root cause analysis per test
FAIL_DETAIL = {
    'P01': ('nav_helper.ts:45', 'waitForFunction timeout 15s esperando que document.title o body incluya "detalle"/"detalle de cliente" tras click en GridObligaciones → FrmDetalleClie no respondio a tiempo'),
    'P03': ('nav_helper.ts:33', 'waitForFunction timeout 15s esperando #c_GridObligaciones tbody tr con filas en FrmBusqueda tras click en GridPersonas (UpdatePanel PostBack lento o CLCOD sin obligaciones visibles)'),
    'P05': ('nav_helper.ts:33', 'Idem P03 — GridObligaciones sin filas dentro del timeout'),
    'P06': ('nav_helper.ts:33', 'Idem P03 — GridObligaciones sin filas dentro del timeout'),
    'P07': ('nav_helper.ts:33', 'Idem P03 — GridObligaciones sin filas dentro del timeout'),
    'P08': ('nav_helper.ts:33', 'Idem P03 — GridObligaciones sin filas dentro del timeout'),
    'P11': ('nav_helper.ts:33', 'Idem P03 — GridObligaciones sin filas dentro del timeout'),
    'P12': ('nav_helper.ts:33', 'Idem P03 — GridObligaciones sin filas dentro del timeout'),
}

SCENARIOS = [
    ('P01','Fecha ingreso judicial no aparece en el grid de obligaciones','OGFECPASAJEJUD eliminada del GridObligaciones en FrmDetalleClie','FrmDetalleClie.aspx'),
    ('P02','Columna fecha judicial eliminada del modelo de datos','Verificacion de esquema de BD — columna OGFECPASAJEJUD','FrmDetalleClie.aspx'),
    ('P03','Las 8 nuevas columnas aparecen en la grilla de obligaciones','8 nuevas columnas visibles en GridObligaciones','FrmDetalleClie.aspx'),
    ('P04','BD — nuevas columnas presentes en OGLIGACIONES','Verificacion de esquema de BD — nuevas columnas','FrmDetalleClie.aspx'),
    ('P05','Campos nulos se muestran sin error, grilla carga completa','hasServerError=false y rowCount > 0','FrmDetalleClie.aspx'),
    ('P06','Afiliado al Debito Automatico muestra Si/No/guion, nunca valor raw','OGDEBAUT_DESC values = Si|No|-','FrmDetalleClie.aspx'),
    ('P07','Los nuevos campos de la grilla son de solo lectura','editableInputs=0, editableSelects=0, editableTextareas=0','FrmDetalleClie.aspx'),
    ('P08','Campos monetarios muestran formato decimal coherente','DESALDOFAVOR y OGMONTOCUOTA con formato numerico','FrmDetalleClie.aspx'),
    ('P09','OGDEBAUT_DESC: Si con acento mapea correcto','Verificacion BD — mapeo Si con acento','FrmDetalleClie.aspx'),
    ('P10','RCONTROLES tiene etiquetas columnas nuevas','Verificacion BD — RCONTROLES tiene labels','FrmDetalleClie.aspx'),
    ('P11','Sub-vista de detalle de cuotas carga sin errores','dlgPrestamos modal y GridCuotas presentes sin server error','FrmDetalleClie.aspx'),
    ('P12','Boton exportacion de obligaciones existe y dispara descarga','#c_btnExportExcelObligaciones existe y descarga inicia','FrmDetalleClie.aspx'),
    ('P13','Columnas nuevas exportadas al Excel','Verificacion de encabezados en archivo XLS exportado','FrmDetalleClie.aspx'),
]

BLOCKED_REASONS = {
    'P02': ('REQUIRES_DB_QUERY','Requiere acceso DB con RSPACIFICOREAD — no disponible en esta ejecucion'),
    'P04': ('REQUIRES_DB_QUERY','Requiere acceso DB con RSPACIFICOREAD — no disponible en esta ejecucion'),
    'P09': ('REQUIRES_DB_QUERY','Requiere acceso DB con RSPACIFICOREAD — no disponible en esta ejecucion'),
    'P10': ('REQUIRES_DB_QUERY','Requiere acceso DB con RSPACIFICOREAD — no disponible en esta ejecucion'),
    'P13': ('REQUIRES_DOWNLOAD_INSPECTION','Requiere inspeccion del archivo Excel descargado — fuera de scope automatico'),
}

EXEC_SCENARIOS = ['P01','P03','P05','P06','P07','P08','P11','P12']
BLOCKED_SCENARIOS = ['P02','P04','P09','P10','P13']

NAV_STEPS = [
    'Restaurar sesion desde .auth/agenda.json (global.setup.ts)',
    'Navegar a FrmBusqueda.aspx',
    'Fill #c_abfCodCliente con CLCOD=4127924112345393',
    'Click #c_btnOk',
    'Esperar #c_GridPersonas tbody tr (filas > 0)',
    'Click primera fila GridPersonas (UpdatePanel PostBack)',
    'Esperar #c_GridObligaciones tbody tr (filas > 0) [TIMEOUT en P03-P12]',
    'Click primera fila GridObligaciones (PostBack → redirect FrmDetalleClie)',
    'Esperar title/body contiene "detalle de cliente" [TIMEOUT en P01]',
    'Esperar #c_GridObligaciones tbody tr en FrmDetalleClie (filas > 0)',
    'Ejecutar assertion especifica del test',
]

# Build HTML
def scenario_article(tid, title, oracle, screen, verdict, detail=None, steps=None, reason=None, ss_b64=None):
    if verdict == 'BLOCKED':
        result_color = '#856404'
        result_bg = '#fff3cd'
    elif verdict == 'FAIL':
        result_color = '#721c24'
        result_bg = '#f8d7da'
    else:
        result_color = '#155724'
        result_bg = '#d4edda'

    ss_html = ''
    if ss_b64:
        ss_html = f'''<h5>Screenshot de fallo</h5>
<figure>
  <img src="data:image/png;base64,{ss_b64}" alt="{tid} — screenshot de fallo" style="max-width:100%;border:1px solid #ccc;" />
  <figcaption>{tid} — estado de la pagina al momento del timeout de navegacion.</figcaption>
</figure>'''
    elif verdict != 'BLOCKED' or not reason:
        ss_html = '<p><em>No screenshot disponible.</em></p>'
    
    steps_html = ''
    if steps:
        items = ''.join(f'<li>{s}</li>' for s in steps)
        steps_html = f'<h5>Pasos ejecutados</h5><ol>{items}</ol>'

    detail_html = ''
    if detail:
        loc, msg = detail
        detail_html = f'<p><strong>Ubicacion del error:</strong> <code>{loc}</code></p><p><strong>Causa:</strong> {msg}</p>'

    reason_html = ''
    if reason:
        rcode, rmsg = reason
        reason_html = f'<p><strong>Razon de bloqueo:</strong> <code>{rcode}</code> — {rmsg}</p>'

    return f'''<article class="qa-scenario" id="scenario-{tid}" style="margin:16px 0;padding:16px;border:1px solid #dee2e6;border-radius:4px;">
  <h4 style="margin-top:0;">{tid} — {title}</h4>
  <table style="width:100%;border-collapse:collapse;margin-bottom:8px;">
    <tr><th style="text-align:left;padding:4px 8px;background:#f8f9fa;width:200px;">Resultado</th><td style="padding:4px 8px;background:{result_bg};color:{result_color};font-weight:bold;">{verdict}</td></tr>
    <tr><th style="text-align:left;padding:4px 8px;background:#f8f9fa;">Oracle esperado</th><td style="padding:4px 8px;">{oracle}</td></tr>
    <tr><th style="text-align:left;padding:4px 8px;background:#f8f9fa;">Pantalla objetivo</th><td style="padding:4px 8px;"><code>{screen}</code></td></tr>
  </table>
  {detail_html}{reason_html}{steps_html}{ss_html}
</article>'''

articles = []
for tid, title, oracle, screen in SCENARIOS:
    if tid in EXEC_SCENARIOS:
        loc, msg = FAIL_DETAIL[tid]
        steps = NAV_STEPS[:NAV_STEPS.index('Ejecutar assertion especifica del test')+1]
        articles.append(scenario_article(tid, title, oracle, screen, 'BLOCKED',
            detail=(loc, msg), steps=steps, ss_b64=ss.get(tid)))
    else:
        r = BLOCKED_REASONS[tid]
        articles.append(scenario_article(tid, title, oracle, screen, 'BLOCKED',
            reason=r))

articles_html = '\n'.join(articles)

html = f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>QA UAT — Ticket 120</title></head>
<body style="font-family:Arial,sans-serif;max-width:1200px;margin:0 auto;padding:16px;">

<section id="qa-uat-summary">
  <h2>QA UAT — Resultado ticket 120</h2>
  <p><strong>Veredicto global:</strong> <span style="color:#856404;font-weight:bold;background:#fff3cd;padding:2px 8px;border-radius:3px;">BLOCKED</span></p>
  <p><strong>Fecha:</strong> {NOW}</p>
  <p><strong>Duracion:</strong> ~4m 30s (8 tests × ~29s avg)</p>
  <p><strong>Base URL:</strong> http://localhost:35017/AgendaWeb/</p>
  <p><strong>Usuario:</strong> PABLO</p>
  <p><strong>Login attempts:</strong> 1 (re-login por sesion vencida &gt;1800s)</p>
  <p><strong>Browser launches:</strong> 1</p>
  <p><strong>Modo:</strong> dry-run</p>
  <p><strong>Playbook:</strong> busqueda_to_detalle_clie_obligaciones</p>
  <p><strong>Pantalla objetivo:</strong> FrmDetalleClie.aspx (via FrmBusqueda.aspx)</p>
  <p><strong>CLCOD de prueba:</strong> 4127924112345393</p>
  <p><strong>Escenarios ejecutados:</strong> 8 de 13</p>
  <p><strong>Escenarios bloqueados (sin ejecucion):</strong> P02, P04, P09, P10, P13</p>
</section>

<hr/>

<section id="qa-uat-root-cause">
  <h3>Causa raiz del bloqueo</h3>
  <p>Todos los tests (P01–P12 ejecutables) fallaron durante la fase de <strong>navegacion</strong>, antes de llegar a la pantalla objetivo <code>FrmDetalleClie.aspx</code>. El playbook no pudo completar el recorrido <em>FrmBusqueda → GridPersonas → GridObligaciones → FrmDetalleClie</em> dentro de los timeouts configurados (15s por paso).</p>
  <h4>Patron de fallo</h4>
  <ul>
    <li><strong>P01:</strong> Logro clickear GridObligaciones en FrmBusqueda, pero FrmDetalleClie no cargó o su texto body/title no coincidió con "detalle"/"detalle de cliente" en 15s. (<code>nav_helper.ts:45</code>)</li>
    <li><strong>P03–P12 (7 tests):</strong> <code>#c_GridObligaciones tbody tr</code> en FrmBusqueda no tuvo filas dentro de 15s tras el click en GridPersonas (UpdatePanel PostBack). (<code>nav_helper.ts:33</code>)</li>
  </ul>
  <h4>Hipotesis</h4>
  <ol>
    <li><strong>CLCOD 4127924112345393 no retorna obligaciones para este cliente en GridObligaciones de FrmBusqueda</strong> — el CLCOD puede ser valido para GridPersonas pero el cliente seleccionado no tiene obligaciones visibles en la grilla de busqueda intermedia.</li>
    <li><strong>Timeout insuficiente:</strong> El UpdatePanel PostBack de GridPersonas → GridObligaciones tarda mas de 15s en dev/IIS Express.</li>
    <li><strong>Selector incorrecto:</strong> <code>#c_GridObligaciones</code> en FrmBusqueda puede tener un ID diferente al de FrmDetalleClie.</li>
    <li><strong>FrmDetalleClie carga pero sin texto esperado:</strong> Para P01, la pagina cargo pero el title/body no contiene "detalle de cliente" en el HTML inicial (puede requerir esperar render de panel).</li>
  </ol>
  <p><strong>Nota critica de deployment:</strong> La rama <code>Task-120-RF-007-v2</code> existe solo en remoto (<code>origin/Task-120-RF-007-v2</code>) y nunca fue checkeada ni compilada localmente. El DLL corriendo en IIS Express es del build del 2026-05-07 19:26 (rama Task-119). Las funcionalidades de RF-007 <strong>no estan deployadas</strong> en la instancia local testeada.</p>
</section>

<hr/>

<section id="qa-uat-effective-config">
  <h3>Configuracion efectiva del run</h3>
  <pre style="background:#f8f9fa;padding:12px;border-radius:4px;font-size:12px;">{json.dumps({
    "ticket": 120,
    "base_url": "http://localhost:35017/AgendaWeb/",
    "username": "PABLO",
    "password": "***REDACTED***",
    "credentials_source": "N:/GIT/RS/RSPACIFICO/Tools/Stacky/.secrets/agenda_web.env",
    "manage_app": False,
    "require_playbook": True,
    "allow_ui_discovery": False,
    "allow_llm_navigation": False,
    "max_login_attempts": 1,
    "max_browser_launches": 1,
    "max_total_minutes": 6,
    "step_timeout_ms": 15000,
    "playbook_id": "busqueda_to_detalle_clie_obligaciones",
    "target_screen": "FrmDetalleClie.aspx",
    "test_clcod": "4127924112345393",
    "scenarios_executable": ["P01","P03","P05","P06","P07","P08","P11","P12"],
    "scenarios_blocked": ["P02","P04","P09","P10","P13"]
  }, indent=2)}</pre>
</section>

<hr/>

<section id="qa-uat-scenarios">
  <h3>Escenarios</h3>
  {articles_html}
</section>

<hr/>

<section id="qa-uat-human-next-step">
  <h3>Proximo paso humano</h3>
  <ol>
    <li><strong>Deploy RF-007:</strong> Checkout <code>origin/Task-120-RF-007-v2</code>, compilar AgendaWeb.sln, reiniciar IIS Express.</li>
    <li><strong>Ejecutar scripts BD:</strong> <code>600804 - Inserts RIDIOMA.sql</code> y <code>600804 - Inserts RCONTROLES.sql</code> en dev DB.</li>
    <li><strong>Validar playbook navegacion:</strong> Confirmar que CLCOD 4127924112345393 tiene obligaciones en <code>#c_GridObligaciones</code> de FrmBusqueda, o proveer un CLCOD/OCRAIZ valido para el entorno dev.</li>
    <li><strong>Revisar selector:</strong> Confirmar que el grid en FrmBusqueda usa ID <code>c_GridObligaciones</code> y no otro (ej. <code>c_GridObligaciones2</code>).</li>
    <li><strong>Re-ejecutar QA UAT</strong> una vez corregidos los puntos anteriores.</li>
  </ol>
  <p><em>No cambiar estado del ticket en ADO. El ticket permanece en "Listo para QA" hasta que el run con RF-007 deployado sea exitoso.</em></p>
</section>

</body>
</html>'''

out = os.path.join(EV, 'ado_comment.html')
with open(out, 'w', encoding='utf-8') as f:
    f.write(html)
print(f'HTML written: {os.path.getsize(out):,} bytes')
print(f'Path: {out}')
