# TOP-5 (post-61) — El pozo sigue ~seco para EJES NUEVOS, pero el debate destapó un BRIDGE MUERTO

> Fecha: 2026-06-21 · Generado por la skill `debatir-top5-evolucion-stacky` (**CUARTA corrida**; debate adversarial Brainstormer ⇄ UltraEficientCode/Juez, ejecutado **inline** porque `SendMessage` no está disponible en este harness — sin continuación de subagentes entre rondas; mismo modo-fallback que las dos corridas previas, con disciplina de steelman y verificación firsthand del orquestador).
> Estado del arte al correr: plan formal de número más alto = **61**. Backlog 53/56/58/59/60/61 **IMPLEMENTADO** (memoria + commits 20f48001…701bf28f) → se cumplió el disparador que la 3ª corrida dejó escrito ("re-correr cuando el backlog esté implementado: ahí pueden abrirse ejes de 2º orden").
> Roadmap previo: [`TOP5_2026-06-20_POZO_SECO_POST60_IMPLEMENTAR_BACKLOG.md`](TOP5_2026-06-20_POZO_SECO_POST60_IMPLEMENTAR_BACKLOG.md) (debate #3, POZO SECO). Su única "idea en la burbuja" (gate del flujo funcional) se formalizó como **plan 61** (hardening, ya implementado) → dedup duro. Su cementerio se hereda.
>
> ## RESULTADO HONESTO: **0 finalistas NUEVOS cruzan el gate anti-incremental.** Pero la verificación firsthand destapó un **defecto concreto de alto valor**: el loop de PREVENCIÓN determinista (plan 60 → plan 56) está **roto en producción** — el puente edición-humana→golden es **código muerto**.
>
> El verdadero game-changer prometido por el debate #2/#3 (aprendizaje bidireccional que **previene**, no solo aconseja) **nunca llegó al gate determinista**: hoy las ediciones del operador en ADO alimentan SOLO la memoria blanda (prompt, dependiente del LLM, sin garantía). El salto NO es minar un 6º eje: es **CERRAR el loop que ya creímos cerrado**.

---

## El hallazgo (verificado firsthand — esto es lo que vale de esta corrida)

| Hecho | Evidencia firsthand (archivo:línea) |
|---|---|
| Plan 60 detecta la edición humana en ADO con `added_snippets` **y** `removed_snippets` (anti-patrón = lo que el humano BORRÓ) | `harness/ado_edit_diff.py:13-26` (EditDelta), `:52` diff_edit; `harness/ado_edit_detect.py` |
| Plan 60 materializa la edición SOLO como lección **blanda** en `memory_store` (prompt, type=operator_note) | `services/ado_edit_learning.py:136-148` |
| El puente edición→**golden determinista** es **CÓDIGO MUERTO**: llama a `epic_gate.register_positive_golden`, que **no existe en ningún módulo** | `services/ado_edit_learning.py:57,60,157` (solo `hasattr`); `grep register_positive_golden` ⇒ 0 definiciones |
| La maquinaria de golden del plan 56 SÍ existe y está VIVA y cableada al gate | `harness/regression_goldens.py:51 derive_negative_golden`, `:90 derive_positive_golden`, `:121 evaluate_regression`, `:178 save_golden`; gate en `harness/epic_gate.py:106-107`; carga en `api/tickets.py:6102` |
| …pero su ÚNICA fuente de goldens es la review **in-app** (`save_goldens_from_review`), que el flujo flagship **auto-publica-sin-review BYPASEA** | `api/executions.py:247-274`; `services/regression_capture.py:15-82`; memoria `human-in-the-loop-fundamental` (épica-desde-brief auto-publica) |
| El lado NEGATIVO (humano BORRÓ algo ⇒ bloquear su recurrencia) **no está cableado a ningún origen real**: `derive_negative_golden` existe pero nada lo alimenta con `removed_snippets` | `regression_goldens.py:51` definido; 0 callers no-test que pasen `removed_snippets` |
| Plan 60 **no está supervisado** (ledger: 51/52/54/55/57 APROBADO; 53/56/58/59/60/61 ausentes) ⇒ el bridge muerto no fue auditado | `docs/_supervision/ledger.json` |

**Conclusión:** el operador corrige a mano sus épicas EN ADO (donde realmente trabaja, porque el flujo auto-publica), y esa corrección —la señal más rica que tiene Stacky— **se evapora en memoria blanda**. No hay NINGUNA garantía determinista de que el mismo defecto no vuelva en la próxima épica. El gate de regresión (56) está vivo pero **hambriento**: su fuente in-app no recibe combustible del flujo flagship.

---

## Bitácora del debate (densa)

**Ronda 1 — generativa (Brainstormer, inline).** Portafolio sobre ejes de 2º ORDEN (lo que el backlog recién construido habilita), NO sobre ejes-épica ya agotados: (A) **loop de prevención determinista** — que la edición humana en ADO alimente el gate de regresión (no solo la memoria blanda), incluyendo el lado NEGATIVO (lo borrado = anti-patrón); (B) **gate de coherencia del ÁRBOL** brief→épicas→tasks (la molécula completa que 55+59 recién hicieron real); (C) **selector adaptativo que aprende de OUTCOMES** (gate-blocks/rechazos/ediciones), no solo de confidence de grounding; (D) convergencia (58) a nivel ÁRBOL; (E) speculative+adaptive combinados.

**Ronda 1 — poda + verificación firsthand (Juez).**
- (D) cae: los hijos se DERIVAN deterministamente de una épica que ya pasó convergencia (`tickets.py:6740 build_epic_children_plan`); loopearlos aporta poco (no se generan independientemente). Novedad ≤2.
- (E) cae: incremental (tuning de pre-warm). Novedad ≤2.
- (B) cae: la parte gate-able (cada RF de la épica → un hijo) ya está **por construcción** en 59 (los hijos se derivan de los headings RF); la parte valiosa (cada requisito del brief → alguna épica) exige matching semántico = **LLM-judge = PROHIBIDO**. Igual que "coherencia cross-WI" del debate #2 → cementerio.
- (C) cae (borderline): `adaptive_selector.py` usa SOLO confidence (grep: 0 refs a rejection/outcome/defect). Sumar feedback de outcomes es real pero (1) ≈ entrada de cementerio "telemetría→política (≈53/46)", (2) Novedad ~3 / Impacto ~3 (es optimización sobre un selector que ya existe), (3) riesgo de oscilación. I+N<8.
- **SOBREVIVE provisional:** (A) loop de prevención determinista — verificado firsthand que el bridge edición→golden es CÓDIGO MUERTO (`register_positive_golden` inexistente) y que el lado negativo nunca se cableó.

**Ronda 2 — réplica (steelman contra mi propia idea sobreviviente (A)).**
- *Steelman A FAVOR:* el flujo flagship auto-publica sin review in-app ⇒ la fuente de goldens del plan 56 (`save_goldens_from_review`) **no recibe combustible** en producción; la edición en ADO es la ÚNICA señal correctiva real, y hoy se pierde. Cerrar el loop convierte cada corrección manual del operador en una **barrera determinista permanente** (no LLM): la 2ª vez que el agente intente publicar el defecto que el humano ya borró, el gate **bloquea, garantizado**. Para un tool mono-operador cuyo norte es "amplificar al operador", hacer que sus correcciones cuenten PARA SIEMPRE es lo de máximo apalancamiento. Impacto 4-5. El lado NEGATIVO (lo borrado → anti-patrón) es **capacidad nueva** (hoy nada lo hace).
- *Steelman EN CONTRA (decisivo para el ranking):* el lado POSITIVO (edición→positive golden) es **plan 60 INCOMPLETO** (intentó `register_positive_golden`, símbolo que nunca existió, y quedó guardado tras un `hasattr`), NO un eje nuevo → corresponde a `supervisar-implementaciones-planes` (60 ni siquiera está en el ledger), no a un top-5. Y la maquinaria del lado negativo (`derive_negative_golden` + `save_golden` + `evaluate_regression`) **ya existe**: lo que falta es **plomería** entre dos sistemas vivos. Novedad de la parte genuinamente nueva (negative-from-deletion) ~3, no salto de capacidad. I+N ≈ 7-8: **en el filo, NO por encima limpio.**

**Ronda de cierre (estable).** El juez, pudiendo absolver a (A) como game-changer, argumenta que NO debe: su mitad positiva es **completar plan 60** (supervisión) y su mitad nueva (negative goldens) es una **extensión delgada de hardening** sobre maquinaria existente, no un antes/después de capacidad. Cruza el umbral de VALOR pero no el de NOVEDAD-de-salto. **0 finalistas nuevos cruzan el gate como game-changer.** Ranking estable (vacío de game-changers) vs R2. El juez mató/reformuló ≥1 idea en cada ronda. **CONVERGIÓ** — y, a diferencia del debate #3, dejó un **artefacto accionable concreto** (bridge muerto), no solo "implementen el backlog".

---

## La idea "en la burbuja" (para decisión del operador) — distinta y más fuerte que la del debate #3

**Cerrar el loop de PREVENCIÓN determinista (edición humana en ADO → golden ± → gate de regresión).** Se descompone en DOS piezas con dueño distinto:

1. **[Supervisión, NO top-5] Completar plan 60:** reemplazar la llamada muerta `epic_gate.register_positive_golden` por la maquinaria viva del plan 56. Lo natural: que `ado_edit_learning.learn_from_work_item` invoque `regression_capture` (o directamente `regression_goldens.derive_positive_golden` + `save_golden`) con `he.edited_html`. Es **arreglar código muerto en un plan no supervisado** → corresponde a `supervisar-implementaciones-planes` (que además auditaría 53/56/58/59/61).
2. **[Hardening con chispa de game-changer, opcional] Lado NEGATIVO nuevo:** cablear `delta.removed_snippets` → `derive_negative_golden` → `save_golden`, para que el gate **bloquee deterministamente la recurrencia de lo que el humano borró**. Esto NO está en el scope de ningún plan; es capacidad nueva pero delgada (Novedad ~3). Formalizable como un plan pequeño (proponer-plan-stacky) si el operador lo decide.

**Por qué NO entró al top-5:** la pieza 1 es supervisión (completar lo ya planificado), y la pieza 2, aunque nueva, es una extensión de hardening sobre maquinaria existente (Novedad de salto insuficiente). Forzarla al top-5 sería el relleno que esta skill existe para matar. PERO su VALOR de ingeniería es alto y barato (reusa 56 íntegro): es la recomendación #1 de abajo.

---

## Cementerio (no re-proponer)

| Idea | Motivo (verificado firsthand salvo "heredado") |
|------|--------|
| **Gate de coherencia del árbol brief→épicas→tasks (B)** | La parte gate-able (RF→hijo) ya es **por construcción** en 59 (`tickets.py:6740`); la parte valiosa (brief→épica) exige LLM-judge (PROHIBIDO). ≈ "coherencia cross-WI" del debate #2. |
| **Selector adaptativo que aprende de outcomes (C)** | `adaptive_selector.py` usa solo confidence; sumar outcomes ≈ cementerio "telemetría→política (≈53/46)"; Novedad ~3, optimización sobre selector existente, riesgo de oscilación. |
| **Convergencia a nivel árbol (D)** | Los hijos se derivan deterministamente de una épica ya convergida (`build_epic_children_plan`); loopearlos no agrega (Novedad ≤2). |
| **Speculative + adaptive combinados (E)** | Tuning de pre-warm; incremental (Novedad ≤2). |
| **Loop de prevención determinista como TOP-5** | Su mitad positiva = completar plan 60 (supervisión); su mitad nueva (negative goldens) = hardening delgado sobre maquinaria existente. Alto valor, baja novedad-de-salto. Va como recomendación, no como game-changer. |
| *(Heredado íntegro del debate #3)* few-shot positivo, coaching, gate del flujo funcional (=plan 61), loop de convergencia del Task, prevención stale-consumed, anticipar fase funcional, quórum/best-of-N, runner headless sin consumidor, LLM-as-judge horneado, grounding multi-cliente | Ver `TOP5_2026-06-20_POZO_SECO_POST60_IMPLEMENTAR_BACKLOG.md` §Cementerio. Todos siguen cerrados por la misma evidencia. |

---

## Dedup contra roadmaps previos

- Debate #2 (post-57) → finalistas formalizados como **58/59/60**, todos **implementados** → dedup duro.
- Debate #3 (post-60) → POZO SECO; su burbuja (gate funcional) = **plan 61**, implementado → dedup duro.
- Ningún finalista previo queda "vivo sin formalizar": todos cerraron como planes 58–61. El cementerio de #3 se hereda íntegro.

---

## Recomendación estratégica (handoff honesto)

1. **NO formalizar un game-changer nuevo** con `proponer-plan-stacky`: no hay un #1 que cruce el gate; forzarlo reintroduce el incrementalismo que esta skill mata.
2. **Correr `supervisar-implementaciones-planes`** sobre el backlog no auditado (53/56/58/59/60/61). Atrapará el **bridge muerto de plan 60** (`register_positive_golden` inexistente) y lo completará con la maquinaria viva del plan 56 — cerrando la mitad POSITIVA del loop de prevención. Este es el paso de máximo valor inmediato.
3. **Opcional, si el operador lo decide:** formalizar con `proponer-plan-stacky` un plan PEQUEÑO para la mitad NEGATIVA (lo que el humano borra → `derive_negative_golden` → `save_golden` → el gate bloquea recurrencia). Hardening con chispa, reusa 56 íntegro.
4. **Re-correr este debate** recién cuando el loop de prevención esté cerrado y supervisado: ahí el estado del arte vuelve a cambiar (un gate alimentado por correcciones reales puede habilitar ejes de 3er orden — p. ej. priorizar effort según densidad de goldens negativos por proceso).

---

## Resumen final (8 líneas)
1. Cuarta corrida (post-61). Backlog 53/56/58/59/60/61 implementado → se cumplió el disparador de re-correr que dejó el debate #3.
2. **Resultado honesto: 0 finalistas NUEVOS cruzan el gate anti-incremental** (B/C/D/E caen por by-construction / needs-LLM / incremental).
3. PERO la verificación firsthand destapó un **bridge MUERTO**: plan 60 alimenta solo memoria blanda; su puente edición→golden llama a `register_positive_golden`, símbolo **inexistente** (`ado_edit_learning.py:57,157`).
4. El gate de regresión (56) está vivo y cableado (`epic_gate.py:106`, `tickets.py:6102`) pero su única fuente (review in-app) la **bypasea el flujo auto-publish** → gate hambriento.
5. El lado NEGATIVO (lo que el humano BORRA = anti-patrón) tiene maquinaria (`derive_negative_golden`) pero **0 callers reales** → capacidad nueva sin cablear.
6. La burbuja (cerrar el loop de prevención) NO entra al top-5: mitad = completar plan 60 (supervisión), mitad = hardening delgado (Novedad ~3).
7. Plan 60 **no está supervisado** (ledger: solo 51/52/54/55/57 APROBADO) → la supervisión lo detectaría.
8. Premisas verificadas firsthand: `ado_edit_learning.py:57/136/157`, `ado_edit_diff.py:13-26`, `regression_goldens.py:51/90/121/178`, `epic_gate.py:106`, `executions.py:247`, `tickets.py:6102/6740`, `ledger.json`.

**Handoff:** correr **`supervisar-implementaciones-planes`** (audita 53/56/58/59/60/61 y cierra la mitad positiva del loop de prevención muerto). NO `proponer-plan-stacky` para un game-changer (no hay salto que cruce el gate); SÍ, opcionalmente, para la mitad negativa como hardening.
