# Flujo QA UAT Agent — Etapas, componentes y llamadas LLM

## Dos sistemas QA distintos

Stacky tiene dos sistemas QA que no deben confundirse:

| Sistema | Qué hace | LLM |
|---|---|---|
| **QA Agent** (workbench Flask) | Análisis textual de evidencia → veredicto PASS/FAIL | 1 llamada al invocar desde el workbench |
| **QA UAT Agent** (este pipeline) | Browser real (Playwright) → evidencia forense → dossier | 4 llamadas distribuidas en etapas |

---

## Sistema A — QA Agent (workbench)

Una sola llamada LLM cuando el operador hace click en Run desde el workbench de Stacky:

```
Operador hace click Run
    → agent_runner construye prompt (system + context_blocks)
    → copilot_bridge.invoke()          ← única llamada LLM
        ├─ backend="vscode_bridge" → Extension de Stacky en puerto 5052
        ├─ backend="copilot_direct" → POST a models.github.ai/inference
        └─ backend="mock" → respuesta canned (para tests)
    → output = texto PASS/FAIL con veredicto
```

**VS Code Copilot Chat NO participa directamente.** `copilot_bridge.py` llama la API REST
via el bridge local (o directamente). Es una llamada HTTP desde Python.

---

## Sistema B — QA UAT Agent (pipeline Playwright)

Pipeline de stages con browser real. El orquestador es `qa_uat_pipeline.py`.

```bash
python qa_uat_pipeline.py --ticket 70 [--mode dry-run|publish]
python qa_uat_pipeline.py --intent-file evidence/run/intent_spec.json  # free-form
```

---

## Preflight y smoke path

Antes de ejecutar cualquier stage, el pipeline corre dos checks en serie:

### Preflight (`environment_preflight.py`)

Verifica que la Agenda Web esté activa. Si no responde → BLOCKED inmediato.

```python
preflight = run_environment_preflight()
if not preflight.ok:
    return {"verdict": "BLOCKED", "reason": preflight.reason}
```

### Smoke path (`smoke_path_checker.py`)

Verifica en ≤20s que la app responde, el archivo de auth existe, y la pantalla target
es accesible. Si falla → BLOCKED sin abrir browser.

```bash
QA_UAT_SKIP_SMOKE=true  # para saltar (no recomendado)
```

---

## Stage 1 — reader (`uat_ticket_reader.py`)

**Qué hace:** Lee el ticket ADO, normaliza el HTML y extrae:
- Análisis técnico (sección con emoji 🔬)
- Plan de pruebas funcional
- Evidencia del Developer

**Llamadas externas:** `ado.py` → ADO REST API  
**LLM:** ❌ NO — parsing regex/HTML determinístico  
**Output:** `evidence/{ticket_id}/ticket.json`

En **modo free-form**, este stage es reemplazado por:
1. `intent_parser.py` — parsea `intent_spec.json`
2. `synthetic_ticket_builder.py` — genera `ticket.json` desde el intent spec
3. `data_resolver.py` — resuelve placeholders via BD dev (SELECT only)

---

## Stage 2 — ui_map (`ui_map_builder.py`)

**Qué hace:** Inspecciona el DOM y construye un mapa de selectores (inputs, botones,
panels, selects, links) identificados por nombre semántico.

**Guardrail**: `QA_UAT_ALLOW_UI_DISCOVERY=false` (default) → solo usa cache existente.
Si no hay cache para una pantalla → BLOCKED.

**Llamadas externas:** Playwright (Chromium) contra la app web  
**LLM:** ❌ NO — análisis DOM determinístico  
**Output:** `cache/ui_maps/{pantalla}.json`

---

## Stage 3 — compiler (`uat_scenario_compiler.py`)

**Qué hace:** Convierte cada ítem del plan de pruebas en un scenario JSON estructurado
con pasos (`accion`, `target`, `valor`) y oráculos (`tipo`, `target`, `valor`).

**LLM:** ✅ SÍ — `gpt-4.1-mini`  
**Cuándo:** por cada ítem del plan de pruebas  
**Fallback:** heurísticas regex si el LLM falla  
**Output:** `evidence/{ticket_id}/scenarios.json`

Pantallas soportadas: el catálogo de `agenda_screens.py` (~90 pantallas). El system prompt
es **dinámico** — lee `SUPPORTED_SCREENS` para no tener pantallas hardcodeadas.

---

## Stage 3b — preconditions (`uat_precondition_checker.py`)

**Qué hace:** Verifica en BD dev que los datos requeridos por los escenarios existan
(INSERTs RIDIOMA aplicados, registros de referencia presentes).

**Llamadas externas:** BD dev (pyodbc/sqlcmd) — solo SELECT  
**LLM:** ❌ NO  
**Fatal:** ❌ NO — si BD no disponible, warning + continúa

---

## Stage 4 — generator (`playwright_test_generator.py`)

**Qué hace:** Genera archivos TypeScript de Playwright desde `scenarios.json`.
Renderizado Jinja2 determinístico.

**LLM:** ❌ NO  
**Output:** `evidence/{ticket_id}/tests/*.spec.ts`

Si todos los scenarios quedan BLOCKED (selectores faltantes), el pipeline salta
runner/evaluator/failure_analyzer y va directo al dossier con veredicto BLOCKED.

---

## Stage 4b — spec_linter (`spec_linter.py`)

**Qué hace:** Valida cada `.spec.ts` generado ANTES de abrir el browser.
Detecta: login hardcodeado, credenciales en el código, acciones prohibidas.

**LLM:** ❌ NO  
**Fatal:** ✅ SÍ — si encuentra violations, BLOCK inmediato

---

## Stage 5 — runner (`uat_test_runner.py`)

**Qué hace:** Ejecuta cada `.spec.ts` con `npx playwright test`, captura screenshots
y devuelve `runner_output.json`.

**Instrumentación forense (Fase 3):**
- `playwright/forensic_logger.ts` escribe JSONL desde el proceso TypeScript:
  - `actions.jsonl` — cada acción con intent+result+duration
  - `network.jsonl` — requests (sin recursos image/font/media)
  - `console.jsonl` — mensajes de consola (solo WARNING/ERROR)
  - `screenshots.jsonl` — metadata con SHA256 y size
- `playwright_forensic_bridge.py` importa esos JSONL → `ForensicEventLogger` Python

**Guardrail de runtime:**
```
QA_UAT_MAX_TOTAL_MINUTES=6   (default — 3× el flujo humano esperado de 2min)
QA_UAT_MAX_BROWSER_LAUNCHES=1
QA_UAT_MAX_LOGIN_ATTEMPTS=1
```

**LLM:** ❌ NO  
**Output:** `evidence/{ticket_id}/runner_output.json` + capturas PNG

**Replanning (Fase 9, opcional):**  
Si `--replan` → `replan_engine.py` ejecuta hasta N rondas:
1. Analiza failures → `no_action` / `retry` / `escalate`
2. Si `retry`: parchea intent_spec, re-genera specs, re-ejecuta runner

---

## Stage 5b — annotator (`screenshot_annotator.py`)

**Qué hace:** Agrega box rojo en screenshots señalando el elemento bajo prueba.
Usa Pillow. Lee `step_bboxes.json` generado por las specs.

**LLM:** ❌ NO  
**Fatal:** ❌ NO — non-fatal, el pipeline continúa aunque falle

---

## Stage 6 — evaluator (`uat_assertion_evaluator.py`)

**Qué hace:** Evalúa los oráculos de cada scenario contra el DOM/resultado capturado.
Determina PASS / FAIL / BLOCKED / REVIEW por scenario.

**LLM:** ❌ NO — comparación determinística  
**Output:** `evidence/{ticket_id}/evaluations.json`

---

## Stage 7 — failure_analyzer (`uat_failure_analyzer.py`)

**Qué hace:** Para cada scenario con FAIL, clasifica la causa y genera hipótesis.

**Categorías:** `selector_not_found` / `text_not_present` / `timeout` /
`regression` / `precondition_not_met` / `environment_error` / `unknown`

**LLM:** ✅ SÍ — `gpt-4.1` (solo si hay FAILs, solo si la heurística no resuelve)  
**Fallback:** `category=unknown, confidence=low`  
**Output:** `evidence/{ticket_id}/failure_analysis.json`

---

## Stage 8 — dossier (`uat_dossier_builder.py`)

**Qué hace:** Arma el dossier final con resumen ejecutivo, tabla de casos, capturas
y recomendaciones para el QA humano.

**LLM:** ✅ SÍ — `gpt-4.1` — **2 llamadas:**
1. `executive_summary` — resumen ejecutivo del resultado
2. `recommendations` — recomendaciones para el QA humano

**Fallback:** template string fijo si el LLM falla  
**Output:** `evidence/{ticket_id}/dossier.html` + `dossier.md` + `dossier.json`

---

## Stage 9 — publisher (`ado_evidence_publisher.py`)

**Qué hace:** En modo `publish`, postea el dossier como comentario en el ticket ADO.
En modo `dry-run` (default), solo genera los archivos sin publicar.

**Llamadas externas:** `ado.py` → ADO REST API (POST comentario, idempotente por hash)  
**LLM:** ❌ NO  
**Seguridad:** nunca cambia el estado del ticket — solo agrega comentario

---

## Instrumentación forense transversal (Fases 1–4)

Todo el pipeline emite eventos forenses via `ForensicEventLogger`:

```
forensic_event_logger.emit(
    stage="runner",
    event_type="playwright.action",
    actor="playwright",
    target="btn_guardar",
    status="ok",
    ...
)
```

**Persistencia:** `EventStore` escribe en paralelo en:
- `events.sqlite` (WAL mode — fuente de verdad)
- `events.jsonl` (append-only — backup)

**Human Unlock (Fase 4):**  
Cuando un stage no puede continuar sin intervención humana:
```python
unlock = HumanUnlock(run_id, run_dir, forensic_log)
blocker_id = unlock.block(stage="runner", reason="Selector no encontrado",
                          question="¿El elemento existe en producción?")
# El operador responde via CLI:
python qa_uat_pipeline.py --ticket N --run-id RUN_ID --resolve-blocker ID --answer "no"
```

**Learning governance (Fase 4):**  
`LearningCandidateGenerator.generate()` analiza los eventos post-run y propone learnings.
Los learnings requieren **aprobación explícita humana** antes de ser aplicados:
- `learning_store.add_candidate(...)` → status `candidate`
- Humano aprueba: `learning_store.approve(learning_id, reviewed_by)`
- Solo entonces pueden ser aplicados en runs futuros

---

## Resumen: cuándo actúa el LLM

| Stage | LLM | Modelo | Propósito | Fallback |
|---|---|---|---|---|
| compiler | ✅ | gpt-4.1-mini | Plan de pruebas → ScenarioSpecs | regex heurísticas |
| failure_analyzer | ✅ (solo si hay FAILs) | gpt-4.1 | Clasifica causa + hipótesis | `unknown` |
| dossier | ✅ | gpt-4.1 | Resumen ejecutivo + recomendaciones | template fijo |
| intent_inferrer | ✅ (free-form) | gpt-4.1-mini | Texto libre → intent_spec | — |
| QA Agent workbench | ✅ | configurable | Veredicto PASS/FAIL textual | — |
| Todas las demás | ❌ | — | — | — |

---

## Routing del LLM (`llm_client.py`)

```
STACKY_LLM_BACKEND=vscode_bridge  (default)
    → ¿está 127.0.0.1:5052 activo?
        → SÍ  → llama a la Extension de Stacky (bridge local)
        → NO  → fallback a copilot_direct

STACKY_LLM_BACKEND=copilot_direct
    → POST directo a models.github.ai/inference con gh auth token

STACKY_LLM_BACKEND=mock
    → respuesta hardcodeada (para tests)
```

---

## Comandos analíticos y de observabilidad (Fase 4)

Estos comandos no requieren que la Agenda Web esté activa. Operan solo sobre datos persistidos.

### Analytics + KPIs

```bash
python qa_uat_pipeline.py --analytics-report
# → {"ok": true, "kpis": {...}, "report": {...}}
```

KPIs calculados por `kpi_builder.py`:
- KPI-01: Pass Rate ≥ 80% = green
- KPI-02: Duración promedio ≤ 120s = green
- KPI-03: Resolución de blockers ≥ 90% = green
- KPI-04: Assertions PASS ≥ 85% = green
- KPI-05: Adopción de learnings ≥ 50% = green
- KPI-06: Runs ejecutados (conteo)

### Replay forense

```bash
python qa_uat_pipeline.py --ticket 70 --replay-run uat-70-20260508-153012
# Reconstruye la timeline del run desde events.jsonl
# NO re-ejecuta Playwright
```

### Observabilidad

```bash
python qa_uat_pipeline.py --ticket 70 --validate-observability
# Valida 8 capas: event_policy, data_contracts, run_manifest,
# checkpoints, artifacts, playwright, blockers, metrics
# Veredicto: PASS (8/8) | PARTIAL (≥6/8) | FAIL (<6/8)
```

### Blockers

```bash
python qa_uat_pipeline.py --ticket 70 --list-blockers RUN_ID
python qa_uat_pipeline.py --ticket 70 --run-id RUN_ID --resolve-blocker ID --answer "respuesta"
```

---

## Diagrama de flujo completo

```
CLI
 │
 ├── --analytics-report → _cmd_analytics_report() → exit
 ├── --replay-run       → _cmd_replay_run()       → exit
 ├── --validate-obs.    → _cmd_validate_obs()      → exit
 ├── --list-blockers    → _cmd_list_blockers()     → exit
 ├── --resolve-blocker  → _cmd_resolve_blocker()   → exit
 │
 └── --ticket N (ADO mode)
      │
      ├─ environment_preflight         [¿app activa?]
      ├─ smoke_path_checker            [¿app accesible?]
      │
      ├─ Stage 1: reader               [ticket.json]
      ├─ Stage 2: ui_map               [ui_maps/*.json]
      ├─ Stage 3: compiler         LLM [scenarios.json]
      ├─ Stage 3b: preconditions       [BD dev SELECT]
      ├─ Stage 4: generator            [tests/*.spec.ts]
      ├─ Stage 4b: spec_linter         [valida specs]
      ├─ Stage 5: runner               [runner_output.json]
      │    ├─ forensic_logger.ts       [actions/network/console/screenshots JSONL]
      │    └─ playwright_forensic_bridge.py [→ ForensicEventLogger]
      │    └─ [opcional] replan_engine replan_loop
      ├─ Stage 5b: annotator           [screenshots anotados]
      ├─ Stage 6: evaluator            [evaluations.json]
      ├─ Stage 7: failure_analyzer LLM [failure_analysis.json]
      ├─ Stage 8: dossier          LLM [dossier.html+md+json]
      └─ Stage 9: publisher            [ADO comment o dry-run]
```
