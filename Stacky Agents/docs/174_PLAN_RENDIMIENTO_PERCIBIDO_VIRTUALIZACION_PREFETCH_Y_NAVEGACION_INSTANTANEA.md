# Plan 174 — Rendimiento percibido: virtualización de listas largas, prefetch on-hover y navegación instantánea

**Serie UX Cockpit del Operador (172-175) — plan 3/4 — v2 CRITICADO (APROBADO-CON-CAMBIOS) — 2026-07-18**

> **Estado:** CRITICADO v2 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode (perfil normal) · **Juez:** StackyArchitectaUltraEficientCode (perfil normal, Opus 4.8)

## Changelog v1 → v2 (crítica adversarial aplicada)

Veredicto del juez: **APROBADO-CON-CAMBIOS** (2 BLOQUEANTES + 3 IMPORTANTES + 2 MENORES corregidos). Cambios:

- **C1 (BLOQUEANTE) — F4 sin gate de flag.** El v1 (§F4 final) dejaba `placeholderData`/`gcTime`/`data-stale` SIN branch de flag, con "el kill-switch real es revert del commit". Contradecía la DoD (§9: "con ambas flags OFF… System Logs se comportan como HOY") y viola la regla dura "toda fase que agregue comportamiento tiene gate de flag configurable por UI, no git-revert". **Fix:** F4 se gatea con una **3ra flag nueva `STACKY_UI_INSTANT_NAV_ENABLED`** (bool, default ON, `env_only=False`, editable en Settings) vía ternario en cada `useQuery` afectada (no duplica el `useQuery`; es 1 expresión). Ver F0 (alta triple) y F4.
- **C2 (BLOQUEANTE) — premisa de plan 156 obsoleta.** El v1 afirmaba en §2.1/§2.4/§F2 que 156 "aún no implementado", que `LogsPanel` mapea todo en `:27` (`stream.lines.map`) y autoscrollea en `:13-15`. **Evidencia real 2026-07-18:** `LogsPanel.tsx` YA tiene Plan 156 F3 — `RENDER_CAP = 2000` (`:9`), render `stream.lines.slice(-RENDER_CAP).map(...)` (`:34`), banner `dropped` (`:31-33`), autoscroll en `:17-19`. F2 se reescribió contra el código REAL y reconcilia con `RENDER_CAP` + banner `dropped`.
- **C3 (IMPORTANTE) — `useVirtualList.enabled` ambiguo + call sites inconsistentes.** LogsPanel pasaba el flag crudo y DiffList `shouldVirtualize(...)`; el contrato no fijaba si el hook aplica el umbral 200. **Fix:** contrato pinneado — el hook recibe el **flag crudo** y aplica `shouldVirtualize(total, enabled)` internamente vía el helper puro `deriveIsVirtualized` (testeado); ambos call sites pasan el flag crudo.
- **C4 (IMPORTANTE) — line-cites obsoletos.** Sesión paralela editó los archivos; las citas `archivo:línea` de §1/§2/§F0/§F4 estaban corridas (ExecutionHistoryPage `historyQ` en `:115` no `:67-80`; SystemLogsPage `staleTime` en `:181` no `:153`; harness_flags FlagSpec shell v2 en `:3239` no `:3180-3192`). **Fix:** citas marcadas como orientativas y **anclaje 100% por texto** reforzado; además F4 aclara que SystemLogsPage tiene DOS queries (`:178` staleTime 10_000 y `:186` staleTime 30_000) y sólo la de la tabla paginada recibe `placeholderData`.
- **C5 (IMPORTANTE) — prefetch on-focus amplificado por el foco roving del 172.** `getPrefetchProps` esparce `onFocus`; con el j/k del plan 172 cada paso de foco dispararía un prefetch. **Fix:** R10 + nota en F3: el debounce ≥150 ms + dedup + cap 1 lo absorben; se documenta que la traversal pura NO debe emitir (el foco que "pasa de largo" cancela en `onBlur` antes del deadline) y que 172 comparte el MISMO scheduler (cap global de 1 en vuelo).
- **C6 (MENOR) — a11y del log virtualizado.** R11: `LogsPanel` virtualizado declara `role="log"` en el contenedor; se acepta como trade-off explícito que `aria-live` sólo anuncia la ventana montada (el texto completo vive en disco backend), mismo criterio que R1/R2.
- **C7 (MENOR) — request de flags duplicada.** `useUiPerfFlags` hacía `fetch("/api/diag/health")` propio, duplicando el health que `App.tsx` ya pide al montar. **Fix + [ADICIÓN ARQUITECTO]:** hook único `useHealthFlags` compartido (misma `queryKey ["ui-perf-flags"]`, `staleTime: Infinity`) reutilizado por App y por los consumidores; chequeo `r.ok` antes de `r.json()`; 0 requests extra sobre el presupuesto del plan 156.
- **v2 · coherencia de serie 2026-07-18 (C-3/C-1/C-2):** intérprete backend corregido al canónico `.venv\Scripts\python.exe` (py3.13.5) en KPI-4/KPI-7, §3.3 y todos los bloques de comando — `venv\Scripts\python.exe` (py3.11.9, WIP ajeno) queda marcado PROHIBIDO (197 §4.1); el preámbulo de dependencias ya no da a 165 por no-implementado (F1-F3 mergeadas); la flag se lee por `useHealthFlags`/`/api/diag/health`, no por `HarnessFlags.list` (197 §6.1 parte A).

**[ADICIÓN ARQUITECTO]:** (1) 3ra flag `STACKY_UI_INSTANT_NAV_ENABLED` que le da a "navegación instantánea" su propio kill-switch **en la UI de Settings** (no git-revert), cerrando C1 con la regla dura; (2) el `data-stale` respeta `prefers-reduced-motion` (sin transición si el SO lo pide) — cero trabajo del operador, default ON, accesible.

---

> **Estado histórico v1:** PROPUESTO v1 (2026-07-18) · **Autor:** StackyArchitectaUltraEficientCode (perfil normal)
> **Hermanos de serie:** 172 (teclado primero: atajos + foco roving), 173 (vistas guardadas: presets + preferencias de tabla), 175 (peek + acciones rápidas). Este plan NO define atajos (172), NO define presets ni columnas persistentes (173), NO define hover-cards ni menú contextual (175). Las dependencias con hermanos son **blandas**: si el hermano no está implementado, la feature degrada explícitamente (se detalla ítem por ítem), nunca rompe.
> **Dependencias blandas fuera de serie:** plan 156 (latido único — presupuesto de red KPI ≤2 requests/tick en idle: este plan lo RESPETA como techo duro aunque 156 no esté implementado aún), plan 164 (diálogo canónico — N/A acá: este plan no tiene ninguna acción con efecto), plan 165 (contrato de URL — **YA IMPLEMENTADO F1-F3**, commits f49588eb→8619acfd: `routes.ts` existe y la navegación instantánea consume sus deep-links canónicos; camino histórico degradado — si faltara, funcionaría igual sobre la history API actual).
> **Runtimes:** las features de este plan son 100% del dashboard (frontend React + 3 campos de lectura aditivos en un endpoint backend existente). Son **agnósticas del runtime de agentes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro): ninguna fase toca el camino de ejecución, publicación ni telemetría de agentes. La paridad de los 3 runtimes es automática por vacuidad — igual se declara fase por fase.
> **Flags nuevas (3, alta triple en F0):** `STACKY_UI_VIRTUALIZATION_ENABLED` (gatea F2), `STACKY_UI_PREFETCH_ENABLED` (gatea F3) y `STACKY_UI_INSTANT_NAV_ENABLED` (gatea F4 — agregada en v2 por C1), las tres **default ON**, editables desde la UI de Settings (FlagSpec `env_only=False`), con kill-switch instantáneo (OFF = comportamiento actual byte-idéntico). **Regla dura cumplida en las 3 fases con comportamiento nuevo:** cada fase que cambia comportamiento (F2, F3, F4) tiene su gate de flag configurable por UI; ninguna depende de "git revert".
> **Human-in-the-loop:** N/A por diseño — este plan solo hace GETs de lectura y cambia CÓMO se pinta lo que ya se pinta. Cero acciones destructivas, cero publicaciones, cero decisiones quitadas al operador. Ninguna de las 4 excepciones duras al "default ON" aplica (§3.2 lo argumenta textualmente).
> **Trabajo del operador: ninguno** (en todas las fases; se repite fase por fase porque es regla de la serie).

> Este documento está escrito para que un modelo menor (Haiku / Codex CLI / GitHub Copilot Pro) lo
> implemente **sin inferir nada**. Cada fase trae archivos exactos, símbolos exactos, pseudocódigo,
> tests primero con comando exacto y criterio de aceptación binario. Si algo no está escrito acá,
> **NO lo inventes**: parás y preguntás al operador.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** que la UI de Stacky se sienta instantánea sin pedir un byte de más: (a) las listas largas reales (stream de logs de ejecución y lista de diferencias del Comparador de BD) dejan de renderizar un nodo DOM por elemento y pasan a una **ventana virtualizada hand-rolled** (~≤60 nodos aunque haya 5.000 filas), extraída del precedente propio del repo (DiffList del plan 124) y sin agregar dependencias; (b) al **apuntar** con el mouse o el foco a una fila de ejecución, el detalle se **prefetchea** con react-query (debounce ≥150 ms, máximo 1 en vuelo, cancelación al salir), así el drawer abre ya pintado; (c) **paginar y filtrar deja de parpadear** (`placeholderData: keepPreviousData`) y **volver atrás pinta desde cache** y revalida en background (staleTime/gcTime afinados por tipo de query). Todo detrás de **3 flags default ON** (una por fase con comportamiento nuevo: F2/F3/F4 — la 3ra agregada en v2 por C1), editables por UI, con presupuesto de red y de DOM **binarios y testeados**, sin violar el techo del plan 156 (≤2 requests/tick en idle: el prefetch solo dispara con interacción humana; en idle suma exactamente 0; leer las flags reutiliza el health que App ya pide, 0 requests extra).

**KPIs binarios (comandos exactos; backend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` — intérprete backend CANÓNICO `.venv\Scripts\python.exe` (py3.13.5, verificado en disco 2026-07-18; ver 197 §4.1). **PROHIBIDO** `venv\Scripts\python.exe` (py3.11.9, WIP ajeno untracked de la sesión paralela: ni usarlo ni borrarlo ni recrearlo). Frontend desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`):**

- **KPI-1 — Presupuesto de DOM:** `npx vitest run src/utils/__tests__/virtualWindow.test.ts` → exit 0. Incluye el caso binario: lista de **5.000 filas** (rowHeight 22 px, viewport 600 px, overscan 10) → `rendered ≤ 60` nodos y la suma `padTopPx + rendered*rowHeightPx + padBottomPx === total*rowHeightPx`.
- **KPI-2 — Presupuesto de red del prefetch:** `npx vitest run src/services/__tests__/prefetchPolicy.test.ts` → exit 0. Incluye: **0** llamadas sin interacción; debounce **≥150 ms**; **≤1** prefetch en vuelo (el excedente se DESCARTA, no se encola); `leave()` antes del deadline ⇒ **0** llamadas.
- **KPI-3 — Adopción real (fs+regex, precedente plan 140):** `npx vitest run src/__tests__/plan174Adoption.test.ts` → exit 0 (LogsPanel y DiffList usan `useVirtualList`; ExecutionHistoryPage y SystemLogsPage usan `placeholderData: keepPreviousData`; ExecutionHistoryPage y ReviewInboxPage usan `getPrefetchProps`).
- **KPI-4 — Flags backend verdes:** `.venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q` → exit 0 (**las 3 flags** `STACKY_UI_VIRTUALIZATION_ENABLED` / `STACKY_UI_PREFETCH_ENABLED` / `STACKY_UI_INSTANT_NAV_ENABLED`: default ON, curadas, categorizadas, PLAIN_HELP, y sus 3 campos `ui_virtualization_enabled` / `ui_prefetch_enabled` / `ui_instant_nav_enabled` en `/api/diag/health`).
- **KPI-5 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-6 — Ratchets:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 (cero `style={{` nuevos) **y** `grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.sh` → `1` **y** `grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.ps1` → `1`.
- **KPI-7 — Sin regresión de flags:** `.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` y `.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q` → exit 0.

**KPIs de impacto (proyectados, verificables por smoke manual en §10 DoD):**

| Métrica | Hoy | Con el plan |
|---|---|---|
| Nodos DOM de una ejecución con 5.000 líneas de log (LogsPanel) | ≤2.000 hoy (`LogsPanel.tsx:34` `slice(-RENDER_CAP)`, cap 156 F3) — pero la cola descarta visualmente el resto | ≤ 60, con scroll a TODO el buffer retenido por 156 |
| Nodos DOM de un diff de BD con 3.000 objetos (DiffList) | crece de a 100 con clicks manuales "Mostrar 100 más" (`DiffList.tsx:36-38`) | ≤ 60, con scroll continuo y sin clicks |
| Apertura del drawer de detalle tras hover ≥150 ms sobre la fila | spinner siempre (2 queries en frío, `ExecutionDetailDrawer.tsx:36-46`) | pintado instantáneo desde cache (detalle prefetcheado) |
| Cambiar de página en Historial / System Logs | flash de skeleton/"Loading logs…" y tabla vacía | la tabla anterior queda visible atenuada hasta que llega la nueva |
| Requests extra en idle (sin mouse ni teclado) | 0 | **0** (techo duro; el prefetch es solo interacción humana) |

---

## 2. Por qué ahora / gap que cierra (evidencia leída 2026-07-18)

### 2.1 Listas largas sin ventana de render

- `frontend/src/components/LogsPanel.tsx` (evidencia REAL 2026-07-18, ~45 líneas) — **Plan 156 F3 YA está implementado acá** (corrección C2 sobre el v1, que lo daba por no implementado): `RENDER_CAP = 2000` (`:9`), render `stream.lines.slice(-RENDER_CAP).map((l, i) => ...)` (`:34`), banner `dropped` de líneas descartadas (`:31-33`) y autoscroll incondicional en `useEffect` sobre `stream.lines.length` (`:17-19`, `ref.current.scrollTop = ref.current.scrollHeight`). O sea: el DOM del log **ya está acotado a ≤2.000 nodos**, no 5.000. Aun así 2.000 nodos monoespaciados con re-render en cada línea nueva siguen degradando el frame-rate en ejecuciones largas; la virtualización baja ese piso a ~60 nodos **y** elimina el `slice(-RENDER_CAP)` que hoy **descarta visualmente** las primeras líneas (con virtualización el operador puede scrollear a TODO el buffer retenido por 156, no sólo la cola). La virtualización es el complemento de render que 156 declaró fuera de su alcance ("La cota se implementa sin libs nuevas", 156 §2.3; su F3 acota memoria y cola de render, no da ventana de scroll completo).
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

- Plan 156 §1 (tabla de impacto): KPI **≤2 requests por tick en idle** (1 por scope de summary). Plan 156 F3 ya está parcialmente aterrizado (ver §2.1: el `RENDER_CAP` de `LogsPanel` vive en el árbol). Este plan NO puede sumar requests periódicas: todo tráfico nuevo es (a) disparado por interacción humana explícita (hover/focus con debounce), o (b) **cero** requests nuevas para leer flags — reutiliza el `GET /api/diag/health` que `App.tsx` ya dispara al montar, vía el hook compartido `useHealthFlags` (`staleTime: Infinity`, §F1; [ADICIÓN ARQUITECTO] C7), sin duplicarlo.

---

## 3. Principios y guardarrailes

### 3.1 Los rieles duros de la serie

1. **3 runtimes con paridad.** Todo ítem es dashboard puro (frontend + 3 campos aditivos de lectura en `/api/diag/health`). Nada toca `agent_runner`, publicación, ni telemetría por runtime ⇒ paridad Codex CLI / Claude Code CLI / GitHub Copilot Pro por vacuidad. Se declara igual en cada fase.
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
- **Comando backend:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"` + `.venv\Scripts\python.exe -m pytest tests/test_X.py -q` — **por archivo, nunca la suite entera** (contaminación cross-file conocida).
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

### F0 — Flags backend: alta TRIPLE con default ON + campos en `/api/diag/health`

**Objetivo (1 frase):** dar de alta `STACKY_UI_VIRTUALIZATION_ENABLED` (F2), `STACKY_UI_PREFETCH_ENABLED` (F3) y `STACKY_UI_INSTANT_NAV_ENABLED` (F4 — agregada en v2 por C1) (bool, default ON, editables por UI de Settings) y exponerlas al frontend por el mecanismo canónico del plan 139, para que las 3 fases con comportamiento nuevo tengan kill-switch por UI desde el día cero.
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

- `test_virtualization_flag_default_on` — `monkeypatch.delenv("STACKY_UI_VIRTUALIZATION_ENABLED", raising=False)`; `importlib.reload(config)`; assert `config.config.STACKY_UI_VIRTUALIZATION_ENABLED is True`; reload final para restaurar. **Gotcha (memoria de la serie):** `importlib.reload(config)` en un test contamina los tests flag-off de la MISMA corrida ⇒ este archivo corre SIEMPRE por sí solo (`pytest tests/test_plan174_ui_perf_flags.py`), nunca dentro de la suite.
- `test_prefetch_flag_default_on` — ídem para `STACKY_UI_PREFETCH_ENABLED`.
- `test_instant_nav_flag_default_on` — ídem para `STACKY_UI_INSTANT_NAV_ENABLED` (agregada en v2, C1).
- `test_flagspecs_registered_and_categorized` — para cada una de las **3** keys: existe `FlagSpec` en `FLAG_REGISTRY` con `type == "bool"`, `default is True`, `env_only is False`, y la key está en `_CATEGORY_KEYS["interfaz_ui"]`.
- `test_plain_help_entries` — `PLAIN_HELP` tiene entrada para las 3 keys con `what/on_effect/off_effect/example` no vacíos (respetar denylist de jerga de `tests/test_harness_flags_help.py`).
- `test_health_exposes_ui_perf_fields` — con fixture `app` (patrón `app_flag_on` sin tocar flags), `client.get("/api/diag/health")` → 200 y el JSON contiene `"ui_virtualization_enabled"`, `"ui_prefetch_enabled"` y `"ui_instant_nav_enabled"` como bool.
- `test_health_fields_follow_config` — fixture que setea `cfg.config.STACKY_UI_INSTANT_NAV_ENABLED = False` (con restore) → el campo `ui_instant_nav_enabled` del health es `False`.

Correr y verlos FALLAR por la razón correcta (flags inexistentes):
```
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
.venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q
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

STACKY_UI_INSTANT_NAV_ENABLED: bool = os.getenv(  # Plan 174 v2 (C1) — gatea F4
    "STACKY_UI_INSTANT_NAV_ENABLED", "true"
).strip().lower() == "true"
```

(b) `harness_flags.py` — dos ediciones (citas de línea ORIENTATIVAS; anclar por TEXTO, la sesión paralela mueve los números — evidencia 2026-07-18: `_CATEGORY_KEYS["interfaz_ui"]` empieza en `:332` con la key `STACKY_UI_SHELL_V2_ENABLED` en `:333`; la `FlagSpec` de shell v2 está en `:3239`, no en `:3180-3192`): (b1) en la tupla `_CATEGORY_KEYS["interfaz_ui"]` (ancla de texto: la línea `"STACKY_UI_SHELL_V2_ENABLED",  # Plan 139`) agregar las **3** keys con comentario `# Plan 174 — ...`; (b2) en `FLAG_REGISTRY`, junto a la `FlagSpec` cuyo `key="STACKY_UI_SHELL_V2_ENABLED"`, agregar **3** `FlagSpec` con `default=True` (patrón `default=True` explícito, p.ej. `CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED`):
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
        "abra al instante. Con OFF, comportamiento actual."
    ),
    group="global",
),
FlagSpec(
    key="STACKY_UI_INSTANT_NAV_ENABLED",
    type="bool",
    default=True,
    label="Navegación instantánea sin parpadeo",
    description=(
        "Plan 174 — Paginar, filtrar y volver a una pantalla mantiene la "
        "información anterior visible (atenuada) hasta que llega la nueva, en "
        "vez de mostrar una pantalla vacía. Solo cambia el pintado; mismos "
        "datos y mismos pedidos. Con OFF, comportamiento actual."
    ),
    group="global",
),
```
- **Anti-gotcha (recurrido 6 veces en la serie):** la prosa de comentarios NO debe colisionar con greps-gate de otros planes; no escribir literales de diálogos nativos ni `style={{` en comentarios.

(c) `harness_flags_help.py` — **3** entradas `PlainHelp` en `PLAIN_HELP` (formato on/off del archivo, sin jerga de la denylist).

(d) `tests/test_harness_flags.py` — agregar las **3** keys al set `_CURATED_DEFAULTS_ON` (ancla de texto, no línea; evidencia v1 lo daba en `:467`). Es la vía canónica para default ON (si no: rompe `test_default_known_only_for_curated`).

(e) `api/diag.py` — en el dict de retorno de `health()`, inmediatamente después de la línea de `shell_v2_enabled` (ancla de texto `"shell_v2_enabled": ... # Plan 139`, hoy en `diag.py:415`), agregar:
```python
"ui_virtualization_enabled": bool(getattr(_config.config, "STACKY_UI_VIRTUALIZATION_ENABLED", True)),  # Plan 174
"ui_prefetch_enabled": bool(getattr(_config.config, "STACKY_UI_PREFETCH_ENABLED", True)),  # Plan 174
"ui_instant_nav_enabled": bool(getattr(_config.config, "STACKY_UI_INSTANT_NAV_ENABLED", True)),  # Plan 174 v2
```
(fallback `True` = coherente con default ON; aditivo puro, ningún consumidor existente se rompe).

(f) Registrar `tests/test_plan174_ui_perf_flags.py` en `HARNESS_TEST_FILES` de `scripts/run_harness_tests.sh` (lista `:20`, orden alfabético del bloque donde caiga) **y** en la lista homóloga de `scripts/run_harness_tests.ps1`.

**Criterio de aceptación (binario):**
```
.venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q   → exit 0
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q          → exit 0
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q     → exit 0
grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.sh      → 1
grep -c "test_plan174_ui_perf_flags.py" scripts/run_harness_tests.ps1     → 1
```
**Flag que protege la fase:** las 3 flags SON la fase; default ON.
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

// C3 — alias explícito que consume el hook: la decisión de virtualizar SIEMPRE
// pasa por el umbral. NO existe un modo "flag crudo sin umbral".
export function deriveIsVirtualized(total: number, flagEnabled: boolean): boolean {
  return shouldVirtualize(total, flagEnabled);
}
```

**Contrato de `enabled` (pinneado en v2, C3):** `enabled` es SIEMPRE el **flag crudo** (`flags.virtualization`), nunca `shouldVirtualize(...)` pre-computado. El hook aplica el umbral internamente vía `deriveIsVirtualized(total, enabled)`. Regla dura para el implementador: **ambos** call sites (LogsPanel y DiffList) pasan `enabled: flags.virtualization` — NO `shouldVirtualize(...)` — para que el umbral 200 se aplique en un solo lugar y no se duplique ni se saltee (evita virtualizar listas <200 y romper R1/Ctrl+F). El test 8 cubre `shouldVirtualize`/`deriveIsVirtualized` en puro; el hook queda como wiring fino sin lógica de umbral propia.

**`useVirtualList.ts` (hook fino; contrato exacto):**
```ts
import { useCallback, useRef, useState } from "react";
import { computeVirtualWindow, shouldVirtualize, type VirtualWindow } from "../utils/virtualWindow";

export interface UseVirtualListOptions {
  total: number;
  rowHeightPx: number;
  enabled: boolean;             // C3: SIEMPRE el flag CRUDO (flags.virtualization). El hook aplica el umbral 200 vía deriveIsVirtualized(total, enabled).
  overscan?: number;
  pinnedIndex?: number | null;  // plan 172 (blanda): sin 172 nadie lo pasa y no cambia nada
}
export interface UseVirtualListResult extends VirtualWindow {
  isVirtualized: boolean;                       // = deriveIsVirtualized(total, enabled). false ⇒ render directo, sin listeners
  containerRef: React.RefObject<HTMLDivElement>;// va al contenedor scrolleable
  onScroll: () => void;                         // va al onScroll del contenedor
  scrollToIndex: (i: number) => void;           // containerRef.scrollTop = i * rowHeightPx
}
```
Semántica: estado interno `scrollTopPx` actualizado en `onScroll` leyendo `containerRef.current.scrollTop` (throttle vía `requestAnimationFrame`: 1 recomputo por frame como máximo); `viewportHeightPx` leído de `containerRef.current.clientHeight` en el mismo callback (fallback 600 si el ref aún no montó). Con `isVirtualized === false` devuelve `{start:0, end:total, padTopPx:0, padBottomPx:0}` y `onScroll` es no-op. **Sin ResizeObserver ni efectos de layout** — mantenerlo mínimo; el recomputo en scroll cubre el caso real.

**`useUiPerfFlags.ts` (lectura de flags, CERO requests extra — reutiliza el health que App ya pide; C7 + [ADICIÓN ARQUITECTO]):**
```ts
import { useQuery } from "@tanstack/react-query";

export interface UiPerfFlags { virtualization: boolean; prefetch: boolean; instantNav: boolean; }
const DEFAULTS: UiPerfFlags = { virtualization: true, prefetch: true, instantNav: true }; // fail-open = default ON

// C7 — MISMA queryKey y config que el (único) fetch de health de App.tsx: react-query
// deduplica por key, así que este hook NO agrega una request; lee de la cache compartida.
// staleTime Infinity ⇒ 0 requests por tick: presupuesto del plan 156 intacto.
export function useUiPerfFlags(): UiPerfFlags {
  const q = useQuery({
    queryKey: ["ui-perf-flags"],
    queryFn: async (): Promise<UiPerfFlags> => {
      const r = await fetch("/api/diag/health");
      if (!r.ok) return DEFAULTS;            // C7: chequear r.ok antes de .json() (fail-open a ON)
      const d = await r.json();
      return {
        virtualization: d.ui_virtualization_enabled !== false,
        prefetch: d.ui_prefetch_enabled !== false,
        instantNav: d.ui_instant_nav_enabled !== false,
      };
    },
    staleTime: Infinity,
    gcTime: Infinity,
    refetchOnWindowFocus: false,
    retry: 0,
    placeholderData: DEFAULTS,
  });
  return q.data ?? DEFAULTS;
}
```
Mecanismo idéntico al del plan 139 (§3.3): campo aditivo de `/api/diag/health`; toggle desde Settings requiere recargar la página, igual que shell v2 (`App.tsx` ancla de texto "recargar la página para ver el efecto"). **Reuso (C7):** si `App.tsx` hoy pide health con OTRA `queryKey`, el implementador unifica ambas bajo `["ui-perf-flags"]` (o el hook llama a la key existente) para garantizar 1 sola request de health por sesión; se anota el desvío en el commit. Nunca 2 fetches de health.

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

**Implementación — LogsPanel (`LogsPanel.tsx`, hoy ~45 líneas; C2: escrito contra el código REAL que YA tiene Plan 156 F3).** Estado real de anclas (evidencia 2026-07-18, verificar por texto): `const RENDER_CAP = 2000;` (`:9`); `const ref = useRef<HTMLDivElement>(null);` (`:15`); autoscroll `useEffect(() => { if (ref.current) ref.current.scrollTop = ref.current.scrollHeight; }, [stream.lines.length]);` (`:17-19`); contenedor `<div className={styles.body} ref={ref}>` (`:27`); banner `dropped` (`:31-33`); render `stream.lines.slice(-RENDER_CAP).map((l, i) => ...)` con spans `styles.ts`/`styles.msg` (`:34-41`).

1. `const flags = useUiPerfFlags();` y `const virt = useVirtualList({ total: stream.lines.length, rowHeightPx: LOG_ROW_HEIGHT_PX, enabled: flags.virtualization });` con `const LOG_ROW_HEIGHT_PX = 20;` (constante del archivo). **`enabled` = flag CRUDO** (C3), no `shouldVirtualize(...)`.
2. **Reconciliar con `RENDER_CAP` (156):** hoy el render es `stream.lines.slice(-RENDER_CAP).map(...)` (cola de 2.000). Con `virt.isVirtualized === true`, la ventana YA acota el DOM a ~60 ⇒ **se virtualiza sobre `stream.lines` COMPLETO** (`stream.lines.slice(virt.start, virt.end)`), eliminando el `slice(-RENDER_CAP)` (el operador recupera el scroll a todo el buffer que 156 retiene). Con `virt.isVirtualized === false` (flag OFF o <200 líneas), el render queda **byte-idéntico al actual**, incluido el `slice(-RENDER_CAP)` y el banner `dropped`. El banner `dropped` (`:31-33`) se conserva en AMBOS caminos.
3. CSS: en `LogsPanel.module.css` agregar `.virtualLine { height: 20px; line-height: 20px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }`. Cuando `virt.isVirtualized`, cada fila lleva `className={`${styles.line} ${styles.virtualLine} ${styles[l.level]}`}` (altura fija = requisito del motor; se preserva la estructura de spans `styles.ts`/`styles.msg` del código real). Cuando NO, el render es EXACTAMENTE el actual, wrap incluido.
4. Render virtualizado: `stream.lines.slice(virt.start, virt.end).map((l, i) => ... key={virt.start + i} ...)` entre dos spacers `<div ref={padTopRef} />` / `<div ref={padBottomRef} />` cuyas alturas se setean por **ref + effect imperativo** (`padTopRef.current.style.height = `${virt.padTopPx}px``) — **prohibido `style={{}}`** (ratchet plan 138).
5. Contenedor: el `ref` actual `:27` (`ref`) pasa a ser `virt.containerRef` y se agrega `onScroll={virt.onScroll}` SOLO en el camino virtualizado (unificar; en camino no-virtualizado el `ref` sigue siendo el de autoscroll).
6. Autoscroll (reemplaza el `useEffect` de `:17-19`): en el mismo `useEffect` dependiente de `stream.lines.length`, si `isPinnedToBottom(el.scrollTop, el.clientHeight, el.scrollHeight)` era true ANTES de agregar líneas ⇒ `virt.scrollToIndex(stream.lines.length - 1)` (o, camino no-virtualizado, `el.scrollTop = el.scrollHeight` como hoy); si el operador scrolleó arriba, NO se lo arrastra al fondo (mejora deliberada; hoy `:17-19` arrastra SIEMPRE — R3 lo documenta). El `useEffect` actual arrastra incondicional: la nueva semántica es un cambio de comportamiento **sólo bajo flag ON**.
7. **a11y (C6/R11):** el contenedor scrolleable lleva `role="log"`; se acepta que con virtualización `aria-live` sólo cubre la ventana montada (trade-off explícito, mismo criterio que R1/R2; el texto completo vive en el archivo de log backend).

**Implementación — DiffList (`DiffList.tsx`, hoy 43 líneas):**
1. Mantener `PAGE_SIZE`/`visibleCount`/botón "Mostrar 100 más" SOLO para el camino flag OFF (byte-idéntico a hoy).
2. Camino virtualizado — decidido por `const virt = useVirtualList({ total: items.length, rowHeightPx: DIFF_ROW_HEIGHT_PX, enabled: flags.virtualization });` y ramificando por `virt.isVirtualized` (**C3: pasar el flag CRUDO `flags.virtualization`, NO `shouldVirtualize(...)`**; el umbral 200 lo aplica el hook). Cuando `virt.isVirtualized`: render de `items.slice(virt.start, virt.end)` con spacers imperativos (mismo patrón que LogsPanel), `DIFF_ROW_HEIGHT_PX = 32` + clase CSS `.diffRowVirtual { height: 32px; overflow: hidden; }` agregada a `dbcompare.module.css` y aplicada junto a `styles.diffRow`. El botón "Mostrar 100 más" NO se renderiza en este camino (la lista completa es scrolleable).
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

**Interacción con el foco roving del plan 172 (C5 / R10):** `getPrefetchProps` esparce `onFocus`/`onBlur`, así que cuando 172 aterrice, cada paso de foco por teclado (j/k) entra y sale de filas. Esto **NO** genera trabajo extra ni ráfaga de requests: (a) el `onBlur` de la fila que el foco abandona llama `leave(key)` y **cancela** el prefetch pendiente ANTES del deadline de 150 ms si el operador sigue moviéndose (traversal pura ⇒ 0 requests); (b) sólo si el foco se DETIENE ≥150 ms en una fila se dispara 1 prefetch; (c) el cap `PREFETCH_MAX_CONCURRENT = 1` + dedup por key en vuelo son globales, y **el plan 172 DEBE reusar este mismo `createPrefetchScheduler`** (no crear el suyo) para compartir el cap. Resultado: navegar 20 filas con j/k rápido = 0 requests; pararse en una = 1. El presupuesto del plan 156 (0 en idle) queda intacto porque el foco es interacción humana explícita, no un tick.

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

**Gate de flag (C1 — CORREGIDO en v2):** F4 CAMBIA comportamiento visible (placeholder atenuado en vez de tabla vacía) ⇒ DEBE tener gate de flag configurable por UI, NO "git revert". Se gatea con la flag nueva **`STACKY_UI_INSTANT_NAV_ENABLED`** (F0). El gate es un **ternario en la opción `placeholderData`** — NO duplica el `useQuery` (era la objeción falsa del v1): con la flag OFF, `placeholderData` queda `undefined` ⇒ comportamiento **byte-idéntico** a hoy (flash de vacío incluido). Patrón exacto:
```ts
import { keepPreviousData } from "@tanstack/react-query";
import { tuningFor } from "../services/queryTuning";
import { useUiPerfFlags } from "../hooks/useUiPerfFlags";
// en el cuerpo del componente:
const { instantNav } = useUiPerfFlags();
// en historyQ (ancla de texto: la queryFn de historyQ; hoy en :115, staleTime literal 30_000 en :127):
placeholderData: instantNav ? keepPreviousData : undefined,   // C1: gate de flag
...tuningFor("history"),        // reemplaza el staleTime: 30_000 literal
```
Feedback visual del dato provisorio SIN inline style: el contenedor de la tabla lleva `data-stale={(instantNav && historyQ.isPlaceholderData) || undefined}` y en `ExecutionHistoryPage.module.css` se agrega:
```css
[data-stale] { opacity: 0.6; }
@media (prefers-reduced-motion: no-preference) { [data-stale] { transition: opacity 120ms ease; } }
```
([ADICIÓN ARQUITECTO]: la transición respeta `prefers-reduced-motion`; patrón de microinteracción, plan 143). El contador de resultados (ancla de texto `${items.length} resultado…`, hoy en `:152`) durante placeholder muestra los datos previos — correcto, son los que se ven.

**Edición — `SystemLogsPage.tsx`:** ídem con el MISMO gate `instantNav ? keepPreviousData : undefined`. **OJO (C4): SystemLogsPage tiene DOS `useQuery`** (evidencia 2026-07-18: `staleTime: 10_000` en `:181` = la query de LOGS paginada; `staleTime: 30_000` en `:188` = query secundaria/summary). El `placeholderData` + `...tuningFor("systemLogs")` van SOLO en la query de logs paginada (la de `staleTime: 10_000`, `:181`); la secundaria NO se toca. El `refetchInterval` existente NO se toca. `data-stale` en el contenedor de la tabla + misma regla CSS. Con esto, "Loading logs…" (ancla de texto, hoy `:322`) queda SOLO para la primera carga (`isLoading` es false con placeholder presente — semántica react-query v5).

**Edición — `ExecutionDetailDrawer.tsx` (opcional-recomendada, 1 línea, bajo el mismo gate):** agregar `...tuningFor("executionDetail")` a `execQ` (ancla de texto la query `["execution-detail", ...]`) para que reabrir el mismo detalle dentro de los 30 s pinte desde cache (coherente con F3). Si el archivo tiene WIP ajeno ⇒ se omite y se anota.

**Sobre `gcTime`/`tuningFor` sin gate:** `gcTime` (retención en cache) NO cambia comportamiento observable con flag OFF (sólo retiene datos más tiempo; sin `placeholderData` no se pintan) y NO gasta red ⇒ puede quedar sin branch. Lo que SÍ cambia lo visible (`placeholderData` + `data-stale`) está gateado. Así, con `STACKY_UI_INSTANT_NAV_ENABLED=OFF` + recarga, las 2 páginas se comportan **como HOY** (cumple la DoD §9, que el v1 contradecía).

**Criterio de aceptación (binario):**
```
npx vitest run src/services/__tests__/queryTuning.test.ts → exit 0
npx tsc --noEmit                                          → exit 0
```
**Flag:** `STACKY_UI_INSTANT_NAV_ENABLED` default ON (C1); OFF ⇒ `placeholderData` queda `undefined` y `data-stale` nunca se activa ⇒ Historial y System Logs byte-idénticos a hoy.
**Runtimes / fallback:** cache local del dashboard; paridad por vacuidad. Fallback: sin cache retenida (primera visita) el comportamiento es el actual; health caído ⇒ `instantNav` fail-open a ON.
**Trabajo del operador: ninguno.**

---

### F5 — Adopción verificada + cierre integral

**Objetivo (1 frase):** fijar con un test fs+regex (precedente plan 140) que la adopción de F2/F3/F4 está realmente cableada, y correr la batería integral de cierre.
**Valor:** el plan no se puede "implementar a medias" sin que un test lo delate; la adopción queda ratcheteada.

**Archivo a crear:** `Stacky Agents/frontend/src/__tests__/plan174Adoption.test.ts`

**Test (es la fase):** lee los archivos fuente con `fs.readFileSync` (patrón exacto de los tests de adopción del plan 140 y del `uiDebtRatchet`) y asserta:
1. `src/components/LogsPanel.tsx` contiene `useVirtualList(` y NO contiene `stream.lines.map(` **fuera** del camino no-virtualizado (assert simple: contiene `virt.start` y `virt.end`).
2. `src/components/dbcompare/DiffList.tsx` contiene `useVirtualList(` y conserva `PAGE_SIZE` (camino flag OFF intacto).
3. `src/pages/ExecutionHistoryPage.tsx` contiene `keepPreviousData` **y** `instantNav` (C1: gate presente) **y** `getPrefetchProps(`.
4. `src/pages/SystemLogsPage.tsx` contiene `keepPreviousData` **y** `instantNav`.
5. `src/pages/ReviewInboxPage.tsx` contiene `getPrefetchProps(`.
6. `src/hooks/useVirtualList.ts` contiene `requestAnimationFrame` (throttle presente) **y** `deriveIsVirtualized` (C3: el umbral se aplica en el hook, no en los call sites).
7. Anti-regresión de presupuesto: `src/services/prefetchPolicy.ts` contiene `PREFETCH_MAX_CONCURRENT = 1` y `PREFETCH_HOVER_DELAY_MS = 150` (los valores son parte del contrato con 156 y 175; cambiarlos exige tocar este test a conciencia).
8. Gate de C1 verificado en backend: el test de adopción NO cubre backend; el gate de las 3 flags lo cubre `test_plan174_ui_perf_flags.py` (KPI-4).

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
.venv\Scripts\python.exe -m pytest tests/test_plan174_ui_perf_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q
.venv\Scripts\python.exe -m pytest tests/test_harness_flags_help.py -q
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
| R10 | **Foco roving del 172 dispara ráfaga de prefetch** (cada j/k entra/sale de filas). | `onBlur` ⇒ `leave()` cancela antes del deadline 150 ms ⇒ traversal pura = 0 requests; sólo detenerse ≥150 ms dispara 1; cap global `PREFETCH_MAX_CONCURRENT=1` compartido (172 reusa `createPrefetchScheduler`, no crea el suyo). Test KPI-2 caso 3 (leave antes del deadline ⇒ 0). C5. |
| R11 | **Log virtualizado rompe lectores de pantalla / `aria-live`** (sólo ~60 nodos montados). | Contenedor `role="log"`; se acepta como trade-off explícito (mismo criterio que R1/R2) que `aria-live` anuncia sólo la ventana montada; el texto completo vive en el archivo de log backend. Bajo el umbral 200 o flag OFF, DOM completo y a11y intacta. C6. |
| R12 | **F4 sin gate dejaba comportamiento nuevo activo con "todas las flags OFF"** (contradecía la DoD). | RESUELTO en v2 (C1): `STACKY_UI_INSTANT_NAV_ENABLED` gatea `placeholderData`+`data-stale` por ternario; OFF ⇒ byte-idéntico a hoy. Kill-switch en Settings, no git-revert. |

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

1. **F0** — **3 flags** backend + 3 campos en health + registro en `HARNESS_TEST_FILES` (sh y ps1).
2. **F1** — `virtualWindow.ts` (test primero) + `useVirtualList` + `useUiPerfFlags`.
3. **F2** — LogsPanel + DiffList virtualizados (test `stickToBottom` primero; pre-flight git por archivo).
4. **F3** — `prefetchPolicy.ts` (test primero) + hook + wiring en Historial y Review Inbox.
5. **F4** — `queryTuning.ts` (test primero) + `placeholderData` en Historial y System Logs.
6. **F5** — test de adopción + batería integral de cierre.

## 9. Definición de Hecho (DoD) global

- [ ] KPI-1..KPI-7 de §1: todos exit 0, con output real pegado (cero falsos verdes; la verificación final la corre y la LEE el agente principal).
- [ ] **Las 3 flags** (`STACKY_UI_VIRTUALIZATION_ENABLED`, `STACKY_UI_PREFETCH_ENABLED`, `STACKY_UI_INSTANT_NAV_ENABLED`) visibles y toggleables en la UI de Settings (panel de flags), con ayuda en lenguaje llano.
- [ ] Con **las 3 flags OFF** (toggle + recarga): LogsPanel, DiffList, Historial, System Logs y Review Inbox se comportan como HOY, byte-idéntico (smoke visual) — incluye que Historial/System Logs vuelven a mostrar el flash de vacío al paginar (prueba de que F4 quedó realmente gateada, C1).
- [ ] Smoke manual (deploy o dev): (1) ejecución con >1.000 líneas de log → scroll fluido y ≤~60 filas en el inspector DOM; (2) diff de BD con >200 objetos → scroll continuo sin botón "Mostrar 100 más"; (3) hover 1 s sobre una fila del historial → abrir → drawer pintado sin spinner; (4) paginar historial y logs → la tabla no desaparece, se atenúa; (5) ir a otra pantalla y volver → pinta al instante y revalida en background (ver request en Network, no spinner).
- [ ] En idle absoluto (sin mouse/teclado, pestaña visible) el panel Network no muestra NINGUNA request nueva atribuible a este plan.
- [ ] `git status` final sin archivos ajenos tocados; commits con pathspec explícito.
- [ ] Doc del plan actualizado a IMPLEMENTADO con desvíos anotados (regla del pipeline).
