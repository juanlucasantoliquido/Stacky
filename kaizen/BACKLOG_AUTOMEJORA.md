# Kaizen — Backlog de Automejora

> Archivo vivo. El loop lee esto para elegir el SIGUIENTE objetivo de mayor valor.
> Estado: [PENDIENTE] | [EN_PROGRESO] | [HECHO] | [PARKEADO]
> Actualizar al cerrar cada sesión que cierre un ítem o detecte deuda nueva.

---

## Alta prioridad

### B-01 [HECHO 2026-06-22] Dashboard estático HTML (kaizen/dashboard/index.html)
**Valor:** El prompt del operador lo pide explícitamente. Permite ver el estado sin servidor.
**Detalles:** `python kaizen.py dashboard` debe generar `kaizen/dashboard/index.html` autocontenido
(CSS/JS inline, sin CDN). Mostrar: pipeline 5 etapas con etapa actual, historial de sesiones con
veredicto, métricas forenses. Regenerar al cierre de CADA sesión. El servidor HTTP en vivo ya existe
(`scripts/dashboard.py`); esto agrega la variante estática.
**Métrica:** El archivo existe, se abre con `file://`, tiene las 3 secciones requeridas.
**Rollback:** Eliminar `kaizen/dashboard/index.html` y revertir cambio en `kaizen.py`.

### B-02 [HECHO 2026-06-22] Limpiar sesión open sin artefactos (043909Z)
**Valor:** La sesión `2026-06-22T043909Z__automejora-aotl-1-foco-playground` quedó con status=open
y proposal.md vacío (solo template). Contamina el índice y selfcheck la tolera pero no la limpia.
**Detalles:** Cerrar la sesión como `abandoned` en `_index.json` con nota explicativa.
**Métrica:** `python kaizen.py list` no muestra esa sesión en estado open.
**Rollback:** Revertir el campo `status` en `_index.json`.

### B-03 [HECHO 2026-06-22] Ampliar foco AOTL más allá de playground/
**Valor:** El loop actual solo toca `playground/`; las mejoras reales de Kaizen (docs, scripts,
contratos) quedan fuera del alcance AOTL.
**Detalles:** Actualizar `adapters/claude/adapter.yaml` (y el genérico) para incluir `docs/`,
`scripts/` (con denylist de maquinaria sensible), y `contracts/`. Agregar denylist explícita.
**Métrica:** El adapter.yaml actualizado contiene los nuevos focos y el loop no toca rutas protegidas.
**Rollback:** Revertir adapter.yaml al estado previo.

### B-04 [HECHO 2026-06-22] Subcomando `dashboard` genera HTML estático + ruta file://
**Valor:** El runbook y el prompt piden `python kaizen.py dashboard` que regenere el HTML estático
y muestre la ruta `file://`. Actualmente solo lanza el servidor HTTP.
**Detalles:** Hacer que `dashboard` sin `--port` genere el estático y lo imprima. Con `--port` sigue
siendo el servidor. Agregar a `kaizen.py` la bifurcación.
**Nota:** Dependencia de B-01 (el generador de HTML estático debe existir primero).
**Métrica:** `python kaizen.py dashboard` sin args genera `dashboard/index.html` y lo imprime.
**Rollback:** Revertir bifurcación en `kaizen.py`.

---

## Media prioridad

### B-05 [HECHO 2026-06-22] Tests unitarios para scripts core (new_session, run_session, validate)
**Valor:** La cobertura de tests es baja; solo hay `test_aotl.py`. Agregar tests para los scripts
más críticos reduce el riesgo de regresión en sesiones futuras.
**Detalles:** Crear `scripts/test_core.py` con tests de `new_session.py`, `validate.py`,
`run_session.py` usando fixtures mínimas.
**Métrica:** `python -m pytest scripts/test_core.py -q` da 0 fallos.
**Rollback:** Eliminar `scripts/test_core.py`.

### B-06 [HECHO 2026-06-22] Sincronizar MANIFEST.md con artefactos reales
**Valor:** MANIFEST.md puede estar desactualizado respecto a los scripts y contratos reales.
**Detalles:** Auditar MANIFEST.md contra `ls scripts/`, `ls contracts/`, `ls adapters/` y actualizar.
**Métrica:** Cada archivo en MANIFEST.md existe; no hay archivos reales no listados.
**Rollback:** Revertir MANIFEST.md.

### B-07 [HECHO 2026-06-22] Adapter de ejemplo end-to-end verificable (adapter distinto de claude/mock)
**Valor:** La arquitectura promete soporte de adapters para mejorar OTRAS aplicaciones, pero solo
hay dos (claude y mock). Un tercer adapter de ejemplo (ej: adapter para Stacky Agents) demostraría
la portabilidad real.
**Detalles:** Crear `adapters/stacky/adapter.yaml` con foco en `../Stacky Agents/backend/` y
un `observe.prompt` ajustado al contexto de Stacky.
**Métrica:** `python kaizen.py loop --engine mock --adapter stacky --max-iterations 1` corre sin error.
**Rollback:** Eliminar `adapters/stacky/`.

### B-08 [HECHO 2026-06-22] Gate: reportar ítem de bloqueante con descripción en decision.json
**Valor:** Actualmente el gate escribe `blocking: []` pero no explica por qué se disparó cada
bloqueante. El operador debe inferirlo del evaluation.json.
**Detalles:** Agregar campo `blocking_details` en `decision.json` con descripción de cada bloqueante.
**Métrica:** Al correr un gate con bloqueante, decision.json contiene `blocking_details` no vacío.
**Rollback:** Revertir cambio en `scripts/run_session.py`.

---

## Baja prioridad / Mantenimiento

### B-09 [HECHO 2026-06-22] README.md menciona el dashboard estático
**Valor:** La doc no cubre la variante estática del dashboard.
**Detalles:** Agregar sección en README.md sobre `python kaizen.py dashboard` (variante estática).
**Métrica:** README.md contiene la sección y no hay contradicción con el comportamiento real.
**Rollback:** Revertir README.md.

### B-10 [HECHO 2026-06-22] Prompt de observación AOTL más rico (incluye decisiones previas)
**Valor:** El prompt actual que recibe el motor solo ve el índice de sesiones, no las decisiones
promovidas (ADR-lite). Inyectar el resumen de decisions/ mejoraría la calidad de las propuestas.
**Detalles:** Actualizar `scripts/engine.py` o el adapter para incluir un resumen de `decisions/`.
**Métrica:** El prompt generado contiene al menos una línea de las decisions/ existentes.
**Rollback:** Revertir cambio en engine.py / adapter.

---

### B-11 [HECHO 2026-06-22] Regeneración automática del dashboard al cerrar cada sesión
**Valor:** El prompt del operador dice "regeneralo al cierre de CADA sesión". Actualmente solo se
regenera si el operador llama manualmente a `python kaizen.py dashboard`.
**Detalles:** Agregar llamada a `dashboard_static.py` al final de `run_session.py` (tras cerrar la
sesión). Solo si `dashboard/` existe ya (para no crearlo en tests). La llamada silencia errores
(el dashboard es best-effort; no debe romper el gate).
**Métrica:** Tras `python kaizen.py run <id>`, `dashboard/index.html` tiene fecha de modificación
más reciente que antes del run.
**Rollback:** Eliminar la llamada en `run_session.py`.

### B-12 [HECHO 2026-06-22] Test unitario para recent_decisions_summary (autoloop.py)
**Valor:** La funcion recien agregada no tiene tests unitarios.
**Detalles:** Agregar cases en `scripts/test_core.py` para `recent_decisions_summary` con
fixtures de decisions/ simuladas en tempdir.
**Métrica:** `python scripts/test_core.py` da 0 fallas con al menos 2 casos nuevos.
**Rollback:** Eliminar los 2 casos nuevos de test_core.py.

### B-13 [PENDIENTE] Dashboard: sección de bloqueantes activos y sesiones iterate
**Valor:** El dashboard actual muestra historial de sesiones pero no resalta las que quedaron en
estado iterate/escalado (sesiones que el operador debe revisar manualmente). El loop es invisible
cuando algo escala.
**Detalles:** Agregar en `dashboard_static.py` una sección "Pendiente revisión humana" con las
sesiones status=closed verdict=iterate o escalated_to_human=true. Colores: rojo para bloqueantes,
amarillo para confianza baja.
**Métrica:** Tras crear una sesión con verdict=iterate, el HTML generado muestra esa sesión en rojo/amarillo.
**Rollback:** Eliminar la sección de `dashboard_static.py`.

### B-14 [PENDIENTE] test_aotl.py: ampliar con tests de run_session (gate con scores distintos)
**Valor:** test_aotl.py solo cubre el loop end-to-end con mock. No hay tests del gate con scores
en zona iterate (7-10) ni en zona reject (<7). Una regresión del gate podría pasar desapercibida.
**Detalles:** Agregar en `scripts/test_aotl.py` al menos 3 casos: accept (>=11), iterate (7-10),
reject (<7). Usar fixtures de proposal/evaluation en tempdir.
**Métrica:** `python scripts/test_aotl.py` corre sin fallos con los 3 nuevos casos.
**Rollback:** Eliminar los 3 casos nuevos.

### B-15 [PENDIENTE] Selfcheck detecta sesiones decide->closed olvidadas (status=decided)
**Valor:** En esta sesión se encontraron 2 sesiones con status=decided (deberían ser closed).
Selfcheck las contaba como OK. El invariante debería verificar que status=decided solo existe
para sesiones en vuelo (recién decididas por el gate, antes de que run_session las cierre).
**Detalles:** En `scripts/selfcheck.py`, agregar regla: status=decided es válido solo si
existe session.output.json Y la sesión tiene edad < 5 minutos. Si es más vieja, reportar WARNING.
**Métrica:** `python kaizen.py selfcheck` da WARNING para sesiones decided viejas.
**Rollback:** Eliminar la regla en selfcheck.py.

---

### B-16 [HECHO 2026-06-22] Proteger scripts criticos de maquinaria en PROTECTED_FILES
**Valor:** run_session.py, validate.py, forensic.py, new_session.py, selfcheck.py, spawn_child.py
y promote_decision.py no estan en PROTECTED_FILES. El loop AOTL podria auto-editarlos y
autosabotearse silenciosamente en caliente.
**Detalles:** Agregar esos 7 scripts a PROTECTED_FILES en aotl_state.py. Scripts editables
por el loop (tests, visualizacion, metrics, adapter_info, doctor, archive, check): se dejan libres.
**Métrica:** `st.safe_target_path("scripts/run_session.py")` lanza ValueError.
`st.safe_target_path("scripts/test_core.py")` no lanza (editable).
**Rollback:** Quitar las entradas de PROTECTED_FILES.

### B-17 [HECHO 2026-06-22] Dashboard: mostrar ruta file:// clickeable en el header
**Valor:** El dashboard no muestra su propia URL. El operador debe recordar la ruta o correr
de nuevo el comando para verla. Agregar el link en el header facilita compartir/reabrir.
**Detalles:** En generate_html(), agregar en el header un link href='<url_relativa>' o simplemente
el texto de la ruta. En file:// los links a rutas absolutas funcionan en los browsers modernos.
**Métrica:** El HTML generado contiene un elemento con la ruta del archivo (al menos como texto).
**Rollback:** Eliminar el elemento del header.

### B-18 [HECHO 2026-06-22] Actualizar docs/07_AOTL_AUTODRIVE.md con cambios de sesiones B-01..B-17
**Valor:** El doc dice "python kaizen.py dashboard lanza HTTP" pero ahora genera un HTML estatico.
No menciona blocking_details, la seccion de revision humana del dashboard, ni PROTECTED_FILES
ampliado. La doc desactualizada confunde a quien lee el runbook.
**Detalles:** (1) Cambiar la descripcion del subcomando dashboard: ahora genera dashboard/index.html
(file://). Con --port sigue siendo el servidor. (2) Mencionar blocking_details en el gate.
(3) Mencionar la seccion de revision humana en el dashboard. (4) Actualizar lista de PROTECTED_FILES.
**Métrica:** docs/07_AOTL_AUTODRIVE.md menciona 'file://', 'blocking_details', 'revision humana' y la lista actualizada. selfcheck: 0 fallas.
**Rollback:** Revertir docs/07_AOTL_AUTODRIVE.md.

### B-19 [PENDIENTE] Adapter denylist: sincronizar comentario con PROTECTED_FILES actual
**Valor:** El comentario DENYLIST en adapters/claude/adapter.yaml lista 9 scripts pero ya
hay 15 protegidos (los 7 nuevos de B-16 no aparecen). Quien edite el adapter podria omitirlos.
**Detalles:** Actualizar el comentario DENYLIST en adapters/claude/adapter.yaml con los 7 nuevos.
Solo es documentacion del adapter; la proteccion real esta en aotl_state.py.
**Metrica:** adapters/claude/adapter.yaml menciona 'run_session.py', 'selfcheck.py', 'validate.py'.
**Rollback:** Revertir el comentario en adapter.yaml.

### B-20 [PENDIENTE] doctor verifica PROTECTED_FILES no modificados (integridad del guardarrail)
**Valor:** El doctor verifica que scripts/contratos existen pero no verifica que PROTECTED_FILES
no fue manipulado. Si alguien agrega un script a PROTECTED_FILES que no existe, safe_target_path
funciona mal en silencio (rechaza paths invalidos sin alertar).
**Detalles:** En doctor.py agregar check: cada ruta en PROTECTED_FILES existe en kaizen/ (o es
ignorada si tiene prefijo de tipo 'scripts/' — en ese caso verifica que la ruta este en la tupla
de aotl_state.py). Reportar WARN si algun PROTECTED_FILE no existe.
**Metrica:** python kaizen.py doctor da OK en todos los checks de PROTECTED_FILES. Si borramos
un script listado en PROTECTED_FILES, da WARN.
**Rollback:** Eliminar el check de doctor.py.

### B-21 [PENDIENTE] test_aotl: guardarrail debe verificar los 7 scripts nuevos en PROTECTED_FILES
**Valor:** El test 'guardarrail: maquinaria del loop protegida' solo prueba 3 de los 10 scripts
en PROTECTED_FILES (kaizen.py, apply.py, autoloop.py). Los 7 nuevos (run_session, validate,
forensic, new_session, selfcheck, spawn_child, promote_decision) no estan en el test. Si alguien
los saca de PROTECTED_FILES, los tests no lo detectan.
**Detalles:** Ampliar el test existente en test_aotl.py para incluir los 7 scripts nuevos
(o agregar un caso adicional que los itere todos).
**Metrica:** python scripts/test_aotl.py: 20/20 verdes y el test guardarrail prueba todos
los scripts en PROTECTED_FILES.
**Rollback:** Revertir el cambio en test_aotl.py.

### B-22 [PENDIENTE] metrics: agregar latencia p95 y tasa de escalacion al reporte JSON
**Valor:** El reporte de metrics reporta media/mediana/min/max de latencia pero no p95 (percentil
que suele importar mas que la media). Tampoco normaliza la tasa de escalacion. Datos utiles para
detectar runs que tardan mucho.
**Detalles:** En scripts/metrics.py, agregar p95_elapsed_ms (sorted list, indexado en 95%) y
escalation_rate (escalations_to_human / sessions_total). Actualizar print_report.
**Metrica:** python kaizen.py metrics --json contiene 'p95_elapsed_ms' y 'escalation_rate'.
**Rollback:** Quitar los 2 campos de summarize() y print_report().

## Items parkeados (REVIEW_QUEUE)

*(ninguno parkeado aún — ver kaizen/REVIEW_QUEUE.md cuando exista)*

---

## Historial de items cerrados

- B-01: Dashboard estático HTML — sesión 052633Z (2026-06-22)
- B-02: Limpiar sesiones open huérfanas — sesión 052346Z (2026-06-22)
- B-03: Ampliar foco AOTL docs/ y scripts/ — sesión 052910Z (2026-06-22)
- B-04: Subcomando dashboard genera file:// — incluido en B-01
- B-05: Tests unitarios core (new_session, validate) — sesión 053031Z (2026-06-22)
- B-06: Sincronizar MANIFEST.md — sesión 053151Z (2026-06-22)
- B-07: Adapter Stacky end-to-end — sesión 053400Z (2026-06-22)
- B-08: Gate blocking_details — sesión 053558Z (2026-06-22)
- B-09: README dashboard estático — sesión 053307Z (2026-06-22)
- B-10: Contexto AOTL decisions ADR-lite — sesión 053808Z (2026-06-22)
- B-11: Regeneración automática dashboard — sesión 054032Z (2026-06-22)
- B-12: Tests unitarios recent_decisions_summary — sesión 054144Z (2026-06-22)
- B-13: Dashboard sección revisión humana — sesión 054632Z (2026-06-22)
- B-14: Tests gate zonas iterate/reject — sesión 054741Z (2026-06-22)
- B-15: Selfcheck detecta decided huérfanas — sesión 054844Z (2026-06-22)
- B-16: PROTECTED_FILES maquinaria crítica — sesión 055032Z (2026-06-22)
- B-17: Dashboard URL file:// en header — sesión 055139Z (2026-06-22)
