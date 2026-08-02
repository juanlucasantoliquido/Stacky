# Plan 294 — El pipeline se crea sin saber YAML: wizard guiado para no técnicos

**Estado:** PROPUESTO **v1 → v2** (crítica adversarial aplicada) · **Fecha v1:** 2026-08-02 · **Fecha v2:** 2026-08-02
**Rama al escribir:** `docs/plan-279`
**Autor v1:** StackyArchitectaUltraEficientCode (perfil normal)
**Juez v2: subagente independiente, misma corrida, contexto limpio**
**Veredicto de la crítica sobre v1: RECHAZADO — 8 bloqueantes.** 162 de 171 anclajes eran correctos.
**El plan NO cayó por anclajes: cayó por (a) tres afirmaciones de ausencia FALSAS y (b) cinco criterios
de aceptación mutuamente insatisfacibles entre fases.**
**Alcance:** P0 completo + inventario automático de pipelines + disparo desde Stacky. P1 restante y P2 en §9.

> **Todo anclaje `archivo:línea` de este documento se verificó abriendo el archivo el 2026-08-02**
> (v1 por su autor; **re-verificado uno por uno por el juez en la v2**).
> Hay una **sesión paralela viva** en este árbol. Donde un número de línea puede correrse, el documento
> da además el **símbolo**. **Si el número no coincide, manda el símbolo.**

---

## 0. CHANGELOG v1 → v2

Una línea por hallazgo resuelto. Los `C#` son los de la crítica adversarial.

### Bloqueantes resueltos (8)

- **C1 (BLOQ, E1) — GAP-4 afirmaba una ausencia FALSA.** El v1 decía: *"`TriggerPipelineSection` no
  tiene pestaña: su único punto de montaje en toda la app es dentro del constructor gráfico. Grep de
  `TriggerPipelineSection` en `frontend/src` no devuelve ningún otro montaje"*. **Falso: hay CUATRO
  montajes** —`PipelineBuilderSection.tsx:746`, `EnvironmentsSection.tsx:615`, `ProductionFlow.tsx:214`,
  `PublicationsSection.tsx:564`. Además el anclaje `:745` estaba desfasado (real `:746`). GAP-4, C3 y
  KPI-3 se reescribieron con el hecho real (el disparo **sí** está reusado en 4 superficies; lo que
  **no** existe es un disparo desde la **fila del inventario**), y **F0 caso 10 congela los 4 montajes**
  para que nadie los rompa "limpiando".
- **C2 (BLOQ, E1) — `STATE_LABELS` y `AVAILABLE_BY_STATE` NO son importables.** §3.1 y §5.6 los daban
  como símbolos exportados de `pipelineCopilotModel.ts` y ordenaban *"se importa desde el modelo del
  wizard"*. **Son `const` PRIVADAS** (`:34` y `:50`); los exports reales son las funciones
  `stateLabel(s)` (`:46`) y `availableActionIds(s)` (`:79`). Corregido en las dos secciones y
  **F0 caso 11 censa los exports reales** antes de que nadie escriba el `import`.
- **C3 (BLOQ, E1) — §3.4 afirmaba "Grep de `TAB_META` en `frontend/src` = 0".** **Falso**:
  `components/shell/shellNav.ts:16` lo define y lo consumen `App.tsx:64,341` y
  `components/shell/AppSidebar.tsx:6,42` —que además dice literal *"`TAB_META` NO se toca: lo congelan
  4 suites"*. Era un **non-sequitur** copiado de otro plan (TAB_META no tiene nada que ver con
  `Stepper`). Eliminado y reemplazado por el censo correcto: **lo que no existe es
  `frontend/src/components/ui/Stepper.tsx`** (verificado con `ls`).
- **C4 (BLOQ, E2) — F11 caso 1 era INSATISFACIBLE.** Exigía que
  `WIZARD_RUNTIMES = ("codex","claude","copilot")` coincidiera *elemento a elemento* con los `id` de
  `COPILOT_RUNTIMES`, cuyos ids REALES son
  **`("claude_code_cli", "codex_cli", "github_copilot")`** (`pipelineCopilotModel.ts:106-110`,
  `CopilotRuntimeId` en `:122`). Un modelo menor "resuelve" esto debilitando el assert a `len == 3`
  ⇒ **falso verde**. El vocabulario de runtime se unificó a los ids reales en §5.4, §5.7, F8, F11 y el
  glosario. **No se relajó ningún criterio: se corrigió el vocabulario.**
- **C5 (BLOQ, E2) — F9 rompe un ratchet VERDE que el plan nunca nombra.**
  `backend/tests/test_devops_action_ratchet.py::test_section_ids_espejan_el_tsx` exige
  `set(ids de DevOpsPage.tsx) == set(DEVOPS_SECTION_IDS)` de
  `backend/services/devops_action_catalog.py:46-54` (hoy **18** ids). Agregar `crear-pipeline` al `.tsx`
  **sin** tocar el catálogo lo pone rojo. **Medido hoy: 13 passed** (verde) y el archivo **está
  registrado en los DOS ratchets** (`run_harness_tests.ps1:891`, `run_harness_tests.sh:997`) ⇒ es
  trampa de **commit**. F9 ahora edita `devops_action_catalog.py`, corre ese archivo y lo verifica.
- **C6 (BLOQ, E2) — el criterio de `test_flag_wiring.py` en F6 era insatisfacible.** F1 registra 3
  flags; F6 fija *"`test_flag_wiring.py` → fallos ≤ línea base"*. Pero en F6 sólo
  `STACKY_PIPELINE_WIZARD_ENABLED` tiene consumidor: `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` recién lo
  tiene en **F7** y `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` **nunca** en backend (el v1 sólo la usaba en
  el `.tsx`). Resuelto **sin relajar el gate**: F1 agrega las **dos** claves nuevas a `_health_payload`
  (`backend/api/devops.py:28`), que es consumo productivo real, y el gate de wiring se corre en **F1 y
  F9**, no en F6.
- **C7 (BLOQ, E2) — la promesa "reusa `pipeline_session`, no se escribe otra máquina" era prosa
  muerta.** Ninguna fase la consume: los 4 endpoints de F6 no la tocan y F8 construye **otra** máquina
  (`WIZARD_STEPS` + `canAdvance` + `advanceWizard`). El DoD no lo verificaba. Resuelto **conservando la
  promesa y volviéndola binaria**: §5.6 declara el mapeo P1..P7 → estado, `pipelineWizardModel.ts`
  **debe** derivar los nombres de `SESSION_STATES` (que **sí** está exportado, `:16`), y
  **F6 caso 11 + F8 caso 13** asertan que el mapeo es total y que **cada salto consecutivo del wizard
  es legal según `TRANSITIONS`**.
- **C8 (BLOQ, E2) — F5 caso 5 contradecía su propia regla de composición.** La regla decía *"por cada
  una de las primeras `_MAX_DESCRIBED` entradas… **el resto viaja sin ficha**"*, pero el caso exigía que
  las otras 15 trajeran `purpose_source == "sin_datos"`. Una entrada que nunca pasa por
  `describe_pipeline` **no tiene esa clave**: el assert es imposible y un modelo menor lo borra.
  Resuelto **acotando la regla, no el criterio**: **TODAS** las entradas pasan por `describe_pipeline`;
  sólo las primeras `_MAX_DESCRIBED` reciben el texto YAML.

### Importantes resueltos (11)

- **C9** — `should_trigger` se atribuía a `backend/api/ci.py`; vive en
  `backend/services/ci_trigger_rules.py:80` (importado en `api/ci.py:26`, usado en `:294` y `:373`).
- **C10** — `devopsCockpitShell.ts` se citaba **sin directorio** 4 veces; el real es
  `Stacky Agents/frontend/src/pages/devopsCockpitShell.ts` (**no** `components/devops/`). Las líneas
  `:20-26`, `:121-151` y `:150` eran correctas.
- **C11** — F5 mandaba `detect_stack(_active_workspace_root())`, pero
  `pipeline_stack_detector.detect_stack(project_root: str)` (`:19`) toma **`str`** y
  `runtime_paths._active_workspace_root()` (`:66`) devuelve **`Path | None`**. Corregido a
  `detect_stack(str(root)) if root else ""`.
- **C12** — F3 caso 5 exigía que `intent_to_spec` produjera un spec válido, pero
  `PipelineSpec.variables` es un **`dict`** (`pipeline_spec.py:88,115`) y `PipelineIntent.variables` es
  una tupla de **NOMBRES**. El puente no estaba especificado. Ahora está: `{nombre: "" ...}`, con caso
  de test propio (F3 caso 10).
- **C13** — §5.5 decía *"`build_inventory` no se toca"* y F10 le agrega el parámetro `describe` y le
  cambia la clave de cache. Reescrito: lo congelado es **el shape de 12 claves y la lógica de
  reconciliación**, no la firma.
- **C14** — `test_plan294_describe.py` tenía **dos** conteos declarados (11 en F2, 14 en F10) y F11
  cerraba con *"el conteo declarado en su fase"*. F11 ahora declara **17** explícito (11 de F2 + 3 de
  F10 + 3 nuevos).
- **C15** — F9 decía *"agregar al payload de `GET /api/devops/health`"* sin nombrar la función. Es
  `backend/api/devops.py`, **`_health_payload`** (`:28`). Nombrada. Y su guardián
  `test_health_key_existe_en_health_payload` (`test_devops_action_ratchet.py:59`) ahora se corre.
- **C16** — F7 edita `trigger_pipeline_route`, que es exactamente lo que espía
  `backend/tests/test_plan260_trigger_gate.py:329-341` (monkeypatchea `ci_mod.should_trigger`).
  Agregado como no-regresión nombrada en F7 y en §7.3.
- **C17** — C8 del v1 acusaba al copiloto de *"desactivar el `onClick` sin explicar"*. El código dice lo
  contrario: `PipelineCopilotSection.tsx:308-311` documenta que el **plan 288** los convirtió a propósito
  en etiquetas, con la frase *"En este paso el copiloto puede proponerte:"* y la ejecución movida a la
  consola. Reescrito para que nadie "arregle" el 288.
- **C18** — F0 caso 6 (`from services.pipeline_inventory import get_pipeline_yaml`) sin decir DÓNDE va
  el import. A nivel de módulo daría **error de colección** (1 error, no "6 passed, 3 failed") y el
  criterio binario sería inalcanzable. Ahora se exige el import **dentro del cuerpo del test**.
- **C19** — F6 caso 10 y F5 caso 7 mandaban *"monkeypatchear el cliente de modelo"* sin nombrar el
  módulo. Reemplazado por una guarda **estructural y determinista** (grep del fuente), que es lo que el
  resto del plan ya usa para "no hace red".

### Menores resueltos (3)

- **C20** — `pipeline_session.py:15-37` → el rango real es `:15-38` (`TERMINAL_STATES` está en `:38`).
- **C21** — `test_plan247_endpoint.py:61-76` → el test real es `:63-78`.
- **C22** — el plan mata una clase de error viva (`inventory_unavailable` / 501 perpetuo del perfilador)
  y no registraba su huella. F2 ahora la registra en
  `Stacky Agents/docs/sistema/error_fingerprints.json`.

### Adiciones del arquitecto (3)

- **[ADICIÓN ARQUITECTO 1]** — F9: el wizard se declara como **acción DevOps de sólo lectura**
  (`devops.pipeline_wizard.open`) en `devops_action_catalog.py`, de modo que un no técnico lo alcance
  escribiendo *"quiero crear una pipeline"* en la consola en castellano y en la paleta. Sin
  `palette-run` (no ejecuta nada), sin flag nueva, sin trabajo del operador.
- **[ADICIÓN ARQUITECTO 2]** — F8: `strictRuntime` y la **prohibición explícita de
  `normalizeCopilotRuntime`** dentro del wizard. Ese normalizador **hoy, en producción**, devuelve
  `'claude_code_cli'` ante un id desconocido (`pipelineCopilotModel.ts:127-130`): es exactamente la
  **degradación silenciosa de la elección** que R4 prohíbe. El wizard no puede rutear por ahí, y un test
  lo verifica.
- **[ADICIÓN ARQUITECTO 3]** — F10: la línea de mayor riesgo del diálogo HITL —*"Esta pipeline NO
  despliega a ningún ambiente"*— dejaba de ser decorado y pasa a **calcularse** con
  `pipeline_profiler.detect_environments` (`:485`), con tres estados honestos
  (`no_despliega` / `despliega_a: [...]` / `no_se_pudo_determinar`) y test propio. Afirmar "no
  despliega" sin saberlo es el peor error posible antes de encolar una corrida real.

### Conteos v1 → v2 (el orquestador los verifica)

| Métrica | v1 | v2 |
|---|---|---|
| Fases (F0..F11) | 12 | **12** (ninguna eliminada, ninguna fusionada) |
| Criterios BINARIOS de fase | 12 | **12** |
| Casos de test enumerados | 125 | **142** (+17; **0 eliminados**) |
| Archivos de test NUEVOS nombrados | 13 | **13** |
| Archivos de test de NO-REGRESIÓN nombrados | 12 | **15** (+`test_devops_action_ratchet.py`, +`test_plan260_trigger_gate.py`, +`test_plan247_profiler_core.py`) |
| Ítems del Definition of Done | 22 | **29** |
| Flags nuevas | 3 | **3** (1 ON, 2 OFF con (B) citada) |

> **AVISO AL IMPLEMENTADOR — LEER ANTES DE ESCRIBIR UNA LÍNEA.**
> Este plan **construye muy poco código nuevo de dominio**. La capacidad central que el operador pidió
> como "importantísima" —**detectar automáticamente las pipelines que ya existen**— **YA ESTÁ
> CONSTRUIDA Y VERDE** (plan 246, `backend/services/pipeline_inventory.py`, 765 líneas). El disparo de
> pipelines **también existe** (plan 72/95, `backend/api/ci.py`) y su flag **ya está encendida**.
> Lo que falta no es capacidad: es **secuencia, lenguaje llano y cableado**.
> **Si en cualquier fase te encontrás escribiendo un barrido de repo, un cliente HTTP de ADO/GitLab, un
> renderizador de YAML o una máquina de estados de sesión: PARÁ. Ya existe. Volvé a §3.**

> **LAS 5 TRAMPAS DE ESTE PLAN, EN ORDEN DE COSTO (agregadas en la v2 tras el rechazo del v1).**
> Leelas ahora; cada una hundió una parte del v1.
> 1. **La sección nueva tiene DOS registros, no uno.** `DevOpsPage.tsx` **y**
>    `backend/services/devops_action_catalog.py`. Falta uno ⇒ `test_devops_action_ratchet.py` (hoy
>    **13 passed**, registrado en los DOS ratchets) tumba **el commit**, no la fase. → §3.4, F9.
> 2. **Los runtimes se llaman `claude_code_cli`, `codex_cli`, `github_copilot`.** `"codex"`, `"claude"`
>    y `"copilot"` **no existen**. → §5.7, F11 caso 8.
> 3. **`STATE_LABELS` y `AVAILABLE_BY_STATE` NO son exports.** Usá `stateLabel()` y
>    `availableActionIds()`. → §3.1, F0 caso 11.
> 4. **Una flag registrada sin literal en código productivo deja `test_flag_wiring.py` rojo para
>    siempre.** Por eso las 3 entran a `_health_payload` en **F1**. → §7.2, F1 casos 8-9.
> 5. **`TriggerPipelineSection` está montado en 4 lugares, no en uno.** El v1 afirmaba lo contrario.
>    **No lo "consolides".** → GAP-4, F0 caso 10.

---

## 1. Objetivo y KPI

### 1.1 Objetivo

Convertir la creación de pipelines en el cockpit de DevOps de una **superficie técnica de 28 campos
simultáneos** en un **wizard guiado de 7 pasos** que un usuario sin conocimientos de DevOps pueda
completar sin escribir YAML, apoyado en lo que Stacky ya sabe del proyecto —incluido el **inventario
automático de las pipelines que ya existen**— y que termine, con confirmación explícita, en un archivo
creado y, si el operador lo decide, en una **corrida real disparada desde Stacky** con seguimiento.

Todo lo actual **se conserva íntegro** detrás de un **"Modo avanzado"**. No se borra ni una capacidad.

### 1.2 KPI medibles (los cuatro se miden con comandos, no con opinión)

| # | KPI | Medición hoy (2026-08-02, medida) | Meta |
|---|---|---|---|
| **KPI-1** | Campos de formulario visibles a la vez para crear una pipeline | **28** (10 propios de `PipelineBuilderSection.tsx` + 18 de `BlockProperties.tsx:43-247`) | **≤ 4 por paso**, verificado por el gate de F9 |
| **KPI-2** | Decisiones técnicas obligatorias antes de ver un YAML | **≥ 6** (stack, preset, bloques, propiedades por bloque, variables, rama) | **0** — el wizard propone TODO y el usuario solo confirma o corrige |
| **KPI-3** | Clics desde "veo esta pipeline en el inventario" hasta la confirmación de disparo | **hoy: INALCANZABLE desde el inventario.** `TriggerPipelineSection` está reusado en **4** superficies (`PipelineBuilderSection.tsx:746`, `EnvironmentsSection.tsx:615`, `ProductionFlow.tsx:214`, `PublicationsSection.tsx:564`) y **en ninguna de las 4** hay una fila de inventario: hay que salir del inventario, entrar a otra sección y volver a elegir la pipeline a mano | **1 clic** desde la fila del inventario |
| **KPI-4** | Llamadas a modelo en reposo que agrega este plan | 0 | **0** — ninguna fase enciende loop, daemon, barrido ni prefetch |

**KPI-5 (seguridad, binario):** cero valores de secreto en preview, diff, prompt, log o payload. Se
verifica con el test de F6 y reusa el gate que ya existe (`STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED`,
`backend/api/pipeline_generator.py`, llamada a `evaluar_gate_secretos`).

---

## 2. Por qué ahora / gap que cierra

Tres planes recientes tocaron esta zona y **ninguno atacó la puerta de entrada**:

- **Plan 275** (`docs/275_PLAN_EL_COCKPIT_DEVOPS_DEJA_DE_AMONTONAR_Y_DEJA_DE_MENTIR.md`) partió el grupo
  `construir` en `construir` + `gobernar` porque tenía "7 secciones heterogéneas". **Repartió el
  amontonamiento en dos cajones, pero el amontonamiento sigue adentro de la pestaña `pipelines`.**
  Este plan no revierte nada del 275: agrega **una** sección al grupo `construir` y deja los 5 grupos de
  `DEVOPS_SECTION_GROUPS` intactos.
  > **RUTA EXACTA (C10) — el archivo NO está en `components/devops/`.** Es
  > **`Stacky Agents/frontend/src/pages/devopsCockpitShell.ts`**, líneas `20-26`. Cada vez que este
  > documento diga `devopsCockpitShell.ts`, se refiere a **esa** ruta.
- **Plan 279** (`docs/279_PLAN_EL_COPILOTO_DE_PIPELINES_UN_SOLO_HILO_CONVERSACIONAL.md`, IMPLEMENTADO
  F0..F9) construyó la máquina de estados de 8 pasos (`backend/services/pipeline_session.py:15-37`) y el
  panel del copiloto. **Pero el copiloto no avanza el estado desde el frontend**: `PipelineCopilot.advance`
  (`frontend/src/api/endpoints.ts:5117`) y `PipelineCopilot.question` (`:5123`) tienen **0 llamadores**
  —grep en `frontend/src` devuelve la definición y nada más; los únicos métodos de ese namespace que sí
  se llaman son `.session` y `.undoHint` (`PipelineCopilotSection.tsx:73` y `:80`)—.
  Este plan **reusa esa máquina de estados como columna vertebral del wizard** y le pone, por fin, un
  consumidor **verificado por test** (§5.6, F6 caso 11, F8 caso 13).
  > **CORRECCIÓN v2 (C17) — lo que el v1 llamaba defecto es una decisión del plan 288.** Que las
  > acciones del paso sean `<span>` sin `onClick` (`PipelineCopilotSection.tsx:315-326`) **no es un
  > descuido**: `:308-311` lo documenta textualmente —*"antes esto eran botones SIN onClick: prometían
  > una acción que no ocurría. Ahora son etiquetas… la ejecución vive en la consola de abajo, que es el
  > ÚNICO mecanismo de confirmación del panel (D1)"*— y arriba hay una frase explicativa visible
  > (*"En este paso el copiloto puede proponerte:"*). **Prohibido "arreglarlo" en este plan:** sería
  > revertir el 288 y reintroducir el botón que miente.
- **Plan 288** (`docs/288_PLAN_LA_VISTA_DEL_TICKET_ADELGAZA_Y_EL_SELECTOR_DE_MODELOS_DEJA_DE_MENTIR.md`)
  tocó `api/pipeline_generator.py` (`_target_efectivo`: el proyecto manda sobre el cuerpo). Este plan
  **respeta esa decisión y la reusa**: el wizard nunca manda `target` a mano, deja que el proyecto lo
  resuelva.

**El gap real, en una frase:** hay **8 pestañas distintas** que hablan de pipelines
(`pipelines`, `variables`, `inventario-pipelines`, `pipeline-audit`, `editar-pipeline`, `matriz-entornos`,
`paquete-entrega`, `copiloto-pipelines` — `DevOpsPage.tsx:151-348`), repartidas entre dos grupos, **y
ninguna se habla con otra**. El usuario no técnico no tiene por dónde empezar.

---

## 3. Diagnóstico del flujo actual (auditoría con `archivo:línea`)

### 3.1 CAPACIDADES QUE YA EXISTEN Y SE REUSAN (la sección más importante del plan)

> Regla dura de este plan: **cada ítem de esta tabla es código que NO se reescribe.** Si una fase parece
> necesitar algo de acá, lo **importa**.

| Capacidad | Dónde vive | Estado | Cómo la usa el wizard |
|---|---|---|---|
| **Inventario multiproveedor de pipelines** | `backend/services/pipeline_inventory.py` (765 líneas), función `build_inventory` | **COMPLETO.** Barre el repo (`scan_repo_pipelines`), lista definiciones del proveedor, y **reconcilia** (`reconcile`) con 4 categorías | **Es la fuente del Paso 1 y del Paso 2.** Se consume tal cual |
| Las 4 categorías de reconciliación | `pipeline_inventory.py`, constantes `CATEGORY_REGISTERED_WITH_FILE`, `CATEGORY_REGISTERED_NO_FILE`, `CATEGORY_FILE_NOT_REGISTERED`, `CATEGORY_UNKNOWN_FILE_STATE` | **COMPLETO** — cubre exactamente los tres estados que pidió el operador, **más un cuarto** ("el barrido no es confiable, no puedo afirmar que falte") | Se muestran en castellano en la UI del inventario |
| Degradación honesta por fuente | `pipeline_inventory.py`, `source_ok` / `source_unavailable`; el payload trae **siempre 2 fuentes** | **COMPLETO** | El aviso "no pude consultar el proveedor" sale de acá, ya está resuelto |
| Endpoint del inventario | `backend/api/pipeline_inventory.py`, `GET /api/pipeline-inventory/list` (guard per-request, `abort(404)`) | **COMPLETO, READ-ONLY** (el módulo declara que no define ningún POST/PUT/PATCH/DELETE, a propósito) | Se reusa; se le empieza a pasar el proyecto (hoy va `null`) |
| Extracción del disparador desde el YAML | `pipeline_inventory.py`, `extract_trigger` (ADO y GitLab, con las limitaciones de GitLab **declaradas** en el propio código) | **COMPLETO** | Alimenta "cuándo se ejecuta" del Paso 6 |
| **Perfilador de pipelines** | `backend/services/pipeline_profiler.py` (plan 247): `detect_pipeline_stacks`, `detect_agents`, `detect_triggers`, `detect_phases`, `detect_artifacts`, `detect_environments` | **COMPLETO** | Alimenta "qué hace cada etapa" del Paso 6 |
| **Frase en castellano, determinista, sin modelo** | `pipeline_profiler.py`, `build_purpose_template` + `PURPOSE_MAX_CHARS = 200` + `PURPOSE_SOURCE_TEMPLATE = "plantilla"` | **COMPLETO** | **Es el "qué hace en lenguaje simple" que pidió el operador.** Cero tokens |
| **Disparo de pipeline (HITL)** | `backend/api/ci.py`, `POST /api/ci/<project>/trigger` (`trigger_pipeline_route`, `:246`); rechaza con 400 sin `confirm=True`; idempotencia de 60 s vía `should_trigger`, que **NO vive en `api/ci.py`**: está en `backend/services/ci_trigger_rules.py:80`, se importa en `api/ci.py:26` y se llama en `:294` (trigger) y `:373` (preview) — **C9** | **COMPLETO** | El wizard y el inventario lo llaman; **no se reimplementa** |
| Preview del disparo (read-only) | `backend/api/ci.py`, `GET /api/ci/<project>/trigger-preview` (`trigger_preview_route`) | **COMPLETO** | Es la pantalla de confirmación del disparo |
| Monitoreo de la corrida | `backend/api/ci.py`, `GET /api/ci/<project>/pipeline/<pipeline_id>` (`monitor_pipeline_route`), con cap real de polls (`_MAX_ACTIVE_POLLS_PER_PIPELINE = 5`) | **COMPLETO** | Seguimiento post-disparo |
| Bitácora de corridas | `backend/api/ci.py`, `GET /api/ci/runs` (`list_ci_runs_route`) + `backend/services/ci_run_ledger.py` | **COMPLETO** | Historial del Paso 7 |
| Trigger por proveedor | `backend/services/ado_ci_provider.py`, `AdoCIProvider.trigger_pipeline`; `backend/services/gitlab_ci_provider.py`, `GitLabCIProvider.trigger_pipeline` | **COMPLETO para la rama**; **SIN variables por corrida** (ver §3.3, GAP-5) | F7 agrega variables **sin cambiar la firma existente** |
| Listado de definiciones del proveedor | `ado_ci_provider.py`, `AdoCIProvider.list_pipeline_definitions`; `gitlab_ci_provider.py`, `GitLabCIProvider.list_pipeline_definitions`; ADO además en `backend/services/ado_pipeline_definitions.py`, `list_definitions` (tope de hidratación y contador `meta["calls"]` real) | **COMPLETO en los dos proveedores** | Se consume vía `build_inventory` |
| Render `PipelineSpec` → YAML | `backend/services/pipeline_renderers.py` (`to_ado_yaml`, `to_gitlab_yaml`) vía `backend/api/pipeline_generator.py`, `POST /api/pipeline-generator/preview` | **COMPLETO** | Es el motor del Paso 5. **No se escribe otro renderizador** |
| Escritura al repo real | `backend/services/repo_writer.py`, `RepoWriter.commit_file` + `get_repo_writer`; implementaciones en `backend/services/ado_provider.py:146` (`commit_file`) y `backend/services/gitlab_provider.py:853` (`commit_file`) | **COMPLETO EN LOS DOS PROVEEDORES** | Es el Paso 7. **La paridad ADO/GitLab de escritura YA está resuelta** |
| Gate de secretos antes de escribir | `backend/api/pipeline_generator.py`, llamada a `evaluar_gate_secretos` (`backend/services/ci_env_gate.py`) | **COMPLETO** | Se hereda gratis al reusar el endpoint |
| Máquina de estados de 8 pasos | `backend/services/pipeline_session.py`: `PIPELINE_SESSION_STATES` (`:15`), `TRANSITIONS` (`:27`), `TERMINAL_STATES` (`:38`), `PIPELINE_FILENAME` (`:45`), `can_transition` (`:67`), `advance` (`:76`), `next_question` (`:158`), `undo_hint` (`:171`). **Rango real `:15-38`, no `:15-37` (C20)** | **COMPLETO** (plan 279) | **Es la máquina de estados del wizard.** No se escribe otra: §5.6 fija el mapeo y **F6 caso 11 + F8 caso 13 lo asertan** |
| Espejo de la máquina en el frontend | `frontend/src/components/devops/pipelineCopilotModel.ts`. **EXPORTADOS (usables): `SESSION_STATES` (`:16`), `COPILOT_ACTION_IDS` (`:22`), `COPILOT_WRITE_ACTION_ID` (`:32`), `stateLabel(s)` (`:46`), `availableActionIds(s)` (`:79`), `needsOperatorConfirmation` (`:84`), `mustShowUndoHint` (`:95`), `COPILOT_RUNTIMES` (`:106`), `normalizeCopilotRuntime` (`:127`)** | **COMPLETO**, con test (`devops/__tests__/pipelineCopilotModel.test.ts`) | Se importa **sólo lo exportado**. Ver la trampa de abajo |
| Detección de stack | `backend/services/pipeline_stack_detector.py`, `detect_stack(root) -> "python" \| "node" \| "dotnet" \| None`; endpoint `GET /api/devops/detect-stack` (`backend/api/devops.py`, `detect_stack_route`) | **EXISTE PERO ES DELGADO** (ver GAP-7) | F5 lo **compone**, no lo reemplaza |
| Lint determinista | `POST /api/devops/pipeline-lint/validate` y `/explain`; clientes ya tipados en `frontend/src/api/endpoints.ts` (`DevOps.pipelineLintValidate`, `DevOps.pipelineLintExplain`) | **COMPLETO** | Paso 6 |
| Preflight | `POST /api/devops/preflight/check`; cliente `DevOps.preflightCheck` | **COMPLETO** | Paso 6 |
| Variables / secretos | `DevOpsVariables.list` / `.create` / `.remove` (`endpoints.ts`, namespace `DevOpsVariables`) | **COMPLETO** | Paso 3 y Paso 6 (por NOMBRE, nunca por valor) |
| Selector de runtime | `frontend/src/components/AgentRuntimeSelector` (usado en `PipelineCopilotSection.tsx:208`) + `COPILOT_RUNTIMES` (3 entradas) | **COMPLETO** | Paso 4 |
| Primitiva de pestañas | `frontend/src/components/ui/Tabs.tsx`, `export default function Tabs` (`:28`) | **COMPLETO** | Se usa para "Guiado / Modo avanzado" |
| Catálogo de acciones DevOps | `backend/services/devops_action_catalog.py`: `DEVOPS_ACTION_CATALOG` y `DEVOPS_SECTION_IDS` (`:46-54`, **18** ids hoy) | **COMPLETO** | **Hay que registrarlo, no reescribirlo.** Toda sección nueva del cockpit **debe** entrar acá o el ratchet se pone rojo (§3.4, F9) |

> **TRAMPA DE IMPORT (C2) — dos de los símbolos que el v1 mandaba importar NO EXISTEN como export.**
> En `pipelineCopilotModel.ts`, **`STATE_LABELS` (`:34`) y `AVAILABLE_BY_STATE` (`:50`) son `const`
> PRIVADAS del módulo**, sin `export`. Escribir
> `import { STATE_LABELS, AVAILABLE_BY_STATE } from './pipelineCopilotModel'` **rompe `tsc`**.
> Lo que hay que usar son las funciones equivalentes que **sí** están exportadas:
> **`stateLabel(s)`** en lugar de `STATE_LABELS[s]`, y **`availableActionIds(s)`** en lugar de
> `AVAILABLE_BY_STATE[s]`. **Prohibido exportarlas para "arreglarlo"**: cambiar la superficie pública de
> un módulo del plan 279 es alcance ajeno. **F0 caso 11 censa esto antes de que nadie escriba el import.**

### 3.2 Flags que ya existen en esta zona (default REAL leído del `os.getenv`, no del comentario)

| Flag | Default REAL | Evidencia | Qué gatea |
|---|---|---|---|
| `STACKY_PIPELINE_INVENTORY_ENABLED` | **ON** | `backend/config.py:1648-1650`, `os.getenv(..., "true").strip().lower() == "true"`; `FlagSpec` en `backend/services/harness_flags.py:6169` con `default=True`; curada en `backend/tests/test_harness_flags.py:603` | Inventario |
| `STACKY_PIPELINE_TRIGGER_ENABLED` | **ON** | `backend/config.py:1731-1733`, `os.getenv(..., "true").lower() in ("1","true","yes")`; `FlagSpec` en `harness_flags.py:3783` con `default=True` | Disparo + monitoreo |
| `STACKY_PIPELINE_GENERATOR_ENABLED` | **ON** | `backend/config.py:1738-1740`; `FlagSpec` `harness_flags.py:3799` con `default=True` | Preview + commit del generador |
| `STACKY_PIPELINE_PROFILER_ENABLED` | **ON** | `backend/config.py:1744-1746`, `os.getenv(..., "true")`; `FlagSpec` `harness_flags.py:3816` | Perfilador |
| `STACKY_CI_RUN_LEDGER_ENABLED` | **ON** | `backend/config.py:2044-2046` | Bitácora de corridas |
| `STACKY_DEVOPS_STACK_DETECT_ENABLED` | **ON** | `backend/config.py:1909-1911` | `detect-stack` |
| `STACKY_PIPELINE_COPILOT_ENABLED` | **ON** | `backend/config.py:2568-2570` | Copiloto (lee/planea) |
| `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED` | **OFF** | `backend/config.py:2571-2573`, `os.getenv(..., "false")`; su `FlagSpec` (`harness_flags.py:6815`) **NO declara `default=`, a propósito** | El copiloto escribe en el repo real |
| `STACKY_PIPELINE_NL_EDIT_ENABLED` | **ON** | `backend/config.py:1798-1800` | Edición quirúrgica (analiza) |
| `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` | **OFF** | `backend/config.py` (bloque plan 250) | Commit de la edición quirúrgica |

> **GOTCHA CONFIRMADO — un comentario del repo miente sobre su propio default.**
> El docstring de módulo de `backend/api/ci.py` (línea 11) dice literalmente
> *"Flag STACKY_PIPELINE_TRIGGER_ENABLED: default OFF"*. **Es FALSO desde 2026-07-05.**
> El default efectivo vive en `backend/config.py:1731-1733` y es **`"true"`**, y el `FlagSpec`
> (`harness_flags.py:3783`) declara `default=True` con la nota *"activado 2026-07-05, decisión explícita
> del operador"*. **F1 corrige ese comentario** (es una línea, cero riesgo) y el gate de F0 lo verifica.

### 3.3 Los diez defectos (GAP-1..GAP-10), con evidencia

| # | Defecto | Evidencia (`archivo:línea`) |
|---|---|---|
| **GAP-1** | **El inventario ignora el proyecto activo.** Pide el inventario con `project = null` fijo y descarta el contexto | `frontend/src/components/devops/PipelineInventorySection.tsx:80` (`void ctx;`) y `:85` (`PipelineInventory.list(null, false)`) |
| **GAP-2** | **El inventario no dice qué hace cada pipeline.** Muestra 7 columnas técnicas (Estado / Nombre / Proveedor / Ruta del YAML / Rama / Última corrida / Trigger); ninguna en lenguaje llano, aunque el perfilador ya sabe generarla | `PipelineInventorySection.tsx:163-181` vs. `pipeline_profiler.py`, `build_purpose_template` |
| **GAP-3** | **Desde el inventario no se puede disparar nada.** Hay columna "Trigger", pero es informativa | `PipelineInventorySection.tsx:172` |
| **GAP-4** *(reescrito en v2 — C1)* | **El disparo no tiene pestaña propia y NUNCA cuelga de una lista de pipelines.** `TriggerPipelineSection` está **reusado en 4 superficies** (eso es sano y no se toca), pero **en las 4 el usuario ya tiene que saber qué pipeline quiere y en qué sección vive**: ninguna nace de una fila del inventario. Además, en el constructor cuelga **debajo** del preview de YAML, del lint, del preflight y del botón de commit | **Los 4 montajes reales, medidos con grep el 2026-08-02:** `PipelineBuilderSection.tsx:746` (import `:53`), `EnvironmentsSection.tsx:615` (import `:46`), `ProductionFlow.tsx:214` (import `:16`), `PublicationsSection.tsx:564` (import `:43`). **NINGUNO está en `PipelineInventorySection.tsx`** |
| **GAP-5** | **No se puede disparar con variables de esa corrida.** El puerto es `trigger_pipeline(item_ref, ref)`; el cuerpo de ADO manda solo `resources.repositories.self.refName` | `backend/services/ci_provider.py`, `Protocol CIProvider`, método `trigger_pipeline`; `backend/services/ado_ci_provider.py`, cuerpo del POST dentro de `trigger_pipeline`; `backend/services/gitlab_ci_provider.py`, `trigger_pipeline` delega con **solo** `ref` |
| **GAP-6** | **BUG VIVO: el perfilador no puede perfilar por id de pipeline.** Importa `get_pipeline_yaml` de `services.pipeline_inventory` — **esa función no existe** (grep de `def get_pipeline_yaml` en `backend/` = 0 resultados). El camino `pipeline_id` devuelve **siempre 501**. El test que lo cubre **fuerza el `ImportError` con monkeypatch**, así que congela el 501 como comportamiento esperado y el bug nunca se ve | `backend/api/pipeline_profiler.py:32` y `:39`; test `backend/tests/test_plan247_endpoint.py:61-76` |
| **GAP-7** | **La detección de stack es de una sola palabra.** Devuelve `"python" \| "node" \| "dotnet" \| None`. No hay framework, ni gestor de paquetes, ni comando de build, ni comando de test — todo lo que el Paso 1 del brief exige | `backend/services/pipeline_stack_detector.py`, `_MANIFEST_SIGNALS` y `detect_stack` |
| **GAP-8** | **Sobrecarga cognitiva medida: 28 campos y ~22 botones a la vez, sin secuencia.** 10 controles propios (3 `input`, 6 `select`, 1 `textarea`) + 18 en `BlockProperties`, **30 `useState`**, 0 pestañas internas, 8 endpoints directos y ≥10 indirectos en una sola pantalla | `frontend/src/components/devops/PipelineBuilderSection.tsx` (845 líneas; `useState` desde `:71` hasta `:324`); `frontend/src/components/devops/BlockProperties.tsx:43-247` |
| **GAP-9** | **Constructor y copiloto duplican cinco capacidades sobre los MISMOS endpoints**, incluida la escritura: los dos terminan en `POST /api/pipeline-generator/commit` | `frontend/src/components/devops/CommitPipelineModal.tsx:50` y `frontend/src/services/devopsActionBindings.ts` (binding `devops.pipeline_new.commit`); el endpoint es `endpoints.ts`, namespace `PipelineGenerator`, campo `commit` |
| **GAP-10** | **La consola de acciones del copiloto pide rutas sin el prefijo `/api` y falla en silencio.** El backend solo expone `/api/*` | `frontend/src/components/devops/DevOpsActionConsole.tsx:117` (`'/devops/actions/catalog'`), `:130`, `:153`; el blueprint real es `backend/api/devops_actions.py` con `url_prefix="/devops/actions"` registrado dentro de `api_bp` (`url_prefix="/api"`) |

### 3.4 Restricciones estructurales del entorno (no negociables)

- **Backend:** el venv es `Stacky Agents/backend/.venv/Scripts/python.exe` (**Python 3.13.5, verificado
  ejecutando `--version`**). Se corre **por archivo**. **Prohibido** usar `-k` o `pytest tests` entero
  como criterio de aceptación.
- **Frontend:** **RTL y jsdom NO están instalados** (`frontend/package.json`, `devDependencies`: solo
  `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`, `typescript`, `vite`, `vitest`; no existe
  `frontend/node_modules/@testing-library`). Hay **20 archivos `.test.tsx` que importan
  `@testing-library/react` y por lo tanto no corren**. ⇒ **toda lógica testeable de UI de este plan vive
  en `.ts` puro**; los `.tsx` se verifican con `npx tsc --noEmit` y con gates estructurales por grep.
- **Ratchets:** todo test backend nuevo se registra en **los DOS**,
  `backend/scripts/run_harness_tests.ps1` (formato exacto `  "tests/archivo.py",`) y
  `backend/scripts/run_harness_tests.sh` (formato exacto `  tests/archivo.py`).
  **Conteo medido hoy: 772 en `.ps1` y 836 en `.sh` ⇒ diferencia = 64**, y
  `backend/tests/test_plan259_ratchet_script_parity.py:46` fija `_PS1_LAG_MAX = 64`.
  **Estamos EXACTAMENTE en el límite: hay que registrar la MISMA cantidad de archivos en los dos, o el
  gate de paridad se pone rojo.**
- **No hay primitiva `Stepper`.** Verificado con `ls` de `frontend/src/components/ui/`: hay 18
  primitivas (`Tabs.tsx`, `Dialog.tsx`, `Input.tsx`, `Select.tsx`, `Textarea.tsx`, `Checkbox.tsx`,
  `Field.tsx`, `Card.tsx`, …) y **no existe `Stepper.tsx`**. El único con lógica pura reaprovechable
  como **molde** es `frontend/src/components/MigratorWizard.logic.ts` (`nextStep` `:37`, `stepIndex`
  `:46`, `stepLabel` `:57`), pero su tipo de paso es un union literal cerrado del migrador: **se copia
  el patrón, no el archivo**.
  > **CORRECCIÓN v2 (C3) — el v1 decía aquí "Grep de `TAB_META` en `frontend/src` = 0". ES FALSO.**
  > `TAB_META` se define en `frontend/src/components/shell/shellNav.ts:16` y lo consumen `App.tsx:64` y
  > `:341`, y `components/shell/AppSidebar.tsx:6` y `:42` —cuyo comentario `:9` dice literal
  > *"`TAB_META` NO se toca: lo congelan 4 suites y lo consume App.tsx"*. Además **no tiene ninguna
  > relación con `Stepper`**: era un párrafo copiado de otro plan. **`TAB_META` está FUERA DE SCOPE de
  > este plan y no se toca:** la sección nueva vive en `DEVOPS_SECTIONS`, que es otro registro.

- **Una sección nueva del cockpit tiene DOS registros, no uno (C5).** Además de `DEVOPS_SECTIONS` en
  `frontend/src/pages/DevOpsPage.tsx:151`, el id **debe** estar en `DEVOPS_SECTION_IDS` de
  `Stacky Agents/backend/services/devops_action_catalog.py:46-54`. El guardián es
  `backend/tests/test_devops_action_ratchet.py::test_section_ids_espejan_el_tsx` (`:76-86`), que compara
  los dos conjuntos con `==` (no con `⊆`) usando la regex `^\s*id: '([a-z0-9-]+)',` sobre el `.tsx`.
  **Medido el 2026-08-02: ese archivo da `13 passed` (VERDE) y está registrado en los DOS ratchets**
  (`run_harness_tests.ps1:891`, `run_harness_tests.sh:997`) ⇒ **es trampa de COMMIT**: agregar la
  sección al `.tsx` sin tocar el catálogo tumba el commit, no la edición.
  El mismo archivo trae `test_health_key_existe_en_health_payload` (`:59-65`), que exige que todo
  `health_key` del catálogo exista en `api/devops.py::_health_payload` (`:28`).
- **Mono-operador sin auth real.** En este producto **403 = flag apagada, NO permiso**. El guard estándar
  de la casa es `abort(404)` per-request leyendo **la instancia** `_config.config` (nunca el módulo: el
  módulo devuelve el default y mata el branch OFF, con lo cual el test de flag-off pasaría en falso).

---

## 4. Crítica priorizada

| # | Problema | Evidencia | Impacto en el usuario | Sev. | Causa raíz | Solución de este plan |
|---|---|---|---|---|---|---|
| **C1** | Sobrecarga cognitiva: 28 campos y ~22 botones simultáneos, sin orden | `PipelineBuilderSection.tsx` (845 líneas, 30 `useState`), `BlockProperties.tsx:43-247` | El no técnico no sabe por dónde empezar; abandona | **P0** | La pantalla expone el **modelo de datos** (`PipelineSpec` con bloques y propiedades) en vez de la **tarea** | Wizard de 7 pasos, **una decisión principal por pantalla**; el `PipelineSpec` se arma solo (F3, F4, F9) |
| **C2** | Fragmentación: 8 pestañas hablan de pipelines y ninguna se habla con otra | `DevOpsPage.tsx:151-348` (18 secciones; 8 sobre pipelines, repartidas en `construir` y `gobernar`) | Para una tarea hay que recorrer 3-4 pestañas y recordar el estado a mano | **P0** | Cada plan agregó su pestaña; nadie agregó el hilo | **Una** sección nueva (`crear-pipeline`) que orquesta las existentes; las 18 quedan como están (F9) |
| **C3** *(reescrito v2 — C1)* | El disparo no es alcanzable **desde donde el usuario ve la pipeline** | Los 4 montajes de `TriggerPipelineSection` (`PipelineBuilderSection.tsx:746`, `EnvironmentsSection.tsx:615`, `ProductionFlow.tsx:214`, `PublicationsSection.tsx:564`) vs. `PipelineInventorySection.tsx:172` (columna "Trigger" **informativa**) | Ve la pipeline en el inventario y no puede ejecutarla; tiene que salir, elegir otra sección y volver a identificarla a mano | **P0** | El componente **sí** se reusa bien; lo que falta es el punto de entrada desde una **lista** de pipelines | Botón "Ejecutar" en la fila del inventario → pantalla de confirmación (F10). **No se toca ninguno de los 4 montajes existentes** (F0 caso 10 los congela) |
| **C4** | El inventario ignora el proyecto activo | `PipelineInventorySection.tsx:80,85` | En multi-proyecto ve el inventario equivocado y no se entera | **P0** | `void ctx;` y `null` literal | Se pasa el proyecto del contexto y se lo agrega a la `queryKey` (F10) |
| **C5** | El inventario es técnico: 7 columnas, ninguna en castellano llano | `PipelineInventorySection.tsx:163-181` | "azure-pipelines.yml / ci / main" no le dice nada a quien no sabe DevOps | **P0** | El perfilador, que ya genera la frase, nunca se conectó al inventario | `describe_pipeline` casa inventario + perfilador (F2) |
| **C6** | Bug vivo: perfilar por id de pipeline devuelve 501 siempre | `api/pipeline_profiler.py:32,39`; `def get_pipeline_yaml` no existe en `backend/` | La ficha "qué hace" no se puede pedir por pipeline; hay que mandar el YAML entero a mano | **P0** | Un plan (247) programó contra una función que el plan hermano (246) nunca expuso | F2 crea `get_pipeline_yaml` en el inventario |
| **C7** | Duplicación: constructor y copiloto escriben por la misma ruta con dos HITL distintos | `CommitPipelineModal.tsx:50` y el binding `devops.pipeline_new.commit` de `devopsActionBindings.ts`, ambos a `POST /api/pipeline-generator/commit` | Dos pantallas de confirmación distintas para el mismo acto; el usuario no sabe cuál es la buena | **P1** | Dos planes construyeron su propio HITL sobre el mismo endpoint | El wizard **no crea un tercero**: reusa el endpoint y expone **una sola** pantalla de confirmación (F6 caso 8, F9) |
| **C8** *(reescrito v2 — C17)* | El riesgo de **repetir** el patrón "parece botón y no hace nada" en el wizard | En el copiloto **ya fue resuelto por el plan 288**: `PipelineCopilotSection.tsx:308-311` documenta la conversión deliberada a etiquetas + frase explicativa; el `<span>` sin `onClick` de `:315-326` **es esa decisión, no un bug**. Avisos de flags faltantes en `:249-265` | Si el wizard reintroduce controles inertes, el no técnico se traba | **P1** | Riesgo de diseño del wizard nuevo, **no** deuda del copiloto | Regla dura §6-R6 + gates de F9 caso 7 y F10 casos 2-3: **nada deshabilitado sin motivo visible y sin salida**. **El panel del copiloto NO se toca en este plan** |
| **C9** | No hay adaptación al tipo de pipeline: el mismo formulario para todo | `PipelineBuilderSection.tsx` (no hay ninguna rama por objetivo; `stackFilter:324` solo filtra presets) | Le piden datos de despliegue a quien solo quiere correr tests | **P1** | No existe un esquema de preguntas; existe un formulario | Esquema declarativo de preguntas con dependencias (F4) |
| **C10** | La confirmación final no es comprensible y mezcla 4 actos en botones sueltos | Commit (`CommitPipelineModal.tsx`), trigger (`TriggerPipelineSection.tsx:362-375`), guardar borrador (`PipelineBuilderSection.tsx:482-495`) y crear definición (`DevOpsProduction.ensureAdoDefinition`) viven en 4 lugares | Confirma sin saber qué se va a escribir, dónde, ni cómo revertirlo | **P0** | Nunca hubo una pantalla de cierre | Paso 7 con **los 4 actos separados y nombrados**, uno recomendado (F9) |
| **C11** | La consola de acciones falla en silencio por falta de `/api` | `DevOpsActionConsole.tsx:117,130,153`; también `frontend/src/components/CommandPalette.tsx:96` | La única superficie ejecutable del copiloto queda muerta sin ningún error visible | **P1** | Rutas literales sin prefijo contra un backend que solo sirve `/api/*` | **Fuera de scope** (§9): es un defecto del 267/279, no del wizard. Se documenta para que el plan que lo tome no lo redescubra |
| **C12** | Un comentario del repo miente sobre el default de una flag | `backend/api/ci.py:11` dice "default OFF"; el efectivo es ON (`config.py:1731-1733`) | Un implementador futuro asume que el disparo está apagado y construye un camino de activación que no hace falta | **P2** | El comentario no se actualizó cuando el operador encendió la flag el 2026-07-05 | F1 lo corrige (una línea); F0 caso 8 lo verifica |

---

## 5. Diseño objetivo del wizard

### 5.1 Arquitectura en una figura

```
                       +----------------------------------------------+
   Pestaña NUEVA  ---> |  crear-pipeline   (grupo `construir`)        |
   `crear-pipeline`    |  +------------+-------------------------+    |
                       |  |  Guiado    |   Modo avanzado         |    |
                       |  | (default)  |  (link a las 8 actuales)|    |
                       |  +-----+------+-------------------------+    |
                       +--------+-------------------------------------+
                                |  Stepper (primitiva NUEVA, en ui/)
                 +--------------+---------------------------------------+
                 | P1 entender · P2 objetivo · P3 preguntas · P4 runtime |
                 | P5 borrador · P6 revision · P7 confirmacion           |
                 +--------------+---------------------------------------+
                                |  pipelineWizardModel.ts  (.ts PURO, testeable)
                                v
        +---------------------------------------------------------------+
        |  api/pipeline_wizard.py   (NUEVO, delgado - solo orquesta)     |
        +---+------------+--------------+---------------+---------------+
            |            |              |               |
      +-----v-----+ +----v--------+ +---v----------+ +--v----------------+
      | probe(F5) | | schema (F4) | | intent (F3)  | | describe (F2)     |
      +-----+-----+ +-------------+ +---+----------+ +--+----------------+
            | compone lo que YA existe   | traduce a     | inventario+perfilador
            v                            v PipelineSpec  v
  detect_stack · build_inventory · get_ci_provider · pipeline_renderers ·
  repo_writer · pipeline_session · ci.py (trigger/preview/monitor/runs) ·
  pipeline-lint · preflight · DevOpsVariables
                    (TODO ESTO YA EXISTE - ver 3.1)
```

**Regla arquitectónica dura:** `api/pipeline_wizard.py` **no contiene lógica de dominio**. Valida el
cuerpo, llama a servicios y serializa. Toda decisión vive en un módulo `.py` **puro y testeable sin red**.

### 5.2 Mapa de los 7 pasos

| Paso | Nombre visible | Decisión principal (UNA) | De dónde salen los datos | Se puede saltar |
|---|---|---|---|---|
| **P1** | "Esto es lo que veo de tu proyecto" | *"¿Está bien?"* (Sí / Corregir) | `probe_project` (F5): proveedor, repo, rama, stack, comandos, **inventario descripto (F2)**, variables por NOMBRE | No (pero se autocompleta entero) |
| **P2** | "¿Qué querés lograr?" | Elegir **1** objetivo de 9 | Catálogo cerrado `WIZARD_GOALS` (F4). "Modificar una pipeline existente" solo aparece si el inventario trajo ≥1 | No |
| **P3** | "Un par de datos" | Responder **solo** lo que el objetivo pide | Esquema declarativo (F4): preguntas + dependencias + defaults por stack/proveedor | Sí, si el esquema resuelve todo con defaults |
| **P4** | "¿Quién lo va a hacer?" | Elegir runtime entre los 3 | `COPILOT_RUNTIMES` + disponibilidad real | No |
| **P5** | "Preparando tu pipeline…" | Ninguna (esperar) | `PipelineIntent` (F3) → `POST /api/pipeline-generator/preview` | — |
| **P6** | "Esto es lo que va a pasar" | *"¿Seguimos?"* | Perfilador + lint + preflight + variables faltantes. **El YAML va en un `<details>` cerrado** | No |
| **P7** | "Confirmá" | Elegir **uno** de 4 actos, con uno recomendado | — | No |

**Los 4 actos del P7, separados y nombrados (nunca un botón ambiguo):**

| Acto | Escribe | Endpoint | Flag |
|---|---|---|---|
| **1. Guardar borrador** | Solo local | (localStorage del wizard) | — |
| **2. Crear/actualizar el archivo + commit** | **Repo REAL** | `POST /api/pipeline-generator/commit` (`confirm: true`) | `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` **OFF (B)** |
| **3. Registrar la definición en ADO** | ADO REAL | `DevOpsProduction.ensureAdoDefinition` (ya existe, plan 95) | la existente del 95 |
| **4. Ejecutar la pipeline** | CI REAL | `POST /api/ci/<project>/trigger` (`confirm: true`) | `STACKY_PIPELINE_TRIGGER_ENABLED` (**ya ON**) |

> Los actos 2, 3 y 4 son **botones distintos**; hacer uno **no** encadena el siguiente. El disparo
> **nunca** es automático.

### 5.3 Árbol de decisiones de P2 → P3 (cerrado y determinista)

```
P2 objetivo
+- compilar_validar ......... -> build; tests? no; artefactos? no
+- ejecutar_tests ........... -> comando de test, cobertura?, en que ramas
+- generar_artefacto ........ -> que genera, carpeta de salida, retencion
+- desplegar ................ -> ambiente, destino, estrategia, aprobacion, rollback
+- ci_completo .............. -> build + tests + (artefacto?)
+- entrega_completa ......... -> ci_completo + desplegar
+- calidad_seguridad ........ -> que chequeo, bloquea o avisa
+- modificar_existente ...... -> [SOLO si inventario >= 1] elegir del inventario + que cambiar
+- describir_libre .......... -> texto libre -> el runtime elegido propone; sigue por review
```

**Regla anti-formulario-genérico (verificada por el gate de F4):** para el objetivo `ejecutar_tests`, el
esquema debe devolver **≤ 4** preguntas y **no debe contener ninguna** pregunta cuyo `id` empiece con
`deploy_` ni con `artifact_`.

### 5.4 Contrato `PipelineIntent` (F3)

Módulo `backend/services/pipeline_intent.py`. `@dataclass(frozen=True)`, **serializable a JSON puro**.

```python
@dataclass(frozen=True)
class PipelineIntent:
    schema_version: str = "1"          # aditivo: nunca se rompe, se sube
    project: str = ""
    repository: str = ""
    provider: str = ""                 # "ado" | "gitlab"  (vocabulario de PIPELINE_FILENAME)
    default_branch: str = ""
    stack: str = ""                    # "python" | "node" | "dotnet" | ""
    framework: str = ""
    package_manager: str = ""
    goal: str = ""                     # una de WIZARD_GOALS
    pipeline_kind: str = ""            # "ci" | "cd" | "ci_cd" | "quality"
    triggers: tuple[str, ...] = ()     # ramas
    stages: tuple[str, ...] = ()
    build_command: str = ""
    test_command: str = ""
    coverage: bool = False
    artifacts: tuple[str, ...] = ()
    environments: tuple[str, ...] = ()
    deploy_target: str = ""
    variables: tuple[str, ...] = ()          # NOMBRES. JAMAS valores.  (KPI-5)
    required_secrets: tuple[str, ...] = ()   # NOMBRES. JAMAS valores.  (KPI-5)
    runtime: str = ""                  # VOCABULARIO REAL (C4), NO inventado:
                                       # "claude_code_cli" | "codex_cli" | "github_copilot"
    constraints: tuple[str, ...] = ()
    proposed_path: str = ""            # de pipeline_session.PIPELINE_FILENAME
    existing_pipeline_key: str = ""    # clave del inventario (pipeline_inventory.identity_key)
    free_text: str = ""
```

- `existing_pipeline_key` es **exactamente** la `key` que produce `identity_key` en
  `pipeline_inventory.py` (`"<provider>::<ruta normalizada>"`). Así el Paso 2 "modificar existente"
  referencia el inventario **sin inventar identificadores**.
- `intent_to_spec(intent) -> dict` traduce a lo que `dict_to_spec` (`backend/services/pipeline_spec.py:140`)
  ya sabe leer. **Es el único puente**; el wizard no renderiza YAML.
- **Puente de `variables` — especificado, no inferido (C12).** `PipelineSpec.variables` es un **`dict`**
  (`pipeline_spec.py:88` a nivel spec y `:115` a nivel stage) mientras que `PipelineIntent.variables` es
  una tupla de **NOMBRES**. La traducción es **exactamente** esta y no otra:
  ```python
  spec_dict["variables"] = {nombre: "" for nombre in intent.variables}
  ```
  Cadena vacía **a propósito**: el nombre viaja al YAML, el valor **nunca**. `required_secrets` **no**
  entra en el spec: viaja aparte, sólo para el aviso "te falta cargar X" del Paso 6.
- **Invariante KPI-5, verificado por test:** `variables` y `required_secrets` contienen **nombres**.
  `intent_to_dict` **debe** lanzar `ValueError` si algún elemento contiene `=` o `:` — es exactamente la
  forma en que un valor se cuela en una lista de nombres.

### 5.5 Contrato del inventario enriquecido (F2)

**Qué está congelado y qué no (C13).** Lo congelado de `build_inventory` (`pipeline_inventory.py:627`)
es **el shape de las 12 claves de `make_entry` (`:142`) y la lógica de reconciliación (`reconcile`,
`:207`)**: eso **no cambia**. Lo que **sí** cambia, y sólo en F10, es **aditivo**: un parámetro
`describe: bool = False` y la clave de `_CACHE` (`:602`, hoy `project or ""`). Sin el parámetro, la
salida es byte-idéntica a hoy. Se agregan además **dos** funciones nuevas al mismo módulo:

```python
def get_pipeline_yaml(pipeline_key: str, project: str | None = None) -> tuple[str, str]:
    """Devuelve (yaml_text, source_path) para una `key` del inventario.
    Cierra GAP-6: es la funcion que api/pipeline_profiler.py:32 ya importa y que no existia.
    Solo lee del WORKSPACE local (nunca de red). Si la key no resuelve a un archivo
    legible dentro del workspace, lanza KeyError (el endpoint lo mapea a 404)."""

def describe_pipeline(entry: dict, yaml_text: str | None) -> dict:
    """Enriquece UNA entrada del inventario con la ficha en castellano.
    Claves que AGREGA (6; nunca quita ni renombra las 12 existentes):
      purpose         str   frase de build_purpose_template (<=200 chars, plantilla, SIN modelo)
      purpose_source  str   "plantilla" | "sin_datos"
      stages_es       list[str]
      when_es         str   'cuando alguien sube algo a main'
      artifacts_es    list[str]
      environments_es list[str]   # [ADICION ARQUITECTO 3] de detect_environments
                                  # (pipeline_profiler.py:485). Lista VACIA = "no despliega";
                                  # purpose_source == "sin_datos" = "no se pudo determinar".
                                  # La UI NUNCA debe confundir esos dos casos (F10 caso 12).
    Si yaml_text es None o no parsea: purpose_source="sin_datos" y el resto vacio.
    NUNCA lanza."""
```

**Compatibilidad hacia atrás dura:** el shape de 12 claves de `make_entry` es un contrato congelado que
consumen los planes 247..252. `describe_pipeline` **agrega** claves; el gate de F2 verifica que las 12
originales siguen presentes y con el mismo nombre.

### 5.6 Máquina de estados del wizard

**Se reusa `backend/services/pipeline_session.py` tal cual.** El mapeo paso↔estado es **CERRADO,
TOTAL y verificado por test** (C7 — en el v1 esto era prosa que ninguna fase consumía):

```python
# vive en backend/services/pipeline_intent.py, exportado como WIZARD_STEP_TO_STATE
WIZARD_STEP_TO_STATE: dict[str, str] = {
    "p1": "discovery",
    "p2": "discovery",
    "p3": "discovery",
    "p4": "discovery",
    "p5": "draft",
    "p6": "review",     # el frontend puede mostrar "secrets" si faltan variables; la
                        # transicion review->secrets YA es legal en TRANSITIONS
    "p7": "confirm",    # confirm -> committed | failed, ya en TRANSITIONS
}
```

**Por qué esto es verificable y no una promesa:**
1. **`WIZARD_STEP_TO_STATE` es total:** sus 7 claves son exactamente `p1..p7` y **todos** sus valores
   están en `PIPELINE_SESSION_STATES` (`pipeline_session.py:15`). → **F6 caso 11**.
2. **Cada salto consecutivo del wizard es legal:** para todo `k` en `1..6`, si
   `WIZARD_STEP_TO_STATE[f"p{k}"] != WIZARD_STEP_TO_STATE[f"p{k+1}"]`, entonces
   `can_transition(origen, destino)` (`pipeline_session.py:67`) devuelve `True`. → **F6 caso 11**.
   *(Comprobación en papel contra `TRANSITIONS` `:27-36`: `discovery→draft` ✔, `draft→review` ✔,
   `review→confirm` ✔. Los tres saltos son legales hoy; el test lo vuelve permanente.)*
3. **El frontend no inventa nombres:** `pipelineWizardModel.ts` **importa `SESSION_STATES`** de
   `pipelineCopilotModel.ts` (`:16`, exportado) y su tabla de estados debe ser un subconjunto de esa
   lista. → **F8 caso 13**.
4. **No se escribe otra máquina de ESTADOS.** `WIZARD_STEPS`/`canAdvance`/`advanceWizard` de F8 son la
   **navegación de pantallas** (índice del stepper), no una segunda máquina de estados de sesión: cada
   paso se proyecta al estado canónico por (1) y todo salto se valida contra `TRANSITIONS` por (2).

`TERMINAL_STATES = ("committed", "failed")` (`:38`) ya impide avanzar desde un terminal.
El frontend espeja con lo **exportado** de `pipelineCopilotModel.ts`: `SESSION_STATES` (`:16`),
`stateLabel` (`:46`), `availableActionIds` (`:79`), `needsOperatorConfirmation` (`:84`),
`mustShowUndoHint` (`:95`). **`STATE_LABELS` y `AVAILABLE_BY_STATE` NO se pueden importar** (§3.1).

### 5.7 Los 3 runtimes: cómo se distingue el fallback legítimo de la degradación silenciosa

El brief exige dos cosas que suenan contradictorias ("los 3 runtimes con fallback explícito" vs. "la
selección se respeta sin fallback silencioso"). **No son lo mismo. Esta es la regla, y F11 la testea:**

| | **Fallback de PLATAFORMA (permitido)** | **Degradación de la ELECCIÓN (prohibida)** |
|---|---|---|
| Qué pasa | Una **capacidad opcional** del runtime elegido no está (p. ej. no puede leer el repo local) y el wizard sigue con **menos información**, avisando | El sistema **cambia el runtime** que el usuario eligió por otro |
| Quién decide | El sistema, pero **la tarea la sigue haciendo el runtime elegido** | El sistema, a espaldas del usuario |
| Visibilidad | Aviso visible + qué se perdió | Ninguna |
| Regla | El wizard **degrada la capacidad**, nunca el ejecutor | **Nunca.** Si el runtime elegido no está disponible, el wizard **se detiene** y muestra qué falta y cómo instalarlo, con los otros dos como **elección explícita del usuario** |

**Formulación operativa (la que verifican los tests de F8 y F11):** `resolve_wizard_runtime(pedido,
disponibles)` devuelve **`pedido` o `None`. Jamás un runtime distinto del pedido.** El `None` obliga a la
UI a mostrar la pantalla de "no disponible" con los 3 botones. No existe camino en el que el runtime
efectivo difiera del solicitado sin que el usuario haya vuelto a elegir.

**Vocabulario de runtime — los ids REALES, no los inventados (C4).** El v1 usaba
`("codex", "claude", "copilot")`, que **no existen en el código**. Los ids reales son los de
`COPILOT_RUNTIMES` (`frontend/src/components/devops/pipelineCopilotModel.ts:106-110`) y del tipo
`CopilotRuntimeId` (`:122`):

| id REAL | Etiqueta que ya muestra la UI | `mode` |
|---|---|---|
| `claude_code_cli` | "Claude Code (recomendado)" | `cli` |
| `codex_cli` | "Codex" | `cli` |
| `github_copilot` | "GitHub Copilot (modo determinista)" | `deterministic` |

**Todo el plan usa estos tres strings y sólo estos tres.** Cualquier aparición de `"codex"`, `"claude"`
o `"copilot"` sueltos en el código nuevo es un defecto.

> **[ADICIÓN ARQUITECTO 2] — el agujero de R4 no está en el wizard: está VIVO en producción.**
> `normalizeCopilotRuntime` (`pipelineCopilotModel.ts:127-130`) hace exactamente lo que R4 prohíbe:
> ```ts
> return (RUNTIME_IDS.includes(r) ? r : 'claude_code_cli') as CopilotRuntimeId;
> ```
> Ante un id desconocido **cambia el runtime elegido por otro, en silencio, sin avisar**. Para el
> copiloto es una decisión del 279 que este plan **no revierte** (alcance ajeno), pero
> **el wizard tiene PROHIBIDO rutear su elección por esa función**. En su lugar, F8 expone:
> ```ts
> /** R4 duro: devuelve `pedido` si esta disponible, o null. JAMAS otro runtime. */
> export function strictRuntime(pedido: string, disponibles: string[]): string | null
> ```
> y **F8 caso 14** asierta por grep del fuente que `pipelineWizardModel.ts` **no contiene** la subcadena
> `normalizeCopilotRuntime`. *(Trampa de auto-gate: no escribas ese identificador tampoco en un
> comentario del archivo; la explicación va acá, en el documento.)*

### 5.8 Endpoints: reuso vs. nuevo

**Se reusan sin tocar (12):** `/api/pipeline-inventory/list` · `/api/pipeline-generator/preview` ·
`/api/pipeline-generator/commit` · `/api/pipeline-profiler/profile` · `/api/devops/detect-stack` ·
`/api/devops/pipeline-lint/validate` · `/api/devops/pipeline-lint/explain` · `/api/devops/preflight/check` ·
`/api/devops/variables` · `/api/ci/<p>/trigger-preview` · `/api/ci/<p>/pipeline/<id>` · `/api/ci/runs`.

**Se extiende de forma ADITIVA (1):** `POST /api/ci/<p>/trigger` acepta un campo opcional `variables`
(F7). Sin ese campo, byte-idéntico a hoy.

**Nuevos, estrictamente necesarios (4), todos bajo `url_prefix="/pipeline-wizard"`:**

| Método | Ruta | Qué hace | Escribe |
|---|---|---|---|
| GET | `/api/pipeline-wizard/detect?project=` | Paso 1 completo (probe + inventario descripto) | No |
| POST | `/api/pipeline-wizard/questions` | Dado `{goal, stack, provider, has_docker, known}` devuelve las preguntas del Paso 3 | No |
| POST | `/api/pipeline-wizard/draft` | `PipelineIntent` → `PipelineSpec` → render con el motor existente | No |
| POST | `/api/pipeline-wizard/review` | Lint + preflight + variables faltantes + ficha en castellano, en **una** respuesta | No |

**No hay endpoint nuevo de commit ni de trigger.** El Paso 7 llama a los que ya existen. Eso es
deliberado: evita el tercer HITL de C7.

### 5.9 Wireframes textuales

**P1 — Entender el proyecto**

```
+---------------------------------------------------------------------------+
|  Crear una pipeline                          *--o--o--o--o--o--o   1 de 7  |
+---------------------------------------------------------------------------+
|  Esto es lo que veo de tu proyecto                                        |
|                                                                           |
|   Se conecta con .......... Azure DevOps            [cambiar]             |
|   Repositorio ............. RecoveryStrategy                              |
|   Rama principal .......... main                                          |
|   Tecnologia .............. .NET  ·  MSBuild                              |
|   Compilar con ............ dotnet build            [corregir]            |
|   Probar con .............. dotnet test             [corregir]            |
|                                                                           |
|   Ya tenes 3 pipelines  -------------------------------------------       |
|    OK  azure-pipelines.yml  · compila .NET y publica 2 artefactos         |
|        se ejecuta cuando alguien sube algo a main  ·  ultima: OK hace 2 h |
|    OK  pipelines/nightly.yml · corre las pruebas todas las noches         |
|        ultima: FALLO hace 9 h                                             |
|    !   release.yml  ·  esta en el repositorio pero no esta registrada     |
|                                                                           |
|   (i)  No pude consultar Azure DevOps (falta el token). Lo de arriba salio|
|        del repositorio. [Configurar el token]                             |
|                                                                           |
|                                        [ Esta bien, seguir ]  <- 1 accion |
+---------------------------------------------------------------------------+
```

**P6 — Revisión comprensible (el YAML NO es la interfaz principal)**

```
+---------------------------------------------------------------------------+
|  Crear una pipeline                          o--o--o--o--o--*--o   6 de 7  |
+---------------------------------------------------------------------------+
|  Esto es lo que va a pasar                                                |
|                                                                           |
|   Se va a ejecutar ....... cuando alguien suba algo a main                |
|   Va a tener 3 etapas                                                     |
|        1. Compilar ....... dotnet build en Windows                        |
|        2. Probar ......... dotnet test, y guarda el informe de cobertura  |
|        3. Empaquetar ..... genera 1 artefacto en ./publish                |
|   Genera ................. publish/ (se guarda 30 dias)                   |
|   No despliega a ningun ambiente                                          |
|   Necesita 2 valores ..... NUGET_FEED   ya cargado                        |
|                            SIGNING_KEY  FALTA   [Cargarlo ahora]          |
|   Va a crear ............. azure-pipelines.yml (hoy no existe)            |
|                                                                           |
|   1 advertencia (no bloquea)                                              |
|      No fijaste la version del SDK: si cambia, la compilacion puede fallar|
|      Como se arregla: agrega "Version de .NET" en el paso anterior        |
|                                                                           |
|   > Ver el archivo YAML (para tecnicos)         <- <details> CERRADO      |
|                                                                           |
|                    [ Volver ]                    [ Seguimos ]             |
+---------------------------------------------------------------------------+
```

**Inventario con acción (F10)**

```
+---------------------------------------------------------------------------+
|  Inventario de pipelines           [ Buscar...]  3 pipelines  [Actualizar]|
+---------------------------------------------------------------------------+
|  OK  azure-pipelines.yml                                    Azure DevOps  |
|      Compila .NET y publica 2 artefactos                                  |
|      Se ejecuta cuando alguien sube algo a main                           |
|      Ultima corrida: OK hace 2 horas            [ Ver ]  [ > Ejecutar ]   |
+---------------------------------------------------------------------------+
|  !   release.yml                                            Azure DevOps  |
|      Esta en el repositorio pero no esta registrada en Azure DevOps       |
|      Quisiste decir "releases/release.yml"?                               |
|      Nunca se ejecuto             [ Ver ]  [ > Ejecutar ] (deshabilitado: |
|                                    hay que registrarla primero. Registrar)|
+---------------------------------------------------------------------------+
```

**Confirmación de disparo (F10) — HITL**

```
+---------------------------------------------------------------------------+
|  Vas a ejecutar una pipeline de verdad                                    |
+---------------------------------------------------------------------------+
|   Pipeline ....... azure-pipelines.yml  (definicion #147)                 |
|   Proyecto ....... RecoveryStrategy                                       |
|   Proveedor ...... Azure DevOps                                           |
|   Rama ........... main                          [cambiar]                |
|   Variables ...... ninguna              (apagado: la podes activar en     |
|                                          Configuracion -> Arnes)          |
|                                                                           |
|   Que va a pasar:                                                         |
|     · Se va a encolar una corrida REAL en Azure DevOps                    |
|     · Va a consumir minutos de tu CI                                      |
|     · Esta pipeline no despliega a ningun ambiente        <- CALCULADO,   |
|       (o) Ojo: esta pipeline despliega a: produccion         no fijo.     |
|       (o) No pude determinar si despliega. Revisa el archivo.  [ADICION 3]|
|     · Si volves a apretar antes de 60 s, se reusa la misma corrida        |
|                                                                           |
|   Para cancelar: cerra esta ventana. No se ejecuta nada hasta confirmar.  |
|                                                                           |
|                    [ Cancelar ]              [ Si, ejecutar ahora ]       |
+---------------------------------------------------------------------------+
```

### 5.10 Migración, feature flag y rollback

- **Migración:** cero. No se borra ni renombra ninguna sección, endpoint o contrato. La pestaña
  `pipelines` (constructor gráfico) **queda exactamente como está** y pasa a ser el destino del enlace
  "Modo avanzado".
- **Rollback:** apagar `STACKY_PIPELINE_WIZARD_ENABLED` hace desaparecer la sección `crear-pipeline`
  (mecanismo estándar `healthKey` + `gateFlagKey` de `DevOpsPage.tsx`, igual que las otras 16 secciones
  gateadas). **Todo lo demás queda idéntico a hoy.** Es rollback de un click, por UI.
- **Aterrizaje:** `resolveLandingSection` (**`Stacky Agents/frontend/src/pages/devopsCockpitShell.ts:121-151`**)
  **no se toca**. Su último recurso sigue siendo `return 'pipelines';` (**`:150`**, verificado). Cambiarlo
  sería una regresión del plan 275.
- **Reversión del ratchet de secciones:** apagar la flag **no** saca el id del catálogo. `crear-pipeline`
  queda en `DEVOPS_SECTION_IDS` y en `DEVOPS_SECTIONS` siempre; lo que la flag apaga es el **render** (el
  mecanismo `gateFlagKey` estándar). Eso mantiene verde a `test_section_ids_espejan_el_tsx` con la flag
  en cualquier posición.

---

## 6. Principios y guardarraíles (R1..R12) — se codifican, no se prometen

| # | Regla | Cómo se verifica |
|---|---|---|
| **R1** | **Una decisión principal por pantalla.** Cada paso expone **≤ 4** campos y **exactamente 1** botón primario | Gate estructural de F9 (casos 5 y 6) |
| **R2** | **Nada se escribe sin confirmación explícita.** Los 4 actos del P7 son botones distintos y ninguno encadena al siguiente | F6 caso 8, F9 caso 8 |
| **R3** | **Cero valores de secreto** en preview, diff, prompt, log o payload. Solo NOMBRES | F3 casos 3-4, F5 caso 4, F6 casos 5 y 9, F10 caso 6 |
| **R4** | **La elección de runtime no se degrada nunca en silencio** (§5.7) | F8 caso 10 (27 combinaciones) y F11 caso 2 (24 casos) |
| **R5** | **Lectura ⇒ flag ON.** Inventariar, describir, detectar, previsualizar, diffear y seguir corridas van ON | §7.1, F1 |
| **R6** | **Nada deshabilitado sin motivo visible.** Todo control deshabilitado lleva un `title`/hint con la causa y la salida | F9 caso 7, F10 casos 2-3 |
| **R7** | **El YAML nunca es la interfaz principal.** Va dentro de un `<details>` cerrado por defecto | F9 caso 4 |
| **R8** | **Volver no pierde información.** El borrador se guarda en cada cambio de paso | F8 caso 4 |
| **R9** | **No se pregunta lo que Stacky puede averiguar.** Si `probe_project` lo trajo, el Paso 3 no lo pregunta | F4 caso 5 |
| **R10** | **Backward-compatible.** Las 12 claves de `make_entry` y el comportamiento de `trigger_pipeline` sin variables no cambian | F2 caso 9, F7 caso 1, F10 caso 12 |
| **R11** | **403 = flag apagada, no permiso.** Guard `abort(404)` per-request leyendo `_config.config` (la instancia) | F6 caso 1, F7 caso 2 |
| **R12** | **Cero trabajo para el operador.** Todo lo nuevo es automático u opt-in con default ON, salvo las dos que escriben | §7.1 |

---

## 7. Flags nuevas (3) y flags reusadas

### 7.1 Las 3 flags nuevas

| Flag | Default | Categoría de excepción | Justificación con evidencia |
|---|---|---|---|
| `STACKY_PIPELINE_WIZARD_ENABLED` | **ON** | **ninguna** | Detecta, pregunta, previsualiza y explica. **No enciende loop, daemon, barrido ni prefetch** (no aplica (A)) y **no escribe en ningún sistema del operador** (no aplica (B)). Todas las llamadas salen de un clic del usuario |
| `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` | **OFF** | **(B)** | **ESCRIBE EN EL REPOSITORIO REAL DEL OPERADOR.** El acto 2 del Paso 7 llama a `POST /api/pipeline-generator/commit`, que termina en `writer.commit_file(...)` (puerto en `backend/services/repo_writer.py:17`, implementaciones en `backend/services/ado_provider.py:146` y `backend/services/gitlab_provider.py:853`). Precedentes literales en el repo: `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED` (`backend/config.py:2571-2573`) y `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` |
| `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` | **OFF** | **(B)** | **INYECTA VALORES EN UNA CORRIDA REAL DEL CI DEL OPERADOR.** Hoy el disparo manda **solo la rama** (`backend/services/ado_ci_provider.py`, cuerpo `resources.repositories.self.refName` dentro de `trigger_pipeline`; `backend/services/gitlab_ci_provider.py`, `trigger_pipeline` delega con solo `ref`). Mandar variables por corrida cambia **qué hace** esa ejecución —puede apuntarla a otro ambiente o a otro destino de despliegue—, y eso es una decisión que le corresponde al operador |

> **Por qué NO nace una cuarta flag para "disparar".**
> El operador pidió "partí la capacidad en dos: ver ON, disparar OFF". **En este repo ya está partida y
> ya está decidida:** `STACKY_PIPELINE_TRIGGER_ENABLED` existe desde el plan 72 y su default efectivo es
> **ON** por **decisión explícita del operador el 2026-07-05** (`backend/config.py:1731-1733`;
> `FlagSpec` con `default=True` en `harness_flags.py:3783`). Crear una flag nueva OFF que tape una
> capacidad que él ya encendió **sería una regresión**, y apagar la existente viola la regla de "no
> degradar". Lo que este plan agrega sobre el disparo —**variables por corrida**— sí es nuevo, sí escribe
> más en su CI, y **por eso** nace OFF citando (B). El HITL (`confirm=True`) ya es obligatorio y no se
> relaja: `backend/api/ci.py` rechaza con 400 sin él.

### 7.2 Los OCHO guardianes de cada flag nueva (verificados en este repo)

Para **cada** flag nueva hay que tocar **todos** estos. Si falta uno, la flag queda **inerte** o el arnés
se pone rojo:

| # | Archivo | Qué se agrega | Cuándo aplica |
|---|---|---|---|
| **1** | `Stacky Agents/backend/services/harness_flags.py` | `FlagSpec(key=..., type="bool", label=..., description=..., group="global", env_only=False)` dentro de `FLAG_REGISTRY` | Siempre |
| **2** | `Stacky Agents/backend/services/harness_flags.py` | La key en `_CATEGORY_KEYS` (línea 120), **categoría `"devops"`** (bloque que arranca en `harness_flags.py:258`) | Siempre — si falta, `test_every_registry_flag_is_categorized` (`test_harness_flags.py:1135`) se pone rojo |
| **3** | `Stacky Agents/backend/config.py` | El `os.getenv("<KEY>", "true"\|"false").strip().lower() == "true"` — **este es el default EFECTIVO** | Siempre |
| **4** | `Stacky Agents/backend/services/harness_flags_help.py` | Entrada en `PLAIN_HELP` con `what` / `on_effect` / `off_effect` / `example` | Siempre — `test_plain_help_covers_all_registry_keys` (`test_harness_flags_help.py:32`) |
| **5** | `Stacky Agents/backend/tests/test_harness_flags.py` | La key en `_CURATED_DEFAULTS_ON` (línea 467) | **SOLO si nace ON** |
| **6** | `Stacky Agents/backend/services/harness_flags.py` | `default=True` en el `FlagSpec` | **SOLO si nace ON.** Una flag OFF **NO declara `default=`** (ver el comentario literal del `FlagSpec` de `STACKY_PIPELINE_COPILOT_COMMIT_ENABLED`, `harness_flags.py:6815`): declararlo la volvería `default_is_known()` y `test_default_known_only_for_curated` (`test_harness_flags.py:1207`) exige que ese conjunto sea **exactamente** `_CURATED_DEFAULTS_ON` |
| **7** | `Stacky Agents/backend/services/harness_flags.py` | `requires="<KEY PADRE>"` en el `FlagSpec` | Si depende de otra. **`STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` declara `requires="STACKY_PIPELINE_WIZARD_ENABLED"`** y **`STACKY_PIPELINE_TRIGGER_VARS_ENABLED` declara `requires="STACKY_PIPELINE_TRIGGER_ENABLED"`**. Guardián: `backend/tests/test_harness_flags_requires.py` |
| **8** | `Stacky Agents/deployment/export_harness_defaults.py` → `Stacky Agents/deployment/harness_defaults.env` | Regenerar el archivo | Siempre. Guardián: `backend/tests/test_harness_flags_bounds.py:262` (`test_harness_defaults_env_within_bounds`) |

**Además (guardián transversal):** `backend/tests/test_flag_wiring.py`
(`test_every_non_reserved_flag_is_wired`, línea 57) exige que la flag **tenga un consumidor real** en el
código.

> **CÓMO FUNCIONA DE VERDAD ESE CENTINELA (C6) — leerlo o F6 nace insatisfacible.**
> `_production_corpus()` (`test_flag_wiring.py:30-53`) concatena **`backend/**/*.py` MÁS
> `frontend/src/**/*.{ts,tsx}`** (excluye `backend/tests/**`, `services/harness_flags.py`,
> `services/harness_flags_help.py` y todo directorio `__tests__`). El assert es
> `spec.key not in corpus`: **basta con que la key aparezca como LITERAL** en cualquiera de esos
> archivos. No exige un `getattr` — pero **sí** exige que alguien la escriba en producción.
>
> **Consecuencia sobre este plan, medida:**
> - `STACKY_PIPELINE_WIZARD_ENABLED` → consumidor en F6 (`api/pipeline_wizard.py`, `_gate()`).
> - `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` → consumidor recién en **F7** (`api/ci.py`).
> - `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` → en el v1 **no tenía ningún consumidor backend jamás**,
>   sólo un `title` de un `.tsx` que ni siquiera se exigía que contuviera la key.
>
> **Resolución (sin relajar el gate):** **F1 agrega las DOS claves nuevas a `_health_payload`**
> (`backend/api/devops.py:28`, patrón idéntico a las 40+ que ya están ahí):
> ```python
> "pipeline_wizard_enabled": bool(getattr(cfg, "STACKY_PIPELINE_WIZARD_ENABLED", False)),          # Plan 294
> "pipeline_wizard_commit_enabled": bool(getattr(cfg, "STACKY_PIPELINE_WIZARD_COMMIT_ENABLED", False)),  # Plan 294
> "pipeline_trigger_vars_enabled": bool(getattr(cfg, "STACKY_PIPELINE_TRIGGER_VARS_ENABLED", False)),    # Plan 294
> ```
> Es **consumo productivo real** (lo lee la UI para decidir qué habilitar), es **aditivo**, y deja las 3
> flags cableadas **desde F1**. Por eso el gate de wiring se corre en **F1 y F9**, y **no** en F6.

**Trampas literales de `PLAIN_HELP` (medidas en el test):**
`test_plain_help_on_off_start_with_si` (`test_harness_flags_help.py:56`) exige que `on_effect` y
`off_effect` empiecen con **`"Si "` SIN TILDE**; `test_plain_help_fields_non_empty_and_bounded`
(`:44`) exige los 4 campos no vacíos y acotados; `test_plain_help_has_no_orphan_keys` (`:38`) prohíbe
entradas sin `FlagSpec`.

**La UI no requiere trabajo extra:** `HarnessFlagsPanel` se arma solo desde el registro categorizado. Con
los 8 guardianes hechos, la flag ya es editable por UI (riel duro "toda config del operador por UI").

### 7.3 Rojos de fábrica del backend — MEDIR LA LÍNEA BASE ANTES DE EMPEZAR

Antes de F0, correr y **anotar** el resultado en el commit. Hay rojos ajenos preexistentes; si no se
miden, se confunden con daño propio:

```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flag_wiring.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_bounds.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_devops_action_ratchet.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan260_trigger_gate.py" -q
```

**Criterio de no-regresión de todo el plan:** el conteo de fallos de cada uno de esos **7** archivos
**después** del plan debe ser **≤** el de la línea base. No se exige verde absoluto: se exige
**delta ≤ 0**.

> **DOS de esos 7 son NUEVOS en la v2 y NO son opcionales (C5, C16):**
> - `test_devops_action_ratchet.py` — **medido el 2026-08-02: `13 passed`, VERDE.** Su
>   `test_section_ids_espejan_el_tsx` compara con `==` los ids del `.tsx` contra `DEVOPS_SECTION_IDS`.
>   F9 lo rompe si no se toca el catálogo. Como está verde hoy, **su delta admisible es 0 fallos: tiene
>   que seguir en 13 passed.**
> - `test_plan260_trigger_gate.py` — espía `trigger_pipeline_route` monkeypatcheando
>   `ci_mod.should_trigger` (`:329-341`) y verifica que el gate del plan 260 corra **antes**. F7 edita
>   exactamente esa ruta e inserta código **entre** el guard HITL y la idempotencia: es el test que
>   detecta si el orden se rompió.

---

## 8. Fases

> **Orden de dependencia:** F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9 → F10 → F11.
> **Cada fase declara su comando exacto y su criterio binario.**
> **Ninguna fase queda sin forma de verificarse.**

---

### F0 — Censo ejecutable: congelar lo que YA existe (P0)

**Objetivo (1 frase):** dejar un test que **falle hoy** y pase al final, y que **impida** que un
implementador reescriba las capacidades que ya existen.

**Valor:** es la mitad de contraste del plan. Sin esto, "reusar lo existente" es una intención.

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_plan294_baseline.py`

**Archivos a editar:**
- `Stacky Agents/backend/scripts/run_harness_tests.ps1` — agregar la línea `  "tests/test_plan294_baseline.py",`
- `Stacky Agents/backend/scripts/run_harness_tests.sh` — agregar la línea `  tests/test_plan294_baseline.py`

**Tests (TDD) — casos exactos:**

1. `test_inventario_ya_existe` — `from services.pipeline_inventory import build_inventory, reconcile, scan_repo_pipelines, identity_key, make_entry` **no lanza**, y `CATEGORIES` tiene **4** elementos.
2. `test_trigger_ya_existe` — `from services.ci_provider import CI_PORT_METHODS`; `"trigger_pipeline" in CI_PORT_METHODS`.
3. `test_perfilador_ya_existe` — `from services.pipeline_profiler import build_purpose_template, detect_phases, detect_triggers, detect_artifacts` no lanza.
4. `test_maquina_de_estados_ya_existe` — `from services.pipeline_session import PIPELINE_SESSION_STATES, TRANSITIONS, advance`; `len(PIPELINE_SESSION_STATES) == 8`.
5. `test_escritor_de_repo_ya_existe_en_los_dos_proveedores` — los módulos `services.ado_provider` y `services.gitlab_provider` contienen ambos, leídos como texto, la cadena `def commit_file`.
6. **`test_get_pipeline_yaml_falta` (NACE ROJO)** — `from services.pipeline_inventory import get_pipeline_yaml` **debe importar sin error**. Hoy lanza `ImportError`. **Contraste de F2.**
   > **C18 — el `import` va DENTRO del cuerpo del test, nunca a nivel de módulo.** A nivel de módulo,
   > pytest reporta **error de colección** (`1 error`) y **ningún** otro caso del archivo corre: el
   > criterio "6 passed, 3 failed" sería inalcanzable y el implementador creería que rompió todo.
7. **`test_flags_294_registradas` (NACE ROJO)** — las 3 keys nuevas están en `{s.key for s in FLAG_REGISTRY}`. **Contraste de F1.**
8. **`test_docstring_de_ci_no_miente` (NACE ROJO)** — leer `backend/api/ci.py` como texto y asertar que **no** contiene la subcadena `default OFF`. **Contraste de F1.** *(Verificado: hoy la contiene, en `api/ci.py:11`.)*
9. `test_no_hay_segundo_renderizador` — grep en `backend/services/` de `def to_ado_yaml` devuelve **exactamente 1** archivo (`pipeline_renderers.py`, `:110`; `to_gitlab_yaml` en `:308`). Guarda anti-duplicación permanente.
10. **`test_los_cuatro_montajes_del_trigger_siguen_ahi` (NUEVO v2 — C1)** — leer los 4 `.tsx` como texto
    y asertar que **cada uno** contiene `<TriggerPipelineSection`:
    `frontend/src/components/devops/PipelineBuilderSection.tsx`,
    `frontend/src/components/devops/EnvironmentsSection.tsx`,
    `frontend/src/components/devops/ProductionFlow.tsx`,
    `frontend/src/components/devops/PublicationsSection.tsx`.
    **Nace VERDE y debe seguir verde.** Existe porque el v1 afirmaba que había **un solo** montaje: este
    caso impide que alguien "consolide" el disparo y rompa 3 superficies vivas creyendo el dato viejo.
11. **`test_exports_reales_del_modelo_del_copiloto` (NUEVO v2 — C2)** — leer
    `frontend/src/components/devops/pipelineCopilotModel.ts` como texto y asertar, en un solo caso, las
    dos mitades:
    - **presencia:** contiene `export const SESSION_STATES`, `export function stateLabel`,
      `export function availableActionIds`, `export const COPILOT_RUNTIMES`.
    - **ausencia:** **no** contiene `export const STATE_LABELS` ni `export const AVAILABLE_BY_STATE`
      (son privadas, `:34` y `:50`).
    **Nace VERDE.** Su valor es informativo-duro: si alguien las exporta para "arreglar" el plan, este
    caso se pone rojo y obliga a discutirlo en vez de ampliar la superficie pública del 279.

> **TRAMPA — leerla o el gate se autoinvalida.** El caso 8 grepea la cadena `default OFF` sobre
> `backend/api/ci.py`. **No escribas esa cadena en un comentario nuevo de ese archivo** al corregirlo,
> ni siquiera para explicar la corrección. Redactá el comentario como *"default ON (operador
> 2026-07-05)"*. El caso 9 grepea `backend/services/`, no `docs/`: este documento no lo afecta.

**Comando exacto:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_baseline.py" -q
```

**Criterio de aceptación BINARIO:** al terminar F0, la corrida da **8 passed, 3 failed** (fallan los casos
6, 7 y 8; los 11 casos existen). Al terminar F2, da **11 passed, 0 failed**. **Si al crear F0 da 11
passed, el test no prueba nada y hay que arreglarlo antes de seguir.** Si da `1 error` en vez de
`8 passed, 3 failed`, el import del caso 6 quedó a nivel de módulo (C18): moverlo adentro del test.

**Flag que la protege:** ninguna (es un test).
**Impacto por runtime:** ninguno. Fallback: n/a.
**Trabajo del operador: ninguno.**

---

### F1 — Las 3 flags, con sus 8 guardianes (P0)

**Objetivo:** registrar `STACKY_PIPELINE_WIZARD_ENABLED` (ON),
`STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` (OFF, B) y `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` (OFF, B),
y corregir el comentario mentiroso de `api/ci.py`.

**Valor:** sin esto, todo lo demás es código muerto que ningún guard puede encender.

**Archivos a editar (exactos):**

| Archivo | Qué |
|---|---|
| `Stacky Agents/backend/services/harness_flags.py` | 3 `FlagSpec` en `FLAG_REGISTRY` + las 3 keys en `_CATEGORY_KEYS["devops"]` |
| `Stacky Agents/backend/config.py` | 3 atributos con su `os.getenv` |
| `Stacky Agents/backend/services/harness_flags_help.py` | 3 entradas en `PLAIN_HELP` |
| `Stacky Agents/backend/tests/test_harness_flags.py` | `STACKY_PIPELINE_WIZARD_ENABLED` en `_CURATED_DEFAULTS_ON` (**solo esa**) |
| `Stacky Agents/deployment/harness_defaults.env` | regenerar con `deployment/export_harness_defaults.py` (**verificado: el generador existe en `deployment/`**) |
| `Stacky Agents/backend/api/ci.py` | docstring de módulo (línea 11): reemplazar la frase del default por *"Flag STACKY_PIPELINE_TRIGGER_ENABLED: default ON (operador 2026-07-05), leida per-request."* |
| **`Stacky Agents/backend/api/devops.py`** *(NUEVO v2 — C6/C15)* | dentro de **`_health_payload`** (`:28`), **3 claves aditivas** al final del dict: `pipeline_wizard_enabled`, `pipeline_wizard_commit_enabled`, `pipeline_trigger_vars_enabled` (el snippet exacto está en §7.2). **Esto es lo que cablea las 3 flags desde F1** y lo que la UI lee para R6 |

**Diff ilustrativo — `backend/config.py`:**
```python
    # -- Plan 294 - Wizard guiado de creacion de pipelines --
    # Lectura, preguntas, borrador y explicacion. NO escribe nada. Default ON:
    # no enciende loop/daemon/barrido (no es (A)) y no toca sistemas del operador (no es (B)).
    STACKY_PIPELINE_WIZARD_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_WIZARD_ENABLED", "true"
    ).strip().lower() == "true"
    # Excepcion dura (B): el paso 7 ESCRIBE el archivo de pipeline en el repositorio REAL
    # (repo_writer.commit_file). Nace APAGADA. Precedente: STACKY_PIPELINE_COPILOT_COMMIT_ENABLED.
    STACKY_PIPELINE_WIZARD_COMMIT_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_WIZARD_COMMIT_ENABLED", "false"
    ).strip().lower() == "true"
    # Excepcion dura (B): manda VARIABLES a una corrida REAL del CI del operador; pueden
    # cambiar a que ambiente apunta esa ejecucion. Nace APAGADA.
    STACKY_PIPELINE_TRIGGER_VARS_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_TRIGGER_VARS_ENABLED", "false"
    ).strip().lower() == "true"
```

**Diff ilustrativo — `FlagSpec` de una que nace OFF (nótese la AUSENCIA de `default=`):**
```python
    FlagSpec(
        key="STACKY_PIPELINE_WIZARD_COMMIT_ENABLED",
        # SIN default= A PROPOSITO. Una flag OFF no lo declara: la volveria
        # default_is_known() y test_default_known_only_for_curated exige que ese
        # conjunto sea EXACTAMENTE _CURATED_DEFAULTS_ON, donde una OFF no entra.
        # Excepcion dura (B): ESCRIBE el archivo de pipeline en el repositorio REAL.
        type="bool",
        label="El asistente puede crear el archivo en tu repositorio",
        description=(
            "Plan 294 - Decide si el asistente guiado puede escribir el archivo de "
            "pipeline en la rama que elijas de tu repositorio real, o si solo puede "
            "mostrarte el borrador. Nace APAGADA: aun encendida exige tu confirmacion "
            "explicita. OFF: el asistente llega hasta el borrador revisado y te ofrece "
            "copiarlo para que lo crees vos."
        ),
        group="global",
        env_only=False,          # editable por UI (regla dura operator-config-always-via-ui)
        requires="STACKY_PIPELINE_WIZARD_ENABLED",
    ),
```

**Tests (TDD) — archivo NUEVO `Stacky Agents/backend/tests/test_plan294_flags.py`:**
1. Las 3 keys están en `FLAG_REGISTRY`.
2. `config.STACKY_PIPELINE_WIZARD_ENABLED is True` con el entorno limpio.
3. `config.STACKY_PIPELINE_WIZARD_COMMIT_ENABLED is False` y `config.STACKY_PIPELINE_TRIGGER_VARS_ENABLED is False`.
4. `default_is_known(spec)` es `True` **solo** para `STACKY_PIPELINE_WIZARD_ENABLED` de las tres.
5. Las 3 están en `_CATEGORY_KEYS["devops"]`.
6. Las 3 tienen entrada en `PLAIN_HELP` con los 4 campos no vacíos, y `on_effect`/`off_effect` empiezan con la cadena `"Si "`.
7. `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` declara `requires="STACKY_PIPELINE_WIZARD_ENABLED"`; `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` declara `requires="STACKY_PIPELINE_TRIGGER_ENABLED"`.
8. **(NUEVO v2 — C6/C15)** `from api.devops import _health_payload`; el dict devuelto contiene las **3** claves nuevas (`pipeline_wizard_enabled`, `pipeline_wizard_commit_enabled`, `pipeline_trigger_vars_enabled`) y **conserva** `trigger_enabled`, `generator_enabled` y `pipeline_inventory_enabled` con el mismo nombre (no-regresión del payload).
9. **(NUEVO v2 — C6)** Las **3** keys aparecen como **literal** en al menos un archivo de `backend/` que **no** sea `tests/`, `services/harness_flags.py` ni `services/harness_flags_help.py` — es exactamente la condición que evalúa `_production_corpus()` de `test_flag_wiring.py:30-53`. **Mitad de contraste: este caso falla si alguien registra las flags y se olvida del `_health_payload`.**

**Ratchets:** registrar `test_plan294_flags.py` en los DOS (`.ps1` con comillas y coma, `.sh` sin nada).

**Comandos exactos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_bounds.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flag_wiring.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_devops_action_ratchet.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_baseline.py" -q
```

**Criterio BINARIO:** `test_plan294_flags.py` → **9 passed, 0 failed**. Los 5 archivos de arnés
(`test_harness_flags`, `_help`, `_requires`, `_bounds`, `test_flag_wiring`) → **fallos ≤ línea base de
§7.3**. `test_devops_action_ratchet.py` → **13 passed** (F1 no lo toca; se corre para fijar que sigue
verde antes de F9). `test_plan294_baseline.py` → los casos 7 y 8 pasan, queda **1 failed** (el caso 6,
que cierra F2) → **10 passed, 1 failed**.

> **CORRECCIÓN v2 (C6) — la nota del v1 sobre `test_flag_wiring.py` era exactamente al revés.**
> El v1 decía *"correrlo recién al cerrar F6"*. Pero en F6 **dos de las tres flags siguen sin
> consumidor** (`TRIGGER_VARS` llega en F7 y `WIZARD_COMMIT` no llegaba nunca al backend), así que el
> criterio de F6 era insatisfacible. Con las 3 claves en `_health_payload`, **el gate se corre en F1**
> (donde ya tiene que pasar) **y se repite en F9**. Si en F1 sale rojo, **sí es daño propio**: falta el
> `_health_payload`.

**Flag que la protege:** las tres son el entregable.
**Impacto por runtime:** ninguno (son flags de servidor). Fallback: n/a.
**Trabajo del operador: opt-in (default ON)** para el wizard; las dos que escriben las enciende él por UI cuando quiera.

---

### F2 — `get_pipeline_yaml` + `describe_pipeline`: el inventario habla castellano (P0)

**Objetivo:** cerrar el bug vivo GAP-6 y darle al inventario la frase en castellano que el perfilador ya
sabe generar, **sin gastar un token**.

**Valor:** es el corazón del requisito "importantísimo" del operador. Convierte
`azure-pipelines.yml / ci / main` en *"Compila .NET y publica 2 artefactos; se ejecuta cuando alguien sube
algo a main."*

**Archivos a editar:**
- `Stacky Agents/backend/services/pipeline_inventory.py` — **agregar** `get_pipeline_yaml` y
  `describe_pipeline` al final del archivo. **No tocar nada de lo existente.**
- **`Stacky Agents/docs/sistema/error_fingerprints.json`** *(NUEVO v2 — C22)* — esta fase **mata una
  clase de error viva**: el `501 {"error": "inventory_unavailable"}` que `api/pipeline_profiler.py:33-38`
  devuelve **siempre** que se pide un perfil por `pipeline_id`. Registrar su huella con
  `status: "resuelto"` y el plan que la cierra (294 F2). **Antes de editar, abrir el archivo y copiar el
  shape de una entrada existente; NO inventar campos.** Si el archivo declara un `status` cerrado por
  enum y `"resuelto"` no está entre los valores, usar el valor existente que signifique lo mismo —
  **nunca agregar un valor nuevo al enum** (precedente conocido: un `status` fuera del enum pone rojo el
  catálogo).

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_plan294_describe.py`

**Ratchets:** registrar el test en los DOS.

**Pseudocódigo (los imports son LAZY, como manda el módulo):**

```python
def get_pipeline_yaml(pipeline_key: str, project: str | None = None) -> tuple[str, str]:
    """Cierra GAP-6. SOLO disco local, nunca red. Lanza KeyError si no resuelve."""
    from pathlib import Path                              # noqa: PLC0415
    from runtime_paths import _active_workspace_root      # noqa: PLC0415
    root = _active_workspace_root()
    if not root:
        raise KeyError("sin_workspace_activo")
    raiz = Path(str(root)).resolve()
    # la key es "<provider>::<ruta normalizada>"  (identity_key)
    if "::" not in (pipeline_key or ""):
        raise KeyError("clave_invalida")
    _prov, _, rel = pipeline_key.partition("::")
    if not rel or rel.startswith("#"):     # "#def123" / "#desconocida": no hay archivo
        raise KeyError("sin_archivo_en_repo")
    ruta = (raiz / rel).resolve()
    # ANTI PATH TRAVERSAL - mismo criterio que api/ci.py, helper _leer_yaml_por_path
    if raiz != ruta and raiz not in ruta.parents:
        raise KeyError("fuera_del_workspace")
    if not ruta.is_file():
        raise KeyError("archivo_inexistente")
    if ruta.stat().st_size > _MAX_YAML_BYTES:      # reusa el cap que YA existe en el modulo
        raise KeyError("archivo_demasiado_grande")
    return ruta.read_text(encoding="utf-8", errors="replace"), rel


def describe_pipeline(entry: dict, yaml_text: str | None) -> dict:
    """AGREGA claves. NUNCA quita ni renombra las 12 de make_entry. NUNCA lanza."""
    out = dict(entry)
    out["purpose"] = ""
    out["purpose_source"] = "sin_datos"
    out["stages_es"] = []
    out["artifacts_es"] = []
    out["when_es"] = _frase_de_trigger(entry.get("trigger") or {})   # el inventario YA lo trae
    if not yaml_text:
        return out
    try:
        from services.pipeline_profiler import (            # noqa: PLC0415
            profile_pipeline, build_purpose_template,
        )
        perfil = profile_pipeline(yaml_text, source_path=entry.get("yaml_path") or "")
        out["purpose"] = build_purpose_template(perfil)   # determinista, <=200, SIN modelo
        out["purpose_source"] = "plantilla"
        out["stages_es"] = _fases_es(perfil)
        out["artifacts_es"] = _artefactos_es(perfil)
    except Exception:            # noqa: BLE001 - la ficha degrada, el inventario nunca rompe
        pass
    return out
```

`_frase_de_trigger` traduce el bloque `trigger` del inventario a castellano con una **tabla cerrada**
consultada **siempre por `.get()`, nunca por `[]`** (el vocabulario del proveedor es abierto; un lookup
directo lanzaría `KeyError` y, como el llamador atrapa todo, un proyecto sano aparecería sin ficha):

```python
_WHEN_ES = {
    "ci":      "cuando alguien sube algo a {ramas}",
    "default": "cuando alguien sube algo a la rama principal",
    "none":    "solo cuando lo pedis a mano",
    "unknown": "no se pudo determinar cuando se ejecuta",
}
```

**Casos borde obligatorios:** key sin `::`; key `"azure_devops::#def147"` (registrada sin archivo);
ruta con `..` (traversal); archivo mayor al cap; YAML que no parsea; `yaml_text=None`; `entry` incompleto.

**Tests — casos exactos (`test_plan294_describe.py`):**
1. `get_pipeline_yaml` **se puede importar** (cierra el caso 6 de F0).
2. Con un workspace temporal y un `azure-pipelines.yml` válido, devuelve `(texto, ruta_relativa)`.
3. Key `"azure_devops::#def147"` → `KeyError`.
4. Key con `"../../etc/passwd"` → `KeyError` y **no lee** el archivo.
5. Archivo mayor a `_MAX_YAML_BYTES` → `KeyError`.
6. `describe_pipeline(entry, texto_valido)` devuelve `purpose` no vacío y `purpose_source == "plantilla"`.
7. `describe_pipeline(entry, None)` devuelve `purpose_source == "sin_datos"` y **no lanza**.
8. `describe_pipeline(entry, "a: [\n")` (YAML roto) **no lanza** y deja `purpose_source == "sin_datos"`.
9. **R10:** el dict devuelto conserva **las 12 claves** de `make_entry` con el mismo nombre y el mismo valor.
10. `describe_pipeline` **no hace red**: monkeypatchear `socket.socket` para que lance y verificar que igual pasa.
11. **KPI-4:** `_frase_de_trigger` con un `kind` fuera de la tabla (p. ej. `"scheduled"`) devuelve la frase de `"unknown"` y **no lanza `KeyError`**.

**Comandos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_describe.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan246_pipeline_inventory.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan246_repo_scan.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan247_endpoint.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_baseline.py" -q
```

**Criterio BINARIO:** `test_plan294_describe.py` → **11 passed, 0 failed**. `test_plan294_baseline.py` →
**11 passed, 0 failed** (los 11 casos, incluidos los 2 nuevos de la v2). Los 3 archivos del 246/247 →
**el mismo conteo que antes de la fase**.

> **NOTA sobre `test_plan247_endpoint.py`:** su caso `test_pipeline_id_sin_inventario_devuelve_501`
> (`:61-76`) **fuerza el `ImportError` con un `monkeypatch` de `builtins.__import__`**. Por eso
> **sigue pasando** aunque `get_pipeline_yaml` ya exista. **No lo borres ni lo cambies.**

**Flag que la protege:** `STACKY_PIPELINE_INVENTORY_ENABLED` (ya ON) y `STACKY_PIPELINE_PROFILER_ENABLED` (ya ON).
**Impacto por runtime:** ninguno (determinista, sin modelo). Fallback: n/a.
**Trabajo del operador: ninguno.**

---

### F3 — El contrato `PipelineIntent` (P0)

**Objetivo:** un objeto declarativo que el wizard llena y que se traduce a lo que el generador ya sabe leer.

**Valor:** el agente recibe **intención estructurada**, no texto libre (requisito explícito del brief).

**Archivos a crear:**
- `Stacky Agents/backend/services/pipeline_intent.py`
- `Stacky Agents/backend/tests/test_plan294_intent.py`

**Ratchets:** los DOS.

**API exacta del módulo:**
```python
INTENT_SCHEMA_VERSION: str = "1"

#: Los 3 ids REALES (C4). Espejan COPILOT_RUNTIMES de pipelineCopilotModel.ts:106-110.
WIZARD_RUNTIME_IDS: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

#: Mapeo CERRADO paso del wizard -> estado canonico de pipeline_session (5.6, C7).
WIZARD_STEP_TO_STATE: dict[str, str] = {...}             # 7 claves p1..p7

@dataclass(frozen=True)
class PipelineIntent: ...                                # los 24 campos de 5.4

def intent_from_dict(d: dict | None) -> PipelineIntent   # tolerante: campo desconocido se IGNORA
def intent_to_dict(i: PipelineIntent) -> dict            # lanza ValueError si un "nombre" trae "=" o ":"
def intent_to_spec(i: PipelineIntent) -> dict            # dict que services.pipeline_spec.dict_to_spec acepta
                                                         # variables -> {nombre: ""}  (C12)
def validate_intent(i: PipelineIntent) -> list[str]      # motivos en CASTELLANO; vacia si OK
```

**Tests — casos exactos:**
1. Round-trip: `intent_from_dict(intent_to_dict(i)) == i`.
2. Campo desconocido en el dict → se ignora, no lanza.
3. **R3:** `variables=("API_KEY=secreto",)` → `intent_to_dict` lanza `ValueError`.
4. **R3:** `required_secrets=("TOKEN: abc",)` → `ValueError`.
5. `intent_to_spec` produce un dict que `services.pipeline_spec.dict_to_spec` acepta y cuyo `.validate()` devuelve `[]`, **para los 3 stacks** (`python`, `node`, `dotnet`).
6. `proposed_path` sale de `pipeline_session.PIPELINE_FILENAME` según `provider` (`"ado"` → `azure-pipelines.yml`; `"gitlab"` → `.gitlab-ci.yml`).
7. `validate_intent` con `goal=""` devuelve al menos un motivo no vacío.
8. `validate_intent` con `goal="modificar_existente"` y `existing_pipeline_key=""` devuelve un motivo.
9. El módulo **no importa red ni modelo**: grep del fuente por `requests`, `urllib`, `ado_client`, `gitlab_client` = 0 ocurrencias.
10. **(NUEVO v2 — C12) El puente de `variables` es exacto.** Con
    `PipelineIntent(variables=("NUGET_FEED", "SIGNING_KEY"), ...)`:
    `intent_to_spec(i)["variables"] == {"NUGET_FEED": "", "SIGNING_KEY": ""}` — **un `dict`, no una
    lista**, con **todos los valores string vacío**. Y `required_secrets` **no** aparece como clave del
    spec. *(Existe porque `PipelineSpec.variables` es un `dict` (`pipeline_spec.py:88`) y el v1 no decía
    cómo se llenaba: sin esto, el caso 5 es inimplementable sin adivinar.)*
11. **(NUEVO v2 — C4) Vocabulario de runtime.** `validate_intent` con
    `runtime="claude"` (id inventado) devuelve **al menos un motivo**; con `runtime="claude_code_cli"`
    devuelve **cero motivos por ese campo**. Los 3 ids aceptados son exactamente
    `("claude_code_cli", "codex_cli", "github_copilot")`.

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_intent.py" -q
```
**Criterio BINARIO:** **11 passed, 0 failed**.
**Flag:** ninguna (módulo puro; lo gatea quien lo consuma, en F6).
**Impacto por runtime:** ninguno. Fallback: n/a.
**Trabajo del operador: ninguno.**

---

### F4 — Esquema declarativo de preguntas dinámicas (P0)

**Objetivo:** que las preguntas del Paso 3 salgan de **datos**, no de `if`s, para que agregar un tipo de
pipeline sea agregar una entrada y no reescribir el wizard.

**Valor:** mata C9 de raíz y hace el wizard extensible.

**Archivos a crear:**
- `Stacky Agents/backend/services/pipeline_wizard_schema.py`
- `Stacky Agents/backend/tests/test_plan294_wizard_schema.py`

**Ratchets:** los DOS.

**Estructura de datos exacta:**
```python
@dataclass(frozen=True)
class WizardGoal:
    id: str; label: str; help: str; example: str
    pipeline_kind: str                 # "ci" | "cd" | "ci_cd" | "quality"
    needs_inventory: bool = False      # True SOLO para "modificar_existente"

WIZARD_GOALS: tuple[WizardGoal, ...] = (...)      # los 9 de la tabla de abajo, EN ESE ORDEN

@dataclass(frozen=True)
class WizardQuestion:
    id: str; label: str; help: str; example: str
    kind: str                          # "text" | "choice" | "bool" | "multi"
    options: tuple[str, ...] = ()
    default: str = ""
    required: bool = True
    depends_on: tuple[tuple[str, str], ...] = ()   # (id_de_pregunta, valor) - AND
    autofilled_from: str = ""          # clave del probe (F5) que la resuelve sola  -> R9

def questions_for(goal: str, *, stack: str = "", provider: str = "",
                  has_docker: bool = False, known: dict | None = None
                  ) -> tuple[WizardQuestion, ...]:
    """PURA. `known` son los datos que el probe YA trajo: toda pregunta cuyo
    `autofilled_from` este en `known` con valor no vacio se OMITE (R9)."""

def visible_questions(qs, answers: dict) -> tuple[WizardQuestion, ...]:
    """Filtra por depends_on. PURA."""

def default_answers(goal: str, stack: str, provider: str) -> dict:
    """Defaults seguros por stack. dotnet -> 'dotnet build'/'dotnet test';
    node -> 'npm run build'/'npm test'; python -> 'pip install -r requirements.txt'/'pytest'."""
```

**Los 9 objetivos, con su `pipeline_kind` FIJADO (v2 — el v1 dejaba el `kind` de 4 de ellos sin
declarar, y `pipeline_kind` es un vocabulario cerrado de 4 valores):**

| # | `id` | `pipeline_kind` | `needs_inventory` |
|---|---|---|---|
| 1 | `compilar_validar` | `ci` | `False` |
| 2 | `ejecutar_tests` | `ci` | `False` |
| 3 | `generar_artefacto` | `ci` | `False` |
| 4 | `desplegar` | `cd` | `False` |
| 5 | `ci_completo` | `ci` | `False` |
| 6 | `entrega_completa` | `ci_cd` | `False` |
| 7 | `calidad_seguridad` | `quality` | `False` |
| 8 | `modificar_existente` | `ci` | **`True`** |
| 9 | `describir_libre` | `ci` | `False` |

**Tests — casos exactos:**
1. `WIZARD_GOALS` tiene **9** entradas, ids únicos, y **cada una** tiene `help` y `example` no vacíos.
2. **Anti-formulario-genérico (§5.3):** `questions_for("ejecutar_tests", stack="node")` devuelve **≤ 4**
   preguntas y **ninguna** cuyo `id` empiece con `deploy_` o `artifact_`.
3. **Contraste del caso 2:** `questions_for("desplegar", stack="node")` **sí** devuelve al menos una `deploy_*`.
4. `questions_for("compilar_validar", ...)` y `questions_for("desplegar", ...)` devuelven **conjuntos de ids distintos**.
5. **R9:** con `known={"build_command": "dotnet build"}`, la pregunta cuyo `autofilled_from == "build_command"` **no aparece**.
6. `depends_on`: con `answers={"needs_docker": "no"}`, `visible_questions` **oculta** las preguntas de registry y tag.
7. `default_answers("ejecutar_tests", "dotnet", "ado")["test_command"] == "dotnet test"`; ídem `node` → `npm test`; `python` → `pytest`.
8. Los 3 stacks × los 9 objetivos = **27 combinaciones**: `questions_for` **nunca lanza** y **nunca** devuelve dos preguntas con el mismo `id`.
9. `needs_inventory` es `True` **solo** para el objetivo `modificar_existente`.
10. El módulo es puro: grep del fuente por `requests`, `urllib`, `os.walk`, `open(` = 0 ocurrencias.
11. **(NUEVO v2)** El `pipeline_kind` de **cada uno** de los 9 objetivos está en
    `{"ci","cd","ci_cd","quality"}` y coincide **exactamente** con la tabla de arriba, comparada como
    `dict` completo (`{g.id: g.pipeline_kind for g in WIZARD_GOALS} == <la tabla>`). *(Sin esto, 4 de
    los 9 quedaban con `kind` indefinido y cada implementador elegía uno distinto.)*

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_schema.py" -q
```
**Criterio BINARIO:** **11 passed, 0 failed**.
**Flag:** ninguna (puro).
**Impacto por runtime:** ninguno (el esquema es idéntico para los 3). Fallback: n/a.
**Trabajo del operador: ninguno.**

---

### F5 — `probe_project`: el Paso 1 se llena solo (P0)

**Objetivo:** una función que **componga** lo que ya existe y devuelva, en una sola llamada, todo lo que
el Paso 1 muestra —incluido el inventario descripto—, degradando por fuente sin romper nunca.

**Valor:** es el "no preguntar nada que Stacky pueda averiguar" del brief, hecho código.

**Archivos a crear:**
- `Stacky Agents/backend/services/pipeline_project_probe.py`
- `Stacky Agents/backend/tests/test_plan294_project_probe.py`

**Ratchets:** los DOS.

**Contrato:**
```python
_MAX_DESCRIBED: int = 25       # tope duro: sin esto, un monorepo con 200 YAML mata el Paso 1

def probe_project(project: str | None = None, *, refresh: bool = False) -> dict:
    """READ-ONLY ABSOLUTO. NUNCA LANZA. Devuelve SIEMPRE este shape (13 claves):
    {
      "ok": True,
      "project": str,
      "provider": "ado" | "gitlab" | "",
      "repository": str,
      "default_branch": str,
      "stack": "python"|"node"|"dotnet"|"",
      "framework": str,          # "" si no se puede afirmar
      "package_manager": str,    # "" si no se puede afirmar
      "build_command": str,      # sugerido por stack; el usuario lo puede corregir
      "test_command": str,
      "variables": [str],        # NOMBRES. JAMAS valores.  (R3 / KPI-5)
      "inventory": {...},        # payload de build_inventory con describe_pipeline aplicado
      "sources": [ {id, available, reason, workaround}, ... ],   # MISMO shape que el 246
    }"""
```

**Reglas de composición (todas reusan; ninguna reimplementa):**
- `stack` ← `services.pipeline_stack_detector.detect_stack` (`:19`). **Ojo con los tipos (C11):** esa
  función toma **`project_root: str`**, y `runtime_paths._active_workspace_root()` (`:66`) devuelve
  **`Path | None`**. La línea exacta es:
  ```python
  root = _active_workspace_root()
  stack = (detect_stack(str(root)) or "") if root else ""
  ```
  **Nunca** `detect_stack(_active_workspace_root())` a secas: con workspace ausente pasa `None` y
  revienta.
- `framework` / `package_manager` / `build_command` / `test_command` ← tabla **cerrada y determinista**
  por stack + presencia de manifiesto (`package.json` con `scripts.test` → `npm test`; `pyproject.toml`
  → `pytest`; `.sln` → `dotnet build`). **Si no hay señal, string vacío. Nunca se inventa.**
- `provider` / `repository` / `default_branch` ← `services.project_context.resolve_project_context` (`:373`).
- `variables` ← solo **nombres**, del servicio de variables existente.
- `inventory` ← `build_inventory(project, refresh=refresh)` y después, **sobre TODAS las entradas**:
  ```python
  for i, entry in enumerate(entradas):
      texto = None
      if i < _MAX_DESCRIBED:
          try:
              texto, _ = get_pipeline_yaml(entry.get("key") or "")
          except Exception:                     # noqa: BLE001
              texto = None
      salida.append(describe_pipeline(entry, texto))   # TODAS pasan por aca
  ```
  > **CORRECCIÓN v2 (C8) — el v1 decía "el resto viaja sin ficha, con `purpose_source == 'sin_datos'`",
  > y eso era imposible.** Una entrada que **no** pasa por `describe_pipeline` es el dict crudo de
  > `make_entry`: **no tiene la clave `purpose_source` en absoluto**, así que el caso 5 no podía pasar y
  > un modelo menor lo habría borrado. La regla correcta: **todas** pasan por `describe_pipeline`; el
  > tope `_MAX_DESCRIBED` limita **cuántas leen el YAML del disco**, que es lo caro. Las que no lo leen
  > reciben `yaml_text=None` y salen con `purpose_source == "sin_datos"`, que es el contrato de §5.5.
- **Cada bloque va en su propio `try/except`.** Que falle uno no puede vaciar los otros; cada fallo
  agrega una entrada a `sources` con `available: False` y `reason` no vacío.

**Tests — casos exactos:**
1. Con todo mockeado en verde, el shape trae **las 13 claves** y `ok is True`.
2. Con `build_inventory` lanzando, `probe_project` **no lanza**, `inventory` viene vacío y hay una entrada en `sources` con `available: False` y `reason` no vacío (**degradación visible**).
3. Con `detect_stack` devolviendo `None`, `stack == ""` y `build_command == ""` (**no se inventa**).
4. **R3:** ningún elemento de `variables` contiene `=` ni `:`.
5. **(reescrito v2 — C8)** Con un inventario de **40** entradas mockeado y `get_pipeline_yaml`
   mockeado para devolver un YAML válido **siempre**: **las 40** entradas traen la clave
   `purpose_source`; **exactamente 25** valen `"plantilla"` y **exactamente 15** valen `"sin_datos"`.
   *(El mock de `get_pipeline_yaml` es obligatorio: sin él no hay archivos en disco, las 40 darían
   `sin_datos` y el caso no probaría el tope.)*
6. `probe_project` **no escribe**: monkeypatchear `builtins.open` para que lance si el modo contiene `"w"` y verificar que igual devuelve el payload.
7. **(reescrito v2 — C19)** `probe_project` **no llama a ningún modelo** (KPI-4), verificado de forma
   **estructural y determinista** en vez de con un mock de un cliente sin nombrar: leer el fuente de
   `services/pipeline_project_probe.py` y asertar **0 ocurrencias** de cada una de estas subcadenas:
   `llm`, `anthropic`, `openai`, `copilot_bridge`, `model_router`, `requests`, `urllib`, `httpx`.
   *(El v1 decía "monkeypatchear el cliente de modelo" sin decir cuál: inejecutable para un modelo
   menor.)*
8. Con un proyecto inexistente, `ok is True` y todo lo no resoluble en vacío (**nunca una excepción**).
9. **(NUEVO v2 — C11)** Con `_active_workspace_root` mockeado devolviendo `None`, `probe_project`
   **no lanza** y devuelve `stack == ""` y `build_command == ""`. **Mitad de contraste del bug de tipos:
   si alguien escribe `detect_stack(_active_workspace_root())`, este caso se pone rojo.**

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_project_probe.py" -q
```
**Criterio BINARIO:** **9 passed, 0 failed**.
**Flag:** se consume bajo `STACKY_PIPELINE_WIZARD_ENABLED` (ON) en F6.
**Impacto por runtime:** ninguno (sin modelo, idéntico para los 3). Fallback: n/a.
**Trabajo del operador: opt-in (default ON).**

---

### F6 — El blueprint del wizard: 4 endpoints delgados (P0)

**Objetivo:** exponer por HTTP lo de F2..F5, **sin lógica de dominio en el blueprint** y **sin un endpoint
de escritura propio**.

**Valor:** conecta el frontend con todo lo anterior reusando el commit y el trigger existentes (mata C7).

**Archivos a crear:**
- `Stacky Agents/backend/api/pipeline_wizard.py`
- `Stacky Agents/backend/tests/test_plan294_wizard_api.py`

**Archivos a editar:**
- `Stacky Agents/backend/api/__init__.py` — registrar el blueprint **sobre `api_bp`**, exactamente como
  se registra `pipeline_inventory`. **NO registrarlo en `app.py`.**

**Ratchets:** los DOS.

**Esqueleto exacto (copiar el patrón de `backend/api/pipeline_inventory.py`):**
```python
"""api/pipeline_wizard.py - Plan 294. Blueprint del asistente guiado.

url_prefix="/pipeline-wizard" -> ruta final /api/pipeline-wizard/...
NO poner url_prefix="/api/..." (daria /api/api/...) y NO registrar en app.py:
se registra sobre api_bp en api/__init__.py.
Guard de la flag PER-REQUEST (abort(404)), nunca gateado en el registro.

DELGADO A PROPOSITO: este modulo no decide nada. Valida el cuerpo, llama a
services/ y serializa. Cero logica de dominio.
NO define endpoint de escritura: el paso 7 reusa /api/pipeline-generator/commit
y /api/ci/<p>/trigger, que ya tienen su HITL. No se crea un tercero.
"""
bp = Blueprint("pipeline_wizard", __name__, url_prefix="/pipeline-wizard")

def _gate():
    # GOTCHA: leer la INSTANCIA (_config.config), no el modulo. getattr del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_WIZARD_ENABLED", False):
        abort(404)

@bp.get("/detect")        # -> probe_project(project, refresh=?)
@bp.post("/questions")    # -> questions_for + visible_questions + default_answers
@bp.post("/draft")        # -> intent_from_dict -> validate_intent -> intent_to_spec -> render
@bp.post("/review")       # -> lint + preflight + variables faltantes (NOMBRES) + describe
```

**Reglas:**
- `/draft` **no hace red**: importa `to_ado_yaml`/`to_gitlab_yaml` de `services.pipeline_renderers` en
  proceso. Si `validate_intent` devuelve motivos → **400** con `{"errors": [motivos]}`.
- `/review` devuelve `warnings` y `blocking` **como dos listas distintas** (el brief lo exige
  explícitamente: advertencias ≠ errores bloqueantes).
- **Ningún endpoint devuelve un valor de variable.** Solo nombres.

**Tests — casos exactos:**
1. **R11 — flag OFF → los 4 endpoints devuelven 404** (parchear `_config.config`, **no** el módulo).
2. Flag ON, `GET /detect` → 200 y trae las 13 claves del probe.
3. `POST /questions` con `{"goal":"ejecutar_tests","stack":"node"}` → 200 y **≤ 4** preguntas.
4. `POST /questions` con `goal` desconocido → **400** con motivo en castellano.
5. `POST /draft` con intención válida → 200 con `{"ado": ..., "gitlab": ...}`; **el YAML devuelto no contiene ningún valor de variable** (R3).
6. `POST /draft` con `goal=""` → **400**.
7. `POST /review` devuelve `warnings` y `blocking` como **claves distintas**, ambas listas.
8. **El blueprint NO expone escritura:** recorrer las reglas del blueprint y asertar que **no hay ninguna
   ruta** cuyo endpoint contenga `commit`, `trigger`, `apply` o `delete`, y que los métodos declarados
   estén todos en `{"GET","POST","HEAD","OPTIONS"}`. (Guarda arquitectónica de C7.)
9. `POST /draft` con un cuerpo que trae `variables: ["K=v"]` → **400** (R3, propagado desde `intent_to_dict`).
10. **(reescrito v2 — C19) KPI-4, verificado de forma determinista:** leer el fuente de
    `api/pipeline_wizard.py` y asertar **0 ocurrencias** de `llm`, `anthropic`, `openai`,
    `copilot_bridge`, `model_router`, `requests`, `urllib`, `httpx`; **y además** que los 4 endpoints
    responden 200/400 en la corrida normal del archivo. *(El v1 pedía "monkeypatchear el cliente de
    modelo" sin nombrar el módulo.)*
11. **(NUEVO v2 — C7) El mapeo paso↔estado es total y legal.** En un solo caso, las tres mitades:
    ```python
    from services.pipeline_intent import WIZARD_STEP_TO_STATE
    from services.pipeline_session import PIPELINE_SESSION_STATES, can_transition

    assert set(WIZARD_STEP_TO_STATE) == {f"p{k}" for k in range(1, 8)}          # total
    assert set(WIZARD_STEP_TO_STATE.values()) <= set(PIPELINE_SESSION_STATES)   # vocabulario canonico
    for k in range(1, 7):                                                        # saltos legales
        o, d = WIZARD_STEP_TO_STATE[f"p{k}"], WIZARD_STEP_TO_STATE[f"p{k+1}"]
        assert o == d or can_transition(o, d), (k, o, d)
    ```
    **Este es el caso que convierte "reusamos la máquina del 279" de promesa en hecho.** Si alguien
    inventa un estado (`"wizard_review"`, `"paso5"`, …), se pone rojo.

**Comandos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_api.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_intent.py" -q
```
**Criterio BINARIO:** `test_plan294_wizard_api.py` → **11 passed, 0 failed**;
`test_plan294_intent.py` → **11 passed** (sin cambios respecto de F3).

> **CORRECCIÓN v2 (C6): `test_flag_wiring.py` NO se corre acá.** El v1 lo ponía como criterio de F6, pero
> en F6 `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` (F7) y `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` todavía no
> tienen consumidor ⇒ el criterio era insatisfacible. Con el `_health_payload` de F1 las 3 quedan
> cableadas desde F1, y el gate se corre en **F1** y se repite en **F9**.

**Flag que la protege:** `STACKY_PIPELINE_WIZARD_ENABLED` (ON).
**Impacto por runtime:** ninguno (los 4 endpoints son deterministas, sin modelo). Fallback: n/a.
**Trabajo del operador: opt-in (default ON).**

---

### F7 — Disparo con variables por corrida, con paridad ADO/GitLab (P0)

**Objetivo:** que el disparo pueda llevar variables de esa corrida, **detrás de una flag OFF**, sin
cambiar la firma del puerto ni el comportamiento de hoy.

**Valor:** cierra GAP-5 y completa el segundo pedido "importantísimo" del operador.

**Archivos a editar:**
- `Stacky Agents/backend/services/ci_provider.py` — el `Protocol CIProvider` pasa a
  `def trigger_pipeline(self, item_ref: ItemRef, ref: str, variables: dict | None = None) -> dict`.
  **`CI_PORT_METHODS` NO cambia** (sigue siendo la 3-tupla congelada). El parámetro es **opcional con
  default `None`**: todo llamador existente sigue funcionando igual.
- `Stacky Agents/backend/services/ado_ci_provider.py` — `AdoCIProvider.trigger_pipeline` acepta
  `variables` y, si no es vacío, agrega al cuerpo del POST:
  `body["variables"] = {k: {"value": str(v), "isSecret": False} for k, v in variables.items()}`
  (forma de la Runs API de ADO). **Si `variables` es `None` o vacío, el cuerpo es byte-idéntico a hoy.**
- `Stacky Agents/backend/services/gitlab_ci_provider.py` — ídem, delegando
  `[{"key": k, "value": str(v)} for k, v in variables.items()]`. Si el delegate no acepta el argumento
  (`TypeError`), **degrada disparando sin variables** y el resultado trae `"variables_applied": False`
  — degradación **visible**, nunca silenciosa.
- `Stacky Agents/backend/api/ci.py` — en `trigger_pipeline_route`, **después** del guard HITL y **antes**
  de la idempotencia:
  ```python
  variables = None
  if getattr(_config.config, "STACKY_PIPELINE_TRIGGER_VARS_ENABLED", False):
      variables = _validar_variables(body.get("variables"))   # dict[str,str], <= 25 claves
  elif body.get("variables"):
      return jsonify({"error": "las variables por corrida estan desactivadas",
                      "kind": "trigger_vars_disabled",
                      "hint": "Activala en Configuracion -> Arnes, categoria DevOps."}), 409
  ```
  y pasarlas: `provider.trigger_pipeline(item_ref, ref_value, variables)`.

**`_validar_variables` (helper nuevo en `backend/api/ci.py`, junto a los otros):** devuelve `None` si el
valor es `None`; **aborta con 400** si no es `dict`, si tiene más de 25 claves, si alguna clave no matchea
`^[A-Za-z_][A-Za-z0-9_]*$`, o si algún valor no es `str`/`int`/`bool`.

**Archivos a crear:**
- `Stacky Agents/backend/tests/test_plan294_trigger_vars.py`

**Ratchets:** los DOS.

**Tests — casos exactos:**
1. **R10 / no-regresión:** flag OFF y **sin** `variables` en el cuerpo → el disparo se comporta exactamente como hoy y el doble recibe `variables is None`.
2. **R11:** flag OFF **con** `variables` en el cuerpo → **409** con `kind == "trigger_vars_disabled"`. (409 y no 403: la ruta existe y la flag padre está ON; es un conflicto de configuración, no un permiso.)
3. Flag ON: el doble de `AdoCIProvider` recibe `variables == {"ENV": "qa"}`.
4. Flag ON, ADO: el cuerpo del POST contiene `variables` con la forma `{"ENV": {"value": "qa", "isSecret": False}}`.
5. Flag ON, GitLab: el delegate recibe la lista `[{"key": "ENV", "value": "qa"}]`.
6. **Paridad:** el mismo cuerpo de request produce un disparo exitoso contra el doble de ADO **y** contra el de GitLab.
7. **Degradación visible:** si el delegate de GitLab lanza `TypeError` por el argumento, el disparo **igual ocurre** y la respuesta trae `variables_applied: False`.
8. 26 claves → **400**.
9. Clave `"MI-VAR"` (con guion) → **400**.
10. **HITL intacto:** sin `confirm: true` → **400**, con o sin variables.
11. **Idempotencia intacta:** dos disparos iguales dentro de 60 s → el segundo devuelve `status: "reused"`.
12. **CERO RED:** el módulo de test monkeypatchea `socket.socket` para que lance, y los 11 casos anteriores igual pasan. **Ningún test dispara una pipeline real.**
13. **(NUEVO v2 — C16) El orden del gate del plan 260 no se movió.** Con la flag de variables **ON** y
    el gate del 260 **bloqueando**, `should_trigger` **no** se llama (`_validar_variables` puede correr
    antes o después, pero el disparo no ocurre). Es el mismo invariante que
    `test_plan260_trigger_gate.py:329-341` espía en su propia corrida; acá se repite **con variables en
    el cuerpo**, que es la combinación nueva que ese test no cubre.

**Comandos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_trigger_vars.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan260_trigger_gate.py" -q
```
Y el test del plan 72 sobre el trigger: **localizarlo con
`grep -rn "trigger_pipeline_route" "Stacky Agents/backend/tests/"` — NO adivinar el nombre del archivo** —
y correrlo con el mismo comando por archivo.

**Criterio BINARIO:** `test_plan294_trigger_vars.py` → **13 passed, 0 failed**.
`test_plan260_trigger_gate.py` → **el mismo conteo que en la línea base de §7.3** (es el guardián del
orden `guard HITL → gate 260 → idempotencia`, y F7 inserta código justo ahí).
El test del plan 72 → **el mismo conteo que antes de la fase**.

> **INVARIANTE DE ORDEN (C16), literal:** el bloque nuevo va **después** del guard de `confirm=True` y
> **después** del gate del plan 260 (`api/ci.py:274`, comentario *"el gate corre DESPUES de tener
> provider.name"*), y **antes** de la llamada a `should_trigger` de `:294`. Ni un renglón antes.

**Flag que la protege:** `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` (**OFF, categoría B**).
**Impacto por runtime:** ninguno (es servidor). Fallback: n/a.
**Trabajo del operador: ninguno** (queda apagada hasta que él la encienda por UI).

> **PROHIBIDO EN LA CORRIDA:** disparar una pipeline real. El humo con credenciales reales queda como
> **PENDIENTE DEL OPERADOR** (§14).

---

### F8 — La primitiva `Stepper` y el modelo puro del wizard (P0)

**Objetivo:** la lógica del wizard vive en `.ts` **puro** y testeable; la primitiva visual de pasos se crea
una sola vez y queda disponible para todo el producto.

**Valor:** sin esto, la lógica termina dentro de un `.tsx` y **no se puede testear** (no hay RTL).

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/ui/stepperModel.ts` (**puro**)
- `Stacky Agents/frontend/src/components/ui/stepperModel.test.ts`
- `Stacky Agents/frontend/src/components/ui/Stepper.tsx` (presentación; consume `stepperModel.ts`)
- `Stacky Agents/frontend/src/components/ui/Stepper.module.css`
- `Stacky Agents/frontend/src/components/devops/pipelineWizardModel.ts` (**puro**)
- `Stacky Agents/frontend/src/components/devops/pipelineWizardModel.test.ts`

**API de `stepperModel.ts` (patrón copiado de `MigratorWizard.logic.ts`, NO el archivo):**
```ts
export interface StepDef { id: string; label: string; optional?: boolean }
export type StepStatus = 'pendiente' | 'actual' | 'completo' | 'bloqueado';
export function stepIndex(steps: StepDef[], id: string): number
export function nextStepId(steps: StepDef[], current: string): string | null
export function prevStepId(steps: StepDef[], current: string): string | null
export function stepStatus(steps: StepDef[], current: string, done: string[], id: string): StepStatus
export function progressLabel(steps: StepDef[], current: string): string   // "3 de 7"
```

**API de `pipelineWizardModel.ts`:**
```ts
export const WIZARD_STEPS: StepDef[]              // 7, ids: p1..p7
export interface WizardState { step: string; answers: Record<string,string>;
  goal: string; runtime: string; intent: Record<string,unknown>; done: string[] }
export function emptyWizardState(): WizardState
export function canAdvance(s: WizardState): { ok: boolean; reason: string }   // reason en CASTELLANO
export function advanceWizard(s: WizardState): WizardState                    // NO avanza si !ok
export function goBack(s: WizardState): WizardState                           // NO pierde answers (R8)
export function buildIntent(s: WizardState, probe: ProbePayload): Record<string,unknown>
export function serializeDraft(s: WizardState): string                        // para localStorage
export function parseDraft(raw: string | null): WizardState | null            // tolera basura

// --- R4 (5.7). Los ids son los REALES de COPILOT_RUNTIMES, no "codex"/"claude"/"copilot" (C4).
export const WIZARD_RUNTIME_IDS = ['claude_code_cli', 'codex_cli', 'github_copilot'] as const;
/** [ADICION ARQUITECTO 2] Devuelve `pedido` o null. JAMAS otro runtime.
 *  Reemplaza a la normalizacion permisiva del copiloto, que cae al primero. */
export function strictRuntime(pedido: string, disponibles: string[]): string | null
/** Alias historico del plan: misma semantica que strictRuntime. */
export function resolveWizardRuntime(pedido: string, disponibles: string[]): string | null

// --- R2: los 4 actos del Paso 7 no se encadenan NUNCA.
export const WIZARD_ACT_IDS = ['guardar_borrador', 'crear_archivo', 'registrar_definicion',
                               'ejecutar'] as const;
/** SIEMPRE null. Existe para que la ausencia de encadenamiento sea TESTEABLE
 *  y no una promesa de prosa: no hay "siguiente acto automatico". */
export function nextActAfter(act: string): null
```

> **`WIZARD_STEP_TO_STATE` en el frontend:** `pipelineWizardModel.ts` **importa `SESSION_STATES`** de
> `./pipelineCopilotModel` y expone `stepState(stepId: string): string`, cuyos valores deben estar en
> `SESSION_STATES`. **No se copia la lista de estados a mano.**

**Tests de `stepperModel.test.ts` (6 casos):** índices correctos; `nextStepId` del último → `null`;
`prevStepId` del primero → `null`; `stepStatus` produce los 4 valores según el caso; `progressLabel`
devuelve `"3 de 7"`; un id inexistente **no lanza**.

**Tests de `pipelineWizardModel.test.ts` — casos exactos:**
1. `WIZARD_STEPS` tiene **7** entradas con ids únicos `p1..p7`.
2. `canAdvance` en `p2` sin `goal` → `{ok:false}` con `reason` **no vacío**.
3. `advanceWizard` con `!ok` **no cambia** el paso.
4. **R8:** `advanceWizard` y después `goBack` conserva `answers` byte a byte.
5. `serializeDraft` → `parseDraft` es round-trip exacto.
6. `parseDraft("{basura")` → `null`, **no lanza**.
7. `parseDraft(null)` → `null`.
8. **R4 (ids reales, C4):** `strictRuntime("codex_cli", ["claude_code_cli","github_copilot"])` devuelve **`null`** (nunca `"claude_code_cli"`).
9. **R4:** `strictRuntime("codex_cli", ["codex_cli","claude_code_cli"])` devuelve `"codex_cli"`.
10. **R4 — el gate duro:** para los 3 pedidos de `WIZARD_RUNTIME_IDS` × los 8 subconjuntos de
    disponibles (**24 combinaciones**, recorridas en un bucle dentro del test), el resultado es
    **`pedido` o `null`**, jamás otro valor. Y `resolveWizardRuntime` devuelve **lo mismo** que
    `strictRuntime` en las 24.
11. `buildIntent` produce un objeto cuyas claves son **exactamente** las 24 de `PipelineIntent`.
12. **R3:** `buildIntent` **nunca** pone en `variables` un string que contenga `=` o `:`.
13. **(NUEVO v2 — C7) El wizard habla el vocabulario del 279.** `WIZARD_STEPS.map(s => stepState(s.id))`
    devuelve sólo valores incluidos en `SESSION_STATES` **importado** de `./pipelineCopilotModel`, y
    `stepState` está definida para los 7 ids. *(Espejo cliente del F6 caso 11.)*
14. **(NUEVO v2 — [ADICIÓN ARQUITECTO 2]) R4, la mitad que faltaba:** leer el fuente de
    `pipelineWizardModel.ts` como texto y asertar que **no contiene** la subcadena
    `normalizeCopilotRuntime`. Esa función (`pipelineCopilotModel.ts:127-130`) **cae a
    `'claude_code_cli'` ante un id desconocido**: rutear la elección del usuario por ahí sería
    exactamente la degradación silenciosa que R4 prohíbe, y los casos 8-10 **no la detectarían** porque
    prueban `strictRuntime`, no el camino real. *(Trampa de auto-gate: no escribas ese identificador ni
    en un comentario del archivo.)*
15. **(NUEVO v2 — R2) Los 4 actos no se encadenan.** `WIZARD_ACT_IDS` tiene **4** ids únicos y
    `nextActAfter(a) === null` para **los 4** y también para un id inventado. *(El v1 sólo defendía R2
    con un grep de dos frases prohibidas en el `.tsx`; esto lo vuelve una propiedad del modelo.)*

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/components/ui/stepperModel.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/devops/pipelineWizardModel.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/devops/__tests__/pipelineCopilotModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** `stepperModel.test.ts` → **6 passed**; `pipelineWizardModel.test.ts` →
**15 passed**; `pipelineCopilotModel.test.ts` → **el mismo conteo que antes de la fase** (no-regresión:
F8 lo importa, no lo modifica); `tsc --noEmit` → **0 errores**.

> **SI `tsc` SE QUEJA DE `STATE_LABELS` O `AVAILABLE_BY_STATE`, PARÁ (C2).** No son exports: usá
> `stateLabel()` y `availableActionIds()`. **Exportarlas para que compile es alcance del plan 279, no de
> este**, y rompería el caso 11 de F0.

> **PROHIBIDO:** escribir un `.test.tsx` que renderice un componente. **RTL y jsdom no están
> instalados**; un test así reporta *"no tests"* y **exit 0** — un falso verde perfecto.

**Flag que la protege:** la UI la gatea `STACKY_PIPELINE_WIZARD_ENABLED` en F9.
**Impacto por runtime:** `resolveWizardRuntime` es exactamente la regla §5.7 para los 3.
Fallback: si el elegido no está, **`null`** y la UI pide una elección nueva; **nunca** un swap.
**Trabajo del operador: ninguno.**

---

### F9 — La sección `crear-pipeline`: los 7 pasos y el Modo avanzado (P0)

**Objetivo:** la pantalla. Wizard por defecto, todo lo actual intacto detrás de "Modo avanzado".

**Valor:** es el entregable visible. KPI-1 y KPI-2 se cumplen o no acá.

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/devops/PipelineWizardSection.tsx`
- `Stacky Agents/frontend/src/components/devops/PipelineWizardSection.module.css`
- `Stacky Agents/frontend/src/pages/__tests__/plan294WizardTab.test.ts` (gate **estructural** por lectura de fuente)

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` — namespace nuevo `PipelineWizard` con
  `detect`, `questions`, `draft`, `review` (4 funciones, patrón idéntico al namespace `PipelineInventory`
  que arranca en `endpoints.ts:5770`).
- `Stacky Agents/frontend/src/pages/DevOpsPage.tsx` — **una** entrada nueva en `DEVOPS_SECTIONS`
  (hoy 18 → **19**), insertada **inmediatamente antes** de la entrada `id: 'pipelines'`
  (`DevOpsPage.tsx:164-169`):
  ```tsx
  {
    id: 'crear-pipeline',
    label: 'Crear pipeline',
    group: 'construir',
    icon: '*',
    summary: 'Un asistente guiado que arma tu pipeline sin que escribas YAML.',
    healthKey: 'pipeline_wizard_enabled',
    gateFlagKey: 'STACKY_PIPELINE_WIZARD_ENABLED',
    gateMessage: 'La seccion Crear pipeline necesita la flag STACKY_PIPELINE_WIZARD_ENABLED (Configuracion -> Arnes, categoria DevOps).',
    render: (ctx) => <PipelineWizardSection ctx={ctx} />,
  },
  ```
- `Stacky Agents/backend/api/devops.py` — la clave `pipeline_wizard_enabled` que consume `healthKey`
  **ya la agregó F1** dentro de **`_health_payload`** (`:28`), junto con las otras dos (§7.2). **F9 no
  vuelve a tocar este archivo**; sólo verifica que la clave siga ahí.
- **`Stacky Agents/backend/services/devops_action_catalog.py`** *(NUEVO v2 — C5, BLOQUEANTE del v1)*:
  1. **`DEVOPS_SECTION_IDS` (`:46-54`) pasa de 18 a 19 ids**, agregando `"crear-pipeline"`
     **inmediatamente antes de `"pipelines"`** (mismo orden que el `.tsx`, para que el diff se lea).
     **Sin esto, `test_devops_action_ratchet.py::test_section_ids_espejan_el_tsx` (`:76-86`) se pone
     ROJO** — compara los dos conjuntos con `==`, y hoy está en **13 passed**.
  2. **[ADICIÓN ARQUITECTO 1]** una entrada nueva en `DEVOPS_ACTION_CATALOG`:
     ```
     id          "devops.pipeline_wizard.open"
     label       "Crear una pipeline paso a paso"
     summary     "Abre el asistente guiado que arma tu pipeline sin que escribas YAML."
     section_id  "crear-pipeline"
     nav_path    "/devops/crear-pipeline"     # OBLIGATORIO f"/devops/{section_id}" — test_nav_path_de_seccion_es_devops_slug (:89)
     effect      "read"                        # NO escribe: sólo navega
     impact      (el que el enum use para "ninguno")   # test_write_declara_impacto (:26) sólo aplica a effect="write"
     flag_key    "STACKY_PIPELINE_WIZARD_ENABLED"      # test_flag_key_existe_en_el_registro (:85)
     health_key  "pipeline_wizard_enabled"             # test_health_key_existe_en_health_payload (:59)
     reach       SIN "palette-run"             # no ejecuta nada; sólo aparece y navega
     phrases     "crear una pipeline", "armar una pipeline", "hacer un pipeline",
                 "no se yaml", "necesito una pipeline"
     ```
     **Valor:** un no técnico escribe *"quiero crear una pipeline"* en la consola en castellano o en la
     paleta y **cae en el wizard**. Cero flags nuevas, cero endpoints nuevos, cero trabajo del operador,
     cero tokens en reposo. Es la puerta de entrada que el §2 dice que falta, hecha con el mecanismo que
     ya existe (plan 267).
     > **ANTES DE ESCRIBIRLA: abrí `devops_action_catalog.py` y copiá el shape de una entrada
     > `effect="read"` que ya exista.** Los campos `impact`, `reach` y `phrases` son vocabularios
     > cerrados del 267; inventar un valor pone rojo el ratchet. **Y revisá
     > `test_frases_no_colisionan_entre_read_y_write` (`:110`): ninguna de las 5 frases puede colisionar
     > con las de una acción de escritura.** Si alguna colisiona, cambiá la frase — **nunca** el test.

**NO se toca:** `Stacky Agents/frontend/src/pages/devopsCockpitShell.ts` (los 5 grupos `:20-26` y
`resolveLandingSection` `:121-151` quedan igual — el plan 275 manda), `PipelineBuilderSection.tsx`,
`PipelineCopilotSection.tsx` (C17), `components/shell/shellNav.ts` / `TAB_META` (C3), ni ninguna de las
18 secciones existentes.

**"Modo avanzado":** un `Tabs` (`frontend/src/components/ui/Tabs.tsx`) con dos ítems, `Guiado` (default)
y `Modo avanzado`. El segundo **no duplica nada**: muestra una lista de las capacidades avanzadas y un
botón por cada una que **cambia la pestaña activa del cockpit** a la sección existente (`pipelines`,
`variables`, `editar-pipeline`, `matriz-entornos`, `pipeline-audit`, `paquete-entrega`,
`inventario-pipelines`, `copiloto-pipelines`), cada uno con una frase de qué se hace ahí.

**Gate estructural (`plan294WizardTab.test.ts`)** — lee los fuentes como texto, patrón ya usado en
`frontend/src/pages/__tests__/DevOpsPage.test.ts`:
1. `DevOpsPage.tsx` contiene `id: 'crear-pipeline'`, `gateFlagKey: 'STACKY_PIPELINE_WIZARD_ENABLED'` y `group: 'construir'`.
2. `DEVOPS_SECTIONS` tiene **19** entradas (contar ocurrencias de la cadena `    id: '` dentro del arreglo).
3. **No-regresión del 275:** `DevOpsPage.tsx` sigue conteniendo `id: 'pipelines'`, `id: 'inventario-pipelines'` y `id: 'copiloto-pipelines'`, y `devopsCockpitShell.ts` sigue declarando **5** grupos.
4. **R7:** `PipelineWizardSection.tsx` contiene `<details` y el bloque del YAML está adentro; ese `<details>` **no** lleva el atributo `open`.
5. **R1:** el total de botones con la clase primaria (`className={styles.primary}`) en `PipelineWizardSection.tsx` es **≤ 7** (uno por paso como máximo).
6. **R1 (KPI-1):** entre los marcadores literales `{/* PASO p1 */}` … `{/* PASO p7 */}` —**que el implementador debe poner**— ningún bloque declara más de **4** ocurrencias de `<Input`/`<Select`/`<Textarea`/`<Checkbox`.
7. **R6:** en `PipelineWizardSection.tsx`, `count("disabled=") <= count("title=")`, y ninguna línea con `disabled=` carece de `title=` en esa misma línea o en la siguiente.
8. **R2:** el `.tsx` contiene los **4** rótulos de acto del Paso 7 como cadenas distintas, y **no** contiene la cadena `Hacer todo` ni la cadena `Crear y ejecutar`.
9. `endpoints.ts` exporta `PipelineWizard` con las 4 funciones, y dentro de ese namespace **no** aparecen las subcadenas `/commit` ni `/trigger`.
10. **Anti-duplicación (C7 del v1):** `PipelineWizardSection.tsx` **no** contiene `to_ado_yaml`, `to_gitlab_yaml` ni un literal de plantilla YAML; el YAML siempre viene del servidor.
11. **(NUEVO v2 — C5) Los DOS registros están sincronizados.** Leer
    `Stacky Agents/backend/services/devops_action_catalog.py` como texto y asertar que contiene
    `"crear-pipeline"`; y que la cantidad de ids de `DEVOPS_SECTION_IDS` es **19**. *(Espejo en el lado
    frontend del ratchet backend; que el implementador lo vea rojo en su propia fase y no recién en el
    commit.)*
12. **(NUEVO v2 — [ADICIÓN ARQUITECTO 1])** El catálogo declara `devops.pipeline_wizard.open` con
    `nav_path` **exactamente** `/devops/crear-pipeline`, `effect` `read`, y **sin** `palette-run` en su
    `reach`. *(Que la puerta de entrada en castellano exista y que **no** sea ejecutable desde la paleta:
    abre una pantalla, no dispara nada.)*
13. **(NUEVO v2 — C6/C15)** `backend/api/devops.py` contiene la cadena `"pipeline_wizard_enabled"`
    dentro de `_health_payload`; sin ella, el `healthKey` de la sección apunta a una clave inexistente y
    la sección **no se renderiza nunca** aunque la flag esté ON.

> **TRAMPA DE AUTO-GATE:** el caso 8 grepea el `.tsx` buscando la **ausencia** de esas dos frases.
> **No las escribas en un comentario del `.tsx`** explicando que están prohibidas. Van en este documento
> (donde ya están) y en el test, nunca en el componente.

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/plan294WizardTab.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/DevOpsPage.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/devopsCockpitShell.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/DevOpsCockpitRegression.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/plan275DevOpsGroupBalance.test.ts
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_devops_action_ratchet.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flag_wiring.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_api.py" -q
```
**Criterio BINARIO:** `plan294WizardTab.test.ts` → **13 passed**; `tsc --noEmit` → **0 errores**;
`test_devops_action_ratchet.py` → **13 passed** (**el mismo número que en la línea base: esta fase es la
que lo puede romper**); `test_flag_wiring.py` → **fallos ≤ línea base**; `DevOpsPage.test.ts`,
`devopsCockpitShell.test.ts`, `DevOpsCockpitRegression.test.ts` y `plan275DevOpsGroupBalance.test.ts` →
**el mismo conteo que antes de la fase**.

> **LOS TRES ARCHIVOS DE COCKPIT SON NO-REGRESIÓN DEL 275, y hay que CORRERLOS, no suponerlos.**
> `plan275DevOpsGroupBalance.test.ts` es, por su propio nombre, un test de **balance de grupos**: pasar
> el grupo `construir` de 2 a 3 secciones puede tener un tope declarado ahí. **Si alguno tiene el número
> 18 (o un tope de secciones por grupo) fijado en una aserción, actualizarlo a 19 es parte de esta fase
> y debe declararse en el mensaje del commit** —y **sólo** el número: prohibido borrar el assert.

**Flag que la protege:** `STACKY_PIPELINE_WIZARD_ENABLED` (ON) para la sección;
`STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` (OFF) deshabilita **solo** el acto 2 del Paso 7, **con `title`
explicando por qué y cómo encenderlo** (R6).
**Impacto por runtime:** el Paso 4 muestra los 3 con su disponibilidad real.
Fallback: el de §5.7 — elección explícita del usuario, **nunca** un swap silencioso.
**Trabajo del operador: opt-in (default ON).**

---

### F10 — El inventario se conecta y se puede ejecutar (P0)

**Objetivo:** cerrar GAP-1, GAP-2, GAP-3 y GAP-4: el inventario mira el proyecto activo, habla castellano
y tiene un botón "Ejecutar" que abre la confirmación HITL.

**Valor:** es, literalmente, lo que el operador marcó como "importantísimo".

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/devops/pipelineInventoryActions.ts` (**puro**)
- `Stacky Agents/frontend/src/components/devops/pipelineInventoryActions.test.ts`
- `Stacky Agents/frontend/src/components/devops/TriggerConfirmDialog.tsx`

**Archivos a editar:**
- `Stacky Agents/frontend/src/components/devops/PipelineInventorySection.tsx`
  - Quitar `void ctx;` (línea 80) y pasar el proyecto: `PipelineInventory.list(ctx.project ?? null, false)`.
  - **Agregar el proyecto a la `queryKey`**: `["pipeline-inventory", ctx.project ?? ""]`. **Sin esto,
    react-query sirve el cache del proyecto anterior y el bug de GAP-1 queda vivo con otra cara.**
  - Mostrar `purpose` y `when_es` bajo el nombre (vienen de F2).
  - Columna de acciones con `[ Ver ]` y `[ Ejecutar ]`, que abre `TriggerConfirmDialog`.
- `Stacky Agents/backend/api/pipeline_inventory.py` — parámetro opcional `?describe=1` que aplica
  `describe_pipeline`. **Sin el parámetro, la respuesta es byte-idéntica a hoy** (R10).
- `Stacky Agents/backend/services/pipeline_inventory.py` — `build_inventory(..., describe: bool = False)`.
  **La clave del cache TTL pasa a incluir `describe`** (`f"{project}|{int(describe)}"`); si no, un pedido
  sin ficha envenena el cache del pedido con ficha.

**API de `pipelineInventoryActions.ts` (pura):**
```ts
export type TriggerGate = { can: boolean; reason: string; fix: string };
export function canTriggerEntry(entry: InventoryEntry, health: DevOpsHealth): TriggerGate
export function triggerConfirmSummary(entry: InventoryEntry, project: string,
                                      branch: string, vars: Record<string,string>): string[]
export function defaultBranchFor(entry: InventoryEntry, probeBranch: string): string

// --- [ADICION ARQUITECTO 3] La linea de mayor riesgo del dialogo HITL deja de ser decorado.
export type DeployWarning =
  | { kind: 'no_despliega'; text: string }
  | { kind: 'despliega'; text: string; environments: string[] }
  | { kind: 'no_se_pudo_determinar'; text: string };
/** Deriva el aviso de despliegue de la ficha del inventario. NUNCA afirma
 *  "no despliega" sin evidencia: sin datos devuelve 'no_se_pudo_determinar'. */
export function deployWarningFor(entry: InventoryEntry): DeployWarning
```

> **[ADICIÓN ARQUITECTO 3] — por qué esta función existe.** El wireframe del v1 (§5.9) imprime
> *"Esta pipeline NO despliega a ningún ambiente"* en la pantalla que **encola una corrida real en el CI
> del operador**, pero **ninguna fase del v1 calculaba ese dato y ningún test lo verificaba**: era texto
> fijo. Afirmar "no despliega" cuando la pipeline **sí** despliega es el peor error posible de todo el
> plan, y es silencioso. Ahora sale de datos reales: el `describe_pipeline` de F2 ya corre
> `profile_pipeline`, del cual `detect_environments` (`pipeline_profiler.py:485`) es un campo. F10
> agrega `environments_es: list[str]` al dict de `describe_pipeline` (clave **aditiva**, misma regla
> R10 que las otras 5) y `deployWarningFor` lo traduce a las **tres** frases honestas:
>
> | Estado | Frase exacta |
> |---|---|
> | `no_despliega` | "Esta pipeline no despliega a ningún ambiente." |
> | `despliega` | "**Ojo: esta pipeline despliega a:** \<ambientes\>." |
> | `no_se_pudo_determinar` | "**No pude determinar si esta pipeline despliega a algún ambiente.** Revisá el archivo antes de ejecutarla." |
>
> **El estado por defecto ante la duda es `no_se_pudo_determinar`, nunca `no_despliega`.**

**Reglas de `canTriggerEntry` (R6: cada `false` trae `reason` **y** `fix`):**

| Situación | `can` | `reason` | `fix` |
|---|---|---|---|
| `health.trigger_enabled === false` | `false` | "El disparo de pipelines está desactivado." | "Activalo en Configuración → Arnés, categoría DevOps." |
| `category === "en_repo_sin_registrar"` | `false` | "Esta pipeline está en el repositorio pero no está registrada en el proveedor." | "Registrala primero desde Llevar a producción." |
| `category === "registrada_sin_archivo"` | `false` | "El proveedor la tiene registrada pero el archivo no está en el repositorio." | "Creá el archivo o corregí la ruta." |
| `category === "registrada_estado_desconocido"` | `true` | "" | "" |
| `category === "registrada+en_repo"` | `true` | "" | "" |

**Tests de `pipelineInventoryActions.test.ts` — casos exactos:**
1. Las **4** categorías de `CATEGORIES` producen un `TriggerGate` definido (ninguna cae en `undefined`).
2. `trigger_enabled === false` → `can:false` con `reason` **y** `fix` no vacíos (R6).
3. `en_repo_sin_registrar` → `can:false` con `fix` no vacío.
4. `registrada+en_repo` → `can:true`.
5. `triggerConfirmSummary` incluye **pipeline, proyecto, proveedor y rama**, en 4 líneas distintas.
6. **R3:** `triggerConfirmSummary` con `vars={"K":"secreto"}` **no** incluye la cadena `"secreto"`; muestra solo el nombre `K`.
7. `defaultBranchFor` usa `entry.default_branch` si existe, y el del probe si no.
8. Ninguna función lanza con un `entry` vacío (`{}`).
9. **Gate estructural:** `PipelineInventorySection.tsx` **ya no contiene** `void ctx;`.
10. **Gate estructural:** `PipelineInventorySection.tsx` **ya no contiene** `PipelineInventory.list(null`.
11. **Gate estructural:** `PipelineInventorySection.tsx` contiene una `queryKey` con **dos** elementos (el proyecto incluido).
12. **(NUEVO v2 — [ADICIÓN ARQUITECTO 3])** `deployWarningFor` con `environments_es: []` devuelve
    `kind: 'no_despliega'`; con `environments_es: ["produccion"]` devuelve `kind: 'despliega'` y su
    `text` **contiene** `produccion`; con la clave **ausente** o `undefined` devuelve
    `kind: 'no_se_pudo_determinar'`. **Las tres mitades en el mismo caso: la tercera es la que impide el
    falso "no despliega".**
13. **(NUEVO v2 — [ADICIÓN ARQUITECTO 3])** `triggerConfirmSummary` **incluye** el `text` de
    `deployWarningFor` como una de sus líneas, para las **tres** variantes. *(Sin esto la función existe
    y el diálogo sigue mintiendo: es el mismo patrón de "código construido y nunca cableado".)*

**Tests backend (agregar a `test_plan294_describe.py`, llevándolo de 11 a 17 casos):**
14. `GET /api/pipeline-inventory/list` **sin** `describe` → respuesta con las 12 claves y **sin** `purpose` (R10, byte-compatible).
15. `GET /api/pipeline-inventory/list?describe=1` → las entradas traen `purpose` y `when_es`.
16. El cache no se cruza: pedir **primero sin** `describe` y **después con** `describe` devuelve fichas en el segundo pedido.
17. **(NUEVO v2 — [ADICIÓN ARQUITECTO 3])** `describe_pipeline` con un YAML que **sí** declara un
    `environment` devuelve `environments_es` **no vacío**; con un YAML de sólo build devuelve
    `environments_es == []`; con `yaml_text=None` devuelve `environments_es == []` **y**
    `purpose_source == "sin_datos"` (que es lo que el frontend usa para distinguir "no despliega" de "no
    sé"). **R10: las 12 claves de `make_entry` siguen intactas** (el dict ahora agrega **6** claves, no 5).
18. **(NUEVO v2 — R10 en las dos direcciones)** `GET /api/pipeline-inventory/list?describe=1` devuelve
    entradas que **conservan las 12 claves originales** con el mismo nombre y el mismo valor que la
    misma llamada **sin** `describe`. *(El caso 14 prueba que sin el parámetro nada cambia; este prueba
    que con el parámetro tampoco se pierde nada. Un `describe_pipeline` que renombrara una clave pasaría
    el 14 y rompería a los planes 247..252 en silencio.)*
19. **(NUEVO v2 — degradación honesta)** Con `STACKY_PIPELINE_PROFILER_ENABLED` en `False` en la
    instancia `_config.config`, `?describe=1` **responde 200** y las entradas traen
    `purpose_source == "sin_datos"` con las 12 claves intactas. **Nunca 500, nunca 404.** *(El
    inventario está gateado por su propia flag; la ficha depende de OTRA flag y su ausencia degrada la
    ficha, no la lista.)*

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/components/devops/pipelineInventoryActions.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_describe.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan246_inventory_endpoint.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan246_inventory_sources.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan247_profiler_core.py" -q
```
**Criterio BINARIO:** `pipelineInventoryActions.test.ts` → **13 passed**; `test_plan294_describe.py` →
**17 passed**; `tsc --noEmit` → **0 errores**; los 2 tests del 246 y
`test_plan247_profiler_core.py` → **el mismo conteo que antes de la fase** (esta fase consume
`detect_environments`, así que el núcleo del perfilador entra como no-regresión).

**Flag que la protege:** `STACKY_PIPELINE_INVENTORY_ENABLED` (ON) para ver;
`STACKY_PIPELINE_TRIGGER_ENABLED` (ya ON) para el botón Ejecutar;
`STACKY_PIPELINE_TRIGGER_VARS_ENABLED` (OFF) para el campo de variables del diálogo, que aparece
deshabilitado **con su `title`** cuando está apagada (R6).
**Impacto por runtime:** ninguno (no interviene un runtime). Fallback: n/a.
**Trabajo del operador: ninguno.**

---

### F11 — Paridad de los 3 runtimes, no-regresión y documentación (P0)

**Objetivo:** demostrar con un test que la elección de runtime **nunca** se degrada sola, y cerrar el plan
sin regresiones y documentado.

**Valor:** es el riel duro del producto y la parte del brief más fácil de romper sin darse cuenta.

**Archivos a crear:**
- `Stacky Agents/backend/services/wizard_runtime.py`:
  ```python
  #: Los ids REALES (C4). Copiados de COPILOT_RUNTIMES (pipelineCopilotModel.ts:106-110)
  #: y del tipo CopilotRuntimeId (:122). NO son "codex"/"claude"/"copilot".
  WIZARD_RUNTIMES: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

  def resolve_wizard_runtime(pedido: str, disponibles: tuple[str, ...]) -> str | None:
      """Devuelve `pedido` si esta disponible, o None. JAMAS otro runtime.
      El None obliga a la UI a pedirle al usuario que elija de nuevo (R4)."""
  ```
  > **CORRECCIÓN v2 (C4) — en el v1 esta tupla era `("codex","claude","copilot")` y el caso 1 exigía que
  > coincidiera *elemento a elemento* con los ids de `COPILOT_RUNTIMES`. Era INSATISFACIBLE**: esos tres
  > strings no existen en el código. Un modelo menor lo "resuelve" cambiando el assert por `len == 3`
  > ⇒ falso verde y dos vocabularios de runtime en el mismo producto. **Se corrigió el vocabulario, no
  > el criterio: el caso 1 sigue exigiendo coincidencia elemento a elemento.**
- `Stacky Agents/backend/tests/test_plan294_runtime_parity.py`

**Archivos a editar:**
- `Stacky Agents/docs/sistema/` — una página corta del asistente, enlazada desde el índice de esa
  carpeta. **Localizar el índice con `ls`, no adivinar el nombre.**

**Ratchets:** registrar `test_plan294_runtime_parity.py` en los DOS.

**Tests — casos exactos:**
1. `WIZARD_RUNTIMES` tiene **3** entradas y coincide, **elemento a elemento y en el mismo orden**, con
   los `id` de `COPILOT_RUNTIMES` de `frontend/src/components/devops/pipelineCopilotModel.ts:106-110`
   (se lee el `.ts` como texto y se extraen los ids con `re.findall(r"id:\s*'([a-z_]+)'", ...)`).
   **Paridad servidor↔cliente verificada, no prometida.** *(Los ids son
   `claude_code_cli`, `codex_cli`, `github_copilot` — ver §5.7.)*
2. **R4, exhaustivo:** para los 3 pedidos × los 8 subconjuntos de `disponibles` = **24 casos** recorridos
   con `itertools`, el resultado es `pedido` o `None`. **Nunca** otro string.
3. `resolve_wizard_runtime("codex_cli", ())` → `None`.
4. `resolve_wizard_runtime("inexistente", ("codex_cli",))` → `None` (**no** cae al primero disponible).
   **Es el contraste directo de `normalizeCopilotRuntime`, que en el mismo escenario devuelve
   `'claude_code_cli'`** (`pipelineCopilotModel.ts:127-130`).
5. **Paridad de capacidad:** `POST /api/pipeline-wizard/draft` con el **mismo** `PipelineIntent` salvo el
   campo `runtime` (`claude_code_cli` / `codex_cli` / `github_copilot`) devuelve **el mismo payload byte
   a byte**. Esto prueba que **nada del wizard está atado a un runtime**.
6. **No-regresión de flags:** las 3 keys siguen en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["devops"]`, en
   `PLAIN_HELP` **y en `_health_payload`** (las 3 patas que las mantienen vivas y cableadas).
7. **Paridad de ratchets:** contar las entradas que matchean `tests/test_plan294_` en
   `run_harness_tests.ps1` y en `run_harness_tests.sh` y asertar que son **iguales** (y **9** en cada
   uno). **Medido el 2026-08-02: `.ps1` tiene 772 entradas, `.sh` tiene 836, diferencia 64, y
   `_PS1_LAG_MAX = 64` (`test_plan259_ratchet_script_parity.py:46`). Estamos EXACTAMENTE en el límite:
   registrar 9 en `.sh` y 8 en `.ps1` pone rojo el gate.**
8. **(NUEVO v2 — C4) Vocabulario único en todo el backend del plan:** grep sobre los fuentes de
   `services/wizard_runtime.py`, `services/pipeline_intent.py` y `api/pipeline_wizard.py` de las
   cadenas `'codex'`, `'claude'` y `'copilot'` **entre comillas y solas** = **0 ocurrencias**.
   *(Impide que los ids inventados del v1 reaparezcan por copiado.)*
9. **(NUEVO v2 — C7) El mapeo del wizard sobrevive al cierre:** re-asertar aquí, como no-regresión de
   cierre, las 3 mitades del caso 11 de F6 (`WIZARD_STEP_TO_STATE` total, vocabulario canónico, saltos
   legales). *(Es el invariante más fácil de romper en las últimas fases, cuando se toca la UI.)*

**Comandos de cierre — los 9 archivos backend del plan, uno por uno:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_baseline.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_describe.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_intent.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_schema.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_project_probe.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_api.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_trigger_vars.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_runtime_parity.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan259_ratchet_script_parity.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_devops_action_ratchet.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flag_wiring.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan260_trigger_gate.py" -q
```

**Criterio BINARIO — los conteos exactos de cierre (C14: el v1 decía "el conteo declarado en su fase" y
`test_plan294_describe.py` tenía DOS conteos declarados):**

| Archivo | Conteo exigido al cerrar F11 |
|---|---|
| `test_plan294_baseline.py` | **11 passed, 0 failed** |
| `test_plan294_flags.py` | **9 passed, 0 failed** |
| `test_plan294_describe.py` | **17 passed, 0 failed** (11 de F2 + 3 de F10 + 3 de la ADICIÓN 3) |
| `test_plan294_intent.py` | **11 passed, 0 failed** |
| `test_plan294_wizard_schema.py` | **11 passed, 0 failed** |
| `test_plan294_project_probe.py` | **9 passed, 0 failed** |
| `test_plan294_wizard_api.py` | **11 passed, 0 failed** |
| `test_plan294_trigger_vars.py` | **13 passed, 0 failed** |
| `test_plan294_runtime_parity.py` | **9 passed, 0 failed** |
| `test_plan259_ratchet_script_parity.py` | **verde** |
| `test_devops_action_ratchet.py` | **13 passed** (igual a la línea base) |
| Los 5 guardianes del arnés + `test_plan260_trigger_gate.py` | **delta ≤ 0** contra §7.3 |

**Total backend del plan: 101 casos en 9 archivos.**

**Flag que la protege:** ninguna nueva.
**Impacto por runtime:** es la fase que lo prueba, para los 3.
**Trabajo del operador: ninguno.**

---

### 8.12 Cobertura de pruebas exigida por el operador — dónde vive cada caso

| Caso pedido | Fase | Archivo de test |
|---|---|---|
| Proyecto Node / Python / .NET | F4 (caso 8: 27 combinaciones), F3 (caso 5) | `test_plan294_wizard_schema.py`, `test_plan294_intent.py` |
| Azure DevOps y GitLab | F7 (caso 6), F3 (caso 6) | `test_plan294_trigger_vars.py`, `test_plan294_intent.py` |
| Pipeline de build y tests | F4 (casos 2, 7) | `test_plan294_wizard_schema.py` |
| Pipeline con artefactos | F4 (caso 3) | `test_plan294_wizard_schema.py` |
| Pipeline de despliegue | F4 (casos 3, 6) | `test_plan294_wizard_schema.py` |
| Edición de pipeline existente | F3 (caso 8), F4 (caso 9) | `test_plan294_intent.py`, `test_plan294_wizard_schema.py` |
| Reanudación de borrador | F8 (casos 5, 6, 7) | `pipelineWizardModel.test.ts` |
| Cambio de runtime | F8 (casos 8-10), F11 (caso 2) | `pipelineWizardModel.test.ts`, `test_plan294_runtime_parity.py` |
| Runtime no disponible | F8 (caso 8), F11 (caso 3) | idem |
| **Ausencia de fallback silencioso** | F8 (caso 10, 24 combinaciones), F11 (caso 2, 24 casos) | idem |
| Error de lint | F6 (caso 7) | `test_plan294_wizard_api.py` |
| Variable faltante | F6 (caso 7), F5 (caso 4) | `test_plan294_wizard_api.py`, `test_plan294_project_probe.py` |
| Secreto faltante | F6 (caso 7) | `test_plan294_wizard_api.py` |
| Preflight con advertencias vs. bloqueante | F6 (caso 7: `warnings` y `blocking` separados) | `test_plan294_wizard_api.py` |
| Confirmación y cancelación | F9 (caso 8), F10 (caso 5) | `plan294WizardTab.test.ts`, `pipelineInventoryActions.test.ts` |
| Protección contra doble submit | F7 (caso 11: idempotencia de 60 s, ya existente) | `test_plan294_trigger_vars.py` |
| Fallo de commit | F6 (caso 8: el wizard no commitea; el fallo lo maneja el endpoint del 73) | `test_plan294_wizard_api.py` |
| Fallo de trigger | F7 (caso 7: degradación visible) | `test_plan294_trigger_vars.py` |
| **No exposición de secretos** | F3 (3, 4), F5 (4), F6 (5, 9), F10 (6) | 4 archivos |
| **Inventario CON pipelines en el repo** | F2 (casos 2, 6) | `test_plan294_describe.py` |
| **Inventario SIN pipelines (estado vacío)** | F5 (caso 2) | `test_plan294_project_probe.py` |
| **Inventario con credenciales caídas (degradación visible)** | F5 (caso 2: `sources` con `available:False` y `reason`) | `test_plan294_project_probe.py` |
| **Disparo con la flag de variables OFF** | F7 (caso 2: **409**, no 403 — la ruta existe y la flag padre está ON) | `test_plan294_trigger_vars.py` |
| **(v2) La pipeline que SÍ despliega, antes de disparar** | F10 (casos 12, 13, 17) | `pipelineInventoryActions.test.ts`, `test_plan294_describe.py` |
| **(v2) El wizard usa la máquina de estados del 279** | F6 (caso 11), F8 (caso 13), F11 (caso 9) | `test_plan294_wizard_api.py`, `pipelineWizardModel.test.ts`, `test_plan294_runtime_parity.py` |
| **(v2) La sección nueva no rompe el catálogo de acciones** | F9 (casos 11, 12) + `test_devops_action_ratchet.py` corrido en F1, F9 y F11 | `plan294WizardTab.test.ts`, `test_devops_action_ratchet.py` |
| **(v2) Las 3 flags están CABLEADAS, no sólo registradas** | F1 (casos 8, 9) + `test_flag_wiring.py` en F1 y F9 | `test_plan294_flags.py`, `test_flag_wiring.py` |
| **(v2) El runtime elegido no cae al normalizador permisivo** | F8 (caso 14), F11 (caso 4) | `pipelineWizardModel.test.ts`, `test_plan294_runtime_parity.py` |
| **(v2) Los 4 actos del Paso 7 no se encadenan** | F8 (caso 15) + F9 (caso 8) | `pipelineWizardModel.test.ts`, `plan294WizardTab.test.ts` |
| **(v2) El perfilador apagado degrada la ficha, no la lista** | F10 (caso 19) | `test_plan294_describe.py` |

---

## 9. Fuera de scope de este plan

| Ítem | Prioridad del brief | Por qué queda afuera | Plan futuro que lo tomaría |
|---|---|---|---|
| Historial de generaciones del wizard | P1 | Necesita persistencia nueva (tabla o archivo); este plan no agrega esquema | Plan de "bitácora del asistente" |
| Recuperación de sesión **entre dispositivos** | P1 | El borrador de F8 es local (localStorage). Cross-device exige servidor | Idem anterior |
| Variables y secretos guiados **con escritura al proveedor** | P1 | El wizard **lee** nombres y **enlaza** a la sección Variables existente; escribir variables en el ADO/GitLab del operador es otra capacidad (B) | Plan de "caja fuerte guiada" |
| Diff visual al editar una pipeline existente | P1 | El objetivo `modificar_existente` **sí** entra (F3/F4), pero el render del diff lado a lado es una pieza de UI propia y grande | Plan de "diff de pipelines" |
| Recomendaciones avanzadas / plantillas aprendidas por proyecto | P2 | Requiere memoria por proyecto y evaluación; sale del alcance de una corrida | Plan de "plantillas aprendidas" |
| Aprobaciones y rollback de despliegue | P2 | Ya hay superficie propia (`DeploymentsSection`, `rollbackReadiness.ts`); duplicarla sería exactamente el error que este plan combate | Plan de "aprobaciones" |
| Métricas de conversión y abandono del wizard | P2 | Necesita telemetría de UI que hoy no existe | Plan de "telemetría del cockpit" |
| **C11 / GAP-10 — `DevOpsActionConsole` pide rutas sin `/api`** | bug vivo | Es un defecto del 267/279, no del wizard. Meterlo acá mezcla dos fronteras y ensucia el diff | Plan de corrección del 267: `DevOpsActionConsole.tsx:117,130,153` y `CommandPalette.tsx:96` |
| **C7 / GAP-9 — unificar el HITL duplicado de Builder y Copiloto** | deuda | Este plan **no agrega** un tercero (usa los existentes), pero **fusionar** los dos que ya hay es refactor de dos features ajenas | Plan de "un solo HITL de escritura de pipelines" |
| El copiloto nunca avanza estado (`advance`/`question` con 0 llamadores) | deuda | El wizard le da un consumidor a la máquina de estados, pero arreglar el panel del copiloto es alcance del 279 | Plan de cierre del 279 |
| Eliminar el código muerto del shell (`devopsShell.ts`: `countCapabilities`, `buildAwareness`) | deuda | Sin relación con el wizard | Limpieza del 239/275 |
| Instalar RTL + jsdom | infraestructura | Es un cambio de infraestructura del frontend con 20 tests hoy inertes esperándolo. Decisión del operador | Plan de "el frontend se puede testear" |

---

## 10. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación (concreta y verificable) |
|---|---|---|---|---|
| **R-1** | **El implementador reescribe el inventario o el trigger** en vez de reusarlos | **Alta** | Alto | El aviso al inicio del documento + §3.1 + F0 casos 1-5 y 9 (grep anti-segundo-renderizador). **Si F0 no está hecho, no se empieza F2** |
| **R-2** | El ratchet de paridad se pone rojo por registrar distinta cantidad en `.ps1` y `.sh` | **Alta** | Medio | Está **exactamente** en el límite (772 vs 836 = 64 = `_PS1_LAG_MAX`). F11 caso 7 lo verifica y `test_plan259_ratchet_script_parity.py` es criterio de cierre |
| **R-3** | Un gate por grep se invalida solo porque el implementador escribe la cadena prohibida en un comentario | Media | Alto (falso verde) | Trampas declaradas **en el cuerpo de F0 y F9** con la redacción alternativa exacta |
| **R-4** | `DevOpsPage.test.ts` tiene el número 18 fijado y se pone rojo al agregar la sección 19 | Media | Bajo | F9 lo declara: actualizar el número **es parte de la fase** y va en el mensaje del commit |
| **R-5** | El cache del inventario se envenena al agregar `describe` | Media | Medio | F10: la clave de cache incluye `describe`; caso 14 lo verifica |
| **R-6** | Un test toca la red o la BD real del operador | Baja | **Muy alto** | F7 caso 12 (monkeypatch de `socket.socket`), F5 caso 6 (no escribe), F2 caso 10. Regla del repo: base SQLite fresca por archivo |
| **R-7** | La sesión paralela corre los números de línea y los anclajes no coinciden | **Alta** | Bajo | Todo anclaje crítico trae además el **símbolo**; el documento declara que **manda el símbolo** |
| **R-8** | Alguien "arregla" el default del trigger poniéndolo OFF para cumplir el brief al pie de la letra | Media | Alto | §7.1 lo prohíbe por escrito, con la evidencia de la decisión del operador del 2026-07-05 |
| **R-9** | `test_flag_wiring.py` rojo en F1 y se interpreta como daño propio | Media | Bajo | F1 lo declara explícitamente: se corre en F6, no en F1 |
| **R-10** | El Paso 1 se vuelve lento en un monorepo con 200 YAML | Media | Medio | `_MAX_DESCRIBED = 25` en F5, verificado por el caso 5 |
| **R-11** | Se escribe un `.test.tsx` con RTL y reporta "no tests" con exit 0 | Media | Alto (falso verde) | Prohibido explícitamente en F8; §3.4 documenta los 20 archivos hoy inertes |
| **R-12** | La tabla `_WHEN_ES` se consulta con `[]` y un `kind` nuevo del proveedor la hace lanzar | Media | Medio | F2 obliga a `.get()` y el caso 11 lo prueba con un `kind` fuera de la tabla |
| **R-13** *(v2, C5)* | **La sección 19 tumba el commit por un ratchet que el v1 no nombraba** | **Alta** | **Alto** | `test_devops_action_ratchet.py` está **verde (13 passed)** y **registrado en los DOS ratchets** ⇒ es trampa de COMMIT, no de edición. F9 edita `devops_action_catalog.py` y el archivo se corre en **F1** (línea base), **F9** (la fase que lo puede romper) y **F11** (cierre) |
| **R-14** *(v2, C6)* | Una flag registrada sin consumidor deja `test_flag_wiring.py` rojo para siempre | **Alta** | Alto | Las 3 claves entran a `_health_payload` en **F1**; el caso 9 de F1 es la mitad de contraste. El gate se corre en F1 y F9, **nunca** en F6 |
| **R-15** *(v2, C4)* | **Dos vocabularios de runtime conviviendo** (`codex` vs `codex_cli`) y un test debilitado para taparlo | **Alta** | **Alto (falso verde)** | Los ids reales están fijados en §5.7 y repetidos en F3 caso 11, F8 casos 8-10, F11 casos 1-4; **F11 caso 8 grepea los inventados y exige 0 ocurrencias** |
| **R-16** *(v2, C7)* | Se construye una segunda máquina de estados y "reusamos el 279" queda en prosa | **Alta** | Medio | El mapeo es un dict exportado (`WIZARD_STEP_TO_STATE`) y **F6 caso 11 + F8 caso 13 + F11 caso 9** lo asertan contra `TRANSITIONS`. **Aparece en el DoD** |
| **R-17** *(v2, ADICIÓN 3)* | **El diálogo HITL afirma "no despliega" sobre una pipeline que despliega a producción** | Media | **Muy alto** | `deployWarningFor` tiene **tres** estados y el default ante la duda es `no_se_pudo_determinar`; F10 casos 12, 13 y 17 lo prueban en las tres variantes |
| **R-18** *(v2, C1)* | Alguien "consolida" `TriggerPipelineSection` creyendo el dato falso del v1 (un solo montaje) y rompe 3 superficies vivas | Media | Alto | **F0 caso 10 congela los 4 montajes reales** y nace verde |

---

## 11. Glosario

| Término | Significado en este plan |
|---|---|
| **Inventario** | La lista reconciliada de pipelines del proyecto: las registradas en el proveedor + los YAML del repo. Producida por `build_inventory` (plan 246) |
| **Las 4 categorías** | `registrada+en_repo`, `registrada_sin_archivo`, `en_repo_sin_registrar`, `registrada_estado_desconocido` |
| **`PipelineIntent`** | El objeto declarativo que el wizard llena y que se traduce a `PipelineSpec`. Nunca lleva valores de secreto |
| **Ficha en castellano** | La frase determinista de `build_purpose_template` (≤200 caracteres, sin modelo) más etapas, disparador y artefactos |
| **Modo avanzado** | El conjunto intacto de las 8 secciones actuales de pipelines, alcanzable desde el wizard |
| **Fallback de plataforma** | Perder una capacidad opcional avisando, **manteniendo** el runtime elegido. Permitido |
| **Degradación silenciosa** | Cambiar el runtime elegido por otro sin avisar. **Prohibido** (§5.7, R4) |
| **Los 4 actos** | Guardar borrador / crear archivo + commit / registrar definición / ejecutar. Botones distintos |
| **Los 8 guardianes** | Los 8 lugares que hay que tocar por cada flag nueva (§7.2) |
| **Categoría (B)** | La excepción que permite que una flag nazca OFF: escribe en un sistema real del operador |
| **Mitad de contraste** | Un test que **falla hoy** y pasa al final. Sin él, un gate no prueba nada |
| **Delta ≤ 0** | Criterio de no-regresión sobre un archivo con rojos de fábrica: no se exige verde, se exige no empeorar |
| **Los 3 runtimes** | `claude_code_cli`, `codex_cli`, `github_copilot`. **Son los ids REALES** de `COPILOT_RUNTIMES` (`pipelineCopilotModel.ts:106-110`). `"codex"`, `"claude"` y `"copilot"` **no existen en el código** y están prohibidos en todo el código nuevo (F11 caso 8) |
| **Los DOS registros de una sección** | `DEVOPS_SECTIONS` en `frontend/src/pages/DevOpsPage.tsx:151` **y** `DEVOPS_SECTION_IDS` en `backend/services/devops_action_catalog.py:46`. Falta uno ⇒ ratchet rojo en el **commit** |
| **Trampa de COMMIT** | Un gate que no rompe la edición ni la fase, pero está registrado en `run_harness_tests.*` y tumba el commit. En este plan: `test_devops_action_ratchet.py` y `test_plan259_ratchet_script_parity.py` |
| **Degradación de la ficha vs. de la lista** | Si el perfilador falla o está apagado, la **ficha** cae a `purpose_source="sin_datos"`; la **lista** del inventario sigue respondiendo 200 con sus 12 claves. Nunca al revés |
| **"No despliega" vs. "no sé"** | `environments_es == []` con `purpose_source == "plantilla"` = **no despliega** (afirmación). `purpose_source == "sin_datos"` = **no se pudo determinar** (ignorancia). Confundirlos antes de encolar una corrida real es el peor error del plan |

---

## 12. Orden de implementación

```
F0 -> F1 -> F2 -> F3 -> F4 -> F5 -> F6 -> F7 -> F8 -> F9 -> F10 -> F11
```

**Puntos de corte seguros** (si hay que parar, se para acá y el sistema queda íntegro y útil):
- **Después de F2:** el bug vivo del perfilador (GAP-6) está cerrado y el inventario ya puede hablar
  castellano. Valor real, cero UI, cero riesgo.
- **Después de F7:** todo el backend está listo y testeado; la UI vieja sigue funcionando igual.
- **Después de F10:** el objetivo del operador está cumplido de punta a punta.

> **NO hay punto de corte entre F8 y F9 (v2, C5).** F9 es la fase que toca los **dos** registros de
> sección. Parar con `DevOpsPage.tsx` editado y `devops_action_catalog.py` sin editar deja el árbol
> **imposible de commitear** (`test_devops_action_ratchet.py` rojo, y `--no-verify` está prohibido).
> **F9 se termina o no se empieza.**

---

## 13. Definition of Done

- [ ] Los **9** archivos de test backend del plan corren **uno por uno** con
      `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q` y dan **exactamente** el
      conteo de la tabla de cierre de F11 (**101 casos en total**). **Ningún `-k`. Ningún `pytest tests`
      entero.**
- [ ] Los **4** archivos de test frontend corren con `npx vitest run <ruta>` y dan el conteo declarado
      (**6 + 15 + 13 + 13 = 47 casos**). **Ninguno renderiza React.**
- [ ] `npx tsc --noEmit` en `Stacky Agents/frontend` → **0 errores**.
- [ ] Los **9** archivos de test backend están registrados en **`run_harness_tests.ps1` Y en
      `run_harness_tests.sh`**, con la **misma cantidad** en los dos, y
      `test_plan259_ratchet_script_parity.py` está **verde**.
- [ ] Las **3** flags nuevas tienen sus **8 guardianes** (§7.2) y son editables desde
      Configuración → Arnés, categoría DevOps.
- [ ] `STACKY_PIPELINE_WIZARD_ENABLED` es **ON**; `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` y
      `STACKY_PIPELINE_TRIGGER_VARS_ENABLED` son **OFF** y **no declaran `default=`** en su `FlagSpec`.
- [ ] `STACKY_PIPELINE_TRIGGER_ENABLED` **sigue siendo ON**. Nadie la tocó.
- [ ] Los 5 guardianes del arnés (`test_harness_flags.py`, `test_harness_flags_help.py`,
      `test_flag_wiring.py`, `test_harness_flags_requires.py`, `test_harness_flags_bounds.py`) tienen
      **fallos ≤ la línea base de §7.3**.
- [ ] **(v2, C6)** Las **3** flags nuevas aparecen como literal en `backend/api/devops.py`
      (`_health_payload`) y `test_flag_wiring.py` está en **delta ≤ 0**. Ninguna nació inerte.
- [ ] **(v2, C5)** `Stacky Agents/backend/services/devops_action_catalog.py` tiene **19** ids en
      `DEVOPS_SECTION_IDS` y `test_devops_action_ratchet.py` da **13 passed** (igual que la línea base).
- [ ] **(v2, ADICIÓN 1)** El catálogo declara `devops.pipeline_wizard.open` con `effect="read"`,
      `nav_path="/devops/crear-pipeline"` y **sin `palette-run`** en su `reach`.
- [ ] **(v2, C7)** `WIZARD_STEP_TO_STATE` cubre `p1..p7`, sus valores están en
      `PIPELINE_SESSION_STATES` y **todos** los saltos consecutivos son legales según `TRANSITIONS`
      (F6 caso 11, F8 caso 13, F11 caso 9). **La reutilización del 279 está probada, no prometida.**
- [ ] **(v2, C4)** El vocabulario de runtime es **`claude_code_cli` / `codex_cli` / `github_copilot`** en
      todo el código nuevo, y `grep` de `'codex'`, `'claude'`, `'copilot'` sueltos en los 3 módulos
      backend del wizard = **0** (F11 caso 8).
- [ ] **(v2, ADICIÓN 2)** `pipelineWizardModel.ts` **no contiene** `normalizeCopilotRuntime` (F8 caso 14).
- [ ] **(v2, ADICIÓN 3)** El diálogo de disparo muestra el aviso de despliegue **calculado**, con sus
      **tres** estados, y nunca afirma "no despliega" sin evidencia (F10 casos 12, 13, 17).
- [ ] `test_plan246_*` (4 archivos) y `test_plan247_endpoint.py` dan **el mismo conteo que antes del
      plan**. Cero regresión sobre el inventario y el perfilador.
- [ ] `DEVOPS_SECTIONS` tiene **19** entradas y las **18** anteriores siguen ahí con el mismo `id`.
- [ ] `devopsCockpitShell.ts` sigue con **5** grupos y `resolveLandingSection` sin tocar (plan 275 intacto).
- [ ] **KPI-1:** ningún paso del wizard expone más de 4 campos (F9 caso 6).
- [ ] **KPI-2:** el wizard llega al Paso 6 sin exigir ninguna decisión técnica (F4 casos 2 y 7 + F5 caso 1).
- [ ] **KPI-3:** hay un botón "Ejecutar" en la fila del inventario (F10).
- [ ] **KPI-4:** ninguna fase agrega loop, daemon, barrido, polling ni prefetch. Verificado por los casos
      "no llama a modelo" de F2, F5 y F6.
- [ ] **KPI-5:** ningún test encuentra un valor de secreto en payload, preview, resumen o log.
- [ ] **R4:** los 24 casos de `resolveWizardRuntime` (F8) y los 24 de `resolve_wizard_runtime` (F11)
      devuelven `pedido` o `null`/`None`. **Nunca otro runtime.**
- [ ] **Ninguna pipeline real fue disparada durante la implementación.** El humo con credenciales reales
      queda como **PENDIENTE DEL OPERADOR** y está anotado como tal.
- [ ] Ninguna capacidad existente fue eliminada. Las 8 secciones de pipelines siguen accesibles desde
      "Modo avanzado".

---

## 14. Pendientes del operador (no se hacen en la corrida)

1. **Humo real del disparo**: ejecutar una pipeline de verdad desde el inventario, contra su ADO y contra
   su GitLab, con credenciales reales. **Prohibido durante la implementación.**
2. **Humo real del commit**: encender `STACKY_PIPELINE_WIZARD_COMMIT_ENABLED` y dejar que el wizard cree
   `azure-pipelines.yml` en una rama descartable.
3. **Decidir sobre `STACKY_PIPELINE_TRIGGER_VARS_ENABLED`**: nace OFF; encenderla es su decisión.
4. **Decidir sobre C11 / GAP-10** (`DevOpsActionConsole` sin `/api`): es un bug vivo que este plan
   **documenta pero no toca**. Si lo quiere cerrado, es un plan de dos líneas.
