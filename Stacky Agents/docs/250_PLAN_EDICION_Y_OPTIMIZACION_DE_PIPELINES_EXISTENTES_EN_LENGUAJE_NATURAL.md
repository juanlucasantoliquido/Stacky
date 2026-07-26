# Plan 250 — Editar y optimizar una pipeline que ya existe, describiendo el cambio en lenguaje natural

> ## ESTADO REAL AL 2026-07-26: **IMPLEMENTADO — F0..F5 COMPLETAS**
>
> Implementado y commiteado en `feat/plan-217-migrador-mantis-gitlab`. **Backend 70 tests verdes
> corridos por archivo con `backend/.venv` (py3.13.5); frontend 12 verdes + `npx tsc --noEmit`
> en 0 errores.**
>
> | Fase | Estado | Archivo de test | Resultado real |
> |---|---|---|---|
> | F0 motor de anclajes y splice | IMPLEMENTADA | `test_plan250_patcher.py` | **14 passed** |
> | F1 verbos cerrados | IMPLEMENTADA | `test_plan250_verbos.py` | **11 passed** |
> | F2 gates por delta + sello | IMPLEMENTADA | `test_plan250_gates_delta.py` | **12 passed** |
> | F3 blueprint + 2 flags | IMPLEMENTADA | `test_plan250_api.py` (**14**) + `test_plan250_flag.py` (**7**) | **21 passed** |
> | F4 panel + diff | IMPLEMENTADA | `pipelineEditModel.test.ts` | **12 passed**, `tsc` 0 errores |
> | F5 puerta NL + puente 248 | IMPLEMENTADA | `test_plan250_edit_intent.py` | **12 passed** |
>
> **KPI-1 verificado sobre los 9 goldens: 337/337 comentarios sobreviven** (el round-trip los
> deja en 0). KPI-2, KPI-3, KPI-4, KPI-5, KPI-6 y KPI-7 verdes con sus tests nombrados.
>
> ### Los 5 bugs del PROPIO PLAN que sólo aparecieron al construirlo
>
> Los 4 planes anteriores de la serie tuvieron cada uno una contradicción interna; este tuvo
> cinco. Anclaje verificado ≠ plan implementable.
>
> 1. **§2.4 — `key_col` de una SECUENCIA.** El plan dice que `yaml.compose` da
>    `item.start_mark.column` = columna de la primera clave. Es cierto para el **item**, pero para
>    el nodo **secuencia** (`steps`) `start_mark.column` es la columna del **guion** (4, no 6).
>    Tomarlo de ahí emite el bloque nuevo con las claves de continuación 2 columnas a la izquierda
>    y produce un YAML **inválido** — que `scan_unsupported` devuelve como `()` en vez de fallar
>    ruidosamente, así que el test 6 mentía sin decir por qué. Corregido: `_first_child_col`
>    recursa al primer item. Además, `dash_col` NO se calcula como `start_mark.column - 2` (falla
>    con `-   task:`): se deriva del texto crudo que precede a la primera clave, que es lo que dice
>    el propio encabezado de mediciones.
> 2. **§2.3 deja comentarios huérfanos al BORRAR.** La fórmula de fin efectivo le saca al item N
>    el comentario que introduce a N+1 — pero el `start_mark` de N+1 tampoco lo incluye, así que
>    ese comentario **no pertenece a nadie**. Al borrar `PublishTestResults@2` quedaba
>    `# 4. Publicar resultados de tests en ADO` colgado sobre el paso equivocado: corrupción
>    silenciosa. Corregido con `Anchor.lead_line` (el bloque de comentarios/blancos que INTRODUCE
>    al nodo, acotado por el fin efectivo del hermano anterior); `delete`, `insert_before` y
>    `move_step` lo usan. Consecuencia medida: el plan decía "47 menos los **2** propios de ese
>    paso"; el bloque de ese paso no tiene **ningún** comentario adentro y el único suyo es el que
>    lo presenta ⇒ **47 → 46**, no 45.
> 3. **F1 — `validate_inputs` hace `set_task_input` imposible.** El plan manda
>    `validate_inputs(profile, task_ref, inputs) != [] ⇒ error`, pero ese validador exige los
>    inputs **requeridos**: cambiar sólo `configuration` en `VSBuild@1` daba siempre "falta el
>    input requerido 'solution'". Las dos cosas del plan (esa validación y
>    `test_set_task_input_cambia_una_sola_linea`) no pueden ser ciertas a la vez. Corregido:
>    `plan_edit` valida el resultado **efectivo** (los inputs que el paso YA tiene + el nuevo), que
>    además es más estricto; `validate_intent_dict` valida sólo las claves recibidas.
> 4. **F3 — `default=False` en la `FlagSpec` rompe el meta-test.** El plan escribe
>    `default=False` para la flag de commit. Declarar cualquier default la vuelve
>    `default_is_known`, y `test_default_known_only_for_curated` exige que ese conjunto sea
>    EXACTAMENTE `_CURATED_DEFAULTS_ON` — a la que la flag no puede entrar por ser OFF. Corregido:
>    la `FlagSpec` **no declara** `default=`; el default OFF vive en `config.py`.
>    **Además el plan v2 afirma que `_REQUIRES_MAP_FROZEN` no existe en este árbol: SÍ existe**
>    (`tests/test_harness_flags_requires.py:120`) y la arista hubo que agregarla.
> 5. **F5 — `LLMCallSpec(prompt=...)` es un `TypeError`** (el mismo bug de clase que encontró el
>    247). El dataclass real (`pm_llm_client.py:90`) exige `project`, `agent_kind`, `prompt_type`,
>    `model`, `system` y `user`. Y el resultado se lee por `.parsed_json`/`.text`, no `.data`.
>    **También: el puente con el 248 importa `get_recommendation`, que no existe** — el símbolo
>    real es `check_recommendations(yaml_text, *, provider, mode)`
>    (`services/pipeline_recommendations.py:238`). Cableado al símbolo real: si se hubiera dejado
>    el import del plan, el `except ImportError` habría hecho que el puente degradara **siempre**,
>    inerte y en silencio, con el 248 instalado.
>
> ### Los 3 peligros del plan, verificados en el código construido
>
> - **¿Escribe en el ADO real?** Sí, `/commit` termina en `ado_provider.commit_file` (push real).
>   Por eso está detrás de **8 candados en serie**: flag propia default **OFF** → `confirm=True` →
>   `branch` no vacío y **distinto de la rama por defecto** (y si no se puede resolver cuál es,
>   **400**, no se escribe) → sha256 del `before` → **recompilación en el servidor** (el YAML del
>   cliente se ignora) → `approved_after_sha256` (409) → los 4 gates (422) → `get_repo_writer` en
>   su propio `try` (400, no 500). `test_default_de_fabrica_no_escribe` prueba que el default del
>   **código** (no el del test) es OFF, y cada test de candado afirma `writer.llamadas == []`.
> - **¿`stale_check`?** Siempre `"no_verificable"`, con el motivo literal. **Nunca** se afirma
>   haber validado contra el repo.
> - **Falla CERRADO:** ante `after` que no parsea, gate roto, provider sin puerto o preservación en
>   rojo, la respuesta es un error y **no** un commit.
>
> ### Lo que queda pendiente (declarado, no maquillado)
>
> - **Smoke visual del operador** (no automatizable: no hay `jsdom` ni `@testing-library/react`):
>   pegar una pipeline real, ver el diff y el sello, **encender la flag de commit desde la UI** y
>   confirmar. Ese paso es parte del smoke a propósito: prueba que el default de fábrica no escribía.
> - **§7.5 huella de regresión** (`docs/sistema/error_fingerprints.json`): NO se escribió — ese
>   archivo está fuera de la frontera §3.1 de este plan. El guard vive igual, doble: el test
>   `test_los_337_comentarios_del_corpus_sobreviven` (corpus dorado) + el gate en vivo
>   `G-PRESERVACION` de `services/pipeline_diff.py` (los pipelines del operador).
> - **Ratchets rojos AJENOS** (no crecidos por este plan, verificado archivo por archivo):
>   `formDebtRatchet` (7 ofensores: EnvSetupWizard, EnvironmentRadar, PipelineAuditPanel,
>   PipelineInventorySection, DensityToggle, PlansBoardPage, TicketBoard) y `devopsPollingRatchet`
>   (BuildWorkshopSection.tsx:93). `PipelineEditNlPanel.tsx` **no figura en ninguno**: usa las
>   primitivas `Input/Select/Textarea/Checkbox` y no tiene ni un `style={{...}}` inline.
>
> ---
>
> Implementados y commiteados en esta misma rama, en orden: **246** (`f2e63e77`), **247**
> (`d006e406`), **248** (`ed9a1942`), **249** (`7fc345d8`). Los cuatro tienen su estado real
> escrito en su propio encabezado, con los números de tests y los bugs de plan que aparecieron.
>
> ### Mediciones de F0 ya verificadas EJECUTANDO el código (2026-07-26) — no las re-derives
>
> Corridas contra el árbol real con `backend/.venv/Scripts/python.exe`; los cuatro números del
> plan dieron **exacto**, así que F0 puede arrancar confiando en ellos:
>
> | Dato | Valor medido | Dónde |
> |---|---|---|
> | Comentarios totales del corpus dorado | **337** | 81+44+31+36+47+57+18+11+12 |
> | Comentarios de `ci-cd-online.yml` | **47** | test 3 y test 5 de F0 |
> | `stages[0].jobs[0].steps` de `ci-cd-online.yml` | `start_mark.line=70`, **6 items** | test 1 |
> | `key_col` de sus hijos | **6** | `steps.value[0].value[0][0].start_mark.column` |
> | `dash_col` | **4** | **NO sale de `start_mark.column` (que da 6): sale de buscar el `-` en la línea cruda.** `L[70].find("-") == 4`. Es la regla §2.4 "columnas derivadas del archivo", y si se toma del `start_mark` el test 1 falla |
> | Item `steps[3]` | `start_mark.line=100`, `end_mark.line=112`, **fin efectivo 109** | test 2. Las líneas 110 y 111 son la vacía y `'    # 4. Publicar resultados de tests en ADO'`, que pertenecen al item SIGUIENTE |
> | `dash_col` del deployment de `cd-deploy-test.yml` | **16** | línea 129 (`- checkout: self`), test 7 |
> | `scan_unsupported` | `('matrix',)` en `ci-batch.yml`, `('compile_time_expression',)` en `bootstrap-server-environment.yml`, `()` en `ci-cd-online.yml` | test 6 |
>
> **Cambio del árbol que este plan todavía no contempla:** el **249** ya mergeó y le agregó a
> `scan_unsupported` un kwarg `provider="ado"` (`services/pipeline_renderers.py`). El test 6 de F0
> (`scan_unsupported(after) == scan_unsupported(before)`) **sigue valiendo sin tocarlo**, porque el
> default conserva el comportamiento ADO byte-idéntico — pero conviene saberlo antes de leer ese
> archivo y encontrarlo distinto de como lo describe §2.

---

> Estado: **v2 · CRITICADO** (2026-07-26). Pipeline: proponer ✓ → **criticar ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor v1: Claude Opus 5 (1M context). Crítica v1→v2: juez **independiente** (no escribió el v1), veredicto **RECHAZADO** con 4 bloqueantes, corregidos abajo.
> Serie: **"Mago de las Pipelines"** (246–252). Este es el **250**. Contrato compartido: dossier de la serie §1.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro — **paridad obligatoria**. **F0–F4 no usan LLM**; sólo F5 lo usa, con una única llamada acotada y mockeable.
> Flags: `STACKY_PIPELINE_NL_EDIT_ENABLED` default **ON** (analizar/diff, **cero escritura**) +
> `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` default **OFF** (única ruta que escribe en el repo real del operador; excepción dura (2), §3).

---

## Changelog v1 → v2 (qué corrigió la crítica)

La v1 fue **RECHAZADA** por 4 hallazgos bloqueantes. Todo lo demás del v1 se conservó: se
re-verificaron **69 anclajes** (65 exactos) y **se re-corrieron las mediciones**, que dieron
**idénticas** (round-trip 1138→588 líneas y **337→0 comentarios**; `end_mark` 112 vs fin efectivo
109; las 4 filas de indentación de §2.4; `scan_unsupported` de §F0 test 6). La tesis del plan es
correcta y está medida.

| # | Sev. | Qué estaba mal en v1 | Dónde se corrigió |
|---|---|---|---|
| **C1** | BLOQUEANTE | **Colisión de superficie**: F5 creaba `services/pipeline_edit_intent.py` y F4 editaba `components/devops/PipelineBuilderSection.tsx` — **ninguno reservado al 250** (frontera §0.3 del 246) | §3.1 (frontera), F4 (monta por `DEVOPS_SECTIONS`), F5 (capa de intent dentro de la superficie reservada) |
| **C2** | BLOQUEANTE | **La flag que escribe en el repo del operador quedaba default ON**, justificada con una premisa **falsa** (que ADO no sabe commitear) | §3 (flag partida en dos: análisis ON / commit OFF), F3 |
| **C3** | BLOQUEANTE | **Candado 3 inimplementable**: `RepoWriter` es **write-only** (`repo_writer.py:27`), no existe seam para releer el archivo y comparar `before_sha256` | §2.8 (nueva) y F3 (candados re-especificados + honestidad declarada) |
| **C4** | BLOQUEANTE | **`_finding_key` no compila contra los dataclasses reales**: `LintFinding` **no tiene `location`** (`AttributeError`) y su `line` entero se desplaza ⇒ el gate de lint marcaría como "nuevos" TODOS los findings posteriores a una inserción | §F2 (dos claves distintas, `_sem_key` / `_lint_key`) |
| C5 | IMPORTANTE | F4 no decía **de dónde sale el YAML** ⇒ el "punto de corte seguro en F4" era falso: el panel no tenía entrada | §F4 (contrato de entrada) |
| C6 | IMPORTANTE | `STACKY_PIPELINE_NL_EDIT_MAX_LLM_CALLS` era una **flag sin consumidor** y con `max_value=3` invitaba al bucle de reintentos que el propio plan prohíbe | §F3 (flag eliminada; el techo es constante del módulo) |
| C7 | IMPORTANTE | `/interpret` — el **único endpoint que gasta tokens** — no tenía test de flag-off | §F5 (test 10) |
| C8 | IMPORTANTE | `build_anchor_index` no declaraba **qué paths** debe indexar | §F0 (cobertura enumerada + test 13) |
| C9 | IMPORTANTE | `get_repo_writer` lanza **`RuntimeError`** (`repo_writer.py:38`) y el plan sólo mapeaba `NotImplementedError` y `TrackerApiError` ⇒ 500 mudo | §F3 candado 0 y §4 |
| C10 | MENOR | §2.7 daba por no verificado algo verificable en 30 s, y repetía copy **stale** ("Render-only v1") | §2.7 reescrita |
| C11 | MENOR | El glosario decía "`EditIntent` = 8 campos"; el dataclass tiene **9** | §7.1 |
| C12 | MENOR | 3 anclajes off-by-1/-6 | §2.1 |
| C13 | MENOR | No registraba la **huella de regresión** de la clase de error que mata | §7.5 (nueva) |
| **+** | **[ADICIÓN ARQUITECTO]** | El invariante que define el plan (preservación) vivía **sólo en tests que el operador nunca ve** | §F2 **Sello de preservación** + gate `G-PRESERVACION` |

---

## 0. La tesis del plan (leer esto antes que nada)

El operador dice *"agregale un stage de tests antes del deploy"* o *"esta pipeline no cachea las
dependencias, arreglalo"*, y obtiene **un cambio quirúrgico revisable** sobre el archivo que ya
tiene — no una pipeline nueva.

Crear desde cero (243/244) y editar lo existente parecen el mismo problema. **No lo son, y el
segundo es más difícil**, por una razón que se puede medir:

> Un pipeline real no es su AST. Es su AST **más** los comentarios que explican por qué está
> escrito así, el orden en que el autor lo dejó, la alineación de sus valores, y las
> construcciones que el modelo interno de Stacky no cubre.

Si el sistema parsea a `PipelineSpec` y vuelve a renderizar, **destruye todo eso en silencio**.
No es una hipótesis: se corrió sobre el corpus dorado vendorizado por el Plan 243 F0
(`backend/tests/fixtures/cicd_nl/golden/`), con las funciones que hoy existen
(`parse_ado_yaml` → `to_ado_yaml`, `services/pipeline_renderers.py:453` y `:79`):

| Golden | Líneas antes → después | Comentarios antes → después |
|---|---|---|
| `agendaweb-ci.yml` | 160 → 58 | **81 → 0** |
| `bootstrap-server-environment.yml` | 146 → 75 | **44 → 0** |
| `cd-deploy-test.yml` | 189 → 129 | **31 → 0** |
| `ci-batch.yml` | 102 → 32 | **36 → 0** |
| `ci-cd-online.yml` | 127 → 63 | **47 → 0** |
| `ci-dacpac.yml` | 116 → 42 | **57 → 0** |
| `nightly-build-online.yml` | 115 → 79 | **18 → 0** |
| `pr-validation-online.yml` | 80 → 48 | **11 → 0** |
| `security-scan-online.yml` | 103 → 62 | **12 → 0** |
| **TOTAL** | **1138 → 588 (−48 %)** | **337 → 0 (−100 %)** |

Entre esos 337 comentarios está el postmortem de **ADO-369** (`ci-cd-online.yml:10-30` en el
fixture): 21 líneas que explican por qué se eliminaron dos stages de deploy y por qué no hay que
reintroducirlos. Es exactamente el conocimiento que el Plan 243 F3 convirtió en la regla RS002.
**Un editor que regenera borra el comentario que documenta el incidente y deja la regla que lo
detecta: pierde la mitad del sistema inmunitario y encima lo hace sin avisar.**

Esta casa prohíbe explícitamente perder trabajo del operador. Por lo tanto:

> **TESIS: el editor NO regenera. Edita el documento original por splice de líneas,
> preservando byte por byte todo lo que no tocó, y prueba esa preservación con un test que se
> pone rojo si desaparece un solo comentario o una sola construcción no modelada.**

---

## 1. Objetivo y valor (KPI medibles)

Que el operador abra una pipeline que ya existe, escriba *"agregá la publicación del artefacto
después de los tests"*, vea **el diff exacto de las 8 líneas que se agregan**, y lo commitee a una
rama con confirmación — sin que se toque ni una coma del resto del archivo.

| KPI | Hoy | Con el 250 | Cómo se mide (binario) |
|---|---|---|---|
| **KPI-1 · Preservación** | 0/337 comentarios sobreviven a un round-trip | **337/337** | `test_los_337_comentarios_del_corpus_sobreviven` (F0) |
| **KPI-2 · Cirugía** | n/a (no existe la capacidad) | 0 líneas modificadas fuera de los hunks declarados | `test_el_diff_real_no_sale_de_los_hunks_declarados` (F0) |
| **KPI-3 · No romper** | n/a | 0 patches ofrecidos que introduzcan un error nuevo de lint o de semántica | `test_patch_que_introduce_error_nuevo_no_se_ofrece` (F2) |
| **KPI-4 · HITL** | n/a | 0 escrituras sin `confirm=True` | `test_commit_sin_confirm_es_400` (F3) |
| **KPI-5 · Costo** | n/a | ≤ **1** llamada LLM por pedido de edición | `test_una_sola_llamada_llm_por_pedido` (F5) + `test_interpret_404_con_flag_off` (F5) |
| **KPI-6 · Default seguro** *(v2, C2)* | n/a | **0** escrituras en el repo del operador con la instalación de fábrica | `test_commit_404_con_flag_de_commit_off` (F3) |
| **KPI-7 · Preservación en vivo** *(v2, ADICIÓN)* | el invariante sólo vive en un test que el operador no ve | el sello se calcula y **bloquea** en cada `/plan`, sobre el archivo real | `test_gate_preservacion_bloquea_si_desaparece_un_comentario` (F2) |

**Valor cualitativo:** hoy, modificar una pipeline de 130 líneas con 47 comentarios significa
abrir el YAML a mano. Con esto, significa **leer un diff de 8 líneas y apretar Confirmar**.

---

## 2. Evidencia (verificada abriendo cada archivo el 2026-07-26)

> Regla de anclajes del dossier §5 y del Plan 243 §7.2: **todo anclaje lleva el símbolo**. El
> número es una pista; si no coincide, greppeá el símbolo y **nunca concluyas que no existe**.

### 2.1 Lo que YA existe y este plan reutiliza sin reimplementar

| Pieza | Anclaje (archivo:línea `(símbolo)`) | Qué aporta a este plan |
|---|---|---|
| Parser ADO tolerante | `backend/services/pipeline_renderers.py:453 (parse_ado_yaml)` | Se usa **sólo para entender la estructura**, jamás para reescribir el archivo |
| Emisor de un paso `task:` | `backend/services/pipeline_renderers.py:110 (_task_step_doc)` | Renderiza el bloque **nuevo** que se inserta (sólo ese bloque) |
| Declaración de lo no modelado | `backend/services/pipeline_renderers.py:28 (UNSUPPORTED_CONSTRUCTS)`, `:51 (scan_unsupported)` | Invariante de preservación: lo no modelado no puede desaparecer |
| Lint estructural | `backend/services/pipeline_lint.py:791 (lint_yaml(yaml_text, provider, known_variables=None))`, `:33 (LintFinding)`, `:43 (LintReport)`, `:18-20 (SEV_ERROR/SEV_WARNING/SEV_INFO)` | Gate G-LINT por delta |
| **⚠ Forma REAL de los dos findings (C4)** | `pipeline_lint.py:33 (LintFinding)` → campos `code, severity, message, line:int\|None, node:str\|None, fix` — **NO tiene `location`**. `cicd_semantic_rules.py:63 (SemanticFinding)` → campos `code, severity, message, location:str, evidence` — **NO tiene `line`** | **Son dataclasses DISTINTOS con campos DISJUNTOS.** Una sola función de identidad para los dos revienta con `AttributeError` (§F2) |
| **Doctrina de cirugía de líneas (precedente de la casa)** | `backend/services/pipeline_lint.py:29` — comentario literal del campo `LintFix.new_yaml`: *"YAML COMPLETO corregido (cirugía de líneas, nunca re-dump)"* | **El Plan 186 ya decidió esto para los autofixes.** El 250 generaliza la misma doctrina |
| Helpers de splice ya probados | `pipeline_lint.py:218 (_rebuild)`, `:225 (_fix_replace_on_line)`, `:236 (_fix_delete_line)`, `:244 (_fix_insert_after)`, `:252 (_key_indent)` | Convención de reconstrucción y de newline final |
| Reglas semánticas por perfil | `backend/services/cicd_semantic_rules.py:497 (check_semantics(yaml_text, *, profile, repo_root=None, mode=MODE_AUDIT))`, `:43 (MODE_AUDIT)`, `:44 (MODE_NL_STRICT)`, `:48 (_NL_STRICT_ONLY)`, **`:63 (SemanticFinding)`** *(v1 decía `:62`; ahí está el `@dataclass` — C12)*, `:51 (MAX_YAML_BYTES = 512*1024)` | Gate G-SEM por delta. **La elección de modo es la decisión sutil de §F2**. Ojo: `mode` inválido **lanza `ValueError`** (`:503-504`) |
| **`check_semantics` NO tiene ningún consumidor en producción hoy** | verificado: `grep -rn "check_semantics" backend --include=*.py` fuera de su módulo y de los tests ⇒ **0 hits** | **F2 es su PRIMER call-site real.** Su tasa de falsos positivos sobre pipelines de producción nunca se midió en vivo — que es exactamente por qué el gate va **por delta** y no por valor absoluto (§F2) |
| Catálogo cerrado de tareas | `backend/services/cicd_task_catalog.py:199 (get_task)`, `:204 (is_allowed)`, `:209 (validate_inputs)`, `:43 (TaskSpec)`, `:30 (PROFILE_DOTNET_FRAMEWORK)`, `:268 (extract_task_dicts)` | El LLM elige **dentro** del catálogo; nunca inventa una tarea |
| Escritura al repo | `backend/services/repo_writer.py:30 (get_repo_writer(project=None))`, `:17 (RepoWriter.commit_file(path, content, branch, message))` | **Acepta contenido literal y ruta arbitraria** ⇒ sirve para commitear el archivo parcheado tal cual |
| **El puerto es SOLO-ESCRITURA (C3)** | `repo_writer.py:27 (REPO_WRITER_METHODS = ("commit_file",))` | **No hay `get_file`/`read_file` en el puerto.** Consecuencia dura en §2.8 |
| **`get_repo_writer` lanza `RuntimeError` (C9)** | `repo_writer.py:37-41` (`if not isinstance(provider, RepoWriter): raise RuntimeError(...)`) | El precedente lo mapea a **400**, no lo deja escapar: `pipeline_generator.py:71-73` (`except Exception as e: return jsonify({"error": str(e)}), 400`) |
| **ADO SÍ commitea de verdad (C10 — corrige §2.7 del v1)** | `backend/services/ado_provider.py:146 (commit_file)` — *"Plan 95 F1.a — commit real vía Git Pushes API (**cierra el TODO del plan 73 C12**)"*; crea la rama desde la default si no existe (`:168-191`), y devuelve `status='unchanged'` sin pushear si el contenido ya es idéntico (`:199-221`) | **El 250 escribe en el repo REAL del operador.** Es la premisa que obliga a partir la flag (§3) |
| Rama por defecto del repo (candado 2) | `backend/services/ado_pipeline_definitions.py:64 (_default_branch(provider, project))` — *"GET .../repositories/{id} → campo `defaultBranch`, STRIP del prefijo `refs/heads/`"* | Seam real para rechazar el commit sobre la rama por defecto |
| Ritual HITL del commit | `backend/api/pipeline_generator.py:53 (commit_route)` *(v1 decía `:52`; ahí está el decorador `@bp.post("/commit")` — C12)*, `:59` (`if body.get("confirm") is not True: → 400 "confirm=True requerido (HITL)"`) | Se copia **el mismo ritual**, palabra por palabra |
| Modal de commit con confirm | `frontend/src/components/devops/CommitPipelineModal.tsx:41 (confirmChecked)`, `:145` (texto del checkbox), `:163` (botón deshabilitado sin confirm) | Lenguaje UX del commit ya establecido |
| **Diff con LCS ya en el panel** | `frontend/src/components/devops/pipelineLint.ts:91 (buildDiffLines(oldYaml, newYaml) → DiffResult)`, `:79 (DiffRow)`, `:87 (DiffResult.rows)`; consumido en `PipelineLintPanel.tsx:13-19` (import) y `:190` (render) | **No se escribe ni una línea de diff nueva en el frontend**: ya existe y ya se usa para previsualizar autofixes. **`buildDiffLines` NO tiene cap** (matriz LCS `O(n·m)` cruda, `pipelineLint.ts:94-96`) ⇒ el cap lo pone `canRenderDiff` de F4, y es obligatorio |
| **Punto de montaje del panel (C1)** | `frontend/src/pages/DevOpsPage.tsx:112-113` — comentario literal: *"Los planes 88/89 y features futuras agregan entradas aquí SIN refactor"* + `DEVOPS_SECTIONS`; gate declarativo por `healthKey`/`gateFlagKey`/`gateMessage` (`:79-81`, ejemplo `:136-138`) | **Extensión documentada de la casa.** El 250 agrega **una entrada**; **NO** toca `PipelineBuilderSection.tsx` |
| Llaves de salud que alimentan ese gate | `backend/api/devops.py:42` (`"publications_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PUBLICATIONS_ENABLED", False))`), `:72` (`"cockpit_enabled"`, Plan 239) | Patrón literal para publicar la llave del 250 |
| Segundo diff (referencia) | `frontend/src/components/dbcompare/lineDiff.ts:22 (diffLines)`, `:12 (MAX_LINES = 3000)` | Precedente del cap duro para no colgar la UI con un LCS O(n·m) |
| Contrato UX de IA del panel | `frontend/src/components/devops/PipelineBuilderSection.tsx:382-383` (Plan 106 F5, literal: *"pide sugerencias al modelo local y PRE-RELLENA solo lo que está vacío (KPI-5, HITL): nunca pisa lo que el operador ya escribió"*), `:384 (handleSuggestWithLocalLlm)`, `:403-408` (patrón "sólo si está vacío") | **Este plan entra por ese mismo lenguaje** |
| Seam de LLM | `backend/services/pm/pm_llm_client.py:278 (call_llm)`, `:90 (LLMCallSpec)`, `:98 (temperature=0.0)`, `:99 (fixture_id)`, `:101 (expect_json)` — docstring `:281-283`: *"Nunca lanza excepción al caller por fallas de red/SDK: devuelve `success=False`"* | Única llamada LLM, mockeable por `fixture_id` |
| Contrato de flags | `backend/services/harness_flags.py:21 (FlagSpec)`, `:22 (key)`, `:23 (type)`, `:29 (default)`, `:30-32 (requires — informativo, ningún runner lo evalúa)`, `:33 (min_value)`, `:34 (max_value)` | Ambas flags configurables **desde la UI** |
| Ratchet de tests (**DOS listas**) | `backend/scripts/run_harness_tests.sh:20 (HARNESS_TEST_FILES=()` **y** `backend/scripts/run_harness_tests.ps1:13 ($HarnessTestFiles = @()` | Todo `test_*.py` nuevo se registra **en las dos** |
| Curación de defaults ON | `backend/tests/test_harness_flags.py:467 (_CURATED_DEFAULTS_ON)` | Una flag `default=True` fuera de esta lista pone rojo `test_default_known_only_for_curated` |
| Corpus dorado real | `backend/tests/fixtures/cicd_nl/golden/*.yml` (9 archivos, Plan 243 F0) | **Los fixtures de edición son pipelines de producción**, no YAMLs de juguete |

### 2.2 El hallazgo técnico que hace posible la cirugía: `yaml.compose()` da marcas de línea

`PyYAML 6.0.3` (ya en `requirements.txt`, verificado por el Plan 243 §pipeline_renderers.py:9)
expone `yaml.compose(text)` → árbol de `Node` con `start_mark.line`, `start_mark.column`,
`end_mark.line`. **Corrido de verdad contra el corpus** con
`backend/.venv\Scripts\python.exe` (Python 3.13.5):

```
compose ok: MappingNode 32 127
'trigger'   clave L32   valor L33..44
'pr'        clave L44   valor L44..44
'variables' clave L47   valor L48..55
'pool'      clave L55   valor L56..61
'stages'    clave L61   valor L62..127        (líneas 0-based)
```

Es decir: **se puede localizar cualquier nodo en el texto original sin perder el texto original**.
Ese es todo el mecanismo. No hace falta ninguna dependencia nueva.

> **`ruamel.yaml` NO está instalado** — verificado: `ModuleNotFoundError: No module named 'ruamel'`.
> Agregarlo caería en la **excepción dura (3)** del dossier §6 (*prerequisito no garantizado en la
> instalación default*) y rompería la paridad de runtimes en cualquier máquina que instale sin
> tocar `requirements.txt`. **Se descarta explícitamente.** El camino es PyYAML + splice.

### 2.3 La trampa del `end_mark` (esto es lo que un modelo menor rompe en silencio)

Sobre `ci-cd-online.yml`, los 6 items de `stages[0].jobs[0].steps`:

```
item 3  → start_mark.line 100   end_mark.line 112     (- task: DotNetCoreCLI@2)
item 4  → start_mark.line 112   end_mark.line 121     (- task: PublishTestResults@2)
```

Pero el contenido real del item 3 **termina en la línea 109**. Las líneas 110 y 111 son:

```
110  ''                                              ← línea en blanco
111  '    # 4. Publicar resultados de tests en ADO'   ← comentario del paso SIGUIENTE
```

**`end_mark.line` de un item de secuencia es EXCLUSIVO y se traga las líneas en blanco y el
comentario que introduce al item siguiente.** Una implementación ingenua que inserte "después del
item 3" en la línea `end_mark.line` deja el paso nuevo **debajo** del comentario
`# 4. Publicar resultados de tests en ADO`, huerfanando ese comentario sobre el paso equivocado.
Es corrupción silenciosa: el YAML sigue siendo válido y el operador tiene que descubrirlo leyendo.

**Regla obligatoria, sin margen de interpretación (se codifica en F0 y se testea):**

```
fin_efectivo(item) = max{ i ∈ [start_mark.line, end_mark.line)
                          : L[i].strip() != "" y no L[i].lstrip().startswith("#") }
punto_de_insercion_despues_de(item) = fin_efectivo(item) + 1
```

Las líneas en blanco y los comentarios finales **quedan con el item siguiente**, que es donde el
autor los puso.

### 2.4 La indentación no es una constante: se deriva del archivo

Los dos estilos conviven en el corpus real:

| Archivo | Forma | Columna del `-` | Columna de las claves |
|---|---|---|---|
| `ci-cd-online.yml:63` | `- stage: Build` (a ras) | 0 | 2 |
| `cd-deploy-test.yml:116` | `  - stage: DeployAgendaWeb` (indentado) | 2 | 4 |
| `ci-cd-online.yml:71` | `    - task: NuGetToolInstaller@1` | 4 | 6 |
| `cd-deploy-test.yml:135` | `                - task: PowerShell@2` | 16 | 18 |

`yaml.compose` da `item.start_mark.column` = columna de la **primera clave** del mapping
(6 y 18 en los casos de arriba). La columna del guion se lee del texto:
`dash_col = start_mark.column - 2`, **verificando** que `L[start][dash_col] == '-'`; si no
coincide (por ejemplo un item escrito como `-` solo en su línea y las claves abajo), **se devuelve
un error accionable, nunca se adivina** (test 11 de F0).

### 2.5 El flujo de commit existente NO sirve tal cual (y por qué)

`backend/api/pipeline_generator.py:52 (commit_route)` es HITL y correcto para **crear**, pero para
**editar** tiene dos bloqueos verificados:

1. `:67` — `yaml_str = to_ado_yaml(spec) if target == "ado" else to_gitlab_yaml(spec)`:
   **regenera desde el spec**. Es exactamente la ruta que borra los 337 comentarios (§0).
2. `:70` — `path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"`: **ruta
   hardcodeada**. No puede apuntar a `pipelines/ci-cd-online.yml`, que es donde viven los
   pipelines reales.

**Decisión:** se reutiliza **el seam** (`get_repo_writer(...).commit_file(...)`,
`repo_writer.py:30` y `:17`) y **el ritual** (`confirm is not True` → 400, copiado de
`pipeline_generator.py:59`), pero **no** la ruta `/commit`. El endpoint del 250 manda el texto
parcheado literal y la ruta real. `pipeline_generator.py` **no se modifica** (retrocompatible).

### 2.6 Trampa del corpus vendorizado: **+1 línea respecto de todos los anclajes del Plan 243**

El Plan 243 F0 agregó una línea de procedencia al principio de cada fixture
(`# fuente: RSPACIFICO/pipelines/<archivo> - copiado 2026-07-26 (plan 243 F0)`). Por lo tanto
**todo anclaje del Plan 243 al corpus está desplazado exactamente +1 respecto del fixture
vendorizado**. Verificado con `grep -n` sobre los fixtures:

| Lo que dice el Plan 243 | Dónde está de verdad en `backend/tests/fixtures/cicd_nl/golden/` |
|---|---|
| `nightly-build-online.yml:110` (`- script: |` crudo) | **`:111`** |
| `ci-batch.yml:58-59` (`matrix:`) | **`:60`** |
| `ci-cd-online.yml:9-29` (postmortem ADO-369) | **`:10-30`** |

**Este plan ancla siempre al fixture vendorizado** (que es lo que corren los tests), y lo dice
acá para que quien implemente no crea que el 243 se equivocó ni "corrija" nada.

### 2.7 Lo NO verificado (declarado)

- **No se abrieron** `ci-dacpac.yml`, `security-scan-online.yml`, `pr-validation-online.yml`,
  `bootstrap-server-environment.yml`, `agendaweb-ci.yml` ni `ci-batch.yml` línea por línea: de
  ellos sólo se verificó, por ejecución, el conteo de líneas/comentarios de la tabla §0 y los tres
  `grep` de §2.6. Los tests de F0 los recorren **por enumeración del directorio**, no por anclaje
  a una línea concreta de cada uno, precisamente para no depender de lo no verificado.
- **`services/pipeline_recommendations.py` y `cicd_security_rules.py` (Plan 248) NO existen hoy**
  — están reservados en el dossier §3. El puente `OPT*` de F5 se implementa con **import blando**
  y degradación declarada (§F5), no asumiendo que estén.
- ~~No se verificó que el `RepoWriter` concreto de ADO soporte `commit_file`~~ → **CORREGIDO EN v2
  (C10): SÍ lo soporta y escribe de verdad.** `ado_provider.py:146 (commit_file)` implementa un
  push real por la Git Pushes API desde el **Plan 95 F1.a**, cuyo docstring dice literalmente que
  *"cierra el TODO del plan 73 C12"*. El `NotImplementedError → 501` de
  `pipeline_generator.py:86-88` y el copy *"Render-only v1 (commit devuelve 501)"* de
  `CommitPipelineModal.tsx:91` son **restos stale del Plan 73**, no el estado actual.
  **Consecuencia:** el 250 **no es una feature de sólo-lectura con un final teórico**; su
  `/commit` empuja commits al repo real del operador. Por eso la ruta de escritura tiene **su
  propia flag, default OFF** (§3). El camino 501 se conserva igual en §4 como degradación honesta
  para cualquier provider que no implemente el puerto — pero **no es el caso de ADO**.
- **No se abrió** el resto de `ado_provider.commit_file` más allá de `:146-221` (resolución de
  ref, creación de rama y detección `create/update/unchanged`). Lo que hay debajo de `:221` (el
  push propiamente dicho) **no se verificó línea por línea**; se asume el contrato declarado en
  `repo_writer.py:17-22` (`{sha, branch, path, web_url, status}` + `TrackerApiError`).
- Este plan **no toca ninguna tabla de base de datos**.

### 2.8 El puerto de repo es SOLO-ESCRITURA: qué se puede y qué NO se puede prometer (C3)

`REPO_WRITER_METHODS = ("commit_file",)` (`repo_writer.py:27`). **No existe ningún método de
lectura de archivos del repo en el puerto**, y el único lector de contenido que existe está
*enterrado adentro* de `ado_provider.commit_file` (`:200-211`: `GET .../items?path=...&
versionDescriptor.version={branch}` + `base64.b64decode`), sin exponerse. Verificado además que
`ado_pipeline_definitions.py:82 (find_yaml_definition)` devuelve la **definición de pipeline**, no
el contenido del archivo en una rama.

**Por lo tanto el candado "releo el archivo y comparo el sha" del v1 era inimplementable.** Lo que
se puede prometer de verdad, y lo que no:

| Promesa | ¿Se puede? | Cómo |
|---|---|---|
| "Lo que se commitea es lo que el operador aprobó" | **SÍ, duro** | El servidor **recompila** el patch desde el `intent` y compara con `approved_after_sha256`; **nunca** acepta el YAML del cliente (F3 candado 4) |
| "El `before` que se parcheó es el que el operador vio" | **SÍ, duro** | El servidor rehashea el `before` recibido y lo compara con `before_sha256` (auto-consistencia del request) |
| "El archivo no cambió **en el repo** desde que viste el diff" | **NO con el puerto actual** | Se **declara** `stale_check: "no_verificable"` en la respuesta y en la UI. **Jamás se reporta como validado** — misma doctrina que `repo_root=None` ⇒ RS006 `skipped` |
| "Dos commits concurrentes no se pisan" | **SÍ, pero lo garantiza ADO, no Stacky** | `ado_provider.py:161-191` resuelve el `old_object_id` del ref y pushea contra él; un push concurrente sobre la misma rama lo **rechaza ADO** con `TrackerApiError`, que se propaga con su status real |

**Esto NO se resuelve agregando un método al puerto**: `RepoWriter` es superficie del Plan 73/95 y
está **fuera de la frontera del 250** (§3.1). Si algún día se agrega `get_file` al puerto, este
candado pasa de "declarado" a "verificado" **sin tocar nada más** que la función que hoy devuelve
`"no_verificable"`. Queda anotado como deuda nombrada, no como hueco silencioso.

---

## 3. Principios, guardarraíles y alcance

**En alcance:** editar un YAML ADO existente por verbos cerrados; describir el cambio en lenguaje
natural; diff visible; gates por delta; commit HITL a una rama; puente opcional con las
recomendaciones del 248.

**Guardarraíles no negociables (dossier §6), codificados en las fases:**

1. **Human-in-the-loop, y acá es el corazón.** Nada se escribe ni se commitea sin `confirm=True`
   explícito. El operador **siempre ve el diff antes**. El sistema no aplica un patch por su
   cuenta ni siquiera cuando el gate está verde. F3 lo prueba con `test_commit_sin_confirm_es_400`.
2. **Cero trabajo extra al operador — con la escritura separada de la lectura (C2).** El v1 tenía
   **una sola flag default ON** que habilitaba también el `/commit`, y lo justificaba diciendo que
   el commit "no es destructivo". Esa justificación se apoyaba además en una premisa **falsa**
   (§2.7: se creía que ADO no sabía commitear). Con ADO commiteando de verdad
   (`ado_provider.py:146`), **la superficie de análisis y la superficie de escritura no pueden
   compartir interruptor**. Quedan dos:

   | Flag | Default | Qué habilita | Por qué ese default |
   |---|---|---|---|
   | `STACKY_PIPELINE_NL_EDIT_ENABLED` | **ON** | `/plan`, `/verbs`, `/interpret` y el panel. **Cero escritura**: analiza, parchea en memoria y muestra el diff | **Ninguna de las 4 excepciones duras aplica**: no bypasea revisión humana (la exige), **no escribe nada en ningún lado**, no agrega prerequisitos (PyYAML ya está: `requirements.txt`), no reduce la seguridad (agrega gates) |
   | `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` | **OFF** | **Sólo** `/commit` | **Excepción dura (2): escribe en un sistema externo real del operador** (push a su Azure DevOps). Que sea reversible (borrar la rama) no lo hace no-escritura. Encender esto es una decisión consciente del operador, una vez, desde la UI |

   **Esto NO agrega trabajo al operador para el 95 % del valor**: con la instalación default puede
   describir el cambio, ver el diff exacto y copiarlo. Lo único que pide un clic previo es el
   push. Y el panel **lo dice**: con la flag de commit en OFF el botón muestra
   *"Activar el commit desde Configuración → Arnés"* con el deep-link, en vez de esconderse.
3. **Paridad de 3 runtimes.** F0–F4 **no invocan LLM ni red**: paridad trivial. F5 usa una única
   llamada por `pm_llm_client.call_llm` (`:278`), que **nunca lanza** (`:281-283`), y tiene
   fallback declarado (§F5).
4. **No degradar, backward-compatible.** No se modifica `pipeline_generator.py`, ni
   `pipeline_renderers.py`, ni `pipeline_lint.py`, ni `cicd_semantic_rules.py`. Todo el código
   nuevo vive en módulos nuevos. El panel gráfico actual queda **idéntico** con la flag en OFF.
5. **Mono-operador sin auth.** Ningún RBAC, ningún rol. El `confirm` es del operador, punto.

**Fuera de alcance (§6 lo detalla plan por plan):** crear pipelines desde cero, descubrir,
perfilar, definir reglas nuevas, GitLab, entornos, bundle.

### 3.1 Frontera de superficie: los archivos que este plan puede tocar (C1 — BLOQUEANTE en v1)

El dossier §0.3 del **Plan 246** reserva superficies por plan para que los 7 planes de la serie no
colisionen. **El v1 se salía de la reserva en dos lugares** y eso habría pisado trabajo de otros
planes. Lista **cerrada**; lo que no está acá, no se toca:

| Puede CREAR | Puede EDITAR |
|---|---|
| `backend/services/pipeline_patcher.py` | `backend/services/harness_flags.py` |
| `backend/services/pipeline_diff.py` | `backend/config.py` |
| `backend/api/pipeline_editor.py` | `backend/tests/test_harness_flags.py` |
| `frontend/src/devops/pipelineEditModel.ts` | `backend/scripts/run_harness_tests.sh` y `.ps1` |
| `frontend/src/components/devops/PipelineEditNlPanel.tsx` (+ su `.module.css`) | `backend/api/__init__.py` |
| `backend/tests/test_plan250_*.py` | `backend/api/devops.py` |
| `backend/tests/fixtures/pipeline_edit/**` | `frontend/src/pages/DevOpsPage.tsx` |
| `frontend/src/devops/__tests__/pipelineEditModel.test.ts` | `frontend/src/api/endpoints.ts` |

**Las dos violaciones del v1 y su corrección:**

1. **`backend/services/pipeline_edit_intent.py` (F5) — NO reservado.** Corrección: la capa de
   intent se parte entre las dos superficies que **sí** son del 250: el **esquema cerrado y la
   validación pura** (`INTENT_SCHEMA`, `validate_intent_dict`) van a
   `services/pipeline_patcher.py`, junto a `EDIT_VERBS` que ya vive ahí (F1) y de quien son la
   contracara; **la llamada al LLM y el armado del prompt** van a `api/pipeline_editor.py`, que es
   su único caller. No se pierde ninguna capacidad y no se crea ningún archivo fuera de la
   reserva. *Si el operador prefiere el módulo separado, primero hay que agregarlo a la reserva
   §0.3 del 246 — nunca al revés.*
2. **`frontend/src/components/devops/PipelineBuilderSection.tsx` (F4) — NO reservado**, y encima
   es territorio de los planes 87/106/243/244 **con guardias de contenido literal sobre el
   archivo** (`frontend/src/components/devops/__tests__/PipelineBuilderSection.test.ts:44-118`
   lee el `.tsx` con `readFileSync` y afirma cadenas). Corrección: el panel **no se monta ahí**.
   Se agrega **una entrada** a `DEVOPS_SECTIONS` en `DevOpsPage.tsx:113`, que es el punto de
   extensión que la casa documenta en el comentario de `:112` (*"features futuras agregan entradas
   aquí SIN refactor"*), con su `healthKey` publicado desde `backend/api/devops.py` (patrón `:42`
   y `:72`). Ambas superficies **están reservadas al 250**.

**Prohibido explícitamente** (exclusivos de otros planes de la serie): `pipeline_renderers.py` y
`cicd_semantic_rules.py` (**249**), `pipeline_recommendations.py` y `cicd_security_rules.py`
(**248**), `pipeline_generator.py` y `pipeline_lint.py` (**73/186**), `repo_writer.py` y
`ado_provider.py` (**73/95**). **De todos ellos se IMPORTA y se lee; ninguno se modifica** — lo
verifica el gate `git diff --name-only` del DoD (§7.4).

**Recorte de alcance decidido por adelantado (precedente: el 243 tuvo que partirse, su C25):**
este plan tiene **exactamente 6 fases (F0..F5)** y **provider ADO solamente**. Se recorta a
propósito:

- **Verbos cerrados, 7 y ni uno más** (§F1). Nada de "editar cualquier cosa".
- **Sin bucle de auto-reparación.** Ninguno. Si el intent no valida, se le pregunta al operador
  (§F5). El 243 aprendió con su C10 que un bucle sin techo es una fuga; el techo más honesto y
  más barato es **cero reintentos automáticos** cuando el humano está mirando la pantalla.
- **GitLab queda afuera** de la ruta NL de edición (el 249 lleva la paridad GitLab del motor).
- **Si la corrida de implementación no llega a F5**, la feature ya está completa y es útil:
  F0–F4 entregan edición quirúrgica por controles estructurados, con diff y commit HITL. F5 sólo
  agrega la puerta de entrada en lenguaje natural.

---

## F0 — Motor de anclajes y splice quirúrgico (`pipeline_patcher.py`)

**Objetivo:** poder modificar N líneas de un YAML dejando **todas las demás byte-idénticas**, y
probarlo sobre 9 pipelines de producción. **Sin LLM, sin red, sin I/O.**

**Crear:** `backend/services/pipeline_patcher.py`, `backend/tests/test_plan250_patcher.py`.
**Editar:** nada.

```python
# backend/services/pipeline_patcher.py
PATCHER_VERSION = "250.1"
MAX_YAML_BYTES = 512 * 1024      # mismo límite que cicd_semantic_rules.py:51
MAX_OPS_PER_PLAN = 12            # techo duro: un patch no es una reescritura

@dataclass(frozen=True)
class Anchor:
    path: str          # "stages[0].jobs[0].steps"
    kind: str          # "seq" | "map" | "scalar"
    key_line: int|None # línea 0-based de la clave que abre el bloque; None en items
    start_line: int    # 0-based, primera línea del VALOR
    end_line: int      # 0-based INCLUSIVE, fin EFECTIVO (§2.3)
    key_col: int       # columna de las claves hijas
    dash_col: int|None # columna del guion si kind == "seq"; None si no
    item_paths: tuple  # para seq: paths de sus items, en orden

@dataclass(frozen=True)
class EditOp:
    kind: str          # "insert_after" | "insert_before" | "replace" | "delete"
    anchor_path: str   # path del Anchor sobre el que opera
    lines: tuple       # líneas YA indentadas a insertar; () para "delete"
    reason: str        # español, 1 línea: por qué existe esta op (va al hunk)

@dataclass(frozen=True)
class Hunk:
    start_line: int    # 1-based sobre el ORIGINAL
    end_line: int      # 1-based INCLUSIVE sobre el ORIGINAL; == start_line-1 si es inserción pura
    before: tuple      # líneas originales del rango
    after: tuple       # líneas resultantes
    reason: str

@dataclass(frozen=True)
class PatchResult:
    ok: bool
    text: str          # YAML resultante; == entrada si ok is False
    hunks: tuple
    errors: tuple      # mensajes en español; () si ok

def build_anchor_index(yaml_text: str) -> tuple[dict, tuple]:
    """→ ({path: Anchor}, errores). Usa yaml.compose(); NUNCA regex. Jamás lanza."""

def render_block(doc: dict, *, key_col: int, dash_col: int|None) -> tuple:
    """dict de UN paso/job/stage → líneas indentadas. Usa yaml.safe_dump(sort_keys=False)
    sobre ESE dict solo, y re-indenta. Nunca toca el documento completo."""

def apply_ops(yaml_text: str, ops: tuple) -> PatchResult:
    """Aplica las ops de abajo hacia arriba (índices estables). PURA."""
```

**Reglas duras que el implementador NO puede reinterpretar:**

1. **`build_anchor_index` usa `yaml.compose`, jamás `grep`/`re`/lectura por líneas** para
   localizar estructura (misma doctrina que el Plan 243 C20 impuso al catálogo).
1-bis. **Cobertura EXACTA del índice (C8 — el v1 no la declaraba).** `build_anchor_index` indexa
   **exactamente** este conjunto de paths, ni uno más ni uno menos. Un path que no esté acá **no
   es direccionable** por un `EditOp`, y pedirlo devuelve un error accionable que **enumera los
   paths disponibles**:

   | Path | Cuándo existe |
   |---|---|
   | `trigger`, `pr`, `schedules`, `variables`, `pool`, `stages`, `jobs`, `steps` | si la clave existe en la **raíz** del documento |
   | `trigger.paths`, `trigger.paths.include` | si existen |
   | `stages[i]` | por cada item de `stages` |
   | `stages[i].jobs`, `stages[i].jobs[j]` | idem |
   | `stages[i].jobs[j].steps`, `stages[i].jobs[j].steps[k]` | idem |
   | `stages[i].jobs[j].strategy`, `...runOnce`, `...runOnce.deploy`, `...runOnce.deploy.steps`, `...steps[k]` | **obligatorio**: `cd-deploy-test.yml` es un `deployment:` y sin esto no es editable (test 7 lo exige) |
   | `jobs[j]`, `jobs[j].steps`, `jobs[j].steps[k]` | pipelines **sin** `stages` (job-level), p.ej. `pr-validation-online.yml` |
   | `steps[k]` | pipelines **sin** `stages` ni `jobs` (step-level) |

   Y **una excepción explícita hacia abajo**, porque `set_task_input` la necesita:
   `<step>.inputs` y `<step>.inputs.<clave>` (nodos escalares, `kind="scalar"`). **Es
   obligatoria**: sin ella `set_task_input` tendría que re-renderizar el paso entero, lo que
   borraría los comentarios de adentro del paso y haría **imposible** el test 5
   (`1 hunk de 1 línea`). Con ella, cambiar un input es un `replace` de la línea del escalar
   —o un `insert_after` de `inputs:` si la clave no existía—, y todo lo demás del paso queda
   byte-idéntico. **Nada más profundo se indexa** (no se entra en listas dentro de un input).
2. **Fin efectivo** exactamente como §2.3. Escribirlo de otra forma rompe el test 2.
3. **Columnas derivadas del archivo** exactamente como §2.4. Si `L[start][dash_col] != '-'`
   ⇒ `errors` con mensaje accionable y `ok=False`. **Nunca adivinar.**
4. **Ops solapadas ⇒ rechazo total.** Si dos ops tocan rangos que se intersectan, no se aplica
   ninguna: `ok=False`. Un patch a medias es peor que ninguno.
5. **Newline final preservado** con la convención ya existente de `pipeline_lint.py:218
   (_rebuild)`: si el original terminaba en `\n`, el resultado también.
6. **`len(yaml_text) > MAX_YAML_BYTES` ⇒ `ok=False`** con un error, nunca colgar el request
   (espejo de `cicd_semantic_rules.py:506-512`).
7. **`len(ops) > MAX_OPS_PER_PLAN` ⇒ `ok=False`.**
8. **`yaml.YAMLError` ⇒ `ok=False` con el error**, jamás propagar la excepción.

**Tests PRIMERO (12) — `backend/tests/test_plan250_patcher.py`:**

| # | Test | Qué prueba |
|---|---|---|
| 1 | `test_indice_de_anclajes_de_ci_cd_online` | `build_anchor_index` sobre el fixture devuelve `stages[0].jobs[0].steps` con `key_col == 6`, `dash_col == 4` y **6** `item_paths` |
| 2 | `test_fin_efectivo_excluye_comentario_del_siguiente_item` | **§2.3.** El `Anchor` de `stages[0].jobs[0].steps[3]` tiene `end_line == 109` (0-based), **no 111** |
| 3 | `test_insertar_paso_al_final_preserva_los_47_comentarios` | Insertar un `- task: PublishCodeCoverageResults@2` al final de los steps de `ci-cd-online.yml`: el resultado tiene **47** líneas de comentario, igual que el original |
| 4 | `test_el_diff_real_no_sale_de_los_hunks_declarados` | **KPI-2.** Con `difflib.SequenceMatcher` (stdlib) sobre `(before, after)`, **todo opcode distinto de `equal` cae dentro de un `Hunk` declarado**. Es la prueba de que los hunks son la verdad y no una reconstrucción |
| 5 | `test_los_337_comentarios_del_corpus_sobreviven` | **KPI-1, CAPSTONE.** Para **los 9** goldens: aplicar una inserción al final del primer bloque `steps:` encontrado y afirmar que el conteo de líneas-comentario del resultado es **igual** al del original. Total del corpus: **337** |
| 6 | `test_construcciones_no_modeladas_no_desaparecen` | Para los 9: `scan_unsupported(after) == scan_unsupported(before)` (`pipeline_renderers.py:51`). En particular `ci-batch.yml` conserva `"matrix"` y `bootstrap-server-environment.yml` conserva `"compile_time_expression"` |
| 7 | `test_indentacion_se_deriva_del_archivo` | El mismo paso insertado en `ci-cd-online.yml` sale con guion en col 4 y en `cd-deploy-test.yml` (dentro del deployment) con guion en col 16 |
| 8 | `test_newline_final_se_preserva` | Con y sin `\n` final: el resultado respeta el original |
| 9 | `test_yaml_invalido_no_lanza` | `apply_ops("stages: [\n", ops)` ⇒ `ok is False`, sin excepción |
| 10 | `test_yaml_gigante_rechazado` | 600 KB ⇒ `ok is False` con error; no procesa |
| 11 | `test_item_con_dash_en_linea_propia_no_soportado` | `- \n  task: X` ⇒ `ok is False` con error accionable. **No adivina** |
| 12 | `test_ops_solapadas_rechazadas` | Dos ops sobre rangos que se cruzan ⇒ `ok is False` y `text == entrada` |
| 13 | `test_cobertura_del_indice_es_la_declarada` | **C8.** Para los 9 goldens: el conjunto de claves de `build_anchor_index` es **exactamente** el de la tabla de la regla 1-bis (ni de más ni de menos). En particular `cd-deploy-test.yml` expone `...strategy.runOnce.deploy.steps` y `pr-validation-online.yml` expone `jobs[0].steps` **sin** `stages` |
| 14 | `test_path_inexistente_enumera_los_disponibles` | Pedir `stages[9].jobs[0].steps` ⇒ `ok is False` y el mensaje **lista los paths que sí existen**. No "no encontrado" a secas |

**Comando exacto (dossier §4):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan250_patcher.py -q
```

**Registrar** `tests/test_plan250_patcher.py` en **las DOS listas del ratchet**:
`backend/scripts/run_harness_tests.sh:20 (HARNESS_TEST_FILES=()` y
`backend/scripts/run_harness_tests.ps1:13 ($HarnessTestFiles = @()`, y correr
`.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q`.

**Criterio de aceptación (BINARIO):** **14/14** verdes, en particular los tests 2, 4, 5, 6 y 13.
Además `test_harness_ratchet_meta.py` verde.

> **Anclajes de los tests, RE-VERIFICADOS por la crítica v2 corriendo el código** (no copiados del
> v1): `stages[0].jobs[0].steps` de `ci-cd-online.yml` da `key_col=6`, `dash_col=4` y **6** items
> (test 1); el item 3 va de `start_mark.line=100` a `end_mark.line=112` con **fin efectivo 109**, y
> las líneas 110/111 son la vacía y `'    # 4. Publicar resultados de tests en ADO'` (test 2);
> `ci-cd-online.yml` tiene **47** comentarios y el corpus **337** (tests 3 y 5);
> `scan_unsupported` da `('matrix',)` en `ci-batch.yml`, `('compile_time_expression',)` en
> `bootstrap-server-environment.yml` y `()` en `ci-cd-online.yml` (test 6). **Los cuatro números
> del v1 eran correctos.**

**Flag:** ninguna (módulo puro sin consumidor todavía; se cablea en F3).
**Impacto por runtime:** idéntico en los 3 — no hay LLM, red ni I/O. **Fallback: no aplica,
no hay nada que degradar.**
`Trabajo del operador: ninguno`

---

## F1 — Verbos de edición cerrados: `EditIntent` → `EditPlan` (determinista)

**Objetivo:** un conjunto **cerrado y pequeño** de cambios expresables, compilados a `EditOp`s de
forma 100 % reproducible. **Sin LLM.**

**Crear:** `backend/tests/test_plan250_verbos.py`.
**Editar:** `backend/services/pipeline_patcher.py` (agrega la capa de verbos; mismo módulo porque
comparte el índice de anclajes y no tiene sentido separarla).

```python
EDIT_VERBS = (
    "add_step",          # agregar un paso `- task:` a un job existente
    "remove_step",       # quitar un paso por su ref (`PublishTestResults@2`) o índice
    "move_step",         # reordenar un paso dentro del mismo job
    "set_task_input",    # cambiar/agregar un `inputs.<clave>` de un paso existente
    "add_stage",         # agregar un stage completo (build/test) antes o después de otro
    "set_trigger_paths", # reemplazar el bloque trigger.paths.include
    "set_schedule",      # agregar/reemplazar el bloque schedules
)

@dataclass(frozen=True)
class EditIntent:
    verb: str
    target_path: str      # path del índice de F0, p.ej. "stages[0].jobs[0].steps"
    anchor_ref: str|None  # ref del paso de referencia, p.ej. "PublishBuildArtifacts@1"
    position: str         # "before" | "after" | "end"
    task_ref: str|None    # "PublishTestResults@2" — DEBE estar en el catálogo del perfil
    inputs: dict
    display_name: str
    values: tuple         # para set_trigger_paths / set_schedule
    notes: tuple          # supuestos asumidos — SE MUESTRAN SIEMPRE al operador

def plan_edit(yaml_text: str, intent: EditIntent, *, profile: str) -> tuple[tuple, tuple]:
    """→ (ops, errores). DETERMINISTA: mismo (yaml_text, intent, profile) ⇒ mismas ops,
    byte por byte, siempre. NO aplica nada: sólo planifica."""
```

**Validaciones obligatorias antes de emitir una sola op:**

- `verb not in EDIT_VERBS` ⇒ error. **Lista cerrada.**
- `task_ref` con `is_allowed(profile, task_ref) is False`
  (`cicd_task_catalog.py:204`) ⇒ error. **El editor no puede introducir una tarea que no esté
  en el catálogo**, ni aunque el operador la escriba a mano en el formulario.
- `validate_inputs(profile, task_ref, inputs) != []` (`:209`) ⇒ error con la lista de inputs
  inválidos.
- `display_name` y todo valor de `inputs`: **una sola línea** (sin `\n` ni `\r`), **≤ 200
  caracteres**, sin caracteres de control. Se emiten siempre por `yaml.safe_dump` del dict del
  paso (nunca por concatenación de strings), de modo que el quoting lo hace PyYAML.
- `anchor_ref` que no existe en `target_path` ⇒ error nombrando las refs que **sí** están
  (mensaje accionable, no "no encontrado").
- **El texto en lenguaje natural NUNCA se copia al YAML**, ni siquiera como comentario
  (herencia directa del Plan 243 C7).

**Renderizado del bloque nuevo:** se arma el dict del paso con la misma forma que
`pipeline_renderers.py:110 (_task_step_doc)` — claves en orden `task` → `displayName` →
`condition` → `inputs` — y se pasa por `render_block` de F0 con las columnas del anchor.

**Tests PRIMERO (10) — `backend/tests/test_plan250_verbos.py`:**

1. `test_add_step_al_final_de_ci_cd_online` — el plan devuelve **1** op `insert_after` sobre
   `steps[5]` y el YAML resultante parsea y contiene la nueva ref.
2. `test_add_step_antes_de_una_ref` — `position="before"`, `anchor_ref="PublishBuildArtifacts@1"`
   ⇒ la ref nueva queda entre `PublishTestResults@2` y `PublishBuildArtifacts@1`.
3. `test_remove_step_por_ref` — quitar `PublishTestResults@2` de `ci-cd-online.yml` borra **su**
   rango y deja los 47 comentarios menos los 2 propios de ese paso.
4. `test_move_step_reordena_sin_reescribir` — mover un paso produce exactamente 2 hunks y ninguna
   otra línea cambia.
5. `test_set_task_input_cambia_una_sola_linea` — cambiar `configuration` en `VSBuild@1` produce
   **1** hunk de **1** línea.
6. `test_add_stage_respeta_el_estilo_del_archivo` — en `cd-deploy-test.yml` (stages indentados a
   col 2) el stage nuevo sale con guion en col 2.
7. `test_tarea_fuera_del_catalogo_rechazada` — `task_ref="MSBuild@1"` ⇒ error, **0 ops**.
8. `test_input_invalido_rechazado` — `inputs={"msbuildArguments": "x"}` sobre `VSBuild@1` ⇒ error
   (el input real es `msbuildArgs`).
9. `test_display_name_multilinea_rechazado` — `display_name="a\nb"` ⇒ error, 0 ops.
10. `test_determinismo` — 2 corridas de `plan_edit` con el mismo intent ⇒ ops **idénticas**.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan250_verbos.py -q`
(+ registrar el archivo en las dos listas del ratchet).

**Criterio de aceptación (BINARIO):** 10/10 verdes **y** `tests/test_plan250_patcher.py` sigue en
12/12 (no regresión).

**Flag:** ninguna todavía.
**Impacto por runtime:** idéntico en los 3, sin LLM. **Fallback: no aplica.**
`Trabajo del operador: ninguno`

---

## F2 — Gates por DELTA (`pipeline_diff.py`): no ofrecer un patch que rompe

**Objetivo:** que un patch que introduce un error **no se ofrezca**, sin volver ineditables los
pipelines que hoy ya tienen hallazgos.

**Crear:** `backend/services/pipeline_diff.py`, `backend/tests/test_plan250_gates_delta.py`.
**Editar:** nada.

### La decisión sutil, por escrito: qué modo de regla se aplica al resultado de una edición

`check_semantics` (`cicd_semantic_rules.py:497`) tiene dos modos: `MODE_AUDIT` (`:43`) y
`MODE_NL_STRICT` (`:44`), y `RS004`/`RS006`/`RS008` sólo corren en el estricto (`:48`).

**Aplicar `MODE_NL_STRICT` al documento completo editado sería un error de diseño.** Prueba
concreta: `nightly-build-online.yml:111` tiene un `- script: |` crudo y real. Si el operador pide
"cambiale la configuración del build a Debug", el gate estricto sobre el documento entero
reportaría **RS008 error** sobre un paso que el operador no tocó, en un pipeline que corre en
producción desde siempre. El patch quedaría bloqueado por una falta ajena. El operador aprendería
en dos días a ignorar el semáforo — **que es el peor resultado posible para un gate**.

**Aplicar sólo `MODE_AUDIT` también sería un error**, por el lado opuesto: RS004 y RS008 existen
justamente para que **Stacky** no emita PowerShell inline ni tareas fuera del catálogo (Plan 243
C5/C7). Si Stacky escribe, Stacky se somete al estándar estricto.

**Decisión (se implementa así y se testea así):**

| Qué se evalúa | Modo | Qué bloquea |
|---|---|---|
| Documento completo **después** vs **antes** | `MODE_AUDIT` | Sólo los findings **nuevos** con severidad `error` (delta) |
| Los bloques que **el patch introdujo**, aislados en un documento sintético mínimo | `MODE_NL_STRICT` | **Cualquier** finding `error` |
| `lint_yaml(after, "ado")` vs `lint_yaml(before, "ado")` (`pipeline_lint.py:791`) | — | Sólo los findings **nuevos** con `SEV_ERROR` |

**El delta se calcula por identidad de finding, no por conteo**: dos findings son "el mismo" si
coinciden `(code, message)` **normalizando la parte posicional**, porque un paso insertado corre
la posición de todos los siguientes y un conteo ingenuo daría falsos positivos en masa.

> **C4 — BLOQUEANTE del v1, corregido acá.** El v1 daba **una sola** `_finding_key(code, message,
> location)`. **No compila contra los dataclasses reales**, verificado abriéndolos:
> `SemanticFinding` (`cicd_semantic_rules.py:63`) tiene `location: str` y **no** `line`;
> `LintFinding` (`pipeline_lint.py:33`) tiene `line: int|None` y `node: str|None` y **NO tiene
> `location`** ⇒ pasarle un `LintFinding` es un **`AttributeError`**. Y aunque se le pasara
> `str(f.line)`, `re.sub(r"\[\d+\]", "[]", ...)` **no normaliza un entero suelto**: insertar 8
> líneas convierte el finding de la línea 40 en el de la 48, y **todos** los findings posteriores
> al hunk se contarían como nuevos. Es decir: el v1 declaraba en R4 que mitigaba exactamente el
> falso positivo que su propio código habría producido, y su test 4 lo habría puesto rojo sin
> decir por qué. **Son dos claves distintas porque son dos formas distintas:**

```python
def _sem_key(f) -> tuple:
    """SemanticFinding: la posición es un PATH.
    `stages[1].jobs[0].steps[4]` → `stages[].jobs[].steps[]`."""
    return (f.code, f.message, re.sub(r"\[\d+\]", "[]", f.location or ""))

def _lint_key(f) -> tuple:
    """LintFinding: NO tiene `location`. Tiene `node` ("stage:Build", "var:MY_TOKEN"),
    que es ESTABLE ante una inserción, y `line`, que NO lo es.
    REGLA DURA: `f.line` NUNCA entra en la clave. Si `node` es None, la identidad
    queda (code, message) y punto: perder granularidad es infinitamente preferible
    a inventar 30 findings nuevos que no lo son."""
    return (f.code, f.message, f.node or "")
```

```python
DIFF_VERSION = "250.1"

@dataclass(frozen=True)
class GateDelta:
    gate: str            # "LINT" | "SEM_AUDIT" | "SEM_NL_STRICT"
    passed: bool
    new_errors: tuple    # findings NUEVOS con severidad error
    new_warnings: tuple
    resolved: tuple      # findings que el patch HIZO DESAPARECER (se muestran: es valor)
    skipped_reason: str  # "" si corrió

@dataclass(frozen=True)
class EditReview:
    ok: bool             # True ⇔ ningún gate con new_errors Y preservation.ok
    gates: tuple
    hunks: tuple
    summary: str         # español, derivado (NO redactado por un LLM)
    unsupported: tuple   # scan_unsupported(after) — se informa, no bloquea
    preservation: "Preservation"   # [ADICIÓN ARQUITECTO] — ver abajo

def review_patch(before: str, after: str, hunks: tuple, *, profile: str,
                 repo_root: str|None = None) -> EditReview
```

### [ADICIÓN ARQUITECTO] Sello de preservación: el invariante deja de vivir sólo en los tests

El v1 tenía un problema silencioso: **el invariante que justifica el plan entero — "no se pierde
nada" — sólo se comprueba en `test_los_337_comentarios_del_corpus_sobreviven`, que el operador
nunca ve.** El día que una `EditOp` nueva rompa la preservación sobre un archivo que no está en el
corpus, el operador se entera **después**, leyendo su repo. Eso es exactamente el fracaso que el §0
promete evitar, movido un escalón más adelante.

Se calcula sobre `(before, after)` **con lo que ya existe** —el conteo de líneas-comentario que los
tests de F0 ya hacen y `scan_unsupported` (`pipeline_renderers.py:51`)— y se devuelve en cada
`/plan`:

```python
@dataclass(frozen=True)
class Preservation:
    ok: bool                  # False si se perdió un comentario o una construcción no modelada
    comments_before: int
    comments_after: int
    unsupported_lost: tuple   # construcciones que estaban y ya no
    lines_untouched: int      # líneas byte-idénticas entre before y after
    lines_total_before: int
```

**Es un GATE, no un adorno**: `G-PRESERVACION` es el cuarto gate y **bloquea igual que los otros**
(`comments_after < comments_before` ⇒ `ok=False`), con **una sola excepción legítima y acotada**:
el verbo `remove_step`, donde los comentarios que vivían *dentro del rango del paso borrado* se van
con él a propósito. En ese caso el gate compara contra
`comments_before − comentarios_dentro_del_rango_borrado` y, si sobra alguno, **avisa cuáles**.

La UI lo muestra en **una línea** al lado del semáforo, antes del botón:

> *"Se preservan 47/47 comentarios y 0 construcciones no modeladas; 119 de 127 líneas quedan
> byte-idénticas."*

**Por qué es alto valor y no cuesta nada:** convierte el KPI-1 en evidencia **en el momento de
decidir** en vez de en un test que corre en otra máquina; reusa código existente; es puro (sin LLM,
sin red) ⇒ **idéntico en los 3 runtimes**; no agrega ni un paso al operador (aparece solo); y es la
única defensa que funciona sobre los pipelines del operador que **no** están en el corpus dorado —
que son todos los que le importan.

**Reglas duras:**
- **`resolved` se muestra**: si el patch arregla algo (por ejemplo agrega el `PublishBuildArtifacts@1`
  que faltaba), el operador tiene que verlo. Un gate que sólo sabe decir "no" enseña a ignorarlo.
- **`unsupported` nunca bloquea**: es informativo (misma doctrina que el espejo de corpus del
  243 F3.5, que es `info` y no puede cambiar el estado).
- **`repo_root is None` ⇒ RS006 no se evalúa** y el gate lo declara en `skipped_reason`;
  **jamás se reporta como "validado"** (herencia del 243 §4).
- Si `after` no parsea ⇒ `ok=False` con el error de PL001. El patch no se ofrece.

**Tests PRIMERO (9) — `backend/tests/test_plan250_gates_delta.py`:**

1. `test_error_preexistente_no_bloquea_la_edicion` — editar `nightly-build-online.yml` (que tiene
   el `- script: |` de `:111`) con un `set_task_input` inocuo ⇒ `ok is True`. **Es el test que
   impide que el gate se vuelva inútil por estricto.**
2. `test_patch_que_introduce_error_nuevo_no_se_ofrece` — **KPI-3.** Un patch que agrega
   `IISWebAppDeploymentOnMachineGroup@0` en un stage con `pool: vmImage:` ⇒ `ok is False` con
   **RS002** en `new_errors`. *Es ADO-369 detectado en la ruta de edición.*
3. `test_paso_insertado_se_evalua_en_nl_strict` — un patch que inserta `PowerShell@2` con
   `inputs.script` inline ⇒ **RS004 error**, aunque el documento completo en `audit` no lo marque.
4. `test_indices_desplazados_no_cuentan_como_nuevos` — insertar un paso al principio de un job de
   6 pasos **no** produce ningún `new_error` ni `new_warning` por corrimiento de índices.
5. `test_findings_resueltos_se_reportan` — un patch que elimina la causa de un finding lo lista en
   `resolved`.
6. `test_lint_delta_solo_reporta_lo_nuevo` — un YAML con un `SEV_ERROR` de lint preexistente sigue
   siendo editable.
7. `test_sin_repo_root_rs006_se_declara_skipped` — `repo_root=None` ⇒ `skipped_reason` no vacío y
   **nunca** `passed` por omisión.
8. `test_after_no_parsea_bloquea` — `after` corrupto ⇒ `ok is False`.
9. `test_unsupported_se_informa_y_no_bloquea` — editar `ci-batch.yml` (que tiene `matrix:` en
   `:60`) ⇒ `unsupported` contiene `"matrix"` y `ok is True`.
10. `test_lint_delta_no_usa_line_como_identidad` — **C4.** Insertar un paso al principio de un job
    y afirmar que `_lint_key` de un finding preexistente es **igual** antes y después, aunque su
    `f.line` haya cambiado. Y que `_lint_key(LintFinding(...))` **no lanza `AttributeError`**
    (el v1 le habría pedido `.location`, que ese dataclass no tiene).
11. `test_gate_preservacion_bloquea_si_desaparece_un_comentario` — **[ADICIÓN ARQUITECTO].** Con
    una `EditOp` fabricada a mano que pisa un rango con comentarios ⇒ `preservation.ok is False`
    y `review.ok is False`.
12. `test_remove_step_no_dispara_falso_positivo_de_preservacion` — la excepción acotada:
    `remove_step` de `PublishTestResults@2` en `ci-cd-online.yml` ⇒ `preservation.ok is True`
    (los 2 comentarios propios del paso se van con él, y **sólo** esos).

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan250_gates_delta.py -q`
(+ las dos listas del ratchet).

**Criterio de aceptación (BINARIO):** **12/12** verdes, en particular 1, 2, 3, 4, 10 y 11. Además,
sin regresión: `.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q`
verde.

**Flag:** ninguna todavía.
**Impacto por runtime:** idéntico en los 3, sin LLM. **Fallback: no aplica.**
`Trabajo del operador: ninguno`

---

## F3 — Blueprint `api/pipeline_editor.py` + commit HITL + flags

**Objetivo:** exponer el motor con el mismo ritual de confirmación que ya existe, y dejar las dos
flags configurables **desde la UI**.

**Crear:** `backend/api/pipeline_editor.py`, `backend/tests/test_plan250_api.py`,
`backend/tests/test_plan250_flag.py`.
**Editar:** `backend/api/__init__.py` (importar y registrar el blueprint, patrón de `:44` y `:77+`),
`backend/services/harness_flags.py`, `backend/config.py`,
`backend/tests/test_harness_flags.py:467 (_CURATED_DEFAULTS_ON)`.

```python
"""api/pipeline_editor.py — Blueprint edición quirúrgica de pipelines existentes. Plan 250 F3."""
from __future__ import annotations
import config as _config
from flask import Blueprint, abort, jsonify, request

# url_prefix="/pipeline-editor" → ruta final /api/pipeline-editor/...
# NO "/api/pipeline-editor" (daría /api/api/...) y NO registrar en app.py.
bp = Blueprint("pipeline_editor", __name__, url_prefix="/pipeline-editor")
```

| Método | Ruta | Cuerpo | Devuelve |
|---|---|---|---|
| POST | `/plan` | `{yaml, intent, profile, repo_root?}` | `{ops, hunks, review, before_sha256, after_sha256}` — **no escribe nada** |
| POST | `/commit` | `{project, path, branch, message, intent, profile, before_sha256, approved_after_sha256, confirm}` | resultado de `commit_file` |
| GET | `/verbs` | — | `{verbs: EDIT_VERBS, catalog: {ref: [inputs...]}}` para el formulario de F4 |

**Guard de flag PER-REQUEST** en cada handler (nunca en el registro del blueprint):

```python
if not getattr(_config.config, "STACKY_PIPELINE_NL_EDIT_ENABLED", False):
    abort(404)
```

> **Gotcha dura del dossier §3:** el consumidor lee **la instancia** (`_config.config`), no el
> módulo. `getattr` del módulo devuelve el default y **mata el branch OFF** (el test flag-off
> pasaría en falso).

**Candados de `/commit`, en este orden exacto** (re-especificados en v2 por C3 y C9):

0. **`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (flag PROPIA, default OFF)** ⇒ si está OFF, **404**.
   Los otros 3 endpoints siguen vivos con la flag de análisis en ON: **se puede ver el diff sin
   poder pushear**, que es exactamente el default seguro que se busca (§3, C2).
1. `body.get("confirm") is not True` ⇒ **400** `{"error": "confirm=True requerido (HITL)"}`
   — literal copiado de `pipeline_generator.py:59-60`.
2. `branch` vacío ⇒ **400**. `branch == _default_branch(None, project)`
   (`ado_pipeline_definitions.py:64`) ⇒ **400**. **Nunca se commitea sobre la rama por defecto.**
   Si `_default_branch` lanza (red/auth), ⇒ **400** con su mensaje: **no se sigue**; no poder
   saber cuál es la rama por defecto no habilita a escribir en ella.
3. **Auto-consistencia del `before`** (C3 — el v1 pedía releer el archivo, y **el puerto no sabe
   leer**, §2.8): se rehashea el `before` recibido y se compara con `before_sha256`; si difiere ⇒
   **400** (request incoherente). La respuesta **siempre** incluye
   `"stale_check": "no_verificable"` con el motivo literal *"el puerto RepoWriter no expone
   lectura; si el archivo cambió en el repo desde que viste el diff, Stacky no puede saberlo — el
   push contra `old_object_id` lo rechazaría ADO"*. **Jamás se reporta como validado.**
4. Se **recompila el patch en el servidor** desde `intent` (F1) y se aplica (F0). Si el sha256 del
   resultado ≠ `approved_after_sha256` ⇒ **409** con el diff nuevo.
   **El servidor NUNCA acepta el YAML final que manda el cliente.**
5. `review_patch(...)` (F2). Si `ok is False` ⇒ **422** con los `new_errors` **y** con
   `preservation` (si lo que falló fue el gate de preservación, el operador tiene que ver
   **qué se perdía**, no un "no").
6. `get_repo_writer(project)` (`repo_writer.py:30`) **dentro de su propio `try`**: lanza
   **`RuntimeError`** si el provider activo no implementa el puerto (`:37-41`) ⇒ **400** con el
   mensaje, igual que hace el precedente en `pipeline_generator.py:71-73` (C9). **Sin este `try`
   es un 500 mudo.**
7. Recién ahí: `writer.commit_file(path=path, content=after, branch=branch, message=message)`
   (`repo_writer.py:17`). En ADO esto **empuja de verdad** (`ado_provider.py:146`), crea la rama
   desde la default si no existe (`:168-191`) y devuelve `status='unchanged'` sin pushear si el
   contenido ya era idéntico (`:199-221`) — ese `unchanged` **se muestra tal cual**, nunca como
   "commiteado".
8. `TrackerApiError` ⇒ su `status` real (patrón de `pipeline_generator.py:83-85`).
   `NotImplementedError` ⇒ **501** con `{"yaml": after, "hunks": [...]}` intactos: la UI ofrece
   copiar el YAML parcheado. **Nunca se presenta como "commiteado".** *Nota v2: este camino
   **ya no es el de ADO** (§2.7 del v1 estaba mal); queda para cualquier otro provider que no
   implemente escritura.*

**Flags** (`services/harness_flags.py`, patrón de `:21 (FlagSpec)`):

```python
FlagSpec(
    key="STACKY_PIPELINE_NL_EDIT_ENABLED",
    type="bool",
    default=True,   # default ON: ninguna de las 4 excepciones duras aplica (§3);
                    # curada en _CURATED_DEFAULTS_ON (test_harness_flags.py:467)
    label="Edición de pipelines en lenguaje natural",
    description=(
        "Plan 250 - Modificar una pipeline existente describiendo el cambio; patch "
        "quirúrgico con diff visible y commit con confirmación. OFF: desaparece el panel "
        "de edición y sus 3 endpoints dan 404; el builder gráfico queda IDÉNTICO a hoy."
    ),
    group="global",
),
FlagSpec(
    key="STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED",
    type="bool",
    default=False,  # C2 — EXCEPCION DURA (2): esta es la unica ruta que ESCRIBE en un
                    # sistema externo real del operador (push a su Azure DevOps via
                    # ado_provider.commit_file). Al ser default OFF, NO va en
                    # _CURATED_DEFAULTS_ON y por eso tampoco declara default=True.
    label="Permitir commitear la pipeline editada",
    description=(
        "Plan 250 - Habilita SOLO el commit del YAML parcheado a una rama del repo real. "
        "Ver el cambio y el diff NO necesita esta flag. OFF: el boton de commit explica "
        "como activarla y ofrece copiar el YAML; los otros 3 endpoints siguen funcionando."
    ),
    group="global",
    requires="STACKY_PIPELINE_NL_EDIT_ENABLED",
),
```

> **C6 — la flag `STACKY_PIPELINE_NL_EDIT_MAX_LLM_CALLS` del v1 se ELIMINA.** Era una flag **sin
> consumidor**: el diseño hace exactamente 1 llamada y prohíbe los reintentos (§F5), así que
> ponerla en 2 o 3 no cambiaba nada — y su `max_value=3` **invitaba explícitamente** al bucle de
> auto-reparación que el propio plan declara prohibido citando el C10 del 243. La casa ya tiene el
> mecanismo para flags sin consumidor (`FlagSpec.reserved`, `harness_flags.py:40`, Plan 85), pero
> acá ni eso hace falta: **el techo es una constante del módulo**,
> `MAX_LLM_CALLS_PER_REQUEST = 1` en `api/pipeline_editor.py`. Menos superficie, misma garantía,
> y el KPI-5 se sigue probando igual (test 5 de F5).

> **Gotchas obligatorias:** (a) una `FlagSpec` con `default=True` **debe** estar además en
> `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`) o
> `test_default_known_only_for_curated` se pone rojo; (b) toda flag nueva necesita su entrada en
> `_CATEGORY_KEYS` (`services/harness_flags.py`) o el meta-test de categorización falla; (c)
> `requires` es **informativo para la UI — ningún runner lo evalúa** (`harness_flags.py:30-32`),
> así que F5 **debe** chequear `STACKY_PIPELINE_NL_EDIT_ENABLED` por su cuenta.

**Tests PRIMERO (8 + 4):**

`backend/tests/test_plan250_api.py` (**11**):
1. `test_endpoints_404_con_flag_off` — los 4 endpoints con `STACKY_PIPELINE_NL_EDIT_ENABLED` OFF.
2. `test_plan_devuelve_hunks_y_review` — 200 con `hunks` no vacío.
3. `test_plan_no_escribe_nada` — el fixture en disco queda byte-idéntico tras `/plan`.
4. `test_commit_sin_confirm_es_400` — **KPI-4.**
5. `test_commit_sobre_rama_default_es_400`.
6. `test_commit_con_before_sha_incoherente_es_400` — C3: el `before` recibido no hashea a
   `before_sha256`.
7. `test_commit_ignora_el_yaml_del_cliente` — se manda un `yaml` malicioso en el body y se afirma
   que lo commiteado es el recompilado del servidor.
8. `test_commit_con_review_en_rojo_es_422`.
9. `test_commit_404_con_flag_de_commit_off` — **C2, el candado 0.** Con
   `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` OFF: `/commit` da **404** y `/plan` sigue dando
   **200**. *Es el test que prueba que el default de fábrica ve pero no escribe.*
10. `test_stale_check_se_declara_no_verificable` — C3: toda respuesta de `/commit` trae
    `stale_check == "no_verificable"`; **ninguna** dice que se validó contra el repo.
11. `test_provider_sin_repo_writer_es_400` — C9: `get_repo_writer` que lanza `RuntimeError` ⇒
    **400** con el mensaje, **no** 500.

`backend/tests/test_plan250_flag.py` (**4**):
1. Las **dos** flags aparecen en el catálogo que consume la UI y son editables desde ahí.
2. `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` **NO** está en `_CURATED_DEFAULTS_ON`
   (`test_harness_flags.py:467`) — es la contracara de ser default OFF.
3. `test_default_known_only_for_curated` verde (`STACKY_PIPELINE_NL_EDIT_ENABLED` **sí** curada).
4. Las **dos** flags tienen categoría en `_CATEGORY_KEYS` (`harness_flags.py:120`).

> **Verificado por la crítica v2 (para que nadie pierda una tarde buscándolos):** en este árbol
> **NO existen** `_REQUIRES_MAP_FROZEN` ni `_FROZEN_BOUNDS` (`grep -rn` sobre `backend/` ⇒ 0
> hits). El `requires` de `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` **no necesita** registrarse en
> ningún mapa congelado; es un campo informativo de la `FlagSpec` (`harness_flags.py:30-32`) y
> **ningún runner lo evalúa** ⇒ el candado 0 de F3 chequea la flag **por su cuenta**.

**Comandos:**
```powershell
.venv\Scripts\python.exe -m pytest tests/test_plan250_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
```
> **Rojo ajeno conocido (dossier §4):** `test_harness_flags_help` tiene **4 fallos preexistentes
> que NO son tuyos**. Validá tus 4 tests de forma aislada; no "arregles" los ajenos.

**Criterio de aceptación (BINARIO):** **15/15** verdes (11+4), ratchet meta verde con los 5
archivos de test registrados en **las dos** listas, y `tests/test_plan73_generator_endpoint.py`
verde (prueba de que `pipeline_generator.py` no se tocó).

**Flags:** `STACKY_PIPELINE_NL_EDIT_ENABLED` default **ON** (analizar/diff) +
`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` default **OFF** (escribir).
**Impacto por runtime:** idéntico en los 3 — el blueprint no invoca LLM.
**Fallback:** flag de análisis OFF ⇒ 404 en los 4 endpoints y el panel no se renderiza. Flag de
commit OFF (**el default**) ⇒ todo funciona menos el push, y el botón **explica cómo activarlo**.
En los dos casos el builder gráfico queda **exactamente como hoy**.
`Trabajo del operador: análisis sin trabajo (ON); el commit exige UN clic consciente, una vez`

---

## F4 — Panel de edición con diff (sin LLM todavía): la feature ya sirve acá

**Objetivo:** que el operador edite una pipeline existente por **controles estructurados**, vea el
diff y commitee — todo sin modelo. Si la corrida de implementación muere después de esta fase,
**la feature está completa y es útil**.

**Crear:** `frontend/src/devops/pipelineEditModel.ts` (**modelo PURO, toda la lógica testeable**),
`frontend/src/devops/__tests__/pipelineEditModel.test.ts`,
`frontend/src/components/devops/PipelineEditNlPanel.tsx`,
`frontend/src/components/devops/PipelineEditNlPanel.module.css`.
**Editar:** `frontend/src/api/endpoints.ts` (objeto `PipelineEditor` con `plan`, `commit`,
`verbs`, `interpret`), `frontend/src/pages/DevOpsPage.tsx`, `backend/api/devops.py`.

> **C1 — corrección del montaje (BLOQUEANTE en v1).** El v1 decía *"Editar
> `PipelineBuilderSection.tsx` (montar el panel)"*. Ese archivo **no está reservado al 250**
> (§3.1), es territorio de los planes 87/106/243/244, tiene 852 líneas y está **custodiado por
> guardias de contenido literal** que lo leen con `readFileSync`
> (`frontend/src/components/devops/__tests__/PipelineBuilderSection.test.ts:44-118`). No se toca.

**Montaje correcto, literal (las dos superficies SON del 250):**

1. `backend/api/devops.py` — publicar la llave de salud, con el patrón exacto de `:42`:
   ```python
   "pipeline_nl_edit_enabled": bool(getattr(cfg, "STACKY_PIPELINE_NL_EDIT_ENABLED", False)),
   "pipeline_nl_edit_commit_enabled": bool(getattr(cfg, "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED", False)),
   ```
2. `frontend/src/pages/DevOpsPage.tsx:113 (DEVOPS_SECTIONS)` — **una entrada nueva**, en el punto
   de extensión que la casa documenta en `:112` (*"features futuras agregan entradas aquí SIN
   refactor"*), con el mismo gate declarativo que ya usan Publicaciones y Ambientes (`:79-81`):
   ```tsx
   {
     id: 'editar-pipeline',
     label: 'Editar pipeline',
     group: 'construir',
     healthKey: 'pipeline_nl_edit_enabled',
     gateFlagKey: 'STACKY_PIPELINE_NL_EDIT_ENABLED',
     gateMessage: 'La edición de pipelines existentes necesita la flag STACKY_PIPELINE_NL_EDIT_ENABLED (Configuración → Arnés).',
     render: (ctx) => <PipelineEditNlPanel ctx={ctx} />,
   },
   ```
   **El gate de flag-off lo hace el shell**, no el componente — el panel **no hand-rollea** su
   propio banner (misma nota que llevan `PublicationsSection.tsx:7` y `ServersSection.tsx:9`).

### C5 — De dónde sale el YAML: el contrato de entrada que el v1 no tenía

El v1 declaraba que *"al terminar F4 la feature está completa y usable"* pero **nunca dijo cómo
entra el pipeline al panel**. El §6 delega el descubrimiento en el **Plan 246**, que **no está
implementado** (verificado: `services/pipeline_patcher.py` y toda la serie 246-252 no existen aún).
Sin entrada, el punto de corte seguro era falso. Se cierra con un contrato de **dos vías**, y la
segunda **no depende de ningún otro plan**:

| Vía | Requisito | Estado hoy |
|---|---|---|
| **A — Pegar** (siempre disponible) | Un `<textarea>` "Pegá el YAML de la pipeline" + un campo "Ruta en el repo" (p. ej. `pipelines/ci-cd-online.yml`, usada tal cual en `/commit`) | **Es la vía que se implementa en F4.** Cero dependencias |
| **B — Elegir de la lista** | El registro del Plan 246 | **Cuando el 246 exista.** F4 deja el hueco: si `verbs.discovery_available` es `false`, la vía B **no se muestra** y no hay error |

`EditFormState` gana por lo tanto dos campos: `beforeYaml: string` y `repoPath: string`, y
`isPlanRequestReady` exige **los dos** no vacíos además de lo del verbo.

```ts
// frontend/src/devops/pipelineEditModel.ts — PURO, sin React, sin fetch
export const MAX_EDIT_LINES = 3000;   // espejo de lineDiff.ts:12 (MAX_LINES)

export interface EditFormState { verb: string; targetPath: string; anchorRef: string|null;
  position: 'before'|'after'|'end'; taskRef: string|null; inputs: Record<string,string>;
  displayName: string; }

/** Habilita "Ver diff" sólo si el formulario está completo para ese verbo. */
export function isPlanRequestReady(s: EditFormState): boolean

/** Resumen en español del cambio, DERIVADO de los hunks (nunca redactado por un LLM). */
export function summarizeHunks(hunks: Hunk[]): string

/** Contrato Plan 106 F5 (PipelineBuilderSection.tsx:382-383): PRE-RELLENA sólo lo vacío.
 *  Nunca pisa un campo que el operador ya escribió. */
export function prefillOnlyEmpty(current: EditFormState, suggested: Partial<EditFormState>): EditFormState

/** Gate de tamaño: por encima del cap no se pide diff (se ofrece el YAML crudo). */
export function canRenderDiff(before: string, after: string): boolean
```

**Contrato de UI (no negociable):**

- **El diff se muestra SIEMPRE antes de cualquier escritura.** Se renderiza con
  `buildDiffLines(before, after)` de `frontend/src/components/devops/pipelineLint.ts:91`
  (`DiffRow` en `:79`) — **el mismo componente visual que ya usa `PipelineLintPanel.tsx:190`**
  para previsualizar autofixes. **No se escribe ni una línea de código de diff nuevo.**
- Junto al diff completo se listan los **hunks** con su `reason`, para que el operador vea
  **qué op causó qué cambio** y no tenga que deducirlo de un LCS.
- El botón de commit repite el ritual de `CommitPipelineModal.tsx:41,145,163`: checkbox de
  confirmación obligatorio, botón deshabilitado sin él.
- El semáforo muestra `new_errors` (bloquean el commit), `new_warnings` (no bloquean) y
  **`resolved`** (lo que el patch arregla).
- Si `review.ok is false`, el botón de commit está deshabilitado **y el diff se muestra igual**:
  el operador tiene derecho a ver lo que Stacky se negó a ofrecerle.
- **Gotcha de la casa:** en un `.tsx` **nuevo** el `uiDebtRatchet` tiene alcance 0 ⇒ **cero
  `style={{...}}` inline**, todo al `.module.css`.

**Tests PRIMERO (8) — `frontend/src/devops/__tests__/pipelineEditModel.test.ts`:**

1. `isPlanRequestReady` es `false` sin `taskRef` para `add_step`, `true` con él.
2. `isPlanRequestReady` no exige `taskRef` para `remove_step`.
3. `prefillOnlyEmpty` **no pisa** un `displayName` que ya tiene texto.
4. `prefillOnlyEmpty` **sí** rellena un `displayName` vacío.
5. `summarizeHunks` con 1 hunk de inserción dice "1 bloque agregado" y con 0 hunks dice
   "sin cambios".
6. `canRenderDiff` es `false` por encima de `MAX_EDIT_LINES`. **Es obligatorio**: `buildDiffLines`
   (`pipelineLint.ts:91`) arma una matriz LCS `O(n·m)` **sin cap propio** (`:94-96`), a diferencia
   de `lineDiff.ts:22`, que devuelve `null` por encima de `MAX_LINES` (`:12`).
7. `summarizeHunks` es puro: 2 llamadas ⇒ el mismo string.
8. El estado inicial del formulario no habilita el commit.
9. **C5.** `isPlanRequestReady` es `false` con `beforeYaml` vacío y `false` con `repoPath` vacío,
   aunque el resto del formulario esté completo.
10. **C2.** `canCommit(state, health)` es `false` cuando `health.pipeline_nl_edit_commit_enabled`
    es `false`, **aunque** `review.ok` sea `true` y el checkbox esté marcado; y el modelo devuelve
    el motivo `'flag_commit_off'` para que la UI muestre cómo activarla en vez de un botón muerto.
11. **[ADICIÓN ARQUITECTO].** `formatPreservation(p)` con `47/47` y `0` perdidas devuelve la línea
    en español esperada; con una construcción perdida el string **nombra cuál**.

> **No hay tests de render:** `@testing-library/react` y `jsdom` **no están instalados** en este
> frontend. Por eso **toda la lógica vive en el modelo puro** y el `.tsx` es sólo cableado. El
> gate real del componente es `npx tsc --noEmit` + el smoke visual del operador.

**Comandos:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineEditModel.test.ts
npx tsc --noEmit
```
> `npm test` **falla**: no hay script `test` en `package.json`. Se usa `npx vitest`.

**Criterio de aceptación (BINARIO):** **11/11** verdes, `npx tsc --noEmit` sin errores nuevos, el
ratchet de deuda de UI **no crece**, y `npx vitest run
src/components/devops/__tests__/PipelineBuilderSection.test.ts` **sigue verde** (prueba de que no
se tocó el archivo ajeno, C1).

**Flag:** `STACKY_PIPELINE_NL_EDIT_ENABLED` — el gate lo aplica el shell por `healthKey`
(`DevOpsPage.tsx:79-81`), **no el componente**.
**Impacto por runtime:** idéntico en los 3 — el panel no llama a ningún modelo en esta fase.
**Fallback:** flag OFF ⇒ la sección muestra el `FlagGateBanner` estándar y
`PipelineBuilderSection` queda **idéntico a hoy** (ni siquiera se importa desde el panel nuevo).
`Trabajo del operador: opt-in, default ON (ver y diffear); el commit, aparte y OFF`

---

## F5 — La puerta de entrada en lenguaje natural (única llamada LLM) + puente con el 248

**Objetivo:** que el operador escriba *"agregale un stage de tests antes del deploy"* y eso se
convierta en **un `EditIntent` validado**, que entra por el mismo camino de F1→F0→F2→F4.

> **C1 — el v1 creaba `backend/services/pipeline_edit_intent.py`, que NO está reservado al 250**
> (§3.1). Se parte en dos, **sin perder nada**, entre las superficies que sí lo están:
>
> | Qué | Dónde va en v2 | Por qué ahí |
> |---|---|---|
> | `INTENT_SCHEMA`, `validate_intent_dict(d, *, profile) -> (EditIntent\|None, errores)` — **puro, sin red, sin LLM** | `backend/services/pipeline_patcher.py` | Es la contracara exacta de `EDIT_VERBS`, que **ya vive ahí** (F1), y comparte el catálogo y el índice de anclajes |
> | `PROMPT_TYPE`, armado del prompt, `interpret_edit(...)`, `recommendation_to_intent(...)`, `MAX_LLM_CALLS_PER_REQUEST = 1` | `backend/api/pipeline_editor.py` | Es el **único caller**; el adaptador de LLM vive con su endpoint |
>
> *Si se prefiere el módulo separado, primero se agrega a la reserva §0.3 del 246; nunca al revés.*

**Crear:** `backend/tests/test_plan250_edit_intent.py`,
`backend/tests/fixtures/pipeline_edit/intents/*.json` (**≥6**).
**Editar:** `backend/services/pipeline_patcher.py` (esquema + validación pura),
`backend/api/pipeline_editor.py` (endpoint `POST /interpret` + la llamada al LLM),
`frontend/src/components/devops/PipelineEditNlPanel.tsx` (caja de texto),
`frontend/src/devops/pipelineEditModel.ts` (sin lógica nueva de negocio: sólo el estado de la caja).

```python
# services/pipeline_patcher.py — PURO
INTENT_SCHEMA: dict          # cerrado; verbo ∈ EDIT_VERBS, task_ref ∈ catálogo del perfil
def validate_intent_dict(d: dict, *, profile: str) -> tuple:
    """→ (EditIntent|None, errores). Sin red, sin LLM, sin I/O. Nunca lanza."""

# api/pipeline_editor.py — adaptador
PROMPT_TYPE = "pipeline_edit_intent_v1"
MAX_LLM_CALLS_PER_REQUEST = 1    # C6: constante, NO flag. Sin reintentos, nunca.

def interpret_edit(text: str, *, yaml_text: str, profile: str,
                   fixture_id: str|None = None) -> tuple:
    """→ (EditIntent|None, preguntas). UNA sola llamada a call_llm. Nunca lanza."""
```

**El LLM NO escribe YAML. Nunca. Bajo ninguna condición.** Recibe:

1. la lista literal de `EDIT_VERBS` (7),
2. **el índice de anclajes** de F0 (los `path` disponibles) y **la espina de tareas**
   (`extract_task_refs`, `cicd_task_catalog.py:287`) — **no el YAML completo**: es más chico, más
   barato y no expone los comentarios ni los valores del archivo al modelo,
3. el catálogo del perfil como **referencia cerrada** (`is_allowed`, `validate_inputs`).

Y devuelve **un JSON de `EditIntent`**, con `LLMCallSpec` (`pm_llm_client.py:90`):
`expect_json=True` (`:101`), `temperature=0.0` (`:98`), `prompt_type=PROMPT_TYPE`,
`fixture_id` pasante (`:99`).

**Ambigüedad explícita — no adivina:** si no puede resolver el `target_path`, o el pedido no cae
en ninguno de los 7 verbos, devuelve `(None, (preguntas,))` **nombrando el dato que falta**. Las
`notes` (supuestos asumidos) **se muestran siempre**, antes del diff.

### Techo de costo y de reintentos (numérico y duro)

- **Máximo 1 llamada LLM por pedido**, y es **`MAX_LLM_CALLS_PER_REQUEST = 1`, una constante del
  módulo, no una flag** (C6). El v1 la había hecho configurable hasta 3 — una perilla **sin
  consumidor** que sólo servía para habilitar el bucle de reintentos que el propio plan prohíbe.
  El techo no se negocia desde la UI.
- **Cero reintentos automáticos.** Si el JSON no valida contra `INTENT_SCHEMA`, o el `task_ref`
  no está en el catálogo, **se devuelve la pregunta al operador**; no se reinvoca al modelo.
  *Justificación explícita: el 243 documentó en su C10 que el bucle de auto-reparación sin techo
  es una fuga. Con el operador mirando la pantalla, preguntarle cuesta 0 tokens y acierta más.*
- **Máximo 12 `EditOp` por plan** (`MAX_OPS_PER_PLAN`, F0). Un pedido que requiera más se rechaza
  con "partilo en dos ediciones".
- El texto NL **no se persiste** en ningún lado; **no se copia al YAML** ni como comentario.

### Determinismo (declarado con su mitigación)

| Tramo | ¿Determinista? | Mitigación |
|---|---|---|
| `EditIntent` → `EditPlan` → texto parcheado (F1+F0) | **SÍ, byte por byte** | `test_determinismo` (F1) |
| NL → `EditIntent` (F5) | **NO garantizado** entre versiones de modelo, aun con `temperature=0.0` | (a) el `EditIntent` **se muestra al operador antes del diff**, en castellano y campo por campo; (b) los tests usan `fixture_id` ⇒ **cero red**; (c) el `EditIntent` es chico y cerrado: dos interpretaciones distintas producen dos intents visiblemente distintos, no dos YAML sutilmente distintos |

**Este es el punto entero del diseño:** el no determinismo se concentra en una estructura de 8
campos que el operador lee de un vistazo, en vez de repartirse por 130 líneas de YAML.

### Fallback explícito por runtime (obligatorio)

| Runtime | Camino normal | Fallback si no hay LLM disponible |
|---|---|---|
| **Codex CLI** | `call_llm` con el backend configurado | La caja NL muestra el error de `call_llm` (`success=False`, `pm_llm_client.py:281-283`) y **el formulario de verbos de F4 sigue 100 % operativo** |
| **Claude Code CLI** | ídem | ídem |
| **GitHub Copilot Pro** | ídem (`_call_copilot`) | ídem |

**La respuesta a "¿y si el runtime no tiene LLM?" no es "no anda": es "andá por el formulario".**
F0–F4 no dependen de ningún modelo, así que la capacidad de editar quirúrgicamente **nunca se
pierde**; lo único que se pierde es escribir el pedido en prosa. Eso se dice en la UI con esas
palabras, no se oculta.

### Puente con el Plan 248 (recomendaciones `OPT*`) — degradación declarada

```python
def recommendation_to_intent(rec_id: str, yaml_text: str, *, profile: str):
    """Si el 248 está implementado, traduce una recomendación OPT* a un EditIntent.
    Import BLANDO: si services/pipeline_recommendations.py no existe, devuelve
    (None, ("el módulo de recomendaciones (plan 248) no está instalado",)).
    NUNCA lanza ImportError."""
    try:
        from services.pipeline_recommendations import get_recommendation
    except ImportError:
        return None, ("...",)
```

El endpoint `/verbs` devuelve `{"recommendations_available": bool}`; la UI muestra el botón
**"Aplicar esta recomendación"** sólo si es `true`. **Si el 248 no está, no hay botón y no hay
error**: la edición NL pura funciona igual. Verificado en §2.7: hoy ese módulo **no existe**.

**Tests PRIMERO (9) — `backend/tests/test_plan250_edit_intent.py` (todos con `fixture_id`, sin red):**

1. `test_seis_fixtures_producen_el_intent_esperado` — los 6 JSON de
   `backend/tests/fixtures/pipeline_edit/intents/` → `EditIntent` esperado, campo por campo.
2. `test_pedido_ambiguo_devuelve_preguntas` — *"mejorá esto"* ⇒ `(None, (preguntas,))` nombrando
   el dato faltante.
3. `test_verbo_fuera_de_la_lista_rechazado` — el modelo devuelve `verb="delete_pipeline"` ⇒
   `(None, ...)`, **0 ops**.
4. `test_tarea_alucinada_rechazada` — `task_ref="VSBuild@2"` ⇒ rechazo (no está en el catálogo).
5. `test_una_sola_llamada_llm_por_pedido` — **KPI-5.** Con un doble de `call_llm` que cuenta
   invocaciones: **exactamente 1**, incluso cuando el JSON devuelto es inválido.
6. `test_no_lanza_si_call_llm_falla` — `success=False` ⇒ `(None, (mensaje,))`, sin excepción.
7. `test_el_texto_nl_no_llega_al_yaml` — se pide una edición con un texto que contiene
   `# hackme` y `$(malicious)`, y se afirma que **ninguna de esas cadenas aparece** en el YAML
   resultante.
8. `test_recomendacion_sin_plan_248_degrada` — `recommendation_to_intent` con el módulo ausente ⇒
   `(None, (mensaje,))`, **sin `ImportError`**.
9. `test_intent_se_muestra_antes_del_diff` — el endpoint `/interpret` devuelve `intent` **y**
   `notes`, y **no** devuelve `yaml` ni `hunks` (el diff exige el paso `/plan` aparte, que es
   donde el operador confirma el intent).
10. `test_interpret_404_con_flag_off` — **C7.** `/interpret` es el **único endpoint que gasta
    tokens**; con `STACKY_PIPELINE_NL_EDIT_ENABLED` OFF debe dar **404 sin llamar a `call_llm`**
    (doble de `call_llm` que cuenta invocaciones: **0**). *Un endpoint de LLM sin test de flag-off
    es una fuga de tokens esperando a que alguien lo llame.*
11. `test_validate_intent_dict_es_puro` — la validación vive en `pipeline_patcher.py` (C1) y
    **no importa nada de `api/`**: se la invoca con un dict crudo, sin app Flask ni red.

**Comando:** `.venv\Scripts\python.exe -m pytest tests/test_plan250_edit_intent.py -q`
(+ las dos listas del ratchet).

**Criterio de aceptación (BINARIO):** **11/11** verdes, **cero acceso a red** (guard de red del
arnés verde), y el KPI-5 probado por los tests 5 y 10.

**Flag:** `STACKY_PIPELINE_NL_EDIT_ENABLED` (default ON). **F5 la chequea por su cuenta** en cada
handler: el `requires` de la `FlagSpec` es **informativo y ningún runner lo evalúa**
(`harness_flags.py:30-32`).
**Impacto por runtime:** ver la tabla de fallback de arriba. En tests, `fixture_id` ⇒ cero red en
los 3 runtimes.
`Trabajo del operador: opt-in, default ON`

---

## 4. Gestión de errores (transversal)

| Falla | Comportamiento |
|---|---|
| Pedido NL ambiguo | `(None, preguntas)`. **No adivina.** 0 reintentos automáticos |
| LLM caído / runtime sin modelo | `call_llm` no lanza (`pm_llm_client.py:281-283`); la caja NL reporta el error y **el formulario de verbos sigue operativo** |
| `task_ref` fuera del catálogo | Rechazo en F1, antes de emitir una sola op |
| Patch introduce un error nuevo | `review.ok is False` ⇒ commit deshabilitado; el diff **se muestra igual** |
| Error preexistente en el archivo | **No bloquea** (gates por delta, §F2) |
| YAML no parsea (antes) | `ok=False` con el error de PL001; no se ofrece patch |
| YAML no parsea (después) | `ok=False`; el patch **no se ofrece** |
| YAML > 512 KB | `ok=False` con mensaje; no se procesa (espejo de `cicd_semantic_rules.py:51`) |
| > 12 ops en un plan | Rechazo con "partilo en dos ediciones" |
| Ops solapadas | Rechazo **total**; nunca se aplica media edición |
| Item con `-` en línea propia | Error accionable; **nunca se adivina la indentación** |
| `before` recibido no hashea a `before_sha256` | **400** (request incoherente) |
| **El archivo cambió en el repo desde el diff** | **No es detectable** con el puerto actual (§2.8, C3): se devuelve `stale_check: "no_verificable"`. **Jamás se dice "validado"**. Un push concurrente sobre la misma rama lo rechaza **ADO** contra el `old_object_id` (`ado_provider.py:161-191`) |
| El cliente manda un YAML final | **Se ignora**: el servidor recompila desde el `intent` |
| Rama = rama por defecto | **400.** Nunca se commitea sobre la rama por defecto |
| `_default_branch` no se puede resolver | **400.** No saber cuál es la rama por defecto **no habilita** a escribir en ella |
| Contenido idéntico al que ya está en la rama | `status='unchanged'` de `ado_provider.py:199-221`; se muestra **tal cual**, nunca como "commiteado" |
| **El provider no implementa `RepoWriter`** | `get_repo_writer` lanza `RuntimeError` (`repo_writer.py:37-41`) ⇒ **400** con su mensaje (C9). **Nunca un 500 mudo** |
| Writer sin soporte de escritura | **501** con el YAML parcheado y los hunks intactos; la UI ofrece copiar. **Nunca se dice "commiteado"**. *No es el caso de ADO (§2.7)* |
| **Se perdería un comentario o una construcción no modelada** | `preservation.ok is False` ⇒ `review.ok is False` ⇒ **422**, y el operador ve **qué** se perdía. [ADICIÓN ARQUITECTO] |
| Plan 248 ausente | El botón de recomendaciones **no se muestra**; la edición NL funciona igual |
| Plan 246 ausente (hoy) | La vía "elegir de la lista" no se muestra; **la vía "pegar el YAML" funciona sola** (C5) |
| `repo_root` ausente | RS006 no se evalúa y se declara `skipped`; **nunca** "validado" por omisión |
| Flag de análisis OFF | 404 en los 4 endpoints; la sección muestra el `FlagGateBanner`; **el builder gráfico queda idéntico a hoy** |
| **Flag de commit OFF (el DEFAULT)** | 404 sólo en `/commit`. Se puede planificar, diffear e interpretar; el botón **explica cómo activarla** y ofrece copiar el YAML (C2) |

## 5. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | **Pérdida silenciosa de comentarios o de construcciones no modeladas** | Media | **Crítico** | Tests 3, 5 y 6 de F0 sobre los 9 goldens: 337 comentarios y `scan_unsupported` invariante. Es el riesgo que define el plan |
| R2 | El `end_mark` mal interpretado huerfana comentarios en el paso equivocado | **Alta** | Alto | §2.3 escrito como fórmula + `test_fin_efectivo_excluye_comentario_del_siguiente_item` |
| R3 | Gates demasiado estrictos vuelven ineditables los pipelines reales | **Alta** | Alto | Delta en vez de valor absoluto + `test_error_preexistente_no_bloquea_la_edicion` (F2) |
| R4 | Corrimiento de índices/líneas produce decenas de findings "nuevos" falsos | Alta | Medio | **Dos** claves de identidad, no una (C4): `_sem_key` normaliza `[\d+]` → `[]` sobre `location`; `_lint_key` usa `node` y **nunca** `line`. Tests 4 y 10 de F2 |
| R5 | El LLM inventa una tarea o un input | Media | Alto | Catálogo cerrado (`is_allowed`, `validate_inputs`) + RS008 en `nl_strict` sobre los bloques insertados |
| R6 | Inyección hacia agentes self-hosted vía el pedido NL | Baja | **Crítico** | El NL nunca llega al YAML (test 7 de F5); `display_name`/`inputs` de 1 línea, ≤200 chars, emitidos por `yaml.safe_dump`; RS004 bloquea `PowerShell@2` inline |
| R7 | El operador aprueba un diff y se escribe otro archivo | Baja | Alto | Doble sha256 (`before_sha256` + `approved_after_sha256`) ⇒ 409 |
| R8 | No determinismo del LLM confunde al operador | Media | Medio | El `EditIntent` (8 campos) se muestra **antes** del diff; el tramo intent→patch es determinista |
| R9 | El alcance no entra en una corrida | Media | Alto | **6 fases**, provider ADO solo, 7 verbos, sin bucle de reparación (§3), y F0–F4 entregan la feature completa sin LLM |
| R10 | Costo de LLM | Baja | Bajo | 1 llamada por pedido (**constante del módulo**, no flag), 0 reintentos, y `/interpret` con test de flag-off (C7) |
| **R11** | **Se pushea al repo real del operador con la feature recién instalada, sin que él haya decidido habilitarlo** | Media | **Alto** | **C2:** la escritura tiene **flag propia default OFF**; el análisis (ON) **no escribe nada**. Test 9 de F3 |
| **R12** | **El invariante de preservación se rompe sobre un pipeline que NO está en el corpus dorado y nadie se entera** | Media | **Crítico** | **[ADICIÓN ARQUITECTO]:** `G-PRESERVACION` corre en cada `/plan` sobre el archivo real del operador y **bloquea**; el sello se muestra antes de confirmar. Tests 11 y 12 de F2 |
| **R13** | **Colisión de superficie con los otros 6 planes de la serie** | **Alta** (materializada en el v1) | Alto | **C1:** frontera cerrada §3.1 + gate `git diff --name-only` en el DoD + el test del archivo ajeno (`PipelineBuilderSection.test.ts`) corriendo verde |

**Reversibilidad (explícita, como pide el alcance):**

0. **De fábrica no se escribe en ningún lado**: `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` viene
   **OFF** (C2). Hay que encenderla a mano, una vez, desde la UI.
1. **Nada se escribe sin `confirm=True`.** El estado por defecto es "no escrito".
2. **Todo commit va a una rama**, nunca a la rama por defecto (candado 2 de F3). Descartar la
   rama restaura el estado anterior **byte por byte** — y esto es cierto *porque* el patch es un
   splice sobre el original, no una regeneración: no hay ruido de reformateo que sobreviva.
3. `git revert` del commit funciona limpio por la misma razón.
4. `STACKY_PIPELINE_NL_EDIT_ENABLED=false` **desde la UI** apaga la feature entera; apagar sólo
   la de commit deja el análisis vivo.
5. Las 6 fases son **aditivas**: no se modifica ningún módulo existente de pipelines
   (`pipeline_generator.py`, `pipeline_renderers.py`, `pipeline_lint.py`,
   `cicd_semantic_rules.py` quedan intactos), así que revertir el plan es borrar archivos nuevos
   más 4 líneas de registro.

## 6. Fuera de scope (nombrando los planes de la serie)

- **Crear una pipeline desde cero por lenguaje natural** → **Planes 243 (F0..F3.5) y 244
  (F4..F9)**. El 250 **no** genera pipelines: sólo modifica una que ya existe. Si el archivo no
  existe, el panel lo dice y remite al generador.
- **Descubrir qué pipelines hay** (registro multiproveedor, estado de última corrida) → **Plan
  246**. El 250 recibe la ruta y el contenido; no los busca.
- **Perfilar** (stack, anatomía, propósito en 1 línea) → **Plan 247**.
- **Definir reglas nuevas de seguridad o de optimización** (`SEC001..SECnn`, recomendaciones
  `OPT*`) → **Plan 248**. El 250 **consume** sus recomendaciones si están (puente con import
  blando, §F5) y **no define ni una regla nueva**. Tampoco redefine `PL001..PL014`
  (Plan 186) ni `RS001..RS009` (Plan 243 F3): las **usa**.
- **Paridad GitLab del motor** (catálogo GitLab, `GL001..GLnn`, endurecer parser/renderer GitLab)
  → **Plan 249**. El 250 es **ADO solamente**; cuando el 249 exista, el motor de F0 sirve igual
  porque es agnóstico de proveedor (opera sobre texto YAML y marcas de línea), pero **este plan no
  lo declara soportado ni lo testea**.
- **Matriz de entornos y valores que sólo el operador conoce** → **Plan 251**.
- **Paquete de entrega, README operativo y frontera de capacidades** → **Plan 252**.
- **Registrar la definición en ADO y disparar la primera corrida** → **Plan 244 F8**. El 250
  termina en el commit a la rama; **no dispara ninguna corrida**.
- **Migrar los pipelines existentes** a ningún modelo nuevo.

## 7. Glosario, orden de implementación y DoD

### 7.1 Glosario

| Término | Significado exacto en este plan |
|---|---|
| **Patch quirúrgico** | Reemplazo de un conjunto de rangos de líneas del documento original. Todo lo demás queda **byte-idéntico** |
| **Round-trip / regeneración** | `parse → modelo → render`. **Prohibido** en la ruta de edición: destruye 337/337 comentarios (§0) |
| **Anchor** | Nodo del YAML localizado en el texto (path + rango de líneas + columnas), obtenido con `yaml.compose` |
| **Fin efectivo** | Última línea con contenido real de un nodo, excluyendo blancos y comentarios que pertenecen al siguiente (§2.3) |
| **Hunk** | Rango del original + sus líneas antes/después + el motivo. Es **la verdad** del cambio, no una reconstrucción por LCS |
| **Gate por delta** | Un hallazgo bloquea sólo si **no estaba antes** del patch |
| **`EditIntent`** | Estructura cerrada de **9** campos (`verb`, `target_path`, `anchor_ref`, `position`, `task_ref`, `inputs`, `display_name`, `values`, `notes`): lo único que produce el LLM. *(v1 decía "8" — C11)* |
| **Sello de preservación** | `Preservation` de §F2: comentarios antes/después, construcciones no modeladas perdidas y líneas byte-idénticas. **Es un gate, no un adorno** |
| **`stale_check`** | `"no_verificable"`: Stacky **no puede** saber si el archivo cambió en el repo desde que se mostró el diff, porque el puerto no lee (§2.8). Se declara, no se disimula |
| **`EditPlan`** | Tupla de `EditOp` derivada del intent de forma 100 % determinista |

### 7.2 Orden de implementación (obligatorio)

**F0 → F1 → F2 → F3 → F4 → F5.** Ninguna fase depende de una posterior.
F1 usa el índice de F0; F2 usa los hunks de F0; F3 usa F0+F1+F2; F4 usa F3; F5 usa F1 y el
catálogo del 243 F0.

> **Punto de corte seguro:** al terminar **F4**, la feature está **completa y usable**
> (edición quirúrgica por controles, diff visible, commit HITL, sin ningún modelo). **F5 sólo
> agrega la puerta de entrada en prosa.** Si la corrida se queda sin sesión, se corta acá y se
> declara; no se entrega media F5.
>
> **v2 (C5): ese corte ahora es cierto.** En el v1 no lo era, porque el panel **no tenía de dónde
> sacar el YAML** (dependía del Plan 246, que no existe). Con la vía "pegar el YAML + ruta" de
> §F4, F0–F4 se sostienen **solas**.
>
> **Segundo punto de corte, aún más barato:** al terminar **F2** ya existe el valor central del
> plan sin una línea de UI — patch quirúrgico verificado sobre 9 pipelines de producción, gates
> por delta y sello de preservación. Si algo se cae, se corta ahí y **nada de lo hecho se tira**.

### 7.3 Comandos exactos (dossier §4, verificados el 2026-07-26)

> **Trampa de la casa:** conviven `backend/.venv` (**Python 3.13.5**) y `backend/venv`
> (**3.11.9**). **Usá `.venv`.** El frontend **no tiene script `test`**: `npm test` falla, se usa
> `npx vitest`. Los tests se corren **por archivo** (la suite completa se contamina).

```powershell
# --- BACKEND ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan250_patcher.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_verbos.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_gates_delta.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_flag.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan250_edit_intent.py -q

# --- BACKEND: no regresión (nada de esto puede ponerse rojo) ---
.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_render_ado.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan73_generator_endpoint.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_reglas_semanticas.py -q
.venv\Scripts\python.exe -m pytest tests/test_plan243_renderer_ado.py -q

# --- BACKEND: obligatorios tras crear tests / tocar flags ---
.venv\Scripts\python.exe -m pytest tests/test_harness_ratchet_meta.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q

# --- FRONTEND ---
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/devops/__tests__/pipelineEditModel.test.ts
npx tsc --noEmit
```

### 7.4 Definición de Hecho (BINARIA)

- [ ] **6** archivos de test backend verdes, corridos **por archivo**: `test_plan250_patcher.py`
      (**14**), `test_plan250_verbos.py` (10), `test_plan250_gates_delta.py` (**12**),
      `test_plan250_api.py` (**11**), `test_plan250_flag.py` (4), `test_plan250_edit_intent.py`
      (**11**) = **62 casos**.
- [ ] **1** archivo de test frontend verde: `pipelineEditModel.test.ts` (**11**).
- [ ] **KPI-1:** `test_los_337_comentarios_del_corpus_sobreviven` verde — **337/337** sobre los 9
      goldens.
- [ ] **KPI-2:** `test_el_diff_real_no_sale_de_los_hunks_declarados` verde sobre los 9 goldens.
- [ ] `test_construcciones_no_modeladas_no_desaparecen` verde — `scan_unsupported` invariante,
      con `matrix` conservado en `ci-batch.yml` y `compile_time_expression` en
      `bootstrap-server-environment.yml`.
- [ ] `test_fin_efectivo_excluye_comentario_del_siguiente_item` verde — el `end_mark` está bien
      interpretado (§2.3).
- [ ] **KPI-3:** `test_patch_que_introduce_error_nuevo_no_se_ofrece` verde — **ADO-369 se
      detectaría también en la ruta de edición**.
- [ ] `test_error_preexistente_no_bloquea_la_edicion` verde — el gate no es inútil de estricto.
      *Este y el anterior, los dos, o el gate es mentira.*
- [ ] **KPI-4:** `test_commit_sin_confirm_es_400` y `test_commit_sobre_rama_default_es_400` verdes.
- [ ] `test_commit_ignora_el_yaml_del_cliente` verde — el servidor recompila siempre.
- [ ] **KPI-5:** `test_una_sola_llamada_llm_por_pedido` verde — exactamente 1, aun con JSON
      inválido.
- [ ] `test_el_texto_nl_no_llega_al_yaml` verde.
- [ ] `test_recomendacion_sin_plan_248_degrada` verde — **sin `ImportError`**.
- [ ] **KPI-4 bis (C2):** `test_commit_404_con_flag_de_commit_off` verde — **de fábrica el
      sistema ve y diffea pero NO escribe** en el repo del operador.
- [ ] **[ADICIÓN ARQUITECTO]:** `test_gate_preservacion_bloquea_si_desaparece_un_comentario` y
      `test_remove_step_no_dispara_falso_positivo_de_preservacion` verdes, y el sello visible en
      el panel antes del botón de commit.
- [ ] **C4:** `test_lint_delta_no_usa_line_como_identidad` verde — dos claves distintas, y
      `_lint_key` **no** toca `f.line` ni `f.location`.
- [ ] **C3:** `test_stale_check_se_declara_no_verificable` verde — **nunca** se afirma haber
      validado contra el repo.
- [ ] **C1 — FRONTERA (gate binario):** `git diff --name-only` **no** lista ningún archivo fuera
      de la tabla de §3.1. En particular **NO** aparecen `PipelineBuilderSection.tsx`,
      `pipeline_renderers.py`, `cicd_semantic_rules.py`, `pipeline_generator.py`,
      `pipeline_lint.py`, `repo_writer.py` ni `ado_provider.py`. Y
      `npx vitest run src/components/devops/__tests__/PipelineBuilderSection.test.ts` verde.
- [ ] **No regresión:** `test_plan73_round_trip.py`, `test_plan73_render_ado.py`,
      `test_plan73_generator_endpoint.py`, `test_plan243_reglas_semanticas.py`,
      `test_plan243_renderer_ado.py` verdes.
- [ ] `test_harness_ratchet_meta.py` verde con los **6** archivos registrados en **las DOS**
      listas (`run_harness_tests.sh:20` y `run_harness_tests.ps1:13`).
- [ ] `test_default_known_only_for_curated` verde; **`STACKY_PIPELINE_NL_EDIT_ENABLED` en
      `_CURATED_DEFAULTS_ON` y `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` FUERA** de esa lista
      (es default OFF); ambas visibles y editables **desde la UI**.
      *Baseline verde de referencia antes de tocar nada: `test_harness_flags.py` = **56 passed**,
      `test_harness_ratchet_meta.py` = **4 passed**. Ojo con el rojo ajeno de
      `test_harness_flags_help` (4 fallos preexistentes que **no son tuyos**).*
- [ ] `npx tsc --noEmit` sin errores nuevos; ratchet de deuda de UI **sin crecer**; **cero
      `style={{...}}` inline** en el `.tsx` nuevo.
- [ ] **Paridad de runtimes:** F0–F4 no invocan LLM ni red ⇒ corren igual en Codex CLI, Claude
      Code CLI y GitHub Copilot Pro (**fallback: no aplica, no hay nada que degradar**). F5 pasa
      por `call_llm`, que **nunca lanza**; **fallback explícito**: sin modelo, la caja NL informa
      el error y **el formulario de verbos de F4 sigue 100 % operativo**.
- [ ] **Smoke visual del operador** (no automatizable: no hay `jsdom` ni
      `@testing-library/react`): pegar una pipeline real, pedir un cambio, **ver el diff y el
      sello de preservación**, **encender la flag de commit desde la UI**, confirmar, y verificar
      en la rama que **los comentarios siguen ahí**. *El paso de encender la flag es parte del
      smoke a propósito: prueba que el default de fábrica no escribía.*

### 7.5 Huella de regresión (C13 — convención de la casa)

Este plan mata una clase de error concreta y medida, así que la registra en
`Stacky Agents/docs/sistema/error_fingerprints.json` (mismo formato que el resto de las entradas):

| Campo | Valor |
|---|---|
| `id` | `PIPE-ROUNDTRIP-DESTRUCTIVO` |
| `patron` | Editar un pipeline existente por `parse → modelo → render`, que borra el **100 %** de los comentarios y el **48 %** de las líneas sin avisar (medido dos veces: v1 y crítica v2, sobre los 9 goldens: 1138→588 líneas, 337→0 comentarios) |
| `plan` | 250 |
| `fecha` | 2026-07-26 |
| `guard_test` | `backend/tests/test_plan250_patcher.py::test_los_337_comentarios_del_corpus_sobreviven` **+** el gate en vivo `G-PRESERVACION` de `services/pipeline_diff.py` |

**El guard es doble a propósito:** el test cubre el corpus dorado; el gate cubre **los pipelines
del operador**, que son los que no están en ningún corpus.
