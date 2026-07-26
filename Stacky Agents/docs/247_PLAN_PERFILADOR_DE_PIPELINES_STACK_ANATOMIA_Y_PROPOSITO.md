# Plan 247 — Perfilador de pipelines: qué es, qué hace y con qué está hecha cada pipeline

> Estado: **v1 · PROPUESTO** (2026-07-26). Pipeline: **proponer ✓ [este paso]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: Claude Opus 5 (1M context), rol `StackyArchitectaUltraEficientCode`. **Ningún anclaje de este documento está escrito de memoria: cada `archivo:símbolo` fue abierto el 2026-07-26** (tabla en §2.5; lo no verificado, en §2.6).
> Serie: **"Mago de las Pipelines" (246–252)**. Este es el **247**. Dependencia: `246 → **247** → {248, 250, 251} → 252`.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro. **El perfil completo es 100% determinista y NO usa LLM** — la paridad de runtimes es trivial por construcción (§3.1).
> Flag: **`STACKY_PIPELINE_PROFILER_ENABLED`, default ON**. Fases: **6 (F0..F5)**.

---

## 0. La tesis del plan (leer esto antes que nada)

Stacky sabe **renderizar** pipelines (Plan 73), **lintearlas** (Plan 186), **auditarlas
semánticamente** (Plan 243 F3) y **dispararlas** (Plan 72). Lo que no sabe hacer es lo primero
que hace cualquier humano frente a un `azure-pipelines.yml` ajeno: **leerlo y decir qué es**.

Hoy, si el operador pregunta *"¿qué hace `cd-deploy-test.yml`?"*, la única respuesta que Stacky
puede dar es *"tiene 11 tareas y 0 marcas de lint"*. La respuesta que necesita es:

> *"Compila .NET Framework y despliega a un servidor TEST self-hosted. **No corre un solo test.**
> Publica 4 artefactos, consume 2. Toca el entorno `Test`. Corre sobre dos pools distintos:
> `windows-2022` hosted para el build y `TEST-Server` self-hosted para el deploy."*

Todo eso está **literalmente escrito** en el YAML y es extraíble sin una sola llamada a un LLM.
Y el dato más caro del párrafo —**"no corre un solo test"**— es una **ausencia**: nadie la
produce hoy, porque el lint y las reglas semánticas sólo miran lo que **está**, nunca lo que
**falta**.

> **La tesis:** un perfilador determinista de ausencias y presencias, con evidencia por campo,
> es el sustrato que le falta a los 5 planes que vienen detrás (248 audita, 250 edita, 251
> resuelve entornos, 252 empaqueta). Y como no usa LLM en su camino default, **no puede alucinar
> y corre idéntico en los 3 runtimes**.

---

## 1. Objetivo y valor

**Objetivo.** Dado un YAML de pipeline (venga del registro del Plan 246 o suelto), producir un
**perfil estructurado, determinista y auditable**: stack tecnológico, anatomía de fases,
artefactos publicados/consumidos, entornos tocados, agentes/pools, disparadores, y un propósito
en 1 línea legible por humanos. **Cada campo lleva la evidencia que lo sostiene y un nivel de
confianza; lo que no se puede determinar vale `desconocido`, nunca una suposición.**

### KPI / impacto medible

| # | KPI | Medición binaria | Hoy |
|---|---|---|---|
| K1 | **Anatomía de fases** de una pipeline sin leer el YAML | El perfil de los 9 golden reproduce la tabla de expectativas de §F5 (72 aserciones exactas) | 0 — no existe el concepto |
| K2 | **Ausencias detectadas** | `cd-deploy-test.yml` → `phases["test"].value is False`; `ci-batch.yml` → `phases["publish_artifact"].value is False` | 0 — el lint sólo mira lo presente |
| K3 | **Cero alucinación** | Ningún campo del perfil de los 9 golden tiene `value` no vacío con `confidence == "desconocido"` (test `test_sin_valor_sin_confianza`) | N/A |
| K4 | **Cero tokens en el camino default** | `test_perfil_no_llama_al_llm` monkeypatchea `call_llm` para que explote y perfila los 9 golden | N/A |
| K5 | **Perfilar lo que no se entiende** | `ci-batch.yml` (matrix) y `bootstrap-server-environment.yml` (17 `${{ }}`) devuelven perfil completo + `not_understood` poblado, sin excepción | Hoy `parse_ado_yaml` los tolera pero no declara nada al operador |
| K6 | **Latencia** | Perfilar los 9 golden < 1 s en total (`test_perfil_los_nueve_en_menos_de_un_segundo`) | N/A |

**Valor concreto para el operador:** pasar de *"acá hay 40 pipelines, andá leyéndolas"* a
*"estas 12 compilan sin testear, estas 3 despliegan a prod, estas 5 corren en el self-hosted"*.
El 248 va a poder emitir hallazgos de seguridad **sobre este perfil** en vez de re-parsear.

---

## 2. Evidencia (todo verificado por lectura directa el 2026-07-26)

### 2.1 El gap exacto: `detect_stack` NO perfila pipelines, perfila **repos**

`backend/services/pipeline_stack_detector.py` (55 líneas, leído entero) hace algo **distinto** de
lo que este plan necesita, y confundirlos sería el error de diseño más caro del plan:

| | `detect_stack(project_root)` (Plan 97 F2) | `profile_pipeline(yaml_text)` (este plan) |
|---|---|---|
| Entrada | una **ruta de disco** | el **texto del YAML** |
| Método | `os.walk` + `os.path.exists` sobre manifiestos (`_MANIFEST_SIGNALS`, `:12`) | `yaml.safe_load` + catálogo de tareas |
| Salida | **un solo** id: `'python' \| 'node' \| 'dotnet' \| None` (`:19-20`) | **tupla** de stacks con evidencia y confianza |
| Granularidad | `dotnet` — **no distingue Framework de Core** | `dotnet_framework` ≠ `dotnet_core` ≠ `sql_dacpac` |
| Precedencia | arbitraria y documentada: Python > Node > .NET (`:9-11`) | fija y documentada, pero **no excluyente** |
| I/O | lee disco (tope 500 entradas, `:40`) | **PURO**: no toca disco |

**La prueba de que no alcanza:** `ci-dacpac.yml` compila un `.sqlproj` con el SDK
`Microsoft.Build.Sql` sobre `ubuntu-latest` (`ci-dacpac.yml:37-38 (pool)`, `:43 (UseDotNet@2)`).
`detect_stack` sobre el repo RSPACIFICO devolvería `'dotnet'` (o `'python'`, si hubiese un
`requirements.txt` en el árbol, por su precedencia) — que es **verdad sobre el repo y mentira
sobre esta pipeline**. Y `dotnet` a secas no permite distinguir el caso que causó el incidente
ADO-369 (`VSBuild@1` de .NET **Framework** sobre un pool hosted efímero).

> **Decisión de arquitectura (respuesta explícita a "¿extiende o complementa?"):
> COMPLEMENTA. Este plan NO toca `pipeline_stack_detector.py`.** Ampliar sus 3 ids rompería a
> sus consumidores del Plan 97 (presets por stack) y acoplaría un detector de repo a un catálogo
> de tareas ADO. En su lugar, `pipeline_profiler.py` expone la constante
> `STACK_TO_DETECTOR_ID: dict` para que un consumidor futuro (el 246 en su listado) pueda
> **contrastar** repo vs pipeline y mostrar la divergencia — sin que ninguno de los dos módulos
> dependa del otro.

### 2.2 Qué se reusa del motor existente (y qué NO)

**SÍ se reusa, tal cual, sin tocar:**

| Símbolo | Anclaje | Qué aporta al perfilador |
|---|---|---|
| `scan_unsupported(yaml_text) -> tuple` | `backend/services/pipeline_renderers.py:51` | **Ya resuelve el problema de "el YAML usa cosas que no modelo"**: evalúa sobre el documento PARSEADO (`:57`, `_walk` en `:39`), así que un `${{` dentro de un comentario no cuenta. Devuelve en el orden fijo de `UNSUPPORTED_CONSTRUCTS` (`:28-34`), nunca el de un `set` (`:73-74`). Es exactamente el campo `not_understood`. |
| `extract_task_dicts(node) -> list` | `backend/services/cicd_task_catalog.py:268` | Los `task:` **vivos** de un doc ya parseado; los comentados quedan afuera **por construcción** (`:274-277`), no por un filtro borrable. |
| `is_deploy_step(ref, inputs) -> bool` | `cicd_task_catalog.py:244` | Dos caminos evidenciados: `DEPLOY_TASK_REFS` (`:62`) o `PowerShell@2` con `filePath` que empieza con `DEPLOY_SCRIPT_PREFIX = "Deploy-"` (`:71`, `:254-257`). **Es la fase `deploy` del perfil, ya escrita y ya testeada.** |
| `get_task(profile, ref)` / `TASK_CATALOG` | `cicd_task_catalog.py:199` / `:192` | El catálogo cerrado del perfil `dotnet_framework` (`:30`), 10 tareas con sus `inputs` y `requires_windows` (`:86-190`). Es la fuente para clasificar cada paso. |
| `_pool_is_hosted(pool)` / `_pool_os_is_windows(pool)` | `backend/services/cicd_semantic_rules.py:141` / `:145` | `hosted` ⇔ tiene `vmImage`. El SO devuelve **`True`/`False`/`None`**, y `None` está documentado como *"un pool self-hosted no declara su SO: afirmar algo sobre él sería inventar"* (`:146-147`) — la misma doctrina anti-alucinación de este plan. |
| `_task_inputs(step)` | `cicd_semantic_rules.py:158` | `inputs` como dict, tolerante a `None`. |

**SÍ se reusa, pero requiere una promoción de visibilidad (2 líneas, retro-compatible):**

| Símbolo | Anclaje | Por qué es indispensable |
|---|---|---|
| `_iter_steps(doc) -> list[_StepCtx]` | `cicd_semantic_rules.py:105` | Recorre **las tres raíces de ADO** (`steps:` en `:125-126`, `jobs:` en `:128`, `stages:` en `:130-134`) **y** los jobs `- deployment:` (`:116-119`), resolviendo el **pool efectivo** con la precedencia job > stage > raíz (`:115`) y emitiendo un `location` estable (`"stages[1].jobs[0].steps[2]"`). Reescribirlo sería duplicar ~30 líneas de traversal sutil. `_StepCtx` (`:74-82`) ya trae `step`, `location`, `pool`, `stage_doc`, `in_deployment`. |

**NO se reusa (y el motivo importa):**

| Símbolo | Anclaje | Por qué NO sirve como sustrato de perfilado |
|---|---|---|
| `parse_ado_yaml(yaml_str) -> PipelineSpec` | `pipeline_renderers.py:453` | **Es lossy por diseño y su propio docstring lo dice** (`:458-464`): *"Un `- script:` a nivel raíz mezclado con tareas se recupera, pero al re-emitir sale agrupado antes de las tareas"*. Además **descarta** el bloque `pr:` cuando no es `"none"` (`:512` guarda sólo `pr_disabled`), **descarta** `strategy: matrix` (`ci-batch.yml:59-60`) y **pierde el orden real** de los pasos al separarlos en `steps` / `task_steps` (`:395`). Perfilar sobre `PipelineSpec` produciría un perfil de *la proyección* del pipeline, no del pipeline. **El perfilador trabaja sobre la salida cruda de `yaml.safe_load`.** |
| `check_semantics(...)` | `cicd_semantic_rules.py:497` | Emite `SemanticFinding` (problemas). El perfil no juzga: describe. El 248 es quien juzga. |
| `nearest_golden(...)` | `backend/services/cicd_corpus_mirror.py:121` *(verificado por `grep -n` del símbolo)* | Compara contra el corpus. Ortogonal al perfil. |

### 2.3 Datos duros del corpus (extraídos con `yaml.safe_load`, no con grep)

Los 9 golden de `backend/tests/fixtures/cicd_nl/golden/` fueron parseados y tabulados el
2026-07-26. Hechos que fundan el diseño:

- **La ausencia de tests es real y frecuente.** `cd-deploy-test.yml` tiene 11 tareas, compila
  con `VSBuild@1` (`:63`), despliega con `PowerShell@2` + `Deploy-Local.ps1` (`:135-138`) y
  **no tiene ni un `DotNetCoreCLI@2 command: test` ni un `PublishTestResults@2`**. Lo mismo
  `ci-batch.yml` y `ci-dacpac.yml`.
- **Un pipeline puede tener dos pools de naturaleza distinta.** `cd-deploy-test.yml:44-45`
  (stage Build → `vmImage: 'windows-2022'`, hosted) y `:120-121` (stage DeployAgendaWeb →
  `name: 'TEST-Server'`, self-hosted). **Eso cambia todo lo que se puede hacer** y hoy no se
  reporta en ningún lado.
- **El stack no siempre existe.** `bootstrap-server-environment.yml` y `security-scan-online.yml`
  **no compilan nada**: sus tareas son `PowerShell@2` + `PublishBuildArtifacts@1`. Su `stack`
  honesto es la tupla **vacía** con confianza `desconocido`, no una adivinanza.
- **Un pipeline puede usar dos stacks a la vez.** `ci-dacpac.yml` usa `UseDotNet@2` (`:43`) y
  `DotNetCoreCLI@2 command: build` (`:59-64`) → `dotnet_core`; y sus inputs nombran
  `'schema database/DB_Proj_RSPACIFICO.sqlproj'` (`:33`) y `'**/bin/Release/**/*.dacpac'`
  (`:71`) → `sql_dacpac`. `stack` es una **tupla**, no un escalar.
- **`DotNetCoreCLI@2 command: test` NO es evidencia de stack .NET Core.** `agendaweb-ci.yml:70-72`
  lo documenta explícitamente: *"net48 con dotnet test"*. Y `security-scan-online.yml:59` usa
  `command: 'custom'` / `custom: 'list'` sobre un proyecto Framework. Por eso la regla de stack
  de F1 sólo acepta `command in ("build","publish","restore")` como señal.
- **El entorno puede ser una expresión sin resolver.**
  `bootstrap-server-environment.yml:118` → `environment: '${{ parameters.targetEnvironment }}'`,
  y el parámetro está declarado en `:39` con `values:` en `:43` (`['Test','Production']`).
  El perfil devuelve el literal + los valores posibles **como evidencia**, y la clase queda
  `desconocido`. No se elige `Test` porque sea el `default`.
- **`scan_unsupported` ya distingue lo que estorba de lo que no.** Sobre el corpus devuelve
  `('matrix',)` para `ci-batch.yml` y `('compile_time_expression',)` para
  `bootstrap-server-environment.yml`; `()` para los otros 7. **Ninguno de los dos oculta pasos** —
  y esa distinción es la regla `_HIDES_STEPS` de F2.
- **Hay un `- script: |` crudo real** en `nightly-build-online.yml:111` y otro en
  `cd-deploy-test.yml:81`: el perfilador no puede asumir que todo paso es un `task:`.

### 2.4 Trampa de anclajes verificada: los fixtures están **desplazados +1**

Los golden vendorizados tienen una línea de cabecera `# fuente: RSPACIFICO/pipelines/<x>.yml -
copiado 2026-07-26 (plan 243 F0)` (`agendaweb-ci.yml:1`). Por lo tanto **todo anclaje del Plan
243 que cite `pipelines/<x>.yml:N` corresponde a `tests/fixtures/cicd_nl/golden/<x>.yml:N+1`**.
Verificado en dos puntos independientes:

- 243 §2.2 dice `agendaweb-ci.yml:142` (task comentada `IISWebAppDeploymentOnMachineGroup@0`) →
  en el fixture está en **`:143`**.
- 243 §2.2 dice `ci-dacpac.yml:102` (task comentada `SqlAzureDacpacDeployment@1`) → en el
  fixture está en **`:103`**.
- 243 §2.4 dice `ci-batch.yml:58-59` (`strategy: matrix:`) → en el fixture está en **`:59-60`**.

**Todos los anclajes de fixture de ESTE documento son del fixture** (los abrí ahí), y están
marcados con la ruta completa `backend/tests/fixtures/cicd_nl/golden/…`.

### 2.5 Tabla de anclajes verificados (todos abiertos el 2026-07-26)

| Anclaje | Símbolo | Cómo se verificó |
|---|---|---|
| `backend/services/pipeline_stack_detector.py:12,19` | `_MANIFEST_SIGNALS`, `detect_stack` | archivo leído entero (55 líneas) |
| `backend/services/pipeline_renderers.py:28,39,51,100,110,453,527` | `UNSUPPORTED_CONSTRUCTS`, `_walk`, `scan_unsupported`, `_script_step_doc`, `_task_step_doc`, `parse_ado_yaml`, `parse_gitlab_yaml` | archivo leído entero (581 líneas) |
| `backend/services/cicd_task_catalog.py:28,30,35,42,62,71,75,192,199,204,209,244,261,268,287` | `CATALOG_VERSION`, `PROFILE_DOTNET_FRAMEWORK`, `TaskInput`, `TaskSpec`, `DEPLOY_TASK_REFS`, `DEPLOY_SCRIPT_PREFIX`, `MACHINE_GROUP_MARKER`, `TASK_CATALOG`, `get_task`, `is_allowed`, `validate_inputs`, `is_deploy_step`, `is_machine_group_task`, `extract_task_dicts`, `extract_task_refs` | archivo leído entero (290 líneas) |
| `backend/services/cicd_semantic_rules.py:41,43,44,55,63,74,85,90,95,105,141,145,158,229,239,497` | `RULES_VERSION`, `MODE_AUDIT`, `MODE_NL_STRICT`, `_PROD_MARKERS`, `SemanticFinding`, `_StepCtx`, `_pool_of`, `_steps_of`, `_deployment_steps`, `_iter_steps`, `_pool_is_hosted`, `_pool_os_is_windows`, `_task_inputs`, `_trigger_paths`, `_has_deploy_step`, `check_semantics` | rangos `:55-229` y `:497-542` leídos; resto por `grep -n` del símbolo |
| `backend/services/pm/pm_llm_client.py:90,98,99,101,105,278,281-283` | `LLMCallSpec`, `.temperature`, `.fixture_id`, `.expect_json`, `LLMCallResult`, `call_llm`, docstring *"Nunca lanza excepción al caller"* | rangos leídos |
| `backend/services/harness_flags.py:21,67,120,191,207,2911` | `FlagSpec`, `CategorySpec("epicas_ado", …)`, `_CATEGORY_KEYS`, clave `"epicas_ado"`, entrada `STACKY_PIPELINE_GENERATOR_ENABLED`, `FlagSpec(key="STACKY_PIPELINE_GENERATOR_ENABLED")` | rangos leídos |
| `backend/tests/test_harness_flags.py:467` | `_CURATED_DEFAULTS_ON` | rango `:460-475` leído |
| `backend/config.py:516,1399` | `STACKY_PIPELINES_ENABLED`, `STACKY_PIPELINE_GENERATOR_ENABLED` | rango `:1395-1405` leído |
| `backend/api/pipeline_generator.py:1-10,25,34,36` | docstring del patrón de blueprint, `bp = Blueprint(...)`, `preview_route`, guard `abort(404)` per-request | rango `:1-40` leído |
| `backend/api/__init__.py:44,117` | `from .pipeline_generator import bp`, `api_bp.register_blueprint(pipeline_generator_bp)` | `grep -n` |
| `backend/scripts/run_harness_tests.sh:20,766-770` | `HARNESS_TEST_FILES=(`, bloque `test_plan243_*` | `grep -n` |
| `backend/scripts/run_harness_tests.ps1:13,679-683` | `$HarnessTestFiles = @(`, bloque `test_plan243_*` (**`:683` sin coma final**) | `grep -n` |
| `frontend/src/api/client.ts:44,155,160,162` | `rawPost`, `throw new Error` en non-2xx, `api`, `api.post` | rango `:155-177` leído + `grep -n` |
| `frontend/src/api/endpoints.ts:4426,4428,4434` | `PipelineGenerator`, `.preview`, `.commit` | `grep -n` |
| `frontend/src/components/devops/PipelineYamlPreview.tsx:12,20,57` (154 líneas) | `PipelineYamlPreviewProps`, `PipelineYamlPreview`, `PipelineGenerator.preview(...)` | primeras 70 líneas leídas + `wc -l` |
| `frontend/src/pages/DevOpsPage.tsx:58,75,113,130` | `DevOpsSectionContext`, `DevOpsSection`, `DEVOPS_SECTIONS`, entrada de `PipelineBuilderSection` | `grep -n` |
| `backend/tests/fixtures/cicd_nl/golden/*.yml` (9 archivos) | ver §2.3 | 4 leídos enteros (`agendaweb-ci`, `ci-batch`, `ci-dacpac`, `cd-deploy-test`) + los 9 parseados con `yaml.safe_load` y tabulados |

> **⚠ Aviso a quien implemente y a quien critique.** `frontend/src/api/endpoints.ts` **se movió
> ~58 líneas** desde que el Plan 243 v3 lo verificó: 243 §2.1 cita `endpoints.ts:4368
> (PipelineGenerator)`, y hoy está en **`:4426`**. Es la tercera vez que este archivo desfasa
> anclajes en esta casa. **Buscá siempre por símbolo (`grep -n "PipelineGenerator"`), nunca por
> número.**

### 2.6 Lo NO verificado (declarado)

1. **Que el Plan 246 exista.** Al momento de escribir esto, `backend/services/pipeline_inventory.py`
   y `backend/api/pipeline_inventory.py` **no existen** (verificado: `ls backend/services | grep
   inventor` → 0 resultados). Todo el plan está diseñado para funcionar **sin** el 246 (§3.3).
2. **El comportamiento de `Npm@1`, `NodeTool@0`, `UsePythonVersion@0`, `Docker@2` y
   `PublishPipelineArtifact@1` en pipelines reales de este ecosistema:** **0 usos en el corpus**.
   Se declaran en las tablas de detección de F1/F2 por ser los nombres canónicos de ADO, y se
   testean **sólo con fixtures sintéticas**, nunca contra el corpus. Están marcadas como tal.
3. **La calidad del texto que produzca el LLM en el propósito narrado** (F3): no verificable de
   forma determinista. Por eso es opcional, per-request, con techo de longitud, y **su fallo
   nunca degrada el perfil**.
4. **Este plan no toca ninguna tabla de base de datos.** No hay persistencia nueva: el perfil se
   calcula en el momento y se devuelve. (Cachear es del 246, que es quien tiene el registro.)
5. **`test_harness_flags_help` tiene 4 fallos ajenos preexistentes** (dossier §4). No son de este
   plan y no se "arreglan": la entrada nueva se valida de forma aislada (§F4).

---

## 3. Principios, guardarraíles y alcance

### 3.1 Guardarraíles no negociables (los del §6 del dossier, aterrizados)

| Guardarraíl | Cómo lo cumple ESTE plan |
|---|---|
| **Paridad en los 3 runtimes** | **F0–F2 y el camino default de F3 no usan LLM ni red ni disco**: son funciones puras sobre un string. Codex CLI, Claude Code CLI y Copilot Pro ejecutan bytes idénticos. El único punto con LLM (F3, narración) es **opt-in per-request** y su fallback es la plantilla determinista — que es lo que corre siempre por default. |
| **Cero trabajo extra al operador** | Flag `STACKY_PIPELINE_PROFILER_ENABLED` **default ON**. Ninguna de las 4 excepciones duras aplica: no bypasea revisión humana (es read-only y no publica nada), no es destructiva (no escribe un byte), no tiene prerequisitos fuera de la instalación default (`PyYAML==6.0.3` ya está), y no reduce la seguridad (no abre ninguna superficie). |
| **Cero tokens ociosos** | **El perfil default hace 0 llamadas a LLM.** La narración se pide explícitamente con `narrate: true` (un botón, una pipeline, un click). Perfilar 40 pipelines del inventario del 246 cuesta **0 tokens**. |
| **Human-in-the-loop** | El perfil **describe, no decide y no actúa**. No dispara corridas, no edita YAML, no crea tickets. La narración con IA la pide el operador. |
| **Mono-operador sin auth** | Ni RBAC ni roles: guard de flag `abort(404)` per-request, igual que `pipeline_generator.py:36`. |
| **No degradar** | Módulo nuevo + 2 líneas retro-compatibles en `cicd_semantic_rules.py` (alias preservado) + 1 componente montado adicionalmente. **Comando de no-regresión obligatorio en cada fase.** |
| **Reusar lo existente** | 6 símbolos reusados sin tocar + 1 promovido (§2.2). Cero re-parsers, cero catálogo nuevo, cero infra de flags nueva. |

### 3.2 Los dos principios anti-alucinación (son de diseño, no de estilo)

1. **Ningún campo sin evidencia.** `ProfileField` es `(value, confidence, evidence)` y el
   invariante lo verifica un test: **si `value` no está vacío, `evidence` no puede estar vacío y
   `confidence` no puede ser `desconocido`** (`test_sin_valor_sin_confianza`, F5). No hay forma
   de escribir un campo adivinado sin que el test se ponga rojo.
2. **La ausencia se declara, no se asume.** Una fase ausente vale `False` **con confianza alta**
   sólo si el documento se parseó completo y no oculta pasos. Si trae `template:` o `extends:`
   (los pasos podrían vivir en otro archivo), toda fase ausente pasa a `desconocido`
   (regla `_HIDES_STEPS`, F2).

### 3.3 Degradación explícita ante el Plan 246 (obligatoria, no opcional)

El endpoint acepta **dos formas de entrada, y con que exista una alcanza**:

```
POST /api/pipeline-profiler/profile
  {"yaml_text": "<...>"}                 → SIEMPRE funciona. No depende del 246.
  {"pipeline_id": "<id del registro>"}   → sólo si services/pipeline_inventory.py existe.
```

La resolución por `pipeline_id` se hace con **import perezoso dentro del handler**
(`try: from services.pipeline_inventory import get_pipeline_yaml / except ImportError:`) y
devuelve **`501` con `{"error":"inventory_unavailable", "detail":"el registro de pipelines
(plan 246) no está instalado; enviá yaml_text"}`**. **Prohibido importar `pipeline_inventory` a
nivel de módulo**: un `ImportError` en el import del blueprint tumbaría el arranque de
`api/__init__.py`.

### 3.4 Desviación declarada respecto del dossier (leerla, es deliberada)

El dossier §3 sugiere para el 247, en la columna `api/`: *"(extiende el blueprint del 246)"*.
**Este plan crea un blueprint propio: `backend/api/pipeline_profiler.py` con
`url_prefix="/pipeline-profiler"`.** Motivos:

1. El archivo del 246 **puede no existir** cuando se implemente el 247, y "extender un blueprint
   inexistente" no es una instrucción implementable.
2. Dos planes creando **el mismo archivo** es un riesgo de merge alto en un árbol con sesión
   paralela viva.
3. `pipeline_profiler.py` / `/pipeline-profiler` **no están reservados por ningún otro plan** de
   la serie (tabla §3 del dossier) — no se pisa ningún nombre.

**Todo el resto de los nombres reservados se respeta al pie de la letra:**
`services/pipeline_profiler.py`, `frontend/src/devops/pipelineProfileModel.ts`,
`frontend/src/components/devops/PipelineProfileCard.tsx`, flag
`STACKY_PIPELINE_PROFILER_ENABLED`.

### 3.5 Fuera de alcance de este plan (corte propio, §3 del dossier)

Para que **6 fases entren en una sola corrida** (lección C25 del 243), quedan afuera **por
decisión mía**, no por olvido:

- **Perfilado de GitLab.** El perfilador es ADO-only en v1. `profile_pipeline` acepta un kwarg
  `provider: str = "ado"` y **lanza `ValueError` explícito** para cualquier otro valor — no
  devuelve un perfil vacío que parezca válido. GitLab es del **plan 249**.
- **Persistencia / caché del perfil.** Se calcula en el momento (K6: 9 pipelines < 1 s).
- **Perfiles de catálogo distintos de `dotnet_framework`.** `TASK_CATALOG` (`cicd_task_catalog.py:192`)
  hoy tiene **un** perfil. Las tablas de detección de stack/fases de F1/F2 son **independientes
  del catálogo** (miran refs de tarea, no pertenencia al catálogo), así que un perfil nuevo no
  las rompe.
- **Comparar el perfil contra el repo** (`detect_stack`): se expone `STACK_TO_DETECTOR_ID` y
  nada más. Contrastarlos es del 246 (que tiene el repo) o del 248 (que juzga).

---

# FASES

> **Todas las fases son TDD: primero el archivo de test, corriéndolo y viéndolo ROJO por la
> razón correcta; después el código; después verde.** Los comandos son los del §4 del dossier,
> verificados el 2026-07-26. **Recordá la trampa de los dos venvs: se usa `.venv` (Python
> 3.13.5), NO `venv` (3.11.9).**

---

## F0 — Contrato del perfil + promoción del recorredor de pasos

**Objetivo (1 frase):** dejar escrito y testeado el **contrato de datos** del perfil —con su
invariante anti-alucinación— y hacer público el recorredor de pasos que ya existe, sin duplicarlo.

**Valor entregado:** a partir de acá, cualquier campo que agregue F1/F2 es incapaz de existir sin
evidencia; y el perfilador no reimplementa el traversal de las 3 raíces de ADO.

### Archivos

| Acción | Ruta completa |
|---|---|
| **CREAR** | `Stacky Agents/backend/services/pipeline_profiler.py` |
| **EDITAR** | `Stacky Agents/backend/services/cicd_semantic_rules.py` (+2 líneas, retro-compatible) |
| **CREAR** | `Stacky Agents/backend/tests/test_plan247_profiler_core.py` |

### Símbolos EXACTOS a crear

```python
# services/pipeline_profiler.py — Plan 247 F0
CONTRACT_VERSION = "247.1"

CONF_HIGH    = "alta"          # evidencia directa e inequívoca (ref de tarea, clave del YAML)
CONF_MEDIUM  = "media"         # heurística sobre un dato EXPLÍCITO del YAML (texto de un input)
CONF_UNKNOWN = "desconocido"   # no determinable — NUNCA se adivina

@dataclass(frozen=True)
class Evidence:
    location: str   # "stages[1].deployments[0].steps[2]" | "pool" | "schedules[0]" | "(documento)"
    detail:   str   # "task VSBuild@1" | "vmImage: windows-2022" | "environment: 'Test'"

@dataclass(frozen=True)
class ProfileField:
    value:      object       # tuple | bool | str  (nunca None)
    confidence: str          # CONF_*
    evidence:   tuple = ()   # tuple[Evidence, ...]

@dataclass(frozen=True)
class EnvironmentRef:
    name:            str     # literal tal cual aparece, sin resolver
    kind:            str     # "dev"|"qa"|"test"|"prod"|"desconocido"
    resolved:        bool    # False si `name` contiene "${{"
    possible_values: tuple = ()   # de `parameters[].values`, si se pudo resolver el nombre

@dataclass(frozen=True)
class AgentPool:
    kind: str            # "hosted" | "self_hosted" | "heredado_sin_declarar"
    name: str            # vmImage o pool name, literal
    os:   object = None  # True (windows) | False (no windows) | None (desconocido)

@dataclass(frozen=True)
class PipelineProfile:
    contract_version:    str
    source_path:         str
    stack:               ProfileField           # value: tuple[str, ...]
    phases:              dict                   # str -> ProfileField (value: bool)
    artifacts_published: ProfileField           # value: tuple[str, ...]
    artifacts_consumed:  ProfileField           # value: tuple[str, ...]
    environments:        ProfileField           # value: tuple[EnvironmentRef, ...]
    agents:              ProfileField           # value: tuple[AgentPool, ...]
    triggers:            ProfileField           # value: tuple[str, ...]
    purpose:             str = ""
    purpose_source:      str = "plantilla"      # "plantilla" | "llm"
    not_understood:      tuple = ()             # salida literal de scan_unsupported()
    parse_error:         object = None          # str | None

def empty_profile(source_path: str = "", parse_error: str = None) -> PipelineProfile: ...
def profile_to_dict(profile: PipelineProfile) -> dict: ...   # JSON-safe, claves estables
def field_is_coherent(field: ProfileField) -> bool: ...      # invariante §3.2.1

STACK_TO_DETECTOR_ID: dict = {          # puente informativo hacia el Plan 97, sin acoplar
    "dotnet_framework": "dotnet",
    "dotnet_core":      "dotnet",
    "sql_dacpac":       "dotnet",
    "node":             "node",
    "python":           "python",
    "container":        None,           # detect_stack no tiene id para contenedores
}
```

### Diff exacto en `cicd_semantic_rules.py` (retro-compatible, 2 líneas)

Inmediatamente **después** del cierre de la función `_iter_steps` (hoy `:136`, `return out`) y
**antes** del comentario `# ── Helpers de dominio ──` (hoy `:139`), insertar:

```python
# Plan 247 F0 — alias públicos. `_iter_steps` y `_StepCtx` resuelven las 3 raíces de ADO y el
# pool efectivo; el perfilador los reusa en vez de duplicar el traversal. El nombre privado se
# conserva: los call-sites internos (check_semantics:527) NO se tocan.
iter_step_contexts = _iter_steps
StepContext = _StepCtx
```

> **Prohibido** renombrar `_iter_steps` o `_StepCtx`, y **prohibido** cambiar una sola línea de
> su cuerpo. Si el bloque `return out` no aparece en `:136`, **greppeá `def _iter_steps`** (regla
> de anclajes §2.5).

### Pseudocódigo clave

```python
def field_is_coherent(field) -> bool:
    """Invariante anti-alucinación (§3.2.1). Un campo con valor DEBE tener evidencia
    y no puede declararse desconocido; un campo desconocido DEBE estar vacío."""
    tiene_valor = bool(field.value) if not isinstance(field.value, bool) else field.value
    if tiene_valor:
        return bool(field.evidence) and field.confidence != CONF_UNKNOWN
    if field.confidence == CONF_UNKNOWN:
        return not field.evidence or True   # un campo desconocido PUEDE traer evidencia de por qué
    return True
```

`profile_to_dict` serializa: `ProfileField → {"value":…, "confidence":…, "evidence":[{"location","detail"}]}`,
`EnvironmentRef → {"name","kind","resolved","possible_values"}`,
`AgentPool → {"kind","name","os"}`, `phases → {id: {...}}`. **Claves en inglés y estables**
(las consume `pipelineProfileModel.ts` en F5 y las consumirá el 248).

### Tests PRIMERO — `backend/tests/test_plan247_profiler_core.py`

| Caso | Qué prueba |
|---|---|
| `test_contract_version_declarada` | `CONTRACT_VERSION == "247.1"` |
| `test_field_con_valor_exige_evidencia` | `field_is_coherent(ProfileField(("dotnet_framework",), CONF_HIGH, ()))` es `False` |
| `test_field_con_valor_no_puede_ser_desconocido` | `field_is_coherent(ProfileField(True, CONF_UNKNOWN, (Evidence("x","y"),)))` es `False` |
| `test_field_vacio_desconocido_es_coherente` | `field_is_coherent(ProfileField((), CONF_UNKNOWN, ()))` es `True` |
| `test_empty_profile_es_serializable` | `json.dumps(profile_to_dict(empty_profile("x.yml", "boom")))` no lanza |
| `test_profile_to_dict_claves_estables` | el dict tiene exactamente las 13 claves del contrato |
| `test_iter_step_contexts_es_el_mismo_objeto` | `cicd_semantic_rules.iter_step_contexts is cicd_semantic_rules._iter_steps` |
| `test_iter_step_contexts_cubre_las_tres_raices` | sobre 3 docs sintéticos (`steps:`, `jobs:`, `stages:`) devuelve 1 ctx cada uno con el `location` esperado |
| `test_stack_to_detector_id_no_inventa` | todos los valores de `STACK_TO_DETECTOR_ID` están en `{"dotnet","node","python",None}` |

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan247_profiler_core.py -q
# NO REGRESIÓN (obligatorio, porque F0 edita cicd_semantic_rules.py):
.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q
```

### Criterio de aceptación BINARIO

`test_plan247_profiler_core.py` verde **Y** `test_plan243_reglas_semanticas.py` verde con el
**mismo número de tests pasados que antes del cambio** (anotar el número antes de editar).

**Flag:** `STACKY_PIPELINE_PROFILER_ENABLED` (default **ON**). F0 no la consume: es un módulo
puro sin call-site. **No se declara todavía** (la declara F4, junto con su consumidor — evita
una flag `reserved` sin uso).
**Impacto por runtime:** idéntico en los 3 (Python puro, sin I/O, sin LLM). **Fallback:** ninguno
necesario.
**Trabajo del operador: ninguno**

---

## F1 — Stack tecnológico, agentes/pools y disparadores

**Objetivo (1 frase):** responder *"con qué está hecha, dónde corre y cuándo se dispara"*, con
evidencia por campo y `desconocido` cuando no hay señal.

**Valor entregado:** el operador distingue `dotnet_framework` de `dotnet_core` de `sql_dacpac`
—cosa que `detect_stack` no puede— y ve de un vistazo si una pipeline corre en un agente
self-hosted (donde un paso puede tocar el servidor real).

### Archivos

| Acción | Ruta completa |
|---|---|
| **EDITAR** | `Stacky Agents/backend/services/pipeline_profiler.py` |
| **EDITAR** | `Stacky Agents/backend/tests/test_plan247_profiler_core.py` |

### Símbolos EXACTOS

```python
STACK_IDS = ("dotnet_framework", "dotnet_core", "sql_dacpac", "node", "python", "container")
# ↑ el ORDEN es la precedencia de salida de la tupla `stack`. Determinista y documentado.

TRIGGER_KINDS = ("push", "pr", "scheduled", "manual")

def detect_stacks(doc: dict) -> ProfileField: ...
def detect_agents(doc: dict) -> ProfileField: ...
def detect_triggers(doc: dict) -> ProfileField: ...
def profile_pipeline(yaml_text: str, *, provider: str = "ado",
                     source_path: str = "") -> PipelineProfile: ...
```

### Tabla de detección de stack (CERRADA — cada fila con su procedencia)

| stack id | señal (sobre el doc parseado) | confianza | evidencia en el corpus |
|---|---|---|---|
| `dotnet_framework` | `task == "VSBuild@1"` **o** (`task == "NuGetCommand@2"` y `"restoreSolution" in inputs`) | `alta` | `agendaweb-ci.yml:56`, `ci-batch.yml:97`, `cd-deploy-test.yml:63` |
| `dotnet_core` | `task == "UseDotNet@2"` **o** (`task == "DotNetCoreCLI@2"` y `inputs["command"] in ("build","publish","restore")`) | `alta` | `ci-dacpac.yml:43`, `ci-dacpac.yml:59-64` |
| `sql_dacpac` | algún **valor de input** (str) contiene `".sqlproj"` o `".dacpac"` | `alta` | `ci-dacpac.yml:33` (`SQL_PROJECT`), `:71` (`Contents`) |
| `node` | `task in ("Npm@1", "NodeTool@0")` | `alta` | **0 usos en el corpus** — declarada, testeada sólo con fixture sintética (§2.6.2) |
| `python` | `task == "UsePythonVersion@0"` | `alta` | **0 usos** — ídem |
| `container` | `task == "Docker@2"` **o** existe la clave `container:` en el doc | `alta` | **0 usos** — ídem |

> **REGLA DURA (evidenciada en §2.3):** `DotNetCoreCLI@2` con `command in ("test","custom","run","pack","push")`
> **NO** es señal de `dotnet_core`. `agendaweb-ci.yml:70-72` documenta *"net48 con dotnet test"* y
> `security-scan-online.yml:59` usa `command: 'custom'` sobre un proyecto Framework. Un test
> negativo lo fija: `test_dotnet_test_no_implica_dotnet_core`.

Si no hay ninguna señal → `ProfileField(value=(), confidence=CONF_UNKNOWN, evidence=())`.
**No se cae en `dotnet` por defecto.**

### Tabla de agentes/pools

Recorre `iter_step_contexts(doc)` y agrupa `ctx.pool` (que ya es el efectivo, job > stage > raíz,
`cicd_semantic_rules.py:115`). Deduplica por `(kind, name)`, en **orden de primera aparición**.

| condición sobre `ctx.pool` | `AgentPool.kind` | `AgentPool.name` | `AgentPool.os` |
|---|---|---|---|
| `_pool_is_hosted(pool)` (tiene `vmImage`) | `"hosted"` | `pool["vmImage"]` | `_pool_os_is_windows(pool)` |
| tiene `name` | `"self_hosted"` | `pool["name"]` | `None` (**se declara desconocido, jamás se asume Windows** — `cicd_semantic_rules.py:146-147`) |
| dict vacío | `"heredado_sin_declarar"` | `""` | `None` |

Confianza: `alta` si hay al menos un pool; `desconocido` con tupla vacía si el documento no tiene
ni un paso (p. ej. sólo `parameters:`).

### Tabla de disparadores

```python
def detect_triggers(doc):
    kinds = []
    trg = doc.get("trigger")
    # En ADO, `trigger:` AUSENTE = CI implícito en todas las ramas; `trigger: none` = apagado.
    if isinstance(trg, dict) or trg is None:      kinds.append("push")
    pr = doc.get("pr")
    if isinstance(pr, dict) or pr is None:        kinds.append("pr")
    if doc.get("schedules"):                      kinds.append("scheduled")
    if not kinds:                                 kinds.append("manual")
    # evidencia: Evidence("trigger", "trigger: none") / ("schedules[0]", "cron: 0 5 * * 1-5") / ...
```

### `profile_pipeline` — esqueleto y casos borde

```python
def profile_pipeline(yaml_text, *, provider="ado", source_path=""):
    if provider != "ado":
        raise ValueError("provider %r no soportado por el perfilador v1 (GitLab = plan 249)" % provider)
    if len(yaml_text or "") > MAX_YAML_BYTES:          # MAX_YAML_BYTES = 512 * 1024
        return empty_profile(source_path, "el YAML supera 512 KB: fuera del rango soportado")
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        return empty_profile(source_path, "el YAML no se pudo parsear: %s" % str(exc).splitlines()[0])
    if not isinstance(doc, dict):
        return empty_profile(source_path, "el YAML no es un documento de pipeline (no es un mapa)")
    return PipelineProfile(
        contract_version=CONTRACT_VERSION, source_path=source_path,
        stack=detect_stacks(doc), agents=detect_agents(doc), triggers=detect_triggers(doc),
        phases={}, artifacts_published=ProfileField((), CONF_UNKNOWN),   # ← F2 los llena
        artifacts_consumed=ProfileField((), CONF_UNKNOWN),
        environments=ProfileField((), CONF_UNKNOWN),
        not_understood=scan_unsupported(yaml_text),                      # reuso literal, §2.2
        parse_error=None,
    )
```

**`profile_pipeline` NUNCA lanza** salvo por `provider` inválido (falla ruidosa y deliberada,
misma doctrina que `check_semantics` con `mode` inválido, `cicd_semantic_rules.py:503-504`).

### Tests PRIMERO — se agregan a `test_plan247_profiler_core.py`

| Caso | Qué prueba |
|---|---|
| `test_vsbuild_implica_dotnet_framework` | fixture sintética con `VSBuild@1` → `("dotnet_framework",)`, `CONF_HIGH`, evidencia no vacía |
| `test_dotnet_test_no_implica_dotnet_core` | `DotNetCoreCLI@2 command: test` solo → `stack.value == ()`, `CONF_UNKNOWN` |
| `test_sqlproj_implica_sql_dacpac` | input con `'x/y.sqlproj'` → `"sql_dacpac"` en la tupla |
| `test_stack_multiple_respeta_precedencia` | `UseDotNet@2` + `.dacpac` → **exactamente** `("dotnet_core","sql_dacpac")` (orden de `STACK_IDS`) |
| `test_stack_sin_senal_es_desconocido` | doc con sólo `PowerShell@2` → `((), CONF_UNKNOWN)` |
| `test_node_python_container_sinteticos` | 3 fixtures sintéticas (§2.6.2) → un id cada una |
| `test_pool_hosted_vs_self_hosted` | doc con `vmImage` a nivel stage y `name` en otro → 2 `AgentPool` con `kind` distinto |
| `test_pool_self_hosted_os_es_none` | `AgentPool.os is None` para el self-hosted (nunca `True`) |
| `test_pool_heredado_de_la_raiz` | pool sólo en la raíz, job sin pool → 1 `AgentPool` hosted |
| `test_trigger_none_es_manual` | `trigger: none` + `pr: none` sin `schedules` → `("manual",)` |
| `test_trigger_ausente_es_push` | doc sin claves `trigger`/`pr` → `("push","pr")` |
| `test_schedules_es_scheduled` | doc con `schedules:` → `"scheduled"` en la tupla |
| `test_provider_invalido_lanza` | `pytest.raises(ValueError)` con `provider="gitlab"` |
| `test_yaml_roto_devuelve_parse_error` | `"a: [\n"` → `parse_error` no vacío, sin excepción |
| `test_yaml_gigante_no_se_procesa` | `"a: 1\n" * 200000` → `parse_error` menciona 512 KB |

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan247_profiler_core.py -q
```

### Criterio de aceptación BINARIO

`test_plan247_profiler_core.py` verde con **los 24 casos de F0+F1**.

**Flag:** `STACKY_PIPELINE_PROFILER_ENABLED` (default **ON**) — se cablea en F4.
**Impacto por runtime:** idéntico en los 3 (funciones puras). **Fallback:** ninguno necesario.
**Trabajo del operador: ninguno**

---

## F2 — Anatomía: qué fases tiene y cuáles NO, artefactos y entornos

**Objetivo (1 frase):** producir la anatomía de fases —incluyendo **las ausentes**—, los
artefactos publicados/consumidos y los entornos tocados, con la regla de degradación que impide
afirmar una ausencia cuando el YAML esconde pasos.

**Valor entregado:** el dato de mayor valor del plan y el que hoy nadie produce:
*"esta pipeline compila pero no corre tests"*.

### Archivos

| Acción | Ruta completa |
|---|---|
| **EDITAR** | `Stacky Agents/backend/services/pipeline_profiler.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan247_anatomia.py` |

### Símbolos EXACTOS

```python
PHASE_IDS = ("build", "test", "package", "publish_artifact", "deploy")

# Construcciones que PODRÍAN esconder pasos en otro archivo. `matrix` y
# `compile_time_expression` NO esconden pasos (los pasos son visibles; sólo hay valores sin
# resolver) y por eso NO degradan la anatomía. Evidencia: ci-batch.yml:59-60 tiene matrix y sus
# 3 tareas están a la vista; bootstrap-server-environment.yml tiene 17 `${{ }}` y sus 2 tareas
# también.
_HIDES_STEPS = ("template", "extends")

_ENV_MARKERS = (("prod", ("prod", "produccion", "producción")),
                ("qa",   ("qa", "uat")),
                ("test", ("test", "tst", "staging", "stg")),
                ("dev",  ("dev", "desarrollo")))

def detect_phases(doc: dict, not_understood: tuple) -> dict: ...
def detect_artifacts(doc: dict) -> tuple: ...        # (published: ProfileField, consumed: ProfileField)
def detect_environments(doc: dict) -> ProfileField: ...
def _resolve_parameter_values(doc: dict, expr: str) -> tuple: ...
```

### Tabla de detección de fases (CERRADA)

| fase | señal | confianza | evidencia en el corpus |
|---|---|---|---|
| `build` | `task == "VSBuild@1"` **o** (`task == "DotNetCoreCLI@2"` y `inputs["command"] in ("build","publish")`) **o** `task == "MSBuild@1"` | `alta` | `agendaweb-ci.yml:56`, `ci-dacpac.yml:59` |
| `test` | (`task == "DotNetCoreCLI@2"` y `inputs["command"] == "test"`) **o** `task in ("PublishTestResults@2", "VSTest@2")` | `alta` | `agendaweb-ci.yml:73`, `:89` |
| `package` | valor de input que contiene `"WebPublishMethod=Package"` o `"PackageLocation"` **o** (`task == "CopyFiles@2"` y algún valor menciona `ArtifactStagingDirectory`) | **`media`** (señal textual, no ref de tarea) | `agendaweb-ci.yml:64`, `ci-cd-online.yml:94`, `ci-dacpac.yml:67-72` |
| `publish_artifact` | `task in ("PublishBuildArtifacts@1", "PublishPipelineArtifact@1")` | `alta` (la 2ª: 0 usos, §2.6.2) | `agendaweb-ci.yml:112` |
| `deploy` | `is_deploy_step(ref, inputs)` — **reuso literal de `cicd_task_catalog.py:244`** | `alta` | `cd-deploy-test.yml:135-138` (`Deploy-Local.ps1`) |

> **Contra-caso obligatorio, ya evidenciado:** `bootstrap-server-environment.yml:128` corre
> `Initialize-ServerEnvironment.ps1` con `PowerShell@2` y **no es deploy** — porque
> `DEPLOY_SCRIPT_PREFIX == "Deploy-"` (`cicd_task_catalog.py:71`). El test
> `test_initialize_no_es_deploy` lo fija.

### Regla de degradación de la anatomía (`_HIDES_STEPS`) — el corazón anti-alucinación

```python
def detect_phases(doc, not_understood):
    hay_ciego = any(c in not_understood for c in _HIDES_STEPS)
    out = {}
    for phase_id in PHASE_IDS:
        hits = _signals_for(phase_id, doc)          # lista de Evidence
        if hits:
            out[phase_id] = ProfileField(True, CONF_MEDIUM if phase_id == "package" else CONF_HIGH,
                                         tuple(hits))
        elif hay_ciego:
            # Los pasos podrían vivir en un template/extends que no leímos.
            out[phase_id] = ProfileField(False, CONF_UNKNOWN, (
                Evidence("(documento)",
                         "el pipeline usa %s: los pasos pueden estar en otro archivo"
                         % ", ".join(c for c in _HIDES_STEPS if c in not_understood)),))
        else:
            # Documento completo y sin señal ⇒ la AUSENCIA es un hecho verificado.
            out[phase_id] = ProfileField(False, CONF_HIGH, (
                Evidence("(documento)", "ningún paso del pipeline corresponde a la fase '%s'" % phase_id),))
    return out
```

> Nótese que **la ausencia sí lleva evidencia** (`"ningún paso corresponde a la fase X"`): es una
> afirmación sobre el documento completo, no un silencio. `field_is_coherent` lo acepta porque
> `value is False` (vacío) con confianza `alta`.

### Artefactos

- **Publicados:** por cada `task in ("PublishBuildArtifacts@1","PublishPipelineArtifact@1")`,
  el valor de `inputs["ArtifactName"]` (o `inputs["artifactName"]`, variante de la tarea
  moderna). **Literal, sin resolver `$(...)` ni `${{ }}`.** Deduplicado por orden de aparición.
- **Consumidos:** por cada paso con clave `download` y clave `artifact`, el valor de `artifact`.
  (`cd-deploy-test.yml:132-133`, `:171-172`). `iter_step_contexts` los entrega dentro de los
  `deployment` (`cicd_semantic_rules.py:116-119`).

**Prohibido resolver variables.** `'$(ARTIFACT_NAME)'` se reporta tal cual: el valor de la
variable puede cambiar por variable group o por override en la corrida, y adivinarlo sería
exactamente la alucinación que este plan prohíbe. La resolución de valores por entorno es del
**plan 251**.

### Entornos

Por cada job `- deployment:` (los `ctx.in_deployment == True` dan el paso; el `environment:` se
lee del `jb_doc`, así que `detect_environments` recorre `doc["stages"][i]["jobs"]` y `doc["jobs"]`
buscando la clave `deployment`), construir un `EnvironmentRef`:

```python
name = str(jb_doc.get("environment") or "")
resolved = "${{" not in name
kind = "desconocido"
possible = ()
if resolved:
    low = name.lower()
    for k, markers in _ENV_MARKERS:
        if any(m in low for m in markers): kind = k; break
else:
    possible = _resolve_parameter_values(doc, name)   # ver abajo
```

`_resolve_parameter_values(doc, expr)`: **acotada a propósito**. Sólo si `expr.strip()` matchea
exactamente `^\$\{\{\s*parameters\.([A-Za-z0-9_]+)\s*\}\}$`, busca en `doc["parameters"]` el item
con ese `name` y devuelve `tuple(item.get("values") or ())`. Cualquier otra forma → `()`.
**El `kind` sigue siendo `desconocido` aunque haya `possible_values`**: enumerar los valores
declarados es un hecho; elegir uno sería una suposición.

Evidencia: `Evidence("stages[0].jobs[0].environment", "environment: '${{ parameters.targetEnvironment }}' (parameters.targetEnvironment values: Test, Production)")`.

### Tests PRIMERO — `backend/tests/test_plan247_anatomia.py`

| Caso | Qué prueba |
|---|---|
| `test_build_por_vsbuild` / `test_build_por_dotnet_build` | fase `build` True con `CONF_HIGH` |
| `test_test_por_dotnet_test` / `test_test_por_publish_test_results` | fase `test` True |
| `test_ausencia_de_test_es_hecho_no_silencio` | doc con sólo `VSBuild@1` → `phases["test"] == ProfileField(False, CONF_HIGH, <evidencia no vacía>)` |
| `test_template_degrada_toda_ausencia` | doc con `- template: x.yml` y sin tareas → **las 5 fases** en `(False, CONF_UNKNOWN)` |
| `test_matrix_no_degrada_la_anatomia` | doc con `strategy: matrix:` + `VSBuild@1` → `build (True, CONF_HIGH)` y `test (False, CONF_HIGH)` |
| `test_compile_time_expression_no_degrada` | ídem con `${{ }}` en un input |
| `test_package_tiene_confianza_media` | `msbuildArgs` con `WebPublishMethod=Package` → `phases["package"].confidence == CONF_MEDIUM` |
| `test_deploy_reusa_is_deploy_step` | `PowerShell@2` + `filePath: '.../Deploy-Local.ps1'` → `deploy` True |
| `test_initialize_no_es_deploy` | `filePath: '.../Initialize-ServerEnvironment.ps1'` → `deploy` **False** |
| `test_artefactos_publicados_literales` | `ArtifactName: '$(X)'` → tupla `('$(X)',)` **sin resolver** |
| `test_artefactos_consumidos` | `- download: current` + `artifact: 'A'` dentro de un `deployment` → `('A',)` |
| `test_entorno_literal_clasifica` | `environment: 'Test'` → `kind == "test"`, `resolved is True` |
| `test_entorno_produccion_clasifica_prod` | `environment: 'Production'` → `kind == "prod"` |
| `test_entorno_parametrizado_no_se_adivina` | `environment: '${{ parameters.targetEnvironment }}'` con `values: [Test, Production]` → `resolved is False`, `kind == "desconocido"`, `possible_values == ("Test","Production")` |
| `test_entorno_expresion_rara_no_resuelve` | `environment: '${{ variables.foo }}'` → `possible_values == ()` |
| `test_sin_deployment_no_hay_entornos` | doc de sólo `steps:` → `environments.value == ()` |

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan247_anatomia.py -q
```

### Criterio de aceptación BINARIO

`test_plan247_anatomia.py` verde (16 casos) **Y** `test_plan247_profiler_core.py` sigue verde.

**Flag:** `STACKY_PIPELINE_PROFILER_ENABLED` (default **ON**) — se cablea en F4.
**Impacto por runtime:** idéntico en los 3 (puro). **Fallback:** ninguno necesario.
**Trabajo del operador: ninguno**

---

## F3 — Propósito en 1 línea: plantilla determinista + narración LLM **opcional**

**Objetivo (1 frase):** que el perfil traiga siempre una frase legible por humanos, armada
**sin LLM** a partir de la anatomía, y permitir —sólo si el operador lo pide explícitamente— que
un LLM la reescriba en prosa, sin poder inventar hechos.

**Valor entregado:** la línea que se lee en una tarjeta. Y la garantía de que **sin LLM el perfil
sigue completo y útil**.

### Archivos

| Acción | Ruta completa |
|---|---|
| **EDITAR** | `Stacky Agents/backend/services/pipeline_profiler.py` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan247_proposito.py` |

### Símbolos EXACTOS

```python
PURPOSE_MAX_CHARS = 200
PURPOSE_SOURCE_TEMPLATE = "plantilla"
PURPOSE_SOURCE_LLM = "llm"

def build_purpose_template(profile: PipelineProfile) -> str: ...
def narrate_purpose(profile: PipelineProfile, *, llm_caller=None) -> tuple: ...
    # -> (texto: str, fuente: str)  — NUNCA lanza
```

### Plantilla determinista (sin LLM) — gramática fija

```
<VERBOS> [para <STACK>][; publica <N> artefacto(s)][; despliega a <ENTORNOS>].
Dispara: <TRIGGERS>. Agente: <AGENTES>.[ No corre tests.][ No entendido: <X>.]
```

- `<VERBOS>`: fases True, en el orden de `PHASE_IDS`, mapeadas por una tabla cerrada
  `{"build":"Compila","test":"testea","package":"empaqueta","publish_artifact":"publica artefactos","deploy":"despliega"}`.
  Si ninguna fase es True → `"No compila, no testea ni despliega"`.
- `<STACK>`: `", ".join(stack.value)` con etiquetas legibles
  (`{"dotnet_framework":".NET Framework","dotnet_core":".NET Core","sql_dacpac":"SQL/DACPAC","node":"Node","python":"Python","container":"contenedores"}`).
  Tupla vacía → se **omite** el fragmento (no se escribe "stack desconocido" en una frase corta).
- `<ENTORNOS>`: nombres literales; los no resueltos salen como `"<expresión sin resolver>"`.
- `<TRIGGERS>`: `{"push":"push","pr":"pull request","scheduled":"agendado","manual":"manual"}`.
- `<AGENTES>`: `"hosted windows-2022"` / `"self-hosted TEST-Server"`, separados por `" + "`.
- **`" No corre tests."`** se agrega **sólo** si `phases["test"] == (False, CONF_HIGH)` —
  es decir, si la ausencia está **verificada**, no si es `desconocido`.
- **Truncado duro** a `PURPOSE_MAX_CHARS` con `…` si se pasa.

Ejemplo real esperado para `cd-deploy-test.yml`:
`"Compila, empaqueta, publica artefactos y despliega para .NET Framework; publica 4 artefactos; despliega a Test. Dispara: push. Agente: hosted windows-2022 + self-hosted TEST-Server. No corre tests."`

### Narración con LLM — opcional, degradable, mockeable

```python
def narrate_purpose(profile, *, llm_caller=None):
    """Devuelve (texto, fuente). NUNCA lanza. Sin llm_caller ⇒ plantilla."""
    base = build_purpose_template(profile)
    if llm_caller is None:
        return base, PURPOSE_SOURCE_TEMPLATE
    spec = LLMCallSpec(
        system=("Reescribí en UNA sola línea en español, máximo 200 caracteres, el propósito de "
                "una pipeline de CI/CD. USÁ EXCLUSIVAMENTE los datos del JSON; está PROHIBIDO "
                "agregar cualquier hecho que no esté ahí. Respondé JSON: {\"purpose\": \"...\"}"),
        user=json.dumps(profile_to_dict(profile), ensure_ascii=False),   # ← el PERFIL, no el YAML
        expect_json=True, temperature=0.0, fixture_id="plan247_purpose",
    )
    try:
        result = llm_caller(spec)
    except Exception:
        return base, PURPOSE_SOURCE_TEMPLATE
    if not getattr(result, "success", False):
        return base, PURPOSE_SOURCE_TEMPLATE
    texto = ((getattr(result, "parsed_json", None) or {}).get("purpose") or "").strip()
    texto = " ".join(texto.split())                      # una sola línea, siempre
    if not texto or len(texto) > PURPOSE_MAX_CHARS:
        return base, PURPOSE_SOURCE_TEMPLATE
    return texto, PURPOSE_SOURCE_LLM
```

**Cuatro candados anti-alucinación, todos testeados:**

1. **La entrada del LLM es el perfil ya calculado, NO el YAML.** No puede leer nada que el
   perfilador determinista no haya verificado.
2. **`llm_caller` es un parámetro inyectado.** `pipeline_profiler.py` **no importa
   `pm_llm_client` a nivel de módulo**: quien quiera narración pasa
   `call_llm` (`backend/services/pm/pm_llm_client.py:278`). En tests se pasa un doble.
3. **Cualquier fallo cae a la plantilla.** `call_llm` ya *"Nunca lanza excepción al caller"*
   (`pm_llm_client.py:281-283`) y devuelve `success=False`; igual se envuelve en `try/except`
   por si el caller inyecta otra cosa.
4. **Techo de longitud y una sola línea.** Un texto largo o multilínea se **descarta**.

### Tests PRIMERO — `backend/tests/test_plan247_proposito.py`

| Caso | Qué prueba |
|---|---|
| `test_plantilla_es_determinista` | dos llamadas sobre el mismo perfil → string idéntico |
| `test_plantilla_menciona_ausencia_de_tests` | perfil con `test == (False, CONF_HIGH)` → contiene `"No corre tests."` |
| `test_plantilla_no_miente_si_test_es_desconocido` | perfil con `test == (False, CONF_UNKNOWN)` → **NO** contiene `"No corre tests."` |
| `test_plantilla_sin_fases_lo_dice` | perfil con las 5 fases False → contiene `"No compila"` |
| `test_plantilla_omite_stack_vacio` | `stack.value == ()` → la frase no contiene `"para "` |
| `test_plantilla_respeta_el_techo` | perfil inflado → `len(texto) <= 200` |
| `test_narrate_sin_llm_usa_plantilla` | `narrate_purpose(p)` → `(plantilla, "plantilla")` |
| `test_narrate_con_llm_ok` | doble que devuelve `success=True, parsed_json={"purpose":"X"}` → `("X","llm")` |
| `test_narrate_con_llm_fallido_cae_a_plantilla` | doble con `success=False` → `("...","plantilla")` |
| `test_narrate_con_llm_que_explota_cae_a_plantilla` | doble que lanza `RuntimeError` → `("...","plantilla")` |
| `test_narrate_descarta_texto_largo` | doble que devuelve 500 chars → `"plantilla"` |
| `test_narrate_colapsa_multilinea` | doble que devuelve `"a\nb"` → `"a b"` con fuente `"llm"` |
| `test_narrate_recibe_el_perfil_no_el_yaml` | el doble captura el `spec` y se asserta que `spec.user` es JSON parseable con la clave `"contract_version"` |
| `test_perfil_no_llama_al_llm` (**K4**) | `monkeypatch` de `services.pm.pm_llm_client.call_llm` a una función que lanza; se perfilan los 9 golden → ninguno lanza |

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan247_proposito.py -q
```

### Criterio de aceptación BINARIO

`test_plan247_proposito.py` verde (14 casos), **incluido `test_perfil_no_llama_al_llm`**.

**Flag:** `STACKY_PIPELINE_PROFILER_ENABLED` (default **ON**). **No hay flag nueva para el LLM**:
la narración es un parámetro per-request (§3.1, "cero tokens ociosos"), no una configuración.
**Impacto por runtime:**
- **Codex CLI / Claude Code CLI / GitHub Copilot Pro:** el camino default (plantilla) es idéntico
  en los 3 — es un `str.format` sobre dataclasses.
- **Narración:** depende del backend LLM configurado en `pm_llm_client`. **Fallback explícito en
  los 3:** si el backend no está disponible, `call_llm` devuelve `success=False` y el perfil
  muestra la plantilla con `purpose_source == "plantilla"`. **La UI muestra qué fuente se usó**
  (F5), así que el operador nunca confunde una frase generada con una redactada.
**Trabajo del operador: ninguno** (la narración es `opt-in` por click, y su ausencia no degrada nada)

---

## F4 — Endpoint HTTP, flag y ratchet

**Objetivo (1 frase):** exponer el perfilador por HTTP con guard de flag per-request, degradando
de forma explícita cuando el registro del Plan 246 no está instalado.

**Valor entregado:** el perfil deja de ser una función y pasa a ser una capacidad del producto,
consumible por el frontend (F5), por el 246 y por el 248.

### Archivos

| Acción | Ruta completa |
|---|---|
| **CREAR** | `Stacky Agents/backend/api/pipeline_profiler.py` |
| **EDITAR** | `Stacky Agents/backend/api/__init__.py` |
| **EDITAR** | `Stacky Agents/backend/services/harness_flags.py` |
| **EDITAR** | `Stacky Agents/backend/config.py` |
| **EDITAR** | `Stacky Agents/backend/tests/test_harness_flags.py` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.sh` |
| **EDITAR** | `Stacky Agents/backend/scripts/run_harness_tests.ps1` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan247_endpoint.py` |

### Blueprint (patrón EXACTO copiado de `api/pipeline_generator.py:1-25`)

```python
"""api/pipeline_profiler.py — Blueprint del perfilador de pipelines. Plan 247 F4.

Blueprint registrado SIEMPRE en api/__init__.py sobre api_bp (url_prefix="/api").
url_prefix="/pipeline-profiler" → ruta final /api/pipeline-profiler/...
NO poner url_prefix="/api/pipeline-profiler" (daría /api/api/...) y NO registrar en app.py.
Guard de la flag es PER-REQUEST (abort(404)) — nunca gateado en el registro del blueprint.
"""
from __future__ import annotations
import config as _config
from flask import Blueprint, abort, jsonify, request
from services.pipeline_profiler import profile_pipeline, profile_to_dict, narrate_purpose

bp = Blueprint("pipeline_profiler", __name__, url_prefix="/pipeline-profiler")


@bp.post("/profile")
def profile_route():
    # GOTCHA DURA: se lee la INSTANCIA `_config.config`, no el módulo. getattr del módulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaría en falso).
    if not getattr(_config.config, "STACKY_PIPELINE_PROFILER_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    yaml_text = body.get("yaml_text")
    source_path = str(body.get("source_path") or "")

    if yaml_text is None and body.get("pipeline_id"):
        # Import PEREZOSO: el plan 246 puede no estar instalado. Importarlo a nivel de módulo
        # tumbaría el arranque de api/__init__.py con ImportError.
        try:
            from services.pipeline_inventory import get_pipeline_yaml  # plan 246
        except ImportError:
            return jsonify({"error": "inventory_unavailable",
                            "detail": "el registro de pipelines (plan 246) no está instalado; enviá yaml_text"}), 501
        yaml_text, source_path = get_pipeline_yaml(str(body["pipeline_id"]))

    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_text_requerido",
                        "detail": "enviá yaml_text (string no vacío) o pipeline_id"}), 400

    try:
        profile = profile_pipeline(yaml_text, provider=str(body.get("provider") or "ado"),
                                   source_path=source_path)
    except ValueError as exc:
        return jsonify({"error": "provider_no_soportado", "detail": str(exc)}), 400

    if body.get("narrate") is True:
        from services.pm.pm_llm_client import call_llm      # import perezoso: 0 costo si no se narra
        texto, fuente = narrate_purpose(profile, llm_caller=call_llm)
    else:
        texto, fuente = narrate_purpose(profile, llm_caller=None)

    out = profile_to_dict(profile)
    out["purpose"], out["purpose_source"] = texto, fuente
    return jsonify(out), 200
```

### Registro en `api/__init__.py` (2 líneas, aditivas)

- **Import:** inmediatamente después de la línea `from .pipeline_generator import bp as pipeline_generator_bp`
  (hoy `:44`; **buscar por símbolo**), agregar:
  `from .pipeline_profiler import bp as pipeline_profiler_bp  # Plan 247 — perfilador de pipelines`
- **Registro:** inmediatamente después de `api_bp.register_blueprint(pipeline_generator_bp)`
  (hoy `:117`), agregar:
  `api_bp.register_blueprint(pipeline_profiler_bp)  # Plan 247 — url_prefix="/pipeline-profiler" → /api/pipeline-profiler/...`

### Flag — las **4** ubicaciones exactas (ninguna es opcional)

> **CORRECCIÓN AL DOSSIER.** El §3 del dossier dice *"agregala también a `_CURATED_DEFAULTS_ON`
> en el mismo archivo"* — **es incorrecto**: `_CURATED_DEFAULTS_ON` **no está en
> `services/harness_flags.py`**, está en **`backend/tests/test_harness_flags.py:467`**
> (verificado por `grep -n`). Si se busca en `harness_flags.py` sólo se encuentran comentarios
> que la mencionan.

1. **`services/harness_flags.py`** — nuevo `FlagSpec`, insertado **inmediatamente después** del
   `FlagSpec(key="STACKY_PIPELINE_GENERATOR_ENABLED", …)` (hoy `:2911`, buscar por símbolo):

```python
    # ── Plan 247 — Perfilador de pipelines (stack + anatomía + propósito) ──────
    FlagSpec(
        key="STACKY_PIPELINE_PROFILER_ENABLED",
        type="bool",
        label="Perfilador de pipelines (Plan 247)",
        description=(
            "Plan 247 — Si ON, habilita POST /api/pipeline-profiler/profile: dado un YAML de "
            "pipeline ADO devuelve stack, fases presentes y AUSENTES, artefactos, entornos, "
            "agentes y un propósito en 1 línea. 100% determinista y sin LLM en el camino default. "
            "Default ON (ninguna de las 4 excepciones duras aplica: read-only, no destructivo, "
            "sin prerequisitos nuevos, no reduce seguridad; curada en _CURATED_DEFAULTS_ON de "
            "tests/test_harness_flags.py). "
            "OFF: guard 404 per-request; el blueprint sigue registrado y el resto del panel "
            "queda byte-idéntico."
        ),
        group="global",
        env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
        default=True,
    ),
```

2. **`services/harness_flags.py:207`** — agregar la key a `_CATEGORY_KEYS["epicas_ado"]`
   (`:191`), en la línea siguiente a `"STACKY_PIPELINE_GENERATOR_ENABLED",`:
   `"STACKY_PIPELINE_PROFILER_ENABLED", # Plan 247 — perfilador de pipelines`.
   > **No renombrar la categoría.** `"epicas_ado"` (`CategorySpec` en `:67`, etiqueta
   > *"Épicas, briefs y publicación en ADO"*) es el bucket **histórico** donde ya viven
   > `STACKY_PIPELINE_PROVIDER_ENABLED`, `STACKY_PIPELINE_TRIGGER_ENABLED`,
   > `STACKY_CI_RUN_LEDGER_ENABLED`, `STACKY_CI_FAILURE_TRIAGE_ENABLED` y
   > `STACKY_PIPELINE_GENERATOR_ENABLED`. Renombrarla rompe tests ajenos.
   > **Omitir este paso rompe el meta-test de categorización** (nota en `harness_flags.py:434`).

3. **`config.py`** — atributo de la instancia, junto al del Plan 73 (`:1399`):

```python
    # Plan 247 — Perfilador de pipelines (stack + anatomía + propósito). Default ON.
    # Editable por UI (HarnessFlagsPanel, categoría "Épicas, briefs y publicación en ADO").
    STACKY_PIPELINE_PROFILER_ENABLED: bool = os.getenv(
        "STACKY_PIPELINE_PROFILER_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

4. **`tests/test_harness_flags.py:467`** — agregar `"STACKY_PIPELINE_PROFILER_ENABLED",` al set
   `_CURATED_DEFAULTS_ON` (con su comentario `# ── Plan 247 — perfilador de pipelines ──`).
   **Sin esto, `test_default_known_only_for_curated` queda ROJO.**

> **No se toca `_REQUIRES_MAP_FROZEN`**: la flag **no declara `requires`** (no depende de otra).
> **No se regenera `harness_defaults.env` a mano** (su generador vive en `deployment/`).

### Ratchet — las **DOS** listas (obligatorio)

- `backend/scripts/run_harness_tests.sh` — dentro de `HARNESS_TEST_FILES=(` (`:20`), después de
  `tests/test_plan243_corpus_mirror.py` (hoy `:770`), agregar **5** líneas:
  `tests/test_plan247_profiler_core.py`, `tests/test_plan247_anatomia.py`,
  `tests/test_plan247_proposito.py`, `tests/test_plan247_endpoint.py`,
  `tests/test_plan247_corpus_expectations.py`.
- `backend/scripts/run_harness_tests.ps1` — dentro de `$HarnessTestFiles = @(` (`:13`), después
  de `"tests/test_plan243_corpus_mirror.py"` (hoy `:683`). **⚠ Esa línea NO tiene coma final**
  (verificado): hay que **agregarle la coma** antes de sumar las 5 entradas nuevas, y la última
  de las nuevas queda sin coma.

### Tests PRIMERO — `backend/tests/test_plan247_endpoint.py`

Usa el `client` de Flask del conftest existente (mismo patrón que los tests de endpoint del
Plan 73).

| Caso | Qué prueba |
|---|---|
| `test_flag_off_devuelve_404` | con `config.config.STACKY_PIPELINE_PROFILER_ENABLED = False` (monkeypatch sobre la **instancia**) → `404` |
| `test_yaml_text_perfila_ok` | POST `{"yaml_text": <agendaweb-ci.yml>}` → `200` y `body["stack"]["value"] == ["dotnet_framework"]` |
| `test_sin_yaml_ni_id_devuelve_400` | `{}` → `400`, `error == "yaml_text_requerido"` |
| `test_yaml_vacio_devuelve_400` | `{"yaml_text": "   "}` → `400` |
| `test_provider_gitlab_devuelve_400` | `{"yaml_text":"a: 1","provider":"gitlab"}` → `400`, `error == "provider_no_soportado"` |
| `test_pipeline_id_sin_inventario_devuelve_501` | `{"pipeline_id":"x"}` → `501`, `error == "inventory_unavailable"` (**degradación del 246 verificada**) |
| `test_yaml_roto_devuelve_200_con_parse_error` | YAML inválido → `200` con `parse_error` no nulo (**no rompe**) |
| `test_default_no_narra_con_llm` | sin `narrate` → `purpose_source == "plantilla"` |
| `test_respuesta_es_json_serializable` | el body completo pasa por `json.loads(json.dumps(...))` |

```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan247_endpoint.py -q
# OBLIGATORIOS tras tocar harness_flags.py y crear tests nuevos:
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

> **Rojos ajenos:** `test_harness_flags.py` trae **4 fallos preexistentes** en
> `test_harness_flags_help` (dossier §4). **Verificá TU entrada de forma aislada** con
> `-k "curated or category or STACKY_PIPELINE_PROFILER"` y compará el conteo de fallos **antes y
> después** de tu cambio: tiene que ser **el mismo**. No los "arregles".

### Criterio de aceptación BINARIO

`test_plan247_endpoint.py` verde (9 casos) **Y** `test_harness_ratchet_meta.py` verde **Y**
`test_harness_flags.py` con **exactamente el mismo número de fallos que antes** del cambio.

**Flag:** `STACKY_PIPELINE_PROFILER_ENABLED`, default **ON** (justificación de las 4 excepciones
duras en el propio `description` del `FlagSpec`).
**Impacto por runtime:** el endpoint es Flask puro, idéntico en los 3. El único ramal
runtime-dependiente es `narrate: true`, ya cubierto con fallback en F3.
**Trabajo del operador: ninguno** (default ON; si quiere apagarlo, es un toggle en el panel de flags)

---

## F5 — Frontend: modelo puro, tarjeta y capstone contra los 9 golden

**Objetivo (1 frase):** que el operador **vea** el perfil junto al YAML, y fijar el criterio
binario del plan contra los 9 pipelines reales.

**Valor entregado:** el plan deja de ser una API y se convierte en algo que el operador usa; y
queda blindado contra regresiones por una tabla de expectativas escrita a mano.

### Archivos

| Acción | Ruta completa |
|---|---|
| **CREAR** | `Stacky Agents/frontend/src/devops/pipelineProfileModel.ts` |
| **CREAR** | `Stacky Agents/frontend/src/devops/__tests__/pipelineProfileModel.test.ts` |
| **CREAR** | `Stacky Agents/frontend/src/components/devops/PipelineProfileCard.tsx` |
| **EDITAR** | `Stacky Agents/frontend/src/api/endpoints.ts` |
| **EDITAR** | `Stacky Agents/frontend/src/components/devops/PipelineYamlPreview.tsx` |
| **CREAR** | `Stacky Agents/backend/tests/test_plan247_corpus_expectations.py` |

### Modelo puro — `frontend/src/devops/pipelineProfileModel.ts`

**Toda la lógica testeable va acá, cero lógica en el `.tsx`** (regla del dossier §2.3).

```ts
export type Confidence = 'alta' | 'media' | 'desconocido';
export interface EvidenceDto { location: string; detail: string; }
export interface ProfileFieldDto<T> { value: T; confidence: Confidence; evidence: EvidenceDto[]; }
export interface PipelineProfileDto {
  contract_version: string; source_path: string;
  stack: ProfileFieldDto<string[]>;
  phases: Record<string, ProfileFieldDto<boolean>>;
  artifacts_published: ProfileFieldDto<string[]>;
  artifacts_consumed: ProfileFieldDto<string[]>;
  environments: ProfileFieldDto<Array<{ name: string; kind: string; resolved: boolean; possible_values: string[] }>>;
  agents: ProfileFieldDto<Array<{ kind: string; name: string; os: boolean | null }>>;
  triggers: ProfileFieldDto<string[]>;
  purpose: string; purpose_source: 'plantilla' | 'llm';
  not_understood: string[]; parse_error: string | null;
}
export interface ProfileRow { label: string; text: string; confidence: Confidence; evidence: string[]; tone: 'ok' | 'gap' | 'unknown'; }

export const PHASE_LABELS: Record<string, string>;   // build→'Compila', test→'Testea', …
export const STACK_LABELS: Record<string, string>;   // dotnet_framework→'.NET Framework', …
export function phaseRows(p: PipelineProfileDto): ProfileRow[];
export function summaryRows(p: PipelineProfileDto): ProfileRow[];
export function gapHeadline(p: PipelineProfileDto): string | null;   // "No corre tests" | null
export function confidenceLabel(c: Confidence): string;
```

Reglas del modelo (todas testeadas):
- `phaseRows` devuelve **una fila por fase de `PHASE_LABELS`**, con `tone`:
  `'ok'` si `value === true`; `'gap'` si `value === false && confidence === 'alta'`;
  `'unknown'` si `confidence === 'desconocido'`. **La ausencia verificada se ve distinta de la
  ausencia dudosa** — es el punto entero del plan.
- `gapHeadline` devuelve `'No corre tests'` **sólo** con `phases.test.value === false &&
  phases.test.confidence === 'alta'`.
- `summaryRows` nunca imprime `[object Object]`: los entornos y agentes se formatean con
  funciones propias, testeadas.
- **`parse_error` no nulo ⇒ todas las funciones devuelven `[]` / `null`** (nada de renderizar
  medio perfil de un YAML roto).

### Cliente HTTP — `frontend/src/api/endpoints.ts`

Insertar **inmediatamente después** del bloque `export const PipelineGenerator = { … };`
(hoy `endpoints.ts:4426`; **buscar por símbolo**, ver aviso §2.5). Si el bloque no se encuentra,
agregar al final del archivo.

```ts
/** Plan 247 — perfilador de pipelines (determinista; `narrate` es opt-in y usa LLM). */
export const PipelineProfiler = {
  profile: (body: { yaml_text?: string; pipeline_id?: string; source_path?: string; provider?: string; narrate?: boolean }) =>
    api.post<PipelineProfileDto>("/api/pipeline-profiler/profile", body),
};
```

> **Gotcha verificado:** `api.post` **lanza** en cualquier respuesta non-2xx
> (`frontend/src/api/client.ts:155`, `throw new Error(...)`). El componente **debe** envolver la
> llamada en `try/catch` y mostrar el error; **no existe `rawGet`** en `client.ts` (sólo
> `rawPost`, `:44`), por eso el endpoint es POST.

### Componente — `frontend/src/components/devops/PipelineProfileCard.tsx`

**Presentacional puro, sin fetch adentro** (así lo puede montar tanto `PipelineYamlPreview` hoy
como `PipelineInventorySection` del Plan 246 mañana, sin cambios):

```tsx
export interface PipelineProfileCardProps {
  profile: PipelineProfileDto | null;
  loading: boolean;
  error?: string | null;
  /** undefined ⇒ no se muestra el botón de narrar (p. ej. si no hay backend LLM). */
  onNarrate?: () => void;
}
export const PipelineProfileCard: React.FC<PipelineProfileCardProps> = (…) => …
```

Requisitos de render (verificados por el test del modelo, no por RTL — §"Riesgos" R4):
- Titular grande = `profile.purpose`, con una etiqueta chica que diga **`plantilla`** o **`IA`**
  según `purpose_source`. **El operador siempre sabe si la frase la escribió una máquina de
  plantillas o un modelo.**
- Filas de fases con el `tone` del modelo (`ok` / `gap` / `unknown`).
- Chip por cada `not_understood` con el texto
  `"no interpretado: matrix"` → **declarar lo que no se entendió es parte del producto**.
- Botón `"Redactar con IA"` sólo si `onNarrate` está definido (HITL: un click, una pipeline).
- **Cero `style={{ }}` inline**: el ratchet `uiDebtRatchet` exige alcance 0 en archivos `.tsx`
  nuevos. Usar `devops.module.css` (ya importado por los componentes hermanos) o un
  `PipelineProfileCard.module.css` propio, con `var(--token)`, **nunca literales HEX**.

### Montaje — `PipelineYamlPreview.tsx` (elección deliberada)

Se monta la tarjeta **debajo del preview ADO** en
`frontend/src/components/devops/PipelineYamlPreview.tsx` (154 líneas, Plan 87 F5). Motivos:

1. **Funciona hoy, sin el Plan 246**: ese componente siempre tiene un YAML en la mano — el que
   acaba de renderizar con `PipelineGenerator.preview` (`:57`).
2. **Valor inmediato y real**: el operador que está *armando* una pipeline ve al instante
   *"compila pero no corre tests"* — antes de commitearla.
3. **Cero colisión**: no está reservado por ningún plan de la serie, y no es
   `PipelineBuilderSection.tsx` (804 líneas, que van a tocar el 244 y el 250).

Diff conceptual (aditivo; el render actual queda intacto si el fetch falla):

```tsx
// + import { PipelineProfiler } from '../../api/endpoints';
// + import { PipelineProfileCard } from './PipelineProfileCard';
// + const [profile, setProfile] = useState<PipelineProfileDto | null>(null);
// + const [profileError, setProfileError] = useState<string | null>(null);
// dentro de refreshPreview(), DESPUÉS de setPreview(result):
// +   try { setProfile(await PipelineProfiler.profile({ yaml_text: result.ado })); setProfileError(null); }
// +   catch (e) { setProfile(null); setProfileError(e instanceof Error ? e.message : 'perfil no disponible'); }
// en el JSX, después del bloque del preview ADO:
// + <PipelineProfileCard profile={profile} loading={loading} error={profileError} />
```

> **Contrato UX respetado** (Plan 106 F5, `PipelineBuilderSection.tsx:382-383`): la tarjeta
> **sólo muestra**; no pre-rellena ni pisa nada de lo que el operador escribió. Si la flag está
> OFF, el endpoint devuelve 404, `api.post` lanza, el `catch` deja `profile = null` y la tarjeta
> **no se renderiza**: el panel queda **byte-idéntico** a hoy.

### CAPSTONE — `backend/tests/test_plan247_corpus_expectations.py`

**Este es el criterio binario del plan.** La tabla está escrita a mano acá abajo, derivada de
parsear los 9 golden con `yaml.safe_load` el 2026-07-26. Se copia **tal cual** al test.

```python
# Plan 247 F5 — expectativas escritas a mano contra los 9 pipelines REALES.
# Formato: nombre -> (stack, build, test, publish_artifact, deploy, publicados, consumidos,
#                     entornos_literales, agentes, triggers, not_understood)
EXPECTATIVAS = {
 "agendaweb-ci.yml": (
   ("dotnet_framework",), True, True, True, False,
   ("$(ARTIFACT_NAME)",), (), (), (("hosted","windows-2022"),), ("manual",), ()),

 "bootstrap-server-environment.yml": (
   (), False, False, True, False,
   ("BootstrapLogs-${{ parameters.targetEnvironment }}-$(Build.BuildNumber)",), (),
   ("${{ parameters.targetEnvironment }}",),
   (("self_hosted","${{ parameters.agentPool }}"),), ("manual",), ("compile_time_expression",)),

 "cd-deploy-test.yml": (
   ("dotnet_framework",), True, False, True, True,
   ("AgendaWeb","Batch","DeployLogs-AgendaWeb-$(Build.BuildNumber)","DeployLogs-Batch-$(Build.BuildNumber)"),
   ("AgendaWeb","Batch"), ("Test",),
   (("hosted","windows-2022"),("self_hosted","TEST-Server")), ("push",), ()),

 "ci-batch.yml": (
   ("dotnet_framework",), True, False, False, False,
   (), (), (), (("hosted","windows-2022"),), ("push","pr"), ("matrix",)),

 "ci-cd-online.yml": (
   ("dotnet_framework",), True, True, True, False,
   ("AgendaWeb-drop",), (), (), (("hosted","windows-2022"),), ("push",), ()),

 "ci-dacpac.yml": (
   ("dotnet_core","sql_dacpac"), True, False, True, False,
   ("dacpac-$(Build.BuildNumber)",), (), (), (("hosted","ubuntu-latest"),), ("push","pr"), ()),

 "nightly-build-online.yml": (
   ("dotnet_framework",), True, True, True, False,
   ("AgendaWeb-nightly-$(Build.BuildNumber)",), (), (), (("hosted","windows-2022"),),
   ("scheduled",), ()),

 "pr-validation-online.yml": (
   ("dotnet_framework",), True, True, False, False,
   (), (), (), (("hosted","windows-2022"),), ("push","pr"), ()),

 "security-scan-online.yml": (
   (), False, False, True, False,
   ("vulnerability-report-$(Build.BuildNumber)",), (), (), (("hosted","windows-2022"),),
   ("push","pr","scheduled"), ()),
}
```

**Campos EXIGIDOS EXACTOS (8 por pipeline × 9 = 72 aserciones):** `stack`, `phases["build"]`,
`phases["test"]`, `phases["publish_artifact"]`, `phases["deploy"]`, `artifacts_published`,
`artifacts_consumed` + `environments` (literales), `agents`, `triggers`, `not_understood`.

**Campos que NO se exigen exactos, y por qué (esto es deliberado — ver R1):**

| Campo | Por qué no entra en la tabla | Cómo se cubre igual |
|---|---|---|
| `phases["package"]` | Su señal es **textual** sobre `msbuildArgs`/`Contents`, no una ref de tarea. Fijarla contra 9 pipelines reales convertiría un cambio de redacción del YAML en un test rojo. | 2 tests sintéticos en F2 (`test_package_tiene_confianza_media` + un negativo) |
| `purpose` (texto) | Es prosa; assertarla palabra por palabra es un test de redacción, no de comportamiento. | Se assertan **propiedades**: no vacío, 1 línea, ≤200 chars, `purpose_source == "plantilla"`, e **idéntico en dos corridas** (determinismo) |
| `EnvironmentRef.kind` de los no resueltos | Es `"desconocido"` por construcción. | `test_entorno_parametrizado_no_se_adivina` (F2) |
| `AgentPool.os` | `_pool_os_is_windows` ya está testeado en el Plan 243. | Se assertan sólo `kind` y `name` |

**Tests del capstone:**

| Caso | Qué prueba |
|---|---|
| `test_los_nueve_golden_estan` | `len(list(GOLDEN.glob("*.yml"))) == 9` — si alguien agrega uno, el capstone avisa en vez de ignorarlo |
| `test_expectativas_cubren_los_nueve` | `set(EXPECTATIVAS) == {p.name for p in GOLDEN.glob("*.yml")}` |
| `test_perfil_por_pipeline[<nombre>]` (parametrizado ×9) | las 8 aserciones exactas de la tabla |
| `test_ningun_perfil_lanza` | los 9 perfilan sin excepción y con `parse_error is None` |
| `test_sin_valor_sin_confianza` (**K3**) | para los 9, **todos** los `ProfileField` cumplen `field_is_coherent` |
| `test_proposito_es_determinista_y_acotado` | los 9: `purpose` no vacío, sin `\n`, ≤200 chars, `purpose_source == "plantilla"`, e idéntico al perfilar dos veces |
| `test_ausencia_de_tests_declarada` (**K2**) | `cd-deploy-test.yml`, `ci-batch.yml`, `ci-dacpac.yml`, `bootstrap-…`, `security-scan-…` → `phases["test"] == (False, CONF_HIGH)` |
| `test_perfila_lo_que_no_entiende` (**K5**) | `ci-batch.yml` y `bootstrap-…` tienen `not_understood` no vacío **Y** `stack`/`phases`/`agents` completos |
| `test_los_nueve_en_menos_de_un_segundo` (**K6**) | `time.monotonic()` alrededor del bucle < 1.0 s |

```powershell
# BACKEND — capstone
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan247_corpus_expectations.py -q

# FRONTEND — modelo puro
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineProfileModel.test.ts
npx tsc --noEmit
```

> **Recordatorio del dossier §4:** el frontend **no tiene script `test`**; `npm test` **falla**.
> Se usa `npx vitest run <archivo>`. Y se corre **por archivo**: la corrida completa de vitest
> tiene contaminación cross-file conocida en esta casa.

### Criterio de aceptación BINARIO

`test_plan247_corpus_expectations.py` verde con las **72 aserciones exactas** de la tabla
**Y** `pipelineProfileModel.test.ts` verde **Y** `npx tsc --noEmit` sin errores nuevos.

**Flag:** `STACKY_PIPELINE_PROFILER_ENABLED` (default **ON**). Con la flag OFF el endpoint da
404, el `catch` deja `profile = null` y `PipelineYamlPreview` renderiza **exactamente como hoy**.
**Impacto por runtime:** el frontend no depende del runtime. El backend del capstone es puro.
**Fallback:** el `catch` del componente (ver arriba).
**Trabajo del operador: ninguno**

---

## 4. Gestión de errores (transversal)

| Situación | Comportamiento | Dónde |
|---|---|---|
| YAML sintácticamente inválido | `empty_profile(source_path, "el YAML no se pudo parsear: <1ª línea>")`, HTTP **200** | F1 |
| YAML que no es un mapa (lista, string) | `empty_profile(..., "no es un documento de pipeline")`, HTTP **200** | F1 |
| YAML > 512 KB | `empty_profile(..., "supera 512 KB")` sin parsear, HTTP **200** | F1 |
| `provider != "ado"` | `ValueError` en el servicio → **400** `provider_no_soportado` en el endpoint | F1/F4 |
| Falta `yaml_text` y `pipeline_id` | **400** `yaml_text_requerido` | F4 |
| `pipeline_id` sin Plan 246 instalado | **501** `inventory_unavailable` con instrucción accionable | F4 |
| Flag OFF | **404** per-request (nunca gateado en el registro del blueprint) | F4 |
| LLM caído / sin backend / texto inválido | plantilla determinista, `purpose_source == "plantilla"`, **HTTP 200** | F3 |
| Fetch del perfil falla en la UI | `catch` → `profile = null` → la tarjeta no se renderiza; el preview queda intacto | F5 |

**Ningún camino de error devuelve un perfil parcial que parezca completo.** O hay perfil, o hay
`parse_error` poblado y todos los campos vacíos con `CONF_UNKNOWN`.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Severidad | Mitigación (concreta, dentro del plan) |
|---|---|---|---|
| **R1** | **La trampa C14 del 243:** un capstone "9/9 perfecto" que en realidad exige alcance ilimitado. | **ALTA** | La tabla de §F5 **declara exactamente qué 8 campos se exigen exactos y cuáles no**, con la razón de cada exclusión. Ningún campo excluido queda sin cobertura: se cubre con tests sintéticos. **No hay ninguna frase del tipo "se agrega la construcción faltante"**. Si el perfilador no reproduce la tabla, se **corrige el perfilador o se corrige la tabla con evidencia** — nunca se amplía el alcance. |
| **R2** | Un pipeline con `template:`/`extends:` hace que el perfilador declare ausencias falsas ("no corre tests" cuando los tests están en el template). | **ALTA** | Regla `_HIDES_STEPS` (F2): esas dos construcciones degradan **toda** ausencia a `desconocido`. `test_template_degrada_toda_ausencia`. **0 usos en el corpus** ⇒ no afecta las 72 aserciones, pero protege al primer pipeline real que las use. |
| **R3** | Alguien "mejora" el perfilador leyendo el YAML con regex y vuelve a meter las 2 tareas comentadas (`agendaweb-ci.yml:143`, `ci-dacpac.yml:103` — la causa raíz de ADO-369). | **ALTA** | El perfilador **sólo** consume `yaml.safe_load` + `extract_task_dicts` (`cicd_task_catalog.py:268`), donde los comentarios no existen por construcción. Test explícito: `test_task_comentada_no_entra_al_perfil` sobre `agendaweb-ci.yml` → `IISWebAppDeploymentOnMachineGroup@0` **no** aparece en ninguna evidencia y `phases["deploy"] is False`. |
| **R4** | **RTL/jsdom no están instalados** en este repo ⇒ el render de `PipelineProfileCard.tsx` no es testeable automáticamente. | MEDIA | **Toda** la lógica vive en `pipelineProfileModel.ts` (testeado con vitest). El `.tsx` es una proyección sin ramas de negocio. Gate real del componente: `npx tsc --noEmit` + smoke visual manual. **Declarado, no disimulado.** |
| **R5** | Editar `cicd_semantic_rules.py` (F0) rompe el Plan 243. | MEDIA | El cambio son **2 líneas de alias** después de `_iter_steps`; los nombres privados y sus cuerpos no se tocan. Comando de no-regresión obligatorio en el criterio de F0, con conteo de tests antes/después. |
| **R6** | `endpoints.ts` vuelve a desfasar anclajes (ya pasó 2 veces: 243 dijo `:4368`, hoy es `:4426`). | MEDIA | F5 instruye **buscar por símbolo** `PipelineGenerator` y da un fallback explícito ("si no aparece, agregar al final del archivo"). Aviso destacado en §2.5. |
| **R7** | Olvidar una de las 4 ubicaciones de la flag ⇒ meta-tests rojos y culpar al plan. | MEDIA | F4 enumera las 4 con archivo y línea, **corrige el error del dossier** sobre dónde vive `_CURATED_DEFAULTS_ON`, y da el comando de verificación aislada frente a los 4 rojos ajenos. |
| **R8** | El Plan 246 llega después y ambos definen `get_pipeline_yaml` con firmas distintas. | BAJA | El import es **perezoso y dentro de un `try/except ImportError`**, y la firma esperada está escrita literalmente en F4 (`get_pipeline_yaml(pipeline_id) -> (yaml_text, source_path)`). Si el 246 usa otra firma, falla **un** test del 247 con mensaje claro, no el arranque del backend. |
| **R9** | Perfilar 40 pipelines del inventario cuesta 40 llamadas a LLM. | BAJA | **Imposible por diseño:** `narrate` es per-request y default `false`; `pipeline_profiler.py` no importa `pm_llm_client` a nivel de módulo. `test_perfil_no_llama_al_llm` (K4) lo fija con un `call_llm` que explota. |
| **R10** | El operador confunde una frase de plantilla con una redactada por IA. | BAJA | `purpose_source` viaja en el DTO y la tarjeta muestra la etiqueta `plantilla` / `IA` (F5). |

---

## 6. Fuera de scope (nombrando los otros planes de la serie)

Este plan **no hace** nada de lo siguiente. Cada ítem tiene dueño:

- **Descubrir pipelines** (definiciones ADO + GitLab + YAMLs del repo, estado de última corrida,
  registro unificado, listado en el panel) → **Plan 246**. El 247 **consume** su registro por
  `pipeline_id` y **degrada a `501` explícito** si no está instalado (§3.3).
- **Emitir hallazgos de seguridad, malas prácticas o recomendaciones** (`SEC001..SECnn`,
  secretos en claro, imagen sin pin, `allow_failure` que enmascara, deploy a prod sin aprobación,
  cache ausente, jobs serializados) → **Plan 248**. El 247 **describe**, no juzga: no emite ni un
  `SemanticFinding`. El 248 se monta **sobre este perfil** en vez de re-parsear.
- **Reglas semánticas y catálogo de constructos de GitLab** (`GL001..GLnn`, endurecer
  `parse_gitlab_yaml`) → **Plan 249**. Por eso `profile_pipeline(provider="gitlab")` **lanza
  `ValueError`** en vez de devolver un perfil vacío que parezca válido.
- **Editar/optimizar pipelines existentes por lenguaje natural** (patch quirúrgico, diff visible,
  commit HITL) → **Plan 250**. El 247 es **read-only absoluto**: no escribe un solo byte.
- **Matriz de entornos y los valores que sólo el operador conoce** (credenciales, servidores,
  rutas, resolución contra la caja fuerte del Plan 94) → **Plan 251**. El 247 reporta el
  `environment:` **literal sin resolver** y los `possible_values` declarados; **no resuelve
  `$(VAR)` ni elige un valor**.
- **Paquete de entrega, README operativo y frontera de capacidades** (`.zip`, prerequisitos,
  qué queda manual) → **Plan 252**.
- **Generar pipelines desde lenguaje natural** → **Planes 243 (F0..F3.5, ya implementado) y 244
  (F4..F9)**. El perfilador no genera nada.
- **Ampliar `pipeline_stack_detector.py`** (Plan 97 F2) → **de nadie**: se decidió
  explícitamente **no tocarlo** (§2.1).

---

## 7. Glosario, orden de implementación y DoD binaria

### 7.1 Glosario

| Término | Definición operativa en este plan |
|---|---|
| **Perfil** | `PipelineProfile`: qué es, qué hace y con qué está hecha una pipeline. Descriptivo, nunca prescriptivo. |
| **Anatomía** | El dict `phases`: qué fases tiene **y cuáles no**. |
| **Ausencia verificada** | `ProfileField(False, "alta", <evidencia>)`: el documento se leyó completo y no hay señal de esa fase. |
| **Ausencia dudosa** | `ProfileField(False, "desconocido", …)`: el documento usa `template`/`extends` y los pasos podrían estar en otro archivo. |
| **Evidencia** | `Evidence(location, detail)`: dónde en el YAML y qué dato exacto sostiene el campo. |
| **Confianza** | `alta` (ref de tarea o clave del YAML) / `media` (señal textual sobre un input) / `desconocido` (no determinable). |
| **`not_understood`** | Salida literal de `scan_unsupported()`: construcciones ADO que el modelo no cubre. **Se declara, no se oculta.** |
| **Narración** | Reescritura del propósito con LLM. **Opt-in, per-request, degradable, sin flag propia.** |
| **Corpus dorado** | Los 9 `.yml` de `backend/tests/fixtures/cicd_nl/golden/` (pipelines ADO reales en producción, vendorizados por el Plan 243 F0). |

### 7.2 Orden de implementación (estricto — cada fase depende de la anterior)

```
F0 (contrato + alias)  →  F1 (stack/agentes/triggers)  →  F2 (anatomía/artefactos/entornos)
                       →  F3 (propósito)  →  F4 (endpoint/flag/ratchet)  →  F5 (UI + capstone)
```

F0..F3 son **backend puro y entregan valor solas** (el 248 podría montarse sobre F0..F2 sin la
UI). F4 hace la capacidad consumible. F5 la hace visible y la blinda.

### 7.3 Definición de Hecho (DoD) — **binaria**

Se marca HECHO **si y sólo si** las 10 casillas dan verde:

- [ ] **1.** Existen exactamente **5 archivos de test backend nuevos**:
      `test_plan247_profiler_core.py`, `test_plan247_anatomia.py`, `test_plan247_proposito.py`,
      `test_plan247_endpoint.py`, `test_plan247_corpus_expectations.py`
      — **y 1 frontend**: `src/devops/__tests__/pipelineProfileModel.test.ts`. **Total: 6.**
- [ ] **2.** Los **5** backend están registrados **en las DOS listas del ratchet**
      (`run_harness_tests.sh:20` y `run_harness_tests.ps1:13`) y
      `.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q` está **verde**.
- [ ] **3.** Los 5 archivos de test backend pasan, **corridos de a uno**:
      ```powershell
      cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
      .venv\Scripts\python.exe -m pytest tests/test_plan247_profiler_core.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan247_anatomia.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan247_proposito.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan247_endpoint.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan247_corpus_expectations.py -q
      ```
- [ ] **4.** **No regresión** del motor de pipelines existente:
      ```powershell
      .venv\Scripts\python.exe -m pytest tests/test_plan73_pipeline_spec.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan243_task_catalog.py -q
      .venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q
      ```
      Los 4 verdes, **con el mismo número de tests pasados que antes** de tocar nada.
- [ ] **5.** `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` tiene
      **exactamente el mismo número de fallos que antes** del cambio (los 4 ajenos de
      `test_harness_flags_help`, ni uno más).
- [ ] **6.** Frontend verde: `npx vitest run src/devops/__tests__/pipelineProfileModel.test.ts`
      **y** `npx tsc --noEmit` sin errores nuevos.
- [ ] **7.** **Las 72 aserciones exactas** de la tabla de §F5 pasan sobre los 9 golden.
- [ ] **8.** `test_perfil_no_llama_al_llm` (K4) y `test_sin_valor_sin_confianza` (K3) están
      verdes: **cero LLM en el camino default, cero campos sin evidencia**.
- [ ] **9.** La flag `STACKY_PIPELINE_PROFILER_ENABLED` está en las **4** ubicaciones
      (`harness_flags.py` FlagSpec, `harness_flags.py` `_CATEGORY_KEYS["epicas_ado"]`,
      `config.py`, `tests/test_harness_flags.py` `_CURATED_DEFAULTS_ON`) con `default=True`,
      **es editable desde la UI** (`env_only=False`), y con la flag en `False` el panel de
      pipelines renderiza **exactamente como hoy**.
- [ ] **10.** **Smoke visual manual** (no automatizable, R4): abrir el panel DevOps → sección
      Pipelines → armar cualquier spec → el preview ADO muestra debajo la tarjeta con el
      propósito, las 5 filas de fases (distinguiendo ausencia verificada de ausencia dudosa) y
      la etiqueta `plantilla`. **Adjuntar el resultado al cerrar el plan.**

> **Recordatorio de la casa (§4 del dossier):** los tests de backend se corren **por archivo**
> (la suite completa se contamina) y con **`.venv`** (Python 3.13.5), **no** con `venv`
> (3.11.9). En el frontend, `npm test` **no existe**: es `npx vitest run <archivo>`.
