# Plan 264 — Herramienta, modelo y effort elegibles en TODO punto de uso: una sola matriz de capacidades, una sola resolución, un solo selector

**Estado:** MEJORADO **v3 -> v4** (2026-07-29) · **Autor:** pipeline `proponer-plan-stacky` · **Juez v1→v2:** `criticar-y-mejorar-plan` (v1 RECHAZADO, 4 BLOQUEANTES) · **Juez v2→v3:** `criticar-y-mejorar-plan` en corrida independiente (v2 RECHAZADO, 5 BLOQUEANTES) · **Juez v3→v4:** `criticar-y-mejorar-plan` en corrida **independiente**, abriendo el árbol real de HOY — **v3 RECHAZADO** (2 BLOQUEANTES), v4 con los fixes aplicados.

---

## 0. CHANGELOG v3 -> v4

> El v3 fue anclado el 2026-07-27. Entre esa fecha y hoy (2026-07-29) se mergearon a `main` los
> planes hermanos 259/267/268/269/270 (`git log` confirma `1a04944e "merge(p2): plan 259 F0..F9"`,
> 2026-07-29), cada uno agregando sus propias flags a los mismos registros compartidos
> (`FLAG_REGISTRY`, `_CATEGORY_KEYS`, `_CURATED_DEFAULTS_ON`, `_REQUIRES_MAP_FROZEN`). Es la MISMA
> clase de gotcha que el propio v3 documenta en su C11 (anclajes con desvío de línea), pero esta vez
> le pasó al v3 mismo mientras esperaba turno de crítica — el riesgo es estructural, no un error
> puntual de un autor. Los IDs `C#` de abajo son de **esta** ronda (v3→v4).

- **C1 (BLOQUEANTE) — la huella de regresión de F7 usa un esquema INVENTADO; rompe
  `test_error_fingerprints_catalog.py` (Plan 163 F4), que SÍ corre hoy contra `error_fingerprints.json`.**
  Verificado abriendo `backend/tests/test_error_fingerprints_catalog.py:18`: los campos obligatorios
  reales son `("id", "title", "class", "status", "log_pattern", "log_guarded", "killed_by",
  "guard_test", "self_test")`, con `status` en `{"resolved","open","by_design"}` y `self_test` con
  `matches`/`clean` coherentes contra `log_pattern` (test que además compila el pattern como regex).
  El JSON que el v3 proponía en F7 traía `sintoma`, `causa_raiz`, `deteccion`, `antecedentes`, `plan`,
  `fecha` — **ninguno de estos existe en el schema real** y **faltan 7 de los 9 campos
  obligatorios** (`title`, `class`, `status`, `log_pattern`, `log_guarded`, `killed_by`, `self_test`).
  Aplicado tal cual, `test_campos_obligatorios` sale **rojo** el día que se agrega la entrada — el v3
  pedía "leé primero el esquema real del archivo" pero sus propios autores no lo hicieron. Hay,
  además, un problema de fondo: esta clase de bug (parámetro aceptado y nunca materializado) **no
  tiene firma de log** — es un no-evento, no un patrón que aparezca en texto — así que `log_pattern`
  no puede ser un detector real como el de las huellas existentes (`pipeline_status_404`,
  `ansi_in_file_log`); el `guard_test` (AST) es el único detector posible. **Y el archivo YA está
  rojo hoy** (medido: `test_error_fingerprints_catalog.py` = 3 failed/5 passed, por una huella ajena
  con `status: "guarded"` fuera del enum) — el criterio de F7 no puede pedir "verde", tiene que ser
  delta (mismos 3 failed, ninguno con el id de este plan). v4: entrada reescrita con los campos
  reales, `log_guarded: false` declarado con la razón, `self_test` vacío (vacuamente coherente:
  `test_self_test_coherente` no itera nada si `matches`/`clean` son `[]`) en vez de fingir un patrón
  de log que no existe, y el criterio de F7 pasado a delta.
- **C2 (BLOQUEANTE) — 11 anclajes archivo:línea quedaron viejos por la costura de planes hermanos;
  exactamente el gotcha que este mismo plan advierte en su propio C11, reaparecido.** Verificado
  abriendo cada archivo real hoy (no de memoria). Los anclajes que son **objetivo de un diff/edición
  literal siguen siendo pixel-perfect** (los 6 de `api/agents.py`, los 2 de
  `api/devops_remote_console.py`, los 17 call sites de `run_agent(`, `codex_cli_runner.py:87-97`,
  `agent_runner.py:144-465`, `claude_code_cli_runner.py:516/543/958-961/2224/2301`,
  `preferences.py:14/65/71/75/89`, `model_catalog.py:111/135`, `PlansBoardPage.tsx:336/348`,
  `IncidentResolverModal.tsx:414/422`, `modelEffortOptions.ts:63-73` — todos re-verificados letra por
  letra). El drift está **sólo** en citas de prosa/evidencia en los archivos "calientes" que crecen
  con cada plan hermano:
  | Símbolo | v3 citaba | Real hoy (2026-07-29) |
  |---|---|---|
  | `STACKY_COMPLEXITY_ESTIMATION_ENABLED` | `config.py:774` | `config.py:789-790` |
  | `STACKY_ADAPTIVE_EFFORT_ENABLED` | `config.py:905` | `config.py:920-921` |
  | `STACKY_MODEL_PROBE_ENABLED` | `config.py:1258` | `config.py:1273-1274` |
  | `STACKY_UI_SAVED_VIEWS_ENABLED` | `config.py:1810` | `config.py:1825-1826` |
  | nota Plan 63 (`test_every_registry_flag_is_categorized`) | `harness_flags.py:488-489` | `harness_flags.py:515` |
  | `FLAG_REGISTRY` (apertura) | `harness_flags.py:490` | `harness_flags.py:516` |
  | `default_is_known(spec)` | `harness_flags.py:5503` | `harness_flags.py:5814` |
  | `test_default_known_only_for_curated` | `test_harness_flags.py:974-982` | `test_harness_flags.py:~1001` |
  | `test_requires_map_is_frozen` | `test_harness_flags_requires.py:312-320` | `test_harness_flags_requires.py:~326` |
  | `RuntimeModelCatalog` (interface) | `endpoints.ts:1071-1084` | `endpoints.ts:1090-1103` |
  | historial `r.model`/`r.effort` | `PlansBoardPage.tsx:481`/`:482` | `PlansBoardPage.tsx:482`/`:483` |
  Ninguno de estos 11 es el objetivo de una edición literal (son citas de "por qué" en prosa), así
  que **no bloquean el diff en sí** — pero una cita de línea que no matchea erosiona exactamente la
  confianza que este plan pide para sus propios anclajes, y para un modelo menor "no encuentro esto
  en la línea que dice el plan" es indistinguible de "el plan está mal". v4: los 11 números
  corregidos arriba, y las citas dentro de `harness_flags.py`/`config.py` (los dos archivos que un
  plan hermano nuevo vuelve a mover cada vez que se mergea) llevan ahora la misma coletilla
  "verificar con `grep -n <símbolo>`" que F0 ya usaba para `STACKY_MODEL_PROBE_ENABLED` — no se puede
  evitar que vuelvan a moverse, sí se puede dejar de fingir que un número fijo sobrevive.
- **C3 (IMPORTANTE) — F5(c) delega en "verificalo vos mismo" sin dar la prueba concreta, y uno de
  los 3 candidatos verificablemente NO califica.** Medido: `TriggerPipelineSection.tsx` no llama a
  `run_agent`; dispara `devops.pipeline.trigger` vía `runDevOpsAction` (Plan 267 F7) — un **catálogo
  de acciones DevOps/CI**, sin ninguna dimensión de modelo/effort. `DeploymentsSection.tsx` tampoco
  tiene ningún `run_agent`/`POST run`/`rawPost` — incompatible con "esta pantalla lanza una corrida
  de agente". `DocsPage.tsx` sí es un candidato plausible: usa `documenterEnabled` y
  `handleProposeUpdate` (`DocsPage.tsx:159,445`), que encaja con el call site F3 #4
  (`services/doc_documenter.py:383`). Pedirle a un modelo menor "verificá si lanza una corrida" sin
  decir CÓMO verificarlo invita a confundir "dispara una acción" (CI/deploy) con "lanza un agente
  LLM con modelo/effort elegible" — exactamente los dos primeros no son lo segundo. v4: regla
  concreta y verdicto explícito por candidato.

---

## 0.bis CHANGELOG v2 -> v3

> La v2 fue escrita y criticada **por el mismo agente en la misma corrida**, así que nunca tuvo
> revisión independiente. Esta ronda abrió **todos** los archivos citados. Resultado: el v2 tenía
> razón en su diagnóstico general y en 7 de sus 12 fixes, pero **el fix central apuntaba a código
> muerto** y **tres de sus criterios binarios nacían imposibles**. Los IDs `C#` de abajo son de
> **esta** ronda (v2→v3) y no se corresponden con los de la ronda v1→v2, que se conserva íntegra
> más abajo.

- **C1 (BLOQUEANTE) — F2 parcheaba una rama MUERTA; el effort seguía sin llegar a Codex.**
  `agent_runner.py:144-157` hace un **return temprano incondicional**:
  `if runtime in {"codex_cli", "claude_code_cli"}: return _start_cli_runtime(...)`. Todo el bloque
  `agent_runner.py:227-300` — donde vive el `:256` que el v2 mandaba parchear — es **inalcanzable**
  para una corrida normal. La llamada VIVA que descarta el effort es
  **`agent_runner.py:442-451`**, dentro de `_start_cli_runtime`, que **recibe** `effort_override`
  (`:421`) y **no lo reenvía** a `start_codex_cli_run`. Con el diff del v2 aplicado al pie de la
  letra, el comportamiento observable **no cambiaba** y el **test 2 de F2 nacía ROJO**. Ironía
  registrada: el comentario del Plan 196 (`agent_runner.py:344-349`) afirma *"el OTRO call site
  (`_start_cli_runtime`) sí lo pasa"* — cierto para Claude (`:465`), **falso para Codex**; el v2
  copió el modelo del 196 y heredó su punto ciego. v3: se parchea **`:442-451` (obligatorio, es el
  vivo)** y **`:256-264` (higiene del código muerto)**, y F2.5 Test A cuenta **las dos** llamadas.
- **C2 (BLOQUEANTE) — el binding de `config` estaba invertido: el fix nacía muerto o crasheaba.**
  El v2 escribía `getattr(config.config, "STACKY_CODEX_EFFORT_PARITY_ENABLED", False)` dentro de
  `services/codex_cli_runner.py`. Pero ese módulo hace **`from config import config`**
  (`codex_cli_runner.py:22`): el nombre local `config` **ya es la instancia** (`config.py:2137`
  `config = Config()`). `config.config` levanta `AttributeError` ⇒ o revienta la corrida, o cae en
  el `except` ancho y la flag queda **OFF para siempre**. El v2 aplicó el gotcha del repo
  ("la instancia es `config.config`") de memoria, sin leer el import del archivo destino — que es
  exactamente la clase de error que este plan dice cerrar. v3: **regla explícita de binding**
  (§3.8), el diff usa `getattr(config, ...)` en los runners, y **F2.5 Test E [ADICIÓN
  ARQUITECTO]** convierte la regla en un gate AST.
- **C3 (BLOQUEANTE) — la matriz prometía una capacidad que el catálogo vivo no tiene, y sus tests
  lo tapaban.** En `config/model_catalog.json` el bloque `codex_cli` tiene **`efforts: []`**,
  **`default_effort: null`** y **`models: [""]`** (un id vacío). Consecuencias en cadena:
  `capabilities_for("codex_cli")["efforts"] == []` ⇒ `pickerCapabilities.showEfforts === false` ⇒
  **el selector de esfuerzo de Codex no se muestra en ninguna pantalla**; y
  `resolve_run_selection` cae a `effort=None` ⇒ `codex_turn_budget(None, cap) == cap` ⇒ **toda la
  cadena de F2 queda inerte**. Y los tests del v2 pasaban igual: el test 22 afirmaba
  `{ids} <= set(EFFORTS)` — el conjunto **vacío** es subconjunto de todo — y el test 4 de F3
  afirmaba `effort == default_effort` — `None == None`. Falso verde estructural, de la misma
  familia que el del v1. v3: `capabilities_for()` **normaliza** (fallback a `EFFORTS` cuando el
  modo no es `no_aplica`, filtra ids de modelo vacíos), el test 22 pasa a ser **no vacuo**
  (exige `efforts` **no vacío** e **igual** a `EFFORTS`) y el test 4 exige un `default_effort`
  **no nulo**.
- **C4 (BLOQUEANTE) — `effort_mode` nunca llegaba al frontend: F5 era inerte en producción.**
  El endpoint del catálogo (`api/agents.py:1368-1392`) devuelve `catalog["runtimes"]` **crudo**
  (más los modelos de Copilot). `effort_mode` no existe en `config/model_catalog.json` ni lo
  inyecta nadie ⇒ en producción `runtimeCatalog.effort_mode` es **siempre `undefined`** ⇒
  `effortMode` cae a `"nativo"` ⇒ el cambio de F5 **no hace nada**, mientras el test 2 de vitest
  (que construye el objeto a mano) sale **verde**. Segundo falso verde estructural. v3: **F1 (c)**
  enriquece la respuesta HTTP con `effort_mode`, `effort_note`, `effort_effective_now` y los
  `efforts` normalizados, con un test de backend sobre la **respuesta real**.
- **C5 (BLOQUEANTE) — F0 volvía a nacer roja por DOS patas más de la receta de flags.**
  (a) **`_REQUIRES_MAP_FROZEN`** (`tests/test_harness_flags_requires.py:120`) se compara por
  **igualdad exacta** en `test_requires_map_is_frozen` (`:312-320`); las **3** flags del plan que
  declaran `requires=` aparecen como *"Extras"* ⇒ **ROJO** — y F0 corre justamente ese archivo
  como criterio binario. (b) **`PLAIN_HELP`** vive en `services/harness_flags_help.py` y
  `tests/test_harness_flags_help.py:33-40` exige **cobertura 100 % de `FLAG_REGISTRY` sin keys
  huérfanas**: 4 flags sin entrada = **4 fallos NUEVOS** sumados a los 4 ajenos. Además el chequeo
  manual que el v2 proponía era el equivocado (habla de `label`/`description` y de "240 chars de
  la descripción"; el límite real es sobre **`on_effect`/`off_effect`** del `PlainHelp`,
  `test_harness_flags_help.py:49-50`). v3: **F0 son CINCO archivos**, con las entradas literales
  de las dos estructuras que faltaban.
- **C6 (BLOQUEANTE) — KPI-1 nacía imposible: el censo era 5 y el real es 10.** Corrido el grep del
  propio plan sobre el árbol actual da **10**, no 5. Faltaban `api/agents.py:681, 717, 934, 963,
  1156` y `api/plans_board.py:176`, más el comentario de `services/adaptive_selector.py:57` (que
  el grep **sí** cuenta, porque `\{"low", *"medium"` matchea con cero espacios). Y las dos de
  `api/devops_remote_console.py` que el v2 **sí** editaba **no las cuenta el grep** (el literal
  está partido: `:212` abre la llave, `:213` tiene el contenido). Con las 5 ediciones del v2 el
  grep quedaba en **7**, y el criterio binario "debe dar **0**" era inalcanzable — el mismo
  defecto de clase que el C4 de la ronda anterior, en otra lista. v3: tabla de **12 ediciones en
  6 archivos**, con el reemplazo exacto de cada una y su equivalencia semántica declarada.
- **C7 (IMPORTANTE) — la rama adaptativa NO era "byte-equivalente": -25 % de turnos en el caso
  más común.** Hoy sólo `low` baja el presupuesto (`_codex_adaptive_turns // 2`,
  `codex_cli_runner.py:591-592`); `medium`/`high` lo dejan en el cap. Con
  `CODEX_EFFORT_TURN_FACTOR["medium"] = 0.75`, una corrida con complejidad **M** (y también el
  piso `STACKY_EFFORT_FLOOR="medium"`) pasaba de `cap` a `int(cap*0.75)`. El v2 declaraba
  equivalencia citando **sólo** el caso `low`. v3: `medium` pasa a **1.0** (equivalencia exacta
  con el código de hoy en los 5 efforts) y hay un test que compara los 5 contra la fórmula
  vigente.
- **C8 (IMPORTANTE) — con la configuración por default, el effort en Codex NO tiene ningún efecto
  observable, y el plan lo vendía como cerrado.** `STACKY_RUNAWAY_MAX_TURNS` vale **`0`**
  (`config.py:471-472`) ⇒ `codex_turn_budget(e, 0) == 0` para los 5 efforts ⇒ elegir `low` o `max`
  produce exactamente la misma corrida. El KPI-3 afirmaba "el effort llega al runner en los 3
  runtimes" y el §3.1 prohíbe "mostrar un selector que no hace nada": el plan violaba su propio
  principio. Peor: el **test 5 de F2**, presentado como candado de seguridad, es literalmente la
  prueba de la inercia. v3: `capabilities_for()` expone **`effort_effective_now`** y una
  `effort_note` honesta, el KPI-3 se reformula, y hay test en los dos estados (cap 0 y cap > 0).
- **C9 (IMPORTANTE) — 9 de los 11 call sites de F3 no tienen `runtime` ni `project_name` en
  scope.** Medido: sólo `devops_section_doctor.py:171`, `doc_documenter.py:383` y
  `pipeline_orchestrator.py:58` pasan ambos; `variant_generator.py:188` pasa sólo `runtime`; los
  otros 7 no pasan ninguno. El patrón literal del v2 usaba las dos variables ⇒ ambigüedad que
  impide implementar en 7 de 11. v3: **regla determinista sin adivinanza** + columna por call site
  con el valor exacto.
- **C10 (IMPORTANTE) — KPI-4 era gameable.** Su grep matchea **2 líneas**, ambas en
  `IncidentResolverModal.tsx:414,422`; **`PlansBoardPage.tsx` aporta 0 hoy** (sus `<select` no
  llevan las palabras "model"/"effort" en la misma línea) ⇒ el criterio "**0**" se cumplía sin
  tocar `PlansBoardPage`. v3: criterio **positivo** (`ModelEffortPicker` importado en ambos) +
  **negativo** (`effortsForModel`, `EMERGENCY_MODEL_CATALOG`, `setActionEffort` con **0** hits en
  esos dos archivos).
- **C11 (MENOR) — anclajes con desvío de línea.** Verificados uno por uno: el comentario *"Codex
  no tiene --effort"* está en **`codex_cli_runner.py:580`** (no `:581`, que es
  `_codex_adaptive_turns = ...`); `_codex_complexity` se declara en **`:444`** (no `:445`);
  `_merge_probe` se define en **`model_catalog.py:111`** (no `:128-140`; `:135` sí es el import de
  `claude_code_cli_runner`); el `set(CLI_VALID_EFFORTS)` de `test_plan212_characterization.py`
  está en **`:169`** (no `:168`); el `<select>` de modelos de `PlansBoardPage.tsx` abre en
  **`:336`** (no `:338`); las rutas de preferencias son **`:75`** y **`:89`**. Corregidos en el
  texto.
- **C12 (MENOR) — `test_flag_registry_categorization` no existe.** El test real se llama
  **`test_every_registry_flag_is_categorized`**, nombrado en `harness_flags.py:488-489` (Plan 63).
- **C13 (MENOR) — contradicción de nivel de import, reabierta.** La regla 2 de F1 manda importar
  `runtime_capabilities` **a nivel de módulo** en los consumidores, pero los 4 diffs de
  deduplicación lo importaban **dentro de funciones** (`api/agents.py:425` está indentado). v3:
  una regla, con la excepción escrita y el motivo.
- **C14 (MENOR) — la huella de regresión estaba en prosa.** v3 trae la **entrada JSON literal**
  para `docs/sistema/error_fingerprints.json`, con el `id` y el `guard_test`.
- **[ADICIÓN ARQUITECTO] F2.5 Test D — "efecto observable, no consumo simbólico".** El Test A del
  v2 verifica que el parámetro se **use**; no verifica que **cambie algo**. Los bugs C3 y C8 pasan
  el Test A y siguen siendo teatro. El Test D exige que, para todo runtime con
  `supports_effort=True` y capacidad efectiva, dos efforts distintos produzcan **dos valores de
  ejecución distintos** (argv para Claude, `max_turns` para Codex). Es el gate que separa "el
  parámetro se lee" de "el parámetro sirve".
- **[ADICIÓN ARQUITECTO] F2.5 Test E — gate AST del binding de `config`.** Convierte el C2 en un
  invariante: en cada archivo del alcance de este plan, si el módulo hace
  `from config import config` entonces `config.config.X` es **error**; si hace `import config`
  entonces `config.X` (para keys de `FLAG_REGISTRY`) es **error**. Mata la clase entera de
  "gotcha aplicado de memoria sin leer el import".

---

## 0.ter CHANGELOG v1 -> v2 (se conserva íntegro para trazabilidad de las 4 versiones)

- **C1 (BLOQUEANTE) — el presupuesto de turnos de Codex estaba INVERTIDO y era destructivo.** `STACKY_RUNAWAY_MAX_TURNS` vale **`"0"` por default** (`config.py:471-473`) y `RunLimits(max_turns=0)` significa **sin límite** (`harness/runaway_guard.py:8,20,45`). Con la fórmula del v1 (`base + {low:0…max:3}`), elegir **`max`** convertía "ilimitado" en **un cap de 3 turnos** (el guard mataba el run al turno 3) y elegir `low` dejaba el run ilimitado. Y con cap configurado (p. ej. 40), `max` lo subía a **43**, *por encima* del techo de seguridad que puso el operador. Peor: el **test 5 del v1 salía VERDE** con ese comportamiento invertido (`0 < 3` es numéricamente cierto) ⇒ falso verde perfecto. v2: `codex_turn_budget` es **monótono hacia abajo desde el cap**, `0` es sagrado, y hay 4 aserciones que blindan la inversión (§5 F2).
- **C2 (BLOQUEANTE) — el fix de F2 vivía DENTRO de un `if` de dos flags ajenas, así que no cerraba el hueco.** El bloque de `codex_cli_runner.py:582` está gateado por `STACKY_ADAPTIVE_EFFORT_ENABLED` **y** por `_codex_complexity` (que sólo se llena si `STACKY_COMPLEXITY_ESTIMATION_ENABLED`). Con cualquiera OFF, el effort del operador se seguía descartando en silencio — exactamente el bug que el plan dice cerrar. v2: la resolución del effort explícito sale **fuera y antes** del bloque adaptativo, replicando el patrón real de Claude (`claude_code_cli_runner.py:958-961`), + test con las dos flags en OFF.
- **C3 (BLOQUEANTE) — F0 mandaba las 4 keys al archivo equivocado y declaraba "Archivos a editar (2)".** `_CURATED_DEFAULTS_ON` vive en **`backend/tests/test_harness_flags.py:467`**, no en `harness_flags.py` (ahí vive `_CATEGORY_KEYS`, que abre en `:120`). Con `default=True` y sin tocar el test, `test_default_known_only_for_curated` sale **ROJO** en la primera fase. v2: **3 archivos**, cada estructura con su ubicación real (§5 F0). *(v3: son **5** — ver C5 de arriba.)*
- **C4 (BLOQUEANTE) — la lista "cerrada" de 10 call sites estaba incompleta y hacía imposible su propio KPI-2.** Falta **`services/parallel_runs.py:58`** (pasa `model_override` pero **no** `effort_override`). El test AST exige que **todas** las llamadas pasen ambos; con 10 filas editadas y allowlist de 1 reservada a `variant_generator.py`, el criterio nacía rojo. v2: tabla de **11** filas + allowlist de hasta 2 con motivo escrito.
- **C5 (IMPORTANTE) — la clave de preferencia 400eaba con la mayoría de los proyectos.** `_UI_KEY_RE = ^[A-Za-z0-9._-]{1,128}$` rechaza espacios, acentos y paréntesis; y `api.put` **lanza** en non-2xx. Además el endpoint está gateado por `STACKY_UI_SAVED_VIEWS_ENABLED` (`config.py:1810`), que el v1 nunca nombraba. v2: slug determinista + fallback silencioso + dependencia declarada (§5 F4).
- **C6 (IMPORTANTE) — el diff de F4 borraba `downgraded` y `reason` del trace** y rompía `test_plan212_requested_vs_effective.py`, que el propio F7 corre como regresión. v2: el diff los conserva y **F6 los consume** en vez de recalcular la comparación a mano.
- **C7 (IMPORTANTE) — F5 mostraba un cuerpo de `pickerCapabilities` que no es el real y su test 2 nacía rojo.** La función real ya devuelve `note` (leyendo `effort_note`) y calcula `showEfforts` **sin mirar** `effort_mode`. v2: diff sobre el cuerpo real, se reusa `note` (no se duplica), y la línea literal que hace `showEfforts=false` para `no_aplica`.
- **C8 (IMPORTANTE) — el plan se contradecía sobre el nivel de import** ("a nivel de módulo es seguro" en F1 vs "sólo dentro de funciones" en R1). v2: una sola regla, en dos direcciones separadas (§5 F1).
- **C9 (IMPORTANTE) — `load/save_run_preference` invertía la capa y no decía qué símbolo usar.** La lógica del sub-objeto `ui` vive en el **cuerpo de la ruta**, no en una función reusable. v2: se extraen dos helpers puros en `api/preferences.py` que la ruta existente pasa a usar (contrato HTTP intacto).
- **C10 (MENOR)** — se agrega la huella de regresión a `docs/sistema/error_fingerprints.json` (§5 F7).
- **C11 (MENOR)** — se agrega **§9 Convivencia con 260/263/265** (frontera de merge, orden y qué entra en el KPI).
- **C12 (MENOR)** — se aclara que `EFFORTS` es el **vocabulario de validación** y el catálogo la **fuente de presentación**, con un test que impide que se desincronicen.
- **[ADICIÓN ARQUITECTO] F2.5** — centinela ejecutable de paridad: un test AST que prohíbe parámetros de selección **aceptados y nunca consumidos**, y un test parametrizado **derivado de `RUNTIMES`** que obliga a todo runtime futuro a honrar (o declarar) el effort.
- **[ADICIÓN ARQUITECTO] §9.1** — contrato público congelado del 264 para que 260 y 265 construyan contra él sin esperar a que se implemente.

---

## 1. Objetivo y KPI

Stacky ya tiene las tres piezas buenas: el catálogo vivo por runtime
(`services/model_catalog.py`, Plan 159 + 212), la matriz de clamp
(`services/llm_router.py::clamp_model` / `::clamp_effort_for_model`, Plan 212 F2) y un selector reusable
bien diseñado (`components/ModelEffortPicker.tsx`, Plan 212 F4). Lo que falta es **cobertura y unicidad**:

1. **El effort NO llega a Codex — y el camino vivo no es el que parece.** `run_agent(...)` hace un
   **return temprano** para los dos runtimes CLI: `agent_runner.py:144-157`
   (`if runtime in {"codex_cli","claude_code_cli"}: return _start_cli_runtime(...)`, pasándole
   `effort_override=effort_override` en `:154`). Dentro de `_start_cli_runtime`, la rama de Codex
   (`agent_runner.py:439-450`) llama a `start_codex_cli_run(...)` con `model_override=model_override`
   y **sin `effort_override`** (`:449` es la última línea de kwargs) — mientras la rama de Claude
   (`:453-466`) **sí** lo pasa (`:465`). Y `start_codex_cli_run` **ni siquiera acepta** ese parámetro
   (`services/codex_cli_runner.py:87-97`, verificado). **El bloque `agent_runner.py:227-300` — con su
   propia llamada a `start_codex_cli_run` en `:256-265`, también sin effort — es CÓDIGO MUERTO**: el
   `return` de `:145` ya se ejecutó. Es exactamente el mismo falso verde que el Plan 196 creyó
   arreglar para `claude_code_cli` en `:344-350` (otra rama muerta; Claude funciona por `:465`).
   El operador elige "high" y Codex corre como si no hubiera elegido nada.
2. **La lista de efforts está escrita 10 veces** (censo real 2026-07-27 con el grep del KPI-1, ver
   §5 F1): `api/agents.py:425, 681, 717, 934, 963, 1156`, `api/devops_agent.py:15`,
   `api/plans_board.py:176`, `services/adaptive_selector.py:57` (comentario) y
   `services/claude_code_cli_runner.py:2224`. Más **2 ocurrencias partidas en dos líneas** que ese
   grep no ve: `api/devops_remote_console.py:212-213` y `:313-314`. **12 lugares.** Agregar un effort
   nuevo hoy exige tocar 12 y ninguno falla si te olvidás de uno.
3. **11 de 17 puntos de lanzamiento no ofrecen elección.** `run_agent(...)` se llama desde 17 lugares
   fuera de `tests/` y `evals/`; `phase6.py:192`, `phase6.py:229`, `doc_documenter.py:383`,
   `pipeline_orchestrator.py:58`, `slash_commands.py:101`, `variant_generator.py:188`,
   `devops_section_doctor.py:171`, `macros.py:177` y las tres de `parallel_runs.py` (`:58`, `:126`,
   `:169`) **no pasan modelo y/o effort**: corren con lo que caiga.
4. **El selector está cableado en 2 pantallas de 4.** `ModelEffortPicker` sólo lo usan
   `EpicFromBriefModal.tsx:491` y `TicketBoard.tsx:221`. `PlansBoardPage.tsx:147-162,336-357` y
   `IncidentResolverModal.tsx:83-102,414-427` tienen **cada uno su propio selector hecho a mano**, con
   su propia lógica de defaults y degradación.
5. **El historial no registra qué se usó, salvo en Claude.** `build_model_effort_trace` (`:516-540`) y
   `_persist_model_effort_trace` (`:543`) viven sólo en `claude_code_cli_runner.py`. Una corrida de
   Codex no deja rastro del effort pedido vs. el efectivo.
6. **El catálogo vivo no describe a Codex.** `config/model_catalog.json` → `codex_cli` trae
   `efforts: []`, `default_effort: null` y `models: [""]` (id vacío). Cualquier UI alimentada por el
   catálogo **no puede** ofrecer esfuerzo para Codex, por más que el backend lo honre.

| KPI | Antes (medido 2026-07-27, con el comando de la fila) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Literales de la lista de efforts en el backend fuera de `tests/` (grep de §5 F1) | **10** (+2 partidas que el grep no ve = 12 ediciones) | **1** (`services/runtime_capabilities.py`); el grep da **0** |
| **KPI-2** Llamadas a `run_agent(...)` sin resolución de modelo/effort | **11** de 17 | **0** (allowlist máx. 2, con motivo escrito) |
| **KPI-3** Runtimes donde el effort elegido **llega al runner y queda registrado** | **1** (claude) | **3** (claude nativo · codex por presupuesto de turnos · copilot declarado no-aplicable) |
| **KPI-3b [C8]** Runtimes donde el efecto del effort es **observable con la config vigente**, declarado con honestidad en la UI | **1** (claude) — y el plan no lo decía | **3 declarados**: `effort_effective_now` refleja la verdad (Codex = `false` mientras `STACKY_RUNAWAY_MAX_TURNS == 0`) y la nota lo explica |
| **KPI-4** Selectores de modelo/effort hechos a mano en el frontend | **2** | **0**: `ModelEffortPicker` importado en los 2 archivos **y** 0 hits de `effortsForModel`/`EMERGENCY_MODEL_CATALOG`/`setActionEffort` en ellos |
| **KPI-5** Ejecuciones cuyo `metadata_dict["model_effort"]` registra `{tool, requested/effective, effort_mode}` | sólo claude | **los 3 runtimes**, con `downgraded` y `reason` intactos |
| **KPI-6** Parámetros de selección aceptados por un runner y **nunca consumidos** | **1** (`codex`, en el call site vivo) | **0**, verificado por AST en cada corrida del arnés |
| **KPI-7 [C3/C4]** Runtimes cuya **respuesta HTTP** de `/api/agents/model-catalog` declara `effort_mode` + `effort_note` + `efforts` normalizados | **0** | **3** |

---

## 2. Por qué ahora / gap que cierra

El Plan 212 (`212_PLAN_SELECTOR_VIVO_DE_MODELO_Y_EFFORT_EN_TICKETS_ADO_Y_CUMPLIMIENTO_REAL_DE_LA_ELECCION.md`)
puso el título correcto: **"cumplimiento real de la elección"**. Construyó la matriz, el picker y el
trace — pero acotado al tablero de tickets ADO. El Plan 196, al implementarse el 2026-07-26, encontró
por casualidad que **una** rama de `run_agent` descartaba el effort en silencio, y la parcheó con una
línea. Este plan hace lo que faltó: **buscar el resto de los lugares donde la elección se descarta, en
vez de esperar a tropezarlos.**

El gap no es "falta un selector". Es que **la elección tiene 12 fuentes de verdad y 4
implementaciones**, así que cada superficie nueva reinventa la degradación y cada una se equivoca
distinto.

**Lo que ninguna versión anterior había visto (y por eso existen F2.5 D y E):** el sistema no tiene
forma de detectar (a) que un parámetro de selección fue aceptado y nunca usado, (b) que fue usado pero
**sin efecto observable**, ni (c) que la línea que lo usa está en una rama **muerta**. Arreglar Codex a
mano deja los tres agujeros abiertos para el runtime número 4. Por eso el plan no arregla un caso:
instala los centinelas que hacen imposible el caso.

---

## 3. Principios y guardarraíles

1. **3 runtimes con paridad explícita, incluida la degradación honesta.** El effort **no existe** como
   flag de línea de comandos en Codex: `codex_cli_runner.py:580` lo dice literalmente — *"Codex no
   tiene --effort; se ajusta el presupuesto de turnos bajo el cap"*. Nótese **"bajo el cap"**: el
   presupuesto se mueve **hacia abajo desde el techo**, nunca hacia arriba. Y GitHub Copilot Pro no
   expone effort en absoluto. La regla: **la capacidad se declara, no se finge**. Cada runtime declara
   `effort_mode` ∈ `{"nativo", "presupuesto_turnos", "no_aplica"}`, y la UI muestra al operador qué va
   a pasar realmente con su elección. **Prohibido** mostrar un selector que no hace nada.
2. **[C8] Y prohibido también afirmar un efecto que hoy no ocurre.** Si `STACKY_RUNAWAY_MAX_TURNS == 0`
   (default), el esfuerzo elegido en Codex **no cambia la corrida**: se registra en el trace y se
   aplicará el día que el operador ponga un cap. Eso se declara en `effort_effective_now` y se dice en
   la nota, en castellano. Prometer menos y cumplir es la regla; **el selector se sigue mostrando**
   (la elección se guarda y es real el día que hay cap), pero **con la verdad al lado**.
3. **Cero trabajo extra para el operador.** Todo tiene default: el catálogo trae `default_model` y
   `default_effort`, y donde no los trae los completa `capabilities_for()` (§5 F1). Si el operador no
   toca nada, se comporta como hoy o mejor. Todas las flags de este plan nacen **ON**.
4. **Human-in-the-loop.** La resolución **nunca** escala el effort por su cuenta por encima de lo que
   el operador pidió explícitamente. El selector adaptativo (`services/adaptive_selector.py`) sigue
   siendo el piso, no el techo: **un override explícito siempre gana** (es la regla que ya respeta
   `claude_code_cli_runner.py:958-961`).
5. **Mono-operador sin auth.** La preferencia se guarda por **proyecto**, no por usuario. Nada de RBAC.
6. **Backward-compatible.** `_clamp_effort_for_model` (`api/agents.py:612`) y `CLI_VALID_EFFORTS`
   (`claude_code_cli_runner.py:2224`) **se conservan como delegadores**. No se borra ningún símbolo
   público **ni ninguna clave de un dict público** (`downgraded` y `reason` del trace se conservan).
   Las firmas de `run_agent`, `_start_cli_runtime`, `start_claude_code_cli_run` y `start_codex_cli_run`
   sólo ganan parámetros keyword-only con default `None`. La respuesta del endpoint del catálogo sólo
   **gana** campos.
7. **No degradar — y en particular, no tocar el techo de seguridad.** El módulo nuevo es aritmética
   pura sobre un dict ya cacheado. Cero I/O nuevo, cero red, cero llamada a modelo.
   `load_model_catalog()` ya tiene su caché TTL 300 s (`model_catalog.py:16`) y no se toca.
   **Invariante duro:** ninguna elección de effort puede aumentar `max_turns` del `RunawayGuard` por
   encima de `config.STACKY_RUNAWAY_MAX_TURNS`, ni convertir "sin límite" (`0`) en un límite. **Y
   [C7]:** con el adaptativo encendido y sin override, el presupuesto resultante debe ser **idéntico**
   al de hoy para los 5 efforts.
8. **[C2 — REGLA NUEVA, DURA] El binding de `config` se lee del `import` del archivo, nunca de
   memoria.** Hay dos formas en este repo y el gotcha aplica **al revés** en cada una:
   - `from config import config` (p. ej. `services/codex_cli_runner.py:22`,
     `services/claude_code_cli_runner.py:49`) ⇒ el nombre local **ya es la instancia**. Se escribe
     **`getattr(config, "STACKY_X", default)`**. Escribir `config.config.X` levanta `AttributeError`.
   - `import config` ⇒ el nombre local es el **módulo**. Se escribe **`config.config.X`**; leer
     `config.X` devuelve el valor de clase y **mata el branch OFF**.
   Antes de escribir la primera línea de un archivo, corré
   `grep -n "^from config import\|^import config" <archivo>`. F2.5 Test E lo convierte en gate.
9. **Reusar.** Catálogo del 159/212, clamp del `llm_router`, picker del 212 F4, preferencias de
   `api/preferences.py`, telemetría del 171/258, `ModelDecisionChip` del 212. **No se crea ningún
   catálogo nuevo, ningún endpoint nuevo, ningún chip nuevo.**

---

## 4. Glosario

| Término | Significado |
|---|---|
| **runtime / herramienta** | `claude_code_cli`, `codex_cli` o `github_copilot`. Es lo que el usuario llama "herramienta o proveedor". |
| **catálogo** | `config/model_catalog.json` leído por `services/model_catalog.py`, con `models`, `efforts`, `effort_support`, `effort_degrade`, `default_model`, `default_effort` por runtime. **Ojo:** hoy sólo `claude_code_cli` está completo (§1.6). |
| **clamp de modelo** | `llm_router.clamp_model`: mapea tiers prohibidos (opus/fable) a `CLAUDE_CAP_MODEL = "claude-sonnet-5"` salvo `allow_opus`. |
| **clamp de effort** | `llm_router.clamp_effort_for_model`: baja el effort al máximo que soporta el modelo elegido. |
| **effort_mode** | **NUEVO**: cómo un runtime materializa el effort. `nativo` (flag del CLI), `presupuesto_turnos` (fracción del cap de turnos) o `no_aplica`. |
| **effort_effective_now** | **NUEVO [C8]**: si con la configuración vigente ese modo produce un efecto observable. Para `presupuesto_turnos` es `STACKY_RUNAWAY_MAX_TURNS > 0`. |
| **cap de turnos** | `config.STACKY_RUNAWAY_MAX_TURNS`. **`0` = sin límite.** Techo de seguridad del `RunawayGuard`; el effort sólo puede moverse **por debajo** de él. |
| **selección resuelta** | **NUEVO**: la tupla `(runtime, model, effort_requested, effort_effective, origen)` que sale de `resolve_run_selection()`. |
| **origen** | De dónde salió cada valor: `"explicito"`, `"preferencia"`, `"adaptativo"` o `"default_catalogo"`. |
| **trace** | El dict que `build_model_effort_trace` persiste en `metadata_dict["model_effort"]`. Claves existentes que **no se tocan**: `requested_model`, `effective_model`, `requested_effort`, `effective_effort`, `downgraded`, `reason`. |
| **rama muerta** | Código inalcanzable por un `return` anterior. En este plan: `agent_runner.py:227-300` y `:302-400`. Se parchea igual (higiene), pero **nunca** se confunde con el arreglo. |

---

## 5. Fases

### F(-1) — [ADICIÓN ARQUITECTO] Pre-flight de anclajes: verificar antes de confiar

**Objetivo.** El C2 de esta ronda (v3→v4) encontró 11 citas archivo:línea viejas por la costura de
los planes 259/267/268/269/270, mergeados a `main` DESPUÉS de que este plan se ancló. Ese drift no es
un accidente de este plan puntual: `config.py` y `services/harness_flags.py` son estructuras que
CUALQUIER plan hermano en curso puede volver a mover entre el momento en que leés este documento y el
momento en que lo implementás — incluso si lo implementás mañana mismo. En vez de prometer (otra vez)
que los números de línea son correctos, este paso los **vuelve a medir** antes de tocar nada.

**No hay código de producción en esta fase. No es una flag ni un test nuevo del arnés — es un
comando de una línea que corré vos, a mano, antes de F0**, exactamente como F0 ya hace con
`STACKY_MODEL_PROBE_ENABLED` y F1 con la verificación de imports:

```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -c "
import re
CHECKS = {
    'Stacky Agents/backend/config.py': ['STACKY_RUNAWAY_MAX_TURNS', 'STACKY_COMPLEXITY_ESTIMATION_ENABLED', 'STACKY_ADAPTIVE_EFFORT_ENABLED', 'STACKY_MODEL_PROBE_ENABLED', 'STACKY_UI_SAVED_VIEWS_ENABLED'],
    'Stacky Agents/backend/services/harness_flags.py': ['_CATEGORY_KEYS', 'FLAG_REGISTRY', 'def default_is_known'],
    'Stacky Agents/backend/tests/test_harness_flags.py': ['_CURATED_DEFAULTS_ON', 'def test_default_known_only_for_curated'],
    'Stacky Agents/backend/tests/test_harness_flags_requires.py': ['_REQUIRES_MAP_FROZEN', 'def test_requires_map_is_frozen'],
    'Stacky Agents/frontend/src/api/endpoints.ts': ['interface RuntimeModelCatalog'],
}
for path, symbols in CHECKS.items():
    lines = open(path, encoding='utf-8').read().splitlines()
    for sym in symbols:
        hits = [i + 1 for i, l in enumerate(lines) if sym in l]
        print(f'{path} :: {sym!r} -> lineas {hits}')
"
```

**Qué hacer con la salida:** para cada símbolo, comparalo contra el número que este documento cita en
la sección correspondiente (F0, F1, F2, F4, F5). Si difiere, **usá el número que acabás de medir, no
el del documento** — y seguí adelante: ningún fix de este plan depende de que el número fuera exacto
(los diffs reales anclan por contenido/símbolo, nunca por línea fija), así que un desvío acá **no**
bloquea F0; sólo actualiza tu propia referencia mental antes de editar. Si algún símbolo da **cero**
líneas (no **movió**, sino que **desapareció**), ahí sí parar: eso es señal de que el archivo cambió
de forma más profunda que un simple corrimiento de línea, y merece revisar el drift a mano antes de
seguir.

**Por qué esto es una mejora real y no ceremonia:** convierte una promesa de prosa ("los anclajes son
correctos a tal fecha") en un chequeo ejecutable de 15 segundos que cualquier runtime (Claude Code,
Codex CLI, Copilot) puede correr igual, sin ambigüedad, y que sigue siendo útil aunque pasen semanas
entre que se escribe este plan y se implementa. Es la misma filosofía que el plan ya aplica en F2.5
("instala los centinelas que hacen imposible el caso") aplicada a la propia vigencia del documento.

**Trabajo del operador: ninguno** (comando de una vez, para quien implementa, no una flag ni una
pantalla nueva).

---

### F0 — Flags (la receta completa: 5 archivos, 5 estructuras)

**Objetivo.** Dar de alta las 4 flags del plan **sin poner en rojo ninguno de los guards del arnés**.

> **[FIX C5] Lección: una flag son CINCO patas, no tres.** El v1 acertó una, el v2 tres, y las dos que
> faltaban ponen rojo un archivo que el propio F0 corre como criterio binario:
> - `default_is_known(spec)` es `spec.default is not None` (`services/harness_flags.py:5814` —
>   **[FIX C2 v3→v4]** el v3 citaba `:5503`; el archivo creció ~311 líneas entre el 2026-07-27 del v3
>   y hoy por la costura de los planes 259/267/268/269/270. **Re-verificá con
>   `grep -n "def default_is_known" services/harness_flags.py` antes de confiar en el número**: este
>   archivo se mueve cada vez que se mergea un plan hermano) y
>   `test_default_known_only_for_curated` (`tests/test_harness_flags.py:~1001` — v3 citaba
>   `:974-982`, mismo motivo) exige **igualdad exacta de conjuntos** contra `_CURATED_DEFAULTS_ON`
>   (`tests/test_harness_flags.py:467` — este SÍ verificado estable, no drifted).
> - `_CATEGORY_KEYS` abre en `harness_flags.py:120` (verificado estable); sin la key ahí,
>   **`test_every_registry_flag_is_categorized`** rompe a propósito (así lo dice la nota de
>   `harness_flags.py:515`, Plan 63 — **[FIX C2 v3→v4]** v3 citaba `:488-489`; `FLAG_REGISTRY` abre
>   hoy en `:516`, no `:490`). **[C12]** ese es el nombre real del test; el v2 lo llamaba
>   `test_flag_registry_categorization`, que **no existe**.
> - **`_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`, estable)** se compara por
>   **igualdad exacta** en `test_requires_map_is_frozen` (`tests/test_harness_flags_requires.py:~326`
>   — **[FIX C2 v3→v4]** v3 citaba `:312-320`): toda flag con `requires=` debe estar ahí o el test la
>   reporta como *"Extras"*.
> **Regla para el implementador:** `harness_flags.py` y `config.py` son los dos archivos que CADA
> plan hermano vuelve a mover (crecen con cada FlagSpec/_CURATED_DEFAULTS_ON/_REQUIRES_MAP_FROZEN
> nuevos). Cualquier número de línea citado en este documento para esos dos archivos puede volver a
> estar viejo el día que lo implementes: confirmá con `grep -n "<símbolo>" <archivo>` antes de asumir
> la línea exacta. Los símbolos en sí (los nombres) sí son estables; los números, no.
> - **`PLAIN_HELP` (`services/harness_flags_help.py:25`)** debe cubrir el **100 %** de
>   `FLAG_REGISTRY` sin huérfanas (`tests/test_harness_flags_help.py:33-40`), y cada entrada tiene
>   `on_effect`/`off_effect` de **≤ 240 caracteres** (`:49-50`).

**Archivos a editar (5) — ubicación real de cada estructura:**

| # | Archivo | Estructura | Dónde |
|---|---|---|---|
| 1 | `Stacky Agents/backend/config.py` | los 4 `os.getenv(...)` | junto a `STACKY_MODEL_PROBE_ENABLED` (`config.py:1273-1274` — **[FIX C2 v3→v4]** v3 citaba `:1258`; re-ubicalo con el grep de abajo, no confíes en el número) |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | los 4 `FlagSpec` **y** las 4 keys en `_CATEGORY_KEYS` | `FLAG_REGISTRY` (abre hoy en `:516`, **[FIX C2 v3→v4]** v3 decía `:490`); `_CATEGORY_KEYS` abre en `:120` (estable) |
| 3 | `Stacky Agents/backend/services/harness_flags_help.py` | **[C5]** las 4 entradas de `PLAIN_HELP` | el dict abre en `:25` |
| 4 | `Stacky Agents/backend/tests/test_harness_flags.py` | las 4 keys en `_CURATED_DEFAULTS_ON` | `:467` |
| 5 | `Stacky Agents/backend/tests/test_harness_flags_requires.py` | **[C5]** las **3** keys con `requires=` en `_REQUIRES_MAP_FROZEN` | `:120` |

**1) `config.py`** — insertar en el mismo bloque donde vive `STACKY_MODEL_PROBE_ENABLED` (ubicalo con
`grep -n "STACKY_MODEL_PROBE_ENABLED" config.py`), siguiendo el patrón literal de las líneas vecinas:

```python
    # Plan 264 — una sola matriz de capacidades de runtime/modelo/effort.
    STACKY_RUNTIME_CAPABILITIES_ENABLED: bool = os.getenv(
        "STACKY_RUNTIME_CAPABILITIES_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_CODEX_EFFORT_PARITY_ENABLED: bool = os.getenv(
        "STACKY_CODEX_EFFORT_PARITY_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_RUN_SELECTION_PREFS_ENABLED: bool = os.getenv(
        "STACKY_RUN_SELECTION_PREFS_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_MODEL_PICKER_EVERYWHERE_ENABLED: bool = os.getenv(
        "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
```

**2) `services/harness_flags.py`** — 4 `FlagSpec` en `FLAG_REGISTRY`. Las 4 llevan `default=True`
(nacen ON, y **por eso mismo** hay que curarlas en el paso 4). Ninguna lleva `env_only=True`: son
configuración del operador y se editan por UI (regla dura del repo).

```python
    # ── Plan 264 — herramienta/modelo/effort elegibles en todo punto de uso ──
    FlagSpec(
        key="STACKY_RUNTIME_CAPABILITIES_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Matriz unica de capacidades de runtime",
        description=(
            "Plan 264 — Una sola fuente para 'que modelos y efforts admite cada "
            "herramienta y como degrada'. Reemplaza las 12 copias de la lista de "
            "efforts. Calculo puro sobre el catalogo ya cacheado."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CODEX_EFFORT_PARITY_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="El effort elegido llega tambien a Codex",
        description=(
            "Plan 264 — Codex no tiene --effort: el esfuerzo elegido se traduce a "
            "una fraccion del cap de turnos, siempre POR DEBAJO del cap. Hoy se "
            "descarta en silencio (agent_runner.py:442-450). Solo aplica a corridas "
            "que el operador lanza; no enciende ningun proceso de fondo."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",   # → _REQUIRES_MAP_FROZEN
    ),
    FlagSpec(
        key="STACKY_RUN_SELECTION_PREFS_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Recordar herramienta/modelo/effort por proyecto",
        description=(
            "Plan 264 — La ultima eleccion del operador se guarda en el archivo de "
            "preferencias de Stacky (api/preferences.py) y se preselecciona la "
            "proxima vez. Un override explicito siempre gana. Requiere que el store "
            "de preferencias de UI este activo (STACKY_UI_SAVED_VIEWS_ENABLED)."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",   # → _REQUIRES_MAP_FROZEN
    ),
    FlagSpec(
        key="STACKY_MODEL_PICKER_EVERYWHERE_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Selector de modelo/effort en todas las pantallas",
        description=(
            "Plan 264 — El mismo ModelEffortPicker (Plan 212 F4) en el tablero de "
            "planes, la bandeja de incidencias y las secciones DevOps, en vez de un "
            "selector distinto hecho a mano en cada pantalla."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",   # → _REQUIRES_MAP_FROZEN
    ),
```

y **en el mismo archivo**, agregar las 4 keys a `_CATEGORY_KEYS` (`harness_flags.py:120`), en la
categoría donde ya vive `"STACKY_MODEL_PROBE_ENABLED"` (ubicala con
`grep -n "STACKY_MODEL_PROBE_ENABLED" services/harness_flags.py`). Sin esto,
**`test_every_registry_flag_is_categorized`** sale rojo.

**3) [C5] `services/harness_flags_help.py:25`** — 4 entradas nuevas en `PLAIN_HELP`. Respetá el
**límite de 240 caracteres** en `on_effect` y `off_effect` (`test_harness_flags_help.py:49-50`) y el
tono llano del resto del archivo (una analogía por entrada):

```python
    # ── Plan 264 ──────────────────────────────────────────────────────────
    "STACKY_RUNTIME_CAPABILITIES_ENABLED": PlainHelp(
        what="Una sola tabla que dice qué modelos y qué niveles de esfuerzo acepta cada herramienta, y a qué degrada cada combinación.",
        on_effect="Si la activás: todas las pantallas y todos los lanzadores usan la misma tabla, así que ofrecen exactamente lo que la herramienta puede hacer.",
        off_effect="Si la apagás: cada pantalla vuelve a su propia lista, y algunas pueden ofrecer opciones que la herramienta no acepta.",
        example="Como tener una única carta para todo el restaurante en vez de una distinta por mesa.",
    ),
    "STACKY_CODEX_EFFORT_PARITY_ENABLED": PlainHelp(
        what="Hace que el nivel de esfuerzo que elegís también valga para Codex, traduciéndolo a cuántos turnos de trabajo se le permiten.",
        on_effect="Si la activás: elegir 'bajo' hace que Codex trabaje menos turnos, siempre por debajo del límite que vos configuraste.",
        off_effect="Si la apagás: Codex ignora el esfuerzo elegido y corre como hasta ahora.",
        example="Como decirle a alguien 'dale una revisada rápida' en vez de 'revisalo a fondo'.",
    ),
    "STACKY_RUN_SELECTION_PREFS_ENABLED": PlainHelp(
        what="Recuerda por proyecto la última herramienta, modelo y esfuerzo que elegiste, y te los deja preseleccionados.",
        on_effect="Si la activás: cada proyecto abre con la elección que usaste la última vez; podés cambiarla siempre.",
        off_effect="Si la apagás: cada pantalla arranca con el valor por defecto del catálogo.",
        example="Como el auto que recuerda la posición de tu asiento.",
    ),
    "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED": PlainHelp(
        what="Usa el mismo selector de modelo y esfuerzo en todas las pantallas que lanzan trabajo.",
        on_effect="Si la activás: el control se ve y se comporta igual en todos lados, y se adapta a lo que cada herramienta soporta.",
        off_effect="Si la apagás: cada pantalla muestra su propio selector, con reglas distintas.",
        example="Como que todos los ascensores del edificio tengan la botonera igual.",
    ),
```

**4) `tests/test_harness_flags.py:467`** — agregar las 4 keys al conjunto `_CURATED_DEFAULTS_ON`:

```python
    "STACKY_RUNTIME_CAPABILITIES_ENABLED",      # Plan 264
    "STACKY_CODEX_EFFORT_PARITY_ENABLED",       # Plan 264
    "STACKY_RUN_SELECTION_PREFS_ENABLED",       # Plan 264
    "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED",   # Plan 264
```

**5) [C5] `tests/test_harness_flags_requires.py:120`** — agregar las **3** entradas al
`_REQUIRES_MAP_FROZEN` (respetando el formato `"hija": "madre"` y el comentario de motivo que usa el
resto del dict):

```python
    # Plan 264: la paridad de effort en Codex, la preferencia por proyecto y el
    # selector unico solo tienen sentido si la matriz unica de capacidades esta
    # activa (es quien resuelve y clampea). Profundidad 1: la madre
    # STACKY_RUNTIME_CAPABILITIES_ENABLED no declara requires (R4).
    "STACKY_CODEX_EFFORT_PARITY_ENABLED": "STACKY_RUNTIME_CAPABILITIES_ENABLED",
    "STACKY_RUN_SELECTION_PREFS_ENABLED": "STACKY_RUNTIME_CAPABILITIES_ENABLED",
    "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED": "STACKY_RUNTIME_CAPABILITIES_ENABLED",
```

> **Regla espejo (por si alguna de estas flags se decidiera OFF en el futuro):** una flag que nace OFF
> **NO debe** escribir `default=False` en su `FlagSpec` (`False is not None` ⇒ `default_is_known=True`
> ⇒ exige estar en el conjunto curado ⇒ rojo). Se declara **omitiendo `default=`** y dejando el
> default efectivo en `config.py` (`"false"`). Precedente idéntico, con el motivo escrito, en
> `services/harness_flags.py:3168-3180` (`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED`, Plan 250). En este
> plan **las 4 nacen ON**, así que las 4 llevan `default=True` **y** van al conjunto curado.

**Por qué las 4 nacen ON (justificación explícita):** ninguna enciende loops, daemons, barridos,
polling ni prefetch, y **ninguna dispara una llamada a un modelo/CLI en reposo** — no hay
**categoría (A)**. Ninguna escribe en ADO/GitLab/repo remoto, ni ejecuta DDL/DML, ni despliega, ni
borra datos, ni decide por el operador — no hay **categoría (B)**. Detalle por flag:

- `STACKY_RUNTIME_CAPABILITIES_ENABLED`: aritmética pura sobre un dict cacheado. Cero I/O.
- `STACKY_CODEX_EFFORT_PARITY_ENABLED`: sólo se evalúa **dentro** de una corrida que el operador lanzó,
  y con el esfuerzo que él eligió. Tras C1/C7, **nunca sube el gasto por encima del cap** ni por
  encima del presupuesto que la corrida ya tenía hoy: sólo puede bajarlo. Es on-demand y acotado.
- `STACKY_RUN_SELECTION_PREFS_ENABLED`: escribe únicamente en `data/preferences.json` de Stacky, que
  `api/preferences.py` ya escribe hoy. No es un sistema del operador.
- `STACKY_MODEL_PICKER_EVERYWHERE_ENABLED`: render de UI. Cero llamadas.

> **Nota sobre `STACKY_MODEL_PROBE_ENABLED` (flag AJENA, ya existente, default ON).** Este plan **la
> reusa como lectura** vía `model_catalog`, pero **NO** la enciende, **NO** la extiende y **NO** agrega
> ningún sondeo nuevo. El probe vive en `model_catalog._merge_probe` (definido en
> **`model_catalog.py:111`**; el import de `claude_code_cli_runner` está en `:135`), corre sólo cuando
> alguien **pide** el catálogo, y está corto-circuitado bajo `STACKY_TEST_MODE`. **Prohibido en este
> plan:** llamar a `capabilities_for()` / `resolve_run_selection()` desde cualquier loop, timer, hook
> de arranque o barrido de fondo. Si una fase futura necesitara eso, cae en categoría (A) y la flag
> correspondiente nace OFF.

**Tests:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
```
**Criterio binario.** Ambos exit 0. En particular `test_default_known_only_for_curated` **verde** (el
que el v1 dejaba rojo) y `test_requires_map_is_frozen` **verde** (el que el v2 dejaba rojo).
**Validación separada de `PLAIN_HELP` (no corras el archivo entero: tiene 4 fallos ajenos):**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.harness_flags import FLAG_REGISTRY; from services.harness_flags_help import PLAIN_HELP; ks={s.key for s in FLAG_REGISTRY}; miss=sorted(ks-set(PLAIN_HELP)); orph=sorted(set(PLAIN_HELP)-ks); bad=[k for k,v in PLAIN_HELP.items() if len(v.on_effect)>240 or len(v.off_effect)>240]; print('missing',miss); print('orphans',orph); print('too_long',bad); assert not miss and not orph and not bad"
```
debe imprimir las tres listas **vacías** y no lanzar.
**Impacto por runtime:** ninguno (configuración). **Trabajo del operador: ninguno.**

---

### F1 — Backend: `services/runtime_capabilities.py`, la única matriz (TDD)

**Objetivo.** Un solo módulo que responda "¿qué admite esta herramienta, cómo degrada y qué efecto
tiene hoy?", que las 12 copias de la lista de efforts pasen a delegar en él, y que **el catálogo que
sale por HTTP declare esa capacidad**.

**Archivo a crear:** `Stacky Agents/backend/services/runtime_capabilities.py`.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_runtime_capabilities.py`.

> **[FIX C8 v1→v2 / C13 v2→v3] Regla ÚNICA de imports (dos direcciones, una excepción escrita):**
> 1. **Hacia afuera:** `runtime_capabilities.py` importa `model_catalog`, `llm_router` y `config`
>    **SIEMPRE dentro de las funciones**, nunca en el top-level del módulo. Motivo: `model_catalog`
>    importa `claude_code_cli_runner` (`model_catalog.py:135`), que a su vez va a importar
>    `runtime_capabilities` ⇒ ciclo si el top-level lo resolviera.
> 2. **Hacia adentro:** los consumidores importan `runtime_capabilities` **a nivel de módulo** cuando
>    el símbolo se usa a nivel de módulo (caso `claude_code_cli_runner.py:2224`, que define una
>    constante), y **dentro de la función** cuando el símbolo se usa dentro de una función (casos
>    `api/agents.py:425`, `api/devops_remote_console.py`, `services/codex_cli_runner.py`). Las dos
>    formas son seguras por la regla 1; la elección la dicta **dónde se usa el símbolo**, no el gusto.
>
> **[C2] Y la regla de binding de `config` (§3.8): dentro de `runtime_capabilities.py`, que importa
> config dentro de funciones, se escribe:**
> ```python
> from config import config as _cfg          # _cfg ES la instancia (config.py:2137)
> if not getattr(_cfg, "STACKY_RUNTIME_CAPABILITIES_ENABLED", True):
> ```
> El test monkeypatchea **`config.config.STACKY_...`** — el mismo objeto. **Nunca** `_cfg.config`.
>
> Verificación obligatoria **antes de seguir a F2**:
> ```powershell
> "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); import services.runtime_capabilities, services.claude_code_cli_runner, services.codex_cli_runner, api.agents, api.devops_agent, api.devops_remote_console; print('ok')"
> ```

**(a) Contrato (símbolos exactos):**

```python
# El ÚNICO literal de efforts del backend. Todo lo demás delega acá.
# [FIX C12 v1→v2] Esto es el VOCABULARIO DE VALIDACIÓN (qué strings son legales).
# La FUENTE DE PRESENTACIÓN (labels, orden, soporte por modelo) sigue siendo el
# catálogo: config/model_catalog.json — normalizado por capabilities_for(). Ver test 22.
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
EFFORT_ORDER: dict[str, int] = {e: i for i, e in enumerate(EFFORTS)}

RUNTIMES: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

# Cómo materializa el effort cada runtime. Declarativo, no inferido.
EFFORT_MODE: dict[str, str] = {
    "claude_code_cli": "nativo",              # el CLI acepta el esfuerzo directo
    "codex_cli":       "presupuesto_turnos",  # codex_cli_runner.py:580 — no hay --effort
    "github_copilot":  "no_aplica",           # el bridge no expone esfuerzo
}

# [FIX C1 v1→v2 + C7 v2→v3] Fracción del CAP de turnos por esfuerzo en codex.
# SIEMPRE <= 1.0: el effort sólo mueve el presupuesto HACIA ABAJO desde el techo.
# `medium` vale 1.0 A PROPÓSITO: es EXACTAMENTE lo que hace el código de hoy
# (codex_cli_runner.py:591-592 sólo divide cuando el esfuerzo es `low`). Cambiarlo
# a 0.75 recortaría un 25% el presupuesto del caso más común sin que nadie lo pida.
CODEX_EFFORT_TURN_FACTOR: dict[str, float] = {
    "low": 0.5, "medium": 1.0, "high": 1.0, "xhigh": 1.0, "max": 1.0,
}


def is_valid_effort(effort: str | None) -> bool:
    """True si `effort` (case-insensitive, sin espacios) está en EFFORTS."""


def capabilities_for(runtime: str) -> dict:
    """Capacidades REALES de un runtime, leyendo y NORMALIZANDO el catálogo vivo.

    Devuelve SIEMPRE estas claves (nunca lanza, nunca devuelve None):
      {
        "runtime": str,
        "known": bool,                  # False si `runtime` no está en RUNTIMES
        "effort_mode": str,             # "nativo" | "presupuesto_turnos" | "no_aplica"
        "effort_effective_now": bool,   # [C8] ¿el modo produce efecto con la config vigente?
        "supports_model": bool,         # hay >=1 modelo elegible (con id NO vacío)
        "supports_effort": bool,        # effort_mode != "no_aplica"
        "models": list[dict],           # del catálogo, SIN entradas de id vacío
        "efforts": list[dict],          # [{"id","label"}]; [] sólo si no aplica
        "default_model": str | None,
        "default_effort": str | None,
        "effort_note": str,             # frase corta para la UI, en español
      }

    [FIX C3] NORMALIZACIÓN OBLIGATORIA — el catálogo vivo está incompleto:
      `config/model_catalog.json` trae para `codex_cli` -> efforts: [],
      default_effort: null, models: [""]. Sin normalizar, la UI no puede ofrecer
      esfuerzo para Codex por más que el backend lo honre. Reglas:
      1. models = [m for m in (bloque.get("models") or []) if (m.get("id") or "").strip()]
      2. si effort_mode != "no_aplica" y el bloque no trae `efforts`:
             efforts = [{"id": e, "label": e} for e in EFFORTS]
      3. si effort_mode == "no_aplica": efforts = [] SIEMPRE (aunque el catálogo traiga).
      4. default_effort = bloque["default_effort"] si es válido; si no y
         effort_mode != "no_aplica" -> "medium"; si no -> None.
      5. default_model = bloque["default_model"] si NO es vacío tras strip; si no,
         el id del primer modelo de (1); si no hay, None.

    `effort_effective_now` por modo:
      nativo              -> True
      presupuesto_turnos  -> getattr(_cfg, "STACKY_RUNAWAY_MAX_TURNS", 0) > 0
      no_aplica           -> False

    `effort_note` por modo (y por effect):
      nativo              -> "El esfuerzo se le pasa directo a la herramienta."
      presupuesto_turnos + effective -> "Codex no acepta un esfuerzo explícito: se traduce a cuántos turnos de trabajo se le permiten, siempre por debajo del límite configurado."
      presupuesto_turnos + NO effective -> "Codex no acepta un esfuerzo explícito: se traduce a turnos de trabajo. Hoy no hay límite de turnos configurado, así que tu elección queda registrada pero no cambia esta corrida."
      no_aplica           -> "Esta herramienta no expone niveles de esfuerzo; el selector no se muestra."
    """


def clamp_selection(runtime: str, model: str | None, effort: str | None,
                    *, allow_opus: bool = False) -> dict:
    """Ajusta (model, effort) a lo que el runtime realmente soporta.

    Devuelve {"model": str|None, "effort": str|None,
              "effort_requested": str|None, "degraded": bool, "reason": str|None}.
    - Delega el clamp de modelo en llm_router.clamp_model(model, allow_opus)
      SOLO para claude_code_cli (los otros runtimes no usan modelos Claude).
    - Delega el clamp de effort en llm_router.clamp_effort_for_model(effort, model)
      SOLO para claude_code_cli (la matriz effort_support es de modelos Claude).
    - Si effort_mode == "no_aplica" -> effort=None, degraded=True,
      reason="github_copilot no expone niveles de esfuerzo".
    - Un effort inválido cae al default_effort NORMALIZADO, degraded=True.
    - Si getattr(_cfg, "STACKY_RUNTIME_CAPABILITIES_ENABLED", True) es False ->
      devuelve (model, effort) sin tocar y degraded=False.
    NUNCA lanza.
    """


def codex_turn_budget(effort: str | None, cap_turns: int) -> int:
    """[FIX C1 v1→v2] Turnos que le corresponden a Codex para ese esfuerzo.

    CONTRATO DURO (el v1 lo tenía invertido y era destructivo):
      - `cap_turns <= 0` significa SIN LÍMITE (RunLimits(max_turns=0) = sin límite,
        harness/runaway_guard.py:8,20,45). En ese caso devuelve SIEMPRE 0,
        cualquiera sea el esfuerzo. Nunca convierte "sin límite" en un límite.
      - Con `cap_turns > 0`: devuelve `max(1, int(cap_turns * factor))`, con
        factor = CODEX_EFFORT_TURN_FACTOR[effort]. **Nunca > cap_turns.**
      - `effort` None o inválido -> `cap_turns` sin cambio.
      - Es monótono no decreciente en el orden de EFFORTS.
      - [C7] Para los 5 efforts coincide EXACTAMENTE con lo que hace el código de
        hoy (`cap//2` sólo para `low`, `cap` para el resto).
    Nunca lanza.
    """
```

**(b) Casos de test (mínimo 24):**

| # | Caso | Aserción |
|---|---|---|
| 1 | `EFFORTS` | `== ("low","medium","high","xhigh","max")` |
| 2 | `is_valid_effort("HIGH ")` | `True` (normaliza) |
| 3 | `is_valid_effort("turbo")` / `None` / `""` | `False` |
| 4 | `capabilities_for("claude_code_cli")["effort_mode"]` | `"nativo"` |
| 5 | `capabilities_for("codex_cli")["effort_mode"]` | `"presupuesto_turnos"` |
| 6 | `capabilities_for("github_copilot")["supports_effort"]` | `False` y `efforts == []` |
| 7 | `capabilities_for("inventado")["known"]` | `False`, y no lanza |
| 8 | `capabilities_for(...)` con el catálogo caído (monkeypatch que hace lanzar a `load_model_catalog`) | devuelve el dict completo igual, con **todas** las claves del contrato |
| 9 | `clamp_selection("claude_code_cli","claude-opus-4-8","max")` | `model == "claude-sonnet-5"`, `degraded is True` |
| 10 | idem con `allow_opus=True` | `model == "claude-opus-4-8"` |
| 11 | `clamp_selection("claude_code_cli","claude-haiku-4-5","max")` | `effort == "high"` (según `effort_degrade` del catálogo), `degraded is True` |
| 12 | `clamp_selection("github_copilot", None, "high")` | `effort is None`, `degraded is True`, `reason` no vacío |
| 13 | `clamp_selection("codex_cli", None, "high")` | `effort == "high"` (se conserva; lo materializa el presupuesto) |
| 14 | `clamp_selection("claude_code_cli", None, "turbo")` | `effort == default_effort` normalizado, `degraded is True` |
| 15 | `clamp_selection(...)["effort_requested"]` | siempre trae lo pedido original, aunque haya degradado |
| 16 | `codex_turn_budget("max", 0)` y `codex_turn_budget("low", 0)` | **ambos `== 0`** (sin límite se mantiene sin límite) |
| 17 | `codex_turn_budget(e, 40) <= 40` **para los 5 efforts** | `True` en los 5 (el effort NUNCA sube el cap) |
| 18 | `codex_turn_budget("low", 40)` vs `codex_turn_budget("max", 40)` | `presupuesto("low") == 20 < presupuesto("max") == 40` |
| 19 | `codex_turn_budget(None, 40)` / `codex_turn_budget("turbo", 40)` | `40` (sin cambio) |
| 20 | `codex_turn_budget("medium", 1)` | `>= 1` (nunca 0 con cap>0: 0 significaría "sin límite") |
| 21 | flag OFF (`monkeypatch.setattr(config.config, "STACKY_RUNTIME_CAPABILITIES_ENABLED", False)`) | `clamp_selection` devuelve `(model, effort)` sin tocar y `degraded is False` |
| **22** | **[FIX C3 — NO VACUO]** para cada runtime con `effort_mode != "no_aplica"`: `caps["efforts"]` **no vacío**, `{e["id"] for e in caps["efforts"]} == set(EFFORTS)` y `caps["default_effort"] in EFFORTS`; y para `no_aplica`: `caps["efforts"] == []` | `True` — la versión del v2 (`<= set(EFFORTS)`) pasaba con la lista **vacía** de Codex y por eso no vio el bug |
| **23** | **[FIX C3]** `capabilities_for("codex_cli")["models"]` | ningún elemento con `id` vacío (hoy el catálogo trae `[""]`), y `default_model` nunca es `""` |
| **24** | **[FIX C7 — equivalencia con el código de hoy]** para `cap ∈ {0, 1, 5, 40, 41}` y los 5 efforts: `codex_turn_budget(e, cap)` | `== (max(1, cap // 2) if (cap > 0 and e == "low") else cap)` — la fórmula literal de `codex_cli_runner.py:591-592`. Ninguna corrida gasta menos turnos que hoy sin que alguien lo pida. |
| **25** | **[FIX C8]** `capabilities_for("codex_cli")` con `STACKY_RUNAWAY_MAX_TURNS = 0` y con `= 40` | `effort_effective_now` es `False` y `True` respectivamente, y la `effort_note` **difiere** entre ambos casos (la de `0` contiene la palabra `"registrada"`) |

> **Gotcha obligatorio [C2]:** en `runtime_capabilities.py` el binding es
> `from config import config as _cfg` ⇒ se lee **`getattr(_cfg, "STACKY_...", default)`**. El test
> monkeypatchea `config.config.STACKY_...` (el mismo objeto). Escribir `_cfg.config` o
> `config.STACKY_...` sobre el **módulo** produce un falso verde o un `AttributeError`.

**(c) [FIX C4] El catálogo que sale por HTTP declara la capacidad.**

Sin esto, `effort_mode` **nunca** llega al frontend y toda F5 es decorativa. El endpoint es
`GET /api/agents/model-catalog` y arma su respuesta en `api/agents.py:1382-1386`:

```diff
     runtimes = {**catalog["runtimes"], "github_copilot": {
         **catalog["runtimes"].get("github_copilot", {}),
         "models": copilot["models"],
         "error": copilot["error"],
     }}
+    # Plan 264 [C4] — la capacidad declarada viaja CON el catálogo. Aditivo:
+    # no se quita ninguna clave existente. Sin esto el frontend nunca ve
+    # effort_mode y el selector no puede adaptarse (pickerCapabilities cae a
+    # "nativo" por default y el cambio de F5 queda inerte).
+    try:
+        from services.runtime_capabilities import capabilities_for
+        for _rt in list(runtimes.keys()):
+            _caps = capabilities_for(_rt)
+            runtimes[_rt] = {
+                **runtimes[_rt],
+                "effort_mode": _caps["effort_mode"],
+                "effort_effective_now": _caps["effort_effective_now"],
+                "effort_note": _caps["effort_note"],
+                "efforts": _caps["efforts"],           # normalizados (codex venía vacío)
+                "models": _caps["models"] or runtimes[_rt].get("models") or [],
+                "default_effort": _caps["default_effort"],
+                "default_model": _caps["default_model"],
+            }
+    except Exception:  # el catálogo nunca se cae por el enriquecido
+        pass
```

> **Ojo con `github_copilot`:** sus modelos vienen del bridge (`copilot["models"]`), no del archivo.
> Por eso el enriquecido usa `_caps["models"] or runtimes[_rt].get("models")`: si
> `capabilities_for` no ve modelos (el archivo no los tiene), **se conserva** la lista del bridge.
> Y como su `effort_mode` es `no_aplica`, sus `efforts` quedan `[]` ⇒ el picker no muestra esfuerzo.
> **Test de esto en `tests/test_plan264_runtime_capabilities.py` (test 26):** llamar al endpoint con
> el `app_ctx` del repo y afirmar sobre la **respuesta HTTP real** que los 3 runtimes traen
> `effort_mode`, que `codex_cli["efforts"]` tiene **5** entradas, que `github_copilot["efforts"]` está
> **vacío** y que `github_copilot["models"]` **no** se perdió.

**(d) Deduplicación (KPI-1) — [FIX C6] 12 ediciones en 6 archivos.** El v2 listaba 5. El censo real
con el grep del KPI (abajo) da **10**, más 2 partidas en dos líneas que el grep no ve. **Todas por
delegación, sin borrar símbolos, con equivalencia semántica exacta**:

| # | Archivo:línea | Qué dice hoy | Reemplazo | Nota de equivalencia |
|---|---|---|---|---|
| 1 | `api/agents.py:425` | `_VALID_EFFORTS = ("low", …, "max")` | `from services.runtime_capabilities import EFFORTS as _VALID_EFFORTS` (import **dentro** de la función, donde está la línea) | misma tupla |
| 2 | `api/agents.py:681` | `… _requested_effort_raw in {"low", …}` | `… _requested_effort_raw in EFFORTS` | tupla vs set: mismo resultado para strings exactos |
| 3 | `api/agents.py:717` | `_base_effort if _base_effort in {"low", …} else "high"` | `_base_effort if _base_effort in EFFORTS else "high"` | ídem |
| 4 | `api/agents.py:934` | igual que #2 | igual que #2 | ídem |
| 5 | `api/agents.py:963` | igual que #3 | igual que #3 | ídem |
| 6 | `api/agents.py:1156` | `_requested_effort_raw if … in {"low", …} else "high"` | `… in EFFORTS …` | ídem |
| 7 | `api/devops_agent.py:15` | `_EFFORTS = {"low", …}` | `from services.runtime_capabilities import EFFORTS as _EFFORTS_TUPLE` + `_EFFORTS = set(_EFFORTS_TUPLE)` (nivel de módulo: el símbolo se usa a nivel de módulo) | mismo set |
| 8 | `api/plans_board.py:176` | `_effort_raw if _effort_raw in {"low", …} else "high"` | `… in EFFORTS …` | ídem |
| 9 | `services/adaptive_selector.py:57` | **comentario** `# uno de {"low","medium",…}` | `# uno de services.runtime_capabilities.EFFORTS` | es un comentario; **el grep del KPI lo cuenta** (`, *` matchea con cero espacios) |
| 10 | `services/claude_code_cli_runner.py:2224` | `CLI_VALID_EFFORTS = ("low", …)` | `from services.runtime_capabilities import EFFORTS as CLI_VALID_EFFORTS` (nivel de módulo) | símbolo **conservado** como alias |
| 11 | `api/devops_remote_console.py:212-213` | literal partido en 2 líneas | ver diff abajo | **el grep NO la cuenta**, pero hay que editarla igual |
| 12 | `api/devops_remote_console.py:313-314` | ídem | ver diff abajo | ídem |

```diff
# api/devops_remote_console.py:212-213 y :313-314 (las DOS; reemplazá la sentencia COMPLETA,
# que ocupa dos líneas)
-    effort_override = effort.strip().lower() if effort and effort.strip().lower() in {
-        "low", "medium", "high", "xhigh", "max"} else None
+    from services.runtime_capabilities import is_valid_effort
+    _e = (effort or "").strip().lower()
+    effort_override = _e if is_valid_effort(_e) else None
```

> **`CLI_VALID_EFFORTS` tiene consumidores externos**: `claude_code_cli_runner.py:2301`,
> `tests/test_plan212_characterization.py:169` y `tests/test_plan212_effort_matrix_parity.py:63-76`
> (que hacen `set(CLI_VALID_EFFORTS)`). Por eso el símbolo se **conserva** como alias de `EFFORTS`
> (misma tupla, mismo contenido) en vez de borrarse. Los dos tests del 212 deben seguir verdes.

**Registrar** `tests/test_plan264_runtime_capabilities.py` en **ambas** listas
(`backend/scripts/run_harness_tests.sh:20`, `HARNESS_TEST_FILES=(`, entradas **desnudas**; y
`backend/scripts/run_harness_tests.ps1:13`, `$HarnessTestFiles = @(`, entradas **entrecomilladas** —
sintaxis DISTINTA, no copies la línea del `.sh`), o `test_harness_ratchet_meta.py` sale rojo.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_runtime_capabilities.py" -q
```

**Criterio binario.** 26 passed. Y el grep de KPI-1 (el mismo con el que se midió el "antes = **10**"):
```bash
grep -rnE '\("low", *"medium", *"high", *"xhigh", *"max"\)|\{"low", *"medium", *"high", *"xhigh", *"max"\}' --include=*.py "Stacky Agents/backend" | grep -v "services/runtime_capabilities.py" | grep -v "/tests/" | wc -l
```
debe dar **0** (medí el antes con el mismo comando **antes** de editar y anotá el número en §10).

**Flag:** `STACKY_RUNTIME_CAPABILITIES_ENABLED`, default **ON**.
**Impacto por runtime:** el módulo **describe** los 3; no ejecuta ninguno. El enriquecido del endpoint
es aditivo para los 3.
**Trabajo del operador: ninguno.**

---

### F2 — Backend: paridad real de Codex (el bug gemelo del Plan 196, en el call site VIVO)

**Objetivo.** Que el effort elegido llegue a Codex **con cualquier configuración de flags**, y que quede
registrado — sin tocar el techo de seguridad de turnos y sin recortar el presupuesto de hoy.

> **[FIX C1] LEÉ ESTO ANTES DE EDITAR — el v2 parcheaba código muerto.**
> `agent_runner.py:144-157` hace un **return temprano incondicional**:
> ```python
> if runtime in {"codex_cli", "claude_code_cli"}:
>     return _start_cli_runtime(
>         runtime=runtime, …, model_override=model_override,
>         effort_override=effort_override, …,      # ← :154, el effort SÍ entra
>     )
> ```
> Por lo tanto **todo `agent_runner.py:227-300` es inalcanzable** para una corrida real, incluida la
> llamada a `start_codex_cli_run` de `:256-265` que el v2 mandaba parchear. El agujero VIVO está en
> `_start_cli_runtime` (`:411`), que **recibe** `effort_override` en `:421` y **no lo reenvía**:
> ```python
> if runtime == "codex_cli":                      # :439
>     from services.codex_cli_runner import start_codex_cli_run
>     return start_codex_cli_run(                 # :442
>         …, model_override=model_override,       # :449  ← última línea de kwargs
>     )                                           # :450
> ```
> mientras la rama de Claude (`:453-466`) sí lo pasa (`:465`). **Se parchean las DOS**: `:442-450`
> porque es la que corre, y `:256-265` por higiene (que el código muerto no mienta). El control
> negativo de F2.5 revierte **las dos** líneas.

> **[FIX C2] Y ANTES DE ESCRIBIR LA PRIMERA LÍNEA:** `services/codex_cli_runner.py:22` hace
> **`from config import config`** ⇒ dentro de ese archivo `config` **ya es la instancia**. Se escribe
> `getattr(config, "STACKY_CODEX_EFFORT_PARITY_ENABLED", False)`. Escribir `config.config...` —como
> hacía el v2— levanta `AttributeError` y deja la flag muerta o revienta la corrida. Verificalo vos
> mismo: `grep -n "^from config import\|^import config" "Stacky Agents/backend/services/codex_cli_runner.py"`.

**Archivos a editar (2):**

**1) `Stacky Agents/backend/services/codex_cli_runner.py`**

(a) Agregar el parámetro a `start_codex_cli_run` (`codex_cli_runner.py:87-97`):

```diff
 def start_codex_cli_run(
     *,
     ticket_id: int,
     ...
     model_override: str | None = None,
+    effort_override: str | None = None,
 ) -> int:
```
(b) y en el `metadata_dict` (`codex_cli_runner.py:108-113`):
```diff
         exec_row.metadata_dict = {
             "runtime": RUNTIME,
             "vscode_agent_filename": vscode_agent_filename,
             "workspace_root": workspace_root,
             "model_override": model_override,
+            "effort_override": effort_override,   # Plan 264 — paridad con claude
         }
```
(c) **La zona del esfuerzo se reestructura así.** El bloque real empieza en el comentario de
`codex_cli_runner.py:579` (*"Q0.2 — Esfuerzo adaptativo…"*), la frase *"Codex no tiene --effort"* está
en **`:580`**, `_codex_adaptive_turns = config.STACKY_RUNAWAY_MAX_TURNS` en **`:581`**, el `if` del
adaptativo en **`:582`** y el bloque cierra en **`:597`**. `_codex_complexity` se declara en **`:444`**
y se llena en `:460` sólo si `STACKY_COMPLEXITY_ESTIMATION_ENABLED` (default `true`,
`config.py:789-790` — **[FIX C2 v3→v4]** v3 citaba `:774`; verificado hoy con
`grep -n "STACKY_COMPLEXITY_ESTIMATION_ENABLED" config.py`).
`STACKY_ADAPTIVE_EFFORT_ENABLED` también es default `true` (`config.py:920-921` — v3 citaba `:905`,
mismo motivo) — **pero las dos son
flags ajenas que el operador puede apagar por UI**, y por eso el override va **fuera** del `if`
(lección C2 de la ronda v1→v2). Compará con el código real antes de editar:

```diff
         # Q0.2 — Esfuerzo adaptativo por dificultad estimada (solo codex, OFF default).
-        # Codex no tiene --effort; se ajusta el presupuesto de turnos bajo el cap.
+        # Codex no tiene --effort; se ajusta el presupuesto de turnos bajo el cap.
+        # Plan 264 — el cap es TECHO: el esfuerzo sólo puede mover el presupuesto
+        # hacia abajo. 0 = sin límite y se mantiene sin límite.
         _codex_adaptive_turns = config.STACKY_RUNAWAY_MAX_TURNS
+        _codex_effort_requested = effort_override
+        _codex_effort_effective: str | None = None
         if getattr(config, "STACKY_ADAPTIVE_EFFORT_ENABLED", False) and _codex_complexity:
             _floor = (getattr(config, "STACKY_EFFORT_FLOOR", "medium") or "medium").strip().lower()
             _ORDER_EFFORT = {"low": 0, "medium": 1, "high": 2}
-            _mapped_effort_codex = {"S": "low", "M": "medium", "L": "high", "XL": "high"}.get(
+            _adaptive_codex = {"S": "low", "M": "medium", "L": "high", "XL": "high"}.get(
                 _codex_complexity, "medium"
             )
-            if _ORDER_EFFORT.get(_mapped_effort_codex, 1) < _ORDER_EFFORT.get(_floor, 1):
-                _mapped_effort_codex = _floor
-            # S/low → 50% del cap; M/medium → 100%; L/XL/high → 100%
-            if _codex_adaptive_turns > 0 and _mapped_effort_codex == "low":
-                _codex_adaptive_turns = max(1, _codex_adaptive_turns // 2)
-            log(
-                "info",
-                f"adaptive effort (codex) → {_mapped_effort_codex} "
-                f"(complexity={_codex_complexity}, max_turns={_codex_adaptive_turns}, Q0.2)",
-            )
+            if _ORDER_EFFORT.get(_adaptive_codex, 1) < _ORDER_EFFORT.get(_floor, 1):
+                _adaptive_codex = _floor
+            _codex_effort_effective = _adaptive_codex
+            log("info", f"adaptive effort (codex) → {_adaptive_codex} "
+                        f"(complexity={_codex_complexity}, Q0.2)")
+
+        # Plan 264 [C2 de la ronda v1→v2] — FUERA del bloque adaptativo: el override
+        # explícito del operador se honra tenga o no estimación de complejidad, y le
+        # GANA al adaptativo (misma regla que claude_code_cli_runner.py:961).
+        # [C2 de la ronda v2→v3] `config` acá ES la instancia (`from config import
+        # config`, :22): NO escribir `config.config`.
+        from services.runtime_capabilities import (
+            is_valid_effort as _rc_valid, codex_turn_budget as _rc_budget,
+        )
+        if getattr(config, "STACKY_CODEX_EFFORT_PARITY_ENABLED", False) \
+                and _rc_valid(_codex_effort_requested):
+            _codex_effort_effective = (_codex_effort_requested or "").strip().lower()
+            log("info", f"effort_override explícito (codex) → {_codex_effort_effective} "
+                        f"(prioridad sobre adaptativo, Plan 264)")
+        # El cap NUNCA sube: codex_turn_budget devuelve <= cap, y 0 sigue siendo 0.
+        # [C7] Con los factores de F1, el resultado para el adaptativo es IDÉNTICO
+        # al de hoy (sólo `low` divide por 2).
+        if _codex_effort_effective:
+            _codex_adaptive_turns = _rc_budget(_codex_effort_effective, _codex_adaptive_turns)
+            log("info", f"presupuesto de turnos (codex) → {_codex_adaptive_turns} "
+                        f"(cap={config.STACKY_RUNAWAY_MAX_TURNS}, "
+                        f"esfuerzo={_codex_effort_effective}, "
+                        f"efecto={'si' if config.STACKY_RUNAWAY_MAX_TURNS > 0 else 'no (sin cap)'})")
```

> **Comportamiento con `STACKY_CODEX_EFFORT_PARITY_ENABLED` en OFF:** el override se ignora y queda
> sólo el adaptativo — y con los factores de F1 el presupuesto resultante es **idéntico** al de hoy
> para los 5 efforts (test 24 de F1 y test 6 de F2). La rama OFF es equivalente en comportamiento a la
> actual.
> **[C8] Y con el cap en `0` (default de fábrica):** `codex_turn_budget` devuelve `0` siempre, así que
> **el esfuerzo no cambia esta corrida**; queda en el trace y en el log (`efecto=no (sin cap)`), y
> aplica el día que el operador configure `STACKY_RUNAWAY_MAX_TURNS`. Eso **se le dice al operador**
> vía `effort_note` (F1) — no se finge un efecto que no existe.

(d) Persistir el trace también en Codex (ver F4 (b)), con
`requested_effort=_codex_effort_requested` y `effective_effort=_codex_effort_effective`.

**2) `Stacky Agents/backend/agent_runner.py`** — **las DOS líneas que faltan**:

```diff
@@ _start_cli_runtime — :442-450 — ESTA ES LA QUE CORRE
         return start_codex_cli_run(
             ticket_id=ticket_id,
             ...
             model_override=model_override,
+            # Plan 264 — BUG VIVO: _start_cli_runtime RECIBE effort_override (:421)
+            # y no lo reenviaba, así que el selector de esfuerzo era decorativo en
+            # TODA corrida codex_cli. La rama de claude (:465) sí lo pasa.
+            effort_override=effort_override,
         )
```
```diff
@@ rama muerta — :256-265 — higiene, NO es el arreglo
             _new_exec_id = start_codex_cli_run(
                 ticket_id=ticket_id,
                 ...
                 model_override=model_override,
+                # Plan 264 — este bloque es INALCANZABLE (el return de :145 ya se
+                # ejecutó para codex_cli). Se completa igual para que el código
+                # muerto no contradiga al vivo si alguien lo resucita.
+                effort_override=effort_override,
             )
```

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_codex_effort_parity.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `inspect.signature(start_codex_cli_run).parameters` | contiene `"effort_override"` |
| **2** | **[FIX C1]** Monkeypatch de `services.codex_cli_runner.start_codex_cli_run`; `run_agent(runtime="codex_cli", effort_override="high", …)` — **el camino real, vía `_start_cli_runtime`** | el mock fue llamado con `effort_override == "high"`. Este test es el que **nacía rojo** con el diff del v2 |
| **2b** | **[FIX C1]** llamar **directo** a `agent_runner._start_cli_runtime(runtime="codex_cli", effort_override="high", …)` con el mismo mock | ídem — blinda el call site vivo aunque `run_agent` cambie |
| 3 | idem sin `effort_override` | el mock fue llamado con `effort_override is None` (no rompe llamadores viejos) |
| 4 | `start_codex_cli_run(..., effort_override="max")` con subprocess mockeado | `exec_row.metadata_dict["effort_override"] == "max"` |
| 5 | `cap = 0` (default real) + effort `"max"` | el `max_turns` que recibe `RunLimits` es **`0`** — el run **NO** queda capado |
| **6** | **[FIX C7]** `cap = 40`, los 5 efforts, **sin** override (sólo adaptativo) | el presupuesto es **idéntico** a la fórmula de hoy: `20` para `low`, `40` para los otros 4 |
| 7 | `STACKY_ADAPTIVE_EFFORT_ENABLED = False` **y** `STACKY_COMPLEXITY_ESTIMATION_ENABLED = False`, con `effort_override="low"` y `cap=40` | el presupuesto es **20**, no 40 ⇒ el effort se honró **fuera** del bloque adaptativo |
| 8 | mismas dos flags OFF, `effort_override="high"`, y se inspecciona el trace | `model_effort.requested_effort == "high"` (el effort **no** se descartó) |
| 9 | Flag `STACKY_CODEX_EFFORT_PARITY_ENABLED = False`, `effort_override="low"`, `cap=40`, sin complejidad | presupuesto `40` (comportamiento pre-264, el override se ignora) |
| **9b** | **[FIX C2]** con la flag en **ON**, `effort_override="low"`, `cap=40`, y el módulo importado de verdad | presupuesto **20** y **no se levanta `AttributeError`**. Control del binding: con `config.config.…` este test explota |
| 10 | Regresión Plan 196: `run_agent(runtime="claude_code_cli", effort_override="high")` | `start_claude_code_cli_run` sigue recibiendo `effort_override="high"` |

> **Gotcha del repo (SQLITE_LOCKED):** los tests 4, 8 y 10 tocan la DB ⇒ son **flaky bajo el
> shared-cache de pytest**. Corré este archivo **solo**, 8-12 veces seguidas, y usá el helper
> `run_with_retry` si el repo ya lo expone
> (`grep -rn "run_with_retry" "Stacky Agents/backend/tests" | head -3`). Un solo verde no alcanza.
> **Además:** los tests que instancian la app deben forzar `DATABASE_URL` in-memory. Hay archivos en
> este repo que corren contra la **DB REAL** y purgan tickets vivos.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_codex_effort_parity.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_runtime_dispatch.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_runtime_metadata_roundtrip.py" -q
```
(registrar el archivo nuevo en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** 12 passed × 10 corridas consecutivas sin un solo rojo, y los dos tests de
regresión de runtime en verde.

**Flag:** `STACKY_CODEX_EFFORT_PARITY_ENABLED`, default **ON** (no cae en (A) ni (B): sólo afecta
corridas que el operador lanza, y **nunca por encima del cap** que él configuró **ni por debajo del
presupuesto que la corrida ya tenía hoy**).
**Impacto por runtime:** Claude sin cambios (ya andaba por `:465`) · Codex ahora **honra** el effort
vía presupuesto de turnos, siempre bajo el cap, con efecto observable **sólo si hay cap** (declarado) ·
Copilot no aplica y lo declara.
**Trabajo del operador: ninguno.**

---

### F2.5 — [ADICIÓN ARQUITECTO] Centinelas ejecutables: que el bug no pueda volver

**Objetivo.** El bug de Codex no fue "alguien se olvidó una línea": fue que **nada en el sistema podía
detectar** (a) un parámetro de selección aceptado y jamás consumido, (b) uno consumido **sin efecto**,
ni (c) una corrección aplicada a una **rama muerta**. F2 arregla el caso; F2.5 arregla la clase.

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan264_paridad_ejecutable.py`.
**No hay código de producción nuevo en esta fase.** Es un gate.

**Test A — "cero parámetros decorativos" (AST, KPI-6).** Para cada función de arranque de runtime
(`start_claude_code_cli_run`, `start_codex_cli_run`, y cualquier otra que matchee `^start_.*_run$` en
`services/*_runner.py`):

1. parsear el archivo con `ast`;
2. localizar el `ast.FunctionDef`;
3. si acepta `effort_override` o `model_override`, contar los `ast.Name` con ese `id` **dentro del
   cuerpo**;
4. **fallar** si el único uso está en el `metadata_dict` (o si no hay ninguno). Guardar el trabajo en un
   dict `{param: [lineas_de_uso]}` y afirmar `len(usos_fuera_de_metadata) >= 1`.

**[FIX C1] En el otro extremo: TODAS las llamadas, incluidas las de `_start_cli_runtime`.** Para cada
`ast.Call` a `start_*_run` dentro de `agent_runner.py` — hoy son **cuatro**: `:256` y `:335` (rama
muerta) y `:442` y `:456` (`_start_cli_runtime`, la viva) — afirmar que la llamada pasa **ambos**
keywords. El assert, escrito hoy, sale **rojo contra el `agent_runner.py` sin el fix de F2**, en **dos**
de las cuatro. Ese es su control negativo.

> **Por qué AST y no regex:** la memoria del repo registra que un centinela **textual** sobre flags
> rompió el motor entero. Nunca un grep en masa sobre símbolos: `ast`, siempre.

**Test B — "contrato de honra", parametrizado por `RUNTIMES`.** `@pytest.mark.parametrize("runtime",
runtime_capabilities.RUNTIMES)`: para cada runtime declarado, el mismo escenario:

- `caps = capabilities_for(runtime)`;
- si `caps["supports_effort"]` es `True` ⇒ debe existir un mecanismo declarado: `EFFORT_MODE[runtime]`
  ∈ `{"nativo","presupuesto_turnos"}`, el runner correspondiente debe aceptar `effort_override`
  (verificado con `inspect.signature`) **y** `caps["efforts"]` debe ser **no vacío** (C3);
- si es `False` ⇒ `EFFORT_MODE[runtime] == "no_aplica"`, `caps["efforts"] == []` **y**
  `caps["effort_note"]` no vacía (el operador tiene que enterarse de por qué no hay selector).

**El valor real:** agregar `"runtime_nuevo"` a `RUNTIMES` sin cablear el effort **rompe el test
automáticamente**, sin que nadie tenga que acordarse de actualizar una lista escrita a mano.

**Test C — anti-regresión del cap.** `codex_turn_budget(e, cap) <= max(cap, 0)` para los 5 efforts y
para `cap ∈ {0, 1, 5, 40}`; y `codex_turn_budget(e, 0) == 0` para los 5. Es el candado de la ronda
anterior escrito como propiedad, no como ejemplo.

**Test D — [ADICIÓN ARQUITECTO] "efecto observable, no consumo simbólico".** El Test A prueba que el
parámetro se **use**; no prueba que **cambie algo**. Los bugs C3 y C8 pasan el Test A y siguen siendo
teatro. Para cada runtime con `supports_effort=True` **y** `effort_effective_now=True` bajo una
configuración de prueba explícita:

- **codex_cli:** con `STACKY_RUNAWAY_MAX_TURNS = 40`, `codex_turn_budget("low", 40)` y
  `codex_turn_budget("max", 40)` deben ser **distintos**. Con `= 0`, deben ser **iguales** (y el test
  afirma que `capabilities_for("codex_cli")["effort_effective_now"] is False`, es decir: **la
  inercia está declarada, no escondida**).
- **claude_code_cli:** el effort debe aparecer en el **comando construido**. Localizá el armado del
  argv con `grep -n "effort" "Stacky Agents/backend/services/claude_code_cli_runner.py" | head -20`,
  y afirmá que dos efforts distintos producen dos argv distintos. Si el armado no es aislable sin
  levantar un proceso, afirmá sobre `_effective_effort` (`claude_code_cli_runner.py:961`) con
  monkeypatch del subprocess — **nunca** lanzando un CLI real.

**El valor real:** este es el único test del plan que distingue "el sistema lee tu elección" de "tu
elección cambia la corrida". Es el que habría atrapado C3 y C8 el día que se escribieron.

**Test E — [ADICIÓN ARQUITECTO] gate AST del binding de `config` (§3.8).** Para cada archivo del
alcance de **este** plan — `agent_runner.py`, `services/codex_cli_runner.py`,
`services/claude_code_cli_runner.py`, `services/runtime_capabilities.py`, `api/agents.py`,
`api/devops_agent.py`, `api/devops_remote_console.py`, `api/preferences.py`, `api/plans_board.py`,
`services/adaptive_selector.py` — parsear con `ast` y:

1. determinar el binding: ¿hay un `ast.ImportFrom(module="config", names=["config"])` o un
   `ast.Import(names=["config"])`?
2. si el binding es **`from config import config`** ⇒ **fallar** ante cualquier
   `ast.Attribute` de la forma `config.config.*`;
3. si el binding es **`import config`** ⇒ **fallar** ante cualquier `config.<KEY>` donde `<KEY>` esté
   en `{s.key for s in FLAG_REGISTRY}` (leer el módulo devuelve el valor de clase y mata el branch OFF);
4. el mensaje de error debe decir **qué** binding tiene el archivo y **qué** forma corresponde.

**Alcance acotado a propósito:** sólo los archivos que este plan toca. Un barrido repo-wide arrastraría
deuda ajena y pondría rojo el gate por trabajo de otros planes (regla del repo: nunca adoptar rojos
ajenos). Si algún día se quiere ampliar, se hace con su propio plan y su propio ratchet.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_paridad_ejecutable.py" -q
```
(registrar en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** Los 5 tests verdes **después** de F2, y el Test A **rojo** si se revierten a mano
**las dos** líneas `effort_override=effort_override` de `agent_runner.py` (`:442-450` y `:256-265`)
— verificalo una vez, en una copia de scratch del archivo, y dejá anotado el resultado en §10.
**Flag:** ninguna (son tests). **Trabajo del operador: ninguno.**

---

### F3 — Backend: `resolve_run_selection()`, una sola cascada de precedencia

**Objetivo.** Que los **11** call sites que hoy no eligen nada pasen a resolver herramienta/modelo/effort
por la misma cascada, sin duplicar lógica.

**Archivo a editar:** `Stacky Agents/backend/services/runtime_capabilities.py` (misma casa que F1).

**Contrato:**

```python
def resolve_run_selection(
    *,
    runtime: str,
    model: str | None = None,          # explícito de la request
    effort: str | None = None,         # explícito de la request
    project_name: str | None = None,   # para leer la preferencia guardada (F4)
    adaptive_effort: str | None = None,# piso propuesto por adaptive_selector
    allow_opus: bool = False,
) -> dict:
    """Resuelve la selección final con esta precedencia EXACTA (de mayor a menor):

      1. `model` / `effort` explícitos de la request        -> origen "explicito"
      2. preferencia guardada del proyecto (si la flag ON)  -> origen "preferencia"
      3. `adaptive_effort` (sólo para effort; es PISO, no techo) -> origen "adaptativo"
      4. default_model / default_effort NORMALIZADOS del catálogo -> "default_catalogo"

    Después aplica clamp_selection() sobre el resultado.

    Devuelve:
      {"runtime": str, "model": str|None, "effort": str|None,
       "effort_requested": str|None, "degraded": bool, "reason": str|None,
       "origen_model": str, "origen_effort": str}
    NUNCA lanza: ante cualquier problema cae al paso 4.
    """
```

> **Regla 3 explicada (importante, no la inviertas):** `adaptive_effort` es un **piso**. Si el
> adaptativo propone `high` y el operador no eligió nada, se usa `high`. Si el operador eligió `low`
> explícitamente, gana `low` — el sistema **no** escala por su cuenta por encima de la decisión humana.
> Es la misma regla que ya respeta `claude_code_cli_runner.py:961`.

> **[backward-compat] La cascada NO cambia lo que ya pasa hoy en los 6 call sites que sí eligen**
> (`api/agents.py:529,825,1036,1200`, `api/devops_agent.py:327`, `api/plans_board.py:227` — los 6
> verificados pasando **ambos** overrides): esos ya pasan explícitos, que son el **paso 1** y siguen
> ganando. Esta fase **no los toca**. El único cambio de comportamiento observable es en los 11 que hoy
> corren "con lo que caiga": pasan a correr con el default del catálogo (o la preferencia del
> proyecto), que es igual o mejor que el azar actual. Declararlo así en §10.

**[FIX C9] Cableado de los 11 call sites — regla determinista, sin adivinanza.** El v2 daba un patrón
que usaba `runtime` y `project_name`, pero **9 de los 11 no los tienen en scope** (medido). La regla es:

> **Pasá a `resolve_run_selection` exactamente los mismos valores que la llamada a `run_agent(...)` ya
> le pasa.** Si la llamada **no** pasa `runtime=`, usá el literal `"github_copilot"` — que es el
> **default declarado de `run_agent`** (`agent_runner.py:94`), no una invención. Si no pasa
> `project_name=`, pasá `None`. **Nunca** inventes otro valor ni busques la variable "más parecida".

Patrón literal (ejemplo con `services/pipeline_orchestrator.py:58`, uno de los 3 que sí tiene ambos):

```diff
+    from services.runtime_capabilities import resolve_run_selection
+    _sel = resolve_run_selection(runtime=runtime, project_name=project_name)
     execution_id = agent_runner.run_agent(
         ...
+        model_override=_sel["model"],
+        effort_override=_sel["effort"],
     )
```

**Los 11 archivos:línea a editar (lista cerrada, re-verificada 2026-07-27 con `grep -n "run_agent("`):**

| # | Archivo | Línea | `runtime=` a pasar | `project_name=` a pasar | Nota |
|---|---|---|---|---|---|
| 1 | `Stacky Agents/backend/api/phase6.py` | 192 | `"github_copilot"` (la llamada no pasa runtime) | `None` | |
| 2 | `Stacky Agents/backend/api/phase6.py` | 229 | `"github_copilot"` | `None` | |
| 3 | `Stacky Agents/backend/api/devops_section_doctor.py` | 171 | `runtime` (ya lo pasa) | `project` (la llamada usa `project_name=project`) | |
| 4 | `Stacky Agents/backend/services/doc_documenter.py` | 383 | `runtime` (ya lo pasa) | `project_name` (ya lo pasa) | |
| 5 | `Stacky Agents/backend/services/pipeline_orchestrator.py` | 58 | `runtime` (ya lo pasa) | `project_name` (ya lo pasa) | el del ejemplo |
| 6 | `Stacky Agents/backend/services/slash_commands.py` | 101 | `"github_copilot"` | `None` | |
| 7 | `Stacky Agents/backend/services/variant_generator.py` | 188 | `runtime` (ya lo pasa) | `None` (no lo pasa) | **OJO:** es el optimizador del Plan 169 (`_OPTIMIZER_ADO_ID = -9`, `variant_generator.py:42`). Si el archivo tiene cambios sin commitear de otra sesión, **no lo toques** y dejá el ítem pendiente registrado en §10. |
| 8 | `Stacky Agents/backend/services/parallel_runs.py` | 58 | `"github_copilot"` | `None` | Es el fan-out de variantes: ya pasa `model_override=v.get("model")` (el modelo lo define la variante y **manda**), pero **no** pasa `effort_override`. Agregar **sólo** `effort_override=_sel["effort"]`, dejando el `model_override` de la variante intacto. |
| 9 | `Stacky Agents/backend/services/parallel_runs.py` | 126 | `"github_copilot"` | `None` | |
| 10 | `Stacky Agents/backend/services/parallel_runs.py` | 169 | `"github_copilot"` | `None` | |
| 11 | `Stacky Agents/backend/services/macros.py` | 177 | `"github_copilot"` | `None` | ya pasa `model_override=step.get("model")`; agregar **sólo** `effort_override=_sel["effort"]` |

> **Antes de editar cada uno, corré `git status --porcelain <archivo>`.** Este repo tiene sesiones
> paralelas: si el archivo aparece modificado y el cambio no es tuyo, **saltealo** y anotalo. Nunca
> `git stash`, `git reset` ni `git checkout --` sobre trabajo ajeno.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_run_selection.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | explícito gana a preferencia | `origen_model == "explicito"` |
| 2 | preferencia gana a adaptativo | `origen_effort == "preferencia"` |
| 3 | adaptativo gana a default | `origen_effort == "adaptativo"` |
| **4** | **[FIX C3]** sin nada, para **cada** runtime con `supports_effort` | `origen_effort == "default_catalogo"`, `effort == caps["default_effort"]` **y `effort is not None`** (la versión del v2 pasaba con `None == None` y tapaba el catálogo vacío de Codex) |
| 5 | explícito `"low"` + adaptativo `"high"` | `effort == "low"` (el humano no se sobreescribe) |
| 6 | runtime `github_copilot` | `effort is None`, `degraded is True` |
| 7 | runtime desconocido | no lanza; cae a defaults |
| 8 | flag prefs OFF | el paso 2 se saltea; `origen_effort` nunca es `"preferencia"` |
| 9 | Cobertura (KPI-2): AST sobre **todas** las llamadas a `run_agent(` | **cada** llamada pasa `model_override=` y `effort_override=` |

> **Test 9 — cómo hacerlo bien:** usá el módulo `ast` de Python, **no** un regex. Parseá cada archivo,
> encontrá los `ast.Call` cuyo `func` termine en `run_agent`, y verificá los `keywords`. Excluí
> `backend/evals/` (ahí `run_agent` es **otra función**: `evals/golden_runner.py:109`,
> `def run_agent(agent_type: str) -> list[GoldenResult]`) y `backend/tests/`.
> **El universo son 17 llamadas** (verificado con `grep -rn "run_agent(" --include=*.py` sobre
> `api/` + `services/`, excluyendo `def run_agent`). 6 ya cumplen, 11 las cablea esta fase.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_run_selection.py" -q
```
(registrar en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** 9 passed. El test 9 **es** el KPI-2 y admite **como máximo 2** entradas de
allowlist, cada una con el motivo escrito en el propio test:
`variant_generator.py:188` (ítem 7) y un segundo cupo reservado para cualquier archivo que aparezca
sucio por trabajo ajeno. Si no hay bloqueos, la allowlist queda **vacía**.

**Flag:** `STACKY_RUNTIME_CAPABILITIES_ENABLED` (ON) y `STACKY_RUN_SELECTION_PREFS_ENABLED` (ON) para
el paso 2.
**Impacto por runtime:** la cascada es igual en los 3; lo que cambia es el clamp de F1.
**Trabajo del operador: ninguno** (todo tiene default).

---

### F4 — Backend: persistencia por proyecto + historial en los 3 runtimes

**Objetivo.** Recordar la elección y dejar rastro de qué se usó de verdad.

**(a) Persistencia.**

> **Verificado en el repo (2026-07-27):**
> 1. El endpoint `GET/PUT /api/preferences/ui/<key>` **existe** (`preferences.py:75` y `:89`) **pero
>    está gateado** por `STACKY_UI_SAVED_VIEWS_ENABLED` (`preferences.py:71`, leído de
>    `config.config`; default `true` en `config.py:1825-1826` — **[FIX C2 v3→v4]** v3 citaba `:1810`;
>    re-verificado hoy) y devuelve **404 `feature_disabled`** si está OFF.
> 2. La clave se valida con `_UI_KEY_RE = ^[A-Za-z0-9._-]{1,128}$` (`preferences.py:65`). Un
>    `project_name` con **espacio, acento o paréntesis** (lo normal en este repo) ⇒ **400
>    `invalid_key`**.
> 3. `api.get/api.put` del frontend **lanzan excepción** en non-2xx ⇒ sin manejo, la UI revienta en
>    vez de degradar.
> 4. La lógica del sub-objeto `ui` vive **en el cuerpo de la ruta**, no en una función reusable, y
>    `_PREFS_FILE = Path("data/preferences.json")` (`preferences.py:14`) es **relativo al CWD**.

**Cambio en `Stacky Agents/backend/api/preferences.py`** (extracción pura, **contrato HTTP intacto**):

```python
# Plan 264 — helpers reusables desde services/ (la lógica del sub-objeto `ui`
# estaba enterrada en el cuerpo de la ruta y no se podía reusar sin duplicarla).
def read_ui_pref(key: str):
    """Valor de una preferencia de UI, o None. Nunca lanza."""

def write_ui_pref(key: str, value) -> bool:
    """Guarda la preferencia. False si la clave es inválida o falla. Nunca lanza."""
```
Las rutas `get_ui_preference` / `put_ui_preference` pasan a **llamar a estos helpers**. No cambia
ninguna URL, ningún status code ni ningún body.

**En `runtime_capabilities.py` agregar:**

```python
import re as _re

_PREF_KEY_PREFIX = "runSelection."
_PREF_SAFE = _re.compile(r"[^A-Za-z0-9._-]")

def pref_key_for(project_name: str | None) -> str:
    """Clave válida para _UI_KEY_RE a partir de CUALQUIER nombre de proyecto:
    espacios, acentos y paréntesis se reemplazan por '-'. Determinista y estable.
    `None` -> 'runSelection.__default__'. Resultado <= 128 chars."""

def load_run_preference(project_name: str | None) -> dict | None:
    """Lee la preferencia guardada del proyecto vía preferences.read_ui_pref.
    None si no hay, si STACKY_RUN_SELECTION_PREFS_ENABLED está OFF, si el store
    de preferencias de UI está deshabilitado, o ante CUALQUIER error. Nunca lanza."""

def save_run_preference(project_name: str | None, sel: dict) -> bool:
    """Guarda {"runtime","model","effort"} validado con clamp_selection().
    Devuelve False (sin lanzar) si la flag está OFF o el guardado falla."""
```

**En el frontend**, la lectura/escritura de la preferencia usa **`rawGet`/`rawPut`** (no `api.get`/
`api.put`), porque un 404 `feature_disabled` es un caso **normal** — significa "no hay preferencia,
usá el default", no un error que deba propagarse.

**(b) Historial.** Mover `build_model_effort_trace` (hoy en `claude_code_cli_runner.py:516-540`) a
`runtime_capabilities.py` **conservando el símbolo original como delegador** (hay callers por nombre,
incluidos 2 tests del 212), y llamar a `_persist_model_effort_trace` (`:543`) también desde
`codex_cli_runner`. El trace gana claves; **no pierde ninguna**:

```diff
     return {
+        "tool": runtime,                       # Plan 264 — qué herramienta corrió
         "requested_model": requested_model or "",
         "effective_model": effective_model or "",
         "requested_effort": requested_effort or "",
         "effective_effort": effective_effort or "",
-        "downgraded": degradado,
-        "reason": reason,
+        "downgraded": degradado,               # ← CONSERVADA (test_plan212_requested_vs_effective)
+        "reason": reason,                      # ← CONSERVADA (idem)
+        "effort_mode": EFFORT_MODE.get(runtime, "no_aplica"),
+        "effort_effective_now": bool(effort_effective_now),   # [C8]
+        "origen_model": origen_model,
+        "origen_effort": origen_effort,
     }
```

> **El v1 mostraba este `return` SIN `downgraded` ni `reason`.** Un modelo menor que aplicara el diff
> literal borraba las dos claves y ponía rojo `test_plan212_requested_vs_effective.py` — que el propio
> F7 corre como regresión. **Leé la firma y el cuerpo reales (`claude_code_cli_runner.py:516-540`)
> antes de tocar**, y agregá los parámetros nuevos (`runtime`, `origen_model`, `origen_effort`,
> `effort_effective_now`) como **keyword-only con default**, para no romper a sus llamadores actuales.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_selection_history.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `save_run_preference` + `load_run_preference` round-trip | devuelve lo guardado |
| 2 | `load_run_preference("proyecto_inexistente")` | `None`, no lanza |
| 3 | `save_run_preference` con effort inválido | se guarda **clampeado**, no crudo |
| 4 | flag `STACKY_RUN_SELECTION_PREFS_ENABLED = False` | `save` devuelve `False` y `load` devuelve `None` |
| 5 | `pref_key_for("Stacky Agents (Pacífico)")` | matchea `^[A-Za-z0-9._-]{1,128}$` y el round-trip completo funciona |
| 6 | `STACKY_UI_SAVED_VIEWS_ENABLED = False` | `save` devuelve `False`, `load` devuelve `None`, **no lanza** |
| 7 | trace de una corrida claude | `tool == "claude_code_cli"` y `effort_mode == "nativo"` |
| 8 | trace de una corrida codex | `tool == "codex_cli"` y `effort_mode == "presupuesto_turnos"` |
| 9 | trace con degradación | `downgraded is True` **y** `reason` presente **y** `requested_effort != effective_effort` |
| 10 | `metadata_dict["model_effort"]` persiste tras `start_codex_cli_run` mockeado | presente, con `tool`, `effort_mode`, `effort_effective_now` **y** `downgraded` |

> **Aviso duro:** los tests que escriben preferencias deben monkeypatchear el símbolo exacto
> **`api.preferences._PREFS_FILE`** a un `tmp_path`. `_PREFS_FILE = Path("data/preferences.json")`
> (`preferences.py:14`) es **relativo al CWD**: sin el monkeypatch, el test escribe en el `data/` de
> quien lo corra. La memoria del repo registra que un test del Plan 216 podía escribir en el **perfil
> REAL** del operador. Afirmá **en el propio test** que el archivo real no existe / no cambió.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_selection_history.py" -q
```
(registrar en las dos `HARNESS_TEST_FILES`; correr 8-12 veces por el gotcha de SQLite).

**Criterio binario.** 10 passed × 10 corridas. Y:
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); from services.runtime_capabilities import EFFORT_MODE; print(sorted(EFFORT_MODE))"
```
imprime los 3 runtimes (KPI-5 estructural).

**Flag:** `STACKY_RUN_SELECTION_PREFS_ENABLED` (ON), con dependencia declarada de
`STACKY_UI_SAVED_VIEWS_ENABLED` (flag ajena, default ON). El trace no lleva flag: es telemetría de solo
escritura local que el repo ya hace para Claude.
**Impacto por runtime:** los 3 persisten trace; Copilot registra `effort_mode="no_aplica"`.
**Trabajo del operador: ninguno.**

---

### F5 — Frontend: un solo selector, en todas las superficies

**Objetivo.** Cero selectores hechos a mano (KPI-4).

> **Prerrequisito duro [C4]: sin F1 (c) esta fase es DECORATIVA.** `effort_mode` no existe en
> `config/model_catalog.json`; si el endpoint no lo inyecta, el frontend lo ve `undefined` **siempre**,
> `effortMode` cae a `"nativo"` y nada cambia — mientras los tests de vitest (que arman el objeto a
> mano) salen verdes. **No empieces F5 sin haber verificado la respuesta HTTP real:**
> ```powershell
> "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); import os; os.environ['DATABASE_URL']='sqlite:///:memory:'; from app import create_app; c=create_app().test_client(); r=c.get('/api/agents/model-catalog').get_json(); print({k:{'effort_mode':v.get('effort_mode'),'efforts':len(v.get('efforts') or []),'eff_now':v.get('effort_effective_now')} for k,v in r['runtimes'].items()})"
> ```
> debe imprimir `effort_mode` para los 3 y `efforts: 5` para `codex_cli`.

**(a) Extender el contrato del picker.**

> El cuerpo **real** de `pickerCapabilities` (`frontend/src/services/modelEffortOptions.ts:63-73`)
> **ya devuelve `note`**, leyendo `runtimeCatalog?.effort_note ?? runtimeCatalog?.note ?? ""`. Agregar
> un `effortNote` sería una **segunda copia** del mismo dato — exactamente el pecado que este plan
> viene a matar. Y `showEfforts` se calcula **sin mirar** `effort_mode`.

Diff sobre el cuerpo **real**:

```diff
 export function pickerCapabilities(
   runtimeCatalog: RuntimeModelCatalog | undefined,
-): { showModels: boolean; showEfforts: boolean; note: string } {
+): { showModels: boolean; showEfforts: boolean; note: string; effortMode: string; effortEffectiveNow: boolean } {
   const showModels = (runtimeCatalog?.models?.length ?? 0) > 0;
-  const showEfforts = (runtimeCatalog?.efforts?.length ?? 0) > 0;
+  // Plan 264 — un runtime que no expone esfuerzo NO debe mostrar el selector:
+  // "prohibido mostrar un selector que no hace nada" (§3.1).
+  const effortMode = runtimeCatalog?.effort_mode ?? "nativo";
+  // [C8] Un runtime que SÍ expone esfuerzo pero hoy no produce efecto (Codex sin
+  // cap de turnos) muestra el selector CON la nota que lo explica: la elección se
+  // guarda y valdrá cuando haya cap. Ocultarlo sería peor: perdería la elección.
+  const effortEffectiveNow = runtimeCatalog?.effort_effective_now ?? true;
+  const showEfforts =
+    (runtimeCatalog?.efforts?.length ?? 0) > 0 && effortMode !== "no_aplica";
   return {
     showModels,
     showEfforts,
     note: runtimeCatalog?.effort_note ?? runtimeCatalog?.note ?? "",
+    effortMode,
+    effortEffectiveNow,
   };
 }
```
(y agregar `effort_mode?: string;` y `effort_effective_now?: boolean;` al tipo `RuntimeModelCatalog` en
`frontend/src/api/endpoints.ts:1090-1103` — **[FIX C2 v3→v4]** v3 citaba `:1071-1084`; `endpoints.ts`
es exactamente uno de los archivos "calientes" que otros planes también editan (§9.2): confirmá con
`grep -n "interface RuntimeModelCatalog" frontend/src/api/endpoints.ts` antes de editar).

En `components/ModelEffortPicker.tsx`, renderizar `caps.note` como texto de ayuda debajo del select de
esfuerzo cuando `caps.effortMode !== "nativo" || !caps.effortEffectiveNow`. **Reusar `caps.note`, no
crear un campo nuevo.**

> **Se conserva la decisión de diseño del Plan 212 F4** (documentada en `ModelEffortPicker.tsx:12-18`):
> **dentro de un runtime que soporta esfuerzo, se ofrecen TODOS los efforts, siempre**, anotando a qué
> degradan. No los escondas ni los deshabilites. Lo que agrega este plan es distinto y no contradice esa
> regla: cuando el runtime **entero** no tiene esfuerzo (`no_aplica`), no se muestra el control. Una cosa
> es "no escondas opciones que existen"; otra es "no muestres un control que no hace nada".

**(b) Reemplazar los 2 selectores hechos a mano:**

| Archivo | Qué sacar | Qué poner |
|---|---|---|
| `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` | el `<select>` de modelos que abre en **`:336`** y el de esfuerzo que le sigue (**`:348`**), más la lógica de `:147-162` (`useModelCatalog`, `setActionModel`, `setActionEffort`, `availableEfforts`, `effortsForModel`) | `<ModelEffortPicker catalog={claudeCat} model={actionModel} effort={actionEffort} onChange={...} />` |
| `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx` | la lógica de `:83-102` (`claudeModels`, `claudeEfforts`, `claudeDefaultModel`, el default desde `EMERGENCY_MODEL_CATALOG`) y sus dos `<select>` (**`:414`** y **`:422`**) | el mismo `<ModelEffortPicker>`, alimentado por `useModelCatalog()` |

> El envío sigue igual: `IncidentResolverModal.tsx:243-244` ya manda `model` (sólo si el runtime es
> `claude_code_cli`) y `effort`. **No cambies el contrato del POST**, sólo de dónde salen los valores.
> `PlansBoardPage.tsx` — ver **§9.2**: este archivo también lo edita el Plan 263. Leé el protocolo de
> convivencia **antes** de tocarlo.

**(c) Agregar el picker donde no había** (las superficies de F3 que ahora aceptan selección).

> **[FIX C3 v3→v4] "Verificalo vos mismo" no alcanza — la prueba concreta y el veredicto ya
> medidos.** El v3 nombraba 3 candidatos y delegaba en el implementador decidir cuál "lanza una
> corrida", sin decir CÓMO. Medido con grep sobre los 3 archivos reales (2026-07-29):
> - **`components/devops/TriggerPipelineSection.tsx`: NO califica.** Cero ocurrencias de
>   `run_agent`/`rawPost`/`api.post` hacia un endpoint de ejecución. Dispara
>   `devops.pipeline.trigger` vía `runDevOpsAction` (comentario propio del archivo: *"Plan 267 F7 —
>   antes llamaba CIPipeline.trigger directo, SIN pedir confirmacion... ahora por runDevOpsAction"*).
>   Es el **catálogo de acciones DevOps/CI** del Plan 267: dispara una pipeline externa, no un agente
>   LLM. No tiene ninguna dimensión de modelo/effort que mostrar.
> - **`components/devops/DeploymentsSection.tsx`: NO califica** (misma prueba, mismo resultado: cero
>   `run_agent`/`POST run`). Por nombre y estructura es del mismo catálogo de acciones DevOps que
>   `TriggerPipelineSection`.
> - **`pages/DocsPage.tsx`: SÍ es candidato plausible.** Usa `documenterEnabled` y
>   `handleProposeUpdate` (`DocsPage.tsx:159,445`), que encaja con el call site F3 #4
>   (`services/doc_documenter.py:383`, uno de los 11 que esta fase cablea). Confirmalo mirando qué
>   endpoint llama `handleProposeUpdate` y si ese endpoint es el que termina en
>   `agent_runner.run_agent(...)`.
> **La prueba concreta para cualquier candidato futuro** (no sólo estos 3): `grep -n
> "run_agent\|/api/.*run\b" <archivo>` en el componente, y si hay POST, seguí la cadena hasta el
> blueprint de `api/` que lo atiende — si ese blueprint termina en `agent_runner.run_agent(...)`,
> califica; si termina en un catálogo de acciones DevOps/CI (`runDevOpsAction` u otro disparador que
> no sea un agente LLM), NO califica, sin importar que "dispare" algo.
> **Conclusión para esta fase:** sólo `pages/DocsPage.tsx` es candidato a picker nuevo, sujeto a la
> confirmación de arriba; los otros 2 quedan **descartados** por evidencia, no por omisión. Registrá
> en §10 el veredicto final de los 3 (con el resultado de seguir la cadena de `DocsPage.tsx`).

**Tests (vitest, lógica pura):** crear
`Stacky Agents/frontend/src/services/__tests__/modelEffortOptions.plan264.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `pickerCapabilities(undefined)` | no lanza; `effortMode === "nativo"`; `note === ""`; `effortEffectiveNow === true` |
| 2 | catálogo con `effort_mode: "no_aplica"` y `efforts` no vacío | `showEfforts === false` |
| 3 | catálogo con `effort_mode: "presupuesto_turnos"` y `effort_note` | `note` es esa frase, `showEfforts === true` |
| 4 | `buildEffortOptions` con un modelo que degrada | sigue devolviendo **los 5** efforts, con la anotación (regresión del Plan 212 F4) |
| 5 | catálogo **sin** `effort_mode` (deploy viejo) | `effortMode === "nativo"`, `showEfforts` según `efforts.length` (retrocompatible) |
| **6** | **[C8]** catálogo con `effort_mode: "presupuesto_turnos"` y `effort_effective_now: false` | `showEfforts === true` (no se esconde) **y** `effortEffectiveNow === false` (la UI puede mostrar la nota) |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortOptions.plan264.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelCatalogFallback.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> **Corré cada archivo de test por separado.** La suite completa de vitest de este repo tiene
> contaminación cross-file conocida.
> **No hay RTL ni jsdom:** toda la lógica testeable vive en `.ts` puro. Los `.tsx` (`ModelEffortPicker`,
> `PlansBoardPage`, `IncidentResolverModal`) se validan con `tsc --noEmit` + el smoke manual de R5.

**Criterio binario [FIX C10].** Los 3 comandos exit 0, **y los dos greps de KPI-4** (el del v2, solo,
era gameable: matchea **2** líneas, **ambas** en `IncidentResolverModal.tsx:414,422`;
`PlansBoardPage.tsx` aportaba **0**, así que el criterio se cumplía sin tocarlo):

```bash
# (1) NEGATIVO — ningún resto del selector hecho a mano en los dos archivos:
grep -cE "effortsForModel|EMERGENCY_MODEL_CATALOG|setActionEffort|claudeEfforts" \
  "Stacky Agents/frontend/src/pages/PlansBoardPage.tsx" \
  "Stacky Agents/frontend/src/components/IncidentResolverModal.tsx"   # → 0 en AMBOS
# (2) POSITIVO — el selector único está cableado en los dos:
grep -c "ModelEffortPicker" \
  "Stacky Agents/frontend/src/pages/PlansBoardPage.tsx" \
  "Stacky Agents/frontend/src/components/IncidentResolverModal.tsx"   # → >=1 en AMBOS
```

**Restricciones de ratchet (duras):** no aumentar `style={{` en los archivos tocados
(`PlansBoardPage.tsx` está congelado en **3** en `frontend/src/__tests__/uiDebtBaseline.json:136`), y
**cero literales hex nuevos** en CSS (`PlansBoardPage.module.css` congelado en **39**, `:66`). Los
`.tsx` **nuevos** tienen alcance **0** de inline-style: usá CSS module o `ref` + `effect`.

**Flag:** `STACKY_MODEL_PICKER_EVERYWHERE_ENABLED` (ON). El estado de la flag se lee de
**`/api/diag/health`**, que es donde ya viven las flags de UI.
**Impacto por runtime:** el picker se auto-adapta por `effort_mode`: Claude muestra esfuerzo,
Codex lo muestra con la nota de presupuesto de turnos (y la advertencia si no hay cap), Copilot **no lo
muestra**.
**Trabajo del operador: ninguno** (todo preseleccionado por catálogo/preferencia).

---

### F6 — Frontend: el historial dice qué se usó

**Objetivo.** Que el operador vea, por corrida, herramienta + modelo + esfuerzo pedido y efectivo.

**Archivos a editar (2):**

1. `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx` — mostrar
   `metadata.model_effort` con las claves de F4 (`tool`, `requested_model`, `effective_model`,
   `requested_effort`, `effective_effort`, `effort_mode`). **Para saber si hubo degradación, leé
   `trace.downgraded` — la clave YA existe y ya la calcula el backend.** No recalcules
   `requested_* !== effective_*` en el frontend: sería una tercera implementación de la misma regla.
   Marcalo con el `ModelDecisionChip` **ya existente** (`components/ModelDecisionChip.tsx`, verificado)
   — no crees un chip nuevo.
2. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx:478-486` — el historial de corridas ya muestra
   `r.model` (`:482`) y `r.effort` (`:483` — **[FIX C2 v3→v4]** v3 citaba `:481`/`:482`, off por 1);
   agregar la **herramienta** (`r.tool ?? "—"`) como columna.
   **Es la misma zona que toca el 263** — ver §9.2.

**Test:** crear `Stacky Agents/frontend/src/services/__tests__/modelEffortTrace.test.ts` sobre un
helper puro nuevo `formatModelEffortTrace(trace)` en
`Stacky Agents/frontend/src/services/modelEffortTrace.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | trace `undefined`/`null` | devuelve `null`, no lanza |
| 2 | trace con `downgraded: false` | `degraded === false`, texto sin flecha |
| 3 | trace con `downgraded: true`, `requested_effort: "max"`, `effective_effort: "high"` | `degraded === true` y el texto contiene `"max → high"` |
| 4 | trace con `effort_mode: "no_aplica"` | el texto dice que la herramienta no usa esfuerzo |
| 5 | trace de un deploy viejo (sin `tool`, sin `effort_mode`, **con** `downgraded`) | no lanza; `tool` se muestra como `"—"` y `degraded` sale de `downgraded` |
| **6** | **[C8]** trace con `effort_mode: "presupuesto_turnos"` y `effort_effective_now: false` | el texto avisa que el esfuerzo quedó registrado pero no cambió esa corrida |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortTrace.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 6 passed, `tsc` exit 0, `grep -c "style={{" PlansBoardPage.tsx` sigue en **3**.
**Flag:** protegido por las flags de las pantallas que lo contienen (ya ON).
**Impacto por runtime:** los 3 se muestran; Copilot muestra "no aplica" en esfuerzo.
**Trabajo del operador: ninguno.**

---

### F7 — Cierre y verificación consolidada

**Comandos (todos deben salir exit 0):**

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_runtime_capabilities.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_codex_effort_parity.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_paridad_ejecutable.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_run_selection.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan264_selection_history.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_runtime_dispatch.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_runtime_metadata_roundtrip.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan212_requested_vs_effective.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan212_model_probe.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan212_characterization.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan212_effort_matrix_parity.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
& $py -m compileall -q "Stacky Agents\backend\services" "Stacky Agents\backend\api"
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortOptions.plan264.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortTrace.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> Los tests `test_plan212_*` son la regresión del plan que construyó la matriz — los **cuatro**, no dos:
> `characterization` (`:169`) y `effort_matrix_parity` (`:63-76`) importan `CLI_VALID_EFFORTS`, que esta
> fase convierte en alias. Si alguno se pone rojo, este plan rompió su contrato ⇒ arreglalo, **no** lo
> agregues a una allowlist.
> **`test_harness_flags_help` NO está en esta lista a propósito:** tiene **4 fallos ajenos
> preexistentes**. **[FIX C5] Pero eso NO te exime de tocar `services/harness_flags_help.py`**: el test
> exige cobertura 100 % de `FLAG_REGISTRY` sin huérfanas, así que 4 flags sin entrada en `PLAIN_HELP`
> serían **4 rojos nuevos tuyos**. Validá **tus** 4 entradas con el one-liner de F0 (que no adopta los
> rojos ajenos) y dejá su salida en §10.

**Huella de regresión.** Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` la huella del
defecto que este plan cierra.

> **[FIX C1 v3→v4 — BLOQUEANTE] El JSON del v3 usaba un esquema INVENTADO y rompía el gate real.**
> El v3 traía `sintoma`/`causa_raiz`/`deteccion`/`antecedentes`/`plan`/`fecha` — ninguno de esos
> nombres existe en el esquema real. Verificado abriendo
> `Stacky Agents/backend/tests/test_error_fingerprints_catalog.py:17-18` (Plan 163 F4, corre HOY
> contra este mismo archivo): los campos **obligatorios** son
> `("id", "title", "class", "status", "log_pattern", "log_guarded", "killed_by", "guard_test",
> "self_test")`, `status` debe estar en `{"resolved","open","by_design"}`, `log_pattern` debe compilar
> como regex (`test_patrones_compilan`) y `self_test.matches`/`.clean` deben ser coherentes contra ese
> patrón (`test_self_test_coherente`). El JSON del v3 sólo tenía 2 de los 9 campos obligatorios
> (`id`, `guard_test`) ⇒ `test_campos_obligatorios` sale **rojo** apenas se agrega la entrada tal cual
> estaba escrita.
> **Y hay un problema de fondo, no sólo de nombres:** esta clase de bug (un parámetro aceptado y
> nunca materializado) **no tiene firma de log** — es un no-evento silencioso, no un patrón de texto
> como los 404 de `pipeline_status_404` o los ANSI de `ansi_in_file_log`. Por eso el propio plan
> necesitó un test AST (F2.5) en vez de un scan de logs. Fingir un `log_pattern` sería el mismo pecado
> que el plan viene a matar (aparentar una capacidad que no existe). v4: `log_guarded: false`
> declarado con la razón, y `self_test` con `matches`/`clean` **vacíos** — coherente por vacuidad
> (`test_self_test_coherente` no itera nada si las dos listas están vacías), sin fingir un patrón.
> El contenido narrativo del v3 (síntoma, causa raíz, antecedentes) **no se pierde**: se conserva en
> `note` y `title`, que sí son parte del esquema real (o son campos libres que ya usan otras huellas).
>
> **[FIX C1 — el archivo YA está rojo por deuda ajena; el criterio no puede pedir "verde".]** Medido
> hoy (2026-07-29): `pytest backend/tests/test_error_fingerprints_catalog.py -q` da **3 failed, 5
> passed**, por una huella ajena (`class: "shell-navigation"`, `date_resolved: "2026-07-25"`) que
> tiene `status: "guarded"` (fuera del enum `{"resolved","open","by_design"}`) y no trae `self_test`.
> Ese rojo es de otro plan y está **fuera de alcance** de este (regla del repo: nunca adoptar deuda
> ajena). Por eso el criterio de esta huella es **delta**, no "el archivo entero en verde": correr el
> comando ANTES de tocar el archivo, anotar el 3/5, agregar la entrada nueva con el esquema real de
> arriba, correr DE NUEVO, y el criterio de aceptación es "**los mismos 3 failed** (ninguno con el
> `id` `seleccion-aceptada-nunca-materializada` en el mensaje) **y los mismos o más passed**" — nunca
> "0 failed".

**Leé primero el esquema real del archivo** (`Get-Content` de las primeras 40 líneas, o el `_REQUIRED`
de `test_error_fingerprints_catalog.py:18`) antes de tocarlo. El contenido a registrar es:

```json
{
  "id": "seleccion-aceptada-nunca-materializada",
  "title": "Seleccion de modelo/effort aceptada por el runner y nunca materializada",
  "class": "silent-param-drop",
  "status": "resolved",
  "log_pattern": "$^",
  "log_guarded": false,
  "killed_by": "plan 264 (matriz unica de capacidades runtime/modelo/effort)",
  "killed_commit": "PENDIENTE — completar en Registro de implementacion (§10) con el hash real",
  "date_resolved": "PENDIENTE — completar en §10 con la fecha real de implementacion",
  "guard_test": "backend/tests/test_plan264_paridad_ejecutable.py",
  "evidence": "backend/agent_runner.py:442-450 (rama viva); backend/agent_runner.py:256-265 (rama muerta, higiene)",
  "note": "Sintoma: el operador elige un modelo o un esfuerzo y la corrida se comporta igual que si no hubiera elegido nada. Causa raiz: un parametro de seleccion aceptado por la firma del runner y (a) nunca consumido, (b) consumido dentro de una rama gateada por otra flag, (c) consumido en una rama MUERTA por un return anterior, o (d) consumido sin efecto observable con la config vigente. Antecedentes: Plan 196 (claude_code_cli, rama muerta agent_runner.py:350) y Plan 264 (codex_cli, rama viva agent_runner.py:442). log_guarded=false a proposito: este bug no tiene firma de log (es un no-evento silencioso); el unico detector real es el AST de guard_test (Test A: parametros decorativos y las 4 llamadas de agent_runner; Test D: efecto observable, no solo consumo simbolico).",
  "self_test": {
    "matches": [],
    "clean": []
  }
}
```

> `log_pattern: "$^"` es el idiom estándar de "nunca matchea" (ancla de fin de línea inmediatamente
> tras la de inicio) — compila como regex válida (satisface `test_patrones_compilan`) sin fingir una
> detección de log que no existe. No reemplazarlo por un patrón "real": no lo hay.

**Criterio binario.** 18 comandos exit 0 + los greps de KPI-1, KPI-4 (los **dos**, negativo y positivo)
y `style={{` + el test AST de KPI-2 + el de KPI-6 + el one-liner de `PLAIN_HELP` de F0 + el one-liner
del endpoint de F5 + **`test_error_fingerprints_catalog.py` con el criterio delta de F7** (mismos 3
failed preexistentes, ninguno con el `id` de este plan, passed igual o mayor a 5 — **no** exit 0 llano:
ese archivo ya está rojo por deuda ajena, ver el FIX C1 más arriba).
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| **R1** | Ciclo de import: `runtime_capabilities` ← `claude_code_cli_runner` ← `model_catalog._merge_probe` (que importa `claude_code_cli_runner` en `model_catalog.py:135`, **dentro de la función**). | Media | Regla única de §5 F1: `runtime_capabilities` importa `model_catalog`/`llm_router`/`config` **sólo dentro de funciones**. El comando de verificación de imports de F1 es obligatorio y va **antes** de seguir. |
| **R2** | Honrar el effort en Codex altera el presupuesto de turnos. | Media | **El presupuesto sólo baja, y nunca por debajo de lo que ya bajaba hoy.** `codex_turn_budget` devuelve `<= cap` siempre, `0` se mantiene en `0`, y con `medium=1.0` la rama adaptativa da **exactamente** el mismo número que hoy (test 24 de F1, test 6 de F2). La flag `STACKY_CODEX_EFFORT_PARITY_ENABLED` permite volver atrás sin deploy. |
| **R3** | El `clamp_model` capa Opus a Sonnet y el operador cree que corre Opus. | Media | `clamp_selection` devuelve `degraded: True` + `reason`, y F6 lo muestra con `ModelDecisionChip` leyendo `trace.downgraded`. La degradación deja de ser silenciosa. |
| **R4** | Tocar `variant_generator.py` (call site 7 de F3) pisa trabajo sin commitear de una sesión paralela. | **Alta** (el repo tiene sesiones concurrentes) | `git status --porcelain` antes de cada archivo; si está sucio y no es tuyo, **saltear y registrar**. Prohibido `stash`/`reset`/`checkout --`. La allowlist del test 9 existe justamente para esto (máx. 2). |
| **R5** | Reemplazar el selector de `IncidentResolverModal` rompe el flujo del Dev Resolutor. | Media | El contrato del POST (`:243-244`) **no se toca**. Smoke manual obligatorio: abrir la bandeja, lanzar un resolutor, verificar en el detalle de la ejecución que `model_effort.tool` y `effective_effort` son los elegidos. Sin RTL/jsdom, este smoke **es** el gate de los `.tsx`. |
| **R6** | El test 9 de F3 (AST) se vuelve frágil y bloquea call sites legítimos. | Media | Es AST, no regex. Excluye `evals/` y `tests/`. Admite hasta **2** entradas de allowlist, con motivo escrito. |
| **R7** | `test_harness_flags_help` sale rojo. | **Alta** si se omite el archivo 3 de F0 | Tiene **4 fallos ajenos preexistentes** y por eso no está en F7 — **pero hay que agregar las 4 entradas a `PLAIN_HELP`** o son 4 rojos **propios**. Se valida con el one-liner de F0, que no adopta deuda ajena. |
| **R8** | Los tests que tocan la DB salen flaky (`SQLITE_LOCKED`). | **Alta** | Correr **por archivo**, 8-12 veces. Nunca la suite completa. Forzar `DATABASE_URL` in-memory: hay archivos en este repo que corren contra la **DB REAL**. |
| **R9** | La preferencia por proyecto muere en silencio si `STACKY_UI_SAVED_VIEWS_ENABLED` está OFF o el nombre del proyecto tiene caracteres fuera de `[A-Za-z0-9._-]`. | **Alta** sin el fix | `pref_key_for()` sanea la clave (test 5 de F4); `load/save` devuelven `None`/`False` sin lanzar cuando el store está OFF (test 6); el frontend usa `rawGet`/`rawPut` porque un 404 es un caso normal. Degradar a "sin preferencia" **nunca** rompe la corrida. |
| **R10** | Los planes 260/263/265 tocan los mismos archivos y git mergea sin marcar conflicto cuando dos ramas agregan la misma línea de cierre a una estructura existente. | **Alta** | Protocolo de §9.2, y tras cada merge: `compileall` + `tsc --noEmit` + grep de duplicados por key en `FLAG_REGISTRY` / `_CURATED_DEFAULTS_ON` / `_REQUIRES_MAP_FROZEN` / `PLAIN_HELP` / `HARNESS_TEST_FILES`. |
| **R11** | **[NUEVO por C2]** El gotcha del binding de `config` se aplica al revés y la flag queda muerta o el runner crashea. | **Alta** — ya pasó en el v2 | §3.8 (regla), el `grep` obligatorio antes de editar cada archivo, el test 9b de F2 (control del binding) y el **Test E** de F2.5 (gate AST acotado a los archivos del plan). |
| **R12** | **[NUEVO por C3]** El catálogo vivo no describe a Codex (`efforts: []`, `models: [""]`), así que la UI no puede ofrecer esfuerzo por más que el backend lo honre. | **Alta** | `capabilities_for()` **normaliza** (F1 (a) reglas 1-5), el endpoint lo publica (F1 (c)) y el test 22 es **no vacuo**. Se normaliza en código, **no** se edita `config/model_catalog.json` (así el probe y el fallback siguen siendo la única fuente del archivo). |
| **R13** | **[NUEVO por C8]** El operador cree que el esfuerzo en Codex hace algo y con el cap en 0 no hace nada. | **Alta** | `effort_effective_now` + `effort_note` honesta (F1), visible en el picker (F5) y en el trace (F4/F6). Se prefiere **decir la verdad** a esconder el control: la elección se guarda y aplica el día que haya cap. |

---

## 7. Fuera de scope

- **No** se agregan modelos ni runtimes nuevos al catálogo: se consume el que hay, **normalizado en
  código** (F1). `config/model_catalog.json` **no se edita**.
- **No** se toca `services/adaptive_selector.py` salvo **un comentario** (KPI-1, ítem 9).
- **No** se cambia `CLAUDE_CAP_MODEL` ni la política de `allow_opus` del `llm_router`.
- **No** se toca el `copilot_bridge` ni se le inventa un esfuerzo a GitHub Copilot Pro.
- **No** se persiste preferencia por usuario (mono-operador): la clave es por **proyecto**.
- **No** se migra el catálogo a base de datos: sigue en `config/model_catalog.json`.
- **No** se agrega un selector a pantallas que no lanzan corridas.
- **No** se toca `STACKY_MODEL_PROBE_ENABLED` ni se agrega ningún sondeo, timer o barrido que llame a un
  CLI o a un modelo sin pedido explícito del operador.
- **No** se cambia `STACKY_RUNAWAY_MAX_TURNS` ni su semántica (`0` = sin límite), **ni se le pone un
  valor por default al operador**. El effort se mueve **dentro** de ese techo, nunca lo modifica.
- **No** se borra el código muerto de `agent_runner.py:227-400` (sería un cambio de otro alcance, con
  su propio riesgo); sólo se lo mantiene coherente.
- **No** se extiende el gate de binding de F2.5 Test E a todo el repo (deuda ajena).
- **No** se toca la consola full-screen del Plan 265 (ver §9.3).

---

## 8. Orden de implementación y DoD

**Orden (estricto):**

0. **F(-1)** — [ADICIÓN ARQUITECTO] pre-flight de anclajes (re-medir, no confiar en los números
   citados en este documento para `config.py`/`harness_flags.py`/`endpoints.ts`).
1. **F0** — flags (**5 archivos**).
2. **F1** — `runtime_capabilities.py` + normalización + enriquecido del endpoint + deduplicación (12
   ediciones). **Verificar imports antes de seguir.**
3. **F2** — paridad de Codex en el call site **vivo** (el bug más grave; independiente de F3).
4. **F2.5** — centinelas ejecutables. **Va inmediatamente después de F2**, porque el Test A usa el fix
   de F2 como control positivo y su reversión (de **las dos** líneas) como control negativo.
5. **F3** — `resolve_run_selection` + los **11** call sites.
6. **F4** — persistencia + trace en los 3 runtimes.
7. **F5** — un solo selector en el frontend (**requiere F1 (c) verificado por HTTP**).
8. **F6** — historial visible.
9. **F7** — cierre + huella de regresión.

**Definición de Hecho (DoD):**

- [ ] **[ADICIÓN ARQUITECTO] F(-1) corrida antes de F0**, con la salida real pegada en §10 y los
      números re-medidos usados en vez de los citados en el documento donde difieran.
- [ ] Los 18 comandos de F7 salen **exit 0**, cero rojos. **Aparte** (no exit-0 llano, criterio
      delta — **[FIX C1 v3→v4]**): `test_error_fingerprints_catalog.py` sigue en **3 failed / 5
      passed** (baseline ajeno medido 2026-07-29, `class: "shell-navigation"`), con la huella nueva
      de este plan agregada y **sin** aparecer en ninguno de los 3 mensajes de fallo.
- [ ] **F0 tocó los 5 archivos**; `test_default_known_only_for_curated` **y**
      `test_requires_map_is_frozen` **verdes**; el one-liner de `PLAIN_HELP` imprime las 3 listas vacías.
- [ ] **KPI-1**: el "antes" se midió con el grep **antes** de editar (esperado **10**) y el "después"
      da **0**. Las 12 ediciones aplicadas.
- [ ] **KPI-2**: el test AST de F3 pasa sobre las **17** llamadas; a lo sumo **2** entradas de allowlist,
      con motivo escrito.
- [ ] **KPI-3**: `test_plan264_codex_effort_parity.py` verde **10 corridas seguidas**, incluidos los
      tests 2, 2b, 5, 6, 7, 9 y 9b.
- [ ] **KPI-3b**: `capabilities_for("codex_cli")["effort_effective_now"]` refleja el valor real de
      `STACKY_RUNAWAY_MAX_TURNS` y la nota lo dice (test 25 de F1).
- [ ] **KPI-4**: el grep **negativo** da 0 en los dos archivos **y** el **positivo** da ≥1 en los dos;
      superficies extra de F5(c) registradas con su veredicto.
- [ ] **KPI-5**: `EFFORT_MODE` cubre los 3 runtimes y el trace se persiste en los 3, **con `downgraded`
      y `reason` intactos**.
- [ ] **KPI-6**: `test_plan264_paridad_ejecutable.py` verde, y verificado a mano que su Test A sale
      **rojo** si se revierten **las dos** líneas de `agent_runner.py` (resultado anotado en §10).
- [ ] **KPI-7**: el one-liner de F5 imprime `effort_mode` para los 3 runtimes y `efforts: 5` para
      `codex_cli` sobre la **respuesta HTTP real**.
- [ ] Las 4 flags declaran `default=True`, están en `_CATEGORY_KEYS`, en `_CURATED_DEFAULTS_ON`
      (`tests/test_harness_flags.py:467`) y en `PLAIN_HELP`; las **3** con `requires=` están en
      `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`); y el plan deja escrito por
      qué ninguna cae en (A) ni (B).
- [ ] Los **5** archivos `tests/test_plan264_*.py` registrados en **ambas** listas
      (`run_harness_tests.sh:20` con entradas desnudas y `run_harness_tests.ps1:13` con entradas
      entrecomilladas); `test_harness_ratchet_meta.py` verde.
- [ ] `compileall` de `services/` y `api/` exit 0 (sin ciclos de import).
- [ ] Ningún símbolo público borrado ni clave de dict público perdida: `_clamp_effort_for_model`,
      `CLI_VALID_EFFORTS`, `build_model_effort_trace`, y las claves `downgraded` / `reason` del trace.
      Ninguna clave quitada de la respuesta del endpoint del catálogo.
- [ ] `style={{` no aumentó en los `.tsx` tocados (PlansBoardPage sigue en **3**); cero literales hex
      nuevos en CSS.
- [ ] Huella agregada a `docs/sistema/error_fingerprints.json` con el esquema real del archivo.
- [ ] Smoke manual del Dev Resolutor hecho (R5) y anotado. Sin RTL/jsdom, es el único gate de los `.tsx`.
- [ ] §9.2 respetada: registrado quién tocó `PlansBoardPage.tsx` primero y cómo se resolvió.
- [ ] Registro de implementación agregado en §10, con la salida real y los call sites que quedaron
      pendientes por trabajo ajeno.
- [ ] `git commit` con **pathspec explícito** (`git commit -- "<ruta>" ...`). Prohibido `git add -A`,
      `reset`, `amend`, `stash` y `--no-verify`. El `push` es manual.

---

## 9. Convivencia con los planes hermanos 260, 263 y 265

Los cuatro planes de esta tanda editan los mismos archivos compartidos y **git mergea sin marcar
conflicto** cuando dos ramas agregan la misma línea de cierre a una estructura existente, dejando un
duplicado silencioso. Esta sección existe para que eso no pase.

### 9.1 Contrato público congelado del 264

Estos símbolos **no cambian de nombre ni de firma** después de F1/F3. 260 y 265 pueden construir contra
ellos sin esperar a que este plan se implemente:

| Símbolo | Módulo | Estabilidad |
|---|---|---|
| `EFFORTS`, `EFFORT_ORDER`, `RUNTIMES`, `EFFORT_MODE`, `CODEX_EFFORT_TURN_FACTOR` | `services/runtime_capabilities.py` | congelados |
| `is_valid_effort(effort)` | idem | congelada |
| `capabilities_for(runtime) -> dict` | idem | claves del dict congeladas (se pueden **agregar**, nunca quitar); incluye `effort_effective_now` |
| `clamp_selection(runtime, model, effort, *, allow_opus=False) -> dict` | idem | congelada |
| `codex_turn_budget(effort, cap_turns) -> int` | idem | congelada; invariantes `<= max(cap,0)`, `0 -> 0`, y equivalencia con la fórmula de hoy |
| `resolve_run_selection(**kw) -> dict` | idem | congelada |
| `pref_key_for` / `load_run_preference` / `save_run_preference` | idem | congeladas |
| `read_ui_pref` / `write_ui_pref` | `api/preferences.py` | congeladas; **el contrato HTTP no cambia** |
| campos nuevos de `GET /api/agents/model-catalog` | `api/agents.py` | `effort_mode`, `effort_note`, `effort_effective_now`, `efforts` normalizados: **aditivos**, nunca se quita una clave existente |
| claves de `metadata_dict["model_effort"]` | trace | `requested_model`, `effective_model`, `requested_effort`, `effective_effort`, `downgraded`, `reason` **se conservan**; `tool`, `effort_mode`, `effort_effective_now`, `origen_*` se **agregan** |

**Flags del 264 (no las renombra nadie más):** `STACKY_RUNTIME_CAPABILITIES_ENABLED`,
`STACKY_CODEX_EFFORT_PARITY_ENABLED`, `STACKY_RUN_SELECTION_PREFS_ENABLED`,
`STACKY_MODEL_PICKER_EVERYWHERE_ENABLED`. Verificado: **no colisionan** con las de 260, 263 ni 265.

### 9.2 Frontera de merge, archivo por archivo

| Archivo compartido | Quién más lo toca | Protocolo |
|---|---|---|
| `backend/config.py`, `services/harness_flags.py`, **`services/harness_flags_help.py`**, `tests/test_harness_flags.py`, **`tests/test_harness_flags_requires.py`**, `scripts/run_harness_tests.sh` + `.ps1` | **los 4 planes** | Cada plan agrega su **propio bloque contiguo** con el comentario `# Plan NNN — …` **antes** de sus entradas, y **nunca** reordena las ajenas. Tras cada merge: `compileall`, `tsc --noEmit` y grep de duplicados por key en las **5** estructuras. |
| **`frontend/src/pages/PlansBoardPage.tsx`** | **Plan 263** (lo reescribe para densidad) | **Regla dura: el 263 va PRIMERO.** El 264 toca dos zonas puntuales (los selectores de `:147-162`/`:336-357` en F5, y la fila del historial de `:478-486` en F6); el 263 reescribe el layout. Si el 263 ya está en el árbol, el 264 aplica sus dos cambios **sobre el archivo del 263**. Si el 264 va primero, **el 263 debe conservar el `<ModelEffortPicker>` en vez de reconstruir un `<select>`** — y este plan lo declara acá para que el juez del 263 pueda exigirlo. En ningún caso se toca `PlansBoardPage.module.css` más allá de lo que el ratchet permite (39 hex, `uiDebtBaseline.json:66`; `style={{` en 3, `:136`). |
| `services/claude_code_cli_runner.py` | Planes **260** y **265** | El 264 toca 3 puntos identificables: `CLI_VALID_EFFORTS` (`:2224`), `build_model_effort_trace` (`:516-540`) y nada más. Si otro plan tocó el archivo, aplicar por **hunk**, nunca reescribir el archivo entero. |
| **`backend/agent_runner.py`** | Planes **260** y **265** | El 264 toca **2 líneas** (`:449`/`:450` de la rama viva y `:264`/`:265` de la muerta). Aplicar por hunk. Si el archivo está sucio por otra sesión, **saltear y registrar** (R4). |
| `services/llm_router.py`, `services/model_catalog.py` | Plan **260** | El 264 **sólo lee** de ambos; no los modifica. |
| `api/agents.py` | Plan **260** | El 264 toca **6 líneas de literales** (`:425, 681, 717, 934, 963, 1156`) y **un bloque aditivo** en el endpoint del catálogo (`:1382-1386`). Aplicar por hunk. |
| `backend/services/plans_board.py` | Planes **263** y **265** | El 264 **no lo toca**. |
| `frontend/src/api/endpoints.ts` | los 4 | El 264 agrega **dos campos opcionales** (`effort_mode?`, `effort_effective_now?`) al tipo `RuntimeModelCatalog` (`:1071-1084`). Aditivo, sin romper a nadie. |

### 9.3 ¿La consola full-screen del Plan 265 entra en el KPI de "todo punto de uso"?

**No, y queda declarado por qué.** El Plan 265 **crea** una superficie que hoy no existe. Si el KPI-4 de
este plan enumerara superficies futuras, nacería incompleto por construcción y sería imposible de cerrar.

Por eso el KPI-4 del 264 se define sobre el **censo del 2026-07-27** (las 2 pantallas con selector hecho
a mano: `PlansBoardPage` e `IncidentResolverModal`), y **no** sobre "todas las superficies que existan
algún día".

**Lo que el 264 sí hace por el 265** — y es más útil que enumerarlo:

1. Le deja el contrato congelado de §9.1, para que la consola **consuma** `capabilities_for()` +
   `<ModelEffortPicker>` en vez de inventar un tercer selector.
2. Le deja los gates de F2.5: si la consola del 265 lanza corridas y agrega un runtime a `RUNTIMES` sin
   honrar el effort, **el Test B rompe solo**; si lo honra sin efecto observable, **rompe el Test D**;
   si aplica mal el binding de `config`, **rompe el Test E**.
3. **Ítem explícito para el DoD del Plan 265** (no del 264): "la consola full-screen usa
   `<ModelEffortPicker>` alimentado por `capabilities_for()`; cero `<select>` de modelo/effort propio".
   Este plan lo deja escrito acá para que el juez del 265 pueda exigirlo sin negociar.

---

## 10. Registro de implementación

_(a completar por `implementar-plan-stacky`: salida real del pre-flight de anclajes de **F(-1)** (y
los números corregidos que se usaron si volvieron a moverse), salida real de cada comando, el número
del grep de KPI-1 **antes** de editar, call sites que quedaron pendientes por trabajo ajeno, resultado
del control negativo de F2.5 Test A revirtiendo **las dos** líneas, salida del one-liner de
`PLAIN_HELP`, salida del one-liner del endpoint enriquecido, veredicto final de los 3 candidatos de
F5(c) (incluida la confirmación de a qué endpoint llama `DocsPage.tsx:handleProposeUpdate` y si ese
endpoint cae en `doc_documenter.py`), y `killed_commit`/`date_resolved` reales para la huella de
`error_fingerprints.json`.)_
