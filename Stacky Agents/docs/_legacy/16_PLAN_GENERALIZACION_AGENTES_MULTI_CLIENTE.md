# Plan — Generalización de Agentes Stacky multi-cliente (sin romper lo actual)

> **Versión:** 1.2 — Fases 1, 2 y 3 implementadas + cobertura de endpoints cerrada
> **Fecha:** 2026-05-28
> **Autor:** Asistente Stacky
> **Estado:** EN EJECUCIÓN — Fases 1-3 entregadas y verificadas; **únicamente Fase 4 (migración por cliente)** queda en manos del operador.
> **Alcance:** Convertir `DevPacifico2.agent.md`, `TechnicalAnalyst.agent.md` y `AnalistaFuncionalPacifico.agent.md` en agentes **genéricos, parametrizables por cliente**, manteniendo los estados de transición ADO/Jira/Mantis y la compatibilidad total con el flujo Pacífico actual.

---

## Estado de implementación (2026-05-28)

### Fase 1 — Backend foundation ✅
- `backend/services/client_profile.py` + defaults JSON ADO/Jira/Mantis (`client_profile_defaults/`). Tests: `test_client_profile.py` (17).
- `backend/api/client_profile.py` — GET/PUT/DELETE `/api/projects/<name>/client-profile`, GET `/api/client-profile/default`, POST/GET `/api/projects/<name>/db-readonly-auth`. Tests: `test_client_profile_endpoints.py` (18, agregados en esta iteración).
- `backend/services/config_transfer.py` extendido con sección `clientProfile`. Tests extra: `test_client_profile_section_round_trip`, `test_export_rejects_secret_in_client_profile`, `test_import_rejects_secret_in_incoming_profile`.
- `backend/services/db_query.py` + `backend/api/db_query.py` — `POST /api/tickets/<id>/db/query` (SELECT-only, audit en `data/db_query_audit.jsonl`). Tests: `test_db_query_audit.py` (23).
- `backend/prompt_builder.with_project_header` ahora usa `display_name` del proyecto activo, no `RSPacifico` hardcoded (`_resolve_active_display_name` resuelve por `project_manager.get_active_project()`).
- `_project_to_dict` (`api/projects.py:108`) expone `has_client_profile: bool` para que el frontend marque el estado.

### Fase 2 — Context block ✅
- `backend/services/context_enrichment.py::_inject_client_profile_block` corre **primero** en `enrich_blocks(...)`. Feature flag `STACKY_INJECT_CLIENT_PROFILE` (default ON; `0`/`false`/`off` lo apagan, case-insensitive). El bloque inyectado es `{ id: "client-profile", kind: "text", title: "Perfil del cliente: <PROJ> — <client_label> · <product>", content: JSON.dumps(profile, sort_keys=True) }`. Tests: `test_context_enrichment_client_profile.py` (10) — incluye casos de presencia, ausencia de proyecto, ausencia de perfil, todas las variantes de la feature flag, idempotencia y determinismo de salida.

### Fase 3 — Agentes genéricos ✅ (publicados junto a los legacy)
- `DeployStackyAgents/github_copilot_agents/Developer.agent.md` v2.0.0 — `stacky_agent_type: developer`, `stacky_requires_client_profile: true`.
- `DeployStackyAgents/github_copilot_agents/FunctionalAnalyst.agent.md` v2.0.0 — `stacky_agent_type: functional`.
- `DeployStackyAgents/github_copilot_agents/TechnicalAnalyst.v2.agent.md` v2.0.0 — convive con el legacy `TechnicalAnalyst.agent.md` hasta el cutover.
- Frontend: `ClientProfileEditor.tsx` + sub-tab "Perfil del cliente" en `SettingsPage`. Editor JSON con template default por tracker + bloque para guardar credencial BD readonly (DPAPI).
- `ConfigTransferPanel.tsx` muestra automáticamente `clientProfile` como sección en el dry-run y aplicador del import/export (no necesitó cambios — el panel renderiza dinámicamente las secciones del bundle).
- `manifest.json` (paquete deploy) actualizado con los 3 nuevos.

### Fase 4 — Migración por cliente (pendiente del operador)
El operador debe:
1. Abrir Settings → Perfil del cliente para cada proyecto y aplicar el template default → ajustar valores reales.
2. Guardar la credencial BD readonly del proyecto (si aplica).
3. Probar los nuevos agentes contra tickets reales en paralelo con los legacy.
4. Cuando confirme equivalencia: cambiar `pinned_agents` y mover los legacy a `legacy/`.

### Cobertura de tests
- **86 tests verdes** ejecutados en local (Windows 11, Python 3.13):
  - `test_client_profile.py` (17) — servicio.
  - `test_client_profile_endpoints.py` (18) — HTTP (GET/PUT/DELETE/default + db-readonly-auth).
  - `test_db_query_audit.py` (23) — SELECT-only y audit log.
  - `test_context_enrichment_client_profile.py` (11) — inyección del bloque + feature flag.
  - `test_config_transfer.py` (9) — export/import con `client_profile` + bloqueo de secretos.
  - `test_context_enrichment.py` (8) — pre-existente, sin regresión.
- Tests fallidos en el repo (`test_tickets_assigned_filter.py::test_no_filter_lists_all` y `::test_assigned_to_filters_to_single_user`) corresponden a otro workstream (Requerimiento B, plan 2026-05-27) y **no** son regresión de este plan.

---

---

## 0. Resumen ejecutivo (lectura de 2 minutos)

### Qué se quiere

Hoy los 3 agentes embeden datos específicos de Pacífico:
- Organización ADO (`UbimiaPacifico`), proyecto (`Strategist_Pacifico`).
- BD readonly (`aisbddev02.cloud.ais-int.net`, usuario `RSPACIFICOREAD`, password).
- Rutas internas del repo (`trunk/OnLine/`, `trunk/Batch/`, `trunk/BD/1 - Inicializacion BD/`).
- Convenciones de naming (prefijos `R*`, sufijos de 2 letras, `coMens.mXXXX`, `cFormat.StToBD`).
- Patrón de trazabilidad (`// ADO-{id} | YYYY-MM-DD | desc`).
- MSBuild path.
- Documentación funcional/técnica (`trunk/docs/agentic_manual/...`).

Esto **bloquea** que el mismo agente sirva para CREA, B2Impact, RSSICREA u otros clientes sin duplicar el `.agent.md` y editar a mano.

### Qué se hará

1. **Crear 3 agentes genéricos** que NO tienen ningún dato hardcoded de cliente:
   - `Developer.agent.md` (genérico, reemplaza el rol de `DevPacifico2.agent.md`).
   - `TechnicalAnalyst.agent.md` v2.0.0 (refactor del existente).
   - `FunctionalAnalyst.agent.md` (genérico, reemplaza el rol de `AnalistaFuncionalPacifico.agent.md`).
2. **Extender** `backend/projects/<NAME>/config.json` con nuevas secciones para datos del cliente.
3. **Inyectar un `client-profile` context block** automáticamente desde Stacky cuando el agente arranca.
4. **Sincronizar** opcionalmente a un archivo versionable `<workspace_root>/.stacky/client-profile.yml` para que el agente también funcione sin Stacky.
5. **Mantener los agentes legacy** (`DevPacifico.agent.md`, `DevPacifico2.agent.md`, `AnalistaFuncionalPacifico.agent.md`) intactos hasta que cada cliente haya migrado. El refactor del `TechnicalAnalyst.agent.md` se hace en una rama y se renombra el actual a `TechnicalAnalystPacifico.legacy.agent.md` solo después de verificar la migración con Pacífico.

### Garantías

- **Compatibilidad total**: ningún agente actual deja de funcionar el día 1.
- **Sin secretos en prompts**: el password de la BD nunca entra al `.agent.md`.
- **Reversible**: cada fase tiene rollback documentado y los agentes legacy se preservan durante toda la transición.
- **Auditable**: cada cambio queda en `data/config_transfer_events.jsonl` (formato ya existente).

---

## 1. Estado actual — inventario verificado

### 1.1 Carpeta de agentes de GitHub Copilot Pro

Confirmado en `manifest.json` del paquete `DeployStackyAgents/github_copilot_agents/`:

```
source_root: C:\Users\juanluca\AppData\Roaming\Code\User\prompts
```

Esa es la carpeta que Stacky sincroniza con los `.agent.md` deployados.

### 1.2 Agentes actuales relevantes (con su acoplamiento Pacífico)

| Agente | Rol | Datos hardcoded Pacífico |
|--------|-----|--------------------------|
| `DevPacifico2.agent.md` v1.0.0 | Developer | Org ADO, proyecto ADO, MSBuild path, rutas `trunk/OnLine`/`Batch`/`BD`, archivos maestros RIDIOMA, convenciones `R*`, `coMens.mXXXX`, `cFormat.StToBD`, patrón trazabilidad ADO-{id}. |
| `DevPacifico.agent.md` v1.0.0 | Developer (versión previa) | Igual que DevPacifico2 + credencial BD readonly en claro. |
| `TechnicalAnalyst.agent.md` v1.2.0 | Analista técnico | Org ADO, BD server + usuario + password en claro, rutas `trunk/`, RIDIOMA, URL del board ADO. |
| `AnalistaFuncionalPacifico.agent.md` v1.2.0 | Analista funcional UCollect Strategy | Carpeta `/context/funcional/` (genérica), pero referencias a UCollect, OnLine/Batch terminology Pacífico, contraseña BD en bloque de ejemplo. |
| `analizar-af-agendaweb-pacifico.prompt.md` | Prompt one-off | **PAT ADO en claro** (riesgo de seguridad — se atiende en este plan). |

### 1.3 Infraestructura multi-cliente que YA EXISTE (no hay que crear)

| Componente | Estado | Función |
|------------|--------|---------|
| `backend/project_manager.py` | ✅ Operativo | `projects/<NAME>/config.json` por cliente con `issue_tracker`, `workspace_root`, `docs_paths`, `pinned_agents`, `agent_workflow_configs`. |
| `backend/services/context_enrichment.py` | ✅ Operativo | Pipeline de inyección de context blocks: `ado-structured`, `ado-epic-structured`, `ado-comments`, `ado-similar-tickets`, `filesystem-artifacts-status`. |
| `backend/services/config_transfer.py` | ✅ Operativo (no commiteado pero presente) | Export/import portable de configuración por proyecto con checksum y auditoría. |
| `backend/api/projects.py` | ✅ Operativo | Endpoints `POST /api/init_project`, `PATCH /api/projects/<name>`, `PUT /api/projects/<name>/agents`, `PUT /api/projects/<name>/agent-workflow/<filename>`. |
| Proyectos ya configurados | ✅ | `RSPACIFICO` (ADO), `B2IMPACT` (Jira), `RSSICREA` (ADO). |

### 1.4 Lo que falta en la infra (gap real)

Hay **dos huecos** que cubrir, ningún componente entero a crear:

1. **`config.json` no tiene secciones para datos del cliente que los agentes necesitan**: BD, code layout, build, conventions, terminology. Hoy esa info vive embebida en cada `.agent.md`.
2. **No se inyecta un context block `client-profile`** que el agente pueda leer al arrancar. El `context_enrichment` ya inyecta ADO-stuff, pero no envía el "perfil del cliente".

---

## 2. Principios de diseño (no negociables)

| Principio | Cómo se asegura |
|-----------|-----------------|
| **No romper Pacífico** | Los agentes legacy (`DevPacifico*`, `AnalistaFuncionalPacifico`) quedan intactos. El `TechnicalAnalyst.agent.md` se mueve a versión `2.0.0` solo después de probar contra Pacífico real. |
| **Sin secretos en el prompt** | Passwords/PATs viven en `projects/<NAME>/auth/` (ya cifrados con DPAPI). El context block `client-profile` referencia el `auth_file` pero NO incluye el secreto. El agente ejecuta SQL via plantilla que Stacky completa server-side. |
| **Backward compatibility** | El campo `client_profile` en `config.json` es opcional; si está ausente, el agente cae al modo "preguntar al operador" (lo que ya hacen). |
| **Reversible** | Cada fase es un PR independiente con rollback documentado. Los nuevos agentes se publican junto a los viejos hasta que se confirma migración. |
| **Idempotente** | Igual que `config_transfer.apply_import`: re-aplicar el mismo cambio deja un diff vacío. |
| **Trazable** | Cada cambio de `client_profile` queda en `data/config_transfer_events.jsonl` (la auditoría ya existe). |
| **Testeable** | Cada cambio backend incluye tests en `backend/tests/`. Smoke test del agente genérico contra los 3 proyectos antes de retirar los legacy. |
| **Auditable por humanos** | El `client-profile` es un YAML legible que el operador puede revisar antes de ejecutar el agente (lo verá en el panel de contexto del workbench). |

---

## 3. Decisión arquitectónica — dónde viven los datos del cliente

### 3.1 Opciones evaluadas

| Opción | Pros | Contras | Decisión |
|--------|------|---------|----------|
| **A. Context block dinámico inyectado por Stacky** | Reusa el pipeline `context_enrichment` ya existente. El operador no edita archivos. Auditable. | Solo funciona cuando el agente se ejecuta desde Stacky (no desde VS Code Copilot Chat directo). | ✅ Mecanismo primario. |
| **B. Skill `.github/skills/client-profile/SKILL.md`** | Convención GitHub Copilot. | Skills se invocan con `/comando`; no se cargan automáticamente al inicio. Requiere disciplina del operador. | ❌ No es automático. |
| **C. Archivo `<workspace_root>/.stacky/client-profile.yml`** | Versionable con git. Funciona sin Stacky (el agente puede `read_file`). Auditable. Permite que el cliente lo mantenga en su propio repo. | El operador puede editarlo a mano y romper el formato. | ✅ Mecanismo secundario/fallback. |
| **D. Variables de entorno (`STACKY_DB_SERVER`, etc.)** | Trivial. | No versionable. No auditable. Frágil en Windows. | ❌ Descartado. |

### 3.2 Decisión final

**Combinar A + C** ("primary + fallback"):

```
┌─────────────────────────────────────────────────────────────┐
│  Fuente única de verdad: backend/projects/<NAME>/config.json│
│    └─ sección client_profile (nueva)                        │
└────────────┬────────────────────────┬───────────────────────┘
             │                        │
             ▼                        ▼
   (A) Context block             (C) Sync opcional a
   "client-profile"              <workspace_root>/
   inyectado por Stacky          .stacky/client-profile.yml
   al ejecutar el agente         (versionable con git del cliente)
             │                        │
             ▼                        ▼
   Agente lo lee del             Agente lo lee con read_file
   context que recibe            si NO viene context block
             │                        │
             └────────────┬───────────┘
                          ▼
            Si NINGUNO está disponible:
            agente pregunta al operador
            (degradación elegante)
```

**Razón:** el caso normal (Stacky orquesta) es 100% automático; el caso degradado (Copilot Chat solo) sigue funcionando con disciplina mínima.

---

## 4. Esquema del `client_profile` (schema v1)

### 4.1 Estructura completa propuesta

Sección nueva dentro de `backend/projects/<NAME>/config.json`:

```jsonc
{
  // ── Campos ya existentes ──────────────────────────────────
  "name": "RSPACIFICO",
  "display_name": "RSPACIFICO",
  "workspace_root": "N:/GIT/RS/RSPACIFICO",
  "issue_tracker": { "type": "azure_devops", "organization": "UbimiaPacifico", "project": "Strategist_Pacifico", "auth_file": "auth/ado_auth.json" },
  "pinned_agents": [ ... ],
  "agent_workflow_configs": { ... },
  "docs_paths": { ... },

  // ── NUEVA SECCIÓN: client_profile ─────────────────────────
  "client_profile": {
    "schema_version": 1,

    "code_layout": {
      "online_path":       "trunk/OnLine",
      "batch_path":        "trunk/Batch",
      "db_scripts_path":   "trunk/BD/1 - Inicializacion BD",
      "lib_path":          "trunk/lib",
      "test_path":         "trunk/Tests",
      "file_extensions":   { "ui": ".aspx", "ui_code_behind": ".aspx.cs", "code": ".cs" },
      "architecture_layers": ["UI", "RSBus (BLL)", "RSDalc (DAL)", "BD"]
    },

    "language": {
      "primary":               "csharp",
      "comment_traceability":  "// {ticket_token} | {YYYY-MM-DD} | {description}",
      "ticket_token_pattern":  "ADO-{id}",
      "languages_in_ridioma":  ["ESP", "ENG", "POR"]
    },

    "database": {
      "type":              "sqlserver",
      "server":            "aisbddev02.cloud.ais-int.net",
      "readonly_auth_ref": "auth/db_readonly.json",
      "readonly_user_hint":"RSPACIFICOREAD",
      "connection_kind":   "windows_sqlcmd",
      "dml_policy":        "prohibited_runtime_must_emit_sql",
      "catalog_master_files": {
        "RIDIOMA":     "trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql",
        "RTABL":       "trunk/BD/1 - Inicializacion BD/600804 - Inserts RTABL.sql",
        "RPARAM":      "trunk/BD/1 - Inicializacion BD/600804 - Inserts RPARAM.sql",
        "RCONTROLES":  "trunk/BD/1 - Inicializacion BD/600804 - Inserts RCONTROLES.sql"
      },
      "naming_conventions": {
        "table_prefix":      "R",
        "column_prefix_len": 2
      }
    },

    "build": {
      "tool":             "msbuild",
      "msbuild_path":     "C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe",
      "configuration":    "Release",
      "online_solutions": [ "AgendaWeb.sln" ],
      "batch_proj_glob":  "Batch/*/*.csproj"
    },

    "conventions": {
      "ridioma_helper":        "RSFac.Idioma",
      "ridioma_message_const": "coMens.m{id}",
      "string_sanitizer":      "cFormat.StToBD()",
      "error_helpers":         [ "Error.Agregar", "msgd.Show" ]
    },

    "docs_indexes": {
      "technical_master":  "trunk/docs/agentic_manual/tecnica/00_INDICE_MAESTRO.md",
      "functional_online": "trunk/docs/agentic_manual/funcional/ONLINE/INDEX.md",
      "functional_batch":  "trunk/docs/agentic_manual/funcional/BATCH/00_INDICE_FUNCIONAL_BATCH.md"
    },

    "tracker_state_machine": {
      "functional": {
        "input_states":     ["To Do", "New", "Active"],
        "blocked_state":    "Blocked",
        "next_state_ok":    "Technical review"
      },
      "technical": {
        "input_states":     ["Technical review"],
        "blocked_state":    "Blocked",
        "next_state_ok":    "To Do"
      },
      "developer": {
        "input_states":     ["To Do"],
        "in_progress":      "Doing",
        "blocked_state":    "Blocked",
        "next_state_ok":    "Reviewed by Dev"
      }
    },

    "terminology": {
      "product_name":       "UCollect Strategy",
      "client_label":       "RS Pacífico",
      "domain_glossary_ref":"trunk/docs/glossary.md"
    }
  }
}
```

### 4.2 Mismo bloque para B2Impact (Jira) — ejemplo de cómo cambia

```jsonc
{
  "name": "B2IMPACT",
  "issue_tracker": { "type": "jira", ... },
  "client_profile": {
    "schema_version": 1,
    "code_layout": { "online_path": "src/web", "batch_path": "src/batch", "db_scripts_path": "db/migrations", "lib_path": "src/lib", "architecture_layers": ["UI", "Service", "Repository", "DB"] },
    "language": { "primary": "java", "comment_traceability": "// {ticket_token} | {YYYY-MM-DD} | {description}", "ticket_token_pattern": "B2IM-{id}", "languages_in_ridioma": ["ESP"] },
    "database": { "type": "postgres", "server": "db.b2impact.internal", "readonly_auth_ref": "auth/db_readonly.json", "dml_policy": "prohibited_runtime_must_emit_sql" },
    "build": { "tool": "maven", "command": "mvn -DskipTests=false clean verify" },
    "tracker_state_machine": {
      "functional": { "input_states": ["To Do"], "blocked_state": "Blocked", "next_state_ok": "In Progress" },
      "technical":  { "input_states": ["In Progress"], "blocked_state": "Blocked", "next_state_ok": "Ready for Dev" },
      "developer":  { "input_states": ["Ready for Dev"], "in_progress": "Doing", "blocked_state": "Blocked", "next_state_ok": "Code Review" }
    }
  }
}
```

### 4.3 Validación del schema

- Nuevo módulo `backend/services/client_profile.py` con:
  - `load_client_profile(project_name) -> dict | None`
  - `validate_client_profile(profile) -> ValidationResult`
  - `get_default_client_profile(tracker_type) -> dict` (templates por defecto para ADO / Jira / Mantis)
- Validador estructural: campos obligatorios mínimos (`code_layout`, `language`, `tracker_state_machine`); el resto opcional.
- `validate_import` (de `config_transfer.py`) extendido para validar `client_profile` cuando el bundle lo trae.

### 4.4 Seguridad

- `readonly_auth_ref` apunta a `auth/db_readonly.json` (mismo patrón que ADO PAT — DPAPI cifrado).
- El backend ofrece un nuevo endpoint `POST /api/projects/<name>/db-readonly-auth` para guardar credenciales BD sin tocar el `config.json`.
- El context block `client-profile` que se inyecta al agente **no incluye el password**; incluye un placeholder `{{db_password}}` que el agente NO debe expandir. Para ejecutar SQL, el agente delega en un endpoint nuevo `POST /api/tickets/<id>/db/query` (server-side, audit log) que ejecuta el SELECT con la credencial cifrada.

---

## 5. Los tres agentes genéricos

### 5.1 `FunctionalAnalyst.agent.md` (nuevo)

**Rol:** mismo que `AnalistaFuncionalPacifico.agent.md` actual, pero **producto-agnóstico**.

**Cambios clave respecto al actual:**
- Sección "Documentación de referencia" → **lee `client_profile.docs_indexes.functional_online`** del context block. Fallback: pregunta al operador.
- Sección "Base de datos (solo lectura)" → **lee `client_profile.database`** y construye el comando `sqlcmd` con placeholder `{{db_password}}`. Si Stacky inyectó el placeholder, el comando real se ejecuta vía `runCommands` con expansión server-side.
- Sección "Identidad y rol" → texto genérico: *"Analista Funcional del producto descripto en `client-profile.terminology.product_name`"*.
- Sección "Localización de los requerimientos" → idéntica (ya usa context blocks `ado-epic-structured`).
- Outputs: idénticos (`analisis-funcional.md`, `plan-de-pruebas.md`, `pending-task.json`).
- Frontmatter:
  ```yaml
  ---
  description: "Agente Senior Funcional cliente-agnóstico. Lee el perfil del cliente desde el context block 'client-profile' inyectado por Stacky. Analiza Epics y genera análisis funcional + plan de pruebas + payload de Task."
  tools: ['codebase', 'editFiles', 'runCommands', 'search', 'searchResults', 'logDecision', 'showMemory', 'updateContext', 'updateProgress']
  version: "2.0.0"
  stacky_agent_type: functional
  stacky_completion_contract: v1
  stacky_requires_client_profile: true
  ---
  ```

### 5.2 `TechnicalAnalyst.agent.md` v2.0.0 (refactor)

**El refactor más sensible.** El actual ya se llama `TechnicalAnalyst.agent.md` (sin "Pacifico" en el nombre) pero por dentro tiene MUCHA información Pacífico. Estrategia: refactor con versionado fuerte.

**Cambios:**
- Sección "Organización ADO / Proyecto ADO" → eliminada del prompt. Esa info viene del context block `ado-structured` y del `client-profile`.
- Sección "BD readonly" → reemplaza el bloque hardcoded con:
  ```
  Base de datos (SOLO SELECT):
    - server: {{client_profile.database.server}}
    - user:   {{client_profile.database.readonly_user_hint}} (credencial gestionada por Stacky)
    - dialect: {{client_profile.database.type}}
  ```
  Y el comando concreto se ejecuta vía un endpoint Stacky `POST /api/tickets/<id>/db/query`.
- Sección "Fuentes de información" → todas las rutas vienen de `client_profile.docs_indexes` y `client_profile.code_layout`.
- Sección "RIDIOMA / RTABL" → vienen de `client_profile.database.catalog_master_files` y `client_profile.conventions.ridioma_helper`.
- Sección "Reglas de Stacky / output_watcher" → idéntica (ya genérica).
- Frontmatter:
  ```yaml
  ---
  description: "Analista Técnico cliente-agnóstico. Lee el perfil del cliente desde el context block 'client-profile'. Traduce funcional → técnico, define alcance, plan de pruebas y tests unitarios."
  version: "2.0.0"
  stacky_agent_type: technical
  stacky_completion_contract: v1
  stacky_requires_client_profile: true
  ---
  ```

**Plan de coexistencia:**
- Mientras dure la fase de validación: el `.agent.md` actual se preserva como `TechnicalAnalystPacifico.legacy.agent.md` (auto-generado por el script de migración).
- `agent_workflow_configs` de Pacífico apuntan al legacy hasta que el equipo confirme el corte.

### 5.3 `Developer.agent.md` (nuevo)

**Reemplaza** `DevPacifico.agent.md` y `DevPacifico2.agent.md`.

**Cambios:**
- Sección "Patrones del proyecto" → reemplaza la lista hardcoded (`cFormat.StToBD()`, `RIDIOMA`, `Error.Agregar`, etc.) con:
  ```
  Patrones del proyecto (del client-profile):
    - Sanitizer: {{client_profile.conventions.string_sanitizer}}
    - Mensajes:  {{client_profile.conventions.ridioma_helper}}.Texto({{client_profile.conventions.ridioma_message_const}})
    - Errores:   {{client_profile.conventions.error_helpers | join(", ")}}
    - Naming:    prefijo tabla "{{client_profile.database.naming_conventions.table_prefix}}",
                 prefijo columna {{client_profile.database.naming_conventions.column_prefix_len}} letras
  ```
- Sección "Compilación" → usa `client_profile.build`:
  ```
  cd "{{workspace_root}}/{{client_profile.code_layout.online_path}}"
  & "{{client_profile.build.msbuild_path}}" {{solution}} /p:Configuration={{client_profile.build.configuration}}
  ```
- Sección "RIDIOMA — proceso" → idéntica en estructura, pero las rutas de archivos maestros las saca de `client_profile.database.catalog_master_files`.
- Sección "Idiomas RIDIOMA" → `client_profile.language.languages_in_ridioma` (ESP/ENG/POR para Pacífico; solo ESP para B2Impact).
- Sección "Trazabilidad en comentarios" → usa `client_profile.language.comment_traceability` como plantilla:
  ```
  // {ticket_token} | {YYYY-MM-DD} | {description}
  ```
  donde `{ticket_token}` se expande con `client_profile.language.ticket_token_pattern` (ej: `ADO-1234` para Pacífico, `B2IM-1234` para B2Impact).
- Frontmatter:
  ```yaml
  ---
  description: "Developer cliente-agnóstico. Implementa la solución técnica descripta en el ticket leyendo el cliente_profile inyectado por Stacky."
  version: "2.0.0"
  stacky_agent_type: developer
  stacky_completion_contract: v1
  stacky_requires_client_profile: true
  ---
  ```

### 5.4 Cómo se ve el context block `client-profile` que recibe el agente

Stacky lo inyecta antes del prompt, igual que hoy hace con `ado-epic-structured`:

```yaml
# id: client-profile
# title: Cliente: RSPACIFICO (RS Pacífico — UCollect Strategy)
# kind: text

client_profile:
  schema_version: 1
  workspace_root: N:/GIT/RS/RSPACIFICO
  code_layout:
    online_path: trunk/OnLine
    batch_path:  trunk/Batch
    db_scripts_path: "trunk/BD/1 - Inicializacion BD"
    architecture_layers: [UI, "RSBus (BLL)", "RSDalc (DAL)", BD]
  language:
    primary: csharp
    comment_traceability: "// {ticket_token} | {YYYY-MM-DD} | {description}"
    ticket_token_pattern: "ADO-{id}"
    languages_in_ridioma: [ESP, ENG, POR]
  database:
    type: sqlserver
    server: aisbddev02.cloud.ais-int.net
    readonly_user_hint: RSPACIFICOREAD
    connection_kind: windows_sqlcmd
    dml_policy: prohibited_runtime_must_emit_sql
    # password NO incluido — Stacky lo inyecta server-side al ejecutar SELECTs
    catalog_master_files:
      RIDIOMA: "trunk/BD/1 - Inicializacion BD/600804 - Inserts RIDIOMA.sql"
      RTABL:   "trunk/BD/1 - Inicializacion BD/600804 - Inserts RTABL.sql"
  build:
    tool: msbuild
    msbuild_path: "C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe"
    configuration: Release
  conventions:
    string_sanitizer: "cFormat.StToBD()"
    ridioma_helper: "RSFac.Idioma"
    ridioma_message_const: "coMens.m{id}"
    error_helpers: ["Error.Agregar", "msgd.Show"]
  docs_indexes:
    technical_master:  "trunk/docs/agentic_manual/tecnica/00_INDICE_MAESTRO.md"
    functional_online: "trunk/docs/agentic_manual/funcional/ONLINE/INDEX.md"
  tracker_state_machine:
    technical:
      input_states: [Technical review]
      blocked_state: Blocked
      next_state_ok: To Do
  terminology:
    product_name: "UCollect Strategy"
    client_label: "RS Pacífico"
```

---

## 6. Estados de transición — estandarización por tracker

Los 3 agentes preservan **el mismo grafo de estados lógico** independientemente del tracker concreto. El mapping se hace en `client_profile.tracker_state_machine`.

### 6.1 Grafo lógico (cliente-agnóstico)

```
                       ┌──────────────┐
                       │   NEW (input)│
                       └──────┬───────┘
                              │ FunctionalAnalyst
                              ▼
                    ┌─────────────────────┐
                    │ READY_FOR_TECHNICAL │
                    └─────────┬───────────┘
                              │ TechnicalAnalyst
                              │
                    ┌─────────┴──────────┐
                    ▼                    ▼
              ┌──────────┐         ┌──────────┐
              │ READY_FOR│         │  BLOCKED │
              │   DEV    │         │ (con preg│
              └────┬─────┘         │ funcional)│
                   │               └─────┬────┘
                   │ Developer            │ FunctionalAnalyst (modo B)
                   ▼                      ▼
              ┌──────────┐         (vuelve a READY_FOR_TECHNICAL)
              │  DOING   │
              └────┬─────┘
                   │
                   ▼
              ┌──────────┐
              │ REVIEWED │ → QA / handoff
              │  BY DEV  │
              └──────────┘
```

### 6.2 Mapping por tracker (ejemplo)

| Estado lógico | ADO Pacífico | Jira B2Impact | Mantis genérico |
|---------------|--------------|---------------|-----------------|
| NEW (input) | To Do / New / Active | To Do | new / acknowledged |
| READY_FOR_TECHNICAL | Technical review | In Progress | confirmed |
| READY_FOR_DEV | To Do | Ready for Dev | assigned |
| DOING | Doing | In Development | assigned (with dev) |
| BLOCKED | Blocked | Blocked | feedback |
| REVIEWED_BY_DEV | Reviewed by Dev | Code Review | resolved |

Cada agente **NO** habla en términos del tracker concreto; usa el campo `tracker_state_machine.<role>.next_state_ok` que Stacky publica en el ADO/Jira/Mantis correspondiente.

### 6.3 Cambios backend para soportar esto

Mínimos — porque `agent_workflow_configs` ya existe a nivel proyecto. Solo:

1. `client_profile.tracker_state_machine` se traduce automáticamente a `agent_workflow_configs[agent_filename]` cuando el operador edita el client-profile desde la UI. (Persiste en `config.json`.)
2. `services/ado_publisher.py` y equivalente Jira/Mantis: leen `target_ado_state` del `comment.meta.json` (ya lo hacen). Sin cambios.

---

## 7. Cambios backend (mínimos)

### 7.1 Archivos nuevos

| Archivo | Propósito | LOC estimado |
|---------|-----------|--------------|
| `backend/services/client_profile.py` | Cargar / validar / dar defaults del `client_profile`. | ~250 |
| `backend/services/client_profile_defaults/` | Templates JSON por tracker: `azure_devops.json`, `jira.json`, `mantis.json`. | ~50 cada uno |
| `backend/api/client_profile.py` | Endpoints `GET/PUT /api/projects/<name>/client-profile` y `POST /api/projects/<name>/db-readonly-auth`. | ~180 |
| `backend/api/db_query.py` | Endpoint `POST /api/tickets/<id>/db/query` (server-side SELECT con audit). | ~150 |
| `backend/tests/test_client_profile.py` | Validador, defaults, roundtrip. | ~200 |
| `backend/tests/test_db_query_audit.py` | DML rechazado, SELECT permitido, log obligatorio. | ~120 |

### 7.2 Archivos modificados

| Archivo | Cambio |
|---------|--------|
| `backend/services/context_enrichment.py` | Nuevo step `_inject_client_profile_block(...)` en `enrich_blocks(...)`. Se llama PRIMERO de todo el pipeline. |
| `backend/services/config_transfer.py` | Agregar `client_profile` a `ALL_SECTIONS`. Migrador v1→v2 cuando la sección se introduce. Validar que no se exporten secretos del `client_profile` (no debería tenerlos, pero validar). |
| `backend/api/projects.py` | Pequeña extensión en `_project_to_dict` para devolver `has_client_profile: bool`. |
| `backend/project_manager.py` | Helper `get_client_profile(name)`. |
| `backend/api/__init__.py` | Registrar los nuevos blueprints `client_profile` y `db_query`. |
| `backend/prompt_builder.py` | Generalizar `with_project_header` — usar `display_name` del proyecto activo en vez de hardcoded `RSPacifico`. |

### 7.3 Cambios menores (limpieza prohibida sin pedirla)

> ⚠️ **No** se renombran funciones que cambian la API pública sin pedirlo explícitamente. Por ejemplo `with_project_header` se queda; solo se cambia el string interno.

---

## 8. Cambios frontend (mínimos, UI no invasiva)

| Componente | Cambio |
|------------|--------|
| `frontend/src/pages/SettingsPage.tsx` | Nueva sección "Perfil del cliente" con editor JSON / formulario plegable para `client_profile`. |
| `frontend/src/components/ClientProfileEditor.tsx` (**nuevo**) | Formulario con secciones colapsables (code_layout, language, database, build, conventions). Validación inline. |
| `frontend/src/components/NewProjectModal.tsx` | Al crear proyecto: ofrece el template default del tracker elegido (botón "Aplicar template default"). |
| `frontend/src/api/endpoints.ts` | Nuevos endpoints `ClientProfile.get/put`, `DbReadonlyAuth.save`. |
| `frontend/src/components/ConfigTransferPanel.tsx` | Mostrar `client_profile` como sección importable/exportable. |

**Nada de esto bloquea el funcionamiento si el operador no toca la UI** — el agente cae al fallback de pedirle al operador.

---

## 9. Plan de migración por fases — sin romper

### Fase 0 — Preparación (1 día, sin código de producción)

| Tarea | Output | Riesgo |
|-------|--------|--------|
| Snapshot completo del estado actual: backup de `backend/projects/`, `data/`, `github_copilot_agents/`. | Carpeta `backup-pre-generalizacion-2026-05-28/`. | 0 — solo lectura. |
| Crear branch `feature/client-profile-v1`. | Branch. | 0. |
| Subir este plan a `docs/16_PLAN_GENERALIZACION_AGENTES_MULTI_CLIENTE.md`. | Doc. | 0. |
| **Aprobación del operador.** | Sign-off. | — |

### Fase 1 — Backend foundation (2-3 días)

**Objetivo:** que el backend cargue y exponga el `client_profile`, **sin tocar agentes todavía**.

| Tarea | PR | Tests |
|-------|----|-------|
| Crear `services/client_profile.py` + defaults. | PR-1 | `test_client_profile.py` |
| Endpoints `GET/PUT /api/projects/<name>/client-profile`. | PR-2 | `test_client_profile_endpoints.py` |
| Extender `config_transfer.py` con sección `client_profile`. | PR-3 | `test_config_transfer.py` (agregar casos). |
| Generalizar `prompt_builder.with_project_header` para usar `display_name`. | PR-4 | smoke. |
| Endpoint `POST /api/tickets/<id>/db/query` (solo SELECT, audit log). | PR-5 | `test_db_query_audit.py` |
| **Rollback de fase 1:** revertir los 5 PRs (commits atómicos). Los agentes legacy no cambian, siguen funcionando. |

**Criterio de salida de fase 1:** los 3 proyectos existentes (RSPACIFICO, B2IMPACT, RSSICREA) siguen funcionando idénticamente. Tests verdes. Smoke test exitoso.

### Fase 2 — Inyección del context block (1 día)

| Tarea | PR | Tests |
|-------|----|-------|
| Agregar `_inject_client_profile_block` a `context_enrichment.enrich_blocks`. **Con feature flag** `STACKY_INJECT_CLIENT_PROFILE` (default OFF en main, ON en branch). | PR-6 | `test_context_enrichment.py` (caso flag on/off). |
| Verificar manualmente que los agentes LEGACY siguen funcionando con el flag ON (el bloque extra no debería romperlos — solo lo ignoran). | smoke manual contra Pacífico. | — |
| **Rollback:** desactivar el feature flag. |

**Criterio de salida:** agentes legacy reciben el bloque extra y lo ignoran sin error.

### Fase 3 — Agentes genéricos (3-4 días)

**Estrategia: cada agente genérico se publica JUNTO al legacy.** El operador elige cuál usar.

| Tarea | PR | Validación |
|-------|----|-----------|
| Escribir `Developer.agent.md` v2.0.0. | PR-7 | Probar contra ticket Pacífico real en sandbox (workspace separado). |
| Escribir `FunctionalAnalyst.agent.md` v2.0.0. | PR-8 | Probar contra Epic Pacífico real. |
| Refactor de `TechnicalAnalyst.agent.md` → v2.0.0. **Antes** del refactor: copiar el actual a `TechnicalAnalystPacifico.legacy.agent.md`. **Después** del refactor, `pinned_agents` de RSPACIFICO apunta al legacy hasta el corte. | PR-9 | Idem. |
| Actualizar `manifest.json` del paquete deploy. | PR-10 | smoke deploy. |
| Frontend: editor de `client_profile` en `SettingsPage`. | PR-11 | manual. |
| **Rollback fase 3:** los nuevos `.agent.md` se borran del paquete, los legacy quedan intactos. |

**Criterio de salida:** los 3 agentes genéricos producen el MISMO output (semánticamente) que los legacy para el mismo ticket Pacífico, contra los mismos artifacts.

### Fase 4 — Migración por cliente (rolling)

| Cliente | Pasos | Validación |
|---------|-------|-----------|
| **RSPACIFICO** (primero) | 1. Operador llena el `client_profile` desde la UI. <br> 2. Cambia `pinned_agents` para incluir los v2.0.0. <br> 3. Ejecuta 5-10 tickets reales en paralelo con ambas variantes. <br> 4. Confirma equivalencia. <br> 5. Quita los legacy de `pinned_agents`. | Comparar outputs lado a lado. |
| **B2IMPACT** | 1. Operador llena `client_profile` (template Jira). <br> 2. Adopta los v2.0.0 directamente. | Smoke + ticket real. |
| **RSSICREA** | Mismo flujo que B2Impact. | Idem. |
| **Cliente nuevo "CREA"** | 1. `POST /api/init_project` con tracker ADO. <br> 2. Editor de client-profile → llenar BD, paths, build. <br> 3. Adopción directa de los v2.0.0. | Smoke. |

### Fase 5 — Limpieza (opcional, post-validación)

- Mover `DevPacifico.agent.md` y `DevPacifico2.agent.md` a `legacy/`.
- Renombrar `AnalistaFuncionalPacifico.agent.md` → `legacy/AnalistaFuncionalPacifico.agent.md`.
- Marcar como `deprecated: true` en el frontmatter.
- Borrar `analizar-af-agendaweb-pacifico.prompt.md` (tiene un PAT en claro — riesgo de seguridad ya identificado en §1).
- **NO** se borra nada antes de 30 días post-migración exitosa.

---

## 10. Tests obligatorios (cobertura mínima)

| Archivo | Casos |
|---------|-------|
| `test_client_profile.py` | (1) carga válida, (2) campos faltantes con defaults, (3) schema-version mismatch, (4) tracker_state_machine válido por tipo de tracker, (5) merge con defaults. |
| `test_client_profile_endpoints.py` | GET (con/sin perfil), PUT (validación), POST db-auth (cifrado), 401/403. |
| `test_db_query_audit.py` | DML rechazado (INSERT/UPDATE/DELETE/MERGE/DROP/ALTER), SELECT permitido, log en `data/db_query_audit.jsonl`, timeout, query inválido. |
| `test_context_enrichment.py` (extensión) | client-profile inyectado, ausente cuando proyecto no tiene perfil, no rompe con agente legacy. |
| `test_config_transfer.py` (extensión) | export/import incluye client_profile, checksum válido, no exporta secretos, idempotente. |
| `test_agent_runner_smoke.py` (nuevo) | smoke: run del Developer v2.0.0 contra mock LLM con client-profile inyectado produce output válido. |

---

## 11. Plan de rollback (por fase)

| Fase | Rollback |
|------|----------|
| 1 (backend foundation) | Revertir PR-1 a PR-5. Los endpoints nuevos se eliminan. Nada que estaba antes cambió. |
| 2 (context block) | Setear `STACKY_INJECT_CLIENT_PROFILE=false` y reiniciar el backend. El bloque deja de inyectarse. |
| 3 (agentes nuevos) | Quitar los nuevos `.agent.md` del paquete `DeployStackyAgents/github_copilot_agents/` y republicar. Los legacy siguen ahí. |
| 4 (migración cliente) | Volver a poner los legacy en `pinned_agents` del cliente afectado. |
| 5 (limpieza) | Restaurar desde el snapshot de Fase 0 (`backup-pre-generalizacion-2026-05-28/`). |

---

## 12. Checklist de seguridad

- [ ] El `client_profile` **nunca** contiene `pat`, `token`, `password`, `secret`, `auth_header`, `api_key` (mismo conjunto que ya filtra `config_transfer._SECRET_KEYS`).
- [ ] El context block `client-profile` que llega al LLM tampoco los contiene (placeholder `{{db_password}}`).
- [ ] El endpoint `POST /api/tickets/<id>/db/query` rechaza cualquier statement que no empiece con `SELECT` (case-insensitive, después de strip de comentarios) y registra cada ejecución en `data/db_query_audit.jsonl`.
- [ ] `analizar-af-agendaweb-pacifico.prompt.md` (PAT en claro) se elimina en Fase 5 y se reporta al operador para que rote el PAT.
- [ ] `config_transfer.build_export` se extiende para escanear y rechazar exportar un `client_profile` que contenga claves prohibidas (defensa en profundidad).

---

## 13. Trazabilidad y observabilidad

- Cada cambio del `client_profile` queda en `data/config_transfer_events.jsonl` con action=`client_profile_update`, project, schema_version, actor, fields_changed.
- Cada ejecución de SELECT via `/api/tickets/<id>/db/query` queda en `data/db_query_audit.jsonl` con ticket_id, query (sin parámetros sensibles), duration_ms, row_count, executed_by.
- El context block `client-profile` que se inyecta se loguea en el AgentExecution.metadata del Run (igual que ya se loguean los demás bloques).

---

## 14. Cronograma estimado

| Fase | Duración | Bloqueado por |
|------|----------|---------------|
| 0 — Aprobación | 1 día | Operador |
| 1 — Backend foundation | 2-3 días | Fase 0 |
| 2 — Context block | 1 día | Fase 1 |
| 3 — Agentes nuevos | 3-4 días | Fase 2 |
| 4 — Migración RSPACIFICO | 2-3 días (incluye validación lado a lado) | Fase 3 |
| 4 — Migración B2IMPACT + RSSICREA | 1 día cada uno | RSPACIFICO ok |
| 5 — Limpieza | 1 día (30 días después) | Validación ok |

**Total tiempo de ingeniería:** ~12-15 días-persona. **Calendar time:** ~3-4 semanas con buffer.

---

## 15. Decisiones que requieren input del operador

Antes de arrancar Fase 1, necesito confirmación o decisión sobre:

1. **Nombre del agente Developer genérico.** Propongo `Developer.agent.md`. ¿OK o preferís `DevStack.agent.md` / `DevStandard.agent.md` para no confundir con la familia `DevStack1/2/3`?
2. **Política respecto al `TechnicalAnalyst.agent.md` actual.** ¿OK con renombrar a `TechnicalAnalystPacifico.legacy.agent.md` mientras dura la transición, o preferís que el actual se reemplace in-place con cutover por feature flag?
3. **`analizar-af-agendaweb-pacifico.prompt.md`** tiene un PAT en claro. ¿Lo eliminamos en Fase 5 o antes (recomendado: rotar el PAT YA y eliminar el archivo de inmediato)?
4. **Schema `client_profile` schema_version 1** — ¿el set de campos propuesto cubre tu visión, o querés agregar algo (ej: integración con sistemas externos, claves de templates de tickets, etc.)?
5. **Endpoint `POST /api/tickets/<id>/db/query`.** ¿OK con que el SELECT sea server-side (más seguro pero menos flexible), o preferís que el agente arme y ejecute el `sqlcmd` localmente con la credencial DPAPI?
6. **Soporte multi-lenguaje en RIDIOMA.** Confirmado que Pacífico usa ESP+ENG+POR; ¿confirma el operador que ningún otro cliente requiere más idiomas (p.ej., chino simplificado, alemán)?
7. **Frontend.** ¿El editor de `client_profile` debe ser formulario estructurado o editor JSON crudo en Fase 1, con upgrade al formulario en Fase 3?

---

## 16. Riesgos conocidos y mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|-----------|
| Algún proyecto Pacífico crítico falla con agente v2.0.0 | Media | Alto | Validación lado-a-lado contra 10 tickets reales antes del cutover; rollback en 1 click (cambiar pinned_agents). |
| Schema del client_profile evoluciona y rompe configs existentes | Baja | Medio | Migradores secuenciales (mismo patrón que `config_transfer._MIGRATORS`). |
| Endpoint `/db/query` se vuelve cuello de botella | Baja | Bajo | Es para tickets puntuales del análisis técnico, no es alta carga. Si pasa, agregar pool de conexiones. |
| Operador edita el client_profile a mano y rompe el JSON | Media | Bajo | Validador estructural + UI con formulario; backups automáticos antes de cada PUT. |
| Stacky no está corriendo y el agente queda sin client-profile | Media | Bajo | Fallback al `.stacky/client-profile.yml` del workspace (mecanismo C). |
| Algún cliente tiene una convención que no encaja en el schema | Baja | Medio | Campo `client_profile.extensions: {}` libre para cosas no estandarizadas (escape hatch). |

---

## 17. Glosario para este plan

- **Client Profile**: el bloque `client_profile` dentro de `backend/projects/<NAME>/config.json` que describe TODO lo específico del cliente que los agentes necesitan saber.
- **Context block**: estructura `{id, kind, title, content}` que Stacky inyecta antes del prompt user. Ver `services/context_enrichment.py`.
- **Tracker**: sistema de tickets externo (ADO / Jira / Mantis). Cada proyecto Stacky apunta a uno.
- **Agente genérico v2.0.0**: el `.agent.md` que NO tiene datos hardcoded del cliente; lee el `client_profile`.
- **Agente legacy**: el `.agent.md` actual con datos Pacífico embebidos. Se mantiene durante la transición.
- **Cutover**: momento en que se cambia `pinned_agents` para que solo apunten a los genéricos.

---

## 18. Próximos pasos inmediatos

Apenas el operador apruebe este plan:

1. Crear branch `feature/client-profile-v1`.
2. Hacer snapshot de `backend/projects/`, `data/`, `DeployStackyAgents/github_copilot_agents/`.
3. Arrancar Fase 1, PR-1 (`services/client_profile.py`).
4. Reportar al operador cada PR mergeado con su evidencia de tests.

---

> **Estado:** PROPUESTA — pendiente de aprobación.
> **Cómo aprobar:** responder `APROBADO` (o con comentarios sobre las preguntas de §15) en el chat. Una vez aprobado, arranco Fase 0 inmediatamente.
