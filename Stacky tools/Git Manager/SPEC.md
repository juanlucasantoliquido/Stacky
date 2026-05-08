---
status: approved
approved_by: StackyToolArchitect
approved_date: 2026-05-02
---

# SPEC — Git Manager (`git.py`)

## 1. Propósito

CLI Python para gestionar repositorios Git de **Azure DevOps** desde agentes o terminal. Es la **única interfaz autorizada** del ecosistema Stacky para interactuar con repos, branches y pull requests de ADO. Ningún agente ejecuta comandos `git` directamente ni llama la API REST de ADO Repos; todos lo hacen a través de esta tool.

## 2. Alcance

**Hace:**
- Listar repositorios del proyecto
- Listar branches de un repositorio (con filtro por prefijo)
- Listar, obtener, crear, actualizar y abandonar pull requests
- Buscar usuarios/identidades por email o nombre (para obtener GUIDs de reviewers)

**NO hace:**
- Operaciones de `git` local (commit, push, pull, clone) — esas las hace el agente via `runCommands`
- Gestionar work items o comentarios ADO — eso es responsabilidad de ADO Manager
- Aprobar o mergear PRs (operación humana por diseño)
- Gestionar permisos de repo o branch policies

## 3. Inputs

### Forma de invocación

```bash
python git.py <accion> [argumentos]
```

### Acciones y sus argumentos

| Acción | Args obligatorios | Args opcionales |
|---|---|---|
| `repos` | — | — |
| `branches` | `--repo <nombre>` | `--filter <prefijo>` |
| `pr list` | `--repo <nombre>` | `--status active\|completed\|abandoned\|all`, `--source <branch>` |
| `pr get` | `<pr_id>`, `--repo <nombre>` | — |
| `pr create` | `--repo <nombre>`, `--source <branch>`, `--target <branch>`, `--title <str>` | `--desc <str>`, `--html`, `--reviewer <guid>...`, `--work-items <id>...`, `--draft` |
| `pr update` | `<pr_id>`, `--repo <nombre>` | `--title <str>`, `--desc <str>`, `--publish` (convierte draft → activo) |
| `pr abandon` | `<pr_id>`, `--repo <nombre>` | — |
| `identity` | `--search <email_o_nombre>` | — |

### Configuración de credenciales (en orden de prioridad)

1. Args CLI: `--org`, `--project`, `--repo`, `--pat`
2. `git-config.json` en la carpeta del script
3. `../../PAT-ADO` (compatibilidad con Stacky Agents)

## 4. Outputs

### Éxito — JSON a stdout

**`repos`**
```json
{"ok": true, "action": "repos", "count": 2, "repos": [
  {"id": "guid", "name": "Strategist_Pacifico", "default_branch": "main", "url": "..."}
]}
```

**`branches`**
```json
{"ok": true, "action": "branches", "repo": "Strategist_Pacifico", "count": 5, "branches": [
  {"name": "feature/ado-70-filtros", "commit": "abc123", "is_default": false}
]}
```

**`pr list`**
```json
{"ok": true, "action": "pr list", "count": 1, "prs": [
  {"id": 42, "title": "...", "status": "active", "source": "feature/...", "target": "main",
   "author": "...", "created_date": "...", "url": "..."}
]}
```

**`pr get`**
```json
{"ok": true, "action": "pr get", "pr": {
  "id": 42, "title": "...", "description": "...", "status": "active",
  "source": "feature/...", "target": "main", "author": "...",
  "reviewers": [...], "work_items": [70], "created_date": "...", "url": "..."
}}
```

**`pr create`**
```json
{"ok": true, "action": "pr create", "pr": {"id": 43, "url": "...", "status": "active"}}
```

**`identity`**
```json
{"ok": true, "action": "identity", "count": 1, "identities": [
  {"display_name": "Juan Perez", "email": "juan@empresa.com", "guid": "..."}
]}
```

### Error — JSON a stdout + exit code 1

```json
{"ok": false, "error": "<error_code>", "message": "<descripción legible>"}
```

## 5. Contrato de uso

**Precondiciones:**
- `git-config.json` con org, project, repo y PAT válido
- El PAT tiene permisos `Code — Read & Write` y `Identity — Read`

**Postcondiciones:**
- Lecturas (`repos`, `branches`, `pr list`, `pr get`, `identity`) no modifican nada
- `pr create` crea exactamente un PR; si el PR ya existe para ese source+target (mismo estado activo), ADO puede retornar error — la tool lo reporta como `duplicate_pr`
- `pr update` modifica solo los campos especificados; no toca los demás
- `pr abandon` marca el PR como abandonado; es reversible (un humano puede reactivarlo)

**Idempotencia:**
- Lecturas: idempotentes
- `pr create`: NO idempotente
- `pr update`: idempotente si se llama con los mismos valores
- `pr abandon`: idempotente (abandonar un PR ya abandonado retorna el PR sin error)

## 6. Validaciones internas

- `<pr_id>` debe ser entero positivo — falla con `invalid_pr_id` si no lo es
- `--status` acepta solo `active`, `completed`, `abandoned`, `all`
- Si `--draft` está presente, el PR se crea en modo borrador y solo puede publicarse después con `pr update <id> --publish`
- Los `--reviewer` reciben GUIDs; para obtener el GUID de un usuario, usar `identity --search <email>` primero

## 7. Errores esperados

| Código | Cuándo |
|---|---|
| `missing_pat` | Config no encontrada o PAT vacío |
| `missing_org_project` | Config sin org o project |
| `network_error` | Sin conectividad |
| `http_401` | PAT inválido o expirado |
| `http_403` | PAT sin permisos |
| `http_404` | Repo o PR no encontrado |
| `duplicate_pr` | Ya existe un PR activo para ese source+target |
| `invalid_pr_id` | ID no numérico |
| `invalid_status` | `--status` fuera de los valores aceptados |

## 8. Dependencias

- Python 3.8+ stdlib únicamente
- Sin dependencias externas
- Acceso de red a `https://dev.azure.com/`

## 9. Ejemplos de uso

```bash
# Listar repos
python git.py repos

# Listar branches con prefijo "feature"
python git.py branches --repo Strategist_Pacifico --filter feature

# Crear PR
python git.py pr create \
  --repo Strategist_Pacifico \
  --source feature/ado-70-filtros \
  --target main \
  --title "ADO-70 RF-003 Validación filtros" \
  --desc "<h2>Cambios</h2><p>Agrega validación post-búsqueda</p>" \
  --html \
  --work-items 70

# Buscar GUID de reviewer
python git.py identity --search "juan.perez@empresa.com"

# Listar PRs activos
python git.py pr list --repo Strategist_Pacifico --status active
```

## 10. Criterios de aceptación

- [ ] `python git.py repos` retorna `ok:true` con lista de repos del proyecto
- [ ] `python git.py branches --repo X` retorna branches del repo X
- [ ] `python git.py pr create ...` crea un PR y retorna `ok:true` con `pr.id` numérico
- [ ] `python git.py pr get <id_inexistente>` retorna `{"ok": false, "error": "http_404"}`
- [ ] Sin `git-config.json`, retorna `{"ok": false, "error": "missing_pat"}`
- [ ] Toda salida parsea como JSON válido
- [ ] Toda salida de error incluye `"ok"`, `"error"` y `"message"`

## 11. Tests requeridos

```
tests/unit/test_git_manager.py

test_repos_returns_ok_structure
test_branches_filters_by_prefix
test_pr_create_returns_pr_id
test_pr_get_nonexistent_returns_error
test_identity_search_by_email
test_missing_config_returns_error
test_output_always_valid_json
```
