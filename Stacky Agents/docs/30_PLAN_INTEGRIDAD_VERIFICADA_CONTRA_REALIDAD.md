# 30 — Plan Integridad Verificada contra la Realidad: que ningún run salga condenado, referencie cosas inexistentes, ni declare éxito fantasma

**Fecha:** 2026-06-14
**Estado:** PROPUESTO (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 parciales), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (implementado salvo UI U2.1), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto), `docs/26_PLAN_MEMORIA_CONFIGURABLE_Y_DIRECTIVAS.md` (**implementado completo**), `docs/27_PLAN_MEJORAS_INVISIBLES_MOTOR.md` (**implementado salvo I2.2 diferido**), `docs/28_PLAN_MEJORAS_ALTO_IMPACTO_INVISIBLES.md` (PROPUESTO — lifecycle/escritura/telemetría), `docs/29_PLAN_CALIDAD_RESULTADO_A_LA_PRIMERA.md` (PROPUESTO — criterios/few-shot CLI/effort/repair semántico).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia `file:line`, diseño con archivos exactos, criterios de aceptación, tests TDD, salvaguarda de calidad, frontera de no-solapamiento y complejidad.

**Tesis (innegociable):** los planes previos cubren tres lados del motor — el **27** hace que **piense mejor** (qué entra al modelo: contexto/retrieval/routing/caché), el **28** que **no se ahogue ni pierda trabajo** (lifecycle/proceso/escrituras/telemetría) y el **29** que **el producto cumpla el encargo** (criterios, reuso de lo aprobado, esfuerzo a la medida — juicio **semántico**). Falta el cuarto lado, **determinista y de costo casi nulo**: que el run esté **anclado a la realidad** en sus bordes. Hoy un run puede **arrancar condenado** (sin acceso a ADO, sin `outputs_dir`, sin repo) y recién fallar de forma confusa 5 minutos y un costo de LLM después; puede producir un entregable que **referencia archivos o IDs que no existen** (la causa raíz documentada "crea archivos pero no la task" es exactamente eso: un ordinal/parent-id que no resuelve contra ADO); y puede **declarar éxito fantasma** — escribir el marker `consumed` "tarea creada" cuando en ADO no quedó nada. Ninguna de estas tres es un problema de *pensar mejor* (27), *sobrevivir* (28) ni *cumplir el criterio semántico* (29): son fallos de **verdad contra la realidad** —filesystem, repo, estado de ADO— que se chequean **sin LLM, en milisegundos**. Este plan los cierra **sin pedirle nada al operador**: el run que está condenado falla al instante con una razón clara (no gasta), el entregable no afirma cosas que no existen, y Stacky nunca reporta "hecho" para una task que no está. El TRABAJO es invisible; el RESULTADO se nota: menos runs gastados en vano, menos referencias alucinadas, y **cero éxitos fantasma**.

**"Invisible" NO significa "autónomo" (frontera dura, regla 11):** invisible quiere decir que el operador no configura ni ve el mecanismo. NO quiere decir que el sistema decida por él. **Cada run lo inició el operador.** Las acciones de este plan son **verificación determinista de pre/post-condiciones contra el mundo real**: chequear que las condiciones para correr existen *antes* de gastar el run, chequear que lo que el output afirma existir *existe*, y chequear que una escritura que el operador aprobó *realmente llegó* antes de marcarla consumida. Ninguna publica a ADO por su cuenta, ninguna re-lanza trabajo decidiendo por el humano, ninguna re-crea algo que el humano borró a propósito, y ninguna emite un juicio sobre el *contenido* del trabajo. Cada ítem trae su línea explícita **"Por qué NO viola rule 11"**.

**Calidad nunca se sacrifica (segundo eje innegociable):** todos los chequeos de este plan son **deterministas y aditivos**; o bien evitan gastar un run condenado (no hay output que degradar), o bien **agregan una señal de verdad** que solo puede mejorar el entregable (nunca lo empeora). No hay ningún ítem cuyo "ahorro" pueda producir un peor resultado. Cada ítem trae su línea **"Salvaguarda de calidad (y cómo se mide)"**.

---

## Relación con los planes 27/28/29 (qué se subsume, qué se reemplaza, qué queda fuera)

> **Estado verificado el 2026-06-14 contra el código** (`codex/subida-cambios-pendientes`). El 27 está implementado (seams `context_enrichment`, `llm_router`, `harness/complexity.py`, `harness/run_repair.py`); el 28 y el 29 están **propuestos** y reservan, respectivamente, el lifecycle/escritura/telemetría y la calidad-semántica del entregable. El 30 ocupa el espacio que ninguno toca: **la verificación determinista contra la realidad en los bordes del run** (pre-condiciones y post-condiciones vs filesystem/repo/ADO).

- **SUBSUME:** nada. No re-especifica ningún ítem de 27/28/29.
- **REEMPLAZA:** nada. Los ítems pendientes del 28 (R0-R2) y del 29 (Q0-Q2) siguen vigentes y no se tocan.
- **Eje de cada plan (frontera de no-solapamiento):**
  - **27** = *qué entra al modelo y cómo se cobra* (contexto/retrieval/routing-de-modelo/caché).
  - **28** = *que el proceso sobreviva y la escritura sea robusta* (zombie/stall/reap, validación **estructural** del body antes del POST, idempotencia de **comentarios**, telemetría de fallos).
  - **29** = *que el producto cumpla el encargo* (criterios de aceptación, few-shot, esfuerzo) — juicio **semántico vía LLM**.
  - **30** = *que el run esté anclado a la realidad*: precondiciones reales antes de gastar, referencias del output que **existen de verdad**, y escritura que **realmente llegó** antes de declararla hecha. Eje **determinista, cero LLM, cero costo de inferencia**. Es el eje *grounded-against-reality-per-token*.
- **Frontera fina declarada (tres verificaciones que parecen la del 28/29 pero son disjuntas):**
  1. **28/R1.2 (validación estructural del pending-task)** mira si el **body** está bien formado **antes** del POST (campos/ordinal). **30/G1.1** mira si la task **quedó creada de verdad en ADO** **después** del POST, **antes** de escribir el marker `consumed`. *Pre-write structure* vs *post-write truth*: disjuntos.
  2. **28/R1.3 (publicación idempotente)** evita **duplicar un comentario**. **30/G1.1** evita **declarar éxito de una task que no existe**. Operaciones (comentario vs task) y fallos (duplicado vs fantasma) distintos.
  3. **29/Q1.1 (pase correctivo de criterios, LLM)** corrige un fallo **semántico** de criterios de aceptación. **30/G1.2** detecta un fallo **factual y determinista** (una ruta/ID que no existe). El 30 **alimenta** el seam de reparación del 29/Q1.1 si está disponible; no lo re-implementa ni emite juicio semántico.
- **Frontera con el preflight existente:** `app.py::_log_completion_preflight` (`app.py:142-179`) ya chequea predicados reales (`outputs_dir`, PAT) **pero solo los LOGUEA al arrancar** (`app.py:345`, envuelto en `logger.exception(... continuando)`); los endpoints de diagnóstico (`api/tickets.py:150,181,194,208`, `api/diag.py:282`) los **reportan** read-only. El 30/G0.1 **reusa esos predicados** y los cablea como **gate antes de lanzar el run**; no inventa chequeos nuevos.
- **Frontera con la detección `stale_consumed` existente:** el desatascador ya **detecta y surface** el estado `stale_consumed` (`api/tickets.py:2460-2477,2500`) y existe remediación **manual** (`stale_consumed_resets` `tickets.py:66`, botón "Recrear Task borrada"). El 30/G1.1 ataca la **causa** (no escribir `consumed` sin verificar que ADO tiene la task) para que el estado fantasma **no se cree**; no re-implementa la detección ni auto-recrea lo que el humano borró.

---

## 1. Punto de partida: el sustrato de verificación que YA existe (no re-implementar)

Verificado contra el código el 2026-06-14. La lectura central: **los predicados de verdad ya existen, pero se usan para *reportar*, no para *gatear*** — se chequea que `outputs_dir`/repo/PAT existan, pero solo en logs y endpoints de diagnóstico; se marca `consumed` sin re-leer ADO; se valida el output por forma pero no se verifica que lo que referencia exista. El mayor valor de este plan es **cablear esos predicados como gates/post-checks**, no inventar.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Preflight de arranque (predicados reales: `outputs_dir`, repo, PAT) | `app.py:142-179` (`_log_completion_preflight`, warnings :160/:165/:175, `logger.exception(...continuando)` :179), invocado `app.py:345` | OK — **solo LOGUEA al arrancar; NO gatea ningún run** (D-G1) |
| Predicados de existencia en endpoints de diagnóstico | `api/tickets.py:150,181,194,208` (`repo_root_exists`, `outputs_dir_exists`, `outputs_dir.exists()`), `api/diag.py:282` | OK — **read-only, no gatean el lanzamiento** (D-G1) |
| Entrada de lanzamiento de run | `agent_runner.py:28` (`run_agent`), dispatch CLI `:52-63` (`_start_cli_runtime`), copilot crea exec row `:65` | **Sin gate de precondiciones** — arranca aunque esté condenado (D-G1) |
| Marca `consumed` del pending-task (status final "task creada") | `api/tickets.py:51` (`PENDING_TASK_STATUS_CONSUMED`), skip por consumed en watcher `services/output_watcher.py:956,994` | OK — **se marca sin re-verificar que la task quedó en ADO** (D-G2) |
| Auto-create de task desde el watcher (POST a create-child-task) | `services/output_watcher.py:998-1015` (arma body y POST), cuarentena por HTTP error `:1066` | OK — **confía en el POST; un id devuelto que no resuelve queda como éxito fantasma** (D-G2) |
| Detección + remediación manual de `stale_consumed` | `api/tickets.py:2460-2477,2500` (blocker + readiness), `tickets.py:66` (`stale_consumed_resets`), botón "Recrear Task borrada" | OK — **detecta y arregla a mano; no previene en el origen** (D-G2) |
| Post-run: contract validator (forma por agente) + confidence (heurística) | `harness/post_run.py:35` (`finalize_run`), `:54` (`import contract_validator`), `:62` (`validate(agent_type, output_text)`), `:69` (`confidence.score`) | OK — **valida FORMA y heurística; NO verifica que rutas/IDs referenciados existan** (D-G3) |
| Caché de lecturas ADO (27/I3.2) | `services/ado_read_cache.py` (singleton, invalidación en `mark_succeeded`) | OK — **el seam barato para verificar existencia de un work item sin pegarle a ADO de más** (lo reusan G0.1/G1.1) |
| Seam de reparación dirigida (29/Q1.1) + autocorrect/run_repair (forma) | `services/self_review.py`, `harness/run_repair.py`, `services/cli_autocorrect.py` | OK — **seam al que G1.2 puede enchufar una corrección de referencia factual** (no re-implementar) |
| Retry en el runner | claude `services/claude_code_cli_runner.py` (0 matches de retry/backoff), codex `services/codex_cli_runner.py:690` (solo autocorrect) | **No hay retry de run ante salida transitoria clasificada** (D-G4, opcional) |
| Telemetría de run + harness-health (H8) + DiagnosticsPage | `harness/telemetry.py:122`, `services/harness_health.py`, `frontend/.../DiagnosticsPage` (`HarnessHealthCard`) | OK — **no mide runs-condenados-evitados / éxito-fantasma-atrapado / referencias-no-ancladas** (D-G5); seam para exponer sin UI nueva |
| Capacidades por runtime | `harness/capabilities.py:21` (`CAPABILITIES`) | OK — seam para decidir por-runtime sin `if` dispersos |

**Restricciones vinculantes (idénticas a docs 22-29, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable); "solo Stacky escribe en ADO" = todo por el path de publicación existente (este plan **no agrega caminos de escritura**; solo **verifica** que la escritura llegó); mono-operador **sin RBAC** (`current_user()` es un header sin validar); claves de metadata existentes son contrato (**agregar, nunca renombrar**); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` (`services/harness_flags.py`) en el MISMO PR, default **OFF/0**, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → **validar por archivo de test** con el python del `.venv` (pin pywin32==306 roto en 3.13); vitest frontend NO instalado (UI: solo cambios que compilen con `tsc`, degradación con gracia, sin tests vitest nuevos obligatorios); **sin fallback silencioso entre runtimes** (claude/codex/copilot se cablean por separado); **sin deps npm/py nuevas** (todo con stdlib + los seams existentes); el build congelado no tiene FTS5 verificado (no introducirlo).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Cada acción es **verificación determinista contra la realidad** dentro del run que el operador lanzó: no decide trabajo, no publica, no re-crea lo borrado a propósito, no juzga contenido. El verdict humano y el path de publicación (U1.3/U2.2 del doc 23) quedan **intactos**.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía ni auto-intake.** Ningún run nace sin el operador. Verificar precondiciones o post-condiciones no decide trabajo: gatea/anota un run que el operador ya lanzó.
2. **No re-crea ni re-publica nada por su cuenta.** Detectar que una task no quedó en ADO **no** dispara una re-creación automática (eso podría pelear con un borrado deliberado del humano); solo **impide declarar éxito fantasma** y deja el estado accionable en la superficie que ya existe (desatascador). La re-creación sigue siendo decisión humana ("Recrear Task borrada").
3. **No agrega caminos de escritura a ADO ni cambia QUÉ/CUÁNDO se publica.** La única lectura nueva es de **existencia** (verificar que un work item resolvió), que reusa la caché del 27/I3.2.
4. **No expone perillas nuevas al operador.** Todos los flags son **internos**; la única superficie que cambia es la **DiagnosticsPage existente** (G2.1), que muestra *más* información de integridad sin pedir acción.
5. **No re-implementa el motor (27), el lifecycle (28) ni el juicio semántico (29).** No toca `context_enrichment`, ni el routing, ni el reap/stall, ni `run_repair`, ni `self_review`. G1.2 **alimenta** el seam de reparación del 29 si existe; no lo re-implementa.
6. **No emite juicios de contenido.** Todo chequeo es **determinista** (existe / no existe / resuelve / no resuelve). La calidad semántica es del 29.
7. **No introduce FTS5 ni deps nuevas.** Todo con stdlib + los predicados/caché/seams ya existentes.

---

## 3. Diagnóstico: dónde el run pierde resultado y plata por no verificar la realidad (con evidencia)

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-G1** | **Un run arranca aunque esté condenado; las precondiciones solo se loguean/reportan.** `run_agent` (`agent_runner.py:28`) dispatchea a `_start_cli_runtime` (`:52-63`) o crea la exec row (`:65`) **sin gate de precondiciones**. Los predicados de verdad ya existen pero solo **loguean al arrancar** (`app.py:142-179`, envuelto en `logger.exception(...continuando)` `:179`) o **reportan** read-only (`tickets.py:150,181,194,208`; `diag.py:282`). Si falta el PAT (con auto-create ON), no existe `outputs_dir`, o el repo no está, el run igual se lanza y falla confuso minutos y un costo de LLM después. | `agent_runner.py:28,52-63,65`; `app.py:142-179,345`; `tickets.py:150,181,194,208` | Runs gastados en vano (costo de LLM + slot ocupado); fallo tardío y confuso que el operador tiene que diagnosticar; latencia percibida alta para un fallo evitable en 2 segundos. |
| **D-G2** | **Se marca `consumed` ("task creada") sin verificar que la task quedó en ADO → éxito fantasma.** El auto-create POSTea (`output_watcher.py:998-1015`) y el flujo marca `consumed` (`tickets.py:51`; skip por consumed `output_watcher.py:956,994`) confiando en el POST. Si el POST "tuvo éxito" pero el id no resuelve, o la task se borró luego, queda un marker `consumed` sin task real. La detección existe **a posteriori** y **manual** (`stale_consumed` `tickets.py:2460-2477`; `stale_consumed_resets:66`; botón "Recrear"), pero **nada lo previene en el origen**. Es la causa raíz documentada ("crea archivos pero no la task" / "Stacky dice OK sin crear nada"). | `output_watcher.py:998-1015,956,994`; `tickets.py:51,66,2460-2477` | Tasks fantasma: Stacky reporta "hecho", el equipo no ve la task, el operador descubre tarde y remedia a mano. Tasa de éxito **efectiva** de creación por debajo de lo reportado. |
| **D-G3** | **El output se valida por forma, pero no se verifica que lo que referencia exista.** `finalize_run` (`post_run.py:35`) corre `contract_validator.validate(agent_type, output_text)` (forma por agente, `:62`) + `confidence.score` (heurística, `:69`). Ninguno chequea que las **rutas de archivo** referenciadas en contexto de lectura/modificación existan en el repo, ni que los **work-item IDs / parent-ids** resuelvan contra ADO. El mismatch ordinal-vs-ADO-id (la causa raíz documentada) es exactamente una referencia factual no anclada. | `post_run.py:35,54,62,69` | Entregables que citan archivos inexistentes o IDs equivocados pasan el gate de forma; el equipo los recibe con referencias rotas; reproceso humano para corregir lo que un chequeo determinista habría marcado. |
| **D-G4** | **No hay retry de run ante una salida transitoria clasificada del runner.** El runner claude no tiene retry/backoff (0 matches); codex solo reintenta por autocorrect (`codex_cli_runner.py:690`). El 27/I1.1 (`run_repair`) cubre output **vacío/malformado** y el 28/R1.1 el **stall**, pero un exit por causa **transitoria y recuperable** (no de contenido) termina como `failed` y el operador relanza a mano. | `claude_code_cli_runner.py` (sin retry), `codex_cli_runner.py:690`, `harness/run_repair.py` (solo vacío/malformado) | Runs que un único reintento acotado habría salvado caen a fallo → relanzamiento manual. *(Ítem opcional/diferido: requiere verificar la clasificación de exit-codes; el CLI ya maneja retries de API a su nivel.)* |
| **D-G5** | **No se mide la integridad: runs-condenados-evitados, éxito-fantasma-atrapado, referencias-no-ancladas.** La telemetría tiene costo/turnos/contract/confidence (`harness/telemetry.py:122`) y `harness_health` (H8) no cubre nada de estos chequeos. | `harness/telemetry.py:122`, `services/harness_health.py` | Sin un número, no se sabe cuántos runs se ahorraron ni cuántos éxitos fantasma se evitaron; no se afina lo que no se mide. |

**Lectura estratégica:** el 27 mejora lo que entra; el 28 que el proceso sobreviva; el 29 que el producto cumpla el criterio. El 30 cierra el cuarto lado, el más barato y el de mayor "verdad por token": el run no arranca condenado (G0.1), el output no afirma cosas inexistentes (G1.2), y Stacky nunca declara una task que no está (G1.1) — todo determinista, y medible (G2.1). El operador no toca nada: ve menos fallos confusos, menos tasks fantasma, y referencias que cierran.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo** y por riesgo. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: **G0** (fail-fast: el quick win de mayor leverage, reusa predicados existentes) → **G1** (los de mayor valor: matar el éxito fantasma y anclar las referencias) → **G2** (medir + opcional). Todos los flags default **OFF/0**; con todo en default, el comportamiento es **byte-idéntico** a hoy, runtime por runtime.

### FASE G0 — Fail-fast: no gastar un run condenado

---

#### G0.1 Gate de precondiciones determinista antes de lanzar el run — el ítem de mayor leverage

- **Ataca:** D-G1. Reusa los predicados de `_log_completion_preflight`/diagnóstico; NO inventa chequeos.
- **Problema + evidencia:** `run_agent` (`agent_runner.py:28`) lanza sin gate (`:52-63`, `:65`); los predicados de verdad solo loguean (`app.py:142-179`) o reportan (`tickets.py:150,181,194,208`).
- **Propuesta (mínima):** un helper `services/run_preflight.py::check(ticket, runtime, project) -> PreflightResult` que corre, **rápido y sin LLM**, los predicados **duros** ya existentes: `outputs_dir` existe y es escribible; repo presente si el runtime lo requiere; PAT presente **si** auto-create de tasks está habilitado; binario/CLI del runtime resolvible (`capabilities`). Se invoca al inicio de `run_agent` (antes de `_start_cli_runtime`/crear la exec row). Si **falla un predicado duro** → no se lanza: se crea (o marca) la execution como `failed` con `metadata["precondition_failure"]={check, detail}` (clave **nueva**, aditiva) y un mensaje accionable ("No se lanzó: falta PAT de ADO y auto-create está ON"). Predicados **blandos** (p. ej. plan de pruebas ausente) → **warning**, no bloquean. Sin fallback entre runtimes: cada runtime declara sus predicados duros en `capabilities`.
- **Impacto esperado:** **eficiencia** — runs condenados no se lanzan → 0 costo de LLM + slot libre; el fallo es **instantáneo** en vez de tardío y confuso. **Resultado** — el operador ve una razón clara y corrige la causa real, no un stacktrace ambiguo. Métrica: nº de `precondition_failure` (runs ahorrados) en G2.1; tiempo medio a fallo de un run condenado (de minutos a < 1s).
- **Por qué es invisible:** el operador no configura nada; en vez de un run colgado/confuso, recibe un mensaje claro al instante. Cero pasos nuevos.
- **Por qué NO viola rule 11:** gatear precondiciones reales no decide trabajo ni publica; es negarse a gastar un run que **no puede** funcionar. El operador igual decide relanzar tras corregir.
- **Salvaguarda de calidad (y cómo se mide):** solo bloquea por predicados **duros y objetivos** (existe/no existe, resoluble/no); los blandos solo avisan → **cero falsos bloqueos** de runs que podrían funcionar. Flag OFF → `run_agent` byte-idéntico (sin gate). Se mide con tests: precondición dura faltante → no se lanza + `precondition_failure`; todas presentes → se lanza igual que hoy; predicado blando → warning sin bloqueo.
- **Flag:** `STACKY_RUN_PREFLIGHT_GATE_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`.
- **TDD (`tests/test_run_preflight.py`):** PAT ausente + auto-create ON → bloqueado con `precondition_failure`; `outputs_dir` inexistente → bloqueado; repo ausente para runtime que lo exige → bloqueado; todo OK → `run_agent` procede; predicado blando ausente → warning; flag OFF → byte-idéntico. Mock de filesystem/ADO (sin binarios ni red reales).
- **Complejidad:** S/M.

---

### FASE G1 — Verdad contra la realidad: matar el éxito fantasma y anclar las referencias

---

#### G1.1 Verificación post-create de que la task existe en ADO antes de marcar `consumed` — el ítem de mayor valor

- **Ataca:** D-G2. EXTIENDE el path de auto-create; NO re-implementa la detección `stale_consumed` ni la validación estructural del 28/R1.2.
- **Frontera con lo existente (declarada):** 28/R1.2 valida el **body antes** del POST; el desatascador **detecta** `stale_consumed` **después** y a mano (`tickets.py:2460-2477`). Este ítem cubre el instante intermedio que ninguno atrapa: **justo después del POST, antes de escribir `consumed`**, confirmar que la task **quedó creada de verdad**.
- **Problema + evidencia:** el watcher POSTea (`output_watcher.py:998-1015`) y el flujo marca `consumed` (`tickets.py:51`; skip `output_watcher.py:956,994`) confiando en el POST; un id que no resuelve queda como éxito fantasma.
- **Propuesta (mínima):** antes de escribir el marker `consumed`, una **verificación de existencia determinista**: resolver el `task_ado_id` devuelto por el POST contra ADO (un read de existencia barato, **reusando la caché del 27/I3.2** `ado_read_cache`). Solo si el work item **resuelve** → se escribe `consumed` (con `metadata["create_verified"]={ado_id, verified_at}`, clave **nueva**). Si **no resuelve** → **no** se marca `consumed`: se cuarentena con telemetría (mismo path que `output_watcher.py:1066`) y el estado queda accionable en el desatascador (como hoy) — **sin** auto-recrear (eso es decisión humana). Sin fallback silencioso: si el read de verificación **falla por error transitorio** (no "no existe", sino "no se pudo verificar"), se cae al **comportamiento actual** (marca `consumed`) para no introducir falsos negativos — la verificación solo **previene** el fantasma confirmado, nunca empeora el camino feliz.
- **Impacto esperado:** **resultado** — Stacky deja de declarar tasks que no están; la tasa de éxito **reportada** = la **efectiva**. **Eficiencia** — el operador no descubre fantasmas tarde ni remedia a mano lo que se previno en el origen. Métrica: nº de `create_verified=false` atrapados (antes: éxito fantasma silencioso); caída de `stale_consumed` nuevos (G2.1).
- **Por qué es invisible:** el operador no verifica nada; simplemente deja de aparecer el caso "Stacky dijo hecho y no estaba". Cero pasos nuevos.
- **Por qué NO viola rule 11:** verificar que una escritura **aprobada por el operador** realmente llegó no decide trabajo ni publica nada nuevo; **no** re-crea lo que el humano pudo haber borrado a propósito. Solo se niega a **mentir** ("hecho") cuando la realidad lo contradice.
- **Salvaguarda de calidad (y cómo se mide):** la verificación es **determinista** (resuelve/no resuelve); ante duda transitoria, degrada al comportamiento actual (no bloquea de más); **nunca** auto-recrea (preserva la decisión humana). Flag OFF → se marca `consumed` como hoy (byte-idéntico). Se mide con tests: id que resuelve → `consumed` + `create_verified=true`; id que no resuelve → no `consumed` + cuarentena + telemetría; verificación con error transitorio → fallback a `consumed` (comportamiento actual); flag OFF → byte-idéntico.
- **Flag:** `STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED` (bool, default **false**) + `FLAG_REGISTRY`. Reusa `ado_read_cache` (27/I3.2) si está; si no, read best-effort.
- **TDD (`tests/test_verify_task_before_consumed.py`):** POST ok + id resuelve → `consumed` + `create_verified`; POST ok + id no resuelve → no `consumed` + cuarentena + contador; verificación lanza error de red → fallback a `consumed`; no auto-recrea nunca; flag OFF → byte-idéntico. Mock de ADO read y del path del watcher.
- **Complejidad:** M.

---

#### G1.2 Grounding determinista de las referencias del output (rutas/IDs que existen)

- **Ataca:** D-G3. EXTIENDE `finalize_run`; alimenta el seam de reparación del 29/Q1.1 si existe; NO emite juicio semántico ni re-implementa `contract_validator`.
- **Problema + evidencia:** `finalize_run` (`post_run.py:35`) corre `contract_validator.validate` (forma, `:62`) + `confidence.score` (heurística, `:69`); ninguno verifica que las rutas/IDs referenciados existan.
- **Propuesta (mínima):** un pase **determinista** `services/grounding.py::check_references(output_text, repo_root, ado_resolver) -> GroundingResult` invocado en `finalize_run` después del contract validator: (a) extrae rutas de archivo referenciadas **en contexto de lectura/modificación** (patrones como "modificar `X`", "en el archivo `Y`", "ver `Z`") y verifica que existan en el repo; (b) extrae work-item IDs / parent-ids y verifica que resuelvan (reusando `ado_read_cache`). Produce `metadata["grounding"]={unresolved_paths:[...], unresolved_ids:[...]}` (clave **nueva**). Si hay referencias no ancladas Y el seam de reparación del 29/Q1.1 está disponible Y queda presupuesto → enchufa un pase correctivo dirigido **solo** a las referencias rotas (reusa su transporte/budget; no agrega pases propios). Si Q1.1 no está → **anota** y baja la confianza (no bloquea). **Cero LLM** en el chequeo mismo.
- **Impacto esperado:** **resultado** — entregables sin rutas/IDs alucinados; menos reproceso humano por referencias rotas; ataca de raíz el mismatch ordinal-vs-id documentado. **Eficiencia** — el chequeo es microsegundos; corregir antes es más barato que el ida-y-vuelta humano. Métrica: tasa de referencias no ancladas por run (debe caer); % recuperado vía Q1.1 (G2.1).
- **Por qué es invisible:** el operador no revisa referencias; recibe entregables que "cierran". Cero pasos nuevos.
- **Por qué NO viola rule 11:** verificar existencia de lo referenciado no decide ni publica; si corrige, lo hace por el seam del 29 (una vez, contra hechos objetivos), y si no, solo anota.
- **Salvaguarda de calidad (y cómo se mide):** **solo** marca referencias en contexto que **implica existencia** (leer/modificar), **nunca** archivos que el output **propone crear** (cero falsos positivos sobre trabajo legítimo nuevo); ante ambigüedad, no marca. El chequeo es aditivo: en el peor caso anota y baja confianza, **nunca** degrada el output. Flag OFF → `finalize_run` byte-idéntico. Se mide con tests sobre fixtures: ruta inexistente en "modificar X" → marcada; ruta en "crear nuevo Y" → no marcada; id que no resuelve → marcado; output limpio → sin marcas; flag OFF → byte-idéntico.
- **Flag:** `STACKY_OUTPUT_GROUNDING_ENABLED` (bool, default **false**) + `STACKY_OUTPUT_GROUNDING_REPAIR` (bool, default **false**, exige 29/Q1.1).
- **TDD (`tests/test_output_grounding.py`):** detección de rutas/IDs no anclados; exclusión de archivos propuestos a crear; integración con el seam de Q1.1 (si presente, corrige; si no, anota + confidence↓); flag OFF → byte-idéntico. Mock de repo/ADO resolver.
- **Complejidad:** M.

---

### FASE G2 — Cerrar el loop (medir) + resiliencia opcional

---

#### G2.1 KPIs de integridad en harness-health (read-only, sin UI nueva)

- **Ataca:** D-G5. Extiende `harness_health` (H8) y la `HarnessHealthCard` existente; NO crea UI nueva.
- **Problema + evidencia:** la telemetría no mide integridad (`harness/telemetry.py:122`); `harness_health` no lo cubre.
- **Propuesta (mínima):** un bloque de **integridad** en `services/harness_health.py`, por proyecto y ventana, leyendo la metadata que G0.1/G1.1/G1.2 ya pueblan: `runs_condenados_evitados` (de `precondition_failure`), `exitos_fantasma_atrapados` (de `create_verified=false`), `tasa_referencias_ancladas` (de `grounding`), y `tasa_exito_real_creacion` (consumed **con** `create_verified=true` / intentos). Read-only.
- **Impacto esperado:** la integridad se vuelve un **número visible** en la pantalla que el operador/management ya consultan → se afina dónde invertir. Métrica: el propio dashboard.
- **Por qué es invisible:** se agrega a una card existente; cero pasos nuevos.
- **Por qué NO viola rule 11:** mostrar números no decide nada; es observabilidad.
- **Salvaguarda de calidad (y cómo se mide):** definiciones explícitas y testeadas; read-only puro; fuente ausente → degrada con gracia ("—"). Flag OFF → la card no agrega el bloque (byte-idéntico). Se mide con un test del endpoint con datos sintéticos.
- **Flag:** `STACKY_INTEGRITY_KPIS_ENABLED` (bool, default **false**).
- **TDD (`tests/test_harness_health_integrity.py`):** con runs sintéticos (condenados, fantasma atrapado, referencias no ancladas, creación verificada) → KPIs correctos por proyecto/ventana; fuente ausente → degrada; flag OFF → sin bloque nuevo.
- **Complejidad:** M.

---

#### G2.2 Retry de run acotado ante salida transitoria clasificada (opcional / diferido)

- **Ataca:** D-G4. Es el ítem **menos seguro** del plan (depende de clasificar exit-codes y de que el CLI no maneje ya el caso a su nivel) — se incluye marcado **opcional/diferido**, mismo criterio que el 29/Q2.1.
- **Problema + evidencia:** el runner claude no tiene retry (0 matches); codex solo autocorrect (`codex_cli_runner.py:690`); `run_repair` (27/I1.1) cubre vacío/malformado, no salida transitoria.
- **Propuesta (mínima, condicionada a verificación):** **primero** verificar si el exit del runner se puede **clasificar** de forma confiable como *transitorio recuperable* (no de contenido, no de criterio): p. ej. exit por red caída / arranque fallido del proceso, distinguible del exit normal. **Solo si** existe esa señal: un **único** reintento acotado del run (compartiendo el presupuesto duro de autocorrect/run_repair, sin sumar techo) antes de marcar `failed`, con `metadata["transient_retry"]={attempted, recovered}`. Si la clasificación **no** es barata/confiable → **no se implementa** (se documenta el descarte). Sin fallback entre runtimes: claude y codex se cablean por separado.
- **Impacto esperado:** **eficiencia/resultado** — runs salvables por un reintento dejan de caer a relanzamiento manual. Métrica: `transient_retry.recovered/attempted` (G2.1).
- **Por qué es invisible:** el operador no relanza; el reintento ocurre dentro del run que lanzó.
- **Por qué NO viola rule 11:** reintentar **una vez** un run que el operador ya lanzó, ante un fallo de infraestructura, no decide trabajo ni publica; es lo que el operador haría al relanzar.
- **Salvaguarda de calidad (y cómo se mide):** **solo** reintenta ante causa **clasificada como transitoria** (nunca ante fallo de contenido/criterio, que sigue su flujo a `needs_review`); presupuesto duro de 1, compartido. Flag OFF → byte-idéntico. Se mide con tests: exit transitorio simulado → un reintento; exit de contenido → no reintenta; recupera → `completed`; no recupera → `failed`; flag OFF → byte-idéntico.
- **Flag:** `STACKY_TRANSIENT_RUN_RETRY_ENABLED` (bool, default **false**) + `STACKY_TRANSIENT_RUN_RETRY_MAX` (int, default 1).
- **TDD (`tests/test_transient_run_retry.py`):** clasificación + un reintento; no reintenta por contenido; presupuesto compartido (no se suma a autocorrect/run_repair); flag OFF → byte-idéntico.
- **Complejidad:** M (condicionada; **diferir** si la clasificación de exit no es confiable y barata).

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | **G0.1** Gate de precondiciones (fail-fast) | S/M | **Muy alto (runs ahorrados + claridad)** | Bajo (solo predicados duros, flag OFF) | predicados existentes (en código) |
| 2 | **G1.1** Verificación post-create (mata éxito fantasma) | M | **Muy alto (ataca causa raíz documentada)** | Medio (toca path de auto-create → fallback a actual ante duda) | `ado_read_cache` (27/I3.2, en código) |
| 3 | **G1.2** Grounding determinista de referencias | M | **Alto (referencias que cierran)** | Bajo/Medio (solo contexto de existencia; aditivo) | `finalize_run` (en código); 29/Q1.1 opcional |
| 4 | **G2.1** KPIs de integridad | M | Alto (cierra el loop) | Bajo (read-only) | G0.1/G1.1/G1.2 pueblan datos |
| 5 | **G2.2** Retry transitorio (opcional/diferido) | M | Medio (si la clasificación es confiable) | Medio (depende de clasificar exit) | run_repair/autocorrect budget; verificación previa |

**Reglas de implementación (las 7 del doc 22 + las de frontend del doc 23 aplican íntegras):** TDD; validar **por archivo de test** con el python del `.venv` (suite contaminada; pin pywin32==306 roto en 3.13); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves **nuevas** (`precondition_failure`, `create_verified`, `grounding`, `transient_retry`, KPIs de integridad); default **OFF/0** (retro-compat **byte-idéntica** — con todos los flags en default, el resultado es EXACTAMENTE el de hoy, runtime por runtime); ADO solo por los caminos existentes (la única lectura nueva es de **existencia**, que reusa la caché 27/I3.2); **sin fallback silencioso entre runtimes**; sin deps npm/py nuevas; UI (DiagnosticsPage) degrada con gracia y compila con `tsc` (vitest no instalado: sin tests vitest obligatorios).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Doctrina: (a) cada acción es **verificación determinista contra la realidad** dentro de un run que el operador lanzó; (b) lo que se chequea es existencia/resolución objetiva (precondiciones, rutas, IDs, task creada), nunca contenido; (c) la única "corrección" (G1.2) reusa el seam del 29/Q1.1 contra hechos objetivos, una vez; (d) **nada re-crea lo borrado por el humano** ni publica solo; (e) lo que mide (G2.1) produce números, no mutaciones. Cada ítem trae su línea "Por qué NO viola rule 11".

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (que NO configura ni ve estos mecanismos)
- **Hoy:** a veces lanza un run que falla minutos después con un error confuso (faltaba el PAT, no estaba el `outputs_dir`); a veces Stacky dice "task creada" y la task no está en ADO, y lo descubre tarde; a veces el entregable cita un archivo o un ID que no existe.
- **Después (sin tocar nada):** un run condenado falla al instante con una razón clara y accionable (no gasta); Stacky nunca reporta una task que no quedó en ADO; los entregables no citan rutas/IDs inexistentes. No ve ninguna perilla nueva: solo nota que Stacky "no se equivoca con los hechos".

### Desarrollador / equipo (que vive en ADO)
- **Hoy:** a veces faltan tasks que Stacky reportó como hechas; a veces los artefactos citan referencias rotas.
- **Después:** la tasa de éxito reportada coincide con la efectiva (verificación post-create) y las referencias del entregable existen (grounding) — sin cambios en cómo Stacky escribe.

### Management
- **Hoy:** no hay número de integridad; los fallos "de hechos" son anecdóticos.
- **Después:** runs-condenados-evitados, éxitos-fantasma-atrapados, tasa de referencias ancladas y tasa de éxito **real** de creación en la DiagnosticsPage existente (G2.1) — la integridad se vuelve medible sin sumar trabajo operativo.

---

## 7. Ventaja competitiva: por qué anclar a la realidad gana

1. **Un CLI suelto miente sobre hechos; el arnés verifica.** Un CLI suelto declara "listo" sin confirmar que la task quedó en ADO ni que la ruta que citó existe. Stacky, dentro del run que el humano lanzó, **verifica contra la realidad** antes de afirmar — sin cruzar la línea de la autonomía (no re-crea ni publica solo).
2. **No gastar un run condenado es el ahorro más limpio.** Fallar en 1 segundo por una precondición real, en vez de gastar una inferencia completa para fallar confuso, baja costo y latencia **sin tocar la calidad de un solo entregable** (no había entregable que degradar).
3. **La verdad por token es barata y decisiva.** Los chequeos son deterministas (microsegundos, cero LLM); previenen la clase de fallo que más erosiona la confianza del operador —el "Stacky dijo que sí y no era"— que ningún modelo, por bueno que sea, evita por su cuenta.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo | Fuente |
|---|---|---|---|
| Runs condenados que igual se lanzan | ocurren (fallo tardío) | ~0 (fail-fast) | `precondition_failure` (G0.1) + G2.1 |
| Tiempo a fallo de un run condenado | minutos + costo LLM | < 1s, sin costo | telemetría G0.1 |
| Éxitos fantasma (consumed sin task real) | invisibles hasta tarde | ~0 (verificados) | `create_verified` (G1.1) + G2.1 |
| `stale_consumed` nuevos | aparecen y se reparan a mano | caen (prevención en origen) | desatascador + G2.1 |
| Referencias del output no ancladas (rutas/IDs) | pasan el gate de forma | detectadas y/o corregidas | `grounding` (G1.2) + G2.1 |
| Tasa de éxito **real** de creación (verificada) | = tasa reportada (optimista) | = tasa efectiva (honesta) | G2.1 |
| Calidad de entregables tras los chequeos | n/a | **no debe caer** (aditivos) | G2.1 + KPIs del 29/Q2.2 |
| Perillas nuevas que el operador debe tocar | — | **cero** (flags internos, default OFF) | — |

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El gate de precondiciones (G0.1) bloquea un run que sí podía correr | Solo predicados **duros y objetivos**; los blandos solo avisan; flag OFF = comportamiento actual. Tests de no-bloqueo de runs válidos. |
| La verificación post-create (G1.1) marca como fantasma una task real por un error transitorio de lectura | Distingue "no existe" de "no se pudo verificar"; ante duda transitoria, **fallback** a marcar `consumed` (comportamiento actual); nunca auto-recrea. |
| El grounding (G1.2) marca como rota una ruta que el output **propone crear** | Solo marca referencias en contexto que **implica existencia** (leer/modificar); excluye archivos propuestos a crear; ante ambigüedad no marca. Tests de exclusión. |
| El grounding agrega lecturas caras a ADO/repo | Reusa `ado_read_cache` (27/I3.2) y el repo local; chequeo en microsegundos; no toca el camino feliz si está OFF. |
| Confundir G1.1 con la validación estructural del 28/R1.2 o la idempotencia del 28/R1.3 | Frontera declarada: R1.2 = body pre-POST; R1.3 = comentario duplicado; G1.1 = task realmente creada post-POST. Disjuntos. |
| El retry transitorio (G2.2) reintenta un fallo de contenido o duplica trabajo del CLI | Opcional/diferido; solo ante causa **clasificada como transitoria**; presupuesto duro compartido; si la clasificación no es confiable, **no se implementa**. |
| Doble lectura de ADO entre G0.1 y G1.1 | Ambas reusan `ado_read_cache`; G0.1 chequea presencia de credencial/predicado, G1.1 resuelve un id puntual — sin duplicar el mismo read. |

---

## 10. Roadmap por fases (estado)

| Fase | Ítem | Estado |
|---|---|---|
| G0 | G0.1 Gate de precondiciones (fail-fast) | PROPUESTO |
| G1 | G1.1 Verificación post-create (mata éxito fantasma) | PROPUESTO |
| G1 | G1.2 Grounding determinista de referencias | PROPUESTO |
| G2 | G2.1 KPIs de integridad | PROPUESTO |
| G2 | G2.2 Retry transitorio (opcional/diferido) | PROPUESTO |

**Estado global:** PROPUESTO (0/5 implementado al 2026-06-14). Con todos los flags en default OFF/0, el comportamiento es **byte-idéntico** al actual, runtime por runtime. El plan cierra el cuarto lado del motor — la **integridad verificada contra la realidad** en los bordes del run — con chequeos **deterministas, cero LLM, cero fricción para el operador**, reusando los predicados/caché/seams que 27/28/29 dejaron en el código sin re-implementar ninguno.
