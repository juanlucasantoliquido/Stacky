# Plan 174 — Rendimiento percibido: virtualización de listas largas, prefetch on-hover y navegación instantánea

**Serie UX Cockpit del Operador (172-175) — plan 3/4 — v1 PROPUESTO — 2026-07-18**

> **Estado:** PROPUESTO v1 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode (perfil normal)
> **Hermanos de serie:** 172 (teclado primero: atajos + foco roving), 173 (vistas guardadas: presets + preferencias de tabla), 175 (peek + acciones rápidas). Este plan NO define atajos (172), NO define presets ni columnas persistentes (173), NO define hover-cards ni menú contextual (175). Las dependencias con hermanos son **blandas**: si el hermano no está implementado, la feature degrada explícitamente (se detalla ítem por ítem), nunca rompe.
> **Dependencias blandas fuera de serie:** plan 156 (latido único — presupuesto de red KPI ≤2 requests/tick en idle: este plan lo RESPETA como techo duro aunque 156 no esté implementado aún), plan 164 (diálogo canónico — N/A acá: este plan no tiene ninguna acción con efecto), plan 165 (contrato de URL — la navegación instantánea complementa sus deep-links; sin 165 funciona igual sobre la history API actual).
> **Runtimes:** las features de este plan son 100% del dashboard (frontend React + 2 campos de lectura aditivos en un endpoint backend existente). Son **agnósticas del runtime de agentes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): ninguna fase toca el camino de ejecución, publicación ni telemetría de agentes. La paridad de los 3 runtimes es automática por vacuidad — igual se declara fase por fase.
> **Flags nuevas:** `STACKY_UI_VIRTUALIZATION_ENABLED` y `STACKY_UI_PREFETCH_ENABLED`, ambas **default ON**, editables desde la UI de Settings (FlagSpec `env_only=False`), con kill-switch instantáneo (OFF = comportamiento actual byte-idéntico).
> **Human-in-the-loop:** N/A por diseño — este plan solo hace GETs de lectura y cambia CÓMO se pinta lo que ya se pinta. Cero acciones destructivas, cero publicaciones, cero decisiones quitadas al operador. Ninguna de las 4 excepciones duras al "default ON" aplica (§3.2 lo argumenta textualmente).
> **Trabajo del operador: ninguno** (en todas las fases; se repite fase por fase porque es regla de la serie).

> Este documento está escrito para que un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) lo
> implemente **sin inferir nada**. Cada fase trae archivos exactos, símbolos exactos, pseudocódigo,
> tests primero con comando exacto y criterio de aceptación binario. Si algo no está escrito acá,
> **NO lo inventes**: parás y preguntás al operador.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** que la UI de Stacky se sienta instantánea sin pedir un byte de más: (a) las listas largas reales (stream de logs de ejecución y lista de diferencias del Comparador de BD) dejan de renderizar un nodo DOM por elemento y pasan a una **ventana virtualizada hand-rolled** (~≤60 nodos aunque haya 5.000 filas), extraída del precedente propio del repo (DiffList del plan 124) y sin agregar dependencias; (b) al **apuntar** con el mouse o el foco a una fila de ejecución, el detalle se **prefetchea** con react-query (debounce ≥150 ms, máximo 1 en vuelo, cancelación al salir), así el drawer abre ya pintado; (c) **paginar y filtrar deja de parpadear** (`placeholderData: keepPreviousData`) y **volver atrás pinta desde cache** y revalida en background (staleTime/gcTime afinados por tipo de query). Todo detrás de 2 flags default ON, con presupuesto de red y de DOM **binarios y testeados**, sin violar el techo del plan 156 (≤2 requests/tick en idle: el prefetch solo dispara con interacción humana; en idle suma exactamente 0).

**KPIs binarios (comandos exactos; backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` — en disco existen HOY `venv\Scripts\python.exe` y `.venv\Scripts\python.exe` (verificado 2026-07-18); usar `venv\Scripts\python.exe` y, solo si no existiera, `.venv\Scripts\python.exe`. Frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`):**

- **KPI-1 — Presupuesto de DOM:** `npx vitest run src/utils/__tests__/virtualWindow.test.ts` → exit 0. Incluye el caso binario: lista de **5.000 filas** (rowHeight 22 px, viewport 600 px, overscan 10) → `rendered ≤ 60` nodos y la suma `padTopPx + rendered*rowHeightPx + padBottomPx === total*rowHeightPx`.
- **KPI-2 — Presupuesto de red del prefetch:** `npx vitest run src/services/__tests__/prefetchPolicy.test.ts` → exit 0. Incluye: **0** llamadas sin interacción; debounce **≥150 ms**; **≤1** prefetch en vuelo (el excedente se DESCARTA, no se encola); `leave()` antes del deadline ⇒ **0** llamadas.
- **KPI-3 — Adopción real (fs+regex, precedente plan 140):** `npx vitest run src/__tests__/plan174Adoption.test.ts` → exit 0 (LogsPanel y DiffList usan `useVirtualList`; ExecutionHistoryPage y SystemLogsPage usan `placeholderData: keepPreviousData`; ExecutionHistoryPage y ReviewInboxPage usan `getPrefetchProps`).
- **KPI-4 — Flags backend verdes:** `venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q` → exit 0 (default ON, curadas, categorizadas, PLAIN_HELP, campos en `/api/diag/health`).
- **KPI-5 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-6 — Ratchets:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 (cero `style={{` nuevos) **y** `grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.sh` → `1` **y** `grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.ps1` → `1`.
- **KPI-7 — Sin regresión de flags:** `venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` y `venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q` → exit 0.

**KPIs de impacto (proyectados, verificables por smoke manual en §10 DoD):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Nodos DOM de una ejecución con 5.000 líneas de log (LogsPanel) | 5.000 (`LogsPanel.tsx:27` mapea todo) | ≤ 60 |
| Nodos DOM de un diff de BD con 3.000 objetos (DiffList) | crece de a 100 con clicks manuales "Mostrar 100 más" (`DiffList.tsx:36-38`) | ≤ 60, con scroll continuo y sin clicks |
| Apertura del drawer de detalle tras hover ≥150 ms sobre la fila | spinner siempre (2 queries en frío, `ExecutionDetailDrawer.tsx:36-46`) | pintado instantáneo desde cache (detalle prefetcheado) |
| Cambiar de página en Historial / System Logs | flash de skeleton/"Loading logs…" y tabla vacía | la tabla anterior queda visible atenuada hasta que llega la nueva |
| Requests extra en idle (sin mouse ni teclado) | 0 | **0** (techo duro; el prefetch es solo interacción humana) |

---

## 2. Por qué ahora / gap que cierra (evidencia leída 2026-07-18)

### 2.1 Listas largas sin ventana de render

- `frontend/src/components/LogsPanel.tsx:27` — `{stream.lines.map((l, i) => ...)}` renderiza **todas** las líneas del stream, sin ventana. El stream de `useExecutionStream` acumula sin cota (`useExecutionStream.ts:36` lista `lines`, `:39` Set `seenKeys`; documentado en plan 156 §2.3). El plan 156 (CRITICADO v2, **aún no implementado**) acota la memoria a ≤5.000 líneas con un ring-buffer — pero aun con 156 aterrizado, **5.000 líneas = 5.000 nodos DOM**. La virtualización es el complemento de render que 156 declaró explícitamente fuera de su alcance ("La cota se implementa sin libs nuevas", 156 §2.3; su F3 acota memoria, no DOM).
- `frontend/src/components/dbcompare/DiffList.tsx:12-16` — el único precedente de mitigación del repo: paginación incremental en cliente de a `PAGE_SIZE = 100` (`:5`), con botón "Mostrar 100 más" (`:37`) y el comentario normativo *"sin librerías de virtualización, per guardrail §3.1"* (plan 124). Dos problemas: el DOM **crece monótonamente** a medida que el operador clickea (3.000 objetos = 3.000 nodos si los quiere ver todos) y el patrón está **encerrado en un componente** en vez de ser un hook reutilizable.
- `frontend/src/pages/TicketBoard.tsx:1139,1157` — el board renderiza épicas con hijos anidados (`epic.children.map`, `:734`). Se **descarta como target de virtualización** en este plan: estructura jerárquica con alturas variables y volumen moderado (decenas de épicas, no miles de filas planas). Queda citado en §7 Fuera de scope.
- `frontend/package.json` — **no hay ninguna librería de virtualización** (grep `react-window|react-virtual|virtua` → 0 hits). Decisión §3.4: se mantiene hand-rolled.

### 2.2 Cero prefetch: el drawer siempre abre en frío

- `frontend/src/components/ExecutionDetailDrawer.tsx:36-46` — al abrir, dispara 2 queries en frío: `["execution-detail", executionId]` → `Executions.byId` (`:37-38`) y `["execution-output-files", executionId]` (`:42-44`). El operador ve spinner aunque llevara 2 segundos con el mouse sobre la fila.
- Consumidores del drawer con lista hovereable: `frontend/src/pages/ExecutionHistoryPage.tsx:258` y `frontend/src/pages/ReviewInboxPage.tsx:125` (también `DiagnosticsPage.tsx:213`, `AgentHistoryModal.tsx:111`, `CodexConsoleDock.tsx:321` — fuera del wiring inicial por listas cortas/no-hover, §7).
- Grep `onMouseEnter|prefetch` sobre `frontend/src` → **1 solo archivo** (`CommandPalette.tsx`, y es hover de selección visual, no prefetch de datos). Prefetch de datos real hoy: **cero**.

### 2.3 Paginar y filtrar parpadea; volver atrás repinta en frío

- `frontend/src/pages/ExecutionHistoryPage.tsx:82` — `const items = historyQ.data ?? []`: al cambiar filtro/página cambia la `queryKey` (`:68`) ⇒ `data` pasa a `undefined` ⇒ flash de skeleton + contador "0 resultados" (`:104`) hasta que llega la página nueva. `staleTime: 30_000` (`:79`), paginado de a `limit: 50` (`:41`).
- `frontend/src/pages/SystemLogsPage.tsx:150-155` — misma estructura (`PAGE_SIZE = 100`, `:7`; `staleTime: 10_000`, `refetchInterval: 30_000`): cada "Next →" (`:353-359`) pasa por `isLoading` ⇒ "Loading logs…" (`:293-294`) y la tabla desaparece.
- `frontend/src/main.tsx:9-10` — `QueryClient` global: `defaultOptions: { queries: { staleTime: 30_000, retry: 1 } }`. **Sin `gcTime` explícito** (default 5 min de react-query v5) y **sin `placeholderData`** en ningún consumidor paginado. `@tanstack/react-query": "^5.59.0"` ya está (`package.json:13`): `keepPreviousData` y `prefetchQuery` vienen incluidos — el sustrato existe, está subusado.

### 2.4 Presupuesto de red ya legislado que este plan debe respetar

- Plan 156 §1 (tabla de impacto): KPI **≤2 requests por tick en idle** (1 por scope de summary). Este plan NO puede sumar requests periódicas: todo tráfico nuevo es (a) disparado por interacción humana explícita (hover/focus con debounce), o (b) 1 única lectura de flags por sesión (staleTime `Infinity`, §F1).

---

## 3. Principios y guardarrailes

### 3.1 Los rieles duros de la serie

1. **3 runtimes con paridad.** Todo ítem es dashboard puro (frontend + 2 campos aditivos de lectura en `/api/diag/health`). Nada toca `agent_runner`, publicación, ni telemetría por runtime ⇒ paridad Codex CLI / Claude Code CLI / GitHub Copilot Pro por vacuidad. Se declara igual en cada fase.
2. **Cero trabajo extra para el operador.** Todo invisible/automático, flags **default ON**, sin pasos manuales nuevos, sin config nueva obligatoria, backward-compatible (OFF = byte-idéntico a hoy).
3. **Human-in-the-loop innegociable.** Este plan no ejecuta ninguna acción con efecto (ni destructiva ni de publicación): solo GETs y render. El diálogo canónico (164) no participa porque no hay nada que confirmar. Si durante la implementación apareciera una acción con efecto (no debería), pasa por 164 — se deja escrito para que el implementador no improvise.
4. **Mono-operador sin auth real.** Nada de RBAC ni multiusuario; los campos nuevos de `/api/diag/health` son de lectura y no validan `current_user` (no hay qué validar: sustrato sin login, header sin validar).
5. **No degradar.** Menos nodos DOM, menos parpadeo, misma información; el prefetch tiene techo duro (≤1 en vuelo, 0 en idle); el tuning de cache NO toca los pollers existentes ni el default global de `main.tsx:10`.

### 3.2 Las 4 excepciones duras al "default ON" — ninguna aplica (verificación textual)

- **"Bypass de revisión humana":** NO aplica — no hay ninguna revisión que saltear; el plan no publica ni ejecuta nada.
- **"Acción destructiva/irreversible":** NO aplica — solo lecturas (GET) y render; la cache de react-query es efímera y local.
- **"Prerequisito no garantizado":** NO aplica — el único prerequisito es `@tanstack/react-query ^5.59.0`, que **ya está** en `frontend/package.json:13`; no se instala nada.
- **"Reduce seguridad":** NO aplica — el prefetch solo repite GETs same-origin que la UI ya hace al click; no expone endpoints nuevos ni datos nuevos.

### 3.3 Convenciones duras del repo (obligatorias)

- **Flags:** `FlagSpec` en `backend/services/harness_flags.py` (registro `FLAG_REGISTRY`, `harness_flags.py:333`); una flag `default=True` DEBE agregarse a `_CURATED_DEFAULTS_ON` (`backend/tests/test_harness_flags.py:467`) o rompe `test_default_known_only_for_curated`; toda flag DEBE estar en `_CATEGORY_KEYS` (categoría `"interfaz_ui"`, `harness_flags.py:325-327`) o rompe `test_every_registry_flag_is_categorized` (nota normativa `harness_flags.py:331-332`); entrada en `PLAIN_HELP` (`harness_flags_help.py`) o rompe su test de cobertura. El default EFECTIVO vive en `backend/config.py` (patrón `config.py:1300-1302`, acá con default `"true"`). `env_only=False` ⇒ la flag queda **editable desde la UI de Settings** automáticamente (el panel de flags renderiza `FLAG_REGISTRY`; mismo mecanismo por el que `STACKY_UI_SHELL_V2_ENABLED` es visible hoy). Regla dura del pipeline cumplida: configurable por UI, no solo env var.
- **Mecanismo EXACTO de lectura de flags por el frontend** (plan 139 §"Mecanismo EXACTO de lectura de la flag por el frontend", `docs/139_PLAN_APP_SHELL_V2_...md:133-152`): campo booleano **aditivo** en la respuesta de `GET /api/diag/health` (`backend/api/diag.py:311-312` `def health()`; campos existentes `local_llm_enabled` / `shell_v2_enabled` en `diag.py:410-411`, patrón `bool(getattr(_config.config, "FLAG", False))`), leído por el frontend al montar (precedente `App.tsx:152-161`). Este plan agrega 2 campos con ese patrón exacto y los consume vía un hook con react-query (§F1) en lugar de estado en `App.tsx`, para no tocar `App.tsx` (archivo caliente de la serie).
- **Gotcha `config` vs `config.config`:** en los módulos backend la instancia de flags es `config.config` (el módulo es `config`); `getattr(config, FLAG)` devuelve siempre el default. En `diag.py` el patrón correcto ya está a la vista: `getattr(_config.config, ...)` (`diag.py:410`). Usar EXACTAMENTE ese.
- **Tests backend nuevos** se registran en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh:20` **y** `backend/scripts/run_harness_tests.ps1` — ambos existen, verificado) o el meta-test del ratchet rompe.
- **Comando backend:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` + `venv\Scripts\python.exe -m pytest tests/test_X.py -q` — **por archivo, nunca la suite entera** (contaminación cross-file conocida).
- **Comando frontend:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"` + `npx vitest run src/<ruta>/<archivo>.test.ts` — **por archivo** (vitest completo contamina cross-file).
- **Ratchet de deuda UI (plan 138):** prohibido `style={{}}` en `.tsx` nuevos y prohibido aumentar el baseline en los existentes. Los spacers de la virtualización (altura dinámica en px) se setean por **ref + effect imperativo** (`el.style.height = ...` dentro de `useEffect`), patrón ya validado en el repo.
- **jsdom/@testing-library NO existen** en `frontend/package.json` (gap estructural conocido): **todo test frontend de este plan es de lógica pura** (módulos `.ts` sin DOM), como `commandPaletteData.test.ts`, más tests de adopción fs+regex (precedente plan 140). Cero `render()`. El gate real de UI = `tsc --noEmit` + tests puros + smoke manual del DoD.
- **Formato humano:** este plan no formatea fechas/costos/tokens nuevos; si una fase tocara un texto de ese tipo, usa los 11 exports canónicos de `frontend/src/services/format.ts` (plan 161; OJO: el módulo canónico real es `services/format.ts`, importado así en `SystemLogsPage.tsx:4` y `ExecutionHistoryPage.tsx:18`). No hay formularios nuevos (si los hubiera: primitivas `ui/` del plan 162).
- **Sesión paralela conocida en el repo:** antes de editar CADA archivo existente, `git status -- "<ruta>"`; si hay WIP ajeno sin commitear en ese archivo ⇒ STOP y reportar. Anclar ediciones por TEXTO citado, no por número de línea.

### 3.4 Decisión de arquitectura: hand-rolled, NO `@tanstack/react-virtual`

Se **extrae y generaliza el patrón propio** (precedente `DiffList.tsx:12-13`, guardrail del plan 124 §3.1 "sin librerías de virtualización") como módulo puro + hook, en vez de sumar dependencia. Razones verificables: (1) el guardrail §3.1 del plan 124 ya legisló contra libs de virtualización y sigue vigente; (2) sin jsdom/RTL en el repo, una lib de virtualización sería **intesteable acá**, mientras que la función pura de ventana se testea al 100%; (3) las listas objetivo tienen **altura de fila fija** (logs monoespaciados, filas compactas de diff) — el caso que hand-rolled resuelve en ~60 líneas; (4) cero costo de bundle y de supply chain. **Fallback documentado:** si un plan futuro necesita alturas variables con medición dinámica (p.ej. virtualizar TicketBoard), ahí se evalúa `@tanstack/react-virtual` en SU plan, con jsdom como prerequisito; este plan deja la API del hook compatible con ese reemplazo (misma forma `{start, end, padTopPx, padBottomPx}`).

---

## 4. Fases

**Orden de dependencia:** F0 → F1 → F2 → F3 → F4 → F5. Cada fase es autocontenida, verificable sola y deja el árbol verde.

---

### F0 — Flags backend: alta doble con default ON + campos en `/api/diag/health`

**Objetivo (1 frase):** dar de alta `STACKY_UI_VIRTUALIZATION_ENABLED` y `STACKY_UI_PREFETCH_ENABLED` (bool, default ON, editables por UI de Settings) y exponerlas al frontend por el mecanismo canónico del plan 139, para que todo lo demás del plan tenga kill-switch desde el día cero.
**Valor:** kill-switch instantáneo por flag + cumplimiento de la regla dura "configurable desde la UI".

**Archivos a editar (exactos):**
1. `Stacky Agents/backend/config.py`
2. `Stacky Agents/backend/services/harness_flags.py`
3. `Stacky Agents/backend/services/harness_flags_help.py`
4. `Stacky Agents/backend/tests/test_harness_flags.py` (solo el set `_CURATED_DEFAULTS_ON`)
5. `Stacky Agents/backend/api/diag.py`
6. `Stacky Agents/backend/scripts/run_harness_tests.sh` y `Stacky Agents/backend/scripts/run_harness_tests.ps1` (registro del test nuevo)

**Archivo a crear:** `Stacky Agents/backend/tests/test_plan174_ui_perf_flags.py`

**Tests PRIMERO (TDD).** Crear `tests/test_plan174_ui_perf_flags.py` con el patrón exacto de `tests/test_plan131_incident_flag.py` (fixtures `app_flag_on`/`app_flag_off` con `create_app()` + `TESTING=True` + mutación de `cfg.config` con restore; NUNCA `create_app()` fuera de pytest). Casos, con estos nombres exactos:

- `test_virtualization_flag_default_on` — `monkeypatch.delenv("STACKY_UI_VIRTUALIZATION_ENABLED", raising=False)`; `importlib.reload(config)`; assert `config.config.STACKY_UI_VIRTUALIZATION_ENABLED is True`; reload final para restaurar.
- `test_prefetch_flag_default_on` — ídem para `STACKY_UI_PREFETCH_ENABLED`.
- `test_flagspecs_registered_and_categorized` — para cada una de las 2 keys: existe `FlagSpec` en `FLAG_REGISTRY` con `type == "bool"`, `default is True`, `env_only is False`, y la key está en `_CATEGORY_KEYS["interfaz_ui"]`.
- `test_plain_help_entries` — `PLAIN_HELP` tiene entrada para ambas keys con `what/on_effect/off_effect/example` no vacíos (respetar denylist de jerga de `tests/test_harness_flags_help.py`).
- `test_health_exposes_ui_perf_fields` — con fixture `app` (patrón `app_flag_on` sin tocar flags), `client.get("/api/diag/health")` → 200 y el JSON contiene `"ui_virtualization_enabled"` y `"ui_prefetch_enabled"` como bool.
- `test_health_fields_follow_config` — fixture que setea `cfg.config.STACKY_UI_PREFETCH_ENABLED = False` (con restore) → el campo `ui_prefetch_enabled` del health es `False`.

Correr y verlos FALLAR por la razón correcta (flags inexistentes):
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q
```

**Implementación (cambio mínimo):**

(a) `config.py` — junto al bloque de flags UI (ancla: el bloque de `STACKY_UI_SHELL_V2_ENABLED`, patrón `config.py:1300-1302` pero con default `"true"`):
```python
# Plan 174 — Rendimiento percibido. Default ON: solo cambia CÓMO se pinta lo
# que ya se pinta (ventana de render) y agrega prefetch de lectura con techo
# duro. OFF = comportamiento actual byte-idéntico.
STACKY_UI_VIRTUALIZATION_ENABLED: bool = os.getenv(
    "STACKY_UI_VIRTUALIZATION_ENABLED", "true"
).strip().lower() == "true"

STACKY_UI_PREFETCH_ENABLED: bool = os.getenv(
    "STACKY_UI_PREFETCH_ENABLED", "true"
).strip().lower() == "true"
```

(b) `harness_flags.py` — dos ediciones: (b1) en `_CATEGORY_KEYS["interfaz_ui"]` (`:325-327`) agregar las 2 keys con comentario `# Plan 174 — ...`; (b2) en `FLAG_REGISTRY`, junto a la `FlagSpec` de `STACKY_UI_SHELL_V2_ENABLED` (`:3180-3192`), agregar 2 `FlagSpec` con `default=True` (patrón `default=True` explícito de `CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED`, `:337`):
```python
FlagSpec(
    key="STACKY_UI_VIRTUALIZATION_ENABLED",
    type="bool",
    default=True,
    label="Listas largas virtualizadas",
    description=(
        "Plan 174 — Las listas largas (logs de ejecución, diferencias del "
        "comparador de BD) renderizan solo la ventana visible (~60 filas) en "
        "lugar de miles de nodos. Solo cambia el render; mismos datos. "
        "Con OFF la interfaz se comporta exactamente como hasta ahora."
    ),
    group="global",
),
FlagSpec(
    key="STACKY_UI_PREFETCH_ENABLED",
    type="bool",
    default=True,
    label="Precarga al apuntar + navegación instantánea",
    description=(
        "Plan 174 — Al posar el mouse o el foco sobre una fila de ejecución, "
        "el detalle se precarga (máximo 1 pedido a la vez) para que el panel "
        "abra al instante; paginar y volver atrás pinta desde memoria y "
        "revalida en segundo plano. Con OFF, comportamiento actual."
    ),
    group="global",
),
```
- **Anti-gotcha (recurrido 6 veces en la serie):** la prosa de comentarios NO debe colisionar con greps-gate de otros planes; no escribir literales de diálogos nativos ni `style={{` en comentarios.

(c) `harness_flags_help.py` — 2 entradas `PlainHelp` en `PLAIN_HELP` (formato on/off del archivo, sin jerga de la denylist).

(d) `tests/test_harness_flags.py` — agregar las 2 keys al set `_CURATED_DEFAULTS_ON` (`:467`). Es la vía canónica para default ON (si no: rompe `test_default_known_only_for_curated`).

(e) `api/diag.py` — en el dict de retorno de `health()`, inmediatamente después de la línea de `shell_v2_enabled` (`diag.py:411`), agregar:
```python
"ui_virtualization_enabled": bool(getattr(_config.config, "STACKY_UI_VIRTUALIZATION_ENABLED", True)),  # Plan 174
"ui_prefetch_enabled": bool(getattr(_config.config, "STACKY_UI_PREFETCH_ENABLED", True)),  # Plan 174
```
(fallback `True` = coherente con default ON; aditivo puro, ningún consumidor existente se rompe).

(f) Registrar `tests/test_plan174_ui_perf_flags.py` en `HARNESS_TEST_FILES` de `scripts/run_harness_tests.sh` (lista `:20`, orden alfabético del bloque donde caiga) **y** en la lista homóloga de `scripts/run_harness_tests.ps1`.

**Criterio de aceptación (binario):**
```
venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q   → exit 0
venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q          → exit 0
venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q     → exit 0
grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.sh      → 1
grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.ps1     → 1
```
**Flag que protege la fase:** las 2 flags SON la fase; default ON.
**Runtimes / fallback:** backend de lectura pura; idéntico para los 3 runtimes (no toca ejecución). Fallback: si el health falla, el frontend asume ON (fail-open coherente con default ON, §F1).
**Trabajo del operador: ninguno.**

---

### F1 — Núcleo puro: `virtualWindow.ts` + `useVirtualList` + `useUiPerfFlags`

**Objetivo (1 frase):** crear el motor de virtualización como función pura 100% testeada + el hook React fino que la aplica, y el hook de lectura de flags (1 request por sesión).
**Valor:** toda la lógica riesgosa queda testeable sin DOM; F2 se vuelve puro wiring.

**Archivos a crear (exactos):**
1. `Stacky Agents/frontend/src/utils/virtualWindow.ts` (módulo puro, sin imports de React)
2. `Stacky Agents/frontend/src/utils/__tests__/virtualWindow.test.ts`
3. `Stacky Agents/frontend/src/hooks/useVirtualList.ts`
4. `Stacky Agents/frontend/src/hooks/useUiPerfFlags.ts`

**Test PRIMERO.** `src/utils/__tests__/virtualWindow.test.ts` — casos exactos (todos sobre `computeVirtualWindow` y `shouldVirtualize`):
1. `total=0` → `{start:0, end:0, padTopPx:0, padBottomPx:0, rendered:0}`.
2. Viewport más alto que el contenido total → renderiza todo (`start=0, end=total`), pads 0.
3. `scrollTopPx` más allá del final → clamp (nunca `start > total`, nunca pads negativos).
4. `overscan` negativo → se trata como 0.
5. `pinnedIndex` fuera de la ventana calculada → la ventana se EXTIENDE para incluirlo (dependencia blanda con el foco roving del plan 172).
6. **Presupuesto (KPI-1):** `total=5000, rowHeightPx=22, viewportHeightPx=600, scrollTopPx=50_000, overscan=10` → `rendered ≤ 60` **y** `padTopPx + rendered*22 + padBottomPx === 5000*22`.
7. Invariante de continuidad: `start ≤ end`, `end - start === rendered`, `padTopPx === start*rowHeightPx`.
8. `shouldVirtualize(150, true) === false` (bajo el umbral), `shouldVirtualize(201, true) === true`, `shouldVirtualize(5000, false) === false` (flag OFF).

Comando (debe FALLAR primero por módulo inexistente):
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/utils/__tests__/virtualWindow.test.ts
```

**Implementación — `virtualWindow.ts` (contrato exacto):**
```ts
export const VIRTUALIZATION_THRESHOLD = 200; // por debajo: render directo (Ctrl+F del navegador intacto)
export const DEFAULT_OVERSCAN = 10;

export interface VirtualWindowInput {
  total: number;            // cantidad total de filas
  rowHeightPx: number;      // altura FIJA de fila en px (>0)
  viewportHeightPx: number; // alto visible del contenedor
  scrollTopPx: number;      // scroll actual del contenedor
  overscan?: number;        // filas extra arriba/abajo (default DEFAULT_OVERSCAN)
  pinnedIndex?: number | null; // índice que DEBE quedar dentro de la ventana (foco roving, plan 172)
}

export interface VirtualWindow {
  start: number;      // primer índice renderizado (inclusive)
  end: number;        // último índice renderizado (exclusive) — slice(start, end)
  padTopPx: number;   // alto del spacer superior
  padBottomPx: number;// alto del spacer inferior
  rendered: number;   // end - start
}

export function computeVirtualWindow(input: VirtualWindowInput): VirtualWindow {
  // 1. Normalizar: overscan = max(0, overscan ?? DEFAULT_OVERSCAN); total/heights clamp ≥ 0.
  // 2. firstVisible = floor(scrollTopPx / rowHeightPx); clamp a [0, max(0,total-1)].
  // 3. visibleCount = ceil(viewportHeightPx / rowHeightPx) + 1 (fila parcial de borde).
  // 4. start = max(0, firstVisible - overscan); end = min(total, firstVisible + visibleCount + overscan).
  // 5. Si pinnedIndex != null y 0 ≤ pinnedIndex < total: start = min(start, pinnedIndex); end = max(end, pinnedIndex + 1).
  // 6. padTopPx = start * rowHeightPx; padBottomPx = (total - end) * rowHeightPx.
}

export function shouldVirtualize(total: number, flagEnabled: boolean): boolean {
  return flagEnabled && total >= VIRTUALIZATION_THRESHOLD;
}
```

**`useVirtualList.ts` (hook fino; contrato exacto):**
```ts
import { useCallback, useRef, useState } from "react";
import { computeVirtualWindow, shouldVirtualize, type VirtualWindow } from "../utils/virtualWindow";

export interface UseVirtualListOptions {
  total: number;
  rowHeightPx: number;
  enabled: boolean;             // pasar shouldVirtualize(total, flag) o el flag directo
  overscan?: number;
  pinnedIndex?: number | null;  // plan 172 (blanda): sin 172 nadie lo pasa y no cambia nada
}
export interface UseVirtualListResult extends VirtualWindow {
  isVirtualized: boolean;                       // false ⇒ render directo, sin listeners
  containerRef: React.RefObject<HTMLDivElement>;// va al contenedor scrolleable
  onScroll: () => void;                         // va al onScroll del contenedor
  scrollToIndex: (i: number) => void;           // containerRef.scrollTop = i * rowHeightPx
}
```
Semántica: estado interno `scrollTopPx` actualizado en `onScroll` leyendo `containerRef.current.scrollTop` (throttle vía `requestAnimationFrame`: 1 recomputo por frame como máximo); `viewportHeightPx` leído de `containerRef.current.clientHeight` en el mismo callback (fallback 600 si el ref aún no montó). Con `isVirtualized === false` devuelve `{start:0, end:total, padTopPx:0, padBottomPx:0}` y `onScroll` es no-op. **Sin ResizeObserver ni efectos de layout** — mantenerlo mínimo; el recomputo en scroll cubre el caso real.

**`useUiPerfFlags.ts` (lectura de flags, 1 request por sesión):**
```ts
import { useQuery } from "@tanstack/react-query";

export interface UiPerfFlags { virtualization: boolean; prefetch: boolean; }
const DEFAULTS: UiPerfFlags = { virtualization: true, prefetch: true }; // fail-open = default ON

export function useUiPerfFlags(): UiPerfFlags {
  const q = useQuery({
    queryKey: ["ui-perf-flags"],
    queryFn: async (): Promise<UiPerfFlags> => {
      const r = await fetch("/api/diag/health");
      const d = await r.json();
      return {
        virtualization: d.ui_virtualization_enabled !== false,
        prefetch: d.ui_prefetch_enabled !== false,
      };
    },
    staleTime: Infinity,   // 1 request por sesión: NO suma al presupuesto por tick del plan 156
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: 0,
    placeholderData: DEFAULTS,
  });
  return q.data ?? DEFAULTS;
}
```
Mecanismo idéntico al del plan 139 (§3.3): campo aditivo de `/api/diag/health`; toggle desde Settings requiere recargar la página, igual que shell v2 (`App.tsx:152-153`, comentario "recargar la página para ver el efecto").

**Criterio de aceptación (binario):** `npx vitest run src/utils/__tests__/virtualWindow.test.ts` → exit 0 **y** `npx tsc --noEmit` → exit 0.
**Flag:** `STACKY_UI_VIRTUALIZATION_ENABLED` (motor) / `STACKY_UI_PREFETCH_ENABLED` (hook de flags la lee también) — default ON.
**Runtimes / fallback:** código frontend puro, idéntico para los 3 runtimes. Fallback: health caído ⇒ `DEFAULTS` (fail-open, cosmético).
**Trabajo del operador: ninguno.**

---

### F2 — Virtualizar las 2 listas largas reales: LogsPanel y DiffList

**Objetivo (1 frase):** aplicar `useVirtualList` a `LogsPanel.tsx` (stream de logs, miles de líneas hoy sin cota; ≤5.000 cuando aterrice 156) y a `DiffList.tsx` (miles de objetos de diff), preservando autoscroll y comportamiento con flag OFF.
**Valor:** el panel de logs y el comparador dejan de degradar el frame-rate del dashboard entero en ejecuciones largas.

**Archivos a editar (exactos):**
1. `Stacky Agents/frontend/src/components/LogsPanel.tsx` (+ su `LogsPanel.module.css`)
2. `Stacky Agents/frontend/src/components/dbcompare/DiffList.tsx` (+ `dbcompare/dbcompare.module.css`)

**Archivos a crear:**
3. `Stacky Agents/frontend/src/utils/stickToBottom.ts`
4. `Stacky Agents/frontend/src/utils/__tests__/stickToBottom.test.ts`

**Pre-flight obligatorio (sesión paralela):** `git status -- "Stacky Agents/frontend/src/components/LogsPanel.tsx" "Stacky Agents/frontend/src/components/dbcompare/DiffList.tsx"` → si hay WIP ajeno, STOP.

**Test PRIMERO.** `src/utils/__tests__/stickToBottom.test.ts` sobre el módulo puro:
```ts
// stickToBottom.ts
export const STICK_SLACK_PX = 40;
export function isPinnedToBottom(scrollTopPx: number, viewportHeightPx: number, contentHeightPx: number, slackPx = STICK_SLACK_PX): boolean {
  return contentHeightPx - (scrollTopPx + viewportHeightPx) <= slackPx;
}
```
Casos: exactamente al fondo → true; a 39 px del fondo → true; a 41 px → false; contenido más chico que viewport → true; valores 0 → true.
Comando: `npx vitest run src/utils/__tests__/stickToBottom.test.ts` (falla primero por módulo inexistente).

**Implementación — LogsPanel (`LogsPanel.tsx`, hoy 38 líneas):**
1. `const flags = useUiPerfFlags();` y `const virt = useVirtualList({ total: stream.lines.length, rowHeightPx: LOG_ROW_HEIGHT_PX, enabled: flags.virtualization });` con `const LOG_ROW_HEIGHT_PX = 20;` (constante del archivo).
2. CSS: en `LogsPanel.module.css` agregar `.virtualLine { height: 20px; line-height: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }`. Cuando `virt.isVirtualized`, cada fila lleva `className={`${styles.line} ${styles.virtualLine} ${styles[l.level]}`}` (altura fija = requisito del motor). Cuando NO (flag OFF o <200 líneas), el render es EXACTAMENTE el actual (`:27-34`), wrap incluido.
3. Render virtualizado: reemplazar `stream.lines.map(...)` por
   `stream.lines.slice(virt.start, virt.end).map((l, i) => ... key={virt.start + i} ...)` entre dos spacers `<div ref={padTopRef} />` / `<div ref={padBottomRef} />` cuyas alturas se setean por **ref + effect imperativo** (`padTopRef.current.style.height = `${virt.padTopPx}px``) — **prohibido `style={{}}`** (ratchet plan 138).
4. Contenedor: `<div className={styles.body} ref={virt.containerRef} onScroll={virt.onScroll}>` (el `ref` actual `:11` pasa a ser `virt.containerRef`; unificar).
5. Autoscroll (reemplaza `:13-15`): en el mismo `useEffect` dependiente de `stream.lines.length`, si `isPinnedToBottom(el.scrollTop, el.clientHeight, el.scrollHeight)` era true ANTES de agregar líneas ⇒ `virt.scrollToIndex(stream.lines.length - 1)`; si el operador scrolleó arriba, NO se lo arrastra al fondo (mejora deliberada y documentada; hoy `:13-15` arrastra siempre).

**Implementación — DiffList (`DiffList.tsx`, hoy 43 líneas):**
1. Mantener `PAGE_SIZE`/`visibleCount`/botón "Mostrar 100 más" SOLO para el camino flag OFF (byte-idéntico a hoy).
2. Camino flag ON (`shouldVirtualize(items.length, flags.virtualization)`): render de `items.slice(virt.start, virt.end)` con spacers imperativos (mismo patrón que LogsPanel), `rowHeightPx = DIFF_ROW_HEIGHT_PX = 32` + clase CSS `.diffRowVirtual { height: 32px; overflow: hidden; }` agregada a `dbcompare.module.css` y aplicada junto a `styles.diffRow`. El botón "Mostrar 100 más" NO se renderiza en este camino (la lista completa es scrolleable).
3. El contenedor scrolleable es el propio `styles.diffList` (agregar `overflow-y: auto` + `max-height` si no los tiene — verificar en `dbcompare.module.css`; si el scroll hoy lo maneja un ancestro, el implementador mueve `containerRef` a ESE ancestro y lo anota en el commit).
4. Nota: `DiffList.tsx:26` ya tiene un `style={{ background }}` (baseline del ratchet) — NO tocarlo, NO agregar otros.

**Dependencias blandas declaradas:**
- **Plan 172 (foco roving):** cuando 172 aterrice, su hook pasa `pinnedIndex` a `useVirtualList` para que la fila enfocada por teclado nunca se desmonte, y usa `scrollToIndex` para j/k. Sin 172: nadie pasa `pinnedIndex`, cero efecto.
- **Plan 156 (ring-buffer):** sin 156, `stream.lines` sigue sin cota en MEMORIA (gap de 156, no de este plan) pero el DOM ya queda acotado por la ventana. Con 156, memoria Y DOM acotados. Ninguno bloquea al otro.

**Criterio de aceptación (binario):**
```
npx vitest run src/utils/__tests__/stickToBottom.test.ts  → exit 0
npx vitest run src/__tests__/uiDebtRatchet.test.ts        → exit 0 (sin style={{ nuevos)
npx tsc --noEmit                                          → exit 0
```
más el check de adopción que se activa en F5 (KPI-3).
**Flag:** `STACKY_UI_VIRTUALIZATION_ENABLED` default ON; OFF ⇒ ambos componentes byte-idénticos a hoy.
**Runtimes / fallback:** render puro del dashboard; los logs que muestra vienen del mismo SSE para los 3 runtimes (`useExecutionStream`), así que la paridad se hereda. Fallback: <200 filas o flag OFF ⇒ render directo.
**Trabajo del operador: ninguno.**

---

### F3 — Prefetch on-hover/on-focus del detalle de ejecución (presupuesto duro)

**Objetivo (1 frase):** precargar `["execution-detail", id]` cuando el operador apunta una fila ≥150 ms, con máximo 1 prefetch en vuelo y cancelación al salir, para que `ExecutionDetailDrawer` abra pintado.
**Valor:** el gesto más frecuente del cockpit (abrir detalle de una ejecución) pasa de "spinner siempre" a instantáneo, gastando a lo sumo 1 GET que el click iba a gastar igual.

**Archivos a crear (exactos):**
1. `Stacky Agents/frontend/src/services/prefetchPolicy.ts` (módulo puro, sin React)
2. `Stacky Agents/frontend/src/services/__tests__/prefetchPolicy.test.ts`
3. `Stacky Agents/frontend/src/hooks/usePrefetchExecutionDetail.ts`

**Archivos a editar:** `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx`, `Stacky Agents/frontend/src/pages/ReviewInboxPage.tsx` (pre-flight `git status` por archivo, como en F2).

**Test PRIMERO.** `src/services/__tests__/prefetchPolicy.test.ts` con **timer inyectado manual** (objeto `{set, clear}` de test que colecciona callbacks; NO hace falta `vi.useFakeTimers`, el módulo es 100% puro). Casos exactos:
1. Sin `enter()` jamás ⇒ `run` nunca llamado (**0 requests sin interacción** — presupuesto 156).
2. `enter("a")` y avanzar el timer <150 ms ⇒ `run` no llamado todavía (debounce ≥ `PREFETCH_HOVER_DELAY_MS = 150`).
3. `enter("a")` + `leave("a")` antes del deadline ⇒ `run` NUNCA llamado (cancelación).
4. `enter("a")`, vence el debounce ⇒ `run("a")` llamado exactamente 1 vez; `enter("a")` de nuevo con la promesa aún en vuelo ⇒ NO se re-llama (dedup por key en vuelo).
5. Con `run("a")` en vuelo (promesa sin resolver), vence el debounce de `enter("b")` ⇒ `run("b")` **se descarta** (NO se encola): `inFlightCount()` nunca supera `PREFETCH_MAX_CONCURRENT = 1`.
6. Resuelta la promesa de "a", un `enter("b")` nuevo sí dispara.
7. `enter` repetido de la misma key con timer pendiente NO acumula timers (idempotente).

Comando: `npx vitest run src/services/__tests__/prefetchPolicy.test.ts` (falla primero).

**Implementación — `prefetchPolicy.ts` (contrato exacto):**
```ts
export const PREFETCH_HOVER_DELAY_MS = 150;
export const PREFETCH_MAX_CONCURRENT = 1;
export const PREFETCH_DETAIL_STALE_TIME_MS = 30_000; // = staleTime que ya usa la página (ExecutionHistoryPage.tsx:79)

export interface PrefetchTimer {
  set: (fn: () => void, ms: number) => number;
  clear: (id: number) => void;
}

export interface PrefetchScheduler {
  enter: (key: string) => void;   // hover/focus entra
  leave: (key: string) => void;   // hover/focus sale (cancela lo no disparado)
  inFlightCount: () => number;
  dispose: () => void;            // limpia todos los timers pendientes (unmount)
}

export function createPrefetchScheduler(
  run: (key: string) => Promise<unknown>,
  timer?: PrefetchTimer,          // default: setTimeout/clearTimeout reales
): PrefetchScheduler { /* semántica = los 7 casos del test, ni más ni menos */ }
```
Decisión documentada: lo que ya salió a la red NO se aborta (`prefetchQuery` no expone abort trivial y abortar un GET barato ya emitido cuesta más que dejarlo poblar la cache); el techo lo garantizan el debounce + `PREFETCH_MAX_CONCURRENT`.

**Implementación — `usePrefetchExecutionDetail.ts`:**
```ts
import { useMemo, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Executions } from "../api/endpoints";
import { createPrefetchScheduler, PREFETCH_DETAIL_STALE_TIME_MS } from "../services/prefetchPolicy";
import { useUiPerfFlags } from "./useUiPerfFlags";

/** Devuelve getPrefetchProps(id): props para esparcir en la fila. Flag OFF ⇒ {} (cero handlers). */
export function usePrefetchExecutionDetail() {
  const qc = useQueryClient();
  const { prefetch } = useUiPerfFlags();
  const scheduler = useMemo(
    () => createPrefetchScheduler((key) =>
      qc.prefetchQuery({
        queryKey: ["execution-detail", Number(key)],   // MISMA key y fn que ExecutionDetailDrawer.tsx:37-38
        queryFn: () => Executions.byId(Number(key)),
        staleTime: PREFETCH_DETAIL_STALE_TIME_MS,
      })),
    [qc],
  );
  useEffect(() => () => scheduler.dispose(), [scheduler]);
  return function getPrefetchProps(id: number) {
    if (!prefetch) return {};
    return {
      onMouseEnter: () => scheduler.enter(String(id)),
      onMouseLeave: () => scheduler.leave(String(id)),
      onFocus: () => scheduler.enter(String(id)),
      onBlur: () => scheduler.leave(String(id)),
    };
  };
}
```
**Alcance deliberado:** se prefetchea SOLO `execution-detail` (la query que pinta el cuerpo del drawer). `execution-output-files` (`ExecutionDetailDrawer.tsx:42-44`) queda lazy al abrir: mantener 1 GET por hover es parte del presupuesto.

**Wiring (2 páginas):**
- `ExecutionHistoryPage.tsx`: localizar el elemento de fila clickeable con `grep -n "setDetailId" src/pages/ExecutionHistoryPage.tsx` (el que hace `onClick={() => setDetailId(item.id)}` en el cuerpo de la tabla) y esparcirle `{...getPrefetchProps(item.id)}`.
- `ReviewInboxPage.tsx`: ídem con `grep -n "setDetailExecutionId"` (drawer en `:125`).
- NO se cablea en `DiagnosticsPage`/`AgentHistoryModal`/`CodexConsoleDock` (listas cortas o contexto modal; §7).

**Cumplimiento del presupuesto 156 (declaración normativa):** el prefetch NO agrega tráfico periódico: en idle absoluto (sin hover/focus) = **0 requests** (caso 1 del test). El KPI ≤2 req/tick del plan 156 queda intacto. `hover → click inmediato (<150 ms)` = 0 requests extra (el debounce no venció; el click dispara la query normal del drawer, igual que hoy).

**Dependencia blanda con 175:** el plan 175 (peek/hover-cards) DEBE consumir `createPrefetchScheduler` y sus constantes (mismo gate global de 1 en vuelo) en vez de crear su propio scheduler; este contrato queda exportado desde `prefetchPolicy.ts`. Sin 175, nada cambia.

**Criterio de aceptación (binario):**
```
npx vitest run src/services/__tests__/prefetchPolicy.test.ts → exit 0
npx tsc --noEmit                                             → exit 0
```
**Flag:** `STACKY_UI_PREFETCH_ENABLED` default ON; OFF ⇒ `getPrefetchProps` devuelve `{}` (cero handlers, cero requests).
**Runtimes / fallback:** el detalle prefetcheado es el mismo `Executions.byId` que ven los 3 runtimes; paridad heredada. Fallback: flag OFF o health caído sin campo ⇒ fail-open a ON solo si el campo falta (`!== false`); con flag OFF explícita ⇒ comportamiento actual.
**Trabajo del operador: ninguno.**

---

### F4 — Navegación instantánea: `queryTuning.ts` + `placeholderData` sin parpadeo

**Objetivo (1 frase):** centralizar staleTime/gcTime por tipo de query en un módulo puro y aplicar `placeholderData: keepPreviousData` a las 2 páginas paginadas que hoy parpadean, para que paginar/filtrar mantenga la tabla visible y volver atrás pinte desde cache.
**Valor:** elimina el "flash de vacío" (el defecto de percepción más visible del cockpit) sin una request extra.

**Archivos a crear (exactos):**
1. `Stacky Agents/frontend/src/services/queryTuning.ts`
2. `Stacky Agents/frontend/src/services/__tests__/queryTuning.test.ts`

**Archivos a editar:** `Stacky Agents/frontend/src/pages/ExecutionHistoryPage.tsx`, `Stacky Agents/frontend/src/pages/SystemLogsPage.tsx` (+ sus `.module.css`) — pre-flight `git status` por archivo.

**Test PRIMERO.** `src/services/__tests__/queryTuning.test.ts`:
1. `QUERY_TUNING.history.staleTime === 30_000` (idéntico al actual `ExecutionHistoryPage.tsx:79` — el tuning NO acelera ni frena revalidación, solo agrega retención).
2. `QUERY_TUNING.systemLogs.staleTime === 10_000` (idéntico al actual `SystemLogsPage.tsx:153`).
3. Todo `gcTime ≥ 10 * 60_000` (volver atrás dentro de 10 min pinta desde cache) y todo `gcTime > staleTime`.
4. `tuningFor("history")` devuelve el objeto exacto y tipa por literal (compile-time + runtime).

Comando: `npx vitest run src/services/__tests__/queryTuning.test.ts` (falla primero).

**Implementación — `queryTuning.ts`:**
```ts
/** Plan 174 — retención por tipo de query. staleTime = cuándo revalidar (SE PRESERVAN
 *  los valores actuales de cada página); gcTime = cuánto retener para pintar-desde-cache
 *  al volver. NO tocar el default global de main.tsx:10. */
export const QUERY_TUNING = {
  history:         { staleTime: 30_000, gcTime: 10 * 60_000 },
  systemLogs:      { staleTime: 10_000, gcTime: 10 * 60_000 },
  executionDetail: { staleTime: 30_000, gcTime: 10 * 60_000 },
} as const;

export type QueryTuningKind = keyof typeof QUERY_TUNING;
export function tuningFor(kind: QueryTuningKind): { staleTime: number; gcTime: number } {
  return QUERY_TUNING[kind];
}
```

**Edición — `ExecutionHistoryPage.tsx` (query `:67-80`):**
```ts
import { keepPreviousData } from "@tanstack/react-query";
import { tuningFor } from "../services/queryTuning";
// en historyQ:
placeholderData: keepPreviousData,
...tuningFor("history"),        // reemplaza el staleTime: 30_000 literal
```
y feedback visual del dato provisorio SIN inline style: el contenedor de la tabla lleva `data-stale={historyQ.isPlaceholderData || undefined}` y en `ExecutionHistoryPage.module.css` se agrega `[data-stale] { opacity: 0.6; transition: opacity 120ms ease; }` (patrón de microinteracción, plan 143). El contador de resultados (`:104`) durante placeholder muestra los datos previos — correcto, porque son los que se están viendo.

**Edición — `SystemLogsPage.tsx` (query `:150-155`):** ídem — `placeholderData: keepPreviousData` + `...tuningFor("systemLogs")` (reemplaza el `staleTime: 10_000` literal; el `refetchInterval: 30_000` existente NO se toca) + `data-stale` en `styles.tableWrap` con la misma regla CSS en `SystemLogsPage.module.css`. Con esto, "Loading logs…" (`:293-294`) queda SOLO para la primera carga (`isLoading` es false con placeholder presente — semántica react-query v5).

**Edición — `ExecutionDetailDrawer.tsx` (opcional-recomendada, 1 línea):** agregar `...tuningFor("executionDetail")` a `execQ` (`:36-40`) para que reabrir el mismo detalle dentro de los 30 s pinte desde cache (coherente con F3). Si el archivo tiene WIP ajeno ⇒ se omite y se anota (dependencia de F3: el prefetch ya setea `staleTime` equivalente vía `prefetchQuery`).

**Gate de flag:** `placeholderData`/`gcTime` son tuning de cache local sin efecto de red adicional; quedan bajo `STACKY_UI_PREFETCH_ENABLED` conceptualmente pero SIN branch condicional en el código (un branch por flag acá duplicaría cada `useQuery`; el kill-switch real es revert del commit de F4, y así se documenta). El criterio: flag OFF apaga lo que gasta red (F3); F4 no gasta red.

**Criterio de aceptación (binario):**
```
npx vitest run src/services/__tests__/queryTuning.test.ts → exit 0
npx tsc --noEmit                                          → exit 0
```
**Runtimes / fallback:** cache local del dashboard; paridad por vacuidad. Fallback: sin cache retenida (primera visita) el comportamiento es el actual.
**Trabajo del operador: ninguno.**

---

### F5 — Adopción verificada + cierre integral

**Objetivo (1 frase):** fijar con un test fs+regex (precedente plan 140) que la adopción de F2/F3/F4 está realmente cableada, y correr la batería integral de cierre.
**Valor:** el plan no se puede "implementar a medias" sin que un test lo delate; la adopción queda ratcheteada.

**Archivo a crear:** `Stacky Agents/frontend/src/__tests__/plan174Adoption.test.ts`

**Test (es la fase):** lee los archivos fuente con `fs.readFileSync` (patrón exacto de los tests de adopción del plan 140 y del `uiDebtRatchet`) y asserta:
1. `src/components/LogsPanel.tsx` contiene `useVirtualList(` y NO contiene `stream.lines.map(` **fuera** del camino no-virtualizado (assert simple: contiene `virt.start` y `virt.end`).
2. `src/components/dbcompare/DiffList.tsx` contiene `useVirtualList(` y conserva `PAGE_SIZE` (camino flag OFF intacto).
3. `src/pages/ExecutionHistoryPage.tsx` contiene `placeholderData: keepPreviousData` y `getPrefetchProps(`.
4. `src/pages/SystemLogsPage.tsx` contiene `placeholderData: keepPreviousData`.
5. `src/pages/ReviewInboxPage.tsx` contiene `getPrefetchProps(`.
6. `src/hooks/useVirtualList.ts` contiene `requestAnimationFrame` (throttle presente).
7. Anti-regresión de presupuesto: `src/services/prefetchPolicy.ts` contiene `PREFETCH_MAX_CONCURRENT = 1` y `PREFETCH_HOVER_DELAY_MS = 150` (los valores son parte del contrato con 156 y 175; cambiarlos exige tocar este test a conciencia).

**Anti-gotcha (6 recurrencias históricas):** los patrones que busca este test NO deben aparecer en comentarios de los archivos objetivo más allá del código real; y este test NO debe matchearse a sí mismo (excluir `src/__tests__/` del escaneo).

**Cierre integral (comandos exactos, todos deben dar exit 0):**
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npx vitest run src/__tests__/plan174Adoption.test.ts
npx vitest run src/utils/__tests__/virtualWindow.test.ts
npx vitest run src/utils/__tests__/stickToBottom.test.ts
npx vitest run src/services/__tests__/prefetchPolicy.test.ts
npx vitest run src/services/__tests__/queryTuning.test.ts
npx vitest run src/__tests__/uiDebtRatchet.test.ts
npx tsc --noEmit

cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q
```
**Runtimes / fallback:** N/A (fase de verificación).
**Trabajo del operador: ninguno.**

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | **Ctrl+F del navegador deja de encontrar filas desmontadas** en listas virtualizadas (solo existen ~60 nodos). | (a) Umbral `VIRTUALIZATION_THRESHOLD = 200`: por debajo, render completo y Ctrl+F intacto; (b) sobre el umbral, el camino canónico de búsqueda son los **filtros propios de cada pantalla** (SystemLogs/Historial tienen filtros server-side; DbCompare filtra upstream de DiffList; el log completo vive en disco backend — Ctrl+F sobre 5.000 líneas ya era impracticable); (c) el riesgo queda declarado acá a propósito: NO se oculta. Si el operador lo reporta como molestia, el kill-switch es la flag en Settings. |
| R2 | **Líneas de log largas**: el modo virtualizado exige altura fija ⇒ `nowrap + ellipsis`, se pierde el wrap actual. | Solo aplica con >200 líneas y flag ON; el texto completo sigue en `title`/detalle y en el archivo de log backend. Flag OFF restaura wrap. Documentado como trade-off consciente, no efecto colateral. |
| R3 | **Regresión de autoscroll** en LogsPanel (hoy arrastra siempre al fondo, `:13-15`). | Helper puro `isPinnedToBottom` testeado + semántica explícita: pegado al fondo ⇒ sigue; scrolleado arriba ⇒ no arrastra (mejora deliberada). Smoke manual en DoD. |
| R4 | **Prefetch sirve datos viejos** (ejecución en curso que cambia entre hover y click). | `PREFETCH_DETAIL_STALE_TIME_MS = 30_000` = mismo staleTime que la página usa hoy (`:79`); al montar el drawer, react-query revalida en background si pasó el umbral (refetchOnMount default). Ventana de obsolescencia ≤ la ya aceptada hoy. |
| R5 | **Violación del presupuesto de red del plan 156** por hovers frenéticos. | Debounce ≥150 ms + `PREFETCH_MAX_CONCURRENT = 1` con DESCARTE (no cola) + cancelación en leave + 0 tráfico sin interacción — cada propiedad tiene test propio (KPI-2) y el valor está ratcheteado por el test de adopción (F5.7). |
| R6 | **`placeholderData` muestra datos de la página anterior** como si fueran los nuevos. | Atenuación visual `data-stale` (opacity 0.6) mientras `isPlaceholderData` — el operador VE que está llegando lo nuevo; patrón de microinteracciones del plan 143. |
| R7 | **Sesión paralela viva en el repo** (WIP ajeno confirmado creciente). | Pre-flight `git status -- <ruta>` antes de CADA archivo en CADA fase; STOP ante WIP ajeno; anclas por texto, no por línea; commits con pathspec explícito. |
| R8 | **Drift de `gcTime` infla memoria del navegador.** | `gcTime` 10 min solo en 3 tipos de query paginadas/detalle (datos chicos, JSON de decenas de KB); el default global de `main.tsx:10` NO se toca; test de queryTuning fija `gcTime > staleTime` y valores exactos. |
| R9 | **El toggle de flag no surte efecto en caliente.** | Igual que shell v2 (plan 139): efecto al recargar la página; la descripción de la FlagSpec y el PLAIN_HELP lo dicen. Es el precedente aceptado del repo. |

---

## 6. Fuera de scope (y qué hermano lo cubre)

- **Atajos de teclado, overlay "?", foco roving j/k** → plan **172**. Este plan solo deja el enchufe (`pinnedIndex`/`scrollToIndex` en `useVirtualList`).
- **Vistas guardadas, presets de filtros, columnas/sort/anchos persistentes, restauración de última vista** → plan **173** (ortogonal: la virtualización es ventana de RENDER, no de datos; los presets de 173 no interactúan con ella).
- **Hover-cards/peek de entidades, menú contextual, acciones rápidas inline** → plan **175** (que CONSUME `createPrefetchScheduler` de F3 como contrato, §F3).
- **Ring-buffer del stream, endpoint summary, poller central, supresión de access-log** → plan **156** (este plan respeta su presupuesto pero no implementa nada de eso).
- **Virtualizar TicketBoard** (jerárquico, alturas variables, volumen moderado — `TicketBoard.tsx:1139,1157`) → si algún día hace falta, plan propio con evaluación de `@tanstack/react-virtual` (§3.4).
- **Prefetch de `execution-output-files`, prefetch en DiagnosticsPage/modales** → deliberadamente fuera (presupuesto 1 GET por hover; listas cortas).
- **Instalar jsdom/@testing-library** → gap estructural conocido del repo, no lo resuelve este plan.

---

## 7. Glosario corto (términos Stacky)

- **Virtualización / ventana de render:** renderizar solo las filas visibles (+overscan) de una lista, con 2 spacers que preservan la altura total del scroll.
- **Overscan:** filas extra renderizadas fuera del viewport para que el scroll rápido no muestre huecos.
- **Prefetch:** poblar la cache de react-query ANTES del click (`prefetchQuery`), para que la query del componente encuentre el dato ya resuelto.
- **staleTime / gcTime:** react-query v5 — tiempo en que un dato se considera fresco (no se refetchea) / tiempo que un dato sin suscriptores se retiene en cache antes de ser recolectado.
- **placeholderData: keepPreviousData:** al cambiar la queryKey (paginar/filtrar), se muestra el resultado anterior marcado `isPlaceholderData` hasta que llega el nuevo.
- **Tick / latido:** ciclo de polling de la UI (plan 156); presupuesto idle ≤2 requests/tick.
- **Ratchet:** test que impide que una métrica de deuda empeore (`uiDebtRatchet` = inline styles; `HARNESS_TEST_FILES` = registro de tests backend).
- **Flag curada:** flag bool con `default=True` declarada en `_CURATED_DEFAULTS_ON` (única vía canónica de default ON).
- **Stick-to-bottom:** autoscroll de un log SOLO cuando el usuario ya estaba pegado al fondo.
- **Fail-open:** ante error leyendo la flag, asumir su default (acá ON) para no degradar la experiencia por un health caído.

## 8. Orden de implementación

1. **F0** — flags backend + health + registro en `HARNESS_TEST_FILES` (sh y ps1).
2. **F1** — `virtualWindow.ts` (test primero) + `useVirtualList` + `useUiPerfFlags`.
3. **F2** — LogsPanel + DiffList virtualizados (test `stickToBottom` primero; pre-flight git por archivo).
4. **F3** — `prefetchPolicy.ts` (test primero) + hook + wiring en Historial y Review Inbox.
5. **F4** — `queryTuning.ts` (test primero) + `placeholderData` en Historial y System Logs.
6. **F5** — test de adopción + batería integral de cierre.

## 9. Definición de Hecho (DoD) global

- [ ] KPI-1..KPI-7 de §1: todos exit 0, con output real pegado (cero falsos verdes; la verificación final la corre y la LEE el agente principal).
- [ ] Ambas flags visibles y toggleables en la UI de Settings (panel de flags), con ayuda en lenguaje llano.
- [ ] Con ambas flags OFF (toggle + recarga): LogsPanel, DiffList, Historial, System Logs y Review Inbox se comportan como HOY (smoke visual).
- [ ] Smoke manual (deploy o dev): (1) ejecución con >1.000 líneas de log → scroll fluido y ≤~60 filas en el inspector DOM; (2) diff de BD con >200 objetos → scroll continuo sin botón "Mostrar 100 más"; (3) hover 1 s sobre una fila del historial → abrir → drawer pintado sin spinner; (4) paginar historial y logs → la tabla no desaparece, se atenúa; (5) ir a otra pantalla y volver → pinta al instante y revalida en background (ver request en Network, no spinner).
- [ ] En idle absoluto (sin mouse/teclado, pestaña visible) el panel Network no muestra NINGUNA request nueva atribuible a este plan.
- [ ] `git status` final sin archivos ajenos tocados; commits con pathspec explícito.
- [ ] Doc del plan actualizado a IMPLEMENTADO con desvíos anotados (regla del pipeline).
