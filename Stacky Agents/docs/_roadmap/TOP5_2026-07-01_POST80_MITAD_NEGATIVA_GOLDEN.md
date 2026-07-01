# TOP-5 (post-80) — 1 finalista cruza el gate: la MITAD NEGATIVA del loop de prevención (lo que el operador BORRA → golden negativo → el gate bloquea su recurrencia)

> Fecha: 2026-07-01 · Generado por la skill `debatir-top5-evolucion-stacky` (**QUINTA corrida**).
> Modo: Ronda 1 generativa con subagente REAL `StackyArquitectoBrainstormer` (10 ideas); poda/réplica/cierre
> ejecutadas inline por el orquestador (persona `StackyArchitectaUltraEficientCode` = juez), con verificación
> firsthand de TODAS las citas en disputa por el orquestador (anti-colusión).
> Estado del arte al correr: plan formal de número más alto = **80**. Implementados desde el debate #4:
> 62/63/64/65/66/67/68/69/70/71/72/**73**/74/**77**/78/79. Backlog en papel REAL: **75** (deep links GitLab,
> APROBADO-CON-CAMBIOS) y **80** (wiring codebase-memory-mcp, v3). 76 implementado (commit `233adbd5`).
> Roadmap previo: [`../TOP5_2026-06-21_POST61_LOOP_PREVENCION_MUERTO.md`](../TOP5_2026-06-21_POST61_LOOP_PREVENCION_MUERTO.md)
> (debate #4: 0 finalistas; burbuja = cerrar el loop de prevención en dos mitades).
>
> ## RESULTADO: **1 finalista cruza el gate anti-incremental** (menos que el techo de 5 — resultado honesto,
> ## no se rellenó). El resto del pozo sigue ~seco para game-changers. El finalista es la promoción de la
> ## "burbuja" del debate #4: su mitad bloqueante (bridge positivo muerto) ya se resolvió, y la mitad NEGATIVA
> ## quedó como la ÚNICA capacidad nueva, barata y determinista que marca un antes/después.

---

## Correcciones de estado descubiertas en esta corrida (dedup — verificadas firsthand)

| Creencia previa (briefing/memoria) | Realidad verificada |
|---|---|
| "Plan 73 en papel (v2 RECHAZADO)" | **IMPLEMENTADO** — commit `e4a2b406` ("feat(plan-73): generador declarativo PipelineSpec->ADO/GitLab — F0..F6"); `services/pipeline_renderers.py` existe |
| "Plan 77 en papel (v2 RECHAZADO)" | **IMPLEMENTADO** — commit `43f28baf` ("feat(plan-77): issue fases comentarios + color — F0..F6"); `publish_issue_phase_from_run` cableado en los 3 runners |
| "`derive_negative_golden` tiene 0 callers" (memoria del debate #4) | **STALE**: tiene UN caller productivo — `services/regression_capture.py:30,43` ← `api/executions.py:247-274` (veredicto humano in-app `rejected`). El hueco REAL es más fino (ver finalista) |
| "Mitad positiva del plan 60 muerta" | **CERRADA y VIVA**: `services/ado_edit_learning.py:169-170` usa `derive_positive_golden` + `save_golden` (API viva del plan 56); sweep automático cableado en `app.py:410-417` |

---

## El finalista (único que cruza el gate)

### #1 — "El golden que nace del tache": removed_snippets → golden negativo → gate bloquea recurrencia

**Tesis del salto.** ANTES: lo que el operador BORRA a mano en ADO se convierte solo en una lección de texto
blanda (`ado_edit_learning.edit_to_lesson_content`, `services/ado_edit_learning.py:49-53`: "Evitá: …") que el
LLM del próximo run PUEDE ignorar — la recurrencia del defecto depende del azar. DESPUÉS: cada frase borrada se
convierte en un **golden negativo determinista** (`absent_substring`) que `evaluate_epic_gate` aplica en el
próximo autopublish/publish: si el defecto reaparece, el gate **bloquea, garantizado**. Cierra la última arista
del loop observar→actuar→aprender→**PREVENIR** que los debates #2/#3/#4 persiguieron.

**Evidencia ancla (verificada firsthand por el orquestador, 2026-07-01):**
- `harness/ado_edit_diff.py:20` — `EditDelta.removed_snippets` ya captura lo que el humano borró.
- `services/ado_edit_learning.py:49-53` — hoy `removed_snippets` muere en la lección blanda; `:155-180`
  deriva SOLO el golden positivo (mitad negativa ausente).
- `harness/regression_goldens.py:51-77` — `derive_negative_golden` (PURA, `absent_substring`) existe y su único
  caller es `services/regression_capture.py:43` (nota de rechazo in-app, flujo minoritario porque el flagship
  auto-publica). Los snippets borrados son frases EXACTAS → encaje perfecto con `absent_substring`.
- Gate vivo y cableado donde importa: `harness/epic_gate.py:73` + autopublish `services/claude_code_cli_runner.py:950-1011`
  + publish in-app `api/tickets.py:6498-6542` (`epic_gate_blocked`).
- Sweep automático ya operativo: `app.py:410-417` (`sweep_recent_runs`).

**Score (rúbrica):** Impacto **4** (cada corrección manual del operador se vuelve barrera permanente en el flujo
flagship, donde la edición en ADO es la señal humana PRIMARIA) · Novedad **4** (azar→determinismo sobre señal hoy
desperdiciada; clase nueva de fuente de goldens; a diferencia del debate #4, ya NO incluye "completar plan 60" —
esa mitad está cerrada — queda solo capacidad nueva) · Factibilidad **5** (toda la maquinaria viva; es cablear
dos sistemas existentes + guards) · Evidencia **5** (todo archivo:línea firsthand). Gate: (4+4)≥8 ✓, F≥3 ✓, E≥3 ✓.

**Cambios exigidos por el juez (ENTRA-CON-CAMBIOS):**
1. Guard determinista de calidad de snippet: longitud mínima normalizada + cap de N goldens por edición
   (un borrado de "el" no puede envenenar el catálogo; `derive_negative_golden` hoy solo filtra vacío).
2. Flag nueva editable por UI, default OFF (`FlagSpec` SIN `default=` explícito — gotcha `_CURATED_DEFAULTS_ON`),
   `env_only=False`, en categoría existente. La flag del plan 60 es env-only: NO reusarla como toggle de esto.
3. Respetar el modo warning-no-bloqueante default del gate de regresión (el límite documentado de
   `regression_goldens.py:63-64` aplica igual).
4. Fuera de scope explícito: paridad GitLab del edit-learning (`ado_edit_learning` es ADO-coupled, allowlisted en
   `test_no_adoclient_outside_ado_provider.py:22`; Pacífico opera en ADO hoy). Anotar como seguimiento.

**Riel-check:** 3 runtimes ✓ (el sweep y el gate son backend-side, agnósticos del runtime que generó el run);
cero trabajo operador ✓ (la señal ES su trabajo actual: borrar en ADO); human-in-the-loop ✓ (máximo: la fuente es
la corrección humana literal); mono-operador ✓; no degrada ✓ (reusa 56+60 íntegros, flag OFF).

**Siguiente paso:** `proponer-plan-stacky` → plan **81**.

---

## Bitácora del debate (densa)

**R1 — generativa (subagente `StackyArquitectoBrainstormer`, real).** Portafolio de 10 ideas:
(1) golden-del-tache; (2) pipeline-que-vota (CI rojo → goldens sospechosos) [ROMPE-MARCO]; (3) veredicto
sintético en auto-publish → `save_goldens_from_review`; (4) auditoría cruzada dual-tracker post-migración;
(5) estados-79 como telemetría de flujo → sugerencias a process_discipline; (6) pre-mortem brief-reverso
pre-autopublish [ROMPE-MARCO]; (7) cuarentena de goldens sospechosos; (8) UI anticipatoria de rejection_lessons
al escribir el brief; (9) replay determinista del historial contra el gate de hoy [autodeclarado Incremental];
(10) propagar corrección a tasks hermanas. El propio Brainstormer detectó y corrigió la creencia stale
"0 callers" del debate #4. Recomendó dupla #1+#3 con #2 de respaldo.

**R2 — poda + verificación (juez inline; citas verificadas firsthand por el orquestador).**
- #3 MUERE por riel: un veredicto sintético "pasó-el-gate ⇒ approved" alimentando `save_goldens_from_review`
  rompe el contrato golden=humano-validado y crea un ratchet autorreferencial (el gate protegería estructuras que
  solo el propio gate sancionó). El canal honesto post-autopublish YA existe: ediciones ADO → positivo (vivo).
- #4 MUERE: tooling de verificación one-shot sobre plan 74; solapa conceptual con F-SHADOW (plan 70, diferida). I2.
- #5 MUERE: telemetría→política ≈ entradas de cementerio heredadas; requiere persistencia nueva de transiciones;
  I3+N3=6.
- #6 MUERE: el comparador es determinista pero la SEÑAL la produce otro pase LLM (validador estocástico
  encubierto, pariente del LLM-as-judge prohibido) y duplica costo/latencia del único flujo auto. I3+N4=7 y
  riel "no degradar" en duda.
- #7 MUERE: prematuro — catálogo de goldens joven, rechazos in-app escasos (el flagship no pasa por review),
  "contenido similar" exige matching semántico ruidoso. I2.
- #8 MUERE: superficie UI sobre datos existentes (54+patrón observatorio 44); I3+N3=6.
- #9 MUERE por regla dura: Novedad ≤2 ⇒ afuera (el propio Brainstormer lo marcó Incremental). Se anota como
  herramienta de calibración recomendable FUERA del top-5 (banco de falsos-positivos proyectados antes de subir
  severidad de gates).
- #10 MUERE: la aplicación cross-hermanas exige transformación semántica (LLM) o string-ops frágiles; ventana de
  simultaneidad dudosa; la lección de memoria ya cubre a la generación siguiente. F2.
- SOBREVIVEN provisionales: #1 y #2.

**R3 — réplica (steelman).**
- #2 steelman A FAVOR: primera señal de REALIDAD ejecutable (no humana, no estática); plan 71/72/73 ya
  implementados dan la maquinaria; capturar ahora = el loop aprende cuando GitLab-MAIN madure. EN CONTRA
  (decisivo): la atribución causal es INDETERMINISTA — un pipeline rojo corre sobre commits que Stacky no
  controla (los agentes escriben en la máquina del operador; el push es manual); fallo CI ≠ defecto del run
  (flaky/infra/commits ajenos); "marcar goldens como sospechosos" con señal ruidosa contamina un mecanismo
  determinista con azar — exactamente lo que Stacky vino matando en 58/61/79. I3+N4=7 ⇒ NO cruza. A la burbuja:
  re-evaluar cuando exista atribución determinista (p.ej. pipelines generados por 73 corriendo en ramas creadas
  por el propio flujo, con SHA trazable a un run).
- #1 steelman EN CONTRA: "es la misma idea que el debate #4 puntuó N=3, al filo". Réplica del juez: aquel score
  promediaba DOS mitades (completar plan 60 = supervisión + mitad negativa = capacidad); la mitad-supervisión se
  cerró el 2026-06-21, de modo que lo que queda es 100% capacidad nueva; y el sweep automático hoy vivo
  (`app.py:410`) le da un canal de producción que entonces no existía. Reformulada con guards (min-length, cap,
  flag UI OFF) ⇒ ENTRA-CON-CAMBIOS.

**R4 — cierre (estable).** El juez, pudiendo matar al finalista, argumenta que NO debe: premisa verificada viva,
gate cruzado sin forzar, rieles intactos, cero solapamiento con planes `NN_*` (el plan 60 explícitamente NO
incluyó esta mitad; el 56 provee la maquinaria pero no esta fuente). Ningún otro caído merece resurrección: cada
muerte está anclada en riel, score o premisa. Conjunto y ranking idénticos a R3 ⇒ **CONVERGIÓ** con 1 finalista.
Con <3 finalistas, se declara la señal correspondiente: **el pozo de game-changers sigue ~seco** más allá de esta
promoción — coherente con debates #3/#4 y con un producto que ya cerró sus loops grandes.

---

## Cementerio (no re-proponer)

| Idea | Motivo (verificado) |
|------|--------|
| Veredicto sintético en auto-publish → goldens (#3) | Rompe contrato golden=humano-validado; ratchet autorreferencial; el canal honesto (ediciones ADO→positivo) ya está vivo |
| Pipeline que vota / CI→goldens sospechosos (#2) | Atribución causal indeterminista (commits ajenos, flaky, push manual); señal ruidosa sobre mecanismo determinista. BURBUJA: re-evaluar con atribución SHA→run real |
| Auditoría cruzada dual-tracker (#4) | Tooling one-shot sobre 74; solapa F-SHADOW (70, diferida); I2 |
| Estados-79 → telemetría de flujo → catálogo (#5) | Telemetría→política (cementerio heredado); exige persistencia nueva; I3+N3=6 |
| Pre-mortem brief-reverso (#6) | Validador estocástico encubierto (pase LLM extra); duplica costo del único flujo auto |
| Cuarentena de goldens (#7) | Prematuro: catálogo joven, señal escasa, matching semántico ruidoso |
| UI anticipatoria de rejection_lessons (#8) | Superficie UI sobre datos existentes; incremental (54/44) |
| Replay determinista del historial (#9) | Novedad ≤2 (regla dura). Recomendable como herramienta de calibración fuera del top-5 |
| Propagar corrección a hermanas (#10) | Cross-aplicación exige LLM o string-ops frágiles; F2; la lección ya cubre la generación siguiente |
| *(Heredado íntegro de #3/#4)* few-shot positivo, coaching, quórum/best-of-N, LLM-as-judge horneado, grounding multi-cliente, gate coherencia árbol, selector por outcomes, convergencia de árbol, speculative+adaptive | Ver `../TOP5_2026-06-20_POZO_SECO_POST60_IMPLEMENTAR_BACKLOG.md` y `../TOP5_2026-06-21_POST61_LOOP_PREVENCION_MUERTO.md` §Cementerio |

## Tratamiento del roadmap previo (#4, post-61)

- Burbuja pieza 1 (completar plan 60 / bridge positivo): **RESUELTA** vía supervisión 2026-06-21 → retirada.
- Burbuja pieza 2 (mitad negativa): **PROMOVIDA a finalista único** de esta corrida (ver arriba).
- "Auto-publish bypasea la fuente in-app del gate": sigue siendo cierto, pero la respuesta correcta NO es un
  veredicto sintético (#3, muerto); la mitad negativa + el canal positivo vivo cubren la señal honesta.

## Recomendación estratégica (handoff)

1. **Formalizar el finalista** con `proponer-plan-stacky` → plan **81** (mitad negativa del aprendizaje
   bidireccional). Pequeño, determinista, reusa 56+60 íntegros.
2. Implementar el backlog en papel REAL en este orden: **75** (deep links, el más maduro) → **80** (wiring
   codebase-memory-mcp).
3. Corregir memorias/briefings stale: 73 y 77 están IMPLEMENTADOS (commits `e4a2b406`, `43f28baf`).
4. Re-correr este debate recién cuando (a) el loop negativo esté en producción con datos, o (b) exista
   atribución determinista run→SHA→pipeline (reabre la burbuja #2).

## Resumen final (8 líneas)
1. Quinta corrida (post-80): R1 con Brainstormer real (10 ideas), poda/réplica/cierre inline con verificación firsthand.
2. **1 finalista cruza el gate** (no se rellenó a 5): removed_snippets → `derive_negative_golden` → gate.
3. Es la promoción de la burbuja del debate #4: su mitad bloqueante (bridge positivo) ya está cerrada y viva.
4. Premisa re-verificada: la señal negativa muere en lección blanda (`ado_edit_learning.py:49-53`); el único caller de `derive_negative_golden` es la review in-app minoritaria (`regression_capture.py:43`).
5. #3 (veredicto sintético) murió por contrato golden=humano-validado; #2 (CI-que-vota) por atribución indeterminista → burbuja.
6. Los otros 6 murieron por incrementales, señal escasa o F<3; #9 queda como herramienta de calibración no-plan.
7. Dedup corregido firsthand: 73 y 77 IMPLEMENTADOS (el briefing estaba stale); backlog en papel real = 75 y 80.
8. Handoff: `proponer-plan-stacky` → plan 81; luego implementar 75 → 80.
