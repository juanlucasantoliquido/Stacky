# 27 — Plan Mejoras Invisibles del Motor: el cuarto de máquinas que rinde más sin pedirle nada al operador

**Fecha:** 2026-06-13
**Estado:** propuesto (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 propuestos), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (U0-U2, propuesto), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto) y el **plan de memoria colaborativa v2** (`docs/plans/plan-memoria-colaborativa-stacky-agents-2026-06-06-v2.md`).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia, diseño con archivos exactos, criterios de aceptación, tests TDD y complejidad.

**Tesis (innegociable):** este plan mejora el **resultado** (mejor output, más barato, más rápido, más confiable) **sin agregar trabajo al operador**: ni pasos, ni configuración nueva, ni UI que tenga que tocar. El TRABAJO es invisible — los mecanismos viven detrás de flags internos default **OFF**, se activan por sign-off del que opera el arnés, y NO exponen perillas al operador del día a día. El RESULTADO se nota: el mismo run que el operador lanzó sale mejor y/o más barato. Es el "cuarto de máquinas" — el operador disfruta del aire acondicionado sin ver el compresor.

**"Invisible" NO significa "autónomo" (frontera dura, regla 11):** invisible quiere decir que el operador no configura ni ve el mecanismo. NO quiere decir que el sistema decida solo. **Cada run lo inició el operador**; nada se publica a ADO sin el verdict humano; ningún aprendizaje muta prompts/memoria/goldens sin aprobación. Todos los ítems de este plan operan DENTRO de un run que el operador ya lanzó, o ajustan sustrato (caché, ranking, presupuesto) que no toma decisiones por el humano. Si un ítem se puede leer como "el sistema procesó/publicó/decidió sin que el operador lo pidiera", está mal diseñado. (Esto se evaluó y descartó explícitamente en el doc 24 §2: sin auto-intake, sin triage automático, sin procesamiento nocturno.)

**Relación con los docs 22/23/24 (frontera de no-solapamiento):**
- El doc 22 ataca la capa *interna* del arnés (perfiles, guardrails, taxonomía de fallos, pricing, versionado, intake, CI, advisor, golden loop, cache). El doc 23 la *perceptible*. El doc 24 la de *amplificación* (briefing curado, refine, plan-first, crítica, flywheel) — toda con **gestos explícitos** del operador.
- Este plan es el complemento exacto del 24: **donde el 24 le da al operador palancas que VE y usa, este le da mejoras que NO ve ni usa.** Misma filosofía centauro, lado opuesto del tablero.
- **Frontera crítica con mecanismos ya construidos** (se EXTIENDEN, no se duplican): el loop de autocorrección F1.3/H2.3 (`services/cli_autocorrect.py`), el presupuesto de contexto con ranking F2.4 (`context_enrichment._apply_context_budget`), el routing por complejidad FA-04 (`llm_router.decide`), el outbox con retry/backoff (`ado_write_outbox`), el output cache de copilot (`output_cache`), el pricing fallback V0.5 (`harness/pricing`). Cada ítem declara qué seam extiende y por qué no re-implementa.
- Ningún ítem bloquea en 22/23/24: todos declaran modo degradado.

> **Nota de numeración:** el ítem V2.1 del doc 22 referenciaba un checklist de nuevo runtime; el doc 24 lo asignó a `docs/25_CHECKLIST_NUEVO_RUNTIME.md`, que **ya existe**. El usuario llama coloquialmente "plan 26" a este documento, pero como el 25 está tomado y el plan de memoria configurable es el doc 26, este se materializa como **doc 27** (mismo corrimiento que aplicaron 23/24).

---

## 1. Punto de partida: el sustrato del motor que YA existe (no re-implementar)

Verificado contra el código el 2026-06-13 en `codex/subida-cambios-pendientes`. Esta tabla es el hallazgo central: hay maquinaria de optimización **a medio cablear** (existe pero apenas se usa, o se usa en un runtime y no en otro). El mayor valor de este plan es **terminar de aprovechar lo que ya está**, no inventar.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Ensamblado de contexto multi-runtime (memoria → client-profile → épica → artefactos → similares → comentarios ADO) | `services/context_enrichment.py:34` (`enrich_blocks`), llamado en los 3 runtimes | OK — pero **sin dedup entre bloques** (D-I1) |
| Presupuesto de contexto con ranking por prioridad + truncado F2.4 | `services/context_enrichment.py:140` (`_apply_context_budget`), prioridades `:106` (`_BLOCK_PRIORITY`), estimador `_block_token_estimate:129` | OK — ranking por prioridad FIJA, **no por relevancia al ticket** (D-I1) |
| Routing de modelo por complejidad estimada (FA-04) con cap duro | `services/llm_router.py:174` (`decide`), clamp `:33` (`clamp_model`), reglas de upgrade `:247-258`; invocado en `agent_runner.py:649` | OK — pero `fingerprint_complexity` **casi nunca se computa** (llega `None`, D-I4) |
| Loop de autocorrección intra-run: claude (F1.3) y codex (H2.3) son **dos módulos distintos** (no uno) | claude `services/cli_autocorrect.py::AutocorrectLoop` (clase; cableado `claude_code_cli_runner.py:686-690`, `on_turn_end:736`, `summary:905`, metadata `autocorrect`); codex `services/codex_autocorrect.py::run_autocorrect_loop` (función; cableado `codex_cli_runner.py:636-674`, devuelve `retries_used`/`final_artifacts_ok`, metadata `autocorrect_codex`) | OK — disparan solo por **contract failures de artifacts**, no por output vacío/malformado (D-I3) |
| Post-run unificado: contract gate + confidence + status final | `harness/post_run.py:35` (`finalize_run`), gate `:76`, status `:75` | OK — `finalize_run` NO recibe `model` ni `execution_id`; es puro sobre el texto (límite para auto-reparación, ver I1.1) |
| Telemetría de run (turnos, costo, tokens, cache_read) persistida en metadata | `harness/telemetry.py:28` (`RunTelemetry`), `persist:122` (`metadata["harness_telemetry"]` + `claude_telemetry` legacy), estimación `_maybe_estimate_cost:53` | OK — `cache_read_tokens` se persiste pero **nada lo aprovecha** (D-I2) |
| Pricing fallback multi-proveedor (V0.5) | `harness/pricing.py:66` (`estimate_cost`, match por prefijo más largo, fallback `None`), tabla `:24`, override `STACKY_PRICING_JSON` `:39` | OK |
| Output cache (clave = agent_type + PROMPT_VERSION + bloques normalizados) | `services/output_cache.py:73` (`compute_key`), `lookup`/`store` usados SOLO en copilot `agent_runner.py:602,767`, gated `config.CACHE_ENABLED` | OK en copilot — **los runtimes CLI no lo usan** (D-I2) |
| Retrieval TF-IDF coseno (memoria, tickets similares, ejecuciones) | `services/embeddings.py:42` (`_tokenize`), `top_k:158`, IDF cache TTL 10min `:121`; memoria `memory_store.search:677` | OK — **TF-IDF puro, sin BM25, sin expansión de query** (D-I5) |
| Outbox de escritura ADO con retry/backoff exponencial + dedup por idempotency_key | `services/ado_write_outbox.py:210` (`enqueue`), backoff `:199` (`compute_backoff_seconds`), dedup `:248`, MAX_ATTEMPTS=6 | OK — el **WRITE** ya es robusto; las **lecturas** caras de ADO NO se cachean (D-I6) |
| Guard anti-duplicados + cap de concurrencia (V0.2/V0.3) | `services/run_guard.py:21` (`find_active_run`, estados activos `:18`), `services/run_slots.py:28` (`try_acquire`) | OK |
| Capacidades por runtime (resume, stdin, telemetría, mcp) | `harness/capabilities.py:21` (`CAPABILITIES`), campos `:11` | OK — el seam correcto para decidir por-runtime sin `if` dispersos |

**Restricciones vinculantes (idénticas a docs 22/23/24, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable); "solo Stacky escribe en ADO" = todo por `ado_write_outbox`; mono-operador **sin RBAC**; claves de metadata existentes son contrato (agregar, nunca renombrar); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR, default OFF/0, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → validar por archivo de test; **sin fallback silencioso entre runtimes**; sin deps npm/py nuevas sin justificación escrita; el build congelado NO tiene FTS5 verificado (no introducirlo).

**Regla 11 (innegociable):** invisible ≠ autónomo. Cada run lo inicia el operador; nada se publica solo; ningún ítem decide por el humano. Las mejoras de este plan o bien ocurren DENTRO del run lanzado (auto-reparación, routing) o bien ajustan sustrato sin tomar decisiones (caché, dedup, ranking, caps). Cada ítem trae una línea explícita **"Por qué NO viola rule 11"**.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía, ni auto-intake, ni procesamiento nocturno.** Ningún run nace sin el operador. Ningún ítem "agarra trabajo solo". (Descartado en doc 24 §2; este plan lo respeta al pie.)
2. **No publica ni transiciona ADO por su cuenta.** El cierre de loop ADO es U1.3 (doc 23); el preview pre-publicación es U2.2 (doc 23). Acá no se toca el verdict humano ni el path de publicación. La única interacción con ADO es **cachear lecturas** (I3.2) y no cambia qué/ cuándo se escribe.
3. **No expone perillas nuevas al operador.** Si un ítem necesita configuración del operador, NO pertenece a este plan (va al doc 24 o al 26). Los flags de este plan son **internos** (los maneja quien administra el arnés vía la pantalla de flags genérica que ya existe), no superficies del operador.
4. **No re-implementa mecanismos existentes.** El autocorrect (F1.3/H2.3), el routing (FA-04), el budget (F2.4), el outbox retry, el output cache y el pricing ya existen. Este plan los **extiende/termina de aprovechar**. Lo nuevo (prefix-cache del proveedor, dedup semántico, caché de lecturas ADO) está marcado como greenfield con su evidencia de no-existencia.
5. **No introduce FTS5.** El retrieval sigue siendo TF-IDF en Python (plan v2 §B6). Las mejoras de retrieval (I2.x) son sobre ese sustrato, sin nuevas tablas virtuales.

---

## 3. Diagnóstico: dónde el motor deja valor sobre la mesa (con evidencia)

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-I1** | **El ensamblado de contexto no deduplica ni re-rankea por relevancia.** `enrich_blocks` apila bloques (memoria, client-profile, épica, similares, comentarios) y `_apply_context_budget` los ordena por una **prioridad FIJA por id** (`_BLOCK_PRIORITY`), no por relevancia al ticket; no hay dedup de hechos repetidos entre bloques (el mismo dato del cliente puede venir en `client-profile` y en `stacky-memory` y en un comentario ADO). Confirmado: NO existe dedup/rerank semántico fuera del budget (grep `dedup`/`rerank`/`semantic` en `services/` → 0). | `services/context_enrichment.py:106` (prioridad fija), `:140` (budget por prioridad), ausencia de dedup verificada | Tokens gastados en repetir el mismo hecho 3 veces; bloques irrelevantes al ticket ocupan presupuesto que desplaza a los relevantes. Output menos certero y más caro. |
| **D-I2** | **No hay reuso de contexto entre runs del mismo ticket, ni prompt-caching del proveedor.** El output cache (`output_cache`) solo lo usa copilot (`agent_runner.py:602,767`); los runtimes CLI (claude/codex) re-ensamblan y re-envían todo en cada run. No existe `cache_control`/prefix estable para el prompt-caching nativo de Anthropic (grep `cache_control`/`prompt_cache`/`ephemeral` → 0 en código propio); `RunTelemetry.cache_read_tokens` se persiste pero nada lo provoca ni lo mide para optimizar. | `services/output_cache.py` (solo copilot), `harness/telemetry.py:28` (`cache_read_tokens` sin productor), ausencia de cache_control verificada | Refinar/re-lanzar sobre el mismo ticket paga el contexto entero cada vez. Con prompts largos y estables (épica + perfil + memoria), se desperdicia el descuento de caching del proveedor. Más caro y más lento, invisible al operador. |
| **D-I3** | **La auto-reparación intra-run solo cubre artifacts inválidos, no output vacío/malformado.** Los loops de autocorrección (claude `cli_autocorrect.AutocorrectLoop` / codex `codex_autocorrect.run_autocorrect_loop` — módulos distintos) disparan correcciones cuando el contract gate de artifacts falla, pero si el run termina con **output vacío** o un JSON de pending-task malformado por algo trivial, no hay un reintento final antes de presentar el resultado: cae directo a `needs_review`/error. `finalize_run` es puro sobre el texto (no puede relanzar). | claude `services/cli_autocorrect.py::AutocorrectLoop` (`claude_code_cli_runner.py:686`), codex `services/codex_autocorrect.py::run_autocorrect_loop` (`codex_cli_runner.py:636`); `harness/post_run.py:35` (sin capacidad de relanzar) | `needs_review` triviales que un solo reintento habría salvado → trabajo de revisión humano evitable, latencia percibida (el operador tiene que relanzar a mano). |
| **D-I4** | **El routing por dificultad está a medio cablear: `fingerprint_complexity` casi nunca llega.** `llm_router.decide` tiene reglas de upgrade por complejidad (`XL` → sonnet; tokens > umbral → sonnet; qa chico → haiku) pero `fingerprint_complexity` se pasa como parámetro desde arriba con default `None` (`agent_runner.py:41,649`); no hay un estimador que lo compute de forma consistente para los 3 runtimes. Resultado: el routing decide casi siempre por tokens crudos y default-por-agente, sin señal real de dificultad del encargo. | `services/llm_router.py:174,229,247`, `agent_runner.py:41` (default None), `:649` (se pasa tal cual) | Encargos simples corren en sonnet (caro de más); encargos difíciles cortos corren en haiku (calidad de menos). Plata y calidad sobre la mesa, invisible. |
| **D-I5** | **El retrieval es TF-IDF coseno puro, sin expansión de query ni normalización robusta.** `embeddings.top_k` y `memory_store.search` usan el mismo tokenizer (`_tokenize`, regex + stopwords) y coseno TF-IDF; no hay expansión de sinónimos/lemmas, ni BM25, ni normalización de acentos/variantes más allá del regex. Una memoria/ticket relevante con vocabulario distinto al query **no matchea**. (El build no tiene FTS5 verificado → no es opción.) | `services/embeddings.py:42,158`, `services/memory_store.py:677,728` | Memoria y tickets similares relevantes se pierden por mismatch léxico → el agente arranca con menos contexto del que existe. Output menos informado. |
| **D-I6** | **Las lecturas caras de ADO no se cachean; el outbox de escritura sí es robusto pero el read no.** El `ado_write_outbox` ya tiene retry/backoff + dedup para WRITES. Pero las LECTURAS caras (estructura de épica, tickets similares, comentarios/adjuntos) se piden a ADO en cada `enrich_blocks` sin caché con invalidación. Refinar 3 veces el mismo ticket pega 3 veces a ADO por la misma épica. | `services/ado_write_outbox.py:199,248` (write robusto); `context_enrichment.py:575` (`_inject_ado_context` pide en cada run), ausencia de read-cache | Latencia por run (round-trips a ADO) y carga sobre el PAT; el operador espera de más sin saber por qué. |
| **D-I7** | **Los caps de contexto y los presupuestos son estáticos, no aprenden de la telemetría.** Los caps por agente (memoria) y el budget de tokens (F2.4) son constantes; la telemetría (`harness_telemetry`) registra cuánto contexto y costo tuvo cada run, pero nada realimenta el tamaño óptimo de contexto por agente. | `services/memory_store.py:107` (caps fijos), `context_enrichment.py:160` (budget fijo), `harness/telemetry.py:122` (datos sin consumir para esto) | Se inyecta de más a agentes que rinden igual con menos (caro), o de menos a agentes que necesitarían más (calidad). Sin un loop de afinado, queda en intuición. |
| **D-I8** | **El briefing se ensambla recién después del launch, en serie, dentro del runner.** `enrich_blocks` corre sincrónicamente al arrancar el run (cada injector en secuencia: épica, artifacts, similares, comentarios ADO), y solo entonces empieza el trabajo del modelo. No hay pre-ensamblado al seleccionar el ticket ni paralelización de los injectors independientes. | `context_enrichment.py:67-96` (injectors en serie), llamado al inicio de cada runner | Time-to-first-token más alto: el operador espera el ensamblado completo (incluidas llamadas a ADO) antes de ver progreso. Latencia percibida, invisible la causa. |

**Lectura estratégica:** los docs 21-24 hicieron el arnés confiable, visible y amplificado por el operador. Este plan exprime el motor por dentro: ensambla contexto más inteligente (menos tokens, más señal), reusa lo que ya pagó (caché de contexto y de lecturas ADO), salva los fallos triviales dentro del run que el operador ya lanzó, elige el modelo a la medida de la dificultad, y afina el presupuesto con datos en vez de constantes. El operador no toca nada: ve outputs mejores, más rápidos y más baratos.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo** y por riesgo. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: I0 (quick wins de bajo riesgo) → I1 (los de mayor valor: auto-reparación y routing) → I2 (estructurales de contexto/caché) → I3 (diferenciales con datos).

### FASE I0 — Quick wins: exprimir el sustrato existente sin riesgo

---

#### I0.1 Dedup de hechos repetidos entre bloques de contexto

- **Ataca:** D-I1 (mitad dedup).
- **Resultado visible:** menos tokens por run con el mismo o mejor output (el mismo hecho deja de viajar 3 veces).
- **Diseño:**
  - Flag interno: `STACKY_CONTEXT_DEDUP_ENABLED` (bool, default **false**) + `STACKY_CONTEXT_DEDUP_PROJECTS` (csv) en `config.py` + `FLAG_REGISTRY` (mismo patrón que `STACKY_CONTEXT_BUDGET_*`, `services/harness_flags.py:104`). OFF = byte-idéntico.
  - Nuevo paso aditivo en `enrich_blocks` (`context_enrichment.py`), DESPUÉS de los injectors y ANTES de `_apply_context_budget` (`:95`): `_dedup_blocks(blocks)` — dedup **conservador y barato** a nivel de líneas/oraciones: normaliza cada línea (lowercase, colapsa espacios — reusa el patrón de `memory_store._normalized_hash:255`), y dentro de los bloques de **menor prioridad** (`_block_priority`) elimina líneas cuyo hash ya apareció en un bloque de **mayor prioridad**. Nunca toca `ado-epic-structured`/`client-profile`/`modal_user_input` (prioridad alta = fuente de verdad, se conserva intacta); solo poda repeticiones en `ado-comments`/`ado-similar-tickets`/`stacky-memory` cuando el hecho ya está en uno más prioritario.
  - Es **léxico exacto**, NO semántico (el dedup semántico real es I2.1, detrás de su propio flag y con más riesgo). Esto es el quick win seguro: solo borra líneas idénticas duplicadas.
  - Puro sobre `blocks`; best-effort (cualquier excepción → bloques sin tocar, mismo contrato que `_apply_context_budget:151`).
- **Por qué NO viola rule 11:** ajusta sustrato (el texto del prompt) sin tomar ninguna decisión por el humano; el run sigue siendo el que el operador lanzó; no cambia qué se publica.
- **Criterios de aceptación:** flag OFF → `enrich_blocks` byte-idéntico (test de regresión sobre fixtures existentes de `test_context_budget.py`); una línea idéntica presente en épica y en un comentario ADO → queda solo en la épica; bloques de alta prioridad nunca se podan; dedup + budget conviven (el dedup corre antes, el budget sobre el resultado).
- **Tests (TDD, `tests/test_context_dedup.py`):** dedup léxico por prioridad, alta prioridad intacta, flag OFF byte-idéntico, interacción con budget.
- **Complejidad:** M.

---

#### I0.2 Cómputo consistente de `fingerprint_complexity` para los 3 runtimes

- **Ataca:** D-I4 (mitad: que la señal exista).
- **Resultado visible:** ninguno por sí solo (es el habilitador de I1.2); pero deja el routing listo para decidir por dificultad real.
- **Diseño:**
  - Existe la estructura: `decide(..., fingerprint_complexity=...)` ya consume la señal (`llm_router.py:247`). Falta **producirla**. Nuevo helper puro `harness/complexity.py::estimate_complexity(*, agent_type, ticket_title, ticket_description, blocks) -> str` → `"S"|"M"|"L"|"XL"` con heurística barata y determinística (sin LLM): longitud y estructura del encargo (nº de criterios/bullets en la descripción, nº de bloques de contexto, tamaño total estimado vía `_block_token_estimate`, presencia de palabras-señal de complejidad como "migración", "refactor", "integración"). Es transparente y testeable; NO llama a ningún modelo.
  - Cableado: en el punto donde cada runner arma la decisión de modelo (copilot `agent_runner.py:649`; claude `claude_code_cli_runner.py:~557`; codex vía `harness/model_policy.resolve_model`), computar `estimate_complexity(...)` y pasarlo a `decide`. Hoy claude/codex no pasan por `llm_router.decide` igual que copilot — verificar al implementar y, si el routing CLI usa otra ruta (`model_policy`), agregar la señal ahí de forma equivalente. **Sin fallback silencioso entre runtimes:** cada runtime computa su propia complejidad con el mismo helper.
  - Flag: `STACKY_COMPLEXITY_ESTIMATION_ENABLED` (bool, default **false**) — OFF → `fingerprint_complexity=None` como hoy (routing byte-idéntico).
- **Por qué NO viola rule 11:** computar una estimación y pasarla al router no decide por el humano; el cap de modelo (`clamp_model`) sigue siendo el techo; el operador puede seguir forzando el modelo (override gana, `llm_router.py:212`).
- **Criterios de aceptación:** flag OFF → `decide` recibe `None` y el modelo elegido es idéntico a hoy; encargo con 8 criterios + 6 bloques + "migración" → `XL`; encargo trivial corto → `S`; el helper es puro (mismo input → mismo output, sin DB ni red); los 3 runtimes computan la misma señal para el mismo input.
- **Tests (TDD, `tests/test_complexity_estimation.py`):** clasificación por tamaño/estructura/palabras-señal, determinismo, flag OFF no-op.
- **Complejidad:** M.

---

#### I0.3 Pre-warming del cache de lecturas ADO al seleccionar el ticket

- **Ataca:** D-I8 (mitad pre-ensamblado) + prepara I3.2.
- **Resultado visible:** time-to-first-token más bajo cuando el operador finalmente lanza (la épica/similares ya están en caché).
- **Diseño:**
  - **Depende de I3.2** (caché de lecturas ADO con invalidación) — sin esa caché, pre-warmear no sirve. Si I3.2 no está, este ítem es no-op declarado.
  - Backend: endpoint `POST /api/tickets/<id>/prewarm` (nuevo, `api/tickets.py`) que dispara, en un thread best-effort, las lecturas caras que `enrich_blocks` haría (estructura de épica, similares) y las deja en la caché de I3.2. Idempotente (si ya está caliente, no hace nada). NO crea execution, NO toca el modelo, NO escribe ADO.
  - Frontend: cuando el operador **selecciona** un ticket en el board (no cuando lanza), `TicketBoard` dispara el prewarm de forma silenciosa (fire-and-forget, sin spinner, sin bloquear nada). Si falla, no pasa nada (el run igual ensambla en vivo).
  - Flag: `STACKY_ADO_PREWARM_ENABLED` (bool, default **false**) — OFF → el frontend no dispara y el endpoint 404/feature-gated.
- **Por qué NO viola rule 11:** seleccionar un ticket es un gesto del operador; pre-warmear lecturas read-only no lanza ningún run ni decide nada; el run sigue siendo explícito. (No es "el sistema empezó a trabajar solo": es cachear datos que el operador va a necesitar si decide lanzar, y que de todos modos se leerían.)
- **Criterios de aceptación:** seleccionar un ticket con flag ON → la épica/similares quedan en caché (verificable: el run siguiente reusa la caché sin pegar a ADO); seleccionar con flag OFF → cero llamadas; prewarm de un ticket ya caliente → no-op; el prewarm nunca crea execution ni bloquea la UI.
- **Tests (TDD):** backend `tests/test_ado_prewarm.py` (dispara lecturas, idempotente, sin execution, flag OFF); vitest del fire-and-forget en selección.
- **Complejidad:** S/M (depende de I3.2).

---

### FASE I1 — Estructurales de mayor valor: salvar runs y elegir bien el modelo

---

#### I1.1 Auto-reparación del run ante output vacío/malformado (extiende el autocorrect) — el ítem de mayor valor

- **Ataca:** D-I3. Reusa y EXTIENDE los loops de autocorrección (claude `cli_autocorrect.AutocorrectLoop` / codex `codex_autocorrect.run_autocorrect_loop`, F1.3/H2.3); NO los re-implementa.
- **Resultado visible:** menos `needs_review` triviales — runs que hoy mueren por un output vacío o un JSON malformado se recuperan solos antes de presentarse, sin que el operador relance a mano.
- **Frontera con lo existente (declarada):** los loops de autocorrección ya corrigen **intra-turno** cuando los artifacts fallan el contract gate — son **dos módulos distintos**: claude `cli_autocorrect.AutocorrectLoop` (clase con `on_turn_end()`/`summary()`, contador interno) vía stdin; codex `codex_autocorrect.run_autocorrect_loop()` (función que devuelve `retries_used`) vía `exec resume`. Este ítem cubre el caso que esos loops NO atrapan: **al final del run**, el output principal sale **vacío** o el `pending-task.json`/`comment.html` sale **malformado por algo trivial** (no es un fallo de criterio, es un glitch). En ese caso se reintenta **UNA** vez antes de `finalize_run`.
- **Diseño:**
  - `finalize_run` es puro (no puede relanzar, `harness/post_run.py:35`), así que la reparación vive en el **runner**, justo ANTES de invocar `finalize_run` (codex `codex_cli_runner.py:714`; claude, en su punto equivalente de cierre). Nuevo helper `harness/run_repair.py::needs_repair(output_text, artifacts) -> str | None` (puro) → devuelve el motivo (`"empty_output"|"malformed_artifact"`) o `None`. "Malformado trivial" = el archivo existe pero no parsea como JSON / le falta una clave estructural obvia — NO un fallo de criterio (eso es el contract gate y va a `needs_review` como siempre).
  - Si `needs_repair` devuelve un motivo Y el runtime soporta resume/stdin (`capabilities.CAPABILITIES[runtime].supports_resume`, `harness/capabilities.py:21`) Y no se agotó el presupuesto de reparación: un **único** reintento con un mensaje corto y fijo ("Tu salida quedó vacía/malformada. Re-generá SOLO el artefacto, mismo trabajo, formato válido.") por el MISMO transporte que usa el autocorrect (stdin/resume). Si el reintento arregla → sigue el flujo normal; si no → `finalize_run` como hoy (`needs_review`).
  - Presupuesto duro: `STACKY_RUN_REPAIR_MAX_RETRIES` (int, default 1) — UNA sola reparación; nunca un loop infinito. **El conteo se comparte con el autocorrect del runtime, que tiene forma distinta por módulo:** en claude, leer/incrementar el contador interno del objeto `AutocorrectLoop` (mismo `max_retries`); en codex, sumar al `retries_used` que devuelve `run_autocorrect_loop`. Así el total de mensajes correctivos por run (autocorrect + repair) no se dispara. Si unificar ambos contadores resulta caro, alternativa aceptable y declarada: presupuesto propio del repair acotado a 1, documentando que en el peor caso son autocorrect(N)+repair(1) = N+1 mensajes.
  - Modelo: el reintento usa el MISMO modelo (dentro del clamp); NO escala a un modelo superior (eso sería I1.2 territory y cambiaría el costo de forma no obvia). Documentar que la reparación es "mismo modelo, una vez".
  - Sello: `metadata["run_repair"] = {"attempted": true, "reason": ..., "recovered": bool}` (clave NUEVA, aditiva).
  - Flag: `STACKY_RUN_REPAIR_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`. OFF → comportamiento actual exacto (output vacío → `needs_review` directo).
- **Por qué NO viola rule 11:** el run lo lanzó el operador; la reparación ocurre DENTRO de ese run, antes de presentar el resultado; NO publica nada (el verdict humano y la publicación siguen intactos, U1.3/U2.2 del doc 23); es exactamente lo que un humano haría manualmente (relanzar una vez) pero sin obligarlo. No es una decisión nueva: es completar el trabajo que ya se pidió.
- **Criterios de aceptación:** run codex con output vacío + flag ON + runtime con resume → un reintento; si recupera → `completed` con `run_repair.recovered=true`; si no → `needs_review` con `recovered=false`; output malformado (JSON inválido) → repara; fallo de **criterio** (contract gate de contenido) → NO dispara repair (va a `needs_review` como hoy — el repair no enmascara mala calidad); github_copilot (sin resume) → no repara (sin fallback silencioso; degrada a comportamiento actual); el repair comparte el techo de reintentos del autocorrect del runtime correspondiente (claude `AutocorrectLoop` / codex `run_autocorrect_loop`), no se suman; flag OFF → byte-idéntico.
- **Tests (TDD, `tests/test_run_repair.py`):** `needs_repair` (vacío/malformado/None); un solo reintento; recovered true/false; criterio-fail no dispara; sin resume no repara; tope compartido con autocorrect; flag OFF. Mock de runner (sin binarios reales).
- **Complejidad:** M/L (toca el cierre de ambos runners CLI; partible: PR1 codex, PR2 claude).

---

#### I1.2 Routing por dificultad estimada dentro del clamp

- **Ataca:** D-I4 (cierre). Depende de I0.2 (la señal de complejidad). Reusa `llm_router.decide`.
- **Resultado visible:** runs simples más baratos (haiku donde alcanza), runs difíciles cortos mejor servidos (sonnet donde la dificultad lo pide) — sin que el operador elija el modelo.
- **Diseño:**
  - Con I0.2 produciendo `fingerprint_complexity` real, las reglas de upgrade de `decide` (`llm_router.py:247-258`) ya hacen lo correcto para Claude (XL→sonnet) y Copilot (XL→o3). Este ítem **afina** esas reglas y agrega el camino **down** que hoy es tímido: encargo estimado `S` + agente no crítico → preferir el modelo barato (haiku/mini) aunque los tokens no sean chicos, porque la dificultad es baja. Hoy el downgrade solo mira tokens (`qa < 6k`, `functional < 3k`), no dificultad.
  - Reglas nuevas (todas DENTRO del clamp, `clamp_model` sigue siendo el techo, `:260`): `complexity=="S"` y `agent_type not in {critical set}` → modelo barato del backend; `complexity in {"L","XL"}` → modelo capable (sonnet/o3) aunque los tokens sean pocos. El override del operador SIEMPRE gana (`:212`).
  - Flag: `STACKY_DIFFICULTY_ROUTING_ENABLED` (bool, default **false**). OFF → `decide` se comporta como hoy (las reglas nuevas se saltean; el `fingerprint_complexity` se ignora salvo las reglas preexistentes). El cap duro (`clamp_model`) NO se toca en ningún caso.
  - **Transparencia:** el `RoutingDecision.reason` (`:117`) explica la elección ("complexity=S → haiku (downgrade por dificultad baja)") — queda en logs/telemetría para auditar que el routing es sensato. NO se expone como perilla al operador.
- **Por qué NO viola rule 11:** elegir el modelo a la medida de la dificultad es una decisión de sustrato acotada por el cap duro y por el override del operador; no cambia QUÉ se hace ni QUÉ se publica; el operador puede forzar el modelo cuando quiera. Es exactamente lo que el router YA hace por tokens, ahora también por dificultad.
- **Criterios de aceptación:** flag OFF → routing byte-idéntico a hoy; encargo `S` no-crítico → modelo barato aunque tokens > umbral viejo; encargo `XL` corto → modelo capable; override del operador → gana siempre, ignorando la complejidad; `clamp_model` jamás superado (test: una regla que pidiera opus se clampa a sonnet); `reason` explica la elección.
- **Tests (TDD, `tests/test_difficulty_routing.py`):** downgrade por S, upgrade por XL corto, override gana, clamp respetado, flag OFF; extensión de los tests existentes de `llm_router`.
- **Complejidad:** M.

---

### FASE I2 — Estructurales de contexto y caché: reusar lo que ya se pagó

---

#### I2.1 Re-ranking de bloques por relevancia al ticket (sobre el budget F2.4)

- **Ataca:** D-I1 (cierre: rerank). Extiende `_apply_context_budget`; NO lo reemplaza.
- **Resultado visible:** cuando el presupuesto obliga a recortar, se conservan los bloques **relevantes al ticket**, no los de prioridad fija más alta — output más certero con el mismo budget.
- **Diseño:**
  - Hoy `_apply_context_budget` (`context_enrichment.py:140`) ordena por `_block_priority` (fijo) y trunca/dropea por presupuesto. Este ítem agrega una señal de **relevancia al ticket** que modula la prioridad de los bloques de prioridad media/baja (NUNCA de los altos: épica/client-profile/directivas siguen siendo intocables).
  - Relevancia barata sin deps: reusar el tokenizer y el coseno TF-IDF de `services/embeddings.py` (`_tokenize:42`) entre el texto del ticket (título+descripción) y el contenido de cada bloque candidato a recorte. Score combinado: `efectivo = prioridad_fija + w * relevancia_normalizada` (w pequeño, configurable interno) — la prioridad fija manda, la relevancia desempata y rescata bloques relevantes que la prioridad sola descartaría.
  - Solo aplica al **orden de conservación** dentro del budget (la lista `ordered` en `:169`); no cambia el orden de presentación (que sigue siendo el original, `:209`). Es decir: mejora QUÉ se conserva bajo presión, no CÓMO se narra.
  - Flag: `STACKY_CONTEXT_RERANK_ENABLED` (bool, default **false**) — OFF → budget se comporta exactamente como hoy (ranking por prioridad fija pura).
- **Por qué NO viola rule 11:** decide qué contexto conservar bajo presupuesto, no qué hacer con él; sustrato puro; el run sigue siendo del operador.
- **Criterios de aceptación:** flag OFF → budget byte-idéntico (regresión sobre `test_context_budget.py`); con presupuesto ajustado y dos bloques de igual prioridad media, se conserva el más relevante al ticket; bloques de prioridad alta nunca se recortan independientemente de la relevancia; el orden de presentación no cambia (solo el de conservación).
- **Tests (TDD, `tests/test_context_rerank.py`):** rescate por relevancia bajo presión, alta prioridad intocable, orden de presentación estable, flag OFF idéntico.
- **Complejidad:** M.

---

#### I2.2 Prompt-prefix estable para el caching del proveedor (claude) + reuso entre runs del mismo ticket

- **Ataca:** D-I2. Greenfield (no existe `cache_control` en el código propio).
- **Resultado visible:** refinar/re-lanzar sobre el mismo ticket es más barato y más rápido (el proveedor cobra menos por el contexto repetido).
- **Diseño:**
  - **Alcance honesto:** el prompt-caching nativo difiere por runtime. **claude** (vía el CLI / la API que el CLI usa) soporta caché de prefijo; **codex/copilot** tienen otra mecánica. Sin fallback silencioso: este ítem se implementa **solo para claude** y se declara explícitamente que codex/copilot NO lo usan (degradan a comportamiento actual). NO se finge soporte uniforme.
  - Mecanismo: estructurar el prompt de claude para que la parte **estable** (system prompt + bloques de contexto pesados y constantes: épica, client-profile, directivas, memoria) vaya PRIMERO y de forma byte-estable entre runs del mismo ticket, y la parte **variable** (feedback de refine, instrucción del turno) vaya al final. Si el CLI/SDK expone el marcado de caché (`cache_control: ephemeral` de Anthropic), aplicarlo al final del bloque estable; si solo respeta el caché por prefijo idéntico, basta con garantizar el orden y la estabilidad byte a byte (no reordenar bloques entre runs del mismo ticket).
  - Medición: `RunTelemetry.cache_read_tokens` (`harness/telemetry.py:28`) ya existe — este ítem lo **puebla** desde lo que reporte el CLI de claude, para que el ahorro sea medible (y aparezca en el digest U1.5 / harness-health H8 sin trabajo extra).
  - Reuso entre runs del mismo ticket: el refine (C1.1 doc 24) ya reanuda sesión (resume) → el contexto pesado ya está del lado del proveedor; este ítem garantiza que cuando NO hay resume (primer run vs run nuevo del mismo ticket), el prefix estable maximice el cache-hit del proveedor.
  - Flag: `STACKY_PROMPT_PREFIX_CACHE_ENABLED` (bool, default **false**) + `..._PROJECTS` (csv). OFF → el prompt se arma como hoy.
- **Por qué NO viola rule 11:** es puramente una optimización de cómo se ordena/marca el prompt de un run que el operador lanzó; no cambia el contenido del trabajo ni qué se publica.
- **Criterios de aceptación:** flag OFF → prompt de claude byte-idéntico a hoy; flag ON → el bloque estable va primero y es byte-idéntico entre dos runs del mismo ticket (test de estabilidad del prefix); `cache_read_tokens` se puebla cuando el CLI lo reporta; codex/copilot → sin cambios (declarado, verificado por test que el flag no toca esos runners); el costo reportado refleja el descuento cuando hay cache-hit.
- **Tests (TDD, `tests/test_prompt_prefix_cache.py`):** estabilidad byte del prefix entre runs, marcado de caché aplicado solo a claude, telemetría de cache_read poblada, flag OFF idéntico, codex/copilot intactos.
- **Complejidad:** L (requiere verificar el contrato real del CLI de claude respecto al caching; partible: PR1 ordenar/estabilizar prefix + medir, PR2 marcado explícito si el CLI lo soporta).
- **Dependencias:** consultar la referencia de la API de Claude para el contrato exacto de `cache_control` antes de implementar el marcado (el ordenamiento estable no lo requiere).

- **ESTADO: DIFERIDO FORMALMENTE (2026-06-15).** Verificado contra el código + la referencia oficial de la API de Claude. **No existe superficie controlable por Stacky.** No se implementa flag ni código (sería contrato inventado o no-op silencioso — viola reglas 11 y "sin fallback silencioso").
  - **Realidad técnica verificada:**
    1. El runtime claude **invoca el CLI `claude` como subproceso** (`claude_code_cli_runner.py:641` `Popen`; comando en `_build_command` :1311-1364 = `claude -p --input-format stream-json --output-format stream-json --verbose [--append-system-prompt-file] [--settings] [--mcp-config] [--resume]`). **NO** llama a la Messages API / SDK directo.
    2. El prompt viaja por stdin como mensaje de usuario stream-json; el envelope (`_user_message_line` :221-234) es **solo** `{"type":"user","message":{"role":"user","content":[{"type":"text","text":...}]}}`. **No hay campo `cache_control`** en ese contrato de stdin.
    3. `cache_control:{type:"ephemeral"}` es un campo **de la request de la Messages API** (referencia oficial Anthropic / prompt-caching): se coloca en content-blocks de `system`/`tools`/`messages` que se pasan a `messages.create()`, con render order `tools→system→messages` y match por prefijo. **No es un campo del input stdin del CLI.**
    4. El CLI **es el cliente de la API**: posee `system` (persona vía `--append-system-prompt-file` + su propio system prompt), `tools` e historial — el prefijo realmente cacheable — y aplica sus propios breakpoints. El mensaje de usuario que Stacky inyecta es el **sufijo volátil** de `messages`, después del breakpoint por diseño.
    5. **El CLI gestiona el caché internamente y ya lo reporta**: `_capture_result_telemetry` (:1868-1895) extrae `cache_read_input_tokens`/`cache_creation_input_tokens` del evento `result`, y `harness/telemetry.py:79` los mapea a `RunTelemetry.cache_read_tokens`. **La mitad de "medición" de este ítem ya está implementada** (observabilidad del caché propio del CLI).
  - **Por qué cada sub-PR es inviable hoy:**
    - **PR2 (marcado `cache_control`):** requeriría que el stdin stream-json del CLI aceptara `cache_control` en el content-block del user message. La referencia oficial documenta `cache_control` **solo** como campo de la Messages API; **no existe contrato publicado del CLI para ello**. Agregarlo sería inventar un contrato.
    - **PR1 (reordenar/estabilizar byte el prompt de Stacky):** el contexto pesado que Stacky controla (épica, client-profile, directivas, memoria) viaja **dentro del user message** (lo arma `context_enrichment`), que es el sufijo, no el prefijo cacheable. Sin un breakpoint sobre ese bloque (= PR2, imposible), estabilizar bytes de un sufijo **no produce cache-hit verificable**: el criterio de aceptación "`cache_read_tokens` se puebla por el prefix estable" no lo puede satisfacer nada del lado de Stacky, solo el comportamiento propio del CLI (que ya ocurre, independiente del flag → flag sería no-op).
  - **El objetivo de negocio YA está cubierto sin este ítem:** el refine reanuda sesión (`--resume`, F2.3, :1361-1364) → el contexto pesado ya queda provider-side y el CLI lo cachea cross-run; el ahorro es medible vía `cache_read_tokens` (ya capturado).
  - **Precondición para retomarlo:** (a) Anthropic publica que el envelope `--input-format stream-json` del CLI acepta `cache_control` en el content-block y lo propaga a la request que construye; **o** (b) Stacky deja de pasar por el CLI en esta ruta y llama a la Messages API directo vía SDK (otro runtime, fuera del alcance de I2.2 y contra la arquitectura headless-CLI actual). Hasta entonces, estado honesto = DIFERIDO.

---

#### I2.3 Expansión y normalización de query para el retrieval (sin FTS5, sin deps)

- **Ataca:** D-I5. Sobre el TF-IDF existente; NO introduce FTS5 ni BM25 externo.
- **Resultado visible:** la memoria y los tickets similares relevantes se recuperan aunque el vocabulario difiera — el agente arranca mejor informado.
- **Diseño:**
  - Sobre `services/embeddings.py` y `services/memory_store.search`: agregar normalización más robusta en el tokenizer (`_tokenize:42`) — fold de acentos (á→a) consistente y colapso de variantes obvias — y **expansión de query** ligera: para el query de búsqueda (no para el corpus), agregar un puñado de sinónimos/variantes del dominio desde un diccionario chico y estático (p. ej. "factura"↔"facturación"↔"comprobante") mantenido en un módulo `services/query_expansion.py` (datos, no LLM). NO se toca el índice ni se agrega tabla.
  - Opcional (mismo flag): re-pesado tipo BM25-lite **calculado en Python** sobre el conjunto ya recuperado (saturación de term-frequency con `k1`/`b`), aplicado solo al ranking final — sin estructura nueva, es aritmética sobre los `tf`/`idf` que `embeddings` ya computa. Esto NO es FTS5 ni una dependencia: es cambiar la fórmula de score sobre los mismos datos.
  - Flag: `STACKY_RETRIEVAL_EXPANSION_ENABLED` (bool, default **false**). OFF → tokenizer y ranking idénticos a hoy (el tokenizer es compartido con muchos sitios — el flag debe envolver SOLO la ruta de búsqueda, no mutar `_tokenize` global; pasar un tokenizer/expansor explícito a `search`/`top_k` cuando el flag está ON, para no alterar el resto del sistema que comparte `_tokenize`).
  - **Cuidado de contrato:** `_tokenize` lo importa `memory_store` (`:55`) como tokenizer compartido. NO cambiar su firma ni su comportamiento por default; la expansión es una capa OPT-IN sobre el query, no una mutación del tokenizer base.
- **Por qué NO viola rule 11:** mejora qué contexto se recupera, no qué se hace con él; el run sigue siendo del operador; no decide nada por el humano.
- **Criterios de aceptación:** flag OFF → retrieval byte-idéntico (regresión sobre tests de `embeddings`/`memory_store`); query "factura" recupera una memoria que dice "facturación" con el flag ON; fold de acentos hace match "facturacion"↔"facturación"; el tokenizer global NO cambia su comportamiento por default (test que verifica que otros consumidores de `_tokenize` no se afectan); BM25-lite re-pondera sin tabla nueva.
- **Tests (TDD, `tests/test_query_expansion.py`):** expansión de query, fold de acentos, BM25-lite vs coseno, flag OFF idéntico, tokenizer base inmutable.
- **Complejidad:** M.

---

### FASE I3 — Diferenciales: confiabilidad invisible y afinado con datos

---

#### I3.1 Paralelización de los injectors independientes del briefing

- **Ataca:** D-I8 (cierre). Sobre `enrich_blocks`.
- **Resultado visible:** time-to-first-token más bajo — el ensamblado del briefing tarda menos porque las lecturas independientes corren en paralelo.
- **Diseño:**
  - Hoy `enrich_blocks` corre los injectors en serie (`context_enrichment.py:67-96`): memoria → client-profile → épica → artifacts → similares → ADO. Varios son **independientes** y dominados por I/O (similares y comentarios ADO pegan a la red; artifacts pega al filesystem). Este ítem paraleliza SOLO los injectors mutuamente independientes con un `ThreadPoolExecutor` acotado (stdlib, cero deps), preservando el **orden final** de los bloques (se paraleliza la obtención, no el orden de inserción) y el contrato de pureza/best-effort (cada injector ya es best-effort, `:470,506,605`).
  - Cuáles se paralelizan: los que NO dependen del resultado de otro. La memoria y el client-profile son rápidos/locales y van primero como hoy; similares + comentarios ADO + artifacts pueden lanzarse en paralelo. Verificar dependencias reales al implementar (p. ej. si algún injector lee un bloque que otro inyectó — hoy no parece, pero confirmarlo).
  - Determinismo: el orden de los bloques en la salida debe ser idéntico al serial (recolectar resultados y ensamblar en el orden canónico). Sin esto, el output cache y el prefix-cache (I2.2) se romperían.
  - Flag: `STACKY_PARALLEL_INJECTORS_ENABLED` (bool, default **false**). OFF → serial, byte-idéntico.
- **Por qué NO viola rule 11:** acelera el ensamblado del run que el operador lanzó; no cambia el contenido ni decide nada.
- **Criterios de aceptación:** flag OFF → serial idéntico; flag ON → mismo conjunto y MISMO orden de bloques que el serial (test que compara salida serial vs paralela byte a byte); una excepción en un injector paralelo no tumba el resto (best-effort preservado); medición de latencia muestra mejora con ADO lento (mock con sleep).
- **Tests (TDD, `tests/test_parallel_injectors.py`):** equivalencia serial vs paralelo (orden y contenido), aislamiento de fallos, flag OFF.
- **Complejidad:** M (riesgo de concurrencia — de ahí el test de equivalencia estricta).

---

#### I3.2 Caché de lecturas caras de ADO con invalidación

- **Ataca:** D-I6. El outbox de WRITE ya es robusto; esto cachea las LECTURAS.
- **Resultado visible:** menos latencia por run y menos carga sobre el PAT — refinar 3 veces el mismo ticket lee la épica de ADO una sola vez.
- **Diseño:**
  - Nuevo `services/ado_read_cache.py`: caché en memoria (proceso) con TTL e invalidación por evento, para las lecturas caras que hoy hace `_inject_ado_context` (`context_enrichment.py:575`) y `similar_tickets`/épica: `get_or_fetch(key, fetch_fn, ttl)`. Key por `(project, ado_id, kind)`. TTL configurable (`STACKY_ADO_READ_CACHE_TTL_SEC`, int, default 0 = **desactivado**, byte-idéntico).
  - Invalidación: cuando Stacky **escribe** en un ticket (comentario/transición vía `ado_write_outbox` al drenar con éxito) → invalidar las entradas de caché de ese `ado_id` (la estructura cambió). Esto evita servir datos viejos tras una publicación. Hook en el punto donde el outbox marca una operación `succeeded`.
  - Best-effort y conservador: ante cualquier duda, fetch fresco; la caché es una optimización, nunca una fuente de verdad. Una entrada vencida o ausente = comportamiento actual (leer de ADO).
  - Mono-operador: como hay un solo operador y un solo proceso backend, una caché en memoria es suficiente (no hace falta caché distribuida). Documentarlo.
- **Por qué NO viola rule 11:** cachear lecturas no decide nada ni cambia qué se publica; la invalidación tras escritura mantiene la coherencia; el operador no ve ni configura nada.
- **Criterios de aceptación:** TTL 0 (default) → sin caché, byte-idéntico (cada run lee de ADO); TTL > 0 → segunda lectura del mismo `ado_id` dentro del TTL no pega a ADO (mock cuenta llamadas); una escritura exitosa vía outbox invalida la caché de ese ticket (la lectura siguiente es fresca); entrada vencida → fetch fresco.
- **Tests (TDD, `tests/test_ado_read_cache.py`):** hit/miss por TTL, invalidación por escritura, TTL 0 no-op, fallo de fetch no corrompe caché.
- **Complejidad:** M.

---

#### I3.3 Caps de contexto adaptativos por telemetría (afinado, no decisión)

- **Ataca:** D-I7. Cuidado especial con rule 11.
- **Resultado visible:** el tamaño de contexto por agente se acerca al óptimo observado — ni de más (caro) ni de menos (peor calidad) — sin que nadie ajuste perillas.
- **Diseño:**
  - **Esto NO ajusta caps por su cuenta en producción.** Rule 11: el sistema NO decide el cap del operador. Lo que hace es **proponer** un cap sugerido por agente, derivado de la telemetría (`harness_telemetry`), que un humano revisa y aplica con un click (vía el panel de config de memoria del doc 26, M0.2). El loop es: telemetría → sugerencia → aprobación humana → aplica. Sin aprobación, nada cambia.
  - Nuevo `services/context_caps_advisor.py::suggest_caps(project, days=30) -> dict` — analiza, por agent_type, la relación entre tamaño de contexto inyectado (de `harness_telemetry` / `input_context`) y señales de calidad (contract_score, confidence, tasa de needs_review, costo). Heurística transparente: si los runs con más contexto NO mejoran calidad → sugerir bajar el cap; si los runs cortos tienen más needs_review → sugerir subir. Devuelve `{agent_type: {current_cap, suggested_cap, rationale, sample_size}}`. NUNCA aplica.
  - Endpoint `GET /api/metrics/caps-advisor?project=X&days=30` (read-only). La sugerencia aparece en el panel de config de memoria (doc 26 M0.2) como "sugerencia basada en N runs" con un botón "aplicar" que escribe `STACKY_MEMORY_CAPS_JSON` (doc 26 M0.1). El botón es del **operador/administrador**, no automático.
  - Flag: `STACKY_CAPS_ADVISOR_ENABLED` (bool, default **false**) — OFF → endpoint 404, cero sugerencias.
  - **Frontera con "invisible":** este es el ítem MENOS invisible del plan (tiene una sugerencia que el humano ve y aplica). Se incluye igual porque el TRABAJO (analizar telemetría, calcular el óptimo) es invisible y el operador no lo hace; solo aprueba un número. Si se quiere mantener 100% invisible, queda como ítem opcional/diferido — declarado.
- **Por qué NO viola rule 11:** la máquina PROPONE un cap; el humano lo aprueba y aplica; nada se auto-ajusta. Es el mismo patrón que el flywheel C2.2 (doc 24): aprendizaje que produce propuestas, nunca mutaciones automáticas.
- **Criterios de aceptación:** con telemetría sintética donde más contexto no mejora score → sugiere bajar; donde runs cortos fallan más → sugiere subir; `suggest_caps` NUNCA escribe (test explícito); aplicar la sugerencia escribe `STACKY_MEMORY_CAPS_JSON` solo por click humano; flag OFF → endpoint 404; muestra `sample_size` (no sugiere con N chico).
- **Tests (TDD, `tests/test_caps_advisor.py`):** sugerencia up/down por telemetría, no-escritura, sample mínimo, flag OFF.
- **Complejidad:** M.
- **Dependencias:** doc 26 M0.1 (caps por flag) y M0.2 (panel) para el "aplicar"; degradado: la sugerencia se expone read-only y se aplica a mano editando el flag.

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | I0.1 Dedup léxico entre bloques | M | Alto (tokens ↓) | Bajo (flag, default idéntico) | — |
| 2 | I0.2 Computar `fingerprint_complexity` | M | Alto (habilitador) | Bajo (puro, flag OFF) | — |
| 3 | I1.1 Auto-reparación intra-run | M/L | **Muy alto (menos needs_review triviales)** | Medio (toca cierre de runners → flag, extiende autocorrect) | autocorrect (en código) |
| 4 | I1.2 Routing por dificultad | M | **Muy alto (más barato/mejor)** | Bajo (dentro del clamp, override gana) | I0.2 dura |
| 5 | I2.3 Expansión/normalización de query | M | Alto (mejor retrieval) | Medio (tokenizer compartido — flag aislado) | — |
| 6 | I2.1 Re-ranking por relevancia | M | Alto (mejor uso del budget) | Bajo (extiende F2.4) | — |
| 7 | I3.2 Caché de lecturas ADO | M | Alto (latencia ↓) | Bajo (TTL 0 default) | — |
| 8 | I3.1 Paralelizar injectors | M | Medio/alto (TTFT ↓) | Medio (concurrencia — test de equivalencia) | — |
| 9 | I0.3 Pre-warming ADO | S/M | Medio (TTFT ↓) | Bajo | I3.2 dura |
| 10 | I2.2 Prompt-prefix cache (claude) — **DIFERIDO 2026-06-15** | L | Alto (costo/latencia ↓) | Medio (contrato del CLI) | **sin superficie controlable: el CLI gestiona el caché internamente; ver §I2.2** |
| 11 | I3.3 Caps adaptativos (sugerencia) | M | Medio/alto (afinado) | Bajo (solo propone) | doc 26 M0.1/M0.2 |

**Reglas de implementación (las 7 del doc 22 + las 3 de frontend del doc 23 aplican íntegras):** TDD; validar por archivo de test (suite contaminada); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves nuevas (las de este plan: `run_repair`, y el poblado de `cache_read_tokens` ya existente); default OFF/0 (retro-compat **byte-idéntica** — con todos los flags en default, el motor se comporta EXACTAMENTE como hoy, runtime por runtime); ADO solo vía `ado_write_outbox` (las escrituras no cambian; solo se cachean lecturas); **sin fallback silencioso entre runtimes** (I2.2 es solo-claude declarado; I1.1 no repara sin resume); sin deps npm/py nuevas (todo con stdlib + el TF-IDF existente); UI degrada con gracia.

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Cada ítem trae su línea "Por qué NO viola rule 11". Resumen de la doctrina: (a) las mejoras ocurren DENTRO de un run que el operador lanzó (I1.1, I1.2, I2.x, I3.1) o ajustan sustrato sin decidir (I0.1, I3.2); (b) nada se publica a ADO por su cuenta (el verdict humano y el path de publicación U1.3/U2.2 quedan intactos); (c) lo único que "aprende" (I3.3) produce una **sugerencia** que el humano aplica con un click, nunca una mutación automática — mismo patrón que el flywheel C2.2 del doc 24. Si un ítem se puede leer como "el sistema decidió/publicó/procesó solo", está mal implementado.

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (que NO configura ni ve estos mecanismos)
- **Hoy:** lanza un run; a veces sale vacío y tiene que relanzar a mano; refinar el mismo ticket vuelve a pagar todo el contexto; el modelo se elige por reglas gruesas; el briefing tarda en ensamblarse.
- **Después (sin tocar nada):** el mismo run que lanza sale más seguido a la primera (auto-reparación de glitches), arranca más rápido (pre-warming + injectors en paralelo), cuesta menos en los casos simples (routing por dificultad + dedup de tokens + prefix-cache) y llega mejor informado (retrieval expandido + rerank). No ve ninguna perilla nueva: solo nota que Stacky "anda mejor".

### Desarrollador / equipo (que vive en ADO)
- **Hoy:** recibe artefactos cuya calidad depende de cuánto del contexto relevante entró y de si el output no se rompió por un glitch.
- **Después:** recibe artefactos más consistentes (mejor contexto por el mismo budget) y menos huecos por fallos triviales (auto-reparación) — sin cambios en cómo Stacky escribe en ADO (las escrituras siguen pasando por el outbox idempotente, solo se aceleran las lecturas).

### Management
- **Hoy:** el costo por run es lo que es; no hay forma de bajarlo sin que alguien afine a mano.
- **Después:** costo por run más bajo y medible (routing por dificultad, dedup, prefix-cache con `cache_read_tokens` visible en el digest U1.5 / harness-health H8), menos tiempo de revisión humano (menos `needs_review` triviales), y un afinado de contexto basado en datos (caps advisor) — todo sin sumar trabajo operativo. El ahorro es invisible en el proceso y visible en la factura.

---

## 7. Ventaja competitiva: por qué el motor invisible gana

1. **El mismo operador rinde más sin aprender nada nuevo.** El doc 24 le dio palancas que el operador usa con criterio; este plan le da mejoras que NO tiene que entender ni activar. La curva de adopción es cero: las mejoras llegan por sign-off del administrador, no por capacitación del operador. Un CLI suelto exige que el humano optimice a mano (elegir modelo, recortar contexto, reintentar); acá el arnés lo hace solo, dentro de los límites que el humano fijó.
2. **Reusar lo ya pagado es estructuralmente más barato que rehacerlo.** El prefix-cache del proveedor, la caché de lecturas ADO y el reuso de contexto entre runs del mismo ticket convierten el trabajo repetido en casi-gratis. Un CLI suelto re-paga el contexto entero en cada invocación; Stacky lo amortiza. En un flujo de refine iterativo (doc 24 C1.1), ese ahorro se compone.
3. **Confiabilidad invisible: el glitch no llega al humano.** La auto-reparación intra-run salva los fallos triviales antes de que el operador los vea, sin cruzar la línea de la autonomía (no publica, no decide; solo completa el trabajo pedido, una vez, como haría el humano). El resultado es menos fricción percibida con cero pérdida de control — el centauro sigue firmando cada verdict, pero firma menos basura trivial.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo |
|---|---|---|
| Tokens de contexto por run (mismo output) | sin dedup ni rerank | reducción medible con dedup (I0.1) + rerank (I2.1), sin perder calidad |
| `needs_review` por output vacío/malformado trivial | caen a revisión humana | reparados dentro del run (I1.1) — reducción medible de needs_review triviales |
| Costo por run según dificultad | reglas gruesas por tokens | modelo a la medida de la dificultad (I1.2), simples más baratos |
| Costo de refinar el mismo ticket | re-paga el contexto entero | amortizado por prefix-cache (I2.2) + caché de lecturas ADO (I3.2); `cache_read_tokens` visible |
| Lecturas repetidas a ADO por ticket | una por run | una por TTL (I3.2) |
| Time-to-first-token | ensamblado serial post-launch | reducido por injectors en paralelo (I3.1) + pre-warming (I0.3) |
| Recall de memoria/similares relevantes con vocabulario distinto | mismatch léxico los pierde | expansión/normalización de query (I2.3) los recupera |
| Tamaño de contexto óptimo por agente | constante por intuición | sugerido por telemetría, aplicado por click humano (I3.3) |
| Perillas nuevas que el operador debe tocar | — | **cero** (todos los flags son internos, default OFF) |
