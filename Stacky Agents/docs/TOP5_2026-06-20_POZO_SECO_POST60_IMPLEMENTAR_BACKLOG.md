# TOP-5 (post-60) — POZO SECO: 0 finalistas nuevos, el salto es IMPLEMENTAR el backlog

> Fecha: 2026-06-20 · Generado por la skill `debatir-top5-evolucion-stacky` (TERCERA corrida; debate adversarial Brainstormer ⇄ UltraEficientCode/Juez, ejecutado **inline** porque `SendMessage`/subagentes no estaban disponibles en este harness — mismo modo que la corrida previa, con disciplina de steelman y verificación firsthand del orquestador).
> Estado del arte al correr: plan formal de número más alto = **60**.
> Roadmap previo: [`TOP5_2026-06-20_POST57_LOOP_MOLECULA_BIDIRECCIONAL.md`](TOP5_2026-06-20_POST57_LOOP_MOLECULA_BIDIRECCIONAL.md) (debate #2). Sus 3 finalistas (bucle de calidad / molécula vertical / aprendizaje bidireccional) **ya se formalizaron como planes 58, 59, 60** (v2, juzgados, NO implementados) → entran como **dedup duro**, no se re-proponen.
>
> ## RESULTADO HONESTO: **0 finalistas nuevos que crucen el gate.** El pozo quedó **seco**.
> Tras 49–60 (gate determinista, grounding, convergencia, golden ±, preview, molécula horizontal+vertical, aprendizaje bidireccional, selector adaptativo) + few_shot/coaching ya vivos + 30/31/32 ya formalizados, **ningún eje nuevo alcanza (Impacto+Novedad) ≥ 8 con Novedad ≥ 3** sin (a) duplicar algo ya implementado/formalizado, (b) exigir LLM-judge horneado (PROHIBIDO), o (c) violar un riel duro. **La skill prohíbe rellenar para llegar a 5** y declara explícitamente que "<3 finalistas tras agotar las rondas es una SEÑAL, no un fracaso".
>
> **El verdadero game-changer ahora NO es minar un salto nuevo: es CONSTRUIR los 5 saltos ya formalizados y sin implementar (53, 56, 58, 59, 60).** Hay 5 planes endurecidos por el juez esperando `implementar-plan-stacky`. Minar un 6º eje incremental sería el incrementalismo que esta skill existe para matar.

---

## Por qué el pozo está seco (no es fatiga — es criterio + evidencia)

La conclusión sale del **gate anti-incremental + dedup + rieles**, verificada firsthand, NO de cansancio. Mapa de ejes y por qué cada uno está cerrado:

| Eje candidato | Estado | Evidencia firsthand |
|---|---|---|
| input→modelo adaptativo (confidence→model/effort) | **Formalizado (53)** | `top5-roadmap-debate` + doc 53 |
| rechazo→anti-patrón inyectado en prompt | **Implementado (54)** | ledger `54` APROBADO; `rejection_lessons.py`, `memory_prefix.py` |
| molécula horizontal (brief→N épicas) | **Implementado (55)** | ledger `55` APROBADO; `tickets.py:5835 build_epic_payload_preview` |
| gate golden ± (regresión) | **Formalizado (56)** | doc 56; `tickets.py:5461 _regression_gate_enabled` |
| especulación / latencia-cero | **Implementado (57)** parcial | ledger `57` APROBADO; `services/speculative.py` |
| loop de calidad determinista (gate→repair→re-gate) | **Formalizado (58)** | doc 58 v2 |
| molécula vertical (épica→hijos) | **Formalizado (59)** | doc 59 v2 |
| aprendizaje bidireccional desde ADO | **Formalizado (60)** | doc 60 v2; `ado_client.py:930 fetch_work_item_updates` |
| verificación ejecutable del entregable / contrato de aceptación | **Formalizado (30/31/32)** | `11-estado-planes.md`; flags G*/E*/A* OFF en `config.py` |
| **few-shot positivo desde outputs aprobados** | **Implementado y default ON** | `few_shot.py` (FA-12) + WIRING `agents/base.py:70-85`, `agent_runner.py:89/831`, `api/agents.py:483` |
| **coaching al operador desde su historial** | **Implementado** | `coaching.py` (FA-43), endpoint `GET /api/coaching/tips` |
| grounding multi-cliente | **Ya existe per-cliente** | `context_enrichment.py build_process_dictionary_block` (heredado) |
| LLM-as-judge horneado / cerebro interno mejor | **PROHIBIDO** | `llm_router.py:256` capa cerebro a sonnet-4-6, sin Anthropic directo (heredado) |
| runner headless side-effect-free standalone | **Cementerio: sin consumidor vivo** | `claude_code_cli_runner.py:119/146/1283/1430` side-effectful (heredado) |
| quórum / best-of-N (incluso juzgado por humano) | **Cementerio: rompe rieles** | 2–3× costo (degrada) + comparación humana (trabajo extra) (heredado, reconfirmado) |

---

## Bitácora del debate (densa)

**Ronda 1 — generativa (Brainstormer, inline).** El subagente `StackyArquitectoBrainstormer` se intentó spawnear UNA vez con la dedup completa (planes 53–60 + cementerio heredado), pero el harness devolvió límite de sesión (0 tokens, 0 tool_uses) → fallback de la skill: ambos roles inline. Portafolio honesto de ~6 candidatos sobre ejes NO-épica (el 53–60 es todo épica/brief-céntrico): (1) gate de calidad/grounding para el flujo FUNCIONAL (pending-task→Task), (2) loop de convergencia para el Task, (3) prevención-en-origen del stale-consumed, (4) anticipación de la fase funcional, (5) gate de coherencia del PORTAFOLIO cross-WI, (6) few-shot/coaching reforzado.

**Ronda 1 — poda + verificación firsthand (Juez).** Caen de entrada por premisa-ya-existe (firsthand): (6) **few-shot positivo YA existe y está cableado default-ON** (`few_shot.py` FA-12 + `base.py:70-85`) y **coaching YA existe** (`coaching.py` FA-43) → trampa "grounding-multicliente/speculative.py", al cementerio. (4) anticipar la fase funcional = especulación (57) sobre un paso nuevo + exige el runner headless sin consumidor (cementerio). (3) prevención stale-consumed = hardening (Novedad ≤ 2), además el caso ya está RESUELTO en el desatascador (`tickets.py:2477`). (5) coherencia cross-WI semántica exige LLM-judge (PROHIBIDO); la versión estructural (dedup de RF-id) es delgada. **SOBREVIVE provisional:** (1) gate del flujo funcional — verificado firsthand que `create_child_task` (`tickets.py:3534`) valida **solo schema + idempotencia**, sin ningún gate de calidad/grounding (todo el stack 49–60 es épica-only).

**Ronda 2 — réplica (steelman contra mi propia idea sobreviviente).** Steelman A FAVOR de (1): el Task es el contrato de trabajo REAL del desarrollador y es el artefacto MENOS protegido; "determinismo sobre el contrato del dev" sería un antes/después para ese flujo; reusa `harness/epic_gate.py` puro. Steelman EN CONTRA (decisivo): el dolor documentado del flujo funcional NO es de CALIDAD de contenido sino de MECÁNICA — `functional-task-not-created` = "mismatch ordinal vs ADO-id + JSON inválido, NO jerarquía", y `stale-consumed-trap`. Un gate de calidad de contenido **no atrapa** JSON-inválido ni ordinal-mismatch; esos ya están RESUELTOS (contrato solo-HTML + `_looks_like_epic` + desatascador). Con el Impacto real sobre el dolor documentado bajando a ~3, **(1) cae a I+N ≈ 6 < 8 → NO cruza el gate.** Reconfirmado: best-of-N juzgado-por-humano sigue muerto (2–3× costo degrada + comparación humana = trabajo extra).

**Ronda de cierre (estable).** El juez, pudiendo absolver a (1), argumenta que NO debe: bajo red-team honesto su Impacto sobre el dolor real es moderado y su Novedad es de paridad-port (≤3), no de salto. **Cero ideas cruzan el gate.** Ranking estable (vacío) vs R2. El juez mató/reformuló ≥1 idea en CADA ronda. **CONVERGIÓ con 0 finalistas nuevos** — resultado honesto, no relleno (la skill lo valida como señal).

---

## La idea "en la burbuja" (para decisión del operador)

La skill, cuando quedan <3 finalistas, pide **reportar las ideas en disputa y pedir decisión al operador** (es un trade-off de negocio real). Hay UNA:

**Blindaje del flujo FUNCIONAL (paridad con la protección del flujo épica).** Llevar un gate determinista PURO al contrato `pending-task.json`/Task (citar RF cubierta, plan-de-pruebas no vacío, `epic_id` = System.Id real y no etiqueta humana EP-26, slug válido, parent link correcto) que **advierta/bloquee antes de `create_child_task`** y avise al `FunctionalAgent` en generación. **NO es game-changer** (Novedad de paridad-port ~3, Impacto sobre el dolor documentado ~3, es hardening del último tramo de un issue ya resuelto), por eso NO entró al top-5. PERO es valor de ingeniería real y barato (reusa el patrón puro de `epic_gate.py`). Decisión del operador: ¿vale formalizarlo como plan de **hardening** (no top-5), o se descarta?

---

## Cementerio (no re-proponer)

| Idea | Motivo (verificado firsthand salvo "heredado") |
|------|--------|
| **Few-shot positivo desde outputs aprobados** | YA EXISTE y default-ON: `few_shot.py` FA-12 cableado en `agents/base.py:70-85`, `agent_runner.py:89/831`, `api/agents.py:483`. Trampa "ya existe". |
| **Coaching al operador** | YA EXISTE: `coaching.py` FA-43, `GET /api/coaching/tips`. |
| **Gate de calidad para el flujo funcional (Task)** | No es game-changer: el dolor documentado es de MECÁNICA (JSON/ordinal, ya resuelto), no de calidad → Impacto real ~3, Novedad paridad-port ~3, I+N<8. Sobrevive solo como hardening opcional (ver "burbuja"). |
| **Loop de convergencia para el Task** | Port de un port (58 aplicado al funcional); depende de un gate que no cruzó el gate; Novedad ≤2. |
| **Prevención stale-consumed en origen** | Hardening (Novedad ≤2); el caso ya está RESUELTO en el desatascador (`tickets.py:2477`). |
| **Anticipar la fase funcional (speculative)** | Especulación (≈57) sobre un paso nuevo + exige runner headless sin consumidor (cementerio heredado). |
| **Coherencia semántica cross-WI del portafolio** | La versión útil exige LLM-judge (PROHIBIDO); la estructural (dedup RF-id) es demasiado delgada para top-5. |
| **Quórum / best-of-N (incluso juzgado por humano)** | Rompe rieles: 2–3× costo (degrada) + comparación humana (trabajo extra). Heredado, reconfirmado. |
| **Runner headless side-effect-free standalone** | Plumbing sin consumidor vivo (especulación 57 = único consumidor, RECHAZADO). Heredado. |
| **LLM-as-judge horneado / cerebro interno mejor** | Cerebro capado a sonnet-4-6 sin Anthropic directo (`llm_router.py:256`). Heredado. |
| **Grounding multi-cliente / pre-mortem brief / telemetría→política / verificación ejecutable** | ≈ ya existe (`context_enrichment.py`) / ≈ plan 41 / ≈ 53/46 / ≈ 30/31/32. Heredado. |

---

## Dedup contra el roadmap previo (post-57 → planes 58/59/60)
Los 3 finalistas del debate #2 se FORMALIZARON como planes 58, 59, 60 (v2, juzgados, NO implementados) → contexto de dedup, NO se re-proponen. Ninguno se "retira al cementerio": están vivos y son el backlog a construir. El 57 sigue parcial (F2a runner headless diferido). El cementerio de #2 se hereda íntegro arriba.

---

## Recomendación estratégica (el handoff honesto)

1. **NO formalizar un plan nuevo** con `proponer-plan-stacky`: no hay un #1 que lo merezca; forzarlo reintroduce el incrementalismo que esta skill mata.
2. **Construir el backlog ya formalizado** con `implementar-plan-stacky`, en orden de dependencia: **58** (bucle de calidad, depende solo de 51 ✓) → **53** (selector adaptativo, habilitador) → **56** (golden ±, depende del corpus de 54 ✓) → **59** (épica→hijos, depende de 55 ✓) → **60** (bidireccional, depende de 54 ✓ + 56).
3. **Opcional, fuera del top-5:** si el operador lo decide, formalizar el blindaje del flujo funcional como plan de **hardening** (no game-changer).
4. **Re-correr este debate** recién cuando el backlog 53/56/58/59/60 esté IMPLEMENTADO: ahí el estado del arte cambia y pueden abrirse ejes nuevos (p. ej. loops de 2º orden sobre capacidades recién construidas).

---

## Resumen final (8 líneas)
1. Tercera corrida del debate (post-60). Los 3 finalistas del debate #2 ya son los planes 58/59/60 (formalizados, sin implementar) → dedup.
2. **Resultado honesto: 0 finalistas nuevos cruzan el gate.** El pozo está SECO tras 49–60 + few_shot/coaching vivos + 30/31/32 formalizados.
3. Verificado firsthand: few-shot positivo (`few_shot.py` cableado default-ON) y coaching (`coaching.py`) YA existen → matan los ejes "positivo/coaching".
4. La única idea sobreviviente provisional (gate del flujo funcional) cae en R2: el dolor documentado del flujo funcional es de MECÁNICA (ya resuelta), no de calidad → I+N<8.
5. El juez mató ≥1 idea por ronda; convergió en ronda de cierre estable con 0 finalistas (la skill valida <3 como señal, no relleno).
6. El game-changer real ahora es **implementar** los 5 planes ya formalizados (53/56/58/59/60), no minar un 6º eje incremental.
7. Idea en la burbuja para decisión del operador: blindar el flujo funcional como **hardening** (no top-5).
8. Premisas todas verificadas firsthand: `tickets.py:3534`, `few_shot.py`+`base.py:70-85`, `coaching.py`, gate épica-only `tickets.py:5450-5633`, ledger 51/52/54/55/57, docs 53/56/58/59/60.

**Handoff:** correr `implementar-plan-stacky` sobre el backlog (empezar por **58**). NO `proponer-plan-stacky` (no hay salto nuevo que formalizar).
