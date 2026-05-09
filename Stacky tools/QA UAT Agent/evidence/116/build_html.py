import json, base64, os, datetime

ev = 'evidence/116'
cfg = json.load(open(ev+'/effective_config.json'))
p08 = json.load(open(ev+'/P08/assertions_P08.json'))
barra = open(ev+'/P08/barraResumen.html',encoding='utf-8').read()

def b64img(path):
    if os.path.exists(path):
        return base64.b64encode(open(path,'rb').read()).decode()
    return None

img1 = b64img(ev+'/P08/P08-01-initial.png')
img2 = b64img(ev+'/P08/P08-02-counter-check.png')

def img_tag(b64, alt, caption):
    if b64:
        return '<figure><img src="data:image/png;base64,' + b64 + '" alt="' + alt + '" style="max-width:100%;border:1px solid #ccc;"/><figcaption>' + caption + '</figcaption></figure>'
    return '<p><em>(screenshot not available)</em></p>'

today = datetime.date.today()
d7 = (today + datetime.timedelta(days=6))

parts = []
parts.append('<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><title>QA UAT ADO-116 Run 002</title><style>')
parts.append('body{font-family:Arial,sans-serif;font-size:13px;color:#222;max-width:900px;margin:0 auto;padding:16px}')
parts.append('h2{color:#0078d4}h3{color:#005a9e}h4{color:#003366}')
parts.append('table{border-collapse:collapse;width:100%;margin-bottom:12px}')
parts.append('th,td{border:1px solid #ddd;padding:6px 10px;text-align:left}')
parts.append('th{background:#f0f4f8;font-weight:bold}')
parts.append('.PASS{color:green;font-weight:bold}.FAIL{color:red;font-weight:bold}.BLOCKED{color:#888;font-weight:bold}')
parts.append('pre{background:#f5f5f5;padding:8px;font-size:11px;overflow:auto;border:1px solid #ddd;border-radius:4px}')
parts.append('figure{margin:8px 0}figcaption{font-size:11px;color:#666;font-style:italic}')
parts.append('.defect-box{background:#fff3cd;border:1px solid #ffc107;padding:12px;border-radius:4px;margin:12px 0}')
parts.append('.defect-box h5{margin:0 0 6px 0;color:#856404}')
parts.append('</style></head><body>')

parts.append('<section id="qa-uat-summary">')
parts.append('<h2>QA UAT - Resultado ticket ADO-116 (Run 002)</h2>')
parts.append('<table>')
parts.append('<tr><th>Veredicto global</th><td><span class="FAIL">FAIL</span></td></tr>')
parts.append('<tr><th>Run ID</th><td>uat-116-20260508-002</td></tr>')
parts.append('<tr><th>Alcance este run</th><td>P08 (CA-08) - Visibilidad contador para usuario no-Pacifico</td></tr>')
parts.append('<tr><th>Ejecutados</th><td>1 / 10 escenarios</td></tr>')
parts.append('<tr><th>FAIL</th><td>P08 - Counter visible para PABLO (no-Pacifico) - CA-08 FALLA</td></tr>')
parts.append('<tr><th>BLOCKED anteriores</th><td>P01-P04, P06-P07, P10 (sin datos) | ver run 001</td></tr>')
parts.append('<tr><th>PASS anteriores</th><td>P05, P09 - evidencia en run uat-116-20260508-001</td></tr>')
parts.append('<tr><th>Duracion</th><td>~13.4s (Playwright) | pipeline menos de 2m</td></tr>')
parts.append('<tr><th>Base URL</th><td>http://localhost:35017/AgendaWeb/</td></tr>')
parts.append('<tr><th>Usuario primario</th><td>PABLO (PEEMPRESA=0001 - NO es instancia Pacifico)</td></tr>')
parts.append('<tr><th>Login attempts</th><td>1</td></tr>')
parts.append('<tr><th>Browser launches</th><td>1</td></tr>')
parts.append('<tr><th>Modo</th><td>dry-run</td></tr>')
parts.append('</table></section>')

parts.append('<section id="qa-uat-effective-config"><h3>Configuracion efectiva (sin password)</h3>')
safe_cfg = {k:v for k,v in cfg.items() if 'pass' not in k.lower() and 'pwd' not in k.lower()}
parts.append('<pre>' + json.dumps(safe_cfg, indent=2, ensure_ascii=False) + '</pre></section>')

parts.append('<section id="qa-uat-defect"><div class="defect-box">')
parts.append('<h5>DEFECTO DETECTADO - CA-08 / ADO-116</h5>')
parts.append('<p><strong>Descripcion del defecto:</strong> El contador "Promesas a Vencer en 7 dias" es visible para el usuario <strong>PABLO</strong> (PEEMPRESA=0001, instancia estandar, no Pacifico). Segun CA-08, el contador NO debe aparecer en instancias no-Pacifico.</p>')
parts.append('<p><strong>Root cause hipotesis:</strong> En <code>trunk/OnLine/AIS.PR.UI.Web.Controls/AISMenu.cs</code>, el bloque de render usa condicion <code>if (!EsJudicial)</code> en lugar de <code>if (!EsJudicial &amp;&amp; EsInstanciaPacifico(usuario.CodUsuario))</code>. El metodo EsInstanciaPacifico() no existe en AISMenu.cs y no es invocado. El contador se renderiza para TODOS los usuarios no-judiciales.</p>')
parts.append('<p><strong>Evidencia directa (barraResumen HTML de PABLO):</strong></p>')
parts.append('<pre>' + barra.replace('<','&lt;').replace('>','&gt;') + '</pre>')
parts.append('<p><strong>Fix sugerido (para el Developer):</strong><br>')
parts.append('Cambiar en AISMenu.cs L~593: <code>if (!EsJudicial)</code><br>')
parts.append('por: <code>if (!EsJudicial &amp;&amp; EsInstanciaPacifico(usuario.CodUsuario))</code><br>')
parts.append('e implementar EsInstanciaPacifico() con query RPERFEMP.PEEMPRESA=\'0010\'.</p>')
parts.append('</div></section>')

parts.append('<section id="qa-uat-scenarios"><h3>Escenario ejecutado en este run</h3>')
parts.append('<article class="qa-scenario" id="scenario-P08"><h4>P08 - CA-08 - El contador NO debe aparecer en instancia no-Pacifico</h4>')
parts.append('<table>')
parts.append('<tr><th>Resultado</th><td><span class="FAIL">FAIL</span></td></tr>')
parts.append('<tr><th>Descripcion del test</th><td>Valida que el contador "Promesas a Vencer en 7 dias" NO sea visible para usuario instancia estandar. PABLO tiene PEEMPRESA=0001. La logica EsInstanciaPacifico() debe devolver false y el bloque no debe renderizarse.</td></tr>')
parts.append('<tr><th>Playbook usado</th><td>frmagenda_resumen_actividad</td></tr>')
parts.append('<tr><th>Pantalla objetivo</th><td>FrmAgenda.aspx</td></tr>')
parts.append('<tr><th>URL esperada</th><td>/FrmAgenda/</td></tr>')
parts.append('<tr><th>URL real</th><td>http://localhost:35017/AgendaWeb/FrmAgenda.aspx</td></tr>')
parts.append('<tr><th>Selector estable</th><td>.barraResumen</td></tr>')
parts.append('<tr><th>Oracle esperado</th><td>counter_visible === false</td></tr>')
parts.append('<tr><th>Oracle real</th><td>counter_visible === <strong>true</strong> (FALLA)</td></tr>')
parts.append('<tr><th>Ultimo paso exitoso</th><td>barraResumen localizada y HTML capturado</td></tr>')
parts.append('</table>')
parts.append('<h5>Pasos seguidos en la prueba</h5><ol>')
steps = ['Login como PABLO via globalSetup (storageState .auth/agenda.json)','goto http://localhost:35017/AgendaWeb/FrmAgenda.aspx (waitUntil: load)','waitForLoadState domcontentloaded','Verificar URL contiene FrmAgenda - PASS','Screenshot inicial (P08-01-initial.png)','Localizar .barraResumen - FOUND (barraFound=true)','Capturar innerHTML de barraResumen - contiene texto "Promesas a Vencer en 7 dias"','getByText(/Promesas.*Vencer/i) - count=1 (visible)','Screenshot estado contador (P08-02-counter-check.png)','Assertion: counter_visible===false - FAIL (received: true)']
for s in steps: parts.append('<li>' + s + '</li>')
parts.append('</ol>')
parts.append('<h5>Assertions</h5><pre>' + json.dumps(p08, indent=2, ensure_ascii=False) + '</pre>')
parts.append('<h5>barraResumen HTML real (PABLO)</h5><pre>' + barra.replace('<','&lt;').replace('>','&gt;') + '</pre>')
parts.append('<h5>Screenshots</h5>')
parts.append(img_tag(img1,'P08 pantalla inicial FrmAgenda con PABLO','P08 - Pantalla FrmAgenda.aspx con usuario PABLO (no-Pacifico). El bloque barraResumen muestra el contador cuando no deberia.'))
parts.append(img_tag(img2,'P08 contador visible FALLA','P08 - Contador visible para PABLO. CA-08 FALLA: se renderiza sin verificar instancia Pacifico.'))
parts.append('</article></section>')

parts.append('<section id="qa-uat-all-scenarios"><h3>Estado de todos los escenarios ADO-116</h3>')
parts.append('<table><tr><th>ID</th><th>CA</th><th>Resultado</th><th>Run</th><th>Motivo</th></tr>')
rows = [
    ('P01','CA-01','BLOCKED','001','TEST_DATA_EXPIRED - insertar CPFECVEN en ventana'),
    ('P02','CA-02','BLOCKED','001','TEST_DATA_MISSING - requiere 3 promesas exactas'),
    ('P03','CA-03','BLOCKED','001','TEST_DATA_MISSING - lote con 2 promesas en ventana'),
    ('P04','CA-04','BLOCKED','001','TEST_DATA_MISSING - CPFECVEN = hoy'),
    ('P05','CA-05','PASS','001','Counter visible=0 para PACIFICO (run anterior)'),
    ('P06','CA-06','BLOCKED','001','TEST_DATA_MISSING - GestorB con promesas'),
    ('P07','CA-07','BLOCKED','001','TEST_DATA_AMBIGUOUS - sin promesas activas'),
    ('P08','CA-08','FAIL','002','Counter visible para PABLO (no-Pacifico). EsInstanciaPacifico() no implementado.'),
    ('P09','CA-09','PASS','001','Recalculo consistente en reload (run anterior)'),
    ('P10','CA-10','BLOCKED','001','TEST_DATA_INSUFFICIENT - 0 promesas en ventana'),
]
for pid,ca,res,run,mot in rows:
    css = res
    parts.append(f'<tr><td>{pid}</td><td>{ca}</td><td><span class="{css}">{res}</span></td><td>{run}</td><td>{mot}</td></tr>')
parts.append('</table></section>')

parts.append('<section id="qa-uat-human-next-step"><h3>Proximo paso humano</h3><ol>')
parts.append('<li><strong>Defecto CA-08 (CRITICO):</strong> El Developer debe corregir AISMenu.cs - agregar EsInstanciaPacifico() en la condicion de render. El metodo no existe en AISMenu.cs.</li>')
parts.append(f'<li><strong>Datos P01-P04, P06, P07, P10:</strong> Insertar RCPAGO con CPFECVEN en [{today}, {d7}] para PACIFICO/PABLO6 (INSERT requiere admin).</li>')
parts.append('<li><strong>Re-ejecucion post-fix:</strong> Tras fix CA-08, re-ejecutar P08 con PABLO para confirmar PASS. Tras datos, re-ejecutar P01-P04, P06, P07, P10 con PACIFICO.</li>')
parts.append('<li>NO mover estado del ticket - el humano decide tras revisar este reporte.</li>')
parts.append('</ol></section>')
parts.append('</body></html>')

html = ''.join(parts)
with open(ev+'/ado_comment.html','w',encoding='utf-8') as f:
    f.write(html)
sz = os.path.getsize(ev+'/ado_comment.html')
print('OK size:', sz, 'bytes')
