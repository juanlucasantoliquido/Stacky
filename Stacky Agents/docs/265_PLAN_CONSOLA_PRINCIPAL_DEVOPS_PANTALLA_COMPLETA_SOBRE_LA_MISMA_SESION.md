# Plan 265 — La consola como experiencia principal: pantalla completa sobre la MISMA sesión, con contexto de repo, diffs y auditoría

**Estado:** PROPUESTO v1 (2026-07-27) · **Autor:** pipeline `proponer-plan-stacky` · **Juez:** pendiente (`criticar-y-mejorar-plan`)

---

## 1. Objetivo y KPI

`CodexConsoleDock` (`frontend/src/components/CodexConsoleDock.tsx`, 328 líneas) está montado
globalmente en `App.tsx:520` y es el canal único por el que ya entran el agente DevOps
(`components/devops/DevOpsAgentSection.tsx:5`), el doctor de secciones
(`components/devops/SectionDoctorButton.tsx:7`) y el documentador
(`components/docs/DocumenterButton.tsx:37`). El sustrato es bueno: SSE con reconexión exponencial y
ring-buffer (`hooks/useExecutionStream.ts:23-24`), estado que sobrevive al F5
(`store/workbench.ts:145-151`) y endpoint de cancelación ya construido
(`api/executions.py:603`, `services/claude_code_cli_runner.py:228`).

Lo que falta es que **sea una superficie de trabajo y no un cajón**:

| Falta hoy | Evidencia |
|---|---|
| Modo pantalla completa | El store sólo tiene 2 estados: `codexConsoleExecutionId` + `codexConsoleMinimized` (`workbench.ts:10-11`). No hay un tercero. |
| Markdown y bloques de código | El dock imprime líneas crudas (`CodexConsoleDock.tsx:242-260`). `ChatDrawer.tsx:10` sí usa `ReactMarkdown`, la consola no. |
| Copiar comando | No hay ningún botón de copia en el dock, pese a existir `services/copyService.ts` (Plan 194). |
| Cancelar / reintentar desde la consola | El endpoint existe (`api/executions.py:603`), el dock no lo llama. |
| Búsqueda en la conversación | Ninguna. |
| Historial de sesiones | `api/executions.py:442 /history` existe; la consola no lo consume. |
| Archivos modificados y diffs | `api/git.py` sólo expone `file-context` y `context-block`. **No hay endpoint de diff.** |
| Modelo/effort activos a la vista | El trace se persiste (`claude_code_cli_runner.py:543`), la consola no lo muestra. |
| Atajos de teclado propios | Existe el registro (`hooks/useShortcut.ts:15`, `components/ShortcutsCheatsheet.tsx`); la consola no registra ninguno. |

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Estados de presentación de la consola | **2** (normal, minimizada) | **3** (dock, pantalla completa, minimizada) |
| **KPI-2** Clicks para pasar de dock a pantalla completa y volver **sin perder la conversación** | imposible | **1** (y `lines.length` no cambia) |
| **KPI-3** Capacidades de la lista del operador presentes en la consola | **7 / 20** | **20 / 20** |
| **KPI-4** Acciones destructivas de la consola sin confirmación explícita | cancelar no existe; al agregarla sería 1 | **0** |
| **KPI-5** Endpoints nuevos que escriben algo | — | **0** (todo lo nuevo del backend es de solo lectura) |

Las 7 que ya están: streaming, estados de ejecución, logs en tiempo real, reconexión, persistencia tras
recargar, visualización de salidas, proyecto activo.

---

## 2. Por qué ahora / gap que cierra

Los planes 255-258 endurecieron lo que pasa **por dentro** de una corrida (fallas mudas, intake,
observabilidad, telemetría veraz). El Plan 200 le dio una consola **por incidencia**. Lo que nunca se
hizo es darle al operador **un lugar donde vivir mientras el agente trabaja**. Hoy, para seguir una
corrida, mira una tira de log de 300 px de alto encima del resto de la app.

Este plan **no construye una consola nueva**. Promueve la que ya existe: el mismo store, el mismo
stream SSE, el mismo `execution_id`. Todo lo que ya entra por `CodexConsoleDock` entra igual — el modo
pantalla completa es una **presentación** del mismo estado, no un componente paralelo. Esa es la
decisión de arquitectura central: **una sola sesión, dos presentaciones**. Un segundo componente con su
propio stream duplicaría eventos, rompería el ring-buffer y desincronizaría el scroll.

---

## 3. Principios y guardarraíles

1. **3 runtimes con paridad.** La consola es agnóstica: renderiza el stream SSE de una `AgentExecution`,
   que los 3 runtimes producen igual (`log_streamer.py`). Diferencias declaradas: el panel de
   modelo/effort muestra `effort_mode: "no_aplica"` en GitHub Copilot Pro (contrato del Plan 264) y el
   botón Cancelar sólo aparece si el runtime expone cancelación — `claude_code_cli_runner.py:228` la
   tiene; **verificá en implementación si `codex_cli_runner` la expone** y, si no, el botón se muestra
   deshabilitado con el hint *"Esta herramienta no admite cancelación; cerrá la corrida desde el
   sistema."* **Prohibido** un botón que no hace nada.
2. **Cero trabajo extra para el operador.** El dock sigue siendo el default. La pantalla completa es un
   click (o un atajo). Nada obliga a migrar. Las 4 flags nacen **ON** — ninguna cae en (A) ni (B).
3. **Human-in-the-loop.** La consola **no ejecuta nada por su cuenta**. Cancelar pide confirmación.
   No hay auto-reintento: reintentar es un click humano.
4. **Mono-operador sin auth.** "Permisos y auditoría" se implementa como **bitácora local de acciones
   de consola**, no como RBAC. Se registra qué hizo el operador y cuándo; no se restringe a nadie.
5. **Backward-compatible.** `codexConsoleMinimized` **se conserva** en el store: un estado persistido de
   una sesión anterior (o de un deploy viejo) rehidrata sin romper. El campo nuevo es opcional.
6. **No degradar.** El ring-buffer acotado de `useExecutionStream` (`hooks/logRingBuffer.ts`) **no se
   toca**: la pantalla completa muestra las mismas líneas acotadas, no un buffer ilimitado. Sin
   `setInterval` ni `refetchInterval` nuevos — la consola es push (SSE), no polling.
7. **Reusar, no reinventar.** `react-markdown@9` + `rehype-highlight@7` + `highlight.js@11` ya están en
   `frontend/package.json:14,19,20` ⇒ **cero dependencias nuevas**. `services/copyService.ts` (Plan
   194), `hooks/useShortcut.ts` (Plan 172), `components/ui/ConfirmDialog.tsx` (Plan 164),
   `components/ModelDecisionChip.tsx` (Plan 212).

---

## 4. Glosario

| Término | Significado |
|---|---|
| **dock** | La presentación actual: barra baja, ~300 px, sobre el resto de la app. |
| **modo principal / pantalla completa** | Presentación nueva: la consola ocupa toda el área útil, con paneles laterales plegables. **Mismo estado, misma sesión.** |
| **presentación** | `"dock" \| "full" \| "minimized"`. Sustituye al booleano `codexConsoleMinimized`. |
| **sesión de consola** | Un `execution_id` con su stream. Sobrevive al F5 vía `workbench.ts:145-151`. |
| **ring-buffer** | Cota de líneas de `useExecutionStream`; descarta las más viejas y reporta `dropped`. |
| **bitácora de consola** | Registro local append-only de las acciones que el operador dispara desde la consola. |
| **panel lateral** | Columna plegable del modo principal: Contexto, Repositorio o Historial. |

---

## 5. Fases

### F0 — Flags (patrón triple)

**Archivos a editar (2):** `backend/config.py` y `backend/services/harness_flags.py`.

```python
    # Plan 265 — la consola como experiencia principal.
    STACKY_CONSOLE_FULLSCREEN_ENABLED: bool = os.getenv(
        "STACKY_CONSOLE_FULLSCREEN_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_CONSOLE_RICH_RENDER_ENABLED: bool = os.getenv(
        "STACKY_CONSOLE_RICH_RENDER_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_CONSOLE_REPO_PANEL_ENABLED: bool = os.getenv(
        "STACKY_CONSOLE_REPO_PANEL_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    STACKY_CONSOLE_AUDIT_LOG_ENABLED: bool = os.getenv(
        "STACKY_CONSOLE_AUDIT_LOG_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
```

Y en `Stacky Agents/backend/services/harness_flags.py`, los 4 `FlagSpec` **completos** (escribilos tal
cual; no los resumas), agregados después del último bloque de FlagSpec del archivo:

```python
    # ── Plan 265 — la consola como experiencia principal ──
    FlagSpec(
        key="STACKY_CONSOLE_FULLSCREEN_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Consola en pantalla completa",
        description=(
            "Plan 265 — La consola de corridas puede ocupar toda la pantalla util, "
            "con paneles laterales, busqueda y atajos, sobre la MISMA sesion que el "
            "dock. Presentacion de UI: no cambia como corre nada."
        ),
        group="global",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_RICH_RENDER_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Markdown y bloques de codigo en la consola",
        description=(
            "Plan 265 — En pantalla completa, la salida se renderiza con markdown y "
            "resaltado de sintaxis, con boton de copia por bloque. El dock sigue "
            "mostrando lineas crudas. Sin dependencias nuevas."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_REPO_PANEL_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Panel de repositorio en la consola",
        description=(
            "Plan 265 — Muestra archivos modificados y su diff con git status y git "
            "diff de SOLO LECTURA sobre el workspace de la corrida. Sin .git, sin git "
            "instalado o si expira el timeout, el panel lo dice y no rompe nada."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_AUDIT_LOG_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON.
        label="Bitacora de acciones de la consola",
        description=(
            "Plan 265 — Registra que acciones disparo el operador desde la consola "
            "(cancelar, reintentar, copiar) en el directorio de datos de Stacky. Es "
            "registro, no restriccion: mono-operador, sin RBAC."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
```

Y las **4** keys agregadas a la tupla `_CURATED_DEFAULTS_ON` (las 4 nacen ON):

```python
        "STACKY_CONSOLE_FULLSCREEN_ENABLED",    # Plan 265
        "STACKY_CONSOLE_RICH_RENDER_ENABLED",   # Plan 265
        "STACKY_CONSOLE_REPO_PANEL_ENABLED",    # Plan 265
        "STACKY_CONSOLE_AUDIT_LOG_ENABLED",     # Plan 265
```

**Por qué las 4 nacen ON:** ninguna enciende loop, daemon, barrido, polling ni prefetch (la consola es
push por SSE) ⇒ no hay **(A)**. Ninguna escribe en ADO/GitLab/repo remoto/BD del operador, ni
despliega, ni borra, ni decide por él ⇒ no hay **(B)**. El panel de repositorio es
**`git status` + `git diff` de SOLO LECTURA**, y la regla es explícita: *leer un archivo local,
calcular, mostrar, diffear o auditar nunca es excepción*. La bitácora escribe sólo en el directorio de
datos del propio Stacky.

**Tests:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
```
**Criterio binario.** Ambos exit 0. **Trabajo del operador: ninguno.**

---

### F1 — Store: la tercera presentación, sin perder la sesión (TDD, lógica pura)

**Objetivo.** KPI-1 y KPI-2: un tercer estado, persistido, sin tocar el `execution_id`.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consolePresentation.ts` — **lógica pura, sin
React** (el repo **no tiene RTL ni jsdom**, así que toda la lógica testeable vive en `.ts` puro).

```ts
export type ConsolePresentation = "dock" | "full" | "minimized";

export const DEFAULT_PRESENTATION: ConsolePresentation = "dock";

/** Normaliza cualquier valor rehidratado (o de un deploy viejo) a una presentación válida. */
export function normalizePresentation(raw: unknown): ConsolePresentation;

/** Migración del booleano viejo. `codexConsoleMinimized === true` -> "minimized", si no "dock". */
export function presentationFromLegacy(minimized: boolean | undefined): ConsolePresentation;

/** El booleano que hay que seguir escribiendo para no romper deploys viejos. */
export function legacyMinimizedFrom(p: ConsolePresentation): boolean;

/** Alterna dock <-> full. Desde "minimized" va a "dock" (un paso a la vez, sin saltos). */
export function togglePresentation(current: ConsolePresentation): ConsolePresentation;

/** ¿Se muestra el chrome de la app (nav, topbar) con esta presentación? */
export function hidesAppChrome(p: ConsolePresentation): boolean;   // true sólo en "full"
```

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consolePresentation.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `normalizePresentation("full")` | `"full"` |
| 2 | `normalizePresentation("basura")` / `undefined` / `null` / `42` | `"dock"` (nunca lanza) |
| 3 | `presentationFromLegacy(true)` | `"minimized"` |
| 4 | `presentationFromLegacy(false)` / `presentationFromLegacy(undefined)` | `"dock"` |
| 5 | `legacyMinimizedFrom("minimized")` | `true` |
| 6 | `legacyMinimizedFrom("full")` y `("dock")` | `false` (un deploy viejo la ve abierta, no rota) |
| 7 | `togglePresentation("dock")` | `"full"` |
| 8 | `togglePresentation("full")` | `"dock"` |
| 9 | `togglePresentation("minimized")` | `"dock"` |
| 10 | `hidesAppChrome` | `true` sólo para `"full"` |
| 11 | round-trip `legacyMinimizedFrom(presentationFromLegacy(x)) === x` para `true`/`false` | se cumple |

**Cambios en el store** (`Stacky Agents/frontend/src/store/workbench.ts`):

```diff
   codexConsoleExecutionId: number | null;
   codexConsoleMinimized: boolean;
+  /** Plan 265 — presentación de la consola. `codexConsoleMinimized` se conserva
+      y se sigue escribiendo, para que un deploy viejo rehidrate sin romper. */
+  codexConsolePresentation: ConsolePresentation;
```
```diff
   setCodexConsoleMinimized: (value: boolean) => void;
+  setCodexConsolePresentation: (p: ConsolePresentation) => void;
```
```diff
   setCodexConsolePresentation: (p) =>
     set({
       codexConsolePresentation: p,
       codexConsoleMinimized: legacyMinimizedFrom(p),   // los dos SIEMPRE en sync
     }),
```
y en el bloque `partialize` de persistencia (`workbench.ts:145-151`), agregar
`codexConsolePresentation: state.codexConsolePresentation,`. **`codexConsoleExecutionId` no se toca:
ahí vive la sesión, y es justamente lo que no se puede perder.**

> **Regla de oro de esta fase:** cambiar de presentación **NO** puede tocar
> `codexConsoleExecutionId`. Si lo tocás, el `useExecutionStream` se re-suscribe, el ring-buffer se
> vacía y el operador pierde la conversación. Eso es exactamente lo que KPI-2 mide.

Y en la rehidratación (el `onRehydrateStorage` o equivalente; **leé cómo lo hace hoy el archivo**):
si `codexConsolePresentation` no viene (estado viejo), derivarla con
`presentationFromLegacy(state.codexConsoleMinimized)`.

**Comando de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consolePresentation.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 11 passed, `tsc` exit 0.

**Smoke manual obligatorio (KPI-2, no automatizable sin RTL):** lanzar una corrida, esperar ≥ 20 líneas,
pasar a pantalla completa, volver a dock, y verificar que **el contador de líneas es el mismo** (la
consola muestra `dropped` y el total; anotá ambos números antes y después).

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Impacto por runtime:** ninguno (estado de UI).
**Trabajo del operador: ninguno** (el dock sigue siendo el default).

---

### F2 — Render rico: markdown, bloques de código y copia de comandos

**Objetivo.** Que la salida sea legible y accionable, sin dependencias nuevas.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consoleRender.ts` — **lógica pura**:

```ts
export interface RenderedChunk {
  kind: "text" | "code" | "command";
  lang: string | null;      // del fence ```lang
  content: string;
  copyable: boolean;        // true para "code" y "command"
}

/** Agrupa líneas consecutivas del stream en bloques renderizables.
 *  Detecta fences ``` abiertos/cerrados. Un fence sin cerrar al final del
 *  stream se emite igual como "code" (la corrida sigue viva). Nunca lanza. */
export function groupLinesIntoChunks(lines: LogLine[]): RenderedChunk[];

/** ¿Este bloque es un comando de shell copiable? Heurística conservadora:
 *  lang ∈ {"bash","sh","powershell","ps1","cmd"} O una sola línea que empieza
 *  con un prefijo conocido (git, npm, npx, python, pytest, dotnet, docker). */
export function isCommandChunk(chunk: RenderedChunk): boolean;
```

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consoleRender.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | líneas sin fences | 1 chunk `"text"` |
| 2 | fence ```` ```bash ```` cerrado | 3 chunks: text, code(lang=`"bash"`), text |
| 3 | fence sin cerrar al final | último chunk es `"code"`, no se traga el contenido |
| 4 | `[]` | `[]`, no lanza |
| 5 | fence vacío | chunk `"code"` con `content === ""` |
| 6 | `isCommandChunk` con `lang: "powershell"` | `true` |
| 7 | `isCommandChunk` con `content: "git status"`, `lang: null` | `true` |
| 8 | `isCommandChunk` con prosa de 3 líneas | `false` |
| 9 | 5000 líneas | termina en < 100 ms (cota de performance, `performance.now()`) |

**Componente.** En el modo pantalla completa, renderizar los chunks con `ReactMarkdown` +
`rehype-highlight` (mismo patrón que `ChatDrawer.tsx:10`) y, en cada chunk `copyable`, un botón de
copia que llama a **`services/copyService.ts`** (Plan 194) — **no** `navigator.clipboard` directo.

> **El dock NO cambia.** El render rico es sólo del modo `"full"`: el dock sigue mostrando líneas
> crudas, que es lo correcto para 300 px de alto y evita re-renders caros en la barra siempre visible.
> Si `STACKY_CONSOLE_RICH_RENDER_ENABLED` está OFF, el modo full también muestra líneas crudas.

**Comando de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRender.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 9 passed. Y `grep -c "navigator.clipboard" src/components/Console*.tsx` ⇒ **0**.

**Flag:** `STACKY_CONSOLE_RICH_RENDER_ENABLED` (ON).
**Impacto por runtime:** igual en los 3 (renderiza texto del stream).
**Trabajo del operador: ninguno.**

---

### F3 — Cancelar y reintentar, con confirmación (KPI-4)

**Objetivo.** Cerrar el lazo de control sin agregar un solo endpoint nuevo.

**Sin backend nuevo.** Se usa `POST /api/executions/<id>/cancel` (`api/executions.py:603`).
Para reintentar se usa el endpoint de lanzamiento que corresponda al origen de la corrida — **leé el
`metadata_dict` de la ejecución para saber cuál** (`agent_type`, `runtime`, `vscode_agent_filename`).
Si no se puede determinar el origen, el botón "Reintentar" queda **deshabilitado** con el hint
*"No se puede reintentar: esta corrida no registra su origen."* — nunca adivines un endpoint.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consoleActions.ts` — **lógica pura**:

```ts
export type ConsoleActionId = "cancel" | "retry" | "copyAll" | "close";

export interface ExecutionSnapshot {
  status: string | null;          // "running" | "completed" | "error" | "cancelled" | ...
  runtimeSupportsCancel: boolean;
  hasOrigin: boolean;
}

/** Qué acciones se ofrecen y cuáles quedan deshabilitadas (con motivo). Nunca lanza. */
export function availableActions(snap: ExecutionSnapshot):
  Array<{ id: ConsoleActionId; enabled: boolean; reason: string | null }>;

/** ¿Esta acción exige confirmación explícita antes de ejecutarse? */
export function requiresConfirmation(id: ConsoleActionId): boolean;   // true SÓLO para "cancel"

/** Texto exacto del diálogo de confirmación. */
export function confirmationText(id: ConsoleActionId, executionId: number): string;
```

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consoleActions.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `status: "running"`, soporta cancel | `cancel` presente y `enabled` |
| 2 | `status: "completed"` | `cancel` presente pero `enabled: false`, `reason` no nulo |
| 3 | `runtimeSupportsCancel: false` | `cancel` `enabled: false` con motivo que nombra la herramienta |
| 4 | `hasOrigin: false` | `retry` `enabled: false` con motivo |
| 5 | `status: null` (deploy viejo / snapshot incompleto) | no lanza; nada queda habilitado por accidente |
| 6 | `requiresConfirmation("cancel")` | `true` |
| 7 | `requiresConfirmation("retry" \| "copyAll" \| "close")` | `false` |
| 8 | `confirmationText("cancel", 42)` | contiene `"42"` y la palabra `"cancelar"` |

**Cableado.** El botón Cancelar abre el **`ConfirmDialog` canónico** (`components/ui/ConfirmDialog.tsx`,
Plan 164) — **no** `window.confirm`. Al confirmar, `POST .../cancel`.

> **Gotcha del repo:** para llamar al endpoint usá el helper **crudo** (`rawPost`) y no `api.post`: el
> wrapper `api.*` **lanza excepción ante cualquier non-2xx**, así que un 409 (la corrida ya terminó)
> tumbaría el componente en vez de mostrar el mensaje. Confirmá el nombre con
> `grep -n "rawPost\|rawGet" "Stacky Agents/frontend/src/api/endpoints.ts"`.

**Comando de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleActions.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 8 passed. Y `requiresConfirmation` devuelve `true` para **toda** acción
destructiva ⇒ KPI-4 = 0.

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Impacto por runtime:** Claude cancela de verdad (`claude_code_cli_runner.py:228`); Codex y Copilot,
si no exponen cancelación, muestran el botón deshabilitado con el motivo. **Verificalo en el código
antes de habilitarlo.**
**Trabajo del operador: ninguno.**

---

### F4 — Panel de Repositorio: archivos modificados y diff (SOLO LECTURA)

**Objetivo.** Ver qué tocó el agente sin salir de la consola.

**Archivo a editar (backend):** `Stacky Agents/backend/api/git.py` — dos endpoints **de solo lectura**:

```python
@bp.get("/status")           # /api/git/status?workspace=<ruta>
def git_status_route():
    """git status --porcelain=v1 sobre el workspace de la corrida.
    Devuelve {"ok": bool, "available": bool, "files": [{"path","status"}], "reason": str|None}.
    - `available: False` + `reason` si no hay .git, si git no está instalado, o si expira el timeout.
    - Timeout DURO de 5 s (mismo criterio que services/plans_board.py:644 _GIT_TIMEOUT_SEC).
    - `workspace` se valida contra los workspaces conocidos por project_manager:
      una ruta arbitraria se RECHAZA con 400. Nunca ejecuta git en un path del cliente.
    NUNCA lanza. NUNCA escribe."""


@bp.get("/diff")             # /api/git/diff?workspace=<ruta>&path=<archivo>
def git_diff_route():
    """git diff -- <archivo> (unified). Devuelve {"ok","available","diff","truncated","reason"}.
    - Cota DURA: 200 KB de diff; más allá se trunca y `truncated: True`.
    - `path` se valida: debe ser relativo, sin `..`, y resolver DENTRO del workspace.
    - Comando fijo, argumentos por lista (NUNCA shell=True, NUNCA interpolación de strings).
    NUNCA lanza. NUNCA escribe."""
```

> **Restricción dura de seguridad, no negociable:** los dos endpoints construyen el comando como
> **lista de argumentos** (`["git", "status", "--porcelain=v1"]`), con `shell=False`, `cwd` validado y
> `timeout=5`. Cero interpolación de strings del usuario en el comando. Es el mismo patrón que ya usa
> `services/plans_board.py:665-681`, copialo de ahí.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan265_git_readonly.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `workspace` no registrado en `project_manager` | HTTP 400, y **git no se ejecutó** (monkeypatch de `subprocess.run` que cuenta llamadas ⇒ 0) |
| 2 | `path` con `..` | HTTP 400, git no se ejecutó |
| 3 | `path` absoluto | HTTP 400 |
| 4 | workspace sin `.git` | 200 con `available: False` y `reason` no vacío |
| 5 | git no instalado (`FileNotFoundError` mockeado) | 200 con `available: False`, no 500 |
| 6 | `TimeoutExpired` mockeado | 200 con `available: False`, `reason` menciona el timeout |
| 7 | `git status` con salida mockeada de 3 archivos | `len(files) == 3` y cada uno tiene `path` y `status` |
| 8 | diff > 200 KB | `truncated is True` y `len(diff) <= 200*1024` |
| 9 | El comando pasado a `subprocess.run` | es una **lista**, y `kwargs.get("shell")` es falsy |
| 10 | Flag `STACKY_CONSOLE_REPO_PANEL_ENABLED = False` | envelope de deshabilitado; git no se ejecutó |
| 11 | Barrido de escritura | ningún subcomando de git peligroso aparece en el módulo: el test grepea el propio `api/git.py` y falla si encuentra `commit`, `push`, `checkout`, `reset`, `clean` o `stash` |

> **Test 11 — hacelo por lista de subcomandos, leyendo el archivo.** Es el guardián de KPI-5: garantiza
> que este plan no introdujo ninguna escritura a git. Si alguna vez hace falta un subcomando nuevo,
> que el test obligue a discutirlo.

**Frontend.** Panel lateral "Repositorio" en modo `"full"`: lista de archivos modificados; al hacer
click, el diff con `ReactMarkdown` + `rehype-highlight` en un fence `diff`. **Reusá el patrón visual de
`components/dbcompare/DiffList.tsx`** si su API sirve; si no, un componente propio simple. **No**
agregues una librería de diff.

**Lógica pura testeable:** `Stacky Agents/frontend/src/services/consoleRepoPanel.ts` con
`groupFilesByStatus(files)` (agrupa en modificados / nuevos / borrados / sin seguimiento) y
`shortPath(path, max)` (elide el medio de una ruta larga). Test:
`src/services/__tests__/consoleRepoPanel.test.ts`, 6 casos incluyendo entrada vacía y `status`
desconocido (que debe caer en un grupo "otros", nunca perderse).

**Comandos de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan265_git_readonly.py" -q
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRepoPanel.test.ts
```
(registrar `tests/test_plan265_git_readonly.py` en **ambas** `HARNESS_TEST_FILES`).

**Criterio binario.** 11 + 6 passed. Test 11 en verde ⇒ **KPI-5 = 0 endpoints de escritura**.

**Flag:** `STACKY_CONSOLE_REPO_PANEL_ENABLED` (**ON** — es solo lectura; la regla dice explícitamente
que diffear y mostrar nunca es excepción).
**Impacto por runtime:** idéntico (lee el workspace, no la herramienta). Sin `.git` degrada a
`available: False` con el motivo a la vista.
**Trabajo del operador: ninguno.**

---

### F5 — Paneles de Contexto e Historial + búsqueda en la conversación

**Objetivo.** Cubrir las capacidades que faltan sin endpoints nuevos.

**(a) Panel "Contexto"** — todo de datos que ya existen:
- proyecto y entorno activos: `store/workbench` + `api/projects`;
- herramienta / modelo / effort activos: `metadata_dict["model_effort"]` (Plan 264 F4), renderizado con
  `formatModelEffortTrace` (Plan 264 F6) y `ModelDecisionChip`;
- estado de ejecución y duración: de `GET /api/executions/<id>`;
- líneas descartadas por el ring-buffer: el `dropped` que `useExecutionStream` ya expone
  (`hooks/useExecutionStream.ts:14`) — mostrarlo es honestidad, no adorno.

> **Dependencia declarada:** el bloque de herramienta/modelo/effort necesita el trace de los 3 runtimes
> que construye el **Plan 264 F4**. Si el 261 no está implementado, esta parte muestra sólo lo que hay
> para Claude y **lo dice** (`"—"`), no inventa. Es degradación explícita, no bloqueo.

**(b) Panel "Historial"** — consume `GET /api/executions/history` (`api/executions.py:442`), ya
existente. Click en una corrida ⇒ `setCodexConsoleExecution(id)`. **Sin polling nuevo.**

**(c) Búsqueda en la conversación** — puramente cliente, sobre las líneas ya en memoria.
`Stacky Agents/frontend/src/services/consoleSearch.ts`:

```ts
export interface SearchHit { lineIndex: number; start: number; end: number; }

/** Busca `query` en las líneas. Case-insensitive. `query` vacío -> []. Nunca lanza.
 *  `query` se trata como TEXTO LITERAL, no como regex (una regex inválida del
 *  operador no puede romper la consola, y `.*` no puede colgarla). */
export function searchLines(lines: LogLine[], query: string): SearchHit[];

/** Índice del hit siguiente/anterior, con wrap-around. Lista vacía -> null. */
export function nextHit(hits: SearchHit[], current: number | null): number | null;
export function prevHit(hits: SearchHit[], current: number | null): number | null;
```

Test `src/services/__tests__/consoleSearch.test.ts`, 8 casos: query vacía, sin hits, múltiples hits en
una línea, case-insensitive, caracteres de regex (`.*`, `[`, `(`) tratados como literales, wrap-around
de `nextHit`/`prevHit`, `current: null`, y 5000 líneas en < 100 ms.

**Comandos de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleSearch.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 8 passed, `tsc` exit 0, y **cero** `setInterval`/`refetchInterval` nuevos:
```bash
grep -rcE "setInterval|refetchInterval" "Stacky Agents/frontend/src/components/CodexConsoleDock.tsx" "Stacky Agents/frontend/src/services/console*.ts"
```
⇒ **0** en todos.

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Impacto por runtime:** igual en los 3.
**Trabajo del operador: ninguno.**

---

### F6 — Atajos de teclado, registrados en el cheatsheet existente

**Objetivo.** Que la consola sea usable sin mouse, y que sus atajos **aparezcan en la ayuda que ya
existe** (`components/ShortcutsCheatsheet.tsx`, Plan 172).

**Atajos a registrar** (con `hooks/useShortcut.ts:15`, **no** con `addEventListener` propio):

| Atajo | Acción | Alcance |
|---|---|---|
| `Ctrl+\`` | Alternar dock ↔ pantalla completa | global |
| `Esc` | De `"full"` a `"dock"` | sólo con la consola en `"full"` **y** sin diálogo abierto |
| `Ctrl+F` | Foco en la búsqueda de la conversación | sólo con la consola en `"full"` |
| `Enter` / `Shift+Enter` | Siguiente / anterior resultado | sólo con foco en la búsqueda |
| `Ctrl+Shift+C` | Copiar toda la conversación | sólo con la consola visible |

> **Colisiones — verificalas antes de registrar.** Corré
> `grep -rn "useShortcut(" "Stacky Agents/frontend/src" | head -40` y revisá el registro central. Si
> alguno ya está tomado, **elegí otro y anotalo**; no lo pises. `Esc` en particular ya lo usa el
> `Dialog` canónico (`components/ui/dialogKeyboard.ts`): por eso el atajo de consola sólo actúa
> **si no hay diálogo abierto** — el diálogo tiene prioridad.

**Test:** `Stacky Agents/frontend/src/services/__tests__/consoleShortcuts.test.ts` sobre un mapa puro
`CONSOLE_SHORTCUTS` exportado desde `services/consoleShortcuts.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `CONSOLE_SHORTCUTS` | cada entrada tiene `keys`, `label` (español) y `scope` |
| 2 | sin duplicados | `keys` únicas dentro del mapa |
| 3 | `shouldHandleEscape({presentation:"full", dialogOpen:false})` | `true` |
| 4 | `shouldHandleEscape({presentation:"full", dialogOpen:true})` | `false` (el diálogo gana) |
| 5 | `shouldHandleEscape({presentation:"dock", dialogOpen:false})` | `false` |

**Comando:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleShortcuts.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/shortcuts.test.ts
```
**Criterio binario.** 5 passed + el test de atajos existente **sigue verde** (regresión del Plan 172).

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Trabajo del operador: ninguno** (los atajos se documentan solos en el cheatsheet).

---

### F7 — Bitácora de acciones de consola (auditoría local)

**Objetivo.** Cubrir "permisos, seguridad y auditoría" como corresponde a un sistema **mono-operador**:
**registrar**, no restringir.

**Archivo a crear:** `Stacky Agents/backend/services/console_audit.py`.

```python
def record_console_action(*, execution_id: int, action: str, detail: dict | None = None) -> bool:
    """Append-only al archivo de bitácora en el directorio de datos de Stacky.

    - Ruta vía runtime_paths.data_dir() (NUNCA __file__): válida en dev y en el
      deploy congelado PyInstaller.
    - Una línea JSON por acción: {"ts","execution_id","action","detail"}.
    - `action` se valida contra una allowlist: {"cancel","retry","copy_all","open_full","close"}.
      Un valor fuera de la lista se descarta y devuelve False (no se escribe basura).
    - Rotación: si el archivo supera 5 MB, se renombra a .1 y se empieza de nuevo
      (máximo 2 archivos). Nada crece sin techo.
    - Devuelve False (sin lanzar) ante cualquier error de I/O o con la flag OFF.
      La auditoría NUNCA puede romper una acción del operador.
    """

def read_console_audit(limit: int = 200) -> list[dict]:
    """Últimas N entradas, más nuevas primero. [] ante cualquier problema."""
```

Endpoint de lectura: `GET /api/executions/console-audit?limit=N` en `api/executions.py`.
La escritura se dispara desde los handlers de cancel/retry ya existentes; **no** se expone un endpoint
de escritura de bitácora (KPI-5).

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan265_console_audit.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `record` + `read` round-trip | la entrada aparece con `action` y `execution_id` |
| 2 | `action` fuera de la allowlist | `False`, nada escrito |
| 3 | Directorio no escribible (mock `OSError`) | `False`, **no lanza** |
| 4 | Rotación a los 5 MB | existe el `.1` y el principal arranca de cero |
| 5 | Flag `STACKY_CONSOLE_AUDIT_LOG_ENABLED = False` | `record` devuelve `False`, `read` devuelve `[]` |
| 6 | `read_console_audit` con una línea corrupta (JSON inválido) en el medio | las demás se devuelven; no lanza |
| 7 | `detail` con un valor no serializable | se descarta ese campo, la entrada se escribe igual |
| 8 | Aislamiento | el test usa `tmp_path` y verifica que el archivo **real** de datos no se creó ni cambió |

> **Test 8 es obligatorio.** La memoria del repo registra que un test del Plan 216 podía escribir en el
> **perfil REAL** del operador. Monkeypatcheá `runtime_paths.data_dir` y asertá sobre el path real.

**Comando:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan265_console_audit.py" -q
```
(registrar en ambas `HARNESS_TEST_FILES`).

**Criterio binario.** 8 passed.

**Flag:** `STACKY_CONSOLE_AUDIT_LOG_ENABLED` (**ON** — escribe sólo en el directorio de datos del propio
Stacky, no en un sistema del operador; es registro, no acción).
**Impacto por runtime:** idéntico (registra acciones del operador, no de la herramienta).
**Trabajo del operador: ninguno.**

---

### F8 — Cierre y verificación consolidada

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_plan265_git_readonly.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan265_console_audit.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
& $py -m compileall -q "Stacky Agents\backend\api" "Stacky Agents\backend\services"
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consolePresentation.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRender.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleActions.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRepoPanel.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleSearch.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleShortcuts.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/shortcuts.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Smoke manual obligatorio (no automatizable — el repo no tiene RTL ni jsdom).** Anotá cada resultado
en el registro de implementación:

1. Lanzar una corrida real; esperar ≥ 20 líneas.
2. `Ctrl+\`` ⇒ pantalla completa. **Contar las líneas: mismo número.** Volver a dock: mismo número. (KPI-2)
3. F5 con la consola en pantalla completa ⇒ rehidrata en pantalla completa, misma corrida.
4. Buscar una palabra que aparezca 3 veces ⇒ 3 hits, `Enter` cicla con wrap-around.
5. Panel Repositorio ⇒ archivos modificados; abrir un diff.
6. Cancelar ⇒ aparece el `ConfirmDialog`; confirmar ⇒ la corrida pasa a cancelada.
7. `GET /api/executions/console-audit` ⇒ la acción `cancel` está registrada.
8. Apagar `STACKY_CONSOLE_FULLSCREEN_ENABLED` ⇒ el dock sigue funcionando **exactamente** como antes.

**Criterio binario.** 14 comandos exit 0 + los 8 pasos del smoke con resultado esperado.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| **R1** | Cambiar de presentación re-suscribe el SSE y **borra la conversación**. | **Alta** (es el fallo natural) | `codexConsoleExecutionId` **no se toca** al cambiar de presentación; el `useExecutionStream` vive en un componente que no se desmonta. El paso 2 del smoke es el gate. Si el contador de líneas cambia, la fase **no está hecha**. |
| **R2** | Renderizar markdown de un stream vivo re-renderiza todo en cada línea y la consola se traba. | **Alta** | El render rico es **sólo** del modo `"full"` (el dock queda crudo). `groupLinesIntoChunks` memoizado por longitud del array. Test 9 de F2 pone la cota de 100 ms sobre 5000 líneas. Si en el smoke se siente lento, la salida es rendear crudo el último chunk (el que está creciendo) y rico los cerrados. |
| **R3** | El endpoint de git ejecuta un comando en una ruta arbitraria (inyección / path traversal). | Media | Validación de `workspace` contra `project_manager`, `path` relativo sin `..` resuelto dentro del workspace, comando por **lista**, `shell=False`, timeout 5 s. Tests 1, 2, 3 y 9 de F4 lo cubren, y el test 1 verifica que git **no se ejecutó**. |
| **R4** | El panel de repo cuelga la UI en un repo grande. | Media | Timeout duro de 5 s, cota de 200 KB de diff, `truncated` visible. Sin `.git` degrada a `available: False`. |
| **R5** | Los atajos nuevos pisan atajos existentes (Plan 172) o el `Esc` del `Dialog` (Plan 164). | **Alta** | Verificación de colisiones obligatoria **antes** de registrar; `Esc` de consola sólo actúa con `dialogOpen === false` (test 4 de F6); `src/services/shortcuts.test.ts` corre como regresión. |
| **R6** | La bitácora crece sin techo o rompe una acción del operador. | Media | Rotación a 5 MB con máximo 2 archivos; `record_console_action` **nunca lanza** y devuelve `False` ante cualquier error. |
| **R7** | El panel de Contexto depende del Plan 264 (trace en los 3 runtimes) y ese plan no está implementado. | **Alta** | Degradación explícita: muestra lo que hay y `"—"` en lo que falta. **No bloquea** este plan. Declarado en F5(a). |
| **R8** | Ocultar el chrome de la app en `"full"` deja al operador sin salida si un atajo falla. | Media | Siempre hay un botón visible de "Volver al dock" en el header de la consola, además del atajo. Nunca sólo teclado. |
| **R9** | `style={{` o literales hex nuevos ponen los ratchets de UI en rojo. | **Alta** (la consola es una pantalla nueva grande) | La consola nueva nace con **alcance 0** en el ratchet de inline styles: **cero `style={{`** — para lo dinámico usá `ref` + efecto o variables CSS, nunca `style={{}}`. Cero literales hex: sólo tokens de `theme.css`. El ratchet corre en F8. |
| **R10** | Espaciados hardcodeados hacen la consola sorda a la densidad. | Media | Todo el CSS nuevo usa `var(--space-N)` (Plan 150). Grep de verificación igual al del Plan 263 F5, sobre el `.module.css` nuevo ⇒ **0** hardcodeados. |

---

## 7. Fuera de scope

- **No** se crea un componente de consola paralelo: es una presentación del mismo `CodexConsoleDock`.
- **No** se toca el ring-buffer ni sus cotas.
- **No** se agregan dependencias npm (markdown y highlight ya están instalados).
- **No** se implementa RBAC ni permisos por usuario: la auditoría es bitácora, no restricción.
- **No** se agrega ningún endpoint que escriba en git, ADO, GitLab o una BD del operador.
- **No** se implementa auto-reintento: reintentar es siempre un click humano.
- **No** se reemplaza `ChatDrawer` (es otro flujo: chat libre con un agente, no seguimiento de corrida).
- **No** se agrega polling: la consola es push por SSE.

---

## 8. Orden de implementación y DoD

**Orden (estricto):**

1. **F0** — flags.
2. **F1** — store + presentación (**gate duro**: si el smoke de KPI-2 falla, no sigas).
3. **F2** — render rico (independiente de F3-F7).
4. **F3** — cancelar/reintentar con confirmación.
5. **F4** — panel de repositorio (backend + frontend).
6. **F5** — contexto, historial y búsqueda.
7. **F6** — atajos (después de F5, porque `Ctrl+F` necesita la búsqueda).
8. **F7** — bitácora.
9. **F8** — cierre.

**Definición de Hecho (DoD):**

- [ ] Los 14 comandos de F8 salen **exit 0**, cero rojos.
- [ ] Los 8 pasos del smoke manual ejecutados y **anotados con su resultado real**.
- [ ] **KPI-1**: `normalizePresentation` cubre los 3 estados; test verde.
- [ ] **KPI-2**: el conteo de líneas es **idéntico** antes y después de alternar presentación (anotado).
- [ ] **KPI-3**: las 20 capacidades de la lista tienen su fase; las que degradan
      (cancelación por runtime, trace sin Plan 264) lo declaran en la UI con un motivo visible.
- [ ] **KPI-4**: `requiresConfirmation("cancel") === true` y el `ConfirmDialog` canónico se abre de
      verdad (paso 6 del smoke). Cero acciones destructivas sin confirmar.
- [ ] **KPI-5**: el test 11 de F4 verde ⇒ ningún subcomando de escritura de git en `api/git.py`.
- [ ] Las 4 flags declaran default explícito (**las 4 ON**) y el plan deja escrito por qué ninguna cae
      en (A) ni (B).
- [ ] Los 2 archivos `tests/test_plan265_*.py` registrados en **ambas** listas `HARNESS_TEST_FILES`;
      `test_harness_ratchet_meta.py` verde.
- [ ] **Cero `style={{`** en los componentes nuevos de consola; cero literales hex nuevos; cero
      espaciados hardcodeados en el `.module.css` nuevo. Ratchet de UI verde.
- [ ] Cero `setInterval`/`refetchInterval` nuevos.
- [ ] Con `STACKY_CONSOLE_FULLSCREEN_ENABLED=false`, el dock se comporta **exactamente** como antes
      (paso 8 del smoke).
- [ ] Registro de implementación agregado al final de **este** documento.
- [ ] `git commit` con **pathspec explícito** (`git commit -- "<ruta>" ...`). Prohibido `git add -A`,
      `reset`, `amend`, `stash` y `--no-verify`. El `push` es manual.
