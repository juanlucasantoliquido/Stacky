# Plan 213 — Analistas que infieren y declaran SUPUESTOS en vez de frenar el pipeline

> Estado: **v2 · CRITICADO — APROBADO-CON-CAMBIOS (v1 RECHAZADO por C1/C2; corregidos en esta versión)** (2026-07-23). Pipeline: proponer ✓ → **criticar ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor v1: StackyArchitectaUltraEficientCode (perfil max). Juez v2: StackyArchitectaUltraEficientCode (perfil normal, heredado de Fable 5), crítica contra evidencia releída del repo el 2026-07-23.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria).
> Origen: **incidencia reportada por el operador** — *"Que empiece a inferir bloqueantes y lo marque como supuesto para evitar bloqueos: el Analista Técnico y el Funcional."*

---

## v1 → v2 — Changelog de la crítica adversarial (2026-07-23)

**Veredicto sobre v1: RECHAZADO** (2 bloqueantes verificados contra el repo). v2 los corrige todos.

- **C1 (BLOQUEANTE) — El "chokepoint post-run único de los 3 runtimes" NO existe.** `harness/post_run.py:finalize_run` lo invoca **solo el runner de codex** (`codex_cli_runner.py:966-967`). Claude corre `contract_validator` + `confidence` **inline** (`claude_code_cli_runner.py:2244-2260`, metadata en `:1781`) y el path de copilot lo hace `agent_runner.py:890` (verificado: `grep finalize_run` da 0 hits en `claude_code_cli_runner.py` y 0 en `agents/`). La F4 de v1 persistía supuestos **solo para codex** → KPI-2 (100% de ejecuciones con la clave) era matemáticamente imposible, y `assumption_overload` solo frenaba en codex. La cobertura de v1 apuntaba además al archivo equivocado (`agents/base.py`; el post-procesamiento copilot vive en `agent_runner.py`). **Fix:** F4 reescrita como helper único `assumptions.apply_to_metadata(...)` + **3 call-sites explícitos** con test por call-site y grep-gate de 4 matches.
- **C2 (BLOQUEANTE) — Orden de fases contradictorio dentro del propio doc.** v1 documentaba §4 en orden F0,F1,F2,F3 pero exigía en §8 el orden F0→F1→F3→F2. `implementar-plan-stacky` implementa "fase por fase F0..Fn" en orden documental: un implementador (o modelo menor) que siga §4 abre la ventana en la que los prompts ya piden `[SUPUESTO]`/`[PENDIENTE:` mientras `confidence.py:33` sigue restando **8 puntos por `"[PENDIENTE"`** (verificado) → `needs_review` → **el freno vuelve por la puerta de atrás**. Peor: incluso el orden de §8 dejaba una ventana F1→F3 (F1 activa la política con flag **default ON** antes de que exista la exención de scoring). **Fix:** fases renumeradas — **el orden de lectura ES el orden de ejecución**: F0 parser → **F1 scoring/contrato (aterriza dormido)** → **F2 flags+política (enciende todo atómicamente)** → **F3 prompts** → F4..F7. La ventana desaparece por construcción.
- **C3 (IMPORTANTE) — `agent_type` no está en scope** donde v1 mandaba concatenar la política: `_build_system_prompt` (claude, `:2370-2400`) y `_build_codex_prompt` (codex, `:1367-1387`) reciben `selected_agent: VsCodeAgent`, que **solo tiene `name` y `filename`** (`services/vscode_agents.py:31-33`) — el diff de v1 producía `NameError`. **Fix:** F2 especifica el threading del kwarg `agent_type` desde los callers.
- **C4 (IMPORTANTE) — Coordinación con planes hermanos incompleta y una afirmación falsa.** (a) v1 decía "208 y 213 no comparten archivos": **falso** — ambos tocan `api/tickets.py` (208 endpoints de estado; 213 el board del Desatascador `:2748-2783`). (b) La sesión paralela del **Plan 212** tiene `UnblockerPage.tsx` **modificado ahora mismo** (git status) y F7 lo edita. **Fix:** bullets de coordinación corregidos/agregados.
- **C5 (IMPORTANTE) — G2.3 prometía una regla no implementada en ninguna fase** ("más del 40% de sus secciones son supuesto" — sin definición de "sección", sin fase, sin test). **Fix:** cláusula eliminada; el techo numérico `STACKY_ASSUMPTION_MAX_PER_RUN` es la única regla (determinista).
- **C6 (IMPORTANTE) — KPI-1 no era medible:** "contador" emitido a un logger no es consultable. **Fix:** `blocked_without_pending` es ahora un booleano **persistido en `metadata.assumptions`** (detección determinista en F0) y el KPI se mide sobre metadata.
- **C7 (MENOR) — Ambigüedad del bonus de F1:** el bonus `assumption_discipline` debe calcularse sobre el texto **original** (el texto stripped ya no contiene `[SUPUESTO`); assert del test precisado (`score_with >= score_without`).
- **C8 (MENOR) — `tests/test_intent_preflight.py` no existe**; los reales son `test_intent_preflight_{contract,generate,ranking}.py` (verificado con Glob). Comando de F0 corregido, sin fallback vago.
- **C9 (MENOR) — `render_html_block` era API muerta:** ninguna fase la llamaba (la sección HTML "Supuestos asumidos" la escribe el propio agente por plantilla de F3; el panel de F5 renderiza desde metadata). Eliminada de F0.
- **C10 (MENOR) — Caso borde del endpoint F5:** `index` fuera de rango no estaba especificado → `400 {"error": "invalid_index"}` + test.
- **C11 (MENOR) — Drift de anclas y conteos:** `_RULES_MCP` es `:40-64` (no `:61`); contract functional `:61-71`, technical `:73-90`, loop de evasión `:188`; `text_lower` en `confidence.py:82`; bloque de bonus `:97-107`; `metadata_dict` en `models.py:260`; los archivos de test backend nuevos son **8**, no 7. Todo corregido.
- **[ADICIÓN ARQUITECTO A1] — Las correcciones del operador se ACUMULAN entre corridas.** v1 solo inyectaba la última ejecución con ítems no-pending: si el operador corregía en la corrida N y confirmaba otra cosa en N+1, la decisión de N se perdía en N+2. F6 ahora acumula las últimas **3** ejecuciones con dedupe por texto (gana la más reciente). Ninguna decisión del operador se evapora — refuerzo directo de G1/HITL.
- **[ADICIÓN ARQUITECTO A2] — Truncado determinista anti-supuesto-gigante:** `parse()` trunca `text` a 500 chars y `basis` a 300 (sufijo `…`), para que un supuesto desbordado no infle `metadata_json`, el panel ni el board. Con test.

---

## Planes relacionados (leer antes de implementar)

- **PORTA la política ya probada del BusinessAgent.** El Agente de Negocio **ya hace exactamente esto** desde hace tiempo: `backend/Stacky/agents/BusinessAgent.agent.md:90-95` (*"Sos muy proactivo: no frenás para preguntar… adoptás la interpretación más razonable, la dejás explícita como `[SUPUESTO: ...]` y seguís"*), con bloque visible de supuestos (`:223-233`) y métrica de grounding (`:76-83`). Este plan **generaliza esa política** a los dos analistas y le agrega el motor determinista (parser, persistencia, UI, bucle de corrección) que el BusinessAgent nunca tuvo.
- **REUSA el patrón de autonomía del Documentador.** `backend/Stacky/agents/Documentador.agent.md:28` (*"Si te falta un dato, inferís un valor válido y seguro… documentás el supuesto tomado con marca `[INF]` — jamás frenás la corrida"*), con **gate determinista de marcas** en `backend/services/doc_documenter.py:165,:190`. Ese gate es el modelo a copiar en F1.
- **REUSA `IntentAssumption` (Plan 41).** `backend/services/intent_preflight.py:29-34` ya define el supuesto tipado (`text`, `impact`, `needs_confirmation`), su ranking (`rank_and_flag` `:197`), sus preguntas derivadas (`derive_open_questions` `:182`) y el **bloque de correcciones del operador de máxima prioridad** (`build_corrections_block` `:206`, id `operator-corrections`, prioridad **110** en `context_enrichment.py:373`). Este plan **no inventa un tipo nuevo**: extiende ese y cierra el bucle con él.
- **COORDINA con Plan 208** (sync ADO al completar + matriz de estados). 208 decide *a qué estado* transiciona el ticket al completar; este plan cambia *cuándo el analista se declara completo* (ya no queda esperando respuesta humana por un bloqueante inferible). **SÍ comparten `api/tickets.py`** (corregido C4: 208 toca endpoints de estado; 213 toca el board del Desatascador `:2748-2783` — regiones distintas, cambios aditivos, releer el archivo en frío antes de editar). 213 toca además prompts, `harness/post_run.py`, `contract_validator.py`, `services/confidence.py`, `claude_code_cli_runner.py` y `agent_runner.py` (C1). Interacción sana: con 213 habrá **más** ejecuciones que llegan a `completed`, que es justo lo que 208 sincroniza; este plan **no toca** el chokepoint de completación `ticket_status.on_execution_end` ni la matriz de estados del 208.
- **COORDINA con Plan 212** (selector vivo de modelo/effort). La sesión paralela del 212 tiene **`UnblockerPage.tsx` modificado sin commitear ahora mismo** (git status 2026-07-23). F7 edita ese archivo: quien implemente segundo **relee el archivo en frío**, integra de forma aditiva y verifica con `npx tsc --noEmit` tras el merge. Ídem `api/tickets.py`.
- **COORDINA con Plan 209** (playbook "cómo validar esto" al terminar una task). 209 anexa al deliverable una guía de validación; 213 anexa el bloque de supuestos. **Ambos escriben en el deliverable final del agente**: quien implemente segundo **integra**, no clobberea. Orden de bloques acordado en el deliverable: `…contenido del análisis…` → **Supuestos asumidos (213)** → **Cómo validar esto (209)**. Verificación tras merge: `grep -n "Supuestos asumidos" backend/services/*.py` **y** `grep -n "Cómo validar" backend/services/*.py` → ambos con 1+ match.
- **COORDINA con Plan 210/211** (gate de build + inspector). Los tres tocan `harness/post_run.py:finalize_run` (chokepoint compartido de los 3 runtimes). 213 solo **agrega una clave** a `metadata_patch` (`assumptions`); 210 agrega `build_verdict`; 211 agrega findings. Son claves disjuntas → componen. Regla dura: **agregar** claves a `metadata_patch`, jamás reasignar el dict entero.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Hoy, cuando al Analista Técnico o al Funcional les falta un dato, el sistema **para y espera al humano**: el Técnico publica una *"❓ CONSULTA TÉCNICA (pre-bloqueo)"* y deja el ticket en el estado de revisión esperando respuesta (`TechnicalAnalyst.v2.agent.md:107-109,:157-164`), y el Funcional tiene la regla dura *"Cero ambigüedad… declararla en Preguntas abiertas"* (`FunctionalAnalyst.agent.md:316`) — una sección que **su propia plantilla de salida ni siquiera declara** (`:186-232`, secciones 1..7, ninguna se llama así). El resultado es un pipeline que se detiene por información que, en la enorme mayoría de los casos, **es inferible con la documentación y el perfil de cliente que el agente ya tiene en contexto**. Este plan invierte el default: **el analista infiere la interpretación más razonable, la declara explícitamente como `[SUPUESTO: … | base: … | impacto: …]` y sigue hasta terminar**; el supuesto queda **tipado, persistido, visible y confirmable en un click** por el operador, y su confirmación/corrección **vuelve como contexto de máxima prioridad** a la siguiente corrida. Frenar deja de ser el default y pasa a estar reservado para el dato duro imposible de inferir (`[PENDIENTE: …]`).

**Gap que cierra.** Convierte "me falta un dato" de un **freno del pipeline** en un **artefacto de trabajo trazable**: el trabajo avanza, el riesgo queda declarado y el operador decide sobre hechos concretos en vez de sobre una pregunta abierta que lo obliga a reconstruir el contexto.

**KPI / impacto medible (binarios).**
- **KPI-1 — Cero frenos por información inferible:** ejecuciones de `technical`/`functional` que terminan publicando una consulta pre-bloqueo **y** dejan el ticket esperando respuesta: **0**, salvo que el output contenga al menos un `[PENDIENTE: …]` justificado. Medible **[C6]**: booleano `metadata.assumptions.blocked_without_pending` persistido por ejecución (F0 detecta, F4 persiste); ninguna ejecución con flag ON debe tenerlo en `true`.
- **KPI-2 — Supuestos siempre explícitos:** 100% de las ejecuciones de los dos analistas con la flag ON producen la clave `metadata.assumptions` (aunque sea lista vacía). Medible: presencia de la clave.
- **KPI-3 — Supuestos con respaldo:** ≥ 80% de los supuestos declarados traen `base:` no vacía. El resto se marca `impacto: alto` automáticamente y encabeza la lista. Medible: ratio calculado en F4 y expuesto en el panel.
- **KPI-4 — Ningún supuesto se pierde:** 100% de los supuestos de impacto alto sin confirmar aparecen en el Desatascador (F7). Medible: conteo cruzado panel ↔ board.
- **KPI-5 — El bucle cierra:** una corrección del operador sobre un supuesto aparece en la corrida siguiente del mismo ticket dentro del bloque `operator-corrections` (prioridad 110). Medible: test de integración de F6.
- **KPI-6 — El sistema deja de castigar la honestidad:** un output con `[SUPUESTO: …]` canónicos **no** pierde puntos de confidence por hedge (hoy pierde **8 por ocurrencia** — `services/confidence.py:85-89`; incluye `"[PENDIENTE"` en `:33`). Medible: test de F1.
- **KPI-7 — Cero regresión:** con `STACKY_ASSUMPTION_MODE_ENABLED=false`, prompts, scoring, contrato y metadata son byte-idénticos a hoy.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada)

Anclas **releídas contra el repo el 2026-07-22**. Rutas relativas a `Stacky Agents/`.

### 2.1 El Técnico está diseñado para frenar

- `backend/Stacky/agents/TechnicalAnalyst.v2.agent.md:100-102` — PASO 4 define *"**Bloqueante** = condición que, sin resolverse, llevaría al Developer a implementar algo incorrecto o imposible."*
- `:107` — tabla de decisión: *"Hay preguntas funcionales sin respuesta tras leer la doc funcional → Publicar análisis parcial + **❓ CONSULTA TÉCNICA (pre-bloqueo)** … → **dejar el ticket en el estado de revisión** `{…technical.input_states[0]}`"*.
- `:157-164` — la plantilla de salida reserva la sección 6 para esa consulta y cierra con *"El ticket NO se bloquea: queda en el estado de revisión esperando tu respuesta."*
- `backend/agents/technical.py:35-39` — el system prompt Python dice lo mismo: *"Si detectás un bloqueante, NO bloquees el ticket: primero publicá una consulta al humano … y **dejá el ticket en su estado de revisión. Esperá la respuesta humana**"*.
- **Cero ocurrencias** de `SUPUESTO`, `asum` o `infer` en todo el prompt del Técnico (verificado).
- Traducción operativa: **"no bloquea el ticket" ≠ "no frena el trabajo"**. El ticket queda parado igual, esperando a un humano. Ese es el freno real que reporta el operador.

### 2.2 El Funcional tiene la regla contraria y una sección fantasma

- `backend/Stacky/agents/FunctionalAnalyst.agent.md:316` — REGLA DURA: *"**Cero ambigüedad.** Si después de leer la documentación queda ambigüedad, declararla en «Preguntas abiertas» con al menos 2 opciones concretas."*
- Esa sección **no existe** en su plantilla `analisis-funcional.md` (`:186-232`: secciones 1..7, ninguna se llama "Preguntas abiertas"). El agente tiene una regla que apunta a un contenedor inexistente → o la ignora, o improvisa una sección fuera de contrato.
- Sin embargo el Funcional **ya conoce el marcador**: `:90-91` (*"Si el `process_catalog` no está presente, marcá los procesos que menciones como `[SUPUESTO]`"*), `:88-89`, `:219`. Es decir, **la mitad del comportamiento ya está**; falta generalizarla y darle contenedor.
- `backend/agents/functional.py:18-43` — el system prompt Python del Funcional **no dice nada** sobre bloqueantes ni supuestos.

### 2.3 El sistema hoy CASTIGA inferir (el punto más importante y menos obvio)

- `backend/services/confidence.py:17-34` — `_HEDGE_PHRASES` incluye literalmente `"asumo que"`, `"supongo que"`, `"no puedo determinar"`, `"[PENDIENTE"`. Cada ocurrencia resta **8 puntos** (`:85-89`).
- `backend/contract_validator.py:66-70` (functional) y `:85-89` (technical) — `forbidden_phrases` penaliza `"no tengo información"`, `"no puedo determinar"`, `"requeriría más contexto"`; y `_EVASION_PHRASES` (`:122-127`) suma más penalización. **Pero ninguna regla premia ni exige `[SUPUESTO]`.**
- El score de confidence alimenta el post-run (`harness/post_run.py:77-81`) y `needs_review`.
- **Consecuencia:** si mañana se cambiara solo el prompt, el analista que empieza a asumir vería **caer su confidence** y podría terminar en `needs_review` — es decir, el pipeline se frenaría igual, por otra puerta. **Cambiar el prompt sin tocar el scoring es una trampa; F1 existe exactamente por esto y por eso va ANTES que cualquier cambio de prompt (C2).**

### 2.4 Ya existe todo el andamiaje para hacerlo bien (no hay que inventar nada)

| Pieza que ya existe | Ancla | Rol en este plan |
|---|---|---|
| Supuesto tipado + ranking + preguntas | `services/intent_preflight.py:29-34,:182,:197` | tipo canónico (F0) |
| Bloque de correcciones del operador, prioridad 110 | `services/intent_preflight.py:206-223` + `context_enrichment.py:373` | cierre del bucle (F6) |
| Gate determinista de marcas `[V]/[INF]/[NV]` | `services/doc_documenter.py:165,:190` | patrón del gate (F1) |
| Parser de `[SUPUESTO` en épicas | `api/tickets.py:6198` | precedente del regex |
| Pipeline post-run de **codex** | `harness/post_run.py:35` `finalize_run` (⚠️ C1: **solo codex lo invoca**, `codex_cli_runner.py:966`) | call-site 1 de persistencia (F4) |
| Path de calidad inline de **claude** | `claude_code_cli_runner.py:2244-2260` (contract+confidence), metadata `:1781` | call-site 2 de persistencia (F4) |
| Path de calidad de **copilot** | `agent_runner.py:890` (`contract_validator.validate`) | call-site 3 de persistencia (F4) |
| Punto único de reglas para claude+codex | `harness/run_contract.py:40-64` `rules_text` | inyección de política (F2) |
| Composición de prompt de copilot | `agents/base.py:56` `compose_system_prompt` | paridad 3er runtime (F2) |
| Bandeja de revisión y Desatascador | `pages/ReviewInboxPage.tsx`, `pages/UnblockerPage.tsx` + `api/tickets.py:2604-2830` | visibilidad (F7) |

### 2.5 El guard anti-auto-bloqueo ya impide lo peor (y por eso el problema es "quedarse esperando")

`backend/api/tickets.py:1345-1368` — con `STACKY_BLOCK_GUARD` (default `"on"`) y sin header `X-User-Email` (origen agente), cualquier intento de mover el ticket a `blocked_state` se fuerza al estado de revisión. Y `backend/harness/task_states.py:37-39` deja `blocked_state` fuera de las transiciones automáticas *a propósito*. **Es decir: el agente ya no puede bloquear.** Lo que sí puede —y hace— es **terminar sin avanzar y dejar el ticket esperando**. Este plan ataca eso, sin tocar el guard.

---

## 3. Principios y guardarraíles (no negociables)

- **G1 — Human-in-the-loop INTACTO y REFORZADO.** Inferir **no** es decidir por el operador: es **preparar la decisión**. Nada se auto-publica ni se auto-aprueba que no se publicara ya hoy (el analista ya publica su análisis). El supuesto es **visible, tipado y confirmable en un click**, y su corrección **manda** sobre el supuesto en la corrida siguiente (bloque de prioridad 110). El operador termina viendo **más** verdad, no menos: hoy un supuesto tácito del LLM no se ve en ningún lado.
- **G2 — Anti-alucinación operacionalizado.** Un supuesto sin respaldo es peligroso, no cómodo. Reglas duras, verificadas por máquina (F0/F1):
  1. Todo supuesto declara su **base** (`base: <doc/módulo/dato>`), o queda auto-clasificado `impacto: alto` y **encabeza** la lista.
  2. **`[PENDIENTE: …]` sigue existiendo** para el dato duro imposible de inferir (valor numérico que nadie dio, credencial, decisión de negocio). Inferir un `[PENDIENTE]` está prohibido.
  3. **Techo de supuestos:** si un análisis supera `STACKY_ASSUMPTION_MAX_PER_RUN` (default **10**), el post-run marca `needs_review` con razón `assumption_overload`. **Inferir no puede degenerar en inventar.** *(C5: la regla "40% de las secciones" de v1 se eliminó — no era implementable de forma determinista y ninguna fase la construía; el techo numérico es la única regla.)*
- **G3 — Cero trabajo extra al operador.** El cambio es invisible en el camino feliz: el analista simplemente ya no se frena. El panel de supuestos es lectura pasiva; confirmar es opcional (los no confirmados no bloquean nada, solo quedan visibles).
- **G4 — Paridad de 3 runtimes.** La política se inyecta en el punto que cubre claude+codex (`harness/run_contract.py`) **y** en el que cubre copilot (`agents/base.py` + los `system_prompt()` de los dos analistas). El parser, la persistencia, el gate y la UI son Python/TS deterministas → idénticos en los 3.
- **G5 — No degradar.** El parser es puro y O(n) sobre el texto del output; corre una vez por ejecución en el post-run que ya existe. Sin llamadas de red, sin LLM adicional, sin tokens extra.
- **G6 — Ámbito acotado por allowlist explícita.** La política aplica **solo** a `technical` y `functional` (lo que pidió el operador). El BusinessAgent y el Documentador ya la tienen por su cuenta; el Developer y QA **no** la reciben (un developer que "asume" que compila es exactamente el falso verde que combate el Plan 210). Allowlist en `STACKY_ASSUMPTION_MODE_AGENT_TYPES`, default `"technical,functional"`.
- **G7 — Config del operador vía UI.** Toda flag nueva se registra en `harness_flags.py` (editable desde la UI de flags), nunca env-only.
- **G8 — Backward-compatible.** Flag OFF ⇒ prompts, scoring, contrato y metadata byte-idénticos a hoy.

> Convención de tests: **backend** = pytest **por archivo**; **frontend** = vitest **por archivo**.
> **Comando backend** (desde `Stacky Agents/backend`): `& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q` (si no hay `.venv`, usar `venv\Scripts\python.exe`).
> **Comando frontend** (desde `Stacky Agents/frontend`): `npx vitest run src\<ruta>\<archivo>.test.ts`.
> **Ratchet:** todo `backend/tests/test_*.py` nuevo va en `backend/scripts/run_harness_tests.sh` (array en `:20`, **sin** comillas) **y** en `backend/scripts/run_harness_tests.ps1` (array en `:13`, **con** comillas), o `test_harness_ratchet_meta.py:43-53` se pone rojo.

---

## 4. Fases

### F0 — El vocabulario canónico del supuesto y su parser determinista

**Objetivo (1 frase).** Un formato único de supuesto, parseable por máquina desde texto **y desde HTML**, con reglas de impacto deterministas.

**Archivo a crear:** `Stacky Agents/backend/services/assumptions.py`
**Archivo a editar:** `Stacky Agents/backend/services/intent_preflight.py` (extensión aditiva del tipo existente)

**Formato canónico (el que van a escribir los agentes):**

```
[SUPUESTO: <afirmación concreta> | base: <evidencia o "sin respaldo"> | impacto: alto|medio|bajo]
[PENDIENTE: <dato duro imposible de inferir> | necesito: <qué exactamente>]
```

Tolerancias obligatorias del parser (los LLMs no son perfectos y el prompt debe poder fallar sin romper nada):
- `[SUPUESTO: texto]` sin `base` ni `impacto` → válido; `basis=""`, `impact="high"` (**regla dura G2.1**).
- Con `base` no vacía y sin `impacto` → `impact="medium"`.
- `impacto` en español (`alto|medio|bajo`) se normaliza a `high|medium|low`.
- Insensible a mayúsculas en las etiquetas (`SUPUESTO`, `Supuesto`, `base:`, `Base:`).
- **Debe funcionar sobre HTML**: el Analista Técnico escribe `comment.html` (`TechnicalAnalyst.v2.agent.md:118`). Antes de parsear, si el texto contiene `<` y `>`, pasarlo por `services.ado_context._html_to_text` (la misma función que ya usa `business_preflight.py:102`). **Sin esto, el parser no ve nada del Técnico** — es el mismo tipo de trampa que el hallazgo C4 del Plan 209.

**Extensión aditiva de `IntentAssumption` (`intent_preflight.py:29-34`):**

```python
 @dataclass(frozen=True)
 class IntentAssumption:
     text: str
     impact: str              # "high" | "medium" | "low"
     needs_confirmation: bool
+    basis: str = ""          # Plan 213 — evidencia citada; "" = sin respaldo (⇒ impacto alto)
```
- `to_payload()` (`:109-127`) incluye `basis`.
- `from_model_json()` (`:78-106`) lee `basis` si está, `""` si no.
- Default `""` ⇒ **todo caller existente sigue funcionando sin cambios** (G8).

**API de `services/assumptions.py`:**

```python
_ASSUMPTION_RE = re.compile(
    r"\[SUPUESTO:\s*(?P<text>[^|\]]+?)"
    r"(?:\s*\|\s*base:\s*(?P<basis>[^|\]]*))?"
    r"(?:\s*\|\s*impacto:\s*(?P<impact>alto|medio|bajo))?"
    r"\s*\]",
    re.IGNORECASE,
)
_PENDING_RE = re.compile(
    r"\[PENDIENTE:\s*(?P<text>[^|\]]+?)"
    r"(?:\s*\|\s*necesito:\s*(?P<needs>[^|\]]*))?\s*\]",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class AssumptionReport:
    assumptions: tuple[IntentAssumption, ...]   # ordenadas: alto → medio → bajo
    pending: tuple[dict, ...]                   # [{"text": ..., "needs": ...}]
    unbased_count: int
    overload: bool                              # supera el techo de G2.3
    marks_ok: bool                              # hay al menos un marcador canónico
    blocked_without_pending: bool               # C6/KPI-1: consulta pre-bloqueo SIN [PENDIENTE

def parse(output: str) -> AssumptionReport: ...
def to_metadata(report: AssumptionReport) -> dict: ...   # {"assumptions": {...}} listo para metadata_patch
def strip_canonical_marks(text: str) -> str: ...         # borra matches de _ASSUMPTION_RE y _PENDING_RE (F1)
```

*(C9: v1 declaraba `render_html_block(...)` — API muerta, ninguna fase la llamaba: la sección HTML "Supuestos asumidos" la escribe el propio agente por plantilla (F3) y el panel de F5 renderiza desde metadata. **Eliminada.**)*

Reglas exactas de `parse`:
1. Normalizar HTML→texto si corresponde (arriba).
2. Extraer supuestos y pendientes; **deduplicar** por `text.strip().lower()`.
3. **[A2] Truncado determinista:** `text` se trunca a **500** chars y `basis` a **300** (agregando sufijo `…` si se truncó), ANTES de deduplicar. Un supuesto desbordado no infla `metadata_json`, el panel ni el board.
4. `needs_confirmation = (impact == "high")`.
5. Ordenar con `intent_preflight._IMPACT_ORDER` (**reuso**, no reimplementar).
6. `overload = len(assumptions) > config.STACKY_ASSUMPTION_MAX_PER_RUN`.
7. `marks_ok = bool(assumptions or pending)`.
8. **[C6] `blocked_without_pending`** = el texto normalizado contiene `"CONSULTA TÉCNICA (pre-bloqueo)"` (comparación case-insensitive) **y** `pending` está vacío. Es la detección determinista del KPI-1; se persiste en metadata (F4).
9. **Nunca lanza excepción**: entrada `None`/vacía → reporte vacío.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_assumptions_parser.py`:**

| Test | Assert |
|---|---|
| `test_parse_full_form` | `[SUPUESTO: X | base: doc funcional M12 | impacto: bajo]` → 1 supuesto, `impact=="low"`, `basis` no vacía |
| `test_parse_minimal_form_is_high_impact` | `[SUPUESTO: X]` → `impact=="high"`, `basis==""`, `needs_confirmation is True` |
| `test_parse_with_basis_defaults_medium` | con `base:` y sin `impacto:` → `impact=="medium"` |
| `test_parse_normalizes_spanish_impact` | `alto/medio/bajo` → `high/medium/low` |
| `test_parse_is_case_insensitive` | `[supuesto: x | Base: y | IMPACTO: Alto]` parsea |
| `test_parse_from_html` | entrada `"<p>[SUPUESTO: X | base: Y]</p>"` → 1 supuesto (**caso crítico del Técnico**) |
| `test_parse_dedupes` | el mismo texto dos veces → 1 |
| `test_parse_orders_high_first` | mezcla de impactos → `[0].impact=="high"` |
| `test_parse_pending` | `[PENDIENTE: monto tope | necesito: valor de negocio]` → 1 pendiente con `needs` |
| `test_parse_empty_and_none` | `""`, `None` → reporte vacío, `marks_ok is False`, sin excepción |
| `test_overload_flag` | 11 supuestos con techo 10 → `overload is True` |
| `test_unbased_count` | 3 supuestos, 2 sin `base` → `unbased_count == 2` |
| `test_truncates_giant_assumption` | **[A2]** supuesto con `text` de 5000 chars → `len(text) == 500` y termina en `…`; `basis` de 1000 → `len == 300` |
| `test_blocked_without_pending_detection` | **[C6]** texto con `"❓ CONSULTA TÉCNICA (pre-bloqueo)"` y sin `[PENDIENTE:` → `blocked_without_pending is True`; con `[PENDIENTE:` → `False` |
| `test_strip_canonical_marks` | `strip_canonical_marks("x [SUPUESTO: a | base: b] y [PENDIENTE: c]")` → `"x  y "` (solo borra los marcadores) |
| `test_intent_assumption_basis_is_backward_compatible` | `IntentAssumption(text="x", impact="high", needs_confirmation=True)` sigue construyéndose sin `basis` |

**Comando (C8 — los nombres reales, verificados):** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_assumptions_parser.py tests\test_intent_preflight_contract.py tests\test_intent_preflight_generate.py tests\test_intent_preflight_ranking.py -q`
**Criterio BINARIO:** los 4 archivos verdes; 16/16 casos nuevos.
**Flag:** ninguna (módulo puro sin callers todavía).
**Impacto por runtime:** ninguno aún.
**Trabajo del operador:** ninguno.

---

### F1 — Dejar de castigar la honestidad (confidence + contrato) — ANTES que cualquier prompt

> **[C2] Por qué es la fase 1 y no la 3:** `_HEDGE_PHRASES` incluye `"[PENDIENTE"` (`confidence.py:33`) y resta 8 puntos por ocurrencia. Si los prompts (F3) o la política (F2) llegaran primero, cada analista honesto perdería confidence y caería en `needs_review` — el freno por la puerta de atrás. Esta fase aterriza **dormida**: sus guardas leen `getattr(config, "STACKY_ASSUMPTION_MODE_ENABLED", False)` y la flag **todavía no existe** (se registra en F2) ⇒ `False` ⇒ comportamiento byte-idéntico a hoy. Cuando F2 registre la flag con default ON, la exención de scoring y la política del prompt se encienden **atómicamente**. No hay ventana.

**Objetivo (1 frase).** Que declarar supuestos canónicos no destruya el score ni dispare `needs_review`, pero que asumir sin respaldo o de más **sí** se detecte.

**Archivos a editar:**
1. `Stacky Agents/backend/services/confidence.py`
2. `Stacky Agents/backend/contract_validator.py`

**Cambio 1 — `confidence.py`: exención del formato canónico.** Reemplazar la línea `text_lower = text.lower()` (`:82`, justo antes del loop de hedge `:85-89`) por:

```python
+    # Plan 213 — Un supuesto DECLARADO en formato canónico es rigor, no evasión.
+    # Se remueve del texto antes de contar hedge phrases; el hedge VAGO
+    # ("asumo que…" suelto en prosa) sigue penalizando igual.
+    scored_text = text
+    from config import config as _acfg
+    if getattr(_acfg, "STACKY_ASSUMPTION_MODE_ENABLED", False):
+        from services.assumptions import strip_canonical_marks
+        scored_text = strip_canonical_marks(text)
+    text_lower = scored_text.lower()
-    text_lower = text.lower()
```
(`strip_canonical_marks` ya existe desde F0.)

**Cambio 2 — `confidence.py`: bonus por disciplina.** Después del bloque de bonus existente (`:97-107`), agregar: **[C7]** calcular `parse(text)` sobre el texto **ORIGINAL** (el stripped ya no contiene `[SUPUESTO`); si hay ≥1 supuesto con `basis` no vacía → `score += 5` (máximo una vez) y `signals.append("assumption_discipline")`. Un análisis que declara sus supuestos con evidencia es **más** confiable que uno que calla. Misma guarda de flag que el Cambio 1.

**Cambio 3 — `contract_validator.py`: regla de disciplina de supuestos.** Agregar a los contratos `functional` (`:61-71`) y `technical` (`:73-90`) una clave nueva:

```python
         "min_word_count": 200,
+        "assumption_discipline": True,   # Plan 213
```
Y en `validate()` (`:130`), después del loop de `_EVASION_PHRASES` (`:188`), agregar una regla que **solo corre si `contract.get("assumption_discipline")` y la flag está ON**:

- Si el output contiene alguna `_EVASION_PHRASES`/`forbidden_phrases` **y** `parse(output).marks_ok is False` → **warning** (no failure) `assumption_missing`: *"declara incertidumbre sin marcarla como [SUPUESTO] o [PENDIENTE]"*.
- Si `parse(output).overload is True` → **warning** `assumption_overload`.
- Si `parse(output).unbased_count > 0` → **warning** `assumption_unbased` con el conteo.
- **Nunca failure.** Razón: un failure con `gate_enabled` manda la ejecución a `needs_review` — o sea, **volvería a frenar el pipeline**, que es exactamente lo que este plan combate. Los warnings quedan visibles en el `ContractBadge` existente y en el panel de F5.

> **Excepción única a "nunca failure":** `assumption_overload` **sí** produce `needs_review` (no vía contrato, sino vía la persistencia de F4 en los 3 call-sites), porque un análisis mayormente supuesto necesita ojos humanos (G2.3). Es el contrapeso honesto de todo el plan.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_scoring_and_contract.py`** (la flag aún no existe: los tests ON la simulan con `monkeypatch.setattr(config, "STACKY_ASSUMPTION_MODE_ENABLED", True, raising=False)` sobre la **instancia** `config.config`):

| Test | Assert |
|---|---|
| `test_canonical_assumption_does_not_lower_confidence` | **[C7 assert exacto]** `score(texto_con_3_supuestos_canónicos_con_base) >= score(mismo_texto_sin_ellos)` — **KPI-6** |
| `test_vague_hedge_still_penalized` | `"asumo que el proceso corre de noche"` en prosa suelta → sigue restando 8 |
| `test_pendiente_canonico_not_penalized` | `[PENDIENTE: x | necesito: y]` canónico → no resta los 8 de `"[PENDIENTE"` (lo removió el strip) |
| `test_assumption_discipline_bonus` | ≥1 supuesto con base → `+5` y señal `assumption_discipline` |
| `test_flag_off_scoring_is_identical` | sin flag (estado real post-F1) → score byte-idéntico al pre-213 (**KPI-7**) |
| `test_contract_warns_when_evasion_without_marks` | output con `"no puedo determinar"` y sin marcas → 1 warning `assumption_missing`, `passed` **sin cambios** |
| `test_contract_no_warning_when_marks_present` | mismo output + `[SUPUESTO: …]` → sin ese warning |
| `test_contract_warns_on_unbased` | 2 supuestos sin `base:` → warning `assumption_unbased` con `count==2` |
| `test_contract_never_fails_on_assumptions` | ningún caso de arriba mueve `ContractResult.failures` |
| `test_developer_contract_untouched` | el contrato `developer` **no** tiene `assumption_discipline` (**G6, protege 210**) |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_scoring_and_contract.py tests\test_harness_post_run.py -q`
**Criterio BINARIO:** ambos verdes **y** `grep -n "assumption_discipline" "Stacky Agents/backend/contract_validator.py"` → 2+ matches (functional + technical) y **0** en el bloque `developer`.
**Flag:** `STACKY_ASSUMPTION_MODE_ENABLED` — **se registra recién en F2**; hasta entonces `getattr(config, …, False)` ⇒ OFF ⇒ esta fase es inerte en producción (aposta, C2).
**Impacto por runtime:** transversal — los 3 runtimes llaman `contract_validator` y `confidence` directamente (claude `:2244-2260`, codex vía `finalize_run`, copilot `agent_runner.py:890`).
**Trabajo del operador:** ninguno.

---

### F2 — La política global, inyectada en los 3 runtimes

**Objetivo (1 frase).** Que los dos analistas reciban, en cualquier runtime, la misma instrucción: inferir y declarar en vez de frenar.

**Archivos a editar:**
1. `Stacky Agents/backend/harness/run_contract.py` (cubre **claude_code_cli** y **codex_cli**)
2. `Stacky Agents/backend/agents/base.py` (cubre **github_copilot**)
3. `Stacky Agents/backend/config.py` + `Stacky Agents/backend/services/harness_flags.py` + `Stacky Agents/backend/services/harness_flags_help.py` (flags)

**Cambio 1 — bloque canónico en `run_contract.py`.** Agregar, después de `rules_text` (`:64-76`; `_RULES_MCP` está en `:40`), una constante nueva y una función pública:

```python
# ── Plan 213 — Política de supuestos para agentes de análisis ────────────────
_RULES_ASSUMPTIONS = """\
## Política de supuestos (Stacky Agents)

- **No frenás para preguntar.** Ante información faltante o ambigua, adoptás la
  interpretación más razonable a partir de la documentación y el `client-profile`
  que ya tenés en contexto, la dejás explícita y SEGUÍS hasta terminar el análisis.
- **Formato obligatorio del supuesto** (una línea, dentro del contenido donde aplica):
  `[SUPUESTO: <afirmación concreta> | base: <documento/módulo/dato que lo respalda> | impacto: alto|medio|bajo]`
  Si no encontrás respaldo, escribí `base: sin respaldo` — se clasificará como impacto alto.
- **`[PENDIENTE: …]` es la ÚNICA excepción**, y es para un dato DURO imposible de inferir
  (un valor numérico que nadie dio, una decisión de negocio, una credencial):
  `[PENDIENTE: <dato> | necesito: <qué exactamente hace falta>]`
  Prohibido usar `[PENDIENTE]` para algo que podrías inferir con la doc que tenés.
- **Techo:** si necesitás más de 10 supuestos para completar el análisis, es señal de que
  falta contexto real: declaralos igual, terminá, y el operador lo revisará.
- **Cerrá con el bloque "Supuestos asumidos"** listando todos tus supuestos, los de
  impacto alto primero. El operador los confirma o corrige desde Stacky; sus correcciones
  mandan sobre tus supuestos en la próxima corrida.
- **No inventes hechos.** Un supuesto es una interpretación declarada, no un dato fabricado:
  jamás presentes como verificado algo que asumiste.\
"""


def assumption_rules_text() -> str:
    """Plan 213 — Texto canónico de la política de supuestos.

    Devuelve "" si la flag está OFF (comportamiento pre-213, byte-idéntico).
    """
    from config import config
    if not getattr(config, "STACKY_ASSUMPTION_MODE_ENABLED", False):
        return ""
    return _RULES_ASSUMPTIONS


def applies_to(agent_type: str) -> bool:
    """True si `agent_type` está en la allowlist de la política (G6)."""
    from config import config
    raw = getattr(config, "STACKY_ASSUMPTION_MODE_AGENT_TYPES", "") or ""
    allowed = {a.strip().lower() for a in raw.split(",") if a.strip()}
    return (agent_type or "").lower() in allowed
```

> **Nota de diseño (por qué acá):** `harness/run_contract.py` es el único punto que ya alimenta a claude (`claude_code_cli_runner.py:2387-2388`) y codex (`codex_cli_runner.py:1378-1382`) simultáneamente. Es exactamente el mismo mecanismo con el que H4.3 inyectó las Skills en los 3 runtimes.

**Cambio 2 — consumo en los dos runners CLI, con threading de `agent_type` (C3).** Los builders son `_build_system_prompt` (claude, `claude_code_cli_runner.py:2370`) y `_build_codex_prompt` (codex, `codex_cli_runner.py:1367`). **Ninguno recibe `agent_type` hoy, y `selected_agent: VsCodeAgent` solo tiene `name`/`filename` (`services/vscode_agents.py:31-33`)** — sin este paso el diff no compila:

1. Agregar a **ambos** builders el kwarg nuevo `agent_type: str = ""` (default `""` ⇒ backward-compatible: sin pasar nada, `applies_to("")` es `False` y el prompt es idéntico).
2. Localizar sus call-sites con `grep -n "_build_system_prompt(" "Stacky Agents/backend/services/claude_code_cli_runner.py"` y `grep -n "_build_codex_prompt(" "Stacky Agents/backend/services/codex_cli_runner.py"` y pasar el `agent_type` que el runner ya conoce (el mismo que luego llega al post-run).
3. Dentro de cada builder, donde hoy se arma `rules` (claude `:2388`, codex `:1382`), concatenar:

```python
     rules = rules_text(runtime="claude", mcp_enabled=mcp_enabled)
+    from harness.run_contract import assumption_rules_text, applies_to as _assump_applies
+    if _assump_applies(agent_type or ""):
+        _ar = assumption_rules_text()
+        if _ar:
+            rules = rules + "\n\n" + _ar
```
(idéntico en codex con `runtime="codex"`).

**Cambio 3 — paridad copilot (`agents/base.py:56` `compose_system_prompt`).** En el ensamblado final (`:196-200`), agregar la política a `prefix_parts` **antes** de `"# Instrucciones del agente"`, con la misma guarda de flag + allowlist. Mismo texto, misma fuente (`assumption_rules_text()`) — **prohibido duplicar el string**.

**Flags nuevas (las 3 registradas en `harness_flags.py`, `config.py` y `harness_flags_help.py`):**

| Key | Tipo | Default | Descripción |
|---|---|---|---|
| `STACKY_ASSUMPTION_MODE_ENABLED` | bool | **True** | "Analistas infieren y declaran supuestos en vez de frenar. OFF = comportamiento pre-213 (consulta pre-bloqueo y espera humana)." |
| `STACKY_ASSUMPTION_MODE_AGENT_TYPES` | csv | **`"technical,functional"`** | "Tipos de agente que reciben la política de supuestos. Vacío = ninguno." |
| `STACKY_ASSUMPTION_MAX_PER_RUN` | int | **10** | "Techo de supuestos por ejecución; superarlo marca la corrida como `assumption_overload` para revisión." |

- **Default ON justificado:** no dispara ninguna de las 4 excepciones duras. (1) No bypasea revisión humana: **al contrario**, hace visible lo que hoy el LLM asume en silencio, y el operador conserva confirmar/corregir. (2) No es destructiva ni irreversible: solo cambia el texto del análisis. (3) No requiere prerequisito nuevo. (4) No reduce seguridad. Además **no consume tokens ociosos** (es texto de prompt, no una corrida extra).
- **Obligatorio (memoria `harness-flags-default-explicit-gotcha`):** agregar `STACKY_ASSUMPTION_MODE_ENABLED` a `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py:467`, o `test_default_known_only_for_curated` se pone rojo.
- **Obligatorio (memoria `gotcha-config-config-vs-modulo-tickets`):** leer siempre la **instancia** `from config import config` y `getattr(config, "…", default)`. Leer del **módulo** devuelve el default y mata la rama OFF.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_policy_injection.py`:**

| Test | Assert |
|---|---|
| `test_assumption_rules_text_off_is_empty` | flag OFF → `""` |
| `test_assumption_rules_text_on_has_canonical_format` | contiene `"[SUPUESTO:"`, `"base:"`, `"impacto:"`, `"[PENDIENTE:"` |
| `test_applies_to_allowlist` | `technical`/`functional` → True; `developer`/`qa`/`business`/`""` → False |
| `test_applies_to_empty_csv` | csv vacío → False para todos |
| `test_claude_system_prompt_includes_policy_for_technical` | el system prompt armado para `technical` contiene `"[SUPUESTO:"` |
| `test_claude_system_prompt_excludes_policy_for_developer` | para `developer` **no** lo contiene (**G6 — protege el Plan 210**) |
| `test_codex_prompt_includes_policy` | idem en el builder de codex |
| `test_copilot_compose_includes_policy` | `FunctionalAgent().compose_system_prompt(...)` contiene la política |
| `test_all_three_runtimes_share_the_same_text` | el string inyectado en los 3 es **idéntico** (sin duplicación) |
| `test_flag_off_prompts_are_byte_identical` | con flag OFF, los 3 prompts son iguales a los de antes del cambio |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_policy_injection.py tests\test_run_contract.py tests\test_harness_flags.py -q`
> **Ojo (memoria `gotcha-config-reload-harness-flags-contamina`):** `test_harness_flags.py` hace `importlib.reload(config)` y contamina tests flag-off de la misma corrida. Correr **por archivo**, nunca junto con los tests de rama OFF.

**Criterio BINARIO:** los 3 archivos verdes **y** `grep -c "SUPUESTO" "Stacky Agents/backend/harness/run_contract.py"` ≥ 1 **y** `grep -rn "_RULES_ASSUMPTIONS" "Stacky Agents/backend"` → **exactamente 1 definición** (sin copias).
**Impacto por runtime:** Claude Code CLI y Codex CLI vía `run_contract`; GitHub Copilot vía `compose_system_prompt`. Fallback de los 3: flag OFF ⇒ string vacío ⇒ prompt idéntico al actual.
**Trabajo del operador:** ninguno (opt-in con default ON).

---

### F3 — Reescribir la conducta de los dos analistas (prompts + system prompts Python)

> **[C2] Prerrequisito duro:** F1 (scoring/contrato) y F2 (flags+política) ya implementadas y verdes. Esta fase es la ÚLTIMA que toca comportamiento de prompts, precisamente para que ningún analista declare supuestos mientras el sistema todavía los castiga.

**Objetivo (1 frase).** Invertir el default en los dos agentes: inferir y declarar es el camino normal; frenar es la excepción justificada.

**Archivos a editar:**
1. `Stacky Agents/backend/Stacky/agents/TechnicalAnalyst.v2.agent.md`
2. `Stacky Agents/backend/Stacky/agents/FunctionalAnalyst.agent.md`
3. `Stacky Agents/backend/agents/technical.py`
4. `Stacky Agents/backend/agents/functional.py`

> **Dato verificado:** los `.agent.md` **NO están gitignored** — `.gitignore:49-51` los des-ignora explícitamente (solo `manifest.json` está ignorado, `:52`). Varios comentarios del repo afirman lo contrario (p.ej. `services/agent_prompt_registry.py:3`); **esa afirmación está desactualizada**. Se editan y se commitean normalmente.
> **Espejo del release:** existe una copia en `Stacky Agents/DeployStackyAgents/Stacky/agents/`. Actualizarla en el mismo cambio o el deploy corre con el prompt viejo (riel: "deploy debe ser foto fiel del dev").

**Cambio 1 — Técnico, PASO 4 (`TechnicalAnalyst.v2.agent.md:100-109`).** Reemplazar la tabla de decisión y el aviso por:

```markdown
### PASO 4 — Resolver la incertidumbre y compilar el análisis

**Bloqueante** = condición que, sin resolverse, llevaría al Developer a implementar algo
incorrecto o imposible.

**Regla de oro: un bloqueante inferible NO es un bloqueante — es un supuesto.** Ante
información faltante, buscás la respuesta en la documentación técnica/funcional y en el
`client-profile`, adoptás la interpretación más razonable, la declarás y SEGUÍS.

| Condición | Acción |
|-----------|--------|
| Análisis completo, sin incertidumbre | Publicar análisis → pasar a `{…technical.next_state_ok}` |
| Falta un dato que podés inferir de la doc, del `client-profile` o del análisis funcional | **Inferirlo**, declararlo como `[SUPUESTO: … | base: … | impacto: …]` en el punto donde aplica, listarlo en "Supuestos asumidos" y **completar el análisis** → pasar a `{…technical.next_state_ok}` |
| Falta un dato DURO imposible de inferir (valor de negocio, decisión de producto, credencial) | Declararlo como `[PENDIENTE: … | necesito: …]`, **completar todo lo demás del análisis** y dejar el ticket en el estado de revisión `{…technical.input_states[0]}` |

> ⚠️ **El agente NUNCA aplica `blocked_state` por su cuenta.** (Sin cambios: sigue siendo
> decisión humana.) Lo que SÍ cambia: ya no dejás el análisis a medias esperando una
> respuesta que podías inferir. Entregás el análisis completo con tus supuestos declarados.
```

**Cambio 2 — Técnico, plantilla de salida (`:157-164`).** Reemplazar la sección 6 "Consulta pre-bloqueo" por **dos** secciones:

```html
<h3>6. Supuestos asumidos</h3>
<ul>
  <li>[SUPUESTO: ... | base: ... | impacto: alto] — [qué implica si es falso]</li>
</ul>
<p><em>Confirmá o corregí estos supuestos desde Stacky; tus correcciones mandan en la próxima corrida.</em></p>

<h3>7. Datos pendientes (solo si son imposibles de inferir)</h3>
<ul>
  <li>[PENDIENTE: ... | necesito: ...]</li>
</ul>
```
Y en el PASO FINAL (`:187-231`): el caso "consulta" se conserva **pero pasa a dispararse solo si hay al menos un `[PENDIENTE: …]`**; si solo hay supuestos, el ticket avanza a `next_state_ok`. Bumpear `version` en el frontmatter (`:4`) `2.0.0 → 2.1.0`.

**Cambio 3 — Funcional, regla dura (`FunctionalAnalyst.agent.md:316`).** Reemplazar:

```markdown
- **Cero ambigüedad NO significa frenar.** Si después de leer la documentación queda
  ambigüedad, resolvela con la interpretación más razonable y declarala como
  `[SUPUESTO: <interpretación> | base: <doc/módulo> | impacto: alto|medio|bajo]` en el
  punto donde aplica, y listala en la sección "8. Supuestos asumidos". Solo usás
  `[PENDIENTE: … | necesito: …]` para un dato duro imposible de inferir. **Nunca dejás el
  análisis incompleto por una ambigüedad que podías resolver.**
```

**Cambio 4 — Funcional, plantilla (`:186-232`).** Agregar la sección faltante al final de `analisis-funcional.md` (cierra el hueco de la "sección fantasma" de §2.2):

```markdown
## 8. Supuestos asumidos

| Supuesto | Base | Impacto | Qué implica si es falso |
|----------|------|---------|-------------------------|
| [SUPUESTO: ... | base: ... | impacto: alto] | ... | alto | ... |
```
Bumpear `version` (`:4`) `2.1.0 → 2.2.0`.

**Cambio 5 — system prompts Python (paridad copilot).**
- `backend/agents/technical.py:35-39`: reemplazar el párrafo "Si detectás un bloqueante, NO bloquees el ticket: primero publicá una consulta al humano … Esperá la respuesta humana" por: *"Si detectás un bloqueante, primero intentá resolverlo por inferencia con la documentación y el client-profile que tenés en contexto: declarálo como `[SUPUESTO: … | base: … | impacto: …]` y completá el análisis. Reservá la consulta al humano (`[PENDIENTE: … | necesito: …]`) para datos duros imposibles de inferir. Nunca aplicás el estado 'Blocked' por tu cuenta: eso sigue siendo decisión humana."*
- `backend/agents/functional.py:18-43`: agregar el párrafo equivalente (hoy no dice nada de bloqueantes).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_analyst_prompts.py`** (patrón copiado de `tests/test_documenter_autonomy.py:48-82`, incluido el `pytest.skip` si el `.agent.md` no está materializado):

| Test | Assert |
|---|---|
| `test_technical_prompt_has_assumption_policy` | el `.md` contiene `"[SUPUESTO:"`, `"Supuestos asumidos"` y `"un bloqueante inferible NO es un bloqueante"` |
| `test_technical_prompt_keeps_no_autoblock_rule` | **no-regresión B7**: sigue conteniendo `"NUNCA aplica"` + `blocked_state` |
| `test_technical_prompt_pending_gates_the_review_state` | contiene la condición de que el estado de revisión aplica solo con `[PENDIENTE:` |
| `test_functional_prompt_has_assumption_policy` | contiene `"[SUPUESTO:"` y `"Supuestos asumidos"` |
| `test_functional_template_declares_section_8` | la plantilla contiene `"## 8. Supuestos asumidos"` (**cierra la sección fantasma**) |
| `test_functional_prompt_no_longer_says_cero_ambiguedad_frenar` | **no** contiene la frase vieja `"declararla en \"Preguntas abiertas\""` |
| `test_technical_agent_system_prompt_mentions_supuesto` | `TechnicalAgent().system_prompt()` contiene `"[SUPUESTO"` |
| `test_functional_agent_system_prompt_mentions_supuesto` | idem `FunctionalAgent()` |
| `test_versions_bumped` | frontmatter del Técnico `2.1.0` y del Funcional `2.2.0` |
| `test_deploy_mirror_in_sync` | el `.agent.md` de `DeployStackyAgents/Stacky/agents/` tiene el mismo `sha256` que el de `backend/Stacky/agents/` (**skip** si el directorio de deploy no existe) |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_analyst_prompts.py tests\test_b7_technical_no_autoblock.py tests\test_functional_analyst_extraction_rules.py -q`
> **Nota de ratchet:** `test_b7_technical_no_autoblock.py` y `test_functional_analyst_extraction_rules.py` están hoy en `backend/tests/harness_ratchet_allowlist.txt` (`:29`, `:90`, marcados `pendiente-de-triage`). Como este plan los ejercita y los deja verdes, **moverlos de la allowlist al ratchet** (`run_harness_tests.sh` + `.ps1`) y bajar en 2 el techo `_ALLOWLIST_MAX` de `tests/test_harness_ratchet_meta.py:66`. Es deuda que este plan salda de paso.

**Criterio BINARIO:** los 3 archivos verdes; `test_b7_technical_no_autoblock.py` verde **sin modificarlo** (prueba que no se rompió el guardarraíl anti-auto-bloqueo).
**Flag que la protege:** los prompts cambian de forma **incondicional** (son texto), pero la política operativa la gatea `STACKY_ASSUMPTION_MODE_ENABLED` en el scoring/gate (F1) y la persistencia (F4). **Riesgo asumido y declarado:** con la flag OFF, el prompt igual pide supuestos. Mitigación: como F1 ya aterrizó ANTES (C2), con flag OFF el scoring es exactamente el de hoy (nunca peor) y con flag ON no castiga la honestidad — no existe combinación en la que declarar supuestos penalice. La alternativa de mover los dos párrafos a la inyección de F2 (flag-gated) y dejar los `.md` sin cambios queda **explícitamente descartada**: los `.agent.md` son la fuente de verdad que lee el CLI del disco (`claude_code_cli_runner.py:2393-2397`) y partir la política en dos lugares es peor que el riesgo que evita.
**Impacto por runtime:** Claude Code CLI y Codex CLI leen el `.agent.md` del disco; GitHub Copilot usa `system_prompt()` de Python — por eso se tocan los cuatro archivos.
**Trabajo del operador:** ninguno.

---

### F4 — Persistir los supuestos en los TRES paths post-run (no hay chokepoint único — C1)

> **[C1] Realidad verificada del repo:** `harness/post_run.py:finalize_run` **solo lo invoca codex** (`codex_cli_runner.py:966-967`). Claude corre `contract_validator` + `confidence` inline (`claude_code_cli_runner.py:2237-2260`; escribe `metadata["confidence"]` en `:1781`) y el path de copilot lo hace `agent_runner.py` (`contract_validator.validate` en `:890`, metadata vía `metadata_dict`). Un solo cambio NO cubre los 3: hacen falta **un helper + 3 call-sites**.

**Objetivo (1 frase).** Que cada ejecución de los dos analistas deje sus supuestos tipados en la metadata, **en los 3 runtimes**, para que la UI y el board puedan mostrarlos.

**Archivos a editar (C1 — helper + 3 call-sites):**
1. `Stacky Agents/backend/services/assumptions.py` (helper nuevo)
2. `Stacky Agents/backend/harness/post_run.py` (call-site codex)
3. `Stacky Agents/backend/services/claude_code_cli_runner.py` (call-site claude)
4. `Stacky Agents/backend/agent_runner.py` (call-site copilot)

**Cambio 1 — helper único en `services/assumptions.py`** (toda la lógica vive acá; los call-sites son 4 líneas cada uno):

```python
def apply_to_metadata(agent_type: str, output_text: str, metadata: dict, log=None) -> str | None:
    """Plan 213 F4 — Parsea supuestos del output y los fusiona en `metadata`
    (mutación in-place con .update(), JAMÁS reasigna el dict — convivencia 210/211).

    Devuelve "needs_review" si el reporte tiene overload (G2.3); None en cualquier
    otro caso. No-op (devuelve None sin tocar metadata) si la flag está OFF o si
    `agent_type` no está en la allowlist (usa harness.run_contract.applies_to).
    NUNCA lanza: cualquier excepción se loguea como warn y devuelve None.
    """
```

**Cambio 2 — call-site codex, dentro de `finalize_run` (`post_run.py:35`), después de armar `metadata_patch` (`:106-109`) y antes de devolver el resultado:**

```python
    # ── Plan 213 — Supuestos declarados por los agentes de análisis ──────────
    from services.assumptions import apply_to_metadata as _assump_apply
    if _assump_apply(agent_type, output_text or "", metadata_patch, log=_log) == "needs_review":
        status = "needs_review"          # G2.3 — único caso que frena
        _log("warn", "assumption_overload → needs_review")
```

**Cambio 3 — call-site claude, en el bloque de calidad inline de `claude_code_cli_runner.py`** (donde ya se escribe `metadata["confidence"] = conf.to_dict()`, `:1781`): misma llamada sobre el dict `metadata`; si devuelve `"needs_review"` y el status calculado era `completed`, forzarlo a `needs_review` con log `warn`.

**Cambio 4 — call-site copilot, en `agent_runner.py`** (tras `contract_validator.validate`, `:890`, donde se fusiona la metadata de la ejecución vía `metadata_dict`): misma llamada sobre el dict que se persiste; mismo tratamiento del retorno. Localizar el punto exacto de fusión con `grep -n "metadata_dict" "Stacky Agents/backend/agent_runner.py"` y aplicar sobre el dict ANTES de la asignación `row.metadata_dict = md` (recordar: el setter serializa con `json.dumps`, `models.py:264-265`).

**Shape exacto de `to_metadata` (contrato congelado — lo consumen F5, F6 y F7):**

```json
{
  "assumptions": {
    "items": [
      {"text": "…", "basis": "…", "impact": "high", "needs_confirmation": true, "status": "pending"}
    ],
    "pending": [{"text": "…", "needs": "…"}],
    "unbased_count": 1,
    "overload": false,
    "blocked_without_pending": false,
    "total": 3
  }
}
```
`status` ∈ `"pending" | "confirmed" | "corrected"`; nace siempre en `"pending"` (**solo el operador lo cambia**, F5 — G1). **[C6]** `blocked_without_pending` viene del reporte de F0 y hace el KPI-1 medible por consulta sobre metadata (no por logs).

> **Gotcha obligatorio (memoria `plan-209-status`, hallazgo C3):** `AgentExecution.metadata_json` es una columna **`Text`** (`backend/models.py:219`). `metadata_patch` es un dict que el **caller** fusiona y serializa; verificar en el punto de escritura que se use `json.dumps` (o el accessor `metadata_dict` de `models.py:260-265`). Si se asigna un dict crudo a la columna, la feature muere en silencio. **Test obligatorio abajo.**
> **Regla de convivencia (210/211):** `metadata_patch.update(...)`, **jamás** `metadata_patch = {...}` — regla embebida en `apply_to_metadata` (Cambio 1), por eso los call-sites no pueden violarla.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_post_run_assumptions.py`:**

| Test | Assert |
|---|---|
| `test_apply_adds_assumptions_for_technical` | helper directo: `metadata["assumptions"]["total"] == 2` con un output de 2 supuestos |
| `test_apply_adds_empty_assumptions_when_none` | analista sin supuestos → clave presente con `total == 0` (**KPI-2**) |
| `test_apply_skips_for_developer` | `agent_type="developer"` → la clave **no** aparece y devuelve `None` (**G6**) |
| `test_apply_parses_html_output` | output HTML del Técnico → supuestos detectados (**el caso que rompería todo**) |
| `test_apply_overload_returns_needs_review` | 11 supuestos → retorno `"needs_review"` |
| `test_apply_never_raises` | monkeypatch de `assumptions.parse` que lanza → devuelve `None`, metadata intacta, warn logueado |
| `test_apply_flag_off_is_noop` | flag OFF (allowlist vacía) → la clave no aparece; `metadata` idéntico al pre-213 |
| `test_finalize_run_persists_assumptions` | **call-site codex**: `finalize_run(...)` con output de supuestos → `metadata_patch["assumptions"]` presente y `status_suggestion == "needs_review"` si overload |
| `test_claude_inline_path_persists_assumptions` | **call-site claude [C1]**: la función del bloque de calidad inline (localizar la que escribe `metadata["confidence"]`, `:1775-1790`) deja `metadata["assumptions"]` |
| `test_agent_runner_persists_assumptions` | **call-site copilot [C1]**: el dict persistido vía `row.metadata_dict` contiene `assumptions` |
| `test_metadata_roundtrips_as_json_string` | `json.loads(json.dumps(metadata))` conserva el shape completo (blindaje del gotcha) |
| `test_metadata_patch_preserves_foreign_keys` | si el dict ya traía `contract_score`/`confidence`, siguen ahí (convivencia con 210/211) |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_post_run_assumptions.py tests\test_harness_post_run.py tests\test_codex_post_run.py -q`
**Criterio BINARIO:** los 3 verdes **y** `grep -rn "apply_to_metadata" "Stacky Agents/backend" --include=*.py` (excluyendo `tests/`) → **exactamente 4 matches**: 1 def en `services/assumptions.py` + 3 call-sites (`harness/post_run.py`, `services/claude_code_cli_runner.py`, `agent_runner.py`). Menos de 4 = un runtime quedó sin persistencia = KPI-2 roto.
**Flag:** la de F2 (vía `applies_to`, embebido en el helper).
**Impacto por runtime:** **[C1]** un call-site por runtime, con la lógica en un único helper — codex vía `finalize_run`, claude vía su path inline, copilot vía `agent_runner`. Paridad G4 garantizada por el grep-gate de 4 matches y los 3 tests de call-site.
**Trabajo del operador:** ninguno.

---

### F5 — Panel de supuestos + confirmar/corregir en un click (HITL real)

**Objetivo (1 frase).** Que el operador vea los supuestos junto al análisis y pueda confirmarlos o corregirlos sin escribir un comentario en ADO.

**Archivos a crear:**
- `Stacky Agents/frontend/src/components/AssumptionsPanel.tsx`
- `Stacky Agents/frontend/src/components/AssumptionsPanel.module.css`
- `Stacky Agents/frontend/src/components/assumptionsModel.ts` (lógica pura)
- `Stacky Agents/frontend/src/components/__tests__/assumptionsModel.test.ts`

**Archivos a editar:**
- `Stacky Agents/backend/api/executions.py` (endpoint nuevo)
- `Stacky Agents/frontend/src/components/OutputPanel.tsx` (montaje, junto al bloque `metadata.human_review` de `:147+`)
- `Stacky Agents/frontend/src/api/endpoints.ts` (cliente)

**Endpoint nuevo — `PATCH /api/executions/<execution_id>/assumptions`:**

```
body: {"updates": [{"index": 0, "status": "confirmed"},
                   {"index": 2, "status": "corrected", "correction": "En realidad el proceso corre a las 02:00"}]}
→ 200 {"ok": true, "assumptions": {…shape completo actualizado…}}
→ 404 si la ejecución no existe
→ 400 {"error": "invalid_status"} si status ∉ {pending, confirmed, corrected}
→ 400 {"error": "correction_required"} si status=="corrected" y correction vacía
→ 400 {"error": "invalid_index"} si index < 0 o index >= len(items)   [C10]
```
Implementación: leer `metadata_dict`, mutar `assumptions.items[index].status` (+ `correction`), **serializar con `json.dumps`** y guardar. Idempotente. **No toca ADO, no cambia el estado del ticket, no relanza nada** (G1).

**Modelo puro (`assumptionsModel.ts`):**
```ts
export function groupByImpact(items: AssumptionDTO[]): { high: […]; medium: […]; low: […] };
export function pendingHighCount(items: AssumptionDTO[]): number;
export function badgeLabel(meta: AssumptionsMetaDTO | null): string;  // "3 supuestos · 1 sin confirmar"
```

**Componente:** lista agrupada por impacto (alto primero), cada ítem con su `base` (o el aviso **"sin respaldo"** en tono de advertencia), y dos acciones: `✔ Confirmar` y `✎ Corregir` (abre un textarea). Si `overload` → banner *"Análisis mayormente supuesto — revisá antes de avanzar"*. Si no hay supuestos → no renderiza nada (cero ruido).

**Tests (TDD):**
- Backend — `Stacky Agents/backend/tests/test_plan213_assumptions_endpoint.py`: happy path confirmar; corregir con texto; `400` sin corrección; `400` status inválido; **`400` index fuera de rango [C10]**; `404`; **idempotencia** (dos PATCH iguales → mismo resultado); **round-trip JSON** (el valor guardado es `str` y `json.loads` lo parsea); **no side-effects** (el `ado_state` y el `status` de la ejecución no cambian).
  Comando: `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_assumptions_endpoint.py -q`
- Frontend — `assumptionsModel.test.ts`: agrupación por impacto; `pendingHighCount`; `badgeLabel` con 0/1/N; metadata ausente → sin throw.
  Comando: `npx vitest run src\components\__tests__\assumptionsModel.test.ts`

**Criterio BINARIO:** ambos verdes + `npx tsc --noEmit` limpio.
**Flag:** `STACKY_ASSUMPTION_MODE_ENABLED` (el panel no renderiza si no hay metadata → degradación natural).
**Impacto por runtime:** transversal (lee metadata, agnóstico del runtime).
**Trabajo del operador:** **opcional**. No confirmar no bloquea nada; los supuestos quedan visibles igual.

---

### F6 — Cerrar el bucle: la corrección del operador manda en la próxima corrida

**Objetivo (1 frase).** Que confirmar/corregir un supuesto no sea un gesto decorativo: debe llegar al agente en la corrida siguiente, con prioridad máxima.

**Archivo a editar:** `Stacky Agents/backend/services/context_enrichment.py`

**Cambio — injector nuevo `_inject_assumption_corrections`, registrado en `enrich_blocks` (`:60`, orden de inyección `:100-128`), inmediatamente después de `_inject_run_directive` (`:125`):**

```python
def _inject_assumption_corrections(ticket_id: int, agent_type: str, blocks: list, log) -> list:
    """Plan 213 F6 — Los supuestos confirmados/corregidos por el operador vuelven
    como bloque `operator-corrections` (prioridad 110, la máxima).

    Fuente: la ÚLTIMA ejecución de este ticket+agent_type con
    metadata.assumptions.items que tengan status != "pending".
    Reusa intent_preflight.build_corrections_block (NO duplicar el bloque).
    """
```
Reglas exactas:
1. Guarda de flag + `applies_to(agent_type)`; si no, devolver `blocks` sin tocar.
2. **[A1] Buscar las últimas 3 `AgentExecution`** de ese `ticket_id` + `agent_type` (orden descendente por fecha) cuya metadata tenga `assumptions.items`, y **acumular** los ítems de las 3 — no solo la última. Razón: si el operador corrige en la corrida N y confirma otra cosa en N+1, ambas decisiones deben sobrevivir en N+2 (v1 perdía la de N). Dedupe por `text.strip().lower()`; ante el mismo texto en dos corridas, **gana la más reciente**.
3. Filtrar los ítems acumulados con `status in ("confirmed", "corrected")`. Si no hay ninguno → no inyectar nada.
4. Armar el texto:
   - confirmados → `CONFIRMADO por el operador: <text>`
   - corregidos → `CORREGIDO por el operador: <correction> (tu supuesto anterior era: <text> — es INCORRECTO)`
5. Llamar `intent_preflight.build_corrections_block(texto)` → devuelve el bloque con id `operator-corrections`.
6. **Si ya existe un bloque `operator-corrections`** en `blocks` (el flujo de brief lo puede haber puesto), **concatenar el contenido**, no agregar un segundo bloque con el mismo id.
7. Envuelto en `try/except` — nunca rompe el enriquecimiento.

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_corrections_loop.py`:**

| Test | Assert |
|---|---|
| `test_confirmed_assumption_is_injected` | bloque con id `operator-corrections` presente y contiene `"CONFIRMADO"` |
| `test_corrected_assumption_carries_the_correction` | contiene el texto de la corrección **y** la advertencia de que el supuesto anterior es incorrecto |
| `test_pending_only_injects_nothing` | todos `pending` → sin bloque nuevo |
| `test_corrections_accumulate_across_runs` | **[A1]** corrección en la corrida N + confirmación distinta en N+1 → el bloque de N+2 contiene **ambas**; mismo texto en N y N+1 con status distinto → gana N+1 |
| `test_merges_with_existing_corrections_block` | ya había uno → sigue habiendo **exactamente uno**, con ambos contenidos |
| `test_block_priority_is_max` | el id inyectado tiene prioridad 110 en `_BLOCK_PRIORITY` (`context_enrichment.py:373`) |
| `test_flag_off_injects_nothing` | flag OFF → `blocks` idéntico |
| `test_developer_does_not_get_the_block` | `agent_type="developer"` → sin bloque (**G6**) |
| `test_secrets_are_redacted` | una corrección con algo tipo secreto sale enmascarada (lo hace `build_corrections_block` vía `pii_masker`) |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_corrections_loop.py tests\test_run_directive_block.py -q`
**Criterio BINARIO:** ambos verdes **y** `grep -c "CORRECTIONS_BLOCK_ID" "Stacky Agents/backend/services/context_enrichment.py"` ≥ 1 (usa la constante, no un string suelto).
**Flag:** la de F2 (`STACKY_ASSUMPTION_MODE_ENABLED`).
**Impacto por runtime:** transversal — los context blocks alimentan a los 3 runtimes por el mismo camino.
**Trabajo del operador:** ninguno adicional (su click de F5 ya es la entrada).

---

### F7 — Que ningún supuesto de alto impacto se pierda (Desatascador + KPI)

**Objetivo (1 frase).** Los supuestos de impacto alto sin confirmar aparecen donde el operador ya mira los pendientes.

**Archivos a editar:**
- `Stacky Agents/backend/api/tickets.py` (board del Desatascador, `:2604-2830`; `blockers` se arma en `:2748-2783`)
- `Stacky Agents/frontend/src/pages/UnblockerPage.tsx`

**Cambio — nueva categoría en el board.** En el armado de `blockers` (`:2748-2783`), agregar una entrada por ticket cuya última ejecución de `technical`/`functional` tenga ítems con `impact == "high"` y `status == "pending"`:

```
"supuesto_alto_sin_confirmar: <N> supuesto(s) de alto impacto esperando tu confirmación"
```
**Regla dura (no reintroducir el freno):** esto es **informativo**, no bloqueante. No cambia el estado del ticket, no impide que el Developer avance, no dispara `needs_review`. Es visibilidad, no un gate. En la UI se muestra con estilo de *aviso*, distinto del de *bloqueo*.

**KPI medibles sobre metadata (C6 — un logger no es un contador consultable).** Los KPI del §1 se miden consultando `AgentExecution.metadata_json` (la persistencia de F4 ya deja todo): `assumptions.total`, `assumptions.unbased_count`, `assumptions.overload` y `assumptions.blocked_without_pending` (booleano por ejecución, detección determinista en F0 — el KPI-1 exige que ninguna ejecución con flag ON lo tenga en `true`). Los call-sites de F4 ya loguean el resumen por corrida (línea `info` del helper); no se agrega infra de telemetría nueva.

> **Coordinación 212 (C4):** `UnblockerPage.tsx` está modificado **ahora mismo** por la sesión paralela del Plan 212. Antes de editar: releer el archivo en frío, integrar de forma aditiva (sección nueva, sin reordenar lo existente) y correr `npx tsc --noEmit` tras el merge. Ídem la región del board en `api/tickets.py` (que también comparte con 208).

**Tests (TDD) — `Stacky Agents/backend/tests/test_plan213_unblocker_assumptions.py`:**

| Test | Assert |
|---|---|
| `test_board_lists_high_impact_pending` | el ticket aparece con el string `"supuesto_alto_sin_confirmar"` y el conteo correcto |
| `test_board_ignores_confirmed` | todos confirmados → no aparece |
| `test_board_ignores_low_and_medium` | solo `low`/`medium` pendientes → no aparece |
| `test_board_entry_does_not_change_ticket_state` | el `ado_state`/`stacky_status` del ticket no se toca |
| `test_flag_off_board_identical` | flag OFF → respuesta byte-idéntica a la pre-213 |
| `test_kpi_blocked_without_pending_persisted` | **[C6]** output con consulta pre-bloqueo y sin `[PENDIENTE:` → `metadata["assumptions"]["blocked_without_pending"] is True` (consultable, no solo logueado) |

**Comando:** `& ".venv\Scripts\python.exe" -m pytest tests\test_plan213_unblocker_assumptions.py -q`
**Criterio BINARIO:** verde + la suite existente del board del Desatascador verde (localizarla con `grep -rln "unblocker" tests\` y correrla por archivo).
**Flag:** la de F2 (`STACKY_ASSUMPTION_MODE_ENABLED`).
**Impacto por runtime:** transversal.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Prob. | Mitigación (concreta) |
|---|---|---|
| **El analista alucina y lo llama "supuesto"** | **Alta** — es EL riesgo del plan | (1) Todo supuesto declara `base:`; sin base ⇒ `impacto: alto` automático y encabeza la lista (F0). (2) `unbased_count` visible en el panel y en el warning del contrato (F1). (3) Techo de 10 ⇒ `needs_review` (F4). (4) El prompt dice explícitamente *"Un supuesto es una interpretación declarada, no un dato fabricado: jamás presentes como verificado algo que asumiste"* (F2). (5) El operador confirma/corrige y su corrección **manda** en la corrida siguiente (F6). |
| **[C1] Un runtime queda sin persistencia de supuestos** | **Alta si no se contempla** | No hay chokepoint post-run único (verificado). Helper único + 3 call-sites (F4) + grep-gate de **exactamente 4 matches** de `apply_to_metadata` + 1 test por call-site. |
| **[C2] El freno vuelve por `needs_review` durante la implementación** | **Alta si se implementa en otro orden** | Orden documental = orden de ejecución: F1 (scoring, aterriza dormido) antes que F2 (flag ON) antes que F3 (prompts). No existe ventana en la que un prompt pida supuestos y el scoring los castigue. |
| **Se rompe el guardarraíl anti-auto-bloqueo (B7)** | Baja | El guard de `api/tickets.py:1345-1368` **no se toca**. El test `test_b7_technical_no_autoblock.py` se corre sin modificar en F3 y debe quedar verde. |
| **El Developer empieza a "asumir" que compila** | Baja | Allowlist dura `STACKY_ASSUMPTION_MODE_AGENT_TYPES = "technical,functional"` (G6), con tests explícitos en F2 (`test_claude_system_prompt_excludes_policy_for_developer`), F1 (`test_developer_contract_untouched`) y F4 (`test_apply_skips_for_developer`). Protege directamente al Plan 210. |
| **El parser no ve nada porque el Técnico escribe HTML** | **Alta si no se contempla** | `parse()` normaliza HTML→texto con `ado_context._html_to_text`, con test dedicado en F0 y en F4. Es el mismo tipo de falla que el hallazgo C4 del Plan 209. |
| **La feature muere en silencio por `metadata_json` (columna `Text`)** | **Alta si no se contempla** | Test `test_metadata_roundtrips_as_json_string` en F4 + `json.dumps` explícito en F5. Es el hallazgo C3 del Plan 209, ya conocido. |
| **Colisión en `metadata_patch` con 210/211** | Media | Claves disjuntas + regla `update()` embebida en el helper + test `test_metadata_patch_preserves_foreign_keys` (F4). |
| **Colisión en el deliverable con 209** | Media | Orden de bloques acordado (Supuestos → Cómo validar) + grep de verificación tras merge (declarado arriba). |
| **[C4] Colisión viva con 212 en `UnblockerPage.tsx` / `api/tickets.py` con 208** | Media | Releer en frío antes de editar, cambios aditivos, `npx tsc --noEmit` tras merge (cláusulas en Planes relacionados y F7). |
| **Con flag OFF el prompt igual pide supuestos** | Media | Declarado y aceptado en F3 con su razón. El impacto es cosmético (el agente declara supuestos que nadie parsea); el scoring y el gate siguen siendo los de hoy (tests de F1). |
| **El espejo `DeployStackyAgents/Stacky/agents/` queda desactualizado** | Media | `test_deploy_mirror_in_sync` compara sha256 (F3), con skip si el directorio no existe. |
| **`test_harness_flags.py` contamina la corrida** (memoria) | Media | Correr **por archivo**; declarado en el comando de F2. |

---

## 6. Fuera de scope (explícito)

- **El preflight de negocio `functional_prereqs_unmet`** (`services/business_preflight.py:124-131`), que impide lanzar el Analista Funcional sobre un ticket que no es Épica en `input_states` ni tiene el marcador de bloqueo. **No se toca a propósito:** es una precondición sobre el **tipo y estado del ticket**, no información que el agente pueda inferir; "asumir" que un ticket es una Épica produciría basura. Es un plan aparte si el operador lo quiere flexibilizar.
- **Agregar un predicado de preflight para `technical`** (`_PREDICATES` `:136-138` solo tiene `functional`).
- **Cambiar el guard anti-auto-bloqueo** (`api/tickets.py:1345-1368`) o la exclusión de `blocked_state` de las transiciones automáticas (`harness/task_states.py:37-39`).
- **Extender la política a `developer`, `qa`, `devops`** (G6).
- **Tabla nueva de supuestos en la DB.** Se reusa `AgentExecution.metadata_json`; una tabla dedicada es deuda futura si el volumen lo justifica.
- **Reescribir el Modo B del Funcional** (`FunctionalAnalyst.agent.md:293-301`, responder tickets Blocked). Sigue igual.
- **Auto-confirmar supuestos** por antigüedad, por confianza o por cualquier heurística. **Prohibido por G1**: la confirmación es del operador o no es.

---

## 7. Glosario

| Término | Significado en Stacky |
|---|---|
| **SUPUESTO** | Interpretación declarada explícitamente por el agente ante información faltante, en formato `[SUPUESTO: … | base: … | impacto: …]`. Es trabajo entregado, no una pregunta. |
| **PENDIENTE** | Dato duro imposible de inferir (`[PENDIENTE: … | necesito: …]`). Única razón legítima para dejar el ticket esperando a un humano. |
| **base** | Evidencia que respalda el supuesto (documento, módulo, dato del `client-profile`). Vacía ⇒ impacto alto automático. |
| **consulta pre-bloqueo** | Mecanismo actual del Técnico (`TechnicalAnalyst.v2.agent.md:157-164`): publicar una pregunta y dejar el ticket en revisión. Este plan lo reserva para el caso `[PENDIENTE]`. |
| **`blocked_state`** | Estado "Blocked" del tracker. **Siempre** decisión humana; el agente nunca lo aplica (guard en `api/tickets.py:1345-1368`). |
| **`needs_review`** | Estado interno de la ejecución que la manda a la bandeja de revisión. Distinto de "Blocked". |
| **paths post-run** | **[C1]** NO hay chokepoint único: codex usa `harness/post_run.py:finalize_run` (`codex_cli_runner.py:966`); claude corre calidad inline (`claude_code_cli_runner.py:2237-2260`); copilot usa `agent_runner.py:890`. Por eso F4 tiene 3 call-sites. |
| **`operator-corrections`** | Bloque de contexto de prioridad **110** (la máxima) con las correcciones del operador (`intent_preflight.py:206`, `context_enrichment.py:373`). |
| **allowlist de agentes** | `STACKY_ASSUMPTION_MODE_AGENT_TYPES` — qué agentes reciben la política. Default `technical,functional`. |
| **ratchet de tests** | `HARNESS_TEST_FILES` en `run_harness_tests.sh`/`.ps1`: lista que solo crece. |

---

## 8. Orden de implementación

**[C2] El orden de implementación es el orden documental: F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7. Sin excepciones, sin reordenamientos.** (v1 tenía dos órdenes contradictorios — §4 documental vs §8 — y hasta el de §8 dejaba una ventana en la que la flag ON activaba prompts antes que la exención de scoring. v2 renumeró las fases para que no exista otra lectura posible.)

1. **F0** — vocabulario + parser + extensión de `IntentAssumption`. *(Base de todo; puro, sin callers.)*
2. **F1** — scoring y contrato. *(Aterriza DORMIDO: la flag aún no existe, `getattr ⇒ False`. Crítico que preceda a todo cambio de prompt.)*
3. **F2** — las 3 flags + política global en los 3 runtimes. *(Registrar la flag con default ON enciende scoring-exento y política atómicamente; da la guarda `applies_to` que usan F3-F7.)*
4. **F3** — prompts de los dos analistas + espejo de deploy + rescate de 2 tests de la allowlist.
5. **F4** — persistencia: helper + 3 call-sites (codex/claude/copilot).
6. **F5** — panel + endpoint HITL.
7. **F6** — bucle de correcciones (acumulativo, A1).
8. **F7** — Desatascador + KPI sobre metadata.

---

## 9. Definición de Hecho (DoD) global

- [ ] `parse()` reconoce el formato canónico en **texto y en HTML**, con las 3 reglas de impacto, trunca supuestos gigantes (A2), detecta `blocked_without_pending` (C6) y nunca lanza — `test_plan213_assumptions_parser.py` verde (16/16).
- [ ] La política llega **idéntica** a los 3 runtimes, con **una sola** definición del string — `test_all_three_runtimes_share_the_same_text` verde.
- [ ] **[C1]** Los 3 paths post-run persisten supuestos: `grep -rn "apply_to_metadata"` (sin `tests/`) → **exactamente 4 matches** (1 def + codex + claude + copilot); los 3 tests de call-site verdes.
- [ ] **[C2]** Implementado en el orden documental F0→F7; en ningún commit intermedio existe un prompt que pida supuestos sin que la exención de scoring (F1) esté ya mergeada.
- [ ] `developer` **no** recibe la política, no la ve en su contrato y no la persiste — los 3 tests de G6 verdes.
- [ ] Un output con supuestos canónicos **no** pierde confidence (incluido `[PENDIENTE:` canónico); el hedge vago **sí** sigue penalizando — **KPI-6**.
- [ ] Ninguna regla de supuestos produce un `failure` de contrato; el único camino a `needs_review` es `assumption_overload` — verificado por `test_contract_never_fails_on_assumptions`.
- [ ] Toda ejecución de `technical`/`functional` con la flag ON deja `metadata.assumptions` (aunque sea vacía), serializada como **string JSON válido**, en los 3 runtimes — **KPI-2** + blindaje del gotcha de `metadata_json`.
- [ ] El operador puede confirmar/corregir desde la UI sin tocar ADO ni cambiar el estado del ticket — **G1**.
- [ ] Una corrección aparece en la corrida siguiente dentro de `operator-corrections` (prioridad 110), en **un solo** bloque, y las decisiones de las últimas 3 corridas **se acumulan con dedupe** (A1) — **KPI-5** + `test_corrections_accumulate_across_runs`.
- [ ] Los supuestos de alto impacto sin confirmar aparecen en el Desatascador **sin** bloquear nada — **KPI-4**.
- [ ] `metadata.assumptions.blocked_without_pending == false` en una corrida real de los dos analistas (consultable en metadata, C6) — **KPI-1**.
- [ ] Con `STACKY_ASSUMPTION_MODE_ENABLED=false`: scoring, contrato, metadata y board byte-idénticos a hoy; suite existente verde — **KPI-7**.
- [ ] `test_b7_technical_no_autoblock.py` verde **sin modificarlo**; `test_functional_analyst_extraction_rules.py` verde; ambos **movidos** de `harness_ratchet_allowlist.txt` al ratchet, con `_ALLOWLIST_MAX` bajado en 2.
- [ ] Los **8** archivos de test backend nuevos (C11: parser, scoring_and_contract, policy_injection, analyst_prompts, post_run_assumptions, assumptions_endpoint, corrections_loop, unblocker_assumptions) registrados en `run_harness_tests.sh` **y** `run_harness_tests.ps1`; `test_harness_ratchet_meta.py` verde.
- [ ] `STACKY_ASSUMPTION_MODE_ENABLED` en `_CURATED_DEFAULTS_ON`; las 3 flags editables desde la UI de flags.
- [ ] Espejo `DeployStackyAgents/Stacky/agents/` en sync (sha256) con `backend/Stacky/agents/`.
- [ ] `& ".venv\Scripts\python.exe" -m compileall backend -q` sin errores y `npx tsc --noEmit` limpio.
- [ ] Trabajo del operador: **ninguno obligatorio** en todas las fases; confirmar supuestos es opcional y no bloquea.
