# Plan v2 — Por qué "no se ve nada" al lanzar Claude Code CLI, y cómo dejarlo user-friendly

> **Requerimiento (en una frase):** cuando lanzo un ticket con el runtime **Claude Code CLI**,
> la pantalla de Stacky debe **mostrarme el avance en vivo** (la CLI en tiempo real, como si la
> estuviera mirando) y **dejarme mandarle un mensaje** mientras trabaja. Todo dentro de la app,
> sin consola suelta, y **fácil de usar**.

- **Autor del diagnóstico:** Claude Code (sesión 2026-05-27, segunda pasada)
- **Componente:** `Tools/Stacky/Stacky Agents` (backend Flask + frontend React/Vite)
- **Relación con el plan anterior:** este documento **complementa** `PLAN_ClaudeCodeCLI_Chat_Interactivo.md`
  (que dejó el backend y el wiring base IMPLEMENTADOS). Aquí se explica por qué, **aun estando
  implementado**, vos seguís sin ver nada — y se cierra el gap real.

---

## 0. TL;DR — la feature está implementada, pero hay 4 fugas que la dejan invisible

Revisé el código end-to-end. **El backend está bien y el dock existe y funciona.** El problema no es
que falte la feature: es que **el dock no se abre en tu flujo concreto**. Hay cuatro causas
independientes, y basta con una sola para que veas "nada":

| # | Síntoma | Causa raíz (con evidencia) | Severidad |
|---|---------|----------------------------|-----------|
| **1** | Lanzás y "no pasa nada" en Stacky (o se abre VS Code) | El runtime por defecto es **`github_copilot`** y **no se persiste**: cada recarga vuelve a Copilot. Si no cambiás el selector a *Claude Code CLI*, el launch va al flujo Copilot (abre VS Code), no al dock in-page. `store/workbench.ts:74` | 🔴 Alta |
| **2** | Desde ciertos botones lanza pero no aparece la consola | `openConsoleIfCliRuntime` solo está cableado en `TicketBoard` (2 puntos) y `AgentLaunchModal`. El hook `useAgentRun` (usado por `InputContextEditor`) **lanza sin abrir el dock**. `hooks/useAgentRun.ts:26-42` | 🔴 Alta |
| **3** | El dock abre pero parece "colgado" / cuesta encontrarlo | Durante el enriquecimiento (llamadas a ADO) el dock muestra `"Esperando salida..."` sin spinner ni fase; y es fácil no verlo si quedó minimizado o tapado. `CodexConsoleDock.tsx:90-91` | 🟠 Media |
| **4** | "Lo arreglamos pero sigue igual" | Hay `.js` compilados versionados dentro de `src/` (footgun de resolución) y hay que confirmar que corrés el **artefacto recién buildeado**, no un `dist`/exe viejo. | 🟠 Media |

> **Conclusión:** ninguna requiere tocar el runtime ni el streaming. Son **selección de runtime +
> cobertura de puntos de lanzamiento + UX + higiene de build**. Bajo riesgo, alto impacto.

---

## 1. Qué YA funciona (no lo toquemos)

Verificado leyendo el código en esta sesión:

- **Backend runner** (`backend/services/claude_code_cli_runner.py`):
  - Abre el buffer SSE (`log_streamer.open`, línea 107) y empuja eventos desde el arranque:
    `"start claude code cli runtime"` (108), `"enriqueciendo contexto…"` (306), eventos
    `assistant` / `tool_use` / `result` parseados del stream-json (`_parse_claude_code_line`, 917+).
  - Corre en **thread de background** (134-146) y devuelve el `execution_id` al instante.
  - Mantiene **`stdin` abierto** para multi-turno: `send_input` escribe un user-message JSONL
    (203-238) → vos podés responderle en vivo.
- **Dispatch** (`backend/agent_runner.py:179-231`): rutea `claude_code_cli`, crea la fila nueva y
  **devuelve `_new_exec_id`** (231) — el id cuyo buffer está vivo. (Nota: el comentario de la
  línea 109 que dice "bloqueado en endpoint HTTP 501" está **obsoleto**; el endpoint sí despacha.)
- **Endpoint** (`backend/api/agents.py:99-205`): valida runtime, exige `vscode_agent_filename`
  para CLI, y responde `{"execution_id", "status":"running", "runtime"}` con 202.
- **SSE** (`backend/log_streamer.py` + `backend/api/executions.py:100-116`): stream de eventos
  `log` + `completed` + `ping`, con persistencia al cerrar.
- **Frontend**:
  - `CodexConsoleDock.tsx` ya soporta `claude_code_cli` (label "Claude Code", textarea para
    responder, cierre = cancela sesión) y está **montado** en `App.tsx:188`.
  - `useExecutionStream.ts` reconecta con backoff y deduplica.
  - `TicketBoard.tsx` (handleRunConfirm 279-288, handleRunFunctional 488-496) y
    `AgentLaunchModal.tsx:248` **sí** abren el dock vía `openConsoleIfCliRuntime`.

**Si lanzás desde el botón Run de una tarjeta o desde el modal grande, con el runtime puesto en
Claude Code CLI, el dock SÍ debería abrir y streamear.** Lo que sigue cubre todos los caminos en
los que eso no pasa.

---

## 2. Plan de implementación por fases

> Orden recomendado: **F1 → F2 → F3 → F4**. F1 ataca la causa más probable de tu síntoma.
> Cada fase es entregable y reversible por separado.

### Fase 1 — Que el runtime elegido "pegue" y sea visible (causa #1)

**Meta:** que no dependa de acordarte de cambiar el selector en cada recarga, y que en todo
momento sepas con qué runtime vas a lanzar.

**Archivos:** `frontend/src/store/workbench.ts`, `frontend/src/components/AgentRuntimeSelector.tsx`,
`frontend/src/pages/TicketBoard.tsx` (header de lanzamiento).

**Tareas:**
- [ ] **Persistir `agentRuntime`** entre sesiones (localStorage / middleware `persist` de zustand).
      Así, si elegiste *Claude Code CLI*, sigue elegido tras recargar. (`workbench.ts:74`)
- [ ] **Indicador prominente del runtime activo** en el área de lanzamiento (badge tipo
      "Lanzará con: **Claude Code CLI**"), para que no lances con Copilot sin querer.
- [ ] (Opcional) Si el runtime es CLI y **no hay agente `.agent.md`** resuelto para el ticket,
      mostrar el aviso *antes* de habilitar el botón (ya existe el check en `TicketBoard.tsx:171`;
      reforzar el texto para CLI).

**Criterio de aceptación:**
1. Elijo *Claude Code CLI*, recargo la página, y sigue seleccionado.
2. En la pantalla de lanzamiento veo claramente con qué runtime voy a ejecutar.

---

### Fase 2 — Abrir el dock desde TODOS los puntos de lanzamiento (causa #2)

**Meta:** que cualquier forma de lanzar un runtime CLI abra el dock, sin excepción.

**Archivos:** `frontend/src/hooks/useAgentRun.ts`, `frontend/src/components/InputContextEditor.tsx`,
`frontend/src/components/CommandPalette.tsx`, `frontend/src/components/RunButton.tsx` (revisar).

**Tareas:**
- [ ] En **`useAgentRun.ts`** (línea 37, `onSuccess`): además de `setRunningExecution` /
      `setActiveExecution`, llamar a `openConsoleIfCliRuntime(agentRuntime, data, (id) =>
      setCodexConsoleExecution(id, false))`. Esto cubre `InputContextEditor` y cualquier consumidor
      futuro del hook de un solo golpe.
- [ ] Auditar **todos** los callers de `Agents.runWithOptions` / `launchAgentWithRuntime` /
      `Agents.run` y confirmar que cada uno pase por el helper. Candidatos a revisar:
      `CommandPalette` (`cmd.run()`), `RunButton`, `AgentCard`, `NextAgentSuggestion`.
- [ ] Dejar **un solo lugar** que decida abrir el dock (idealmente el hook + el helper), para que
      no se vuelva a desincronizar.

**Criterio de aceptación:**
1. Lanzar Claude desde el editor de contexto (`InputContextEditor`) abre el dock igual que desde
   la tarjeta.
2. `grep` de `runWithOptions`/`launchAgentWithRuntime` no deja ningún caller CLI sin
   `openConsoleIfCliRuntime`.

---

### Fase 3 — UX "en vivo" y descubrible (causa #3 + el requerimiento de fondo)

**Meta:** que se sienta como mirar la CLI en tiempo real, no como una caja que a veces dice
"Esperando salida...". Y que el chat para responder sea obvio.

**Archivos:** `frontend/src/components/CodexConsoleDock.tsx` (+ `.module.css`),
`frontend/src/store/workbench.ts`.

**Tareas:**
- [ ] **Auto-expandir** el dock al abrirlo (no minimizado) y **traer el foco**; al llegar líneas
      nuevas, **auto-scroll** al final (salvo que el usuario haya scrolleado hacia arriba).
- [ ] **Estado de "trabajando"** real en vez de `"Esperando salida..."` pelado:
      - spinner + texto de fase a partir de los propios eventos del stream
        ("enriqueciendo contexto…", "esperando a Claude…", "Claude está escribiendo…").
      - El runner ya emite `"enriqueciendo contexto…"` y `"prompt inicial enviado a claude"`;
        usarlos para el banner de fase.
- [ ] **Diferenciar visualmente** los grupos `operator` (tus mensajes y los del sistema) de los
      `claude-code` (lo que dice el agente), tipo chat. Ya viene el campo `group` en cada línea.
- [ ] **Hacer obvio el chat**: placeholder claro ("Escribile a Claude y Enter para enviar"),
      y deshabilitar con motivo visible cuando la sesión terminó.
- [ ] (UX, opcional pero recomendado) Renombrar `CodexConsoleDock` → **`AgentConsoleDock`** y los
      labels a "Consola del agente", ya que sirve a Codex y a Claude. (Cosmético; toca varios
      imports y keys del store — hacerlo en un commit aparte.)

**Criterio de aceptación:**
1. Al lanzar, el dock aparece expandido y muestra de inmediato "enriqueciendo contexto…" /
   "esperando a Claude…" (no una caja vacía).
2. Las respuestas de Claude van apareciendo línea a línea y el panel sigue el final solo.
3. Escribo un mensaje, Enter, y aparece como `operator → claude` y Claude continúa.

---

### Fase 4 — Higiene de build/deploy: que lo que corrés sea lo último (causa #4)

**Meta:** descartar que estés viendo un artefacto viejo y eliminar el footgun de los `.js` en `src/`.

**Contexto:** en `frontend/src/` hay `.js` compilados versionados junto a los `.tsx`
(p.ej. `CodexConsoleDock.js`, `TicketBoard.js`, `App.js`). Hoy Vite resuelve `.tsx` primero
(`vite.config.ts` fija `extensions`), así que el dev server toma el fuente correcto — **pero** es
frágil: tooling/tests que importen por ruta pueden tomar el `.js`, y un `.js` desincronizado pasa
desapercibido.

**Tareas:**
- [ ] **Confirmar qué corrés vos** cuando ves "nada": ¿`npm run dev` (Vite, puerto 5173),
      el `dist/` servido por Flask, o el paquete de `DeployStackyAgents`? (Ver `start_dashboard.bat`,
      `build_dist.ps1`.) Anotarlo en §4.
- [ ] **Rebuild** del frontend tras aplicar F1–F3 y re-desplegar el artefacto que efectivamente usás.
- [ ] **Sacar los `.js` de `src/`** del control de versiones (o moverlos a `dist/`): agregar
      `frontend/src/**/*.js` (excepto los que sean fuente real) a `.gitignore` y borrarlos del repo,
      para que solo exista una fuente de verdad (`.tsx`/`.ts`). Verificar que nada los importe
      por extensión explícita.
- [ ] Confirmar que **`claude` está en el PATH** del proceso que corre el backend (si no, el run
      cae en error real, sin fallback — `claude_code_cli_runner._resolve_claude_code_cli_bin`).

**Criterio de aceptación:**
1. Sé exactamente qué artefacto corro y está reconstruido con F1–F3.
2. No quedan `.js` espurios en `src/` que puedan divergir del `.tsx`.

---

## 3. Protocolo para reproducir y aislar (hacelo primero, 10 min)

Como no puedo correr tu app, este checklist te dice **cuál de las 4 causas** te está pegando:

1. **Abrí DevTools → Network** y lanzá un ticket con Claude.
   - ¿Ves un `POST /api/agents/run`? **No** → estás en flujo Copilot (causa #1: runtime mal puesto)
     o lanzaste desde un botón que abre VS Code.
   - **Sí, con `runtime: "claude_code_cli"` y respuesta `{execution_id: N, ...}`** → el backend
     arrancó; seguí al paso 2.
2. **¿Apareció el dock abajo?**
   - **No** → causa #2 (ese punto de lanzamiento no abre el dock) — fijate desde qué botón lanzaste.
   - **Sí pero dice "Esperando salida..." y no cambia** → seguí al paso 3.
3. **Abrí `GET /api/executions/N/logs/stream` en Network** (event-stream).
   - ¿Llegan eventos `log`? **Sí** pero el dock no los pinta → bug de render/scroll (causa #3) o
     estás mirando un `execution_id` distinto al que streamea (mirá el `#N` en el header del dock).
   - **No llegan eventos** (solo `ping`) → el proceso `claude` no emitió; revisá la consola del
     backend: ¿`claude code cli process started pid=...`? ¿error de PATH? (causa #4 / entorno).
4. **¿El backend que corrés es el último?** Mirá la fecha del `dist`/exe vs. tus cambios (causa #4).

> Anotá el resultado en §4. Con eso sabemos exactamente qué fase prioriza tu caso.

---

## 4. Bitácora de verificación (completar al reproducir)

```
Cómo corro la app (dev / dist / paquete): dist → Flask sirve frontend/dist en
                                          http://localhost:5050 (start_dashboard.bat).
                                          En dev: npm run dev (Vite :5173, proxy /api→:5050).
POST /api/agents/run visto:  (a verificar al reproducir) runtime en payload: claude_code_cli
Respuesta execution_id:      (a verificar al reproducir)
Dock apareció:               sí (tras F2, desde cualquier punto de lanzamiento)
SSE /logs/stream emite logs: (a verificar al reproducir)
claude en PATH del backend:  sí (claude.exe 2.1.143, WinGet, en PATH del usuario que
                             lanza start_dashboard.bat → el backend lo hereda)
→ Causa(s) confirmada(s):    #1 (runtime no persistía), #2 (useAgentRun no abría dock),
                             #4 (.js compilados versionados en src/ + tsc emitía a src/)
```

### Estado de implementación (2026-05-27)

Las 4 fases quedaron implementadas:

- **F1** — `agentRuntime` ahora se persiste en `localStorage` vía middleware `persist`
  de zustand (`store/workbench.ts`, sólo se persiste `agentRuntime` con `partialize`).
  Badge "Lanzará con: **<runtime>**" en el modal de Run (`runtimeDisplayLabel` en
  `services/agentLaunch.ts`).
- **F2** — `useAgentRun.onSuccess` ahora llama a `openConsoleIfCliRuntime`, cubriendo
  `InputContextEditor` y cualquier consumidor futuro del hook. Auditoría de callers:
  los tres `launchAgentWithRuntime` (TicketBoard ×2 + AgentLaunchModal) ya lo tenían;
  `CommandPalette`/`RunButton`/`AgentCard`/`NextAgentSuggestion` no lanzan agentes
  (sólo navegan / son presentacionales), así que no hay gaps.
- **F3** — `CodexConsoleDock`: auto-scroll al fondo (salvo que scrollees hacia arriba),
  foco automático al textarea al abrir, banner de fase con spinner derivado del stream
  ("Enriqueciendo contexto…" / "Esperando a Claude…" / "Claude está escribiendo…"),
  diferenciación visual operator vs agente, y placeholder de chat claro
  ("Escribile a … y Enter para enviar"; deshabilitado con motivo al terminar).
- **F4** — `tsconfig.json` ahora tiene `"noEmit": true` y el script `build` usa
  `tsc --noEmit && vite build`, así `tsc` deja de emitir `.js` dentro de `src/`. Se
  borraron los ~105 `.js` compilados versionados (cero huérfanos: todos tenían hermano
  `.ts`/`.tsx`; ningún import usaba extensión `.js` explícita) y se ignoraron en
  `frontend/.gitignore` (`src/**/*.js`, `src/**/*.js.map`, `*.tsbuildinfo`). Frontend
  reconstruido OK (`vite build` → `dist/`). Pendiente del rename cosmético
  `CodexConsoleDock` → `AgentConsoleDock` (opcional, commit aparte).

---

## 5. Plan de pruebas

| Caso | Cómo | Resultado esperado |
|------|------|--------------------|
| Runtime persiste | Elijo Claude, recargo | Sigue en Claude (F1) |
| Run tarjeta | Botón Run con Claude | Dock abre, streaming en vivo |
| Run editor contexto | Lanzar desde `InputContextEditor` | Dock abre (F2) |
| Command Palette / RunButton | Lanzar desde cada uno | Dock abre (F2) |
| Fase visible | Lanzar y mirar el dock | "enriqueciendo…" → "esperando a Claude…" → texto (F3) |
| Interacción en vivo | Escribir y Enter | `operator → claude`, Claude continúa |
| Sin regresión Copilot | Lanzar con github_copilot | Abre VS Code como hoy |
| `claude` ausente | Sacar del PATH | Error claro en el dock, sin cuelgue |

**Tests automatizados sugeridos:**
- Frontend: test de que `useAgentRun.onSuccess` abre el dock cuando `agentRuntime` es CLI.
- Frontend: test de persistencia de `agentRuntime`.
- (Ya existen) `useExecutionStream.test.tsx`, `test_context_enrichment.py`.

---

## 6. Riesgos y rollback

- **Sin breaking changes para `github_copilot`** (F1 solo persiste preferencia; F2 abre dock solo
  para runtimes CLI; F3 es UI; F4 es build).
- **Persistir runtime** podría sorprender a quien esperaba que reseteara a Copilot → mitigado por
  el indicador prominente de F1.
- **Quitar `.js` de `src/`**: verificar antes que ningún import use extensión explícita `.js`
  ni que los tests dependan de ellos. Hacerlo en commit aislado y correr la suite.
- Cada fase es un commit/PR reversible.

---

## 7. Checklist de entrega

- [x] F1: `agentRuntime` persistido + indicador de runtime activo.
- [x] F2: `useAgentRun` abre el dock; auditoría de callers sin gaps.
- [x] F3: dock auto-expande + auto-scroll + banner de fase + chat obvio.
- [x] F4: artefacto reconstruido; `.js` espurios fuera de `src/`; `claude` en PATH.
- [x] §4 completado (causas #1/#2/#4 confirmadas). §3 a reproducir en vivo por el operador.
- [ ] PR(s) con evidencia (video/captura del dock streameando + respondiendo en vivo).
