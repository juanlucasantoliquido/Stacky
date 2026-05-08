# Flujo QA UAT Agent — Etapas, componentes y llamadas LLM

## Dos sistemas QA distintos

Stacky tiene dos sistemas QA que no deben confundirse:

| Sistema | Qué hace | LLM |
|---|---|---|
| **QA Agent** (workbench Flask) | Análisis textual de evidencia → veredicto PASS/FAIL | 1 llamada al invocar desde el workbench |
| **QA UAT Agent** (este pipeline) | Browser real (Playwright) → evidencia automatizada → dossier | 4 llamadas distribuidas en etapas |

---

## Sistema A — QA Agent (workbench)

Una sola llamada LLM cuando el operador hace click en Run desde el workbench de Stacky:

```
Operador hace click Run
    → agent_runner construye prompt (system + context_blocks)
    → copilot_bridge.invoke()          ← única llamada LLM
        ├─ backend="copilot" → POST a api.githubcopilot.com (GitHub Copilot API REST)
        └─ backend="mock"    → respuesta canned (para tests de UI)
    → output = texto PASS/FAIL con veredicto
```

**VS Code Copilot Chat NO participa.** `copilot_bridge.py` llama directamente a la API REST de GitHub
Copilot con token OAuth (`gh auth token`). Es una llamada HTTP desde Python, no requiere VS Code abierto.

---

## Sistema B — QA UAT Agent (pipeline Playwright)

Pipeline de 10 etapas con browser real. Cada etapa tiene un archivo Python dedicado.

```
python qa_uat_pipeline.py --ticket 70 --mode dry-run|publish
```

---

### Stage 1 — reader (`uat_ticket_reader.py`)

**Qué hace:** Lee el ticket ADO, normaliza el HTML de los comentarios y extrae:
- Análisis técnico (sección `🔬`)
- Plan de pruebas funcional
- Evidencia del Developer (sección `🚀`)

**Llamadas externas:** `ado.py` → ADO REST API  
**LLM:** ❌ NO — parsing regex/HTML determinístico  
**Output:** `evidence/{ticket_id}/ticket.json`

---

### Stage 2 — ui_map (`ui_map_builder.py`)

**Qué hace:** Abre la pantalla web con Playwright, inspecciona el DOM y construye un mapa de
selectores (inputs, botones, panels, selects, links) identificados por nombre semántico.

**Llamadas externas:** Playwright (Chromium) contra la app web  
**LLM:** ❌ NO — análisis DOM determinístico  
**Output:** `cache/ui_maps/{pantalla}.json`

---

### Stage 3 — compiler (`uat_scenario_compiler.py`)

**Qué hace:** Convierte cada ítem del plan de pruebas en un scenario JSON estructurado con
pasos (`accion`, `target`, `valor`) y oráculos (`tipo`, `target`, `valor`).

**LLM:** ✅ SÍ — `gpt-4.1-mini`  
**Cuándo:** por cada ítem del plan de pruebas  
**Fallback:** si el LLM falla → heurísticas regex  
**Output:** `evidence/{ticket_id}/scenarios.json`

---

### Stage 3b — preconditions (`uat_precondition_checker.py`)

**Qué hace:** Verifica en BD dev que los datos requeridos por los escenarios existan
(ej: INSERTs RIDIOMA aplicados, registros de referencia presentes).

**Llamadas externas:** BD dev (pyodbc / sqlcmd) — solo SELECT  
**LLM:** ❌ NO  
**Comportamiento si BD no disponible:** warning + continúa (no fatal)

---

### Stage 4 — generator (`playwright_test_generator.py`)

**Qué hace:** Genera archivos TypeScript de Playwright (`p01_test.ts`, etc.) a partir del
`scenarios.json`. Renderizado Jinja2 determinístico — sin interpretación.

**LLM:** ❌ NO — rendering Jinja2 puro  
**Output:** `evidence/{ticket_id}/tests/*.ts`

---

### Stage 5 — runner (`uat_test_runner.py`)

**Qué hace:** Ejecuta cada archivo TypeScript con `npx playwright test`, captura screenshots
y guarda el resultado JSON de Playwright.

**Llamadas externas:** Playwright (Chromium) contra la app web  
**LLM:** ❌ NO  
**Output:** `evidence/{ticket_id}/runner_output.json` + capturas PNG

---

### Stage 6 — evaluator (`uat_assertion_evaluator.py`)

**Qué hace:** Evalúa los oráculos de cada scenario contra el DOM/resultado capturado.
Determina PASS / FAIL / BLOCKED por scenario.

**LLM:** ❌ NO — comparación determinística  
**Output:** actualiza `runner_output.json` con veredictos por escenario

---

### Stage 7 — failure_analyzer (`uat_failure_analyzer.py`)

**Qué hace:** Para cada scenario con FAIL, clasifica la causa del fallo y genera una hipótesis
en lenguaje natural.

**Categorías de fallo:** `selector_not_found` / `text_not_present` / `timeout` /
`regression` / `precondition_not_met` / `environment_error` / `unknown`

**LLM:** ✅ SÍ — `gpt-4.1` (solo si hay FAILs)  
**Orden de análisis:**
1. Heurística primero (rápida, sin costo LLM)
2. Si la heurística no resuelve → llama LLM  

**Fallback:** si LLM falla → `category=unknown, confidence=low`  
**Output:** `evidence/{ticket_id}/failure_analysis.json`

---

### Stage 8 — dossier (`uat_dossier_builder.py`)

**Qué hace:** Arma el dossier final del QA con resumen ejecutivo, tabla de casos, capturas
y recomendaciones para el QA humano.

**LLM:** ✅ SÍ — `gpt-4.1` — **2 llamadas:**
1. `executive_summary` — resumen ejecutivo del resultado
2. `recommendations` — recomendaciones para el QA humano

**Fallback:** si LLM falla → template string fijo  
**Output:** `evidence/{ticket_id}/dossier.html` + `dossier.md`

---

### Stage 9 — publisher (`ado_evidence_publisher.py`)

**Qué hace:** En modo `publish`, postea el dossier como comentario en el ticket ADO.
En modo `dry-run`, solo genera los archivos sin publicar.

**Llamadas externas:** `ado.py` → ADO REST API (POST comentario)  
**LLM:** ❌ NO  
**Seguridad:** nunca cambia el estado del ticket — solo agrega comentario

---

## Resumen: ¿cuándo actúa el LLM?

| Etapa | LLM | Modelo | Propósito | Fallback |
|---|---|---|---|---|
| compiler | ✅ | gpt-4.1-mini | Convierte plan de pruebas → scenarios JSON | heurísticas regex |
| failure_analyzer | ✅ (solo si hay FAILs) | gpt-4.1 | Clasifica causa del fallo + hipótesis | `unknown` |
| dossier (summary) | ✅ | gpt-4.1 | Genera resumen ejecutivo | template fijo |
| dossier (recs) | ✅ | gpt-4.1 | Genera recomendaciones para QA humano | heurísticas |
| QA Agent workbench | ✅ | configurable | Veredicto PASS/FAIL textual | — |
| Todas las demás | ❌ | — | ADO API / Playwright / BD / Jinja2 | — |

---

## Routing del LLM (`llm_client.py`)

Cada llamada LLM de este pipeline usa la siguiente jerarquía de backends:

```
STACKY_LLM_BACKEND=vscode_bridge  (default)
    → ¿está 127.0.0.1:5052 activo?
        → SÍ  → llama a la VS Code Extension de Stacky (bridge local)
        → NO  → fallback a copilot_direct

STACKY_LLM_BACKEND=copilot_direct
    → POST directo a models.github.ai/inference con gh auth token

STACKY_LLM_BACKEND=mock
    → respuesta hardcodeada, sin red (para tests)
```

**VS Code Copilot Chat actúa solo si** `STACKY_LLM_BACKEND=vscode_bridge` (default) **y la
VS Code Extension de Stacky está corriendo en el puerto 5052.** Si no está activa, el pipeline
usa la GitHub Models API directamente y VS Code no interviene.
