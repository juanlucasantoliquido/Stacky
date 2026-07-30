# Plan 274 — El QAUAT deja de esperar de gusto: navegación eficiente y fin de la infraestructura huérfana

> **Estado:** PROPUESTO (v1)
> **Fecha:** 2026-07-30
> **Origen:** auditoría de eficiencia de navegación pedida por el operador (agente QA/UAT + Playwright sobre AgendaWeb).
> **Advertencia sobre este header:** el campo `Estado:` **NO es evidencia**. Hay precedente de 7 planes cuyo header decía
> IMPLEMENTADO sin serlo, y de 2 planes de este mismo linaje (240, 241) cuyo header dice "falta implementar" cuando el
> código ya está en `main`. Verificá siempre con `git log --all --grep="plan-274"` y con los greps de §4.

---

## §1. Objetivo y KPI

**Objetivo (1 párrafo).** El agente QA/UAT ya sabe navegar AgendaWeb sin desviarse (plan 214), sin URLs `?q=` que
matan la sesión (plan 240), con aserciones que saben fallar (plan 241) y recuperándose en caliente de una ruta
inválida (plan 262). Lo que **nunca** se auditó es cuánto **desperdicia** en el camino. Este plan ataca exclusivamente
la **eficiencia**: elimina las esperas de reloj incondicionales que están horneadas en el generador de specs, deja de
sacar una captura de pantalla por paso pase lo que pase, deja de mentir sobre el paralelismo, y —sobre todo— **conecta
la infraestructura de eficiencia que ya está escrita, testeada y sin usar**: 4462 líneas verificadas de módulos de
navegación, validación de llegada, presupuesto de capturas, calidad de selectores y cache de datos que **ningún camino
de producción invoca**. El patrón es idéntico al que encontró la auditoría UX/UI del 2026-07-29: *no falta construir,
falta conectar*.

**KPI (medidos, con el comando que los produce en §4).**

| KPI | Hoy (medido) | Meta del plan | Cómo se verifica |
|---|---|---|---|
| **KPI-1** — ms de espera de reloj incondicional en los specs vivos | **35 900 ms** (26 llamadas) | **≤ 3 000 ms** (solo las que un test pruebe necesarias) | comando `C-1` de §4 |
| **KPI-2** — esperas de reloj horneadas en el generador maestro | **1** (`templates/playwright_test.spec.ts.j2:608`) | **0** | comando `C-2` |
| **KPI-3** — `page.screenshot()` incondicionales por paso en el generador | **17** de 19 | **≤ 2** (setup + final), el resto gobernado por presupuesto | comando `C-3` |
| **KPI-4** — módulos de eficiencia con 0 importadores de producción (corpus CERRADO de 11, §2.3) | **11 de 11** | **≤ 5 de 11** (6 conectados o borrados con veredicto escrito) | comando `C-4` |
| **KPI-5** — etapas del pipeline que consultan el deadline de 6 min | **2 de 38** | **≥ 8 de 38** (las 6 más largas + las 2 actuales) | comando `C-5` |
| **KPI-6** — el paralelismo configurable es real (la env var no se pisa) | **falso** (`--workers=1` hardcodeado en `uat_test_runner.py:355` pisa `QA_UAT_WORKERS`) | **verdadero** (se respeta, con guardia de sesión) | comando `C-6` |

**Impacto esperado sobre una corrida real.** Los 2 specs que concentran el desperdicio (`ado122_provincia_domicilio.spec.ts`
= 21 100 ms, `ado171_emails_oficial.spec.ts` = 14 500 ms) bajan ~33 s de reloj de pared **por corrida y sin tocar la app**.
Sobre el presupuesto declarado del pipeline (6 min por ticket, `qa_uat_pipeline.py:1373`), 33 s son el **9,2 %** del
presupuesto total recuperados de esperas que no verifican nada.

---

## §2. Evidencia de campo (auditoría read-only del 2026-07-30)

> Esta sección **es** la auditoría que pidió el operador. Vive en el documento —y no solo en el chat— porque el
> documento es lo que consume el modelo que implementa. Cada cifra trae el comando que la produjo en §4.
> Todos los comandos se corrieron desde `N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent`.

### §2.1. Estado actual — hay DOS subsistemas, y el grande es el que no corre

El agente QA/UAT no es un subsistema, son dos, con una frontera de proceso en medio:

| | Mundo Python | Mundo TypeScript |
|---|---|---|
| Qué es | Orquestador + generador de specs. ~180 módulos. | Los specs que se ejecutan de verdad. 5 `.spec.ts` + 5 helpers. |
| Punto de entrada | `qa_uat_pipeline.py` (4817 líneas), invocado **in-process** desde `Stacky Agents/backend/api/qa_uat.py:317` (`import qa_uat_pipeline`) y `:323` (`qa_uat_pipeline.run(...)`). | `npx playwright test`, lanzado como **subprocess** en `uat_test_runner.py:352` (arma el comando) y `:395` (`subprocess.Popen`). |
| Quién toca el navegador | **Nadie en producción** (ver §2.3). | Todo. |

La frontera explica el hallazgo central: **un módulo Python no puede conducir un navegador que vive en un proceso Node
separado.** Por eso `navigation_driver.py` (975 líneas de `via_menu` / `via_form_submit` / `via_dopostback` / re-auth en
vivo / backoff exponencial) es código sin destino: el generador (`playwright_test_generator.py`) no lo importa, y el
pipeline tampoco. Lo confirma el propio repo: sus únicas 2 menciones fuera de tests son **comentarios**
(`auth_session_factory.py:629` y `uat_scenario_compiler.py:69`), no imports.

**Ruta del tool (no está donde uno esperaría):** el tool **no vive dentro de `backend/`**. Vive en
`N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent\` y el backend lo alcanza por ruta relativa hardcodeada en
`Stacky Agents/backend/api/qa_uat.py:59-63` (`Path(__file__).resolve().parent.parent.parent.parent / "Stacky tools" / "QA UAT Agent"`),
insertándola en `sys.path` (`qa_uat.py:67-71`).

### §2.2. Flujo de navegación detectado (el que realmente se ejecuta)

```
[1] backend: POST /api/qa-uat/run          -> api/qa_uat.py:211
[2] thread daemon                           -> api/qa_uat.py:165-171
[3] pipeline in-process                     -> api/qa_uat.py:317,323  (import qa_uat_pipeline; .run())
[4] ... 38 etapas (stages[...] = ...) ...   -> qa_uat_pipeline.py  (deadline consultado en solo 2: :1673, :3402)
[5] genera los .spec.ts desde el template   -> playwright_test_generator.py:179 (get_template), :384/:932 (render)
                                               template = templates/playwright_test.spec.ts.j2  (playwright_test_generator.py:51)
[6] runner: UNA sola invocación npx         -> uat_test_runner.py:301 (_run_all_specs_once), :352 (cmd), :395 (Popen)
[7] Playwright globalSetup: auth            -> playwright.config.ts:7 -> playwright/global.setup.ts
      reusa .auth/agenda.json si es válido   -> global.setup.ts:85 (authFile), :91-106 (fingerprint), :116-120 (skip login)
      valida sesión viva por HTTP real       -> playwright/auth_state_validator.ts (TTL 30 min)
[8] cada spec navega                         -> playwright/helpers/webforms_nav.ts  (navigateViaFormSubmit)
      *** único helper TS con importadores reales: 4 ***
[9] evidencia                                -> 17 page.screenshot() incondicionales heredados del template
```

**Lo bueno, que este plan NO debe tocar:** el paso [7] es excelente. La sesión **se reusa de verdad**: `storageState`
persistido en `.auth/agenda.json` (`playwright.config.ts:27`), invalidado por fingerprint de `(user, baseURL)`
(`global.setup.ts:80-106`), y revalidado con un GET HTTP real que detecta redirect a login antes de confiar en la cookie
(`playwright/auth_state_validator.ts`). Es el componente mejor construido del subsistema. **No se rediseña.**

### §2.3. Hallazgos con evidencia (`archivo:línea`)

**H1 (CRÍTICO) — 4462 líneas de infraestructura de eficiencia con CERO importadores de producción.**
Corpus **CERRADO** de 11 módulos (esta lista es normativa; ninguna fase la amplía):

| # | Módulo | Líneas | Qué hace que nadie usa | Importadores prod |
|---|---|---|---|---|
| 1 | `navigation_driver.py` | 975 | `via_menu`/`via_form_submit`/`via_dopostback`, re-auth en vivo, backoff `[1,2,4,8]s` (`:105`) | 0 |
| 2 | `playwright/helpers/navigation_executor.ts` | 793 | ejecutor de navegación TS con reintentos | 0 |
| 3 | `playwright/instrumented_actions.ts` | 601 | acciones instrumentadas (telemetría por acción) | 0 |
| 4 | `deeplink_readiness_checker.py` | 435 | valida un deep link con 7 chequeos (`:118-126`) antes de usarlo | 0 |
| 5 | `playwright/helpers/arrival_validator.ts` | 372 | valida llegada a pantalla | 0 (solo su propio docstring) |
| 6 | `locator_quality.py` | 294 | puntúa fragilidad de un selector | 0 |
| 7 | `playbook_performance.py` | 226 | `recommend_timeout_ms()` = p95×1,5 acotado a `[60s, 600s]` (`:59-60`) | 0 |
| 8 | `test_data_cache.py` | 219 | cachea datos resueltos 8 h para no re-resolverlos | 0 |
| 9 | `screenshot_budget.py` | 208 | `build_ts_budget_block()` (`:154`) genera el gating TS; `1` en éxito / `3` en fallo / `25` techo (`:52-54`) | 0 |
| 10 | `playwright/helpers/grid_precheck.ts` | 172 | pre-chequeo de grilla antes de buscar una fila | 0 |
| 11 | `playwright/helpers/session_guard.ts` | 167 | guardia de sesión | 0 |
| | **TOTAL** | **4462** | | **0 de 11** |

El caso 9 es el más elocuente: el docstring de `screenshot_budget.py` describe **exactamente** el problema que H3
mide (*"cada step exitoso captura pre_step.png + step_completed.png, duplicando el volumen sin valor diagnóstico
(ticket 122: ~56 PNG en 4 escenarios)"*), tiene la función que lo arregla, tiene su propio eval en
`evals/run_screenshot_budget_evals.py` — y **el template nunca lo llama**.

**H2 (ALTO) — 35 900 ms de espera de reloj incondicional en los 5 specs que sí se ejecutan.**

| ms | ocurrencias | archivo |
|---|---|---|
| 21 100 | 17 | `playwright/uat/ado122_provincia_domicilio.spec.ts` |
| 14 500 | 8 | `playwright/uat/ado171_emails_oficial.spec.ts` |
| 300 | 1 | `playwright/smoke/compromiso_minimo.spec.ts` |
| 0 | 0 | `playwright/uat/frm_detalle_clie.spec.ts`, `playwright/uat/ado120_obligaciones.spec.ts` |

Y el foco de contagio: **`templates/playwright_test.spec.ts.j2:608`** → `await page.waitForTimeout(800);` en la rama
`expand_collapsible`. Está en el **generador maestro**, así que **todo spec futuro** hereda ese sleep. En el mismo
archivo ya existen los helpers correctos de espera por estado (`waitForAspNetIdle()` / `waitForAgendaStable()`,
`templates/playwright_test.spec.ts.j2:40-66`) — o sea, la solución está a 40 líneas del problema.

**H3 (ALTO) — 17 de 19 `page.screenshot()` del generador son incondicionales.** Una captura por paso, pase o falle,
en cada rama de acción: `:570` (navigate), `:603` (navigate_webforms), `:609` (expand_collapsible), `:622` (click),
`:633` (fill), `:644` (select), `:654`, `:669` (press_key), `:674` (hover), `:682` (double_click), `:694` (check_checkbox),
`:702` (select_radio), `:710` (clear), `:719` (scroll_into_view), `:555`, más `:496` (setup) y `:798` (final_state).
Ninguna tiene un `if` de éxito/fallo. Contraste: `playwright.config.ts:22` declara `screenshot: 'only-on-failure'` —
esa opción solo gobierna el adjunto **automático** de Playwright, es irrelevante frente a 17 capturas manuales.

**H4 (ALTO) — el paralelismo configurable es una mentira, en 3 capas.**
`playwright.config.ts:13` → `workers: Number(process.env.QA_UAT_WORKERS ?? 1)`. Pero `uat_test_runner.py:355`
inyecta **`"--workers=1"` hardcodeado** en el comando CLI, y el CLI **pisa** el config. Resultado: setear
`QA_UAT_WORKERS=4` no hace nada. Tercera capa: el último reporte real (`reports/playwright-results.json:6`) dice
`"fullyParallel": false`.
**Advertencia de diseño, no un bug a "arreglar" subiendo el número:** AgendaWeb es ASP.NET WebForms y el `storageState`
compartido (`playwright.config.ts:27`) lleva **una sola** cookie `ASP.NET_SessionId`. Dos workers con la misma sesión de
servidor se pisan el contexto (ViewState / cliente en sesión). Subir workers sin sesión por worker **rompe** el
subsistema. Ver F3 y R-2.

**H5 (MEDIO) — cero selectores semánticos; todo cuelga de IDs autogenerados de WebForms.**
En el template: `getByRole`=0, `getByLabel`=0, `getByTestId`=0, `page.locator`=50, `#c_`=4.
En los specs vivos: `getByRole`=0, `getByLabel`=0, `getByTestId`=0, `locator(`=105, `#c_`=35.
Los `#c_...` son IDs que genera ASP.NET a partir de la jerarquía de controles: cambiar un contenedor en el `.aspx`
los renombra en masa. El módulo que puntúa esa fragilidad (`locator_quality.py`, 294 líneas) es el huérfano #6.
**Realismo obligatorio:** no se puede exigir `getByRole` sobre una app que el equipo QA no controla; lo que sí se puede
es **medir** la fragilidad y **anclar por contrato** (F5).

**H6 (MEDIO) — el presupuesto de 6 minutos casi no se consulta.** `qa_uat_pipeline.py:1373` fija
`max_total_minutes = 6`; `:1404` calcula `_deadline`; `:1406-1420` define `_check_deadline(stage_name)` que devuelve
`BLOCKED / EXCEEDED_REASONABLE_RUNTIME`. Pero solo se **invoca en 2 lugares** (`:1673` y `:3402`) sobre **38**
asignaciones de etapa. Es cooperativo: evita *empezar* una etapa tarde, no puede cortar una colgada.

**H7 (MEDIO) — no hay un solo punto donde se fije el timeout por defecto.**
`set_default_timeout` = 0 ocurrencias; `set_default_navigation_timeout` = 0. Hay 182 líneas con `timeout=`, cada
call-site con su valor. Techo real más alto del repo: `playbook_performance.py:60` → `_TIMEOUT_CEILING_MS = 600_000`
(10 min) — en el huérfano #7. Y `uat_test_runner.py:352` pasa `--timeout=90000` (de `_DEFAULT_TIMEOUT_MS = 90_000`,
`:48`) que **pisa** el `timeout: 60000` de `playwright.config.ts:8`.

**H8 (MEDIO) — los 90 archivos de test del tool están FUERA de los dos ratchets del arnés.**
`grep -c "QA UAT Agent" run_harness_tests.sh` → **0**. Idem `.ps1` → **0**. Los ratchets solo registran los tests del
**backend** (`tests/test_plan214_*`, `tests/test_plan241_qa_uat.py`). Consecuencia directa para este plan: **un test
nuevo creado dentro del tool no tiene gate automático**; hay que declarar su comando explícito (F0.3 y §4).

**H9 (BAJO, pero corrige el brief) — no existe el dominio de "turnos".**
`turno|cita|disponibilidad` → 0 ocurrencias. `profesional|recurso` → 0. `fecha|calendar` → solo comentarios y el nombre
de una aserción (`navigation_contracts.yml:239` `agenda_calendar_visible`, que verifica que el **widget** se renderizó).
**"AgendaWeb" acá NO es una agenda de turnos**: es el módulo web de gestión de cartera/cobranza de RecoveryStrategy —
clientes, lotes, obligaciones, demandas judiciales (`navigation_graph.py:63-67`, `navigation_contracts.yml:109-155`).
Por lo tanto: **navegación por fechas → sin evidencia en el código. Localización de turnos/disponibilidades/profesionales/recursos
→ sin evidencia en el código.** El equivalente real es localizar un **cliente/lote/demanda** por grilla + filtro
(`row_click` como acción del grafo, `navigation_graph.py:86`; filtro descrito en `navigation_contracts.yml:149-155`).
Este plan **no inventa** un modelo de turnos.

**H10 (BAJO) — sin evidencia de WebSockets ni de tiempo real.** `ws://`=0, `SignalR`=0, `EventSource`=0. El único hit
de `websocket` es un string en una lista de `resource_type` de filtrado de red (`playwright_forensic_bridge.py:197`).
Coherente: WebForms usa postbacks/`UpdatePanel`, no push. **Nada que optimizar acá.**

**H11 (BAJO) — la limpieza de datos nunca corre sola, y está bien así.** `cleanup_manager.cleanup()` tiene
`dry_run: bool = True` por default (`cleanup_manager.py:119`) y el único caller pasa `dry_run=True` **hardcodeado**
(`qa_uat_pipeline.py:2872`, con el comentario *"always dry_run in pipeline; real cleanup triggered by operator"*).
Es human-in-the-loop correcto (categoría B: DML en una BD del operador). **No se toca.**

### §2.4. Impacto de cada hallazgo

| Hallazgo | Velocidad | Estabilidad | Mantenimiento |
|---|---|---|---|
| H1 huérfanos 4462 líneas | alto (las mejoras existen y no se cosechan) | medio (código no ejercitado se podre) | **muy alto** (11 módulos que un dev cree activos) |
| H2 35,9 s de sleeps | **muy alto** | medio (un sleep corto de más = flaky) | alto (se replica desde el template) |
| H3 17 capturas/paso | medio (I/O + disco) | bajo | medio (ruido en la evidencia) |
| H4 paralelismo falso | alto (potencial sin cobrar) | **crítico si se "arregla" mal** (sesión WebForms única) | alto (config que miente) |
| H5 selectores `#c_` | bajo | **alto** (renombre masivo al tocar el `.aspx`) | alto |
| H6 deadline en 2/38 | medio | medio (etapa colgada agota la corrida) | bajo |
| H7 timeouts dispersos | medio | medio | alto |
| H8 tool fuera del ratchet | — | **alto** (regresiones sin gate) | alto |

### §2.5. Mejoras inmediatas vs estructurales

- **Inmediatas (bajo riesgo, alto impacto):** borrar el `waitForTimeout(800)` del template (H2); reemplazar las 26 esperas
  fijas de los specs vivos por los helpers de estado que ya existen (H2); conectar `screenshot_budget` al template (H3);
  dejar de pisar `QA_UAT_WORKERS` (H4, sin subir el número); extender `_check_deadline` a las 6 etapas más largas (H6).
- **Estructurales (cambio más profundo):** sesión por worker para habilitar paralelismo real (H4); contrato de selector
  con puntuación de fragilidad (H5); veredicto escrito sobre cada uno de los 11 huérfanos — conectar o borrar (H1);
  un único punto de timeout por defecto (H7); meter el tool en los dos ratchets (H8).

---

## §3. Principios y guardarraíles (no negociables)

1. **Human-in-the-loop innegociable.** Este plan no agrega ninguna decisión automática. Nada publica, commitea, pushea
   ni ejecuta DML. `cleanup_manager` sigue en `dry_run=True` (H11).
2. **Mono-operador sin auth real.** Cero RBAC, cero multiusuario. `current_user` sigue siendo un header sin validar.
3. **Paridad de los 3 runtimes (Codex CLI / Claude Code CLI / GitHub Copilot Pro).** Todo lo que este plan toca vive
   en el tool y en los specs `.ts` — **ningún runtime de LLM participa de la ejecución de un spec**. El impacto por
   runtime es por lo tanto **idéntico y neutro** en las 9 fases, y así se declara en cada una (no es una omisión: es el
   hecho de que la frontera de proceso es `npx playwright test`, `uat_test_runner.py:352`).
4. **Cero trabajo extra al operador.** Ninguna fase agrega un paso manual, una credencial ni una config nueva
   obligatoria. Las flags nuevas nacen **ON** (§3.1).
5. **No degradar estabilidad.** Prohibido subir `workers` por default (H4 / R-2). Prohibido bajar un timeout sin un test
   que pruebe que la espera por estado cubre el caso.
6. **Backward-compatible.** Ningún cambio de contrato de `api/qa_uat.py` ni de la forma del reporte. Los specs existentes
   siguen corriendo.
7. **Reusar antes que construir.** Es la tesis del plan: **6 de las 9 fases conectan código que ya existe**; solo F3 y
   F5 escriben lógica nueva, y es mínima.

### §3.1. Flags nuevas — todas ON, con su justificación

| Flag | Tipo | Default | Por qué |
|---|---|---|---|
| `STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED` | bool | **ON** | Solo decide si se saca o no una captura local. Lectura/escritura de PNG en el propio directorio de evidencia del tool. No es (A) ni (B). |
| `STACKY_QA_UAT_STATE_WAITS_ENABLED` | bool | **ON** | Reemplaza sleeps por espera por estado. Sin LLM, sin escritura externa. No es (A) ni (B). |
| `STACKY_QA_UAT_RESPECT_WORKERS_ENABLED` | bool | **ON** | Deja de pisar `QA_UAT_WORKERS`. **Encender esto NO cambia el comportamiento**: el default de la env var sigue siendo `1` (`playwright.config.ts:13`). Solo elimina la mentira. No es (A) ni (B). |
| `STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED` | bool | **ON** | Un GET HTTP de solo lectura contra la propia AgendaWeb local antes de usar un deep link. Es una **lectura**; no es (A) (no llama a un modelo, no corre en reposo: solo cuando ya se decidió usar un deeplink) ni (B) (no escribe nada). |
| `STACKY_QA_UAT_DATA_CACHE_ENABLED` | bool | **ON** | Cachea en disco local el resultado de un `SELECT` ya hecho. Reduce carga sobre la BD del operador; no escribe en ella. No es (A) ni (B). |
| `STACKY_QA_UAT_STAGE_DEADLINE_ENABLED` | bool | **ON** | Extiende un chequeo de reloj ya existente. Cortar por deadline **ya es** el comportamiento actual en 2 etapas. No es (A) ni (B). |

**Ninguna flag de este plan nace OFF.** No hay en este plan ninguna capacidad que queme tokens en reposo (A) ni que
escriba en un sistema real del operador, destruya datos o le saque una decisión (B).

**Las 6 patas obligatorias de cada flag** (si el implementador salta una, la flag no aparece en la UI y el plan queda
a medias — precedente registrado varias veces):
1. `FlagSpec(...)` en `Stacky Agents/backend/services/harness_flags.py` (patrón exacto: `key=`, `type="bool"`, `label=`,
   `description=`, `group="global"`, `env_only=False`, `default=True`) — copiar la forma de
   `harness_flags.py:519-531` (`STACKY_QA_UAT_ADO_BRIDGE_ENABLED`).
2. Constante que la lee en `Stacky Agents/backend/config.py` con `os.getenv(<KEY>, "true")` — junto al bloque de las
   otras QA UAT (`config.py:1224-1240`).
3. Alta en `_CURATED_DEFAULTS_ON` (mismo archivo `harness_flags.py`): hay un test que compara **igualdad de conjuntos**,
   así que una flag `default=True` que no esté curada **rompe el arnés**.
4. Categoría en `_CATEGORY_KEYS` (si el registry lo exige para `group="global"`).
5. `PLAIN_HELP` de la key (texto llano para el panel del operador).
6. Verificación de que aparece en el panel de flags de la UI (`GET /api/harness/flags` la lista).

**Advertencia sobre el comentario que miente:** en `config.py:1230-1231` hay un comentario que dice
*"Default OFF por EXCEPCION DURA #3"* pegado encima de un `os.getenv(..., "true")` (línea 1232-1234). **No copiar ese
patrón.** Si el implementador agrega un comentario, el comentario tiene que decir la verdad sobre el default de la
línea de abajo.

---

## §4. Comandos de verificación (normativos)

> **Regla anti-falso-verde:** todo criterio basado en pytest **debe** exigir el conteo de tests **seleccionados**, no
> solo el exit code. `pytest -k <patrón>` sin match devuelve **exit 0** con `N deselected` — un criterio que solo mira
> `$?` da verde con cero tests corridos. Cada criterio de este plan pide el número de `passed`.

**Intérprete.** Un worktree **no tiene venv propio**. Usar siempre el del árbol principal por ruta absoluta:

```
PY="N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend/venv/Scripts/python.exe"
```

**Correr los tests SIEMPRE por archivo** (hay contaminación cross-run y `SQLITE_LOCKED` en tests de DB):

```bash
# tests del TOOL (recordar H8: NO están en ningún ratchet)
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_<nombre>.py -v
# tests del BACKEND
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
"$PY" -m pytest tests/test_plan274_<nombre>.py -v
```

**Comandos de KPI** (todos desde `N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent`):

```bash
# C-1  KPI-1: ms de espera fija en los specs vivos  (hoy: 26 ocurrencias / 35900 ms)
grep -ohE "waitForTimeout\([0-9]+\)" playwright/uat/*.spec.ts playwright/smoke/*.spec.ts \
  | grep -oE "[0-9]+" | awk '{s+=$1; n++} END {print "ocurrencias="n"  total_ms="s}'

# C-2  KPI-2: esperas fijas horneadas en el generador  (hoy: 1)
grep -c "waitForTimeout(" templates/playwright_test.spec.ts.j2

# C-3  KPI-3: screenshots en el generador  (hoy: 19 totales, 17 incondicionales)
grep -c "page.screenshot(" templates/playwright_test.spec.ts.j2

# C-4  KPI-4: huérfanos del corpus CERRADO de 11  (hoy: 11 de 11 con 0 importadores)
for m in navigation_driver deeplink_readiness_checker locator_quality playbook_performance \
         test_data_cache screenshot_budget; do
  n=$(grep -rln "import ${m}\|from ${m} import" --include=*.py . 2>/dev/null \
      | grep -viE "__pycache__|/tests/|_attic|/evals/|^\./${m}\.py" | wc -l)
  echo "$m -> importadores_prod=$n"
done
for t in navigation_executor arrival_validator grid_precheck session_guard instrumented_actions; do
  n=$(grep -rn "from '.*${t}'" playwright templates 2>/dev/null \
      | grep -viE "node_modules|__tests__" | grep -vE "^\S+:[0-9]+: \*" | wc -l)
  echo "$t.ts -> importadores_reales=$n"
done

# C-5  KPI-5: etapas que consultan el deadline  (hoy: 2 llamadas + 1 definición = 3 líneas)
grep -c "_check_deadline(" qa_uat_pipeline.py

# C-6  KPI-6: el --workers hardcodeado  (hoy: 1 ocurrencia = miente)
grep -n -- "--workers=1" uat_test_runner.py
```

---

## §5. Fases

**Mapeo explícito de las 3 fases pedidas por el operador → las fases de este plan:**

| Fase del brief | Fases de este plan |
|---|---|
| **Fase 1 — mejoras rápidas** (esperas fijas, reuso de sesión, selectores estables, menos pasos repetidos) | **F0, F1, F2, F3** |
| **Fase 2 — optimización de navegación** (accesos directos, datos por API, helpers semánticos, menos navegación visual) | **F4, F5, F6** |
| **Fase 3 — consolidación** (arquitectura mantenible, métricas, paralelización, observabilidad, anti-regresión) | **F7, F8** |

> Nota honesta sobre "reuso de sesión", que el brief pone en Fase 1: **ya está resuelto y bien**
> (§2.2 paso [7]). No hay fase para eso; F0.4 solo lo **congela** con un centinela para que nadie lo rompa.

---

### F0 — Costura, baseline congelado y censo de huérfanos

**Objetivo.** Antes de tocar nada, dejar los números de hoy escritos en un test para que cualquier mejora sea
**demostrable** y cualquier regresión, **visible**. Sin baseline, "más rápido" es una opinión.

**Archivos a crear:**
- `Stacky tools/QA UAT Agent/tests/unit/test_plan274_baseline.py`
- `Stacky tools/QA UAT Agent/tests/unit/test_plan274_orphan_census.py`

**Archivos a editar:** ninguno.

**F0.1 — Baseline de espera fija.** `test_plan274_baseline.py` implementa
`_sum_fixed_waits(paths: list[Path]) -> tuple[int, int]` que devuelve `(ocurrencias, total_ms)` parseando
`waitForTimeout(<N>)` con `re.compile(r"waitForTimeout\((\d+)\)")` sobre la lista **CERRADA** de 5 specs:
```
playwright/uat/ado120_obligaciones.spec.ts
playwright/uat/ado122_provincia_domicilio.spec.ts
playwright/uat/ado171_emails_oficial.spec.ts
playwright/uat/frm_detalle_clie.spec.ts
playwright/smoke/compromiso_minimo.spec.ts
```
- `test_baseline_hoy_es_35900ms` — asserta `total_ms == 35_900` y `ocurrencias == 26`. **Este test debe FALLAR
  cuando F1 mejore el número** — es su señal de éxito, no un error. F1 lo actualiza al valor nuevo en el mismo commit.
- `test_generador_tiene_una_espera_fija` — asserta que `templates/playwright_test.spec.ts.j2` tiene exactamente `1`
  ocurrencia de `waitForTimeout(`. F1 lo baja a `0`.

**F0.2 — Censo de huérfanos.** `test_plan274_orphan_census.py` define la constante
`ORPHAN_CORPUS: dict[str, int]` con las **11** entradas exactas de la tabla H1 (nombre → líneas) y un test
`test_corpus_es_exactamente_once` que asserta `len(ORPHAN_CORPUS) == 11` y `sum(ORPHAN_CORPUS.values()) == 4462`.
Segundo test `test_censo_de_importadores` que, por cada entrada, cuenta importadores de producción con
`_prod_importers(module_name) -> int` (excluye `__pycache__`, `tests/`, `_attic`, `evals/` y el propio archivo) y
asserta el número **esperado de la fase en curso**. Arranca en `11 huérfanos`; cada fase que conecta uno baja el número
esperado **en ese mismo commit**.
> **Por qué el criterio no es "la lista está vacía":** un conteo agregado sobre "cuántos huérfanos quedan" colapsa N
> casos en 1 y no discrimina cuál se conectó. El test asserta **por módulo**, con el nombre en el mensaje de fallo.

**F0.3 — Registrar la deuda de arnés (H8).** Crear
`Stacky Agents/backend/tests/test_plan274_tool_tests_outside_ratchet.py` con un único test
`test_los_tests_del_tool_no_estan_en_el_ratchet` que asserta que `grep "QA UAT Agent"` sobre
`Stacky Agents/backend/scripts/run_harness_tests.sh` **y** `.ps1` da 0, con el mensaje:
*"H8: los 90 tests del tool no tienen gate automático; F8 decide si entran al ratchet o se declara deuda aceptada."*
**Este test documenta el hecho de hoy.** F8 lo invierte si mete el tool al ratchet.
Registrar este archivo en **los DOS** ratchets (`run_harness_tests.sh` **y** `run_harness_tests.ps1` — sintaxis distinta;
el meta-test parsea solo el `.sh`, pero ambos tienen que quedar consistentes).

**F0.4 — Centinela del reuso de sesión (lo que NO hay que romper).** En `test_plan274_baseline.py`, test
`test_reuso_de_sesion_intacto` que asserta que **siguen existiendo**, por lectura de archivo:
`playwright.config.ts` contiene `storageState: '.auth/agenda.json'`; `playwright/global.setup.ts` contiene
`validateAuthState`; `playwright/auth_state_validator.ts` existe. Mensaje de fallo: *"el reuso de sesión del §2.2[7] es
lo mejor del subsistema — si este test falla, alguien lo rompió; revertir."*

**Tests + comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_baseline.py tests/unit/test_plan274_orphan_census.py -v
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
"$PY" -m pytest tests/test_plan274_tool_tests_outside_ratchet.py -v
```
**Criterio de aceptación BINARIO.** Los 3 archivos existen y los comandos de arriba reportan **≥ 6 passed, 0 failed**
(el número de `passed` debe aparecer en la salida; exit 0 con `0 passed` **no cuenta**).
**Flag:** ninguna (solo tests). **Trabajo del operador:** ninguno.
**Runtimes:** neutro en los 3 (§3.3) — son tests locales.

---

### F1 — Matar la espera de reloj: el generador primero, después los specs

**Objetivo.** Que ninguna espera de reloj sobreviva sin un test que pruebe que la espera por estado no alcanza.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2` (línea **608**)
- `Stacky tools/QA UAT Agent/playwright/uat/ado122_provincia_domicilio.spec.ts` (17 ocurrencias)
- `Stacky tools/QA UAT Agent/playwright/uat/ado171_emails_oficial.spec.ts` (8 ocurrencias)
- `Stacky tools/QA UAT Agent/playwright/smoke/compromiso_minimo.spec.ts` (1 ocurrencia)
- `Stacky tools/QA UAT Agent/tests/unit/test_plan274_baseline.py` (actualizar los 2 números)

**F1.1 — El generador (la raíz).** En `templates/playwright_test.spec.ts.j2:608`, reemplazar:
```diff
-    await page.waitForTimeout(800);
+    await waitForAspNetIdle(page);
+    await waitForAgendaStable(page);
```
Los dos helpers **ya están definidos en el mismo archivo** (`:40-66`), no hay que importar nada.
**Caso borde:** si `expand_collapsible` abre un panel con animación CSS pura (sin postback), `waitForAspNetIdle` retorna
de inmediato y el panel puede no estar visible. Cubrirlo con una espera por estado, **no** por reloj: agregar
`await page.locator(<selector del panel>).waitFor({ state: 'visible', timeout: Number(process.env.QA_UAT_ACTION_TIMEOUT_MS ?? 15000) });`.
Si el selector del panel no está disponible en el contexto del template, **dejar el sleep y documentarlo** con un
comentario `// plan-274 F1.1: sleep conservado — sin selector de panel en el contexto del template` y **no** bajar KPI-2
a 0: bajarlo al número real. Prohibido mentir en el número para cerrar la fase.

**F1.2 — Los 26 sleeps de los specs vivos.** Para **cada** ocurrencia, en orden y una por una:
1. Leer las 3 líneas anteriores para saber qué se está esperando.
2. Si sigue a un click/submit de postback → reemplazar por `await waitForAspNetIdle(page)` (importar de
   `../helpers/webforms_nav` si el spec aún no lo importa; `navigateViaFormSubmit` ya se importa en 2 specs).
3. Si sigue a un `fill` y espera un autopostback → misma sustitución.
4. Si espera que aparezca un elemento → `await <locator>.waitFor({ state: 'visible', timeout: ... })`.
5. Si **no se puede determinar qué se espera** → conservar el sleep, **bajarlo a `500`**, y agregar
   `// plan-274 F1.2: espera no determinada — revisar con AgendaWeb arriba`. Contarlo en el KPI real.

**Tests PRIMERO.** Crear `Stacky tools/QA UAT Agent/tests/unit/test_plan274_no_fixed_waits.py`:
- `test_generador_sin_espera_fija_o_documentada` — cada `waitForTimeout(` que quede en el `.j2` debe tener en la
  línea anterior o siguiente el marcador literal `plan-274 F1.1`. Sin marcador → falla nombrando la línea.
- `test_specs_vivos_bajo_umbral` — `_sum_fixed_waits` sobre los 5 specs devuelve `total_ms <= 3000`.
- `test_toda_espera_residual_esta_marcada` — cada `waitForTimeout(` residual en los 5 specs tiene el marcador
  `plan-274 F1.2` adyacente.
> **Este test discrimina de verdad:** no asserta "la lista está vacía" (que un modelo menor satisface borrando el
> assert), asserta **por ocurrencia y con la línea en el mensaje**.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_no_fixed_waits.py -v
bash -c 'grep -ohE "waitForTimeout\([0-9]+\)" playwright/uat/*.spec.ts playwright/smoke/*.spec.ts | grep -oE "[0-9]+" | awk "{s+=\$1} END {print s}"'
```
**Criterio BINARIO.** `test_plan274_no_fixed_waits.py` reporta **3 passed, 0 failed**, Y el comando `C-1` devuelve
`total_ms <= 3000`, Y `C-2` devuelve `0` **o** todas las residuales tienen marcador (lo prueba el primer test).
**Flag:** `STACKY_QA_UAT_STATE_WAITS_ENABLED` (**ON**, §3.1). El flag gobierna el **generador**: con la flag OFF, el
template emite el sleep viejo (rollback sin revertir código). Los specs ya editados no dependen de la flag (son
archivos, no runtime) — **decirlo así en el plan es honesto**: el rollback total de F1.2 es `git revert`, no la flag.
**Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F2 — Presupuesto de capturas: conectar `screenshot_budget.py` (huérfano #9)

**Objetivo.** Pasar de 17 capturas incondicionales por paso a `1 en éxito / 3 en fallo / 25 techo` usando el módulo que
**ya existe y ya está testeado**.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/playwright_test_generator.py` (render del template: `:179`, `:384`, `:932`)
- `Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2` (17 sitios de `page.screenshot`)

**Cómo.** `screenshot_budget.py` ya expone lo necesario: `load_budget()` (`:86`), `should_capture()` (`:116`) y
`build_ts_budget_block(budget)` (`:154`), con los defaults `1/3/25` (`:52-54`).
1. En `playwright_test_generator.py`, junto al `template.render(...)` de `:384` y de `:932`, agregar al contexto:
   `screenshot_budget_block=build_ts_budget_block(load_budget())` (import a nivel de módulo:
   `from screenshot_budget import load_budget, build_ts_budget_block`).
2. En el `.j2`, insertar `{{ screenshot_budget_block }}` una sola vez en el preámbulo (junto a los helpers de `:40-66`)
   y envolver **las 17 capturas por paso** con la función que ese bloque expone:
   ```diff
   -    await page.screenshot({ path: 'evidence/.../step_XX_after.png' });
   +    if (__shouldCapture('success')) {
   +      await page.screenshot({ path: 'evidence/.../step_XX_after.png' });
   +    }
   ```
   **NO envolver** `:496` (setup) ni `:798` (final_state) ni el `afterEach` de `:806` — esas 2+1 son la evidencia
   mínima y quedan siempre.
3. **Casos borde.** Si `load_budget()` lanza (config ausente) → `build_ts_budget_block` debe recibir el
   `ScreenshotBudget` por default; el generador **no debe fallar** por esto: envolver en `try/except Exception` y, en el
   `except`, pasar `screenshot_budget_block=""` + emitir la captura sin guardia (comportamiento de hoy). Degrada, no rompe.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_screenshot_budget_wired.py`:
- `test_generador_importa_el_presupuesto` — `screenshot_budget` tiene ≥ 1 importador de producción (invierte la fila 9
  del censo F0.2).
- `test_template_tiene_el_bloque` — el `.j2` contiene `{{ screenshot_budget_block }}` exactamente 1 vez.
- `test_capturas_por_paso_estan_guardadas` — de las 19 `page.screenshot(` del `.j2`, **≤ 2** están fuera de un
  `if (__shouldCapture(`. El test lista las que quedan sin guardia en el mensaje de fallo.
- `test_generador_degrada_si_el_presupuesto_falla` — monkeypatchear `load_budget` para que lance, y verificar que el
  render **igual produce** un spec válido.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_screenshot_budget_wired.py -v
"$PY" -m pytest tests/unit/test_plan274_orphan_census.py -v
```
**Criterio BINARIO.** `4 passed, 0 failed` en el primero, Y el censo de F0.2 pasa con `screenshot_budget` esperado
en **≥1 importador** (bajando el total de huérfanos de 11 a 10).
**Flag:** `STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED` (**ON**). Con OFF, `build_ts_budget_block` devuelve un bloque cuyo
`__shouldCapture` retorna siempre `true` ⇒ comportamiento idéntico al de hoy. Rollback exacto por flag.
**Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F3 — El paralelismo deja de mentir (sin habilitarlo)

**Objetivo.** Que `QA_UAT_WORKERS` signifique algo, y que subirlo **no pueda** romper la sesión WebForms por accidente.

> **Esta fase NO sube el paralelismo.** Sube la **honestidad**. El default efectivo sigue siendo 1 worker.
> Habilitar paralelismo real requiere sesión por worker, que es F7.3 (declarada, acotada y con riesgo propio).

**Archivos a editar:** `Stacky tools/QA UAT Agent/uat_test_runner.py` (línea **355**).

**Cómo.**
1. Reemplazar el literal `"--workers=1"` por un valor resuelto:
   ```diff
   -        "--workers=1",
   +        f"--workers={_resolve_workers()}",
   ```
2. Agregar `_resolve_workers() -> int` en el mismo módulo, con esta lógica **exacta**:
   ```
   def _resolve_workers() -> int:
       # plan-274 F3. Antes: "--workers=1" hardcodeado pisaba QA_UAT_WORKERS (playwright.config.ts:13).
       if os.environ.get("STACKY_QA_UAT_RESPECT_WORKERS_ENABLED", "true").lower() != "true":
           return 1                                    # flag OFF -> comportamiento histórico exacto
       try:
           n = int(os.environ.get("QA_UAT_WORKERS", "1"))
       except ValueError:
           return 1                                    # basura -> 1, nunca crashea
       if n <= 1:
           return 1
       # GUARDIA DE SESIÓN (H4/R-2): con storageState compartido, N workers comparten
       # UNA cookie ASP.NET_SessionId y se pisan el contexto de servidor.
       if not _has_per_worker_session():
           logger.warning(
               "plan-274 F3: QA_UAT_WORKERS=%d ignorado -> 1. "
               "AgendaWeb es WebForms con sesion unica en storageState (playwright.config.ts:27); "
               "N workers se pisarian el ViewState. Sesion por worker = plan 274 F7.3.", n)
           return 1
       return n
   ```
3. `_has_per_worker_session() -> bool` devuelve **`False` de forma incondicional** en este plan, con un docstring que
   dice que F7.3 es quien la implementa. **Es un stub honesto, declarado como tal** — no una función que finge.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_workers_honest.py`:
- `test_default_sigue_siendo_un_worker` — sin env vars → `_resolve_workers() == 1`.
- `test_flag_off_devuelve_uno` — `STACKY_QA_UAT_RESPECT_WORKERS_ENABLED=false` + `QA_UAT_WORKERS=4` → `1`.
- `test_workers_altos_se_bloquean_por_sesion` — `QA_UAT_WORKERS=4` → `1` **y** se emitió el `logger.warning` con el
  texto `sesion unica` (capturar con `caplog`).
- `test_basura_no_crashea` — `QA_UAT_WORKERS=abc` → `1`, sin excepción.
- `test_el_comando_ya_no_hardcodea_uno` — leer `uat_test_runner.py` y asertar que **no** contiene el literal
  `"--workers=1"`. **Este es el test que corre contra el defecto:** con el código de hoy da ROJO.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_workers_honest.py -v
grep -n -- '"--workers=1"' uat_test_runner.py   # debe devolver 0 lineas
```
**Criterio BINARIO.** `5 passed, 0 failed` Y el `grep` no devuelve ninguna línea.
**Flag:** `STACKY_QA_UAT_RESPECT_WORKERS_ENABLED` (**ON**; encenderla no cambia el comportamiento observable).
**Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F4 — Deep links validados: conectar `deeplink_readiness_checker.py` (huérfano #4)

**Objetivo.** Que cuando el pipeline decida usar un deep link (lo cual **ya hace**), lo pruebe antes de gastar una
corrida en una URL que redirige a login.

> **No contradice el plan 240.** El 240 prohibió las URLs `?q=` con payload cifrado por sesión, porque **destruían la
> sesión**. Este plan **no las resucita**. Los deep links que sí son legítimos son los declarados en el contrato con
> parámetros de negocio (`navigation_contracts.yml:125`: `pattern: "FrmDetalleClie.aspx?clcod={CLCOD}"`), permitidos
> solo en lanes no-humanos (`navigation_contracts.yml:142-144` los prohíbe en `uat_human` / `uat_human_simulation`).
> Esta fase **respeta esa prohibición** y solo agrega un probe donde el deeplink ya está permitido.

**Archivos a editar:** `Stacky tools/QA UAT Agent/navigation_strategy_resolver.py` (bloque `:386-407`, donde hoy se
arma la URL con `pattern.replace(...)` **sin ninguna validación**).

**Cómo.** Justo después de construir `url` y **antes** de devolver `strategy="deeplink"` (`:395`), insertar:
```
if os.environ.get("STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED", "true").lower() == "true":
    try:
        from deeplink_readiness_checker import check_deeplink_readiness
        probe = check_deeplink_readiness(screen=screen, params=params, base_url=base_url)
    except Exception:
        probe = None            # el probe NUNCA decide por una excepcion propia
    if probe is not None and not probe.get("ready", False):
        # el deeplink no sirve -> degradar a la estrategia siguiente, NO bloquear la corrida
        return _fallback_after_failed_deeplink(screen, lane, contract, probe)
```
`_fallback_after_failed_deeplink` devuelve la estrategia que el resolver ya elegiría si el deeplink no estuviera
permitido: `human_path` si el contrato tiene `human_paths` no vacío, si no `direct_entry` cuando
`direct_entry_allowed`, si no `_blocked(...)` con `reason` que incluya el motivo del probe.
**Caso borde crítico (falla ABIERTO, a propósito):** si el probe **no puede** correr (módulo ausente, red caída,
timeout), `probe is None` y el flujo sigue **exactamente como hoy**. Un probe roto no debe bloquear una corrida que
antes funcionaba.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_deeplink_probe.py` (todo con doble, sin red):
- `test_probe_ok_mantiene_deeplink` — probe `ready=True` → `strategy == "deeplink"`.
- `test_probe_redirect_a_login_degrada_a_human_path` — probe `ready=False, reason="redirected_to_login"` y contrato con
  `human_paths` → `strategy == "human_path"`.
- `test_probe_falla_abierto_si_lanza` — `check_deeplink_readiness` lanza → `strategy == "deeplink"` (igual que hoy).
- `test_flag_off_no_llama_al_probe` — flag `false` → el doble **no** se invoca (`assert mock.call_count == 0`).
- `test_lane_humano_sigue_prohibido` — lane `uat_human` con contrato que prohíbe deeplink → **nunca** se llama al probe
  ni se devuelve `deeplink` (centinela del plan 240).

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_deeplink_probe.py -v
"$PY" -m pytest tests/unit/test_plan274_orphan_census.py -v
```
**Criterio BINARIO.** `5 passed, 0 failed` Y el censo baja a **9** huérfanos.
**Flag:** `STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED` (**ON**). **Trabajo del operador:** ninguno.
**Runtimes:** neutro en los 3.

---

### F5 — Fragilidad de selectores medida (no reescrita)

**Objetivo.** Saber **cuáles** de los 140 selectores (105 `locator(` + 35 `#c_`) son bombas de tiempo, y que agregar uno
nuevo peor que el peor de hoy dé rojo. **No** se migra a `getByRole`: la app es WebForms y no expone roles ni test-ids
(H5), así que exigirlo sería inventar alcance.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/qa_uat_pipeline.py` (junto a la etapa que ya usa `selector_contract_validator`, que **sí**
  está cableado)

**Archivos a crear:**
- `Stacky tools/QA UAT Agent/tests/unit/test_plan274_selector_fragility.py`
- `Stacky tools/QA UAT Agent/reports/plan274_selector_baseline.json` (generado por el test la primera vez)

**Cómo.** `locator_quality.py` (huérfano #6, 294 líneas) ya puntúa selectores. Conectarlo **solo como observabilidad**:
en la etapa del pipeline que ya invoca `selector_contract_validator`, agregar el cálculo del score y **loguearlo**
(`logger.info`), más un volcado al reporte de la corrida. **No** cambia ninguna decisión de navegación — es medición
pura, así que no puede degradar estabilidad.

**Test-ratchet (el que da valor).** `test_plan274_selector_fragility.py`:
- `test_baseline_existe_o_se_crea` — si `reports/plan274_selector_baseline.json` no existe, lo genera con el score de
  cada uno de los selectores de los 5 specs + el `.j2`, y pasa (primera corrida).
- `test_ningun_selector_empeora_el_baseline` — recalcula y asserta, **por selector**, que su score no bajó respecto del
  baseline. El mensaje de fallo nombra el selector y las 2 puntuaciones. **Criterio DELTA, no absoluto** — el subsistema
  arranca con deuda y un umbral absoluto lo dejaría rojo de fábrica por deuda preexistente.
- `test_cero_selectores_semanticos_es_el_hecho_de_hoy` — asserta `getByRole == 0 and getByLabel == 0 and getByTestId == 0`
  en los 5 specs, con el mensaje: *"H5: WebForms no expone roles/test-ids; si este test falla es porque alguien logró
  agregar uno — actualizá el número, es una mejora."*

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_selector_fragility.py -v
```
**Criterio BINARIO.** `3 passed, 0 failed`, Y `locator_quality` pasa a **≥1** importador de producción (censo → **8**).
**Flag:** ninguna nueva (es logging + test; el logging va detrás del `logger.info` existente).
**Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F6 — Reusar el dato ya resuelto: conectar `test_data_cache.py` (huérfano #8)

**Objetivo.** Dejar de re-ejecutar el mismo `SELECT` contra la BD del operador en cada corrida cuando el dato no cambió.

> **Contexto real, para que no se sobre-diseñe:** la resolución de datos por SQL **ya está cableada y funciona** —
> `data_resolver.resolve()` (`data_resolver.py:213`) y `resolve_fields()` (`:287`) corren `SELECT` vía `sqlcmd`
> (`:500-558`), invocados desde `qa_uat_pipeline.py:1176` y `:1282`, con whitelist de tablas
> (`sql_query_guard.py:38-55`). **No hay que construir el camino SQL: existe.** El gap es que su resultado se tira.
> Y la **escritura** de datos sigue sin correr sola por diseño (`seed_executor.execute()` sin caller;
> `cleanup_manager` en `dry_run=True`, H11) — **este plan no lo cambia**.

**Archivos a editar:** `Stacky tools/QA UAT Agent/data_resolver.py` (envolver `resolve_fields`, `:287`).

**Cómo.** Cache-aside alrededor de la llamada a `sqlcmd`:
```
# plan-274 F6, en resolve_fields antes de _run_sqlcmd
if _cache_enabled():
    hit = test_data_cache.get_data(cache_key)      # test_data_cache.py:67
    if hit is not None:
        return hit
result = <camino actual>
if _cache_enabled() and result:
    test_data_cache.put_data(cache_key, result)
return result
```
- `cache_key` = hash estable de `(tabla, columnas ordenadas, filtros ordenados)`. **Ordenar** las claves antes de
  hashear, si no el mismo pedido con otro orden de dict genera 2 entradas.
- TTL: el que ya trae el módulo (8 h, `test_data_cache.py:49-50`), **sin inventar uno nuevo**.
- **Bypass ya existente que hay que respetar:** `QA_UAT_FORCE_RUN=true` salta el cache (`test_data_cache.py:72`).
- **Caso borde:** si el cache lanza (JSON corrupto, disco lleno) → `except Exception` → seguir por el camino SQL normal.
  Un cache roto nunca debe romper una resolución que funcionaba.
- **Qué NO cachear:** resultados vacíos (`result` falsy). Cachear un "no encontré" durante 8 h escondería un dato que
  apareció después.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_data_cache_wired.py` (con doble de `_run_sqlcmd`,
sin BD):
- `test_segunda_llamada_no_toca_sqlcmd` — 2 llamadas iguales → el doble se invocó **1** vez.
- `test_clave_estable_ante_orden_de_filtros` — mismos filtros en otro orden → **1** sola invocación.
- `test_force_run_ignora_el_cache` — `QA_UAT_FORCE_RUN=true` → **2** invocaciones.
- `test_flag_off_no_cachea` — flag `false` → **2** invocaciones.
- `test_cache_roto_no_rompe` — `get_data` lanza → se resuelve igual por SQL (1 invocación, sin excepción).
- `test_resultado_vacio_no_se_cachea` — `result = []` → segunda llamada vuelve a consultar (**2** invocaciones).

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_data_cache_wired.py -v
```
**Criterio BINARIO.** `6 passed, 0 failed`, Y censo → **7** huérfanos.
**Flag:** `STACKY_QA_UAT_DATA_CACHE_ENABLED` (**ON**). **Trabajo del operador:** ninguno.
**Runtimes:** neutro en los 3.

---

### F7 — Consolidación: deadline útil, timeout recomendado, y la puerta al paralelismo

**Objetivo.** Que el presupuesto de 6 minutos sirva, que el timeout por caso salga de datos y no de un número mágico, y
que quede **escrito** qué falta exactamente para paralelizar.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/qa_uat_pipeline.py`
- `Stacky tools/QA UAT Agent/uat_test_runner.py`

**F7.1 — `_check_deadline` en las 6 etapas más largas (H6).** Hoy: 2 llamadas (`:1673`, `:3402`). Agregar 6, en las
etapas cuya duración media sea mayor. **Lista CERRADA**, determinada por lectura del propio pipeline: las etapas de
`data_resolution`, `precondition_check`, `seed_generation`, `spec_generation`, `playwright_run` y `evidence_publish`
(usar el nombre literal de la clave `stages["..."]` que exista en el archivo; si un nombre no existe, **usar la etapa
inmediatamente anterior a la asignación más costosa y documentarlo con el número de línea real** — prohibido inventar
una clave).
Patrón exacto, idéntico al de `:1673`:
```
if _dl := _check_deadline(stage):
    return _dl
```
**F7.2 — Timeout recomendado por datos (`playbook_performance.py`, huérfano #7).** En `uat_test_runner.py`, donde hoy
se usa `_DEFAULT_TIMEOUT_MS = 90_000` (`:48`, consumido en `:84` y `:352`), consultar primero
`playbook_performance.recommend_timeout_ms(...)` (p95×1,5, acotado a `[60 000, 600 000]`, `:59-60`) y caer al 90 000
si no hay historial suficiente. **Nunca** por debajo de 60 000 (el propio módulo lo garantiza con su piso), para no
reintroducir el fallo que motivó subir de 30 s a 90 s (comentario en `uat_test_runner.py:48`).
**F7.3 — La puerta al paralelismo, declarada y NO abierta.** Escribir en `uat_test_runner.py`, en el docstring de
`_has_per_worker_session()` (creada en F3), la lista exacta de lo que haría falta: (a) un `storageState` por worker
(`.auth/agenda.w{index}.json`), (b) un usuario de AgendaWeb por worker o una sesión de servidor por worker, (c) verificar
que la BD de test tolera N escrituras concurrentes. **Esta fase NO lo implementa** y `_has_per_worker_session()` sigue
devolviendo `False`. Es alcance de un plan futuro, no una fase encubierta.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_consolidation.py`:
- `test_deadline_en_ocho_etapas` — `grep -c "_check_deadline("` sobre `qa_uat_pipeline.py` ≥ **9** (8 llamadas + 1
  definición). El test cuenta **llamadas** con `\b_check_deadline\(` excluyendo la línea de `def `.
  > **Cuidado con el conteo:** `_check_deadline(` como subcadena también matchea dentro de la definición. Usar
  > el patrón con `\b` y excluir explícitamente las líneas que empiezan con `def `.
- `test_timeout_sale_de_recomendacion` — doble de `recommend_timeout_ms` devolviendo `120_000` → el comando armado
  contiene `--timeout=120000`.
- `test_sin_historial_cae_a_90000` — el doble lanza / devuelve `None` → `--timeout=90000`.
- `test_nunca_baja_de_60000` — el doble devuelve `10_000` → el comando usa **≥ 60000**.
- `test_paralelismo_sigue_cerrado` — `_has_per_worker_session() is False` **y** su docstring contiene las 3 condiciones
  (a)(b)(c). Centinela de que F7.3 no se "implementó" a medias.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_consolidation.py -v
grep -c "_check_deadline(" qa_uat_pipeline.py    # >= 9
```
**Criterio BINARIO.** `5 passed, 0 failed` Y el `grep` ≥ 9, Y censo → **6** huérfanos (`playbook_performance` conectado).
**Flag:** `STACKY_QA_UAT_STAGE_DEADLINE_ENABLED` (**ON**) para F7.1; F7.2 no lleva flag (es un default calculado con
fallback al valor de hoy). **Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F8 — Cierre: veredicto escrito sobre los 5 huérfanos restantes + anti-regresión

**Objetivo.** Que no quede un solo módulo del corpus sin decisión escrita, y que el trabajo de F1..F7 no se deshaga.

**F8.1 — Veredicto por módulo.** Los **5** que quedan huérfanos tras F2/F4/F5/F6/F7 son, exactamente:
`navigation_driver.py` (975), `playwright/helpers/navigation_executor.ts` (793),
`playwright/instrumented_actions.ts` (601), `playwright/helpers/arrival_validator.ts` (372),
`playwright/helpers/grid_precheck.ts` (172), `playwright/helpers/session_guard.ts` (167).
> **Son 6, no 5** — y esa es la cuenta correcta: 11 del corpus − 5 conectados (screenshot_budget, deeplink_readiness_checker,
> locator_quality, test_data_cache, playbook_performance) = **6**. El KPI-4 pide `≤ 5 de 11` **conectados o con veredicto**;
> esta fase entrega el veredicto escrito de los 6, lo cual satisface el KPI. Si el implementador encuentra que la cuenta
> no cierra, **corrige el número en el doc**, no el criterio.

Para cada uno, escribir en una sección nueva `§9. Veredicto del censo` de **este mismo documento** una de dos frases,
con evidencia:
- `MANTENER COMO DEUDA DECLARADA — <razón>, plan futuro <sin número>`, o
- `BORRAR — reemplazado por <archivo:línea que lo reemplaza>`.
**Recomendación fundada del autor de este plan** (el implementador puede cambiarla, pero debe justificar):
`navigation_driver.py` y `navigation_executor.ts` son **duplicación de `webforms_nav.ts`** (el único vivo, 4 importadores)
y su backoff `[1,2,4,8]` está reimplementado en los dos lenguajes (`navigation_driver.py:105` y
`playwright/helpers/webforms_nav.ts:76`) ⇒ **MANTENER COMO DEUDA DECLARADA** (borrar 1768 líneas es un cambio de riesgo
propio, no una fase de este plan). `arrival_validator.ts`, `grid_precheck.ts`, `session_guard.ts` e
`instrumented_actions.ts` ⇒ **MANTENER COMO DEUDA DECLARADA**, candidatos a conectarse en el plan que abra el paralelismo.
**Prohibido borrar código en esta fase.** El entregable es papel: el veredicto.

**F8.2 — Ratchet anti-regresión.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_ratchet.py`:
- `test_no_vuelven_las_esperas_fijas` — `total_ms` de los 5 specs ≤ el valor alcanzado por F1 (leído de
  `reports/plan274_selector_baseline.json` o de una constante actualizada por F1). **Criterio delta.**
- `test_el_generador_no_recupera_capturas_incondicionales` — ≤ 2 `page.screenshot(` sin guardia en el `.j2`.
- `test_el_censo_no_crece` — el número de huérfanos del corpus **CERRADO de 11** no sube. El corpus **no se amplía**:
  un módulo nuevo huérfano no rompe este test (sería alcance infinito). Se declara así explícitamente.
- `test_workers_no_se_rehardcodea` — `uat_test_runner.py` no contiene `"--workers=1"` literal.

**F8.3 — Decisión sobre H8 (el tool fuera del ratchet).** Registrar los **7** archivos de test nuevos de este plan
(`test_plan274_baseline.py`, `test_plan274_orphan_census.py`, `test_plan274_no_fixed_waits.py`,
`test_plan274_screenshot_budget_wired.py`, `test_plan274_workers_honest.py`, `test_plan274_deeplink_probe.py`,
`test_plan274_data_cache_wired.py`, `test_plan274_selector_fragility.py`, `test_plan274_consolidation.py`,
`test_plan274_ratchet.py` — **son 10**, corregir el número al implementar) **en los DOS** ratchets
(`Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1`), **con la ruta del tool**, e invertir
el test de F0.3. Si el arnés no puede correr tests fuera de `backend/` (verificar antes de prometerlo), entonces
**dejar el test de F0.3 tal como está** (documentando la deuda) y anotarlo en §9 — no forzar un registro que no funciona.
> **Advertencia sobre la sintaxis:** `.sh` y `.ps1` **no** tienen la misma sintaxis, y el meta-test del arnés parsea
> solo el `.sh`. Editar los dos y **correr** el meta-test, no solo mirarlo.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_ratchet.py -v
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
"$PY" -m pytest tests/test_plan274_tool_tests_outside_ratchet.py -v
```
**Criterio BINARIO.** `4 passed, 0 failed` en el ratchet, Y §9 de este documento tiene **una línea de veredicto por
cada uno de los 6** módulos restantes, Y la decisión de F8.3 está escrita (registrado **o** deuda aceptada con motivo).
**Flag:** ninguna. **Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

## §6. Riesgos y mitigaciones

| # | Riesgo | Prob. | Mitigación |
|---|---|---|---|
| **R-1** | Quitar un sleep que **sí** era necesario ⇒ flaky nuevo. Es el riesgo principal del plan. | **Alta** | F1.2 obliga a sustituir por espera **por estado**, no a borrar. Si no se puede determinar qué se espera, el sleep se conserva a 500 ms **con marcador**. El smoke manual de §8 es el gate final. |
| **R-2** | Alguien "arregla" H4 subiendo `QA_UAT_WORKERS` ⇒ N workers comparten una sesión ASP.NET y se pisan el ViewState ⇒ falsos rojos masivos. | **Alta si no se mitiga** | F3 agrega el guardia `_has_per_worker_session()` que **fuerza 1** y loguea el motivo. F7.3 escribe qué falta. El test `test_workers_altos_se_bloquean_por_sesion` lo prueba. |
| **R-3** | El probe de deeplink (F4) agrega latencia o falla y bloquea corridas que antes pasaban. | Media | Falla **ABIERTO** por diseño: `probe is None` ⇒ comportamiento de hoy. Flag ON con rollback inmediato. |
| **R-4** | El cache de datos (F6) sirve un dato viejo y produce un falso verde. | Media | TTL 8 h del módulo, `QA_UAT_FORCE_RUN` respetado, y **no se cachean resultados vacíos**. El cache no toca aserciones: el veredicto sigue saliendo del oráculo del plan 241. |
| **R-5** | Bajar capturas (F2) borra la evidencia que el operador necesita para diagnosticar. | Media | `setup`, `final_state` y el `afterEach` de fallo quedan **siempre**. El presupuesto da 3 capturas en fallo (más que 1 en éxito): la evidencia crece justo cuando importa. |
| **R-6** | Los tests nuevos viven en el tool, que está fuera de los ratchets (H8) ⇒ nadie los corre y se podren. | **Alta** | F0.3 lo deja escrito como test; F8.3 lo resuelve o lo declara deuda con motivo. Los comandos de §4 son explícitos para que el implementador los corra a mano. |
| **R-7** | El implementador cierra una fase con `pytest` en exit 0 y **0 tests seleccionados**. | Media | Todo criterio de §5 exige el número de `passed`, no el exit code (§4). |
| **R-8** | Sesión paralela: hay **9 worktrees vivos** y el `wt-plan-262` tiene F0..F11 del 262 sin mergear, tocando `uat_test_runner.py` (el mismo archivo que F3 y F7.2). | **Alta** | **Frontera de merge declarada:** el 262 cablea su recuperación en `uat_test_runner.py:256`; F3 toca `:355` y F7.2 toca `:48/:84/:352`. Son zonas distintas del mismo archivo ⇒ merge de 3 vías sin conflicto, **pero** git puede fusionar sin marcar conflicto y dejar duplicados. Tras cualquier merge con `feat/plan-262-*`, correr `python -m compileall uat_test_runner.py` **y** `grep -c "_resolve_workers" uat_test_runner.py` (debe ser exactamente 2: definición + uso). |
| **R-9** | El plan asume un dominio de "turnos/agenda de citas" que no existe (H9) y se construyen helpers para nada. | Baja (mitigado) | H9 lo declara explícitamente: **sin evidencia** de turnos, fechas, profesionales ni recursos. Ninguna fase de este plan menciona esos conceptos. |

---

## §7. Fuera de scope (explícito)

1. **No se rediseña el reuso de sesión** (§2.2[7]) — está bien hecho; F0.4 solo lo protege.
2. **No se habilita paralelismo real.** F3 sube la honestidad, no los workers. Sesión por worker = plan futuro (F7.3).
3. **No se borra ninguna de las 4462 líneas huérfanas.** F8.1 entrega **veredicto escrito**, no deleciones.
4. **No se migran selectores a `getByRole`/`getByTestId`.** WebForms no los expone (H5). F5 **mide**, no reescribe.
5. **No se toca `cleanup_manager`, `seed_executor` ni ninguna escritura a BD** (H11). Sigue todo `dry_run=True`.
6. **No se implementa navegación por fechas, turnos, profesionales ni recursos** — no existen en el dominio (H9).
7. **No se toca nada de WebSockets / tiempo real** — no existe (H10).
8. **No se unifican los ~54 hardcodeos de `localhost:35017`** — el plan 262 ya lo declaró fuera de alcance por tamaño;
   este plan hereda esa exclusión.
9. **No se rediseñan las 4 taxonomías de error ni el veredicto** — territorio de los planes 241 y 262.
10. **Cero cambios de frontend.** Ningún `.tsx` se toca (igual que 240 y 241).
11. **No se reescribe `qa_uat_pipeline.py`** (4817 líneas). Solo se insertan las 6 llamadas de F7.1 y el logging de F5.
12. **No se agrega ninguna capa LLM.** Todo lo de este plan es determinista.
13. **No se mergea ni pushea nada.** El push es siempre manual.

---

## §8. Glosario, orden de implementación y DoD

### Glosario (para un modelo menor)

- **AgendaWeb** — aplicación web ASP.NET **WebForms** del producto RecoveryStrategy: gestión de cartera/cobranza
  (clientes, lotes, obligaciones, demandas judiciales). **No es una agenda de turnos.**
- **WebForms / postback** — modelo de página con estado en el servidor: un click envía todo el formulario
  (`__doPostBack` / `form.submit()`) y el servidor re-renderiza. Por eso no hay `page.reload()` en el repo (0 ocurrencias):
  la "recarga" es el postback.
- **ViewState** — estado serializado que WebForms manda en el HTML; dos sesiones que se pisan lo corrompen (R-2).
- **`storageState`** — archivo de Playwright con cookies/localStorage que permite saltear el login (`.auth/agenda.json`).
- **Lane** — perfil de corrida del QA/UAT (`uat_human`, `smoke_deeplink`, `nightly-regression`…) que decide si se
  permite un deep link o hay que ir por menú (`navigation_strategy_resolver.py:65,72`).
- **Deep link** — URL que va directo a una pantalla con parámetros (`FrmDetalleClie.aspx?clcod={CLCOD}`). Los `?q=`
  cifrados por sesión están **prohibidos** desde el plan 240.
- **Espera por estado vs espera fija** — `waitForAspNetIdle()` (espera a que el servidor termine) vs
  `waitForTimeout(800)` (duerme 800 ms pase lo que pase). La primera es correcta; la segunda es el desperdicio que este
  plan elimina.
- **Huérfano** — módulo sin ningún importador en código de producción (excluye tests y evals). 11 en el corpus de H1.
- **Ratchet** — test que congela una métrica para que no empeore. Los del arnés viven en
  `backend/scripts/run_harness_tests.sh` **y** `.ps1`.
- **Falso verde** — un test que pasa sin haber verificado nada (p. ej. `pytest -k` sin match: exit 0 con 0 seleccionados).

### Orden de implementación (estricto)

1. **F0** — baseline y censo. **No empezar nada sin esto**: sin baseline no hay forma de probar la mejora.
2. **F1** — esperas fijas (el generador **antes** que los specs, para no re-contagiar).
3. **F2** — presupuesto de capturas.
4. **F3** — honestidad de workers.
5. **F4** — probe de deeplink.
6. **F5** — fragilidad de selectores.
7. **F6** — cache de datos.
8. **F7** — deadline + timeout recomendado + puerta declarada.
9. **F8** — veredicto del censo + ratchet + decisión de arnés.

F4, F5 y F6 son **independientes entre sí** (archivos disjuntos: `navigation_strategy_resolver.py`,
`qa_uat_pipeline.py`, `data_resolver.py`) y pueden hacerse en cualquier orden entre ellas. F1 y F2 **no** son
independientes: las dos editan `templates/playwright_test.spec.ts.j2` ⇒ **secuenciales, F1 primero**.

### Definición de Hecho (DoD) global

- [ ] Los 6 KPI de §1 medidos **con los comandos de §4** y anotados en §9 con su valor final.
- [ ] Los 10 archivos de test nuevos existen y cada comando de §5 reporta su número de `passed` con `0 failed`.
- [ ] Las 6 flags nuevas tienen sus **6 patas** (§3.1) y aparecen en `GET /api/harness/flags`.
- [ ] Ninguna flag nació OFF (y si alguna lo hizo, cita por escrito la categoría (A) o (B)).
- [ ] `§9. Veredicto del censo` tiene una línea por cada módulo del corpus de 11.
- [ ] `python -m compileall` limpio sobre los `.py` tocados; `npx tsc --noEmit` no introduce errores nuevos en los
      `.ts` tocados (comparar contra el conteo previo — hay deuda preexistente, criterio **delta**).
- [ ] **Smoke manual con AgendaWeb arriba** (el único gate que prueba que quitar los sleeps no rompió nada): correr
      `ado122_provincia_domicilio.spec.ts` y `ado171_emails_oficial.spec.ts` **3 veces** y verificar 3/3 verdes y
      tiempo de pared menor al baseline. **Sin este smoke, F1 no está hecha** — los tests unitarios miden el archivo,
      no el navegador.
- [ ] Backward-compatible: ningún contrato de `api/qa_uat.py` cambió; los 5 specs siguen corriendo.
- [ ] Cero código de frontend tocado. Cero `push`. Cero DML.

---

## §9. Veredicto del censo (a completar en F8.1)

> Esta sección se llena durante la implementación. Debe tener **una línea por cada uno de los 11 módulos** del corpus
> de H1, con `MANTENER COMO DEUDA DECLARADA — <razón>` o `BORRAR — reemplazado por <archivo:línea>`, más el valor
> final de los 6 KPI. Si queda vacía, **F8 no está hecha**.

| Módulo | Veredicto | Evidencia |
|---|---|---|
| `navigation_driver.py` | _(pendiente F8.1)_ | |
| `playwright/helpers/navigation_executor.ts` | _(pendiente F8.1)_ | |
| `playwright/instrumented_actions.ts` | _(pendiente F8.1)_ | |
| `deeplink_readiness_checker.py` | _(esperado: CONECTADO en F4)_ | |
| `playwright/helpers/arrival_validator.ts` | _(pendiente F8.1)_ | |
| `locator_quality.py` | _(esperado: CONECTADO en F5)_ | |
| `playbook_performance.py` | _(esperado: CONECTADO en F7.2)_ | |
| `test_data_cache.py` | _(esperado: CONECTADO en F6)_ | |
| `screenshot_budget.py` | _(esperado: CONECTADO en F2)_ | |
| `playwright/helpers/grid_precheck.ts` | _(pendiente F8.1)_ | |
| `playwright/helpers/session_guard.ts` | _(pendiente F8.1)_ | |

---

## §10. Nota de numeración (por qué 274)

Verificado el 2026-07-30 relistando `Stacky Agents/docs/` en frío:

- Máximo existente: **271**. Huecos sin archivo: **244, 245, 261**.
- **272 — RESERVADO por escrito, por DOS vecinos y para dos ejes distintos:** plan 271 §6.1 lo reserva para
  *"unificar los SEIS escritores de estado"* (`271_PLAN_...md:2136`, y lo referencia 10 veces más), y el plan 270 lo
  sugiere para *"reconciliación masiva Stacky→tracker"* (`270_PLAN_...md:1574`). Además `270_PLAN_...md:1577` dice
  textualmente: *"No hardcodear 272/273 desde este documento"*.
- **273 — YA TOMADO durante esta misma corrida por una sesión paralela.** Cuando empecé, no existía; al cerrar,
  `273_PLAN_EL_DEEP_LINK_ATERRIZA_Y_EL_ERROR_SE_ENTIENDE_LOS_7_BLOQUEANTES_DE_PRODUCCION.md` estaba **commiteado**
  (`8a6a7123`). Además el plan 270 ya lo había **sugerido por escrito** para `services/gitlab_sync.py`
  (`270_PLAN_...md:1575`). Doble motivo para no tomarlo.
  **Frontera con el 273 (verificada, no asumida):** su "deep link" es el de la **SPA de Stacky** (`/devops`, F5,
  `frontend/src/App.tsx`, `frontend/src/api/client.ts`, tokens de contraste). El "deep link" de **este** plan (F4) es una
  URL directa a una pantalla de **AgendaWeb** (`FrmDetalleClie.aspx?clcod={CLCOD}`) resuelta en
  `navigation_strategy_resolver.py`. **Son dos conceptos homónimos y disjuntos.** Confirmado por construcción: el 273
  declara "Flags nuevas: CERO" y toca solo frontend; este plan declara "cero cambios de frontend" (§7.10) y no toca
  ningún `.tsx`. **Cero archivos en común ⇒ se pueden implementar en paralelo.**
- **261 — evidencia contradictoria:** el plan 260 le asignó alcance (*"la F0 del Plan 261"*,
  `260_PLAN_...md:2415`; también `:1194` y `:2496`), pero `_supervision/PAQUETES_PARALELIZACION_2026-07-28.md:274`
  declara *"Los números 261 y 262 siguen libres"* — y el 262 ya existe, lo que muestra que ese doc está desactualizado.
- **274 — LIBRE y sin reserva:** `grep -rniE "\b274\b"` sobre `Stacky Agents/docs/` devuelve solo números de línea
  incidentales (`db_query.py:272-274`, `App.tsx:274`, …), **ninguna reserva de plan**.

⇒ Se toma **274**: el primer número por arriba del tope real que no tiene ni reserva escrita ni sugerencia escrita.
