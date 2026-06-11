# 23 — Plan Capa Perceptible: cockpit del operador, calidad visible y cierre de loop

**Fecha:** 2026-06-10
**Estado:** propuesto (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5) y `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0-V2, propuesto).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia, diseño con archivos exactos, criterios de aceptación, tests TDD y complejidad.

**Relación con el doc 22 (frontera de no-solapamiento):** el doc 22 ataca la capa *interna* del arnés (perfiles de flags, guardrails de launch, taxonomía de fallos, pricing, versionado de prompts, intake universal, CI, advisor). Este plan ataca la capa *perceptible*: lo que el operador, el dev y management VEN en el uso diario. Donde un ítem de acá consume un ítem del 22, la dependencia está marcada (`dep: V0.4`, etc.) y SIEMPRE con modo degradado si la dependencia no está mergeada — ningún ítem de este plan bloquea en el 22.

> **Nota de numeración:** el ítem V2.1 del doc 22 menciona un futuro `docs/23_CHECKLIST_NUEVO_RUNTIME.md`. Ese número queda tomado por este plan; al implementar V2.1, crear el checklist como `docs/24_CHECKLIST_NUEVO_RUNTIME.md`.

---

## 1. Punto de partida: qué YA existe en la capa perceptible (no re-implementar)

Verificado contra el código el 2026-06-10 en `feat/memoria-colaborativa-hardening`:

| Capacidad visible | Dónde vive | Estado |
|---|---|---|
| Consola en vivo de runs CLI (SSE, fase "está escribiendo…", input interactivo) | `frontend/src/components/CodexConsoleDock.tsx` + `hooks/useExecutionStream.ts` (eventos `log`/`pre_run`/`completed`) + `GET /api/executions/<id>/logs/stream` (`api/executions.py:100`) | OK |
| Notificación browser al terminar el run streameado (beep + Notification API + title flash, opt-in localStorage) | `frontend/src/services/executionNotifier.ts` | OK (limitado, ver D-P6) |
| Status de runs en vivo (polling 5s) | `hooks/useRunningStatus.ts` | OK |
| Resume de sesión "continuar donde lo dejé" (C8) + ahorro semanal de tiempo (C14) + standup diario (C15) | `api/adoption.py`, `TeamScreen.tsx:118-125` (`ResumeCard`, `SavingsCard`), `DailyStandupModal` | OK |
| KPIs del arnés en UI | `HarnessHealthCard.tsx` montado SOLO en `pages/DiagnosticsPage.tsx` | OK (escondido) |
| Preflight de instalación | `GET /api/diag/health` (`api/diag.py:281`: PAT, outputs_dir, proyecto activo, watchers) + `GET /api/diag/local` (`services/local_diagnostics.py`: backend, ADO, gh, vscode, bridge, DB, runs huérfanos) + `HealthBanner.tsx` | OK (sin chequeo de binarios CLI) |
| Webhooks salientes CRUD + delivery firmado | `services/webhooks.py` (FA-52), `api/webhooks.py` | OK (1 solo evento, solo copilot, ver D-P6) |
| Publicación automática a ADO al completar (Modo B): comment.html + attachments + transición de estado por flow config | `services/agent_completion_internal.py:62` (`close_execution_with_publish`), `:341` (`_attempt_state_change`), `:395` (`_attempt_publish`), `services/ado_publisher.py` | OK (solo en éxito, ver D-P4) |
| Marcador idempotente en comentarios ADO | `ado_publisher.py:566-601` (`_stacky_comment_marker` — **invisible por diseño**) | OK |
| Sugerencia de próximo agente (datos + fallback `DEFAULT_NEXT`) | `services/next_agent.py`, `POST /api/flow-config/resolve` (`api/flow_config.py:197`) | OK (sin UI) |
| Inferencia de etapa del pipeline desde estado ADO | `services/ado_pipeline_inference.py` | OK (sin UI montada) |
| Crítico genérico bajo demanda (FA-47) | `agents/critic.py` + `POST /api/phase5/executions/<id>/critique` (`api/phase5.py:67`) | OK (cero consumidores frontend, no usa acceptance criteria) |
| Notificador desktop del SO (C10) | `services/desktop_notifier.py` | **Código muerto** (cero callers en el repo) |
| Tour de onboarding (6 pasos, one-shot) | `components/OnboardingTour.tsx` | OK |
| PM Command Center (sprint, riesgos, sentimiento, recomendaciones, ai/usage) | `pages/PMCommandCenter.tsx` + `api/pm.py` | OK |

**Restricciones vinculantes (idénticas al doc 22, no relitigar):** cap duro de modelo vía `llm_router.clamp_model`; "solo Stacky escribe en ADO" = todo por `ado_write_outbox`; mono-operador sin RBAC; claves de metadata existentes son contrato (agregar, nunca renombrar); todo flag nuevo entra en `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR; suite completa contaminada → validar por archivo.

---

## 2. Inventario de componentes huérfanos del frontend (evidencia central)

Hallazgo estructural: existe una capa rica de visualización construida en fases FA-* que **ningún page monta hoy**. Verificado con grep de montaje (`<Componente`) en todo `frontend/src`: solo se referencian entre sí.

| Componente | Estado | Decisión en este plan |
|---|---|---|
| `OutputPanel.tsx` (output + ContractBadge + DossierPanel + OutputTools) | Huérfano (nadie lo monta) | NO revivir entero: contrato de datos viejo. Canibalizar piezas. |
| `ContractBadge.tsx` (renderiza `execution.contract_result`) | Huérfano transitivo (solo lo monta OutputPanel:120) | **Revivir** en U0.1 — el contract gate (doc 21) hoy es invisible. |
| `StructuredOutput.tsx` | Huérfano transitivo | **Revivir** en U0.1. |
| `ExecutionHistory.tsx`, `LogsPanel.tsx`, `ChatDrawer.tsx` | Huérfanos | Dejar (la consola dock los reemplazó). No asumirlos funcionales. |
| `ABCompare.tsx`, `ReplayPlayer.tsx`, `ConfidenceDashboard.tsx`, `OracleDashboard.tsx`, `CatalogDashboard.tsx`, `DossierPanel.tsx`, `ProvenanceDrawer.tsx` | Huérfanos | Dejar fuera de scope (borrarlos es otro PR de limpieza, riesgo cero pero ruido). |
| `PipelineStatus.tsx` | Huérfano (solo su propia definición) | **Adaptar y montar** en U1.4. |
| `NextAgentSuggestion.tsx` | Huérfano | **Adaptar** en U1.4 (CTA de próximo agente). |

Regla para el dev junior: **ningún componente de esta tabla se considera "funcionando" por existir**. Antes de reusar uno, validar su contrato de props contra los types actuales (`frontend/src/types.ts`) y escribir test.

---

## 3. Diagnóstico: debilidades perceptibles con evidencia

| # | Debilidad | Evidencia | Impacto percibido |
|---|---|---|---|
| **D-P1** | **El resultado de un run es invisible en la app.** Al terminar un run, el operador no tiene dónde ver: artefactos producidos (existe `GET /api/executions/<id>/output-files`, `api/executions.py:391`, con **cero** consumidores frontend), resultado del contract gate (`contract_result` es columna real, `models.py:219`, pero `ContractBadge` está huérfano), costo/tokens/duración, ni el error con detalle. El dock muestra logs y nada más. | Greps de montaje sección 2; `CodexConsoleDock.tsx` (solo líneas + fase heurística :25-45) | Todo el trabajo del arnés (validación, telemetría, confianza) no se VE. El operador termina yendo a ADO o al filesystem a mirar qué pasó. |
| **D-P2** | **Cuando algo falla, no hay diagnóstico accionable en pantalla.** `needs_review` solo aparece agregado en `HarnessHealthCard` (Diagnóstico); no existe una bandeja de ejecuciones falladas/needs_review con causa, ni botones de acción (resume/relaunch/descartar) en un solo lugar. El repro.ps1 (H7) y los `intake_errors` futuros (V1.3) no se muestran en ningún lado. | grep `needs_review` en frontend → solo `endpoints.ts`, `HarnessHealthCard.tsx`, `MemoryPage.tsx`, `agentCompletionErrors.ts` | El operador diagnostica por logs/DB. El tiempo-a-resolución de un run fallido es alto y la sensación es "caja negra". |
| **D-P3** | **Lo publicado en ADO no se distingue de un comentario manual.** El marcador es invisible por diseño (`ado_publisher.py:584-601`). No hay firma visible (agente, runtime/modelo, duración, costo, confianza, run id), ni en comentarios ni en tasks creadas. | `_inject_stacky_marker` = `<!-- -->` + span display:none | Stakeholders que viven en ADO no perciben que Stacky trabajó. El valor producido es anónimo. |
| **D-P4** | **El loop con ADO solo se cierra en éxito.** `close_execution_with_publish` publica y transiciona estado al completar; en error/needs_review no se deja NADA en ADO (ni comentario de diagnóstico, ni transición configurable). El ticket queda en silencio. | `agent_completion_internal.py:62-395` (paths solo de publish); sin llamadas a outbox en paths de error de `harness/post_run.py` | Quien mira el ticket en ADO no sabe que un agente lo intentó y falló. Re-trabajo y desconfianza. |
| **D-P5** | **El botón "publicar a ADO" de la UI es un stub y "aprobar" no publica.** `POST /executions/<id>/publish-to-ado` devuelve `stubbed: true` con TODO de Fase 1 (`api/executions.py:151-168`); `approve` solo setea verdict + captura memoria (`:119-148`). La publicación real es 100% automática (watcher/Modo B), sin preview ni gate humano posible. | `api/executions.py:151-168` | No existe el modo "revisar antes de publicar". El operador no puede ver QUÉ va a aterrizar en ADO antes de que aterrice. |
| **D-P6** | **Notificaciones: solo si estás mirando esa ejecución.** El notify browser se dispara únicamente desde `useExecutionStream.onCompleted` (`useExecutionStream.ts:87`) — es decir, solo para el run actualmente abierto en el dock. `desktop_notifier.py` (C10) tiene cero callers. Webhooks: un solo evento `exec.completed`, disparado SOLO desde `agent_runner.py:622,755` (path copilot) — los runners CLI no disparan nada (grep `webhooks` en `claude_code_cli_runner.py`/`codex_cli_runner.py`/`harness/post_run.py` → 0); no hay eventos de fallo/needs_review; payload JSON crudo inservible para Teams. | `executionNotifier.ts`, `webhooks.py:132-148`, modelo `Webhook` sin campo de formato (`webhooks.py:31-46`) | El operador tiene que mirar la pantalla. Un run CLI que falla a los 20 minutos pasa desapercibido hasta que alguien revisa. |
| **D-P7** | **La calidad del artefacto no se mide contra el ticket antes de publicar.** El contract gate valida estructura; no existe self-review contra acceptance criteria (grep `AcceptanceCriteria|acceptance_criteria` en backend → 0 archivos). El `CriticAgent` (FA-47) existe pero: endpoint sin consumidores, crítica genérica sin AC, no integrado al flujo de publicación. | `api/phase5.py:67-93`; grep `critique` en frontend → 0 | Lo publicado puede estar bien formado e igual no responder al ticket. La calidad percibida en ADO depende solo del prompt. |
| **D-P8** | **El pipeline conceptual (funcional→dev→QA) no existe como experiencia.** Hay piezas: inferencia de etapa (`ado_pipeline_inference.py`), próximo agente (`next_agent.py` + flow-config resolve), transiciones de estado. Pero no hay vista de pipeline por ticket ni encadenamiento: cada etapa es un lanzamiento manual desconectado (grep `launch_next|auto_chain|orchestrat` → 0). | sección 1 + greps | "Entra ticket → sale artefacto validado" hoy son N decisiones manuales. El valor de orquestación no se percibe porque no existe. |
| **D-P9** | **No hay reporting para management.** Existe ahorro semanal de tiempo per-user (`/api/savings/weekly`, conservador) y el PM Command Center, pero: nada combina runs+éxito+costo+ahorro en un digest; no hay export (grep endpoints csv/pdf/digest → solo usos internos no relacionados); no hay envío programado. El argumento de valor de Stacky no sale de la pantalla del operador. | `api/adoption.py`, `api/pm.py` | Management no ve el ROI sin que el operador haga capturas de pantalla. |
| **D-P10** | **Preflight ciego a los runtimes CLI.** `local_diagnostics` chequea backend/ADO/gh/vscode/bridge/DB (`services/local_diagnostics.py:53-257`) pero NO la presencia/versión de los binarios `claude` y `codex` — los dos runtimes que el arnés promociona. Un runtime ausente se descubre con el primer run fallando. | grep `claude|codex` en `local_diagnostics.py` → 0 checks | Time-to-first-value malo en máquina nueva: el error aparece tarde y críptico (spawn_error). |

**Lectura estratégica:** el arnés (docs 21-22) garantiza que el trabajo se haga bien; este plan garantiza que se VEA: (a) el resultado de cada run en pantalla con su evidencia de calidad, (b) la firma de Stacky en ADO en éxito Y en fallo, (c) avisos que liberan al operador de mirar la pantalla, (d) el pipeline como experiencia de primera clase, (e) el ROI empaquetado para management.

---

## 4. Hoja de ruta

Tres fases priorizadas por **visibilidad-por-esfuerzo**. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: U0 completo → U1.1, U1.2 → resto de U1 → U2.

### FASE U0 — Quick wins: hacer visible lo que ya existe

---

#### U0.1 Panel de detalle de ejecución (el "qué pasó" en un click)

- **Ataca:** D-P1.
- **Objetivo:** un drawer/panel único donde el operador ve TODO lo de un run: estado, contract gate, output estructurado, artefactos producidos, telemetría (costo/tokens/duración) y error si lo hubo. Primer consumidor real de `output-files` y de `contract_result` en UI.
- **Diseño:**
  - Nuevo `frontend/src/components/ExecutionDetailDrawer.tsx` (+ `.module.css`). Props: `executionId: number | null`, `onClose`. Datos:
    - `GET /api/executions/<id>` (existe, `api/executions.py:58`) → status, error_message, verdict, `contract_result`, `metadata` (telemetría `claude_telemetry`/`runaway`/`prompt_sha` si existe), output.
    - `GET /api/executions/<id>/output-files` (existe, `api/executions.py:391`) → lista de artefactos con nombre/tamaño; render como lista con ruta absoluta copiable (los archivos viven en la máquina del operador — mono-operador, alcanza con la ruta + botón copiar).
  - Secciones del drawer (en orden): encabezado (agente, runtime, modelo, ticket, duración), **ContractBadge** (reusar `components/ContractBadge.tsx` — validar props contra el shape actual de `contract_result` y ajustar SOLO el badge si difiere), telemetría (chips: costo USD si existe, tokens in/out, turnos; "—" si falta), artefactos, output (reusar `StructuredOutput.tsx` con la misma validación de contrato), error/`needs_review` (texto completo de `error_message` + claves `metadata.intake_errors` y `metadata.failure_kind` si existen — `dep: V0.4/V1.3 del doc 22, degrada a mostrar solo error_message`).
  - Puntos de montaje (3): fila de `AgentHistoryModal.tsx` (click → abre drawer), botón "Ver detalle" en el header de `CodexConsoleDock.tsx` cuando `stream.done`, y la bandeja U1.1 cuando exista.
  - Sin backend nuevo. Sin flag (es UI read-only aditiva).
- **Criterios de aceptación:**
  1. Para una execution `completed` con contract gate, el drawer muestra badge con el resultado real.
  2. Para una con `error`, muestra `error_message` completo y no rompe si `metadata` no tiene claves nuevas.
  3. `output-files` con N archivos → lista de N; endpoint 404/vacío → sección "sin artefactos registrados" (no crash).
  4. Abrirlo desde historial y desde el dock muestra el mismo contenido.
- **Tests (TDD, vitest):** `components/__tests__/ExecutionDetailDrawer.test.tsx` — render con fixture completa, con execution mínima (sin metadata/contract), con output-files vacío; mock de fetch por MSW o stub del módulo `api`.
- **Complejidad:** M.

---

#### U0.2 Firma visible de Stacky en ADO (run footer)

- **Ataca:** D-P3.
- **Objetivo:** que cada comentario/task publicado lleve un pie visible y sobrio: quién (agente), con qué (runtime/modelo), cuánto (duración, costo si existe) y qué run (`exec #N`). El trabajo de Stacky deja de ser anónimo en ADO.
- **Diseño:**
  - Flag: `STACKY_ADO_RUN_FOOTER_ENABLED` (bool, default **false**) en `config.py` + `FLAG_REGISTRY` (mismo PR).
  - Nuevo helper en `services/ado_publisher.py`: `_render_run_footer(execution: AgentExecution) -> str` → HTML de una línea, estilo discreto:
    `<hr/><p style="font-size:11px;color:#888">🤖 Stacky · {agent_type} · {runtime}/{model} · {duración} · ${costo:.2f} · run #{id}</p>`
    Campos faltantes se omiten (nunca "None"). Costo: `metadata.claude_telemetry.total_cost_usd` o el estimado (`dep: V0.5, degrada omitiendo el costo`).
  - Cableado: en `publish_from_execution`, inmediatamente antes de `_inject_stacky_marker`, si el flag está ON → `html = html + _render_run_footer(...)`. El marcador invisible sigue siendo el ÚLTIMO append (no tocar su lógica: la idempotencia hashea el contenido ANTES del marcador — verificar en el test que el footer participa del sha de forma estable, es decir, se calcula el sha DESPUÉS de agregar el footer para que re-publicaciones no dupliquen).
  - Tasks creadas: en el path `create_task` de `services/agent_completion.py` (kind `agent_completion`), si el flag está ON, append de una línea equivalente al final de la descripción de la task. Mismo flag, mismo formato (sin HTML si el campo es texto plano).
- **Criterios de aceptación:** flag OFF → HTML publicado byte-idéntico al actual; flag ON → footer presente UNA sola vez aun re-publicando (idempotencia intacta, `comment_exists` sigue encontrando el marcador); execution sin costo → footer sin segmento de costo; task creada lleva la línea de firma.
- **Tests (TDD, `tests/test_ado_run_footer.py`):** render con/sin costo; OFF byte-idéntico; doble publish no duplica footer (reusar fixtures de idempotencia existentes de `ado_publisher`).
- **Complejidad:** S.

---

#### U0.3 Webhooks v2: paridad multi-runtime, eventos de fallo y formato Teams

- **Ataca:** D-P6 (mitad saliente).
- **Objetivo:** que CUALQUIER run, en CUALQUIER runtime, dispare webhook al terminar (completed/failed/needs_review), y que apuntar uno a un Incoming Webhook de Teams "simplemente funcione".
- **Diseño:**
  - Nuevo helper único en `services/webhooks.py`:
    ```python
    def fire_for_execution(execution_id: int) -> None:
        # status → evento: completed→exec.completed | error→exec.failed | needs_review→exec.needs_review
        # payload compacto: {event, execution: {id, ticket_id, agent_type, runtime, status,
        #   error_message, duration_s, cost_usd?, failure_kind?}}  (NO include_output=True: payloads chicos)
    ```
    `fire_completed_safe` queda como alias deprecado que delega (compat).
  - Cableado: `harness/post_run.py::finalize_run` (cubre claude+codex en éxito y needs_review) y los paths de error de ambos runners CLI (donde escriben el error final); `agent_runner.py:622,755` migra a `fire_for_execution` (copilot, mismo comportamiento para completed + gana failed). Gate: `STACKY_WEBHOOKS_V2_ENABLED` (bool, default **false**) — OFF = comportamiento actual exacto (solo copilot/completed).
  - Formato Teams: columna nueva add-only en el modelo `Webhook`: `format = Column(String(20), default="raw")` (`raw` | `teams`). En `_deliver`, si `format == "teams"` → envolver en MessageCard:
    `{"@type": "MessageCard", "summary": title, "themeColor": verde/rojo/ámbar según evento, "title": "Stacky · {agent} {verbo}", "text": "Ticket {id} · {runtime} · {duración} · {error o costo}"}`.
    `POST /api/webhooks` acepta `format` opcional (default raw); `to_dict` lo expone.
  - Frontend: en `SettingsPage` (sección webhooks si existe; si no, agregar subsección mínima de alta/baja/test que consuma el CRUD ya existente de `api/webhooks.py`), selector de evento (3) y formato (2).
- **Criterios de aceptación:** flag ON + run claude CLI que termina `error` → POST con `event: exec.failed`; run codex `needs_review` → `exec.needs_review`; webhook `format=teams` → body MessageCard válido (claves `@type`/`summary` presentes); flag OFF → ningún disparo nuevo (solo el legacy de copilot); migración de tabla: DB existente sin la columna no rompe (`Base.metadata.create_all` la agrega en DB nueva; para DB viva, default por código al leer `getattr(w, "format", "raw")` o migración add-column idempotente al boot — elegir la segunda: `ALTER TABLE webhooks ADD COLUMN format VARCHAR(20) DEFAULT 'raw'` con try/except como hacen otras columnas del repo).
- **Tests (TDD, `tests/test_webhooks_v2.py`):** mapeo status→evento (3 casos), payload compacto sin output, formato teams, flag OFF no-op, alias de compat.
- **Complejidad:** M (S backend + S formato/UI).

---

#### U0.4 Notificaciones globales del operador (app + desktop)

- **Ataca:** D-P6 (mitad local).
- **Objetivo:** que el operador se entere cuando CUALQUIER run termina, sin tener el dock abierto ni la pestaña visible.
- **Diseño:**
  - **Frontend (sin backend nuevo):** nuevo `frontend/src/hooks/useGlobalExecutionNotifier.ts`, montado una vez en `App.tsx`. Lógica: mantiene el set de ids `running` (reusa la MISMA query de polling de `useRunningStatus` — `GET /executions?status=running` cada 5s — vía react-query para no duplicar tráfico); cuando un id sale del set, fetch puntual de `GET /executions/<id>` y llama `notifyExecutionFinished({agent_type, status, ticket_label})` (ya soporta los 3 estados). Respeta los opt-ins existentes de `executionNotifier` (sound/desktop en localStorage). Dedup con `MIN_GAP_MS` ya resuelto en el notifier.
  - **Backend (cablear el código muerto C10):** flag `STACKY_DESKTOP_NOTIFY_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`. En `harness/post_run.py::finalize_run` y en el cierre de `agent_runner`, si el flag está ON → `desktop_notifier.notify(title=f"Stacky · {agent_type} {status}", message=f"Ticket {ticket} · {runtime}")` envuelto en try/except (nunca afecta el run). Mono-operador: el backend corre en la máquina del operador, así que el toast del SO le llega aunque el browser esté cerrado — exactamente el caso que el browser no cubre.
- **Criterios de aceptación:** con la app abierta en CUALQUIER tab y un run ajeno al dock terminando en error → notificación browser (si opt-in); flag backend ON + browser cerrado → toast del SO al terminar un run CLI; flag OFF → cero llamadas a `desktop_notifier`; el polling no se duplica (una sola query compartida).
- **Tests:** vitest para el hook (fixtures de transiciones running→done, dedup); `tests/test_desktop_notify_wiring.py` backend (flag ON llama al notifier con mock, OFF no, excepción del notifier no rompe finalize).
- **Complejidad:** S.

---

#### U0.5 Telemetría en vivo en la consola (costo/turnos mientras corre)

- **Ataca:** D-P1 (lado "en vivo").
- **Objetivo:** que el dock muestre, mientras el agente trabaja: turnos, tokens y costo acumulado (reportado o estimado) — la sensación de control del taxímetro.
- **Diseño:**
  - Flag: `STACKY_LIVE_TELEMETRY_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`.
  - Backend: ambos runners CLI ya parsean el stream de eventos del proveedor (de ahí salen logs y runaway guard). En ese mismo loop, con el flag ON, cada vez que cambie el contador de turnos o haya datos de tokens/costo, emitir al `log_streamer` un evento `type: "telemetry"` con payload `{turns, input_tokens?, output_tokens?, cost_usd?, cost_estimated?}`. Fuente del costo: el del CLI si lo reporta (claude `total_cost_usd`); si no, `harness/pricing.estimate_cost` (`dep: V0.5; degrada emitiendo solo turns/tokens sin costo`). Throttle: máximo 1 evento de telemetría cada 2s (no spamear el SSE).
  - Frontend: `useExecutionStream.ts` agrega listener para `telemetry` (estado nuevo `telemetry?: {...}` en `StreamState`; los eventos NO van a `lines`). `CodexConsoleDock` muestra chips en el header: `🔁 {turns} · ⎁ {tokens} · ${cost}` con tooltip "estimado" si `cost_estimated`.
- **Criterios de aceptación:** run claude con flag ON → chips se actualizan durante el run y el costo final coincide con el de la telemetría persistida; codex sin costo del CLI y sin V0.5 → chips de turnos/tokens, sin `$`; flag OFF → cero eventos `telemetry` en el SSE (byte-idéntico); el throttle limita la frecuencia.
- **Tests:** backend `tests/test_live_telemetry_events.py` (emisión con flag ON/OFF, throttle, payload), vitest extensión de `hooks/__tests__/useExecutionStream.test.tsx` (evento telemetry actualiza estado y no contamina lines).
- **Complejidad:** M.

---

### FASE U1 — Estructurales: diagnóstico, calidad y reporting

---

#### U1.1 Bandeja de revisión (inbox de runs que necesitan al humano)

- **Ataca:** D-P2.
- **Objetivo:** un solo lugar con todo lo que requiere intervención: runs `needs_review` y `error`, cada uno con causa y acciones. El operador deja de cazar fallos por logs.
- **Diseño:**
  - Backend: extender `GET /api/executions` (`api/executions.py:26`) para aceptar `status` repetido o lista separada por coma (`?status=needs_review,error`) y `limit`/`days` si no existen — cambio aditivo, sin alterar el shape de respuesta.
  - Frontend: nueva pestaña "Revisión" en `App.tsx` (mismo patrón Tab que las existentes, sin gate de `sections` — siempre visible) + `pages/ReviewInboxPage.tsx`:
    - Tabla: ticket (id+título), agente, runtime, terminado hace X, causa — prioridad de fuentes: `metadata.failure_kind` (`dep: V0.4, degrada a heurística sobre error_message truncado`), errores del contract gate (`contract_result.errors` si `passed=false`), `metadata.intake_errors` (`dep: V1.3, degrada omitiendo`).
    - Acciones por fila: "Ver detalle" (abre U0.1), "Reanudar" (reusar el flujo existente de `RecoverExecutionButton.tsx` — H7 resume), "Relanzar" (servicio `agentLaunch` existente con el mismo ticket/agente), "Descartar" (`POST /executions/<id>/discard` existente), "Repro" (muestra/copia la ruta del `repro.ps1` del run_dir si está en metadata).
    - Badge contador en el botón de la pestaña (`{n}` rojo si n>0), alimentado por la misma query con `refetchInterval` 30s.
- **Criterios de aceptación:** una execution `needs_review` con contract fallido muestra sus errores legibles; una `error` por crash muestra el error_message; los 4 botones disparan los flujos existentes (no se reimplementa resume/launch/discard); con cero pendientes, la página muestra empty-state y el badge desaparece; runs viejos sin claves nuevas de metadata no rompen el render.
- **Tests:** backend extensión de tests de `executions` (filtro multi-status); vitest `pages/__tests__/ReviewInboxPage.test.tsx` (render de causas con/sin metadata nueva, empty state).
- **Complejidad:** M.

---

#### U1.2 Self-review contra acceptance criteria antes de publicar

- **Ataca:** D-P7. La mejora de calidad MÁS perceptible en ADO.
- **Objetivo:** que el artefacto se revise solo contra los acceptance criteria del ticket antes de publicarse; el resultado es un checklist con score que (a) se ve en la UI, (b) opcionalmente firma el comentario en ADO, (c) opcionalmente bloquea la publicación si no llega al umbral.
- **Diseño:**
  - Flags (`config.py` + `FLAG_REGISTRY`, mismo PR): `STACKY_SELF_REVIEW_MODE` (str: `off`|`annotate`|`gate`, default **off**) y `STACKY_SELF_REVIEW_MIN_SCORE` (float, default `0.7`, solo aplica en `gate`).
  - Nuevo `backend/services/self_review.py`:
    ```python
    @dataclass(frozen=True)
    class SelfReviewResult:
        score: float                      # 0..1 = criterios cumplidos / evaluables
        checklist: list[dict]             # [{criterion, met: bool, evidence: str}]
        skipped_reason: str | None        # "no_acceptance_criteria" | "llm_error" | None
    def review_artifact(*, execution_id: int, artifact_text: str) -> SelfReviewResult
    ```
    Pasos: (1) obtener AC del work item vía `ado_client.get_work_item(ado_id, fields=["Microsoft.VSTS.Common.AcceptanceCriteria", "System.Description"])` — AC vacío → usar Description; ambos vacíos → `skipped_reason="no_acceptance_criteria"`, score neutro 1.0 (nunca castigar por falta de AC). (2) UNA llamada LLM vía `llm_router` (modelo barato de la política; el clamp existente aplica solo) con prompt fijo: "dado este checklist de criterios y este artefacto, devolvé JSON {checklist:[{criterion, met, evidence}]}" — parse estricto, error de parse → `skipped_reason="llm_error"`, score 1.0 (fail-open: el self-review NUNCA rompe un run por su propia falla). (3) score = met/total.
  - Cableado (dos hooks, mismo helper):
    - CLI: `harness/post_run.py::finalize_run`, después del contract gate y antes del estado final. `annotate` → solo persiste `metadata["self_review"] = {...}` (clave NUEVA). `gate` → si `score < MIN_SCORE`, status `needs_review` (mismo mecanismo que el contract gate) con el checklist en metadata.
    - File-based/copilot: `agent_completion_internal.close_execution_with_publish`, antes de `_attempt_publish` — mismo contrato; en `gate` el publish NO se ejecuta y la execution queda `needs_review`.
  - Visibilidad: U0.1 muestra el checklist (✓/✗ por criterio + evidencia); U0.2, si `self_review` existe y el footer está ON, agrega `✔ {met}/{total} AC` al pie; U1.1 lista los criterios fallidos como causa.
- **Criterios de aceptación:** mode `off` → cero llamadas LLM (byte-idéntico); `annotate` → metadata poblada, publicación intacta; `gate` con score bajo → `needs_review` y NADA llega a ADO; ticket sin AC → skipped, no bloquea; error del LLM → skipped + log warn, no bloquea; el costo de la llamada de review aparece sumado a la telemetría del run si es medible (si no, se omite — nunca inventar).
- **Tests (TDD, `tests/test_self_review.py`):** mock de ado_client y LLM — score por checklist, sin AC, parse error fail-open, gate vs annotate vs off; integración con `finalize_run` (extensión de los tests de post_run existentes) y con `close_execution_with_publish`.
- **Complejidad:** L (es el ítem más profundo del plan; partible en PR1 servicio+annotate, PR2 gate+UI).

---

#### U1.3 Cierre de loop ADO en fallo + transición configurable

- **Ataca:** D-P4.
- **Objetivo:** que el ticket en ADO nunca quede en silencio: si Stacky no pudo, lo dice con causa y próximo paso; opcionalmente mueve el estado a uno configurado.
- **Diseño:**
  - Flag: `STACKY_ADO_FAILURE_COMMENT_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`.
  - Nuevo `backend/services/ado_feedback.py`: `comment_run_outcome(execution_id) -> str | None` — para status `error`/`needs_review`, compone comentario corto:
    `"🤖 Stacky: el agente {agent} no completó esta tarea. Causa: {failure_kind o resumen de error}. Estado: requiere revisión del operador. (run #{id})"` y lo **encola vía `ado_write_outbox.enqueue(kind="post_comment", ...)`** con idempotency_key = `f"failure-comment:{execution_id}"` (un solo comentario de fallo por run, garantizado por la dedup del outbox). Nunca llama al cliente ADO directo (regla 6 doc 22).
  - Cableado: `harness/post_run.py::finalize_run` (paths error/needs_review) + el reaper (`services/ticket_status.py::recover_stale_running_tickets`) cuando marca un run colgado como error — mismo helper.
  - Transición en fallo: las reglas de `services/flow_config_store.py` ganan campo opcional add-only `on_failure_state: str | None`; `agent_completion_internal._resolve_transition_state_from_config` lo resuelve para los paths de fallo igual que hoy resuelve el de éxito. Sin estado configurado → no transiciona (comportamiento actual).
  - Causa: usa `metadata.failure_kind` (`dep: V0.4, degrada a primera línea de error_message`).
- **Criterios de aceptación:** run CLI que termina `needs_review` con flag ON → exactamente UN comentario encolado en el outbox (re-finalizar no duplica, por idempotency_key); flag OFF → cero escrituras; regla con `on_failure_state="Active"` → transición encolada en fallo; sin regla → sin transición; el comentario nunca incluye stack traces completos (truncar a 300 chars).
- **Tests (TDD, `tests/test_ado_feedback.py`):** compone+encola por status, idempotencia, truncado, flag OFF; extensión de tests de flow_config (campo nuevo opcional retro-compat).
- **Complejidad:** M.

---

#### U1.4 Vista de pipeline del ticket + CTA de próximo agente

- **Ataca:** D-P8 (mitad visibilidad).
- **Objetivo:** que cada ticket muestre su recorrido (Negocio→Funcional→Técnico→Dev→QA): qué etapas ya pasaron (con qué run), cuál sigue, y un botón "Lanzar {siguiente}". La orquestación todavía es manual; la CONCIENCIA de pipeline deja de serlo.
- **Diseño:**
  - Backend: nuevo `GET /api/tickets/<id>/pipeline` (en `api/tickets.py`): combina (1) inferencia de etapas (`services/ado_pipeline_inference.py` — reusar tal cual; si ya hay endpoint equivalente, reusarlo y NO crear otro), (2) executions del ticket agrupadas por agent_type/etapa (última de cada una con status), (3) próximo sugerido vía `POST /api/flow-config/resolve` / `services/next_agent.suggest`. Respuesta: `{stages: [{stage, done, evidence, last_execution: {id, status, agent_type} | null}], next: {agent_type, source: "flow_config"|"default"} | null}`.
  - Frontend: adaptar `components/PipelineStatus.tsx` (hoy huérfano — actualizar props al shape nuevo) y montarlo en el header del ticket seleccionado en `TicketBoard.tsx`, modo `compact`. Cada etapa hecha es clickeable → abre U0.1 con su `last_execution`. Debajo, CTA `▶ Lanzar {next}` que invoca el flujo de `services/agentLaunch.ts` existente con el agente sugerido (pre-seleccionado, el operador confirma en el modal de siempre — nunca lanza sin confirmación).
- **Criterios de aceptación:** ticket con funcional `completed` y dev sin correr → etapa funcional ✓ con link al run, CTA "Lanzar Developer"; ticket sin historia → todas pendientes y CTA del primer agente del flow; el click en CTA abre el modal de launch pre-cargado (no lanza directo); sin flow config para el proyecto → fallback `DEFAULT_NEXT` y `source: "default"` visible en tooltip.
- **Tests:** backend `tests/test_ticket_pipeline_endpoint.py` (composición de etapas+executions+next con fixtures); vitest del componente adaptado (estados done/pending/CTA).
- **Complejidad:** M.

---

#### U1.5 Digest de valor para management (exportable y enviable)

- **Ataca:** D-P9.
- **Objetivo:** el argumento de valor de Stacky en un artefacto enviable: "esta semana, N tickets procesados, X% éxito sin intervención, $Y de costo, Z horas ahorradas, top causas de fallo". Un click para descargarlo; opcional, llega solo a Teams.
- **Diseño:**
  - Nuevo `backend/services/run_digest.py`: `compose_digest(days: int = 7, project: str | None = None) -> dict` — agrega desde `AgentExecution` + `harness_telemetry` + (si existen) `failure_kind`/costos estimados:
    `{period, projects: [...], totals: {runs, completed, needs_review, error, success_rate, cost_usd: {reported, estimated, total}, time_saved_ms (reusa la lógica conservadora de adoption/savings), tickets_touched}, by_agent_type: [...], by_runtime: [...], top_failures: [{kind|resumen, count}], highlights: [strings determinatas: "mejor agente", "runtime más usado"]}`.
    `dep: V0.4/V0.5 del doc 22 — degrada: sin failure_kind usa needs_review/error planos; sin pricing solo costo reportado` (los campos degradados se marcan `"partial": true`, nunca se inventan).
  - Renderers en el mismo módulo: `to_markdown(digest) -> str` y `to_html(digest) -> str` (tabla simple, sin dependencias nuevas).
  - Endpoint: `GET /api/reports/digest?days=7&project=X&fmt=json|md|html` (nuevo `api/reports.py`, blueprint registrado en `api/__init__.py`). `fmt=md|html` → `Content-Disposition: attachment` con filename fechado.
  - Envío programado: `STACKY_DIGEST_INTERVAL_HOURS` (int, default **0**=off) + `FLAG_REGISTRY`. Daemon thread en `app.py` (mismo patrón que el reaper) que cada intervalo compone y dispara `webhooks.fire("digest.ready", {digest}, project=None)` — con webhooks `format=teams` (U0.3) el resumen llega como card a un canal.
  - Frontend: card "Reporte semanal" en `PMCommandCenter.tsx` con preview de totals + botones "Descargar MD/HTML".
- **Criterios de aceptación:** digest con datos sintéticos de 2 proyectos/3 runtimes cuadra (totales = suma de partes); sin datos en el período → `totals.runs=0` y nota "sin actividad" (no error); `fmt=md` descarga archivo válido; intervalo 0 → daemon no arranca; el digest jamás incluye contenido de outputs/prompts (solo agregados — sin PII).
- **Tests (TDD, `tests/test_run_digest.py`):** agregación con fixtures (reusar helpers `_mk_cli_exec` de `test_harness_health.py`), degradación sin claves nuevas, renderers estables (snapshot), daemon off por default.
- **Complejidad:** M.

---

#### U1.6 Preflight de runtimes CLI (onboarding sin sorpresas)

- **Ataca:** D-P10.
- **Objetivo:** que una máquina/proyecto nuevo sepa ANTES del primer run si los runtimes están operativos.
- **Diseño:** nuevo check `_check_cli_runtimes()` en `services/local_diagnostics.py` (mismo shape que `_check_gh_auth`): ejecuta `claude --version` y `codex --version` con timeout 5s y cache en memoria TTL 10 min (no penalizar cada carga de la página); reporta `{name, ok, detail: version|"no encontrado en PATH"}` por binario. `HealthBanner.tsx` ya renderiza los checks de `/api/diag/local` — verificar que el check nuevo aparezca con mensaje accionable ("Instalá claude CLI o usá runtime github_copilot").
- **Criterios de aceptación:** binario ausente → check rojo con detail accionable y el resto de diagnósticos intactos; presente → versión visible; dos llamadas seguidas usan el cache (un solo spawn); timeout no cuelga el endpoint.
- **Tests:** `tests/test_local_diag_cli_runtimes.py` con mock de subprocess (ok/ausente/timeout/cache).
- **Complejidad:** S.

---

### FASE U2 — Diferenciales: la experiencia "entra ticket, sale artefacto"

---

#### U2.1 Pipeline runs orquestados con gates

- **Ataca:** D-P8 (cierre). Depende de: U1.4 (vista), U1.2 (gate de calidad), V0.2/V0.3 del doc 22 (guard de duplicados y slots — **requisito duro**: no orquestar sin guardrails de launch).
- **Objetivo:** "Ejecutar pipeline" sobre un ticket: Stacky encadena las etapas configuradas, avanza solo cuando los gates pasan (contract + self-review), se detiene en `needs_review` y el operador ve el avance etapa por etapa.
- **Diseño:**
  - Modelo nuevo en `models.py`: `PipelineRun(id, ticket_id, project, stages_json, current_stage, status: running|paused|completed|failed|cancelled, created_at, updated_at)` — tabla nueva, `create_all` la crea.
  - Nuevo `backend/services/pipeline_orchestrator.py`:
    - `start(ticket_id, stages: list[str] | None) -> PipelineRun` — stages default desde flow config del proyecto; lanza la primera etapa por el MISMO path interno que `POST /api/agents/.../run` (extraer la función de launch de `api/agents.py` a helper reusable si hace falta — refactor mínimo, mismo comportamiento), respetando guard V0.2 y slots V0.3.
    - Avance por evento, no por polling: hook en `finalize_run`/cierre de copilot — si la execution pertenece a un pipeline activo (clave nueva `metadata["pipeline_run_id"]`): status `completed` + gates OK → lanzar siguiente etapa; `needs_review`/`error` → pipeline `paused` con la causa. Última etapa OK → `completed`.
    - `resume(pipeline_id)` (tras resolver la revisión) y `cancel(pipeline_id)`.
  - Endpoints: `POST /api/pipelines {ticket_id, stages?}`, `GET /api/pipelines/<id>`, `POST /api/pipelines/<id>/cancel`, `POST /api/pipelines/<id>/resume` (nuevo `api/pipelines.py`).
  - Flag: `STACKY_PIPELINES_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`; OFF → endpoints 404/feature-gated y cero hooks activos.
  - Frontend: la vista U1.4 gana botón "▶ Ejecutar pipeline" (visible solo con flag ON vía `GET /api/harness-flags` o config endpoint): muestra cada etapa con spinner/✓/⏸; `paused` → link directo a la bandeja U1.1; webhooks U0.3 ganan eventos `pipeline.completed`/`pipeline.paused`.
- **Criterios de aceptación:** pipeline de 2 etapas con ambas OK → 2 executions encadenadas sin intervención y pipeline `completed`; etapa 1 `needs_review` → pipeline `paused`, etapa 2 NUNCA lanzada; resume tras aprobar continúa desde la etapa siguiente; cancel detiene (la execution en curso se cancela por el flujo existente); flag OFF → byte-idéntico al sistema actual; dos `start` sobre el mismo ticket → 409 (guard).
- **Tests (TDD, `tests/test_pipeline_orchestrator.py`):** avance feliz, pausa por gate, resume, cancel, doble start, flag OFF; sin binarios reales (mock del launch helper).
- **Complejidad:** L.

---

#### U2.2 Modo "revisar antes de publicar" (preview + gate humano real)

- **Ataca:** D-P5.
- **Objetivo:** que el operador pueda elegir, por proyecto, que NADA se publique en ADO sin su click — viendo exactamente el HTML que va a aterrizar. Convierte el stub `publish-to-ado` en el endpoint real.
- **Diseño:**
  - Config por proyecto (en el storage de configuración por proyecto existente — `api/global_config.py`/`project_manager`): `publish_mode: "auto" | "review"` (default **auto** = comportamiento actual).
  - Backend: en `agent_completion_internal.close_execution_with_publish`, si el proyecto está en `review` → NO llamar `_attempt_publish`; persistir `metadata["publish_hold"] = {"reason": "review_mode", "artifacts": [rutas]}` y dejar la execution `completed` con verdict pendiente. Transición de estado ADO tampoco se ejecuta (se difiere al publish).
  - `POST /api/executions/<id>/publish-to-ado` (reemplaza el stub de `api/executions.py:151-168`): valida `publish_hold` presente → delega en `_attempt_publish(execution_id, triggered_by="operator_review")` (que ya publica vía publisher/outbox) + ejecuta la transición diferida → limpia el hold (set `metadata["publish_hold"]["released_at"]`). Sin hold → 409 (evita doble publicación manual).
  - Frontend: U0.1 gana sección "Pendiente de publicación" cuando hay hold: render del `comment.html` (iframe sandbox / `dangerouslySetInnerHTML` saneado con el saneador que ya use el repo para HTML — verificar `DocViewer`/`OutputPanel` como referencia), lista de attachments, y botones "Publicar a ADO" / "Descartar". El badge de U1.1 suma los holds pendientes.
- **Criterios de aceptación:** proyecto en `review` → run completo SIN escrituras ADO y con hold visible en el drawer; click publicar → comentario+transición llegan (vía el path real de siempre, outbox incluido) y segundo click → 409; proyecto en `auto` → byte-idéntico al comportamiento actual; descartar libera el hold sin publicar.
- **Tests (TDD, `tests/test_publish_review_mode.py`):** hold en review, publish real al aprobar, 409 doble, auto intacto; extensión de tests de `agent_completion_internal`.
- **Complejidad:** M/L.

---

#### U2.3 Economía visible en el día a día (costo por ticket en las vistas de trabajo)

- **Ataca:** D-P1/D-P9 (lado económico). Dep: V0.5 del doc 22 para cobertura no-claude (degrada a "solo lo reportado").
- **Objetivo:** que el costo deje de vivir solo en Diagnóstico: chip de costo acumulado por ticket en el board y rollup mensual por proyecto en PM.
- **Diseño:**
  - Backend: `GET /api/metrics/ticket-costs?ticket_ids=1,2,3` (en `api/metrics.py`): suma `total_cost_usd` de `harness_telemetry` por execution→ticket (+ flag `estimated: true` si incluye estimados); `GET /api/metrics/project-costs?months=3` → serie mensual por proyecto.
  - Frontend: chip `$X.XX` junto al ticket seleccionado en `TicketBoard` (y en la fila de U1.1/U1.4 donde ya se muestra la execution); card "Costo por proyecto (mes)" en `PMCommandCenter` junto al digest U1.5. Tooltip siempre aclara "incluye estimados" cuando aplica.
  - Sin flag (endpoints read-only + UI aditiva); el dato estimado hereda la transparencia de V0.5 (`cost_estimated`).
- **Criterios de aceptación:** ticket con 3 runs con costo → chip = suma exacta; ticket sin telemetría → sin chip (no `$0.00` falso); rollup mensual cuadra con harness-health del mismo período; tickets_ids vacío → 400.
- **Tests:** `tests/test_ticket_costs_endpoint.py` (agregación, sin datos, mezclas reportado/estimado).
- **Complejidad:** S/M.

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Visibilidad | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | U0.1 Panel detalle de ejecución | M | Muy alta (cada run, cada día) | Bajo (UI read-only) | — |
| 2 | U0.2 Firma visible en ADO | S | Muy alta (la ven stakeholders) | Bajo (flag OFF) | V0.5 opcional |
| 3 | U0.4 Notificaciones globales | S | Alta | Bajo | — |
| 4 | U1.6 Preflight runtimes CLI | S | Media/alta (onboarding) | Bajo | — |
| 5 | U0.3 Webhooks v2 + Teams | M | Alta | Bajo (flag OFF) | — |
| 6 | U0.5 Telemetría en vivo | M | Alta (taxímetro) | Bajo (flag OFF) | V0.5 opcional |
| 7 | U1.1 Bandeja de revisión | M | Muy alta | Bajo | V0.4/V1.3 opcionales |
| 8 | U1.4 Vista pipeline + CTA | M | Alta | Bajo | — |
| 9 | U1.2 Self-review vs AC | L | Muy alta (calidad en ADO) | Medio (toca finalize → modes off/annotate/gate) | — |
| 10 | U1.3 Loop ADO en fallo | M | Alta | Bajo (outbox + flag) | V0.4 opcional |
| 11 | U1.5 Digest management | M | Alta (management) | Bajo | V0.4/V0.5 opcionales |
| 12 | U2.3 Economía visible | S/M | Media/alta | Bajo | V0.5 |
| 13 | U2.2 Review-before-publish | M/L | Alta | Medio (toca completion → default auto) | U0.1 |
| 14 | U2.1 Pipelines orquestados | L | Muy alta (demo killer) | Medio/alto | U1.4, U1.2, **V0.2+V0.3 duras** |

**Reglas de implementación (las 7 del doc 22 aplican íntegras a todos los ítems):** TDD; validar por archivo de test (suite contaminada); flag nuevo = `config.py` + `FLAG_REGISTRY` + preset de V0.1 cuando exista, mismo PR; metadata solo claves nuevas; default OFF/0/auto-actual (retro-compat byte-idéntica); ADO solo vía `ado_write_outbox`; sin fallback silencioso entre runtimes.

**Reglas adicionales propias del frontend (este plan):**
8. Ningún componente huérfano (sección 2) se reusa sin validar su contrato de props contra `types.ts` y sin test vitest propio en el mismo PR.
9. Patrón existente obligatorio: CSS modules junto al componente, react-query para data, cero dependencias npm nuevas sin justificación escrita en el PR.
10. Toda UI nueva degrada con gracia ante metadata ausente (runs históricos): "—" o sección oculta, jamás crash ni "undefined" en pantalla.

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (quien lanza y supervisa runs)
- **Hoy:** lanza un run, ve logs crudos en el dock, y al terminar va a ADO o al filesystem a averiguar qué se produjo; si falla, lee logs; si no está mirando, no se entera.
- **Post-U0:** al terminar CUALQUIER run le llega aviso (browser o toast del SO aunque el navegador esté cerrado); un click y ve el detalle completo: contract gate, artefactos, costo, error. Mientras corre, ve el taxímetro (turnos/tokens/$).
- **Post-U1:** abre la pestaña "Revisión" y tiene TODO lo que requiere su intervención con causa y botones (reanudar/relanzar/descartar); cada ticket muestra su pipeline con "Lanzar siguiente"; una máquina nueva le avisa si falta un binario CLI antes del primer run.
- **Post-U2:** aprieta "Ejecutar pipeline" y supervisa por excepción: solo interviene cuando un gate pausa; si quiere, nada llega a ADO sin su preview y su click.

### Desarrollador / equipo (quien vive en ADO)
- **Hoy:** aparecen comentarios y tasks anónimos, indistinguibles de los manuales; si el agente falló, el ticket queda mudo.
- **Post-U0/U1:** cada artefacto llega firmado (agente, modelo, duración, costo, run id) y con `✔ 7/8 AC` de self-review; los tickets donde Stacky falló tienen comentario con causa y próximo paso; las tasks creadas declaran su origen. La calidad sube de verdad (el gate de AC frena lo incompleto) y además SE NOTA que subió.

### Management / stakeholders
- **Hoy:** el valor de Stacky es invisible salvo demo en vivo; no hay número que mostrar sin armarlo a mano.
- **Post-U1.5/U2.3:** digest semanal descargable (o directo en Teams): tickets procesados, tasa de éxito sin intervención, costo total (real+estimado), horas ahorradas, top causas de fallo; costo por proyecto/mes en el PM Center. El caso de negocio se escribe solo, con números conservadores y trazables.

---

## 7. Métricas de éxito del plan

| Métrica | Hoy | Objetivo |
|---|---|---|
| Clicks para ver el resultado completo de un run (artefactos+gate+costo) | imposible en la app | 1 (drawer U0.1) |
| Runs terminados que el operador detecta sin mirar la pantalla | solo el run abierto en el dock | 100% (U0.4 + U0.3) |
| Comentarios/tasks en ADO con autoría y métricas visibles | 0% | 100% con flag ON (U0.2) |
| Tickets con fallo de agente que quedan en silencio en ADO | 100% | 0% con flag ON (U1.3) |
| Artefactos publicados verificados contra acceptance criteria | 0% | 100% en modo annotate/gate (U1.2) |
| Tiempo de armado del reporte de valor para management | manual (capturas) | 1 click / automático a Teams (U1.5) |
| Lanzar la cadena funcional→dev→QA sobre un ticket | N lanzamientos manuales | 1 acción con gates (U2.1) |
