# Plan 165 — El contrato de URL: la columna vertebral de la navegación (deep-links y estado persistente)

## Versión: v1 -> v2 (crítica adversarial aplicada)

**CHANGELOG v1 -> v2 (2026-07-18):**
- **C1 (BLOQUEANTE, deep-link solo-al-montar):** el diseño v1 de F3 (`initialRoute` en `useRef` congelado + props `initial*` alimentando `useState`) solo funcionaba con carga completa de página (pegar URL / F5). Navegación in-app a `/history?exec=N` (el caso EXACTO del gate del plan 152), Atrás/Adelante con otro exec/subtab, y el propio comentario del plan ("si la página ya está montada, el receptor de prop la actualiza" — FALSO: `useState(initial)` ignora cambios de prop) estaban rotos. v2: la ruta es **ESTADO** de App (`useState<RouteState>`), `popstate` hace `setRoute(parseRoute(...))`, las páginas reciben props VIVAS (`exec`/`subTab`) y se sincronizan con el patrón `lastApplied` (F3 Pasos 1-3).
- **C2 (BLOQUEANTE, promesa sin implementación):** la tabla de KPIs y el DoD prometían "una URL filtrada reproduce la vista", pero NINGÚN paso conectaba `historyFiltersFromQuery`/`sysLogFiltersFromQuery` a las páginas (helpers exportados con 0 callers) ni definía la precedencia URL vs `localStorage`. v2: F2 agrega `resolveMountFilters` (puro, testeado) + efecto de montaje OBLIGATORIO en ambas páginas: si la URL trae ≥1 clave de filtro, la URL manda COMPLETA (DEFAULT+URL, reproducción exacta); si no, DEFAULT+persistido.
- **C3 (IMPORTANTE, contrato 152↔165 ya divergente):** el plan 152 CRITICADO v2 define HOY `nav {tab:"team", executionId}` ejecutado vía `selectTab` (su §"Pseudocódigo useRunActivityCapture" y su tabla de intents) — exactamente el formato ad-hoc que R7 temía: apunta a "team" (no a "history") y `selectTab` no propaga exec. v2: se agrega **`navigateToRoute(state)`** como EL punto de entrada de navegación tipada ([ADICIÓN ARQUITECTO A1]) y la nota de reconciliación en §3.12/R7: al implementar 152, su `onActivityNavigate` debe llamar `navigateToRoute({tab:"history", exec:executionId})`.
- **C4 (IMPORTANTE, parser sub-especificado):** `Number("")===0` → `?exec=` (valor vacío) abría el drawer de la ejecución 0; `Number("0x10")===16`; decimales aceptados; ambas claves a la vez (`?exec=1&execution=2`) sin comportamiento definido; y con tab DESCONOCIDO el subtab se conservaba → `/nonexistent/foo` serializaba a `/foo` y el re-parse perdía el subtab, violando la idempotencia que el propio §4 define. v2: `exec` solo acepta `/^\d+$/` (parseInt), subtab SOLO con tab conocido, "team" jamás lleva subtab, y 4 tests nuevos lo fijan (F1).
- **C5 (IMPORTANTE, shape-drift + decisiones abiertas):** `useLocalStorageState` hace `JSON.parse(raw) as T` SIN merge con el default (verificado en `hooks/useLocalStorageState.ts`, cuerpo del `useState` inicial) → un objeto `Filters` persistido con shape viejo filtra `undefined` a la API cuando se agregue un campo. Además v1 dejaba TRES decisiones "a criterio del implementador" (offset aparte vs reset, `omitFilterKeys` inlineable, `replaceState` canónico "si querés") — prohibido en un plan para modelos menores. v2: merge `{...DEFAULT_FILTERS, ...persistido}` SIEMPRE al montar (dentro de `resolveMountFilters`), constantes exportadas `HISTORY_FILTER_QUERY_KEYS`/`SYSLOG_FILTER_QUERY_KEYS`, reset de `offset` OBLIGATORIO, `replaceState` canónico al montar OBLIGATORIO.
- **C6 (MENOR, residuos de renumeración y cwd):** header de tabla §2.2 decía "Rol en 158" (el plan nació como 158-variante y fue renumerado a 165); KPI-5 usa el path `backend/...` pero el preámbulo manda correr todo desde `frontend/` → KPI-5 ahora declara cwd raíz del repo.
- **C7 (MENOR, casos sin test):** trailing slash, hash (`#`), `?exec=` vacío y ambas claves no estaban testeados; el hash se declara fuera de scope explícito (parseRoute recibe `pathname+search`, nunca el hash). Tests agregados en F1.
- **[ADICIÓN ARQUITECTO A1]:** `navigateToRoute(state: RouteState)` en `App.tsx` — API única de navegación tipada del router casero; `selectTab`/`navigateTo` la reusan por dentro; es el punto de consumo del plan 152 (F3 Paso 1).
- **[ADICIÓN ARQUITECTO A2]:** write-back de subestado → URL vía `replaceState` con guard: abrir/cerrar el drawer por CLICK refleja `?exec=` en la URL, y cambiar de sub-tab en Settings refleja `/settings/<sub>`. En v1 la URL solo se LEÍA; ahora copiar la URL de la barra comparte SIEMPRE la vista exacta — "URL fuente de verdad" completa (F3 Pasos 2-3).
- **RE-VERIFICACIÓN 2026-07-18 (checkout real, no el worktree):** todos los anclajes de §2 confirmados POR TEXTO; los números de línea driftearon levemente (p.ej. filtros de Historial hoy en `:54`, receptor `?execution=` en `:59-65`, filtros de SystemLogs en `:124-133`, offset en `:134`, `setFilter` de SystemLogs SÍ resetea offset — confirmado). La regla "anclar por texto, no por línea" sigue vigente y cubrió el drift. `frontend/package.json`: sin `router`, sin `@testing-library/react`, sin `jsdom` (confirmado). `slash_commands.py:116,138` emiten `/?exec=` (confirmado, KPI-5=2).

> **Estado:** CRITICADO v2 (2026-07-18) — **v1 RECHAZADO** (C1+C2 BLOQUEANTES); v2 aplica C1..C7 + A1/A2 · **Autor:** StackyArchitectaUltraEficientCode · **Juez:** StackyArchitectaUltraEficientCode (adversarial)
> **Origen:** debate adversarial 2026-07-16 sobre la navegación del panel. El gap viene verificado del debate; **toda** la evidencia archivo:línea de este doc fue **re-verificada contra el worktree `C:/wt/uxlog`** y se corrigió el drift encontrado (ver §2 y los bloques "DRIFT CORREGIDO"). Los números de línea son referencia de ese día — **toda edición se ancla por TEXTO/símbolo citado, no por número de línea**.
> **Orden en el roadmap:** va en el **bloque de UX**, junto a los planes de densidad, onboarding y notificaciones. Esfuerzo **S/M**: el sustrato ya existe (el `pushState`/`popstate` casero de `App.tsx`, el hook `useLocalStorageState`, el helper `readQueryParam`). **HECHO NO OBVIO clave (§2.1):** el contrato de deep-links de ejecución **hoy está ROTO** — el backend emite `/?exec=<id>` pero el único receptor del frontend lee `/history?execution=<id>` (ni el path ni la clave coinciden). Este plan **no formaliza un contrato que ya funciona: RECONCILIA dos mitades divergentes** y hace que el deep-link funcione de punta a punta por primera vez. Sus **F1+F3 son GATE RECOMENDADO** antes de implementar el plan del centro de notificaciones (ese plan necesita deep-link notificación→run; su v2 YA trae un intent ad-hoc `{tab:"team", executionId}` vía `selectTab` que no puede abrir el drawer — ver C3/§3.12: debe consumir `navigateToRoute`).
> **Runtimes:** este plan es **navegación de la UI del panel Stacky**, 100% **agnóstica del runtime de agentes** (Codex CLI, Claude Code CLI, GitHub Copilot Pro). Ninguna fase toca el camino de ejecución de agentes, ni el de publicación, ni ningún endpoint del backend (salvo LEER que `slash_commands.py` ya emite `?exec=`). Solo cambia **cómo la UI mapea su estado de navegación a la URL**. La paridad de runtimes es automática por vacuidad. Se declara igual por fase.
> **Flags nuevas:** **NINGUNA.** Es mejora de navegación pura, backward-compatible y aditiva: las URLs viejas de primer nivel siguen funcionando idénticas; el contrato solo AGREGA capacidad (sub-tabs y drawer direccionables, filtros que sobreviven). NO se toca `FLAG_REGISTRY`, NO se toca `_CURATED_DEFAULTS_ON`, NO hay panel nuevo, NO hay config nueva del operador. Precedente directo: los planes de estados universales, tema claro/oscuro, sistema de movimiento y diálogo canónico se implementaron sin flag.
> **Human-in-the-loop:** **N/A** — es navegación. No hay ninguna acción automática hacia afuera; las URLs solo empiezan a funcionar y a persistir. Ninguna decisión se le quita al operador; al contrario, gana la capacidad de compartir/recargar una vista exacta.

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** en Stacky la URL es una etiqueta decorativa, no la columna vertebral de la navegación. El estado de navegación vive en RAM de React y **muere con F5**: la URL solo conoce el primer nivel (los ~16 tabs de `App.tsx`), mientras que los **9 sub-tabs de Settings** (`flow`/`sections`/`client-profile`/`transfer`/`webhooks`/`notifications`/`harness`/`playground`/`appearance`) y el **drawer de detalle de ejecución** son invisibles a la URL, y los **filtros de Historial (4) y de Logs del Sistema (8)** se evaporan al cambiar de tab (la página se desmonta por completo) o al recargar. Peor: el **único deep-link "en la calle" está roto** — `slash_commands.py` emite links de Slack `http://localhost:5173/?exec=<id>`, pero el único receptor del frontend (`ExecutionHistoryPage`) lee la clave `?execution=` sobre el path `/history`, así que un link de Slack aterriza en la pantalla de equipo y **no hace nada**. Este plan instala la **columna vertebral**: un **contrato de rutas tipado** (`frontend/src/services/routes.ts`) que parsea y serializa el esquema `/{tab}/{subtab?}?exec=&...` con `parse`/`serialize` inversos y testeados, **reconcilia** el deep-link de ejecución (clave canónica `exec`, alias legacy `execution`, normalización del `/?exec=` de raíz hacia `/history?exec=`), hace que los filtros de Historial y Logs **sobrevivan** F5 y el cambio de tab (vía `useLocalStorageState`, el hook que ya existe y que el Tablero de Tickets ya usa), y vuelve **direccionables por URL** los sub-tabs de Settings y el drawer de ejecución. Todo extendiendo el **router casero** de `App.tsx` — **jamás** metiendo `react-router` (el debate lo evaluó y lo rechazó: recableado invasivo de todas las páginas, la paleta y la nav, más su suite de tests). Resultado: la URL vuelve a ser la fuente de verdad compartible/recargable de dónde estás parado.

**KPIs binarios (comandos exactos; TODO frontend). Correr desde el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (el `node_modules` del worktree `C:/wt/uxlog` puede estar roto — junction conocida). Equivalente POSIX: `cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/frontend"`. vitest SIEMPRE por archivo (cross-file pollution conocida en este repo):**

- **KPI-1 — Parser/serializer del contrato verde (F1):** `npx vitest run src/services/__tests__/routes.test.ts` → exit 0 (round-trip `parseRoute∘serializeRoute` idempotente para CADA patrón del contrato; `serializeRoute(parseRoute(url)) === url` para URLs canónicas; query desconocida preservada).
- **KPI-2 — Filtros↔querystring reversibles (F2):** `npx vitest run src/services/__tests__/routeFilters.test.ts` → exit 0 (round-trip de los filtros de Historial y de Logs a/desde querystring; `offset` NUNCA se serializa).
- **KPI-3 — Deep-links de subestado parsean al estado correcto (F3):** `npx vitest run src/services/__tests__/routesDeepLink.test.ts` → exit 0 (`/settings/appearance` → `{tab:"settings", subtab:"appearance"}`; `/history?exec=123` → `{tab:"history", exec:123}`; `/?exec=123` → normaliza a `{tab:"history", exec:123}`; alias `?execution=123` → `exec:123`).
- **KPI-4 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-5 — El backend sigue emitiendo `?exec=` (contrato de facto anclado, no roto por este plan):** correr desde la **RAÍZ del repo** `N:\GIT\RS\STACKY\Stacky\Stacky Agents` (NO desde `frontend/` — el path `backend/...` no existe ahí): `grep -c "?exec=" backend/services/slash_commands.py` → `2` (los dos emisores siguen ahí; F1/F3 los reconcilian, no los borran).

**KPIs de impacto (proyectados, verificables por observación manual):**

| Métrica | Hoy (recuento en frío) | Con el plan |
|---|---|---|
| Subestados direccionables por URL (más allá del tab) | **0** formalizados (los receptores `?execution=`/`?flag=` son ad-hoc, parciales y el de ejecución está roto vs. el backend) | **10** (9 sub-tabs de Settings + drawer de ejecución), vía `routes.ts` |
| Deep-link de Slack `/?exec=<id>` → abre la ejecución | **NO** (aterriza en equipo, no hace nada) | **SÍ** (normaliza a `/history?exec=` y abre el drawer) — funciona de punta a punta por primera vez |
| Filtros de Historial (4) que sobreviven F5 y cambio de tab | **0** (se resetean al default) | **4** (persisten vía `useLocalStorageState`) |
| Filtros de Logs del Sistema (8) que sobreviven F5 y cambio de tab | **0** (se resetean al default) | **8** (persisten vía `useLocalStorageState`) |
| Vista filtrada compartible por URL (Historial / Logs) | **no** | **sí** (filtros reflejados en el querystring, sin `offset`) |
| Deep-link notificación→run para el plan del centro de notificaciones | inexistente (nacería ad-hoc) | **habilitado** por el contrato de F1 (GATE recomendado) |

**Impacto esperado:** pegar `/settings/appearance` abre Settings en Apariencia; pegar `/history?exec=123` abre el Historial con el drawer de la ejecución 123 desplegado; un link de Slack finalmente abre la ejecución; recargar el Historial o los Logs conserva los filtros; cambiar de tab y volver conserva los filtros; y el plan del centro de notificaciones tiene un contrato tipado que consumir en vez de inventar un deep-link ad-hoc. La URL deja de ser decorativa y vuelve a ser la columna vertebral de la navegación.

---

## 2. Por qué ahora / gap que cierra (evidencia re-verificada 2026-07-16)

### 2.1 U-clave — El deep-link de ejecución está ROTO (no solo informal)

Este es el hallazgo más importante del debate, y **no es lo que el debate creía**. El debate partió de "el backend YA emite deep-links `?exec={id}` → el contrato de facto ya circula sin formalizar". La re-verificación en el worktree muestra que **el contrato de facto está inconsistente y no funciona de punta a punta**:

- **Emisor (backend):** `backend/services/slash_commands.py` emite el link en DOS lugares:
  - `:116` — `f"Mirá el progreso en: http://localhost:5173/?exec={eid}"` (respuesta de `/stacky run`)
  - `:138` — `f"Link: http://localhost:5173/?exec={ex.id}"` (respuesta de `/stacky status`)
  - Es decir: **path raíz `/`** (tab "team") con la clave **`exec`**.
- **Único receptor (frontend):** `frontend/src/pages/ExecutionHistoryPage.tsx:76-83` — el receptor del plan de la paleta global lee `readQueryParam("execution")` (clave **`execution`**) y abre el drawer, **pero solo cuando `ExecutionHistoryPage` está montada** (es decir, cuando el tab activo es `/history`).
- **Consecuencia:** un link `http://localhost:5173/?exec=123` de Slack aterriza en `/` → `tabFromPath("/")` devuelve `"team"` (`App.tsx:64-68`) → `ExecutionHistoryPage` **no se monta** → el receptor **nunca corre** → **y aunque corriera, buscaría `execution`, no `exec`**. El deep-link "en la calle" **no hace nada hoy**.

> **DRIFT CORREGIDO (crítico) respecto del debate:** el debate afirmó que "el backend YA emite `?exec` → F1 lo FORMALIZA, no lo inventa". La realidad es que **F1/F3 RECONCILIAN** un contrato roto: canonizan la clave (`exec`, alias `execution`), y normalizan `/?exec=<id>` (raíz) hacia `/history?exec=<id>` para que el drawer se abra. La tesis "la URL es la columna vertebral" se sostiene **con más fuerza**: no es que la URL esté sub-especificada, es que su único deep-link real está partido en dos mitades que no se hablan.

### 2.2 El sustrato ya existe (≈70% del trabajo hecho — verificado)

| Símbolo | Archivo:línea (2026-07-16; drift menor re-verificado 2026-07-18 — anclar por TEXTO) | Rol en este plan (165) |
|---|---|---|
| `pushState` casero + guard de `pathname` | `frontend/src/App.tsx:109-115` (`selectTab`), `:117-123` (`navigateTo`) | F3 extiende este router casero; NO se agrega `react-router`. |
| `popstate` listener | `frontend/src/App.tsx:167-171` | F3 lo amplía para re-derivar subtab/exec, no solo el tab. |
| Comentario StrictMode double-push | `frontend/src/App.tsx:191-196` (dentro del handler `isToggleNav`) | Regla de oro heredada: `pushState` JAMÁS dentro de un updater de `setState`. |
| `<React.StrictMode>` | `frontend/src/main.tsx:18-22` | La causa del double-invoke en dev (por qué la regla anterior existe). |
| `TAB_PATHS` + `tabFromPath` (prefix match) | `frontend/src/App.tsx:45-62,64-68` | F1 los MUEVE a `routes.ts` (fuente única); F3 hace que App los importe. |
| `useLocalStorageState<T>(key, default)` | `frontend/src/hooks/useLocalStorageState.ts:14-41` | F2 lo usa para que los filtros sobrevivan (tolerante a fallos; ya probado en producción). |
| Uso real del hook | `frontend/src/pages/TicketBoard.tsx:704,705,706,724` (`ticketBoard.search`, etc.) | Precedente EXACTO del patrón que F2 replica (keys `stacky.ui.*`). |
| `parseQueryParam(search,name)` (puro) + `readQueryParam(name)` | `frontend/src/utils/queryParams.ts:6-8,10-12` | F1 reusa/generaliza para el parser; `parseQueryParam` ya es testeable sin jsdom. |
| Receptor `?execution=` (drawer) | `frontend/src/pages/ExecutionHistoryPage.tsx:76-83` | F3 lo REEMPLAZA por el `exec` parseado por `routes.ts` y pasado como prop. |
| Receptor `?flag=` (fuerza sub-tab harness) | `frontend/src/pages/SettingsPage.tsx:114-119` | F3 lo hace coexistir con el sub-tab direccionable por path (composición). |
| `slash_commands.py` (emisor `?exec=`) | `backend/services/slash_commands.py:116,138` | Fuente del contrato; F1 canoniza la clave `exec`. Se LEE, no se toca (salvo backlog opcional §8). |

### 2.3 U4 — Los filtros se evaporan al cambiar de tab o recargar (evidencia anclada)

- **Montaje condicional total:** `App.tsx:235-254` monta cada página con un condicional (`{tab === "history" && <ExecutionHistoryPage/>}`, `:247`; `{tab === "logs" && sections.logs && <SystemLogsPage/>}`, `:242`). Cambiar de tab **desmonta la página entera** → todo `useState` local vuelve a su default al re-montar.
- **Historial:** `ExecutionHistoryPage.tsx:72` — `const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)` (interface `Filters` en `:45-52`: `agent_type`, `runtime`, `status`, `days`, `limit`, `offset`; defaults en `:54-61`). `useState` puro → se resetea.
- **Logs del Sistema:** `SystemLogsPage.tsx:133-142` — `const [filters, setFilters] = useState({...})` con **8 campos** (`level`, `source`, `action`, `q`, `execution_id`, `ticket_id`, `from`, `to`) + `const [offset, setOffset] = useState(0)` en `:143` (aparte). `useState` puro → se resetea. `setFilter` (`:173-176`) ya resetea `offset` a 0 en cada cambio de filtro.

> **DRIFT CORREGIDO:** el debate citó `ExecutionHistoryPage:71` (filtros) y `:72` (drawer) — en el worktree es `:72` (filtros) y `:73` (`detailId`), con el receptor `?execution=` en `:76-83`. `SystemLogsPage:133-144` (8 filtros + offset) **confirmado**. `TicketBoard:703` → en el worktree el primer `useLocalStorageState` está en `:704`.

### 2.4 U5 — Los sub-tabs de Settings y el drawer son invisibles a la URL

- **Settings:** `SettingsPage.tsx:29` define `type SubTab = "flow" | "sections" | "client-profile" | "transfer" | "webhooks" | "notifications" | "harness" | "playground" | "appearance"` (**9 sub-tabs**, verificado uno por uno en los `setSub(...)` de `:126-174`). El estado es `const [sub, setSub] = useState<SubTab>("flow")` (`:110`), invisible a la URL: recargar siempre cae en `flow`, y no se puede compartir un link a un sub-tab.
  - **Excepción parcial preexistente:** `:114-119` ya hay un receptor `?flag=<key>` que fuerza `sub="harness"` y resalta una fila. F3 debe hacerlo **coexistir** con el sub-tab por path (ver F3).
- **Drawer de ejecución:** `detailId` en `useState` (`ExecutionHistoryPage.tsx:73`), invisible salvo por el receptor roto de §2.1.
- **`tabFromPath` ya tolera sub-paths:** `App.tsx:66` usa `pathname.startsWith(path)`, así que `/settings/appearance` **ya** matchea el tab `settings` hoy. Esto hace que agregar el parseo de subtab sea **aditivo y de bajo riesgo**: el primer nivel sigue funcionando idéntico; F1/F3 solo extraen el 2do segmento por encima.

> **DRIFT CORREGIDO:** el debate dijo `SettingsPage:109` para `sub` → en el worktree es `:110`; el debate no mencionó el receptor `?flag=` preexistente (`:114-119`) — F3 lo contempla explícitamente. El debate dijo "TAB_PATHS mapea ~15 rutas" → son **16** (`:45-62`). `popstate` "aprox :155-159" → **:167-171**. StrictMode double-push "aprox :179-183" → el comentario vive en **:191-196** (dentro de `isToggleNav`), y `<React.StrictMode>` en `main.tsx:18` (no `:13`). `navigateTo` "aprox :111-117" → `selectTab` `:109-115`, `navigateTo` `:117-123`.

### 2.5 Ausencia total de `react-router` (confirmado — y así se queda)

- `grep -i "router" frontend/package.json` → **0 coincidencias**. No hay `react-router` ni `@tanstack/router`. La navegación es 100% casera (`pushState`/`popstate` en `App.tsx`).
- `frontend/package.json` tiene `vitest ^4.1.9`, **NO** `@testing-library/react`, **NO** `jsdom` → todo test de este plan es de **lógica pura** (`.ts`, sin `render()`).
- **Decisión del debate (codificada en §8/§9):** NO introducir `react-router`. `routes.ts` es **código propio** (un parser/serializer puro de ~80 líneas), no una librería. Meter `react-router` obligaría a recablear las 16 páginas, la paleta de comandos, la nav del shell y su suite de tests — recableado invasivo, con re-render extra, contra el riel "no degradar".

---

## 3. Principios y guardarraíles

1. **La URL es la fuente de verdad de la navegación.** El estado de navegación (tab + subtab + drawer + filtros compartibles) se serializa a la URL y se rehidrata desde ella; recargar o compartir reconstruye la vista.
2. **Reconciliar, no reinventar.** El deep-link de ejecución ya existe partido en dos (`?exec=` del backend vs. `?execution=` del frontend): F1 lo unifica con una clave canónica (`exec`) y un alias (`execution`), sin borrar al emisor.
3. **Extender el router casero, JAMÁS meter `react-router`.** `routes.ts` es un parser/serializer puro; App sigue usando su `pushState`/`popstate`. Sin librerías nuevas, sin re-render extra (no degradar).
4. **`pushState` JAMÁS dentro de un updater de `setState`.** La app monta en `<React.StrictMode>` (`main.tsx:18`) → en dev los updaters se invocan DOS veces → un `pushState` adentro duplicaría el historial. Todo `pushState` va en un `useEffect` dedicado con guard de `pathname+search` (regla ya escrita en `App.tsx:191-196`).
5. **Aditivo y backward-compatible.** Las URLs de primer nivel (`/history`, `/settings`, ...) siguen parseando idéntico. El contrato solo AGREGA (subtab, exec, filtros). Ninguna URL vieja se rompe.
6. **Query desconocida se PRESERVA (pass-through).** `routes.ts` solo posee `tab` (path seg 1), `subtab` (path seg 2) y `exec` (query especial). Todo otro query param (`?flag=`, `?path=` de Docs, `?server=` de DevOps, los filtros de F2) se preserva verbatim en el round-trip: `routes.ts` **nunca** descarta lo que no entiende. (Decisión explícita: descartarlo rompería los receptores ortogonales que ya existen.)
7. **`offset` NO se persiste ni se serializa.** La paginación se resetea al recargar/cambiar de filtro (comportamiento ya vigente en `setFilter`); persistir un offset abriría un vacío (página N sin datos si el dataset encogió). Los filtros SÍ persisten; el offset NO.
8. **Persistencia en dos capas, con roles distintos.** `useLocalStorageState` (keys `stacky.ui.history.*` / `stacky.ui.syslogs.*`) es lo que hace **sobrevivir** los filtros a F5 y al desmonte por cambio de tab. El querystring es para **compartir/deep-linkear** una vista filtrada. Son ortogonales y compatibles.
9. **Tests de lógica pura, sin `render()`.** No hay RTL/jsdom en `package.json`. Todo lo testeable es puro (`parseRoute`/`serializeRoute`, `*FiltersToQuery`/`*FiltersFromQuery`). El resto (que el drawer abra, que el sub-tab cambie) se verifica por smoke manual documentado.
10. **Cero trabajo extra al operador.** Sin flags, sin config, sin migración de datos. Las URLs "simplemente empiezan a funcionar y persistir". "Trabajo del operador: ninguno" por fase.
11. **Mono-operador sin auth.** Nada de rutas protegidas ni roles: `routes.ts` no valida `current_user`, no hay guards de permiso. Es navegación pura de un panel de un solo operador.
12. **F1+F3 son GATE del plan del centro de notificaciones (152) — y la divergencia YA existe (C3).** El 152 CRITICADO v2 define hoy `nav?: { tab: string; executionId?: number }` ejecutado vía `selectTab`, con el capture emitiendo `{tab:"team", executionId}` — formato ad-hoc que NO puede abrir el drawer (target equivocado y `selectTab` no propaga exec). Reconciliación obligatoria al implementar 152: su `onActivityNavigate` llama **`navigateToRoute({tab:"history", exec:nav.executionId})`** (A1). `serializeRoute` solo NO alcanza como contrato: sin el punto de entrada de navegación in-app, un pushState manual no notificaría a la página montada (ese era el bug C1).

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **deep-link** | Una URL que apunta directamente a un **subestado** de la app (no solo a una pantalla de primer nivel), de modo que pegarla o recargarla reconstruye exactamente esa vista. Ej.: `/history?exec=123` abre el Historial con el drawer de la ejecución 123. |
| **querystring** | La parte de la URL después del `?` (`window.location.search`), compuesta por pares `clave=valor` separados por `&`. Se lee/escribe con `URLSearchParams`. Ej.: en `/history?exec=123&status=error`, el querystring es `exec=123&status=error`. |
| **pushState / popstate** | `window.history.pushState(state, "", url)` cambia la URL en la barra **sin recargar** la página (navegación SPA). El evento `popstate` se dispara cuando el usuario usa Atrás/Adelante del navegador; el listener re-deriva el estado desde la nueva URL. Stacky ya usa ambos en `App.tsx` (router casero). |
| **StrictMode double-push** | En dev, `<React.StrictMode>` (`main.tsx:18`) invoca los updaters de `setState` (y algunos efectos) **DOS veces** para detectar efectos impuros. Si se hace `pushState` **dentro** de un updater de `setState`, se ejecuta dos veces → se duplica una entrada en el historial del navegador. Regla: `pushState` va SIEMPRE en un `useEffect` dedicado con guard, nunca dentro de un updater. |
| **useLocalStorageState** | Hook propio de Stacky (`hooks/useLocalStorageState.ts`) que es como `useState` pero **persiste** el valor en `localStorage` bajo una `key`: rehidrata el valor inicial al montar y lo re-escribe ante cada cambio. Tolerante a fallos (si `localStorage` no está, cae a estado en memoria). El Tablero de Tickets ya lo usa. |
| **router casero** | La navegación SPA de Stacky **sin librería**: un `Record<Tab,string>` (`TAB_PATHS`), una función `tabFromPath` (prefix match), `pushState` al navegar y un listener `popstate`. Este plan lo EXTIENDE (parser/serializer tipado), no lo reemplaza por `react-router`. |
| **round-trip parse/serialize** | La propiedad de que `parse` y `serialize` sean inversos: `serializeRoute(parseRoute(url))` reconstruye la URL canónica, y `parseRoute(serializeRoute(state))` reconstruye el estado. Para URLs no-canónicas (alias `execution`, `/?exec=` de raíz) el round-trip es **idempotente tras normalizar**: `parseRoute(serializeRoute(parseRoute(url)))` es igual a `parseRoute(url)`. Es lo que garantiza que no se pierda ni se corrompa estado al ir y volver de la URL. |
| **normalización** | Convertir una URL no-canónica a su forma canónica sin perder información: `?execution=123` → `?exec=123`; `/?exec=123` → `/history?exec=123` (para que el drawer, que vive en el Historial, efectivamente se abra). |
| **sub-tab** | Una pestaña de segundo nivel dentro de una página. Settings tiene 9 (`flow`, `sections`, `client-profile`, `transfer`, `webhooks`, `notifications`, `harness`, `playground`, `appearance`). Hoy invisibles a la URL; este plan las vuelve direccionables como 2do segmento del path (`/settings/appearance`). |
| **drawer** | El panel lateral de detalle de ejecución (`ExecutionDetailDrawer`) que se abre dentro del Historial cuando hay un `detailId`/`exec`. Este plan lo vuelve direccionable con `?exec=<id>`. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`frontend/src/App.tsx`, `frontend/src/pages/ExecutionHistoryPage.tsx`, `frontend/src/pages/SystemLogsPage.tsx`, `frontend/src/pages/SettingsPage.tsx`): `git status -- "<ruta>"`. Si hay WIP ajeno, STOP y avisar al orquestador (sesiones paralelas en el mismo árbol son un escenario real conocido). Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** frontend SIEMPRE por archivo desde el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con `npx vitest run src/<archivo>` (el `node_modules` del worktree `C:/wt/uxlog` puede estar roto — junction conocida). `npx tsc --noEmit` al terminar cada fase que toque `.tsx`. NUNCA `vitest run` de toda la suite: cross-file pollution conocida y documentada en este repo.
>
> **Orden de implementación:** F1 → F2 → F3 (F2 y F3 consumen `routes.ts` de F1; el reflejo de filtros vive en las páginas (F2 Paso 4) y los write-backs de subestado en F3 usan solo `parseRoute`/`serializeRoute` — sin dependencia F3→F2 más allá de convivir en los mismos archivos). Ver §6.

---

### F1 — El contrato de rutas tipado: `frontend/src/services/routes.ts` (parser/serializer + tests)

**Objetivo (1 frase):** crear el módulo `routes.ts` que parsea y serializa el esquema de URL de Stacky (`/{tab}/{subtab?}?exec=&...`), canonizando la clave `exec` (alias `execution`) y preservando la query desconocida, con `parse`/`serialize` inversos y 100% testeados. **Valor:** el contrato de navegación deja de vivir implícito y partido en dos; es un módulo tipado, testeado y reutilizable — **este es el entregable que el plan del centro de notificaciones consume (GATE recomendado).**

**Archivos:**
- NUEVO `frontend/src/services/routes.ts`
- NUEVO `frontend/src/services/__tests__/routes.test.ts`

**Paso 1 — `frontend/src/services/routes.ts`** (100% puro, sin JSX, sin `window` en las funciones puras — el `window` queda en los wrappers que las llaman desde `App.tsx`):

```ts
// frontend/src/services/routes.ts — Plan 165 F1
// Contrato de URL tipado de Stacky. Router CASERO (NO react-router).
// Parser/serializer PUROS: no tocan window (App.tsx pasa pathname/search).

export type Tab =
  | "team" | "tickets" | "review" | "unblocker" | "pm" | "logs"
  | "settings" | "docs" | "memory" | "diagnostics" | "history"
  | "migrador" | "devops" | "dbcompare" | "costcenter" | "planes";

// MOVIDO desde App.tsx (fuente única). App.tsx pasará a importarlo (F3).
export const TAB_PATHS: Record<Tab, string> = {
  team: "/", tickets: "/tickets", review: "/review", unblocker: "/unblocker",
  pm: "/pm", logs: "/logs", settings: "/settings", docs: "/docs",
  memory: "/memory", diagnostics: "/diagnostics", history: "/history",
  migrador: "/migrador", devops: "/devops", dbcompare: "/dbcompare",
  costcenter: "/costcenter", planes: "/planes",
};

export interface RouteState {
  tab: Tab;
  subtab?: string;                 // 2do segmento del path (hoy solo Settings lo usa)
  exec?: number;                   // ?exec=<id> — drawer de ejecución (clave canónica)
  query: Record<string, string>;   // TODO otro query param, preservado verbatim
}

// Clave canónica primero; alias legacy segundo (Plan de paleta emitía "execution").
const EXEC_KEYS = ["exec", "execution"] as const;

/** (interno) matchea el 1er segmento contra un tab conocido (nunca "team"/raíz). */
function matchKnownTab(segments: string[]): Tab | undefined {
  if (segments.length === 0) return undefined;
  const first = "/" + segments[0];
  const match = (Object.entries(TAB_PATHS) as [Tab, string][])
    .find(([, path]) => path !== "/" && path === first);
  return match?.[0];
}

/** tab desde el primer segmento del path. Vacío o desconocido => "team". */
export function tabFromSegments(segments: string[]): Tab {
  return matchKnownTab(segments) ?? "team";
}

/** Parsea pathname + search a RouteState (normalizado). No toca window.
 *  NUNCA recibe el hash (#...): los callers pasan pathname+search; el hash está
 *  fuera del contrato (Stacky no usa anclas). */
export function parseRoute(pathname: string, search: string): RouteState {
  const segments = pathname.split("/").filter(Boolean); // filter(Boolean) descarta
                                                         // "" de doble-slash, raíz y trailing slash
  const known = matchKnownTab(segments);
  const tab = known ?? "team";
  // C4: subtab SOLO si el 1er segmento es un tab CONOCIDO. Con tab desconocido
  // ("/nonexistent/foo") o raíz, subtab queda undefined — si no, el round-trip
  // serializaría "/foo" y el re-parse perdería el subtab (rompe la idempotencia §4).
  // Corolario: "team" (raíz "/") JAMÁS lleva subtab.
  const subtab = known && segments.length >= 2 ? segments[1] : undefined;

  const sp = new URLSearchParams(search);
  let exec: number | undefined;
  for (const k of EXEC_KEYS) {
    const raw = sp.get(k);
    if (raw != null) {
      // C4: SOLO enteros decimales no vacíos. Number("")===0, Number("0x10")===16
      // y Number("1.5")===1.5 son trampas: "?exec=" vacío abriría el drawer de la
      // ejecución 0. Regex estricta o exec queda undefined.
      if (/^\d+$/.test(raw)) exec = parseInt(raw, 10);
      break;  // la PRIMERA clave presente DECIDE; si vienen ambas (?exec=1&execution=2),
              // la segunda se ignora y NO pasa a query (ambas están en EXEC_KEYS).
    }
  }
  const query: Record<string, string> = {};
  sp.forEach((v, k) => { if (!EXEC_KEYS.includes(k as typeof EXEC_KEYS[number])) query[k] = v; });

  return normalizeInitial({ tab, subtab, exec, query });
}

/** Backward-compat: el backend emite `/?exec=` en la RAÍZ, pero el drawer vive en
 *  el Historial. Si hay exec y el tab no es "history", normalizamos a "history"
 *  para que el drawer efectivamente se abra (hoy ese link no hace NADA). */
function normalizeInitial(s: RouteState): RouteState {
  if (s.exec != null && s.tab !== "history") return { ...s, tab: "history" };
  return s;
}

/** Serializa RouteState a una URL canónica (path + "?" + querystring ordenado). */
export function serializeRoute(s: RouteState): string {
  const base = TAB_PATHS[s.tab];                          // "/", "/history", "/settings", ...
  // C4: "team" (base "/") JAMÁS lleva subtab — "/x" colisionaría con el espacio de
  // tabs desconocidos y el round-trip no sería idempotente. Se descarta defensivo.
  const path = s.subtab && base !== "/"
    ? `${base}/${s.subtab}`                               // "/settings/appearance"
    : base;                                               // "/settings" | "/"
  const sp = new URLSearchParams();
  // query preservada primero, con claves ordenadas (round-trip estable/determinista)
  Object.keys(s.query).sort().forEach((k) => sp.set(k, s.query[k]));
  if (s.exec != null) sp.set("exec", String(s.exec));     // SIEMPRE clave canónica "exec"
  const qs = sp.toString();
  return qs ? `${path}?${qs}` : path;
}
```

**Casos borde (todos cubiertos por el test):**
- **Ruta sin subtab:** `/settings` → `{tab:"settings", subtab:undefined, query:{}}`; serializa a `"/settings"`.
- **entityId ausente:** `/history` (sin `exec`) → `{tab:"history", exec:undefined}`; serializa a `"/history"`. `?exec=abc` (no numérico) → `exec` queda `undefined` (no rompe).
- **Query desconocida se PRESERVA:** `/docs?path=a/b` → `{tab:"docs", query:{path:"a/b"}}`; serializa preservando `path` (decisión §3.6).
- **Doble-slash:** `//history` → `filter(Boolean)` → `["history"]` → `{tab:"history"}`. `/settings//appearance` → `["settings","appearance"]` → subtab `"appearance"`.
- **Raíz:** `/` → `segments=[]` → `tabFromSegments([])` → `"team"`.
- **Normalización backward-compat:** `/?exec=123` → `{tab:"history", exec:123}` (NO es identidad — es normalización documentada; ese link hoy no hace nada). `serializeRoute` de eso → `"/history?exec=123"`.
- **Alias legacy:** `/history?execution=123` → `{tab:"history", exec:123}`; serializa a `"/history?exec=123"` (canoniza la clave).
- **`?exec=` con valor VACÍO (C4):** `/history?exec=` → `exec:undefined` (la regex `/^\d+$/` rechaza `""`; sin ella, `Number("")===0` abriría el drawer de la ejecución 0). Ídem `?exec=0x10`, `?exec=1.5`, `?exec=-3` → `undefined`. Al serializar, un exec inválido simplemente NO aparece (se pierde: es basura, comportamiento documentado).
- **Ambas claves a la vez (C4):** `/history?exec=1&execution=2` → `exec:1` (la primera clave de `EXEC_KEYS` decide); `execution=2` NO pasa a `query` (ambas claves son propiedad de routes.ts).
- **Tab DESCONOCIDO con segundo segmento (C4):** `/nonexistent/foo` → `{tab:"team", subtab:undefined}` (el subtab se descarta si el 1er segmento no es un tab conocido); serializa a `"/"`. Idempotente tras el primer parse.
- **Trailing slash (C7):** `/history/` → `["history"]` → `{tab:"history", subtab:undefined}`.
- **Hash (C7, fuera de contrato):** `parseRoute` recibe `pathname+search`, NUNCA `location.hash`. Stacky no usa anclas; los write-backs con `replaceState` pueden descartarlo sin pérdida.
- **StrictMode double-push:** las funciones puras NO tocan `window`; el `pushState` lo hace App en un efecto con guard (F3). Nunca dentro de un updater.

**Paso 2 — Test** `frontend/src/services/__tests__/routes.test.ts`:

| Test | Qué afirma |
|---|---|
| `parse_primer_nivel` | `parseRoute("/history","")` → `{tab:"history", subtab:undefined, exec:undefined, query:{}}`; `parseRoute("/","")` → `tab:"team"`. |
| `parse_subtab` | `parseRoute("/settings/appearance","")` → `{tab:"settings", subtab:"appearance"}`. |
| `parse_exec_canonico` | `parseRoute("/history","?exec=123")` → `exec:123`. |
| `parse_exec_alias` | `parseRoute("/history","?execution=123")` → `exec:123` (alias). |
| `parse_exec_raiz_normaliza` | `parseRoute("/","?exec=123")` → `{tab:"history", exec:123}` (backward-compat). |
| `parse_query_desconocida_preserva` | `parseRoute("/docs","?path=a/b&flag=X")` → `query:{path:"a/b", flag:"X"}`. |
| `parse_doble_slash` | `parseRoute("//history","")` → `tab:"history"`; `parseRoute("/settings//appearance","")` → `subtab:"appearance"`. |
| `parse_trailing_slash` | `parseRoute("/history/","")` → `{tab:"history", subtab:undefined}` (C7). |
| `parse_exec_no_numerico` | `parseRoute("/history","?exec=abc")` → `exec:undefined` (no rompe). |
| `parse_exec_vacio_y_formas_raras` | `parseRoute("/history","?exec=")` → `exec:undefined`; ídem `?exec=0x10`, `?exec=1.5`, `?exec=-3` → `undefined` (C4: regex `/^\d+$/`, jamás `Number()` pelado). |
| `parse_ambas_claves` | `parseRoute("/history","?exec=1&execution=2")` → `exec:1` y `query` SIN `execution` (C4: la primera clave de `EXEC_KEYS` decide). |
| `parse_tab_desconocido_sin_subtab` | `parseRoute("/nonexistent/foo","")` → `{tab:"team", subtab:undefined}`; `serializeRoute` de eso → `"/"`; re-parse deep-equals (C4: idempotencia §4). |
| `serialize_canonico` | `serializeRoute({tab:"settings", subtab:"appearance", query:{}})` → `"/settings/appearance"`; `serializeRoute({tab:"history", exec:123, query:{}})` → `"/history?exec=123"`. |
| `serialize_preserva_query` | `serializeRoute({tab:"docs", query:{path:"a/b"}})` incluye `path=a%2Fb` (o `path=a/b` según `URLSearchParams`); `parseRoute` de la salida recupera `path:"a/b"`. |
| `roundtrip_identidad_canonica` | Para cada URL canónica de una lista (`/history`, `/settings/appearance`, `/history?exec=9`, `/tickets`), `serializeRoute(parseRoute(url, "")) === url` (separando path/search). |
| `roundtrip_idempotente_no_canonica` | Para `/?exec=123` y `/history?execution=123`: `parseRoute(serializeRoute(parseRoute(url)))` deep-equals `parseRoute(url)` (idempotencia tras normalizar). |

**Criterio de aceptación BINARIO:** `npx vitest run src/services/__tests__/routes.test.ts` → exit 0; `npx tsc --noEmit` → exit 0.

**Flag:** ninguna. **Runtimes:** navegación de la UI del panel; agnóstica del runtime de agentes (los 3 ven la misma URL). **Fallback:** toda entrada degrada a `{tab:"team", query:{}}` sin lanzar; `exec` no numérico → `undefined`. **Trabajo del operador: ninguno.**

**GATE:** marcar F1 como **GATE recomendado** antes de implementar el plan del centro de notificaciones. Ese plan debe importar `serializeRoute`/`parseRoute` para su deep-link notificación→run, no inventar un formato propio.

---

### F2 — Los filtros sobreviven: `useLocalStorageState` + reflejo en querystring (Historial y Logs)

**Objetivo (1 frase):** migrar los filtros de `ExecutionHistoryPage` y `SystemLogsPage` de `useState` puro a `useLocalStorageState` (keys `stacky.ui.history.*` / `stacky.ui.syslogs.*`) para que sobrevivan F5 y el cambio de tab, y reflejarlos en el querystring (excluyendo `offset`) para poder compartir una vista filtrada. **Valor:** el operador deja de reconfigurar los mismos filtros cada vez que entra a una página o recarga.

**Archivos:**
- NUEVO `frontend/src/services/routeFilters.ts` (helpers PUROS filtros↔querystring)
- NUEVO `frontend/src/services/__tests__/routeFilters.test.ts`
- MODIFICADO `frontend/src/pages/ExecutionHistoryPage.tsx` (`useState`→`useLocalStorageState` + reflejo)
- MODIFICADO `frontend/src/pages/SystemLogsPage.tsx` (`useState`→`useLocalStorageState` + reflejo)

**Paso 1 — `frontend/src/services/routeFilters.ts`** (puro; convierte los objetos de filtros a/desde `Record<string,string>` de query, SIN `offset`):

```ts
// frontend/src/services/routeFilters.ts — Plan 165 F2
// Serialización PURA de filtros de página a/desde querystring. offset NUNCA se
// serializa (la paginación no se comparte ni se persiste — ver plan §3.7).

export interface HistoryFilters {
  agent_type: string; runtime: string; status: string; days: string;
  limit: number; offset: number;   // offset se ignora al serializar
}

/** Filtros de Historial -> Record de query (solo claves NO vacías; sin offset). */
export function historyFiltersToQuery(f: HistoryFilters): Record<string, string> {
  const q: Record<string, string> = {};
  if (f.agent_type) q.agent_type = f.agent_type;
  if (f.runtime) q.runtime = f.runtime;
  if (f.status) q.status = f.status;
  if (f.days) q.days = f.days;
  // limit y offset NO se serializan (limit es fijo por página; offset no se comparte)
  return q;
}

/** Record de query -> filtros parciales de Historial (para rehidratar desde URL). */
export function historyFiltersFromQuery(q: Record<string, string>): Partial<HistoryFilters> {
  const out: Partial<HistoryFilters> = {};
  if (q.agent_type) out.agent_type = q.agent_type;
  if (q.runtime) out.runtime = q.runtime;
  if (q.status) out.status = q.status;
  if (q.days) out.days = q.days;
  return out;
}

export interface SysLogFilters {
  level: string; source: string; action: string; q: string;
  execution_id: string; ticket_id: string; from: string; to: string;
}

const SYSLOG_KEYS: (keyof SysLogFilters)[] =
  ["level", "source", "action", "q", "execution_id", "ticket_id", "from", "to"];

export function sysLogFiltersToQuery(f: SysLogFilters): Record<string, string> {
  const out: Record<string, string> = {};
  for (const k of SYSLOG_KEYS) { if (f[k]) out[k] = f[k]; }
  return out;
}

export function sysLogFiltersFromQuery(q: Record<string, string>): Partial<SysLogFilters> {
  const out: Partial<SysLogFilters> = {};
  for (const k of SYSLOG_KEYS) { if (q[k]) out[k] = q[k]; }
  return out;
}

// C5: claves de filtro que cada página POSEE en el querystring. Exportadas para
// que el efecto de reflejo (Paso 4) las quite de current.query sin acumular —
// NADA de "omitFilterKeys" inlineado a criterio del implementador.
export const HISTORY_FILTER_QUERY_KEYS = ["agent_type", "runtime", "status", "days"] as const;
export const SYSLOG_FILTER_QUERY_KEYS = SYSLOG_KEYS;

/** Quita de un Record de query las claves listadas (puro; para el Paso 4). */
export function omitKeys(
  q: Record<string, string>, keys: readonly string[],
): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(q)) { if (!keys.includes(k)) out[k] = v; }
  return out;
}

/** C2: resolución de filtros AL MONTAR (puro, testeado). Precedencia:
 *  - Si la URL trae >=1 clave de filtro => la URL manda COMPLETA la vista
 *    (defaults + URL, IGNORANDO lo persistido): una URL compartida reproduce
 *    EXACTAMENTE la vista del que la compartió (sus campos vacíos no viajan,
 *    y no deben contaminarse con los filtros persistidos del receptor).
 *  - Si la URL no trae ninguna => defaults + persistido. El spread sobre
 *    defaults es además el merge ANTI-DRIFT (C5): useLocalStorageState hace
 *    JSON.parse sin merge, así que un shape persistido viejo (campo nuevo
 *    agregado a Filters) completa el faltante con su default en vez de
 *    filtrar undefined a la API. No hace falta versionar la key.
 */
export function resolveMountFilters<T extends object>(
  defaults: T, persisted: Partial<T>, fromUrl: Partial<T>,
): T {
  return Object.keys(fromUrl).length > 0
    ? { ...defaults, ...fromUrl }
    : { ...defaults, ...persisted };
}
```

**Paso 2 — `ExecutionHistoryPage.tsx`.** Reemplazar `const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)` (`:72`) por:

```ts
const [filters, setFilters] = useLocalStorageState<Filters>("stacky.ui.history.filters", DEFAULT_FILTERS);
```

Importar el hook: `import { useLocalStorageState } from "../hooks/useLocalStorageState";`.

**Paso 2b (OBLIGATORIO — C2/C5) — efecto de MONTAJE único** que aplica en un solo `setFilters`: (a) el merge anti-drift sobre defaults, (b) la precedencia URL-gana-completa, y (c) el reset de `offset` a 0 (NO "a criterio": esta es LA forma):

```ts
// Montaje: precedencia URL > persistido > defaults, anti-drift y offset 0 (§3.7).
useEffect(() => {
  const { query } = parseRoute(window.location.pathname, window.location.search);
  const fromUrl = historyFiltersFromQuery(query);
  setFilters((persisted) => ({
    ...resolveMountFilters(DEFAULT_FILTERS, persisted, fromUrl),
    offset: 0,
  }));
}, []);  // SOLO al montar
```

Con esto, pegar `/history?status=error&agent_type=qa` en una pestaña nueva reproduce EXACTAMENTE esa vista (los filtros de la URL pisan lo persistido); sin filtros en la URL, rehidrata lo persistido con shape saneado. Nota deliberada: al aplicar filtros de URL, el efecto de persistencia del hook los escribe a `localStorage` — la vista a la que navegaste PASA a ser tu estado actual (coherente y documentado). `offset` queda dentro del objeto persistido pero SIEMPRE vuelve a 0 al montar; separar `offset` a su propio `useState` (como `SystemLogsPage`) NO se hace en este plan (cambio extra sin valor: el reset ya cumple §3.7).

**Paso 3 — `SystemLogsPage.tsx`.** Reemplazar `const [filters, setFilters] = useState({...})` (`:133-142`) por:

```ts
const [filters, setFilters] = useLocalStorageState("stacky.ui.syslogs.filters", {
  level: "", source: "", action: "", q: "", execution_id: "", ticket_id: "", from: "", to: "",
});
```

`offset` ya está en su propio `useState(0)` (hoy `:134`; anclar por texto) → **se deja como está** (no se persiste, cumple §3.7 sin tocar nada). Importar el hook. **Y el mismo efecto de montaje OBLIGATORIO que el Paso 2b (C2)**, con sus helpers:

```ts
useEffect(() => {
  const { query } = parseRoute(window.location.pathname, window.location.search);
  const fromUrl = sysLogFiltersFromQuery(query);
  setFilters((persisted) => resolveMountFilters(SYSLOG_DEFAULTS, persisted, fromUrl));
  setOffset(0);
}, []);  // SOLO al montar
```

(`SYSLOG_DEFAULTS` es el objeto literal de 8 campos vacíos que ya se pasa como default al hook — extraerlo a una `const` para no duplicarlo; `clearFilters` ya usa ese mismo literal.)

**Paso 4 — Reflejo en querystring (ambas páginas).** En un `useEffect` con dependencia `[filters]`, reflejar los filtros en la URL SIN recargar y SIN romper el StrictMode double-push (usar `replaceState`, no `pushState`, para no ensuciar el historial con cada tecleo de filtro; y con guard de `search` actual):

```ts
useEffect(() => {
  const current = parseRoute(window.location.pathname, window.location.search);
  const next = serializeRoute({
    ...current,
    query: { ...omitKeys(current.query, HISTORY_FILTER_QUERY_KEYS), ...historyFiltersToQuery(filters) },
  });
  const target = window.location.pathname + window.location.search;
  if (next !== target) {
    window.history.replaceState({}, "", next);
  }
}, [filters]);
```

(En `SystemLogsPage`, mismo efecto con `SYSLOG_FILTER_QUERY_KEYS` y `sysLogFiltersToQuery`. `omitKeys` es el helper EXPORTADO de `routeFilters.ts` (Paso 1) con las constantes de claves — C5: nada inlineado "a criterio". Se usa `replaceState` a propósito: el filtrado es de alta frecuencia y no debe generar entradas de historial. `parseRoute`/`serializeRoute` de F1 preservan `exec` y toda query ajena. El guard `!next.startsWith("//")` de v1 se ELIMINÓ: con el fix C4 (team jamás serializa subtab) ese caso es imposible por construcción.)

**Paso 5 — Test** `frontend/src/services/__tests__/routeFilters.test.ts`:

| Test | Qué afirma |
|---|---|
| `history_to_query_omite_vacios_y_offset` | `historyFiltersToQuery({agent_type:"qa", runtime:"", status:"error", days:"", limit:50, offset:100})` → `{agent_type:"qa", status:"error"}` (sin `offset`, sin `limit`, sin vacíos). |
| `history_roundtrip` | `historyFiltersFromQuery(historyFiltersToQuery(f))` recupera los campos no vacíos de `f`. |
| `syslog_to_query_8_campos` | `sysLogFiltersToQuery` con los 8 campos llenos → 8 claves; con vacíos → solo las llenas. |
| `syslog_roundtrip` | `sysLogFiltersFromQuery(sysLogFiltersToQuery(f))` recupera los 8 campos no vacíos. |
| `offset_nunca_en_query` | Ninguna clave `offset` aparece en la salida de `historyFiltersToQuery`. |
| `resolve_mount_url_gana_completa` | `resolveMountFilters(DEF, {status:"error", agent_type:"qa"}, {status:"running"})` → `{...DEF, status:"running"}` — con >=1 clave en URL, lo persistido se IGNORA entero (C2: reproducción exacta de la vista compartida). |
| `resolve_mount_sin_url_usa_persistido` | `resolveMountFilters(DEF, {status:"error"}, {})` → `{...DEF, status:"error"}`. |
| `resolve_mount_anti_drift` | `resolveMountFilters(DEF, persistidoConShapeViejo, {})` completa los campos faltantes con su default — ningún `undefined` en el resultado (C5). |
| `omit_keys` | `omitKeys({a:"1", agent_type:"qa"}, HISTORY_FILTER_QUERY_KEYS)` → `{a:"1"}`. |

**Criterio de aceptación BINARIO:** `npx vitest run src/services/__tests__/routeFilters.test.ts` → exit 0; `npx tsc --noEmit` → exit 0. **Verificación manual (documentada, sin operador):** en Historial, setear filtros → recargar (F5): los filtros persisten; cambiar a otro tab y volver: los filtros persisten; la URL muestra `?agent_type=...&status=...` (sin `offset`); pegar esa URL en otra pestaña reproduce la vista filtrada. Ídem en Logs del Sistema con sus 8 filtros.

**Flag:** ninguna. **Runtimes:** UI del panel; agnóstica del runtime de agentes. **Fallback:** si `localStorage` no está disponible (modo privado/cuota), `useLocalStorageState` ya cae a estado en memoria sin romper (comportamiento existente del hook). **Trabajo del operador: ninguno.**

---

### F3 — Subestado en la URL: sub-tabs de Settings y drawer de ejecución (parseados por `routes.ts`)

**Objetivo (1 frase):** representar en la URL el drawer de detalle de ejecución (`?exec=<id>`) y los sub-tabs de Settings (`/settings/appearance`, etc.), parseándolos con `routes.ts` (F1) y pasándolos como prop inicial a las páginas, además de extender el router casero de `App.tsx` (parseo de subtab/exec + `popstate` + normalización backward-compat). **Valor:** pegar una URL de subestado abre exactamente ese subestado; el deep-link de Slack finalmente funciona.

**Archivos:**
- MODIFICADO `frontend/src/App.tsx` (importar `routes.ts`; ruta como ESTADO `useState<RouteState>`; `navigateToRoute` (A1); props vivas; `popstate` re-deriva todo; canonicalización al montar)
- MODIFICADO `frontend/src/pages/SettingsPage.tsx` (prop viva `subTab` + patrón `lastApplied`; write-back del sub-tab al path (A2); coexistir con el receptor `?flag=`)
- MODIFICADO `frontend/src/pages/ExecutionHistoryPage.tsx` (prop viva `exec` + patrón `lastApplied`; write-back del drawer a `?exec=` (A2); reemplazar el receptor `?execution=` roto)
- NUEVO `frontend/src/services/__tests__/routesDeepLink.test.ts`

**Paso 1 — `App.tsx` (extender el router casero). La ruta es ESTADO, no un ref congelado (C1).**

> **Regla dura v2 (C1):** PROHIBIDO el patrón v1 de `useRef<RouteState>` capturado al montar + props `initial*` que alimentan un `useState`. `useState(initial)` IGNORA los cambios de prop → los deep-links solo funcionarían con F5, y la navegación in-app (el caso EXACTO del gate del plan 152) y Atrás/Adelante con otro exec/subtab quedarían muertos.

- Importar de `routes.ts`: `import { parseRoute, serializeRoute, TAB_PATHS, type Tab, type RouteState } from "./services/routes";` y **BORRAR** las definiciones locales de `type Tab`, `TAB_PATHS` y `tabFromPath` (hoy `:45-68`; anclar por texto) → fuente única en `routes.ts`.
- **Reemplazar** `const [tab, setTab] = useState<Tab>(() => tabFromPath(window.location.pathname))` (hoy `:71`) por la ruta completa como estado (verificado: `setTab` solo se usa en esa declaración y en el listener de `popstate` — el reemplazo es acotado):

```ts
const [route, setRoute] = useState<RouteState>(() =>
  parseRoute(window.location.pathname, window.location.search),
);
const tab = route.tab;  // todo el JSX existente que lee `tab` sigue idéntico
```

- **[ADICIÓN ARQUITECTO A1] `navigateToRoute` — LA API de navegación tipada** (todo pasa por acá; `selectTab`/`navigateTo` conservan su firma y la reusan por dentro; es el punto de consumo del plan 152):

```ts
const navigateToRoute = (next: RouteState) => {
  const url = serializeRoute(next);
  const current = window.location.pathname + window.location.search;
  if (url !== current) window.history.pushState({}, "", url);  // guard (regla §3.4)
  setRoute(next);
};
const selectTab = (next: Tab) => navigateToRoute({ tab: next, query: {} });
const navigateTo = (path: string) => {           // la paleta sigue pasando strings
  const [pathname, search = ""] = path.split("?");
  navigateToRoute(parseRoute(pathname, search ? `?${search}` : ""));
};
```

  (`navigateToRoute` NO se llama dentro de ningún updater de `setState` — el `pushState` queda fuera de updaters, cumpliendo §3.4. Nota: `selectTab` con `query:{}` LIMPIA el querystring al cambiar de tab, comportamiento idéntico al actual `pushState(TAB_PATHS[next])`; los filtros no se pierden porque persisten en `localStorage` (F2) y la página los re-refleja al montar.)
- **`popstate` re-deriva TODO el estado** (no solo el tab — C1):

```ts
useEffect(() => {
  const onPopState = () =>
    setRoute(parseRoute(window.location.pathname, window.location.search));
  window.addEventListener("popstate", onPopState);
  return () => window.removeEventListener("popstate", onPopState);
}, []);
```

- **Normalización backward-compat al montar (OBLIGATORIA, no "si querés" — C5):** `parseRoute` ya normaliza `/?exec=` → `{tab:"history", exec}` así que App monta en el tab correcto sin lógica extra; y un `useEffect` de montaje reescribe la barra a la forma canónica:

```ts
useEffect(() => {
  const canonical = serializeRoute(route);
  const current = window.location.pathname + window.location.search;
  if (canonical !== current) window.history.replaceState({}, "", canonical);
  // replaceState (no pushState): no duplica historial ni dispara el double-push.
}, []);  // SOLO al montar
```

- **Pasar props VIVAS a las páginas** en el fragment `pages` (hoy `:247` y vecinas; anclar por texto). Se llaman `exec`/`subTab` (NO `initial*`: son props que CAMBIAN con la ruta):

```tsx
{tab === "history"  && <ExecutionHistoryPage exec={route.exec ?? null} />}
{tab === "settings" && <SettingsPage subTab={route.subtab ?? null} />}
```

**Paso 2 — `SettingsPage.tsx`.** Aceptar la prop VIVA `subTab`, sincronizarla con el patrón `lastApplied` (C1), y reflejar el sub-tab elegido por click de vuelta al path ([ADICIÓN ARQUITECTO A2]). Coexiste con el receptor `?flag=` (hoy `:115-117`; anclar por texto):

```ts
export default function SettingsPage({ subTab }: { subTab?: string | null }) {
  const [sub, setSub] = useState<SubTab>(
    isValidSubTab(subTab) ? (subTab as SubTab) : "flow",
  );
  // C1 — sincronización con la prop VIVA: reacciona SOLO a cambios de la prop
  // (popstate / navegación in-app), sin pisar la elección local del operador.
  const lastAppliedSub = useRef(subTab);
  useEffect(() => {
    if (subTab !== lastAppliedSub.current) {
      lastAppliedSub.current = subTab;
      if (isValidSubTab(subTab)) setSub(subTab as SubTab);
    }
  }, [subTab]);
  // A2 — write-back: el sub-tab elegido por CLICK se refleja en el path
  // (/settings/<sub>) vía replaceState con guard. La URL SIEMPRE dice dónde
  // estás parado; copiarla comparte la vista exacta. replaceState: cambiar de
  // sub-tab no genera entradas de historial.
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    if (current.tab !== "settings") return;          // guard: solo montada en /settings
    const next = serializeRoute({ ...current, subtab: sub === "flow" ? undefined : sub });
    const target = window.location.pathname + window.location.search;
    if (next !== target) window.history.replaceState({}, "", next);
  }, [sub]);
  // El receptor ?flag= existente sigue forzando "harness" + highlight; si hay
  // AMBOS (subtab por path y ?flag=), gana ?flag= (comportamiento actual: abre
  // harness para resaltar la flag). Documentar esta precedencia.
```

donde `isValidSubTab(x)` chequea que `x` sea una de las 9 claves de `SubTab` (una función pura, testeable). El sub-tab por path (`/settings/appearance`) es aditivo: si el path no trae subtab válido, cae a `"flow"` como hoy. **Convención canónica A2:** `"flow"` (el default) se representa SIN segmento (`/settings`, no `/settings/flow`) — así las URLs de primer nivel de hoy siguen siendo canónicas.

**Paso 3 — `ExecutionHistoryPage.tsx`.** Aceptar la prop VIVA `exec`, **reemplazar** el receptor `?execution=` roto (hoy `:59-65`, el `useEffect` con `readQueryParam("execution")`; anclar por texto) y reflejar el drawer de vuelta a la URL ([ADICIÓN ARQUITECTO A2]):

```ts
export default function ExecutionHistoryPage({ exec }: { exec?: number | null }) {
  const [detailId, setDetailId] = useState<number | null>(exec ?? null);
  // BORRAR el useEffect que leía readQueryParam("execution"): routes.ts (vía App)
  // ya parseó exec/execution y lo pasa como prop viva.
  // C1 — sincronización con la prop VIVA (patrón lastApplied): reacciona SOLO a
  // cambios de la prop. Sin este patrón, cerrar el drawer con route.exec aún
  // seteado lo re-abriría en el próximo render (loop prop→estado).
  const lastAppliedExec = useRef(exec);
  useEffect(() => {
    if (exec !== lastAppliedExec.current) {
      lastAppliedExec.current = exec;
      setDetailId(exec ?? null);
    }
  }, [exec]);
  // A2 — write-back: abrir el drawer por CLICK escribe ?exec=<id> en la URL;
  // cerrarlo lo quita. replaceState con guard (sin entradas de historial).
  useEffect(() => {
    const current = parseRoute(window.location.pathname, window.location.search);
    if (current.tab !== "history") return;           // guard: solo montada en /history
    const next = serializeRoute({ ...current, exec: detailId ?? undefined });
    const target = window.location.pathname + window.location.search;
    if (next !== target) window.history.replaceState({}, "", next);
  }, [detailId]);
```

El drawer se abre al montar si `exec` viene con valor, y TAMBIÉN cuando la prop cambia con la página ya montada (popstate o navegación in-app — C1). Esto cierra el bucle roto de §2.1: un `/?exec=123` de Slack → `parseRoute` normaliza a `{tab:"history", exec:123}` → App monta (o actualiza) `ExecutionHistoryPage` con `exec={123}` → el drawer abre. Y con A2, una ejecución abierta por click queda compartible copiando la URL de la barra. (Convivencia con el reflejo de filtros de F2: ambos efectos leen `window.location` fresco y solo tocan sus propias claves — el de filtros preserva `exec` vía `...current`, el del drawer preserva los filtros vía `...current`; no se pisan.)

**Paso 4 — Test** `frontend/src/services/__tests__/routesDeepLink.test.ts` (lógica pura de parseo; los componentes se verifican por smoke):

| Test | Qué afirma |
|---|---|
| `deeplink_settings_subtab` | `parseRoute("/settings/appearance","")` → `{tab:"settings", subtab:"appearance"}`. |
| `deeplink_settings_subtab_invalido` | `parseRoute("/settings/xyz","")` → `subtab:"xyz"` (routes no valida; la validación vive en `isValidSubTab`, que se testea acá: `isValidSubTab("appearance")===true`, `isValidSubTab("xyz")===false`, `isValidSubTab(null)===false`). |
| `deeplink_history_exec` | `parseRoute("/history","?exec=123")` → `{tab:"history", exec:123}`. |
| `deeplink_slack_root_exec` | `parseRoute("/","?exec=123")` → `{tab:"history", exec:123}` (el link de Slack ahora abre el drawer). |
| `deeplink_alias_execution` | `parseRoute("/history","?execution=456")` → `exec:456`. |
| `deeplink_preserva_flag` | `parseRoute("/settings/harness","?flag=STACKY_X")` → `{tab:"settings", subtab:"harness", query:{flag:"STACKY_X"}}` (el receptor `?flag=` sigue teniendo su dato). |

(`isValidSubTab` se exporta desde `SettingsPage.tsx` o desde un pequeño helper puro; si se exporta desde el `.tsx`, el test lo importa sin renderizar. Alternativa: definir el array de sub-tabs en un `.ts` aparte para no arrastrar JSX al test.)

**Criterio de aceptación BINARIO:** `npx vitest run src/services/__tests__/routesDeepLink.test.ts` → exit 0; `npx tsc --noEmit` → exit 0. **Verificación manual (documentada, sin operador):** pegar `/settings/appearance` → abre Settings en Apariencia; pegar `/history?exec=<id-real>` → abre el Historial con el drawer de esa ejecución; pegar `/?exec=<id-real>` (forma de Slack) → normaliza a `/history?exec=` y abre el drawer; **Atrás/Adelante re-derivan tab, sub-tab Y drawer con la página YA montada (C1)** — p.ej. `/settings/appearance` → click a `harness` → Atrás vuelve a `appearance`; abrir el drawer por CLICK escribe `?exec=` en la barra y cerrarlo lo quita (A2); pegar `/history?exec=<id-inexistente>` → el drawer abre y muestra el estado de error/vacío que el drawer ya tiene para un fetch fallido (NO pantalla blanca; el contrato de rutas no valida existencia — la valida el fetch, como hoy).

**Flag:** ninguna. **Runtimes:** navegación de la UI; agnóstica del runtime de agentes. **Fallback:** subtab inválido → `"flow"`; `exec` ausente/no numérico → drawer cerrado; exec inexistente en la DB → el drawer muestra su error de fetch (comportamiento actual del drawer, sin cambio); sin `localStorage`/con URL vieja de primer nivel → comportamiento idéntico al de hoy. **Trabajo del operador: ninguno.**

---

## 6. Orden de implementación (numerado)

1. **F1** — `frontend/src/services/routes.ts` (parser/serializer puro + `TAB_PATHS` movido) + `routes.test.ts`. Es el cimiento; F2 y F3 lo consumen. **GATE recomendado del plan del centro de notificaciones.**
2. **F2** — `routeFilters.ts` + `routeFilters.test.ts` + migración de filtros a `useLocalStorageState` en `ExecutionHistoryPage` y `SystemLogsPage` + reflejo en querystring (`replaceState`). Consume `parseRoute`/`serializeRoute` de F1.
3. **F3** — extender el router casero en `App.tsx` (importar `routes.ts`, borrar las defs locales, **ruta como ESTADO** + `navigateToRoute` (A1), `popstate` re-deriva todo, canonicalizar al montar) + props VIVAS con patrón `lastApplied` y write-backs `replaceState` (A2) en `SettingsPage` y `ExecutionHistoryPage` (reemplazando el receptor `?execution=` roto) + `routesDeepLink.test.ts`.

Correr `npx tsc --noEmit` al terminar CADA fase que toque `.tsx` (F2, F3) y al final. Cada test SIEMPRE por archivo desde el checkout real. Antes de F3, **coordinar el contrato de F1 con el plan del centro de notificaciones** (§3.12).

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Alguien "resuelve" la navegación metiendo `react-router`. | **Prohibido explícito** (§8/§9): el debate lo evaluó y lo rechazó (recableado invasivo + re-render + tests). `routes.ts` es código propio puro. |
| R2 | `pushState` dentro de un updater de `setState` duplica el historial (StrictMode). | Regla dura (§3.4, ya escrita en `App.tsx:191-196`): todo `pushState`/`replaceState` en `useEffect` dedicado con guard de `pathname+search`. F2 usa `replaceState` (no ensucia el historial con cada tecleo de filtro). |
| R3 | El deep-link de Slack sigue sin funcionar por la clave/path partidos. | F1 canoniza `exec` (alias `execution`) y `normalizeInitial` lleva `/?exec=` a `/history?exec=`; el test `deeplink_slack_root_exec` lo fija; `ExecutionHistoryPage` recibe la prop VIVA `exec` (C1). |
| R4 | Persistir `offset` reabre una página vacía si el dataset encogió. | `offset` NUNCA se persiste ni se serializa (§3.7). En `SystemLogsPage` ya está aparte; en `ExecutionHistoryPage` se resetea a 0 al rehidratar. `offset_nunca_en_query` lo fija. |
| R5 | `routes.ts` descarta un query param ajeno (`?flag=`, `?path=`, `?server=`) y rompe un receptor. | Query desconocida se **preserva** verbatim (§3.6); `parse_query_desconocida_preserva` y `deeplink_preserva_flag` lo fijan. |
| R6 | Colisión con la sesión paralela que toca los mismos `.tsx` (App/páginas). | Pre-flight `git status -- "<ruta>"` por archivo caliente; staging quirúrgico; el implementador NO commitea (lo hace el orquestador). |
| R7 | El plan del centro de notificaciones se implementa ANTES y nace con un deep-link ad-hoc. **CONFIRMADO PARCIAL (C3):** el 152 CRITICADO v2 YA define `nav {tab:"team", executionId}` ejecutado vía `selectTab` — apunta a "team" (no a "history") y `selectTab` no propaga exec: ese intent NO puede abrir el drawer. | F1+F3 son **GATE recomendado**; al implementar 152, su `onActivityNavigate` debe llamar **`navigateToRoute({tab:"history", exec:executionId})`** (A1) en lugar de `selectTab(nav.tab)`; es un adapter de una línea que corrige el target y propaga el exec. Registrado en §3.12. |
| R8 | El receptor `?flag=` de Settings y el sub-tab por path se pisan. | Precedencia documentada (F3 Paso 2): si hay ambos, gana `?flag=` (abre `harness` para resaltar). Ambos coexisten; ninguno se borra. Nota A2: mientras `?flag=` fuerza `harness`, el write-back reescribirá el path a `/settings/harness` — coherente (la URL dice lo que se ve). |
| R11 | Loop prop↔estado local: con la prop viva `exec`, cerrar el drawer (detailId→null) con `route.exec` aún seteado lo re-abriría en el próximo render; ídem sub-tab. | Patrón **`lastApplied` ref** (F3 Pasos 2-3): el efecto de sincronización solo actúa ante CAMBIOS de la prop, nunca re-aplica el mismo valor. El write-back A2 usa `replaceState` con guard `next !== target` (idempotente, sin historial). |
| R9 | Sin RTL/jsdom no se puede testear que el drawer/subtab realmente abran. | La lógica testeable es pura (`parseRoute`/`serializeRoute`/`isValidSubTab`/filtros); la apertura efectiva se verifica por **smoke manual documentado** por fase. Es el mismo patrón de los planes de UX previos. |
| R10 | `serializeRoute` con `query` reordenada rompe el round-trip byte-a-byte. | El round-trip se define **normalizado** (§4): identidad para URLs canónicas, idempotencia tras normalizar para las demás. `serialize` ordena las claves (determinista). `roundtrip_idempotente_no_canonica` lo fija. |

---

## 8. Fuera de scope (explícito)

- **`react-router` (o cualquier librería de routing).** `routes.ts` es código propio. Rechazado por el debate; ver §9.
- **CommandPalette profunda** (navegar la paleta a sub-tabs/entidades, no solo al primer nivel). La paleta hoy navega solo primer nivel (`App.tsx` `navigateTo`); hacerla consumir `routes.ts` para deep-linkear subestados es un **backlog** que este contrato habilita, pero NO se implementa acá.
- **`sort` y `total` de la tabla de Historial.** El endpoint de historial no expone hoy un `total` real ni orden configurable. **Backlog cruzado (nota):** el campo `total` "viaja gratis" cuando el plan del arnés veraz toque `backend/api/executions.py` (ahí es natural devolver el total); registrarlo como backlog de ESE plan, NO como fase de éste. El `sort` de columnas es otro backlog de UI aparte.
- **Persistencia de scroll.** Recordar la posición de scroll de una lista al volver a ella es otra mejora de UX; fuera de scope.
- **Cambiar `slash_commands.py` para emitir `/history?exec=`.** Opcional y NO requerido: F1/F3 hacen funcionar el `/?exec=` actual vía normalización. Si el operador quiere emitir directamente la forma canónica, es un one-liner de backlog (cambiar `/?exec=` por `/history?exec=` en `:116,138`), pero **no** es necesario y no se toca en este plan (evita tocar backend).
- **Cualquier cambio al plan del centro de notificaciones más allá de definir el contrato que consumirá.** Este plan entrega `routes.ts`; ese plan lo usa. No se implementa su campana ni su deep-link acá.
- **Rutas protegidas / roles / guards de permiso.** Mono-operador sin auth: nada de eso.
- **Tests de render (`render()`/RTL).** No hay `@testing-library/react` ni `jsdom` en `frontend/package.json`; todo test es de lógica pura + `tsc` + smoke manual.

---

## 9. Advertencias para el implementador (leer antes de tocar nada)

- **EXTENDER el router casero de `App.tsx`, JAMÁS meter `react-router`.** El debate lo evaluó y lo rechazó: recableado invasivo de las 16 páginas + la paleta + la nav del shell + su suite de tests, más re-render extra (degrada). `routes.ts` es un parser/serializer puro de código propio.
- **`pushState`/`replaceState` JAMÁS dentro de un updater de `setState`.** La app monta en `<React.StrictMode>` (`main.tsx`; anclar por texto) → en dev los updaters corren DOS veces → se duplicaría el historial (gotcha ya documentado en el comentario "Plan 136 F7" de `App.tsx`). Todo cambio de URL va en un `useEffect` dedicado (o en `navigateToRoute`, que es una función de evento, no un updater) con guard de `pathname+search`. F2 usa `replaceState` a propósito (filtrado de alta frecuencia, sin ensuciar el historial).
- **PROHIBIDO el patrón `useRef` congelado + props `initial*` a `useState` (C1).** La ruta vive como **ESTADO** de App (`useState<RouteState>`); las páginas reciben props VIVAS (`exec`/`subTab`) y se sincronizan con el patrón **`lastApplied` ref** (reaccionar SOLO a cambios de prop). Sin esto, los deep-links solo funcionan con F5 y el gate del 152 es letra muerta. Todo write-back de subestado (drawer, sub-tab) usa `replaceState` con guard `next !== target` (A2).
- **La precedencia de filtros al montar es LEY (C2):** URL con ≥1 clave de filtro → `DEFAULT + URL` completa (lo persistido se ignora); URL sin claves → `DEFAULT + persistido` (merge anti-drift, porque `useLocalStorageState` hace `JSON.parse` sin merge). Implementada SOLO vía `resolveMountFilters` de `routeFilters.ts` — no reinventarla inline.
- **RTL/jsdom NO están en `frontend/package.json`.** Prohibido `render()`/`renderHook`. Los tests son de **lógica pura**: `parseRoute`/`serializeRoute`, `historyFiltersToQuery`/`sysLogFiltersToQuery`, `isValidSubTab`. La apertura del drawer/subtab se verifica por **smoke manual** (documentado por fase). Si `isValidSubTab` o el array de sub-tabs se necesita en un test, conviene ponerlo en un `.ts` puro (no arrastrar JSX de `SettingsPage.tsx` al test).
- **vitest SIEMPRE por archivo** (`npx vitest run src/<archivo>`), NUNCA la suite completa: cross-file pollution conocida en este repo. Correr desde el checkout real `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` (el `node_modules` del worktree puede estar roto — junction conocida).
- **Query desconocida se PRESERVA, no se descarta** (§3.6). Hay receptores ortogonales vivos: `?flag=` (Settings), `?path=` (Docs), `?server=` (DevOps). `routes.ts` solo posee `tab`/`subtab`/`exec`; todo lo demás pasa verbatim. Romper esto rompe esos receptores.
- **El contrato de `exec` está partido HOY** (§2.1): backend emite `?exec=` en `/`, el receptor lee `?execution=` en `/history`. F1 canoniza `exec`, acepta `execution` como alias, y normaliza `/?exec=` → `/history?exec=`. NO borrar el emisor de `slash_commands.py` (KPI-5 verifica que sigue en 2).
- **No crear `.tsx` nuevos** (el uiDebtRatchet del plan de sistema de diseño da alcance CERO inline-styles a `.tsx` nuevos, y además no hace falta): `routes.ts` y `routeFilters.ts` son `.ts` puros. En los `.tsx` MODIFICADOS (App/Settings/ExecutionHistory/SystemLogs) **NO** introducir `style={{}}` nuevos.
- **`useLocalStorageState` ya existe y es tolerante a fallos** — NO reimplementarlo. Keys: `stacky.ui.history.filters` y `stacky.ui.syslogs.filters` (namespace `stacky.ui.*`, consistente con `ticketBoard.*` de `TicketBoard.tsx`).
- **Coordinar F1 con el plan del centro de notificaciones ANTES** de que ese plan se implemente (§3.12): su deep-link notificación→run debe consumir `serializeRoute({tab:"history", exec:id})`, no inventar un formato.
- **Sesión concurrente en el mismo árbol:** `git status -- "<ruta>"` antes de cada fase caliente; staging quirúrgico por path; el implementador NO commitea.
- **`offset` NO se persiste ni se serializa** (§3.7). En `SystemLogsPage` ya está aparte (dejarlo). En `ExecutionHistoryPage` está dentro de `Filters`: resetearlo a 0 al rehidratar (o separarlo a su propio `useState`).

---

## 10. Definition of Done (global)

- [ ] KPI-1..KPI-5 en verde con los comandos exactos de §1, cada test corrido por archivo desde el checkout real y su salida pegada en el resumen.
- [ ] `frontend/src/services/routes.ts` existe con `parseRoute`/`serializeRoute`/`tabFromSegments`/`TAB_PATHS`/`RouteState`; round-trip idempotente probado para todos los patrones; query desconocida preservada.
- [ ] El deep-link `/?exec=<id>` (forma de Slack) normaliza a `/history?exec=<id>` y **abre el drawer** de esa ejecución (smoke manual con un id real); el alias `?execution=` sigue funcionando; el emisor de `slash_commands.py` intacto (KPI-5=2).
- [ ] Los filtros de Historial (4) y de Logs del Sistema (8) sobreviven F5 y el cambio de tab (vía `useLocalStorageState`, keys `stacky.ui.history.*`/`stacky.ui.syslogs.*`); se reflejan en el querystring (sin `offset`); una URL filtrada reproduce la vista **vía el efecto de montaje con `resolveMountFilters` (C2: precedencia URL-gana-completa, testeada en `routeFilters.test.ts`), no solo por promesa**.
- [ ] Los 9 sub-tabs de Settings son direccionables por path (`/settings/<subtab>`); un subtab inválido cae a `flow`; el receptor `?flag=` sigue funcionando y su precedencia está documentada.
- [ ] `App.tsx` importa `routes.ts` (fuente única de `Tab`/`TAB_PATHS`/parseo); la ruta es **ESTADO** (`useState<RouteState>`, C1) y **`navigateToRoute` existe y es la única vía de navegación tipada (A1)**; `popstate` re-deriva TODO el estado (tab+subtab+exec) con las páginas montadas; ningún `pushState`/`replaceState` dentro de un updater de `setState`.
- [ ] Write-backs A2 verificados por smoke: abrir/cerrar el drawer por click refleja/quita `?exec=` en la barra; cambiar de sub-tab en Settings refleja `/settings/<sub>` (con `flow` sin segmento); Atrás/Adelante mueven sub-tab y drawer con la página YA montada (C1).
- [ ] `npx tsc --noEmit` verde; ningún `style={{}}` inline nuevo en los `.tsx` modificados; ningún `.tsx` nuevo creado.
- [ ] Sin flags nuevas, sin config nueva, backward-compatible: las URLs de primer nivel parsean idéntico; el contrato es aditivo. "Trabajo del operador: ninguno" se cumple.
- [ ] `react-router` NO fue agregado a `frontend/package.json` (`grep -i router frontend/package.json` → 0).
- [ ] F1+F3 marcados como GATE recomendado del plan del centro de notificaciones (152); la divergencia YA detectada (C3: su `nav {tab:"team"}` vía `selectTab`) tiene su reconciliación documentada en §3.12: `onActivityNavigate` → `navigateToRoute({tab:"history", exec})`.
- [ ] Pre-flight `git status` por archivo caliente hecho; sin WIP ajeno arrastrado; el implementador NO commiteó.
