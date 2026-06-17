# Plan 37 — "Claude Code CLI" se ejecuta SIEMPRE por la CLI (nunca cae a Copilot) y los fallos se ven, no se ocultan

> **Estado:** PROPUESTO (reescrito 2026-06-16 sobre evidencia de runtime).
> **Numeración:** 37 (máximo previo = `36_PLAN_SELECTOR_RUNTIME_SIN_FALLBACK.md`). Es el correlativo natural y el número pedido por el operador.
> **Pensado para que un modelo menor (Haiku / Codex / GitHub Copilot Pro) lo implemente sin inferir nada.**
> **Relación con el Plan 36:** el 36 cerró el *routing* (selección → runner, sin fallback silencioso). Este plan cierra lo que QUEDA: que el **valor del selector** no sea Copilot por default/migración, que los **fallos del subproceso `claude` se persistan** (hoy se pierden), y que los **runs colgados (zombie)** se corten.

---

## 0. CORRECCIÓN IMPORTANTE DEL DIAGNÓSTICO PREVIO (leer antes de tocar nada)

Una versión anterior de este documento afirmaba que la causa era el **passthrough de credenciales**: que `build_agent_env` (`backend/services/agent_env.py:45`, `:50-53`) borra `ANTHROPIC_API_KEY` y por eso `claude` caía a la suscripción de GitHub Copilot. **ESO ES FALSO y quedó refutado con evidencia dura.** NO implementar ningún cambio sobre `agent_env.py` ni "readmitir credenciales".

**Prueba reproducible (2026-06-16, CLI `claude` v2.1.178):**

| Test | Resultado |
|---|---|
| `claude -p "model id?" --model claude-sonnet-4-6` con el env EXACTO de `build_agent_env(...)` (sin `ANTHROPIC_API_KEY`) | `rc=0` → responde **`claude-sonnet-4-6`** |
| Ídem con `os.environ` completo | `rc=0` → **`claude-sonnet-4-6`** |
| `ANTHROPIC_API_KEY` presente en el entorno del operador | **NO existe** (ni filtrado ni full) |
| `~/.claude/.credentials.json` (OAuth Anthropic Pro en disco) | **existe** |

Conclusión: con el **mismo entorno filtrado que usa Stacky**, `claude` autentica por el **OAuth de disco** y sirve **Sonnet 4.6**, no Haiku. El filtro de entorno no degrada nada. El `claude` CLI **no tiene ninguna vía de auth por GitHub Copilot**; "Copilot/Haiku" solo puede salir del runtime `github_copilot` (bridge `backend/copilot_bridge.py`) o del chat de Copilot de VS Code — **nunca** del runtime `claude_code_cli`.

**Evidencia de runtime (DB viva `DeployStackyAgents/data/stacky_agents.db` + backups):**
- Los únicos runs `claude_code_cli` registrados o **salen con `exit 1`** (functional, ~155 s de trabajo y muere) o quedan **zombie** (technical, `status=running` 30+ min, `output` vacío). **Ninguno** es `github_copilot`; **ninguno** muestra Haiku.
- El stderr del proceso `claude` **no se persiste en ningún lado** (`claude_code_runs/<id>/events.jsonl` guarda solo `exit_code`; `system_logs` no guarda la fuente `claude-code-stderr`; `error_message` en DB = `"claude code cli exited with code 1"`). Por eso el operador percibe "falla en silencio" y lo atribuye a Copilot.

---

## 1. Objetivo y KPIs

**Objetivo.** Cuando el operador quiere usar Claude Code CLI:
1. El **valor del selector** debe ser `claude_code_cli` de forma confiable (default sano; la migración del Plan 36 no debe reintroducir Copilot).
2. Cuando un run `claude_code_cli` **falla o se cuelga**, el operador debe **ver la causa real** (stderr persistido + estado terminal visible), nunca un silencio que parezca "usó Copilot".
3. Un run colgado debe **terminar solo** en un tiempo acotado (no zombie indefinido).

**KPIs (binarios, verificables):**
- **KPI-1:** instalación nueva y operador migrado del Plan 36 → el selector arranca en `claude_code_cli` (no `github_copilot`). Verificable por test de store + inspección de `localStorage`.
- **KPI-2:** un run `claude_code_cli` que termina con `exit_code != 0` deja en `events.jsonl`, en `MANIFEST.json` y en `agent_executions.error_message` las **últimas N líneas de stderr** del proceso. Verificable por test backend.
- **KPI-3:** un run sin actividad / con `claude` que no cierra solo se **termina** dentro de `cap` segundos (default > 0) y queda en `status=error|cancelled` con motivo `timeout`/`stall`. 0 runs en `running` por más de `cap + margen`. Verificable por test backend (con proceso fake) y por inspección de DB.
- **KPI-4 (no-regresión):** Codex CLI y GitHub Copilot siguen idénticos. `agent_env.py` no se modifica. Ningún secreto nuevo se filtra a subprocesos.

---

## 2. Causa raíz REAL (clasificación obligatoria, con `archivo:línea`)

El operador YA selecciona Claude Code CLI y el routing lo respeta (Plan 36). El problema se descompone en **tres causas independientes**:

### Pilar A — La queja literal: a veces el selector vale `github_copilot`
- El path primario de ejecución respeta el selector: `frontend/src/hooks/useAgentRun.ts:28-39` envía `runtime: agentRuntime` a `Agents.runWithOptions`. Los otros puntos (`AgentLaunchModal.tsx:236`, `TicketBoard.tsx:297` y `:583`, `TicketGraphView.jsx:328`) usan `launchAgentWithRuntime` (`services/agentLaunch.ts:105`), que también respeta el runtime (`:120` rama Copilot, `:143` rama CLI). **No hay ningún path que mande "claude seleccionado" a Copilot.**
- ⇒ La fuga se reduce a **el VALOR del selector**: el default es `github_copilot` (`frontend/src/store/workbench.ts:77`) y la **migración del Plan 36** (`workbench.ts:136` bump de `version`, fallback `:143` → `"github_copilot"`) **resetea la preferencia persistida** del operador a Copilot. Si el selector vale `github_copilot`, el `RunButton` primario manda `runtime:"github_copilot"` → `Agents.openChat` → bridge Copilot → con Copilot Free = solo Haiku.
- El botón "↗ Abrir en Chat" (`InputContextEditor.tsx:139`, hook `useOpenChat.ts:11` que llama `openChat` SIN `runtime`) **no es la fuga**: está **gateado a `!cliRuntime`** (`InputContextEditor.tsx:127`), o sea se oculta cuando el selector está en un runtime CLI. Es un escape hatch deliberado a Copilot. Solo se relabela para que no confunda (F1.3).
- Defensa adicional: si el payload de `/run` llega **sin** `runtime`, el backend default-ea a `github_copilot` (`backend/api/agents.py:351-353`). El frontend siempre lo manda, pero conviene endurecer (F1.4).

**Clasificación A:** *valor de configuración por default/migración apunta a Copilot* — no es bug de routing ni de credenciales.

### Pilar B — Los fallos del subproceso se pierden (falla en silencio)
- El runner lee stdout y **stderr** en threads (`backend/services/claude_code_cli_runner.py:829-841`); ambos van al mismo `tail` vía `_read_stream` (`:1793-1834`) y al log stream en vivo (fuente `claude-code-stderr`).
- Pero en la rama de error (`:1228-1258`) el `append_event` (`:1233-1237`) y el `write_manifest` solo registran `exit_code`/`duration_ms`; el `error_message` que se persiste en DB es el genérico `"claude code cli exited with code N"`. **El stderr nunca se persiste** → diagnóstico imposible post-mortem (confirmado: `events.jsonl` y `system_logs` no lo tienen).

**Clasificación B:** *gap de observabilidad* — el motivo del `exit 1` existe pero no se guarda.

### Pilar C — Runs colgados quedan zombie
- `session_timeout = config.CLAUDE_CODE_CLI_TIMEOUT if > 0 else None` (`claude_code_cli_runner.py:652`) y `CLAUDE_CODE_CLI_TIMEOUT` default = **0** (`backend/config.py:162`) → cap de sesión **desactivado**.
- El runner mantiene **stdin abierto** a propósito (`:657`, `:686-687`) para permitir turnos del operador. En modo `-p --input-format stream-json`, `claude` puede **quedar esperando más input y no terminar solo** tras completar su turno → `status=running` indefinido (el run zombie observado).
- Existen watchdogs (`STACKY_STALL_WATCHDOG_SECONDS` en `:851`/`:903-926`, runaway por turnos/costo `:820-827`/`:859-888`, session cap `:889-902`) pero dependen de flags; con el cap en 0 y, si el stall watchdog está en 0, nada corta el cuelgue.

**Clasificación C:** *defaults inseguros + ciclo de vida de stdin* — runs sin fin.

> **Comando de verificación de la evidencia (dejar la huella en el PR):**
> ```powershell
> cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents"
> # A: default selector y migración
> #   Grep "github_copilot" frontend/src/store/workbench.ts        -> 77, 143
> #   Grep "runtime: agentRuntime" frontend/src/hooks/useAgentRun.ts
> # B: stderr no persistido
> #   Grep "claude-code-stderr" backend/services/claude_code_cli_runner.py -> 838
> #   Grep "append_event" backend/services/claude_code_cli_runner.py -> 1233 (rama error)
> # C: timeout default 0
> #   Grep "CLAUDE_CODE_CLI_TIMEOUT" backend/config.py             -> 162
> ```

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** Codex CLI, Claude Code CLI, GitHub Copilot Pro. Cambiar el default a Claude Code CLI **no** rompe Codex ni Copilot; el operador puede re-seleccionar cualquiera.
- **PROHIBIDO tocar `agent_env.py`** ni "pasar credenciales". El diagnóstico de credenciales quedó refutado (§0). Cualquier PR que toque el filtro de entorno por este plan es incorrecto.
- **Fallar fuerte y VISIBLE, nunca en silencio:** ante error/cuelgue, el operador ve estado terminal + stderr real.
- **Cero trabajo extra del operador en el caso feliz:** seleccionar el agente y darle a Ejecutar; lo demás es automático.
- **Human-in-the-loop:** el sistema nunca cambia el runtime elegido por el operador en silencio; solo fija un default sano y le dice la verdad.
- **Backward-compatible y feature-flagged** donde haya cambio de comportamiento; defaults seguros. Los defaults horneados del deploy (`harness_defaults.env`) deben quedar coherentes (F4).
- **TDD:** test backend primero por fase. Frontend: vitest NO está instalado → criterio degradado a `npm run build` (tsc) + verificación manual descrita. Correr tests backend **por archivo** con el python del `.venv`.
- **No degradar** performance/estabilidad/DX. Reusar lo existente (`manifest_watcher`, watchdogs, `run_preflight`).

---

## 4. Fases

### F0 — Confirmar diagnóstico (no escribe código)
**Pasos:** dejar citadas en el PR las anclas de §2 (A: `workbench.ts:77/143`, `useAgentRun.ts:28-39`; B: `claude_code_cli_runner.py:838/1233-1258`; C: `config.py:162`, `claude_code_cli_runner.py:652/686-687`).
**Criterio (binario):** evidencia citada; clasificación A+B+C registrada; **confirmado que NO se toca `agent_env.py`**.
**Flag:** ninguno. **Trabajo del operador:** ninguno.

---

### F1 — Pilar A: el selector arranca y se mantiene en `claude_code_cli`

**F1.1 — Default del store.** En `frontend/src/store/workbench.ts:77` cambiar `agentRuntime: "github_copilot"` → `agentRuntime: "claude_code_cli"`.

**F1.2 — Migración que no reintroduce Copilot.** En el bloque `persist` (`workbench.ts:132-143`):
- Bumpear `version: 1` → `version: 2`.
- En `migrate(persisted, fromVersion)`: si `fromVersion < 2` y el `agentRuntime` persistido es `"github_copilot"` (el viejo default), mapearlo a `"claude_code_cli"`. **Preservar** una elección explícita de `"codex_cli"`. Mantener el fallback de valor inválido en `"claude_code_cli"` (`:143`).
- Comentario explicando el porqué (Copilot Free solo da Haiku; el default útil es la CLI).

**F1.3 — Relabel del escape hatch (claridad, no es la fuga).** En `InputContextEditor.tsx:139` cambiar `"↗ Abrir en Chat"` → `"↗ Abrir en Copilot Chat"` y el `title` (`:131`) ya es claro. No cambiar el gating `!cliRuntime` (`:127`).

**F1.4 — Endurecer el default backend (defensivo, flag).** En `backend/api/agents.py:351-353`, detrás de flag `STACKY_RUN_DEFAULT_RUNTIME` (default `"github_copilot"` para retro-compat de callers directos/tests/packs): si está seteado, usarlo como default cuando `runtime` viene ausente. NO cambiar el comportamiento default sin flag (evita romper tests/packs que asumen Copilot). Mantener el log de warning existente y el 400 para runtime inválido (`:367-385`).

**Criterio F1 (binario):**
- Test store (vitest si existiera; si no, test unit puro de la función `migrate`): `migrate({agentRuntime:"github_copilot"}, 1) === {agentRuntime:"claude_code_cli"}`; `migrate({agentRuntime:"codex_cli"},1)` preserva `codex_cli`; default de un store fresco = `claude_code_cli`.
- `npm run build` (frontend) verde.
- Backend: test de `agents.run` con flag `STACKY_RUN_DEFAULT_RUNTIME="claude_code_cli"` y payload sin runtime → dispatch a claude_code_cli; sin flag → comportamiento actual.
**Flag:** `STACKY_RUN_DEFAULT_RUNTIME` (solo F1.4). **Trabajo del operador:** ninguno (el default ahora juega a su favor).

---

### F2 — Pilar B: persistir el stderr real (que el fallo se vea)

**F2.1 — Separar el tail de stderr.** En `claude_code_cli_runner.py`:
- Crear `stderr_tail: list[str] = []` junto a `stdout_tail` (cerca de `:324`).
- En el reader de stderr (`:836-840`) pasar `stderr_tail` como `tail` en vez de `stdout_tail` (mantener `final_output=None`). Así el stderr queda aislado y no contamina la extracción de output.

**F2.2 — Adjuntar stderr a los artefactos en TODA rama terminal.** En las ramas de cierre (éxito `~:1040-1048`, parcial `~:1161-1169`, error `:1228-1258`):
- Calcular `stderr_excerpt = "\n".join(stderr_tail[-40:]).strip()`.
- Incluirlo en el `payload` del `append_event` de error (`:1233-1237`): `{"exit_code":..., "duration_ms":..., "error":..., "stderr_tail": stderr_excerpt}`.
- Incluirlo en `write_manifest` (campo nuevo `stderr_excerpt`) y en `output_data` (`:1258`).
- En `error_message` que se persiste en DB, **prefijar** las últimas líneas: `f"claude code cli exited with code {rc}: {stderr_excerpt[:500]}"` (si hay stderr).

**F2.3 — (opcional, flag `STACKY_CLAUDE_PERSIST_STDERR_FILE`, default ON)** volcar `stderr_tail` completo a `claude_code_runs/<id>/stderr.log` para forense.

**Criterio F2 (binario):**
- Test backend con un proceso fake que emite a stderr y sale con `rc=1`: el `events.jsonl` del run contiene `stderr_tail` no vacío; el `error_message` de la fila incluye el extracto; el `MANIFEST.json` tiene `stderr_excerpt`.
- No-regresión: en éxito (`rc=0`) sin stderr, los campos quedan vacíos y nada cambia para el operador.
**Flag:** `STACKY_CLAUDE_PERSIST_STDERR_FILE` (solo F2.3). **Trabajo del operador:** ninguno.

---

### F3 — Pilar C: ningún run queda zombie + diagnosticar el `exit 1`

**F3.1 — Cap de sesión por default sano.** En `backend/config.py:162` dejar `CLAUDE_CODE_CLI_TIMEOUT` con default **> 0** (sugerido `1800` = 30 min) en vez de `0`. Documentar que `0` = ilimitado (opt-in explícito). Con esto, `session_deadline` (`claude_code_cli_runner.py:849`, `:889-902`) corta el run y lo marca terminal con motivo de cap.

**F3.2 — Stall watchdog por default.** Asegurar `STACKY_STALL_WATCHDOG_SECONDS` (usado en `:851`/`:903-926`) con default > 0 (sugerido `300`): si `claude` no emite eventos por N s, se termina y queda `error`/`cancelled` con motivo `stall`. (Solo fijar el default si hoy es 0; verificar en `config.py`.)

**F3.3 — Cierre de stdin al fin de turno (raíz del cuelgue, flag `STACKY_CLAUDE_AUTOCLOSE_STDIN`, default OFF→validar).** Hipótesis confirmada por código: stdin queda abierto (`:686-687`) y `claude` en `--input-format stream-json` puede no terminar solo. Cuando `_on_stream_event` detecte fin de turno/`result` y no haya turno interactivo pendiente, cerrar `proc.stdin` para que `claude` finalice limpio. Mantener el modo interactivo (no cerrar) si el operador está en una sesión multi-turno. Detrás de flag por riesgo.

**F3.4 — Runbook del `exit 1`.** Con F2 ya mergeado, el operador re-ejecuta el run funcional que fallaba; el `stderr_tail` persistido revela la causa real (p.ej. flag no soportada como `--effort`/`--append-system-prompt-file` en la versión instalada, error de MCP, error de tool, etc.). Documentar en el PR el `stderr` capturado y abrir el fix puntual si aplica. **No** adivinar la causa antes de tener el stderr.

**Criterio F3 (binario):**
- Test backend con proceso fake que nunca termina: con `CLAUDE_CODE_CLI_TIMEOUT=2` el run se marca terminal (`error`/`cancelled`, motivo cap) en ≤ cap+margen; `_PROCESSES` queda limpio.
- Test fake sin eventos: con `STACKY_STALL_WATCHDOG_SECONDS=2` se dispara stall.
- DB: tras el cambio, 0 filas `claude_code_cli` en `running` por > cap+margen.
**Flags:** `CLAUDE_CODE_CLI_TIMEOUT`, `STACKY_STALL_WATCHDOG_SECONDS`, `STACKY_CLAUDE_AUTOCLOSE_STDIN`. **Trabajo del operador:** ninguno.

---

### F4 — Coherencia del deploy (que el horneado no revierta los defaults)
- Actualizar `backend/.env.example` con los nuevos defaults/flags (`STACKY_RUN_DEFAULT_RUNTIME`, `CLAUDE_CODE_CLI_TIMEOUT=1800`, `STACKY_STALL_WATCHDOG_SECONDS=300`, `STACKY_CLAUDE_PERSIST_STDERR_FILE`, `STACKY_CLAUDE_AUTOCLOSE_STDIN`).
- Verificar que el snapshot horneado (`harness_defaults.env` → `backend/.env` en cada deploy; ver memoria del arnés) **no** reintroduzca `CLAUDE_CODE_CLI_TIMEOUT=0` ni un runtime default Copilot. Si el snapshot vivo trae valores viejos, regenerarlo.
- El default del **selector** vive en el bundle del frontend (F1), no en `.env`: confirmar que el build del frontend se rehornea en el deploy.

**Criterio F4:** `.env.example` actualizado; deploy de prueba conserva los defaults nuevos; frontend buildeado trae el selector en `claude_code_cli`.

---

## 5. Verificación / cómo probar

**Backend (python del `.venv`, por archivo):**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& .\.venv\Scripts\python.exe -m pytest tests\test_claude_code_cli_phase1.py -q
& .\.venv\Scripts\python.exe -m pytest tests\test_claude_cli_stderr_persist.py -q   # nuevo (F2)
& .\.venv\Scripts\python.exe -m pytest tests\test_claude_cli_timeout_stall.py -q     # nuevo (F3)
& .\.venv\Scripts\python.exe -m pytest tests\test_agents_run_default_runtime.py -q   # nuevo (F1.4)
```

**Frontend:**
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
npm run build   # tsc + vite; debe quedar verde
```

**Manual (operador):**
1. Borrar/observar `localStorage` del workbench: tras el deploy, el selector "Ejecutar con" aparece en **Claude Code CLI**.
2. Seleccionar un agente `.agent.md`, cargar contexto, **Ejecutar**. Confirmar en la consola in-page que streamea y que en DB la fila es `runtime=claude_code_cli` con modelo Sonnet.
3. Forzar un fallo (p.ej. agente inexistente) y confirmar que el run queda `error` con **stderr visible** (no silencio).
4. Confirmar que ningún run queda en `running` más de ~30 min.

**Reproducción de auth (opcional, ya hecha en §0):**
```powershell
$env:ANTHROPIC_API_KEY=$null
claude -p "What is your exact model id? Reply with ONLY the id." --model claude-sonnet-4-6
# Esperado: claude-sonnet-4-6 (NO haiku/copilot)
```

---

## 6. Riesgos y rollback
- **F1 (default claude_code_cli):** un operador que de verdad quería Copilot deberá re-seleccionarlo. Aceptable (Copilot Free solo da Haiku). Rollback: revertir `workbench.ts:77` y la migración.
- **F3.1/F3.3 (timeout + cierre de stdin):** podría cortar sesiones interactivas largas legítimas. Mitigación: cap generoso (30 min) y `STACKY_CLAUDE_AUTOCLOSE_STDIN` por flag/OFF hasta validar. Rollback: `CLAUDE_CODE_CLI_TIMEOUT=0`.
- **F2:** mínimo riesgo (solo agrega campos). Cuidar no loguear PII en stderr persistido → reusar `pii_masker` si el stderr puede traer datos (como ya se hace con el output, `:944-945`).
- **Regla dura:** ningún cambio en `agent_env.py`. Si un PR lo toca, rechazar.

---

## 7. Checklist final
- [ ] F0 evidencia citada; confirmado "no tocar agent_env".
- [ ] F1.1 default `claude_code_cli`; F1.2 migración v2 (copilot→claude, preserva codex); F1.3 relabel; F1.4 flag backend.
- [ ] F2 stderr persistido en events.jsonl + MANIFEST + error_message (+ stderr.log opcional).
- [ ] F3 cap default 30 min + stall default + (flag) autoclose stdin; runbook del exit 1 con stderr real.
- [ ] F4 `.env.example` + horneado coherentes; frontend rehorneado.
- [ ] Tests backend nuevos verdes (por archivo, venv); `npm run build` verde.
- [ ] Verificación manual de los 4 puntos de §5.
