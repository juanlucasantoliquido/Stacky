# QA UAT Agent

> Pipeline de QA automatizado con Playwright para la Agenda Web Pacífico. Convierte tickets ADO en suites de pruebas ejecutables con evidencia forense completa.

---

## Estado actual — Mayo 2026

| Fase | Descripción | Estado |
|---|---|---|
| Fase 1 | Event Store, persistencia, schemas, contratos de datos | ✅ completa — 22/22 smoke |
| Fase 2 | Logging de comandos, PowerShell, filesystem, pipeline stage | ✅ completa — 31/31 smoke |
| Fase 3 | Instrumentación Playwright forense (TypeScript bridge) | ✅ completa — 22/22 smoke |
| Fase 4 | Human Unlock, learning governance, métricas, analytics, replay | ✅ completa — 47/47 smoke |

---

## Instalación rápida

```bash
# 1. Dependencias Python
pip install -r requirements.txt

# 2. Dependencias Node.js (Playwright)
npm install
npx playwright install chromium

# 3. Variables de entorno obligatorias
$env:AGENDA_WEB_USER    = "pablo"
$env:AGENDA_WEB_PASS    = "tu_password"
$env:AGENDA_WEB_BASE_URL = "http://localhost:35017/AgendaWeb/"  # default

# 4. La Agenda Web DEBE estar corriendo antes de ejecutar.
#    QA UAT Agent NUNCA inicia/detiene IIS Express.
```

---

## Uso

### Modo ADO (ticket real)

```bash
python qa_uat_pipeline.py --ticket 70
python qa_uat_pipeline.py --ticket 70 --mode publish     # publica dossier en ADO
python qa_uat_pipeline.py --ticket 70 --headed           # browser visible
python qa_uat_pipeline.py --ticket 70 --skip-to runner   # reutiliza cache
python qa_uat_pipeline.py --ticket 70 --replan           # replanning automático (Fase 9)
```

### Modo free-form (sin ticket ADO)

```bash
python qa_uat_pipeline.py --intent-file evidence/mi_run/intent_spec.json
# Con datos pendientes:
python qa_uat_pipeline.py --intent-file ... --resume --data-file resolved_data.json
# Auto-resolución via BD:
python qa_uat_pipeline.py --intent-file ... --auto-resolve
```

### Comandos analíticos / forenses (Fase 4)

```bash
# KPIs + analytics (últimos 7 días)
python qa_uat_pipeline.py --analytics-report
python qa_uat_pipeline.py --analytics-report --days 30

# Replay forense (sin re-ejecutar Playwright)
python qa_uat_pipeline.py --ticket 70 --replay-run uat-70-20260508-153012

# Observabilidad forense
python qa_uat_pipeline.py --ticket 70 --validate-observability

# Blockers
python qa_uat_pipeline.py --ticket 70 --list-blockers uat-70-20260508-153012
python qa_uat_pipeline.py --ticket 70 --run-id uat-70-20260508-153012 \
    --resolve-blocker blk-abc123 --answer "si"
```

### Flags completos

| Flag | Default | Descripción |
|---|---|---|
| `--ticket N` | — | ID del ticket ADO |
| `--intent-file PATH` | — | Archivo de intención (free-form) |
| `--mode dry-run\|publish` | `dry-run` | `publish` escribe en ADO |
| `--headed` | false | Browser en modo visible |
| `--timeout-ms N` | 90000 | Timeout por step Playwright |
| `--skip-to STAGE` | — | Salta stages anteriores (cache) |
| `--resume` | false | Retoma run pausado (PENDING_DATA) |
| `--data-file PATH` | — | Datos resueltos para `--resume` |
| `--replan` | false | Replanning automático |
| `--auto-resolve` | false | Resuelve datos pendientes via BD |
| `--ado-path PATH` | auto | Ruta alternativa al binario `ado.py` |
| `--background` | false | Solo WARNING a stderr |
| `--analytics-report` | — | Reporte KPIs + analytics |
| `--days N` | 7 | Período para `--analytics-report` |
| `--replay-run RUN_ID` | — | Replay forense (requiere `--ticket`) |
| `--validate-observability` | — | Validación 8-capas (requiere `--ticket`) |
| `--list-blockers RUN_ID` | — | Lista blockers (requiere `--ticket`) |
| `--resolve-blocker ID` | — | Resuelve blocker (requiere `--ticket --run-id --answer`) |
| `--run-id RUN_ID` | — | Run ID para `--resolve-blocker` |
| `--answer TEXT` | — | Respuesta para `--resolve-blocker` |

---

## Arquitectura del pipeline

```
qa_uat_pipeline.py
│
├─ Stage 1:  reader           → uat_ticket_reader.py
├─ Stage 2:  ui_map           → ui_map_builder.py
├─ Stage 3:  compiler         → uat_scenario_compiler.py  (LLM)
├─ Stage 3b: preconditions    → uat_precondition_checker.py
├─ Stage 4:  generator        → playwright_test_generator.py
├─ Stage 4b: spec_linter      → spec_linter.py
├─ Stage 5:  runner           → uat_test_runner.py
│               └─ playwright/forensic_logger.ts + instrumented_actions.ts
├─ Stage 5b: annotator        → screenshot_annotator.py
├─ Stage 6:  evaluator        → uat_assertion_evaluator.py
├─ Stage 7:  failure_analyzer → uat_failure_analyzer.py  (LLM, solo si hay FAILs)
├─ Stage 8:  dossier          → uat_dossier_builder.py   (LLM)
└─ Stage 9:  publisher        → ado_evidence_publisher.py
```

Salida JSON del pipeline:

```json
{
  "ok": true,
  "ticket_id": 70,
  "verdict": "PASS|FAIL|BLOCKED|MIXED",
  "stages": {
    "reader":          {"ok": true, "skipped": false, "plan_item_count": 7},
    "ui_map":          {"ok": true, "skipped": false, "screens": ["FrmAgenda.aspx"]},
    "compiler":        {"ok": true, "skipped": false, "scenario_count": 6},
    "preconditions":   {"ok": true, "skipped": false, "total": 3, "ok_count": 3},
    "generator":       {"ok": true, "skipped": false, "generated": 5, "blocked": 1},
    "spec_linter":     {"ok": true, "skipped": false, "checked": 5},
    "runner":          {"ok": true, "skipped": false, "pass": 4, "fail": 1, "blocked": 1},
    "annotator":       {"ok": true, "skipped": false, "annotated": 3},
    "evaluator":       {"ok": true, "skipped": false, "pass": 4, "fail": 1},
    "failure_analyzer":{"ok": true, "skipped": false, "analyzed": 1},
    "dossier":         {"ok": true, "skipped": false, "verdict": "MIXED"},
    "publisher":       {"ok": true, "skipped": false, "publish_state": "dry-run"}
  },
  "elapsed_s": 45.2
}
```

### Guardrails de seguridad

| Guardrail | Default | Variable de entorno |
|---|---|---|
| Tiempo total máximo | 6 min | `QA_UAT_MAX_TOTAL_MINUTES` |
| Intentos de login | 1 | `QA_UAT_MAX_LOGIN_ATTEMPTS` |
| Lanzamientos de browser | 1 | `QA_UAT_MAX_BROWSER_LAUNCHES` |
| UI discovery automático | deshabilitado | `QA_UAT_ALLOW_UI_DISCOVERY=true` |
| Require playbook | habilitado | `QA_UAT_REQUIRE_PLAYBOOK=false` |
| LLM navigation | deshabilitado | `QA_UAT_ALLOW_LLM_NAVIGATION=true` |

---

## Estructura de archivos

```
QA UAT Agent/
│
├── qa_uat_pipeline.py              ← Orquestador CLI principal
│
├── ── Pipeline core ─────────────────────────────────────────────────────────
├── uat_ticket_reader.py            ← Stage 1: Lee ticket ADO → JSON normalizado
├── ui_map_builder.py               ← Stage 2: Inspecciona DOM → selectores semánticos
├── selector_discovery.py           ← Helper: elige el selector más robusto
├── uat_scenario_compiler.py        ← Stage 3: Plan de pruebas → ScenarioSpecs (LLM)
├── uat_precondition_checker.py     ← Stage 3b: Verifica datos en BD dev (SELECT only)
├── playwright_test_generator.py    ← Stage 4: Genera .spec.ts (Jinja2)
├── spec_linter.py                  ← Stage 4b: Valida .spec.ts generados
├── uat_test_runner.py              ← Stage 5: Ejecuta specs + evidencia
├── screenshot_annotator.py         ← Stage 5b: Anota screenshots (Pillow)
├── uat_assertion_evaluator.py      ← Stage 6: Evalúa oráculos → PASS/FAIL/BLOCKED
├── uat_failure_analyzer.py         ← Stage 7: Clasifica FAILs + hipótesis (LLM)
├── uat_dossier_builder.py          ← Stage 8: Arma dossier HTML+MD (LLM)
├── ado_evidence_publisher.py       ← Stage 9: Publica dossier en ADO (idempotente)
│
├── ── Free-form mode ────────────────────────────────────────────────────────
├── intent_parser.py                ← Parsea intent_spec.json + valida placeholders
├── synthetic_ticket_builder.py     ← Construye ticket.json desde intent_spec
├── data_resolver.py                ← Resuelve placeholders via BD (SELECT only)
│
├── ── Instrumentación forense (Fase 1–4) ────────────────────────────────────
├── event_schema.py                 ← Schema universal de eventos v1.0
├── event_store.py                  ← Persistencia dual: SQLite (WAL) + JSONL
├── forensic_event_logger.py        ← Logger forense canónico
├── run_manifest.py                 ← run_manifest.json + run_state.json por run
├── checkpoint_manager.py           ← Checkpoints por stage
├── artifact_registry.py            ← Registry de artefactos con SHA256
├── event_policy.py                 ← 10 checks de trazabilidad por run
├── data_contracts.py               ← 16 contratos de calidad (DC-01..DC-16)
├── redactor.py                     ← Redacción de secretos en todos los logs
│
├── ── Logging de comandos (Fase 2) ──────────────────────────────────────────
├── command_runner.py               ← Wrapper forense para subprocess
├── powershell_logger.py            ← PowerShell con Start-Transcript forense
├── filesystem_logger.py            ← Wrapper forense para operaciones de archivo
├── pipeline_stage_logger.py        ← Ciclo de vida forense por stage
│
├── ── Playwright forense (Fase 3) ───────────────────────────────────────────
├── playwright/forensic_logger.ts   ← Escribe JSONL desde proceso TypeScript
├── playwright/instrumented_actions.ts ← Wrappers con eventos intent+result
├── playwright_forensic_bridge.py   ← Importa eventos TS → ForensicEventLogger Python
│
├── ── Human Unlock + Learning (Fase 4) ──────────────────────────────────────
├── blocker_registry.py             ← Registry JSON de blockers por run
├── human_unlock.py                 ← Desbloqueo humano: register/resolve/skip
├── learning_store.py               ← SQLite global de learnings gobernados
├── learning_candidate_generator.py ← Detecta 5 patrones y propone learnings
│
├── ── Métricas + Analytics (Fase 4) ─────────────────────────────────────────
├── metrics_collector.py            ← Métricas por run → data/metrics.jsonl
├── analytics_builder.py            ← Analytics histórico desde metrics.jsonl
├── kpi_builder.py                  ← 6 KPIs con semáforo green/yellow/red
├── observability_validator.py      ← Validación 8-capas de observabilidad
├── replay_run.py                   ← Replay forense desde event log (CLI)
│
├── ── Autonomía agéntica ────────────────────────────────────────────────────
├── replan_engine.py                ← Replanning automático (Fase 9)
├── autonomous_explorer.py          ← Exploración autónoma de UI (Fase 10)
├── navigation_graph.py             ← Grafo de navegación aprendido
├── navigation_graph_learner.py     ← Aprende edges desde sesiones grabadas
├── path_planner.py                 ← Path óptimo por confianza
├── session_recorder.py             ← Graba sesiones de navegación
├── session_to_playbook.py          ← Sesión → playbook replay-ready
├── playbook_router.py              ← Selecciona playbook según ticket/screen
├── playbook_performance.py         ← Métricas de uso de playbooks
│
├── ── Conocimiento de la app ────────────────────────────────────────────────
├── agenda_screens.py               ← Catálogo de ~90 pantallas de la Agenda Web
├── agenda_glossary.py              ← Glosario semántico de elementos UI
├── form_knowledge.json             ← Conocimiento de formularios
│
├── ── Guardrails / diagnóstico ──────────────────────────────────────────────
├── environment_preflight.py        ← Verifica que la Agenda Web esté activa
├── smoke_path_checker.py           ← Pre-validación rápida (≤20s)
├── execution_logger.py             ← Logger de sesión de ejecución
├── screen_error_detector.py        ← Detecta errores en screenshots
├── sql_query_guard.py              ← Whitelist de queries SQL permitidas
│
├── ── Schemas, templates, specs ─────────────────────────────────────────────
├── schemas/                        ← JSON schemas de contratos
├── templates/                      ← Templates Jinja2 para generación
├── SPEC/                           ← Especificaciones técnicas por tool
│
├── ── Smoke tests ───────────────────────────────────────────────────────────
├── smoke_phase1.py                 ← 22/22 PASS — Event Store, persistencia
├── smoke_phase2.py                 ← 31/31 PASS — Command logging, pipeline stage
├── smoke_phase3.py                 ← 22/22 PASS — Playwright forense
├── smoke_phase4.py                 ← 47/47 PASS — Human Unlock, métricas, analytics
├── tests/                          ← Tests unitarios por tool
│
└── ── Persistencia runtime ──────────────────────────────────────────────────
    ├── data/
    │   ├── learning_store.sqlite   ← DB global de learnings (compartida entre runs)
    │   ├── metrics.jsonl           ← Historial de métricas append-only
    │   └── agenda_glossary.json
    ├── evidence/
    │   └── <ticket_id>/<run_id>/   ← Evidencia forense por run
    │       ├── events.sqlite        (WAL mode)
    │       ├── events.jsonl         (append-only)
    │       ├── run_manifest.json
    │       ├── run_state.json
    │       ├── blockers.json
    │       ├── checkpoints/
    │       ├── artifacts/
    │       ├── playwright/          (JSONL de eventos TypeScript)
    │       └── command_logs/
    ├── cache/ui_maps/              ← Cache de UI maps (borrable)
    └── audit/                      ← Audit log de publicaciones ADO
```

---

## Persistencia de evidencia

| Ruta | Descripción |
|---|---|
| `evidence/<ticket>/<run_id>/events.sqlite` | Event store SQLite WAL — fuente de verdad |
| `evidence/<ticket>/<run_id>/events.jsonl` | Backup JSONL del event store |
| `evidence/<ticket>/<run_id>/run_manifest.json` | Manifiesto del run |
| `evidence/<ticket>/<run_id>/blockers.json` | Blockers registrados |
| `evidence/<ticket>/<run_id>/playwright/actions.jsonl` | Acciones Playwright |
| `evidence/<ticket>/<run_id>/playwright/network.jsonl` | Requests de red |
| `evidence/<ticket>/<run_id>/playwright/console.jsonl` | Mensajes de consola |
| `evidence/<ticket>/<run_id>/playwright/screenshots.jsonl` | Metadata de screenshots |
| `data/learning_store.sqlite` | Learnings gobernados (requieren aprobación humana) |
| `data/metrics.jsonl` | Historial de métricas de todos los runs |

---

## KPIs monitoreados

```bash
python qa_uat_pipeline.py --analytics-report
```

| KPI | Umbral verde | Umbral amarillo |
|---|---|---|
| KPI-01 Pass Rate | ≥ 80% | ≥ 60% |
| KPI-02 Duración promedio | ≤ 120s | ≤ 180s |
| KPI-03 Resolución de blockers | ≥ 90% | ≥ 70% |
| KPI-04 Assertions PASS | ≥ 85% | ≥ 70% |
| KPI-05 Adopción de learnings | ≥ 50% | ≥ 25% |
| KPI-06 Runs ejecutados | conteo | — |

---

## Variables de entorno

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `AGENDA_WEB_USER` | ✅ | — | Usuario de la Agenda Web |
| `AGENDA_WEB_PASS` | ✅ | — | Password de la Agenda Web |
| `AGENDA_WEB_BASE_URL` | ❌ | `http://localhost:35017/AgendaWeb/` | URL base |
| `STACKY_LLM_BACKEND` | ❌ | `vscode_bridge` | `vscode_bridge` / `copilot_direct` / `mock` |
| `QA_UAT_ALLOW_UI_DISCOVERY` | ❌ | `false` | Habilitar discovery dinámico de UI |
| `QA_UAT_REQUIRE_PLAYBOOK` | ❌ | `true` | Requerir playbook grabado |
| `QA_UAT_ALLOW_LLM_NAVIGATION` | ❌ | `false` | Habilitar navegación LLM |
| `QA_UAT_MAX_TOTAL_MINUTES` | ❌ | `6` | Límite de tiempo total |
| `QA_UAT_MAX_LOGIN_ATTEMPTS` | ❌ | `1` | Máximo de intentos de login |
| `QA_UAT_MAX_BROWSER_LAUNCHES` | ❌ | `1` | Máximo de lanzamientos de browser |
| `QA_UAT_SKIP_SMOKE` | ❌ | `false` | Saltar smoke path check |
| `QA_UAT_EXPECTED_HUMAN_MINUTES` | ❌ | `2` | Tiempo esperado del flujo humano |
| `QA_UAT_MAX_RUNTIME_MULTIPLIER` | ❌ | `3` | Multiplicador de expected_human_minutes |

---

## Restricciones de seguridad innegociables

- **Sin credenciales hardcodeadas**: toda credencial via `os.getenv()`.
- **Sin `ado.py state`**: prohibido en todos los módulos UAT.
- **Sin gestión del runtime de la app**: QA UAT Agent nunca inicia/detiene IIS Express.
- **BD solo-lectura**: todo acceso a BD es SELECT únicamente (guardado por `sql_query_guard.py`).
- **Sin publicación silenciosa**: `--mode publish` requiere acción CLI explícita del operador.
- **Redacción automática**: `redactor.py` redacta credentials en todos los logs y eventos.

---

## Correr smoke tests

```bash
cd "n:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent"
python smoke_phase1.py   # 22/22 — Event Store
python smoke_phase2.py   # 31/31 — Command logging
python smoke_phase3.py   # 22/22 — Playwright forense
python smoke_phase4.py   # 47/47 — Human Unlock, métricas, analytics
```
