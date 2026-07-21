# Plan 210 — Gate de build determinista del Developer: fin del falso "Build OK"

> Estado: **v1 → v2 · CRITICADO — APROBADO-CON-CAMBIOS** (2026-07-21). Pipeline: proponer → criticar (`criticar-y-mejorar-plan`) → **[este paso ✓]** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Opus 4.8). Juez v2: StackyArchitectaUltraEficientCode (perfil max, adversarial).
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).

**CHANGELOG v1 → v2** (cada bullet cierra un hallazgo del juez; anclas reverificadas contra el repo 2026-07-21):
- **C1 (BLOQUEANTE) — veredicto stale = falso verde por construcción.** El veredicto se persistía por `ado_id` y sobrevive entre corridas: una segunda corrida que NO refresca el veredicto (un runtime ignora el PASO 4, o el endpoint falla) dejaba el gate leyendo un `gate_ok=true` viejo → el developer avanzaba en falso. Esto **derrotaba G1** ("ausencia = no verificado": no era ausencia, era *stale*). FIX: se **liga el veredicto a la ejecución** (`execution_id`, campo OPCIONAL aditivo del contrato §5) + razón `stale_verdict`; `gate_final_state` degrada si el veredicto no pertenece a la corrida que se cierra (F2, F4).
- **C2 (BLOQUEANTE) — contrato `get_status` (201) mal consumido.** `get_status` devuelve un **sobre** `{status, mode, slugs, log, artifact_ready, error, summary}` donde `summary` (el `build.summary.json`) es **`null` mientras corre**, `returncodes`/`base_dir` viven **dentro** de `summary`, y `get_status` puede ser **`None`** (201:620,:699-707,:769). El `_summary_path` **no existe** en el 201. FIX: `_poll_until_terminal` reescrito EXPLÍCITO (tolera `None`, itera `sobre["status"]`, extrae `sobre["summary"]` al terminal, deriva `summary_path` desde `base_dir`) (F2).
- **C3 (BLOQUEANTE) — F4 cableaba una variable inexistente.** El pseudocódigo envolvía `resolved_state`, pero `_apply_task_state` real (`api/tickets.py:530-558`) usa `target = plan.in_progress if phase=="start" else plan.final_ok` y **retorna directo** `_safe_transition`. FIX: wiring reescrito contra la estructura real (variable `target`, punto de inserción tras el centinela `:546`, early-return, rama legacy `:1385-1416` explícita) (F4).
- **C4 (IMPORTANTE) — F5 no-implementable literal.** `agent_html_output` **no expone `replace_body`**, `HtmlOutput` es **`@dataclass(frozen=True)`** con atributo `.html` (no `.body`), y la llamada pasaba `body=` contra el parámetro `html=`. FIX: `dataclasses.replace(output, html=...)`, keyword `html=`, inserción **antes** del fingerprint/dedupe (`:325`), y `annotate` reconstruye el `BuildVerdict` (frozen) con `dataclasses.replace` (F5).
- **C5 (IMPORTANTE) — colisión de edición 208↔210 en `_apply_task_state`.** Ambos editan la misma función (208 cambia la línea `plan = resolve_task_state_plan(...)`; 210 inserta el gate tras `target`). FIX: protocolo de integración explícito (quien implemente segundo INTEGRA, no clobberea) + test de coexistencia + aviso en "Planes relacionados" (C5).
- **C6 (IMPORTANTE) — el gate no cubría el path remoto del daemon de 208.** 208 introduce `completion_state.maybe_apply_state_transition` (transiciona `System.State` REMOTO fuera de `_apply_task_state`). El gate de 210 no lo tocaba → el plano remoto reabría el agujero. FIX: requisito duro de coordinación + **[ADICIÓN ARQUITECTO 1]** guard de cobertura (F4-bis) que se pone ROJO si un path de transición del developer omite `gate_final_state`.
- **C7 (MENOR) — literalidades:** firma de `_not_verified` unificada (kwargs), roundtrip tuple/list de `BuildVerdict` en `read_verdict`, `annotate` con `dataclasses.replace`, y se nombra un test de regresión concreto para el DoD flag-OFF.
- **C8 (MENOR) — huella de error.** Este plan mata la clase "falso Build OK": registra su huella en `docs/sistema/error_fingerprints.json` (F4-bis / DoD).
- **C9 (MENOR) — regex de neutralización evadible:** ya mitigado por defensa en profundidad (el gate de estado no depende del HTML + bloque autoritativo siempre insertado); se endurece con log de discrepancia y una segunda pasada para el claim sin `<span>` verde (F5).
- **Coherencia 210↔211 (reconciliación del orquestador del juez, post-crítica en paralelo)** — el pane de findings del Plan 211 (su F5) consume `execution.metadata["build_verdict"].{blocking_findings,warnings}`. Se extiende el resumen de metadata de **F7** para incluir esos dos campos (ya presentes en el `BuildVerdict` fusionado en F5). **210 es dueño de la escritura; el 211 no toca esta key.** Cierra el hueco de "pane muerto" que quedaba entre los dos planes criticados en paralelo, sin cambiar la seam congelada (`register_evidence_contributor`) ni la forma pública del `BuildVerdict`.

---

## Planes relacionados (leer antes de implementar)

- **DEPENDE de Plan 201** — "Taller de Compilación: detección de `.sln`, build en Release 1-click y artefactos descargables" (`Stacky Agents/docs/201_PLAN_TALLER_DE_COMPILACION_DETECCION_SLN_BUILD_RELEASE_1CLICK_Y_ARTEFACTOS_DESCARGABLES.md`, CRITICADO v2 — APROBADO-CON-CAMBIOS, aún SIN implementar). Este plan **reusa su builder** (`solution_builder.start_build`/`get_status`, F5 del 201), su `build.summary.json` (returncode/toolchain/salidas), su detección de toolchain + doctor (`build_toolchain.detect_toolchain`, F3 del 201), su scanner (`solution_scanner.scan_solutions_ex`, F1 del 201) y su store de catálogo (`solution_store.rescan_and_save`/`load_catalog`, F2 del 201). **210 NO reimplementa nada de eso**; lo invoca. Si el 201 todavía no está mergeado al implementar el 210, el 210 **degrada de forma controlada** (verdicto `build_workshop_unavailable` = "no verificado", nunca "Build OK") — ver F2, G7.
- **Es prerequisito de Plan 211** — "Inspector post-build y barrido de residuos de port entre clientes" (`Stacky Agents/docs/211_PLAN_INSPECTOR_POST_BUILD_Y_BARRIDO_DE_RESIDUOS_DE_PORT_ENTRE_CLIENTES.md`). El 211 **consume el `BuildVerdict`** y el `build.summary.json` que produce este plan, y se engancha en la **seam de contribuidores de evidencia** que expone F5 (`register_evidence_contributor`). No implementar 211 sin 210.
- **Coordina con Plan 208 (con protocolo de integración DURO — C5, C6)** — "Sincronización ADO al completar + Matriz de estados" (`Stacky Agents/docs/208_PLAN_SINCRONIZACION_ADO_AL_COMPLETAR_AGENTE_Y_MATRIZ_DE_ESTADOS_POR_TIPO_DE_TICKET_Y_AGENTE.md`, PROPUESTO v1). Reparto de responsabilidades: 208 decide *a qué estado* transiciona la matriz; 210 decide *si el developer puede avanzar* (requiere veredicto de máquina). **Dos puntos de fricción reales, con contrato explícito:**
  - **(C5) Colisión de edición en `_apply_task_state` (`api/tickets.py:530`).** AMBOS planes editan esa función: 208 F2 cambia la línea `plan = resolve_task_state_plan(profile, agent_type)` → `resolve_task_state_plan(profile, agent_type, getattr(ticket,"work_item_type",None))`; 210 F4 **inserta el gate DESPUÉS** de que se resuelve `target = plan.final_ok` (`:542`) y antes de `_safe_transition` (`:553`). Los dos cambios son en puntos distintos y **componen**. **Regla dura para quien implemente segundo: INTEGRAR, no reescribir la función** (riesgo de merge-duplicado silencioso — memoria `gotcha-merge-silent-duplicate-keyword`). Verificación tras merge: `grep -n "gate_final_state" api/tickets.py` → 1+ **y** `grep -n "work_item_type" api/tickets.py` → 1+ (ambos presentes).
  - **(C6) El gate DEBE cubrir el path REMOTO que introduce 208.** 208 F2 agrega `services/completion_state.py::maybe_apply_state_transition`, que transiciona `System.State` **remoto** en el daemon (`completion_dispatcher._drain_loop`) — **por fuera de `_apply_task_state`**. Si 208 shippea sin gatear ese path, el developer avanza el estado ADO remoto **sin veredicto de máquina** → reabre el agujero en el plano remoto. **Requisito duro (no negociable):** *todo* código que transicione el estado del developer (`agent_type == "developer"`) DEBE pasar por `dev_build_verify.gate_final_state(...)`. 210 expone esa función y un **guard de cobertura** (F4-bis, [ADICIÓN ARQUITECTO 1]) que se pone **ROJO** si aparece un path de transición del developer que no invoca el gate. 210 **no reimplementa 208**; solo blinda la seam.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy el Developer agéntico de Stacky **narra** "Build OK" como texto libre en su entregable (el LLM escribe `✓ Build OK`), y esa narración es lo que dispara la transición del ticket a "listo para QA" y lo que ve el revisor en Azure DevOps — sin que **ninguna máquina** haya compilado nada. Este plan agrega un **servicio determinista** (`dev_build_verify`) que resuelve la **entrada canónica de build** del proyecto (prefiere `.sln`), invoca el **builder real del Plan 201**, captura el `build.summary.json` y devuelve un **veredicto tipado** (`BuildVerdict`); y **endurece el DoD** para que el "Build OK" que llega a ADO — y la transición de estado que lo acompaña — **solo puedan emitirse si el veredicto de máquina es `ok` Y `entry_kind == 'sln'`**. El gate es **server-side y determinista**: no confía en la prosa del LLM (que puede narrar cualquier cosa) — el hecho lo produce la máquina, y la **ausencia** de veredicto se trata como **no verificado**, nunca como OK. Si no hay `.sln` o falta el toolchain .NET, el ticket va a estado de revisión/bloqueo con la razón exacta, jamás a "Build OK".

**Gap que cierra.** El "Build OK" es hoy 100% inverificable (ver §2 con anclas). Este plan convierte "el developer terminó y compila" de una **afirmación narrada** a un **hecho verificado por máquina**, sin agregar trabajo al operador y sin romper el contrato de salida existente.

**KPI / impacto medible (binarios).**
- **KPI-1 — Cero falsos verdes de estado:** % de transiciones del developer a `next_state_ok` (p.ej. "Reviewed by Dev") respaldadas por un `build.verdict.json` con `ok == true` y `entry_kind == 'sln'` = **100%**. Medible: contar transiciones final del developer vs. veredictos válidos (log `dev_build_gate.*`).
- **KPI-2 — Cero "Build OK" narrado sin respaldo:** en los deliverables publicados por el developer, el bloque "3. BUILD" que llega a ADO es **siempre** el bloque autoritativo de máquina (verde solo si veredicto `ok+sln`). Medible: sentinel de F5 (grep) verde + contador `dev_build_gate.neutralized_claim`.
- **KPI-3 — Trazabilidad:** 100% de las corridas del developer con la flag ON producen un `build.verdict.json` (aunque sea `reason == "toolchain_missing"` o `"no_sln"`). Medible: presencia del archivo por `ado_id`.
- **KPI-4 — Paridad 3 runtimes:** el núcleo (resolución de entrada + build + veredicto + gate) es Python determinista → **idéntico** en Codex/Claude/Copilot. Único roce con el LLM: la instrucción de prompt que dispara el endpoint (F6), con fallback duro (ausencia = no verificado).
- **KPI-5 — Cero regresión:** flag OFF → comportamiento byte-idéntico al actual (el developer narra como hoy). Ningún test existente se rompe.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada)

Cada ancla `archivo:línea` fue releída contra el repo el 2026-07-21 (no se cita de memoria):

1. **El "developer agéntico" = prompt + runner mínimo, y el runner NO compila ni verifica.** El runner `Stacky Agents/backend/agents/developer.py` tiene 36 líneas y solo define `system_prompt()` (`developer.py:27-35`): arma texto y nada más. La conducta de "compilar" vive únicamente en el prompt `Stacky Agents/backend/Stacky/agents/Developer.agent.md` (v2.1.1, `stacky_completion_contract: v1`, frontmatter `:4,:6`).

2. **"Build OK" es texto libre que narra el LLM — en DOS lugares del prompt:**
   - Seed boilerplate en el "RESUMEN RÁPIDO": `...para implementar la validación requerida. Build OK."` (`Developer.agent.md:301`).
   - Bloque HTML de build: `<p><span style="color:green"><strong>✓ Build OK</strong></span> — [solución compilada, configuración usada]</p>` (`Developer.agent.md:325-327`).
   No hay ningún gate determinista que verifique esa afirmación.

3. **El PASO 4 define "verificar" = correr el build y, si falla, iterar o reportar bloqueante — pero el DoD TERMINA en el exit code, narrado por el LLM.** `Developer.agent.md:197-199`: "Ejecutar el build descripto en la sección 'Compilación'. Si falla, iterar hasta que compile o reportar bloqueante." Cero verificación server-side; cero mención a que el hecho deba ser producido por máquina.

4. **El contrato de build del prompt apunta a `client_profile.build.online_solutions` (el `.sln`), pero el perfil default lo trae VACÍO.** `Developer.agent.md:152-168` (sección COMPILACIÓN) dice que las soluciones vienen de `client_profile.build.online_solutions`. Pero `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json:39` trae `"online_solutions": []`. El fallback para vacío es "No compilar automáticamente; indicar al operador" (`Developer.agent.md:69`). **Nada prohíbe que el LLM derive a compilar un `.csproj` suelto (o nada) y lo cante como "Build OK".**

5. **No hay verificación de build en el cierre del run.** Grep de `build|compil|completion_contract` en `Stacky Agents/backend/app.py` → solo `build_ado_client` / `build_error_envelope`; nada compila. El cierre universal de agente es `services/ticket_status.py::on_execution_end` (registro de post-hooks en `ticket_status.register_post_hook`, usado en `app.py:853-855`), y ninguno de esos hooks verifica build.

6. **La transición de estado "developer terminó → next_state_ok" existe y HOY se dispara con la narración.** El developer cierra con un PATCH a `POST /api/tickets/by-ado/{ADO_ID}/stacky-status` (`Developer.agent.md:242-267`) mandando `target_ado_state`. En el modo determinista (default ON, `config.py:1192-1194` `STACKY_DETERMINISTIC_TASK_STATES_ENABLED`), el handler `set_stacky_status_by_ado` **ignora** el `target_ado_state` del agente y resuelve el estado final con `_apply_task_state(ticket=t, agent_type=agent_type, phase="final", ...)` (`api/tickets.py:1375-1384`), que usa `resolve_task_state_plan` + `_safe_transition`. **Ese `_apply_task_state` (`api/tickets.py:530`) es el punto exacto donde "el developer terminó bien" se materializa en ADO — hoy sin ninguna prueba de que compiló.** El path legacy (flag OFF) aplica el `target_ado_state` del agente directo (`api/tickets.py:1385-1416`).

7. **El publish del deliverable a ADO tiene un chokepoint universal.** Toda publicación pasa por `services/ado_publisher.py::publish_from_execution` (`ado_publisher.py:212`), que lee el HTML del agente con `agent_html_output.read_and_validate(ado_id, hint=...)` (`ado_publisher.py:306`; validador en `agent_html_output.py:123`) y lo manda a ADO. Lo invocan el post-hook (`ado_publish_post_hook`, `ado_publisher.py:514,:539`), el gateway (`agent_completion.py:840`) y el rescate (`rescue_execution.py:460`). **Un solo lugar donde interceptar el HTML antes de publicar** = `publish_from_execution` justo después de `read_and_validate`.

8. **Confirmación estructural del vacío:** el propio Plan 201 declara que "**Ninguna** pieza compila desde fuente" (`201_PLAN_...:34`). Hoy nada en Stacky compila código de cliente de forma determinista, así que el "Build OK" del developer es, por construcción, inverificable. Este plan crea el productor de ese hecho (reusando el builder del 201) y el gate que lo exige.

**Conclusión:** el trabajo es **aditivo, server-side y determinista**: un servicio nuevo (`dev_build_verify`) que reusa el builder del 201, un endpoint que lo dispara durante el run, y dos gates en puntos ya identificados (`_apply_task_state` para el estado; `publish_from_execution` para el deliverable). El prompt se endurece pero **el gate no confía en el prompt**.

---

## 3. Principios y guardarraíles (NO negociables — codificados en cada fase)

- **G1 · El hecho lo produce la máquina, no el LLM.** El `BuildVerdict` sale de correr el builder real del 201 sobre un `.sln` resuelto determinísticamente. El LLM **no puede fabricarlo**. La **ausencia** de veredicto = **no verificado** (nunca OK). Prompt-only está PROHIBIDO como única defensa.
- **G2 · Human-in-the-loop innegociable.** El build corre **dentro del run que el operador ya inició** (el agente lo dispara vía endpoint como parte de su trabajo autorizado). **No** se auto-compila fuera de un run, **no** se auto-instala toolchain, **no** se bypasea al operador. El gate **degrada** el estado a revisión/bloqueo; nunca fuerza un "Blocked" duro por sí solo (respeta el `block_guard` existente, `api/tickets.py:1345-1368`).
- **G3 · Determinista-primero, cero LLM en el núcleo.** Resolución de entrada + build + veredicto + gates + anotación del deliverable son Python puro/determinista → idéntico en los 3 runtimes.
- **G4 · Paridad de 3 runtimes.** El único punto que roza el LLM es la instrucción de prompt (F6) que dispara el endpoint; y aun si un runtime la ignora, la ausencia de veredicto degrada el estado igual (el gate es server-side). Fallback explícito en cada fase.
- **G5 · Mono-operador sin auth.** Cero RBAC. `current_user`/`X-User-Email` es informativo (se usa solo para distinguir "origen agente" vs "operador", igual que el `block_guard` actual).
- **G6 · No degradar performance/seguridad/estabilidad/DX.** El build ya está acotado por el timeout del 201 (`_BUILD_TIMEOUT_SEC = 1800`) y su cancelación. El veredicto se cachea en `build.verdict.json`. Backward-compatible: flag OFF = byte-idéntico. Ningún import de red/LLM en `dev_build_verify`.
- **G7 · EXCEPCIÓN DURA #3 (prerequisito no garantizado: MSBuild/.NET SDK).** El build depende de un toolchain ausente en instalación default. Esto NO se respeta apagando la feature: la flag queda **default ON** (resolución + veredicto + gate son seguros y read-only sobre el toolchain), y cuando el toolchain falta, el veredicto es `reason == "toolchain_missing"` con el **doctor** del 201 (`build_toolchain.detect_toolchain`), el estado va a revisión (no "Build OK") y el deliverable dice la verdad. **Nunca crashea, nunca auto-instala.** Mismo criterio si el builder del 201 aún no está mergeado: `reason == "build_workshop_unavailable"` (degrada, no rompe). Citada en F2, F3, F4.
- **G8 · Config vía UI.** La flag `STACKY_DEV_BUILD_VERIFY_ENABLED` es visible/toggleable desde **Configuración → Arnés → categoría DevOps** (cableada en `harness_flags.py`, no solo env var).

---

## 4. Flag del arnés + campo de perfil nuevo (default seguro) — cableado EXACTO

**Flag nueva:** `STACKY_DEV_BUILD_VERIFY_ENABLED` · tipo `bool` · **default ON** · categoría `devops` · sin `requires`.

Los 5 lugares (idéntico patrón al Plan 201 §4 y a la receta de memoria "Receta flag DEVOPS default-ON = 5 lugares"; anclas verificadas 2026-07-21):

| # | Archivo | Qué agregar | Ancla verificada |
|---|---------|-------------|------------------|
| 1 | `Stacky Agents/backend/services/harness_flags.py` | `FlagSpec(key="STACKY_DEV_BUILD_VERIFY_ENABLED", type="bool", label="Verificación de build del Developer", description="Verifica de forma determinista que el Developer compiló (.sln) antes de permitir 'Build OK' y la transición de estado. El build requiere toolchain .NET.", group="global", default=True)` dentro de `FLAG_REGISTRY`. | `class FlagSpec` = `harness_flags.py:21`; `FLAG_REGISTRY` = `harness_flags.py:379` |
| 2 | `Stacky Agents/backend/services/harness_flags.py` | Agregar `"STACKY_DEV_BUILD_VERIFY_ENABLED",` a la tupla `_CATEGORY_KEYS["devops"]`. | `_CATEGORY_KEYS` = `harness_flags.py:117`; tupla `"devops"` = `harness_flags.py:202` |
| 3 | `Stacky Agents/backend/tests/test_harness_flags.py` | Agregar `"STACKY_DEV_BUILD_VERIFY_ENABLED",` al conjunto `_CURATED_DEFAULTS_ON`. | `test_harness_flags.py:467` (mismo set que usó el 201) |
| 4 | `Stacky Agents/backend/config.py` | Nuevo atributo de `Config`: `STACKY_DEV_BUILD_VERIFY_ENABLED: bool = os.getenv("STACKY_DEV_BUILD_VERIFY_ENABLED", "true").lower() in ("1", "true", "yes")` — espejá la forma de `STACKY_DETERMINISTIC_TASK_STATES_ENABLED`. | `config.py:1192-1194` (patrón default "true") |
| 5 | `Stacky Agents/backend/api/devops.py` | En el dict de `_health_payload()`, agregar `"dev_build_verify_enabled": bool(getattr(cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)),`. | patrón `*_enabled` en `devops.py` (mismo que el 201 lugar #5) |

> **NO hand-editar** `Stacky Agents/backend/harness_defaults.env` (lo genera `deployment/export_harness_defaults.py`; prohibido a mano — memoria "generador harness_defaults"). El default ON efectivo lo da `config.py` (lugar #4).
> **NO** hay `requires=` → NO se toca `_REQUIRES_MAP_FROZEN` ni bounds-map (es `bool`).
> Efecto colateral inocuo del lugar #5: la key aparece también en `/devops/bootstrap` (dict compartido); es intencional (paridad), igual que documentó el 201 (C10).

**Campo de perfil nuevo (default seguro):** `build.allow_csproj_entry` · tipo `bool` · **default `false`**.
- Semántica: un `.csproj` suelto (sin `.sln`) **NO** cuenta como entrada de build verificable **salvo** que el perfil lo declare `true` explícitamente. Con `false` (default), si no hay `.sln`, el veredicto es `reason == "no_sln"` → **bloqueante** (nunca "Build OK").
- Se agrega al template default en `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json` dentro de `"build"` (junto a `online_solutions`, `azure_devops.json:35-41`): `"allow_csproj_entry": false`.
- **No** requiere migración: `resolve_build_entry` lee `profile.get("build", {}).get("allow_csproj_entry", False)` → los perfiles viejos (sin la clave) se comportan como `false` (el más seguro). El editor de perfil (`ClientProfileEditor.tsx`) puede exponerlo en un follow-up; no es requisito de este plan (G1: default seguro sin tocar UI).

---

## 5. Arquitectura objetivo (mapa de artefactos)

```
BACKEND (Stacky Agents/backend/)
  services/dev_build_verify.py     (F1/F2/F3/F4/F5) NÚCLEO determinista:
                                     - resolve_build_entry (F1, PURO)
                                     - BuildVerdict(+execution_id) + verify_build (F2, invoca builder del 201)
                                     - write_verdict/read_verdict/verdict_path + _poll_until_terminal (F2)
                                     - project_name_for_ado/workspace_root_for_ado/latest_execution_id_for_ado (F3, PÚBLICOS)  ← los reusa 211
                                     - gate_final_state (F4, staleness-aware)  ← lo reusa Plan 208
                                     - annotate_build_evidence + register_evidence_contributor (F5)  ← lo reusa Plan 211
  api/dev_build.py                 (F3) blueprint: POST /api/tickets/by-ado/<ado_id>/dev/build-verify
  api/tickets.py                   (F4) wiring del gate en _apply_task_state (tras :552, sobre `target`) + rama legacy (:1385)
  services/ado_publisher.py        (F5) wiring de annotate (dataclasses.replace) en publish_from_execution (entre :306 y :325)
  tests/test_plan210_gate_coverage.py (F4-bis) guard: todo path de transición del developer pasa por gate_final_state
  docs/sistema/error_fingerprints.json (F4-bis) huella "dev_build_ok_narrated_unverified" (mata la clase)
  Stacky/agents/Developer.agent.md (F6) prompt endurecido (quita seed, reescribe PASO 4 + BUILD, v2.2.0)

FRONTEND (Stacky Agents/frontend/src/)
  components/OutputPanel.tsx        (F7) pane "Build (verificado por máquina)" desde execution.metadata.build_verdict
  components/devBuildModel.ts       (F7) helpers PUROS testeables (label/color/formato)
  components/devBuildModel.test.ts  (F7) vitest del modelo puro

DATOS (en el workspace del cliente, junto al deliverable)
  <workspace_root>/Agentes/outputs/<ado_id>/build.verdict.json   veredicto persistido (F2)
  <workspace_root>/Agentes/outputs/<ado_id>/comment.html         deliverable (anotado por F5 al publicar)
```

**Contrato `BuildVerdict` (CONGELADO por F2 — Plan 211 lo consume tal cual):**

```json
{
  "ok": false,
  "gate_ok": false,
  "entry_kind": "none",
  "solution": "",
  "solutions": [],
  "returncode": -1,
  "summary_path": "",
  "reason": "no_sln",
  "toolchain": { "available": false, "builder": null, "version": null },
  "build_id": "",
  "verified_at": "2026-07-21T12:00:00Z",
  "execution_id": 0,
  "blocking_findings": [],
  "warnings": []
}
```
- `ok` = el build corrió y **todas** las soluciones devolvieron returncode 0.
- `entry_kind` ∈ `{"sln","csproj","none"}`.
- `gate_ok` = `ok and entry_kind == "sln" and not blocking_findings` → **este** es el booleano que gobierna el estado y el verde del deliverable.
- **`execution_id`** (C1 — campo NUEVO, **opcional y aditivo**; default `0`): la ejecución del developer que produjo el veredicto. Liga el veredicto a la corrida para que un veredicto de una corrida **anterior** no valga como "verde" de la corrida actual (fin del falso verde por *staleness*). `0`/ausente = desconocido → el gate degrada a comportamiento best-effort (no puede probar frescura, ver F4). **Compatibilidad Plan 211:** el 211 consume `ok`/`entry_kind`/`gate_ok`/`solutions`/`summary_path`/`blocking_findings` y **no** lee `execution_id` → agregar el campo es backward-compatible con el contrato que 211 congela (campo opcional nuevo, permitido).
- `solution` = ruta de la `.sln` primaria (primera) construida, o `""`. `solutions` = todas las construidas.
- `returncode` = agregado (0 sii todas 0; el peor returncode si alguna falló; `-1` si no se construyó).
- `reason` ∈ el conjunto congelado `_REASONS` (ver F2).
- `blocking_findings` / `warnings` = **puntos de extensión** que los contribuidores de F5 (Plan 211) rellenan; cada item `{ "kind": str, "severity": "blocking"|"warning", "file": str, "detail": str }`.

---

## 6. Fases

> Convención de tests: **backend** = pytest **por archivo** con el intérprete del backend; **frontend** = vitest **por archivo** (contaminación cross-file conocida — memoria `gotcha-vitest-test-order-pollution-frontend`).
> **Comando backend** (desde `Stacky Agents/backend`): `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q` — si `.venv` no existe, usar `venv\Scripts\python.exe` (mismo py3.13).
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run src\components\<archivo>.test.ts`.
> **Registrar** CADA `test_*.py` nuevo en `Stacky Agents/backend/scripts/run_harness_tests.sh` array `HARNESS_TEST_FILES` (`run_harness_tests.sh:20`) o el meta-ratchet se pone rojo (memoria `stacky-ratchet-obliga-registrar-tests`).

---

### F0 — Flag + campo de perfil + esqueleto (gate primero)

**Objetivo:** dejar la flag cableada (5 lugares §4) y el campo `build.allow_csproj_entry` en el template default, con `dev_build_verify.py` creado exponiendo solo constantes y firmas (stubs que devuelven `not_verified`), sin lógica. Valor: de-riesga toda la ceremonia de flags/health antes de la lógica.

**Archivos a editar/crear:**
- Los 5 de §4 (harness_flags.py ×2, test_harness_flags.py, config.py, api/devops.py).
- `Stacky Agents/backend/services/client_profile_defaults/azure_devops.json` — agregar `"allow_csproj_entry": false` dentro de `"build"` (`azure_devops.json:35-41`).
- Crear `Stacky Agents/backend/services/dev_build_verify.py` con: la constante `_REASONS` (tupla congelada, ver F2), el dataclass `BuildVerdict` (campos de §5, `@dataclass(frozen=True)`) y un factory `_not_verified(...)`, y las firmas públicas de F1-F5 como stubs (`raise NotImplementedError` NO; devolver `_not_verified("not_verified")` o el `html` sin cambios, para que importar el módulo nunca rompa).
  - **Defaults del dataclass frozen (C7 — literal):** los campos de colección usan `field(default_factory=...)` o tuplas inmutables, nunca `[]` literal como default (rompería `@dataclass`). Forma exacta: `solutions: tuple[str, ...] = ()`, `blocking_findings: tuple = ()`, `warnings: tuple = ()`, `toolchain: dict = field(default_factory=lambda: {"available": False, "builder": None, "version": None})`, `execution_id: int = 0`. `from dataclasses import dataclass, field, asdict, replace`.
  - **Factory `_not_verified` (C7 — firma única que usan F1/F2/F4/F5):**
    ```python
    def _not_verified(reason: str, *, entry_kind: str = "none", solutions: tuple = (),
                      toolchain: dict | None = None, verified_at: str | None = None,
                      execution_id: int = 0) -> "BuildVerdict":
        return BuildVerdict(ok=False, gate_ok=False, entry_kind=entry_kind, solution="",
                            solutions=tuple(solutions), returncode=-1, summary_path="",
                            reason=(reason if reason in _REASONS else "not_verified"),
                            toolchain=toolchain or {"available": False, "builder": None, "version": None},
                            build_id="", verified_at=(verified_at or _utcnow_iso()),
                            execution_id=execution_id, blocking_findings=(), warnings=())
    ```

**Nombres exactos:** flag `STACKY_DEV_BUILD_VERIFY_ENABLED`; health key `dev_build_verify_enabled`; campo perfil `build.allow_csproj_entry`; módulo `services/dev_build_verify.py`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_flag.py`:**
- `test_flag_registered_and_curated`: la key está en `FLAG_REGISTRY`, en `_CATEGORY_KEYS["devops"]` y en `_CURATED_DEFAULTS_ON`.
- `test_health_exposes_dev_build_verify_enabled`: `/api/devops/health` incluye `dev_build_verify_enabled` (molde `test_plan120_api.py`).
- `test_default_profile_has_allow_csproj_entry_false`: `json.load(azure_devops.json)["build"]["allow_csproj_entry"] is False`.
- `test_module_imports_clean`: `import services.dev_build_verify` no lanza; `_not_verified("x").gate_ok is False`.
- Registrar `tests/test_plan210_flag.py` en `HARNESS_TEST_FILES`.
- Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan210_flag.py tests\test_harness_flags.py -q`

**Criterio de aceptación BINARIO:**
- Comando anterior → verde.
- `grep -rn "STACKY_DEV_BUILD_VERIFY_ENABLED" "Stacky Agents/backend/config.py"` → 1+ match.
- `grep -n "allow_csproj_entry" "Stacky Agents/backend/services/client_profile_defaults/azure_devops.json"` → 1 match.

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED` (default ON). **Impacto runtime:** idéntico 3/3 (solo registro/stubs). **Trabajo del operador:** ninguno.

---

### F1 — Resolución determinista de la entrada de build (`resolve_build_entry`)

**Objetivo:** función pura que decide, sin LLM, cuál es la entrada canónica de build del proyecto: prefiere `.sln`; si `online_solutions` está vacío, escanea; si no hay `.sln`, es bloqueante; un `.csproj` suelto no cuenta salvo `allow_csproj_entry`. Valor: es el corazón "nunca 'Build OK' sin un `.sln` real".

**Archivo a editar:** `Stacky Agents/backend/services/dev_build_verify.py`.

**API pública (nombres exactos):**
```python
def resolve_build_entry(profile: dict, workspace_root: str | None) -> dict
# devuelve {"entry_kind": "sln"|"csproj"|"none", "solutions": list[str], "reason": str}
```

**Reglas (deterministas, en orden):**
1. `workspace_root` falsy o no es dir → `{"entry_kind":"none","solutions":[],"reason":"workspace_missing"}`.
2. `declared = profile.get("build", {}).get("online_solutions") or []`. Para cada entrada declarada, resolver a ruta absoluta bajo `workspace_root` (si es relativa) y quedarse con las que existen y terminan en `.sln`. Si queda ≥1 → `{"entry_kind":"sln","solutions":[...abs...],"reason":"ok"}`.
3. Si `declared` no rindió `.sln`: **escanear** con el scanner del Plan 201 → `from services.solution_scanner import scan_solutions_ex` dentro de un `try/except ImportError` (el 201 puede no estar mergeado). `found = [s["sln_path"] for s in scan_solutions_ex(workspace_root)["solutions"]]`. Si ≥1 → `{"entry_kind":"sln","solutions": sorted(found), "reason":"ok"}`. Si `ImportError` → seguir al paso 4 con `found = []` (no romper).
4. Sin `.sln`: si `profile.get("build", {}).get("allow_csproj_entry", False)` es `True`, intentar hallar un `.csproj` (via `scan_solutions_ex` proyectos, o un `os.walk` acotado propio idéntico al patrón `pipeline_stack_detector.py:31-49` si el scanner no está): si hay ≥1 → `{"entry_kind":"csproj","solutions":[...],"reason":"csproj_entry"}`. Si no → `{"entry_kind":"none","solutions":[],"reason":"no_sln"}`.
5. Sin `.sln` y `allow_csproj_entry` False → `{"entry_kind":"none","solutions":[],"reason":"csproj_not_allowed"}` si detectó `.csproj` pero no está permitido, o `"no_sln"` si no hay nada. (Distinguirlos ayuda al mensaje; ambos son bloqueantes.)

**Casos borde (cubrir en tests):** perfil sin `build` → trata como `online_solutions=[]`, `allow_csproj_entry=False`; `online_solutions` con rutas inexistentes → se descartan, cae a escaneo; `.sln` declarado relativo → se resuelve contra `workspace_root`; scanner ausente (`ImportError`) → no crashea, degrada a `no_sln`/`csproj_*`; workspace con solo `.csproj` y `allow_csproj_entry=True` → `entry_kind="csproj"`; ídem con `False` → `entry_kind="none"`, `reason="csproj_not_allowed"`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_resolve_entry.py`:** (usar `tmp_path`, escribir `.sln`/`.csproj` fixtures; monkeypatch `services.solution_scanner.scan_solutions_ex` cuando se quiera aislar del 201)
- `test_workspace_missing_returns_none`
- `test_declared_online_solutions_win` (perfil con `online_solutions=["src/App.sln"]` real → `entry_kind=="sln"`, ruta absoluta)
- `test_empty_online_solutions_falls_back_to_scan` (perfil `online_solutions=[]`, un `.sln` en disco → `entry_kind=="sln"`)
- `test_no_sln_is_blocking` (solo `.csproj`, `allow_csproj_entry` ausente → `entry_kind=="none"`, `reason in {"no_sln","csproj_not_allowed"}`)
- `test_csproj_allowed_when_opted_in` (`allow_csproj_entry=True`, un `.csproj` → `entry_kind=="csproj"`)
- `test_scanner_import_error_degrades` (monkeypatch para simular `ImportError` del scanner → no crashea, `entry_kind=="none"`)
- Registrar en `HARNESS_TEST_FILES`. Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan210_resolve_entry.py -q`

**Criterio BINARIO:** comando verde; `grep -nE "import requests|import runtime$|copilot|llm" "Stacky Agents/backend/services/dev_build_verify.py"` → **0 matches** (núcleo sin red/LLM).

**Flag:** el servicio no chequea flag (lo hace el endpoint F3/los gates F4-F5). **Runtime:** idéntico 3/3. **Trabajo del operador:** ninguno.

---

### F2 — `verify_build` + persistencia del veredicto (invoca el builder del 201)

**Objetivo:** correr el build real (builder del Plan 201) sobre la entrada resuelta, capturar el `build.summary.json`, y producir/persistir un `BuildVerdict`. Valor: el hecho producido por máquina.

**Archivo a editar:** `Stacky Agents/backend/services/dev_build_verify.py`.

**Constante congelada de razones (parte del contrato):**
```python
_REASONS = ("ok", "no_sln", "csproj_not_allowed", "csproj_entry", "build_failed",
            "toolchain_missing", "build_workshop_unavailable", "workspace_missing",
            "stale_verdict", "not_verified")
```
> `stale_verdict` (C1) — NUEVO: lo emite el gate (F4), no `verify_build`; marca "hay un veredicto pero es de otra corrida". Aditivo; 211 no discrimina sobre el set de razones.

**API pública (nombres exactos):**
```python
def verdict_path(ado_id: int, workspace_root: str | None) -> Path
def write_verdict(ado_id: int, workspace_root: str | None, verdict: BuildVerdict) -> None
def read_verdict(ado_id: int, workspace_root: str | None) -> BuildVerdict | None
def verify_build(*, ado_id: int, project_name: str, workspace_root: str | None,
                 execution_id: int = 0) -> BuildVerdict   # C1: liga el veredicto a la corrida
```
- **`read_verdict` (C7 — roundtrip):** al reconstruir el `BuildVerdict` desde el JSON, convertir las listas a tuplas para los campos inmutables (`solutions`, `blocking_findings`, `warnings`) — `json.load` devuelve `list`, el dataclass frozen espera `tuple` → sin esto `test_verdict_roundtrip` fallaría por desigualdad list≠tuple. Campos ausentes (veredictos viejos sin `execution_id`) → default `0`.

- **`verdict_path`**: `Path(workspace_root)/"Agentes"/"outputs"/str(ado_id)/"build.verdict.json"` (mismo layout que el deliverable, `Developer.agent.md:209-210`). Si `workspace_root` es None → `data_dir()/"dev_build_verdicts"/f"{ado_id}.json"` (fallback dev; `from runtime_paths import data_dir`).
- **`write_verdict`**: `mkdir(parents=True, exist_ok=True)` + `json.dumps(asdict(verdict), indent=2, ensure_ascii=False)` con `errors="replace"`. Nunca lanza hacia afuera (best-effort; loguea y sigue).
- **`read_verdict`**: lee y reconstruye el `BuildVerdict`; si el archivo no existe o es inválido → `None` (el caller trata `None` como "no verificado").

**Pseudocódigo `verify_build` (EXCEPCIÓN DURA #3, dependencia del 201, contrato REAL de `get_status` — C2, y ligado a la corrida — C1):**
```python
def verify_build(*, ado_id, project_name, workspace_root, execution_id=0):
    from services.client_profile import load_effective_client_profile
    profile = load_effective_client_profile(project_name) or {}
    entry = resolve_build_entry(profile, workspace_root)
    now = _utcnow_iso()
    if entry["entry_kind"] != "sln":
        # sin .sln => BLOQUEANTE. Nunca "Build OK".
        v = _not_verified(entry["reason"], entry_kind=entry["entry_kind"],
                          solutions=tuple(entry["solutions"]), verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v); return v
    # toolchain (doctor del 201) — read-only, nunca instala (G7)
    tc = _detect_toolchain_safe()          # try import build_toolchain.detect_toolchain; si ImportError => {"available": False,...}
    if not tc.get("available"):
        v = _not_verified("toolchain_missing", entry_kind="sln",
                          solutions=tuple(entry["solutions"]), toolchain=tc, verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v); return v
    # invocar el builder real del 201 (F2 depende de que exista)
    try:
        from services import solution_builder, solution_store
    except ImportError:
        v = _not_verified("build_workshop_unavailable", entry_kind="sln",
                          solutions=tuple(entry["solutions"]), toolchain=tc, verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v); return v
    # mapear cada .sln -> slug del catálogo (rescan idempotente del 201)
    solution_store.rescan_and_save(workspace_root)
    slugs = _slugs_for_solutions(entry["solutions"], workspace_root, solution_store)
    if not slugs:                                    # ningún .sln resolvió a un slug del catálogo
        v = _not_verified("build_failed", entry_kind="sln",
                          solutions=tuple(entry["solutions"]), toolchain=tc, verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v); return v
    build_id = solution_builder.start_build(slugs, unified=(len(slugs) > 1), workspace_root=str(workspace_root))
    envelope = _poll_until_terminal(solution_builder, build_id)   # respeta _VERIFY_POLL_TIMEOUT_SEC; SIEMPRE dict, nunca None
    status = envelope.get("status")                  # top-level del SOBRE (running|success|failed|cancelled|toolchain_missing)
    summary = envelope.get("summary") or {}          # build.summary.json; {} si el 201 no lo pobló al terminal
    rc = _aggregate_returncode(summary)              # 0 sii todas las returncodes son 0 (0 si dict vacío)
    ok = (status == "success" and rc == 0)
    base_dir = summary.get("base_dir") or ""
    summary_path = (os.path.join(base_dir, "build.summary.json") if base_dir else "")
    v = BuildVerdict(
        ok=ok, gate_ok=ok, entry_kind="sln",
        solution=(entry["solutions"][0] if entry["solutions"] else ""),
        solutions=tuple(entry["solutions"]),
        returncode=rc,
        summary_path=summary_path,
        reason=("ok" if ok else "build_failed"),
        toolchain={"available": True, "builder": tc.get("builder"), "version": tc.get("version")},
        build_id=build_id, verified_at=now, execution_id=execution_id,
        blocking_findings=(), warnings=())
    write_verdict(ado_id, workspace_root, v); return v
```
- `_detect_toolchain_safe()`: `try: from services.build_toolchain import detect_toolchain; return detect_toolchain() except Exception: return {"available": False, "builder": None, "version": None, "remediation": None}`.
- **`_poll_until_terminal(builder, build_id)` (C2 — REESCRITO EXPLÍCITO; el 201 `get_status` devuelve un SOBRE, puede ser `None`, y el `summary` es `null` mientras corre):** devuelve SIEMPRE un `dict` sobre `{status, summary}` — nunca `None`. Contrato exacto a implementar (a prueba de modelos menores):
  ```python
  _POLL_INTERVAL_SEC = 2
  _VERIFY_POLL_TIMEOUT_SEC = 1800
  _TERMINAL = {"success", "failed", "cancelled", "toolchain_missing"}
  def _poll_until_terminal(builder, build_id):
      import time
      deadline = time.monotonic() + _VERIFY_POLL_TIMEOUT_SEC
      none_streak = 0
      while True:
          env = builder.get_status(build_id)          # <-- puede ser None (201:620)
          if env is None:
              none_streak += 1
              if none_streak >= 5:                     # None persistente => build perdido
                  return {"status": "failed", "summary": {}}
          else:
              none_streak = 0
              st = env.get("status")
              if st in _TERMINAL:
                  # al terminal, env["summary"] es el build.summary.json (o None por carrera de escritura)
                  return {"status": st, "summary": env.get("summary") or {}}
          if time.monotonic() >= deadline:
              return {"status": "failed", "summary": {}}   # timeout => failed sintético (nunca "ok")
          time.sleep(_POLL_INTERVAL_SEC)
  ```
  Notas: (a) `get_status → None` se reintenta; `None` 5 veces seguidas = `failed` sintético. (b) Se itera sobre el `status` **top-level del sobre**, NO sobre el summary anidado (que es `null` mientras corre). (c) Al terminal se extrae `env["summary"]` (el `build.summary.json`); si por carrera aún es `null`, se devuelve `{}` → `rc=0` pero `status` manda: si `status=="success"` con summary vacío, `ok` queda `True` sin `returncodes` (caso raro; el 201 escribe el summary **siempre** al terminar, 201:699). (d) `summary_path` se **deriva** de `summary["base_dir"]` (no existe `_summary_path` en el 201). (e) timeout → `failed` (jamás "ok").
- `_slugs_for_solutions(...)`: para cada `.sln` en `solutions`, buscar en `solution_store.load_catalog(workspace_root)["solutions"]` el `slug` cuyo `sln_path == esa ruta`; si no está, saltarla (defensivo). Si quedan **0 slugs** → `verify_build` devuelve `build_failed` (arriba), NO invoca `start_build`.
- `_aggregate_returncode(summary)`: `rcs = summary.get("returncodes", {}) or {}`; `max((abs(int(v)) for v in rcs.values()), default=0)`; devuelve 0 sii todos 0 (dict vacío → 0, pero entonces `ok` lo decide `status`).

**Casos borde:** sin `.sln` → `no_sln`/`csproj_not_allowed`, no corre build; toolchain ausente → `toolchain_missing`; builder del 201 ausente (`ImportError`) → `build_workshop_unavailable`; build falla → `build_failed`, `ok=False`; timeout de poll → `build_failed`; **`get_status → None` persistente → `failed` sintético → `build_failed` (C2)**; `.sln` sin slug en catálogo → se omite (si quedan 0 slugs → `build_failed`, sin `start_build`); **`summary` `null` al terminal (carrera) → `rc=0` pero manda `status` (C2)**.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_verify_build.py`:** (monkeypatch: `services.dev_build_verify._detect_toolchain_safe`, `services.solution_builder.start_build`/`get_status`, `services.solution_store.rescan_and_save`/`load_catalog`; `load_effective_client_profile`; `tmp_path` como workspace)
> **Forma del fake `get_status` (C2 — el 201 devuelve un SOBRE, no el summary):** `def fake_get_status(bid): return {"status": "success", "mode": "single", "slugs": ["app"], "log": [], "artifact_ready": True, "error": None, "summary": {"returncodes": {"app": 0}, "base_dir": str(tmp_path), "status": "success"}}`. Mientras "corre" devolver `{"status": "running", ..., "summary": None}`; para `None` devolver `None`.
- `test_no_sln_writes_blocking_verdict_no_build` (assert `start_build` NUNCA se llamó; `read_verdict(...).reason in {"no_sln","csproj_not_allowed"}`, `gate_ok is False`)
- `test_toolchain_missing_verdict` (`_detect_toolchain_safe` → `available False` → `reason=="toolchain_missing"`, `ok is False`, `start_build` no llamado)
- `test_workshop_unavailable_when_builder_import_fails` (simular `ImportError` de `solution_builder` → `reason=="build_workshop_unavailable"`)
- `test_success_verdict_ok_and_gate_ok` (fake `get_status` pasa `running`→`success` con `summary.returncodes={"app":0}` → `ok`, `gate_ok`, `entry_kind=="sln"`, `summary_path` termina en `build.summary.json` derivado de `base_dir`)
- `test_build_failed_sets_reason` (summary `returncodes={"app":1}`, status `failed` → `ok False`, `reason=="build_failed"`)
- `test_get_status_none_is_synthetic_failed` (C2: `get_status` siempre `None` → `_poll_until_terminal` corta en `none_streak` → `reason=="build_failed"`, `ok False`, sin colgar)
- `test_summary_path_derived_from_base_dir` (C2: assert `read_verdict(...).summary_path == os.path.join(base_dir,"build.summary.json")`; NO se usa una key `_summary_path`)
- `test_execution_id_is_stamped` (C1: `verify_build(..., execution_id=77)` → `read_verdict(...).execution_id == 77`)
- `test_verdict_roundtrip` (C7: `write_verdict` luego `read_verdict` reconstruye el mismo `BuildVerdict`, con `solutions`/`blocking_findings`/`warnings` como **tuplas**)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "start_build" "Stacky Agents/backend/services/dev_build_verify.py"` → 1+ match (invoca el builder del 201); `grep -n "_summary_path" "Stacky Agents/backend/services/dev_build_verify.py"` → **0 matches** (esa key inventada NO debe existir; el path se deriva de `base_dir` — C2); el veredicto de `no_sln`/`toolchain_missing`/`build_failed` NUNCA tiene `gate_ok True`.

**Flag:** el endpoint F3 gatea. **Runtime:** idéntico 3/3 (el build es MSBuild/dotnet, no LLM). **EXCEPCIÓN DURA #3** citada (ramas `toolchain_missing` y `build_workshop_unavailable`). **Operador:** ninguno directo (corre dentro del run del agente).

---

### F3 — Endpoint disparador (`POST /api/tickets/by-ado/<ado_id>/dev/build-verify`)

**Objetivo:** exponer `verify_build` por HTTP para que el Developer lo dispare durante su PASO 4. Determinista, server-side. Valor: el agente produce el hecho de máquina como parte de su run.

**Archivo a crear:** `Stacky Agents/backend/api/dev_build.py`.

**Blueprint (patrón `devops_deployments.py` / registro `api/__init__.py`):**
```python
bp = Blueprint("dev_build", __name__)

@bp.post("/tickets/by-ado/<int:ado_id>/dev/build-verify")
def build_verify_route(ado_id: int):
    import config as _config
    from dataclasses import asdict
    if not bool(getattr(_config.config, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)):
        return jsonify({"error": "dev_build_verify deshabilitado"}), 404
    # resolver proyecto + workspace + ejecución del ticket — helpers PÚBLICOS canónicos (F3, reusados por F4/F5/211)
    project_name = dev_build_verify.project_name_for_ado(ado_id)          # Ticket.stacky_project_name (session_scope)
    workspace_root = dev_build_verify.workspace_root_for_ado(ado_id)      # runtime_paths / project config; None-safe
    execution_id = dev_build_verify.latest_execution_id_for_ado(ado_id)   # C1: liga el veredicto a la corrida actual
    verdict = dev_build_verify.verify_build(ado_id=ado_id, project_name=project_name,
                                            workspace_root=workspace_root, execution_id=execution_id)
    return jsonify({"verdict": asdict(verdict)}), 200
```
- Guard por flag con `404` (patrón del 201 F4), usando la **instancia** `_config.config` (memoria `gotcha-config-config-vs-modulo`).
- **Helper público canónico (definido en `dev_build_verify.py`, lo reusan F3/F4/F5 y el Plan 211 — una sola implementación, cero duplicación):**
  - `dev_build_verify.project_name_for_ado(ado_id) -> str | None`: `with session_scope() as s: t = s.query(Ticket).filter(Ticket.ado_id==ado_id).first(); return t.stacky_project_name if t else None`.
  - `dev_build_verify.workspace_root_for_ado(ado_id) -> str | None`: compone `project_name_for_ado` + resolución de workspace (leer `projects/<name.upper()>/config.json → workspace_root`; si el ticket es del proyecto activo, `runtime_paths._active_workspace_root()`; si no, `project_manager.get_project_config(name)["workspace_root"]`). Si no resuelve → `None` (los callers degradan; `verify_build` devuelve `workspace_missing`, no 500).
  - `dev_build_verify.latest_execution_id_for_ado(ado_id) -> int` (C1): la ejecución **más reciente** del ticket (`with session_scope() as s: e = s.query(AgentExecution).join(Ticket, ...).filter(Ticket.ado_id==ado_id).order_by(AgentExecution.id.desc()).first(); return int(e.id) if e else 0`). El implementador confirma la relación `AgentExecution`↔`Ticket` grepeando `class AgentExecution` en `backend/models.py` (memoria `gotcha-session-scope-y-agentexecution-metadata`: los datos viven en `metadata_json`, pero `id`/FK del ticket son columnas). Devuelve `0` si no hay ejecución (el gate degrada best-effort). **Nunca lanza** (try/except → `0`).
- El endpoint F3 usa `ws = dev_build_verify.workspace_root_for_ado(ado_id)`; el gate F4 y la anotación F5 usan **el mismo** helper (no reimplementan la resolución).
- **Siempre responde 200** con el veredicto (aun bloqueante), para que el `api.post` del front/agente lo renderice (memoria `gotcha-frontend-api-wrapper-lanza-en-non-2xx`). Solo `404` si la flag está OFF.

**Registro del blueprint (patrón `api/__init__.py`):**
- Import: `from .dev_build import bp as dev_build_bp  # Plan 210 — gate de build del Developer`
- Registro: `api_bp.register_blueprint(dev_build_bp)  # Plan 210 — /api/tickets/by-ado/<ado_id>/dev/build-verify`

**Casos borde:** flag OFF → `404`; ado_id sin ticket en BD → `project_name=None` → `verify_build` degrada a `workspace_missing` → 200 bloqueante; sin workspace → 200 `workspace_missing`.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_api.py`:** (Flask test client; monkeypatch `dev_build_verify.verify_build` para no correr build real; `_config.config` para flag)
- `test_verify_off_returns_404` (flag OFF)
- `test_verify_returns_verdict_200` (monkeypatch `verify_build` → un `BuildVerdict` fake → `resp.json["verdict"]["gate_ok"]` presente)
- `test_verify_unknown_ado_still_200_blocking` (sin ticket → `verify_build` recibe `project_name None`; assert 200)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.
- **GOTCHA:** para flag OFF/ON en test usar `monkeypatch.setattr(_config.config, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)` sobre la **instancia**, NO `importlib.reload(config)` (memoria `gotcha-config-reload-harness-flags-contamina`).

**Criterio BINARIO:** comando verde; `grep -rn "dev_build_bp" "Stacky Agents/backend/api/__init__.py"` → 2 matches (import + register).

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED`. **Runtime:** idéntico 3/3. **EXCEPCIÓN DURA #3** (rutas doctor/unavailable). **Operador:** ninguno (lo dispara el agente).

---

### F4 — Gate de estado en `_apply_task_state` (fin del avance sin build)

**Objetivo:** que la transición del developer a `next_state_ok` **solo** ocurra si `gate_ok`; si no, degradar a estado de revisión (nunca "Blocked" duro, nunca avanzar). Valor: el consecuencial "developer terminó" pasa a exigir el hecho de máquina.

**Archivo a editar:** `Stacky Agents/backend/api/tickets.py` (y la función pública en `dev_build_verify.py`).

**API pública nueva en `dev_build_verify.py` (la reusa Plan 208):**
```python
def gate_final_state(*, project_name: str | None, agent_type: str | None,
                     ado_id: int, workspace_root: str | None,
                     proposed_state: str | None, execution_id: int = 0) -> tuple[str | None, dict]
```
Lógica exacta (determinista, nunca lanza):
- Si flag OFF (`STACKY_DEV_BUILD_VERIFY_ENABLED`, vía `config.config`) o `agent_type != "developer"` → `(proposed_state, {"applied": False, "reason": "not_applicable"})`.
- `verdict = read_verdict(ado_id, workspace_root)`.
- **Frescura (C1):** si `verdict is not None` y `execution_id` y `verdict.execution_id` son ambos truthy y **distintos** → el veredicto es de **otra corrida** → tratarlo como no-verificado con `reason = "stale_verdict"` (NO usar su `gate_ok`). Si `verdict is None` → `reason = "not_verified"`. En ambos casos `effective_gate_ok = False`.
- Si el veredicto es fresco y `verdict.gate_ok is True` → `(proposed_state, {"applied": True, "gate_ok": True, "reason": verdict.reason})` (deja pasar el estado que resolvió la config/matriz).
- Si NO pasa (`effective_gate_ok False` o `verdict.gate_ok False`) → resolver `review_state` **leyendo el profile directamente** (NO importar de `api.tickets` — evitá el import circular service→api): `machine = (load_effective_client_profile(project_name) or {}).get("tracker_state_machine", {}).get("developer", {})`; `review_state = (machine.get("input_states") or [None])[0]`. Devolver `(review_state, {"applied": True, "gate_ok": False, "reason": <stale_verdict|not_verified|verdict.reason>, "downgraded_from": proposed_state})`. Si `review_state` es falsy → `(None, {...})` (cancelar la transición: mejor dejar el ticket donde está que avanzar en falso — mismo criterio que el `block_guard`, `api/tickets.py:1366-1368`).
> **Nota anti-import-circular (C7):** `dev_build_verify` es un **service**; importa `services.client_profile.load_effective_client_profile` (service→service, OK). NUNCA `from api.tickets import _resolve_agent_block_states` (api importa services, no al revés → romperías el arranque). La lógica de `review_state` es idéntica a `_resolve_agent_block_states` (`api/tickets.py:520-523`) pero replicada localmente para no invertir la dependencia.

**Wiring en `_apply_task_state` (`api/tickets.py:530`) — CONTRA LA ESTRUCTURA REAL (C3):** la función real NO tiene una variable `resolved_state`; resuelve `target = plan.in_progress if phase == "start" else plan.final_ok` (`:542`), corre el centinela `if target not in applicable_states(plan)` (`:546`), chequea `ado_id`/`publish_ok`, y **retorna directo** `_safe_transition(prov, ado_id, target, ...)` (`:553-558`). Insertá el gate **después del centinela `:546` y de los guards de `ado_id`/`publish_ok` (`:548-552`), inmediatamente ANTES de `prov = _provider_for_ticket(...)` (`:553`)**, operando sobre `target` (NO `resolved_state`):
```python
# Plan 210 — gate de build del Developer: no avanzar a final_ok sin veredicto de máquina fresco.
if phase == "final":
    _ws = dev_build_verify.workspace_root_for_ado(int(ado_id))          # ado_id ya resuelto en :548
    _exec_id = dev_build_verify.latest_execution_id_for_ado(int(ado_id)) # C1: corrida actual
    target, _gate_meta = dev_build_verify.gate_final_state(
        project_name=getattr(ticket, "stacky_project_name", None), agent_type=agent_type,
        ado_id=int(ado_id), workspace_root=_ws, proposed_state=target, execution_id=_exec_id)
    if _gate_meta.get("applied"):
        logger.info("dev_build_gate: ADO-%s agent=%s gate_ok=%s reason=%s target=%s",
                    ado_id, agent_type, _gate_meta.get("gate_ok"), _gate_meta.get("reason"), target)
    if target is None:
        return {"skipped": True, "reason": "dev_build_gate_no_state",
                "gate_reason": _gate_meta.get("reason")}
```
- Reusa el `ado_id` ya extraído en `:548` (`ado_id = getattr(ticket, "ado_id", None)`), por eso el gate va **después** de ese guard. El `import` de `dev_build_verify` va arriba del módulo (junto a los otros `from services import ...`).
- **Interacción con el centinela `:546` (C7):** el `review_state` degradado puede NO estar en `applicable_states(plan)`; el gate se inserta **después** del centinela a propósito (el centinela protege el `final_ok` de la matriz, no el estado de revisión, que es un estado legítimo del rol). No re-ejecutar el centinela sobre el estado degradado.
- **Coexistencia con Plan 208 (C5):** 208 edita la línea `plan = resolve_task_state_plan(...)` (arriba, `:541`); este gate va **abajo** (tras `:552`). Ambos coexisten; quien implemente segundo NO reescribe la función (ver "Planes relacionados").

**Rama legacy (flag determinista OFF) — wiring EXPLÍCITO (`api/tickets.py:1385-1416`, C3):** en `set_stacky_status_by_ado`, la rama `elif target_ado_state:` aplica el estado propuesto por el agente. Insertá el gate **después** del `block_guard` (`:1353-1368`, que ya munge `target_ado_state`) y **antes** de la rama determinista/legacy (antes de `:1375`), para que ambas ramas vean el `target_ado_state` gateado:
```python
# Plan 210 — gate de build (rama legacy y determinista comparten este downgrade del target propuesto).
if agent_type == "developer" and bool(getattr(_config.config, "STACKY_DEV_BUILD_VERIFY_ENABLED", False)):
    _ws = dev_build_verify.workspace_root_for_ado(int(ado_id) if ado_id else 0)
    _exec_id = dev_build_verify.latest_execution_id_for_ado(int(ado_id) if ado_id else 0)
    target_ado_state, _lg_meta = dev_build_verify.gate_final_state(
        project_name=t.stacky_project_name, agent_type=agent_type,
        ado_id=int(ado_id) if ado_id else 0, workspace_root=_ws,
        proposed_state=target_ado_state, execution_id=_exec_id)
```
- En la rama determinista (`:1375`) el `target_ado_state` se ignora igual (usa `_apply_task_state`, ya gateado arriba) → sin doble efecto. En la rama legacy (`:1385`) el `target_ado_state` gateado es el que se aplica. Si el gate lo dejó `None`, la rama legacy `elif target_ado_state:` no entra → no transiciona (correcto). `import config as _config` ya está en el módulo.

**Casos borde:** `agent_type != "developer"` → passthrough (no toca ningún otro agente); flag OFF → passthrough; sin veredicto → degrada (`not_verified`); **veredicto de otra corrida → degrada (`stale_verdict`) — C1**; `review_state` desconocido → cancela transición (`target None`); ticket sin `ado_id` → gate corre con `ado_id=0`, `read_verdict` da None → degrada (no crashea).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_state_gate.py`:** (unit de `gate_final_state` con monkeypatch de `read_verdict` y `load_effective_client_profile` — el `review_state` sale del profile, ver nota anti-import-circular; + un test de integración de `_apply_task_state` monkeypatcheando `read_verdict`/`latest_execution_id_for_ado`)
- `test_gate_passthrough_for_non_developer` (agent_type "technical" → estado intacto, `applied False`)
- `test_gate_passthrough_when_flag_off`
- `test_gate_allows_when_verdict_gate_ok` (verdict fresco `gate_ok True` → estado propuesto intacto)
- `test_gate_downgrades_when_no_verdict` (`read_verdict → None` → estado = review_state, nunca next_state_ok, `reason=="not_verified"`)
- `test_gate_downgrades_when_build_failed` (verdict `reason="build_failed"`, `gate_ok False` → review_state)
- `test_gate_downgrades_on_stale_verdict` (**C1**: verdict `gate_ok True` pero `execution_id=41`; gate llamado con `execution_id=42` → downgrade, `reason=="stale_verdict"`, NO deja pasar)
- `test_gate_cancels_when_no_review_state` (profile sin `input_states` → review_state None → `(None, ...)`)
- `test_apply_task_state_early_returns_when_gate_cancels` (integración: `_apply_task_state(phase="final")` con gate → `None` → retorna `{"skipped": True, "reason":"dev_build_gate_no_state"}`, `_safe_transition` NO llamado)
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "gate_final_state" "Stacky Agents/backend/api/tickets.py"` → 2+ matches (determinista + legacy); `grep -n "from api" "Stacky Agents/backend/services/dev_build_verify.py"` → **0 matches** (sin import service→api — C7); un test de regresión existente que ejerce `_apply_task_state`/`stacky-status` sigue verde con flag OFF: `& ".venv\Scripts\python.exe" -m pytest tests\test_finish_work.py tests\test_auto_publish_legacy.py -q` (byte-idéntico, KPI-5).

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED`. **Runtime:** idéntico 3/3 (Python determinista; ningún runner difiere). **Operador:** ninguno; el estado refleja la verdad de máquina.

---

### F4-bis — Guard de cobertura del gate ([ADICIÓN ARQUITECTO 1]) + huella de error (C6, C8)

**Objetivo:** convertir el requisito de coordinación con 208 ("todo path que transiciona el developer pasa por `gate_final_state`") de una **esperanza documentada** a un **test que se pone ROJO** si un path nuevo lo omite; y registrar la huella del anti-patrón que este plan mata. Valor: la clase "falso Build OK" no puede reabrirse en silencio por un plan hermano (208) ni por un refactor futuro.

**Archivos:** ninguno de runtime (es un test + una entrada de datos). Crear `Stacky Agents/backend/tests/test_plan210_gate_coverage.py` y editar `Stacky Agents/docs/sistema/error_fingerprints.json`.

**Guard de cobertura (determinista, sobre el árbol de código — NO importa runtime):**
```python
# Para CADA módulo conocido que transicione el System.State del developer, exigir que
# invoque gate_final_state. Los módulos que aún no existen (208 sin implementar) se saltan.
_SITES = [
    "backend/api/tickets.py",                      # _apply_task_state + rama legacy (F4)
    "backend/services/completion_state.py",        # Plan 208 maybe_apply_state_transition (path remoto)
]
def test_developer_transition_sites_pass_through_gate():
    for rel in _SITES:
        p = _repo_path(rel)
        if not p.exists():          # 208 todavía no implementado => no aplica aún
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        # Solo exigir el gate si el archivo REALMENTE transiciona estado del developer.
        transitions_developer = ("update_item_state" in text or "_safe_transition" in text) and "developer" in text
        if transitions_developer:
            assert "gate_final_state" in text, (
                f"{rel} transiciona estado del developer sin pasar por dev_build_verify.gate_final_state "
                f"(reabre el 'falso Build OK' en el plano remoto — Plan 210 C6)")
```
- **Determinista y barato:** grep de texto, cero LLM, corre igual en los 3 runtimes. Si 208 agrega su path sin el gate, el archivo `completion_state.py` matcheará `_safe_transition`+`developer` sin `gate_final_state` → **ROJO** → obliga a integrar el gate. Registrar en `HARNESS_TEST_FILES`.
- **Nota de acoplamiento honesta:** el heurístico `"developer" in text` puede requerir que 208 nombre el agente en ese módulo; si 208 resuelve por `agent_type` sin la literal, el implementador de 208 debe invocar `gate_final_state` igual (requisito duro §"Planes relacionados") y este test es una red **complementaria**, no la única garantía.

**Huella de error (C8) — agregar a `docs/sistema/error_fingerprints.json`:** una entrada con `id: "dev_build_ok_narrated_unverified"`, `pattern` (el `<span color:green>...Build OK` narrado sin veredicto de máquina), `plan: 210`, `commit: "(pendiente al mergear)"`, `date: "2026-07-21"`, `guard_test: "tests/test_plan210_prompt.py::test_build_section_is_machine_authored"` + `"tests/test_plan210_gate_coverage.py::test_developer_transition_sites_pass_through_gate"`. El implementador confirma el **schema real** del JSON leyéndolo antes de editar (mantener las claves existentes; NO reformatear el archivo entero — memoria de merges silenciosos).

**Tests (TDD):** el propio `test_developer_transition_sites_pass_through_gate` (arriba) + `test_fingerprint_registered` (carga el JSON y asserta que existe la entrada `id=="dev_build_ok_narrated_unverified"` con `guard_test` no vacío). Correr: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan210_gate_coverage.py -q`.

**Criterio BINARIO:** comando verde; `grep -n "dev_build_ok_narrated_unverified" "Stacky Agents/docs/sistema/error_fingerprints.json"` → 1 match.

**Flag:** N/A (test + datos). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F5 — Anotación autoritativa del deliverable (fin del "Build OK" narrado en ADO)

**Objetivo:** que el bloque "3. BUILD" que llega a ADO sea el **veredicto de máquina** (verde solo si `gate_ok`), neutralizando cualquier verde no respaldado que el LLM haya escrito. Punto único: `publish_from_execution`. Además, exponer la **seam de contribuidores** que consume Plan 211. Valor: ADO muestra la verdad, no la narración.

**Archivos a editar:** `Stacky Agents/backend/services/dev_build_verify.py` (funciones) + `Stacky Agents/backend/services/ado_publisher.py` (wiring).

**API pública nueva en `dev_build_verify.py`:**
```python
_EVIDENCE_CONTRIBUTORS: list = []   # Plan 211 registra acá
def register_evidence_contributor(fn) -> None    # fn(ado_id, verdict) -> {"title","section_html","blocking":[...],"warnings":[...]}
def annotate_build_evidence(*, ado_id: int, agent_type: str | None,
                            workspace_root: str | None, html: str) -> str
```

**Lógica de `annotate_build_evidence`:**
1. Si flag OFF o `agent_type != "developer"` → devolver `html` sin cambios (passthrough).
2. `verdict = read_verdict(ado_id, workspace_root)`; si None → construir un veredicto sintético `_not_verified("not_verified")` (para anotar "no verificado").
3. Correr los contribuidores registrados (Plan 211): acumular `section_html` extra, y **fusionar** sus `blocking`/`warnings`. Como `BuildVerdict` es **frozen** (C4/C7), reconstruir con `dataclasses.replace` (preserva `execution_id`, `verified_at`, etc.): `blocking = tuple(verdict.blocking_findings) + tuple(nuevos_blocking)`; `verdict = dataclasses.replace(verdict, blocking_findings=blocking, warnings=tuple(verdict.warnings)+tuple(nuevos_warn), gate_ok=(verdict.ok and verdict.entry_kind=="sln" and not blocking))`. **Re-persistir** con `write_verdict` (para que el gate de estado F4, que en el path MANUAL corre DESPUÉS en el mismo request — publish en `set_stacky_status_by_ado` ~`:1300` precede a `_apply_task_state` `:1381` —, lea los findings del 211). **Nota de orden en paths de runner (C6):** en runners, publish (post-hook) y la transición (daemon de 208) son asíncronos e independientes; el gate leería al menos el veredicto BASE persistido por `verify_build` durante el run (los findings del 211 son best-effort si aún no se fusionaron). Documentado; no bloqueante.
4. Construir el **bloque autoritativo** de máquina (HTML), verde solo si `gate_ok`:
   - `gate_ok True`: `<span style="color:green"><strong>✓ Build OK (verificado por máquina)</strong></span>` + solución(es) + toolchain + returncode + link/nombre del `build.summary.json`.
   - `gate_ok False`: `<span style="color:red"><strong>✗ Build NO verificado</strong></span>` + razón legible (`_REASON_LABEL[reason]`, p.ej. `no_sln`→"No se encontró ninguna solución .sln para compilar", `toolchain_missing`→"Falta el toolchain .NET (ver doctor)", `build_failed`→"La compilación devolvió errores", `build_workshop_unavailable`→"El Taller de Compilación (Plan 201) no está disponible") + los `blocking_findings` si los hay.
5. **Neutralizar** el verde no respaldado del LLM: si `not gate_ok`, reemplazar en `html` cualquier coincidencia (case-insensitive) de un verde de build por una marca tachada. **Dos pasadas (C9 — el gate de estado F4 NO depende de esto; es cosmético/defensa en profundidad):**
   - (a) span verde del prompt: `re.sub(r'(?is)<span[^>]*color\s*:\s*green[^>]*>\s*<strong>\s*[✓✔]?\s*Build OK.*?</strong>\s*</span>', _STRUCK_BUILD_CLAIM, html)`.
   - (b) claim "Build OK" **sin** `<span>` verde (texto plano que un runtime podría inventar): `re.sub(r'(?is)(?<![\w>])[✓✔]\s*Build OK\b', _STRUCK_TEXT, html)` con `_STRUCK_TEXT = '<s>Build OK (no verificado)</s>'` — acotado al `✓/✔` inicial para no tachar la instrucción del prompt ("NO escribas 'Build OK'").
   - `_STRUCK_BUILD_CLAIM = '<span style="color:#888"><s>Build OK (afirmación no verificada — ver veredicto de máquina)</s></span>'`.
   - Contador `dev_build_gate.neutralized_claim` (log). Si se neutralizó ≥1 claim pero el veredicto es `not gate_ok`, **loguear `WARNING` de discrepancia** (`dev_build_gate.claim_vs_machine_mismatch`) — señal de un runtime narrando verde sin respaldo (observabilidad, G6).
6. Insertar el bloque autoritativo: reemplazar el contenido bajo el marcador `<h2>3. BUILD</h2>` si existe (regex hasta el próximo `<hr>`); si no existe el marcador, **anexar** el bloque al final del `html`. Idempotente: si ya está el bloque de máquina (marca comentario `<!-- dev_build_verify -->`), no duplicar.

**Wiring en `ado_publisher.publish_from_execution` — CONTRA EL SHAPE REAL (C4):** `output = html_io.read_and_validate(ado_id, hint=hint)` (`ado_publisher.py:306`) devuelve un **`agent_html_output.HtmlOutput`** que es `@dataclass(frozen=True)` con atributo `.html: str` (NO `.body`), `.path`, `.size_bytes`, `.meta`, `.ado_id` (`agent_html_output.py:49-57`). **NO existe `html_io.replace_body`** (verificado). Como es frozen, hay que construir uno nuevo con `dataclasses.replace`. Insertá el bloque **inmediatamente después de `:306` y ANTES de `html_sha = _output_publish_fingerprint(output)` (`:325`)**, para que el fingerprint/marcador/dedupe operen sobre el HTML **anotado** (si anotaras después, la idempotencia se calcularía sobre el HTML sin anotar):
```python
# Plan 210 — anotar el deliverable con el veredicto de build de máquina (developer).
# Va ANTES de _output_publish_fingerprint(output) (:325) para que el sha cubra lo publicado.
try:
    import dataclasses as _dc
    _agent_type = _agent_type_for_execution(execution_id)   # helper local: lee AgentExecution.agent_type (grep 'agent_type' en models.py)
    _ws = dev_build_verify.workspace_root_for_ado(ado_id)   # helper público (F3), no reimplementar
    _annotated = dev_build_verify.annotate_build_evidence(
        ado_id=ado_id, agent_type=_agent_type, workspace_root=_ws, html=output.html)  # keyword html= (C4)
    if _annotated != output.html:
        output = _dc.replace(output, html=_annotated, size_bytes=len(_annotated.encode("utf-8")))
except Exception:
    logger.exception("dev_build_verify: anotación falló (se publica el original)")  # G6: nunca romper publish
```
- **`dataclasses.replace(output, html=..., size_bytes=...)`** (C4): `HtmlOutput` es frozen → no se puede `output.html = ...` (lanzaría `FrozenInstanceError`). Se recalcula `size_bytes` para mantener el invariante del dataclass.
- **`_agent_type_for_execution(execution_id)`** (C7): helper local nuevo en `ado_publisher.py` que resuelve `AgentExecution.agent_type` en `session_scope`; el implementador confirma el nombre real del atributo grepeando `agent_type` en `backend/models.py`. Si no resuelve → `None` (annotate hace passthrough).
- Envuelto en `try/except` total: si algo falla, se publica el HTML original (G6: la anotación **nunca** rompe la publicación).

**Casos borde:** no developer → passthrough; sin veredicto → bloque "no verificado" + neutraliza verde; deliverable sin sección "3. BUILD" → anexa bloque al final; doble publicación (idempotencia) → no duplica el bloque; HTML sin verde → solo inserta el bloque autoritativo.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_annotate.py`:** (unit de `annotate_build_evidence` con HTML fixture; monkeypatch `read_verdict`)
- `test_passthrough_non_developer`
- `test_ok_verdict_inserts_green_authoritative_block` (verdict `gate_ok True` → contiene "Build OK (verificado por máquina)" en verde)
- `test_no_verdict_neutralizes_llm_green` (HTML con `<span style="color:green"><strong>✓ Build OK</strong></span>`; verdict None → el verde queda tachado y hay bloque rojo "no verificado")
- `test_build_failed_shows_red_reason`
- `test_plain_text_build_ok_is_struck` (**C9**: HTML con `✓ Build OK` en texto plano SIN span verde; verdict None → queda tachado por la pasada (b))
- `test_idempotent_double_annotation` (anotar dos veces no duplica el bloque)
- `test_contributor_findings_flip_gate_and_persist` (registrar un contribuidor fake que devuelve un `blocking` → `gate_ok` pasa a False y `read_verdict` refleja el finding; verificar que `execution_id` se **preserva** tras el `dataclasses.replace`) — cierra la seam de Plan 211
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

**Criterio BINARIO:** comando verde; `grep -n "annotate_build_evidence" "Stacky Agents/backend/services/ado_publisher.py"` → 1+ match; `grep -n "register_evidence_contributor" "Stacky Agents/backend/services/dev_build_verify.py"` → 1+ match.

**Flag:** `STACKY_DEV_BUILD_VERIFY_ENABLED`. **Runtime:** idéntico 3/3 (Python; se aplica sea cual sea el runtime que produjo el HTML). **Operador:** ninguno; ve la verdad en ADO.

---

### F6 — Endurecer el prompt del Developer (paridad 3 runtimes)

**Objetivo:** que el prompt deje de sembrar "Build OK" narrado, dispare el endpoint de verificación en PASO 4, e interprete el veredicto de máquina. Valor: alinea la conducta del LLM con el gate (aunque el gate no dependa de esto).

**Archivo a editar:** `Stacky Agents/backend/Stacky/agents/Developer.agent.md`. Bump `version: "2.1.1"` → `version: "2.2.0"` (frontmatter `:4`).

**Ediciones EXACTAS:**
1. **Quitar el seed "Build OK." (`:301`).** Reemplazar:
   `<p>[2-3 líneas. Ej: "Se modificó <code>ClaseBus.MetodoX()</code> para implementar la validación requerida. Build OK."]</p>`
   por:
   `<p>[2-3 líneas. Ej: "Se modificó <code>ClaseBus.MetodoX()</code> para implementar la validación requerida."]</p>`
   (elimina el string " Build OK." del ejemplo).
2. **Reescribir la sección "3. BUILD" (`:325-327`).** Reemplazar el `<p>` con el verde hardcodeado por:
   ```html
   <h2>3. BUILD</h2>
   <p>[Stacky anexa aquí el <strong>veredicto de build verificado por máquina</strong>. NO escribas "Build OK" a mano: el verde, la publicación y la transición de estado dependen del veredicto determinista de Stacky, no de este texto.]</p>
   <hr>
   ```
3. **Reescribir PASO 4 (`:197-199`).** Reemplazar por:
   ```
   ### PASO 4 — Compilar y verificar (VEREDICTO DE MÁQUINA)

   La verificación de build la produce Stacky, no vos. Tras implementar, dispará el
   veredicto determinista (server-side, sin LLM):

       POST http://localhost:5050/api/tickets/by-ado/{ADO_ID}/dev/build-verify

   Interpretá la respuesta `verdict`:
   - `gate_ok: true` (y `entry_kind: "sln"`) → build verificado. Continuá al PASO 5 con
     `target_ado_state = next_state_ok` del client-profile.
   - `gate_ok: false` → NO afirmes "Build OK". Reportá el bloqueante con `verdict.reason`
     (p.ej. `no_sln`, `toolchain_missing`, `build_failed`) y usá
     `target_ado_state = blocked_state` (o dejá el ticket en revisión). Iterá si `build_failed`
     es por tu cambio; si es `no_sln`/`toolchain_missing`, es un gap de entorno/config: reportalo.

   Aunque no dispares este endpoint, Stacky NO publicará "Build OK" ni avanzará el estado
   sin un veredicto de máquina válido (la ausencia de veredicto = no verificado).
   ```
4. **Nota en COMPILACIÓN (`:152-168`).** Agregar al final de la sección:
   `> Stacky resuelve la solución a compilar así: prefiere client_profile.build.online_solutions; si está vacío, escanea el workspace y toma los .sln encontrados. Un .csproj suelto NO cuenta como build verificable salvo que el perfil declare build.allow_csproj_entry: true.`
5. **Nota en target_ado_state (`:236-240`).** Agregar: `> En modo determinista, Stacky ignora el target_ado_state que mandes y decide next_state_ok vs blocked según el veredicto de build de máquina (Plan 210). No dependas de narrar "Build OK".`
6. Actualizar la firma final `_Developer cliente-agnóstico v2.1.1 — Stacky Agents._` (`:361`) → `v2.2.0`.

**Paridad 3 runtimes:** el prompt es el mismo para Codex/Claude/Copilot; los tres reciben la misma instrucción. Ninguno puede fabricar el veredicto (lo produce el endpoint). Fallback: si un runtime ignora PASO 4, el gate server-side (F4/F5) degrada igual.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan210_prompt.py`:** (lee el archivo del prompt como texto)
- `test_no_hardcoded_build_ok_seed`: el string `Build OK."` (con la comilla del ejemplo) YA NO está en `:301` — assert que la ocurrencia del seed original desapareció. (Buscar la línea del RESUMEN RÁPIDO y verificar que no contiene "Build OK".)
- `test_build_section_is_machine_authored`: la sección `3. BUILD` contiene "verificado por máquina" y NO contiene el `<span style="color:green"><strong>✓ Build OK` hardcodeado.
- `test_paso4_calls_verify_endpoint`: el texto contiene `dev/build-verify`.
- `test_version_bumped`: frontmatter contiene `version: "2.2.0"`.
- Registrar en `HARNESS_TEST_FILES`. Correr por archivo.

> **GOTCHA (memoria `gotcha-plan-comment-matches-own-gate`):** este plan menciona literalmente `Build OK` en su prosa; los tests deben grepear el **archivo del prompt** (`Developer.agent.md`), NO este doc de plan. Escribí los asserts con la ruta del prompt explícita.

**Criterio BINARIO:** comando verde; el patrón del **span verde hardcodeado** desaparece: `grep -nE 'color:green[^>]*>\s*<strong>\s*.{0,3}Build OK' "Stacky Agents/backend/Stacky/agents/Developer.agent.md"` → **0 matches**. (OJO: un `grep "Build OK"` a secas NO da 0 — el texto que queda incluye la instrucción "NO escribas 'Build OK'", que es correcta y no es un claim verde. El gate cuenta SOLO el patrón del span verde.)

**Flag:** el prompt no chequea flag (el gate sí). **Runtime:** idéntico 3/3. **Operador:** ninguno.

---

### F7 — Pane de evidencia en la UI (opcional, alto valor, default ON)

**Objetivo:** mostrar el veredicto de build al operador en el panel de salida, con color y razón. Valor: el operador ve de un vistazo si el build fue verificado.

**Archivos a crear/editar:**
- `Stacky Agents/frontend/src/components/devBuildModel.ts` — helpers PUROS: `verdictColor(v): 'green'|'red'|'gray'`, `verdictLabel(reason): string`, `verdictBadge(v): { text, color }`. Sin render, sin `style={{}}` inline (memoria `gotcha-ratchet-nuevo-archivo-cero-inline-style`).
- `Stacky Agents/frontend/src/components/devBuildModel.test.ts` — vitest por función.
- `Stacky Agents/frontend/src/components/OutputPanel.tsx` — leer `execution.metadata.build_verdict` (poblado en F4/F5 vía metadata) y renderizar un pane distinguible (patrón de los panes auxiliares que cuelgan de `execution.metadata`, `OutputPanel.tsx:140`). Solo para `agentType === "developer"` y si el veredicto existe.

> **Nota de metadata (incluye la seam del Plan 211):** para que la UI reciba el veredicto, F4/F5 deben escribir un resumen en `execution.metadata["build_verdict"]` (`{gate_ok, reason, entry_kind, solution, blocking_findings, warnings}`) al gatear/anotar. Los campos `blocking_findings`/`warnings` salen del `BuildVerdict` **ya fusionado en F5** (los rellenan los contribuidores del Plan 211); **210 es el dueño de esta escritura** — el pane del 211 (su F5) los consume desde esta misma key y degrada limpio si faltan (el 211 NO escribe esta metadata). Agregar esa escritura en F4/F5 (donde ya se tiene el `AgentExecution` en `session_scope`) es el sub-paso mínimo. Backward-compatible: sin la key, el pane no se renderiza.

**Casos borde:** sin `build_verdict` en metadata → pane no aparece (no rompe); `agentType != developer` → no aplica.

**Tests (TDD) — `devBuildModel.test.ts`:** un `it` por función (color/label/badge para `gate_ok true`, `no_sln`, `toolchain_missing`, `build_failed`). Correr: `npx vitest run src\components\devBuildModel.test.ts`.

**Criterio BINARIO:** comando verde; `tsc` del frontend sin errores nuevos (el gate real de UI, memoria `gotcha-rtl-jsdom-structural-gap`: no hay RTL; validar con `tsc` + modelo puro).

**Flag:** el pane depende de que la metadata exista (poblada solo con flag ON). **Runtime:** N/A (UI). **Operador:** ninguno; ve el pane solo.

---

## 5-bis. Orden de implementación (dependencias entre fases)

F0 → F1 → F2 → F3 → F4 → **F4-bis** → F5 → F6 → F7. F1 no depende de F2; F4 y F5 dependen de F2 (leen el veredicto); F4-bis (guard de cobertura + huella) depende de F4 (el gate existe); F7 depende de F4/F5 (metadata). F6 es independiente pero se implementa tras F3 (el prompt cita el endpoint de F3). **Prerequisito externo:** el builder del Plan 201 (F5 del 201). Si aún no está mergeado, F2 degrada a `build_workshop_unavailable` y los tests de F2 monkeypatchean el builder — el plan es implementable y verde, pero el valor real (build verificado de verdad) se materializa cuando el 201 esté en `main`.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|-----------|
| R1 | El 201 no está mergeado → el gate degrada TODO a "no verificado" y bloquea a todos los developers. | `reason == "build_workshop_unavailable"` degrada a **review_state** (no "Blocked" duro); el operador puede avanzar a mano. La flag es toggleable: si molesta antes del 201, se apaga desde UI. KPI-5 (flag OFF = byte-idéntico) garantiza salida. |
| R2 | Toolchain .NET ausente en la máquina del operador → todos los builds `toolchain_missing`. | EXCEPCIÓN DURA #3: doctor del 201 + degradación a review; **nunca** auto-instala. El deliverable dice exactamente qué instalar. |
| R3 | Build lento (hasta 30 min) bloquea el request del endpoint. | El build ya está acotado (`_BUILD_TIMEOUT_SEC=1800` del 201) + `_VERIFY_POLL_TIMEOUT_SEC`. El endpoint corre dentro del run del agente (ya largo). Follow-up posible: modo async con polling desde el agente (fuera de scope). |
| R4 | La regex de neutralización del verde no matchea una variante que el LLM invente. | El gate de **estado** (F4) no depende del HTML: aunque el verde se cuele visualmente, el ticket NO avanza sin `gate_ok`. Además el bloque autoritativo de máquina se inserta siempre. Defensa en profundidad. |
| R5 | Falso negativo: hay `.sln` válido pero el scanner no lo encuentra (árbol raro). | `resolve_build_entry` prefiere `online_solutions` declarado (el operador lo puede fijar en el perfil); el scan es fallback. `truncated` del scanner del 201 avisa. |
| R6 | Colisión con Plan 208 (ambos editan `_apply_task_state`) y el path remoto del daemon de 208 sin gate (C5/C6). | 208 edita `plan=` (`:541`); 210 gatea `target` (tras `:552`) → puntos distintos, coexisten. El **guard de cobertura F4-bis** se pone ROJO si `completion_state.py` (208) transiciona al developer sin `gate_final_state`. Requisito duro en "Planes relacionados". Sin colisión de símbolos. |
| R7 | Romper el publish si la anotación falla. | F5 envuelve la anotación en `try/except` total → se publica el original (G6); `HtmlOutput` frozen → `dataclasses.replace` (C4). |
| R8 | **Veredicto stale de una corrida anterior = falso verde (C1).** | El veredicto lleva `execution_id`; `gate_final_state` degrada a `stale_verdict` si el veredicto no es de la corrida que se cierra. `verified_at` como señal secundaria. Test `test_gate_downgrades_on_stale_verdict`. |
| R9 | **`get_status` (201) devuelve un sobre con `summary` null y puede ser `None` (C2).** | `_poll_until_terminal` reescrito explícito: tolera `None` (streak→failed), itera el `status` top-level, extrae `summary` al terminal, deriva `summary_path` de `base_dir`. Timeout → `failed` sintético (nunca "ok"). Tests `test_get_status_none_is_synthetic_failed`, `test_summary_path_derived_from_base_dir`. |

---

## 7. Fuera de scope (explícito)

- **NO** se implementa el builder ni la UI del Taller de Compilación (eso es Plan 201).
- **NO** se auto-compila fuera de un run del agente ni se auto-instala toolchain (G2/G7).
- **NO** se toca el flujo de otros agentes (technical/functional/QA): el gate es exclusivo de `agent_type == "developer"`.
- **NO** se implementa el inspector post-build ni el barrido de residuos (eso es Plan 211; este plan solo expone la seam `register_evidence_contributor`).
- **NO** se agrega RBAC ni multiusuario (G5).
- **NO** se modifica `harness_defaults.env` a mano (§4).

---

## 8. Glosario + DoD

**Glosario:**
- **`BuildVerdict`** — objeto tipado con el resultado de máquina del build (contrato §5, congelado por F2).
- **`gate_ok`** — booleano rector: `ok and entry_kind=="sln" and not blocking_findings`. Gobierna estado y verde.
- **Entrada canónica** — la(s) `.sln` a compilar: `online_solutions` declarado, o escaneadas; nunca un `.csproj` suelto salvo `allow_csproj_entry`.
- **Doctor** — remediación read-only del toolchain (del Plan 201); nunca instala.
- **Contribuidor de evidencia** — función que Plan 211 registra para sumar findings/HTML al bloque de build (seam de F5).

**Definition of Done (binario):**
1. Los 9 archivos de test (`test_plan210_flag`, `_resolve_entry`, `_verify_build`, `_api`, `_state_gate`, `_gate_coverage` [F4-bis], `_annotate`, `_prompt`, + `devBuildModel.test.ts`) → **verdes**, corridos por archivo con el venv del repo, y todos los `test_plan210_*.py` registrados en `HARNESS_TEST_FILES`.
2. `grep -n "gate_final_state\|annotate_build_evidence\|register_evidence_contributor" "Stacky Agents/backend/services/dev_build_verify.py"` → 3+ matches; `grep -n "from api" "Stacky Agents/backend/services/dev_build_verify.py"` → **0** (sin import service→api, C7); `grep -n "_summary_path" "Stacky Agents/backend/services/dev_build_verify.py"` → **0** (C2).
3. `grep -rn "dev_build_bp" "Stacky Agents/backend/api/__init__.py"` → 2 matches; `grep -n "gate_final_state" "Stacky Agents/backend/api/tickets.py"` → 2+ (determinista + legacy, C3).
4. Con flag OFF: la suite existente de `stacky-status`/`_apply_task_state`/`ado_publisher` pasa **byte-idéntica** (KPI-5); comando concreto verde: `& ".venv\Scripts\python.exe" -m pytest tests\test_finish_work.py tests\test_auto_publish_legacy.py -q`.
5. El prompt `Developer.agent.md` no contiene el patrón `color:green...Build OK` hardcodeado y sí contiene `dev/build-verify` (F6).
6-bis. **(C1)** `test_gate_downgrades_on_stale_verdict` verde: un veredicto `gate_ok True` de otra `execution_id` NO deja avanzar (`reason=="stale_verdict"`). **(C6/C8)** `grep -n "dev_build_ok_narrated_unverified" "Stacky Agents/docs/sistema/error_fingerprints.json"` → 1 match, y `test_developer_transition_sites_pass_through_gate` verde.
6. **Smoke E2E (manual, documentado como pendiente):** correr un developer real sobre un proyecto con `.sln` y toolchain presente → `build.verdict.json` con `gate_ok true`, ADO recibe "Build OK (verificado por máquina)" verde y transiciona a `next_state_ok`; repetir con un cambio que no compila → `gate_ok false`, ADO en rojo y ticket en revisión. (El smoke real depende del Plan 201 mergeado.)

**Trabajo del operador:** ninguno (opt-in default ON; degrada solo y con doctor si falta toolchain). Config toggleable desde Configuración → Arnés → DevOps.
