# Plan 189 — DevOps: preparación de rollback — semáforo de reversibilidad y simulacro read-only

- **Versión:** v1 (PROPUESTO)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
- **Serie:** DevOps (extiende el Centro de Despliegues 120; hermano de 188 evidencia de fallos)

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** El Centro de Despliegues (120) tiene un botón de rollback que EJECUTA
(`POST /devops/deployments/rollback`, `api/devops_deployments.py:245`, con `confirm=True` y
`confirm_text` en targets protegidos) — pero **nada te dice ANTES si podés volver atrás ni qué haría
exactamente**. La reversibilidad recién se descubre en el peor momento: con producción caída. Este plan
agrega **reversibilidad como indicador de primera clase**: un semáforo por app×target ("↩ Rollback
listo → v1.4.1" / "↩ Sin respaldo") calculado con lecturas LOCALES puras del ledger, y un **simulacro
read-only** que muestra los pasos EXACTOS que ejecutaría el rollback real (mismo builder,
`deploy_planner.build_rollback_plan`, `services/deploy_planner.py:210`) sin tocar nada. El operador
sabe SIEMPRE, de un vistazo, si tiene red de seguridad — y puede ensayar el rollback antes de
necesitarlo.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Readiness correcto | Los 5 escenarios golden (con candidatas / sin retenidas / target sin cfg / run en curso / solo la versión actual retenida) devuelven exactamente el `ready` y los `reasons` esperados |
| KPI-2 | Simulacro inocuo | Con `remote_exec.run_deploy_step` y `deploy_executor.LocalTransport.run` monkeypatcheados a `raise`, el preview responde 200 — CERO ejecución; y responde 200 aun con `STACKY_DEPLOYMENTS_EXECUTE_ENABLED` OFF |
| KPI-3 | Paridad con el rollback real | Los `steps` del simulacro son EXACTAMENTE los de `deploy_planner.build_rollback_plan(...)` llamado directo con los mismos argumentos (comparación `==` en test) |
| KPI-4 | UI pura verificada | Helpers de badge/filas testeados por vitest y `npx tsc --noEmit` sin errores nuevos |

**Ganancia robusta:** el costo de descubrir "no hay rollback posible" pasa de minutos de pánico en
incidente a un badge gris visible desde el primer día. Cero red, cero ejecución, cero riesgo.

**Onboarding casi nulo:** el semáforo aparece solo en las cards que el operador ya mira; el simulacro
es un botón al lado del rollback que ya conoce.

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `api/devops_deployments.py:245-269` — `/rollback` EJECUTA (`executor.start_rollback_async` :267),
  gateado por `_execute_on()` (:248, flag `STACKY_DEPLOYMENTS_EXECUTE_ENABLED`) + `confirm=True`
  (:251) + `confirm_text` si `protected` (:264). **No existe ningún preview.**
- `services/deploy_planner.py:210` — `build_rollback_plan(...)` ya construye el plan de pasos
  (dicts de `_step(name, command, read_only, housekeeping)` :171). Hoy solo lo consume
  `deploy_executor.py:312` DENTRO de la ejecución. **El builder es puro y reutilizable: nadie lo
  expone read-only.**
- `services/deploy_store.py` — `retained_versions(app_id, target, n=10)` (:195),
  `last_success_version` (:186), `is_locked` (:175): todo lo necesario para saber si hay a dónde
  volver, con lecturas locales. **Nadie compone ese "¿puedo volver?" hoy.**
- `frontend/src/components/devops/DeploymentsSection.tsx` — cards por app×target con estado
  (:28-33). **Sin indicador de reversibilidad.**
- Vecinos que NO se pisan: 186 (lint de pipelines), 188 (evidencia de fallos → incidencia),
  178 (drift de ambientes/BD), 120 `/drift` (versión desplegada vs deseada — otra pregunta).

**Gap:** la acción más estresante del Centro (rollback) es la única sin capa de preparación: ni
indicador previo, ni ensayo. Cerrarlo es composición pura de piezas 120 existentes.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** backend Python determinista + UI React, cero
   LLM; idéntico con Codex CLI / Claude Code CLI / GitHub Copilot Pro o sin ninguno.
2. **Cero trabajo extra para el operador:** flag default **ON** (ninguna de las 4 excepciones duras:
   TODO es lectura local — ledger y config de apps; el simulacro NO ejecuta nada, ni siquiera
   comandos `read_only`). El rollback real y sus guardas (:245-269) quedan INTACTOS.
3. **Human-in-the-loop:** este plan NO agrega ninguna ejecución; solo información. El botón que
   ejecuta sigue siendo el existente, con su confirm.
4. **Mono-operador sin auth:** nada de roles.
5. **No degradar:** endpoint nuevo aditivo; `DeploymentsSection` solo suma un badge y un botón; si
   el preview falla, la card queda EXACTAMENTE como hoy (degradación silenciosa).
6. **Reusar, no reinventar:** `build_rollback_plan` (:210), `retained_versions`/`last_success_version`/
   `is_locked` (deploy_store), patrón de guards (:37-39), timeout de smoke
   (`STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC`, `deploy_executor.py:262-264`), CSS modules existentes.
7. **Gotcha config:** instancia de flags = `_config.config` (import `import config as _config`,
   `devops_deployments.py:15`); patrón `_master_on()` :25-26. NUNCA `getattr(config, ...)` sobre el
   módulo.

---

## 4. Fases

### F0 — Flag, esqueleto del servicio y endpoint preview con guards (vertical slice)

**Objetivo:** cablear flag → servicio → `POST /devops/deployments/rollback/preview` (404/400/200).
**Valor:** wiring completo probado; F1/F2 solo rellenan cálculo y simulacro.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- CREAR `Stacky Agents/backend/services/rollback_readiness.py`
- EDITAR `Stacky Agents/backend/api/devops_deployments.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan189_readiness_flag.py`

**Cambios exactos:**

1. `harness_flags.py` — FlagSpec al final del bloque DEVOPS (tras
   `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED` ~:2743; convención R4 profundidad-1, patrón
   `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` :2650-2674):

```python
FlagSpec(
    key="STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED",
    type="bool",
    label="Semáforo de rollback y simulacro",
    description="Muestra por app y destino si hay rollback disponible (y a qué versión) "
                "y permite simular los pasos SIN ejecutar nada. Solo lecturas locales.",
    group="global",
    default=True,
    requires="STACKY_DEVOPS_PANEL_ENABLED",  # R4 profundidad-1 (patrón :2674)
),
```

2. Agregar la key a `_CURATED_DEFAULTS_ON` (~:200-216, comentario
   `# Plan 189 — semáforo de rollback y simulacro`). **Gotcha:** fuera de la lista →
   `test_default_known_only_for_curated` rojo.

3. CREAR `services/rollback_readiness.py`:

```python
"""services/rollback_readiness.py — Plan 189. Reversibilidad como indicador (read-only).

PURO: lecturas locales vía services.deploy_store + builder puro de deploy_planner.
PROHIBIDO importar deploy_executor, remote_exec o requests (ver test_sin_imports_de_ejecucion).
"""
from __future__ import annotations

from services import deploy_store as store
from services import deploy_planner as planner

SCHEMA_VERSION = "189.1"

# códigos EXACTOS de razones de no-readiness (la UI los traduce)
REASON_NO_TARGET_CFG = "sin_target_cfg"
REASON_NO_RETAINED = "sin_versiones_retenidas"
REASON_ONLY_CURRENT = "solo_version_actual"
REASON_RUN_IN_PROGRESS = "run_en_curso"


def compute_rollback_readiness(app_id: str, target: str) -> dict | None:
    """None si la app no existe. F0: shape mínimo {ready: False, reasons: []}; F1 lo completa."""
    ...


def simulate_rollback_plan(app_id: str, target: str, to_version: str,
                           smoke_timeout_s: int) -> dict | None:
    """F2. None si app/target/version inválidos. NUNCA ejecuta: solo construye el plan."""
    ...
```

4. `api/devops_deployments.py` — ruta nueva DESPUÉS de `rollback_route` (:269):

```python
@bp.post("/rollback/preview")
def rollback_preview_route():
    """Semáforo + simulacro read-only. NO exige _execute_on(): acá no se ejecuta nada. Plan 189."""
    _guard_master()  # patrón :37-39
    if not bool(getattr(_config.config, "STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED", False)):
        abort(404)
    body = request.get_json(silent=True) or {}
    app_id, target = body.get("app_id"), body.get("target")
    if not app_id or not target:
        return jsonify({"error": "app_id y target son obligatorios"}), 400
    from services.rollback_readiness import compute_rollback_readiness, simulate_rollback_plan
    readiness = compute_rollback_readiness(app_id, target)
    if readiness is None:
        return jsonify({"error": "app_not_found"}), 404
    plan = None
    to_version = body.get("to_version")
    if to_version:
        plan = simulate_rollback_plan(app_id, target, str(to_version), _smoke_timeout_s())
        if plan is None:
            return jsonify({"error": "version_not_retained"}), 404
    return jsonify({"readiness": readiness, "plan": plan})
```

   (`_smoke_timeout_s()` ya existe en el módulo del executor — **leer `deploy_executor.py:262-264`**:
   si la helper vive en `deploy_executor`, importarla ahí o replicar la línea
   `int(getattr(_config.config, "STACKY_DEPLOYMENTS_SMOKE_TIMEOUT_SEC", 30))` INLINE en la ruta;
   elegir la opción que NO importe `deploy_executor` desde el servicio nuevo.)

5. Edge `STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` en
   `tests/test_harness_flags_requires.py`.

6. `test_plan189_readiness_flag.py` a `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh`
   (**gotcha** meta-test).

**Tests PRIMERO** — `tests/test_plan189_readiness_flag.py`:
- `test_flag_declarada_bool_default_on` (type/default/requires exactos).
- `test_flag_en_curated_defaults_on`.
- `test_preview_404_readiness_off` (master ON, readiness OFF).
- `test_preview_404_master_off`.
- `test_preview_400_payload_incompleto` (sin `target`).
- `test_preview_404_app_inexistente` (store monkeypatcheado: `get_app` → None).
- `test_preview_200_execute_off` — con `STACKY_DEPLOYMENTS_EXECUTE_ENABLED` OFF → 200 igual
  (KPI-2 parcial: el preview NO depende de la flag de ejecución).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan189_readiness_flag.py -q`
(cwd = `Stacky Agents\backend`; SIEMPRE por archivo).

**Criterio binario:** los 7 tests pasan Y `test_harness_ratchet_meta.py` verde.

**Flag:** `STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED` default **ON** (ninguna excepción dura:
lecturas locales, cero ejecución).

**Runtimes:** idéntico en los 3 (sin LLM). Fallback: flag OFF → 404 y la UI no muestra nada.

**Trabajo del operador:** ninguno.

---

### F1 — Readiness real (semáforo con razones tipadas)

**Objetivo:** calcular `ready`/`to_version`/`candidates`/`reasons` con lecturas locales puras.
**Valor:** el "¿puedo volver?" contestado siempre, sin abrir nada.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/rollback_readiness.py`
- CREAR `Stacky Agents/backend/tests/test_plan189_readiness_compute.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Diseño exacto de `compute_rollback_readiness`:**

```python
def compute_rollback_readiness(app_id: str, target: str) -> dict | None:
    app = store.get_app(app_id)              # deploy_store.py:63
    if app is None:
        return None
    cfg = (app.get("targets") or {}).get(target)
    reasons: list[str] = []
    if cfg is None:
        reasons.append(REASON_NO_TARGET_CFG)
    current = store.last_success_version(app_id, target)      # :186
    retained = store.retained_versions(app_id, target, n=10)  # :195 — LEER esa función antes:
                                                              # respetar su orden tal cual (no re-ordenar)
    candidates = [v for v in retained if v != current]
    if not retained:
        reasons.append(REASON_NO_RETAINED)
    elif not candidates:
        reasons.append(REASON_ONLY_CURRENT)
    if store.is_locked(app_id, target):                       # :175
        reasons.append(REASON_RUN_IN_PROGRESS)
    return {
        "schema_version": SCHEMA_VERSION,
        "ready": not reasons,
        "to_version": candidates[0] if candidates else None,  # la más reciente ≠ actual
        "candidates": candidates,
        "current_version": current,
        "protected": bool(cfg.get("protected")) if cfg else False,
        "locked": store.is_locked(app_id, target),
        "reasons": reasons,
    }
```

Notas duras:
- `to_version` = primer candidato en el ORDEN que devuelve `retained_versions` (leer
  `deploy_store.py:195` y NO re-ordenar: ese orden ya refleja la retención del plan 120).
- `protected: True` NO baja `ready` — solo avisa a la UI que el rollback real pedirá
  `confirm_text` (patrón :264).
- Cero red, cero `remote_exec`.

**Tests PRIMERO** — `tests/test_plan189_readiness_compute.py` (deploy_store monkeypatcheado en
memoria; 5 escenarios golden = KPI-1):
- `test_ready_con_candidatas` — retained `["v3","v2","v1"]`, current `"v3"` → `ready True`,
  `to_version "v2"`, `candidates ["v2","v1"]`, `reasons []`.
- `test_sin_retenidas` — retained `[]` → `ready False`, reasons `["sin_versiones_retenidas"]`.
- `test_solo_version_actual` — retained `["v3"]`, current `"v3"` → reasons `["solo_version_actual"]`.
- `test_target_sin_cfg` — cfg ausente → reason `"sin_target_cfg"` presente y `ready False`.
- `test_run_en_curso` — `is_locked` True → reason `"run_en_curso"` y `ready False`.
- `test_none_si_app_inexistente`.
- `test_protected_no_baja_ready` — cfg `{"protected": True}` + candidatas → `ready True` y
  `protected True`.
- `test_sin_imports_de_ejecucion` — el SOURCE de `services/rollback_readiness.py` no contiene
  `"deploy_executor"`, `"remote_exec"` ni `"import requests"`.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan189_readiness_compute.py -q`

**Criterio binario:** los 8 tests pasan (KPI-1 completo).

**Flag:** la de F0. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F2 — Simulacro read-only (mismos pasos que el rollback real)

**Objetivo:** exponer el plan EXACTO de pasos del rollback sin ejecutar nada.
**Valor:** ensayo sin riesgo; el operador ve comando por comando qué pasaría.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/rollback_readiness.py`
- CREAR `Stacky Agents/backend/tests/test_plan189_simulacro.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Diseño exacto de `simulate_rollback_plan`:**

```python
def simulate_rollback_plan(app_id: str, target: str, to_version: str,
                           smoke_timeout_s: int) -> dict | None:
    app = store.get_app(app_id)
    if app is None:
        return None
    cfg = (app.get("targets") or {}).get(target)
    if cfg is None:
        return None
    retained = store.retained_versions(app_id, target, n=10)
    if to_version not in retained:
        return None                      # el endpoint lo traduce a 404 version_not_retained
    # LEER deploy_planner.py:210 y deploy_executor.py:312 ANTES: llamar build_rollback_plan
    # con EXACTAMENTE la misma forma de argumentos que usa el executor real.
    steps = planner.build_rollback_plan(app, target, cfg, to_version, smoke_timeout_s)
    return {
        "schema_version": SCHEMA_VERSION,
        "to_version": to_version,
        "smoke_timeout_s": smoke_timeout_s,
        "steps": steps,                  # dicts _step: {name, command, read_only, housekeeping}
        "simulated": True,               # SIEMPRE True — marca inequívoca de que NADA se ejecutó
    }
```

Notas duras:
- Si la firma real de `build_rollback_plan` (:210) difiere (p.ej. devuelve dict y no lista, o
  recibe kwargs), ESPEJAR la llamada de `deploy_executor.py:312` argumento por argumento — esa
  llamada es la fuente de verdad de KPI-3.
- Los `command` de los steps se construyen SOLO con `install_path`/`version_id`
  (`build_switch_commands` :89, `_reject_embedded_quotes` :83): no llevan credenciales, van tal
  cual al preview.

**Tests PRIMERO** — `tests/test_plan189_simulacro.py` (store y planner reales con fixture app en
memoria vía monkeypatch de `_load_apps`/ledger, o store monkeypatcheado — elegir lo que ya haga
`tests/test_plan120_*` con el Centro; leer UN test existente del 120 y espejar el estilo de fixture):
- `test_kpi3_paridad_steps` — `simulate_rollback_plan(...)["steps"] ==
  planner.build_rollback_plan(app, target, cfg, to_version, 30)` (comparación `==` literal).
- `test_none_version_no_retenida` → endpoint 404 `version_not_retained` (test de API con client).
- `test_kpi2_cero_ejecucion` — monkeypatch `deploy_executor.LocalTransport.run` y
  `remote_exec.run_deploy_step` a `raise AssertionError("ejecución prohibida")`; llamar al endpoint
  completo (readiness + plan) → 200 sin excepción.
- `test_simulated_true_siempre`.
- `test_steps_shape` — cada step tiene EXACTAMENTE las keys `{name, command, read_only,
  housekeeping}` (o las que `_step` :171 produzca — assert contra `_step("x", "cmd")` real).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan189_simulacro.py -q`

**Criterio binario:** los 5 tests pasan (KPI-2 y KPI-3 completos).

**Flag:** la de F0. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — UI: badge de reversibilidad + modal de simulacro

**Objetivo:** semáforo visible en cada card app×target y ensayo en un click.
**Valor:** la reversibilidad deja de ser una incógnita; cero fricción nueva.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/devops/rollbackReadiness.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/devops/rollbackReadiness.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/devops/DeploymentsSection.tsx`

**Comportamiento exacto:**

1. `rollbackReadiness.ts` (puro):

```typescript
export interface Readiness {
  ready: boolean; to_version: string | null; candidates: string[];
  current_version: string | null; protected: boolean; locked: boolean; reasons: string[];
}
export const REASON_LABELS: Record<string, string> = {
  sin_target_cfg: 'destino sin configurar',
  sin_versiones_retenidas: 'no hay versiones retenidas',
  solo_version_actual: 'solo está retenida la versión actual',
  run_en_curso: 'hay un run en curso',
};
export function readinessBadge(r: Readiness | undefined): { tone: 'ok'|'off'|'none'; text: string; title: string } {
  if (!r) return { tone: 'none', text: '', title: '' };
  if (r.ready) return { tone: 'ok', text: `↩ Rollback listo → ${r.to_version}`,
                        title: r.protected ? 'Destino protegido: pedirá confirmación extra' : '' };
  const motivos = r.reasons.map((x) => REASON_LABELS[x] ?? x).join('; ');
  return { tone: 'off', text: '↩ Sin rollback disponible', title: motivos };
}
export function stepRows(plan: { steps: Array<{name: string; command: string; read_only?: boolean; housekeeping?: boolean}> } | null):
  Array<{ name: string; command: string; tags: string[] }> {
  if (!plan) return [];
  return plan.steps.map((s) => ({
    name: s.name, command: s.command,
    tags: [s.read_only ? 'solo lectura' : '', s.housekeeping ? 'housekeeping' : ''].filter(Boolean),
  }));
}
```

2. `DeploymentsSection.tsx`:
   - Al cargar el overview (fetch existente), disparar EN PARALELO un
     `POST /api/devops/deployments/rollback/preview` con `{app_id, target}` por cada card visible
     (`Promise.all`; los datos son lecturas locales, responden en ms) y guardar
     `readinessMap[appId + '|' + target]`. Si CUALQUIER request falla o da 404 (flag OFF) →
     `readinessMap` queda sin esa key y la card se ve EXACTAMENTE como hoy (degradación silenciosa;
     además, ante el PRIMER 404 no reintentar en la sesión).
   - Render del badge con `readinessBadge(...)` junto al estado existente de la card (clases del
     CSS module; **gotcha ratchet:** cero `style={{}}`).
   - Botón `"Simular rollback…"` SOLO si `ready`: re-llama al preview con
     `to_version = readiness.to_version` y muestra un panel/modal read-only: banda superior
     "Simulacro — nada se ejecutó ni se va a ejecutar", lista de `stepRows` (nombre + `<code>` con
     el comando + tags), y botón único "Cerrar". El botón REAL de rollback existente NO se toca ni
     se mueve.

**Tests PRIMERO** — `rollbackReadiness.test.ts` (vitest, **sin @testing-library** — gap conocido;
espejar `RemediationCard.test.tsx`):
- `readinessBadge(undefined)` → tone `none`.
- ready → tone `ok`, texto con la versión; protected → title con "protegido".
- no-ready → tone `off`, title junta los motivos traducidos (y deja crudo un reason desconocido).
- `stepRows` — mapea tags según read_only/housekeeping; `null` → `[]`.

**Comando:** `npx vitest run src/components/devops/rollbackReadiness.test.ts`
(cwd = `Stacky Agents\frontend`; por archivo).

**Criterio binario:** los 4 tests pasan Y `npx tsc --noEmit` sin errores nuevos (KPI-4).

**Flag:** la de F0 (404 → sin badge, cero diferencia visual). **Runtimes:** UI pura.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| El preview ejecuta algo por accidente (peor caso) | El servicio tiene PROHIBIDO importar executor/remote_exec (test de source F1) + KPI-2 con transportes monkeypatcheados a `raise` |
| Divergencia simulacro vs rollback real | KPI-3: mismos steps por `==` contra `build_rollback_plan` directo; la llamada espeja `deploy_executor.py:312` argumento por argumento |
| `retained_versions` con semántica distinta a la asumida | Instrucción explícita de LEER `deploy_store.py:195` antes; el orden NO se re-ordena; tests con fixture propio no dependen del orden real de disco |
| N requests de preview al cargar la sección | Lecturas locales en ms + `Promise.all`; ante el primer 404 no se reintenta en la sesión; si falla, cero cambio visual |
| Sesión paralela toca `devops_deployments.py` (177-188 activa) | Ruta ADITIVA tras `/rollback` (:269); tras merge `python -m compileall` + grep de duplicado silencioso (gotcha conocido) |
| Confusión simulacro vs ejecución real | Campo `simulated: True` en el contrato + banda fija "nada se ejecutó" + el modal NO tiene botón de ejecutar |

## 6. Fuera de scope (explícito)

- Ejecutar el rollback desde el modal del simulacro (el flujo real existente :245-269 queda único).
- Chequeo de espacio en disco del destino (`check_disk_headroom` :294 requiere consulta remota).
- Verificación remota de que los artefactos retenidos EXISTEN físicamente en el destino (remoto).
- Readiness para deploys de pipelines CI (esto es del Centro de Despliegues 120, no del monitor 103).
- Notificaciones proactivas cuando un target pierde reversibilidad (v2; requeriría centro 152).

## 7. Glosario (para modelos menores)

- **Centro de Despliegues (120):** apps × targets (local/servidores 91) con ledger de runs;
  `api/devops_deployments.py` + `services/deploy_store.py` + `deploy_planner`/`deploy_executor`.
- **Versión retenida:** versión anterior conservada en el destino tras un deploy exitoso
  (`retained_versions`, `deploy_store.py:195`); es a dónde se puede volver.
- **`protected`:** marca del target que exige `confirm_text == app_id` para ejecutar (:264).
- **`is_locked`:** hay un run de deploy/rollback en curso para ese app×target (:175).
- **Step `_step`:** dict `{name, command, read_only, housekeeping}` (`deploy_planner.py:171`).
- **Simulacro:** construir y MOSTRAR los steps sin pasarlos por ningún transporte de ejecución.
- **HITL / `_CURATED_DEFAULTS_ON` / HARNESS_TEST_FILES / ratchet UI:** ver planes 186-188 (mismas
  convenciones: flags ON curadas, registro de tests del arnés, cero estilos inline en .tsx nuevos).

## 8. Orden de implementación

1. F0 — flag + esqueleto + endpoint preview con guards + 7 tests de wiring.
2. F1 — readiness real + 8 tests (KPI-1).
3. F2 — simulacro + 5 tests (KPI-2, KPI-3).
4. F3 — badge + modal simulacro + 4 tests vitest + `tsc` (KPI-4).

Cada fase se commitea sola con sus tests verdes ANTES de la siguiente (TDD estricto, cero falsos
verdes).

## 9. Definición de Hecho (DoD) global

- [ ] Los 4 archivos de test (`test_plan189_readiness_flag.py`, `test_plan189_readiness_compute.py`,
      `test_plan189_simulacro.py`, `rollbackReadiness.test.ts`) pasan POR ARCHIVO con el intérprete
      correcto.
- [ ] `test_harness_ratchet_meta.py`, `test_harness_flags_requires.py` y
      `test_default_known_only_for_curated` siguen verdes.
- [ ] KPI-1..KPI-4 verificados por los tests nombrados.
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio.
- [ ] Flag `STACKY_DEVOPS_ROLLBACK_READINESS_ENABLED` visible/toggleable en la UI de flags, default ON.
- [ ] Con la flag OFF: cero diferencias observables vs. hoy (404 + sin badge + sin botón).
- [ ] `/rollback` real (:245-269) intacto byte a byte.
- [ ] `services/rollback_readiness.py` sin imports de ejecución (test de source lo prueba).
