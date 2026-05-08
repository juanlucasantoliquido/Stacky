# Git Manager

Herramienta CLI para gestionar repositorios Git de **Azure DevOps** desde un coding agent o terminal.

- Sin servidor, sin dependencias externas
- Solo Python 3.8+ stdlib
- Salida siempre en **JSON** → fácil de parsear desde cualquier agente
- Un único archivo: `git.py`

---

## Configuración (una sola vez)

Edita `git-config.json` con tus credenciales:

```json
{
  "org": "UbimiaPacifico",
  "project": "Strategist_Pacifico",
  "repo": "Strategist_Pacifico",
  "pat": "TU_PAT_AQUI"
}
```

> El PAT se genera en **ADO → User Settings → Personal access tokens**.  
> Permisos mínimos necesarios: `Code — Read & Write` (para PRs), `Identity — Read` (para identity lookup).

Si el PAT ya está en `Tools/PAT-ADO`, la herramienta lo toma automáticamente como fallback.

---

## Acciones disponibles

| Acción | Descripción |
|--------|-------------|
| `repos` | Lista todos los repositorios del proyecto |
| `branches` | Lista branches de un repo |
| `pr list` | Lista pull requests (filtrable por status, branch) |
| `pr get` | Detalle completo de un PR |
| `pr create` | Crea un pull request |
| `pr update` | Actualiza título, descripción o publica un draft |
| `pr abandon` | Abandona un PR |
| `identity` | Busca usuarios por email/nombre (para GUIDs de reviewers) |

---

## Ejemplos

### Listar repos y branches

```bash
python git.py repos

python git.py branches --repo Strategist_Pacifico
python git.py branches --repo Strategist_Pacifico --filter feature
```

### Pull Requests

```bash
# Listar PRs activos
python git.py pr list --repo Strategist_Pacifico

# Listar PRs completados
python git.py pr list --repo Strategist_Pacifico --status completed

# Filtrar por branch origen
python git.py pr list --repo Strategist_Pacifico --source feature/login

# Detalle de un PR
python git.py pr get 42 --repo Strategist_Pacifico

# Crear PR básico
python git.py pr create \
  --repo Strategist_Pacifico \
  --source feature/mi-feature \
  --target main \
  --title "Agrega nueva funcionalidad X"

# Crear PR con descripción, revisores y work items vinculados
python git.py pr create \
  --repo Strategist_Pacifico \
  --source feature/mi-feature \
  --target main \
  --title "Fix validacion de formulario" \
  --desc "Corrige el bug reportado en ADO #1234" \
  --reviewer <guid-revisor-1> <guid-revisor-2> \
  --work-items 1234 5678

# Crear como borrador
python git.py pr create \
  --repo Strategist_Pacifico \
  --source feature/mi-feature \
  --target main \
  --title "WIP: refactor modulo X" \
  --draft

# Publicar borrador (draft → active)
python git.py pr update 42 --repo Strategist_Pacifico --publish

# Actualizar título
python git.py pr update 42 --repo Strategist_Pacifico --title "Nuevo titulo definitivo"

# Abandonar PR
python git.py pr abandon 42 --repo Strategist_Pacifico
```

### Buscar revisores

Para obtener el GUID de un revisor antes de crear el PR:

```bash
python git.py identity --search "juan.perez@empresa.com"
```

Retorna algo como:
```json
{
  "ok": true,
  "action": "identity",
  "result": [
    {
      "id": "a1b2c3d4-...",
      "display_name": "Juan Perez",
      "unique_name": "juan.perez@empresa.com"
    }
  ]
}
```

Luego usás el `id` como `--reviewer a1b2c3d4-...`.

---

## Override de credenciales por CLI

Todos los comandos aceptan `--org`, `--project`, `--repo` y `--pat` para sobrescribir lo que está en `git-config.json`:

```bash
python git.py pr list --repo OtroRepo --org OtraOrg --project OtroProject --pat MI_PAT
```

---

## Formato de salida

Éxito:
```json
{
  "ok": true,
  "action": "pr create",
  "result": { ... }
}
```

Error:
```json
{
  "ok": false,
  "action": "pr create",
  "error": "http_422",
  "message": "El branch 'feature/x' no existe en el repositorio."
}
```

Exit code `0` en éxito, `1` en error.


---

## Arquitectura

```mermaid
flowchart TD
    subgraph CALLERS["CONSUMIDORES - Quienes llaman a git.py"]
        DEV_AG["Agente Desarrollador\n(crear PR al finalizar)"]
        TA_AG["Agente Analista Tecnico\n(verificar branches existentes)"]
        CLI_USER["Operador via terminal"]
    end

    subgraph GIT_TOOL["GIT MANAGER - git.py"]
        direction TB
        CFG["Configuracion\ngit-config.json / PAT-ADO"]
        AUTH["Autenticacion\nBasic Auth via PAT"]
        ACTIONS["Acciones disponibles"]
        REPOS["repos - Listar repos"]
        BRANCHES["branches - Listar branches"]
        PR_LIST["pr list - Listar PRs"]
        PR_GET["pr get - Detalle de PR"]
        PR_CREATE["pr create - Crear PR\n+ vincular work items + reviewers"]
        PR_UPDATE["pr update - Actualizar PR\n+ publish draft"]
        PR_ABANDON["pr abandon - Abandonar PR"]
        IDENTITY["identity - Buscar usuarios por email"]
    end

    subgraph ADO_GIT_API["AZURE DEVOPS GIT API"]
        REPO_API["Repos API\n/_apis/git/repositories"]
        BRANCH_API["Branches API\n/refs?filter=heads/"]
        PR_API["Pull Requests API\n/pullrequests"]
        ID_API["Identity API\n/_apis/identities"]
    end

    subgraph OUTPUT["OUTPUT - siempre JSON"]
        OK["ok: true\n+ datos del recurso"]
        ERR["ok: false\n+ error message\n+ exit code 1"]
    end

    DEV_AG & TA_AG & CLI_USER --> CFG
    CFG --> AUTH
    AUTH --> ACTIONS
    ACTIONS --> REPOS & BRANCHES & PR_LIST & PR_GET & PR_CREATE & PR_UPDATE & PR_ABANDON & IDENTITY
    REPOS --> REPO_API
    BRANCHES --> BRANCH_API
    PR_LIST & PR_GET & PR_CREATE & PR_UPDATE & PR_ABANDON --> PR_API
    IDENTITY --> ID_API
    PR_API & REPO_API & BRANCH_API & ID_API --> OK
    PR_API & REPO_API & BRANCH_API & ID_API -->|"HTTP error"| ERR
```

---

## Flujo de creacion de PR tipico

```mermaid
sequenceDiagram
    participant DEV as Agente Desarrollador
    participant GIT as git.py
    participant CFG as git-config.json
    participant API as Azure DevOps Git API

    DEV->>GIT: python git.py pr create --source feature/ADO-65 --target main --title "..." --work-items 65
    GIT->>CFG: Leer org, project, repo, PAT
    GIT->>API: POST /pullrequests (con branch, titulo, work items)
    API-->>GIT: 201 Created + PR ID
    GIT-->>DEV: {"ok": true, "pr_id": 42, "url": "https://..."}
```

---

## Input / Output

| Accion | Input | Output |
|---|---|---|
| `repos` | — | Lista de repositorios del proyecto |
| `branches` | repo | Lista de branches con hash de ultimo commit |
| `pr list` | repo, status opcional, branch origen | Array de PRs con estado y titulo |
| `pr get` | PR ID, repo | Detalle completo del PR |
| `pr create` | repo, source, target, titulo | PR creado con ID y URL |
| `pr update` | PR ID, repo | PR actualizado |
| `pr abandon` | PR ID, repo | Confirmacion de PR abandonado |
| `identity` | email o nombre | GUID del usuario para usar como reviewer |

---

## Sinergia con ADO Manager

```mermaid
flowchart LR
    DEV["Agente Desarrollador"]
    ADO["ADO Manager\nado.py\ncambiar estado ticket"]
    GIT["Git Manager\ngit.py\ncrear PR vinculado"]
    ADO_SVC["Azure DevOps"]
    DEV --> ADO --> ADO_SVC
    DEV --> GIT --> ADO_SVC
```
