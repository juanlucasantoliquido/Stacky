# Plan 262 — Recuperación en caliente del QA UAT: una ruta inválida NO es una caída

> Estado: **v1 -> v2 · RECHAZADO en v1, CORREGIDO en v2** — criticado adversarialmente. Pipeline: proponer ✓ → **criticar ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar (`supervisar-implementaciones-planes`).
>
> **Juez v2: subagente independiente, misma corrida, contexto limpio.**
>
> Veredicto de la crítica: **RECHAZADO** (7 BLOQUEANTES). Todos resueltos **dentro de este documento**; el v2 es implementable.
>
> Autor v1: Claude Opus 5 (1M context) en rol **StackyArchitectaUltraEficientCode**, perfil `normal`. **Corrección v2:** juez adversarial, perfil `normal`, que abrió los archivos reales y **corrió los baselines** en vez de heredarlos.
>
> Runtimes objetivo: **Codex CLI, Claude Code CLI, GitHub Copilot Pro** — paridad obligatoria. El núcleo de este plan es **100 % determinista y sin LLM**: clasificar una excepción no puede depender de que un modelo esté disponible.

---

## 0. CHANGELOG v1 -> v2

**Los 7 BLOQUEANTES y cómo quedaron resueltos:**

- **C1 — Baseline FALSO: `test_plan259_ratchet_script_parity.py` está VERDE.** El v1 lo declaraba `1 failed, 11 passed` con *"65 archivos solo en el .sh (maximo 64)"*. **Medido: `12 passed`.** El lag real es **exactamente 64** contra `_PS1_LAG_MAX = 64` y el assert es `<=` (`:93`), así que **pasa con CERO holgura**. Los criterios A2.7 y D-12 del v1 (*"sigue en 1 failed y el mensaje sigue diciendo 65"*) eran **insatisfacibles**: no hay mensaje que leer. **Fix:** criterio ABSOLUTO `12 passed`, y el gate-contra-el-defecto pasa a ser *registrar sólo en el `.sh` ⇒ `1 failed` diciendo **66***. Además el lag sin holgura convierte el registro en el `.ps1` en **dependencia dura**, no en buena práctica.
- **C2 — El "gate anti-deriva" de códigos de navegación pasaba CON el defecto, y el conteo era falso.** Los códigos reales del driver son **11**, no 10; falta **`NAV_WRONG_SCREEN`** (`navigation_driver.py:569`), que es justamente *"pantalla equivocada"* — el caso central del pedido. Y `_classify_error` devuelve sólo **8** (`:872,875,877,879,882,884,886,887`), así que el extractor propuesto (regex sobre `_classify_error`) obtenía 8 ⊆ 10 y el assert **pasaba dejando 3 códigos sin mapear**. **Fix:** el mapa cubre los **11**, `NAV_WRONG_SCREEN -> ROUTE_ERROR`, y el gate escanea **todo el archivo** y es **bidireccional** (ni huérfanos ni entradas fantasma).
- **C3 — `hot_recovery.recover()` NO TENÍA CALL SITE: el plan repetía el pecado que denuncia.** `uat_test_runner.run` llama `_run_all_specs_once` **una vez** (`:172`) y después sólo **agrega contadores** (`pass_count`/`fail_count`/`blocked_count`, `:236-238`): **no existe ningún punto en Python donde una excepción por caso emerja**. F8 sólo cablea el catch-all del pipeline, que dispara ante un crash de Python, **no** ante un spec fallido. Los criterios (d)(e)(f) del operador quedaban implementados como código inalcanzable — exactamente como `_run_single_spec` hoy (§2, hecho 5). **Fix:** nueva **F7.2** que nombra el call site EXACTO, con archivo de test propio y un gate que asserta que `recover` **se llama de verdad**.
- **C4 — `AGENDA_WEB_BASE_URL` en `_QA_UAT_FLAG_KEYS` PISA el valor del operador.** `_export_qa_uat_flags` hace asignación incondicional (`os.environ[_k] = val`, `:110`) y su docstring **prohíbe** `setdefault`. Hoy ese valor **no existe en el backend** (0 hits de `AGENDA_WEB_*` en todo `backend/**.py`): sale del entorno del operador. Con la key registrada, **todo run lanzado desde la UI sobrescribe la URL base con el default `35017`** ⇒ probe contra la URL equivocada ⇒ `alive=False` ⇒ `SERVICE_DOWN` ⇒ **"la Agenda Web está caída", el bug que este plan viene a matar, ahora causado por el plan** y violando INV-8. Divergencia real medida: `.secrets\agenda_web.env.example:7` trae `http://localhost/AgendaWeb/` **sin puerto** y el `.env` vivo trae `35017`. **Fix:** declaración env-first obligatoria en `config.py` + **test de idempotencia** del export + prohibición de que cualquier criterio dependa de la línea en `harness_defaults.env`.
- **C5 — `FlagSpec.type` SÍ soporta `"str"`.** El v1 afirmaba como verificado que no existe (anclado a `harness_flags.py:23`) y sobre esa afirmación falsa construía un compromiso de diseño: declarar dos valores de un solo elemento como `csv` y sostener un test de *"la lista tiene exactamente 1 elemento"*. **Medido: `type="str"` se usa 10 veces** en `FLAG_REGISTRY` (`:1988, 2030, 3867, 3933, 3958, 3969, 4007, 4691, 4859, 4872`) y el panel lo renderiza (`HarnessFlagsPanel.tsx:157`). El comentario de `:23` está simplemente **stale**. **Fix:** `STACKY_QA_UAT_SAFE_ROUTE` y `AGENDA_WEB_BASE_URL` pasan a `type="str"`; se elimina el desenvolvimiento y su test.
- **C6 — INV-4 era insatisfacible por la propia F9.** Prometía *"exactamente una función que hace el probe HTTP"*, pero F9 declara explícitamente que *"el resto del módulo no se toca"* y `environment_preflight._http_get` (`:225`, con su `_attempt` interno) **sobrevive intacto** y se sigue usando en `:164` y `:181`. El gate de F9 sólo contaba el frozenset, nunca las funciones de probe. **Fix:** INV-4 se reescribe honestamente (*una sola DEFINICIÓN de alive codes*), `_http_get` queda declarado fuera de alcance **con motivo**, y el gate cuenta implementaciones de probe contra una allowlist de **2** nominadas.
- **C7 — La aritmética del DoD se contradecía a sí misma.** D-1 listaba `2, 11, 12, 22, 20, 16, 8, 18, 12, 10, 12, 14` (= **157**) y en la misma celda exigía **189**; §9.1 declaraba *"205 casos"* y *"13 archivos"* cuando eran **173** en **12**. Un criterio binario que no cierra numéricamente no se puede satisfacer. **Fix:** totales recalculados y verificables sumando la columna.

**IMPORTANTES resueltos:**

- **C8 —** El `[NO VERIFICADO]` nº1 (¿el panel de flags renderiza `int`/`float`/`csv`?) queda **RESUELTO A FAVOR**: `HarnessFlagsPanel.tsx` renderiza `bool:94`, `int:115` (`<input type="number" step="1" min max>`), `float:130`, `csv:145`, `str:157`, `json:169`, y pinta el hint de bounds en `:293-301`. **R-4 desaparece y con él la tarea manual nº1 del operador.**
- **C9 —** "Reintentos configurables" quedaba a medias: F6 unificaba `QA_NAV_RETRIES` pero lo dejaba **env-only**, contra el riel *toda config del operador va por UI*. **Fix:** `QA_NAV_RETRIES` se registra como flag (int, bounds `(0,10)`, default **3** = el efectivo de hoy).
- **C10 —** F0.3 arreglaba **la mitad** de la mentira: `config.py:1230-1231` sigue diciendo `# Default OFF por EXCEPCION DURA #3` justo encima del `"true"`. Y su test *"buscar el segundo argumento de `os.getenv`"* **falla con un regex por línea**: la key está en `:1232` y el default en `:1233`. **Fix:** se corrigen las dos mentiras y se especifica el regex multilínea.
- **C11 —** F1 introducía un **cuarto** hardcode de `http://localhost:35017/AgendaWeb/` en el mismo plan cuya F9 borra uno y asserta 0 hits en otro archivo. **Fix:** una sola constante canónica.
- **C12 —** F10.2 no decía **quién** adjunta `recovery_report`: `_blocked_result(spec_file, scenario_id, reason)` (`:1003`) no tiene parámetro para eso. **Fix:** lo adjunta el call site de F7.2, que es el único dueño del dict del caso.
- **C13 —** F9 decía *"conservando su dict de retorno exacto"* sin nombrar las claves. **Medido: `_check_http` devuelve exactamente `ok`, `label`, `status`, `error`** en sus 5 ramas — y `HealthProbe` no tiene `ok` ni `label`, así que hace falta un adaptador explícito.
- **C14 —** F5 leía `_CLASS_TO_TAXONOMY` (privado, de otro módulo) con indexación directa. **Fix:** F3 expone `is_recoverable(recovery_class) -> bool` y F5 la usa.

**Anclajes corregidos con la línea REAL (no borrados):** `qa_uat_pipeline.py` traceback `:704 -> :706`; `stages["evaluator"]/all_scenarios_blocked` `:3090 -> :3170`; `environment_preflight` `rstrip("/")+"/"` `:76 -> :77` y uso de `run_environment_preflight` `:247 -> :279` (`:247` es un uso de `_ALIVE_STATUS_CODES`, no la función); `agenda_web_launcher` `started_by_us` del stop `:179 -> :187`; `uat_test_runner` dossier `:292-293 -> :293-294` (y **no es un dossier**: es el sub-dict `"meta"` del retorno de `run()`, abierto en `:279`); `harness_flags.default_is_known` `:5816 -> :5814`; `harness_flags_help.PlainHelp` `:19 -> :18`; `test_harness_ratchet_meta._SCRIPT` `:14 -> :13` y `_TESTS_DIR` `:16 -> :15`.

**Los 7 `[NO VERIFICADO]` del v1, resueltos:** (1) panel de flags **OK, renderiza los 6 tipos** (C8); (2) `harness_defaults.env`: **NINGUNO es "el fuente"**, los dos los genera `deployment/export_harness_defaults.py` (header idéntico), y `backend/harness_defaults.env` es el snapshot **PARCIAL** (3 009 B vs 13 719 B) que el build refresca (`build_release.ps1:343, :516-531`); (3) archivos que leen `AGENDA_WEB_BASE_URL`: **54 de código** (217 contando `evidence/`), no ~20; (4) `.secrets\agenda_web.env.example` **NO está en el tool**: está en la raíz del repo y trae `http://localhost/AgendaWeb/` **sin puerto** — verificado, y ahora es evidencia de C4; (5) `# noqa: BLE001` en `uat_test_runner.py`: **16**, no ~40; (6) `harness_flags.py:519/533/567/582/2091` de las 5 `FlagSpec` QA UAT: **las 5 OK**; (7) módulos `.py` del tool: **166 en la raíz / 281 en el árbol**, no ~180.
>
> **Origen — pedido textual del operador:** *"El agente QA UAT debe recuperar automáticamente la Agenda Web y corregir rutas inválidas durante la ejecución de pruebas"*. Hoy, cuando durante una prueba se produce una excepción por una ruta incorrecta, inexistente, no permitida o mal seleccionada, la ejecución se interrumpe y el agente interpreta erróneamente que la Agenda Web no está disponible.
>
> **Nota de numeración (cadena de evidencia, verificada en frío el 2026-07-29; no re-resolver):** el tope con archivo en `Stacky Agents/docs/` es **271**. El **261 está RESERVADO** por `260_PLAN_NINGUNA_PIPELINE_CORRE_A_CIEGAS_...:1837` (reafirmado en `:1842`). El **272 está RESERVADO 2×** (`271_PLAN_...:6` y `270_PLAN_...:1517`). El **273 está sugerido** por `270_PLAN_...:1575`. El **262 está LIBRE** según 4 fuentes independientes: `260_PLAN_...:1842`, `267_PLAN_...:8`, `271_PLAN_...:6` y `_supervision/PAQUETES_PARALELIZACION_2026-07-28_v2.md:82`. Este plan toma **262**.

---

## 1. Objetivo

Hacer que el agente QA UAT **distinga la causa de una excepción durante la corrida** y se recupere sin abortar todo. Hoy el pipeline tiene un único decisor de "la app está caída" y corre **una sola vez, antes** de abrir el navegador (`qa_uat_pipeline.py:run:400`); cualquier excepción posterior cae en un catch-all que la sepulta como `BLOCKED / OPS / PIPELINE_CRASH` (`qa_uat_pipeline.py:690`, `:702`) **sin volver a preguntar si la app responde**. El resultado es el síntoma que reporta el operador: una ruta mal construida o una pantalla que no admite `goto()` se lee como "AgendaWeb no está disponible", y el run entero muere. Este plan introduce un **probe de salud independiente en caliente**, una **taxonomía determinista de 5 clases de recuperación**, una **allowlist de rutas con ruta segura**, un **presupuesto anti-bucle**, **reintento acotado al caso** (cableando código que ya existe y está muerto) y la **configuración por UI** de reintentos, esperas, URL base y rutas permitidas.

### KPI / impacto medible

| Métrica | Hoy (medido / derivado del código) | Después |
|---|---|---|
| Excepciones no previstas clasificadas con evidencia de salud | **0 %** — `qa_uat_pipeline.py:690` sepulta todo en `PIPELINE_CRASH` sin probe | **100 %** — probe obligatorio antes de rotular |
| Chequeos de disponibilidad por run | **1 o 2** (`run_environment_preflight` en `:400`, y un re-preflight en `:409` sólo si hubo autostart) | **1 + N** (uno por excepción candidata, con cota `RECOVERY_MAX_PER_RUN`) |
| Unidad mínima que muere por una excepción de navegación | **el run completo** (el catch-all envuelve `_run_pipeline_stages`, `:670`) | **el caso afectado**; el resto continúa |
| Decisores duplicados de "app viva" | **3** copias del frozenset, verificadas por grep sobre los `*.py` del tool: `environment_preflight.py:62`, `smoke_path_checker.py:40`, `agenda_web_launcher.py:78` | **1** definición (`agenda_health`), las otras dos son alias |
| Parámetros de recuperación configurables por UI | **0** — las env vars del tool se leen crudas de `os.environ` | **9** en `FLAG_REGISTRY` (1 bool + 5 numéricas con bounds + 1 csv + 2 str) |
| `QA_UAT_MAX_NAVIGATION_RETRIES` efectiva por el camino del runner | **inerte** — variable muerta en `uat_test_runner.py:136` (1 solo hit en el archivo) | efectiva y con **un solo nombre canónico** |
| Reporte de un caso no recuperable | sin ruta usada ni conteo de intentos | **ruta usada + excepción + intentos + motivo final** obligatorios |

---

## 2. La tesis del plan / por qué ahora

**Tesis: el pipeline QA UAT tiene un buen detector de caída y lo corre en el peor momento posible — una sola vez, antes de que pueda pasar algo.**

Cinco hechos verificados sostienen esto:

1. **El único decisor de "caída" corre ANTES, nunca durante.** `qa_uat_pipeline.py:run` llama `preflight = run_environment_preflight()` en `:400`, y sólo si `not preflight.ok and preflight.reason == "APP_NOT_RUNNING"` (`:404`) importa `ensure_agenda_web` (`:406`), la invoca (`:407`) y hace **UN** re-preflight (`:409`). Después de esa línea, nadie vuelve a preguntar si la app responde en todo el run.

2. **El catch-all sepulta la causa.** `qa_uat_pipeline.py:690` es `except Exception as _pipeline_crash:  # noqa: BLE001` envolviendo la llamada a `_run_pipeline_stages` de `:670`. El dict abre en `:697` y produce `verdict="BLOCKED"`, `category="OPS"`, `reason="PIPELINE_CRASH"` (`:702`). El plan 241 F6 hizo lo correcto agregando el traceback (`"traceback": _crash_tb[-2000:]`, **`:706`** — v2: el v1 decía "dos líneas más abajo", son cuatro), pero el **rótulo sigue siendo el mismo para una caída real y para un `urljoin` mal hecho**.

3. **El preflight está diseñado explícitamente para NO reintentar.** `environment_preflight.py:53` dice literal *"We do NOT retry — fail fast."*, con `_CHECK_TIMEOUT_S: float = 5.0` (`:54`). Eso es **correcto para un preflight** y **equivocado como única política de todo el run**: la app puede estar reiniciando su AppPool en el segundo 40 de una prueba de 6 minutos.

4. **Ya hay tres implementaciones de "¿está viva?" que no se conocen entre sí.** `environment_preflight._ALIVE_STATUS_CODES` (`:62`) es la definición canónica; `smoke_path_checker.py:40` la **copia literal**; `agenda_web_launcher._responds` (`:73`) intenta importarla y si falla **la vuelve a hardcodear** en `:78`. Tres copias del mismo `frozenset({200, 301, 302, 400, 401, 403})`. Agregar una cuarta sería el error obvio; este plan agrega **una** y hace que las tres deleguen.

5. **La maquinaria de reintento por caso ya está escrita y está muerta.** `uat_test_runner._run_single_spec` (`:1031`, firma completa **verificada**: `(spec_file: Path, scenario_id: str, scenario_dir: Path, ticket_id: int, headed: bool, timeout_ms: int, verbose: bool, exec_log=None) -> dict`, posicional, `exec_log` con default) tiene **exactamente 1 hit en todo el árbol del tool: su propia definición** (0 referencias en cualquier otro `.py`/`.ts`/`.md`). Lo que se ejecuta es `_run_all_specs_once` (`:301`), invocada una única vez desde `:172`, que lanza **un** subprocess `npx playwright test` con **todos** los specs; y cuando ese subprocess expira, `except subprocess.TimeoutExpired:` (`:421`) mata el proceso y `_timeout_result` (`:1016`) marca **TODOS** los specs como `BLOCKED/TIMEOUT`. El reintento acotado al caso no hay que inventarlo: hay que **cablearlo**.

   > **v2 / C3 — y ahí está el agujero que el v1 no vio.** Después de `:172`, `run()` **no itera los casos para nada más que contarlos**: `pass_count`/`fail_count`/`blocked_count` (`:236-238`) son tres `sum(...)` sobre `runs`, y de ahí se va derecho a `_classify_and_emit_runner_summary`. **No existe ningún sitio en Python donde una excepción de UN caso emerja**, porque la excepción vive y muere dentro del subprocess de Playwright. Un plan que escriba `hot_recovery.recover()` sin nombrar el call site produce **otro `_run_single_spec`**: código correcto, probado con mocks, y jamás ejecutado. Por eso el v2 agrega **F7.2**, que no escribe lógica nueva: escribe **la línea que la llama**.

**Y un bug vivo que este plan cierra porque es el mismo problema en miniatura.** `uat_test_runner.py:136` declara `max_nav_retries = int(os.environ.get("QA_UAT_MAX_NAVIGATION_RETRIES", "1"))`. Esa variable tiene **1 solo hit** en el archivo: se asigna y no se usa nunca. Contraste medido en el mismo archivo: `max_browser_launches` (`:134`, default `"1"`) y `max_login_attempts` (`:135`, default `"1"`) tienen **6 hits cada una** (`134,193,196,201,204,294` y `135,215,218,223,226,293`) y llegan al **sub-dict `"meta"` del retorno de `run()`** en **`:293-294`** — v2: el v1 decía "el dossier" y "`:292-293`", ambos incorrectos; `"meta"` abre en `:279` y cierra en `:295`. `max_total_min` (`:139`, default `"6"`) se usa en `:292`. Del otro lado, `playwright/helpers/navigation_executor.ts:allowedAttempts:375` lee `process.env.QA_UAT_MAX_NAVIGATION_RETRIES ?? process.env.QA_NAV_RETRIES ?? 0` (`:377`) y capa el pedido del paso con `Math.min(Math.max(0, requestedRetries), allowedRetries)` (`:382`). **Precisión importante y contraintuitiva: el retry TS NO está capado a 0.** El runner exporta `QA_NAV_RETRIES` con default `"3"` en `uat_test_runner.py:343`, sobre un `env = {**os.environ, ...}` (`:337`), así que `allowedAttempts` resuelve a 3 intentos. El defecto real es doble: **(a)** la env var *documentada* como cota de reintentos de navegación es **inerte por el camino del runner**, y **(b)** hay **dos nombres para el mismo concepto con defaults distintos** (1 en Python, 3 en TS) y el que gana en el TS es justamente el que Python nunca exporta. Eso es una bomba de relojería: el día que alguien exporte `QA_UAT_MAX_NAVIGATION_RETRIES=1` "para arreglar el warning", los reintentos de navegación bajan de 3 a 1 **en silencio**.

**Por qué ahora.** Los planes 214, 240 y 241 dejaron el QA UAT capaz de navegar, autenticarse, arrancar la app y emitir un veredicto funcional honesto. Con eso funcionando, el cuello de botella dejó de ser "no puede navegar" y pasó a ser "cualquier tropiezo mata el run entero y miente sobre la causa". Es exactamente el momento de atacar la resiliencia, y no antes: sin el veredicto honesto del 241, una capa de recuperación habría sido una máquina de generar falsos verdes.

---

## 3. Frontera explícita contra los planes 214 / 240 / 241

Leí los headers de los tres. Estado declarado: **214 COMPLETO F0..F6**, **240 v3 APROBADO-CON-CAMBIOS (implementado F0..F8)**, **241 v2 APROBADO-CON-CAMBIOS (implementado F0..F9)**.

### 3.1 Qué es de ellos y NO se toca

| Plan | Es suyo | Cómo lo trata este plan |
|---|---|---|
| **214 F1** | KB de navegación (`navigation_kb.py`) + curación de playbooks | **Sólo lectura.** Este plan no escribe en la KB. |
| **214 F2** | `wait_aspnet_idle`, `NavigationDriver.assert_arrival`, y la rama `NAV_DEVIATION` en `navigation_driver._classify_error` (`:872`) | **REUSA los códigos**, no los reimplementa. `NAV_DEVIATION` es una **entrada** de mi clasificador, no una salida. |
| **214 F3** | Disparo post-desarrollo por `on_execution_end` + `qa_uat_enqueue.py` + flags `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` / `STACKY_QA_UAT_AUTORUN_ENABLED` (esta última con `requires=` en `harness_flags.py:2116`) | **Intacto.** Este plan no cambia cuándo arranca un run. |
| **214 F4 / F5** | Pane de veredicto en la UI; playbooks-first en `QAUat1.agent.md` | **Intacto.** |
| **240 F2** | **El arranque de AgendaWeb con IIS Express es SUYO**: `agenda_web_launcher.ensure_agenda_web` (`:88`), `stop_agenda_web` (`:179`), su flag `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` (`harness_flags.py:547`, default efectivo `"true"` en `config.py:1232`) | Este plan **INVOCA** `ensure_agenda_web`; **no** escribe un launcher propio, **no** duplica `_resolve_iisexpress` (`:44`) ni los códigos `START_FAILED`/`START_TIMEOUT` (`:170`). Lo que agrego es **cuándo** invocarlo (en caliente, no sólo en el preflight) y **con qué cota**. Reuso su misma flag como gate: arrancar un proceso en la máquina del operador durante el run es el mismo acto que ya gatea el 240. |
| **240 F0 / F1 / F3 / F4 / F5 / F6 / F7** | Guard de runtime, login sin falso negativo, navegación por menú vivo, llegada verificada, reader DPAPI, veredicto funcional, manifiesto con hash | **Intacto.** |
| **240 F8** | `api/qa_uat.py::get_runtime_doctor` (`:1977`, decorador `@bp.get("/runtime-doctor")` en `:1976`); el puente flags→proceso `_QA_UAT_FLAG_KEYS` (`:82`) + `_export_qa_uat_flags` (`:91`) bajo `_FLAG_EXPORT_LOCK` (`:80`) | **EXTIENDO, no duplico.** Agrego una sección al doctor existente y agrego keys a la tupla existente. **Y arreglo un defecto del puente** (§F2): `:108` coacciona todo a booleano. |
| **241 F0..F9** | Aserciones discriminantes, control negativo obligatorio, datos que discriminan, playbook `FrmDetalleClie`, `via_menu`, higiene de diagnósticos, épicas por agregación, suite golden | **Intacto, y su ley es mi invariante #1.** |

### 3.2 Mi eje exclusivo

Clasificar la excepción **DURANTE** la corrida y recuperarse sin abortar todo: probe de salud independiente en caliente, taxonomía de recuperación de 5 clases, allowlist de rutas, retorno a ruta segura, reintento acotado al paso/caso, presupuesto anti-bucle, configuración por UI, y reporte de no-recuperable con ruta/excepción/intentos/motivo.

### 3.3 Invariantes numerados

> **INV-1 (LEY DEL 241 — la recuperación NUNCA ablanda el veredicto).** Ningún camino de recuperación puede convertir un fallo real en `PASS`, ni un `BLOCKED` honesto en `MIXED`, ni bajar `FAIL` a `SKIPPED`. Un caso que terminó en `FAIL` tras 0 reintentos y uno que terminó en `FAIL` tras 3 reintentos son **el mismo `FAIL`**. Precedente que lo hace obligatorio: el 241 C4 documenta un caso donde el gate funcional tapaba un `BLOCKED` legítimo (**`qa_uat_pipeline.py:3170`** — v2: el v1 anclaba `:3090`, 80 líneas arriba, donde hay un `logger.debug` de `apply_approved_learnings`; la línea real es `stages["evaluator"] = {"ok": True, "skipped": True, "reason": "all_scenarios_blocked"}`, con `runner` en `:3169` y `failure_analyzer` en `:3171-3172`). Se prueba en **F11** con un test dedicado, no con una promesa en prosa.

> **INV-2 (`FUNCTIONAL_ERROR` no se reintenta).** Si el probe dice que la app está viva y la ruta usada pertenece a la allowlist, la excepción es **funcional** y es el resultado de la prueba. No se reintenta, no se recupera, no se reabre nada. Reintentar una aserción que falló es la definición de falso verde.

> **INV-3 (regla del 241 sobre 0 tests, intacta).** `total == 0` sigue siendo `BLOCKED / PIP / NO_TESTS_FOUND` y **jamás** `PASS`. La recuperación no puede producir un run con 0 tests y llamarlo verde. `playwright_result_classifier.py` documenta esa regla en su cabecera y este plan no la toca.

> **INV-4 (una sola DEFINICIÓN de "vivo")** — después de F9 existe **exactamente una** definición del frozenset de alive codes en todo el tool (`agenda_health.ALIVE_STATUS_CODES`); las otras dos son **alias por import**. Se prueba con un gate de conteo que **nombra los archivos ofensores**.
>
> **v2 / C6 — lo que INV-4 NO dice, y por qué.** El v1 prometía además *"exactamente una función que hace el probe HTTP"*. **Era insatisfacible por la propia F9**, que declara textualmente *"el resto del módulo no se toca"*: `environment_preflight._http_get` (`:225`, con su `_attempt` interno en `:241`) sigue vivo y se sigue usando en `:164` y `:181`, y el gate del v1 sólo contaba el frozenset, así que la promesa nunca se probaba. Un invariante que el propio plan viola en la fase que dice cerrarlo es peor que no tenerlo. **Regla real:** hay **DOS** implementaciones de probe HTTP y ambas están nominadas con motivo — `environment_preflight._http_get` (**fail-fast, una sola vez, ANTES del navegador**: su semántica de no-reintento es correcta para un preflight y `run_environment_preflight` es contrato consumido por `qa_uat_pipeline.py:404`) y `agenda_health.probe_url` (**en caliente, repetible, durante el run**). El gate de F9 asserta el conjunto **exacto de 2**, así que una **tercera** rompe el test. Unificarlas es un refactor del preflight, es alcance de otro plan, y está en §7.

> **INV-5 (el probe es independiente de la ruta que falló).** El chequeo de disponibilidad se hace **siempre** contra la URL base estable, **nunca** contra la ruta que produjo la excepción. Preguntarle a la ruta rota si el servidor está vivo es el bug que este plan cierra.

> **INV-6 (cero LLM en el camino de decisión).** Clasificar, validar la ruta, decidir el reintento y contar el presupuesto son operaciones deterministas. Ninguna consulta a un modelo. Corolario: paridad trivial entre Codex CLI, Claude Code CLI y GitHub Copilot Pro.

> **INV-7 (el presupuesto es un techo, nunca un piso).** El presupuesto de recuperación **no puede autorizar** más intentos que las cotas ya existentes: `navigation_driver._MAX_REAUTH_PER_STEP = 1` (`:109`), `replan_engine.MAX_REPLAN_ROUNDS = 3` (`:66`), `QA_UAT_MAX_BROWSER_LAUNCHES` (`uat_test_runner.py:134`). Ante conflicto, gana **el mínimo**.

> **INV-8 (degradación silenciosa, no ruptura).** Con `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` en OFF el comportamiento es **el de hoy**: mismo rótulo `PIPELINE_CRASH`, mismo flujo, mismos artefactos. Ninguna fase de este plan puede hacer que un run que hoy funciona deje de funcionar cuando la flag está apagada.

---

## 4. Principios y guardarraíles

1. **Human-in-the-loop innegociable.** Este plan no le saca ninguna decisión al operador: la recuperación es *mecánica* (reabrir una ruta, restablecer sesión, reintentar un caso), no *interpretativa*. No decide si un criterio se cumple, no cierra tickets, no reescribe escenarios. Todo lo que recupera queda en el log y en el reporte para que el operador lo lea.
2. **Mono-operador, sin auth real.** `current_user` es un header sin validar. **Cero RBAC**: ninguna fase introduce permisos, roles ni chequeos de autorización.
3. **Toda config del operador va por UI.** Cero env vars nuevas de cara al operador. Las **9** claves nuevas nacen en `FLAG_REGISTRY` (§F2) y el panel de flags **renderiza sus 4 tipos** (verificado, C8). Las env vars siguen existiendo como **camino de lectura del tool** (que corre en otro proceso/CLI), no como interfaz del operador.
4. **Cambio mínimo y aditivo.** Ninguna fase reescribe las 4 taxonomías existentes; la mía **mapea** a ellas. Ninguna fase cambia la firma pública de `run_environment_preflight`, `ensure_agenda_web` ni `uat_test_runner.run`.
5. **Criterios de aceptación DELTA.** Hay gates rojos de fábrica por deuda ajena (medidos en F0). Un DoD que pida "suite verde" es insatisfacible; se piden **deltas nominadas**.
6. **Todo gate se corre CONTRA el defecto.** Por cada criterio hay un comando y dos resultados: **rojo antes** del fix y **verde después**. Un gate que pasa igual con y sin el fix no cuenta.
7. **Anclaje por SÍMBOLO además de línea.** Las líneas caducan (este mismo repo movió `_REQUIRES_MAP_FROZEN` 143→146 en una costura). Todo anclaje de este plan nombra el símbolo.
8. **Determinismo antes que inteligencia.** Si una clasificación necesita un modelo para decidirse, la clasificación está mal diseñada.

---

## 5. Fases

### Preámbulo: entorno de tests (vale para todas las fases)

- Intérprete: `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe` (py3.13). **Verificado que corre los tests del tool**: `tests/unit/test_plan240_agenda_launcher.py` → **9 passed in 1.12s**.
- **Las dos variables que usan TODOS los comandos de este plan** (definirlas una vez por sesión de PowerShell; las rutas son exactas y verificadas):
  ```powershell
  $PY   = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\venv\Scripts\python.exe"
  $TOOL = "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent"
  $BE   = "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
  ```
  Los comandos escritos como `& $PY -m pytest tests\... -q` **sin** prefijo de ruta se corren **desde `$BE`**; los que llevan `"$TOOL\..."` se pueden correr desde cualquier directorio.
- **Correr SIEMPRE por archivo.** La suite completa se contamina cross-file.
- Tests del tool → `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\tests\unit\`. El `conftest.py` de la raíz del tool inserta `TOOL_ROOT` en `sys.path` y fija `STACKY_LLM_BACKEND=mock`.
- **Hallazgo que ahorra trabajo (CONFIRMADO en la crítica, con las líneas corregidas):** `backend/tests/test_harness_ratchet_meta.py` define `_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"` (**`:13`**, el v1 decía `:14`), `_ALLOWLIST` (`:14`), `_TESTS_DIR = _BACKEND / "tests"` (**`:15`**, el v1 decía `:16`) y `_all_test_files` (`:35`) que hace `_TESTS_DIR.rglob("test_*.py")`. Escanea **sólo** `Stacky Agents/backend/tests/`. ⇒ **Los tests que vivan en el tool NO requieren registro en el ratchet.** Precedente verificado: los **14** archivos del tool (**5** `test_plan240_*.py` + **9** `test_plan241_*.py`) no están registrados. Sólo los **2 archivos backend** de este plan (F2 y F10) se registran, y van en **`.sh` Y `.ps1`**.
- **`pytest -k` que no selecciona nada sale 0.** Prohibido usar `-k` como criterio de aceptación sin exigir el conteo de seleccionados. **Ningún criterio de este plan usa `-k`.**
- **v2 — dónde está `.secrets\agenda_web.env`:** **NO** existe ningún `.secrets/` bajo el tool. El archivo vive en la raíz del repo: `N:\GIT\RS\STACKY\Stacky\.secrets\agenda_web.env` (línea 1: `AGENDA_WEB_BASE_URL=http://localhost:35017/AgendaWeb/`) y su `.example` (línea 7: `AGENDA_WEB_BASE_URL=http://localhost/AgendaWeb/`, **sin puerto**). El backend **no lo carga**: `config.py` sólo hace `load_dotenv(BACKEND_ROOT/".env")` (`:14`) y `load_dotenv(Path.cwd()/".env")` (`:15`). Esto es evidencia directa de C4 y hay que tenerlo presente en toda F2.

---

### F0 — Costura, baseline medido y el doc que miente

**Objetivo (1 frase):** dejar medido qué está rojo ANTES de tocar nada, reservar los nombres que las fases siguientes van a crear, y corregir una línea de documentación que hoy afirma lo contrario de lo que hace el código.

**Valor:** sin esto, cada fase posterior confunde deuda ajena con daño propio, y dos fases paralelas se pisan los nombres.

#### F0.1 — Baseline medido (ya ejecutado en la escritura de este plan; el implementador lo re-corre y compara)

| Archivo | Comando | Resultado medido 2026-07-29 | Clasificación |
|---|---|---|---|
| `backend/tests/test_harness_flags.py` | `.\venv\Scripts\python.exe -m pytest tests/test_harness_flags.py -q` | **56 passed** | VERDE — se puede exigir verde |
| `backend/tests/test_harness_flags_bounds.py` | `... tests/test_harness_flags_bounds.py -q` | **18 passed** | VERDE — se puede exigir verde |
| `backend/tests/test_harness_ratchet_meta.py` | `... tests/test_harness_ratchet_meta.py -q` | **4 passed** | VERDE — se puede exigir verde |
| `backend/tests/test_harness_flags_help.py` | `... tests/test_harness_flags_help.py -q` | **4 failed, 4 passed** | **ROJO DE FÁBRICA** — criterio DELTA obligatorio |
| `backend/tests/test_plan259_ratchet_script_parity.py` | `... tests/test_plan259_ratchet_script_parity.py -q` | **12 passed** ← v2, RE-MEDIDO | **VERDE, con CERO holgura** — criterio ABSOLUTO |

**Detalle (medido en la crítica v2 con el venv del backend, no heredado) — esto cambia el diseño de los criterios de F2:**

- `test_harness_flags_help.py::test_plain_help_covers_all_registry_keys` falla con **79 keys sin ayuda llana** (v2: el v1 decía 80. Medido: `FLAG_REGISTRY` = **403** keys, `PLAIN_HELP` = **324**, faltantes = **79**, huérfanas = **0**). Entre las faltantes están `STACKY_QA_UAT_AUTORUN_ENABLED` y `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` (deuda del plan 214). Los otros 3 fallos son: `test_plain_help_fields_non_empty_and_bounded` (`:44`), `test_plain_help_on_off_start_with_si` (`:56`) y `test_plain_help_avoids_jargon_denylist` (`:63`), todos por deuda ajena.
  **Consecuencia de diseño:** el assert es `assert missing == []`, que **colapsa 79 faltantes a 1 fallo**. Si mis keys nuevas no tuvieran ayuda, el test seguiría rojo **exactamente igual** y el gate no discriminaría nada. ⇒ F2 exige un criterio que asserte sobre **el contenido del mensaje**, no sobre pass/fail.
- **v2 / C1 — `test_plan259_ratchet_script_parity.py` NO es un rojo de fábrica: está VERDE y al borde.** Medición real: `_SH_RE` (`:28`) extrae **713** rutas del `.sh`, `_PS1_RE` (`:30`) extrae **649** del `.ps1`; `solo_en_ps1 = 0` y `solo_en_sh = `**64**. `_PS1_LAG_MAX = 64` (`:46`) y el assert de `test_el_ps1_no_pierde_terreno` (`:85`) es `len(solo_en_sh) <= _PS1_LAG_MAX` (`:93`) ⇒ **64 <= 64 pasa**. El mensaje *"65 archivos solo en el .sh"* que el v1 citaba **no existe**.
  **Tres consecuencias, todas de diseño:**
  1. El criterio del v1 (*"sigue en `1 failed, 11 passed` y el mensaje sigue diciendo 65"*) es **insatisfacible**. Se reemplaza por el criterio **ABSOLUTO `12 passed`**.
  2. **Holgura cero ⇒ dependencia dura.** Registrar los 2 archivos backend en el `.sh` sin registrarlos en el `.ps1` lleva el lag a **66 > 64** y pone el archivo en `1 failed` con el mensaje *"el .ps1 perdio terreno: 66 archivos solo en el .sh (maximo 64)"*. **Ese es el gate corrido contra el defecto**, y es más fuerte que el delta que el v1 proponía.
  3. `_PS1_LAG_MAX` **no se toca** (ni sube ni baja). Saldar los 64 es deuda ajena y está en §7.
  4. **AVISO OPERATIVO (medido con `git status` durante la crítica): `backend/scripts/run_harness_tests.sh` Y `.ps1` están MODIFICADOS por una sesión paralela viva en este mismo árbol, y hay 3 `tests/test_mg_*.py` sin trackear.** Con holgura cero, **el lag es un blanco móvil**: si esa sesión agrega archivos sólo al `.sh`, la parity test se pone roja **sin que este plan haya tocado nada**. Antes de culpar a F2 o F10, corré `git status` y `git diff -- backend/scripts/` y **re-medí el lag** con el script de F0.1. Si el lag ya venía en 65+ por deuda de la sesión paralela, ese rojo es ajeno y se documenta como tal — pero **igual hay que registrar los 2 archivos propios en los dos scripts**.

#### F0.2 — Reserva de nombres (predeclaración, para que F1..F11 no colisionen)

Módulos nuevos del tool (verificado que **ninguno existe hoy**):
`agenda_health.py`, `recovery_config.py`, `recovery_classifier.py`, `route_allowlist.py`, `recovery_budget.py`, `hot_recovery.py` — todos en `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\`.

Claves de flag nuevas (**las 9**, para que ninguna fase las renombre a mitad de camino):
`STACKY_QA_UAT_HOT_RECOVERY_ENABLED`, `STACKY_QA_UAT_RECOVERY_MAX_PER_RUN`, `STACKY_QA_UAT_RECOVERY_MAX_PER_CASE`, `STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S`, `STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S`, `STACKY_QA_UAT_ROUTE_ALLOWLIST`, `STACKY_QA_UAT_SAFE_ROUTE`, `AGENDA_WEB_BASE_URL`, `QA_NAV_RETRIES`.

> **v2 — por qué 9 y no 7.** `QA_NAV_RETRIES` entra por **C9** (F6 la unificaba y la dejaba env-only, contra el riel *toda config del operador va por UI*, y "reintentos configurables" es criterio literal del operador). `STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S` entra por la **`[ADICIÓN ARQUITECTO]`** de F1.5. **Las dos últimas no llevan prefijo `STACKY_` y eso es LEGAL:** verificado que `FLAG_REGISTRY` ya tiene 25+ keys sin ese prefijo (`CLAUDE_CODE_CLI_*` desde `:596`, `CODEX_CLI_*` desde `:817`, `INTENT_PREFLIGHT_*` desde `:2612`, `LOCAL_LLM_*` desde `:3946`) y **ningún test exige el prefijo** (los únicos `startswith("STACKY` del backend son `test_optimizer_engine.py:310-311`, sobre otras familias, y `codex_cli_runner.py:1997`, que es un filtro de passthrough, no una validación del registry).

Archivos de test nuevos (**13 en el tool + 2 en el backend**): ver la tabla del §9.

> **PROHIBIDO en F0:** pre-registrar en el ratchet rutas de test que todavía no existen. `test_harness_ratchet_meta.py::_all_test_files` (`:35`) deriva del filesystem; una ruta declarada sin archivo pone el meta-test **rojo**. Los 2 archivos backend se registran **en la fase que los crea**, no acá.

#### F0.3 — El doc que miente (v2 / C10: son DOS mentiras, no una)

**Mentira 1.** `agenda_web_launcher.py:12` dice literal: `FLAG: STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED, default OFF por EXCEPCION DURA #3`. Reemplazar por:

```
FLAG: STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED, default ON desde el barrido 2026-07-27
(config.py). Con OFF el comportamiento es byte-identico al previo al plan 240
(BLOCKED/APP_NOT_RUNNING sin intentar arrancar nada).
```

**Mentira 2 — la que el v1 no vio.** El comentario de `config.py:1230-1231`, **inmediatamente encima de la declaración**, sigue diciendo lo contrario del código:

```python
# :1230  # Default OFF por EXCEPCION DURA #3 (prerequisito no garantizado: IIS Express +
# :1231  # applicationhost.config del cliente + solucion compilada).
# :1232  STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED: bool = os.getenv(
# :1233      "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED", "true"
# :1234  ).lower() in ("1", "true", "yes")
```

Reemplazar `:1230-1231` por: `# Default ON desde el barrido default-ON 2026-07-27. Con OFF el pipeline no intenta`  /  `# arrancar IIS Express: devuelve BLOCKED/APP_NOT_RUNNING (comportamiento pre-plan-240).`
Corregir sólo el launcher y dejar esta en pie es exactamente el defecto que F0.3 dice arreglar, en el archivo que manda.

> **v2 — trampa de implementación que el v1 dejaba abierta.** La declaración ocupa **3 líneas**: la key aparece en `:1232` (nombre del atributo) y en `:1233` (argumento de `os.getenv`), y el default `"true"` está en `:1233`. Un regex **por línea** (`^.*STACKY_QA_UAT_AUTOSTART.*os\.getenv\((.*)\)`) **no matchea nunca**. El test debe usar un patrón multilínea explícito: `re.search(r'STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"?\s*:?\s*bool\s*=\s*os\.getenv\(\s*"STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"\s*,\s*"(?P<def>[a-z]+)"', text, re.S)` y asserta `m.group("def") == "true"`.

**Tests PRIMERO:** `Stacky tools\QA UAT Agent\tests\unit\test_plan262_launcher_doc_truth.py` — **3 casos**
1. `test_launcher_docstring_no_dice_default_off` — lee `agenda_web_launcher.py` como texto y asserta que la frase `"default OFF"` (case-insensitive) **no** aparece en el docstring de módulo (los primeros 40 renglones). Mensaje del assert: **la línea encontrada, completa, con su número**.
2. `test_config_no_dice_default_off_para_la_flag_del_240` — lee `config.py` como texto, ubica el índice de `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` y asserta que en las **5 líneas anteriores** no aparece `"Default OFF"` ni `"default OFF"`. Mensaje: la línea ofensora con su número. **ANTES: falla** (`:1230`).
3. `test_launcher_flag_default_es_on_en_config` — el regex multilínea de arriba sobre `config.py`, asserta `"true"`. **No importa `config`** (importarlo arrastra el backend entero al proceso del tool).

**Comando:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_launcher_doc_truth.py" -q
```

**Criterio de aceptación BINARIO:** `3 passed`.
**Rojo antes / verde después:** ANTES → `2 failed, 1 passed` (fallan 1 y 2; el 3 pasa porque el default ya es `"true"`). DESPUÉS → `3 passed`.
**Gate corrido contra el defecto:** el caso 3 pasa **antes y después**, así que **no es un gate**: es una guarda de no-regresión (si alguien vuelve el default a `"false"`, avisa). Los gates reales son 1 y 2, y son los únicos que están rojos hoy.

**Flag que la protege:** ninguna. Es una corrección de documentación y una medición; no hay comportamiento nuevo que gatear.
**Impacto por runtime:** ninguno (nada ejecuta doc). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F1 — `agenda_health.py`: la ÚNICA fuente de verdad de "¿está viva la app?" en caliente

**Objetivo (1 frase):** un módulo determinista que responda "¿AgendaWeb responde AHORA?" contra una URL estable, reusando los alive codes existentes en vez de crear una cuarta copia.

**Valor:** sin esto, ninguna de las fases siguientes puede distinguir una caída de una ruta mala. Es la pieza base de la que dependen F3, F7, F8, F9 y F10.

**Archivo nuevo:** `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\agenda_health.py`

**Símbolos EXACTOS:**

```python
"""agenda_health.py — Plan 262 F1. UNICA fuente de verdad de "AgendaWeb responde AHORA".

POR QUE EXISTE. environment_preflight.run_environment_preflight corre UNA VEZ, antes
de abrir el navegador (qa_uat_pipeline.py:400) y esta disenado para NO reintentar
(comentario literal en environment_preflight.py:53). Este modulo es el chequeo EN
CALIENTE: barato, acotado, repetible, y SIEMPRE contra la URL base estable, nunca
contra la ruta que fallo (invariante INV-5 del plan 262).

NUNCA lanza. NUNCA usa un modelo. Determinista.
"""

ALIVE_STATUS_CODES: frozenset[int] = frozenset({200, 301, 302, 400, 401, 403})
DEFAULT_PROBE_TIMEOUT_S: float = 5.0
DEFAULT_CONFIRM_PAUSE_S: float = 2.0        # F1.5 [ADICION ARQUITECTO]

# v2 / C11 — UNICA constante del default de la URL base en este modulo. El v1 la
# hardcodeaba inline, agregando un CUARTO literal "http://localhost:35017/AgendaWeb/"
# en el mismo plan cuya F9 borra uno y asserta 0 hits en otro archivo.
DEFAULT_BASE_URL: str = "http://localhost:35017/AgendaWeb/"

@dataclass(frozen=True)
class HealthProbe:
    alive: bool
    status: int | None
    url: str
    elapsed_ms: int
    error: str            # "" cuando alive is True
    source: str           # "http_probe" | "http_probe_confirmed" | "http_probe_flapped"
    samples: int = 1      # F1.5 — cuantas muestras sostienen este veredicto

def probe_url(url: str, *, timeout_s: float | None = None) -> HealthProbe: ...
def probe_agenda(*, base_url: str | None = None, timeout_s: float | None = None) -> HealthProbe: ...
def probe_agenda_confirmed(*, base_url: str | None = None, timeout_s: float | None = None,
                           confirm_pause_s: float | None = None) -> HealthProbe: ...   # F1.5
def is_alive(*, base_url: str | None = None, timeout_s: float | None = None) -> bool: ...
```

**Diseño con casos borde:**

```python
def probe_url(url, *, timeout_s=None):
    t0 = time.time()
    to = DEFAULT_PROBE_TIMEOUT_S if timeout_s is None else float(timeout_s)
    # BORDE 1: timeout <= 0 sería un probe que nunca puede dar vivo. Se clampea.
    to = max(0.5, to)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=to) as resp:
            code = int(resp.getcode())
            return HealthProbe(code in ALIVE_STATUS_CODES, code, url, _ms(t0), "", "http_probe")
    except urllib.error.HTTPError as exc:
        # BORDE 2: 401/403/302 PRUEBAN que el proceso sirve HTTP. Vivo.
        code = int(getattr(exc, "code", 0))
        alive = code in ALIVE_STATUS_CODES
        return HealthProbe(alive, code, url, _ms(t0), "" if alive else f"HTTP {code}", "http_probe")
    except urllib.error.URLError as exc:
        return HealthProbe(False, None, url, _ms(t0), f"URLError: {exc.reason}", "http_probe")
    except OSError as exc:
        return HealthProbe(False, None, url, _ms(t0), f"OSError: {exc}", "http_probe")
    except Exception as exc:                       # noqa: BLE001 — NUNCA lanza
        return HealthProbe(False, None, url, _ms(t0), f"{type(exc).__name__}: {exc}", "http_probe")

def probe_agenda(*, base_url=None, timeout_s=None):
    url = base_url
    if not url:
        # IMPORT DIFERIDO A PROPOSITO: environment_preflight va a importar ESTE modulo
        # en F9 para su alias de alive codes. Un import de modulo aca crearia un ciclo.
        try:
            from environment_preflight import get_agenda_base_url
            url = get_agenda_base_url()
        except Exception:                          # noqa: BLE001
            url = DEFAULT_BASE_URL                 # v2/C11: la constante, no un literal
    if timeout_s is None:
        try:
            from recovery_config import health_probe_timeout_s   # F2; opcional
            timeout_s = health_probe_timeout_s()
        except Exception:                          # noqa: BLE001
            timeout_s = DEFAULT_PROBE_TIMEOUT_S
    return probe_url(url, timeout_s=timeout_s)
```

> **Decisión de dirección de dependencia, explícita:** `agenda_health` **posee** `ALIVE_STATUS_CODES` (público, sin underscore) y **no** importa `environment_preflight` a nivel de módulo. `environment_preflight` sí importará `agenda_health` en F9. El import de `get_agenda_base_url` va **dentro de la función** para que el ciclo no exista en tiempo de import. `get_agenda_base_url` **no se mueve**: tiene importadores en todo el tool y moverla sería un refactor de riesgo gratuito.

#### F1.5 — `[ADICIÓN ARQUITECTO]` — `SERVICE_DOWN` exige DOS muestras: el control negativo del probe

**El agujero que el v1 no cubre.** El v1 declara `SERVICE_DOWN` con **una sola muestra**: un `GET` con timeout de 5 s. Y `SERVICE_DOWN` es la **única** clase que autoriza `ensure_agenda_web`, es decir **abrir un proceso en la máquina del operador**, con un presupuesto de exactamente **1** por run (INV-7, `max_service_starts = 1`). El propio plan escribe en §2, hecho 3, el escenario que lo rompe: *"la app puede estar reiniciando su AppPool en el segundo 40 de una prueba de 6 minutos"*. Un reciclado de AppPool de IIS dura segundos y devuelve `URLError`/`503` mientras dura. Con una sola muestra:

1. el probe dice muerto en el peor segundo posible;
2. se gasta **el único** crédito de arranque de servicio del run;
3. `ensure_agenda_web` hace `subprocess.Popen` (`:148`) **contra un puerto que está por volver solo** — dos IIS Express peleando por `35017`;
4. cuando el segundo arranque falla, el run entero termina en `UNRECOVERABLE` por un hipo de 3 segundos;
5. y el reporte le dice al operador *"la app está caída"*, que es **exactamente la mentira que este plan existe para matar**, ahora con probe.

Es el mismo error de razonamiento del bug original, un nivel más abajo: **afirmar una causa con una sola observación.** Y es la disciplina del 241 aplicada al probe: una aserción que no puede distinguir el caso malo del transitorio no es evidencia.

**El fix, determinista y barato:**

```python
def probe_agenda_confirmed(*, base_url=None, timeout_s=None, confirm_pause_s=None):
    """SERVICE_DOWN necesita DOS muertos consecutivos. Un muerto seguido de un vivo
    es un FLAP (reciclado de AppPool), no una caida: no autoriza arrancar nada.
    """
    first = probe_agenda(base_url=base_url, timeout_s=timeout_s)
    if first.alive:
        return replace(first, source="http_probe_confirmed", samples=1)
    pause = DEFAULT_CONFIRM_PAUSE_S if confirm_pause_s is None else float(confirm_pause_s)
    pause = min(15.0, max(0.0, pause))          # BORDE: negativo -> 0; nunca > 15 s
    if pause > 0:
        time.sleep(pause)
    second = probe_agenda(base_url=base_url, timeout_s=timeout_s)
    if second.alive:
        # FLAP: la app volvio sola. NO se gasta el arranque de servicio.
        return replace(second, source="http_probe_flapped", samples=2)
    return replace(second, source="http_probe_confirmed", samples=2)
```

**Reglas que esto agrega (y que F3/F5/F7 deben respetar):**
- **Sólo `probe_agenda_confirmed` puede sostener `SERVICE_DOWN`.** F3 asserta: si `health.samples < 2` y `health.alive is False`, la clase **no puede ser** `SERVICE_DOWN` — es `UNRECOVERABLE` con `evidence="probe sin confirmar: 1 muestra"`. Esto hace **imposible por construcción** que un solo `GET` fallido abra un proceso.
- **`source == "http_probe_flapped"`** ⇒ la app está viva pero fue inestable: se clasifica por el camino de app-viva (paso 4), se **reintenta el caso**, se emite `recovery_probe_flapped` en el log, y **no** se consume `_service_starts`.
- **Costo real:** la pausa sólo ocurre en la rama del primer probe muerto, o sea **sólo en runs que hoy mueren enteros**. Techo: `RECOVERY_MAX_PER_RUN` (6) × (5 s timeout + 2 s pausa + 5 s timeout) = 72 s sobre una ventana de 6 min = 20 %, y sólo en el peor caso patológico. Es más barato que perder el run.
- **Flag nueva:** `STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S`, `type="float"`, bounds `(0, 15)`, default **2.0**. `0` = confirmación inmediata sin pausa (sigue exigiendo 2 muestras). Cae dentro del criterio literal (g) del operador: *"esperas configurables"*.
- **Cero LLM, cero decisión del operador, cero trabajo extra.** Respeta INV-5 (siempre contra la base), INV-6 y INV-7 (nunca autoriza más de 1 arranque; ahora autoriza **menos**).

**Tests PRIMERO:** `tests\unit\test_plan262_agenda_health.py` — **13 casos**, todos con `unittest.mock.patch` sobre `urllib.request.urlopen`, cero red real:
1. `test_200_es_vivo`
2. `test_302_es_vivo` — redirección a login **no** es caída
3. `test_401_es_vivo` — HTTPError con code 401 ⇒ `alive is True`
4. `test_403_es_vivo`
5. `test_400_es_vivo` — el caso host-binding documentado en `environment_preflight.py:59-61`
6. `test_500_no_es_vivo` — `alive is False`, `status == 500`
7. `test_connection_refused_no_es_vivo` — `URLError` ⇒ `alive is False`, `error` contiene `"URLError"`
8. `test_excepcion_inesperada_no_lanza` — `urlopen` levanta `RuntimeError("boom")` ⇒ devuelve `HealthProbe(alive=False)` y **no propaga**
9. `test_timeout_cero_se_clampea` — `probe_url(url, timeout_s=0)` ⇒ el `timeout` pasado a `urlopen` es `>= 0.5`
10. `test_alive_codes_son_los_mismos_que_el_preflight` — `agenda_health.ALIVE_STATUS_CODES == environment_preflight._ALIVE_STATUS_CODES` (igualdad de valor: antes de F9 son dos frozensets distintos con el mismo contenido; la identidad `is` se exige recién en F9)
11. `test_probe_agenda_usa_la_base_url_no_la_ruta` — con `AGENDA_WEB_BASE_URL="http://x/AgendaWeb/"` en el env, la URL pedida a `urlopen` es exactamente `"http://x/AgendaWeb/"`, **sin** ningún `.aspx` concatenado
12. **`test_un_solo_probe_muerto_no_da_service_down_confirmado`** — F1.5: `urlopen` levanta `URLError` la 1ª vez y devuelve **200** la 2ª ⇒ `probe_agenda_confirmed()` da `alive is True`, `source == "http_probe_flapped"`, `samples == 2`. `time.sleep` mockeado (el test no espera 2 s de verdad).
13. **`test_dos_probes_muertos_dan_service_down_confirmado`** — F1.5: `URLError` las dos veces ⇒ `alive is False`, `source == "http_probe_confirmed"`, `samples == 2`; y con `confirm_pause_s=-5` el `sleep` recibe **0** (nunca un negativo).

**Comando:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_agenda_health.py" -q
```

**Criterio de aceptación BINARIO:** `13 passed`.
**Rojo antes / verde después:** ANTES → `ERROR ... ModuleNotFoundError: No module named 'agenda_health'` (colección falla, exit ≠ 0). DESPUÉS → `13 passed`.
**Gate corrido contra el defecto:** el caso 3 (`401 es vivo`) es exactamente el defecto que este plan ataca — un naive `resp.status == 200` lo llamaría caída. Implementación prohibida: comparar contra `200` a secas ⇒ los tests 3, 4 y 5 fallan. Y el **caso 12 es el gate de F1.5**: la implementación de una sola muestra (la del v1) lo falla, porque devuelve `alive is False` ante un flap.

**Flag que la protege:** ninguna. Es un módulo nuevo sin importadores hasta F7/F8/F9; **inerte por construcción**. Gatear un módulo que nadie llama sería teatro.
**Impacto por runtime:** idéntico en los 3 (sólo `urllib` de la stdlib). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F2 — Configuración por UI: 9 claves nuevas, y el arreglo del puente que hoy destruye los valores

**Objetivo (1 frase):** que reintentos, esperas, URL base, rutas permitidas y ruta segura sean configurables **por UI** y lleguen intactos al proceso del tool.

**Valor:** el operador lo pidió explícitamente, y el riel de Stacky dice que toda config del operador va por UI. Hoy las ~30 env vars del tool (`AGENDA_WEB_BASE_URL`, `QA_UAT_MAX_*`, `QA_NAV_*`, `QA_UAT_*_TIMEOUT_MS`) se leen crudas de `os.environ` y ninguna está en `FLAG_REGISTRY`.

#### F2.0 — Corrección de un supuesto del pedido (verificado, cambia el diseño)

El pedido asumía que `FLAG_REGISTRY` es booleano y que habría que buscar otro mecanismo para valores. **Es falso.** Verificado en `backend/services/harness_flags.py`:
- `class FlagSpec` (`:21`), campo `type: str` (`:23`) con el comentario literal `# "bool" | "csv" | "int" | "float" | "json"`.
- `min_value: float | None` (`:33`) y `max_value: float | None` (`:34`), del plan 83.
- `value_in_bounds(spec, value)` (`:5883`) y `validate_bounds_registry()` (`:5908`).
- Ejemplo real vivo: `STACKY_STARTUP_WRITE_BARRIER_WAIT_S` con `type="float"`, `min_value=0`, `max_value=300`, **sin `default=`** y con el comentario `# SIN default= (numerica; el default EFECTIVO 30.0 vive en config.py)` (`harness_flags.py:5142`).
- Ejemplos reales de csv: `harness_flags.py:639, 655, 671, 704, 733` (`type="csv"`), almacenados en `config.py` como **str con comas** — patrón verificado: `STACKY_ASSUMPTION_MODE_AGENT_TYPES: str = os.getenv("STACKY_ASSUMPTION_MODE_AGENT_TYPES", "technical,functional")` (`config.py:1316-1318`).
- Patrón de int verificado: `STACKY_ASSUMPTION_MAX_PER_RUN: int = int(os.getenv("STACKY_ASSUMPTION_MAX_PER_RUN", "10") or 10)` (`config.py:1319-1320`).

⇒ **El mecanismo correcto es `FLAG_REGISTRY`.** No hace falta ni `api/preferences.py::get_ui_preference` (`:75`) ni un perfil de cliente ni un archivo de config propio del tool. Se descarta `get_ui_preference` porque introduciría un **segundo** lugar donde vive la config del arnés, que es precisamente la enfermedad que este plan trata.

##### v2 / C8 — el `[NO VERIFICADO]` nº1 está VERIFICADO: el panel renderiza los 6 tipos

Se abrió `Stacky Agents\frontend\src\components\HarnessFlagsPanel.tsx`. La función `control()` de `FlagRow` (`:93`) despacha por `flag.type` con una rama por tipo, **todas presentes**:

| `flag.type` | Línea | Control que renderiza |
|---|---|---|
| `"bool"` | `:94` | toggle `<input type="checkbox">` + etiqueta Activada/Desactivada |
| `"int"` | `:115` | `<input type="number" step="1" min={flag.min_value} max={flag.max_value}>`, commit `onBlur` con `Number(...)` |
| `"float"` | `:130` | `<input type="number" step="0.01" min max>`, commit `onBlur` con `parseFloat(...)` |
| `"csv"` | `:145` | `<input type="text">`, commit `onBlur` con el string crudo |
| `"str"` | `:157` | `<input type="text">`, commit `onBlur` con el string crudo |
| `"json"` | `:169` | `<JsonInput>` (`:26`) con validación `JSON.parse` y borde rojo si es inválido |

Y `:293-301` pinta el hint de rango (`min–max` / `≥ min` / `≤ max`) cuando el spec tiene bounds; `:91` + `:267-269` muestran *"Valor actual fuera de rango válido"* si el backend devuelve `in_bounds === false`.

⇒ **R-4 queda CERRADO como riesgo inexistente**, F2 no nace inerte, el criterio literal del operador *"reintentos, esperas, URL base y rutas permitidas configurables"* **se cumple por UI**, y **la tarea manual nº1 del §9.3 se elimina** (era trabajo del operador para verificar algo que se verifica leyendo un archivo).

##### v2 / C5 — `type="str"` EXISTE: el compromiso `csv` del v1 se descarta

El v1 afirmaba, **como verificado**, que `FlagSpec.type` no tiene `"str"`, anclándolo al comentario de `harness_flags.py:23`. **El comentario está stale, la afirmación es falsa.** `type="str"` se usa **10 veces** en `FLAG_REGISTRY`: `:1988`, `:2030`, `:3867`, `:3933`, `:3958`, `:3969`, `:4007`, `:4691` (con el comentario propio *"SIN default= (C14: efectivo 'auto' en config.py)"*), `:4859` (`STACKY_INCIDENT_VISION_ENDPOINT`) y `:4872` (`STACKY_INCIDENT_VISION_MODEL`). Y el panel lo renderiza (`HarnessFlagsPanel.tsx:157`).
⇒ `STACKY_QA_UAT_SAFE_ROUTE` y `AGENDA_WEB_BASE_URL` se declaran **`type="str"`**. Desaparecen: el "compromiso consciente", el desenvolvimiento *"tomar el primer elemento no vacío"* y el test *"la lista tiene exactamente 1 elemento"*.
**Tarea aditiva de 1 línea (aprovechando que se toca el archivo):** actualizar el comentario de `:23` a `# "bool" | "csv" | "int" | "float" | "str" | "json"`. Una lista de tipos incompleta en el único lugar donde un implementador la va a leer es cómo nació este error.

#### F2.1 — El defecto del puente (BUG REAL, **CONFIRMADO** abriendo el archivo en la crítica v2)

`api/qa_uat.py::_export_qa_uat_flags` (`:91`) hace, en `:108` (verificado literal; `_FLAG_EXPORT_LOCK` en `:80`, `_QA_UAT_FLAG_KEYS` en `:82` con sus 5 keys bool en `:83-87`, `os.environ[_k] = val` en `:110`):

```python
val = "true" if bool(getattr(_cfg, _k, False)) else "false"
```

**Coacciona TODO a booleano.** Si se agrega `STACKY_QA_UAT_RECOVERY_MAX_PER_RUN` a `_QA_UAT_FLAG_KEYS` (`:82`) sin tocar esto, el tool recibe `os.environ["STACKY_QA_UAT_RECOVERY_MAX_PER_RUN"] = "true"` y `int("true")` levanta `ValueError` **dentro del hilo del pipeline** — es decir, cae en el catch-all de `qa_uat_pipeline.py:690` y se reporta como… `PIPELINE_CRASH`. El plan se autoinfligiría el bug que viene a arreglar. Fix:

```python
    with _FLAG_EXPORT_LOCK:
        for _k in _QA_UAT_FLAG_KEYS:
            _spec = _SPEC_BY_KEY.get(_k)
            _ftype = getattr(_spec, "type", "bool") if _spec is not None else "bool"
            if _ftype == "bool":
                val = "true" if bool(getattr(_cfg, _k, False)) else "false"
            else:
                # Plan 262 F2: int/float/csv se exportan TAL CUAL. Coaccionarlos a
                # booleano destruye el valor (int("true") -> ValueError en el hilo
                # del pipeline, que termina rotulado PIPELINE_CRASH).
                raw = getattr(_cfg, _k, None)
                if raw is None:
                    continue                      # BORDE: sin atributo, no se exporta basura
                if isinstance(raw, (list, tuple)):
                    val = ",".join(str(x) for x in raw)
                else:
                    val = str(raw)
            os.environ[_k] = val
            exported[_k] = val
```
donde `_SPEC_BY_KEY = {s.key: s for s in FLAG_REGISTRY}` se construye una vez a nivel de módulo en `api/qa_uat.py`.

> **Guarda de no-regresión obligatoria:** las 5 keys booleanas que hoy exporta (`:83-87`) deben seguir produciendo **exactamente** `"true"` / `"false"`. Es un test propio, no una inspección visual.

#### F2.2 — Las 9 claves nuevas (v2: eran 7; +`QA_NAV_RETRIES` por C9, +`..._CONFIRM_S` por F1.5)

| Clave | `type` | bounds | default EFECTIVO en `config.py` | Por qué ese default |
|---|---|---|---|---|
| `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` | `bool` | — | `"true"` (**ON**) | Gate de capacidad. Nace ON: no quema tokens en reposo (cero LLM, INV-6), no escribe en ningún sistema real del operador, no le saca ninguna decisión. Con OFF, comportamiento de hoy (INV-8). |
| `STACKY_QA_UAT_RECOVERY_MAX_PER_RUN` | `int` | `(0, 50)` | `6` | Cota global anti-bucle. 6 = una recuperación por minuto en el run típico de 6 min (`QA_UAT_MAX_TOTAL_MINUTES` default `"6"`, `uat_test_runner.py:139`). `0` = recuperación medida pero nunca ejecutada (modo observación). |
| `STACKY_QA_UAT_RECOVERY_MAX_PER_CASE` | `int` | `(0, 10)` | `1` | Un reintento por caso. Alineado con `_MAX_REAUTH_PER_STEP = 1` (`navigation_driver.py:109`) y con `QA_UAT_MAX_LOGIN_ATTEMPTS` default `"1"` (`uat_test_runner.py:135`). |
| `STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S` | `float` | `(1, 30)` | `5.0` | **Idéntico** a `environment_preflight._CHECK_TIMEOUT_S = 5.0` (`:54`). Cambiar el número acá sería introducir una segunda política de timeout. |
| **`STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S`** | `float` | `(0, 15)` | `2.0` | **F1.5 `[ADICIÓN ARQUITECTO]`.** Pausa entre las 2 muestras que exige `SERVICE_DOWN`. `0` = confirmar sin pausa (sigue exigiendo 2 muestras). Cubre la palabra *"esperas"* del criterio (g) del operador. |
| `STACKY_QA_UAT_ROUTE_ALLOWLIST` | `csv` | — | `""` (vacío) | Vacío = allowlist **derivada** del código (ver F4), no "todo permitido". Nace vacío para que el comportamiento por defecto no dependa de que el operador la llene. |
| `STACKY_QA_UAT_SAFE_ROUTE` | **`str`** | — | `""` (vacío) | Vacío = **la URL base**, que siempre existe y siempre es válida. v2/C5: `str`, no `csv`. |
| `AGENDA_WEB_BASE_URL` | **`str`** | — | `os.getenv("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")` — **env-first OBLIGATORIO** | **Registrar el nombre EXACTO que el tool ya lee.** `environment_preflight.get_agenda_base_url` (`:67`) lo lee en `:76` y normaliza en `:77`. Verificado: **54 archivos de código** del tool leen esa env var (217 contando `evidence/`), no ~20. Registrarlo hace que la UI controle a todos sin tocar una línea. **Leer la nota C4 de abajo antes de escribir una sola línea de esto.** |
| **`QA_NAV_RETRIES`** | `int` | `(0, 10)` | `3` | **v2/C9.** Es la cota de reintentos de navegación que F6 vuelve canónica. Default **3 = el efectivo de hoy** (`uat_test_runner.py:343`); ponerlo en 1 sería la regresión silenciosa que F6 existe para prevenir. Sin registrarla, *"reintentos configurables"* quedaba env-only, contra el riel de Stacky. |

> **v2 / C4 — BLOQUEANTE resuelto: `AGENDA_WEB_BASE_URL` no puede pisar el valor del operador.**
> `_export_qa_uat_flags` hace **asignación incondicional** (`os.environ[_k] = val`, `:110`) y su propio docstring **prohíbe** `setdefault` (*"eso volvería inefectivo el toggle de la UI"*). Hoy `AGENDA_WEB_BASE_URL` **no existe en ninguna parte del backend**: `grep -rn 'AGENDA_WEB_' backend/**/*.py` da **0 hits**. Sale del entorno del proceso. Y el backend **no** carga `.secrets\agenda_web.env`: `config.py` sólo hace `load_dotenv(BACKEND_ROOT/".env")` (`:14`) y `load_dotenv(Path.cwd()/".env")` (`:15`). Divergencia real y medida: el `.example` de la raíz trae `http://localhost/AgendaWeb/` **sin puerto**, el `.env` vivo trae `35017`.
> Si la key se registra sin cuidado, **todo run lanzado desde la UI reescribe la URL base con el default**, el probe pega contra la URL equivocada, da `alive=False`, y el veredicto es `SERVICE_DOWN` — *"la Agenda Web está caída"*, el bug del pedido, **causado por el plan**, y en violación directa de INV-8.
> **Las 3 reglas que lo cierran, y son obligatorias:**
> 1. **Declaración env-first en `config.py`, literal:** `AGENDA_WEB_BASE_URL: str = os.getenv("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")`. Así, si el operador ya tiene la var en el entorno o en `backend\.env`, `config` **adopta su valor** y el export escribe **el mismo string**: la operación se vuelve **idempotente**. Un default hardcodeado sin `os.getenv` la volvería destructiva.
> 2. **Test de idempotencia obligatorio** (caso 11 de `test_plan262_recovery_flags.py`): con `os.environ["AGENDA_WEB_BASE_URL"] = "http://otrohost:9999/AgendaWeb/"` **y `config` recargado**, `_export_qa_uat_flags()` deja `os.environ["AGENDA_WEB_BASE_URL"] == "http://otrohost:9999/AgendaWeb/"`. Este test **falla** con la declaración hardcodeada y **pasa** con la env-first: es el gate corrido contra el defecto.
> 3. **Ningún criterio de este plan puede depender de la línea `AGENDA_WEB_BASE_URL=...` en `harness_defaults.env`** (ver F2.3 punto 6): esos archivos se **regeneran** en cada build desde la config viva, y hornear la URL base de un entorno en el `.env` de otro es la misma clase de error.

> **v2 — nota de tipo, corregida:** el v1 declaraba `STACKY_QA_UAT_SAFE_ROUTE` y `AGENDA_WEB_BASE_URL` como `csv` "por compromiso". `type="str"` existe (C5) y es el tipo correcto. El lector del tool devuelve el string tal cual, sin listas ni índices.

> **Decisión: NO se crea una flag nueva para el reinicio del servicio en caliente.** Arrancar IIS Express durante el run es el **mismo acto** que ya gatea `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` (`harness_flags.py:547`, default `"true"` en `config.py:1232`). F7 reusa **esa** flag. Crear una segunda sería duplicar el gate del 240 y romper la frontera del §3.

> **Validación cruzada obligatoria:** `STACKY_QA_UAT_SAFE_ROUTE`, si no está vacía, **debe** pertenecer a la allowlist efectiva. Una ruta segura fuera de la allowlist es un bucle garantizado: el orquestador volvería a una ruta que su propio validador rechaza. `recovery_config.validate_recovery_config()` lo verifica y `route_allowlist` **auto-incluye** la ruta segura (F4).

#### F2.3 — Los 8 puntos de cableado (v2: el v1 decía "7 estructuras"; con las 9 claves los puntos son 8 y **todos** son obligatorios)

1. `backend/services/harness_flags.py` → `FLAG_REGISTRY`: **9** `FlagSpec` nuevos. Las **8 de valor SIN `default=`** (así `default_is_known` devuelve `False` — verificado: `default_is_known(spec)` es literalmente `return spec.default is not None`, **`:5814`**, el v1 decía `:5816`). El bool **CON `default=True`**. Aprovechando el archivo: corregir el comentario de `:23` para incluir `"str"` (C5).
2. `backend/services/harness_flags.py` → `_CATEGORY_KEYS` (`:120`), categoría **`"calidad_verificacion"`** (abre en `:154`; su `CategorySpec` en `:61`, label *"Calidad y verificación del entregable"*), junto a las 7 keys QA UAT que ya viven ahí (`:171-172`, `:174`, `:178` — **verificado**). El comentario de `:514` lo hace obligatorio: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS`"*.
3. `backend/config.py` → los **9** atributos con el default EFECTIVO de la tabla, siguiendo los patrones verificados (`:1316-1318` para el `str` con comas, `:1319-1320` para `int`, `:2114` para `int` simple). Ubicación sugerida: junto al bloque QA UAT existente de `:1224-1239`. **`AGENDA_WEB_BASE_URL` va env-first, sin excepción (C4).**
4. `backend/services/harness_flags_help.py` → `PLAIN_HELP` (`:25`): **9** entradas `PlainHelp`. Contrato **verificado, son 6 reglas**: `what` ≥10 y ≤200 chars; `on_effect` ≤240; `off_effect` ≤240; `example` ≤300 (`class PlainHelp`, **`:18`**, el v1 decía `:19`; los límites están en `test_plain_help_fields_non_empty_and_bounded`, `:44-53`); `on_effect` y `off_effect` **deben empezar con `"Si "`** (`test_plain_help_on_off_start_with_si`, `:56`); prohibida la denylist de jerga `JARGON_DENYLIST` (`:17`) = `("MCP","TF-IDF","LLM","stdin","stdout","endpoint","frontmatter","prompt","token","regex","backend","frontend","gate","hook","runtime")` con **plural opcional** e insensible a mayúsculas (el `re.search(rf"\b{term}s?\b", field, re.IGNORECASE)` está en `test_plain_help_avoids_jargon_denylist`, `:63-77`), prohibido citar keys `SCREAMING_SNAKE` (`_KEY_RE = \b[A-Z]+_[A-Z0-9_]+\b`, `:22`, chequeado en `:72`) y prohibido referenciar fases (`_PHASE_RE = \bF\d`, `:23`, chequeado en `:74`).
   > **Trampa concreta y verificada:** las 9 entradas hablan de rutas, reintentos y esperas. **`"runtime"`, `"endpoint"`, `"gate"` y `"token"` están prohibidos** y su plural también. Escribir *"la ruta del endpoint"* o *"el runtime del agente"* pone rojo un test **que ya está rojo**, y por eso el error pasa desapercibido: el criterio A2.6 asserta sobre **el contenido del mensaje**, no sobre pass/fail, justamente para atrapar esto.
5. `backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON` (`:467`): **una sola** key, `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`. Las **8 de valor NO van** (no tienen `default=`, así que `default_is_known` es `False` y `test_default_known_only_for_curated` (`:1001`) — que asserta **igualdad de conjuntos** en `:1006`, con los mensajes "Extras"/"Faltantes" en `:1008-1009` — se pondría rojo si las agregás).
6. **v2 / `[NO VERIFICADO]` nº2 RESUELTO — `harness_defaults.env`: NINGUNO es "el fuente".** Los dos archivos existen y **los dos llevan el mismo header**: *"GENERADO por `deployment/export_harness_defaults.py` desde el deploy vivo"*. `backend/harness_defaults.env` (**3 009 B**) es el snapshot **PARCIAL** versionado que el build refresca (`deployment/build_release.ps1:343`, `:516-531`) y que después hornea dentro de `backend\.env` (`:605-620`); `deployment/harness_defaults.env` (**13 719 B**) es el snapshot completo del deploy. **Reglas del v2:**
   - Se pueden **sembrar a mano** las 9 líneas en `backend/harness_defaults.env` (hay precedente: `test_plan74_migrator_wiring.py:46-54`, `test_plan127_flags.py:64`, `test_plan128_plans_board_flag.py:53`, `test_plan130_code_integrity_flag.py:61` asertan líneas concretas de ese archivo), **pero**
   - **PROHIBIDO** que un criterio de aceptación de este plan dependa de esas líneas: se regeneran en cada build y el plan no controla cuándo.
   - **PROHIBIDO** sembrar `AGENDA_WEB_BASE_URL` ahí (C4, regla 3): hornear la URL base de un entorno en el `.env` de otro es el mismo error.
   - **Único chequeo exigible:** `tests/test_harness_flags_bounds.py::test_harness_defaults_env_within_bounds` (`:254`, `skip` si el archivo no existe, `:259`) sigue verde — o sea, si sembrás las numéricas, sus valores tienen que caer dentro de los bounds declarados.
7. **`_FROZEN_BOUNDS`, específica de las numéricas:** `backend/tests/test_harness_flags_bounds.py` → `_FROZEN_BOUNDS` (`:149`). `test_bounds_map_is_frozen` (`:223`) deriva `actual` de **todo** spec con algún bound no-`None` y hace `assert actual == _FROZEN_BOUNDS` (`:231`). Las **5** numéricas con bounds **obligan 5** entradas nuevas:
   ```python
   "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN": (0, 50),
   "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE": (0, 10),
   "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S": (1, 30),
   "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S": (0, 15),
   "QA_NAV_RETRIES": (0, 10),
   ```
   Las 5 califican para tener bounds según el "procedimiento F1 paso 4" documentado en ese archivo (bounds sólo para flags con consumidor real): sus consumidores son `recovery_budget` (F5), `agenda_health` (F1/F1.5) y `uat_test_runner` (F6).
   > **Es un `assert` de IGUALDAD, no de inclusión:** registrar las 5 numéricas sin tocar `_FROZEN_BOUNDS` pone el archivo en **`1 failed`**. Ese es el gate contra el defecto de este punto (criterio A2.4).

8. `api/qa_uat.py` → `_QA_UAT_FLAG_KEYS` (`:82`): agregar las **9**. Sin esto **nacen invisibles para el tool** (trampa documentada del 240 C13). Y `_SPEC_BY_KEY` a nivel de módulo, con `from services.harness_flags import FLAG_REGISTRY` — import legal en un módulo de `api/` (`services/` nunca importa `api/`, la dirección inversa es la normal).

#### F2.4 — El lector del lado tool: `recovery_config.py`

**Archivo nuevo:** `Stacky tools\QA UAT Agent\recovery_config.py`

```python
"""recovery_config.py — Plan 262 F2. Lector unico de la config de recuperacion.

DOS CAMINOS, UN SOLO DEFAULT. Cuando el pipeline corre desde el backend,
api/qa_uat.py::_export_qa_uat_flags escribe estas keys en os.environ. Cuando corre
desde la CLI (que es como se depura y como se verifica el DoD), NADIE las exporta
—trampa documentada del plan 240 C13—. Por eso los defaults EFECTIVOS viven aca
duplicados a proposito, y un test de paridad cross-arbol falla si divergen de config.py.
"""

DEFAULTS: dict[str, str] = {
    "STACKY_QA_UAT_HOT_RECOVERY_ENABLED":    "true",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN":    "6",
    "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE":   "1",
    "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S":  "5.0",
    "STACKY_QA_UAT_HEALTH_PROBE_CONFIRM_S":  "2.0",     # v2 F1.5
    "STACKY_QA_UAT_ROUTE_ALLOWLIST":         "",
    "STACKY_QA_UAT_SAFE_ROUTE":              "",
    "AGENDA_WEB_BASE_URL":                   "http://localhost:35017/AgendaWeb/",
    "QA_NAV_RETRIES":                        "3",       # v2 C9 — el EFECTIVO de hoy
}

def hot_recovery_enabled() -> bool: ...
def recovery_max_per_run() -> int: ...
def recovery_max_per_case() -> int: ...
def health_probe_timeout_s() -> float: ...
def health_probe_confirm_s() -> float: ...         # v2 F1.5
def route_allowlist_raw() -> list[str]: ...
def safe_route_raw() -> str: ...                   # v2/C5: type="str", string tal cual
def base_url() -> str: ...                         # normalizada con "/" final
def nav_retries() -> int: ...                      # v2 C9
def validate_recovery_config() -> list[str]: ...   # [] = OK; strings = problemas
def snapshot() -> dict: ...                        # para el log y para runtime-doctor
```

Casos borde del lector, todos con test:
- valor no numérico (`"abc"`, `"true"`) ⇒ **cae al default**, no levanta. Log en nivel `warning`.
- valor fuera de bounds ⇒ **se clampea** al bound y se registra. El motivo: `value_in_bounds` (`harness_flags.py:5883`) protege la escritura por UI, pero **no** protege una env var puesta a mano.
- csv con espacios y comas colgantes (`" FrmLogin.aspx , ,FrmBusqueda.aspx "`) ⇒ `["FrmLogin.aspx", "FrmBusqueda.aspx"]`.
- `AGENDA_WEB_BASE_URL` sin `/` final ⇒ normalizada con `/` final, **igual que `get_agenda_base_url`** (`environment_preflight.py:76`, `raw.rstrip("/") + "/"`).

**Tests PRIMERO — DOS archivos (1 en el tool, 1 en el backend):**

`tests\unit\test_plan262_recovery_config.py` (tool) — **15 casos**:
`test_defaults_completos` (**las 9** keys presentes; mensaje = las faltantes por nombre) · `test_bool_true_por_default` · `test_bool_off_respetado` (`"false"`, `"0"`, `"no"`) · `test_int_no_numerico_cae_al_default` · `test_int_fuera_de_bounds_se_clampea` (`"999"` ⇒ `50`) · `test_float_timeout_negativo_se_clampea` · **`test_confirm_s_cero_es_valido`** (`"0"` ⇒ `0.0`, no cae al default: cero es una elección legítima) · **`test_confirm_s_fuera_de_bounds_se_clampea`** (`"99"` ⇒ `15.0`) · `test_csv_limpia_espacios_y_vacios` (`" FrmLogin.aspx , ,FrmBusqueda.aspx "` ⇒ `["FrmLogin.aspx","FrmBusqueda.aspx"]`) · `test_csv_vacio_da_lista_vacia` · `test_base_url_normaliza_barra_final` (igual que `environment_preflight.py:77`, `raw.rstrip("/") + "/"`) · `test_safe_route_es_string_no_lista` (**v2/C5**: `safe_route_raw()` devuelve `str`; falla si alguien la implementa como `csv` y devuelve `list`) · **`test_nav_retries_default_es_3`** (v2/C9: el default es 3, no 1) · `test_validate_detecta_safe_route_fuera_de_allowlist` (mensaje contiene la ruta ofensora) · `test_snapshot_no_expone_credenciales` (asserta que `snapshot()` no contiene las claves `AGENDA_WEB_USER` ni `AGENDA_WEB_PASS` ni su valor)

`backend\tests\test_plan262_recovery_flags.py` (backend) — **14 casos**:
1. `test_las_9_keys_estan_en_el_registry` — mensaje del assert = **la lista de las faltantes por nombre**, no un conteo
2. `test_las_9_keys_estan_categorizadas` — `categorize(k) == "calidad_verificacion"` para las 9; mensaje = las mal categorizadas con su categoría real
3. `test_los_tipos_son_los_declarados` — dict `{key: type}` exacto: `bool`/`int`/`int`/`float`/`float`/`csv`/`str`/`str`/`int`
4. `test_solo_la_bool_tiene_default_explicito` — `spec.default is True` para la bool; `spec.default is None` para las **8** de valor
5. `test_las_5_numericas_tienen_bounds` — `(min_value, max_value)` exactos, los 5 pares de la tabla
6. `test_las_9_estan_en_config_py` — `hasattr(config, k)` para las 9
7. `test_defaults_de_config_coinciden_con_el_tool` — **paridad cross-árbol**: extrae el bloque `DEFAULTS = { ... }` de `recovery_config.py` por lectura de texto (recorte entre `"DEFAULTS: dict[str, str] = "` y el primer `"\n}"` inclusive) + `ast.literal_eval`, **sin importar el tool**, y lo compara con `str(getattr(config, k))`. Mensaje = las divergencias con **ambos** valores.
8. `test_las_9_estan_en_la_tupla_de_export` — `set(...) <= set(api.qa_uat._QA_UAT_FLAG_KEYS)`
9. `test_export_de_bool_sigue_siendo_true_false` — **guarda de no-regresión**: para las 5 keys bool preexistentes (`:83-87`), `_export_qa_uat_flags()` produce exactamente `"true"` o `"false"`
10. `test_export_de_valor_no_se_coacciona_a_booleano` — con `config.STACKY_QA_UAT_RECOVERY_MAX_PER_RUN = 6`, `os.environ["STACKY_QA_UAT_RECOVERY_MAX_PER_RUN"] == "6"` y **no** `"true"`
11. **`test_export_de_base_url_es_idempotente_con_el_valor_del_operador`** — **v2/C4, el gate más importante de F2**: con `AGENDA_WEB_BASE_URL="http://otrohost:9999/AgendaWeb/"` en `os.environ` **antes** de que `config` se materialice, `_export_qa_uat_flags()` deja ese mismo string en `os.environ`. **Falla** con una declaración hardcodeada en `config.py`; **pasa** con la env-first.
12. **`test_agenda_web_base_url_se_declara_env_first`** — lee `config.py` como texto y asserta que la asignación de `AGENDA_WEB_BASE_URL` contiene `os.getenv("AGENDA_WEB_BASE_URL"`. Gate estructural: impide que un refactor futuro vuelva a hardcodearla.
13. **`test_qa_nav_retries_default_es_3_en_config`** — v2/C9 + gate anti-regresión de F6: `config.QA_NAV_RETRIES == 3`. Un `1` acá bajaría los reintentos efectivos en silencio.
14. **`test_ninguna_de_las_9_keys_esta_en_curated_defaults_on_salvo_la_bool`** — `_CURATED_DEFAULTS_ON` contiene `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` y **ninguna** de las otras 8. Gate contra el modo de fallo del punto 5 de F2.3.

`backend\tests\test_plan262_recovery_flags.py` se registra en `backend/scripts/run_harness_tests.sh` (array `HARNESS_TEST_FILES`, abre en `:20`, ruta **pelada**: `tests/test_plan262_recovery_flags.py`) **y** en `backend/scripts/run_harness_tests.ps1` (ruta **ENTRECOMILLADA y con coma**: `"tests/test_plan262_recovery_flags.py",`). Los dos regex son distintos: `_SH_RE = ^\s*(tests/[\w/]+\.py)\s*$` (`test_plan259_ratchet_script_parity.py:28`) y `_PS1_RE = ^\s*"(tests/[\w/]+\.py)"\s*,?\s*$` (`:30`). **Sin comillas, PowerShell lee la ruta como nombre de comando, el array parsea con 0 errores y la ruta se pierde MUDA.**

**Comandos:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_recovery_config.py" -q
& $PY -m pytest tests\test_plan262_recovery_flags.py -q          # desde backend/
& $PY -m pytest tests\test_harness_flags.py -q                   # regresión
& $PY -m pytest tests\test_harness_flags_bounds.py -q            # regresión
& $PY -m pytest tests\test_harness_ratchet_meta.py -q            # regresión
& $PY -m pytest tests\test_harness_flags_help.py -q 2>&1 | Select-String "STACKY_QA_UAT_HOT_RECOVERY|STACKY_QA_UAT_RECOVERY_MAX|STACKY_QA_UAT_HEALTH_PROBE|STACKY_QA_UAT_ROUTE_ALLOWLIST|STACKY_QA_UAT_SAFE_ROUTE|AGENDA_WEB_BASE_URL"
& $PY -m pytest tests\test_plan259_ratchet_script_parity.py -q
```

**Criterios de aceptación BINARIOS (mezcla de absolutos y DELTA):**

| # | Criterio | Comando | Antes | Después |
|---|---|---|---|---|
| A2.1 | 15 casos del lector verdes | tool `test_plan262_recovery_config.py` | `ModuleNotFoundError: recovery_config` | `15 passed` |
| A2.2 | 14 casos de flags verdes | `test_plan262_recovery_flags.py` | `14 failed` (el registry no tiene ninguna key) | `14 passed` |
| A2.3 | `test_harness_flags.py` **sigue** en 56 | `test_harness_flags.py` | `56 passed` (medido v2) | `56 passed` |
| A2.4 | **bounds**: sigue en 18 y verde, con las 5 entradas nuevas en `_FROZEN_BOUNDS` | `test_harness_flags_bounds.py` | Si registrás las 5 numéricas **sin** tocar `_FROZEN_BOUNDS` → **`1 failed`** en `test_bounds_map_is_frozen` (`assert actual == _FROZEN_BOUNDS`, `:231`). **Gate corrido contra el defecto.** | `18 passed` |
| A2.5 | ratchet meta **sigue** en 4 | `test_harness_ratchet_meta.py` | Si creás el test backend sin registrarlo en el `.sh` → **`1 failed`** con el archivo nombrado | `4 passed` |
| A2.6 | **DELTA sobre archivo rojo**: ninguna de las 9 keys aparece en `missing` | el `Select-String` de arriba | **9 líneas** con las 9 keys (sin ayuda llana) | **0 líneas**. El archivo sigue en `4 failed, 4 passed` (deuda ajena **79 → 79**, ahora sin las mías) |
| A2.7 | **v2/C1 — ABSOLUTO, no delta**: la paridad `.sh`/`.ps1` sigue **verde** | `test_plan259_ratchet_script_parity.py` | Si registrás sólo en el `.sh` → **`1 failed`** con *"el .ps1 perdio terreno: **66** archivos solo en el .sh (maximo 64)"*. **Gate corrido contra el defecto, y más fuerte que el delta del v1.** | **`12 passed`** (medido v2: lag 64 de 64, holgura CERO) |

> **v2 — el error del v1 en A2.7, para que no vuelva.** El v1 exigía *"el mensaje sigue diciendo 65"* sobre un archivo que **está verde y no emite mensaje**. Un criterio que describe una salida inexistente es peor que no tener criterio: un modelo menor que "no logra" reproducir el rojo esperado puede concluir que rompió algo, o peor, tocar `_PS1_LAG_MAX`. **`_PS1_LAG_MAX = 64` no se toca en ninguna dirección.**

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`, default **ON**. Las 8 claves de valor no necesitan gate propio: con la bool en OFF nadie las lee — **con una excepción declarada**: `QA_NAV_RETRIES` la lee `uat_test_runner` en F6 **sin gate**, porque F6 preserva el comportamiento efectivo de hoy (3 → 3) y gatear un no-cambio agrega una rama muerta.
**Impacto y fallback por runtime:** el registro de flags es backend puro, idéntico en los 3 runtimes. `recovery_config` usa sólo `os` y `re` de la stdlib. Fallback: si `recovery_config` no se puede importar, `agenda_health.probe_agenda` cae a `DEFAULT_PROBE_TIMEOUT_S` (ya está en F1) y `hot_recovery` (F7) se desactiva a sí mismo — degradación al comportamiento de hoy, no ruptura.
**Trabajo del operador:** ninguno obligatorio. Opcionalmente, revisar los **9** controles nuevos en el panel de flags (categoría *Calidad y verificación del entregable*) y ajustar la URL base si su AgendaWeb no está en el puerto 35017 — y con la regla env-first de C4, si ya la tenía configurada en el entorno, **el panel la muestra con su valor real, no con el default**.

---

### F3 — `recovery_classifier.py`: las 5 clases que pidió el operador, mapeadas a las 4 taxonomías que ya existen

**Objetivo (1 frase):** una función determinista que, dada una excepción + la ruta usada + el resultado del probe de salud, devuelva **exactamente una** de las 5 clases del pedido, y su traducción a las categorías que el resto del pipeline ya entiende.

**Valor:** es la pieza que convierte "algo explotó" en "esto es una ruta mala, no una caída". Todo el resto del plan depende de este veredicto.

**Restricción de alcance, explícita:** existen **CUATRO** taxonomías paralelas y divergentes, ninguna con `enum.Enum`:
- `playwright_result_classifier.VALID_VERDICTS` (`:57`, 4 valores) y `VALID_CATEGORIES` (`:58`, **7**: `APP NAV ENV DATA OPS OBS PIP`), con `_CLASSIFICATION_RULES` (`:65`) y entrada `classify_playwright_results` (`:189`).
- `failure_triage.VALID_VERDICTS` (`:58`, **5** — agrega `SKIPPED`) y `VALID_CATEGORIES` (`:59`, **9** — agrega `GEN` y `SEC`), con `_CATEGORY_OWNER` (`:64`) y `_REASON_RULES` (`:92`).
- `uat_failure_analyzer._FAILURE_CATEGORIES` (`:56`).
- `navigation_driver._classify_error` (`:859`), cadena de `if` que devuelve **8** códigos: `NAV_DEVIATION` (`:872`), `NAV_SESSION_LOST` (`:875`), `MENU_LABEL_NOT_FOUND` (`:877`), `APP_ERROR_PAGE` (`:879`), `NAV_AUTH_EXPIRED` (`:882`), `NAV_TIMEOUT` (`:884`), `NAV_FORM_NOT_FOUND` (`:886`) y `NAV_PLAYWRIGHT_ERROR` (`:887`, **un `return` final sin condición**: la función es total, nunca devuelve `None`).

> **v2 / C2 — el conteo del v1 era falso y su gate no servía. Los códigos del driver son ONCE.**
> El v1 decía *"10 códigos"* y armaba el mapa con 10. **Barrido completo del archivo (`error_code=` + `return`), verificado línea por línea:**
>
> | Código | Líneas | ¿Lo devuelve `_classify_error`? |
> |---|---|---|
> | `MENU_LABEL_NOT_FOUND` | `:524`, `:877` | sí |
> | `NAV_SESSION_LOST` | `:551`, `:875` | sí |
> | **`NAV_WRONG_SCREEN`** | **`:569` — y SÓLO ahí** | **NO** (lo emite `via_menu`) |
> | `NAV_TIMEOUT` | `:486`, `:613`, `:836`, `:884` | sí |
> | `NAV_DEVIATION` | `:651`, `:872` | sí |
> | `NAV_FORM_NOT_FOUND` | `:721`, `:886` | sí |
> | `NAV_DOPOSTBACK_NOT_AVAILABLE` | `:734` | **NO** (`_execute_nav`) |
> | `NAV_JS_ERROR` | `:734` | **NO** (`_execute_nav`) |
> | `NAV_AUTH_EXPIRED` | `:807`, `:882` | sí |
> | `APP_ERROR_PAGE` | `:879` | sí |
> | `NAV_PLAYWRIGHT_ERROR` | `:887` | sí (fallback final) |
>
> (`NAV_SUCCESS` aparece **sólo** en el docstring del módulo, `:33`, y nunca como `error_code`: no cuenta.)
>
> **Dos defectos, no uno.**
> 1. **`NAV_WRONG_SCREEN` faltaba en el mapa.** Con el mapa del v1 caería en `UNRECOVERABLE`, o sea *"no se puede hacer nada"*, cuando su significado literal es **"llegué a la pantalla equivocada"** — el caso más central del pedido del operador (*"ruta … mal seleccionada"*). El plan habría abortado exactamente el escenario que vino a resolver.
> 2. **El gate del v1 pasaba con el defecto.** Proponía extraer los códigos con un regex `return "([A-Z_]+)"` **sobre `_classify_error`**, que produce **8**, y assertar `8 ⊆ 10`: verde. Los 3 códigos que **no** salen de `_classify_error` (`NAV_WRONG_SCREEN`, `NAV_DOPOSTBACK_NOT_AVAILABLE`, `NAV_JS_ERROR`) quedaban invisibles para el propio gate que decía protegerlos. Un gate que no puede ver el defecto no es un gate.

**NO se reescribe ninguna de las cuatro.** La taxonomía de recuperación es una **capa de traducción**, no un reemplazo.

**Archivo nuevo:** `Stacky tools\QA UAT Agent\recovery_classifier.py`

```python
# Las 5 clases del pedido del operador. str, no Enum: estos valores viajan a JSONL,
# a runner_output.json y al dossier; un Enum obligaria .value en ~40 sitios y en un
# archivo donde casi todo esta envuelto en `except Exception` un AttributeError
# silencioso seria invisible. Frozenset + constantes es el patron de la casa.
SERVICE_DOWN      = "SERVICE_DOWN"        # caida de servicio
ROUTE_ERROR       = "ROUTE_ERROR"         # error de ruta
SESSION_ERROR     = "SESSION_ERROR"       # error de sesion
FUNCTIONAL_ERROR  = "FUNCTIONAL_ERROR"    # error funcional de la prueba
UNRECOVERABLE     = "UNRECOVERABLE"       # error no recuperable

RECOVERY_CLASSES: frozenset[str] = frozenset({
    SERVICE_DOWN, ROUTE_ERROR, SESSION_ERROR, FUNCTIONAL_ERROR, UNRECOVERABLE,
})

# Mapeo a lo que YA existe. No reemplaza: traduce.
_CLASS_TO_TAXONOMY: dict[str, dict] = {
    SERVICE_DOWN:     {"verdict": "BLOCKED", "category": "ENV", "reason": "APP_NOT_RUNNING",
                       "owner": "devops",        "recoverable": True},
    ROUTE_ERROR:      {"verdict": "BLOCKED", "category": "NAV", "reason": "ROUTE_INVALID",
                       "owner": "qa_automation", "recoverable": True},
    SESSION_ERROR:    {"verdict": "BLOCKED", "category": "NAV", "reason": "SESSION_LOST",
                       "owner": "qa_automation", "recoverable": True},
    FUNCTIONAL_ERROR: {"verdict": "FAIL",    "category": "APP", "reason": None,
                       "owner": "developer",     "recoverable": False},
    UNRECOVERABLE:    {"verdict": "BLOCKED", "category": "OPS", "reason": "UNRECOVERABLE",
                       "owner": "qa_automation", "recoverable": False},
}

# Los ONCE codigos que navigation_driver.py puede producir (v2/C2: el v1 mapeaba 10
# y se dejaba afuera NAV_WRONG_SCREEN, que es justamente "pantalla equivocada").
# Cada linea lleva la linea REAL del driver donde nace, para que el gate de deriva
# sea auditable a mano.
_NAV_CODE_TO_CLASS: dict[str, str] = {
    "NAV_DEVIATION":                ROUTE_ERROR,     # :651, :872
    "NAV_WRONG_SCREEN":             ROUTE_ERROR,     # :569  <-- v2/C2, faltaba
    "MENU_LABEL_NOT_FOUND":         ROUTE_ERROR,     # :524, :877
    "NAV_FORM_NOT_FOUND":           ROUTE_ERROR,     # :721, :886
    "APP_ERROR_PAGE":               ROUTE_ERROR,     # :879
    "NAV_DOPOSTBACK_NOT_AVAILABLE": ROUTE_ERROR,     # :734
    "NAV_SESSION_LOST":             SESSION_ERROR,   # :551, :875
    "NAV_AUTH_EXPIRED":             SESSION_ERROR,   # :807, :882
    "NAV_TIMEOUT":                  UNRECOVERABLE,   # :486, :613, :836, :884 - ver nota
    "NAV_JS_ERROR":                 UNRECOVERABLE,   # :734
    "NAV_PLAYWRIGHT_ERROR":         UNRECOVERABLE,   # :887 (fallback final del driver)
}

def is_recoverable(recovery_class: str) -> bool:
    """v2/C14 — API PUBLICA para F5. Un modulo externo no indexa _CLASS_TO_TAXONOMY:
    una clase desconocida daria KeyError dentro del presupuesto, y un KeyError ahi
    termina rotulado PIPELINE_CRASH, que es el bug que este plan cierra.
    Clase desconocida -> False (conservador: no se recupera lo que no se entiende).
    """
    return bool(_CLASS_TO_TAXONOMY.get(recovery_class, {}).get("recoverable", False))

@dataclass(frozen=True)
class RecoveryVerdict:
    recovery_class: str
    reason_code: str
    route_used: str
    route_allowed: bool | None      # None = no se pudo evaluar
    health: object | None           # HealthProbe | None
    nav_code: str | None            # el codigo de navigation_driver si lo hubo
    evidence: str                   # 1 frase determinista de POR QUE esta clase
    taxonomy: dict                  # copia de _CLASS_TO_TAXONOMY[recovery_class]

def classify_recovery(
    *, exc: BaseException | None = None, exc_text: str = "",
    route_used: str = "", nav_code: str | None = None,
    health: object | None = None, route_allowed: bool | None = None,
) -> RecoveryVerdict: ...
```

**El algoritmo, en el ORDEN EXACTO que pidió el operador:**

```
PASO 1  Capturar el error y registrar la ruta usada.
        route_used se normaliza (F4). Si viene vacia -> route_used = "<desconocida>".
        NO se decide nada todavia.

PASO 2  Verificar si la ruta pertenece al conjunto de rutas permitidas.
        route_allowed = route_allowlist.is_allowed(route_used)  (F4)
        Si route_allowed is False -> candidata FUERTE a ROUTE_ERROR, pero NO se
        cierra aun: hay que descartar que la app este caida (una app caida tambien
        produce URLs raras por redireccion).

PASO 3  Comprobar disponibilidad contra una URL ESTABLE (INV-5).
        health = agenda_health.probe_agenda_confirmed()   # SIEMPRE la base, nunca
        route_used. v2/F1.5: CONFIRMADO (2 muestras) porque su veredicto negativo es
        lo unico que autoriza abrir un proceso en la maquina del operador.

PASO 4  Si RESPONDE (health.alive is True):
        4a. nav_code en _NAV_CODE_TO_CLASS  -> esa clase. (La senal mas especifica
            gana: el driver ya miro la excepcion Y la URL actual.)
        4b. sin nav_code y route_allowed is False -> ROUTE_ERROR
        4c. sin nav_code, ruta permitida, y el texto matchea los patrones de sesion
            (_SESSION_PATTERNS: "frmlogin", "session", "sesion expirada",
            "authentication", "no autenticado") -> SESSION_ERROR
        4d. cualquier otro caso -> FUNCTIONAL_ERROR
            La app esta viva, la ruta es legal, la navegacion no se quejo:
            entonces la prueba fallo. Esto es un RESULTADO, no un incidente.
            INV-2: NO se reintenta.

PASO 5  Si NO RESPONDE (health.alive is False):
        5a. health.samples >= 2  -> SERVICE_DOWN.
            Es la UNICA clase que autoriza intentar levantar el servicio.
        5b. health.samples < 2   -> UNRECOVERABLE con
            evidence="probe sin confirmar: 1 muestra". v2/F1.5: una sola observacion
            no alcanza para gastar el unico arranque de servicio del run.
        (Y si health.source == "http_probe_flapped", health.alive es True: cae por el
         PASO 4, se reintenta el caso, y NO se consume _service_starts.)

PASO 6  Si el presupuesto esta agotado (lo consulta hot_recovery, F7, no este modulo)
        -> el llamador reclasifica a UNRECOVERABLE conservando el reason_code
        original en `reason_code` y poniendo evidence = "presupuesto agotado tras N
        intentos". Marca SOLO el caso afectado.
```

**Casos borde con decisión escrita:**
- **`NAV_TIMEOUT` con la app viva** ⇒ `UNRECOVERABLE`, no `ROUTE_ERROR`. Justificación: un timeout de navegación con el servidor respondiendo significa que la página carga pero no llega al estado esperado; reintentarla es el bucle más caro y menos productivo posible. `navigation_driver` ya reintentó lo suyo con `_RETRY_BACKOFF_S = [1, 2, 4, 8]` (`:105`) y su `asyncio.sleep` en `:481`. Duplicar ese reintento acá viola INV-7.
- **`exc is None` y `exc_text` vacío** ⇒ `UNRECOVERABLE` con `evidence="sin excepcion ni texto: no hay nada que clasificar"`. Nunca `FUNCTIONAL_ERROR`: inventar un fallo funcional a partir de la nada es fabricar un veredicto.
- **`health is None`** (el llamador no pudo hacer el probe) ⇒ `UNRECOVERABLE`. **Nunca** `FUNCTIONAL_ERROR` ni `SERVICE_DOWN`: sin evidencia de salud no se afirma ni una cosa ni la otra. Esto es lo que hoy falta y por eso todo cae en `PIPELINE_CRASH`.
- **Doble señal contradictoria** (`nav_code="NAV_SESSION_LOST"` pero `route_allowed is False`) ⇒ gana el `nav_code` (paso 4a antes que 4b), porque el driver tuvo acceso a la URL real en el momento del fallo. Queda registrado en `evidence` que hubo conflicto.
- **`route_used` es una URL absoluta de otro host** ⇒ `route_allowed is False` en F4 ⇒ `ROUTE_ERROR`. Cubre la "redirección inesperada" del pedido.

**Tests PRIMERO:** `tests\unit\test_plan262_recovery_classifier.py` — **25 casos**:
`test_las_5_clases_y_nada_mas` (`RECOVERY_CLASSES` tiene exactamente 5 y son las nombradas) · `test_toda_clase_mapea_a_una_categoria_existente` (cada `category` del mapeo ∈ `playwright_result_classifier.VALID_CATEGORIES` = `{APP,NAV,ENV,DATA,OPS,OBS,PIP}` **y** ∈ `failure_triage.VALID_CATEGORIES` = esas 7 + `{GEN,SEC}` — **verificado que las 4 categorías usadas (`ENV`,`NAV`,`APP`,`OPS`) están en ambos**) · `test_todo_verdict_esta_en_valid_verdicts` · `test_todo_owner_esta_en_valid_owners` (∈ `failure_triage.VALID_OWNERS`, `:60` = `{developer, qa_automation, devops, product, data_owner}` — **verificado que los 3 owners del mapeo existen**) · `test_app_caida_da_service_down` · `test_ruta_no_permitida_con_app_viva_da_route_error` · `test_nav_deviation_da_route_error` · **`test_nav_wrong_screen_da_route_error`** (v2/C2) · `test_menu_label_not_found_da_route_error` · `test_session_lost_da_session_error` · `test_auth_expired_da_session_error` · `test_nav_timeout_con_app_viva_da_unrecoverable` · `test_app_viva_ruta_legal_sin_nav_code_da_functional_error` · `test_functional_error_no_es_recuperable` (`taxonomy["recoverable"] is False`) · **`test_is_recoverable_publica_coincide_con_la_taxonomia`** (v2/C14: `is_recoverable` para las 5 clases + `is_recoverable("BASURA") is False` **sin levantar**) · `test_health_none_da_unrecoverable_no_functional` · **`test_health_sin_confirmar_no_da_service_down`** (v2/F1.5: `HealthProbe(alive=False, samples=1)` ⇒ `UNRECOVERABLE`, **nunca** `SERVICE_DOWN`; sólo `samples >= 2` lo autoriza) · `test_exc_vacia_da_unrecoverable` · `test_nav_code_gana_sobre_ruta_no_permitida` · `test_evidence_nunca_vacia` (para las 5 clases) · `test_route_used_vacia_se_rotula_desconocida` · `test_redireccion_a_otro_host_da_route_error` · `test_clasificador_no_importa_ningun_modulo_de_llm` (lee el módulo como texto y asserta 0 hits de `invoke_local_llm`, `openai`, `anthropic`, `STACKY_LLM_BACKEND`) · `test_clasificar_es_puro` (dos llamadas con los mismos argumentos devuelven `RecoveryVerdict` iguales) · **`test_los_11_nav_codes_del_driver_estan_mapeados`** ← reescrito, ver abajo

> **v2 / C2 — el gate anti-deriva, reescrito para que SÍ vea el defecto.** `test_los_11_nav_codes_del_driver_estan_mapeados`:
> 1. lee **todo** `navigation_driver.py` como texto (no sólo `_classify_error`);
> 2. extrae el conjunto `found` con **dos** regex, unidos: `r'error_code\s*=\s*"([A-Z][A-Z0-9_]+)"'` y `r'return\s+"([A-Z][A-Z0-9_]+)"'`; descarta `NAV_SUCCESS` con una **allowlist de exclusión nominada y comentada** (`_NOT_AN_ERROR_CODE = {"NAV_SUCCESS"}  # solo docstring :33`);
> 3. **assert bidireccional, con dos mensajes distintos:**
>    - `assert sorted(found - set(_NAV_CODE_TO_CLASS)) == []`, mensaje `f"codigos del driver SIN mapear: {...}"` — atrapa un código nuevo;
>    - `assert sorted(set(_NAV_CODE_TO_CLASS) - found) == []`, mensaje `f"entradas fantasma en _NAV_CODE_TO_CLASS: {...}"` — atrapa un código renombrado o borrado, que es la mitad de la deriva que el v1 ni consideraba;
> 4. y `assert len(found) == 11, f"el driver ahora produce {len(found)} codigos: {sorted(found)}"` — congela el número **medido**, así que si el driver crece el test lo dice con el conteo real, no con un `[]` mudo.
>
> **Prueba de que el gate corre contra el defecto:** borrando la entrada `NAV_WRONG_SCREEN` del mapa, el test **falla** con `codigos del driver SIN mapear: ['NAV_WRONG_SCREEN']`. Con el gate del v1 (regex sólo sobre `_classify_error`), borrar esa misma entrada **pasaba**.

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_recovery_classifier.py" -q`

**Criterio de aceptación BINARIO:** `25 passed`.
**Rojo antes / verde después:** ANTES → `ModuleNotFoundError: No module named 'recovery_classifier'`. DESPUÉS → `25 passed`.
**Gate corrido contra el defecto:** `test_health_none_da_unrecoverable_no_functional` y `test_app_viva_ruta_legal_sin_nav_code_da_functional_error` son el par que discrimina. La implementación prohibida —"si algo explotó, es la app"— hace fallar el segundo; la implementación perezosa —"si no sé, es funcional"— hace fallar el primero. Un clasificador que devuelva siempre `UNRECOVERABLE` falla 8 casos.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` (default ON) protege a su **consumidor** (F7/F8). El módulo en sí es inerte sin llamadores.
**Impacto y fallback por runtime:** stdlib pura (`dataclasses`, `re`). Idéntico en los 3. Fallback: N/A (INV-6 garantiza que no hay dependencia de modelo).
**Trabajo del operador:** ninguno.

---

### F4 — `route_allowlist.py`: rutas permitidas, ruta segura y validación de la URL usada

**Objetivo (1 frase):** decidir de forma determinista si la URL que se usó pertenece al conjunto de rutas permitidas, y cuál es la ruta segura a la que volver.

**Valor:** es el paso 2 del orden exigido por el operador y la única forma de distinguir "URL mal construida" de "la prueba falló".

**Estado hoy:** **no existe** ninguna allowlist de rutas. Lo más cercano es `navigation_driver.CHILD_SCREENS` (`:114`), un `frozenset[str]` de pantallas hijas que **requieren `form.submit()` en vez de `goto()`** — es una lista de *cómo* llegar, no de *qué* es legal. **Corrección a un supuesto del pedido:** el pedido afirmaba que no hay ningún `urljoin` en el tool; **es falso**, `deeplink_readiness_checker.py` lo importa en `:69` (`from urllib.parse import urljoin, urlencode, quote`) y lo usa en `:207` (`full_url = urljoin(base_url, url_relative)`). Es **un solo** importador; el resto del tool concatena con `rstrip("/")`. Este plan usa `urlsplit`/`urljoin` y no toca a los demás.

**Archivo nuevo:** `Stacky tools\QA UAT Agent\route_allowlist.py`

```python
@dataclass(frozen=True)
class RouteVerdict:
    allowed: bool
    normalized: str        # ruta relativa normalizada, ej "FrmBusqueda.aspx"
    absolute: str          # URL absoluta resuelta contra la base
    reason: str            # "in_allowlist" | "not_in_allowlist" | "foreign_host" |
                           # "unparseable" | "outside_base_path"
    source: str            # "configured" | "derived" — de donde salio la allowlist

def effective_allowlist() -> tuple[frozenset[str], str]: ...   # (rutas, source)
def safe_route_url() -> str: ...
def normalize_route(url_or_path: str, *, base_url: str | None = None) -> str: ...
def is_allowed(url_or_path: str, *, base_url: str | None = None) -> RouteVerdict: ...
def is_child_screen(route: str) -> bool: ...   # delega a navigation_driver.CHILD_SCREENS
```

**Derivación de la allowlist cuando `STACKY_QA_UAT_ROUTE_ALLOWLIST` está vacía** (que es el default, F2):

```
1. navigation_driver.CHILD_SCREENS            (import diferido; si falla, se omite)
2. environment_preflight._LOGIN_PATH          ("FrmLogin.aspx", :49)
3. La raiz de la base URL                     ("" y "/" siempre permitidas)
4. La ruta segura configurada, si hay         (auto-inclusion: INV anti-bucle de F2)
=> source = "derived"
```
Con la flag no vacía, la allowlist es **exactamente** lo configurado más la ruta segura (auto-incluida), `source = "configured"`.

> **Decisión de política, explícita: la allowlist derivada es PERMISIVA por diseño.** Con `source == "derived"`, una ruta desconocida pero que *vive bajo el path base* y *termina en `.aspx`* se considera **permitida** (`reason="in_allowlist"`). Motivo: una allowlist derivada incompleta que rechace rutas legítimas convertiría fallos funcionales reales en `ROUTE_ERROR` y los haría reintentar — es decir, **crearía falsos verdes**, violando INV-1. La allowlist sólo se vuelve estricta cuando el operador la declara (`source == "configured"`). Esto es una decisión de seguridad del veredicto, no una comodidad.

**Casos borde con decisión escrita:**
- URL de **otro host** (`http://otro:8080/x.aspx`) ⇒ `allowed=False`, `reason="foreign_host"`. Cubre "redirección inesperada".
- URL **bajo el mismo host pero fuera del path base** (`http://localhost:35017/OtraApp/x.aspx`) ⇒ `allowed=False`, `reason="outside_base_path"`.
- **Ruta relativa** (`"FrmBusqueda.aspx"`, `"./FrmBusqueda.aspx"`, `"/AgendaWeb/FrmBusqueda.aspx"`) ⇒ las tres normalizan a `"FrmBusqueda.aspx"`.
- **Query string y fragmento** (`"FrmDetalleClie.aspx?id=42#tab2"`) ⇒ normaliza a `"FrmDetalleClie.aspx"`. La allowlist es de **rutas**, no de parámetros.
- **Case** ⇒ comparación **case-insensitive** (IIS no distingue mayúsculas en el path). `"frmlogin.aspx"` matchea `"FrmLogin.aspx"`.
- Cadena **vacía o basura** (`""`, `"::::"`, `None`) ⇒ `allowed=False`, `reason="unparseable"`. **Nunca levanta.**
- `safe_route_url()` con `STACKY_QA_UAT_SAFE_ROUTE` vacía ⇒ devuelve la **URL base** tal cual. Siempre hay una ruta segura válida.
- Ruta segura que **es** una `CHILD_SCREEN` ⇒ `is_child_screen()` devuelve `True` y F7 **no** intenta `goto()` sobre ella: vuelve a la base. Un `goto()` a una pantalla hija es exactamente el error que el 214 F2 clasificó como `NAV_DEVIATION`.

**Tests PRIMERO:** `tests\unit\test_plan262_route_allowlist.py` — 20 casos:
`test_allowlist_derivada_incluye_child_screens` · `test_allowlist_derivada_incluye_login_path` · `test_allowlist_configurada_reemplaza_la_derivada` · `test_allowlist_configurada_auto_incluye_la_ruta_segura` · `test_source_es_derived_sin_config` · `test_source_es_configured_con_config` · `test_ruta_relativa_normaliza` · `test_ruta_con_slash_inicial_normaliza` · `test_ruta_absoluta_de_la_base_normaliza` · `test_query_y_fragmento_se_descartan` · `test_case_insensitive` · `test_host_ajeno_no_permitido` · `test_path_base_ajeno_no_permitido` · `test_vacia_es_unparseable` · `test_basura_no_lanza` · `test_derivada_es_permisiva_con_aspx_desconocido` (`allowed is True`, `reason == "in_allowlist"`) · `test_configurada_es_estricta_con_aspx_desconocido` (`allowed is False`) · `test_safe_route_vacia_es_la_base` · `test_safe_route_child_screen_se_detecta` · `test_child_screens_no_se_duplican` (asserta que el módulo **no** define su propia copia: `grep` sobre el texto del módulo da **0** hits de `"FrmDetalleClie.aspx"` fuera del import)

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_route_allowlist.py" -q`

**Criterio de aceptación BINARIO:** `20 passed`.
**Rojo antes / verde después:** ANTES → `ModuleNotFoundError: No module named 'route_allowlist'`. DESPUÉS → `20 passed`.
**Gate corrido contra el defecto:** el par `test_derivada_es_permisiva_con_aspx_desconocido` / `test_configurada_es_estricta_con_aspx_desconocido` es el gate. Una implementación que sea estricta siempre falla el primero (y produce falsos verdes en producción); una que sea permisiva siempre falla el segundo (y no valida nada). `test_child_screens_no_se_duplican` atrapa la tentación de copiar la lista.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` vía sus consumidores. Los **datos** vienen de `STACKY_QA_UAT_ROUTE_ALLOWLIST` y `STACKY_QA_UAT_SAFE_ROUTE`.
**Impacto y fallback por runtime:** `urllib.parse` de la stdlib. Idéntico en los 3. Fallback: si el import diferido de `navigation_driver` falla, la allowlist derivada se arma sin `CHILD_SCREENS` y `is_child_screen` devuelve `False` — degradación (algún `goto()` de más), no ruptura.
**Trabajo del operador:** opcional — declarar la allowlist estricta para su instalación si quiere validación fuerte. Con la caja vacía funciona en modo derivado permisivo.

---

### F5 — `recovery_budget.py`: presupuesto anti-bucle, techo y nunca piso

**Objetivo (1 frase):** garantizar que la recuperación termine, contando intentos por run y por caso, y **sin nunca autorizar** más de lo que las cotas existentes ya permiten.

**Valor:** el operador pidió explícitamente "evitar ciclos infinitos de recuperación". Sin esto, `SERVICE_DOWN → arrancar → probe → SERVICE_DOWN → arrancar…` es un bucle que consume la ventana entera del run.

**Estado hoy:** **no existe** ningún presupuesto global de recuperación. Lo que existe son cotas locales, cada una ciega a las otras: `navigation_driver._MAX_REAUTH_PER_STEP = 1` (`:109`), `replan_engine.MAX_REPLAN_ROUNDS = 3` (`:66`), `QA_UAT_MAX_BROWSER_LAUNCHES` (`uat_test_runner.py:134`, default `"1"`), `QA_UAT_MAX_LOGIN_ATTEMPTS` (`:135`, default `"1"`), `QA_UAT_MAX_TOTAL_MINUTES` (`:139`, default `"6"`, aplicado en `:292`), `playwright_config_writer._ENV_DEFAULTS["QA_UAT_RETRIES"] = "1"` (`:46`, `:52`), y `rerun_guard.run_rerun_guard` (`:276`, cooldown/TTL) más `failure_triage._should_rerun` (`:656`, que **sólo recomienda**).

**Archivo nuevo:** `Stacky tools\QA UAT Agent\recovery_budget.py`

```python
@dataclass
class RecoveryBudget:
    max_per_run: int
    max_per_case: int
    max_service_starts: int          # derivado, ver abajo
    _used_run: int = 0
    _used_by_case: dict = field(default_factory=dict)
    _service_starts: int = 0
    _ledger: list = field(default_factory=list)   # historial completo, para el reporte

    def can_recover(self, case_id: str, recovery_class: str) -> tuple[bool, str]: ...
    def consume(self, case_id: str, recovery_class: str, detail: str = "") -> None: ...
    def attempts_for(self, case_id: str) -> int: ...
    def exhausted_reason(self, case_id: str) -> str: ...   # "" si no esta agotado
    def as_dict(self) -> dict: ...                          # para el JSONL y el reporte

def build_budget() -> RecoveryBudget: ...   # lee recovery_config, aplica INV-7
```

**Cómo `build_budget` respeta INV-7 (el mínimo gana):**

```python
def build_budget():
    import recovery_config as rc
    per_run  = rc.recovery_max_per_run()
    per_case = rc.recovery_max_per_case()
    # INV-7: arrancar el servicio abre un proceso en la maquina del operador.
    # El techo NO puede exceder lo que el 240 ya autoriza: UN intento por run.
    # agenda_web_launcher.ensure_agenda_web documenta "UN intento" (:144) y hace
    # UN solo subprocess.Popen (:148). Se respeta.
    service_starts = 1 if rc.hot_recovery_enabled() else 0
    # Y el per_case nunca puede exceder el per_run.
    per_case = min(per_case, per_run)
    return RecoveryBudget(per_run, per_case, service_starts)
```

**Reglas de `can_recover`, en orden:**
1. `hot_recovery_enabled()` es `False` ⇒ `(False, "hot_recovery_off")`.
2. **`recovery_classifier.is_recoverable(recovery_class)` es `False`** ⇒ `(False, "clase_no_recuperable")`. Esto hace que `FUNCTIONAL_ERROR` **jamás** consuma presupuesto (INV-2) y que el contador no se contamine con resultados legítimos.
   > **v2 / C14 —** el v1 escribía `_CLASS_TO_TAXONOMY[recovery_class]["recoverable"]`: indexación directa de un dict **privado de otro módulo**. Una clase desconocida (por deriva o por un typo) levanta `KeyError` **dentro del presupuesto**, y un `KeyError` ahí termina rotulado `PIPELINE_CRASH` — el bug que este plan cierra, reintroducido por la capa que lo cierra. Se usa la API pública de F3, que ante clase desconocida devuelve `False`.
3. `_used_run >= max_per_run` ⇒ `(False, "presupuesto_de_run_agotado")`.
4. `attempts_for(case_id) >= max_per_case` ⇒ `(False, "presupuesto_del_caso_agotado")`.
5. `recovery_class == SERVICE_DOWN` y `_service_starts >= max_service_starts` ⇒ `(False, "arranques_de_servicio_agotados")`.
6. Si no, `(True, "")`.

**Casos borde con decisión escrita:**
- `max_per_run == 0` ⇒ **modo observación**: `can_recover` siempre `False`, pero la **clasificación sigue ocurriendo y se registra**. El operador ve qué habría recuperado sin que nada se recupere. Es el modo de puesta en marcha honesto.
- `max_per_case > max_per_run` por config inconsistente ⇒ se clampea en `build_budget` (`min`). Un caso no puede reintentar más veces que el run entero.
- `case_id` vacío o `None` ⇒ se normaliza a `"<run>"` y consume del presupuesto de run. Nunca crea una clave `None` en el dict.
- **El presupuesto nunca se reinicia dentro del run.** Ni por caso nuevo, ni por replan, ni por reinicio del navegador. Un contador que se resetea no es un presupuesto: es un bucle con pasos extra.
- `consume` de una clase no recuperable ⇒ **no incrementa** los contadores pero **sí** escribe en `_ledger`. El reporte de F10 necesita saber que pasó, aunque no se haya gastado nada.

**Tests PRIMERO:** `tests\unit\test_plan262_recovery_budget.py` — 16 casos:
`test_build_lee_la_config` · `test_per_case_se_clampea_al_per_run` · `test_service_starts_es_uno_con_flag_on` · `test_service_starts_es_cero_con_flag_off` · `test_flag_off_nunca_recupera` · `test_functional_error_nunca_consume` · `test_agota_per_run` (el 7º intento con `max_per_run=6` da `False` con razón `"presupuesto_de_run_agotado"`) · `test_agota_per_case` · `test_dos_casos_no_comparten_el_contador_por_caso` · `test_dos_casos_si_comparten_el_de_run` · `test_segundo_service_down_no_arranca_de_nuevo` · `test_max_cero_es_modo_observacion` (`can_recover` `False` pero `_ledger` crece al hacer `consume`) · `test_case_id_vacio_no_crea_clave_none` · `test_presupuesto_no_se_reinicia_entre_casos` · `test_ledger_registra_las_no_recuperables` · `test_as_dict_es_json_serializable` (`json.dumps(b.as_dict())` no levanta)

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_recovery_budget.py" -q`

**Criterio de aceptación BINARIO:** `16 passed`.
**Rojo antes / verde después:** ANTES → `ModuleNotFoundError: No module named 'recovery_budget'`. DESPUÉS → `16 passed`.
**Gate corrido contra el defecto:** `test_presupuesto_no_se_reinicia_entre_casos` y `test_segundo_service_down_no_arranca_de_nuevo` son los gates anti-bucle. Una implementación con contador por caso pero sin contador de run pasa 14 de 16 y **permite el bucle infinito** — esos 2 casos son exactamente el defecto.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`; el presupuesto lo consulta en la regla 1 y con OFF nunca autoriza nada.
**Impacto y fallback por runtime:** stdlib pura. Idéntico en los 3. Fallback: si `recovery_config` no importa, `build_budget` devuelve `RecoveryBudget(0, 0, 0)` — modo observación, cero riesgo.
**Trabajo del operador:** ninguno. Opcionalmente subir `RECOVERY_MAX_PER_RUN` si su entorno es inestable, o bajarlo a `0` para observar antes de habilitar.

---

### F6 — Cierre del bug vivo: `QA_UAT_MAX_NAVIGATION_RETRIES` (variable muerta + doble nombre)

**Objetivo (1 frase):** que exista **un solo** nombre canónico para "cuántos reintentos de navegación se permiten", que sea efectivo por los dos caminos (Python y TS), **sin cambiar el número efectivo de hoy**.

**Valor:** cierra un defecto real y elimina una bomba de relojería. Además es el ejemplo mínimo del problema general del plan: dos nombres, dos defaults, un camino de export que no coincide.

**El defecto, ya medido (§2) y RE-VERIFICADO en la crítica v2:** `uat_test_runner.py:136` `max_nav_retries = int(os.environ.get("QA_UAT_MAX_NAVIGATION_RETRIES", "1"))` — **1 hit en todo el archivo, nunca usada**. `navigation_executor.ts` define `allowedAttempts` en `:375`, lee `process.env.QA_UAT_MAX_NAVIGATION_RETRIES ?? process.env.QA_NAV_RETRIES ?? 0` en `:377`, clampea con `Math.min(Math.max(0, requestedRetries), allowedRetries)` en `:382`, devuelve `retries + 1` en `:384`, y se consume en `:397` (`const maxAttempts = allowedAttempts(step)`) y `:526`. El runner exporta **sólo** `QA_NAV_RETRIES` (`:343`: `env.setdefault("QA_NAV_RETRIES", os.environ.get("QA_NAV_RETRIES", "3"))`) sobre `env = {**os.environ, "STACKY_QA_UAT_HEADLESS": headless_flag}` (`:337`). Efectivo hoy: **3**.

> **v2 / C9 — F6 además REGISTRA la clave.** El v1 unificaba el nombre y la dejaba env-only, con la justificación *"gatear un no-cambio de comportamiento sería una rama muerta"*. Eso es correcto para la **flag booleana** y equivocado para el **valor**: el operador pidió literalmente *"reintentos … configurables"* y el riel de Stacky dice que toda config del operador va por UI. `QA_NAV_RETRIES` entra a `FLAG_REGISTRY` como `int`, bounds `(0, 10)`, default **3** (F2.2). El *comportamiento* sigue sin gate; lo que se agrega es la **perilla**.

**El fix, con el número efectivo PRESERVADO:**

```python
# uat_test_runner.py, en el bloque de guardrails (hoy :133-140)
    # ── Plan 262 F6 — UN nombre canonico para la cota de reintentos de navegacion.
    # ANTES: `max_nav_retries` se asignaba y NUNCA se usaba (1 hit en el archivo), y
    # el lado TS (navigation_executor.ts:377) prefiere QA_UAT_MAX_NAVIGATION_RETRIES
    # sobre QA_NAV_RETRIES — la que Python jamas exportaba. Dos nombres, dos defaults
    # (1 y 3), y el efectivo era 3 por accidente.
    # AHORA: QA_NAV_RETRIES es el CANONICO. QA_UAT_MAX_NAVIGATION_RETRIES sigue siendo
    # leible como alias por compatibilidad, y se EXPORTA con el mismo valor para que el
    # TS no pueda resolver un numero distinto del que Python cree.
    # EL DEFAULT SE MANTIENE EN 3: bajarlo a 1 seria una regresion silenciosa de
    # comportamiento disfrazada de limpieza.
    nav_retries_canonical = int(
        os.environ.get("QA_NAV_RETRIES")
        or os.environ.get("QA_UAT_MAX_NAVIGATION_RETRIES")
        or "3"
    )
```
y en el bloque de export a subprocess (hoy `:343`):
```python
    env.setdefault("QA_NAV_RETRIES", str(nav_retries_canonical))
    # Plan 262 F6: se exporta el ALIAS con el MISMO valor. Sin esto, el TS prefiere
    # el alias (:377); si el operador lo setea a mano queda una asimetria muda.
    env.setdefault("QA_UAT_MAX_NAVIGATION_RETRIES", str(nav_retries_canonical))
```

> **Se ELIMINA** la línea muerta `:136`. No se "usa para algo": se borra y su intención queda cumplida por `nav_retries_canonical`. Una variable muerta que se cablea a la ligera es cómo un plan introduce una regresión.
>
> **NO se toca `navigation_executor.ts`.** El orden `alias ?? canonico ?? 0` de `:377` queda tal cual; ahora ambos llegan con el mismo valor, así que el orden deja de importar. Cambiar el TS sería alcance del 214 F2.

**Tests PRIMERO:** `tests\unit\test_plan262_nav_retries_unified.py` — 8 casos, con `patch.dict(os.environ)` y un `subprocess.Popen` mockeado (patrón ya usado por los tests del runner):
1. `test_variable_muerta_eliminada` — el texto de `uat_test_runner.py` tiene **0** hits de `max_nav_retries` (el nombre viejo)
2. `test_default_efectivo_sigue_siendo_3` — sin env vars, el `env` pasado a `Popen` tiene `QA_NAV_RETRIES == "3"`. **Este es el gate anti-regresión.**
3. `test_qa_nav_retries_explicito_gana` — con `QA_NAV_RETRIES="5"` ⇒ `"5"` en ambas keys
4. `test_alias_solo_tambien_funciona` — con **sólo** `QA_UAT_MAX_NAVIGATION_RETRIES="2"` ⇒ ambas keys `"2"` (antes: el alias se leía a una variable muerta y se exportaba `"3"`)
5. `test_ambas_keys_se_exportan_con_el_mismo_valor` — para 4 combinaciones de env, `env["QA_NAV_RETRIES"] == env["QA_UAT_MAX_NAVIGATION_RETRIES"]`
6. `test_valor_no_numerico_cae_al_default_sin_lanzar` — `QA_NAV_RETRIES="abc"` ⇒ `"3"` y **no** `ValueError`
7. `test_cero_se_respeta` — `QA_NAV_RETRIES="0"` ⇒ `"0"` en ambas (desactivar reintentos es legítimo)
8. `test_el_ts_lee_las_dos_keys` — lee `playwright/helpers/navigation_executor.ts` como texto y asserta que **la misma línea** menciona `QA_UAT_MAX_NAVIGATION_RETRIES` **y** `QA_NAV_RETRIES` (gate de deriva: si alguien cambia el TS, este test avisa). **Anclar por contenido, no por número de línea**: buscar la línea que contiene `process.env.QA_UAT_MAX_NAVIGATION_RETRIES` (hoy `:377`) y assertar sobre ESA. Un test anclado a `:377` se rompe con cualquier edición del archivo.
9. **`test_qa_nav_retries_llega_por_flag`** — v2/C9: `QA_NAV_RETRIES` está en `recovery_config.DEFAULTS` con `"3"` y `recovery_config.nav_retries()` devuelve `3` sin env; con `QA_NAV_RETRIES="7"` devuelve `7`; con `"99"` se clampea a `10`.

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_nav_retries_unified.py" -q`
**Regresión obligatoria:** `& $PY -m pytest "$TOOL\tests\unit\test_navigation_driver.py" "$TOOL\tests\unit\test_navigation_strategy_resolver.py" -q` — **correr cada archivo por separado** y anotar los conteos antes y después; deben ser idénticos.

**Criterio de aceptación BINARIO:** `9 passed`, y los dos archivos de regresión con el **mismo** conteo que antes del cambio.
**Rojo antes / verde después:** ANTES → **`4 failed, 5 passed`** (falla 1 porque `max_nav_retries` existe; falla 4 porque el alias no llega; falla 5 porque sólo se exporta una key; falla 9 porque `recovery_config` no tiene la key). DESPUÉS → `9 passed`.
**Gate corrido contra el defecto:** el caso 2 es la trampa. La "limpieza obvia" —hacer que `max_nav_retries` (default `1`) sea la canónica— pasa los casos 1, 4 y 5 y **falla el 2**, porque bajaría los reintentos efectivos de 3 a 1. Ese es exactamente el error que el gate existe para atrapar. Y el caso 13 de `test_plan262_recovery_flags.py` lo cubre desde el otro lado (`config.QA_NAV_RETRIES == 3`).

**Flag que la protege:** **ninguna para el comportamiento, a propósito** — es la corrección de un bug con efecto preservado (3 → 3) y gatear un no-cambio agrega una rama muerta. **Pero el VALOR sí es configurable por UI** (`QA_NAV_RETRIES` en `FLAG_REGISTRY`, v2/C9).
**Impacto y fallback por runtime:** el runner es el mismo en los 3 runtimes; el subprocess `npx playwright test` hereda el `env` del padre en los 3. Fallback: N/A.
**Trabajo del operador:** ninguno. Su comportamiento no cambia.

---

### F7 — `hot_recovery.py`: el orquestador que ejecuta los 6 pasos, y el reintento acotado al caso

**Objetivo (1 frase):** ejecutar el orden de recuperación exigido por el operador, y reintentar **sólo** el caso afectado dejando correr el resto.

**Valor:** es la fase que entrega el requerimiento. Todo lo anterior son piezas; esta las une.

**Archivo nuevo:** `Stacky tools\QA UAT Agent\hot_recovery.py`

```python
@dataclass(frozen=True)
class RecoveryOutcome:
    attempted: bool
    succeeded: bool
    recovery_class: str
    actions: tuple           # ("probe", "return_to_safe_route", "reauth", "start_service", "retry_case")
    verdict: object          # RecoveryVerdict de F3
    attempts: int            # intentos consumidos por ESTE caso hasta ahora
    final_reason: str        # "" si succeeded; el motivo si no
    route_used: str

def recover(
    *, case_id: str, exc: BaseException | None = None, exc_text: str = "",
    route_used: str = "", nav_code: str | None = None,
    budget=None, exec_log=None,
) -> RecoveryOutcome: ...

def retry_case(
    *, spec_file, scenario_id: str, scenario_dir, ticket_id: int,
    headed: bool, timeout_ms: int, verbose: bool, exec_log=None,
) -> dict: ...
```

**`recover()` — los 6 pasos del operador, literales:**

```
PASO 1  CAPTURAR Y REGISTRAR LA RUTA USADA
        exec_log.event("recovery_attempt_start", {"case_id":..., "route_used":...,
                       "exc_type":..., "nav_code":...})
        Se registra ANTES de decidir cualquier cosa. Si el proceso muere aca,
        el operador igual sabe cual era la ruta.

PASO 2  VERIFICAR LA RUTA CONTRA LA ALLOWLIST
        rv = route_allowlist.is_allowed(route_used)

PASO 3  COMPROBAR DISPONIBILIDAD CONTRA UNA URL ESTABLE
        health = agenda_health.probe_agenda_confirmed()   # SIEMPRE la base (INV-5),
                                                          # 2 muestras (v2/F1.5)
        exec_log.event("recovery_health_probe", {...health.__dict__...})

        verdict = recovery_classifier.classify_recovery(
            exc=exc, exc_text=exc_text, route_used=route_used,
            nav_code=nav_code, health=health, route_allowed=rv.allowed)

        ok, why = budget.can_recover(case_id, verdict.recovery_class)
        if not ok:
            -> RecoveryOutcome(attempted=False, succeeded=False, final_reason=why)
               El llamador reclasifica a UNRECOVERABLE (paso 6).

PASO 4  SI RESPONDE  (health.alive is True)
        4a. FUNCTIONAL_ERROR -> NO se recupera (INV-2). attempted=False,
            final_reason="error_funcional_no_se_recupera". Es el RESULTADO.
        4b. volver a ruta base o ruta segura configurada:
              target = route_allowlist.safe_route_url()
              si route_allowlist.is_child_screen(target): target = base_url
              (una CHILD_SCREEN no admite goto: es NAV_DEVIATION garantizado)
        4c. restablecer sesion/contexto:
              SESSION_ERROR -> auth_session_factory.reauth_in_page(page)   [ASYNC]
              PROHIBIDO llamar run_auth_session (:452) desde codigo async:
              es sincrono y el plan 240 C1 ya lo probo.
              Si no hay `page` (no estamos dentro del contexto Playwright),
              la reautenticacion se DELEGA al reintento del caso: el spec
              vuelve a loguearse por su cuenta.
        4d. corregir/recalcular la ruta:
              si rv.allowed is False -> la ruta corregida es la de la allowlist
              que mejor matchea por nombre de archivo (comparacion exacta
              case-insensitive sobre el basename; SIN fuzzy matching: un match
              aproximado que navega a la pantalla equivocada produce un falso
              verde, que INV-1 prohibe). Si no hay match exacto -> ruta segura.
        4e. budget.consume(case_id, clase); reintentar SOLO el caso (retry_case)

PASO 5  SI NO RESPONDE (health.alive is False) -> SERVICE_DOWN
        5a. intentar levantar: agenda_web_launcher.ensure_agenda_web(base_url=...)
            gateado por STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED (del plan 240) y
            por budget.max_service_starts (1).
        5b. esperar disponibilidad: el propio ensure_agenda_web ya hace polling de
            1s hasta timeout_s (:157-163). NO se agrega un segundo bucle de espera.
        5c. re-probe con agenda_health. Si sigue muerto -> UNRECOVERABLE.
        5d. si revivio: budget.consume(...); reanudar desde punto seguro = volver a
            la ruta segura y reintentar el caso.

PASO 6  SI PERSISTE TRAS LOS REINTENTOS PERMITIDOS
        -> marcar SOLO el caso afectado como fallido (F10 arma el reporte con
           ruta usada, excepcion, intentos y motivo final), registrar evidencias,
           y CONTINUAR con los demas casos.
        -> detener todo SOLO si no se puede continuar de forma segura, que es
           exactamente un caso: health.alive is False Y los arranques de servicio
           estan agotados. Sin app, los casos restantes darian BLOCKED igual;
           seguir seria quemar la ventana de tiempo para nada.
```

**`retry_case()` — el reintento acotado, cableando código muerto:**

Delega en `uat_test_runner._run_single_spec` (`:1031`), que **existe, está completo y no tiene ni un llamador**. Se promueve a público con un alias `run_single_spec` (sin underscore) en `uat_test_runner`, manteniendo `_run_single_spec` como el nombre interno para no romper nada que lo referencie por texto.

> **LIMITACIÓN DECLARADA, honesta: el reintento por PASO no es alcanzable desde Python dentro del modelo actual de Playwright.**
> Un spec `.spec.ts` corre **dentro** del proceso de Playwright. Cuando una aserción falla, la excepción se levanta **ahí adentro** y aborta ese spec; Python sólo ve el resultado agregado al terminar el subprocess. Además, `_normalize_step` (`uat_scenario_compiler.py:816`) produce un **`dict` plano** `{"accion", "target", "valor"}` (`_SUPPORTED_ACTIONS` en `:51`, 15 acciones) persistido en `evidence/<ticket>/scenarios.json` (`:837`) — **no existe ningún `TaskStep`/`TestStep`/`Step`** con identidad que Python pueda direccionar para reintentar, y `step_descriptor.build_step_descriptions` (`:54`) es **post-mortem**: parsea `[STEP n]` de los logs con `_STEP_LOG_RE` (`:47`) **después** de la corrida.
> **Reparto real de responsabilidades, sin promesas falsas:**
> - **Reintento por PASO de navegación:** ya existe y es del lado TS — `navigation_executor.allowedAttempts` (`:375`), consumido en `:397` y `:526`. F6 lo hace configurable de verdad. **Este plan no lo reimplementa.**
> - **Reintento por CASO (spec):** es lo que este plan agrega, del lado Python, vía `_run_single_spec`. **Granularidad real: el spec.**
> - **Reintento por paso de ASERCIÓN:** **fuera de alcance y declarado inalcanzable** sin rediseñar el compilador de escenarios para emitir specs con identidad de paso y estado reanudable. Eso es un plan propio, no una fase de este.

**Casos borde con decisión escrita:**
- `budget is None` ⇒ `recover` llama `build_budget()`. Nunca corre sin presupuesto.
- `exec_log is None` ⇒ toda la telemetría se omite en silencio (patrón ya usado en todo el pipeline). La recuperación **no depende** del logger.
- `retry_case` levanta una excepción ⇒ se captura, se cuenta como intento consumido y se devuelve `succeeded=False`. Una excepción en el reintento **no** puede escalar al catch-all: sería el bug original con un paso extra.
- **Reentrada:** `recover` no se llama a sí misma. Si el reintento vuelve a fallar, es el **llamador** (F8 / el loop de casos) quien decide invocar `recover` otra vez, y el presupuesto lo corta. Recursión en un recuperador es un bucle infinito con nombre elegante.
- **`page` no disponible** para `reauth_in_page` ⇒ paso 4c degrada a "el spec se reautentica solo". No se intenta el camino sincrónico.

**Tests PRIMERO:** `tests\unit\test_plan262_hot_recovery.py` — 18 casos, todo mockeado (`agenda_health.probe_agenda`, `ensure_agenda_web`, `run_single_spec`), **cero red y cero navegador**:
`test_paso1_registra_la_ruta_antes_de_decidir` (el primer evento del `exec_log` fake es `recovery_attempt_start` y contiene `route_used`) · `test_paso3_prueba_la_base_no_la_ruta_rota` (la URL pasada al probe es la base, **no** `route_used`) · `test_app_viva_ruta_mala_vuelve_a_ruta_segura` (`"return_to_safe_route" in actions`) · `test_app_viva_ruta_mala_reintenta_solo_el_caso` (`run_single_spec` llamado **1** vez, con **ese** `spec_file`) · `test_app_viva_ruta_legal_funcional_no_reintenta` (`run_single_spec` **0** llamadas, `attempted is False`) · `test_session_error_reautentica` (`"reauth" in actions`) · `test_session_error_no_llama_run_auth_session` (**gate del 240 C1**: `run_auth_session` mockeado, **0** llamadas) · `test_app_caida_arranca_el_servicio` (`ensure_agenda_web` **1** llamada) · `test_app_caida_con_flag_240_off_no_arranca` (**0** llamadas) · `test_segundo_service_down_no_arranca_dos_veces` · `test_app_no_revive_da_unrecoverable` · `test_presupuesto_agotado_no_intenta` (`attempted is False`, `final_reason == "presupuesto_del_caso_agotado"`) · `test_child_screen_como_ruta_segura_usa_la_base` · `test_ruta_corregida_es_match_exacto_o_ruta_segura` (con `"FrmBusquedaX.aspx"` no hay match exacto ⇒ ruta segura; **sin fuzzy**) · `test_excepcion_en_el_reintento_no_escala` (`run_single_spec` levanta `RuntimeError` ⇒ `succeeded is False` y `recover` **no** propaga) · `test_recover_no_es_recursiva` (lee el módulo como texto y asserta 0 hits de `recover(` dentro del cuerpo de `recover`) · `test_sin_exec_log_no_lanza` · `test_run_single_spec_tiene_alias_publico` (`hasattr(uat_test_runner, "run_single_spec")`)

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_hot_recovery.py" -q`

**Criterio de aceptación BINARIO:** `18 passed`.
**Rojo antes / verde después:** ANTES → `ModuleNotFoundError: No module named 'hot_recovery'`. DESPUÉS → `18 passed`.
**Gate corrido contra el defecto:** tres gates atacan las tres formas de hacerlo mal. `test_paso3_prueba_la_base_no_la_ruta_rota` mata la implementación intuitiva (preguntarle a la ruta rota). `test_app_viva_ruta_legal_funcional_no_reintenta` mata la implementación entusiasta (reintentar todo), que es la que produce falsos verdes. `test_session_error_no_llama_run_auth_session` mata la regresión del 240 C1.

---

#### F7.2 — `[v2 / C3 — BLOQUEANTE RESUELTO]` El CALL SITE: dónde se llama `recover()`

**Objetivo (1 frase):** que `hot_recovery.recover()` **se ejecute de verdad**, en un lugar nombrado del código de producción, y no quede como un segundo `_run_single_spec`.

**El agujero, medido.** `uat_test_runner.run` hace exactamente esto y nada más:

```
:172   runs, browser_launches, login_count = _run_all_specs_once(...)   # UN subprocess, TODOS los specs
:186   (bridge de forense, best-effort)
:194   if browser_launches > max_browser_launches:  -> return _blocked     # cota, no recuperacion
:236   pass_count    = sum(1 for r in runs if r.get("status") == "pass")
:237   fail_count    = sum(1 for r in runs if r.get("status") == "fail")
:238   blocked_count = sum(1 for r in runs if r.get("status") == "blocked")
:252   classification = _classify_and_emit_runner_summary(runs=runs, total=len(runs), ...)
:270   return {... "runs": runs, "verdict": classification[...], "meta": {...}}
```

**No hay ningún `for` sobre `runs` que haga algo distinto de contar, y no hay ningún `except` por caso**: la excepción del spec vive y muere dentro del proceso de Playwright. El v1 escribía `recover()` y `retry_case()` y decía *"es el llamador (F8 / el loop de casos) quien decide invocar `recover`"* — **F8 sólo cablea el catch-all del pipeline**, que dispara ante un crash de Python, no ante un spec que falló; y **el "loop de casos" no existe**. Los criterios (d), (e) y (f) del operador quedaban implementados y jamás ejecutados, y los 18 tests de F7 —todos con `run_single_spec` mockeado— **pasaban igual**. Es el pecado que §2 hecho 5 denuncia, cometido por el plan.

**El fix: un bloque nuevo en `uat_test_runner.run`, ENTRE `:172` y `:236`.** No es lógica nueva; es la línea que llama a la lógica de F7.

```python
    # ── Plan 262 F7.2 — RECUPERACION EN CALIENTE POR CASO ─────────────────────
    # UNICO call site de hot_recovery.recover(). Va DESPUES de _run_all_specs_once
    # (:172) y ANTES de los contadores (:236) a proposito: los contadores y el
    # classifier derivan de `runs`, asi que reemplazar una entrada de `runs` aca
    # hace que el reintento fluya al veredicto sin tocar el classifier.
    # Con la flag OFF este bloque es un no-op de una comparacion (INV-8).
    try:
        import recovery_config as _rc
        if _rc.hot_recovery_enabled():
            import hot_recovery as _hr
            _budget = _hr.build_budget_for_run()          # una sola vez por run
            for _i, _r in enumerate(runs):
                if _r.get("status") not in ("fail", "blocked"):
                    continue                              # un pass no se toca JAMAS
                _out = _hr.recover(
                    case_id=str(_r.get("scenario_id") or _r.get("spec") or _i),
                    exc=None,
                    exc_text=f"{_r.get('error','')} {_r.get('message','')}".strip(),
                    route_used=_hr.route_of_case(_r, evidence_out),
                    nav_code=_hr.nav_code_of_case(_r, evidence_out),
                    budget=_budget,
                    exec_log=_exec_log,
                )
                if _out.attempted and _out.succeeded and _out.retried_result is not None:
                    runs[_i] = _out.retried_result         # el reintento REEMPLAZA al caso
                # F10.2 — el reporte va SIEMPRE que se haya intentado o clasificado,
                # exito o no. Es el unico dueno del dict del caso (v2/C12).
                runs[_i]["recovery_report"] = _out.as_report()
    except Exception:                                      # noqa: BLE001
        # INV-8: un fallo de la capa nueva devuelve el comportamiento de hoy.
        logger.warning("recuperacion en caliente no disponible", exc_info=True)
```

**Tres símbolos nuevos que F7 debe exponer (y que el v1 no declaraba):**
- `hot_recovery.build_budget_for_run() -> RecoveryBudget` — alias fino de `recovery_budget.build_budget()`, para que el call site no importe dos módulos.
- `hot_recovery.route_of_case(run_dict, evidence_out) -> str` y `hot_recovery.nav_code_of_case(run_dict, evidence_out) -> str | None` — leen el `execution.jsonl` del run (`ExecutionLogger._write`, `:193`) filtrando por `scenario_id`, con la misma precedencia determinista de `_last_route_used` (F8) y **sin levantar nunca**: sin dato, `""` / `None`.
- `RecoveryOutcome.retried_result: dict | None` y `RecoveryOutcome.as_report() -> dict` — el primero transporta el dict del reintento, el segundo arma el bloque de F10.2. **Esto resuelve C12**: el v1 decía que `recovery_report` colgaba de *"el dict del caso (el que produce `_blocked_result`, `:1003`)"*, pero `_blocked_result(spec_file, scenario_id, reason)` **no tiene parámetro para eso**; el dueño es este call site.

**Reglas duras del call site (cada una con su test):**
1. **Un `pass` no se toca nunca.** El `continue` es lo primero. Sin él, la recuperación podría "mejorar" un caso verde, que es INV-1 al revés.
2. **`_budget` se construye UNA vez, fuera del `for`.** Construirlo dentro reinicia los contadores por caso y convierte el presupuesto en un bucle con pasos extra (F5 lo prohíbe explícitamente).
3. **El `try/except` envuelve TODO el bloque**, no cada iteración: un fallo de import no puede dejar el run a medio recuperar.
4. **`runs[_i]` se reemplaza sólo si `attempted and succeeded and retried_result is not None`.** Un reintento fallido **no** pisa el resultado original (C12 / F11 caso 8: el reporte conserva la excepción original).
5. **`recovery_report` se escribe siempre que hubo clasificación**, aun con `attempted=False` — incluido `FUNCTIONAL_ERROR`, donde el reporte dice *"app viva, ruta legal, no se reintenta"*, que es información que hoy no existe en ninguna parte.

**Tests PRIMERO:** `tests\unit\test_plan262_recovery_call_site.py` — **9 casos**. Se testea llamando a `uat_test_runner.run` con `_run_all_specs_once` **mockeado** para devolver un `runs` fabricado, y `hot_recovery.recover` **espiado**:
1. **`test_recover_se_llama_para_un_caso_fail`** — `runs=[{"status":"fail",...}]` ⇒ `recover` llamado **exactamente 1 vez**. **Este es EL gate de C3**: con el v1 (sin call site) es `0` llamadas.
2. `test_recover_no_se_llama_para_un_caso_pass` — `runs=[{"status":"pass"}]` ⇒ **0** llamadas.
3. `test_recover_se_llama_una_vez_por_caso_recuperable` — 3 casos (`pass`, `fail`, `blocked`) ⇒ **2** llamadas, con los `case_id` correctos.
4. `test_el_presupuesto_se_construye_una_sola_vez` — `build_budget_for_run` llamado **1** vez con 3 casos fallidos. Un `2` o `3` acá es el bucle infinito latente.
5. `test_reintento_exitoso_reemplaza_el_caso_en_runs` — el `runs` devuelto trae el dict del reintento y `pass_count` sube; el `verdict` lo recalcula el classifier existente **sin modificarlo**.
6. `test_reintento_fallido_no_pisa_el_resultado_original` — `runs[0]["status"] == "fail"` y su `error` sigue siendo el original.
7. `test_recovery_report_presente_incluso_sin_intento` — caso `FUNCTIONAL_ERROR`: `attempted is False` y **`recovery_report` existe** igual.
8. `test_flag_off_no_llama_a_recover_y_runs_queda_intacto` — **gate de INV-8**: con `STACKY_QA_UAT_HOT_RECOVERY_ENABLED=false`, `recover` **0** llamadas y `runs` es el mismo objeto sin `recovery_report`.
9. `test_excepcion_en_la_capa_de_recuperacion_no_rompe_el_run` — `recover` levanta `RuntimeError` ⇒ `run()` devuelve el resultado de hoy y **no** propaga.

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_recovery_call_site.py" -q`
**Regresión obligatoria (por archivo, conteos anotados antes y después):**
```
& $PY -m pytest "$TOOL\tests\unit\test_sprint5_playwright_runner.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_p0_observability.py" -q
```

**Criterio de aceptación BINARIO:** `9 passed` + los 2 archivos de regresión con conteo idéntico al baseline de F0.
**Rojo antes / verde después:** ANTES → los casos 1, 3, 4, 5, 7 fallan (no hay call site; `recover` recibe 0 llamadas). DESPUÉS → `9 passed`.
**Gate corrido contra el defecto:** el caso 1 **es** el defecto C3 convertido en test. Toda la F7 del v1 —18 casos, todos verdes— era compatible con `recover()` sin llamadores; el caso 1 hace que eso sea imposible.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` (default ON), consultada en la primera línea del bloque.
**Impacto y fallback por runtime:** es Python del tool, idéntico en los 3. Fallback: el `try/except` que envuelve el bloque **es** el fallback — cualquier fallo devuelve el `runs` de hoy.
**Trabajo del operador:** ninguno.

---

#### F7 — cierre (metadatos del orquestador, F7.1)

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` (default ON) para toda la orquestación; **`STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED`** (del plan 240, default ON) específicamente para el paso 5a. **Dos flags porque hay dos naturalezas**: clasificar y reintentar es inocuo; arrancar un proceso en la máquina del operador ya tiene su propio gate y se respeta.
**Impacto y fallback por runtime:** el orquestador es Python + stdlib. `reauth_in_page` es `async` — **verificado: `auth_session_factory.py:623`, `async def reauth_in_page(page, *, base_url=None) -> dict`** — y requiere un `page` de Playwright; `run_auth_session` es síncrona (**`:452`, `def`, confirmado**) y su docstring en `:665-676` ya prohíbe llamarla desde código async. Igual en los 3 runtimes. Fallback por runtime: ninguno necesario (INV-6). Fallback por **capacidad**: sin Playwright disponible, `retry_case` devuelve `BLOCKED` vía `_blocked_result` (`uat_test_runner.py:1003`), que es el comportamiento de hoy.
**Trabajo del operador:** ninguno. Si quiere ver la recuperación sin que actúe, poner `RECOVERY_MAX_PER_RUN = 0` (modo observación de F5).

---

### F8 — Fin del catch-all: `PIPELINE_CRASH` clasificado, con el traceback intacto

**Objetivo (1 frase):** que el `except Exception` de `qa_uat_pipeline.py:690` clasifique antes de rotular, sin perder ni un byte del traceback que el 241 F6 agregó a propósito.

**Valor:** es el síntoma exacto que reportó el operador. Hasta esta fase, todo lo anterior existe pero el crash sigue diciendo "OPS/PIPELINE_CRASH".

**Archivo:** `Stacky tools\QA UAT Agent\qa_uat_pipeline.py` (4 817 líneas), dentro de `run` (`:314`) — el bloque `except Exception as _pipeline_crash:` (`:690`) y el dict que arma (`:697` en adelante, con `"reason": "PIPELINE_CRASH"` en `:702` y **`"traceback": _crash_tb[-2000:]` en `:706`**, v2: no en `:704`).

> **v2 — dos símbolos de este bloque NO existen todavía y hay que crearlos**: `_last_route_used` y `classify_pipeline_crash`. Verificado: **0 hits en todo el árbol del tool**. El falso amigo más cercano es `_last_result_of(child_id)` en `:4099` — **no** sirve y no hay que reusarlo.

**Diff ilustrativo:**

```python
    except Exception as _pipeline_crash:  # noqa: BLE001
        import traceback as _tb
        # Plan 241 F6 — un crash que esconde SU PROPIA ubicacion es un diagnostico
        # mentiroso: obliga a adivinar. El traceback va al log y a la evidencia.
        _crash_tb = _tb.format_exc()
        logger.error("Sprint 1: pipeline crashed unexpectedly: %s\n%s",
                     _pipeline_crash, _crash_tb)

        # ── Plan 262 F8 — CLASIFICAR ANTES DE ROTULAR ────────────────────────
        # ANTES: todo crash no previsto salia BLOCKED/OPS/PIPELINE_CRASH sin
        # preguntar NUNCA si la app respondia. Una ruta mal construida se leia
        # como "AgendaWeb no disponible". El traceback del 241 F6 se CONSERVA.
        _rc_verdict = None
        try:
            if _recovery_enabled():                      # lee recovery_config
                from recovery_classifier import classify_recovery
                from agenda_health import probe_agenda_confirmed
                _rc_verdict = classify_recovery(
                    exc=_pipeline_crash,
                    exc_text=f"{type(_pipeline_crash).__name__}: {_pipeline_crash}",
                    route_used=_last_route_used(),        # helper nuevo, ver abajo
                    nav_code=None,
                    health=probe_agenda_confirmed(),      # v2/F1.5: confirmado, 2 muestras
                    route_allowed=None,
                )
        except Exception:                                 # noqa: BLE001
            # Un clasificador que rompe NO puede empeorar el diagnostico:
            # se cae al rotulo historico. Degradacion, no ruptura (INV-8).
            logger.debug("clasificacion de recuperacion no disponible", exc_info=True)

        _cat    = "OPS"
        _reason = "PIPELINE_CRASH"
        if _rc_verdict is not None:
            _cat    = _rc_verdict.taxonomy["category"]
            _reason = _rc_verdict.taxonomy["reason"] or "PIPELINE_CRASH"

        pipeline_result = {
            "ok": False,
            "ticket_id": ticket_id,
            "verdict": "BLOCKED",                 # NO cambia: INV-1
            "category": _cat,                     # ENV | NAV | OPS segun evidencia
            "reason": _reason,
            "failed_stage": "pipeline",
            "error": "pipeline_crash",
            "message": str(_pipeline_crash),
            "traceback": _crash_tb[-2000:],       # Plan 241 F6: INTACTO
            # Plan 262 F8 — la evidencia de la clasificacion, no solo el rotulo
            "recovery_class": getattr(_rc_verdict, "recovery_class", None),
            "recovery_evidence": getattr(_rc_verdict, "evidence", ""),
            "route_used": getattr(_rc_verdict, "route_used", ""),
            "app_alive": (None if _rc_verdict is None
                          else bool(getattr(_rc_verdict.health, "alive", False))),
            "stages": stages,
            "elapsed_s": round(time.time() - started, 2),
        }
```

**`_last_route_used()` — helper nuevo, módulo-level en `qa_uat_pipeline.py`:**
Devuelve la última URL/ruta conocida del run, con esta precedencia determinista y **sin levantar nunca**:
1. la última entrada `url_after` / `url_before` del `execution.jsonl` del run (`evidence/<ticket>/<run_id>/execution.jsonl`, escrito por `ExecutionLogger._write`, `:193`);
2. si no hay, el `target` del último paso de `evidence/<ticket>/scenarios.json` (`uat_scenario_compiler.py:837`);
3. si no hay, `""` (que F3 rotula `"<desconocida>"`).

> **`verdict` NO cambia: sigue `"BLOCKED"`.** Un crash no previsto **no** es un `FAIL` funcional ni un `PASS`. Lo que cambia es la **categoría y el motivo** (`ENV/APP_NOT_RUNNING` vs `NAV/ROUTE_INVALID` vs `OPS/PIPELINE_CRASH`), que es lo que el operador necesita para saber si tiene que levantar la app o arreglar un escenario. Cambiar el `verdict` acá sería exactamente el ablandamiento que INV-1 prohíbe.

**Tests PRIMERO:** `tests\unit\test_plan262_pipeline_crash_classified.py` — 12 casos. Se testea el bloque de clasificación de forma aislada extrayéndolo a una función pura `classify_pipeline_crash(exc, route_used, probe) -> dict` en `qa_uat_pipeline.py` (testeable sin arrancar el pipeline):
`test_crash_con_app_caida_da_env_app_not_running` · `test_crash_con_app_viva_y_ruta_mala_da_nav_route_invalid` · `test_crash_con_app_viva_y_ruta_legal_conserva_ops` (sin señal de navegación, un crash genérico sigue siendo `OPS`; no se inventa una causa) · `test_verdict_sigue_siendo_blocked_en_los_3_casos` (**gate de INV-1**) · `test_traceback_se_conserva` (**gate del 241 F6**: el campo `traceback` está presente, no vacío, y contiene el nombre del archivo donde se levantó) · `test_traceback_se_recorta_a_2000` · `test_clasificador_roto_cae_al_rotulo_historico` (`classify_recovery` mockeado para levantar ⇒ `category == "OPS"`, `reason == "PIPELINE_CRASH"`, y **no** propaga) · `test_flag_off_es_byte_identico` (**gate de INV-8**: con la flag OFF, el dict resultante es **igual** al de hoy salvo por las 4 claves nuevas, que son `None`/`""`) · `test_route_used_llega_al_resultado` · `test_app_alive_es_none_sin_clasificacion` · `test_last_route_used_lee_el_jsonl` · `test_last_route_used_no_lanza_sin_archivos` (directorio inexistente ⇒ `""`)

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_pipeline_crash_classified.py" -q`
**Regresión obligatoria (por archivo, conteos anotados antes y después):**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan241_diagnostics.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_plan240_evidence_manifest.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_p0_observability.py" -q
```

**Criterio de aceptación BINARIO:** `12 passed` + los 3 archivos de regresión con conteo idéntico al medido antes del cambio.
**Rojo antes / verde después:** ANTES → `ImportError` / `AttributeError: module 'qa_uat_pipeline' has no attribute 'classify_pipeline_crash'` (colección falla). DESPUÉS → `12 passed`.
**Gate corrido contra el defecto:** `test_crash_con_app_caida_da_env_app_not_running` y `test_crash_con_app_viva_y_ruta_mala_da_nav_route_invalid` son **el defecto exacto** que reportó el operador: hoy los dos dan `OPS/PIPELINE_CRASH`. Con el bloque viejo intacto, ambos fallan. Y `test_traceback_se_conserva` impide "arreglarlo" tirando el traceback del 241.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` (default ON). Con OFF, el rótulo histórico exacto (probado por `test_flag_off_es_byte_identico`).
**Impacto y fallback por runtime:** el pipeline corre **in-process en un `threading.Thread`** desde el backend (documentado en `api/qa_uat.py:74-79`), y desde la CLI corre directo. Los 3 runtimes ven el mismo código Python. Fallback: el `except` alrededor de la clasificación garantiza que un fallo de la capa nueva devuelve el comportamiento de hoy.
**Trabajo del operador:** ninguno. El beneficio es que su próximo `BLOCKED` le va a decir si tiene que levantar la app o arreglar un escenario.

---

### F9 — Una sola DEFINICIÓN de "app viva": las tres copias delegan

**Objetivo (1 frase):** que exista **exactamente una** definición de los alive codes en todo el tool y que las **dos** implementaciones de probe HTTP queden **nominadas con motivo**, sin cambiar ninguna firma pública.

> **v2 / C6 — el objetivo del v1 era inalcanzable por la propia fase.** Decía *"y **una** función de probe HTTP"*, pero esta misma F9 declara que *"el resto del módulo no se toca"*, y `environment_preflight._http_get` (`:225`) sigue vivo y usado en `:164` y `:181`. Además el gate del v1 sólo contaba el frozenset: la mitad del objetivo no se probaba. El v2 baja la promesa a lo que la fase de verdad entrega —**una definición**— y agrega el caso 11, que congela el conjunto de probes en **exactamente 2** con su motivo escrito. Unificarlas es alcance de otro plan (§7).

**Valor:** cierra INV-4 y elimina la causa estructural del bug: tres módulos que opinan sobre lo mismo con código distinto derivan, y ya derivaron (el launcher tiene un fallback hardcodeado por si el import falla).

**Archivos y cambios EXACTOS:**

1. **`environment_preflight.py`** — `_ALIVE_STATUS_CODES` (`:62`) pasa de literal a alias:
   ```python
   # Plan 262 F9 — la definicion canonica vive en agenda_health. El nombre privado
   # se CONSERVA porque agenda_web_launcher._responds lo importa por este nombre
   # exacto (agenda_web_launcher.py:76). Cambiarlo romperia ese import.
   from agenda_health import ALIVE_STATUS_CODES as _ALIVE_STATUS_CODES  # noqa: F401
   ```
   El resto del módulo no se toca: `_CHECK_TIMEOUT_S = 5.0` (`:54`), el comentario *"We do NOT retry — fail fast."* (`:53`), `get_agenda_base_url` (`:67`), `run_environment_preflight` (`:119`) y su uso en `:247` quedan **idénticos**. El preflight sigue siendo fail-fast: eso es correcto para un preflight.

2. **`environment_preflight.py:43`** — `logger = logging.getLogger(__name__)` pasa a `logging.getLogger("stacky.qa_uat.environment_preflight")`, alineándose con la convención del resto del tool. Cambio de 1 línea, sin efecto funcional.

3. **`smoke_path_checker.py`** — se elimina la copia literal de `:40` y se reemplaza por el mismo alias. `_check_http` (`:127`, con su uso de los alive codes en `:140`) delega en `agenda_health.probe_url` **conservando su dict de retorno exacto** (es consumido por `run_smoke_path`, `:45`). Y el `"http://localhost:35017/AgendaWeb/"` hardcodeado de `:66` pasa a `get_agenda_base_url()` — **verificado que `:66` es el ÚNICO hit de `localhost:35017` en ese archivo**, así que el test 6 de abajo es satisfacible.

   > **v2 / C13 — las 4 claves, nombradas.** El v1 decía *"conservando su dict de retorno exacto"* sin decir cuáles. Medido: `_check_http` devuelve **exactamente** `{"ok", "label", "status", "error"}`, idéntico en sus 5 ramas de `return` (`:138`, `:141`, `:142-143`, `:145-146`, `:148`, `:150`). Y `HealthProbe` **no tiene** `ok` ni `label`. Hace falta un **adaptador explícito**, no una sustitución:
   > ```python
   > def _check_http(url: str, label: str = "url") -> dict:
   >     from agenda_health import probe_url
   >     p = probe_url(url, timeout_s=_CHECK_TIMEOUT_S)
   >     return {"ok": p.alive, "label": label, "status": p.status, "error": p.error}
   > ```
   > **Ojo con el falso amigo:** `_check_auth_file` (`:164`) devuelve `{"ok","label","message"}` — forma **distinta**. No unificar las dos: el caller inyecta `check3["note"]` por fuera en `:112` y una "limpieza" ahí rompe `run_smoke_path`.

4. **`agenda_web_launcher.py`** — `_responds` (`:73`) borra su fallback hardcodeado de `:78` y delega:
   ```python
   def _responds(base_url: str, timeout_s: float = 3.0) -> bool:
       """True si AgendaWeb responde con un status 'vivo'. NUNCA lanza."""
       try:
           from agenda_health import probe_url
           return probe_url(base_url, timeout_s=timeout_s).alive
       except Exception:  # noqa: BLE001
           return False
   ```
   `ensure_agenda_web` (`:88`, firma **verificada**: `def ensure_agenda_web(*, base_url=None, timeout_s: int = 60) -> dict:` — **keyword-only**), su polling de 1 s (`:157-163`, con `deadline` en `:157` y `time.sleep(1)` en `:163`), el `started_by_us=True` del retorno (`:160`), `proc.terminate()` (`:167`), `START_TIMEOUT` (`:170`), `stop_agenda_web` (`:179`) y su guarda `if not h.get("started_by_us") or not h.get("pid")` (**`:187`**, v2: el v1 decía `:179`, que es sólo el `def`) **no se tocan**.

**Tests PRIMERO:** `tests\unit\test_plan262_single_source_alive.py` — **11 casos**:
1. `test_una_sola_definicion_del_frozenset` — **gate de conteo con mensaje discriminante**: recorre todos los `*.py` de la raíz del tool y cuenta los que contienen el literal `frozenset({200, 301, 302, 400, 401, 403})`. Debe ser **1** (`agenda_health.py`). El assert reporta **la lista de archivos ofensores por nombre**, no el conteo — `assert offenders == []` con `f"copias de los alive codes en: {offenders}"`.
2. `test_preflight_usa_el_alias` — `environment_preflight._ALIVE_STATUS_CODES is agenda_health.ALIVE_STATUS_CODES`
3. `test_smoke_usa_el_alias` — idem para `smoke_path_checker`
4. `test_launcher_responds_delega` — `agenda_health.probe_url` mockeado; `_responds` devuelve lo que devuelve el mock
5. `test_launcher_no_tiene_fallback_hardcodeado` — 0 hits de `frozenset({200` en `agenda_web_launcher.py`
6. `test_smoke_no_hardcodea_la_base_url` — 0 hits de `"localhost:35017"` en `smoke_path_checker.py`
7. `test_preflight_logger_tiene_el_prefijo_de_la_casa` — el logger del módulo se llama `"stacky.qa_uat.environment_preflight"`
8. `test_run_environment_preflight_sigue_devolviendo_app_not_running` — con `urlopen` mockeado a `URLError`, `reason == "APP_NOT_RUNNING"` (contrato consumido por `qa_uat_pipeline.py:404`)
9. `test_run_smoke_path_conserva_su_contrato` — las claves del dict de `_check_http` son **exactamente** `{"ok","label","status","error"}` (lista literal, v2/C13), y `_check_auth_file` (`:164`) sigue devolviendo su forma propia `{"ok","label","message"}` sin unificarse
10. `test_sin_ciclo_de_imports` — `importlib.import_module("agenda_health")` y luego `importlib.import_module("environment_preflight")` en un intérprete limpio, en **los dos órdenes**, sin `ImportError`
11. **`test_las_implementaciones_de_probe_http_son_las_dos_declaradas`** — **v2/C6, el gate honesto de INV-4**: recorre los `*.py` de la raíz del tool buscando definiciones que hagan `urllib.request.urlopen` y asserta que el conjunto de módulos que las contienen es **exactamente** `{"agenda_health.py", "environment_preflight.py"}`, con el mensaje `f"probes HTTP no declarados en: {sorted(extras)}"`. Congela el número **medido (2)** con motivo escrito para cada uno, y una **tercera** implementación rompe el test. El v1 prometía "una sola" y no la probaba.

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_single_source_alive.py" -q`
**Regresión obligatoria (por archivo):**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan240_agenda_launcher.py" -q      # baseline medido: 9 passed
& $PY -m pytest "$TOOL\tests\unit\test_plan240_login_url_predicate.py" -q
```

**Criterio de aceptación BINARIO:** `11 passed`, **y `test_plan240_agenda_launcher.py` sigue en `9 passed`** (baseline del v1; el implementador lo re-mide en F0 y usa SU número).
**Rojo antes / verde después:** ANTES → `3 failed` como mínimo: el caso 1 falla reportando **3 archivos** (`environment_preflight.py:62`, `smoke_path_checker.py:40`, `agenda_web_launcher.py:78` — los 3 confirmados por grep sobre los `*.py` del tool, ni uno más); el 2 y el 3 fallan por identidad. DESPUÉS → `11 passed`.
**Gate corrido contra el defecto:** el caso 1 es literalmente el defecto contado, **y su mensaje nombra los archivos** — cumpliendo la regla de no colapsar N faltantes a 1 fallo. El caso 10 atrapa el ciclo de imports, que es el modo de fallo más probable de esta fase.

**Flag que la protege:** **ninguna, a propósito.** Es un refactor con contratos preservados y probados; no hay comportamiento nuevo que gatear. Gatear un refactor detrás de una flag deja las dos ramas vivas y duplica el problema que el refactor viene a resolver.
**Impacto y fallback por runtime:** stdlib pura. Idéntico en los 3. Fallback: el `except Exception` de `_responds` preserva el `return False` de hoy.
**Trabajo del operador:** ninguno.

---

### F10 — Reporte de no-recuperable, logs de recuperación y `runtime-doctor` extendido

**Objetivo (1 frase):** que un caso que no se pudo recuperar reporte **ruta usada, excepción, intentos realizados y motivo final**, que toda recuperación quede en los logs, y que el operador pueda ver la config y la salud desde el doctor que ya existe.

**Valor:** es el criterio de cierre explícito del operador. Sin esto, la recuperación es una caja negra.

#### F10.1 — Los logs de recuperación

Usa `ExecutionLogger` (`execution_logger.py:137`), JSONL en `evidence/<ticket>/<run_id>/execution.jsonl`, obtenido con `get_active_logger` (`:118`) y escrito por `_write` (`:193`). **No se agregan métodos nuevos al logger**: se usa el `event` genérico (`:252`), que ya existe, con **6 nombres de evento nuevos**:

| Evento | Cuándo | Campos obligatorios |
|---|---|---|
| `recovery_attempt_start` | paso 1, antes de decidir | `case_id`, `route_used`, `exc_type`, `nav_code` |
| `recovery_health_probe` | paso 3 | `url`, `alive`, `status`, `elapsed_ms`, `error`, **`source`**, **`samples`** (v2/F1.5: sin `samples` el operador no puede distinguir un flap de una caída) |
| `recovery_classified` | tras F3 | `recovery_class`, `reason_code`, `route_allowed`, `evidence` |
| `recovery_action` | por cada acción del paso 4/5 | `action`, `target`, `ok` |
| `recovery_budget_state` | tras cada `consume` | `used_run`, `max_run`, `used_case`, `max_case`, `service_starts` |
| `recovery_outcome` | al cerrar el intento | `succeeded`, `attempts`, `final_reason`, `route_used` |

Además se usan los métodos existentes: `stage_error` (`:287`) para el error original y `flake_suspected` (`:630`) cuando un caso pasa **después** de un reintento — señal honesta de inestabilidad, no de éxito.

> **Los 6 eventos son aditivos.** No se modifica ni se renombra ningún evento existente: hay consumidores de ese JSONL (`_collect_precheck_events_from_evidence`, `uat_test_runner.py:946`; `evidence_manifest.build_evidence_manifest`, `:42`).

#### F10.2 — El reporte de no-recuperable

**v2 / C12 — quién lo adjunta, sin ambigüedad.** El v1 decía *"el dict del caso (el que produce `_blocked_result`, `uat_test_runner.py:1003`)"*, pero `_blocked_result(spec_file, scenario_id, reason)` **no tiene ningún parámetro para un reporte** y no hay que agregárselo. El dueño único es **el call site de F7.2**: `runs[_i]["recovery_report"] = _out.as_report()`. `RecoveryOutcome.as_report()` es la función que arma el bloque, y se escribe **siempre que hubo clasificación**, tanto con `succeeded is False` como con `attempted is False` (el caso `FUNCTIONAL_ERROR`, donde el reporte dice *"app viva, ruta legal, no se reintenta"* — información que hoy no existe en ninguna parte).

El bloque `recovery_report` lleva **exactamente los 4 campos que pidió el operador**, más los que hacen el diagnóstico accionable:

```python
"recovery_report": {
    "route_used":      "FrmDetalleClieX.aspx",       # ruta usada
    "exception":       "TimeoutError: waiting for ...",# excepcion
    "exception_type":  "TimeoutError",
    "attempts":        2,                              # intentos realizados
    "final_reason":    "presupuesto_del_caso_agotado", # motivo final
    "recovery_class":  "ROUTE_ERROR",
    "route_allowed":   False,
    "app_alive":       True,                           # la evidencia de que NO fue caida
    "actions_taken":   ["probe", "return_to_safe_route", "retry_case"],
    "safe_route":      "http://localhost:35017/AgendaWeb/",
    "evidence":        "app viva y ruta fuera de la allowlist declarada",
}
```
`None` está **prohibido** en `route_used`, `exception`, `attempts` y `final_reason`: si el dato no se pudo obtener, se escribe `"<desconocida>"` / `""` / `0` / `"sin_motivo_registrado"`. Un campo `None` en un reporte de diagnóstico obliga al operador a adivinar, que es el pecado que el 241 F6 corrigió con el traceback.

#### F10.3 — `runtime-doctor` extendido (del 240 F8, **se extiende, no se duplica**)

`api/qa_uat.py::get_runtime_doctor` (`:1977`, ruta `@bp.get("/runtime-doctor")` en `:1976`) suma **una** sección:

```python
"hot_recovery": {
    "enabled": bool(...),
    "config": {...},              # recovery_config.snapshot(), SIN credenciales
    "allowlist": {"source": "derived"|"configured", "count": 7, "routes": [...]},
    "safe_route": "...",
    "health": {...},              # agenda_health.probe_agenda(), en vivo. UNA muestra:
                                  # el doctor informa, no autoriza arrancar nada, asi
                                  # que no paga la pausa de confirmacion (v2/F1.5)
    "flags_exported": [...],      # las 9 keys y el valor con el que salieron
}
```
Aditivo: ninguna clave existente de la respuesta cambia de nombre, tipo ni posición.

**Tests PRIMERO — dos archivos:**

`tests\unit\test_plan262_unrecoverable_report.py` (tool) — 12 casos:
`test_los_4_campos_del_operador_estan_presentes` (mensaje = **los que faltan por nombre**) · `test_ningun_campo_obligatorio_es_none` · `test_route_used_desconocida_cuando_no_se_sabe` · `test_attempts_es_entero_no_none` · `test_final_reason_nunca_vacio` · `test_app_alive_true_cuando_la_app_respondio` (**el campo que prueba que NO fue una caída**) · `test_los_6_eventos_se_emiten_en_orden` (con un `exec_log` fake: la secuencia de nombres es exactamente `["recovery_attempt_start","recovery_health_probe","recovery_classified","recovery_action","recovery_budget_state","recovery_outcome"]`) · `test_ningun_evento_existente_se_renombra` (lee `execution_logger.py` y asserta que los nombres de método `event`/`stage_error`/`flake_suspected`/`pipeline_verdict`/`screenshot`/`human_decision`/`error` siguen existiendo) · `test_flake_suspected_cuando_pasa_tras_reintento` · `test_reporte_es_json_serializable` · `test_reporte_no_contiene_credenciales` (0 hits de `AGENDA_WEB_PASS` y del valor de la password en el JSON serializado) · `test_sin_exec_log_el_reporte_se_arma_igual`

`backend\tests\test_plan262_runtime_doctor_recovery.py` (backend) — **7 casos**:
`test_doctor_tiene_seccion_hot_recovery` · `test_las_claves_previas_del_doctor_siguen` (**gate de no-regresión**: el set de claves top-level de hoy ⊆ el de mañana; `get_runtime_doctor` en `api/qa_uat.py:1977`, ruta `@bp.get("/runtime-doctor")` en `:1976`, **ambas verificadas**) · `test_config_expuesta_no_trae_password` · `test_allowlist_declara_su_source` · `test_health_se_reporta_aunque_la_app_este_caida` (probe mockeado a `alive=False` ⇒ 200 OK con `alive: false`, **no** un 500) · `test_flags_exported_lista_las_9` · **`test_health_expone_samples_y_source`** (v2/F1.5: la sección trae `samples` y `source`, para que el operador vea si fue caída confirmada o flap)

Este archivo backend se registra en **`.sh` (ruta pelada, array `HARNESS_TEST_FILES` que abre en `:20`) Y `.ps1` (entrecomillada con coma)**, igual que el de F2. **Con el lag de paridad en 64/64 (holgura cero), omitir el `.ps1` pone rojo `test_plan259_ratchet_script_parity.py`.**

**Comandos:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_unrecoverable_report.py" -q
& $PY -m pytest tests\test_plan262_runtime_doctor_recovery.py -q         # desde backend/
& $PY -m pytest tests\test_harness_ratchet_meta.py -q                    # sigue en 4 passed
& $PY -m pytest tests\test_plan259_ratchet_script_parity.py -q           # v2: sigue en 12 passed
```

**Criterio de aceptación BINARIO:** `12 passed` (tool) + `7 passed` (backend) + `test_harness_ratchet_meta.py` en `4 passed` + **`test_plan259_ratchet_script_parity.py` en `12 passed`** (v2/C1: es un criterio ABSOLUTO; el v1 pedía leer un mensaje que no existe).
**Rojo antes / verde después:** ANTES → tool `12 failed` (no existe `recovery_report`); backend `7 failed` (no existe la sección); si se crean los 2 archivos backend sin registrar en el `.sh`, `test_harness_ratchet_meta.py` da `1 failed` **nombrando los archivos**; y si se registran en el `.sh` **pero no en el `.ps1`**, la parity test da `1 failed` con *"66 archivos solo en el .sh (maximo 64)"*. DESPUÉS → todo verde, incluida la parity en `12 passed`.
**Gate corrido contra el defecto:** `test_los_4_campos_del_operador_estan_presentes` es el criterio del operador convertido en gate, y su mensaje **nombra los faltantes** en vez de colapsarlos. `test_app_alive_true_cuando_la_app_respondio` es el que prueba que el reporte dice *"la app estaba viva"* — la información que hoy no existe en ninguna parte y sin la cual el operador no puede saber que no fue una caída.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`. Con OFF, `recovery_report` no se emite (no hay recuperaciones) y la sección del doctor reporta `"enabled": false` con el resto vacío — **sigue respondiendo 200**, porque un doctor que falla cuando la feature está apagada es un doctor roto.
**Impacto y fallback por runtime:** el endpoint es Flask del backend; el reporte es Python del tool. Idénticos en los 3. Fallback: el probe en vivo del doctor está envuelto y ante fallo reporta `alive: false` con el error, nunca un 500.
**Trabajo del operador:** ninguno obligatorio. Para diagnosticar, abrir `GET /api/qa-uat/runtime-doctor` y leer `hot_recovery`.

---

### F11 — El invariante del 241: la recuperación NO ablanda el veredicto

**Objetivo (1 frase):** probar con tests dedicados que ningún camino de recuperación puede convertir un fallo real en `PASS`, ni un `BLOCKED` honesto en `MIXED`.

**Valor:** es la fase que hace que este plan sea compatible con el 241 en vez de destruirlo. Sin ella, la recuperación es la mejor máquina de falsos verdes jamás construida en este repo.

**Por qué hace falta un test y no una promesa:** el 241 C4 documenta un caso **ya ocurrido** en este mismo subsistema: si el evaluador se saltaba (`stages["evaluator"] = {"ok": True, "skipped": True, "reason": "all_scenarios_blocked"}`, **`qa_uat_pipeline.py:3170`** — v2: el v1 anclaba `:3090`), el gate funcional devolvía `MIXED/NO_FUNCTIONAL_ASSERTION` **tapando un `BLOCKED` honesto**. El mismo patrón con recuperación en el medio es más fácil de introducir y más difícil de ver.

**Archivo nuevo:** `tests\unit\test_plan262_no_verdict_softening.py` — **15 casos**, el gate más importante del plan:

1. `test_functional_error_no_dispara_recuperacion` — app viva + ruta legal ⇒ `attempted is False` y `run_single_spec` con **0** llamadas
2. `test_fail_tras_reintento_sigue_siendo_fail` — el caso falla, se reintenta, vuelve a fallar ⇒ verdict final `"FAIL"`, **nunca** `"SKIPPED"` ni `"MIXED"`
3. `test_fail_que_pasa_al_reintentar_no_se_reporta_como_pass_limpio` — pasa en el reintento ⇒ el caso lleva `flake_suspected` y `attempts >= 1` en su reporte. Un `PASS` con historial de reintento **no es** un `PASS` limpio y el artefacto debe decirlo.
4. `test_blocked_honesto_no_se_convierte_en_mixed` — `SERVICE_DOWN` no recuperable ⇒ `verdict == "BLOCKED"`
5. `test_recuperacion_no_puede_producir_pass_con_cero_tests` — **gate de INV-3**: con `total == 0`, el verdict es `BLOCKED/PIP/NO_TESTS_FOUND` con o sin recuperación
6. `test_ningun_camino_devuelve_pass` — **gate exhaustivo**: se recorren **las 5** clases de recuperación × {recuperación exitosa, fallida} = 10 combinaciones, y se asserta que en ninguna `RecoveryOutcome` ni en ningún dict de caso aparece `verdict == "PASS"` como *consecuencia de la recuperación*. Mensaje del assert = **la combinación ofensora**, no un conteo.
7. `test_el_presupuesto_agotado_no_baja_la_severidad` — agotado ⇒ `UNRECOVERABLE` con `verdict == "BLOCKED"`, no `SKIPPED`
8. `test_reintento_no_borra_el_fallo_original` — el `recovery_report` del caso reintentado conserva la excepción **original**, no sólo la del último intento
9. `test_recuperacion_no_toca_los_criterios_funcionales` — lee `hot_recovery.py`, `recovery_classifier.py`, `recovery_budget.py` y `route_allowlist.py` como texto y asserta **0** hits de `criteria`, `acceptance`, `functional_verdict`, `discrimination`. La capa de recuperación **no tiene permiso** de tocar el gate funcional del 241.
10. `test_recuperacion_no_escribe_en_el_veredicto_del_pipeline` — 0 hits de `pipeline_verdict(` en los 4 módulos nuevos
11. `test_clasificador_no_emite_pass` — ningún valor de `_CLASS_TO_TAXONOMY[*]["verdict"]` es `"PASS"`
12. `test_functional_error_mapea_a_fail_no_a_blocked` — `FUNCTIONAL_ERROR` ⇒ `verdict "FAIL"`. Mandarlo a `BLOCKED` sería el ablandamiento inverso: convertir un bug del desarrollo en un problema de entorno.
13. `test_verdicts_del_mapeo_son_subconjunto_de_los_oficiales` — todos ∈ `playwright_result_classifier.VALID_VERDICTS` (`:57`)
14. `test_con_flag_off_los_veredictos_son_los_de_hoy` — **gate de INV-8**: los 5 escenarios de arriba con `STACKY_QA_UAT_HOT_RECOVERY_ENABLED=false` producen exactamente los verdicts previos al plan
15. **`test_nav_wrong_screen_no_ablanda_el_veredicto`** — **v2/C2**: `NAV_WRONG_SCREEN` (`navigation_driver.py:569`) clasifica `ROUTE_ERROR`, es recuperable, y **el caso reintentado que vuelve a fallar sigue en `FAIL`**. Es el código más on-point del pedido del operador (*"pantalla equivocada"*) y el que el v1 dejaba sin mapear: hay que probar **las dos cosas** — que se recupera **y** que recuperarse no lo ablanda.

> **v2 — nota sobre el caso 9 (gate estructural) y la auto-colisión.** El caso 9 asserta **0 hits** de `criteria`, `acceptance`, `functional_verdict` y `discrimination` en el texto de `hot_recovery.py`, `recovery_classifier.py`, `recovery_budget.py` y `route_allowlist.py`. **Prohibido copiar la prosa justificativa de este plan a los docstrings de esos módulos**: la decisión de política de F4 y varias notas de este documento usan la palabra *"criterio"* y sus vecinas, y una explicación bien intencionada en un docstring pone rojo el gate del propio plan. Los docstrings de esos 4 módulos hablan de rutas, salud, presupuesto y clases — no del gate funcional del 241. **`test_plan262_recovery_call_site.py` y el bloque de F7.2 NO están en el alcance del caso 9** (viven en `uat_test_runner.py`, que ya menciona esas palabras por razones ajenas): el caso 9 se limita a los **4 módulos nuevos** nombrados.

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_no_verdict_softening.py" -q`
**Regresión obligatoria del 241 (por archivo, conteos anotados):**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan241_discrimination.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_plan241_golden_suite.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_plan241_diagnostics.py" -q
```

**Criterio de aceptación BINARIO:** `15 passed`, **y los 3 archivos del 241 con conteo idéntico al baseline que mida el implementador en F0**.
**Rojo antes / verde después:** ANTES → colección falla (`ModuleNotFoundError`) hasta que F3/F5/F7/F7.2 existen; con F7 implementada **pero sin la regla de INV-2**, fallan los casos **1, 6 y 12** — y ese es exactamente el diseño peligroso que este gate existe para atrapar.
**Gate corrido contra el defecto:** el caso 6 es el gate exhaustivo. Una implementación "servicial" que al recuperar exitosamente marque el caso como `PASS` pasa 13 de 14 y **falla el 6**, nombrando la combinación. El caso 9 es un gate estructural: impide que una fase futura cablee la recuperación al gate funcional, que es la única forma de que INV-1 se rompa sin que nadie lo note.

**Flag que la protege:** ninguna. **Un invariante no se gatea.** Si pudiera apagarse, no sería un invariante.
**Impacto y fallback por runtime:** tests puros. Idénticos en los 3.
**Trabajo del operador:** ninguno. Este gate existe para que el operador pueda seguir confiando en que un `PASS` significa algo.

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación (concreta, con anclaje) |
|---|---|---|---|---|
| R-1 | **La recuperación genera falsos verdes** — un caso que debía fallar termina en `PASS` por reintento | Media | **CRÍTICO** — destruye el 241 | INV-1 + INV-2; `FUNCTIONAL_ERROR` no consume presupuesto (F5 regla 2); F11 con 14 gates, incluido el exhaustivo de 10 combinaciones (caso 6) y el estructural (caso 9) |
| R-2 | **Bucle de recuperación** consume la ventana del run | Media | Alto | F5: presupuesto por run **y** por caso, que **nunca se reinicia**; `max_service_starts = 1` (INV-7); `recover` no es recursiva (test 16 de F7) |
| R-3 | **Ciclo de imports** `agenda_health` ↔ `environment_preflight` | Media | Alto — rompería el tool entero | `agenda_health` **posee** los alive codes y no importa `environment_preflight` a nivel de módulo; el import de `get_agenda_base_url` es diferido dentro de la función (F1); test 10 de F9 importa en **los dos órdenes** |
| R-4 | ~~El panel de flags no renderiza inputs numéricos/csv~~ | **NULA** | — | **v2/C8: RIESGO INEXISTENTE, CERRADO.** `HarnessFlagsPanel.tsx` renderiza `bool:94`, `int:115`, `float:130`, `csv:145`, `str:157`, `json:169`, con `min`/`max` cableados y hint de bounds en `:293-301`. No hay nada que verificar y **la tarea manual nº1 del operador se elimina**. |
| **R-16** | **`AGENDA_WEB_BASE_URL` pisa el valor del operador** y el probe pega contra la URL equivocada ⇒ `SERVICE_DOWN` falso | **Alta si se implementa mal** | **CRÍTICO** — convierte un setup que funciona en uno roto, y con el rótulo exacto que el plan viene a eliminar | **v2/C4:** declaración **env-first** obligatoria en `config.py`; casos 11 y 12 de `test_plan262_recovery_flags.py` (idempotencia + gate estructural); prohibido sembrarla en `harness_defaults.env`; prohibido que un criterio dependa de esa línea |
| **R-17** | **`recover()` sin call site**: la capa se construye, se testea con mocks y **nunca corre** | **Alta** (era el estado del v1) | **CRÍTICO** — el plan entregaría 0 % del pedido con 100 % de los tests verdes | **v2/C3:** F7.2 nombra el call site exacto (`uat_test_runner.run`, entre `:172` y `:236`) y su caso 1 (`test_recover_se_llama_para_un_caso_fail`) es imposible de pasar sin él |
| **R-18** | **Un probe de una muestra gasta el único arranque de servicio** ante un reciclado de AppPool, y termina rotulando *"app caída"* | Media | Alto | **v2/F1.5 `[ADICIÓN ARQUITECTO]`:** `SERVICE_DOWN` exige `samples >= 2`; un muerto seguido de un vivo es `http_probe_flapped` y **no** consume `_service_starts`; casos 12-13 de F1 y `test_health_sin_confirmar_no_da_service_down` en F3 |
| **R-19** | **Deriva de tipos en `FlagSpec`**: el comentario de `harness_flags.py:23` omite `"str"` y el próximo plan repite el error del v1 | Media | Bajo | **v2/C5:** F2.3 punto 1 corrige el comentario a `"bool" \| "csv" \| "int" \| "float" \| "str" \| "json"` |
| R-5 | **El exportador booleano destruye los valores** | **Alta si no se arregla** | Alto — `int("true")` ⇒ `ValueError` ⇒ … `PIPELINE_CRASH` | F2.1 lo arregla con export por `spec.type`; casos 9 y 10 de `test_plan262_recovery_flags.py`, incluida la guarda de no-regresión de las 5 bool |
| R-6 | **Regresión silenciosa de reintentos** 3 → 1 al unificar el nombre | Media | Medio | F6 caso 2 (`test_default_efectivo_sigue_siendo_3`) es un gate dedicado exactamente a eso |
| R-7 | **La allowlist derivada rechaza rutas legítimas** y convierte `FAIL` en `ROUTE_ERROR` reintentable | Media | Alto (es R-1 por otra puerta) | La derivada es **permisiva por diseño** (F4, decisión escrita); sólo se vuelve estricta cuando el operador declara la lista; par de tests permisiva/estricta |
| R-8 | **Ruta segura fuera de la allowlist** ⇒ bucle garantizado | Baja | Alto | `route_allowlist` **auto-incluye** la ruta segura; `validate_recovery_config()` lo reporta; test dedicado en F2 y F4 |
| R-9 | **Deriva de los códigos de `navigation_driver`**: un código nuevo queda sin mapear y cae a `UNRECOVERABLE` | Media | **Alto** (v2: el riesgo YA ESTABA MATERIALIZADO — `NAV_WRONG_SCREEN` faltaba, y es el código central del pedido) | **v2/C2:** `test_los_11_nav_codes_del_driver_estan_mapeados` escanea **todo el archivo** (`error_code=` **y** `return`), no sólo `_classify_error`; es **bidireccional** (huérfanos **y** entradas fantasma, con mensajes distintos) y congela el conteo medido (**11**). El gate del v1 pasaba con el defecto |
| R-10 | **El gate rojo de fábrica** (`test_harness_flags_help.py`) hace ilegible el resultado | Alta (ya es así) | Medio | **v2/C1: es UNO, no dos.** F0.1 lo mide y nomina (**79** keys ajenas, no 80); A2.6 es criterio **delta sobre el contenido del mensaje**, no sobre pass/fail. **A2.7 deja de ser delta: la paridad `.sh`/`.ps1` está VERDE y se exige verde.** |
| R-11 | **`agenda_web_launcher` mata un proceso que no arrancó** | Baja | Alto (mataría el IIS del operador) | **No se toca** `ensure_agenda_web` ni `stop_agenda_web`. La lógica `started_by_us` (retorno en `:160`, guarda del stop en **`:187`** — v2: el v1 decía `:179`) es del 240 y queda intacta; F7 sólo la **invoca**, con `base_url=` (keyword-only, verificado) |
| R-12 | **El probe en caliente agrega latencia** al run | Alta (por diseño) | Bajo | **v2, recalculado con F1.5:** el peor caso es 2 muestras (5 s + 2 s pausa + 5 s = 12 s) **y sólo ante excepción**, acotado por `RECOVERY_MAX_PER_RUN` (6). Techo: 72 s sobre una ventana de 6 min = **20 %**, sólo en el caso patológico de 6 fallos con app muerta, y sólo en runs que **hoy mueren enteros**. En el caso normal (app viva) es 1 GET de milisegundos |
| R-13 | **Sesión paralela sobre el mismo árbol** pisa los cambios | Media (documentada) | Alto | `git worktree list` **antes** de tocar nada; commits con **pathspec explícito**; **prohibido** `amend`/`reset`/`rebase`/`stash` |
| R-14 | **El pipeline in-process comparte `os.environ`** entre runs concurrentes | Baja (mono-operador) | Medio | Limitación **ya documentada** en `_export_qa_uat_flags` (`api/qa_uat.py:94-99`). Este plan la hereda y **no la empeora**; se anota en el docstring de `recovery_config` |
| R-15 | **F8 pierde el traceback del 241 F6** al refactorizar el catch | Media | Alto | `test_traceback_se_conserva` + `test_traceback_se_recorta_a_2000` en F8; el diff ilustrativo conserva la línea literal |

---

## 7. Fuera de scope (explícito)

Este plan **NO**:

1. **No reescribe las 4 taxonomías existentes.** `playwright_result_classifier` (`:57` = `{PASS,FAIL,BLOCKED,MIXED}`, `:58` = `{APP,NAV,ENV,DATA,OPS,OBS,PIP}`, `:65`, entrada en `:189`), `failure_triage` (`:58` = las 4 + `SKIPPED`, `:59` = las 7 + `{GEN,SEC}`, `:60` = `{developer,qa_automation,devops,product,data_owner}`, `:64`, `:92`), `uat_failure_analyzer._FAILURE_CATEGORIES` (`:56`, 7 miembros) y los **11** códigos de `navigation_driver` (`_classify_error` en `:859` + `via_menu` en `:569` + `_execute_nav` en `:734`) quedan **exactamente** como están. **Todos esos anclajes fueron verificados en la crítica v2.** La taxonomía de recuperación **mapea** a ellas.
2. **No convierte ninguna taxonomía a `enum.Enum`.** Sería un refactor transversal de riesgo alto y valor estético.
3. **No implementa reintento por PASO de aserción.** Declarado inalcanzable en F7 con la evidencia, y **la crítica v2 la CONFIRMÓ y la reforzó**: `_normalize_step` (`uat_scenario_compiler.py:816`) devuelve literalmente `{"accion": ..., "target": ..., "valor": ...}` — 3 claves, **ninguna de identidad**; **no existe ninguna clase `TaskStep`/`TestStep`/`Step` en todo el árbol del tool** (0 hits, incluyendo `_attic`); y `templates\playwright_test.spec.ts.j2` tiene **0 ocurrencias de `test.step(`**: la identidad del paso es **posicional** (`loop.index` de Jinja en `:560`, `:564`, `:609`, `:623`) y se recupera *post mortem* parseando `[STEP nn]` con `_STEP_LOG_RE` (`step_descriptor.py:47`) **después** de la corrida. La cadena entera es posicional de punta a punta: no hay nada que Python pueda direccionar para reanudar. **La limitación está bien fundada; no es una excusa.** Y está declarada donde el operador la va a leer: en F7, en este §7 y en la tabla de criterios del §9.2 (criterio (f), *"granularidad = spec"*). La granularidad real de este plan es **el spec**.
4. **No escribe su propio launcher de AgendaWeb.** Es del 240 F2 (`agenda_web_launcher.py`). Este plan lo invoca.
5. **No cambia cuándo arranca un run** (214 F3: `on_execution_end`, `qa_uat_enqueue.py`, autorun opt-in).
6. **No toca `navigation_executor.ts`** más allá de leerlo en un test de deriva.
7. **No salda la deuda del `.ps1`** (**64** archivos atrás, techo **64** — v2: el v1 decía 65). `_PS1_LAG_MAX` (`:46`) **no se toca ni para arriba ni para abajo**. Lo que este plan sí hace, obligatoriamente, es **no empeorarla**: sus 2 archivos backend van en los dos scripts.
8. **No salda las 79 keys sin `PLAIN_HELP`** (v2: el v1 decía 80; medido: 403 keys en `FLAG_REGISTRY`, 324 en `PLAIN_HELP`, 79 faltantes, 0 huérfanas) ni los otros 3 fallos de `test_harness_flags_help.py`. Sólo agrega las **9** propias.
9. **No unifica las copias de `http://localhost:35017/AgendaWeb/`.** F9 corrige **una** (`smoke_path_checker.py:66`, verificado como su único hit). **v2 — el inventario real, medido, es mucho mayor que el "~20" del v1:** `localhost:35017` aparece en **57 archivos de código** (286 contando `evidence/` y `__pycache__`), y `AGENDA_WEB_BASE_URL` en **54 de código** (217 con `evidence/`). Entre ellos: 12 `diag_*.py`, `auth_session_factory.py`, `build_dossier.py`, `deployment_fingerprint.py`, `deeplink_readiness_checker.py:19,31,115`, `rerun_guard.py`, `run_tests.py`, `session_recorder.py`, `uat_result_cache.py`, `uat_test_runner.py`, `write_test_spec.py`, `ui_map_builder.py`, `autonomous_explorer.py`, 6 `evals/auth_session/*.json`, 4 `playwright/uat/*.spec.ts`, `playwright/global.setup.ts`, los `cache/ui_maps/*.json` y el propio `templates/playwright_test.spec.ts.j2`. **Precisamente por ese tamaño, unificar está fuera de alcance** — y por eso registrar `AGENDA_WEB_BASE_URL` como flag env-first (C4) es la palanca correcta: controla a los 54 sin editar ninguno.
10. **No corrige la inconsistencia del `.env.example`.** **v2 — VERIFICADA y con la ruta real:** el archivo **no está en el tool**, está en la raíz del repo (`N:\GIT\RS\STACKY\Stacky\.secrets\agenda_web.env.example:7` = `AGENDA_WEB_BASE_URL=http://localhost/AgendaWeb/`, **sin puerto**) y su hermano vivo `agenda_web.env:1` trae `35017`. Corregir el `.example` sigue fuera de alcance, **pero la divergencia dejó de ser una curiosidad**: es la evidencia de R-16/C4 y por eso el plan **prohíbe** hornear esa key en `harness_defaults.env`.
11. **No agrega RBAC, login ni roles.** Stacky es mono-operador; `current_user` es un header sin validar.
12. **No agrega una capa LLM de clasificación.** INV-6. Si en el futuro se quisiera, sería **opcional y degradable**, y no podría cambiar el veredicto (INV-1).
13. **No toca `replan_engine`** (`MAX_REPLAN_ROUNDS = 3`, `:66`) ni `rerun_guard` (`:276`) ni `failure_triage._should_rerun` (`:656`). El presupuesto los respeta como techo (INV-7) sin reemplazarlos.
14. **No hace el smoke E2E manual contra AgendaWeb viva.** Es del operador (§10, paso 13).
15. **No commitea ni pushea.** Lo hace el operador.
16. **No unifica las 2 implementaciones de probe HTTP** (v2/C6). `environment_preflight._http_get` (`:225`, fail-fast, una vez, antes del navegador; su `run_environment_preflight` es contrato consumido por `qa_uat_pipeline.py:404`) y `agenda_health.probe_url` (en caliente, repetible) conviven **con motivo escrito**, y el caso 11 de F9 congela el conjunto en **2**. Fusionarlas es un refactor del preflight con riesgo de romper el gate de arranque del 240: es un plan propio.
17. **No implementa el sentinel de "probe siempre vivo"** (v2). F1.5 cubre el falso `SERVICE_DOWN` (probe que dice muerto cuando no lo está). El caso simétrico —un proxy o portal cautivo que devuelve 200/302 a **todo**, volviendo `SERVICE_DOWN` inalcanzable y convirtiendo caídas reales en `FUNCTIONAL_ERROR` atribuidos al desarrollador— **no se cubre acá**: la sonda obvia (pegarle a una ruta inexistente y ver si "responde") **no discrimina en WebForms**, porque una app sana redirige cualquier ruta no autenticada a `FrmLogin.aspx` con un 302, que es un alive code legítimo (`environment_preflight.py:59-61`). Detectarlo requiere una señal distinta (comparar cuerpos, o un endpoint de salud propio en AgendaWeb) y eso es alcance de producto, no de este plan. **Queda declarado como hueco conocido, no como omisión.**

---

## 8. Glosario (para un modelo menor que implemente esto)

| Término | Qué es, sin ambigüedad |
|---|---|
| **AgendaWeb** | La aplicación web ASP.NET WebForms del cliente que el QA UAT prueba. Corre local con IIS Express, por defecto en `http://localhost:35017/AgendaWeb/`. |
| **el tool** | `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\` — el pipeline QA UAT (Python + Playwright/Node). **166** `.py` en la raíz, **281** en el árbol (v2: el v1 estimaba ~180 en total). **No** es `Stacky\backend\`, que está casi vacío y **NO** es el backend. |
| **el backend** | `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\` — el Flask que dispara el tool. `api/qa_uat.py` es el puente. |
| **preflight** | `environment_preflight.run_environment_preflight` (`:119`). Corre **una vez, antes** de abrir el navegador. Fail-fast por diseño (`:53`). |
| **probe / healthcheck en caliente** | Lo que agrega este plan: `agenda_health.probe_agenda` (F1). Corre **durante** el run, ante cada excepción candidata, siempre contra la URL base. |
| **alive codes** | `frozenset({200, 301, 302, 400, 401, 403})`. Un 401 o un 302-a-login **prueban** que el servidor está vivo. Hoy hay 3 copias; después de F9, una. |
| **spec** | Un archivo `.spec.ts` de Playwright = **un caso de prueba**. Es la unidad mínima de reintento realizable en este plan. |
| **paso (step)** | Un `dict` `{"accion","target","valor"}` producido por `uat_scenario_compiler._normalize_step` (`:816`). **No** es una clase (verificado: 0 clases `Step`/`TaskStep`/`TestStep` en el tool). Su identidad es **posicional** (`loop.index` en el template Jinja, `[STEP nn]` en el log). No tiene identidad reanudable desde Python. |
| **CHILD_SCREENS** | `navigation_driver.py:114`, `frozenset[str]` de **11** miembros (`:115-125`), el primero `"FrmDetalleClie.aspx"`. Pantallas que **no** admiten `goto()` directo y requieren `form.submit()`. Un `goto()` a una de ellas produce `NAV_DEVIATION`. |
| **`samples`** | v2/F1.5. Cuántas observaciones HTTP sostienen un `HealthProbe`. **`SERVICE_DOWN` exige `samples >= 2`**; con 1 sola muestra muerta la clase es `UNRECOVERABLE`. Un muerto seguido de un vivo es un **flap** (`source="http_probe_flapped"`) y no gasta el arranque de servicio. |
| **ruta segura** | La URL a la que se vuelve tras una excepción de navegación. Configurable; por defecto, la URL base. Siempre pertenece a la allowlist. |
| **allowlist de rutas** | Conjunto de rutas relativas legales. `derived` = calculada del código (permisiva). `configured` = declarada por el operador (estricta). |
| **presupuesto de recuperación** | Contadores por run y por caso que garantizan terminación. Es un **techo**, nunca un piso (INV-7). |
| **flag** | Clave de `FLAG_REGISTRY` (`backend/services/harness_flags.py`). **No es sólo booleana**: `type` ∈ `{bool, csv, int, float, str, json}` — **v2/C5: el comentario de `:23` omite `"str"`, pero `type="str"` se usa 10 veces en el registry y el panel lo renderiza (`HarnessFlagsPanel.tsx:157`)**. La key **no** necesita prefijo `STACKY_` (hay 25+ sin él). |
| **default efectivo** | Para una flag de valor sin `default=` en su `FlagSpec`, el default real vive en `config.py`. Patrón verificado (`harness_flags.py:5142`). Para `AGENDA_WEB_BASE_URL` el default **tiene que ser env-first** (`os.getenv`), o el export pisa al operador (C4). |
| **criterio delta** | Criterio que compara **contra el baseline medido** en un archivo rojo de fábrica, en vez de exigir "verde". **Sólo se usa cuando el archivo está realmente rojo**: aplicarlo a un archivo verde produce un criterio insatisfacible (el error C1 del v1). |
| **rojo de fábrica** | Test que ya falla antes de tocar nada, por deuda ajena. **v2: este plan tiene UNO, no dos** — `test_harness_flags_help.py` (`4 failed, 4 passed`). `test_plan259_ratchet_script_parity.py` está **VERDE** (`12 passed`) con lag 64 de 64. |
| **ratchet** | Lista que sólo crece. `HARNESS_TEST_FILES` en `run_harness_tests.sh` (`:20`, rutas **peladas**) y su gemelo `.ps1` (rutas **entrecomilladas y con coma**, sintaxis distinta). Los dos regex son `_SH_RE` (`test_plan259_ratchet_script_parity.py:28`) y `_PS1_RE` (`:30`). Sin comillas, el `.ps1` parsea con 0 errores y **la ruta se pierde MUDA**. |
| **veredicto** | `PASS` / `FAIL` / `BLOCKED` / `MIXED` (`playwright_result_classifier.py:57`); `failure_triage` agrega `SKIPPED` (`:58`). La recuperación **nunca** lo ablanda (INV-1). |
| **falso verde** | Un `PASS` que no certifica el criterio funcional. Es lo que el plan 241 existe para prevenir. |

---

## 9. Orden de implementación y DoD global

### 9.1 Orden numerado (por dependencia dura)

| # | Fase | Depende de | Por qué en ese lugar | Tests nuevos |
|---|---|---|---|---|
| 1 | **F0** Costura + baseline + las 2 mentiras del doc | — | Sin baseline medido no hay criterio delta honesto | **3** (tool) |
| 2 | **F1 + F1.5** `agenda_health` + probe confirmado | F0 | Es la pieza base de F3, F7, F8, F9, F10 | **13** (tool) |
| 3 | **F2** Config por UI + fix del exportador + anti-clobber | F0 | F1 la usa opcionalmente; F5 la usa obligatoriamente | **15** (tool) + **14** (backend) |
| 4 | **F3** `recovery_classifier` | F1, F2 | Necesita el probe y la config | **25** (tool) |
| 5 | **F4** `route_allowlist` | F2 | Necesita las claves de allowlist y ruta segura | 20 (tool) |
| 6 | **F5** `recovery_budget` | F2, F3 | Necesita los máximos y `is_recoverable` | 16 (tool) |
| 7 | **F6** Unificación de reintentos de navegación | F0, **F2** | v2/C9: ahora depende de F2 porque registra `QA_NAV_RETRIES` | **9** (tool) |
| 8 | **F7.1** `hot_recovery` (el orquestador) | F1..F5 | Une todas las piezas | 18 (tool) |
| 9 | **F7.2** El CALL SITE en `uat_test_runner.run` | **F7.1** | **v2/C3: sin esto todo lo anterior es código muerto.** Va inmediatamente después de F7.1 y **antes** de F10, que consume su `recovery_report` | **9** (tool) |
| 10 | **F8** Fin del `PIPELINE_CRASH` catch-all | F1, F3 | Toca `qa_uat_pipeline.py`: va después de que las piezas existan | 12 (tool) |
| 11 | **F9** Una sola definición de "app viva" | F1 | Refactor: **después** de que `agenda_health` esté probado | **11** (tool) |
| 12 | **F10** Reporte + logs + doctor | **F7.2** | v2: necesita el `recovery_report` que escribe el call site, no sólo el `RecoveryOutcome` | 12 (tool) + **7** (backend) |
| 13 | **F11** Invariante anti-ablandamiento | F3, F5, F7.1, F7.2 | Es el gate final: se corre sobre el sistema completo | **15** (tool) |

**Total verificable sumando la columna: 199 casos** — **178 en el tool (13 archivos)** + **21 en el backend (2 archivos)**.
Desglose del tool, en el orden de la tabla: `3 + 13 + 15 + 25 + 20 + 16 + 9 + 18 + 9 + 12 + 11 + 12 + 15 = 178`. Backend: `14 + 7 = 21`.

> **v2 / C7 — por qué se recalculó todo.** El v1 declaraba *"205 casos — 189 en el tool (13 archivos) + 16 en el backend"*, y su propio D-1 listaba `2, 11, 12, 22, 20, 16, 8, 18, 12, 10, 12, 14`, que suma **157** en **12** archivos, con 16 en el backend = **173**. Tres números distintos para la misma cosa, en la misma página, en un criterio declarado binario. Un DoD que no cierra aritméticamente no se puede satisfacer: el implementador no sabe cuándo terminó. **Regla del v2: el total es la suma de la columna, y se verifica sumando.**

**Paralelización segura:** F6 ya **no** es independiente (v2/C9: depende de F2). **F2, F8, F9, F10 y F7.2 NO se paralelizan entre sí ni con nada**: F2 toca 8 puntos compartidos del arnés (donde se pierden escrituras en silencio), F8 toca `qa_uat_pipeline.py` y F9 toca `environment_preflight.py` (archivos que todo el tool importa), **F7.2 y F6 tocan los DOS el mismo bloque de `uat_test_runner.run`** (F6 en `:133-140` y `:343`, F7.2 entre `:172` y `:236`) y F10 toca `api/qa_uat.py`, que F2 también toca. **Techo real de paralelismo de este plan: 2**, y con este orden: **F2 primero y sola**, después una rama `F1→F3→F4→F5→F7.1→F7.2→F10→F11` y otra `F6→F8→F9`.

### 9.2 DoD global — criterios DELTA

**Absolutos (archivos verdes hoy; se exige verde):**

| # | Criterio | Comando | Esperado |
|---|---|---|---|
| D-1 | Los **13** archivos de test del tool pasan, **corridos de a uno** | `& $PY -m pytest "$TOOL\tests\unit\test_plan262_<n>.py" -q` × 13 | `3, 13, 15, 25, 20, 16, 9, 18, 9, 12, 11, 12, 15` → **178 passed** en total (la lista **suma** 178: verificalo antes de aceptar el criterio) |
| D-2 | Los 2 archivos de test del backend pasan | `& $PY -m pytest tests\test_plan262_recovery_flags.py -q` y `... test_plan262_runtime_doctor_recovery.py -q` | `14 passed` + `7 passed` = **21** |
| D-3 | `test_harness_flags.py` sin regresión | `& $PY -m pytest tests\test_harness_flags.py -q` | **56 passed** (medido en la crítica v2) |
| D-4 | `test_harness_flags_bounds.py` sin regresión y con las **5** numéricas en `_FROZEN_BOUNDS` | `& $PY -m pytest tests\test_harness_flags_bounds.py -q` | **18 passed** (medido en la crítica v2) |
| D-5 | `test_harness_ratchet_meta.py` sin regresión | `& $PY -m pytest tests\test_harness_ratchet_meta.py -q` | **4 passed** (medido en la crítica v2) |
| **D-6** | **v2/C1 — paridad `.sh`/`.ps1` VERDE** (era "delta" en el v1) | `& $PY -m pytest tests\test_plan259_ratchet_script_parity.py -q` | **12 passed** (medido en la crítica v2; lag 64 de 64). Registrar sólo en el `.sh` da `1 failed` con *"66 archivos solo en el .sh (maximo 64)"* |
| D-7 | Regresión del 240 en el launcher | `& $PY -m pytest "$TOOL\tests\unit\test_plan240_agenda_launcher.py" -q` | **9 passed** (baseline del v1; el implementador lo re-mide en F0 y usa SU número) |
| D-8 | Regresión del 241 (3 archivos, de a uno) | `test_plan241_discrimination.py`, `test_plan241_golden_suite.py`, `test_plan241_diagnostics.py` | conteo **idéntico** al baseline que mida el implementador en F0 |
| D-9 | Regresión de navegación (2 archivos, de a uno) | `test_navigation_driver.py`, `test_navigation_strategy_resolver.py` | conteo **idéntico** al baseline |
| **D-10** | **v2 — regresión del runner**, porque F6 y F7.2 lo tocan los dos | `test_sprint5_playwright_runner.py`, `test_p0_observability.py` (de a uno) | conteo **idéntico** al baseline |
| D-11 | El tool compila | `& $PY -m compileall -q "$TOOL"` | exit 0 |
| D-12 | El backend compila | `& $PY -m compileall -q "$BE"` | exit 0 |

**DELTA (el ÚNICO archivo rojo de fábrica; se exige que la deuda no crezca y que lo propio no esté):**

| # | Criterio | Comando | Baseline medido en la crítica v2 | Esperado después |
|---|---|---|---|---|
| D-13 | Ninguna de las **9** keys nuevas aparece sin ayuda llana | `& $PY -m pytest tests\test_harness_flags_help.py -q 2>&1 \| Select-String "STACKY_QA_UAT_HOT_RECOVERY\|STACKY_QA_UAT_RECOVERY_MAX\|STACKY_QA_UAT_HEALTH_PROBE\|STACKY_QA_UAT_ROUTE_ALLOWLIST\|STACKY_QA_UAT_SAFE_ROUTE\|AGENDA_WEB_BASE_URL\|QA_NAV_RETRIES"` | `4 failed, 4 passed`; **79 keys** en `missing` (403 en `FLAG_REGISTRY`, 324 en `PLAIN_HELP`) | **0 líneas** en el `Select-String`; el archivo sigue en `4 failed, 4 passed` con **79** keys ajenas |

> **v2 — el `Select-String` es el criterio, no el pass/fail.** El assert de `test_plain_help_covers_all_registry_keys` es `assert missing == []`: colapsa 79 faltantes a 1 fallo, así que el archivo está rojo **igual** con o sin ayuda para mis 9 keys. La única forma de discriminar es grepear **el contenido del mensaje** buscando mis keys. **0 líneas = mis 9 tienen ayuda.** Y ojo con la denylist de jerga (F2.3 punto 4): `runtime`, `endpoint`, `gate` y `token` (y sus plurales) están prohibidos en los 4 campos.

**Criterios funcionales del operador — cada uno mapeado a fase y test (los 12, sin excepción):**

| # | Criterio del operador | Fase | Test que lo prueba |
|---|---|---|---|
| (a) | Diferenciar caída real de ruta inválida | F3 | `test_app_caida_da_service_down` + `test_ruta_no_permitida_con_app_viva_da_route_error` + **`test_nav_wrong_screen_da_route_error`** (v2/C2) |
| (b) | Una excepción de navegación NO marca la app como no disponible | F8 | `test_crash_con_app_viva_y_ruta_mala_da_nav_route_invalid` |
| (c) | Validar el estado real por mecanismo independiente | F1 + F1.5 + F7 | `test_paso3_prueba_la_base_no_la_ruta_rota` (INV-5) + **`test_dos_probes_muertos_dan_service_down_confirmado`** + **`test_health_sin_confirmar_no_da_service_down`** |
| (d) | Reabrir desde ruta segura y reintentar | F7.1 + **F7.2** | `test_app_viva_ruta_mala_vuelve_a_ruta_segura` + **`test_recover_se_llama_para_un_caso_fail`** (v2/C3: sin el call site, (d) no ocurría nunca) |
| (e) | Corregir/recalcular ruta sin intervención manual | F7.1 + **F7.2** | `test_ruta_corregida_es_match_exacto_o_ruta_segura` + **`test_reintento_exitoso_reemplaza_el_caso_en_runs`** |
| (f) | Reintento acotado al paso/caso afectado | F7.1 + **F7.2** | `test_app_viva_ruta_mala_reintenta_solo_el_caso` + **`test_recover_se_llama_una_vez_por_caso_recuperable`**. **Granularidad = spec**, y el límite está declarado en F7, §7.3 y acá: el reintento por PASO de aserción es inalcanzable (paso posicional de punta a punta, 0 `test.step(`, 0 clases `Step`) |
| (g) | Reintentos, esperas, URL base y rutas permitidas configurables | F2 (+F1.5, +C9) | los 15 de `test_plan262_recovery_config.py` + los 14 de `test_plan262_recovery_flags.py`. **Cobertura por palabra:** *reintentos* → `RECOVERY_MAX_PER_RUN`/`_PER_CASE` **y `QA_NAV_RETRIES`** (v2/C9); *esperas* → `HEALTH_PROBE_TIMEOUT_S` **y `HEALTH_PROBE_CONFIRM_S`** (v2/F1.5); *URL base* → `AGENDA_WEB_BASE_URL` (env-first, C4); *rutas permitidas* → `ROUTE_ALLOWLIST` + `SAFE_ROUTE`. **Y por UI de verdad**: el panel renderiza los 6 tipos (C8) |
| (h) | Evitar ciclos infinitos de recuperación | F5 + **F7.2** | `test_presupuesto_no_se_reinicia_entre_casos` + `test_segundo_service_down_no_arranca_de_nuevo` + **`test_el_presupuesto_se_construye_una_sola_vez`** (v2: construirlo dentro del `for` anula el presupuesto) |
| (i) | Cada excepción clasificada en las 5 clases | F3 | `test_las_5_clases_y_nada_mas` + los 11 casos de clasificación + **`test_los_11_nav_codes_del_driver_estan_mapeados`** (bidireccional, v2/C2) |
| (j) | Todas las recuperaciones/correcciones/reinicios/reintentos en los logs | F10 | `test_los_6_eventos_se_emiten_en_orden` |
| (k) | Reporte de no-recuperable con ruta, excepción, intentos y motivo | F10 + **F7.2** | `test_los_4_campos_del_operador_estan_presentes` + `test_ningun_campo_obligatorio_es_none` + **`test_recovery_report_presente_incluso_sin_intento`** (v2/C12: el call site es el único dueño del dict del caso) |
| (extra) | Levantar el servicio **solo** si está realmente caído | F7.1 + F1.5 | `test_app_viva_ruta_legal_funcional_no_reintenta` + `test_app_caida_arranca_el_servicio` + **`test_un_solo_probe_muerto_no_da_service_down_confirmado`** |

**Los 8 invariantes, cada uno con su gate:** INV-1 → F11 (15 casos) · INV-2 → F5 `test_functional_error_nunca_consume` + F11 caso 1 · INV-3 → F11 caso 5 · INV-4 → F9 caso 1 (**definición** de alive codes) **y F9 caso 11** (las **2** implementaciones de probe declaradas, v2/C6) · INV-5 → F7 caso 2 · INV-6 → F3 `test_clasificador_no_importa_ningun_modulo_de_llm` · INV-7 → F5 `test_service_starts_es_uno_con_flag_on` + `test_per_case_se_clampea_al_per_run` + F1.5 (`samples >= 2` reduce el techo, nunca lo sube) · INV-8 → F8 `test_flag_off_es_byte_identico` + F11 caso 14 + **F7.2 caso 8** (`test_flag_off_no_llama_a_recover_y_runs_queda_intacto`).

### 9.3 Trabajo del operador (consolidado — el ÚNICO trabajo humano de este plan)

> **v2 — la tarea nº1 del v1 se ELIMINA.** Era *"abrir el panel de flags y verificar que los controles numéricos/csv rendericen"*. Se verificó leyendo `HarnessFlagsPanel.tsx` (C8): renderiza los 6 tipos con `min`/`max` y hint de rango. **Pedirle al operador que confirme algo que se confirma leyendo un archivo es exactamente el trabajo extra que este plan no tiene permiso de generar.**

1. **Smoke E2E manual** contra AgendaWeb viva, **5** escenarios: (a) app arriba + ruta inválida inyectada → esperar `NAV/ROUTE_INVALID`, `recovery_report` con `app_alive: true`, y que **el resto de los casos siga corriendo**; (b) app abajo de verdad → esperar `ENV/APP_NOT_RUNNING`, `samples: 2`, y **un** solo intento de arranque; (c) sesión expirada forzada → esperar `SESSION_ERROR` + reautenticación; (d) aserción que falla de verdad → esperar `FAIL` **sin ningún reintento** y `recovery_report` diciendo *"app viva, ruta legal, no se reintenta"*; (e) **v2/F1.5** — reciclar el AppPool de IIS a mitad de un run (`appcmd recycle apppool`) → esperar `source: "http_probe_flapped"` en el log, reintento del caso, y **cero** arranques de servicio.
2. **Verificar la URL base en el panel** (v2/C4): abrir la categoría *Calidad y verificación del entregable* y confirmar que `AGENDA_WEB_BASE_URL` muestra **su** URL real, no `http://localhost:35017/AgendaWeb/`, si su AgendaWeb está en otro puerto. Si muestra el default cuando no debería, la declaración env-first de `config.py` está mal y hay que frenar antes de correr un run.
3. **Decidir** si quiere la allowlist en modo `derived` (permisivo, default) o declarar la lista estricta de su instalación.
4. Commitear y pushear. **El plan no commitea.**

---

## 10. Estado de verificación tras la crítica v2

**Ya no queda ningún `[NO VERIFICADO]` en este documento.** Los 7 del v1 se resolvieron abriendo los archivos y corriendo los tests (ver §0). Resumen de lo que se **midió**, no se estimó:

| Qué | Resultado real | ¿Coincidía con el v1? |
|---|---|---|
| `test_harness_flags.py` | **56 passed** | sí |
| `test_harness_flags_bounds.py` | **18 passed** | sí |
| `test_harness_ratchet_meta.py` | **4 passed** | sí |
| `test_harness_flags_help.py` | **4 failed, 4 passed**, **79** keys sin ayuda | el pass/fail sí, el número **no** (decía 80) |
| `test_plan259_ratchet_script_parity.py` | **12 passed**, lag **64** de 64 | **NO** (decía `1 failed, 11 passed` y lag 65) |
| Panel de flags: tipos renderizados | `bool/int/float/csv/str/json` | era `[NO VERIFICADO]`; **resuelto a favor** |
| `type="str"` en `FlagSpec` | **existe, 10 usos** | **NO** (el v1 lo declaraba inexistente) |
| Códigos de `navigation_driver` | **11** distintos; `_classify_error` devuelve **8** | **NO** (decía 10) |
| `_run_single_spec` | **1 hit, 0 referencias externas** | sí |
| `_last_route_used` / `classify_pipeline_crash` | **0 hits: hay que crearlos** | implícito, ahora explícito |
| `# noqa: BLE001` en `uat_test_runner.py` | **16** | **NO** (decía ~40) |
| `.py` del tool | **166** raíz / **281** árbol | **NO** (decía ~180 total) |
| Archivos que leen `AGENDA_WEB_BASE_URL` | **54** de código / 217 con `evidence/` | **NO** (decía ~20) |
| `localhost:35017` literal | **57** archivos de código | **NO** (decía ~20) |
| `harness_defaults.env` | **los DOS son generados** por `export_harness_defaults.py` | era `[NO VERIFICADO]`; resuelto |
| `.secrets\agenda_web.env.example` | en la **raíz del repo**, sin puerto; el `.env` vivo con `35017` | era `[NO VERIFICADO]`; resuelto y **ahora es evidencia de C4** |
| `harness_flags.py:519/533/567/582/2091` | **las 5 OK** | era `[NO VERIFICADO]`; confirmado |
| Prefijo `STACKY_` obligatorio en el registry | **NO lo es** (25+ keys sin él, 0 tests que lo exijan) | duda abierta; resuelta |
| `FlagSpec` anclajes: `type:23`, `min_value:33`, `max_value:34`, `value_in_bounds:5883`, `validate_bounds_registry:5908`, `_CATEGORY_KEYS:120`, `calidad_verificacion:154`, `:171-178`, `:514`, `:5142` | **todos OK** | sí |
| `default_is_known` | **`:5814`** | **NO** (decía `:5816`) |

**Anclajes DESFASADOS corregidos en el cuerpo del documento (8):** `qa_uat_pipeline.py` traceback `:704→:706` y `all_scenarios_blocked` `:3090→:3170`; `environment_preflight.py` rstrip `:76→:77` y uso del preflight `:247→:279`; `agenda_web_launcher.py` `started_by_us` del stop `:179→:187`; `uat_test_runner.py` `"meta"` `:292-293→:293-294`; `harness_flags.py` `default_is_known` `:5816→:5814`; `harness_flags_help.py` `PlainHelp` `:19→:18`; `test_harness_ratchet_meta.py` `_SCRIPT` `:14→:13` y `_TESTS_DIR` `:16→:15`.

**Anclajes INEXISTENTES (símbolos a crear, no errores del plan):** `agenda_health.py`, `recovery_config.py`, `recovery_classifier.py`, `route_allowlist.py`, `recovery_budget.py`, `hot_recovery.py`, `_last_route_used`, `classify_pipeline_crash`, `run_single_spec` (alias público), `build_budget_for_run`, `route_of_case`, `nav_code_of_case`.

> **Regla para el implementador.** Antes de tocar una línea, **re-medí los 6 baselines de F0.1 y anotá TUS números.** Los de este documento se midieron el 2026-07-29 con una sesión paralela viva en el mismo árbol; el propio v1 se equivocó en dos de ellos por heredarlos en vez de correrlos. Y **anclá por SÍMBOLO, no por número de línea**: de los 8 desfasados de arriba, uno estaba 80 líneas corrido.
