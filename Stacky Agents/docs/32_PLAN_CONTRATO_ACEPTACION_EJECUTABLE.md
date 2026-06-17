# 32 — Plan Contrato de Aceptación Ejecutable: derivar la Definición de Hecho como prueba ejecutable e INDEPENDIENTE antes del run, converger contra ella y gatear ejecutándola — rompiendo la circularidad del auto-examen

**Fecha:** 2026-06-15
**Estado:** PROPUESTO (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 parciales), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (implementado salvo UI U2.1), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto), `docs/26_PLAN_MEMORIA_CONFIGURABLE_Y_DIRECTIVAS.md` (**implementado completo**), `docs/27_PLAN_MEJORAS_INVISIBLES_MOTOR.md` (**implementado salvo I2.2 diferido**), `docs/28_PLAN_MEJORAS_ALTO_IMPACTO_INVISIBLES.md` (PROPUESTO — lifecycle/escritura/telemetría), `docs/29_PLAN_CALIDAD_RESULTADO_A_LA_PRIMERA.md` (PROPUESTO — criterios/few-shot CLI/effort/repair **semántico**), `docs/30_PLAN_INTEGRIDAD_VERIFICADA_CONTRA_REALIDAD.md` (PROPUESTO — preflight/post-create/grounding **determinista de existencia**), `docs/31_PLAN_VERIFICACION_EJECUTABLE_ENTREGABLE.md` (PROPUESTO — ejecutar los verificadores que el proyecto **ya tiene** sobre lo producido).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia `file:line`, diseño con archivos exactos, criterios de aceptación, tests TDD, salvaguarda de calidad, frontera de no-solapamiento y complejidad.

**Tesis (innegociable):** los planes previos cubren **cinco lados del motor** — el **27** hace que **piense mejor** (qué entra al modelo: contexto/retrieval/routing/caché), el **28** que **no se ahogue ni pierda trabajo** (lifecycle/proceso/escrituras/telemetría), el **29** que **el producto cumpla el encargo** según un juicio **semántico vía LLM** (criterios de aceptación en prosa, inyectados como guía y corregidos por LLM), el **30** que **el run esté anclado a la realidad** por **existencia determinista** en los bordes, y el **31** que **lo producido funcione** **ejecutando los verificadores que el proyecto YA tiene** sobre el artefacto. **Los cinco actúan DESPUÉS de que el agente trabajó** (verificación post-hoc) y **ninguno define, ANTES del run, qué significa "hecho" de forma ejecutable e independiente del agente.** Ese es el sexto lado, y el que un ingeniero senior hace por instinto antes de tocar una línea: **escribir la prueba que el trabajo debe pasar — primero.** Hoy el blanco del run es difuso: el ticket llega como prosa, el 29 inyecta sus criterios **como texto** (el agente los interpreta), y el 31 ejecuta los tests que **el propio agente** escribió junto con el código — **el alumno se pone su propio examen.** Ese examen puede ser real pero alineado a la (posiblemente errónea) interpretación del agente, o trivialmente fácil; el guard anti-verde-falso del 31 atrapa el test **vacío**, pero no el test **real-pero-laxo** ni la **circularidad** de fondo. Este plan cierra el sexto lado **sin pedirle nada al operador**: del mismo ticket que el operador seleccionó, **deriva una Definición de Hecho EJECUTABLE e independiente** (un puñado de chequeos concretos y corribles), la **valida deterministamente** —el chequeo generado debe **fallar en rojo contra el repo sin tocar** (propiedad red-green: un test que ya pasa antes de trabajar no exige nada)—, la **inyecta como el objetivo explícito del run** (el agente trabaja test-first contra un blanco concreto), y al terminar la **ejecuta como gate** (reusando el motor del 31). Si no se cumple, **un único** pase correctivo dirigido por la salida del chequeo en rojo; si no recupera, `needs_review` con el contrato y los chequeos fallidos a la vista. El LLM **propone** el examen; lo que **manda** es la **ejecución determinista** del examen, y el examen solo cuenta si **probadamente exige** la conducta nueva. El TRABAJO es invisible; el RESULTADO se nota: el run converge a un "hecho" concreto en vez de a un blanco difuso, el verde deja de ser auto-otorgado, y el verdict humano se toma sobre "cumple 4/4 criterios ejecutables derivados del ticket" — **sin sacrificar calidad y sin sacar al humano del lazo.**

**"Invisible" NO significa "autónomo" (frontera dura, regla 11):** invisible quiere decir que el operador no configura ni ve el mecanismo. NO quiere decir que el sistema decida por él. **Cada run lo inició el operador.** Las acciones de este plan ocurren **dentro de ese run**: derivar del ticket una Definición de Hecho ejecutable (lo que el ticket **ya pide**, traducido a algo corrible), trabajar contra ella, y al final **ejecutar** ese examen — exactamente lo que un dev senior haría (escribir el test de aceptación, hacerlo pasar). Ninguna acción publica a ADO por su cuenta, ninguna transiciona el work item, ninguna decide trabajo nuevo, ninguna oculta un fallo: ante fallo no recuperable, el entregable va a `needs_review` con el contrato y los chequeos fallidos adjuntos, y **el operador conserva la decisión.** El contrato es una **traducción** del encargo del operador, no una invención de trabajo. Cada ítem trae su línea explícita **"Por qué NO viola rule 11"**.

**Calidad nunca se sacrifica (segundo eje innegociable):** el riesgo único y obvio de "generar el examen con un LLM" es que el examen esté **mal** (mide lo que no es) o sea **laxo** (pasa trivialmente). Este plan lo neutraliza con un **juez determinista del propio examen**: (a) cada chequeo generado se corre contra el **baseline sin tocar** y **solo se conserva si falla en rojo** (si ya pasa, es vacuo → se descarta) — garantía ejecutable de que el chequeo **constriñe** algo real; (b) el guard anti-verde-falso del 31/E1.2 se aplica al chequeo **generado** (debe tener un `assert` real); (c) si **ningún** chequeo sobrevive a esa validación, el contrato es `n/a` y se cae a 29 (semántico) + 31 (ejecutable de lo existente) — **nunca** se gatea con un contrato de baja confianza; (d) el contrato es **inmutable durante el run**: el agente satisface el blanco independiente, no uno ablandado. La derivación es el único gasto extra: **acotada** por complejidad, **gated**, **annotate-first** para medir ROI antes de gatear, y **reusa** los criterios del 29 si están (traducir prosa→ejecutable es más barato que re-leer el ticket). No hay ningún ítem cuyo "ahorro" pueda producir un peor resultado. Cada ítem trae su línea **"Salvaguarda de calidad (y cómo se mide)"**.

---

## Relación con los planes 27/28/29/30/31 (qué se subsume, qué se reemplaza, qué queda fuera)

> **Estado verificado el 2026-06-15 contra el código** (`codex/subida-cambios-pendientes`). El 27 está implementado (seams `context_enrichment.enrich_blocks` `services/context_enrichment.py:34`, llamado en ambos runners CLI `codex_cli_runner.py:310` y `claude_code_cli_runner.py:384`; `harness/complexity.py`; `harness/run_repair.py`; `llm_router`). El `self_review` del 29 ya existe en código (`services/self_review.py:43` `_resolve_criteria`, `:60` `review_artifact`, `:130` `apply_to_execution`) aunque el grueso del 29 está **propuesto**. El 28/30/31 están **propuestos**. El 32 ocupa el espacio que ninguno toca: **definir, ANTES del run, una Definición de Hecho ejecutable e independiente del agente, y converger/gatear contra ella.**

- **SUBSUME:** nada. No re-especifica ningún ítem de 27/28/29/30/31.
- **REEMPLAZA:** nada. Los ítems pendientes del 28 (R0-R2), 29 (Q0-Q2), 30 (G0-G2) y 31 (E0-E2) siguen vigentes y no se tocan.
- **Eje de cada plan (frontera de no-solapamiento) — el 32 es el ÚNICO que actúa sobre el BLANCO antes del run:**
  - **27** = *qué entra al modelo y cómo se cobra* (contexto/retrieval/routing-de-modelo/caché). **Post-hoc: no.** **Define el blanco: no.**
  - **28** = *que el proceso sobreviva y la escritura sea robusta*. Define el blanco: no.
  - **29** = *que el producto cumpla el encargo* — criterios de aceptación en **prosa**, juicio **semántico vía LLM**, corrección **semántica**. Inyecta los criterios como **texto guía**; el juez es un **LLM**. **Post-hoc el juicio; el blanco es prosa, no ejecutable.**
  - **30** = *que el run esté anclado a la realidad por existencia* — precondiciones de **entorno**, rutas/IDs que **existen**. Determinista, **estático**. **Post-hoc (salvo el preflight de entorno, que NO define qué es "hecho" sino si "se puede correr").**
  - **31** = *que lo producido FUNCIONE* — ejecuta los verificadores que el proyecto **ya tiene** (incluidos los tests que **el propio agente** escribió). Determinista, **dinámico**. **Post-hoc. Ejecuta el examen existente; no lo define ni garantiza su independencia.**
  - **32** = *definir el examen ejecutable e independiente ANTES del run, converger contra él y gatear ejecutándolo*. El LLM **propone** el examen; la **ejecución determinista** lo valida (fail-red on baseline) y lo hace cumplir. Es el eje *definition-of-done-as-executable-independent-contract-per-token* — el único **pre-run + test-first** de toda la línea.
- **Frontera fina declarada (cuatro cosas que parecen del 29/31 pero son disjuntas):**
  1. **29/Q0.1 (inyección de criterios)** inyecta los criterios del ticket **como prosa** en el briefing; el agente los **lee e interpreta**, y un **LLM** juzga si se cumplieron. **32/A0.1+A1.1** derivan del ticket un chequeo **EJECUTABLE** (un test corrible / un schema / un comando con salida esperada), lo inyectan como **el blanco**, y lo hacen cumplir por **ejecución determinista**. *Prosa-juzgada-por-LLM* vs *examen-ejecutable-juzgado-por-ejecución*: disjuntos. (El 32 **reusa** el extractor de criterios del 29 como insumo si está; traduce prosa→ejecutable.)
  2. **31/E0.1 (motor ejecutable)** corre los verificadores que **ya existen** en el proyecto (config detectable) o que **el agente escribió**. **32/A0.1** **genera** el chequeo que **no existía** para la conducta nueva del ticket y prueba que **falla en rojo** antes de trabajar. *Correr-lo-existente* vs *generar-y-validar-lo-faltante*: disjuntos. El 32 **reusa el motor del 31** para ejecutar su contrato (dependencia declarada), no re-implementa el runner.
  3. **31/E1.2 (guard anti-verde-falso)** verifica que **los tests que el agente escribió** no estén vacíos. **32/A0.1+A1.2** garantizan que **el contrato INDEPENDIENTE** (derivado antes y fuera del agente) **no sea vacuo** (fail-red on baseline) y **no sea ableado** (inmutable durante el run). *El-test-propio-del-agente-no-vacío* vs *el-examen-independiente-no-vacuo-y-no-manipulado*: disjuntos. El 31 mitiga la circularidad a medias (atrapa el test vacío); el 32 **la rompe de raíz** (el examen lo define alguien que no es el agente, antes de que trabaje).
  4. **30/G0.1 (preflight de entorno)** chequea, antes del run, que **se puede correr** (PAT, `outputs_dir`, repo). **32/A0.1** chequea, antes del run, **qué significa que esté hecho** (la Definición de Hecho ejecutable). *Pre-condición-de-entorno* vs *definición-del-blanco*: disjuntos.
- **Frontera con el seam de reparación (27/31/29):** `run_repair` (27/I1.1) dispara por **forma**; 31/E1.1 por **fallo ejecutable de un verificador existente**; 29/Q1.1 por **criterio semántico (LLM)**. **32/A1.1** dispara por **fallo ejecutable del contrato derivado** (un chequeo del examen, en rojo). El log del chequeo fallido **es** el prompt correctivo. **Comparten el presupuesto** de reparación (mismo techo por run); no se re-implementa el transporte.
- **Frontera con el motor de ejecución del 31:** el 32 **depende** de `services/exec_verification.py` (31/E0.1) para correr su contrato. Si el 31 aún no está implementado, A0.1/A1.1 ejecutan **solo** su conjunto reducido de chequeos generados por el **mismo** patrón `subprocess`+`cwd` que los runners ya usan (`claude_code_cli_runner.py:2003` `_resolve_cwd`, `:643` `cwd=...`), **sin deps nuevas**; cuando el 31 entre, el 32 conmuta al motor compartido (caché/short-circuit/sandbox/budget) sin re-trabajo.

---

## 1. Punto de partida: el sustrato que YA existe (no re-implementar)

Verificado contra el código el 2026-06-15. La lectura central: **el blanco del run es difuso y el examen lo escribe el propio agente.** Existe TODO lo necesario para definir un examen ejecutable e independiente sin inventar: un extractor de criterios reusable, el seam compartido de inyección al prompt (los 3 runtimes), el patrón `subprocess`/`cwd` (y, cuando entre el 31, su motor de ejecución), el seam de reparación con presupuesto, el post-run donde gatear, y las superficies de verdict/health para mostrar y medir. El mayor valor de este plan es **derivar+validar+hacer-cumplir el examen ejecutable**, no inventar maquinaria.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Extractor de criterios de aceptación del ticket (insumo del contrato) | `services/self_review.py:43` (`_resolve_criteria` lee `Microsoft.VSTS.Common.AcceptanceCriteria`), `:60` (`review_artifact`), `:130` (`apply_to_execution`) | OK — **existe y es reusable; produce prosa, no un examen ejecutable** (D-A1). Insumo de A0.1. |
| Seam compartido de inyección al prompt (los 3 runtimes) | `services/context_enrichment.py:34` (`enrich_blocks`), llamado en `codex_cli_runner.py:310` y `claude_code_cli_runner.py:384` (copilot vía su path) | OK — **el lugar correcto para inyectar el contrato como BLANCO sin tocar cada runner** (seam de A1.1) |
| Workspace real + patrón `subprocess`/`cwd` (donde se valida el baseline y se corre el contrato) | `services/claude_code_cli_runner.py:2003` (`_resolve_cwd`), `cwd` `:643,665`; `services/codex_cli_runner.py` (mismo patrón) | OK — **el `cwd` con la toolchain del proyecto; nada deriva ni corre un examen ahí** (D-A1). Lo reusa A0.1/A1.1. |
| Motor de verificación ejecutable (31/E0.1, dependencia para ejecutar el contrato) | `services/exec_verification.py` (PROPUESTO en doc 31) | **No existe aún** — el 32 lo reusa cuando entre; mientras tanto corre su contrato reducido por `subprocess` (sin deps nuevas) |
| Guard anti-verde-falso (31/E1.2, reusado sobre el chequeo GENERADO) | `tests`/`fake_green_guard` (PROPUESTO en doc 31) | **No existe aún** — A0.1 reusa su lógica (AST stdlib) para validar que el chequeo generado tenga `assert` real |
| Post-run unificado: contract gate (forma) + confidence (heurística) + status final | `harness/post_run.py:35` (`finalize_run`), `:62` (`contract_validator.validate`, forma por agente), `:69` (`confidence.score`), `:76` (gate → `needs_review`) | OK — **valida FORMA y heurística; no ejecuta un examen derivado del ticket** (D-A2). Seam donde A1.1 ejecuta el contrato y gatea (post-contrato, pre-status). |
| Wiring del self-review en el cierre | `services/agent_completion_internal.py:155-165` (`self_review.apply_to_execution`) | OK — el path donde el contrato se evalúa como red final post-close sin re-costo (reusa el resultado cacheado de A1.1) |
| Seam de reparación dirigida + presupuesto compartido | `harness/run_repair.py` (27/I1.1), `services/cli_autocorrect.py`, `services/codex_autocorrect.py`; seams de 29/Q1.1 y 31/E1.1 | OK — **transporte y presupuesto reusables; ninguno se dispara por un chequeo del contrato en rojo** (D-A3) |
| Estimación de complejidad determinística (27/I0.2) | `harness/complexity.py::estimate_complexity` → `S/M/L/XL` | OK — seam para acotar cuántos chequeos/cuánto presupuesto de derivación por dificultad (un `S` no merece un contrato grande) |
| Capacidades por runtime (resume/stdin) | `harness/capabilities.py:21` (`CAPABILITIES`) | OK — seam para decidir el pase correctivo por-runtime sin `if` dispersos |
| Cap duro de modelo | `services/llm_router.py` (`clamp_model`, nunca opus/fable) | OK — la derivación del contrato (1 llamada LLM) corre **bajo el clamp** |
| Verdict humano y vista del entregable (23/U1.3) | flujo de publicación `agent_completion_internal.py`, UI de revisión (doc 23) | OK — **el operador juzga sin ver una Definición de Hecho ejecutable cumplida/incumplida** (D-A4); seam de A2.1 |
| Telemetría de run + harness-health (H8) + DiagnosticsPage | `harness/telemetry.py:122`, `services/harness_health.py`, `frontend/.../DiagnosticsPage` (`HarnessHealthCard`) | OK — **no mide contrato-derivado / cumplido-a-la-primera / vacuo-descartado** (D-A5); seam de A2.2 |
| Flags + registro | `config.py`, `services/harness_flags.py` (`FLAG_REGISTRY`) | OK — patrón de flag interno default OFF, mismo PR |

**Restricciones vinculantes (idénticas a docs 22-31, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable; la derivación del contrato corre bajo el clamp); "solo Stacky escribe en ADO" = todo por el path de publicación existente (este plan **no agrega caminos de escritura**; deriva/ejecuta un examen read-only sobre el workspace local); mono-operador **sin RBAC** (`current_user()` es un header sin validar); claves de metadata existentes son contrato (**agregar, nunca renombrar**); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` en el MISMO PR, default **OFF/0**, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → **validar por archivo de test** con el python del `.venv` (pin pywin32==306 roto en 3.13); vitest frontend NO instalado (UI: solo cambios que compilen con `tsc`, degradación con gracia, sin tests vitest nuevos obligatorios); **sin fallback silencioso entre runtimes** (claude/codex/copilot se cablean por separado); **sin deps npm/py nuevas** (la derivación usa el LLM ya configurado; la ejecución usa el motor del 31 o `subprocess` con la toolchain del proyecto); el build congelado no tiene FTS5 verificado (no introducirlo).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Cada acción es **traducir el encargo del operador a un examen ejecutable y hacerlo cumplir** dentro del run que él lanzó, antes de presentar: no decide trabajo nuevo (el contrato deriva del ticket que el operador seleccionó), no publica, no transiciona ADO, no oculta fallos. Ante fallo no recuperable, degrada a `needs_review` con el contrato y los chequeos fallidos; el verdict humano y el path de publicación (U1.3/U2.2 del doc 23) quedan **intactos**.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía ni auto-intake.** Ningún run nace sin el operador. Derivar la Definición de Hecho del ticket que él seleccionó no decide trabajo: es traducir su encargo a algo verificable, dentro del run que él lanzó.
2. **No publica ni transiciona ADO por su cuenta, ni cambia QUÉ/CUÁNDO se publica.** El verdict humano no se toca. Un contrato cumplido **no** auto-aprueba ni auto-publica; uno incumplido **no** se descarta solo: va a `needs_review` con el contrato y el log del chequeo en rojo, y el operador decide. El examen **nunca** oculta un fallo.
3. **No inventa requisitos.** El contrato es una **traducción** del ticket (y de los criterios del 29 si están) a forma ejecutable; cada chequeo lleva una **traza** a la cláusula del ticket que codifica. Si una cláusula no se puede traducir a algo ejecutable con confianza → **no** se genera ese chequeo (queda para el 29 semántico). No se agregan exigencias que el ticket no pide.
4. **No gatea con un examen no confiable.** Un chequeo generado que **pasa en el baseline** (vacuo) se **descarta**; uno sin `assert` real se descarta; si **ningún** chequeo sobrevive → contrato `n/a`, sin gate (cae a 29+31). El gate solo existe sobre chequeos **probadamente exigentes**.
5. **No ejecuta código arbitrario sin contención.** El baseline-check y el gate corren con `cwd` acotado al workspace, **timeout duro**, **presupuesto**, **sin red**, sin mutar el repo fuera de un build-dir temporal. Reusa la contención del 31/E0.1; si el 31 no está, replica sus límites. Un chequeo no contenible no se cablea.
6. **No re-implementa el motor del 31, el `run_repair` (27), el autocorrect ni el juicio semántico del 29.** A1.1 **reusa** el motor de ejecución (31) y comparte el presupuesto de reparación; la novedad es **derivar el examen y disparar por su rojo**.
7. **No emite juicios de contenido en el gate.** El gate es pass/fail **objetivo de la ejecución** del contrato. La calidad semántica sigue siendo del 29; el 32 le da al 29 un blanco más nítido, no lo reemplaza.
8. **No expone perillas nuevas al operador.** Todos los flags son **internos**. Las únicas superficies que cambian son el **bloque de contrato en la vista de verdict** que el operador ya abre (A2.1) y la **DiagnosticsPage existente** (A2.2) — ambas muestran *más verdad*, sin pedir acción.
9. **No introduce FTS5 ni deps nuevas.** Todo con stdlib + el LLM ya configurado (derivación) + el motor del 31 o `subprocess` con la toolchain del proyecto (ejecución).

---

## 3. Diagnóstico: dónde el resultado deja calidad (y plata) sobre la mesa por no definir el examen primero (con evidencia)

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-A1** | **El blanco del run es difuso: no hay Definición de Hecho ejecutable.** Los criterios del ticket existen como **prosa** y su único consumidor es el self-review **al final** (`self_review.py:43` `_resolve_criteria`); aun con el 29/Q0.1, se inyectan como **texto** que el agente interpreta (no como un examen corrible). El workspace con toolchain y el patrón `subprocess` existen (`claude_code_cli_runner.py:2003,643`) pero **nada deriva del ticket un chequeo ejecutable** que el agente deba pasar. | `self_review.py:43`; `context_enrichment.py:34` (inyecta prosa); `claude_code_cli_runner.py:2003,643` (workspace ocioso para esto) | El agente apunta a un blanco difuso: produce de más/de menos, "termina" sin un criterio objetivo de done, y recién el post-hoc (29/30/31) descubre los huecos. Más turnos, más reprocesos, más `needs_review`. |
| **D-A2** | **El gate de cierre no ejecuta ningún examen derivado del ticket.** `finalize_run` (`post_run.py:35`) corre `contract_validator.validate` (forma por agente, `:62`) + `confidence.score` (heurística, `:69`) y fija el status (`:76`). El `contract_validator` valida **forma por tipo de agente**, no las cláusulas del ticket puntual; nada ejecuta una prueba de aceptación específica de ESTE encargo. | `post_run.py:35,62,69,76` | Un entregable que respeta la forma del agente pero **no hace lo que el ticket pedía** pasa el gate; el incumplimiento se descubre tarde (revisión humana o, peor, en producción). |
| **D-A3** | **El examen lo escribe el propio agente: circularidad del auto-examen.** Cuando el agente escribe tests junto al código, el 31/E0.1 los ejecuta y el 31/E1.2 atrapa los **vacíos** — pero un test **real pero alineado a la interpretación (posiblemente errónea) del agente**, o **laxo a propósito**, pasa. No hay un examen **independiente del agente, definido antes** de que trabaje. El seam de reparación (`run_repair.py`, `cli_autocorrect.py`) tampoco dispara por "el contrato del ticket está en rojo" porque ese contrato no existe. | `harness/run_repair.py` (forma); `cli_autocorrect.py` (artifacts); guard 31/E1.2 (solo test vacío) | "Tests verdes" puede significar "el agente se aprobó a sí mismo". La red de seguridad mide la interpretación del agente, no el encargo. Regresiones y malentendidos se cuelan con apariencia de validados. |
| **D-A4** | **El operador juzga sin ver una Definición de Hecho ejecutable.** El verdict (23/U1.3) se toma sobre el **texto**; el operador no ve "✓ 4/4 criterios ejecutables derivados del ticket" ni "✗ 1/4 (test `X` en rojo, log adjunto)". Para saberlo, ejecuta él mismo o aprueba a ciegas. | flujo de verdict (`agent_completion_internal.py`), UI de revisión (doc 23) | El operador re-verifica a mano (trabajo que el arnés podría darle hecho) o aprueba sin la señal y descubre el incumplimiento después. Decide con menos información de la disponible. |
| **D-A5** | **No se mide la Definición de Hecho.** La telemetría tiene costo/turnos/contract/confidence (`harness/telemetry.py:122`); `harness_health` (H8) no cubre **% runs con contrato derivable**, **% cumplido-a-la-primera**, **% recuperado** ni **% chequeos vacuos descartados** (calidad del examen). | `harness/telemetry.py:122`, `services/harness_health.py` | Sin número no se sabe si el contrato ayuda ni qué tan bueno es el examen generado; no se afina lo que no se mide. |

**Lectura estratégica:** el 27 mejora lo que entra; el 28 que el proceso sobreviva; el 29 que cumpla el criterio semántico; el 30 que las referencias existan; el 31 que lo producido ejecute. **Los cinco verifican después.** El 32 cierra el sexto lado, el primero en el tiempo y el que un senior hace por instinto: **definir el examen ejecutable e independiente — primero** (A0.1), trabajar contra él (A1.1), ejecutarlo como gate y corregir una vez (A1.1), blindar su independencia (A1.2), mostrarlo al operador (A2.1) y medirlo (A2.2). El operador no toca nada: el run converge a un "hecho" concreto y el verdict se toma sobre un examen probado.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo** y por riesgo. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: **A0** (derivar+validar el contrato, en modo `annotate` para medir calidad del examen sin gatear) → **A1** (cerrar el lazo: inyectar el blanco, gatear ejecutando, corregir, y blindar la independencia) → **A2** (amplificar el verdict humano + medir). Todos los flags default **OFF/0**; con todo en default, el comportamiento es **byte-idéntico** a hoy, runtime por runtime.

### FASE A0 — Definir y validar el examen: derivar la Definición de Hecho ejecutable e independiente

---

#### A0.1 Derivador de contrato de aceptación ejecutable + juez determinista del examen (fail-red on baseline) — el ítem fundacional

- **Ataca:** D-A1. Reusa el extractor de criterios (`self_review._resolve_criteria:43`) como insumo, el workspace/`subprocess` de los runners, y la lógica anti-verde-falso (31/E1.2); NO inventa toolchain.
- **Frontera con lo existente (declarada):** 29/Q0.1 inyecta criterios como **prosa**; 31/E0.1 ejecuta lo **existente**; A0.1 **genera** un examen **ejecutable** del ticket y **prueba que falla en rojo** antes de trabajar. Disjunto de ambos.
- **Problema + evidencia:** los criterios solo viven como prosa para juicio final (`self_review.py:43`); el workspace ejecutable está ocioso para esto (`claude_code_cli_runner.py:2003,643`); el gate de cierre no ejecuta un examen del ticket (`post_run.py:62`).
- **Propuesta (mínima):** un servicio `services/acceptance_contract.py::derive(ticket, workspace, complexity, runtime) -> AcceptanceContract`, invocado **antes** de lanzar el trabajo del agente (en `run_agent`/el runner, junto al armado de contexto). Diseño:
  - **Derivación acotada (1 llamada LLM, bajo el clamp).** A partir del ticket (+ los criterios del 29 si están: traducir prosa→ejecutable, más barato que re-leer), el LLM propone un **conjunto PEQUEÑO** (cap por `estimate_complexity`: `S`→0-1, `M`→1-2, `L/XL`→2-4) de **chequeos concretos y corribles**, cada uno con: `kind` ∈ {`generated_test` (un test en el framework detectado del proyecto), `schema` (un JSON/YAML-schema que el output debe satisfacer — validación **estructural**), `command` (una invocación CLI + exit/salida esperada), `file_predicate` (un archivo debe existir y matchear un patrón de contenido)}; el **artefacto corrible**; y una **traza** (`ticket_clause`) a la parte del ticket que codifica. Si una cláusula no se puede traducir con confianza → no se genera ese chequeo (queda para el 29 semántico).
  - **Juez determinista del examen (el núcleo de calidad).** Cada chequeo generado se ejecuta contra el **baseline sin tocar** (el workspace antes de que el agente trabaje), con la contención del 31/E0.1 (o `subprocess` acotado si el 31 no está):
    - chequeo que **falla en rojo** en baseline → **se conserva** (probadamente exige conducta nueva: red-green).
    - chequeo que **pasa** en baseline → **vacuo, se descarta** (no constriñe nada).
    - chequeo sin `assert`/predicado real (lógica 31/E1.2 vía `ast` stdlib) → **se descarta**.
    - chequeo que **no se pudo ejecutar** (toolchain ausente, timeout) → **descartado para gate**, anotado como `could-not-baseline` (degrada con gracia, nunca gatea).
  - **Resultado.** `AcceptanceContract = {checks_kept: [...], checks_dropped: [{reason}], coverage: 0..1, n_a: bool}`. Si `checks_kept` está vacío → `n_a=true` (sin gate; cae a 29+31). Se persiste en `metadata["acceptance_contract"]` (clave **NUEVA**, aditiva) **antes** del run.
  - **Modo.** `STACKY_ACCEPTANCE_CONTRACT_MODE` ∈ {`off|annotate|gate`}, default `off`. En `annotate` deriva y valida pero **no** inyecta como blanco ni gatea — solo mide calidad del examen (vacuos descartados, cobertura) antes de confiar en él.
- **Impacto esperado:** **resultado** — existe un blanco objetivo y probadamente exigente para cada run. **Eficiencia** — derivación acotada (1 llamada, cap por complejidad), reusa criterios del 29; un `S` puede no derivar nada (no-op, cero costo). Métrica: % runs con contrato no-vacío; tasa de chequeos vacuos descartados (calidad del examen) (A2.2).
- **Por qué es invisible:** el operador no escribe el examen; deriva del ticket que él seleccionó. Cero pasos nuevos.
- **Por qué NO viola rule 11:** derivar el examen del encargo del operador no decide trabajo nuevo ni publica; en `annotate` ni siquiera cambia el run — solo anota qué sería "hecho".
- **Salvaguarda de calidad (y cómo se mide):** el examen solo se conserva si **probadamente falla en rojo** en baseline (no vacuo) y tiene `assert` real; si nada sobrevive → `n/a` (sin gate, cae a 29+31, **nunca** peor que hoy); un chequeo no ejecutable nunca gatea. Flag OFF → `run_agent`/`finalize_run` byte-idénticos. Se mide con tests: ticket con cláusula traducible → chequeo que falla-red conservado; chequeo que pasa en baseline → descartado vacuo; chequeo sin assert → descartado; nada traducible → `n/a`; toolchain ausente → `could-not-baseline` (no gate); `annotate` no cambia el run; flag OFF → byte-idéntico. Mock del LLM y del runner de subprocess.
- **Flag:** `STACKY_ACCEPTANCE_CONTRACT_ENABLED` (bool, default **false**) + `STACKY_ACCEPTANCE_CONTRACT_MODE` (str `off|annotate|gate`, default `off`) + `STACKY_ACCEPTANCE_CONTRACT_MAX_CHECKS` (int, default 4) + `STACKY_ACCEPTANCE_CONTRACT_PROJECTS` (csv) + `FLAG_REGISTRY`.
- **TDD (`tests/test_acceptance_contract.py`):** derivación con cap por complejidad; fail-red-on-baseline conserva, pass-on-baseline descarta vacuo, sin-assert descarta; `n/a` cuando nada sobrevive; `could-not-baseline` no gatea; reuso de criterios del 29 si están; `annotate` no inyecta ni gatea; flag OFF → byte-idéntico. Sin binarios reales (mock LLM + subprocess).
- **Complejidad:** L (derivador + juez de baseline + 2-3 `kind` iniciales; partible: PR1 `schema`+`file_predicate` (baratos, stdlib), PR2 `generated_test`+`command`).

---

### FASE A1 — Cerrar el lazo: trabajar contra el blanco, gatear ejecutándolo, corregir y blindar la independencia

---

#### A1.1 Inyectar el contrato como BLANCO del run + gate por ejecución + pase correctivo único dirigido por el chequeo en rojo — el ítem de mayor valor

- **Ataca:** D-A1, D-A2, D-A3. Reusa `enrich_blocks` (inyección), el motor del 31/E0.1 (ejecución), y el seam de reparación con presupuesto compartido (corrección). NO re-implementa ninguno.
- **Frontera con lo existente (declarada):** 29/Q0.1 inyecta prosa; 31/E0.1 ejecuta lo existente; 29/Q1.1 corrige por LLM; 31/E1.1 corrige por verificador existente. A1.1 inyecta el **examen ejecutable** como blanco, gatea **ejecutándolo**, y corrige por su **rojo** (el log del chequeo **es** el prompt). Disjunto.
- **Problema + evidencia:** el contrato derivado en A0.1 no se usa como guía (briefing inyecta prosa, `context_enrichment.py:34`) ni como gate (`finalize_run` no lo ejecuta, `post_run.py:62`); la señal "contrato en rojo" no dispara corrección (`run_repair.py` solo forma).
- **Propuesta (mínima):** cuando `STACKY_ACCEPTANCE_CONTRACT_MODE == gate` y el contrato **no** es `n/a`:
  - **Inyección como blanco (test-first).** Un **bloque de contexto nuevo y aditivo** `acceptance-contract` (alta prioridad, fuente de verdad), inyectado en `enrich_blocks` (un solo seam, los 3 runtimes): presenta los chequeos como la Definición de Hecho explícita ("Tu entregable DEBE pasar estos chequeos ejecutables: <lista con kind+intención>. Trabajá hasta que pasen."). Participa del dedup (27/I0.1) y del budget como bloque de alta prioridad (nunca se poda). El agente trabaja **contra un blanco concreto**, no difuso.
  - **Gate por ejecución.** En `finalize_run`, **después** del contract validator y **antes** de fijar el status, se ejecuta el contrato (`checks_kept`) vía el motor del 31/E0.1 (caché/short-circuit/sandbox/budget; o `subprocess` acotado si el 31 no está). Si **todos pasan** → `completed` (`acceptance_contract.satisfied=true`). Si **alguno falla** → no se presenta como `completed`.
  - **Pase correctivo único dirigido por el rojo.** Si hay chequeo fallido Y el runtime soporta resume/stdin (`capabilities.CAPABILITIES[runtime].supports_resume`) Y queda presupuesto: **un único** mensaje correctivo con el **excerpt del log del chequeo en rojo** ("El chequeo de aceptación `<id>` (`<intención>`) falló: `<excerpt del log>`. Corregí SOLO eso, manteniendo el resto; mismo formato.") por el MISMO transporte del autocorrect/run_repair. Se **re-ejecuta el contrato una vez** (cacheado): pasa → `completed` (`recovered=true`); sigue rojo → `needs_review` con el contrato y el log.
  - **Presupuesto duro compartido.** `STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES` (int, default 1); el conteo se **comparte** con autocorrect/`run_repair`/Q1.1/E1.1 (mismo techo por run). Peor caso documentado.
  - **Modelo/effort.** El pase usa el MISMO modelo y effort del run (bajo el clamp); NO escala.
  - **Sin resume → no repara (sin fallback silencioso):** degrada directo a `needs_review` con el contrato; nunca finge un fix.
  - **Sello:** `metadata["acceptance_contract"]["result"] = {"satisfied": bool, "failed_checks": [...], "repair": {"attempted": bool, "recovered": bool}}`.
- **Impacto esperado:** **resultado** — el run converge a "hecho" objetivo; menos entregables que "se ven bien" pero no hacen lo pedido; el verde deja de ser auto-otorgado. **Eficiencia** — apuntar bien la primera vez baja turnos; el log del chequeo es el mejor prompt; menos `needs_review` + relanzamiento manual. Métrica: % cumplido-a-la-primera; tasa de recuperación; caída de `needs_review` por incumplimiento (A2.2).
- **Por qué es invisible:** el operador no escribe el examen, no relanza ni corrige; ve el entregable cumpliendo el contrato o un `needs_review` con el log. Cero pasos nuevos.
- **Por qué NO viola rule 11:** el run lo lanzó el operador; el contrato deriva de SU ticket; la corrección ocurre DENTRO del run, antes de presentar; NO publica nada (verdict humano y publicación U1.3/U2.2 intactos); es lo que el operador haría (relanzar pidiendo que pase el test). Si no recupera, **no decide**: `needs_review` con la verdad adjunta. Nunca oculta el fallo ni auto-publica.
- **Salvaguarda de calidad (y cómo se mide):** el repair **no enmascara** mala calidad — solo salva lo que vuelve a pasar el MISMO chequeo (inmutable, ver A1.2); si no → `needs_review` (el contrato sigue siendo el juez); presupuesto duro de 1; sin resume → no repara. El contrato es el examen **independiente** (A0.1), no uno escrito por el agente. Flag OFF / `annotate` → byte-idéntico (no inyecta ni gatea). Se mide con la tasa de cumplido-a-la-primera, de recuperación, y de `needs_review` por incumplimiento (A2.2).
- **Flag:** `STACKY_ACCEPTANCE_GATE_ENABLED` (bool, default **false**) + `STACKY_ACCEPTANCE_REPAIR_ENABLED` (bool, default **false**) + `STACKY_ACCEPTANCE_REPAIR_MAX_RETRIES` (int, default 1) + `FLAG_REGISTRY`. Depende de `STACKY_ACCEPTANCE_CONTRACT_MODE == gate`.
- **TDD (`tests/test_acceptance_gate.py`):** contrato inyectado como bloque de alta prioridad (no se poda, no duplica con la épica); todos pasan → `completed`+`satisfied=true`; uno falla + resume → un pase con el excerpt → recupera → `completed`+`recovered=true`; no recupera → `needs_review`+log; sin resume → `needs_review` sin reparar; presupuesto compartido (no se suma a autocorrect/run_repair/Q1.1/E1.1); `n/a` → sin gate; flag OFF/`annotate` → byte-idéntico. Mock de runner, de `enrich_blocks` y del motor de ejecución.
- **Complejidad:** L (inyección en el seam compartido + gate en `finalize_run` + cierre de ambos runners CLI; partible: PR1 inyección+gate, PR2 repair codex, PR3 repair claude).

---

#### A1.2 Guard de independencia/no-circularidad: el contrato es inmutable durante el run

- **Ataca:** D-A3. Verificador determinista dentro del flujo de A1.1; NO emite juicio semántico.
- **Frontera con lo existente (declarada):** 31/E1.2 detecta que **los tests del agente** estén vacíos. A1.2 protege que **el contrato INDEPENDIENTE** (derivado antes y fuera del agente) **no sea ablandado** por el propio agente para pasar. Distinto: ahí el sujeto es el test propio; acá es el examen externo.
- **Problema + evidencia:** el seam de reparación reusa el workspace del agente (`claude_code_cli_runner.py:643`); nada impide que un pase correctivo (A1.1) edite el archivo del chequeo del contrato en vez del código bajo prueba — gameando el gate.
- **Propuesta (mínima):** antes de cada ejecución del contrato (baseline en A0.1, gate y re-gate en A1.1), los artefactos corribles del contrato (`checks_kept[*].artifact`) se materializan en una **ubicación de solo-arnés** (un subdir temporal del run, fuera de los paths que el agente edita) y se ejecutan **desde ahí**, no desde donde el agente trabaja. Si un chequeo es del tipo `generated_test` que vive en el árbol del proyecto, antes del re-gate se verifica su **hash**: si el agente lo modificó, ese chequeo se **restaura** a la versión derivada (inmutable) y la modificación del agente se trata como **artefacto nuevo a re-validar** (debe a su vez fallar-red en baseline para contar, A0.1). `metadata["acceptance_contract"]["integrity"] = {"mutated_checks": [...], "restored": bool}`. **Cero LLM.**
- **Impacto esperado:** **resultado** — el gate mide la conducta real contra el examen independiente, no contra un examen ablandado; rompe la circularidad de raíz. **Eficiencia** — hash-check en microsegundos. Métrica: nº de runs con `mutated_checks` (intentos de gameo atrapados) (A2.2).
- **Por qué es invisible:** el operador no inspecciona nada; recibe un gate confiable. Cero pasos nuevos.
- **Por qué NO viola rule 11:** preservar la integridad del examen no decide ni publica; es una garantía objetiva.
- **Salvaguarda de calidad (y cómo se mide):** el contrato derivado es la fuente de verdad inmutable; restaurarlo solo **endurece** el gate, nunca degrada el entregable; si el agente mejoró legítimamente un test, esa mejora se re-valida (fail-red) y se incorpora solo si es genuina. Flag OFF → no corre. Se mide con tests: chequeo materializado fuera del árbol del agente; `generated_test` modificado → restaurado + marcado; modificación que pasa fail-red → incorporada; flag OFF → byte-idéntico.
- **Flag:** `STACKY_ACCEPTANCE_INTEGRITY_ENABLED` (bool, default **false**). Depende de A1.1.
- **TDD (`tests/test_acceptance_integrity.py`):** ejecución desde ubicación de solo-arnés; mutación de un `generated_test` → restaurado + `mutated_checks` poblado; mutación que fall-red → re-incorporada; flag OFF → byte-idéntico.
- **Complejidad:** M.

---

### FASE A2 — Amplificar el verdict humano + medir (cerrar el loop)

---

#### A2.1 Definición de Hecho ejecutable en la vista de verdict (amplifica al humano, no lo reemplaza)

- **Ataca:** D-A4. Reusa la vista de verdict (23/U1.3) y la metadata que A0.1/A1.1 ya pueblan; NO crea workflow nuevo ni saca al humano del lazo.
- **Frontera con lo existente (declarada):** 23 hace **perceptible** el valor del run; 31/E2.1 muestra "compila/tests/lint" (verificadores **genéricos**); A2.1 muestra los **criterios ejecutables específicos de ESTE ticket** (la Definición de Hecho derivada), con su traza al ticket.
- **Problema + evidencia:** el operador juzga sobre el texto sin ver la Definición de Hecho cumplida/incumplida (`agent_completion_internal.py`, UI doc 23).
- **Propuesta (mínima):** renderizar `metadata["acceptance_contract"]` como un **bloque compacto y read-only** en la vista de revisión que el operador ya abre: "Definición de Hecho (derivada del ticket): ✓ 4/4" o "✗ 3/4 (chequeo `<intención>` en rojo)", cada chequeo con su **traza** a la cláusula del ticket y el **excerpt del log** colapsable para los fallos; aviso si el contrato fue `n/a` (sin examen ejecutable → se juzgó por 29/31). **Sin** botones nuevos que decidan: el operador conserva su verdict, ahora **mejor informado** y pudiendo **ver exactamente qué se midió como "hecho"**. Degrada con gracia (sin metadata → no se muestra); compila con `tsc` (sin tests vitest obligatorios).
- **Impacto esperado:** **resultado/eficiencia** — el operador decide con la Definición de Hecho en pantalla; menos re-verificación manual, menos aprobaciones a ciegas; transparencia total de qué exigió el arnés. Amplificación pura del centauro (doc 23/24).
- **Por qué es invisible:** se agrega a una vista existente; cero pasos nuevos, cero workflow nuevo. Ve *más verdad*, no *más trabajo*.
- **Por qué NO viola rule 11:** mostrar el contrato no decide nada; el verdict humano queda intacto. Es observabilidad dentro del flujo de aprobación.
- **Salvaguarda de calidad (y cómo se mide):** read-only puro; no altera el entregable ni el verdict; fuente ausente → degrada ("—"). Flag OFF → la vista no agrega el bloque (byte-idéntico). Se mide con el shape del payload (backend) y cualitativamente (el operador decide con más contexto y puede auditar el examen).
- **Flag:** `STACKY_ACCEPTANCE_VERDICT_CARD_ENABLED` (bool, default **false**).
- **TDD:** test del shape del payload que la API expone (satisfecho/incumplido/`n/a`/ausente → bloque correcto o degradación); UI solo `tsc`.
- **Complejidad:** S/M.

---

#### A2.2 KPIs del contrato de aceptación en harness-health (read-only, sin UI nueva)

- **Ataca:** D-A5. Extiende `harness_health` (H8) y la `HarnessHealthCard` existente; NO crea UI nueva.
- **Problema + evidencia:** la telemetría no mide la Definición de Hecho (`harness/telemetry.py:122`); `harness_health` no lo cubre.
- **Propuesta (mínima):** un bloque de **contrato de aceptación** en `services/harness_health.py`, por proyecto y ventana, leyendo `metadata["acceptance_contract"]` que A0.1/A1.1/A1.2 pueblan: `tasa_contrato_derivable` (no-`n/a` / total), `tasa_cumplido_a_la_primera` (satisfied sin repair / con contrato), `tasa_recuperacion` (`repair.recovered/attempted`), `calidad_del_examen` (1 − vacuos_descartados/generados), `intentos_de_gameo_atrapados` (`mutated_checks` no vacío), y `cobertura_media` (`coverage`). Read-only.
- **Impacto esperado:** la Definición de Hecho se vuelve un **número visible** → se afina dónde invertir y se valida que el contrato (y su calidad) ayudan. Métrica: el propio dashboard.
- **Por qué es invisible:** se agrega a una card existente; cero pasos nuevos.
- **Por qué NO viola rule 11:** mostrar números no decide nada; es observabilidad.
- **Salvaguarda de calidad (y cómo se mide):** definiciones explícitas y testeadas; read-only puro; fuente ausente → degrada ("—"). Flag OFF → la card no agrega el bloque (byte-idéntico). Se mide con un test del endpoint con datos sintéticos.
- **Flag:** `STACKY_ACCEPTANCE_KPIS_ENABLED` (bool, default **false**).
- **TDD (`tests/test_harness_health_acceptance.py`):** con runs sintéticos (derivado/`n/a`, cumplido a la primera, recuperado, vacuos descartados, gameo atrapado) → KPIs correctos por proyecto/ventana; fuente ausente → degrada; flag OFF → sin bloque nuevo.
- **Complejidad:** M.

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | **A0.1** Derivador + juez del examen (fail-red on baseline), `annotate` | L | **Muy alto (crea el blanco objetivo + garantiza que no es vacuo)** | Bajo en `annotate` (no inyecta ni gatea, flag OFF) | `_resolve_criteria` (29, en código); workspace/`subprocess` (en código); motor 31/E0.1 si está |
| 2 | **A1.1** Inyectar blanco + gate por ejecución + repair dirigido | L | **Muy alto (converge a "hecho" + recupera dentro del run + rompe el verde auto-otorgado)** | Medio (toca `enrich_blocks`, `finalize_run` y cierre de runners → flags, presupuesto compartido) | A0.1; `enrich_blocks` (en código); motor 31; seam de reparación (en código) |
| 3 | **A1.2** Guard de independencia (inmutabilidad del contrato) | M | **Alto (rompe la circularidad de raíz)** | Bajo (hash + materialización; cero LLM) | A1.1 |
| 4 | **A2.1** Definición de Hecho en el verdict (amplifica al humano) | S/M | Alto (decisión mejor informada + auditable) | Bajo (read-only, degrada) | A0.1/A1.1 pueblan datos |
| 5 | **A2.2** KPIs del contrato | M | Alto (cierra el loop + mide calidad del examen) | Bajo (read-only) | A0.1/A1.1/A1.2 pueblan datos |

**Rollout gradual (mismo patrón que `STACKY_SELF_REVIEW_MODE` / `STACKY_EXEC_VERIFICATION_MODE` off/annotate/gate):** (1) `off` → byte-idéntico; (2) `annotate` global → A0.1 deriva y valida el examen y **solo anota** (se miden tasa de contrato derivable, vacuos descartados, cobertura — la **calidad del examen** — sin gatear ni inyectar); (3) `gate` en proyectos piloto vía `STACKY_ACCEPTANCE_CONTRACT_PROJECTS` + `STACKY_ACCEPTANCE_GATE_ENABLED` + `STACKY_ACCEPTANCE_REPAIR_ENABLED` cuando la calidad del examen en `annotate` sea aceptable; (4) `gate` general. A1.2 entra junto al gate. Cada paso reversible bajando el flag.

**Reglas de implementación (las 7 del doc 22 + las de frontend del doc 23 aplican íntegras):** TDD; validar **por archivo de test** con el python del `.venv` (suite contaminada; pin pywin32==306 roto en 3.13); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves **nuevas** (`acceptance_contract` y sub-claves); default **OFF/0** (retro-compat **byte-idéntica** — con todos los flags en default, el resultado es EXACTAMENTE el de hoy, runtime por runtime); ADO solo por los caminos existentes (este plan **no agrega escrituras**; deriva/ejecuta un examen read-only sobre el workspace local; la única lectura nueva de ADO es la de criterios, que reusa el extractor del 29 y la caché del 27/I3.2 si está); **sin fallback silencioso entre runtimes** (A1.1 no repara sin resume; la derivación/ejecución se cablean por workspace); **sin deps npm/py nuevas** (derivación con el LLM ya configurado bajo el clamp; ejecución con el motor del 31 o `subprocess` + la toolchain del proyecto; si no está → `n/a`); UI (vista de verdict + DiagnosticsPage) degrada con gracia y compila con `tsc` (vitest no instalado: sin tests vitest obligatorios).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Doctrina: (a) el contrato es una **traducción del encargo del operador** a forma ejecutable, dentro de un run que él lanzó, antes de presentar; (b) lo que se gatea es pass/fail objetivo de la **ejecución** del examen, nunca contenido; (c) la única "corrección" (A1.1) reusa el seam de reparación contra un chequeo objetivo, **una vez**, y si no recupera va a `needs_review` con el log; (d) **nada publica, transiciona ADO ni oculta un fallo**; (e) lo que muestra (A2.1) **amplifica** y hace **auditable** el verdict humano sin reemplazarlo; (f) lo que mide (A2.2) produce números, no mutaciones. Cada ítem trae su línea "Por qué NO viola rule 11".

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (que NO configura ni ve estos mecanismos)
- **Hoy:** lanza un run contra un encargo en prosa; el agente apunta a un blanco difuso y "termina" sin un criterio objetivo de done; cuando aprueba, lo hace sobre el texto, sin saber si el entregable realmente hace lo que el ticket pedía; si el agente escribió tests, son los suyos (se aprobó a sí mismo).
- **Después (sin tocar nada):** el mismo run trabaja contra una Definición de Hecho ejecutable derivada de SU ticket, probadamente exigente; sale cumpliéndola, lo que falla se corrige una vez o llega a `needs_review` con el chequeo en rojo a la vista; y cuando aprueba, ve "✓ 4/4 criterios ejecutables derivados del ticket" con la traza a cada cláusula. No ve ninguna perilla nueva: solo nota que Stacky "hace exactamente lo que el ticket pedía, y lo demuestra".

### Desarrollador / equipo (que vive en ADO)
- **Hoy:** a veces recibe entregables que respetan la forma pero no cumplen el encargo, o cuya "red de tests" la escribió el mismo agente.
- **Después:** recibe entregables que pasaron un examen ejecutable **independiente** derivado del ticket, con el verde respaldado por un examen que probadamente exigía la conducta nueva — sin cambios en cómo Stacky escribe.

### Management
- **Hoy:** no hay número de "cumple la Definición de Hecho"; la calidad del examen es invisible.
- **Después:** tasa de contrato derivable, cumplido-a-la-primera, recuperación, **calidad del examen** (vacuos descartados) e intentos de gameo atrapados en la DiagnosticsPage existente (A2.2) — el "definición de hecho cumplida" se vuelve medible sin sumar trabajo operativo.

---

## 7. Ventaja competitiva: por qué definir el examen primero gana

1. **Un CLI suelto apunta a un blanco difuso; el arnés define el examen primero.** Un CLI suelto interpreta el ticket y se autoevalúa. Stacky, dentro del run que el humano lanzó, **traduce el encargo a un examen ejecutable e independiente, prueba que exige la conducta nueva, y recién entonces deja trabajar al agente contra ese blanco** — sin cruzar la línea de la autonomía (no publica, no decide; el humano firma).
2. **El verde deja de auto-otorgarse.** En un CLI suelto, el agente escribe el código y su propio test: el alumno se pone el examen. El 32 rompe esa circularidad: el examen lo define el arnés, antes, y es inmutable durante el run. "Tests verdes" pasa de "el agente se aprobó" a "el arnés definió el examen y el agente lo pasó".
3. **El LLM propone, la ejecución determinista manda — incluso sobre el propio examen.** La parte creativa (traducir un requisito a un test) la hace el modelo; la parte de confianza (¿el test exige algo? ¿el entregable lo pasa?) la hace la ejecución determinista (fail-red on baseline + gate). Es la única forma de usar un LLM para subir calidad **sin** confiar ciegamente en él.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo | Fuente |
|---|---|---|---|
| Runs con Definición de Hecho ejecutable | ninguna (blanco difuso) | derivable y medible | `acceptance_contract` (A0.1) + A2.2 |
| Calidad del examen (vacuos descartados / generados) | n/a | baja tasa de vacuos (examen exigente) | A0.1 (fail-red on baseline) + A2.2 |
| Cumplido-a-la-primera (pasa el contrato sin repair) | no medido | medible y creciente | A2.2 |
| Recuperación del pase correctivo (`recovered/attempted`) | n/a | alta y medible | `acceptance_contract.result.repair` (A1.1) |
| Circularidad / verde auto-otorgado | la norma (agente se autoexamina) | roto (examen independiente e inmutable) | A1.2 (`mutated_checks`) + A2.2 |
| Verdict humano informado por la Definición de Hecho | aprueba sobre el texto | aprueba con "✓ N/N criterios ejecutables" + traza | A2.1 |
| Calidad de entregables tras los chequeos | n/a | **no debe caer** (aditivos; `n/a` cae a 29+31) | A2.2 + KPIs del 29/30/31 |
| Perillas nuevas que el operador debe tocar | — | **cero** (flags internos, default OFF) | — |

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| El examen generado por el LLM está **mal** (mide lo que no es) o es **laxo** | **Juez determinista del examen:** cada chequeo debe **fallar-red en baseline** (no vacuo) y tener `assert` real (31/E1.2); si nada sobrevive → `n/a`, sin gate. El gate solo existe sobre chequeos probadamente exigentes. Se valida primero en `annotate` (se mide la calidad del examen antes de confiar). |
| El gate bloquea un entregable bueno por un examen demasiado estricto/erróneo | Rollout `annotate` antes de `gate` mide falsos positivos; nunca bloquea silenciosamente: `needs_review` **con el contrato y el log**; el operador conserva el verdict y **ve qué se midió** (A2.1). Si el examen es `n/a`, se cae a 29+31 (nunca peor que hoy). |
| El agente **ablanda el examen** para pasar (edita el archivo del chequeo) | A1.2: el contrato se ejecuta desde una **ubicación de solo-arnés**, es **inmutable**; un `generated_test` modificado se **restaura** y la modificación se re-valida (debe fallar-red). Rompe la circularidad de raíz. |
| La derivación (1 llamada LLM) infla costo/latencia | Acotada por complejidad (`S`→0-1 chequeos, hasta `L/XL`→2-4); reusa los criterios del 29 (traducir es barato); `annotate-first` mide el ROI; un `S` puede no derivar nada (no-op). Bajo el clamp de modelo. |
| Ejecutar el contrato corre código potencialmente peligroso | Reusa la contención del 31/E0.1 (`cwd` acotado, timeout duro, budget, sin red, build-dir temporal); si el 31 no está, replica esos límites. Chequeo no contenible no se cablea. |
| Confundir A0.1/A1.1 con el 29 (criterios prosa) o el 31 (ejecutar lo existente) | Frontera declarada: 29 = prosa juzgada por LLM; 31 = ejecutar lo existente/del agente; 32 = **generar+validar+exigir** un examen ejecutable e independiente **antes** del run. Disjuntos. |
| Doble pase correctivo entre autocorrect/run_repair/Q1.1/E1.1/A1.1 | Presupuesto **compartido** (mismo techo por run); peor caso documentado; sin resume → no repara. |
| Una cláusula del ticket no se puede traducir a algo ejecutable | No se genera ese chequeo (no se inventa exigencia); queda para el 29 semántico. El contrato cubre lo objetivable; el resto sigue su flujo. |
| Sin resume, A1.1 no puede corregir | Sin fallback silencioso: degrada a `needs_review` con el contrato; `capabilities` declara la diferencia por runtime. |

---

## 10. Roadmap por fases (estado)

| Fase | Ítem | Estado |
|---|---|---|
| A0 | A0.1 Derivador + juez del examen (fail-red on baseline) | PROPUESTO |
| A1 | A1.1 Inyectar blanco + gate por ejecución + repair dirigido | PROPUESTO |
| A1 | A1.2 Guard de independencia (inmutabilidad del contrato) | PROPUESTO |
| A2 | A2.1 Definición de Hecho en el verdict (amplifica al humano) | PROPUESTO |
| A2 | A2.2 KPIs del contrato de aceptación | PROPUESTO |

**Estado global:** PROPUESTO (0/5 implementado al 2026-06-15). Con todos los flags en default OFF/0, el comportamiento es **byte-idéntico** al actual, runtime por runtime. El plan cierra el sexto lado del motor — **la Definición de Hecho ejecutable e independiente, definida ANTES del run** (el único eje pre-run + test-first de toda la línea) — con un examen que el **LLM propone** pero la **ejecución determinista valida y exige** (fail-red on baseline + gate + inmutabilidad), reusando el extractor de criterios (29), el seam de inyección `enrich_blocks` (27), el motor de ejecución (31), el seam de reparación (27) y las superficies de verdict/health (23/H8) que el código ya tiene, sin re-implementar el motor (27), el lifecycle (28), el juicio semántico (29), la verificación de existencia (30) ni el motor ejecutable (31), y sin sacar al humano del lazo.
