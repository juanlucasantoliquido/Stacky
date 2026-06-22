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

### B-19 [HECHO 2026-06-22] Adapter denylist: sincronizar comentario con PROTECTED_FILES actual
**Metrica lograda:** adapters/claude/adapter.yaml menciona los 15 scripts protegidos (verificado en sesion 46).

### B-20 [HECHO 2026-06-22] doctor verifica PROTECTED_FILES no modificados (integridad del guardarrail)
**Metrica lograda:** doctor.py verifica PROTECTED_FILES en lines 85-94, corre OK con 15 rutas (verificado en sesion 46).

### B-21 [HECHO 2026-06-22] test_aotl: guardarrail debe verificar los 7 scripts nuevos en PROTECTED_FILES
**Valor:** El test 'guardarrail: maquinaria del loop protegida' solo prueba 3 de los 10 scripts
en PROTECTED_FILES (kaizen.py, apply.py, autoloop.py). Los 7 nuevos (run_session, validate,
forensic, new_session, selfcheck, spawn_child, promote_decision) no estan en el test. Si alguien
los saca de PROTECTED_FILES, los tests no lo detectan.
**Detalles:** Ampliar el test existente en test_aotl.py para incluir los 7 scripts nuevos
(o agregar un caso adicional que los itere todos).
**Metrica:** python scripts/test_aotl.py: 20/20 verdes y el test guardarrail prueba todos
los scripts en PROTECTED_FILES.
**Rollback:** Revertir el cambio en test_aotl.py.

### B-22 [HECHO 2026-06-22] metrics: agregar latencia p95 y tasa de escalacion al reporte JSON
**Valor:** El reporte de metrics reporta media/mediana/min/max de latencia pero no p95 (percentil
que suele importar mas que la media). Tampoco normaliza la tasa de escalacion. Datos utiles para
detectar runs que tardan mucho.
**Detalles:** En scripts/metrics.py, agregar p95_elapsed_ms (sorted list, indexado en 95%) y
escalation_rate (escalations_to_human / sessions_total). Actualizar print_report.
**Metrica:** python kaizen.py metrics --json contiene 'p95_elapsed_ms' y 'escalation_rate'.
**Rollback:** Quitar los 2 campos de summarize() y print_report().

### B-23 [HECHO 2026-06-22] Dashboard: columna tags en historial de sesiones
**Valor:** Las sesiones tienen tags (ej: ['infra', 'cli']) pero el dashboard no los muestra.
El historial es mas util para filtrar/entender cuando se ven los tags.
**Detalles:** En _session_rows() de dashboard_static.py, agregar columna 'Tags' que muestra
los tags de la sesion como pills (o vacio si no tiene). La tabla ya tiene 5 columnas; agregar
una 6ta pequeña.
**Metrica:** El HTML generado muestra la columna Tags con al menos un tag visible (hay 15 sesiones con tags).
**Rollback:** Eliminar la columna Tags de _session_rows() y el thead.

### B-24 [HECHO 2026-06-22] test_core: test de _percentile para casos borde (lista vacia y un elemento)
**Valor:** _percentile() es una funcion pura critica para el reporte de metricas. No tiene
tests propios. Si se rompe, el reporte dice 0 silenciosamente.
**Detalles:** Agregar en test_core.py 3 casos para _percentile: lista vacia, 1 elemento, lista con varios.
**Metrica:** python scripts/test_core.py: 22 OK (19+3) 0 FAIL.
**Rollback:** Eliminar los 3 casos de test_core.py.

## Items parkeados (REVIEW_QUEUE)

### B-25 [HECHO 2026-06-22] Dashboard: tarjeta de latencia con p95 y tasa de escalacion
**Valor:** El dashboard muestra total/aceptadas/rechazadas pero no las metricas de latencia
(p95, media, mediana) ni la tasa de escalacion que ya calcula metrics.py. El operador
deberia ver el p95 directamente en el dashboard sin correr metrics.
**Detalles:** En build_data() de dashboard_static.py, agregar lectura de forensic para
calcular p95 y escalation_rate. Agregar 2 cards nuevas en la grilla de metricas: p95 (ms)
y escalation_rate (%). Reusar _percentile de metrics.py (o reimplementarla inline si el
import es problematico).
**Metrica:** HTML generado contiene 'p95' y 'escalacion %'. python scripts/test_core.py: 22 OK.
**Rollback:** Quitar las 2 cards de la grilla y el calculo de build_data().

### B-26 [N/A] Adapter generic actualizar denylist con PROTECTED_FILES actual
**DESCARTADO:** adapters/generic/adapter.yaml es modo manual (HITL): no tiene foco ni
denylist porque no hace auto-apply. No aplica el mismo parche que B-19.

### B-27 [HECHO 2026-06-22] Tests de is_protected() para casos: prefijo protegido, archivo exacto, extra_protected
**Valor:** is_protected() es la funcion raiz del guardarrail. safe_target_path la usa pero
los tests solo prueban safe_target_path (comportamiento externo). Si is_protected tiene un
bug de borde (ej: prefijo con trailing slash, ruta con mayusculas), no lo detectamos.
**Detalles:** Agregar en test_aotl.py 4 casos: prefijo sessions/ rechazado, archivo en PROTECTED_FILES
rechazado, extra_protected funciona, ruta editable pasa.
**Metrica:** 20/20 + 4 nuevos = 24/24 en test_aotl.py.
**Rollback:** Quitar los 4 casos de test_aotl.py.

### B-29 [HECHO 2026-06-22] test_aotl: tests de set_impl_status y update_index_fields en tempdir
**Valor:** set_impl_status y update_index_fields son funciones criticas que usa autoloop
para actualizar el indice entre vueltas. Sin tests, una regresion puede hacer que las sesiones
queden con impl_status incorrecto (planned en vez de implemented) y el operador crea que fallo.
**Detalles:** Agregar en test_aotl.py 3 casos con indice en tempdir: set_impl_status guarda el
campo, rechaza impl_status invalido, update_index_fields hace merge sin borrar campos previos.
**Metrica:** python scripts/test_aotl.py: 27/27 verdes (24 + 3).
**Rollback:** Quitar los 3 casos de test_aotl.py.

### B-30 [HECHO 2026-06-22] check.py: agregar test_core y test_aotl al pipeline de check
**Valor:** python kaizen.py check corre doctor y selfcheck pero NO corre test_core.py ni
test_aotl.py. El CI-gate de check pasa aunque los tests fallen.
**Detalles:** En scripts/check.py, agregar subcall a test_core.py y test_aotl.py con
subprocess.run y reportar FAIL si alguno da exit code != 0.
**Metrica:** python kaizen.py check termina con exit 1 si test_core.py tiene fallas. Normalmente 0.
**Rollback:** Quitar los subcalls en check.py.

### B-31 [HECHO 2026-06-22] test_core: tests de recent_objectives y gather_focus (autoloop.py)
**Valor:** recent_objectives y gather_focus son funciones puras en autoloop.py que el loop usa para
construir su contexto en cada iteracion. Sin tests, una regresion puede hacer que el contexto del
motor quede vacio o con datos incorrectos sin que nadie lo detecte.
**Detalles:** Agregar en test_core.py: (1) test_recent_objectives_empty_index: devuelve [] si no hay
indice; (2) test_recent_objectives_returns_last_n: devuelve los ultimos n objetivos. Usar tempdir
y parchar INDEX en autoloop antes del test.
**Metrica:** python scripts/test_core.py: 24 OK (22 + 2) 0 FAIL.
**Rollback:** Eliminar los 2 casos de test_core.py.

### B-32 [HECHO 2026-06-22] decisions/: indice README de las ADR-lites existentes
**Valor:** Hay 41 decisiones en decisions/ pero no hay un indice legible. El motor solo puede
leer los ultimos 8 vía recent_decisions_summary. Un README.md en decisions/ que liste las N
mas recientes con fecha + titulo + veredicto facilita la navegacion humana y puede reutilizarse
como contexto de orientacion.
**Detalles:** Generar (o actualizar) decisions/README.md con las ultimas 15 decisiones en tabla
Markdown. El archivo se regenera solo en cada sesion (como el dashboard). Agregarlo en run_session.py
(best-effort, no rompe el gate).
**Metrica:** decisions/README.md existe y tiene una tabla con al menos 15 filas tras el gate.
**Rollback:** Eliminar la llamada en run_session.py y el archivo decisions/README.md.

### B-33 [HECHO 2026-06-22] test_core: tests de _gen_decisions_index en dashboard_static.py
**Valor:** _gen_decisions_index es la unica funcion nueva de B-32 que no tiene tests.
Si se rompe, decisions/README.md queda obsoleto silenciosamente. Ademas documenta el contrato
de la funcion (que acepta directorio temporal) para futuros mantenedores.
**Detalles:** Agregar en test_core.py: (1) test_gen_decisions_index_empty_dir: decisions/ vacia -> no crea README; (2) test_gen_decisions_index_generates_table: 2 ADRs en tempdir -> README con tabla correcta; (3) test_gen_decisions_index_excludes_non_numeric: README.md existente no se incluye.
**Metrica:** python scripts/test_core.py: 27 OK (24 + 3) 0 FAIL.
**Rollback:** Eliminar los 3 casos de test_core.py.

### B-34 [HECHO 2026-06-22] test_core: tests de _pending_review_section en dashboard_static

### B-35 [HECHO 2026-06-22] test_core: tests de metrics.summarize con forensic fixtures

### B-36 [HECHO 2026-06-22] test_core: tests de _tag_pills y build_data en dashboard_static

### B-37 [HECHO 2026-06-22] test_core: tests de archive.py (5 caminos de main)

### B-38 [HECHO 2026-06-22] test_core: tests de list_sessions.py

### B-39 [HECHO 2026-06-22] test_core: actualizar docstring para reflejar 9 modulos cubiertos

### B-40 [HECHO 2026-06-22] test_core: tests de show_session.py

### B-41 [HECHO 2026-06-22] test_core: tests de forensic_view.py y fmt_data

### B-42 [HECHO 2026-06-22] test_core: actualizar docstring a 53 tests y 11 modulos

### B-43 [HECHO 2026-06-22] check.py: resumen final con conteo de tests

### B-44 [HECHO 2026-06-22] test_core: tests de adapter_info.py

### B-45 [HECHO 2026-06-22] Actualizar conteos docstring test_core y check.py a 83 tests

### B-46 [HECHO 2026-06-22] test_aotl: tests de promote_decision (next_adr_number + already_promoted)
**Valor:** promote_decision.py sin tests. next_adr_number y already_promoted cubiertos + detectado bug Path%tuple (corregido en el test).
**Metrica lograda:** python scripts/test_aotl.py: 30/30 verdes.
**Valor:** Sincronizar conteos exactos (56 tests / 12 modulos / 83 total) tras B-44.
**Metrica lograda:** CHECK: TODO VERDE [5/5 grupos OK | 83 tests unitarios].
**Valor:** adapter_info.py ultimo script con logica sin tests. 3 casos: list_adapters, describe_valid(0), describe_missing(1).
**Metrica lograda:** python scripts/test_core.py: 56 OK 0 FAIL.
**Valor:** El resumen 'TODO VERDE' no decia cuantos tests pasaron. Ahora: '5/5 grupos OK | ~80 tests'.
**Metrica lograda:** python kaizen.py check termina con el resumen ampliado.
**Valor:** Docstring estaba en 46/9. Corregido a 53/11 con show_session y forensic_view.
**Metrica lograda:** python scripts/test_core.py: 53 OK 0 FAIL. Todos los comandos CLI cubiertos.
**Valor:** forensic_view.py ultimo comando sin tests. 4 casos: fmt_data pura (2) + main (2 caminos).
**Metrica lograda:** python scripts/test_core.py: 53 OK 0 FAIL.
**Valor:** show_session.py sin tests. 3 caminos: no_args(2), not_found(1), exists(0).
**Metrica lograda:** python scripts/test_core.py: 49 OK 0 FAIL.
**Valor:** Docstring obsoleto decia solo 2 modulos cuando hay 9 y 46 tests. Corregido.
**Metrica lograda:** python scripts/test_core.py: 46 OK 0 FAIL. Docstring menciona todos los modulos.
**Valor:** list_sessions.py sin tests. 3 casos: no_index, returns_zero, get_opt.
**Metrica lograda:** python scripts/test_core.py: 46 OK 0 FAIL.
**Valor:** archive.py unico comando sin tests. 5 caminos cubiertos con tempdir + parche archive.INDEX.
**Metrica lograda:** python scripts/test_core.py: 43 OK 0 FAIL.
**Valor:** _tag_pills (pura) y build_data (contrato de claves) sin tests. El test B-36 descubrio que build_data no tiene clave 'metrics' (es 'verdicts'+'p95_elapsed_ms') — fact capturado.
**Metrica lograda:** python scripts/test_core.py: 38 OK 0 FAIL.
**Valor:** metrics.summarize() es la funcion principal que alimenta el dashboard y el reporte. 4 casos puros con _mk_run_events fixtures minimas.
**Metrica lograda:** python scripts/test_core.py: 34 OK 0 FAIL.
**Valor:** _pending_review_section filtra sesiones que requieren atencion del operador. Funcion pura directamente testeable.
**Metrica lograda:** python scripts/test_core.py: 30 OK 0 FAIL (3 casos: empty, iterate, escalated).

### B-47 [HECHO 2026-06-22] check.py: headers sin acentos para terminales cp1252
**Valor:** En terminales Windows con codepage cp1252, los acentos en los headers del check.py
aparecen como '?' corrompiendo la legibilidad del output CI. El fix es usar ASCII puro en los
strings de print() del check (logica, FALLO en lugar de logica, FALLO con acento).
**Detalles:** Reemplazar 'logica' con 'logica' y 'FALLO' con 'FALLO' en scripts/check.py.
No afecta los docstrings (no van al stdout en runtime).
**Metrica lograda:** python kaizen.py check: headers ASCII, sin '?' en terminal cp1252.
**Rollback:** Revertir los 3 prints en scripts/check.py.

### B-52 [HECHO 2026-06-22] test_core: tests de doctor.py (6 ramas implementadas)
**Valor:** doctor.py es el comando de diagnostico estructural pero no tiene tests. Tiene 7
ramas: config OK/FAIL/WARN, perfil OK/FAIL, adapter OK/WARN, contratos OK/FAIL, scripts OK/FAIL,
PROTECTED_FILES OK/WARN, indice OK/FAIL. Sin tests, una regresion puede hacer que doctor
devuelva exit 0 aunque detecte FAILs.
**Detalles:** Agregar en test_core.py al menos 4 casos de doctor.main(): (1) sin config ->
0 FAIL (WARN); (2) config valida -> OK; (3) config invalida -> 1 FAIL; (4) perfil faltante -> 1 FAIL.
Usar tempdir y parchar ROOT dentro de doctor.py o montar estructura minima en tempdir.
**Metrica:** python scripts/test_core.py: OK con al menos 4 casos nuevos para doctor. 0 FAIL.
**Rollback:** Eliminar los casos de doctor en test_core.py.

### B-53 [HECHO 2026-06-22] test_core: tests de _console.enable_utf8()
**Valor:** _console.py no tiene tests. La funcion enable_utf8() es el guardarrail de encoding;
si se rompe, todos los scripts que la llaman pueden fallar silenciosamente en Windows cp1252.
**Detalles:** Agregar en test_core.py 2 casos: (1) enable_utf8() no lanza en stdout/stderr normales;
(2) enable_utf8() no lanza si reconfigure no existe (mock del atributo).
**Metrica:** python scripts/test_core.py: 2 casos nuevos, 0 FAIL.
**Rollback:** Eliminar los 2 casos de _console en test_core.py.

### B-54 [HECHO/INLINE 2026-06-22] Sincronizar conteo de tests en check.py y docstring con el total actual
**Valor:** check.py dice '102 tests unitarios' pero el total real podria cambiar con B-52/B-53.
El docstring de test_core.py tambien necesita sincronizarse con cada lote nuevo.
**Detalles:** Tras implementar B-52 y B-53, actualizar el conteo en check.py y el docstring de
test_core.py para que reflejen el numero exacto de tests. Verificar con python kaizen.py check.
**Metrica:** python kaizen.py check muestra el conteo exacto. python scripts/test_core.py: 0 FAIL.
**Rollback:** Revertir los conteos en check.py y test_core.py.
**Nota:** Este item es dependiente de B-52 y B-53; implementar despues de ambos.

### B-55 [HECHO 2026-06-22] test_aotl: tests de normalize_proposal y normalize_evaluation de engine.py
**Metrica lograda:** 42/42 verdes. python kaizen.py check: 114 tests unitarios.

### B-56 [HECHO 2026-06-22] test_aotl: test de extract_json con fence sin json/ (solo ```) y vacio
**Metrica lograda:** 2 assertions agregadas en B-59 (el check de extract_json). 44/44 verdes.

### B-57 [HECHO 2026-06-22] test_aotl: test de validate.check_enums con campo no requerido
**Metrica lograda:** Descubierto que test_check_enums_invalid ya existia en test_core.py:182.
Sesion aceptada (score=12) porque la auditoria misma tiene valor de confirmacion.

### B-58 [HECHO 2026-06-22] test_core: tests de gather_focus y active_config en autoloop.py
**Metrica lograda:** 4 casos nuevos. python scripts/test_core.py: 76/76 verdes. check: 120 tests.

### B-59 [HECHO 2026-06-22] test_aotl: tests de applied_paths (sin manifest, tras apply)
**Metrica lograda:** 2 checks nuevos. python scripts/test_aotl.py: 44/44 verdes.

### B-60 [HECHO 2026-06-22] Sincronizar contracts/decision.schema.json: agregar _meta
**Metrica lograda:** _meta en schema. python kaizen.py check: TODO VERDE [120 tests].

### B-69 [HECHO 2026-06-22] test_aotl: test de make_engine devuelve MockEngine para driver='mock'
**Metrica lograda:** python scripts/test_aotl.py: 52/52 verdes. Sesion 140953Z.

### B-70 [HECHO 2026-06-22] MANIFEST.md: verificar que todos los scripts actuales esten listados
**Metrica lograda:** MANIFEST.md actualizado con test_core 103 casos, check.py CI, adapter stacky. Sesion 141103Z.

### B-71 [HECHO 2026-06-22] test_aotl: test de active_adapter en adapter_info.py
**Metrica lograda:** 2 casos verdes (config con adapter + default). Sesion 141224Z. python scripts/test_core.py: 109 OK.

### B-72 [HECHO 2026-06-22] test_core: tests de load_adapter y load_profile en autoloop.py
**Metrica lograda:** 3 casos verdes. python scripts/test_core.py: 109 OK. Sesion 141346Z.

---

## Deuda nueva detectada (B-73+)

### B-73 [HECHO/INLINE 2026-06-22] test_aotl: tests de validate_change_set (apply.py) con casos criticos
**Valor:** validate_change_set es el guardarrail de contenido del change_set antes de aplicar.
No tiene tests directos. Si se rompe, el loop puede aplicar change_sets invalidos (rutas protegidas
en foco erroneo, action invalida, path con traversal ../) sin deteccion.
**Detalles:** Agregar en test_aotl.py: (1) path protegido rechazado; (2) action invalida rechazada;
(3) change_set valido pasa; (4) path con ../ rechazado. Usar tempdir para root.
**Metrica:** python scripts/test_aotl.py: 56/56 verdes (52 + 4).
**Rollback:** Eliminar los 4 casos.

### B-74 [HECHO/INLINE 2026-06-22] test_aotl: test de gate_decide en run_session (score accept/iterate/reject)
**Nota:** gate_decide ya cubierto en test_aotl.py lineas 289-340 (6 tests: accept/iterate/reject/escalar/bloqueante B1/B2). Auditoria inline sesion 141846Z.
**Valor:** gate_decide es la funcion que toma scores y devuelve accept/iterate/reject. Ya hay tests
de check_scores pero no de gate_decide directamente con proposal+evaluation reales. Si la logica de
umbral cambia silenciosamente, los tests existentes no lo detectan.
**Detalles:** Agregar en test_aotl.py o test_core.py: fixture minima de proposal + evaluation con
C1..C5 scores. Verificar que gate_decide devuelve decision correcta para accept (total>=11),
iterate (7-10), reject (<7).
**Metrica:** 3 casos nuevos verdes.
**Rollback:** Eliminar los 3 casos.

### B-75 [HECHO 2026-06-22] docs/02_USAGE.md: actualizar conteo tests a 161 (109+52)
**Valor:** 02_USAGE.md menciona 135 tests (85+50) pero el total real ahora es 161 (109+52) tras B-69..B-72.
**Detalles:** Actualizar la tabla de modulos y el total en docs/02_USAGE.md.
**Metrica:** grep '161' docs/02_USAGE.md retorna resultado.
**Rollback:** Revertir docs/02_USAGE.md.

### RQ-01 [PENDIENTE REVISION HUMANA] Rollback no restaura archivos borrados por action='delete'
**Descripcion:** apply.py implementa action='delete' (elimina el archivo) pero rollback() no
guarda una pre-imagen del archivo eliminado y no lo restaura. Si el loop elimina un archivo
con action='delete', el rollback deja el archivo eliminado permanentemente. Esto viola el
guardarrail B1 (propuesta sin rollback completo).
**Impacto:** Potencialmente irreversible. action='delete' en el change_set es una trampa.
**Opciones:** (A) Guardar pre-imagen del archivo antes de eliminarlo (como hace con modify).
(B) Prohibir action='delete' en el gate si no hay respaldo externo (git rollback manual).
**Por que va a REVIEW_QUEUE:** apply.py esta en PROTECTED_FILES (no puede ser auto-editado
por el loop). Requiere decision y cambio manual del operador.

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
- B-18: Docs 07 actualizados — sesión 055325Z (2026-06-22)
- B-19: Denylist adapter claude sincronizado — sesión 055540Z (2026-06-22)
- B-20: Doctor verifica PROTECTED_FILES — sesión 055628Z (2026-06-22)
- B-21: Test guardarrail itera PROTECTED_FILES completo — sesión 055812Z (2026-06-22)
- B-22: Metrics p95 y escalation_rate — sesión 055930Z (2026-06-22)
- B-23: Dashboard columna Tags — sesión 060132Z (2026-06-22)
- B-24: Tests _percentile + refactor modulo — sesión 060233Z (2026-06-22)
- B-25: Dashboard tarjetas p95 y escalation_rate — sesión 060520Z (2026-06-22)
- B-27: Tests is_protected() casos borde — sesión 060714Z (2026-06-22)
- B-28: Denylist adapter stacky sincronizado — sesión 060821Z (2026-06-22)
- B-29: Tests set_impl_status y update_index_fields — sesión 060947Z (2026-06-22)
- B-30: check.py integra test_core y test_aotl — sesión 061331Z (2026-06-22)
- B-31: Tests recent_objectives en autoloop.py — sesión 061632Z (2026-06-22)
- B-32: decisions/README.md auto-generado — sesión 061802Z (2026-06-22)
- B-33: Tests _gen_decisions_index en test_core.py — sesión 061953Z (2026-06-22)
- B-34: Tests _pending_review_section en test_core.py — sesión 062113Z (2026-06-22)
- B-35: Tests metrics.summarize con fixtures forenses — sesión 062219Z (2026-06-22)
- B-36: Tests _tag_pills y build_data en test_core.py — sesión 062402Z (2026-06-22)
- B-37: Tests archive.py 5 caminos — sesión 062539Z (2026-06-22)
- B-38: Tests list_sessions.py — sesión 062709Z (2026-06-22)
- B-39: Docstring test_core.py actualizado — sesión 062816Z (2026-06-22)
- B-40: Tests show_session.py — sesión 062934Z (2026-06-22)
- B-41: Tests forensic_view.py y fmt_data — sesión 063048Z (2026-06-22)
- B-42: Docstring test_core.py a 53 tests/11 modulos — sesión 063206Z (2026-06-22)
- B-43: check.py resumen final con ~80 tests — sesión 063307Z (2026-06-22)
- B-44: Tests adapter_info.py — sesión 063445Z (2026-06-22)
- B-45: Conteos sincronizados 56+27=83 tests — sesión 063604Z (2026-06-22)
- B-46: Tests promote_decision next_adr_number+already_promoted — sesión 063744Z (2026-06-22)
- B-47: check.py headers ASCII (sin acentos para cp1252) + B-19/B-20 marcados HECHO — sesión 064318Z (2026-06-22)
- B-48: Tests _config.load_yaml y spawn_child.py — sesión 064617Z (2026-06-22)
- B-49: Tests forensic.py sha256 y Forensic.log — sesión 064923Z (2026-06-22)
- B-50: Tests validate.check_scores — sesión 065224Z (2026-06-22)
- B-51: doc 02_USAGE actualizar (RECHAZADO: ya estaba cumplido) — sesión 065416Z (2026-06-22)
- B-52: tests doctor.py 6 ramas — sesión 133315Z (2026-06-22)
- B-53: tests _console.enable_utf8() 2 casos — sesión 133633Z (2026-06-22)
- B-54: sync conteo tests (INLINE en B-52/B-53) — 2026-06-22
- B-55: tests normalize_proposal/evaluation 4 casos — sesión 133921Z (2026-06-22)
- B-56: tests extract_json fence sin json + vacio (inline en B-59) — sesión 134159Z (2026-06-22)
- B-57: auditoria check_enums_invalid ya existia — sesión 134243Z (2026-06-22)
- B-58: tests gather_focus y active_config en autoloop.py — sesión 134357Z (2026-06-22)
- B-59: tests applied_paths sin_manifest + tras_apply — sesión 134553Z (2026-06-22)
- B-60: sincronizar decision.schema.json agregar _meta — sesión 134818Z (2026-06-22)
- B-61: tests de compute_total, required_keys, validate_required en run_session.py — sesión 135301Z (2026-06-22)
- B-62: tests write/read/clear loop_status + request/stop/clear_stop en aotl_state.py — sesión 135621Z (2026-06-22)
- B-63: tests render y append_to_index en new_session.py — sesión 135826Z (2026-06-22)
- B-64: check.py conteo de tests dinamico (run_and_capture + _parse_test_count) — sesión 140049Z (2026-06-22)
- B-65: docs/02_USAGE.md actualizado con conteos reales 85+50=135 — sesión 140245Z (2026-06-22)
- B-66: tests _impl_badge, _phase_pills, _session_rows en dashboard_static — sesión 140404Z (2026-06-22)
- B-67: tests _coerce, _strip_comment, _median (helpers puros) — sesión 140546Z (2026-06-22)
- B-68: tests _parse_test_count en check.py — sesión 140728Z (2026-06-22)
- B-69: tests make_engine MockEngine factory — sesión 140953Z (2026-06-22)
- B-70: MANIFEST.md actualizado scripts/adapters — sesión 141103Z (2026-06-22)
- B-71: tests active_adapter en adapter_info.py — sesión 141224Z (2026-06-22)
- B-72: tests load_adapter y load_profile en autoloop.py — sesión 141346Z (2026-06-22)
- B-73: validate_change_set ya cubierto (4 tests en test_aotl.py lineas 123-176) — auditoria inline sesion 141846Z (2026-06-22)
- B-74: gate_decide ya cubierto (6 tests en test_aotl.py lineas 289-340) — auditoria inline sesion 141846Z (2026-06-22)
- B-75: docs/02_USAGE.md actualizado a 161 tests (109+52) — sesion 141846Z (2026-06-22)
- B-83: test_core: 4 tests validate_session (valida/inexistente/score_rango/strict) — sesion 143205Z (2026-06-22)
- B-84: test_aotl: 4 tests create_session+run_gate con mock de _py — sesion 143630Z (2026-06-22)
- B-85: test_aotl: 3 tests commit_applied (sin rutas, git-add-falla, commit-ok) con mock subprocess — sesion 143920Z (2026-06-22)
- B-76: test_core: 2 tests build_context (claves_obligatorias + valores_pasados) — sesion 142114Z (2026-06-22)
- B-77: docstring test_core.py 111 y 02_USAGE.md 163 tests — sesion 142225Z (2026-06-22)
- B-78: test_core: 2 tests update_index_status (modifica_correcta + id_inexistente) — sesion 142403Z (2026-06-22)
- B-79: sync docstring 113/165 + backlog B-74..B-78 — sesion 142531Z (2026-06-22)
- B-80: test_aotl: 2 tests ClaudeCliEngine._context_block — sesion 142702Z (2026-06-22)
- B-81: test_core: 3 tests load_json (valido/inexistente/malformado) — sesion 142829Z (2026-06-22)
