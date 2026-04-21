# Stacky — Adaptación a Azure DevOps

Documento técnico de la migración de Stacky desde Mantis + SVN hacia una
arquitectura pluggable con soporte nativo de **Azure DevOps Work Items** y
**Azure DevOps Repos (Git)**, manteniendo Mantis/SVN como proveedores
alternativos vía adapter.

> **Audiencia:** devs que mantienen Stacky y quieren entender qué cambió,
> por qué, y dónde tocar para extender.

## 1. Objetivo

Stacky debía dejar de asumir que el issue tracker es Mantis y el SCM es SVN.
El objetivo era:

- Soportar **Azure DevOps Work Items** como tracker principal.
- Operar sobre **Git de Azure DevOps** para commits/push.
- Mantener la capacidad de trabajar contra Mantis/SVN sin regresiones.
- Dejar la puerta abierta para agregar otros proveedores (GitHub, GitLab, Jira).

El resultado es una arquitectura de proveedores pluggables con dos paquetes
nuevos, cambios localizados en `daemon.py` y `dashboard_server.py`, y una
configuración declarativa por proyecto.

## 2. Diagnóstico previo

### 2.1 Acoplamiento Mantis en Stacky

Se midió el acoplamiento real con `grep` sobre ~100 archivos:

| Punto | Archivo | Naturaleza |
|---|---|---|
| Scraper | `mantis_scraper.run_scraper` | Playwright, 51 KB |
| Updater | `mantis_updater.update_ticket_on_mantis`, `confirm_ticket_on_mantis` | Playwright, 40 KB |
| Change monitor | `mantis_change_monitor.MantisChangeMonitor` | Escanea INC.md locales (no habla con Mantis) |
| Importadores | `daemon.py`, `dashboard_server.py` | 5 imports en total |
| Menciones | 64 archivos | Solo strings literales: `estado_mantis`, nombres de campos |

**Conclusión:** el acoplamiento duro está restringido a 3 módulos Mantis y a
5 imports. Todo lo demás solo usa `estado_mantis` como etiqueta semántica en
el state del pipeline.

### 2.2 Integración ADO existente en el proyecto

- `.claude/create_ado_tickets.py` — script Python con `urllib` + PAT base64
  preencoded, apuntando a `https://dev.azure.com/UbimiaPacifico/Strategist_Pacifico`.
- `trunk/tools/Create-ADOTickets-DB.ps1` / `-v2.ps1` — scripts PowerShell
  con el mismo patrón (Invoke-WebRequest + Basic auth + api-version 7.1).
- PAT y endpoint **ya conocidos y en uso**, pero embebidos en cada script.

**Conclusión:** la conectividad ADO ya funciona en el proyecto; la adaptación
debe reutilizar ese conocimiento (org, proyecto, api-version, formato PAT)
y centralizarlo en una única capa.

## 3. Arquitectura propuesta

### 3.1 Dos paquetes nuevos

```
Tools/Stacky/
├── issue_provider/           ← tracker pluggable
│   ├── __init__.py           ← facade: get_provider(), sync_tickets()
│   ├── base.py               ← IssueProvider ABC
│   ├── types.py              ← Ticket, TicketDetail, TicketComment...
│   ├── factory.py            ← dispatcher por config.type
│   ├── azure_devops_provider.py ← REST nativo (urllib stdlib)
│   ├── mantis_provider.py    ← shim sobre mantis_scraper/updater
│   └── sync.py               ← sync_tickets() → layout local
│
├── scm_provider/             ← SCM pluggable
│   ├── __init__.py
│   ├── base.py               ← ScmProvider ABC
│   ├── factory.py            ← autodetecta .git / .svn
│   ├── git_provider.py       ← Git nativo (ADO-aware, AB# trailers)
│   └── svn_provider.py       ← shim sobre svn_ops.py
│
└── scripts/
    └── ado_smoke_test.py     ← prueba E2E del provider ADO
```

### 3.2 Contratos

**`IssueProvider`** (abstracción mínima):

```python
class IssueProvider(ABC):
    name: str = ""
    def is_available(self) -> tuple[bool, str]: ...
    def fetch_open_tickets(self) -> list[Ticket]: ...
    def fetch_ticket_detail(self, id: str) -> TicketDetail: ...
    def add_comment(self, id, body, kind=CommentKind.GENERIC, is_html=False) -> bool: ...
    def transition_state(self, id, target_state) -> bool: ...
    def assign(self, id, user) -> bool: ...
    def close(self, id, reason="") -> bool: ...
    def ticket_url(self, id) -> str: ...
```

**`ScmProvider`**:

```python
class ScmProvider(ABC):
    name: str = ""
    def is_available(self, workspace) -> tuple[bool, str]: ...
    def info(self, workspace) -> RepoInfo: ...
    def status(self, workspace) -> list[ChangedFile]: ...
    def diff(self, workspace, full=False, paths=None) -> str: ...
    def add(self, workspace, paths) -> bool: ...
    def commit(self, workspace, message, files=None, work_item_id=None) -> CommitResult: ...
    def push(self, workspace, remote="origin", branch=None) -> tuple[bool, str]: ...
    def log(self, workspace, limit=10) -> list[dict]: ...
```

### 3.3 Flujo end-to-end (ADO)

```
┌──────────────┐   cada N min    ┌────────────────────┐
│  daemon.py   │ ─────────────── │ issue_provider     │
│ _scrape_cycle│                 │  .sync_tickets()   │
└──────┬───────┘                 └─────────┬──────────┘
       │                                   │
       │ tracker_kind != "mantis"          │ WIQL + REST
       │                                   ▼
       │                          ┌────────────────────┐
       │                          │ ADO Work Items API │
       │                          └─────────┬──────────┘
       │                                    │
       │                                    ▼
       │                  projects/<X>/tickets/{estado}/{id}/
       │                       INC-{id}.md + 6 placeholders PM
       │
       ▼
┌──────────────────┐     PM → Dev → QA      ┌──────────────┐
│ pipeline_watcher │ ────────────────────── │  agentes     │
│                  │                         │  (VS Code)   │
└────────┬─────────┘                        └──────┬───────┘
         │  QA completado                          │
         ▼                                         ▼
┌────────────────────┐          ┌──────────────────────────┐
│ issue_provider     │          │ scm_provider.GitProvider │
│  .add_comment(    │ ──────── │  .commit(..., AB#<id>)   │
│   QA_RESOLUTION)   │          │  .push()                 │
│  .transition_state │          └──────────────────────────┘
│   ("Resolved")    │
└────────────────────┘
```

Punto clave: el **layout local de archivos se preserva**
(`projects/<NAME>/tickets/{estado}/{ticket_id}/INC-{id}.md` + 6 placeholders
PM), por eso los agentes PM/Dev/QA, `ticket_detector`, `pipeline_watcher`,
`pipeline_state` y el dashboard **no requieren cambios internos**.

## 4. Decisiones tomadas

### 4.1 ¿Por qué abstracción y no reemplazo directo?

Alternativa descartada: reescribir `mantis_scraper.py` y `mantis_updater.py`
para que "también hablen ADO". Se descartó porque:

- Mantis usa Playwright (scraping UI), ADO usa REST. No hay nada reutilizable
  entre ambos a nivel de código — solo a nivel de contrato.
- El proyecto actual tiene dos proyectos Stacky activos (RIPLEY, RSMOBILENET)
  que siguen usando Mantis. Un reemplazo rompería compat.
- Un abstract provider deja la puerta abierta para GitHub Issues, Jira, etc.,
  sin tocar daemon/dashboard.

### 4.2 `sync_tickets()` vs. `run_scraper()`

`mantis_scraper.run_scraper()` escribe directamente a disco por razones
históricas (Playwright + naveg. lenta). Para ADO con REST es natural separar
"fetch" (provider) de "escribir layout" (sync_tickets). `sync_tickets`
vive en `issue_provider` y consume cualquier provider compatible — no solo
ADO. Si mañana se agrega GitHub Issues, `sync_tickets` sigue sirviendo.

### 4.3 Transición de estados

ADO tiene un ciclo de vida muy template-dependiente (Agile, Scrum, Basic, CMMI),
y cada template expone estados distintos. Stacky:

- **Lee** el estado crudo (`System.State`) y lo normaliza a 5 buckets
  Stacky (`asignada` / `aceptada` / `resuelta` / `completada` / `archivada`)
  usando un `state_mapping` configurable.
- **Escribe** el estado crudo tal cual lo recibe (ADO valida transiciones
  desde el server). El caller elige el nombre nativo ("Resolved", "Active",
  etc.), Stacky no intenta adivinar.

Default del mapping cubre los templates más comunes (Agile/Scrum/Basic).

### 4.4 Auth

PAT con tres fuentes, en orden de precedencia:

1. `$STACKY_ADO_PAT` (env var) — pref. para CI / servidores
2. `auth/ado_auth.json` (archivo ignorado por git) — pref. para devs
3. `config.issue_tracker.pat` inline (solo desarrollo local)

Soporta PAT "raw" (~52 chars) **y** PAT preencoded (base64 con prefijo `:`)
para compatibilidad con el formato usado en `.claude/create_ado_tickets.py`.

### 4.5 Trailers `AB#<id>` en commits

Azure DevOps linkea automáticamente commits a work items cuando el mensaje
contiene `AB#<id>`. `GitProvider.commit(work_item_id=...)` agrega el trailer
automáticamente si no está presente en el mensaje. **No** lo agrega si el
mensaje ya lo tiene (evita duplicación).

### 4.6 Conversión HTML → Markdown

ADO devuelve descripciones, criterios de aceptación y comentarios en HTML.
Stacky (y los agentes PM/Dev/QA) consumen Markdown. Se agrega un conversor
liviano (`issue_provider.sync._html_to_md`) que cubre las tags típicas:
`<h1-6>, <p>, <br>, <strong>, <em>, <code>, <li>`. **No** es exhaustivo —
la premisa es "Markdown legible", no "fidelidad 100% HTML".

Decisión explícita: evitar `BeautifulSoup`/`html2text` para **no** inflar
`requirements.txt`. Si la conversión quedara corta, se re-evaluará.

### 4.7 Dependencias

Cero nuevas dependencias. `urllib.request` / `json` / `subprocess` /
`pathlib` — todo stdlib. `requirements.txt` sigue teniendo solo lo que
Mantis necesita (Playwright + pywinauto + pyautogui + pyperclip).

## 5. Archivos creados / modificados

### 5.1 Creados

| Archivo | Rol |
|---|---|
| `issue_provider/__init__.py` | Facade público |
| `issue_provider/base.py` | `IssueProvider` ABC, `ProviderError`, `TicketNotFound` |
| `issue_provider/types.py` | Dataclasses: Ticket, TicketDetail, TicketComment, TicketAttachment, CommentKind |
| `issue_provider/factory.py` | `get_provider()`, `load_tracker_config()` |
| `issue_provider/azure_devops_provider.py` | Implementación REST de ADO |
| `issue_provider/mantis_provider.py` | Shim sobre módulos Mantis existentes |
| `issue_provider/sync.py` | `sync_tickets()` + placeholders + move-on-state-change |
| `scm_provider/__init__.py` | Facade público |
| `scm_provider/base.py` | `ScmProvider` ABC |
| `scm_provider/factory.py` | `get_scm()` con autodetect `.git`/`.svn` |
| `scm_provider/git_provider.py` | Git nativo ADO-aware (`parse_ado_remote`, `AB#` trailers) |
| `scm_provider/svn_provider.py` | Shim sobre `svn_ops.py` |
| `auth/ado_auth.json.template` | Plantilla de credenciales ADO |
| `projects/RSPACIFICO/config.json` | Proyecto Stacky apuntando a ADO `Strategist_Pacifico` |
| `scripts/ado_smoke_test.py` | Prueba E2E del provider |
| `docs/ARCHITECTURE_ADO.md` | Este documento |
| `docs/README_ADO.md` | Guía operativa |

### 5.2 Modificados

| Archivo | Cambio |
|---|---|
| `config.json` | + bloque `issue_tracker` (default ADO); Mantis queda como fallback |
| `daemon.py` | `_scrape_cycle` usa `load_tracker_config` + `sync_tickets`; fallback a `run_scraper` si tracker=mantis. E-02 usa `IssueProvider.add_comment` + `transition_state` en lugar de `mantis_updater` directo. Helper `_build_resolution_note` + `_md_to_html_mini` |
| `dashboard_server.py` | `/api/send_note_to_mantis` usa `IssueProvider` en lugar de imports directos |
| `project_manager.py` | `initialize_project(..., issue_tracker, scm)`; nuevo helper `initialize_ado_project(...)` |
| `.gitignore` | + `auth/ado_auth.json` |

## 6. Backwards compatibility

- Los proyectos existentes (RIPLEY, RSMOBILENET) siguen operando exactamente
  igual que antes: si `issue_tracker.type` no está seteado y hay `mantis_url`,
  el factory devuelve `MantisProvider`, y el daemon ejecuta `run_scraper`.
- `mantis_scraper.py`, `mantis_updater.py`, `mantis_change_monitor.py`
  **no se tocaron**. Siguen siendo la implementación canónica de Mantis.
- `svn_ops.py` **no se tocó**. `SvnProvider` solo delega.
- El state del pipeline (`pipeline_state.py`) y sus 40+ estados siguen igual.
  La clave `estado_mantis` en `seen_tickets.json` conserva su nombre
  (representa "estado en el tracker" — semánticamente vale para ADO también).

## 7. Extensibilidad

Agregar un nuevo tracker (ej. GitHub Issues):

1. Crear `issue_provider/github_provider.py` implementando `IssueProvider`.
2. Agregar en `issue_provider/factory.py`:
   ```python
   _PROVIDERS["github"] = GitHubProvider
   ```
3. Setear `issue_tracker.type = "github"` en el config del proyecto.

No requiere cambios en `daemon.py`, `dashboard_server.py`, `pipeline_runner.py`
ni en los agentes.

## 8. Limitaciones conocidas

1. **Mantis sin API REST nativa** — el flujo Mantis sigue dependiendo de
   Playwright. `MantisProvider` no implementa `fetch_open_tickets` porque
   Mantis hace scraping; el daemon delega en `run_scraper` cuando detecta
   tracker=mantis. Esto es intencional: no se reescribe algo que ya funciona.

2. **Adjuntos de ADO** — `TicketAttachment` contiene URL y metadata pero
   `sync_tickets()` no los descarga a disco (solo los lista en `INC.md`).
   Descargarlos es una extensión fácil si se necesita.

3. **Transiciones ADO template-dependientes** — si el proyecto ADO usa
   CMMI, Scrum o Basic, los nombres de estados difieren (ej. "Active" vs
   "Committed"). El `state_mapping` de `config.json` cubre los 3 templates
   comunes; para templates custom, agregar el mapeo en el config del proyecto.

4. **PAT preencoded** — el `.claude/create_ado_tickets.py` usa un PAT ya
   base64-encoded. El provider lo detecta heurísticamente (>80 chars + base64
   charset). Si tu PAT raw supera 80 chars la heurística falla — usá
   `auth/ado_auth.json` con `"pat_format": "raw"` explícito (pendiente de
   implementar override por campo).

## 9. Pendientes

- [ ] Override explícito del campo `pat_format` en `auth/ado_auth.json`.
- [ ] Download de adjuntos en `sync_tickets()`.
- [ ] Conversión MD → HTML más rica para `add_comment(is_html=False)`.
- [ ] Test unitarios para `sync._html_to_md` y `azure_devops_provider._to_ticket`.
- [ ] Hook de pre-commit para inyectar `AB#<id>` desde la carpeta del ticket
      activo (hoy depende de que el Dev lo escriba en el mensaje manualmente).
