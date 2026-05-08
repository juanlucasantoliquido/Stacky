# Stacky Tools — Roadmap

> **Documento rector del ecosistema de herramientas Stacky.**
>
> Principio fundamental: **spec antes de código**. Ninguna tool se implementa sin que exista primero su especificación técnica completa aprobada. Las specs son el contrato de la tool con el resto del ecosistema; el código es su implementación.
>
> **Enfoque**: cada tool es un binario CLI Python que:
> - Acepta argumentos deterministas
> - Devuelve JSON a stdout
> - Reporta errores en `{"ok": false, "error": "<code>", "message": "..."}` con exit code 1
> - No tiene side effects fuera de su dominio declarado
> - Es invocable tanto por agentes como por humanos desde la terminal

---

## 0. Principios del ecosistema

### Por qué spec-driven

Los agentes de IA son no-deterministas por naturaleza. Las tools físicas son el cimiento determinista sobre el que los agentes operan de forma confiable. Si una tool no tiene spec:
- El agente no sabe qué esperar → improvisa → produce resultados variables
- El developer no sabe qué contrato mantener → rompe compatibilidad sin saberlo
- El QA no sabe qué validar → los tests no cubren los contratos reales

Una spec bien escrita elimina esa incertidumbre.

### Restricción de acceso a servicios externos

**Todo acceso a servicios externos (ADO, Git, BD, LLM) ocurre exclusivamente via Stacky Tools.** Ningún agente llama APIs REST directamente ni usa MCP tools de Azure DevOps.

```
Agente → StackyTool CLI → Servicio externo
         ^^^^^^^^^^^^^^^
         única capa autorizada
```

Esto garantiza:
- Auditoría centralizada
- Credenciales en un solo lugar
- Testabilidad (se mockea la tool, no el servicio externo)
- Versionabilidad

### Categorías de tools

| Categoría | Propósito | Ejemplos |
|---|---|---|
| `ado_*` | Interacción con Azure DevOps | ADO Manager, `ado_evidence_publisher` |
| `git_*` | Interacción con Git/ADO Repos | Git Manager |
| `uat_*` | Pipeline de UAT funcional | ticket_reader, scenario_compiler, test_runner |
| `ui_*` | Inspección y verificación de UI | ui_map_builder |
| `llm_*` | Acceso a modelos LLM | LLM Router, copilot_bridge |
| `db_*` | Consultas a BD (solo-lectura) | precondition_checker, data_resolver |

---

## 1. Inventario actual de tools

### 1.A Tools existentes en producción

| Tool | Ubicación | Spec | Tests |
|---|---|---|---|
| **ADO Manager** (`ado.py`) | `Tools/Stacky/Stacky tools/ADO Manager/` | ❌ pendiente | ❌ |
| **Git Manager** (`git.py`) | `Tools/Stacky/Stacky tools/Git Manager/` | ❌ pendiente | ❌ |
| **copilot_bridge** | `Tools/Stacky/Stacky Agents/backend/copilot_bridge.py` | ❌ pendiente | ❌ |
| **ado_html_postprocessor** | `Tools/Stacky/Stacky pipeline/ado_html_postprocessor.py` | ❌ pendiente | ❌ |
| **ado_client** (Agents backend) | `Tools/Stacky/Stacky Agents/backend/services/ado_client.py` | ❌ pendiente | parcial |
| **llm_router** | `Tools/Stacky/Stacky Agents/backend/services/llm_router.py` | ❌ pendiente | parcial |

### 1.B Tools QA UAT Agent — estado actual

#### Pipeline core

| Tool | Implementada | Spec | Tests |
|---|---|---|---|
| `uat_ticket_reader.py` | ✅ | `SPEC/uat_ticket_reader.md` | parcial |
| `ui_map_builder.py` | ✅ | `SPEC/ui_map_builder.md` | parcial |
| `selector_discovery.py` | ✅ | `SPEC/selector_discovery.md` | parcial |
| `uat_scenario_compiler.py` | ✅ | `SPEC/uat_scenario_compiler.md` | parcial |
| `uat_precondition_checker.py` | ✅ | — | ❌ |
| `playwright_test_generator.py` | ✅ | `SPEC/playwright_test_generator.md` | parcial |
| `spec_linter.py` | ✅ | — | ❌ |
| `uat_test_runner.py` | ✅ | `SPEC/uat_test_runner.md` | parcial |
| `screenshot_annotator.py` | ✅ | — | ❌ |
| `uat_assertion_evaluator.py` | ✅ | — | ❌ |
| `uat_failure_analyzer.py` | ✅ | — | ❌ |
| `uat_dossier_builder.py` | ✅ | `SPEC/uat_dossier_builder.md` | parcial |
| `ado_evidence_publisher.py` | ✅ | `SPEC/ado_evidence_publisher.md` | parcial |
| `qa_uat_pipeline.py` | ✅ | — | smoke (122/122) |

#### Free-form mode

| Tool | Implementada | Descripción |
|---|---|---|
| `intent_parser.py` | ✅ | Parsea intent_spec.json |
| `synthetic_ticket_builder.py` | ✅ | Genera ticket.json desde intent_spec |
| `data_resolver.py` | ✅ | Resuelve placeholders via BD (SELECT only) |
| `intent_inferrer.py` | ✅ | Infiere intent_spec desde texto libre (LLM) |

#### Instrumentación forense (Fases 1–4)

| Tool | Implementada | Smoke |
|---|---|---|
| `event_schema.py` | ✅ | — |
| `event_store.py` | ✅ | Fase 1 |
| `forensic_event_logger.py` | ✅ | Fase 1 |
| `run_manifest.py` | ✅ | Fase 1 |
| `checkpoint_manager.py` | ✅ | Fase 1 |
| `artifact_registry.py` | ✅ | Fase 1 |
| `event_policy.py` | ✅ | Fase 1 |
| `data_contracts.py` | ✅ | Fase 1 |
| `redactor.py` | ✅ | Fase 2 |
| `command_runner.py` | ✅ | Fase 2 |
| `powershell_logger.py` | ✅ | Fase 2 |
| `filesystem_logger.py` | ✅ | Fase 2 |
| `pipeline_stage_logger.py` | ✅ | Fase 2 |
| `playwright/forensic_logger.ts` | ✅ | Fase 3 |
| `playwright/instrumented_actions.ts` | ✅ | Fase 3 |
| `playwright_forensic_bridge.py` | ✅ | Fase 3 |
| `blocker_registry.py` | ✅ | Fase 4 |
| `human_unlock.py` | ✅ | Fase 4 |
| `learning_store.py` | ✅ | Fase 4 |
| `learning_candidate_generator.py` | ✅ | Fase 4 |
| `metrics_collector.py` | ✅ | Fase 4 |
| `analytics_builder.py` | ✅ | Fase 4 |
| `kpi_builder.py` | ✅ | Fase 4 |
| `observability_validator.py` | ✅ | Fase 4 |
| `replay_run.py` | ✅ | Fase 4 |

#### Autonomía agéntica

| Tool | Implementada | Descripción |
|---|---|---|
| `replan_engine.py` | ✅ | Replanning automático (Fase 9) |
| `navigation_graph.py` | ✅ | Grafo de navegación |
| `navigation_graph_learner.py` | ✅ | Aprende edges desde sesiones |
| `path_planner.py` | ✅ | Path óptimo por confianza |
| `graph_promoter.py` | ✅ | Promueve edges al grafo activo |
| `session_recorder.py` | ✅ | Graba sesiones de navegación |
| `session_to_playbook.py` | ✅ | Sesión → playbook |
| `playbook_router.py` | ✅ | Selecciona playbook según ticket/screen |
| `playbook_performance.py` | ✅ | Métricas de playbooks |
| `autonomous_explorer.py` | ✅ | Exploración autónoma (Fase 10) |

#### Conocimiento de la app

| Tool | Implementada | Descripción |
|---|---|---|
| `agenda_screens.py` | ✅ | ~90 pantallas de la Agenda Web |
| `agenda_glossary.py` | ✅ | Glosario semántico UI |
| `form_knowledge.json` | ✅ | Conocimiento de formularios |

#### Guardrails / diagnóstico

| Tool | Implementada | Descripción |
|---|---|---|
| `environment_preflight.py` | ✅ | Verifica que la app esté activa |
| `smoke_path_checker.py` | ✅ | Pre-validación rápida ≤20s |
| `execution_logger.py` | ✅ | Logger de sesión de ejecución |
| `screen_error_detector.py` | ✅ | Detecta errores en screenshots |
| `sql_query_guard.py` | ✅ | Whitelist de queries SQL |

---

## 2. Estructura de una spec

Toda spec vive en `Tools/Stacky/Stacky tools/<Tool Name>/SPEC/<tool_name>.md`.

Secciones obligatorias:

```markdown
# SPEC — <nombre de la tool>

## 1. Propósito
## 2. Alcance (qué hace y qué NO hace)
## 3. Inputs (args CLI, env vars, stdin)
## 4. Outputs (JSON a stdout — esquema)
## 5. Contrato de uso (precondiciones, postcondiciones, idempotencia)
## 6. Validaciones internas
## 7. Errores esperados (código, mensaje, cuándo)
## 8. Dependencias (otras tools, servicios, libs)
## 9. Ejemplos de uso
## 10. Criterios de aceptación
## 11. Tests requeridos
```

---

## 3. Roadmap pendiente

### FASE 0 — Spec de tools existentes sin spec

| # | Tool | Archivo spec destino | Estado |
|---|---|---|---|
| F0.1 | ADO Manager (`ado.py`) | `Tools/Stacky/Stacky tools/ADO Manager/SPEC.md` | ❌ pendiente |
| F0.2 | Git Manager (`git.py`) | `Tools/Stacky/Stacky tools/Git Manager/SPEC.md` | ❌ pendiente |
| F0.3 | `copilot_bridge.py` | `Tools/Stacky/Stacky Agents/backend/SPEC/copilot_bridge.md` | ❌ pendiente |
| F0.4 | `ado_html_postprocessor.py` | `Tools/Stacky/Stacky tools/ADO Manager/SPEC/ado_html_postprocessor.md` | ❌ pendiente |
| F0.5 | `llm_router.py` | `Tools/Stacky/Stacky Agents/backend/SPEC/llm_router.md` | ❌ pendiente |

### FASE E — Cobertura de tests (QA UAT Agent)

| # | Objetivo | Estado |
|---|---|---|
| E1 | Tests unitarios ≥ 80% cobertura en todas las tools de pipeline core | ❌ pendiente |
| E2 | Specs formales para `spec_linter`, `screenshot_annotator`, `uat_assertion_evaluator`, `uat_failure_analyzer` | ❌ pendiente |
| E3 | Integration test con AgendaWeb real (ticket 70) | ❌ pendiente |

### FASE F — Integraciones Stacky Agents backend

| # | Artefacto | Descripción | Estado |
|---|---|---|---|
| F1 | `POST /api/qa-uat/run` | Endpoint Flask con streaming SSE | ❌ pendiente |
| F2 | Panel de KPIs en frontend React | Visualización de KPIs/blockers/analytics | ❌ pendiente |
| F3 | Auto-collect métricas al fin de cada run | Llamar `MetricsCollector.collect_and_persist()` en `run()` | ❌ pendiente |
| F4 | Auto-generar learnings al fin de cada run | Llamar `LearningCandidateGenerator.generate()` en `run()` | ❌ pendiente |

---

## 4. Smoke tests actuales

```bash
cd "n:\GIT\RS\RSPACIFICO\Tools\Stacky\Stacky tools\QA UAT Agent"
python smoke_phase1.py   # 22/22 PASS — Event Store
python smoke_phase2.py   # 31/31 PASS — Command logging
python smoke_phase3.py   # 22/22 PASS — Playwright forense
python smoke_phase4.py   # 47/47 PASS — Human Unlock, métricas, analytics
```

Total: **122/122 smoke checks PASS** (2026-05-08).
