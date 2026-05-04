---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `uat_test_runner.py`

## 1. Propósito

Ejecuta los archivos `.spec.ts` generados por `playwright_test_generator.py` y captura evidencia estructurada: trace, video, screenshots, console log y network log. Produce un JSON con el resultado de cada escenario y la ubicación de cada artefacto de evidencia.

## 2. Alcance

**Hace:**
- Ejecuta cada `.spec.ts` en serie (no paralelo en MVP) via `npx playwright test`
- Captura: trace.zip, video.webm, screenshots por paso, console log JSON, network log JSON
- Persiste la evidencia en `evidence/<ticket>/<scenario_id>/`
- Reporta el resultado de cada escenario: `pass`, `fail`, `blocked` (si falla por error técnico, no por assertion)
- Distingue entre un escenario que falla por una assertion (`fail`) vs uno que crashea por error técnico (`blocked: RUNTIME_ERROR`)

**NO hace:**
- Evalúa si el resultado es correcto a nivel de negocio — eso lo hace `uat_assertion_evaluator`
- Genera tests
- Hace login — el login está en el `beforeEach` de cada `.spec.ts`
- Ejecuta tests en paralelo en MVP (`retries: 0`)

## 3. Inputs

### CLI

```bash
python uat_test_runner.py \
  --tests-dir evidence/70/tests/ \
  --evidence-out evidence/70/ \
  [--headed] \
  [--timeout-ms 90000] \
  [--verbose]
```

| Arg | Tipo | Descripción |
|---|---|---|
| `--tests-dir <dir>` | str | Carpeta con los `.spec.ts` a ejecutar |
| `--evidence-out <dir>` | str | Carpeta raíz de evidencia; se crean subcarpetas por escenario |
| `--headed` | flag | Ejecutar en modo headed (default: según `STACKY_QA_UAT_HEADLESS` env) |
| `--timeout-ms <n>` | int | Timeout por test en ms; default `90000` (cubre login ASP.NET + nav + steps) |
| `--verbose` | flag | Pasar `--reporter=list` a Playwright + logs a stderr |

### Env vars heredadas por los tests

Los `.spec.ts` leen estas vars de `process.env`:

| Var | Descripción |
|---|---|
| `AGENDA_WEB_BASE_URL` | URL base de la Agenda Web |
| `AGENDA_WEB_USER` | Usuario de login |
| `AGENDA_WEB_PASS` | Password de login |
| `STACKY_QA_UAT_HEADLESS` | `1`=headless, `0`=headed (default `0`) |

## 4. Outputs

### JSON a stdout

```json
{
  "ok": true,
  "ticket_id": 70,
  "total": 6,
  "pass": 5,
  "fail": 1,
  "blocked": 0,
  "runs": [
    {
      "scenario_id": "P01",
      "spec_file": "evidence/70/tests/P01_busqueda_sin_filtros.spec.ts",
      "status": "pass",
      "duration_ms": 4321,
      "artifacts": {
        "trace": "evidence/70/P01/trace.zip",
        "video": "evidence/70/P01/video.webm",
        "screenshots": [
          "evidence/70/P01/step_00_setup.png",
          "evidence/70/P01/step_01_after.png"
        ],
        "console_log": "evidence/70/P01/console.json",
        "network_log": "evidence/70/P01/network.json"
      },
      "raw_stdout": "...",
      "raw_stderr": ""
    },
    {
      "scenario_id": "P04",
      "status": "fail",
      "duration_ms": 5200,
      "artifacts": {"trace": "...", "video": "...", "screenshots": [...], ...},
      "assertion_failures": [
        {
          "message": "P04: mensaje lista vacía - Expected: 'No hay lotes agendados', Received: ''",
          "expected": "No hay lotes agendados",
          "actual": ""
        }
      ]
    }
  ],
  "meta": {"tool": "uat_test_runner", "version": "1.0.0", "duration_ms": 32400}
}
```

### Artefactos en disco

Por cada escenario: `evidence/<ticket>/<scenario_id>/`
- `trace.zip` — trace completo de Playwright
- `video.webm` — video de la sesión (siempre; en MPV retener-siempre)
- `step_NN_{before,after}.png` — screenshots por paso
- `console.json` — `[{type, text, location}]` de mensajes de consola del browser
- `network.json` — `[{method, url, status, duration_ms}]` de requests de red

## 5. Contrato de uso

**Precondiciones:**
- `node` y `npx` instalados y en PATH
- Playwright instalado en el proyecto Node (`npx playwright install chromium`)
- Los `.spec.ts` compilan (esto fue validado por `playwright_test_generator.py`)
- Credenciales en env vars
- Agenda Web accesible

**Postcondiciones:**
- Por cada `.spec.ts` en `--tests-dir`, existe una entrada en `runs[]`
- Por cada run, la carpeta `evidence/<ticket>/<scenario_id>/` existe con los artefactos declarados en `artifacts`
- Si `status: blocked`, los artefactos existen hasta el punto en que ocurrió el crash

**Idempotencia:** sí — reejecutar sobreescribe los artefactos del run anterior

## 6. Validaciones internas

- Si `--tests-dir` está vacío o no contiene `.spec.ts` → falla con `no_tests_found`
- Si `node`/`npx` no están en PATH → falla con `playwright_not_available`
- Si la ejecución de un test termina con exit code distinto de 0 pero hay `assertion_failures` → `status: fail`
- Si la ejecución termina con exit code distinto de 0 y el stderr contiene `Error:` (no assertion) → `status: blocked, reason: RUNTIME_ERROR`
- El runner captura stdout+stderr del proceso Playwright para incluirlos en `raw_stdout`/`raw_stderr`

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `no_tests_found` | `--tests-dir` vacío o sin `.spec.ts` |
| `playwright_not_available` | `node` o `npx` no en PATH |
| `browser_launch_failed` | Playwright no puede iniciar Chromium (drivers desactualizados) |
| `runner_timeout` | El runner completo supera 5x el `--timeout-ms` total |
| `evidence_dir_write_failed` | No se puede escribir en `--evidence-out` |

## 8. Dependencias

- `node` + `npx` en PATH
- `@playwright/test` instalado en el proyecto Node
- Python 3.8+ stdlib (`subprocess`, `json`, `pathlib`)
- Sin LLM

## 9. Ejemplos de uso

```bash
# Ejecutar todos los tests del ticket 70
python uat_test_runner.py \
  --tests-dir evidence/70/tests/ \
  --evidence-out evidence/70/

# Ejecutar en modo headed (ver el browser)
python uat_test_runner.py \
  --tests-dir evidence/70/tests/ \
  --evidence-out evidence/70/ \
  --headed

# Resumen rápido del resultado
python uat_test_runner.py \
  --tests-dir evidence/70/tests/ \
  --evidence-out evidence/70/ \
  | python -c "import sys,json; r=json.load(sys.stdin); print(f'PASS: {r[\"pass\"]}, FAIL: {r[\"fail\"]}, BLOCKED: {r[\"blocked\"]}')"
```

## 10. Criterios de aceptación

- [ ] Para los 6 tests del ticket 70: `total == 6` y todos los artefactos existen en disco
- [ ] Un test con assertion fallida → `status: fail` con `assertion_failures` poblado
- [ ] Un test que crashea por error técnico → `status: blocked, reason: RUNTIME_ERROR` con trace adjunto
- [ ] Sin `node`/`npx` → `{"ok": false, "error": "playwright_not_available"}`
- [ ] Los artefactos `trace.zip` y `video.webm` existen para cada run
- [ ] El JSON retornado valida contra `schemas/runner_output.schema.json`

## 11. Tests requeridos

```
tests/unit/test_uat_test_runner.py

test_no_tests_found_returns_error
test_playwright_not_available_returns_error
test_assertion_failure_marks_scenario_fail
test_runtime_error_marks_scenario_blocked
test_artifacts_created_for_each_run
test_evidence_directory_structure_correct
test_output_validates_against_schema
```
