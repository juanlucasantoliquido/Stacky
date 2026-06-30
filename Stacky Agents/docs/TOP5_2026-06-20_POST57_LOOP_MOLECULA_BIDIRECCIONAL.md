# TOP-5 (post-57) — Bucle de calidad, molécula vertical y aprendizaje bidireccional

> Fecha: 2026-06-20 · Generado por la skill `debatir-top5-evolucion-stacky` (debate adversarial Brainstormer ⇄ UltraEficientCode/Juez).
> Estado del arte al correr: plan formal de número más alto = **57**. Los planes **53–57 ya fueron formalizados HOY por el debate previo pero NO están implementados** → entran como dedup, no se re-proponen.
> Roadmap previo: no existía `_roadmap/TOP5_*.md` (esta es la primera materialización; el debate previo vive solo en la memoria `top5-roadmap-debate`). Sus finalistas 53–57 se tratan como dedup explícito (abajo).
>
> **RESULTADO HONESTO: 3 finalistas, NO 5.** El pozo de saltos quedó parcialmente seco tras 53–57 (minteados el mismo día sobre los ejes input→modelo, rechazo→prompt, preview/portafolio, gate golden, especulación). "Menos pero todas game-changer" por diseño de la skill: no se rellenó para llegar a 5. Cada finalista ocupa un eje que 53–57 NO tocan.

---

## TOP-3 rankeado (orden de implementación = dependencias primero)

### #1 — Bucle de convergencia de calidad determinista (generate→gate→repair→re-gate)
- **Tesis del salto:** ANTES: el entregable se genera de UN tiro; el "pase correctivo" de aceptación es **un único intento** que re-chequea una vez y se detiene (`services/acceptance_gate.py:149` "Intenta un ÚNICO pase correctivo", cap `STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES` default **1** en `config.py:403-404`, y además detrás del plan 32 PROPUESTO/OFF). → DESPUÉS: un **bucle determinista acotado** que evalúa el output con el gate ya implementado, dispara un pase correctivo dirigido al fallo, **re-evalúa** y repite hasta PASS o agotar presupuesto (>1). Single-shot → iterativo-convergente.
- **Eje de novedad:** single-shot→iterativo. NO es tuning (no es subir el cap 1→N): hoy **no existe** un lazo que re-evalúe contra el `epic_gate` verdict; `attempt_acceptance_repair` re-corre una vez y para, y `cli_autocorrect.py`/`codex_autocorrect.py` (sí son `while`-loops reales, `codex_autocorrect.py:85`) sólo iteran sobre **errores de EJECUCIÓN** (`report.ok`), no sobre la **calidad del entregable** contra un gate.
- **Evidencia ancla (verificada firsthand):** `services/acceptance_gate.py:140-194` (pase único + re-check una vez); `config.py:403-404` (cap default 1); `harness/epic_gate.py:72 evaluate_epic_gate(...)` (veredicto PURO PASS/REPAIR/NEEDS_REVIEW, plan 51 IMPLEMENTADO) = punto de re-evaluación a reusar; `services/cli_autocorrect.py:153` / `codex_autocorrect.py:85` (loops de EJECUCIÓN, no de calidad).
- **Score:** Impacto 4 · Novedad 4 · Factibilidad 4 · Evidencia 5 → **gate (I+N)=8 ✓**.
- **Riel-check:** Paridad 3 runtimes con fallback → el repair usa `send_fn`/resume (`CAPABILITIES[runtime].supports_resume`, ya chequeado en `acceptance_gate.py:166-168`); runtime sin resume ⇒ degrada a pase único (graceful). · Cero trabajo extra: automático, default **OFF**. · Human-in-the-loop: el lazo produce un CANDIDATO; el operador sigue aprobando/rechazando — no auto-publica nada nuevo. · Mono-operador: sin auth. · No degradar: flag OFF = byte-idéntico; presupuesto acota costo.
- **Depende de:** plan 51 (`epic_gate.py`, IMPLEMENTADO). Sin dependencia de 53–57.
- **Siguiente paso:** `proponer-plan-stacky`.

### #2 — Descomposición vertical épica→hijos (1 Epic → Features/Tasks)
- **Tesis del salto:** ANTES: brief→épica auto-publica **un solo work item Epic** (`api/tickets.py:5919 autopublish_epic_from_run` publica un WI; el confidence/HTML no genera jerarquía). → DESPUÉS: una épica aprobada se **descompone determinísticamente en su jerarquía de hijos** (Features/Tasks) en ADO, con preview previo. Átomo → molécula **vertical** (complementa, no duplica, el 55 que es molécula **horizontal**: brief→N épicas hermanas).
- **Eje de novedad:** átomo→molécula vertical. NO incremental: hoy la jerarquía hija sólo se crea en el flujo funcional pending-task (`api/tickets.py:37` constantes `create_child_task`, endpoint separado), nunca desde el flujo brief→épica.
- **Evidencia ancla (verificada firsthand):** `api/tickets.py:5919 autopublish_epic_from_run(... already_published_id ...)` publica el Epic padre solamente; `api/tickets.py:37-57` maquinaria `create_child_task` + relaciones parent/child existentes (`parent_ado_id`, líneas 2047-2055) = infra a reusar; `api/tickets.py:5823`/`55_PLAN_*` preview (`build_epic_payload_preview`) = patrón de preview a reusar.
- **Score:** Impacto 5 · Novedad 4 · Factibilidad 4 · Evidencia 4 → **gate (I+N)=9 ✓**.
- **Riel-check:** Paridad → la descomposición es parse PURO del HTML de la épica (igual en los 3 runtimes); la publicación de hijos reusa el camino autopublish claude-CLI-only (misma degradación documentada que 55). · Cero trabajo extra: opt-in, default **OFF**; el operador ve el preview de la jerarquía antes de crear nada. · Human-in-the-loop: REFUERZA — el operador aprueba la jerarquía propuesta antes de tocar ADO. · No degradar: solo-lectura hasta confirmar.
- **Depende de:** plan 55 (preview ejecutable, top-5 previo, NO implementado) → orden después de 55.
- **Siguiente paso:** `proponer-plan-stacky`.

### #3 — Aprendizaje bidireccional: las ediciones del operador en ADO vuelven como lección/golden
- **Tesis del salto:** ANTES: la publicación es **fire-and-forget**; cuando el operador corrige la épica a mano EN ADO, ese delta —la señal de entrenamiento más rica que existe, la versión REAL corregida por el humano— se pierde. → DESPUÉS: Stacky **lee de vuelta** las revisiones del work item, **diffea** lo publicado vs. lo que el operador dejó, y materializa ese diff como **lección determinista** (alimenta el corpus de 54) y/o **golden positivo** (56). Write-only → bidireccional; observar→APRENDER cerrado contra ground-truth real.
- **Eje de novedad:** ciego post-publicación → aprende de la corrección humana real. NO incremental: distinto de 54 (nota de rechazo dentro de Stacky) y de 56 (golden de aprobar/rechazar) porque la señal es **la versión editada por el humano en ADO**, no una nota.
- **Evidencia ancla (verificada firsthand):** `services/ado_client.py:930 fetch_work_item_updates(ado_id, top=50)` **EXISTE pero es CÓDIGO MUERTO — cero callers** en todo el backend (grep: solo su definición + su propia línea de log). `get_work_item` (`ado_client.py:836`) solo lo usa `ado_sync.py:248` (sync de estado), nunca para aprender ediciones. La infra de read-back de revisiones está sentada sin usar.
- **Score:** Impacto 4 · Novedad 4 · Factibilidad 4 · Evidencia 5 → **gate (I+N)=8 ✓**.
- **Riel-check:** Paridad → read-back vía ADO API (runtime-agnóstico) + diff PURO de texto. · Cero trabajo extra: el operador edita en ADO como ya lo haría; Stacky lee pasivamente. · Human-in-the-loop: APRENDE de lo que el humano hizo, nunca actúa solo. · No degradar: solo-lectura sobre ADO; default **OFF**. · Reuso: `fetch_work_item_updates` (dead code) + corpus de 54 + golden de 56.
- **Depende de:** plan 54 (rejection_lessons corpus) + plan 56 (golden gate) — ambos top-5 previo, NO implementados.
- **Siguiente paso:** `proponer-plan-stacky`.

---

## Bitácora del debate (densa)

**Ronda 1 — generativa (subagente `StackyArquitectoBrainstormer`, spawn único).** Portafolio de 7 ideas (honesto sobre pozo seco). 3 genuinas: Quórum de Runtimes, Descomposición Épica→hijos, Bucle Convergente; relleno: Pre-mortem del Brief, Telemetría→Política. Premisa decisiva que dejó marcada para verificar: ¿`STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES` (config.py:403) es un bucle o un cap a 1?

**Ronda 1 — poda + verificación firsthand (orquestador como UltraEficientCode/Juez; SendMessage no disponible en este harness → réplica inline con disciplina de steelman).** Verificadas las premisas en código real:
- Bucle Convergente: cap=1 + "pase ÚNICO" (acceptance_gate.py:149) + gate detrás de plan 32 OFF; loops existentes (cli_autocorrect) son de ejecución, no de calidad ⇒ **SOBREVIVE como #1** (no es tuning; es lazo de calidad inexistente).
- Descomposición épica→hijos: autopublish publica un solo Epic; `create_child_task` existe para otro flujo ⇒ **SOBREVIVE como #2** (reuso fuerte, distinto de 55).
- **MUERTOS R1:** Quórum de Runtimes (3× costo + merge de N épicas HTML exige LLM-judge PROHIBIDO o comparación humana = trabajo extra). Pre-mortem del Brief (solapa plan 41 preflight). Telemetría→Política (53 ya cierra el lazo accionable; resto = dashboard 46 o autonomía riesgosa).

**Ronda 2 — réplica inline (steelman) + búsqueda de un 3º genuino.** Defendí Quórum reformulado como **best-of-N determinista** (N muestras, elegir por score de `epic_gate`, sin LLM-judge) → **MUERTO**: redundante en costo con #1 (el bucle de repair puede incluir branch de regeneración y logra el mismo objetivo más barato); su prerequisito **runner headless side-effect-free NO existe** (verificado firsthand: `start_claude_code_cli_run` crea AgentExecution `claude_code_cli_runner.py:119`, dispara `ticket_status.on_execution_start:146` y `_maybe_autopublish_epic:1283/1430`), y el runner headless solo es plumbing (I+N=7<8) sin consumidor vivo (especulación 57 = RECHAZADO). Propuse y **VERIFIQUÉ** un 3º genuino: aprendizaje desde ediciones del operador en ADO — `fetch_work_item_updates` (ado_client.py:930) es **dead code** ⇒ **ENTRA como #3**.

**Ronda de cierre (estable).** El juez, pudiendo matar, argumenta que NO debe: los 3 sobrevivientes ocupan ejes ortogonales (iterativo-calidad / molécula-vertical / aprendizaje-bidireccional), ninguno redundante, ninguno rompe rieles, todos con premisa verificada firsthand. Ranking estable vs. R2. **CONVERGIÓ con 3** (techo es 5; 3 es resultado honesto, no relleno).

---

## Cementerio (no re-proponer)

| Idea | Motivo |
|------|--------|
| **Quórum de runtimes (consenso/voting cross-runtime)** | Rompe riel: 3× costo (degrada) + merge determinista de N épicas HTML imposible sin LLM-judge (PROHIBIDO) o comparación humana (trabajo extra). |
| **Best-of-N determinista** | Redundante-en-costo con #1 (el bucle de repair subsume el beneficio con branch de regeneración, a menor costo default). |
| **Runner headless side-effect-free (standalone)** | Plumbing: Impacto+Novedad=7 < 8. Su único consumidor vivo (especulación, plan 57) está RECHAZADO; sin consumidor sobreviviente. Verificado: no existe (claude_code_cli_runner.py:119/146/1283/1430 todo side-effectful). |
| **Pre-mortem del brief** | Solapa plan 41 (preflight de intención y plan negociable). Dedup. |
| **Telemetría→política (auto-ajuste de defaults por agregados)** | Plan 53 ya cierra el lazo accionable (confidence→modelo/effort); el agregado o es dashboard (plan 46) o es autonomía proactiva riesgosa. Incremental. |
| **Verificación ejecutable del entregable** | YA tiene planes formales 30/31/32 (PROPUESTOS, flags declarados OFF). Re-proponer = duplicar NN_ existente; implementarlos es trabajo, no nuevo top-5. Dedup. |
| **Grounding multi-cliente** | YA existe per-cliente (`context_enrichment.py build_process_dictionary_block`); lo Pacífico-céntrico son DATOS. (Heredado del debate previo.) |
| **LLM-as-judge horneado / cerebro interno mejor** | MUERTO: cerebro interno capado a sonnet-4-6 sin Anthropic directo (`llm_router.py`). Inviable sin código de proveedor nuevo. (Heredado.) |

## Dedup contra el top-5 previo (53–57)
Todos FORMALIZADOS (NO implementados) → contexto de dedup, no se re-proponen. Ninguno de los 3 finalistas los duplica: **#1** es lazo de calidad sobre el gate 51 (53–57 no iteran calidad); **#2** es molécula vertical (55 es horizontal); **#3** es aprendizaje desde ADO real (54 aprende de notas, 56 de aprobar/rechazar, ninguno lee la edición humana en ADO). **#2 depende de 55; #3 depende de 54+56** → estos tres se implementan DESPUÉS de su prerequisito del top-5 previo. **57 sigue RECHAZADO**; su prerequisito (runner headless) quedó en el cementerio por falta de consumidor vivo.

---

## Resumen final (8 líneas)
1. Tras 53–57 (minteados hoy), el pozo quedó parcialmente seco: el resultado HONESTO es **3 game-changers, no 5** (la skill prohíbe rellenar).
2. **#1 Bucle de convergencia de calidad:** generate→`epic_gate`→repair→re-gate hasta PASS/presupuesto; hoy el repair es un pase ÚNICO (cap 1, plan 32 OFF). Single-shot→iterativo. Depende solo de 51 (hecho).
3. **#2 Descomposición vertical épica→hijos:** 1 Epic→Features/Tasks con preview; reusa `create_child_task`. Átomo→molécula vertical (complementa 55 horizontal). Depende de 55.
4. **#3 Aprendizaje bidireccional ADO:** lee las ediciones del operador en ADO (`fetch_work_item_updates`, hoy dead code) y las vuelve lección/golden. Write-only→bidireccional. Depende de 54+56.
5. Cementerio clave: quórum/best-of-N/runner-headless (costo + sin consumidor vivo), pre-mortem (≈41), telemetría→política (≈53/46), verificación ejecutable (≈30/31/32).
6. Premisas TODAS verificadas firsthand (config.py:403, acceptance_gate.py:149, claude_code_cli_runner.py:119/146/1283/1430, tickets.py:5919/37, ado_client.py:930 dead code).
7. Rieles respetados por los 3: paridad-3 con fallback, cero trabajo extra (default OFF), human-in-the-loop, mono-operador, no degradar, reuso obligatorio.
8. Convergió en ronda de cierre estable: 3 ejes ortogonales, ranking estable, el juez pudiendo matar argumenta que no debe.

**Handoff:** para formalizar el **#1 (Bucle de convergencia de calidad)**, corré `proponer-plan-stacky`.
