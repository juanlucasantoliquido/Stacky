# Plan: agentes autocontenidos dentro de la carpeta `Stacky`

| Campo | Valor |
|---|---|
| Fecha | 2026-05-29 |
| Estado | Implementado (2026-05-30) |
| Alcance | StackyAgent, deploy portable y runtimes que invocan agentes `.agent.md` |
| Objetivo | Que todos los agentes usados por StackyAgent vivan dentro de la carpeta `Stacky` generada desde la ruta de ejecución, y que cada invocación declare explícitamente `@nombre`, ruta y archivo `.agent.md` seleccionado. |

## 1. Contexto y problema

Hoy StackyAgent puede leer agentes desde una ruta externa de prompts de VS Code (`VSCODE_PROMPTS_DIR`) o desde un bundle empaquetado (`github_copilot_agents`). Ese comportamiento es útil en desarrollo, pero en deploy puede dejar agentes fuera del artefacto portable o depender de rutas del usuario operador.

La nueva regla operativa es:

> A partir de ahora, los agentes que utilice StackyAgent deben estar dentro de la carpeta `Stacky` que Stacky genera desde la ruta donde se está ejecutando. Así, cuando se haga un deploy, el paquete ya lleva todos los agentes en la misma carpeta.

Además, cada vez que StackyAgent invoque a cualquier agente debe indicarle de forma explícita:

1. El `@nombre` del agente.
2. La ruta base desde donde debe trabajar.
3. La ruta exacta del archivo `.agent.md` que debe elegir.
4. El nombre del archivo `.agent.md` seleccionado.

## 2. Decisión de arquitectura

### 2.1 Carpeta canónica de agentes

Crear una carpeta canónica dentro del runtime generado por Stacky:

```text
<execution_root>/Stacky/
├── agents/
│   ├── manifest.json
│   ├── Business.agent.md
│   ├── Functional.agent.md
│   ├── Technical.agent.md
│   ├── Developer.agent.md
│   └── QA.agent.md
├── data/
├── projects/
└── logs/
```

Donde:

- `<execution_root>` es la ruta desde donde se ejecuta StackyAgent o el instalador.
- `<execution_root>/Stacky` es el `STACKY_HOME` operativo.
- `<execution_root>/Stacky/agents` es el `STACKY_AGENTS_DIR` canónico.
- `manifest.json` es el índice versionado de agentes disponibles.

### 2.2 Regla de resolución de agentes

La resolución debe seguir esta prioridad:

1. `STACKY_AGENTS_DIR`, si está definido y apunta a una carpeta válida.
2. `<STACKY_HOME>/agents`, si existe.
3. Carpeta bundle del deploy: `<app_root>/github_copilot_agents`, solo como compatibilidad temporal.
4. Ruta legacy `VSCODE_PROMPTS_DIR`, solo para migración/desarrollo y con warning visible.

La meta de cierre es que producción use siempre los puntos 1 o 2 y no dependa de rutas de VS Code del usuario.

### 2.3 Contrato de invocación

Toda invocación de agente debe incluir un bloque normalizado como este en el prompt, log y metadata de ejecución:

```markdown
## Agente Stacky seleccionado

- Mention: @Developer
- Nombre: Developer
- Archivo agent.md: Developer.agent.md
- Ruta agent.md: C:\ruta\de\ejecucion\Stacky\agents\Developer.agent.md
- Carpeta de agentes: C:\ruta\de\ejecucion\Stacky\agents
- Workspace de trabajo: C:\ruta\del\proyecto

Regla: usa el agente `@Developer` y toma como prompt/persona únicamente el archivo
`C:\ruta\de\ejecucion\Stacky\agents\Developer.agent.md`.
```

Para Linux/macOS el mismo contrato aplica con rutas POSIX.

## 3. Cambios funcionales requeridos

### Fase 1 — Definir `STACKY_HOME` y `STACKY_AGENTS_DIR`

1. Agregar helpers en runtime paths:
   - `stacky_home()`: resuelve `<execution_root>/Stacky`.
   - `stacky_agents_dir()`: resuelve `<stacky_home>/agents` o `STACKY_AGENTS_DIR`.
2. Permitir override por variables de entorno:
   - `STACKY_HOME`
   - `STACKY_AGENTS_DIR`
3. Crear la carpeta si no existe al inicializar StackyAgent.
4. Registrar en logs la ruta efectiva:
   - `stacky_home=<...>`
   - `stacky_agents_dir=<...>`

### Fase 2 — Materializar agentes dentro de `Stacky/agents`

1. En arranque o preparación de deploy, copiar los `.agent.md` conocidos hacia `Stacky/agents`.
2. Normalizar nombres de archivo para evitar rutas externas o traversal:
   - aceptar solo `*.agent.md`;
   - usar `Path(filename).name`;
   - rechazar duplicados por nombre normalizado.
3. Generar `Stacky/agents/manifest.json` con:
   - `name`;
   - `mention` (`@Developer`);
   - `filename`;
   - `path` absoluto;
   - `relative_path` desde `STACKY_HOME`;
   - `description`;
   - `checksum_sha256`;
   - `source` (`bundled`, `imported`, `legacy_vscode`, `custom`).
4. Si un agente existe en `Stacky/agents`, esa copia tiene prioridad sobre cualquier copia externa.

### Fase 3 — Actualizar carga/listado de agentes

1. Cambiar el listado de agentes para leer por defecto desde `stacky_agents_dir()`.
2. Mantener `VSCODE_PROMPTS_DIR` como fallback temporal, pero mostrar warning:

   ```text
   WARNING: usando VSCODE_PROMPTS_DIR legacy. Importá estos agentes a Stacky/agents antes de producción.
   ```

3. Agregar endpoint o comando de importación:

   ```text
   Importar agentes externos → Stacky/agents
   ```

4. Mostrar en UI la ruta real del agente seleccionado para que el operador confirme qué `.agent.md` se usará.

### Fase 4 — Enriquecer prompt, logs y metadata de ejecución

Cada ejecución debe persistir:

- `agent_mention`: por ejemplo `@Developer`.
- `agent_name`: por ejemplo `Developer`.
- `agent_filename`: por ejemplo `Developer.agent.md`.
- `agent_path`: ruta absoluta dentro de `Stacky/agents`.
- `agents_dir`: ruta absoluta de `Stacky/agents`.
- `stacky_home`: ruta absoluta de `Stacky`.
- `workspace_root`: ruta del repo/proyecto donde el agente debe trabajar.

El prompt del runtime debe incluir el contrato de invocación antes del contexto del ticket. Esto aplica como mínimo a:

- Codex CLI runtime.
- Claude Code CLI runtime.
- VS Code bridge / Copilot bridge.
- Cualquier runner futuro que use `.agent.md`.

### Fase 5 — Deploy portable

1. Actualizar scripts de publicación para incluir:

   ```text
   Stacky/agents/*.agent.md
   Stacky/agents/manifest.json
   ```

2. Validar el paquete generado:
   - el zip/instalador contiene `Stacky/agents`;
   - no hay dependencia obligatoria de `%APPDATA%/Code/User/prompts`;
   - el primer arranque puede listar agentes sin conexión y sin VS Code abierto.
3. Agregar una verificación pre-release:

   ```text
   check_deploy_agents.py --stacky-home <deploy>/Stacky
   ```

4. Bloquear o advertir publicación si `Stacky/agents` está vacío.

## 4. Formato propuesto de `manifest.json`

```json
{
  "schema_version": 1,
  "generated_at": "2026-05-29T00:00:00Z",
  "stacky_home": "C:/Deploy/Stacky",
  "agents_dir": "C:/Deploy/Stacky/agents",
  "agents": [
    {
      "name": "Developer",
      "mention": "@Developer",
      "filename": "Developer.agent.md",
      "path": "C:/Deploy/Stacky/agents/Developer.agent.md",
      "relative_path": "agents/Developer.agent.md",
      "description": "Implementa cambios técnicos sobre el repo del proyecto.",
      "checksum_sha256": "...",
      "source": "bundled"
    }
  ]
}
```

## 5. Ejemplo de instrucción al invocar un agente

Plantilla que StackyAgent debe inyectar en cada ejecución:

```markdown
StackyAgent invoca al agente @{{agent_name}}.

Debes trabajar desde la ruta:

`{{workspace_root}}`

Debes elegir este archivo de agente como prompt/persona:

`{{agent_path}}`

Archivo seleccionado:

`{{agent_filename}}`

Carpeta canónica de agentes:

`{{agents_dir}}`

No uses otro `.agent.md` aunque exista en rutas externas. Si el archivo no existe,
detén la ejecución y reporta el bloqueo.
```

## 6. Criterios de aceptación

- [x] Al ejecutar StackyAgent desde cualquier carpeta, se crea o usa `<execution_root>/Stacky/agents`. — `runtime_paths.stacky_home()/stacky_agents_dir()` + bootstrap `materialize_agents()` en `app.py`.
- [x] Todos los agentes seleccionables en producción salen de `Stacky/agents`. — `config.VSCODE_PROMPTS_DIR` prioriza el canonical; legacy sólo con `STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE`.
- [x] El deploy contiene los `.agent.md` y `manifest.json` dentro de la carpeta `Stacky`. — `build_release.ps1` materializa `Stacky/agents` + `check_deploy_agents.py`.
- [x] Cada ejecución registra `@nombre`, `agent_filename`, `agent_path`, `agents_dir`, `stacky_home` y `workspace_root`. — `stacky_agents.invocation_metadata()` persistido en `metadata_dict` de ambos runners CLI.
- [x] El prompt enviado al runtime indica explícitamente la ruta y el `.agent.md` a elegir. — `stacky_agents.build_invocation_block()` inyectado en codex_cli, claude_code_cli y open-chat bridge.
- [x] Si falta el archivo `.agent.md` seleccionado, la ejecución falla temprano con un mensaje claro. — `RuntimeError` en los runners cuando `selected_agent`/`agent_entry` es `None`.
- [x] `VSCODE_PROMPTS_DIR` queda documentado como fallback legacy, no como fuente canónica de producción. — docstrings en `config._default_vscode_prompts_dir()` y warnings al usar legacy.

## 7. Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Agentes duplicados entre VS Code y `Stacky/agents` | Se ejecuta una persona incorrecta | Prioridad estricta a `Stacky/agents` y checksum en manifest. |
| Deploy sin agentes | StackyAgent no puede ejecutar prompts personalizados | Check pre-release obligatorio y bloqueo si `Stacky/agents` está vacío. |
| Rutas absolutas cambian entre build y máquina destino | Manifest queda desactualizado | Regenerar `path` absoluto en primer arranque y conservar `relative_path`. |
| Operador edita un `.agent.md` sin trazabilidad | Difícil auditar resultados | Guardar checksum por ejecución y mostrar diferencia contra manifest. |
| Runtime futuro omite el contrato de invocación | Inconsistencia operativa | Crear helper único `build_agent_invocation_block()` reutilizado por todos los runners. |

## 8. Orden recomendado de implementación

1. Crear helpers `stacky_home()` y `stacky_agents_dir()`.
2. Cambiar configuración para que `VSCODE_PROMPTS_DIR` apunte por defecto a `stacky_agents_dir()`.
3. Agregar importación/materialización de agentes a `Stacky/agents`.
4. Generar `manifest.json`.
5. Actualizar prompts de Codex CLI y Claude Code CLI con el bloque de invocación.
6. Persistir metadata extendida en `AgentExecution`.
7. Actualizar UI para mostrar ruta y archivo seleccionados.
8. Actualizar scripts de deploy y validación pre-release.
9. Agregar tests unitarios de resolución, manifest e invocación.
10. Ejecutar prueba E2E con un deploy portable sin depender de VS Code prompts.

## 9. Tests sugeridos

- `test_stacky_agents_dir_default`: valida que el default sea `<execution_root>/Stacky/agents`.
- `test_stacky_agents_dir_env_override`: valida `STACKY_AGENTS_DIR`.
- `test_agent_manifest_contains_paths_and_mentions`: valida `@nombre`, `filename`, `path`, `relative_path` y checksum.
- `test_runner_prompt_includes_agent_invocation_contract`: valida que el prompt incluye `@nombre`, ruta, carpeta y archivo `.agent.md`.
- `test_missing_selected_agent_fails_fast`: valida error temprano si el archivo seleccionado no existe.
- `test_deploy_package_contains_stacky_agents`: valida que el zip/instalador incluya `Stacky/agents`.

## 10. Definición de terminado

La iniciativa se considera terminada cuando se pueda entregar un deploy portable que incluya la carpeta `Stacky/agents`, arrancar StackyAgent en una máquina limpia, seleccionar cualquier agente, y comprobar en logs/prompt/metadata que la invocación declara explícitamente `@nombre`, ruta de trabajo y archivo `.agent.md` elegido dentro de la carpeta `Stacky`.

## 11. Estado de implementación (2026-05-30)

Mapa fase → código entregado:

| Fase | Entregado en |
|---|---|
| 1 — `STACKY_HOME` / `STACKY_AGENTS_DIR` | `backend/runtime_paths.py`: `stacky_home()`, `stacky_agents_dir()`, `ensure_stacky_home()`, `ensure_stacky_agents_dir()` (env overrides incluidos). |
| 2 — Materializar agentes + manifest | `backend/services/stacky_agents.py`: `materialize_agents()`, `write_manifest()`; bootstrap automático en `backend/app.py` con log `stacky_home=… stacky_agents_dir=… materialized=N`. |
| 3 — Carga/listado + import + UI | `config.VSCODE_PROMPTS_DIR` (canonical-first); endpoints `GET /agents/stacky/manifest`, `POST /agents/stacky/materialize`, `POST /agents/stacky/import`; `TeamManageDrawer.tsx` muestra la carpeta fuente efectiva **y la ruta absoluta del `.agent.md` por agente** (desde `manifest.agents[].path`, con fallback a `agentsDir + filename` para overrides por proyecto). |
| 4 — Prompt + logs + metadata | `build_invocation_block()` + `invocation_metadata()` inyectados en `codex_cli_runner.py`, `claude_code_cli_runner.py` y `api/agents.py` (open-chat bridge). |
| 5 — Deploy portable | `deployment/build_release.ps1` materializa `Stacky/agents`, genera `manifest.json` y bloquea release vacío; `deployment/check_deploy_agents.py` valida manifest + checksums pre-release. |

Tests (`backend/tests/`):

- `test_stacky_agents.py` — resolución, materialización, manifest, contrato de invocación, import fail-fast y **validación de deploy** (`test_deploy_package_contains_stacky_agents`, empty-dir y checksum-mismatch).
- `test_config_agent_source.py` — canonical-first, override por proyecto y flag legacy explícito.
- `test_claude_code_cli_prompt.py` — el prompt del runner incluye el bloque "Agente Stacky seleccionado".

Todos en verde (`pytest tests/test_stacky_agents.py tests/test_config_agent_source.py tests/test_claude_code_cli_prompt.py` → 50 passed con dispatch/ADO incluidos). Frontend: `tsc --noEmit` sin errores.
