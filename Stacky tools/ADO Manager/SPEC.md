---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — ADO Manager (`ado.py`)

## 1. Propósito

CLI Python para gestionar work items de **Azure DevOps** desde agentes o terminal. Es la **única interfaz autorizada** del ecosistema Stacky para leer y escribir datos en ADO. Ningún agente llama la API REST de ADO directamente; todos lo hacen a través de esta tool.

## 2. Alcance

**Hace:**
- Listar, filtrar y buscar work items con WIQL
- Obtener el detalle completo de un work item (campos + relaciones)
- Crear work items (Task, Bug, User Story, Feature, Epic)
- Agregar comentarios (texto plano o HTML)
- Cambiar el estado de un work item
- Listar los comentarios de un work item
- Listar los estados y tipos disponibles del proyecto

**NO hace:**
- Gestionar repositorios, branches, PRs — eso es responsabilidad de Git Manager
- Gestionar adjuntos binarios (solo texto/HTML en comentarios)
- Gestionar permisos, equipos o configuración del proyecto
- Hacer operaciones masivas sobre cientos de work items en una sola llamada sin paginar

## 3. Inputs

### Forma de invocación

```bash
python ado.py <accion> [argumentos]
```

### Acciones y sus argumentos

| Acción | Args obligatorios | Args opcionales |
|---|---|---|
| `list` | — | `--state <str>`, `--search <str>`, `--limit <int>`, `--all` |
| `get` | `<id>` | — |
| `create` | `--title <str>`, `--desc <str>` | `--html`, `--type <str>`, `--priority <int>`, `--assigned <email>`, `--area <str>`, `--tags <str>` |
| `comment` | `<id>`, `--text <str>` | `--html` |
| `state` | `<id>`, `<nuevo_estado>` | — |
| `comments` | `<id>` | — |
| `states` | — | — |
| `types` | — | — |

### Configuración de credenciales (en orden de prioridad)

1. Args CLI: `--org`, `--project`, `--pat`
2. `ado-config.json` en la carpeta del script: `{"org": "...", "project": "...", "pat": "..."}`
3. `../PAT-ADO` (compatibilidad con Stacky Agents): `{"pat": "...", "pat_format": "raw|preencoded"}`

**Nunca se pasa el PAT como variable de entorno** (por diseño histórico del archivo de config). Las demás tools del ecosistema que necesiten ADO deben usar esta tool como intermediario.

## 4. Outputs

### Éxito — JSON a stdout

**`list`**
```json
{"ok": true, "action": "list", "count": 3, "items": [
  {"id": 70, "title": "RF-003 Validación combinación filtros", "state": "Done", "type": "Task",
   "priority": 2, "assigned_to": "juan@empresa.com", "changed_date": "2026-05-01T..."}
]}
```

**`get`**
```json
{"ok": true, "action": "get", "item": {
  "id": 70, "title": "...", "state": "...", "type": "Task",
  "description": "<html>...", "priority": 2, "assigned_to": "...",
  "area_path": "...", "tags": "...", "changed_date": "...", "created_date": "...",
  "url": "https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico/_workitems/edit/70"
}}
```

**`comment`**
```json
{"ok": true, "action": "comment", "comment": {
  "id": 1234, "author": "...", "created_date": "..."
}}
```

**`state`**
```json
{"ok": true, "action": "state", "item": {"id": 70, "state": "Listo para QA"}}
```

**`comments`**
```json
{"ok": true, "action": "comments", "ticket_id": 70, "count": 3, "comments": [
  {"id": 1, "text": "<html>...", "author": "...", "created_date": "...", "modified_date": "..."}
]}
```

**`states` / `types`**
```json
{"ok": true, "action": "states", "values": ["New", "Active", "Technical review", ...]}
```

### Error — JSON a stdout + exit code 1

```json
{"ok": false, "error": "<error_code>", "message": "<descripción legible>"}
```

## 5. Contrato de uso

**Precondiciones:**
- `ado-config.json` (o `../PAT-ADO`) con org, project y PAT válido
- El PAT tiene permisos `Work Items — Read & Write` en el proyecto

**Postcondiciones:**
- Toda operación de lectura (`list`, `get`, `comments`, `states`, `types`) no modifica nada en ADO
- `comment` agrega exactamente un comentario al work item especificado
- `state` cambia el estado del work item al valor indicado; si el estado no existe, falla con `invalid_state`
- `create` crea un nuevo work item; si se ejecuta dos veces con el mismo input, crea dos work items distintos (NO es idempotente)

**Idempotencia:**
- Lecturas: idempotentes
- `comment`: NO idempotente (cada llamada agrega un comentario nuevo)
- `state`: idempotente si el work item ya está en el estado solicitado
- `create`: NO idempotente

## 6. Validaciones internas

- `<id>` debe ser un entero positivo — falla con `invalid_id` si no lo es
- `--priority` acepta solo `1`, `2`, `3`, `4`
- El estado en `state <id> <nuevo_estado>` debe estar en la lista devuelta por `states`; de lo contrario, ADO retorna error HTTP 400 que se traduce a `invalid_state`
- El PAT se codifica en base64 solo si no está ya pre-codificado (detectado por longitud ≥ 80 y patrón base64)
- El texto de `comment` se convierte a HTML si no se especifica `--html` y no parece ser HTML (texto plano → `<p>` por línea)

## 7. Errores esperados

| Código | Mensaje típico | Cuándo ocurre |
|---|---|---|
| `missing_pat` | "PAT no encontrado. Crea ado-config.json..." | Config no encontrada o PAT vacío |
| `missing_org_project` | "org y project son obligatorios" | Config sin org o project |
| `network_error` | "Error de red: <reason>" | Sin conectividad a dev.azure.com |
| `http_401` | "HTTP 401 ..." | PAT inválido o expirado |
| `http_403` | "HTTP 403 ..." | PAT sin permisos suficientes |
| `http_404` | "HTTP 404 ..." | Work item no encontrado |
| `http_400` | "HTTP 400 ..." | Estado inválido u otros errores de validación de ADO |
| `invalid_id` | "El ID debe ser un entero positivo" | ID no numérico |

## 8. Dependencias

- Python 3.8+ stdlib únicamente (`urllib`, `json`, `base64`, `argparse`, `re`)
- Sin dependencias externas — no requiere `pip install`
- Acceso de red a `https://dev.azure.com/`

## 9. Ejemplos de uso

```bash
# Listar tickets en "Listo para QA"
python ado.py list --state "Listo para QA"

# Obtener detalle del ticket 70 (incluye descripción HTML completa)
python ado.py get 70

# Leer comentarios del ticket 70
python ado.py comments 70

# Agregar comentario de texto plano
python ado.py comment 70 --text "Análisis completado. Ver adjunto."

# Agregar comentario HTML (dossier de evidencia)
python ado.py comment 70 --text "<h2>Dossier UAT</h2><p>Veredicto: PASS</p>" --html

# Cambiar estado
python ado.py state 70 "QA Done"

# Crear ticket
python ado.py create --title "Bug en FrmAgenda" --desc "El grid no filtra" --type "Bug" --priority 2

# Listar estados disponibles
python ado.py states
```

### Invocación desde otro script Python

```python
import subprocess, json

result = subprocess.run(
    ["python", "Tools/Stacky/Stacky tools/ADO Manager/ado.py", "get", "70"],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
if not data["ok"]:
    raise RuntimeError(data["message"])
ticket = data["item"]
```

## 10. Criterios de aceptación

- [ ] `python ado.py get 70` retorna JSON con `ok:true` y `item.id == 70` cuando el ticket existe
- [ ] `python ado.py list --state "Technical review"` retorna solo tickets en ese estado
- [ ] `python ado.py comment 70 --text "test"` crea un comentario y retorna `ok:true` con `comment.id` numérico
- [ ] `python ado.py get 99999999` retorna `{"ok": false, "error": "http_404", ...}` con exit code 1
- [ ] Sin `ado-config.json`, `python ado.py list` retorna `{"ok": false, "error": "missing_pat", ...}` con exit code 1
- [ ] Toda salida de éxito parsea como JSON válido con `json.loads`
- [ ] Toda salida de error incluye los campos `"ok"`, `"error"` y `"message"`
- [ ] No hay secretos (PAT) en la salida JSON ni en stderr

## 11. Tests requeridos

> La tool ya está en producción. Los tests a escribir son retroactivos para formalizar el contrato.

```
tests/unit/test_ado_manager.py

test_list_returns_ok_structure
test_get_existing_ticket_returns_item
test_get_nonexistent_ticket_returns_error_json
test_comment_adds_comment
test_state_change_valid_state
test_state_change_invalid_state_returns_error
test_missing_pat_returns_error
test_output_always_valid_json
test_no_secrets_in_output
```
