# Plan 264 — Herramienta, modelo y effort elegibles en TODO punto de uso: una sola matriz de capacidades, una sola resolución, un solo selector

**Estado:** MEJORADO **v1 -> v2** (2026-07-27) · **Autor:** pipeline `proponer-plan-stacky` · **Juez:** `criticar-y-mejorar-plan` — **v1 RECHAZADO** (4 BLOQUEANTES), v2 con los fixes aplicados.

---

## 0. CHANGELOG v1 -> v2

- **C1 (BLOQUEANTE) — el presupuesto de turnos de Codex estaba INVERTIDO y era destructivo.** `STACKY_RUNAWAY_MAX_TURNS` vale **`"0"` por default** (`config.py:471-473`) y `RunLimits(max_turns=0)` significa **sin límite** (`harness/runaway_guard.py:8,20,45`). Con la fórmula del v1 (`base + {low:0…max:3}`), elegir **`max`** convertía "ilimitado" en **un cap de 3 turnos** (el guard mataba el run al turno 3) y elegir `low` dejaba el run ilimitado. Y con cap configurado (p. ej. 40), `max` lo subía a **43**, *por encima* del techo de seguridad que puso el operador. Peor: el **test 5 del v1 salía VERDE** con ese comportamiento invertido (`0 < 3` es numéricamente cierto) ⇒ falso verde perfecto. v2: `codex_turn_budget` es **monótono hacia abajo desde el cap**, `0` es sagrado, y hay 4 aserciones que blindan la inversión (§5 F2).
- **C2 (BLOQUEANTE) — el fix de F2 vivía DENTRO de un `if` de dos flags ajenas, así que no cerraba el hueco.** El bloque de `codex_cli_runner.py:582` está gateado por `STACKY_ADAPTIVE_EFFORT_ENABLED` **y** por `_codex_complexity` (que sólo se llena si `STACKY_COMPLEXITY_ESTIMATION_ENABLED`, `:445`). Con cualquiera OFF, el effort del operador se seguía descartando en silencio — exactamente el bug que el plan dice cerrar. v2: la resolución del effort explícito sale **fuera y antes** del bloque adaptativo, replicando el patrón real de Claude (`claude_code_cli_runner.py:958-961`), + test con las dos flags en OFF.
- **C3 (BLOQUEANTE) — F0 mandaba las 4 keys al archivo equivocado y declaraba "Archivos a editar (2)".** `_CURATED_DEFAULTS_ON` vive en **`backend/tests/test_harness_flags.py:467`**, no en `harness_flags.py:454` (ahí vive `_CATEGORY_KEYS`). Con `default=True` y sin tocar el test, `test_default_known_only_for_curated` sale **ROJO** en la primera fase. v2: **3 archivos**, cada estructura con su ubicación real (§5 F0).
- **C4 (BLOQUEANTE) — la lista "cerrada" de 10 call sites estaba incompleta y hacía imposible su propio KPI-2.** Falta **`services/parallel_runs.py:58`** (pasa `model_override` pero **no** `effort_override`). El test AST exige que **todas** las llamadas pasen ambos; con 10 filas editadas y allowlist de 1 reservada a `variant_generator.py`, el criterio nacía rojo. v2: tabla de **11** filas + allowlist de hasta 2 con motivo escrito.
- **C5 (IMPORTANTE) — la clave de preferencia 400eaba con la mayoría de los proyectos.** `_UI_KEY_RE = ^[A-Za-z0-9._-]{1,128}$` rechaza espacios, acentos y paréntesis; y `api.put` **lanza** en non-2xx. Además el endpoint está gateado por `STACKY_UI_SAVED_VIEWS_ENABLED` (`config.py:1810`), que el v1 nunca nombraba. v2: slug determinista + fallback silencioso + dependencia declarada (§5 F4).
- **C6 (IMPORTANTE) — el diff de F4 borraba `downgraded` y `reason` del trace** y rompía `test_plan212_requested_vs_effective.py`, que el propio F7 corre como regresión. v2: el diff los conserva y **F6 los consume** en vez de recalcular la comparación a mano.
- **C7 (IMPORTANTE) — F5 mostraba un cuerpo de `pickerCapabilities` que no es el real y su test 2 nacía rojo.** La función real ya devuelve `note` (leyendo `effort_note`) y calcula `showEfforts` **sin mirar** `effort_mode`. v2: diff sobre el cuerpo real, se reusa `note` (no se duplica), y la línea literal que hace `showEfforts=false` para `no_aplica`.
- **C8 (IMPORTANTE) — el plan se contradecía sobre el nivel de import** ("a nivel de módulo es seguro" en F1 vs "sólo dentro de funciones" en R1). v2: una sola regla, en dos direcciones separadas (§5 F1).
- **C9 (IMPORTANTE) — `load/save_run_preference` invertía la capa y no decía qué símbolo usar.** La lógica del sub-objeto `ui` vive en el **cuerpo de la ruta**, no en una función reusable. v2: se extraen dos helpers puros en `api/preferences.py` que la ruta existente pasa a usar (contrato HTTP intacto).
- **C10 (MENOR)** — se agrega la huella de regresión a `docs/sistema/error_fingerprints.json` (§5 F7).
- **C11 (MENOR)** — se agrega **§9 Convivencia con 260/263/265** (frontera de merge, orden y qué entra en el KPI).
- **C12 (MENOR)** — se aclara que `EFFORTS` es el **vocabulario de validación** y el catálogo la **fuente de presentación**, con un test que impide que se desincronicen.
- **[ADICIÓN ARQUITECTO] F2.5** — centinela ejecutable de paridad: un test AST que prohíbe parámetros de selección **aceptados y nunca consumidos**, y un test parametrizado **derivado de `RUNTIMES`** que obliga a todo runtime futuro a honrar (o declarar) el effort. Es el gate que habría atrapado el bug de Codex el día que se escribió.
- **[ADICIÓN ARQUITECTO] §9.1** — contrato público congelado del 264 para que 260 y 265 construyan contra él sin esperar a que se implemente.

---

## 1. Objetivo y KPI

Stacky ya tiene las tres piezas buenas: el catálogo vivo por runtime
(`services/model_catalog.py`, Plan 159 + 212), la matriz de clamp
(`services/llm_router.py::clamp_model` / `::clamp_effort_for_model`, Plan 212 F2) y un selector reusable
bien diseñado (`components/ModelEffortPicker.tsx`, Plan 212 F4). Lo que falta es **cobertura y unicidad**:

1. **El effort NO llega a Codex.** `agent_runner.py:256-264` invoca `start_codex_cli_run(...)` pasando
   `model_override` pero **sin** `effort_override` — y `start_codex_cli_run` ni siquiera acepta ese
   parámetro (`services/codex_cli_runner.py:87-97`, verificado). Es exactamente el mismo falso verde que
   el Plan 196 descubrió y arregló para `claude_code_cli` (`agent_runner.py:344-350`): **el gemelo de
   Codex sigue vivo**. El operador elige "high" y Codex corre como si no hubiera elegido nada.
2. **La lista de efforts está escrita 5 veces.** `api/agents.py:425` (`_VALID_EFFORTS`),
   `api/devops_agent.py:15` (`_EFFORTS`), `api/devops_remote_console.py:212` y `:313` (literal inline
   duplicado), `services/claude_code_cli_runner.py:2224` (`CLI_VALID_EFFORTS`). Agregar un effort nuevo
   hoy exige tocar 5 lugares y ninguno falla si te olvidás de uno.
3. **11 de 17 puntos de lanzamiento no ofrecen elección.** `run_agent(...)` se llama desde 17 lugares
   fuera de `tests/` y `evals/`; `phase6.py:192`, `phase6.py:229`, `doc_documenter.py:383`,
   `pipeline_orchestrator.py:58`, `slash_commands.py:101`, `variant_generator.py:188`,
   `devops_section_doctor.py:171`, `macros.py:177` y las tres de `parallel_runs.py` (`:58`, `:126`,
   `:169`) **no pasan modelo y/o effort**: corren con lo que caiga.
4. **El selector está cableado en 2 pantallas de 4.** `ModelEffortPicker` sólo lo usan
   `EpicFromBriefModal.tsx:491` y `TicketBoard.tsx:221`. `PlansBoardPage.tsx:148-162,338-345` y
   `IncidentResolverModal.tsx:83-100` tienen **cada uno su propio selector hecho a mano**, con su propia
   lógica de defaults y degradación.
5. **El historial no registra qué se usó, salvo en Claude.** `build_model_effort_trace` y
   `_persist_model_effort_trace` viven sólo en `claude_code_cli_runner.py:516-561`. Una corrida de Codex
   no deja rastro del effort pedido vs. el efectivo.

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Literales de la lista de efforts en el backend (fuera de `tests/`) | **5** | **1** (`services/runtime_capabilities.py`) |
| **KPI-2** Llamadas a `run_agent(...)` sin resolución de modelo/effort | **11** | **0** (allowlist máx. 2, con motivo escrito) |
| **KPI-3** Runtimes en los que el `effort` elegido llega al runner | **1** (claude) | **3** (claude nativo, codex por presupuesto de turnos, copilot declarado no-aplicable) |
| **KPI-4** Selectores de modelo/effort implementados a mano en el frontend | **2** | **0** (superficies enumeradas en §9.2) |
| **KPI-5** Ejecuciones cuyo `metadata_dict["model_effort"]` registra `{tool, requested/effective, effort_mode}` | sólo claude | **los 3 runtimes** |
| **KPI-6 [ADICIÓN]** Parámetros de selección aceptados por un runner y **nunca consumidos** | **1** (`codex`, latente) | **0**, verificado por AST en cada corrida del arnés |

---

## 2. Por qué ahora / gap que cierra

El Plan 212 (`212_PLAN_SELECTOR_VIVO_DE_MODELO_Y_EFFORT_EN_TICKETS_ADO_Y_CUMPLIMIENTO_REAL_DE_LA_ELECCION.md`)
puso el título correcto: **"cumplimiento real de la elección"**. Construyó la matriz, el picker y el
trace — pero acotado al tablero de tickets ADO. El Plan 196, al implementarse el 2026-07-26, encontró
por casualidad que la rama `claude_code_cli` de `run_agent` descartaba el effort en silencio, y lo
arregló con una línea. Este plan hace lo que faltó: **buscar el resto de los lugares donde la elección
se descarta, en vez de esperar a tropezarlos.** Y ya encontró uno idéntico en Codex.

El gap no es "falta un selector". Es que **la elección tiene 5 fuentes de verdad y 4 implementaciones**,
así que cada superficie nueva reinventa la degradación y cada una se equivoca distinto.

**Lo que el v1 no había visto (y por eso existe F2.5):** el bug no es "alguien se olvidó una línea". Es
que el sistema **no tiene forma de detectar** que un parámetro de selección fue aceptado y nunca usado.
Arreglar Codex a mano deja el mismo agujero abierto para el runtime número 4. Por eso el v2 no arregla
un caso: instala el centinela que hace imposible el caso.

---

## 3. Principios y guardarraíles

1. **3 runtimes con paridad explícita, incluida la degradación honesta.** El effort **no existe** como
   flag de línea de comandos en Codex: `codex_cli_runner.py:581` lo dice literalmente — *"Codex no tiene
   --effort; se ajusta el presupuesto de turnos bajo el cap"*. Nótese **"bajo el cap"**: el presupuesto
   se mueve **hacia abajo desde el techo**, nunca hacia arriba (ver C1 / F2). Y GitHub Copilot Pro no
   expone effort en absoluto. La regla de este plan: **la capacidad se declara, no se finge**. Cada
   runtime declara `effort_mode` ∈ `{"nativo", "presupuesto_turnos", "no_aplica"}`, y la UI muestra al
   operador qué va a pasar realmente con su elección. **Prohibido** mostrar un selector que no hace nada.
2. **Cero trabajo extra para el operador.** Todo tiene default: el catálogo ya trae `default_model` y
   `default_effort` por runtime. Si el operador no toca nada, se comporta como hoy o mejor. Todas las
   flags de este plan nacen **ON** — ninguna cae en las categorías de excepción (ver §5 F0).
3. **Human-in-the-loop.** La resolución **nunca** escala el effort por su cuenta por encima de lo que el
   operador pidió explícitamente. El selector adaptativo existente (`services/adaptive_selector.py`)
   sigue siendo el piso, no el techo: **un override explícito siempre gana** (es la regla que ya
   respeta `claude_code_cli_runner.py:958-961`).
4. **Mono-operador sin auth.** La preferencia se guarda por **proyecto**, no por usuario. Nada de RBAC.
5. **Backward-compatible.** `_clamp_effort_for_model` (`api/agents.py:612`) y `CLI_VALID_EFFORTS`
   (`claude_code_cli_runner.py:2224`) **se conservan como delegadores** al módulo único. No se borra
   ningún símbolo público **ni ninguna clave de un dict público** (ver C6: `downgraded` y `reason` del
   trace se conservan). Las firmas de `run_agent`, `start_claude_code_cli_run` y `start_codex_cli_run`
   sólo ganan parámetros keyword-only con default `None`.
6. **No degradar — y en particular, no tocar el techo de seguridad.** El módulo nuevo es aritmética pura
   sobre un dict ya cacheado. Cero I/O nuevo, cero red, cero llamada a modelo. `load_model_catalog()` ya
   tiene su caché TTL 300 s (`model_catalog.py:16`) y no se toca. **Invariante duro nuevo:** ninguna
   elección de effort puede aumentar `max_turns` del `RunawayGuard` por encima de
   `config.STACKY_RUNAWAY_MAX_TURNS`, ni convertir "sin límite" (`0`) en un límite.
7. **Reusar.** Catálogo del 159/212, clamp del `llm_router`, picker del 212 F4, preferencias de
   `api/preferences.py`, telemetría del 171/258, `ModelDecisionChip` del 212. **No se crea ningún
   catálogo nuevo, ningún endpoint nuevo, ningún chip nuevo.**

---

## 4. Glosario

| Término | Significado |
|---|---|
| **runtime / herramienta** | `claude_code_cli`, `codex_cli` o `github_copilot`. Es lo que el usuario llama "herramienta o proveedor". |
| **catálogo** | `config/model_catalog.json` leído por `services/model_catalog.py`, con `models`, `efforts`, `effort_support`, `effort_degrade`, `default_model`, `default_effort` por runtime. |
| **clamp de modelo** | `llm_router.clamp_model`: mapea tiers prohibidos (opus/fable) a `CLAUDE_CAP_MODEL = "claude-sonnet-5"` salvo `allow_opus`. |
| **clamp de effort** | `llm_router.clamp_effort_for_model`: baja el effort al máximo que soporta el modelo elegido. |
| **effort_mode** | **NUEVO**: cómo un runtime materializa el effort. `nativo` (flag del CLI), `presupuesto_turnos` (se traduce a fracción del cap de turnos) o `no_aplica`. |
| **cap de turnos** | `config.STACKY_RUNAWAY_MAX_TURNS`. **`0` = sin límite.** Es el techo de seguridad del `RunawayGuard`; el effort sólo puede moverse **por debajo** de él. |
| **selección resuelta** | **NUEVO**: la tupla `(runtime, model, effort_requested, effort_effective, origen)` que sale de `resolve_run_selection()`. |
| **origen** | De dónde salió cada valor: `"explicito"`, `"preferencia"`, `"adaptativo"` o `"default_catalogo"`. |
| **trace** | El dict que `build_model_effort_trace` persiste en `metadata_dict["model_effort"]` de la ejecución. Claves existentes que **no se tocan**: `requested_model`, `effective_model`, `requested_effort`, `effective_effort`, `downgraded`, `reason`. |

---

## 5. Fases

### F0 — Flags (patrón triple: 3 archivos, 3 estructuras)

**Objetivo.** Dar de alta las 4 flags del plan **sin poner en rojo el guard de flags curadas**.

> **[FIX C3] Lección ya escrita en el propio código.** `default_is_known(spec)` es
> `spec.default is not None` (`services/harness_flags.py:5503`) y el guard
> `test_default_known_only_for_curated` (`tests/test_harness_flags.py:974`) exige **igualdad exacta de
> conjuntos** contra `_CURATED_DEFAULTS_ON`, que vive en **`backend/tests/test_harness_flags.py:467`**
> — *no* en `harness_flags.py`. En `harness_flags.py:120/454` vive `_CATEGORY_KEYS`, que es otra cosa
> (asigna flags a categorías de UI). Declarar `default=True` sin agregar la key al conjunto curado ⇒
> **ROJO "Extras (no curadas)"**. El v1 declaraba "Archivos a editar (2)" y nunca mandaba a tocar el
> archivo de test: la primera fase nacía roja. Precedente idéntico documentado en
> `services/harness_flags.py:3166-3173` (Plan 250).

**Archivos a editar (3) — ubicación real de cada estructura:**

| # | Archivo | Estructura | Dónde |
|---|---|---|---|
| 1 | `Stacky Agents/backend/config.py` | los 4 `os.getenv(...)` | junto a `STACKY_MODEL_PROBE_ENABLED` (`config.py:1258`) |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | los 4 `FlagSpec` **y** las 4 keys en `_CATEGORY_KEYS` | `FLAG_REGISTRY`; `_CATEGORY_KEYS` abre en `harness_flags.py:120` |
| 3 | `Stacky Agents/backend/tests/test_harness_flags.py` | las 4 keys en `_CURATED_DEFAULTS_ON` | `test_harness_flags.py:467` |

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
(nacen ON, y **por eso mismo** hay que curarlas en el paso 3). Ninguna lleva `env_only=True`: son
configuración del operador y se editan por UI (regla dura del repo).

```python
    # ── Plan 264 — herramienta/modelo/effort elegibles en todo punto de uso ──
    FlagSpec(
        key="STACKY_RUNTIME_CAPABILITIES_ENABLED",
        type="bool", default=True,   # Curada en tests/test_harness_flags.py:467.
        label="Matriz unica de capacidades de runtime",
        description=(
            "Plan 264 — Una sola fuente para 'que modelos y efforts admite cada "
            "herramienta y como degrada'. Reemplaza las 5 copias de la lista de "
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
            "descarta en silencio (agent_runner.py:256-264). Solo aplica a corridas "
            "que el operador lanza; no enciende ningun proceso de fondo."
        ),
        group="global",
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",
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
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",
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
        requires="STACKY_RUNTIME_CAPABILITIES_ENABLED",
    ),
```

y **en el mismo archivo**, agregar las 4 keys a `_CATEGORY_KEYS` (`harness_flags.py:120`), en la
categoría donde ya vive `"STACKY_MODEL_PROBE_ENABLED"`. Sin esto,
`test_flag_registry_categorization` sale rojo por flags sin categoría.

**3) `tests/test_harness_flags.py:467`** — agregar las 4 keys al conjunto `_CURATED_DEFAULTS_ON`:

```python
    "STACKY_RUNTIME_CAPABILITIES_ENABLED",      # Plan 264
    "STACKY_CODEX_EFFORT_PARITY_ENABLED",       # Plan 264
    "STACKY_RUN_SELECTION_PREFS_ENABLED",       # Plan 264
    "STACKY_MODEL_PICKER_EVERYWHERE_ENABLED",   # Plan 264
```

> **Regla espejo (por si alguna de estas flags se decidiera OFF en el futuro):** una flag que nace OFF
> **NO debe** escribir `default=False` en su `FlagSpec` (`False is not None` ⇒ `default_is_known=True` ⇒
> exige estar en el conjunto curado ⇒ rojo). Se declara **omitiendo `default=`** y dejando el default
> efectivo en `config.py` (`"false"`). En este plan **las 4 nacen ON**, así que las 4 llevan
> `default=True` **y** van al conjunto curado.

**Por qué las 4 nacen ON (justificación explícita):** ninguna enciende loops, daemons, barridos, polling
ni prefetch, y **ninguna dispara una llamada a un modelo/CLI en reposo** — no hay **categoría (A)**.
Ninguna escribe en ADO/GitLab/repo remoto, ni ejecuta DDL/DML, ni despliega, ni borra datos, ni decide
por el operador — no hay **categoría (B)**. Detalle por flag:

- `STACKY_RUNTIME_CAPABILITIES_ENABLED`: aritmética pura sobre un dict cacheado. Cero I/O.
- `STACKY_CODEX_EFFORT_PARITY_ENABLED`: sólo se evalúa **dentro** de una corrida que el operador lanzó,
  y con el esfuerzo que él eligió. Además, tras el fix de C1, **nunca sube el gasto por encima del cap
  que el operador ya tenía configurado**: sólo puede bajarlo. Es on-demand y acotado por arriba.
- `STACKY_RUN_SELECTION_PREFS_ENABLED`: escribe únicamente en `data/preferences.json` de Stacky, que
  `api/preferences.py` ya escribe hoy. No es un sistema del operador.
- `STACKY_MODEL_PICKER_EVERYWHERE_ENABLED`: render de UI. Cero llamadas.

> **Nota sobre `STACKY_MODEL_PROBE_ENABLED` (flag AJENA, ya existente, default ON).** Este plan **la
> reusa como lectura** vía `model_catalog`, pero **NO** la enciende, **NO** la extiende y **NO** agrega
> ningún sondeo nuevo. El probe vive en `model_catalog._merge_probe` (`model_catalog.py:128-140`), corre
> sólo cuando alguien **pide** el catálogo, y está corto-circuitado bajo `STACKY_TEST_MODE`. **Prohibido
> en este plan:** llamar a `capabilities_for()` / `resolve_run_selection()` desde cualquier loop, timer,
> hook de arranque o barrido de fondo. Si una fase futura necesitara eso, cae en categoría (A) y la flag
> correspondiente nace OFF.

**Tests:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
```
**Criterio binario.** Ambos exit 0. En particular `test_default_known_only_for_curated` **verde**
(es el que el v1 dejaba rojo).
**Impacto por runtime:** ninguno (configuración). **Trabajo del operador: ninguno.**

---

### F1 — Backend: `services/runtime_capabilities.py`, la única matriz (TDD)

**Objetivo.** Un solo módulo que responda "¿qué admite esta herramienta y cómo degrada?", y que las 5
copias de la lista de efforts pasen a delegar en él.

**Archivo a crear:** `Stacky Agents/backend/services/runtime_capabilities.py`.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_runtime_capabilities.py`.

> **[FIX C8] Regla ÚNICA de imports (dos direcciones distintas, no las mezcles):**
> 1. **Hacia afuera:** `runtime_capabilities.py` importa `model_catalog`, `llm_router` y `config`
>    **SIEMPRE dentro de las funciones**, nunca en el top-level del módulo. Motivo: `model_catalog`
>    importa `claude_code_cli_runner` (`model_catalog.py:135`), que a su vez va a importar
>    `runtime_capabilities` ⇒ ciclo si el top-level lo resolviera.
> 2. **Hacia adentro:** los consumidores (`claude_code_cli_runner.py`, `codex_cli_runner.py`,
>    `api/agents.py`, `api/devops_agent.py`, `api/devops_remote_console.py`) **sí** importan
>    `runtime_capabilities` **a nivel de módulo**. Es seguro precisamente por la regla 1: el top-level de
>    `runtime_capabilities` no importa nada de `services/`.
>
> Verificación obligatoria **antes de seguir a F2**:
> ```powershell
> "Stacky Agents\backend\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'Stacky Agents/backend'); import services.runtime_capabilities, services.claude_code_cli_runner, services.codex_cli_runner, api.agents, api.devops_agent, api.devops_remote_console; print('ok')"
> ```

**Contrato (símbolos exactos):**

```python
# El ÚNICO literal de efforts del backend. Todo lo demás delega acá.
# [FIX C12] Esto es el VOCABULARIO DE VALIDACIÓN (qué strings son legales).
# La FUENTE DE PRESENTACIÓN (labels, orden, soporte por modelo) sigue siendo el
# catálogo: config/model_catalog.json. Ver test 19.
EFFORTS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")
EFFORT_ORDER: dict[str, int] = {e: i for i, e in enumerate(EFFORTS)}

RUNTIMES: tuple[str, ...] = ("claude_code_cli", "codex_cli", "github_copilot")

# Cómo materializa el effort cada runtime. Declarativo, no inferido.
EFFORT_MODE: dict[str, str] = {
    "claude_code_cli": "nativo",              # el CLI acepta el esfuerzo directo
    "codex_cli":       "presupuesto_turnos",  # codex_cli_runner.py:581 — no hay --effort
    "github_copilot":  "no_aplica",           # el bridge no expone esfuerzo
}

# [FIX C1] Fracción del CAP de turnos que le toca a cada esfuerzo en codex.
# SIEMPRE <= 1.0: el effort sólo puede mover el presupuesto HACIA ABAJO desde el
# techo de seguridad. Reemplaza el `+N` del v1, que subía el cap y convertía
# "sin límite" (0) en un cap de 3 turnos.
CODEX_EFFORT_TURN_FACTOR: dict[str, float] = {
    "low": 0.5, "medium": 0.75, "high": 1.0, "xhigh": 1.0, "max": 1.0,
}


def is_valid_effort(effort: str | None) -> bool:
    """True si `effort` (case-insensitive, sin espacios) está en EFFORTS."""


def capabilities_for(runtime: str) -> dict:
    """Capacidades REALES de un runtime, leyendo el catálogo vivo.

    Devuelve SIEMPRE estas claves (nunca lanza, nunca devuelve None):
      {
        "runtime": str,
        "known": bool,                 # False si `runtime` no está en RUNTIMES
        "effort_mode": str,            # "nativo" | "presupuesto_turnos" | "no_aplica"
        "supports_model": bool,        # hay >=1 modelo elegible
        "supports_effort": bool,       # effort_mode != "no_aplica"
        "models": list[dict],          # del catálogo, tal cual
        "efforts": list[dict],         # del catálogo, tal cual ({"id","label"}); [] si no aplica
        "default_model": str | None,
        "default_effort": str | None,
        "effort_note": str,            # frase corta para la UI, en español
      }
    `effort_note` por modo:
      nativo              -> "El esfuerzo se le pasa directo a la herramienta."
      presupuesto_turnos  -> "Codex no acepta un esfuerzo explícito: se traduce a cuántos turnos de trabajo se le permiten, siempre por debajo del límite configurado."
      no_aplica           -> "Esta herramienta no expone niveles de esfuerzo; el selector no se muestra."
    """


def clamp_selection(runtime: str, model: str | None, effort: str | None,
                    *, allow_opus: bool = False) -> dict:
    """Ajusta (model, effort) a lo que el runtime realmente soporta.

    Devuelve {"model": str|None, "effort": str|None,
              "effort_requested": str|None, "degraded": bool, "reason": str|None}.
    - Delega el clamp de modelo en llm_router.clamp_model(model, allow_opus)
      SOLO para claude_code_cli (los otros runtimes no usan modelos Claude).
    - Delega el clamp de effort en llm_router.clamp_effort_for_model(effort, model).
    - Si effort_mode == "no_aplica" -> effort=None, degraded=True,
      reason="github_copilot no expone niveles de esfuerzo".
    - Un effort inválido cae al default_effort del catálogo, degraded=True.
    - Si config.config.STACKY_RUNTIME_CAPABILITIES_ENABLED es False -> devuelve
      (model, effort) sin tocar y degraded=False.
    NUNCA lanza.
    """


def codex_turn_budget(effort: str | None, cap_turns: int) -> int:
    """[FIX C1] Turnos que le corresponden a Codex para ese esfuerzo.

    CONTRATO DURO (el v1 lo tenía invertido y era destructivo):
      - `cap_turns <= 0` significa SIN LÍMITE (RunLimits(max_turns=0) = sin límite,
        harness/runaway_guard.py:8,20,45). En ese caso devuelve SIEMPRE 0,
        cualquiera sea el esfuerzo. Nunca convierte "sin límite" en un límite.
      - Con `cap_turns > 0`: devuelve `max(1, int(cap_turns * factor))`, con
        factor = CODEX_EFFORT_TURN_FACTOR[effort]. **Nunca > cap_turns.**
      - `effort` None o inválido -> `cap_turns` sin cambio.
      - Es monótono no decreciente en el orden de EFFORTS.
    Nunca lanza.
    """
```

**Casos de test (mínimo 22):**

| # | Caso | Aserción |
|---|---|---|
| 1 | `EFFORTS` | `== ("low","medium","high","xhigh","max")` |
| 2 | `is_valid_effort("HIGH ")` | `True` (normaliza) |
| 3 | `is_valid_effort("turbo")` / `None` / `""` | `False` |
| 4 | `capabilities_for("claude_code_cli")["effort_mode"]` | `"nativo"` |
| 5 | `capabilities_for("codex_cli")["effort_mode"]` | `"presupuesto_turnos"` |
| 6 | `capabilities_for("github_copilot")["supports_effort"]` | `False` |
| 7 | `capabilities_for("inventado")["known"]` | `False`, y no lanza |
| 8 | `capabilities_for(...)` con el catálogo caído (monkeypatch que hace lanzar a `load_model_catalog`) | devuelve el dict completo igual, con **todas** las claves del contrato |
| 9 | `clamp_selection("claude_code_cli","claude-opus-4-8","max")` | `model == "claude-sonnet-5"`, `degraded is True` |
| 10 | idem con `allow_opus=True` | `model == "claude-opus-4-8"` |
| 11 | `clamp_selection("claude_code_cli","claude-haiku-4-5","max")` | `effort == "high"` (según `effort_degrade` del catálogo), `degraded is True` |
| 12 | `clamp_selection("github_copilot", None, "high")` | `effort is None`, `degraded is True`, `reason` no vacío |
| 13 | `clamp_selection("codex_cli", None, "high")` | `effort == "high"` (se conserva; lo materializa el presupuesto) |
| 14 | `clamp_selection("claude_code_cli", None, "turbo")` | `effort == default_effort` del catálogo, `degraded is True` |
| 15 | `clamp_selection(...)["effort_requested"]` | siempre trae lo pedido original, aunque haya degradado |
| **16** | **[FIX C1]** `codex_turn_budget("max", 0)` y `codex_turn_budget("low", 0)` | **ambos `== 0`** (sin límite se mantiene sin límite) |
| **17** | **[FIX C1]** `codex_turn_budget(e, 40) <= 40` **para los 5 efforts** | `True` en los 5 (el effort NUNCA sube el cap) |
| **18** | **[FIX C1]** `codex_turn_budget("low", 40)` vs `codex_turn_budget("max", 40)` | `20 <= presupuesto("max") == 40`, y `presupuesto("low") < presupuesto("max")` |
| 19 | `codex_turn_budget(None, 40)` / `codex_turn_budget("turbo", 40)` | `40` (sin cambio) |
| 20 | `codex_turn_budget("medium", 1)` | `>= 1` (nunca 0 con cap>0: 0 significaría "sin límite") |
| 21 | flag OFF (`config.config.STACKY_RUNTIME_CAPABILITIES_ENABLED = False`) | `clamp_selection` devuelve `(model, effort)` sin tocar y `degraded is False` |
| **22** | **[FIX C12]** para cada runtime del catálogo: `{e["id"] for e in caps["efforts"]} <= set(EFFORTS)` | `True` — el catálogo no puede ofrecer un effort que el backend no valida |

> **Gotcha obligatorio:** leé la flag por **`config.config.STACKY_...`** (la instancia), nunca
> `config.STACKY_...` (el módulo) — el módulo devuelve el default y el test 21 queda en falso verde.

**Deduplicación (KPI-1) — editar 5 ocurrencias en 4 archivos, todas por delegación, sin borrar símbolos:**

```diff
# api/agents.py:425
-    _VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
+    from services.runtime_capabilities import EFFORTS as _VALID_EFFORTS
```
```diff
# api/devops_agent.py:15
-_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
+from services.runtime_capabilities import EFFORTS as _EFFORTS_TUPLE
+_EFFORTS = set(_EFFORTS_TUPLE)
```
```diff
# api/devops_remote_console.py:212 y :313 (las DOS ocurrencias; el literal se
# extiende a la línea siguiente, :213 y :314 — reemplazá la sentencia COMPLETA)
-    effort_override = effort.strip().lower() if effort and effort.strip().lower() in {
-        "low", "medium", "high", "xhigh", "max"} else None
+    from services.runtime_capabilities import is_valid_effort
+    _e = (effort or "").strip().lower()
+    effort_override = _e if is_valid_effort(_e) else None
```
```diff
# services/claude_code_cli_runner.py:2224
-CLI_VALID_EFFORTS = ("low", "medium", "high", "xhigh", "max")
+from services.runtime_capabilities import EFFORTS as CLI_VALID_EFFORTS  # Plan 264 — símbolo conservado
```

> **`CLI_VALID_EFFORTS` tiene consumidores externos**: `claude_code_cli_runner.py:2301`,
> `tests/test_plan212_characterization.py:168` y `tests/test_plan212_effort_matrix_parity.py:65-74`
> (que hacen `set(CLI_VALID_EFFORTS)`). Por eso el símbolo se **conserva** como alias de `EFFORTS`
> (misma tupla, mismo contenido) en vez de borrarse. Los dos tests del 212 deben seguir verdes.

**Registrar** `tests/test_plan264_runtime_capabilities.py` en **ambas** listas `HARNESS_TEST_FILES`
(`backend/scripts/run_harness_tests.sh:20` y la copia `.ps1`, que tiene **sintaxis distinta** — no
copies la línea del `.sh` tal cual), o `test_harness_ratchet_meta.py` sale rojo.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_runtime_capabilities.py" -q
```

**Criterio binario.** 22 passed. Y el grep de KPI-1:
```bash
grep -rnE '\("low", *"medium", *"high", *"xhigh", *"max"\)|\{"low", *"medium", *"high", *"xhigh", *"max"\}' --include=*.py "Stacky Agents/backend" | grep -v "services/runtime_capabilities.py" | grep -v "/tests/" | wc -l
```
debe dar **0**.

**Flag:** `STACKY_RUNTIME_CAPABILITIES_ENABLED`, default **ON**.
**Impacto por runtime:** el módulo **describe** los 3; no ejecuta ninguno.
**Trabajo del operador: ninguno.**

---

### F2 — Backend: paridad real de Codex (el bug gemelo del Plan 196)

**Objetivo.** Que el effort elegido llegue a Codex **con cualquier configuración de flags**, y que quede
registrado — sin tocar el techo de seguridad de turnos.

> **[FIX C2] Leé esto antes de editar: el v1 metía el fix en una rama condicional.**
> El bloque de `codex_cli_runner.py:582` es:
> ```python
> if getattr(config, "STACKY_ADAPTIVE_EFFORT_ENABLED", False) and _codex_complexity:
> ```
> y `_codex_complexity` sólo se llena si `config.STACKY_COMPLEXITY_ESTIMATION_ENABLED`
> (`codex_cli_runner.py:445-466`). Ambas están ON por default hoy, **pero son flags ajenas que el
> operador puede apagar por UI**. Poner el override adentro de ese `if` significa que apagar cualquiera
> de las dos vuelve a descartar el effort en silencio — el bug que este plan dice cerrar. El fix va
> **fuera y antes** del bloque, igual que en Claude (`claude_code_cli_runner.py:958-961`, donde
> `_effective_effort = effort_override or _adaptive_effort` está fuera del bloque adaptativo).

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
(c) **La zona del esfuerzo (`codex_cli_runner.py:580-597`) se reestructura así.** Comparalo con el
código real antes de editar; el nombre `_codex_adaptive_turns` y la constante
`config.STACKY_RUNAWAY_MAX_TURNS` **ya existen** en ese bloque y no se renombran:

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
+        # Plan 264 [C2] — FUERA del bloque adaptativo: el override explícito del
+        # operador se honra tenga o no estimación de complejidad, y le GANA al
+        # adaptativo (misma regla que claude_code_cli_runner.py:958-961).
+        from services.runtime_capabilities import (
+            is_valid_effort as _rc_valid, codex_turn_budget as _rc_budget,
+        )
+        if getattr(config.config, "STACKY_CODEX_EFFORT_PARITY_ENABLED", False) \
+                and _rc_valid(_codex_effort_requested):
+            _codex_effort_effective = (_codex_effort_requested or "").strip().lower()
+            log("info", f"effort_override explícito (codex) → {_codex_effort_effective} "
+                        f"(prioridad sobre adaptativo, Plan 264)")
+        # El cap NUNCA sube: codex_turn_budget devuelve <= cap, y 0 sigue siendo 0.
+        if _codex_effort_effective:
+            _codex_adaptive_turns = _rc_budget(_codex_effort_effective, _codex_adaptive_turns)
+            log("info", f"presupuesto de turnos (codex) → {_codex_adaptive_turns} "
+                        f"(cap={config.STACKY_RUNAWAY_MAX_TURNS}, "
+                        f"esfuerzo={_codex_effort_effective})")
```

> **Comportamiento con la flag `STACKY_CODEX_EFFORT_PARITY_ENABLED` en OFF:** el override se ignora y
> queda sólo el adaptativo — y `codex_turn_budget(_adaptive, cap)` con `low` da `cap*0.5`, que es
> **exactamente** el `cap//2` que hacía el código de hoy. La rama OFF es byte-equivalente en
> comportamiento a la actual: eso es lo que el test 6 verifica.

(d) Persistir el trace también en Codex (ver F4 (b)), con
`requested_effort=_codex_effort_requested` y `effective_effort=_codex_effort_effective`.

**2) `Stacky Agents/backend/agent_runner.py:256-264`** — **la línea que falta** (el gemelo exacto del
fix del Plan 196 en `agent_runner.py:350`):

```diff
             _new_exec_id = start_codex_cli_run(
                 ticket_id=ticket_id,
                 ...
                 model_override=model_override,
+                # Plan 264 — BUG GEMELO del que el Plan 196 arregló para claude_code_cli
+                # (agent_runner.py:344-350): esta rama descartaba el effort en silencio,
+                # así que el selector era decorativo en TODA corrida codex_cli.
+                effort_override=effort_override,
             )
```

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_codex_effort_parity.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `inspect.signature(start_codex_cli_run).parameters` | contiene `"effort_override"` |
| 2 | Monkeypatch de `start_codex_cli_run`; `run_agent(runtime="codex_cli", effort_override="high", ...)` | el mock fue llamado con `effort_override == "high"` |
| 3 | idem sin `effort_override` | el mock fue llamado con `effort_override is None` (no rompe llamadores viejos) |
| 4 | `start_codex_cli_run(..., effort_override="max")` con subprocess mockeado | `exec_row.metadata_dict["effort_override"] == "max"` |
| **5** | **[FIX C1]** `cap = 0` (default real) + effort `"max"` | el `max_turns` que recibe `RunLimits` es **`0`** — el run **NO** queda capado en 3 |
| **6** | **[FIX C1]** `cap = 40`, comparar `"low"` vs `"max"` | `budget("low") == 20 < budget("max") == 40`, y **`budget("max") <= 40`** |
| **7** | **[FIX C2]** `STACKY_ADAPTIVE_EFFORT_ENABLED = False` **y** `STACKY_COMPLEXITY_ESTIMATION_ENABLED = False`, con `effort_override="low"` y `cap=40` | el presupuesto es **20**, no 40 ⇒ el effort se honró **fuera** del bloque adaptativo |
| **8** | **[FIX C2]** mismas dos flags OFF, `effort_override="high"`, y se inspecciona el trace | `model_effort.requested_effort == "high"` (el effort **no** se descartó) |
| 9 | Flag `STACKY_CODEX_EFFORT_PARITY_ENABLED = False`, `effort_override="low"`, `cap=40`, sin complejidad | presupuesto `40` (comportamiento pre-264, el override se ignora) |
| 10 | Regresión Plan 196: `run_agent(runtime="claude_code_cli", effort_override="high")` | `start_claude_code_cli_run` sigue recibiendo `effort_override="high"` |

> **Gotcha del repo (SQLITE_LOCKED):** los tests 4, 8 y 10 tocan la DB ⇒ son **flaky bajo el
> shared-cache de pytest**. Corré este archivo **solo**, 8-12 veces seguidas, y usá el helper
> `run_with_retry` si el repo ya lo expone
> (`grep -rn "run_with_retry" "Stacky Agents/backend/tests" | head -3`). Un solo verde no alcanza para
> dar por buena esta fase.
> **Además:** los tests que instancian la app deben forzar `DATABASE_URL` in-memory. Hay archivos en
> este repo que corren contra la **DB REAL** y purgan tickets vivos.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_codex_effort_parity.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_runtime_dispatch.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_runtime_metadata_roundtrip.py" -q
```
(registrar el archivo nuevo en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** 10 passed × 10 corridas consecutivas sin un solo rojo, y los dos tests de
regresión de runtime en verde.

**Flag:** `STACKY_CODEX_EFFORT_PARITY_ENABLED`, default **ON** (no cae en (A) ni (B): sólo afecta
corridas que el operador lanza, y **nunca por encima del cap** que él configuró).
**Impacto por runtime:** Claude sin cambios (ya andaba) · Codex ahora **honra** el effort vía
presupuesto de turnos, siempre bajo el cap · Copilot no aplica y lo declara.
**Trabajo del operador: ninguno.**

---

### F2.5 — [ADICIÓN ARQUITECTO] Centinela ejecutable de paridad: que el bug no pueda volver

**Objetivo.** El bug de Codex no fue "alguien se olvidó una línea": fue que **nada en el sistema podía
detectar** un parámetro de selección aceptado y jamás consumido. F2 arregla el caso; F2.5 arregla la
clase. Cuando aparezca el runtime número 4, esta fase lo obliga a honrar el effort — o a declarar
explícitamente que no puede.

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

Lo mismo en el otro extremo: para cada `ast.Call` a `start_*_run` dentro de `agent_runner.py`, afirmar
que la llamada pasa **ambos** keywords. Ese assert, escrito hoy, sale **rojo contra el `agent_runner.py`
sin el fix de F2** — es su control negativo.

> **Por qué AST y no regex:** la memoria del repo registra que un centinela **textual** sobre flags
> rompió el motor entero. Nunca un grep en masa sobre símbolos: `ast`, siempre.

**Test B — "contrato de honra", parametrizado por `RUNTIMES`.** `@pytest.mark.parametrize("runtime",
runtime_capabilities.RUNTIMES)`: para cada runtime declarado, el mismo escenario:

- `caps = capabilities_for(runtime)`;
- si `caps["supports_effort"]` es `True` ⇒ debe existir un mecanismo declarado: `EFFORT_MODE[runtime]`
  ∈ `{"nativo","presupuesto_turnos"}` **y** el runner correspondiente debe aceptar `effort_override`
  (verificado con `inspect.signature`);
- si es `False` ⇒ `EFFORT_MODE[runtime] == "no_aplica"` **y** `caps["effort_note"]` no vacía (el
  operador tiene que enterarse de por qué no hay selector).

**El valor real:** agregar `"runtime_nuevo"` a `RUNTIMES` sin cablear el effort **rompe el test
automáticamente**, sin que nadie tenga que acordarse de actualizar una lista escrita a mano. La paridad
de 3 runtimes deja de ser una promesa de documento y pasa a ser un invariante ejecutable.

**Test C — anti-regresión del cap.** `codex_turn_budget(e, cap) <= max(cap, 0)` para los 5 efforts y
para `cap ∈ {0, 1, 5, 40}`; y `codex_turn_budget(e, 0) == 0` para los 5. Es el candado de C1 escrito
como propiedad, no como ejemplo.

**Comando de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan264_paridad_ejecutable.py" -q
```
(registrar en las dos `HARNESS_TEST_FILES`).

**Criterio binario.** Los 3 tests verdes **después** de F2, y el Test A **rojo** si se revierte a mano
la línea `effort_override=effort_override` de `agent_runner.py` (verificalo una vez, en un archivo de
scratch, y dejá anotado el resultado en el registro de implementación).
**Flag:** ninguna (es un test). **Trabajo del operador: ninguno.**

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
      4. default_model / default_effort del catálogo        -> origen "default_catalogo"

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
> Es la misma regla que ya respeta `claude_code_cli_runner.py:958-961`.

> **[FIX C11 / backward-compat] La cascada NO cambia lo que ya pasa hoy en los 6 call sites que sí
> eligen** (`api/agents.py:529,825,1036,1200`, `api/devops_agent.py:327`, `api/plans_board.py:227`):
> esos ya pasan `model_override`/`effort_override` explícitos, que son el **paso 1** y siguen ganando.
> Esta fase **no los toca**. El único cambio de comportamiento observable es en los 11 que hoy corren
> "con lo que caiga": pasan a correr con el default del catálogo (o la preferencia del proyecto), que es
> igual o mejor que el azar actual. Declararlo así en el registro de implementación.

**Cableado de los 11 call sites.** En cada uno, reemplazar la llamada desnuda por la resuelta. Patrón
literal a aplicar (ejemplo con `services/pipeline_orchestrator.py:58`, donde `project_name` y `runtime`
**ya están en scope** — verificado):

```diff
+    from services.runtime_capabilities import resolve_run_selection
+    _sel = resolve_run_selection(runtime=runtime, project_name=project_name)
     execution_id = agent_runner.run_agent(
         ...
+        model_override=_sel["model"],
+        effort_override=_sel["effort"],
     )
```

**Los 11 archivos:línea a editar (lista cerrada, re-verificada 2026-07-27):**

| # | Archivo | Línea | Nota |
|---|---|---|---|
| 1 | `Stacky Agents/backend/api/phase6.py` | 192 | |
| 2 | `Stacky Agents/backend/api/phase6.py` | 229 | |
| 3 | `Stacky Agents/backend/api/devops_section_doctor.py` | 171 | |
| 4 | `Stacky Agents/backend/services/doc_documenter.py` | 383 | |
| 5 | `Stacky Agents/backend/services/pipeline_orchestrator.py` | 58 | `runtime` y `project_name` en scope |
| 6 | `Stacky Agents/backend/services/slash_commands.py` | 101 | |
| 7 | `Stacky Agents/backend/services/variant_generator.py` | 188 | **OJO:** es el optimizador del Plan 169 (`_OPTIMIZER_ADO_ID = -9`). Si el archivo tiene cambios sin commitear de otra sesión, **no lo toques** y dejá el ítem pendiente registrado en el cierre. |
| **8** | `Stacky Agents/backend/services/parallel_runs.py` | **58** | **[FIX C4] FALTABA EN EL v1.** Es el fan-out de variantes: ya pasa `model_override=v.get("model")` (el modelo lo define la variante y **manda**), pero **no** pasa `effort_override`. Agregar sólo `effort_override=_sel["effort"]`, dejando el `model_override` de la variante intacto. |
| 9 | `Stacky Agents/backend/services/parallel_runs.py` | 126 | |
| 10 | `Stacky Agents/backend/services/parallel_runs.py` | 169 | |
| 11 | `Stacky Agents/backend/services/macros.py` | 177 | ya pasa **uno** de los dos; completar el que falte |

> **Antes de editar cada uno, corré `git status --porcelain <archivo>`.** Este repo tiene sesiones
> paralelas: si el archivo aparece modificado y el cambio no es tuyo, **saltealo** y anotalo. Nunca
> `git stash`, `git reset` ni `git checkout --` sobre trabajo ajeno.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_run_selection.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | explícito gana a preferencia | `origen_model == "explicito"` |
| 2 | preferencia gana a adaptativo | `origen_effort == "preferencia"` |
| 3 | adaptativo gana a default | `origen_effort == "adaptativo"` |
| 4 | sin nada | `origen_effort == "default_catalogo"` y `effort == default_effort` |
| 5 | explícito `"low"` + adaptativo `"high"` | `effort == "low"` (el humano no se sobreescribe) |
| 6 | runtime `github_copilot` | `effort is None`, `degraded is True` |
| 7 | runtime desconocido | no lanza; cae a defaults |
| 8 | flag prefs OFF | el paso 2 se saltea; `origen_effort` nunca es `"preferencia"` |
| 9 | Cobertura (KPI-2): AST sobre **todas** las llamadas a `run_agent(` | **cada** llamada pasa `model_override=` y `effort_override=` |

> **Test 9 — cómo hacerlo bien:** usá el módulo `ast` de Python, **no** un regex. Parseá cada archivo,
> encontrá los `ast.Call` cuyo `func` termine en `run_agent`, y verificá los `keywords`. Excluí
> `backend/evals/` (ahí `run_agent` es **otra función**: `evals/golden_runner.py:109`,
> `def run_agent(agent_type: str) -> list[GoldenResult]` — verificado) y `backend/tests/`.
> **El universo son 17 llamadas.** 6 ya cumplen, 11 las cablea esta fase.

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

**(a) Persistencia — [FIX C5 + C9].**

> **Lo que el v1 no vio, verificado en el repo:**
> 1. El endpoint `GET/PUT /api/preferences/ui/<key>` **existe** (`preferences.py:74-89`) **pero está
>    gateado** por `STACKY_UI_SAVED_VIEWS_ENABLED` (`config.py:1810`, default `true`) y devuelve
>    **404 `feature_disabled`** si está OFF.
> 2. La clave se valida con `_UI_KEY_RE = ^[A-Za-z0-9._-]{1,128}$`. Un `project_name` con **espacio,
>    acento o paréntesis** (lo normal en este repo) ⇒ **400 `invalid_key`**.
> 3. `api.get/api.put` del frontend **lanzan excepción** en non-2xx ⇒ sin manejo, la UI revienta en
>    vez de degradar.
> 4. La lógica del sub-objeto `ui` vive **en el cuerpo de la ruta**, no en una función reusable, y
>    `_PREFS_FILE = Path("data/preferences.json")` es **relativo al CWD**.

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
    """[FIX C5] Clave válida para _UI_KEY_RE a partir de CUALQUIER nombre de
    proyecto: espacios, acentos y paréntesis se reemplazan por '-'. Determinista
    y estable. `None` -> 'runSelection.__default__'. Resultado <= 128 chars."""

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

**(b) Historial — [FIX C6].** Mover `build_model_effort_trace` (hoy en
`claude_code_cli_runner.py:516-541`) a `runtime_capabilities.py` **conservando el símbolo original como
delegador** (hay callers por nombre, incluidos 2 tests del 212), y llamar a
`_persist_model_effort_trace` también desde `codex_cli_runner`. El trace gana claves; **no pierde
ninguna**:

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
+        "origen_model": origen_model,
+        "origen_effort": origen_effort,
     }
```

> **El v1 mostraba este `return` SIN `downgraded` ni `reason`.** Un modelo menor que aplicara el diff
> literal borraba las dos claves y ponía rojo `test_plan212_requested_vs_effective.py` — que el propio
> F7 corre como regresión. **Leé la firma y el cuerpo reales
> (`claude_code_cli_runner.py:516-541`) antes de tocar**, y agregá los parámetros nuevos
> (`runtime`, `origen_model`, `origen_effort`) como **keyword-only con default**, para no romper a sus
> llamadores actuales.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan264_selection_history.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `save_run_preference` + `load_run_preference` round-trip | devuelve lo guardado |
| 2 | `load_run_preference("proyecto_inexistente")` | `None`, no lanza |
| 3 | `save_run_preference` con effort inválido | se guarda **clampeado**, no crudo |
| 4 | flag `STACKY_RUN_SELECTION_PREFS_ENABLED = False` | `save` devuelve `False` y `load` devuelve `None` |
| **5** | **[FIX C5]** `pref_key_for("Stacky Agents (Pacífico)")` | matchea `^[A-Za-z0-9._-]{1,128}$` y el round-trip completo funciona |
| **6** | **[FIX C5]** `STACKY_UI_SAVED_VIEWS_ENABLED = False` | `save` devuelve `False`, `load` devuelve `None`, **no lanza** |
| 7 | trace de una corrida claude | `tool == "claude_code_cli"` y `effort_mode == "nativo"` |
| 8 | trace de una corrida codex | `tool == "codex_cli"` y `effort_mode == "presupuesto_turnos"` |
| **9** | **[FIX C6]** trace con degradación | `downgraded is True` **y** `reason` presente **y** `requested_effort != effective_effort` |
| 10 | `metadata_dict["model_effort"]` persiste tras `start_codex_cli_run` mockeado | presente, con `tool`, `effort_mode` **y** `downgraded` |

> **Aviso duro:** los tests que escriben preferencias deben monkeypatchear el símbolo exacto
> **`api.preferences._PREFS_FILE`** a un `tmp_path`. `_PREFS_FILE = Path("data/preferences.json")` es
> **relativo al CWD**: sin el monkeypatch, el test escribe en el `data/` de quien lo corra. La memoria
> del repo registra que un test del Plan 216 podía escribir en el **perfil REAL** del operador. Afirmá
> **en el propio test** que el archivo real no existe / no cambió.

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

**(a) Extender el contrato del picker — [FIX C7].**

> **El v1 mostraba un cuerpo de `pickerCapabilities` que NO es el real.** El real
> (`frontend/src/services/modelEffortOptions.ts`) **ya devuelve `note`**, leyendo
> `runtimeCatalog?.effort_note ?? runtimeCatalog?.note ?? ""`. Agregar un `effortNote` sería una
> **segunda copia** del mismo dato — exactamente el pecado que este plan viene a matar. Y `showEfforts`
> se calcula **sin mirar** `effort_mode`, así que el test 2 del v1 (`showEfforts === false` para
> `no_aplica`) nacía **rojo sin ningún cambio de código que lo justificara**.

Diff sobre el cuerpo **real**:

```diff
 export function pickerCapabilities(
   runtimeCatalog: RuntimeModelCatalog | undefined,
-): { showModels: boolean; showEfforts: boolean; note: string } {
+): { showModels: boolean; showEfforts: boolean; note: string; effortMode: string } {
   const showModels = (runtimeCatalog?.models?.length ?? 0) > 0;
-  const showEfforts = (runtimeCatalog?.efforts?.length ?? 0) > 0;
+  // Plan 264 — un runtime que no expone esfuerzo NO debe mostrar el selector:
+  // "prohibido mostrar un selector que no hace nada" (§3.1).
+  const effortMode = runtimeCatalog?.effort_mode ?? "nativo";
+  const showEfforts =
+    (runtimeCatalog?.efforts?.length ?? 0) > 0 && effortMode !== "no_aplica";
   return {
     showModels,
     showEfforts,
     note: runtimeCatalog?.effort_note ?? runtimeCatalog?.note ?? "",
+    effortMode,
   };
 }
```
(y agregar `effort_mode?: string` al tipo `RuntimeModelCatalog` en `frontend/src/api/endpoints.ts`).

En `components/ModelEffortPicker.tsx`, renderizar `caps.note` como texto de ayuda debajo del select de
esfuerzo cuando `caps.effortMode !== "nativo"`. **Reusar `caps.note`, no crear un campo nuevo.**

> **Se conserva la decisión de diseño del Plan 212 F4** (documentada en `ModelEffortPicker.tsx:12-18`):
> **dentro de un runtime que soporta esfuerzo, se ofrecen TODOS los efforts, siempre**, anotando a qué
> degradan. No los escondas ni los deshabilites. Lo que agrega este plan es distinto y no contradice esa
> regla: cuando el runtime **entero** no tiene esfuerzo (`no_aplica`), no se muestra el control. Una cosa
> es "no escondas opciones que existen"; otra es "no muestres un control que no hace nada".

**(b) Reemplazar los 2 selectores hechos a mano:**

| Archivo | Qué sacar | Qué poner |
|---|---|---|
| `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx` | el `<select>` de modelos de `:338-345` y la lógica de `:148-162` (`setActionModel`, `setActionEffort`, `availableEfforts`, `effortsForModel`) | `<ModelEffortPicker catalog={claudeCat} model={actionModel} effort={actionEffort} onChange={...} />` |
| `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx` | la lógica de `:83-100` (`claudeModels`, `claudeEfforts`, `claudeDefaultModel`, el default desde `EMERGENCY_MODEL_CATALOG`) y sus `<select>` | el mismo `<ModelEffortPicker>`, alimentado por `useModelCatalog()` |

> El envío sigue igual: `IncidentResolverModal.tsx:243-244` ya manda `model` y `effort` al backend.
> **No cambies el contrato del POST**, sólo de dónde salen los valores.
> `PlansBoardPage.tsx` — ver **§9.2**: este archivo también lo edita el Plan 263. Leé el protocolo de
> convivencia **antes** de tocarlo.

**(c) Agregar el picker donde no había** (las superficies de F3 que ahora aceptan selección):
`components/devops/DeploymentsSection.tsx`, `components/devops/TriggerPipelineSection.tsx` y
`pages/DocsPage.tsx`, **sólo si esas pantallas efectivamente lanzan una corrida** —
**verificalo leyendo cada archivo antes de agregar nada**. Si una no lanza corridas, no le pongas
selector: un selector que no hace nada es peor que ninguno. Registrá en el cierre cuáles calificaron.

**Tests (vitest, lógica pura):** crear
`Stacky Agents/frontend/src/services/__tests__/modelEffortOptions.plan264.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `pickerCapabilities(undefined)` | no lanza; `effortMode === "nativo"`; `note === ""` |
| 2 | catálogo con `effort_mode: "no_aplica"` y `efforts` no vacío | `showEfforts === false` (**ahora sí hay código que lo produce**) |
| 3 | catálogo con `effort_mode: "presupuesto_turnos"` y `effort_note` | `note` es esa frase, `showEfforts === true` |
| 4 | `buildEffortOptions` con un modelo que degrada | sigue devolviendo **los 5** efforts, con la anotación (regresión del Plan 212 F4) |
| 5 | catálogo **sin** `effort_mode` (deploy viejo) | `effortMode === "nativo"`, `showEfforts` según `efforts.length` (retrocompatible) |

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortOptions.plan264.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelCatalogFallback.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> **Corré cada archivo de test por separado.** La suite completa de vitest de este repo tiene
> contaminación cross-file conocida.
> **No hay RTL ni jsdom:** toda la lógica testeable vive en `.ts` puro. Los `.tsx` (`ModelEffortPicker`,
> `PlansBoardPage`, `IncidentResolverModal`) se validan con `tsc --noEmit` + el smoke manual de R5.

**Criterio binario.** Los 3 comandos exit 0, y el grep de KPI-4:
```bash
grep -rn "<select" --include=*.tsx "Stacky Agents/frontend/src/pages/PlansBoardPage.tsx" "Stacky Agents/frontend/src/components/IncidentResolverModal.tsx" | grep -icE "model|effort"
```
debe dar **0**.

**Restricciones de ratchet (duras):** no aumentar `style={{` en los archivos tocados
(`PlansBoardPage.tsx` está congelado en **3** en `frontend/src/__tests__/uiDebtBaseline.json:136`), y
**cero literales hex nuevos** en CSS (`PlansBoardPage.module.css` congelado en **39**, `:66`). Los
`.tsx` **nuevos** tienen alcance **0** de inline-style: usá CSS module o `ref` + `effect`.

**Flag:** `STACKY_MODEL_PICKER_EVERYWHERE_ENABLED` (ON). El estado de la flag se lee de
**`/api/diag/health`**, que es donde ya viven las flags de UI.
**Impacto por runtime:** el picker se auto-adapta por `effort_mode`: Claude muestra esfuerzo,
Codex lo muestra con la nota de presupuesto de turnos, Copilot **no lo muestra**.
**Trabajo del operador: ninguno** (todo preseleccionado por catálogo/preferencia).

---

### F6 — Frontend: el historial dice qué se usó

**Objetivo.** Que el operador vea, por corrida, herramienta + modelo + esfuerzo pedido y efectivo.

**Archivos a editar (2):**

1. `Stacky Agents/frontend/src/components/ExecutionDetailDrawer.tsx` — mostrar
   `metadata.model_effort` con las claves de F4 (`tool`, `requested_model`, `effective_model`,
   `requested_effort`, `effective_effort`, `effort_mode`). **[FIX C6] Para saber si hubo degradación,
   leé `trace.downgraded` — la clave YA existe y ya la calcula el backend.** No recalcules
   `requested_* !== effective_*` en el frontend: sería una tercera implementación de la misma regla.
   Marcalo con el `ModelDecisionChip` **ya existente** (`components/ModelDecisionChip.tsx`, verificado)
   — no crees un chip nuevo.
2. `Stacky Agents/frontend/src/pages/PlansBoardPage.tsx:480-486` — el historial de corridas ya muestra
   `r.model` (`:482`) y `r.effort` (`:483`); agregar la **herramienta** (`r.tool ?? "—"`) como columna.
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

```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortTrace.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 5 passed, `tsc` exit 0, `grep -c "style={{" PlansBoardPage.tsx` sigue en **3**.
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
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
& $py -m compileall -q "Stacky Agents\backend\services" "Stacky Agents\backend\api"
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortOptions.plan264.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/modelEffortTrace.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

> Los tests `test_plan212_*` son la regresión del plan que construyó la matriz — los **cuatro**, no dos:
> `characterization` y `effort_matrix_parity` importan `CLI_VALID_EFFORTS`, que esta fase convierte en
> alias. Si alguno se pone rojo, este plan rompió su contrato ⇒ arreglalo, **no** lo agregues a una
> allowlist.
> **`test_harness_flags_help` NO está en esta lista a propósito:** tiene **4 fallos ajenos
> preexistentes**. Validá aparte, a mano, que tus 4 flags nuevas tengan `label` y `description` no
> vacíos, y que la descripción no dispare el límite de 240 caracteres de `PlainHelp`.

**[FIX C10] Huella de regresión.** Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` la
huella del defecto que este plan cierra, para que el próximo runtime no lo repita:

- **síntoma:** "el operador elige un esfuerzo y la corrida se comporta igual que sin elegirlo";
- **causa raíz:** un parámetro de selección aceptado por la firma del runner y nunca consumido (o
  consumido dentro de una rama condicional gateada por otra flag);
- **detección:** `tests/test_plan264_paridad_ejecutable.py` (Test A, AST);
- **antecedentes:** Plan 196 (claude_code_cli), Plan 264 (codex_cli).

**Criterio binario.** 17 comandos exit 0 + los 3 greps (KPI-1, KPI-4 y el de `style={{`) + el test AST
de KPI-2 + el de KPI-6.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| **R1** | Ciclo de import: `runtime_capabilities` ← `claude_code_cli_runner` ← `model_catalog._merge_probe` (que ya importa `claude_code_cli_runner` en `model_catalog.py:135`). | **Alta** | Regla única de §5 F1: `runtime_capabilities` importa `model_catalog`/`llm_router`/`config` **sólo dentro de funciones**; los consumidores lo importan a nivel de módulo. El comando de verificación de imports de F1 es obligatorio y va **antes** de seguir. |
| **R2** | **[REESCRITO por C1]** Honrar el effort en Codex altera el presupuesto de turnos. | Media | **El presupuesto sólo baja.** `codex_turn_budget` devuelve `<= cap` siempre, y `0` (sin límite) se mantiene en `0`. El operador nunca gasta más de lo que su `STACKY_RUNAWAY_MAX_TURNS` ya permitía; lo que cambia es que con esfuerzo bajo gasta **menos**. Tests 16-20 de F1 y 5-6 de F2 son el candado. La flag `STACKY_CODEX_EFFORT_PARITY_ENABLED` permite volver atrás sin deploy. |
| **R3** | El `clamp_model` capa Opus a Sonnet y el operador cree que corre Opus. | Media | `clamp_selection` devuelve `degraded: True` + `reason`, y F6 lo muestra con `ModelDecisionChip` leyendo `trace.downgraded`. La degradación deja de ser silenciosa. |
| **R4** | Tocar `variant_generator.py` (call site 7 de F3) pisa trabajo sin commitear de una sesión paralela. | **Alta** (el repo tiene sesiones concurrentes) | `git status --porcelain` antes de cada archivo; si está sucio y no es tuyo, **saltear y registrar**. Prohibido `stash`/`reset`/`checkout --`. La allowlist del test 9 existe justamente para esto (máx. 2). |
| **R5** | Reemplazar el selector de `IncidentResolverModal` rompe el flujo del Dev Resolutor. | Media | El contrato del POST (`:243-244`) **no se toca**. Smoke manual obligatorio: abrir la bandeja, lanzar un resolutor, verificar en el detalle de la ejecución que `model_effort.tool` y `effective_effort` son los elegidos. Sin RTL/jsdom, este smoke **es** el gate de los `.tsx`. |
| **R6** | El test 9 de F3 (AST) se vuelve frágil y bloquea call sites legítimos. | Media | Es AST, no regex (la memoria del repo registra que un centinela textual rompió el motor de flags). Excluye `evals/` y `tests/`. Admite hasta **2** entradas de allowlist, con motivo escrito. |
| **R7** | `test_harness_flags_help` sale rojo. | Media | **Tiene 4 fallos ajenos preexistentes.** No está en la lista de F7. Validá sólo que tus 4 flags nuevas tengan `label`/`description` no vacíos y bajo el límite de 240 chars de `PlainHelp`; no adoptes los rojos ajenos. |
| **R8** | Los tests que tocan la DB salen flaky (`SQLITE_LOCKED`). | **Alta** | Correr **por archivo**, 8-12 veces. Nunca la suite completa. Forzar `DATABASE_URL` in-memory: hay archivos en este repo que corren contra la **DB REAL**. |
| **R9** | **[NUEVO por C5]** La preferencia por proyecto muere en silencio si `STACKY_UI_SAVED_VIEWS_ENABLED` está OFF o el nombre del proyecto tiene caracteres fuera de `[A-Za-z0-9._-]`. | **Alta** sin el fix | `pref_key_for()` sanea la clave (test 5 de F4); `load/save` devuelven `None`/`False` sin lanzar cuando el store está OFF (test 6); el frontend usa `rawGet`/`rawPut` porque un 404 es un caso normal. Degradar a "sin preferencia" **nunca** rompe la corrida. |
| **R10** | **[NUEVO por C11]** Los planes 260/263/265 tocan los mismos archivos y git mergea sin marcar conflicto cuando dos ramas agregan la misma línea de cierre a una estructura existente. | **Alta** | Protocolo de §9.2, y tras cada merge: `compileall` + `tsc --noEmit` + grep de duplicados en `FLAG_REGISTRY` / `_CURATED_DEFAULTS_ON` / `HARNESS_TEST_FILES`. |

---

## 7. Fuera de scope

- **No** se agregan modelos ni runtimes nuevos al catálogo: se consume el que hay.
- **No** se toca `services/adaptive_selector.py` (sigue proponiendo el piso).
- **No** se cambia `CLAUDE_CAP_MODEL` ni la política de `allow_opus` del `llm_router`.
- **No** se toca el `copilot_bridge` ni se le inventa un esfuerzo a GitHub Copilot Pro.
- **No** se persiste preferencia por usuario (mono-operador): la clave es por **proyecto**.
- **No** se migra el catálogo a base de datos: sigue en `config/model_catalog.json`.
- **No** se agrega un selector a pantallas que no lanzan corridas.
- **No** se toca `STACKY_MODEL_PROBE_ENABLED` ni se agrega ningún sondeo, timer o barrido que llame a un
  CLI o a un modelo sin pedido explícito del operador.
- **No** se cambia `STACKY_RUNAWAY_MAX_TURNS` ni su semántica (`0` = sin límite). El effort se mueve
  **dentro** de ese techo, nunca lo modifica.
- **No** se toca la consola full-screen del Plan 265 (ver §9.3).

---

## 8. Orden de implementación y DoD

**Orden (estricto):**

1. **F0** — flags (**3 archivos**).
2. **F1** — `runtime_capabilities.py` + deduplicación. **Verificar imports antes de seguir.**
3. **F2** — paridad de Codex (el bug más grave; independiente de F3).
4. **F2.5** — centinela ejecutable de paridad. **Va inmediatamente después de F2**, porque su Test A usa
   el fix de F2 como control positivo y su reversión como control negativo.
5. **F3** — `resolve_run_selection` + los **11** call sites.
6. **F4** — persistencia + trace en los 3 runtimes.
7. **F5** — un solo selector en el frontend (necesita el `effort_mode` de F1/F4 en el contrato del catálogo).
8. **F6** — historial visible.
9. **F7** — cierre + huella de regresión.

**Definición de Hecho (DoD):**

- [ ] Los 17 comandos de F7 salen **exit 0**, cero rojos.
- [ ] **F0 tocó los 3 archivos** y `test_default_known_only_for_curated` está **verde**.
- [ ] **KPI-1**: el grep de literales de efforts fuera de `runtime_capabilities.py` ⇒ **0**.
- [ ] **KPI-2**: el test AST de F3 pasa sobre las **17** llamadas; a lo sumo **2** entradas de allowlist,
      con motivo escrito.
- [ ] **KPI-3**: `test_plan264_codex_effort_parity.py` verde **10 corridas seguidas**, incluidos los
      tests 5-9 (cap, inversión y flags adaptativas en OFF).
- [ ] **KPI-4**: el grep de `<select>` de modelo/effort en las 2 pantallas ⇒ **0**; superficies extra
      de F5(c) registradas con su veredicto.
- [ ] **KPI-5**: `EFFORT_MODE` cubre los 3 runtimes y el trace se persiste en los 3, **con `downgraded`
      y `reason` intactos**.
- [ ] **KPI-6**: `test_plan264_paridad_ejecutable.py` verde, y verificado a mano que su Test A sale
      **rojo** si se revierte la línea de `agent_runner.py` (resultado anotado).
- [ ] Las 4 flags declaran `default=True`, están en `_CATEGORY_KEYS` **y** en `_CURATED_DEFAULTS_ON`
      (`tests/test_harness_flags.py:467`), y el plan deja escrito por qué ninguna cae en (A) ni (B).
- [ ] Los **5** archivos `tests/test_plan264_*.py` registrados en **ambas** listas `HARNESS_TEST_FILES`
      (`.sh` **y** `.ps1`, sintaxis distinta); `test_harness_ratchet_meta.py` verde.
- [ ] `compileall` de `services/` y `api/` exit 0 (sin ciclos de import).
- [ ] Ningún símbolo público borrado ni clave de dict público perdida: `_clamp_effort_for_model`,
      `CLI_VALID_EFFORTS`, `build_model_effort_trace`, y las claves `downgraded` / `reason` del trace.
- [ ] `style={{` no aumentó en los `.tsx` tocados (PlansBoardPage sigue en **3**); cero literales hex
      nuevos en CSS.
- [ ] Huella agregada a `docs/sistema/error_fingerprints.json`.
- [ ] Smoke manual del Dev Resolutor hecho (R5) y anotado. Sin RTL/jsdom, es el único gate de los `.tsx`.
- [ ] §9.2 respetada: registrado quién tocó `PlansBoardPage.tsx` primero y cómo se resolvió.
- [ ] Registro de implementación agregado al final de **este** documento, con la salida real y los
      call sites que quedaron pendientes por trabajo ajeno.
- [ ] `git commit` con **pathspec explícito** (`git commit -- "<ruta>" ...`). Prohibido `git add -A`,
      `reset`, `amend`, `stash` y `--no-verify`. El `push` es manual.

---

## 9. [ADICIÓN ARQUITECTO] Convivencia con los planes hermanos 260, 263 y 265

Los cuatro planes de esta tanda editan los mismos archivos compartidos y **git mergea sin marcar
conflicto** cuando dos ramas agregan la misma línea de cierre a una estructura existente, dejando un
duplicado silencioso. Esta sección existe para que eso no pase.

### 9.1 Contrato público congelado del 264

Estos símbolos **no cambian de nombre ni de firma** después de F1/F3. 260 y 265 pueden construir contra
ellos sin esperar a que este plan se implemente:

| Símbolo | Módulo | Estabilidad |
|---|---|---|
| `EFFORTS`, `EFFORT_ORDER`, `RUNTIMES`, `EFFORT_MODE` | `services/runtime_capabilities.py` | congelados |
| `is_valid_effort(effort)` | idem | congelada |
| `capabilities_for(runtime) -> dict` | idem | claves del dict congeladas (se pueden **agregar**, nunca quitar) |
| `clamp_selection(runtime, model, effort, *, allow_opus=False) -> dict` | idem | congelada |
| `codex_turn_budget(effort, cap_turns) -> int` | idem | congelada; invariante `<= max(cap,0)`, `0 -> 0` |
| `resolve_run_selection(**kw) -> dict` | idem | congelada |
| `pref_key_for` / `load_run_preference` / `save_run_preference` | idem | congeladas |
| `read_ui_pref` / `write_ui_pref` | `api/preferences.py` | congeladas; **el contrato HTTP no cambia** |
| claves de `metadata_dict["model_effort"]` | trace | `requested_model`, `effective_model`, `requested_effort`, `effective_effort`, `downgraded`, `reason` **se conservan**; `tool`, `effort_mode`, `origen_*` se **agregan** |

**Flags del 264 (no las renombra nadie más):** `STACKY_RUNTIME_CAPABILITIES_ENABLED`,
`STACKY_CODEX_EFFORT_PARITY_ENABLED`, `STACKY_RUN_SELECTION_PREFS_ENABLED`,
`STACKY_MODEL_PICKER_EVERYWHERE_ENABLED`. Verificado: **no colisionan** con las de 260, 263 ni 265.

### 9.2 Frontera de merge, archivo por archivo

| Archivo compartido | Quién más lo toca | Protocolo |
|---|---|---|
| `backend/config.py`, `services/harness_flags.py`, `tests/test_harness_flags.py`, `scripts/run_harness_tests.sh` + `.ps1` | **los 4 planes** | Cada plan agrega su **propio bloque contiguo** con el comentario `# Plan NNN — …` **antes** de sus entradas, y **nunca** reordena las ajenas. Tras cada merge: `compileall`, `tsc --noEmit` y grep de duplicados por key en las 3 estructuras. |
| **`frontend/src/pages/PlansBoardPage.tsx`** | **Plan 263** (lo reescribe para densidad) | **Regla dura: el 263 va PRIMERO.** El 264 toca dos zonas puntuales (el selector de `:148-162`/`:338-345` en F5, y la fila del historial de `:480-486` en F6); el 263 reescribe el layout. Si el 263 ya está en el árbol, el 264 aplica sus dos cambios **sobre el archivo del 263** (el `<ModelEffortPicker>` reemplaza lo que haya quedado como selector, y la columna `tool` se agrega a la grilla densa del 263). Si el 264 va primero, **el 263 debe conservar el `<ModelEffortPicker>` en vez de reconstruir un `<select>`** — y este plan lo declara acá para que el juez del 263 pueda exigirlo. En ningún caso se toca `PlansBoardPage.module.css` más allá de lo que el ratchet permite (congelado en **39** literales hex, `uiDebtBaseline.json:66`; `style={{` congelado en **3**, `:136`). |
| `services/claude_code_cli_runner.py` | Planes **260** y **265** | El 264 toca 3 puntos identificables: `CLI_VALID_EFFORTS` (`:2224`), `build_model_effort_trace` (`:516-541`) y nada más. Si otro plan tocó el archivo, aplicar por **hunk**, nunca reescribir el archivo entero. |
| `services/llm_router.py`, `services/model_catalog.py`, `api/agents.py` | Plan **260** | El 264 **sólo lee** de `llm_router` y `model_catalog` (no los modifica). En `api/agents.py` toca **una línea** (`:425`). |
| `backend/services/plans_board.py` | Planes **263** y **265** | El 264 **no lo toca**. |
| `frontend/src/api/endpoints.ts` | los 4 | El 264 agrega **un campo opcional** (`effort_mode?: string`) al tipo `RuntimeModelCatalog`. Aditivo, sin romper a nadie. |

### 9.3 ¿La consola full-screen del Plan 265 entra en el KPI de "todo punto de uso"?

**No, y queda declarado por qué.** El Plan 265 **crea** una superficie que hoy no existe. Si el KPI-4 de
este plan enumerara superficies futuras, nacería incompleto por construcción y sería imposible de cerrar.

Por eso el KPI-4 del 264 se define sobre el **censo del 2026-07-27** (las 2 pantallas con selector hecho
a mano: `PlansBoardPage` e `IncidentResolverModal`), y **no** sobre "todas las superficies que existan
algún día".

**Lo que el 264 sí hace por el 265** — y es más útil que enumerarlo:

1. Le deja el contrato congelado de §9.1, para que la consola **consuma** `capabilities_for()` +
   `<ModelEffortPicker>` en vez de inventar un tercer selector.
2. Le deja el gate de F2.5 Test B: si la consola del 265 lanza corridas y agrega un runtime a `RUNTIMES`
   sin honrar el effort, **el test rompe solo**.
3. **Ítem explícito para el DoD del Plan 265** (no del 264): "la consola full-screen usa
   `<ModelEffortPicker>` alimentado por `capabilities_for()`; cero `<select>` de modelo/effort propio".
   Este plan lo deja escrito acá para que el juez del 265 pueda exigirlo sin negociar.

---

## 10. Registro de implementación

_(a completar por `implementar-plan-stacky`: salida real de cada comando, call sites que quedaron
pendientes por trabajo ajeno, resultado del control negativo de F2.5 Test A, y veredicto de las
superficies extra de F5(c).)_
