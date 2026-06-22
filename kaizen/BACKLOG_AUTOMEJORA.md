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

### B-11 [PENDIENTE] Regeneración automática del dashboard al cerrar cada sesión
**Valor:** El prompt del operador dice "regeneralo al cierre de CADA sesión". Actualmente solo se
regenera si el operador llama manualmente a `python kaizen.py dashboard`.
**Detalles:** Agregar llamada a `dashboard_static.py` al final de `run_session.py` (tras cerrar la
sesión). Solo si `dashboard/` existe ya (para no crearlo en tests). La llamada silencia errores
(el dashboard es best-effort; no debe romper el gate).
**Métrica:** Tras `python kaizen.py run <id>`, `dashboard/index.html` tiene fecha de modificación
más reciente que antes del run.
**Rollback:** Eliminar la llamada en `run_session.py`.

### B-12 [PENDIENTE] Test unitario para recent_decisions_summary (autoloop.py)
**Valor:** La funcion recien agregada no tiene tests unitarios.
**Detalles:** Agregar cases en `scripts/test_core.py` para `recent_decisions_summary` con
fixtures de decisions/ simuladas en tempdir.
**Métrica:** `python scripts/test_core.py` da 0 fallas con al menos 2 casos nuevos.
**Rollback:** Eliminar los 2 casos nuevos de test_core.py.

---

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
