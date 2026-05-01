"""
project_manager.py — Gestión multi-proyecto para el Pipeline Dashboard.

Cada proyecto vive en:
  tools/stacky/projects/{NOMBRE}/
    config.json       ← configuración del cliente/proyecto
    prompts/
      pm.md           ← prompt base PM adaptado al proyecto
      dev.md          ← prompt base Dev adaptado al proyecto
      qa.md           ← prompt base QA adaptado al proyecto
    tickets/          ← tickets sincronizados (ruta configurable en config.json)
    pipeline/
      state.json      ← estado del pipeline (ruta configurable en config.json)
"""

import json
import os
from pathlib import Path

BASE_DIR     = Path(__file__).parent
PROJECTS_DIR = BASE_DIR / "projects"
ACTIVE_FILE  = BASE_DIR / "active_project.json"


# ── CRUD de proyectos ─────────────────────────────────────────────────────────

def get_all_projects() -> list[dict]:
    """Retorna todos los proyectos inicializados en projects/."""
    if not PROJECTS_DIR.exists():
        return []
    result = []
    for d in sorted(PROJECTS_DIR.iterdir()):
        cfg_file = d / "config.json"
        if d.is_dir() and cfg_file.exists():
            try:
                cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
                result.append(cfg)
            except Exception:
                pass
    return result


def get_project_config(name: str) -> dict | None:
    cfg_file = PROJECTS_DIR / name / "config.json"
    if not cfg_file.exists():
        return None
    try:
        return json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_active_project() -> str:
    """Retorna el nombre del proyecto activo. Default: primer proyecto en lista."""
    if ACTIVE_FILE.exists():
        try:
            data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
            name = data.get("active", "")
            if name and (PROJECTS_DIR / name / "config.json").exists():
                return name
        except Exception:
            pass
    projects = get_all_projects()
    if projects:
        return projects[0]["name"]
    return "RIPLEY"


def set_active_project(name: str):
    ACTIVE_FILE.write_text(json.dumps({"active": name}, indent=2), encoding="utf-8")


def get_project_paths(name: str) -> dict:
    """Retorna paths absolutos para tickets, state, prompts."""
    base = PROJECTS_DIR / name
    return {
        "base":    str(base),
        "tickets": str(base / "tickets"),
        "state":   str(base / "pipeline" / "state.json"),
        "prompts": str(base / "prompts"),
        "config":  str(base / "config.json"),
    }


def get_prompt(project_name: str, role: str) -> str:
    """
    Lee el prompt base para un rol del proyecto.
    role: "pm" | "dev" | "qa"
    Retorna "" si no existe.
    """
    path = PROJECTS_DIR / project_name / "prompts" / f"{role}.md"
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8-sig")
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end != -1:
                text = text[end + 4:].lstrip("\n")
        return text
    except Exception:
        return ""


# ── Inicialización de proyectos ───────────────────────────────────────────────

def initialize_project(
    name: str,
    display_name: str = "",
    tickets_dir: str = "",
    state_path: str = "",
    workspace_root: str = "",
    issue_tracker: dict | None = None,
    scm: dict | None = None,
) -> dict:
    """
    Crea la estructura de carpetas y archivos para un nuevo proyecto.

    workspace_root: ruta al workspace del proyecto.
    issue_tracker: bloque de configuración del tracker. Ver issue_provider.factory.
    scm: bloque { "type": "git", ... }. Si no se indica, se autodetecta
         por la presencia de .git en el workspace.
    """
    name = name.upper()
    ws = workspace_root.replace("\\", "/") if workspace_root else ""
    base = PROJECTS_DIR / name

    (base / "prompts").mkdir(parents=True, exist_ok=True)
    (base / "tickets").mkdir(parents=True, exist_ok=True)
    (base / "pipeline").mkdir(parents=True, exist_ok=True)
    (base / "state").mkdir(parents=True, exist_ok=True)

    if issue_tracker is None:
        issue_tracker = {"type": "azure_devops"}

    # Resolución de SCM — explicit > autodetect
    if scm is None:
        ws_path = Path(ws) if ws else Path(".")
        if (ws_path / ".git").exists():
            scm = {"type": "git"}
        else:
            scm = {"type": "git"}  # default

    config = {
        "name":             name,
        "display_name":     display_name or name,
        "workspace_root":   ws,
        "issue_tracker":    issue_tracker,
        "scm":              scm,
        "agents": {
            "pm":     "PM-TL STack 3",
            "dev":    "DevStack3",
            "tester": "QA",
        },
    }

    cfg_file = base / "config.json"
    cfg_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")

    _generate_prompts(base / "prompts", config)
    return config


def initialize_ado_project(
    name: str,
    organization: str,
    ado_project: str,
    workspace_root: str,
    display_name: str = "",
    area_path: str = "",
    wiql: str = "",
    state_mapping: dict | None = None,
    auth_file: str = "auth/ado_auth.json",
    scm_type: str = "git",
    agents: dict | None = None,
) -> dict:
    """
    Helper de alto nivel para dar de alta un proyecto Azure DevOps.

    Ejemplo:
        initialize_ado_project(
            name="RSPACIFICO",
            organization="UbimiaPacifico",
            ado_project="Strategist_Pacifico",
            workspace_root="N:/GIT/RS/RSPacifico/trunk",
            area_path="Strategist_Pacifico\\\\AgendaWeb",
        )
    """
    tracker = {
        "type":         "azure_devops",
        "organization": organization,
        "project":      ado_project,
        "auth_file":    auth_file,
    }
    if area_path:
        tracker["area_path"] = area_path
    if wiql:
        tracker["wiql"] = wiql
    if state_mapping:
        tracker["state_mapping"] = state_mapping

    cfg = initialize_project(
        name=name,
        display_name=display_name or name,
        workspace_root=workspace_root,
        issue_tracker=tracker,
        scm={"type": scm_type},
    )
    if agents:
        cfg["agents"] = agents
        (PROJECTS_DIR / cfg["name"] / "config.json").write_text(
            json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return cfg


# ── Generación de prompts ─────────────────────────────────────────────────────

def _generate_prompts(prompts_dir: Path, config: dict):
    """Genera prompts base adaptados al proyecto si no existen aún."""
    name    = config["name"]
    display = config["display_name"]
    ws      = config["workspace_root"]
    for role, fn in [("pm", _pm_prompt), ("dev", _dev_prompt), ("qa", _qa_prompt)]:
        path = prompts_dir / f"{role}.md"
        if not path.exists():
            path.write_text(fn(name, display, ws), encoding="utf-8")


def regenerate_prompts(project_name: str):
    """Regenera los prompts de un proyecto (sobreescribe los existentes)."""
    cfg = get_project_config(project_name)
    if not cfg:
        raise ValueError(f"Proyecto '{project_name}' no encontrado")
    prompts_dir = PROJECTS_DIR / project_name / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    for role, fn in [("pm", _pm_prompt), ("dev", _dev_prompt), ("qa", _qa_prompt)]:
        (prompts_dir / f"{role}.md").write_text(
            fn(cfg["name"], cfg["display_name"], cfg["workspace_root"]), encoding="utf-8"
        )


def _pm_prompt(name: str, display: str, ws: str) -> str:
    return f"""# PM-TL — Análisis de Tickets — {display}

## Contexto del Proyecto

- **Cliente / Proyecto:** {display}
- **Workspace:** `{ws}`
- **Stack:** ASP.NET WebForms (OnLine) + C# .NET (Batch) + Oracle (sin Entity Framework)

## Carpeta de trabajo del ticket

`tools/stacky/projects/{name}/tickets/{{estado}}/{{ticket_id}}/`

Contiene `INC-{{ticket_id}}.md` con los datos crudos del ticket + los 6 archivos de análisis
generados como placeholder por el scraper que debés completar.

## Tu tarea

1. Leé `INC-{{ticket_id}}.md` completamente — descripción, pasos, historial, adjuntos
2. Completá los 6 archivos SIN dejar placeholders:
   - `INCIDENTE.md` — severidad, categoría, impacto, URL tracker
   - `ANALISIS_TECNICO.md` — causa raíz, componentes, flujo actual vs. esperado
   - `ARQUITECTURA_SOLUCION.md` — qué cambiar exactamente y dónde
   - `TAREAS_DESARROLLO.md` — tareas con criterios de aceptación verificables, estado PENDIENTE
   - `QUERIES_ANALISIS.sql` — queries de diagnóstico y verificación post-fix
   - `NOTAS_IMPLEMENTACION.md` — convenciones críticas, advertencias, dependencias
3. Para cada tarea: nombre corto, archivos a modificar (rutas relativas desde `{ws}`),
   criterios medibles, estado PENDIENTE
4. Al finalizar: crear `PM_COMPLETADO.flag` en la carpeta del ticket
5. Si hay un bloqueante real: crear `PM_ERROR.flag` con descripción

## Convenciones del proyecto {display}

### Mensajes al usuario — RIDIOMA (obligatorio)
- NUNCA hardcodear mensajes visibles al usuario
- Usar siempre `Idm.Texto(coMens.mXXXX)` con constante en `coMens.cs`
- Para mensajes nuevos: INSERT en tabla RIDIOMA (idioma ES + ENG mínimo)
- Workspace del QueryRunner para verificar: `tools/OracleQueryRunner/`

### Base de datos
- Oracle sin Entity Framework — DAL directo con queries parametrizadas
- Validar estructura: `ALL_TAB_COLUMNS WHERE TABLE_NAME = 'TABLA'` antes de consultar

### Logging (Batch)
```csharp
Log.Error("descripción del error", ex);
Log.Info("descripción de acción");
```

### Validaciones OnLine
```csharp
Error.Agregar(Const.ERROR_VALID, Idm.Texto(coMens.mXXXX, "fallback"), "Ctx", Const.SEVERIDAD_Baja);
msgd.Show(Error, Idm.Texto(coMens.m2500, "Error"));
```
"""


def _dev_prompt(name: str, display: str, ws: str) -> str:
    return f"""# Developer — Implementación — {display}

## Contexto del Proyecto

- **Cliente / Proyecto:** {display}
- **Workspace:** `{ws}`
- **Stack:** ASP.NET WebForms (OnLine) + C# .NET (Batch) + Oracle

## Carpeta de trabajo

`tools/stacky/projects/{name}/tickets/{{estado}}/{{ticket_id}}/`

## Arranque obligatorio

Antes de tocar código, leé en este orden:
1. `INC-{{ticket_id}}.md` — descripción original del ticket (contexto completo)
2. `INCIDENTE.md` — severidad y categoría
3. `ANALISIS_TECNICO.md` — causa raíz y componentes afectados
4. `ARQUITECTURA_SOLUCION.md` — qué cambiar y dónde
5. `NOTAS_IMPLEMENTACION.md` — advertencias y dependencias
6. `QUERIES_ANALISIS.sql` — queries de verificación
7. `TAREAS_DESARROLLO.md` ← **ejecutar TODAS las tareas en estado PENDIENTE**

Si cualquiera de los archivos 2-7 tiene placeholders sin completar, **NO procedas**.
Indicar que primero debe ejecutarse la etapa PM-TL.

## Convenciones obligatorias — {display}

### Mensajes de usuario — RIDIOMA
```csharp
// CORRECTO
Idm.Texto(coMens.mXXXX)

// INCORRECTO — nunca hardcodear
"mensaje hardcodeado"
```
Para mensajes nuevos:
1. `SELECT MAX(IDTEXTO) FROM RIDIOMA` → obtener próximo ID
2. Agregar constante en `OnLine/Negocio/Comun/coMens.cs`
3. Script SQL INSERT en RIDIOMA (ES + ENG mínimo)

### Oracle
- Sin Entity Framework — DAL directo con queries parametrizadas
- Validar estructura: `ALL_TAB_COLUMNS WHERE TABLE_NAME = 'TABLA'`

### Logging (Batch)
```csharp
Log.Error("descripción del error", ex);
Log.Info("descripción de acción");
```

### Validaciones OnLine
```csharp
RSFac.Idioma Idm = new RSFac.Idioma();
Error.Agregar(Const.ERROR_VALID, Idm.Texto(coMens.mXXXX, "fallback"), "Ctx", Const.SEVERIDAD_Baja);
msgd.Show(Error, Idm.Texto(coMens.m2500, "Error"));
```

### Estructura del proyecto
```
{ws}/
  OnLine/
    AgendaWeb/          → formularios ASPX + code-behind
    Negocio/Comun/      → coMens.cs, constantes compartidas
    RSXxx/              → servicios por módulo
  Batch/
    Motor/              → máquina de estados
    RSXxx/              → servicios batch por módulo
    Negocio/            → lógica compartida
    XMLConfig.xml       → configuración centralizada
```

## Al finalizar

Creá `DEV_COMPLETADO.md` en la carpeta del ticket con:
- Lista de archivos modificados (rutas relativas desde `{ws}`)
- Resumen de cambios por tarea
- Observaciones o pendientes

Si bloqueante: `DEV_ERROR.flag` con descripción del bloqueo.

## Reglas de calidad
- No hardcodear mensajes — siempre RIDIOMA
- No modificar más archivos de los necesarios para cumplir el objetivo
- Reutilizar lógica existente antes de crear nuevas clases/métodos
- Dejar trazabilidad por archivo y decisión en `DEV_COMPLETADO.md`
"""


def _qa_prompt(name: str, display: str, ws: str) -> str:
    return f"""# QA Tester — Validación — {display}

## Contexto del Proyecto

- **Cliente / Proyecto:** {display}
- **Workspace:** `{ws}`
- **Stack:** ASP.NET WebForms (OnLine) + C# .NET (Batch) + Oracle

## Carpeta de trabajo

`tools/stacky/projects/{name}/tickets/{{estado}}/{{ticket_id}}/`

## Arranque obligatorio

Leé en este orden:
1. `INC-{{ticket_id}}.md` — descripción original, pasos para reproducir
2. `INCIDENTE.md` — severidad, impacto de negocio
3. `ANALISIS_TECNICO.md` — causa raíz identificada
4. `ARQUITECTURA_SOLUCION.md` — qué se propuso cambiar
5. `TAREAS_DESARROLLO.md` — criterios de aceptación
6. `DEV_COMPLETADO.md` — qué implementó el Developer ← **REQUERIDO**

Si `DEV_COMPLETADO.md` no existe: **no procedas**. La etapa Dev debe completarse primero.

## Convenciones a validar — {display}

- [ ] Mensajes al usuario usan `Idm.Texto(coMens.mXXXX)` — sin hardcodeo
- [ ] Nuevos mensajes tienen INSERT en RIDIOMA (ES + ENG)
- [ ] Queries Oracle parametrizadas (sin concatenación de input)
- [ ] Batch: errores logueados con `Log.Error(msg, ex)`
- [ ] OnLine: excepciones no llegan al usuario sin manejar
- [ ] No se modificaron archivos fuera del scope de las tareas

## Protocolo de pruebas (por cada tarea)

1. **Verificación de código** — revisar archivos indicados en `DEV_COMPLETADO.md`
2. **Happy path** — flujo normal funciona como se esperaba
3. **Casos de error** — entradas inválidas, nulos, condiciones de borde
4. **Regresión** — flujos no tocados siguen funcionando
5. **Validación de datos** — usar QueryRunner si aplica

## Veredicto final

Uno de:
- `APROBADO` — todos los criterios cumplidos, sin defectos bloqueantes
- `CON OBSERVACIONES` — criterios principales cumplidos, hay observaciones menores
- `RECHAZADO` — criterios no cumplidos o defectos de severidad Alta

## Al finalizar

Creá `TESTER_COMPLETADO.md` en la carpeta del ticket con:
- **Veredicto** global
- Tabla de defectos encontrados
- Resultados por tarea (happy path, error, regresión)
- Queries de verificación ejecutadas
- Pasos para verificación manual

Si bloqueante: `TESTER_ERROR.flag` con descripción.
"""
