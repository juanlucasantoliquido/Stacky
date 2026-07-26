# Plan 243 — Del lenguaje natural al pipeline: generador NL en el panel de pipelines, con pasos `task:` reales y gates honestos

> Estado: **v3 · CRITICADO INDEPENDIENTEMENTE (v2 → v3)** — VEREDICTO SOBRE v2: **RECHAZADO** (3 bloqueantes). Estado de v3 tras aplicar los fixes: **APROBADO-CON-CAMBIOS** (2026-07-26). Pipeline: proponer ✓ → criticar v1→v2 ✓ → **criticar independiente v2→v3 ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: Claude Opus 5 (1M context). Juez v2: **el mismo agente, en la misma corrida** en que propuso el plan — por lo tanto **v2 nunca tuvo revisión independiente y ninguno de sus anclajes `archivo:línea` fue verificado por un tercero**. Juez v3: agente independiente que **abrió cada archivo y verificó cada anclaje** (tabla en Parte B.2).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; **el núcleo F0–F3 y F5–F6 NO usa LLM** — sólo F4 lo usa, y de forma acotada y mockeable).
> Origen: **pedido textual del operador** — *"un sistema que permita crear pipelines mediante instrucciones en lenguaje natural […] interpretar la solicitud, generar el pipeline, configurar sus dependencias, validar su funcionamiento, desplegarlo y dejarlo completamente operativo"*, más la aclaración *"el plan es para añadir en Stacky Agents en el panel de pipelines"*.

**CHANGELOG v1 → v2 (12 hallazgos; los 4 más importantes salieron de leer el panel que ya existe):**

- **C1 (BLOQUEANTE, resuelto):** todo el panel es **`script:`-only** y no puede expresar un `- task: X@N`, que es como están escritos el 100% de los pipelines reales de Azure DevOps del ecosistema. `StepDraft` (`specBuilder.ts:9`), los presets (`pipelinePresets.ts:30-32,50-53,71-73`) y el emisor `_spec_to_ado_doc` (`pipeline_renderers.py:65`, emite literalmente `{"script":…, "displayName":…}`) coinciden en la misma limitación. Un generador NL montado encima produciría YAML válido e **inútil**. F1/F2 lo arreglan **para todo el panel**, no sólo para la feature nueva.
- **C2 (BLOQUEANTE, resuelto):** validez sintáctica ≠ pipeline correcto, y hay **precedente real documentado** (incidente ADO-369). F3 agrega reglas semánticas por perfil.
- **C3 (IMPORTANTE, resuelto) — [reducción de alcance por reuso]:** v1 proponía escribir un materializador (archivo + commit + PR). **Ya existe y es HITL:** `PipelineGenerator.commit` (`endpoints.ts:4295-4298` **← anclaje corregido en v3 a `:4376`, ver C16**, "commit HITL con confirm") y `CommitPipelineModal.tsx`. También existe el preview (`endpoints.ts:4291-4293` **← real `:4371`**) y el panel de lint (`PipelineLintPanel.tsx`). v2 **borra** esa fase y reusa el flujo.
- **C4 (IMPORTANTE, resuelto) — [alineación con el contrato UX del panel]:** el panel ya tiene IA, con un contrato explícito del Plan 106 F5: *"pide sugerencias al modelo local y PRE-RELLENA solo lo que está vacío (KPI-5, HITL): nunca pisa lo que el operador ya escribió"* (`PipelineBuilderSection.tsx:382-383`). v1 ignoraba esto y proponía una página nueva. v2 entra **por el mismo lenguaje**: la caja NL rellena un draft que el operador edita en el builder, muestra justificación, y **nunca pisa** trabajo manual.
- **C5..C12:** ver Parte B (falso verde, alucinación de tareas, inyección hacia agentes self-hosted, determinismo, colisión de nombres, costo sin techo, observabilidad, rollback).

**CHANGELOG v2 → v3 (13 hallazgos, C13..C25; los 3 bloqueantes salieron de correr el corpus y de abrir los archivos que v2 citaba de memoria):**

- **C13 (BLOQUEANTE, resuelto):** F3 se contradecía consigo mismo. `nightly-build-online.yml:110` tiene un `- script: |` crudo real, así que **RS008 y `test_corpus_dorado_sin_errores` no podían ser verdaderos a la vez** (y RS006 tampoco, porque en la corrida de tests `repo_root` no es RSPACIFICO). Resuelto con `mode="audit" | "nl_strict"` en `check_semantics`.
- **C14 (BLOQUEANTE, resuelto):** el "round-trip 9/9" de F2 exigía un AST completo de ADO YAML (`matrix` en `ci-batch.yml:58-59`, **17** expresiones `${{ }}` en `bootstrap-server-environment.yml`), con la frase-trampa *"se agrega la construcción faltante — no se relaja el test"* = alcance ilimitado disfrazado de criterio binario. Partido en dos gates honestos y acotados.
- **C15 (BLOQUEANTE, resuelto):** F1 pedía validar el catálogo dentro de `_validate_spec(spec)`, que **no recibe ningún `profile`** — inimplementable sin inventar, y además acoplaba el modelo genérico del Plan 73 al catálogo ADO/.NET. La validación de catálogo se movió a F3.
- **C16 (IMPORTANTE, resuelto):** los **4** anclajes de `endpoints.ts` estaban desfasados ~77 líneas (`:4291-4293` es `PrReview`, no `PipelineGenerator`). Corregidos + regla de anclaje nueva (§7.2).
- **C17..C25:** ver Parte B.2 (comando de test inexistente y trampa de los dos venvs; DoD que contaba 8 archivos donde las fases crean 11; F8 disparaba la primera corrida sin confirmación en el caso más común; extracción del catálogo que podía incorporar la mismísima tarea que RS002 prohíbe; `fromParsedSpec` es un cast no-op; corpus vendorizado sin procedencia ni guardia de deriva; huella de ADO-369 sin registrar; corte de alcance 243/244).

---

## 0. La tesis del plan (leer esto antes que nada)

El panel de pipelines de Stacky ya tiene **casi todo el camino construido**: builder gráfico
(`PipelineBuilderSection.tsx`, 804 líneas), presets por stack (Plan 97), snippets y recetas,
lint con autofix (Plan 186), preview ADO/GitLab, commit HITL con confirm (Plan 73 F5), doctor
de fallos (Plan 96) y trigger/monitor de corridas (Plan 72).

Lo que **falta** son dos cosas, y una es mucho más grave que la otra:

1. **La entrada en lenguaje natural** — hoy hay que armar el pipeline paso a paso, o partir de
   un preset genérico. Esto es lo que pidió el operador.
2. **La capacidad de emitir pasos `task:`** — y esto es un agujero que ya existe hoy,
   independientemente del lenguaje natural. Los presets emiten `dotnet restore` como `script:`,
   pero **ningún pipeline real de Azure DevOps del ecosistema RS está escrito así**: todos usan
   `- task: VSBuild@1` con `inputs:`, porque compilar WebForms .NET Framework 4.8.1 requiere
   MSBuild vía la tarea, no `dotnet build`.

> **La tesis:** agregar lenguaje natural encima de un modelo que no puede expresar pipelines
> reales multiplicaría el problema en vez de resolverlo — produciría YAML plausible, bien
> formado, y que no compila nada. Por eso **F0–F3 van antes que el LLM**, y por eso F0–F3
> tienen valor entregable por sí solas: arreglan el panel para todos sus usuarios actuales.

---

## 1. Objetivo y valor

Que el operador escriba en el panel *"compilá AgendaWeb.sln en Release, corré los tests y
publicá el artefacto; que dispare sólo en push a main cuando cambie algo bajo trunk/OnLine"*
y obtenga un **draft completo cargado en el builder gráfico**, con pasos `task:` reales,
validado por una escalera de gates con nombres honestos, listo para revisar, commitear con el
flujo HITL existente y —previa confirmación— registrar y ejecutar hasta quedar verde.

**Valor medible:** de "armar 130 líneas de YAML a mano" a "revisar un draft ya validado".
Y como efecto colateral, el panel pasa a poder generar pipelines .NET Framework reales, que
hoy **no puede** (C1).

---

## 2. Evidencia (todo verificado por lectura directa)

### 2.1 Lo que YA existe y este plan reutiliza sin tocar

| Pieza | Anclaje | Qué aporta |
|---|---|---|
| Builder gráfico | `frontend/src/components/devops/PipelineBuilderSection.tsx:64` | Editor de stages/jobs/steps, estado `spec` (`:71`) |
| Modelo de draft | `frontend/src/devops/specBuilder.ts:9,17,28,34` | `StepDraft`, `JobDraft`, `StageDraft`, `PipelineSpecDraft` |
| Helpers de draft | `specBuilder.ts:107,161,185` | `validateSpecLocal`, `toSpecDict`, `fromParsedSpec` |
| Presets por stack | `frontend/src/devops/pipelinePresets.ts:102-107` | 4 presets (Plan 97 F0) |
| Snippets / recetas | `frontend/src/devops/pipelineStepSnippets.ts`, `pipelineRecipes.ts` | Pasos curados reutilizables |
| **Preview** | `frontend/src/api/endpoints.ts:4368` (`PipelineGenerator`), `:4371` (`preview`) → `POST /api/pipeline-generator/preview` | spec → `{ado, gitlab}` |
| **Commit HITL** | `endpoints.ts:4376` (`commit`) → `POST /api/pipeline-generator/commit` + `CommitPipelineModal.tsx` | **Ya es HITL con confirm** |
| Lint + autofix | `backend/services/pipeline_lint.py:791` (`lint_yaml`), `:1031` (`explain_plan`), `PipelineLintPanel.tsx` | Reglas **PL001..PL006 y PL010..PL014** (`:261`..`:772`; **PL007/PL008/PL009 NO existen** — verificado), `ENGINE_VERSION="186.1"` (`:16`), `SEV_ERROR/SEV_WARNING/SEV_INFO` (`:18-20`) |
| Contrato UX de IA | `PipelineBuilderSection.tsx:382-383` (Plan 106 F5) | *"PRE-RELLENA solo lo que está vacío […] nunca pisa lo que el operador ya escribió"* |
| Sugerencia IA por paso | `PipelineBuilderSection.tsx:384-421`, `LocalLlmApi` (`endpoints.ts:4380`) → `suggestPipeline` (`:4431`) | Precedente de LLM en el panel, con `justification` mostrada (`:696-698`) |
| Spec backend | `backend/services/pipeline_spec.py:26-64,69,112` | `PipelineSpec`, `dict_to_spec`, `_validate_spec` |
| Renderer | `backend/services/pipeline_renderers.py:23,35` | `to_ado_yaml`, `_spec_to_ado_doc` |
| Detector de stack | `backend/services/pipeline_stack_detector.py:19` | `python\|node\|dotnet\|None` |
| Alta de definición ADO | `backend/services/ado_pipeline_definitions.py:125` + `DefinitionConfirmRequired` (`:120`) | Registro con confirmación humana |
| Trigger / monitor CI | `backend/api/ci.py:75,191,269` | Disparo, monitoreo, jobs fallidos |
| Seam de LLM | `backend/services/pm/pm_llm_client.py:278` (`call_llm`), `:90` (`LLMCallSpec`), `:122` (guard PII) | `expect_json`, `fixture_id`, `temperature=0.0`, **nunca lanza** (`:281-283`) |
| Ledger JSONL | `backend/services/ci_run_ledger.py:23` (`ENTRY_FIELDS`), `:62-63` (proyección que **descarta** claves fuera del contrato) | Patrón con ALLOWLIST estricta, sin BD |
| Flags | `backend/services/harness_flags.py:21-41` (`FlagSpec`) | Contrato de config por UI. **Verificado:** soporta `type="int"` (`:23`), `requires` (`:30`), `min_value` (`:33`), `max_value` (`:34`) — F9 es implementable. Ojo: `requires` es **informativo para la UI; ningún runner lo evalúa** (`:31-32`) |
| Ratchet de tests | **DOS listas**: `backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`) **y** `backend/scripts/run_harness_tests.ps1:13` (`$HarnessTestFiles = @(`) + `tests/test_harness_ratchet_meta.py` | Todo `test_*.py` nuevo debe registrarse **en las dos** |
| Huellas de error | `docs/sistema/error_fingerprints.json` (`schema_version: 1`; campos `id,title,class,status,log_pattern,log_guarded,killed_by,killed_commit,date_resolved,guard_test,evidence,note`) | Catálogo de clases de error ya muertas; **hoy no tiene entrada de ADO-369** (C23) |

### 2.2 El agujero `task:` (fundamento de C1)

- `StepDraft` (`specBuilder.ts:9`) y `Step` (`pipeline_spec.py:26-32`) modelan **sólo**
  `name`/`script`/`working_directory`/`condition`/`env`.
- `_spec_to_ado_doc` emite literalmente `{"script": step.script, "displayName": step.name}`
  (`pipeline_renderers.py:65`). **No hay forma de emitir `task:` ni `inputs:`.**
- Los presets confirman el sesgo: `"pip install -r requirements.txt"` (`pipelinePresets.ts:30`),
  `"npm ci"` (`:50`), `"dotnet restore"` (`:71`).
- **Contraste con la realidad**, verificado sobre los 9 pipelines de
  `N:\GIT\RS\RSPACIFICO\pipelines\*.yml`: el 100% de los pasos son `- task: X@N` + `inputs:`.
  Catálogo real en uso: `NuGetToolInstaller@1` (`ci-cd-online.yml:70`), `NuGetCommand@2` (`:75`),
  `VSBuild@1` (`:85`), `DotNetCoreCLI@2` (`:100`), `PublishTestResults@2` (`:112`),
  `PublishBuildArtifacts@1` (`:121`), `PublishCodeCoverageResults@2` (`agendaweb-ci.yml:101`),
  `CopyFiles@2` (`ci-dacpac.yml:66`), `UseDotNet@2` (`ci-dacpac.yml:42`),
  `PowerShell@2` (`cd-deploy-test.yml:134`).
> **[v3 — C20] Trampa de extracción, leer antes de implementar F0.** Los 10 refs de arriba son
> los **vivos** (los que devuelve `yaml.safe_load`). Un `grep`/regex sobre los mismos 9 archivos
> devuelve **12**, porque hay dos `- task:` **dentro de comentarios**:
> `agendaweb-ci.yml:142` (`IISWebAppDeploymentOnMachineGroup@0`) y
> `ci-dacpac.yml:102` (`SqlAzureDacpacDeployment@1`).
> Extraer con regex metería en el catálogo **la mismísima tarea que RS002 existe para prohibir**
> (ADO-369). **La extracción es SIEMPRE por `yaml.safe_load`, nunca por texto**, y F0 lleva un
> test negativo explícito que lo verifica.

- Formas estructurales también ausentes del modelo: `- deployment:` + `environment:` +
  `strategy.runOnce` (`cd-deploy-test.yml:122-128`), `pool: name:` self-hosted a nivel de stage
  (`:119-120`), `${{ parameters.X }}` (`bootstrap-server-environment.yml:116`), `dependsOn`
  (`cd-deploy-test.yml:117`), `pr: none` (`ci-cd-online.yml:44`), `schedules`
  (`nightly-build-online.yml:7`), filtros `paths` (`ci-cd-online.yml:36-39`).

### 2.3 El incidente ADO-369 (fundamento de C2)

`ci-cd-online.yml:9-29` documenta dos stages de deploy eliminados por estar **"rotos por
diseño"**: heredaban el pool hosted `windows-2022` y usaban
`IISWebAppDeploymentOnMachineGroup@0`, "que es la variante machine-group — no tiene input de
servidor y publica contra el IIS LOCAL del agente que la corre. Resultado: msdeploy buscaba el
sitio 'AgendaWeb' en la VM efímera de Microsoft -> ERROR_SITE_DOES_NOT_EXIST". Además, dos
pipelines disparaban sobre los mismos paths, lo que significaba "dos robocopy simultáneos sobre
`C:\AIS\AgendaWeb\Web` del mismo servidor".

**Ese YAML era sintácticamente perfecto y habría pasado el lint actual sin una sola marca.**

### 2.4 Lo NO verificado (declarado)

- **Validación server-side de YAML en ADO** (gate G4): **NO VERIFICADO** el endpoint exacto,
  su disponibilidad ni los scopes de PAT. F6 obliga a confirmarlo antes de implementar G4; si
  no está, G4 queda `SKIPPED` y **`OPERATIVO` sigue exigiendo G5**.
- **No se verificó** que los pipelines del working tree coincidan con las definiciones
  registradas en la organización ADO.
- Este plan **no toca ninguna tabla**: la persistencia nueva es JSONL (§F9).

**[v3] Verificado en la crítica independiente (2026-07-26), contra el código y el corpus reales:**

- `N:\GIT\RS\RSPACIFICO\pipelines\` tiene **exactamente 9 `.yml`** (+ `ESTRUCTURA-SERVIDOR-DEPLOY-INICIAL.md` y `scripts/`). **Está FUERA del repo de Stacky** ⇒ el corpus dorado **debe vendorizarse** en `backend/tests/fixtures/` (F0 ya lo hacía) y **ningún test puede depender de la ruta `N:\...`** (ver C22).
- `parse_ado_yaml` **SÍ existe** (`pipeline_renderers.py:194`), pero **sólo lee `script` + `displayName`** (`:212-217`) ⇒ F2 no "extiende" un parser, lo **reescribe** (C14).
- Los 10 anclajes `archivo:línea` del corpus en §2.2 son **todos correctos** (reverificados uno por uno).
- **`ci-batch.yml:58-59` usa `strategy: matrix:`** y **`bootstrap-server-environment.yml` tiene 17 expresiones `${{ }}`**: ambas quedan **FUERA DE ALCANCE** (§3) y por eso el round-trip 9/9 de v2 era inalcanzable.
- **`nightly-build-online.yml:110` tiene un `- script: |` crudo real** ⇒ rompía RS008 vs el capstone de F3 (C13).
- El corpus **no usa variable groups** (`grep "group:"` = 0 hits) ⇒ la evidencia de RS005 se sostiene.

---

## 3. Alcance / Fuera de alcance

**En alcance:** entrada NL en el panel; soporte de pasos `task:` y jobs `deployment:` en el
modelo, el renderer y el builder; catálogo de tareas por perfil; reglas semánticas; escalera de
gates; activación HITL; ledger y flag por UI. Provider **ADO**.

**Fuera de alcance (explícito):**
- **GitLab CI** para la ruta NL (el renderer GitLab existe y no se rompe, pero el generador NL
  emite `provider="ado"`).
- **Producción**: se genera deploy a entornos de prueba; `Production` se rechaza por regla (RS009).
- **Crear infraestructura** (agent pools, environments, servidores): se verifican, no se crean.
- **Migrar los pipelines existentes** al modelo nuevo.
- Cambios en el orquestador de agentes (`pipeline_orchestrator.py`) — es otro sistema (ver C8).
- **[v3, C14] Construcciones ADO explícitamente NO modeladas** (ni se emiten, ni se round-trippean):
  `strategy: matrix:` (`ci-batch.yml:58-59`), expresiones de tiempo de compilación `${{ … }}`
  (`bootstrap-server-environment.yml`, 17 ocurrencias), `template:`/`extends:`/`resources:`
  (0 usos en el corpus, no se agregan). Entran a la allowlist `UNSUPPORTED_CONSTRUCTS` de F2.
- **[v3, C25] Corte de alcance:** este documento (243) implementa **F0 → F3.5**. Las fases
  **F4 → F9 se mueven al plan 244** (`244_PLAN_GENERADOR_NL_DE_PIPELINES_FASE_2_LLM_GATES_Y_ACTIVACION.md`;
  número libre verificado el 2026-07-26: 243 es el máximo en `Stacky Agents/docs/`). Se conservan
  aquí, completas y ya corregidas, para que el 244 se cree por copia sin reinterpretación.
  **Justificación:** 11 archivos de test, ~90 casos, backend + frontend + blueprint + seam de LLM
  + ledger + 2 flags no entran en una corrida de implementación sin degradar la calidad; y F0–F3
  **ya entregan valor solas** (§6). El corte lo confirma el operador antes de implementar (HITL).

---

# PARTE A — Arquitectura y plan v1 (propuesta inicial, conservada para auditoría)

**Flujo v1:** texto → LLM → `PipelineSpec` (JSON) → `validate()` → `lint_yaml()` →
`to_ado_yaml()` → escribir archivo → commit → PR → `ensure_yaml_definition()` → trigger.

**Componentes v1:** `nl_pipeline_intent.py` (NL→intent), `nl_pipeline_generator.py`
(intent→spec), `nl_pipeline_deployer.py` (archivo/commit/PR/registro/trigger),
`api/devops_nl_pipeline.py`, y una página nueva `NlPipelineStudio.tsx`.

**Decisiones v1:** validación = esquema + lint existente; errores = reenviar el lint al LLM en
bucle hasta que quede limpio; seguridad = guard de PII + `_looks_secret`; observabilidad =
logging estándar; despliegue = flag + commit automático + PR + alta de definición + trigger.

---

# PARTE B — Crítica adversarial del plan v1

### C1 — BLOQUEANTE · El modelo no puede expresar ningún pipeline ADO real
Ver §2.2. Un generador NL sobre el modelo actual emite YAML válido que no compila nada.
**Corrección:** extender modelo, renderer y builder **de forma aditiva** antes del LLM → **F1, F2**.

### C2 — BLOQUEANTE · "Pasa el lint" no significa "funciona"
Ver §2.3. Las reglas PL002..PL014 (`pipeline_lint.py:263-772` — **v3: rango real `:261-772`, y
PL007/PL008/PL009 no existen; ver C24**) son genéricas de estructura;
ninguna conoce la compatibilidad tarea↔pool↔entorno, que es justo lo que falló.
**Corrección:** reglas semánticas por perfil → **F3**.

### C3 — IMPORTANTE · v1 reescribía lo que ya existe (materializar/commitear)
`PipelineGenerator.commit` ya es "commit HITL con confirm" (`endpoints.ts:4295-4298` — **v3: real
`:4376`**) y
`CommitPipelineModal.tsx` ya es la UI. **Corrección:** eliminar la fase de materialización;
la salida del generador es un `PipelineSpecDraft` que entra al builder y sigue el flujo existente.

### C4 — IMPORTANTE · v1 rompía el contrato UX del panel
Plan 106 F5 fijó: pre-rellenar sólo lo vacío, nunca pisar lo del operador, mostrar justificación
(`PipelineBuilderSection.tsx:382-383,696-698`). Una página nueva paralela habría creado dos
lenguajes de IA distintos en la misma pantalla.
**Corrección:** la caja NL vive **dentro** del builder y respeta el mismo contrato → **F7**.

### C5 — ALTO · Alucinación de tareas e inputs
Nada impide que el modelo emita `VSBuild@2` (no existe) o `inputs.msbuildArguments` (el input
real es `msbuildArgs`, `ci-cd-online.yml:91`). El error aparecería recién al correr.
**Corrección:** **allowlist cerrada** por perfil; el LLM elige *dentro* del catálogo → **F0, F5**.

### C6 — ALTO · Falso verde: "validado y operativo" sin haber ejecutado nada
**Corrección:** escalera de gates con estados honestos:

| Gate | Qué prueba | Dónde | Habilita |
|---|---|---|---|
| G1 SCHEMA | spec válido + YAML parseable | local | `BORRADOR` |
| G2 LINT | `lint_yaml` sin `SEV_ERROR` | local | — |
| G3 SEMÁNTICA | reglas del perfil sin error | local | `VALIDADO_LOCAL` |
| G4 REMOTO | validación server-side ADO | red | `VALIDADO_REMOTO` |
| G5 EJECUCIÓN | corrida real verde en rama descartable | agente ADO | `OPERATIVO` |

→ **F6**.

### C7 — ALTO (SEGURIDAD) · Superficie de inyección hacia agentes self-hosted
El YAML generado se ejecuta en agentes con acceso a servidores y datos reales. En v1, un pedido
ambiguo puede materializarse como `PowerShell@2` con script inline arbitrario. Además
`_looks_secret` (`pipeline_lint.py:553`) evalúa **nombres de referencias**, no valores literales.
**Corrección:** `PowerShell@2` sólo con `inputs.filePath` a un script **ya versionado** en el
repo; prohibido `inputs.script` inline y `- script:`/`- bash:` crudos en la ruta NL; escaneo de
secretos literales; **el texto NL nunca se copia al YAML** (ni como comentario) → **F3 (RS004,
RS008), F5**.

### C8 — MEDIO · Colisión de nombres
`pipeline_orchestrator.py` usa "pipeline" para la cadena de agentes business→qa (`:11`) bajo la
flag `STACKY_PIPELINES_ENABLED` (`:15`). Nombrar la feature `STACKY_PIPELINES_NL_*` invita a
tocar la flag equivocada. **Corrección:** prefijo `cicd_nl_*` y flag `STACKY_CICD_NL_ENABLED`.

### C9 — MEDIO · No determinismo
Sin temperatura fija ni registro, el mismo pedido da pipelines distintos: intesteable.
**Corrección:** `temperature=0.0` (default en `LLMCallSpec`, `pm_llm_client.py:98`),
`fixture_id` (`:99`) en todos los tests, y **el LLM sólo produce el `IntentSpec`** — el
compilador a draft es 100% determinista → **F4, F5**.

### C10 — MEDIO · Bucle de reparación sin techo
"Hasta que quede limpio" puede no terminar nunca. **Corrección:** tope duro de 2 intentos
(`STACKY_CICD_NL_MAX_REPAIRS`), luego `RECHAZADO` con findings. **Prohibido** el fallback a
`raw_yaml` (`pipeline_spec.py:60`): esquivaría el catálogo → **F6**.

### C11 — BAJO · Observabilidad indefinida
**Corrección:** ledger JSONL con ALLOWLIST (patrón `ci_run_ledger.py:23-30`); **el NL crudo no
se persiste**, sólo su hash; 4 métricas definidas → **F9**.

### C12 — BAJO · Rollback indefinido
**Corrección:** 3 niveles — revertir el commit (flujo existente), despublicar la definición por
`definition_id` del ledger, y `STACKY_CICD_NL_ENABLED=false` desde la UI.

## Veredicto

**APROBADO-CON-CAMBIOS.** La dirección es correcta y hay más infraestructura reutilizable de la
que v1 suponía (C3, C4 achican el plan). Pero C1 y C2 son bloqueantes y **reordenan** el trabajo:
primero se arregla el modelo y se codifica el conocimiento del dominio; el LLM entra recién en F4.

---

# PARTE B.2 — Crítica adversarial INDEPENDIENTE del plan v2 (2026-07-26)

> Esta es la **primera** revisión hecha por un agente distinto del que escribió el plan. Su eje
> es la **verificación contra el código real**: cada anclaje se abrió, se grepeó y se corrió.

### Tabla de verificación de anclajes

| Anclaje del v2 | Resultado |
|---|---|
| `specBuilder.ts` `StepDraft`:9 `JobDraft`:17 `StageDraft`:28 `PipelineSpecDraft`:34 `validateSpecLocal`:107 `toSpecDict`:161 `fromParsedSpec`:185 | **OK (7/7)** |
| `pipelinePresets.ts` :30 :50 :71, `PIPELINE_PRESETS`:102-107 (4 presets) | **OK** |
| `pipeline_renderers.py` `to_ado_yaml`:23 `sort_keys=False`:32 `_spec_to_ado_doc`:35 literal `{"script":…,"displayName":…}`:65 | **OK** |
| `pipeline_renderers.py` **`parse_ado_yaml`** | **OK, existe (`:194`)** — pero sólo parsea `script`/`displayName` (`:212-217`) ⇒ **C14** |
| `pipeline_spec.py` `Step`:26-32 `raw_yaml`:60 `dict_to_spec`:69 `_validate_spec`:112 | **OK** |
| `pipeline_lint.py` `ENGINE_VERSION`:16 `_ADO_WL_PREFIXES`:545 `_looks_secret`:553 `lint_yaml`:791 `explain_plan`:1031 | **OK** |
| `pipeline_lint.py` "reglas PL002..PL014 (`:263-772`)" | **DESFASADO** — rango real `:261-772` y **PL007/PL008/PL009 no existen** (⇒ C24) |
| `PipelineBuilderSection.tsx` componente:64, `spec`:71, contrato Plan 106 F5:382-383, sugerencia IA:384-421, `justification`:696-698 | **OK (5/5)** |
| `endpoints.ts` `PipelineGenerator.preview`:4291-4293 | **DESFASADO** — `:4291` es `PrReview`; real `PipelineGenerator`:4368, `preview`:4371 |
| `endpoints.ts` `.commit`:4295-4298 | **DESFASADO** — real `:4376` |
| `endpoints.ts` `LocalLlmApi.suggestPipeline`:4353 | **DESFASADO** — `:4353` es `SectionDoctorApi`; real `LocalLlmApi`:4380, `suggestPipeline`:4431 |
| `pm_llm_client.py` `LLMCallSpec`:90 `temperature`:98 `fixture_id`:99 guard PII:122 `call_llm`:278 "nunca lanza":281 | **OK (6/6)** |
| `ado_pipeline_definitions.py` `DefinitionConfirmRequired`:120 `ensure_yaml_definition`:125 | **OK** |
| `api/ci.py` `_read_pat_scopes`:60, trigger:75/76, monitor:191/192, jobs fallidos:269/270 | **OK** (el número citado es la línea del decorador) |
| `ci_run_ledger.py` ALLOWLIST:23-30 | **OK** — `ENTRY_FIELDS`:23-26 y **filtra de verdad** al escribir (`:62-63`) |
| `harness_flags.py` `FlagSpec`:21-41; ¿`type="int"` + `min_value`/`max_value` + `requires`? | **OK — F9 es implementable** (`:23`, `:30`, `:33`, `:34`; precedente `:501-506`) |
| `pipeline_stack_detector.py:19` (`detect_stack`) | **OK** |
| `scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES`) | **OK** — pero hay **una segunda lista** en `run_harness_tests.ps1:13` (`$HarnessTestFiles`) que el v2 no ancla (C24) |
| **Corpus dorado: 9 `.yml` en `N:\GIT\RS\RSPACIFICO\pipelines\`** | **OK — son 9 exactos** (`agendaweb-ci`, `bootstrap-server-environment`, `cd-deploy-test`, `ci-batch`, `ci-cd-online`, `ci-dacpac`, `nightly-build-online`, `pr-validation-online`, `security-scan-online`) |
| Catálogo de **10** tareas y sus `archivo:línea` (§2.2) | **OK (10/10)** — reverificados uno por uno; el regex ingenuo daría 12 (⇒ C20) |
| Incidente ADO-369 en `ci-cd-online.yml:9-29` | **OK, literal** (incluye `IISWebAppDeploymentOnMachineGroup@0`, `ERROR_SITE_DOES_NOT_EXIST` y el doble robocopy) |
| `docs/sistema/error_fingerprints.json` | **Existe**, `schema_version: 1`, **sin entrada de ADO-369** (⇒ C23) |

**Veredicto de anclajes:** 0 inexistentes, **4 desfasados** (todos en `endpoints.ts`) + 1 impreciso
(rango de reglas PL). El fundamento fáctico del plan es sólido; lo que falla es su **coherencia
interna** y su **acotamiento**.

---

### C13 — BLOQUEANTE · F3 se contradice a sí mismo: sus dos capstones son mutuamente insatisfacibles
`nightly-build-online.yml:110` contiene un `- script: |` **crudo y real**. RS008 prohíbe
`- script:` crudo con severidad `error`; `test_corpus_dorado_sin_errores` exige que **los 9**
golden pasen **sin ningún finding `error`**. Las dos cosas no pueden ser verdad. Lo mismo con
RS006 (rutas deben existir en `repo_root`): en la corrida de tests `repo_root` **no es**
RSPACIFICO, así que todo el corpus daría error de ruta inexistente.
**Por qué importa:** un modelo menor resuelve la contradicción por el camino barato — relaja el
test (falso verde) o mutila la regla — y el plan pierde exactamente lo que vino a comprar.
**Fix:** `check_semantics(yaml_text, *, profile, repo_root=None, mode="audit")` con
`mode ∈ {"audit","nl_strict"}`. RS004, RS006 y RS008 **sólo se evalúan en `nl_strict`** (son
reglas de *lo que Stacky puede generar*, no de *lo que ya existe y funciona*). El capstone corre
en `audit`; se agrega un test que afirma que `nightly-build-online.yml` da RS008 `error` en
`nl_strict` **y cero errores** en `audit`.

### C14 — BLOQUEANTE · El "round-trip 9/9" de F2 es alcance ilimitado disfrazado de criterio binario
`parse_ado_yaml` (`:194`) hoy sólo entiende `script`/`displayName`. Cerrar el round-trip de los 9
golden exige modelar, además de lo que F1 agrega: `strategy: matrix:` (`ci-batch.yml:58-59`),
**17** expresiones `${{ … }}` (`bootstrap-server-environment.yml`), `condition`, `variables`,
`- checkout: self`, `- download: current`, `dependsOn`, `schedules`, `parameters`. Es un AST de
ADO YAML. Y la frase *"si alguno no cierra, se agrega la construcción faltante — no se relaja el
test"* convierte una fase en un pozo sin fondo.
**Por qué importa:** es la fase donde un implementador honesto se queda sin sesión y uno menos
honesto borra un `assert`.
**Fix:** dos gates honestos y acotados (ver F2 v3): **(a) EMISIÓN exacta 3/3** sobre los goldens
que el generador debe poder producir (`ci-cd-online.yml`, `agendaweb-ci.yml`, `cd-deploy-test.yml`);
**(b) PARSE TOLERANTE 9/9** = `parse_ado_yaml` no lanza y extrae la espina de `task:` correcta,
declarando lo no modelado en `UNSUPPORTED_CONSTRUCTS` (allowlist versionada, con test que impide
que crezca en silencio). `matrix` y `${{ }}` pasan a §3 Fuera de alcance.

### C15 — BLOQUEANTE · El contrato de validación de F1 es inimplementable como está escrito
F1 pide: *"`TaskStep.task` fuera del catálogo del perfil → `ValidationError`"* dentro de
`_validate_spec` (`pipeline_spec.py:112`). Pero `_validate_spec(spec)` recibe **sólo el spec**, y
`PipelineSpec` **no tiene campo `profile`** (ni F1 lo agrega). No hay de dónde sacar el perfil.
Peor: acoplaría `pipeline_spec.py` (Plan 73, genérico, sirve a ADO **y GitLab**) a
`cicd_task_catalog.py` (ADO + .NET Framework), y haría que un spec GitLab válido empiece a fallar.
**Por qué importa:** es el punto exacto donde un modelo menor inventa un campo, o peor, un import
circular; y rompe retrocompatibilidad justo donde F1 prometía no romperla.
**Fix:** `_validate_spec` valida **forma** (`task` no vacío y con formato `Nombre@N`, `inputs`
dict, `environment` no vacío, `strategy == "runOnce"`) y **nada de catálogo**. La pertenencia al
catálogo se valida en F3 (**RS008**), donde `profile` ya es parámetro explícito. `pipeline_spec.py`
**no importa** `cicd_task_catalog`.

### C16 — IMPORTANTE · Los 4 anclajes de `endpoints.ts` están desfasados ~77 líneas
Ver tabla. El v2 los cita **5 veces** (§2.1 ×2, C3, C4, F7) y son el fundamento de la reducción de
alcance C3 ("ya existe, no lo reimplementes"). Quien abra `:4291` encuentra `PrReview` y concluye
que el preview HITL no existe.
**Fix:** corregidos en §2.1 y en F7 + **regla de anclaje** (§7.2): todo anclaje lleva el
**símbolo** además del número, el número es una **pista** (`≈`), y si no coincide **se greppea el
símbolo, nunca se inventa ni se asume que la pieza no existe**.

### C17 — IMPORTANTE · Ninguna de las 10 fases dice cómo correr un solo test, y hay dos venvs que se parecen
El plan dice "5 tests verdes", "20 tests verdes"… y nunca un comando. En este repo conviven
`backend/.venv` (**Python 3.13.5**) y `backend/venv` (**Python 3.11.9**) — ambos con `pytest 8.3.3`.
Además el frontend **no tiene script `test`** en `package.json` (sólo `dev/build/preview/lint`),
así que `npm test` **falla**.
**Por qué importa:** un plan que no se puede ejecutar a ciegas no es implementable por un modelo
menor; y elegir el venv equivocado produce fallos que se leen como bugs del código.
**Fix:** §7.1 nueva con los comandos **exactos y verificados en esta corrida** (uno de ellos
corrido de verdad: `tests/test_plan73_round_trip.py` → `5 passed in 0.30s`), y cada fase apunta
a §7.1.

### C18 — IMPORTANTE · El DoD cuenta 8 archivos de test; las fases crean 11
Enumerados: `task_catalog`, `spec_extendido`, `renderer_ado`, `reglas_semanticas`, `nl_intent`,
`compilador`, `gates`, `api`, `activacion`, `ledger`, `flag` = **11** `test_plan243_*.py`
(+2 de frontend). Con el DoD viejo, el ratchet queda incompleto y
`test_harness_ratchet_meta.py` se pone rojo al final, cuando ya es caro arreglarlo.
**Fix:** DoD corregido con la lista literal de los 11 (7 en el 243 tras el corte C25) y el
recordatorio de que son **dos** listas (`.sh:20` y `.ps1:13`).

### C19 — IMPORTANTE · F8 dispara la primera corrida sin confirmación humana en el caso más común
Los 4 puntos de confirmación son `merge_default_branch`, `register_definition`,
`first_trigger_self_hosted` (**condicional**) y `has_deploy_stage` (**condicional**). Para el
pipeline más frecuente —build en pool hosted, sin deploy— **ninguno de los dos condicionales
aplica**: el sistema registra la definición y **dispara solo** una corrida que consume minutos de
agente y ejecuta código.
**Por qué importa:** riel duro de la casa — human-in-the-loop **amplifica, nunca reemplaza**. "Se
confirmó registrar" ≠ "se confirmó ejecutar".
**Fix:** **5º punto de confirmación `first_run_trigger`, incondicional**, con el YAML, la rama
descartable y el pool a la vista. Test `test_g5_siempre_pide_confirmacion_de_corrida`.

### C20 — IMPORTANTE · La extracción del catálogo, si se hace con regex, importa la tarea que el plan quiere matar
Ver §2.2 (recuadro v3). `grep` sobre los 9 golden devuelve **12** refs; dos viven en comentarios,
y una es `IISWebAppDeploymentOnMachineGroup@0` — **la causa raíz de ADO-369**. Quedaría
catalogada como "tarea legítima del perfil" mientras RS002 la prohíbe: el plan se contradice y
además habilita al compilador a emitirla.
**Fix:** F0 especifica extracción por `yaml.safe_load` + test negativo
`test_tareas_comentadas_no_entran_al_catalogo`.

### C21 — IMPORTANTE · `fromParsedSpec` es un cast no-op: F1 no puede "extenderlo" y F5 le mete un dict del backend sin validar
`specBuilder.ts:185-186` es literalmente `return dict as PipelineSpecDraft;`. No valida nada. F5
entrega "un dict compatible con `PipelineSpecDraft`" que va **directo al estado de React** del
builder (`PipelineBuilderSection.tsx:71`); si al dict le falta `stages[].jobs[].steps`, el panel
rompe al renderizar — y el operador ve un panel muerto, no un error del generador.
**Fix:** F1 convierte `fromParsedSpec` en **normalizador real** (defaults por campo, arrays
garantizados, campos desconocidos descartados), retrocompatible por construcción, con test de que
un draft del Plan 97 pasa idéntico y uno recortado sale completo en vez de romper.

### C22 — IMPORTANTE · El corpus dorado se vendoriza desde otro repo, sin procedencia, sin guardia de deriva y con datos de infra del cliente
`N:\GIT\RS\RSPACIFICO` **no está dentro del repo de Stacky**: F0 acierta al copiarlo a
`backend/tests/fixtures/`, pero (a) no registra **de dónde ni de cuándo** salió cada archivo —y la
fuente está viva: `ci-cd-online.yml` se modificó el 2026-07-21—; (b) no hay test que avise cuando
el original cambia; (c) los 9 archivos traen nombres de pool (`TEST-Server`), rutas
(`C:\AIS\AgendaWeb\Web`) y nombres de variables de credenciales, que quedarían **commiteados en
Stacky** (precedente de la casa: la protección de push se dispara con literales que *parecen*
credenciales).
**Fix:** header de procedencia por archivo (`# fuente: RSPACIFICO/pipelines/<f> — copiado 2026-07-26`),
`test_corpus_dorado_no_derivo` que **se SKIPEA** si la ruta fuente no existe (así el arnés queda
verde en cualquier otra máquina o en CI), y pasada de detección de secretos sobre los fixtures
**antes** de commitear.

### C23 — MENOR · El plan mata una clase de error real y no registra su huella
`docs/sistema/error_fingerprints.json` existe (`schema_version: 1`) y **no tiene entrada de
ADO-369**. Este plan es justo el que convierte ese incidente en un gate.
**Fix:** F3 agrega la entrada con el schema real del archivo (`id`, `class`, `status`,
`log_pattern`, `killed_by`, `guard_test`, `evidence`, `date_resolved`).

### C24 — MENOR · Anclajes imprecisos y referencias sin nombre propio
(a) "reglas PL002..PL014 (`:263-772`)" → real `:261-772`, y **PL007/PL008/PL009 no existen**;
(b) "registrar en `run_harness_tests.sh:20` y el `.ps1`" → el `.ps1` tiene **su propia** lista
(`$HarnessTestFiles`, `run_harness_tests.ps1:13`); (c) el gotcha de `_CURATED_DEFAULTS_ON` no dice
dónde vive (`backend/tests/test_harness_flags.py:467`, y el assert que se pone rojo está en `:852`);
(d) F1/F2 dicen "los tests preexistentes de `pipeline_spec` / `specBuilder`" sin nombrarlos —son
`test_plan73_pipeline_spec.py`, `test_plan73_render_ado.py`, `test_plan73_round_trip.py`,
`test_plan73_generator_endpoint.py`.
**Fix:** todos anclados en §2.1, §7.1 y en las fases.

### C25 — IMPORTANTE · 10 fases no entran en una corrida de implementación
11 archivos de test, ~90 casos, backend + frontend + blueprint nuevo + seam de LLM + ledger + 2
flags + edición de 3 archivos vivos del panel. El propio plan admite el corte natural en §6 pero
no lo formaliza, así que el implementador arranca F0 creyendo que llega a F9.
**Fix:** corte formal en §3: **243 = F0..F3.5**, **244 = F4..F9** (número verificado libre el
2026-07-26). Las fases F4–F9 quedan escritas y corregidas acá para copiarse sin reinterpretar.

### Veredicto v2 → v3

**RECHAZADO** (criterio binario: ≥1 BLOQUEANTE ⇒ RECHAZADO; hay **3**: C13, C14, C15 — dos
contradicciones internas que fuerzan al implementador a elegir entre falso verde y alcance
infinito, y un contrato que no se puede escribir sin inventar un campo).
El fundamento es fuerte (0 anclajes inexistentes, corpus real y bien leído, reducción de alcance
por reuso bien argumentada). Lo que falla es coherencia y acotamiento — **todo corregible sin
cambiar la tesis**, que es lo que hace esta v3.

---

# PARTE C — Plan v3 (ESTA ES LA QUE SE IMPLEMENTA)

> **Cómo leer esta parte:** **F0 → F3.5 son el plan 243** (lo que se implementa ahora: sin LLM,
> sin red, valor entregable por sí solo). **F4 → F9 quedan escritas acá, ya corregidas, y se
> mueven al plan 244** (C25). Antes de escribir una línea de código, leé **§7.1 (comandos
> exactos)** y **§7.2 (regla de anclajes)**.

**Convención:** módulos backend `backend/services/cicd_nl_*.py`, API
`backend/api/devops_cicd_nl.py`, tests `backend/tests/test_plan243_*.py`, flag
`STACKY_CICD_NL_ENABLED`.

**Estados del artefacto:** `BORRADOR` → `VALIDADO_LOCAL` (G1-G3) → `VALIDADO_REMOTO` (G4) →
`OPERATIVO` (G5 verde) · `RECHAZADO`.

```
  Caja NL en PipelineBuilderSection
            │  texto libre
            ▼
   F4  parse_intent()  ── única llamada LLM, temperature=0.0
            │  IntentSpec (JSON chico, cerrado, validado por schema)
            ▼
   F5  compile_intent() ── DETERMINISTA, sin LLM, reusa presets/snippets
            │  PipelineSpecDraft  ──►  carga en el builder (F7)
            ▼
   F2  to_ado_yaml() ── con TaskStep/DeploymentJob (F1)
            ▼
   F6  G1 schema → G2 lint → G3 semántica(nl_strict) → G4 remoto → G5 corrida
            │            (auto-reparación ≤ 2, luego RECHAZADO)
            │
            ├─ F3.5 espejo contra el corpus  ── INFORMATIVO, nunca bloquea  [ADICIÓN v3]
            ▼
   FLUJO YA EXISTENTE: preview → CommitPipelineModal (HITL) → commit
            ▼
   F8  registrar definición + primera corrida (**5** confirmaciones humanas — v3, C19)
            ▼
   F9  ledger + métricas
```

> **[v3, C25] Corte de alcance:** el plan **243** llega hasta **F3.5** (la línea punteada del
> diagrama: todo lo que NO usa LLM). **F4–F9 se implementan como plan 244.**

---

## F0 — Catálogo de tareas ADO por perfil + corpus dorado

> Estado fase: PENDIENTE

**Objetivo:** codificar como dato el conocimiento real del dominio, sin LLM.

**Crear:** `backend/services/cicd_task_catalog.py`,
`backend/tests/test_plan243_task_catalog.py`,
`backend/tests/fixtures/cicd_nl/golden/*.yml` (copia literal de los 9 pipelines de
`N:\GIT\RS\RSPACIFICO\pipelines\`).

```python
@dataclass(frozen=True)
class TaskInput:
    name: str
    required: bool = False
    allowed_values: tuple = ()

@dataclass(frozen=True)
class TaskSpec:
    ref: str                        # "VSBuild@1"
    inputs: tuple                   # tuple[TaskInput, ...]
    requires_windows: bool = False
    is_deploy: bool = False
    evidence: str = ""              # "pipelines/ci-cd-online.yml:85"

PROFILE_DOTNET_FRAMEWORK = "dotnet_framework"
TASK_CATALOG: dict[str, dict[str, TaskSpec]]   # perfil → {ref: TaskSpec}
CATALOG_VERSION = "243.1"

def get_task(profile: str, ref: str) -> TaskSpec | None
def is_allowed(profile: str, ref: str) -> bool
def validate_inputs(profile: str, ref: str, inputs: dict) -> list[str]   # [] = OK
```

Primer perfil: `dotnet_framework`, con las **10 tareas** de §2.2, cada una con su `evidence`
apuntando a `archivo:línea` real. `VSBuild@1` y `NuGetCommand@2` llevan `requires_windows=True`
(evidencia: `ci-cd-online.yml:55-56`, `pool: vmImage: 'windows-2022'` — .NET Framework 4.8.1
requiere agente Windows).

**[v3 — C20] Cómo se extrae el catálogo (obligatorio, sin margen de interpretación):**
1. `yaml.safe_load(open(golden).read())` — **nunca** `grep`, `re` ni lectura por líneas.
2. Recorrer recursivamente listas/dicts y quedarse con los dicts que tengan la clave `"task"`.
3. El regex daría **12** refs; lo correcto son **10**. Los 2 de más viven en comentarios
   (`agendaweb-ci.yml:142` → `IISWebAppDeploymentOnMachineGroup@0`, `ci-dacpac.yml:102` →
   `SqlAzureDacpacDeployment@1`) y **no deben entrar jamás** al catálogo.

**[v3 — C22] Procedencia y deriva del corpus.** Cada `golden/*.yml` se copia **con una primera
línea agregada**: `# fuente: RSPACIFICO/pipelines/<archivo> — copiado 2026-07-26 (plan 243 F0)`.
El resto es **byte-idéntico**. Antes de commitear, pasar los 9 fixtures por la detección de
secretos del arnés (`services/secret_masking.py`); si algún literal se marca, **no** se edita el
YAML: se documenta en el propio header por qué es infra y no credencial.

**Tests (8):** archivo `backend/tests/test_plan243_task_catalog.py`. Comando: §7.1.
1. `test_catalogo_cubre_todas_las_tareas_del_corpus` — parsea los 9 golden con `yaml.safe_load`,
   extrae cada `task` y afirma que existe en el catálogo. *Es el test que impide que el catálogo
   se pudra.* **Criterio binario: exactamente 10 refs distintas.**
2. `test_tareas_comentadas_no_entran_al_catalogo` — **[v3, C20]** afirma
   `is_allowed(P, "IISWebAppDeploymentOnMachineGroup@0") is False` **y**
   `is_allowed(P, "SqlAzureDacpacDeployment@1") is False`. *Si este test es verde por casualidad
   (porque se extrajo con regex y luego se filtró a mano), el test 1 falla con 12 ≠ 10.*
3. `test_inputs_del_corpus_son_aceptados` — `validate_inputs(...) == []` para todo el corpus.
4. `test_tarea_desconocida_rechazada` — `is_allowed(P, "MSBuild@1") is False` y `"VSBuild@2"` False.
5. `test_evidence_formato_archivo_linea` — toda entrada matchea `^.+:\d+$`.
6. `test_perfil_desconocido_no_lanza` — devuelve `None`/`False`, nunca excepción.
7. `test_golden_tiene_header_de_procedencia` — **[v3, C22]** los 9 fixtures arrancan con
   `# fuente: RSPACIFICO/pipelines/`.
8. `test_corpus_dorado_no_derivo` — **[v3, C22]** compara cada fixture (sin su primera línea)
   contra `N:\GIT\RS\RSPACIFICO\pipelines\<archivo>`; **`pytest.skip()` si esa ruta no existe**,
   para que el arnés quede verde en cualquier otra máquina o en CI.

**Registrar** `tests/test_plan243_task_catalog.py` en **las DOS listas del ratchet**:
`backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`) **y**
`backend/scripts/run_harness_tests.ps1:13` (`$HarnessTestFiles = @(`).

**Aceptación (binaria):** 8 tests verdes + `test_harness_ratchet_meta.py` verde.

---

## F1 — `TaskStep` y `DeploymentJob` en el modelo (backend + builder)

> Estado fase: PENDIENTE

**Objetivo:** que el panel entero pueda representar pipelines ADO reales. **Aditivo y
retrocompatible**: `Step`/`StepDraft` no se tocan.

**Editar:** `backend/services/pipeline_spec.py`, `frontend/src/devops/specBuilder.ts`.
**Crear:** `backend/tests/test_plan243_spec_extendido.py`,
`frontend/src/devops/__tests__/specBuilderTaskStep.test.ts`.

```python
# pipeline_spec.py — NUEVO
@dataclass(frozen=True)
class TaskStep:
    name: str                         # displayName
    task: str                         # "VSBuild@1"
    inputs: dict = field(default_factory=dict)
    condition: Optional[str] = None
    env: dict = field(default_factory=dict)

@dataclass(frozen=True)
class DeploymentJob:
    name: str
    environment: str
    strategy: str = "runOnce"
    steps: tuple = ()                 # tuple[TaskStep, ...]
    checkout: bool = True
    download_artifacts: tuple = ()

# Job    += task_steps: tuple = (), pool_name: Optional[str] = None, depends_on: tuple = ()
# Stage  += deployments: tuple = (), pool_name/pool_vm_image: Optional[str] = None, depends_on: tuple = ()
# Spec   += pr_disabled: bool = False, trigger_paths/schedules/parameters: tuple = (), pool_vm_image
```

`dict_to_spec` (`:69`) suma `_task_step` y `_deployment` con el mismo patrón puro de `_step`.

`_validate_spec` (`:112`) suma, **sin quitar nada**:
- job inválido sólo si `steps` **y** `task_steps` están ambos vacíos *(cuidado: hay un test del
  Plan 73 que verifica "job sin steps" — debe seguir pasando con un job `script`-only vacío)*;
- `TaskStep.task` vacío o que **no matchee `^[A-Za-z][A-Za-z0-9_]*@\d+$`** → `ValidationError`;
- `TaskStep.inputs` que no sea `dict` → `ValidationError`;
- `DeploymentJob.environment` vacío → `ValidationError`;
- `strategy != "runOnce"` → `ValidationError`.

> **[v3 — C15] `_validate_spec` NO conoce el catálogo, y `pipeline_spec.py` NO importa
> `cicd_task_catalog`.** El v2 pedía "task fuera del catálogo del perfil → ValidationError", pero
> `_validate_spec(spec)` recibe **sólo el spec** y `PipelineSpec` **no tiene campo `profile`**:
> era inimplementable sin inventar. Además `pipeline_spec.py` es el modelo genérico del Plan 73 y
> sirve también a GitLab; acoplarlo al catálogo ADO/.NET rompería specs que hoy son válidos.
> **La pertenencia al catálogo se valida en F3 (RS008)**, donde `profile` es parámetro explícito.

En `specBuilder.ts`, espejo en TypeScript: `TaskStepDraft`, `DeploymentJobDraft`, campos nuevos
opcionales en `JobDraft`/`StageDraft`/`PipelineSpecDraft`, y `toSpecDict` (`:161`) extendido.

> **[v3 — C21] `fromParsedSpec` (`specBuilder.ts:185-186`) hoy es un cast no-op** — literalmente
> `return dict as PipelineSpecDraft;`, sin validar nada. F5 le va a entregar un dict construido en
> el backend que va **directo al estado de React** (`PipelineBuilderSection.tsx:71`): si le falta
> `stages[].jobs[].steps`, el panel **rompe al renderizar** y el operador ve una pantalla muerta,
> no un error del generador. F1 lo convierte en **normalizador real**: `stages`/`jobs`/`steps`/
> `task_steps`/`deployments` garantizados como arrays, strings con default `""`, `env`/`inputs`
> con default `{}`, claves desconocidas descartadas. **Es aditivo**: un draft bien formado del
> Plan 97 sale idéntico.

**Tests (backend 8 / frontend 5).** Archivos: `backend/tests/test_plan243_spec_extendido.py`,
`frontend/src/devops/__tests__/specBuilderTaskStep.test.ts`. Comandos: §7.1.
Backend: construcción válida; `dict_to_spec` con `task_steps`; `dict_to_spec` con `deployments`;
job task-only aceptado; `task` con formato inválido rechazada; `environment` vacío rechazado;
`strategy` inválida rechazada; **`test_no_importa_el_catalogo`** — **[v3, C15]** afirma que
`"cicd_task_catalog" not in` las importaciones de `pipeline_spec.py` (lectura del módulo, no
adivinanza) y que un spec con `task="Loquesea@9"` **pasa** `_validate_spec` (el catálogo es cosa
de F3). Frontend: round-trip `toSpecDict` con task steps; draft del Plan 97 sin cambios;
**`fromParsedSpec` con dict recortado devuelve estructura completa**; con claves desconocidas las
descarta; con `null` devuelve `emptySpec()` en vez de romper.

**Aceptación (binaria):** 13 tests nuevos verdes **y** estos 4 preexistentes verdes, corridos
**por archivo** (contaminación cross-file conocida): `tests/test_plan73_pipeline_spec.py`,
`tests/test_plan73_render_ado.py`, `tests/test_plan73_round_trip.py`,
`tests/test_plan73_generator_endpoint.py`.

---

## F2 — Renderer ADO + round-trip contra el corpus

> Estado fase: PENDIENTE

**Editar:** `backend/services/pipeline_renderers.py` (`_spec_to_ado_doc`, `:35`;
`parse_ado_yaml`). **Crear:** `backend/tests/test_plan243_renderer_ado.py`.

Cambios, **todos condicionados a campo presente** para no alterar la salida de specs del Plan 73:
`pr_disabled` → `pr: none` · `trigger_paths` → `trigger.paths.include` · `schedules` ·
`parameters` · `pool_vm_image` raíz · en stage `pool_name` → `pool.name` y `depends_on` →
`dependsOn` · en job `task_steps` → `{"task", "displayName", "inputs"}` **en ese orden**
(`yaml.safe_dump(sort_keys=False)`, ya en `:32`) · `deployments` →
`{"deployment", "environment", "strategy": {"runOnce": {"deploy": {"steps": [...]}}}}` con
`- checkout: self` y `- download: current` al frente (patrón exacto de `cd-deploy-test.yml:129-132`).

> **[v3 — C14] El "round-trip 9/9" del v2 era inalcanzable y hay que decirlo acá, no descubrirlo
> a mitad de la fase.** `parse_ado_yaml` (`:194`) hoy sólo entiende `script`/`displayName`
> (`:212-217`): no lo extendés, lo reescribís. Y cerrar los 9 golden exigiría además modelar
> `strategy: matrix:` (`ci-batch.yml:58-59`) y **17** expresiones `${{ … }}`
> (`bootstrap-server-environment.yml`) — un AST completo de ADO YAML. La frase del v2 *"se agrega
> la construcción faltante — no se relaja el test"* es alcance ilimitado. **Se reemplaza por dos
> gates acotados y honestos**, y `matrix`/`${{ }}` pasan a Fuera de alcance (§3).

```python
# pipeline_renderers.py — NUEVO, allowlist explícita y versionada
UNSUPPORTED_CONSTRUCTS: tuple[str, ...] = ("matrix", "compile_time_expression",
                                           "template", "extends", "resources")
def scan_unsupported(yaml_text: str) -> tuple[str, ...]   # puro, sin I/O
```

**Tests (7):** archivo `backend/tests/test_plan243_renderer_ado.py`. Comando: §7.1.
1. **GATE A — EMISIÓN exacta 3/3.** Para `ci-cd-online.yml`, `agendaweb-ci.yml` y
   `cd-deploy-test.yml` (los tres que el generador **debe** poder producir): `parse_ado_yaml` →
   `to_ado_yaml` → los dicts de `yaml.safe_load` son **iguales**. **No se relaja: si no cierra, se
   implementa la construcción**, porque son exactamente las formas que F5 va a emitir.
2. **GATE B — PARSE TOLERANTE 9/9.** Para los 9 golden: `parse_ado_yaml` **no lanza** y la espina
   de `task:` extraída coincide con la del `yaml.safe_load` crudo. *Esto es lo que F0/F3 necesitan
   del corpus; el round-trip completo no.*
3. `test_unsupported_declarado` — `scan_unsupported("ci-batch.yml")` contiene `"matrix"` y
   `scan_unsupported("bootstrap-server-environment.yml")` contiene `"compile_time_expression"`.
4. `test_allowlist_no_crece_en_silencio` — `UNSUPPORTED_CONSTRUCTS` tiene **exactamente** las 5
   entradas listadas. *Agregar una obliga a tocar el test y a justificarlo en el doc.*
5. `TaskStep` emite `task`/`displayName`/`inputs` **en ese orden**.
6. `DeploymentJob` emite `strategy.runOnce.deploy.steps` anidado, con `- checkout: self` y
   `- download: current` al frente (patrón de `cd-deploy-test.yml:129-132`).
7. **No regresión:** un spec del Plan 73 produce **exactamente** el YAML de antes.

**Aceptación (binaria):** Gate A 3/3, Gate B 9/9, test 7 verde, y
`tests/test_plan73_render_ado.py` + `tests/test_plan73_round_trip.py` siguen verdes.

---

## F3 — Reglas semánticas por perfil (RS001..RS009)

> Estado fase: PENDIENTE

**Objetivo:** convertir en gate el conocimiento que ADO-369 costó un incidente.

**Crear:** `backend/services/cicd_semantic_rules.py`,
`backend/tests/test_plan243_reglas_semanticas.py`.

```python
@dataclass(frozen=True)
class SemanticFinding:
    code: str          # "RS002"
    severity: str      # reusa pipeline_lint.SEV_ERROR / SEV_WARNING
    message: str       # español, accionable
    location: str      # "stages[1].jobs[0]"
    evidence: str      # por qué existe la regla

RULES_VERSION = "243.1"

MODE_AUDIT = "audit"        # auditar un YAML que YA EXISTE y funciona
MODE_NL_STRICT = "nl_strict"  # validar un YAML que STACKY acaba de generar

def check_semantics(yaml_text: str, *, profile: str, repo_root: str | None = None,
                    mode: str = MODE_AUDIT) -> list[SemanticFinding]
```

> **[v3 — C13] El `mode` no es un adorno: sin él, F3 se contradice a sí misma.**
> `nightly-build-online.yml:110` tiene un `- script: |` **crudo y real**, así que RS008 y
> `test_corpus_dorado_sin_errores` **no podían ser verdaderos a la vez**. Lo mismo RS006: en la
> corrida de tests `repo_root` **no es** RSPACIFICO, así que todo el corpus daría "ruta
> inexistente". Con `mode`, la distinción queda explícita y ambas cosas son ciertas:
> **RS004, RS006 y RS008 sólo se evalúan en `nl_strict`** — son reglas sobre *lo que Stacky puede
> generar*, no sobre *lo que ya existe y anda en producción*. RS001, RS002, RS003, RS005, RS007 y
> RS009 se evalúan **siempre** (esas sí son verdades del dominio).
> `mode` inválido ⇒ `ValueError` (falla ruidosa, nunca silenciosa).

| Código | Regla | Sev | Modos | Evidencia |
|---|---|---|---|---|
| RS001 | Job con tarea `requires_windows` debe correr en pool Windows | error | ambos | `ci-cd-online.yml:55-56` |
| RS002 | Prohibida tarea `*OnMachineGroup*` en stage con pool hosted (`vmImage`) | error | ambos | `ci-cd-online.yml:15-20` (ADO-369) |
| RS003 | Stage con tarea `is_deploy` debe declarar `pool: name:` a nivel stage y usar `- deployment:` con `environment:` | error | ambos | `cd-deploy-test.yml:119-127`; recomendación en `ci-cd-online.yml:27-29` |
| RS004 | `PowerShell@2` sólo con `inputs.filePath` a script existente en el repo; `inputs.script` inline prohibido | error | **`nl_strict`** | `cd-deploy-test.yml:134-141` |
| RS005 | Toda referencia `$(x)` no built-in debe estar declarada en `variables:` del propio YAML | error | ambos | ausencia total de variable groups en el corpus (verificado v3: `grep "group:"` = 0 hits) |
| RS006 | Rutas de `solution`/`restoreSolution`/`projects`/`testProject` deben existir en `repo_root` | error | **`nl_strict`** (y sólo si `repo_root is not None`) | `ci-cd-online.yml:48-49` |
| RS007 | Dos pipelines con deploy no pueden disparar sobre los mismos `paths` de la misma rama | warning | ambos | `ci-cd-online.yml:22-25` |
| RS008 | Prohibido `- script:`/`- bash:` crudo y toda `task:` fuera del catálogo del perfil | error | **`nl_strict`** | C5/C7; **contraejemplo real: `nightly-build-online.yml:110`** |
| RS009 | Prohibido `environment:` que contenga `Prod`/`Producción` | error | ambos | §3 |

RS005 reutiliza `_ADO_WL_PREFIXES` (`pipeline_lint.py:545`) para los built-ins.
**RS008 es el único punto donde se consulta el catálogo de F0** (`is_allowed(profile, ref)`) — ver C15.

**Tests (23):** archivo `backend/tests/test_plan243_reglas_semanticas.py`. Comando: §7.1.
1 positivo + 1 negativo por regla (18), más:
- `test_corpus_dorado_sin_errores` — los 9 pipelines reales, en **`mode="audit"`**, pasan sin
  ningún finding `error`. *Si una regla marca un pipeline que hoy funciona, la regla está mal.*
- `test_ado369_seria_detectado` — se reconstruye el stage de `ci-cd-online.yml:9-29`
  (`IISWebAppDeploymentOnMachineGroup@0` sobre pool hosted) y se afirma **RS002 severidad error**,
  **en los dos modos**. **Este es el KPI del plan.**
- **[v3, C13] `test_script_crudo_solo_falla_en_nl_strict`** — `nightly-build-online.yml` da
  **RS008 `error` en `nl_strict`** y **cero `error` en `audit`**. *Este test es el que impide que
  alguien "arregle" la contradicción borrando un assert.*
- **[v3, C13] `test_rs006_no_corre_sin_repo_root`** — con `repo_root=None` no emite RS006 en
  ningún modo.
- **[v3, C13] `test_mode_invalido_lanza`** — `mode="loquesea"` ⇒ `ValueError`.

**[v3 — C23] Registrar la huella del incidente.** Agregar a
`docs/sistema/error_fingerprints.json` (`schema_version: 1`, respetando los campos existentes):

```json
{
  "id": "ado369_machine_group_en_pool_hosted",
  "title": "Deploy IIS con tarea machine-group sobre agente hosted (ERROR_SITE_DOES_NOT_EXIST)",
  "class": "pipeline-semantica-tarea-vs-pool",
  "status": "resolved",
  "log_pattern": "ERROR_SITE_DOES_NOT_EXIST",
  "log_guarded": false,
  "killed_by": "plan 243 F3 (regla semantica RS002)",
  "killed_commit": "<sha del commit de F3>",
  "date_resolved": "2026-07-26",
  "guard_test": "tests/test_plan243_reglas_semanticas.py::test_ado369_seria_detectado",
  "evidence": "RSPACIFICO/pipelines/ci-cd-online.yml:9-29; backend/services/cicd_semantic_rules.py",
  "note": "El YAML era sintacticamente perfecto y habria pasado el lint PL001..PL014 sin una sola marca."
}
```

**Aceptación (binaria):** 23 tests verdes (en particular los dos capstone y
`test_script_crudo_solo_falla_en_nl_strict`) + la entrada nueva en `error_fingerprints.json` y el
JSON sigue parseando (`python -c "import json;json.load(open(...))"`).

---

## F3.5 — [ADICIÓN ARQUITECTO v3] Espejo contra el corpus: "¿en qué se diferencia de uno que YA funciona?"

> Estado fase: PENDIENTE · **Determinista, sin LLM, sin red. Cierra el hueco de R4.**

**El problema que resuelve.** Los gates G1–G3 responden *"¿está bien formado y no viola ninguna
regla conocida?"*. Ninguno responde la pregunta que de verdad se hace el operador frente a un
draft generado: ***"¿esto se parece a un pipeline que anda?"***. El riesgo R4 (`IntentSpec`
plausible pero equivocado — probabilidad media, impacto **alto**) hoy tiene una mitigación blanda:
*"las `notes` se muestran antes de cargar"*. Eso le pide al operador que audite de memoria. Y el
caso típico no es un YAML roto: es uno **correcto al que le falta un paso** (por ejemplo, compila
y testea pero **nunca publica el artefacto**, o publica los tests pero no el resultado). Ningún
gate del v2 lo ve.

**La idea.** Ya tenemos, vendorizado por F0, **9 pipelines que corren en producción**. Usarlos
como **espejo**: comparar la **espina de tareas** del draft contra la del golden más parecido y
mostrar la diferencia. Es la diferencia entre *"pasó el linter"* y *"mirá en qué se aparta de uno
que ya funciona"*.

**Crear:** `backend/services/cicd_corpus_mirror.py`,
`backend/tests/test_plan243_corpus_mirror.py`.

```python
@dataclass(frozen=True)
class SpineDiff:
    reference: str        # "ci-cd-online.yml"
    similarity: float     # 0.0..1.0 — Jaccard sobre el conjunto de refs task:
    missing: tuple        # refs que el golden tiene y el draft NO  → "¿te falta esto?"
    extra: tuple          # refs que el draft tiene y el golden NO
    order_changed: bool   # misma composición, distinta secuencia
    hint: str             # español, accionable, derivado (no redactado por un LLM)

MIRROR_VERSION = "243.1"

def task_spine(yaml_text: str) -> tuple[str, ...]        # puro; reusa el extractor de F0
def nearest_golden(yaml_text: str, *, profile: str) -> SpineDiff | None
```

**Reglas duras (para que sea reproducible y no moleste):**
- **Determinista**: mayor `similarity`; empate ⇒ **nombre de archivo alfabético**. Nunca aleatorio.
- **Nunca bloquea**: es `info`. **No es un gate**, no cambia el estado del artefacto, no puede
  impedir que el operador siga. *Amplifica, no reemplaza.*
- **Sin LLM, sin red, sin I/O fuera de los fixtures** ⇒ paridad automática en los 3 runtimes
  (Codex CLI, Claude Code CLI, GitHub Copilot Pro): no hay nada específico de runtime que probar.
- **Cero trabajo extra al operador**: se calcula en el mismo request de `/generate` y se muestra
  al lado del semáforo de gates. No hay botón nuevo ni configuración nueva.
- Si `nearest_golden` devuelve `None` (`similarity < 0.3`, sin referencia razonable), la UI
  **no muestra nada** — mejor silencio que un consejo inventado.

**Tests (5):** archivo `backend/tests/test_plan243_corpus_mirror.py`. Comando: §7.1.
1. `test_espina_exacta_de_ci_cd_online` — `task_spine(ci-cd-online.yml)` == las 6 refs de
   `:70,:75,:85,:100,:112,:121` **en orden**.
2. `test_draft_sin_publish_reporta_missing` — un draft igual a `ci-cd-online.yml` pero sin
   `PublishBuildArtifacts@1` devuelve `missing == ("PublishBuildArtifacts@1",)`.
3. `test_empate_resuelve_alfabetico` — dos goldens con idéntica `similarity` ⇒ siempre gana el
   mismo (determinismo).
4. `test_sin_referencia_razonable_devuelve_none` — un YAML de otro stack ⇒ `None`.
5. `test_nunca_emite_severidad_error` — ningún camino produce algo distinto de `info`.

**Aceptación (binaria):** 5 tests verdes y **cero** llamadas a LLM o red en toda la fase.

> Consumo: `/generate` (F7) agrega `spine_diff` a su respuesta; la UI lo renderiza como un aviso
> *"Comparado con `ci-cd-online.yml` (que hoy corre en producción), a este draft le falta:
> `PublishBuildArtifacts@1`"*. Si el 243 se corta acá (§3), F3.5 igual sirve **hoy** al panel
> gráfico: cualquier spec armado a mano puede pedir su espejo.

---

## F4 — NL → `IntentSpec` (única llamada LLM)

> Estado fase: PENDIENTE

**Objetivo:** texto libre → estructura chica, cerrada y validable. **El LLM no escribe YAML.**

**Crear:** `backend/services/cicd_nl_intent.py`, `backend/tests/test_plan243_nl_intent.py`,
`backend/tests/fixtures/cicd_nl/intents/*.json` (≥6).

```python
@dataclass(frozen=True)
class IntentSpec:
    kind: str            # "build" | "build_test" | "build_test_publish" | "deploy" | "scheduled_build"
    profile: str         # "dotnet_framework" | ...
    solution_path: str
    test_project: str | None
    configuration: str
    triggers: dict       # {"branches": [...], "paths": [...], "pr": bool, "cron": str|None}
    target_environment: str | None
    publish_artifact: str | None
    notes: tuple         # supuestos asumidos — SE MUESTRAN al operador

INTENT_SCHEMA: dict
PROMPT_TYPE = "cicd_nl_intent_v1"

def parse_intent(text: str, *, project_root: str, profile: str,
                 fixture_id: str | None = None) -> tuple[IntentSpec | None, list[str]]
```

Usa `LLMCallSpec` (`pm_llm_client.py:90`) con `expect_json=True`, `temperature=0.0`,
`prompt_type=PROMPT_TYPE`, `fixture_id` pasante. El system prompt incluye los `kind` válidos y
el catálogo F0 **como referencia cerrada**, y ordena declarar en `notes` todo dato ausente en
vez de inventarlo. Valida `parsed_json` contra `INTENT_SCHEMA`.

**Ambigüedad explícita:** si no puede determinar `solution_path`, o el pedido cae fuera de los
`kind` soportados, devuelve `(None, [preguntas])`. **Nunca adivina qué compilar.**

**Tests (10, todos con `fixture_id`, sin red):** 6 fixtures realistas → intent esperado; texto
ambiguo → `(None, [...])` nombrando el dato faltante; `kind` inválido rechazado; `parse_intent`
no lanza aunque `call_llm` devuelva `success=False`; determinismo con el mismo `fixture_id`.

**Aceptación (binaria):** 10 tests verdes y **cero acceso a red** (guard de red del arnés verde).

---

## F5 — `IntentSpec` → `PipelineSpecDraft` (determinista, sin LLM)

> Estado fase: PENDIENTE

**Objetivo:** generación reproducible: mismo intent ⇒ mismo draft, siempre.

**Crear:** `backend/services/cicd_nl_compiler.py`, `backend/tests/test_plan243_compilador.py`.

```python
TEMPLATES: dict[tuple[str, str], callable]   # (profile, kind) → constructor
COMPILER_VERSION = "243.1"

def compile_intent(intent: IntentSpec, *, repo_root: str) -> tuple[dict | None, list[str]]
```

Devuelve un **dict compatible con `PipelineSpecDraft`** (el mismo que consume
`fromParsedSpec`, `specBuilder.ts:185`) para que el builder lo cargue sin traducción.
**[v3, C21] Depende de que F1 haya convertido `fromParsedSpec` en normalizador real**: hoy es un
cast no-op y un dict incompleto rompería el render del panel.

Cada plantilla **calca la secuencia real** del corpus. `build_test_publish` para
`dotnet_framework`, copiado de `ci-cd-online.yml:70-126`:

```
NuGetToolInstaller@1 (versionSpec 6.x)
 → NuGetCommand@2 (restore, restoreSolution=$(solution), feedsToUse=select)
 → VSBuild@1 (solution/platform/configuration + msbuildArgs de Web Deploy Package)
 → DotNetCoreCLI@2 (test, --logger trx, publishTestResults=false)
 → PublishTestResults@2 (VSTest, condition=succeededOrFailed(), failTaskOnFailedTests=true)
 → PublishBuildArtifacts@1 (Container)
```

`deploy` se calca de `cd-deploy-test.yml:115-149`. **El pool lo decide una regla, no el LLM:**
si alguna tarea tiene `requires_windows` → imagen Windows; si el stage es de deploy → pool
self-hosted del entorno. Toda ruta se valida contra `repo_root` antes de emitir (adelanta RS006
con un error más legible). `variables` siempre inline.

**Tests (9):** 1 por plantilla comparando contra un draft esperado literal; determinismo (2
corridas ⇒ idéntico); `solution_path` inexistente ⇒ `(None, [...])`; y **test de integración
F5+F2+F3**: el intent equivalente a `ci-cd-online.yml` produce YAML que pasa `check_semantics`
sin errores.

**Aceptación (binaria):** 9 tests verdes, incluido el de integración.

---

## F6 — Escalera de gates G1..G5 + auto-reparación acotada

> Estado fase: PENDIENTE

**Crear:** `backend/services/cicd_gates.py`, `backend/tests/test_plan243_gates.py`.

```python
STATE_DRAFT = "BORRADOR"; STATE_LOCAL = "VALIDADO_LOCAL"
STATE_REMOTE = "VALIDADO_REMOTO"; STATE_OPERATIONAL = "OPERATIVO"; STATE_REJECTED = "RECHAZADO"

@dataclass(frozen=True)
class GateResult:
    gate: str; passed: bool; skipped: bool; findings: tuple; duration_ms: int

@dataclass(frozen=True)
class GateLadderResult:
    state: str; gates: tuple; yaml_text: str; draft: dict; repair_attempts: int

def run_local_gates(yaml_text: str, *, profile: str, repo_root: str) -> GateLadderResult
def run_remote_gate(yaml_text: str, *, project: str) -> GateResult
def generate_with_repair(intent, *, repo_root: str, profile: str, max_repairs: int) -> GateLadderResult
```

- **G1** = `dict_to_spec` + `_validate_spec` + `yaml.safe_load` sin excepción.
- **G2** = `lint_yaml(yaml_text, provider="ado")` (`pipeline_lint.py:791`) sin `SEV_ERROR`.
- **G3** = `check_semantics(..., mode="nl_strict")` sin `error`. **[v3, C13] `mode` obligatorio y
  explícito acá**: la ruta NL es justamente el caso estricto (RS004/RS006/RS008 activas).
  `run_local_gates` **debe** recibir `repo_root`, o RS006 no se evalúa y G3 miente por omisión.
- **G3.5** = espejo contra el corpus (F3.5). **Informativo, nunca bloquea**: se adjunta al
  resultado y no puede cambiar `state`.
- **G4** = validación server-side ADO. **NO VERIFICADO (§2.4):** la primera tarea de esta fase
  es confirmar endpoint y scopes (`api/ci.py:60 _read_pat_scopes` ya lee scopes). Si no está →
  `skipped=True` y el estado tope es `VALIDADO_LOCAL`.
- **G5** = corrida real (F8).

**Auto-reparación:** si G2/G3 fallan, se reinvoca `parse_intent` con los findings como contexto,
**máximo `max_repairs`** (default 2, de `STACKY_CICD_NL_MAX_REPAIRS`). Agotado ⇒ `RECHAZADO` con
todos los findings. **Prohibido** el fallback a `raw_yaml`.

**Tests (12):** cada gate pasa/falla aislado; YAML que falla G3 **no** llega a `VALIDADO_LOCAL`;
G4 no disponible ⇒ `skipped` y estado `VALIDADO_LOCAL` (nunca `VALIDADO_REMOTO`); la reparación
se detiene exacto en `max_repairs` (contando llamadas con un doble de `parse_intent`); agotada ⇒
`RECHAZADO`; **`test_nunca_operativo_sin_g5`**.

**Aceptación (binaria):** 12 tests verdes, incluido `test_nunca_operativo_sin_g5`.

---

## F7 — Entrada NL dentro del panel (reusando preview/lint/commit)

> Estado fase: PENDIENTE

**Objetivo:** que el operador escriba en el builder y el draft se cargue ahí mismo, **sin
página nueva** y respetando el contrato UX del Plan 106 F5.

**Crear:** `frontend/src/components/devops/NlPipelinePrompt.tsx`,
`frontend/src/components/devops/NlPipelinePrompt.module.css`,
`backend/api/devops_cicd_nl.py`,
`backend/tests/test_plan243_api.py`,
`frontend/src/components/devops/__tests__/nlPipelinePrompt.test.ts`.

**Editar:** `frontend/src/components/devops/PipelineBuilderSection.tsx` (montar el componente
junto a la galería de presets), `frontend/src/api/endpoints.ts`, `backend/api/__init__.py`
(registrar blueprint, patrón de `:43,46`).

**Endpoints** (`/api/devops/cicd-nl/...`):

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/interpret` | texto → `IntentSpec` + `notes`/preguntas (F4) |
| POST | `/generate` | `IntentSpec` → `draft` + `yaml` + `GateLadderResult` (F5+F6) |
| POST | `/activate` | registro de definición + G5 (F8) |
| GET | `/history` | últimas N del ledger (F9) |

**Contrato de UI (no negociable, hereda Plan 106 F5):**
- Botón **"Cargar en el builder"**: aplica el draft y **sólo rellena lo vacío**; si el operador
  ya tiene un spec no vacío, pide confirmación antes de reemplazar y ofrece "cargar como stage
  nuevo". **Nunca pisa trabajo manual en silencio.**
- Muestra las `notes` del intent (supuestos asumidos) y las preguntas si el intent fue ambiguo.
- Muestra el semáforo de los 5 gates con sus findings, enlazando al `PipelineLintPanel` existente,
  **más el espejo del corpus de F3.5** (`spine_diff`) cuando exista referencia.
- **Preview y commit NO se reimplementan:** se usan `PipelineGenerator.preview`
  (`endpoints.ts:4368` el objeto, `:4371` el método) y el `CommitPipelineModal` que ya existen.
  **[v3, C16] Ojo: el v2 citaba `:4291-4298`, que es `PrReview` — anclajes corregidos. Si el
  número no coincide, greppeá el símbolo (`PipelineGenerator`), no asumas que no existe.**
- Gotcha de la casa: en `.tsx` **nuevo** el `uiDebtRatchet` tiene alcance 0 → **cero
  `style={{...}}` inline**, todo al `.module.css`.

**Tests:** endpoints 404 con flag OFF / 200 con ON; `/generate` sin gates locales verdes ⇒ 409;
la función pura de merge draft→spec no pisa campos no vacíos (test unitario del reducer, sin
RTL — **`@testing-library/react` no está instalado en este frontend**, así que la lógica de
merge vive en un módulo puro testeable con vitest).

**Aceptación (binaria):** tests verdes; `npx tsc --noEmit` sin errores nuevos; el ratchet de
deuda de UI no crece.

---

## F8 — Activación HITL: registrar definición y primera corrida (G5)

> Estado fase: PENDIENTE

**Crear:** `backend/services/cicd_nl_activation.py`, `backend/tests/test_plan243_activacion.py`.

```python
class ActivationConfirmRequired(Exception):
    def __init__(self, step: str, detail: dict): ...

def activate(*, project: str, yaml_path: str, branch: str,
             confirm_token: str | None = None) -> dict
```

**Los 5 puntos de confirmación** (cada uno lanza `ActivationConfirmRequired` sin su token):
1. `merge_default_branch` — **nunca lo hace el sistema**; el merge es 100% del operador.
2. `register_definition` — delega en `ensure_yaml_definition` (`ado_pipeline_definitions.py:125`),
   que ya expone `DefinitionConfirmRequired` (`:120`).
3. **`first_run_trigger` — INCONDICIONAL. [v3, C19]** El v2 sólo pedía confirmación si el pool era
   self-hosted o si había deploy; para el caso más común (build en pool hosted) **el sistema
   disparaba solo** una corrida que consume minutos de agente y ejecuta código. "Confirmé
   registrar" **no es** "confirmé ejecutar". El detalle del confirm muestra rama descartable, pool
   y la espina de tareas que se va a correr.
4. `first_trigger_self_hosted` — **extra**, si el YAML declara `pool: name:` (corre contra
   infraestructura propia del cliente, no contra una VM efímera).
5. `has_deploy_stage` — **extra**, si `check_semantics` detectó cualquier tarea `is_deploy`.

**G5:** el trigger va sobre una **rama descartable** `cicd/nl-<request_id>`, nunca sobre la rama
por defecto, reutilizando `api/ci.py:75` (trigger) y `:191` (monitor). Estado `OPERATIVO`
**sólo** si la corrida termina en éxito.
**Casos borde a cubrir explícitamente:** si `cicd/nl-<request_id>` **ya existe**, se aborta con
error accionable (no se pisa ni se le agrega sufijo silencioso); `request_id` es un UUID4
generado por el backend, **nunca** provisto por el cliente.

**Tests (10, provider ADO mockeado, sin red):** archivo
`backend/tests/test_plan243_activacion.py`. Comando: §7.1. Los 5 puntos lanzan sin token y
proceden con token; **`test_g5_nunca_dispara_sobre_rama_default`**;
**`test_g5_siempre_pide_confirmacion_de_corrida`** (**[v3, C19]** pipeline hosted sin deploy:
igual exige token de `first_run_trigger`); **`test_deploy_stage_siempre_pide_confirmacion`**;
`test_rama_descartable_existente_aborta`; corrida fallida ⇒ no pasa a `OPERATIVO`.

**Aceptación (binaria):** 10 tests verdes, incluidos los tres nombrados en negrita.

---

## F9 — Ledger, métricas y flag por UI

> Estado fase: PENDIENTE

**Crear:** `backend/services/cicd_nl_ledger.py`, `backend/tests/test_plan243_ledger.py`,
`backend/tests/test_plan243_flag.py`.
**Editar:** `backend/services/harness_flags.py`, `backend/config.py`,
`backend/scripts/run_harness_tests.sh:20` (`HARNESS_TEST_FILES=(`) **y**
`backend/scripts/run_harness_tests.ps1:13` (`$HarnessTestFiles = @(`) — **[v3, C24] son DOS listas
separadas**, no una — para registrar **los 12 archivos de test** del plan (§6, no 8: el v2 los
contó mal, C18).

**Ledger** — patrón exacto de `ci_run_ledger.py:23-30` (JSONL en `data_dir()`, lock, retención,
ALLOWLIST estricta). `ENTRY_FIELDS`: `request_id, project, profile, nl_sha256, intent_kind,
model, prompt_type, tokens_in, tokens_out, cost_usd, latency_ms, gates, repair_attempts,
yaml_sha256, definition_id, run_id, final_state, created_at`.

> **El texto NL crudo NO se persiste** — sólo `nl_sha256`. La ALLOWLIST garantiza que aunque un
> llamador lo pase, se descarta al escribir.

**Métricas:** (a) % de drafts aceptados sin edición manual, (b) gate más fallado, (c) costo USD
y latencia por pipeline `OPERATIVO`, (d) tiempo NL→verde.

**Flags** (`harness_flags.py`): `STACKY_CICD_NL_ENABLED`, `type="bool"`, `group="global"`,
`default=True`, categoría DevOps.
> **Gotcha obligatorio (anclado en v3, C24):** toda `FlagSpec` con `default=True` debe estar
> además en `_CURATED_DEFAULTS_ON` (**`backend/tests/test_harness_flags.py:467`**), o el assert de
> `:852` pone rojo a `test_default_known_only_for_curated`. Además, la flag nueva necesita su
> categoría en `_CATEGORY_KEYS` o el meta-test de categorización falla.

Más `STACKY_CICD_NL_MAX_REPAIRS` (`type="int"`, `default=2`, `min_value=0`, `max_value=5`,
`requires="STACKY_CICD_NL_ENABLED"`). **[v3] Verificado: `FlagSpec` soporta los cuatro campos**
(`harness_flags.py:23,30,33,34`; precedente completo en `:501-506`). **Ojo:** `requires` es
**informativo para la UI — ningún runner lo evalúa** (`:31-32`), así que el código de F6 **debe
chequear `STACKY_CICD_NL_ENABLED` por su cuenta**, no confiar en el `requires`.
Ambas configurables **desde la UI** (riel de la casa: nada env-only para el operador).

**Tests (7):** archivos `backend/tests/test_plan243_ledger.py` y
`backend/tests/test_plan243_flag.py`. Comando: §7.1. El ledger descarta claves fuera de la
ALLOWLIST (incluido un intento explícito de persistir el NL crudo — patrón de proyección de
`ci_run_ledger.py:62-63`); retención `MAX_ROWS`; **línea corrupta en el JSONL no rompe la lectura**
(el ledger existente ya tolera y saltea: `ci_run_ledger.py:34`); ambas flags aparecen en el
catálogo de la UI; `STACKY_CICD_NL_MAX_REPAIRS` fuera de `[0,5]` es rechazada por
`apply_updates`; `test_default_known_only_for_curated` verde.

**Aceptación (binaria):** 7 tests verdes + ratchet meta verde con **los 12 archivos** registrados
en **las dos** listas.

---

## 4. Gestión de errores (transversal)

| Falla | Comportamiento |
|---|---|
| NL ambiguo | `(None, [preguntas])`. No adivina. |
| LLM caído | `call_llm` no lanza (`pm_llm_client.py:281-283`); se reporta y se aborta. |
| G2/G3 rojo | Reparación ≤2; luego `RECHAZADO` con findings. Nunca `raw_yaml`. |
| G4 no disponible | `skipped`; estado tope `VALIDADO_LOCAL`. |
| G5 rojo | No pasa a `OPERATIVO`; se ofrece el triage de fallos ya existente (`api/ci.py:269`). |
| Operador ya tiene spec | Confirmación previa; nunca se pisa en silencio (C4). |
| Secreto literal detectado | Se bloquea antes de emitir. |
| Flag OFF | 404 en todos los endpoints; la caja no se renderiza. **El builder gráfico sigue igual que hoy** (fallback explícito). |
| **[v3]** Modelo local caído / runtime sin LLM | La caja NL reporta el error y **el panel gráfico completo sigue operativo**: F0–F3.5 no usan LLM. Paridad de los 3 runtimes por construcción. |
| **[v3]** `repo_root` inexistente o no provisto | RS006 **no se evalúa** (no inventa un veredicto); el gate lo reporta como cobertura parcial, nunca como "validado". |
| **[v3]** La rama descartable `cicd/nl-<request_id>` ya existe | Se aborta con error accionable. **Nunca** se pisa ni se le agrega sufijo silencioso. |
| **[v3]** Ledger JSONL con una línea corrupta | Se saltea esa línea y se sigue (patrón ya probado de `ci_run_ledger.py:34`); nunca tumba el endpoint. |
| **[v3]** YAML gigante (> 512 KB) | `check_semantics` y el espejo del corpus devuelven un finding `warning` "archivo fuera de rango soportado" y no procesan, en vez de colgar el request. |
| **[v3]** El espejo del corpus no encuentra referencia | No se muestra nada. **Silencio > consejo inventado.** |

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | El catálogo se desactualiza | Alta | Medio | `test_catalogo_cubre_todas_las_tareas_del_corpus` falla apenas aparece un `task:` no catalogado |
| R2 | Una regla marca en rojo un pipeline que hoy funciona | Media | Alto | `test_corpus_dorado_sin_errores` es gate de F3: se corrige la regla, no el pipeline |
| R3 | G4 inexistente ⇒ menos validación de la prometida | Media | Medio | Declarado NO VERIFICADO; degrada a `SKIPPED`; `OPERATIVO` sigue exigiendo G5 |
| R4 | `IntentSpec` plausible pero equivocado | Media | Alto | El LLM no escribe YAML; el intent es chico, validado por schema, y sus `notes` se muestran antes de cargar. **[v3] Además: F3.5 muestra en qué se aparta del pipeline real más parecido** — el caso típico (draft correcto al que le falta un paso) no lo ve ningún gate |
| R5 | Regresión en el panel al extender el modelo | Media | Alto | Todo campo nuevo con default; tests de retrocompatibilidad explícitos en F1 y F2 (`test_plan73_*` nombrados en §7.1). **[v3] `fromParsedSpec` pasa de cast no-op a normalizador**, que es donde el panel se rompería de verdad (C21) |
| R8 | **[v3]** El corpus dorado deriva del original o filtra datos de infra del cliente | Media | Medio | Header de procedencia + `test_corpus_dorado_no_derivo` (skip si la fuente no está) + pasada de detección de secretos antes de commitear (C22) |
| R9 | **[v3]** Alcance: 10 fases no entran en una corrida y el implementador se queda sin sesión a mitad de F2 | **Alta** | Alto | Corte formal 243 (F0..F3.5) / 244 (F4..F9) en §3, confirmado por el operador antes de arrancar (C25) |
| R6 | Costo de LLM | Baja | Bajo | Tope de reparaciones, costo por corrida en el ledger |
| R7 | Pipeline generado pisa a otro existente | Media | Alto | RS007 (warning) + revisión humana del commit |

**Rollback:** (1) revertir el commit por el flujo existente; (2) despublicar la definición por
`definition_id` del ledger; (3) `STACKY_CICD_NL_ENABLED=false` desde la UI; (4) las fases son
aditivas — F1/F2 son los únicos cambios sobre archivos existentes y ambos tienen test de no-regresión.

## 6. Orden de implementación y Definición de Hecho

**Orden obligatorio:** F0 → F1 → F2 → F3 → **F3.5** → *(corte 243/244)* → F4 → F5 → F6 → F7 → F8 → F9.
Ninguna fase depende de una posterior (verificado en v3: F3 usa el catálogo de F0; F5 "adelanta"
RS006 sólo como mensaje más legible, no como dependencia; F6 G3 usa F3; F3.5 usa el corpus de F0).

> **F0–F3.5 no usan LLM y entregan valor solas:** el panel gana pasos `task:` reales (hoy
> imposibles), un linter semántico que habría detectado ADO-369, y el espejo contra pipelines que
> ya corren en producción. **[v3, C25] Ese es el alcance del plan 243.**

### DoD del plan 243 (F0 → F3.5) — binaria

- [ ] **5** archivos verdes corriendo **por archivo** con el comando de §7.1:
      `test_plan243_task_catalog.py`, `test_plan243_spec_extendido.py`,
      `test_plan243_renderer_ado.py`, `test_plan243_reglas_semanticas.py`,
      `test_plan243_corpus_mirror.py`.
- [ ] **1** archivo de frontend verde: `specBuilderTaskStep.test.ts` (comando en §7.1).
- [ ] **[v3, C14]** F2 Gate A **3/3** (emisión exacta) y Gate B **9/9** (parse tolerante);
      `UNSUPPORTED_CONSTRUCTS` con exactamente 5 entradas.
- [ ] **[v3, C13]** `test_corpus_dorado_sin_errores` verde en `mode="audit"` **y**
      `test_script_crudo_solo_falla_en_nl_strict` verde. *Los dos, o el gate es mentira.*
- [ ] `test_ado369_seria_detectado` verde — el incidente real se detectaría hoy.
- [ ] **[v3, C20]** `test_tareas_comentadas_no_entran_al_catalogo` verde y el catálogo tiene
      **exactamente 10** refs.
- [ ] **[v3, C15]** `test_no_importa_el_catalogo` verde — `pipeline_spec.py` sigue desacoplado.
- [ ] No regresión: `test_plan73_pipeline_spec.py`, `test_plan73_render_ado.py`,
      `test_plan73_round_trip.py`, `test_plan73_generator_endpoint.py` verdes.
- [ ] `test_harness_ratchet_meta.py` verde con los 5 archivos registrados **en las dos listas**
      (`run_harness_tests.sh:20` y `run_harness_tests.ps1:13`).
- [ ] **[v3, C23]** Entrada `ado369_machine_group_en_pool_hosted` en
      `docs/sistema/error_fingerprints.json` y el JSON sigue parseando.
- [ ] `npx tsc --noEmit` sin errores nuevos; ratchet de deuda de UI sin crecer.
- [ ] Paridad de runtimes: **F0–F3.5 no invocan LLM ni red**, por lo que corren igual en Codex CLI,
      Claude Code CLI y GitHub Copilot Pro. **Fallback explícito: no hay nada que degradar** —
      ninguna de estas fases tiene camino alternativo porque ninguna depende de un modelo.

### DoD del plan 244 (F4 → F9) — binaria

- [ ] **7** archivos verdes por archivo: `nl_intent`, `compilador`, `gates`, `api`, `activacion`,
      `ledger`, `flag` (prefijo `tests/test_plan243_*` **se conserva** para no romper trazabilidad
      con este documento; el 244 lo aclara en su encabezado).
- [ ] **1** archivo de frontend: `nlPipelinePrompt.test.ts`.
- [ ] `test_nunca_operativo_sin_g5`, `test_g5_nunca_dispara_sobre_rama_default` y
      **[v3, C19]** `test_g5_siempre_pide_confirmacion_de_corrida` verdes.
- [ ] `test_default_known_only_for_curated` verde; ambas flags visibles y editables **desde la UI**.
- [ ] Paridad de runtimes en F4: la única llamada a LLM pasa por `pm_llm_client.call_llm`, que
      **nunca lanza** (`:281-283`); **fallback explícito** = si el modelo no está disponible, la
      caja NL muestra el error y **el builder gráfico sigue funcionando igual que hoy**. En tests,
      `fixture_id` ⇒ **cero red** en los 3 runtimes.
- [ ] Demo end-to-end: un pedido en español produce un pipeline que llega a `OPERATIVO` con
      corrida verde sobre rama descartable, **con las 5 confirmaciones humanas dadas a mano**.

---

## 7. Comandos exactos y regla de anclajes (**[v3] nuevo — C17, C16**)

### 7.1 Comandos (verificados el 2026-07-26 en esta máquina)

> **Trampa de la casa:** en `backend/` conviven **dos** entornos —`backend/.venv` (**Python
> 3.13.5**) y `backend/venv` (**Python 3.11.9**)—, ambos con `pytest 8.3.3`. **Usá `.venv`.**
> Y el frontend **no tiene script `test`** en `package.json` (sólo `dev`/`build`/`preview`/`lint`):
> `npm test` **falla**; se invoca `vitest` con `npx`.

```powershell
# --- BACKEND: un archivo de test (SIEMPRE por archivo; la suite completa se contamina) ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan243_task_catalog.py -q

# Comprobado en la crítica v3 con un archivo existente:
#   .venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q   ->  5 passed in 0.30s

# --- BACKEND: no regresión del Plan 73 (F1/F2) ---
.venv\Scripts\python.exe -m pytest tests/test_plan73_pipeline_spec.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_render_ado.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_generator_endpoint.py -q

# --- BACKEND: ratchet del arnés (después de crear CUALQUIER test_*.py) ---
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q

# --- BACKEND: flags (después de tocar harness_flags.py) ---
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q

# --- FRONTEND: un archivo de test ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/specBuilderTaskStep.test.ts

# --- FRONTEND: gate de tipos ---
npx tsc --noEmit
```

> Si un comando falla por dependencias, probá el mismo comando con `venv\Scripts\python.exe`
> (3.11.9) **antes** de tocar el código: puede ser el entorno, no tu cambio.

### 7.2 Regla de anclajes (obligatoria para quien implemente y para quien critique)

La crítica v3 encontró **4 anclajes desfasados ~77 líneas** en `endpoints.ts` (C16). Por lo tanto:

1. **Todo anclaje lleva el símbolo, no sólo el número:** `endpoints.ts:4371 (PipelineGenerator.preview)`.
2. **El número es una pista, no un contrato.** Si la línea no coincide, **greppeá el símbolo**.
3. **Prohibido concluir "no existe" porque la línea no coincide**, y prohibido inventar una
   implementación nueva de algo que ya está. Si el símbolo no aparece con `grep`, **frená y
   reportalo** en vez de improvisar.
4. Anclajes verificados de este plan: tabla completa en **Parte B.2**.
