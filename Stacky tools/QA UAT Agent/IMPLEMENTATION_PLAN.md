# Plan de Implementación — QA UAT Agent

> **Autor**: StackyToolArchitect
> **Última actualización**: 2026-05-08
> **Estado**: Todas las fases completadas y validadas.

---

## Resumen de fases

| Fase | Descripción | Estado | Smoke |
|---|---|---|---|
| Fase A | Infraestructura base (schemas, templates, requirements) | ✅ completa | — |
| Fase B | Pipeline core (8 tools: reader→publisher) | ✅ completa | — |
| Fase C | Orquestador `qa_uat_pipeline.py` | ✅ completa | — |
| Fase D | Integraciones (free-form, playbooks, replanning) | ✅ completa | — |
| Fase 1 (forense) | Event Store, persistencia, schemas, contratos | ✅ completa | 22/22 |
| Fase 2 (forense) | Logging de comandos, PowerShell, filesystem | ✅ completa | 31/31 |
| Fase 3 (forense) | Instrumentación Playwright forense | ✅ completa | 22/22 |
| Fase 4 (forense) | Human Unlock, learnings, métricas, analytics, replay | ✅ completa | 47/47 |

---

## Restricciones innegociables

| Restricción | Detalle |
|---|---|
| Sin credenciales en repo | Toda credencial via `os.getenv()` con fail-fast |
| Sin `ado.py state` | Prohibido en cualquier `uat_*.py` y `ado_evidence_publisher.py` |
| JSON a stdout | Toda tool retorna `{"ok": true, ...}` o `{"ok": false, "error": "...", "message": "..."}` con exit code 1 en error |
| Sin MCP Azure | El agente usa solo `python ado.py ...` via subprocess |
| Sin gestión del runtime de la app | QA UAT Agent NUNCA inicia/detiene IIS Express |
| BD solo-lectura | Todo acceso a BD es SELECT (guardado por `sql_query_guard.py`) |
| Sin publicación silenciosa | `--mode publish` requiere acción CLI explícita |

---

## Fase A — Infraestructura base (completa)

### Artefactos

| ID | Artefacto | Estado |
|---|---|---|
| A1 | `schemas/uat_ticket.schema.json` | ✅ |
| A2 | `schemas/scenario_spec.schema.json` | ✅ |
| A3 | `schemas/ui_map.schema.json` | ✅ |
| A4 | `schemas/runner_output.schema.json` | ✅ |
| A5 | `schemas/dossier.schema.json` | ✅ |
| A6 | `templates/playwright_test.spec.ts.j2` | ✅ |
| A7 | `templates/dossier.md.j2` | ✅ |
| A8 | `templates/ado_comment.html.j2` | ✅ |
| A9 | `requirements.txt` | ✅ |
| A10 | `playwright.config.ts` | ✅ |

---

## Fase B — Pipeline core (completa)

### Tools implementadas

| ID | Tool | Tests |
|---|---|---|
| B1 | `uat_ticket_reader.py` | `tests/unit/test_uat_ticket_reader.py` |
| B2 | `selector_discovery.py` | `tests/unit/test_selector_discovery.py` |
| B3 | `ui_map_builder.py` | `tests/unit/test_ui_map_builder.py` |
| B4 | `uat_scenario_compiler.py` | `tests/unit/test_uat_scenario_compiler.py` |
| B5 | `playwright_test_generator.py` | `tests/unit/test_playwright_test_generator.py` |
| B6 | `uat_test_runner.py` | `tests/unit/test_uat_test_runner.py` |
| B7 | `uat_dossier_builder.py` | `tests/unit/test_uat_dossier_builder.py` |
| B8 | `ado_evidence_publisher.py` | `tests/unit/test_ado_evidence_publisher.py` |

### Tools adicionales (Fase 3.B)

| Tool | Descripción |
|---|---|
| `uat_precondition_checker.py` | Verifica datos en BD dev antes de ejecutar |
| `uat_assertion_evaluator.py` | Evalúa oráculos → PASS/FAIL/BLOCKED/REVIEW |
| `uat_failure_analyzer.py` | Clasifica FAILs en taxonomía con hipótesis |
| `screenshot_annotator.py` | Anota screenshots con box rojo (Pillow) |
| `spec_linter.py` | Valida que los .spec.ts generados no contengan login |

---

## Fase C — Orquestador (completa)

`qa_uat_pipeline.py` orquesta los stages 1–9 con las siguientes capacidades:

- **Modo ADO**: `--ticket N`
- **Modo free-form**: `--intent-file PATH`
- **Skip de stages**: `--skip-to STAGE`
- **Replanning**: `--replan` (Fase 9)
- **Guardrails**: tiempo total, intentos de login, lanzamientos de browser
- **Preflight**: verifica que la Agenda Web esté activa antes de cualquier acción
- **Smoke path**: pre-validación rápida (≤20s) antes de abrir browser

### Stages del pipeline

| Stage | Tool | LLM | Fatal |
|---|---|---|---|
| reader | `uat_ticket_reader.py` | ❌ | ✅ |
| ui_map | `ui_map_builder.py` | ❌ | ✅ |
| compiler | `uat_scenario_compiler.py` | ✅ gpt-4.1-mini | ✅ |
| preconditions | `uat_precondition_checker.py` | ❌ | ❌ (warning) |
| generator | `playwright_test_generator.py` | ❌ | ✅ |
| spec_linter | `spec_linter.py` | ❌ | ✅ |
| runner | `uat_test_runner.py` | ❌ | ✅ |
| annotator | `screenshot_annotator.py` | ❌ | ❌ (non-fatal) |
| evaluator | `uat_assertion_evaluator.py` | ❌ | ✅ |
| failure_analyzer | `uat_failure_analyzer.py` | ✅ gpt-4.1 | ✅ |
| dossier | `uat_dossier_builder.py` | ✅ gpt-4.1 | ✅ |
| publisher | `ado_evidence_publisher.py` | ❌ | ✅ |

---

## Fase D — Integraciones (completa)

### D1 — Free-form mode

```bash
python qa_uat_pipeline.py --intent-file evidence/mi_run/intent_spec.json
python qa_uat_pipeline.py --intent-file ... --resume --data-file resolved_data.json
python qa_uat_pipeline.py --intent-file ... --auto-resolve
```

Módulos involucrados:
- `intent_parser.py` — parsea y valida `intent_spec.json`
- `synthetic_ticket_builder.py` — construye `ticket.json` desde intent_spec
- `data_resolver.py` — resuelve placeholders via BD (SELECT only)

Exit codes:
- `0` — OK
- `1` — error fatal
- `2` — PENDING_DATA (datos sin resolver, usar `--resume`)

### D2 — Playbooks y autonomía

| Tool | Descripción |
|---|---|
| `session_recorder.py` | Graba sesiones de navegación para aprendizaje |
| `session_to_playbook.py` | Convierte sesión grabada → playbook replay-ready |
| `navigation_graph.py` | Grafo de navegación aprendido |
| `navigation_graph_learner.py` | Aprende edges + trigger_selector PostBack |
| `path_planner.py` | Calcula path óptimo por pesos de confianza |
| `graph_promoter.py` | Promueve edges al grafo activo |
| `playbook_router.py` | Selecciona playbook según ticket/screen |
| `intent_inferrer.py` | Infiere intent_spec desde texto libre (LLM) |

### D3 — Replanning automático (Fase 9)

```bash
python qa_uat_pipeline.py --ticket 70 --replan
```

`replan_engine.py` ejecuta hasta N rondas de corrección automática:
1. Analiza fallas del runner
2. Clasifica: `no_action` / `retry` / `escalate`
3. Si `retry`: parchea intent_spec, re-genera specs, re-ejecuta runner

---

## Fase 1–4 — Instrumentación forense (completa)

### Fase 1 — Event Store

| Módulo | Descripción |
|---|---|
| `event_schema.py` | Schema universal v1.0 — `build_event()`, `validate_event()` |
| `event_store.py` | Persistencia dual SQLite+JSONL con dead_letters fallback |
| `forensic_event_logger.py` | Logger forense canónico — toda la instrumentación pasa por aquí |
| `run_manifest.py` | `run_manifest.json` + `run_state.json` por run |
| `checkpoint_manager.py` | Checkpoints por stage |
| `artifact_registry.py` | Registry de artefactos con SHA256 |
| `event_policy.py` | 10 checks de trazabilidad |
| `data_contracts.py` | 16 contratos de calidad DC-01..DC-16 |
| `redactor.py` | Redacción de secretos en todos los logs |

**Run ID format**: `uat-<ticket_id>-<YYYYMMDD>-<HHMMSS>`

**Smoke**: `python smoke_phase1.py` → 22/22 PASS

### Fase 2 — Logging de comandos

| Módulo | Descripción |
|---|---|
| `command_runner.py` | Wrapper forense para subprocess — `run_logged()`, `run_streaming()` |
| `powershell_logger.py` | PowerShell con Start-Transcript forense |
| `filesystem_logger.py` | Wrapper forense para operaciones de archivo |
| `pipeline_stage_logger.py` | Ciclo de vida forense por stage |

**Smoke**: `python smoke_phase2.py` → 31/31 PASS

### Fase 3 — Playwright forense

| Módulo | Descripción |
|---|---|
| `playwright/forensic_logger.ts` | Escribe JSONL desde proceso TypeScript |
| `playwright/instrumented_actions.ts` | Wrappers con eventos intent+result |
| `playwright_forensic_bridge.py` | Importa eventos TS → `ForensicEventLogger` Python |
| `uat_test_runner.py` (modificado) | Pasa `run_dir`, `forensic_log`, `artifact_registry` al runner |

**Config via env vars**: `QA_UAT_FORENSIC_RUN_DIR`, `QA_UAT_FORENSIC_RUN_ID`, `QA_UAT_FORENSIC_TICKET_ID`

**Output TypeScript**:
- `<run_dir>/playwright/actions.jsonl`
- `<run_dir>/playwright/network.jsonl`
- `<run_dir>/playwright/console.jsonl`
- `<run_dir>/playwright/screenshots.jsonl`

**Smoke**: `python smoke_phase3.py` → 22/22 PASS

### Fase 4 — Human Unlock, learnings, métricas, analytics

| Módulo | Descripción |
|---|---|
| `blocker_registry.py` | Registry JSON de blockers: `register()`, `resolve()`, `skip()` |
| `human_unlock.py` | Desbloqueo humano con eventos forenses + CLI entry point |
| `learning_store.py` | SQLite global — candidates requieren aprobación humana |
| `learning_candidate_generator.py` | Detecta 5 patrones: selector_fix, timeout_fix, flow_fix, blocker_resolved, replan_success |
| `metrics_collector.py` | Métricas por run → `data/metrics.jsonl` (append-only) |
| `analytics_builder.py` | Analytics histórico: pass_rate, top_failures, duration_trends, blocker_analysis |
| `kpi_builder.py` | 6 KPIs con semáforo green/yellow/red |
| `observability_validator.py` | Validación 8-capas: event_policy, data_contracts, run_manifest, checkpoints, artifacts, playwright, blockers, metrics |
| `replay_run.py` | Replay forense desde event log (solo analítico, no re-ejecuta) |

**Nuevos comandos CLI**:
```bash
python qa_uat_pipeline.py --analytics-report [--days N]
python qa_uat_pipeline.py --ticket N --replay-run RUN_ID
python qa_uat_pipeline.py --ticket N --validate-observability
python qa_uat_pipeline.py --ticket N --list-blockers RUN_ID
python qa_uat_pipeline.py --ticket N --run-id RUN_ID --resolve-blocker BLOCKER_ID --answer TEXT
```

**Smoke**: `python smoke_phase4.py` → 47/47 PASS

---

## Árbol de archivos actual

```
QA UAT Agent/
├── qa_uat_pipeline.py              ← Orquestador CLI
├── requirements.txt                ← Dependencias Python
├── playwright.config.ts            ← Config Playwright
├── package.json                    ← Dependencias Node.js
│
├── ── Pipeline core ─────────────────────────────────────
├── uat_ticket_reader.py
├── ui_map_builder.py
├── selector_discovery.py
├── uat_scenario_compiler.py
├── uat_precondition_checker.py
├── playwright_test_generator.py
├── spec_linter.py
├── uat_test_runner.py
├── screenshot_annotator.py
├── uat_assertion_evaluator.py
├── uat_failure_analyzer.py
├── uat_dossier_builder.py
├── ado_evidence_publisher.py
│
├── ── Free-form mode ────────────────────────────────────
├── intent_parser.py
├── synthetic_ticket_builder.py
├── data_resolver.py
│
├── ── Forense (Fase 1–4) ───────────────────────────────
├── event_schema.py
├── event_store.py
├── forensic_event_logger.py
├── run_manifest.py
├── checkpoint_manager.py
├── artifact_registry.py
├── event_policy.py
├── data_contracts.py
├── redactor.py
├── command_runner.py
├── powershell_logger.py
├── filesystem_logger.py
├── pipeline_stage_logger.py
├── playwright/forensic_logger.ts
├── playwright/instrumented_actions.ts
├── playwright_forensic_bridge.py
├── blocker_registry.py
├── human_unlock.py
├── learning_store.py
├── learning_candidate_generator.py
├── metrics_collector.py
├── analytics_builder.py
├── kpi_builder.py
├── observability_validator.py
├── replay_run.py
│
├── ── Autonomía agéntica ────────────────────────────────
├── replan_engine.py
├── autonomous_explorer.py
├── navigation_graph.py
├── navigation_graph_learner.py
├── path_planner.py
├── graph_promoter.py
├── session_recorder.py
├── session_to_playbook.py
├── playbook_router.py
├── playbook_performance.py
├── intent_inferrer.py
│
├── ── Conocimiento de la app ───────────────────────────
├── agenda_screens.py               ← ~90 pantallas de la Agenda Web
├── agenda_glossary.py
├── form_knowledge.json
│
├── ── Guardrails / diagnóstico ─────────────────────────
├── environment_preflight.py
├── smoke_path_checker.py
├── execution_logger.py
├── screen_error_detector.py
├── sql_query_guard.py
│
├── ── Schemas, templates, SPEC ─────────────────────────
├── schemas/
├── templates/
├── SPEC/
│
├── ── Smoke tests ───────────────────────────────────────
├── smoke_phase1.py                 ← 22/22 PASS
├── smoke_phase2.py                 ← 31/31 PASS
├── smoke_phase3.py                 ← 22/22 PASS
├── smoke_phase4.py                 ← 47/47 PASS
├── tests/
│
└── ── Persistencia runtime ─────────────────────────────
    ├── data/
    │   ├── learning_store.sqlite
    │   └── metrics.jsonl
    ├── evidence/<ticket_id>/<run_id>/
    ├── cache/ui_maps/
    └── audit/
```

---

## Próximos pasos potenciales

| Item | Descripción | Prioridad |
|---|---|---|
| Auto-collect métricas | Llamar `MetricsCollector.collect_and_persist()` al final de `run()` | Media |
| Auto-generar learnings | Llamar `LearningCandidateGenerator.generate()` al final del pipeline | Media |
| UI surfacing KPIs | Panel en el frontend de Stacky Agents con KPIs/blockers | Baja |
| Endpoint Flask | `POST /api/qa-uat/run` con streaming SSE | Baja |
| Tests unitarios completos | Cobertura ≥ 80% en todas las tools de Fase B | Media |
