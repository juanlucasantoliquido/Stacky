# Stacky + Azure DevOps — Guía operativa

Guía práctica para poner en marcha Stacky contra un proyecto de Azure DevOps
(ADO). Cubre configuración mínima, credenciales, validación de conectividad y
cómo correr el pipeline PM → Dev → QA contra tickets reales.

Para el diseño y las decisiones arquitectónicas ver
[ARCHITECTURE_ADO.md](ARCHITECTURE_ADO.md).

---

## 1. Requisitos

- Python 3.11+ (Stacky ya corre sobre el mismo intérprete que usa hoy)
- Repositorio Git del proyecto **ya clonado localmente** con remote a ADO
  (`https://dev.azure.com/<org>/<project>/_git/<repo>`)
- Personal Access Token (PAT) de Azure DevOps con scopes:
  - `Work Items (Read, write, & manage)`
  - `Code (Read)` — para que Stacky pueda parsear el remoto; los pushes los
    hace tu usuario, no el PAT.

No se agregan dependencias nuevas: todo el provider usa `urllib` + `subprocess`
del stdlib.

---

## 2. Layout de archivos relevante

```
Tools/Stacky/
├── auth/
│   ├── ado_auth.json           # ← credenciales ADO (no versionado)
│   └── ado_auth.json.template  # ejemplo
├── projects/
│   └── RSPACIFICO/
│       └── config.json         # proyecto Stacky configurado para ADO
├── issue_provider/             # abstracción de issue tracker
│   ├── azure_devops_provider.py
│   ├── mantis_provider.py      # shim legacy
│   └── factory.py
├── scm_provider/               # abstracción de SCM
│   ├── git_provider.py
│   └── svn_provider.py
└── scripts/
    └── ado_smoke_test.py       # script de validación end-to-end
```

Los `projects/<NAME>/tickets/...` se generan al correr el scraper/sync.

---

## 3. Configurar credenciales

### Opción A — variable de entorno (recomendada)

```bash
# Windows PowerShell
$env:STACKY_ADO_PAT = "<tu-pat-crudo>"

# bash / git-bash
export STACKY_ADO_PAT="<tu-pat-crudo>"
```

Esto tiene prioridad sobre el archivo y evita persistir el secreto en disco.

### Opción B — archivo `auth/ado_auth.json`

Copiar el template y completar:

```bash
cp Tools/Stacky/auth/ado_auth.json.template Tools/Stacky/auth/ado_auth.json
```

Contenido:

```json
{
  "pat": "<pega-aqui-tu-PAT>",
  "pat_format": "raw"
}
```

- `pat_format: "raw"` → el PAT tal cual te lo da ADO (~52 caracteres).
- `pat_format: "preencoded"` → si ya tenés el string base64 listo
  (`":TUPAT"` → base64). El provider también detecta este caso por heurística,
  pero declararlo explícitamente es más seguro.

`auth/ado_auth.json` ya está en `.gitignore`.

---

## 4. Configurar el proyecto Stacky

El proyecto `RSPACIFICO` viene preconfigurado en
[projects/RSPACIFICO/config.json](../projects/RSPACIFICO/config.json). Los
campos clave son:

```jsonc
{
  "name": "RSPACIFICO",
  "workspace_root": "N:/GIT/RS/RSPacifico/trunk",  // ← repo local clonado
  "issue_tracker": {
    "type": "azure_devops",
    "organization": "UbimiaPacifico",               // ← org de ADO
    "project":      "Strategist_Pacifico",          // ← proyecto de ADO
    "api_version":  "7.1",
    "auth_file":    "auth/ado_auth.json",
    "auto_resolve": false,                          // true = transiciona a Resolved al cerrar
    "wiql": "SELECT [System.Id] FROM WorkItems WHERE [System.TeamProject] = @project AND [System.AssignedTo] = @me AND [System.State] NOT IN ('Closed','Done','Removed') ORDER BY [System.ChangedDate] DESC",
    "state_mapping": {
      "New": "asignada", "Active": "aceptada", "Resolved": "resuelta",
      "Done": "completada", "Closed": "completada", "Removed": "archivada"
      // ... ver config.json para el mapping completo
    }
  },
  "scm": { "type": "git" },
  "agents": { "pm": "PM-TL STack 3", "dev": "DevStack3", "tester": "QA" }
}
```

### Crear otro proyecto ADO

```python
from project_manager import initialize_ado_project

initialize_ado_project(
    name="MIPROYECTO",
    organization="MiOrg",
    ado_project="Mi Project",
    workspace_root="C:/repos/mi-repo",
    display_name="Mi Proyecto",
)
```

Genera `projects/MIPROYECTO/config.json` con el bloque `issue_tracker`
ya armado y los mappings de estado por defecto.

---

## 5. Probar la conexión

Desde `Tools/Stacky/`:

```bash
python scripts/ado_smoke_test.py
```

Salida esperada:

```
[smoke] Proyecto: RSPACIFICO
[smoke] tracker type: azure_devops
[smoke] organization:  UbimiaPacifico
[smoke] ado project:   Strategist_Pacifico
[smoke] ✅ provider disponible (auth + ping OK)
[smoke] work items abiertos: N
   - #12345    [      Active] (bug) Título del ticket...
   - #12346    [         New] (feature) Otro ticket...
[smoke] Descargando detalle de #12345 ...
   tags:           Priority:1; ...
   area_path:      Strategist_Pacifico\Backend
   description:    1820 chars (HTML=True)
   comments:       4
   attachments:    2
[smoke] Usá --sync para escribir el layout local de tickets.
```

### Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `❌ provider no disponible: sin PAT configurado` | No se encontró PAT | Setear `STACKY_ADO_PAT` o `auth/ado_auth.json` |
| `HTTP 401` al listar | PAT expirado o sin scopes | Regenerar PAT con `Work Items (read/write)` |
| `HTTP 404` | Typo en `organization` o `project` | Validar URL ADO real |
| `0 work items` pero hay tickets asignados | La WIQL excluye algunos estados | Ajustar `wiql` en `config.json` |

---

## 6. Primer sync de tickets

```bash
python scripts/ado_smoke_test.py --sync --limit 3
```

Esto ejecuta `sync_tickets()`, que:

1. Lista work items abiertos vía WIQL.
2. Descarga detalle + comments + relations por cada uno.
3. Crea `projects/RSPACIFICO/tickets/<estado>/<id>/` con:
   - `INC-<id>.md` — metadata y cuerpo del work item (HTML convertido a MD)
   - 6 placeholders PM (`INCIDENTE.md`, `ANALISIS_TECNICO.md`,
     `ARQUITECTURA_SOLUCION.md`, `TAREAS_DESARROLLO.md`,
     `QUERIES_ANALISIS.sql`, `NOTAS_IMPLEMENTACION.md`)
4. Registra el ticket en `projects/RSPACIFICO/state/seen_tickets.json`.
5. Si el estado en ADO cambió desde el sync anterior, mueve el folder a la
   nueva carpeta de estado (`asignada/` → `aceptada/` → `resuelta/` → …).

Estos artefactos son los mismos que consumen PM, Dev y QA — **nada en el
pipeline downstream cambia respecto de la operatoria con Mantis**.

---

## 7. Correr el pipeline contra ADO

El daemon se activa como siempre:

```bash
python daemon.py --project RSPACIFICO
```

Flujo por ticket nuevo:

1. **Scrape cycle** → `sync_tickets()` baja/actualiza tickets de ADO.
2. **E-01** → PM-TL arma `INCIDENTE.md`, `ANALISIS_TECNICO.md`, etc.
3. **E-02** → cuando un ticket entra en estado `aceptada`, se publica como
   comentario en el work item de ADO el contenido de `INCIDENTE.md` (HTML
   liviano). Si `auto_resolve=true`, además transiciona el estado a
   `Resolved`.
4. **E-03..E-05** → Dev implementa, commitea y pushea. El commit message
   lleva trailer automático `AB#<id>` para que ADO linkee el commit al
   work item.
5. **E-06** → QA valida.

### `AB#<id>` en commits

`scm_provider/git_provider.py::commit()` inserta automáticamente el trailer
si el mensaje no lo contiene todavía. Ejemplo:

```
fix(api): validar null en payload /orders

AB#12345
```

Azure DevOps detecta el trailer y crea el vínculo commit ↔ work item.

---

## 8. Volver a Mantis (compatibilidad legacy)

Un proyecto Stacky con `issue_tracker.type = "mantis"` (o con el legacy
`mantis_url`) sigue funcionando idéntico a antes. El provider lo resuelve
hacia `mantis_scraper.py` / `mantis_updater.py`, intactos.

No hay que correr ninguna migración: los proyectos Mantis existentes no se
tocan.

---

## 9. Checklist de validación

Antes de declarar operativo un proyecto ADO nuevo:

- [ ] `python scripts/ado_smoke_test.py` devuelve `✅ provider disponible`
- [ ] Lista al menos 1 work item abierto del asignado
- [ ] `--sync` genera carpeta de ticket con los 7 archivos esperados
- [ ] Un commit de prueba aparece linkeado al work item en ADO (trailer
      `AB#<id>` aplicado)
- [ ] `dashboard_server.py` levanta y `/api/send_note_to_mantis` responde
      200 contra un ticket ADO real (envía un comentario)
- [ ] `daemon.py --project <NAME>` corre un ciclo sin error

---

## 10. Referencias

- [ARCHITECTURE_ADO.md](ARCHITECTURE_ADO.md) — diseño y decisiones
- Azure DevOps REST API — Work Items:
  https://learn.microsoft.com/rest/api/azure/devops/wit/
- WIQL syntax:
  https://learn.microsoft.com/azure/devops/boards/queries/wiql-syntax
