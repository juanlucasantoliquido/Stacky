# Plan 214 — Reactivación y fortalecimiento del agente QAUAT E2E (Playwright): navegación sin desvíos y validación post-desarrollo desde Agenda Web

> Estado: **PARCIAL — faltan F1 y F2** (auditoría solo-lectura 2026-07-26, `supervisar-implementaciones-planes`).
>
> | Fase | Veredicto | Evidencia verificada contra código |
> |---|---|---|
> | F0 | **IMPLEMENTADA** (`615baf45`) | `ls "Stacky tools/QA UAT Agent" \| grep -c "^tmp"` = **0**; `_attic/` = **12** archivos; `grep -c RSPACIFICO run_tests.py` = **0** |
> | F1 | **PENDIENTE — SIN CÓDIGO** | NO existen `navigation_kb.py` ni `playbook_curator.py` en el tool; NO existe `tests/unit/test_plan214_navigation_kb.py`; `grep -n "get_kb_inventory" backend/api/qa_uat.py` = **0 hits** (no hay endpoint `GET /api/qa-uat/kb`); no existe `backend/tests/test_plan214_qa_uat_kb_endpoint.py`. La KB SÍ creció (7 playbooks + 6 ui_maps en `cache/`), pero eso lo trajeron los planes 240/241: el inventario determinista y el curador del 214 no están |
> | F2 | **PARCIAL (≈20%)** | Único hit: `navigation_driver.py:390` `click(no_wait_after=True)` — y lo puso el plan **241** (`25fc4072`), no el 214. FALTAN: `wait_aspnet_idle`/`_ASPNET_IDLE_JS` (0 hits), `assert_arrival` (0 hits), `NAV_DEVIATION` en `navigation_driver.py` **y** en `replan_engine.py` (**0 hits en ambos**), `waitForAspNetIdle` en `templates/playwright_test.spec.ts.j2` (**0 hits**), `nav_deviations` en `qa_uat_pipeline.py` (**0 hits**), la huella `qa_uat_nav_deviation` en `docs/sistema/error_fingerprints.json` (**0 hits**), y los 2 archivos de test (`test_plan214_webforms_idle.py`, `test_plan214_nav_deviation.py`). `grep -rn "deviation" --include=*.py` sobre el tool devuelve **0 hits** |
> | F3 | **IMPLEMENTADA** (`02ffdac9`) | `backend/services/qa_uat_enqueue.py` + wiring real `app.py:924-925` (`register(ticket_status.register_post_hook)`); flags `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` / `STACKY_QA_UAT_AUTORUN_ENABLED` en `harness_flags.py:178,1966,1978` (la 2ª con `requires` de profundidad 1) |
> | F4 | **IMPLEMENTADA** (`02ffdac9`) | `api/qa_uat.py:174` `def _update_dev_candidate(...)`; `components/qaUatVerdictModel.ts`, `QaUatVerdictPane.tsx` + `.module.css`, `__tests__/qaUatVerdictModel.test.ts`; montado en `OutputPanel.tsx` (2 hits, no inerte) |
> | F5 | **IMPLEMENTADA** (`615baf45`) | `grep -c "PLAYBOOKS PRIMERO" backend/Stacky/agents/QAUat1.agent.md` = **1**; `services/qa_browser_plan.py:27` `def playbook_candidates(...)` |
> | F6 | **IMPLEMENTADA** (`615baf45`) | `grep -c "Smoke E2E de reactivación" "Stacky tools/QA UAT Agent/Flujo_QA_UAT.md"` = **1**. La CORRIDA del smoke sigue pendiente (manual, opt-in, como el plan lo declara) |
>
> Tests corridos de verdad con `backend/.venv` (py3.13.5), por archivo:
> `test_plan214_qa_uat_enqueue.py` **26 passed**, `test_plan214_qa_browser_playbooks.py` **11 passed**.
> Ambos registrados en `run_harness_tests.sh` (2 hits). `npx tsc --noEmit` exit 0.
>
> **Corrección de una creencia previa:** se creía que F3/F4 estaban hechas y que F1/F2 "las cubrieron los
> planes 240/241". Falso contra código: 240/241 aportaron `no_wait_after` y crecieron el `cache/`, pero NO
> construyeron el inventario/curador de F1 ni el circuito `NAV_DEVIATION` de F2. Lo pendiente REAL es F1 + F2.
>
> Estado previo: **v2 · CRITICADO (v1 → v2)** — VEREDICTO: **APROBADO-CON-CAMBIOS** (2026-07-23). Pipeline: proponer ✓ → **criticar ✓** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: StackyArchitectaUltraEficientCode (perfil normal, heredado de Fable 5). Juez v2: el mismo agente en rol adversarial.

**CHANGELOG v1 → v2 (hallazgos del juez, todos verificados contra código):**
- **C1 (IMPORTANTE, resuelto):** F2 citaba atributos INEXISTENTES del driver (`self._page`/`self._timeout_ms`) y ubicaba el `click()` en el método equivocado. Reales: `self.page` (`navigation_driver.py:224`), `timeout_ms` es parámetro LOCAL de los métodos (`_execute_nav:349`), y el `locator.click()` vive en `via_link_click` (`navigation_driver.py:300`), no en `_execute_nav`. Instrucciones F2 corregidas quirúrgicamente.
- **C2 (IMPORTANTE, resuelto):** faltaba la arista `requires=` entre flags: con `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` OFF, el autorun ON es un no-op silencioso (vive DENTRO del hook gateado). El harness soporta `requires` (`harness_flags.py:30`) y exige declarar la arista en `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py:120`, profundidad 1 — cumple R4). F3 ahora la declara (5 lugares, no 4).
- **C3 (IMPORTANTE, resuelto):** el plan declaraba "NAV|DATA|ENV|APP" como LA taxonomía del normalizador; el `CATEGORY_SET` real tiene **9** categorías (`APP, ENV, DATA, PIP, GEN, NAV, OBS, SEC, OPS` — `verdict_normalizer.py:47-57`). `categoryLabel` (F4) colapsaba 5 categorías reales a "—" (un BLOCKED/PIP perdía su señal). F4 mapea las 9 y ante desconocida devuelve el código crudo.
- **C4 (IMPORTANTE, resuelto):** F3 lee `build_verdict` asumiendo que el 210 ya escribió. Verificado: en `on_execution_end` los post-hooks corren DESPUÉS de `set_status` (`ticket_status.py:270-286`), así que el gate del 210 (que corre en el camino de estado) es visible. Regla nueva explícita: si el 210 se implementara como post-hook, debe registrarse en `app.py` ANTES que `qa_uat_enqueue` (el orden de `_POST_HOOKS` es el orden de registro).
- **C5 (MENOR, resuelto):** el plan mata la clase de regresión "QAUAT se desvía de la ruta" pero no sembraba su huella en `docs/sistema/error_fingerprints.json` (registro real: `services/error_fingerprints.py:18`). F2 ahora la siembra.
- **C6 (MENOR, resuelto):** KPI-1 ("≥90% de los runs") no era binario sin población definida. Redefinido como binario verificable.
- **C7 (MENOR, resuelto):** `tmp72.py` NO matchea el glob `tmp_*` (sin guion bajo) — verificado que existe; F0 aclara que el `git mv` es por lista literal, jamás por glob.
- **C8 (MENOR, resuelto):** `build_guarded_browser_spec(data: BrowserRunInput)` (`qa_browser_plan.py:27`) tiene firma pública con callers; F5 ahora exige parámetro keyword con default (`pipeline_root=None` → sin candidatos extra) para no romper contrato.
- **C9 (MENOR, resuelto):** el DoD v1 decía "5 archivos de test" pero enumeraba 2+3+1=**6**; corregido.
- **[ADICIÓN ARQUITECTO] (resuelta en F4):** cierre de loop bidireccional — al terminar el run qa-uat, el `qa_uat_candidate` de la ejecución del Developer se actualiza best-effort a `validated|failed|blocked` con `qa_uat_execution_id`, para que la tarjeta deje de decir "sugerida" cuando la validación ya corrió. Cero trabajo del operador, HITL intacto.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo del pipeline NO usa LLM).
> Origen: **pedido textual del operador** — *"Investigar cómo retomar, fortalecer y poner en funcionamiento el agente QAUAT E2E basado en Playwright… que pueda ejecutar los flujos completos sin desviarse ni fallar durante la navegación… que, una vez finalizado un desarrollo, el agente pueda tomarlo, validarlo de punta a punta desde la Agenda Web, navegar de forma autónoma por las distintas pantallas y verificar correctamente el funcionamiento del flujo implementado."*

---

## Planes relacionados (leer antes de implementar)

- **ENCADENA con Plan 208** — "Sincronización ADO al completar agente + matriz de estados" (`Stacky Agents/docs/208_PLAN_SINCRONIZACION_ADO_AL_COMPLETAR_AGENTE_Y_MATRIZ_DE_ESTADOS_POR_TIPO_DE_TICKET_Y_AGENTE.md`, CRITICADO v2). El 208 estableció el chokepoint runtime-agnóstico "un agente terminó": `services/ticket_status.py::on_execution_end` (`ticket_status.py:231`) + `register_post_hook` (`ticket_status.py:307`). **Este plan REUSA ese mismo patrón de registro** (F3): registra **su propio** post-hook `qa_uat_enqueue._post_hook`, exactamente como hoy hacen `incident_autopublish` e `incident_dev_autocommit` (`app.py:853-855`). **NO toca ni reimplementa** `completion_dispatcher` del 208: los post-hooks son independientes y componen (la lista `_POST_HOOKS` acepta N hooks, `ticket_status.py:307-314`). Regla de merge para quien implemente segundo: **agregar líneas propias en `app.py`, jamás reordenar ni reescribir las ajenas** (memoria `gotcha-merge-silent-duplicate-keyword`).
- **ENCADENA con Plan 210** — "Gate de build determinista del Developer" (`Stacky Agents/docs/210_*`, CRITICADO v2). La cadena natural post-desarrollo es: Developer termina → gate de build (210) + inspector post-build (211) → **validación QAUAT E2E (ESTE plan)** → sync ADO (208) → guía de validación al usuario (209). F3 hace un **gate best-effort** sobre `execution.metadata["build_verdict"].gate_ok` (contrato §5 del 210): si el 210 está implementado y el build NO pasó, el candidato QAUAT se marca `blocked_by_build` (visible, honesto) en vez de sugerir validar algo que no compila. Si el 210 aún no está mergeado, el campo no existe y el candidato se encola igual (degradación controlada, cero dependencia dura).
- **NO COLISIONA con Plan 209** — el playbook "Cómo validar esto" (209) es texto para el usuario final dentro del deliverable; este plan produce un **veredicto de máquina** (PASS/FAIL/BLOCKED/MIXED) de un run E2E real. Planos distintos; ninguno edita archivos del otro.
- **NO COLISIONA con 212/213** — 212 toca `api/agents.py`/`llm_router`/selección de modelo; 213 toca prompts de analistas + `harness/post_run.py`. Este plan toca `api/qa_uat.py`, `services/qa_uat_enqueue.py` (nuevo), `services/qa_browser_plan.py`, el tool `Stacky tools/QA UAT Agent/` y `OutputPanel.tsx`. Únicos archivos compartidos con otros planes: `app.py` (aditivo, 1 bloque), `harness_flags.py`/`config.py`/`test_harness_flags.py` (aditivos por naturaleza) y `backend/scripts/run_harness_tests.sh|.ps1` (ratchet, siempre aditivo).
- **PROHIBIDO editar** `frontend/src/pages/TicketBoard.tsx`, `frontend/src/pages/UnblockerPage.tsx` y `frontend/src/components/TicketGraphView.jsx` en este plan: hay una **sesión paralela viva** trabajándolos (git status del árbol compartido). Toda la superficie UI de este plan vive en `OutputPanel.tsx` + componentes nuevos.

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El agente QAUAT E2E **ya existe** con muchísimo trabajo previo en `Stacky tools/QA UAT Agent/` (pipeline determinista de 8 herramientas, 72 archivos de tests unit, schemas JSON, replan engine, session recorder, contratos de navegación) y con integración backend viva (`api/qa_uat.py`, blueprint `/api/qa-uat`), pero está **dormido y se desvía al navegar**: su base de conocimiento de navegación está casi vacía (**1** playbook en `cache/playbooks/`, **2** ui_maps en `cache/ui_maps/`, verificado 2026-07-23), su driver no aplica el patrón WebForms-safe de forma sistemática, nada lo dispara cuando un desarrollo termina, y su veredicto no aterriza en la UI de Stacky. Este plan lo **retoma y fortalece sin reescribir nada**: (F0) higiene del tool y arnés de tests veraz; (F1) inventario + curación para **crecer la base de playbooks/ui_maps** con las piezas que ya existen (`session_recorder` → `session_to_playbook`); (F2) navegación **WebForms-safe** (`noWaitAfter` + espera de idle ASP.NET + validación de llegada por DOM) con **detección temprana de desvío** y replan acotado; (F3) **disparo post-desarrollo** vía el chokepoint `on_execution_end` (patrón del 208), con candidato visible al operador y autorun opt-in; (F4) **veredicto preciso y visible** (NAV|DATA|ENV|APP + weak assertions + evidencia) en un pane de la UI; (F5) **paridad de 3 runtimes** con playbooks-first en el agente Claude y en los planes del Codex Browser.

**KPI / impacto medible (binarios).**
- **KPI-1 — Navegación sin desvío (binario, C6):** (a) el 100% de los runs nuevos del pipeline exponen el contador `nav_deviations` en `stages.runner` (F2 — hoy el campo no existe); (b) el run del smoke E2E de F6, ejecutado sobre una pantalla con ui_map + playbook curado, termina con `nav_deviations == 0`. Ambos verificables leyendo el JSON de salida del pipeline.
- **KPI-2 — Base de conocimiento poblada:** 100% de las pantallas declaradas en `navigation_contracts.yml` con ui_map en `cache/ui_maps/`, y ≥ 5 playbooks curados en `cache/playbooks/` (hoy: 2 ui_maps, 1 playbook). Medible: `GET /api/qa-uat/kb` (F1) devuelve `coverage_pct == 100.0` y `playbooks_total >= 5`.
- **KPI-3 — Tiempo dev-terminado → validación disponible:** el candidato QAUAT aparece en la ejecución del Developer ≤ 5 segundos después de completar (post-hook síncrono, O(ms)); con autorun ON (opt-in), el veredicto llega al terminar el pipeline. Hoy: **nunca** (cero disparo automático). Medible: presencia de `metadata.qa_uat_candidate` en la ejecución del Developer.
- **KPI-4 — Cero falso verde silencioso:** 100% de los runs del pipeline exponen en `execution.metadata` el veredicto normalizado + categoría canónica (una de las **9** del `CATEGORY_SET`: `APP|ENV|DATA|PIP|GEN|NAV|OBS|SEC|OPS`, `verdict_normalizer.py:47-57` — C3) + conteo de weak assertions. Un PASS con assertions débiles queda ANOTADO (nunca oculto). Medible: campos de F4 presentes en todo run nuevo.
- **KPI-5 — Paridad 3 runtimes:** Claude Code → `QAUat1.agent.md` con política playbooks-first; Codex → `qa_browser` con candidatos desde playbooks; fallback universal (Copilot y cualquier runtime) → pipeline determinista `qa_uat_pipeline.py` sin LLM. Medible: tabla §5 con test por mecanismo.
- **KPI-6 — Cero regresión:** con las 2 flags nuevas en su default y sin configurar nada, el comportamiento actual de Stacky es byte-idéntico salvo: candidato en metadata (aditivo) y pane nuevo (data-driven, solo renderiza si hay datos). Ningún test existente se rompe.

---

## 2. Por qué ahora / gap que cierra (anclado en evidencia verificada 2026-07-23)

Cada ancla fue verificada contra el repo en frío (no se cita de memoria):

1. **El pipeline determinista existe y es serio.** `Stacky tools/QA UAT Agent/qa_uat_pipeline.py` (4427 líneas) orquesta 8 etapas (`reader → ui_map → compiler → generator → runner → dossier → publisher`, ver `--skip-to` en `qa_uat_pipeline.py:27`) con preflight de entorno (`environment_preflight`, stage en `:400-424`), fingerprint de deploy (`:506-524`), smoke path (`:553-576`) y replan hasta `MAX_REPLAN_ROUNDS=3` (`replan_engine.py:66`). Tests: 72 archivos en `tests/unit/` + `tests/integration/` + `tests/regression/`, corridos con pytest vía `conftest.py` de la raíz del tool (agrega el tool a `sys.path` y fuerza `STACKY_LLM_BACKEND=mock`).
2. **GAP CENTRAL — la base de conocimiento de navegación está casi vacía.** `cache/playbooks/` tiene **1** archivo (`agregar_usuario_nuevo.json`) y `cache/ui_maps/` tiene **2** (`FrmAgenda.aspx.json`, `FrmDetalleClie.aspx.json`), pese a que las herramientas para crecerla existen y funcionan: `session_recorder.py` (graba una sesión humana, CLI `--goal/--url/--no-learn/--background`, `session_recorder.py:563-580`) y `session_to_playbook.py::run(session_dir, dry_run, verbose)` (`session_to_playbook.py:47-51`, convierte la grabación en playbook + actualiza `form_knowledge.json`). Sin playbooks ni ui_maps, el agente navega "a ciegas" y se desvía: **ese es el porqué del síntoma que reporta el operador.**
3. **El patrón WebForms-safe no está aplicado sistemáticamente.** AgendaWeb es ASP.NET WebForms (postbacks, UpdatePanels, `__doPostBack` — el propio driver lo documenta, `navigation_driver.py:9,:188-195`). `grep -n "noWaitAfter\|no_wait_after" navigation_driver.py` → **0 hits**; el template de specs `templates/playwright_test.spec.ts.j2` tampoco impone `noWaitAfter` + espera de idle ASP.NET. La navegación robusta en WebForms exige `click` con `noWaitAfter` + espera corta de idle + validación por DOM, no esperas largas ciegas.
4. **La detección de desvío existe pero no está cableada como señal de primera clase.** `screen_error_detector.py` (detectores JS de excepción ASP.NET y DOM, `:295-318`), `smoke_path_checker.py::run_smoke_path` (`:45`), `screen_detector.py::detect_screens` (`:121`) y `verdict_normalizer.py` (VERDICT_SET `{PASS, FAIL, BLOCKED, MIXED, SKIPPED}` `:45`, `CATEGORY_SET` de **9** categorías `APP|ENV|DATA|PIP|GEN|NAV|OBS|SEC|OPS` `:47-57` — C3: NAV/DATA/ENV/APP son las 4 que el operador ve más seguido, NO el set completo) existen. Falta: aserción de llegada por pantalla tras cada paso y el código de error `NAV_DEVIATION` que el `replan_engine._classify_failure` (`replan_engine.py:256`) pueda patchear con un camino alternativo del contrato.
5. **Nada dispara QAUAT al terminar un desarrollo.** El chokepoint universal "un agente terminó" es `ticket_status.on_execution_end` (`ticket_status.py:231`) con registro de post-hooks (`register_post_hook` `:307`, firma esperada `fn(*, ticket_id, execution_id, final_status, agent_type, error, **kwargs)` `:310`, ejecutados con captura de excepciones `:325-331`). Hoy los únicos hooks registrados son `incident_autopublish` e `incident_dev_autocommit` (`app.py:853-855`). Cero conexión con QA UAT.
6. **La integración backend ya existe y es reusable tal cual.** `api/qa_uat.py`: blueprint `/qa-uat` (`:50`), `_AGENT_TYPE = "qa-uat"` (`:63`), `_PIPELINE_ROOT` apunta a `../../Stacky tools/QA UAT Agent` (`:58`), `POST /run` valida `ticket_id/mode(dry-run|publish)/headed/timeout_ms`, crea la `AgentExecution` con `metadata_dict` y lanza `_run_pipeline_in_background` en thread daemon (`:76-171`), logs por SSE `stream_url=/api/executions/{id}/logs/stream` (`:170`). El frontend ya tiene los endpoints tipados (`frontend/src/api/endpoints.ts:2450-2526`).
7. **La seguridad HITL ya está resuelta por diseño previo.** Default `mode="dry-run"`; `mode="publish"` publica Stacky centralmente (nunca el agente directo a ADO); existe `check_run_publish_policy` (`api/qa_uat.py:462`) y la gobernanza de datos v2.0 (SQL seed NUNCA auto-ejecutado, `approve_seed_proposal` `:1119` es un endpoint de aprobación humana). Este plan NO abre ninguna salida externa nueva.
8. **Higiene: el arnés de tests del tool miente por rutas muertas.** `run_tests.py` tiene HARDCODEADA la ubicación VIEJA del tool (`BASE = r"N:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent"` y `SECRETS = r"N:\GIT\RS\RSPACIFICO\Tools\Stacky\.secrets\agenda_web.env"`) y corre 3 specs de `evidence\116`, no los unit tests. Además hay **12 archivos basura** en la raíz del tool: `tmp_db_check.py, tmp_db2.py … tmp_db8.py, tmp_dbquery.py, tmp_pablo_clients.py, tmp_rdire_query.py, tmp72.py` (verificado por listado).
9. **El agente agéntico existe para el runtime Claude.** `backend/Stacky/agents/QAUat1.agent.md`: QA UAT generalista, regla dura NO tocar ADO, explora por código primero, credenciales desde `Tools/Stacky/.secrets/agenda_web.env`, base default `http://localhost:35017/AgendaWeb/`, clasificación NAV|DATA|ENV|APP, handoff a `Agentes/outputs/<ADO_ID>/` (el tool también lo implementa determinista: `stacky_handoff.py::export_stacky_handoff` `:26`, escribe `Agentes/outputs/<ADO_ID>/comment.html + attachments.json` `:5-7,:49`).

**Gap en una frase:** todas las piezas existen (pipeline, replan, recorder→playbook, contratos, blueprint, agente, veredicto normalizado) pero la KB de navegación está vacía, el patrón WebForms-safe no es sistemático, nada dispara la validación al terminar un desarrollo y el veredicto no llega a la UI — este plan cablea esas cuatro cosas reusando el 100% de lo existente.

---

## 3. Principios y guardarraíles (NO negociables, codificados en las fases)

- **G1 · Retomar y fortalecer, NO reescribir.** Cero reemplazo de módulos del tool. Solo: archivos nuevos pequeños (`navigation_kb.py`, `playbook_curator.py`), ediciones quirúrgicas (`navigation_driver.py`, `replan_engine.py`, template J2, `run_tests.py`) y wiring backend aditivo.
- **G2 · Human-in-the-loop innegociable.** El run E2E puede **prepararse/sugerirse** automático (candidato en metadata, botón en UI), pero: publicar en ADO = `mode="publish"` explícito del operador (flujo existente); cambiar estados ADO = territorio del 208 (no de este plan); ejecutar SQL seed = flujo de aprobación existente (`approve_seed_proposal`). El autorun (F3) corre **SIEMPRE en dry-run literal** (constante en código, no configurable) y está **OFF por default**.
- **G3 · Determinista-primero, cero LLM en el núcleo.** Inventario KB, curación, driver WebForms-safe, post-hook, veredicto y pane son Python/TS deterministas → idénticos en los 3 runtimes.
- **G4 · Paridad 3 runtimes con fallback explícito por ítem.** Claude Code → `QAUat1.agent.md`; Codex → `qa_browser` guarded spec; **fallback universal** (Copilot Pro y cualquier runtime) → `qa_uat_pipeline.py` determinista que no depende de ningún LLM. Cada fase declara su impacto por runtime.
- **G5 · Cero trabajo extra al operador.** Todo invisible/automático u opt-in default ON, con UNA excepción citada: `STACKY_QA_UAT_AUTORUN_ENABLED` default **OFF** por **EXCEPCIÓN DURA #3 (prerequisito no garantizado en instalación default):** AgendaWeb corriendo en `http://localhost:35017/AgendaWeb/`, credenciales en `Tools/Stacky/.secrets/agenda_web.env` y browsers Playwright instalados (`playwright install chromium`). El loop de captura de sesiones (F1) también depende de esos prerequisitos: por eso es un **comando opt-in documentado**, no un daemon.
- **G6 · Mono-operador sin auth real.** Cero RBAC. `current_user()` sigue siendo informativo.
- **G7 · No degradar performance/seguridad/estabilidad/DX.** El post-hook es O(ms) (una escritura de metadata), nunca lanza (los post-hooks ya capturan excepciones, `ticket_status.py:325-331`). El pipeline ya corre en thread daemon con logs SSE. Nada nuevo toca la red salvo el pipeline mismo (que ya existía).
- **G8 · Config del operador vía UI.** Las 2 flags nuevas van al registry del arnés (`harness_flags.py`) → visibles/toggleables en Configuración → Arnés. Cero env-var-only para el operador.
- **G9 · Gotchas duros del repo (obligatorios):** leer flags SIEMPRE de la instancia `config.config` (el módulo devuelve el default y mata el branch OFF); todo `backend/tests/test_*.py` nuevo se registra en `HARNESS_TEST_FILES` (`run_harness_tests.sh` **y** `.ps1`) o el meta-ratchet queda rojo; tests SIEMPRE por archivo (contaminación cross-run conocida); backend con el venv py3.13 (`Stacky Agents/backend/.venv`); frontend nuevo `.tsx` con **cero inline-style** (ratchet uiDebt: usar `.module.css`); NO hand-editar `harness_defaults.env` (lo genera `deployment/export_harness_defaults.py`).

---

## 4. Nomenclatura fija (usar EXACTAMENTE estos nombres)

- Flag encolado: `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` (bool, default **True**, categoría `calidad_verificacion`).
- Flag autorun: `STACKY_QA_UAT_AUTORUN_ENABLED` (bool, default **False** — EXCEPCIÓN DURA #3 citada en G5; NO va en `_CURATED_DEFAULTS_ON`).
- Módulo backend nuevo: `backend/services/qa_uat_enqueue.py`.
- Helper extraído en `api/qa_uat.py`: `start_qa_uat_run(ticket_ado_id, *, mode="dry-run", headed=False, timeout_ms=30000, started_by="qa-uat-auto") -> int`.
- Key de metadata en la ejecución del Developer: `qa_uat_candidate` (dict, ver F3).
- Módulos nuevos del tool: `Stacky tools/QA UAT Agent/navigation_kb.py` y `Stacky tools/QA UAT Agent/playbook_curator.py`.
- Helper async del driver: `wait_aspnet_idle(page, timeout_ms=3000) -> bool` (en `navigation_driver.py`).
- Método nuevo del driver: `NavigationDriver.assert_arrival(expected_screen: str) -> dict`.
- Código de error de desvío: `NAV_DEVIATION` (string exacto, se suma al contrato de `_classify_error`).
- Carpeta de cuarentena de basura: `Stacky tools/QA UAT Agent/_attic/`.
- Frontend nuevos: `frontend/src/components/qaUatVerdictModel.ts`, `frontend/src/components/QaUatVerdictPane.tsx`, `frontend/src/components/QaUatVerdictPane.module.css`, test `frontend/src/components/__tests__/qaUatVerdictModel.test.ts`.

**Comandos de test canónicos (usar tal cual):**
- Tool QA UAT (pytest por archivo, con el venv py3.13 del backend — el `conftest.py` de la raíz del tool resuelve `sys.path` y mockea el LLM):
  ```powershell
  cd "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent"
  & "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\unit\<archivo> -q
  ```
  (si `.venv` no existe, usar `venv\Scripts\python.exe` — mismo py3.13).
- Backend Stacky (pytest por archivo):
  ```powershell
  cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
  & ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q
  ```
- Frontend (vitest por archivo — jamás la suite entera, contaminación cross-file conocida):
  ```powershell
  cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"
  npx vitest run src/components/__tests__/qaUatVerdictModel.test.ts
  ```
- **Registro de ratchet:** SOLO los `backend/tests/test_plan214_*.py` van en `HARNESS_TEST_FILES` (`backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1`). Los tests del tool (`Stacky tools/QA UAT Agent/tests/…`) **NO** se registran ahí (viven fuera de `backend/tests/`; el meta-ratchet no los cuenta).

---

## 5. Paridad de runtimes (tabla normativa)

| Runtime | Mecanismo QAUAT | Fallback |
|---|---|---|
| Claude Code CLI | Agente `backend/Stacky/agents/QAUat1.agent.md` (F5: playbooks-first) — explora por código, navega con Playwright, handoff local | Si el agente falla/no está: pipeline determinista `qa_uat_pipeline.py` vía `POST /api/qa-uat/run` |
| Codex CLI | `api/qa_browser.py` + `services/qa_browser_plan.py::build_guarded_browser_spec` (F5: candidatos desde playbooks) | Pipeline determinista vía `POST /api/qa-uat/run` |
| GitHub Copilot Pro | **Directo al fallback universal:** pipeline determinista `qa_uat_pipeline.py` (no usa LLM en ninguna etapa obligatoria; `STACKY_LLM_BACKEND=mock` es el default de tests) | — (es el fallback) |

El disparo post-desarrollo (F3) es **runtime-agnóstico por construcción**: el post-hook vive en `on_execution_end`, que los 3 runners llaman directamente (evidencia del Plan 208 §2.2: `claude_code_cli_runner.py`, `codex_cli_runner.py`, `agent_runner.py`).

---

## 6. Fases

> Orden de dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6**. F1 y F2 son independientes entre sí (paralelizables). F3 no depende de F1/F2 (puede adelantarse), pero F4 consume campos que F2 produce. F5 depende de F1 (playbooks existentes que consumir).

---

### F0 — Higiene del tool + arnés de tests veraz

**Objetivo (1 frase):** dejar la raíz del tool sin basura y el runner de tests sin rutas muertas, para que todo lo que sigue se construya sobre un arnés que dice la verdad.

**Valor:** hoy `run_tests.py` apunta a una ruta que NO existe en este árbol (`N:\GIT\RS\RSPACIFICO\...`) — cualquier modelo menor que lo corra concluye cosas falsas; y 12 archivos `tmp_*` contaminan la raíz.

**Archivos a tocar (todos bajo `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\`, OJO ruta con espacios — SIEMPRE entre comillas):**
1. CREAR carpeta `_attic/` y MOVER con `git mv` estos 12 archivos exactos (ni uno más — los `diag_*.py`, `check_*.py` y `smoke_phase*.py` NO se tocan):
   `tmp_db_check.py`, `tmp_db2.py`, `tmp_db3.py`, `tmp_db4.py`, `tmp_db5.py`, `tmp_db6.py`, `tmp_db7.py`, `tmp_db8.py`, `tmp_dbquery.py`, `tmp_pablo_clients.py`, `tmp_rdire_query.py`, `tmp72.py`.
   **(C7) Mover por LISTA LITERAL, jamás por glob:** `tmp72.py` NO matchea `tmp_*` (no tiene guion bajo) — un `git mv tmp_*.py` movería 11 y dejaría 1; los 12 existen (verificado 2026-07-23). El criterio de aceptación usa `grep -c "^tmp"`, que sí cubre a los 12.
   **Pre-check obligatorio (antes de mover):** `grep -rn "import tmp_\|from tmp_\|tmp_db\|tmp_pablo\|tmp_rdire\|tmp72" --include="*.py" .` excluyendo los propios archivos → debe dar **0 hits** fuera de ellos mismos. Si diera >0, NO mover ese archivo y reportarlo (no improvisar).
2. EDITAR `run_tests.py` (28 líneas, reescritura completa permitida — es un script suelto, nadie lo importa):
   ```python
   import os, subprocess, sys
   from pathlib import Path

   BASE = Path(__file__).resolve().parent          # antes: ruta hardcodeada RSPACIFICO (muerta)
   env = os.environ.copy()

   secrets = os.environ.get("AGENDA_WEB_ENV_FILE", "").strip()
   if secrets and Path(secrets).is_file():
       with open(secrets, encoding="utf-8") as f:
           for line in f:
               line = line.strip()
               if line and not line.startswith("#") and "=" in line:
                   k, v = line.split("=", 1)
                   env.setdefault(k.strip(), v.strip())   # setdefault: no pisar lo ya exportado
   # Defaults de smoke local (solo si no vinieron por env):
   env.setdefault("AGENDA_WEB_USER", "PACIFICO")
   env.setdefault("AGENDA_WEB_PASS", "PACIFICO")
   env.setdefault("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")

   specs = sys.argv[1:]   # los specs se pasan por CLI; sin args → mensaje de uso, exit 2
   if not specs:
       print("uso: python run_tests.py <spec.ts> [<spec.ts> ...]"); sys.exit(2)
   cmd = r'"node_modules\.bin\playwright.cmd" test ' + " ".join(f'"{s}"' for s in specs) + " --reporter=list"
   result = subprocess.run(cmd, cwd=str(BASE), env=env, shell=True)
   sys.exit(result.returncode)
   ```
   Casos borde: sin `AGENDA_WEB_ENV_FILE` → sigue con defaults; archivo de secrets inexistente → sigue sin cargar (no crashea).
3. EDITAR `Flujo_QA_UAT.md`: agregar al final una sección `## Cómo correr los tests (canónico)` con los dos comandos de §4 (tool y specs Playwright vía `run_tests.py`), literal.

**Tests (TDD adaptado — fase de higiene, la validación es estructural):** no se crea pytest nuevo; el criterio es binario por comandos.

**Criterio de aceptación (binario) + comandos:**
- `ls "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent" | grep -c "^tmp"` → **0**; `ls "...\_attic" | wc -l` → **12**.
- `grep -c "RSPACIFICO" "N:\...\QA UAT Agent\run_tests.py"` → **0**.
- Smoke del arnés real: `& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\unit\test_navigation_driver.py -q` (desde la raíz del tool) → exit 0 (prueba que el conftest + venv funcionan en la ubicación NUEVA).
- `python -m compileall run_tests.py` → exit 0 (con el mismo venv).

**Flag:** ninguna — higiene interna del tool, sin comportamiento operador-visible.
**Impacto por runtime:** ninguno (los 3 usan el tool igual).
**Trabajo del operador:** ninguno.

---

### F1 — Inventario de la base de conocimiento (KB) + curación de playbooks

**Objetivo (1 frase):** medir y crecer la KB de navegación (playbooks/ui_maps, hoy 1+2) con un inventario determinista consultable por API y un curador que valida las grabaciones antes de promoverlas a playbook.

**Valor:** ataca la causa raíz del "se desvía al navegar": sin ui_map/playbook, el agente improvisa. Con inventario visible, el gap deja de ser invisible; con curación, cada sesión grabada del operador se convierte en conocimiento estable.

**Archivos a crear:**
- `Stacky tools/QA UAT Agent/navigation_kb.py`:
  ```python
  """navigation_kb.py — Inventario determinista de la KB de navegación (Plan 214 F1)."""
  import argparse, json, sys
  from pathlib import Path
  import yaml   # ya es dependencia del pipeline (navigation_contracts.yml se parsea con yaml)

  _TOOL_ROOT = Path(__file__).resolve().parent

  def load_contract_screens(contracts_path: Path | None = None) -> list[str]:
      """Claves top-level de navigation_contracts.yml que parezcan pantallas .aspx.
      Devuelve [] si el archivo no existe o no parsea (nunca lanza)."""
      path = contracts_path or (_TOOL_ROOT / "navigation_contracts.yml")
      try:
          data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
      except Exception:
          return []
      return sorted(k for k in data.keys() if isinstance(k, str) and k.lower().endswith(".aspx"))

  def kb_inventory(root: Path | None = None) -> dict:
      """Cruza pantallas declaradas x ui_maps x playbooks. Puro, sin red, nunca lanza."""
      base = root or _TOOL_ROOT
      screens = load_contract_screens(base / "navigation_contracts.yml")
      ui_maps = sorted(p.stem for p in (base / "cache" / "ui_maps").glob("*.json"))
      playbooks = sorted(p.stem for p in (base / "cache" / "playbooks").glob("*.json"))
      missing_ui_maps = [s for s in screens if s not in ui_maps]
      covered = len(screens) - len(missing_ui_maps)
      coverage_pct = round(100.0 * covered / len(screens), 1) if screens else 0.0
      return {"ok": True, "screens_declared": screens, "ui_maps": ui_maps,
              "playbooks": playbooks, "playbooks_total": len(playbooks),
              "missing_ui_maps": missing_ui_maps, "coverage_pct": coverage_pct}
  ```
  CLI en el mismo archivo: `--report` (imprime el JSON de `kb_inventory()`), `--json-out <path>` (además lo escribe). Exit 0 siempre que el inventario se produzca (aunque la cobertura sea 0).
  Casos borde: `cache/ui_maps` o `cache/playbooks` inexistentes → listas vacías (glob sobre dir inexistente = []); YAML corrupto → `screens_declared: []`, `coverage_pct: 0.0`.
- `Stacky tools/QA UAT Agent/playbook_curator.py`:
  ```python
  """playbook_curator.py — Valida y promueve grabaciones a playbooks (Plan 214 F1)."""
  # curate(session_dir, dry_run=True) -> dict
  # 1) Llama session_to_playbook.run(session_dir=Path(...), dry_run=dry_run, verbose=False)
  #    (firma verificada: session_to_playbook.py:47-51).
  # 2) Si ok y no dry_run: valida el playbook escrito contra schemas/Playbook.schema.json:
  #    required = json.loads((_TOOL_ROOT/"schemas"/"Playbook.schema.json").read_text(encoding="utf-8")).get("required", [])
  #    → cada key de required debe existir en el playbook JSON. SIN dependencia jsonschema nueva:
  #    validación estructural por presencia de keys (determinista, cero deps).
  # 3) Si falta una key required: renombra el archivo escrito a <slug>.rejected.json y
  #    devuelve {"ok": false, "error": "playbook_schema_invalid", "missing": [...]}.
  # 4) Devuelve {"ok": true, "playbook_path": "...", "validated": true} en éxito.
  ```
  CLI: `--session <dir>` (requerido), `--dry-run`, patrón espejo del CLI de `session_to_playbook.py:464-478`.
- `Stacky tools/QA UAT Agent/tests/unit/test_plan214_navigation_kb.py` (TDD, escribir ANTES de los módulos):
  - `test_inventory_vacio`: con `root=tmp_path` (sin nada) → `screens_declared == []`, `coverage_pct == 0.0`, `ok is True`.
  - `test_inventory_cruza_bien`: fixture tmp con `navigation_contracts.yml` (2 pantallas `A.aspx`, `B.aspx`), `cache/ui_maps/A.aspx.json` → `missing_ui_maps == ["B.aspx"]`, `coverage_pct == 50.0`.
  - `test_yaml_corrupto_no_lanza`: contracts con bytes basura → `screens_declared == []` sin excepción.
  - `test_curator_valida_required`: playbook tmp sin una key required del schema → `ok is False`, `error == "playbook_schema_invalid"`, archivo renombrado a `.rejected.json`.
  - `test_curator_dry_run_no_escribe`: `dry_run=True` → no aparece archivo nuevo en `cache/playbooks/`.

**Archivos a editar:**
- `Stacky Agents/backend/api/qa_uat.py`: nuevo endpoint read-only al final del blueprint:
  ```python
  @bp.get("/kb")
  def get_kb_inventory():
      """Inventario de la KB de navegación (Plan 214 F1). Read-only, best-effort."""
      _ensure_pipeline_on_path()          # helper existente, api/qa_uat.py:66
      try:
          import navigation_kb
          return jsonify(navigation_kb.kb_inventory())
      except Exception as exc:
          return jsonify({"ok": False, "error": "kb_unavailable", "message": str(exc)}), 200
  ```
  (200 con `ok:false`, no 5xx: el pane de F4 lo consume best-effort. Patrón de los GET existentes del blueprint, que no llevan flag.)
- `Stacky Agents/backend/tests/test_plan214_qa_uat_kb_endpoint.py` (TDD):
  - `test_kb_endpoint_ok`: `GET /api/qa-uat/kb` con la app de test → 200 y body con keys `ok, screens_declared, ui_maps, playbooks, coverage_pct` (espejo de fixtures de `tests/test_qa_uat_endpoint.py` para el app factory — copiar su patrón de fixture, no inventar uno).
  - `test_kb_endpoint_degrada`: monkeypatch `navigation_kb.kb_inventory` para lanzar → 200 `ok False error kb_unavailable`.
  - **Registrar en `HARNESS_TEST_FILES`** (sh y ps1).

**Loop de crecimiento de la KB (opt-in documentado, EXCEPCIÓN DURA #3):** con AgendaWeb corriendo + credenciales + browsers instalados, el operador (o el agente en un run) crece la KB con los comandos EXACTOS (van también a `Flujo_QA_UAT.md`, sección `## Crecer la base de navegación`):
```powershell
cd "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent"
# 1) Grabar una demo humana del flujo (login automático; el operador navega; Ctrl+C al terminar):
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" session_recorder.py --goal "alta de obligacion desde agenda"
# 2) Curar la grabación a playbook validado:
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" playbook_curator.py --session evidence\recordings\latest
# 3) Ver cobertura:
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" navigation_kb.py --report
```
Esto NO es un paso manual obligatorio nuevo: sin hacerlo, todo lo demás funciona igual que hoy (el inventario simplemente reporta la cobertura baja). Es la palanca para subir KPI-1/KPI-2.

**Criterio de aceptación (binario):**
- Tool: `...python.exe -m pytest tests\unit\test_plan214_navigation_kb.py -q` → 5/5 verde.
- Backend: `...python.exe -m pytest tests\test_plan214_qa_uat_kb_endpoint.py -q` → 2/2 verde.
- `grep -n "get_kb_inventory" "Stacky Agents/backend/api/qa_uat.py"` → ≥1.

**Flag:** ninguna nueva (endpoint read-only, patrón de los GET existentes del blueprint; los módulos del tool son CLI locales).
**Impacto por runtime:** los 3 consumen la misma KB (el agente Claude en F5, el Codex en F5, el pipeline directamente). Fallback: KB vacía → comportamiento actual.
**Trabajo del operador:** ninguno obligatorio; crecer la KB es opt-in (excepción #3 citada).

---

### F2 — Navegación WebForms-safe + detección temprana de desvío con replan acotado

**Objetivo (1 frase):** que cada paso de navegación use el patrón WebForms-safe (`noWaitAfter` + espera corta de idle ASP.NET + validación de llegada por DOM) y que un desvío se detecte EN el paso (no al final del flujo), disparando el replan acotado existente.

**Valor:** es el corazón de "sin desviarse ni fallar durante la navegación": los postbacks de WebForms rompen las esperas default de Playwright; validar llegada por DOM convierte "siguió navegando en la pantalla equivocada" en una señal NAV accionable en el momento.

**Archivos a editar (tool):**
1. `Stacky tools/QA UAT Agent/navigation_driver.py`:
   - NUEVO helper module-level (antes de `class NavigationDriver`, línea ~206):
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
         Poll cada 100ms. True=idle, False=timeout. NUNCA lanza."""
         import asyncio, time
         deadline = time.monotonic() + (timeout_ms / 1000.0)
         while time.monotonic() < deadline:
             try:
                 if await page.evaluate(_ASPNET_IDLE_JS):
                     return True
             except Exception:
                 pass   # navegación en curso: evaluate puede fallar transitoriamente
             await asyncio.sleep(0.1)
         return False
     ```
   - **(C1 — anclajes exactos verificados; NO existen `self._page` ni `self._timeout_ms`):** el atributo real es **`self.page`** (`navigation_driver.py:224`) y `timeout_ms` es **parámetro local** de los métodos (no atributo). Dos sitios de edición:
     1. `via_link_click` (`navigation_driver.py:280`, el `await locator.click()` está en `:300`): cambiar a `await locator.click(no_wait_after=True)` (API Python de Playwright) e, inmediatamente después, insertar `await wait_aspnet_idle(self.page, min(timeout_ms, 5000))` usando el `timeout_ms` local del método, ANTES de los `wait_for_url`/lecturas de URL existentes.
     2. `_execute_nav` (`navigation_driver.py:342`, firma con `timeout_ms` local en `:349`): inmediatamente después de cada acción que dispare postback en su cuerpo (el trigger JS de `__doPostBack` vía `self.page.evaluate`, `:364`), insertar `await wait_aspnet_idle(self.page, min(timeout_ms, 5000))` ANTES de cualquier aserción o lectura de URL.
     NO quitar los timeouts/esperas existentes: el idle-wait es adicional y corto. Si al implementar aparece otro sitio con `click(` sobre controles de postback, aplicar el mismo par (kwarg + idle-wait) y anotarlo en el commit.
   - NUEVO método:
     ```python
     async def assert_arrival(self, expected_screen: str) -> dict:
         """Valida por DOM que estamos en expected_screen. {'ok': bool, 'deviation': str|None}.
         1) Carga cache/ui_maps/{expected_screen}.json; toma el primer elemento con 'id'.
            Si existe: self.page.locator(f"#{el_id}").count() > 0 => ok.
         2) Fallback (sin ui_map): expected_screen.lower() in current_url.lower() => ok.
         3) No-ok => {'ok': False, 'deviation': f'expected={expected_screen} url={current_url}'}.
         NUNCA lanza; ante error de I/O devuelve fallback por URL."""
     ```
   - En `_classify_error` (`navigation_driver.py:496`): nueva rama — si el string contiene `"NAV_DEVIATION"` → devolver `"NAV_DEVIATION"` (clase nueva del contrato). En `_execute_nav`, cuando `assert_arrival` da `ok=False` tras agotar el retry del paso: construir el `NavigationResult` con error `f"NAV_DEVIATION: {deviation}"` y sacar screenshot (`_screenshot`, `:482`) como evidencia.
2. `Stacky tools/QA UAT Agent/replan_engine.py`:
   - En `_classify_failure` (`replan_engine.py:256`): nueva rama ANTES de las genéricas — si el texto del fallo contiene `"NAV_DEVIATION"` → `ReplanDecision` con `category="NAV"`, `action="switch_human_path"`: en `_apply_patch` (`:401`), si `navigation_contracts.yml` declara para esa pantalla otro `human_paths` no intentado aún, patchear el intent_spec para usarlo; si no hay alternativa → decisión `abort_round` (el veredicto queda FAIL/NAV honesto). `MAX_REPLAN_ROUNDS = 3` NO se toca.
3. `Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2`:
   - Inyectar al inicio del template un helper TS:
     ```ts
     async function waitForAspNetIdle(page, timeoutMs = 3000) {
       const deadline = Date.now() + timeoutMs;
       while (Date.now() < deadline) {
         try {
           const idle = await page.evaluate(() => {
             if (document.readyState !== 'complete') return false;
             try {
               const prm = (window as any).Sys?.WebForms?.PageRequestManager?.getInstance();
               if (prm && prm.get_isInAsyncPostBack()) return false;
             } catch (e) {}
             return true;
           });
           if (idle) return true;
         } catch (e) {}
         await page.waitForTimeout(100);
       }
       return false;
     }
     ```
   - Y en los bloques del template que emiten `click(` sobre controles de postback: emitir `{ noWaitAfter: true }` + `await waitForAspNetIdle(page);` en la línea siguiente. (Solo el template: los specs YA generados en `playwright/uat/*.spec.ts` no se regeneran en esta fase.)
4. `Stacky tools/QA UAT Agent/qa_uat_pipeline.py`: en el resumen del stage runner (donde se arma `stages["runner"]`), agregar el contador `nav_deviations` = cantidad de resultados con clase `NAV_DEVIATION` (sumar desde el runner output; 0 si no hay). Aditivo: ningún consumidor existente se rompe por una key nueva.
5. **(C5 — huella de regresión)** `Stacky Agents/docs/sistema/error_fingerprints.json` (registro real consumido por `backend/services/error_fingerprints.py:18`): AGREGAR una entrada con id `qa_uat_nav_deviation` para la clase "QAUAT se desvía de la ruta de navegación" — **leer primero el JSON y copiar el shape exacto de una entrada existente** (no inventar keys); el patrón de matching es el literal `NAV_DEVIATION`. Aditivo puro: una entrada nueva al array, jamás editar entradas ajenas.

**Tests (TDD — escribir ANTES; tool, pytest por archivo):**
- `tests/unit/test_plan214_webforms_idle.py`:
  - `test_idle_inmediato`: fake page cuyo `evaluate` devuelve True → `wait_aspnet_idle` True en <300ms.
  - `test_idle_tras_polls`: evaluate devuelve False,False,True → True.
  - `test_timeout_devuelve_false`: evaluate siempre False → False (no lanza) con `timeout_ms=300`.
  - `test_evaluate_lanza_no_rompe`: evaluate lanza siempre → False (no propaga).
- `tests/unit/test_plan214_nav_deviation.py`:
  - `test_assert_arrival_por_ui_map`: tmp ui_map con elemento id `btnGuardar`; fake locator count 1 → ok True.
  - `test_assert_arrival_desvio`: locator count 0 y URL sin la pantalla → ok False + deviation con `expected=`.
  - `test_classify_error_nav_deviation`: `_classify_error("NAV_DEVIATION: expected=X url=Y", "http://...")` → `"NAV_DEVIATION"`.
  - `test_replan_switch_human_path`: fixture contracts con 2 human_paths; fallo NAV_DEVIATION → decisión `switch_human_path`; con 1 solo path → `abort_round`.
  - `test_template_contiene_helper`: leer `templates/playwright_test.spec.ts.j2` → contiene `waitForAspNetIdle` y `noWaitAfter: true` (test de presencia, anti-regresión del template).

**Criterio de aceptación (binario):** los 2 archivos de test → verdes por archivo; `grep -c "no_wait_after=True" navigation_driver.py` → ≥1; `grep -c "NAV_DEVIATION" navigation_driver.py replan_engine.py` → ≥1 en cada uno; `grep -c "waitForAspNetIdle" templates/playwright_test.spec.ts.j2` → ≥2 (definición + al menos un uso); `grep -c "qa_uat_nav_deviation" "Stacky Agents/docs/sistema/error_fingerprints.json"` → ≥1 y `python -m json.tool` sobre ese JSON → exit 0 (C5). Regresión: `...python.exe -m pytest tests\unit\test_navigation_driver.py -q` y `tests\unit\test_navigation_plan_gate.py -q` siguen verdes (contratos previos intactos).

**Flag:** ninguna — robustez interna del tool; `wait_aspnet_idle` devuelve True casi inmediato en páginas sin ScriptManager (backward-safe), y `assert_arrival` degrada a chequeo por URL cuando no hay ui_map (comportamiento equivalente al actual).
**Impacto por runtime:** los 3 se benefician idéntico (driver y template son del pipeline determinista). El agente Claude (F5) recibe la MISMA regla vía prompt.
**Trabajo del operador:** ninguno.

---

### F3 — Disparo post-desarrollo por el chokepoint `on_execution_end` (208-compatible) + autorun opt-in

**Objetivo (1 frase):** cuando el Developer completa un ticket, Stacky deja preparada (y visible) la validación QAUAT E2E de ese ticket — y, solo si el operador activó el autorun, lanza el pipeline en dry-run.

**Valor:** cierra "una vez finalizado un desarrollo, el agente pueda tomarlo": hoy nadie conecta dev-terminado → QA E2E.

**Archivos a crear:**
- `Stacky Agents/backend/services/qa_uat_enqueue.py`:
  ```python
  """qa_uat_enqueue.py — Plan 214 F3: candidato de validación QAUAT al completar el Developer.

  Post-hook runtime-agnóstico (mismo patrón que incident_autopublish): se registra en
  ticket_status.register_post_hook y se dispara desde on_execution_end en los 3 runtimes.
  """
  import json, logging
  from datetime import datetime, timezone

  logger = logging.getLogger("stacky_agents.qa_uat_enqueue")

  _TRIGGER_AGENT_TYPES = frozenset({"developer"})   # extensible en el futuro; NUNCA "qa-uat"
  _OK_FINAL = "completed"   # único terminal de éxito del vocabulario canónico (gotcha 208 C2:
                            # final_status ya pasó por _coerce_terminal_status; "done"/"success"
                            # NO existen y needs_review NO es éxito)

  def _enabled() -> bool:
      from config import config as _cfg          # INSTANCIA config.config (gotcha: el módulo
      return bool(getattr(_cfg, "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED", True))   # mata el OFF)

  def _autorun_enabled() -> bool:
      from config import config as _cfg
      return bool(getattr(_cfg, "STACKY_QA_UAT_AUTORUN_ENABLED", False))

  def _post_hook(*, ticket_id, execution_id, final_status, agent_type=None, error=None, **kwargs) -> None:
      """Firma EXACTA esperada por register_post_hook (ticket_status.py:310). Nunca lanza."""
      try:
          if not _enabled(): return
          if final_status != _OK_FINAL: return
          if (agent_type or "") not in _TRIGGER_AGENT_TYPES: return   # anti-recursión: qa-uat jamás
          from db import session_scope                                # import exacto (db.py, no models)
          from models import AgentExecution, Ticket
          ado_id = None
          with session_scope() as session:
              row = session.query(AgentExecution).filter(AgentExecution.id == execution_id).first()
              if row is None: return
              t = session.query(Ticket).filter(Ticket.id == ticket_id).first()
              ado_id = getattr(t, "ado_id", None)
              if not ado_id: return                                   # sin ADO id no hay run QAUAT
              md = dict(row.metadata_dict)                            # property models.py:260-265
              if "qa_uat_candidate" in md: return                     # idempotente (reintentos/zombies)
              build = md.get("build_verdict") or {}                   # gate best-effort Plan 210
              status = "blocked_by_build" if build.get("gate_ok") is False else "pending"
              md["qa_uat_candidate"] = {
                  "status": status,
                  "ado_id": int(ado_id),
                  "mode": "dry-run",
                  "suggested_at": datetime.now(timezone.utc).isoformat(),
                  "source": "on_execution_end",
              }
              row.metadata_dict = md
          if status == "pending" and _autorun_enabled():
              from api.qa_uat import start_qa_uat_run                 # import LAZY (patrón 209 C6:
              start_qa_uat_run(int(ado_id), mode="dry-run",           #  evita ciclo service->api al boot)
                               started_by="qa-uat-auto")              # dry-run LITERAL: jamás publish
      except Exception:
          logger.debug("qa_uat_enqueue post_hook fallo (best-effort)", exc_info=True)

  def register(register_fn) -> None:
      """Espeja incident_autopublish.register: register_fn == ticket_status.register_post_hook."""
      register_fn(_post_hook)
  ```
  Casos borde: ejecución sin ticket ADO (`ado_id` None) → no-op; hook llamado dos veces (retry) → idempotente por presencia de la key; DB caída → capturada por el try externo, log debug, jamás rompe la completación.

**Archivos a editar:**
- `Stacky Agents/backend/api/qa_uat.py`: extraer del cuerpo del route `run_pipeline` (`:76-171`) el helper reutilizable, y que el route lo llame:
  ```python
  def start_qa_uat_run(ticket_ado_id: int, *, mode: str = "dry-run", headed: bool = False,
                       timeout_ms: int = 30_000, started_by: str = "qa-uat-auto") -> int:
      """Crea la AgentExecution qa-uat + lanza _run_pipeline_in_background. Devuelve execution_id.
      Lanza ValueError si el ticket ADO no existe en la DB local (el route lo traduce a 404)."""
  ```
  Reglas de extracción: mover TAL CUAL la creación de `AgentExecution` (agent_type `_AGENT_TYPE`, `metadata_dict`, `input_context`), `log_streamer.open/push` y el `threading.Thread` (`:160-167`); el route `run_pipeline` queda: validaciones de payload (idénticas) → `execution_id = start_qa_uat_run(ticket_id, mode=mode, headed=headed, timeout_ms=timeout_ms, started_by=current_user())` → mismo JSON 202. **Prohibido cambiar el contrato HTTP** (mismos códigos 400/404/202, mismo body).
- `Stacky Agents/backend/app.py`: junto a `:853-855`, AGREGAR (sin tocar las líneas existentes):
  ```python
  from services import qa_uat_enqueue
  qa_uat_enqueue.register(ticket_status.register_post_hook)   # Plan 214 — QAUAT post-desarrollo
  ```
  (Si el 208 ya mergeó `completion_dispatcher` en ese bloque: agregar DEBAJO, jamás reordenar — memoria `gotcha-merge-silent-duplicate-keyword`.)
  **(C4 — garantía de orden para leer `build_verdict`):** verificado en código: `on_execution_end` corre `set_status(...)` (`ticket_status.py:270-278`) ANTES de `_run_post_hooks` (`:279-286`), así que si el 210 escribe `build_verdict` en el camino de aplicación de estado (su diseño v2), este hook lo ve. Regla para quien implemente el 210: si su gate se materializara como post-hook, DEBE registrarse en `app.py` ANTES que `qa_uat_enqueue.register(...)` — el orden de `_POST_HOOKS` es el orden de registro (`ticket_status.py:313,:326`). Si aun así el campo no está, la degradación ya prevista aplica: candidato `pending` (best-effort honesto, nunca bloquea).
- Flags (**5 lugares** — C2; NO hand-editar `harness_defaults.env`):
  1. `backend/services/harness_flags.py` → `FLAG_REGISTRY` (`:379`):
     ```python
     FlagSpec(key="STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED", type="bool", group="global",
         label="Sugerir validacion QAUAT al completar el Developer",
         description="Al completar el Developer un ticket, deja preparado el candidato de validacion E2E (QA UAT) visible en la ejecucion. No corre nada ni publica nada por si solo. Default ON.",
         default=True),
     FlagSpec(key="STACKY_QA_UAT_AUTORUN_ENABLED", type="bool", group="global",
         label="Autorun QAUAT (dry-run) al completar el Developer",
         description="Lanza automaticamente el pipeline QA UAT en dry-run al completar el Developer. Requiere AgendaWeb local corriendo, credenciales agenda_web.env y browsers Playwright instalados. Default OFF.",
         default=False,
         requires="STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED"),   # C2: el autorun vive DENTRO del
         # hook gateado por la otra flag; sin requires, autorun ON + encolado OFF = no-op mudo.
         # El campo requires existe en FlagSpec (harness_flags.py:30); profundidad 1 → cumple R4.
     ```
  2. `_CATEGORY_KEYS` (`:117`): ambas keys bajo `calidad_verificacion`.
  3. `backend/config.py` (espejo del patrón `config.py:1192-1194`):
     ```python
     STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED: bool = os.getenv("STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED", "true").lower() in ("1", "true", "yes")
     STACKY_QA_UAT_AUTORUN_ENABLED: bool = os.getenv("STACKY_QA_UAT_AUTORUN_ENABLED", "false").lower() in ("1", "true", "yes")
     ```
  4. `backend/tests/test_harness_flags.py` → `_CURATED_DEFAULTS_ON` (`:467`): agregar **SOLO** `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` (la de autorun es default OFF: NO va).
  5. **(C2)** `backend/tests/test_harness_flags_requires.py` → `_REQUIRES_MAP_FROZEN` (`:120`): agregar la arista `"STACKY_QA_UAT_AUTORUN_ENABLED": "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED"` — SOLO la propia (gotcha `_FROZEN_BOUNDS deuda ajena`: no tocar aristas ajenas aunque el test estuviera rojo por otras).

**Tests (TDD — crear `Stacky Agents/backend/tests/test_plan214_qa_uat_enqueue.py`; fixtures espejo de `tests/test_qa_uat_endpoint.py`):**
- `test_flags_registradas_y_defaults`: ambas en `FLAG_REGISTRY` + `_CATEGORY_KEYS`; `config.Config` con ON/OFF respectivos; solo la primera en `_CURATED_DEFAULTS_ON`; **el FlagSpec de autorun tiene `requires == "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED"` y la arista está en `_REQUIRES_MAP_FROZEN`** (C2).
- `test_hook_ignora_no_completed`: `final_status="error"` → sin `qa_uat_candidate` en metadata.
- `test_hook_ignora_agente_no_developer`: `agent_type="qa-uat"` y `agent_type="functional"` → no-op (anti-recursión y scope).
- `test_hook_escribe_candidato`: developer + completed + ticket con `ado_id` → metadata con `qa_uat_candidate.status == "pending"` y `mode == "dry-run"`.
- `test_hook_idempotente`: segunda llamada con la misma ejecución → metadata sin duplicar (una sola key, mismo `suggested_at`).
- `test_hook_respeta_build_verdict`: metadata previa con `build_verdict.gate_ok == False` → `status == "blocked_by_build"`.
- `test_flag_off_no_escribe`: `monkeypatch.setattr(config.config, "STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED", False)` (la INSTANCIA) → no-op.
- `test_autorun_off_por_default_no_llama`: spy sobre `api.qa_uat.start_qa_uat_run` → 0 llamadas con defaults.
- `test_autorun_on_llama_dry_run`: `monkeypatch.setattr(config.config, "STACKY_QA_UAT_AUTORUN_ENABLED", True)` + spy → 1 llamada con `mode == "dry-run"`.
- **Registrar el archivo en `HARNESS_TEST_FILES`** (`run_harness_tests.sh` y `.ps1`).

**Criterio de aceptación (binario):** `...python.exe -m pytest tests\test_plan214_qa_uat_enqueue.py -q` → 9/9; `grep -n "qa_uat_enqueue.register" "Stacky Agents/backend/app.py"` → 1; `grep -n "def start_qa_uat_run" "Stacky Agents/backend/api/qa_uat.py"` → 1; regresión `...python.exe -m pytest tests\test_qa_uat_endpoint.py -q` → verde (contrato HTTP intacto).

**Flags:** `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` default **ON** (solo escribe metadata local: no publica, no ejecuta, no toca ADO → ninguna excepción dura aplica). `STACKY_QA_UAT_AUTORUN_ENABLED` default **OFF** por **EXCEPCIÓN DURA #3** (prerequisito no garantizado: AgendaWeb local en `:35017`, `agenda_web.env`, browsers Playwright); aun ON, corre SOLO dry-run (G2) y el preflight del pipeline (`environment_preflight`, `qa_uat_pipeline.py:400-424`) degrada a BLOCKED/ENV honesto si el entorno no está.
**Impacto por runtime:** paridad por construcción — el hook vive en `on_execution_end`, llamado por los 3 runners. Fallback: si un runner no cerrara por `on_execution_end` (no existe hoy), simplemente no hay candidato (cero daño).
**Trabajo del operador:** ninguno; activar autorun es opt-in (excepción #3 citada).

---

### F4 — Veredicto preciso y visible en la UI (pane data-driven, cero clic extra)

**Objetivo (1 frase):** que el veredicto normalizado (PASS|FAIL|BLOCKED|MIXED + categoría NAV|DATA|ENV|APP), las weak assertions, los desvíos y el candidato post-dev aterricen en la UI de Stacky sin trabajo del operador.

**Valor:** "verificar correctamente el funcionamiento" exige que el resultado se VEA con su nivel de confianza real, no enterrado en un JSON de evidencia.

**Archivos a editar (backend):**
- `Stacky Agents/backend/api/qa_uat.py` → `_run_pipeline_in_background` (`:203-337`): en el punto donde hoy se persiste el resultado final en la metadata de la ejecución (localizarlo con `grep -n "verdict\|metadata_dict" api/qa_uat.py` dentro de esa función; NO adivinar), EXTENDER el dict persistido con estas keys best-effort (`.get` encadenados sobre el output del pipeline; si el campo no está, se omite — jamás lanzar):
  - `verdict` (ya existe), `verdict_reason` (reason code del normalizador), `verdict_category` (`NAV|DATA|ENV|APP` — viene de `verdict_normalizer.ReasonCodeMeta.category`),
  - `nav_deviations` (int, de `stages.runner.nav_deviations`, F2),
  - `weak_assertions_count` (int, del reporte del `weak_assertion_detector` si el dossier lo trae),
  - `replan_rounds` (int, de `stages` si el pipeline replaneó),
  - `playbooks_used` (list[str] si el runner la reporta).
  Regla dura: SOLO agregar keys al dict de metadata existente (patrón `md = dict(row.metadata_dict); md.update(...); row.metadata_dict = md`), jamás reasignar el dict entero pisando keys ajenas (208/210/213 escriben keys hermanas).
- **[ADICIÓN ARQUITECTO] Cierre de loop bidireccional (best-effort, mismo `_run_pipeline_in_background`):** tras persistir el veredicto en la ejecución qa-uat, buscar la ÚLTIMA `AgentExecution` con `agent_type == "developer"` del MISMO ticket cuya metadata contenga `qa_uat_candidate`, y actualizar (con la misma regla de merge de metadata) SOLO estas sub-keys del candidato: `status` → `"validated"` si verdict `PASS`, `"failed"` si `FAIL|MIXED`, `"blocked"` si `BLOCKED`; y `qa_uat_execution_id` → id del run qa-uat. Si no hay tal ejecución o cualquier error: no-op silencioso (try/except + log debug). Así la tarjeta del Developer deja de decir "sugerida" cuando la validación ya corrió — cero clic del operador, y el link ejecución↔validación queda navegable. NO cambia estados ADO ni publica nada (HITL intacto, G2).

**Archivos a crear (frontend):**
- `frontend/src/components/qaUatVerdictModel.ts` — helpers PUROS (sin React, sin fetch):
  ```ts
  export type QaUatVerdict = "PASS" | "FAIL" | "BLOCKED" | "MIXED" | "SKIPPED";
  export function verdictTone(v: string | undefined): "success" | "danger" | "warning" | "neutral";
  //   PASS→success; FAIL→danger; BLOCKED/MIXED→warning; otro/undefined→neutral
  export function categoryLabel(c: string | undefined): string;
  //   (C3) Mapea las 9 categorías reales del CATEGORY_SET (verdict_normalizer.py:47-57):
  //   NAV→"Navegación", DATA→"Datos", ENV→"Entorno", APP→"Aplicación", PIP→"Pipeline",
  //   GEN→"Generación", OBS→"Evidencia", SEC→"Seguridad", OPS→"Infraestructura".
  //   Desconocida no-vacía → devolver el código CRUDO (nunca ocultar señal); undefined/vacía → "—"
  export function weaknessNote(weakCount: number | undefined, verdict: string | undefined): string | null;
  //   PASS con weakCount>0 → "PASS con N assertions débiles — revisar evidencia"; si no → null
  export function candidateLabel(c: {status?: string} | undefined): string | null;
  //   pending→"Validación E2E sugerida"; blocked_by_build→"E2E en espera: build sin verificar";
  //   [ADICIÓN ARQUITECTO] validated→"Validación E2E corrida: PASS"; failed→"Validación E2E corrida: FALLÓ";
  //   blocked→"Validación E2E corrida: BLOQUEADA (entorno)"; otro→null
  ```
- `frontend/src/components/QaUatVerdictPane.tsx` + `QaUatVerdictPane.module.css`:
  - Renderiza SOLO si hay datos (data-driven): para ejecuciones `agent_type === "qa-uat"` con `metadata.verdict` → badge de veredicto (tono por `verdictTone`), categoría, `nav_deviations`, `weaknessNote`, `replan_rounds`, `playbooks_used`; para ejecuciones `agent_type === "developer"` con `metadata.qa_uat_candidate` → tarjeta con `candidateLabel` y botón "Validar E2E (dry-run)" que llama el endpoint existente `POST /api/qa-uat/run` (helper ya tipado en `frontend/src/api/endpoints.ts:2450`) con `{ ticket_id: candidate.ado_id, mode: "dry-run" }` y muestra el `stream_url` devuelto como link a logs.
  - **Cero inline-style** (ratchet uiDebt): todo estilo en el `.module.css` con `var(--token)` (nada de HEX nuevos).
- Wiring: `frontend/src/components/OutputPanel.tsx` — insertar `<QaUatVerdictPane execution={...} />` junto al render de `StructuredOutput` (`OutputPanel.tsx:140`, seam ya usada por el enriquecimiento de deliverables). Aditivo: si la metadata no trae los campos, el pane devuelve `null`.
- Test: `frontend/src/components/__tests__/qaUatVerdictModel.test.ts` (SOLO el modelo puro — RTL/jsdom NO están instalados en este frontend, gotcha estructural):
  - `verdictTone`: los 5 veredictos + undefined.
  - `categoryLabel`: las **9** categorías del CATEGORY_SET + desconocida (`"XYZ"` → `"XYZ"` crudo) + undefined (`"—"`) (C3).
  - `weaknessNote`: PASS+3 → string con "3"; PASS+0 → null; FAIL+3 → null.
  - `candidateLabel`: pending / blocked_by_build / validated / failed / blocked / undefined.
- Tests backend del back-link (ADICIÓN — van en `tests/test_plan214_qa_uat_enqueue.py`, que ya monta fixtures de ejecuciones+tickets; se implementan en F4):
  - `test_backlink_actualiza_candidato`: run qa-uat PASS sobre ticket cuyo Developer tiene `qa_uat_candidate` → `status == "validated"` + `qa_uat_execution_id` seteado; las demás keys del candidato intactas.
  - `test_backlink_sin_candidato_noop`: sin ejecución Developer con candidato → no lanza, nada cambia.
  Para testeabilidad, el back-link se implementa como helper nombrado `_update_dev_candidate(ticket_id, verdict, qa_execution_id)` en `api/qa_uat.py` (llamado desde `_run_pipeline_in_background`).

**Criterio de aceptación (binario):** `npx vitest run src/components/__tests__/qaUatVerdictModel.test.ts` → verde; `cd "Stacky Agents/frontend" && npx tsc --noEmit` → exit 0; `grep -n "QaUatVerdictPane" src/components/OutputPanel.tsx` → 1; `grep -c "style={{" src/components/QaUatVerdictPane.tsx` → **0**; backend: `...python.exe -m pytest tests\test_plan214_qa_uat_enqueue.py -q` → **11/11** (los 9 de F3 + los 2 del back-link) y `grep -n "def _update_dev_candidate" "Stacky Agents/backend/api/qa_uat.py"` → 1.

**Flag:** sin flag frontend propia — el gating es server-side: el candidato SOLO existe en metadata si `STACKY_QA_UAT_ON_DEV_COMPLETE_ENABLED` está ON (F3), y el pane es data-driven (sin datos, no renderiza). Backward-compatible por construcción.
**Impacto por runtime:** idéntico (la UI lee metadata; los 3 runtimes la producen por el mismo pipeline/hook).
**Trabajo del operador:** ninguno; el botón "Validar E2E (dry-run)" es un clic OPCIONAL que hoy no existe ni como opción.

---

### F5 — Paridad 3 runtimes: playbooks-first en QAUat1 y en los planes del Codex Browser

**Objetivo (1 frase):** que los DOS caminos agénticos (Claude Code y Codex Browser) consuman la MISMA KB de navegación que el pipeline determinista, en vez de improvisar la navegación.

**Valor:** sin esto, la KB de F1 solo mejora el fallback determinista; con esto, los 3 runtimes navegan con el mismo conocimiento (paridad real, no declarada).

**Archivos a editar:**
1. `Stacky Agents/backend/Stacky/agents/QAUat1.agent.md` — agregar (sección nueva, después de la regla de "explorar por código primero"; bump de versión en el frontmatter):
   ```markdown
   ## PLAYBOOKS PRIMERO (obligatorio)
   Antes de abrir el navegador para CUALQUIER flujo:
   1. Lee `Stacky tools/QA UAT Agent/navigation_contracts.yml` y localiza la pantalla objetivo.
   2. Lista `Stacky tools/QA UAT Agent/cache/playbooks/` y `cache/ui_maps/`.
   3. Si existe un playbook que cubre el flujo: SEGUILO LITERAL (mismos selectores, mismo orden).
      Solo desviate si un paso falla, y registra el desvío con su motivo.
   4. Si NO existe playbook: navega usando el `human_paths` del contrato de la pantalla; si la
      pantalla no está en el contrato, decláralo como limitación (categoría NAV) en el reporte.
   5. En WebForms: clicks de postback con `noWaitAfter: true` + espera corta de idle ASP.NET
      (readyState complete y sin async postback del PageRequestManager) + validación por DOM
      de que llegaste a la pantalla esperada. Nunca esperas largas ciegas.
   6. En el `comment.meta.json` del handoff, completa `playbooks_used` con los playbooks seguidos.
   ```
2. `Stacky Agents/backend/services/qa_browser_plan.py` — nueva función PURA + su uso:
   ```python
   def playbook_candidates(pipeline_root) -> list[dict]:
       """Lee cache/playbooks/*.json del tool y los mapea a plan candidates.
       Cada item: {"id": <stem>, "title": <goal o stem>, "source": "playbook",
                   "steps": <len(steps) si existe, 0 si no>}.
       JSON inválido => se saltea (log debug). Dir inexistente => []. NUNCA lanza."""
   ```
   e integrarla donde `build_guarded_browser_spec` arma sus `plan_candidates` (verificado: `qa_browser_plan.py:27-28` — `def build_guarded_browser_spec(data: BrowserRunInput)` toma los candidatos de `data.context.get("plan_candidates")`; los de playbook se AGREGAN a los existentes, nunca los reemplazan). **(C8 — contrato público con callers):** NO cambiar la firma de forma rompiente — agregar parámetro keyword con default: `def build_guarded_browser_spec(data: BrowserRunInput, *, pipeline_root: Path | None = None)`; con `None` (todos los callers actuales) el comportamiento es byte-idéntico al de hoy. El caller de `api/qa_browser.py` pasa el root real, resuelto con el mismo `_PIPELINE_ROOT` de `api/qa_uat.py:58` (importarlo, no duplicar la constante).
3. (Documental) La fila Copilot de la tabla §5 no requiere cambios: su camino ES el pipeline determinista.

**Tests (TDD):** `Stacky Agents/backend/tests/test_plan214_qa_browser_playbooks.py`:
- `test_candidates_dir_inexistente`: tmp sin `cache/playbooks` → `[]`.
- `test_candidates_json_invalido_se_saltea`: 1 válido + 1 corrupto → 1 candidato.
- `test_candidates_shape`: playbook con `goal` y `steps` → item con `id/title/source/steps` exactos.
- `test_spec_incluye_playbooks`: `build_guarded_browser_spec` con un playbook en tmp root → el spec resultante contiene el candidato con `source == "playbook"` junto a los candidatos previos.
- **Registrar en `HARNESS_TEST_FILES`** (sh y ps1).

**Criterio de aceptación (binario):** `...python.exe -m pytest tests\test_plan214_qa_browser_playbooks.py -q` → 4/4; `grep -n "PLAYBOOKS PRIMERO" "Stacky Agents/backend/Stacky/agents/QAUat1.agent.md"` → 1; `grep -n "def playbook_candidates" "Stacky Agents/backend/services/qa_browser_plan.py"` → 1. Regresión: `...python.exe -m pytest tests\test_qa_browser_plan.py -q` → verde.

**Flag:** ninguna nueva — aditivo puro: sin playbooks en cache, ambos caminos se comportan EXACTO como hoy.
**Impacto por runtime:** Claude → prompt endurecido; Codex → candidatos enriquecidos; Copilot → sin cambios (ya usa el fallback determinista). Fallback de los 3: pipeline determinista.
**Trabajo del operador:** ninguno.

---

### F6 — Cierre: baseline de KPIs + smoke E2E documentado (manual, opt-in)

**Objetivo (1 frase):** dejar registrado el baseline medible de la reactivación y el guion exacto del smoke E2E manual que valida el circuito completo con AgendaWeb viva.

**Archivos a editar:** `Stacky tools/QA UAT Agent/Flujo_QA_UAT.md` — sección nueva `## Smoke E2E de reactivación (Plan 214)` con el guion literal:
```powershell
# Prerequisitos (EXCEPCIÓN #3): AgendaWeb en http://localhost:35017/AgendaWeb/, agenda_web.env, chromium de Playwright.
cd "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent"
# 1) Baseline de KB:
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" navigation_kb.py --report
# 2) Pipeline completo dry-run sobre un ticket real ya desarrollado (ej. el último del Developer):
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" qa_uat_pipeline.py --ticket <ADO_ID> --mode dry-run
# 3) Verificar en la salida: stages.runner.nav_deviations, verdict y categoría.
# 4) En la UI de Stacky: la ejecución del Developer muestra la tarjeta "Validación E2E sugerida";
#    el run qa-uat muestra el pane de veredicto.
```
**Criterio de aceptación (binario):** la sección existe (`grep -n "Smoke E2E de reactivación" Flujo_QA_UAT.md` → 1). La CORRIDA del smoke es manual y queda explícitamente como pendiente post-implementación (mismo tratamiento que los smokes E2E de los planes 153/166/177).

**Flag:** ninguna. **Impacto por runtime:** n/a (documental). **Trabajo del operador:** ninguno obligatorio (el smoke es opt-in, excepción #3).

---

## 7. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|--------|------------|
| R1 | El autorun dispara pipelines contra un entorno caído → ruido de BLOCKED | Default OFF (excepción #3); aun ON, `environment_preflight` (etapa ya existente, `qa_uat_pipeline.py:400-424`) produce BLOCKED/ENV honesto sin abrir navegador; el veredicto BLOCKED-ENV se ve como "Entorno", no como fallo del desarrollo |
| R2 | Colisión de edición en `app.py` con el 208 (`completion_dispatcher`) | Bloque propio ADITIVO debajo de `:853-855`; quien implemente segundo integra, jamás reescribe; verificación post-merge: `grep -c "register(ticket_status.register_post_hook)" app.py` == cantidad de hooks esperada |
| R3 | Claves de metadata pisadas entre planes (208/210/213/214 escriben en `execution.metadata`) | Regla dura F3/F4: leer `metadata_dict`, mutar copia, reasignar — jamás reconstruir el dict desde cero; keys propias con prefijo `qa_uat_` |
| R4 | `assert_arrival` con ui_maps viejos → falsos NAV_DEVIATION | Degradación por capas: sin ui_map → chequeo por URL (equivalente a hoy); el desvío NUNCA es terminal por sí solo: pasa por `replan_engine` (≤3 rondas) y termina en veredicto honesto con screenshot |
| R5 | El post-hook toca DB en el hilo de completación | Escritura única O(ms) con `session_scope`; `try/except` total propio + captura del runner de hooks (`ticket_status.py:325-331`); cero red |
| R6 | Sesión paralela viva en el árbol compartido (TicketBoard/UnblockerPage) | Prohibición explícita de tocar esos archivos (§Planes relacionados); la UI va por `OutputPanel.tsx` + componentes nuevos; commits SIEMPRE con pathspec explícito |
| R7 | `run_tests.py` usado por algún script externo con su contrato viejo | El contrato viejo estaba MUERTO (ruta inexistente en este árbol): nadie puede estar usándolo con éxito; el nuevo exige args explícitos y falla claro (exit 2 con uso) |
| R8 | Crecer la KB exige demo humana (¿trabajo del operador?) | No es obligatorio: sin demos, todo funciona como hoy; cada demo es una inversión opcional de ~2 min que el recorder ya automatiza (login incluido) y el curador valida — trabajo que HOY el operador hace a mano cada vez que QA falla, ahora se captura una vez |

## 8. Fuera de scope (explícito)

- Transicionar estados ADO al terminar QAUAT (es del Plan 208, matriz por work_item_type × agent_type; QAUAT participará vía la matriz cuando el operador la configure).
- Publicación automática a ADO de dossiers (sigue HITL: `mode=publish` explícito + política `check_run_publish_policy`).
- Auto-ejecución de SQL seeds (gobernanza v2.0 del roadmap SEGUNDA_PARTE: `PROPOSE_SQL_SEED → HUMAN_APPROVAL` intacta).
- Regenerar los specs existentes de `playwright/uat/*.spec.ts` con el template nuevo (solo el template cambia; regeneración cuando el pipeline los regenere naturalmente).
- Visión/screenshot-IA para detección de errores (el `screen_error_detector` LLM-visión queda como está).
- Tocar `TicketBoard.tsx`, `UnblockerPage.tsx`, `TicketGraphView.jsx` (sesión paralela viva).
- Limpieza de `diag_*.py` / `smoke_phase*.py` / `check_*.py` de la raíz del tool (solo los 12 `tmp_*` listados; el resto puede tener valor diagnóstico y se evalúa en otro plan).

## 9. Glosario

- **AgendaWeb:** aplicación web ASP.NET WebForms del producto RS del cliente (default `http://localhost:35017/AgendaWeb/`), objetivo de las pruebas E2E.
- **WebForms / postback:** modelo de ASP.NET donde los controles reenvían la página entera (`__doPostBack`) o parcial (UpdatePanel + ScriptManager); rompe las esperas default de Playwright → patrón `noWaitAfter` + espera de idle + validación DOM.
- **ui_map:** JSON en `cache/ui_maps/<Pantalla>.aspx.json` con los elementos/selectores estables de una pantalla (lo produce `ui_map_builder.py`).
- **playbook:** JSON en `cache/playbooks/<slug>.json` con los pasos parametrizados y validados de un flujo de navegación (lo produce `session_to_playbook.py` desde una grabación de `session_recorder.py`).
- **dossier:** paquete de evidencia del run (screenshots, resultados, triage) que arma `uat_dossier_builder.py`.
- **handoff:** exportación del resultado a `Agentes/outputs/<ADO_ID>/` (`comment.html` + `attachments.json` + `comment.meta.json`) para que Stacky publique centralmente.
- **NAV / DATA / ENV / APP:** las 4 categorías de falla más frecuentes para el operador — Navegación (no llegó/se desvió), Datos (faltan datos de prueba), Entorno (AgendaWeb caída, credenciales), Aplicación (bug real del desarrollo). **(C3)** Son un SUBCONJUNTO del `CATEGORY_SET` canónico de **9** (`verdict_normalizer.py:47-57`), que suma `PIP` (pipeline roto), `GEN` (generación/ui_map faltante), `OBS` (evidencia incompleta), `SEC` (seguridad) y `OPS` (infraestructura); la UI (F4) las muestra todas.
- **dry-run vs publish:** dry-run = corre y deja evidencia local, no publica nada; publish = Stacky publica el resultado (HITL, decisión del operador).
- **chokepoint `on_execution_end`:** único punto runtime-agnóstico donde Stacky se entera de que un agente terminó (`services/ticket_status.py:231`), con post-hooks registrables (`register_post_hook:307`). Patrón establecido por el Plan 208.
- **candidato QAUAT (`qa_uat_candidate`):** marca en la metadata de la ejecución del Developer que dice "este desarrollo está listo para validarse E2E". Estados: `pending`, `blocked_by_build` (F3) y, tras correr la validación, `validated | failed | blocked` con `qa_uat_execution_id` (back-link de F4, ADICIÓN ARQUITECTO).
- **weak assertion:** aserción de test que pasa sin verificar nada sustantivo (detectadas por `weak_assertion_detector.py`); un PASS con weak assertions se anota, nunca se oculta.

## 10. Orden de implementación

1. **F0** — higiene + arnés veraz (desbloquea confianza en todos los tests siguientes).
2. **F1** — `navigation_kb.py` + `playbook_curator.py` + endpoint `/kb` (tests tool + backend).
3. **F2** — WebForms-safe + `NAV_DEVIATION` + template (tests tool; regresión de `test_navigation_driver.py`).
4. **F3** — flags + `qa_uat_enqueue.py` + `start_qa_uat_run` + wiring `app.py` (tests backend; regresión `test_qa_uat_endpoint.py`).
5. **F4** — metadata extendida + `qaUatVerdictModel.ts` + pane + wiring OutputPanel (vitest + tsc).
6. **F5** — QAUat1.agent.md + `playbook_candidates` en qa_browser (tests backend; regresión `test_qa_browser_plan.py`).
7. **F6** — doc de smoke + baseline KPI.

## 11. Definición de Hecho (DoD) global

- [ ] Los **6** archivos de test nuevos (2 tool + 3 backend + 1 vitest — C9: v1 decía "5" con la suma mal) verdes, corridos POR ARCHIVO con los comandos exactos de §4, output real leído (cero "pasó todo" sin pegar salida). `test_plan214_qa_uat_enqueue.py` termina en 11/11 (9 de F3 + 2 del back-link de F4).
- [ ] Los 3 `backend/tests/test_plan214_*.py` registrados en `HARNESS_TEST_FILES` (sh **y** ps1); meta-ratchet verde.
- [ ] Regresiones nombradas verdes: `test_navigation_driver.py`, `test_navigation_plan_gate.py`, `test_qa_uat_endpoint.py`, `test_qa_browser_plan.py`, `test_harness_flags.py` (por archivo).
- [ ] `grep` sentinels de cada fase (F0-F5) en verde, tal como se listan en cada criterio de aceptación.
- [ ] Flags visibles en Configuración → Arnés (categoría `calidad_verificacion`); `STACKY_QA_UAT_AUTORUN_ENABLED` OFF por default con su excepción #3 documentada en la description, **con `requires=` hacia la flag de encolado y la arista en `_REQUIRES_MAP_FROZEN` (C2)**.
- [ ] Huella `qa_uat_nav_deviation` sembrada en `docs/sistema/error_fingerprints.json` y el JSON sigue parseando (C5).
- [ ] Con flags en default y KB vacía: comportamiento de Stacky byte-idéntico salvo aditivos declarados (candidato en metadata + pane data-driven + endpoint `/kb`).
- [ ] `npx tsc --noEmit` limpio en frontend; `compileall` limpio en los módulos Python tocados.
- [ ] Raíz del tool sin `tmp_*.py`; `run_tests.py` sin rutas RSPACIFICO.
- [ ] Smoke E2E manual documentado (F6) y marcado como pendiente-post-implementación (excepción #3), igual que los smokes de 153/166/177.
- [ ] Ningún archivo prohibido tocado (`TicketBoard.tsx`, `UnblockerPage.tsx`, `TicketGraphView.jsx`); `git status` revisado antes de commitear, commits con pathspec explícito.
