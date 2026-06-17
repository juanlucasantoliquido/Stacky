# Plan 36 — Selector de runtime que SIEMPRE se respeta (sin fallback silencioso a GitHub Copilot)

> Estado: PROPUESTO. Numeración: 36 (máximo previo = 35_PLAN_APRENDIZAJE_DEL_ARNES_PATRONES_REUTILIZABLES.md).
> Pensado para que un modelo menor (Haiku / Codex / GitHub Copilot Pro) lo implemente sin inferir nada.

## 1. Título, objetivo y KPI

**Objetivo.** Cuando el operador selecciona un runtime ("GitHub Copilot", "Codex CLI" o "Claude Code") en Stacky, el agente DEBE lanzarse con EXACTAMENTE ese runtime, sin ningún fallback silencioso a `github_copilot`. Hoy el operador reporta que aun seleccionando "Claude Code" se abre el chat de GitHub Copilot en VS Code y nunca logró abrir la consola headless de Stacky con Claude Code. Este plan elimina el default persistido peligroso, hace el default explícito y visible, agrega un indicador de "runtime efectivo" antes de lanzar, y añade un criterio binario backend que prueba que `runtime` del payload == `runtime` ejecutado (sin reescritura).

**KPI / impacto.**
- KPI-1 (binario): para cada lanzamiento, `payload.runtime == metadata["runtime"]` de la ejecución resultante. Meta: 100%.
- KPI-2 (operador): "abrir consola headless con Claude Code" pasa de imposible a 1 clic, 0 pasos manuales nuevos.
- KPI-3 (regresión): 0 lanzamientos que cambien de runtime sin que el operador lo vea en la UI.

## 2. Por qué ahora / gap que cierra

El operador NUNCA pudo usar la consola headless de Claude Code; siempre termina en Copilot Chat. Causa raíz confirmada (ver F0): NO es propagación rota en el backend — el backend ya respeta el runtime end-to-end. El gap está en el **frontend**:

1. El default del selector está **persistido** como `github_copilot` en `localStorage` (clave `stacky-workbench`), y sobrevive entre sesiones vía `partialize`. Si el operador no cambia el selector explícitamente en CADA modal, lanza Copilot.
2. La decisión de "abrir VS Code Chat vs consola headless" la toma el **frontend** ANTES de llamar al backend: si `agentRuntime === "github_copilot"` se llama `Agents.openChat` (abre Copilot) y NUNCA se manda `runtime` al endpoint `/run`. Es decir: con el default pegado, el operador nunca llega siquiera a la rama CLI.
3. Cuando el operador SÍ elige "Claude Code" pero el binario/sesión no está listo (`claudeReady === false`), el botón de lanzar queda deshabilitado; el operador, para lograr "algo", vuelve a Copilot. Eso refuerza la percepción de "siempre abre Copilot".

El backend tiene un fallback secundario `runtime = runtime_raw or "github_copilot"` (agents.py) que solo aplica cuando `runtime` viene ausente/None — hoy NO es la causa, pero es una bomba silenciosa que este plan también desactiva (default explícito y logueado).

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cada cambio funciona en los 3 o degrada con fallback EXPLÍCITO y visible (nunca silencioso).
- **Cero trabajo del operador:** el fix es invisible/automático. La migración del store no requiere ninguna acción manual del operador.
- **Human-in-the-loop:** el operador siempre elige el runtime; el sistema nunca decide por él ni reescribe su elección.
- **Mono-operador sin auth real:** nada de RBAC.
- **Backward-compatible:** llamadas viejas a `/run` sin `runtime` siguen funcionando (default explícito + warning), pero la UI nunca manda ausente.
- **No degradar** performance/seguridad/estabilidad/DX. Reusar lo existente.
- **TDD:** test primero en cada fase con backend. Frontend: vitest NO está instalado → criterio degradado a verificación manual descrita (con instrucción de instalación opcional).

---

## 4. Fases

### F0 — DIAGNÓSTICO REPRODUCIBLE (no escribe código; confirma causa raíz)

**Objetivo.** Reproducir el bug y confirmar con evidencia rutas:líneas dónde se decide abrir Copilot en lugar de la consola headless.

**Pasos de reproducción (operador / implementador):**
1. Abrir Stacky. En la barra superior, el selector "Ejecutar con" muestra **GitHub Copilot** activo por default (estado persistido).
   - Evidencia: `frontend/src/store/workbench.ts:77` → `agentRuntime: "github_copilot"`; `frontend/src/store/workbench.ts:135` → `partialize: (state) => ({ agentRuntime: state.agentRuntime })` (se persiste en `localStorage` clave `stacky-workbench`, definida en `workbench.ts:130`).
2. Sin tocar el selector, abrir el modal de asignación de un agente y lanzar.
   - El modal lee `agentRuntime` del store: `frontend/src/components/AgentLaunchModal.tsx:57`.
   - En `handleLaunch`, llama `launchAgentWithRuntime({ runtime: agentRuntime, ... })`: `AgentLaunchModal.tsx:235-241`.
3. Como `agentRuntime === "github_copilot"`, `launchAgentWithRuntime` toma la rama Copilot y llama `Agents.openChat(...)` → abre VS Code Chat. NUNCA llama al endpoint `/run` ni manda `runtime`.
   - Evidencia: `frontend/src/services/agentLaunch.ts:120-128` (`if (runtime === "github_copilot") return Agents.openChat(...)`).
   - Confirmación post-launch: `AgentLaunchModal.tsx:243` (`if (agentRuntime === "github_copilot") setBridgeStatus("ready")`).
4. Si el operador SÍ elige "Claude Code" pero el binario/sesión no está listo, el botón "Lanzar" queda deshabilitado y empuja al operador de vuelta a Copilot.
   - Evidencia: `AgentLaunchModal.tsx:398` (`disabled={... || (agentRuntime === "claude_code_cli" && !claudeReady)}`).

**Confirmación de que el backend NO es la causa (no reescribe runtime):**
- `backend/api/agents.py:349-350` → `runtime = runtime_raw or "github_copilot"`. SOLO aplica si `runtime` viene ausente/None; con la UI actual viene siempre presente, así que no se dispara hoy. Es fallback latente, no la causa.
- `backend/api/agents.py:358-376` → runtime desconocido devuelve 400 `unknown_runtime` (no fallback).
- `backend/agent_runner.py:236-307` → `claude_code_cli` se despacha a `start_claude_code_cli_run`. NO hay bloqueo 501 (el comentario de `agent_runner.py:159` que dice "claude_code_cli bloqueado en endpoint HTTP 501" está OBSOLETO; no existe tal bloqueo — verificar con grep `501` en `backend/api/agents.py`, que no arroja ningún `return 501` para este runtime).
- `backend/api/agents.py:495` → la respuesta incluye `"runtime": runtime` (el mismo que entró).
- `backend/config.py:155` → `CLAUDE_CODE_CLI_MODEL = "claude-sonnet-4-6"`; el "solo Haiku" venía del path Copilot Free, NO del runner CLI.

**Resultado de F0 a documentar (clasificación obligatoria):** la causa es **(c) el frontend ejecuta la rama Copilot antes de mandar nada al backend**, disparada por el **default persistido `github_copilot`** y reforzada por el botón deshabilitado cuando Claude no está listo. NO es (a) "no se envía" ni (b) "el backend lo pisa".

**Criterio de aceptación F0 (binario):** el implementador deja escrito en el PR las 6 rutas:líneas de arriba verificadas (existen y dicen lo citado). Comando de verificación:
```
cd "Stacky Agents"
grep -n "github_copilot" frontend/src/store/workbench.ts
grep -n "Agents.openChat" frontend/src/services/agentLaunch.ts
grep -n "501" backend/api/agents.py    # NO debe haber 501 para claude_code_cli
```
**Flag:** ninguno (solo diagnóstico). **Trabajo del operador: ninguno.**

---

### F1 — Backend: eliminar el fallback silencioso a `github_copilot` y hacer el default explícito + logueado

**Objetivo (1 frase).** El endpoint `/run` nunca cambia de runtime de forma silenciosa: si `runtime` está ausente usa un default EXPLÍCITO, logueado y devuelto en la respuesta; si está presente, lo respeta exacto.

**Valor.** Desactiva la bomba latente y deja una huella binaria de "runtime entrante == runtime ejecutado".

**Archivo exacto:** `backend/api/agents.py` (función `run`, alrededor de líneas 339-495).

**Cambio 1 — default explícito con bandera.** Reemplazar la lógica de `runtime_raw`/`runtime` (líneas 348-350) por:
```python
# Runtime seleccionado por el operador. Default EXPLÍCITO (no silencioso):
# si viene ausente, usamos github_copilot por retro-compat, pero lo marcamos
# como "defaulted" y lo logueamos para que sea visible/auditable.
runtime_raw: str | None = payload.get("runtime")
runtime_defaulted: bool = runtime_raw is None or str(runtime_raw).strip() == ""
runtime: str = (runtime_raw or "github_copilot") if runtime_defaulted else str(runtime_raw)
if runtime_defaulted:
    logger.warning(
        "runtime ausente en payload de /run; aplicando default EXPLÍCITO '%s' "
        "(ticket=%s, agent=%s). El frontend SIEMPRE debería enviar runtime.",
        runtime, payload.get("ticket_id"), payload.get("agent_type"),
    )
```
Caso borde: `runtime_raw == ""` (string vacío) cuenta como ausente → default + warning. `runtime_raw` con valor inválido (p.ej. `"foo"`) sigue cayendo en la validación existente `unknown_runtime` (líneas 358-376) → 400. No tocar esa rama.

**Cambio 2 — exponer `runtime_defaulted` en la respuesta.** En `resp_body` (línea 495), agregar la bandera:
```python
resp_body = {
    "execution_id": execution_id,
    "status": "preparing",
    "runtime": runtime,
    "runtime_defaulted": runtime_defaulted,
}
```

**TDD — test PRIMERO.** Archivo: `backend/tests/test_run_runtime_no_fallback.py` (nuevo).
Casos:
1. `test_run_with_explicit_claude_code_cli_keeps_runtime`: POST `/api/agents/run` con `runtime="claude_code_cli"` + `vscode_agent_filename` válido (monkeypatchear `agent_runner.run_agent` para que devuelva un id fijo y capture sus kwargs) → assert `run_agent` recibió `runtime="claude_code_cli"` y `resp.json["runtime"] == "claude_code_cli"` y `resp.json["runtime_defaulted"] is False`.
2. `test_run_with_explicit_codex_cli_keeps_runtime`: idem con `codex_cli`.
3. `test_run_absent_runtime_defaults_explicitly`: POST sin clave `runtime` → `resp.json["runtime"] == "github_copilot"`, `resp.json["runtime_defaulted"] is True`, y `agent_runner.run_agent` recibió `runtime="github_copilot"`.
4. `test_run_empty_runtime_treated_as_absent`: POST con `runtime=""` → igual que caso 3 (`runtime_defaulted is True`).
5. `test_run_unknown_runtime_rejected_400`: POST con `runtime="foo"` → status 400, body `error == "unknown_runtime"`, y `agent_runner.run_agent` NO fue llamado.

Patrón de mock (según memoria del repo): importar `from api import agents as agents_api`, parchear `agents_api.agent_runner.run_agent` con `monkeypatch.setattr`. Usar el `app.test_client()` del fixture existente (ver otros tests en `backend/tests/test_*` que ya golpean `/api/agents/run`).

**Comando exacto para correr (backend, python del .venv del repo):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_run_runtime_no_fallback.py -q
```
(En PowerShell: `& ".venv\Scripts\python.exe" -m pytest tests\test_run_runtime_no_fallback.py -q`.)

**Criterio de aceptación (binario):** los 5 tests pasan (5 passed). Comando: el de arriba.

**Flag:** `STACKY_RUNTIME_STRICT` (env var, leída en `backend/config.py`). Default seguro: `"true"`.
- Agregar en `config.py` junto a las otras vars de runtime (cerca de línea 151):
  `STACKY_RUNTIME_STRICT = os.getenv("STACKY_RUNTIME_STRICT", "true").lower() in ("1", "true", "yes")`
- Semántica: con `STACKY_RUNTIME_STRICT=true` (default), `runtime` ausente además del warning escribe en la metadata de la ejecución `metadata["runtime_defaulted"]=True` (ver F4). Con `false`, comportamiento idéntico a hoy salvo el campo extra en la respuesta. Documentar en `.env.example`.
- Agregar a `backend/.env.example`:
  ```
  # Plan 36 — si true (default), /run loguea y marca cuando el runtime vino ausente
  # y tuvo que aplicarse el default github_copilot. Nunca cambia de runtime en silencio.
  STACKY_RUNTIME_STRICT=true
  ```

**Impacto por runtime / fallback:**
- Codex CLI: respetado exacto, sin cambios funcionales.
- Claude Code CLI: respetado exacto, sin cambios funcionales.
- GitHub Copilot: sigue siendo el default cuando el campo viene ausente, pero ahora explícito y logueado.

**Trabajo del operador: ninguno.**

---

### F2 — Frontend: default neutral seguro + migración de store sin acción del operador

**Objetivo (1 frase).** El selector deja de quedar "pegado" en GitHub Copilot por estado viejo persistido: se migra el `localStorage` una vez (automática) y el default de fábrica pasa a ser explícito y configurable, sin que el operador haga nada.

**Valor.** Mata la causa raíz #1 (default persistido). El operador deja de heredar Copilot por estado viejo.

**Archivo exacto:** `frontend/src/store/workbench.ts`.

**Decisión de default.** Mantener `github_copilot` como default de fábrica para no romper la expectativa de operadores que sí usan Copilot, PERO:
- Resetear el valor persistido VIEJO una sola vez (migración) para que la elección del operador sea siempre fruto de un clic consciente o del default actual, no de un estado fosilizado.
- La migración NO requiere acción del operador.

**Cambio 1 — versionar el store y migrar.** En el segundo argumento de `persist(...)` (objeto de config, líneas 129-136), agregar `version` y `migrate`:
```ts
{
  name: "stacky-workbench",
  storage: createJSONStorage(() => localStorage),
  version: 1, // Plan 36 — bump para forzar migración del runtime persistido
  partialize: (state) => ({ agentRuntime: state.agentRuntime }),
  migrate: (persisted: unknown, fromVersion: number) => {
    // Migración v0 -> v1: el estado viejo pudo quedar pegado en un runtime.
    // No borramos la preferencia del operador si es un runtime válido conocido;
    // solo saneamos valores inválidos/ausentes al default de fábrica.
    const valid = ["github_copilot", "codex_cli", "claude_code_cli"];
    const prev = (persisted ?? {}) as { agentRuntime?: unknown };
    const rt = typeof prev.agentRuntime === "string" && valid.includes(prev.agentRuntime)
      ? (prev.agentRuntime as AgentRuntime)
      : "github_copilot";
    return { agentRuntime: rt };
  },
}
```
Caso borde: si `localStorage` no tiene la clave (operador nuevo), zustand usa el default de fábrica (`github_copilot`) sin invocar `migrate`. Caso borde: si el valor persistido es un runtime válido (operador ya eligió Claude Code antes), `migrate` lo respeta (no lo pisa). Caso borde: valor corrupto/desconocido → saneado a `github_copilot`.

> Nota de diseño (importante): la migración NO fuerza Claude Code. Forzarlo violaría human-in-the-loop. Solo sanea estado inválido. La causa raíz real se cierra con F3 (decisión de rama por runtime efectivo) + F1 (sin fallback silencioso), no obligando un runtime.

**TDD — vitest NO instalado (criterio degradado a verificación manual).**
- Verificación manual obligatoria (describir en el PR):
  1. Build del frontend sin errores de tipos: `cd "Stacky Agents/frontend" && npm run build` (debe terminar 0 errores TS).
  2. En el navegador con DevTools: poner `localStorage.setItem("stacky-workbench", JSON.stringify({state:{agentRuntime:"basura"},version:0}))`, recargar, abrir el selector → debe mostrar GitHub Copilot (saneado). Repetir con `agentRuntime:"claude_code_cli"` → debe mostrar Claude Code (respetado).
- Opcional (si se desea test automatizado): instalar vitest con `cd "Stacky Agents/frontend" && npm i -D vitest @testing-library/react jsdom` y crear `frontend/src/store/workbench.migrate.test.ts` con los 3 casos (válido respetado, inválido saneado, ausente→default). NO bloqueante.

**Criterio de aceptación (binario):** `npm run build` termina con 0 errores TS (comando arriba) + las 2 verificaciones manuales del store dan el resultado descrito.

**Flag:** ninguno (migración de versión de store es parte del contrato de persistencia; no se feature-flaggea). Default seguro: la migración es idempotente y solo sanea.

**Impacto por runtime:** neutral para los 3; solo cambia cómo se inicializa el selector tras estado viejo. **Trabajo del operador: ninguno** (migración automática al recargar).

---

### F3 — Frontend: indicador de "runtime efectivo" + confirmación antes de abrir Copilot

**Objetivo (1 frase).** Antes de lanzar, el modal muestra claramente con QUÉ runtime va a lanzar, y si va a abrir Copilot (que abre VS Code, no la consola headless) lo dice explícito, para que el operador nunca se sorprenda.

**Valor.** Cierra la causa raíz #2/#3 (el frontend decide la rama antes del backend; el operador no veía qué iba a pasar). Hace la elección visible y consciente. Cero pasos nuevos: es solo una etiqueta + el texto del botón ya existente.

**Archivo exacto:** `frontend/src/components/AgentLaunchModal.tsx`.

**Cambio 1 — etiqueta de runtime efectivo bajo el selector.** Debajo del `<AgentRuntimeSelector .../>` (después de la línea 296, dentro de `runtimeSection` o inmediatamente después), agregar un texto determinista que reusa `runtimeDisplayLabel` (ya existe en `services/agentLaunch.ts:70`):
```tsx
<p className={styles.effectiveRuntime} role="status">
  Lanzará con: <strong>{runtimeDisplayLabel(agentRuntime)}</strong>
  {agentRuntime === "github_copilot"
    ? " — abre VS Code Chat (no la consola headless de Stacky)."
    : " — abre la consola headless de Stacky."}
</p>
```
Importar `runtimeDisplayLabel` en el bloque de imports desde `../services/agentLaunch` (línea 5-10). Agregar la clase `.effectiveRuntime` a `AgentLaunchModal.module.css` (estilo discreto, p.ej. `font-size: 12px; opacity: .75;` — copiar patrón de `.subtitle`).

> Nota: `TicketBoard.tsx:177` YA muestra `Lanzará con: <strong>{runtimeDisplayLabel(agentRuntime)}</strong>`. Este cambio lleva esa misma transparencia al modal, que es el punto donde el operador reporta el problema. Reuso del mismo helper, sin duplicar lógica.

**Cambio 2 — el botón ya distingue runtime (línea 405-411).** No cambiar la lógica; solo verificar que el texto "OK — Abrir en GitHub Copilot" vs "▶ Lanzar ejecución" sea coherente con la etiqueta nueva. Ya lo es.

**TDD — vitest no instalado → verificación manual descrita.**
- Manual:
  1. Abrir el modal con el selector en GitHub Copilot → la etiqueta dice "Lanzará con: GitHub Copilot — abre VS Code Chat (no la consola headless de Stacky)." y el botón dice "OK — Abrir en GitHub Copilot".
  2. Cambiar a Claude Code → la etiqueta dice "Lanzará con: Claude Code CLI — abre la consola headless de Stacky." y el botón dice "▶ Lanzar ejecución".
  3. Cambiar a Codex CLI → "Codex CLI — abre la consola headless de Stacky."
- `npm run build` 0 errores TS.

**Criterio de aceptación (binario):** `npm run build` 0 errores TS + las 3 verificaciones manuales dan el texto exacto descrito.

**Flag:** ninguno (es UI informativa, no cambia comportamiento). Default seguro: siempre visible. **Trabajo del operador: ninguno.**

---

### F4 — Backend: persistir y verificar `runtime` en la metadata de la ejecución (criterio binario payload==ejecutado)

**Objetivo (1 frase).** Garantizar y poder auditar que el runtime que entró por el payload es EXACTAMENTE el que se ejecutó, escribiéndolo en la metadata de la ejecución para los 3 runtimes.

**Valor.** Provee el criterio binario pedido por el operador: "test que garantice que el runtime del payload == runtime ejecutado (sin reescritura)".

**Estado actual (verificado).** Para `codex_cli` y `claude_code_cli`, `agent_runner.py` ya escribe `md["runtime"] = runtime` en la fila reemplazada (`agent_runner.py:210` y `:284`). Para `github_copilot` (rama estándar, `agent_runner.py:309+`), hay que confirmar que la metadata de la ejecución incluya `runtime`. Si no, agregarlo.

**Archivos exactos:**
- `backend/agent_runner.py` (rama `github_copilot`, a partir de la línea 309 — el `thread`/`_pre_run_then_run_in_background`). Verificar dónde se crea la fila `AgentExecution` con su metadata inicial (buscar con grep `metadata_dict` y `runtime` cerca de la creación de la ejecución, antes de línea 140). Asegurar que la metadata inicial de TODA ejecución incluya `metadata["runtime"] = runtime`.
- Si la fila se crea en un helper común antes del dispatch (líneas ~120-145, donde ya se loguea `"runtime": runtime`), agregar ahí `md["runtime"] = runtime` a la metadata persistida de la fila para que también el path copilot lo tenga.

**Cambio (defensivo, idempotente).** En el punto de creación de la ejecución (donde hoy se arma el dict de metadata inicial), asegurar:
```python
md = dict(initial_metadata or {})
md.setdefault("runtime", runtime)  # nunca reescribir si ya está; nunca quedar ausente
```
Caso borde: si ya existe `md["runtime"]`, `setdefault` no lo pisa (no reescritura).

**TDD — test PRIMERO.** Archivo: `backend/tests/test_runtime_metadata_roundtrip.py` (nuevo).
Casos (parchear los runners `start_codex_cli_run` / `start_claude_code_cli_run` para que no spawneen procesos reales y devuelvan un id; o usar el patrón de stub ya presente en `test_claude_code_cli_phase1.py`):
1. `test_copilot_run_records_runtime_metadata`: lanzar con `runtime="github_copilot"` → la `AgentExecution` resultante tiene `metadata["runtime"] == "github_copilot"`.
2. `test_codex_run_records_runtime_metadata`: `runtime="codex_cli"` → fila reemplazada tiene `metadata["runtime"] == "codex_cli"`.
3. `test_claude_run_records_runtime_metadata`: `runtime="claude_code_cli"` → `metadata["runtime"] == "claude_code_cli"`.
4. `test_runtime_never_rewritten`: pasar `runtime="claude_code_cli"` y assert que en NINGÚN punto la metadata final dice `"github_copilot"`.

**Comando exacto (backend, python del .venv):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_runtime_metadata_roundtrip.py -q
```

**Criterio de aceptación (binario):** los 4 tests pasan (4 passed). KPI-1 verificable: `payload.runtime == metadata["runtime"]` para los 3 runtimes.

**Flag:** reusa `STACKY_RUNTIME_STRICT` (F1). Con `true` (default), además escribe `metadata["runtime_defaulted"]` cuando el runtime vino ausente. Default seguro: `true`.

**Impacto por runtime:** los 3 escriben `metadata["runtime"]`. Fallback explícito: solo cuando viene ausente, y queda marcado en `metadata["runtime_defaulted"]`. **Trabajo del operador: ninguno.**

---

### F5 — (Opcional, default OFF) Pre-chequeo de "runtime listo" para reducir el rebote a Copilot

**Objetivo (1 frase).** Cuando el operador elige Claude Code o Codex CLI y el binario/sesión no está listo, mostrar una guía clara de configuración en vez de empujarlo silenciosamente de vuelta a Copilot.

**Valor.** Ataca la causa raíz #3 (botón deshabilitado → operador vuelve a Copilot). Reusa lo existente (`ClaudeCliConfigModal`, `probeClaude`). No cambia el comportamiento por default.

**Archivo exacto:** `frontend/src/components/AgentLaunchModal.tsx`. Ya existe el banner de "Claude Code no está configurado" (líneas 299-313) y el botón deshabilitado (línea 398). Este ítem solo agrega un texto que aclara: "Configurá Claude Code para usar la consola headless; no cae a Copilot automáticamente."

**Cambio:** en el `title` del botón deshabilitado (línea 400-403) y/o en el banner (línea 302), agregar la frase: "Stacky no cambia a GitHub Copilot por vos; configurá este runtime o elegí GitHub Copilot manualmente." Texto, no lógica.

**TDD:** verificación manual (vitest no instalado): con Claude Code seleccionado y no configurado, el banner muestra el texto nuevo y el botón sigue deshabilitado (no auto-cambia de runtime).

**Criterio de aceptación (binario):** `npm run build` 0 errores TS + verificación manual del texto.

**Flag:** `frontend` constante `SHOW_RUNTIME_READINESS_HINT` en el componente, default `true` (es solo texto). **Trabajo del operador: ninguno (opt-in de texto, default on, sin pasos nuevos).**

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| La migración del store borra la preferencia válida del operador. | `migrate` solo sanea valores inválidos; runtimes válidos se respetan (F2, test/manual). |
| Operadores que usan Copilot a propósito ven cambio de comportamiento. | Default de fábrica sigue siendo `github_copilot`; solo se hace explícito y visible. |
| Forzar Claude Code rompería human-in-the-loop. | El plan NUNCA fuerza runtime; solo elimina fallback silencioso y da transparencia. |
| `setdefault("runtime", ...)` pisa metadata existente. | `setdefault` no reescribe; test `test_runtime_never_rewritten` lo prueba. |
| Frontend sin vitest deja gaps de test. | Criterios degradados a verificación manual descrita + `npm run build` obligatorio; instalación opcional documentada. |
| `STACKY_RUNTIME_STRICT` mal configurado en prod. | Default `true`; con `false` el comportamiento es el de hoy + campo extra (no rompe). |

## 6. Fuera de scope

- Cambiar el default de fábrica a Claude Code (violaría human-in-the-loop; queda elección del operador).
- Auto-instalar / auto-loguear el CLI de Claude o Codex.
- Refactor del runner Copilot (`copilot_bridge`) o del router de modelos.
- RBAC / auth (mono-operador, no aplica).
- Cambiar el modelo fijo `claude-sonnet-4-6` (config.py:155) — fuera de scope, ya correcto.

## 7. Glosario, orden de implementación y DoD

**Glosario.**
- **runtime efectivo:** el valor `agentRuntime` del store que el frontend usará para decidir la rama de lanzamiento.
- **fallback silencioso:** cambiar de runtime sin avisar al operador. Prohibido por este plan.
- **default explícito:** usar `github_copilot` solo cuando el runtime viene ausente, logueándolo y marcándolo (`runtime_defaulted`).
- **consola headless:** el dock in-page de Stacky que streamea logs de los runners CLI (Codex/Claude), distinto de abrir VS Code Chat (Copilot).

**Orden de implementación (numerado, por dependencia):**
1. F0 — diagnóstico (sin código; deja evidencia en el PR).
2. F1 — backend default explícito + `runtime_defaulted` + flag `STACKY_RUNTIME_STRICT` + tests.
3. F4 — backend metadata `runtime` para los 3 runtimes + tests (depende de F1).
4. F2 — frontend migración de store (independiente del backend).
5. F3 — frontend etiqueta de runtime efectivo en el modal (depende de F2 para que el valor mostrado sea limpio).
6. F5 — frontend texto de readiness (opcional, último).

**Definición de Hecho (DoD) global (todo binario):**
- [ ] F0: 6 rutas:líneas verificadas y citadas en el PR; clasificación de causa = (c) + default persistido.
- [ ] F1: `tests/test_run_runtime_no_fallback.py` → 5 passed.
- [ ] F4: `tests/test_runtime_metadata_roundtrip.py` → 4 passed.
- [ ] F2: `npm run build` 0 errores TS + 2 verificaciones manuales del store OK.
- [ ] F3: `npm run build` 0 errores TS + 3 verificaciones manuales de etiqueta/botón OK.
- [ ] F5: `npm run build` 0 errores TS + verificación manual del texto OK.
- [ ] KPI-1: para un lanzamiento de cada runtime, `payload.runtime == metadata["runtime"]` (probado por F4).
- [ ] Operador: abrir consola headless con Claude Code en 1 clic, 0 pasos manuales nuevos.
- [ ] `.env.example` documenta `STACKY_RUNTIME_STRICT=true`.
- [ ] Suite backend afectada sin nuevas regresiones: correr por archivo los tests nuevos + `tests/test_claude_code_cli_phase1.py` con el python del .venv.

**Comando de validación global (backend):**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_run_runtime_no_fallback.py tests/test_runtime_metadata_roundtrip.py -q
```
**Comando de validación global (frontend):**
```
cd "Stacky Agents/frontend"
npm run build
```
