---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — `ui_map_builder.py`

## 1. Propósito

Inspecciona una pantalla del Agenda Web en vivo usando Playwright y produce un **UI map** persistente: un JSON que lista todos los elementos accesibles (inputs, selects, botones, grids, mensajes) con sus selectores recomendados y alias semánticos. Es el **contrato físico entre la pantalla y los tests**; el `playwright_test_generator.py` solo puede usar selectores que estén en este mapa.

## 2. Alcance

**Hace:**
- Hace login en la Agenda Web con las credenciales de env
- Navega a la pantalla indicada
- Extrae elementos accesibles via accessibility tree + DOM queries
- Persiste el UI map en `cache/ui_maps/<pantalla>.json` con hash del DOM
- Invalida y reconstruye la caché si el hash del DOM cambió desde la última captura
- Usa LLM para sugerir alias semánticos legibles por elemento (sin inventar elementos)

**NO hace:**
- Interactúa con la aplicación más allá de navegar a la pantalla
- Genera tests Playwright
- Determina cuál selector usar por escenario — eso lo hace `selector_discovery.py`

## 3. Inputs

### CLI

```bash
python ui_map_builder.py --screen <pantalla> [--rebuild] [--verbose]
```

| Arg | Tipo | Descripción |
|---|---|---|
| `--screen <nombre>` | str | Nombre de la pantalla (ej: `FrmAgenda.aspx`) |
| `--rebuild` | flag | Ignora la caché y reconstruye desde cero |
| `--verbose` | flag | Logs detallados a stderr |

### Env vars

| Var | Requerida | Descripción |
|---|---|---|
| `AGENDA_WEB_BASE_URL` | ✅ | URL base (ej: `http://localhost/AgendaWeb/`) |
| `AGENDA_WEB_USER` | ✅ | Usuario de login |
| `AGENDA_WEB_PASS` | ✅ | Password de login |
| `STACKY_QA_UAT_HEADLESS` | ❌ | `0` (default) para modo headed, `1` para headless |

Credenciales cargables desde `Tools/Stacky/.secrets/agenda_web.env`.

### LLM

Usa **GPT-5 mini** para sugerir `alias_semantic` para cada elemento. Input: lista de elementos `[{kind, role, label, asp_id}]`. Output: `[{asp_id, alias_semantic}]`.

Validación: el alias debe seguir el patrón `(select|input|btn|grid|panel|msg)_<nombre>`. Fallback: alias = camelCase del label o del asp_id.

## 4. Outputs

### JSON a stdout

```json
{
  "ok": true,
  "screen": "FrmAgenda.aspx",
  "hash": "sha256:abc123...",
  "captured_at": "2026-05-02T14:32:00Z",
  "url": "http://localhost/AgendaWeb/FrmAgenda.aspx",
  "elements": [
    {
      "kind": "select",
      "role": "combobox",
      "label": "Empresa",
      "asp_id": "ddlEmpresa",
      "data_testid": null,
      "selector_recommended": "#ddlEmpresa",
      "robustness": "high",
      "alias_semantic": "select_empresa",
      "position": {"x": 120, "y": 80}
    },
    {
      "kind": "button",
      "role": "button",
      "label": "Buscar",
      "asp_id": "btnOk",
      "data_testid": null,
      "selector_recommended": "input[value='Buscar']",
      "robustness": "medium",
      "alias_semantic": "btn_buscar",
      "position": {"x": 400, "y": 180}
    }
  ],
  "warnings": [
    "3 elementos con robustness=low: requieren data-testid del dev"
  ],
  "meta": {"tool": "ui_map_builder", "version": "1.0.0", "duration_ms": 3200}
}
```

### Archivo persistido

`cache/ui_maps/<pantalla>.json` — mismo contenido que stdout.

## 5. Contrato de uso

**Precondiciones:**
- Playwright instalado
- Agenda Web accesible en `AGENDA_WEB_BASE_URL`
- Credenciales de login válidas en env vars

**Postcondiciones:**
- `cache/ui_maps/<pantalla>.json` existe y tiene hash del DOM actual
- Cada elemento en `elements[]` fue encontrado realmente en el DOM (no inventado)
- Ningún alias semántico fue asignado a un elemento que no existe

**Idempotencia:** sí — si el DOM no cambió (mismo hash), el resultado es idéntico

## 6. Validaciones internas

- Si la env var `AGENDA_WEB_PASS` no está seteada → falla con `missing_env_var` antes de abrir browser
- Si el login falla (DOM no muestra la pantalla esperada) → falla con `login_failed`
- Si la pantalla no carga en 15s → falla con `screen_not_loaded`
- Si el DOM hash del cache coincide y no se usó `--rebuild` → retorna el cache sin abrir browser
- Elementos con `robustness: low` se incluyen pero se listan en `warnings[]`
- Alias LLM fuera del patrón permitido → se usa el fallback (no se aborta la operación)

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `missing_env_var` | `AGENDA_WEB_BASE_URL`, `AGENDA_WEB_USER` o `AGENDA_WEB_PASS` no seteada |
| `playwright_not_installed` | Playwright no instalado |
| `login_failed` | Credenciales inválidas o pantalla de login no encontrada |
| `screen_not_loaded` | Timeout navegando a la pantalla |
| `playwright_crash` | Error inesperado de Playwright |
| `no_elements_found` | El DOM no expone ningún elemento accesible |

## 8. Dependencias

- `playwright` — para navegación y accessibility tree
- LLM Router — para alias semánticos (opcional; con fallback)
- `selector_discovery.py` — helper interno para elegir el selector más robusto por elemento
- Python 3.8+ stdlib + `hashlib`, `json`

## 9. Ejemplos de uso

```bash
# Construir UI map de FrmAgenda.aspx
python ui_map_builder.py --screen FrmAgenda.aspx

# Reconstruir ignorando caché
python ui_map_builder.py --screen FrmAgenda.aspx --rebuild

# Verificar qué selectores se encontraron
python ui_map_builder.py --screen FrmAgenda.aspx | python -c \
  "import sys,json; m=json.load(sys.stdin); [print(e['alias_semantic'], '->', e['selector_recommended'], f'({e[\"robustness\"]})') for e in m['elements']]"
```

## 10. Criterios de aceptación

- [ ] Para `FrmAgenda.aspx`: retorna elementos incluyendo `ddlEmpresa`, `btnOk`, `gvAgendaAut`, con `robustness ≥ medium` para los campos principales
- [ ] Sin env vars → retorna `{"ok": false, "error": "missing_env_var"}` sin abrir browser
- [ ] Con caché válida (hash no cambió) → retorna sin llamar a Playwright
- [ ] Con `--rebuild` → siempre reconstruye aunque exista caché
- [ ] Ningún alias semántico en `elements[]` corresponde a un elemento no encontrado en el DOM
- [ ] El JSON retornado valida contra `schemas/ui_map.schema.json`

## 11. Tests requeridos

```
tests/unit/test_ui_map_builder.py

test_missing_env_var_fails_before_browser
test_cache_hit_skips_playwright
test_rebuild_flag_bypasses_cache
test_alias_semantic_follows_pattern
test_low_robustness_elements_in_warnings
test_login_failed_returns_error
test_output_validates_against_schema
```
