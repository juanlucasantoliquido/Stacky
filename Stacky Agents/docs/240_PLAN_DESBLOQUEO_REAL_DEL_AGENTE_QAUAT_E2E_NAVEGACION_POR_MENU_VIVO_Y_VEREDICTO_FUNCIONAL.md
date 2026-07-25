# Plan 240 — Desbloqueo real del agente QAUAT E2E: guard de runtime, login sin falso negativo, navegación por menú vivo y veredicto funcional

> Estado: **v3 · CRITICADO 2 VECES (v1 → v2 → v3)** — VEREDICTO FINAL: **APROBADO-CON-CAMBIOS** (2026-07-25). El v1 fue **RECHAZADO** (3 BLOQUEANTES: C1, C2, C3) y el v2 también fue **RECHAZADO** (1 BLOQUEANTE nuevo: C14 — la feature de veredicto funcional habría nacido muerta). Todos resueltos en esta v3. Pipeline: proponer ✓ → criticar ✓ → **criticar v2 ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar.

**CHANGELOG v2 → v3 (segunda pasada de juez; 5 hallazgos nuevos, todos probados ejecutando):**
- **C14 (BLOQUEANTE, resuelto):** `AdoClient.get_work_item(ado_id, fields=None)` tiene una **lista hardcodeada de 7 campos** (`ado_client.py:868-871`) que **NO incluye `System.Description`**. Probado: `get_work_item(367)` → `System.Description` **ausente (0 chars)**; con lista explícita → **12.622 chars**. Como F5 llamaba `get_work_item(ticket_id)` sin `fields`, F6 habría recibido siempre un work item vacío y **todo** run habría dado `MIXED/NO_FUNCTIONAL_ASSERTION`: la feature nacía muerta. F5 ahora pasa la lista explícita (verificado que ADO **no** devuelve 400 cuando un campo no existe para ese tipo: simplemente lo omite — se pidieron 11 y volvieron 9).
- **C15 (IMPORTANTE, resuelto) — [ADICIÓN ARQUITECTO #2], cambia F6 de heurística a parseo estructural:** `Microsoft.VSTS.Common.AcceptanceCriteria` **no existe en este proyecto** (0 chars en los 4 tickets sondeados; ausente del dump completo de 25 campos). Pero los criterios **sí existen**, dentro de `System.Description`, con una **estructura canónica por headings** verificada: `RESUMEN EJECUTIVO`, `CONTEXTO DE NEGOCIO`, `ANALISIS FUNCIONAL`, `ANALISIS TECNICO`, `PASOS DE REPRODUCCION`, `CRITERIOS DE ACEPTACION`, `ARCHIVOS Y MODULOS PROBABLES`, `EPICA RELACIONADA`, `PRIORIDAD Y ESTIMACION` (sin acentos). Los criterios son `<li>` con ids tipo `CA-01:`, **pantalla explícita** (`FrmBusqueda.aspx`) y **valor esperado** (`50 caracteres`); y `PASOS DE REPRODUCCION` son `<li>` que describen literalmente la navegación a ejecutar. F6 ahora **parsea secciones** (mucho más preciso que regex sobre prosa) y devuelve además `repro_steps`, que F3 consume como guion de navegación. Casos borde probados: el 367 **duplica todo el bloque** (headings dos veces → gana la primera aparición) y arranca con un **preámbulo espurio de agente** ("Ahora reviso la capa de negocio…") que hay que descartar.
- **C12 (IMPORTANTE, resuelto):** el guard de F0 tenía un **falso positivo propio**. `pw.chromium.executable_path` devuelve el Chrome **headed** (`…\chromium-1228\chrome-win64\chrome.exe`), pero `launch(headless=True)` usa el **headless shell** (`…\chromium_headless_shell-1228\chrome-headless-shell-win64\chrome-headless-shell.exe`) — ejecutables distintos, probado. Un chequeo que solo hace `stat` de `executable_path` puede dar **OK mientras el launch falla** (exactamente el error original: *"Executable doesn't exist at …chromium_headless_shell-1228…"*). F0 ahora valida **ambas** rutas y el preflight llama `probe_launch=True` **una vez por run** (autoritativo, ~1 s, evita un fallo de 25 s más tarde).
- **C13 (IMPORTANTE, resuelto):** el launcher de F2 leía su flag solo de `os.environ`, pero la exportación vive en `_run_pipeline_in_background` (camino backend). Corriendo `qa_uat_pipeline.py` **desde la CLI** — que es exactamente cómo se hacen las verificaciones en vivo del DoD y cómo depura el operador — nada la exporta ⇒ autostart quedaba **permanentemente `AUTOSTART_DISABLED`**. F2 agrega el flag de CLI `--autostart`.
- **C16 (MENOR, verificado y anotado):** `services/ado_client.py` importa **solo** `config` y `services.secrets_store` (`:27-28`) — **no** importa `db` ni `models`, así que el `sys.path` insert del bridge es **liviano** y seguro también desde la CLI (no levanta engine de BD). Anotado en F5 para que quien implemente no tema un import pesado.

> Autor: Claude Opus 5 (1M context) en rol StackyArchitectaUltraEficientCode. Juez v2: el mismo agente en rol adversarial, **verificando contra el código instalado y contra AgendaWeb viva**.

**CHANGELOG v1 → v2 (11 hallazgos; cada uno verificado ejecutando, no leyendo):**
- **C1 (BLOQUEANTE, resuelto):** F3 hacía re-auth llamando `run_auth_session` (que usa `sync_playwright`, `auth_session_factory.py:244,:258`) **desde dentro del método `async` `via_menu`**. Playwright **lanza** en ese caso: *"It looks like you are using Playwright Sync API inside the asyncio loop"* (`playwright/sync_api/_context_manager.py:48`). El driver es async (7 `async def` en `navigation_driver.py`). F3 ahora define un helper **async** nuevo, `reauth_in_page(page, *, base_url=None)`, que loguea sobre la MISMA página async reusando las constantes de selectores; queda **prohibido** llamar `run_auth_session` desde código async.
- **C2 (BLOQUEANTE, resuelto):** F3 mandaba `page.goto(<base_url>)` pero **`NavigationDriver` no tiene `base_url`**: su constructor es `__init__(self, page, evidence_dir=None, scenario_id="nav")` (`navigation_driver.py:218-225`) y `grep -c "base_url" navigation_driver.py` → **0**. F3 ahora lo resuelve con `environment_preflight.get_agenda_base_url()` (la fuente única declarada, `environment_preflight.py:68`) por import lazy, sin tocar la firma del constructor.
- **C3 (BLOQUEANTE, resuelto):** F4 instruía `await page.evaluate(render_aspnet_exception_detector_js())`. **No funciona:** esa función devuelve una **definición de función TS** (`async function __checkAspNetException(page) { … await page.evaluate(…) }`, `screen_error_detector.py:255-256,:295`) pensada para incrustarse en un `.spec.ts` — recibe `page` y llama `page.evaluate` ella misma; pasarla a `page.evaluate` desde Python falla. F4 ahora reusa las **constantes Python** del mismo módulo (`ASPNET_EXCEPTION_TITLE_PATTERNS:171`, `DOM_ERROR_SELECTORS:92`, `DOM_ERROR_TEXT_PATTERNS:131`) con un `evaluate` propio y mínimo.
- **C4 (IMPORTANTE, resuelto) — [ADICIÓN ARQUITECTO]:** el detector existente **no detecta la página de error real**. Probado: el título de `FrmJDemanda.aspx` es `"500-Error interno del servidor ."` y matchea **0 de los 7** patrones de `ASPNET_EXCEPTION_TITLE_PATTERNS` (`"Server Error"`, `"Runtime Error"`, `"Error - AgendaWeb"`, `"Ha ocurrido un error"`, `"Se produjo un error"`, `"Application Error"`, `"Unhandled Exception"`). Sin este fix **KPI-4 era inalcanzable** aunque el cableado de C3 fuera correcto. F4 agrega los patrones faltantes al módulo existente + un test que usa el título real verificado.
- **C5 (IMPORTANTE, resuelto):** F8 mutaba `os.environ` desde un **hilo** (`_run_pipeline_in_background` corre en `threading.Thread`) y `os.environ` es **global al proceso** ⇒ dos runs concurrentes con flags distintas se pisan. Verificado que el **mecanismo** es correcto (el pipeline corre in-process — `api/qa_uat.py:66-70` inserta el tool en `sys.path`, sin subprocess — y el runner de specs sí lanza subprocess `npx playwright test`, `uat_test_runner.py:352`, que **hereda** el entorno). F8 ahora envuelve export+lanzamiento en un `threading.Lock` de módulo y **documenta** la limitación de runs concurrentes.
- **C6 (IMPORTANTE, resuelto):** la absorción declarada del **214 F2** era demasiado amplia y dejaba al 214 inconsistente: este plan **no** cubría 3 ítems de esa fase (el template `templates/playwright_test.spec.ts.j2`, el contador `nav_deviations` en `stages["runner"]`, y la huella en `error_fingerprints.json`). §0 ahora acota la absorción a exactamente `wait_aspnet_idle` + `assert_arrival` + clasificación `NAV_DEVIATION`; el contador `nav_deviations` y las huellas **se agregan a este plan** (F4/F8), y **solo el template J2 queda para el 214 F2**.
- **C7 (MENOR, resuelto):** anclaje stale heredado del 214: `FLAG_REGISTRY` está en `harness_flags.py:392` (no `:379`); `_CATEGORY_KEYS` en `:120` (no `:117`) y su bloque `calidad_verificacion` en `:154`. Corregidos en F8.
- **C8 (MENOR, resuelto):** el DoD decía "8 archivos de test" y enumeraba "7 del tool"; el conteo real es **9 archivos** (8 del tool + 1 backend). Los **79 casos** sí estaban bien (5+6+8+10+13+8+15+8+6). Corregido.
- **C9 (MENOR, resuelto):** el plan no declaraba nada sobre `requires=`. Verificado: `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`) lista **solo** las flags que TIENEN `requires`; las 3 nuevas son **independientes**, así que **no corresponde ninguna arista**, y además `FlagSpec.requires` es *"Solo informativo para la UI; NINGÚN runner lo evalúa"* (`harness_flags.py:30-32`). F8 lo declara y agrega un test que asserta la ausencia.
- **C10 (MENOR, resuelto):** faltaba la huella de regresión (convención del repo para planes tipo-fix). F8 siembra 3 entradas en `Stacky Agents/docs/sistema/error_fingerprints.json`.
- **C11 (MENOR, resuelto) — auto-colisión del gate:** el docstring que F5 mandaba escribir contenía **literalmente** `create_work_item`, `post_comment`, `update_work_item_state` y `upload_attachment`, mientras el criterio de aceptación de la misma fase exigía `grep -cE "create_work_item|post_comment|…" stacky_ado_bridge.py` → **0**. El plan se contradecía a sí mismo (misma clase que el gotcha `plan-comment-matches-own-gate`). F5 reescribe el docstring sin esos literales y conserva el grep en 0.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).
> Origen: **pedido textual del operador** — *"retomar, mejorar y poner en funcionamiento el agente QAUAT E2E basado en Playwright, de modo que pueda validar desarrollos de Agenda Web con la máxima precisión posible… evitando fallos por rutas, selectores, estados intermedios, tiempos de carga o datos de prueba… evitar falsos positivos y falsos negativos"*.

---

## 0. Frontera con el Plan 214 (leer ANTES de tocar nada)

El Plan 214 (`Stacky Agents/docs/214_PLAN_REACTIVACION_QAUAT_E2E_PLAYWRIGHT_NAVEGACION_SIN_DESVIOS_Y_VALIDACION_POST_DESARROLLO.md`, CRITICADO v2, **sin implementar**) diagnosticó el problema **desde el código**. Este plan lo diagnosticó **ejecutando el pipeline de verdad contra AgendaWeb viva el 2026-07-25**, y encontró **6 bloqueantes que el 214 no podía ver sin correrlo**. Sin este plan, **ninguna fase del 214 es verificable**: el pipeline muere en el stage `reader` y todo login se reporta como credenciales inválidas.

| Fase del 214 | Qué hace este plan |
|---|---|
| **F0** (higiene `tmp_*` + `run_tests.py`) | **NO se toca.** Sigue siendo del 214. Este plan no depende de ella. |
| **F1** (`navigation_kb.py`, `playbook_curator.py`, `GET /api/qa-uat/kb`) | **NO se toca.** Este plan aporta el insumo que la hace útil: `sanitize_for_playbook` (F3) garantiza que lo que se cure NO contenga URLs `?q=` inservibles. |
| **F2** (WebForms-safe: `wait_aspnet_idle`, `assert_arrival`, `NAV_DEVIATION`) | **PARCIALMENTE ABSORBIDA, CON CORRECCIONES** (C6 — alcance acotado con precisión). Este plan implementa, con los nombres EXACTOS que pide el 214: `wait_aspnet_idle` + `no_wait_after=True` (F4), `assert_arrival` (F4, **superior**: agrega el gate de página de error que el 214 no tenía), la clasificación `NAV_DEVIATION` en `_classify_error` y su rama en `replan_engine` (F3/F6), el contador `nav_deviations` en `stages["runner"]` (F4) y la huella en `error_fingerprints.json` (F8). **Queda ÚNICAMENTE para el 214 F2:** inyectar el helper `waitForAspNetIdle` + `noWaitAfter: true` en el template `templates/playwright_test.spec.ts.j2` (superficie TS de los specs generados, que este plan no toca). Por qué el `assert_arrival` del 214 era insuficiente: valida por ui_map/URL y habría dado **PASS falso** en `FrmJDemanda.aspx` (HTTP 200 con cuerpo "500-Error interno del servidor", H5) y **NAV_AUTH_EXPIRED falso** en la cascada de sesión destruida (H4). Quien implemente el 214 después: marcar su F2 como cubierta salvo el template, y NO reimplementar lo demás. |
| **F3** (post-hook `qa_uat_enqueue` + autorun) | **NO se toca.** Sigue siendo del 214. |
| **F4** (pane de veredicto en `OutputPanel.tsx`) | **NO se toca.** Este plan produce los campos `functional_pass` y `criteria` que ese pane podrá mostrar; los deja en `execution.metadata` sin tocar frontend. |
| **F5** (paridad: `QAUat1.agent.md` + `playbook_candidates`) | **NO se toca**, salvo un párrafo aditivo obligatorio en `QAUat1.agent.md` (F3 de este plan) porque la regla "nunca sintetices URLs con `?q=`" es una **regla de corrección**, no de estilo: sin ella el runtime Claude repite el bug. |

**Este plan NO edita ningún archivo de frontend.** Superficie 100% en `Stacky tools/QA UAT Agent/` + `backend/api/qa_uat.py` + los 5 lugares de flags. Cumple la prohibición de tocar `frontend/src/pages/TicketBoard.tsx`, `frontend/src/pages/UnblockerPage.tsx` y `frontend/src/components/TicketGraphView.jsx` (sesión paralela viva) por construcción: no toca frontend en absoluto.

---

## 1. Objetivo y KPI

**Objetivo (1 párrafo).** El agente QAUAT E2E está **bloqueado de punta a punta**, no dormido: el binding Python de Playwright no está instalado en el venv que corre el backend y el propio tool tiene un directorio `playwright/` que hace **mentir** a la detección por `find_spec` (H1); el login pasa un regex-string a `page.wait_for_url()`, que Playwright interpreta como **glob**, por lo que **todo** login se reporta `AUTH_CREDENTIALS_INVALID` aunque haya aterrizado correctamente en `FrmAgenda.aspx` (H2); el mismo fallo emite **dos diagnósticos contradictorios** (H3); AgendaWeb usa URLs con `?q=` **encriptado por sesión** y deep-linkearlas redirige a login **destruyendo la sesión**, cascando falsos `NAV_AUTH_EXPIRED` en todos los pasos siguientes (H4 — la causa raíz real del "se desvía al navegar"); hay pantallas que devuelven **HTTP 200 con cuerpo de error 500** (H5 — falso PASS); el reader de tickets depende de un CLI legacy que exige **PAT en texto plano** inexistente, matando el pipeline en su primer stage (H6); y el tool se declara incapaz de gestionar el runtime de AgendaWeb, así que con la app caída **todo** es BLOCKED (H9). Este plan arregla exactamente esos siete bloqueantes reusando el tool existente, y agrega lo que convierte "no hubo error técnico" en **veredicto funcional**: extracción determinista de criterios de aceptación, prohibición de PASS sin ninguna aserción funcional verificada, reintento acotado con corrección de enfoque, y un manifiesto de evidencia re-verificable por hash.

**KPI / impacto medible (binarios, todos verificables por comando).**
- **KPI-1 — Login veraz:** `run_auth_session(mode="normal")` contra AgendaWeb viva devuelve `ok=True, reason="AUTH_LOGIN_OK"` con `landing_url` conteniendo `FrmAgenda.aspx`. Hoy: `ok=False, AUTH_CREDENTIALS_INVALID` **siempre**, tras 25 s de espera inútil. Medible: F1.
- **KPI-2 — Pipeline pasa el stage `reader`:** `python qa_uat_pipeline.py --ticket <ADO_ID> --mode dry-run` deja de devolver `{"verdict":"BLOCKED","category":"PIP","reason":"ado_error"}` y `stages.reader.ok == true` con `stages.reader.source == "stacky_dpapi"`. Hoy: BLOCKED en 5.9 s, siempre. Medible: F5.
- **KPI-3 — Cero URL `?q=` persistida:** `menu_resolver.sanitize_for_playbook` elimina el payload y marca `requires_live_menu`; ratchet `test_plan240_menu_resolver.py::test_ningun_playbook_persiste_q_param` sobre `cache/playbooks/*.json` → 0 hits de `?q=`. Hoy: nada lo impide.
- **KPI-4 — Cero falso PASS por 200-con-error:** `assert_arrival` sobre una pantalla que renderiza cuerpo de error devuelve `ok=False, code="APP_ERROR_PAGE"` (categoría `APP`). Verificable en test con fixture y **en vivo con `FrmJDemanda.aspx`**. Hoy: `assert_arrival` no existe, el status 200 se toma como llegada válida **y además** los patrones del detector existente no reconocen el título real (`"500-Error interno del servidor ."` matchea 0 de 7 — C4), así que el KPI exige **ambos** fixes: el cableado correcto (C3) y los patrones nuevos (C4).
- **KPI-5 — Cero PASS sin aserción funcional:** `build_functional_verdict` con `criteria_results == []` devuelve `verdict="MIXED", reason="NO_FUNCTIONAL_ASSERTION"`, **nunca** `PASS`. Hoy: un run sin aserciones sustantivas puede reportar PASS.
- **KPI-6 — Runtime auto-diagnosticado:** `GET /api/qa-uat/runtime-doctor` devuelve en un solo objeto binding Playwright, browser, AgendaWeb y credenciales, cada uno con `remediation` ejecutable. Hoy: el operador recibe diagnósticos contradictorios (H3).
- **KPI-7 — Evidencia re-verificable:** todo run escribe `evidence_manifest.json` y `verify_evidence_manifest(run_dir)` devuelve `ok=True` con `mismatches == []`. Hoy: no hay manifiesto ni forma de probar que la evidencia no cambió.
- **KPI-8 — Cero regresión:** con las 3 flags nuevas en su default y sin AgendaWeb, el comportamiento del pipeline es idéntico al de hoy salvo mensajes de diagnóstico más precisos y keys nuevas aditivas. Ningún test existente se rompe.

---

## 2. Por qué ahora / evidencia (todo ejecutado el 2026-07-25, no leído de memoria)

Cada hallazgo se reprodujo corriendo el código real. Rutas: tool = `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent`, backend = `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend`.

**H1 — El binding Python de Playwright no está y la detección miente.** `pip show playwright` en `backend/.venv` → *not found*; en `backend/venv` (py3.11) → *not found*. El pipeline corre **in-process en el backend** (`api/qa_uat.py:218-219` inserta el tool en `sys.path`; no hay subprocess), así que el intérprete del backend es el que necesita el binding. **Agravante:** el tool tiene un directorio propio `playwright/` (specs TS: `flows/ helpers/ smoke/ uat/`). Con el tool en `sys.path`, `importlib.util.find_spec("playwright")` **devuelve un ModuleSpec** (`_NamespacePath(['…\QA UAT Agent\playwright'])`) ⇒ cualquier chequeo de presencia por `find_spec` da falso positivo; el fallo real aparece recién en `from playwright.sync_api import …` → `ModuleNotFoundError: No module named 'playwright.sync_api'`.

**H2 — Falso negativo total de login.** `auth_session_factory.py:95` define `_POST_LOGIN_URL_RE = r"FrmAgenda|FrmMain"` y `:271` lo pasa como **string** a `page.wait_for_url(...)`. Playwright interpreta los strings planos como **glob**, no como regex ⇒ el wait nunca matchea, expira a los 25 s (`_LOGIN_WAIT_URL_TIMEOUT_MS`, `:100`), se toma la rama de fallo (`:277-285`) y se devuelve `AUTH_CREDENTIALS_INVALID` con el mensaje *"Login falló — sigue en …/FrmAgenda.aspx"* — donde `FrmAgenda.aspx` es **exactamente la pantalla post-login exitosa**. Reproducido: `elapsed_ms: 30094`, `reason: AUTH_CREDENTIALS_INVALID`. Con predicado callable (`lambda u: "frmlogin" not in u.lower()`) el mismo flujo da login **OK**, `title="Agenda Personal"`, ScriptManager presente. Es el **único** sitio con el bug: `navigation_driver.py:302` y `:403` ya usan lambda, y los 12 `diag_*.py` también.

**H3 — Dos diagnósticos contradictorios del mismo fallo.** La rama `except ImportError` de `_do_playwright_login` (`auth_session_factory.py:245-250`) hardcodea `"playwright no está instalado"` para **cualquier** ImportError, y aguas arriba `AUTH_NOT_AVAILABLE` se mapea a `human_action_required = "AgendaWeb no responde durante el login. Verificar que la aplicación está corriendo"`. Observado en vivo: un solo fallo produjo ambos mensajes a la vez ⇒ el operador persigue lo que no es.

**H4 — CAUSA RAÍZ del "se desvía al navegar": `?q=` encriptado por sesión.** La shell post-login tiene 64 links: **22** `__doPostBack` y **31** `.aspx`. Muchos menús llevan payload encriptado: `FrmAgenda.aspx?q=rh3wPkybH+atHWY9zjvV4w==`, `FrmReportes.aspx?q=…`, `FrmLiquidaciones.aspx?q=…`, `FrmInformes.aspx?q=…`, `FrmReporteOperativo.aspx?q=…`. **Deep-link sin `?q=` → redirect a `frmLogin.aspx`** (probado en `FrmReportes.aspx` y `FrmLiquidaciones.aspx`), **y ese redirect destruye la sesión**: en el barrido secuencial, todo lo visitado después del primer redirect también cayó a login (`FrmAsignarLote`, `FrmAdministrador`), mientras que en contexto limpio y visitadas temprano cargan perfecto (`title="Reasignación Manual de Lote"`, `"Administrador"`). Consecuencia dura: **un playbook/ui_map nunca debe persistir la URL con `?q=`**; la navegación debe resolver el `href` **en vivo desde el menú, por etiqueta visible**; y un redirect a login debe disparar **re-auth + reintento del paso**, no un fallo global de auth.

**H5 — Falso PASS: HTTP 200 con cuerpo de error 500.** `FrmJDemanda.aspx` responde **200** con `title="500-Error interno del servidor ."` y ese texto en el body. Cualquier aserción por status code da PASS falso. El tool ya tiene `screen_error_detector.py` (detectores de excepción ASP.NET/DOM, `:295-318`) pero **no está cableado** como gate de llegada.

**H6 — El reader no puede leer tickets (dos caminos de credencial ADO divergentes).** `uat_ticket_reader._DEFAULT_ADO_PATH` (`:43`) → `Stacky tools/ADO Manager/ado.py`, invocado por subprocess (`:324-346`). `ado.py` resuelve el PAT **solo** desde `ado-config.json` junto al script o `../PAT-ADO` (`:59-83`), ambos **texto plano** y **ninguno existe** ⇒ `"PAT no encontrado"`. Corrida real: `qa_uat_pipeline.py --ticket 367 --mode dry-run` → `{"ok":false,"verdict":"BLOCKED","category":"PIP","reason":"ado_error","failed_stage":"reader"}` en 5.9 s. Mientras tanto el store DPAPI de Stacky **funciona**: PAT en `backend/projects/RSPACIFICO/auth/ado_auth.json` (`pat_format: dpapi_*`), org `UbimiaPacifico`, proyecto `Strategist_Pacifico`; se leyeron **33 work items DONE** read-only con `services.ado_client.AdoClient`.

**H8 — Ruido de consola que tapa errores reales.** La pantalla post-login emite **14 errores de consola** (404 de recursos estáticos) en un run **sano**. Sin allowlist, cualquier aserción "consola sin errores" es un falso negativo permanente.

**H9 — El agente se declara incapaz de gestionar el runtime de AgendaWeb.** `environment_preflight.py:17-19` (docstring): *"QA UAT Agent NEVER manages the runtime of AgendaWeb. If the app is not running, the correct action is to return BLOCKED and ask the operator to start it manually."* Con la app caída **todo** el pipeline es BLOCKED ⇒ no existe validación autónoma post-desarrollo. Probado que es arrancable determinísticamente: IIS Express (`C:\Program Files\IIS Express\iisexpress.exe`) + `N:\GIT\RS\RSPACIFICO\trunk\OnLine\Soluciones\.vs\AgendaWeb\config\applicationhost.config`, sitio `AgendaWeb-Site` (binding `*:35017:localhost`, app `/AgendaWeb` → `physicalPath N:\GIT\RS\RSPACIFICO\trunk\OnLine\AgendaWeb`) ⇒ `http://localhost:35017/AgendaWeb/` responde **200** y `FrmLogin.aspx` **200**.

**Sano y reusable (NO tocar):** `environment_preflight.run_environment_preflight()` funciona (`ok=True`, `PREFLIGHT_PASS`, 2.8 s). Trampa de lectura documentada: `to_pipeline_dict()` hardcodea `"ok": False` **por diseño** (es el dict de respuesta BLOCKED) — no es un bug, pero quien lo use en el camino de éxito concluye lo contrario; F0 agrega el comentario que lo aclara. 8 pantallas alcanzables por URL directa con sesión válida: `FrmAgenda`, `FrmBusqueda`, `FrmDetalleClie`, `FrmAgendaEquipo`, `FrmAgendaJudicial`, `FrmBusquedaJudicial`, `FrmGestionFlujos`, `Default`.

---

## 3. Principios y guardarraíles (NO negociables, codificados en las fases)

- **G1 · Reusar, no reescribir.** Cero reemplazo de módulos. Solo: 7 archivos nuevos pequeños en el tool, ediciones quirúrgicas en 5 archivos existentes, y wiring backend aditivo.
- **G2 · Human-in-the-loop innegociable.** Publicar en ADO sigue exigiendo `mode="publish"` explícito del operador (flujo existente + `check_run_publish_policy`, `api/qa_uat.py:462`). Este plan **no abre ninguna salida externa nueva**: el bridge ADO de F5 es **solo lectura** (`get_work_item`, `fetch_comments`, `fetch_attachments`) y lo declara en su docstring y en un test.
- **G3 · Determinista-primero, cero LLM en el núcleo.** Guard, login, menu resolver, arrival, bridge, veredicto funcional y manifiesto son Python determinista ⇒ idénticos en los 3 runtimes. La extracción de criterios (F6) es **regex/heurística determinista**; el enriquecimiento por LLM queda fuera de scope.
- **G4 · Paridad 3 runtimes con fallback explícito por ítem.** Cada fase declara su impacto y fallback. El fallback universal es el pipeline determinista, que no depende de ningún LLM.
- **G5 · Cero trabajo extra al operador.** Todo automático u opt-in default **ON**, con **una** excepción citada: `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` default **OFF** por **EXCEPCIÓN DURA #3** (prerequisito no garantizado en instalación default: IIS Express instalado + `applicationhost.config` del cliente + solución compilada).
- **G6 · Mono-operador sin auth real.** Cero RBAC.
- **G7 · No degradar.** El guard de F0 cuesta un import + un `stat` (no lanza browser). El launcher de F2 solo actúa si el preflight ya falló por `APP_NOT_RUNNING` **y** la flag está ON. El manifiesto de F7 es un walk del directorio de evidencia al final del run.
- **G8 · Config del operador vía UI.** Las 3 flags nuevas van a `harness_flags.py` ⇒ visibles/toggleables en Configuración → Arnés. Cero env-var-only.
- **G9 · Gotchas duros del repo (obligatorios).** Leer flags SIEMPRE de la instancia `config.config` (el módulo devuelve el default y mata el branch OFF); todo `backend/tests/test_*.py` nuevo se registra en `HARNESS_TEST_FILES` (`run_harness_tests.sh` **y** `.ps1`) o el meta-ratchet queda rojo; tests SIEMPRE por archivo (contaminación cross-run conocida); venv py3.13 (`Stacky Agents/backend/.venv`); NO hand-editar `harness_defaults.env`; commits con **pathspec explícito** (árbol compartido con sesión paralela viva).
- **G10 · Nada de red nueva fuera de localhost.** El launcher rechaza cualquier `base_url` cuyo host no sea `localhost`/`127.0.0.1`. El bridge ADO habla con el mismo endpoint que Stacky ya usa.

---

## 4. Nomenclatura fija (usar EXACTAMENTE estos nombres)

**Módulos nuevos del tool** (todos bajo `Stacky tools/QA UAT Agent/`):
- `browser_runtime_guard.py` — funciones `check_browser_runtime(probe_launch: bool = False) -> dict`, `_detect_shadowing() -> str | None`.
- `agenda_web_launcher.py` — funciones `ensure_agenda_web(*, base_url: str | None = None, timeout_s: int = 60) -> dict`, `stop_agenda_web(handle: dict) -> dict`, `_resolve_iisexpress() -> str | None`, `_resolve_apphost_config() -> str | None`.
- `menu_resolver.py` — funciones `normalize_label(raw: str) -> str`, `harvest_menu_sync(page) -> list[dict]`, `harvest_menu_js() -> str`, `resolve_target(menu: list[dict], wanted: str) -> dict | None`, `sanitize_for_playbook(entry: dict) -> dict`, `is_login_redirect(url: str) -> bool`.
- `console_noise_policy.py` — funciones `is_ignorable_console_error(text: str) -> bool`, `classify_console(messages: list[str]) -> dict`.
- `stacky_ado_bridge.py` — funciones `bridge_available() -> bool`, `fetch_work_item(ticket_id: int) -> dict`, `fetch_comments(ticket_id: int, top: int = 20) -> dict`.
- `acceptance_extractor.py` — función `extract_acceptance(work_item: dict) -> dict`.
- `functional_verdict.py` — función `build_functional_verdict(criteria_results: list[dict], technical: dict) -> dict`.
- `evidence_manifest.py` — funciones `build_evidence_manifest(run_dir) -> dict`, `verify_evidence_manifest(run_dir) -> dict`.

**Códigos de error nuevos (strings exactos):** `BROWSER_RUNTIME_MISSING`, `PLAYWRIGHT_SHADOWED_BY_TOOL_DIR`, `APP_ERROR_PAGE`, `NAV_SESSION_LOST`, `MENU_LABEL_NOT_FOUND`, `NO_FUNCTIONAL_ASSERTION`.

**Flags (3):**
- `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` (bool, default **False** — EXCEPCIÓN DURA #3, categoría `calidad_verificacion`).
- `STACKY_QA_UAT_ADO_BRIDGE_ENABLED` (bool, default **True**, categoría `calidad_verificacion`).
- `STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED` (bool, default **True**, categoría `calidad_verificacion`).

**Endpoint nuevo (read-only):** `GET /api/qa-uat/runtime-doctor`.

**Comandos de test canónicos (usar tal cual):**
```powershell
# Tool QA UAT (pytest POR ARCHIVO; el conftest.py de la raíz del tool resuelve sys.path y fuerza STACKY_LLM_BACKEND=mock)
cd "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent"
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\unit\<archivo> -q

# Backend Stacky (pytest POR ARCHIVO)
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q
```
**Registro de ratchet:** SOLO `backend/tests/test_plan240_*.py` van en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`). Los tests del tool (`Stacky tools/QA UAT Agent/tests/…`) **NO** se registran ahí (viven fuera de `backend/tests/`).

---

## 5. Paridad de runtimes (tabla normativa)

| Runtime | Mecanismo | Fallback |
|---|---|---|
| Claude Code CLI | Agente `backend/Stacky/agents/QAUat1.agent.md` (F3 le agrega la regla dura "menú vivo, jamás sintetizar `?q=`") | Pipeline determinista vía `POST /api/qa-uat/run` |
| Codex CLI | `api/qa_browser.py` + `services/qa_browser_plan.py` (sin cambios en este plan) | Pipeline determinista vía `POST /api/qa-uat/run` |
| GitHub Copilot Pro | **Directo al fallback universal:** `qa_uat_pipeline.py` determinista (ninguna etapa obligatoria usa LLM) | — (es el fallback) |

Los 7 módulos nuevos son Python determinista dentro del pipeline ⇒ los 3 runtimes se benefician idéntico, sin código por-runtime.

---

## 6. Fases

> Orden de dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8**. F5 (bridge ADO) es independiente de F1-F4 y puede adelantarse si se quiere ver el pipeline pasar el reader antes que nada. F6 depende de F5 (necesita el work item leído). F7 y F8 cierran.

---

### F0 — Guard de runtime veraz: el fin del diagnóstico contradictorio (H1, H3)

**Objetivo (1 frase):** que el agente sepa y diga con precisión si puede abrir un navegador, antes de intentar nada, y que un ImportError nunca se disfrace de "AgendaWeb no responde".

**Valor:** hoy el operador recibe dos causas contradictorias para un solo fallo y persigue la equivocada. Y la trampa del directorio `playwright/` hace que cualquier chequeo por `find_spec` reporte "instalado" cuando no lo está.

**Archivo a CREAR: `Stacky tools/QA UAT Agent/browser_runtime_guard.py`**
```python
"""browser_runtime_guard.py — Guard veraz del runtime de navegador (Plan 240 F0).

REGLA DURA: la presencia del binding se prueba SIEMPRE con un import real de
playwright.sync_api, JAMAS con importlib.util.find_spec("playwright").
Motivo (H1): este tool tiene un directorio propio llamado "playwright/" (specs TS).
Con el tool en sys.path, find_spec("playwright") devuelve un ModuleSpec de
namespace package apuntando a ESE directorio => reporta "instalado" cuando no lo esta.
"""
from __future__ import annotations
import os, sys
from pathlib import Path

_TOOL_ROOT = Path(__file__).resolve().parent
_PIP_HINT = 'pip install "playwright>=1.44.0" && python -m playwright install chromium'


def _detect_shadowing() -> str | None:
    """Devuelve la ruta del directorio que enmascara al paquete, o None.
    No importa nada: solo mira el filesystem y sys.path."""
    for entry in [str(_TOOL_ROOT)] + list(sys.path):
        try:
            cand = Path(entry) / "playwright"
        except Exception:
            continue
        if cand.is_dir() and not (cand / "__init__.py").is_file():
            return str(cand)
    return None


def check_browser_runtime(probe_launch: bool = False) -> dict:
    """Chequea binding + browser. NUNCA lanza. Nunca abre red.

    Retorna dict con keys FIJAS:
      ok (bool), binding_ok (bool), browser_ok (bool|None),
      code (str: "" | "BROWSER_RUNTIME_MISSING" | "PLAYWRIGHT_SHADOWED_BY_TOOL_DIR"),
      binding_version (str|None), executable_path (str|None),
      shadowed_by (str|None), remediation (str), detail (str)
    probe_launch=False: heurístico — NO lanza browser, valida por filesystem AMBOS
      ejecutables (ver _headless_shell_path abajo). probe_launch=True: lanza y cierra
      chromium headless — es el ÚNICO chequeo autoritativo.
    (C12) POR QUÉ AMBAS RUTAS: pw.chromium.executable_path devuelve el Chrome HEADED
      (…\\chromium-<rev>\\chrome-win64\\chrome.exe), pero launch(headless=True) usa el
      HEADLESS SHELL (…\\chromium_headless_shell-<rev>\\chrome-headless-shell-win64\\
      chrome-headless-shell.exe) — son ejecutables DISTINTOS (probado 2026-07-25).
      Un stat solo de executable_path da OK MIENTRAS el launch falla: ese fue
      literalmente el error original ("Executable doesn't exist at
      …chromium_headless_shell-1228…"). browser_ok exige que existan LAS DOS.
    """

def _headless_shell_path(executable_path: str) -> str | None:
    """Deriva la ruta del headless shell desde la del Chrome headed (C12).
    Reemplaza en el path: el componente 'chromium-<rev>' por
    'chromium_headless_shell-<rev>', 'chrome-win64' por 'chrome-headless-shell-win64'
    y el archivo 'chrome.exe' por 'chrome-headless-shell.exe'.
    Devuelve None si el patrón no matchea (otra plataforma/otro layout): en ese caso
    browser_ok se decide solo por executable_path y `detail` lo declara."""
    shadowed = _detect_shadowing()
    try:
        from playwright.sync_api import sync_playwright  # import REAL, no find_spec
    except Exception as exc:
        code = "PLAYWRIGHT_SHADOWED_BY_TOOL_DIR" if shadowed else "BROWSER_RUNTIME_MISSING"
        return {"ok": False, "binding_ok": False, "browser_ok": None, "code": code,
                "binding_version": None, "executable_path": None, "shadowed_by": shadowed,
                "remediation": _PIP_HINT,
                "detail": f"{type(exc).__name__}: {exc}"}   # H3: el texto REAL, no un hardcode
    version = None
    try:
        import playwright as _pw
        version = getattr(_pw, "__version__", None)
    except Exception:
        pass
    exe, browser_ok, detail = None, False, ""
    try:
        with sync_playwright() as pw:
            exe = pw.chromium.executable_path
            browser_ok = bool(exe) and Path(exe).is_file()
            if probe_launch and browser_ok:
                b = pw.chromium.launch(headless=True)
                try:
                    browser_ok = True
                finally:
                    b.close()
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        browser_ok = False
    if not browser_ok:
        return {"ok": False, "binding_ok": True, "browser_ok": False,
                "code": "BROWSER_RUNTIME_MISSING", "binding_version": version,
                "executable_path": exe, "shadowed_by": shadowed,
                "remediation": "python -m playwright install chromium",
                "detail": detail or f"executable no encontrado: {exe}"}
    return {"ok": True, "binding_ok": True, "browser_ok": True, "code": "",
            "binding_version": version, "executable_path": exe,
            "shadowed_by": shadowed, "remediation": "", "detail": ""}
```
CLI en el mismo archivo: `--report` imprime el JSON de `check_browser_runtime()`; `--probe` usa `probe_launch=True`. Exit 0 si `ok`, 1 si no.

**Archivos a EDITAR:**
1. `Stacky tools/QA UAT Agent/environment_preflight.py`:
   - Agregar **Check 0** al inicio de `run_environment_preflight` (ANTES del check de credenciales, `:140`), porque sin binding no hay nada que probar:
     ```python
     # ── Check 0: runtime de navegador (Plan 240 F0) ───────────────────────────
     try:
         from browser_runtime_guard import check_browser_runtime
         # (C12) probe_launch=True: el stat es heurístico y puede dar falso OK
         # (headed vs headless-shell). Un launch+close cuesta ~1 s UNA vez por run y
         # evita un fallo de 25 s más tarde con diagnóstico peor.
         guard = check_browser_runtime(probe_launch=True)
     except Exception:
         guard = {"ok": True}          # el guard nunca puede bloquear por su propio fallo
     if not guard.get("ok", True):
         return EnvironmentPreflightResult(
             ok=False, verdict="BLOCKED", reason=guard.get("code") or "BROWSER_RUNTIME_MISSING",
             message=(f"Runtime de navegador no disponible: {guard.get('detail','')}. "
                      f"Remediacion: {guard.get('remediation','')}"),
             base_url=base_url, login_url=login_url,
             elapsed_ms=int((time.time() - started) * 1000),
         )
     ```
   - Corregir el docstring del módulo (`:17-19`): reemplazar la frase absoluta *"QA UAT Agent NEVER manages the runtime of AgendaWeb"* por: *"Por default QA UAT Agent NO gestiona el runtime de AgendaWeb (devuelve BLOCKED/APP_NOT_RUNNING). Con `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` ON el pipeline puede intentar UN arranque local acotado (Plan 240 F2, agenda_web_launcher)."*
   - Agregar a `to_pipeline_dict` (`:93`) el comentario aclaratorio: `# OJO: "ok" es False a proposito — este dict es la RESPUESTA BLOCKED del pipeline. Para el camino de exito leer result.ok, no este dict (trampa de lectura, Plan 240 §2).`
2. `Stacky tools/QA UAT Agent/auth_session_factory.py`:
   - `_do_playwright_login`, rama `except ImportError` (`:245-250`): reemplazar el mensaje hardcodeado por el guard real:
     ```python
     except ImportError as exc:
         try:
             from browser_runtime_guard import check_browser_runtime
             g = check_browser_runtime()
             return {"ok": False, "reason": g.get("code") or "AUTH_NOT_AVAILABLE",
                     "error": f"{g.get('detail') or exc} — remediacion: {g.get('remediation','')}"}
         except Exception:
             return {"ok": False, "reason": "AUTH_NOT_AVAILABLE", "error": f"{type(exc).__name__}: {exc}"}
     ```
   - En `run_auth_session`, donde se arma `human_action_required` para `AUTH_NOT_AVAILABLE` (localizar con `grep -n "AgendaWeb no responde durante el login" auth_session_factory.py`; **no adivinar la línea**): hacer el mensaje **dependiente del reason**: si el reason es `BROWSER_RUNTIME_MISSING` o `PLAYWRIGHT_SHADOWED_BY_TOOL_DIR` → usar el `remediation` del guard; si es `AUTH_NOT_AVAILABLE` → conservar el texto actual sobre AgendaWeb. Prohibido dejar dos causas para un mismo fallo.

**Tests (TDD — escribir ANTES): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_browser_runtime_guard.py`**
- `test_guard_ok_en_este_entorno`: `check_browser_runtime()` → `ok is True`, `binding_ok is True`, `browser_ok is True`, `code == ""` (el venv ya tiene binding+chromium).
- `test_detecta_shadowing_del_directorio_del_tool`: `_detect_shadowing()` → string no vacío terminando en `playwright` (el directorio de specs TS existe en la raíz del tool).
- `test_guard_sin_binding_no_lanza_y_da_remediacion`: monkeypatch de `builtins.__import__` para que `playwright.sync_api` lance `ImportError` → `ok is False`, `binding_ok is False`, `code in ("BROWSER_RUNTIME_MISSING","PLAYWRIGHT_SHADOWED_BY_TOOL_DIR")`, `"pip install" in remediation`, `detail` contiene `ImportError` (H3: el texto real, no un hardcode).
- `test_keys_del_contrato_siempre_presentes`: las 10 keys fijas existen en ambos caminos (ok y no-ok).
- `test_headless_shell_path_derivada` (**C12**): `_headless_shell_path(r"C:\x\ms-playwright\chromium-1228\chrome-win64\chrome.exe")` → termina en `chromium_headless_shell-1228\chrome-headless-shell-win64\chrome-headless-shell.exe`; con un path que no matchea el patrón → `None`.
- `test_browser_ok_falso_si_falta_el_headless_shell` (**C12, el test del falso positivo**): monkeypatch para que `executable_path` exista pero la ruta derivada del headless shell **no** → `browser_ok is False`, `code == "BROWSER_RUNTIME_MISSING"`, `remediation` contiene `playwright install`.
- `test_preflight_bloquea_sin_browser`: monkeypatch de `browser_runtime_guard.check_browser_runtime` → `{"ok": False, "code": "BROWSER_RUNTIME_MISSING", "detail": "x", "remediation": "y"}`; `run_environment_preflight()` → `ok is False`, `verdict == "BLOCKED"`, `reason == "BROWSER_RUNTIME_MISSING"`, y **no** hizo ninguna request HTTP (spy sobre `_http_get` → 0 llamadas).

**Criterio de aceptación (binario):**
- `& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\unit\test_plan240_browser_runtime_guard.py -q` → **5/5**.
- `& "…python.exe" browser_runtime_guard.py --report` → exit 0 y JSON con `"ok": true`.
- `grep -c "find_spec" browser_runtime_guard.py` → **0** (la regla dura es no usarlo).
- Regresión: `& "…python.exe" -m pytest tests\unit\test_environment_preflight.py -q` → verde (si el archivo no existiera, usar `grep -rl "environment_preflight" tests\unit` y correr los que aparezcan, por archivo).

**Flag:** ninguna — es diagnóstico veraz de algo que hoy miente; sin él el resto no se puede depurar. Backward-safe: si el guard falla por su cuenta, `guard = {"ok": True}` y el preflight sigue exactamente como hoy.
**Impacto por runtime:** los 3 idéntico (guard determinista en el pipeline). Fallback: guard indisponible → comportamiento actual.
**Trabajo del operador:** ninguno.

---

### F1 — Fin del falso negativo de login: predicado en vez de glob (H2)

**Objetivo (1 frase):** que un login exitoso se reporte como exitoso, en <5 s en vez de 30 s, y que ningún `wait_for_url` del tool vuelva a pasar un regex como string.

**Valor:** es **el** bloqueante de superficie: hoy el 100% de los logins se reportan `AUTH_CREDENTIALS_INVALID` aunque funcionen, así que ninguna validación E2E puede empezar.

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/auth_session_factory.py`**
1. Junto a `_POST_LOGIN_URL_RE` (`:95`) AGREGAR (sin borrar la constante vieja: `_dry_run_verify` la reporta en `:379`):
   ```python
   import re   # si no está ya importado arriba
   _POST_LOGIN_URL_PATTERN = re.compile(_POST_LOGIN_URL_RE, re.IGNORECASE)

   def _is_post_login_url(url: str) -> bool:
       """True si la URL ya NO es el login. Predicado CALLABLE a propósito:
       Playwright trata los strings planos de wait_for_url como GLOB, no como regex
       (Plan 240 H2) — pasar r"FrmAgenda|FrmMain" hacía expirar SIEMPRE el wait."""
       u = (url or "").lower()
       if "frmlogin" in u:
           return False
       return True
   ```
2. `:271` — reemplazar:
   ```python
   # ANTES (bug H2: string => glob => timeout siempre):
   page.wait_for_url(_POST_LOGIN_URL_RE, timeout=_LOGIN_WAIT_URL_TIMEOUT_MS)
   # DESPUES:
   page.wait_for_url(lambda u: _is_post_login_url(u), timeout=_LOGIN_WAIT_URL_TIMEOUT_MS)
   ```
   `login_succeeded` (`:273`) queda como está (`"frmlogin" not in page.url.lower()`), ahora coherente con el wait.
3. Enriquecer el retorno de éxito (`:309`) con la pantalla de aterrizaje, para que el falso negativo sea imposible de repetir a ciegas:
   ```python
   return {"ok": True, "reason": "AUTH_LOGIN_OK", "error": None,
           "landing_url": page.url,
           "landing_title": (page.title() or "")[:120],
           "post_login_matched": bool(_POST_LOGIN_URL_PATTERN.search(page.url or ""))}
   ```
   Propagar `landing_url` y `landing_title` a `AuthSessionResult` como **campos nuevos con default `None`** (dataclass, `:109`) y a `to_dict()`. Aditivo: ningún consumidor existente se rompie por keys nuevas.
4. En la rama de fallo (`:277-285`), el mensaje debe distinguir los dos casos reales:
   ```python
   still_login = "frmlogin" in page.url.lower()
   return {"ok": False,
           "reason": "AUTH_CREDENTIALS_INVALID" if still_login else "AUTH_POST_LOGIN_UNRECOGNIZED",
           "error": (f"Login rechazado — sigue en {page.url}." if still_login
                     else f"Login aparentemente OK pero la pantalla de aterrizaje no es reconocible: {page.url}")}
   ```
   Motivo: "no reconozco dónde aterricé" **no es** "credenciales inválidas". El código `AUTH_POST_LOGIN_UNRECOGNIZED` es nuevo y debe agregarse donde el módulo enumere sus reasons (buscar con `grep -n "AUTH_CREDENTIALS_INVALID" auth_session_factory.py` y replicar el patrón; si hay un set/tupla de reasons, sumarlo ahí).

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_login_url_predicate.py`**
- `test_predicado_reconoce_frmagenda`: `_is_post_login_url("http://h/AgendaWeb/FrmAgenda.aspx")` → True; `_is_post_login_url("http://h/AgendaWeb/frmLogin.aspx")` → False (case-insensitive, la app redirige con `f` minúscula — verificado en vivo).
- `test_wait_for_url_recibe_callable`: fake page cuyo `wait_for_url` registra el tipo del primer argumento; correr `_do_playwright_login` con un `sync_playwright` fake → el argumento es **callable**, no `str`. Este test es el ratchet del bug.
- `test_login_ok_devuelve_landing`: fake page con `url` = `.../FrmAgenda.aspx` y `title()` = `"Agenda Personal"` → `ok is True`, `reason == "AUTH_LOGIN_OK"`, `landing_url` contiene `FrmAgenda.aspx`, `landing_title == "Agenda Personal"`.
- `test_sigue_en_login_es_credenciales_invalidas`: fake page que queda en `frmLogin.aspx` → `reason == "AUTH_CREDENTIALS_INVALID"`.
- `test_aterrizaje_desconocido_no_es_credenciales`: fake page que queda en `.../FrmOtra.aspx` tras timeout del wait → `reason == "AUTH_POST_LOGIN_UNRECOGNIZED"` (**no** `AUTH_CREDENTIALS_INVALID`).
- `test_ratchet_ningun_wait_for_url_con_string_literal`: escanear **todos** los `*.py` del tool (excluyendo `node_modules`, `_attic`) y verificar que ninguna llamada `wait_for_url(` tenga como primer argumento un literal de string ni un `_RE`/`_PATTERN` sin envolver en lambda. Implementación obligatoria **por AST** (`ast.parse` + `ast.walk` buscando `ast.Call` con `func.attr == "wait_for_url"` y `args[0]` de tipo `ast.Constant(str)`), **jamás por regex** (memoria `gotcha-flag-binding-regex-destructivo`: un centinela textual sobre código es destructivo). Hoy este test da 1 hit (`auth_session_factory.py:271`) y debe quedar en **0**.

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_login_url_predicate.py -q` → **6/6**.
- `grep -n "wait_for_url(_POST_LOGIN_URL_RE" auth_session_factory.py` → **0 hits**.
- **Verificación en vivo (obligatoria, requiere AgendaWeb arriba):** `run_auth_session(mode="normal")` → `ok True`, `reason "AUTH_LOGIN_OK"`, `elapsed_ms < 15000`, `landing_url` con `FrmAgenda.aspx`. Pegar la salida real en el reporte de implementación.
- Regresión: `& "…python.exe" -m pytest tests\unit\test_auth_session_factory.py -q` → verde (si no existe ese archivo, `grep -rl "auth_session" tests\unit` y correr los que aparezcan, por archivo).

**Flag:** ninguna — es la corrección de un bug que produce un falso negativo del 100%. Poner una flag sería mantener el bug activable.
**Impacto por runtime:** los 3 idéntico. Fallback: ninguno necesario (el camino corregido es estrictamente mejor).
**Trabajo del operador:** ninguno.

---

### F2 — Arrancador local acotado de AgendaWeb: el fin del BLOCKED por app caída (H9)

**Objetivo (1 frase):** que, con la flag ON, el pipeline pueda levantar AgendaWeb en local una sola vez, verificarlo por HTTP y apagarlo al terminar si fue él quien lo arrancó.

**Valor:** hoy, con la app caída, el 100% de los runs son BLOCKED y no existe validación autónoma post-desarrollo. Probado que el arranque es determinista (H9).

**Archivo a CREAR: `Stacky tools/QA UAT Agent/agenda_web_launcher.py`**
```python
"""agenda_web_launcher.py — Arranque local ACOTADO de AgendaWeb (Plan 240 F2).

Guardarraíles NO negociables (todos verificados antes de ejecutar nada):
  1. SOLO localhost: si el host de base_url no es localhost/127.0.0.1 => rechaza.
  2. SOLO si el ejecutable de IIS Express y el applicationhost.config EXISTEN.
  3. Idempotente: si AgendaWeb ya responde => no arranca nada y NUNCA lo apaga
     (started_by_us=False). Solo se apaga lo que este módulo arrancó.
  4. Un intento, con timeout. Cero reintentos infinitos, cero polling eterno.
  5. Jamás en deploy/frozen: si la variable STACKY_DEPLOY_MODE esta seteada o
     el ejecutable corre congelado (sys.frozen), rechaza.
"""
_DEFAULT_SITE = "AgendaWeb-Site"
_APPPOOL = "Clr4IntegratedAppPool"
_IIS_CANDIDATES = (r"C:\Program Files\IIS Express\iisexpress.exe",
                   r"C:\Program Files (x86)\IIS Express\iisexpress.exe")

def _resolve_iisexpress() -> str | None:
    """QA_UAT_IISEXPRESS_EXE si está y existe; si no, el primer candidato estándar que exista."""

def _resolve_apphost_config() -> str | None:
    """QA_UAT_AGENDA_APPHOST_CONFIG si está y existe; si no, None.
    NO adivina rutas de clientes: el operador la configura una vez por env/flag UI."""

def ensure_agenda_web(*, base_url: str | None = None, timeout_s: int = 60) -> dict:
    """Retorna dict con keys FIJAS:
      ok(bool), already_running(bool), started_by_us(bool), pid(int|None),
      code(str: "" | "AUTOSTART_DISABLED" | "NOT_LOCALHOST" | "IISEXPRESS_NOT_FOUND"
                | "APPHOST_CONFIG_NOT_FOUND" | "START_TIMEOUT" | "START_FAILED" | "DEPLOY_MODE"),
      base_url(str), detail(str), remediation(str)
    Pasos: (1) leer flag por env STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED (el pipeline
    ya la exporta; ver F8) -> si OFF: ok=False, code="AUTOSTART_DISABLED" (NO es error,
    es el default). (2) validar host local. (3) HTTP GET a base_url: si responde con
    un status de _ALIVE_STATUS_CODES de environment_preflight => ok=True,
    already_running=True, started_by_us=False. (4) resolver exe+config. (5) subprocess.Popen
    con /config:<cfg> /site:<site> /apppool:Clr4IntegratedAppPool, sin shell, stdout/stderr a
    <tool>/evidence/_runtime/iisexpress.log. (6) poll HTTP cada 1 s hasta timeout_s;
    éxito => ok=True, started_by_us=True, pid=proc.pid; timeout => matar el proceso que
    arrancamos y devolver code="START_TIMEOUT". NUNCA lanza."""

def stop_agenda_web(handle: dict) -> dict:
    """Apaga SOLO si handle.get("started_by_us") is True y hay pid.
    terminate() y, si sigue vivo a los 5 s, kill(). Retorna {"ok":bool,"stopped":bool,"detail":str}.
    Con started_by_us False => {"ok":True,"stopped":False,"detail":"no lo arrancamos nosotros"}."""
```

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/qa_uat_pipeline.py`**
- **(C13) Flag alcanzable desde la CLI.** El launcher lee `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` de `os.environ`, pero esa variable la exporta el backend en `_run_pipeline_in_background` (F8). Corriendo el pipeline **desde la CLI** —que es exactamente cómo se hacen las verificaciones en vivo del DoD y cómo depura el operador— nadie la exporta y el autostart quedaría **permanentemente `AUTOSTART_DISABLED`**. Por lo tanto, agregar al `argparse` del pipeline:
  ```python
  parser.add_argument("--autostart", action="store_true",
                      help="Intenta arrancar AgendaWeb local si no responde (Plan 240 F2). "
                           "Equivale a la flag STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED de la UI.")
  # ... y al procesar args, ANTES del stage de preflight:
  if args.autostart:
      os.environ["STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"] = "true"
  ```
  Regla: el flag de CLI **solo puede activar**, nunca desactivar lo que la UI dejó en ON (sin `--autostart` la variable no se toca, así que el valor exportado por el backend manda).
- En el stage de preflight (`:400-424`), cuando el resultado sea `ok=False` **y** `reason == "APP_NOT_RUNNING"`: **un** intento de autostart y **un** re-preflight:
  ```python
  agenda_handle = {"started_by_us": False}
  if not pre.ok and pre.reason == "APP_NOT_RUNNING":
      try:
          from agenda_web_launcher import ensure_agenda_web
          agenda_handle = ensure_agenda_web(base_url=pre.base_url)
          if agenda_handle.get("ok"):
              pre = run_environment_preflight()          # UN re-preflight, no un loop
      except Exception:
          logger.debug("autostart AgendaWeb no disponible", exc_info=True)
  ```
  Registrar en el dict de stages: `stages["preflight"]["autostart"] = {k: agenda_handle.get(k) for k in ("ok","already_running","started_by_us","code")}`.
- Al final del run (en el `finally` del orquestador, o inmediatamente antes de construir el JSON de salida si no hay `finally`; **localizar con `grep -n "finally\|def run(" qa_uat_pipeline.py`, no adivinar**): `stop_agenda_web(agenda_handle)` envuelto en `try/except`. Regla: **nunca** apagar lo que no arrancamos.

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_agenda_launcher.py`**
- `test_flag_off_es_no_op`: sin la env var → `ok is False`, `code == "AUTOSTART_DISABLED"`, y `subprocess.Popen` **no** fue llamado (spy).
- `test_rechaza_host_no_local`: flag ON + `base_url="http://10.0.0.5/AgendaWeb/"` → `code == "NOT_LOCALHOST"`, Popen 0 llamadas.
- `test_ya_corriendo_no_arranca_ni_apaga`: flag ON + fake HTTP 200 → `ok True`, `already_running True`, `started_by_us False`; `stop_agenda_web(res)` → `stopped is False`.
- `test_exe_faltante`: flag ON + monkeypatch `_resolve_iisexpress` → None → `code == "IISEXPRESS_NOT_FOUND"` con `remediation` no vacía.
- `test_config_faltante`: flag ON + exe fake presente + `_resolve_apphost_config` → None → `code == "APPHOST_CONFIG_NOT_FOUND"`.
- `test_timeout_mata_lo_que_arranco`: flag ON, exe/config fake, HTTP siempre falla, `timeout_s=1` → `code == "START_TIMEOUT"` y el fake proc recibió `terminate()`.
- `test_stop_solo_lo_propio`: `stop_agenda_web({"started_by_us": True, "pid": <fake>})` → `stopped True`; con `started_by_us False` → `stopped False`.
- `test_deploy_mode_rechaza`: flag ON + `STACKY_DEPLOY_MODE=1` → `code == "DEPLOY_MODE"`, Popen 0 llamadas.

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_agenda_launcher.py -q` → **8/8**.
- `grep -c "shell=True" agenda_web_launcher.py` → **0** (sin shell: evita inyección por rutas con espacios).
- `grep -c "started_by_us" agenda_web_launcher.py` → **≥4**.
- Regresión: `& "…python.exe" -m pytest tests\unit\test_qa_uat_pipeline.py -q` → verde (si el nombre difiere, `ls tests\unit | grep -i pipeline` y correr los que aparezcan, por archivo).

**Flag:** `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` default **OFF** por **EXCEPCIÓN DURA #3** (prerequisito no garantizado en instalación default: IIS Express instalado + `applicationhost.config` del cliente + solución compilada). Con OFF el comportamiento es **byte-idéntico** al de hoy (BLOCKED/APP_NOT_RUNNING).
**Impacto por runtime:** los 3 idéntico (vive en el pipeline). Fallback: flag OFF o prerequisito ausente → BLOCKED honesto con `remediation`, como hoy.
**Trabajo del operador:** ninguno con el default. Activarlo es un toggle en Configuración → Arnés + una ruta de `applicationhost.config` (dos campos, una vez).

---

### F3 — Navegación por menú vivo: el fin de las URLs `?q=` y del falso NAV_AUTH_EXPIRED (H4)

**Objetivo (1 frase):** que la navegación resuelva el `href` real **en vivo desde el menú de la shell por etiqueta visible**, que jamás persista un `?q=` en un playbook, y que un redirect a login sea `NAV_SESSION_LOST` con re-auth + reintento en vez de un fallo global de auth.

**Valor:** es la **causa raíz** del "se desvía al navegar" (H4). Sin esto, cualquier playbook con URL guardada envenena la sesión y cascada falsos `NAV_AUTH_EXPIRED` en todos los pasos siguientes.

**Archivo a CREAR: `Stacky tools/QA UAT Agent/menu_resolver.py`**
```python
"""menu_resolver.py — Resolución de navegación por el menú VIVO (Plan 240 F3).

REGLA DURA (H4): AgendaWeb usa URLs con ?q= ENCRIPTADO POR SESIÓN
(p.ej. FrmReportes.aspx?q=TdbfUQQM9SQ5...). Deep-linkear una de esas SIN el ?q=
redirige a frmLogin.aspx Y ESE REDIRECT DESTRUYE LA SESIÓN, cascando falsos
NAV_AUTH_EXPIRED en todos los pasos siguientes. Por lo tanto:
  - NUNCA se sintetiza una URL con ?q=.
  - NUNCA se persiste un href con ?q= en un playbook/ui_map.
  - El destino se resuelve clickeando el ANCLA REAL del menú, por etiqueta visible.
"""
import re, unicodedata
from urllib.parse import urlsplit, parse_qs

_ICON_LIGATURE_RE = re.compile(r"^[a-z_]+(?=[A-ZÁÉÍÓÚÑ])")   # "switch_accountReasignacion" -> "Reasignacion"

def normalize_label(raw: str) -> str:
    """Normaliza una etiqueta de menú para comparar.
    Pasos EXACTOS, en este orden:
      1. Reemplazar \n y \t por espacio; colapsar espacios; strip.
      2. Quitar el token de icono Material: si el texto arranca con un run de
         [a-z_]+ pegado a una mayúscula (ligature de Material Icons), eliminarlo.
         Casos reales verificados: "event\nAgenda Personal" -> "Agenda Personal";
         "switch_accountReasignacion Manual" -> "Reasignacion Manual";
         "searchFiltrar" -> "Filtrar"; "grid_on\nAGENDADOS POR USUARIO" -> "AGENDADOS POR USUARIO".
      3. Quitar acentos (NFKD + drop de combinantes).
      4. lower() y colapsar espacios de nuevo.
    """

def harvest_menu_js() -> str:
    """Devuelve el JS (string) que se pasa a page.evaluate() para cosechar el menú.
    Extrae de TODOS los <a>: text (innerText o title), href crudo (getAttribute, NO .href
    resuelto), id. No filtra: el filtrado es Python puro y testeable."""

def harvest_menu_sync(page) -> list[dict]:
    """Cosecha el menú de la página ACTUAL. NUNCA lanza (ante error devuelve []).
    Cada item: {"label": <crudo>, "label_norm": normalize_label(label),
                "href": <crudo>, "id": <str>,
                "kind": "postback"|"aspx"|"other",
                "screen": "<FrmX.aspx>"|None, "has_q_param": bool}
    kind: "postback" si '__doPostBack' in href; "aspx" si '.aspx' in href.lower(); si no "other".
    screen: nombre de archivo .aspx del path (sin query), preservando el case del href.
    has_q_param: True si parse_qs(urlsplit(href).query) tiene la clave 'q'."""

def resolve_target(menu: list[dict], wanted: str) -> dict | None:
    """Resuelve por precedencia EXACTA (primera que matchea gana):
      1. screen == wanted (case-insensitive) — p.ej. wanted="FrmBusqueda.aspx".
      2. label_norm == normalize_label(wanted) — igualdad exacta de etiqueta.
      3. label_norm empieza con normalize_label(wanted).
      4. normalize_label(wanted) contenido en label_norm.
    Empate en el mismo nivel: gana el de menor índice (orden del DOM), determinista.
    Sin match => None (el caller emite MENU_LABEL_NOT_FOUND)."""

def sanitize_for_playbook(entry: dict) -> dict:
    """Devuelve una copia SEGURA de persistir: si has_q_param, elimina la query
    entera de 'href' (queda solo el path) y agrega requires_live_menu=True +
    resolve_by = entry['label_norm'] (así el playbook dice CÓMO volver a resolverlo).
    Si no hay ?q=, requires_live_menu=False y el href se conserva tal cual."""

def is_login_redirect(url: str) -> bool:
    """True si la URL es la pantalla de login (case-insensitive: la app redirige
    a 'frmLogin.aspx' con f minúscula — verificado en vivo)."""
    return "frmlogin" in (url or "").lower()
```

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/navigation_driver.py`**
1. NUEVO método `via_menu`, modelado sobre `via_link_click` (`:280`) — **no reescribirlo, agregarlo al lado**:
   ```python
   async def via_menu(self, wanted: str, timeout_ms: int = _DEFAULT_TIMEOUT_MS,
                      retries: int = _DEFAULT_RETRIES,
                      screenshot_prefix: str = "menu") -> NavigationResult:
       """Navega resolviendo el ancla REAL del menú vivo (Plan 240 F3).
       1) menu = menu_resolver.harvest_menu_sync(self.page)  (via evaluate)
       2) target = menu_resolver.resolve_target(menu, wanted)
          None => NavigationResult(ok=False, error_code="MENU_LABEL_NOT_FOUND",
                  error_detail=f"wanted={wanted} candidatos={[m['label_norm'] for m in menu][:20]}")
       3) locator por id si target['id'] else por texto exacto del ancla
       4) click(no_wait_after=True)  +  await wait_aspnet_idle(self.page, min(timeout_ms, 5000))  (F4)
       5) si is_login_redirect(self.page.url) => error_code="NAV_SESSION_LOST" (NO NAV_AUTH_EXPIRED)
       6) arrival = await self.assert_arrival(target['screen'] or wanted)  (F4)
       NUNCA sintetiza URL. NUNCA usa target['href'] con ?q= para un page.goto."""
   ```
2. En `_classify_error` (`:496`): agregar ramas **antes** de las genéricas, en este orden:
   - texto contiene `"NAV_SESSION_LOST"` → `"NAV_SESSION_LOST"`.
   - texto contiene `"MENU_LABEL_NOT_FOUND"` → `"MENU_LABEL_NOT_FOUND"`.
   - texto contiene `"APP_ERROR_PAGE"` → `"APP_ERROR_PAGE"` (F4).
   La rama existente `NAV_AUTH_EXPIRED` se conserva **pero deja de disparar por un redirect a login dentro de un paso**: ese caso ahora es `NAV_SESSION_LOST`. Diferencia semántica obligatoria: `NAV_AUTH_EXPIRED` = la sesión venció por tiempo; `NAV_SESSION_LOST` = la app nos expulsó **por navegar mal** (deep-link sin `?q=`) y es **recuperable con re-auth + reintento del paso**.
3. **Re-auth ASYNC (C1 — el v1 estaba roto).** **PROHIBIDO** llamar `run_auth_session` desde `via_menu`: usa `sync_playwright` (`auth_session_factory.py:244,:258`) y Playwright **lanza** si se invoca la Sync API dentro de un event loop asyncio (*"It looks like you are using Playwright Sync API inside the asyncio loop"*, `playwright/sync_api/_context_manager.py:48`). `NavigationDriver` es **async** (7 `async def`). Por lo tanto se AGREGA a `auth_session_factory.py` un helper **async** nuevo, que reusa las constantes de selectores ya existentes (`_LOGIN_USER_SEL:92`, `_LOGIN_PASS_SEL:93`, `_LOGIN_BTN_SEL:94`) y el predicado de F1:
   ```python
   async def reauth_in_page(page, *, base_url: str | None = None) -> dict:
       """Re-login sobre una página ASYNC ya existente (Plan 240 F3, C1).
       NO usa sync_playwright: es seguro llamarlo desde código async.
       Lee las credenciales con _read_credentials(None) (ya existente, :149).
       Pasos: goto(base_url + "FrmLogin.aspx", wait_until="domcontentloaded")
              -> fill user/pass -> click(_LOGIN_BTN_SEL, no_wait_after=True)
              -> await page.wait_for_url(lambda u: _is_post_login_url(u), timeout=25000)
       Retorna {"ok": bool, "reason": str, "landing_url": str|None}. NUNCA lanza.
       NO escribe storage_state: la sesión vive en el contexto async en curso."""
   ```
   **(C2) De dónde sale `base_url`:** `NavigationDriver` **no lo tiene** — su constructor es `__init__(self, page, evidence_dir=None, scenario_id="nav")` (`navigation_driver.py:218-225`) y `grep -c "base_url" navigation_driver.py` → **0**. Se resuelve con la fuente única ya declarada, por import LAZY dentro del método (sin tocar la firma del constructor):
   ```python
   from environment_preflight import get_agenda_base_url   # :68, fuente única de verdad
   base = get_agenda_base_url()
   ```
   En el bucle de retries de `via_menu` (y **solo** ahí), si `error_code == "NAV_SESSION_LOST"` y quedan intentos: `await reauth_in_page(self.page, base_url=base)` y luego `await self.page.goto(base, wait_until="domcontentloaded")` para volver a la shell y re-cosechar el menú. `MAX` de re-auths por paso: **1** (constante de módulo `_MAX_REAUTH_PER_STEP = 1`); sin esa cota un bucle de expulsión reintentaría indefinidamente.

**Archivo a EDITAR: `Stacky Agents/backend/Stacky/agents/QAUat1.agent.md`** — agregar (regla de corrección, no de estilo; bump de versión en el frontmatter):
```markdown
## NAVEGACIÓN: MENÚ VIVO, JAMÁS URLs SINTETIZADAS (regla dura)
AgendaWeb usa URLs con `?q=` ENCRIPTADO POR SESIÓN (ej: `FrmReportes.aspx?q=TdbfUQ…`).
1. NUNCA construyas ni reutilices una URL con `?q=`: deep-linkearla redirige a `frmLogin.aspx`
   Y ESE REDIRECT DESTRUYE LA SESIÓN, haciendo fallar todos los pasos siguientes.
2. Para ir a una pantalla: cosechá los `<a>` del menú de la página actual y clickeá el
   ANCLA REAL por su etiqueta visible. Las etiquetas traen un prefijo de icono Material
   pegado (`switch_accountReasignacion Manual`) — normalizá antes de comparar.
3. Si terminás en `frmLogin.aspx` en medio de un flujo, NO lo reportes como "sesión vencida":
   es expulsión por navegación inválida. Re-autenticá UNA vez y reintentá ese paso.
4. Estas 8 pantallas SÍ son alcanzables por URL directa con sesión válida (verificado):
   FrmAgenda, FrmBusqueda, FrmDetalleClie, FrmAgendaEquipo, FrmAgendaJudicial,
   FrmBusquedaJudicial, FrmGestionFlujos, Default. Para cualquier otra: menú vivo.
```

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_menu_resolver.py`**
- `test_normalize_label_casos_reales`: los 4 casos verificados en vivo (`"event\nAgenda Personal"`→`"agenda personal"`, `"switch_accountReasignacion Manual"`→`"reasignacion manual"`, `"searchFiltrar"`→`"filtrar"`, `"grid_on\nAGENDADOS POR USUARIO"`→`"agendados por usuario"`).
- `test_harvest_clasifica_kind_y_q`: fake page cuyo `evaluate` devuelve 3 links (`__doPostBack('x','')`, `/AgendaWeb/FrmBusqueda.aspx`, `/AgendaWeb/FrmReportes.aspx?q=ABC==`) → kinds `postback|aspx|aspx`, `has_q_param` `False|False|True`, `screen` `None|"FrmBusqueda.aspx"|"FrmReportes.aspx"`.
- `test_harvest_no_lanza_si_evaluate_falla`: `evaluate` lanza → `[]`.
- `test_resolve_precedencia`: menú con un item `screen="FrmBusqueda.aspx"` y otro con `label_norm="busqueda de clientes"`; `resolve_target(menu,"FrmBusqueda.aspx")` → el de screen; `resolve_target(menu,"Búsqueda de Clientes")` → el de label (acentos ignorados); `resolve_target(menu,"Nada")` → None.
- `test_resolve_empate_gana_el_primero`: dos items con el mismo `label_norm` → devuelve el de índice menor.
- `test_sanitize_elimina_q_y_marca`: entry con `?q=ABC==` → `href` sin query, `requires_live_menu is True`, `resolve_by == label_norm`; entry sin `q` → `requires_live_menu is False` y href intacto.
- `test_is_login_redirect_case_insensitive`: `"…/frmLogin.aspx"` y `"…/FRMLOGIN.ASPX"` → True; `"…/FrmAgenda.aspx"` → False.
- `test_ningun_playbook_persiste_q_param` (**ratchet, KPI-3**): recorrer `cache/playbooks/*.json` y `cache/ui_maps/*.json` del tool; ningún valor de string debe contener `"?q="`. Hoy pasa (1 playbook, sin `?q=`); el test impide la regresión cuando la KB crezca (214 F1).
- `test_classify_error_nuevos_codigos`: `_classify_error("NAV_SESSION_LOST: …", "http://x")` → `"NAV_SESSION_LOST"`; ídem `MENU_LABEL_NOT_FOUND` y `APP_ERROR_PAGE`.
- `test_via_menu_no_encontrado_no_navega`: driver con fake page cuyo menú no contiene el target → `NavigationResult.ok is False`, `error_code == "MENU_LABEL_NOT_FOUND"`, y `page.goto` **0 llamadas** (spy) — jamás sintetiza URL.

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_menu_resolver.py -q` → **10/10**.
- `grep -c "NAV_SESSION_LOST" navigation_driver.py menu_resolver.py` → **≥1 en cada uno**.
- `grep -c "def via_menu" navigation_driver.py` → **1**.
- `grep -n "MENÚ VIVO, JAMÁS URLs SINTETIZADAS" "Stacky Agents/backend/Stacky/agents/QAUat1.agent.md"` → **1**.
- Regresión: `& "…python.exe" -m pytest tests\unit\test_navigation_driver.py -q` y `tests\unit\test_navigation_plan_gate.py -q` → verdes.

**Flag:** ninguna — `via_menu` es un método **nuevo** (nada lo llamaba antes, cero riesgo de regresión) y los códigos nuevos son aditivos al contrato de `_classify_error`. La única semántica que cambia es que un redirect a login dentro de un paso pasa de `NAV_AUTH_EXPIRED` a `NAV_SESSION_LOST`: es la **corrección de una clasificación errónea**, no un cambio de comportamiento a gatear.
**Impacto por runtime:** pipeline (Codex/Copilot/Claude fallback) usa `via_menu`; Claude agéntico recibe la misma regla por prompt. Fallback: si el menú viene vacío, `via_menu` falla con `MENU_LABEL_NOT_FOUND` explícito en vez de navegar a ciegas.
**Trabajo del operador:** ninguno.

---

### F4 — Llegada verificada: idle ASP.NET + error en el cuerpo + ruido de consola (H5, H8)

**Objetivo (1 frase):** que cada paso confirme que llegó a la pantalla correcta **y que esa pantalla no es una página de error**, y que los 404 de recursos estáticos nunca produzcan un falso negativo.

**Valor:** mata las dos caras del engaño: el **falso PASS** de `FrmJDemanda.aspx` (HTTP 200 con cuerpo "500-Error interno del servidor", H5) y el **falso FAIL** por los 14 errores 404 de consola que emite un run sano (H8).

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/navigation_driver.py`**
1. Helper module-level nuevo (antes de `class NavigationDriver`, ~`:206`) — **esto materializa el `wait_aspnet_idle` del 214 F2**:
   ```python
   _ASPNET_IDLE_JS = """
   () => {
     if (document.readyState !== 'complete') return false;
     try {
       const prm = window.Sys && window.Sys.WebForms
         && window.Sys.WebForms.PageRequestManager
         && window.Sys.WebForms.PageRequestManager.getInstance();
       if (prm && prm.get_isInAsyncPostBack()) return false;
     } catch (e) { /* sin ScriptManager => no hay async postback */ }
     return true;
   }
   """

   async def wait_aspnet_idle(page, timeout_ms: int = 3000) -> bool:
       """Espera corta a que ASP.NET quede idle (readyState + PageRequestManager).
       Poll cada 100 ms. True=idle, False=timeout. NUNCA lanza.
       Verificado en vivo: la shell de AgendaWeb SÍ tiene ScriptManager."""
       import asyncio, time
       deadline = time.monotonic() + (timeout_ms / 1000.0)
       while time.monotonic() < deadline:
           try:
               if await page.evaluate(_ASPNET_IDLE_JS):
                   return True
           except Exception:
               pass          # navegación en curso: evaluate puede fallar transitoriamente
           await asyncio.sleep(0.1)
       return False
   ```
2. En `via_link_click`: el `await locator.click()` de `:300` pasa a `await locator.click(no_wait_after=True)` y **inmediatamente después** `await wait_aspnet_idle(self.page, min(timeout_ms, 5000))`, ANTES del `wait_for_url` existente de `:301`. El atributo real es **`self.page`** (`:224`) y `timeout_ms` es **parámetro local** del método (`:284`) — no existen `self._page` ni `self._timeout_ms`.
3. Método nuevo `assert_arrival` (**supera al del 214 F2**: agrega el gate de página de error):
   ```python
   async def assert_arrival(self, expected_screen: str) -> dict:
       """Valida por DOM que estamos en expected_screen Y que no es página de error.
       Retorna {"ok": bool, "code": str, "deviation": str|None, "screen": str}.
       ORDEN OBLIGATORIO (el gate de error va PRIMERO — H5):
       1) Página de error (C3 — cableado corregido). NO llamar
          render_aspnet_exception_detector_js()/render_dom_detector_js(): esas funciones
          devuelven una DEFINICIÓN de función TS que recibe `page` y llama page.evaluate
          ella misma (screen_error_detector.py:255-256,:295,:302), pensada para incrustarse
          en un .spec.ts; pasarla a page.evaluate desde Python FALLA.
          Camino correcto: reusar las CONSTANTES Python del mismo módulo (import lazy)
            from screen_error_detector import (ASPNET_EXCEPTION_TITLE_PATTERNS,   # :171
                                               DOM_ERROR_SELECTORS,              # :92
                                               DOM_ERROR_TEXT_PATTERNS)          # :131
          y un evaluate propio y mínimo:
            snap = await self.page.evaluate(
                "() => ({title: document.title || '',"
                " body: (document.body && document.body.innerText || '').slice(0, 4000),"
                " url: window.location.href || ''})")
          Detecta error si: (a) algún patrón de ASPNET_EXCEPTION_TITLE_PATTERNS está
          (case-insensitive) en snap['title']; (b) algún patrón de DOM_ERROR_TEXT_PATTERNS
          está en snap['body']; (c) snap['url'] contiene 'errors.aspx' o 'aspxerrorpath';
          (d) algún selector de DOM_ERROR_SELECTORS tiene count() > 0.
          Si detecta => {"ok": False, "code": "APP_ERROR_PAGE",
                         "deviation": <title + primeros 160 chars del body>}.
       2) Expulsión: si menu_resolver.is_login_redirect(url) =>
          {"ok": False, "code": "NAV_SESSION_LOST", ...}
       3) Llegada por ui_map: cache/ui_maps/{expected_screen}.json, primer elemento con
          'id'; self.page.locator(f"#{el_id}").count() > 0 => ok.
       4) Fallback sin ui_map: expected_screen (sin extensión) contenido en la URL actual.
       5) Ninguna => {"ok": False, "code": "NAV_DEVIATION",
                      "deviation": f"expected={expected_screen} url={url}"}.
       NUNCA lanza; ante error de I/O usa el fallback por URL. Un ok=False SIEMPRE
       saca screenshot con self._screenshot (:482) como evidencia."""
   ```
   **Regla anti-falso-PASS (dura):** el chequeo de página de error corre **antes** que el de llegada. Una pantalla que "llegó" pero muestra error es `APP_ERROR_PAGE` (categoría `APP` = bug real del desarrollo), **nunca** un PASS.

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/screen_error_detector.py` — [ADICIÓN ARQUITECTO] (C4), sin esto KPI-4 es inalcanzable**

Los patrones de título del detector **no reconocen la página de error real de AgendaWeb**. Probado el 2026-07-25: el título de `FrmJDemanda.aspx` es `"500-Error interno del servidor ."` y matchea **0 de los 7** patrones actuales de `ASPNET_EXCEPTION_TITLE_PATTERNS` (`:171`). AGREGAR a esa lista, al final (aditivo puro — el mismo array lo consume el JS del template, así que los specs generados también se benefician):
```python
    "Error interno del servidor",   # Plan 240 C4 — título REAL de la custom error page
                                    # de AgendaWeb, verificado en vivo:
                                    # FrmJDemanda.aspx => "500-Error interno del servidor ."
    "Error interno",                # variante sin la palabra "servidor"
```
**Regla dura:** NO reordenar ni editar las 7 entradas existentes (otros consumidores dependen de ellas); solo agregar al final. Cambio backward-compatible: agregar patrones solo puede detectar MÁS errores, nunca menos.

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/qa_uat_pipeline.py` — contador `nav_deviations` (C6, ítem traído del 214 F2)**

En el resumen del stage runner (donde se arma `stages["runner"]`; **localizar con `grep -n 'stages\["runner"\]' qa_uat_pipeline.py`, no adivinar la línea**), AGREGAR dos contadores derivados de los resultados del runner (0 si no hay ninguno):
- `nav_deviations`: cantidad de resultados cuya clase de error es `NAV_DEVIATION`.
- `app_error_pages`: cantidad con clase `APP_ERROR_PAGE`.
Aditivo puro: son keys nuevas en un dict existente; ningún consumidor actual se rompe. Habilita KPI-1 del Plan 214 sin que el 214 tenga que tocar este archivo.

**Archivo a CREAR: `Stacky tools/QA UAT Agent/console_noise_policy.py`**
```python
"""console_noise_policy.py — Allowlist de ruido de consola (Plan 240 F4, H8).

Un run SANO de AgendaWeb emite 14 errores de consola: 404 de recursos estáticos.
Sin esta política, cualquier aserción "consola sin errores" es un falso negativo
permanente. Determinista, sin red, sin estado.
"""
_IGNORABLE_PATTERNS = (
    "failed to load resource",          # 404/403 de assets
    "net::err_aborted",                 # navegación cancelada por postback
    "favicon",
)
_IGNORABLE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2",
                         ".ttf", ".eot", ".ico", ".map", ".css")

def is_ignorable_console_error(text: str) -> bool:
    """True si el mensaje es ruido conocido de assets. Case-insensitive.
    NO ignora: excepciones JS reales, errores de ScriptManager/PageRequestManager,
    'Sys.WebForms', 'Uncaught', 'is not defined', 'Input string was not in a correct
    format' (patrón real de los AJAX rotos de los tickets 364/375)."""

def classify_console(messages: list[str]) -> dict:
    """{"ignored": [...], "significant": [...], "ignored_count": int,
        "significant_count": int}. Nunca lanza; None/no-str se saltean."""
```
**Regla dura:** la lista de significativos incluye **siempre** los patrones que delatan los bugs de este dominio (`"Sys.WebForms"`, `"Uncaught"`, `"is not defined"`, `"Input string was not in a correct format"`); si un mensaje matchea a la vez un patrón ignorable y uno significativo, **gana significativo**.

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_arrival_and_console.py`**
- `test_idle_inmediato`: fake page cuyo `evaluate` devuelve True → `wait_aspnet_idle` True en <300 ms.
- `test_idle_tras_polls`: `evaluate` devuelve False, False, True → True.
- `test_idle_timeout_false`: siempre False, `timeout_ms=300` → False, no lanza.
- `test_idle_evaluate_lanza_no_rompe`: `evaluate` lanza siempre → False (no propaga).
- `test_arrival_pagina_de_error_gana_al_ui_map` (**el test clave de H5**): fake page con el `id` del ui_map presente **y** `title` = `"500-Error interno del servidor ."` → `ok False`, `code == "APP_ERROR_PAGE"` (el gate de error corre primero; con el orden invertido daría PASS falso).
- `test_arrival_ok_por_ui_map`: ui_map tmp con elemento `id="btnGuardar"`, locator count 1, body limpio → `ok True`.
- `test_arrival_desvio`: locator count 0, URL sin la pantalla → `ok False`, `code == "NAV_DEVIATION"`, `deviation` contiene `expected=`.
- `test_arrival_login_redirect_es_session_lost`: URL `frmLogin.aspx` → `code == "NAV_SESSION_LOST"`.
- `test_arrival_sin_ui_map_fallback_por_url`: sin ui_map, URL contiene la pantalla → `ok True`.
- `test_console_ignora_404_de_assets`: los 3 mensajes reales del run sano → todos en `ignored`.
- `test_console_no_ignora_excepcion_js`: `"Uncaught TypeError: x is not a function"` y `"Sys.WebForms.PageRequestManagerServerErrorException"` → `significant`.
- `test_console_significativo_gana_el_empate`: `"Failed to load resource … Sys.WebForms"` → `significant`.
- `test_console_ignora_no_strings`: `[None, 3, "favicon 404"]` → no lanza, `ignored_count == 1`.
- `test_detector_reconoce_el_titulo_real` (**C4, el test que hace alcanzable KPI-4**): importar `ASPNET_EXCEPTION_TITLE_PATTERNS` y verificar que **al menos un patrón** matchea (case-insensitive) el título real verificado en vivo `"500-Error interno del servidor ."`. Hoy este test **falla** (0 de 7 patrones matchean) y con el fix pasa. Escribirlo ANTES del fix.
- `test_no_se_reordenaron_los_patrones_existentes`: los 7 patrones originales siguen presentes y en el mismo orden relativo (anti-regresión de otros consumidores).

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_arrival_and_console.py -q` → **15/15**.
- `grep -c "no_wait_after=True" navigation_driver.py` → **≥1**.
- `grep -c "APP_ERROR_PAGE" navigation_driver.py` → **≥1**.
- `grep -c "def assert_arrival" navigation_driver.py` → **1**.
- `grep -c "Error interno del servidor" screen_error_detector.py` → **≥1** (C4).
- `grep -c "nav_deviations" qa_uat_pipeline.py` → **≥1** (C6).
- Regresión por el cambio de patrones: `& "…python.exe" -m pytest tests\unit\test_screen_error_detector.py -q` → verde (si el nombre difiere, `ls tests\unit | grep -i error` y correr los que aparezcan, por archivo).
- **Verificación en vivo (requiere AgendaWeb arriba):** `assert_arrival("FrmJDemanda.aspx")` estando en esa pantalla → `code == "APP_ERROR_PAGE"`. Pegar la salida real.
- Regresión: `tests\unit\test_navigation_driver.py` → verde.

**Flag:** ninguna — `wait_aspnet_idle` devuelve True casi inmediato en páginas sin ScriptManager (backward-safe) y `assert_arrival` es un método nuevo. La política de consola solo se consume donde antes no había política (nada se vuelve más estricto sin querer).
**Impacto por runtime:** los 3 idéntico. Fallback: sin `screen_error_detector` disponible, `assert_arrival` usa la regex de body/title (declarada arriba).
**Trabajo del operador:** ninguno.

---

### F5 — Reader de tickets sobre el store DPAPI de Stacky: el fin del PAT en texto plano (H6)

**Objetivo (1 frase):** que el pipeline lea el work item con las credenciales que Stacky ya tiene (DPAPI), y que el CLI legacy quede solo como fallback.

**Valor:** desbloquea el **primer stage** del pipeline, que hoy muere siempre (`BLOCKED/PIP/ado_error`), y **elimina el requisito de un PAT en texto plano** (mejora de seguridad, no solo de wiring).

**Archivo a CREAR: `Stacky tools/QA UAT Agent/stacky_ado_bridge.py`**
```python
"""stacky_ado_bridge.py — Puente SOLO-LECTURA al cliente ADO de Stacky (Plan 240 F5).

Por qué existe (H6): uat_ticket_reader invoca `Stacky tools/ADO Manager/ado.py`, que
resuelve el PAT solo desde ado-config.json / PAT-ADO EN TEXTO PLANO (ado.py:59-83) y
ninguno existe => el pipeline muere en el stage reader. Stacky ya tiene el PAT
cifrado con DPAPI en backend/projects/<proyecto>/auth/ado_auth.json y funciona.

ALCANCE DURO: SOLO LECTURA. Este módulo no expone NINGÚN método de escritura de
AdoClient — ni creación de work items, ni publicación de comentarios, ni cambio de
estados, ni subida de adjuntos. El HITL de publicación (G2) queda intacto.

(C11) El docstring evita a propósito escribir los nombres literales de los métodos
de escritura: el criterio de aceptación de esta fase es un grep de esos literales
con resultado 0, y nombrarlos aquí haría fallar el gate contra su propio autor.
"""
from pathlib import Path
import sys

_TOOL_ROOT = Path(__file__).resolve().parent
# tool = <repo>/Stacky tools/QA UAT Agent  =>  backend = <repo>/Stacky Agents/backend
_BACKEND = _TOOL_ROOT.parent.parent / "Stacky Agents" / "backend"

_READ_ONLY_METHODS = frozenset({"get_work_item", "fetch_comments", "fetch_attachments"})

def _ensure_backend_on_path() -> bool:
    if not _BACKEND.is_dir():
        return False
    p = str(_BACKEND)
    if p not in sys.path:
        sys.path.insert(0, p)
    return True

def bridge_available() -> bool:
    """True si el backend es importable Y hay PAT presente. NUNCA lanza."""
    try:
        if not _ensure_backend_on_path():
            return False
        from services.ado_client import ado_pat_present
        return bool(ado_pat_present())
    except Exception:
        return False

# (C14) Lista EXPLÍCITA de campos: get_work_item(ado_id, fields=None) usa por default
# una lista hardcodeada de 7 campos (ado_client.py:868-871) que NO incluye
# System.Description. Probado: sin esta lista, Description vuelve VACÍO (0 chars) y el
# extractor de criterios de F6 no tiene nada que leer => todo run daría
# MIXED/NO_FUNCTIONAL_ASSERTION. Con la lista, el 367 devuelve 12.622 chars.
# Verificado también que ADO NO devuelve 400 si un campo no existe para ese tipo de
# work item: simplemente lo omite del dict (se piden 11, vuelven 9).
_WORK_ITEM_FIELDS = [
    "System.Id", "System.Title", "System.State", "System.WorkItemType",
    "System.Parent", "System.AssignedTo", "System.ChangedDate", "System.Tags",
    "System.Description",
    "Microsoft.VSTS.Common.AcceptanceCriteria",   # no existe en este proyecto: se omite solo
    "Microsoft.VSTS.TCM.ReproSteps",              # idem
]

def fetch_work_item(ticket_id: int) -> dict:
    """{"ok": bool, "work_item": dict|None, "source": "stacky_dpapi",
        "error": str|None, "message": str|None}
    Devuelve el work item con el MISMO shape que ado.py get (dict con 'id' y 'fields'),
    para que uat_ticket_reader lo consuma sin cambios de forma.
    OBLIGATORIO: llamar get_work_item(ticket_id, fields=_WORK_ITEM_FIELDS) — jamás sin
    fields (C14). NUNCA lanza."""

def fetch_comments(ticket_id: int, top: int = 20) -> dict:
    """{"ok": bool, "comments": list, "source": "stacky_dpapi", "error": str|None}. NUNCA lanza."""
```

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/uat_ticket_reader.py`**
- En `_ado_get` (`:349`) y `_ado_comments`: intentar el bridge PRIMERO y caer al CLI si no está. Patrón exacto (aplicar a ambos):
  ```python
  def _ado_get(ado_path: Path, ticket_id: int) -> dict:
      import os
      if os.environ.get("STACKY_QA_UAT_ADO_BRIDGE_ENABLED", "true").lower() in ("1", "true", "yes"):
          try:
              from stacky_ado_bridge import bridge_available, fetch_work_item
              if bridge_available():
                  res = fetch_work_item(ticket_id)
                  if res.get("ok"):
                      return res            # incluye source="stacky_dpapi"
          except Exception:
              pass                          # fallback silencioso al CLI legacy
      out = _ado_run(ado_path, ["get", str(ticket_id)])   # camino ACTUAL, intacto
      out.setdefault("source", "ado_cli")
      return out
  ```
- En el dict del stage `reader` que devuelve `run(...)`, propagar `source` (`"stacky_dpapi"` | `"ado_cli"`) para que KPI-2 sea verificable leyendo el JSON de salida.

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_ado_bridge.py`**
- `test_backend_path_resuelto`: `_BACKEND` termina en `Stacky Agents\backend` y `is_dir()` es True en este árbol.
- `test_bridge_available_true_aqui`: `bridge_available()` → True (PAT DPAPI presente, verificado).
- `test_bridge_solo_lectura`: `_READ_ONLY_METHODS` contiene exactamente `{"get_work_item","fetch_comments","fetch_attachments"}`; y el propio módulo, leído como texto por el test, no contiene ninguno de los 4 nombres de escritura (el test los construye por concatenación de fragmentos — p. ej. `"create_" + "work_item"` — para no introducirlos él mismo como literales y colisionar con el mismo gate, C11). **Este test es el guardián de G2.**
- `test_fetch_work_item_shape`: monkeypatch de `AdoClient.get_work_item` → dict con `id`/`fields` → `ok True`, `source == "stacky_dpapi"`, `work_item["id"]` correcto.
- `test_fetch_no_lanza_si_ado_falla`: monkeypatch que lanza → `ok False`, `error` no vacío, sin excepción.
- `test_reader_usa_bridge_primero`: spy sobre `_ado_run` (el CLI) + bridge fake que devuelve ok → `_ado_run` **0 llamadas**, resultado con `source == "stacky_dpapi"`.
- `test_reader_cae_al_cli_si_bridge_no_disponible`: `bridge_available` → False + spy sobre `_ado_run` → **1 llamada**, `source == "ado_cli"` (backward-compat estricta).
- `test_reader_flag_off_usa_cli`: `STACKY_QA_UAT_ADO_BRIDGE_ENABLED=false` → `_ado_run` 1 llamada, bridge 0.

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_ado_bridge.py -q` → **8/8**.
- `grep -cE "create_work_item|post_comment|update_work_item_state|upload_attachment" stacky_ado_bridge.py` → **0**.
- **Verificación en vivo (KPI-2):** `& "…python.exe" qa_uat_pipeline.py --ticket 367 --mode dry-run` → el JSON de salida tiene `stages.reader.ok == true` y `stages.reader.source == "stacky_dpapi"` (hoy: `BLOCKED/PIP/ado_error`). Pegar la salida real.
- Regresión: `& "…python.exe" -m pytest tests\unit\test_uat_ticket_reader.py -q` → verde.

**Flag:** `STACKY_QA_UAT_ADO_BRIDGE_ENABLED` default **ON**. Ninguna excepción dura aplica: es **solo lectura**, usa credenciales que el operador ya configuró para Stacky, no abre ninguna salida nueva, y ante cualquier fallo cae al camino actual. Con la flag OFF el comportamiento es byte-idéntico al de hoy.
**Impacto por runtime:** los 3 idéntico (el reader es del pipeline). Fallback explícito: bridge no disponible → CLI legacy → si el CLI no tiene PAT, el mismo BLOCKED honesto de hoy.
**Trabajo del operador:** ninguno — desaparece el paso manual de crear un `ado-config.json` con el PAT en texto plano.

---

### F6 — Veredicto funcional: criterios de aceptación y prohibición del PASS vacío

**Objetivo (1 frase):** convertir "no hubo error técnico" en "los criterios de aceptación del ticket se verificaron", y hacer **imposible** un PASS sin ninguna aserción funcional verificada.

**Valor:** cierra el pedido central del operador ("verifica el resultado funcional, no solo la ausencia de errores técnicos") y mata el falso positivo más caro: el run verde que no probó nada.

**Archivo a CREAR: `Stacky tools/QA UAT Agent/acceptance_extractor.py`**
```python
"""acceptance_extractor.py — Criterios de aceptación testeables (Plan 240 F6).
100% DETERMINISTA (regex + heurísticas del dominio RS). Cero LLM => idéntico en los 3 runtimes.
"""
_SCREEN_RE = r"\b(Frm[A-Za-z]+)\.aspx\b"
# Sinónimos funcionales -> pantalla, verificados contra la app real:
_SCREEN_HINTS = {
    "busqueda de clientes": "FrmBusqueda.aspx", "detalle de cliente": "FrmDetalleClie.aspx",
    "agenda personal": "FrmAgenda.aspx", "agenda de grupo": "FrmAgendaEquipo.aspx",
    "reasignacion manual": "FrmAsignarLote.aspx", "agenda judicial": "FrmAgendaJudicial.aspx",
    "busqueda judicial": "FrmBusquedaJudicial.aspx",
}
# Tipos de criterio reconocidos, con el patrón que los delata:
#   "maxlength"  -> MaxLength=NN / longitud maxima / se trunca / truncamiento
#   "presence"   -> debe mostrar(se) / debe aparecer / se visualiza / no aparece / ausente / falta
#   "absence"    -> duplicad(a|o) / repetid(a|o) / no debe aparecer
#   "ordering"   -> orden(ado|amiento) / ordenar por / de mayor a menor / por fecha
#   "value"      -> debe ser / igual a / muestra 0 / debe indicar / calcula
#   "catalog"    -> catalogo / lista desplegable / combo / debe incluir
#   "color"      -> color / rojo / verde / chip / semaforo
#   "no_error"   -> error ajax / input string was not in a correct format / excepcion


# (C15) PARSEO ESTRUCTURAL, no heurístico. Verificado el 2026-07-25 en los tickets
# 367, 366, 57 y 61: System.Description trae SIEMPRE esta estructura canónica de
# headings h1-h6 (SIN acentos), y los ítems son <li>:
_CANONICAL_SECTIONS = (
    "RESUMEN EJECUTIVO", "CONTEXTO DE NEGOCIO", "ANALISIS FUNCIONAL",
    "ANALISIS TECNICO", "PASOS DE REPRODUCCION", "CRITERIOS DE ACEPTACION",
    "ARCHIVOS Y MODULOS PROBABLES", "EPICA RELACIONADA", "PRIORIDAD Y ESTIMACION",
)
# El campo Microsoft.VSTS.Common.AcceptanceCriteria NO EXISTE en este proyecto
# (0 chars en los 4 tickets sondeados, ausente del dump de 25 campos): los criterios
# viven dentro de System.Description bajo el heading "CRITERIOS DE ACEPTACION".

def split_sections(html: str) -> dict:
    """Parte el HTML por headings h1-h6 -> {HEADING_UPPER: html_del_bloque}.
    Implementación EXACTA: re.split(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, flags=re.I|re.S)
    y recorrer de dos en dos (heading, cuerpo).
    CASO BORDE PROBADO (ticket 367): la descripción DUPLICA todo el bloque de headings;
    gana SIEMPRE la PRIMERA aparición (if head not in out). El texto anterior al primer
    heading es preámbulo espurio (en el 367: "Ahora reviso la capa de negocio…", una
    frase de agente) y se DESCARTA. NUNCA lanza: ante error devuelve {}."""

def _li_items(block_html: str) -> list[str]:
    """Extrae los <li> de un bloque y los limpia: quita tags, resuelve &quot; &amp;
    &nbsp; &gt; &lt;, colapsa espacios. Si el bloque no tiene <li>, parte el texto plano
    por saltos de línea y descarta lo de menos de 4 palabras."""

def extract_acceptance(work_item: dict) -> dict:
    """Lee fields System.Title y System.Description (el único que trae contenido real).
    Devuelve:
      {"ok": True,
       "criteria": [{"id": "CA-01"|"AC-n", "text": <ítem completo>, "kind": <uno de los 8>,
                     "screen_hint": "FrmX.aspx"|None, "tokens": [<literales citados>],
                     "expected": <str|None>}],
       "repro_steps": [<texto de cada <li> de PASOS DE REPRODUCCION, en orden>],
       "screens": [<pantallas .aspx mencionadas, deduplicadas, orden de aparición>],
       "confidence": "high"|"medium"|"low",
       "sections_found": [<headings canónicos presentes>],
       "notes": [<supuestos declarados>]}
    Reglas EXACTAS:
      - secs = split_sections(description). Criterios = _li_items(secs["CRITERIOS DE
        ACEPTACION"]); repro_steps = _li_items(secs["PASOS DE REPRODUCCION"]).
      - id: si el ítem arranca con un prefijo tipo "CA-01:" / "CA-1 -" se usa ese id
        literal (verificado en el 367); si no, se genera "AC-<n>" por posición.
      - kind: primer patrón que matcha en el orden declarado arriba. Si ninguno matcha,
        el criterio SE CONSERVA con kind="assertion" (a diferencia del v2, que lo
        descartaba: un criterio explícito del ticket JAMÁS se tira — descartarlo
        inflaría el falso PASS que este plan viene a matar).
      - screen_hint: primer match de _SCREEN_RE en el ítem; si no hay, primer match en
        el título; si no, _SCREEN_HINTS por sinónimo funcional; si no, None.
      - expected: valor numérico o entrecomillado citado en el ítem
        (ej "admite hasta 50 caracteres" -> "50"; MaxLength=20 -> "20").
      - confidence: "high" si existe la sección CRITERIOS DE ACEPTACION con >=1 <li>;
        "medium" si hay descripción con secciones canónicas pero sin esa sección;
        "low" si no hay descripción (solo título).
      - Si NO hay sección de criterios, se cae al modo heurístico sobre ANALISIS
        FUNCIONAL + título (partir por [.;\\n], descartar <4 palabras) y confidence
        queda en "medium"/"low". Nunca se inventan criterios.
      - NUNCA lanza: ante cualquier error devuelve {"ok": True, "criteria": [],
        "repro_steps": [], "screens": [], "confidence": "low",
        "notes": ["extraction_failed: <detalle>"]}.
        Motivo: 0 criterios NO es un error, es una señal — F6 la convierte en MIXED, no en PASS.
    """
```

**Archivo a CREAR: `Stacky tools/QA UAT Agent/functional_verdict.py`**
```python
"""functional_verdict.py — Veredicto FUNCIONAL (Plan 240 F6).

REGLA DURA ANTI-FALSO-VERDE: un run sin NINGÚN criterio funcional verificado
NO puede ser PASS. Devuelve MIXED con reason NO_FUNCTIONAL_ASSERTION.
"""
_VERDICTS = ("PASS", "FAIL", "BLOCKED", "MIXED", "SKIPPED")   # espeja verdict_normalizer.VERDICT_SET

def build_functional_verdict(criteria_results: list[dict], technical: dict) -> dict:
    """criteria_results: [{"id","kind","status": "verified"|"violated"|"not_verifiable",
                          "evidence": str|None, "detail": str|None}]
    technical: dict del runner ya normalizado, al menos {"verdict": str, "category": str|None}

    Precedencia EXACTA (primera que aplica gana):
      1. technical["verdict"] == "BLOCKED"            -> BLOCKED (entorno; no se juzga lo funcional)
      2. any(status == "violated")                    -> FAIL,  reason "ACCEPTANCE_VIOLATED",
                                                        category "APP"
      3. technical["verdict"] == "FAIL"               -> FAIL,  reason "TECHNICAL_FAILURE"
      4. verified_count == 0                          -> MIXED, reason "NO_FUNCTIONAL_ASSERTION"
                                                        (aunque lo técnico sea PASS — KPI-5)
      5. any(status == "not_verifiable")               -> MIXED, reason "PARTIAL_COVERAGE"
      6. else                                          -> PASS,  reason "ACCEPTANCE_MET"

    Retorna {"verdict","reason","functional_pass": bool, "category": str|None,
             "verified": int, "violated": int, "not_verifiable": int,
             "criteria": <criteria_results tal cual>}
    functional_pass es True SOLO en el caso 6. NUNCA lanza (entradas basura => caso 4)."""
```

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/replan_engine.py`**
- En `_classify_failure` (`:256`), ramas nuevas **antes** de las genéricas (`MAX_REPLAN_ROUNDS = 3` **NO se toca**):
  | Texto del fallo contiene | `category` | `action` | Semántica |
  |---|---|---|---|
  | `NAV_SESSION_LOST` | `NAV` | `reauth_and_retry` | expulsión recuperable: re-autenticar y reintentar el MISMO paso |
  | `MENU_LABEL_NOT_FOUND` | `NAV` | `switch_to_menu_harvest` | reintentar cosechando el menú desde la pantalla base (`page.goto(base_url)` y volver a resolver) |
  | `APP_ERROR_PAGE` | `APP` | `abort_round` | **bug real del desarrollo**: NO reintentar, veredicto FAIL honesto |
  | `NAV_DEVIATION` | `NAV` | `switch_human_path` | si el contrato declara otro `human_paths` no intentado, patchear el spec; si no, `abort_round` |
  Regla dura: `APP_ERROR_PAGE` **jamás** se reintenta — reintentar un bug del desarrollo lo convertiría en flaky y podría enmascararlo.

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_functional_verdict.py`**
- `test_split_sections_encuentra_las_canonicas` (**C15**): fixture con el HTML de headings canónicos → `sections_found` contiene `CRITERIOS DE ACEPTACION` y `PASOS DE REPRODUCCION`.
- `test_split_sections_duplicado_gana_el_primero` (**C15, caso borde real del 367**): HTML con el bloque de headings DUPLICADO y con preámbulo espurio antes del primer heading → el cuerpo devuelto es el de la **primera** aparición y el preámbulo no aparece en ningún criterio.
- `test_extract_criterios_con_id_CA` (**C15, formato real del 367**): `<li>CA-01: El campo Póliza en FrmBusqueda.aspx admite hasta 50 caracteres…</li>` → criterio con `id == "CA-01"`, `screen_hint == "FrmBusqueda.aspx"`, `expected == "50"`, y `confidence == "high"`.
- `test_extract_repro_steps` (**C15**): 3 `<li>` bajo `PASOS DE REPRODUCCION` → `repro_steps` con 3 items en orden, el primero conteniendo `FrmBusqueda.aspx`.
- `test_extract_maxlength_del_ticket_367`: título *"Truncamiento del campo Póliza en Búsqueda de Clientes (MaxLength=20)"* sin sección de criterios → modo heurístico: ≥1 criterio con `kind == "maxlength"`, `expected == "20"`, `screen_hint == "FrmBusqueda.aspx"`, `confidence != "high"`.
- `test_extract_catalogo_del_ticket_366`: *"Catalogo Tipo de Telefono no incluye Laboral ni Particular"* → `kind == "catalog"`, `tokens` con `Laboral` y `Particular`, `screen_hint == "FrmDetalleClie.aspx"`.
- `test_criterio_sin_kind_reconocido_se_conserva` (**C15**): `<li>` con prosa que no matchea ningún patrón → el criterio **está** en la lista con `kind == "assertion"` (no se descarta: descartarlo infla el falso PASS).
- `test_extract_html_limpio`: descripción con `<div><b>texto</b></div>` y entidades `&quot; &amp; &nbsp; &gt;` → el criterio no contiene `<`, `>` ni `&…;`.
- `test_extract_sin_nada_no_lanza`: `{}` → `ok True`, `criteria == []`, `confidence == "low"`.
- `test_confidence_por_fuente`: con AcceptanceCriteria → `"high"`; solo descripción → `"medium"`; solo título → `"low"`.
- `test_verdict_sin_criterios_no_es_pass` (**KPI-5, el test clave**): `build_functional_verdict([], {"verdict": "PASS"})` → `verdict == "MIXED"`, `reason == "NO_FUNCTIONAL_ASSERTION"`, `functional_pass is False`.
- `test_verdict_violado_es_fail`: un criterio `violated` con técnico PASS → `FAIL`, `reason == "ACCEPTANCE_VIOLATED"`, `category == "APP"`.
- `test_verdict_blocked_gana`: técnico BLOCKED + criterios verificados → `BLOCKED` (precedencia 1).
- `test_verdict_pass_real`: 2 `verified`, 0 `violated`, 0 `not_verifiable`, técnico PASS → `PASS`, `functional_pass is True`.
- `test_verdict_parcial_es_mixed`: 1 `verified` + 1 `not_verifiable` → `MIXED`, `reason == "PARTIAL_COVERAGE"`.
- `test_verdict_entrada_basura_no_lanza`: `build_functional_verdict(None, None)` → `MIXED`/`NO_FUNCTIONAL_ASSERTION`.
- `test_replan_app_error_page_no_reintenta`: fallo con `APP_ERROR_PAGE` → `action == "abort_round"`.
- `test_replan_session_lost_reautentica`: fallo con `NAV_SESSION_LOST` → `action == "reauth_and_retry"`, `category == "NAV"`.
- `test_replan_menu_no_encontrado`: fallo con `MENU_LABEL_NOT_FOUND` → `action == "switch_to_menu_harvest"`.

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_functional_verdict.py -q` → **15/15**.
- `grep -c "NO_FUNCTIONAL_ASSERTION" functional_verdict.py` → **≥1**.
- `grep -cE "reauth_and_retry|switch_to_menu_harvest|abort_round" replan_engine.py` → **≥3**.
- Regresión: `& "…python.exe" -m pytest tests\unit\test_replan_engine.py -q` → verde.

**Flag:** `STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED` default **ON**. Ninguna excepción dura aplica: es determinista, local, y solo **agrega** información al veredicto. Con OFF, el pipeline reporta el veredicto técnico como hoy. Justificación de ON: el default actual (PASS sin aserciones) es precisamente el falso positivo que el operador pidió eliminar; dejarlo OFF sería mantener el bug activo por default.
**Impacto por runtime:** los 3 idéntico (determinista, cero LLM). Fallback: extracción con 0 criterios → `MIXED/NO_FUNCTIONAL_ASSERTION` (honesto), nunca un PASS inventado.
**Trabajo del operador:** ninguno.

---

### F7 — Evidencia re-verificable: manifiesto con hash por run

**Objetivo (1 frase):** que cada ejecución deje un manifiesto de toda su evidencia con hash, y que se pueda re-verificar después con un comando.

**Valor:** "evidencias claras y resultados repetibles" exige poder demostrar que la evidencia corresponde al run y no cambió. Hoy hay artefactos sueltos sin índice ni integridad.

**Archivo a CREAR: `Stacky tools/QA UAT Agent/evidence_manifest.py`**
```python
"""evidence_manifest.py — Manifiesto de evidencia con hash (Plan 240 F7)."""
_KIND_BY_SUFFIX = {".png": "screenshot", ".webm": "video", ".zip": "trace",
                   ".json": "data", ".jsonl": "log", ".html": "report",
                   ".log": "log", ".txt": "log", ".ts": "spec"}
_MANIFEST_NAME = "evidence_manifest.json"
_MAX_FILES = 5000          # cota dura: un run patológico no puede colgar el walk

def build_evidence_manifest(run_dir) -> dict:
    """Camina run_dir recursivo (excluyendo el manifiesto mismo) y escribe
    <run_dir>/evidence_manifest.json con:
      {"ok": True, "run_dir": str, "generated_at": <ISO UTC>,
       "files": [{"path": <relativo, separadores "/">, "bytes": int,
                  "sha256": <hex>, "kind": <de _KIND_BY_SUFFIX o "other">}],
       "counts": {"total": int, "screenshot": int, "video": int, "trace": int, ...},
       "truncated": bool}
    sha256 se calcula por chunks de 64 KB (no carga archivos enteros en memoria).
    Orden de "files": por path ascendente (determinista => dos corridas sobre el mismo
    directorio producen el MISMO manifiesto salvo generated_at).
    NUNCA lanza: directorio inexistente => {"ok": False, "error": "run_dir_missing"}."""

def verify_evidence_manifest(run_dir) -> dict:
    """Relee el manifiesto y recalcula los hashes.
    {"ok": bool, "checked": int, "mismatches": [{"path","reason"}], "missing": [...],
     "extra": [...]}  — reason en ("hash_mismatch","size_mismatch").
    "extra" = archivos presentes que no están en el manifiesto (informativo, no falla).
    ok=True solo si mismatches y missing están vacíos. NUNCA lanza."""
```

**Archivo a EDITAR: `Stacky tools/QA UAT Agent/qa_uat_pipeline.py`** — al final del run, junto al `stop_agenda_web` de F2 (mismo `finally`), best-effort:
```python
try:
    from evidence_manifest import build_evidence_manifest
    man = build_evidence_manifest(evidence_dir)          # el dir del run que el pipeline ya calcula
    stages["evidence"] = {"ok": bool(man.get("ok")),
                          "files": man.get("counts", {}).get("total", 0),
                          "manifest": "evidence_manifest.json"}
except Exception:
    logger.debug("evidence manifest no disponible", exc_info=True)
```
**Archivo a EDITAR: `Stacky tools/QA UAT Agent/playwright.config.ts`** — asegurar captura de evidencia en fallo (leer el archivo primero; si ya están, no duplicar): `use: { screenshot: 'only-on-failure', video: 'retain-on-failure', trace: 'retain-on-failure' }`.

**Tests (TDD): `Stacky tools/QA UAT Agent/tests/unit/test_plan240_evidence_manifest.py`**
- `test_manifest_lista_y_clasifica`: tmp con `a.png`, `b.webm`, `c.json`, `d.bin` → `counts.screenshot == 1`, `video == 1`, `data == 1`, y `d.bin` con `kind == "other"`.
- `test_manifest_determinista`: dos llamadas seguidas → misma lista de `path`+`sha256` (solo difiere `generated_at`).
- `test_manifest_excluye_a_si_mismo`: tras `build`, ningún `files[].path` es `evidence_manifest.json`.
- `test_verify_ok`: build + verify sin tocar nada → `ok True`, `mismatches == []`.
- `test_verify_detecta_modificacion`: build, modificar un byte de `a.png`, verify → `ok False`, `mismatches[0].reason == "hash_mismatch"`.
- `test_verify_detecta_borrado`: build, borrar `b.webm`, verify → `missing` contiene `b.webm`.
- `test_dir_inexistente_no_lanza`: `build_evidence_manifest(tmp/"nope")` → `ok False`, `error == "run_dir_missing"`.
- `test_subdirectorios_con_paths_relativos_posix`: archivo en `sub/dir/x.png` → `path == "sub/dir/x.png"` (separador `/` siempre, aunque el SO sea Windows).

**Criterio de aceptación (binario):**
- `& "…python.exe" -m pytest tests\unit\test_plan240_evidence_manifest.py -q` → **8/8**.
- `grep -c "sha256" evidence_manifest.py` → **≥2**.
- `grep -cE "only-on-failure|retain-on-failure" playwright.config.ts` → **≥2**.

**Flag:** ninguna — aditivo puro (un archivo JSON nuevo dentro del directorio de evidencia del run) y best-effort (su fallo nunca afecta el veredicto).
**Impacto por runtime:** los 3 idéntico. Fallback: si el walk falla, `stages["evidence"]` no aparece y el run sigue.
**Trabajo del operador:** ninguno.

---

### F8 — Flags en la UI, endpoint doctor y registro de ratchet

**Objetivo (1 frase):** que las 3 flags sean toggleables desde Configuración → Arnés, que el operador pueda auto-diagnosticar el runtime con un GET, y que el meta-ratchet de tests quede verde.

**Valor:** cierra G8 (config del operador vía UI) y KPI-6 (fin del diagnóstico contradictorio, ahora consultable).

**Sobre `requires=` (C9 — verificado, no hay aristas que declarar):** las 3 flags nuevas son **independientes entre sí** (ninguna vive dentro del branch de otra), así que **NO corresponde ninguna entrada** en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`), que lista **solo** las flags que tienen `requires`. Además `FlagSpec.requires` está documentado como *"Solo informativo para la UI; NINGÚN runner lo evalúa"* (`harness_flags.py:30-32`), por lo que una arista inventada sería puramente cosmética. El test `test_sin_aristas_requires` (abajo) fija esta decisión.

**Flags — los 5 lugares obligatorios (NO hand-editar `harness_defaults.env`):**
1. `Stacky Agents/backend/services/harness_flags.py` → `FLAG_REGISTRY` (**`:392`** — C7: el `:379` del v1 era un anclaje stale heredado del 214):
   ```python
   FlagSpec(key="STACKY_QA_UAT_ADO_BRIDGE_ENABLED", type="bool", group="global",
       label="Leer tickets de QA UAT con las credenciales de Stacky",
       description="El pipeline QA UAT lee el work item con el PAT cifrado que ya usa Stacky, en vez de exigir un ado-config.json con el PAT en texto plano. Solo lectura. Si falla, cae al CLI legacy. Default ON.",
       default=True),
   FlagSpec(key="STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED", type="bool", group="global",
       label="Veredicto funcional por criterios de aceptacion",
       description="Extrae los criterios de aceptacion del ticket y exige verificarlos: un run sin ninguna asercion funcional verificada nunca da PASS (queda MIXED). Determinista, sin LLM. Default ON.",
       default=True),
   FlagSpec(key="STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED", type="bool", group="global",
       label="Arrancar AgendaWeb local para validar (opt-in)",
       description="Si AgendaWeb no responde, el pipeline intenta UN arranque local con IIS Express y lo apaga al terminar. Requiere IIS Express instalado, el applicationhost.config del cliente y la solucion compilada. Solo localhost. Default OFF.",
       default=False),
   ```
2. `_CATEGORY_KEYS` (**`:120`**, bloque `"calidad_verificacion"` en **`:154`** — C7): las **3** keys ahí. Sin esto, el test que exige categoría para toda flag nueva queda rojo (`harness_flags.py:390` lo advierte en un comentario del propio archivo).
3. `Stacky Agents/backend/config.py` (espejo del patrón de `config.py:1192-1194`):
   ```python
   STACKY_QA_UAT_ADO_BRIDGE_ENABLED: bool = os.getenv("STACKY_QA_UAT_ADO_BRIDGE_ENABLED", "true").lower() in ("1", "true", "yes")
   STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED: bool = os.getenv("STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED", "true").lower() in ("1", "true", "yes")
   STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED: bool = os.getenv("STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED", "false").lower() in ("1", "true", "yes")
   ```
4. `Stacky Agents/backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON` (`:467`): agregar **SOLO** las dos primeras (la de autostart es default OFF: **NO** va, o `test_default_known_only_for_curated` queda rojo — gotcha `harness-flags-default-explicit-gotcha`).
5. **Propagación al entorno del pipeline (C5 — con candado, el v1 tenía una carrera):** en `Stacky Agents/backend/api/qa_uat.py`, en `_run_pipeline_in_background` (`:203`), ANTES de invocar el pipeline, exportar las 3 flags a `os.environ` leyéndolas de la **instancia** `config.config` (gotcha `config.config` vs módulo):
   ```python
   import threading
   _FLAG_EXPORT_LOCK = threading.Lock()      # módulo-level, junto a las otras constantes

   # dentro de _run_pipeline_in_background, antes de lanzar el pipeline:
   from config import config as _cfg
   with _FLAG_EXPORT_LOCK:
       for _k in ("STACKY_QA_UAT_ADO_BRIDGE_ENABLED",
                  "STACKY_QA_UAT_FUNCTIONAL_VERDICT_ENABLED",
                  "STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED"):
           os.environ[_k] = "true" if bool(getattr(_cfg, _k, False)) else "false"
   ```
   **Por qué este mecanismo es el correcto (verificado):** el pipeline corre **in-process** (`_ensure_pipeline_on_path`, `api/qa_uat.py:66-70`, inserta el tool en `sys.path`; no hay subprocess para el pipeline), así que los módulos del tool ven el mismo `os.environ`; y el runner de specs **sí** lanza un subprocess (`npx playwright test`, `uat_test_runner.py:352`) que **hereda** el entorno del padre. Sin esta exportación, el toggle de la UI no tendría ningún efecto sobre el tool (los módulos del tool leen por `os.environ`, no importan `config`).
   **Limitación documentada (C5):** `os.environ` es global al proceso y `_run_pipeline_in_background` corre en un `threading.Thread`. El candado evita que dos exportaciones se **interleaven**, pero **dos runs concurrentes comparten los valores del último export**. Es aceptable para el modelo mono-operador (G6) y debe quedar escrito en el docstring de la función. Prohibido "arreglarlo" con `setdefault`: eso volvería inefectivo el toggle de la UI, que es justamente el bug que esta fase corrige.

**Endpoint nuevo (read-only) en `Stacky Agents/backend/api/qa_uat.py`**, al final del blueprint, patrón de los GET existentes (sin flag):
```python
@bp.get("/runtime-doctor")
def get_runtime_doctor():
    """Doctor del runtime QA UAT (Plan 240 F8). Read-only, best-effort, siempre 200."""
    _ensure_pipeline_on_path()                       # helper existente, api/qa_uat.py:66
    out = {"ok": True, "browser": None, "agenda": None, "ado_bridge": None}
    try:
        from browser_runtime_guard import check_browser_runtime
        out["browser"] = check_browser_runtime(probe_launch=False)
    except Exception as exc:
        out["browser"] = {"ok": False, "code": "GUARD_UNAVAILABLE", "detail": str(exc)}
    try:
        from environment_preflight import run_environment_preflight
        pre = run_environment_preflight()
        out["agenda"] = {"ok": pre.ok, "reason": pre.reason, "message": pre.message,
                         "base_url": pre.base_url}
    except Exception as exc:
        out["agenda"] = {"ok": False, "reason": "PREFLIGHT_UNAVAILABLE", "message": str(exc)}
    try:
        from stacky_ado_bridge import bridge_available
        out["ado_bridge"] = {"ok": bool(bridge_available())}
    except Exception as exc:
        out["ado_bridge"] = {"ok": False, "detail": str(exc)}
    out["ok"] = bool((out["browser"] or {}).get("ok"))
    return jsonify(out)
```

**Huellas de regresión (C10) — `Stacky Agents/docs/sistema/error_fingerprints.json`** (registro real consumido por `backend/services/error_fingerprints.py:18`). **Leer primero el JSON y copiar el shape EXACTO de una entrada existente** (no inventar keys). AGREGAR 3 entradas nuevas al array, jamás editar entradas ajenas:
| id | clase que mata | patrón de matching |
|---|---|---|
| `qa_uat_login_glob_false_negative` | login exitoso reportado como credenciales inválidas por pasar un regex-string a `wait_for_url` | literal `AUTH_CREDENTIALS_INVALID` junto a `FrmAgenda` |
| `qa_uat_nav_session_lost` | expulsión a login por deep-link sin `?q=`, que cascada falsos auth-expired | literal `NAV_SESSION_LOST` |
| `qa_uat_app_error_page` | HTTP 200 con cuerpo de error 500 tomado como llegada válida (falso PASS) | literal `APP_ERROR_PAGE` |
Tras editar: `python -m json.tool "Stacky Agents/docs/sistema/error_fingerprints.json"` → exit 0.

**Tests (TDD): `Stacky Agents/backend/tests/test_plan240_qa_uat_runtime.py`** (fixtures espejo de `tests/test_qa_uat_endpoint.py` — copiar su patrón de app factory, no inventar uno):
- `test_flags_registradas`: las 3 en `FLAG_REGISTRY` y en `_CATEGORY_KEYS["calidad_verificacion"]`.
- `test_defaults_de_config`: `config.Config()` → bridge True, functional True, autostart False.
- `test_solo_las_on_en_curated`: `_CURATED_DEFAULTS_ON` contiene las 2 ON y **no** la de autostart.
- `test_sin_aristas_requires` (**C9**): ninguna de las 3 keys aparece en `_REQUIRES_MAP_FROZEN`, y el `FlagSpec` de cada una tiene `requires is None`.
- `test_doctor_endpoint_200`: `GET /api/qa-uat/runtime-doctor` → 200 con keys `ok, browser, agenda, ado_bridge`.
- `test_doctor_degrada_sin_guard`: monkeypatch para que el import del guard lance → 200 con `browser.code == "GUARD_UNAVAILABLE"` (nunca 5xx).
- `test_flags_se_exportan_al_entorno`: llamar el bloque de export con `config.config` monkeypatcheado (bridge True, autostart False) → `os.environ` con `"true"` y `"false"` respectivamente. Usar `monkeypatch.setattr(config.config, ...)` sobre la **INSTANCIA**.
- `test_huellas_sembradas` (**C10**): las 3 ids nuevas están en `error_fingerprints.json` y el archivo parsea.
- **Registrar el archivo en `HARNESS_TEST_FILES`** (`backend/scripts/run_harness_tests.sh` **y** `run_harness_tests.ps1`) — si no, el meta-ratchet queda rojo.

**Criterio de aceptación (binario):**
- `& ".venv\Scripts\python.exe" -m pytest tests\test_plan240_qa_uat_runtime.py -q` → **8/8**.
- `grep -cE "qa_uat_login_glob_false_negative|qa_uat_nav_session_lost|qa_uat_app_error_page" "Stacky Agents/docs/sistema/error_fingerprints.json"` → **3** (C10).
- `grep -c "test_plan240_qa_uat_runtime.py" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` → **1 en cada uno**.
- `grep -n "runtime-doctor" api/qa_uat.py` → **≥1**.
- Regresión (por archivo): `tests\test_qa_uat_endpoint.py`, `tests\test_harness_flags.py` → verdes.

**Flag:** las 3 descritas arriba (2 ON, 1 OFF con EXCEPCIÓN DURA #3 citada). El endpoint doctor no lleva flag (read-only, patrón de los GET existentes del blueprint).
**Impacto por runtime:** los 3 idéntico. Fallback: cualquier import roto → el doctor responde 200 con el sub-objeto en `ok:false`, nunca 5xx.
**Trabajo del operador:** ninguno; los toggles quedan disponibles en Configuración → Arnés.

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El launcher deja procesos `iisexpress.exe` colgados | `started_by_us` + `stop_agenda_web` en el `finally` del pipeline; jamás apaga lo que no arrancó; timeout mata lo propio; test `test_timeout_mata_lo_que_arranco` |
| R2 | El bridge ADO abre por accidente una vía de escritura (rompería G2/HITL) | `_READ_ONLY_METHODS` explícito + test `test_bridge_solo_lectura` que lee el propio archivo y falla si aparece `create_work_item`/`post_comment`/`update_work_item_state`/`upload_attachment`; criterio de aceptación con `grep -c … → 0` |
| R3 | `assert_arrival` con ui_maps viejos → falsos `NAV_DEVIATION` | Degradación por capas: sin ui_map → chequeo por URL (equivalente a hoy); el desvío nunca es terminal por sí solo (pasa por `replan_engine`, ≤3 rondas) y termina en veredicto honesto con screenshot |
| R4 | La allowlist de consola (F4) esconde un error real | Precedencia invertida a favor de la seguridad: si un mensaje matchea ignorable **y** significativo, gana **significativo**; los patrones de bug del dominio (`Sys.WebForms`, `Uncaught`, `is not defined`, `Input string was not in a correct format`) están en la lista de significativos con test propio |
| R5 | `via_menu` no encuentra la etiqueta y el run muere | `MENU_LABEL_NOT_FOUND` incluye los 20 primeros `label_norm` cosechados en el `error_detail` (diagnóstico inmediato) y el replan intenta `switch_to_menu_harvest` una vez |
| R6 | Bucle de re-auth infinito ante expulsión repetida | `_MAX_REAUTH_PER_STEP = 1` (constante de módulo) + `MAX_REPLAN_ROUNDS = 3` intacto |
| R7 | Colisión de edición con el 214 en `navigation_driver.py` (su F2) | §0 declara la absorción: quien implemente el 214 marca su F2 como cubierta por 240 F3+F4 y NO la reimplementa. `wait_aspnet_idle` y `assert_arrival` tienen los nombres EXACTOS que pide el 214, así que sus criterios de aceptación (`grep -c "no_wait_after=True"`, `grep -c "NAV_DEVIATION"`) quedan satisfechos |
| R8 | Sesión paralela viva en el árbol compartido | Este plan **no toca frontend** (superficie 100% tool + `api/qa_uat.py` + flags); commits SIEMPRE con pathspec explícito; `git worktree list` y `git status` antes de commitear |
| R9 | El export de flags al entorno (F8 §5) pisa una env var que el operador seteó a mano | Documentado: la UI es la fuente de verdad (G8, memoria `operator-config-always-via-ui`). Si en el futuro se quisiera respetar el env, sería `setdefault` — pero eso volvería el toggle de la UI inefectivo, que es el bug que F8 arregla |
| R10 | El ratchet AST de F1 falla en un archivo con sintaxis inválida | El test envuelve cada `ast.parse` en try/except y **cuenta** los archivos no parseables en un `skipped` que imprime; si `skipped > 0` el test **no** falla pero lo reporta (un archivo roto es un problema distinto, no de este ratchet) |
| R11 | **(C1)** Alguien vuelve a llamar código sync de Playwright desde un método async del driver | Prohibición verificable en el DoD (`grep -c "run_auth_session" navigation_driver.py` → 0) + `reauth_in_page` async como única vía soportada + explicación del crash real (`sync_api/_context_manager.py:48`) escrita en el docstring del helper |
| R12 | **(C4)** Aparece otra custom error page con un título que tampoco está en la lista de patrones | El gate de `assert_arrival` no depende solo del título: también mira `DOM_ERROR_TEXT_PATTERNS` sobre el body, los `DOM_ERROR_SELECTORS` y los indicadores de URL (`errors.aspx`, `aspxerrorpath`); cualquier patrón nuevo se agrega al final de la lista existente (aditivo, nunca reordenar) |
| R13 | **(C5)** Dos runs QA UAT concurrentes con flags distintas comparten el último export a `os.environ` | Candado de módulo para que los exports no se interleaven + limitación escrita en el docstring; aceptable bajo el modelo mono-operador (G6). Prohibido "arreglarlo" con `setdefault` (volvería inefectivo el toggle de la UI) |
| R14 | **(C14)** Alguien vuelve a llamar `get_work_item` sin `fields` y el veredicto funcional queda vacío en silencio | `_WORK_ITEM_FIELDS` obligatorio en el bridge + el propio `functional_verdict` convierte "0 criterios" en `MIXED/NO_FUNCTIONAL_ASSERTION` **visible**, nunca en un PASS: el modo de falla es ruidoso, no silencioso |
| R15 | **(C15)** Un ticket futuro no sigue la estructura canónica de headings | Degradación explícita por capas: sin sección `CRITERIOS DE ACEPTACION` se cae al modo heurístico sobre `ANALISIS FUNCIONAL` + título con `confidence` `medium`/`low`, y si tampoco hay nada, 0 criterios → `MIXED` honesto. Nunca se inventan criterios |
| R16 | **(C16)** El `sys.path` insert del bridge arrastra imports pesados del backend desde la CLI | Verificado: `services/ado_client.py` importa solo `config` y `services.secrets_store` (`:27-28`); **no** importa `db` ni `models`, así que no se levanta engine de BD. Si un refactor futuro lo cambiara, el bridge seguiría degradando al CLI legacy por su `try/except` |

## 8. Fuera de scope (explícito)

- Las fases F0, F1, F3, F4 y F5 del Plan 214 (higiene `tmp_*`, `navigation_kb.py`/`playbook_curator.py`, post-hook `qa_uat_enqueue`, pane de UI, `playbook_candidates`). Este plan produce los insumos que las hacen correctas, pero no las implementa.
- **Cualquier** cambio de frontend (incluye el pane del 214 F4). Este plan deja los campos en `execution.metadata` y nada más.
- Transicionar estados ADO al terminar QAUAT (Plan 208) y publicar dossiers automáticamente (sigue HITL: `mode="publish"` explícito).
- Auto-ejecución de SQL seeds (la gobernanza `PROPOSE_SQL_SEED → HUMAN_APPROVAL` queda intacta).
- Enriquecimiento por LLM de los criterios de aceptación (G3: el núcleo es determinista; el LLM se evaluará en otro plan).
- Arreglar el bug real de `FrmJDemanda.aspx` (HTTP 200 con error 500): es un defecto de AgendaWeb, no del agente. Este plan lo **detecta y lo reporta**; corregirlo es del equipo de RS.
- Instalar el binding de Playwright en `backend/venv` (py3.11). Este plan lo **detecta y da la remediación**; qué venv usa el operador para correr el backend es su decisión.
- Regenerar los specs ya existentes de `playwright/uat/*.spec.ts`.

## 9. Glosario

- **AgendaWeb:** aplicación web ASP.NET WebForms del producto RS (default `http://localhost:35017/AgendaWeb/`), objetivo de las pruebas E2E.
- **WebForms / postback:** modelo de ASP.NET donde los controles reenvían la página entera (`__doPostBack`) o parcial (UpdatePanel + ScriptManager); rompe las esperas default de Playwright.
- **`?q=` (payload de menú):** parámetro **encriptado y válido solo para la sesión actual** que AgendaWeb pone en varios links de menú. No es un id estable: reconstruirlo o reusarlo de una corrida anterior expulsa la sesión (H4).
- **glob vs regex en Playwright:** `page.wait_for_url("…")` con un **string** se interpreta como patrón glob; para un regex hay que pasar `re.compile(...)` o un **callable**. Confundirlos hace que el wait nunca matchee (H2).
- **namespace package (trampa de `find_spec`):** un directorio sin `__init__.py` en `sys.path` hace que `find_spec("nombre")` devuelva un spec de namespace aunque el paquete real no esté instalado. El tool tiene un directorio `playwright/` que dispara exactamente eso (H1).
- **ui_map:** JSON en `cache/ui_maps/<Pantalla>.aspx.json` con los selectores estables de una pantalla.
- **playbook:** JSON en `cache/playbooks/<slug>.json` con los pasos validados de un flujo.
- **veredicto técnico vs funcional:** técnico = "el test corrió sin errores"; funcional = "los criterios de aceptación del ticket se verificaron". Un PASS técnico con 0 criterios verificados es `MIXED/NO_FUNCTIONAL_ASSERTION` (KPI-5).
- **DPAPI:** cifrado de Windows con el que Stacky guarda el PAT de ADO (`pat_format: dpapi_*`). Windows-only; en otro SO el bridge cae al CLI legacy.
- **dry-run vs publish:** dry-run = corre y deja evidencia local, no publica nada; publish = Stacky publica el resultado (HITL, decisión del operador).
- **flag `requires`:** arista entre flags del arnés (`harness_flags.py:30`) que declara que una flag solo tiene efecto si otra está ON. Este plan **no** introduce aristas nuevas (las 3 flags son independientes).

## 10. Orden de implementación

1. **F0** — `browser_runtime_guard.py` + Check 0 del preflight + fin del mensaje contradictorio. (Sin esto nada se puede depurar.)
2. **F1** — fix del glob→predicado en el login + ratchet AST. (Desbloquea toda navegación.)
3. **F5** — `stacky_ado_bridge.py` + reader. (Desbloquea el primer stage del pipeline; se adelanta a F2-F4 porque KPI-2 se puede verificar sin navegar.)
4. **F2** — `agenda_web_launcher.py` + wiring del preflight. (Hace autónoma la validación.)
5. **F3** — `menu_resolver.py` + `via_menu` + `NAV_SESSION_LOST` + regla en `QAUat1.agent.md`.
6. **F4** — `wait_aspnet_idle` + `assert_arrival` con gate de página de error + `console_noise_policy.py`.
7. **F6** — `acceptance_extractor.py` + `functional_verdict.py` + ramas nuevas del replan.
8. **F7** — `evidence_manifest.py` + wiring + `playwright.config.ts`.
9. **F8** — flags en los 5 lugares + export al entorno + endpoint doctor + registro en `HARNESS_TEST_FILES`.

## 11. Definición de Hecho (DoD) global

- [ ] Los **9** archivos de test nuevos verdes (C8: el v1 decía "8" y enumeraba 7+1), corridos **POR ARCHIVO** con los comandos exactos de §4, con la salida real pegada (cero "pasó todo" sin evidencia). **8 del tool:** `test_plan240_browser_runtime_guard.py` **7** (5 + los 2 de C12), `test_plan240_login_url_predicate.py` **6**, `test_plan240_agenda_launcher.py` **8**, `test_plan240_menu_resolver.py` **10**, `test_plan240_arrival_and_console.py` **15** (13 + los 2 de C4), `test_plan240_ado_bridge.py` **8**, `test_plan240_functional_verdict.py` **19** (15 + los 4 de C15), `test_plan240_evidence_manifest.py` **8**. **1 backend:** `test_plan240_qa_uat_runtime.py` **8** (6 + C9 + C10). **Total 89 casos.**
- [ ] El único `backend/tests/test_plan240_*.py` registrado en `HARNESS_TEST_FILES` (sh **y** ps1); meta-ratchet verde.
- [ ] Regresiones nombradas verdes (por archivo): `test_navigation_driver.py`, `test_navigation_plan_gate.py`, `test_replan_engine.py`, `test_uat_ticket_reader.py`, `test_screen_error_detector.py` (por C4), `test_qa_uat_endpoint.py`, `test_harness_flags.py`, `test_harness_flags_requires.py` (por C9).
- [ ] **Prohibiciones de arquitectura verificadas (los 3 bloqueantes del v1 no pueden volver):** `grep -c "run_auth_session" navigation_driver.py` → **0** (C1: jamás Sync API desde async); `grep -c "def reauth_in_page" auth_session_factory.py` → **1** (C1); `grep -c "get_agenda_base_url" navigation_driver.py` → **≥1** (C2: base_url resuelto por la fuente única); `grep -cE "evaluate\(\s*render_(aspnet_exception|dom)_detector_js" navigation_driver.py` → **0** (C3: no se evalúa una definición de función TS).
- [ ] Las 3 huellas sembradas en `error_fingerprints.json` y el JSON parsea (C10).
- [ ] Ratchet AST de F1 en **0 hits** (`wait_for_url` con string literal).
- [ ] Ratchet KPI-3 en **0 hits** de `?q=` en `cache/playbooks/*.json` y `cache/ui_maps/*.json`.
- [ ] `grep` sentinels de cada fase (F0-F8) verdes, tal como se listan en cada criterio de aceptación.
- [ ] Las 3 flags visibles en Configuración → Arnés (categoría `calidad_verificacion`), con `STACKY_QA_UAT_AUTOSTART_AGENDA_ENABLED` en OFF y su EXCEPCIÓN DURA #3 citada en la description.
- [ ] **Verificaciones en vivo (requieren AgendaWeb arriba), con salida real pegada:** (a) login `ok=True/AUTH_LOGIN_OK` con `landing_url` de `FrmAgenda.aspx` en <15 s (KPI-1); (b) `qa_uat_pipeline.py --ticket <ADO_ID> --mode dry-run` con `stages.reader.ok == true` y `source == "stacky_dpapi"` (KPI-2); (c) `assert_arrival("FrmJDemanda.aspx")` → `APP_ERROR_PAGE` (KPI-4); (d) `GET /api/qa-uat/runtime-doctor` → 200 con los 3 sub-objetos (KPI-6); (e) `verify_evidence_manifest(<run_dir>)` → `ok=True, mismatches=[]` (KPI-7).
- [ ] Con las 3 flags en default y AgendaWeb caída: el pipeline devuelve el mismo BLOCKED de hoy (con mejor mensaje). Cero regresión (KPI-8).
- [ ] `python -m compileall` limpio sobre los 7 módulos nuevos y los 5 editados del tool.
- [ ] **Ningún archivo de frontend tocado** (verificable con `git status`); en particular ni `TicketBoard.tsx`, ni `UnblockerPage.tsx`, ni `TicketGraphView.jsx`.
- [ ] `git worktree list` + `git status` revisados antes de commitear; commits con **pathspec explícito** (árbol compartido con sesión paralela viva).
