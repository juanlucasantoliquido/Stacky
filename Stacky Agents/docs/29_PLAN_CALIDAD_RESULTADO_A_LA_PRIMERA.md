# 29 — Plan Calidad del Resultado a la Primera: que el entregable salga correcto, consistente y a la medida del esfuerzo, sin pedirle nada al operador

**Fecha:** 2026-06-14
**Estado:** IMPLEMENTADO COMPLETO 2026-06-15 (Q0.1, Q0.2, Q1.1, Q1.2, Q2.2; Q2.1 diferido per spec)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 parciales), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (implementado salvo UI U2.1), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto), `docs/26_PLAN_MEMORIA_CONFIGURABLE_Y_DIRECTIVAS.md` (**implementado completo** al 2026-06-14), `docs/27_PLAN_MEJORAS_INVISIBLES_MOTOR.md` (I0-I1 implementados; I2-I3 parciales) y `docs/28_PLAN_MEJORAS_ALTO_IMPACTO_INVISIBLES.md` (PROPUESTO, lifecycle/escritura/telemetría).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia `file:line`, diseño con archivos exactos, criterios de aceptación, tests TDD, salvaguarda de calidad y complejidad.

**Tesis (innegociable):** los docs 27 y 28 atacaron dos lados del motor — el 27 hizo que **piense mejor** (mejor contexto, routing de modelo por dificultad, dedup de tokens, caché de contenido) y el 28 que **no se ahogue ni pierda trabajo** (lifecycle, escrituras confiables, telemetría de fallos). Falta el tercer lado, el que el operador realmente juzga: **que el producto del run sea correcto, completo y consistente — a la primera.** Hoy el agente puede terminar con un output que **no cumple los criterios de aceptación del ticket** y, en el mejor caso, eso se **detecta** (U1.2 self-review en modo gate) pero **no se corrige** — cae a `needs_review` y el operador relanza a mano. Los runtimes CLI (claude/codex, los principales) **no reusan los outputs ya aprobados** como ejemplo (el few-shot FA-12 solo corre en copilot), así que arrancan sin el estándar de calidad de la empresa. Y el **esfuerzo del modelo es una constante** (`effort=medium` fijo), no se adapta a la dificultad que ya sabemos estimar. Este plan cierra ese tercer lado **sin pedirle nada al operador**: el mismo run que lanzó sale cumpliendo los criterios más seguido, escrito con el estilo de lo ya aprobado, y gastando esfuerzo en proporción a la dificultad real. El TRABAJO es invisible; el RESULTADO se nota: menos `needs_review` por criterios faltantes, entregables más consistentes, y costo proporcional a la dificultad — **sin sacrificar calidad en ningún caso**.

**"Invisible" NO significa "autónomo" (frontera dura, regla 11):** invisible quiere decir que el operador no configura ni ve el mecanismo. NO quiere decir que el sistema decida por él. **Cada run lo inició el operador**; nada se publica a ADO sin el verdict humano; ningún aprendizaje muta prompts/memoria/goldens sin aprobación. Las acciones de este plan ocurren **dentro de un run que el operador ya lanzó**: inyectar los criterios que el propio ticket declara, reusar outputs que un humano **ya aprobó**, corregir **una vez** un criterio incumplido antes de presentar (exactamente lo que el operador haría al relanzar), y graduar el esfuerzo. Ninguna decide sobre el producto del trabajo ni publica nada. Cada ítem trae su línea explícita **"Por qué NO viola rule 11"**.

**Calidad nunca se sacrifica (segundo eje innegociable de este plan):** ninguna optimización de costo/latencia puede degradar la calidad. Donde un ítem ahorra (esfuerzo bajo en encargos simples), la salvaguarda garantiza que solo se aplica donde la dificultad estimada lo permite y el cap nunca baja de un piso seguro. Donde un ítem cuesta algo más (un pase correctivo, un few-shot, una autoevaluación), el gasto está **acotado y gated**, y se compensa con creces evitando un ciclo de revisión humana + relanzamiento manual. Cada ítem trae una línea **"Salvaguarda de calidad (y cómo se mide)"**.

---

## Relación con los planes 26/27/28 (qué se subsume, qué se reemplaza, qué queda fuera)

> **Estado verificado el 2026-06-14 contra el código** (`codex/subida-cambios-pendientes`): los headers de los docs 23/26/27 quedaron "propuesto" tras implementarse (patrón conocido). Para este plan importa que ya existen, **implementados**, los seams que el 29 EXTIENDE: `services/self_review.py` (U1.2, flags `STACKY_SELF_REVIEW_MODE`/`_MIN_SCORE`, `config.py:314-318`), `services/few_shot.py` (FA-12), `harness/complexity.py::estimate_complexity` (27/I0.2) y el routing por dificultad (27/I1.2). El 29 NO re-implementa ninguno: cierra el lazo de cada uno donde quedó abierto.

- **SUBSUME:** nada. Este plan no re-especifica ningún ítem de 26/27/28.
- **REEMPLAZA:** nada. Los ítems pendientes del 27 (I0.3, I2.x, I3.x) y los 8 del 28 (R0-R2) siguen vigentes y no se tocan.
- **Eje de cada plan (frontera de no-solapamiento):**
  - **26** = perillas que el operador VE y configura (memoria, directivas). El 29 no agrega perillas de operador.
  - **27** = lo que **entra** al modelo y cómo se cobra (contexto/retrieval/routing-de-**modelo**/caché-de-contenido). El 29 no toca `context_enrichment` ensamblado/ranking/retrieval, ni el routing de modelo, ni las cachés de contenido.
  - **28** = que el run **llegue a destino** sin colgarse ni perder trabajo (proceso/writes/telemetría de fallos).
  - **29** = que el **producto** del run sea correcto vs el encargo: cumplir los **criterios de aceptación**, reusar lo **aprobado** en todos los runtimes, y graduar el **esfuerzo** por dificultad. Es el eje *output-quality-per-token*.
- **Frontera fina declarada (tres reparaciones que parecen la misma pero son disjuntas):**
  1. **27/I1.1 (`run_repair`)** repara un run que terminó **vacío o estructuralmente malformado** (JSON inválido, falta una clave) — un glitch de forma, sin mirar el contenido.
  2. **28/R1.2 (validación estructural del pending-task)** bloquea una **escritura** estructuralmente rota antes del POST a ADO.
  3. **29/Q1.1 (pase correctivo de criterios)** corrige un output **bien formado pero que no cumple los criterios de aceptación** — un fallo **semántico**, no de forma. Ningún ítem del 29 re-implementa `run_repair` ni la validación de escritura.
- **Frontera con el few-shot existente:** FA-12 (`few_shot.py`) ya selecciona outputs aprobados y arma el prefix, pero **solo está cableado en copilot** (`agents/base.py:70`). El 29/Q1.2 lo **cablea en los runtimes CLI**; no re-implementa la selección ni el render.
- **Frontera con U1.2 self-review:** ya extrae los criterios de aceptación y gatea a `needs_review` (`self_review.apply_to_execution`, `agent_completion_internal.py:155-165`). El 29/Q1.1 **cierra el lazo** agregando el pase correctivo que U1.2 no hace; reusa su checklist (no re-juzga).
- **Frontera con la complejidad:** `estimate_complexity` (27/I0.2) ya existe y alimenta el routing de **modelo** (27/I1.2). El 29/Q0.2 reusa la misma señal para graduar el **esfuerzo/turnos** — eje distinto del modelo.

---

## 1. Punto de partida: el sustrato de calidad que YA existe (no re-implementar)

Verificado contra el código el 2026-06-14. La lectura central: **la maquinaria de calidad existe pero está a medio cablear o medio cerrada** — se evalúa contra criterios pero no se corrige; se reusa lo aprobado pero solo en un runtime; se sabe estimar la dificultad pero solo se usa para el modelo, no para el esfuerzo. El mayor valor de este plan es **terminar de cerrar esos lazos**, no inventar.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Self-review contra acceptance criteria (U1.2): extrae criterios de ADO, juzga con LLM, gatea a `needs_review` | `services/self_review.py` (`_resolve_criteria:43` lee `Microsoft.VSTS.Common.AcceptanceCriteria`, `review_artifact:60`, `apply_to_execution`), cableado `services/agent_completion_internal.py:155-165`, flags `config.py:314-318` (`STACKY_SELF_REVIEW_MODE` off/annotate/gate, `_MIN_SCORE` 0.7) | OK — **detecta pero NO corrige**; corre post-close (sin resume); re-juzga sin reusar (D-Q1) |
| Few-shot de outputs aprobados (FA-12): top-K execs `verdict=="approved"`, score por contrato+confianza, cap de tokens | `services/few_shot.py:56` (`pick_examples`), `:105` (`build_prefix`), cableado **solo copilot** `agents/base.py:70-88` + `agent_runner.py:39,724` | OK en copilot — **los runtimes CLI no lo usan** (D-Q2) |
| Contract validator: valida el output contra un contrato declarativo **por tipo de agente** (formato/secciones esperadas) | `contract_validator.py` (`validate(agent_type, output_text)`), usado en `harness/post_run.py:62` | OK — valida **forma por agente**, NO los criterios del ticket puntual (D-Q4) |
| Confidence scoring: heurística post-hoc sobre el texto (hedge phrases, TODOs) | `services/confidence.py` (docstring: "se reemplaza por self-reported cuando se integre el LLM real"), `harness/post_run.py:69` | OK — **heurística, no self-reported**; no gobierna ningún esfuerzo extra (D-Q5) |
| Estimación de complejidad determinística (27/I0.2) | `harness/complexity.py::estimate_complexity` → `S/M/L/XL` | OK — alimenta **solo** el routing de modelo (27/I1.2), **no el esfuerzo** (D-Q3) |
| Reasoning effort del CLI | claude `services/claude_code_cli_runner.py:1320-1324` (`--effort`, lee `config.CLAUDE_CODE_CLI_EFFORT` default `"medium"`, `config.py:158`); codex vía su parámetro de reasoning | **Constante** — no se adapta a la dificultad (D-Q3) |
| Post-run unificado: contract gate + confidence + status final | `harness/post_run.py:35` (`finalize_run`) | OK — puro sobre el texto; no recibe los criterios del ticket ni puede relanzar (límite para Q1.1) |
| Ensamblado de contexto multi-runtime (briefing) | `services/context_enrichment.py:34` (`enrich_blocks`), llamado en los 3 runtimes | OK — el seam correcto para inyectar criterios (Q0.1) y few-shot CLI (Q1.2) sin tocar cada runner |
| Telemetría de run (turnos/costo/tokens/contract/confidence) + harness-health (H8) | `harness/telemetry.py:122`, `services/harness_health.py`, `frontend/.../DiagnosticsPage` | OK — **no mide "aprobado a la primera"** (D-Q6); seam para exponer calidad sin UI nueva |
| Autocorrect intra-run (F1.3/H2.3) + run_repair (27/I1.1) | claude `services/cli_autocorrect.py`, codex `services/codex_autocorrect.py`, `harness/run_repair.py` | OK — corrigen **forma** (artifacts inválidos / output vacío/malformado), no **criterios** (D-Q1); seam de presupuesto compartido para Q1.1 |
| Capacidades por runtime (resume/stdin/...) | `harness/capabilities.py:21` (`CAPABILITIES`) | OK — seam para decidir el pase correctivo por-runtime sin `if` dispersos |

**Restricciones vinculantes (idénticas a docs 22-28, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable); "solo Stacky escribe en ADO" = todo por el path de publicación existente (este plan **no agrega caminos de escritura** ni cambia qué/cuándo se publica); mono-operador **sin RBAC** (`current_user()` es un header sin validar); claves de metadata existentes son contrato (**agregar, nunca renombrar**); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR, default **OFF/0**, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → **validar por archivo de test**; **sin fallback silencioso entre runtimes** (claude/codex/copilot se cablean por separado); **sin deps npm/py nuevas** sin justificación escrita (todo con stdlib + el TF-IDF/few-shot/complejidad existentes); el build congelado no tiene FTS5 verificado (no introducirlo).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Cada acción ocurre DENTRO del run que el operador lanzó y o bien inyecta algo que el ticket/empresa **ya declaró** (criterios, ejemplos aprobados), o bien completa el trabajo pedido **una vez** (pase correctivo), o bien gradúa un parámetro de sustrato (esfuerzo). Nada se publica solo; el verdict humano y el path de publicación (U1.3/U2.2 del doc 23) quedan **intactos**.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía ni auto-intake.** Ningún run nace sin el operador; nada "agarra trabajo solo". Corregir un criterio incumplido dentro del run que el operador lanzó no es decidir trabajo nuevo: es completar el que ya se pidió, una vez, como haría el humano. (Descartado en doc 24 §2; se respeta al pie.)
2. **No publica ni transiciona ADO por su cuenta, ni cambia QUÉ/CUÁNDO se publica.** El verdict humano no se toca. La única lectura nueva de ADO es la de criterios (Q0.1), que reusa la caché de lecturas del 27/I3.2 cuando esté disponible.
3. **No expone perillas nuevas al operador.** Todos los flags son **internos** (los administra quien opera el arnés vía la pantalla de flags genérica que ya existe). La única superficie que cambia es la **DiagnosticsPage existente** (Q2.2), que muestra *más* información de calidad sin pedir acción.
4. **No re-implementa el motor del 27 ni el lifecycle del 28.** No toca `context_enrichment` (ensamblado/ranking/retrieval), ni el routing de **modelo**, ni `run_repair`, ni nada de proceso/escritura/zombie. Solo agrega bloques aditivos al briefing y un pase correctivo semántico.
5. **No re-implementa U1.2 ni FA-12.** Cierra el lazo de U1.2 (le agrega el pase correctivo) y cablea FA-12 en los runtimes donde falta. Reusa `review_artifact`, `pick_examples`, `build_prefix` y `estimate_complexity` tal cual.
6. **No sacrifica calidad por costo.** El ahorro de esfuerzo solo se aplica donde la dificultad estimada lo permite, con un piso seguro; el gasto extra (pases/few-shot/autoeval) está acotado y gated. No hay ningún ítem cuyo "ahorro" pueda producir un peor entregable.
7. **No introduce FTS5 ni deps nuevas.** Todo con stdlib + el TF-IDF/few-shot/complejidad/self-review ya existentes.

---

## 3. Diagnóstico: dónde el resultado deja calidad (y plata) sobre la mesa (con evidencia)

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-Q1** | **El self-review contra criterios detecta pero no corrige.** `self_review.apply_to_execution` (`agent_completion_internal.py:155-165`) corre en `mode=gate` y, si el output no alcanza `STACKY_SELF_REVIEW_MIN_SCORE`, degrada a `needs_review` — pero **no intenta arreglar** el criterio incumplido. Además corre **post-close** (sin sesión resumible) y vuelve a juzgar sin reusar un resultado previo. El autocorrect/run_repair solo cubren fallos de **forma** (artifacts/vacío/malformado), no de **criterio**. | `services/self_review.py` (`review_artifact:60`, `apply_to_execution`), `agent_completion_internal.py:155-165`, `config.py:314-318`; `harness/run_repair.py` (solo forma) | `needs_review` por un criterio que un único pase dirigido habría salvado → revisión humana evitable + relanzamiento manual; el costo del juicio LLM se paga sin capturar su valor (solo flaggea). |
| **D-Q2** | **Los outputs aprobados solo se reusan en copilot.** El few-shot FA-12 (`few_shot.pick_examples`, filtra `verdict=="approved"`, cap de tokens, `build_prefix`) está cableado **solo** en el path copilot (`agents/base.py:70-88`). Los runtimes CLI (claude/codex — los headless/principales) **no** inyectan ejemplos aprobados (grep `few_shot` en `claude_code_cli_runner.py`/`codex_cli_runner.py` → 0). Mismo patrón copilot-only que tuvo el `output_cache` (27/D-I2). | `services/few_shot.py:56,105`, `agents/base.py:70-88`; ausencia en runners CLI verificada | Los runtimes que más se usan arrancan **sin el estándar de calidad ya validado** por la empresa → outputs menos consistentes, más variabilidad de estilo/estructura, más iteración humana para alinear. |
| **D-Q3** | **El esfuerzo del modelo es constante; la dificultad estimada no lo modula.** `CLAUDE_CODE_CLI_EFFORT` es fijo (`config.py:158`, default `"medium"`; aplicado `claude_code_cli_runner.py:1320-1324`); codex corre con su effort por defecto. `estimate_complexity` (27/I0.2) ya produce `S/M/L/XL` pero **solo** alimenta el routing de **modelo** (27/I1.2), no el esfuerzo ni el presupuesto de turnos. | `config.py:158`, `claude_code_cli_runner.py:1320-1324`, `harness/complexity.py::estimate_complexity` (consumido solo por routing) | Encargos triviales corren con effort de más (caro/lento sin ganancia); encargos difíciles cortos corren con effort de menos (calidad por debajo de lo posible). Plata y calidad sobre la mesa, invisible. |
| **D-Q4** | **Los criterios de aceptación solo se usan reactivamente (al juzgar), no proactivamente (al trabajar).** El único consumidor de `Microsoft.VSTS.Common.AcceptanceCriteria` es `self_review._resolve_criteria` (`self_review.py:43-57`), que corre al final. El briefing (`enrich_blocks`) **no** inyecta los criterios como checklist explícito al inicio (grep `AcceptanceCriteria` en `context_enrichment.py` → 0). El contract validator mira la forma por agente, no los criterios del ticket puntual. | `self_review.py:43-57` (único consumidor), ausencia en `context_enrichment.py`, `contract_validator.py` (forma por agente) | El agente descubre los criterios **al ser juzgado**, no al trabajar → apunta a un blanco difuso, produce de más/de menos, y el self-review encuentra huecos que un checklist al frente habría evitado. Más reprocesos. |
| **D-Q5** | **La confianza es heurística post-hoc, no self-reported, y no gobierna esfuerzo.** `confidence.score(output_text)` (`confidence.py`, `post_run.py:69`) infiere confianza del texto (hedge phrases/TODOs); el propio docstring dice que la versión real sería self-reported por el agente. Nada usa esa señal para decidir un esfuerzo extra donde la confianza es baja. | `services/confidence.py` (docstring), `harness/post_run.py:69` | No hay señal accionable de "esto quedó dudoso, conviene un pase más" vs "esto quedó sólido, no gastes": el esfuerzo se reparte parejo en vez de concentrarse donde rinde. |
| **D-Q6** | **No se mide "aprobado a la primera".** La telemetría tiene costo/turnos/contract/confidence (`harness/telemetry.py:122`) pero **no** un KPI de tasa de aceptación a la primera (sin `needs_review` ni reprocesos), ni el efecto del few-shot/criterios sobre la calidad. `harness_health` (H8) no lo cubre. | `harness/telemetry.py:122`, `services/harness_health.py` | Sin un número de calidad-a-la-primera no se puede saber si estas mejoras funcionan ni afinar dónde invertir esfuerzo. No se mejora lo que no se mide. |

**Lectura estratégica:** el 27 mejoró lo que entra; el 28 que llegue a destino; este plan mejora **lo que sale**. Cierra cuatro lazos abiertos: el self-review que detecta pero no corrige (Q1.1), el few-shot aprobado que solo vive en copilot (Q1.2), la dificultad que solo elige modelo y no esfuerzo (Q0.2), y los criterios que solo se usan para juzgar y no para guiar (Q0.1) — y lo vuelve medible (Q2.2). El operador no toca nada: ve outputs que cumplen los criterios más seguido, escritos con el estándar de lo aprobado, y un costo proporcional a la dificultad.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo** y por riesgo. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: **Q0** (quick wins que reusan señales ya implementadas) → **Q1** (los de mayor valor: cerrar el lazo de criterios y reusar lo aprobado) → **Q2** (confianza real y medición). Todos los flags default **OFF/0**; con todo en default, el resultado es **byte-idéntico** a hoy, runtime por runtime.

### FASE Q0 — Quick wins: guiar con lo que el ticket ya declara y la dificultad que ya sabemos

---

#### Q0.1 Inyección proactiva de los criterios de aceptación como checklist en el briefing

- **Ataca:** D-Q4.
- **Problema + evidencia:** los criterios de aceptación del ticket solo se leen al final, para juzgar (`self_review._resolve_criteria:43-57`); el briefing (`enrich_blocks`) no los inyecta como guía al inicio (ausentes en `context_enrichment.py`).
- **Propuesta (mínima):** un **bloque de contexto nuevo y aditivo** `acceptance-criteria` (alta prioridad, fuente de verdad — junto a `ado-epic-structured`/`client-profile`), producido reusando la lógica de `self_review._resolve_criteria` extraída a un helper compartido `services/acceptance_criteria.py::resolve(ticket) -> str` (mismo origen ADO; **reusa la caché de lecturas del 27/I3.2** si está, si no es best-effort). Se renderiza como checklist explícito ("Tu entregable DEBE cumplir, uno por uno: …"). Inyectado en `enrich_blocks` detrás de flag; participa del dedup (27/I0.1) y del budget (F2.4) como cualquier bloque de alta prioridad (nunca se poda).
- **Impacto esperado:** **calidad** — el agente apunta a los criterios desde el turno 1 → menos huecos que el self-review tenga que marcar. **Eficiencia** — menos reprocesos/turnos para llegar a lo mismo (apuntar bien la primera vez es más barato que corregir después).
- **Por qué es invisible:** el operador no escribe ni ve nada nuevo; los criterios ya están en el ticket que él seleccionó. Solo nota que el entregable "viene más completo".
- **Por qué NO viola rule 11:** inyectar lo que el ticket **ya declara** no decide trabajo ni publica nada; es sustrato del prompt del run que el operador lanzó.
- **Salvaguarda de calidad (y cómo se mide):** es **aditivo y de alta prioridad** → nunca desplaza épica/perfil/directivas (que siguen intocables); si no hay criterios en ADO, el bloque no se inyecta (no-op). Flag OFF → briefing byte-idéntico. Se mide con un test de regresión sobre fixtures de `test_context_budget.py`/`test_context_dedup.py` y con el KPI de Q2.2 (criterios cumplidos a la primera).
- **Flag:** `STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED` (bool, default **false**) + `..._PROJECTS` (csv) en `config.py` + `FLAG_REGISTRY`.
- **TDD (`tests/test_acceptance_criteria_injection.py`):** ticket con AC → bloque de alta prioridad presente con los criterios; ticket sin AC → no se inyecta; flag OFF → byte-idéntico; interacción con dedup/budget (no se poda; no duplica con la épica).
- **Complejidad:** S/M.

---

#### Q0.2 Esfuerzo (y presupuesto de turnos) a la medida de la dificultad estimada

- **Ataca:** D-Q3. Reusa `estimate_complexity` (27/I0.2); NO re-implementa el routing de modelo (27/I1.2).
- **Problema + evidencia:** el effort es constante (`CLAUDE_CODE_CLI_EFFORT` fijo, `config.py:158`; aplicado `claude_code_cli_runner.py:1320-1324`); `estimate_complexity` ya produce `S/M/L/XL` pero solo se usa para el modelo.
- **Propuesta (mínima):** un mapa determinístico `complexity → effort` aplicado en el punto donde cada runner arma sus flags de CLI: `S → low`, `M → medium`, `L/XL → high`, **dentro de límites seguros** (un piso `STACKY_EFFORT_FLOOR`, default `medium`, por debajo del cual nunca se baja para un agente crítico). claude vía `--effort` (`:1320-1324`); codex vía su parámetro de reasoning effort si lo expone — **sin fallback silencioso**: cada runtime mapea con su mecanismo; si codex no soporta effort, en codex el ítem aplica el **presupuesto de turnos** por dificultad (límite blando bajo el cap `STACKY_RUNAWAY_MAX_TURNS`) y deja el effort en codex sin tocar. copilot N/A (declarado). El override del operador sobre el modelo/effort, si existe, **siempre gana**.
- **Impacto esperado:** **eficiencia** — encargos `S` corren con menos effort (más baratos/rápidos) sin perder calidad porque son simples. **Calidad** — encargos `L/XL` corren con effort `high` (mejor razonamiento donde la dificultad lo pide), incluso si son cortos en tokens.
- **Por qué es invisible:** el operador no elige effort; solo nota que lo difícil sale mejor y lo simple sale más rápido.
- **Por qué NO viola rule 11:** graduar un parámetro de sustrato (esfuerzo) dentro de límites no decide trabajo ni publica; es lo que el router ya hace con el modelo, ahora con el effort.
- **Salvaguarda de calidad (y cómo se mide):** el **piso de esfuerzo** garantiza que nunca se baja por debajo de `medium` para agentes críticos → el ahorro solo ocurre donde la dificultad es genuinamente baja; nunca al revés. El upgrade a `high` en `L/XL` solo sube calidad. Flag OFF → effort fijo actual (byte-idéntico). Se mide con tests de mapeo + el KPI de calidad de Q2.2 segmentado por complejidad (la calidad de los `S` no debe caer).
- **Flag:** `STACKY_ADAPTIVE_EFFORT_ENABLED` (bool, default **false**) + `STACKY_EFFORT_FLOOR` (str, default `"medium"`).
- **TDD (`tests/test_adaptive_effort.py`):** `S→low`, `M→medium`, `L/XL→high`; piso respetado para agente crítico; override gana; flag OFF → effort fijo; codex sin effort → ajusta turnos, no effort; copilot no-op.
- **Complejidad:** M.

---

### FASE Q1 — Alto valor: cerrar el lazo de criterios y reusar lo aprobado en todos los runtimes

---

#### Q1.1 Pase correctivo único dirigido a los criterios incumplidos (cierra U1.2) — el ítem de mayor valor

- **Ataca:** D-Q1. EXTIENDE `self_review` (U1.2); reusa el seam de presupuesto del autocorrect/run_repair. NO re-implementa ninguno.
- **Problema + evidencia:** U1.2 detecta criterios incumplidos y degrada a `needs_review` (`agent_completion_internal.py:162-163`) pero **no corrige**; corre post-close (sin resume). El autocorrect/run_repair solo cubren **forma**.
- **Frontera con lo existente (declarada):** `run_repair` (27/I1.1) repara **vacío/malformado** (forma); el autocorrect repara **artifacts inválidos** (forma). Este ítem cubre el caso que ninguno atrapa: el output está **bien formado** pero **no cumple uno o más criterios de aceptación** (semántica). Se reintenta **UNA** vez, dirigido **solo** a los criterios incumplidos.
- **Propuesta (mínima):**
  - **Mover el punto de evaluación a un seam con resume.** Hoy U1.2 juzga en `agent_completion_internal` (post-close). Este ítem invoca `self_review.review_artifact(execution_id, artifact_text)` (función ya reusable, `self_review.py:60`) en el **runner**, justo ANTES de `finalize_run` — donde la sesión es resumible (igual que `run_repair`). El `SelfReviewResult` (score + checklist de criterios con cumple/no-cumple) se **cachea por `execution_id`**; `apply_to_execution` lo reusa como **red final** post-close (no re-juzga → cero doble-costo de LLM).
  - **Pase correctivo dirigido.** Si `score < STACKY_SELF_REVIEW_MIN_SCORE` Y hay criterios marcados como no-cumplidos Y el runtime soporta resume/stdin (`capabilities.CAPABILITIES[runtime].supports_resume`) Y queda presupuesto: **un único** mensaje correctivo, corto y fijo, listando **solo** los criterios incumplidos ("Estos criterios de aceptación NO se cumplieron: <lista>. Corregí SOLO eso, manteniendo el resto del entregable; mismo formato."), por el MISMO transporte del autocorrect (stdin/resume). Se re-evalúa **una** vez: si ahora cumple → `completed`; si no → `needs_review` como hoy.
  - **Presupuesto duro compartido:** `STACKY_CRITERIA_REPAIR_MAX_RETRIES` (int, default 1). El conteo se comparte con el autocorrect y el `run_repair` del runtime (mismo techo) para que el total de mensajes correctivos por run no se dispare; alternativa aceptable y declarada: presupuesto propio acotado a 1, documentando peor caso autocorrect(N)+run_repair(1)+criteria_repair(1).
  - **Modelo/effort:** el pase usa el MISMO modelo y effort del run (dentro del clamp); NO escala (eso sería 27/I1.2 territory).
  - **Sello:** `metadata["criteria_repair"] = {"attempted": bool, "unmet_before": [...], "recovered": bool}` (clave NUEVA, aditiva).
- **Impacto esperado:** **calidad** — runs que hoy mueren en `needs_review` por un criterio puntual se recuperan cumpliéndolo. **Eficiencia** — menos ciclos de revisión humana + relanzamiento manual; y se **captura el valor** del juicio LLM de U1.2 que hoy solo flaggea.
- **Por qué es invisible:** el operador no relanza ni corrige a mano; ve el entregable ya cumpliendo los criterios. Cero pasos nuevos.
- **Por qué NO viola rule 11:** el run lo lanzó el operador; la corrección ocurre DENTRO de ese run, antes de presentar; NO publica nada (verdict humano y publicación U1.3/U2.2 intactos); es exactamente lo que el operador haría (relanzar una vez pidiendo cumplir el criterio), sin obligarlo. No es trabajo nuevo: es completar el pedido.
- **Salvaguarda de calidad (y cómo se mide):** corrige **solo** criterios objetivamente declarados en el ticket (no inventa estándares); si el pase NO logra cumplir → va a `needs_review` (el repair **no enmascara** mala calidad, solo salva lo recuperable); sin resume → no repara (sin fallback silencioso; degrada a comportamiento actual de gate); presupuesto duro de 1. Flag OFF → byte-idéntico (U1.2 gate como hoy). Se mide con la tasa de `needs_review` por criterio (debe caer) y la tasa de `criteria_repair.recovered` (Q2.2).
- **Flag:** `STACKY_CRITERIA_REPAIR_ENABLED` (bool, default **false**) + `STACKY_CRITERIA_REPAIR_MAX_RETRIES` (int, default 1) + `FLAG_REGISTRY`. Depende de `STACKY_SELF_REVIEW_MODE != off` para tener criterios que evaluar (degradado declarado: con self-review off, el repair no dispara).
- **TDD (`tests/test_criteria_repair.py`):** output con 1 criterio incumplido + resume → un pase dirigido; recupera → `completed` + `criteria_repair.recovered=true`; no recupera → `needs_review` + `recovered=false`; output que cumple todos → no dispara; sin resume → no repara; el presupuesto se comparte con autocorrect/run_repair (no se suman); `apply_to_execution` reusa el resultado cacheado (no re-juzga); flag OFF → byte-idéntico. Mock de runner y de `review_artifact` (sin binarios ni LLM reales).
- **Complejidad:** M/L (toca el cierre de ambos runners CLI; partible: PR1 codex, PR2 claude).

---

#### Q1.2 Cablear el few-shot de outputs aprobados (FA-12) en los runtimes CLI

- **Ataca:** D-Q2. Reusa `few_shot.pick_examples`/`build_prefix`; NO re-implementa la selección ni el render.
- **Problema + evidencia:** FA-12 (`few_shot.py:56,105`) solo se cablea en copilot (`agents/base.py:70-88`); los runtimes CLI no inyectan ejemplos aprobados (ausente en `claude_code_cli_runner.py`/`codex_cli_runner.py`).
- **Propuesta (mínima):** un **bloque de contexto nuevo y aditivo** `few-shot-approved` en `enrich_blocks` (el seam compartido por los 3 runtimes), que llama a `few_shot.pick_examples(agent_type=…, project=…, exclude_ticket_id=<este ticket>, k, max_chars_per_example)` y renderiza con `build_prefix`. Prioridad media-alta (importante pero podable bajo presión, después de épica/criterios), con su propio sub-budget para no desplazar la fuente de verdad. El cap de tokens por ejemplo ya existe en `pick_examples` (`max_chars_per_example`, `:62`). **Sin fallback silencioso:** el bloque se inyecta para los runtimes que lo activan; copilot ya lo tiene por su path (no se duplica — el flag CLI no toca el path copilot).
- **Impacto esperado:** **calidad** — los runtimes principales arrancan con el estándar ya aprobado por la empresa → outputs más consistentes en estilo/estructura/detalle, menos variabilidad. **Eficiencia** — menos iteración humana para alinear el estilo; el agente "ya sabe cómo se ve lo bueno".
- **Por qué es invisible:** el operador no selecciona ejemplos ni configura nada; los ejemplos salen de lo que él (o el equipo) ya aprobó. Solo nota outputs más parejos.
- **Por qué NO viola rule 11:** reusar outputs que un humano **ya aprobó** como ejemplo no decide ni publica nada; es sustrato del prompt.
- **Salvaguarda de calidad (y cómo se mide):** solo usa execs con `verdict=="approved"` y mejor score combinado contrato+confianza (`pick_examples:79-85`) → nunca enseña con un mal ejemplo; el cap de tokens evita inflar el contexto (y respeta el budget del 27); excluye el ticket actual (`exclude_ticket_id`) para no filtrar el propio enunciado; si no hay aprobados, no se inyecta (no-op). Flag OFF → byte-idéntico. Se mide con el KPI de Q2.2 segmentado con/sin few-shot (la calidad-a-la-primera de los runtimes CLI debe subir).
- **Flag:** `STACKY_CLI_FEWSHOT_ENABLED` (bool, default **false**) + `STACKY_CLI_FEWSHOT_K` (int, default 2) + `..._PROJECTS` (csv).
- **TDD (`tests/test_cli_fewshot.py`):** con ≥1 exec aprobada → bloque `few-shot-approved` presente con el prefix de `build_prefix`; sin aprobadas → no se inyecta; excluye el ticket actual; respeta el cap de tokens; flag OFF → byte-idéntico; copilot no se duplica.
- **Complejidad:** M.

---

### FASE Q2 — Confianza real y medición: concentrar el esfuerzo donde rinde y cerrar el loop

---

#### Q2.1 Confianza self-reported que concentra el esfuerzo correctivo (opcional / diferido)

- **Ataca:** D-Q5. Es el ítem **menos invisible** del plan (toca el system prompt) — se incluye marcado como **opcional/diferido**, mismo criterio que el 27/I3.3.
- **Problema + evidencia:** `confidence.score` es heurística post-hoc (`confidence.py`, docstring: "se reemplaza por self-reported cuando se integre el LLM real"); nada usa la confianza para decidir un esfuerzo extra.
- **Propuesta (mínima):** pedir al agente, vía una línea fija en el briefing, un **bloque de autoevaluación** corto y estructurado al final del output (p. ej. `confidence: 0–100` + criterios que considera dudosos). Parsearlo (reusando el patrón `_extract_json` de `self_review.py:28`) y, cuando la confianza self-reported sea baja en criterios concretos, **priorizar** el pase correctivo de Q1.1 hacia esos criterios (no agregar pases; concentrar el único pase). La heurística de `confidence.py` queda como **fallback** cuando el agente no reporta.
- **Impacto esperado:** **eficiencia** — el único pase correctivo se gasta donde el propio agente señala duda, no a ciegas. **Calidad** — se atiende primero lo que el modelo sabe que quedó flojo.
- **Por qué es invisible:** el operador no ve el bloque de autoevaluación (se consume internamente, no se publica); solo se beneficia de un pase mejor dirigido.
- **Por qué NO viola rule 11:** pedir y consumir una autoevaluación no decide ni publica; gobierna un mecanismo (Q1.1) que ya respeta rule 11.
- **Salvaguarda de calidad (y cómo se mide):** la autoevaluación **solo prioriza**, nunca **reemplaza** el juicio de U1.2 (un agente que se auto-aprueba mal igual pasa por el self-review objetivo contra los criterios de ADO); fallback a la heurística actual si no reporta. Flag OFF → confidence como hoy, sin bloque de autoeval. Se mide comparando recuperación de Q1.1 con/sin la priorización.
- **Flag:** `STACKY_SELF_REPORTED_CONFIDENCE_ENABLED` (bool, default **false**).
- **TDD (`tests/test_self_reported_confidence.py`):** parseo del bloque de autoeval; prioriza el pase hacia el criterio dudoso; ausencia de bloque → fallback heurístico; no reemplaza el gate objetivo; flag OFF → byte-idéntico.
- **Complejidad:** M (toca briefing + el orquestador de Q1.1; depende de Q1.1).

---

#### Q2.2 KPI de "aprobado a la primera" + efecto de few-shot/criterios (read-only, sin UI nueva)

- **Ataca:** D-Q6. Extiende `harness_health` (H8) y la `HarnessHealthCard` existente; NO crea UI nueva.
- **Problema + evidencia:** la telemetría no tiene un KPI de calidad-a-la-primera (`harness/telemetry.py:122`); `harness_health` no lo cubre.
- **Propuesta (mínima):** un bloque de **calidad** en `services/harness_health.py`, por proyecto y ventana: `tasa_aprobado_a_la_primera = completed_sin_needs_review_ni_criteria_repair / total_completados`; `needs_review_por_criterio` (de `self_review`/`criteria_repair`); `tasa_recuperacion_criteria_repair` (`criteria_repair.recovered=true / attempted`); y un corte **con/sin few-shot** y **con/sin criterios inyectados** (de la metadata `few_shot_count`/el bloque `acceptance-criteria`) para ver el efecto. Read-only, leyendo la metadata/tablas que Q0.1/Q1.1/Q1.2 ya poblan.
- **Impacto esperado:** la calidad-a-la-primera se vuelve un **número visible** en la pantalla que el operador/management ya consultan → se puede afinar dónde invertir esfuerzo, sin pedirle nada al operador.
- **Por qué es invisible:** se agrega a una card existente; cero pasos nuevos, cero workflow nuevo.
- **Por qué NO viola rule 11:** mostrar números no decide nada; es observabilidad.
- **Salvaguarda de calidad (y cómo se mide):** definiciones explícitas y testeadas (qué cuenta como "a la primera") para que el KPI no mienta; read-only puro; si falta una fuente, degrada con gracia ("—"). Flag OFF → la card no agrega el bloque (byte-idéntico). Se mide con un test del endpoint con datos sintéticos.
- **Flag:** `STACKY_QUALITY_KPIS_ENABLED` (bool, default **false**).
- **TDD (`tests/test_harness_health_quality.py`):** con runs sintéticos (aprobados, needs_review, criteria_repair recuperados/no, con/sin few-shot) → los KPI correctos por proyecto/ventana; fuente ausente → degrada; flag OFF → sin bloque nuevo.
- **Complejidad:** M.

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | **Q0.1** Inyección de criterios como checklist | S/M | **Alto (calidad a la primera)** | Bajo (aditivo, flag OFF idéntico) | — |
| 2 | **Q0.2** Esfuerzo a la medida de la dificultad | M | Alto (costo↓ / calidad↑ por dificultad) | Bajo (piso de esfuerzo, flag OFF) | `estimate_complexity` (en código) |
| 3 | **Q1.1** Pase correctivo de criterios incumplidos | M/L | **Muy alto (menos needs_review por criterio)** | Medio (toca cierre de runners → flag, extiende U1.2/autocorrect) | self_review (en código); `STACKY_SELF_REVIEW_MODE != off` |
| 4 | **Q1.2** Few-shot aprobado en runtimes CLI | M | **Muy alto (consistencia/calidad)** | Bajo (reusa FA-12, cap de tokens) | `few_shot` (en código) |
| 5 | **Q2.2** KPI de calidad a la primera | M | Alto (cierra el loop) | Bajo (read-only) | Q0.1/Q1.1/Q1.2 pueblan datos |
| 6 | **Q2.1** Confianza self-reported (opcional/diferido) | M | Medio (concentra el pase) | Medio (toca prompts) | Q1.1 |

**Reglas de implementación (las 7 del doc 22 + las de frontend del doc 23 aplican íntegras):** TDD; validar por archivo de test (suite contaminada); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves nuevas (`criteria_repair`, los KPI de calidad, y el poblado de `few_shot_count` ya existente en CLI); default **OFF/0** (retro-compat **byte-idéntica** — con todos los flags en default, el resultado es EXACTAMENTE el de hoy, runtime por runtime); ADO solo por los caminos existentes (este plan no agrega escrituras; la única lectura nueva es la de criterios, que reusa la caché 27/I3.2); **sin fallback silencioso entre runtimes** (Q1.1 no repara sin resume; Q1.2/Q0.2 se cablean por runtime); sin deps npm/py nuevas (todo con el self-review/few-shot/complejidad existentes); UI (DiagnosticsPage) degrada con gracia.

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Resumen de la doctrina: (a) cada acción ocurre DENTRO de un run que el operador lanzó; (b) lo que se inyecta es lo que el ticket/empresa **ya declaró** (criterios) o **ya aprobó** (few-shot); (c) la única "corrección" (Q1.1) completa el trabajo pedido **una vez** contra criterios objetivos del ticket, sin publicar ni decidir, y si no lo logra va a `needs_review` como hoy; (d) lo que "aprende/mide" (Q2.x) produce números, nunca mutaciones automáticas. Cada ítem trae su línea "Por qué NO viola rule 11".

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (que NO configura ni ve estos mecanismos)
- **Hoy:** lanza un run; a veces el output no cumple un criterio del ticket y cae a `needs_review`, y tiene que relanzar a mano pidiendo el criterio; los runtimes CLI producen outputs de estilo dispar; el esfuerzo es el mismo para un encargo trivial que para uno difícil.
- **Después (sin tocar nada):** el mismo run sale cumpliendo los criterios más seguido (se inyectan al frente y se corrige una vez lo que falte), con un estilo más consistente con lo ya aprobado (few-shot en CLI), y más rápido/barato en lo simple y mejor razonado en lo difícil (esfuerzo a la medida). No ve ninguna perilla nueva: solo nota que Stacky "entrega mejor a la primera".

### Desarrollador / equipo (que vive en ADO)
- **Hoy:** recibe artefactos cuya completitud frente a los criterios depende del run, y con estilo variable según el runtime.
- **Después:** recibe artefactos que cumplen los criterios del ticket más seguido y con un estándar de estilo/estructura más parejo — sin cambios en cómo Stacky escribe en ADO.

### Management
- **Hoy:** no hay un número de "calidad a la primera"; la mejora de calidad es anecdótica.
- **Después:** una tasa de **aprobado a la primera**, la recuperación del pase correctivo y el efecto del few-shot/criterios en la DiagnosticsPage existente (Q2.2) — la calidad se vuelve medible y el costo se hace proporcional a la dificultad, sin sumar trabajo operativo.

---

## 7. Ventaja competitiva: por qué entregar bien a la primera gana

1. **El arnés aprende de lo que el humano aprobó; un CLI suelto, no.** Cada entregable aprobado se convierte en ejemplo para el siguiente run, en todos los runtimes — el estándar de calidad de la empresa se propaga solo, sin que nadie cure ejemplos a mano. Un CLI suelto arranca de cero en cada invocación.
2. **El criterio se persigue, no se descubre tarde.** Inyectar los criterios al frente y corregir una vez lo que falte convierte el "lo reviso y lo mando a rehacer" en "salió cumpliendo" — sin cruzar la línea de la autonomía (corrige contra criterios objetivos del ticket, una vez, sin publicar). El centauro firma menos reprocesos triviales.
3. **El esfuerzo va donde rinde, sin sacrificar calidad.** Gastar `high` en lo difícil y `low` en lo trivial — gobernado por una estimación determinística y un piso seguro — baja el costo agregado sin tocar la calidad de lo que importa. Un CLI suelto corre con un esfuerzo fijo o exige que el humano lo elija a mano.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo | Fuente |
|---|---|---|---|
| Tasa de aprobado a la primera (sin needs_review ni reproceso) | no medida | medible y creciente | KPI Q2.2 |
| `needs_review` por criterio de aceptación incumplido | caen a revisión humana | reparados dentro del run (Q1.1) — reducción medible | `criteria_repair` + Q2.2 |
| Recuperación del pase correctivo (`recovered/attempted`) | n/a | alta y medible | `metadata["criteria_repair"]` |
| Consistencia/calidad de outputs en runtimes CLI | sin few-shot aprobado | con few-shot (Q1.2) — calidad-a-la-primera CLI ↑ | Q2.2 con/sin few-shot |
| Completitud frente a criterios a la primera | criterios solo al juzgar | criterios inyectados al frente (Q0.1) | Q2.2 |
| Costo/latencia por dificultad | effort constante | esfuerzo proporcional (Q0.2), piso seguro | telemetría costo/turnos por complejidad |
| Calidad de los encargos simples tras bajar effort | n/a | **no debe caer** (salvaguarda) | Q2.2 segmentado por complejidad |
| Perillas nuevas que el operador debe tocar | — | **cero** (todos los flags internos, default OFF) | — |

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El pase correctivo (Q1.1) enmascara mala calidad "arreglando" para pasar el gate | Corrige **solo** criterios objetivos declarados en el ticket; si no los cumple → `needs_review` como hoy. Un solo pase, presupuesto duro. El gate objetivo de U1.2 sigue siendo el juez. |
| Bajar el effort (Q0.2) degrada un encargo que parecía simple pero no lo era | Piso de esfuerzo (`STACKY_EFFORT_FLOOR`, default `medium`) para agentes críticos; solo se baja con complejidad estimada `S`; KPI Q2.2 segmentado por complejidad vigila que la calidad de los `S` no caiga. |
| El few-shot en CLI (Q1.2) infla el contexto o "contamina" con un ejemplo malo | Solo execs `approved` con mejor score contrato+confianza; cap de tokens por ejemplo ya existente; sub-budget propio; excluye el ticket actual; respeta el budget del 27. |
| Doble costo de LLM (U1.2 juzga dos veces: en el runner y en `apply_to_execution`) | Q1.1 cachea el `SelfReviewResult` por `execution_id`; `apply_to_execution` lo reusa (no re-juzga). |
| Q1.1 depende de resume y los runtimes difieren | Sin fallback silencioso: solo repara en runtimes con `supports_resume`; el resto degrada al gate actual. `capabilities` declara la diferencia. |
| Inyectar criterios (Q0.1) duplica lo que ya trae la épica | Participa del dedup (27/I0.1); test de no-duplicación con la épica; alta prioridad pero podable solo por dedup, nunca por budget. |
| La autoevaluación (Q2.1) lleva a un agente a auto-aprobarse mal | Solo **prioriza** el pase; nunca reemplaza el juicio objetivo de U1.2 contra ADO; fallback a la heurística. Por eso es opcional/diferido. |
| Costo extra agregado de pases/few-shot/autoeval | Todo gated y acotado (un pase, k ejemplos, una autoeval); se compensa evitando ciclos de revisión humana + relanzamiento. Visible en la telemetría de costo. |

---

## 10. Roadmap por fases (estado)

| Fase | Ítem | Estado | Archivos clave (file:line) |
|---|---|---|---|
| Q0 | Q0.1 Inyección de criterios como checklist | **IMPLEMENTADO 2026-06-15** | `services/acceptance_criteria.py` (nuevo), `services/context_enrichment.py:_inject_acceptance_criteria`, `_BLOCK_PRIORITY["acceptance-criteria"]=74`, `config.py:STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED`, `FLAG_REGISTRY`, tests: `test_acceptance_criteria_injection.py` (9 tests) |
| Q0 | Q0.2 Esfuerzo a la medida de la dificultad | **IMPLEMENTADO 2026-06-15** | `services/claude_code_cli_runner.py:_map_effort`, `_build_command(effort_override=)`, codex: bloque `_codex_adaptive_turns`, `config.py:STACKY_ADAPTIVE_EFFORT_ENABLED+STACKY_EFFORT_FLOOR`, `FLAG_REGISTRY`, tests: `test_adaptive_effort.py` (13 tests) |
| Q1 | Q1.1 Pase correctivo de criterios incumplidos | **IMPLEMENTADO 2026-06-15** | `harness/criteria_repair.py` (nuevo; `attempt_criteria_repair`, `get_cached_review`, `_REVIEW_CACHE`, `mark_recovery`), cableado en `claude_code_cli_runner.py:_on_stream_event`, caché en `self_review.apply_to_execution`, `config.py:STACKY_CRITERIA_REPAIR_ENABLED+MAX_RETRIES`, `FLAG_REGISTRY`, tests: `test_criteria_repair.py` (11 tests) |
| Q1 | Q1.2 Few-shot aprobado en runtimes CLI | **IMPLEMENTADO 2026-06-15** | `services/context_enrichment.py:_inject_cli_fewshot`, `_BLOCK_PRIORITY["few-shot-approved"]=55`, `config.py:STACKY_CLI_FEWSHOT_ENABLED+K+PROJECTS`, `FLAG_REGISTRY`, tests: `test_cli_fewshot.py` (9 tests) |
| Q2 | Q2.2 KPI de calidad a la primera | **IMPLEMENTADO 2026-06-15** | `services/harness_health.py:_compute_quality_kpis`, `HarnessHealth._quality`, `to_dict["quality"]`, `config.py:STACKY_QUALITY_KPIS_ENABLED`, `FLAG_REGISTRY`, tests: `test_harness_health_quality.py` (8 tests) |
| Q2 | Q2.1 Confianza self-reported (opcional/diferido) | DIFERIDO (per spec, fuera del scope de este PR) | — |

**Estado global:** IMPLEMENTADO COMPLETO 2026-06-15 (5/5 ítems mandatorios; Q2.1 diferido per spec). 50 tests verdes. Con todos los flags en default OFF/0, el resultado es **byte-idéntico** al actual, runtime por runtime.
