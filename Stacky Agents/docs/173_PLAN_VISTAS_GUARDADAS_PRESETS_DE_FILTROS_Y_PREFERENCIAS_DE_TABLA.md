# Plan 173 — Vistas guardadas: presets nombrados de filtros y preferencias de tabla persistentes

Serie UX Cockpit del Operador (172-175) — plan 2/4 — **v2 CRITICADO** — 2026-07-18

> **Estado:** CRITICADO v2 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode · crítica adversarial aplicada (`criticar-y-mejorar-plan`). APROBADO-CON-CAMBIOS.
>
> ### Changelog v1 → v2 (crítica adversarial)
> - **C1 (IMPORTANTE, correctness):** F5 — el `disabled` de «Siguiente» ahora se guarda con el MISMO predicado que el label (`total != null && filters.runtime === ""`). Antes usaba solo `total != null`: con filtro `runtime` activo el backend devuelve el `COUNT` SQL (pre-filtro-runtime, porque `runtime` se filtra post-paginación en Python, `executions.py:420-422`) y la nav basada en `total` quedaba desalineada respecto de `items.length`. Con runtime activo se cae SIEMPRE a la regla legacy `items.length < limit`.
> - **[ADICIÓN ARQUITECTO] C1b:** la decisión de paginación se extrae a una función PURA `historyPaginationView(...)` en `tablePrefs.ts`, testeada (K5, casos nuevos) en vez de vivir suelta en el JSX verificada solo por smoke. Cierra C1 con cobertura binaria, respetando el principio #12 (lógica pura sin DOM).
> - **C2 (IMPORTANTE, orden/ambigüedad):** F6 — se elimina la conclusión rígida «Hoy NO matchea ⇒ el paso se implementa» (contradecía el orden canónico de la serie, donde el 165 aterriza ANTES del 173). La auto-aplicación de `lastApplied` ahora se gatea por una condición **verificable en runtime e independiente del 165**: solo dispara si los filtros al montar son iguales al DEFAULT de la pantalla (si algo — el 165 o una URL — ya los restauró, 173 NO pisa). El grep de `useLocalStorageState` queda como guía secundaria, no como autoridad.
> - **C3 (MENOR, gotcha):** F1/F2 — se explicita que `saveUiPref`/`hydrateUiPref` usan `fetch` CRUDO, nunca el wrapper `api.*` de `client.ts` (que LANZA en non-2xx, gotcha documentado del repo); el fire-and-forget depende de `.catch(() => {})` sobre `fetch`.
> - **C4 (MENOR, coherencia):** §2.1 — se aclara que el 165 §8 delegó el backlog de `total` en «el plan del arnés veraz» (154); verificado que **154 quedó implementado SIN tocar `executions.py`** (sigue `return jsonify(items)` pelado, `:450`), por lo que el backlog sigue abierto y 173 lo retoma legítimamente (no es duplicación).
> - **C5 (MENOR, UX):** F2 — `useSavedViewsEnabled()` documenta el flash de montaje con flag OFF (render optimista `true` → health resuelve) como aceptable (flag default ON) y ofrece la semilla síncrona opcional.
> - **C6 (MENOR, wording):** R9 — corregido: el store hace read-modify-write del ARCHIVO completo `preferences.json` (patrón de la casa, `preferences.py:49-51`), no «por clave»; último-escribe-gana a nivel archivo; mono-operador ⇒ aceptado sin locking.
> - **v2 · coherencia de serie 2026-07-18 (C-1):** §1 actualizada — 165 F1-F3 YA está mergeado (commits f49588eb→8619acfd) y los filtros ya sobreviven vía `useLocalStorageState` (`ExecutionHistoryPage.tsx:60`); el gating runtime-verificable de F6 (C2) no cambia — sigue siendo la autoridad.
>
> **v1 original:** PROPUESTO (2026-07-18). Pendiente de crítica adversarial.
> **Serie:** 172 Teclado primero · **173 Vistas guardadas (este plan)** · 174 Rendimiento percibido · 175 Peek y acciones rápidas. Cada tema pertenece a UN solo plan: acá NO hay atajos de teclado (172), NO hay virtualización ni prefetch (174), NO hay hover-cards ni menú contextual (175).
> **Toda la evidencia archivo:línea de este doc fue verificada en frío contra el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents` el 2026-07-18.** Los números de línea son referencia de ese día; **toda edición se ancla por TEXTO/símbolo citado, no por número de línea** (hay una sesión paralela conocida commiteando en este mismo árbol).

**Objetivo (1 párrafo):** hoy el operador reconstruye a mano, una y otra vez, las mismas combinaciones de filtros ("errores de los últimos 7 días del developer", "logs ERROR del endpoint X") porque Stacky no tiene el concepto de **vista guardada**: los filtros de Historial y de Logs del Sistema viven en `useState` puro y mueren con F5 o al cambiar de tab (`ExecutionHistoryPage.tsx:54`, `SystemLogsPage.tsx:124-134`), y aunque el plan 165 (**YA IMPLEMENTADO F1-F3**, commits f49588eb→8619acfd) ya los hace sobrevivir vía `useLocalStorageState` (`ExecutionHistoryPage.tsx:60`, verificado 2026-07-18), **dejó explícitamente fuera de su alcance** (su §8 "Fuera de scope") las vistas nombradas, el `sort`/`total` de la tabla de Historial y toda preferencia de columnas. Este plan instala esa capa: (a) un **store de preferencias de UI** clave-valor con persistencia backend (`GET/PUT /api/preferences/ui/<key>` extendiendo el endpoint real `backend/api/preferences.py`) y **fallback transparente a localStorage** si el backend no responde (el patrón exacto que ya usa `frontend/src/services/preferences.ts:38-74`); (b) **presets nombrados de filtros** por pantalla (guardar la vista actual con nombre, aplicar, renombrar, borrar) en Historial, Logs del Sistema y Tablero de Tickets, con el formulario hecho con las primitivas del plan 162; (c) **preferencias de tabla persistentes** (columnas visibles, orden de sort y anchos) para las tablas de Historial (10 columnas) y Logs del Sistema (11 columnas), **retomando el backlog cruzado del 165**: `sort` servidor y `total` real en `GET /api/executions/history` (verificado: hoy el endpoint NO los expone — orden fijo `started_at.desc()` en `executions.py:338` y lista pelada sin total en `:380` — así que se especifica como fase backend aditiva); y (d) **restauración de la última vista** al volver a una pantalla. Todo detrás de la flag `STACKY_UI_SAVED_VIEWS_ENABLED` (default ON), invisible hasta que el operador la usa, sin romper nada de lo existente.

**KPIs binarios (comandos exactos):**

| # | Qué verifica | Comando (cwd indicado) | Esperado |
|---|---|---|---|
| K1 | Store backend `GET/PUT /api/preferences/ui/<key>` + flag default ON + gate OFF→404 | `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` → `venv/Scripts/python.exe -m pytest tests/test_ui_preferences.py -q` | exit 0 |
| K2 | Backlog 165: `sort`/`dir`/`include_total` en `/api/executions/history`, backward-compatible | mismo cwd → `venv/Scripts/python.exe -m pytest tests/test_executions_history_sort_total.py -q` | exit 0 |
| K3 | La flag quedó curada (`_CURATED_DEFAULTS_ON`) y categorizada (`_CATEGORY_KEYS`) | mismo cwd → `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q` | exit 0 |
| K4 | Lógica pura de presets (CRUD, sanitización, vista activa) | `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` → `npx vitest run src/services/__tests__/savedViews.test.ts` | exit 0 |
| K5 | Lógica pura de preferencias de tabla (visibilidad, sort, anchos) **+ decisión de paginación `historyPaginationView` (C1b)** | mismo cwd → `npx vitest run src/services/__tests__/tablePrefs.test.ts` | exit 0 |
| K6 | Tipos verdes en todo el frontend | mismo cwd → `npx tsc --noEmit` | exit 0 |
| K7 | Los 2 tests backend nuevos quedaron registrados en el ratchet de cobertura | desde la RAÍZ del repo → `grep -c "test_ui_preferences.py\|test_executions_history_sort_total.py" "Stacky Agents/backend/scripts/run_harness_tests.sh"` | `2` |

**KPIs de impacto (proyectados, verificables por observación manual):**

| Métrica | Hoy (recuento en frío 2026-07-18) | Con el plan |
|---|---|---|
| Pantallas con presets nombrados de filtros | **0** | **3** (Historial, Logs del Sistema, Tablero de Tickets) |
| Tablas con columnas visibles / anchos persistentes | **0** | **2** (Historial 10 col., Logs del Sistema 11 col.) |
| Sort de columnas servidor en Historial | **0** (orden fijo `started_at.desc()`, `executions.py:338`) | **3 columnas** (Inicio, Estado, Agente) con asc/desc |
| `total` real en la paginación de Historial | **NO** (muestra `offset+1–offset+items.length`, `ExecutionHistoryPage.tsx:244-246`) | **SÍ** («X–Y de N») cuando el backend nuevo responde |
| Última vista restaurada al volver a una pantalla | **NO** (todo vuelve a default al montar) | **SÍ** (preset `lastApplied` re-aplicado; cede ante URL/165) |
| Clicks para reconstruir un filtro habitual de 4 campos | 4+ selects cada vez | 1 (aplicar preset) |

---

## 2. Por qué ahora / gap que cierra (evidencia verificada)

### 2.1 El backlog del plan 165 es explícitamente NUESTRO

El plan 165 (`docs/165_PLAN_CONTRATO_DE_URL_DEEP_LINKS_Y_ESTADO_PERSISTENTE.md`, CRITICADO v2) hace sobrevivir los filtros a F5 vía `useLocalStorageState` y los refleja en el querystring, pero su §8 "Fuera de scope" declara textualmente: *"**`sort` y `total` de la tabla de Historial.** El endpoint de historial no expone hoy un `total` real ni orden configurable. […] El `sort` de columnas es otro backlog de UI aparte."* Ese backlog cruzado aterriza acá. Verificación directa del endpoint (`backend/api/executions.py`, función `executions_history`, `:283-380`):

- **Orden fijo:** `q.order_by(AgentExecution.started_at.desc()).offset(offset).limit(limit)` (`:337-342`). No hay parámetro `sort` ni `dir`.
- **Sin total:** la respuesta es `jsonify(items)` — **lista pelada** (`:380`). El frontend pagina a ciegas: `«{filters.offset + 1}–{filters.offset + items.length}»` y deshabilita "Siguiente" solo cuando `items.length < filters.limit` (`ExecutionHistoryPage.tsx:244-253`).
- **Wrinkle preexistente que condiciona el diseño:** el filtro `runtime` se aplica **en Python DESPUÉS de la paginación** (`:350-352`, porque `runtime` vive en `metadata_json`, no en una columna). Cualquier `total` por `COUNT` no puede descontar ese filtro. La fase F5 lo codifica como limitación documentada en vez de fingir precisión.

⇒ **Conclusión verificada:** retomar sort/total **requiere cambio backend**; se especifica como fase (F5), aditiva y backward-compatible.

> **Coherencia con el destino original del backlog (C4).** El 165 §8 no solo declaró el `total` fuera de su alcance: sugirió que «viaja gratis cuando el plan del arnés veraz toque `backend/api/executions.py`». Ese plan es el **154** (arnés veraz), hoy IMPLEMENTADO. **Verificación en frío 2026-07-18:** `executions_history` sigue devolviendo la lista pelada (`return jsonify(items)`, `executions.py:450`) — 154 NO tocó ese retorno. Por lo tanto el backlog sigue ABIERTO y 173 lo retoma sin duplicar trabajo de 154. Esta nota existe para que la crítica/supervisión no lo confunda con una toma de alcance ajeno.

### 2.2 El patrón de store de preferencias YA EXISTE — se extiende, no se inventa

- **Backend:** `backend/api/preferences.py` (blueprint `preferences`, url_prefix `/preferences`, registrado en `backend/api/__init__.py:30`) ya persiste preferencias de usuario en **`data/preferences.json`**: `GET /api/preferences` devuelve el objeto completo y `PUT /api/preferences` hace merge **solo de claves permitidas** (`_ALLOWED_KEYS`, `:16-22`) con helpers `_read()` (`:25-29`, tolerante a archivo ausente/corrupto) y `_write()` (`:32-36`). Este plan agrega dos rutas al MISMO blueprint (`GET/PUT /api/preferences/ui/<key>`) guardando bajo una clave raíz nueva `"ui"` — el PUT legacy no puede pisarla porque filtra a `_ALLOWED_KEYS` (`:48-50`).
- **Frontend:** `frontend/src/services/preferences.ts` ya implementa EXACTAMENTE el contrato "localStorage + sync backend con fallback transparente": `initPreferences()` hidrata desde el backend al arrancar y si el backend no está *"se usan los valores actuales de localStorage"* (`:38-58`); `_pushToBackend()` persiste fire-and-forget con `.catch(() => { /* backend offline — no-op */ })` (`:61-74`). El módulo nuevo `uiPrefs.ts` replica este patrón con claves namespaced.
- **Precedente de persistencia de UI por pantalla:** `TicketBoard.tsx` ya persiste `search`/`onlyPending`/`viewMode` (`:759-761`) y `showAll` (`:784`) vía `useLocalStorageState` — la materia prima exacta de un preset nombrado del tablero.

### 2.3 Las superficies concretas (elegidas leyendo el código)

| Pantalla | Filtros preseteables (símbolos reales) | Tabla con preferencias |
|---|---|---|
| **Historial** — `frontend/src/pages/ExecutionHistoryPage.tsx` | `Filters` `:27-34`: `agent_type`, `runtime`, `status`, `days` (más `limit`/`offset` que NO se presetean) | SÍ — 10 columnas: Inicio, Agente, Runtime, Modelo, Estado, Duración, Costo, Prompt, Archivos, Ticket (`:168-181`) |
| **Logs del Sistema** — `frontend/src/pages/SystemLogsPage.tsx` | 8 filtros `:124-133`: `level`, `source`, `action`, `q`, `execution_id`, `ticket_id`, `from`, `to`; `offset` aparte `:134` | SÍ — 11 columnas: Level, Timestamp, Source, Action, Exec ID, Ticket, User, Method, Endpoint, Status, Duration (`:301-311`) |
| **Tablero de Tickets** — `frontend/src/pages/TicketBoard.tsx` | `search`, `onlyPending`, `viewMode` (`:759-761`), `showAll` (`:784`) | NO (vista graph/list, sin tabla clásica) — solo presets |

### 2.4 El sustrato de flags, formularios y salud ya está (prior art que NO se duplica)

- **Flags:** `FlagSpec` en `backend/services/harness_flags.py:21-41`; nota normativa `:331`: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS` (arriba) o el test [rompe]"*; categoría existente `interfaz_ui` (`:109-111`) es la correcta para esta flag. El set curado `_CURATED_DEFAULTS_ON` vive en `backend/tests/test_harness_flags.py:467` y el patrón triple canónico está documentado en `backend/tests/test_context_contract_flags.py:3`: *"FlagSpec default=True + _CURATED_DEFAULTS_ON + [config.py]"*. Default efectivo en `config.py` — patrón exacto en `config.py:543-545` (`STACKY_COST_CENTER_ENABLED`).
- **La flag queda configurable desde la UI de Settings sin trabajo extra:** el panel de flags del arnés es registry-driven — `GET /api/harness-flags` (`backend/api/harness_flags.py:71`) y `PUT /api/harness-flags` (`:117`) sirven TODO el `FLAG_REGISTRY`; registrar el `FlagSpec` la hace aparecer sola en Settings→Arnés.
- **Mecanismo EXACTO de lectura de la flag por el frontend (plan 139, §"Mecanismo EXACTO de lectura de la flag por el frontend"):** campo ADITIVO en el retorno de `GET /api/diag/health` — el precedente literal es `"shell_v2_enabled": bool(getattr(_config.config, "STACKY_UI_SHELL_V2_ENABLED", False))` en `backend/api/diag.py:411`, junto a `"local_llm_enabled"` (`:410`) — y un fetch de montaje en el frontend. Este plan agrega `"saved_views_enabled"` por el mismo patrón (F0) y lo consume vía un hook con caché de módulo (F2), sin tocar `App.tsx` (archivo caliente de la sesión paralela).
- **Formularios:** las 5 primitivas del plan 162 están implementadas y exportadas por el barrel: `Field`/`fieldControlProps`/`firstErrorFieldId`, `Input`, `Select`, `Checkbox` (`frontend/src/components/ui/index.ts:25-34`). El formulario "guardar vista" las usa (obligatorio: el `formDebtRatchet` del 162 cuenta tags crudos nuevos como deuda).
- **Fixture backend canónico:** `tests/test_executions_history.py:32-45` (fixture `_app`/`client` con `STACKY_EXECUTION_HISTORY_ENABLED=true` + `create_app()` + `test_client`) y su seeder `_seed_exec` (`:50-90`) — F5 lo replica. Para endpoints sin DB, el patrón fresco es `tests/test_spa_index_no_cache.py:23-51`.

---

## 3. Principios y guardarraíles (no negociables, codificados acá)

1. **Cero trabajo extra para el operador.** Todo default ON e invisible: las barras de presets y el menú de columnas aparecen solos; usarlos es opcional. Sin pasos manuales nuevos, sin archivo de config nuevo, sin migración (el store arranca vacío y `data/preferences.json` ya existe o se crea solo, `preferences.py:32-36`). **Ninguna de las 4 excepciones duras aplica**, revisadas una por una: (1) *bypass de revisión humana* — no publica ni ejecuta nada hacia afuera; (2) *destructiva/irreversible* — lo único que se borra es un preset propio de UI, recreable en 5 segundos y SIEMPRE con confirmación previa; (3) *prerequisito no garantizado* — usa `localStorage` y `data/preferences.json`, ambos presentes en toda instalación default; (4) *reduce seguridad* — no abre superficie nueva (el store valida clave y tamaño, F1).
2. **Human-in-the-loop innegociable.** La única acción con efecto destructivo (borrar/sobrescribir un preset) pide confirmación explícita: con el diálogo canónico del plan 164 si ya está implementado; si no, `window.confirm` (patrón vigente en la app) como degradación declarada. Nada se ejecuta ni publica solo.
3. **Paridad de 3 runtimes por vacuidad, declarada igual ítem por ítem.** Presets, preferencias de tabla, store y sort/total son features del **dashboard** (frontend + un endpoint Flask): idénticas con Codex CLI, Claude Code CLI y GitHub Copilot Pro porque no tocan el camino de ejecución/publicación de ningún runtime. Cada fase lo declara con su fallback.
4. **Reusar, no reinventar.** Store = extensión de `api/preferences.py` (patrón real citado). Sync = patrón de `services/preferences.ts`. Persistencia local = mismo espíritu que `useLocalStorageState` (que NO se modifica). Formularios = primitivas 162. Formato humano = `services/format.ts` del 161 si se muestra fecha/costo (este plan no formatea valores nuevos; el `total` es un entero que se interpola con `String(total)` — sin `Intl`, el ratchet anti-Intl del 161 no se toca).
5. **Backward-compatible en ambos sentidos.** `GET /api/executions/history` sin `include_total` responde EXACTAMENTE la lista pelada de hoy (ningún consumidor existente se rompe); el frontend nuevo tolera un backend viejo (respuesta array ⇒ `total: null` ⇒ la paginación se ve como hoy; `sort` ignorado ⇒ orden default). El PUT legacy de `/api/preferences` sigue intacto.
6. **Dependencias blandas con los hermanos y con 165 — degradar, no romper.** Aplicar un preset ES aplicar estado local (`setFilters`); si el 165 ya está implementado, SU efecto de reflejo filtros→querystring serializa la URL solo (el preset "navega a la URL del contrato" transitivamente, sin importar `routes.ts`); si no está, el preset funciona igual sin URL. La restauración de última vista cede ante la precedencia URL-manda del 165 (§F6). Si 164 no está: `window.confirm`. 172/174/175 no son prerequisito de nada.
7. **Mono-operador sin auth.** Un solo namespace de preferencias, sin `user_id`, sin RBAC (`current_user` es un header sin validar — no protege nada y no se usa acá).
8. **No degradar performance.** El store se lee 1 vez por montaje de pantalla (localStorage síncrono + 1 GET en background); guardar es fire-and-forget; el sort servidor reutiliza la query existente con un `order_by` distinto; `COUNT` solo cuando `include_total=1`. Nada de polling nuevo.
9. **Ratchets del repo se respetan, no se gamean.** `.tsx` nuevos con CERO `style={{}}` (uiDebtRatchet, plan 138): anchos de columna aplicados por **ref + effect imperativo**. Cero tags crudos `<input>/<select>/<label>` en archivos nuevos (formDebtRatchet, plan 162): solo primitivas `ui/`. Tests backend nuevos registrados en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh:20`, comentario `:8-9`: la lista es un ratchet que solo crece).
10. **Flags backend SIEMPRE por la instancia.** En módulos `api/*`, `config` es el MÓDULO; la instancia es `config.config`. Patrón obligatorio (el mismo de `diag.py:201,411`): `import config as _config` + `getattr(_config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True)`. `getattr(config, FLAG)` sobre el módulo devuelve siempre el default y mata el branch OFF (gotcha documentado del repo).
11. **Sesión paralela viva en este árbol.** Pre-flight OBLIGATORIO por archivo antes de editar: `git status -- "<ruta>"`; si hay WIP ajeno en ese archivo ⇒ STOP y reportar al orquestador. `backend/scripts/run_harness_tests.sh` y `backend/app.py` figuran modificados HOY por la otra sesión. Staging quirúrgico por path explícito; el implementador NO commitea (lo hace el orquestador).
12. **Tests sin DOM.** `@testing-library/react` y `jsdom` NO están en `frontend/package.json` (gap estructural conocido): toda la lógica de este plan vive en módulos `.ts` puros testeables (`savedViews.ts`, `tablePrefs.ts`) y los componentes son cáscaras finas verificadas por `tsc` + smoke manual documentado.

---

## 4. Fases

> **Convenciones de comandos.** Backend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` y correr `venv/Scripts/python.exe -m pytest tests/<archivo>.py -q` — SIEMPRE por archivo, NUNCA la suite entera (contaminación cross-file conocida). Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` y `npx vitest run src/<ruta>` — por archivo, ídem. `npx tsc --noEmit` al cerrar cada fase que toque `.ts/.tsx`.
> **Orden:** F0 → F1 → F2 → F3 → F4 → F5 → F6 (cada una autocontenida y verificable sola; F3/F4 consumen F2; F5 es independiente de F3/F4 pero posterior a F0).

---

### F0 — La flag `STACKY_UI_SAVED_VIEWS_ENABLED` (default ON) + exposición al frontend

**Objetivo (1 frase):** registrar la flag con el patrón triple canónico (FlagSpec + `_CURATED_DEFAULTS_ON` + `config.py`) y exponerla al frontend como campo aditivo de `GET /api/diag/health`. **Valor:** un único interruptor, visible y toggleable en Settings→Arnés sin escribir UI nueva, gobierna todo el plan.

**Archivos a editar (4) y crear (1):**

1. **`backend/services/harness_flags.py`** — agregar al `FLAG_REGISTRY` (anclar junto a las flags de UI existentes; la nota `:331` exige el paso 2):

```python
FlagSpec(
    key="STACKY_UI_SAVED_VIEWS_ENABLED",
    type="bool",
    label="Vistas guardadas y preferencias de tabla",
    description="Presets nombrados de filtros por pantalla y columnas/sort/anchos persistentes en las tablas (plan 173).",
    group="global",
    default=True,
),
```

2. **`backend/services/harness_flags.py`** — en `_CATEGORY_KEYS` (`:117`), agregar `"STACKY_UI_SAVED_VIEWS_ENABLED"` a la tupla de la categoría **`"interfaz_ui"`** (la categoría ya existe, `:109-111`; NO crear categoría nueva).
3. **`backend/config.py`** — atributo con default efectivo ON, patrón EXACTO de `STACKY_COST_CENTER_ENABLED` (`:543-545`):

```python
# ── Plan 173 — Vistas guardadas y preferencias de tabla ────────────────────
# Default ON (ninguna de las 4 excepciones duras aplica: no publica, no
# destruye datos de negocio, sin prerequisitos, no reduce seguridad).
STACKY_UI_SAVED_VIEWS_ENABLED: bool = os.getenv(
    "STACKY_UI_SAVED_VIEWS_ENABLED", "true"
).strip().lower() == "true"
```

4. **`backend/tests/test_harness_flags.py`** — agregar `"STACKY_UI_SAVED_VIEWS_ENABLED"` al set `_CURATED_DEFAULTS_ON` (`:467`). Sin este paso, `test_default_known_only_for_curated` (`:743-757`) rompe — es el gate, no un opcional.
5. **`backend/api/diag.py`** — en el dict de retorno de `health()`, inmediatamente después de `"shell_v2_enabled"` (`:411`), agregar el campo aditivo:

```python
"saved_views_enabled": bool(getattr(_config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True)),  # Plan 173
```

6. **NUEVO `backend/tests/test_ui_preferences.py`** — arranca acá con los tests de flag (F1 le suma los del store; es UN solo archivo para las dos fases):

| Test | Qué afirma |
|---|---|
| `test_flag_registrada_default_on` | `FLAG_REGISTRY` contiene un spec con `key == "STACKY_UI_SAVED_VIEWS_ENABLED"`, `type == "bool"`, `default is True`. |
| `test_flag_categorizada_en_interfaz_ui` | `"STACKY_UI_SAVED_VIEWS_ENABLED" in _CATEGORY_KEYS["interfaz_ui"]`. |
| `test_config_default_on` | `import config` → `config.config.STACKY_UI_SAVED_VIEWS_ENABLED is True` (sin la env var seteada). |
| `test_health_expone_saved_views_enabled` | `GET /api/diag/health` → 200 y `body["saved_views_enabled"] is True` (fixture de app: replicar `tests/test_spa_index_no_cache.py:23-51`, sin necesidad de dist real si el fixture solo pega a `/api/diag/health`). |

7. **`backend/scripts/run_harness_tests.sh`** — agregar `tests/test_ui_preferences.py` al array `HARNESS_TEST_FILES` (`:20`). **Pre-flight obligatorio:** este archivo tiene WIP de la sesión paralela HOY — `git status -- "Stacky Agents/backend/scripts/run_harness_tests.sh"` primero; si sigue con WIP ajeno, agregar la línea igual (es un array aditivo, una línea propia) y declarar la coexistencia en el resumen.

**TDD:** escribir los 4 tests ANTES de tocar `harness_flags.py`/`config.py`/`diag.py`; correr (rojos por flag inexistente); implementar; correr verdes.

**Criterio de aceptación BINARIO:** `venv/Scripts/python.exe -m pytest tests/test_ui_preferences.py -q` → exit 0 **y** `venv/Scripts/python.exe -m pytest tests/test_harness_flags.py -q` → exit 0.

**Flag:** `STACKY_UI_SAVED_VIEWS_ENABLED` (la de este plan), default **ON**; queda configurable desde Settings→Arnés automáticamente porque el panel es registry-driven (`GET/PUT /api/harness-flags`, `api/harness_flags.py:71,117`). **Runtimes:** flag de UI del dashboard, idéntica con los 3 runtimes; fallback: OFF ⇒ la app se ve y se comporta EXACTAMENTE como hoy. **Trabajo del operador: ninguno.**

---

### F1 — Store backend: `GET/PUT /api/preferences/ui/<key>` sobre `data/preferences.json`

**Objetivo (1 frase):** dar persistencia server-side a las preferencias de UI extendiendo el blueprint real `api/preferences.py` con dos rutas mínimas clave-valor bajo la clave raíz `"ui"`. **Valor:** las vistas sobreviven a limpiar el navegador / cambiar de máquina, sin tabla nueva ni blueprint nuevo.

**Archivo a editar (1):** `backend/api/preferences.py`. **Sin cambios en `api/__init__.py`** (el blueprint ya está registrado, `:30`) **ni en `models.py`/`db.py`** (persistencia en el JSON existente, mismo trade-off mono-operador que las preferencias de avatares). **Decisión explícita:** `_PREFS_FILE = Path("data/preferences.json")` es relativa al CWD del backend (preexistente, `:14`); este plan NO la migra a `runtime_paths` — fuera de scope, no lo "arregles".

**Diff ilustrativo (agregar al final del archivo; los helpers `_read`/`_write` existentes se reusan tal cual):**

```python
# ── Plan 173 — Store clave-valor de preferencias de UI (vistas guardadas) ──
import re
import config as _config  # instancia = _config.config (¡no el módulo!)

_UI_STATE_KEY = "ui"                                   # clave raíz dentro de preferences.json
_UI_KEY_RE = re.compile(r"^[a-z][a-z0-9._-]{0,127}$", re.IGNORECASE)
_UI_VALUE_MAX_BYTES = 65536                            # 64 KB por clave: presets son chicos


def _saved_views_enabled() -> bool:
    return bool(getattr(_config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", True))


@bp.get("/ui/<key>")
def get_ui_preference(key: str):
    if not _saved_views_enabled():
        return jsonify({"error": "feature_disabled", "feature": "STACKY_UI_SAVED_VIEWS_ENABLED"}), 404
    if not _UI_KEY_RE.match(key):
        return jsonify({"error": "invalid_key"}), 400
    value = _read().get(_UI_STATE_KEY, {}).get(key)     # ausente ⇒ None ⇒ null en JSON
    return jsonify({"key": key, "value": value})


@bp.put("/ui/<key>")
def put_ui_preference(key: str):
    if not _saved_views_enabled():
        return jsonify({"error": "feature_disabled", "feature": "STACKY_UI_SAVED_VIEWS_ENABLED"}), 404
    if not _UI_KEY_RE.match(key):
        return jsonify({"error": "invalid_key"}), 400
    payload = request.get_json(force=True, silent=True)
    if not isinstance(payload, dict) or "value" not in payload:
        return jsonify({"error": "value_required"}), 400
    value = payload["value"]
    raw = json.dumps(value, ensure_ascii=False)
    if len(raw.encode("utf-8")) > _UI_VALUE_MAX_BYTES:
        return jsonify({"error": "value_too_large", "max_bytes": _UI_VALUE_MAX_BYTES}), 413
    data = _read()
    ui = data.get(_UI_STATE_KEY, {})
    if not isinstance(ui, dict):                        # tolerancia a corrupción manual
        ui = {}
    ui[key] = value
    data[_UI_STATE_KEY] = ui
    _write(data)
    return jsonify({"ok": True})
```

**Casos borde codificados:** clave inválida (`../x`, vacía, >128 chars, no-ASCII) → 400 `invalid_key`; body sin `"value"` → 400 `value_required`; valor >64 KB → 413 `value_too_large`; clave nunca escrita → 200 `{"key", "value": null}` (NO 404: el frontend distingue "no hay preferencia" sin manejar errores); flag OFF → 404 `feature_disabled` (patrón `executions.py:291-292`); `preferences.json` corrupto → `_read()` ya devuelve `{}` (`:28-29`), el store arranca vacío sin romper; el `PUT /api/preferences` legacy NO puede pisar `"ui"` (filtra a `_ALLOWED_KEYS`, `:48-50`).

**Tests primero (TDD)** — agregar a `backend/tests/test_ui_preferences.py` (fixture: `monkeypatch.setattr` de `api.preferences._PREFS_FILE` a `tmp_path / "preferences.json"` + el fixture de app/cliente de F0):

| Test | Qué afirma |
|---|---|
| `test_put_get_roundtrip` | `PUT /api/preferences/ui/views.history` con `{"value": {"views": [{"name": "errores 7d", "filters": {"status": "error", "days": "7"}}], "lastApplied": "errores 7d"}}` → 200 `{"ok": true}`; `GET` de la misma clave → 200 con el MISMO value (deep-equal). |
| `test_get_clave_ausente_value_null` | `GET /api/preferences/ui/views.nunca_escrita` → 200 y `body["value"] is None`. |
| `test_clave_invalida_400` | `GET` y `PUT` con key `"..x"` (falla la regex por empezar con punto) → 400 `invalid_key`; `PUT` con body `{}` → 400 `value_required`. |
| `test_valor_gigante_413` | `PUT` con `{"value": "x" * 70000}` → 413 `value_too_large`. |
| `test_flag_off_404` | `monkeypatch.setattr(_config.config, "STACKY_UI_SAVED_VIEWS_ENABLED", False, raising=False)` → `GET` y `PUT` → 404 `feature_disabled`. |
| `test_put_legacy_no_pisa_ui` | Escribir `ui` vía `PUT /api/preferences/ui/k`; luego `PUT /api/preferences` con `{"pinnedAgents": [], "ui": {"k": "HACK"}}` → el `GET /api/preferences/ui/k` sigue devolviendo el valor original (la clave `ui` no está en `_ALLOWED_KEYS`). |

**Criterio de aceptación BINARIO:** `venv/Scripts/python.exe -m pytest tests/test_ui_preferences.py -q` → exit 0 (K1).

**Flag:** `STACKY_UI_SAVED_VIEWS_ENABLED` (gate 404 en ambas rutas). **Runtimes:** endpoint del dashboard, ninguno de los 3 runtimes lo consume; paridad por vacuidad. **Fallback:** backend caído/flag OFF ⇒ el frontend opera 100% con localStorage (F2). **Trabajo del operador: ninguno.**

---

### F2 — Núcleo frontend puro: `savedViews.ts` + `tablePrefs.ts` + `uiPrefs.ts` (I/O)

**Objetivo (1 frase):** implementar TODA la lógica de presets y preferencias de tabla como funciones puras testeables sin DOM, más un módulo fino de I/O (localStorage + backend, fallback transparente). **Valor:** los componentes de F3/F4 quedan como cáscaras; los tests fijan el comportamiento sin RTL/jsdom.

**Archivos NUEVOS (5):**
- `frontend/src/services/savedViews.ts` (puro)
- `frontend/src/services/tablePrefs.ts` (puro)
- `frontend/src/services/uiPrefs.ts` (I/O: localStorage + fetch; único con side-effects)
- `frontend/src/services/__tests__/savedViews.test.ts`
- `frontend/src/services/__tests__/tablePrefs.test.ts`

**Paso 1 — `savedViews.ts` (100% puro, sin `window`):**

```ts
// frontend/src/services/savedViews.ts — Plan 173 F2
export interface SavedView { name: string; filters: Record<string, string> }
export interface SavedViewsState { views: SavedView[]; lastApplied: string | null }

export const EMPTY_SAVED_VIEWS: SavedViewsState = { views: [], lastApplied: null };
export const MAX_VIEWS_PER_SCREEN = 20;
export const MAX_VIEW_NAME_LEN = 60;

/** Mensaje de error para validación inline (plan 162) o null si es válido.
 *  Reglas: trim; no vacío; <= 60 chars; único case-insensitive (salvo excludeName,
 *  para permitir "renombrar sin cambiar"). */
export function validateViewName(name: string, state: SavedViewsState, excludeName?: string): string | null;
// "El nombre no puede estar vacío" | "Máximo 60 caracteres" |
// "Ya existe una vista con ese nombre" | (views.length >= 20 y no reemplaza) "Máximo 20 vistas por pantalla" | null

/** Solo claves con valor no vacío, ordenadas alfabéticamente (comparación estable). */
export function normalizeFilters(filters: Record<string, string>): Record<string, string>;

/** Alta o reemplazo por nombre (trim). Reemplazar el propio nombre NO cuenta contra el cap. */
export function upsertView(state: SavedViewsState, name: string, filters: Record<string, string>): SavedViewsState;

export function renameView(state: SavedViewsState, oldName: string, newName: string): SavedViewsState; // actualiza lastApplied si apuntaba a oldName
export function deleteView(state: SavedViewsState, name: string): SavedViewsState;                       // limpia lastApplied si apuntaba ahí

/** null si no existe; si existe: state con lastApplied=name + los filtros normalizados a aplicar. */
export function applyView(state: SavedViewsState, name: string): { state: SavedViewsState; filters: Record<string, string> } | null;

/** Nombre de la vista cuyos filtros normalizados son deep-equal a los actuales, o null. */
export function computeActiveView(state: SavedViewsState, currentFilters: Record<string, string>): string | null;

/** Shape-merge tolerante contra drift (mismo espíritu que 165 C5): cualquier `unknown`
 *  (respuesta backend, localStorage viejo, null) → SavedViewsState válido. Entradas sin
 *  name string no vacío o sin filters objeto-de-strings se DESCARTAN; cap 20; lastApplied
 *  que no matchea ninguna vista → null. */
export function sanitizeSavedViews(raw: unknown): SavedViewsState;

// ── Codec del Tablero de Tickets (bool/enum → Record<string,string>) ──
export interface TicketBoardViewState { search: string; onlyPending: boolean; showAll: boolean; viewMode: string }
export function ticketBoardStateToFilters(s: TicketBoardViewState): Record<string, string>; // bool ⇒ "1"/"" ; viewMode tal cual
export function filtersToTicketBoardState(f: Record<string, string>): TicketBoardViewState; // ausente ⇒ default: search "", onlyPending false, showAll true, viewMode "graph" (defaults reales de TicketBoard.tsx:759-784)
```

**Paso 2 — `tablePrefs.ts` (100% puro):**

```ts
// frontend/src/services/tablePrefs.ts — Plan 173 F2
export interface ColumnDef { id: string; label: string; sortKey?: string }  // sortKey = clave servidor (solo columnas sorteables)
export interface TableSort { column: string; dir: "asc" | "desc" }
export interface TablePrefs { visibleColumns: string[] | null; sort: TableSort | null; widths: Record<string, number> }

export const EMPTY_TABLE_PREFS: TablePrefs = { visibleColumns: null, sort: null, widths: {} };
export const MIN_COL_WIDTH = 40;
export const MAX_COL_WIDTH = 800;

// Catálogos de columnas — ids estables, orden = orden visual actual de cada tabla.
export const HISTORY_COLUMNS: ColumnDef[] = [
  { id: "inicio", label: "Inicio", sortKey: "started_at" },
  { id: "agente", label: "Agente", sortKey: "agent_type" },
  { id: "runtime", label: "Runtime" },
  { id: "modelo", label: "Modelo" },
  { id: "estado", label: "Estado", sortKey: "status" },
  { id: "duracion", label: "Duración" },       // NO sorteable: duration_ms se calcula por fila (executions.py duration_ms())
  { id: "costo", label: "Costo" },             // NO sorteable: cost_usd vive en metadata_json, no en columna
  { id: "prompt", label: "Prompt" },
  { id: "archivos", label: "Archivos" },
  { id: "ticket", label: "Ticket" },
];
export const SYSLOG_COLUMNS: ColumnDef[] = [ /* 11 ids en el orden de SystemLogsPage.tsx:301-311:
  "level","timestamp","source","action","exec_id","ticket","user","method","endpoint","status","duration" — sin sortKey (F5 solo cubre Historial) */ ];

export function isColVisible(prefs: TablePrefs, colId: string): boolean;                       // visibleColumns null ⇒ todas visibles
export function toggleColumn(prefs: TablePrefs, colId: string, all: ColumnDef[]): TablePrefs;  // NUNCA deja 0 visibles (la última ignora el toggle)
export function cycleSort(prefs: TablePrefs, colId: string, all: ColumnDef[]): TablePrefs;     // solo si la col tiene sortKey: null→asc→desc→null; col sin sortKey ⇒ prefs sin cambios
export function setColumnWidth(prefs: TablePrefs, colId: string, px: number): TablePrefs;      // clamp [40, 800], redondeo entero
export function sanitizeTablePrefs(raw: unknown, all: ColumnDef[]): TablePrefs;                // ids desconocidos se descartan; sort a col sin sortKey ⇒ null; widths fuera de rango se clampéan
export function sortToQuery(prefs: TablePrefs, all: ColumnDef[]): { sort?: string; dir?: "asc" | "desc" }; // {} si sort null
```

**Paso 3 — `uiPrefs.ts` (el ÚNICO módulo con I/O; replica el patrón de `preferences.ts:15-30,38-74`):**

```ts
// frontend/src/services/uiPrefs.ts — Plan 173 F2
// Claves canónicas del store (backend key = sufijo; localStorage = "stacky.ui.prefs." + key):
//   views.history | views.syslogs | views.ticketBoard   (SavedViewsState)
//   table.history | table.syslogs                        (TablePrefs)
const LS_PREFIX = "stacky.ui.prefs.";
const API_BASE = `${(import.meta as any).env?.VITE_API_BASE ?? ""}/api/preferences/ui/`;

export function loadUiPrefLocal<T>(key: string, fallback: T): T;         // try/catch JSON.parse, patrón read() de preferences.ts:15-22
export function saveUiPref(key: string, value: unknown): void;           // localStorage write + PUT fire-and-forget con .catch(() => {}) (patrón _pushToBackend :61-74)
export async function hydrateUiPref<T>(key: string, sanitize: (raw: unknown) => T): Promise<T | null>;
//   GET /api/preferences/ui/<key>; !res.ok o value null ⇒ null (el caller conserva lo local);
//   value presente ⇒ sanitize(value), se escribe a localStorage y se devuelve (backend gana al hidratar, patrón initPreferences :38-58).

export function useSavedViewsEnabled(): boolean;
//   Hook React: useState(true) + useEffect que hace UNA VEZ por sesión (promesa cacheada a nivel módulo)
//   fetch("/api/diag/health") y setea enabled = (body.saved_views_enabled !== false).
//   Regla binaria: solo `false` explícito apaga; backend viejo sin el campo o fetch fallido ⇒ true
//   (la flag es default ON; un backend viejo tampoco serviría el store y el fallback localStorage cubre).
//   C5 — con flag OFF hay un flash de montaje (render optimista true → health resuelve → false → return null).
//   Aceptado: la flag es default ON, OFF es excepcional. Optimización opcional (no obligatoria): si la app ya
//   hidrata /api/diag/health al arrancar y lo cachea, sembrar el useState desde ese caché síncrono elimina el flash.
```

> **C3 — regla dura de I/O (gotcha del repo).** `saveUiPref` y `hydrateUiPref` usan **`fetch` CRUDO**, NUNCA el wrapper `api.get/api.post` de `frontend/src/services/client.ts`: ese wrapper **LANZA una excepción en toda respuesta non-2xx** (404 con flag OFF, 400/413 de validación), lo que rompería el fire-and-forget y el fallback silencioso. El patrón correcto es el de `preferences.ts:61-74` (`fetch(...).catch(() => {})`) y el de `initPreferences` (`fetch` + chequeo `res.ok` explícito). Un modelo menor que alcance `api.post` por reflejo introduce un bug: prohibido.

**Paso 2b — [ADICIÓN ARQUITECTO] `historyPaginationView` (pura, en `tablePrefs.ts`) — cierra C1 con test, no con smoke:**

```ts
// La ÚNICA fuente de verdad de la paginación de Historial. El JSX de F5 solo la invoca.
export interface PaginationView { label: string; canNext: boolean }
export function historyPaginationView(args: {
  offset: number; count: number; limit: number;
  total: number | null; runtimeActive: boolean;   // runtimeActive = filters.runtime !== ""
}): PaginationView;
//   Regla binaria (idéntica para label y canNext — ESTE es el fix de C1):
//   usarTotal = args.total != null && !args.runtimeActive
//   label   = usarTotal ? `${offset+1}–${offset+count} de ${total}` : `${offset+1}–${offset+count}`
//   canNext = usarTotal ? (offset + count < total) : (count >= limit)
//   Con runtime activo el `total` del backend es el COUNT SQL PRE-filtro-runtime (runtime se filtra
//   post-paginación en Python, executions.py:420-422) ⇒ NO es comparable con `count`; se ignora y se
//   cae a la regla legacy `count >= limit`. Sin este guardado, «Siguiente» quedaría mal habilitada.
```

**Paso 4 — Tests (TDD: escribirlos ANTES que los módulos).** `savedViews.test.ts`: `valida_nombre_vacio_largo_duplicado_cap` (los 4 mensajes exactos), `upsert_alta_y_reemplazo_sin_duplicar`, `rename_actualiza_lastApplied`, `delete_limpia_lastApplied`, `apply_inexistente_null`, `apply_setea_lastApplied_y_normaliza`, `computeActiveView_deep_equal_normalizado` (orden de claves y vacíos no afectan), `sanitize_descarta_basura` (null, array, entradas sin name, filters con números ⇒ descartadas, cap 20), `ticketboard_codec_roundtrip` (bool→"1"/""→bool; defaults al faltar claves). `tablePrefs.test.ts`: `visible_null_todas_visibles`, `toggle_nunca_cero_columnas`, `cycle_solo_sorteables_null_asc_desc_null`, `width_clamp_40_800`, `sanitize_ids_desconocidos_y_sort_invalido`, `sortToQuery_mapea_sortKey` (`inicio`→`{sort:"started_at"}`), `history_columns_10_syslog_11` (fija los catálogos: 10 y 11 ids, en el orden citado), **`paginationView_sin_runtime_usa_total` (total=42, runtimeActive=false → label «X–Y de 42», canNext por `offset+count<total`), `paginationView_con_runtime_ignora_total` (total=42, runtimeActive=true → label sin «de N», canNext por `count>=limit` — el fix de C1), `paginationView_backend_viejo_total_null` (total=null → regla legacy en ambos)**.

**Criterio de aceptación BINARIO:** `npx vitest run src/services/__tests__/savedViews.test.ts` → exit 0 (K4); `npx vitest run src/services/__tests__/tablePrefs.test.ts` → exit 0 (K5); `npx tsc --noEmit` → exit 0.

**Flag:** consumida por `useSavedViewsEnabled()` vía el campo de health de F0 (mecanismo del plan 139 citado en §2.4). **Runtimes:** lógica pura del dashboard; paridad por vacuidad. **Fallback:** sin backend ⇒ `hydrateUiPref` devuelve null y todo opera con localStorage; sin localStorage (modo privado) ⇒ `loadUiPrefLocal` cae al fallback en memoria por el try/catch. **Trabajo del operador: ninguno.**

---

### F3 — Presets nombrados por pantalla: `SavedViewsBar` en Historial, Logs del Sistema y Tablero

**Objetivo (1 frase):** una barra compacta reutilizable para guardar la vista actual con nombre, aplicarla, renombrarla y borrarla (con confirmación), cableada en las 3 pantallas de §2.3. **Valor:** 1 click reemplaza la reconstrucción manual de filtros — el corazón del plan.

**Archivos NUEVOS (2):** `frontend/src/components/SavedViewsBar.tsx` + `frontend/src/components/SavedViewsBar.module.css`.
**Archivos a EDITAR (3):** `frontend/src/pages/ExecutionHistoryPage.tsx`, `frontend/src/pages/SystemLogsPage.tsx`, `frontend/src/pages/TicketBoard.tsx` (pre-flight `git status -- "<ruta>"` en cada uno; TicketBoard es caliente).

**Contrato del componente (props exactas):**

```ts
interface SavedViewsBarProps {
  screenId: "history" | "syslogs" | "ticketBoard";        // clave del store: `views.${screenId}`
  currentFilters: Record<string, string>;                  // ya normalizados por el caller
  onApply: (filters: Record<string, string>) => void;      // el caller aplica a su estado local
}
```

**Comportamiento (sin ambigüedad):**
1. Si `useSavedViewsEnabled()` es false ⇒ `return null` (la pantalla queda idéntica a hoy).
2. Montaje: `loadUiPrefLocal` inmediato + `hydrateUiPref(key, sanitizeSavedViews)` en background (si devuelve valor, reemplaza el estado — backend gana, patrón `initPreferences`).
3. UI (una sola fila, DENTRO del bloque de filtros existente de cada pantalla, sin tocar densidad ni tema): `Select` (primitiva 162, Tier B con `aria-label="Vistas guardadas"`) con opción vacía «Vistas…» + una opción por vista (⭐ prefijo si `computeActiveView` la marca activa); botones (`Button` primitiva): **Guardar** (visible siempre; si hay vista activa cambia el label a **Actualizar**), **Renombrar** y **Borrar** (solo con vista seleccionada).
4. **Guardar/Renombrar** abren una fila inline (NO un modal — sin dependencia del 164 para el caso feliz): `Field` con `label="Nombre de la vista"` + `Input` + botones Confirmar/Cancelar. Validación inline con `validateViewName` mostrada vía la prop `error` de `Field` (plan 162); Confirmar deshabilitado mientras `error != null`. **Sobrescribir un preset existente vía "Guardar" con nombre duplicado exige confirmación previa** (mismo mecanismo del punto 5).
5. **Borrar / sobrescribir** (acciones destructivas, human-in-the-loop): si el diálogo canónico del plan 164 ya existe en el checkout (buscar el componente `ConfirmDialog` exportado por `components/ui`; verificable con `grep -r "ConfirmDialog" frontend/src/components/ui/index.ts` en el momento de implementar), usarlo; si NO existe, `window.confirm("¿Borrar la vista \"<name>\"?")` — degradación explícita al patrón vigente de la app; NUNCA borrar sin confirmar.
6. Toda mutación: `setState` local + `saveUiPref("views." + screenId, nuevoEstado)` (fire-and-forget).
7. Aplicar: `const r = applyView(state, name); if (r) { setState(r.state); saveUiPref(...); onApply(r.filters); }`.

**Ratchets:** CERO `style={{}}` (archivo nuevo ⇒ tolerancia 0 del uiDebtRatchet — todo en `SavedViewsBar.module.css` con tokens del tema); CERO tags crudos `<select>/<input>/<label>/<button>` (formDebtRatchet 162 ⇒ primitivas `Select`, `Input`, `Field`, `Button` de `components/ui`).

**Wiring por pantalla (exacto):**
- **Historial:** debajo de los 4 selects (`ExecutionHistoryPage.tsx`, bloque `className={styles.filters}` `:112-158`). `currentFilters = normalizeFilters({ agent_type: filters.agent_type, runtime: filters.runtime, status: filters.status, days: filters.days })`. `onApply={(f) => setFilters((prev) => ({ ...prev, agent_type: f.agent_type ?? "", runtime: f.runtime ?? "", status: f.status ?? "", days: f.days ?? "", offset: 0 }))}` — se pisan las 4 claves (ausente ⇒ `""` = «Todos»), `offset` SIEMPRE a 0, `limit` se conserva. **`limit` y `offset` JAMÁS forman parte de un preset** (regla heredada del 165 §3.7).
- **Logs del Sistema:** ídem con las 8 claves de `:124-133`; `onApply` setea el objeto completo (ausente ⇒ `""`) + `setOffset(0)`.
- **Tablero de Tickets:** `currentFilters = ticketBoardStateToFilters({ search, onlyPending, showAll, viewMode })`; `onApply` decodifica con `filtersToTicketBoardState` y llama los 4 setters existentes (`setSearch`, `setOnlyPending`, `setShowAll`, `setViewMode` — que ya persisten solos por `useLocalStorageState`, `:759-784`).

**Dependencia blanda con el 165 (declarada):** aplicar un preset es SIEMPRE `setFilters` local. Si el 165 ya está implementado cuando esto aterrice, su efecto de reflejo filtros→querystring (su F2 Paso 4) serializa la URL solo — el preset "navega a la URL del contrato" transitivamente, sin `import` de `routes.ts`. Si el 165 no está, el preset funciona igual, sin URL. **Cero acoplamiento de código entre 173 y 165.**

**Tests:** la lógica ya quedó fijada en F2 (K4). Esta fase se verifica con `npx tsc --noEmit` → exit 0 **y smoke manual documentado:** en Historial setear `status=error, days=7` → Guardar como «errores 7d» → cambiar filtros a mano → seleccionar «errores 7d» → los 4 selects vuelven y la tabla refetchea (la queryKey ya depende de `filters`, `ExecutionHistoryPage.tsx:68`); Renombrar; Borrar (aparece confirmación); repetir 1 preset en Logs y 1 en Tablero; recargar con F5 → los presets siguen (localStorage) ; borrar localStorage del navegador y recargar → los presets vuelven (backend).

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` → exit 0 + smoke de arriba completado y anotado en el resumen de implementación.

**Flag:** OFF ⇒ la barra no se renderiza (punto 1). **Runtimes:** UI del dashboard; paridad por vacuidad; el contenido de un preset es agnóstico (filtra por el campo `runtime` de la ejecución igual que los selects de hoy). **Fallback:** sin backend ⇒ presets solo-local; sin 164 ⇒ `window.confirm`; sin 165 ⇒ sin reflejo URL. **Trabajo del operador: ninguno** (usar presets es opcional; no usarlos deja todo como hoy).

---

### F4 — Preferencias de tabla: columnas visibles y anchos en Historial y Logs del Sistema

**Objetivo (1 frase):** persistir por tabla qué columnas se ven y con qué ancho (`table.history` / `table.syslogs`), con un menú de columnas y resize por arrastre, aplicados imperativamente (sin `style={{}}`). **Valor:** cada operador deja la tabla como le sirve y la reencuentra así.

**Archivos NUEVOS (2):** `frontend/src/components/TableColumnsMenu.tsx` + `frontend/src/components/TableColumnsMenu.module.css`.
**Archivos a EDITAR (2):** `ExecutionHistoryPage.tsx`, `SystemLogsPage.tsx` (pre-flight git status por archivo).

**`TableColumnsMenu` (props exactas):** `{ columns: ColumnDef[]; prefs: TablePrefs; onChange: (next: TablePrefs) => void }`. Botón «Columnas» (primitiva `Button`) que abre un popover posicionado por CSS del module.css con una `Checkbox` (primitiva 162, `aria-label` = label de la columna) por columna; cada toggle llama `onChange(toggleColumn(prefs, id, columns))`. Cierre por click-afuera con un listener `mousedown` en `document` dentro de `useEffect` (patrón simple; el focus-trap canónico es del plan 164 y NO se implementa acá). La última columna visible no se puede desmarcar (garantía de `toggleColumn`, ya testeada en K5).

**Cableado en cada página (idéntico patrón, descrito para Historial):**
1. Estado: `const [tablePrefs, setTablePrefs] = useState<TablePrefs>(() => loadUiPrefLocal("table.history", EMPTY_TABLE_PREFS));` + `useEffect` de montaje con `hydrateUiPref("table.history", (raw) => sanitizeTablePrefs(raw, HISTORY_COLUMNS))`. Mutar = `setTablePrefs` + `saveUiPref`.
2. **Visibilidad:** cada `<th>`/`<td>` de la tabla (`:168-227`) se envuelve en `{isColVisible(tablePrefs, "<colId>") && (…)}` usando los 10 ids EXACTOS de `HISTORY_COLUMNS` en su orden actual. El orden de columnas NO es configurable (fuera de scope, ver §6).
3. **Anchos:** cada `<th>` gana `data-col="<colId>"` y un `<span className={styles.resizeHandle} data-resize="<colId>" />`. Un solo `useEffect` con `pointerdown/pointermove/pointerup` sobre el `tableRef` implementa el arrastre: al soltar, `onChange(setColumnWidth(prefs, colId, Math.round(anchoFinalPx)))`. Los anchos persistidos se APLICAN en otro `useEffect` (`[tablePrefs.widths]`): `tableRef.current.querySelectorAll("th[data-col]")` y asignación imperativa `th.style.width = px + "px"` — **NUNCA `style={{}}` en el JSX** (uiDebtRatchet: estos `.tsx` existentes tienen baseline congelado; subirlo = test rojo; el patrón ref+effect es la vía documentada del repo).
4. Sin `width` persistido ⇒ la columna queda como hoy (auto). «Restablecer columnas» dentro del popover: `onChange(EMPTY_TABLE_PREFS)` conservando `sort` (`{ ...EMPTY_TABLE_PREFS, sort: prefs.sort }`).
5. En `SystemLogsPage` ídem con `SYSLOG_COLUMNS` (11 ids) y clave `table.syslogs`. Sin sort (los `sortKey` de syslogs no existen — F5 solo cubre Historial).
6. Gate: si `useSavedViewsEnabled()` es false ⇒ no se renderiza el menú, no se aplican anchos ni visibilidad (tabla idéntica a hoy).

**Tests:** lógica fijada en F2 (K5: `toggle_nunca_cero_columnas`, `width_clamp_40_800`, `sanitize_ids_desconocidos_y_sort_invalido`, catálogos 10/11). Fase verificada con `npx tsc --noEmit` → exit 0 + smoke manual: ocultar «Prompt» y «Archivos» en Historial → recargar → siguen ocultas; angostar «Ticket» a ~200px → recargar → persiste; intentar ocultar todas → la última no se deja; «Restablecer columnas» vuelve al estado de hoy.

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` → exit 0 + smoke completado y anotado.

**Flag:** misma; OFF ⇒ tabla intacta. **Runtimes:** dashboard puro; paridad por vacuidad. **Fallback:** prefs corruptas ⇒ `sanitizeTablePrefs` las repara; backend caído ⇒ solo-local. **Trabajo del operador: ninguno.**

---

### F5 — Backlog del 165: `sort` + `total` en `GET /api/executions/history` (backend aditivo + consumo)

**Objetivo (1 frase):** agregar al endpoint de historial orden configurable por columnas REALES de DB y un total real opt-in, sin romper ningún consumidor existente, y consumirlos desde la tabla de Historial («X–Y de N» + sort por encabezado). **Valor:** cierra el backlog cruzado que el 165 §8 dejó registrado y hace honesta la paginación.

**Archivos a EDITAR (3):** `backend/api/executions.py`, `frontend/src/api/endpoints.ts`, `frontend/src/pages/ExecutionHistoryPage.tsx`. **Archivo NUEVO (1):** `backend/tests/test_executions_history_sort_total.py` (+ registro en `HARNESS_TEST_FILES`).

**Paso 1 — Backend (`executions_history`, `:283-380`), cambios aditivos:**

```python
# Plan 173 F5 — allowlist de sort: SOLO columnas reales de agent_executions.
# duration_ms se calcula por fila y cost_usd/runtime viven en metadata_json ⇒ NO sorteables server-side.
_HISTORY_SORT_COLUMNS = {
    "started_at": AgentExecution.started_at,
    "id": AgentExecution.id,
    "status": AgentExecution.status,
    "agent_type": AgentExecution.agent_type,
}

# dentro de executions_history(), tras leer limit/offset (:298-299):
sort_key = request.args.get("sort", default="started_at")
sort_dir = request.args.get("dir", default="desc")
include_total = (request.args.get("include_total") or "").strip().lower() in ("1", "true", "yes")  # mismo estilo que all_projects (:48)
col = _HISTORY_SORT_COLUMNS.get(sort_key, AgentExecution.started_at)   # desconocido ⇒ fallback, NUNCA 400 (tolerante/backward)
order = col.asc() if sort_dir == "asc" else col.desc()                  # dir inválido ⇒ desc

# reemplazar SOLO la línea q.order_by(AgentExecution.started_at.desc()) (:338) por:
#   total = q.count() if include_total else None    ← ANTES de offset/limit, DESPUÉS de todos los filtros SQL
#   rows = q.order_by(order, AgentExecution.id.desc()).offset(offset).limit(limit).all()   ← tiebreaker estable

# retorno (reemplaza jsonify(items) en :380):
if include_total:
    return jsonify({"items": items, "total": total})
return jsonify(items)                                   # contrato legacy INTACTO
```

**Limitación documentada (obligatoria en el docstring del endpoint):** el filtro `runtime` se aplica post-paginación en Python (`:350-352`, preexistente — vive en `metadata_json`); por lo tanto `total` NO lo descuenta. Regla binaria para la UI: **el total solo se muestra cuando `filters.runtime === ""`**; con filtro de runtime activo la paginación se muestra como hoy («X–Y»).

**Paso 2 — Tests primero (TDD).** `backend/tests/test_executions_history_sort_total.py`, replicando fixture (`:32-45`) y seeder `_seed_exec` (`:50-90`) de `tests/test_executions_history.py` con rango `ado_id` propio (arrancar `_NEXT_ADO_ID` en 91000 para no colisionar):

| Test | Qué afirma |
|---|---|
| `test_sin_include_total_lista_pelada` | `GET /api/executions/history` → 200 y `isinstance(body, list)` (contrato legacy byte-compatible). |
| `test_include_total_devuelve_envelope` | Seed 3 ejecuciones → `?include_total=1&limit=2` → `body["total"] == 3` y `len(body["items"]) == 2`. |
| `test_sort_id_asc` | `?sort=id&dir=asc&include_total=1` → `[it["id"] for it in body["items"]]` estrictamente creciente. |
| `test_sort_desconocido_fallback` | `?sort=cost_usd` → 200 con orden default `started_at` desc (NUNCA 400/500). |
| `test_total_respeta_filtros_sql` | Seed 2 `status=error` + 1 `status=completed` → `?status=error&include_total=1` → `total == 2`. |
| `test_gate_flag_history_sigue` | Con `STACKY_EXECUTION_HISTORY_ENABLED=false` (monkeypatch env) → 404 `feature_disabled` (el gate preexistente `:291-292` no se rompió). |

Registrar `tests/test_executions_history_sort_total.py` en `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`; mismo pre-flight de F0 punto 7). Comando: `venv/Scripts/python.exe -m pytest tests/test_executions_history_sort_total.py -q`.

**Paso 3 — Frontend.** En `endpoints.ts`: NO tocar `Executions.history` (`:1318-1320`, tiene otros consumidores); agregar al MISMO objeto `Executions`:

```ts
export interface ExecutionHistoryEnvelope { items: ExecutionHistoryItem[]; total: number | null }
historyPage: (q: { /* mismos params de history */ sort?: string; dir?: "asc" | "desc" }) => {
  // arma los mismos URLSearchParams + sort/dir + include_total=1 y tolera backend viejo:
  return api.get<ExecutionHistoryItem[] | { items: ExecutionHistoryItem[]; total: number }>(url)
    .then((r) => Array.isArray(r) ? { items: r, total: null } : r);   // array ⇒ backend viejo ⇒ total null
},
```

En `ExecutionHistoryPage.tsx`: (a) la query pasa a `Executions.historyPage({ ...actuales, ...sortToQuery(tablePrefs, HISTORY_COLUMNS) })` con `queryKey: ["execution-history", filters, tablePrefs.sort, activeProject?.name]`; (b) los `<th>` de las 3 columnas con `sortKey` (Inicio/Agente/Estado) se vuelven clickeables: `onClick={() => { const next = cycleSort(tablePrefs, id, HISTORY_COLUMNS); setTablePrefs(next); saveUiPref("table.history", next); }}` con indicador `▲/▼` textual dentro del th (clase del module.css, sin inline style) y `aria-sort` correspondiente; th sin `sortKey` no reciben handler; (c) la línea de paginación (`:244-246`) y el `disabled` de «Siguiente» se derivan AMBOS de una sola llamada a la función pura de C1b: `const pv = historyPaginationView({ offset: filters.offset, count: items.length, limit: filters.limit, total, runtimeActive: filters.runtime !== "" });` → el texto usa `pv.label` y «Siguiente» usa `disabled={!pv.canNext}`. **Fix C1:** el guardado `runtime === ""` aplica a la navegación Y al label por igual (antes el `disabled` miraba solo `total != null`, lo que con filtro runtime activo comparaba `items.length` post-filtro contra un `total` SQL pre-filtro y habilitaba «Siguiente» de más). Sin `Intl`, sin formateadores nuevos (es un entero con `String()` — el ratchet anti-Intl del 161 no se activa). Gate: con flag OFF no hay sort UI (F4 ya no renderiza prefs) y la página usa la regla de paginación vieja.

**Criterio de aceptación BINARIO:** K2 exit 0 + `npx tsc --noEmit` exit 0 + smoke: click en «Inicio» cicla ▲/▼/nada y la tabla se reordena; con backend viejo simulado (devolver array) la página no rompe y muestra «X–Y».

**Flag:** los params nuevos NO se gatean por `STACKY_UI_SAVED_VIEWS_ENABLED` (son contrato API aditivo, inertes si nadie los manda); la UI que los dispara sí está gateada (F4). El gate preexistente `STACKY_EXECUTION_HISTORY_ENABLED` queda intacto. **Runtimes:** el endpoint lista ejecuciones de los 3 runtimes por igual; el sort es sobre columnas comunes; paridad total. **Fallback:** backend viejo ⇒ `total null` + orden default (declarado arriba). **Trabajo del operador: ninguno.**

---

### F6 — Restauración de última vista + preset activo resaltado

**Objetivo (1 frase):** al volver a una pantalla, re-aplicar automáticamente el último preset aplicado (`lastApplied`) — cediendo SIEMPRE ante el contrato de URL del 165 — y resaltar en la barra el preset que coincide con los filtros vigentes. **Valor:** la pantalla te espera como la dejaste, sin un click.

**Archivos a EDITAR (3):** `ExecutionHistoryPage.tsx`, `SystemLogsPage.tsx`, `TicketBoard.tsx` (solo el punto 3).

**Reglas de precedencia al montar (binarias, en este orden):**
1. **Si la URL trae ≥1 clave de filtro de la pantalla** (solo posible con el 165 implementado, su F2/C2): la URL manda; NO se aplica `lastApplied`. Detección concreta sin depender de `routes.ts`: `new URLSearchParams(window.location.search)` contiene alguna de las claves de filtro de la pantalla (las 4 de Historial / las 8 de Logs).
2. **Guardado en runtime, independiente del 165 (fix C2).** La auto-aplicación de `lastApplied` dispara **SOLO si los filtros al montar son iguales al DEFAULT de la pantalla** — es decir, si NADA (ni el 165 vía `useLocalStorageState`, ni una URL, ni un ajuste persistido) los restauró ya. Condición concreta: `deepEqual(normalizeFilters(currentFilters), normalizeFilters(DEFAULT_FILTERS_DE_LA_PANTALLA))`. Si difieren ⇒ algo los restauró ⇒ 173 NO pisa (conserva SOLO el resaltado, punto 4). Este guardado es verificable en runtime y **no depende de si el 165 está o no implementado**, ni del orden de aterrizaje de la serie (el orden canónico pone al 165 ANTES del 173, así que en la práctica los filtros persistidos ya estarán y 173 cederá solo). El `grep -n "useLocalStorageState" …ExecutionHistoryPage.tsx` es guía secundaria para el implementador, **NO** la autoridad: la autoridad es la comparación con el DEFAULT en el `useEffect` de montaje. (Se elimina la conclusión rígida «hoy se implementa» de v1, que contradecía el orden de la serie.)
3. **Si aplica el guardado de la regla 2 y `lastApplied` existe** en `views.<screenId>`: `useEffect` de montaje (una sola vez, con `useRef` guard) hace `const r = applyView(state, state.lastApplied); if (r) onApplyDeLaPantalla(r.filters);`. En TicketBoard este paso NO existe: sus 4 campos ya persisten por `useLocalStorageState` (`:759-784`) ⇒ nunca están en DEFAULT tras la primera vez; TicketBoard solo recibe el resaltado.
4. **Resaltado:** `computeActiveView(state, currentFilters)` (K4) marca la opción del `Select` de la barra (prefijo ⭐ y opción seleccionada). Se recalcula en cada render — si el operador toca un filtro a mano y ya no coincide, el resaltado desaparece (feedback honesto de "estás fuera del preset").

**Tests:** la lógica (`applyView`, `computeActiveView`, codec) ya está fijada en K4; las reglas 1-3 son wiring de montaje verificado por smoke manual documentado: aplicar «errores 7d» en Historial → ir a Tickets → volver a Historial → los filtros del preset están puestos y la vista resaltada; editar un filtro a mano → el resaltado desaparece; (con 165 implementado) pegar una URL con `?status=completed` → la URL gana y no se aplica el preset.

**Criterio de aceptación BINARIO:** `npx tsc --noEmit` → exit 0 + smoke completado y anotado.

**Flag:** misma; OFF ⇒ sin auto-aplicación ni resaltado (la barra ni se monta). **Runtimes:** paridad por vacuidad. **Fallback:** `lastApplied` apuntando a una vista borrada ⇒ `applyView` devuelve null y no pasa nada (ya testeado). **Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | La sesión paralela conocida toca los mismos archivos calientes (`run_harness_tests.sh` y `app.py` YA tienen WIP ajeno hoy; TicketBoard/ExecutionHistoryPage son blanco frecuente). | Pre-flight `git status -- "<ruta>"` antes de CADA archivo en CADA fase; WIP ajeno en el mismo archivo ⇒ STOP y reportar; staging quirúrgico por path; el implementador NO commitea. |
| R2 | Colisión conceptual con el 165 (ambos persisten filtros). | Frontera exacta: 165 = filtros crudos + URL; 173 = vistas NOMBRADAS + prefs de tabla + lastApplied. Cero imports cruzados (F3 «dependencia blanda»); precedencia URL>persistido>lastApplied codificada en F6 con detección verificable por grep. |
| R3 | Olvidar un paso del patrón triple de flags rompe meta-tests (`test_default_known_only_for_curated`, `test_every_registry_flag_is_categorized`). | F0 enumera los 4 archivos exactos y K3 corre `tests/test_harness_flags.py` como gate binario. |
| R4 | `style={{}}` para anchos de columna enciende el uiDebtRatchet (baseline congelado en `.tsx` existentes, tolerancia 0 en nuevos). | Prohibición explícita F4 punto 3: anchos SOLO por ref+effect imperativo (`th.style.width`); archivos nuevos con module.css puro. |
| R5 | Tags crudos `<select>/<input>` en los componentes nuevos suben el formDebtRatchet del 162. | F3/F4 obligan primitivas `Select/Input/Field/Checkbox/Button` de `components/ui` (verificadas exportadas, `index.ts:25-34`). |
| R6 | Cambiar la respuesta de `/api/executions/history` rompe consumidores existentes. | Envelope SOLO con `include_total=1` (opt-in); sin el param la respuesta es byte-compatible (`test_sin_include_total_lista_pelada`); `Executions.history` de `endpoints.ts` NO se toca — se agrega `historyPage`. |
| R7 | `total` engañoso con filtro `runtime` (post-filtrado en Python, `:350-352` preexistente). | Regla binaria F5: la UI muestra total SOLO con `filters.runtime === ""`; limitación documentada en el docstring del endpoint. |
| R8 | Shape-drift del store (presets viejos con forma nueva) rompe páginas al montar. | TODO lo que entra del backend/localStorage pasa por `sanitizeSavedViews`/`sanitizeTablePrefs` (tolerantes a cualquier `unknown`, testeadas en K4/K5) — mismo remedio que el 165 C5. |
| R9 | Escrituras concurrentes al JSON del store (dos pestañas, o PUT legacy `/api/preferences` vs PUT `/ui/<key>`). | **Precisión C6:** cada PUT hace read-modify-write del ARCHIVO COMPLETO `preferences.json` (`_read()`→mutar→`_write()`), igual que el PUT legacy (`preferences.py:49-51`) ⇒ el «último-escribe-gana» es **a nivel archivo**, no por clave (una escritura de avatar concurrente con una de vista podría perderse). Mono-operador ⇒ ventana ínfima y trade-off idéntico al ya aceptado por `preferences.json` para avatares/pins; sin locking nuevo. Las claves separadas por pantalla reducen pisadas *entre vistas*, no la atomicidad del archivo. |
| R10 | Backend viejo + frontend nuevo (o viceversa) tras un deploy parcial. | Ambos sentidos degradan: frontend tolera array legacy (`total null`) y campo de health ausente (`!== false` ⇒ ON con fallback localStorage); backend ignora que nadie le mande `sort`/`include_total`. |
| R11 | El popover de columnas sin focus-trap se percibe inconsistente cuando aterrice el 164. | Se declara: el focus-trap canónico es del 164; cuando exista, migrar el popover es un one-liner de adopción registrado en §6 como backlog del 164, no de este plan. |

---

## 6. Fuera de scope (explícito, con dueño)

- **Atajos de teclado** para guardar/aplicar vistas, foco roving en tablas, overlay «?» — **plan 172** (cuando exista, podrá invocar `upsertView`/`applyView` de `savedViews.ts`; el contrato puro de F2 es su punto de consumo).
- **Virtualización de listas, prefetch on-hover, caché de navegación (react-query) y presupuesto de perf** — **plan 174**. Este plan no toca `staleTime` ni agrega prefetches.
- **Hover-cards/peek, menú contextual de clic derecho y acciones rápidas inline** (p.ej. «aplicar preset» desde un menú contextual) — **plan 175**.
- **Diálogo canónico y focus-trap** — **plan 164**; acá solo se consume si existe (F3 punto 5) con fallback `window.confirm`; la migración del popover de F4 al canónico queda como adopción futura del 164.
- **Reflejo de filtros en la URL, deep-links y persistencia de filtros crudos** — **plan 165** (este plan solo cede precedencia y se beneficia transitivamente).
- **Densidad global** (plan 150), **tema/accesibilidad visual** (141), **microinteracciones** (143): no se tocan ni sus tokens ni sus flags.
- **Orden (drag-reorder) de columnas** y **sort server-side en Logs del Sistema**: mejoras futuras; hoy solo visibilidad+anchos (ambas tablas) y sort en Historial sobre columnas reales de DB.
- **Sort por `duración`/`costo`/`runtime` en el servidor:** imposible sin migrar esos datos de `metadata_json` a columnas — eso sería un plan de datos aparte, no de UX.
- **Migrar `_PREFS_FILE` a `runtime_paths`** o mover el store a una tabla SQL: el JSON existente es el patrón de la casa para preferencias de operador.
- **Multi-usuario/RBAC en el store:** mono-operador sin auth (riel duro).

---

## 7. Glosario + Orden de implementación + DoD

### Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **vista guardada / preset** | Una combinación de filtros de una pantalla, guardada con nombre por el operador, aplicable con 1 click. Vive en el store como `SavedView {name, filters}`. |
| **preferencias de tabla** | Estado persistente de UNA tabla: columnas visibles, sort activo y anchos por columna (`TablePrefs`). |
| **store de preferencias de UI** | Clave-valor persistido en `data/preferences.json` bajo la clave raíz `"ui"`, servido por `GET/PUT /api/preferences/ui/<key>`, con espejo en `localStorage` (`stacky.ui.prefs.*`) que funciona solo si el backend no está. |
| **lastApplied** | Nombre del último preset aplicado en una pantalla; F6 lo re-aplica al volver, salvo que la URL (165) o la persistencia cruda de filtros manden. |
| **flag del arnés** | Interruptor tipado (`FlagSpec`) registrado en `harness_flags.py`, visible y toggleable en Settings→Arnés vía `GET/PUT /api/harness-flags`, con default efectivo en `config.py`. |
| **patrón triple de flags** | FlagSpec `default=True` + entrada en `_CURATED_DEFAULTS_ON` (tests) + atributo en `config.py` — los tres o los meta-tests fallan. |
| **uiDebtRatchet / formDebtRatchet** | Tests que congelan la deuda de `style={{}}` (plan 138) y de tags crudos de formulario (plan 162): en archivos nuevos la tolerancia es CERO; solo puede bajar. |
| **paridad por vacuidad** | La feature es del dashboard y no toca el camino de ejecución de agentes ⇒ se comporta idéntica con Codex CLI, Claude Code CLI y GitHub Copilot Pro sin trabajo extra. |
| **envelope** | Respuesta `{items, total}` de `/api/executions/history` cuando se pide `include_total=1`; sin el param, la respuesta legacy (array pelado) no cambia. |

### Orden de implementación (numerado)

1. **F0** — flag triple + `saved_views_enabled` en health + registro del test en `HARNESS_TEST_FILES`. Gate: K1 (parcial) + K3.
2. **F1** — store `GET/PUT /api/preferences/ui/<key>` + tests completos. Gate: K1.
3. **F2** — `savedViews.ts` + `tablePrefs.ts` + `uiPrefs.ts` + 2 tests puros. Gate: K4 + K5 + K6.
4. **F3** — `SavedViewsBar` + wiring en las 3 pantallas + smoke. Gate: K6 + smoke.
5. **F4** — `TableColumnsMenu` + visibilidad/anchos en las 2 tablas + smoke. Gate: K6 + smoke.
6. **F5** — sort/total backend (TDD) + `historyPage` + sort UI + total en paginación. Gate: K2 + K6 + K7 + smoke.
7. **F6** — lastApplied + precedencias + resaltado + smoke final. Gate: K6 + smoke.

`npx tsc --noEmit` al cierre de CADA fase frontend; pytest SIEMPRE por archivo con `venv/Scripts/python.exe`; vitest SIEMPRE por archivo. Pre-flight `git status -- "<ruta>"` antes de cada edición (sesión paralela activa).

### Definición de Hecho (DoD) global

- [ ] K1..K7 en verde con los comandos EXACTOS de §1, salidas pegadas en el resumen de implementación.
- [ ] `STACKY_UI_SAVED_VIEWS_ENABLED` visible y toggleable en Settings→Arnés (registry-driven, sin UI nueva), default ON, con el patrón triple completo; OFF deja la app píxel-idéntica a hoy (smoke).
- [ ] Presets nombrados funcionando en Historial, Logs del Sistema y Tablero (guardar/aplicar/renombrar/borrar-con-confirmación); persisten a F5 del navegador y, borrando localStorage, se rehidratan del backend.
- [ ] Columnas visibles y anchos persistentes en las tablas de Historial (10 col.) y Logs (11 col.); imposible quedar en 0 columnas; «Restablecer columnas» funciona.
- [ ] `GET /api/executions/history` con `sort`/`dir`/`include_total` aditivos, contrato legacy intacto sin el param, tiebreaker estable, limitación del `runtime` documentada; Historial muestra «X–Y de N» (solo sin filtro runtime) y ordena por Inicio/Agente/Estado.
- [ ] Última vista restaurada al volver (regla de precedencia de F6), preset activo resaltado, y con el 165 presente la URL SIEMPRE gana (smoke condicional documentado).
- [ ] Cero `style={{}}` nuevos, cero tags crudos de formulario nuevos, cero librerías nuevas en `package.json`, ambos tests backend registrados en `HARNESS_TEST_FILES`, ningún archivo fuera de la lista de cada fase tocado.
- [ ] Resumen final: qué cambió, por qué, cómo se validó, y estado del WIP ajeno encontrado en los pre-flights.
