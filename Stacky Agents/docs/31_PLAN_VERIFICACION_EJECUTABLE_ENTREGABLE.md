# 31 — Plan Verificación Ejecutable del Entregable: que lo que el agente produjo PASE SUS PROPIAS PRUEBAS objetivas antes de entregar, sin pedirle nada al operador

**Fecha:** 2026-06-15
**Estado:** PROPUESTO (ningún ítem implementado)
**Predecesores:** `docs/21_PLAN_HARDENING_ARNES_MULTI_PROVEEDOR.md` (H0-H8, implementado salvo H2.5), `docs/22_PLAN_ARNES_VENTAJA_COMPETITIVA.md` (V0 implementado; V1-V2 parciales), `docs/23_PLAN_CAPA_PERCEPTIBLE_VALOR_VISIBLE.md` (implementado salvo UI U2.1), `docs/24_PLAN_CAPA_AMPLIFICACION_OPERADOR.md` (C0-C2, propuesto), `docs/26_PLAN_MEMORIA_CONFIGURABLE_Y_DIRECTIVAS.md` (**implementado completo**), `docs/27_PLAN_MEJORAS_INVISIBLES_MOTOR.md` (**implementado salvo I2.2 diferido**), `docs/28_PLAN_MEJORAS_ALTO_IMPACTO_INVISIBLES.md` (PROPUESTO — lifecycle/escritura/telemetría), `docs/29_PLAN_CALIDAD_RESULTADO_A_LA_PRIMERA.md` (PROPUESTO — criterios/few-shot CLI/effort/repair **semántico**), `docs/30_PLAN_INTEGRIDAD_VERIFICADA_CONTRA_REALIDAD.md` (PROPUESTO — preflight/post-create/grounding **determinista de existencia**).
**Audiencia:** dev agéntico junior. Cada ítem es autocontenido: objetivo, evidencia `file:line`, diseño con archivos exactos, criterios de aceptación, tests TDD, salvaguarda de calidad, frontera de no-solapamiento y complejidad.

**Tesis (innegociable):** los planes previos cubren cuatro lados del motor — el **27** hace que **piense mejor** (qué entra al modelo: contexto/retrieval/routing/caché), el **28** que **no se ahogue ni pierda trabajo** (lifecycle/proceso/escrituras/telemetría), el **29** que **el producto cumpla el encargo** según un juicio **semántico** (criterios de aceptación vía LLM), y el **30** que **el run esté anclado a la realidad** por **existencia determinista** en los bordes (precondiciones reales antes de gastar, rutas/IDs referenciados que existen, task realmente creada). Falta el quinto lado, **el que un humano técnico haría antes de aprobar cualquier entrega: ejecutarla.** Hoy el entregable se valida por **forma** (`contract_validator` mira secciones esperadas por tipo de agente) y por **heurística** (`confidence` cuenta hedge-phrases/TODOs), pero **nunca se EJECUTA**: nadie compila el código que el agente escribió, nadie corre los tests del proyecto contra lo producido, nadie pasa el lint/type-check, nadie valida que el JSON/YAML que generó parsea. Un entregable que **no compila**, con **tests en rojo**, o con un **JSON inválido** (la causa raíz documentada "crea archivos pero no la task" es exactamente un body que no valida) **pasa el gate de forma** y llega al operador como si estuviera listo. Peor: cuando el propio agente corre tests intra-run, un "todos verdes" puede ser **verde falso** — tests vacíos, con `skip`, o sin un solo `assert`. Este plan cierra ese quinto lado **sin pedirle nada al operador**: en el mismo workspace donde el agente trabajó, **ejecuta los verificadores objetivos que el proyecto ya tiene** (compilar, tests, lint, type-check, parseo de esquema), de forma **determinista, barata-primero y con short-circuit**; si algo falla, intenta **un único** pase correctivo dirigido al fallo (reusando el seam de reparación que ya existe) y, si no recupera, degrada a `needs_review` **adjuntando el log del fallo** para que el operador decida con la verdad en la mano. El TRABAJO es invisible; el RESULTADO se nota: menos entregables que "se ven bien" pero no funcionan, menos verde falso, y un verdict humano mejor informado — **sin sacrificar calidad y sin sacar al humano del lazo**.

**"Invisible" NO significa "autónomo" (frontera dura, regla 11):** invisible quiere decir que el operador no configura ni ve el mecanismo. NO quiere decir que el sistema decida por él. **Cada run lo inició el operador.** Las acciones de este plan ocurren **dentro de ese run, antes de presentar**, y son **ejecución determinista de verificadores objetivos** sobre lo que el agente produjo — exactamente lo que el operador haría antes de aprobar (correr los tests, compilar). Ninguna publica a ADO por su cuenta, ninguna transiciona el work item, ninguna oculta un fallo, y ninguna decide el trabajo: en caso de fallo no recuperable, el entregable va a `needs_review` con el reporte adjunto y **el operador conserva la decisión**. Cada ítem trae su línea explícita **"Por qué NO viola rule 11"**.

**Calidad nunca se sacrifica (segundo eje innegociable):** todos los chequeos de este plan son **deterministas y aditivos**. La verificación ejecutable solo puede **mejorar** la entrega: o confirma que pasa (señal de confianza objetiva), o atrapa un fallo que de otro modo llegaría al equipo. El único gasto extra (el pase correctivo de E1.1) está **acotado, gated y comparte el presupuesto** del autocorrect/run_repair existente, y se compensa con creces evitando un ciclo de revisión humana + relanzamiento. Si una herramienta de verificación falla por infraestructura (timeout, toolchain ausente), se trata como **"no se pudo verificar"** (soft/annotate), **nunca** como fallo del entregable — cero falsos negativos sobre trabajo válido. No hay ningún ítem cuyo "ahorro" pueda producir un peor resultado. Cada ítem trae su línea **"Salvaguarda de calidad (y cómo se mide)"**.

---

## Relación con los planes 27/28/29/30 (qué se subsume, qué se reemplaza, qué queda fuera)

> **Estado verificado el 2026-06-15 contra el código** (`codex/subida-cambios-pendientes`). El 27 está implementado (seams `context_enrichment`, `llm_router`, `harness/complexity.py`, `harness/run_repair.py`); el 28/29/30 están **propuestos** y reservan, respectivamente, el lifecycle/escritura/telemetría, la calidad-semántica del entregable (LLM) y la verificación determinista **de existencia** en los bordes. El 31 ocupa el espacio que ninguno toca: **ejecutar lo que el agente produjo y verificar que pasa sus propias pruebas objetivas** (compila / tests verdes / lint / type-check / esquema válido) antes de entregar.

- **SUBSUME:** nada. No re-especifica ningún ítem de 27/28/29/30.
- **REEMPLAZA:** nada. Los ítems pendientes del 28 (R0-R2), del 29 (Q0-Q2) y del 30 (G0-G2) siguen vigentes y no se tocan.
- **Eje de cada plan (frontera de no-solapamiento):**
  - **27** = *qué entra al modelo y cómo se cobra* (contexto/retrieval/routing-de-modelo/caché).
  - **28** = *que el proceso sobreviva y la escritura sea robusta* (zombie/stall/reap, validación **estructural** del body, idempotencia de comentarios, telemetría).
  - **29** = *que el producto cumpla el encargo* (criterios de aceptación) — juicio **semántico vía LLM**.
  - **30** = *que el run esté anclado a la realidad por existencia* — precondiciones reales, rutas/IDs que **existen**, task que **quedó creada**. Determinista, **estático**, cero ejecución.
  - **31** = *que lo que el agente PRODUJO efectivamente FUNCIONE* — compila, los tests pasan, el lint/type-check no tienen errores, el esquema valida. Determinista, **dinámico/ejecutable**, cero LLM en el chequeo. Es el eje *executed-correctness-per-token*.
- **Frontera fina declarada (cuatro verificaciones que parecen la del 27/29/30 pero son disjuntas):**
  1. **30/G1.2 (grounding de referencias)** chequea, **estáticamente**, que las rutas/IDs que el output **menciona** **existen**. **31/E0.1** chequea, **dinámicamente**, que el código/artefacto que el output **produjo** **ejecuta/compila/pasa tests**. *Existencia estática* vs *ejecución dinámica*: disjuntos. Un archivo puede existir (pasa G1.2) y no compilar (falla E0.1).
  2. **30/G0.1 (preflight)** verifica, **antes** del run, que las **condiciones para correr** existen (env: `outputs_dir`, PAT, repo). **31/E0.1** verifica, **después** del run, que el **artefacto producido** pasa sus pruebas. *Pre-run env* vs *post-run artifact*: disjuntos.
  3. **29/Q1.1 (pase correctivo de criterios, LLM)** corrige un fallo **semántico** juzgado por un LLM contra los criterios del ticket. **31/E1.1** corrige un fallo **objetivo y determinista** detectado **sin LLM** (un test rojo, un error de compilación). El 31 **alimenta** el mismo seam de reparación (run_repair/autocorrect/Q1.1) con una señal ejecutable; no re-implementa el transporte ni emite juicio semántico. *Señal LLM* vs *señal de herramienta*: disjuntas.
  4. **harness `contract_validator`** (`post_run.py:62`) valida la **forma por tipo de agente** (secciones esperadas presentes). **31/E0.1** valida la **ejecución** (los tests corren y pasan). *Forma* vs *ejecución*: disjuntos. Un output bien formado (pasa el contrato) puede tener el build roto (falla E0.1).
- **Frontera con `run_repair` (27/I1.1):** repara un output **vacío o estructuralmente malformado** (JSON inválido a nivel del propio output del runner, falta una clave) — un glitch de **forma del output**. **31/E1.1** repara un entregable **bien formado** cuyo **artefacto producido no pasa una prueba ejecutable** (compila / test). Disjuntos; **comparten el presupuesto de reparación**, no el disparador.
- **Frontera con el workspace existente:** el runner ya resuelve el directorio de trabajo donde el agente opera (`claude_code_cli_runner.py::_resolve_cwd` `:2003`, `workspace_root`/`cwd` `:108,371,626`) y ya usa `subprocess` para lanzar el CLI. El 31 **reusa ese mismo `cwd`** para correr los verificadores del proyecto (la toolchain que ya está instalada ahí); **no inventa un entorno** ni agrega deps.

---

## 1. Punto de partida: el sustrato de ejecución/verificación que YA existe (no re-implementar)

Verificado contra el código el 2026-06-15. La lectura central: **el entregable se valida por forma y heurística, pero nunca se ejecuta**, y ya existe TODO lo necesario para ejecutarlo sin inventar nada — un `cwd`/workspace real donde el agente trabajó, `subprocess` ya usado en los runners, un seam de post-run unificado donde enganchar el gate, y un presupuesto de reparación reusable. El mayor valor de este plan es **cablear la ejecución de los verificadores que el proyecto ya tiene**, no inventar herramientas.

| Sustrato | Dónde vive (file:line) | Estado |
|---|---|---|
| Post-run unificado: contract gate (forma) + confidence (heurística) + status final | `harness/post_run.py:35` (`finalize_run`), `:62` (`contract_validator.validate`), `:69` (`confidence.score`), `:76` (gate → `needs_review`) | OK — **valida FORMA y heurística; NO ejecuta el artefacto** (D-E1). Seam exacto donde engancha E0.1 (post-contrato, pre-status). |
| Workspace real donde el agente trabajó (donde corren los verificadores) | `services/claude_code_cli_runner.py:2003` (`_resolve_cwd`), `workspace_root`/`cwd` `:108,312,371,410,626,643,665`; `_run_pre_run_checks` `:348` | OK — **el `cwd` con la toolchain del proyecto ya instalada; nada corre tests/build ahí post-run** (D-E1) |
| `subprocess` ya usado para lanzar el CLI (precedente de ejecución externa) | `services/claude_code_cli_runner.py:643,665` (`cwd=...`), `services/codex_cli_runner.py` | OK — **patrón de ejecución externa con `cwd`/timeout ya establecido; lo reusa el verificador** (no agrega deps) |
| Artefactos producidos detectables (archivos en el workspace/outputs) | `services/output_watcher.py:998-1015` (arma body / detecta archivos del run) | OK — **se sabe qué archivos tocó el run; ninguno se compila/testea** (D-E1) |
| Seam de reparación dirigida (presupuesto compartido) | `harness/run_repair.py` (27/I1.1, vacío/malformado), `services/cli_autocorrect.py`, `services/codex_autocorrect.py`, seam de Q1.1 (29) | OK — **transporte y presupuesto de corrección reusables; ninguno se dispara por un fallo ejecutable** (D-E2) |
| Capacidades por runtime (resume/stdin/writes_artifacts) | `harness/capabilities.py:21` (`CAPABILITIES`) | OK — seam para decidir por-runtime si hay sesión resumible para el pase correctivo, sin `if` dispersos |
| Estimación de complejidad determinística (27/I0.2) | `harness/complexity.py::estimate_complexity` → `S/M/L/XL` | OK — seam para decidir cuánto presupuesto de verificación asignar por dificultad |
| Verdict humano y vista del entregable (23/U1.3) | flujo de publicación `agent_completion_internal.py`, UI de revisión (doc 23) | OK — **el operador juzga el entregable SIN una señal objetiva de si ejecuta** (D-E4); seam para adjuntar el reporte (E2.1) sin sacarlo del lazo |
| Telemetría de run + harness-health (H8) + DiagnosticsPage | `harness/telemetry.py:122`, `services/harness_health.py`, `frontend/.../DiagnosticsPage` (`HarnessHealthCard`) | OK — **no mide verde-a-la-primera / recuperación / verde falso atrapado** (D-E5); seam para exponer sin UI nueva |
| Flags + registro | `config.py`, `services/harness_flags.py` (`FLAG_REGISTRY`) | OK — patrón de flag interno default OFF, mismo PR |

**Restricciones vinculantes (idénticas a docs 22-30, no relitigar):** cap duro de modelo vía `llm_router.clamp_model` (nunca opus/fable); "solo Stacky escribe en ADO" = todo por el path de publicación existente (este plan **no agrega caminos de escritura**; solo **ejecuta verificadores read-only** sobre lo ya producido); mono-operador **sin RBAC** (`current_user()` es un header sin validar); claves de metadata existentes son contrato (**agregar, nunca renombrar**); todo flag nuevo entra en `config.py` + `FLAG_REGISTRY` en el MISMO PR, default **OFF/0**, retro-compat **byte-idéntica** cuando está OFF; suite contaminada → **validar por archivo de test** con el python del `.venv` (pin pywin32==306 roto en 3.13); vitest frontend NO instalado (UI: solo cambios que compilen con `tsc`, degradación con gracia, sin tests vitest nuevos obligatorios); **sin fallback silencioso entre runtimes** (claude/codex/copilot se cablean por separado); **sin deps npm/py nuevas** (la verificación usa la toolchain que el proyecto ya tiene vía `subprocess`; si no está, skip); el build congelado no tiene FTS5 verificado (no introducirlo).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Cada acción es **ejecución determinista de verificadores objetivos** sobre lo que el agente produjo, dentro del run que el operador lanzó, antes de presentar: no decide trabajo, no publica, no transiciona ADO, no oculta fallos. Ante fallo no recuperable, degrada a `needs_review` con el reporte; el verdict humano y el path de publicación (U1.3/U2.2 del doc 23) quedan **intactos**.

---

## 2. Qué NO es este plan (anti-scope explícito)

1. **No es autonomía ni auto-intake.** Ningún run nace sin el operador. Ejecutar los tests/build de lo que el agente produjo no decide trabajo: es la verificación que el operador haría antes de aprobar, hecha dentro del run que él lanzó.
2. **No publica ni transiciona ADO por su cuenta, ni cambia QUÉ/CUÁNDO se publica.** El verdict humano no se toca. Un entregable verde **no** se auto-aprueba ni se auto-publica; uno rojo **no** se descarta solo: va a `needs_review` con el reporte adjunto y el operador decide. La verificación **nunca** oculta un fallo.
3. **No ejecuta código arbitrario sin contención.** Todo verificador corre con `cwd` acotado al workspace del run, **timeout duro**, **presupuesto global**, **sin red**, y sin mutar el repo más allá de un directorio de build temporal. Si un verificador es peligroso o no contenible, no se cablea.
4. **No re-implementa `run_repair` (27), el autocorrect, ni el pase semántico del 29.** E1.1 **reusa** su transporte y comparte su presupuesto; el disparador (fallo ejecutable) es la única novedad.
5. **No inventa verificadores ni toolchain.** Usa **solo** lo que el proyecto ya tiene y es **detectable** (hay `tsconfig.json` → `tsc`; hay tests + `pytest` disponible → pytest; hay `.csproj` → build dotnet). Si **nada aplica** (el entregable es un documento de análisis puro) → **no-op**, nunca falla por "nada que verificar".
6. **No emite juicios de contenido.** Todo es pass/fail **objetivo de una herramienta** (compila / no compila, test verde / rojo, JSON parsea / no parsea). La calidad semántica es del 29.
7. **No expone perillas nuevas al operador.** Todos los flags son **internos**. Las únicas superficies que cambian son: el **reporte adjunto al entregable** que el operador ya revisa (E2.1) y la **DiagnosticsPage existente** (E2.2) — ambas muestran *más verdad*, sin pedir acción.
8. **No introduce FTS5 ni deps nuevas.** Todo con stdlib + `subprocess` (ya usado en los runners) + la toolchain del proyecto.

---

## 3. Diagnóstico: dónde el resultado deja calidad (y plata) sobre la mesa por no ejecutar lo producido (con evidencia)

| # | Debilidad | Evidencia (file:line) | Impacto |
|---|---|---|---|
| **D-E1** | **El entregable se valida por forma y heurística, pero NUNCA se ejecuta.** `finalize_run` (`post_run.py:35`) corre `contract_validator.validate` (forma por agente, `:62`) + `confidence.score` (heurística, `:69`) y decide el status (`:76`). Ningún paso compila el código que el agente escribió, corre los tests del proyecto, pasa lint/type-check, ni parsea el JSON/YAML producido — pese a que el workspace con la toolchain existe (`claude_code_cli_runner.py:2003`, `cwd` `:643`) y `subprocess` ya se usa ahí. | `post_run.py:35,62,69,76`; `claude_code_cli_runner.py:2003,643`; `output_watcher.py:998-1015` | Entregables que **no compilan**, con **tests en rojo**, o con **JSON inválido** (la causa raíz documentada del body que no valida) pasan el gate de forma y llegan al equipo "listos"; reproceso humano para encontrar lo que un `pytest`/`tsc`/parse habría marcado en segundos. |
| **D-E2** | **El fallo ejecutable, aun cuando ocurre, no se captura como señal ni dispara corrección.** El seam de reparación (`run_repair.py`, `cli_autocorrect.py`, Q1.1 del 29) se dispara por **forma** (vacío/malformado) o **criterio semántico** (LLM); **ninguno** toma "el build no compila" o "un test quedó rojo" como disparador de un pase dirigido. El presupuesto de corrección existe pero la señal ejecutable se pierde. | `harness/run_repair.py` (solo vacío/malformado), `services/cli_autocorrect.py`, seam Q1.1 (29) | Un fallo que un único pase dirigido ("el test X falla con Y, corregí solo eso") habría salvado termina en `needs_review` o, peor, llega verde-de-forma pero roto-de-ejecución. El valor del workspace ya montado se desperdicia. |
| **D-E3** | **"Tests verdes" no garantiza nada: el verde puede ser falso.** Cuando el agente corre tests intra-run y reporta "todos verdes", nada valida que esos tests **realmente prueban**: pueden estar **vacíos**, con `@skip`/`xfail`, **sin un solo `assert`**, o la suite puede no haber colectado **ningún** test (0 passed = "verde"). No hay guard que distinga "verde porque pasa" de "verde porque no prueba". | (ausencia de guard; `post_run.py` no inspecciona los tests producidos) | Un entregable con cobertura ilusoria pasa como "validado por sus tests"; el equipo confía en una red que no existe; regresiones que esos tests debían atrapar se cuelan. Erosiona la confianza en la señal "tests verdes". |
| **D-E4** | **El operador juzga el entregable sin una señal objetiva de si ejecuta.** El verdict humano (23/U1.3) se toma sobre el **texto** del entregable; el operador no ve "compila / 12/12 tests verdes / lint OK" ni "2 tests en rojo (log adjunto)". Tiene que ejecutarlo él mismo para saberlo, o aprobar a ciegas. | flujo de verdict (`agent_completion_internal.py`), UI de revisión (doc 23) | El operador o gasta su tiempo re-verificando a mano (lo que el arnés podría darle hecho) o aprueba sin la señal y descubre el fallo después. La decisión humana se toma con menos información de la disponible. |
| **D-E5** | **No se mide la verificación ejecutable.** La telemetría tiene costo/turnos/contract/confidence (`harness/telemetry.py:122`); `harness_health` (H8) no cubre tasa de **verde-a-la-primera**, **% recuperado** por el pase correctivo, ni **verde falso atrapado**. | `harness/telemetry.py:122`, `services/harness_health.py` | Sin un número no se sabe cuántos entregables rotos se atajaron ni si el gate ayuda; no se afina lo que no se mide. |

**Lectura estratégica:** el 27 mejora lo que entra; el 28 que el proceso sobreviva; el 29 que cumpla el criterio semántico; el 30 que las referencias existan. El 31 cierra el quinto lado, el que un revisor humano hace por instinto: **ejecutarlo**. El entregable no solo "se ve bien" (forma) ni "menciona cosas que existen" (30): **funciona** (E0.1), y si no, se corrige una vez (E1.1) o se entrega con la verdad adjunta (E2.1); el "verde" vuelve a significar verde (E1.2); y todo se mide (E2.2). El operador no toca nada: recibe entregables que pasan sus pruebas y un verdict mejor informado.

---

## 4. Hoja de ruta

Tres fases priorizadas por **valor-por-esfuerzo** y por riesgo. Complejidad: S ≤ ½ día, M ≤ 2 días, L > 2 días (dev agéntico). Orden recomendado: **E0** (el juez ejecutable, en modo `annotate` para medir falsos positivos sin gatear) → **E1** (cerrar el lazo: gatear+corregir, y blindar el verde falso) → **E2** (amplificar el verdict humano + medir). Todos los flags default **OFF/0**; con todo en default, el comportamiento es **byte-idéntico** a hoy, runtime por runtime.

### FASE E0 — El juez ejecutable: correr lo que el proyecto ya tiene, barato-primero

---

#### E0.1 Motor de verificación ejecutable determinista (selección por tipo de artefacto + ejecución escalonada barata-primero, short-circuit, sandbox/timeout/budget, caché por content-hash) — el ítem fundacional

- **Ataca:** D-E1. Reusa el `cwd`/workspace y el patrón `subprocess` de los runners; NO inventa toolchain.
- **Frontera con lo existente (declarada):** el `contract_validator` (`post_run.py:62`) mira **forma**; el grounding 30/G1.2 mira **existencia estática**; E0.1 **ejecuta** los verificadores objetivos del proyecto sobre lo producido. Disjunto de ambos.
- **Problema + evidencia:** `finalize_run` decide el status sin ejecutar nada (`post_run.py:35,62,69,76`); el workspace con la toolchain existe (`claude_code_cli_runner.py:2003,643`) y se desperdicia post-run.
- **Propuesta (mínima):** un servicio `services/exec_verification.py::verify(workspace, changed_files, agent_type, runtime, budget) -> VerificationReport`, invocado en `finalize_run` **después** del contract validator y **antes** de fijar el status. Diseño:
  - **Registro de verificadores detectables (no inventados).** Cada verificador declara `applies(workspace, changed_files) -> bool` (por detección de toolchain/config presente) y `run(...) -> VerifierResult` (vía `subprocess` con `cwd`, timeout, sin red). Conjunto inicial, todos **opt-in por detección**: parseo de `.json`/`.yaml` producidos (stdlib, microsegundos); `py_compile` de `.py` cambiados; `tsc --noEmit` si hay `tsconfig.json`; lint a **nivel error** si la config existe (`ruff`/`eslint`); tests del subconjunto afectado si hay framework detectable (`pytest <paths>` / `npm test` / `dotnet test`). Si **ningún** verificador aplica → reporte `n/a` (no-op, **no es fallo**).
  - **Clasificación hard/soft.** **HARD** (gatean en E1.1): parseo inválido, no compila, type-check con errores, **tests en rojo**, lint a nivel **error**. **SOFT** (solo anotan, nunca gatean): warnings de lint, formato, cobertura. Un verificador que **no se pudo ejecutar** (toolchain ausente, timeout, error de infra) se clasifica **"could-not-verify" = soft** (degrada con gracia; **nunca** cuenta como fallo del entregable).
  - **Ejecución escalonada barata-primero + short-circuit (eficiencia incorporada).** Orden por costo: parse/compile (ms) → lint/type (s) → tests (lo caro). **Short-circuit:** ante el **primer fallo HARD**, se detiene (no se paga la suite si no compila). El presupuesto por dificultad sale de `estimate_complexity` (un `S` no merece la suite completa de un monorepo).
  - **Caché por content-hash (eficiencia).** El reporte se cachea por hash del fileset cambiado + versión de la toolchain; en un resume/re-finalize sobre artefacto idéntico, se reusa (no se re-ejecuta).
  - **Contención.** `cwd` acotado al workspace, **timeout duro por verificador** (`STACKY_EXEC_VERIFICATION_TIMEOUT_S`) y **budget global por run** (`STACKY_EXEC_VERIFICATION_BUDGET_S`), `env` sin secretos de red, sin escribir fuera de un build-dir temporal.
  - **Sello (claves NUEVAS, aditivas):** `metadata["exec_verification"] = {"mode": "annotate|gate", "ran": [...], "hard_failed": [...], "soft": [...], "passed": bool|null, "skipped_reason": str|null, "duration_ms": int}`. En **modo `annotate`** (default cuando el flag de modo lo permite) **solo anota**, no cambia el status — para medir falsos positivos antes de gatear.
- **Impacto esperado:** **resultado** — se atrapan entregables que no compilan / con tests rojos / JSON inválido antes de que lleguen al equipo. **Eficiencia** — barato-primero + short-circuit + caché hacen el gate de bajo costo; el chequeo caro solo corre cuando los baratos pasaron. Métrica: tasa de runs con `hard_failed` no vacío (entregables rotos atrapados), costo medio de verificación por run (E2.2).
- **Por qué es invisible:** el operador no configura toolchain ni corre nada; la verificación ocurre dentro del run que lanzó. Cero pasos nuevos.
- **Por qué NO viola rule 11:** ejecutar los verificadores objetivos del proyecto no decide trabajo ni publica; en modo `annotate` ni siquiera cambia el status — solo anota la verdad.
- **Salvaguarda de calidad (y cómo se mide):** **aditivo** — en el peor caso anota y no cambia nada; un verificador que no se pudo ejecutar **nunca** marca el entregable como roto (degrada a soft); `n/a` cuando nada aplica (no falla por "nada que verificar"). Flag OFF → `finalize_run` byte-idéntico. Se mide con tests: artefacto que compila y pasa → `passed=true`; artefacto que no compila → `hard_failed` poblado; nada aplica → `n/a`; toolchain ausente → `could-not-verify` (soft, no fallo); short-circuit corta antes de la suite; caché reusa en re-finalize idéntico; flag OFF → byte-idéntico.
- **Flag:** `STACKY_EXEC_VERIFICATION_ENABLED` (bool, default **false**) + `STACKY_EXEC_VERIFICATION_MODE` (str `off|annotate|gate`, default `off`) + `STACKY_EXEC_VERIFICATION_TIMEOUT_S` (int, default 120) + `STACKY_EXEC_VERIFICATION_BUDGET_S` (int, default 300) + `STACKY_EXEC_VERIFICATION_PROJECTS` (csv) + `FLAG_REGISTRY`.
- **TDD (`tests/test_exec_verification.py`):** detección de verificadores aplicables por fixture (con/sin `tsconfig`/tests/`.csproj`); HARD vs SOFT; short-circuit ante primer HARD; `could-not-verify` no es fallo; `n/a` cuando nada aplica; caché por hash; budget/timeout respetados (mock de `subprocess`); modo `annotate` no cambia status; flag OFF → byte-idéntico. Sin binarios reales (mock del runner de subprocess).
- **Complejidad:** M/L (motor + 2-3 verificadores iniciales; partible: PR1 parse/compile, PR2 tests/lint).

---

### FASE E1 — Cerrar el lazo: corregir el fallo ejecutable y blindar contra el "verde falso"

---

#### E1.1 Gate + pase correctivo único dirigido al fallo de verificación ejecutable (human-in-the-loop en caso de fallo) — el ítem de mayor valor

- **Ataca:** D-E2. EXTIENDE el seam de reparación (run_repair/autocorrect/Q1.1) con la señal ejecutable; reusa su transporte y comparte su presupuesto. NO re-implementa ninguno.
- **Frontera con lo existente (declarada):** `run_repair` (27/I1.1) dispara por **forma** (vacío/malformado); 29/Q1.1 dispara por **criterio semántico** (LLM). E1.1 dispara por **fallo ejecutable objetivo** (test rojo / no compila), detectado por E0.1 **sin LLM**. El **log del fallo ES el prompt correctivo** — no hay juicio.
- **Problema + evidencia:** la señal "no compila / test rojo" no dispara corrección hoy (`run_repair.py` solo forma; `cli_autocorrect.py` solo artifacts); el presupuesto de reparación existe sin consumidor para esta señal.
- **Propuesta (mínima):** cuando E0.1 corre en **modo `gate`** y hay `hard_failed` no vacío:
  - **Gate.** El status se degrada (no se presenta como `completed` un entregable que no pasa sus pruebas).
  - **Pase correctivo dirigido (una vez).** Si el runtime soporta resume/stdin (`capabilities.CAPABILITIES[runtime].supports_resume`) Y queda presupuesto: **un único** mensaje correctivo, corto y determinista, con el **excerpt del log del fallo** ("La verificación ejecutable falló: `<verificador>` → `<excerpt acotado del log>`. Corregí SOLO eso, manteniendo el resto del entregable; mismo formato.") por el MISMO transporte del autocorrect/run_repair. Se **re-verifica una vez** (reusa E0.1, que cachea): si ahora pasa → `completed` (`exec_verification.recovered=true`); si sigue fallando → `needs_review`.
  - **Presupuesto duro compartido.** `STACKY_EXEC_REPAIR_MAX_RETRIES` (int, default 1); el conteo se **comparte** con el autocorrect/`run_repair`/Q1.1 (mismo techo por run) para que el total de pases correctivos no se dispare. Alternativa aceptable y declarada: presupuesto propio acotado a 1, documentando el peor caso autocorrect(N)+run_repair(1)+criteria_repair(1)+exec_repair(1).
  - **Modelo/effort.** El pase usa el MISMO modelo y effort del run (dentro del clamp); NO escala.
  - **Sin resume → no repara (sin fallback silencioso):** degrada directo a `needs_review` con el reporte; nunca finge un fix.
  - **Sello:** `metadata["exec_verification"]["repair"] = {"attempted": bool, "failed_before": [...], "recovered": bool}`.
- **Impacto esperado:** **resultado** — entregables que fallaban una prueba ejecutable por un detalle se recuperan dentro del run. **Eficiencia** — menos ciclos de revisión humana + relanzamiento manual; se aprovecha el workspace ya montado. Métrica: `exec_verification.repair.recovered/attempted`; caída de `needs_review` por fallo ejecutable (E2.2).
- **Por qué es invisible:** el operador no relanza ni corrige a mano; ve el entregable ya pasando sus pruebas, o un `needs_review` con el log del fallo. Cero pasos nuevos.
- **Por qué NO viola rule 11:** el run lo lanzó el operador; la corrección ocurre DENTRO de ese run, antes de presentar; NO publica nada (verdict humano y publicación U1.3/U2.2 intactos); es exactamente lo que el operador haría (relanzar pidiendo que compile/pase el test). Si no recupera, **no decide**: va a `needs_review` con la verdad adjunta y el humano resuelve. Nunca oculta el fallo ni auto-publica un verde.
- **Salvaguarda de calidad (y cómo se mide):** el repair **no enmascara** mala calidad — solo salva lo objetivamente recuperable (que vuelva a pasar la MISMA prueba determinista); si no lo logra → `needs_review` (el gate ejecutable sigue siendo el juez); presupuesto duro de 1; sin resume → no repara. **Crítico:** el pase corrige el ENTREGABLE para pasar el test, **no** "ablanda el test" — la re-verificación corre el verificador original sin tocar (test inmutable durante el repair; cualquier cambio al propio test cuenta como nuevo artefacto a re-verificar, y dispara E1.2). Flag OFF → byte-idéntico (E0.1 en `annotate` o `off`). Se mide con la tasa de recuperación y la de `needs_review` por fallo ejecutable (E2.2).
- **Flag:** `STACKY_EXEC_REPAIR_ENABLED` (bool, default **false**) + `STACKY_EXEC_REPAIR_MAX_RETRIES` (int, default 1) + `FLAG_REGISTRY`. Depende de `STACKY_EXEC_VERIFICATION_MODE == gate`.
- **TDD (`tests/test_exec_repair.py`):** `hard_failed` + resume → un pase con el excerpt del log; recupera → `completed` + `recovered=true`; no recupera → `needs_review` + `recovered=false`; sin resume → no repara, `needs_review`; presupuesto compartido (no se suma a autocorrect/run_repair); re-verificación usa el verificador original (no se ablanda); modificar el propio test cuenta como nuevo artefacto; flag OFF → byte-idéntico. Mock de runner y de E0.1.
- **Complejidad:** M/L (toca el cierre de ambos runners CLI; partible: PR1 codex, PR2 claude).

---

#### E1.2 Guard anti-"verde falso": que "tests verdes" signifique algo

- **Ataca:** D-E3. Verificador determinista nuevo dentro del registro de E0.1; NO emite juicio semántico.
- **Frontera con lo existente (declarada):** E0.1 corre los tests y mira pass/fail; E1.2 inspecciona **los tests producidos por el agente** para detectar que **no prueban nada**. Distinto de "los tests pasan": acá la pregunta es "¿la suite verde es real?".
- **Problema + evidencia:** nada distingue "verde porque pasa" de "verde porque no prueba" (sin guard; `post_run.py` no inspecciona tests producidos); un agente puede entregar tests vacíos/`skip`/sin `assert` y reportar "todos verdes".
- **Propuesta (mínima):** un verificador determinista `fake_green_guard` que, **solo sobre los archivos de test que el run creó/modificó** (de `changed_files`), detecta señales objetivas de cobertura ilusoria: (a) la corrida reportó **0 tests colectados** ("0 passed" = sospechoso); (b) funciones de test **sin ningún `assert`/expect**; (c) **todos** los tests del archivo con `@skip`/`@pytest.mark.skip`/`xfail`/`it.skip`/`test.todo`; (d) cuerpo de test vacío o `pass`/`return` trivial. Detección por parseo determinista (AST de Python via `ast` stdlib; patrón léxico acotado para JS/TS). Clasificación: **soft-warn por defecto** (`exec_verification.fake_green=[...]`), **escalable a HARD** vía flag para proyectos donde el verde debe ser real. **Cero LLM.**
- **Impacto esperado:** **resultado** — "tests verdes" recupera su valor; se atrapa la cobertura ilusoria antes de que el equipo confíe en una red inexistente. **Eficiencia** — el chequeo es parseo (microsegundos), barato dentro del escalonado de E0.1. Métrica: nº de runs con `fake_green` no vacío (E2.2).
- **Por qué es invisible:** el operador no inspecciona los tests; recibe la señal de que el verde es real (o el aviso de que no). Cero pasos nuevos.
- **Por qué NO viola rule 11:** detectar que un test no prueba nada no decide ni publica; es una verificación objetiva sobre lo producido.
- **Salvaguarda de calidad (y cómo se mide):** **solo** inspecciona tests que el run **produjo** (no tests preexistentes del repo → cero falsos positivos sobre código ajeno); ante ambigüedad de parseo (no se pudo analizar) → no marca; por defecto **soft** (avisa, no rompe) hasta que un proyecto opte por HARD. Flag OFF → no corre. Se mide con fixtures: test sin assert → marcado; test con assert → limpio; 0 colectados → marcado; archivo de test ajeno (no en changed_files) → ignorado; parseo fallido → no marca; flag OFF → byte-idéntico.
- **Flag:** `STACKY_FAKE_GREEN_GUARD_ENABLED` (bool, default **false**) + `STACKY_FAKE_GREEN_GUARD_HARD` (bool, default **false**, escala a gate).
- **TDD (`tests/test_fake_green_guard.py`):** detección de test sin assert / solo-skip / 0-colectados / cuerpo trivial; exclusión de tests no producidos por el run; parseo fallido → no marca; soft vs hard; flag OFF → byte-idéntico.
- **Complejidad:** M.

---

### FASE E2 — Amplificar el verdict humano + medir (cerrar el loop)

---

#### E2.1 Reporte de verificación adjunto al entregable que el operador juzga (amplifica al humano, no lo reemplaza)

- **Ataca:** D-E4. Reusa la vista de verdict (23/U1.3) y la metadata que E0.1/E1.2 ya poblan; NO crea workflow nuevo ni saca al humano del lazo.
- **Frontera con lo existente (declarada):** el doc 23 hace **perceptible** el valor del run; E2.1 agrega una señal **objetiva y ejecutable** específica (compila / tests / lint) al mismo verdict, sin decidir por el operador.
- **Problema + evidencia:** el operador juzga sobre el texto sin saber si ejecuta (`agent_completion_internal.py`, UI doc 23); tiene que re-verificar a mano o aprobar a ciegas.
- **Propuesta (mínima):** renderizar `metadata["exec_verification"]` como un **bloque compacto y read-only** en la vista de revisión que el operador ya abre: un resumen verde/rojo ("✓ compila · ✓ 12/12 tests · ✓ lint" o "✗ 2 tests en rojo") con el **excerpt del log** colapsable para los fallos, y el aviso de verde falso si lo hubo. **Sin** botones nuevos que decidan: el operador conserva su verdict (aprobar/rechazar/pedir cambios) exactamente como hoy, ahora **mejor informado**. Degrada con gracia (sin metadata → no se muestra el bloque); compila con `tsc` (vitest no instalado → sin tests vitest obligatorios).
- **Impacto esperado:** **resultado/eficiencia** — el operador decide con la señal objetiva en pantalla; menos re-verificación manual, menos aprobaciones a ciegas. Es **amplificación** pura del centauro (doc 23/24), no autonomía.
- **Por qué es invisible:** se agrega a una vista existente; cero pasos nuevos, cero workflow nuevo. El operador ve *más verdad*, no *más trabajo*.
- **Por qué NO viola rule 11:** mostrar el reporte no decide nada; el verdict humano queda intacto. Es observabilidad dentro del flujo de aprobación, no una decisión automática.
- **Salvaguarda de calidad (y cómo se mide):** read-only puro; no altera el entregable ni el verdict; fuente ausente → degrada ("—"). Flag OFF → la vista no agrega el bloque (byte-idéntico). Se mide cualitativamente (el operador reporta decidir con más contexto) y con el uso del bloque.
- **Flag:** `STACKY_EXEC_VERIFICATION_VERDICT_CARD_ENABLED` (bool, default **false**).
- **TDD:** test del shape del payload que la API expone (backend, con datos sintéticos: pasa/falla/verde-falso/ausente → el bloque correcto o degradación); UI solo `tsc` (sin vitest obligatorio).
- **Complejidad:** S/M.

---

#### E2.2 KPIs de verificación ejecutable en harness-health (read-only, sin UI nueva)

- **Ataca:** D-E5. Extiende `harness_health` (H8) y la `HarnessHealthCard` existente; NO crea UI nueva.
- **Problema + evidencia:** la telemetría no mide verificación ejecutable (`harness/telemetry.py:122`); `harness_health` no lo cubre.
- **Propuesta (mínima):** un bloque de **verificación ejecutable** en `services/harness_health.py`, por proyecto y ventana, leyendo `metadata["exec_verification"]` que E0.1/E1.1/E1.2 pueblan: `tasa_verde_a_la_primera` (passed sin repair / verificados), `tasa_recuperacion_exec_repair` (`repair.recovered/attempted`), `entregables_rotos_atrapados` (`hard_failed` no vacío), `verde_falso_atrapado` (`fake_green` no vacío), y `costo_medio_verificacion_ms`. Read-only.
- **Impacto esperado:** la verificación ejecutable se vuelve un **número visible** en la pantalla que el operador/management ya consultan → se afina dónde invertir y se valida que el gate ayuda. Métrica: el propio dashboard.
- **Por qué es invisible:** se agrega a una card existente; cero pasos nuevos.
- **Por qué NO viola rule 11:** mostrar números no decide nada; es observabilidad.
- **Salvaguarda de calidad (y cómo se mide):** definiciones explícitas y testeadas; read-only puro; fuente ausente → degrada ("—"). Flag OFF → la card no agrega el bloque (byte-idéntico). Se mide con un test del endpoint con datos sintéticos.
- **Flag:** `STACKY_EXEC_VERIFICATION_KPIS_ENABLED` (bool, default **false**).
- **TDD (`tests/test_harness_health_exec_verification.py`):** con runs sintéticos (verde a la primera, recuperado por repair, roto atrapado, verde falso) → KPIs correctos por proyecto/ventana; fuente ausente → degrada; flag OFF → sin bloque nuevo.
- **Complejidad:** M.

---

## 5. Priorización y secuencia

| Orden | Ítem | Complejidad | Valor | Riesgo | Dependencias |
|---|---|---|---|---|---|
| 1 | **E0.1** Motor de verificación ejecutable (annotate) | M/L | **Muy alto (atrapa entregables rotos)** | Bajo en `annotate` (no gatea, flag OFF) | `cwd`/workspace + `subprocess` (en código) |
| 2 | **E1.1** Gate + pase correctivo dirigido al fallo ejecutable | M/L | **Muy alto (recupera dentro del run)** | Medio (toca cierre de runners → flag, comparte presupuesto) | E0.1; seam run_repair/autocorrect (en código) |
| 3 | **E1.2** Guard anti-verde-falso | M | **Alto (el verde vuelve a valer)** | Bajo (parseo, soft por defecto) | E0.1 (registro de verificadores) |
| 4 | **E2.1** Reporte adjunto al verdict (amplifica al humano) | S/M | Alto (decisión mejor informada) | Bajo (read-only, degrada) | E0.1 puebla datos |
| 5 | **E2.2** KPIs de verificación ejecutable | M | Alto (cierra el loop) | Bajo (read-only) | E0.1/E1.1/E1.2 pueblan datos |

**Rollout gradual (mismo patrón que `STACKY_SELF_REVIEW_MODE` off/annotate/gate):** (1) `off` → byte-idéntico; (2) `annotate` global → E0.1 corre y **solo anota**, se miden falsos positivos y costo real sin gatear; (3) `gate` en proyectos piloto vía `STACKY_EXEC_VERIFICATION_PROJECTS` + `STACKY_EXEC_REPAIR_ENABLED`; (4) `gate` general cuando la tasa de falsos positivos en `annotate` sea aceptable. E1.2 entra **soft** y escala a HARD por proyecto. Cada paso reversible bajando el flag.

**Reglas de implementación (las 7 del doc 22 + las de frontend del doc 23 aplican íntegras):** TDD; validar **por archivo de test** con el python del `.venv` (suite contaminada; pin pywin32==306 roto en 3.13); flag nuevo = `config.py` + `FLAG_REGISTRY` mismo PR; metadata solo claves **nuevas** (`exec_verification` y sub-claves); default **OFF/0** (retro-compat **byte-idéntica** — con todos los flags en default, el resultado es EXACTAMENTE el de hoy, runtime por runtime); ADO solo por los caminos existentes (este plan **no agrega escrituras**; la verificación es read-only sobre el workspace local); **sin fallback silencioso entre runtimes** (E1.1 no repara sin resume; los verificadores se cablean por workspace); **sin deps npm/py nuevas** (la verificación usa la toolchain del proyecto vía `subprocess`; si no está → skip); UI (vista de verdict + DiagnosticsPage) degrada con gracia y compila con `tsc` (vitest no instalado: sin tests vitest obligatorios).

**Regla 11 (innegociable, eje de este plan):** invisible ≠ autónomo. Doctrina: (a) cada acción es **ejecución determinista de verificadores objetivos** dentro de un run que el operador lanzó, antes de presentar; (b) lo que se chequea es pass/fail objetivo de una herramienta (compila, test, parse), nunca contenido; (c) la única "corrección" (E1.1) reusa el seam de reparación contra una prueba objetiva, **una vez**, y si no recupera va a `needs_review` con el log; (d) **nada publica, transiciona ADO ni oculta un fallo**; (e) lo que muestra (E2.1) **amplifica** el verdict humano sin reemplazarlo; (f) lo que mide (E2.2) produce números, no mutaciones. Cada ítem trae su línea "Por qué NO viola rule 11".

---

## 6. Qué va a notar cada audiencia (antes → después)

### Operador (que NO configura ni ve estos mecanismos)
- **Hoy:** lanza un run; a veces el entregable "se ve bien" pero no compila, tiene tests en rojo, o el JSON que generó es inválido — y lo descubre cuando lo ejecuta él, o cuando el equipo lo reporta; cuando aprueba, lo hace sobre el texto, sin saber si funciona.
- **Después (sin tocar nada):** el mismo run sale pasando sus propias pruebas (compila, tests verdes reales, lint OK); lo que falla se corrige una vez dentro del run o llega a `needs_review` con el log del fallo a la vista; y cuando aprueba, lo hace con un "✓ compila · ✓ 12/12 tests" en pantalla. No ve ninguna perilla nueva: solo nota que Stacky "entrega cosas que funcionan".

### Desarrollador / equipo (que vive en ADO)
- **Hoy:** a veces recibe artefactos que no compilan o con cobertura ilusoria ("tests verdes" que no prueban nada).
- **Después:** recibe artefactos que pasaron compilación/tests/lint objetivos, con el verde respaldado por tests reales (anti-verde-falso) — sin cambios en cómo Stacky escribe.

### Management
- **Hoy:** no hay número de "entrega que ejecuta"; los entregables rotos son anecdóticos.
- **Después:** tasa de verde-a-la-primera, recuperación del pase correctivo, entregables-rotos-atrapados y verde-falso-atrapado en la DiagnosticsPage existente (E2.2) — la corrección ejecutable se vuelve medible sin sumar trabajo operativo.

---

## 7. Ventaja competitiva: por qué ejecutar antes de entregar gana

1. **Un CLI suelto entrega texto; el arnés entrega algo que pasó sus pruebas.** Un CLI suelto declara "listo" sin compilar ni correr un test. Stacky, dentro del run que el humano lanzó, **ejecuta los verificadores objetivos del proyecto** antes de presentar — y si fallan, corrige una vez o entrega la verdad — sin cruzar la línea de la autonomía (no publica, no decide; el humano firma).
2. **El verde deja de ser una promesa y pasa a ser un hecho.** Compilar y correr los tests del propio proyecto, más el guard anti-verde-falso, convierte "el agente dice que anda" en "el arnés lo comprobó" — la clase de garantía que ningún modelo, por bueno que sea, da por su cuenta.
3. **La corrección ejecutable es barata y certera.** El log del fallo es el mejor prompt posible: específico, objetivo, sin ambigüedad semántica. Un único pase dirigido contra una prueba determinista recupera más por token que cualquier reescritura a ciegas — y se apoya en el workspace que el run ya tenía montado.

---

## 8. Métricas de éxito del plan

| Métrica | Hoy | Objetivo | Fuente |
|---|---|---|---|
| Entregables que no compilan / con tests rojos que igual se entregan | ocurren (se descubren tarde) | atrapados antes de entregar | `exec_verification.hard_failed` (E0.1) + E2.2 |
| Tasa de verde-a-la-primera (pasa sin repair) | no medida | medible y creciente | E2.2 |
| Recuperación del pase correctivo ejecutable (`recovered/attempted`) | n/a | alta y medible | `exec_verification.repair` (E1.1) |
| Verde falso (tests que no prueban) atrapado | invisible | detectado | `exec_verification.fake_green` (E1.2) + E2.2 |
| Costo medio de verificación por run | n/a | bajo (barato-primero + caché) | E2.2 |
| Verdict humano informado por señal ejecutable | aprueba sobre el texto | aprueba con "compila/tests/lint" a la vista | E2.1 |
| Calidad de entregables tras los chequeos | n/a | **no debe caer** (aditivos) | E2.2 + KPIs del 29/30 |
| Perillas nuevas que el operador debe tocar | — | **cero** (flags internos, default OFF) | — |

---

## 9. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Ejecutar verificadores corre código potencialmente peligroso | `cwd` acotado al workspace del run, **timeout duro por verificador**, **budget global**, sin red, sin escribir fuera de un build-dir temporal; verificador no contenible no se cablea (anti-scope §3). |
| Un verificador falla por infraestructura (toolchain ausente, timeout) y marca un entregable bueno como roto | Se clasifica **"could-not-verify" = soft**; **nunca** cuenta como fallo del entregable; `n/a` cuando nada aplica. Cero falsos negativos sobre trabajo válido. Se valida primero en modo `annotate`. |
| El gate (E1.1) bloquea un entregable que el operador igual quería ver | Nunca bloquea silenciosamente: degrada a `needs_review` **con el log adjunto**; el operador conserva el verdict. Rollout `annotate` antes de `gate` mide falsos positivos. |
| El pase correctivo "ablanda el test" para pasar en vez de arreglar el código | La re-verificación corre el **verificador original inmutable**; modificar el propio test cuenta como **nuevo artefacto** y dispara E1.2 (anti-verde-falso). El gate sigue siendo el juez objetivo. |
| Verificación cara (suite completa de un monorepo) infla costo/latencia | Barato-primero + **short-circuit** (no se paga la suite si no compila) + **caché por content-hash** + presupuesto por dificultad (`estimate_complexity`); solo el subconjunto afectado cuando se puede. |
| El guard anti-verde-falso (E1.2) marca tests legítimos | Solo inspecciona tests que el run **produjo** (no preexistentes); ante parseo ambiguo no marca; **soft** por defecto hasta opt-in HARD por proyecto. |
| Confundir E0.1 con el grounding del 30/G1.2 o el contract del harness | Frontera declarada: G1.2 = existencia **estática** de referencias; contract = **forma**; E0.1 = **ejecución dinámica**. Disjuntos. |
| Doble pase correctivo entre autocorrect/run_repair/Q1.1/E1.1 | Presupuesto **compartido** (mismo techo por run); peor caso documentado; sin resume → no repara. |
| Sin resume, E1.1 no puede corregir | Sin fallback silencioso: degrada a `needs_review` con el reporte; `capabilities` declara la diferencia por runtime. |

---

## 10. Roadmap por fases (estado)

| Fase | Ítem | Estado |
|---|---|---|
| E0 | E0.1 Motor de verificación ejecutable (annotate) | PROPUESTO |
| E1 | E1.1 Gate + pase correctivo dirigido al fallo ejecutable | PROPUESTO |
| E1 | E1.2 Guard anti-verde-falso | PROPUESTO |
| E2 | E2.1 Reporte adjunto al verdict (amplifica al humano) | PROPUESTO |
| E2 | E2.2 KPIs de verificación ejecutable | PROPUESTO |

**Estado global:** PROPUESTO (0/5 implementado al 2026-06-15). Con todos los flags en default OFF/0, el comportamiento es **byte-idéntico** al actual, runtime por runtime. El plan cierra el quinto lado del motor — **la verificación ejecutable del entregable** (que lo producido pase sus propias pruebas objetivas antes de entregar) — con chequeos **deterministas, cero LLM en el chequeo, barato-primero y sin fricción para el operador**, reusando el `cwd`/workspace, el `subprocess` y el seam de reparación que el código ya tiene, sin re-implementar el motor (27), el lifecycle (28), el juicio semántico (29) ni la verificación de existencia (30), y sin sacar al humano del lazo.
