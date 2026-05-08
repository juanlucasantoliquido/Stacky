---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `uat_dossier_builder.py`

## 1. Propósito

Ensambla el **dossier final UAT** a partir de los outputs de todas las etapas del pipeline: ticket, escenarios, resultado del runner. Produce tres artefactos: un JSON canónico (`dossier.json`), un Markdown legible (`DOSSIER_UAT.md`) y un HTML formateado para publicar en ADO (`ado_comment.html`). Es la última etapa del pipeline antes de la publicación.

## 2. Alcance

**Hace:**
- Lee los artefactos de `evidence/<ticket>/` producidos por las etapas anteriores
- Calcula el veredicto global del ticket (`PASS`, `FAIL`, `BLOCKED`, `MIXED`)
- Genera el `executive_summary` en lenguaje humano via LLM (3-5 líneas)
- Procesa el HTML del comentario ADO via `ado_html_postprocessor.py` para garantizar compatibilidad con el editor de texto enriquecido de ADO
- Inyecta el marker de idempotencia `<!-- stacky-qa-uat:run id="<run_id>" hash="<sha256>" -->`

**NO hace:**
- Publica en ADO — eso lo hace `ado_evidence_publisher.py`
- Evalúa assertions individuales — el runner ya las evaluó
- Accede a la red o a ADO

## 3. Inputs

### CLI

```bash
python uat_dossier_builder.py \
  --ticket 70 \
  --evidence evidence/70/ \
  [--run-id <uuid>] \
  [--verbose]
```

| Arg | Tipo | Descripción |
|---|---|---|
| `--ticket <id>` | int | ID del ticket |
| `--evidence <dir>` | str | Carpeta raíz con los artefactos del pipeline |
| `--run-id <uuid>` | str | UUID del run; si no se especifica, se genera uno nuevo |
| `--verbose` | flag | Logs detallados a stderr |

### Archivos leídos de `evidence/<ticket>/`

| Archivo | Producido por | Requerido |
|---|---|---|
| `ticket.json` | `uat_ticket_reader.py` | ✅ |
| `scenarios.json` | `uat_scenario_compiler.py` | ✅ |
| `runner_output.json` | `uat_test_runner.py` | ✅ |
| `<scenario>/trace.zip`, `video.webm`, screenshots | runner | Para FAIL |

### LLM

Usa **GPT-4.1** para generar el `executive_summary` (3-5 líneas en español, lenguaje humano). Input: veredicto, título del ticket, lista de resultados por escenario. Validación: máx. 600 caracteres; rechaza si menciona acciones que el agente no hizo. Fallback: plantilla determinista con campos fijos.

## 4. Outputs

### JSON a stdout

```json
{
  "ok": true,
  "run_id": "uuid-...",
  "schema_version": "qa-uat-dossier/1.0",
  "ticket_id": 70,
  "ticket_title": "RF-003 Validación del comportamiento de combinación de filtros",
  "screen": "FrmAgenda.aspx",
  "verdict": "PASS",
  "executive_summary": "Los 6 escenarios ejecutables del ticket 70 pasaron...",
  "context": {
    "build_commit": "d1aec6d",
    "environment": "qa-local",
    "agent_version": "qa-uat/0.1.0",
    "models_used": {"executive_summary": "gpt-4.1"}
  },
  "scenarios": [...],
  "failures": [],
  "recommendation_for_human_qa": [...],
  "next_steps": [...],
  "meta": {"tool": "uat_dossier_builder", "version": "1.0.0", "duration_ms": 1800}
}
```

### Archivos escritos en `evidence/<ticket>/`

| Archivo | Descripción |
|---|---|
| `dossier.json` | JSON canónico del dossier (misma estructura que stdout) |
| `DOSSIER_UAT.md` | Markdown legible con tablas de escenarios, fallas, artefactos |
| `ado_comment.html` | HTML procesado por `ado_html_postprocessor.py`, con marker de idempotencia |

## 5. Contrato de uso

**Precondiciones:**
- `ticket.json`, `scenarios.json` y `runner_output.json` existen en `evidence/<ticket>/`
- `runner_output.json` tiene al menos un run en `runs[]`

**Postcondiciones:**
- Los tres artefactos existen en `evidence/<ticket>/`
- `ado_comment.html` contiene el marker `<!-- stacky-qa-uat:run id="..." hash="..." -->`
- El `hash` del comentario es el SHA-256 del contenido de `ado_comment.html` (sin el marker mismo)

**Idempotencia:** sí — mismo `--run-id` con mismos inputs produce el mismo dossier

### Cálculo del veredicto global

| Condición | Veredicto |
|---|---|
| Todos los escenarios son `pass` | `PASS` |
| Al menos 1 escenario es `fail` y ninguno `pass` | `FAIL` |
| Al menos 1 es `fail` y al menos 1 es `pass` | `FAIL` |
| Todos los no-pass son `blocked` (sin `fail` real) | `BLOCKED` |
| Hay `fail` + `blocked` simultáneos | `MIXED` |

## 6. Validaciones internas

- Si falta alguno de los archivos de entrada requeridos → falla con `missing_artifact`
- El `executive_summary` generado por LLM no puede mencionar verbos de acción que el agente no hizo (ej. "se cerró el ticket", "se corrigió el código") → validador de texto post-LLM rechaza y usa fallback determinista
- El marker HTML debe estar al inicio de `ado_comment.html`; si `ado_html_postprocessor` lo remueve → error `marker_stripped`

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `missing_artifact` | Falta `ticket.json`, `scenarios.json` o `runner_output.json` |
| `render_failed` | Fallo en el template Jinja2 del Markdown o HTML |
| `marker_stripped` | El postprocessor de HTML eliminó el marker de idempotencia |
| `llm_summary_invalid` | LLM generó un summary con contenido prohibido y el fallback también falló (raro) |

## 8. Dependencias

- `jinja2` — para renderizar `dossier.md.j2` y `ado_comment.html.j2`
- `ado_html_postprocessor.py` — para procesar el HTML del comentario ADO
- LLM Router (`llm_router.py`) — para el executive summary
- Python 3.8+ stdlib + `hashlib`, `uuid`

## 9. Ejemplos de uso

```bash
# Construir dossier del ticket 70
python uat_dossier_builder.py --ticket 70 --evidence evidence/70/

# Con run-id fijo (para reproducibilidad)
python uat_dossier_builder.py --ticket 70 --evidence evidence/70/ --run-id "abc-123"

# Ver el veredicto
python uat_dossier_builder.py --ticket 70 --evidence evidence/70/ \
  | python -c "import sys,json; r=json.load(sys.stdin); print('Veredicto:', r['verdict'])"
```

## 10. Criterios de aceptación

- [ ] Con todos los artefactos del ticket 70 presentes: genera los 3 artefactos sin errores
- [ ] `ado_comment.html` contiene el marker de idempotencia al inicio
- [ ] El `hash` en el marker es SHA-256 del contenido del comentario (reproducible)
- [ ] Veredicto global se calcula correctamente para cada caso (`PASS`, `FAIL`, `BLOCKED`, `MIXED`)
- [ ] Sin `runner_output.json` → `{"ok": false, "error": "missing_artifact"}`
- [ ] `dossier.json` valida contra `schemas/dossier.schema.json`
- [ ] El `executive_summary` tiene ≤ 600 caracteres y no menciona acciones prohibidas

## 11. Tests requeridos

```
tests/unit/test_uat_dossier_builder.py

test_dossier_built_successfully_for_ticket_70
test_ado_comment_contains_idempotence_marker
test_hash_is_sha256_of_comment_content
test_verdict_pass_when_all_pass
test_verdict_fail_when_one_fails
test_verdict_blocked_when_all_blocked
test_verdict_mixed_when_fail_and_blocked
test_missing_artifact_returns_error
test_executive_summary_length_constraint
test_dossier_json_validates_against_schema
```
