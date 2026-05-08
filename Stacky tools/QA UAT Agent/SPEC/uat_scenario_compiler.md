---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `uat_scenario_compiler.py`

## 1. Propósito

Convierte el JSON normalizado de `uat_ticket_reader.py` en una lista de **`ScenarioSpec`** ejecutables. Cada `ScenarioSpec` es la representación canónica de un caso de prueba del plan del ticket, con pantalla, precondiciones, pasos y oráculos bien definidos. Es la entrada del `playwright_test_generator.py`.

## 2. Alcance

**Hace:**
- Parsea cada `P0N` del plan de pruebas en `{pantalla, precondiciones, pasos, oraculos, datos_requeridos}`
- Descarta items fuera de alcance (`P07` tipo "performance") marcándolos como `OUT_OF_SCOPE_NEEDS_HUMAN`
- Rechaza `ScenarioSpec` con campos vacíos, pantalla no soportada o placeholders (`[completar]`, `...`)
- Persiste el resultado en `evidence/<ticket>/scenarios.json`

**NO hace:**
- Accede a ADO, UI o BD
- Genera código Playwright
- Verifica precondiciones en el entorno real — solo las declara

## 3. Inputs

### CLI (stdin o archivo)

```bash
# Desde stdin
python uat_ticket_reader.py --ticket 70 | python uat_scenario_compiler.py

# Desde archivo
python uat_scenario_compiler.py --input evidence/70/ticket.json

# Con filtro de pantalla
python uat_scenario_compiler.py --input evidence/70/ticket.json --scope screen=FrmAgenda.aspx
```

| Arg | Tipo | Descripción |
|---|---|---|
| `--input <path>` | str | Ruta al JSON del ticket reader. Si no se especifica, lee de stdin |
| `--scope screen=<nombre>` | str | Filtra y procesa solo los escenarios de esa pantalla |
| `--ticket <id>` | int | Alternativa: leer directamente `evidence/<id>/ticket.json` |
| `--verbose` | flag | Logs detallados a stderr |

### LLM

Usa **GPT-5 mini** para parsear cada `P0N` en `{acciones, oráculo}` cuando el texto libre no sigue un patrón estructurado. Output schema Pydantic v2 estricto.

Fallback: regex + heurística por palabras clave (`"debe aparecer"`, `"no debe aparecer"`, `"verificar que"`, etc.).

## 4. Outputs

### JSON a stdout

```json
{
  "ok": true,
  "ticket_id": 70,
  "compiled": 6,
  "out_of_scope": 1,
  "scenarios": [
    {
      "scenario_id": "P01",
      "ticket_id": 70,
      "pantalla": "FrmAgenda.aspx",
      "titulo": "Búsqueda SIN filtros activos muestra todos los lotes",
      "precondiciones": ["Login como PABLO", "Datos en BD: lote empresa=0001"],
      "pasos": [
        {"accion": "navigate", "target": "FrmAgenda.aspx", "valor": null},
        {"accion": "click", "target": "btn_buscar", "valor": null}
      ],
      "oraculos": [
        {"tipo": "count_gt", "target": "grid_agenda_aut", "valor": "0"},
        {"tipo": "invisible", "target": "msg_lista_vacia", "valor": null}
      ],
      "datos_requeridos": [{"tabla": "RAGEN", "filtro": "OGEMPRESA='0001'"}],
      "origen": {"ticket_section": "plan_pruebas", "item_id": "P01"}
    }
  ],
  "out_of_scope_items": [
    {"id": "P07", "razon": "OUT_OF_SCOPE_NEEDS_HUMAN", "descripcion": "Performance con 3+ filtros"}
  ],
  "meta": {"tool": "uat_scenario_compiler", "version": "1.0.0", "duration_ms": 1240}
}
```

### Archivo persistido

`evidence/<ticket_id>/scenarios.json`

## 5. Contrato de uso

**Precondiciones:**
- Input es JSON válido con la estructura de `uat_ticket.schema.json`
- Al menos un `P0N` en `plan_pruebas`

**Postcondiciones:**
- Cada `ScenarioSpec` en `scenarios[]` tiene `pantalla`, `pasos` (≥ 1) y `oraculos` (≥ 1) no vacíos
- Ningún `ScenarioSpec` contiene placeholders en sus campos
- Items descartados van a `out_of_scope_items[]`

**Idempotencia:** sí — mismo input produce mismo output

## 6. Validaciones internas

- Rechaza `ScenarioSpec` con `pantalla` fuera de `supported_screens` → `screen_not_supported_yet`
- Rechaza `ScenarioSpec` con `pasos: []` o `oraculos: []` → `incomplete_scenario`
- Rechaza `ScenarioSpec` con `"[completar]"`, `"..."` o `"TBD"` en cualquier campo → `placeholder_detected`
- LLM retorna schema inválido → reintento 1 vez con feedback; si persiste → `needs_human_review` (no se descarta, se marca para revisión humana)
- Oracle tipo `contains_semantic` requiere que `valor` sea una frase descriptiva, no un localizador CSS

### Tipos de oráculo soportados

| Tipo | Descripción |
|---|---|
| `equals` | Texto exacto igual |
| `contains_literal` | Texto contiene substring literal |
| `contains_semantic` | Texto semánticamente equivalente (evaluado por LLM en assertion_evaluator) |
| `count_gt` | Grid tiene más de N filas |
| `count_eq` | Grid tiene exactamente N filas |
| `visible` | Elemento visible en el DOM |
| `invisible` | Elemento no visible en el DOM |
| `state` | Elemento tiene estado específico (`disabled`, `checked`, etc.) |

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `invalid_input_json` | El input no es JSON válido o no tiene `plan_pruebas` |
| `no_test_plan_in_ticket` | `plan_pruebas` está vacío |
| `all_scenarios_out_of_scope` | Todos los `P0N` fueron descartados |
| `screen_not_supported_yet` | La pantalla del escenario no está en `supported_screens` |
| `scenario_compilation_failed` | LLM + fallback fallaron en parsear un `P0N` |

## 8. Dependencias

- LLM Router (`llm_router.py`) — para parsing asistido
- `pydantic` v2 — para validación del schema de `ScenarioSpec`
- Python 3.8+ stdlib

## 9. Ejemplos de uso

```bash
# Pipeline completo
python uat_ticket_reader.py --ticket 70 | python uat_scenario_compiler.py

# Solo escenarios de FrmAgenda
python uat_scenario_compiler.py \
  --input evidence/70/ticket.json \
  --scope screen=FrmAgenda.aspx

# Ver cuántos escenarios compilaron
python uat_scenario_compiler.py --input evidence/70/ticket.json | python -c \
  "import sys,json; d=json.load(sys.stdin); print(f'Compilados: {d[\"compiled\"]}, Fuera de scope: {d[\"out_of_scope\"]}')"
```

## 10. Criterios de aceptación

- [ ] El plan de pruebas del ticket 70 produce ≥ 6 `ScenarioSpec` válidos y 1 `OUT_OF_SCOPE`
- [ ] Cada `ScenarioSpec` tiene `pantalla == "FrmAgenda.aspx"`, `pasos ≥ 1`, `oraculos ≥ 1`
- [ ] Ningún `ScenarioSpec` contiene placeholders
- [ ] Input con `plan_pruebas: []` retorna `{"ok": false, "error": "no_test_plan_in_ticket"}`
- [ ] El JSON retornado valida contra `schemas/scenario_spec.schema.json`
- [ ] `P07` (performance) queda en `out_of_scope_items` con `razon: OUT_OF_SCOPE_NEEDS_HUMAN`

## 11. Tests requeridos

```
tests/unit/test_uat_scenario_compiler.py

test_ticket_70_compiles_6_scenarios_and_1_out_of_scope
test_each_scenario_has_required_fields
test_placeholder_scenario_rejected
test_empty_plan_returns_error
test_unsupported_screen_marked_blocked
test_llm_fallback_on_regex
test_output_validates_against_schema
```
