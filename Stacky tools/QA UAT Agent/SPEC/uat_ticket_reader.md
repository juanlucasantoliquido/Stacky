---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `uat_ticket_reader.py`

## 1. Propósito

Lee un ticket de Azure DevOps en modo solo-lectura via **ADO Manager** y devuelve un JSON normalizado con toda la información necesaria para que el pipeline UAT pueda compilar escenarios sin necesidad de volver a leer ADO. Es la **única entrada del pipeline**; todos los pasos subsiguientes consumen su output.

## 2. Alcance

**Hace:**
- Llama `python ado.py get <id>` y `python ado.py comments <id>` para extraer el ticket
- Clasifica cada comentario en uno de los roles: `analisis_funcional`, `analisis_tecnico`, `implementacion`, `qa`, `otros`
- Extrae el plan de pruebas (`P01..P0N`) del comentario de análisis técnico
- Detecta precondiciones (scripts RIDIOMA, flags Web.config, scripts SQL) mencionadas en el análisis técnico
- Valida que el ticket está listo para UAT (tiene análisis técnico + plan de pruebas)
- Persiste el resultado en `evidence/<ticket>/ticket.json`

**NO hace:**
- Modifica nada en ADO
- Parsea adjuntos binarios (solo texto/HTML de los campos del ticket)
- Accede directamente a la API REST de ADO (siempre via ADO Manager)

## 3. Inputs

### CLI

```bash
python uat_ticket_reader.py --ticket <id> [--cache] [--ado-path <ruta_a_ado.py>] [--verbose]
```

| Arg | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `--ticket <id>` | int | ✅ | ID del work item en ADO |
| `--cache` | flag | ❌ | Reusar la última lectura en `evidence/<id>/ticket.json` si existe |
| `--ado-path <path>` | str | ❌ | Ruta al `ado.py`; default: `Tools/Stacky/Stacky tools/ADO Manager/ado.py` |
| `--verbose` | flag | ❌ | Logs detallados a stderr |

### Env vars

Ninguna propia. Las credenciales de ADO las gestiona ADO Manager via su `ado-config.json`.

### LLM (clasificación de comentarios)

Usa **GPT-5 mini** via `llm_router` para clasificar el rol de cada comentario cuando no tiene un encabezado claro. Input al LLM: texto del comentario (máx. 2000 chars). Output esperado: `{"role": "analisis_funcional"|"analisis_tecnico"|"implementacion"|"qa"|"otros"}`.

Fallback determinista: regex sobre encabezados HTML (`<h1>`, `<h2>`) buscando palabras clave (`ANALISIS TECNICO`, `IMPLEMENTACION`, `QA`, etc.).

## 4. Outputs

### JSON a stdout

```json
{
  "ok": true,
  "ticket": {
    "id": 70,
    "title": "RF-003 Validación del comportamiento de combinación de filtros",
    "state": "Done",
    "type": "Task",
    "url": "https://dev.azure.com/..."
  },
  "description_md": "<html>...</html>",
  "comments": [
    {
      "id": 1, "author": "Juan", "date": "2026-04-20T...",
      "text_md": "...", "role": "analisis_tecnico"
    }
  ],
  "analisis_tecnico": "...(texto completo del comentario)...",
  "plan_pruebas": [
    {
      "id": "P01",
      "descripcion": "Búsqueda SIN filtros activos muestra todos los lotes",
      "datos": "usuario=PABLO, empresa=0001",
      "esperado": "Grid con ≥ 1 resultado, sin mensaje de lista vacía"
    }
  ],
  "notas_qa": ["Aplicar 3 INSERTs RIDIOMA antes de ejecutar P04"],
  "adjuntos": [{"name": "Video_Task_70.zip", "url": "..."}],
  "precondiciones_detected": [
    {"tipo": "RIDIOMA_INSERT", "recurso": "IDTEXTO=9296", "evidencia": "INSERT INTO RIDIOMA..."},
    {"tipo": "BUILD_DEPLOY", "recurso": "AgendaWeb.sln", "evidencia": "commit d1aec6d"}
  ],
  "meta": {"tool": "uat_ticket_reader", "version": "1.0.0", "duration_ms": 843}
}
```

### Archivo persistido

`evidence/<ticket_id>/ticket.json` — mismo contenido que stdout.

## 5. Contrato de uso

**Precondiciones:**
- ADO Manager configurado y accesible (`ado-config.json` válido)
- El ticket existe en ADO

**Postcondiciones:**
- No modifica nada en ADO
- Crea (o sobreescribe si no se usa `--cache`) `evidence/<id>/ticket.json`

**Idempotencia:** sí (misma lectura → mismo JSON; con `--cache` evita rellamar ADO)

## 6. Validaciones internas

- `--ticket` debe ser entero positivo; falla con `invalid_id`
- Si ADO Manager retorna `ok:false` → propaga el error con `error: ado_error`
- Si el ticket no tiene ningún comentario con rol `analisis_tecnico` → falla con `missing_technical_analysis`
- Si el plan de pruebas está vacío (ningún `P0N` extraído) → falla con `no_test_plan_in_ticket`
- El LLM retorna un valor fuera del enum de roles → reintenta 1 vez; si persiste → rol `otros`

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `invalid_id` | `--ticket` no es entero positivo |
| `ado_error` | ADO Manager retorna `ok:false` |
| `ticket_not_found` | ADO retorna HTTP 404 |
| `missing_technical_analysis` | Ningún comentario clasificado como `analisis_tecnico` |
| `no_test_plan_in_ticket` | Sin items `P01..P0N` extraídos |
| `parse_failed` | Error inesperado al parsear el HTML del ticket |
| `llm_unavailable` | LLM inaccesible Y fallback determinista tampoco clasifica nada (raro) |

## 8. Dependencias

- ADO Manager (`ado.py`) — invocado via subprocess
- LLM Router (`llm_router.py`) — para clasificación de comentarios (opcional; con fallback)
- Python 3.8+ stdlib + `subprocess`, `re`, `json`

## 9. Ejemplos de uso

```bash
# Leer ticket 70 y persistir en evidence/70/ticket.json
python uat_ticket_reader.py --ticket 70

# Reusar cache si ya fue leído
python uat_ticket_reader.py --ticket 70 --cache

# Parsear el output con jq
python uat_ticket_reader.py --ticket 70 | python -m json.tool

# Encadenar con el compilador de escenarios
python uat_ticket_reader.py --ticket 70 | python uat_scenario_compiler.py
```

## 10. Criterios de aceptación

- [ ] Para el ticket 70: retorna `ok:true`, `plan_pruebas` con 7 items `P01..P07`, `precondiciones_detected` con los 3 INSERTs RIDIOMA
- [ ] Para un ticket sin análisis técnico: retorna `{"ok": false, "error": "missing_technical_analysis"}`
- [ ] Para un ID inexistente: retorna `{"ok": false, "error": "ticket_not_found"}`
- [ ] Sin `ado-config.json`: retorna `{"ok": false, "error": "ado_error", "message": "..."}`
- [ ] Con `--cache` y archivo existente: no llama a `ado.py` (verificable por ausencia de tráfico de red)
- [ ] El JSON retornado valida contra `schemas/uat_ticket.schema.json`

## 11. Tests requeridos

```
tests/unit/test_uat_ticket_reader.py

test_ticket_70_returns_7_scenarios
test_ticket_without_analysis_returns_blocked
test_nonexistent_ticket_returns_not_found
test_cache_flag_skips_ado_call
test_output_validates_against_schema
test_preconditions_detected_ridioma_inserts
test_llm_fallback_on_regex_match
```
