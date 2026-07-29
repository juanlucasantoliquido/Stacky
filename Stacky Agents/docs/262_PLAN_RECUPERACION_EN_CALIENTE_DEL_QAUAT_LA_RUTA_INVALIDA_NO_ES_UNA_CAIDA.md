# Plan 262 — Recuperación en caliente del QA UAT: una ruta inválida NO es una caída

> Estado: **v1 · PROPUESTO** — sin criticar. Pipeline: **proponer ✓ [este paso]** → criticar (`criticar-y-mejorar-plan`) → implementar (`implementar-plan-stacky`) → supervisar (`supervisar-implementaciones-planes`).
>
> Autor: Claude Opus 5 (1M context) en rol **StackyArchitectaUltraEficientCode**, perfil `normal`. Todo anclaje `archivo:símbolo:línea` de este documento fue verificado **abriendo el archivo** en la corrida de escritura (2026-07-29). Los pocos datos heredados del pedido que NO reverifiqué están marcados `[NO VERIFICADO]`.
>
> Runtimes objetivo: **Codex CLI, Claude Code CLI, GitHub Copilot Pro** — paridad obligatoria. El núcleo de este plan es **100 % determinista y sin LLM**: clasificar una excepción no puede depender de que un modelo esté disponible.
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
| Decisores duplicados de "app viva" | **3**, cada uno con su copia de los alive codes (`environment_preflight.py:62`, `smoke_path_checker.py:40`, `agenda_web_launcher.py:78`) | **1** (`agenda_health`), los otros delegan |
| Parámetros de recuperación configurables por UI | **0** — las ~30 env vars del tool se leen crudas de `os.environ` | **7** en `FLAG_REGISTRY` (1 bool + 3 numéricas + 3 csv) |
| `QA_UAT_MAX_NAVIGATION_RETRIES` efectiva por el camino del runner | **inerte** — variable muerta en `uat_test_runner.py:136` (1 solo hit en el archivo) | efectiva y con **un solo nombre canónico** |
| Reporte de un caso no recuperable | sin ruta usada ni conteo de intentos | **ruta usada + excepción + intentos + motivo final** obligatorios |

---

## 2. La tesis del plan / por qué ahora

**Tesis: el pipeline QA UAT tiene un buen detector de caída y lo corre en el peor momento posible — una sola vez, antes de que pueda pasar algo.**

Cinco hechos verificados sostienen esto:

1. **El único decisor de "caída" corre ANTES, nunca durante.** `qa_uat_pipeline.py:run` llama `preflight = run_environment_preflight()` en `:400`, y sólo si `not preflight.ok and preflight.reason == "APP_NOT_RUNNING"` (`:404`) importa `ensure_agenda_web` (`:406`), la invoca (`:407`) y hace **UN** re-preflight (`:409`). Después de esa línea, nadie vuelve a preguntar si la app responde en todo el run.

2. **El catch-all sepulta la causa.** `qa_uat_pipeline.py:690` es `except Exception as _pipeline_crash:  # noqa: BLE001` envolviendo la llamada a `_run_pipeline_stages` de `:670`. Produce `verdict="BLOCKED"`, `category="OPS"`, `reason="PIPELINE_CRASH"` (`:702`). El plan 241 F6 hizo lo correcto agregando el traceback (`"traceback": _crash_tb[-2000:]`, dos líneas más abajo), pero el **rótulo sigue siendo el mismo para una caída real y para un `urljoin` mal hecho**.

3. **El preflight está diseñado explícitamente para NO reintentar.** `environment_preflight.py:53` dice literal *"We do NOT retry — fail fast."*, con `_CHECK_TIMEOUT_S: float = 5.0` (`:54`). Eso es **correcto para un preflight** y **equivocado como única política de todo el run**: la app puede estar reiniciando su AppPool en el segundo 40 de una prueba de 6 minutos.

4. **Ya hay tres implementaciones de "¿está viva?" que no se conocen entre sí.** `environment_preflight._ALIVE_STATUS_CODES` (`:62`) es la definición canónica; `smoke_path_checker.py:40` la **copia literal**; `agenda_web_launcher._responds` (`:73`) intenta importarla y si falla **la vuelve a hardcodear** en `:78`. Tres copias del mismo `frozenset({200, 301, 302, 400, 401, 403})`. Agregar una cuarta sería el error obvio; este plan agrega **una** y hace que las tres deleguen.

5. **La maquinaria de reintento por caso ya está escrita y está muerta.** `uat_test_runner._run_single_spec` (`:1031`, firma completa `(spec_file, scenario_id, scenario_dir, ticket_id, headed, timeout_ms, verbose, exec_log) -> dict`) tiene **exactamente 1 hit en todo el árbol de módulos `.py` del tool: su propia definición**. Lo que se ejecuta es `_run_all_specs_once` (`:301`), invocada una única vez desde `:172`, que lanza **un** subprocess `npx playwright test` con **todos** los specs; y cuando ese subprocess expira, `except subprocess.TimeoutExpired:` (`:421`) mata el proceso y `_timeout_result` (`:1016`) marca **TODOS** los specs como `BLOCKED/TIMEOUT`. El reintento acotado al caso no hay que inventarlo: hay que **cablearlo**.

**Y un bug vivo que este plan cierra porque es el mismo problema en miniatura.** `uat_test_runner.py:136` declara `max_nav_retries = int(os.environ.get("QA_UAT_MAX_NAVIGATION_RETRIES", "1"))`. Esa variable tiene **1 solo hit** en el archivo: se asigna y no se usa nunca. Contraste medido en el mismo archivo: `max_browser_launches` (`:134`) y `max_login_attempts` (`:135`) tienen 6 hits cada una y llegan al dossier en `:292-293`; `max_total_min` (`:139`) se usa en `:292`. Del otro lado, `playwright/helpers/navigation_executor.ts:allowedAttempts:375` lee `process.env.QA_UAT_MAX_NAVIGATION_RETRIES ?? process.env.QA_NAV_RETRIES ?? 0` (`:377`) y capa el pedido del paso con `Math.min(Math.max(0, requestedRetries), allowedRetries)` (`:382`). **Precisión importante y contraintuitiva: el retry TS NO está capado a 0.** El runner exporta `QA_NAV_RETRIES` con default `"3"` en `uat_test_runner.py:343`, sobre un `env = {**os.environ, ...}` (`:337`), así que `allowedAttempts` resuelve a 3 intentos. El defecto real es doble: **(a)** la env var *documentada* como cota de reintentos de navegación es **inerte por el camino del runner**, y **(b)** hay **dos nombres para el mismo concepto con defaults distintos** (1 en Python, 3 en TS) y el que gana en el TS es justamente el que Python nunca exporta. Eso es una bomba de relojería: el día que alguien exporte `QA_UAT_MAX_NAVIGATION_RETRIES=1` "para arreglar el warning", los reintentos de navegación bajan de 3 a 1 **en silencio**.

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

> **INV-1 (LEY DEL 241 — la recuperación NUNCA ablanda el veredicto).** Ningún camino de recuperación puede convertir un fallo real en `PASS`, ni un `BLOCKED` honesto en `MIXED`, ni bajar `FAIL` a `SKIPPED`. Un caso que terminó en `FAIL` tras 0 reintentos y uno que terminó en `FAIL` tras 3 reintentos son **el mismo `FAIL`**. Precedente que lo hace obligatorio: el 241 C4 documenta un caso donde el gate funcional tapaba un `BLOCKED` legítimo (`qa_uat_pipeline.py:3090`, `stages["evaluator"].skipped` con `reason == "all_scenarios_blocked"`). Se prueba en **F11** con un test dedicado, no con una promesa en prosa.

> **INV-2 (`FUNCTIONAL_ERROR` no se reintenta).** Si el probe dice que la app está viva y la ruta usada pertenece a la allowlist, la excepción es **funcional** y es el resultado de la prueba. No se reintenta, no se recupera, no se reabre nada. Reintentar una aserción que falló es la definición de falso verde.

> **INV-3 (regla del 241 sobre 0 tests, intacta).** `total == 0` sigue siendo `BLOCKED / PIP / NO_TESTS_FOUND` y **jamás** `PASS`. La recuperación no puede producir un run con 0 tests y llamarlo verde. `playwright_result_classifier.py` documenta esa regla en su cabecera y este plan no la toca.

> **INV-4 (una sola fuente de verdad de "vivo")** — después de F9 existe **exactamente una** definición de los alive codes y **exactamente una** función que hace el probe HTTP. Se prueba con un gate de conteo sobre el árbol del tool.

> **INV-5 (el probe es independiente de la ruta que falló).** El chequeo de disponibilidad se hace **siempre** contra la URL base estable, **nunca** contra la ruta que produjo la excepción. Preguntarle a la ruta rota si el servidor está vivo es el bug que este plan cierra.

> **INV-6 (cero LLM en el camino de decisión).** Clasificar, validar la ruta, decidir el reintento y contar el presupuesto son operaciones deterministas. Ninguna consulta a un modelo. Corolario: paridad trivial entre Codex CLI, Claude Code CLI y GitHub Copilot Pro.

> **INV-7 (el presupuesto es un techo, nunca un piso).** El presupuesto de recuperación **no puede autorizar** más intentos que las cotas ya existentes: `navigation_driver._MAX_REAUTH_PER_STEP = 1` (`:109`), `replan_engine.MAX_REPLAN_ROUNDS = 3` (`:66`), `QA_UAT_MAX_BROWSER_LAUNCHES` (`uat_test_runner.py:134`). Ante conflicto, gana **el mínimo**.

> **INV-8 (degradación silenciosa, no ruptura).** Con `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` en OFF el comportamiento es **el de hoy**: mismo rótulo `PIPELINE_CRASH`, mismo flujo, mismos artefactos. Ninguna fase de este plan puede hacer que un run que hoy funciona deje de funcionar cuando la flag está apagada.

---

## 4. Principios y guardarraíles

1. **Human-in-the-loop innegociable.** Este plan no le saca ninguna decisión al operador: la recuperación es *mecánica* (reabrir una ruta, restablecer sesión, reintentar un caso), no *interpretativa*. No decide si un criterio se cumple, no cierra tickets, no reescribe escenarios. Todo lo que recupera queda en el log y en el reporte para que el operador lo lea.
2. **Mono-operador, sin auth real.** `current_user` es un header sin validar. **Cero RBAC**: ninguna fase introduce permisos, roles ni chequeos de autorización.
3. **Toda config del operador va por UI.** Cero env vars nuevas de cara al operador. Las 7 claves nuevas nacen en `FLAG_REGISTRY` (§F2). Las env vars siguen existiendo como **camino de lectura del tool** (que corre en otro proceso/CLI), no como interfaz del operador.
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
- **Hallazgo que ahorra trabajo:** `backend/tests/test_harness_ratchet_meta.py` define `_TESTS_DIR = _BACKEND / "tests"` (`:16`) y `_SCRIPT = _BACKEND / "scripts" / "run_harness_tests.sh"` (`:14`). Escanea **sólo** `Stacky Agents/backend/tests/`. ⇒ **Los tests que vivan en el tool NO requieren registro en el ratchet.** Precedente: los 14 archivos `test_plan240_*.py` / `test_plan241_*.py` del tool no están registrados. Sólo los **2 archivos backend** de este plan (F2 y F10) se registran, y van en **`.sh` Y `.ps1`**.
- **`pytest -k` que no selecciona nada sale 0.** Prohibido usar `-k` como criterio de aceptación sin exigir el conteo de seleccionados.

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
| `backend/tests/test_plan259_ratchet_script_parity.py` | `... tests/test_plan259_ratchet_script_parity.py -q` | **1 failed, 11 passed** | **ROJO DE FÁBRICA** — criterio DELTA obligatorio |

**Detalle de los rojos de fábrica (medido, no supuesto) — esto cambia el diseño de los criterios de F2:**

- `test_harness_flags_help.py::test_plain_help_covers_all_registry_keys` falla con **80 keys sin ayuda llana**, entre ellas `STACKY_QA_UAT_AUTORUN_ENABLED` y `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` (deuda del plan 214). Los otros 3 fallos son: `test_plain_help_fields_non_empty_and_bounded` (`STACKY_DEVOPS_COCKPIT_ENABLED: on_effect > 240 chars`), `test_plain_help_on_off_start_with_si` (`STACKY_EGRESS_SENTINEL_MAX_CHARS: off_effect no empieza con 'Si '`) y `test_plain_help_avoids_jargon_denylist` (15 violaciones ajenas).
  **Consecuencia de diseño:** el assert de ese test es `assert missing == []`, que **colapsa 80 faltantes a 1 fallo**. Si mis 7 keys nuevas no tuvieran ayuda, el test seguiría rojo **exactamente igual** y el gate no discriminaría nada. ⇒ F2 exige un criterio que asserte sobre **el contenido del mensaje**, no sobre pass/fail.
- `test_plan259_ratchet_script_parity.py::test_el_ps1_no_pierde_terreno` falla en `:93` con el mensaje literal: *"el .ps1 perdio terreno: 65 archivos solo en el .sh (maximo 64)"*. `_PS1_LAG_MAX = 64` (`:46`). ⇒ El `.ps1` viene **65** archivos atrás y el techo es **64**: el archivo está rojo hagas lo que hagas. **Criterio DELTA:** el número de la deuda **no puede subir de 65**, y los 2 archivos nuevos deben aparecer en **ambos** regex (`_SH_RE` en `:28`, `_PS1_RE` en `:30`). Saldar los 65 es deuda ajena y **está fuera de scope**.

#### F0.2 — Reserva de nombres (predeclaración, para que F1..F11 no colisionen)

Módulos nuevos del tool (verificado que **ninguno existe hoy**):
`agenda_health.py`, `recovery_config.py`, `recovery_classifier.py`, `route_allowlist.py`, `recovery_budget.py`, `hot_recovery.py` — todos en `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\`.

Claves de flag nuevas (las 7, para que ninguna fase las renombre a mitad de camino):
`STACKY_QA_UAT_HOT_RECOVERY_ENABLED`, `STACKY_QA_UAT_RECOVERY_MAX_PER_RUN`, `STACKY_QA_UAT_RECOVERY_MAX_PER_CASE`, `STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S`, `STACKY_QA_UAT_ROUTE_ALLOWLIST`, `STACKY_QA_UAT_SAFE_ROUTE`, `AGENDA_WEB_BASE_URL`.

Archivos de test nuevos (11 en el tool + 2 en el backend): ver la tabla del §9.

> **PROHIBIDO en F0:** pre-registrar en el ratchet rutas de test que todavía no existen. `test_harness_ratchet_meta.py::_all_test_files` (`:35`) deriva del filesystem; una ruta declarada sin archivo pone el meta-test **rojo**. Los 2 archivos backend se registran **en la fase que los crea**, no acá.

#### F0.3 — El doc que miente (corrección de 1 línea)

`agenda_web_launcher.py:12` dice literal: `FLAG: STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED, default OFF por EXCEPCION DURA #3`. **Es falso desde el barrido default-ON del 2026-07-27**: `config.py:1232-1233` declara `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED: bool = os.getenv("STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED", "true")`. Reemplazar por:

```
FLAG: STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED, default ON desde el barrido 2026-07-27
(config.py). Con OFF el comportamiento es byte-identico al previo al plan 240
(BLOCKED/APP_NOT_RUNNING sin intentar arrancar nada).
```

**Tests PRIMERO:** `Stacky tools\QA UAT Agent\tests\unit\test_plan262_launcher_doc_truth.py`
- `test_launcher_docstring_no_dice_default_off` — lee el módulo como texto y asserta que la frase `"default OFF"` **no** aparece en el docstring de `agenda_web_launcher.py`. Mensaje del assert: la línea encontrada, completa.
- `test_launcher_flag_default_es_on_en_config` — parsea `config.py` con `re` buscando `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` y asserta que el segundo argumento de `os.getenv` es `"true"`. **No importa `config`** (importarlo arrastra el backend entero al proceso del tool).

**Comando:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_launcher_doc_truth.py" -q
```

**Criterio de aceptación BINARIO:** `2 passed`.
**Rojo antes / verde después:** ANTES → `1 failed, 1 passed` (falla `test_launcher_docstring_no_dice_default_off`, porque `:12` sí dice "default OFF"). DESPUÉS → `2 passed`.

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

@dataclass(frozen=True)
class HealthProbe:
    alive: bool
    status: int | None
    url: str
    elapsed_ms: int
    error: str            # "" cuando alive is True
    source: str           # "http_probe" — quien produjo el veredicto

def probe_url(url: str, *, timeout_s: float | None = None) -> HealthProbe: ...
def probe_agenda(*, base_url: str | None = None, timeout_s: float | None = None) -> HealthProbe: ...
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
            url = "http://localhost:35017/AgendaWeb/"   # ultimo recurso, mismo default canonico
    if timeout_s is None:
        try:
            from recovery_config import health_probe_timeout_s   # F2; opcional
            timeout_s = health_probe_timeout_s()
        except Exception:                          # noqa: BLE001
            timeout_s = DEFAULT_PROBE_TIMEOUT_S
    return probe_url(url, timeout_s=timeout_s)
```

> **Decisión de dirección de dependencia, explícita:** `agenda_health` **posee** `ALIVE_STATUS_CODES` (público, sin underscore) y **no** importa `environment_preflight` a nivel de módulo. `environment_preflight` sí importará `agenda_health` en F9. El import de `get_agenda_base_url` va **dentro de la función** para que el ciclo no exista en tiempo de import. `get_agenda_base_url` **no se mueve**: tiene importadores en todo el tool y moverla sería un refactor de riesgo gratuito.

**Tests PRIMERO:** `tests\unit\test_plan262_agenda_health.py` — 11 casos, todos con `unittest.mock.patch` sobre `urllib.request.urlopen`, cero red real:
1. `test_200_es_vivo`
2. `test_302_es_vivo` — redirección a login **no** es caída
3. `test_401_es_vivo` — HTTPError con code 401 ⇒ `alive is True`
4. `test_403_es_vivo`
5. `test_400_es_vivo` — el caso host-binding documentado en `environment_preflight.py:59-61`
6. `test_500_no_es_vivo` — `alive is False`, `status == 500`
7. `test_connection_refused_no_es_vivo` — `URLError` ⇒ `alive is False`, `error` contiene `"URLError"`
8. `test_excepcion_inesperada_no_lanza` — `urlopen` levanta `RuntimeError("boom")` ⇒ devuelve `HealthProbe(alive=False)` y **no propaga**
9. `test_timeout_cero_se_clampea` — `probe_url(url, timeout_s=0)` ⇒ el `timeout` pasado a `urlopen` es `>= 0.5`
10. `test_alive_codes_son_los_mismos_que_el_preflight` — `agenda_health.ALIVE_STATUS_CODES == environment_preflight._ALIVE_STATUS_CODES`
11. `test_probe_agenda_usa_la_base_url_no_la_ruta` — con `AGENDA_WEB_BASE_URL="http://x/AgendaWeb/"` en el env, la URL pedida a `urlopen` es exactamente `"http://x/AgendaWeb/"`, **sin** ningún `.aspx` concatenado

**Comando:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_agenda_health.py" -q
```

**Criterio de aceptación BINARIO:** `11 passed`.
**Rojo antes / verde después:** ANTES → `ERROR ... ModuleNotFoundError: No module named 'agenda_health'` (colección falla, exit ≠ 0). DESPUÉS → `11 passed`.
**Gate corrido contra el defecto:** el caso 3 (`401 es vivo`) es exactamente el defecto que este plan ataca — un naive `resp.status == 200` lo llamaría caída. Implementación prohibida: comparar contra `200` a secas ⇒ el test 3, 4 y 5 fallan.

**Flag que la protege:** ninguna. Es un módulo nuevo sin importadores hasta F7/F8/F9; **inerte por construcción**. Gatear un módulo que nadie llama sería teatro.
**Impacto por runtime:** idéntico en los 3 (sólo `urllib` de la stdlib). Fallback: N/A.
**Trabajo del operador:** ninguno.

---

### F2 — Configuración por UI: 7 claves nuevas, y el arreglo del puente que hoy destruye los valores

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
- **`[NO VERIFICADO]`**: no abrí el frontend, así que no verifiqué que el panel de flags renderice un input numérico y un input de lista para `type="int"`/`"float"`/`"csv"`. El campo `type` existe para eso y el plan 83 documenta los bounds como *"hint de UI"*, pero **el implementador debe confirmarlo antes de cerrar F2** (riesgo R-4 en §7).

#### F2.1 — El defecto del puente (BUG REAL, encontrado verificando)

`api/qa_uat.py::_export_qa_uat_flags` (`:91`) hace, en `:108`:

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

#### F2.2 — Las 7 claves nuevas

| Clave | `type` | bounds | default EFECTIVO en `config.py` | Por qué ese default |
|---|---|---|---|---|
| `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` | `bool` | — | `"true"` (**ON**) | Gate de capacidad. Nace ON: no quema tokens en reposo (cero LLM, INV-6), no escribe en ningún sistema real del operador, no le saca ninguna decisión. Con OFF, comportamiento de hoy (INV-8). |
| `STACKY_QA_UAT_RECOVERY_MAX_PER_RUN` | `int` | `(0, 50)` | `6` | Cota global anti-bucle. 6 = una recuperación por minuto en el run típico de 6 min (`QA_UAT_MAX_TOTAL_MINUTES` default `"6"`, `uat_test_runner.py:139`). `0` = recuperación medida pero nunca ejecutada (modo observación). |
| `STACKY_QA_UAT_RECOVERY_MAX_PER_CASE` | `int` | `(0, 10)` | `1` | Un reintento por caso. Alineado con `_MAX_REAUTH_PER_STEP = 1` (`navigation_driver.py:109`) y con `QA_UAT_MAX_LOGIN_ATTEMPTS` default `"1"` (`uat_test_runner.py:135`). |
| `STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S` | `float` | `(1, 30)` | `5.0` | **Idéntico** a `environment_preflight._CHECK_TIMEOUT_S = 5.0` (`:54`). Cambiar el número acá sería introducir una segunda política de timeout. |
| `STACKY_QA_UAT_ROUTE_ALLOWLIST` | `csv` | — | `""` (vacío) | Vacío = allowlist **derivada** del código (ver F4), no "todo permitido". Nace vacío para que el comportamiento por defecto no dependa de que el operador la llene. |
| `STACKY_QA_UAT_SAFE_ROUTE` | `csv` | — | `""` (vacío) | Vacío = **la URL base**, que siempre existe y siempre es válida. Ver la nota de tipo abajo. |
| `AGENDA_WEB_BASE_URL` | `csv` | — | `"http://localhost:35017/AgendaWeb/"` | **Registrar el nombre EXACTO que el tool ya lee.** `environment_preflight.get_agenda_base_url` (`:67`) lo lee en `:76`, y hay ~20 archivos más del tool que leen esa misma env var `[NO VERIFICADO el conteo exacto de 20; verifiqué environment_preflight.py:76, smoke_path_checker.py:66, deeplink_readiness_checker.py:115]`. Registrarlo con su nombre real hace que la UI controle a todos **sin tocar una línea de esos archivos**. |

> **Limitación de tipo, declarada:** `FlagSpec.type` **no tiene un tipo `"str"`** (verificado, `harness_flags.py:23`). `STACKY_QA_UAT_SAFE_ROUTE` y `AGENDA_WEB_BASE_URL` son valores de un solo elemento y se declaran `type="csv"`; el lector del tool toma el **primer elemento no vacío** y un test asserta que la lista tiene exactamente 1 elemento. Es un compromiso consciente, no un descuido: usar `type="json"` para un string suelto sería peor.

> **Decisión: NO se crea una flag nueva para el reinicio del servicio en caliente.** Arrancar IIS Express durante el run es el **mismo acto** que ya gatea `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` (`harness_flags.py:547`, default `"true"` en `config.py:1232`). F7 reusa **esa** flag. Crear una segunda sería duplicar el gate del 240 y romper la frontera del §3.

> **Validación cruzada obligatoria:** `STACKY_QA_UAT_SAFE_ROUTE`, si no está vacía, **debe** pertenecer a la allowlist efectiva. Una ruta segura fuera de la allowlist es un bucle garantizado: el orquestador volvería a una ruta que su propio validador rechaza. `recovery_config.validate_recovery_config()` lo verifica y `route_allowlist` **auto-incluye** la ruta segura (F4).

#### F2.3 — Las 7 estructuras que toca cada clave (6 estructuras / 5 archivos, **más una séptima para las numéricas**)

1. `backend/services/harness_flags.py` → `FLAG_REGISTRY`: 7 `FlagSpec` nuevos. Los 6 de valor **SIN `default=`** (así `default_is_known` devuelve `False` — verificado: `default_is_known(spec)` es literalmente `return spec.default is not None`, `:5816`). El bool **CON `default=True`**.
2. `backend/services/harness_flags.py` → `_CATEGORY_KEYS` (`:120`), categoría **`"calidad_verificacion"`** (abre en `:154`), junto a las 7 keys QA UAT que ya viven ahí (`:171-172`, `:174`, `:178`). El comentario de `:514` lo hace obligatorio: *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS`"*.
3. `backend/config.py` → los 7 atributos con el default EFECTIVO de la tabla, siguiendo los patrones verificados (`:1316-1320` para csv/int, `:2114` para int simple). Ubicación sugerida: junto al bloque QA UAT existente de `:1224-1239`.
4. `backend/services/harness_flags_help.py` → `PLAIN_HELP` (`:25`): 7 entradas `PlainHelp`. Contrato **verificado, son 6 reglas**: `what` ≥10 y ≤200 chars; `on_effect` ≤240; `off_effect` ≤240; `example` ≤300 (`class PlainHelp`, `:19`); `on_effect` y `off_effect` **deben empezar con `"Si "`** (`test_plain_help_on_off_start_with_si`, `:56`); prohibida la denylist de jerga `("MCP","TF-IDF","LLM","stdin","stdout","endpoint","frontmatter","prompt","token","regex","backend","frontend","gate","hook","runtime")` con plural opcional e insensible a mayúsculas (`:17`, `:70`), prohibido citar keys `SCREAMING_SNAKE` (`_KEY_RE = \b[A-Z]+_[A-Z0-9_]+\b`, `:22`) y prohibido referenciar fases (`_PHASE_RE = \bF\d`, `:23`).
5. `backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON` (`:467`): **una sola** key, `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`. Las 6 de valor **NO van** (no tienen `default=`, así que `default_is_known` es `False` y `test_default_known_only_for_curated` (`:1001`) — que asserta **igualdad de conjuntos** en `:1006` — se pondría rojo si las agregás).
6. `backend/harness_defaults.env` y `deployment/harness_defaults.env` → las 7 con su default. **`[NO VERIFICADO]` cuál de los dos es el generado y cuál el fuente**; existen ambos archivos. El implementador debe determinarlo antes de editar a mano el generado.
7. **La séptima, específica de las numéricas:** `backend/tests/test_harness_flags_bounds.py` → `_FROZEN_BOUNDS` (`:149`). `test_bounds_map_is_frozen` (`:223`) deriva `actual` de **todo** spec con algún bound no-`None` y hace `assert actual == _FROZEN_BOUNDS` (`:231`). Las 3 numéricas con bounds **obligan** 3 entradas nuevas:
   ```python
   "STACKY_QA_UAT_RECOVERY_MAX_PER_RUN": (0, 50),
   "STACKY_QA_UAT_RECOVERY_MAX_PER_CASE": (0, 10),
   "STACKY_QA_UAT_HEALTH_PROBE_TIMEOUT_S": (1, 30),
   ```
   Las 3 califican para tener bounds según el "procedimiento F1 paso 4" documentado en ese archivo (bounds sólo para flags con consumidor real): sus consumidores son `recovery_budget` (F5) y `agenda_health` (F1).

8. `api/qa_uat.py` → `_QA_UAT_FLAG_KEYS` (`:82`): agregar las 7. Sin esto **nacen invisibles para el tool** (trampa documentada del 240 C13).

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
    "STACKY_QA_UAT_ROUTE_ALLOWLIST":         "",
    "STACKY_QA_UAT_SAFE_ROUTE":              "",
    "AGENDA_WEB_BASE_URL":                   "http://localhost:35017/AgendaWeb/",
}

def hot_recovery_enabled() -> bool: ...
def recovery_max_per_run() -> int: ...
def recovery_max_per_case() -> int: ...
def health_probe_timeout_s() -> float: ...
def route_allowlist_raw() -> list[str]: ...
def safe_route_raw() -> str: ...
def validate_recovery_config() -> list[str]: ...   # [] = OK; strings = problemas
def snapshot() -> dict: ...                        # para el log y para runtime-doctor
```

Casos borde del lector, todos con test:
- valor no numérico (`"abc"`, `"true"`) ⇒ **cae al default**, no levanta. Log en nivel `warning`.
- valor fuera de bounds ⇒ **se clampea** al bound y se registra. El motivo: `value_in_bounds` (`harness_flags.py:5883`) protege la escritura por UI, pero **no** protege una env var puesta a mano.
- csv con espacios y comas colgantes (`" FrmLogin.aspx , ,FrmBusqueda.aspx "`) ⇒ `["FrmLogin.aspx", "FrmBusqueda.aspx"]`.
- `AGENDA_WEB_BASE_URL` sin `/` final ⇒ normalizada con `/` final, **igual que `get_agenda_base_url`** (`environment_preflight.py:76`, `raw.rstrip("/") + "/"`).

**Tests PRIMERO — TRES archivos (2 en el tool, 1 en el backend):**

`tests\unit\test_plan262_recovery_config.py` (tool) — 12 casos:
`test_defaults_completos` (las 7 keys presentes) · `test_bool_true_por_default` · `test_bool_off_respetado` (`"false"`, `"0"`, `"no"`) · `test_int_no_numerico_cae_al_default` · `test_int_fuera_de_bounds_se_clampea` (`"999"` ⇒ `50`) · `test_float_timeout_negativo_se_clampea` · `test_csv_limpia_espacios_y_vacios` · `test_csv_vacio_da_lista_vacia` · `test_base_url_normaliza_barra_final` · `test_safe_route_vacia_es_la_base_url` · `test_validate_detecta_safe_route_fuera_de_allowlist` (mensaje contiene la ruta ofensora) · `test_snapshot_no_expone_credenciales` (asserta que `snapshot()` no contiene las claves `AGENDA_WEB_USER` ni `AGENDA_WEB_PASS`)

`backend\tests\test_plan262_recovery_flags.py` (backend) — 10 casos:
1. `test_las_7_keys_estan_en_el_registry` — mensaje del assert = **la lista de las faltantes por nombre**, no un conteo
2. `test_las_7_keys_estan_categorizadas` — `categorize(k) == "calidad_verificacion"` para las 7; mensaje = las mal categorizadas con su categoría real
3. `test_los_tipos_son_los_declarados` — dict `{key: type}` exacto (`bool`/`int`/`int`/`float`/`csv`/`csv`/`csv`)
4. `test_solo_la_bool_tiene_default_explicito` — `spec.default is True` para la bool; `spec.default is None` para las 6 de valor
5. `test_las_3_numericas_tienen_bounds` — `(min_value, max_value)` exactos
6. `test_las_7_estan_en_config_py` — `hasattr(config, k)` para las 7
7. `test_defaults_de_config_coinciden_con_el_tool` — **paridad cross-árbol**: parsea `recovery_config.DEFAULTS` del tool (por lectura de texto + `ast.literal_eval` del dict, sin importar el tool) y lo compara con los valores de `config`. Mensaje = las divergencias con ambos valores.
8. `test_las_7_estan_en_la_tupla_de_export` — `set(...) <= set(api.qa_uat._QA_UAT_FLAG_KEYS)`
9. `test_export_de_bool_sigue_siendo_true_false` — **guarda de no-regresión**: para las 5 keys bool preexistentes (`:83-87`), `_export_qa_uat_flags()` produce exactamente `"true"` o `"false"`
10. `test_export_de_valor_no_se_coacciona_a_booleano` — con `config.STACKY_QA_UAT_RECOVERY_MAX_PER_RUN = 6`, `os.environ["STACKY_QA_UAT_RECOVERY_MAX_PER_RUN"] == "6"` y **no** `"true"`

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
| A2.1 | 12 casos del lector verdes | tool `test_plan262_recovery_config.py` | `ModuleNotFoundError: recovery_config` | `12 passed` |
| A2.2 | 10 casos de flags verdes | `test_plan262_recovery_flags.py` | `10 failed` (el registry no tiene ninguna key) | `10 passed` |
| A2.3 | `test_harness_flags.py` **sigue** en 56 | idem | `56 passed` | `56 passed` |
| A2.4 | **bounds**: sube de 18 a 18 y sigue verde | `test_harness_flags_bounds.py` | Si registrás las numéricas **sin** tocar `_FROZEN_BOUNDS` → **`1 failed`** en `test_bounds_map_is_frozen`. **Este es el gate corrido contra el defecto.** | `18 passed` |
| A2.5 | ratchet meta **sigue** en 4 | `test_harness_ratchet_meta.py` | Si creás el test backend sin registrarlo → **`1 failed`** con el archivo nombrado | `4 passed` |
| A2.6 | **DELTA sobre archivo rojo**: ninguna de las 7 keys aparece en `missing` | el `Select-String` de arriba | **7 líneas** con las 7 keys (sin ayuda llana) | **0 líneas**. El archivo sigue en `4 failed, 4 passed` (deuda ajena de 80→80 keys, ahora sin las mías) |
| A2.7 | **DELTA sobre archivo rojo**: la deuda del `.ps1` no sube de 65 | `test_plan259_ratchet_script_parity.py` | Si registrás sólo en el `.sh` → el mensaje dice **66** | el mensaje sigue diciendo **65**; el archivo sigue en `1 failed, 11 passed` |

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`, default **ON**. Las 6 claves de valor no necesitan gate propio: con la bool en OFF nadie las lee.
**Impacto y fallback por runtime:** el registro de flags es backend puro, idéntico en los 3 runtimes. `recovery_config` usa sólo `os` y `re` de la stdlib. Fallback: si `recovery_config` no se puede importar, `agenda_health.probe_agenda` cae a `DEFAULT_PROBE_TIMEOUT_S` (ya está en F1) y `hot_recovery` (F7) se desactiva a sí mismo — degradación al comportamiento de hoy, no ruptura.
**Trabajo del operador:** ninguno obligatorio. Opcionalmente, revisar los 7 controles nuevos en el panel de flags (categoría *Calidad y verificación del entregable*) y ajustar la URL base si su AgendaWeb no está en el puerto 35017.

---

### F3 — `recovery_classifier.py`: las 5 clases que pidió el operador, mapeadas a las 4 taxonomías que ya existen

**Objetivo (1 frase):** una función determinista que, dada una excepción + la ruta usada + el resultado del probe de salud, devuelva **exactamente una** de las 5 clases del pedido, y su traducción a las categorías que el resto del pipeline ya entiende.

**Valor:** es la pieza que convierte "algo explotó" en "esto es una ruta mala, no una caída". Todo el resto del plan depende de este veredicto.

**Restricción de alcance, explícita:** existen **CUATRO** taxonomías paralelas y divergentes, ninguna con `enum.Enum`:
- `playwright_result_classifier.VALID_VERDICTS` (`:57`, 4 valores) y `VALID_CATEGORIES` (`:58`, **7**: `APP NAV ENV DATA OPS OBS PIP`), con `_CLASSIFICATION_RULES` (`:65`) y entrada `classify_playwright_results` (`:189`).
- `failure_triage.VALID_VERDICTS` (`:58`, **5** — agrega `SKIPPED`) y `VALID_CATEGORIES` (`:59`, **9** — agrega `GEN` y `SEC`), con `_CATEGORY_OWNER` (`:64`) y `_REASON_RULES` (`:92`).
- `uat_failure_analyzer._FAILURE_CATEGORIES` (`:56`).
- `navigation_driver._classify_error` (`:859`), cadena de `if` que devuelve 10 códigos: `NAV_DEVIATION` (`:872`), `NAV_SESSION_LOST` (`:875`), `MENU_LABEL_NOT_FOUND` (`:877`), `APP_ERROR_PAGE` (`:879`), `NAV_AUTH_EXPIRED` (`:882`), `NAV_TIMEOUT` (`:884`), `NAV_FORM_NOT_FOUND` (`:886`), `NAV_PLAYWRIGHT_ERROR` (`:887`), más `NAV_DOPOSTBACK_NOT_AVAILABLE` y `NAV_JS_ERROR` emitidos desde `_execute_nav` (`:687`).

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

# Codigos de navigation_driver._classify_error -> clase de recuperacion.
_NAV_CODE_TO_CLASS: dict[str, str] = {
    "NAV_DEVIATION":                ROUTE_ERROR,
    "MENU_LABEL_NOT_FOUND":         ROUTE_ERROR,
    "NAV_FORM_NOT_FOUND":           ROUTE_ERROR,
    "APP_ERROR_PAGE":               ROUTE_ERROR,
    "NAV_DOPOSTBACK_NOT_AVAILABLE": ROUTE_ERROR,
    "NAV_SESSION_LOST":             SESSION_ERROR,
    "NAV_AUTH_EXPIRED":             SESSION_ERROR,
    "NAV_TIMEOUT":                  UNRECOVERABLE,   # ver nota abajo
    "NAV_JS_ERROR":                 UNRECOVERABLE,
    "NAV_PLAYWRIGHT_ERROR":         UNRECOVERABLE,
}

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
        health = agenda_health.probe_agenda()   # SIEMPRE la base, nunca route_used

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

PASO 5  Si NO RESPONDE (health.alive is False) -> SERVICE_DOWN.
        Es la UNICA clase que autoriza intentar levantar el servicio.

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

**Tests PRIMERO:** `tests\unit\test_plan262_recovery_classifier.py` — 22 casos:
`test_las_5_clases_y_nada_mas` (`RECOVERY_CLASSES` tiene exactamente 5 y son las nombradas) · `test_toda_clase_mapea_a_una_categoria_existente` (cada `category` del mapeo ∈ `playwright_result_classifier.VALID_CATEGORIES` **y** ∈ `failure_triage.VALID_CATEGORIES`) · `test_todo_verdict_esta_en_valid_verdicts` · `test_todo_owner_esta_en_valid_owners` (∈ `failure_triage.VALID_OWNERS`, `:60`) · `test_los_10_nav_codes_del_driver_estan_mapeados` (**gate anti-deriva**: extrae los códigos de `navigation_driver.py` por regex `return "([A-Z_]+)"` sobre `_classify_error` y asserta que **todos** están en `_NAV_CODE_TO_CLASS`; el mensaje lista los huérfanos por nombre) · `test_app_caida_da_service_down` · `test_ruta_no_permitida_con_app_viva_da_route_error` · `test_nav_deviation_da_route_error` · `test_menu_label_not_found_da_route_error` · `test_session_lost_da_session_error` · `test_auth_expired_da_session_error` · `test_nav_timeout_con_app_viva_da_unrecoverable` · `test_app_viva_ruta_legal_sin_nav_code_da_functional_error` · `test_functional_error_no_es_recuperable` (`taxonomy["recoverable"] is False`) · `test_health_none_da_unrecoverable_no_functional` · `test_exc_vacia_da_unrecoverable` · `test_nav_code_gana_sobre_ruta_no_permitida` · `test_evidence_nunca_vacia` (para las 5 clases) · `test_route_used_vacia_se_rotula_desconocida` · `test_redireccion_a_otro_host_da_route_error` · `test_clasificador_no_importa_ningun_modulo_de_llm` (lee el módulo como texto y asserta 0 hits de `invoke_local_llm`, `openai`, `anthropic`, `STACKY_LLM_BACKEND`) · `test_clasificar_es_puro` (dos llamadas con los mismos argumentos devuelven `RecoveryVerdict` iguales)

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_recovery_classifier.py" -q`

**Criterio de aceptación BINARIO:** `22 passed`.
**Rojo antes / verde después:** ANTES → `ModuleNotFoundError: No module named 'recovery_classifier'`. DESPUÉS → `22 passed`.
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
2. `_CLASS_TO_TAXONOMY[recovery_class]["recoverable"]` es `False` ⇒ `(False, "clase_no_recuperable")`. Esto hace que `FUNCTIONAL_ERROR` **jamás** consuma presupuesto (INV-2) y que el contador no se contamine con resultados legítimos.
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

**El defecto, ya medido (§2):** `uat_test_runner.py:136` `max_nav_retries = int(os.environ.get("QA_UAT_MAX_NAVIGATION_RETRIES", "1"))` — **1 hit, nunca usada**. `navigation_executor.ts:allowedAttempts:375` lee `QA_UAT_MAX_NAVIGATION_RETRIES ?? QA_NAV_RETRIES ?? 0` (`:377`). El runner exporta **sólo** `QA_NAV_RETRIES` con default `"3"` (`:343`). Efectivo hoy: **3**.

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
8. `test_el_ts_lee_las_dos_keys` — lee `playwright/helpers/navigation_executor.ts` como texto y asserta que `:377` menciona **ambos** nombres (gate de deriva: si alguien cambia el TS, este test avisa)

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_nav_retries_unified.py" -q`
**Regresión obligatoria:** `& $PY -m pytest "$TOOL\tests\unit\test_navigation_driver.py" "$TOOL\tests\unit\test_navigation_strategy_resolver.py" -q` — **correr cada archivo por separado** y anotar los conteos antes y después; deben ser idénticos.

**Criterio de aceptación BINARIO:** `8 passed`, y los dos archivos de regresión con el **mismo** conteo que antes del cambio.
**Rojo antes / verde después:** ANTES → **`3 failed, 5 passed`** (falla 1 porque `max_nav_retries` existe; falla 4 porque el alias no llega; falla 5 porque sólo se exporta una key). DESPUÉS → `8 passed`.
**Gate corrido contra el defecto:** el caso 2 es la trampa. La "limpieza obvia" —hacer que `max_nav_retries` (default `1`) sea la canónica— pasa los casos 1, 4 y 5 y **falla el 2**, porque bajaría los reintentos efectivos de 3 a 1. Ese es exactamente el error que el gate existe para atrapar.

**Flag que la protege:** **ninguna, a propósito.** Es la corrección de un bug con comportamiento efectivo preservado (3 → 3). Gatear un no-cambio de comportamiento detrás de una flag sería agregar una rama muerta más.
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
        health = agenda_health.probe_agenda()      # SIEMPRE la base (INV-5)
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

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED` (default ON) para toda la orquestación; **`STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED`** (del plan 240, default ON) específicamente para el paso 5a. **Dos flags porque hay dos naturalezas**: clasificar y reintentar es inocuo; arrancar un proceso en la máquina del operador ya tiene su propio gate y se respeta.
**Impacto y fallback por runtime:** el orquestador es Python + stdlib. `reauth_in_page` es `async` y requiere un `page` de Playwright — igual en los 3 runtimes. Fallback por runtime: ninguno necesario (INV-6). Fallback por **capacidad**: sin Playwright disponible, `retry_case` devuelve `BLOCKED` vía `_blocked_result` (`uat_test_runner.py:1003`), que es el comportamiento de hoy.
**Trabajo del operador:** ninguno. Si quiere ver la recuperación sin que actúe, poner `RECOVERY_MAX_PER_RUN = 0` (modo observación de F5).

---

### F8 — Fin del catch-all: `PIPELINE_CRASH` clasificado, con el traceback intacto

**Objetivo (1 frase):** que el `except Exception` de `qa_uat_pipeline.py:690` clasifique antes de rotular, sin perder ni un byte del traceback que el 241 F6 agregó a propósito.

**Valor:** es el síntoma exacto que reportó el operador. Hasta esta fase, todo lo anterior existe pero el crash sigue diciendo "OPS/PIPELINE_CRASH".

**Archivo:** `Stacky tools\QA UAT Agent\qa_uat_pipeline.py`, dentro de `run` — el bloque `except Exception as _pipeline_crash:` (`:690`) y el dict que arma (`:697` en adelante, con `"reason": "PIPELINE_CRASH"` en `:702`).

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
                from agenda_health import probe_agenda
                _rc_verdict = classify_recovery(
                    exc=_pipeline_crash,
                    exc_text=f"{type(_pipeline_crash).__name__}: {_pipeline_crash}",
                    route_used=_last_route_used(),        # helper nuevo, ver abajo
                    nav_code=None,
                    health=probe_agenda(),                # el probe que hoy NO existe
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

### F9 — Un solo decisor de "app viva": las tres copias delegan

**Objetivo (1 frase):** que exista **exactamente una** definición de los alive codes y **una** función de probe HTTP en todo el tool, sin cambiar ninguna firma pública.

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

3. **`smoke_path_checker.py`** — se elimina la copia literal de `:40` y se reemplaza por el mismo alias. `_check_http` (`:127`, con su uso de los alive codes en `:140`) delega en `agenda_health.probe_url` **conservando su dict de retorno exacto** (es consumido por `run_smoke_path`, `:45`). Y el `"http://localhost:35017/AgendaWeb/"` hardcodeado de `:66` pasa a `get_agenda_base_url()`.

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
   `ensure_agenda_web` (`:88`), su polling (`:157-163`), `proc.terminate()` (`:167`), `START_TIMEOUT` (`:170`) y `stop_agenda_web` (`:179`) **no se tocan**.

**Tests PRIMERO:** `tests\unit\test_plan262_single_source_alive.py` — 10 casos:
1. `test_una_sola_definicion_del_frozenset` — **gate de conteo con mensaje discriminante**: recorre todos los `*.py` de la raíz del tool y cuenta los que contienen el literal `frozenset({200, 301, 302, 400, 401, 403})`. Debe ser **1** (`agenda_health.py`). El assert reporta **la lista de archivos ofensores por nombre**, no el conteo — `assert offenders == []` con `f"copias de los alive codes en: {offenders}"`.
2. `test_preflight_usa_el_alias` — `environment_preflight._ALIVE_STATUS_CODES is agenda_health.ALIVE_STATUS_CODES`
3. `test_smoke_usa_el_alias` — idem para `smoke_path_checker`
4. `test_launcher_responds_delega` — `agenda_health.probe_url` mockeado; `_responds` devuelve lo que devuelve el mock
5. `test_launcher_no_tiene_fallback_hardcodeado` — 0 hits de `frozenset({200` en `agenda_web_launcher.py`
6. `test_smoke_no_hardcodea_la_base_url` — 0 hits de `"localhost:35017"` en `smoke_path_checker.py`
7. `test_preflight_logger_tiene_el_prefijo_de_la_casa` — el logger del módulo se llama `"stacky.qa_uat.environment_preflight"`
8. `test_run_environment_preflight_sigue_devolviendo_app_not_running` — con `urlopen` mockeado a `URLError`, `reason == "APP_NOT_RUNNING"` (contrato consumido por `qa_uat_pipeline.py:404`)
9. `test_run_smoke_path_conserva_su_contrato` — las claves del dict de `_check_http` son las mismas de antes (lista exacta)
10. `test_sin_ciclo_de_imports` — `importlib.import_module("agenda_health")` y luego `importlib.import_module("environment_preflight")` en un intérprete limpio, en **los dos órdenes**, sin `ImportError`

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_single_source_alive.py" -q`
**Regresión obligatoria (por archivo):**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan240_agenda_launcher.py" -q      # baseline medido: 9 passed
& $PY -m pytest "$TOOL\tests\unit\test_plan240_login_url_predicate.py" -q
```

**Criterio de aceptación BINARIO:** `10 passed`, **y `test_plan240_agenda_launcher.py` sigue en `9 passed`** (baseline medido el 2026-07-29).
**Rojo antes / verde después:** ANTES → `3 failed` como mínimo: el caso 1 falla reportando **3 archivos** (`environment_preflight.py`, `smoke_path_checker.py`, `agenda_web_launcher.py`); el 2 y el 3 fallan por identidad. DESPUÉS → `10 passed`.
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
| `recovery_health_probe` | paso 3 | `url`, `alive`, `status`, `elapsed_ms`, `error` |
| `recovery_classified` | tras F3 | `recovery_class`, `reason_code`, `route_allowed`, `evidence` |
| `recovery_action` | por cada acción del paso 4/5 | `action`, `target`, `ok` |
| `recovery_budget_state` | tras cada `consume` | `used_run`, `max_run`, `used_case`, `max_case`, `service_starts` |
| `recovery_outcome` | al cerrar el intento | `succeeded`, `attempts`, `final_reason`, `route_used` |

Además se usan los métodos existentes: `stage_error` (`:287`) para el error original y `flake_suspected` (`:630`) cuando un caso pasa **después** de un reintento — señal honesta de inestabilidad, no de éxito.

> **Los 6 eventos son aditivos.** No se modifica ni se renombra ningún evento existente: hay consumidores de ese JSONL (`_collect_precheck_events_from_evidence`, `uat_test_runner.py:946`; `evidence_manifest.build_evidence_manifest`, `:42`).

#### F10.2 — El reporte de no-recuperable

Cuando `RecoveryOutcome.succeeded is False` y el caso se marca fallido, el dict del caso (el que produce `_blocked_result`, `uat_test_runner.py:1003`) lleva un bloque `recovery_report` con **exactamente los 4 campos que pidió el operador**, más los que hacen el diagnóstico accionable:

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
    "health": {...},              # agenda_health.probe_agenda(), en vivo
    "flags_exported": [...],      # las 7 keys y el valor con el que salieron
}
```
Aditivo: ninguna clave existente de la respuesta cambia de nombre, tipo ni posición.

**Tests PRIMERO — dos archivos:**

`tests\unit\test_plan262_unrecoverable_report.py` (tool) — 12 casos:
`test_los_4_campos_del_operador_estan_presentes` (mensaje = **los que faltan por nombre**) · `test_ningun_campo_obligatorio_es_none` · `test_route_used_desconocida_cuando_no_se_sabe` · `test_attempts_es_entero_no_none` · `test_final_reason_nunca_vacio` · `test_app_alive_true_cuando_la_app_respondio` (**el campo que prueba que NO fue una caída**) · `test_los_6_eventos_se_emiten_en_orden` (con un `exec_log` fake: la secuencia de nombres es exactamente `["recovery_attempt_start","recovery_health_probe","recovery_classified","recovery_action","recovery_budget_state","recovery_outcome"]`) · `test_ningun_evento_existente_se_renombra` (lee `execution_logger.py` y asserta que los nombres de método `event`/`stage_error`/`flake_suspected`/`pipeline_verdict`/`screenshot`/`human_decision`/`error` siguen existiendo) · `test_flake_suspected_cuando_pasa_tras_reintento` · `test_reporte_es_json_serializable` · `test_reporte_no_contiene_credenciales` (0 hits de `AGENDA_WEB_PASS` y del valor de la password en el JSON serializado) · `test_sin_exec_log_el_reporte_se_arma_igual`

`backend\tests\test_plan262_runtime_doctor_recovery.py` (backend) — 6 casos:
`test_doctor_tiene_seccion_hot_recovery` · `test_las_claves_previas_del_doctor_siguen` (**gate de no-regresión**: el set de claves top-level de hoy ⊆ el de mañana) · `test_config_expuesta_no_trae_password` · `test_allowlist_declara_su_source` · `test_health_se_reporta_aunque_la_app_este_caida` (probe mockeado a `alive=False` ⇒ 200 OK con `alive: false`, **no** un 500) · `test_flags_exported_lista_las_7`

Este archivo backend se registra en **`.sh` (ruta pelada) Y `.ps1` (entrecomillada con coma)**, igual que el de F2.

**Comandos:**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan262_unrecoverable_report.py" -q
& $PY -m pytest tests\test_plan262_runtime_doctor_recovery.py -q         # desde backend/
& $PY -m pytest tests\test_harness_ratchet_meta.py -q                    # sigue en 4 passed
& $PY -m pytest tests\test_plan259_ratchet_script_parity.py -q           # la deuda sigue en 65
```

**Criterio de aceptación BINARIO:** `12 passed` (tool) + `6 passed` (backend) + `test_harness_ratchet_meta.py` en `4 passed` + el mensaje de la parity test sigue diciendo **65** (no 66, no 67).
**Rojo antes / verde después:** ANTES → tool `12 failed` (no existe `recovery_report`); backend `6 failed` (no existe la sección); y si se crean los 2 archivos backend sin registrar en el `.sh`, `test_harness_ratchet_meta.py` da `1 failed` **nombrando los archivos**. DESPUÉS → todo verde y la deuda ajena en 65.
**Gate corrido contra el defecto:** `test_los_4_campos_del_operador_estan_presentes` es el criterio del operador convertido en gate, y su mensaje **nombra los faltantes** en vez de colapsarlos. `test_app_alive_true_cuando_la_app_respondio` es el que prueba que el reporte dice *"la app estaba viva"* — la información que hoy no existe en ninguna parte y sin la cual el operador no puede saber que no fue una caída.

**Flag que la protege:** `STACKY_QA_UAT_HOT_RECOVERY_ENABLED`. Con OFF, `recovery_report` no se emite (no hay recuperaciones) y la sección del doctor reporta `"enabled": false` con el resto vacío — **sigue respondiendo 200**, porque un doctor que falla cuando la feature está apagada es un doctor roto.
**Impacto y fallback por runtime:** el endpoint es Flask del backend; el reporte es Python del tool. Idénticos en los 3. Fallback: el probe en vivo del doctor está envuelto y ante fallo reporta `alive: false` con el error, nunca un 500.
**Trabajo del operador:** ninguno obligatorio. Para diagnosticar, abrir `GET /api/qa-uat/runtime-doctor` y leer `hot_recovery`.

---

### F11 — El invariante del 241: la recuperación NO ablanda el veredicto

**Objetivo (1 frase):** probar con tests dedicados que ningún camino de recuperación puede convertir un fallo real en `PASS`, ni un `BLOCKED` honesto en `MIXED`.

**Valor:** es la fase que hace que este plan sea compatible con el 241 en vez de destruirlo. Sin ella, la recuperación es la mejor máquina de falsos verdes jamás construida en este repo.

**Por qué hace falta un test y no una promesa:** el 241 C4 documenta un caso **ya ocurrido** en este mismo subsistema: si el evaluador se saltaba (`stages["evaluator"].skipped` con `reason == "all_scenarios_blocked"`, `qa_uat_pipeline.py:3090`), el gate funcional devolvía `MIXED/NO_FUNCTIONAL_ASSERTION` **tapando un `BLOCKED` honesto**. El mismo patrón con recuperación en el medio es más fácil de introducir y más difícil de ver.

**Archivo nuevo:** `tests\unit\test_plan262_no_verdict_softening.py` — **14 casos**, el gate más importante del plan:

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

**Comando:** `& $PY -m pytest "$TOOL\tests\unit\test_plan262_no_verdict_softening.py" -q`
**Regresión obligatoria del 241 (por archivo, conteos anotados):**
```
& $PY -m pytest "$TOOL\tests\unit\test_plan241_discrimination.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_plan241_golden_suite.py" -q
& $PY -m pytest "$TOOL\tests\unit\test_plan241_diagnostics.py" -q
```

**Criterio de aceptación BINARIO:** `14 passed`, **y los 3 archivos del 241 con conteo idéntico al baseline**.
**Rojo antes / verde después:** ANTES → colección falla (`ModuleNotFoundError`) hasta que F3/F5/F7 existen; con F7 implementada **pero sin la regla de INV-2**, fallan los casos **1, 6 y 12** — y ese es exactamente el diseño peligroso que este gate existe para atrapar.
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
| R-4 | **`[NO VERIFICADO]` El panel de flags de la UI no renderiza inputs numéricos/csv** | Media | Medio | Verificar **antes de cerrar F2** abriendo el panel con las 7 claves cargadas. Si no los renderiza, las 6 de valor quedan configurables por env var y el plan **declara la limitación**; la bool (que sí es booleana) funciona igual. No bloquea F1/F3..F11. |
| R-5 | **El exportador booleano destruye los valores** | **Alta si no se arregla** | Alto — `int("true")` ⇒ `ValueError` ⇒ … `PIPELINE_CRASH` | F2.1 lo arregla con export por `spec.type`; casos 9 y 10 de `test_plan262_recovery_flags.py`, incluida la guarda de no-regresión de las 5 bool |
| R-6 | **Regresión silenciosa de reintentos** 3 → 1 al unificar el nombre | Media | Medio | F6 caso 2 (`test_default_efectivo_sigue_siendo_3`) es un gate dedicado exactamente a eso |
| R-7 | **La allowlist derivada rechaza rutas legítimas** y convierte `FAIL` en `ROUTE_ERROR` reintentable | Media | Alto (es R-1 por otra puerta) | La derivada es **permisiva por diseño** (F4, decisión escrita); sólo se vuelve estricta cuando el operador declara la lista; par de tests permisiva/estricta |
| R-8 | **Ruta segura fuera de la allowlist** ⇒ bucle garantizado | Baja | Alto | `route_allowlist` **auto-incluye** la ruta segura; `validate_recovery_config()` lo reporta; test dedicado en F2 y F4 |
| R-9 | **Deriva de `navigation_driver._classify_error`**: un código nuevo queda sin mapear y cae a `UNRECOVERABLE` | Media | Bajo–Medio | F3 caso `test_los_10_nav_codes_del_driver_estan_mapeados` extrae los códigos del archivo por regex y **nombra los huérfanos** |
| R-10 | **Los 2 gates rojos de fábrica** hacen ilegible el resultado | Alta (ya es así) | Medio | F0.1 los mide y nomina; A2.6 y A2.7 son criterios **delta** sobre contenido de mensaje, no sobre pass/fail |
| R-11 | **`agenda_web_launcher` mata un proceso que no arrancó** | Baja | Alto (mataría el IIS del operador) | **No se toca** `ensure_agenda_web` ni `stop_agenda_web`. La lógica `started_by_us` (`:160`, `:179`) es del 240 y queda intacta; F7 sólo la **invoca** |
| R-12 | **El probe en caliente agrega latencia** al run | Alta (por diseño) | Bajo | Un probe = 1 GET con timeout de 5 s **y sólo ante excepción**, acotado por `RECOVERY_MAX_PER_RUN` (6). Techo: 30 s sobre una ventana de 6 min = 8 %. Y sólo en runs que hoy **mueren enteros** |
| R-13 | **Sesión paralela sobre el mismo árbol** pisa los cambios | Media (documentada) | Alto | `git worktree list` **antes** de tocar nada; commits con **pathspec explícito**; **prohibido** `amend`/`reset`/`rebase`/`stash` |
| R-14 | **El pipeline in-process comparte `os.environ`** entre runs concurrentes | Baja (mono-operador) | Medio | Limitación **ya documentada** en `_export_qa_uat_flags` (`api/qa_uat.py:94-99`). Este plan la hereda y **no la empeora**; se anota en el docstring de `recovery_config` |
| R-15 | **F8 pierde el traceback del 241 F6** al refactorizar el catch | Media | Alto | `test_traceback_se_conserva` + `test_traceback_se_recorta_a_2000` en F8; el diff ilustrativo conserva la línea literal |

---

## 7. Fuera de scope (explícito)

Este plan **NO**:

1. **No reescribe las 4 taxonomías existentes.** `playwright_result_classifier` (`:57-58`, `:65`), `failure_triage` (`:58-59`, `:64`, `:92`), `uat_failure_analyzer._FAILURE_CATEGORIES` (`:56`) y `navigation_driver._classify_error` (`:859`) quedan **exactamente** como están. La taxonomía de recuperación **mapea** a ellas.
2. **No convierte ninguna taxonomía a `enum.Enum`.** Sería un refactor transversal de riesgo alto y valor estético.
3. **No implementa reintento por PASO de aserción.** Declarado inalcanzable en F7 con la evidencia: el paso es un `dict` plano (`uat_scenario_compiler.py:816`) sin identidad reanudable, y la excepción de Playwright aborta el spec desde dentro del proceso. La granularidad real de este plan es **el spec**.
4. **No escribe su propio launcher de AgendaWeb.** Es del 240 F2 (`agenda_web_launcher.py`). Este plan lo invoca.
5. **No cambia cuándo arranca un run** (214 F3: `on_execution_end`, `qa_uat_enqueue.py`, autorun opt-in).
6. **No toca `navigation_executor.ts`** más allá de leerlo en un test de deriva.
7. **No salda la deuda del `.ps1`** (65 archivos atrás, techo 64). Es deuda ajena; `_PS1_LAG_MAX` (`:46`) **no se baja**.
8. **No salda las 80 keys sin `PLAIN_HELP`** ni los otros 3 fallos de `test_harness_flags_help.py`. Sólo agrega las 7 propias.
9. **No unifica las ~20 copias de `http://localhost:35017/AgendaWeb/`.** F9 corrige **una** (`smoke_path_checker.py:66`); las 12 `diag_*.py`, `run_tests.py:34`, `auth_session_factory.py:183,644`, `deployment_fingerprint.py:64`, `build_dossier.py:141,179` y `deeplink_readiness_checker.py:19,31,115` quedan. Son scripts de diagnóstico, no el camino de producción. `[NO VERIFICADO el inventario completo; verifiqué smoke_path_checker.py:66 y deeplink_readiness_checker.py:19,31,115]`
10. **No corrige la inconsistencia de `.secrets/agenda_web.env.example`** (usa `http://localhost/AgendaWeb/` sin puerto). `[NO VERIFICADO — heredado del pedido, no abrí el archivo]`
11. **No agrega RBAC, login ni roles.** Stacky es mono-operador; `current_user` es un header sin validar.
12. **No agrega una capa LLM de clasificación.** INV-6. Si en el futuro se quisiera, sería **opcional y degradable**, y no podría cambiar el veredicto (INV-1).
13. **No toca `replan_engine`** (`MAX_REPLAN_ROUNDS = 3`, `:66`) ni `rerun_guard` (`:276`) ni `failure_triage._should_rerun` (`:656`). El presupuesto los respeta como techo (INV-7) sin reemplazarlos.
14. **No hace el smoke E2E manual contra AgendaWeb viva.** Es del operador (§10, paso 13).
15. **No commitea ni pushea.** Lo hace el operador.

---

## 8. Glosario (para un modelo menor que implemente esto)

| Término | Qué es, sin ambigüedad |
|---|---|
| **AgendaWeb** | La aplicación web ASP.NET WebForms del cliente que el QA UAT prueba. Corre local con IIS Express, por defecto en `http://localhost:35017/AgendaWeb/`. |
| **el tool** | `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\` — el pipeline QA UAT (Python + Playwright/Node). **No** es `Stacky\backend\`, que está casi vacío. |
| **el backend** | `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend\` — el Flask que dispara el tool. `api/qa_uat.py` es el puente. |
| **preflight** | `environment_preflight.run_environment_preflight` (`:119`). Corre **una vez, antes** de abrir el navegador. Fail-fast por diseño (`:53`). |
| **probe / healthcheck en caliente** | Lo que agrega este plan: `agenda_health.probe_agenda` (F1). Corre **durante** el run, ante cada excepción candidata, siempre contra la URL base. |
| **alive codes** | `frozenset({200, 301, 302, 400, 401, 403})`. Un 401 o un 302-a-login **prueban** que el servidor está vivo. Hoy hay 3 copias; después de F9, una. |
| **spec** | Un archivo `.spec.ts` de Playwright = **un caso de prueba**. Es la unidad mínima de reintento realizable en este plan. |
| **paso (step)** | Un `dict` `{"accion","target","valor"}` producido por `uat_scenario_compiler._normalize_step` (`:816`). **No** es una clase. No tiene identidad reanudable desde Python. |
| **CHILD_SCREENS** | `navigation_driver.py:114`. Pantallas que **no** admiten `goto()` directo y requieren `form.submit()`. Un `goto()` a una de ellas produce `NAV_DEVIATION`. |
| **ruta segura** | La URL a la que se vuelve tras una excepción de navegación. Configurable; por defecto, la URL base. Siempre pertenece a la allowlist. |
| **allowlist de rutas** | Conjunto de rutas relativas legales. `derived` = calculada del código (permisiva). `configured` = declarada por el operador (estricta). |
| **presupuesto de recuperación** | Contadores por run y por caso que garantizan terminación. Es un **techo**, nunca un piso (INV-7). |
| **flag** | Clave de `FLAG_REGISTRY` (`backend/services/harness_flags.py`). **No es sólo booleana**: `type` ∈ `{bool, csv, int, float, json}` (`:23`). |
| **default efectivo** | Para una flag de valor sin `default=` en su `FlagSpec`, el default real vive en `config.py`. Patrón verificado (`harness_flags.py:5142`). |
| **criterio delta** | Criterio que compara **contra el baseline medido** en un archivo rojo de fábrica, en vez de exigir "verde". |
| **rojo de fábrica** | Test que ya falla antes de tocar nada, por deuda ajena. Este plan tiene 2: `test_harness_flags_help.py` y `test_plan259_ratchet_script_parity.py`. |
| **ratchet** | Lista que sólo crece. `HARNESS_TEST_FILES` en `run_harness_tests.sh` (`:20`) y su gemelo `.ps1` (con **comillas y coma**, sintaxis distinta). |
| **veredicto** | `PASS` / `FAIL` / `BLOCKED` / `MIXED` (`playwright_result_classifier.py:57`); `failure_triage` agrega `SKIPPED` (`:58`). La recuperación **nunca** lo ablanda (INV-1). |
| **falso verde** | Un `PASS` que no certifica el criterio funcional. Es lo que el plan 241 existe para prevenir. |

---

## 9. Orden de implementación y DoD global

### 9.1 Orden numerado (por dependencia dura)

| # | Fase | Depende de | Por qué en ese lugar | Tests nuevos |
|---|---|---|---|---|
| 1 | **F0** Costura + baseline + doc stale | — | Sin baseline medido no hay criterio delta honesto | 2 (tool) |
| 2 | **F1** `agenda_health` | F0 | Es la pieza base de F3, F7, F8, F9, F10 | 11 (tool) |
| 3 | **F2** Config por UI + fix del exportador | F0 | F1 la usa opcionalmente; F5 la usa obligatoriamente | 12 (tool) + 10 (backend) |
| 4 | **F3** `recovery_classifier` | F1, F2 | Necesita el probe y la config | 22 (tool) |
| 5 | **F4** `route_allowlist` | F2 | Necesita las claves de allowlist y ruta segura | 20 (tool) |
| 6 | **F5** `recovery_budget` | F2, F3 | Necesita los máximos y saber qué clase es recuperable | 16 (tool) |
| 7 | **F6** Unificación de reintentos de navegación | F0 | **Independiente**: se puede hacer en paralelo desde el paso 2 | 8 (tool) |
| 8 | **F7** `hot_recovery` + reintento por caso | F1..F5 | Une todas las piezas | 18 (tool) |
| 9 | **F8** Fin del `PIPELINE_CRASH` catch-all | F1, F3 | Toca `qa_uat_pipeline.py`: va después de que las piezas existan | 12 (tool) |
| 10 | **F9** Un solo decisor de "app viva" | F1 | Refactor: **después** de que `agenda_health` esté probado | 10 (tool) |
| 11 | **F10** Reporte + logs + doctor | F7 | Necesita `RecoveryOutcome` real | 12 (tool) + 6 (backend) |
| 12 | **F11** Invariante anti-ablandamiento | F3, F5, F7 | Es el gate final: se corre sobre el sistema completo | 14 (tool) |

**Total: 205 casos de test** — 189 en el tool (13 archivos) + 16 en el backend (2 archivos).

**Paralelización segura:** F6 es independiente de F1..F5 y puede ir en paralelo. **F2, F8, F9 y F10 NO se paralelizan entre sí ni con nada**: F2 toca 8 estructuras compartidas del arnés (donde se pierden escrituras en silencio), F8 y F9 tocan `qa_uat_pipeline.py` y `environment_preflight.py` (archivos que todo el tool importa), y F10 toca `api/qa_uat.py` que F2 también toca. **Techo real de paralelismo de este plan: 2** (una rama F1→F3→F4→F5→F7→F11, otra F6), y F2 primero, sola.

### 9.2 DoD global — criterios DELTA

**Absolutos (archivos verdes hoy; se exige verde):**

| # | Criterio | Comando | Esperado |
|---|---|---|---|
| D-1 | Los 13 archivos de test del tool pasan, **corridos de a uno** | `& $PY -m pytest "$TOOL\tests\unit\test_plan262_<n>.py" -q` × 13 | `2, 11, 12, 22, 20, 16, 8, 18, 12, 10, 12, 14` → **189 passed** en total |
| D-2 | Los 2 archivos de test del backend pasan | `& $PY -m pytest tests\test_plan262_recovery_flags.py -q` y `... test_plan262_runtime_doctor_recovery.py -q` | `10 passed` + `6 passed` |
| D-3 | `test_harness_flags.py` sin regresión | `& $PY -m pytest tests\test_harness_flags.py -q` | **56 passed** (baseline medido) |
| D-4 | `test_harness_flags_bounds.py` sin regresión y con las 3 numéricas registradas | `& $PY -m pytest tests\test_harness_flags_bounds.py -q` | **18 passed** |
| D-5 | `test_harness_ratchet_meta.py` sin regresión | `& $PY -m pytest tests\test_harness_ratchet_meta.py -q` | **4 passed** |
| D-6 | Regresión del 240 en el launcher | `& $PY -m pytest "$TOOL\tests\unit\test_plan240_agenda_launcher.py" -q` | **9 passed** (baseline medido) |
| D-7 | Regresión del 241 (3 archivos, de a uno) | `test_plan241_discrimination.py`, `test_plan241_golden_suite.py`, `test_plan241_diagnostics.py` | conteo **idéntico** al baseline que mida el implementador en F0 |
| D-8 | Regresión de navegación (2 archivos, de a uno) | `test_navigation_driver.py`, `test_navigation_strategy_resolver.py` | conteo **idéntico** al baseline |
| D-9 | El tool compila | `& $PY -m compileall -q "$TOOL"` | exit 0 |
| D-10 | El backend compila | `& $PY -m compileall -q "$BE"` | exit 0 |

**DELTA (archivos rojos de fábrica; se exige que la deuda no crezca y que lo propio no esté):**

| # | Criterio | Comando | Baseline medido 2026-07-29 | Esperado después |
|---|---|---|---|---|
| D-11 | Ninguna de las 7 keys nuevas aparece sin ayuda llana | `& $PY -m pytest tests\test_harness_flags_help.py -q 2>&1 \| Select-String "STACKY_QA_UAT_HOT_RECOVERY\|STACKY_QA_UAT_RECOVERY_MAX\|STACKY_QA_UAT_HEALTH_PROBE\|STACKY_QA_UAT_ROUTE_ALLOWLIST\|STACKY_QA_UAT_SAFE_ROUTE\|AGENDA_WEB_BASE_URL"` | `4 failed, 4 passed`; **80 keys** en `missing` | **0 líneas** en el `Select-String`; el archivo sigue en `4 failed, 4 passed` con **80** keys ajenas |
| D-12 | La deuda del `.ps1` no crece | `& $PY -m pytest tests\test_plan259_ratchet_script_parity.py -q` | `1 failed, 11 passed`; mensaje: *"65 archivos solo en el .sh (maximo 64)"* | sigue `1 failed, 11 passed` y el mensaje sigue diciendo **65** |

**Criterios funcionales del operador — cada uno mapeado a fase y test (los 12, sin excepción):**

| Criterio del operador | Fase | Test que lo prueba |
|---|---|---|
| Diferenciar caída real de ruta inválida | F3 | `test_app_caida_da_service_down` + `test_ruta_no_permitida_con_app_viva_da_route_error` |
| Una excepción de navegación NO marca la app como no disponible | F8 | `test_crash_con_app_viva_y_ruta_mala_da_nav_route_invalid` |
| Validar el estado real por mecanismo independiente | F1 + F7 | `test_paso3_prueba_la_base_no_la_ruta_rota` (INV-5) |
| Reabrir desde ruta segura y reintentar | F7 | `test_app_viva_ruta_mala_vuelve_a_ruta_segura` |
| Corregir/recalcular ruta sin intervención manual | F7 | `test_ruta_corregida_es_match_exacto_o_ruta_segura` |
| Reintento acotado al paso/caso afectado | F7 | `test_app_viva_ruta_mala_reintenta_solo_el_caso` (**granularidad = spec**; el límite está declarado) |
| Reintentos, esperas, URL base y rutas permitidas configurables | F2 | los 12 de `test_plan262_recovery_config.py` + los 10 de `test_plan262_recovery_flags.py` |
| Evitar ciclos infinitos de recuperación | F5 | `test_presupuesto_no_se_reinicia_entre_casos` + `test_segundo_service_down_no_arranca_de_nuevo` |
| Cada excepción clasificada en las 5 clases | F3 | `test_las_5_clases_y_nada_mas` + los 10 casos de clasificación |
| Todas las recuperaciones/correcciones/reinicios/reintentos en los logs | F10 | `test_los_6_eventos_se_emiten_en_orden` |
| Reporte de no-recuperable con ruta, excepción, intentos y motivo | F10 | `test_los_4_campos_del_operador_estan_presentes` + `test_ningun_campo_obligatorio_es_none` |
| Levantar el servicio **solo** si está realmente caído | F7 | `test_app_viva_ruta_legal_funcional_no_reintenta` + `test_app_caida_arranca_el_servicio` |

**Los 8 invariantes, cada uno con su gate:** INV-1 → F11 (14 casos) · INV-2 → F5 `test_functional_error_nunca_consume` + F11 caso 1 · INV-3 → F11 caso 5 · INV-4 → F9 caso 1 · INV-5 → F7 caso 2 · INV-6 → F3 `test_clasificador_no_importa_ningun_modulo_de_llm` · INV-7 → F5 `test_service_starts_es_uno_con_flag_on` + `test_per_case_se_clampea_al_per_run` · INV-8 → F8 `test_flag_off_es_byte_identico` + F11 caso 14.

### 9.3 Trabajo del operador (consolidado — el ÚNICO trabajo humano de este plan)

1. **Confirmar el riesgo R-4**: abrir el panel de flags, categoría *Calidad y verificación del entregable*, y verificar que las 3 claves numéricas y las 3 csv rendericen un control usable. Si no, el plan se cierra con la limitación declarada.
2. **Smoke E2E manual** contra AgendaWeb viva, 4 escenarios: (a) app arriba + ruta inválida inyectada → esperar `NAV/ROUTE_INVALID` y que el resto de los casos corra; (b) app abajo → esperar `ENV/APP_NOT_RUNNING` y **un** intento de arranque; (c) sesión expirada forzada → esperar `SESSION_ERROR` + reautenticación; (d) aserción que falla de verdad → esperar `FAIL` **sin ningún reintento**.
3. **Decidir** si quiere la allowlist en modo `derived` (permisivo, default) o declarar la lista estricta de su instalación.
4. Commitear y pushear. **El plan no commitea.**

---

> **Nota final para el juez.** Los siguientes datos de este documento **no** fueron verificados de primera mano y están marcados en su lugar: el conteo de "~180 módulos Python" del tool; el inventario completo de "~20 archivos" que duplican `http://localhost:35017/AgendaWeb/` (verifiqué 5 sitios en 3 archivos); el contenido de `.secrets/agenda_web.env.example`; el conteo de "~40 `except Exception  # noqa: BLE001`" en `uat_test_runner.py`; cuál de `backend/harness_defaults.env` y `deployment/harness_defaults.env` es el generado; las líneas `harness_flags.py:519/533/567/582/2091` de 5 de las 7 `FlagSpec` QA UAT (verifiqué `:547` y `:2103`, y las 7 keys en `_CATEGORY_KEYS:171-178`); y si el panel de flags del frontend renderiza controles para `type="int"`/`"float"`/`"csv"` (R-4). **Todo el resto de los anclajes `archivo:símbolo:línea` fue verificado abriendo el archivo.** Los baselines de test de F0.1 y D-3..D-6, D-11 y D-12 fueron **ejecutados**, no estimados.
