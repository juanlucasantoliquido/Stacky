# Plan 241 — Cero falso verde: aserciones discriminantes, control negativo obligatorio y cierre total de los pendientes del QAUAT E2E

> Estado: **v2 · CRITICADO (v1 → v2)** — VEREDICTO: **APROBADO-CON-CAMBIOS** (2026-07-25). Pipeline: proponer ✓ → **criticar ✓ [este paso]** → implementar (`implementar-plan-stacky`) → supervisar.
> Autor: Claude Opus 5 (1M context) en rol StackyArchitectaUltraEficientCode. Juez v2: el mismo agente en rol adversarial, verificando cada anclaje contra el código real.

**CHANGELOG v1 → v2 (6 hallazgos, todos verificados leyendo el código):**
- **C1 (IMPORTANTE, resuelto):** el oráculo `attribute_equals` **no era emitible**. El tipo `OracleProbe` del template tiene exactamente 5 campos (`oracle_id, target, tipo, expected, selector` — `templates/playwright_test.spec.ts.j2:71-80`) y **no hay campo para el nombre del atributo**. F1 ahora especifica extender el tipo con `atributo?: string | null` y el emisor con `{{ oracle.atributo | tojson }}`.
- **C2 (IMPORTANTE, resuelto):** el `target` de un oráculo **no es un selector CSS**: el template lo resuelve con `ui_map[oracle.target]` (`:78`), o sea que debe ser una **clave del dict `ui_map`** que recibe la plantilla. Un alias inexistente emite `selector: undefined`, el probe captura `actual = null` y el evaluador devuelve `"review"` — un criterio que **se pierde en silencio**. F1 ahora obliga a validar la pertenencia del alias a las claves del ui_map y a devolver `[]` si no pertenece, con test propio.
- **C3 (IMPORTANTE, resuelto):** F6 atacaba `NO_TESTS_FOUND` sin anclarlo. El sitio real es el **guard estructural `if total == 0`** de `uat_test_runner.py:761-766`. Además `playwright_result_classifier.py:25,34` documenta *"total=0 ALWAYS maps to BLOCKED PIP NO_TESTS_FOUND — never PASS"*, regla que es **correcta y no se toca**: el fix va **antes** de ese guard, en el runner, distinguiendo la causa (crash de `globalSetup`) sin permitir jamás que 0 tests sea PASS.
- **C4 (IMPORTANTE, resuelto):** F0 podía volver `MIXED` runs legítimamente `BLOCKED`. Si el evaluador se salta (`stages["evaluator"].skipped` con `reason == "all_scenarios_blocked"`, `qa_uat_pipeline.py:3090`), `_criteria_results` queda vacío y `functional_verdict` devolvería `MIXED/NO_FUNCTIONAL_ASSERTION` tapando un `BLOCKED` honesto. F0 ahora exige: **si el evaluador se saltó, el veredicto del run sigue siendo el del runner**; el gate funcional solo manda cuando el evaluador efectivamente corrió.
- **C5 (MENOR, resuelto):** el DoD declaraba "60 casos"; la suma de las fases da 7+8+8+5+4+11+6+6+5 = **60** ✓ (verificado, se deja anotado para que el supervisor no lo recuente).
- **C6 (IMPORTANTE, resuelto) — [ADICIÓN ARQUITECTO]:** faltaba el destino de `DISCRIMINATION_FAILED`. Un test que no discrimina es un **bug del arnés, no del desarrollo**, y sin separarlo se leería como si el desarrollo estuviera mal. F2 ahora emite esos casos en una sección propia `test_quality_issues` del dossier, que **no** contamina el veredicto del desarrollo (el criterio cae a `not_verifiable` ⇒ `MIXED`) y queda como backlog accionable del arnés.
> Runtimes objetivo: Codex CLI, Claude Code CLI, GitHub Copilot Pro (paridad obligatoria; el núcleo NO usa LLM).
> Origen: **pedido textual del operador** — *"Propone un plan para resolver todo lo pendiente con un nivel de eficacia enorme, debe ser super robusto y asertivo por todas las cosas"*, tras la implementación del Plan 240 y el hallazgo de un falso positivo en la corrida real del ticket 366.

---

## 0. La tesis del plan (leer esto antes que nada)

El Plan 240 dejó el agente **corriendo de verdad** contra AgendaWeb: login veraz, lectura de tickets, navegación, specs generados, Playwright ejecutando con evidencia. Pero la corrida real destapó el problema que este plan viene a matar:

> **Un PASS de hoy certifica "navegué y la pantalla cargó", no "el criterio de aceptación se cumple".**

Dos pruebas duras, ambas verificadas ejecutando el 2026-07-25:

1. **Falso positivo por pantalla equivocada (ADO-366).** El run reportó `PASS 3/3`; la captura del propio run (`evidence/366/P02/step_final_state.png`) muestra la pantalla **"Agenda Personal"**, cuando el criterio es sobre el combo *Tipo de Teléfono* del mantenedor en **Detalle de Cliente**. Lo detectó un humano mirando una imagen, no el arnés.
2. **Aserción que no discrimina (ADO-367).** El criterio CA-01 dice *"El campo Póliza admite hasta 50 caracteres"* (el bug truncaba a 20). El test generado llenó `VM12-P-1816961389-60`, que tiene **exactamente 20 caracteres**: ese test **pasa igual con el bug presente**. La verdad funcional (`c_abfCodObligacion` tiene `maxlength="50"`) se comprobó con una sonda manual, **no con el test del agente**.

De ahí la ley que estructura este plan:

> **LEY DE DISCRIMINACIÓN — Una aserción que no puede fallar no es una aserción.**
> Todo criterio que produce un veredicto PASS debe venir acompañado de una **prueba de discriminación**: la demostración mecánica de que la misma aserción **falla** contra el estado pre-fix. Sin prueba de discriminación, el criterio es `not_verifiable` y el run **no puede ser PASS**.

Esto es *mutation testing* aplicado al oráculo, no al código: no preguntamos "¿el test pasó?" sino "¿este test **sabría** fallar?".

---

## 1. Objetivo y KPI

**Objetivo.** Cerrar el 100% de lo pendiente del Plan 240 y elevar la precisión del E2E de "llegué a la pantalla" a "verifiqué el criterio con una aserción que sabe fallar". Se logra con: (F0) cableado del veredicto funcional como **gate terminal** —imposible un PASS sin aserciones verificadas—; (F1) un **catálogo determinista de aserciones por tipo de criterio**, incluyendo el tipo `attribute_equals` que hoy no existe; (F2) **control negativo obligatorio** por aserción; (F3) **datos de prueba discriminantes** derivados del propio criterio; (F4) el playbook de `FrmDetalleClie` con cliente en sesión, que por sí solo desbloquea 5 incidencias; (F5) `via_menu` para las pantallas no alcanzables por deep-link; (F6) higiene de diagnósticos mentirosos; (F7) validación de épicas por agregación de hijas; (F8) las fases F2/F7/F8 que el 240 dejó sin implementar; (F9) una **suite golden reproducible** que convierte los resultados en un ratchet permanente.

**KPI (todos binarios y verificables por comando).**
- **KPI-1 — Imposible el PASS vacío:** ningún run puede terminar `PASS` con `verified == 0`. Verificable: `functional_verdict` es el productor del veredicto final del pipeline y su test `test_verdict_sin_criterios_no_es_pass` está en el gate. Hoy: el 366 dio PASS con 0 criterios verificados.
- **KPI-2 — Imposible el PASS en pantalla equivocada:** todo escenario que produce PASS incluye en la evidencia el `screen_verified` (URL + título + ancla) y coincide con el `screen_hint` del criterio. Un mismatch ⇒ `FAIL/NAV_WRONG_SCREEN`. Hoy: no existe el chequeo.
- **KPI-3 — Discriminación probada:** 100% de los criterios con veredicto `verified` traen `discrimination: {"proven": true, "negative_control": ...}`. Los que no la tienen quedan `not_verifiable`. Hoy: 0%.
- **KPI-4 — Aserciones de atributo disponibles:** el tipo `attribute_equals` existe en el evaluador y en el template, y el criterio `kind="maxlength"` del ADO-367 genera `attribute_equals(#c_abfCodObligacion, maxlength, 50)`. Hoy: el evaluador solo soporta `equals|contains_literal|count_eq|count_gt|count_lt|visible` (`uat_assertion_evaluator.py:243-275`).
- **KPI-5 — 5 incidencias desbloqueadas:** 362, 366, 369, 373 y 387 pasan del `BLOCKED` actual a ejecución real. Medible: `stages.runner.total > 0` en los 5.
- **KPI-6 — Cero diagnóstico mentiroso:** `NO_TESTS_FOUND` deja de emitirse cuando la causa real es un crash del `globalSetup`; el `NameError` de `data_readiness_check` desaparece; la deriva de versiones Node↔Python se reporta antes de correr. Hoy: los 3 ocurren.
- **KPI-7 — Reproducibilidad:** la suite golden (F9) corre dos veces seguidas y produce el mismo veredicto por escenario. Medible por comando.

---

## 2. Evidencia de partida (verificada ejecutando, no de memoria)

| # | Hecho | Prueba |
|---|---|---|
| E1 | El evaluador **no** sabe asertar atributos del DOM | `_evaluate_deterministic` soporta `equals`, `contains_literal`, `count_eq`, `count_gt`, `count_lt`, `visible` (`uat_assertion_evaluator.py:243-275`); no hay rama de atributos |
| E2 | El campo real de Póliza es `c_abfCodObligacion` con `maxlength="50"` | Sonda en vivo sobre `FrmBusqueda.aspx`; el alias del ui_map (`input_p_liza`) se resuelve por etiqueta, no por id |
| E3 | El dato del test (`VM12-P-1816961389-60`) mide **20** caracteres | `len()` medido; el bug permitía 20 ⇒ el test no discrimina |
| E4 | El 366 dio PASS navegando a `FrmAgenda.aspx` | `evidence/366/ticket.json` → `primary_screen: FrmAgenda.aspx`; captura del run |
| E5 | El dossier reporta `BLOCKED` con 3/3 tests verdes | `evidence/367/<run>/dossier.json` vs `runner_output.json` (3 × `"status": "passed"`) |
| E6 | `data_readiness_check` muere con `NameError: name '_run_id' is not defined` | Log del pipeline; la variable existe como `_run_id` en `qa_uat_pipeline.py:359` pero no está en el scope del call site (`:2275`) |
| E7 | `QA_UAT_CLCOD` ya desbloquea la validación de contrato de navegación | El ADO-387 pasó de `NAVIGATION_DATA_MISSING` a bloquear recién en el generador |
| E8 | El bloqueo restante de las 5 incidencias es **un solo artefacto**: el playbook de `FrmDetalleClie` | `generated: 0, blocked: 2` con `MISSING_PLAYBOOK`; el ui_map de esa pantalla se construyó sin cliente (5.7 KB vs 38 KB de `FrmBusqueda`) |
| E9 | La navegación al detalle usa `?q=` encriptado por sesión | Click en fila de agenda → `FrmDetalleClie.aspx?q=4hVF9ypabGEudDMcl3cMASSNhFPC7sZ1…` |

---

## 3. Principios y guardarraíles (NO negociables)

- **G1 · La ley de discriminación manda.** Ninguna fase puede introducir un camino que produzca PASS sin aserción discriminante. Cualquier duda se resuelve del lado de `not_verifiable`.
- **G2 · Determinista, cero LLM en el núcleo.** Catálogo de aserciones, control negativo, generación de datos y veredicto son Python puro ⇒ idénticos en los 3 runtimes.
- **G3 · Reusar, no reescribir.** Se extienden `uat_assertion_evaluator`, el template J2, `qa_uat_pipeline` y los módulos del 240. Cero reemplazos.
- **G4 · Human-in-the-loop intacto.** Publicar en ADO sigue siendo `mode="publish"` explícito. Nada de este plan escribe en ADO.
- **G5 · Cero trabajo extra al operador.** Todo automático u opt-in default **ON**, salvo la excepción dura ya citada por el 240 (autostart de AgendaWeb, prerequisito no garantizado).
- **G6 · Fallar ruidoso, nunca silencioso.** Todo degradado deja `reason` + `human_action_required` en la evidencia.
- **G7 · Gotchas del repo:** flags desde la instancia `config.config`; `backend/tests/test_*.py` nuevos en `HARNESS_TEST_FILES` (`.sh` **y** `.ps1`); tests por archivo; venv py3.13; commits con pathspec explícito (árbol compartido).
- **G8 · Prohibido tocar** `frontend/src/pages/TicketBoard.tsx`, `frontend/src/pages/UnblockerPage.tsx`, `frontend/src/components/TicketGraphView.jsx`. Este plan **no toca frontend**.

---

## 4. Nomenclatura fija

**Módulos nuevos** (bajo `Stacky tools/QA UAT Agent/`):
- `assertion_catalog.py` — `build_assertions(criterion, ui_map, screen) -> list[dict]`, `SUPPORTED_KINDS`.
- `discrimination_prover.py` — `prove(assertion, criterion) -> dict`, `requires_discrimination(kind) -> bool`.
- `test_data_forge.py` — `forge(criterion) -> dict` (valor positivo + valor de control negativo).
- `screen_guard.py` — `verify_screen(page_state, expected_screen) -> dict`.
- `epic_rollup.py` — `rollup(epic_id, children_results) -> dict`.

**Códigos nuevos (strings exactos):** `NAV_WRONG_SCREEN`, `NO_DISCRIMINATION`, `DISCRIMINATION_FAILED`, `ATTRIBUTE_MISMATCH`, `GLOBAL_SETUP_FAILED`, `BROWSER_VERSION_DRIFT`.
**Tipo de oráculo nuevo:** `attribute_equals` (target = alias del ui_map; `atributo` + `valor`).
**Flags (2):** `STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED` (bool, default **True**, categoría `calidad_verificacion`), `STACKY_QA_UAT_EPIC_ROLLUP_ENABLED` (bool, default **True**, misma categoría).

**Comandos canónicos:**
```powershell
# Tool (pytest POR ARCHIVO)
cd "N:\GIT\RS\STACKY\Stacky\Stacky tools\QA UAT Agent"
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" -m pytest tests\unit\<archivo> -q

# Backend (pytest POR ARCHIVO)
cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"
& ".venv\Scripts\python.exe" -m pytest tests\<archivo> -q

# E2E real (requiere AgendaWeb arriba)
$env:AGENDA_WEB_BASE_URL="http://localhost:35017/AgendaWeb/"; $env:AGENDA_WEB_USER="PABLO"; $env:AGENDA_WEB_PASS="PABLO"; $env:QA_UAT_CLCOD="17654321"
& "..\..\Stacky Agents\backend\.venv\Scripts\python.exe" qa_uat_pipeline.py --ticket <ADO_ID> --mode dry-run
```

---

## 5. Fases

> Orden: **F0 → F1 → F2 → F3 → F4 → F5 → F6 → F7 → F8 → F9**. F4 es independiente y puede adelantarse (desbloquea 5 incidencias por sí sola). F9 exige todo lo anterior.

---

### F0 — El gate terminal: el veredicto funcional manda, y la pantalla se verifica

**Objetivo:** que el veredicto final del pipeline lo produzca `functional_verdict` (ya escrito y testeado en el 240, **sin cablear**), y que un PASS en la pantalla equivocada sea imposible.

**Valor:** mata los dos falsos positivos observados (366 pantalla equivocada, agregación que oculta 3/3 verdes).

**Archivo a CREAR: `screen_guard.py`**
```python
"""screen_guard.py — Un PASS en la pantalla equivocada es imposible (Plan 241 F0)."""
def verify_screen(page_state: dict, expected_screen: str) -> dict:
    """page_state: {"url": str, "title": str, "anchor_present": bool|None}
    Retorna {"ok": bool, "code": str, "detail": str}.
    Reglas EXACTAS (en orden):
      1. expected_screen vacio => {"ok": True, "code": "", ...} (nada que verificar).
      2. is_login_redirect(url)          => code "NAV_SESSION_LOST".
      3. expected_screen (sin .aspx, lower) NO contenido en url.lower()
                                         => code "NAV_WRONG_SCREEN" con url real.
      4. anchor_present is False         => code "NAV_WRONG_SCREEN" (llego la URL pero
                                            no el contenido: postback a medias).
      5. resto                            => ok True.
    NUNCA lanza."""
```

**Archivos a EDITAR:**
1. `qa_uat_pipeline.py` — en el stage `evaluator` (`:3658`, donde ya se llama `uat_assertion_evaluator.run`), DESPUÉS de obtener las evaluaciones, calcular el veredicto funcional y **usarlo como veredicto del run**:
   ```python
   from functional_verdict import build_functional_verdict     # ya existe (Plan 240)
   _criteria_results = [
       {"id": e.get("scenario_id"), "kind": e.get("kind"),
        "status": ("verified" if e.get("status") == "pass"
                   else "violated" if e.get("status") == "fail"
                   else "not_verifiable"),
        "evidence": e.get("evidence_path"), "detail": e.get("detail")}
       for e in (_evaluations or [])
   ]
   _fv = build_functional_verdict(_criteria_results, {"verdict": _runner_verdict,
                                                      "category": _runner_category})
   stages["functional_verdict"] = {"ok": True, "skipped": False, **_fv}
   ```
   Y en `_build_output`, el `verdict`/`reason` del run salen de `stages["functional_verdict"]` cuando existe; si no, del runner (degradación). **Regla dura:** con `verified == 0` el run **no puede** salir `PASS`.

   **(C4) Guarda obligatoria — el gate funcional NO puede tapar un BLOCKED honesto.** Si el evaluador se saltó (`stages["evaluator"].get("skipped") is True`, p. ej. con `reason == "all_scenarios_blocked"`, `qa_uat_pipeline.py:3090`), entonces `_criteria_results` está vacío **no porque no se verificara nada, sino porque no se llegó a ejecutar**. En ese caso:
   ```python
   _evaluator_ran = not stages.get("evaluator", {}).get("skipped", False)
   if _evaluator_ran:
       stages["functional_verdict"] = {"ok": True, "skipped": False, **_fv}
       _final_verdict, _final_reason = _fv["verdict"], _fv["reason"]
   else:
       stages["functional_verdict"] = {"ok": True, "skipped": True,
                                       "reason": "evaluator_did_not_run"}
       _final_verdict, _final_reason = _runner_verdict, _runner_reason   # BLOCKED honesto
   ```
   Sin esta guarda, todo run bloqueado por entorno saldría `MIXED/NO_FUNCTIONAL_ASSERTION`, que es **menos** honesto que el `BLOCKED` actual.
2. `templates/playwright_test.spec.ts.j2` — en el `afterEach` que ya escribe `assertions_<sid>.json`, agregar el bloque `screen_verified`:
   ```ts
   screen_verified: {
     url: page.url(),
     title: await page.title().catch(() => ''),
     expected: EXPECTED_SCREEN,          // inyectado por el generador desde scenario.pantalla
     anchor_present: await page.locator(ANCHOR_SELECTOR).count().then(c => c > 0).catch(() => null),
   }
   ```
3. `qa_uat_pipeline.py` — tras el runner, para cada escenario con `screen_verified`, llamar `screen_guard.verify_screen`; si `ok is False`, forzar ese escenario a `violated` con el `code` devuelto. **Un escenario que no probó su pantalla no aporta un `verified`.**

**Tests (TDD): `tests/unit/test_plan241_screen_guard.py`**
- `test_pantalla_correcta_ok`: url con `FrmBusqueda`, ancla presente → `ok True`.
- `test_pantalla_equivocada` (**caso real del 366**): expected `FrmDetalleClie.aspx`, url `.../FrmAgenda.aspx` → `code == "NAV_WRONG_SCREEN"` y el detalle nombra ambas.
- `test_login_redirect_es_session_lost`.
- `test_url_ok_pero_sin_ancla_es_wrong_screen`.
- `test_expected_vacio_no_bloquea`.
- `test_verdict_final_sale_del_funcional`: pipeline fake con runner PASS y 0 criterios verificados → veredicto `MIXED/NO_FUNCTIONAL_ASSERTION`.
- `test_verdict_pass_requiere_verified`: 2 verificados, 0 violados → `PASS`.

**Aceptación (binaria):** `pytest tests\unit\test_plan241_screen_guard.py -q` → **7/7**; `grep -c "build_functional_verdict" qa_uat_pipeline.py` → **≥1**; `grep -c "screen_verified" templates/playwright_test.spec.ts.j2` → **≥1**. Regresión: el ADO-367 vuelve a correr y su veredicto final ya **no** es `BLOCKED` con 3/3 verdes (E5 corregido).
**Flag:** ninguna — es la corrección de un falso positivo; gatearlo sería dejar el bug activable.
**Runtimes:** los 3 idéntico (pipeline determinista). **Operador:** ninguno.

---

### F1 — Catálogo de aserciones por tipo de criterio (incluye `attribute_equals`)

**Objetivo:** traducir cada `kind` de criterio a una aserción Playwright **concreta y discriminante**, en vez de a un oráculo de texto genérico.

**Valor:** es la mejora de mayor retorno por línea. Para el ADO-367, en lugar de tipear 20 caracteres, se asertará `maxlength == "50"`: una comprobación exacta, imposible de falsear.

**Archivo a CREAR: `assertion_catalog.py`**
```python
"""assertion_catalog.py — kind de criterio -> asercion concreta (Plan 241 F1)."""
SUPPORTED_KINDS = ("maxlength", "catalog", "absence", "ordering", "presence",
                   "value", "color", "no_error")

def build_assertions(criterion: dict, ui_map: dict, screen: str) -> list:
    """Devuelve una lista de oraculos ejecutables. NUNCA lanza; [] si no puede.

    Mapa EXACTO kind -> oraculo:
      maxlength : {"tipo": "attribute_equals", "target": <alias del input>,
                   "atributo": "maxlength", "valor": criterion["expected"]}
                  (caso ADO-367: #c_abfCodObligacion / maxlength / "50")
      catalog   : un {"tipo": "contains_literal", "target": <alias del select>,
                      "valor": token} POR CADA token del criterio
                  (caso ADO-366: "Laboral" y "Particular" en el combo Tipo Telefono)
      absence   : {"tipo": "count_eq", "target": <alias>, "valor": 1}
                  sobre el conteo de columnas/elementos con ese texto
                  (caso ADO-387: "Medio de Contacto" debe aparecer UNA vez)
      presence  : {"tipo": "visible", "target": <alias>, "valor": true}
      ordering  : {"tipo": "ordered_by", "target": <alias de la grilla>,
                   "columna": <col>, "direccion": "asc"|"desc"}
      value     : {"tipo": "equals", "target": <alias>, "valor": criterion["expected"]}
      color     : {"tipo": "attribute_equals", "target": <alias>, "atributo": "class",
                   "valor": <clase esperada>}   # si el criterio nombra la clase
      no_error  : {"tipo": "no_console_error"}  # consumido por console_noise_policy
    Resolucion del target: primero por token entrecomillado contra id/label/alias del
    ui_map (reusa menu_resolver/playbook_synthesizer.find_by_tokens); si no resuelve,
    NO se inventa un alias: se devuelve [] y el criterio queda not_verifiable."""
```

**Archivos a EDITAR:**
1. `uat_assertion_evaluator.py` → `_evaluate_deterministic` (`:243`): ramas nuevas **antes** del `else` final:
   ```python
   elif tipo == "attribute_equals":
       return "pass" if str(actual).strip() == str(expected).strip() else "fail"
   elif tipo == "ordered_by":
       # actual: lista de valores de la columna, en el orden del DOM
       vals = actual if isinstance(actual, list) else []
       ok = vals == sorted(vals, reverse=(str(expected).lower() == "desc"))
       return "pass" if ok else "fail"
   elif tipo == "no_console_error":
       return "pass" if not actual else "fail"     # actual = significativos
   ```
   **Regla dura:** ninguna rama nueva puede devolver `"pass"` cuando `actual is None` (el guard de `:245-247` ya lo cubre: NO tocarlo).
2. `templates/playwright_test.spec.ts.j2` — **(C1) el tipo `OracleProbe` NO tiene campo para el atributo**: hoy son exactamente 5 (`oracle_id, target, tipo, expected, selector`, `:71-80`). Hay que:
   - extender el type con `atributo?: string | null;`
   - emitirlo en el bucle: `atributo: {{ (oracle.atributo if oracle.atributo is defined else None) | tojson }},`
   - y capturar el `actual` de los tipos nuevos en el `afterEach`:
     - `attribute_equals` → `await page.locator(probe.selector).first.getAttribute(probe.atributo)`
     - `ordered_by` → `await page.locator(probe.selector + ' tbody tr td:nth-child(N)').allInnerTexts()`
     - `no_console_error` → los mensajes del listener de consola, filtrados con `console_noise_policy` (Plan 240).

   **(C2) REGLA DURA sobre `target`.** El template resuelve el selector con `ui_map[oracle.target]` (`:78`): el `target` **no es un selector CSS, es una CLAVE del dict `ui_map`** que recibe la plantilla. Si el alias no existe, se emite `selector: undefined`, el probe captura `actual = null` y el evaluador devuelve `"review"` ⇒ **el criterio se pierde en silencio**. Por eso `build_assertions` recibe el ui_map y **verifica que el alias esté en sus claves**; si no está, devuelve `[]` y el criterio queda `not_verifiable` de forma visible.
3. `uat_scenario_compiler.py` — cuando el ítem del plan trae `kind` (lo pone `acceptance_extractor` del 240), pedir los oráculos a `assertion_catalog.build_assertions` **antes** de caer en la heurística de texto. Los oráculos del catálogo **reemplazan** a los heurísticos, no se suman.

**Tests (TDD): `tests/unit/test_plan241_assertion_catalog.py`**
- `test_maxlength_del_367`: criterio `kind="maxlength", expected="50"`, ui_map con `c_abfCodObligacion` → oráculo `attribute_equals/maxlength/50` con ese target.
- `test_catalog_del_366`: tokens `["Laboral","Particular"]` → **2** oráculos `contains_literal`.
- `test_absence_del_387`: token `"Medio de Contacto"` → `count_eq` con `valor == 1`.
- `test_target_no_resuelto_devuelve_vacio`: token que no matchea nada del ui_map → `[]` (no se inventa alias).
- `test_evaluator_attribute_equals`: `_evaluate_deterministic("attribute_equals","50","50")` → `"pass"`; con `"20"` → `"fail"`; con `None` → `"review"`.
- `test_evaluator_ordered_by_asc_y_desc`.
- `test_evaluator_no_console_error`.
- `test_template_emite_getattribute`: el `.j2` contiene `getAttribute(` (anti-regresión).

**Aceptación:** `pytest tests\unit\test_plan241_assertion_catalog.py -q` → **8/8**; `grep -c "attribute_equals" uat_assertion_evaluator.py assertion_catalog.py` → ≥1 en cada uno; **verificación en vivo**: el ADO-367 genera el oráculo `attribute_equals` y pasa (el fix está puesto: `maxlength="50"` medido en vivo).
**Flag:** ninguna — aditivo: sin `kind` en el ítem, el compilador se comporta como hoy.
**Runtimes:** los 3 idéntico. **Operador:** ninguno.

---

### F2 — Control negativo obligatorio: la prueba de que la aserción sabe fallar

**Objetivo:** que cada aserción declare y **demuestre** su poder de discriminación antes de contar como `verified`.

**Valor:** es el corazón del plan. Sin esto, F1 mejora la puntería pero no impide otro caso "20 caracteres contra un bug de 20 caracteres".

**Archivo a CREAR: `discrimination_prover.py`**
```python
"""discrimination_prover.py — Una asercion que no puede fallar no es una asercion.

LEY (Plan 241): un criterio solo cuenta como `verified` si su asercion viene con un
CONTROL NEGATIVO: el valor/estado pre-fix contra el cual la MISMA asercion da `fail`.
La comprobacion es puramente logica (se evalua el oraculo contra el control negativo
con el mismo _evaluate_deterministic): NO abre el navegador ni toca la app.
"""
def requires_discrimination(kind: str) -> bool:
    """True para los kinds con umbral/valor concreto: maxlength, value, catalog,
    absence, ordering, color. False para presence y no_error (su control negativo es
    trivialmente el estado contrario y ya lo cubre el evaluador)."""

def negative_control_for(criterion: dict, assertion: dict) -> dict | None:
    """Deriva el control negativo del texto del criterio. Reglas EXACTAS:
      maxlength : el valor PRE-FIX citado en el ticket ("truncaba a 20" -> "20");
                  si el ticket no lo cita, usar str(int(expected) // 2) y anotarlo
                  en `derived: true`.
      catalog   : la lista de opciones PREVIAS citadas ("solo ofrece No Identificado,
                  Fijo, Movil y Trabajo") -> el token esperado NO esta en ella.
      absence   : el conteo PREVIO (duplicado) -> 2.
      ordering  : el orden inverso.
      value/color: el valor observado ("Comportamiento observado: ...").
    Devuelve {"valor": <control>, "fuente": "ticket"|"derivado"} o None."""

def prove(assertion: dict, criterion: dict) -> dict:
    """{"proven": bool, "negative_control": <valor|None>, "code": str, "detail": str}
    proven=True SOLO si _evaluate_deterministic(tipo, expected, negative_control)
    devuelve "fail". Si devuelve "pass" => la asercion NO discrimina =>
    code "DISCRIMINATION_FAILED" (es un BUG DEL TEST, no del desarrollo).
    Sin control negativo => code "NO_DISCRIMINATION"."""
```

**Archivo a EDITAR: `functional_verdict.py`** — regla nueva, aplicada **antes** de contar `verified`:
```python
# Plan 241 F2: un criterio con status "verified" pero sin discriminacion probada
# NO cuenta como verificado: pasa a not_verifiable. Gateado por
# STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED (default ON).
if strict and c.get("status") == "verified" and not (c.get("discrimination") or {}).get("proven"):
    c["status"] = "not_verifiable"
    c["downgrade_reason"] = "NO_DISCRIMINATION"
```

**[ADICIÓN ARQUITECTO — C6] El fallo del test no se disfraza de fallo del desarrollo.** Un `DISCRIMINATION_FAILED` significa *"esta aserción no sabe fallar"*: es un **bug del arnés**, no del desarrollo. Si se mezclara con el veredicto, un arnés flojo se leería como software roto. Regla:
- el criterio afectado cae a `not_verifiable` ⇒ el run sale `MIXED/PARTIAL_COVERAGE` (nunca `FAIL`);
- el caso se emite en una sección **propia** del dossier, `test_quality_issues: [{"criterio_id", "kind", "code", "detail", "fix_sugerido"}]`, que `qa_dossier_builder` renderiza aparte de los hallazgos del desarrollo;
- esa lista es el backlog accionable para mejorar el catálogo (F1) y la forja (F3).
Test dedicado: `test_discrimination_failed_no_es_fail_del_desarrollo` — un criterio con `DISCRIMINATION_FAILED` produce `MIXED`, **no** `FAIL`, y aparece en `test_quality_issues`.

**Tests (TDD): `tests/unit/test_plan241_discrimination.py`**
- `test_maxlength_367_discrimina` (**el test insignia**): aserción `attribute_equals maxlength=50` + control negativo `"20"` → `proven True`.
- `test_maxlength_con_dato_de_20_no_discrimina`: aserción `equals` con valor de 20 chars y control negativo de 20 chars → `proven False`, `code == "DISCRIMINATION_FAILED"`.
- `test_catalog_366_discrimina`: control negativo = lista previa sin "Laboral" → `proven True`.
- `test_absence_387_discrimina`: control negativo = 2 → `count_eq(1)` da fail → `proven True`.
- `test_sin_control_negativo`: → `proven False`, `code == "NO_DISCRIMINATION"`.
- `test_kinds_que_no_requieren`: `presence` y `no_error` → `requires_discrimination` False.
- `test_verdict_degrada_sin_discriminacion`: criterio `verified` sin `discrimination` + strict ON → cuenta como `not_verifiable` ⇒ veredicto `MIXED`.
- `test_flag_off_no_degrada`: strict OFF → cuenta como `verified` (compatibilidad).
- `test_discrimination_failed_no_es_fail_del_desarrollo` (**C6**): → `MIXED` (no `FAIL`) y el caso aparece en `test_quality_issues`.

**Aceptación:** `pytest tests\unit\test_plan241_discrimination.py -q` → **9/9**; `grep -c "DISCRIMINATION_FAILED" discrimination_prover.py` → ≥1; `grep -c "test_quality_issues" functional_verdict.py qa_dossier_builder.py` → ≥1 en cada uno.
**Flag:** `STACKY_QA_UAT_STRICT_DISCRIMINATION_ENABLED` default **ON**. Ninguna excepción dura aplica: es determinista, local y solo endurece el veredicto. Justificación de ON: el default laxo **es** el bug que este plan mata.
**Runtimes:** los 3 idéntico. **Operador:** ninguno.

---

### F3 — Datos de prueba que discriminan (forja determinista)

**Objetivo:** que el valor de prueba lo derive el arnés del propio criterio, garantizando que cruza el umbral.

**Valor:** el ADO-367 falló en esto: usó el valor truncado del ticket (20 chars) en vez de uno que probara el fix (>20).

**Archivo a CREAR: `test_data_forge.py`**
```python
"""test_data_forge.py — Valores de prueba que cruzan el umbral (Plan 241 F3)."""
def forge(criterion: dict) -> dict:
    """{"positivo": str, "negativo": str|None, "rationale": str}. NUNCA lanza.
    Reglas EXACTAS por kind:
      maxlength: positivo = una cadena de longitud int(expected) EXACTA, construida
                 a partir del literal del ticket y rellenada con [A-Z0-9-] deterministas
                 (nada de random: el mismo criterio produce SIEMPRE el mismo valor);
                 negativo = cadena de longitud (control_negativo + 1), que el campo
                 pre-fix habria rechazado.
                 (ADO-367: positivo de 50 chars, negativo de 21 => discrimina)
      value    : positivo = expected literal.
      catalog  : positivo = el primer token esperado.
      resto    : positivo = el literal entrecomillado del criterio, si existe.
    rationale explica en una linea POR QUE ese valor discrimina (va a la evidencia)."""
```
**Archivo a EDITAR: `acceptance_extractor.py`** — `build_plan_from_description` usa `forge()` para poblar `datos` con `CLAVE=valor` en vez de volcar los pasos de reproducción crudos. Los pasos de reproducción siguen yendo a `repro_steps` (contexto), no a `datos` (dato ejecutable).

**Tests (TDD): `tests/unit/test_plan241_test_data_forge.py`**
- `test_maxlength_forja_50_chars`: criterio del 367 → `len(positivo) == 50`.
- `test_maxlength_negativo_supera_el_umbral_previo`: `len(negativo) == 21`.
- `test_determinista`: dos llamadas con el mismo criterio → valores idénticos.
- `test_sin_expected_devuelve_none`: criterio sin `expected` → `positivo` None y `rationale` lo explica.
- `test_rationale_no_vacio`.

**Aceptación:** `pytest tests\unit\test_plan241_test_data_forge.py -q` → **5/5**; **en vivo**: el spec del ADO-367 tipea 50 caracteres y el campo los acepta (con el bug habría truncado a 20).
**Flag:** ninguna (aditivo). **Runtimes:** los 3. **Operador:** ninguno.

---

### F4 — El playbook de `FrmDetalleClie` con cliente en sesión (desbloquea 5 incidencias)

**Objetivo:** producir el ui_map y el playbook de la pantalla de detalle **con un cliente cargado**, que es el único artefacto que falta para 362, 366, 369, 373 y 387.

**Valor:** una sola pieza convierte 5 tickets `BLOCKED` en ejecutables. Es la fase de mayor retorno inmediato.

**Archivo a EDITAR: `playbook_synthesizer.py`** — función nueva:
```python
def ensure_playbook_with_context(screen: str, *, entry_screen: str = "FrmAgenda.aspx",
                                 row_selector: str | None = None) -> dict:
    """Sintetiza el playbook de una pantalla que EXIGE contexto previo (Plan 241 F4).

    Por que (Plan 240 H4/E9): FrmDetalleClie.aspx solo se abre con un cliente
    seleccionado, y el enlace real lleva un ?q= ENCRIPTADO POR SESION que NO se puede
    reconstruir. Por eso el contexto se gana NAVEGANDO, no sintetizando URLs:
      1. login  2. goto entry_screen  3. click en la primera fila de la grilla
      4. esperar aterrizaje en `screen`  5. recien AHI cosechar el ui_map real
         (ui_map_builder sobre la pagina viva) y elegir el ancla por VISIBILIDAD.
    El playbook resultante declara navigation_steps con la secuencia de CLICKS
    (jamas un goto con ?q=) y `requires_context: true`.
    Retorna {"ok": bool, "anchor": str|None, "ui_map_elements": int, "path": str|None,
             "error": str|None}. NUNCA lanza."""
```
Selector de fila por default (verificado en vivo): `#__gvc_GridAgendaAut__div table tr:nth-child(2) td:first-child`.

**Archivo a EDITAR: `ui_map_builder.py`** — parámetro nuevo `--from-live-page` que construye el mapa a partir de la **página actual** de una sesión ya navegada, en vez de hacer `goto` (hoy siempre navega por URL, y por eso el mapa de `FrmDetalleClie` salió de 5.7 KB sin contexto). Sin el flag, comportamiento idéntico al de hoy.

**Tests:** `tests/unit/test_plan241_context_playbook.py`
- `test_declara_requires_context`: el playbook generado tiene `requires_context is True`.
- `test_navigation_steps_sin_q_param`: ningún string del playbook contiene `?q=` (ratchet del 240).
- `test_click_en_fila_antes_del_wait`: el orden de `navigation_steps` es `goto entry → click fila → waitFor ancla`.
- `test_sin_grilla_devuelve_error_honesto`: fake sin filas → `ok False`, `error` explícito (no inventa ancla).
- **Verificación en vivo (obligatoria):** `cache/ui_maps/FrmDetalleClie.aspx.json` supera los **20 KB** (hoy 5.7 KB) y `cache/playbooks/verificar_frmdetalleclie.json` existe con `anchor_verified_live: true`.

**Aceptación:** los 4 tests verdes + la verificación en vivo + **los 5 tickets (362, 366, 369, 373, 387) pasan de `BLOCKED` a `stages.runner.total > 0`**, con la salida real pegada.
**Flag:** ninguna (artefactos de KB). **Runtimes:** los 3. **Operador:** ninguno.

---

### F5 — `via_menu`: las pantallas que no se alcanzan por URL

**Objetivo:** implementar el `via_menu` + `menu_resolver` que el Plan 240 especificó en su F3 y quedó sin construir, para llegar a `FrmGestion.aspx`, `FrmReportes.aspx`, `FrmLiquidaciones.aspx` e `FrmInformes.aspx`.

**Valor:** desbloquea el ADO-57 y toda la familia de pantallas con `?q=` obligatorio. Sin esto, ~30% del menú es inalcanzable.

**Alcance:** implementar **tal cual** está especificado en el Plan 240 §F3 (v3), que ya trae los fixes C1 (helper `reauth_in_page` async — **ya implementado** en `auth_session_factory.py`), C2 (`base_url` vía `environment_preflight.get_agenda_base_url`) y el ratchet `?q=`. Este plan **no re-especifica**: reusa. Archivos: `menu_resolver.py` (nuevo) + `navigation_driver.via_menu` + ramas de `_classify_error`.

**Tests:** `tests/unit/test_plan241_menu_resolver.py` — los 10 casos ya enumerados en el Plan 240 F3, más:
- `test_via_menu_alcanza_frmgestion_en_vivo` (marcado `@pytest.mark.e2e`, requiere AgendaWeb): resuelve la etiqueta del menú y aterriza en `FrmGestion.aspx` sin construir la URL.

**Aceptación:** 11/11 + `grep -c "def via_menu" navigation_driver.py` → 1 + el ADO-57 pasa de `BLOCKED/UI_MAP_MISSING` a ejecutable.
**Flag:** ninguna (método nuevo). **Runtimes:** los 3 + regla en `QAUat1.agent.md`. **Operador:** ninguno.

---

### F6 — Higiene de diagnósticos mentirosos

**Objetivo:** que ningún fallo se reporte con una causa que no es.

**Valor:** cada diagnóstico falso costó tiempo real de depuración en la corrida del 240.

**Tres correcciones exactas:**
1. **`NO_TESTS_FOUND` que en realidad es un crash del `globalSetup`.** **(C3) Anclaje exacto:** el sitio es el **guard estructural** `if total == 0:` de `uat_test_runner.py:761-766`. El fix va **inmediatamente ANTES** de ese guard: si la salida de Playwright contiene `globalSetup` **y** `Error:`, el reason pasa a `GLOBAL_SETUP_FAILED` (categoría `ENV`) con las 3 primeras líneas del error en `detail`. **Prohibido tocar `playwright_result_classifier.py`**: su regla *"total=0 ALWAYS maps to BLOCKED PIP NO_TESTS_FOUND — never PASS"* (`:25,34`) es **correcta** y debe seguir valiendo — lo que cambia es la **causa reportada**, nunca el hecho de que 0 tests jamás es PASS. Test: fixture con la salida real capturada (`Executable doesn't exist at ...chromium_headless_shell-1217...`) → `GLOBAL_SETUP_FAILED`, y un segundo test que verifica que un `total == 0` sin rastro de globalSetup sigue dando `NO_TESTS_FOUND`.
2. **`NameError: name '_run_id' is not defined`** (`qa_uat_pipeline.py`, call site del `data_readiness_check` cerca de `:2271-2276`): la variable existe como `_run_id` (`:359`) pero no está en el scope del bloque; pasarla explícitamente. Test: el stage `data_readiness_check` deja de aparecer con `reason` que empieza con `error:name`.
3. **Deriva de versiones Node↔Python** (`browser_runtime_guard.py`, del 240): función nueva `check_node_browser_drift() -> dict` que lee la versión de `node_modules/.bin/playwright --version` y la revisión que exige, y la compara con la del binding Python; si difieren, `code == "BROWSER_VERSION_DRIFT"` con el comando de remediación **de ambos lados**. Se expone en el endpoint `runtime-doctor`. Test: fixture con 1.59.1 vs 1.61.0 → drift detectado con las 2 remediaciones.

**Aceptación:** `pytest tests\unit\test_plan241_diagnostics.py -q` → **6/6**; `grep -c "GLOBAL_SETUP_FAILED" uat_test_runner.py` → ≥1; una corrida completa **sin** `reason` que empiece con `error:name`.
**Flag:** ninguna. **Runtimes:** los 3. **Operador:** ninguno.

---

### F7 — Épicas: validación por agregación de hijas

**Objetivo:** que una épica no dé `BLOCKED/missing_technical_analysis`, sino un veredicto agregado real de sus tasks hijas.

**Valor:** las épicas (61, 125) son *roll-ups*: no tienen pasos de reproducción propios. Pero sus hijas sí (65 y 70 son hijas de 61, con `parent=61` verificado) y **ya corren**.

**Archivo a CREAR: `epic_rollup.py`**
```python
"""epic_rollup.py — Veredicto de una epica por agregacion de sus hijas (Plan 241 F7)."""
def rollup(epic_id: int, children_results: list) -> dict:
    """children_results: [{"ado_id": int, "verdict": str, "verified": int, ...}]
    Reglas EXACTAS:
      - sin hijas ejecutadas            -> SKIPPED / NO_EXECUTABLE_CHILDREN
      - alguna hija FAIL                -> FAIL / CHILD_ACCEPTANCE_VIOLATED
      - alguna BLOCKED y ninguna FAIL   -> MIXED / PARTIAL_EPIC_COVERAGE
      - todas PASS                      -> PASS / EPIC_ACCEPTANCE_MET
    Incluye SIEMPRE `children` con el detalle por hija: una epica en verde con una
    hija sin correr es un falso verde, y el campo lo hace visible."""
```
**Archivo a EDITAR: `uat_ticket_reader.py`** — si el work item es `Epic` y no tiene secciones canónicas, en vez de `missing_technical_analysis` devolver `ok=True` con `epic_rollup_required: true` y la lista de hijas (obtenida con el bridge ADO del 240, consulta **solo lectura** por `System.Parent`). El pipeline, al ver ese flag, corre `epic_rollup` con los últimos resultados de las hijas.

**Tests:** `tests/unit/test_plan241_epic_rollup.py` — 6 casos (los 4 de precedencia + `test_children_siempre_presente` + `test_epica_61_con_65_y_70`, usando los resultados reales).
**Aceptación:** 6/6 + el ADO-61 devuelve un veredicto agregado con sus dos hijas listadas.
**Flag:** `STACKY_QA_UAT_EPIC_ROLLUP_ENABLED` default **ON** (solo lectura, aditivo).
**Runtimes:** los 3. **Operador:** ninguno.

---

### F8 — Cierre de lo que el Plan 240 dejó sin implementar

**Objetivo:** terminar las fases F2 (launcher de AgendaWeb), F7 (manifiesto de evidencia con hash) y F8 (flags en UI + endpoint `runtime-doctor` + registro en el ratchet) del Plan 240.

**Alcance:** implementar **tal cual** están especificadas en el Plan 240 v3, sin re-especificar. Se suman a ese alcance, por este plan:
- las 2 flags nuevas de F2/F7 de **este** plan en los mismos 5 lugares;
- el `runtime-doctor` expone además `check_node_browser_drift` (F6);
- `backend/tests/test_plan241_qa_uat.py` registrado en `HARNESS_TEST_FILES` (`.sh` **y** `.ps1`).

**Aceptación:** los criterios binarios del Plan 240 F2/F7/F8 + `pytest tests\test_plan241_qa_uat.py -q` verde + `grep -c "test_plan241_qa_uat.py" scripts/run_harness_tests.sh scripts/run_harness_tests.ps1` → 1 en cada uno.

---

### F9 — Suite golden reproducible (el ratchet que impide la recaída)

**Objetivo:** congelar los tickets que corren en verde como una suite de regresión reproducible, con veredicto esperado por escenario.

**Valor:** sin esto, cualquier cambio futuro puede reintroducir un falso verde y nadie se entera hasta que alguien mire una captura — que es exactamente cómo se descubrió el del 366.

**Archivo a CREAR: `golden_suite.py`**
```python
"""golden_suite.py — Regresion E2E reproducible (Plan 241 F9).

golden/expected.json: {"<ado_id>": {"verdict": str, "verified": int,
                                    "scenarios": {"P01": "pass", ...}}}
"""
def record(ado_ids: list) -> dict:   # corre y GRABA el esperado (opt-in explicito)
def verify(ado_ids: list) -> dict:   # corre y COMPARA; diff por escenario
```
CLI: `python golden_suite.py --record 367 65 70` / `--verify` (default: los ids grabados).
**Regla dura:** `--record` **nunca** corre en automático; grabar un esperado es una decisión del operador (si no, se congelaría un falso verde).

**Tests:** `tests/unit/test_plan241_golden_suite.py` — 5 casos (grabar/verificar/diff/archivo ausente/no-lanza).
**Aceptación:** 5/5 + **en vivo**: `--verify` sobre el golden grabado corre **dos veces** y produce el mismo resultado (KPI-7), con la salida pegada.
**Flag:** ninguna (herramienta CLI). **Runtimes:** los 3. **Operador:** solo el `--record` inicial (una vez, opt-in explícito).

---

## 6. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El control negativo (F2) degrada tantos criterios que todo queda `MIXED` | Es el resultado **honesto** mientras el catálogo (F1) no cubra un `kind`. La métrica a mirar es `verified/total`, y F1+F3 la suben. La flag permite medir el antes/después sin perder trazabilidad |
| R2 | `negative_control_for` deriva mal el valor pre-fix del texto | Marca `fuente: "derivado"` cuando no lo cita el ticket; un derivado nunca se presenta como evidencia fuerte y queda en la evidencia para revisión |
| R3 | F4 depende de que la agenda tenga al menos un cliente | Si la grilla viene vacía, `ok False` con error explícito (nunca inventa ancla). Hoy hay datos reales (`RUT 17654321-*`) |
| R4 | `--from-live-page` (F4) rompe el `ui_map_builder` actual | Parámetro opt-in; sin él, comportamiento byte-idéntico. Test de regresión del builder por archivo |
| R5 | El veredicto funcional como gate terminal (F0) cambia veredictos históricos | Es el objetivo. Los runs viejos no se reescriben; el cambio aplica a runs nuevos y queda declarado en `stages.functional_verdict` |
| R6 | `ordered_by` compara strings y falla con fechas `dd/mm/yyyy` | El catálogo declara `columna_tipo` (`text|number|date`); para `date` normaliza a ISO antes de comparar. Test explícito con fechas de la agenda real |
| R7 | Colisión con el Plan 240 en `qa_uat_pipeline.py` y `functional_verdict.py` | Este plan **continúa** el 240 (mismo autor, mismas ramas); las ediciones son aditivas y F8 declara explícitamente qué fases del 240 cierra |
| R8 | Sesión paralela viva en el árbol compartido | Este plan **no toca frontend**; commits con pathspec explícito; `git worktree list` + `git status` antes de commitear |

## 7. Fuera de scope

- Corregir bugs de AgendaWeb detectados (p. ej. `FrmJDemanda.aspx` que devuelve 200 con cuerpo de error 500): el agente los **reporta**, no los arregla.
- Enriquecimiento por LLM de criterios u oráculos (G2: el núcleo es determinista).
- Publicación automática a ADO (sigue HITL).
- Cualquier cambio de frontend, incluido el pane de veredicto del Plan 214 F4.
- Reescribir el compilador de escenarios: F1 se engancha en su seam, no lo reemplaza.

## 8. Glosario

- **Aserción discriminante:** la que **falla** contra el estado pre-fix. Una que pasa en ambos estados no prueba nada.
- **Control negativo:** el valor/estado pre-fix contra el cual se comprueba que la aserción sabe fallar. Se deriva del propio ticket ("truncaba a 20", "solo ofrece … Trabajo").
- **`attribute_equals`:** oráculo nuevo que asserta un atributo del DOM (`maxlength`, `class`) en vez del valor tipeado. Para umbrales de UI es exacto e infalsificable.
- **Roll-up de épica:** veredicto de una épica calculado agregando el de sus tasks hijas, porque una épica no tiene pasos propios.
- **Suite golden:** conjunto de tickets con veredicto esperado congelado, usado como regresión reproducible.
- **`?q=`:** payload encriptado y válido solo para la sesión actual que AgendaWeb pone en varios links; jamás se persiste ni se reconstruye.

## 9. Orden de implementación

1. **F4** — playbook de `FrmDetalleClie` (desbloquea 5 incidencias; independiente y de mayor retorno inmediato).
2. **F0** — gate terminal del veredicto funcional + `screen_guard` (impide falsos verdes desde ya).
3. **F1** — catálogo de aserciones + `attribute_equals` en evaluador y template.
4. **F2** — control negativo obligatorio.
5. **F3** — forja de datos discriminantes.
6. **F6** — higiene de diagnósticos (barato y mejora toda depuración posterior).
7. **F5** — `via_menu` (desbloquea el ADO-57 y el resto del menú).
8. **F7** — roll-up de épicas.
9. **F8** — cierre de F2/F7/F8 del Plan 240 + flags + doctor + ratchet.
10. **F9** — suite golden.

## 10. Definición de Hecho (DoD)

- [ ] **9 archivos de test nuevos** verdes, corridos **POR ARCHIVO**, con la salida real pegada: `test_plan241_screen_guard` **7**, `assertion_catalog` **9** (8 + el de alias inexistente, C2), `discrimination` **9** (8 + C6), `test_data_forge` **5**, `context_playbook` **4**, `menu_resolver` **11**, `diagnostics` **7** (6 + el de `total==0` sin globalSetup, C3), `epic_rollup` **6**, `golden_suite` **5** → **63 casos** (C5: recuento verificado). Más `backend/tests/test_plan241_qa_uat.py` registrado en `HARNESS_TEST_FILES` (`.sh` y `.ps1`).
- [ ] **(C1/C2) Contrato del template intacto:** `grep -c "atributo" templates/playwright_test.spec.ts.j2` → ≥2 (tipo + emisión); y un test verifica que un `target` que NO es clave del ui_map produce `[]` en el catálogo, jamás un probe con `selector: undefined`.
- [ ] **(C3)** `playwright_result_classifier.py` **sin modificar** (`git diff --stat` no lo lista): su regla "0 tests nunca es PASS" sigue vigente.
- [ ] **(C4)** Un run bloqueado por entorno sigue reportando `BLOCKED`, no `MIXED`.
- [ ] Regresiones verdes (por archivo): `test_uat_ticket_reader`, `test_navigation_driver`, `test_navigation_plan_gate`, `test_replan_engine`, `test_plan240_*` (los 3), `test_qa_uat_endpoint`, `test_harness_flags`.
- [ ] **KPI-1 probado:** un run con 0 criterios verificados devuelve `MIXED/NO_FUNCTIONAL_ASSERTION`, nunca PASS.
- [ ] **KPI-2 probado:** un escenario que aterriza en pantalla distinta a la del criterio devuelve `NAV_WRONG_SCREEN` (reproducir el caso del ADO-366).
- [ ] **KPI-3 probado:** el ADO-367 produce `attribute_equals(maxlength=50)` con `discrimination.proven == true` y control negativo `"20"`.
- [ ] **KPI-5 probado:** 362, 366, 369, 373 y 387 con `stages.runner.total > 0`.
- [ ] **KPI-6 probado:** una corrida completa sin `NO_TESTS_FOUND` espurio, sin `error:name '_run_id'` y con el drift Node↔Python reportado en `runtime-doctor`.
- [ ] **KPI-7 probado:** `golden_suite.py --verify` dos veces seguidas → mismo veredicto por escenario.
- [ ] Las 2 flags nuevas visibles en Configuración → Arnés, categoría `calidad_verificacion`, ambas default ON.
- [ ] `python -m compileall` limpio sobre los módulos nuevos y editados.
- [ ] **Ningún archivo de frontend tocado** (verificable con `git status`).
- [ ] `git worktree list` + `git status` revisados antes de commitear; commits con **pathspec explícito**.
