# Plan 294 — El pipeline se crea sin saber YAML: wizard guiado para no técnicos

**Estado:** PROPUESTO v1 · **Fecha:** 2026-08-02 · **Rama al escribir:** `docs/plan-279`
**Autor:** StackyArchitectaUltraEficientCode (perfil normal)
**Alcance:** P0 completo + inventario automático de pipelines + disparo desde Stacky. P1 restante y P2 en §9.

> **Todo anclaje `archivo:línea` de este documento se verificó abriendo el archivo el 2026-08-02.**
> Hay una **sesión paralela viva** en este árbol. Donde un número de línea puede correrse, el documento
> da además el **símbolo**. **Si el número no coincide, manda el símbolo.**

> **AVISO AL IMPLEMENTADOR — LEER ANTES DE ESCRIBIR UNA LÍNEA.**
> Este plan **construye muy poco código nuevo de dominio**. La capacidad central que el operador pidió
> como "importantísima" —**detectar automáticamente las pipelines que ya existen**— **YA ESTÁ
> CONSTRUIDA Y VERDE** (plan 246, `backend/services/pipeline_inventory.py`, 765 líneas). El disparo de
> pipelines **también existe** (plan 72/95, `backend/api/ci.py`) y su flag **ya está encendida**.
> Lo que falta no es capacidad: es **secuencia, lenguaje llano y cableado**.
> **Si en cualquier fase te encontrás escribiendo un barrido de repo, un cliente HTTP de ADO/GitLab, un
> renderizador de YAML o una máquina de estados de sesión: PARÁ. Ya existe. Volvé a §3.**

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
| **KPI-3** | Clics desde "quiero disparar esta pipeline" hasta la confirmación | **hoy: inalcanzable desde Inventario.** `TriggerPipelineSection` solo se monta dentro del constructor (`PipelineBuilderSection.tsx:745`) | **1 clic** desde la fila del inventario |
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
  `devopsCockpitShell.ts:20-26` intactos.
- **Plan 279** (`docs/279_PLAN_EL_COPILOTO_DE_PIPELINES_UN_SOLO_HILO_CONVERSACIONAL.md`, IMPLEMENTADO
  F0..F9) construyó la máquina de estados de 8 pasos (`backend/services/pipeline_session.py:15-37`) y el
  panel del copiloto. **Pero el copiloto no avanza el estado desde el frontend**: `PipelineCopilot.advance`
  (`frontend/src/api/endpoints.ts:5117`) y `PipelineCopilot.question` (`:5123`) tienen **0 llamadores**
  —grep en `frontend/src` devuelve solo la definición—, y las acciones del paso se renderizan como
  `<span>` sin `onClick` (`PipelineCopilotSection.tsx:315-326`). Este plan **reusa esa máquina de estados
  como columna vertebral del wizard** y le pone, por fin, un consumidor.
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
| **Disparo de pipeline (HITL)** | `backend/api/ci.py`, `POST /api/ci/<project>/trigger` (`trigger_pipeline_route`); rechaza con 400 sin `confirm=True`; idempotencia de 60 s (`should_trigger`) | **COMPLETO** | El wizard y el inventario lo llaman; **no se reimplementa** |
| Preview del disparo (read-only) | `backend/api/ci.py`, `GET /api/ci/<project>/trigger-preview` (`trigger_preview_route`) | **COMPLETO** | Es la pantalla de confirmación del disparo |
| Monitoreo de la corrida | `backend/api/ci.py`, `GET /api/ci/<project>/pipeline/<pipeline_id>` (`monitor_pipeline_route`), con cap real de polls (`_MAX_ACTIVE_POLLS_PER_PIPELINE = 5`) | **COMPLETO** | Seguimiento post-disparo |
| Bitácora de corridas | `backend/api/ci.py`, `GET /api/ci/runs` (`list_ci_runs_route`) + `backend/services/ci_run_ledger.py` | **COMPLETO** | Historial del Paso 7 |
| Trigger por proveedor | `backend/services/ado_ci_provider.py`, `AdoCIProvider.trigger_pipeline`; `backend/services/gitlab_ci_provider.py`, `GitLabCIProvider.trigger_pipeline` | **COMPLETO para la rama**; **SIN variables por corrida** (ver §3.3, GAP-5) | F7 agrega variables **sin cambiar la firma existente** |
| Listado de definiciones del proveedor | `ado_ci_provider.py`, `AdoCIProvider.list_pipeline_definitions`; `gitlab_ci_provider.py`, `GitLabCIProvider.list_pipeline_definitions`; ADO además en `backend/services/ado_pipeline_definitions.py`, `list_definitions` (tope de hidratación y contador `meta["calls"]` real) | **COMPLETO en los dos proveedores** | Se consume vía `build_inventory` |
| Render `PipelineSpec` → YAML | `backend/services/pipeline_renderers.py` (`to_ado_yaml`, `to_gitlab_yaml`) vía `backend/api/pipeline_generator.py`, `POST /api/pipeline-generator/preview` | **COMPLETO** | Es el motor del Paso 5. **No se escribe otro renderizador** |
| Escritura al repo real | `backend/services/repo_writer.py`, `RepoWriter.commit_file` + `get_repo_writer`; implementaciones en `backend/services/ado_provider.py:146` (`commit_file`) y `backend/services/gitlab_provider.py:853` (`commit_file`) | **COMPLETO EN LOS DOS PROVEEDORES** | Es el Paso 7. **La paridad ADO/GitLab de escritura YA está resuelta** |
| Gate de secretos antes de escribir | `backend/api/pipeline_generator.py`, llamada a `evaluar_gate_secretos` (`backend/services/ci_env_gate.py`) | **COMPLETO** | Se hereda gratis al reusar el endpoint |
| Máquina de estados de 8 pasos | `backend/services/pipeline_session.py`: `PIPELINE_SESSION_STATES`, `TRANSITIONS`, `TERMINAL_STATES`, `can_transition`, `advance`, `next_question`, `undo_hint`, `PIPELINE_FILENAME` | **COMPLETO** (plan 279) | **Es la máquina de estados del wizard.** No se escribe otra |
| Espejo de la máquina en el frontend | `frontend/src/components/devops/pipelineCopilotModel.ts`: `SESSION_STATES`, `STATE_LABELS`, `AVAILABLE_BY_STATE`, `needsOperatorConfirmation`, `mustShowUndoHint`, `COPILOT_RUNTIMES`, `normalizeCopilotRuntime` | **COMPLETO**, con test (`devops/__tests__/pipelineCopilotModel.test.ts`) | Se importa desde el modelo del wizard |
| Detección de stack | `backend/services/pipeline_stack_detector.py`, `detect_stack(root) -> "python" \| "node" \| "dotnet" \| None`; endpoint `GET /api/devops/detect-stack` (`backend/api/devops.py`, `detect_stack_route`) | **EXISTE PERO ES DELGADO** (ver GAP-7) | F5 lo **compone**, no lo reemplaza |
| Lint determinista | `POST /api/devops/pipeline-lint/validate` y `/explain`; clientes ya tipados en `frontend/src/api/endpoints.ts` (`DevOps.pipelineLintValidate`, `DevOps.pipelineLintExplain`) | **COMPLETO** | Paso 6 |
| Preflight | `POST /api/devops/preflight/check`; cliente `DevOps.preflightCheck` | **COMPLETO** | Paso 6 |
| Variables / secretos | `DevOpsVariables.list` / `.create` / `.remove` (`endpoints.ts`, namespace `DevOpsVariables`) | **COMPLETO** | Paso 3 y Paso 6 (por NOMBRE, nunca por valor) |
| Selector de runtime | `frontend/src/components/AgentRuntimeSelector` (usado en `PipelineCopilotSection.tsx:208`) + `COPILOT_RUNTIMES` (3 entradas) | **COMPLETO** | Paso 4 |
| Primitiva de pestañas | `frontend/src/components/ui/Tabs.tsx`, `export default function Tabs` | **COMPLETO** | Se usa para "Guiado / Modo avanzado" |

### 3.2 Flags que ya existen en esta zona (default REAL leído del `os.getenv`, no del comentario)

| Flag | Default REAL | Evidencia | Qué gatea |
|---|---|---|---|
| `STACKY_PIPELINE_INVENTORY_ENABLED` | **ON** | `backend/config.py:1648-1650`, `os.getenv(..., "true").strip().lower() == "true"`; `FlagSpec` en `backend/services/harness_flags.py:6169` con `default=True`; curada en `backend/tests/test_harness_flags.py:603` | Inventario |
| `STACKY_PIPELINE_TRIGGER_ENABLED` | **ON** | `backend/config.py:1731-1733`, `os.getenv(..., "true").lower() in ("1","true","yes")`; `FlagSpec` en `harness_flags.py:3783` con `default=True` | Disparo + monitoreo |
| `STACKY_PIPELINE_GENERATOR_ENABLED` | **ON** | `backend/config.py:1738-1740`; `FlagSpec` `harness_flags.py:3799` con `default=True` | Preview + commit del generador |
| `STACKY_PIPELINE_PROFILER_ENABLED` | **ON** | `backend/config.py` (bloque plan 247, `os.getenv(..., "true")`); `FlagSpec` `harness_flags.py:3816` | Perfilador |
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
| **GAP-4** | **El disparo está sepultado.** `TriggerPipelineSection` **no tiene pestaña**: su único punto de montaje en toda la app es dentro del constructor gráfico, debajo del preview de YAML, del lint, del preflight y del botón de commit | `frontend/src/components/devops/PipelineBuilderSection.tsx:745`. Grep de `TriggerPipelineSection` en `frontend/src` no devuelve ningún otro montaje |
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
- **No hay primitiva `Stepper`.** Grep de `TAB_META` en `frontend/src` = 0; no existe
  `frontend/src/components/ui/Stepper.tsx`. Hay 4 wizards ad-hoc; el único con lógica pura reaprovechable
  como **molde** es `frontend/src/components/MigratorWizard.logic.ts` (`nextStep`, `stepIndex`,
  `stepLabel`), pero su tipo de paso es un union literal cerrado del migrador: **se copia el patrón, no
  el archivo**.
- **Mono-operador sin auth real.** En este producto **403 = flag apagada, NO permiso**. El guard estándar
  de la casa es `abort(404)` per-request leyendo **la instancia** `_config.config` (nunca el módulo: el
  módulo devuelve el default y mata el branch OFF, con lo cual el test de flag-off pasaría en falso).

---

## 4. Crítica priorizada

| # | Problema | Evidencia | Impacto en el usuario | Sev. | Causa raíz | Solución de este plan |
|---|---|---|---|---|---|---|
| **C1** | Sobrecarga cognitiva: 28 campos y ~22 botones simultáneos, sin orden | `PipelineBuilderSection.tsx` (845 líneas, 30 `useState`), `BlockProperties.tsx:43-247` | El no técnico no sabe por dónde empezar; abandona | **P0** | La pantalla expone el **modelo de datos** (`PipelineSpec` con bloques y propiedades) en vez de la **tarea** | Wizard de 7 pasos, **una decisión principal por pantalla**; el `PipelineSpec` se arma solo (F3, F4, F9) |
| **C2** | Fragmentación: 8 pestañas hablan de pipelines y ninguna se habla con otra | `DevOpsPage.tsx:151-348` (18 secciones; 8 sobre pipelines, repartidas en `construir` y `gobernar`) | Para una tarea hay que recorrer 3-4 pestañas y recordar el estado a mano | **P0** | Cada plan agregó su pestaña; nadie agregó el hilo | **Una** sección nueva (`crear-pipeline`) que orquesta las existentes; las 18 quedan como están (F9) |
| **C3** | El disparo no es alcanzable donde el usuario lo espera | `PipelineBuilderSection.tsx:745`; `PipelineInventorySection.tsx:172` | Ve la pipeline en el inventario y no puede ejecutarla; tiene que ir al constructor gráfico y scrollear | **P0** | El disparo se construyó como hijo del constructor, no como capacidad del proyecto | Botón "Ejecutar" en la fila del inventario → pantalla de confirmación (F10) |
| **C4** | El inventario ignora el proyecto activo | `PipelineInventorySection.tsx:80,85` | En multi-proyecto ve el inventario equivocado y no se entera | **P0** | `void ctx;` y `null` literal | Se pasa el proyecto del contexto y se lo agrega a la `queryKey` (F10) |
| **C5** | El inventario es técnico: 7 columnas, ninguna en castellano llano | `PipelineInventorySection.tsx:163-181` | "azure-pipelines.yml / ci / main" no le dice nada a quien no sabe DevOps | **P0** | El perfilador, que ya genera la frase, nunca se conectó al inventario | `describe_pipeline` casa inventario + perfilador (F2) |
| **C6** | Bug vivo: perfilar por id de pipeline devuelve 501 siempre | `api/pipeline_profiler.py:32,39`; `def get_pipeline_yaml` no existe en `backend/` | La ficha "qué hace" no se puede pedir por pipeline; hay que mandar el YAML entero a mano | **P0** | Un plan (247) programó contra una función que el plan hermano (246) nunca expuso | F2 crea `get_pipeline_yaml` en el inventario |
| **C7** | Duplicación: constructor y copiloto escriben por la misma ruta con dos HITL distintos | `CommitPipelineModal.tsx:50` y el binding `devops.pipeline_new.commit` de `devopsActionBindings.ts`, ambos a `POST /api/pipeline-generator/commit` | Dos pantallas de confirmación distintas para el mismo acto; el usuario no sabe cuál es la buena | **P1** | Dos planes construyeron su propio HITL sobre el mismo endpoint | El wizard **no crea un tercero**: reusa el endpoint y expone **una sola** pantalla de confirmación (F6 caso 8, F9) |
| **C8** | Acciones deshabilitadas sin explicación | Las acciones del paso son `<span>` sin `onClick` (`PipelineCopilotSection.tsx:315-326`); avisos de flags faltantes en `:249-265` | El usuario ve algo que parece un botón y no pasa nada | **P1** | Se desactivó el `onClick` sin desactivar el elemento ni explicar | Regla dura §6-R6 + gates de F9 y F10: **nada deshabilitado sin motivo visible y sin salida** |
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
    runtime: str = ""                  # "codex" | "claude" | "copilot"
    constraints: tuple[str, ...] = ()
    proposed_path: str = ""            # de pipeline_session.PIPELINE_FILENAME
    existing_pipeline_key: str = ""    # clave del inventario (pipeline_inventory.identity_key)
    free_text: str = ""
```

- `existing_pipeline_key` es **exactamente** la `key` que produce `identity_key` en
  `pipeline_inventory.py` (`"<provider>::<ruta normalizada>"`). Así el Paso 2 "modificar existente"
  referencia el inventario **sin inventar identificadores**.
- `intent_to_spec(intent) -> dict` traduce a lo que `dict_to_spec` de
  `backend/services/pipeline_spec.py` ya sabe leer. **Es el único puente**; el wizard no renderiza YAML.
- **Invariante KPI-5, verificado por test:** `variables` y `required_secrets` contienen **nombres**.
  `intent_to_dict` **debe** lanzar `ValueError` si algún elemento contiene `=` o `:` — es exactamente la
  forma en que un valor se cuela en una lista de nombres.

### 5.5 Contrato del inventario enriquecido (F2)

`build_inventory` **no se toca en su lógica**. Se agregan **dos** funciones nuevas al mismo módulo:

```python
def get_pipeline_yaml(pipeline_key: str, project: str | None = None) -> tuple[str, str]:
    """Devuelve (yaml_text, source_path) para una `key` del inventario.
    Cierra GAP-6: es la funcion que api/pipeline_profiler.py:32 ya importa y que no existia.
    Solo lee del WORKSPACE local (nunca de red). Si la key no resuelve a un archivo
    legible dentro del workspace, lanza KeyError (el endpoint lo mapea a 404)."""

def describe_pipeline(entry: dict, yaml_text: str | None) -> dict:
    """Enriquece UNA entrada del inventario con la ficha en castellano.
    Claves que AGREGA (nunca quita ni renombra las 12 existentes):
      purpose        str   frase de build_purpose_template (<=200 chars, plantilla, SIN modelo)
      purpose_source str   "plantilla" | "sin_datos"
      stages_es      list[str]
      when_es        str   'cuando alguien sube algo a main'
      artifacts_es   list[str]
    Si yaml_text es None o no parsea: purpose_source="sin_datos" y el resto vacio.
    NUNCA lanza."""
```

**Compatibilidad hacia atrás dura:** el shape de 12 claves de `make_entry` es un contrato congelado que
consumen los planes 247..252. `describe_pipeline` **agrega** claves; el gate de F2 verifica que las 12
originales siguen presentes y con el mismo nombre.

### 5.6 Máquina de estados del wizard

**Se reusa `backend/services/pipeline_session.py` tal cual.** El mapeo paso↔estado es:

| Paso UI | Estado de `PIPELINE_SESSION_STATES` |
|---|---|
| P1, P2, P3, P4 | `discovery` |
| P5 | `draft` |
| P6 | `review` (o `secrets` si faltan variables) |
| P7 | `confirm` → `committed` \| `failed` |

`can_transition` y `advance` **ya validan** las transiciones legales (`TRANSITIONS`), y
`TERMINAL_STATES = ("committed", "failed")` ya impide avanzar desde un terminal. **No se escribe otra
máquina.** El frontend espeja con lo que ya está en `pipelineCopilotModel.ts` (`SESSION_STATES`,
`STATE_LABELS`, `AVAILABLE_BY_STATE`, `needsOperatorConfirmation`, `mustShowUndoHint`).

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
|     · Esta pipeline NO despliega a ningun ambiente                        |
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
- **Aterrizaje:** `resolveLandingSection` (`devopsCockpitShell.ts:121-151`) **no se toca**. Su último
  recurso sigue siendo `'pipelines'` (`devopsCockpitShell.ts:150`). Cambiarlo sería una regresión del
  plan 275.

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
código; una flag registrada pero sin `getattr(_config.config, "<KEY>", ...)` en producción se pone roja.

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
```

**Criterio de no-regresión de todo el plan:** el conteo de fallos de cada uno de esos 5 archivos
**después** del plan debe ser **≤** el de la línea base. No se exige verde absoluto: se exige
**delta ≤ 0**.

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
7. **`test_flags_294_registradas` (NACE ROJO)** — las 3 keys nuevas están en `{s.key for s in FLAG_REGISTRY}`. **Contraste de F1.**
8. **`test_docstring_de_ci_no_miente` (NACE ROJO)** — leer `backend/api/ci.py` como texto y asertar que **no** contiene la subcadena `default OFF`. **Contraste de F1.**
9. `test_no_hay_segundo_renderizador` — grep en `backend/services/` de `def to_ado_yaml` devuelve **exactamente 1** archivo (`pipeline_renderers.py`). Guarda anti-duplicación permanente.

> **TRAMPA — leerla o el gate se autoinvalida.** El caso 8 grepea la cadena `default OFF` sobre
> `backend/api/ci.py`. **No escribas esa cadena en un comentario nuevo de ese archivo** al corregirlo,
> ni siquiera para explicar la corrección. Redactá el comentario como *"default ON (operador
> 2026-07-05)"*. El caso 9 grepea `backend/services/`, no `docs/`: este documento no lo afecta.

**Comando exacto:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_baseline.py" -q
```

**Criterio de aceptación BINARIO:** al terminar F0, la corrida da **6 passed, 3 failed** (fallan los casos
6, 7 y 8). Al terminar F2, da **9 passed, 0 failed**. **Si al crear F0 da 9 passed, el test no prueba
nada y hay que arreglarlo antes de seguir.**

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
| `Stacky Agents/deployment/harness_defaults.env` | regenerar con `deployment/export_harness_defaults.py` |
| `Stacky Agents/backend/api/ci.py` | docstring de módulo (línea 11): reemplazar la frase del default por *"Flag STACKY_PIPELINE_TRIGGER_ENABLED: default ON (operador 2026-07-05), leida per-request."* |

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

**Ratchets:** registrar `test_plan294_flags.py` en los DOS (`.ps1` con comillas y coma, `.sh` sin nada).

**Comandos exactos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_help.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_requires.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_harness_flags_bounds.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_baseline.py" -q
```

**Criterio BINARIO:** `test_plan294_flags.py` → **7 passed, 0 failed**. Los 4 archivos de arnés →
**fallos ≤ línea base de §7.3**. `test_plan294_baseline.py` → los casos 7 y 8 pasan, queda **1 failed**
(el caso 6, que cierra F2) → **8 passed, 1 failed**.

> **NOTA IMPORTANTE:** `test_flag_wiring.py` exigirá un **consumidor real** de cada flag. En F1 todavía no
> existe. **Correr `test_flag_wiring.py` recién al cerrar F6** (que crea los consumidores), no en F1.
> Si el implementador lo corre en F1 y lo ve rojo, **no es daño**: es la fase equivocada.

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
**9 passed, 0 failed**. Los 3 archivos del 246/247 → **el mismo conteo que antes de la fase**.

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

@dataclass(frozen=True)
class PipelineIntent: ...                                # los 24 campos de 5.4

def intent_from_dict(d: dict | None) -> PipelineIntent   # tolerante: campo desconocido se IGNORA
def intent_to_dict(i: PipelineIntent) -> dict            # lanza ValueError si un "nombre" trae "=" o ":"
def intent_to_spec(i: PipelineIntent) -> dict            # dict que services.pipeline_spec.dict_to_spec acepta
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

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_intent.py" -q
```
**Criterio BINARIO:** **9 passed, 0 failed**.
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

WIZARD_GOALS: tuple[WizardGoal, ...] = (...)      # los 9 de 5.3, EN ESE ORDEN

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

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_schema.py" -q
```
**Criterio BINARIO:** **10 passed, 0 failed**.
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
- `stack` ← `services.pipeline_stack_detector.detect_stack(_active_workspace_root())`.
- `framework` / `package_manager` / `build_command` / `test_command` ← tabla **cerrada y determinista**
  por stack + presencia de manifiesto (`package.json` con `scripts.test` → `npm test`; `pyproject.toml`
  → `pytest`; `.sln` → `dotnet build`). **Si no hay señal, string vacío. Nunca se inventa.**
- `provider` / `repository` / `default_branch` ← `services.project_context.resolve_project_context`.
- `variables` ← solo **nombres**, del servicio de variables existente.
- `inventory` ← `build_inventory(project, refresh=refresh)` y, por cada una de las **primeras
  `_MAX_DESCRIBED`** entradas, `describe_pipeline(entry, get_pipeline_yaml(entry["key"]))` envuelto en
  `try/except`. El resto viaja sin ficha, con `purpose_source == "sin_datos"`.
- **Cada bloque va en su propio `try/except`.** Que falle uno no puede vaciar los otros; cada fallo
  agrega una entrada a `sources` con `available: False` y `reason` no vacío.

**Tests — casos exactos:**
1. Con todo mockeado en verde, el shape trae **las 13 claves** y `ok is True`.
2. Con `build_inventory` lanzando, `probe_project` **no lanza**, `inventory` viene vacío y hay una entrada en `sources` con `available: False` y `reason` no vacío (**degradación visible**).
3. Con `detect_stack` devolviendo `None`, `stack == ""` y `build_command == ""` (**no se inventa**).
4. **R3:** ningún elemento de `variables` contiene `=` ni `:`.
5. Con un inventario de 40 entradas mockeado, **exactamente 25** traen `purpose_source == "plantilla"` y las otras 15 `"sin_datos"`.
6. `probe_project` **no escribe**: monkeypatchear `builtins.open` para que lance si el modo contiene `"w"` y verificar que igual devuelve el payload.
7. `probe_project` **no llama a ningún modelo** (KPI-4): monkeypatchear el cliente de modelo para que lance y verificar que igual pasa.
8. Con un proyecto inexistente, `ok is True` y todo lo no resoluble en vacío (**nunca una excepción**).

**Comando:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_project_probe.py" -q
```
**Criterio BINARIO:** **8 passed, 0 failed**.
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
10. **KPI-4:** monkeypatchear el cliente de modelo para que lance y verificar que los 4 endpoints siguen respondiendo 200/400 (ninguno llama a un modelo).

**Comandos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_api.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_flag_wiring.py" -q
```
**Criterio BINARIO:** `test_plan294_wizard_api.py` → **10 passed, 0 failed**.
`test_flag_wiring.py` → **fallos ≤ línea base de §7.3** (acá ya hay consumidor real de la flag del wizard).

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

**Comandos:**
```
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_trigger_vars.py" -q
```
Y el test del plan 72 sobre el trigger: **localizarlo con
`grep -rn "trigger_pipeline_route" "Stacky Agents/backend/tests/"` — NO adivinar el nombre del archivo** —
y correrlo con el mismo comando por archivo.

**Criterio BINARIO:** `test_plan294_trigger_vars.py` → **12 passed, 0 failed**. El test del plan 72 →
**el mismo conteo que antes de la fase**.

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
export function resolveWizardRuntime(pedido: string, disponibles: string[]): string | null   // 5.7
```

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
8. **R4:** `resolveWizardRuntime("codex", ["claude","copilot"])` devuelve **`null`** (nunca `"claude"`).
9. **R4:** `resolveWizardRuntime("codex", ["codex","claude"])` devuelve `"codex"`.
10. **R4 — el gate duro:** para los 3 pedidos × los 8 subconjuntos de disponibles (**24 combinaciones**,
    recorridas en un bucle dentro del test), el resultado es **`pedido` o `null`**, jamás otro valor.
11. `buildIntent` produce un objeto cuyas claves son **exactamente** las 24 de `PipelineIntent`.
12. **R3:** `buildIntent` **nunca** pone en `variables` un string que contenga `=` o `:`.

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/components/ui/stepperModel.test.ts
cd "Stacky Agents/frontend" && npx vitest run src/components/devops/pipelineWizardModel.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
```
**Criterio BINARIO:** 6 passed + 12 passed, y `tsc --noEmit` con **0 errores**.

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
- `Stacky Agents/backend/api/devops.py` — agregar `pipeline_wizard_enabled` al payload de
  `GET /api/devops/health` (es la clave que consume `healthKey`). **Aditivo, no cambia nada existente.**

**NO se toca:** `devopsCockpitShell.ts` (los 5 grupos y `resolveLandingSection` quedan igual — el plan 275
manda), `PipelineBuilderSection.tsx`, ni ninguna de las 18 secciones existentes.

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
10. **Anti-duplicación (C7):** `PipelineWizardSection.tsx` **no** contiene `to_ado_yaml`, `to_gitlab_yaml` ni un literal de plantilla YAML; el YAML siempre viene del servidor.

> **TRAMPA DE AUTO-GATE:** el caso 8 grepea el `.tsx` buscando la **ausencia** de esas dos frases.
> **No las escribas en un comentario del `.tsx`** explicando que están prohibidas. Van en este documento
> (donde ya están) y en el test, nunca en el componente.

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/plan294WizardTab.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
cd "Stacky Agents/frontend" && npx vitest run src/pages/__tests__/DevOpsPage.test.ts
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_wizard_api.py" -q
```
**Criterio BINARIO:** `plan294WizardTab.test.ts` → **10 passed**; `tsc --noEmit` → **0 errores**;
`DevOpsPage.test.ts` → verde. **Si ese archivo tiene el número 18 fijado en una aserción, actualizarlo a
19 es parte de esta fase y debe declararse en el mensaje del commit.**

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
```

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

**Tests backend (agregar a `test_plan294_describe.py`, llevándolo de 11 a 14 casos):**
12. `GET /api/pipeline-inventory/list` **sin** `describe` → respuesta con las 12 claves y **sin** `purpose` (R10, byte-compatible).
13. `GET /api/pipeline-inventory/list?describe=1` → las entradas traen `purpose` y `when_es`.
14. El cache no se cruza: pedir **primero sin** `describe` y **después con** `describe` devuelve fichas en el segundo pedido.

**Comandos:**
```
cd "Stacky Agents/frontend" && npx vitest run src/components/devops/pipelineInventoryActions.test.ts
cd "Stacky Agents/frontend" && npx tsc --noEmit
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan294_describe.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan246_inventory_endpoint.py" -q
"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "Stacky Agents/backend/tests/test_plan246_inventory_sources.py" -q
```
**Criterio BINARIO:** `pipelineInventoryActions.test.ts` → **11 passed**; `test_plan294_describe.py` →
**14 passed**; `tsc --noEmit` → **0 errores**; los 2 tests del 246 → **el mismo conteo que antes de la
fase**.

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
  WIZARD_RUNTIMES: tuple[str, ...] = ("codex", "claude", "copilot")

  def resolve_wizard_runtime(pedido: str, disponibles: tuple[str, ...]) -> str | None:
      """Devuelve `pedido` si esta disponible, o None. JAMAS otro runtime.
      El None obliga a la UI a pedirle al usuario que elija de nuevo (R4)."""
  ```
- `Stacky Agents/backend/tests/test_plan294_runtime_parity.py`

**Archivos a editar:**
- `Stacky Agents/docs/sistema/` — una página corta del asistente, enlazada desde el índice de esa
  carpeta. **Localizar el índice con `ls`, no adivinar el nombre.**

**Ratchets:** registrar `test_plan294_runtime_parity.py` en los DOS.

**Tests — casos exactos:**
1. `WIZARD_RUNTIMES` tiene **3** entradas y coincide, elemento a elemento, con los `id` de
   `COPILOT_RUNTIMES` de `frontend/src/components/devops/pipelineCopilotModel.ts` (se lee el `.ts` como
   texto y se extraen los ids). **Paridad servidor↔cliente verificada, no prometida.**
2. **R4, exhaustivo:** para los 3 pedidos × los 8 subconjuntos de `disponibles` = **24 casos** recorridos
   con `itertools`, el resultado es `pedido` o `None`. **Nunca** otro string.
3. `resolve_wizard_runtime("codex", ())` → `None`.
4. `resolve_wizard_runtime("inexistente", ("codex",))` → `None` (**no** cae al primero disponible).
5. **Paridad de capacidad:** `POST /api/pipeline-wizard/draft` con el **mismo** `PipelineIntent` salvo el
   campo `runtime` (`codex` / `claude` / `copilot`) devuelve **el mismo payload byte a byte**. Esto prueba
   que **nada del wizard está atado a un runtime**.
6. **No-regresión de flags:** las 3 keys siguen en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["devops"]` y en `PLAIN_HELP`.
7. **Paridad de ratchets:** contar las entradas que matchean `tests/test_plan294_` en
   `run_harness_tests.ps1` y en `run_harness_tests.sh` y asertar que son **iguales**. (Guarda contra el
   `_PS1_LAG_MAX = 64` que está exactamente en el límite.)

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
```

**Criterio BINARIO:** `test_plan294_runtime_parity.py` → **7 passed, 0 failed**; los otros 8 archivos con
el conteo declarado en su fase; `test_plan259_ratchet_script_parity.py` **verde**; los 5 guardianes del
arnés con **delta ≤ 0** contra §7.3.

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

---

## 13. Definition of Done

- [ ] Los **9** archivos de test backend del plan corren **uno por uno** con
      `"Stacky Agents/backend/.venv/Scripts/python.exe" -m pytest "<ruta>" -q` y dan el conteo declarado
      en su fase. **Ningún `-k`. Ningún `pytest tests` entero.**
- [ ] Los **4** archivos de test frontend corren con `npx vitest run <ruta>` y dan el conteo declarado.
      **Ninguno renderiza React.**
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
