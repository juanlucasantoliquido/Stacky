# Plan 249 — Paridad GitLab del motor inteligente de pipelines: catálogo de constructos, reglas `GL000..GL011` y renderer/parser que dejan de mentir

> **Estado: IMPLEMENTADO F0..F5 (2026-07-26).** Resultados REALES, cada archivo en su propia
> corrida: `test_plan249_corpus_gitlab.py` **6 passed**, `test_plan249_gitlab_catalog.py`
> **11 passed**, `test_plan249_reglas_gitlab.py` **16 passed** (el número que el propio plan pide
> al cerrar F3), `test_plan249_renderer_gitlab.py` **12 passed**,
> `test_plan249_parser_gitlab.py` **10 passed**, `test_plan249_endpoint_gitlab.py` **6 passed**.
> Frontend: `gitlabProfileModel.test.ts` **4 passed**, `npx tsc --noEmit` **0 errores**.
> No regresión, **sin editar ninguno**: 73-round-trip 5, 73-spec 8, 243-renderer-ado 19,
> 243-reglas-semánticas 27, 243-corpus-mirror 8, 243-task-catalog 9, 186-lint-catálogo 5.
> Gates: `test_harness_flags.py` **56 passed**, `test_harness_ratchet_meta.py` **4 passed**.
>
> **Los 9 KPI dieron el número exacto del plan, medidos:** K1 **9/9**, **K2 51/51** (el número
> corregido en la v2; el `51` sale de sumar las cuatro ubicaciones de `TaskStep`), K3 **3/3**,
> K4 **3/3** (`GL001`+`GL002`+`GL005` sobre el YAML de §2.3), K5 **0**, K6 **0**, K7 **12/12**,
> K8 **12/12**, **K9 = 0** (`test_ley_de_severidad_sobre_nivel_A` quedó **passed directo**, sin
> pasar por `xfail`, porque F2 y F3 se implementaron en la misma corrida).
>
> **BUG REAL DEL PLAN encontrado al implementar (F2):** el plan manda subir
> `RULES_VERSION` de `"243.1"` a `"249.1"` **y a la vez** exige (DoD #3) que
> `test_plan243_reglas_semanticas.py` quede verde **sin editarlo**. Las dos cosas no pueden ser
> ciertas: ese test **pinea** la constante (`assert RULES_VERSION == "243.1"`). Medido: con el
> bump, 1 failed / 26 passed. **Corrección aplicada:** `RULES_VERSION` queda en `"243.1"` y la
> familia GitLab lleva su **propia** `GITLAB_RULES_VERSION = "249.1"` — exactamente el patrón que
> el plan 248 ya usa con `SECURITY_RULES_VERSION` / `RECOMMENDATION_RULES_VERSION`. No se pierde
> información y el gate de no-regresión se cumple de verdad.
>
> **Hallazgo al cerrar F4:** el round-trip del nivel A fallaba en 1 de 9
> (`nightly-build-online`) porque `parse_gitlab_yaml` **nunca leía `rules`**, y `rules.if` **sí**
> está en `GITLAB_ROUNDTRIP_SUBSET`. Se recupera como la `condition` de los `Step` del job (que
> es de donde el renderer las emite). Con eso, **9/9 idempotentes**.
>
> **DoD #12, matiz honesto:** `grep -c "pipeline_inventory" api/devops.py` da **1**, no 0 — pero
> esa línea es la key de health `pipeline_inventory_enabled` que dejó el **plan 246**, no un
> import de este plan (`grep -c "import.*pipeline_inventory"` → **0** en los cuatro archivos).
> La independencia real del 246 se sostiene.
>
> **Pendiente:** el panel no monta una sección nueva (el plan lo declara así: reusa
> `PipelineLintPanel`); falta el **smoke visual** de que los `semantic_findings` se vean.
>
> Estado previo: **Serie "Mago de las Pipelines" (246–252) · Plan 249 · CRITICADO v2 · 2026-07-26**
> Dependencias: **ninguna dura de código**. El 249 **no consume ningún artefacto del 246 ni del
> 247** — hecho verificable, no declamado: el módulo que el 246 va a crear **no existe** en el
> árbol, y **ningún archivo de código de este plan lo importa ni lo nombra** (gate DoD #12,
> que se corre sobre los archivos de CÓDIGO, nunca sobre este documento). El 246 §0.2
> (`docs/246_PLAN_INVENTARIO_VIVO_DE_PIPELINES_MULTIPROVEEDOR.md:86-87`) pide que el 249 vaya
> "después del 246" por **orden de merge**, no por dependencia funcional: si el 246 no está, este
> plan corre igual y no degrada nada, porque no hay nada del 246 que leer.
> **Convención de anclajes de este documento (v2):** cuando un símbolo tiene decorador
> (`@dataclass`, `@_rule`, `@bp.post`), el anclaje apunta a la **primera línea del decorador**,
> no a la del `def`/`class`. Es una pista, no un contrato (§7.4).
> Lo no verificado está declarado en §2.6.

---

## Changelog v1 → v2 (crítica adversarial independiente, 2026-07-26)

> Veredicto de la v1: **RECHAZADO** — 4 bloqueantes. Todos resueltos abajo. La crítica se hizo
> **ejecutando el código real** con `backend/.venv/Scripts/python.exe`, no releyendo la prosa.

| # | Hallazgo v1 | Sev | Qué se hizo en v2 |
|---|---|---|---|
| **C1** | **`K2 = 24` era un número falso.** El corpus tiene **51** `TaskStep`, no 24. `24` es exactamente la suma de `root_task_steps`; la tabla §2.2 sumaba **13** en su columna `task:`. Tres números distintos para el mismo hecho, y `test_k2_los_24_task_steps_sobreviven` era un criterio binario construido sobre el equivocado | **BLOQ** | K2 pasa a **51**; §2.2 se reemplazó por la medición real desglosada por ubicación; el test se renombró a `test_k2_los_51_task_steps_sobreviven` |
| **C2** | **La receta del ratchet para el `.ps1` era literalmente incorrecta.** El plan mandaba `  tests/<archivo>.py` en **las dos** listas; `run_harness_tests.ps1:13` usa `"tests/…",` (comillas + coma). Un implementador literal rompía el script | **BLOQ** | §4 ahora da la línea **exacta y distinta** para cada lista, con el ejemplo real de cada archivo |
| **C3** | **El wiring de F5 era inimplementable.** (a) el endpoint está gateado por `STACKY_DEVOPS_PIPELINE_LINT_ENABLED` (`api/devops.py:199`, `abort(404)`) y el plan no lo mencionaba ⇒ los 5 tests darían 404; (b) decía "DESPUÉS de la línea `:209`" cuando `:209` es un `return` que hay que **reemplazar**; (c) usaba `kv_runner_tags` sin definirlo nunca | **BLOQ** | F5 reescrita con el diff antes/después completo, la flag del lint declarada como prerequisito del test, y `kv_runner_tags` derivada del body en una línea explícita |
| **C4** | **DoD #11 era imposible de cumplir:** `grep "…open(" services/cicd_semantic_rules.py` da **1 hit hoy** (`:418`). Un grep sobre un archivo no se puede acotar a "el bloque GitLab" | **BLOQ** | DoD #11 se partió en dos criterios ejecutables: grep 0-hits sobre el módulo **nuevo** (`cicd_gitlab_catalog.py`), y un test de importación que prueba pureza sin grep |
| **C5** | La tabla §2.2 **subreportaba**: `nightly-build-online` figuraba con 0 `task:` y tiene **8**; `bootstrap-server-environment` figuraba con 0 y su deployment tiene **2**; `cd-deploy-test` figuraba con 7 y tiene **11** | IMP | Tabla §2.2 reemplazada por la medición real con columna por ubicación |
| **C6** | `_deployment_doc_gitlab` asumía que **todo** `dp.steps` es `TaskStep`. Es cierto hoy sólo porque `_parse_deployment` (`pipeline_renderers.py:427`) **descarta** los `- script:` (`_scripts` sin usar). Arreglar ese parser reventaría F3 con `AttributeError` | IMP | `_task_step_to_script_lines` ahora acepta `Step` **y** `TaskStep`; se agregó test y se declaró la pérdida preexistente en §2.6 |
| **C7** | El invariante `_GL_NL_STRICT_ONLY` quedaba **sólo en un test**: el `return _check_gitlab(...)` temprano saltea el `assert` de `cicd_semantic_rules.py:541` | IMP | El `assert` se replica **dentro** de `_check_gitlab` |
| **C8** | **Reuso violado:** `frontend/src/components/devops/pipelineLint.ts` ya exporta `groupFindings` (`:62`) y `commitLintSummary` (`:157`), y `PipelineLintPanel.tsx` vive ahí. El plan creaba tres funciones equivalentes en **otra** carpeta | IMP | El módulo nuevo se mueve a `components/devops/gitlabProfileModel.ts`, **reusa** `groupFindings` y sólo aporta lo que no existe (`GL_RULE_TITLES`) |
| **C9** | `profile` es kwarg **obligatorio** de `check_semantics` (`:497`) y no significa nada en GitLab; la tabla de tests escribía literalmente `profile=...` | IMP | `profile` pasa a `profile: str = ""` y se declara ignorado cuando `provider="gitlab"`; todos los ejemplos usan `profile=""` |
| **C10** | Con `provider="gitlab"`, un YAML ilegible o >512 KB devolvía un finding con código **`RS000`** — un código ADO dentro de un reporte GitLab, que `GL_RULE_TITLES` no cubre | IMP | Se agrega **`GL000`** simétrico de `RS000`, y `GL_RULE_TITLES` lo incluye |
| **C11** | El encabezado borraba el "después del 246" del 246 §0.2 sin convertir la independencia en algo verificable | IMP | Encabezado reescrito + **DoD #12**, un grep de 0 hits sobre los **archivos de código** del 249. **OJO — gotcha recurrente de la casa evitada a propósito:** el gate NO se corre sobre este documento, porque la prosa que explica el gate contiene el término que el gate busca y se auto-invalidaría (es exactamente el error de la v1 en DoD #11, C4) |
| **C12** | Anclajes: **1 falso** (`_PROD_MARKERS:56` → real **55**). Los otros 13 desfasados apuntaban al decorador siguiendo una convención **no declarada** | MEN | `_PROD_MARKERS` corregido a `:55`; la convención del decorador queda declarada en el encabezado y en §7.4 |
| **C13** | `LintReport` tiene **6** campos (`pipeline_lint.py:42-52`), no 5: faltaba `fixes_omitted` | MEN | Enumeración corregida en F5 |
| **C14** | DoD #1 exigía "por archivo (6 corridas)" pero el comando era un glob `tests/test_plan249_*.py`, la corrida conjunta que la casa prohíbe | MEN | Las 6 corridas quedan escritas una por una |
| **C15** | `GITLAB_ROUNDTRIP_SUBSET` listaba `"variables"` **dos veces** ⇒ `len()==13` pero `len(set())==12`; el test "exactamente 13 entradas" quedaba ambiguo | MEN | Pasa a `dict` `{scope: keywords}`, sin duplicados y con el scope explícito |
| **C16** | Sin huella de regresión pese a matar una clase de error | MEN | F5 registra la huella en `docs/sistema/error_fingerprints.json` |
| **[ADICIÓN ARQUITECTO]** | — | — | **Ley de no-vacuidad + ley de severidad** (§3 P11, F2): cada `GL*` trae además un **contra-repro** que NO debe dispararla, y toda `GL*` de severidad `error` en modo `ambos` debe dar **0 hallazgos sobre el nivel A post-F3**. Convierte el corpus derivado de "foto" en **oráculo** |

---

## 0. La tesis del plan (leer esto antes que nada)

El Plan 243 encontró que el panel de pipelines **emitía YAML plausible que no compilaba nada**
para Azure DevOps, y lo arregló: catálogo cerrado de tareas (`cicd_task_catalog.py`), reglas
semánticas `RS001..RS009` (`cicd_semantic_rules.py`) y un renderer que sabe emitir `- task:`
con `inputs:`.

**Para GitLab, ese mismo agujero sigue abierto — y es peor.**

Peor no es una figura retórica. Para ADO el problema era de *incapacidad*: el modelo no podía
expresar `- task:`, así que el panel producía algo pobre pero visible. Para GitLab el problema
es de *silencio*: el renderer **acepta** un `PipelineSpec` con 6 tareas reales y emite un
`.gitlab-ci.yml` sintácticamente perfecto cuyo único cuerpo ejecutable es
`script: ["echo 'no-op'"]`. Nada en el sistema lo dice. El lint responde `ok=True`.

> **Medido, no supuesto** (§2.2, reproducible con un comando; **re-medido y corregido en v2**):
> sobre los **9 pipelines ADO reales** del corpus dorado, `to_gitlab_yaml(parse_ado_yaml(golden))`
> produce **9 de 9 pipelines GitLab sin un solo comando real**. **51** pasos `task:`, 3 jobs
> `deployment:` y 1 job raíz del corpus se convierten en **0 comandos emitidos**. Siete de los
> nueve no emiten siquiera un job.
>
> **[v2, C1] El número correcto es 51, no 24.** La v1 decía 24 —que es exactamente la suma de
> `root_task_steps`— y su propia tabla sumaba 13 en la columna `task:`. Los `TaskStep` del corpus
> viven en **cuatro** lugares distintos del `PipelineSpec` y hay que contar los cuatro:
> `root_task_steps` (24) + `job.task_steps` (13) + `root_jobs[*].task_steps` (8) +
> `deployment.steps` (6) = **51**. El desglose por archivo está en §2.2.

Y no hay red que lo atrape: `RS001..RS009` son **ADO por construcción** (leen `pool.vmImage`,
`$(VAR)`, `task:`, `strategy.runOnce`); las `PL001..PL014` son estructurales y aprueban
`script: ["echo 'no-op'"]` porque *tiene* un script.

> **La tesis:** la paridad multiproveedor del Plan 218 (§3.1, "un solo núcleo, N adaptadores")
> está construida en la capa de *transporte* — hay provider, hay client, hay CI provider. Lo que
> **no** tiene paridad es la capa de *conocimiento*: hoy Stacky **sabe** qué es un pipeline ADO
> correcto y **no sabe nada** de qué es un pipeline GitLab correcto. Este plan cierra esa capa,
> y la cierra con la misma disciplina que el 243: **catálogo como dato + reglas por perfil +
> subset explícitamente cerrado**, todo determinista y sin LLM.

**Corolario operativo:** cuando llegue el generador NL (243/244), GitLab va a estar a la par de
ADO sin tocar una línea del pipeline NL→spec. Este plan no escribe NL; le construye el piso.

---

## 1. Objetivo y valor

Que el panel de pipelines deje de emitir para GitLab artefactos que no ejecutan nada, y que
empiece a **decir en español qué está mal** en un `.gitlab-ci.yml` — propio o ajeno — con el
mismo nivel de conocimiento de dominio que hoy sólo tiene para Azure DevOps.

### KPI / impacto medible (todos binarios y verificables por comando)

| # | KPI | Hoy (medido) | Meta |
|---|---|---|---|
| K1 | Pipelines del corpus que al pasar a GitLab emiten ≥1 comando real | **0 / 9** | **9 / 9** |
| K2 | Pasos `task:` del corpus preservados al traducir a GitLab **[v2, C1: era 24, el real es 51]** | **0 / 51** | **51 / 51** |
| K3 | Jobs `deployment:` del corpus preservados como job GitLab con `environment:` | **0 / 3** | **3 / 3** |
| K4 | Defectos semánticos GitLab detectados sobre el YAML de §2.3 | **0 / 3** | **3 / 3** |
| K5 | Jobs ocultos (`.template`) promovidos a jobs reales por el round-trip | **1** (corrupción) | **0** |
| K6 | Falsos positivos de `scan_unsupported` sobre keywords legítimas de GitLab | **1** (`extends`) | **0** |
| K7 | Reglas `GL*` con `repro` mínimo que dispara su propia regla | 0 | **12 / 12** (`GL000..GL011`) |
| **K8** | **[ADICIÓN ARQUITECTO]** Reglas `GL*` con **contra-repro** que NO la dispara | 0 | **12 / 12** |
| **K9** | **[ADICIÓN ARQUITECTO]** Hallazgos `error` de modo `ambos` sobre el nivel A post-F3 (lo que Stacky emite no puede violar sus propias reglas duras) | n/a | **0** |

**Valor para el operador:** el que hoy trabaja contra GitLab tiene un panel que le miente por
omisión. Después de este plan tiene el mismo copiloto que ya tiene el que trabaja contra ADO.

---

## 2. Evidencia (verificada por lectura directa y por ejecución)

### 2.1 Lo que YA existe y este plan reutiliza sin reinventar

| Pieza | Anclaje (`archivo:línea (símbolo)`) | Qué aporta |
|---|---|---|
| Catálogo ADO (**patrón a espejar**) | `backend/services/cicd_task_catalog.py:28 (CATALOG_VERSION)`, `:35 (TaskInput)`, `:42 (TaskSpec)`, `:192 (TASK_CATALOG)`, `:199 (get_task)`, `:204 (is_allowed)`, `:209 (validate_inputs)` | La forma canónica de codificar dominio **como dato**: dataclasses frozen + dict por perfil + API que **nunca lanza** |
| Extractor canónico | `cicd_task_catalog.py:268 (extract_task_dicts)`, `:287 (extract_task_refs)` | Recorrido recursivo sobre `yaml.safe_load`. **Regla dura del 243 C20:** los `- task:` comentados no existen por construcción |
| Reglas semánticas ADO (**patrón a espejar**) | `backend/services/cicd_semantic_rules.py:41 (RULES_VERSION)`, `:43 (MODE_AUDIT)`, `:44 (MODE_NL_STRICT)`, `:45 (_MODES)`, `:48 (_NL_STRICT_ONLY)`, `:51 (MAX_YAML_BYTES)`, `:62 (SemanticFinding)`, `:73 (_StepCtx)`, `:105 (_iter_steps)`, `:497 (check_semantics)` | El eje `audit` / `nl_strict`, el dataclass de hallazgo, el guard de tamaño, y el `raise ValueError` ante modo inválido (`:503-504`) |
| Lint estructural con **eje de proveedor ya construido** | `backend/services/pipeline_lint.py:57 (LintContext)`, `:59 (provider: "ado"｜"gitlab")`, `:67 (_RULES)`, `:70 (_rule)`, `:791 (lint_yaml)` | El motor de reglas ya es multiproveedor. `_rule` **exige** un `repro` mínimo por regla |
| Helpers GitLab del lint (**reusar, no duplicar**) | `pipeline_lint.py:107 (_GITLAB_RESERVED)`, `:154 (_gitlab_jobs)`, `:165 (_gitlab_needs_refs)` | `_gitlab_jobs` ya excluye correctamente las claves reservadas y los jobs ocultos `.x` |
| Selftest de `repro` (**el corpus por construcción**) | `backend/tests/test_plan186_lint_catalogo.py:33 (test_toda_regla_tiene_repro)`, `:39 (test_todo_repro_dispara_su_regla)` | Cada regla trae su caso mínimo y un test verifica que lo dispara. **Es la respuesta de la casa al problema del corpus** (§2.5) |
| Renderer / parser GitLab (Plan 73) | `backend/services/pipeline_renderers.py:277 (to_gitlab_yaml)`, `:289 (_spec_to_gitlab_doc)`, `:250 (_translate_condition_to_gitlab)`, `:264 (_image_map)`, `:527 (parse_gitlab_yaml)` | Existen y funcionan para el subset v1. **Este plan los endurece, no los reescribe desde cero** |
| Declaración de lo no modelado | `pipeline_renderers.py:28 (UNSUPPORTED_CONSTRUCTS)`, `:51 (scan_unsupported)` | El patrón "declarar en vez de prometer" del 243 F2 |
| Modelo genérico (sirve a los dos) | `backend/services/pipeline_spec.py:81 (Job)`, `:85 (image)`, `:87 (runner_tags)`, `:90 (services)`, `:92 (task_steps)`, `:98 (Stage)`, `:111 (PipelineSpec)`, `:140 (dict_to_spec)` | `Job` **ya tiene** `image`, `runner_tags` y `services` — campos GitLab. No hay que tocar el modelo |
| Espejo contra corpus | `backend/services/cicd_corpus_mirror.py:38 (MIRROR_VERSION)`, `:42 (SEVERITY)`, `:45 (MIN_SIMILARITY)`, `:47 (_GOLDEN_DIRS)`, `:121 (nearest_golden)` | Doctrina **"silencio > consejo inventado"** (`:23-24`): bajo `MIN_SIMILARITY` devuelve `None` |
| Guardia de deriva de corpus | `backend/tests/test_plan243_task_catalog.py:32 (SOURCE_DIR)`, `:46 (PROVENANCE_PREFIX)`, `:122 (test_golden_tiene_header_de_procedencia)`, `:131 (test_corpus_dorado_no_derivo)` | La disciplina del C22 del 243 — y **su límite** (§2.5) |
| Endpoint de lint (seam de wiring) | `backend/api/devops.py:196 (pipeline_lint_validate_route)`, `:209 (lint_yaml(yaml_str, source, ...))`, `:212 (pipeline_lint_explain_route)` | Ya recibe `source ∈ {"ado","gitlab"}` y ya tiene guard per-request con `abort(404)` |
| Preview de los dos proveedores | `backend/api/pipeline_generator.py:19 (import to_ado_yaml, to_gitlab_yaml)`, `:46 (gitlab = to_gitlab_yaml(spec))` | La ruta por la que el YAML GitLab defectuoso llega hoy a la UI |
| Categoría de flags de paridad | `backend/services/harness_flags.py:112 (CategorySpec("paridad_proveedores", ...))`, `:425 ("paridad_proveedores": (...))` | **Congelada por el Plan 218 F2** (`docs/218…:153`). La flag de este plan vive ahí |

### 2.2 El agujero: para GitLab, el panel emite pipelines que no ejecutan nada

**Causa raíz, leída línea por línea en `_spec_to_gitlab_doc` (`pipeline_renderers.py:289-340`):**

| Lo que el spec trae | Qué hace `_spec_to_gitlab_doc` | Anclaje |
|---|---|---|
| `jb.task_steps` (los pasos reales de un pipeline ADO) | **Nunca los lee.** El bucle es `for step in jb.steps:` | `:321` |
| `spec.root_task_steps` / `spec.root_steps` | **Nunca los lee.** Sólo itera `spec.stages` | `:303` |
| `spec.root_jobs` | **Nunca los lee.** | `:303` |
| `st.deployments` (jobs `- deployment:` con `environment:`) | **Nunca los lee.** | `:307` |
| `jb.depends_on` | **Nunca lo emite** como `needs:` | `:307-338` |
| `st.condition` | `if st.condition: pass` — **código muerto literal** | `:304-306` |
| `jb.pool_name` (agente self-hosted) | Se pierde: `_image_map` sólo mira `pool_vm_image` | `:264`, `:309` |
| `spec.trigger_paths` / `pr_disabled` / `schedules` / `parameters` | Se pierden sin aviso (`trigger_branches` sí está declarado lossy-by-design en `:291`) | `:289-340` |
| Job que quedó sin ningún script | Emite `job_doc["script"] = ["echo 'no-op'"]` | `:331` |

Esa última línea es la que convierte una **pérdida** en una **mentira**: el artefacto sale
sintácticamente válido y ejecutable, y no hace nada.

**Medición completa sobre los 9 goldens** (`backend/tests/fixtures/cicd_nl/golden/`), obtenida
ejecutando el código real con `backend/.venv/Scripts/python.exe`:

**[v2, C1+C5] Tabla re-medida.** La de v1 subreportaba: daba `0` para `nightly-build-online`
(tiene **8** `task:` dentro de su job raíz), `0` para `bootstrap-server-environment` (su
`deployment` tiene **2**) y `7` para `cd-deploy-test` (tiene 7 en el job **+ 4** en sus dos
deployments = **11**). Las cuatro columnas de ubicación son las cuatro tuplas del `PipelineSpec`
donde el parser ADO deposita `TaskStep`; **hay que sumar las cuatro**.

| golden | stages | jobs | `root_task_steps` | `job.task_steps` | `root_jobs[*].task_steps` | `deployment.steps` | **TaskStep total** | `deployment:` | jobs GitLab emitidos | cuerpos `echo 'no-op'` |
|---|---|---|---|---|---|---|---|---|---|---|
| `agendaweb-ci.yml` | 0 | 0 | 7 | 0 | 0 | 0 | **7** | 0 | **0** | 0 |
| `bootstrap-server-environment.yml` | 1 | 0 | 0 | 0 | 0 | 2 | **2** | 1 | **0** | 0 |
| `cd-deploy-test.yml` | 3 | 1 | 0 | 7 | 0 | 4 | **11** | 2 | **1** | **1** |
| `ci-batch.yml` | 0 | 0 | 3 | 0 | 0 | 0 | **3** | 0 | **0** | 0 |
| `ci-cd-online.yml` | 1 | 1 | 0 | 6 | 0 | 0 | **6** | 0 | **1** | **1** |
| `ci-dacpac.yml` | 0 | 0 | 5 | 0 | 0 | 0 | **5** | 0 | **0** | 0 |
| `nightly-build-online.yml` | 0 | 0 | 0 | 0 | 8 (1 job raíz) | 0 | **8** | 0 | **0** | 0 |
| `pr-validation-online.yml` | 0 | 0 | 5 | 0 | 0 | 0 | **5** | 0 | **0** | 0 |
| `security-scan-online.yml` | 0 | 0 | 4 | 0 | 0 | 0 | **4** | 0 | **0** | 0 |
| **TOTAL** | | | **24** | **13** | **8** | **6** | **51** | **3** | **2** | **2** |

**Salida literal para `ci-cd-online.yml`** (el pipeline que compila AgendaWeb con 6 tareas
reales — `NuGetToolInstaller@1`, `NuGetCommand@2`, `VSBuild@1`, `DotNetCoreCLI@2`,
`PublishTestResults@2`, `PublishBuildArtifacts@1`):

```yaml
stages:
- Build
variables:
  solution: trunk/OnLine/Soluciones/AgendaWeb.sln
  testProject: trunk/OnLine/AgendaWebTests/AgendaWebTests/AgendaWebTests.csproj
  buildConfiguration: Release
  buildPlatform: Any CPU
BuildJob:
  stage: Build
  script:
  - echo 'no-op'
```

Las 4 variables sobrevivieron. Los 6 pasos que compilan, testean y publican, no.

### 2.3 El lint GitLab aprueba un pipeline con tres defectos que GitLab rechaza

Ejecutado contra el código real (`lint_yaml(GL, provider="gitlab")` →
`ok=True, counts={'error': 0, 'warning': 0, 'info': 0}`):

```yaml
stages: [build, deploy]
.base:
  image: mvn:3
build:
  stage: build
  extends: .base
  needs: [deploy]          # ← needs a un job de un stage POSTERIOR
  script: [mvn package]
deploy:
  stage: deploy
  environment: production  # ← deploy a producción sin compuerta manual
  script: [./deploy.sh]
ghost:
  stage: nonexistent       # ← stage no declarado en `stages:`
  script: [echo hi]
```

Los tres son defectos que **GitLab rechaza o ejecuta mal**, y ninguna regla existente los ve:
`PL003` (`pipeline_lint.py:373 (_pl003_gitlab)`) sólo verifica que el job del `needs` **exista**;
`PL004` (`:390 (_rule_pl004)`) sólo busca **ciclos**; `PL005` (`:447 (_rule_pl005)`) sólo exige
que haya `script`/`run`/`trigger`/`extends`; `PL006` (`:501 (_rule_pl006)`) sólo mira claves de
**raíz**. Ninguna conoce la relación `stage ↔ stages:`, ni el **orden topológico**, ni la
compuerta humana de un `environment`. Ese es exactamente el hueco de las `GL*`.

### 2.4 El parser/`scan_unsupported` corrompen y mal-declaran

Dos defectos más, ambos reproducidos ejecutando el código con el mismo YAML de §2.3:

1. **`scan_unsupported` marca `extends` como no soportado en GitLab.** Su allowlist
   (`pipeline_renderers.py:28 (UNSUPPORTED_CONSTRUCTS)`) es **ADO-específica**
   (`matrix`/`template`/`extends`/`resources`) y la función **no tiene eje de proveedor**
   (`:51`). En GitLab, `extends` es una keyword de primera clase y de uso corriente ⇒ **falso
   positivo estructural** (K6).

2. **`parse_gitlab_yaml` promueve los jobs ocultos a jobs reales.** El bucle
   `for key, val in doc.items()` (`pipeline_renderers.py:538`) sólo excluye `"stages"` y
   `"variables"` (`:539`), así que `.base` — un **template**, que GitLab nunca ejecuta — entra
   como job. El round-trip devuelve:

   ```yaml
   stages: [build, deploy, '', nonexistent]   # ← stage fantasma '' inventado
   .base:
     stage: ''
     image: mvn:3
     script:
     - echo 'no-op'                            # ← script inventado en un template
   ```

   Y de paso pierde `needs`, `environment`, `extends` y `rules`. **El lint ya sabe hacerlo
   bien** (`pipeline_lint.py:154-162 (_gitlab_jobs)` excluye `ks.startswith(".")`): el parser
   simplemente no reusó ese criterio.

### 2.5 El problema del corpus (resuelto explícitamente, no asumido)

**Verificado el 2026-07-26:** `find . -iname "*gitlab-ci*"` sobre todo el repo (excluyendo
`node_modules`) devuelve **cero resultados**. La única carpeta `fixtures/**/gitlab` que existe es
`backend/tests/fixtures/provider_contract/gitlab/`, y contiene **un solo archivo**,
`item_created.json` (457 bytes) — un fixture de *tracker*, no de CI. **No hay corpus GitLab, ni
dentro ni fuera del repo.**

Y la disciplina del 243 **no es trasplantable tal cual**: su guardia de deriva
(`test_plan243_task_catalog.py:131 (test_corpus_dorado_no_derivo)`) compara el corpus vendorizado
contra `SOURCE_DIR = r"N:\GIT\RS\RSPACIFICO\pipelines"` (`:32`), una ruta **fuera del repo y
específica de esta máquina**. Para GitLab no existe ni siquiera ese origen.

**Por lo tanto este plan NO inventa un corpus "real" de GitLab.** Adopta una estrategia de tres
niveles, y declara cuál es cuál (F0):

| Nivel | Qué es | Procedencia | Guardia de deriva |
|---|---|---|---|
| **A — derivado** | `to_gitlab_yaml(parse_ado_yaml(golden_ado))` para los 9 goldens | **Función determinista** de un corpus que YA tiene guardia | **Regenerar y comparar byte a byte.** Más fuerte que vendorizar: no depende de ninguna ruta externa |
| **B — repros por regla** | Un YAML mínimo por cada `GL000..GL011` **y su contra-repro (P11)** | Escrito por el plan, **declarado sintético** | El selftest `test_todo_repro_dispara_su_regla` (patrón `test_plan186_lint_catalogo.py:39`). Completo **por construcción**: una regla sin repro rompe el test |
| **C — real** | `.gitlab-ci.yml` de un proyecto GitLab del operador | **NO EXISTE HOY** | Se declara ausente. El espejo mira una carpeta vacía y **calla** (doctrina `cicd_corpus_mirror.py:23-24`) |

El nivel A es la clave: **su procedencia es reproducible por comando**, no por copia. Y como los
artefactos del nivel A hoy son la salida *defectuosa*, congelarlos en F0 y regenerarlos en F3
convierte el diff del fixture en **la evidencia revisable de que el renderer mejoró de verdad**
(test de aprobación). El nivel C **nunca se fabrica**: silencio antes que un golden inventado.

### 2.6 Lo NO verificado (declarado)

- **No se ejecutó ningún pipeline contra una instancia GitLab real.** No hay instancia
  alcanzable en esta máquina y `STACKY_GITLAB_ENABLED` está **OFF** por default
  (`backend/config.py:1185-1187`). Todas las afirmaciones sobre *qué rechaza GitLab* provienen de
  la semántica documentada del producto, **no** de una corrida. **Mitigación dura, dentro del
  plan:** ninguna regla `GL*` bloquea nada por sí sola — el consumidor decide; y toda `GL*` cuyo
  fundamento sea "GitLab lo rechaza" nace con su evidencia escrita en el campo `evidence` del
  `SemanticFinding`, igual que las `RS*`.
- **`needs` dentro del MISMO stage:** GitLab lo admite desde 14.2. **No se verificó la versión
  del GitLab del operador.** Por eso `GL002` marca **sólo** el caso inequívoco —
  `stage_index(destino) > stage_index(origen)` — y **nunca** el caso `==`.
- **DPAPI:** la memoria de la casa lo ubicaba en `gitlab_provider.py`. **Es incorrecto y queda
  corregido acá:** DPAPI vive en `backend/services/secrets_store.py:45 (import win32crypt)`,
  `:71 ("DPAPI sólo está disponible en Windows.")`, `:134 (CryptProtectData)`. `gitlab_provider.py`
  **no lo menciona** (0 ocurrencias). **Irrelevante para este plan de todos modos:** las 6 fases
  son módulos puros + un endpoint ya existente; **ninguna toca secretos, red ni disco del
  operador**.
- **Los write de GitLab sí viven en `gitlab_provider.py`** (verificado: `:602 (commit_file)`,
  `:534 (trigger_pipeline)`, `:487 (fetch_pipelines)`; `gitlab_ci_provider.py:23 (GitLabCIProvider)`
  sólo delega). **Este plan no llama a ninguno de ellos.**
- **La gotcha "GitLab inalcanzable por flag del módulo"** fue resuelta por el Plan 218 F0 y se
  verificó su rastro vivo en `gitlab_ci_provider.py:30-31` (comentario `D3 (Plan 218 F0): el
  kwarg real es project=`). **Este plan no reintroduce el problema porque no lee flags dentro de
  ningún módulo de servicio**: las 6 fases son puras y el único `getattr(config.config, ...)`
  vive en el endpoint (F5), que es el patrón sancionado (`backend/api/devops.py:199`).
- **Este plan no toca ninguna tabla ni crea persistencia nueva.**
- **[v2, C6] Pérdida PREEXISTENTE, declarada y NO arreglada por este plan:** `_parse_deployment`
  (`pipeline_renderers.py:418`) hace `_scripts, tasks, checkout, downloads = _parse_steps(...)`
  y luego `steps=tasks` (`:427-432`): **los pasos `- script:` crudos dentro de un `deployment:`
  se descartan antes de llegar al `PipelineSpec`.** Consecuencia para F3: hoy `dp.steps` contiene
  **sólo** `TaskStep`, pero eso es un accidente del parser, no un contrato del modelo
  (`DeploymentJob.steps` está anotado `tuple[TaskStep, ...]` en `pipeline_spec.py:75`, sin
  validación). **Por eso F3 NO asume el tipo:** `_task_step_to_script_lines` acepta `Step` y
  `TaskStep` y tiene un test dedicado. Arreglar `_parse_deployment` es del 250, no de acá — pero
  cuando pase, F3 **no** se rompe.
- **[v2, C3] El endpoint de F5 ya está gateado por otra flag preexistente:**
  `api/devops.py:199` hace `abort(404)` si `STACKY_DEVOPS_PIPELINE_LINT_ENABLED` es falsa. Su
  default es **`"true"`** (`backend/config.py:1577-1578`, verificado), así que no hay que
  encenderla — pero **todo test de F5 debe asegurarla ON explícitamente** o recibe 404 y falla
  por una razón que no tiene nada que ver con este plan.
- **[v2, C11] Independencia del 246, verificable:** el módulo de inventario que el 246 va a crear
  **no existe** en el árbol, y ningún archivo de código de este plan lo importa. No hay degradación
  que escribir porque no hay consumo que degradar. Es el gate DoD #12.

---

## 3. Principios, guardarraíles y corte de alcance declarado

- **P1 — Determinista y sin LLM, íntegramente.** Catálogo (dato) + reglas (funciones puras) +
  renderer/parser (puros). **Paridad de los 3 runtimes trivial y demostrable:** no hay ninguna
  ruta específica de Codex CLI, Claude Code CLI ni GitHub Copilot Pro; los tres importan el mismo
  módulo Python y obtienen el mismo resultado byte a byte. El fallback por runtime es
  **"no aplica: no hay divergencia posible"**, y se declara así en cada fase en vez de inventar
  una degradación que no existe.
- **P2 — No duplicar `PL*`.** Frontera dura y verificada en §2.3: lo que ya cubren
  `PL002/PL003/PL004/PL005/PL006/PL010..PL014` para GitLab **no** se reimplementa. F2 trae un
  test de anti-solape explícito.
- **P3 — Espejar el 243, no improvisar.** El catálogo copia la forma de `cicd_task_catalog.py`;
  las reglas viven **dentro** de `cicd_semantic_rules.py` y respetan `MODE_AUDIT` /
  `MODE_NL_STRICT` (`:43-45`) con la misma semántica: *audit* = "esto ya existe y anda",
  *nl_strict* = "esto lo acaba de generar Stacky".
- **P4 — Extracción SIEMPRE por `yaml.safe_load`, NUNCA por grep/regex.** Regla dura heredada
  del 243 C20 (`cicd_task_catalog.py:10-19`). F1 trae su test negativo propio.
- **P5 — Subset CERRADO, no promesa abierta.** El 243 fue **RECHAZADO en v2** por escribir un
  criterio "round-trip 9/9" que era alcance ilimitado disfrazado de criterio binario (su C14).
  Acá el round-trip se define sobre una **lista de keywords enumerada y versionada**
  (`GITLAB_ROUNDTRIP_SUBSET`, F4) y sobre un **conjunto finito y nombrado de artefactos**
  (niveles A y B de §2.5). Lo de afuera se **declara**, no se promete.
- **P6 — Backward-compatible.** Toda firma nueva es **kwarg con default**. `check_semantics(...)`
  sin `provider=` sigue comportándose byte-idéntico. `scan_unsupported(text)` sin `provider=`
  también. Los tests del 243 y del 73 quedan verdes sin tocarlos.
- **P7 — Cero trabajo extra para el operador.** Flag `STACKY_GITLAB_SEMANTIC_RULES_ENABLED`
  **default ON**. **Ninguna de las 4 excepciones duras aplica:** no bypasea revisión humana (sólo
  reporta), no es destructiva (no escribe nada), no exige prerequisito nuevo (es Python puro sobre
  texto que la UI ya manda), no reduce seguridad (sólo agrega detección). **Nota deliberada:** la
  flag **no** depende de `STACKY_GITLAB_ENABLED` (que está OFF por la excepción 3, `docs/218…:110
  P7`), porque analizar el **texto** de un `.gitlab-ci.yml` no requiere ninguna instancia GitLab.
  Atarlas dejaría la capacidad muerta en una instalación limpia — que es exactamente la gotcha
  "GitLab inalcanzable por flag del módulo" que el 218 F0 mató.
- **P8 — Human-in-the-loop.** Cero autonomía. Todo `GL*` **reporta**; nada autofixea, nada
  commitea, nada dispara. El commit sigue siendo el flujo HITL existente
  (`CommitPipelineModal.tsx`), que este plan no toca.
- **P9 — Mono-operador sin auth.** Sin RBAC, sin roles, sin permisos.
- **P10 — No degradar.** Con la flag OFF, la salida del endpoint es **byte-idéntica** a la
  actual. Sin red nueva. Sin I/O nuevo en el arranque.
- **P11 — [ADICIÓN ARQUITECTO] Ley de no-vacuidad y ley de severidad.** El selftest de `repro`
  que la casa usa desde el 186 (`test_plan186_lint_catalogo.py:39`) prueba que cada regla
  **dispara** sobre su propio caso mínimo. Eso es **la mitad** de la prueba, y la mitad fácil:
  una regla escrita como `return [finding]` pasa ese test. Nada en la casa prueba lo contrario —
  que la regla **no** dispare sobre un pipeline correcto. Sin corpus GitLab real (§2.5 nivel C),
  ese hueco es especialmente peligroso acá: una `GL*` demasiado ansiosa inundaría el panel de
  falsos positivos y **nadie se enteraría hasta que el operador la vea**. Por eso este plan agrega
  dos leyes, ambas deterministas y sin costo para el operador:

  1. **No-vacuidad (K8).** Toda `GL*` declara, junto a su `repro`, un **`contra_repro`**: el
     YAML **mínimamente distinto** que **no** debe dispararla (típicamente el mismo repro con el
     defecto corregido). `test_todo_contra_repro_NO_dispara_su_regla` lo verifica para las 12.
     Una regla sin `contra_repro` rompe el test, igual que una sin `repro`. Costo: 12 strings
     cortos. Valor: es el único test que puede atrapar una regla que dispara sobre todo.
  2. **Severidad (K9).** Toda `GL*` de severidad `error` y modo `ambos` debe producir **0**
     hallazgos sobre los 9 artefactos del **nivel A regenerados post-F3**. El fundamento es
     duro: después de F3, el nivel A **es lo que Stacky emite**. Si la salida propia de Stacky
     dispara una regla `error` propia, o la regla está mal o el renderer está mal — y el plan
     tiene que decir cuál **antes** de cerrarse, no después. Esta ley es la que convierte el
     corpus derivado de "foto del defecto" en **oráculo**: sin ella, el nivel A sólo demuestra
     que el renderer cambió, no que cambió **bien**.

  > Es el espejo exacto de la doctrina del 248 (*"error en `MODE_AUDIT` ⟺ 0 hits en el corpus"*),
  > aplicada al único corpus que este plan puede tener con honestidad.

**Corte de alcance declarado (§7 del dossier: máximo 6-7 fases; el 243 se partió por tener 10).**
Este plan implementa **F0 → F5, seis fases**. Se dejaron **fuera a propósito**, y no se
mencionan como "futuro" en ninguna fase para no crear alcance fantasma:
- Un **espejo GitLab** análogo a `cicd_corpus_mirror.py` — no hay corpus real que espejar (§2.5
  nivel C). Sin corpus, el espejo sería consejo inventado.
- **Autofixes** de las `GL*`. Las `PL*` tienen autofix; las `RS*` **no**, y las `GL*` siguen a las
  `RS*`.
- Perfiles GitLab **por stack** (el catálogo de F1 es de **constructos del lenguaje**, no de
  imágenes por tecnología). Un `PROFILE_*` por stack es del 247.

---

## 4. Fases

> **Comandos (verificados el 2026-07-26 en esta máquina; §4 del dossier).**
> **Trampa:** conviven `backend/.venv` (Python **3.13.5**) y `backend/venv` (3.11.9). **Usar `.venv`.**
>
> ```powershell
> # BACKEND — SIEMPRE por archivo (la suite completa se contamina)
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
> .venv\Scripts\python.exe -m pytest tests/<archivo>.py -q
>
> # BACKEND — ratchet del arnés (OBLIGATORIO tras crear CUALQUIER test_*.py nuevo)
> .venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
>
> # BACKEND — flags (OBLIGATORIO tras tocar services/harness_flags.py)
> .venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
>
> # BACKEND — no regresión del motor de pipelines
> .venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
> .venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q
> .venv\Scripts\python.exe -m pytest tests/test_plan186_lint_catalogo.py -q
>
> # FRONTEND — vitest ^4.1.9 está en frontend/package.json:30 (verificado); correr POR ARCHIVO
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
> npx vitest run src/components/devops/gitlabProfileModel.test.ts
> npx tsc --noEmit
> ```
>
> **Ratchet — obligatorio, en DOS listas, y con SINTAXIS DISTINTA en cada una.**
> **[v2, C2] La v1 mandaba la misma línea a las dos listas y eso rompe el `.ps1`.** Los dos
> archivos NO usan el mismo formato. Copiar literalmente:
>
> ```bash
> # backend/scripts/run_harness_tests.sh  — dentro de HARNESS_TEST_FILES=(  (:20)
> # SIN comillas, SIN coma, dos espacios de indentación. Ejemplo real vecino (:21-22):
> #   tests/test_harness_flags.py
>   tests/test_plan249_corpus_gitlab.py
> ```
>
> ```powershell
> # backend/scripts/run_harness_tests.ps1  — dentro de $HarnessTestFiles = @(  (:13)
> # CON comillas dobles y CON coma final. Ejemplo real vecino (:15-16):
> #   "tests/test_harness_flags.py",
>   "tests/test_plan249_corpus_gitlab.py",
> ```
>
> Sin la entrada en **ambas**, `tests/test_harness_ratchet_meta.py` queda rojo. Con la sintaxis
> del `.sh` metida en el `.ps1`, el script deja de parsear.
>
> **Rojo preexistente ajeno:** `test_harness_flags_help` tiene 4 fallos que **no son de este
> plan**. No arreglarlos; validar la entrada propia de forma aislada.

---

### F0 — El corpus GitLab: tres niveles, procedencia declarada, guardia regenerable

**Objetivo (1 frase):** resolver de raíz que no exista corpus GitLab, sin inventar uno falso.
**Valor:** todas las fases siguientes se prueban contra artefactos con procedencia declarada; y
el nivel A congela la foto del defecto de §2.2 para que la mejora de F3 sea **revisable en el
diff**.

**Archivos a crear:**

| Ruta exacta | Qué es |
|---|---|
| `Stacky Agents/backend/tests/fixtures/cicd_gitlab/PROCEDENCIA.md` | Declara los 3 niveles, qué es sintético y qué es derivado |
| `Stacky Agents/backend/tests/fixtures/cicd_gitlab/derived/<9 archivos>.gitlab-ci.yml` | Nivel A, uno por golden ADO |
| `Stacky Agents/backend/scripts/regen_gitlab_derived_corpus.py` | Regenerador determinista del nivel A |
| `Stacky Agents/backend/tests/test_plan249_corpus_gitlab.py` | Tests de F0 |

**Nombres exactos** — en `backend/scripts/regen_gitlab_derived_corpus.py`:
`ADO_GOLDEN_DIR`, `GITLAB_DERIVED_DIR`, `PROVENANCE_HEADER_FMT`, `derived_name(ado_name) -> str`,
`render_derived(ado_yaml_text) -> str`, `main() -> int`.

**Los 9 nombres del nivel A** (derivados por `derived_name`, que reemplaza el sufijo `.yml` por
`.gitlab-ci.yml`): `agendaweb-ci.gitlab-ci.yml`, `bootstrap-server-environment.gitlab-ci.yml`,
`cd-deploy-test.gitlab-ci.yml`, `ci-batch.gitlab-ci.yml`, `ci-cd-online.gitlab-ci.yml`,
`ci-dacpac.gitlab-ci.yml`, `nightly-build-online.gitlab-ci.yml`,
`pr-validation-online.gitlab-ci.yml`, `security-scan-online.gitlab-ci.yml`.

**Pseudocódigo:**

```python
# backend/scripts/regen_gitlab_derived_corpus.py — NUEVO
PROVENANCE_HEADER_FMT = (
    "# DERIVADO — NO EDITAR A MANO.\n"
    "# origen: backend/tests/fixtures/cicd_nl/golden/%s\n"
    "# generado por: backend/scripts/regen_gitlab_derived_corpus.py\n"
    "# receta: to_gitlab_yaml(parse_ado_yaml(<origen>))\n"
)

def render_derived(ado_yaml_text: str) -> str:
    from services.pipeline_renderers import parse_ado_yaml, to_gitlab_yaml
    return to_gitlab_yaml(parse_ado_yaml(ado_yaml_text))

def main() -> int:
    # Escribe PROVENANCE_HEADER_FMT % nombre_origen + render_derived(...) por cada golden.
    # Determinista: sorted(os.listdir(ADO_GOLDEN_DIR)). Idempotente: correrlo dos veces
    # deja el árbol byte-idéntico. Devuelve 0.
```

**Tests PRIMERO** — `backend/tests/test_plan249_corpus_gitlab.py`:

| Test | Verifica |
|---|---|
| `test_derivado_regenera_identico` | Para los 9: `PROVENANCE_HEADER_FMT % origen + render_derived(origen)` == contenido en disco, **byte a byte**. Es la guardia de deriva |
| `test_derivado_tiene_header_de_procedencia` | Los 9 empiezan con `"# DERIVADO — NO EDITAR A MANO."` |
| `test_derivado_no_depende_de_ruta_externa` | El texto de `regen_gitlab_derived_corpus.py` **no contiene** `"N:\\"` ni `"RSPACIFICO"` (a diferencia de `test_plan243_task_catalog.py:32`) |
| `test_procedencia_declara_los_tres_niveles` | `PROCEDENCIA.md` contiene las cadenas `"nivel A"`, `"nivel B"`, `"nivel C"` y la frase literal `"no existe corpus GitLab real"` |
| `test_nivel_c_esta_vacio_y_es_intencional` | `fixtures/cicd_gitlab/real/` no existe **o** está vacío; el test lo afirma **como contrato**, no como accidente |
| `test_foto_del_defecto_2026_07_26` | **Congela §2.2 al día de hoy:** los 9 derivados suman **0** ocurrencias de `- task:` y `cd-deploy-test`/`ci-cd-online` contienen `echo 'no-op'`. **F3 debe romper este test a propósito** y actualizarlo (test de aprobación) |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe scripts/regen_gitlab_derived_corpus.py
.venv\Scripts\python.exe -m pytest tests/test_plan249_corpus_gitlab.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio de aceptación BINARIO:** `test_plan249_corpus_gitlab.py` **6 passed**; el ratchet
**verde** con `tests/test_plan249_corpus_gitlab.py` presente **en las dos** listas; correr el
regenerador dos veces seguidas deja `git status` sin cambios en `fixtures/cicd_gitlab/`.

**Flag:** ninguna (fixtures y script de test; no hay código de producción).
**Impacto por runtime:** Codex / Claude Code / Copilot — **idéntico**. Script Python puro sobre
archivos del repo; no hay ruta específica de runtime y por lo tanto **no hay fallback que
definir**.
`Trabajo del operador: ninguno`

---

### F1 — `cicd_gitlab_catalog.py`: los constructos de GitLab CI, codificados como DATO

**Objetivo (1 frase):** que Stacky **sepa** qué keywords existen en GitLab CI, dónde son válidas,
cuáles están deprecadas y cuáles exigen una compuerta — igual que ya sabe de tareas ADO.
**Valor:** es la base factual de las 12 reglas de F2. Sin catálogo, las reglas serían opiniones.

**Archivo a crear:** `Stacky Agents/backend/services/cicd_gitlab_catalog.py`
**Archivo de test:** `Stacky Agents/backend/tests/test_plan249_gitlab_catalog.py`

**Nombres exactos:** `GITLAB_CATALOG_VERSION = "249.1"`, `SCOPE_ROOT`, `SCOPE_JOB`, `SCOPE_BOTH`,
`@dataclass(frozen=True) KeywordSpec`, `ROOT_KEYWORDS`, `JOB_KEYWORDS`, `KEYWORD_CATALOG`,
`WHEN_VALUES`, `IMPLICIT_STAGES`, `DEPRECATED_KEYWORDS`, `GATED_KEYWORDS`, `PROD_ENV_MARKERS`,
`get_keyword(name, scope)`, `is_known_keyword(name, scope)`, `is_deprecated(name)`,
`job_dicts(doc)`, `hidden_job_names(doc)`, `stage_index_map(doc)`.

**Contrato (espejo exacto de `cicd_task_catalog.py:35-51`):**

```python
@dataclass(frozen=True)
class KeywordSpec:
    name: str                 # "needs"
    scope: str                # SCOPE_ROOT | SCOPE_JOB | SCOPE_BOTH
    value_kind: str           # "str"|"list"|"map"|"bool"|"int"|"str_or_list"|"any"
    allowed_values: tuple = ()    # enum cerrado (ej. when)
    deprecated_by: str = ""       # "rules"  → only/except
    requires_gate: str = ""       # "when"   → environment
    evidence: str = ""            # por qué está en el catálogo
```

#### Tabla del catálogo GitLab (el corazón de F1)

**Raíz (`SCOPE_ROOT`) — 11 keywords.** Las 11 primeras coinciden **exactamente** con
`pipeline_lint.py:107-110 (_GITLAB_RESERVED)`: el catálogo **reusa ese conjunto verificado**
en vez de proponer uno paralelo que pueda divergir (F1 trae un test que lo fija).

| Keyword | `value_kind` | Notas |
|---|---|---|
| `stages` | `list` | Orden = orden de ejecución. Fundamento de `GL001` y `GL002` |
| `variables` | `map` | Ya cubierto por `PL010..PL014` para valores/secretos |
| `include` | `str_or_list` | Trae jobs y templates **de otro archivo** ⇒ desactiva `GL006` (§F2) |
| `workflow` | `map` | Reglas a nivel pipeline |
| `default` | `map` | Valores por defecto de job (`image`, `tags`, …) ⇒ satisface `GL009` |
| `image` | `str_or_list` | Imagen por defecto de todos los jobs |
| `services` | `list` | Contenedores auxiliares |
| `before_script` | `list` | — |
| `after_script` | `list` | — |
| `cache` | `map` | — |
| `pages` | `map` | Job especial de GitLab Pages |

**Job (`SCOPE_JOB`) — 24 keywords.**

| Keyword | `value_kind` | `allowed_values` / gate | Notas |
|---|---|---|---|
| `stage` | `str` | — | Debe pertenecer a `stages` ∪ `IMPLICIT_STAGES` → `GL001` |
| `script` | `str_or_list` | — | Cuerpo ejecutable |
| `before_script` / `after_script` | `list` | — | — |
| `image` | `str_or_list` | — | → `GL009` |
| `services` | `list` | — | — |
| `tags` | `list` | — | Exige runner con esos tags → `GL007` |
| `needs` | `str_or_list` | — | DAG. Orden topológico → `GL002` |
| `extends` | `str_or_list` | — | Debe resolver a un job oculto → `GL006` |
| `rules` | `list` | — | Excluyente con `only`/`except` → `GL003` |
| `only` | `any` | `deprecated_by="rules"` | → `GL003`, `GL004` |
| `except` | `any` | `deprecated_by="rules"` | → `GL003`, `GL004` |
| `when` | `str` | `WHEN_VALUES` | Compuerta de `environment` → `GL005` |
| `environment` | `str｜map` | `requires_gate="when"` | → `GL005` |
| `artifacts` | `map` | — | `paths` → `GL008` |
| `cache` | `map` | — | — |
| `variables` | `map` | — | — |
| `allow_failure` | `bool` | — | (El eje "enmascara fallos" es del **248**, no de acá) |
| `retry` | `int｜map` | — | — |
| `timeout` | `str` | — | — |
| `parallel` | `int｜map` | — | `parallel:matrix` **no** se round-trippea (F4) |
| `dependencies` | `list` | — | Artefactos, distinto de `needs` |
| `resource_group` | `str` | — | — |
| `interruptible` | `bool` | — | — |
| `trigger` | `str｜map` | — | Pipeline hijo. **No** se round-trippea (F4) |

**Constantes de dominio:**

```python
WHEN_VALUES      = ("on_success", "on_failure", "always", "manual", "delayed", "never")
IMPLICIT_STAGES  = (".pre", ".post")   # existen SIN declararse en `stages:` (clave para GL001)
DEPRECATED_KEYWORDS = ("only", "except")
GATED_KEYWORDS   = {"environment": "when"}
PROD_ENV_MARKERS = ("prod", "produccion", "producción")   # mismo criterio que _PROD_MARKERS
                                                          # (cicd_semantic_rules.py:55) [v2, C12:
                                                          #  la v1 decía :56 — anclaje FALSO,
                                                          #  el único de todo el documento)
```

**Helpers estructurales — reusan el criterio ya probado del lint, no uno nuevo:**

```python
def job_dicts(doc) -> dict:
    """{nombre: dict} de los jobs REALES. PURA. NUNCA lanza.
    Excluye claves de ROOT_KEYWORDS y jobs ocultos (`.x`), exactamente como
    pipeline_lint.py:154-162 (_gitlab_jobs). El criterio vive UNA vez."""

def hidden_job_names(doc) -> tuple:
    """Templates `.x` en orden alfabético — el universo válido de `extends` (GL006)."""

def stage_index_map(doc) -> dict:
    """{nombre_de_stage: índice}. `.pre` -> -1, `.post` -> len(stages).
    Fundamento del orden topológico de GL002."""
```

**Tests PRIMERO** — `backend/tests/test_plan249_gitlab_catalog.py`:

| Test | Verifica |
|---|---|
| `test_root_keywords_coincide_con_lint_gitlab_reserved` | `set(ROOT_KEYWORDS) == pipeline_lint._GITLAB_RESERVED`. **Impide que los dos conjuntos diverjan** |
| `test_catalogo_no_lanza_ante_desconocido` | `get_keyword("inventada", SCOPE_JOB) is None`; `is_known_keyword("inventada", SCOPE_JOB) is False` |
| `test_when_values_es_enum_cerrado` | `get_keyword("when", SCOPE_JOB).allowed_values == WHEN_VALUES` |
| `test_only_except_declaradas_deprecadas` | `is_deprecated("only")` y `is_deprecated("except")` son `True`; su `deprecated_by == "rules"` |
| `test_environment_declara_su_gate` | `get_keyword("environment", SCOPE_JOB).requires_gate == "when"` |
| `test_job_dicts_excluye_ocultos_y_reservadas` | Sobre el YAML de §2.3: `job_dicts` devuelve exactamente `{"build","deploy","ghost"}` (**sin** `.base`, **sin** `stages`) |
| `test_hidden_job_names_encuentra_templates` | Sobre el mismo YAML: `hidden_job_names(doc) == (".base",)` |
| `test_stage_index_map_incluye_implicitos` | `{".pre": -1, "build": 0, "deploy": 1, ".post": 2}` |
| `test_extraccion_por_safe_load_no_por_regex` | Un YAML con `# needs: [fantasma]` **comentado** ⇒ `job_dicts` no ve ninguna `needs`. **Test negativo del P4** |
| `test_version_del_catalogo_declarada` | `GITLAB_CATALOG_VERSION == "249.1"` |
| `test_todo_keyword_tiene_evidence` | Toda entrada de `KEYWORD_CATALOG` tiene `evidence` no vacío |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan249_gitlab_catalog.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio BINARIO:** `test_plan249_gitlab_catalog.py` **11 passed**; ratchet verde con el archivo
en las dos listas.
**Flag:** ninguna (módulo puro sin call-site aún; se enciende en F5).
**Impacto por runtime:** idéntico en los 3 — dataclasses y dicts de Python, sin I/O. **No hay
fallback que definir.**
`Trabajo del operador: ninguno`

---

### F2 — Reglas semánticas de perfil GitLab: `GL000..GL011`

**Objetivo (1 frase):** que un `.gitlab-ci.yml` sintácticamente válido pero semánticamente roto
deje de pasar en silencio.
**Valor:** cierra K4. Es el corazón del plan.

**Archivo a editar:** `Stacky Agents/backend/services/cicd_semantic_rules.py` (**aditivo**).
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan249_reglas_gitlab.py`

**Cambio de firma (backward-compatible, P6):**

```python
# cicd_semantic_rules.py — EDITAR
RULES_VERSION = "249.1"          # era "243.1" (:41)

PROVIDER_ADO = "ado"
PROVIDER_GITLAB = "gitlab"
_PROVIDERS = (PROVIDER_ADO, PROVIDER_GITLAB)

# Espejo EXACTO de _NL_STRICT_ONLY (:48) para el eje GitLab.
_GL_NL_STRICT_ONLY = ("GL004", "GL008", "GL009", "GL010", "GL011")

# [v2, C9] `profile` pasa de OBLIGATORIO a opcional con default "". Es aditivo y
# backward-compatible: los 11 call-sites de test_plan243_reglas_semanticas.py lo siguen
# pasando explícito. Con provider="gitlab", `profile` se IGNORA (no existe el concepto de
# perfil de agente en GitLab); pasar "" es lo correcto y así lo hacen todos los ejemplos.
def check_semantics(yaml_text: str, *, profile: str = "", repo_root: str = None,
                    mode: str = MODE_AUDIT,
                    provider: str = PROVIDER_ADO,          # ← NUEVO, default = comportamiento actual
                    known_runner_tags: list = None) -> list:  # ← NUEVO, None = GL007 no se evalúa
    if mode not in _MODES:
        raise ValueError(...)                                     # PRIMERO, sin cambios (:503-504)
    if provider not in _PROVIDERS:
        raise ValueError("provider inválido: %r (esperado %s)"
                         % (provider, " o ".join(_PROVIDERS)))   # ruidoso, nunca silencioso
    # ... guard de MAX_YAML_BYTES y yaml.safe_load SIN CAMBIOS (:506-524), CON UNA SALVEDAD:
    #     [v2, C10] esos dos guards emiten hoy el código "RS000". Con provider="gitlab" deben
    #     emitir "GL000" — un código ADO dentro de un reporte GitLab es un bug de contrato, y
    #     GL_RULE_TITLES (F5) no lo cubriría. El texto del mensaje NO cambia; sólo el código:
    #         codigo_guard = "GL000" if provider == PROVIDER_GITLAB else "RS000"
    if provider == PROVIDER_GITLAB:
        return _check_gitlab(doc, mode=mode, known_runner_tags=known_runner_tags)
    # ... cuerpo ADO existente, intacto (:526-542) ...


def _check_gitlab(doc: dict, *, mode: str, known_runner_tags: list = None) -> list:
    """GL000..GL011 sobre un documento GitLab ya parseado. PURA. NUNCA lanza."""
    # ... GL001..GL003, GL005..GL007 siempre; el resto sólo en MODE_NL_STRICT ...
    # [v2, C7] El invariante se enforcea EN EL CÓDIGO, no sólo en un test. La v1 lo dejaba
    # únicamente en `test_nl_strict_only_no_aparece_en_audit` porque el `return` temprano de
    # check_semantics saltea el assert de :541. Se replica acá, simétrico al de ADO:
    assert all(f.code not in _GL_NL_STRICT_ONLY for f in findings) or mode == MODE_NL_STRICT
    return findings
```

`SemanticFinding` (`:63`, decorador en `:62`) **se reusa tal cual**: mismos 5 campos. `severity`
sigue viniendo de `SEV_ERROR`/`SEV_WARNING` importados en `cicd_semantic_rules.py:39`.

#### Tabla de reglas `GL000..GL011` (el corazón del plan)

Severidad: **E** = `SEV_ERROR`, **W** = `SEV_WARNING`.
Modo: **ambos** = se evalúa siempre (verdad del dominio) · **nl_strict** = sólo sobre lo que
Stacky genera (espeja `_NL_STRICT_ONLY`, `:48`).

| ID | Título | Sev | Modo | Qué la dispara (condición exacta) | Remediación (mensaje al operador) |
|---|---|---|---|---|---|
| **GL000** | **[v2, C10]** Documento fuera de rango o ilegible | **W** | ambos | `len(yaml_text) > MAX_YAML_BYTES` **o** `yaml.safe_load` lanza `YAMLError`. Espejo exacto de `RS000` (`cicd_semantic_rules.py:507`, `:517`) con código GitLab | El mismo texto que `RS000`. **Sin `GL000`, un reporte GitLab devolvería un código `RS*` y `GL_RULE_TITLES` no tendría cómo titularlo** |
| **GL001** | Job en un stage no declarado | **E** | ambos | `jd["stage"]` es `str` y **no** está en `doc["stages"]` ∪ `IMPLICIT_STAGES` | «el job '{job}' declara `stage: {s}`, que no está en `stages:`. GitLab rechaza el pipeline. Agregá '{s}' a `stages:` o usá uno de: {lista}» |
| **GL002** | `needs` a un job de un stage posterior | **E** | ambos | `stage_index(destino) > stage_index(origen)`. **Nunca** si son iguales (§2.6) | «el job '{a}' necesita a '{b}', que corre en un stage POSTERIOR ('{sb}' va después de '{sa}'). Movelo o quitá el `needs`» |
| **GL003** | `only`/`except` mezclado con `rules` | **E** | ambos | El **mismo** job tiene `rules` **y** (`only` **o** `except`) | «el job '{job}' usa `rules` y `{k}` a la vez: GitLab ignora uno de los dos y el resultado es indefinido. Dejá sólo `rules`» |
| **GL004** | `only`/`except` legado | **W** | nl_strict | El job tiene `only` o `except` y **no** tiene `rules` | «`{k}` es la sintaxis vieja. Un pipeline generado usa `rules:`, que es la que GitLab documenta y la única que soporta condiciones compuestas» |
| **GL005** | Deploy a producción sin compuerta humana | **E** | ambos | El job tiene `environment` cuyo nombre contiene un `PROD_ENV_MARKERS`, **y** ni `when == "manual"` ni ningún `rules[i]["when"] == "manual"` | «el job '{job}' despliega a '{env}' sin `when: manual`: cualquier push a la rama publica a producción sin que nadie confirme. Agregá `when: manual`» |
| **GL006** | `extends` a un template ausente | **E** | ambos | `extends` referencia un nombre **no** presente en `hidden_job_names(doc)` ni en `job_dicts(doc)`. **Se omite entera si `doc` tiene `include`** (el template puede venir de otro archivo — no se puede afirmar sin inventar) | «el job '{job}' extiende '{t}', que no está definido en este archivo. Declaralo como job oculto (`.{t}:`) o agregá el `include:` que lo trae» |
| **GL007** | `tags` que exigen un runner que no existe | **W** | ambos | `known_runner_tags` **no** es `None` **y** algún tag del job no está en ese conjunto. `None` ⇒ la regla **no se evalúa** (degradación explícita, igual que `PL013`, `pipeline_lint.py:736-737`) | «el job '{job}' pide un runner con el tag '{t}', que no está registrado en el proyecto: el job quedaría en `pending` para siempre» |
| **GL008** | `artifacts:paths` que el job no produce | **W** | nl_strict | Un path de `artifacts.paths` (sin `*`, sin `$`) cuyo **primer segmento** no aparece en ninguna línea de `script`/`after_script` del job | «el job '{job}' publica el artefacto '{p}', que ningún comando suyo menciona: el `artifacts:` saldría vacío» |
| **GL009** | Job sin imagen ni runner resolubles | **W** | nl_strict | El job no tiene `image` ni `tags`, **y** la raíz no tiene `image` ni `default.image` ni `default.tags` | «el job '{job}' no dice sobre qué corre (`image:` ni `tags:`) y el archivo no define un `default:`. Va a caer en el runner compartido, que puede no existir» |
| **GL010** | Keyword fuera del catálogo | **E** | nl_strict | Una clave del job que **no** está en `JOB_KEYWORDS` (`is_known_keyword(k, SCOPE_JOB)` es `False`) | «'{k}' no es una keyword de job de GitLab CI: un pipeline generado sólo puede usar el catálogo cerrado. Válidas: {lista}» |
| **GL011** | Pipeline generado sin un solo comando real | **E** | nl_strict | **Todos** los jobs reales tienen `script` vacío, ausente, o compuesto **únicamente** por comandos de relleno (`ECHO_NOOP_MARKERS = ("echo 'no-op'", 'echo "no-op"', "echo no-op")`) | «este pipeline no ejecuta ningún comando real: sale válido y no hace nada. Es el defecto que el Plan 249 §2.2 mató; revisá que la traducción no haya perdido los pasos» |

> **`GL011` es la red de seguridad del bug de §2.2.** Aunque F3 arregle el renderer, `GL011`
> impide que **cualquier** camino futuro vuelva a emitir el artefacto vacío sin que nadie avise.
> Es a este plan lo que `RS002` es al ADO-369: el incidente convertido en gate.

**Anti-solape con `PL*` (P2) — obligatorio y testeado.** Ninguna `GL*` reimplementa:
`PL002` (jobs duplicados), `PL003` (`needs` a job inexistente — `GL002` asume que **existe** y
mira su **stage**), `PL004` (ciclos), `PL005` (job sin cuerpo — `GL011` mira el **pipeline
entero**, no el job), `PL006` (clave de raíz — `GL010` mira claves de **job**),
`PL010..PL014` (variables y secretos).

**Tests PRIMERO** — `backend/tests/test_plan249_reglas_gitlab.py`:

| Test | Verifica |
|---|---|
| `test_repro_de_cada_regla_dispara_su_regla` | **Nivel B del corpus (§2.5).** Tabla `GL_REPROS: dict[str, str]` con las **12** entradas (`GL000..GL011`); para cada una, `check_semantics(repro, profile="", provider="gitlab", mode=MODE_NL_STRICT)` contiene su propio código. **Un `GL*` sin repro rompe el test** (espeja `test_plan186_lint_catalogo.py:39`). **Es K7: 12/12.** **[v2, C9]** `profile=""` literal, no `profile=...` |
| `test_todo_contra_repro_NO_dispara_su_regla` | **[ADICIÓN ARQUITECTO — P11 ley de no-vacuidad].** Tabla `GL_CONTRA_REPROS: dict[str, str]`, también con las **12** entradas. Para cada `GLnnn`: `check_semantics(contra_repro, profile="", provider="gitlab", mode=MODE_NL_STRICT)` **no** contiene `GLnnn`. Cada contra-repro es el `repro` con el defecto **corregido** (ej. `GL001`: el mismo YAML con el stage agregado a `stages:`). **Un `GL*` sin contra-repro rompe el test igual que uno sin repro. Es K8: 12/12** |
| `test_ley_de_severidad_sobre_nivel_A` | **[ADICIÓN ARQUITECTO — P11 ley de severidad].** Para los 9 artefactos de `fixtures/cicd_gitlab/derived/`: `check_semantics(x, profile="", provider="gitlab", mode=MODE_AUDIT)` produce **cero** hallazgos de severidad `error`. **Se escribe en F2 y queda ROJO hasta F3** (hoy el nivel A es la foto del defecto); F3 lo pone verde. Es el test que prueba que el renderer mejoró **bien**, no sólo que cambió. **Es K9: 0.** Marcar con `@pytest.mark.xfail(strict=True, reason="verde recién en F3")` mientras F3 no esté, y **quitar el xfail en F3** |
| `test_yaml_de_evidencia_dispara_gl001_gl002_gl005` | Sobre el YAML **literal** de §2.3: los 3 códigos presentes en `MODE_AUDIT`. **Es K4** |
| `test_gl002_no_marca_needs_en_el_mismo_stage` | Dos jobs en el mismo stage con `needs` entre sí ⇒ **cero** `GL002` (§2.6) |
| `test_gl001_acepta_pre_y_post` | `stage: .pre` y `stage: .post` **sin** declararlos ⇒ cero `GL001` |
| `test_gl005_se_apaga_con_when_manual` | Igual que §2.3 pero con `when: manual` ⇒ cero `GL005`. Idem con `rules: [{if: ..., when: manual}]` |
| `test_gl006_se_omite_si_hay_include` | El YAML de §2.3 **+** `include: [{local: x.yml}]` ⇒ cero `GL006` |
| `test_gl007_no_evalua_sin_inventario` | `known_runner_tags=None` ⇒ cero `GL007`; `known_runner_tags=["docker"]` con `tags: [windows]` ⇒ **uno** |
| `test_nl_strict_only_no_aparece_en_audit` | En `MODE_AUDIT`, **ningún** finding tiene código en `_GL_NL_STRICT_ONLY`. **[v2, C7]** El `assert` equivalente ahora vive **dentro de `_check_gitlab`**, no sólo en este test: el `return` temprano de `check_semantics` saltea el `assert` de `:541` |
| `test_gl000_usa_codigo_gitlab_no_rs000` | **[v2, C10]** Con `provider="gitlab"`: un YAML de >512 KB y un YAML ilegible (`"esto: [no cierra\n"`) devuelven código **`GL000`**, nunca `RS000`. Con `provider="ado"` siguen devolviendo `RS000` (**P6**) |
| `test_gl011_detecta_el_derivado_vacio` | Sobre `fixtures/cicd_gitlab/derived/ci-cd-online.gitlab-ci.yml` (nivel A, F0) en `MODE_NL_STRICT` ⇒ **`GL011` presente**. **Une F0 con F2 sobre evidencia real** |
| `test_provider_invalido_lanza` | `provider="bitbucket"` ⇒ `ValueError` |
| `test_ado_sigue_identico_sin_provider` | Los 9 goldens ADO con la firma **vieja** (sin `provider=`) dan **exactamente** los mismos findings que antes del cambio. **Es P6** |
| `test_no_solapa_con_pl` | Los `repro` de `GL001`, `GL002`, `GL010`, `GL011` pasados por `lint_yaml(..., provider="gitlab")` producen **cero** findings `PL*` de severidad `error`: prueba que las `GL*` cubren un hueco real |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan249_reglas_gitlab.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q   # no regresión ADO
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```

**Criterio BINARIO:** `test_plan249_reglas_gitlab.py` **15 passed, 1 xfailed**
(los 12 de la v1 + `test_todo_contra_repro_NO_dispara_su_regla` + `test_gl000_usa_codigo_gitlab_no_rs000`
+ `test_ley_de_severidad_sobre_nivel_A`, este último **xfail estricto hasta F3**);
`test_plan243_reglas_semanticas.py` **sigue verde sin editarlo**; ratchet verde.
**Flag:** `STACKY_GITLAB_SEMANTIC_RULES_ENABLED` — declarada y consumida en **F5**. En F2 el
módulo es puro y sin call-site (mismo patrón que `check_semantics` hoy, que no tiene consumidor).
**Impacto por runtime:** idéntico en los 3. Funciones puras sobre un dict de `yaml.safe_load`.
**No hay fallback que definir.**
`Trabajo del operador: ninguno`

---

### F3 — El renderer deja de emitir pipelines vacías

**Objetivo (1 frase):** que `to_gitlab_yaml` traduzca los pasos `task:`, los jobs raíz y los
`deployment:` en vez de tirarlos.
**Valor:** K1, K2, K3. Es la fase que convierte 9 artefactos inútiles en 9 útiles.

**Archivo a editar:** `Stacky Agents/backend/services/pipeline_renderers.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan249_renderer_gitlab.py`

**Nombres exactos nuevos:** `GITLAB_RENDERER_VERSION = "249.1"`, `_task_step_to_script_lines`,
`_job_doc_gitlab`, `_deployment_doc_gitlab`, `_needs_value`, `TASK_TRANSLATION_MAP`,
`UNTRANSLATABLE_TASK_MARKER`.

**Diff ilustrativo (`_spec_to_gitlab_doc`, hoy `:289-340`):**

```python
def _task_step_to_script_lines(t) -> list:
    """Paso ADO -> líneas de `script:` GitLab. PURA.

    HONESTIDAD ANTES QUE MAGIA: sólo traduce lo que tiene equivalente real y
    verificable. Lo demás NO se inventa: se emite como un comentario marcado y
    GL011 se encarga de que un pipeline hecho sólo de esos no pase por bueno.

    [v2, C6] Acepta `Step` **y** `TaskStep`. La v1 asumía TaskStep y leía `t.task`
    directo. Eso es cierto HOY sólo porque `_parse_deployment` (:418) descarta los
    `- script:` de un deployment (`_scripts` sin usar, :427). Es un accidente del
    parser, no un contrato del modelo (`DeploymentJob.steps` no se valida). El día
    que el 250 lo arregle, la v1 habría reventado con
    `AttributeError: 'Step' object has no attribute 'task'`.
    """
    if not hasattr(t, "task"):                 # es un Step: ya trae el comando literal
        return [l for l in (t.script or "").split("\n") if l.strip()]
    ref = t.task
    if ref in TASK_TRANSLATION_MAP:
        return TASK_TRANSLATION_MAP[ref](t.inputs)     # ej. DotNetCoreCLI@2 -> "dotnet build ..."
    return ["%s %s (inputs: %s)" % (UNTRANSLATABLE_TASK_MARKER, ref,
                                    ", ".join(sorted(t.inputs)))]

# TASK_TRANSLATION_MAP — CERRADO y versionado. Sólo las 3 tareas del catálogo ADO cuyo
# equivalente en un runner Linux/Windows de GitLab es literal y no requiere inventar nada:
#   DotNetCoreCLI@2  -> "dotnet <command> <projects> <arguments>"
#   PowerShell@2     -> "pwsh -File <filePath> <arguments>"   (sólo con filePath; inline NO)
#   CopyFiles@2      -> "cp -r <SourceFolder>/<Contents> <TargetFolder>"
# Las otras 7 (VSBuild@1, NuGetCommand@2, ...) NO tienen equivalente honesto en GitLab:
# se emiten con UNTRANSLATABLE_TASK_MARKER = "# TODO(stacky-249): sin equivalente GitLab para"

def _job_doc_gitlab(jb, stage_name, spec) -> dict:
    job_doc = {"stage": stage_name}
    img = _image_map(jb.pool_vm_image, jb.image)          # SIN CAMBIOS (:264)
    if img: job_doc["image"] = img
    if jb.runner_tags: job_doc["tags"] = list(jb.runner_tags)
    elif jb.pool_name: job_doc["tags"] = [jb.pool_name]   # NUEVO: pool self-hosted -> tag
    if jb.variables: job_doc["variables"] = dict(jb.variables)
    if jb.services:  job_doc["services"] = list(jb.services)
    if jb.depends_on: job_doc["needs"] = _needs_value(jb.depends_on)   # NUEVO

    scripts, rules = [], []
    for step in jb.steps:                                  # sin cambios
        scripts.extend(l for l in step.script.split("\n") if l.strip())
        if step.condition:
            rules.append({"if": _translate_condition_to_gitlab(step.condition)})
    for t in jb.task_steps:                                # ← NUEVO: la línea que faltaba
        scripts.extend(_task_step_to_script_lines(t))

    job_doc["script"] = scripts if scripts else ["echo 'no-op'"]   # se conserva: GL011 lo caza
    if rules: job_doc["rules"] = rules
    if jb.artifacts: job_doc["artifacts"] = {"paths": list(jb.artifacts)}
    return job_doc

def _deployment_doc_gitlab(dp, stage_name) -> dict:
    """NUEVO — DeploymentJob -> job GitLab con environment y compuerta manual.
    `when: manual` SIEMPRE: un deployment de ADO tiene aprobación de environment;
    el equivalente honesto en GitLab es la compuerta manual (y si no, GL005)."""
    return {"stage": stage_name, "environment": dp.environment, "when": "manual",
            "script": [l for t in dp.steps for l in _task_step_to_script_lines(t)]
                      or ["echo 'no-op'"]}

def _spec_to_gitlab_doc(spec) -> dict:
    doc = {}
    # NUEVO: las 3 raíces de ADO producen un stage sintético "build" en vez de perderse.
    #   root_task_steps / root_steps -> un job "build"
    #   root_jobs                    -> un job por cada uno
    # ... (ver test_raices_no_se_pierden) ...
    doc["stages"] = [st.name for st in spec.stages] or ["build"]
    if spec.variables: doc["variables"] = dict(spec.variables)
    for st in spec.stages:
        for jb in st.jobs:        doc[jb.name] = _job_doc_gitlab(jb, st.name, spec)
        for dp in st.deployments: doc[dp.name] = _deployment_doc_gitlab(dp, st.name)  # NUEVO
    return doc
```

> **Se elimina el código muerto `if st.condition: pass` (`:304-306`)** y se sustituye por la
> traducción real a `rules` del job, o por nada si `_translate_condition_to_gitlab` no puede
> (que ya lanza `ValidationError`, `:257`).

**Tests PRIMERO** — `backend/tests/test_plan249_renderer_gitlab.py`:

| Test | Verifica |
|---|---|
| `test_k1_los_9_derivados_emiten_comandos` | Para los 9 goldens: el GitLab derivado tiene **≥1** línea de `script` que **no** es `echo 'no-op'`. **Es K1: 9/9** |
| `test_k2_los_51_task_steps_sobreviven` | **[v2, C1: la v1 decía 24, medido mal].** Suma de `TaskStep` del corpus **contando las cuatro ubicaciones** (`root_task_steps` 24 + `job.task_steps` 13 + `root_jobs[*].task_steps` 8 + `deployment.steps` 6) == suma de líneas de script atribuibles a tareas (traducidas **o** marcadas). **Es K2: 51/51.** El test **calcula** las dos sumas, no las hardcodea; el `51` va en un `assert` final de sanidad para que un cambio de corpus se vea |
| `test_deployment_con_step_crudo_no_revienta` | **[v2, C6]** Un `DeploymentJob(steps=(Step(script="echo hola"),))` construido a mano produce `script: ["echo hola"]`, **sin `AttributeError`**. Prueba que F3 no depende del accidente de `_parse_deployment` |
| `test_k3_los_3_deployments_emiten_environment` | Los 3 `deployment:` del corpus producen un job con `environment` **y** `when: manual`. **Es K3: 3/3** |
| `test_raices_no_se_pierden` | `agendaweb-ci` (7 tareas raíz), `nightly-build-online` (1 job raíz) y `ci-batch` (3 tareas raíz) emiten **≥1** job cada uno (hoy: 0) |
| `test_depends_on_se_emite_como_needs` | Un spec con `Job(depends_on=("A",))` emite `needs: [A]` |
| `test_pool_name_se_emite_como_tag` | `Job(pool_name="RSPacifico")` sin `runner_tags` ⇒ `tags: ["RSPacifico"]` |
| `test_tarea_sin_equivalente_se_marca_no_se_inventa` | `VSBuild@1` produce una línea que empieza con `UNTRANSLATABLE_TASK_MARKER`. **Nunca** un `msbuild ...` inventado |
| `test_translation_map_es_cerrado` | `set(TASK_TRANSLATION_MAP) == {"DotNetCoreCLI@2","PowerShell@2","CopyFiles@2"}`. Agregar una obliga a tocar el test (patrón `UNSUPPORTED_CONSTRUCTS`, `:24-27`) |
| `test_powershell_inline_no_se_traduce` | `PowerShell@2` con `script:` inline (sin `filePath`) ⇒ marcado, no traducido (coherente con `RS004`, `cicd_semantic_rules.py:318-333`) |
| `test_ado_intacto` | `to_ado_yaml` sobre los 9 goldens es **byte-idéntico** a antes de esta fase. **Es P6/P10** |
| `test_foto_del_defecto_actualizada` | El `test_foto_del_defecto_2026_07_26` de F0 fue **actualizado** y el corpus derivado **regenerado**: `regen_gitlab_derived_corpus.py` + `git diff` muestra los 9 archivos cambiados |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe scripts/regen_gitlab_derived_corpus.py     # regenerar nivel A
.venv\Scripts\python.exe -m pytest tests/test_plan249_renderer_gitlab.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan249_corpus_gitlab.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_renderer_ado.py -q
```

**Criterio BINARIO:** `test_plan249_renderer_gitlab.py` **13 passed**;
`test_plan73_round_trip.py` y `test_plan243_renderer_ado.py` **verdes sin editarlos**; los 9
archivos de `fixtures/cicd_gitlab/derived/` aparecen modificados en `git status`;
**[ADICIÓN ARQUITECTO]** `test_ley_de_severidad_sobre_nivel_A` (F2) pasa de `xfail` a **passed**
tras quitarle el marcador — el criterio que prueba que el renderer mejoró **bien**, no sólo que
cambió. Correr `pytest tests/test_plan249_reglas_gitlab.py -q` al cerrar F3: **16 passed**.
**Flag:** ninguna. **Decisión explícita y su motivo:** la salida de hoy no ejecuta nada (§2.2), así
que **no hay comportamiento útil que preservar** detrás de una flag. Una flag acá sólo permitiría
volver a un artefacto roto. **No degrada** porque nada consume esa salida sin revisión humana: el
preview la muestra y el commit es HITL (`CommitPipelineModal.tsx`).
**Impacto por runtime:** idéntico en los 3. Funciones puras. **No hay fallback que definir.**
`Trabajo del operador: ninguno`

---

### F4 — El parser deja de corromper, y el round-trip se cierra sobre un subset enumerado

**Objetivo (1 frase):** que `parse_gitlab_yaml` respete los jobs ocultos y que `scan_unsupported`
deje de mentir sobre GitLab — con un round-trip cuyo alcance está **enumerado**, no prometido.
**Valor:** K5, K6. Es la fase que evita repetir el error C14 del 243.

**Archivo a editar:** `Stacky Agents/backend/services/pipeline_renderers.py`
**Archivo de test a crear:** `Stacky Agents/backend/tests/test_plan249_parser_gitlab.py`

**Nombres exactos nuevos:** `GITLAB_UNSUPPORTED_CONSTRUCTS`, `GITLAB_ROUNDTRIP_SUBSET`,
`_ADO_UNSUPPORTED_CONSTRUCTS` (renombre interno de la tupla actual `:28`, **conservando
`UNSUPPORTED_CONSTRUCTS` como alias** para no romper a nadie).

```python
# pipeline_renderers.py — EDITAR

# Alias de compatibilidad: `UNSUPPORTED_CONSTRUCTS` sigue existiendo y sigue siendo la
# lista ADO. Nada que la importe hoy cambia (P6).
_ADO_UNSUPPORTED_CONSTRUCTS = UNSUPPORTED_CONSTRUCTS   # (:28) matrix, compile_time_expression, ...

# Allowlist CERRADA de GitLab. Mismo contrato que la de ADO: declarar lo que NO se modela
# en vez de prometer un round-trip universal (C14 del 243).
GITLAB_UNSUPPORTED_CONSTRUCTS: tuple = (
    "include",          # trae jobs de otro archivo: no se puede round-trippear sin leerlo
    "workflow",         # reglas a nivel pipeline, sin lugar en PipelineSpec
    "default",          # herencia implícita de job
    "parallel",         # incluye `parallel:matrix`, hermano del `matrix` de ADO
    "trigger",          # pipelines hijo
    "pages",            # job especial
    "cache",            # PipelineSpec no modela caché
    "before_script",    # no modelado
    "after_script",     # no modelado
    "secrets",          # no modelado — y no se toca por P9
    "id_tokens",        # no modelado
    "release",          # no modelado
)

# Subset EXACTO que sobrevive round-trip. Enumerado y versionado (P5).
# [v2, C15] Era una tupla plana con "variables" REPETIDO (raíz y job): len()==13 pero
# len(set())==12, y el test "exactamente 13 entradas" quedaba ambiguo según se comparara
# lista o conjunto. Pasa a dict por scope: sin duplicados y con el scope explícito.
GITLAB_ROUNDTRIP_SUBSET: dict = {
    "root": ("stages", "variables"),
    "job":  ("stage", "script", "image", "tags", "variables", "services",
             "artifacts.paths", "needs", "rules.if", "when", "environment"),
}
# 2 claves de raíz + 11 de job = 13 entradas, 12 keywords únicas ("variables" en los dos scopes).

def scan_unsupported(yaml_text: str, provider: str = "ado") -> tuple:
    """PURA. `provider` es kwarg con default: llamarla como hoy da el resultado de hoy (P6).

    Con provider="gitlab" se evalúa contra GITLAB_UNSUPPORTED_CONSTRUCTS y `extends`
    NO se marca: en GitLab es una keyword de primera clase (K6).
    """
```

**Fix de `parse_gitlab_yaml` (hoy `:527-581`):**

```python
def parse_gitlab_yaml(yaml_str: str) -> PipelineSpec:
    # ...
    # ANTES (:538-541):
    #   for key, val in doc.items():
    #       if key in ("stages", "variables"): continue
    #
    # AHORA — reusa el criterio YA PROBADO del catálogo (F1), que a su vez es el del
    # lint (pipeline_lint.py:154-162). El criterio vive UNA sola vez:
    from services.cicd_gitlab_catalog import job_dicts
    for key, val in job_dicts(doc).items():
        ...
    # Efecto: `.base` deja de convertirse en job real, deja de inventarse el stage ''
    # y deja de inyectarse `echo 'no-op'` en un template (K5).
    #
    # Además se recuperan al spec: `needs` -> Job.depends_on, `environment` -> se conserva
    # como DeploymentJob del stage cuando está presente.
```

**Tests PRIMERO** — `backend/tests/test_plan249_parser_gitlab.py`:

| Test | Verifica |
|---|---|
| `test_k5_job_oculto_no_se_promueve` | Sobre el YAML de §2.3: el spec parseado **no** contiene ningún job llamado `.base`, y `stages` **no** contiene `''`. **Es K5: 0** |
| `test_k6_extends_no_es_unsupported_en_gitlab` | `scan_unsupported(GL, provider="gitlab")` **no** contiene `"extends"`. **Es K6: 0** |
| `test_scan_unsupported_ado_sin_cambios` | `scan_unsupported(ado_yaml)` (sin kwarg) da **exactamente** lo de hoy sobre los 9 goldens. **Es P6** |
| `test_scan_unsupported_gitlab_declara_include` | Un GitLab con `include:` ⇒ `("include",)` |
| `test_needs_se_recupera_al_spec` | `needs: [a]` ⇒ `Job.depends_on == ("a",)` |
| `test_environment_se_recupera_al_spec` | Un job con `environment: staging` ⇒ aparece como `DeploymentJob(environment="staging")` en su stage |
| `test_roundtrip_idempotente_sobre_nivel_A` | Para los 9 derivados (nivel A **post-F3**): `to_gitlab_yaml(parse_gitlab_yaml(x)) == x`. **Conjunto finito y nombrado, no "9/9 pipelines reales"** |
| `test_roundtrip_idempotente_sobre_nivel_B` | Para los 11 `repro` de F2 que sólo usan keywords de `GITLAB_ROUNDTRIP_SUBSET`: idem. Los que usan keywords de fuera **se excluyen por lista explícita**, no por excepción |
| `test_subset_de_roundtrip_es_cerrado` | **[v2, C15]** `GITLAB_ROUNDTRIP_SUBSET == {"root": (...2...), "job": (...11...)}` **por igualdad de dict completo**, no por `len()`. Agregar una keyword obliga a tocar el test. Se afirma además `len(set(root) | set(job)) == 12` |
| `test_unsupported_gitlab_no_crece_en_silencio` | `len(GITLAB_UNSUPPORTED_CONSTRUCTS) == 12` y su contenido exacto (espeja `test_allowlist_no_crece_en_silencio` del 243 F2, `pipeline_renderers.py:25-27`) |

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan249_parser_gitlab.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_renderer_ado.py -q
```

**Criterio BINARIO:** `test_plan249_parser_gitlab.py` **10 passed**; `test_plan73_round_trip.py`
y `test_plan243_renderer_ado.py` **verdes sin editarlos**.
**Flag:** ninguna (corrección de defecto + kwarg aditivo; el comportamiento ADO es byte-idéntico y
está testeado).
**Impacto por runtime:** idéntico en los 3. Puro. **No hay fallback que definir.**
`Trabajo del operador: ninguno`

---

### F5 — Flag, wiring en el endpoint existente, y el modelo puro del frontend

**Objetivo (1 frase):** que las `GL*` lleguen al panel por la ruta que ya existe, gobernadas por
una flag editable desde la UI.
**Valor:** convierte 4 fases de módulos puros en una capacidad visible. Cierra K7.

**Archivos a editar/crear:**

| Ruta exacta | Acción |
|---|---|
| `Stacky Agents/backend/services/harness_flags.py` | Editar: `FlagSpec` + entrada en `_CATEGORY_KEYS["paridad_proveedores"]` (`:425`) |
| `Stacky Agents/backend/config.py` | Editar: `STACKY_GITLAB_SEMANTIC_RULES_ENABLED` junto al bloque del Plan 218 (`:1188-1204`) |
| `Stacky Agents/backend/tests/test_harness_flags.py` | Editar: agregar la clave a `_CURATED_DEFAULTS_ON` (`:467`) |
| `Stacky Agents/backend/api/devops.py` | Editar: `pipeline_lint_validate_route` (`:196`) |
| `Stacky Agents/frontend/src/components/devops/gitlabProfileModel.ts` | **Crear** — **[v2, C8] la v1 lo ponía en `src/devops/`, lejos del panel que lo consume** |
| `Stacky Agents/backend/tests/test_plan249_endpoint_gitlab.py` | **Crear** |
| `Stacky Agents/frontend/src/components/devops/gitlabProfileModel.test.ts` | **Crear** (colocado, como `pipelineLint.test.ts`) |
| `Stacky Agents/docs/sistema/error_fingerprints.json` | Editar: **[v2, C16]** huella de la clase de error que este plan mata |

**Flag (patrón exacto del dossier §3):**

```python
# services/harness_flags.py — dentro de FLAG_REGISTRY
FlagSpec(
    key="STACKY_GITLAB_SEMANTIC_RULES_ENABLED",
    type="bool",
    default=True,  # default ON (ninguna de las 4 excepciones duras aplica; curada en _CURATED_DEFAULTS_ON)
    label="Reglas semánticas de GitLab CI",
    description=(
        "Plan 249 - agrega los hallazgos GL000..GL011 (stage no declarado, needs a un stage "
        "posterior, only/except mezclado con rules, deploy a produccion sin compuerta manual) "
        "al validador de pipelines cuando el proveedor es GitLab. "
        "OFF: el endpoint devuelve exactamente las PL001..PL014 de hoy, byte-identico."
    ),
    group="global",
),
```

> **GOTCHA DURA 1 (dossier §3):** `default=True` **obliga** a agregar la clave a
> `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`) o
> `test_default_known_only_for_curated` rompe.
> **GOTCHA DURA 2:** el consumidor lee **la instancia** — `getattr(_config.config, "...", False)`.
> Un `getattr` del **módulo** devuelve el default y **mata el branch OFF** (el test flag-off
> pasaría en falso). El patrón correcto ya está en `backend/api/devops.py:199`.
> **Categorización obligatoria:** sin la entrada en `_CATEGORY_KEYS` (`:425`),
> `test_every_registry_flag_is_categorized` rompe a propósito.
> **Deliberado:** la flag **NO** declara `requires="STACKY_GITLAB_ENABLED"` — ver P7.

**Wiring (aditivo, en el endpoint que ya recibe `source`):**

**[v2, C3] La v1 era inimplementable acá.** Decía "DESPUÉS de la línea `:209`", pero `:209` es
un `return` — no se agrega nada después de un `return`, **se lo reemplaza**. Y usaba una variable
`kv_runner_tags` que no definía en ningún lado. Diff completo, antes y después:

```python
# backend/api/devops.py — pipeline_lint_validate_route (decorador :196, def :197)
#
# ANTES (líneas :206-209, tal cual están hoy):
#     kv = body.get("known_variables")
#     kv = [str(x) for x in kv] if isinstance(kv, list) else None
#     from services.pipeline_lint import lint_yaml
#     return jsonify(lint_yaml(yaml_str, source, known_variables=kv).to_dict())
#
# DESPUÉS (se REEMPLAZA la línea :209 por el bloque siguiente; :206-208 quedan intactas):
    from services.pipeline_lint import lint_yaml
    report = lint_yaml(yaml_str, source, known_variables=kv).to_dict()
    # ↓ [v2, C3] la variable que la v1 usaba sin definir. Misma forma que `kv` (:206-207).
    krt = body.get("known_runner_tags")
    krt = [str(x) for x in krt] if isinstance(krt, list) else None   # None ⇒ GL007 no se evalúa
    if source == "gitlab" and getattr(
            _config.config, "STACKY_GITLAB_SEMANTIC_RULES_ENABLED", False):
        from services.cicd_semantic_rules import (
            check_semantics, PROVIDER_GITLAB, MODE_AUDIT)
        report["semantic_findings"] = [
            asdict(f) for f in check_semantics(
                yaml_str, profile="", provider=PROVIDER_GITLAB, mode=MODE_AUDIT,
                known_runner_tags=krt,
            )
        ]
    return jsonify(report)
```

> **`asdict` ya está importado** en `api/devops.py` (se usa en `:193`). No hace falta agregarlo.
>
> **[v2, C3] PREREQUISITO DE TODOS LOS TESTS DE F5:** la ruta empieza con
> `if not getattr(_config.config, "STACKY_DEVOPS_PIPELINE_LINT_ENABLED", False): abort(404)`
> (`:199`). Su default es `"true"` (`backend/config.py:1577-1578`), pero un test que no la
> asegure ON recibe **404** y falla por una razón ajena a este plan. Cada test de F5 debe
> setear **las dos** flags explícitamente sobre `config.config`.
>
> **Clave aditiva, nunca sustitutiva:** `semantic_findings` es una **clave nueva**. Los **seis**
> campos de `LintReport` (`pipeline_lint.py:42-52`) —`ok`, `findings`, `counts`,
> `engine_version`, `duration_ms` y **`fixes_omitted`** **[v2, C13: la v1 enumeraba sólo cinco]**—
> **no cambian**. Un frontend viejo ignora la clave nueva y funciona igual (P6/P10).
> **`MODE_AUDIT`** porque el endpoint valida YAML que el operador trae, no que Stacky generó.

**Modelo puro del frontend** — `frontend/src/components/devops/gitlabProfileModel.ts`

**[v2, C8] La v1 violaba el principio de reuso.** Creaba `groupBySeverity`, `summarize` y
`hasBlocking` en `src/devops/`, cuando `src/components/devops/pipelineLint.ts` **ya exporta**
`groupFindings(findings): GroupedFindings` (`:62`) y `commitLintSummary(report)` (`:157`), y
`PipelineLintPanel.tsx` —el panel que va a consumir esto— vive en esa misma carpeta. Tres
funciones duplicadas en otro directorio. v2 conserva **sólo lo que no existe**:

```ts
// frontend/src/components/devops/gitlabProfileModel.ts — NUEVO
import { groupFindings, type LintFinding, type GroupedFindings } from './pipelineLint';

/** Un SemanticFinding del backend (cicd_semantic_rules.SemanticFinding, 5 campos). */
export type GitlabSemanticFinding = {
  code: string; severity: 'error' | 'warning'; message: string;
  location: string; evidence: string;
};

/** GL000..GL011 -> título corto en español. Es lo ÚNICO genuinamente nuevo de este módulo. */
export const GL_RULE_TITLES: Readonly<Record<string, string>>;

/** Adapta un SemanticFinding a la forma LintFinding que el panel YA sabe renderizar,
 *  para no duplicar el renderizador ni la agrupación. `location` -> `node`. */
export function toLintFinding(f: GitlabSemanticFinding): LintFinding;

/** Agrupa REUSANDO groupFindings de pipelineLint.ts (:62). No reimplementa nada. */
export function groupSemantic(fs: GitlabSemanticFinding[]): GroupedFindings;
```

**Sin componente nuevo** (dossier §3: *"reusa `PipelineLintPanel.tsx`"*). El montaje del panel
mapea con `toLintFinding` y renderiza en la lista que ya existe.

**Tests PRIMERO:**

`backend/tests/test_plan249_endpoint_gitlab.py`:

| Test | Verifica |
|---|---|
> **[v2, C3] Los 5 tests comparten una fixture obligatoria** que setea sobre `config.config`
> (**la instancia**, no el módulo) **las dos** flags: `STACKY_DEVOPS_PIPELINE_LINT_ENABLED = True`
> (sin ella la ruta devuelve **404**, `:199`) y la de este plan según el caso.

| Test | Verifica |
|---|---|
| `test_flag_on_agrega_semantic_findings` | `POST /api/devops/pipeline-lint/validate` con `source="gitlab"` y el YAML de §2.3 ⇒ `semantic_findings` con `GL001`, `GL002`, `GL005`. **Corre con `STACKY_GITLAB_ENABLED` en su default OFF y debe pasar igual** (R6) |
| `test_flag_off_respuesta_identica` | Con la flag OFF, la respuesta **no tiene** la clave `semantic_findings` y el resto es **byte-idéntico** al de hoy. **Es P10** |
| `test_source_ado_no_cambia` | `source="ado"` ⇒ nunca hay `semantic_findings`, con la flag ON o OFF |
| `test_flag_se_lee_de_la_instancia` | Parcheando `config.config` (no el módulo) el branch OFF **se ejecuta de verdad**. **Es la GOTCHA DURA 2** |
| `test_known_runner_tags_opcional` | Sin `known_runner_tags` en el body ⇒ cero `GL007`; con `["docker"]` y un job `tags: [windows]` ⇒ uno |
| `test_404_si_el_lint_esta_apagado` | **[v2, C3]** Con `STACKY_DEVOPS_PIPELINE_LINT_ENABLED=False` la ruta devuelve **404** aunque la flag de este plan esté ON. Documenta el gate preexistente para que nadie lo confunda con una regresión |

`frontend/src/components/devops/gitlabProfileModel.test.ts`:

| Test | Verifica |
|---|---|
| `GL_RULE_TITLES cubre GL000..GL011` | Las **12** claves presentes, ninguna vacía. **Es K7 del lado UI** — **[v2, C10] incluye `GL000`**, que la v1 no tenía y que el backend puede emitir |
| `toLintFinding mapea location a node` | Un `GitlabSemanticFinding` produce un `LintFinding` con `node === location` y misma `severity`/`message` |
| `groupSemantic delega en groupFindings` | 2 error + 1 warning ⇒ el mismo agrupado que `groupFindings` sobre los `LintFinding` equivalentes. **[v2, C8]** prueba el reuso, no una reimplementación |
| `codigo desconocido no rompe el titulo` | `GL_RULE_TITLES["GL999"]` es `undefined` y el mapeo no lanza |

**Huella de regresión [v2, C16]** — agregar en `Stacky Agents/docs/sistema/error_fingerprints.json`:
`id` `GITLAB-EMPTY-PIPELINE`, patrón `script: ["echo 'no-op'"]` como **único** cuerpo del
pipeline emitido, `plan` `249`, `fecha` `2026-07-26`, `guard_test`
`tests/test_plan249_reglas_gitlab.py::test_gl011_detecta_el_derivado_vacio`.

**Comando:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan249_endpoint_gitlab.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q

cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/components/devops/gitlabProfileModel.test.ts
npx tsc --noEmit
```

**Criterio BINARIO:** `test_plan249_endpoint_gitlab.py` **6 passed**;
`gitlabProfileModel.test.ts` **4 passed**; `npx tsc --noEmit` **sin errores**;
`test_harness_flags.py` verde **para la entrada nueva** (recordar los 4 fallos ajenos
preexistentes de `test_harness_flags_help`: **no son de este plan**); ratchet verde con
`tests/test_plan249_endpoint_gitlab.py` en las **dos** listas.
**Flag:** `STACKY_GITLAB_SEMANTIC_RULES_ENABLED`, **default ON**, categoría
`paridad_proveedores`, editable desde el panel de flags.
**Impacto por runtime:** idéntico en los 3. El endpoint Flask es el mismo para Codex CLI,
Claude Code CLI y GitHub Copilot Pro; ninguno tiene ruta propia hacia el lint. **No hay fallback
que definir.**
`Trabajo del operador: opt-in, default ON` (aparece solo; apagarlo es un click).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (dentro del plan) |
|---|---|---|---|
| R1 | **Las `GL*` se basan en semántica documentada, no en una corrida real contra GitLab** (§2.6) | Media | Ninguna `GL*` bloquea por sí sola: **reporta**. `GL002` marca sólo el caso inequívoco (nunca el mismo stage). `GL007` **no se evalúa** sin inventario. `GL006` **se omite entera** si hay `include`. En los tres casos la elección es *callar antes que afirmar de más* |
| R2 | **El traductor de tareas ADO→GitLab inventa comandos** que no funcionan | Media | `TASK_TRANSLATION_MAP` es **cerrado a 3 entradas** con test que lo fija. Las otras 7 tareas se emiten con `UNTRANSLATABLE_TASK_MARKER`, **nunca** con un comando adivinado. Un `VSBuild@1` no tiene equivalente honesto en un runner GitLab y el plan lo dice en vez de fingirlo |
| R3 | **El corpus nivel A es sintético y podría dar falsa confianza** | Media | Está **declarado** como derivado en `PROCEDENCIA.md` y en el header de los 9 archivos. Su valor no es "representa a GitLab" sino "es exactamente lo que Stacky emite hoy", que es lo que las reglas deben juzgar. El nivel C se declara **ausente** y el espejo **calla** |
| R4 | **F3 rompe a propósito un test de F0** y alguien lo interpreta como regresión | Alta | `test_foto_del_defecto_2026_07_26` lleva la fecha en el nombre y su docstring dice literalmente que **F3 debe romperlo**. F3 tiene un test dedicado (`test_foto_del_defecto_actualizada`) que exige la regeneración |
| R5 | **Solape silencioso con las `PL*`**: dos hallazgos para el mismo defecto | Media | `test_no_solapa_con_pl` (F2) lo verifica sobre los repros. La frontera está escrita en P2 y en §2.3 con anclaje por símbolo |
| R6 | **La flag queda muerta** por atarse a `STACKY_GITLAB_ENABLED` (OFF por default) — la gotcha que mató el 218 F0 | Baja | Decidido y justificado en P7: la flag **no** declara `requires`. Analizar texto YAML no necesita instancia GitLab. `test_flag_on_agrega_semantic_findings` corre con `STACKY_GITLAB_ENABLED` en su default OFF y **debe pasar igual** |
| R7 | **Cambiar `check_semantics` rompe los tests del 243** | Media | `provider` es kwarg con default `PROVIDER_ADO`. `test_ado_sigue_identico_sin_provider` (F2) y la exigencia de que `test_plan243_reglas_semanticas.py` quede **verde sin editarlo** son criterio de aceptación binario de F2 |
| R8 | **Colisión de archivos con planes hermanos de la serie** | Baja | Los únicos archivos compartidos son `cicd_semantic_rules.py` (**dueño: 249**, confirmado por `docs/246…:96`: *"único plan que lo edita"*; el 248 crea `cicd_security_rules.py` aparte) y `pipeline_renderers.py` (**dueño: 249** en esta serie). El 250 crea `pipeline_patcher.py` y declara explícitamente (`docs/250…:250`) que no toca ninguno de los dos. **Verificado además:** el test `test_construcciones_no_modeladas_no_desaparecen` del 250 (`docs/250…:355`) compara `scan_unsupported(after) == scan_unsupported(before)` — sobrevive a F4 **porque `provider` es kwarg con default `"ado"`** y el comportamiento ADO queda byte-idéntico |
| **R9** | **[v2, C1] Un KPI mal medido se convierte en un test que nace rojo y alguien lo "ajusta" en silencio**, destruyendo el criterio binario. Le pasó a la v1 con `K2=24` (el real es 51) | **Alta** | K2 se rebautizó con el número correcto **y** el test `test_k2_los_51_task_steps_sobreviven` **calcula las dos sumas en vez de hardcodearlas**, dejando el `51` sólo como `assert` de sanidad. Si el corpus cambia, el test dice *qué* cambió en vez de exigir un número mágico. **Regla para el implementador: si un KPI de este plan no da, la hipótesis por defecto es que el número del plan está mal — verificalo ejecutando antes de tocar el código** |
| **R10** | **[ADICIÓN ARQUITECTO] Una `GL*` demasiado ansiosa inunda el panel de falsos positivos** y sin corpus real nadie lo nota hasta que lo ve el operador | Media | P11: **contra-repro obligatorio por regla** (K8) + **ley de severidad sobre el nivel A** (K9). Las dos son deterministas, sin costo para el operador y rompen el test si alguien agrega una regla sin su mitad negativa |

---

## 6. Fuera de scope (nombrando explícitamente los planes de la serie)

- **Descubrir pipelines** (inventario multiproveedor, estado de última corrida, listado en el
  panel) → **Plan 246**. Este plan **no** enumera pipelines; recibe texto YAML.
- **Perfilar** (stack tecnológico, anatomía build/test/deploy, propósito en una línea) →
  **Plan 247**. El catálogo de F1 es de **constructos del lenguaje GitLab CI**, no de stacks.
- **Reglas de seguridad y eficiencia `SEC*` / `OPT*`** (secretos en claro, imagen sin pin,
  `allow_failure` que enmascara, artefacto público, cache ausente, jobs serializados) →
  **Plan 248**, que las define sobre **ambos** proveedores. Este plan define únicamente las `GL*`
  de **corrección semántica**. Frontera concreta: `allow_failure` está en el catálogo de F1 como
  **dato**, y ninguna `GL*` lo juzga.
- **Editar u optimizar pipelines existentes por lenguaje natural** (patch quirúrgico + diff) →
  **Plan 250**. Ninguna `GL*` autofixea.
- **Matriz de entornos** (valores por entorno, formulario, caja fuerte del Plan 94) →
  **Plan 251**. `GL005` **detecta** un `environment` sin compuerta; **no** resuelve sus valores.
- **Paquete de entrega y frontera de capacidades** (zip + README operativo) → **Plan 252**.
- **La entrada en lenguaje natural y el pipeline NL→`IntentSpec`→`PipelineSpecDraft`** →
  **Planes 243 / 244**. Este plan **no escribe NL** y **no llama a ningún LLM**.
- **El catálogo ADO** (`cicd_task_catalog.py`) → **Plan 243**. Acá sólo se **lee** (F3 lo consulta
  para traducir 3 tareas).
- **La doctrina de paridad multiproveedor** (`CAPABILITY_KEYS`, `CapabilityUnavailable`,
  `TrackerTarget`, vocabulario canónico) → **Plan 218**, cuyos contratos están **congelados**
  (`docs/218…:140-153`). Este plan **construye encima y no los toca**: no agrega una clave de
  capacidad ni cambia una firma del puerto.

---

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado en este plan |
|---|---|
| **`GL000..GL011`** | Reglas semánticas de **corrección** de GitLab CI. Viven en `cicd_semantic_rules.py`. Hermanas de las `RS001..RS009` de ADO |
| **`PL001..PL014`** | Reglas **estructurales** existentes (`pipeline_lint.py`, Plan 186). Ya multiproveedor. **Las `GL*` no las repiten** |
| **`MODE_AUDIT`** | Se juzga un YAML que **ya existe y anda**. Sólo verdades del dominio |
| **`MODE_NL_STRICT`** | Se juzga un YAML que **Stacky acaba de generar**. Se puede exigir más |
| **Nivel A / B / C** | Los tres niveles de corpus GitLab de §2.5: derivado-regenerable / repro-por-regla / real-ausente |
| **Job oculto** | Clave top-level que empieza con `.` (ej. `.base`). GitLab **nunca** la ejecuta; es un template para `extends` |
| **`.pre` / `.post`** | Stages implícitos de GitLab: existen **sin** declararse en `stages:` |

### 7.2 Orden de implementación (estricto, por dependencia)

```
F0  corpus 3 niveles + guardia regenerable      (nada depende de nada)
 └─ F1  cicd_gitlab_catalog.py                   (usa el nivel A para probar job_dicts)
     └─ F2  GL000..GL011                         (usa el catálogo de F1 y el nivel A/B)
         └─ F3  renderer                         (GL011 de F2 valida el resultado; regenera nivel A)
             └─ F4  parser + scan_unsupported    (round-trip sobre el nivel A YA arreglado)
                 └─ F5  flag + endpoint + modelo UI
```

**F3 no puede ir antes que F2:** `GL011` es el test de verdad de que el renderer dejó de emitir
vacío. **F4 no puede ir antes que F3:** el round-trip del nivel A sobre artefactos vacíos sería
verde y no probaría nada.

### 7.3 Definición de Hecho — binaria

| # | Criterio | Comando que lo verifica |
|---|---|---|
| 1 | Los **6** archivos de test nuevos pasan, **cada uno en su propia corrida** (la suite completa se contamina) — **[v2, C14] la v1 escribía un glob, que es exactamente la corrida conjunta prohibida** | `pytest tests/test_plan249_corpus_gitlab.py -q` · `…_gitlab_catalog.py` · `…_reglas_gitlab.py` · `…_renderer_gitlab.py` · `…_parser_gitlab.py` · `…_endpoint_gitlab.py` (6 comandos separados) |
| 2 | Los 6 `test_plan249_*.py` están en **las dos** listas del ratchet, cada una **con su sintaxis** (§4) | `pytest tests/test_harness_ratchet_meta.py -q` |
| 3 | **Cero regresión** en el motor de pipelines, **sin editar** esos tests | `pytest tests/test_plan73_round_trip.py -q`; `tests/test_plan243_renderer_ado.py`; `tests/test_plan243_reglas_semanticas.py`; `tests/test_plan186_lint_catalogo.py` |
| 4 | La flag existe, es ON, está curada y categorizada | `pytest tests/test_harness_flags.py -q` (ignorando los 4 fallos ajenos de `test_harness_flags_help`) |
| 5 | **K1** = 9/9 · **K2** = **51/51** · **K3** = 3/3 | `pytest tests/test_plan249_renderer_gitlab.py -q` |
| 6 | **K4** = 3/3 · **K7** = **12/12** · **K8** = **12/12** · **K9** = **0** | `pytest tests/test_plan249_reglas_gitlab.py -q` |
| 7 | **K5** = 0 · **K6** = 0 | `pytest tests/test_plan249_parser_gitlab.py -q` |
| 8 | Flag OFF ⇒ respuesta del endpoint **byte-idéntica** a la de hoy | `pytest tests/test_plan249_endpoint_gitlab.py -q` (`test_flag_off_respuesta_identica`) |
| 9 | El frontend compila y el modelo puro pasa | `npx tsc --noEmit`; `npx vitest run src/components/devops/gitlabProfileModel.test.ts` |
| 10 | El corpus derivado es **idempotente** | Correr `regen_gitlab_derived_corpus.py` dos veces ⇒ `git status` limpio en `fixtures/cicd_gitlab/` |
| 11a | **Cero LLM, cero red, cero disco** en el módulo **nuevo** | `grep -nE "requests\|urllib\|call_llm\|open\(" services/cicd_gitlab_catalog.py` ⇒ **0 hits** |
| 11b | Idem para el bloque GitLab de `cicd_semantic_rules.py`, **probado por importación en vez de por grep** | `pytest tests/test_plan249_reglas_gitlab.py -q -k pureza`: el test parchea `builtins.open`, `urllib.request.urlopen` y `requests` para que lancen, y corre `check_semantics(..., provider="gitlab")` sobre los 12 repros ⇒ **ninguna excepción** |
| 12 | **[v2, C11]** Independencia real del 246: ningún archivo de **código** del plan importa el inventario | `grep -rn "pipeline_inventory" services/cicd_gitlab_catalog.py services/cicd_semantic_rules.py services/pipeline_renderers.py api/devops.py` ⇒ **0 hits en los cuatro**. **El gate NO incluye `docs/249_*.md`: la prosa que lo documenta nombra el término y lo haría fallar siempre — el mismo error que la v1 cometió en DoD #11 (C4)** |

> **[v2, C4] Por qué el criterio 11 se partió en dos.** La v1 pedía
> `grep "…open(" services/cicd_semantic_rules.py ⇒ 0 hits` **sobre el bloque GitLab**. Dos
> problemas fatales: (a) un `grep` sobre un archivo **no se puede acotar a un bloque**, y (b) ese
> archivo **ya tiene un `open(` hoy** — `cicd_semantic_rules.py:418`, dentro de `_rs007`. El
> criterio era **falso por construcción y para siempre**: el plan nunca se habría podido declarar
> hecho. Se reemplazó por un grep que sí puede dar 0 (el módulo nuevo, que es 100% de este plan) y
> por un test de pureza real, que además prueba más: no que el texto no diga `open`, sino que el
> código **no abra nada**.

### 7.4 Regla de anclajes (para quien implemente y para quien critique)

1. **Todo anclaje lleva el símbolo, no sólo el número:** `pipeline_renderers.py:321 (for step in jb.steps)`.
2. **El número es una pista, no un contrato.** Si la línea no coincide, greppeá el símbolo.
2-bis. **[v2, C12] Convención del decorador, ahora DECLARADA.** Cuando el símbolo tiene decorador
   (`@dataclass(frozen=True)`, `@_rule(...)`, `@bp.post(...)`), el anclaje apunta a la **primera
   línea del decorador**, no a la del `def`/`class`. Por eso `SemanticFinding` es `:62` aunque el
   `class` esté en `:63`, y `_rule_pl004` es `:390` aunque el `def` esté en `:392` (su decorador
   ocupa 390-391). La v1 usaba esta convención **sin declararla**, lo que hacía que 13 anclajes
   correctos parecieran desfasados en una auditoría automática. Auditoría independiente del
   2026-07-26 sobre 78 anclajes: **77 correctos, 1 falso** (`_PROD_MARKERS` decía `:56`, el real
   es `:55` — corregido en v2).
3. **Prohibido concluir "no existe" porque la línea no coincide**, y prohibido reimplementar algo
   que ya está. Si el símbolo no aparece con `grep`, **frená y reportalo**.
4. **No escribas un anclaje que no hayas abierto.** Lo no verificado va a §2.6.

Un plan de esta casa fue **RECHAZADO por 4 anclajes desfasados 77 líneas**. Los anclajes de este
documento se verificaron abriendo cada archivo el **2026-07-26**; las mediciones de §2.2, §2.3 y
§2.4 se obtuvieron **ejecutando el código real** con `backend/.venv/Scripts/python.exe`, no
leyéndolo.
