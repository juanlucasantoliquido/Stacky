# Stacky Tools — Roadmap Spec-Driven Development

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

**Todo acceso a servicios externos (ADO, Git, BD, LLM) ocurre exclusivamente via Stacky Tools.** Ningún agente llama APIs REST directamente ni usa MCP tools de Azure DevOps. El agente usa la CLI de la tool; la tool encapsula el acceso al servicio.

```
Agente → StackyTool CLI → Servicio externo
         ^^^^^^^^^^^^^^^
         única capa autorizada
```

Esto garantiza:
- Auditoría centralizada (la tool loguea, el agente no necesita hacerlo)
- Credenciales en un solo lugar (la tool las gestiona)
- Testabilidad (se mockea la tool, no el servicio externo)
- Versionabilidad (el contrato de la tool es estable, la API del servicio puede cambiar)

### Categorías de tools

| Categoría | Propósito | Ejemplos |
|---|---|---|
| `ado_*` | Interacción con Azure DevOps | ADO Manager, `ado_evidence_publisher` |
| `git_*` | Interacción con Git/ADO Repos | Git Manager |
| `uat_*` | Pipeline de UAT funcional | ticket_reader, scenario_compiler, test_runner |
| `ui_*` | Inspección y verificación de UI | ui_map_builder, web_ui_verifier |
| `llm_*` | Acceso a modelos LLM | LLM Router, copilot_bridge |
| `db_*` | Consultas a BD (solo-lectura) | precondition_checker, test_data_finder |

---

## 1. Inventario actual de tools

### 1.A Tools existentes en producción

| Tool | Ubicación | Spec | Tests |
|---|---|---|---|
| **ADO Manager** (`ado.py`) | `Tools/Stacky/Stacky tools/ADO Manager/` | ❌ pendiente | ❌ |
| **Git Manager** (`git.py`) | `Tools/Stacky/Stacky tools/Git Manager/` | ❌ pendiente | ❌ |
| **web_ui_verifier** | `Tools/Stacky/Stacky pipeline/web_ui_verifier.py` | ❌ pendiente | ❌ |
| **copilot_bridge** | `Tools/Stacky/Stacky Agents/backend/copilot_bridge.py` | ❌ pendiente | ❌ |
| **ado_html_postprocessor** | `Tools/Stacky/Stacky pipeline/ado_html_postprocessor.py` | ❌ pendiente | ❌ |
| **ado_client** (Agents backend) | `Tools/Stacky/Stacky Agents/backend/services/ado_client.py` | ❌ pendiente | parcial |
| **llm_router** | `Tools/Stacky/Stacky Agents/backend/services/llm_router.py` | ❌ pendiente | parcial |

### 1.B Tools QA UAT Agent — nuevas (MVP)

| Tool | Ubicación | Spec | Implementada |
|---|---|---|---|
| `uat_ticket_reader.py` | `Tools/Stacky/Stacky tools/QA UAT Agent/` | ❌ pendiente | ❌ |
| `uat_scenario_compiler.py` | idem | ❌ pendiente | ❌ |
| `ui_map_builder.py` | idem | ❌ pendiente | ❌ |
| `selector_discovery.py` | idem | ❌ pendiente | ❌ |
| `playwright_test_generator.py` | idem | ❌ pendiente | ❌ |
| `uat_test_runner.py` | idem | ❌ pendiente | ❌ |
| `uat_dossier_builder.py` | idem | ❌ pendiente | ❌ |
| `ado_evidence_publisher.py` | idem | ❌ pendiente | ❌ |

### 1.C Tools QA UAT Agent — post-MVP (Fase 3.B/C)

| Tool | Fase |
|---|---|
| `uat_precondition_checker.py` | 3.B |
| `uat_evidence_capturer.py` | 3.B |
| `uat_assertion_evaluator.py` | 3.B |
| `uat_failure_analyzer.py` | 3.B |
| `uat_cleanup_tool.py` | 3.B |
| `uat_session_manager.py` | 3.B |
| `uat_report_summarizer.py` | 3.C |
| `uat_flakiness_detector.py` | 3.C |
| `uat_golden_path_validator.py` | 3.C |
| `uat_test_data_finder.py` | 3.C |
| `uat_action_recorder.py` | 3.C |

---

## 2. Estructura de una spec

Toda spec vive en `Tools/Stacky/Stacky tools/<Tool Name>/SPEC.md` (o `SPEC/<tool_name>.md` para herramientas individuales dentro de un tool folder con múltiples scripts).

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

## 3. Fases del roadmap

### FASE 0 — Spec de tools existentes (prioridad: unblocking)

> **Objetivo**: documentar las tools que ya están en producción pero no tienen spec formal. Sin esto, los agentes que las usan pueden invocarlas incorrectamente o depender de comportamientos no documentados.

| # | Tool | Archivo spec destino | Bloqueante para |
|---|---|---|---|
| F0.1 | ADO Manager (`ado.py`) | `Tools/Stacky/Stacky tools/ADO Manager/SPEC.md` | Todos los agentes que leen/escriben ADO |
| F0.2 | Git Manager (`git.py`) | `Tools/Stacky/Stacky tools/Git Manager/SPEC.md` | Agentes que crean PRs |
| F0.3 | `web_ui_verifier.py` | `Tools/Stacky/Stacky tools/QA UAT Agent/SPEC/web_ui_verifier.md` | Pipeline UAT (deploys, screenshots) |
| F0.4 | `copilot_bridge.py` | `Tools/Stacky/Stacky Agents/backend/SPEC/copilot_bridge.md` | Cualquier agente que use LLM via bridge |
| F0.5 | `ado_html_postprocessor.py` | `Tools/Stacky/Stacky tools/ADO Manager/SPEC/ado_html_postprocessor.md` | `ado_evidence_publisher` + otros comentarios ADO |
| F0.6 | `llm_router.py` | `Tools/Stacky/Stacky Agents/backend/SPEC/llm_router.md` | Cualquier tool que use LLM |

**Criterio de completitud de Fase 0**: cada spec cubre las 11 secciones; ningún agente del ecosistema invoca una tool sin spec.

**Duración estimada**: 1-2 iteraciones de agente.

---

### FASE 1 — Spec de tools QA UAT MVP (spec-first, no código)

> **Objetivo**: especificar completamente las 8 tools del MVP antes de escribir una sola línea de implementación. El orden de specs respeta el orden de ejecución del pipeline.

| # | Tool | Archivo spec | Depende de spec |
|---|---|---|---|
| F1.1 | `uat_ticket_reader.py` | `SPEC/uat_ticket_reader.md` | ADO Manager (F0.1) |
| F1.2 | `ui_map_builder.py` | `SPEC/ui_map_builder.md` | `web_ui_verifier` (F0.3) |
| F1.3 | `selector_discovery.py` | `SPEC/selector_discovery.md` | `ui_map_builder` (F1.2) |
| F1.4 | `uat_scenario_compiler.py` | `SPEC/uat_scenario_compiler.md` | `uat_ticket_reader` (F1.1), `llm_router` (F0.6) |
| F1.5 | `playwright_test_generator.py` | `SPEC/playwright_test_generator.md` | `uat_scenario_compiler` (F1.4), `ui_map_builder` (F1.2) |
| F1.6 | `uat_test_runner.py` | `SPEC/uat_test_runner.md` | `playwright_test_generator` (F1.5) |
| F1.7 | `uat_dossier_builder.py` | `SPEC/uat_dossier_builder.md` | `uat_test_runner` (F1.6), `llm_router` (F0.6) |
| F1.8 | `ado_evidence_publisher.py` | `SPEC/ado_evidence_publisher.md` | ADO Manager (F0.1), `ado_html_postprocessor` (F0.5) |

**Criterio de completitud de Fase 1**: 8 specs completas con criterios de aceptación; revision humana sign-off por spec antes de habilitar implementación.

---

### FASE 2 — Implementación MVP (código + tests)

> **Regla**: ninguna tool se implementa sin que su spec esté en estado `approved` (marcada en el inventario). El orden de implementación sigue el orden del pipeline, con excepciones donde el código es trivialmente derivable de la spec.

Orden recomendado:

1. `uat_ticket_reader.py` — entrada del pipeline; desbloquea todo lo demás
2. `ui_map_builder.py` + `selector_discovery.py` — par acoplado; desbloquea el generator
3. `uat_scenario_compiler.py` — usa LLM; requiere `llm_router` funcional
4. `playwright_test_generator.py` — plantilla determinista; bajo riesgo, alta reutilización
5. `uat_test_runner.py` — ejecución; depende de los `.spec.ts` generados en paso anterior
6. `uat_dossier_builder.py` — ensamblador; bajo riesgo
7. `ado_evidence_publisher.py` — única superficie de escritura a ADO; mayor rigor en testing

Artefactos por tool:
- `<tool>.py` — implementación
- `tests/unit/test_<tool>.py` — cobertura ≥ 80%
- `prompt_cards/<tool>.md` — si la tool usa LLM
- Actualización del inventario en este roadmap: `❌ → ✅`

---

### FASE 3 — Spec + implementación tools Fase 3.B

> **Objetivo**: completar el pipeline UAT con precondición checker, evaluador de assertions semánticas, failure analyzer y session manager.

Misma lógica: spec primero, código después.

| # | Tool | Notas |
|---|---|---|
| F3.1 | `uat_precondition_checker.py` | Requiere spec de acceso BD QA (cuenta `RSPACIFICOREAD`) |
| F3.2 | `uat_evidence_capturer.py` | Hooks Playwright; spec define qué capturar y en qué formato |
| F3.3 | `uat_assertion_evaluator.py` | LLM semántico; spec define cuándo PASS vs REVIEW |
| F3.4 | `uat_failure_analyzer.py` | LLM; spec define taxonomía completa |
| F3.5 | `uat_cleanup_tool.py` | Spec define límites de lo que puede borrar |
| F3.6 | `uat_session_manager.py` | Spec define política de cuenta `PABLO` (§0.bis.2 del roadmap Fase 3) |

---

### FASE 4 — Integración Stacky Agents backend + UI

> **Objetivo**: exponer el pipeline UAT desde el workbench de Stacky Agents (endpoint Flask + SSE + botón "Publicar" en frontend).

Componentes:
- `Tools/Stacky/Stacky Agents/backend/agents/qa_uat.py` — wrapper del agente sobre `qa_uat_pipeline.py`
- Endpoint `POST /api/qa-uat/run` con streaming SSE
- Frontend: pestaña "Dossier UAT" + botón "Publicar comentario en ADO"
- Registro del agente `qa_uat` en el sistema de agentes (`AgentExecution` en BD)

Prerequisito: Fases 0, 1 y 2 completadas.

---

### FASE 5 — Tools avanzadas (Fase 3.C)

> **Objetivo**: ampliar el alcance del agente QA UAT con pantallas adicionales, flakiness detection, golden path validation y action recording.

Spec + implementación de:
- `uat_report_summarizer.py`
- `uat_flakiness_detector.py`
- `uat_golden_path_validator.py`
- `uat_test_data_finder.py`
- `uat_action_recorder.py`

---

## 4. Proceso de una spec → código

```
1. Redactar SPEC.md completo (11 secciones)
         │
         ▼
2. Review humano (sign-off en el archivo: añadir `status: approved` al header)
         │
         ▼
3. Implementar <tool>.py siguiendo la spec como única fuente de verdad
         │
         ▼
4. Escribir tests unitarios cubriendo todos los criterios de aceptación
         │
         ▼
5. Ejecutar tests — cobertura ≥ 80%
         │
         ▼
6. Actualizar inventario: ❌ → ✅ en este roadmap
         │
         ▼
7. PR obligatorio con: spec + implementación + tests + evidencia de tests pasando
```

**Prohibido**: implementar sin spec aprobada. Prohibido marcar una spec como aprobada si le falta alguna de las 11 secciones.

---

## 5. Convenciones de todas las tools

### Output JSON canónico

Toda tool retorna JSON a stdout:

```json
// Éxito
{"ok": true, "data": {...}, "meta": {"duration_ms": 123, "tool": "uat_ticket_reader", "version": "1.0.0"}}

// Error
{"ok": false, "error": "<error_code>", "message": "Descripción legible del error", "meta": {...}}
```

- `"ok"` es siempre el primer campo.
- `"error"` es un código snake_case (`ado_unreachable`, `ticket_not_found`, etc.), nunca texto libre.
- Exit code `0` para éxito, `1` para error.

### Credenciales

- Nunca por argumento CLI (evitar leakage en logs de shell)
- Siempre desde env vars o archivos `.env` cargados con `python-dotenv`
- Fail rápido si la env var requerida no está seteada: `{"ok": false, "error": "missing_env_var", "message": "RS_QA_DB_PASS is required. Cargala desde Tools/Stacky/.secrets/qa_db.env"}`

### Dependencias Python

Cada tool declara sus dependencias en un `requirements.txt` de su carpeta. No depender de paquetes no declarados.

### Logging

- Logs a stderr (no a stdout, que es reservado para JSON)
- Nivel INFO por defecto; DEBUG con flag `--verbose`
- Formato: `[YYYY-MM-DD HH:MM:SS] [TOOL] [LEVEL] mensaje`

### Idempotencia

Toda tool que escribe datos (archivos, ADO, BD) debe ser idempotente: ejecutarla dos veces con el mismo input produce el mismo resultado.

---

## 6. Estado actual del roadmap

### Fase 0 — Specs tools existentes

| # | Tool | Spec | Estado |
|---|---|---|---|
| F0.1 | ADO Manager | `Tools/Stacky/Stacky tools/ADO Manager/SPEC.md` | ✅ completada |
| F0.2 | Git Manager | `Tools/Stacky/Stacky tools/Git Manager/SPEC.md` | ✅ completada |
| F0.3 | web_ui_verifier | `Tools/Stacky/Stacky tools/QA UAT Agent/SPEC/web_ui_verifier.md` | ✅ completada |
| F0.4 | copilot_bridge | `Tools/Stacky/Stacky Agents/backend/SPEC/copilot_bridge.md` | ⏸ pendiente |
| F0.5 | ado_html_postprocessor | `Tools/Stacky/Stacky tools/ADO Manager/SPEC/ado_html_postprocessor.md` | ⏸ pendiente |
| F0.6 | llm_router | `Tools/Stacky/Stacky Agents/backend/SPEC/llm_router.md` | ⏸ pendiente |

### Fase 1 — Specs tools QA UAT MVP

| # | Tool | Spec | Estado |
|---|---|---|---|
| F1.1 | `uat_ticket_reader` | `SPEC/uat_ticket_reader.md` | ✅ completada |
| F1.2 | `ui_map_builder` | `SPEC/ui_map_builder.md` | ✅ completada |
| F1.3 | `selector_discovery` | `SPEC/selector_discovery.md` | ✅ completada |
| F1.4 | `uat_scenario_compiler` | `SPEC/uat_scenario_compiler.md` | ✅ completada |
| F1.5 | `playwright_test_generator` | `SPEC/playwright_test_generator.md` | ✅ completada |
| F1.6 | `uat_test_runner` | `SPEC/uat_test_runner.md` | ✅ completada |
| F1.7 | `uat_dossier_builder` | `SPEC/uat_dossier_builder.md` | ✅ completada |
| F1.8 | `ado_evidence_publisher` | `SPEC/ado_evidence_publisher.md` | ✅ completada |

### Fase 2 — Implementación MVP

| # | Tool | Implementada | Tests | Estado |
|---|---|---|---|---|
| F2.1 | `uat_ticket_reader` | ❌ | ❌ | ⏸ pendiente (requiere sign-off F1.1) |
| F2.2 | `ui_map_builder` + `selector_discovery` | ❌ | ❌ | ⏸ pendiente |
| F2.3 | `uat_scenario_compiler` | ❌ | ❌ | ⏸ pendiente |
| F2.4 | `playwright_test_generator` | ❌ | ❌ | ⏸ pendiente |
| F2.5 | `uat_test_runner` | ❌ | ❌ | ⏸ pendiente |
| F2.6 | `uat_dossier_builder` | ❌ | ❌ | ⏸ pendiente |
| F2.7 | `ado_evidence_publisher` | ❌ | ❌ | ⏸ pendiente |

### Fases 3–5

⏸ pendientes, desbloqueadas al completar Fase 2.

---

## 7. Próximo paso inmediato

> **Para habilitar la implementación MVP**, el operador debe dar sign-off a las specs F1.1–F1.8.

Proceso de sign-off: revisar el archivo `SPEC/<tool>.md`, y si está conforme, agregar en el header YAML:

```yaml
status: approved
approved_by: <nombre>
approved_date: YYYY-MM-DD
```

Una vez aprobadas las 8 specs, comenzar implementación en el orden indicado en Fase 2.
