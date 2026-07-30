# Plan 274 — El QAUAT deja de esperar de gusto: navegación eficiente y fin de la infraestructura huérfana

> **Estado:** **IMPLEMENTADO F0..F10** el 2026-07-30 — **68 tests propios verdes** (63 en el tool sobre 11 archivos +
> 5 en el backend sobre 2 archivos), 0 fallos. **Falta el smoke manual con AgendaWeb arriba** (DoD) y, por lo tanto, el "después" de KPI-7 queda
> declarado `NO MEDIBLE` en §9.2 — el *baseline* sí se capturó en F0.5, antes de F1.
> Pre-flight: los 7 bloqueantes del v3 se verificaron **uno por uno contra el código real** antes de escribir nada;
> los 7 estaban CERRADOS en el cuerpo de las fases (no solo anunciados en el changelog).
> **Fecha:** 2026-07-30
> **Origen:** auditoría de eficiencia de navegación pedida por el operador (agente QA/UAT + Playwright sobre AgendaWeb).
> **Advertencia sobre este header:** el campo `Estado:` **NO es evidencia**. Hay precedente de 7 planes cuyo header decía
> IMPLEMENTADO sin serlo, y de 2 planes de este mismo linaje (240, 241) cuyo header dice "falta implementar" cuando el
> código ya está en `main`. Verificá siempre con `git log --all --grep="plan-274"` y con los greps de §4.
>
> Juez v2: subagente independiente, misma corrida, contexto limpio.
> **Juez v3: sesión independiente, sin el v1 ni el razonamiento del autor.** Mandato: verificar que los fixes que el v2
> **declaró** estén **aplicados en el cuerpo** (no solo anunciados en el changelog), reabrir cada `archivo:línea` contra
> el código, y re-contar cada cifra con un comando reproducible.

---

## §0. CHANGELOG v2 -> v3

> **Resultado de la verificación de los fixes declarados por el v2 (eje principal de esta pasada).**
> De los 14 fixes que el v2 declaró: **6 CERRADOS**, **5 PARCIALES**, **3 REABIERTOS EN OTRO LADO**.
> Ningún fix estaba puramente inventado — pero **tres de ellos cerraron el síntoma y dejaron vivo el defecto de diseño**,
> que es el modo de falla que este pipeline viene repitiendo.
>
> **Anclajes verificados abriendo el archivo: 81 OK, 10 DESFASADOS, 3 INEXISTENTES/FUERA-DE-SCOPE.**
> **Cifras re-contadas: 12 confirmadas, 4 mal.** Comandos pegados en cada hallazgo.

### §0.1. Estado de los 14 fixes que el v2 declaró

| Fix v2 | Qué prometía | Estado real | Dónde |
|---|---|---|---|
| **C1** | F7.1: reemplazar 6 claves de etapa inventadas por 6 reales | **REABIERTO** | las 6 existen, pero **3 están fuera del scope de `_check_deadline`** → `NameError`. Ver **V1** |
| **C2** | F4: `probe.get("ready")` → `decision == "PASS"` | **CERRADO** | contrato re-verificado: `grep -c '"ready"'` → **0**; `PASS` en `:340`, `BLOCKED` en `:143` |
| **C3** | F4: `screen`/`params`/`base_url` fuera de scope | **CERRADO** | firma `:151-158` re-verificada literal |
| **C4** | F6: `put_data` → `store_data`, por campo | **CERRADO** | API re-verificada; `field_name` **es** el nombre real del loop (`data_resolver.py:360-388`) |
| **C5** | F2: `__shouldCapture('success')` → `__captureIfBudget` | **REABIERTO** | la aridad quedó bien, pero con `captureIndex=0` fijo **el presupuesto por paso no puede activarse nunca**. Ver **V2** |
| **C6** | 6 patas de flag en los 4 archivos correctos | **PARCIAL** | rutas OK y exactas, pero **el gate cubre 4 de 6 patas**; falta `_CATEGORY_KEYS`. Ver **V6** |
| **C7** | F2: criterio `≤2` insatisfacible → conjunto `{325,496,798,806}` | **PARCIAL** | el criterio quedó bien, pero **el encabezado de F2 sigue diciendo "17 sitios"** y contradice su propio cuerpo. Ver **V7** |
| **C8** | KPI-4 partido en 4a/4b | **PARCIAL** | la partición está, pero **la meta de 4a quedó sobre la base equivocada**. Ver **V3** |
| **C9** | F7.2 inerte → agregar la escritura (`record_run`) | **PARCIAL** | el diseño es correcto, pero **la mitad nueva quedó anclada a una variable que no existe** y omite un parámetro obligatorio. Ver **V4** |
| **C10** | F1.1: una sola espera, no dos | **CERRADO** | `waitForAgendaStable(page, timeout=10_000)` delega en `waitForAspNetIdle(page, timeout)` (`.j2:63-66`) ✓ |
| **C11** | el censo arranca en 10, no en 11 | **PARCIAL** | **se corrigió el arranque y NO el cierre**: la cadena de fases pierde un decremento. Ver **V3** |
| **C12** | baseline en archivo de datos + ratchet monótono | **CERRADO** | F0.1 no manda editar ningún assert ✓ |
| **C13** | F8.2 lee `plan274_wait_baseline.json` | **CERRADO** | artefacto correcto ✓ |
| **C14** | "los 5 que quedan"→6; "los 7 archivos"→11 | **CERRADO** | las dos listas cierran ✓ |
| **[ADICIÓN v2] F9** | ratchet de reloj de pared | **REABIERTO** | **§8 y §9 se contradicen sobre cuándo tomar el baseline**, y así ordenado el ratchet es ciego a C10. Además `C-7` **no mide reloj de pared**. Ver **V5** |

### §0.2. Hallazgos de esta pasada (V1..V20, rankeados)

**BLOQUEANTES**

- **V1 — F7.1: `_check_deadline` NO ESTÁ EN SCOPE en 3 de las 6 etapas elegidas.**
  El v2 arregló que las claves *existieran* y no verificó que la función fuera *alcanzable*. `_check_deadline` está
  definida **anidada dentro de `_run_pipeline_stages`** (`qa_uat_pipeline.py:1324` abre la función, `:1406` define el
  closure sobre `_deadline`/`_max_minutes`/`stages`). Las asignaciones elegidas:
  ```bash
  grep -nE 'stages\["[^"]+"\][[:space:]]*=' qa_uat_pipeline.py | awk -F: '{print ($1>=1324 && $1<3794) ? "EN-SCOPE "$0 : "FUERA "$0}'
  ```
  → `stages["evidence"]` **:734** (dentro de `run()`, `:314`) · `stages["dossier"]` **:857** y `stages["publisher"]`
  **:907** (dentro de `_run_dossier_and_publisher()`, `:825`) ⇒ **`NameError` en la primera corrida real**.
  Peor: `compileall` **no lo detecta** (Python resuelve nombres en runtime) y el gate `grep -c "_check_deadline(" ≥ 9`
  **da verde igual**. Era un gate que no corre contra su defecto. Además `screen_detection` **ya tiene** su chequeo en
  `:1673` ⇒ de las 6, sólo `failure_analyzer` era genuinamente nueva y usable.
  **FIX v3:** lista cerrada reemplazada por **6 claves verificadas EN SCOPE y sin chequeo previo**, y el criterio pasa a
  ser **AST de alcance**, no un `grep -c`.
- **V2 — F2: el presupuesto por paso queda INERTE, con todos los KPI en verde.**
  `__shouldCapture(stepOk, captureIndex)` corta con `if (captureIndex >= limit)` donde `limit = stepOk ? __SS_ON_SUCCESS(1) : __SS_ON_FAILURE(3)` (`screenshot_budget.py:190-191`). F2 manda emitir
  `__captureIfBudget(page, path, true, 0)` ⇒ `0 >= 1` es **false** ⇒ **siempre captura**. Y el template ya emite
  **exactamente una** captura por paso:
  ```bash
  grep -n "page.screenshot(" templates/playwright_test.spec.ts.j2   # 19 lineas, 1 por rama de accion
  for f in playwright/uat/*.spec.ts playwright/smoke/*.spec.ts; do echo -n "$f "; grep -c "page.screenshot(" $f; done  # 1 c/u
  ```
  ⇒ el objetivo declarado ("pasar de 17 capturas por paso a 1 en éxito") **ya se cumple hoy**; lo único que F2 agrega es
  el techo de **25 por escenario**, que sólo se activa con >25 pasos. Un plan cuyo criterio es sintáctico (`≤4 sin
  guardia`) **cierra la fase con 0 PNG menos**. Es el mismo patrón que C9 mató en F7.2, reintroducido en F2.
  **FIX v3:** F2 declara honestamente su efecto real, pasa `captureIndex` **incremental por paso** y agrega un criterio
  **sobre el número de PNG emitidos**, no sobre la sintaxis.
- **V3 — la aritmética del censo no cierra: el ratchet de F8.2 nace con 1 unidad de holgura.**
  Base: 11 módulos; `direct == 0` hoy = **10** (`arrival_validator.ts` tiene 1); `prod_reachable == False` = **11**.
  Las fases conectan **5** módulos ⇒ cierre correcto: **direct = 10 − 5 = 5** y **alcanzable = 11 − 5 = 6**.
  El v2 escribe la cadena `F2 10→9`, `F4 9→8`, **`F5 → 8`** (no decrementa), `F6 8→7`, `F7 7→6` ⇒ pierde el decremento
  de F5 y cierra en **6/7**. Como F8.2 congela **esos** valores, un módulo que se desconecte después **no rompe el
  ratchet**. Y `KPI-4a` mezcla bases: dice "Hoy **10** de 11 → Meta **≤6** de 11 (5 conectados)", pero 10 − 5 = **5**.
  Es exactamente el defecto C11 declarado cerrado: **se corrigió el arranque y no el cierre.**
  **FIX v3:** cadena y metas recalculadas a 5/6, con la distinción explícita entre *módulos huérfanos* (6) y *valor de
  la métrica `direct`* (5) — que no son el mismo número y por eso se confundieron.
- **V4 — F7.2.a (la mitad que el v2 agregó para matar la inercia) está anclada a algo que no existe.**
  Dice *"Al terminar `_run_all_specs_once` (`uat_test_runner.py:301`), después de calcular `duration_ms`"*. Pero:
  ```bash
  awk 'NR>=301 && NR<461 && /duration_ms/{print NR": "$0}' uat_test_runner.py   # 0 lineas
  grep -n "duration_ms   = int" uat_test_runner.py                              # 239
  ```
  `_run_all_specs_once` abarca **:301-460** y **no calcula `duration_ms`**: se calcula en `run()`, **`:239`**.
  Y la firma real es **`record_run(playbook_id, verdict, duration_ms, slowest_step="", fail_reason="")`**
  (`playbook_performance.py:113-118`): **`verdict` es posicional y obligatorio**, y el plan no lo nombra ⇒ `TypeError`.
  Es el mismo error de clase que C4 (`put_data`) — cometido **en el fix de C9**.
  **FIX v3:** F7.2.a re-anclada a `run()` `:239` con la firma completa y el valor de `verdict` determinado por regla.
- **V5 — F9 (la [ADICIÓN ARQUITECTO] del v2) se auto-anula: §8 y §9 se contradicen.**
  §8 ordena *"**F9 conviene correrla al final**… si se corre antes, congela como baseline el reloj **previo** a la
  mejora y el ratchet queda flojo"*; §9 dice *"KPI-7 … **(medir antes de F1)**"*. Son instrucciones opuestas, y **el
  razonamiento de §8 está invertido**: F9 existe (por el propio texto) para detectar que una espera por estado sea
  **más lenta** que el sleep que reemplazó (C10) — y eso **sólo** se detecta con baseline **pre-F1**. Corriéndola al
  final, `test_baseline_de_reloj_existe_o_se_crea` congela el reloj **ya mejorado (o ya degradado)** y el ratchet no
  puede detectar nada. **FIX v3:** el baseline de F9 se toma en **F0**, la fase de baselines; el ratchet corre al final.
- **V6 — dos flags nuevas se declaran con rollback por flag y NO tienen mecanismo.**
  `STACKY_QA_UAT_STATE_WAITS_ENABLED` (F1): el diff de F1.1 es una edición **literal** del `.j2` (`await page.waitForTimeout(800);` → `await waitForAgendaStable(page, 5_000);`), sin variable Jinja ni rama condicional ⇒ con la flag
  en OFF **no vuelve nada**. `STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED` (F2): el camino "bloque inerte" de
  `build_ts_budget_block` se activa con `budget.disabled`, que sólo lee **`QA_UAT_SCREENSHOT_BUDGET_DISABLED`**
  (`screenshot_budget.py:99`) — la flag nueva no está cableada a nada. Las dos **pasarían el gate de las 4 `grep`**
  (existen en los 4 archivos) siendo **flags muertas**: el gate de patas verifica registro, no efecto.
  **FIX v3:** mecanismo explícito para las dos + una 5ª pata de gate que exige que la key aparezca **también en el
  código que la lee**.
- **V7 — F7 pide `9 passed` y define 8 tests.** Contá los `test_` de `test_plan274_consolidation.py`: son **8**. Un
  criterio de igualdad estricta con 8 tests definidos es insatisfacible ⇒ el implementador inventa un 9º o baja el
  criterio, que es la conducta que todo el plan combate. **FIX v3:** 9 tests nombrados (el 9º es el gate de scope de V1).

**IMPORTANTES**

- **V8 — `C-7` no mide reloj de pared.** Corrido de verdad contra el reporte real:
  ```
  walk(suites) -> wall_clock_ms_total=47176      # 3 dicts con "duration"
  d["stats"]["duration"] = 70030.106             # el reloj de pared REAL
  d["stats"]["expected"] = 3
  ```
  El recorrido de `suites` **ignora `globalSetup` (el login) y todo el overhead**: subestima **22 854 ms (33 %)**.
  El número correcto está a una clave de distancia. **FIX v3:** `C-7` usa `stats.duration` como reloj de pared y
  `suites[*]` sólo para atribuir por test.
- **V9 — el "impacto sobre una corrida real" no está medido.** Los 2 specs que el plan dice que bajan ~33 s
  (`ado122`, `ado171`) **no aparecen en el único reporte real del repo**, que corrió 3 specs generados del ticket 367
  (`P01/P02/P03`, 15 942 / 15 302 / 15 932 ms). La aritmética cierra (35,9 − 3 ≈ 33 s; 33/360 = 9,2 %) pero es una
  **proyección sobre el contenido de archivos**, rotulada como impacto medido. **FIX v3:** re-rotulado como proyección,
  con el reloj real como única evidencia aceptable (KPI-7).
- **V10 — el gate de las "6 patas" sólo verifica 4.** Falta `_CATEGORY_KEYS` (`harness_flags.py:120`), que el propio
  registry declara obligatorio: `harness_flags.py:514` dice *"toda flag nueva debe agregarse también a `_CATEGORY_KEYS`
  o el test `test_every_registry_flag_is_categorized` **rompe CI a propósito** (Plan 63)"*. El plan lo deja como
  *"si el registry lo exige"* — lo exige. Con 6 flags nuevas sin categorizar, CI rojo.
- **V11 — F8.3 es inimplementable como está escrita, y el plan no lo sabe.** El ratchet corre
  `cd backend && pytest <ruta>` con rutas **peladas** en un array bash; y los dos meta-tests parsean con
  `^\s*(tests/[\w/]+\.py)\s*$` (`.sh`) y `^\s*"(tests/[\w/]+\.py)"\s*,?\s*$` (`.ps1`, `test_plan259_ratchet_script_parity.py:28-30`).
  Una ruta `../../Stacky tools/QA UAT Agent/tests/unit/…` **tiene espacios** (word-splitting en bash) y **no matchea
  ninguno de los dos regex** ⇒ se registraría **muda**. Además hay un **tercer punto de registro** que el plan nunca
  nombra: `backend/tests/harness_ratchet_allowlist.txt` (204 líneas) — un `.py` nuevo en `backend/tests/` que no esté
  en `HARNESS_TEST_FILES` **ni** en la allowlist rompe `test_harness_ratchet_meta.py`.
  ```bash
  grep -cE "^\s+tests/test_" backend/scripts/run_harness_tests.sh   # 718
  grep -cE 'tests[/\\]test_'  backend/scripts/run_harness_tests.ps1 # 654  <- ya divergen 64
  ```
  **FIX v3:** F8.3 pasa a ser **deuda declarada por defecto** (la rama viable), y el único registro obligatorio es el
  del archivo de backend, en los **DOS** scripts, con la sintaxis de cada uno.
- **V12 — `QA_UAT_DEEPLINK_PROBE_TIMEOUT_S` es config de operador nueva fuera de la UI.** Riel: toda config del
  operador va por UI; sólo los kill-switches son env-only. **FIX v3:** constante del módulo, sin env var nueva.
  (En cambio `QA_UAT_ACTION_TIMEOUT_MS` de F1.1 **sí existe** ya — `playwright.config.ts:25` — y su reuso es correcto.)
- **V13 — F0 promete "≥ 8 passed (… 3 de censo)" y F0.2 define 5 tests de censo.** El total nombrado es **10**.
  El `≥` evita que sea insatisfacible, pero el desglose entre paréntesis induce a escribir 3.
- **V14 — `test_el_reloj_de_pared_no_empeora` figura en `test_plan274_ratchet.py` (F8.2) y su implementación en
  `test_plan274_wallclock.py` (F9).** Propiedad ambigua ⇒ o se duplica o falta.
- **V15 — cifras del v2 que no resisten el re-conteo:**
  `182 líneas con timeout=` → **184** (`grep -rn "timeout=" --include=*.py . | grep -v __pycache__ | wc -l`);
  `data_resolver.resolve()/resolve_fields() invocados desde :1176 y :1282` → **`:1282` importa `FIELD_HINTS`**, no
  invoca nada; la invocación real es **`:1203`**, y `resolve()` **no tiene caller en el pipeline**.

**MENORES (anclajes DESFASADOS, corregidos en el texto sin borrarlos)**

- **V16** — `screenshot_budget.py:180` (cuerpo de F2) → real **`:181`** (el changelog del v2 sí decía `:181`: el fix no
  se propagó a la fase).
- **V17** — `screenshot_budget.py:198` (§3.7) → la firma de `__captureIfBudget` está en **`:195`**.
- **V18** — `playbook_performance.py:166-168` (H7-bis) → **`:167-168`**.
- **V19** — `qa_uat_pipeline.py:2144` "el `except`" → el `except ImportError:` está en **`:2143`**; `:2144` es el `logger.debug`.
- **V20** — restos del v1 que el changelog dio por corregidos y siguen en el cuerpo: **"17"** en §2.2[9], §2.4 y en el
  encabezado de F2 (`:685`, `:690`) → **18/19/15**; **"38 etapas"** en §2.2[4] y §2.4 → **19 claves / 35 asignaciones**;
  **`:352`** en R-8 → **`:354`**.

### §0.3. Lo que se re-verificó y quedó CONFIRMADO (no se tocó)

`wc -l` del corpus = **4462 exacto** (11/11 líneas individuales) · `C-1` = **26 / 35 900** · `C-2` = **1** en `:608` ·
`C-3` = **19** y **las 19 líneas coinciden una por una** con la clasificación A/B/C/D de H3 · `C-5` = **3** ·
`C-5b` = **19 / 35** · `C-6` = `--workers=1` en **`:355`** · **0 importadores de producción en los 6 módulos Python** y
**1** en `arrival_validator.ts` (`navigation_executor.ts:26`) · H5 completo (`#c_`=**9** en el template, **35** en los
specs; `getByRole`=0) · H9 completo (`turno`=0, `disponibilidad`=0, `cita`=7, `recurso`=15, `profesional`=1) ·
**90** archivos `test_*.py` en el tool · **0** menciones de "QA UAT Agent" en los dos ratchets · las 6 patas de flag en
sus 4 archivos (`harness_flags.py:518-531`, `config.py:1224-1240`, `test_harness_flags.py:467`,
`harness_flags_help.py:25`) · el comentario mentiroso de `config.py:1230-1234` · el reuso de sesión de §2.2[7] ·
las **6 flags en ON** con justificación válida (ninguna cae en (A) ni en (B)) · human-in-the-loop · cero RBAC ·
neutralidad de los 3 runtimes · `error_fingerprints.json` (53 KB) · **9 worktrees vivos**.

### §0.4. [ADICIÓN ARQUITECTO v3]

**F10 — el gate de EFICACIA: ningún KPI sintáctico cierra una fase solo.** Las tres bloqueantes de esta pasada
(V1 scope, V2 presupuesto inerte, V6 flags muertas) comparten una firma: **el criterio mide que el código esté escrito,
no que haga algo**. F10 agrega dos gates deterministas y baratos que corren contra esa clase entera —
alcance por **AST** y conteo de **artefactos realmente emitidos**. Detalle en §5/F10.

---

### §0.5. CHANGELOG heredado v1 -> v2 (se conserva para trazabilidad)

**BLOQUEANTES corregidos (el v1 era inimplementable sin inventar):**

- **C1 — F7.1 citaba 6 claves de etapa que NO EXISTEN.** `data_resolution`, `precondition_check`, `seed_generation`,
  `spec_generation`, `playwright_run`, `evidence_publish` → **0 hits cada una**. El v1 las llamaba "lista CERRADA,
  determinada por lectura del propio pipeline"; no lo estaban. Reemplazadas por las **19 claves reales** y una lista
  cerrada de 6 elegidas entre ellas. También se corrige el denominador de KPI-5: **no hay 38 etapas** (19 claves
  distintas / 35 asignaciones literales).
- **C2 — F4 leía `probe.get("ready")`, clave que el módulo NUNCA devuelve.** `check_deeplink_readiness` devuelve
  `"decision"` ∈ `{"PASS","BLOCKED"}` (`deeplink_readiness_checker.py:340,143`). Con `.get("ready", False)` el
  resultado era **siempre falso ⇒ el deeplink se degradaba SIEMPRE**, y los 5 tests daban verde porque usan un doble
  con una forma inventada. Corregido a `decision == "PASS"` + test de forma real.
- **C3 — F4 usaba 3 identificadores que no existen en el scope** (`screen`, `params`, `base_url`). La firma real es
  `resolve_navigation_strategy(ticket_id, scenario_id, target_screen, lane, available_data=…)`
  (`navigation_strategy_resolver.py:151-158`). Corregido.
- **C4 — F6 llamaba `test_data_cache.put_data(...)`, que NO EXISTE.** La API real es
  `store_data(field, value, source=, notes=, ttl_hours=)` (`test_data_cache.py:93`). Además el módulo es **por campo**,
  no por hash de query. Reescrito a cache-aside **por campo**.
- **C5 — F2 generaba una llamada con la aridad equivocada.** El v1 escribía `__shouldCapture('success')`; la firma real
  del bloque que emite `build_ts_budget_block` es `__shouldCapture(stepOk: boolean, captureIndex: number)`
  (`screenshot_budget.py:181`, y `:168` en la rama `disabled`) y **ya existe**
  `__captureIfBudget(page, path, stepOk, captureIndex = 0)` (`:195-197`).
  Con 1 argumento, `captureIndex` es `undefined`, `undefined >= limit` es `false` y la guardia **deja pasar todo**:
  presupuesto inerte + `tsc --noEmit` roto. Corregido para usar el helper que ya existe.
- **C6 — las 2 patas de flag más frágiles apuntaban al archivo equivocado.** `_CURATED_DEFAULTS_ON` **no está en
  `harness_flags.py`**: vive en `backend/tests/test_harness_flags.py:467`. `PLAIN_HELP` vive en
  `backend/services/harness_flags_help.py:25`. Son justo las 2 patas cuya omisión rompe el arnés o deja la flag muda.

**Contradicciones entre fases resueltas:**

- **C7 — F2 era matemáticamente insatisfacible.** Su criterio exigía **≤2** capturas fuera de guardia, pero la misma
  fase manda dejar sin guardia `:496`, `:798` y `:806`, y `:325` es una captura de **error** que no puede llevar
  guardia de éxito ⇒ mínimo **4**. Criterio corregido a **≤4, nominadas una por una**.
- **C8 — KPI-4 no se cumplía con las propias fases.** Meta `≤5 de 11` con **5** módulos conectados ⇒ quedan **6**.
  El v1 lo "cerraba" redefiniendo el KPI a mitad de documento ("conectados **o con veredicto**"), cosa que el comando
  C-4 no puede medir. Partido en **KPI-4a** (huérfanos por C-4: 11 → **≤6**) y **KPI-4b** (veredictos escritos: **11/11**).

**Otros arreglos importantes:**

- **C9 — F7.2 nacía INERTE.** `playbook_performance.record_run` tiene **0 callers de producción** ⇒ el store está
  siempre vacío ⇒ `recommend_timeout_ms` devuelve **siempre** `default_ms`. Conectar el lector de un store que nadie
  escribe es el patrón "runner sin loop por caso" del plan 262: tests verdes, feature muerta. F7.2 ahora **también
  escribe** (`record_run`) y su criterio lo prueba.
- **C10 — F1.1 podía hacer la corrida MÁS LENTA.** Encadenaba `waitForAspNetIdle(page)` (3 s) **y**
  `waitForAgendaStable(page)` (que ya delega en `waitForAspNetIdle`, 10 s) ⇒ hasta **13 s** donde había 800 ms, con
  KPI-1 en verde porque KPI-1 cuenta ms **declarados en el archivo**, no reloj. Corregido a **una sola** llamada.
- **C11 — F0.2 arrancaba ROJO.** El propio comando C-4 devuelve **1** importador para `arrival_validator.ts`
  (`navigation_executor.ts:26`), no 0 ⇒ el censo arranca en **10**, no en 11. Se corrige el número y se define el
  criterio como *alcance transitivo de producción*.
- **C12 — F0.1 entrenaba el falso verde.** Un test llamado `test_baseline_hoy_es_35900ms` con `assert == 35_900` que el
  plan manda **editar** en F1. Reemplazado por baseline en **archivo de datos** + ratchet monótono: ningún assert se edita.
- **C13 — F8.2 leía el baseline de esperas desde `plan274_selector_baseline.json`**, que es el artefacto de **F5**
  (scores de selectores). Artefacto equivocado; ahora hay `plan274_wait_baseline.json`.
- **C14 — cuentas que no cierran:** F8.1 decía "los **5** que quedan" y listaba 6; F8.3 decía "los **7** archivos" y
  listaba 10 (11 con el del backend). Corregidos a 6 y 11.

**Cifras corregidas con su comando (§4):** H3 `17 de 19` → **18 de 19**; H5 template `#c_`=4 → **9**;
H9 `cita/recurso/profesional = 0` → **7/15/1** (todos falsos positivos del español: *citado*, *último recurso* — la
conclusión "no hay dominio de turnos" **se sostiene**: `turno`=0, `disponibilidad`=0); `uat_test_runner.py:352` pasa
`--timeout` → **:354**; TTL de `test_data_cache` en `:49-50` → **:52**.

**[ADICIÓN ARQUITECTO]:** **F9 — ratchet de reloj de pared automático** (§5). El v1 optimiza un *proxy* (ms escritos en
archivos) y deja como único gate real un **smoke manual de 3 corridas**. `reports/playwright-results.json` ya publica
`duration` por test y `startTime` — hay un ratchet automático gratis, y sin él C10 (el plan hace la corrida más lenta
con todos los KPI en verde) no la detecta nadie.

**Lo que se confirmó BIEN y no se tocó:** las 11 líneas del corpus H1 (4462 exacto), C-1 (26/35900), C-2 (1 en `:608`),
C-3 (19), C-5 (3), C-6 (`--workers=1` en `:355`), los 0 importadores Python 6/6, el reuso de sesión de §2.2[7], las
**6 flags todas ON** con justificación real (ninguna cae en (A) ni en (B) — revisadas una por una), human-in-the-loop,
cero RBAC, cero trabajo del operador y la neutralidad de los 3 runtimes.

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
| **KPI-3** — `page.screenshot()` incondicionales en el generador | **18** de 19 (v1 decía 17: omitía `:806`) | **≤ 4** sin guardia, y son **estas 4 nominadas**: `:325`, `:496`, `:798`, `:806` | comando `C-3` |
| **KPI-4a** — módulos del corpus CERRADO de 11 (§2.3) con **0 importadores directos** | **10** (v1 decía 11: `arrival_validator.ts` ya tiene 1, ver C-4) | **5** (10 − los 5 que conectan F2/F4/F5/F6/F7) | comando `C-4` |
| **KPI-4a-bis** — módulos del corpus **sin alcance de producción** | **11** | **6** (11 − 5) | `prod_reachable` de F0.2 |
| **KPI-4b** — módulos del corpus con **veredicto escrito** en §9 | **0 de 11** | **11 de 11** | inspección de §9 |
| **KPI-5** — llamadas a `_check_deadline` **en scope** en el pipeline | **2** llamadas + 1 definición = **3 líneas** | **8** llamadas + 1 definición = **9 líneas**, *todas dentro de `_run_pipeline_stages`* | `C-5` **y** `C-8` (AST) |
| **KPI-6** — el paralelismo configurable es real (la env var no se pisa) | **falso** (`--workers=1` hardcodeado en `uat_test_runner.py:355` pisa `QA_UAT_WORKERS`) | **verdadero** (se respeta, con guardia de sesión) | comando `C-6` |
| **KPI-7** — reloj de pared de la corrida Playwright | **70 030 ms** medidos en el último reporte real (3 tests) | ratchet delta desde `stats.duration` de `reports/playwright-results.json` | comando `C-7` |
| **KPI-8** *(nuevo, [ADICIÓN ARQUITECTO v3])* — **PNG realmente emitidos** por un spec renderizado | `N_pasos + 4` (una captura por paso, sin techo) | `min(N_pasos, 25) + 4`, y el techo **demostrado activándose** | comando `C-9` |

> **Por qué KPI-4a bajó de "≤6" a "5" (corrige un error aritmético del v2 — hallazgo V3).** El v2 partió bien el KPI
> pero dejó la meta sobre la base equivocada: escribió "Hoy **10** de 11 → Meta **≤6** de 11", y **10 − 5 = 5**.
> El error nace de confundir dos cosas que dan números distintos:
> - **módulos que siguen huérfanos** tras el plan = **6** (los que F8.1 debe dictaminar), y
> - **valor de la métrica `direct`** al cierre = **5**, porque `arrival_validator.ts` **nunca** estuvo en esa cuenta
>   (ya tenía 1 importador directo).
>
> Las dos son verdad y no son el mismo número. Congelar el ratchet en 6 (como hacía F8.2) le regala **una unidad de
> holgura**: un módulo podría desconectarse sin romper nada. La cadena corregida, fase por fase, es:
>
> | | arranque | F2 | F4 | F5 | F6 | F7 |
> |---|---|---|---|---|---|---|
> | `direct == 0` | 10 | 9 | 8 | **7** | 6 | **5** |
> | `prod_reachable == False` | 11 | 10 | 9 | **8** | 7 | **6** |
>
> *(El v2 saltaba la columna de F5 y reanudaba F6 desde el valor de F4.)*
>
> **Por qué desapareció el "de 38".** No existe ningún comando que produzca 38 etapas.
> `grep -oE 'stages\["[^"]+"\]' qa_uat_pipeline.py | sort -u | wc -l` → **19** claves distintas;
> `grep -cE 'stages\["[^"]+"\][[:space:]]*=' qa_uat_pipeline.py` → **35** asignaciones literales;
> `grep -c 'stages\[' qa_uat_pipeline.py` → **136** referencias. KPI-5 se mide sobre lo único verificable: el conteo
> de `_check_deadline(`.

**Impacto PROYECTADO (no medido) sobre una corrida.** *(Rótulo corregido en v3 — hallazgo V9: el v2 lo presentaba como
"impacto sobre una corrida real" y no hay ninguna corrida real que lo respalde.)* Los 2 specs que concentran el
desperdicio (`ado122_provincia_domicilio.spec.ts` = 21 100 ms, `ado171_emails_oficial.spec.ts` = 14 500 ms) deberían
bajar ~33 s de reloj de pared por corrida sin tocar la app. Sobre el presupuesto declarado del pipeline (6 min por
ticket, `qa_uat_pipeline.py:1373`), 33 s son el **9,2 %**. La aritmética cierra (35,9 − 3,0 ≈ 32,9 s; 32,9 / 360 = 9,1 %)
**pero sale del contenido de los archivos, no de un reloj.**

> **Por qué esto no es evidencia.** El único `reports/playwright-results.json` del repo corresponde a **otra** corrida:
> 3 specs generados del ticket 367 (`P01`/`P02`/`P03`, 15 942 / 15 302 / 15 932 ms, `stats.startTime`
> `2026-07-26T00:36:03.100Z`). **Ninguno de los 2 specs citados aparece ahí.** La única evidencia aceptable de que este
> plan aceleró algo es **KPI-7 medido antes y después** (F9, con el baseline tomado en **F0**, ver §8).

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
[4] ... 19 claves de etapa / 35 asignaciones -> qa_uat_pipeline.py  (deadline consultado en solo 2: :1673, :3402)
    de esas 19, SOLO 12 se asignan dentro de _run_pipeline_stages (:1324), que es donde vive _check_deadline (:1406)
[5] genera los .spec.ts desde el template   -> playwright_test_generator.py:179 (get_template), :384/:932 (render)
                                               template = templates/playwright_test.spec.ts.j2  (playwright_test_generator.py:51)
[6] runner: UNA sola invocación npx         -> uat_test_runner.py:301 (_run_all_specs_once), :351-355 (cmd), :395 (Popen)
                                               duration_ms de la corrida se calcula en run(), :239 — NO en :301-460
[7] Playwright globalSetup: auth            -> playwright.config.ts:7 -> playwright/global.setup.ts
      reusa .auth/agenda.json si es válido   -> global.setup.ts:85 (authFile), :91-106 (fingerprint), :116-120 (skip login)
      valida sesión viva por HTTP real       -> playwright/auth_state_validator.ts (TTL 30 min)
[8] cada spec navega                         -> playwright/helpers/webforms_nav.ts  (navigateViaFormSubmit)
      *** único helper TS con importadores reales: 4 ***
[9] evidencia                                -> 18 de 19 page.screenshot() incondicionales heredados del template
                                               (una por paso; el techo de 25/escenario NO existe hoy — ver V2)
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
| 5 | `playwright/helpers/arrival_validator.ts` | 372 | valida llegada a pantalla | **1** (`navigation_executor.ts:26`) — pero ese importador **también es huérfano** ⇒ alcance de producción 0 |
| 6 | `locator_quality.py` | 294 | puntúa fragilidad de un selector | 0 |
| 7 | `playbook_performance.py` | 226 | `recommend_timeout_ms()` = p95×1,5 acotado a `[60s, 600s]` (`:59-60`) | 0 |
| 8 | `test_data_cache.py` | 219 | cachea datos resueltos 8 h para no re-resolverlos | 0 |
| 9 | `screenshot_budget.py` | 208 | `build_ts_budget_block()` (`:154`) genera el gating TS; `1` en éxito / `3` en fallo / `25` techo (`:52-54`) | 0 |
| 10 | `playwright/helpers/grid_precheck.ts` | 172 | pre-chequeo de grilla antes de buscar una fila | 0 |
| 11 | `playwright/helpers/session_guard.ts` | 167 | guardia de sesión | 0 |
| | **TOTAL** | **4462** (verificado con `wc -l`, exacto) | | **10 de 11** con 0 importadores directos; **11 de 11** sin alcance de producción |

> **Ojo con el número de arranque (corrige el v1).** El comando normativo `C-4` devuelve **10**, no 11, porque
> `arrival_validator.ts` tiene un importador real. El corpus sigue siendo de **11 módulos**, pero el censo de F0.2
> **arranca en 10** medido por C-4. El criterio correcto es **alcance transitivo de producción**: un módulo cuenta como
> conectado solo si su importador es alcanzable desde `qa_uat_pipeline.py` o desde un `.spec.ts` vivo. F0.2 implementa
> las dos métricas y las declara por separado para que ninguna se "arregle" editando el assert.

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

**H3 (ALTO) — 18 de 19 `page.screenshot()` del generador son incondicionales** *(el v1 decía 17; recuento real, ver
desglose)*. **Clasificación completa y CERRADA de las 19**, que es la que gobierna F2:

| Grupo | Líneas | Cuántas | Qué hacer en F2 |
|---|---|---|---|
| **A. Por paso** (una por rama de acción) | `:570` navigate, `:603` navigate_webforms, `:609` expand_collapsible, `:622` click, `:633` fill, `:644` select, `:654`, `:669` press_key, `:674` hover, `:682` double_click, `:694` check_checkbox, `:702` select_radio, `:710` clear, `:719` scroll_into_view | **14** | **envolver** |
| **B. Preámbulo** (panel de filtros avanzados) | `:555` | **1** | **envolver** |
| **C. Evidencia mínima — NO tocar** | `:496` setup, `:798` final_state, `:806` afterEach | **3** | dejar **sin** guardia |
| **D. Ya condicional** (dentro de `if (result && result.is_exception_page)`, `:324`) | `:325` | **1** | dejar **sin** guardia de éxito: es una captura de **error** |

⇒ **envolvibles = 15** (A+B), **sin guardia por diseño = 4** (C+D). El v1 decía "envolver las 17" **y** "no envolver
`:496` ni `:798`", que están **dentro** de esas 17: instrucción contradictoria consigo misma.
Ninguna del grupo A/B tiene un `if` de éxito/fallo. Contraste: `playwright.config.ts:22` declara
`screenshot: 'only-on-failure'` — esa opción solo gobierna el adjunto **automático** de Playwright, es irrelevante
frente a 15 capturas manuales por paso.

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
En el template: `getByRole`=0, `getByLabel`=0, `getByTestId`=0, `page.locator`=50, `#c_`=**9** *(el v1 decía 4)*.
En los specs vivos: `getByRole`=0, `getByLabel`=0, `getByTestId`=0, `locator(`=105, `#c_`=35 *(los 3 verificados)*.
Los `#c_...` son IDs que genera ASP.NET a partir de la jerarquía de controles: cambiar un contenedor en el `.aspx`
los renombra en masa. El módulo que puntúa esa fragilidad (`locator_quality.py`, 294 líneas) es el huérfano #6.
**Realismo obligatorio:** no se puede exigir `getByRole` sobre una app que el equipo QA no controla; lo que sí se puede
es **medir** la fragilidad y **anclar por contrato** (F5).

**H6 (MEDIO) — el presupuesto de 6 minutos casi no se consulta.** `qa_uat_pipeline.py:1373` fija
`max_total_minutes = 6`; `:1404` calcula `_deadline`; `:1406-1420` define `_check_deadline(stage_name)` que devuelve
`BLOCKED / EXCEEDED_REASONABLE_RUNTIME` *(los 4 anclajes verificados, exactos)*. Pero solo se **invoca en 2 lugares**
(`:1673` y `:3402`). Es cooperativo: evita *empezar* una etapa tarde, no puede cortar una colgada.

**H6-bis (ALTO, descubierto al verificar el v2 — es la raíz del hallazgo V1): `_check_deadline` es una función
ANIDADA, no una función del módulo.** Está definida **dentro de `_run_pipeline_stages`** (que abre en `:1324`) y es un
**closure** sobre `_deadline`, `_max_minutes`, `_effective_config`, `ticket_id`, `stages` y `started`. Consecuencia
dura: **sólo se la puede llamar desde dentro de esa función**. Llamarla desde `run()` o desde
`_run_dossier_and_publisher()` es un **`NameError` en runtime que `compileall` no detecta**.

**El denominador real (corrige el "38" del v1, que no sale de ningún comando):** hay **19 claves de etapa distintas**
y **35 asignaciones literales** `stages["…"] = `. Pero **el denominador útil para F7.1 no es 19: es 12**, porque sólo
12 de las 19 se asignan dentro del scope de `_check_deadline`. Comando normativo:

```bash
# EN SCOPE (asignadas dentro de _run_pipeline_stages, :1324-:3793)
awk 'NR>=1324 && NR<3794' qa_uat_pipeline.py \
  | grep -oE 'stages\["[^"]+"\][[:space:]]*=' | grep -oE '"[^"]+"' | sort -u
# FUERA DE SCOPE
awk 'NR<1324 || NR>=3794' qa_uat_pipeline.py \
  | grep -oE 'stages\["[^"]+"\][[:space:]]*=' | grep -oE '"[^"]+"' | sort -u
```

| | Claves |
|---|---|
| **EN SCOPE (12)** — usables por F7.1 | `compiler_contract` · `config_validation` · `evaluator` · `failure_analyzer` · `generator_contract` · `quarantine_check` · `run_metrics_summary` · `runner` · `screen_detection` · `selector_contract` · `triage` · `weak_oracle_filter` |
| **FUERA DE SCOPE (7)** — **prohibidas** para F7.1 | `dossier` (`:857`) · `epic_rollup` (`:4136`) · `evidence` (`:734`) · `functional_verdict` (`:4281`) · `intent_parser` (`:1046`) · `publisher` (`:907`) · `synthetic_ticket_builder` (`:1110`) |

> **Tres de las 6 claves que el v2 eligió están en la columna prohibida** (`evidence`, `dossier`, `publisher`).
> Ese es el hallazgo V1 y por eso F7.1 se reescribió entera.

**H7 (MEDIO) — no hay un solo punto donde se fije el timeout por defecto.**
`set_default_timeout` = 0 ocurrencias; `set_default_navigation_timeout` = 0; **184** líneas con `timeout=`
*(el v2 decía 182; comando: `grep -rn "timeout=" --include=*.py . | grep -v __pycache__ | wc -l` → 184)*.
Techo real más alto del repo: `playbook_performance.py:60` → `_TIMEOUT_CEILING_MS = 600_000` (10 min),
con piso `:59` → `_TIMEOUT_FLOOR_MS = 60_000` — en el huérfano #7. Y **`uat_test_runner.py:354`** *(el v1 decía `:352`;
`:352` es la línea `"npx", "playwright", "test",`)* pasa `--timeout=90000` (de `_DEFAULT_TIMEOUT_MS = 90_000`, `:48`)
que **pisa** el `timeout: 60000` de `playwright.config.ts:8`.

**H7-bis (ALTO, descubierto al verificar) — el huérfano #7 no tiene quién lo alimente.**
`playbook_performance.record_run` tiene **0 callers de producción**
(`grep -rn "record_run" --include=*.py . | grep -v tests/ | grep -v _attic` → solo `budget_enforcer.py:277`, que es
`record_run_cost`, otra función). Sin escritor, `_load(playbook_id)` devuelve vacío, `p95_duration_ms` es 0, y
`recommend_timeout_ms` cae por `if p95 <= 0: return default_ms` (**`:167-168`**; el v2 decía `:166-168` — `:166` es
`p95 = data.get("p95_duration_ms", 0)`) **siempre**. Consecuencia directa:
**conectar solo el lector deja la feature inerte para siempre** con sus tests en verde (el mismo patrón que el
"runner sin loop por caso" del plan 262). Por eso F7.2 **también cablea la escritura**.

> **La firma de la escritura, verificada (hallazgo V4 — el v2 la dio por sentada).**
> `record_run(playbook_id: str, verdict: str, duration_ms: int, slowest_step: str = "", fail_reason: str = "") -> dict`
> (`playbook_performance.py:113-118`). **`verdict` es posicional y obligatorio.** Cualquier llamada que pase sólo id y
> duración es un `TypeError`.

**H8 (MEDIO) — los 90 archivos de test del tool están FUERA de los dos ratchets del arnés.**
`grep -c "QA UAT Agent" run_harness_tests.sh` → **0**. Idem `.ps1` → **0**. Los ratchets solo registran los tests del
**backend** (`tests/test_plan214_*`, `tests/test_plan241_qa_uat.py`). Consecuencia directa para este plan: **un test
nuevo creado dentro del tool no tiene gate automático**; hay que declarar su comando explícito (F0.3 y §4).

**H8-bis (ALTO, descubierto al verificar el v2 — hallazgo V11): meter el tool al ratchet NO ES POSIBLE con el mecanismo
actual, y hay un TERCER punto de registro que el v2 no nombra.**
1. El `.sh` hace `cd "$(dirname "$0")/.."` (→ `backend/`) y corre `pytest <ruta>` con las rutas **peladas, sin comillas**,
   dentro de un array bash. La ruta del tool contiene **dos espacios** (`Stacky tools`, `QA UAT Agent`) ⇒ word-splitting.
2. Los dos meta-tests que vigilan el registro sólo reconocen rutas bajo `tests/`:
   `_SH_RE = ^\s*(tests/[\w/]+\.py)\s*$` y `_PS1_RE = ^\s*"(tests/[\w/]+\.py)"\s*,?\s*$`
   (`backend/tests/test_plan259_ratchet_script_parity.py:28-30`). `[\w/]` **no admite espacios ni puntos**, así que una
   entrada `../../Stacky tools/…` quedaría registrada **muda**: ningún gate la vería.
3. **Tercer punto de registro:** `backend/tests/harness_ratchet_allowlist.txt` (204 líneas). `test_harness_ratchet_meta.py`
   exige que **todo** `backend/tests/test_*.py` esté en `HARNESS_TEST_FILES` **o** en esa allowlist con motivo.
4. Los dos scripts **ya divergen**: `grep -cE "^\s+tests/test_" run_harness_tests.sh` → **718**;
   `grep -cE 'tests[/\\]test_' run_harness_tests.ps1` → **654**.

⇒ **la deuda H8 se declara aceptada, no se "resuelve"** (ver F8.3 reescrita). Lo único obligatorio es registrar el
**archivo de backend** de F0.3 en los **DOS** scripts, cada uno con su sintaxis.

**H9 (BAJO, pero corrige el brief) — no existe el dominio de "turnos".**
`turno` → **0**; `disponibilidad` → **0**. *(Corrección del v1, que declaraba 0 para todos)*: `cita` → **7**,
`recurso` → **15**, `profesional` → **1**, y los **23 son falsos positivos del español**: `acceptance_extractor.py:275`
*"numero **citado**"*, `discrimination_prover.py:80` *"si el ticket no lo **cita**"*,
`playbook_synthesizer.py:503` *"ULTIMO **recurso**"*, `playwright_forensic_bridge.py:46` *"tipos de **recursos** de
red"*. **Grepear vocabulario de dominio en un repo comentado en español da falsos positivos: hay que mirar los hits,
no el conteo.** `fecha|calendar` → solo comentarios y el nombre de una aserción (`navigation_contracts.yml:239`
`agenda_calendar_visible`, verificado, que comprueba que el **widget** se renderizó).
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
| H3 18 de 19 capturas sin guardia | **bajo** *(rebajado en v3 — V2: ya es 1 por paso; lo que falta es el techo)* | bajo | medio (ruido en la evidencia) |
| H4 paralelismo falso | alto (potencial sin cobrar) | **crítico si se "arregla" mal** (sesión WebForms única) | alto (config que miente) |
| H5 selectores `#c_` | bajo | **alto** (renombre masivo al tocar el `.aspx`) | alto |
| H6 deadline en 2 de las 12 etapas alcanzables | medio | medio (etapa colgada agota la corrida) | bajo |
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
   runtime es por lo tanto **idéntico y neutro** en las **11** fases, y así se declara en cada una (no es una omisión:
   es el hecho de que la frontera de proceso es `npx playwright test`, `uat_test_runner.py:351-356`, con el `Popen` en
   `:395`). Verificado: ninguna de las fases **F0..F10** toca `llm_client.py` ni una etapa que invoque un modelo.
   F10 usa `ast` de la stdlib y `grep`: neutro por construcción.
4. **Cero trabajo extra al operador.** Ninguna fase agrega un paso manual, una credencial ni una config nueva
   obligatoria. Las flags nuevas nacen **ON** (§3.1).
5. **No degradar estabilidad.** Prohibido subir `workers` por default (H4 / R-2). Prohibido bajar un timeout sin un test
   que pruebe que la espera por estado cubre el caso.
6. **Backward-compatible.** Ningún cambio de contrato de `api/qa_uat.py` ni de la forma del reporte. Los specs existentes
   siguen corriendo.
7. **Reusar antes que construir.** Es la tesis del plan: **6 de las 11 fases conectan código que ya existe**; solo F3
   y F5 escriben lógica nueva, y es mínima. **El plan se aplica la tesis a sí mismo**: F2 usa el `__captureIfBudget`
   que `screenshot_budget.py:195` ya emite en vez de reescribir el `if` *(el v2 citaba `:198`, que es una llave de
   cierre)*, y F9 lee el `reports/playwright-results.json` que el reporter `json` de `playwright.config.ts:17` ya
   escribe en vez de instrumentar nada.
8. **Ningún criterio sintáctico cierra una fase solo** *(regla nueva en v3)*. Un `grep -c` prueba que el código está
   escrito; no prueba que se ejecute, que esté en scope, ni que cambie un artefacto. Toda fase que conecte algo tiene
   además un criterio **de efecto** (F10).

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
> **Las 6 patas viven en 4 ARCHIVOS DISTINTOS, no en uno.** El v1 mandaba las patas 3 y 5 al archivo equivocado
> (`harness_flags.py`), que es justo donde un modelo menor las busca, no las encuentra y las inventa. Rutas
> **verificadas abriendo cada archivo**:

1. `FlagSpec(...)` en `Stacky Agents/backend/services/harness_flags.py` (patrón exacto: `key=`, `type="bool"`, `label=`,
   `description=`, `group="global"`, `env_only=False`, `default=True`) — copiar la forma del bloque
   **`harness_flags.py:518-531`** (`STACKY_QA_UAT_ADO_BRIDGE_ENABLED`; el `FlagSpec(` abre en `:518`, la `key=` está
   en `:519`).
2. Constante que la lee en `Stacky Agents/backend/config.py` con `os.getenv(<KEY>, "true")` — junto al bloque de las
   otras QA UAT (`config.py:1224-1240`). **Es la pata que hace que el tool vea la flag**: el pipeline corre in-process
   y sus módulos leen por `os.environ` porque `api/qa_uat.py` las exporta antes de lanzarlo (`config.py:1222-1223`).
3. Alta en **`Stacky Agents/backend/tests/test_harness_flags.py:467`** — el set `_CURATED_DEFAULTS_ON` **NO vive en
   `harness_flags.py`** (ahí solo hay un comentario que lo nombra, `:578`). El test compara **igualdad de conjuntos**,
   así que una flag `default=True` que no esté curada **rompe el arnés**. Verificable:
   `grep -n "_CURATED_DEFAULTS_ON *=" backend/tests/test_harness_flags.py` → `467`.
4. Categoría en `_CATEGORY_KEYS` (**`harness_flags.py:120`**). **NO es condicional** *(corrige el "si el registry lo
   exige" del v2 — hallazgo V10)*: `harness_flags.py:514` dice textualmente *"toda flag nueva debe agregarse también a
   `_CATEGORY_KEYS` (arriba) o el test `test_every_registry_flag_is_categorized` **rompe CI a propósito** (Plan 63)"*.
   Con 6 flags nuevas sin categorizar, CI queda rojo.
5. Entrada en `PLAIN_HELP`, que vive en **`Stacky Agents/backend/services/harness_flags_help.py:25`** — **tampoco está
   en `harness_flags.py`**. Sin esta pata la flag aparece muda en el panel del operador.
6. Verificación de que aparece en el panel de flags de la UI (`GET /api/harness/flags` la lista).

**Gate de las 6 patas (binario, corre contra el defecto).** Antes de cerrar cualquier fase con flag, para **cada** una
de las 6 keys nuevas:
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents"
K=STACKY_QA_UAT_<...>
grep -c "$K" backend/services/harness_flags.py        # >= 1  (pata 1)
grep -c "$K" backend/config.py                        # >= 1  (pata 2)
grep -c "$K" backend/tests/test_harness_flags.py      # >= 1  (pata 3)
awk '/_CATEGORY_KEYS/,/^}/' backend/services/harness_flags.py | grep -c "$K"   # >= 1  (pata 4)
grep -c "$K" backend/services/harness_flags_help.py   # >= 1  (pata 5)
# PATA 7 (NUEVA en v3, hallazgo V6): la flag tiene que ser LEIDA por alguien.
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
grep -rn "$K" --include=*.py --include=*.j2 . | grep -v __pycache__ | wc -l   # >= 1
```
Las **6** primeras tienen que dar `>= 1`. Con el código de hoy dan **0** para las 6 keys ⇒ el gate arranca ROJO, que es
lo que se espera de un gate.

> **PATA 7 — "la flag tiene que hacer algo" `[ADICIÓN ARQUITECTO v3]`.** El gate del v2 verificaba **registro**, no
> **efecto**: dos de sus seis flags (`..._STATE_WAITS_ENABLED` y `..._SCREENSHOT_BUDGET_ENABLED`) se declaraban con
> "rollback exacto por flag" y **ninguna fase las cableaba a nada** — hallazgo V6. Una flag registrada en los 5 sitios
> y leída en 0 pasa el gate viejo y es **una flag muerta en el panel del operador**: peor que no tenerla, porque miente.
> La pata 7 cuesta un `grep` y mata la clase entera.

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

# C-5b  denominador REAL de etapas (el "38" del v1 no sale de ningun comando)
grep -oE 'stages\["[^"]+"\]' qa_uat_pipeline.py | sort -u | wc -l     # 19 claves distintas
grep -cE 'stages\["[^"]+"\][[:space:]]*=' qa_uat_pipeline.py          # 35 asignaciones literales

# C-6  KPI-6: el --workers hardcodeado  (hoy: 1 ocurrencia = miente)
grep -n -- "--workers=1" uat_test_runner.py

# C-7  KPI-7: reloj de pared REAL de la ultima corrida Playwright.
#      Es lo unico que detecta que una espera por estado sea MAS LENTA que el sleep que reemplazo.
#      CORREGIDO en v3 (hallazgo V8): el v2 sumaba las "duration" de suites[*] y eso IGNORA globalSetup
#      (el login) y todo el overhead -> subestimaba 22854 ms (33%) en el reporte real del repo.
"$PY" - <<'PY'
import json, pathlib
d = json.loads(pathlib.Path("reports/playwright-results.json").read_text(encoding="utf-8"))
st = d["stats"]
per_test = []
def walk(x):
    if isinstance(x, dict):
        if "duration" in x and isinstance(x["duration"], (int, float)):
            per_test.append(x["duration"])
        for v in x.values(): walk(v)
    elif isinstance(x, list):
        for v in x: walk(v)
walk(d.get("suites", []))
n = st.get("expected", 0) + st.get("unexpected", 0) + st.get("flaky", 0)
print("wall_clock_ms=%d" % st["duration"])          # <- KPI-7 (reloj de pared)
print("tests=%d" % n)
print("ms_por_test=%d" % (st["duration"] / n if n else 0))
print("suma_in_test_ms=%d" % sum(per_test))         # solo para atribuir por test
print("startTime=%s" % st.get("startTime"))
PY
# Con el reporte de hoy: wall_clock_ms=70030  tests=3  ms_por_test=23343  suma_in_test_ms=47176

# C-8  KPI-5 (NUEVO en v3, hallazgo V1): las llamadas a _check_deadline estan EN SCOPE.
#      _check_deadline es una funcion ANIDADA en _run_pipeline_stages: llamarla desde otra
#      funcion es NameError en runtime, y compileall NO lo detecta.
"$PY" - <<'PY'
import ast, pathlib
src = pathlib.Path("qa_uat_pipeline.py").read_text(encoding="utf-8")
tree = ast.parse(src)
host = next(n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_run_pipeline_stages")
inside = {n.lineno for n in ast.walk(host)
          if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
          and n.func.id == "_check_deadline"}
todas = {n.lineno for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
         and n.func.id == "_check_deadline"}
print("llamadas_totales=%d  en_scope=%d  FUERA_DE_SCOPE=%s"
      % (len(todas), len(inside), sorted(todas - inside)))
PY
# Criterio: llamadas_totales == en_scope == 8  y  FUERA_DE_SCOPE == []
# Con el codigo de hoy: llamadas_totales=2  en_scope=2  FUERA_DE_SCOPE=[]

# C-9  KPI-8 (NUEVO en v3, hallazgo V2): PNG que un spec RENDERIZADO llega a emitir.
#      Es lo unico que prueba que F2 baja capturas de verdad y no solo mueve sintaxis.
"$PY" - <<'PY'
import re, pathlib
# Contar, sobre el .j2, cuantas capturas quedan SIN pasar por el helper de presupuesto.
t = pathlib.Path("templates/playwright_test.spec.ts.j2").read_text(encoding="utf-8")
crudas   = [i+1 for i, l in enumerate(t.splitlines()) if "page.screenshot(" in l]
guardada = [i+1 for i, l in enumerate(t.splitlines()) if "__captureIfBudget(" in l]
print("sin_guardia=%s  (esperado exactamente [325,496,798,806] tras F2)" % crudas)
print("con_guardia=%d  (esperado 15 tras F2)" % len(guardada))
PY
```

> **Advertencia sobre `C-4` (corrige el v1).** Su rama TypeScript cuenta **importadores textuales**, no alcance de
> producción: devuelve **1** para `arrival_validator.ts` porque lo importa `navigation_executor.ts:26`, que es a su vez
> un huérfano. Por eso el censo por C-4 arranca en **10**, no en 11. F0.2 mide **las dos cosas** y no permite
> "arreglar" la diferencia editando un assert. **Y el cierre de C-4 es 5, no 6** — ver la tabla de §1 (hallazgo V3).

---

## §5. Fases

**Mapeo explícito de las 3 fases pedidas por el operador → las fases de este plan:**

| Fase del brief | Fases de este plan |
|---|---|
| **Fase 1 — mejoras rápidas** (esperas fijas, reuso de sesión, selectores estables, menos pasos repetidos) | **F0, F1, F2, F3** |
| **Fase 2 — optimización de navegación** (accesos directos, datos por API, helpers semánticos, menos navegación visual) | **F4, F5, F6** |
| **Fase 3 — consolidación** (arquitectura mantenible, métricas, paralelización, observabilidad, anti-regresión) | **F7, F8, F9, F10** |

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
- **Baseline congelado en un ARCHIVO DE DATOS, no en un assert** *(corrige el v1, que mandaba editar el assert)*.
  El v1 definía `test_baseline_hoy_es_35900ms` con `assert total_ms == 35_900` y después ordenaba a F1 **editar ese
  número**. Eso entrena exactamente el reflejo que el resto del plan combate (tocar el assert para poner verde) y deja
  el nombre del test mintiendo. En su lugar:
  1. `test_congela_el_baseline_pre_plan` — si `reports/plan274_wait_baseline.json` **no existe**, lo escribe con
     `{"pre_plan": {"total_ms": <medido>, "ocurrencias": <medido>}}` y pasa. Si existe, **no lo toca**. El valor
     `pre_plan` es **inmutable**: se escribe una vez y ninguna fase lo reescribe.
  2. `test_no_empeora_respecto_del_baseline` — `total_ms_actual <= pre_plan.total_ms`. **Ratchet monótono**: F1 lo
     hace bajar y el test sigue verde sin que nadie edite nada. Es el mismo criterio DELTA que F5 y F8.2.
  3. `test_el_baseline_pre_plan_es_35900` — asserta que el `pre_plan` **grabado** vale `35_900 / 26`. Es el único
     lugar donde vive el número, y **no cambia nunca** porque describe el pasado, no el presente.
- `test_generador_tiene_una_espera_fija` — asserta que `templates/playwright_test.spec.ts.j2` tiene exactamente `1`
  ocurrencia de `waitForTimeout(`. F1 lo baja a `0` **cambiando el código, no el test**: el assert correcto es
  `<= 1` con el detalle de las líneas residuales en el mensaje (ver F1).

**F0.2 — Censo de huérfanos.** `test_plan274_orphan_census.py` define la constante
`ORPHAN_CORPUS: dict[str, int]` con las **11** entradas exactas de la tabla H1 (nombre → líneas) y un test
`test_corpus_es_exactamente_once` que asserta `len(ORPHAN_CORPUS) == 11` y `sum(ORPHAN_CORPUS.values()) == 4462`
*(las 11 cifras y el total verificados con `wc -l`, exactos)*.

Segundo test `test_censo_de_importadores`, que asserta **por módulo** (nunca un agregado) y con **dos métricas
separadas**, porque el v1 confundía una con la otra y arrancaba rojo:

| Métrica | Qué cuenta | Valor de arranque |
|---|---|---|
| `direct_importers(m)` | importadores textuales, igual que `C-4` (excluye `__pycache__`, `tests/`, `_attic`, `evals/` y el propio archivo) | **10** módulos en 0 (`arrival_validator.ts` da **1**) |
| `prod_reachable(m)` | ¿algún importador es alcanzable desde `qa_uat_pipeline.py` o desde un `.spec.ts` vivo? | **11** módulos en 0 |

- `test_arranque_directo_es_diez` — asserta `sum(1 for m in ORPHAN_CORPUS if direct_importers(m) == 0) == 10` **y**
  que el único con importador es `playwright/helpers/arrival_validator.ts`, **nombrándolo**. Con el estado de hoy: verde.
- `test_arranque_alcanzable_es_once` — asserta que los 11 tienen `prod_reachable == False`.
- `test_esperado_de_la_fase_en_curso` — tabla `EXPECTED_CONNECTED: dict[str, str]` (módulo → fase que lo conecta) que
  **crece de a un módulo por fase**, y asserta por módulo con el nombre en el mensaje de fallo.

> **Por qué el criterio no es "la lista está vacía":** un conteo agregado sobre "cuántos huérfanos quedan" colapsa N
> casos en 1 y no discrimina cuál se conectó. El test asserta **por módulo**, con el nombre en el mensaje de fallo.
> **Y por qué son dos métricas:** conectar un módulo a otro huérfano no lo conecta a producción. Sin `prod_reachable`,
> un implementador cierra KPI-4a importando un huérfano desde otro huérfano.

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

**F0.5 — Baseline de RELOJ DE PARED (movido del final a F0 en v3 — hallazgo V5).** Correr **una sola vez, acá y no
después**, `test_baseline_de_reloj_existe_o_se_crea` de F9 (§5/F9 paso 2) para que
`reports/plan274_wallclock_baseline.json` quede escrito con el reloj **anterior** a cualquier cambio de F1.
> **Por qué acá.** F9 existe para detectar que una espera por estado sea **más lenta** que el sleep que reemplazó (C10).
> Si el baseline se captura al final —como ordenaba §8 del v2— congela el reloj **ya modificado** y el ratchet no puede
> detectar nada: el gate más importante del plan quedaba ciego a su propio riesgo principal.
> Si no hay un `reports/playwright-results.json` reciente, **hay que producirlo**: es la única corrida "antes" que
> existirá. Sin ese archivo, KPI-7 queda `NO MEDIBLE` y hay que anotarlo así en §9 — **no** inventar un baseline
> post-hoc.

**Tests + comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_baseline.py tests/unit/test_plan274_orphan_census.py -v
"$PY" -m pytest tests/unit/test_plan274_wallclock.py::test_baseline_de_reloj_existe_o_se_crea -v   # F0.5
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
"$PY" -m pytest tests/test_plan274_tool_tests_outside_ratchet.py -v
```
**Criterio de aceptación BINARIO.** Los 3 archivos existen y los comandos de arriba reportan **≥ 11 passed, 0 failed**
*(el v2 decía "≥ 8 (… 3 de censo)" y F0.2 define **5** tests de censo — hallazgo V13; el desglose real es: 3 de baseline
+ 1 de generador + 1 de reuso de sesión + **5** de censo + 1 de arnés = **11**)*. El número de `passed` debe aparecer en
la salida; exit 0 con `0 passed` **no cuenta**. Además `reports/plan274_wait_baseline.json` existe y su
`pre_plan.total_ms` es `35900`, **y `reports/plan274_wallclock_baseline.json` existe** (F0.5) o KPI-7 está declarado
`NO MEDIBLE` en §9 con el motivo.
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
+    {% if state_waits_enabled %}await waitForAgendaStable(page, 5_000);{% else %}await page.waitForTimeout(800);{% endif %}
```
El helper **ya está definido en el mismo archivo** (`waitForAspNetIdle` en `:40`, `waitForAgendaStable` en `:63`,
verificados), no hay que importar nada.

> **La rama Jinja NO es adorno: sin ella la flag de esta fase es una flag MUERTA (hallazgo V6).**
> El v2 escribía un reemplazo **literal** y a la vez declaraba *"con la flag OFF, el template emite el sleep viejo
> (rollback sin revertir código)"*. Con una edición literal **no hay ningún camino que emita el sleep viejo**: la flag
> quedaba registrada en los 5 archivos del arnés, visible en el panel del operador, y **sin efecto alguno**. Peor: el
> gate de patas del v2 (4 `grep`) **daba verde**, porque verifica registro y no efecto. De ahí sale la **pata 7** de §3.1.
>
> **Cableado obligatorio, en `playwright_test_generator.py`**, junto al `template.render(...)` de `:384` y de `:932`
> (los mismos dos call sites que toca F2):
> ```python
> state_waits_enabled=os.environ.get("STACKY_QA_UAT_STATE_WAITS_ENABLED", "true").lower() == "true",
> ```
> Con esto **`grep -rn "STACKY_QA_UAT_STATE_WAITS_ENABLED" --include=*.py --include=*.j2 .` da ≥ 2** (generador + `.j2`)
> y la pata 7 pasa. Sin esto da **0** y la fase **no cierra**.

> **UNA sola llamada, no dos (corrige el v1).** El v1 encadenaba `waitForAspNetIdle(page)` **y**
> `waitForAgendaStable(page)`. Pero `waitForAgendaStable` **ya delega** en `waitForAspNetIdle` (`:64-66`), así que el
> v1 esperaba el mismo estado dos veces: `waitForAspNetIdle(page)` con su default de **3 s** más
> `waitForAgendaStable(page)` con su default de **10 s**. En una página cuyo `PageRequestManager` no se aquieta
> (ninguno de los dos lanza: `.catch(() => false)`), eso son **hasta 13 s donde había 800 ms**.
> **Y KPI-1 daría verde igual**, porque KPI-1 cuenta ms `waitForTimeout` **escritos en el archivo**, no reloj de pared.
> Ese es exactamente el agujero que tapa el KPI-7 / F9. El `5_000` explícito acota el peor caso a ~5 s y sigue muy por
> encima de los 800 ms que reemplaza.
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
- `test_generador_sin_espera_fija_o_documentada` — cada `waitForTimeout(` que quede en el `.j2` **fuera de la rama
  `{% else %}` de la flag** debe tener en la línea anterior o siguiente el marcador literal `plan-274 F1.1`.
  Sin marcador → falla nombrando la línea.
- `test_specs_vivos_bajo_umbral` — `_sum_fixed_waits` sobre los 5 specs devuelve `total_ms <= 3000`.
- `test_toda_espera_residual_esta_marcada` — cada `waitForTimeout(` residual en los 5 specs tiene el marcador
  `plan-274 F1.2` adyacente.
- `test_la_flag_gobierna_el_render` **(nuevo en v3, hallazgo V6)** — renderizar el template **dos veces**, con
  `STACKY_QA_UAT_STATE_WAITS_ENABLED=true` y `=false`, y asertar que el primero contiene `waitForAgendaStable(page, 5_000)`
  y **no** `waitForTimeout(800)`, y el segundo exactamente al revés. **Corre contra el defecto del v2**: con su diff
  literal, los dos renders son idénticos y el test da ROJO.
> **Este test discrimina de verdad:** no asserta "la lista está vacía" (que un modelo menor satisface borrando el
> assert), asserta **por ocurrencia y con la línea en el mensaje**.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_no_fixed_waits.py -v
bash -c 'grep -ohE "waitForTimeout\([0-9]+\)" playwright/uat/*.spec.ts playwright/smoke/*.spec.ts | grep -oE "[0-9]+" | awk "{s+=\$1} END {print s}"'
grep -rn "STACKY_QA_UAT_STATE_WAITS_ENABLED" --include=*.py --include=*.j2 . | grep -v __pycache__ | wc -l   # >= 2 (pata 7)
```
**Criterio BINARIO.** `test_plan274_no_fixed_waits.py` reporta **4 passed, 0 failed**, Y el comando `C-1` devuelve
`total_ms <= 3000`, Y el **conteo de la pata 7 es ≥ 2**, Y toda espera residual del `.j2` fuera de la rama de rollback
tiene marcador (lo prueba el primer test).
**Flag:** `STACKY_QA_UAT_STATE_WAITS_ENABLED` (**ON**, §3.1), cableada según F1.1 — **la rama Jinja es parte del
entregable, no un comentario**. Los specs ya editados no dependen de la flag (son archivos, no runtime) — **decirlo así
en el plan es honesto**: el rollback total de F1.2 es `git revert`, no la flag.
**Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F2 — Presupuesto de capturas: conectar `screenshot_budget.py` (huérfano #9)

**Objetivo (REESCRITO en v3 — hallazgo V2; el del v2 era falso).** Poner **un techo real de 25 capturas por escenario**
y un presupuesto por paso **que pueda activarse**, usando el módulo que ya existe y ya está testeado.

> **Lo que el v2 prometía y no podía cumplir.** Decía *"pasar de 17 capturas incondicionales **por paso** a 1 en éxito
> / 3 en fallo / 25 techo"*. Verificado abriendo el template y los specs:
> ```bash
> grep -n "page.screenshot(" templates/playwright_test.spec.ts.j2   # 19 lineas: 1 por rama de accion
> for f in playwright/uat/*.spec.ts playwright/smoke/*.spec.ts; do echo -n "$f "; grep -c "page.screenshot(" $f; done  # 1 c/u
> ```
> **El template ya emite exactamente UNA captura por paso.** Y el corte del módulo es
> `const limit = stepOk ? __SS_ON_SUCCESS(1) : __SS_ON_FAILURE(3); if (captureIndex >= limit)`
> (`screenshot_budget.py:190-191`). Con la llamada que ordenaba el v2 —`__captureIfBudget(page, path, true, 0)`— sale
> `0 >= 1` ⇒ **false** ⇒ **captura siempre**. Es decir: el presupuesto **por paso** nace estructuralmente inerte y el
> único límite que puede activarse es el techo de 25. Y como el criterio del v2 era **sintáctico** (`≤4 capturas sin
> guardia`), la fase habría cerrado en verde **con cero PNG de diferencia**. Es el patrón que el propio v2 mató en F7.2
> (C9) y reintrodujo acá.
>
> **Qué gana F2 realmente, dicho sin maquillaje:** (a) el **techo de 25/escenario**, que hoy **no existe**;
> (b) el `.catch(() => null)` uniforme, que hoy sólo tienen `:325` y `:798`; (c) el `captureIndex` correcto, que deja
> el presupuesto **listo para activarse** el día que una rama emita una segunda captura en el mismo paso.
> Nada de eso justifica prometer una reducción que no va a ocurrir.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/playwright_test_generator.py` (render del template: `:179`, `:384`, `:932`)
- `Stacky tools/QA UAT Agent/templates/playwright_test.spec.ts.j2` (**19** sitios de `page.screenshot`, de los cuales se
  envuelven **15**) *(el v2 decía "17 sitios" en el encabezado y "las 15 envolvibles" en el cuerpo — hallazgo V7/V20)*

**Cómo.** `screenshot_budget.py` ya expone lo necesario: `load_budget()` (`:86`), `should_capture()` (`:116`) y
`build_ts_budget_block(budget)` (`:154`), con los defaults `1/3/25` (`:52-54`).
1. En `playwright_test_generator.py`, junto al `template.render(...)` de `:384` y de `:932`, agregar al contexto:
   `screenshot_budget_block=build_ts_budget_block(load_budget())` (import a nivel de módulo:
   `from screenshot_budget import load_budget, build_ts_budget_block`).
2. En el `.j2`, insertar `{{ screenshot_budget_block }}` una sola vez en el preámbulo (junto a los helpers de `:40-66`)
   y reemplazar **las 15 capturas envolvibles** (grupos A y B de la tabla de H3) por el helper que **ese mismo bloque
   ya emite**:
   ```diff
   -    await page.screenshot({ path: 'evidence/.../step_XX_after.png' });
   +    await __captureIfBudget(page, 'evidence/.../step_XX_after.png', true, __ssStepIdx++);
   ```
   **NO tocar** `:496` (setup), `:798` (final_state), `:806` (`afterEach`) ni `:325` (captura de excepción ASP.NET, que
   **ya es condicional** — envolverla en una guardia de *éxito* borraría justo la evidencia de un fallo).

   > **`captureIndex` incremental, no `0` fijo (corrige el v2 — hallazgo V2).** El v2 ordenaba pasar `0` literal.
   > Con `0` constante la condición `captureIndex >= limit` es `0 >= 1` = **false para siempre** ⇒ el presupuesto por
   > paso **no puede activarse nunca** y la fase cierra en verde sin bajar un solo PNG. Se declara en el preámbulo del
   > spec `let __ssStepIdx = 0;` y **se reinicia a `0` al empezar cada paso** (una línea en el `{% for step in pasos %}`,
   > junto al `_stepRef.current = {{ loop.index }}` que ya existe en `:561`/`:575`). Así el índice representa lo que el
   > módulo modela: *"cuál captura de ESTE paso es"*. El comportamiento nominal no cambia (1 captura por paso ⇒ índice 0),
   > pero el gate deja de ser decorativo y una segunda captura en el mismo paso **se corta de verdad**.

   > **Firma real, verificada (corrige el v1).** El v1 escribía `if (__shouldCapture('success'))`. La función que
   > `build_ts_budget_block` emite es **`__shouldCapture(stepOk: boolean, captureIndex: number)`**
   > (**`screenshot_budget.py:181`**; el v2 escribía `:180` en esta fase y `:181` en su changelog — `:180` es
   > `let __ss_exceeded = false;`), de **dos** parámetros. Con un solo argumento: (a) `npx tsc --noEmit` falla por
   > aridad — y el DoD exige tsc limpio; (b) en runtime `captureIndex` es `undefined`, `undefined >= limit` evalúa a
   > `false`, no se corta nada y **el presupuesto por paso queda inerte** (solo sobreviviría el techo de 25).
   > Un plan cuyo criterio es "≤N sin guardia" habría dado verde con la feature muerta.
   > Además el bloque **ya expone** `__captureIfBudget(page, path, stepOk, captureIndex = 0)`
   > (**firma en `screenshot_budget.py:195`**, cuerpo `:196-199`),
   > que hace exactamente el `if` + `page.screenshot(...).catch(() => null)`. Usar ese helper y no reescribirlo:
   > es la tesis del plan (reusar antes que construir) aplicada a sí mismo.
3. **Casos borde.** Si `load_budget()` lanza (config ausente) → `build_ts_budget_block` debe recibir el
   `ScreenshotBudget` por default; el generador **no debe fallar** por esto: envolver en `try/except Exception` y, en el
   `except`, pasar `screenshot_budget_block=""` + emitir la captura sin guardia (comportamiento de hoy). Degrada, no rompe.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_screenshot_budget_wired.py`:
- `test_generador_importa_el_presupuesto` — `screenshot_budget` tiene ≥ 1 importador de producción (invierte la fila 9
  del censo F0.2).
- `test_template_tiene_el_bloque` — el `.j2` contiene `{{ screenshot_budget_block }}` exactamente 1 vez.
- `test_capturas_por_paso_estan_guardadas` — el conjunto de líneas del `.j2` con `page.screenshot(` **sin** guardia de
  presupuesto debe ser **exactamente `{325, 496, 798, 806}`**, comparado como **conjunto**, con las sobrantes y las
  faltantes nombradas en el mensaje de fallo.
  > **Por qué "≤ 2" del v1 era insatisfacible.** El propio F2 manda dejar sin guardia `:496`, `:798` y `:806`, y
  > `:325` es una captura de error que no puede llevar guardia de éxito ⇒ el mínimo alcanzable es **4**, nunca 2.
  > Un modelo menor "cierra" esa contradicción borrando el assert o envolviendo la captura de excepción — las dos
  > salidas son peores que el bug. Se assertan **las 4 por número de línea**, no un umbral.
  > Anclaje por estructura, no por línea: si el `.j2` se corre de lugar, el test debe localizarlas por su `path`
  > (`step_00_setup.png`, `step_final_state.png`, `step_aftereach_state.png`, `aspnet_exception_step_`) y reportar los
  > números nuevos, no fallar por el desplazamiento.
- `test_no_queda_ninguna_llamada_de_aridad_uno` — **cero** ocurrencias de `__shouldCapture(` con un solo argumento en
  el `.j2` (regex `__shouldCapture\([^,)]*\)`). Corre contra el defecto del v1: con el diff que proponía el v1, ROJO.
- `test_generador_degrada_si_el_presupuesto_falla` — monkeypatchear `load_budget` para que lance, y verificar que el
  render **igual produce** un spec válido.
- `test_el_techo_de_25_se_activa` **(nuevo en v3, hallazgo V2 — es el ÚNICO test de efecto de esta fase)** — renderizar
  un escenario con **30 pasos**, ejecutar el bloque TS emitido con un `page` doble que cuenta llamadas a `screenshot`,
  y asertar que se emitieron **25**, no 30. **Corre contra el defecto:** con `captureIndex=0` fijo y sin techo el
  contador da 30 y el test es ROJO. Si el arnés no puede evaluar TS, la variante equivalente en Python es llamar
  `should_capture(budget, step_ok=True, taken_so_far=n, step_capture_index=0)` para `n` de 0..29 y asertar
  **25 `True` / 5 `False`** (`screenshot_budget.py:144-145`, verificado).
- `test_captureindex_no_es_constante` **(nuevo en v3)** — el `.j2` **no** contiene el literal `, true, 0)` en ninguna
  llamada a `__captureIfBudget`, y **sí** contiene `__ssStepIdx`. Corre contra el diff exacto que ordenaba el v2.
- `test_la_flag_gobierna_el_bloque` **(nuevo en v3, hallazgo V6)** — con `STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED=false`
  el bloque emitido es el de la rama `disabled` (`__shouldCapture` retorna `true` siempre, `screenshot_budget.py:168-170`).

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_screenshot_budget_wired.py -v
"$PY" -m pytest tests/unit/test_plan274_orphan_census.py -v
grep -rn "STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED" --include=*.py . | grep -v __pycache__ | wc -l   # >= 1 (pata 7)
```
**Criterio BINARIO.** `8 passed, 0 failed` en el primero, Y el censo de F0.2 pasa con `screenshot_budget` en
`direct_importers >= 1` **y** `prod_reachable == True` (el importador es `playwright_test_generator.py`, que **sí**
está en el camino de producción), Y `npx tsc --noEmit` no introduce errores nuevos sobre el spec renderizado,
Y **`C-9` devuelve `sin_guardia == [325, 496, 798, 806]` y `con_guardia == 15`**, Y el conteo de la pata 7 es ≥ 1.
Censo: `direct` 10 → **9**, `alcanzable` 11 → **10**.
**Flag:** `STACKY_QA_UAT_SCREENSHOT_BUDGET_ENABLED` (**ON**). **Cableado obligatorio (hallazgo V6):** el camino
"bloque inerte" de `build_ts_budget_block` se activa con `budget.disabled`, que **sólo** lee
`QA_UAT_SCREENSHOT_BUDGET_DISABLED` (`screenshot_budget.py:99`) — **la flag nueva no está conectada a nada por sí sola**.
En `playwright_test_generator.py`, la llamada debe ser
`load_budget()` si la flag está en `true`, y `ScreenshotBudget(disabled=True)` si está en `false`. Sin este cableado la
flag es muda y la fase no cierra por la pata 7.
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

**Cómo.** Justo después de construir `url` (bloque `:386-393`) y **antes** del `return _allow(` de `:394` cuyo
`strategy="deeplink"` está en `:395`, insertar:
```python
if os.environ.get("STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED", "true").lower() == "true":
    probe = None
    try:
        from deeplink_readiness_checker import check_deeplink_readiness
        # Firma real (deeplink_readiness_checker.py:77-84):
        #   check_deeplink_readiness(screen, params=None, base_url=None,
        #                            contracts_path=None, timeout_s=10.0, ...)
        # base_url se omite a proposito: el modulo cae a AGENDA_WEB_BASE_URL por si mismo.
        probe = check_deeplink_readiness(
            screen=target_screen,          # NO existe una variable `screen` en este scope
            params=available_data,         # NO existe una variable `params` en este scope
            contracts_path=contracts_path,
            timeout_s=_DEEPLINK_PROBE_TIMEOUT_S,   # constante del modulo = 5.0 (ver nota)
        )
    except Exception:
        probe = None            # el probe NUNCA decide por una excepcion propia
    # Contrato REAL del modulo: devuelve "decision" in {"PASS","BLOCKED"} (:340 y :143).
    # NO devuelve ninguna clave "ready".
    if probe is not None and probe.get("decision") != "PASS":
        # el deeplink no sirve -> degradar a la estrategia siguiente, NO bloquear la corrida
        return _fallback_after_failed_deeplink(
            target_screen, lane, human_paths, direct_entry_allowed, probe)
```

> **Los 2 defectos del v1 que esto corrige (los dos hacían que F4 fuera peor que no hacerla):**
>
> 1. **`probe.get("ready", False)` — clave INEXISTENTE.** `check_deeplink_readiness` construye su resultado en
>    `_build_result` (`deeplink_readiness_checker.py:362-386`) y **no hay ninguna clave `ready`**
>    (`grep -n '"ready"' deeplink_readiness_checker.py` → 0 líneas). La clave es **`decision`**, con valores
>    `"PASS"` (`:340`) y `"BLOCKED"` (`:143, :165, :190, :237, :262, :300, :322`). Con `.get("ready", False)` el
>    resultado es **siempre falso**, la condición `not ...` es **siempre verdadera**, y **F4 degradaría el deeplink
>    SIEMPRE, incluso cuando el probe dice PASS**. Es decir: la fase que dice "validar el deeplink" lo **desactivaba**.
>    Y los 5 tests del v1 daban verde porque todos usan un doble que devuelve `{"ready": True}`, una forma que el
>    módulo real **nunca** produce: falso verde de manual.
> 2. **3 identificadores fuera de scope.** La firma real es
>    `resolve_navigation_strategy(ticket_id, scenario_id, target_screen, lane, available_data=None, contracts_path=None, allow_deeplink_override=False)`
>    (`navigation_strategy_resolver.py:151-158`). **No existen** `screen`, `params` ni `base_url`: son
>    `target_screen` (`:154`), `available_data` (`:156`, normalizado en `:191`) y —para `base_url`— nada, porque el
>    checker resuelve `AGENDA_WEB_BASE_URL` solo. El snippet del v1 era un `NameError` en la primera corrida real.

`_fallback_after_failed_deeplink(target_screen, lane, human_paths, direct_entry_allowed, probe)` devuelve la estrategia
que el resolver ya elegiría si el deeplink no estuviera permitido, usando las variables que **sí** existen en ese scope
(`human_paths` se calcula en `:238`, `direct_entry_allowed` en `:234`): `human_path` si `human_paths` no está vacío;
si no `direct_entry` cuando `direct_entry_allowed`; si no `_blocked(...)` (`:454`) con `reason` que incluya
`probe["reason"]` y `probe["category"]`.
**Caso borde crítico (falla ABIERTO, a propósito):** si el probe **no puede** correr (módulo ausente, red caída,
timeout), `probe is None` y el flujo sigue **exactamente como hoy**. Un probe roto no debe bloquear una corrida que
antes funcionaba.
**Costo:** el probe hace un GET HTTP. `timeout_s` se acota a **5 s** (el default del módulo es 10) para que el peor
caso del probe no se coma el presupuesto de 6 min que F7.1 está tratando de proteger.

> **Sin env var nueva (corrige el v2 — hallazgo V12).** El v2 introducía `QA_UAT_DEEPLINK_PROBE_TIMEOUT_S`: una
> **config de operador nueva, env-only y fuera del panel de flags**. Riel del producto: toda config del operador va
> **por UI**; sólo los kill-switches son env-only, y un timeout de probe no lo es. Se declara
> `_DEEPLINK_PROBE_TIMEOUT_S: float = 5.0` como constante de módulo en `navigation_strategy_resolver.py`, junto a
> `_HUMAN_ONLY_LANES` (`:65`). Si algún día hay que exponerlo, entra como `FlagSpec(type="float")` — el registry ya
> soporta ese tipo. **Cero trabajo extra al operador.**

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_deeplink_probe.py` (todo con doble, sin red).
**Los dobles devuelven la forma REAL del módulo** (`decision`/`category`/`reason`/`checks`), nunca una inventada:
- `test_el_doble_usa_la_forma_real` — **corre primero**: asserta que las claves del doble son un subconjunto de las de
  `_build_result` importado del módulo real (`{"event","screen","url_pattern","params","url","checks",
  "missing_params","decision","category","reason","human_action_required"}`) **y** que `"ready"` **no** es una de ellas.
  > Este test es el centinela anti-falso-verde de toda la fase: sin él, los 5 de abajo pasan contra una forma que el
  > módulo real nunca emite, que es exactamente lo que le pasó al v1.
- `test_probe_pass_mantiene_deeplink` — probe `decision="PASS"` → `strategy == "deeplink"`.
- `test_probe_blocked_por_login_degrada_a_human_path` — probe `decision="BLOCKED", reason="redirected_to_login"` y
  contrato con `human_paths` → `strategy == "human_path"` **y** el `reason` del resultado contiene `redirected_to_login`.
- `test_probe_falla_abierto_si_lanza` — `check_deeplink_readiness` lanza → `strategy == "deeplink"` (igual que hoy).
- `test_flag_off_no_llama_al_probe` — flag `false` → el doble **no** se invoca (`assert mock.call_count == 0`).
- `test_lane_humano_sigue_prohibido` — lane `uat_human` con contrato que prohíbe deeplink
  (`navigation_contracts.yml:142-144`, verificado) → **nunca** se llama al probe ni se devuelve `deeplink`
  (centinela del plan 240).
- `test_se_invoca_con_los_nombres_reales` — inspecciona los kwargs con que se llamó al doble y asserta
  `screen == <target_screen>` y `params == <available_data>`. Corre contra el defecto del v1: con su snippet, `NameError`.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_deeplink_probe.py -v
"$PY" -m pytest tests/unit/test_plan274_orphan_census.py -v
"$PY" -c "import ast,sys; ast.parse(open('navigation_strategy_resolver.py',encoding='utf-8').read())"
```
**Criterio BINARIO.** `7 passed, 0 failed` Y censo: `direct` 9 → **8**, `alcanzable` 10 → **9**
(`deeplink_readiness_checker` importado desde `navigation_strategy_resolver.py`, que **sí** está en el camino de
producción).
**Flag:** `STACKY_QA_UAT_DEEPLINK_PROBE_ENABLED` (**ON**). **Trabajo del operador:** ninguno.
**Runtimes:** neutro en los 3.

---

### F5 — Fragilidad de selectores medida (no reescrita)

**Objetivo.** Saber **cuáles** de los 140 selectores (105 `locator(` + 35 `#c_`) son bombas de tiempo, y que agregar uno
nuevo peor que el peor de hoy dé rojo. **No** se migra a `getByRole`: la app es WebForms y no expone roles ni test-ids
(H5), así que exigirlo sería inventar alcance.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/qa_uat_pipeline.py`, **etapa `stages["selector_contract"]`**, cuyo import vivo está en
  **`qa_uat_pipeline.py:2062`** (`from selector_contract_validator import validate_all_scenarios as _validate_sc`) y
  cuyo `except` está en `:2144`. Ese módulo **sí** está cableado, verificado. *(El v1 decía "junto a la etapa que ya usa
  `selector_contract_validator`" sin dar la línea: un modelo menor tiene que adivinar dónde. Ahora está anclado.)*

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
**Criterio BINARIO.** `3 passed, 0 failed`, Y `locator_quality` pasa a **≥1** importador de producción.
Censo: `direct` 8 → **7**, `alcanzable` 9 → **8** *(el v2 escribía "censo → 8" sin decir qué métrica y sin decrementar
`direct`; ese salto es el origen del hallazgo V3 — la cadena entera cerraba una unidad arriba)*.
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

**Cómo.** Cache-aside **por campo**, alrededor de la llamada a `_run_sqlcmd` que vive dentro de `resolve_fields`
(**`data_resolver.py:388`**, `value, exec_error = _run_sqlcmd(hint_query, db_server, db_user, db_pass)` — verificado;
`_run_sqlcmd` se define en `:500`):
```python
# plan-274 F6, dentro del loop por campo de resolve_fields, JUSTO ANTES de la linea 388.
# `field_name` es el nombre REAL de la variable del loop (verificado: data_resolver.py:360-388).
import test_data_cache
if _cache_enabled():
    hit = test_data_cache.get_data(field_name)          # test_data_cache.py:67
    if hit is not None:
        resolved[field_name] = hit                      # `resolved` se declara en :299
        continue                                        # HIT: no se toca sqlcmd
value, exec_error = _run_sqlcmd(hint_query, db_server, db_user, db_pass)   # :388
if _cache_enabled() and value and not exec_error:
    test_data_cache.store_data(                         # test_data_cache.py:93
        field_name, value, source="data_resolver.resolve_fields", notes="plan-274 F6")
```

> **Dos correcciones al v1, las dos verificadas abriendo el módulo:**
>
> 1. **`put_data` NO EXISTE.** La API pública real de `test_data_cache.py` es `get_data(field)` (`:67`),
>    **`store_data(field, value, source="unknown", notes="", ttl_hours=None)`** (`:93`), `invalidate` (`:120`),
>    `clear_expired` (`:129`), `clear_all` (`:145`), `list_entries` (`:157`). No hay ningún `put_data`:
>    `grep -n "^def " test_data_cache.py` lo confirma. El snippet del v1 era un `AttributeError`.
> 2. **El módulo es por CAMPO, no por hash de query.** `_entry_file(field)` (`:59-62`) sanitiza el nombre y escribe
>    **un archivo por campo**; `get_data`/`store_data`/`invalidate` toman `field: str`. El `cache_key` del v1
>    (hash de `(tabla, columnas, filtros)`) "funcionaría" solo porque el sanitizador acepta cualquier string, pero:
>    (a) rompe `invalidate(field)`, que el operador y `clear_expired` usan por nombre de campo; (b) `resolve_fields`
>    resuelve **N campos**, así que cachear el agregado bajo una clave impide reusar los N−1 campos ya resueltos
>    cuando uno cambia; (c) tira la metadata `source`/`notes` que el módulo ya persiste. Se cachea **por campo**, que
>    es el grano que el módulo ya modela.
- TTL: el que ya trae el módulo — 8 h, **`test_data_cache.py:52`** (`_DEFAULT_TTL_HOURS = 8`; el v1 decía `:49-50`),
  overrideable por `QA_UAT_DATA_CACHE_TTL_HOURS` (`:55-56`). **Sin inventar uno nuevo.**
- **Bypass ya existente que hay que respetar:** `QA_UAT_FORCE_RUN=true` salta el cache (`test_data_cache.py:72`).
- **Caso borde:** si el cache lanza (JSON corrupto, disco lleno) → `except Exception` → seguir por el camino SQL normal.
  Un cache roto nunca debe romper una resolución que funcionaba.
- **Qué NO cachear:** resultados vacíos (`result` falsy). Cachear un "no encontré" durante 8 h escondería un dato que
  apareció después.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_data_cache_wired.py` (con doble de `_run_sqlcmd`,
sin BD):
- `test_la_api_del_modulo_es_la_que_creemos` — **corre primero**: `hasattr(test_data_cache, "store_data") is True` y
  `hasattr(test_data_cache, "put_data") is False`. Centinela anti-`AttributeError`: con el snippet del v1, ROJO.
- `test_segunda_llamada_no_toca_sqlcmd` — 2 resoluciones del mismo campo → el doble de `_run_sqlcmd` se invocó **1** vez.
- `test_cachea_por_campo_no_por_query` — resolver 2 campos y después pedir **solo el segundo** → **0** invocaciones
  nuevas (con clave agregada habría 1). Discrimina el diseño del v1 del correcto.
- `test_force_run_ignora_el_cache` — `QA_UAT_FORCE_RUN=true` → **2** invocaciones (`test_data_cache.py:72`, verificado).
- `test_flag_off_no_cachea` — flag `false` → **2** invocaciones.
- `test_cache_roto_no_rompe` — `get_data` lanza → se resuelve igual por SQL (1 invocación, sin excepción).
- `test_resultado_vacio_no_se_cachea` — `value = ""`/`None` → segunda llamada vuelve a consultar (**2** invocaciones).
- `test_error_de_sql_no_se_cachea` — `exec_error` no vacío → no se llama a `store_data`. Cachear un error 8 h
  esconde una BD caída.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_data_cache_wired.py -v
```
**Criterio BINARIO.** `8 passed, 0 failed`, Y censo: `direct` 7 → **6**, `alcanzable` 8 → **7**
*(recalculado en v3: el v2 decía 8→7 / 9→8 porque su cadena se saltaba el decremento de F5 — hallazgo V3)*.
**Flag:** `STACKY_QA_UAT_DATA_CACHE_ENABLED` (**ON**), leída por `_cache_enabled()` en `data_resolver.py` ⇒ pata 7 ≥ 1.
**Trabajo del operador:** ninguno.
**Runtimes:** neutro en los 3.

---

### F7 — Consolidación: deadline útil, timeout recomendado, y la puerta al paralelismo

**Objetivo.** Que el presupuesto de 6 minutos sirva, que el timeout por caso salga de datos y no de un número mágico, y
que quede **escrito** qué falta exactamente para paralelizar.

**Archivos a editar:**
- `Stacky tools/QA UAT Agent/qa_uat_pipeline.py`
- `Stacky tools/QA UAT Agent/uat_test_runner.py`

**F7.1 — `_check_deadline` en 6 etapas más (H6).** Hoy: 2 llamadas (`:1673`, `:3402`) + 1 definición (`:1406`).

> **Historia de esta sublista, porque explica el criterio.** El **v1** inventó 6 claves que no existían
> (`data_resolution`, `precondition_check`, `seed_generation`, `spec_generation`, `playwright_run`, `evidence_publish`
> → `0 0 0 0 0 0` hits). El **v2** las reemplazó por 6 claves reales… y **no verificó que `_check_deadline` fuera
> alcanzable desde ellas**. Tres de sus seis (`evidence` `:734`, `dossier` `:857`, `publisher` `:907`) están en **otras
> funciones**: `_check_deadline` es un **closure anidado en `_run_pipeline_stages`** (`:1324` / `:1406`, ver H6-bis)
> ⇒ **`NameError` en la primera corrida real**. Y una cuarta (`screen_detection`) **ya tiene su chequeo** en `:1673`.
>
> **Por qué el gate del v2 no lo atrapaba — verificado ejecutándolo.** Insertando la llamada prohibida en `:857`:
> ```
> AST parsea OK             -> `python -m compileall` da VERDE
> grep -c "_check_deadline(" -> 4  (SUBE: el gate del v2 PREMIA el bug, acerca al objetivo de 9)
> C-8 (AST de scope)         -> llamadas_totales=3 en_scope=2 FUERA_DE_SCOPE=[857]  -> ROJO
> ```
> Un gate que sube de puntaje cuando metés el defecto no es un gate. Por eso el criterio de F7.1 pasa a ser **C-8**.

**Lista CERRADA v3 (6 claves, TODAS verificadas EN SCOPE y sin chequeo previo).** Filtro aplicado: la clave debe
asignarse dentro de `_run_pipeline_stages` (`:1324`-`:3793`) — las 12 candidatas están en la tabla de H6-bis — y no
tener ya un `_check_deadline` cubriéndola. Se eligen las que disparan trabajo pesado (subprocess, red, BD, I/O):

| # | Clave `stages["…"]` | Línea de referencia | Por qué |
|---|---|---|---|
| 1 | `compiler_contract` | `:1957` | compila los escenarios; primer bloque pesado tras la detección de pantalla |
| 2 | `selector_contract` | `:2076` | invoca `selector_contract_validator` (módulo externo) y es donde F5 agrega trabajo |
| 3 | `generator_contract` | `:3121` | genera los `.spec.ts`; I/O sobre N archivos |
| 4 | `evaluator` | `:3170` | evaluación de aserciones post-corrida |
| 5 | `failure_analyzer` | `:3171` | análisis pesado post-corrida *(única sobreviviente de la lista del v2)* |
| 6 | `run_metrics_summary` | `:3625` | agregación final; última chance de cortar antes del cierre |

**Ya cubiertas, NO tocar (evita el duplicado del v2):** `screen_detection` (`:1673`) y `runner` (`:3402`).
**PROHIBIDAS (fuera de scope, `NameError`):** `dossier`, `epic_rollup`, `evidence`, `functional_verdict`,
`intent_parser`, `publisher`, `synthetic_ticket_builder`.
Si alguna de las 6 desapareciera, **el reemplazo sale exclusivamente de la columna "EN SCOPE (12)" de H6-bis** y se
anota en §9. Está **prohibido** introducir una clave de la columna prohibida, aunque el `grep -c` dé verde.

Patrón exacto, idéntico al de `:1673` (verificado); `stage` debe ser la variable de etapa viva en ese punto:
```python
if _dl := _check_deadline(stage):
    return _dl
```
**F7.2 — Timeout recomendado por datos (`playbook_performance.py`, huérfano #7) — LECTURA *y* ESCRITURA.**
En `uat_test_runner.py`, donde hoy se usa `_DEFAULT_TIMEOUT_MS = 90_000` (`:48`, consumido en `:84` y en el
`f"--timeout={timeout_ms}"` de **`:354`** — el v1 decía `:352`, que es la línea `"npx", "playwright", "test",`).

> **El v1 conectaba el lector de un store que NADIE escribe ⇒ la fase nacía inerte.**
> `playbook_performance.record_run` tiene **0 callers de producción** (H7-bis). Sin escritor,
> `_load(playbook_id)` (usado en `recommend_timeout_ms`, `:165`) devuelve `{}`, `p95_duration_ms` es `0`, y `recommend_timeout_ms` sale por
> `if p95 <= 0: return default_ms` (`playbook_performance.py:167-168`) **en el 100 % de las corridas, para siempre**.
> El KPI "el timeout sale de datos" habría quedado permanentemente falso mientras los 5 tests —todos con doble— daban
> verde. Es el mismo patrón que el "runner sin loop por caso" del plan 262: feature muerta, suite en verde.
> Por eso F7.2 tiene **dos mitades y las dos son obligatorias**.

**F7.2.a — Escribir el historial (sin esto, F7.2.b no puede funcionar nunca).**

> **Re-anclada en v3 (hallazgo V4): el punto que indicaba el v2 no existe.** El v2 decía *"al terminar
> `_run_all_specs_once` (`:301`), después de calcular `duration_ms`"*. Verificado:
> ```bash
> awk 'NR>=301 && NR<461 && /duration_ms/{print NR": "$0}' uat_test_runner.py   # 0 lineas
> grep -n "duration_ms   = int" uat_test_runner.py                              # 239
> ```
> `_run_all_specs_once` abarca **:301-460** y **no calcula `duration_ms` en ningún lado**. La duración de la corrida se
> calcula en **`run()`, línea `:239`** (`duration_ms = int((time.time() - started) * 1000)`), y se consume en `:258`
> y `:282`. El fix que el v2 agregó para matar la inercia estaba anclado al vacío.

**Dónde exactamente:** en `run()` (`uat_test_runner.py:80`), **después de `:239`** y antes del
`_classify_and_emit_runner_summary(...)` de `:252`, que ya recibe `duration_ms=duration_ms` (`:258`).

**Firma completa, verificada (`playbook_performance.py:113-118`):**
```python
record_run(playbook_id: str, verdict: str, duration_ms: int,
           slowest_step: str = "", fail_reason: str = "") -> dict
```
`verdict` es **posicional y obligatorio** — el v2 no lo nombraba, así que su snippet era un `TypeError`. Regla literal
para el valor: `verdict = "PASS" if fail_count == 0 and blocked_count == 0 else "FAIL"`, usando `fail_count` y
`blocked_count` que ya existen en ese scope (`:254-256`). Llamada:
```python
# plan-274 F7.2.a — historial de duracion; sin esto recommend_timeout_ms devuelve default_ms para siempre.
try:
    import playbook_performance
    playbook_performance.record_run(
        "uat_runner_all_specs",
        "PASS" if (fail_count == 0 and blocked_count == 0) else "FAIL",
        duration_ms,
    )
except Exception:                       # registrar historial NUNCA tumba una corrida
    logger.debug("plan-274 F7.2.a: record_run fallo; se ignora", exc_info=True)
```
Es escritura en un JSON local del propio tool (`playbook_performance.py:64` `_perf_file`) — **no toca ningún sistema
del operador**, así que no cae en la categoría (B) y no necesita flag.

**F7.2.b — Leer la recomendación.** Consultar `playbook_performance.recommend_timeout_ms(playbook_id, default_ms=90_000)`
(p95×1,5, acotado a `[60 000, 600 000]`, `:59-60` y `:170`, verificados).
- **`default_ms=90_000` es explícito y obligatorio.** El default del módulo es `120_000` (`:160`): si no se pasa, sin
  historial el timeout **sube solo** de 90 s a 120 s sin que nadie lo haya decidido.
- **`playbook_id`: cuál.** `_run_all_specs_once` lanza **una** invocación `npx` para **N** specs, así que no hay "el"
  playbook. Regla literal: `playbook_id = "uat_runner_all_specs"` — un id **único y estable** para la invocación
  agregada, el mismo que se pasa en F7.2.a. **Prohibido** derivarlo de un spec: mezclaría p95 de escenarios distintos.
- **Nunca** por debajo de 60 000 (el módulo lo garantiza con su piso, `:170`), para no reintroducir el fallo que
  motivó subir de 30 s a 90 s (comentario en `uat_test_runner.py:48`, verificado).
**F7.3 — La puerta al paralelismo, declarada y NO abierta.** Escribir en `uat_test_runner.py`, en el docstring de
`_has_per_worker_session()` (creada en F3), la lista exacta de lo que haría falta: (a) un `storageState` por worker
(`.auth/agenda.w{index}.json`), (b) un usuario de AgendaWeb por worker o una sesión de servidor por worker, (c) verificar
que la BD de test tolera N escrituras concurrentes. **Esta fase NO lo implementa** y `_has_per_worker_session()` sigue
devolviendo `False`. Es alcance de un plan futuro, no una fase encubierta.

**Tests PRIMERO.** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_consolidation.py`:
- `test_deadline_en_ocho_etapas` — **8 llamadas** a `_check_deadline` (+1 definición = 9 líneas). El test cuenta
  **llamadas** con `\b_check_deadline\(` excluyendo la línea de `def `.
  > **Cuidado con el conteo:** `_check_deadline(` como subcadena también matchea dentro de la definición. Usar
  > el patrón con `\b` y excluir explícitamente las líneas que empiezan con `def `.
- `test_todas_las_llamadas_estan_en_scope` **(nuevo en v3, hallazgo V1 — es el test que mata la bloqueante)** —
  implementa `C-8` con `ast`: localiza el `FunctionDef` `_run_pipeline_stages`, junta los `lineno` de las llamadas a
  `_check_deadline` dentro de él y en todo el módulo, y asserta `todas == en_scope` con las líneas fuera de scope
  **nombradas en el mensaje de fallo**.
  > **Probado contra el defecto exacto del v2** (llamada en `stages["dossier"]`, `:857`): `compileall` VERDE,
  > `grep -c` **sube a 4**, este test ROJO con `FUERA_DE_SCOPE=[857]`. Es la diferencia entre un gate y un adorno.
- `test_ninguna_clave_prohibida` **(nuevo en v3)** — ninguna de las 7 claves fuera de scope (`dossier`, `epic_rollup`,
  `evidence`, `functional_verdict`, `intent_parser`, `publisher`, `synthetic_ticket_builder`) aparece a menos de 3
  líneas de un `_check_deadline(`.
- `test_timeout_sale_de_recomendacion` — doble de `recommend_timeout_ms` devolviendo `150_000` → el comando armado
  contiene `--timeout=150000`.
- `test_sin_historial_cae_a_90000` — **SIN doble**, con el store real vacío (`tmp_path` como `_PERF_DIR`) →
  `--timeout=90000`. Prueba que se pasó `default_ms=90_000`: **con el módulo tal cual y sin ese kwarg da `120000`**
  y el test queda ROJO. Corre contra el defecto del v1.
- `test_nunca_baja_de_60000` — el doble devuelve `10_000` → el comando usa **≥ 60000**.
- `test_se_escribe_el_historial` — tras `_run_all_specs_once` (con `subprocess.Popen` doblado), el store de
  `playbook_performance` contiene una entrada para `uat_runner_all_specs` con `duration_ms > 0`.
  **Este es el test que mata la inercia**: sin F7.2.a el store queda vacío y da ROJO.
- `test_el_historial_alimenta_la_recomendacion` — escribir N corridas con `record_run`, y verificar que
  `recommend_timeout_ms("uat_runner_all_specs", default_ms=90_000)` devuelve un valor **distinto de 90 000**.
  Cierra el lazo escritura→lectura de punta a punta, sin dobles.
- `test_record_run_no_tumba_la_corrida` — `record_run` lanza → `_run_all_specs_once` termina igual y devuelve su
  resultado normal.
- `test_paralelismo_sigue_cerrado` — `_has_per_worker_session() is False` **y** su docstring contiene las 3 condiciones
  (a)(b)(c). Centinela de que F7.3 no se "implementó" a medias.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_consolidation.py -v
grep -c "_check_deadline(" qa_uat_pipeline.py    # == 9   (8 llamadas + 1 definicion)
# y el que de verdad discrimina:
# C-8 -> llamadas_totales=8  en_scope=8  FUERA_DE_SCOPE=[]
```
**Criterio BINARIO.** **`10 passed, 0 failed`** *(el v2 pedía 9 con 8 tests definidos — hallazgo V7; ahora son 10
nombrados)* Y el `grep` da **9**, Y **`C-8` devuelve `llamadas_totales == en_scope == 8` con `FUERA_DE_SCOPE == []`**,
Y las 6 claves nuevas salen de la columna **EN SCOPE (12)** de H6-bis,
Y censo: `direct` 6 → **5**, `alcanzable` 7 → **6** (`playbook_performance` conectado **en las dos direcciones**:
`record_run` escribe y `recommend_timeout_ms` lee).
**Flag:** `STACKY_QA_UAT_STAGE_DEADLINE_ENABLED` (**ON**) para F7.1; F7.2 no lleva flag (es un default calculado con
fallback al valor de hoy). **Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F8 — Cierre: veredicto escrito sobre los 6 huérfanos restantes + anti-regresión

**Objetivo.** Que no quede un solo módulo del corpus sin decisión escrita, y que el trabajo de F1..F7 no se deshaga.

**F8.1 — Veredicto por módulo.** Los que quedan huérfanos tras F2/F4/F5/F6/F7 son **6** *(el v1 titulaba "los 5 que
quedan", listaba 6, y se autocorregía en una nota — un modelo menor que lee el título escribe 5 veredictos y falla el
criterio; ya está corregido en el título, en la lista y en el KPI)*:
`navigation_driver.py` (975), `playwright/helpers/navigation_executor.ts` (793),
`playwright/instrumented_actions.ts` (601), `playwright/helpers/arrival_validator.ts` (372),
`playwright/helpers/grid_precheck.ts` (172), `playwright/helpers/session_guard.ts` (167).
> **La cuenta, y los DOS números que el v2 confundió (hallazgo V3).** 11 del corpus − 5 conectados
> (`screenshot_budget` F2, `deeplink_readiness_checker` F4, `locator_quality` F5, `test_data_cache` F6,
> `playbook_performance` F7.2) = **6 MÓDULOS que siguen huérfanos**. Ese 6 es correcto y es el que gobierna esta fase.
> **Pero el valor de la métrica `direct` al cierre es 5, no 6**, porque `arrival_validator.ts` **nunca estuvo** en esa
> cuenta: ya tenía 1 importador directo (`navigation_executor.ts:26`). Son dos cosas distintas:
>
> | | arranque | cierre |
> |---|---|---|
> | **módulos huérfanos** (los que F8.1 dictamina) | 11 | **6** |
> | métrica `direct == 0` (lo que mide `C-4`) | 10 | **5** |
> | métrica `prod_reachable == False` | 11 | **6** |
>
> El v2 escribió **6 y 7** como valores de cierre de las métricas: una unidad de más en cada una, porque su cadena de
> fases se saltaba el decremento de F5. Congelar el ratchet ahí le regalaba **una unidad de holgura**.
> **§9 lleva una línea por cada uno de los 11**, no por cada uno de los 6: los 5 conectados también llevan veredicto
> (`CONECTADO EN F<n> — <archivo:línea del importador>`).

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
- `test_no_vuelven_las_esperas_fijas` — `total_ms` de los 5 specs ≤ `pre_plan.total_ms` de
  **`reports/plan274_wait_baseline.json`** (el artefacto de F0.1). **Criterio delta.**
  > *El v1 leía este número de `reports/plan274_selector_baseline.json`, que es el artefacto de **F5** y contiene
  > scores de selectores, no milisegundos. Artefacto equivocado: el ratchet habría fallado con `KeyError` o —peor—
  > comparado contra un número sin sentido.*
- `test_el_generador_no_recupera_capturas_incondicionales` — el conjunto de `page.screenshot(` sin guardia en el `.j2`
  sigue siendo **exactamente** `{325, 496, 798, 806}` (mismo criterio de conjunto que F2, no un umbral).
- `test_el_censo_no_crece` — ni `direct` ni `prod_reachable` suben respecto de los valores de cierre **5** y **6**
  *(el v2 congelaba 6 y 7: una unidad de holgura en cada métrica — hallazgo V3)*, sobre el corpus **CERRADO de 11**.
  El corpus **no se amplía**: un módulo nuevo huérfano no rompe este test (sería alcance infinito). Se declara así
  explícitamente.
  > **Corre contra el defecto:** desconectar cualquiera de los 5 módulos que conectan F2/F4/F5/F6/F7 sube `direct` a 6
  > y el test da ROJO. Con los valores del v2 (6 y 7), esa misma desconexión daba **VERDE**.
- `test_workers_no_se_rehardcodea` — `uat_test_runner.py` no contiene `"--workers=1"` literal.
- `test_el_reloj_de_pared_no_empeora` — **vive en `test_plan274_wallclock.py` (F9), NO acá.** *(Aclarado en v3 —
  hallazgo V14: el v2 lo listaba en los dos archivos y ninguno lo reclamaba.)* Este archivo sólo lo **importa** para
  que el ratchet corra completo con un solo comando; si `pytest` lo colecta dos veces, se elimina de este listado.

**F8.3 — Decisión sobre H8 (el tool fuera del ratchet).** Registrar los **11** archivos de test nuevos de este plan
*(el v1 decía 7 y listaba 10, omitiendo además el del backend)*: **10 en el tool** + **1 en el backend**
(`test_plan274_baseline.py`, `test_plan274_orphan_census.py`, `test_plan274_no_fixed_waits.py`,
`test_plan274_screenshot_budget_wired.py`, `test_plan274_workers_honest.py`, `test_plan274_deeplink_probe.py`,
`test_plan274_data_cache_wired.py`, `test_plan274_selector_fragility.py`, `test_plan274_consolidation.py`,
`test_plan274_ratchet.py`, `test_plan274_wallclock.py` — **11 en el tool con F9**, más
`backend/tests/test_plan274_tool_tests_outside_ratchet.py` y `backend/tests/test_plan274_efficacy_gates.py` de F10
= **13 en total**).

> **DECISIÓN TOMADA EN v3, no una bifurcación (hallazgo V11): la deuda H8 se declara ACEPTADA.**
> El v2 presentaba "registrar los 11 del tool en los DOS ratchets" como camino principal y el "si no se puede" como
> escape. Verificado: **no se puede**, por tres razones independientes, y el implementador no debe perder una tarde
> descubriéndolo:
> 1. El `.sh` hace `cd backend` y lista rutas **peladas, sin comillas**, en un array bash. La ruta del tool tiene
>    **dos espacios** (`Stacky tools`, `QA UAT Agent`) ⇒ word-splitting: `pytest` recibiría `../../Stacky` y reventaría.
> 2. Los dos meta-tests sólo reconocen rutas bajo `tests/`:
>    `_SH_RE = ^\s*(tests/[\w/]+\.py)\s*$` y `_PS1_RE = ^\s*"(tests/[\w/]+\.py)"\s*,?\s*$`
>    (`backend/tests/test_plan259_ratchet_script_parity.py:28-30`). `[\w/]` no admite espacios ni `.` ⇒ una entrada
>    del tool quedaría **muda**: registrada y **no vigilada por ningún gate**. Es un falso verde de manual.
> 3. `test_plan259_ratchet_script_parity.py` compara los dos scripts **como conjuntos**; los dos ya divergen en 64
>    entradas (718 vs 654), así que cualquier registro asimétrico agrava un rojo ajeno.
>
> ⇒ **F8.3 = documentar la deuda en §9 y NO invertir el test de F0.3.** Los 11 archivos del tool se corren con los
> comandos explícitos de §4 y de cada fase. Resolver H8 de verdad (un runner que acepte rutas con espacios, o mover
> los tests del tool bajo `backend/tests/`) es **alcance de un plan futuro**, no de éste.

**Lo único obligatorio en F8.3.** Registrar los **2 archivos de backend** (`test_plan274_tool_tests_outside_ratchet.py`
de F0.3 y `test_plan274_efficacy_gates.py` de F10) en **los DOS** scripts
(`Stacky Agents/backend/scripts/run_harness_tests.sh` y `run_harness_tests.ps1`), con la sintaxis de cada uno:
```
run_harness_tests.sh    ->    tests/test_plan274_tool_tests_outside_ratchet.py        (pelada, sin coma)
run_harness_tests.ps1   ->    "tests/test_plan274_tool_tests_outside_ratchet.py",     (ENTRECOMILLADA, con coma)
```
> **Advertencia sobre la sintaxis:** `.sh` y `.ps1` **no** tienen la misma sintaxis. En PowerShell una ruta sin comillas
> se lee como **nombre de comando** y el array parsea con 0 errores dejando la ruta **muda** — no hay error que avise.
> Editar los dos y **correr** los dos meta-tests (`test_harness_ratchet_meta.py` y
> `test_plan259_ratchet_script_parity.py`), no solo mirarlos.
> **TERCER punto de registro (el v2 no lo nombraba):** `backend/tests/harness_ratchet_allowlist.txt` (204 líneas).
> `test_harness_ratchet_meta.py` exige que **todo** `backend/tests/test_*.py` esté en `HARNESS_TEST_FILES` **o** en esa
> allowlist con motivo. Como acá se registran en el ratchet, **no** deben agregarse a la allowlist
> (`test_allowlist_no_se_solapa_con_ratchet` prohíbe estar en las dos).

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_ratchet.py -v
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
"$PY" -m pytest tests/test_plan274_tool_tests_outside_ratchet.py -v
```
**Criterio BINARIO.** `4 passed, 0 failed` en el ratchet *(4, no 5: `test_el_reloj_de_pared_no_empeora` pertenece a F9
— hallazgo V14)*, Y §9 de este documento tiene **una línea de veredicto por cada uno de los 11** módulos del corpus
(6 con `MANTENER`/`BORRAR`, 5 con `CONECTADO EN F<n>` + `archivo:línea`),
Y los 2 archivos de backend aparecen en **los dos** scripts, Y `test_harness_ratchet_meta.py` y
`test_plan259_ratchet_script_parity.py` **corridos** (no mirados) siguen verdes,
Y la deuda H8 del tool está escrita en §9 como **aceptada, con los 3 motivos de V11**.
**Flag:** ninguna. **Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F9 — Ratchet de reloj de pared `[ADICIÓN ARQUITECTO v2, corregida en v3]`

**Por qué existe.** Todo el plan optimiza un **proxy**: KPI-1 cuenta los milisegundos **escritos en un archivo**, no el
tiempo que tarda la corrida. Los dos son separables, y el propio plan lo demuestra: F1 reemplaza `waitForTimeout(800)`
por una espera por estado que en el peor caso espera **más** (C10). Con solo los KPI del v1, **una corrida más lenta
cierra las 9 fases en verde**. El único gate real que quedaba era un **smoke manual de 3 corridas** en el DoD — humano,
no repetible y fuera de cualquier ratchet.

Y no hay que construir nada para medirlo: `reports/playwright-results.json` **ya publica** `stats.duration` (el reloj
de pared de la corrida completa) y una `duration` por test. Es el mismo reporter `json` que ya está configurado en
`playwright.config.ts:17`. Costo: leer un archivo que ya se escribe.

> **DOS correcciones al F9 del v2, y las dos lo anulaban por completo.**
>
> **(a) El baseline se toma en F0, NO al final (hallazgo V5).** §8 del v2 ordenaba *"F9 conviene correrla al final…
> si se corre antes, congela como baseline el reloj **previo** a la mejora y el ratchet queda flojo"* mientras §9 decía
> *"KPI-7 … **(medir antes de F1)**"*. Instrucciones opuestas — y el razonamiento de §8 está **invertido**: F9 existe
> para detectar que una espera por estado sea **más lenta** que el sleep que reemplazó (C10), y eso **sólo** se ve con
> baseline **pre-F1**. Corriéndola al final, `test_baseline_de_reloj_existe_o_se_crea` congela el reloj **ya cambiado**
> y el ratchet no puede detectar nada: la [ADICIÓN ARQUITECTO] del v2 se auto-anulaba. **En v3: el paso 2 (capturar el
> baseline) es F0.5; el ratchet (paso 3) corre al final.**
>
> **(b) `C-7` no medía reloj de pared (hallazgo V8).** Corrido de verdad contra el reporte real del repo:
> `walk(suites) = 47 176 ms` vs **`stats.duration = 70 030,106 ms`**. El recorrido de `suites` sólo ve **3 dicts con
> `duration`** (uno por resultado de test) e **ignora `globalSetup` — que es el login contra AgendaWeb — y todo el
> overhead**: subestima **22 854 ms, un 33 %**. Justamente la parte que puede degradarse sin que nadie la vea.
> **En v3 el reloj de pared es `stats.duration`**, y `suites[*]` queda sólo para **atribuir** el crecimiento por test.

**Archivos a crear:** `Stacky tools/QA UAT Agent/tests/unit/test_plan274_wallclock.py`,
`Stacky tools/QA UAT Agent/reports/plan274_wallclock_baseline.json` (lo genera el test **en F0.5**).
**Archivos a editar:** ninguno de producción. **Flag:** ninguna (es un test).

**Cómo.**
1. `_wall_clock(report_path) -> tuple[int, int, dict]` devuelve `(stats["duration"], n_tests, {test_id: duration})`,
   donde `n_tests = stats["expected"] + stats["unexpected"] + stats["flaky"]` y el dict sale de recorrer `suites[*]`.
   **Mismo cálculo que `C-7`.**
2. `test_baseline_de_reloj_existe_o_se_crea` — si `plan274_wallclock_baseline.json` no existe, lo escribe con la
   medición actual y pasa. **Se corre en F0.5, ANTES de F1** (ver §8). Una vez escrito, ninguna fase lo reescribe.
3. `test_el_reloj_no_empeora` — **criterio DELTA con tolerancia declarada**: `ms_por_test_actual <= baseline * 1.10`,
   con `ms_por_test = stats.duration / n_tests`. El 10 % absorbe el ruido de una máquina compartida; más que eso es
   una regresión real. El mensaje de fallo nombra los tests cuya `duration` creció y en cuánto (para eso está el dict).
   > Se compara **ms por test**, no el total: si mañana hay 6 specs en vez de 5, un total mayor no es una regresión.
4. `test_se_salta_si_no_hay_reporte` — si `reports/playwright-results.json` no existe o está vencido, el test hace
   `pytest.skip` con motivo. **Nunca falla por ausencia de reporte**: es un ratchet, no un requisito de corrida.
5. `test_no_se_mide_sobre_suites` **(nuevo en v3, hallazgo V8)** — asserta que `_wall_clock` devuelve `stats["duration"]`
   y **no** la suma de `suites[*]`, alimentándolo con un reporte-fixture donde los dos números difieren.
   **Corre contra el defecto:** con la implementación de `C-7` del v2, ROJO.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky tools/QA UAT Agent"
"$PY" -m pytest tests/unit/test_plan274_wallclock.py -v
```
**Criterio BINARIO.** `4 passed, 0 failed` (o `3 passed, 1 skipped` si no hay reporte, con el motivo impreso), Y
`reports/plan274_wallclock_baseline.json` existe **desde F0.5** y su `startTime` es **anterior** al primer commit de F1
(verificable: el campo `stats.startTime` del reporte que lo originó, `2026-07-26T00:36:03.100Z` en el reporte de hoy).
**Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3.

---

### F10 — El gate de EFICACIA `[ADICIÓN ARQUITECTO v3]`

**Por qué existe.** Las tres bloqueantes de la crítica v2→v3 (V1 alcance, V2 presupuesto inerte, V6 flags muertas)
tienen la misma firma: **el criterio verificaba que el código estuviera escrito, no que hiciera algo**. En los tres
casos el gate del v2 daba VERDE con el defecto puesto, y en el caso de V1 el gate **subía de puntaje** con el bug
adentro (`grep -c` pasaba de 3 a 4, acercándose al objetivo de 9). Un plan que ya lleva dos rechazos por esta misma
clase necesita un gate **de la clase**, no otro parche puntual.

F10 no agrega comportamiento de producto: agrega **dos tests deterministas, sin dependencias nuevas**, que un modelo
menor no puede satisfacer escribiendo código muerto.

**Archivos a crear:** `Stacky Agents/backend/tests/test_plan274_efficacy_gates.py`.
**Archivos a editar:** ninguno de producción. **Flag:** ninguna (es un test).

**F10.1 — Gate de ALCANCE (mata la clase de V1).** `test_toda_llamada_a_closure_esta_en_su_scope`: implementa `C-8`
de forma **genérica**, no atada a `_check_deadline` — recorre `qa_uat_pipeline.py` con `ast`, encuentra **toda función
anidada** (un `FunctionDef` cuyo padre es otro `FunctionDef`), y asserta que **ninguna** llamada por nombre a esa
función ocurre fuera del cuerpo del padre. Mensaje de fallo: `<nombre> definida en :<def> y llamada en :<linea>, fuera
de <padre>`. Cuesta ~25 líneas y **detecta el `NameError` que `compileall` no ve**, para cualquier closure del archivo.

**F10.2 — Gate de FLAG VIVA (mata la clase de V6).** `test_toda_flag_del_plan_es_leida`: para cada una de las 6 keys
de §3.1, asserta que aparece **al menos una vez** en código que la lee (`.py` o `.j2` del tool), no sólo en los 5
archivos de registro del arnés. Es la **pata 7** convertida en test. Mensaje de fallo: la key y los archivos donde
está registrada, para que quede claro que el problema es que **nadie la usa**.

**Tests PRIMERO.** Los dos tests se escriben **antes** de F7 y F1/F2 respectivamente, y **arrancan ROJOS**:
- F10.1 arranca **VERDE** con el código de hoy (`FUERA_DE_SCOPE=[]`) — es un centinela, y su valor se prueba con el
  caso adverso: el test trae un fixture con el defecto exacto del v2 (`_check_deadline` en `stages["dossier"]`, `:857`)
  y asserta que el detector lo marca. Sin ese caso adverso, F10.1 no está hecha.
- F10.2 arranca **ROJO** (las 6 keys no existen todavía) y se pone verde a medida que F1..F7 las cablean.

**Comando:**
```bash
cd "N:/GIT/RS/STACKY/Stacky/Stacky Agents/backend"
"$PY" -m pytest tests/test_plan274_efficacy_gates.py -v
```
**Criterio BINARIO.** `3 passed, 0 failed` (F10.1 + su caso adverso + F10.2), Y el archivo está registrado en **los DOS**
ratchets (F8.3). **Trabajo del operador:** ninguno. **Runtimes:** neutro en los 3 — es `ast` de la stdlib y `grep`.

> **Relación con el smoke manual del DoD:** F9 **no lo reemplaza**. El smoke prueba que la app sigue funcionando
> (3/3 verdes); F9 prueba que no se degradó el tiempo, y lo hace **cada vez que alguien corre los tests**, no solo
> cuando un humano se acuerda.

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
| **R-8** | Sesión paralela: hay **9 worktrees vivos** y el `wt-plan-262` tiene F0..F11 del 262 sin mergear, tocando `uat_test_runner.py` (el mismo archivo que F3 y F7.2). | **Alta** | **Frontera de merge declarada:** el 262 cablea su recuperación en `uat_test_runner.py:256`; F3 toca `:355` y F7.2 toca `:48/:84/:354` **y ahora también `:239-252`** (F7.2.a re-anclada en v3, hallazgo V4) — **esa zona SÍ colinda con `:256` del 262**, así que la frontera dejó de ser holgada. Tras cualquier merge con `feat/plan-262-*`: `python -m compileall uat_test_runner.py`, `grep -c "_resolve_workers" uat_test_runner.py` (exactamente 2: definición + uso) **y** `grep -c "record_run" uat_test_runner.py` (exactamente 1). *(El v2 escribía `:352`, que es la línea `"npx", "playwright", "test",` — el propio v2 lo había corregido a `:354` en H7 y F7.2 y no propagó el fix acá.)* |
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
    **Y NO se promueve `_check_deadline` a función de módulo**: sacarla del closure de `_run_pipeline_stages` obligaría
    a pasarle `_deadline`, `_max_minutes`, `_effective_config`, `ticket_id`, `stages` y `started` por parámetro, en 8
    call sites, sobre el archivo más grande del tool. Es un refactor con riesgo propio y **es la razón por la que las
    6 claves de F7.1 se eligen dentro del scope existente** (H6-bis). Alcance de un plan futuro.
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

1. **F0** — baseline (esperas, censo **y reloj de pared F0.5**). **No empezar nada sin esto**: sin baseline no hay
   forma de probar la mejora, y el de reloj **sólo sirve si se toma antes de F1**.
2. **F10** — gates de eficacia `[ADICIÓN ARQUITECTO v3]`. Van **antes** de las fases que vigilan, si no son un
   post-hoc. F10.1 arranca verde (centinela), F10.2 arranca rojo y se cierra con F1..F7.
3. **F1** — esperas fijas (el generador **antes** que los specs, para no re-contagiar).
4. **F2** — presupuesto de capturas.
5. **F3** — honestidad de workers.
6. **F4** — probe de deeplink.
7. **F5** — fragilidad de selectores.
8. **F6** — cache de datos.
9. **F7** — deadline **en scope** + timeout recomendado (**las dos mitades**) + puerta declarada.
10. **F8** — veredicto del censo + ratchet + registro de los 2 tests de backend.
11. **F9** — ratchet de reloj de pared (el **paso 3**; el paso 2 ya se corrió en F0.5).

F4, F5 y F6 son **independientes entre sí** (archivos disjuntos: `navigation_strategy_resolver.py`,
`qa_uat_pipeline.py`, `data_resolver.py`) y pueden hacerse en cualquier orden entre ellas. F1 y F2 **no** son
independientes: las dos editan `templates/playwright_test.spec.ts.j2` **y las dos tocan los mismos dos
`template.render(...)` de `playwright_test_generator.py` (`:384`, `:932`)** ⇒ **secuenciales, F1 primero**.
**F5 y F7.1 también comparten archivo** (`qa_uat_pipeline.py`, zonas distintas: `:2062` vs las 6 etapas — y
`selector_contract` es una de las 6, así que la zona **se toca dos veces**) ⇒ si se hacen en paralelo, correr
`python -m compileall qa_uat_pipeline.py` **y `C-8`** después de juntarlas.

> **Corrección de orden respecto del v2 (hallazgo V5).** El v2 decía *"F9 conviene correrla al final… si se corre
> antes, congela como baseline el reloj previo a la mejora y el ratchet queda flojo"*, contradiciendo a §9
> (*"medir antes de F1"*). **El razonamiento estaba invertido**: el baseline **tiene** que ser el reloj previo — es
> exactamente lo que hace falta para detectar que F1 empeoró la corrida. Lo que va al final es el **ratchet**
> (paso 3), no la **captura** (paso 2). En v3 la captura es **F0.5**.

### Definición de Hecho (DoD) global

- [ ] Los **9** KPI de §1 (KPI-1, 2, 3, 4a, 4a-bis, 4b, 5, 6, 7, 8) medidos **con los comandos de §4** y anotados en §9.
- [ ] Los **13** archivos de test nuevos existen (11 en el tool + 2 en el backend) y cada comando de §5 reporta su
      número de `passed` con `0 failed`. **Ningún criterio se cierra mirando solo `$?`.**
- [ ] Las 6 flags nuevas pasan el **gate de las 7 patas** de §3.1 — los 5 `grep` de registro (`harness_flags.py`,
      `config.py`, `tests/test_harness_flags.py`, **`_CATEGORY_KEYS`**, `services/harness_flags_help.py`) **más la
      pata 7** (`grep` en el código que la lee, dentro del tool) dan `>= 1` — y aparecen en `GET /api/harness/flags`.
- [ ] **Ninguna flag quedó muda:** las 6 tienen `pata 7 >= 1`. Una flag registrada y no leída es peor que no tenerla.
- [ ] Ninguna flag nació OFF (y si alguna lo hizo, cita por escrito la categoría (A) o (B)).
- [ ] **`C-8` devuelve `FUERA_DE_SCOPE == []`** con 8 llamadas en scope. Un `grep -c` de 9 **no** cierra F7.1.
- [ ] **`C-9` devuelve `sin_guardia == [325, 496, 798, 806]` y `con_guardia == 15`**, y el test del techo de 25 pasa.
- [ ] **Ningún assert se editó para poner verde un criterio.** Los baselines viven en
      `reports/plan274_wait_baseline.json`, `reports/plan274_selector_baseline.json` y
      `reports/plan274_wallclock_baseline.json`, y los criterios son **delta** contra esos archivos.
- [ ] `§9. Veredicto del censo` tiene una línea por cada módulo del corpus de 11.
- [ ] `python -m compileall` limpio sobre los `.py` tocados; `npx tsc --noEmit` no introduce errores nuevos en los
      `.ts` tocados (comparar contra el conteo previo — hay deuda preexistente, criterio **delta**).
- [ ] **Smoke manual con AgendaWeb arriba** (el gate que prueba que quitar los sleeps no rompió **funcionalidad**):
      correr `ado122_provincia_domicilio.spec.ts` y `ado171_emails_oficial.spec.ts` **3 veces** y verificar 3/3 verdes.
      **Sin este smoke, F1 no está hecha** — los tests unitarios miden el archivo, no el navegador.
- [ ] **Reloj de pared verificado por F9** (KPI-7), no a ojo: `C-7` sobre el `reports/playwright-results.json` de esa
      corrida, comparado contra `plan274_wallclock_baseline.json` **capturado en F0.5, antes de F1**. Es lo único que
      detecta que una espera por estado resulte **más lenta** que el sleep que reemplazó — con KPI-1 en verde.
      Si el baseline se capturó **después** de F1, el ratchet **no vale** y hay que declarar KPI-7 `NO MEDIBLE`.
- [ ] **La huella del error se registró.** Agregar a `Stacky Agents/docs/sistema/error_fingerprints.json` (existe,
      53 KB) la clase de fallo que este plan mata: *deep link que redirige a login y quema la corrida entera* (F4).
      Sin huella, el próximo diagnóstico vuelve a empezar de cero.
- [ ] Backward-compatible: ningún contrato de `api/qa_uat.py` cambió; los 5 specs siguen corriendo.
- [ ] Cero código de frontend tocado. Cero `push`. Cero DML.

---

## §9. Veredicto del censo (a completar en F8.1)

> Esta sección se llena durante la implementación. Debe tener **una línea por cada uno de los 11 módulos** del corpus
> de H1, con `MANTENER COMO DEUDA DECLARADA — <razón>`, `BORRAR — reemplazado por <archivo:línea>` o
> `CONECTADO EN F<n> — <archivo:línea del importador>`, más el valor final de los **10** KPI (§1). Si queda vacía,
> **F8 no está hecha**. Acá también va, por escrito: la **deuda H8 aceptada** con los 3 motivos de V11, y —si
> corresponde— la declaración de `KPI-7 NO MEDIBLE` con su causa.

**Estado: COMPLETADA en la implementación del 2026-07-30.** Los 11 módulos del corpus tienen veredicto escrito.

| Módulo | Veredicto | Evidencia (`archivo:línea` del importador o razón) |
|---|---|---|
| `navigation_driver.py` | **MANTENER COMO DEUDA DECLARADA** | Duplica `webforms_nav.ts` (el único helper vivo). El backoff `[1,2,4,8]` está reimplementado en los dos lenguajes (`navigation_driver.py:105` y `playwright/helpers/webforms_nav.ts:76`). Borrar 975 líneas es un cambio de riesgo propio, no una fase de este plan. Plan futuro sin número. |
| `playwright/helpers/navigation_executor.ts` | **MANTENER COMO DEUDA DECLARADA** | Misma duplicación que el anterior (793 líneas). Además es el único importador de `arrival_validator.ts`, así que borrarlo deja a ese otro en 0. Plan futuro sin número. |
| `playwright/instrumented_actions.ts` | **MANTENER COMO DEUDA DECLARADA** | Telemetría por acción; candidato a conectarse en el plan que abra el paralelismo (F7.3), donde la atribución por worker sí hace falta. |
| `deeplink_readiness_checker.py` | **CONECTADO EN F4** | `navigation_strategy_resolver.py:394-424` (import perezoso dentro de la rama deeplink). `prod_reachable == True`: el resolver lo importa `qa_uat_pipeline.py`. |
| `playwright/helpers/arrival_validator.ts` | **MANTENER COMO DEUDA DECLARADA** | Sigue con 1 importador textual (`navigation_executor.ts:26`) que **también** es huérfano ⇒ alcance de producción 0. Se conecta cuando se conecte su importador. |
| `locator_quality.py` | **CONECTADO EN F5** | `qa_uat_pipeline.py` → `_score_locator_quality()`, invocado dentro de la etapa `selector_contract`. Observabilidad pura: no cambia ninguna decisión de navegación. |
| `playbook_performance.py` | **CONECTADO EN F7.2, EN LAS DOS DIRECCIONES** | Escritura: `uat_test_runner.py` → `_record_run_history()` desde `run()`, tras calcular `duration_ms`. Lectura: `_resolve_timeout_ms()`. Sin la mitad de escritura, `recommend_timeout_ms` devolvía `default_ms` para siempre. |
| `test_data_cache.py` | **CONECTADO EN F6** | `data_resolver.py`, cache-aside **por campo** alrededor de `_run_sqlcmd` dentro de `resolve_fields`. |
| `screenshot_budget.py` | **CONECTADO EN F2** | `playwright_test_generator.py` → `_screenshot_budget_block()`, inyectado en los **dos** `template.render(...)`. |
| `playwright/helpers/grid_precheck.ts` | **MANTENER COMO DEUDA DECLARADA** | Pre-chequeo de grilla; candidato del plan que abra el paralelismo. No se borra: 172 líneas testeadas. |
| `playwright/helpers/session_guard.ts` | **MANTENER COMO DEUDA DECLARADA** | Guardia de sesión; es justamente lo que hace falta para la sesión por worker de F7.3. Borrarlo sería tirar la pieza que el próximo plan necesita. |

**Prohibido borrar código en esta fase, y no se borró: el entregable es el veredicto.**

**Valores finales de KPI (medidos el 2026-07-30, tras la implementación):**

| KPI | Comando | Antes (medido 2026-07-30) | Meta | **Después (real)** |
|---|---|---|---|---|
| KPI-1 ms de espera fija | `C-1` | 35 900 / 26 occ | ≤ 3 000 | **500 ms / 1 occ** ✅ |
| KPI-2 espera fija en el generador | `C-2` | 1 | 0 o marcada | **1, y es la rama `{% else %}` del rollback por flag** ✅ |
| KPI-3 capturas sin guardia | `C-3` / `C-9` | 18 de 19 | exactamente `{325,496,798,806}` | **4, las mismas por artefacto: ahora `{343, 514, 817, 825}`** (el bloque de presupuesto corrió el `.j2`; se anclan por `path`, no por línea) ✅ |
| KPI-4a `direct == 0` | `C-4` | 10 | **5** | **5** ✅ |
| KPI-4a-bis `prod_reachable == False` | F0.2 | 11 | **6** | **6** ✅ |
| KPI-4b veredictos escritos | §9 | 0 de 11 | 11 de 11 | **11 de 11** ✅ |
| KPI-5 `_check_deadline` **en scope** | `C-5` + **`C-8`** | 3 líneas (2 llamadas, 0 fuera de scope) | 9 líneas (8 llamadas, **0 fuera de scope**) | **`C-5`=9; `C-8`: `llamadas_totales=8 en_scope=8 FUERA_DE_SCOPE=[]`** ✅ |
| KPI-6 workers honesto | `C-6` | falso | verdadero | **verdadero** (0 líneas con el literal; `_resolve_workers()` con guardia de sesión) ✅ |
| KPI-7 reloj de pared | `C-7` | **70 030 ms / 3 tests = 23 343 ms por test** | ≤ baseline × 1,10 | **baseline capturado en F0.5** (`reports/plan274_wallclock_baseline.json`, `startTime=2026-07-26T00:36:03.100Z`, anterior a todo cambio de F1). **El "después" queda NO MEDIBLE hasta el smoke manual** — ver abajo. |
| KPI-8 PNG emitidos | `C-9` | `con_guardia = 0`, sin techo | `con_guardia = 15` + techo de 25 activándose | **`con_guardia = 15`; techo demostrado: 30 pasos ⇒ 25 `True` / 5 `False`** ✅ |

### §9.1. Deuda H8 — ACEPTADA (los 3 motivos de V11)

Los ~90 tests del tool (y los 11 nuevos de este plan) **no entran a los dos ratchets**, y no es una omisión:

1. `run_harness_tests.sh` hace `cd backend` y lista rutas **peladas, sin comillas**, en un array bash. La ruta del tool
   tiene **dos espacios** ⇒ word-splitting: `pytest` recibiría `../../Stacky` y reventaría.
2. Los dos meta-tests solo reconocen rutas bajo `tests/`: `_SH_RE = ^\s*(tests/[\w/]+\.py)\s*$` y
   `_PS1_RE = ^\s*"(tests/[\w/]+\.py)"\s*,?\s*$` (`backend/tests/test_plan259_ratchet_script_parity.py:27,29`).
   `[\w/]` no admite espacios ni `.` ⇒ una entrada del tool quedaría **muda**: registrada y vigilada por ningún gate.
3. `test_plan259_ratchet_script_parity.py` compara los dos scripts **como conjuntos** y ya divergen en 64 entradas
   (718 vs 654): cualquier registro asimétrico agrava un rojo ajeno.

⇒ Lo único obligatorio, y lo que se hizo: registrar los **2 archivos de backend**
(`test_plan274_tool_tests_outside_ratchet.py` y `test_plan274_efficacy_gates.py`) en **los dos** scripts, con la
sintaxis de cada uno, y **no** agregarlos a `harness_ratchet_allowlist.txt` (estar en las dos listas está prohibido).
Los 11 del tool se corren con los comandos explícitos de §4.

### §9.2. KPI-7 — `NO MEDIBLE` en el "después", con su causa

El baseline **sí** quedó capturado antes de F1 (que es lo que el v2 hacía mal). Lo que falta es la corrida "después":
medirla exige **AgendaWeb arriba**, que es el mismo prerequisito del smoke manual del DoD y no está disponible en este
entorno. Queda **pendiente y declarado**, no inventado. Además, el único reporte real del repo corrió **otros** specs
(`P01/P02/P03` del ticket 367), así que cuando se tome la medición "después" hay que anotar si se corrieron **los mismos
specs**: comparar dos corridas de specs distintos no es un ratchet, es ruido.

### §9.3. Hallazgo de implementación — una SEXTA pata de flag que el plan no nombra

`_export_qa_uat_flags()` itera una **tupla explícita**, `_QA_UAT_FLAG_KEYS` (`backend/api/qa_uat.py:82`). Una flag
registrada en los 5 archivos del arnés **y leída por el tool** (pata 7 en verde) pero **ausente de esa tupla** nunca se
exporta al entorno: el tool hace `os.environ.get(KEY, "true")`, jamás ve el valor apagado, y **el interruptor del panel
del operador no hace nada**. Es la clase de V6 por otro mecanismo. Las 6 flags se agregaron ahí y el gate
`test_toda_flag_del_plan_llega_al_tool` (F10) lo vigila con `ast`.

> **Recordatorio de honestidad (v3).** La fila KPI-7 "Antes" es el reloj del **único** reporte real del repo, que
> corrió **otros** specs (P01/P02/P03 del ticket 367). Si el baseline de F0.5 se toma sobre una corrida distinta,
> **anotarlo acá**: comparar dos corridas de specs distintos no es un ratchet, es ruido.

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
