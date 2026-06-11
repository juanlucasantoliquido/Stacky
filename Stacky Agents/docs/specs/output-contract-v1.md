# Output Contract v1 — Stacky Agents

**Versión**: 1.0  
**Estado**: Vigente  
**Fuente de verdad del código**: `backend/services/artifact_validator.py`  
**Test de consistencia**: `backend/tests/test_output_contract_spec.py`

> Este documento se mantiene en sincronía con el validador por CI. Si los campos
> listados aquí divergen de `artifact_validator._required_fields()`, el test
> `test_output_contract_spec.py` fallará.

---

## 1. Canales de entrega (por precedencia)

| Prioridad | Canal | Condición |
|-----------|-------|-----------|
| 1 | **MCP `stacky_submit_comment` / `stacky_submit_task`** | `CLAUDE_CODE_CLI_MCP_ENABLED=true` por proyecto |
| 2 | **File-drop validado** | Siempre disponible; validado por `artifact_validator` antes del cierre del run |
| 3 | **`output_watcher` fallback** | Monitoreo periódico de `Agentes/outputs/`; cierre asíncrono |

---

## 2. Schema de `pending-task.json`

### 2.1 Campos requeridos

<!-- FIELDS_START -->
- `description_html`
- `epic_id`
- `generated_at`
- `generated_by`
- `parent_link_type`
- `plan_de_pruebas_path`
- `rf_id`
- `status`
- `title`
<!-- FIELDS_END -->

### 2.2 Estados permitidos (`status`)

<!-- STATUSES_START -->
- `consumed`
- `pending`
- `pending_manual_creation`
<!-- STATUSES_END -->

### 2.3 Semántica de campos

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `generated_at` | ISO-8601 string | Timestamp UTC de generación del JSON |
| `generated_by` | string | Nombre del agente que generó el archivo (p.ej. `"AnalistaFuncional"`) |
| `epic_id` | integer | **ADO id real** del Epic padre — jamás el ordinal (1, 2, 3…) |
| `rf_id` | string | Slug del RF/historia (p.ej. `"RF-14"`) |
| `title` | string | Título corto de la Task a crear |
| `description_html` | string | Descripción completa en HTML |
| `plan_de_pruebas_path` | string | Path relativo al archivo de plan de pruebas (p.ej. `"plan-de-pruebas.md"`) |
| `parent_link_type` | string | Tipo de link ADO con el Epic padre (p.ej. `"System.LinkTypes.Hierarchy-Reverse"`) |
| `status` | string | Estado del artifact (ver 2.2) |

### 2.4 Regla crítica: ADO id real vs. ordinal

El campo `epic_id` y el nombre del directorio `epic-<ADO_ID>` deben contener el
**ADO id real** del Epic (el entero que Azure DevOps asigna al work item, no el número
ordinal de la épica en el sprint o en el backlog).

Confundir ordinal con ADO id real es la **causa más común** del síntoma "el agente
crea archivos pero la Task no aparece en ADO".

---

## 3. Requisitos de `comment.html`

- Archivo bajo `Agentes/outputs/<ADO_ID>/comment.html`
- Debe existir y no estar vacío
- Debe contener HTML válido (con al menos un tag `<...>`)
- Archivo companion opcional: `comment.meta.json` (metadatos de publicación)

---

## 4. Layout de carpetas

```
Agentes/
  outputs/
    <ADO_ID>/
      comment.html          ← comentario ADO (file-drop)
      comment.meta.json     ← metadatos opcionales
    epic-<ADO_ID>/
      <RF_SLUG>/
        pending-task.json   ← Task hija a crear
        plan-de-pruebas.md  ← referenciado por plan_de_pruebas_path
```

**Nota**: `<ADO_ID>` es siempre el ADO id real (entero asignado por Azure DevOps).

---

## 5. Validación

El módulo `backend/services/artifact_validator.py` valida estos contratos de forma
sincrónica antes del cierre de cada run:

- `validate_pending_task_file(path)` — valida schema, campos requeridos, status y ADO id
- `validate_comment_html_file(path)` — valida existencia y contenido HTML
- `validate_artifact_path(path)` — clasifica y valida por nombre de archivo
