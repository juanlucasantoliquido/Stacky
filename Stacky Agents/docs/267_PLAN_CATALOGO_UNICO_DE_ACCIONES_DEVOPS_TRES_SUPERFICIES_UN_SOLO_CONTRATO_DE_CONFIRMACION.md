# Plan 267 — Catálogo único de acciones DevOps: una sola declaración, tres superficies, un solo contrato de confirmación

**Estado:** **CRITICADO v1 → v2** (2026-07-27) · **Autor:** pipeline proponer-plan-stacky · **Juez:** criticar-y-mejorar-plan (Opus 5) · **Veredicto v1: RECHAZADO** (5 bloqueantes)

> **Nota de numeración.** Este plan nació como **266** y se renumeró a **267**: mientras se escribía, una
> sesión paralela commiteó `9281ca75 docs(plan-266): cero pantalla rota en el comparador de BD`, que tomó
> el 266 primero. Ese plan toca `frontend/src/components/dbcompare/` y `radarLogic.ts`; **no hay
> superposición de archivos con este**. Los números **261 y 262** siguen libres (huecos preexistentes).
> *Verificado en la crítica v2:* no quedó **ninguna** referencia interna stale al número viejo — ni flags,
> ni archivos, ni tests, ni fases. Las únicas apariciones son las de esta misma nota.

### CHANGELOG v1 → v2

Los anclajes `archivo:línea` del v1 se verificaron **uno por uno abriendo los archivos reales**. El
resultado fue inusualmente bueno (los 17 ids de secciones, los 21 `health_key`, las 16 flags citadas,
los 3 conteos de tests y los 4 rojos ajenos son **exactos**), pero aparecieron 5 bloqueantes:

| # | Severidad | Qué estaba mal | Dónde se corrigió |
|---|-----------|----------------|-------------------|
| **C1** | BLOQUEANTE | `HARNESS_TEST_FILES` **no existe** en `run_harness_tests.ps1`: ahí es `$HarnessTestFiles = @(` en **`:13`** (no `:15`) y las entradas van **entrecomilladas y con coma**, no desnudas. Además `test_harness_ratchet_meta.py` parsea **solo el `.sh`** | §4.2, F0, F1, F2, F8, §10 |
| **C2** | BLOQUEANTE | El test 4 de F2 salía **rojo el día 1** contra el propio algoritmo del plan: `"Quiero DISPARAR la píplain"` da **0.667 ≥ `MIN_SCORE`** porque `_phrase_score` cuenta `la` como token de contenido | F2 (stopwords + caso reescrito) |
| **C3** | BLOQUEANTE | Los tests 3/5/6 de F2 afirman **quién gana** el ranking, pero el v1 declaraba `phrases` literales para **4 de 23** acciones. El criterio no era determinable | F0 (las 23 listas declaradas) |
| **C4** | BLOQUEANTE | Contradicción triple: §4.7 decía "el mismo texto de confirmación", F7 decía "el texto de la confirmación **cambia**", y la DoD tenía un checkbox binario **falso por construcción** | §4.7, F7, §11 |
| **C5** | BLOQUEANTE | F5 ponía las **7 acciones de escritura de alto impacto** a dos teclas de la paleta global, sin el doble cerrojo que el propio plan elogia (`entityActions.ts:44-46`), y sin flag que lo gatee | §4.10 + campo `reach` (F0), F5, F8 |
| C6 | IMPORTANTE | El catálogo ignoraba el master `STACKY_DEVOPS_PANEL_ENABLED` | F0 `visible_actions` |
| C7 | IMPORTANTE | `replace(...)` usado sin importar en `/propose` ⇒ `NameError`, y sin test que cubriera el camino `ambiguous` | F3 |
| C8 | IMPORTANTE | 3 KPIs se medían con un comando que **no los mide** | §2 |
| C9 | IMPORTANTE | KPI-1 exigía `section_id`+`flag_key` en **todas**, contra su propia semilla y el test 5 de F0 | §2 |
| C10 | IMPORTANTE | `PLAIN_HELP` literal para 1 de 3 flags, sobre un archivo **que ya está rojo** (medido: 4 failed / 4 passed) | F3, F6, §4.1 |
| C11 | IMPORTANTE | `devopsPollingRatchet.test.ts` **no escanea** `CommandPalette.tsx` (solo `components/devops/`) y estaba declarado criterio de F5 | F5 |
| C12 | IMPORTANTE | Los 2 `.tsx` nuevos de F6 no pueden tener **ni un** `style={{` (baseline por archivo = 0) y el plan no lo decía | F6 |
| C13 | IMPORTANTE | F1 test 3 no decía **cómo** apagar "todas las flags DevOps" | F1 |
| C20 | IMPORTANTE | F6 obligaba a prometerle al operador "te deja en la sección **con los datos ya cargados**" y no había mecanismo que lo cumpliera | F4 `navPathWithParams` |
| C14..C19 | MENOR | Pata 7 contradictoria, 6 anclajes corridos, nombre de test más débil que su assert, imports muertos, huella de regresión, frontera del 264/265 | varios |

**[ADICIÓN ARQUITECTO] — `reach`: el catálogo declara también *desde dónde puede dispararse* una acción.**
El v1 unificaba *qué es* y *si escribe*, pero dejaba *desde qué superficie puede ejecutarse* implícito en
el código de cada superficie — que es exactamente el agujero de C5. El v2 agrega un cuarto eje declarado y
verificado por ratchet (§4.10, F0, F5, F8), más `navPathWithParams()` para que "Ver en el panel" cumpla su
promesa (C20). Con eso, "una declaración, tres superficies" pasa a ser cierto también en la dimensión de
seguridad, y no solo en la de nomenclatura.

---

## 1. Objetivo

Hoy el panel DevOps tiene 17 secciones y decenas de acciones, y **cada acción existe una sola vez: pegada a mano en el JSX de la sección que la inventó**. No hay ninguna lista de "qué se puede hacer en DevOps". Por eso la paleta global no puede ejecutar ni una sola acción del panel (solo navega), el agente DevOps devuelve prosa en vez de una acción tipada, y cada sección se escribe su propia confirmación con su propio texto y su propio criterio de peligro. El plan 267 crea el **Catálogo de Acciones DevOps**: una declaración única y verificable de cada acción (qué es, en qué sección vive, si lee o escribe, qué impacto tiene, sobre qué entorno actúa, qué parámetros necesita, qué flag la gatea y cómo se pide en español), consumida por **las tres superficies**: los botones manuales que ya existen, la paleta de comandos, y el agente de lenguaje natural — que deja de contestar texto y pasa a devolver una **propuesta de acción tipada** (`ActionProposal`) con el molde de `IntentBrief` del plan 41: *qué acción, sobre qué entorno, qué impacto, qué va a pasar* → tarjeta de vista previa → `confirmGateway` → **recibo del resultado**. Un ratchet impide que nazca una acción nueva fuera del catálogo. Eso es lo que vuelve la coherencia de la UX **verificable por test** en vez de una promesa de checklist visual.

## 2. KPI / impacto (Antes medido contra el árbol del 2026-07-27)

| # | Métrica | Antes (medido) | Después (binario) | Comando que lo mide |
|---|---------|----------------|-------------------|---------------------|
| KPI-1 | Acciones del panel DevOps declaradas en un catálogo | **0** (no existe el archivo) | **≥ 23**, todas con `effect`, `impact`, `reach` y `phrases`; `section_id` ∈ (ids reales ∪ `None`); `flag_key` **no vacío para toda `write`** [C9] | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_catalog.py -v` |
| KPI-2 | Comandos de la paleta que **ejecutan** una acción del panel | **0** — `NAV_COMMANDS` (`frontend/src/components/commandPaletteData.ts:59-76`) tiene 14 entradas y las 14 son navegación | **≥ 12** entradas `kind:"devops-action"`, **todas de `effect:"read"`** (las `write` entran como navegación, §4.10) | `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts` — caso `test_paleta_ofrece_al_menos_12_lecturas`, que cuenta sobre el **catálogo real**, no sobre entrada sintética [C8] |
| KPI-3 | Entidades cubiertas por el registro de acciones | **2** — `EntityKind = Extract<CommandKind,"execution"\|"ticket">` (`frontend/src/services/entityActions.ts:15`) | **3** (se suma `devops-action` como tercer vocabulario, sin tocar los 2 existentes) | dos corridas **separadas** (regla §4.2, un archivo por invocación): `npx vitest run src/services/entityActions.test.ts` y `npx vitest run src/services/devopsActionRunner.test.ts` [C8] |
| KPI-4 | Respuestas del agente DevOps que son una acción tipada | **0** — `api/devops_agent.py` lanza un turno de CLI y devuelve prosa (`backend/api/devops_agent.py:136-140`) | **100 %** de las frases que superan el umbral del matcher devuelven `ActionProposal` con `action_id` | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v` |
| KPI-5 | Runtimes soportados por el camino "lenguaje natural → acción" | **2 de 3** — `_CLI_RUNTIMES = ("claude_code_cli","codex_cli")` (`backend/api/devops_agent.py:14`) y Copilot recibe **400** `devops_chat_requires_cli_runtime` (`backend/api/devops_agent.py:69-78`) | **3 de 3**: el matcher determinista no usa modelo, así que Copilot obtiene propuesta y vista previa completas | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -k copilot -v` |
| KPI-6 | Confirmaciones de acciones DevOps construidas a mano fuera de `confirmGateway` | **16 construcciones en 6 archivos** — medido con `grep -c 'askConfirm({'`: `ServersSection` 2, `BuildWorkshopSection` 2, `PipelineBuilderSection` 4, `ProductionFlow` 2, `RemoteConsoleSection` 1, `SolutionPublisherSection` 5 | **0 en esos 6 archivos**: todas derivan su `ConfirmRequest` del catálogo | `npx vitest run src/__tests__/plan267Adoption.test.ts` — es **este** el test que mira `askConfirm({`, no el ratchet de catálogo [C8] |
| KPI-7 | Deriva backend↔frontend de acciones | **N/A** (no hay contrato que derive) | **0**: igualdad exacta de conjuntos entre ids del catálogo y claves de `DEVOPS_ACTION_BINDINGS` | `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts` |
| KPI-8 | Acciones con `effect:"write"` sin declarar impacto ni entorno | **N/A** | **0**: `targets_environment=True` ⇒ param `environment` obligatorio; `effect="write"` ⇒ `impact != "none"` | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v` |
| **KPI-9** *(v2, C5)* | Acciones de escritura **ejecutables desde la paleta global** | **N/A** (hoy la paleta no ejecuta nada) | **0**: `effect=="write"` ⇒ `"palette-run" not in reach`. Una acción de alto impacto nunca queda a un fuzzy-match + Enter de distancia | `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v` (caso `test_write_no_es_ejecutable_desde_la_paleta`) |

Cómo se obtuvo cada "Antes": KPI-1 por ausencia del archivo (`backend/services/devops_action_catalog.py` no existe); KPI-2 contando las entradas del array literal en `commandPaletteData.ts:59-76` (el comentario de `:58` dice "13 tabs" — quedó desactualizado, hay 14); KPI-3 leyendo `entityActions.ts:15`; KPI-4 y KPI-5 leyendo `api/devops_agent.py`; KPI-6 por `grep -c "askConfirm({"` sobre los 6 archivos de `frontend/src/components/devops/` (los 6 conteos están arriba, medidos el 2026-07-27).

---

## 3. Por qué ahora, y por qué esto NO duplica al plan 239

### 3.1 El 239 ya hizo el rediseño de shell. El 267 no lo toca.

`docs/239_PLAN_COCKPIT_DEVOPS_REDISENO_INTEGRAL_UX_UI_E_INFORMACION.md` está **IMPLEMENTADO (2026-07-25, F0..F8)** y entregó exactamente la parte estructural del rediseño:

- **F4** — shell v3 con navegación agrupada de dos niveles: `frontend/src/pages/devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, `DevOpsTabsV2.tsx`, `DevOpsHeaderV2.tsx`. Los 4 grupos están congelados en `devopsCockpitShell.ts:20-25` (`resumen` / `operar` / `construir` / `diagnosticar`).
- **F5** — deep-link `/devops/<seccion>` y sección de inicio fijable (`resolveLandingSection`, `devopsCockpitShell.ts:119-149`).
- **F6** — fin del sondeo perpetuo: `visible?: boolean` en el contexto (`DevOpsPage.tsx:76-79`) + ratchet `devopsPollingRatchet.test.ts`.
- **F7a** — convergencia a tokens: 0 hex en los `.module.css` de DevOps. **F7b** — barrido de estilos inline: 385 ≤ 386.
- **F1/F3** — sección Resumen (`backend/services/devops_overview.py`, `GET /api/devops/overview`, `DevOpsOverviewSection.tsx`).

Y declara textualmente que **falta solo lo VISUAL** (checklist de 10 puntos de F8 que requiere navegador; RTL y jsdom no están en el `package.json` del frontend).

**Conclusión operativa: re-proponer navegación, grupos, tokens o barrido de inline styles sería trabajo ya hecho.** El 267 hereda ese shell tal cual y no edita `devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, `DevOpsTabsV2.tsx` ni `DevOpsHeaderV2.tsx` (ver §8, frontera de merge). Lo único que el 267 agrega al shell es *consumir* `DevOpsSection.id`, que ya existe.

### 3.2 El gap que el 239 dejó abierto es de **acciones**, no de layout

El 239 unificó *dónde está cada cosa*. No unificó *qué se puede hacer y cómo se pide permiso*. Cuatro piezas del repo lo gritan:

1. **`frontend/src/services/entityActions.ts` (193 líneas, plan 175 F1)** ya demostró el patrón correcto: el registro es DATOS, no JSX. Su comentario de cabecera (`:3-5`) dice literalmente:
   > *"el menú contextual, las acciones rápidas inline y **(mañana) la paleta** consumen la misma lista. Si cada superficie armara la suya, terminarían ofreciendo cosas distintas para la misma entidad."*

   Ese "mañana" nunca llegó, y el registro cubre **2 entidades**: `EntityKind = Extract<CommandKind, "execution" | "ticket">` (`:15`). **Ninguna acción del panel DevOps está adentro.** Tiene el doble cerrojo `quickActions()` (`:44-46`: `a.quick && a.effect === "safe"`) — la semántica de seguridad correcta, aplicada a 2 de las ~23 acciones que el operador realmente ejecuta.

2. **`frontend/src/services/confirmGateway.ts`** ya es el punto único de HITL: `ConfirmRequest{title,message,confirmLabel,tone}` (`:10-15`), `ConfirmFn` (`:17`) y `denyByDefault` que **niega por default** (`:19-21`), con la prohibición explícita de diálogos nativos del navegador (`:7-8`). Pero como las acciones DevOps no están declaradas, cada sección arma su `ConfirmRequest` a mano con su propio criterio de `tone` — al menos 6 archivos (KPI-6).

3. **`frontend/src/components/commandPaletteData.ts` (125 líneas, plan 129)** tiene `Command{id,kind,icon,label,hint,run}` (`:21-28`), `CommandKind` con 9 valores (`:10-19`) y `fuzzyScore()` (`:31-49`) — toda la maquinaria para ejecutar acciones. Y `NAV_COMMANDS` (`:59-76`) son **14 entradas de navegación pura**. La paleta es un ascensor, no un panel de mandos.

4. **`backend/api/devops_agent.py` (364 líneas, plan 90)** es un chat de texto libre: `POST /devops/agent/conversations` con `project`/`message`/`runtime`/`model`/`server_alias`. No conoce ningún catálogo, no propone una acción tipada, no tiene contrato preview→confirmación→resultado. Además **rechaza Copilot con 400** (`:69-78`) y duplica el literal de efforts en `:15` (`_EFFORTS`), cuando el 264 congela ese eje en `services/model_catalog.py` + `services/llm_router.py`.

Y ya existe el molde exacto para el "esto entendí y así lo haría": **`backend/services/intent_preflight.py` (plan 41)** con `IntentBrief{objective,deliverables,assumptions,open_questions,areas,confidence,version}` (**`:38-46`** — el v1 citaba `:39-47`, corrido en 1 [C15]), `IntentAssumption{text,impact,needs_confirmation,basis}` (**`:29-35`**), `PreflightRuntimeUnavailable` (`:25-26`, exacto) y un parser tolerante `from_model_json` (`:81`, exacto). **No se inventa un contrato nuevo: se calca ese.**

### 3.3 Lo que pidió el operador, mapeado

| Pedido literal | Cómo lo cubre el 267 |
|---|---|
| "consultar el estado de los servicios" | acciones `devops.overview.refresh`, `devops.servers.list`, `devops.servers.doctor` (F7) |
| "gestionar despliegues" | `devops.deployments.history` (read) + `devops.deployment.execute` (write, `impact:high`) |
| "revisar logs" | `devops.logs.tail` (`section_id=None`, `nav_path="/logs"`) |
| "configurar pipelines" | `devops.pipelines.inventory`, `devops.pipeline_edit.preview` (read) + `devops.pipeline_edit.commit` (write) |
| "detectar incidencias" | `devops.incidents.list`, `devops.pipelines.audit` |
| "proponer soluciones" | `ActionProposal.what_will_happen` + `open_questions` + `alternatives` |
| "ejecutar acciones" | `runDevOpsAction()` — el **mismo** binding que usa el botón manual |
| "confirmar operaciones sensibles antes de realizarlas" | `confirmRequestFor()` derivado del catálogo → `confirmGateway`; `denyByDefault` |
| "mostrar qué acción, sobre qué entorno, cuál impacto, cuál resultado" | los 4 campos son **obligatorios** en la tarjeta: `label` / `environment` / `impact` / `DevOpsActionReceipt` |
| "sin eliminar la posibilidad de hacerlo manualmente" | los botones existentes **no se borran**: se recablean al mismo `runDevOpsAction` |

---

## 4. Principios y guardarraíles (aplican a todas las fases)

1. **Human-in-the-loop innegociable.** El agente **propone**, el operador **confirma**. Cero autonomía proactiva: ninguna fase agrega un loop, daemon, barrido, prefetch o inyección de contexto. Nada se ejecuta sin un click del operador. `denyByDefault` (`confirmGateway.ts:21`) es la semántica correcta y se reusa tal cual.
2. **Una sola declaración.** El catálogo backend es la fuente de verdad de la *identidad y la seguridad* de una acción. El binding frontend es la fuente de verdad de *cómo se hace*, reusando los endpoints que **ya existen**. Ningún endpoint de ejecución nuevo. Un ratchet exige igualdad de conjuntos entre ambos.
3. **Cero trabajo extra al operador.** Sin pasos manuales nuevos, sin configuración nueva, sin migración. Todas las acciones siguen disponibles con el mismo click de hoy.
4. **Regla de default de flags.** Toda flag nueva nace **ON**. Solo nace OFF si cae en **(A)** quema tokens en reposo o **(B)** escribe en un sistema real / le saca la decisión al operador. Leer, calcular, mostrar, diffear, auditar y avisar son **siempre ON**. Cuando una capacidad mezcla lo inocuo con lo que escribe, se **parte en dos flags** (precedente: `STACKY_PIPELINE_NL_EDIT_ENABLED` ON en `harness_flags.py:3149-3165` vs `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` OFF en `:3166-3187`).
5. **Paridad de 3 runtimes por construcción.** El matcher de intención es **determinista y sin modelo**. Codex CLI, Claude Code CLI y GitHub Copilot Pro obtienen el mismo catálogo, la misma propuesta y la misma vista previa. El enriquecimiento por LLM es un extra opcional que, si falla o no está disponible, **degrada al resultado determinista** — nunca a un error.
6. **Mono-operador.** Sin RBAC, sin roles, sin multiusuario. `current_user` sigue siendo el header sin validar de `api/_helpers.py`.
7. **Backward-compatible, con una excepción declarada [C4].** Con las tres flags apagadas: los mismos botones, en los mismos lugares, con el **mismo efecto** y la **misma severidad** (una confirmación que hoy es `tone:'danger'` sigue siendo `'danger'`). **Lo único que cambia es el TEXTO de la confirmación**, que a partir de F7 lo genera `confirmRequestFor()` desde el catálogo en vez de estar escrito a mano en cada sección — que es justamente el punto del plan. El v1 afirmaba a la vez "byte-idéntico" y "el texto cambia": no pueden ser ciertas las dos, y esta es la que vale. Ninguna otra ruta de código existente cambia de comportamiento por default.
8. **Reuso obligatorio.** `confirmGateway`, `entityActions` (patrón), `IntentBrief` (molde), `fuzzyScore` (paleta), `ModelEffortPicker` + `llm_router.clamp_model`/`clamp_effort_for_model` (264), flags del arnés, `devops_overview`. **Prohibido** crear un segundo mecanismo de confirmación, un segundo enum de efforts o un segundo catálogo de modelos.
9. **Nada de sondeo.** Ninguna fase introduce `setInterval`, `setTimeout` recurrente ni `refetchInterval`. `frontend/src/__tests__/devopsPollingRatchet.test.ts` (plan 239 F6) ya lo vigila y debe seguir verde — **pero solo escanea `frontend/src/components/devops/`** (`DEVOPS_DIR = path.resolve(__dirname, '../components/devops')`, `:21`). Para `CommandPalette.tsx`, que vive en `components/` y **no** está en ese alcance, F5 trae su propio grep-gate [C11].

### 4.10 Alcance de disparo (`reach`) — el doble cerrojo, elevado a dato [ADICIÓN ARQUITECTO, C5]

El v1 declaraba *qué es* una acción y *si escribe*, pero dejaba **desde qué superficie puede ejecutarse**
implícito en el código de cada superficie. Eso abría un agujero concreto: hoy, disparar
`devops.deployment.execute` exige navegar a `/devops/despliegues`; con la paleta ejecutando acciones
bastaría abrirla, teclear `desp` (`fuzzyScore` matchea por **subsecuencia**, `commandPaletteData.ts:31-49`)
y apretar Enter. `entityActions.ts:44-46` ya resolvió este problema para 2 entidades con un **doble
cerrojo** (`a.quick && a.effect === "safe"`) y el §3.2 lo cita como el patrón correcto — el v1 lo elogiaba
y no lo aplicaba.

**Regla dura.** Cada acción declara `reach: tuple[str, ...]`, subconjunto no vacío de
`REACHES = ("button", "palette-run", "palette-nav", "assistant")`:

| valor | significa |
|---|---|
| `button` | el botón manual de su sección puede ejecutarla (**todas** lo llevan) |
| `palette-run` | la paleta global puede **ejecutarla** |
| `palette-nav` | la paleta global la **ofrece**, pero seleccionarla **navega** a su sección con los parámetros precargados; no ejecuta nada |
| `assistant` | el asistente puede proponerla (y ejecutarla si la flag 3 está ON) |

**Invariante I-REACH, verificada por ratchet (F8):** `effect == "write"` ⇒ `"palette-run" not in reach`.
Sin excepciones y sin allowlist: si mañana alguien quiere una escritura en la paleta, tiene que borrar el
test, y borrar un test es una decisión visible. Las 7 acciones de escritura llevan
`reach=("button","palette-nav","assistant")`; las 16 de lectura llevan
`reach=("button","palette-run","assistant")`.

Esto **no le saca nada al operador**: la acción de escritura sigue apareciendo en la paleta (la encuentra
buscando), y elegirla lo deja en la pantalla correcta con los datos cargados, a un click del botón de
siempre. Es la misma filosofía de `denyByDefault`: el camino peligroso existe, pero nunca es el accidental.

### 4.1 Receta obligatoria de cableado de flags (7 patas)

Cada flag nueva de este plan toca **hasta 7 lugares**. Saltear uno deja un test en rojo:

| # | Lugar | Cuándo |
|---|---|---|
| 1 | `backend/config.py` — el atributo con `os.getenv(...)` | **siempre** (es el default EFECTIVO) |
| 2 | `backend/services/harness_flags.py` — la `FlagSpec` (campos en `:21-41`) | siempre |
| 3 | `backend/services/harness_flags.py` — `_CATEGORY_KEYS` (mapa en `:120`, categoría `"devops"` en `:223`) | siempre |
| 4 | `backend/services/harness_flags_help.py` — `PLAIN_HELP` (dict en `:25`, dataclass en `:17-23`) | siempre |
| 5 | `backend/tests/test_harness_flags.py:467` — `_CURATED_DEFAULTS_ON` | **solo si la `FlagSpec` declara `default=True`** |
| 6 | `backend/tests/test_harness_flags_requires.py:120` — `_REQUIRES_MAP_FROZEN` | **solo si la `FlagSpec` declara `requires=`** |
| 7 | `backend/api/devops.py::_health_payload()` (`:28-108`, verificado: `def` en `:28`, `}` de cierre en `:108`) | **siempre que la UI necesite saber si la flag está ON** — no solo cuando gatea una sección. Las 3 flags de este plan van al `_health_payload()` (F1) aunque **ninguna** gatee una sección; lo que es condicional es tocar `DEVOPS_SECTIONS` en `DevOpsPage.tsx`, y este plan **no lo toca** [C14] |

**REGLA DURA:** una flag **default OFF NO debe declarar `default=False`** en la `FlagSpec`. Declarar cualquier default la vuelve `default_is_known` y `test_default_known_only_for_curated` exige que ese conjunto sea EXACTAMENTE `_CURATED_DEFAULTS_ON`, donde una flag OFF no puede entrar. El OFF vive **solo** en `config.py`. Precedente literal: `harness_flags.py:3169-3173`.

**REGLA DURA (R4):** `validate_requires_graph` (`harness_flags.py:5545-5569`) prohíbe cadenas: si `A.requires = B`, entonces `B.requires` debe ser `None`. Por eso las tres flags de este plan forman una **estrella**, no una cadena (ver §5.0.4).

**PLAIN_HELP:** los 4 campos tienen límites (`what` ≤200, `on_effect` ≤240, `off_effect` ≤240, `example` ≤300, declarados en `harness_flags_help.py:19-22`); `on_effect`/`off_effect` empiezan con `"Si "`; está prohibida la denylist congelada de jerga de `backend/tests/test_harness_flags_help.py:17-20` — **15 palabras, match por palabra completa e insensible a mayúsculas**: `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex, backend, frontend, gate, hook, runtime` — las keys `SCREAMING_SNAKE` (`_KEY_RE = \b[A-Z]+_[A-Z0-9_]+\b`) y las referencias a fases (`_PHASE_RE = \bF\d`).

**REGLA DURA [C10] — `test_harness_flags_help.py` NO sirve como criterio de aceptación de este plan.**
Medido el 2026-07-27 con `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_help.py -q`:
**4 failed, 4 passed**, y los 4 rojos son **exactamente las 4 reglas que las entradas nuevas deben cumplir**
(`test_plain_help_covers_all_registry_keys`, `test_plain_help_fields_non_empty_and_bounded`,
`test_plain_help_on_off_start_with_si`, `test_plain_help_avoids_jargon_denylist`). Es decir: el archivo
está rojo por deuda ajena y **un modelo menor no puede distinguir su propio error del rojo preexistente**.
Por eso este plan escribe el texto LITERAL de las 3 entradas (F0, F3 y F6 — ninguna queda "a criterio") y
la verificación de las claves propias se hace con este comando, que **no depende** del archivo rojo:

```
backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'backend'); import re; from services.harness_flags_help import PLAIN_HELP; D=('MCP','TF-IDF','LLM','stdin','stdout','endpoint','frontmatter','prompt','token','regex','backend','frontend','gate','hook','runtime'); L={'what':200,'on_effect':240,'off_effect':240,'example':300}; K=['STACKY_DEVOPS_ACTION_CATALOG_ENABLED','STACKY_DEVOPS_ACTION_NL_ENABLED','STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED']; e=[]
for k in K:
    h=PLAIN_HELP.get(k)
    if h is None: e.append(k+': FALTA'); continue
    for f,m in L.items():
        v=getattr(h,f)
        if not v or len(v)>m: e.append(f'{k}.{f}: largo {len(v)} > {m} o vacio')
    for f in ('on_effect','off_effect'):
        if not getattr(h,f).startswith('Si '): e.append(f'{k}.{f}: no empieza con Si ')
    t=' '.join([h.what,h.on_effect,h.off_effect,h.example])
    for w in D:
        if re.search(r'\b'+re.escape(w)+r'\b',t,re.I): e.append(f'{k}: jerga prohibida {w!r}')
    if re.search(r'\b[A-Z]+_[A-Z0-9_]+\b',t): e.append(k+': cita una clave en mayusculas')
    if re.search(r'\bF\d',t): e.append(k+': cita una fase')
print('OK' if not e else '\n'.join(e)); sys.exit(1 if e else 0)"
```
**Aceptación binaria:** imprime `OK` y sale con código 0.

### 4.2 Reglas de test (no negociables)

- **Correr SIEMPRE por archivo, nunca la suite completa** (contaminación cross-file conocida en backend y en vitest).
- Backend: `backend\.venv\Scripts\python.exe -m pytest backend/tests/<archivo>.py -v` desde la raíz `Stacky Agents`.
- Frontend: `npx vitest run src/<ruta>.test.ts` **desde `frontend/`**.
- **REGLA DURA [C1] — los dos runners NO se escriben igual.** El v1 decía "`HARNESS_TEST_FILES` en los DOS runners, `.sh:20` y `.ps1:15`". **Eso es falso y un modelo menor lo implementa mal.** Verificado abriendo los dos archivos:

  | runner | símbolo REAL | línea REAL | sintaxis de una entrada |
  |---|---|---|---|
  | `backend/scripts/run_harness_tests.sh` | `HARNESS_TEST_FILES=(` | **`:20`** | `  tests/test_devops_action_catalog.py` — **desnuda**, sin comillas y sin coma |
  | `backend/scripts/run_harness_tests.ps1` | `$HarnessTestFiles = @(` | **`:13`** (no `:15`) | `  "tests/test_devops_action_catalog.py",` — **entrecomillada y con coma** |

  Copiar la línea de un runner al otro rompe: en PowerShell una entrada desnuda es un error de parseo, y en el `.sh` una entrada entrecomillada **deja de matchear** el ratchet.
- **El meta-test parsea SOLO el `.sh`.** `backend/tests/test_harness_ratchet_meta.py:13` fija `_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"` y `:18-21` lo parsea con `re.findall(r"^\s*(tests/[\w/]+\.py)\s*$", ...)` — línea entera, sin comillas ni coma. Consecuencia práctica: **olvidar el `.sh` pone rojo el meta-test; olvidar el `.ps1` NO lo pone rojo**, y deja el arnés de Windows corriendo menos tests que el de bash sin que nadie se entere. Los dos son obligatorios, por motivos distintos.
- `backend/tests/test_harness_flags_help.py` arrastra **4 fallos ajenos preexistentes** (medido 2026-07-27: 4 failed / 4 passed): **no es criterio de aceptación de ninguna fase**; usar el verificador de 3 claves de §4.1.
- **Prohibido el falso verde:** cada fase declara su criterio binario y el comando exacto que lo produce. El output se lee, no se asume.

---

## 5. Fases

### F0 — Contrato del catálogo (backend, puro, sin IO)

**Objetivo.** Crear el tipo de dato de una acción DevOps y el catálogo semilla, sin ningún consumidor todavía. **Valor:** a partir de acá "qué se puede hacer en DevOps" es un dato inspeccionable, no una arqueología de JSX.

**Archivos a crear**
- `backend/services/devops_action_catalog.py`
- `backend/tests/test_devops_action_catalog.py`

**Archivos a editar (las 7 patas de la flag 1)**
- `backend/config.py`
- `backend/services/harness_flags.py`
- `backend/services/harness_flags_help.py`
- `backend/tests/test_harness_flags.py`
- `backend/scripts/run_harness_tests.sh`
- `backend/scripts/run_harness_tests.ps1`

**Contenido exacto de `backend/services/devops_action_catalog.py`**

```python
"""Plan 267 F0 — Catalogo unico de acciones DevOps.

PURO: sin flask, sin config, sin IO, sin red. Solo dataclasses + datos + lookups.
Es la fuente de VERDAD de la identidad y la seguridad de una accion; el COMO se
ejecuta vive en el binding del frontend (services/devopsActionBindings.ts), que
reusa los endpoints que ya existen. El ratchet de F8 exige igualdad de conjuntos.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CATALOG_VERSION = "1"

EFFECTS = ("read", "write")
IMPACTS = ("none", "low", "high")
PARAM_TYPES = ("string", "int", "bool", "enum")
# v2 [C5] — desde donde puede DISPARARSE una accion (ver §4.10). Invariante
# I-REACH, verificada por el ratchet de F8: effect == "write" => "palette-run"
# NO puede estar en reach. El doble cerrojo de entityActions.ts:44-46, elevado
# a dato y cubriendo las TRES superficies en vez de una.
REACHES = ("button", "palette-run", "palette-nav", "assistant")

# Master del panel DevOps (api/devops.py:39). Si esta en False, el panel no
# existe para el operador y ninguna accion de seccion es alcanzable [C6].
MASTER_HEALTH_KEY = "flag_enabled"

# Espejo CONGELADO de los ids de DEVOPS_SECTIONS (frontend/src/pages/DevOpsPage.tsx:145,
# ids en :149..:320). El ratchet de F8 lo compara contra el archivo .tsx real: si el
# frontend agrega o renombra una seccion y no se actualiza aca, el test sale ROJO.
DEVOPS_SECTION_IDS = (
    "resumen", "pipelines", "publicaciones", "ambientes", "agente", "servidores",
    "variables", "remote-console", "pr-review", "despliegues", "taller-compilacion",
    "publicador-soluciones", "inventario-pipelines", "pipeline-audit",
    "editar-pipeline", "matriz-entornos", "paquete-entrega",
)


@dataclass(frozen=True)
class ActionParam:
    name: str                       # snake_case, unico dentro de la accion
    type: str                       # uno de PARAM_TYPES
    label: str                      # español, para la UI
    required: bool = False
    enum_values: tuple[str, ...] = ()   # obligatorio y no vacio si type == "enum"
    default: str = ""               # "" = sin default


@dataclass(frozen=True)
class DevOpsAction:
    id: str                         # "devops.<dominio>.<verbo>", unico
    label: str                      # español, imperativo corto ("Disparar pipeline")
    summary: str                    # 1 frase: que hace, para la tarjeta de preview
    section_id: str | None          # id de DEVOPS_SECTION_IDS, o None si vive fuera del panel
    nav_path: str                   # deep-link donde el operador la ve manualmente
    effect: str                     # "read" | "write"
    impact: str                     # "none" | "low" | "high"
    targets_environment: bool       # True si actua sobre un entorno concreto del operador
    health_key: str                 # key de api/devops.py::_health_payload(), "" = siempre visible
    flag_key: str                   # key de la FlagSpec que la gatea, "" = ninguna
    reach: tuple[str, ...]          # v2 [C5] — subconjunto NO VACIO de REACHES, ver §4.10
    params: tuple[ActionParam, ...] = ()
    phrases: tuple[str, ...] = ()   # frases de intencion en español (matcher determinista)


def get_action(action_id: str) -> DevOpsAction | None:
    """None si no existe. NUNCA lanza."""
    return _INDEX.get((action_id or "").strip())


def visible_actions(health: dict | None) -> list[DevOpsAction]:
    """Acciones alcanzables segun el health del panel. NUNCA lanza.

    Reglas, en este orden:
      1. health_key == ""  => SIEMPRE visible (no depende del panel: son las que
         viven fuera de /devops, como /logs y /incidencias).
      2. resto             => visible solo si el MASTER del panel esta ON
         (health[MASTER_HEALTH_KEY] is True) Y su propio health_key esta ON.

    La regla 2 es el fix de C6: sin ella, con STACKY_DEVOPS_PANEL_ENABLED apagado
    el catalogo seguia ofreciendo ~21 acciones cuyo nav_path (/devops/<seccion>)
    no lleva a ningun lado.
    """
    h = health or {}
    master_on = h.get(MASTER_HEALTH_KEY) is True
    out = []
    for a in DEVOPS_ACTION_CATALOG:
        if not a.health_key:
            out.append(a)
        elif master_on and h.get(a.health_key) is True:
            out.append(a)
    return out


def palette_actions(health: dict | None) -> list[DevOpsAction]:
    """Lo que la paleta global puede OFRECER: reach contiene palette-run o
    palette-nav. Quien decide si ejecuta o navega es el propio reach [C5]."""
    return [a for a in visible_actions(health)
            if "palette-run" in a.reach or "palette-nav" in a.reach]


def assistant_actions(health: dict | None) -> list[DevOpsAction]:
    """Lo que el matcher de F2 tiene permitido proponer. Es el UNICO universo que
    recibe match_intent(): una accion sin 'assistant' en reach jamas se propone."""
    return [a for a in visible_actions(health) if "assistant" in a.reach]


def param_of(action: DevOpsAction, name: str) -> ActionParam | None:
    for p in action.params:
        if p.name == name:
            return p
    return None


def action_to_dict(a: DevOpsAction) -> dict:
    return {
        "id": a.id, "label": a.label, "summary": a.summary,
        "section_id": a.section_id, "nav_path": a.nav_path,
        "effect": a.effect, "impact": a.impact,
        "targets_environment": a.targets_environment,
        "health_key": a.health_key, "flag_key": a.flag_key,
        "reach": list(a.reach),
        "params": [
            {"name": p.name, "type": p.type, "label": p.label,
             "required": p.required, "enum_values": list(p.enum_values),
             "default": p.default}
            for p in a.params
        ],
        "phrases": list(a.phrases),
    }


def catalog_payload(health: dict | None) -> dict:
    acts = visible_actions(health)
    return {
        "ok": True,
        "version": CATALOG_VERSION,
        "count": len(acts),
        "actions": [action_to_dict(a) for a in acts],
    }
```

**Catálogo semilla (23 acciones).** Se declara `DEVOPS_ACTION_CATALOG: tuple[DevOpsAction, ...]` con exactamente estas entradas. `PRJ = ActionParam(name="project", type="string", label="Proyecto", required=True)` se reusa; `ENV = ActionParam(name="environment", type="enum", label="Entorno", required=True, enum_values=("dev","qa","uat","prod"))`.

| # | `id` | `section_id` | `nav_path` | `effect` | `impact` | `targets_environment` | `health_key` | params extra |
|---|------|--------------|-----------|----------|----------|------------------------|--------------|--------------|
| 1 | `devops.overview.refresh` | `resumen` | `/devops/resumen` | read | none | false | `cockpit_enabled` | — |
| 2 | `devops.servers.list` | `servidores` | `/devops/servidores` | read | none | false | `servers_enabled` | — |
| 3 | `devops.servers.doctor` | `servidores` | `/devops/servidores` | read | none | false | `connection_doctor_enabled` | `server_alias` (string) |
| 4 | `devops.environments.list` | `ambientes` | `/devops/ambientes` | read | none | false | `environments_enabled` | — |
| 5 | `devops.variables.list` | `variables` | `/devops/variables` | read | none | false | `variables_enabled` | — |
| 6 | `devops.pipelines.inventory` | `inventario-pipelines` | `/devops/inventario-pipelines` | read | none | false | `pipeline_inventory_enabled` | — |
| 7 | `devops.pipelines.audit` | `pipeline-audit` | `/devops/pipeline-audit` | read | none | false | `pipeline_audit_enabled` | — |
| 8 | `devops.pipelines.env_matrix` | `matriz-entornos` | `/devops/matriz-entornos` | read | none | false | `env_matrix_enabled` | — |
| 9 | `devops.pipeline_edit.preview` | `editar-pipeline` | `/devops/editar-pipeline` | read | none | false | `pipeline_nl_edit_enabled` | `instruction` (string, required) |
| 10 | `devops.deployments.history` | `despliegues` | `/devops/despliegues` | read | none | false | `deployments_enabled` | — |
| 11 | `devops.publications.list` | `publicaciones` | `/devops/publicaciones` | read | none | false | `publications_enabled` | — |
| 12 | `devops.pr.list` | `pr-review` | `/devops/pr-review` | read | none | false | `pr_reviewer_enabled` | — |
| 13 | `devops.build.status` | `taller-compilacion` | `/devops/taller-compilacion` | read | none | false | `build_workshop_enabled` | — |
| 14 | `devops.handoff.preview` | `paquete-entrega` | `/devops/paquete-entrega` | read | none | false | `handoff_bundle_enabled` | — |
| 15 | `devops.logs.tail` | `None` **(el valor Python `None`, no la cadena `"None"`)** | `/logs` | read | none | false | `""` **(cadena vacía)** | `lines` (int, default `"200"`) |
| 16 | `devops.incidents.list` | `None` (valor Python) | `/incidencias` | read | none | false | `""` (cadena vacía) | — |
| 17 | `devops.pipeline.trigger` | `pipelines` | `/devops/pipelines` | **write** | **high** | **true** | `trigger_enabled` | `ENV`, `pipeline_id` (string, required) |
| 18 | `devops.deployment.execute` | `despliegues` | `/devops/despliegues` | **write** | **high** | **true** | `deployments_execute_enabled` | `ENV`, `deployment_id` (string, required) |
| 19 | `devops.publication.run` | `publicaciones` | `/devops/publicaciones` | **write** | **high** | **true** | `one_click_publish_enabled` | `ENV`, `publication_id` (string, required) |
| 20 | `devops.solution.publish` | `publicador-soluciones` | `/devops/publicador-soluciones` | **write** | **high** | **true** | `solution_publisher_enabled` | `ENV`, `solution_path` (string, required) |
| 21 | `devops.remote_console.run` | `remote-console` | `/devops/remote-console` | **write** | **high** | **true** | `remote_console_enabled` | `ENV`, `server_alias` (string, required), `command` (string, required) |
| 22 | `devops.pipeline_edit.commit` | `editar-pipeline` | `/devops/editar-pipeline` | **write** | **high** | false | `pipeline_nl_edit_commit_enabled` | `branch` (string, required) |
| 23 | `devops.build.run` | `taller-compilacion` | `/devops/taller-compilacion` | **write** | **low** | false | `build_workshop_enabled` | `solution_path` (string, required) |

Todas llevan `PRJ` como primer param.

**`reach` (v2, §4.10).** Las **16 de `effect:read`** (filas 1-16) llevan `reach=("button","palette-run","assistant")`. Las **7 de `effect:write`** (filas 17-23) llevan `reach=("button","palette-nav","assistant")` — la paleta las **ofrece** y **navega**, nunca las ejecuta (invariante I-REACH). Ninguna otra combinación está permitida en la semilla.

**`flag_key`.** Es la flag YA EXISTENTE que produce ese `health_key`. **Verificado el 2026-07-27: las 21 `health_key` de esta tabla existen en `api/devops.py::_health_payload()` y las 16 flags correspondientes existen en `harness_flags.py` y en `config.py`** (no hay ninguna inventada). El mapeo es 1:1 con el `getattr` de `_health_payload()`; los pares no obvios son: `cockpit_enabled`⇒`STACKY_DEVOPS_COCKPIT_ENABLED` (`:74`), `trigger_enabled`⇒`STACKY_PIPELINE_TRIGGER_ENABLED` (`:41`), `deployments_execute_enabled`⇒`STACKY_DEPLOYMENTS_EXECUTE_ENABLED` (`:68`), `one_click_publish_enabled`⇒`STACKY_DEVOPS_ONE_CLICK_PUBLISH_ENABLED` (`:59`), `env_matrix_enabled`⇒`STACKY_PIPELINE_ENV_MATRIX_ENABLED` (`:102`), `handoff_bundle_enabled`⇒`STACKY_PIPELINE_HANDOFF_BUNDLE_ENABLED` (`:105`), `pipeline_nl_edit_commit_enabled`⇒`STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` (`:99`). Las dos de `health_key=""` llevan `flag_key=""`.

> **Deuda conocida, declarada y NO resuelta acá [C16]:** `devops.build.status` (read) y `devops.build.run` (write, `impact:low`) comparten `flag_key=STACKY_DEVOPS_BUILD_WORKSHOP_ENABLED`. Eso viola el principio §4.4 ("partir la flag cuando mezcla lo inocuo con lo que escribe"), pero **la flag es preexistente del plan 201** y partirla es scope de otro plan. Se declara para que no quede mudo; el `reach` de `devops.build.run` (sin `palette-run`) y `needs_confirmation` cubren el riesgo operativo.

**`phrases` — LAS 23 LISTAS, LITERALES [C3].** El v1 declaraba 4 de 23 y decía "mínimo 3 por acción" para el resto; los tests 3/5/6 de F2 afirman **quién gana el ranking**, y el ganador depende de las listas que faltaban. Un modelo menor inventándolas volvía el criterio no determinable. Van todas, en español rioplatense, minúscula y sin acentos (el matcher normaliza igual, pero así el dato es legible y diffeable):

```python
# id -> phrases   (copiar TAL CUAL; no agregar, no reordenar, no traducir)
"devops.overview.refresh":     ("resumen de devops", "estado general", "como esta todo")
"devops.servers.list":         ("listar servidores", "que servidores hay", "ver los servidores")
"devops.servers.doctor":       ("estado de los servidores", "chequear conexion", "diagnosticar el servidor", "esta caido el servidor")
"devops.environments.list":    ("listar ambientes", "que ambientes hay", "ver los ambientes")
"devops.variables.list":       ("listar variables", "ver las variables", "que variables hay")
"devops.pipelines.inventory":  ("inventario de pipelines", "que pipelines hay", "listar pipelines")
"devops.pipelines.audit":      ("auditar pipelines", "revisar las pipelines", "auditoria de pipelines")
"devops.pipelines.env_matrix": ("matriz de entornos", "comparar entornos", "diferencias entre entornos")
"devops.pipeline_edit.preview":("previsualizar el cambio de pipeline", "ver el diff de la pipeline", "simular la edicion de pipeline")
"devops.deployments.history":  ("historial de despliegues", "ultimos despliegues", "que se desplego")
"devops.publications.list":    ("listar publicaciones", "ver las publicaciones", "que publicaciones hay")
"devops.pr.list":              ("listar pull requests", "ver los pull requests", "que pull requests hay")
"devops.build.status":         ("estado de la compilacion", "como viene el build", "ver la compilacion")
"devops.handoff.preview":      ("previsualizar el paquete de entrega", "ver el paquete de entrega", "armar entrega")
"devops.logs.tail":            ("ver los logs", "revisar logs", "mostrame el log", "ultimas lineas del log")
"devops.incidents.list":       ("listar incidencias", "ver las incidencias", "que incidencias hay")
"devops.pipeline.trigger":     ("disparar la pipeline", "correr la pipeline", "ejecutar la pipeline", "lanzar la pipeline")
"devops.deployment.execute":   ("ejecutar el despliegue", "hacer el despliegue", "desplegar ahora")
"devops.publication.run":      ("correr la publicacion", "ejecutar la publicacion", "publicar ahora")
"devops.solution.publish":     ("publicar la solucion", "compilar y publicar la solucion", "generar la publicacion de la solucion")
"devops.remote_console.run":   ("correr un comando remoto", "ejecutar en el servidor", "comando en la consola remota")
"devops.pipeline_edit.commit": ("commitear la pipeline editada", "guardar el cambio de pipeline en el repositorio", "subir el cambio de pipeline")
"devops.build.run":            ("compilar la solucion", "correr la compilacion", "buildear el proyecto")
```

**Por qué estas y no otras (regla de diseño, para quien agregue la 24.ª):** ninguna frase de lectura puede ser prefijo/subconjunto de tokens de contenido de una frase de escritura. Contraejemplo prohibido: `devops.deployments.history` NO puede llevar `"desplegar"` (chocaría con `devops.deployment.execute`), por eso lleva `"historial de despliegues"`. El test 6 de F8 (`test_phrases_no_colisionan_entre_read_y_write`) lo verifica automáticamente.

**Flag 1 — `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (default ON)**

- `backend/config.py`, junto a las demás flags DevOps. **Usar el patrón REAL de los vecinos, verificado en `:1540-1542`** (el v1 escribía `.lower() in ("1","true","yes")`, que no es el patrón de este archivo) [C15]:
  ```python
  # Plan 267 — Catalogo unico de acciones DevOps. Default ON (solo LISTA lo que
  # ya existe: no escribe, no llama a ningun modelo, no corre en reposo).
  STACKY_DEVOPS_ACTION_CATALOG_ENABLED: bool = os.getenv(
      "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", "true"
  ).strip().lower() == "true"
  ```
- `backend/services/harness_flags.py`, `FlagSpec` nueva en el bloque DevOps:
  ```python
  FlagSpec(
      key="STACKY_DEVOPS_ACTION_CATALOG_ENABLED",
      type="bool",
      default=True,   # default ON: NINGUNA excepcion aplica. Solo LISTA lo que ya
                      # existe; no escribe en ningun lado, no llama a ningun modelo,
                      # no corre en reposo (se sirve a pedido de la pantalla) y no le
                      # saca ninguna decision al operador.
                      # Curada en _CURATED_DEFAULTS_ON (tests/test_harness_flags.py:467).
      label="Catalogo de acciones DevOps",
      description=(
          "Plan 267 - declara en un solo lugar que se puede hacer en el panel DevOps "
          "(que accion, en que seccion, si lee o escribe, que impacto, sobre que "
          "entorno). Lo consumen los botones, la paleta de comandos y el asistente. "
          "OFF: /api/devops/actions/catalog devuelve 404 y las tres superficies "
          "quedan como hoy."
      ),
      group="global",
      env_only=False,  # editable por UI (regla dura operator-config-always-via-ui)
  ),
  ```
  **SIN `requires=`** — es el master de la estrella (regla R4, §4.1).
- `_CATEGORY_KEYS["devops"]` (`harness_flags.py:223`): agregar `"STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`.
- `PLAIN_HELP` (`harness_flags_help.py:25`):
  ```python
  "STACKY_DEVOPS_ACTION_CATALOG_ENABLED": PlainHelp(
      what="Arma una lista unica de todo lo que se puede hacer en el panel de DevOps, para que los botones, el buscador de comandos y el asistente ofrezcan siempre lo mismo.",
      on_effect="Si la activas: la misma accion aparece con el mismo nombre y la misma advertencia en todos lados.",
      off_effect="Si la apagas: cada pantalla vuelve a ofrecer su propia lista, y el buscador de comandos deja de ofrecer acciones.",
      example="Es como el menu unico de un restaurante: la carta de la mesa, la del mostrador y la del delivery dicen exactamente lo mismo.",
  ),
  ```
  (verificado contra la denylist de `test_harness_flags_help.py:17-20`: no usa ninguna de las 15 palabras prohibidas, no cita keys ni fases).
- `_CURATED_DEFAULTS_ON` (`tests/test_harness_flags.py:467`): agregar `"STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`.
- **Registro del test nuevo, con la sintaxis de cada runner [C1]:**
  - en `backend/scripts/run_harness_tests.sh` (array `HARNESS_TEST_FILES=(` en `:20`), una línea **desnuda**: `  tests/test_devops_action_catalog.py`
  - en `backend/scripts/run_harness_tests.ps1` (array `$HarnessTestFiles = @(` en `:13`), una línea **entrecomillada y con coma**: `  "tests/test_devops_action_catalog.py",`

**Tests PRIMERO — `backend/tests/test_devops_action_catalog.py`**

1. `test_catalog_no_vacio_y_al_menos_23` — `len(DEVOPS_ACTION_CATALOG) >= 23`.
2. `test_ids_unicos` — `len({a.id for a in ...}) == len(DEVOPS_ACTION_CATALOG)`.
3. `test_ids_con_prefijo_devops` — todo `a.id.startswith("devops.")` y tiene exactamente 2 puntos.
4. `test_effect_e_impact_en_vocabulario` — `a.effect in EFFECTS and a.impact in IMPACTS`.
5. `test_section_id_conocida_o_none` — `a.section_id is None or a.section_id in DEVOPS_SECTION_IDS`.
6. `test_nav_path_arranca_con_slash` — `a.nav_path.startswith("/")`.
7. `test_todas_declaran_project` — `param_of(a, "project") is not None` para toda acción.
8. `test_params_nombres_unicos_por_accion`.
9. `test_enum_declara_valores` — `p.type != "enum" or len(p.enum_values) > 0`.
10. `test_phrases_minimo_tres` — `len(a.phrases) >= 3` para toda acción.
11. `test_get_action_desconocida_devuelve_none` — `get_action("nope") is None`, `get_action("") is None`, `get_action(None) is None` (no lanza).
12. `test_visible_actions_filtra_por_health` — con `health={"flag_enabled": True, "servers_enabled": True}` aparecen `devops.servers.list` y las 2 de `health_key==""`, y NO aparece `devops.pipeline.trigger`.
13. `test_visible_actions_health_none` — `visible_actions(None)` devuelve solo las de `health_key==""` (2 acciones) y no lanza.
14. `test_catalog_payload_serializa` — `json.dumps(catalog_payload({...}))` no lanza y `payload["version"] == "1"`.
15. `test_modulo_no_importa_flask_ni_config` — leer el propio `.py` como texto y afirmar que no contiene `"import flask"`, `"from flask"` ni `"import config"`.
16. **`test_master_apagado_deja_solo_las_de_afuera` [C6]** — con `health={"flag_enabled": False, "servers_enabled": True, "trigger_enabled": True}`, `visible_actions(health)` devuelve **exactamente 2** acciones (`devops.logs.tail` y `devops.incidents.list`). Sin este test, apagar el panel dejaba 21 acciones ofrecidas y navegables a ninguna parte.
17. **`test_reach_no_vacio_y_en_vocabulario`** — para toda acción, `a.reach` no está vacío y `set(a.reach) <= set(REACHES)`.
18. **`test_todas_alcanzan_el_boton`** — `"button" in a.reach` para las 23 (el botón manual nunca se pierde; §4.3).
19. **`test_write_nunca_es_palette_run` (I-REACH)** — `effect=="write"` ⇒ `"palette-run" not in a.reach`. El mensaje de fallo **nombra los ids ofensores**.
20. **`test_palette_actions_excluye_ejecucion_de_escritura`** — con todo el health en `True`, `palette_actions(health)` contiene las 7 de escritura (se ofrecen) y `[a for a in palette_actions(health) if "palette-run" in a.reach]` tiene **0** con `effect=="write"`.
21. **`test_assistant_actions_es_el_universo_del_matcher`** — `assistant_actions(health)` con todo ON devuelve las 23; ninguna acción queda fuera del asistente por accidente.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_catalog.py -v`
**Aceptación binaria:** **21 passed**, 0 failed. Además `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -v` (**56 passed** — medido hoy: 56; verificado que este archivo **no tiene ningún `parametrize` sobre `FLAG_REGISTRY`**, así que agregar flags no cambia el número) y `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_ratchet_meta.py -v` (**4 passed** — medido hoy: 4).

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` — **default ON**.
**Runtimes:** Codex / Claude Code / Copilot — **idéntico**; el módulo es datos puros, no ejecuta nada. Sin fallback necesario.
**Trabajo del operador: ninguno.**

---

### F1 — Endpoint del catálogo y health key

**Objetivo.** Servir el catálogo por HTTP para que el frontend lo consuma en vez de duplicarlo. **Valor:** el frontend no reescribe metadatos de seguridad.

**Archivos a crear**
- `backend/api/devops_actions.py`
- `backend/tests/test_devops_actions_api.py`

**Archivos a editar**
- `backend/api/__init__.py` — el import va **inmediatamente después de `from .devops_agent import ...` (`:54`)**; los vecinos verificados son `:53` `from .devops import bp as devops_bp` y `:54` `from .devops_agent import bp as devops_agent_bp` (el v1 citaba `:49`, que es `from .pipeline_editor`) [C15]. El `register_blueprint` va en el bloque que arranca en `:85` (el `api_bp = Blueprint(...)` está en `:84`).
- `backend/api/devops.py` — `_health_payload()` (`:28-108`): agregar antes del cierre de `:108`.

```python
# backend/api/devops_actions.py
"""api/devops_actions.py - Catalogo de acciones DevOps (Plan 267).

url_prefix="/devops/actions" -> rutas /api/devops/actions/... (NO poner /api/ en el
prefix; mismo gotcha C2 del plan 73, ver api/devops_agent.py:3-4).
"""
from flask import Blueprint, jsonify, request

import config as _config

bp = Blueprint("devops_actions", __name__, url_prefix="/devops/actions")


def _catalog_off() -> bool:
    return not getattr(_config.config, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)


@bp.get("/catalog")
def get_catalog():
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    from api.devops import _health_payload
    from services.devops_action_catalog import catalog_payload
    return jsonify(catalog_payload(_health_payload()))
```

En `_health_payload()` (`api/devops.py`, antes del `}` de `:108`):

```python
"action_catalog_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)
),  # Plan 267 - catalogo de acciones (solo lectura)
"action_nl_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_ACTION_NL_ENABLED", False)
),  # Plan 267 - lenguaje natural -> propuesta de accion
"agent_action_run_enabled": bool(
    getattr(cfg, "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", False)
),  # Plan 267 - ejecutar desde una propuesta lo que ESCRIBE (default OFF)
```

Las tres keys se agregan **en F1** aunque las flags 2 y 3 se declaren en F3 y F6: `getattr(..., False)` tolera el atributo ausente, y `test_bootstrap_health_matches_health_endpoint` compara `/health` contra `/bootstrap`, que comparten la misma función — no hay riesgo de divergencia. Registrar en `config.py` los tres atributos en F1 (con sus defaults finales) evita tres ediciones del mismo archivo.

**Tests (parte 1 de `test_devops_actions_api.py`)**
1. `test_catalog_flag_off_404` — con `monkeypatch.setattr(config.config, "STACKY_DEVOPS_ACTION_CATALOG_ENABLED", False)` ⇒ `GET /api/devops/actions/catalog` da **404** con `{"error":"devops_action_catalog_disabled"}`.
2. `test_catalog_flag_on_200_y_shape` — 200; `body["ok"] is True`; `body["version"] == "1"`; `isinstance(body["actions"], list)`; cada item tiene las **12** keys de `action_to_dict` (las 11 del v1 + `reach`).
3. `test_catalog_filtra_por_health` — **el v1 decía "con todas las flags DevOps en False" sin decir cómo, y `_health_payload()` lee ~35 atributos [C13]. El modo literal, que NO depende de enumerar flags:**
   ```python
   def test_catalog_filtra_por_health(client, monkeypatch):
       import api.devops_actions as mod
       monkeypatch.setattr(mod, "_health_payload_for_catalog",
                           lambda: {"flag_enabled": False}, raising=False)
       ...
   ```
   Para que eso sea posible, `api/devops_actions.py` **no llama a `api.devops._health_payload` directamente**: define `def _health_payload_for_catalog() -> dict:` que la envuelve (2 líneas), y **ese** es el seam que los tests parchean. Es el único cambio de estructura que este test impone, y evita monkeypatchear 35 atributos de `config.config`.
4. `test_health_expone_las_tres_keys_nuevas` — `GET /api/devops/health` incluye `action_catalog_enabled`, `action_nl_enabled`, `agent_action_run_enabled`.
5. `test_bootstrap_health_paridad` — `/bootstrap` y `/health` devuelven el mismo subconjunto de esas 3 keys.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v`
**Aceptación binaria:** los 5 tests de F1 en verde. Además `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops.py -v` sigue verde (paridad de `/health`).
**Registro [C1]:** `  tests/test_devops_actions_api.py` (desnuda) en `run_harness_tests.sh` `HARNESS_TEST_FILES` (`:20`) **y** `  "tests/test_devops_actions_api.py",` (entrecomillada, con coma) en `run_harness_tests.ps1` `$HarnessTestFiles` (`:13`).

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` — default ON.
**Runtimes:** idéntico en los 3; es un `GET` sin modelo.
**Trabajo del operador: ninguno.**

---

### F2 — Matcher de intención determinista (sin modelo)

**Objetivo.** Traducir una frase en español a una o más acciones candidatas **sin llamar a ningún modelo**. **Valor:** es la pata que da paridad real a Copilot y el fallback cuando el runtime no está disponible.

**Archivos a crear**
- `backend/services/devops_action_matcher.py`
- `backend/tests/test_devops_action_matcher.py`

```python
"""Plan 267 F2 — Matcher de intencion DETERMINISTA. Sin modelo, sin red, sin IO.

Es el piso de paridad: con GitHub Copilot (o sin runtime disponible) este matcher
es TODO el motor de intencion, y alcanza para proponer y previsualizar.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from services.devops_action_catalog import DevOpsAction

MIN_SCORE = 0.6          # por debajo => no hay match
AMBIGUITY_DELTA = 0.10   # si top1 - top2 < esto => needs_disambiguation
MAX_MATCHES = 3

_NON_WORD = re.compile(r"[^a-z0-9 ]+")   # v2: la ñ se fue en el paso NFD+Mn de
                                         # normalize_text (n + tilde combinante);
                                         # dejarla en la clase era regla muerta [C17]
_SPACES = re.compile(r"\s+")

# v2 [C2] — FIX BLOQUEANTE. Sin esto, "quiero disparar la piplain" puntuaba
# 2/3 = 0.667 >= MIN_SCORE contra la frase "disparar la pipeline", porque el
# articulo "la" contaba como token de contenido. El test 4 salia ROJO el dia 1.
# Las stopwords NO se borran del texto: se excluyen del DENOMINADOR y del
# numerador, para que el score mida solo palabras que significan algo.
_STOPWORDS = frozenset((
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "a", "en", "con", "por", "para", "sobre",
    "y", "o", "que", "se", "lo", "mi", "me", "te", "su",
    "quiero", "necesito", "podes", "puedo", "hace", "haceme", "dame",
    "mostrame", "decime", "porfa", "please",
))


def _content_tokens(text: str) -> list[str]:
    """Tokens que significan algo: no vacios y no stopwords. NUNCA lanza."""
    return [t for t in (text or "").split(" ") if t and t not in _STOPWORDS]


@dataclass(frozen=True)
class ActionMatch:
    action_id: str
    score: float          # 0.0 .. 1.0
    matched_phrase: str


def normalize_text(text: str | None) -> str:
    """minusculas + sin acentos + sin puntuacion + espacios colapsados. NUNCA lanza."""
    if not text:
        return ""
    s = unicodedata.normalize("NFD", str(text).lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = _NON_WORD.sub(" ", s)
    return _SPACES.sub(" ", s).strip()


def _phrase_score(norm_text: str, phrase: str) -> float:
    """Cobertura de tokens DE CONTENIDO de la frase presentes en el texto, mas un
    bonus por aparicion literal. Determinista y acotado a [0,1]. NUNCA lanza.

    v2 [C2]: los articulos y muletillas no cuentan ni arriba ni abajo. Con la
    frase "disparar la pipeline" los tokens de contenido son ("disparar",
    "pipeline"); "quiero disparar la piplain" da 1/2 = 0.5 < MIN_SCORE => NO
    matchea, que es lo que el test 4 siempre quiso afirmar.
    """
    norm_phrase = normalize_text(phrase)
    tokens = _content_tokens(norm_phrase)
    if not tokens:
        return 0.0
    text_tokens = set(_content_tokens(norm_text))
    hits = sum(1 for t in tokens if t in text_tokens)
    base = hits / len(tokens)
    if norm_phrase and norm_phrase in norm_text:
        base = min(1.0, base + 0.15)
    return round(base, 4)


def match_intent(text: str | None, actions: list[DevOpsAction]) -> list[ActionMatch]:
    """Devuelve hasta MAX_MATCHES matches con score >= MIN_SCORE, ordenados por
    score DESC y, ante empate exacto, por el ORDEN DEL CATALOGO (estable).
    Lista vacia = no entendi. NUNCA lanza."""
    norm = normalize_text(text)
    if not norm:
        return []
    scored: list[tuple[float, int, ActionMatch]] = []
    for idx, a in enumerate(actions or []):
        best, best_phrase = 0.0, ""
        for candidate in (*a.phrases, a.label):
            s = _phrase_score(norm, candidate)
            if s > best:
                best, best_phrase = s, candidate
        if best >= MIN_SCORE:
            scored.append((best, idx, ActionMatch(a.id, best, best_phrase)))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [m for _, _, m in scored[:MAX_MATCHES]]


def is_ambiguous(matches: list[ActionMatch]) -> bool:
    """True si hay >= 2 matches y la diferencia de score es menor a AMBIGUITY_DELTA."""
    if len(matches) < 2:
        return False
    return (matches[0].score - matches[1].score) < AMBIGUITY_DELTA
```

**Tests — `backend/tests/test_devops_action_matcher.py`**
Todos los casos corren contra `DEVOPS_ACTION_CATALOG` **completo** (las 23 acciones con sus 23 listas de `phrases` literales de F0), no contra un subconjunto: es la única forma de que el ranking sea el real.

1. `test_normalize_quita_acentos_y_puntuacion` — `normalize_text("¿Disparar la Pipeline?") == "disparar la pipeline"`.
2. `test_normalize_none_y_vacio` — `normalize_text(None) == ""`, `normalize_text("   ") == ""`.
3. `test_match_frase_exacta` — `"disparar la pipeline"` ⇒ `matches[0].action_id == "devops.pipeline.trigger"` con `score == 1.0`.
4. **`test_typo_no_matchea` [C2, era rojo el día 1]** — `"Quiero DISPARAR la píplain"` ⇒ `match_intent(...) == []`. Cálculo verificable a mano: tokens de contenido de `"disparar la pipeline"` = `("disparar","pipeline")`; el texto normalizado es `"quiero disparar la piplain"` cuyos tokens de contenido son `("disparar","piplain")` (`quiero` y `la` son stopwords) ⇒ `1/2 = 0.5 < MIN_SCORE (0.6)`. **Con el `_phrase_score` del v1 daba 0.667 y el test salía ROJO.**
5. `test_frase_con_ruido_si_matchea` — `"Quiero disparar la pipeline de QA"` ⇒ `matches[0].action_id == "devops.pipeline.trigger"` (los tokens de contenido de la frase están los 2, y además aparece literal ⇒ `1.0`).
6. `test_match_parcial_supera_umbral` — `"ver los logs"` ⇒ `matches[0].action_id == "devops.logs.tail"`.
7. `test_lectura_y_escritura_no_se_confunden` — `"historial de despliegues"` ⇒ `devops.deployments.history` (**no** `devops.deployment.execute`); `"hacer el despliegue"` ⇒ `devops.deployment.execute` (**no** el historial). Es el caso que la regla de diseño de `phrases` (F0) existe para garantizar.
8. `test_sin_match_devuelve_vacio` — `"receta de milanesas"` ⇒ `[]`.
9. `test_texto_vacio_devuelve_vacio` — `match_intent("", CAT) == []` y `match_intent(None, CAT) == []`.
10. `test_solo_stopwords_devuelve_vacio` — `"quiero que me des el la de"` ⇒ `[]` (sin tokens de contenido no hay match; verifica que la división `hits/len(tokens)` nunca divide por cero).
11. `test_orden_estable_ante_empate` — construir 2 acciones sintéticas con la misma frase y verificar que gana la de índice menor, **corriendo 5 veces con el mismo input y comparando la salida**.
12. `test_tope_de_tres_matches` — nunca devuelve más de 3.
13. `test_is_ambiguous_true_y_false` — dos matches con 0.90/0.85 ⇒ `True`; con 0.90/0.60 ⇒ `False`; con 1 match ⇒ `False`; con 0 ⇒ `False`.
14. `test_no_importa_flask_ni_red` — leer el `.py` y afirmar que no contiene `"requests"`, `"flask"` ni `"urllib"`.
15. `test_score_acotado` — para **cada una de las 23 acciones, con cada una de sus `phrases` y con cada `phrase` truncada a su primera palabra** (universo determinista, no "200 frases generadas" como decía el v1): `0.0 <= score <= 1.0`.

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_matcher.py -v`
**Aceptación binaria:** **15 passed**.
**Registro [C1]:** `  tests/test_devops_action_matcher.py` (desnuda) en `run_harness_tests.sh:20`; `  "tests/test_devops_action_matcher.py",` (entrecomillada, con coma) en `run_harness_tests.ps1:13`.

**Flag:** ninguna propia (es una función pura consumida por F3, gateada por `STACKY_DEVOPS_ACTION_NL_ENABLED`).
**Runtimes:** **idéntico en los 3** — no usa modelo. Ese es el punto de la fase.
**Trabajo del operador: ninguno.**

---

### F3 — `ActionProposal` + `POST /propose` + `POST /preview` (paridad 3 runtimes)

**Objetivo.** Que el agente devuelva una **acción tipada** en vez de prosa, con el molde de `IntentBrief`. **Valor:** cierra KPI-4 y KPI-5.

**Archivos a crear**
- `backend/services/devops_action_proposal.py`

**Archivos a editar**
- `backend/api/devops_actions.py` (agrega `/propose` y `/preview`)
- `backend/tests/test_devops_actions_api.py` (agrega los tests de F3)
- las 7 patas de la flag 2 (`config.py` ya la tiene desde F1; faltan `harness_flags.py` ×2, `harness_flags_help.py`, `test_harness_flags.py`, `test_harness_flags_requires.py`)

```python
"""Plan 267 F3 — Contrato de propuesta de accion.

Calca el molde de services/intent_preflight.py:39-47 (IntentBrief) a proposito:
mismos campos de intencion (open_questions, confidence, version) sobre un objeto
que ademas nombra la ACCION. NO se inventa un contrato nuevo.
"""
from __future__ import annotations

from dataclasses import dataclass

# v2 [C17]: el v1 importaba ademas get_action, ActionMatch, is_ambiguous y
# match_intent, y NO usaba ninguno. Este modulo solo arma la propuesta; el
# matching vive en el endpoint.
from services.devops_action_catalog import DevOpsAction, param_of

PROPOSAL_VERSION = "1"

_IMPACT_LABEL = {"none": "sin impacto", "low": "impacto bajo", "high": "impacto alto"}

BLOCKED_NONE = ""
BLOCKED_NO_MATCH = "no_match"
BLOCKED_AMBIGUOUS = "ambiguous"
BLOCKED_MISSING_PARAMS = "missing_params"
BLOCKED_FLAG_OFF = "flag_off"
BLOCKED_AGENT_WRITE_DISABLED = "agent_write_disabled"


@dataclass(frozen=True)
class ProposalParam:
    name: str
    value: str
    source: str   # "operator" | "default" | "missing"


@dataclass(frozen=True)
class ActionProposal:
    action_id: str
    label: str
    summary: str
    section_id: str | None
    nav_path: str
    effect: str
    impact: str
    targets_environment: bool
    environment: str            # "" si la accion no apunta a un entorno
    params: list[ProposalParam]
    what_will_happen: str       # 1 frase determinista en español
    open_questions: list[str]   # 1 por param required faltante
    alternatives: list[str]     # action_ids alternativos si hubo ambiguedad
    confidence: float           # score del matcher, 0.0 .. 1.0
    needs_confirmation: bool    # SIEMPRE True si effect == "write"
    blocked_reason: str         # una de las constantes BLOCKED_*
    version: str = PROPOSAL_VERSION


def describe(action: DevOpsAction, environment: str) -> str:
    """Frase determinista de 'que va a pasar'. Sin modelo. NUNCA lanza."""
    donde = f"sobre el entorno {environment}" if environment else "sobre el proyecto activo"
    efecto = ("Escribe en un sistema real del operador."
              if action.effect == "write"
              else "Solo lectura: no cambia nada.")
    return f"{action.label} {donde}. {_IMPACT_LABEL[action.impact]}. {efecto}"


def build_proposal(
    action: DevOpsAction,
    supplied: dict,
    confidence: float,
    alternatives: list[str],
    agent_write_enabled: bool,
) -> ActionProposal:
    """Arma la propuesta. NO ejecuta nada. NUNCA lanza."""
    params: list[ProposalParam] = []
    missing: list[str] = []
    for p in action.params:
        raw = (supplied or {}).get(p.name)
        if raw is not None and str(raw).strip():
            params.append(ProposalParam(p.name, str(raw).strip(), "operator"))
        elif p.default:
            params.append(ProposalParam(p.name, p.default, "default"))
        else:
            params.append(ProposalParam(p.name, "", "missing"))
            if p.required:
                missing.append(p.name)

    env = ""
    if action.targets_environment:
        for pp in params:
            if pp.name == "environment" and pp.value:
                env = pp.value
                break

    blocked = BLOCKED_NONE
    if action.effect == "write" and not agent_write_enabled:
        blocked = BLOCKED_AGENT_WRITE_DISABLED
    elif missing:
        blocked = BLOCKED_MISSING_PARAMS

    return ActionProposal(
        action_id=action.id, label=action.label, summary=action.summary,
        section_id=action.section_id, nav_path=action.nav_path,
        effect=action.effect, impact=action.impact,
        targets_environment=action.targets_environment, environment=env,
        params=params, what_will_happen=describe(action, env),
        open_questions=[
            f"¿Qué valor uso para «{(param_of(action, n).label if param_of(action, n) else n)}»?"
            for n in missing
        ],
        alternatives=alternatives, confidence=round(float(confidence), 4),
        needs_confirmation=(action.effect == "write"),
        blocked_reason=blocked,
    )


def proposal_to_dict(p: ActionProposal) -> dict: ...   # serializacion 1:1, listas planas
```

**Endpoints nuevos en `backend/api/devops_actions.py`**

```python
@bp.post("/propose")
def propose_action():
    """Frase en español -> ActionProposal tipada. DETERMINISTA: no llama a ningun
    modelo. Funciona identico en Codex CLI, Claude Code CLI y GitHub Copilot Pro:
    el runtime del body se ACEPTA y se ignora para el matching (a diferencia de
    api/devops_agent.py:69-78, que devuelve 400 para copilot)."""
    if _catalog_off():
        return jsonify({"error": "devops_action_catalog_disabled"}), 404
    if not getattr(_config.config, "STACKY_DEVOPS_ACTION_NL_ENABLED", False):
        return jsonify({"error": "devops_action_nl_disabled"}), 404
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "text es obligatorio"}), 400
    supplied = body.get("params") if isinstance(body.get("params"), dict) else {}

    from dataclasses import replace          # v2 [C7] — el v1 usaba replace()
                                             # sin importarlo: NameError seguro
                                             # en el camino ambiguo, y ningun
                                             # test lo cubria.
    from services.devops_action_catalog import assistant_actions, get_action
    from services.devops_action_matcher import is_ambiguous, match_intent
    from services import devops_action_proposal as dap

    health = _health_payload_for_catalog()   # seam parcheable, ver F1 test 3
    # v2 [C5]: el universo del matcher son las acciones con "assistant" en su
    # reach, no todas las visibles.
    actions = assistant_actions(health)
    matches = match_intent(text, actions)
    if not matches:
        return jsonify({"ok": True, "proposal": None,
                        "blocked_reason": dap.BLOCKED_NO_MATCH,
                        "suggestions": [a.label for a in actions[:5]]})

    agent_write = bool(getattr(_config.config,
                               "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", False))
    top = get_action(matches[0].action_id)
    alts = [m.action_id for m in matches[1:]] if is_ambiguous(matches) else []
    prop = dap.build_proposal(top, supplied, matches[0].score, alts, agent_write)
    if alts:
        prop = replace(prop, blocked_reason=dap.BLOCKED_AMBIGUOUS)
    return jsonify({"ok": True, "proposal": dap.proposal_to_dict(prop)})


@bp.post("/preview")
def preview_action():
    """action_id + params EXPLICITOS -> la misma ActionProposal, sin matching.
    Es lo que llama la tarjeta cuando el operador corrige un parametro.
    SOLO LECTURA: no ejecuta nada, jamas."""
    # mismos gates que /propose; 404 si el action_id no existe o no esta en
    # visible_actions(health) (una accion gateada NO se previsualiza).
```

**Flag 2 — `STACKY_DEVOPS_ACTION_NL_ENABLED` (default ON)**

- `config.py`: `os.getenv("STACKY_DEVOPS_ACTION_NL_ENABLED", "true")`.
- `FlagSpec`: `default=True`, `requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`, `group="global"`, `env_only=False`.
  Comentario obligatorio en la línea del `default`: *default ON — ninguna excepción aplica: solo INTERPRETA una frase que el operador acaba de escribir y devuelve una propuesta; no corre en reposo (no hay loop ni daemon: se dispara por request), no llama a ningún modelo (el matcher es determinista) y no escribe absolutamente nada. Curada en `_CURATED_DEFAULTS_ON`.*
- `_CATEGORY_KEYS["devops"]`, `PLAIN_HELP`, `_CURATED_DEFAULTS_ON` (`test_harness_flags.py:467`).
- **`_REQUIRES_MAP_FROZEN`** (`backend/tests/test_harness_flags_requires.py:120`): agregar `"STACKY_DEVOPS_ACTION_NL_ENABLED": "STACKY_DEVOPS_ACTION_CATALOG_ENABLED"`. El assert de `:316` es de **igualdad de mapas**: olvidarla es rojo, y agregarla sin `requires` también.

**Tests (parte 2 de `test_devops_actions_api.py`)**
6. `test_propose_nl_flag_off_404`.
7. `test_propose_sin_text_400`.
8. `test_propose_devuelve_accion_tipada` — `{"text":"quiero ver los logs","params":{"project":"Pacifico"}}` ⇒ `proposal["action_id"] == "devops.logs.tail"`, `effect == "read"`, `needs_confirmation is False`, `blocked_reason == ""`.
9. `test_propose_write_marca_needs_confirmation` — `"disparar la pipeline"` con todas las flags ON ⇒ `effect == "write"`, `impact == "high"`, `needs_confirmation is True`.
10. `test_propose_write_bloqueada_si_run_flag_off` — con `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED=False` ⇒ `blocked_reason == "agent_write_disabled"` y **la propuesta igual se devuelve** (el operador puede verla y navegar al panel).
11. `test_propose_param_faltante_genera_pregunta` — sin `environment` ⇒ `blocked_reason == "missing_params"` y `open_questions` tiene 1 entrada que nombra "Entorno".
12. `test_propose_sin_match_no_lanza` — `"receta de milanesas"` ⇒ 200, `proposal is None`, `blocked_reason == "no_match"`, `suggestions` no vacío.
13. **`test_propose_copilot_mismo_resultado_que_cli`** — llamar 3 veces con `runtime` `"codex_cli"`, `"claude_code_cli"` y `"copilot"` y el mismo `text`; los 3 devuelven **200** y **el mismo `proposal` byte a byte**. Este test es el que prueba KPI-5 y el que hace fallar cualquier regresión que reintroduzca el 400 de `devops_agent.py:69-78`.
14. `test_preview_action_id_desconocido_404`.
15. `test_preview_accion_gateada_404` — una acción cuyo `health_key` está en False no se previsualiza.
16. `test_preview_no_ejecuta_nada` — monkeypatchear los módulos de ejecución para que exploten si se los llama; el endpoint responde 200 sin tocarlos.
17. `test_what_will_happen_nombra_entorno_e_impacto` — la frase contiene el entorno declarado y una de las 3 etiquetas de impacto.
18. **`test_propose_ambiguo_devuelve_alternativas` [C7]** — dos acciones que empatan dentro de `AMBIGUITY_DELTA` ⇒ `blocked_reason == "ambiguous"`, `alternatives` no vacío y **200, no 500**. Es el único test que ejecuta la línea `replace(prop, ...)`; sin él, el `NameError` del v1 llegaba a producción con la suite en verde.
19. **`test_propose_respeta_reach_assistant`** — una acción cuyo `reach` no incluye `"assistant"` **nunca** sale propuesta, aunque su frase sea un match perfecto (se construye con una acción sintética inyectada en el universo del matcher).

**Comando:** `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v`
**Aceptación binaria:** **19 passed (5 de F1 + 14 de F3)**, 0 failed. Más: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -v` (**9 passed** — medido hoy: 9).

**`PLAIN_HELP` de la flag 2 — texto LITERAL [C10]** (el v1 no lo daba; verificado contra los 4 límites, el prefijo `"Si "`, las 15 palabras de la denylist, `_KEY_RE` y `_PHASE_RE`):
```python
"STACKY_DEVOPS_ACTION_NL_ENABLED": PlainHelp(
    what="Permite pedir una tarea de despliegue escribiendola en castellano, y que el asistente te muestre cual seria la accion antes de hacer nada.",
    on_effect="Si la activas: escribis lo que queres hacer y aparece una tarjeta con la accion, el ambiente, el riesgo y que va a pasar.",
    off_effect="Si la apagas: el asistente vuelve a responder solo con texto y tenes que buscar el boton vos mismo.",
    example="Escribis «quiero ver los logs» y te muestra la tarjeta de esa tarea, sin ejecutar nada hasta que confirmes.",
),
```

**Flag:** `STACKY_DEVOPS_ACTION_NL_ENABLED` — **default ON**.
**Runtimes:**
- **Codex CLI** — el matcher determinista responde; F6 puede además pedirle al runtime un enriquecimiento opcional.
- **Claude Code CLI** — idéntico.
- **GitHub Copilot Pro** — **idéntico y completo**: el camino no llama a ningún modelo. *Fallback explícito:* si en el futuro se agrega enriquecimiento por LLM y el runtime no está disponible, se captura `PreflightRuntimeUnavailable` (`intent_preflight.py:25-26`) y se devuelve la propuesta determinista con `confidence` sin modificar. **Nunca un error.**
**Trabajo del operador: ninguno.**

---

### F4 — Espejo tipado, bindings y `runDevOpsAction` (frontend puro)

**Objetivo.** Un único ejecutor de acciones en el frontend, con la confirmación derivada del catálogo. **Valor:** cierra KPI-6 y KPI-7; después de F4 ninguna superficie necesita saber cómo se confirma.

**Archivos a crear**
- `frontend/src/services/devopsActionTypes.ts`
- `frontend/src/services/devopsActionRunner.ts`
- `frontend/src/services/devopsActionBindings.ts`
- `frontend/src/services/devopsActionRunner.test.ts`
- `frontend/src/services/devopsActionBindings.test.ts`

```ts
// frontend/src/services/devopsActionTypes.ts
// Plan 267 F4 — Espejo TIPADO del catalogo backend. Sin React, sin DOM.
export type DevOpsActionEffect = 'read' | 'write';
export type DevOpsActionImpact = 'none' | 'low' | 'high';

export interface DevOpsActionParamMeta {
  name: string; type: 'string' | 'int' | 'bool' | 'enum'; label: string;
  required: boolean; enum_values: string[]; default: string;
}

export interface DevOpsActionMeta {
  id: string; label: string; summary: string;
  section_id: string | null; nav_path: string;
  effect: DevOpsActionEffect; impact: DevOpsActionImpact;
  targets_environment: boolean; health_key: string; flag_key: string;
  /** v2 [C5] — subconjunto de 'button'|'palette-run'|'palette-nav'|'assistant'. */
  reach: string[];
  params: DevOpsActionParamMeta[]; phrases: string[];
}
```

```ts
// frontend/src/services/devopsActionRunner.ts
// Plan 267 F4 — Ejecutor UNICO. La confirmacion se DERIVA del catalogo, no se
// escribe a mano. Reusa confirmGateway (services/confirmGateway.ts:10-21) tal cual.
import type { ConfirmFn, ConfirmRequest } from './confirmGateway';
import type { DevOpsActionMeta } from './devopsActionTypes';

export interface DevOpsActionReceipt {
  actionId: string; ok: boolean; summary: string; detail: string;
  navPath: string; startedAt: number; finishedAt: number;
  confirmed: boolean;   // false = el operador dijo que no, o no habia gateway
}

export interface DevOpsActionRunContext {
  askConfirm: ConfirmFn;
  navigate: (path: string) => void;
  now: () => number;                 // inyectable => testeable sin fake timers
  onReceipt?: (r: DevOpsActionReceipt) => void;
}

export interface DevOpsActionBinding {
  id: string;
  run: (params: Record<string, string>, ctx: DevOpsActionRunContext)
    => Promise<{ ok: boolean; summary: string; detail?: string }>;
}

const IMPACT_TEXT: Record<string, string> = {
  none: 'Sin impacto', low: 'Impacto bajo', high: 'Impacto alto',
};

/** null si effect === 'read': NO se molesta al operador para leer.
 *  tone 'danger' <=> impact 'high'. El mensaje SIEMPRE nombra los 4 datos que
 *  el operador pidio ver: accion, entorno, impacto y que va a pasar. */
export function confirmRequestFor(
  a: DevOpsActionMeta, params: Record<string, string>
): ConfirmRequest | null {
  if (a.effect === 'read') return null;
  const env = a.targets_environment ? (params.environment || 'sin entorno declarado') : '';
  const donde = env ? ` sobre el entorno ${env}` : '';
  return {
    title: a.label,
    message: `${a.summary}${donde}. ${IMPACT_TEXT[a.impact]}. Esta acción escribe en un sistema real y no se puede deshacer sola.`,
    confirmLabel: a.label,
    tone: a.impact === 'high' ? 'danger' : 'default',
  };
}

/** Faltan params required => lista de nombres. Vacia = se puede correr. */
export function missingRequired(
  a: DevOpsActionMeta, params: Record<string, string>
): string[] {
  return a.params
    .filter((p) => p.required && !String(params[p.name] ?? '').trim())
    .map((p) => p.name);
}

/** v2 [C20] — El v1 prometia por escrito al operador que «Ver en el panel te deja
 *  en la seccion CON LOS DATOS YA CARGADOS», y el unico mecanismo que tenia era
 *  ctx.navigate(a.nav_path), que va a /devops/<seccion> pelado. Era una promesa
 *  que el codigo no cumplia. Esto la cumple: query string determinista, claves
 *  ordenadas alfabeticamente (para que el test compare strings), valores vacios
 *  omitidos, y encodeURIComponent en clave y valor. */
export function navPathWithParams(
  a: DevOpsActionMeta, params: Record<string, string>
): string {
  const pairs = Object.keys(params ?? {})
    .sort()
    .filter((k) => String(params[k] ?? '').trim())
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]).trim())}`);
  return pairs.length ? `${a.nav_path}?${pairs.join('&')}` : a.nav_path;
}

/** v2 [C5] — la paleta puede EJECUTAR esta accion, o solo llevar a su seccion. */
export function paletteMode(a: DevOpsActionMeta): 'run' | 'nav' | 'hidden' {
  if (a.reach.includes('palette-run')) return 'run';
  if (a.reach.includes('palette-nav')) return 'nav';
  return 'hidden';
}

/** Ejecuta. NUNCA lanza: siempre devuelve un recibo.
 *  Orden EXACTO e inviolable:
 *    1. binding ausente        -> recibo ok:false, NO se ejecuta nada
 *    2. params required faltan -> recibo ok:false, NO se confirma ni se ejecuta
 *    3. confirmRequestFor != null -> askConfirm; si devuelve false -> recibo
 *       ok:false confirmed:false y el binding NO se llama
 *    4. binding.run(...)       -> recibo con su resultado
 *    5. si run() lanza         -> recibo ok:false con el mensaje del error */
export async function runDevOpsAction(
  action: DevOpsActionMeta,
  params: Record<string, string>,
  binding: DevOpsActionBinding | undefined,
  ctx: DevOpsActionRunContext
): Promise<DevOpsActionReceipt> { /* ... */ }
```

```ts
// frontend/src/services/devopsActionBindings.ts
// Plan 267 F4 — El COMO. Cada binding llama al MISMO endpoint que ya usa el boton
// manual de su seccion. PROHIBIDO agregar endpoints nuevos aca.
export const DEVOPS_ACTION_BINDINGS: Record<string, DevOpsActionBinding> = {
  'devops.overview.refresh': { id: 'devops.overview.refresh', run: async (p, ctx) => { ... } },
  // ... una entrada por cada uno de los 23 ids del catalogo
};
export function bindingFor(id: string): DevOpsActionBinding | undefined {
  return DEVOPS_ACTION_BINDINGS[id];
}
```

**Regla de implementación de los bindings (para no equivocarse):** cada binding llama a la función de `frontend/src/api/endpoints.ts` que **ya usa** el botón manual de esa sección. Si un id del catálogo no tiene endpoint propio porque su acción es "abrir la pantalla y filtrar" (caso de `devops.logs.tail` e `devops.incidents.list`), el binding hace `ctx.navigate(nav_path)` y devuelve `{ok:true, summary:"Abierto en <ruta>"}`. **Nunca** se inventa un endpoint.

**Tests — `frontend/src/services/devopsActionRunner.test.ts`** (11 casos)
1. `confirmRequestFor` con `effect:'read'` ⇒ `null`.
2. `confirmRequestFor` con `impact:'high'` ⇒ `tone === 'danger'`.
3. `confirmRequestFor` con `impact:'low'` ⇒ `tone === 'default'`.
4. el `message` contiene el entorno cuando `targets_environment` y `params.environment` está.
5. el `message` dice `'sin entorno declarado'` cuando `targets_environment` y falta el param.
6. `missingRequired` detecta faltantes y devuelve `[]` cuando están todos.
7. **`runDevOpsAction` con `askConfirm = denyByDefault` y `effect:'write'` NO llama al binding** (spy con 0 llamadas) y devuelve `confirmed:false, ok:false`.
8. `runDevOpsAction` con `effect:'read'` **no llama a `askConfirm`** (spy con 0 llamadas) y sí llama al binding.
9. `runDevOpsAction` con binding `undefined` devuelve `ok:false` y **no lanza**.
10. `runDevOpsAction` con un binding cuyo `run` lanza devuelve `ok:false` con el mensaje, **no propaga**.
11. `runDevOpsAction` con `missingRequired` no vacío ⇒ `ok:false`, `askConfirm` **no** se llama y el binding **no** se llama.
12. **`navPathWithParams` sin params ⇒ `nav_path` pelado**; con `{environment:'qa', project:'Pacifico'}` ⇒ `'/devops/despliegues?environment=qa&project=Pacifico'` (**orden alfabético exacto**, string comparado literal) [C20].
13. **`navPathWithParams` omite vacíos y espacios en blanco**, y **escapa** un valor con espacio y `&` (`'a b&c'` ⇒ `a%20b%26c`).
14. **`paletteMode`** ⇒ `'run'` con `reach:['button','palette-run','assistant']`; `'nav'` con `reach:['button','palette-nav','assistant']`; `'hidden'` con `reach:['button']`.

**Tests — `frontend/src/services/devopsActionBindings.test.ts`** (3 casos)
1. Toda clave del record cumple `/^devops\.[a-z_]+\.[a-z_]+$/`.
2. Para toda clave `k`, `DEVOPS_ACTION_BINDINGS[k].id === k` (no hay ids desalineados).
3. `bindingFor('no-existe')` devuelve `undefined` sin lanzar.

**Comando:** desde `frontend/`: `npx vitest run src/services/devopsActionRunner.test.ts` y `npx vitest run src/services/devopsActionBindings.test.ts` (**dos invocaciones separadas**, regla §4.2)
**Aceptación binaria:** **14 + 3 passed**. Más `npx tsc --noEmit` sin errores.

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (la UI solo carga el catálogo si `health.action_catalog_enabled === true`).
**Runtimes:** irrelevante — código de UI, no llama a ningún modelo. Idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F5 — Superficie 1: la paleta de comandos (el "mañana" del comentario)

**Objetivo.** Que la paleta ejecute acciones DevOps, no solo navegue. **Valor:** cierra KPI-2 y cumple, cinco planes después, la promesa escrita en `entityActions.ts:3-5`.

**Archivos a editar**
- `frontend/src/components/commandPaletteData.ts`
- `frontend/src/components/CommandPalette.tsx` (260 líneas)

**Archivos a crear**
- `frontend/src/components/__tests__/commandPaletteDevopsActions.test.ts`

Cambios exactos en `commandPaletteData.ts`:

1. Agregar `"devops-action"` al union `CommandKind` (`:10-19`) — **al final**, para no alterar el orden que otros módulos puedan asumir. `EntityKind` (`entityActions.ts:15`) usa `Extract<..., "execution"|"ticket">`, así que **no se ve afectado**.
2. Agregar la entrada `'devops-action': '⚡'` a `DEEP_ICONS` (`:91-97`).
3. Función nueva, pura — **con el doble cerrojo de §4.10 [C5]**:
   ```ts
   /** Plan 267 F5 v2 — Convierte el catalogo en Command[] para la paleta.
    *
    *  DOBLE CERROJO (§4.10, calcado de entityActions.ts:44-46, que ya resolvio
    *  esto para 2 entidades): una accion de ESCRITURA nunca queda a un
    *  fuzzy-match + Enter de distancia. `paletteMode(a)` decide:
    *    - 'run'    => el Command EJECUTA (via onRun). Solo effect 'read'.
    *    - 'nav'    => el Command NAVEGA a navPathWithParams(a, {}) y NO ejecuta.
    *                  El label lo dice: "Ir a <seccion> para <accion>".
    *    - 'hidden' => no entra a la paleta.
    *  La paleta jamas confirma sola, y jamas dispara una escritura. */
   export function devopsActionCommands(
     actions: DevOpsActionMeta[],
     onRun: (a: DevOpsActionMeta) => void,
     onNavigate: (path: string) => void
   ): Command[]
   ```
   `Command` resultante según el modo:
   - **`run`**: `id: \`devops-action-${a.id}\``, `kind:'devops-action'`, `icon:'⚡'`, `label: a.label`, `hint: a.summary`, `run: () => onRun(a)`.
   - **`nav`**: `id: \`devops-action-nav-${a.id}\``, `kind:'devops-action'`, `icon:'⚠️'`, `label: \`Ir a ${a.label}\``, `hint: \`Escribe · ${IMPACT_TEXT[a.impact]} · se hace desde el panel\``, `run: () => onNavigate(navPathWithParams(a, {}))`.
   - **`hidden`**: no se emite.

En `CommandPalette.tsx`: cargar el catálogo con un `GET /api/devops/actions/catalog` **una sola vez al abrir la paleta** (nunca en un intervalo), concatenar `devopsActionCommands(...)` después de `NAV_COMMANDS`, y cablear `onRun` a `runDevOpsAction` con el `askConfirm` real de la app y `onNavigate` al `navigate` de la app. Si el `GET` falla o devuelve 404, la paleta queda **exactamente como hoy** (solo navegación), sin banner ni error.

**Tests — `commandPaletteDevopsActions.test.ts`** (10 casos)
1. `devopsActionCommands([], noop, noop)` ⇒ `[]`.
2. Con 12 acciones de lectura ⇒ 12 comandos, todos con `kind === 'devops-action'`.
3. Todos los `id` empiezan con `devops-action-` y son únicos.
4. **Una acción `write` (`reach` sin `palette-run`) produce un comando de NAVEGACIÓN**: `icon === '⚠️'`, `label` empieza con `'Ir a '`, `hint` contiene `'se hace desde el panel'`.
5. **`run()` de esa acción `write` llama a `onNavigate` y NO llama a `onRun`** (dos spies: `onNavigate` 1 llamada, `onRun` **0** llamadas). Este es el test que materializa KPI-9 en la superficie de la paleta.
6. Una acción `read` produce `icon === '⚡'`, `hint === a.summary` y su `run()` llama a `onRun` (1) y no a `onNavigate` (0).
7. Una acción con `reach: ['button']` **no aparece** en la salida.
8. `fuzzyScore` (`commandPaletteData.ts:31-49`) sigue devolviendo lo mismo para 6 pares de entrada conocidos — **test de no-regresión de la función existente**.
9. **`test_command_palette_no_sondea` [C11]** — grep-gate propio sobre `frontend/src/components/CommandPalette.tsx` leído como texto: **0** ocurrencias de `setInterval(` y de `refetchInterval`. Motivo: `devopsPollingRatchet.test.ts` escanea **solo** `components/devops/` (`:21`), así que `CommandPalette.tsx` está **fuera de su alcance** y declararlo criterio de aceptación de F5 era un falso verde.
10. **`test_catalogo_se_pide_una_sola_vez`** — sobre el mismo texto: la cadena `'/api/devops/actions/catalog'` aparece **exactamente 1 vez** en el archivo.

**Comando:** desde `frontend/`: `npx vitest run src/components/__tests__/commandPaletteDevopsActions.test.ts` y, en **otra invocación**, `npx vitest run src/components/__tests__/commandPaletteData.test.ts`
**Aceptación binaria:** **10 passed** + los tests preexistentes de `commandPaletteData.test.ts` en verde (mismo número que antes del cambio: anotar el número ANTES de tocar nada y compararlo).

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED`. Con OFF, el `GET` da 404 y la paleta queda idéntica a hoy.
**Runtimes:** idéntico en los 3.
**Trabajo del operador: ninguno.**

---

### F6 — Superficie 2: la consola de acciones del agente (propuesta → confirmación → recibo)

**Objetivo.** Reemplazar la prosa del agente por una tarjeta que muestra **qué acción, sobre qué entorno, qué impacto y qué resultado**. **Valor:** es literalmente lo que pidió el operador.

**Archivos a crear**
- `frontend/src/components/devops/DevOpsActionProposalCard.tsx`
- `frontend/src/components/devops/DevOpsActionConsole.tsx`
- `frontend/src/components/devops/devopsActionConsoleModel.ts` (lógica pura)
- `frontend/src/components/devops/devopsActionConsoleModel.test.ts`

**Archivos a editar**
- `frontend/src/components/devops/DevOpsAgentSection.tsx` (228 líneas) — montar `DevOpsActionConsole` **encima** del chat existente, sin borrarlo.
- las 7 patas de la flag 3.

**REGLA DURA de los `.tsx` nuevos [C12].** `uiDebtRatchet.test.ts` (plan 138 F0) congela **por archivo** el conteo de `style={{` en `*.tsx` y de hex en `*.module.css`; un archivo **nuevo** no tiene entrada de baseline, así que su presupuesto es **CERO**, y regenerar el baseline está bloqueado por deuda ajena. Por lo tanto, en `DevOpsActionProposalCard.tsx` y `DevOpsActionConsole.tsx`:
- **cero** `style={{` — todo con CSS modules y variables de token (cero literales hex en el `.module.css`);
- **cero** `confirm(`, `alert(`, `prompt(` — el ratchet también los cuenta (`NATIVE_DIALOG_RE`, `uiDebtRatchet.test.ts:27`), y además `confirmGateway.ts:7-8` los prohíbe explícitamente;
- si hace falta un valor calculado en runtime (ancho de barra, etc.): `ref` + `useEffect` que setea `el.style.setProperty(...)`, nunca `style={{}}` en el JSX.

**Contrato visual de la tarjeta (obligatorio, en este orden vertical):**
1. **Qué acción** — `label` en el título + `summary` debajo.
2. **Sobre qué entorno** — chip con `environment` si `targets_environment`; si está vacío, chip rojo `"Falta declarar el entorno"`.
3. **Cuál es el impacto** — badge con el texto de `IMPACT_TEXT` y `tone` `danger` si `impact === 'high'`.
4. **Qué va a pasar** — `what_will_happen`, textual, del backend.
5. **Parámetros** — tabla `nombre / valor / origen`; los de `source:'missing'` son campos editables.
6. **Preguntas abiertas** — `open_questions`, una por línea, si las hay.
7. **Alternativas** — si `blocked_reason === 'ambiguous'`, botones para elegir entre `alternatives`.
8. **Acciones** — `[Ejecutar]` (deshabilitado si `blocked_reason !== ''`) + `[Ver en el panel]` (siempre habilitado, navega a **`navPathWithParams(meta, paramsActuales)`**, no a `nav_path` pelado — es lo que hace verdadera la frase obligatoria de más abajo) [C20].
9. **Recibo** — tras ejecutar: ✅/❌, `summary`, `detail`, y la duración `finishedAt - startedAt` en ms.

**Lógica pura en `devopsActionConsoleModel.ts`** (todo lo testeable sin DOM, por el gap RTL/jsdom):
```ts
export type ProposalBlock = '' | 'no_match' | 'ambiguous' | 'missing_params'
  | 'flag_off' | 'agent_write_disabled';

/** Texto EXACTO del botón principal según el bloqueo. Nunca vacío. */
export function primaryActionLabel(p: ProposalView): string;
/** true si el botón Ejecutar debe estar deshabilitado. */
export function isRunDisabled(p: ProposalView): boolean;
/** Mensaje que explica POR QUE no se puede ejecutar, y QUE hacer al respecto.
 *  Para 'agent_write_disabled' debe nombrar la ruta manual, no solo negar. */
export function blockedExplanation(p: ProposalView): string;
/** Chips a renderizar: siempre [accion, entorno, impacto] en ese orden. */
export function headerChips(p: ProposalView): { text: string; tone: 'ok'|'warn'|'bad'|'faint' }[];
/** Recibo -> línea legible. */
export function receiptLine(r: DevOpsActionReceipt): string;
```

Texto obligatorio para `agent_write_disabled` (no se negocia, porque es lo que evita que la flag OFF se sienta como una pared):
> «Esta acción escribe en un sistema real, y la ejecución desde el asistente está desactivada. Podés ejecutarla vos desde el panel: **Ver en el panel** te deja en la sección con los datos ya cargados.»

**Flag 3 — `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` (default OFF — categoría (B))**

- `config.py`: `os.getenv("STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED", "false")`.
- `FlagSpec`: **SIN `default=`** (regla dura de §4.1), `requires="STACKY_DEVOPS_ACTION_CATALOG_ENABLED"` (estrella, no cadena — R4), `group="global"`, `env_only=False`.
  Comentario obligatorio, en la línea de la flag:
  > **EXCEPCIÓN DURA (B)** — es la única ruta por la que una frase en lenguaje natural puede terminar **escribiendo en un sistema real del operador**: dispara pipelines (`devops.pipeline.trigger`), ejecuta despliegues (`devops.deployment.execute`), publica (`devops.publication.run`, `devops.solution.publish`), commitea al repo real (`devops.pipeline_edit.commit`, vía `ado_provider.commit_file`, `backend/services/ado_provider.py:146`) y corre comandos en un servidor remoto (`devops.remote_console.run`). Precedente exacto: `STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED` OFF (`harness_flags.py:3166-3187`) mientras su hermana de solo-lectura `STACKY_PIPELINE_NL_EDIT_ENABLED` está ON (`:3149-3165`). **Con esta flag OFF el sistema NO pierde capacidad**: las 16 acciones de solo lectura se ejecutan igual desde el asistente, y las 7 de escritura se muestran completas con su vista previa y un botón que lleva al panel a hacerlas a mano.
- `_CATEGORY_KEYS["devops"]` (`harness_flags.py:223`) y **`_REQUIRES_MAP_FROZEN`** (`test_harness_flags_requires.py:120`; el assert de igualdad de mapas está en `:316`). **NO** va en `_CURATED_DEFAULTS_ON` (es OFF y no declara `default`).
- **`PLAIN_HELP` de la flag 3 — texto LITERAL [C10]** (verificado contra los 4 límites, el prefijo `"Si "`, las 15 palabras de la denylist, `_KEY_RE` y `_PHASE_RE`):
  ```python
  "STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED": PlainHelp(
      what="Decide si el asistente puede llevar a cabo por si mismo las tareas que modifican tus servidores y repositorios, o si solo puede mostrartelas.",
      on_effect="Si la activas: despues de que confirmes, el asistente hace la tarea (desplegar, publicar, correr una orden en un servidor).",
      off_effect="Si la apagas: el asistente igual te muestra la tarjeta completa con todo lo que haria, y un boton que te lleva a la pantalla para hacerlo vos.",
      example="Le pedis «hace el despliegue en produccion»: apagada, te muestra que haria y te lleva a la pantalla; activada, lo hace despues de tu confirmacion.",
  ),
  ```

**Tests — `devopsActionConsoleModel.test.ts`** (9 casos)
1. `isRunDisabled` ⇒ `true` para los 5 `blocked_reason` no vacíos y `false` para `''`.
2. `primaryActionLabel` nunca devuelve `''`, para los 6 estados.
3. `blockedExplanation('agent_write_disabled')` contiene la frase `'Ver en el panel'`.
4. `blockedExplanation('missing_params')` nombra al menos un parámetro faltante.
5. `headerChips` devuelve **siempre 3 chips**, en el orden acción/entorno/impacto.
6. `headerChips` con `targets_environment:true` y `environment:''` ⇒ el chip 2 tiene `tone:'bad'`.
7. `headerChips` con `impact:'high'` ⇒ el chip 3 tiene `tone:'bad'`.
8. `receiptLine` de un recibo ok incluye `'✅'` y la duración en ms.
9. `receiptLine` de un recibo con `confirmed:false` dice explícitamente que fue cancelado por el operador.
10. **`test_ver_en_el_panel_lleva_los_datos` [C20]** — dado un `ProposalView` con `environment:'prod'` y `project:'Pacifico'`, la ruta del botón "Ver en el panel" es `'/devops/despliegues?environment=prod&project=Pacifico'`. Sin este test, la frase obligatoria de abajo es una promesa que el código no cumple.

**Comando:** desde `frontend/`: `npx vitest run src/components/devops/devopsActionConsoleModel.test.ts`; y backend, en invocaciones separadas: `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -v` y `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -v`, más el verificador de 3 claves de `PLAIN_HELP` de §4.1.
**Aceptación binaria:** **10 passed** en vitest; 56 passed y 9 passed en los dos de flags; el verificador de `PLAIN_HELP` imprime `OK`; `npx tsc --noEmit` limpio; `npx vitest run src/__tests__/uiDebtRatchet.test.ts` verde (los 2 `.tsx` nuevos suman **0** a la deuda) y `npx vitest run src/__tests__/devopsPollingRatchet.test.ts` verde (**este sí aplica en F6**: los componentes nuevos viven en `components/devops/`, que es el alcance real del ratchet — a diferencia de F5, ver C11).

**Flag:** `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` — **default OFF, categoría (B)** (razón y `archivo:línea` arriba).
**Runtimes:**
- **Codex CLI / Claude Code CLI** — la tarjeta se alimenta de `/propose` (determinista). Opcionalmente el chat existente de `devops_agent.py` sigue disponible sin cambios.
- **GitHub Copilot Pro** — **funciona completo**: catálogo, propuesta, vista previa, confirmación y ejecución de acciones de lectura. *Fallback explícito:* el chat legacy de `devops_agent.py` sigue devolviendo 400 para Copilot (no se toca, ver §8), pero la consola de acciones **no lo usa**, así que el operador de Copilot ya no queda sin camino.
**Trabajo del operador:** *opt-in (default ON)* para ver y previsualizar; para que el asistente **ejecute lo que escribe**, el operador prende una flag desde Configuración → Arnés → DevOps (un click, y es exactamente la decisión que no le queremos sacar).

---

### F7 — Recablear los botones manuales al mismo ejecutor

**Objetivo.** Que el botón de siempre y la acción del asistente sean **el mismo código**. **Valor:** cierra KPI-6; a partir de acá "coherente" deja de ser una opinión.

**Archivos a editar** (uno por vez, en este orden, verificando después de cada uno):
1. `frontend/src/components/devops/ServersSection.tsx`
2. `frontend/src/components/devops/BuildWorkshopSection.tsx`
3. `frontend/src/components/devops/PipelineBuilderSection.tsx`
4. `frontend/src/components/devops/ProductionFlow.tsx`
5. `frontend/src/components/devops/RemoteConsoleSection.tsx`
6. `frontend/src/components/devops/SolutionPublisherSection.tsx`

**Transformación exacta, idéntica en los 6** (ejemplo con `ServersSection.tsx`):

```diff
-const ok = await askConfirm({
-  title: 'Ejecutar en el servidor',
-  message: `Vas a correr esto en ${alias}.`,
-  confirmLabel: 'Ejecutar',
-  tone: 'danger',
-});
-if (!ok) return;
-await DevOpsServers.runCommand(alias, cmd);
+const receipt = await runDevOpsAction(
+  actionMeta('devops.remote_console.run'),
+  { project, environment: env, server_alias: alias, command: cmd },
+  bindingFor('devops.remote_console.run'),
+  { askConfirm, navigate, now: () => Date.now(), onReceipt: setLastReceipt },
+);
+if (!receipt.ok) return;
```

**Reglas duras del recableado:**
- **No se borra ningún botón.** El operador ve exactamente los mismos controles.
- **El texto de la confirmación cambia, y eso es lo que el plan viene a hacer [C4].** El v1 decía a la vez, en §4.7, que el panel quedaba "byte-idéntico ... con el mismo texto de confirmación", y acá, que "el texto cambia". Las dos no pueden ser ciertas; vale esta. Lo que **no** cambia: el mismo botón, el mismo efecto, la misma severidad y el mismo `tone`.
- **El `tone` no puede aflojarse**: si hoy una confirmación es `'danger'`, su acción debe declarar `impact:'high'` en el catálogo. **Verificación previa obligatoria, archivo por archivo**, antes de tocar nada: `grep -n "tone: 'danger'" frontend/src/components/devops/<Archivo>.tsx` y anotar a qué acción corresponde cada uno. Censo medido el 2026-07-27 de construcciones a mano (`grep -c "askConfirm({"`): `ServersSection` 2, `BuildWorkshopSection` 2, `PipelineBuilderSection` 4, `ProductionFlow` 2, `RemoteConsoleSection` 1, `SolutionPublisherSection` 5 = **16 en total**. Si al terminar F7 el catálogo no cubre las 16, falta una acción.
- Si una sección tiene una acción con efecto que **no** está en el catálogo, se agrega al catálogo en esta fase (F0 quedó con 23; F7 puede llegar a más) — **nunca** se deja fuera.
- Si un binding no puede reproducir exactamente el comportamiento del botón, **se detiene la fase y se reporta**; no se aproxima.

**Test — `frontend/src/__tests__/plan267Adoption.test.ts`** (patrón calcado de `plan175Adoption.test.ts`, que ya existe en `frontend/src/__tests__/`)
1. Los 6 archivos de la lista **importan** `runDevOpsAction` desde `../../services/devopsActionRunner`.
2. Ninguno de los 6 contiene la cadena `askConfirm({` (construcción de `ConfirmRequest` a mano). **Verificado: hoy los 6 SÍ la contienen (2/2/4/2/1/5), así que este test es rojo antes del recableado y verde después — no es un verde vacío.**
3. `frontend/src/services/devopsActionRunner.ts` es el **único** archivo de `src/` (excluyendo `*.test.ts` y `__tests__/`) que contiene la cadena **`export function confirmRequestFor`**. Se busca esa cadena literal, no `confirmRequestFor` a secas, para no cazar a los que la importan.

**Comando:** desde `frontend/`: `npx vitest run src/__tests__/plan267Adoption.test.ts` + `npx tsc --noEmit`
**Aceptación binaria:** 3 passed, `tsc` sin errores, y `npx vitest run src/__tests__/uiDebtRatchet.test.ts` sigue verde. (`undoConfirmRatchet.test.ts` también debe seguir verde, pero **es informativo**: cuenta `window.confirm(` y `[^.\w]confirm\(` y su propio encabezado aclara que `askConfirm(` **no** matchea ninguno de los dos, así que este plan no puede moverlo.)

**Flag:** `STACKY_DEVOPS_ACTION_CATALOG_ENABLED`. **Nota de degradación:** los bindings y `runDevOpsAction` funcionan con el catálogo **embebido en el frontend como fallback** si el `GET /catalog` falla o la flag está OFF, para que apagar la flag **nunca** rompa un botón que hoy funciona. El fallback embebido se genera copiando los metadatos de las acciones de las 6 secciones tocadas (no las 23) — se declara en `devopsActionBindings.ts` como `FALLBACK_META: Record<string, DevOpsActionMeta>` y un test verifica que sus 6+ entradas coinciden campo a campo con el catálogo backend.
**Runtimes:** irrelevante (UI). Idéntico en los 3.
**Trabajo del operador: ninguno.** Los mismos botones, en el mismo lugar, con el mismo efecto.

---

### F8 — Ratchet anti-deriva y cierre

**Objetivo.** Que **no pueda** nacer una acción DevOps fuera del catálogo. **Valor:** convierte la coherencia en un test, que es lo único que sobrevive a los próximos 20 planes.

**Archivos a crear**
- `backend/tests/test_devops_action_ratchet.py`
- `frontend/src/__tests__/devopsActionCatalogRatchet.test.ts`

**`backend/tests/test_devops_action_ratchet.py`** (reglas estructurales sobre el catálogo)
1. `test_write_declara_impacto` — toda acción con `effect=="write"` tiene `impact != "none"`.
2. `test_targets_environment_exige_param_environment` — si `targets_environment` es `True`, existe un `ActionParam` llamado `environment`, de `type=="enum"`, con `required=True` y `enum_values` no vacío.
3. `test_environment_implica_targets` — la recíproca: si hay un param `environment`, `targets_environment` debe ser `True`.
4. `test_read_no_tiene_impacto_alto` — `effect=="read"` ⇒ `impact == "none"`.
5. `test_write_tiene_flag_key` — toda acción `write` declara `flag_key != ""` (nada que escriba puede quedar sin flag).
6. `test_health_key_existe_en_health_payload` — todo `health_key != ""` es una key real de `api.devops._health_payload()`.
7. `test_flag_key_existe_en_el_registro` — todo `flag_key != ""` está en `{s.key for s in FLAG_REGISTRY}`.
8. `test_section_ids_espejan_el_tsx` — leer `frontend/src/pages/DevOpsPage.tsx` como TEXTO, extraer los ids con `re.findall(r"^\s*id: '([a-z0-9-]+)',", src, re.M)`, y afirmar `set(...) == set(DEVOPS_SECTION_IDS)`. **Esta es la guarda contra el drift más caro**: si alguien agrega una sección DevOps y no la declara acá, el test lo caza.
9. `test_nav_path_de_seccion_es_devops_slug` — si `section_id` no es `None`, `nav_path == f"/devops/{section_id}"`.
10. `test_ninguna_accion_escribe_sin_confirmacion_posible` — para toda `write`, `summary` no está vacío (la tarjeta lo necesita para explicar qué va a pasar).
11. **`test_write_no_es_ejecutable_desde_la_paleta` (I-REACH, KPI-9) [C5]** — para toda acción con `effect=="write"`, `"palette-run" not in a.reach`. El mensaje de fallo **lista los ids ofensores por nombre**. Es el ratchet que impide que un plan futuro reabra el agujero sin que nadie lo note.
12. **`test_phrases_no_colisionan_entre_read_y_write` [C3]** — para todo par (`r` de lectura, `w` de escritura), ninguna `phrase` de `r` tiene su conjunto de **tokens de contenido** (usando `_content_tokens` del matcher) contenido en el de alguna `phrase` de `w`, ni al revés. Es la regla de diseño de `phrases` de F0, hecha test: sin ella, agregar `"desplegar"` al historial de despliegues volvería ambiguo el ranking y nadie se enteraría hasta que el operador confirmara la acción equivocada.
13. **`test_reach_incluye_button_siempre`** — `"button" in a.reach` para las 23: ninguna acción puede volverse *solo* del asistente. Es el guardarraíl de "sin eliminar la posibilidad de hacerlo manualmente", verificado.

**`frontend/src/__tests__/devopsActionCatalogRatchet.test.ts`** (paridad backend↔frontend, leyendo el `.py` como texto — patrón calcado de `devopsPollingRatchet.test.ts:17-21`)
```ts
import { describe, it, expect } from 'vitest';
import fs from 'fs';
import path from 'path';
import { DEVOPS_ACTION_BINDINGS } from '../services/devopsActionBindings';

const CATALOG_PY = path.resolve(__dirname, '../../../backend/services/devops_action_catalog.py');

function catalogIds(): string[] {
  const src = fs.readFileSync(CATALOG_PY, 'utf8');
  return [...src.matchAll(/^\s*id="(devops\.[a-z_]+\.[a-z_]+)"/gm)].map((m) => m[1]);
}
```
1. `test_todo_id_del_catalogo_tiene_binding` — `catalogIds()` ⊆ `Object.keys(DEVOPS_ACTION_BINDINGS)`; el mensaje de fallo **lista los ids huérfanos por nombre**.
2. `test_todo_binding_tiene_id_en_el_catalogo` — la inclusión inversa; el mensaje lista los bindings fantasma.
3. `test_igualdad_exacta` — los dos conjuntos ordenados son iguales (KPI-7).
4. `test_el_archivo_de_catalogo_existe` — falla con un mensaje explícito si la ruta se rompió (protege contra un falso verde por regex que no matchea nada sobre un archivo movido: si el `.py` no existe, el test **no** puede pasar con listas vacías).
5. `test_hay_al_menos_23_ids` — protege contra el mismo falso verde: una regex que deja de matchear daría 2 listas vacías **iguales**, y `test_igualdad_exacta` pasaría sin decir nada.
6. **`test_paleta_ofrece_al_menos_12_lecturas` (KPI-2) [C8]** — parsear del mismo `.py` los bloques `id="..."` junto con su `effect="..."` y su `reach=(...)`, y afirmar que hay **≥12** con `effect="read"` y `"palette-run"` en `reach`. Mide el **catálogo real**, no una entrada sintética como hacía el v1.
7. **`test_ningun_write_tiene_palette_run` (KPI-9, espejo del test 11 del backend)** — el mismo invariante verificado desde el lado del frontend, para que borrar el test de Python no alcance para reabrir el agujero.

**Registro [C1]:** `  tests/test_devops_action_ratchet.py` (desnuda) en `run_harness_tests.sh:20` **y** `  "tests/test_devops_action_ratchet.py",` (entrecomillada, con coma) en `run_harness_tests.ps1:13`.

**Comandos:**
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v`
- desde `frontend/`: `npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts`
- `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_ratchet_meta.py -v`

**Aceptación binaria:** **13 passed (backend) + 7 passed (frontend) + 4 passed (meta-ratchet)**.

**Huella de regresión [C18].** Al cerrar F8, agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` la huella del modo de falla que este plan introduce y que no existía antes: *"el asistente propone una acción DevOps que nunca se puede ejecutar"* — síntoma: `blocked_reason` distinto de `""` de forma permanente; causas ordenadas por probabilidad: (1) `health_key` de la acción apagado o master `flag_enabled` en `False`; (2) `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` OFF (esperado, no es bug: la tarjeta lo explica); (3) `flag_key` que ya no existe en el registro (lo caza el test 7 de este mismo archivo). Sin la huella, el primer reporte de "propone y no hace nada" se investiga desde cero.

**Flag:** ninguna (son tests).
**Runtimes:** irrelevante.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Probabilidad | Mitigación (concreta) |
|---|--------|--------------|------------------------|
| R1 | El recableado de F7 cambia el comportamiento de un botón que hoy funciona | Media | F7 se hace **un archivo por vez**; regla dura "el `tone` no puede aflojarse"; `FALLBACK_META` embebido para que la flag OFF nunca rompa un botón; `plan267Adoption.test.ts` verifica la adopción y `tsc --noEmit` la compilación |
| R2 | El ratchet frontend da **falso verde** si la regex deja de matchear (archivo movido o formato cambiado) | Alta si no se previene | Tests 4 y 5 del ratchet: existencia del archivo + mínimo de 23 ids. Dos listas vacías iguales ya no pasan |
| R3 | El matcher determinista confunde dos acciones y propone la equivocada | Media | `is_ambiguous` + `blocked_reason == "ambiguous"` deshabilita `[Ejecutar]` y ofrece elegir. Además `MIN_SCORE = 0.6` y `needs_confirmation` obligatorio para `write` |
| R4 | Una flag queda mal cableada y rompe tests ajenos | Alta (histórico) | §4.1: las 7 patas tabuladas, la regla "OFF no declara `default=False`", la regla R4 de la estrella, y el comando de verificación por flag |
| R5 | `test_harness_flags_help.py` sale rojo | Certeza parcial (4 fallos ajenos preexistentes) | Verificar que las 3 keys nuevas **no** estén entre las ofensoras; los textos de `PLAIN_HELP` ya fueron chequeados contra la denylist de `:17-20` |
| R6 | La paleta introduce un sondeo y rompe el ratchet del 239 F6 | Baja | El catálogo se pide **una vez al abrir**, nunca en intervalo; `devopsPollingRatchet.test.ts` es criterio de aceptación de F5 y F6 |
| R7 | Colisión de merge con 264 (modelo/effort) o 265 (consola) | Media | §8 declara la frontera archivo por archivo; el 267 **no toca** `model_catalog.py`, `llm_router.py`, `ModelEffortPicker.tsx`, `CodexConsoleDock.tsx` ni `store/workbench.ts` |
| R8 | Un modelo menor implementa `runDevOpsAction` con el orden de guardas invertido y ejecuta sin confirmar | Media | El orden de los 5 pasos está escrito literalmente en el docstring de F4, y los tests 7/8/11 lo verifican con spies de 0 llamadas |
| R9 | `sqlite` bajo pytest da `SQLITE_LOCKED` en los tests de API | Alta (conocido) | `test_devops_actions_api.py` **no escribe en la DB**: `/catalog`, `/propose` y `/preview` son de solo lectura. Si aun así aparece flaky, correr el archivo 8-12 veces y confirmar |
| R10 | Se agrega una sección DevOps nueva y `DEVOPS_SECTION_IDS` queda stale | Alta a mediano plazo | `test_section_ids_espejan_el_tsx` (F8, test 8) lee el `.tsx` real. *Verificado en la crítica v2: los 17 ids congelados del plan coinciden **exactamente** con los 17 de `DevOpsPage.tsx` (`:149`…`:320`), y la regex `^\s*id: '([a-z0-9-]+)',` devuelve esos 17 y nada más — el ratchet arranca verde y no por casualidad* |
| **R11** *(v2, C1)* | El registro del test en el `.ps1` se hace con sintaxis de bash (o no se hace) y el arnés de Windows corre menos tests que el de bash **sin ponerse rojo** | **Alta**: el meta-test solo lee el `.sh` | §4.2 tabula el símbolo, la línea y la sintaxis de cada runner. Verificación manual obligatoria al cerrar: `grep -c "test_devops_action" backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1` deben dar **4 y 4** |
| **R12** *(v2, C5)* | Un plan futuro "simplifica" `devopsActionCommands` y vuelve a poner las escrituras a un Enter de distancia | Media a mediano plazo | Invariante I-REACH verificada por **dos** ratchets independientes (F8 backend test 11 y frontend test 7) más el test 5 de F5 con spy de 0 llamadas. Hay que borrar tres tests para reabrirlo |

---

## 7. Fuera de scope (declarado, no escondido)

1. **Rediseño de shell, navegación, grupos, tokens o barrido de estilos inline.** Es el plan 239, ya implementado. El 267 no edita `devopsCockpitShell.ts`, `DevOpsCockpitNav.tsx`, `DevOpsTabsV2.tsx` ni `DevOpsHeaderV2.tsx`.
2. **El checklist visual de 10 puntos del 239 F8.** Sigue requiriendo navegador; RTL y jsdom no están en el `package.json` del frontend. El 267 **reduce** su superficie (la coherencia de acciones pasa a ser verificable por test) pero no lo cierra.
3. **Eliminar el chat de texto libre de `api/devops_agent.py`.** Se deja intacto, incluido su 400 para Copilot (`:69-78`). Removerlo es un plan aparte, con su propia migración.
4. **Endpoints de ejecución nuevos en el backend.** El 267 declara y confirma; ejecuta reusando lo que ya existe. Un endpoint `POST /devops/actions/execute` sería una segunda implementación de 23 operaciones — exactamente lo que este plan combate.
5. **Ejecución multi-paso / encadenada** ("desplegá y después corré los smoke tests"). Una propuesta = una acción. El encadenamiento es un plan posterior, y necesitaría su propio contrato de HITL por paso.
6. **Enriquecimiento por LLM de la propuesta** (mejorar `what_will_happen` o inferir parámetros con un modelo). El seam está listo (`describe()` es reemplazable y `PreflightRuntimeUnavailable` es el fallback), pero el 267 entrega **solo el camino determinista**, que es el que da paridad de 3 runtimes.
7. **Persistir un historial de recibos.** Los recibos se muestran en sesión. Persistirlos es del eje de telemetría (plan 171).
8. **Traducir el catálogo a otros idiomas.** Todo en español rioplatense, como el resto del producto.

---

## 8. Frontera de merge y convivencia con 239, 264 y 265

| Plan | Archivos que ESE plan posee | Qué hace el 267 con ellos |
|------|------------------------------|----------------------------|
| **239** (IMPLEMENTADO) | `pages/devopsCockpitShell.ts`, `pages/DevOpsCockpitNav.tsx`, `pages/DevOpsTabsV2.tsx`, `pages/DevOpsHeaderV2.tsx`, `services/devops_overview.py`, `components/devops/DevOpsOverviewSection.tsx`, `__tests__/devopsPollingRatchet.test.ts` | **Lectura solamente.** El 267 consume `DevOpsSection.id` y `nav_path=/devops/<id>`, y agrega la acción `devops.overview.refresh` que llama al `GET /api/devops/overview` existente. **Cero ediciones.** `devopsPollingRatchet.test.ts` es criterio de aceptación de F5 y F6 |
| **264** (CRITICADO v2, sin implementar) | `services/model_catalog.py`, `services/llm_router.py`, `components/ModelEffortPicker.tsx`, `agent_runner.py:256-264`, **y `api/devops_agent.py:15`** — el 264 lista ese `_EFFORTS` como uno de los 5 literales que va a reemplazar (ver su §2 y su bloque de F, `# api/devops_agent.py:15`) [C19] | **Cero ediciones, y en particular CERO ediciones a `api/devops_agent.py`**, que es propiedad del 264 en ese punto. El 267 no toca el eje modelo/effort porque su camino es determinista. Si más adelante se agrega enriquecimiento por LLM (fuera de scope, §7.6), debe usar `clamp_model`/`clamp_effort_for_model` del 264 y **nunca** el literal `_EFFORTS` |
| **265** (PROPUESTO v1) | `components/CodexConsoleDock.tsx`, `store/workbench.ts`, `hooks/useExecutionStream.ts` | **Cero ediciones.** *Medido el 2026-07-27:* el doc del 265 **no menciona `CommandPalette` ni `commandPaletteData` ni una sola vez**, así que el riesgo de colisión en la paleta que el v1 declaraba es **teórico, no real** [C19]. Igual se mantiene la regla de convivencia por si el 265 crece: el 267 agrega `"devops-action"` **al final** del union `CommandKind` y una función nueva; no reordena `CommandKind` ni modifica `NAV_COMMANDS`, `fuzzyScore` ni `mergeDeepResults`. **Ojo con el duplicado silencioso**: si dos ramas agregan una entrada a `DEEP_ICONS`, git puede fusionar sin conflicto — verificar `tsc --noEmit` después del merge |
| **175** (implementado) | `services/entityActions.ts`, `services/confirmGateway.ts` | `confirmGateway.ts` se **importa sin modificar**. `entityActions.ts` se toca **solo** si se decide exportar `EntityKind` ampliado — **no hace falta**: `devops-action` vive en su propio módulo y `EntityKind` usa `Extract<>`, que ignora los valores nuevos del union |
| **129** (implementado) | `components/commandPaletteData.ts`, `components/CommandPalette.tsx` | Edición **aditiva** (F5), con test de no-regresión de `fuzzyScore` |
| **41** (implementado) | `services/intent_preflight.py` | **Lectura solamente**: se calca la forma de `IntentBrief`. No se importa ni se modifica |
| **250** (implementado) | `api/pipeline_editor.py`, `components/devops/PipelineEditNlPanel.tsx`, sus 2 flags | **Cero ediciones.** El catálogo declara `devops.pipeline_edit.preview` y `devops.pipeline_edit.commit` apuntando a las flags **existentes** del 250. Su patrón ON/OFF es el precedente citado para la flag 3 |

---

## 9. Glosario

- **Acción** — una operación nombrable del panel DevOps, declarada una sola vez en `DEVOPS_ACTION_CATALOG`.
- **Catálogo** — `backend/services/devops_action_catalog.py`. Fuente de verdad de la **identidad y la seguridad** de una acción (qué es, dónde vive, si escribe, qué impacto tiene, qué flag la gatea, cómo se pide en español).
- **Binding** — `frontend/src/services/devopsActionBindings.ts`. Fuente de verdad del **cómo se hace**, reusando endpoints existentes.
- **Superficie** — un lugar desde donde el operador dispara una acción. Son tres: botón manual, paleta, asistente.
- **`ActionProposal`** — lo que el asistente devuelve en vez de prosa. Calca `IntentBrief` (plan 41).
- **Recibo (`DevOpsActionReceipt`)** — el resultado visible de una acción: ok/error, resumen, detalle, duración, si fue confirmada.
- **`effect`** — `read` (no cambia nada) o `write` (escribe en un sistema real). Determina si se confirma.
- **`impact`** — `none` / `low` / `high`. Determina el `tone` de la confirmación.
- **`targets_environment`** — si la acción actúa sobre un entorno concreto del operador. Obliga a declarar el param `environment`.
- **`reach`** *(v2)* — desde qué superficies puede **dispararse** una acción: `button`, `palette-run`, `palette-nav`, `assistant`. Es el cuarto eje del catálogo y el que sostiene la invariante I-REACH.
- **I-REACH** *(v2)* — `effect == "write"` ⇒ `"palette-run" not in reach`. Una acción que escribe nunca queda a un fuzzy-match + Enter de distancia. Es el doble cerrojo de `entityActions.ts:44-46` aplicado a las tres superficies en vez de a una.
- **Ratchet** — test que solo permite mejorar: impide que nazca una acción fuera del catálogo, que el catálogo y los bindings diverjan, o que una escritura se vuelva ejecutable desde la paleta.
- **Las 7 patas** — los 7 lugares donde se cablea una flag del arnés (§4.1).

---

## 10. Orden de implementación

1. **F0** — `devops_action_catalog.py` + catálogo de 23 acciones (con `reach` y las 23 listas de `phrases`) + flag `STACKY_DEVOPS_ACTION_CATALOG_ENABLED` (7 patas) + `test_devops_action_catalog.py` (**21 tests**).
2. **F1** — `api/devops_actions.py` con `GET /catalog` y el seam `_health_payload_for_catalog()` + 3 keys nuevas en `_health_payload()` + los 3 atributos en `config.py` + `test_devops_actions_api.py` (5 tests).
3. **F2** — `devops_action_matcher.py` (con `_STOPWORDS` y `_content_tokens`) + `test_devops_action_matcher.py` (**15 tests**).
4. **F3** — `devops_action_proposal.py` + `POST /propose` (con `from dataclasses import replace`) + `POST /preview` + flag `STACKY_DEVOPS_ACTION_NL_ENABLED` (7 patas, incluye `_REQUIRES_MAP_FROZEN` y su `PLAIN_HELP` literal) + **14 tests más** en `test_devops_actions_api.py`.
5. **F4** — `devopsActionTypes.ts` + `devopsActionRunner.ts` (con `navPathWithParams` y `paletteMode`) + `devopsActionBindings.ts` + **17 tests de vitest** (14 + 3).
6. **F5** — `commandPaletteData.ts` (aditivo) + `CommandPalette.tsx` + `commandPaletteDevopsActions.test.ts` (**10 tests**).
7. **F6** — `devopsActionConsoleModel.ts` + `DevOpsActionProposalCard.tsx` + `DevOpsActionConsole.tsx` (**cero `style={{}}`**) + `DevOpsAgentSection.tsx` + flag `STACKY_DEVOPS_AGENT_ACTION_RUN_ENABLED` (default **OFF**, 7 patas, con su `PLAIN_HELP` literal) + **10 tests**.
8. **F7** — recableado de los 6 archivos de secciones, **uno por vez** + `plan267Adoption.test.ts` (3 tests).
9. **F8** — `test_devops_action_ratchet.py` (**13 tests**) + `devopsActionCatalogRatchet.test.ts` (**7 tests**) + la huella en `error_fingerprints.json`.

**Registro de los 4 archivos backend nuevos, con la sintaxis de cada runner [C1]** — `tests/test_devops_action_catalog.py`, `tests/test_devops_actions_api.py`, `tests/test_devops_action_matcher.py`, `tests/test_devops_action_ratchet.py`:
- en `backend/scripts/run_harness_tests.sh`, array **`HARNESS_TEST_FILES=(`** en **`:20`** ⇒ 4 líneas **desnudas** (`  tests/test_devops_action_catalog.py`)
- en `backend/scripts/run_harness_tests.ps1`, array **`$HarnessTestFiles = @(`** en **`:13`** ⇒ 4 líneas **entrecomilladas y con coma** (`  "tests/test_devops_action_catalog.py",`)

Verificación de que el registro quedó en los dos: `grep -c "test_devops_action" backend/scripts/run_harness_tests.sh` y el mismo sobre el `.ps1` deben dar **4** y **4**.

---

## 11. Definition of Done global

Todos estos comandos, corridos **por archivo** desde la raíz `Stacky Agents` (backend) o desde `frontend/` (vitest), en verde:

```
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_catalog.py -v      # 21 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_matcher.py -v      # 15 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_actions_api.py -v         # 19 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops_action_ratchet.py -v      # 13 passed
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags.py -v              # 56 passed (medido hoy: 56)
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_flags_requires.py -v     #  9 passed (medido hoy: 9)
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_harness_ratchet_meta.py -v       #  4 passed (medido hoy: 4)
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_devops.py -v                     # sin regresion
```
Más el verificador de las 3 claves de `PLAIN_HELP` de §4.1 ⇒ imprime `OK`. **`test_harness_flags_help.py` NO está en esta lista a propósito: hoy tiene 4 fallos ajenos (medido: 4 failed / 4 passed) y no puede ser criterio binario de nada [C10].**
```
npx vitest run src/services/devopsActionRunner.test.ts                       # 14 passed
npx vitest run src/services/devopsActionBindings.test.ts                     #  3 passed
npx vitest run src/components/devops/devopsActionConsoleModel.test.ts        # 10 passed
npx vitest run src/components/__tests__/commandPaletteDevopsActions.test.ts  # 10 passed
npx vitest run src/components/__tests__/commandPaletteData.test.ts           # sin regresion
npx vitest run src/__tests__/devopsActionCatalogRatchet.test.ts              #  7 passed
npx vitest run src/__tests__/plan267Adoption.test.ts                         #  3 passed
npx vitest run src/__tests__/devopsPollingRatchet.test.ts                    # sin regresion (cubre F6, NO F5)
npx vitest run src/__tests__/uiDebtRatchet.test.ts                           # sin regresion (los .tsx nuevos suman 0)
npx vitest run src/services/entityActions.test.ts                            # sin regresion
npx tsc --noEmit                                                             # 0 errores
```
**Total de tests nuevos: 68 backend + 47 frontend.**

Y estos criterios cualitativos, verificables leyendo el diff:

- [ ] Ningún archivo de los planes 239, 264 y 265 listados en §8 fue editado — **en particular, cero ediciones a `api/devops_agent.py`** (es del 264).
- [ ] Las 3 flags nuevas tienen sus 7 patas cableadas, y la OFF **no** declara `default=False`.
- [ ] La flag OFF tiene escrita, en su propia línea, la categoría de excepción **(B)** y el porqué con `archivo:línea`.
- [ ] Las 3 entradas de `PLAIN_HELP` están escritas con el texto literal de este plan (no inventadas).
- [ ] `grep -c "test_devops_action"` da **4** en `run_harness_tests.sh` **y 4** en `run_harness_tests.ps1`, cada uno con la sintaxis de su runner.
- [ ] Ningún `setInterval`, `setTimeout` recurrente ni `refetchInterval` nuevo — **incluido `CommandPalette.tsx`, que ningún ratchet existente cubre**.
- [ ] Ningún endpoint de ejecución nuevo en el backend.
- [ ] Ningún botón existente del panel DevOps fue borrado, y `"button" in reach` para las 23 acciones.
- [ ] **Ninguna acción con `effect:"write"` tiene `"palette-run"` en su `reach`** (I-REACH / KPI-9).
- [ ] **Con las 3 flags apagadas: los mismos botones, en los mismos lugares, con el mismo efecto y el mismo `tone`. Lo único distinto es el TEXTO de la confirmación, que ahora sale del catálogo — que es el objetivo del plan [C4].** (El v1 pedía "se comporta igual que antes", un checkbox falso por construcción tras F7.)
