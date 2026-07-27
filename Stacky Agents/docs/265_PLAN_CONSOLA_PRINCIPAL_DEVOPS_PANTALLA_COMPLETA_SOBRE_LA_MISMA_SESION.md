# Plan 265 — La consola como experiencia principal: pantalla completa sobre la MISMA sesión, con contexto de repo, diffs y auditoría

**Estado:** MEJORADO **v2 -> v3** (2026-07-27) · **Autor v1:** pipeline `proponer-plan-stacky` · **Juez v2:** `criticar-y-mejorar-plan` (misma corrida que el v1) · **Juez v3:** `criticar-y-mejorar-plan` en corrida INDEPENDIENTE (StackyArchitectaUltraEficientCode)
**Veredicto del v1:** **RECHAZADO** (5 BLOQUEANTES). **Veredicto del v2:** **RECHAZADO** (5 BLOQUEANTES nuevos).
Este documento es el **v3** con los fixes de las dos rondas aplicados.

> **Por qué hubo una tercera ronda.** El v2 lo produjo el **mismo agente y la misma corrida** que escribió el v1:
> no fue revisión independiente. La ronda v3 abrió **cada archivo citado** y verificó línea por línea. Resultado:
> los 16 anclajes que el v2 arregló **verifican**, pero aparecieron **5 anclajes nuevos que NO verifican**, tres de
> ellos con consecuencia directa (cablear la consola al endpoint equivocado, un comando de aceptación que no puede
> salir verde, y un atajo muerto). La lección operativa está escrita en §4.ter.

---

## CHANGELOG v2 -> v3 (ronda independiente)

- **D1 (BLOQ.)** — **`Executions.cancel` NO está en `api/endpoints.ts:1135`.** Esa línea es **`Agents.cancel`**,
  otra función, de otro objeto, que pega en **`POST /api/agents/cancel/<id>`** (`backend/api/agents.py:1434-1436`):
  llama `agent_runner.cancel()` y devuelve `{"ok": True}` **sin gate de estado, sin 409 y sin matar el subproceso
  de Codex ni de Claude**. El `Executions.cancel` real vive en **`api/endpoints.ts:1394`** (el objeto
  `export const Executions = {` abre en `:1326`). Toda F3 —el reuso, el "Gotcha del 409" y `CANCELLABLE_STATUSES`
  como "espejo exacto de `api/executions.py:616`"— colgaba del anclaje equivocado. **Fix:** F3 v3 ancla `:1394`,
  **prohíbe** explícitamente `Agents.cancel` y agrega el test 11 que lo verifica leyendo el archivo.
- **D2 (BLOQ.)** — **El comando "dirigido y binario" de F0.8 (y el #6 de los 19 de F8) ya sale ROJO hoy.**
  Medido en esta ronda: `pytest backend/tests/test_harness_flags_help.py -q` ⇒ **4 failed, 4 passed**. De los 5
  tests que selecciona el `-k` del v2, **4 fallan por deuda ajena** (`covers_all` con **79 keys** del registry sin
  ayuda; `bounded` con `STACKY_DEVOPS_COCKPIT_ENABLED: on_effect > 240 chars` = 316; `start_with_si`; `jargon` con
  15 violaciones). El DoD decía "**19 comandos exit 0**": **insatisfacible**. **Fix:** F0.8 v3 pega la **lista
  medida** de fallos previos como baseline y reemplaza el gate por una comprobación que mira **sólo las 4 keys
  nuevas**, con su propio comando y su propio exit 0.
- **D3 (BLOQ.)** — **El atajo `Escape` del registro está MUERTO con foco en la caja de búsqueda:** es el mismo bug
  que el v2 diagnosticó para `Enter` (C9) y dejó en pie para `Escape`. Medido: `shortcuts.ts:125`
  (`if (ctx.editable && !comboAllowedInEditable(d.combo)) return false;`) + `comboAllowedInEditable` (`:108-111`)
  ⇒ `parseCombo("Escape").ctrl === false`. El plan manda `Ctrl+Shift+F` a poner el foco **en ese input** y después
  registra `Escape` global para salir. Los tests 6/7/8 del v2 prueban `shouldHandleEscape`, una función pura que
  **nunca ve** `comboAllowedInEditable`: **verdes con el atajo muerto**. **Fix:** `Escape` baja a `onKeyDown` local
  (como `Enter`) y nace el **ratchet de atajos muertos** (F6 test 9), que mata la clase de bug entera.
- **D4 (BLOQ.)** — **`detectCollisions` particiona por `scope`: el "gate binario y automático" de F6 es ciego.**
  Medido: `shortcuts.ts:143` arma la clave como `` `${parseCombo(d.combo).key}|${d.combo.toLowerCase()}|${d.scope}` ``.
  Un `Escape` `scope:"global"` y el `Escape` de `LIST_NAV_DISPLAY_DEFS` `scope:"page"` (`:230`) **nunca colisionan**
  para esa función, y el diálogo canónico (`components/ui/dialogKeyboard.ts`) **no está en ninguno de los 3 arrays**.
  R5 apoyaba una mitigación de riesgo **Alto** en un gate que no puede disparar. **Fix:** test 3-bis que agrupa por
  **combo solo** (ignorando `scope`) y exige que todo duplicado cross-scope figure en un mapa congelado con su
  resolución escrita.
- **D5 (BLOQ.)** — **F1 rompe `tsc` siguiendo el plan al pie de la letra.** `store/workbenchPure.ts:9-13` declara
  `export interface WorkbenchPersistV3` con **3 campos** y `:24` la usa como **tipo de retorno** de
  `migrateWorkbenchPersist`. El v2 mandaba agregar `codexConsolePresentation` al objeto **leído** (`prev`) y al
  **retorno**, y **nunca** decía tocar la interfaz: un object literal con propiedad de más contra un tipo declarado
  es **TS2353**. El criterio de F1 era "`tsc` exit 0". **Fix:** F1 v3 trae el bloque literal de
  `WorkbenchPersistV4` y qué hacer con el nombre viejo.
- **D6 (IMP.)** — **`GET /api/executions/history` devuelve 404 con `STACKY_EXECUTION_HISTORY_ENABLED` OFF**
  (`api/executions.py:459-461`), y `api.get` **lanza** ante non-2xx. El v2 cuidó el 409 de F3 y olvidó este 404 en
  F5(b), donde sólo decía "ya existente". Es una flag real y apagable (`harness_flags.py:1896`). **Fix:** F5(b) v3
  declara la degradación, usa `rawGet` y suma el caso al test.
- **D7 (IMP.)** — **Frontera no declarada con el Plan 267**, que crea el catálogo único de acciones DevOps sobre
  **esta misma superficie** (su F6 se llama "la consola de acciones del agente") y dice textualmente
  *"**Prohibido** crear un segundo mecanismo de confirmación"* usando `confirmGateway`
  (existe hoy en `frontend/src/services/entityActions.ts`). §4.bis del v2 sólo cubría 260/263/264. **Fix:** §4.bis
  v3 agrega la fila del 267 con el reparto explícito de contratos.
- **D8 (IMP.)** — **`shouldHandleEscape(dialogOpen)` reinventa lo que el registro ya hace y el v2 nunca dijo de
  dónde sale ese booleano.** Medido: `shortcuts.ts:41` (`dialogOpen: boolean` en el contexto), `:124`
  (`if (ctx.dialogOpen && !d.allowInDialog) return false;`) y `ShortcutDef:38-39` ("Por default un atajo NO dispara
  con un diálogo abierto"). **Fix:** la guarda de diálogo la da el registro; `shouldHandleEscape` decide **sólo**
  por `presentation`.
- **D9 (IMP.)** — **`Ctrl+\`` es un combo riesgoso en el teclado del operador.** `parseCombo` compara
  `normalizeKey(ev.key)`; en layouts español (es-AR/es-ES, que es lo que corre esta máquina) la backtick es **tecla
  muerta** y `ev.key` puede no ser `` "`" ``. **Fix:** el combo pasa a `Ctrl+Shift+Enter`, alfanumérico e
  inequívoco en cualquier layout, y el smoke lo mide.
- **D10 (IMP.)** — **F0.6 citaba las reglas de `PlainHelp` incompletas.** Faltaban `what >= 10`, `what <= 200` y
  `example <= 300` (`tests/test_harness_flags_help.py:47-51`), no decía que la `JARGON_DENYLIST` vive en
  **`backend/tests/test_harness_flags_help.py:17`** (no en el módulo de servicio) y no decía que el match es
  `\b{term}s?\b` — **plural opcional**: "token" y "tokens" caen igual. Las 4 entradas del v2 cumplen (verificadas
  una por una en esta ronda), pero un modelo menor que reescriba una se estrella. **Fix:** reglas completas.
- **D11 (IMP.)** — **`_CATEGORY_KEYS["interfaz_ui"]` cierra en `:477`, y el `),` siguiente (`:484`) es de OTRA
  categoría** (`"paridad_proveedores"`, que abre en `:478`). El v2 decía "al final, antes del `),` de cierre" sin
  línea. Un modelo menor que scrollee de más mete las 4 keys en la categoría equivocada y
  `test_every_registry_flag_is_categorized` **sigue verde**: falso verde de categorización. **Fix:** línea pinneada.
- **D12 (IMP.)** — **"La MISMA sesión" es la tesis del plan y su único guardián era un humano contando líneas.**
  KPI-2 se verificaba en el paso 2 del smoke manual. **Fix:** **[ADICIÓN ARQUITECTO] F1.5** convierte el invariante
  en un gate automático.
- **D13 (MENOR)** — Anclas con deriva (verificadas): `CORE_SHORTCUT_DEFS` es **`:191-221`** (el v2 decía `:191-224`);
  `LIST_NAV_DISPLAY_DEFS` es **`:225-232`** (decía `:225-231`); el botón "Reintentar" del dock es **`:235-237`**
  (decía `:234-237`). **Fix:** corregidas.
- **D14 (MENOR)** — Sin frontera declarada con el **Plan 239** (Cockpit DevOps, **IMPLEMENTADO**). Verificado en
  esta ronda: el 239 **no** construye pantalla completa de consola ⇒ **no hay scope creep**, pero la ausencia de la
  declaración obliga a re-verificarlo. **Fix:** §4.bis lo declara con el resultado ya medido.
- **[ADICIÓN ARQUITECTO] F1.5** — `consoleSession.ts`: la identidad de sesión como **invariante ejecutable**.
- **[ADICIÓN ARQUITECTO] F6 test 9** — **ratchet de atajos muertos**: ningún combo de la consola puede prometer
  funcionar con foco en un input si `comboAllowedInEditable` lo bloquea. Mata la clase de bug de C9 y D3 de raíz.

---

## CHANGELOG v1 -> v2

- **C1 (BLOQ.)** — F0 mandaba las 4 keys a "la tupla `_CURATED_DEFAULTS_ON`" sin nombrar archivo, y declaraba
  **"Archivos a editar (2)"**. `_CURATED_DEFAULTS_ON` es un **set** que vive en
  `backend/tests/test_harness_flags.py:467`, **no** en `services/harness_flags.py`. Con `default=True` y sin
  entrar al set, `test_default_known_only_for_curated` sale ROJO. **Fix:** F0 v2 nombra el archivo, la línea y
  la estructura de forma literal.
- **C2 (BLOQ.)** — F0 no tocaba `_CATEGORY_KEYS` (`services/harness_flags.py:120`). Existe
  `test_every_registry_flag_is_categorized` (`tests/test_harness_flags.py:902`): toda key del registry debe estar
  categorizada. **Fix:** F0 v2 agrega las 4 keys a `_CATEGORY_KEYS["interfaz_ui"]` con el bloque literal.
- **C3 (BLOQ.)** — F0 declaraba `requires=` en 3 FlagSpec sin tocar `_REQUIRES_MAP_FROZEN`
  (`tests/test_harness_flags_requires.py:120`), guardado por igualdad exacta en `:312`. F0 corría ese test y su
  criterio "exit 0" era **falso**. **Fix:** F0 v2 agrega las 3 aristas al mapa congelado.
- **C4 (BLOQ.)** — F0 ignoraba `PLAIN_HELP` (`services/harness_flags_help.py`), obligatorio al 100% por
  `test_plain_help_covers_all_registry_keys`, y ni siquiera corría ese archivo de test. **Fix:** F0 v2 trae las 4
  entradas escritas y validadas contra el límite de 240, el prefijo `"Si "`, la `JARGON_DENYLIST` congelada y los
  dos regex prohibidos, y suma el comando de test.
- **C5 (BLOQ.)** — Paridad de runtimes falsa: el plan pedía "verificá en implementación si `codex_cli_runner`
  expone cancelación" y no decía de dónde sale `runtimeSupportsCancel`. Medido: **los 3 runtimes cancelan**
  (`codex_cli_runner.py:185`, `claude_code_cli_runner.py:228`, y el `else` de `api/executions.py:628-640` cae a
  `agent_runner.cancel()` `agent_runner.py:550` para `github_copilot`). **Fix:** hechos escritos, `metadata.runtime`
  identificado como fuente (ya viaja en `models.py` `to_dict` → `"metadata"`), y **[ADICIÓN ARQUITECTO] F2.5**
  con una matriz de capacidades única.
- **C6 (IMP.)** — KPI-3 decía `7 / 20` sin enumerar nunca las 20 (la tabla del v1 tenía 9 huecos: 7+9=16). No era
  binario. **Fix:** §1.3 enumera las 20, numeradas, con la fase que cubre cada una.
- **C7 (IMP.)** — F1 mandaba a "el `onRehydrateStorage` o equivalente; leé cómo lo hace hoy el archivo".
  `workbench.ts` **no tiene** `onRehydrateStorage`: usa `migrate: migrateWorkbenchPersist` +
  `WORKBENCH_PERSIST_VERSION` (`store/workbenchPure.ts:7,21`). **Fix:** F1 v2 nombra el mecanismo real, el bump
  3→4 y el test de regresión `store/workbenchPure.test.ts`.
- **C8 (IMP.)** — F3 reinventaba el cableado de cancelación. `components/ActiveRunsPanel.tsx:33,57-58,153` ya lo
  tiene resuelto con `useConfirm()` (de `components/ui/index.ts:46`) y `Executions.cancel(id)`
  (`api/endpoints.ts:1135`). **Fix:** F3 v2 reusa ese cableado y agrega el gate real (el estado, no el runtime).
- **C9 (IMP.)** — F6 inventaba el contrato de atajos: pedía `keys` y `label` cuando el registro usa `combo`,
  `description`, `scope`, `category` (`services/shortcuts.ts:24-37`), y mandaba a "grepear colisiones" cuando ya
  existe `detectCollisions()` (`shortcuts.ts:139`). Peor: `Enter`/`Shift+Enter` registrados en el registro global
  **nunca dispararían** con foco en la caja de búsqueda, porque `comboAllowedInEditable` (`shortcuts.ts:108-111`)
  sólo deja pasar combos con Ctrl. **Fix:** F6 v2 usa el contrato real, convierte `detectCollisions` en criterio
  binario, y baja `Enter`/`Shift+Enter` a un `onKeyDown` local del input.
- **C10 (IMP.)** — F5 decía "si el **261** no está implementado". El 261 **no existe** (hueco de numeración); el
  plan del trace de modelo/effort es el **264**. **Fix:** referencia corregida en todos los puntos.
- **C11 (IMP.)** — F4 no reusaba nada: ya existe `services/git_context.py:60` `_git(args, cwd)` con `subprocess`
  y timeout, y `services/plans_board.py:644,665-681` con `_GIT_TIMEOUT_SEC`. **Fix:** F4 v2 declara qué reusa,
  y **prohíbe editar `plans_board.py`** (es archivo compartido con el 263).
- **C12 (IMP.)** — Criterios grep rotos: `grep -c "navigator.clipboard" src/components/Console*.tsx` apunta a un
  glob que **no existe** (el componente es `CodexConsoleDock.tsx`); un glob vacío no devuelve 0, devuelve error.
  **Fix:** rutas literales y comando con semántica de salida definida.
- **C13 (MENOR)** — Anclas con deriva: `useExecutionStream.ts:14` (`dropped` está en `:12`), `workbench.ts:145-151`
  (el `partialize` real es `:148-152`). **Fix:** anclas corregidas.
- **C14 (MENOR)** — El dock ya tiene un botón rotulado **"Reintentar"** (`CodexConsoleDock.tsx:234-237`) que
  reintenta **cerrar la sesión**, no la corrida. Dos "Reintentar" con semánticas distintas en el mismo componente.
  **Fix:** el nuevo se rotula **"Volver a lanzar"**.
- **C15 (MENOR)** — Sin frontera declarada con 260/263/264 en los archivos compartidos. **Fix:** §4.bis nueva.
- **C16 (MENOR)** — Sin huella de regresión. **Fix:** DoD lo resuelve explícitamente (con justificación escrita
  de por qué no corresponde registrar una).
- **[ADICIÓN ARQUITECTO] F2.5** — `consoleCapabilities.ts`: matriz única de capacidades por runtime, con
  degradación declarada. Es el seam donde el 264 enchufa su selector de modelo/effort.
- **[ADICIÓN ARQUITECTO] F4.5** — enmascarado de secretos **antes** de que un diff llegue al navegador o a la
  bitácora. El v1 abría un camino por el que un `.env` o un `web.config` con un PAT viajaba entero a la UI.

---

## 1. Objetivo y KPI

### 1.1 Sustrato (verificado 2026-07-27)

`CodexConsoleDock` (`frontend/src/components/CodexConsoleDock.tsx`, 328 líneas) está montado globalmente en
`App.tsx:520` y es el canal único por el que ya entran el agente DevOps
(`components/devops/DevOpsAgentSection.tsx:5`), el doctor de secciones
(`components/devops/SectionDoctorButton.tsx:7`) y el documentador (`components/docs/DocumenterButton.tsx:37`).
El sustrato es bueno: SSE con reconexión exponencial y ring-buffer (`hooks/useExecutionStream.ts:23-24`,
`hooks/logRingBuffer.ts`), estado que sobrevive al F5 (`store/workbench.ts:148-152`) y cancelación ya construida
para los 3 runtimes (`api/executions.py:603`).

Lo que falta es que **sea una superficie de trabajo y no un cajón**:

| Falta hoy | Evidencia |
|---|---|
| Modo pantalla completa | El store sólo tiene 2 estados: `codexConsoleExecutionId` + `codexConsoleMinimized` (`workbench.ts:10-11`). No hay un tercero. |
| Markdown y bloques de código | El dock imprime líneas crudas (`CodexConsoleDock.tsx:242-260`). `ChatDrawer.tsx:10` sí usa `ReactMarkdown`, la consola no. |
| Copiar comando | No hay ningún botón de copia en el dock, pese a existir `services/copyService.ts` (Plan 194). |
| Cancelar / volver a lanzar desde la consola | El endpoint existe (`api/executions.py:603`) y `ActiveRunsPanel.tsx:57-58` ya lo llama; **el dock no**. |
| Búsqueda en la conversación | Ninguna. |
| Historial de sesiones | `api/executions.py:442 /history` existe; la consola no lo consume. **Ojo (D6): está gateado — `:459-461` devuelve 404 `feature_disabled` si `STACKY_EXECUTION_HISTORY_ENABLED` está OFF.** |
| Archivos modificados y diffs | `api/git.py` tiene **26 líneas** y sólo expone `/file-context` y `/context-block`. **No existe `/status` ni `/diff`: este plan los CREA.** |
| Modelo/effort activos a la vista | El trace se persiste (`claude_code_cli_runner.py:543`), la consola no lo muestra. |
| Atajos de teclado propios | Existe el registro (`services/shortcuts.ts`, `hooks/useShortcut.ts:15`, `components/ShortcutsCheatsheet.tsx`); la consola no registra ninguno. |

### 1.2 KPI

| KPI | Antes (medido 2026-07-27) | Después (criterio binario) |
|---|---|---|
| **KPI-1** Estados de presentación de la consola | **2** (normal, minimizada) | **3** (dock, pantalla completa, minimizada) |
| **KPI-2** Clicks para pasar de dock a pantalla completa y volver **sin perder la conversación** | imposible | **1** (y `lines.length` no cambia) |
| **KPI-3** Capacidades de la lista de §1.3 presentes en la consola | **7 / 20** | **20 / 20** |
| **KPI-4** Acciones destructivas de la consola sin confirmación explícita | cancelar no existe en el dock; al agregarla sería 1 | **0** |
| **KPI-5** Endpoints nuevos que escriben algo | — | **0** (todo lo nuevo del backend es de solo lectura, salvo la bitácora local, que no expone escritura por HTTP) |
| **KPI-6** Diffs que salen al navegador con un secreto en claro | sin medir (no hay diffs) | **0** (F4.5) |

### 1.3 Las 20 capacidades — enumeradas (C6)

Esta lista **es** el KPI-3. No hay otra. Un implementador marca 20/20 tildando esta tabla.

| # | Capacidad | Estado hoy | Fase que la cubre |
|---|---|---|---|
| 1 | Streaming en vivo de la corrida | **ya** | — |
| 2 | Estado de la ejecución a la vista | **ya** | — |
| 3 | Logs en tiempo real con niveles | **ya** | — |
| 4 | Reconexión automática del stream | **ya** | — |
| 5 | Persistencia de la sesión tras recargar (F5) | **ya** | — |
| 6 | Visualización de las salidas del agente | **ya** | — |
| 7 | Proyecto activo visible | **ya** | — |
| 8 | Modo pantalla completa sobre la misma sesión | falta | F1 |
| 9 | Markdown y resaltado de bloques de código | falta | F2 |
| 10 | Copiar un bloque / un comando | falta | F2 |
| 11 | Copiar toda la conversación | falta | F2 + F6 |
| 12 | Cancelar la corrida con confirmación | falta | F3 |
| 13 | Volver a lanzar la corrida | falta | F3 |
| 14 | Buscar dentro de la conversación | falta | F5 |
| 15 | Navegar entre resultados (siguiente/anterior con vuelta) | falta | F5 |
| 16 | Historial de sesiones anteriores | falta | F5 |
| 17 | Archivos modificados por el agente | falta | F4 |
| 18 | Diferencias por archivo | falta | F4 |
| 19 | Herramienta / modelo / effort activos a la vista | falta | F2.5 + F5 |
| 20 | Atajos propios documentados en la ayuda existente | falta | F6 |

Garantías transversales (no cuentan como capacidad, pero son DoD): líneas descartadas (`dropped`) a la vista,
bitácora de acciones (F7), enmascarado de secretos (F4.5), matriz de capacidades por runtime (F2.5),
**identidad de sesión como invariante ejecutable (F1.5)** y **ratchet de atajos muertos (F6 test 9)**.

---

## 2. Por qué ahora / gap que cierra

Los planes 255-258 endurecieron lo que pasa **por dentro** de una corrida (fallas mudas, intake, observabilidad,
telemetría veraz). El Plan 200 le dio una consola **por incidencia**. Lo que nunca se hizo es darle al operador
**un lugar donde vivir mientras el agente trabaja**. Hoy, para seguir una corrida, mira una tira de log de 300 px
de alto encima del resto de la app.

Este plan **no construye una consola nueva**. Promueve la que ya existe: el mismo store, el mismo stream SSE, el
mismo `execution_id`. Todo lo que ya entra por `CodexConsoleDock` entra igual — el modo pantalla completa es una
**presentación** del mismo estado, no un componente paralelo. Esa es la decisión de arquitectura central:
**una sola sesión, dos presentaciones**. Un segundo componente con su propio stream duplicaría eventos, rompería
el ring-buffer y desincronizaría el scroll.

---

## 3. Principios y guardarraíles

1. **3 runtimes con paridad — medida, no supuesta (C5).** La consola es agnóstica: renderiza el stream SSE de una
   `AgentExecution`, que los 3 runtimes producen igual (`log_streamer.py`). Los hechos, ya verificados, son:

   | Runtime (`metadata.runtime`) | Cancelación | Evidencia |
   |---|---|---|
   | `codex_cli` | **sí**, mata el subproceso | `services/codex_cli_runner.py:185` `def cancel(execution_id) -> bool` |
   | `claude_code_cli` | **sí**, cierre ordenado de stdin con gracia | `services/claude_code_cli_runner.py:228` |
   | `github_copilot` (y cualquier otro) | **sí, pero cooperativa**: no hay proceso que matar; se marca una bandera en memoria | `api/executions.py:628-640` → `agent_runner.py:550` |

   Conclusión operativa: **el botón Cancelar existe en los 3**. El único gate real es el **estado** de la
   ejecución: `api/executions.py:616` sólo permite cancelar si `status in ("vscode_chat","preparing","queued","running")`,
   y devuelve **409** en cualquier otro caso. Para `github_copilot` la UI debe decir, textualmente,
   *"Cancelación cooperativa: el turno en curso puede tardar en cerrarse."* — **prohibido** un botón que miente
   sobre su efecto, y **prohibido** un botón deshabilitado por una capacidad que sí existe.
   El panel de modelo/effort muestra `effort_mode: "no_aplica"` en GitHub Copilot Pro (contrato del Plan 264);
   si el 264 no está implementado, muestra `"—"` y lo dice.
2. **Cero trabajo extra para el operador.** El dock sigue siendo el default. La pantalla completa es un click (o
   un atajo). Nada obliga a migrar. Las 4 flags nacen **ON** — ninguna cae en (A) ni (B).
3. **Human-in-the-loop.** La consola **no ejecuta nada por su cuenta**. Cancelar pide confirmación. No hay
   auto-reintento: volver a lanzar es un click humano. El panel de repositorio **no puede escribir en el repo del
   operador**: el gate de F4 (test 11) lo hace verificable, no declarativo.
4. **Mono-operador sin auth.** "Permisos y auditoría" se implementa como **bitácora local de acciones de consola**,
   no como RBAC. Se registra qué hizo el operador y cuándo; **no se restringe a nadie y no se usa como control de
   acceso**. Ningún camino de código puede consultar la bitácora para decidir si permite una acción; el test 9 de
   F7 lo verifica.
5. **Backward-compatible.** `codexConsoleMinimized` **se conserva** en el store y se sigue escribiendo: un estado
   persistido de una sesión anterior (o de un deploy viejo) rehidrata sin romper. El campo nuevo es opcional.
6. **No degradar.** El ring-buffer acotado de `useExecutionStream` (`hooks/logRingBuffer.ts`) **no se toca**: la
   pantalla completa muestra las mismas líneas acotadas, no un buffer ilimitado. Sin `setInterval` ni
   `refetchInterval` nuevos — la consola es push (SSE), **no polling**; tampoco el panel de repositorio, que se
   refresca **sólo** por acción explícita del operador o al terminar la corrida (evento del stream), nunca por
   temporizador.
7. **Reusar, no reinventar.** `react-markdown@9` + `rehype-highlight@7` + `highlight.js@11` ya están en
   `frontend/package.json:14,19,20` ⇒ **cero dependencias nuevas**. Se reusan además:
   `services/copyService.ts` (194), `services/shortcuts.ts` + `hooks/useShortcut.ts` (172),
   `useConfirm()` de `components/ui/index.ts:46` (164), `components/ModelDecisionChip.tsx` (212),
   **`api/endpoints.ts:1394` `Executions.cancel`** (D1 — **no** el `:1135`, que es `Agents.cancel`, otra función
   y otro endpoint: ver el aviso al principio de F3), `utils/loadError.ts` `formatLoadErrorMessage`,
   `services/git_context.py:60` `_git()`, y el patrón de subproceso de `services/plans_board.py:665-681`.

---

## 4. Glosario

| Término | Significado |
|---|---|
| **dock** | La presentación actual: barra baja, ~300 px, sobre el resto de la app. |
| **modo principal / pantalla completa** | Presentación nueva: la consola ocupa toda el área útil, con paneles laterales plegables. **Mismo estado, misma sesión.** |
| **presentación** | `"dock" \| "full" \| "minimized"`. Convive con el booleano `codexConsoleMinimized`, que se sigue escribiendo. |
| **sesión de consola** | Un `execution_id` con su stream. Sobrevive al F5 vía `workbench.ts:148-152`. |
| **ring-buffer** | Cota de líneas de `useExecutionStream`; descarta las más viejas y reporta `dropped` (`useExecutionStream.ts:12`). |
| **bitácora de consola** | Registro local append-only de las acciones que el operador dispara desde la consola. **Registro, nunca restricción.** |
| **panel lateral** | Columna plegable del modo principal: Contexto, Repositorio o Historial. |
| **matriz de capacidades** | Tabla pura que, dado `metadata.runtime` y el estado, dice qué puede la consola y **con qué texto lo explica** cuando no puede (F2.5). |
| **enmascarado** | Reemplazo de un secreto detectado por un marcador antes de que salga del proceso Python (F4.5). |

---

## 4.bis Frontera con los planes hermanos 239, 260, 263, 264 y 267 (C15, D7, D14)

Los 4 planes de esta tanda editan los mismos archivos de registro. Git hace 3-way merge **sin marcar conflicto**
cuando dos ramas agregan la misma línea de cierre a una estructura existente: el resultado es un duplicado
silencioso. Reglas de convivencia de **este** plan:

| Archivo compartido | Qué hace el 265 | Regla |
|---|---|---|
| `backend/config.py` | agrega 4 vars con el comentario `# Plan 265` | Insertar **al final** del bloque de flags, en un bloque propio precedido por `# Plan 265 — ...`. Nunca intercalar entre líneas de otro plan. |
| `backend/services/harness_flags.py` | 4 `FlagSpec` + 4 keys en `_CATEGORY_KEYS["interfaz_ui"]` | Los `FlagSpec` van en un bloque propio al final del registry. En `_CATEGORY_KEYS`, las 4 keys van **juntas y al final** de la tupla `interfaz_ui`, cada una con `# Plan 265`. |
| `backend/tests/test_harness_flags.py` | 4 keys en `_CURATED_DEFAULTS_ON` | Bloque contiguo al final del set, con `# Plan 265` en cada línea. |
| `backend/tests/test_harness_flags_requires.py` | 3 aristas en `_REQUIRES_MAP_FROZEN` | Bloque contiguo al final del dict, con comentario `# Plan 265`. |
| `backend/services/harness_flags_help.py` | 4 entradas `PLAIN_HELP` | Bloque contiguo al final del dict. |
| `backend/scripts/run_harness_tests.sh` **y** `.ps1` | 2 archivos de test | Al final de la lista, en el orden `git_readonly`, `console_audit`. **Sintaxis distinta en cada archivo** (array bash vs array PowerShell con comas): no copies una en la otra. |
| `frontend/src/api/endpoints.ts` | 2 lecturas nuevas (`GitReadonly.status`, `GitReadonly.diff`) + 1 (`Console.audit`) | Objeto exportado **nuevo** (`GitReadonly`), no se toca ningún objeto existente. **No se toca `Agents` (`:1120-1140`) ni `Executions` (`:1326`+)**: sólo se **consume** `Executions.cancel` (`:1394`). |

**Dependencias cruzadas declaradas:**

- **265 ↔ 239 — Cockpit DevOps, ya IMPLEMENTADO (D14).** Verificado en la ronda v3 abriendo el documento del 239:
  su alcance es el **rediseño de UX/UI y arquitectura de la información del panel DevOps** (F0..F8, construidas), y
  **no** construye una presentación a pantalla completa de la consola de corridas. **No hay solapamiento ni scope
  creep.** Regla: el 265 **no toca ningún archivo del panel DevOps**; su superficie es `CodexConsoleDock` y los
  servicios `.ts` nuevos. Si al implementar aparece la tentación de "aprovechar y retocar el cockpit", **rechazarla**:
  eso es alcance del 239 y ya está hecho.
- **265 ↔ 267 — el contrato de confirmación (D7). Frontera dura, leerla antes de escribir F3.** El 267 crea el
  **Catálogo único de acciones DevOps** con "tres superficies y **un solo** contrato de confirmación", su F6 se
  llama textualmente *"la consola de acciones del agente (propuesta → confirmación → recibo)"* y su §Reuso dice
  *"**Prohibido** crear un segundo mecanismo de confirmación"*, apoyándose en `confirmGateway`, que **ya existe**
  en `frontend/src/services/entityActions.ts`. El 265 confirma con `useConfirm()`. **No es contradicción si y sólo
  si el reparto queda escrito, y este es el reparto acordado:**

  | Eje | Quién manda | Mecanismo | Por qué |
  |---|---|---|---|
  | Acciones sobre **la corrida** (cancelar, volver a lanzar) | **265** | `useConfirm()` (diálogo canónico, Plan 164) | Es exactamente lo que ya hace `ActiveRunsPanel.tsx:33,:153` para la misma acción sobre la misma entidad. Usar otro mecanismo para cancelar sería **el** segundo mecanismo. |
  | Acciones **DevOps** (deploy, rollback, variables, pipelines) | **267** | `confirmGateway` + catálogo | El 265 **no declara ni ejecuta ninguna acción DevOps**. |

  Regla operativa: **el 265 no agrega ni una sola entrada al catálogo del 267 y no importa `entityActions.ts`.**
  Si el 267 se implementa después y decide absorber "cancelar corrida" en su catálogo, el punto de absorción es
  `services/consoleActions.ts` (F3), que es **puro y de una sola responsabilidad** justamente para que ese
  reemplazo sea un cambio de una capa y no una cirugía. Frontera: **cero líneas de `services/entityActions.ts` en
  el diff del 265.**

- **265 ↔ 263 — `backend/services/plans_board.py`.** El 263 lo reescribe. **El 265 NO lo edita**: sólo **copia** el
  patrón de subproceso de `:665-681` y la constante `_GIT_TIMEOUT_SEC = 5` de `:644` hacia su propio módulo nuevo
  `services/console_repo.py`. Si alguien propone importar desde `plans_board`, **rechazarlo**: acopla dos planes
  que se mergean por separado. Frontera: **cero líneas de `plans_board.py` en el diff del 265**.
- **265 ↔ 264 — `services/claude_code_cli_runner.py`.** El 264 lo edita. **El 265 NO lo edita**: sólo lo **cita**
  como evidencia (`:228` cancelación, `:543` trace). Frontera: **cero líneas de `claude_code_cli_runner.py` en el
  diff del 265**.
- **265 → 264 — la consola es superficie nueva de selección de modelo/effort.** La tesis del 264 es "modelo y
  effort en TODO punto de uso". La consola full-screen que crea este plan **es** un punto de uso nuevo, y por lo
  tanto **el KPI de cobertura del 264 nace incompleto si no la enumera**. Frontera acordada acá, para que el 264
  no tenga que tocar código del 265: **F2.5 expone el seam**
  `getModelEffortSlot(runtime): { supported: boolean; reason: string | null }` y el header del modo `"full"`
  reserva un contenedor con `data-slot="model-effort"`. Mientras el 264 no exista, ese contenedor muestra el
  `ModelDecisionChip` de sólo lectura o `"—"`. **El 265 no implementa el selector**; deja el hueco medido.
- **265 ↔ 260** — sin intersección fuera de los archivos de registro de la tabla de arriba.

**Orden recomendado de merge** (si se mergean varios): 260 → 265 → 263 → 264. Razón: 265 no toca
`PlansBoardPage.tsx` (que 263 y 264 se disputan) y sí toca los registros de flags, así que entrar temprano
minimiza el rebase. Tras **cada** merge: `python -m compileall backend/api backend/services` +
`npx tsc --noEmit` + `pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py` **por archivo**,
para atrapar el duplicado silencioso.

---

## 4.ter Cómo se leen los `archivo:línea` de este documento (D1..D14)

Este plan pasó por **dos** rondas de crítica. La segunda encontró que **un anclaje puede estar en la línea correcta
y aun así ser falso**, porque la línea contiene un símbolo con el **nombre correcto** y la **semántica equivocada**.
Es lo que pasó con `Executions.cancel` (D1): en `api/endpoints.ts:1135` hay, literalmente, un `cancel:` — pero es
`Agents.cancel`, y pega en otro endpoint sin gate de 409.

**Regla para el implementador, no negociable:**

1. Antes de usar un anclaje, **abrilo y leé el símbolo contenedor**, no sólo la línea. Un `cancel:` suelto no dice
   de qué objeto es.
2. Si el plan dice que una función pega en un endpoint, **seguí la URL literal** hasta la ruta de Flask y confirmá
   que el `@bp.<verbo>` y el `url_prefix` del blueprint coinciden.
3. Si un anclaje **no verifica**, **parás y lo reportás en el registro de implementación**. Está explícitamente
   permitido y es lo esperado. **Prohibido** "arreglarlo por tu cuenta" adivinando qué quiso decir el plan: eso es
   exactamente cómo el v2 llegó a mandar la consola al endpoint equivocado.
4. Las líneas derivan con cada commit. Si el número no coincide pero el **símbolo** es inequívoco y único en el
   archivo, seguí con el símbolo y anotá la deriva. Si el símbolo tampoco está, aplicá el punto 3.

**Anclajes verificados en la ronda v3** (abiertos uno por uno, 2026-07-27): los seis lugares de flags, los tres
`cancel` de runtime, `api/executions.py:603/616/628-640/442/459-461`, `api/git.py` (26 líneas, sin `/status` ni
`/diff`), `git_context.py:60`, `plans_board.py:644/665-681`, `models.py:331`, `workbench.ts:10-11/148-152`,
`workbenchPure.ts:7/9-13/21/41`, `shortcuts.ts:13/14/24-37/108-111/124/125/139/143/161/191/225/278`,
`ActiveRunsPanel.tsx:33/58/153/179`, `ui/index.ts:46`, `endpoints.ts:1/1326/1394`, `package.json:14/19/20`,
`ChatDrawer.tsx:10`, `CodexConsoleDock.tsx` (328 líneas), `App.tsx:520/254`, `useExecutionStream.ts:12/23-24`,
`error_fingerprints.json` (`schema_version: 1`, campos `log_pattern`/`killed_by`/`guard_test`).

---

## 5. Fases

### F0 — Flags: las **SEIS** patas, todas nombradas (C1, C2, C3, C4)

> **Aviso al implementador:** el v1 de este plan declaraba "Archivos a editar (2)" y por eso salía ROJO en el
> primer comando. El patrón de flags de Stacky tiene **seis** puntos de edición y **tres de ellos viven en
> `backend/tests/`**. No es opcional: hay tests de igualdad exacta de conjuntos que fallan si falta uno.

**Archivos a editar — los SEIS, con ruta y estructura literal:**

| # | Archivo | Estructura | Ancla |
|---|---|---|---|
| 1 | `Stacky Agents/backend/config.py` | 4 atributos de la clase de config | final del bloque de flags |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | 4 `FlagSpec` en `FLAG_REGISTRY` | final del registry |
| 3 | `Stacky Agents/backend/services/harness_flags.py` | `_CATEGORY_KEYS["interfaz_ui"]` | **`:120`** abre el dict; `"interfaz_ui"` abre en **`:460`** |
| 4 | **`Stacky Agents/backend/tests/test_harness_flags.py`** | `_CURATED_DEFAULTS_ON` (**es un `set`, no una tupla**) | **`:467`** |
| 5 | **`Stacky Agents/backend/tests/test_harness_flags_requires.py`** | `_REQUIRES_MAP_FROZEN` (dict) | **`:120`** |
| 6 | `Stacky Agents/backend/services/harness_flags_help.py` | `PLAIN_HELP` (dict) | final del dict, antes de `def plain_help_for` |

#### F0.1 — `backend/config.py`

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

> **Gotcha de lectura (no negociable):** todo read-site en runtime usa la **instancia**
> `config.config.STACKY_CONSOLE_*`, nunca `getattr` sobre el **módulo** `config`. Sobre el módulo se lee el
> default de clase y la rama OFF **nunca** se ejecuta: falso verde perfecto y el test de flag-OFF pasa mintiendo.

#### F0.2 — `backend/services/harness_flags.py`, los 4 `FlagSpec` (escribilos tal cual, no los resumas)

```python
    # ── Plan 265 — la consola como experiencia principal ──
    FlagSpec(
        key="STACKY_CONSOLE_FULLSCREEN_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
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
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
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
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
        label="Panel de repositorio en la consola",
        description=(
            "Plan 265 — Muestra archivos modificados y sus diferencias, de SOLO "
            "LECTURA, sobre el workspace de la corrida. Sin repositorio, sin git "
            "instalado o si expira el tiempo, el panel lo dice y no rompe nada."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
    FlagSpec(
        key="STACKY_CONSOLE_AUDIT_LOG_ENABLED",
        type="bool",
        default=True,   # Curada en _CURATED_DEFAULTS_ON de tests/test_harness_flags.py.
        label="Bitacora de acciones de la consola",
        description=(
            "Plan 265 — Registra que acciones disparo el operador desde la consola "
            "(cancelar, volver a lanzar, copiar) en el directorio de datos de Stacky. "
            "Es registro, no restriccion: mono-operador, sin RBAC."
        ),
        group="global",
        requires="STACKY_CONSOLE_FULLSCREEN_ENABLED",
    ),
```

> **Por qué el master NO declara `requires`:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` es la raíz. Si declarara
> `requires`, la cadena tendría profundidad 2 y violaría **R4** (profundidad 1), que
> `tests/test_harness_flags_requires.py` verifica. Las 3 hijas apuntan **todas al master**, nunca entre sí.

#### F0.3 — `backend/services/harness_flags.py`, `_CATEGORY_KEYS` (C2, D11)

> **Trampa medida (D11): la tupla `"interfaz_ui"` abre en `:460` y CIERRA EN `:477`.** El `),` que viene después
> (**`:484`**) **no es el suyo**: es el de `"paridad_proveedores"`, que abre en `:478`. Si metés las 4 keys ahí,
> `test_every_registry_flag_is_categorized` **sigue VERDE** (la key está categorizada... en la categoría
> equivocada) y la consola aparece bajo "Paridad de proveedores" en la UI de flags. Falso verde perfecto.
> **Confirmá antes de escribir:** la última línea de `interfaz_ui` hoy es
> `"STACKY_UI_LOG_NOISE_CARD_ENABLED",  # Plan 257 — tarjeta de firmas de log mas repetidas` (`:476`), y la
> siguiente es el `    ),` de `:477`. Insertá **entre esas dos**.

En la tupla `"interfaz_ui"` (abre en `:460`), **al final**, inmediatamente antes del `),` de **`:477`**:

```python
        "STACKY_CONSOLE_FULLSCREEN_ENABLED",    # Plan 265 — consola en pantalla completa
        "STACKY_CONSOLE_RICH_RENDER_ENABLED",   # Plan 265
        "STACKY_CONSOLE_REPO_PANEL_ENABLED",    # Plan 265
        "STACKY_CONSOLE_AUDIT_LOG_ENABLED",     # Plan 265
```

> Si esto falta, `test_every_registry_flag_is_categorized` (`tests/test_harness_flags.py:902`) sale **ROJO**
> con "Keys sin categoría". No hay forma de saltearlo.

#### F0.4 — `backend/tests/test_harness_flags.py`, `_CURATED_DEFAULTS_ON` (C1)

**Archivo: `Stacky Agents/backend/tests/test_harness_flags.py`. Estructura: el `set` que abre en la línea 467.**
Al final del set:

```python
        "STACKY_CONSOLE_FULLSCREEN_ENABLED",    # Plan 265
        "STACKY_CONSOLE_RICH_RENDER_ENABLED",   # Plan 265
        "STACKY_CONSOLE_REPO_PANEL_ENABLED",    # Plan 265
        "STACKY_CONSOLE_AUDIT_LOG_ENABLED",     # Plan 265
```

> **Por qué acá y no en `services/harness_flags.py`:** `_CURATED_DEFAULTS_ON` **no existe** en el módulo de
> servicio. Vive en el archivo de test y `test_default_known_only_for_curated` (`:974`) compara por **igualdad
> exacta de conjuntos** contra `{s.key for s in FLAG_REGISTRY if default_is_known(s)}`, donde
> `default_is_known(spec)` es `spec.default is not None`. Las 4 nacen con `default=True` ⇒ si no entran acá, el
> test falla con "Extras (no curadas)".
>
> **Corolario que ya se cometió antes en el repo:** una flag que nace **OFF** **no debe** escribir
> `default=False`, porque `False is not None` ⇒ `default_is_known=True` ⇒ exigiría estar en el set curado.
> Una flag OFF se declara **omitiendo `default=`**. Acá las 4 son ON, así que las 4 declaran `default=True`
> **y** entran al set. Las dos cosas, siempre juntas.

#### F0.5 — `backend/tests/test_harness_flags_requires.py`, `_REQUIRES_MAP_FROZEN` (C3)

**Archivo: `Stacky Agents/backend/tests/test_harness_flags_requires.py`. Estructura: el `dict` que abre en `:120`.**
Al final del dict, antes del `}`:

```python
    # Plan 265: las 3 hijas de la consola cuelgan del master de pantalla completa
    # (profundidad 1; el master NO declara requires).
    "STACKY_CONSOLE_RICH_RENDER_ENABLED": "STACKY_CONSOLE_FULLSCREEN_ENABLED",
    "STACKY_CONSOLE_REPO_PANEL_ENABLED": "STACKY_CONSOLE_FULLSCREEN_ENABLED",
    "STACKY_CONSOLE_AUDIT_LOG_ENABLED": "STACKY_CONSOLE_FULLSCREEN_ENABLED",
```

> Si esto falta, `test_requires_map_is_frozen` (`:312`) sale **ROJO** con "Drift detectado en el mapa `requires` /
> Extras: [...]". Es igualdad exacta de dicts.

#### F0.6 — `backend/services/harness_flags_help.py`, `PLAIN_HELP` (C4, D10)

`test_plain_help_covers_all_registry_keys` exige una entrada por cada key del registry, y
`test_plain_help_has_no_orphan_keys` exige que no sobre ninguna.

> **Dónde vive el contrato (D10):** las reglas y la denylist **no están en el módulo de servicio**. Viven en
> **`Stacky Agents/backend/tests/test_harness_flags_help.py`**: `JARGON_DENYLIST` en **`:17-20`**, `_KEY_RE` en
> **`:22`**, `_PHASE_RE` en **`:23`**, y las cotas en **`:47-51`**. Leelo antes de escribir texto.

**Las reglas COMPLETAS (el v2 citaba sólo 3 de 6) — todas verificadas por test:**

| Regla | Campo | Test |
|---|---|---|
| `len(what.strip()) >= 10` | `what` | `:47` |
| `len(what) <= 200` | `what` | `:48` |
| `len(on_effect) <= 240` | `on_effect` | `:49` |
| `len(off_effect) <= 240` | `off_effect` | `:50` |
| `len(example) <= 300` | `example` | `:51` |
| los 4 campos **no vacíos** | todos | `:52-53` |
| **empieza con `"Si "`** | `on_effect` **y** `off_effect` | `:59-60` |
| sin jerga de la denylist | todos | `:63-76` |
| sin key `SCREAMING_SNAKE` (`\b[A-Z]+_[A-Z0-9_]+\b`) | todos | `:72-73` |
| sin referencia a fase (`\bF\d`) | todos | `:74-75` |

- `JARGON_DENYLIST` **congelada**: `MCP, TF-IDF, LLM, stdin, stdout, endpoint, frontmatter, prompt, token, regex,
  backend, frontend, gate, hook, runtime`.
- **El match es `\b{term}s?\b`, case-insensitive: el PLURAL cae igual (D10).** "token" **y** "tokens" están
  prohibidos; "gate" **y** "gates"; "hook" **y** "hooks". No lo pluralices para escaparte.
- **Decí "Plan 265", nunca "F4"; decí "herramienta", nunca la palabra prohibida para el motor que corre.**

Entradas a agregar, ya validadas **una por una contra las 10 reglas de arriba en la ronda v3** (usalas tal cual;
si las reescribís, volvé a validar las 10):

```python
    "STACKY_CONSOLE_FULLSCREEN_ENABLED": PlainHelp(
        what="Permite que la consola de corridas ocupe toda la pantalla, con paneles laterales, busqueda y atajos, sobre la misma sesion que la barra de abajo.",
        on_effect="Si la activás: aparece el botón para agrandar la consola, y la conversación se sigue viendo entera al ir y volver, sin perder ni una línea.",
        off_effect="Si la apagás: la consola sigue siendo la barra de abajo de siempre, exactamente como antes. No se pierde nada de lo que ya hacía.",
        example="Es como poner un video en pantalla completa: el video no se reinicia ni cambia, solo lo ves más grande.",
    ),
    "STACKY_CONSOLE_RICH_RENDER_ENABLED": PlainHelp(
        what="Muestra la salida de la consola con titulos, listas y bloques de codigo resaltados, y un boton para copiar cada bloque.",
        on_effect="Si la activás: en pantalla completa la salida se lee con formato y podés copiar un comando entero con un click, sin seleccionarlo a mano.",
        off_effect="Si la apagás: la salida se ve como texto plano, línea por línea. Se lee peor, pero no falta nada.",
        example="Un comando de cinco líneas se copia entero con un click, en vez de arrastrar el mouse y equivocarse en la última.",
    ),
    "STACKY_CONSOLE_REPO_PANEL_ENABLED": PlainHelp(
        what="Muestra en la consola que archivos toco el agente y las diferencias de cada uno, sin salir de la pantalla.",
        on_effect="Si la activás: aparece un panel con los archivos cambiados y, al hacer click, sus diferencias. Solo lee: nunca guarda, deshace ni borra nada.",
        off_effect="Si la apagás: el panel no aparece y hay que mirar los cambios por afuera, con otra herramienta.",
        example="Como mirar la lista de cambios antes de confirmarlos: se lee todo y no se escribe nada.",
    ),
    "STACKY_CONSOLE_AUDIT_LOG_ENABLED": PlainHelp(
        what="Anota en un archivo propio de la aplicacion que acciones disparaste desde la consola y cuando.",
        on_effect="Si la activás: queda anotado cada cancelar, volver a lanzar o copiar, con la fecha y la corrida. Sirve para reconstruir qué pasó y cuándo.",
        off_effect="Si la apagás: no queda anotación y después no vas a poder reconstruir qué acción disparaste ni en qué momento.",
        example="Es una bitácora, no un permiso: anota lo que hiciste, nunca te impide hacerlo ni le pregunta a nadie.",
    ),
```

#### F0.7 — Por qué las 4 nacen ON

Ninguna enciende loop, daemon, barrido, polling ni prefetch: la consola es **push** por SSE y el panel de
repositorio se refresca **sólo** por acción del operador o por el evento de fin de corrida ⇒ **no hay (A)**.
Ninguna escribe en ADO/GitLab/repo remoto/BD del operador, ni despliega, ni borra, ni decide por él ⇒
**no hay (B)**. El panel de repositorio es `git status` + `git diff` de **SOLO LECTURA** con gate verificable
(F4, test 11), y la regla es explícita: *leer un archivo local, calcular, mostrar, diffear o auditar nunca es
excepción*. La bitácora escribe **sólo** en el directorio de datos del propio Stacky.
**Prohibido** justificar un OFF con "default seguro", "por las dudas" o "prerequisito no garantizado".

#### F0.8 — Tests de F0 (D2 — leé el aviso ANTES de correr nada)

> **AVISO MEDIDO (D2). `test_harness_flags_help.py` NO puede salir exit 0, ni entero ni con el `-k` del v2.**
> Medición real de esta ronda (2026-07-27, worktree limpio, **antes** de tocar nada):
>
> ```
> pytest backend/tests/test_harness_flags_help.py -q   ⇒   4 failed, 4 passed
> ```
>
> **Baseline exacto de fallos ajenos — esta es la lista contra la que comparás al terminar:**
>
> | Test | Falla por | Deuda ajena medida |
> |---|---|---|
> | `test_plain_help_covers_all_registry_keys` | **79 keys** del registry sin entrada en `PLAIN_HELP` | `CLAUDE_CODE_CLI_TRUST_*`, `STACKY_DB_COMPARE_*` (19), `STACKY_UI_*` (7), `STACKY_COST_*` (5), `STACKY_TELEMETRY_HARVEST_*` (5), `STACKY_DEVOPS_*` (4), `STACKY_EVAL/EVOLUTION/SQL/QA_UAT/...` |
> | `test_plain_help_fields_non_empty_and_bounded` | `STACKY_DEVOPS_COCKPIT_ENABLED: on_effect > 240 chars` (**316**) | Plan 239 |
> | `test_plain_help_on_off_start_with_si` | entradas ajenas que no empiezan con `"Si "` | varias |
> | `test_plain_help_avoids_jargon_denylist` | **15 violaciones** | `STACKY_PLANS_BOARD_ENABLED` (key SCREAMING_SNAKE), `STACKY_CODE_INTEGRITY_ENABLED` ('backend'×1, 'endpoint'×2, 'gate'×2), `STACKY_EVOLUTION_*` ('prompt'×3, 'token'×1), `STACKY_EVAL_*` ('prompt'×4, 'token'×1) |
>
> Pasan: `has_no_orphan_keys`, `module_is_pure`, `no_runtime_imports_plain_help`, `read_current_exposes_plain_help`.
>
> **Corolario duro: el `-k "covers_all or orphan or bounded or start_with_si or jargon"` del v2 selecciona 5 tests
> de los cuales 4 fallan HOY. No es un criterio binario: es un rojo garantizado.** Este plan **no** lo usa como
> gate y **no** arregla las 79 keys ajenas (es alcance de otro plan).

**Comandos de F0 — dos con exit 0 y uno con comparación de baseline:**

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_help.py" -q   # NO exige exit 0: ver abajo
```

**Gate propio de este plan — el único que SÍ es binario.** Verifica las 4 keys nuevas contra **las 10 reglas** de
F0.6 sin depender de una sola línea de deuda ajena. Pegalo tal cual:

```powershell
& $py -c @"
import re, sys
sys.path.insert(0, r'Stacky Agents\backend')
from services.harness_flags_help import PLAIN_HELP
from tests.test_harness_flags_help import JARGON_DENYLIST, _KEY_RE, _PHASE_RE
KEYS = ['STACKY_CONSOLE_FULLSCREEN_ENABLED','STACKY_CONSOLE_RICH_RENDER_ENABLED',
        'STACKY_CONSOLE_REPO_PANEL_ENABLED','STACKY_CONSOLE_AUDIT_LOG_ENABLED']
bad = []
for k in KEYS:
    e = PLAIN_HELP.get(k)
    if e is None:
        bad.append(f'{k}: SIN entrada'); continue
    if not (10 <= len(e.what.strip()) and len(e.what) <= 200): bad.append(f'{k}: what fuera de 10..200')
    if len(e.on_effect) > 240:  bad.append(f'{k}: on_effect > 240')
    if len(e.off_effect) > 240: bad.append(f'{k}: off_effect > 240')
    if len(e.example) > 300:    bad.append(f'{k}: example > 300')
    if not e.on_effect.startswith('Si '):  bad.append(f'{k}: on_effect no empieza con Si ')
    if not e.off_effect.startswith('Si '): bad.append(f'{k}: off_effect no empieza con Si ')
    for f in (e.what, e.on_effect, e.off_effect, e.example):
        if not f.strip(): bad.append(f'{k}: campo vacio')
        for t in JARGON_DENYLIST:
            if re.search(rf'\b{re.escape(t)}s?\b', f, re.IGNORECASE): bad.append(f'{k}: jerga {t}')
        if _KEY_RE.search(f):   bad.append(f'{k}: key SCREAMING_SNAKE')
        if _PHASE_RE.search(f): bad.append(f'{k}: referencia a fase')
print('OK 4/4' if not bad else 'FALLA: ' + ' | '.join(bad))
sys.exit(1 if bad else 0)
"@
```

**Criterio binario de F0:**

1. `test_harness_flags.py` ⇒ **exit 0**.
2. `test_harness_flags_requires.py` ⇒ **exit 0**.
3. El snippet de arriba ⇒ **exit 0** e imprime `OK 4/4`.
4. `test_harness_flags_help.py` ⇒ **exactamente `4 failed, 4 passed`, los mismos 4 nombres de la tabla de baseline,
   y ni una sola línea del mensaje de error menciona `CONSOLE`.** Si aparece un quinto fallo, o si un mensaje dice
   `STACKY_CONSOLE_*`, **es tuyo**: arreglalo.

**Trabajo del operador: ninguno.**

---

### F1 — Store: la tercera presentación, sin perder la sesión (TDD, lógica pura) — C7

**Objetivo.** KPI-1 y KPI-2: un tercer estado, persistido, sin tocar el `execution_id`.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consolePresentation.ts` — **lógica pura, sin React**
(el repo **no tiene RTL ni jsdom**, así que toda la lógica testeable vive en `.ts` puro).

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

/** ¿Se oculta el chrome de la app (nav, topbar) con esta presentación? */
export function hidesAppChrome(p: ConsolePresentation): boolean;   // true sólo en "full"
```

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consolePresentation.test.ts`
(el directorio `src/services/__tests__/` **ya existe**; es la convención del repo):

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
+  setCodexConsolePresentation: (p) =>
+    set({
+      codexConsolePresentation: p,
+      codexConsoleMinimized: legacyMinimizedFrom(p),   // los dos SIEMPRE en sync
+    }),
```

y en el bloque `partialize` (`workbench.ts:148-152`), agregar
`codexConsolePresentation: state.codexConsolePresentation,`.
**`codexConsoleExecutionId` no se toca: ahí vive la sesión, y es justamente lo que no se puede perder.**

**Rehidratación — el mecanismo REAL (C7).** `workbench.ts` **no tiene** `onRehydrateStorage`. Usa
`migrate: (persisted, fromVersion) => migrateWorkbenchPersist(persisted, fromVersion)` con
`version: WORKBENCH_PERSIST_VERSION`. Los dos viven en
**`Stacky Agents/frontend/src/store/workbenchPure.ts`** (`WORKBENCH_PERSIST_VERSION = 3` en `:7`,
`migrateWorkbenchPersist` en `:21`, y hoy devuelve exactamente
`{ agentRuntime, codexConsoleExecutionId, codexConsoleMinimized }` en `:41`).

> **BLOQUEANTE del v2 que esta versión corrige (D5) — leelo antes de tocar el archivo.** `WorkbenchPersistV3`
> (`workbenchPure.ts:9-13`) **no es sólo el tipo de lo que se lee: es el TIPO DE RETORNO declarado** de
> `migrateWorkbenchPersist` (`:24` → `): WorkbenchPersistV3 {`). El v2 mandaba agregar el campo al objeto leído
> (`prev`, `:25-29`) y al `return`, y **nunca** decía tocar la interfaz. Un object literal con una propiedad de más
> contra un tipo declarado es **TS2353 — "Object literal may only specify known properties"**: `tsc --noEmit`
> **falla**, que es justo el criterio de esta fase. Hay que tocar **tres** cosas, no dos.

Cambios exactos en `store/workbenchPure.ts` — **los CUATRO, en este orden**:

1. `export const WORKBENCH_PERSIST_VERSION = 4;` (bump 3 → 4, línea `:7`).
2. **Nueva interfaz de retorno** (D5). Agregar debajo de `WorkbenchPersistV3`, **sin borrar la vieja** (puede
   tener consumidores; `tsc` te dice si no):
   ```ts
   /** Plan 265 — v4 agrega la presentación de la consola. `codexConsoleMinimized`
    *  se CONSERVA y se sigue escribiendo: un deploy viejo rehidrata sin romper. */
   export interface WorkbenchPersistV4 extends WorkbenchPersistV3 {
     codexConsolePresentation: ConsolePresentation;
   }
   ```
   y cambiar la firma: `): WorkbenchPersistV4 {`.
   > Si `tsc` reporta que `WorkbenchPersistV3` quedó sin uso, **dejala igual**: es el contrato del estado v3 que la
   > migración sigue leyendo. No la borres para "limpiar".
3. Agregar `codexConsolePresentation?: unknown;` al tipo inline del objeto **leído** (`prev`, `:25-29`).
4. En el retorno:
   ```ts
   const presentation =
     fromVersion >= 4
       ? normalizePresentation(prev.codexConsolePresentation)
       : presentationFromLegacy(minimized);   // estado v3 o anterior: se deriva del booleano
   return { agentRuntime: rt, codexConsoleExecutionId: execId, codexConsoleMinimized: minimized, codexConsolePresentation: presentation };
   ```

**Test de regresión obligatorio:** `Stacky Agents/frontend/src/store/workbenchPure.test.ts` **ya existe y debe
seguir verde**, y se le agregan 3 casos:

| # | Caso | Aserción |
|---|---|---|
| 12 | migrar desde `fromVersion: 3` con `codexConsoleMinimized: true` | `codexConsolePresentation === "minimized"` y `codexConsoleExecutionId` **se conserva** |
| 13 | migrar desde `fromVersion: 4` con `codexConsolePresentation: "full"` | `"full"` |
| 14 | migrar desde `fromVersion: 4` con `codexConsolePresentation: "basura"` | `"dock"`, no lanza |

> **Regla de oro de esta fase:** cambiar de presentación **NO** puede tocar `codexConsoleExecutionId`. Si lo tocás,
> el `useExecutionStream` se re-suscribe, el ring-buffer se vacía y el operador pierde la conversación. Eso es
> exactamente lo que KPI-2 mide. Corolario de implementación: el `useExecutionStream` debe vivir en un componente
> que **no se desmonta** al cambiar de presentación — el mismo `CodexConsoleDock`, con dos ramas de render, nunca
> dos componentes distintos montados condicionalmente.

**Comandos de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consolePresentation.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/store/workbenchPure.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 11 passed en el primero, el segundo **verde con sus casos previos + los 3 nuevos**,
`tsc` exit 0.

**Smoke manual (KPI-2, la parte visual):** lanzar una corrida, esperar ≥ 20 líneas, pasar a
pantalla completa, volver a dock, y verificar que **el contador de líneas es el mismo** (la consola muestra
`dropped` y el total; anotá **ambos** números antes y después).
**Pero el invariante ya NO depende de ese conteo manual: lo blinda F1.5.**

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Impacto por runtime:** ninguno (estado de UI).
**Trabajo del operador: ninguno** (el dock sigue siendo el default).

---

### F1.5 — **[ADICIÓN ARQUITECTO]** La identidad de sesión como invariante EJECUTABLE (D12)

**Por qué existe esta fase.** El título de este plan es *"pantalla completa sobre la MISMA sesión"*. Esa es la
tesis entera. Hasta el v2, su **único guardián era un humano contando líneas en el paso 2 del smoke**. Un
invariante central custodiado por el ojo de una persona a las 2 de la mañana no es un invariante: es una
esperanza. Y el modo de falla es silencioso y caro — el operador pierde la conversación de una corrida larga y no
hay forma de recuperarla, porque el ring-buffer vive en memoria.

Esta fase cuesta un archivo puro y un test, y convierte KPI-2 en **binario y automático**. Además cubre los dos
casos borde que el v2 no tenía: **abrir la pantalla completa dos veces** y **la sesión muerta**.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consoleSession.ts` — **lógica pura**:

```ts
import type { ConsolePresentation } from "./consolePresentation";

/** El subconjunto del estado del workbench del que depende la IDENTIDAD de la sesión.
 *  Todo lo demás es presentación. */
export interface SessionBearingState {
  codexConsoleExecutionId: number | null;
  codexConsolePresentation: ConsolePresentation;
  codexConsoleMinimized: boolean;
}

/** Token de identidad de sesión. Dos estados con el MISMO token miran la misma
 *  conversación; el stream no se re-suscribe y el ring-buffer no se vacía.
 *  Deliberadamente NO incluye la presentación: cambiar de presentación no puede
 *  cambiar de sesión. */
export function sessionIdentity(s: SessionBearingState): string;

/** Aplica una transición de presentación sobre el estado. Es el ÚNICO lugar donde
 *  se calcula el próximo estado de consola: el setter del store lo llama y no
 *  hace aritmética propia. Nunca lanza. */
export function applyPresentation(
  s: SessionBearingState,
  next: ConsolePresentation,
): SessionBearingState;

/** ¿Abrir la pantalla completa sobre este estado crea una sesión nueva?
 *  SIEMPRE false mientras haya `codexConsoleExecutionId`. Si es `null` no hay
 *  sesión que preservar y la consola full arranca vacía, que es lo correcto. */
export function opensNewSession(s: SessionBearingState, next: ConsolePresentation): boolean;
```

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consoleSession.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | **Invariante central**: para **las 9 transiciones** (`dock`/`full`/`minimized` × 3 destinos) con `codexConsoleExecutionId: 4242` | `sessionIdentity(applyPresentation(s, next)) === sessionIdentity(s)` en **las 9** |
| 2 | Mismo barrido | `applyPresentation(s, next).codexConsoleExecutionId === 4242` en las 9 (nunca `null`, nunca otro número) |
| 3 | `opensNewSession` con `executionId: 4242` | `false` para los 3 destinos |
| 4 | **Doble apertura** (el caso que el v2 no tenía): `applyPresentation(applyPresentation(s,"full"),"full")` | idéntico a aplicarlo una vez, **y** el token no cambió. Idempotente. |
| 5 | **Sesión muerta**: `codexConsoleExecutionId: null` | `applyPresentation` no lanza, `opensNewSession` es `true`, y el token es estable entre llamadas |
| 6 | Sincronía del legado | `applyPresentation(s,"minimized").codexConsoleMinimized === true`; con `"dock"` y `"full"`, `false` |
| 7 | `sessionIdentity` **no** depende de la presentación | los 3 estados con el mismo `executionId` dan el **mismo** token |
| 8 | `sessionIdentity` **sí** distingue sesiones | `executionId: 1` y `executionId: 2` dan tokens **distintos** |
| 9 | Entrada degenerada (`undefined`, campos faltantes) | no lanza |

> **Ojo con el falso verde del test 7 (esto es una trampa, no un adorno).** Si implementás
> `sessionIdentity` como `() => "x"` —una constante— los tests 1, 4 y 7 salen **verdes** y el invariante no vale
> nada. Por eso **el test 8 es obligatorio y no es opcional**: es el único que obliga a que el token dependa de
> verdad del `executionId`. Test 7 y test 8 se escriben **juntos o ninguno**.

**Cableado (una línea, y es lo que le da valor).** El setter de F1 deja de hacer aritmética propia:

```diff
   setCodexConsolePresentation: (p) =>
-    set({
-      codexConsolePresentation: p,
-      codexConsoleMinimized: legacyMinimizedFrom(p),
-    }),
+    set((state) => applyPresentation(state, p)),
```

Así el invariante que el test blinda es **el mismo código** que corre en producción, no un gemelo que se puede
desincronizar. Un `set` que además tocara `codexConsoleExecutionId` deja de compilar contra `SessionBearingState`.

**Comando:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleSession.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 9 passed, `tsc` exit 0. **Este test, no el conteo manual de líneas, es el gate de KPI-2.**
El paso 2 del smoke se conserva como confirmación visual, no como única evidencia.

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON). **Impacto por runtime:** ninguno (estado de UI puro).
**Trabajo del operador: ninguno.**

---

### F2 — Render rico: markdown, bloques de código y copia de comandos (C12)

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

/** Quita secuencias de escape ANSI (colores) antes de renderizar. Los 3 runtimes
 *  pueden emitir color; en markdown se verían como basura literal. Nunca lanza. */
export function stripAnsi(text: string): string;
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
| 9 | 5000 líneas | termina en < 100 ms (cota medida con `performance.now()`) |
| 10 | `stripAnsi` sobre una línea con `[31mrojo[0m` | devuelve `"rojo"`; sin ANSI, devuelve la línea igual |
| 11 | una línea de 200 000 caracteres sin saltos | no lanza y termina en < 100 ms (salida gigante en una sola línea) |

**Componente.** En el modo pantalla completa, renderizar los chunks con `ReactMarkdown` + `rehype-highlight`
(mismo patrón que `ChatDrawer.tsx:10`) y, en cada chunk `copyable`, un botón de copia que llama a
**`services/copyService.ts`** (Plan 194) — **no** `navigator.clipboard` directo.

> **El dock NO cambia.** El render rico es sólo del modo `"full"`: el dock sigue mostrando líneas crudas, que es
> lo correcto para 300 px de alto y evita re-renders caros en la barra siempre visible. Si
> `STACKY_CONSOLE_RICH_RENDER_ENABLED` está OFF, el modo full también muestra líneas crudas.

> **Presión de render (no degradar).** `groupLinesIntoChunks` se memoiza por `lines.length` y el **último chunk
> (el que está creciendo con el stream vivo) se renderiza CRUDO**; sólo los chunks ya cerrados pasan por markdown.
> Esto acota el trabajo por evento a O(1) en vez de O(n).

**Comando de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRender.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 11 passed, `tsc` exit 0, y **cero** uso directo del portapapeles del navegador en los
componentes de consola — comando exacto (rutas literales, sin globs que puedan no existir):

```bash
grep -c "navigator.clipboard" "Stacky Agents/frontend/src/components/CodexConsoleDock.tsx" || true
```
⇒ imprime **0**. Si se crean componentes de consola adicionales, agregar su ruta literal a este comando.

**Flag:** `STACKY_CONSOLE_RICH_RENDER_ENABLED` (ON).
**Impacto por runtime:** igual en los 3 (renderiza texto del stream, ya sin ANSI).
**Trabajo del operador: ninguno.**

---

### F2.5 — **[ADICIÓN ARQUITECTO]** Matriz de capacidades por runtime: una sola fuente de verdad (C5)

**Por qué existe esta fase.** El v1 dispersaba las decisiones de paridad en tres lugares (§3, F3, F5) y en dos de
ellos las **difería a la implementación** ("verificá si el runtime lo expone"). Eso es exactamente cómo una
consola termina atada al runtime que la inspiró — y el componente se llama `CodexConsoleDock`. Una matriz pura
convierte la paridad en algo **testeable y binario**, y le da al Plan 264 un enchufe limpio.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consoleCapabilities.ts` — **lógica pura**:

```ts
export type RuntimeId = "codex_cli" | "claude_code_cli" | "github_copilot" | "unknown";

export interface ConsoleCapability {
  supported: boolean;
  /** Texto que la UI muestra cuando `supported` es false, o cuando el soporte es
   *  parcial. `null` cuando no hay nada que aclarar. En español, para el operador. */
  note: string | null;
}

export interface ConsoleCapabilities {
  cancel: ConsoleCapability;        // los 3 pueden; copilot es cooperativo
  relaunch: ConsoleCapability;      // depende de que la corrida registre su origen
  modelEffortSlot: ConsoleCapability; // seam del Plan 264
  repoPanel: ConsoleCapability;     // depende del workspace, no del runtime
}

/** Normaliza `metadata.runtime` (que puede venir null, vacío o con un valor futuro). */
export function normalizeRuntime(raw: unknown): RuntimeId;

/** La matriz. Nunca lanza. Un runtime desconocido NUNCA habilita nada por accidente:
 *  degrada con nota explícita. */
export function capabilitiesFor(runtime: RuntimeId, opts: { hasOrigin: boolean }): ConsoleCapabilities;
```

**Contenido de la matriz — escrito, no inferido:**

| Runtime | `cancel.supported` | `cancel.note` |
|---|---|---|
| `codex_cli` | `true` | `null` |
| `claude_code_cli` | `true` | `"Cierre ordenado: el turno en curso termina antes de salir."` |
| `github_copilot` | `true` | `"Cancelación cooperativa: el turno en curso puede tardar en cerrarse."` |
| `unknown` | `true` | `"Herramienta no reconocida: se pide la cancelación igual; puede no tener efecto inmediato."` |

`modelEffortSlot.supported` es `false` en **los 4** mientras el Plan 264 no exista, con
`note: "Selector de modelo y esfuerzo: pendiente del Plan 264."`. **Este plan no implementa el selector.**

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consoleCapabilities.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `normalizeRuntime("codex_cli" / "claude_code_cli" / "github_copilot")` | devuelve el mismo id |
| 2 | `normalizeRuntime(null / "" / 42 / "runtime_del_futuro")` | `"unknown"`, no lanza |
| 3 | **Paridad**: para los 3 runtimes reales, `capabilitiesFor(...).cancel.supported` | `true` en los **3** |
| 4 | `capabilitiesFor("github_copilot", …).cancel.note` | no nulo y contiene la palabra `"cooperativa"` |
| 5 | `capabilitiesFor("unknown", …)` | ninguna capacidad `supported` sin `note`; nada habilitado en silencio |
| 6 | `hasOrigin: false` | `relaunch.supported === false` con `note` no nulo |
| 7 | `modelEffortSlot.supported` | `false` en los 4, con `note` que nombra el Plan 264 |
| 8 | Barrido de completitud | para **cada** `RuntimeId` la matriz devuelve las 4 capacidades definidas (nada `undefined`) |

**Cableado.** El componente lee `metadata.runtime` del payload de `GET /api/executions/<id>`, que **ya lo expone**:
`models.py` `AgentExecution.to_dict` incluye `"metadata": self.metadata_dict`, y `api/executions.py` lo devuelve.
**No hace falta ningún cambio de backend para esto.**

**Comando:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleCapabilities.test.ts
```
**Criterio binario.** 8 passed. El test 3 **es el gate de paridad de los 3 runtimes de todo el plan.**

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON). **Trabajo del operador: ninguno.**

---

### F3 — Cancelar y volver a lanzar, con confirmación (KPI-4) — C8, C14, D1

> ## ⚠ BLOQUEANTE DEL v2, CORREGIDO ACÁ (D1). ESTA ES LA TRAMPA MÁS CARA DEL PLAN. LEELA DOS VECES.
>
> **Hay DOS funciones llamadas `cancel` en `frontend/src/api/endpoints.ts`, en dos objetos distintos, que pegan en
> dos endpoints distintos con semánticas distintas.** El v2 anclaba la equivocada.
>
> | | **`Agents.cancel`** — **PROHIBIDA acá** | **`Executions.cancel`** — **la correcta** |
> |---|---|---|
> | Línea | `api/endpoints.ts:1135-1136` | **`api/endpoints.ts:1394-1395`** (el objeto `export const Executions = {` abre en `:1326`) |
> | Llama a | `POST /api/agents/cancel/<id>` | `POST /api/executions/<id>/cancel` |
> | Backend | `backend/api/agents.py:1434-1436` | `backend/api/executions.py:603` |
> | Qué hace | `agent_runner.cancel(id)` y `return jsonify({"ok": True})`. **Y nada más.** | Valida el estado, **409** si no es cancelable, y despacha al runner que corresponda |
> | Gate de estado | **NINGUNO.** Devuelve `{"ok": true}` sobre una corrida ya terminada. | `:616` — sólo `vscode_chat`/`preparing`/`queued`/`running` |
> | Mata el subproceso | **NO.** Sólo la bandera cooperativa (el camino de `github_copilot`). | **SÍ**: `codex_cli_runner.cancel` mata el subproceso; `claude_code_cli_runner.cancel` cierra ordenado |
> | Tipo de retorno | `{ ok: true }` | `{ ok: boolean; execution_id: number }` |
>
> **Consecuencia de equivocarse:** la consola "cancela" una corrida de Codex y **el proceso sigue vivo**,
> devolviendo `{"ok": true}` para que la UI muestre éxito. `CANCELLABLE_STATUSES` como "espejo del backend"
> (test 9) quedaría verificando un contrato que ese camino **no honra**: verde en el test, mentira en producción.
>
> **Regla:** en este plan, `Agents.cancel` **no se importa, no se llama y no se menciona en el código**. El test 11
> de esta fase lo verifica leyendo el archivo. `ActiveRunsPanel.tsx` ya hace lo correcto: importa `Executions`
> (`:4`) y llama `Executions.cancel(id)` (`:58`).

**Objetivo.** Cerrar el lazo de control **sin agregar un solo endpoint nuevo y sin reinventar el cableado**.

**Sin backend nuevo.** Se usa `POST /api/executions/<id>/cancel` (`api/executions.py:603`). Para volver a lanzar se
usa el endpoint de lanzamiento que corresponda al origen de la corrida — **leé el `metadata` de la ejecución para
saber cuál** (`agent_type`, `runtime`, `vscode_agent_filename`). Si no se puede determinar el origen, el botón
queda **deshabilitado** con el hint *"No se puede volver a lanzar: esta corrida no registra su origen."* — nunca
adivines un endpoint.

> **Rótulo (C14):** el botón nuevo se llama **"Volver a lanzar"**, **no** "Reintentar". El dock ya tiene un botón
> "Reintentar" en `CodexConsoleDock.tsx:235-237` (dentro del bloque `closeState.error` que abre en `:231`, D13)
> que reintenta **cerrar la sesión**. Dos botones con el mismo
> rótulo y semánticas distintas en el mismo componente es una trampa para el operador.

**Reuso obligatorio (C8) — está todo hecho en `components/ActiveRunsPanel.tsx`, copiá de ahí:**

| Qué | Dónde ya está | Regla |
|---|---|---|
| Confirmación | `ActiveRunsPanel.tsx:33` `const askConfirm = useConfirm();` y `:153` `await askConfirm({ … confirmLabel, cancelLabel })` | `useConfirm` se importa de `components/ui` (`components/ui/index.ts:46`). **Prohibido** `window.confirm` y **prohibido** montar `ConfirmDialog` a mano. |
| Llamada | `ActiveRunsPanel.tsx:58` `mutationFn: (id: number) => Executions.cancel(id)` (importa `Executions` en `:4`) | `Executions.cancel` está en **`api/endpoints.ts:1394`** (D1). **No escribas un `fetch` nuevo y NO uses `Agents.cancel` (`:1135`).** |
| Error a la vista | `ActiveRunsPanel.tsx:179-187` | mismo patrón de mensaje + botón de reintento. |

> **Gotcha del 409 (no negociable).** `api/executions.py:616` devuelve **409** si el estado no es cancelable
> (`vscode_chat`, `preparing`, `queued`, `running` son los únicos cancelables). **Medido:** `Executions.cancel`
> (`api/endpoints.ts:1394-1395`) usa `api.post<{ ok: boolean; execution_id: number }>`, y el wrapper `api.*`
> **lanza excepción ante cualquier non-2xx** ⇒ un 409 tumbaría el componente en vez de mostrar el mensaje.
> **Las dos salidas válidas, elegí una y anotala:**
> 1. envolver la llamada en `try/catch` y mostrar el mensaje con `formatLoadErrorMessage`
>    (`utils/loadError.ts`, el mismo que usa `ActiveRunsPanel.tsx:183`); **o**
> 2. usar `rawPost` (ya importado en `api/endpoints.ts:1`) para leer el body del 409.
>
> Lo que **no** se puede es dejar que la excepción suba. Y **no** se puede "resolverlo" cambiando a
> `Agents.cancel` porque ese nunca devuelve 409: eso no es arreglar el error, es **borrar el gate de estado**.

**Archivo a crear:** `Stacky Agents/frontend/src/services/consoleActions.ts` — **lógica pura**:

```ts
export type ConsoleActionId = "cancel" | "relaunch" | "copyAll" | "close";

export interface ExecutionSnapshot {
  status: string | null;          // "running" | "completed" | "error" | "cancelled" | ...
  runtime: string | null;         // metadata.runtime crudo; se normaliza con consoleCapabilities
  hasOrigin: boolean;
}

/** Estados que el backend acepta cancelar. Espejo EXACTO de api/executions.py:616.
 *  Si cambia allá, este set y su test cambian acá: son un contrato. */
export const CANCELLABLE_STATUSES: ReadonlySet<string>;   // {"vscode_chat","preparing","queued","running"}

/** Qué acciones se ofrecen y cuáles quedan deshabilitadas (con motivo). Nunca lanza.
 *  El motivo de `cancel` sale de consoleCapabilities.capabilitiesFor(...).cancel.note. */
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
| 1 | `status: "running"`, `runtime: "codex_cli"` | `cancel` presente y `enabled` |
| 2 | `status: "completed"` | `cancel` presente pero `enabled: false`, `reason` no nulo |
| 3 | `status: "running"`, `runtime: "github_copilot"` | `cancel` **enabled** (paridad) y `reason` contiene `"cooperativa"` |
| 4 | `hasOrigin: false` | `relaunch` `enabled: false` con motivo |
| 5 | `status: null` (deploy viejo / snapshot incompleto) | no lanza; nada queda habilitado por accidente |
| 6 | `requiresConfirmation("cancel")` | `true` |
| 7 | `requiresConfirmation("relaunch" \| "copyAll" \| "close")` | `false` |
| 8 | `confirmationText("cancel", 42)` | contiene `"42"` y la palabra `"cancelar"` |
| 9 | `CANCELLABLE_STATUSES` | exactamente `{"vscode_chat","preparing","queued","running"}` — espejo del backend |
| 10 | sesión zombie: `status: "running"` pero el stream ya emitió `done` | `cancel` sigue `enabled` (el operador tiene que poder cerrar un colgado) |
| 11 | **Gate de endpoint (D1)** | el test **lee** el texto de los componentes y servicios de consola nuevos y falla si aparece `Agents.cancel` o el literal `/api/agents/cancel`. Ese es el camino sin gate de 409. |
| 12 | Sesión **muerta** sin estado: `status: "cancelled"` y el stream cerrado | `cancel` `enabled: false` con motivo, `relaunch` `enabled` si `hasOrigin`; nada lanza |

> **Test 11 — cómo escribirlo sin dispararse en el pie.** Grepea el texto de los archivos **de este plan**
> (`services/console*.ts` y el/los `.tsx` de consola nuevos), **nunca** `api/endpoints.ts` (donde `Agents.cancel`
> vive legítimamente para otros usos) ni `ActiveRunsPanel.tsx`. Y la cadena prohibida va **construida en el test**
> (por ejemplo `"Agents" + ".cancel"`), no escrita literal: si la escribís literal, el propio archivo de test
> matchea su propio gate. Este error ya se cometió varias veces en este repo.

**Comando de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleActions.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```
**Criterio binario.** 12 passed. Y `requiresConfirmation` devuelve `true` para **toda** acción destructiva
⇒ KPI-4 = 0. El test 11 verde ⇒ la consola cancela por el camino **con** gate de estado.

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Impacto por runtime:** los 3 cancelan (F2.5 test 3); `github_copilot` lo hace de forma cooperativa y **lo dice**.
**Trabajo del operador: ninguno.**

---

### F4 — Panel de Repositorio: archivos modificados y diff (SOLO LECTURA) — C11

**Objetivo.** Ver qué tocó el agente sin salir de la consola.

**Archivos backend:**
- **Crear** `Stacky Agents/backend/services/console_repo.py` — toda la lógica de subproceso y validación.
- **Editar** `Stacky Agents/backend/api/git.py` (26 líneas hoy) — **agregar dos rutas NUEVAS**; `/status` y
  `/diff` **no existen**, este plan las **crea**. Las rutas quedan finitas: parsean, delegan, serializan.

**Reuso declarado (C11):** el patrón de subproceso ya existe dos veces en el repo —
`services/git_context.py:60` `_git(args, cwd)` (con `subprocess.check_output`, `stderr` capturado y
`TimeoutExpired` manejado) y `services/plans_board.py:665-681` con `_GIT_TIMEOUT_SEC = 5` (`:644`).
**Copiá el patrón a `console_repo.py`.** **PROHIBIDO editar `plans_board.py`** (archivo compartido con el
Plan 263) y **prohibido importar de él** (acopla dos ramas que se mergean por separado — ver §4.bis).

```python
# services/console_repo.py
_GIT_TIMEOUT_SEC = 5          # mismo criterio que services/plans_board.py:644
_MAX_DIFF_BYTES = 200 * 1024  # cota dura del diff que viaja al navegador

def repo_status(workspace: str) -> dict:
    """git status --porcelain=v1 sobre el workspace de la corrida.
    Devuelve {"ok": bool, "available": bool, "files": [{"path","status"}], "reason": str|None}.
    - `available: False` + `reason` si no hay repositorio, si git no esta instalado,
      o si expira el tiempo. NUNCA lanza. NUNCA escribe."""

def repo_diff(workspace: str, path: str) -> dict:
    """git diff -- <archivo> (unified). Devuelve
    {"ok","available","diff","truncated","masked","reason"}.
    - Cota DURA de 200 KB; mas alla se trunca y `truncated: True`.
    - El texto pasa por el enmascarado de secretos (Plan 265 F4.5) ANTES de volver.
    NUNCA lanza. NUNCA escribe."""
```

```python
# api/git.py — rutas NUEVAS
@bp.get("/status")           # /api/git/status?workspace=<ruta>
@bp.get("/diff")             # /api/git/diff?workspace=<ruta>&path=<archivo>
```

> **Restricción dura de seguridad, no negociable:** las dos funciones construyen el comando como **lista de
> argumentos** (`["git", "status", "--porcelain=v1"]`), con `shell=False`, `cwd` validado y `timeout=5`. Cero
> interpolación de strings del usuario en el comando.
> - `workspace` se valida contra los workspaces conocidos por `project_manager`: una ruta arbitraria se
>   **RECHAZA con 400**. Nunca se ejecuta git en un path que el operador no registró.
> - `path` debe ser **relativo**, sin `..`, y resolver **dentro** del workspace (comparar rutas ya resueltas, no
>   comparar strings).

> **Trampa del gate — leela antes de escribir el código.** El test 11 grepea el **texto** de
> `api/git.py` y `services/console_repo.py` buscando subcomandos de escritura. Si tu docstring dice
> *"nunca hace commit ni push"*, el gate se pone **rojo por la prosa**. Escribí las advertencias como
> *"solo lectura: no modifica el repositorio"*, sin nombrar los subcomandos prohibidos. Este error ya se cometió
> varias veces en este repo.

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan265_git_readonly.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `workspace` no registrado en `project_manager` | HTTP 400, y **git no se ejecutó** (monkeypatch de `subprocess.run`/`check_output` que cuenta llamadas ⇒ 0) |
| 2 | `path` con `..` | HTTP 400, git no se ejecutó |
| 3 | `path` absoluto | HTTP 400, git no se ejecutó |
| 4 | workspace sin repositorio | 200 con `available: False` y `reason` no vacío |
| 5 | git no instalado (`FileNotFoundError` mockeado) | 200 con `available: False`, **no 500** |
| 6 | `TimeoutExpired` mockeado | 200 con `available: False`, `reason` menciona el tiempo agotado |
| 7 | `git status` con salida mockeada de 3 archivos | `len(files) == 3` y cada uno tiene `path` y `status` |
| 8 | diff > 200 KB | `truncated is True` y `len(diff) <= 200*1024` |
| 9 | El comando pasado al subproceso | es una **lista**, y `kwargs.get("shell")` es falsy |
| 10 | Flag `STACKY_CONSOLE_REPO_PANEL_ENABLED = False` (vía `config.config`) | envelope de deshabilitado; git no se ejecutó |
| 11 | **Barrido de escritura** | el test **lee** `api/git.py` y `services/console_repo.py` y falla si aparece cualquiera de los subcomandos de escritura de la lista congelada del propio test |
| 12 | Archivo **binario** en el diff | 200 con `diff` vacío o marcador textual y `reason` explicando que es binario; **no** bytes crudos al navegador |
| 13 | Workspace con una **sesión concurrente** (index bloqueado / `.git/index.lock` presente) | 200 con `available: False` y `reason`; **no** 500, **no** cuelgue (hay worktrees paralelos vivos en este árbol) |

> **Test 11 — hacelo por lista de subcomandos, leyendo los archivos.** Es el guardián de KPI-5: garantiza que este
> plan no introdujo ninguna escritura a git. La lista de subcomandos prohibidos vive **en el test**, no en el
> plan, y si alguna vez hace falta uno nuevo, el test obliga a discutirlo.

**Frontend.** Panel lateral "Repositorio" en modo `"full"`: lista de archivos modificados; al hacer click, el diff
con `ReactMarkdown` + `rehype-highlight` en un fence `diff`. **Reusá el patrón visual de
`components/dbcompare/DiffList.tsx`** si su API sirve; si no, un componente propio simple. **No** agregues una
librería de diff. **Sin polling:** el panel se refresca sólo con el botón "Actualizar" o cuando el stream emite
`done`.

**Lógica pura testeable:** `Stacky Agents/frontend/src/services/consoleRepoPanel.ts` con
`groupFilesByStatus(files)` (agrupa en modificados / nuevos / borrados / sin seguimiento / **otros**) y
`shortPath(path, max)` (elide el medio de una ruta larga). Test
`src/services/__tests__/consoleRepoPanel.test.ts`, 6 casos incluyendo entrada vacía y `status` desconocido (que
debe caer en `"otros"`, nunca perderse).

**Comandos de test:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan265_git_readonly.py" -q
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRepoPanel.test.ts
```
(registrar `tests/test_plan265_git_readonly.py` en **ambas** `HARNESS_TEST_FILES`: `run_harness_tests.sh` **y**
`run_harness_tests.ps1`, con la sintaxis propia de cada una.)

**Criterio binario.** 13 + 6 passed. Test 11 en verde ⇒ **KPI-5 = 0 endpoints de escritura**.

**Flag:** `STACKY_CONSOLE_REPO_PANEL_ENABLED` (**ON** — es solo lectura; la regla dice explícitamente que diffear
y mostrar nunca es excepción).
**Impacto por runtime:** idéntico (lee el workspace, no la herramienta). Sin repositorio degrada a
`available: False` con el motivo a la vista.
**Trabajo del operador: ninguno.**

---

### F4.5 — **[ADICIÓN ARQUITECTO]** Enmascarado de secretos antes de que el diff salga del proceso (KPI-6)

**Por qué existe esta fase.** El v1 abría un endpoint que devuelve el `git diff` de **cualquier archivo** del
workspace registrado. En los repos que Stacky opera hay `.env`, `web.config`, `appsettings.json` y perfiles de
publicación. Un diff de cualquiera de esos manda un PAT, una cadena de conexión o una clave **en claro** al
navegador, y de ahí a la caché del navegador y —peor— a la bitácora de F7 si alguien guarda el `detail`.
Un panel "de solo lectura" que **lee justo lo que no hay que leer** no es inocuo: la restricción de escritura no
protege contra la fuga de lectura. Esta fase la cierra, y es barata.

**Archivo a crear:** `Stacky Agents/backend/services/console_secret_mask.py` — **puro, sin IO**:

```python
def mask_secrets(text: str) -> tuple[str, int]:
    """Reemplaza secretos por un marcador. Devuelve (texto_enmascarado, cantidad).

    Detecta por FORMA, no por nombre de archivo (un secreto en un .cs tambien es
    un secreto): cadenas largas de alta entropia con prefijos conocidos, valores a
    la derecha de una clave cuyo nombre sugiere secreto (password, pwd, secret,
    token, apikey, pat, connectionstring), y cadenas de conexion completas.
    Reemplaza SIEMPRE por el mismo marcador fijo. NUNCA lanza. Idempotente:
    mask_secrets(mask_secrets(x)[0]) == mask_secrets(x)[0].
    """
```

**Orden de aplicación — no negociable:** `git diff` → **`mask_secrets`** → truncado a 200 KB → respuesta HTTP.
Enmascarar **después** de truncar dejaría pasar el secreto que quedó en el corte; enmascarar **después** de
serializar no sirve de nada. Y el gate de F4 test 11 **no** cubre esto: son ejes distintos (escritura vs fuga).

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan265_secret_mask.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | diff con `PASSWORD=Sup3rS3cr3t!` | el valor **no** aparece en la salida; el marcador sí; contador ≥ 1 |
| 2 | diff con una cadena de conexión completa | la contraseña enmascarada, el resto legible |
| 3 | diff con un valor tipo PAT (cadena larga de alta entropía con prefijo) | enmascarado |
| 4 | diff sin secretos | texto **idéntico** al de entrada, contador 0 (cero falsos positivos sobre código normal) |
| 5 | Idempotencia | aplicar dos veces da el mismo resultado |
| 6 | Entrada vacía / `None`-safe | no lanza |
| 7 | **Orden**: `repo_diff` sobre un diff de 300 KB con un secreto en el KB 250 | el secreto **no** viaja aunque el diff se trunque antes; se enmascara primero |
| 8 | 1 MB de diff | termina en < 500 ms (no es un cuello de botella) |

**Cableado.** `services/console_repo.py::repo_diff` llama a `mask_secrets` y devuelve `masked: <int>` en el
envelope. La UI muestra, cuando `masked > 0`, el aviso *"Se ocultaron N valores sensibles en este diff."* —
honestidad, no silencio. `services/console_audit.py` (F7) también pasa cualquier `detail` de texto por
`mask_secrets` antes de escribir.

**Comando:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan265_secret_mask.py" -q
```
(registrar en **ambas** `HARNESS_TEST_FILES`.)

**Criterio binario.** 8 passed ⇒ **KPI-6 = 0**.

**Flag:** `STACKY_CONSOLE_REPO_PANEL_ENABLED` (ON). El enmascarado **no** tiene flag propia: una protección que se
puede apagar por accidente no es una protección. **Trabajo del operador: ninguno.**

---

### F5 — Paneles de Contexto e Historial + búsqueda en la conversación (C10)

**Objetivo.** Cubrir las capacidades que faltan sin endpoints nuevos.

**(a) Panel "Contexto"** — todo de datos que ya existen:
- proyecto y entorno activos: `store/workbench` + `api/projects`;
- **herramienta** activa: `metadata.runtime`, normalizada con `consoleCapabilities.normalizeRuntime` (F2.5);
- modelo / effort activos: `metadata["model_effort"]` (**Plan 264 F4**), renderizado con
  `formatModelEffortTrace` (**Plan 264 F6**) y `ModelDecisionChip` (`components/ModelDecisionChip.tsx`, Plan 212);
- estado de ejecución y duración: de `GET /api/executions/<id>`;
- líneas descartadas por el ring-buffer: el `dropped` que `useExecutionStream` ya expone
  (`hooks/useExecutionStream.ts:12`) — mostrarlo es honestidad, no adorno.

> **Dependencia declarada (C10):** el bloque de modelo/effort necesita el trace de los 3 runtimes que construye el
> **Plan 264** (no el 261 — el 261 **no existe**, es un hueco de numeración). Si el 264 no está implementado, esta
> parte muestra sólo lo que hay para Claude y **lo dice** (`"—"` más la `note` de
> `capabilitiesFor(...).modelEffortSlot`), no inventa. Es degradación explícita, no bloqueo. El contenedor
> `data-slot="model-effort"` queda reservado para que el 264 lo llene sin tocar este código (§4.bis).

**(b) Panel "Historial"** — consume `GET /api/executions/history` (`api/executions.py:442`), ya existente. Click en
una corrida ⇒ `setCodexConsoleExecution(id)`. **Sin polling nuevo:** se carga al abrir el panel y con un botón
"Actualizar".

> **Gotcha del 404 que el v2 no vio (D6) — es el gemelo exacto del gotcha del 409 de F3.** Ese endpoint **está
> gateado**: `api/executions.py:459-461` hace
> `if not getattr(_cfg, "STACKY_EXECUTION_HISTORY_ENABLED", True): return jsonify({"error": "feature_disabled", ...}), 404`.
> Es una flag real y apagable del registry (`services/harness_flags.py:1896`), **ajena a este plan**. Y `api.get`
> **lanza ante non-2xx** ⇒ con esa flag OFF, el panel Historial **tumba la consola entera**, que es justo la
> pantalla que este plan promueve a experiencia principal.
> **Obligatorio:** leer el historial con **`rawGet`** (ya importado en `api/endpoints.ts:1`) o envolver en
> `try/catch`, y ante 404 `feature_disabled` **degradar con motivo visible**:
> *"Historial no disponible: la capacidad está desactivada en la configuración."* Nunca una pantalla en blanco,
> nunca una excepción que suba. Es el mismo trato que R7 le da a la dependencia del Plan 264.
>
> **Lógica pura testeable de la degradación:** agregar a `services/consoleHistoryPanel.ts`
> `historyPanelState(res: { status: number; body: unknown }): { available: boolean; reason: string | null; items: unknown[] }`,
> con **4 casos** en `src/services/__tests__/consoleHistoryPanel.test.ts`: 200 con items; **404 `feature_disabled`
> ⇒ `available: false` con motivo no vacío**; 500 ⇒ `available: false` con motivo; body basura ⇒ no lanza.

**(c) Búsqueda en la conversación** — puramente cliente, sobre las líneas ya en memoria.
`Stacky Agents/frontend/src/services/consoleSearch.ts`:

```ts
export interface SearchHit { lineIndex: number; start: number; end: number; }

/** Busca `query` en las líneas. Case-insensitive. `query` vacío -> []. Nunca lanza.
 *  `query` se trata como TEXTO LITERAL, no como expresión de búsqueda avanzada (una
 *  entrada inválida del operador no puede romper la consola, y un comodín no puede
 *  colgarla). */
export function searchLines(lines: LogLine[], query: string): SearchHit[];

/** Índice del hit siguiente/anterior, con vuelta al principio. Lista vacía -> null. */
export function nextHit(hits: SearchHit[], current: number | null): number | null;
export function prevHit(hits: SearchHit[], current: number | null): number | null;
```

Test `src/services/__tests__/consoleSearch.test.ts`, **9** casos: query vacía, sin hits, múltiples hits en una
línea, case-insensitive, caracteres especiales de búsqueda (`.*`, `[`, `(`) tratados como literales, vuelta al
principio de `nextHit`/`prevHit`, `current: null`, 5000 líneas en < 100 ms, y una línea de 200 000 caracteres
(salida gigante) sin colgar.

**Comandos de test:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleSearch.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Criterio binario.** 9 passed, `tsc` exit 0, y **cero** `setInterval`/`refetchInterval` nuevos. Comando exacto
(C12 — rutas literales, no globs que puedan no existir):

```bash
grep -c -E "setInterval|refetchInterval" "Stacky Agents/frontend/src/components/CodexConsoleDock.tsx" || true
for f in "Stacky Agents/frontend/src/services/"console*.ts; do echo "$f: $(grep -c -E "setInterval|refetchInterval" "$f" || true)"; done
```
⇒ **0** en todos. (`grep -c` sale con código 1 cuando cuenta 0; el `|| true` evita que el comando "falle" por eso.
Lo que se evalúa es el **número impreso**, no el exit code.)

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Impacto por runtime:** igual en los 3.
**Trabajo del operador: ninguno.**

---

### F6 — Atajos de teclado, con el contrato REAL del registro (C9)

**Objetivo.** Que la consola sea usable sin mouse, y que sus atajos **aparezcan en la ayuda que ya existe**
(`components/ShortcutsCheatsheet.tsx`, Plan 172).

**El contrato real del registro — no lo inventes (C9).** En `Stacky Agents/frontend/src/services/shortcuts.ts`:

- `ShortcutDef` (`:24-37`) tiene **`id`**, **`combo`** (string tipo `"Ctrl+K"`), **`scope`**, **`category`**,
  **`description`** y `handler`. **No existe `keys` ni `label`.**
- `ShortcutScope = "global" | "page" | "dialog"` (`:13`).
- `ShortcutCategory = "global" | "navegacion" | "listas"` (`:14`). **Usá `"global"`**: agregar una categoría
  obliga a tocar el tipo unión y `groupForOverlay` (`:161`), que es alcance de otro plan.
- Ya existe **`detectCollisions(defs): string[][]`** (`:139`) y `assertNoRuntimeCollisions()` (`:278`).
  **No grepees a mano: usalos como test — pero leé la limitación medida de abajo (D4).**
- Combos ya tomados, medidos: **`Ctrl+K`** (`palette.toggle`), **`?`** (`help.shortcuts`), **`Ctrl+/`**
  (`nav.toggle-board`) en `CORE_SHORTCUT_DEFS` (**`:191-221`**, D13); y con `scope: "page"` y `displayOnly`:
  `J`, `K`, `Home`, `End`, `Enter`, `Escape` en `LIST_NAV_DISPLAY_DEFS` (**`:225-232`**, D13).

> **La regla que este repo aprendió tres veces por las malas (C9 y D3).**
> `comboAllowedInEditable(combo)` (`shortcuts.ts:108-111`) devuelve **`parseCombo(combo).ctrl`**, y
> `shortcuts.ts:125` lo aplica: `if (ctx.editable && !comboAllowedInEditable(d.combo)) return false;`.
> **Con foco en un `<input>` o `<textarea>`, SÓLO disparan los combos con Ctrl.** Todo lo demás está muerto ahí.
> - El **v1** registró `Enter`/`Shift+Enter` en el registro global para navegar resultados: muerto, porque el foco
>   está en la caja de búsqueda. Lo arregló el v2 (C9).
> - El **v2** dejó **`Escape`** en el registro global para salir de pantalla completa: `parseCombo("Escape").ctrl`
>   es **`false`** ⇒ **igual de muerto**, y en el escenario más probable de todos, porque el propio plan manda
>   `Ctrl+Shift+F` a poner el foco en ese input. Lo arregla el **v3** (D3).
> - Los tests de `shouldHandleEscape` **no pueden atrapar esto**: son de una función pura que nunca ve
>   `comboAllowedInEditable`. Salen verdes con el atajo muerto. Por eso nace el **test 9**, que sí lo atrapa.

**Atajos, con la resolución de cada colisión ya tomada (v3):**

| `combo` | Acción | `scope` | Dónde se implementa | Colisión / motivo |
|---|---|---|---|---|
| `Ctrl+Shift+Enter` | Alternar dock ↔ pantalla completa | `global` | registro (`useShortcut`) | libre. **`Ctrl+\`` se descarta (D9):** `parseCombo` compara `normalizeKey(ev.key)` y en layouts español (es-AR/es-ES, que es lo que corre esta máquina) la backtick es **tecla muerta** — el atajo podría no existir para el operador. Alfanumérico es inequívoco en cualquier layout. |
| `Ctrl+Shift+F` | Foco en la búsqueda de la conversación | `global` | registro (`useShortcut`) | **`Ctrl+F` se descarta**: es la búsqueda nativa del navegador y pisarla enoja al operador. Tiene Ctrl ⇒ vive con foco en un input. |
| `Ctrl+Shift+C` | Copiar toda la conversación | `global` | registro (`useShortcut`) | libre. Tiene Ctrl ⇒ vive con foco en un input. |
| `Escape` | De `"full"` a `"dock"` | — | **`onKeyDown` local del contenedor de la consola full**, con guarda `shouldHandleEscape(presentation)`. **NO va al registro (D3).** | Muerto en el registro con foco en un input. Además el diálogo canónico (`components/ui/dialogKeyboard.ts`) y `LIST_NAV_DISPLAY_DEFS` (`scope:"page"`) también usan `Escape`: **el diálogo gana siempre** — si hay un diálogo abierto, su propio manejador ya consumió el evento antes de llegar al contenedor. |
| `Enter` / `Shift+Enter` | Siguiente / anterior resultado | — | **`onKeyDown` local del `<input>` de búsqueda**, con `preventDefault()`. **NO va al registro.** | n/a |

Los **3** del registro se declaran en `Stacky Agents/frontend/src/services/consoleShortcuts.ts` como
`CONSOLE_SHORTCUT_DEFS: CoreShortcutSpec[]` (`shortcuts.ts:45` — `Omit<ShortcutDef,"handler">`, el mismo tipo de
`CORE_SHORTCUT_DEFS` que usa `App.tsx:254`), con `category: "global"`, `description` en español, y se registran con
`useShortcut` — **nunca** con un `addEventListener` propio.

> **No declares `allowInDialog` (D8).** El registro **ya** trae la guarda de diálogo: `shortcuts.ts:41` lleva
> `dialogOpen` en el contexto y `:124` hace `if (ctx.dialogOpen && !d.allowInDialog) return false;`, con
> `allowInDialog` **falsy por default** (documentado en `ShortcutDef:38-39`: *"Por default un atajo NO dispara con
> un diálogo abierto"*). El v2 pedía una `shouldHandleEscape({presentation, dialogOpen})` **sin decir nunca de
> dónde salía ese booleano**, cuando la respuesta es: **de ningún lado, porque el registro ya lo resuelve**.
> En el v3, `shouldHandleEscape` recibe **sólo** `presentation`. Un segundo canal de "hay un diálogo abierto" sería
> exactamente la clase de duplicación que este plan promete no crear.

**Test PRIMERO:** `Stacky Agents/frontend/src/services/__tests__/consoleShortcuts.test.ts`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `CONSOLE_SHORTCUT_DEFS` | cada entrada tiene `id`, `combo`, `scope`, `category` y `description` no vacía (**los nombres reales del contrato**) |
| 2 | Categoría | `category` de todas ∈ `{"global","navegacion","listas"}` (no se inventa una nueva) |
| 3 | **Colisiones same-scope, con la función real** | `detectCollisions([...CORE_SHORTCUT_DEFS, ...LIST_NAV_DISPLAY_DEFS, ...CONSOLE_SHORTCUT_DEFS])` devuelve **`[]`** |
| **3-bis** | **Colisiones CROSS-scope (D4) — el gate que faltaba** | agrupar los 3 arrays por **`combo.toLowerCase()` SOLO**, ignorando `scope`. Todo grupo con más de un `id` debe figurar en un mapa congelado `_CROSS_SCOPE_RESUELTAS` **escrito en el test**, con la resolución en prosa. Un duplicado nuevo no declarado ⇒ **ROJO**. |
| 4 | Sin `Ctrl+F` | ningún `combo` es exactamente `"Ctrl+F"` (se reserva la búsqueda del navegador) |
| 5 | `Enter` y `Escape` fuera del registro | ningún `combo` del array es `"Enter"`, `"Shift+Enter"` ni `"Escape"` (viven en `onKeyDown` locales — D3) |
| 6 | `shouldHandleEscape("full")` | `true` |
| 7 | `shouldHandleEscape("dock")` y `shouldHandleEscape("minimized")` | `false` |
| 8 | `shouldHandleEscape` con basura (`undefined`, `"otra"`) | `false`, no lanza |
| **9** | **[ADICIÓN ARQUITECTO] Ratchet de atajos muertos (D3)** | para **cada** entrada de `CONSOLE_SHORTCUT_DEFS`: `comboAllowedInEditable(def.combo) === true`. Ninguna excepción, ninguna allowlist. |
| 10 | Sin backtick (D9) | ningún `combo` contiene el carácter `` ` `` (tecla muerta en layouts español) |

> **Por qué el test 3 SOLO no alcanza (D4) — medido, no supuesto.** `detectCollisions` (`shortcuts.ts:139`) arma su
> clave así (`:143`):
> ```ts
> const clave = `${parseCombo(d.combo).key}|${d.combo.toLowerCase()}|${d.scope}`;
> ```
> **Incluye `scope`.** Un `Escape` con `scope:"global"` y el `Escape` de `LIST_NAV_DISPLAY_DEFS` con
> `scope:"page"` (`:230`) caen en claves **distintas** ⇒ `detectCollisions` devuelve `[]` **con la colisión
> presente**. Y el diálogo canónico (`components/ui/dialogKeyboard.ts`) **no está en ninguno de los tres arrays**,
> así que esa función no puede verlo ni en principio. El v2 declaraba el test 3 "**el** gate de colisiones,
> binario y automático" y R5 apoyaba ahí una mitigación de riesgo **Alto**: la afirmación era falsa.
> El test **3-bis** cierra el hueco obligando a que cada duplicado cross-scope esté **escrito y justificado**,
> no descubierto en el smoke.

> **Por qué el test 9 es la adición más barata y más valiosa de esta fase.** Este repo ya perdió dos rondas de
> crítica con el mismo bug (C9: `Enter`; D3: `Escape`). No es mala suerte: es que **un atajo muerto pasa todos los
> tests unitarios**, porque lo que lo mata vive en el dispatcher (`shortcuts.ts:125`) y no en el atajo. El test 9
> convierte "acordate de `comboAllowedInEditable`" en un **gate que no se puede olvidar**: si alguien agrega
> mañana `Ctrl`-less al registro de la consola, sale rojo antes de llegar al smoke. Cuesta 3 líneas.
> **Corolario de diseño, no de test:** en la consola, **todo lo que va al registro global lleva Ctrl; todo lo que
> no lleva Ctrl va a un `onKeyDown` local.** Esa es la regla, y el test 9 es su guardián.

**Comando:**
```powershell
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleShortcuts.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/shortcuts.test.ts
```
**Criterio binario.** **11 passed** (1, 2, 3, 3-bis, 4..10) + el test de atajos existente **sigue verde**
(regresión del Plan 172). Los gates de colisión son el **3 (same-scope) y el 3-bis (cross-scope)**, los dos
binarios y automáticos; el gate de atajos vivos es el **9**.

**Flag:** `STACKY_CONSOLE_FULLSCREEN_ENABLED` (ON).
**Trabajo del operador: ninguno** (los atajos se documentan solos en el cheatsheet existente).

---

### F7 — Bitácora de acciones de consola (auditoría local, mono-operador)

**Objetivo.** Cubrir "permisos, seguridad y auditoría" como corresponde a un sistema **mono-operador**:
**registrar**, no restringir.

**Archivo a crear:** `Stacky Agents/backend/services/console_audit.py`.

```python
def record_console_action(*, execution_id: int, action: str, detail: dict | None = None) -> bool:
    """Append-only al archivo de bitacora en el directorio de datos de Stacky.

    - Ruta via runtime_paths.data_dir() (NUNCA __file__): valida en dev y en el
      deploy congelado PyInstaller.
    - Una linea JSON por accion: {"ts","execution_id","action","detail"}.
    - `action` se valida contra una allowlist: {"cancel","relaunch","copy_all","open_full","close"}.
      Un valor fuera de la lista se descarta y devuelve False (no se escribe basura).
    - Todo valor de texto de `detail` pasa por console_secret_mask.mask_secrets
      antes de escribirse (Plan 265 F4.5).
    - Rotacion: si el archivo supera 5 MB, se renombra a .1 y se empieza de nuevo
      (maximo 2 archivos). Nada crece sin techo.
    - Devuelve False (sin lanzar) ante cualquier error de I/O o con la flag apagada.
      La auditoria NUNCA puede romper una accion del operador.
    """

def read_console_audit(limit: int = 200) -> list[dict]:
    """Ultimas N entradas, mas nuevas primero. [] ante cualquier problema."""
```

Endpoint de **lectura**: `GET /api/executions/console-audit?limit=N` en `api/executions.py`. La escritura se
dispara desde los handlers de cancel / volver a lanzar ya existentes; **no** se expone un endpoint de escritura de
bitácora (KPI-5).

**Test PRIMERO:** `Stacky Agents/backend/tests/test_plan265_console_audit.py`:

| # | Caso | Aserción |
|---|---|---|
| 1 | `record` + `read` round-trip | la entrada aparece con `action` y `execution_id` |
| 2 | `action` fuera de la allowlist | `False`, nada escrito |
| 3 | Directorio no escribible (mock `OSError`) | `False`, **no lanza** |
| 4 | Rotación a los 5 MB | existe el `.1` y el principal arranca de cero; nunca hay un tercer archivo |
| 5 | Flag `STACKY_CONSOLE_AUDIT_LOG_ENABLED = False` (vía `config.config`) | `record` devuelve `False`, `read` devuelve `[]` |
| 6 | `read_console_audit` con una línea corrupta (JSON inválido) en el medio | las demás se devuelven; no lanza |
| 7 | `detail` con un valor no serializable | se descarta ese campo, la entrada se escribe igual |
| 8 | **Aislamiento** | el test usa `tmp_path` monkeypatcheando `runtime_paths.data_dir` y **asserta que el archivo REAL de datos no se creó ni cambió** |
| 9 | **La bitácora no restringe** | el test lee el código de `services/console_audit.py` y de `api/executions.py` y verifica que **ningún camino** consulte `read_console_audit` para decidir si permite una acción: la bitácora es registro, nunca control de acceso (principio §3.4) |
| 10 | `detail` con un secreto | la línea escrita **no** contiene el valor en claro (F4.5 aplicado) |

> **Test 8 es obligatorio.** Ya pasó en este repo que un test escribiera en el **perfil REAL** del operador
> (Plan 216). Monkeypatcheá `runtime_paths.data_dir` y asertá sobre el path real.
> **Test 9 es el que hace verdadera la promesa de mono-operador**: sin él, "es registro, no restricción" es
> prosa. Con él, es un gate.

**Comando:**
```powershell
"Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest "Stacky Agents\backend\tests\test_plan265_console_audit.py" -q
```
(registrar en **ambas** `HARNESS_TEST_FILES`.)

**Criterio binario.** 10 passed.

**Flag:** `STACKY_CONSOLE_AUDIT_LOG_ENABLED` (**ON** — escribe sólo en el directorio de datos del propio Stacky,
no en un sistema del operador; es registro, no acción).
**Impacto por runtime:** idéntico (registra acciones del operador, no de la herramienta).
**Trabajo del operador: ninguno.**

---

### F8 — Cierre y verificación consolidada

```powershell
$py = "Stacky Agents\backend\.venv\Scripts\python.exe"
& $py -m pytest "Stacky Agents\backend\tests\test_plan265_git_readonly.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan265_secret_mask.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_plan265_console_audit.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_requires.py" -q
& $py -m pytest "Stacky Agents\backend\tests\test_harness_ratchet_meta.py" -q
& $py -m compileall -q "Stacky Agents\backend\api" "Stacky Agents\backend\services"
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consolePresentation.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleSession.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/store/workbenchPure.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRender.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleCapabilities.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleActions.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleRepoPanel.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleHistoryPanel.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleSearch.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/__tests__/consoleShortcuts.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/services/shortcuts.test.ts
cd "Stacky Agents\frontend"; npx vitest run src/__tests__/uiDebtRatchet.test.ts
cd "Stacky Agents\frontend"; npx tsc --noEmit
```

**Son 20 comandos y TODOS deben salir exit 0.** Los de vitest se corren **uno por archivo** (la corrida completa
contamina cross-file en este repo). Los de pytest, también por archivo.

**Más el gate propio de la ayuda llana (F0.8), que es el snippet de 4 keys — exit 0 e imprime `OK 4/4`.**

> **Lo que se SACÓ de esta lista y por qué (D2).** El v2 incluía acá
> `pytest test_harness_flags_help.py -q -k "covers_all or orphan or bounded or start_with_si or jargon"` y
> declaraba "19 comandos exit 0". **Medido: 4 de los 5 tests que ese `-k` selecciona fallan HOY por deuda ajena**
> (79 keys del registry sin ayuda, `STACKY_DEVOPS_COCKPIT_ENABLED` con `on_effect` de 316 chars, 15 violaciones de
> jerga). Ese comando **no puede** salir exit 0 y el DoD era insatisfacible. En su lugar:
> - el **gate binario de lo tuyo** es el snippet de F0.8 (mira sólo las 4 keys `STACKY_CONSOLE_*`);
> - el archivo completo se corre **aparte, como comparación de baseline**, no como exit 0:
>   ```powershell
>   & $py -m pytest "Stacky Agents\backend\tests\test_harness_flags_help.py" -q
>   ```
>   ⇒ debe seguir dando **`4 failed, 4 passed`**, los **mismos 4 nombres** de la tabla de F0.8, y **ninguna línea
>   de error que mencione `CONSOLE`**.
>
> Esta es la regla general del repo: **una deuda ajena nunca se usa como gate propio, y un plan nunca declara
> exit 0 sobre un archivo que ya está rojo.** Si querés arreglar las 79 keys, es otro plan.

**Smoke manual obligatorio (no automatizable — el repo no tiene RTL ni jsdom).** Anotá cada resultado en el
registro de implementación al final de este documento:

1. Lanzar una corrida real; esperar ≥ 20 líneas.
2. `Ctrl+Shift+Enter` ⇒ pantalla completa. **Contar las líneas y el `dropped`: mismos números.** Volver a dock:
   mismos números. (KPI-2 — confirmación visual; el gate automático es F1.5)
2-bis. **Abrir la pantalla completa DOS veces seguidas** (atajo + botón) ⇒ nada cambia, no se duplica el stream,
   el contador de líneas sigue igual. (F1.5 test 4)
3. F5 con la consola en pantalla completa ⇒ rehidrata en pantalla completa, misma corrida (migración v3→v4).
4. Buscar una palabra que aparezca 3 veces ⇒ 3 hits; `Enter` cicla con vuelta al principio **con el foco dentro
   de la caja de búsqueda** (es el caso que el v1 rompía).
4-bis. **Con el foco TODAVÍA dentro de la caja de búsqueda, apretar `Escape`** ⇒ vuelve al dock. **Este es el paso
   que el v2 habría fallado** (D3): con `Escape` en el registro global no pasa nada, porque
   `comboAllowedInEditable("Escape")` es `false`. Si no vuelve al dock, F6 **no está hecha**.
5. Panel Repositorio ⇒ archivos modificados; abrir un diff. Abrir el diff de un archivo de configuración con una
   clave ⇒ **aparece el aviso de valores ocultos y el valor no se ve**. (KPI-6)
6. Cancelar ⇒ aparece el diálogo de confirmación; confirmar ⇒ la corrida pasa a cancelada.
7. Cancelar una corrida **ya terminada** ⇒ mensaje de error a la vista, **la consola no se rompe** (el 409 no
   sube como excepción).
7-bis. **Apagar `STACKY_EXECUTION_HISTORY_ENABLED`** (flag AJENA, `harness_flags.py:1896`) y abrir el panel
   Historial ⇒ **aparece el motivo escrito y la consola NO se rompe** (D6). Volver a encenderla.
8. `GET /api/executions/console-audit` ⇒ la acción `cancel` está registrada.
9. **Paridad:** repetir los pasos 2, 4 y 6 con una corrida de **cada uno de los 3 runtimes**
   (`codex_cli`, `claude_code_cli`, `github_copilot`). Anotar el texto que muestra el botón Cancelar en cada uno.
   **Y en `codex_cli`, después de cancelar, confirmar que el proceso murió de verdad** (no quedó vivo devolviendo
   `ok: true`) — es lo que distingue el endpoint correcto del equivocado (D1).
10. Apagar `STACKY_CONSOLE_FULLSCREEN_ENABLED` ⇒ el dock sigue funcionando **exactamente** como antes.

**Criterio binario.** **20 comandos exit 0** + el snippet de F0.8 en `OK 4/4` + `test_harness_flags_help.py` con el
**baseline idéntico** (`4 failed, 4 passed`, sin `CONSOLE`) + los **12** pasos del smoke (1, 2, 2-bis, 3, 4, 4-bis,
5, 6, 7, 7-bis, 8, 9, 10) con resultado esperado anotado.
**Trabajo del operador: ninguno.**

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| **R1** | Cambiar de presentación re-suscribe el SSE y **borra la conversación**. | **Alta** (es el fallo natural) | `codexConsoleExecutionId` **no se toca** al cambiar de presentación; el `useExecutionStream` vive en un componente que no se desmonta (dos ramas de render, no dos componentes). **El gate ya no es un humano contando líneas (D12): es F1.5**, cuyo test 1 barre las 9 transiciones y exige token de sesión idéntico, y cuyo cableado hace que el setter del store llame a la MISMA función pura que el test blinda. El paso 2 del smoke queda como confirmación visual. |
| **R2** | Renderizar markdown de un stream vivo re-renderiza todo en cada línea y la consola se traba. | **Alta** | El render rico es **sólo** del modo `"full"` (el dock queda crudo). `groupLinesIntoChunks` memoizado por longitud; **el último chunk, el que crece, se rendea crudo**. Tests 9 y 11 de F2 ponen la cota de 100 ms sobre 5000 líneas y sobre una línea de 200 000 caracteres. |
| **R3** | El endpoint de git ejecuta un comando en una ruta arbitraria (inyección / traversal). | Media | Validación de `workspace` contra `project_manager`, `path` relativo sin `..` **resuelto** dentro del workspace, comando por **lista**, `shell=False`, timeout 5 s. Tests 1, 2, 3 y 9 de F4 lo cubren, y el test 1 verifica que git **no se ejecutó**. |
| **R4** | El panel de repo cuelga la UI en un repo grande. | Media | Timeout duro de 5 s, cota de 200 KB de diff, `truncated` visible. Sin repositorio degrada a `available: False`. Sin polling: refresco sólo por acción o por fin de corrida. |
| **R5** | Los atajos nuevos pisan atajos existentes (Plan 172) o el `Escape` del diálogo (Plan 164). | **Alta** | Colisiones resueltas **en el plan** con los combos medidos, y verificadas por **dos** gates: test 3 (same-scope, `detectCollisions`) y **test 3-bis (cross-scope, agrupando por combo solo)** — porque `detectCollisions` incluye `scope` en su clave y **no puede** ver la colisión de `Escape` global vs `page` (D4). `Ctrl+F` descartado a favor de `Ctrl+Shift+F`; `Enter`/`Shift+Enter`/`Escape` fuera del registro global. `src/services/shortcuts.test.ts` corre como regresión. |
| **R5-bis** | **Un atajo nace muerto**: se registra un combo sin Ctrl y no dispara nunca con foco en un input. | **Alta** (pasó en el v1 con `Enter` y en el v2 con `Escape`) | **F6 test 9 (ratchet de atajos muertos)**: `comboAllowedInEditable(combo) === true` para **toda** entrada de `CONSOLE_SHORTCUT_DEFS`, sin allowlist. Regla de diseño: lo que va al registro lleva Ctrl; lo que no, va a un `onKeyDown` local. Paso 4-bis del smoke. |
| **R15** | **La consola se cablea a `Agents.cancel` (`endpoints.ts:1135`)** y "cancela" corridas que siguen vivas, devolviendo `{"ok": true}`. | **Alta** (el v2 anclaba exactamente esa línea) | Aviso en cabecera de F3 con la tabla comparativa de los dos `cancel`; anclaje corregido a `:1394`; **F3 test 11** grepea los archivos de consola y falla si aparece `Agents.cancel` o `/api/agents/cancel`; paso 9 del smoke verifica que el proceso de Codex murió de verdad. |
| **R16** | **Choque de contratos de confirmación con el Plan 267**, que declara "un solo contrato de confirmación" y prohíbe un segundo mecanismo. | Media | §4.bis: reparto escrito — acciones **de corrida** con `useConfirm` (265, igual que `ActiveRunsPanel`), acciones **DevOps** con `confirmGateway` (267). El 265 no importa `entityActions.ts` y `consoleActions.ts` queda puro para que el 267 lo absorba en una capa si decide hacerlo. |
| **R17** | **Una flag ajena OFF tumba la consola entera** (`STACKY_EXECUTION_HISTORY_ENABLED` ⇒ 404 y `api.get` lanza). | Media | F5(b): `rawGet` + `historyPanelState` con degradación y motivo visible; 4 tests; paso 7-bis del smoke con la flag apagada de verdad. |
| **R6** | La bitácora crece sin techo o rompe una acción del operador. | Media | Rotación a 5 MB con máximo 2 archivos; `record_console_action` **nunca lanza** y devuelve `False` ante cualquier error. |
| **R7** | El panel de Contexto depende del **Plan 264** y ese plan no está implementado. | **Alta** | Degradación explícita: muestra lo que hay y `"—"` con la `note` de la matriz de capacidades. **No bloquea** este plan. Declarado en F2.5 y F5(a). |
| **R8** | Ocultar el chrome de la app en `"full"` deja al operador sin salida si un atajo falla. | Media | Siempre hay un botón visible de "Volver al dock" en el header de la consola, además del atajo. Nunca sólo teclado. |
| **R9** | `style={{` o literales hex nuevos ponen los ratchets de UI en rojo. | **Alta** (la consola es una pantalla nueva grande) | Los `.tsx` nuevos nacen con **alcance 0** en el ratchet de inline styles: **cero `style={{`** — para lo dinámico, `ref` + efecto o variables CSS. Cero literales hex: sólo tokens de `theme.css`. `uiDebtRatchet.test.ts` corre en F8. |
| **R10** | Espaciados hardcodeados hacen la consola sorda a la densidad. | Media | Todo el CSS nuevo usa `var(--space-N)` (Plan 150); grep de verificación sobre el `.module.css` nuevo ⇒ **0** hardcodeados. |
| **R11** | **Un diff filtra un secreto del operador al navegador y a la bitácora.** | **Alta** (los repos de Stacky tienen archivos de configuración con claves) | F4.5: enmascarado por **forma** aplicado **antes** del truncado y antes de cualquier escritura; sin flag propia; 8 tests; paso 5 del smoke. |
| **R12** | **F0 sale rojo en el primer comando** por editar sólo 2 de los 6 lugares del patrón de flags. | **Alta** (le pasó al v1 de este plan y a dos planes hermanos) | F0 v2 lista los **seis** archivos con ruta, estructura y línea, y explica el mensaje de error exacto de cada guard. |
| **R13** | El merge con 260/263/264 deja un **duplicado silencioso** en los archivos de registro (git no marca conflicto). | Media | §4.bis: bloques contiguos con marca `# Plan 265`, orden de merge recomendado, y verificación obligatoria tras **cada** merge (`compileall` + `tsc` + los dos tests de flags por archivo). |
| **R14** | Una sesión concurrente sobre el mismo árbol (hay worktrees paralelos vivos) hace fallar `git status`. | Media | Test 13 de F4: `.git/index.lock` presente ⇒ `available: False` con motivo, nunca 500 ni cuelgue. |

---

## 7. Fuera de scope

- **No** se crea un componente de consola paralelo: es una presentación del mismo `CodexConsoleDock`.
- **No** se toca el ring-buffer ni sus cotas.
- **No** se agregan dependencias npm (markdown y resaltado ya están instalados).
- **No** se implementa RBAC ni permisos por usuario: la auditoría es bitácora, no restricción (test 9 de F7).
- **No** se agrega ningún endpoint que escriba en git, ADO, GitLab o una BD del operador.
- **No** se implementa auto-reintento: volver a lanzar es siempre un click humano.
- **No** se reemplaza `ChatDrawer` (es otro flujo: chat libre con un agente, no seguimiento de corrida).
- **No** se agrega polling: la consola es push por SSE y el panel de repo se refresca por acción.
- **No** se implementa el selector de modelo/effort: se deja el seam medido para el Plan 264 (§4.bis).
- **No** se edita `backend/services/plans_board.py` (Plan 263) ni `backend/services/claude_code_cli_runner.py`
  (Plan 264): sólo se los cita y se copia el patrón.
- **No** se toca el panel DevOps ni el cockpit (Plan **239**, ya IMPLEMENTADO): verificado que no hay solapamiento.
- **No** se crea ni se toca el catálogo de acciones DevOps ni `services/entityActions.ts` (Plan **267**): la
  confirmación de acciones **de corrida** usa `useConfirm`, que es lo que ya hace `ActiveRunsPanel` (§4.bis).
- **No** se arreglan las **79 keys** del registry sin entrada en `PLAIN_HELP` ni las 15 violaciones de jerga: es
  deuda ajena medida en F0.8, y este plan la deja **exactamente igual** (ni una entrada más, ni una menos).
- **No** se usa `Agents.cancel` (`api/endpoints.ts:1135`) por ningún camino.

---

## 8. Orden de implementación y DoD

**Orden (estricto):**

1. **F0** — flags (los **seis** lugares).
2. **F1** — store + presentación + migración v3→v4 (ojo con `WorkbenchPersistV4`, D5).
2-bis. **F1.5** — identidad de sesión (**gate duro**: si el test 1 de F1.5 falla, no sigas; es la tesis del plan).
3. **F2** — render rico (independiente de F3-F7).
4. **F2.5** — matriz de capacidades (**antes de F3**: F3 consume sus `note`).
5. **F3** — cancelar / volver a lanzar con confirmación.
6. **F4** — panel de repositorio (backend + frontend).
7. **F4.5** — enmascarado de secretos (**inmediatamente después de F4**; el panel no se habilita en el smoke
   hasta que esta fase esté verde).
8. **F5** — contexto, historial y búsqueda.
9. **F6** — atajos (después de F5, porque el atajo de búsqueda necesita la búsqueda).
10. **F7** — bitácora.
11. **F8** — cierre.

**Definición de Hecho (DoD):**

- [ ] Los **20** comandos de F8 salen **exit 0**, cero rojos nuevos.
- [ ] El **snippet de F0.8** (4 keys `STACKY_CONSOLE_*` contra las 10 reglas) imprime **`OK 4/4`** y sale exit 0.
- [ ] `test_harness_flags_help.py` sigue en su **baseline medido**: **`4 failed, 4 passed`**, los mismos 4 nombres
      de la tabla de F0.8, y **ninguna línea de error menciona `CONSOLE`**. (No se exige exit 0: es deuda ajena.)
- [ ] Los **12** pasos del smoke manual ejecutados y **anotados con su resultado real** (incluidos 2-bis, 4-bis
      y 7-bis, que son los tres casos que el v2 no tenía).
- [ ] **KPI-1**: `normalizePresentation` cubre los 3 estados; test verde.
- [ ] **KPI-2 — ahora automático (D12)**: los **9 casos de F1.5** verdes, en particular el test 1 (las 9
      transiciones conservan el token de sesión) y el test 8 (el token **distingue** sesiones distintas — sin él,
      el test 1 se satisface con una constante). Y el setter del store llama a `applyPresentation`, no hace
      aritmética propia. El conteo manual de líneas del paso 2 queda como confirmación, no como evidencia única.
- [ ] **KPI-3**: las **20** capacidades de la tabla de §1.3 tildadas una por una; las que degradan
      (modelo/effort sin Plan 264) lo declaran en la UI con motivo visible.
- [ ] **KPI-4**: `requiresConfirmation("cancel") === true` y el diálogo canónico (`useConfirm`) se abre de verdad
      (paso 6 del smoke). Cero acciones destructivas sin confirmar.
- [ ] **KPI-5**: el test 11 de F4 verde ⇒ ningún subcomando de escritura de git en `api/git.py` ni en
      `services/console_repo.py`.
- [ ] **KPI-6**: los 8 tests de F4.5 verdes y el paso 5 del smoke con el aviso de valores ocultos a la vista.
- [ ] **Paridad de los 3 runtimes**: test 3 de F2.5 verde **y** el paso 9 del smoke corrido con los 3, con el
      texto del botón Cancelar anotado para cada uno.
- [ ] Las 4 flags declaran `default=True` **y** están en `_CURATED_DEFAULTS_ON`; las 3 hijas están en
      `_REQUIRES_MAP_FROZEN`; las 4 están en `_CATEGORY_KEYS["interfaz_ui"]` — **verificado que quedaron ANTES del
      `),` de `:477` y no del de `:484`, que es de `"paridad_proveedores"` (D11)** — y en `PLAIN_HELP`.
      **Los seis lugares tildados uno por uno.**
- [ ] **Endpoint de cancelación correcto (D1)**: `git diff` del cambio **no** contiene `Agents.cancel` ni
      `/api/agents/cancel`; F3 test 11 verde; paso 9 del smoke confirma que el proceso de `codex_cli` murió.
- [ ] **Cero atajos muertos (D3)**: F6 test 9 verde y paso 4-bis del smoke (`Escape` con el foco DENTRO de la caja
      de búsqueda vuelve al dock).
- [ ] **Colisiones cross-scope (D4)**: F6 test 3-bis verde con su mapa `_CROSS_SCOPE_RESUELTAS` escrito.
- [ ] **`tsc` verde tras F1 (D5)**: existe `WorkbenchPersistV4` y la firma de `migrateWorkbenchPersist` la devuelve.
- [ ] **Degradación del historial (D6)**: `consoleHistoryPanel.test.ts` verde (4 casos, incluido el 404
      `feature_disabled`) y paso 7-bis del smoke corrido con la flag ajena realmente apagada.
- [ ] **Fronteras 239 y 267 (D7, D14)** respetadas: `git diff --stat` **no** contiene `services/entityActions.ts`
      ni ningún archivo del panel DevOps.
- [ ] Los **3** archivos `tests/test_plan265_*.py` registrados en **ambas** listas `HARNESS_TEST_FILES`
      (`.sh` y `.ps1`, con su sintaxis propia); `test_harness_ratchet_meta.py` verde.
- [ ] **Cero `style={{`** en los componentes nuevos de consola; cero literales hex nuevos; cero espaciados
      hardcodeados en el `.module.css` nuevo. `uiDebtRatchet.test.ts` verde.
- [ ] Cero `setInterval` / `refetchInterval` nuevos (comando de F5).
- [ ] Con `STACKY_CONSOLE_FULLSCREEN_ENABLED=false`, el dock se comporta **exactamente** como antes
      (paso 10 del smoke).
- [ ] **Frontera §4.bis respetada**: `git diff --stat` del cambio **no** contiene
      `backend/services/plans_board.py` ni `backend/services/claude_code_cli_runner.py`.
- [ ] **Huella de regresión (C16):** este plan **no registra** una entrada en
      `Stacky Agents/docs/sistema/error_fingerprints.json`, y la ausencia es deliberada: el catálogo guarda
      **patrones de log de clases de error ya observadas** (`schema_version: 1`, campos `log_pattern` /
      `killed_by` / `guard_test`), y este plan agrega capacidad, no cierra una clase de error vista en los logs.
      Los modos de falla que sí introduce (fuga de secreto en un diff, escritura a git desde la consola,
      bitácora usada como control de acceso) quedan cubiertos por **gates de test**, que es el instrumento
      correcto para un fallo que no deja rastro en el log.
- [ ] Registro de implementación agregado al final de **este** documento.
- [ ] `git commit` con **pathspec explícito** (`git commit -- "<ruta>" ...`). Prohibido `git add -A`,
      `reset`, `amend`, `stash`, `rebase`, `checkout` y `--no-verify` — hay sesiones paralelas vivas sobre este
      árbol. El `push` es manual.
