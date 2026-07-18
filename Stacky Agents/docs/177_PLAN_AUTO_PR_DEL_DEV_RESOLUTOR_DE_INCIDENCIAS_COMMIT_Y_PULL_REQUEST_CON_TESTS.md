# Plan 177 — Auto-PR del Dev Resolutor de Incidencias: checkbox "Abrir PR", commit + Pull Request automáticos con los tests incluidos

**Estado:** IMPLEMENTADO (F0-F6) — 2026-07-18 · construido por `implementar-plan-stacky` sobre la
v2 CRITICADO/APROBADO-CON-CAMBIOS (0 bloqueantes). Commits: F0+F1 `8b272d6c`, F2+F3 `b5f3ebeb`,
F4 `8dd66ab3`, F5 `2bf27bc6`, F6 `dc5a0a50` (sin push).

### Resultado de implementación (2026-07-18)
- **116 tests verdes por archivo/grupo (G5)**: flags 63; ADO commit_file 16 (F1); diff+intent 8 (F2);
  endpoint incident_dev 10 (F3, incl. 4 nuevos); post-hook auto-PR 11 + autopublish 8 (F4); frontend
  modelo puro 4 (F5) + `tsc --noEmit` limpio. Suite incidencias+parity agregada: 53 verdes.
- **CAVEAT del comando agregado de F6:** correr `test_harness_flags.py` JUNTO con los tests que leen
  `config` rompe 2 tests flag-off — causa raíz PREEXISTENTE: `test_harness_flags.py` hace
  `importlib.reload(config)` (`:366-382`), reemplazando el singleton; `api/agents.py` mantiene la
  referencia vieja y lee defaults stale. Afecta IDÉNTICO al `test_run_incident_dev_404_when_flag_off`
  del **Plan 166** (no es regresión del 177). Verificación correcta = por archivo (G5). Ver memoria
  `gotcha-config-reload-harness-flags-contamina`.
- **Smoke E2E NO ejecutado** (mismo criterio de riesgo del Plan 166): abriría un PR real en el
  repo/tracker del operador. Queda para que el operador lo dispare cuando quiera (checkbox premarcado).

## Versión: v1 -> v2 (crítica adversarial aplicada)

Las 5 anclas load-bearing del v1 fueron **verificadas contra el código** (2026-07-18): el bug
`_base_project_url` (F1), la firma del post-hook (`ticket_status.py:231/307/325`), el patrón espejo
`incident_autopublish.py`, `run_incident_dev` (`api/agents.py:1079` — pasa la **PK local** del
`Ticket` real, no un pool sentinel) y `metadata_json`/`metadata_dict` (`models.py:219/260-265`). Las
firmas del proveedor MR también: `commit_file(path, content, branch, message)`,
`create_merge_request(source_branch, target_branch, title, description)`,
`resolve_project_context(project_name=None, *, ticket=None)`. Sobre esa base, el juez corrigió:

**CHANGELOG v1 -> v2:**
- **C1 (IMPORTANTE, resuelto):** F4 anclaba `_default_branch_for` a `devops_production.py:37` — ese
  archivo **NO existe** en `services/`; el real es `api/devops_production.py:37`
  (`_default_branch(provider, project)`, chequea `provider.name == "azure_devops"`). Un modelo menor
  buscaba en `services/` y adivinaba. v2 pinea el archivo correcto, aclara que `mrp` ES el tracker
  provider (tiene `.name`), y fija import lazy + fallback duro `"main"`.
- **C2 (IMPORTANTE, resuelto):** `_comment_issue_safe` apuntaba a `ado_client.py:766/796`
  (ADO-específico → **rompe la paridad GitLab** del comentario). Verificado que existe la ruta
  AGNÓSTICA: `ado_provider.py:92` y `gitlab_provider.py:295` definen la MISMA firma
  `post_comment(item_id, body_html)`. v2 usa `get_tracker_provider(project).post_comment(...)`.
- **C3 (IMPORTANTE, resuelto):** `_project_name_for_ticket` devolvía `ctx.name` — **atributo
  inexistente**. Verificado: `ProjectContext` expone `stacky_project_name` y `workspace_root`, NO
  `.name` (`project_context.py:46-51`). v2 pinea `stacky_project_name`.
- **C4 (IMPORTANTE, resuelto):** el post-hook recibe `ticket_id` = **PK local** del `Ticket`; para
  comentar en el tracker se necesita `ticket.ado_id` y para el proveedor MR el `stacky_project_name`.
  v1 pasaba la PK local a `_comment_issue_safe`/`get_repo_writer`. v2 carga el `Ticket` **una sola
  vez** (`_ticket_ado_id_and_project`) y propaga `(ado_id, project)` por todo el hook.
- **C5 (IMPORTANTE, resuelto vía [ADICIÓN ARQUITECTO]):** el commit REST va contra la default branch
  **remota** del repo del tracker; si `workspace_root` es un repo git real pero su `origin` es OTRO
  repo/proyecto, se commiteaba al repo equivocado (hueco que el guard `cwd_fallback` de F3 NO cubre).
  v2 agrega la **guardia de mapeo working-tree↔tracker** + anotación del `origin` en el PR.
- **C6 (MENOR, resuelto):** la clasificación "NO excepción dura" no contrastaba con el Plan 166 F3
  (auto-publish, que SÍ fue excepción dura). v2 argumenta la asimetría de forma trazable.
- **C7 (MENOR, resuelto):** `_read_text_or_none` reusaba `MAX_FILE_BYTES` (10 MB) como cap de texto
  — enorme para un commit REST. v2 usa `_MAX_TEXT_BYTES = 1_000_000` propio del auto-PR.
- **[ADICIÓN ARQUITECTO]:** guardia de mapeo working-tree↔repo del tracker (`remote_origin_url` +
  `_worktree_maps_to_wrong_repo`), best-effort NO bloqueante salvo mismatch inequívoco, con el
  `origin` anotado en la descripción del PR y el intent para la revisión humana. Cierra C5, agnóstica
  de runtime, cero trabajo del operador, backward-compatible.

**Origen:** directiva explícita del operador (2026-07-18): *"quiero que al momento de resolver una
incidencia haya un checkbox para que haga Pull request y commit automáticamente y que incluya los
tests que se hicieron en la PR"*. Decisiones tomadas por el operador en el intake:
1. **Mecánica del PR:** vía **API del tracker con el PAT ya configurado** (reusa el proveedor MR
   existente ADO/GitLab); **sin** `git push` local (no cablear credenciales de push nuevas).
2. **Entrega:** este plan → juez → implementación (flujo de la casa).
3. **Checkbox premarcado (ON por defecto):** resolver una incidencia abre un PR salvo que el
   operador desmarque el checkbox en ese momento.

> Este documento está redactado para que un **MODELO MENOR** (Haiku, Codex CLI o GitHub Copilot
> Pro) lo implemente **SIN inferir nada**. Nombres de símbolos, rutas, literales de mensajes y
> comandos son **LITERALES**. Cada afirmación sobre código existente está anclada a `archivo:línea`
> **verificada** (2026-07-18). Los comandos con `&&` se ejecutan en **Git Bash** (en PowerShell 5.1
> `&&` es error de parser).

**Dependencias (duras):** Plan 166 F4/F5 — el **Dev Resolutor de Incidencias** (`incident_dev`):
`agents/incident_dev.py`, `services/incident_dev_context.py`, endpoint `run-incident-dev`
(`api/agents.py:1079`), botón "🔧 Resolver con agente" (`frontend/src/pages/TicketBoard.tsx:536`),
flag `STACKY_INCIDENT_DEV_RESOLVER_ENABLED`. **Reusa:** el proveedor MR tracker-agnóstico
(`services/merge_request_provider.py`, `services/repo_writer.py`, `services/ado_provider.py`,
`services/gitlab_provider.py`), el post-hook agnóstico de runtime
(`services/ticket_status.py::register_post_hook` `:307`, `on_execution_end` `:231`) y su precedente
`services/incident_autopublish.py`, la resolución de contexto de proyecto
(`services/project_context.py::resolve_project_context` `:116`), el arnés de git no-interactivo
(`services/pre_run_git.py`), el patrón de store en disco de `services/incident_store.py`, y el
patrón triple de flags.

**Ortogonal a:** Plan 166 (no toca su contrato "el agente NUNCA publica ni transiciona"; esto es un
paso **posterior** al run, del backend, no del agente). Plan 159 (catálogo de modelos — el board no
pasa selector de modelo, igual que hoy). Plan 153/154 (publicación ADO de tickets — otro camino).

---

## 1. Objetivo + KPI

Hoy el ciclo se corta justo antes de lo más valioso. El Dev Resolutor (Plan 166 F4/F5) toma una
Issue, **arregla el código y escribe tests en el working tree del proyecto activo**, y cierra con un
comentario `🚀` — pero **NO commitea nada ni abre un PR** (contrato deliberado del Plan 166:
`incident_dev_context.py`, "NUNCA publica"). El operador tiene que ir al repo, mirar qué cambió,
armar la rama, commitear y abrir el PR a mano. Este plan cierra ese último eslabón, **opt-out por
resolución** (checkbox premarcado), reusando el proveedor MR existente sobre el PAT ya configurado
— sin superficie de credencial nueva.

**KPI / impacto esperado:**
- **K1 — Un click, PR listo:** al lanzar "🔧 Resolver con agente" con el checkbox **"Abrir PR"**
  marcado (default), cuando el agente termina el backend abre **automáticamente** un Pull Request en
  el tracker del proyecto con **exactamente** los archivos que el agente tocó (código **+ tests**),
  y comenta el link del PR en la Issue. Medible: `test_incident_dev_autocommit.py` (con provider
  mockeado, un run `incident_dev` `completed` con diff no vacío → `create_merge_request` llamado una
  vez y el `web_url` queda registrado).
- **K2 — Los tests SIEMPRE viajan en el PR:** los archivos de test que el agente creó/modificó se
  commitean junto al fix y se listan explícitamente en una sección **"Tests incluidos"** de la
  descripción del PR. Medible: `test_incident_dev_diff.py` (`classify_changed_files` separa
  código/tests) + `test_incident_dev_autocommit.py` (la descripción del PR contiene la sección y los
  nombres de los tests).
- **K3 — Cero PRs basura / cero falsos verdes:** si el agente cerró con `⚠️ BLOQUEADO` (sin tocar
  código) o el diff es vacío, **no** se abre ningún PR ni rama. Si el commit/PR falla, el error
  **no queda mudo** (comentario en la Issue + log + `status="error"` en el intent store), regla del
  Plan 135. Medible: `test_incident_dev_autocommit.py` (casos diff-vacío → no-op; excepción del
  provider → error registrado, no PR fantasma).
- **K4 — Paridad de runtimes y kill-switch:** funciona igual en Codex CLI, Claude Code CLI y GitHub
  Copilot Pro (el auto-PR vive en el post-hook agnóstico de runtime, no en un runner). Con
  `STACKY_INCIDENT_DEV_PR_ENABLED=OFF` el checkbox no aparece y el comportamiento es **byte-idéntico**
  al de hoy. Medible: `test_harness_flags*.py` verdes + los casos `*_flag_off`.

---

## 2. Por qué ahora / gap que cierra

El Plan 166 entregó el **Dev Resolutor** hasta el comentario `🚀` con evidencia. Falta el paso que
convierte esa resolución en **trabajo revisable y mergeable**: un PR. Sin él, el operador repite a
mano lo que el agente ya hizo (ubicar los cambios, ramear, commitear, abrir PR), lo que es
exactamente el "trabajo extra al operador" que Stacky busca eliminar. Todo el plumbing necesario ya
existe y está probado — sólo falta el **orquestador** que (a) enumere qué tocó el agente y (b) lo
empuje al proveedor MR. Este plan lo agrega respetando los 3 runtimes y sin degradar nada con los
flags nuevos en OFF.

---

## 3. Principios y guardarraíles (no negociables)

- **3 runtimes con paridad:** el auto-PR corre en `ticket_status.on_execution_end` (`:231`), que se
  dispara desde las 3 rutas de completitud (CLI runners + `manifest_watcher` para
  github_copilot). Un solo módulo cubre los 3 — por eso vive en el post-hook, no en un runner
  (idéntica razón que `incident_autopublish.py`).
- **Cero trabajo extra al operador:** el checkbox viene **premarcado** (directiva del operador); un
  click resuelve **y** abre PR. Apagable por UI (flag `STACKY_INCIDENT_DEV_PR_ENABLED`) y
  desmarcable por resolución.
- **Human-in-the-loop intacto (NO es excepción dura — argumentado, C6):** el PR es una **propuesta**
  que el operador revisa y mergea; el auto-PR **NO** mergea, **NO** cierra ni transiciona la Issue,
  **NO** aprueba. Abrir un PR **≠** bypasear la revisión humana: el PR **ES** el artefacto de
  revisión, y el merge (la única acción que impacta) queda 100% humano. **Contraste explícito con el
  Plan 166 F3** (auto-publish), que SÍ se clasificó **EXCEPCIÓN DURA #1**: aquel crea el artefacto de
  tracker (la Issue) **sin gate por-ítem**, publicando sin revisión previa; éste abre una propuesta
  **revisable** gated por un checkbox **por-run, visible y consentido** ("Abrir PR", premarcado por
  directiva del operador 2026-07-18), y sin merge. Por eso 177 **no** dispara ninguna de las 4
  excepciones duras, aunque el mecanismo (post-hook del backend) sea el mismo que el de 166 F3. El
  contrato del Plan 166 "el agente NUNCA publica ni transiciona" se mantiene: quien abre el PR es el
  **backend post-run** (no el agente), sólo con el consentimiento explícito del checkbox, y sin tocar
  el estado de la Issue.
- **Mono-operador sin auth real:** nada de RBAC/multiusuario.
- **Sin superficie de credencial nueva:** commit + PR van por el **proveedor MR** sobre el **PAT del
  proyecto** ya configurado (`ado_client._resolve_auth_header`), **sin** `git push` local. No se
  cablean credenciales de push al remoto.
- **No degradar** performance/seguridad/estabilidad/DX. Backward-compatible: con los flags nuevos
  OFF el comportamiento es **byte-idéntico** al de hoy.

### Gotchas del repo que el implementador DEBE respetar (verificadas 2026-07-18)

- **G1 — `config.config` vs módulo `config`:** en `api/tickets.py`/`api/incidents.py` la instancia
  de flags es `config.config`; en `api/agents.py` se usa `config.STACKY_...` (ver `run_incident_dev`
  `:1086`: `config.STACKY_INCIDENT_DEV_RESOLVER_ENABLED`). En un **servicio** nuevo se lee
  `from config import config as _cfg; _cfg.STACKY_...`. **Copiá el patrón del archivo que editás.**
- **G2 — Ratchet de tests:** todo `test_*.py` nuevo DEBE ir en `HARNESS_TEST_FILES` en **ambos**
  `backend/scripts/run_harness_tests.sh` y `.ps1`, o un meta-test se pone rojo.
- **G3 — Aristas `requires=`:** cada flag con `requires=` DEBE tener su arista en el mapa congelado
  de `backend/tests/test_harness_flags_requires.py` (`:206-207`).
- **G4 — `_CURATED_DEFAULTS_ON`:** cada flag `default=True` DEBE estar en el set de
  `backend/tests/test_harness_flags.py` (`:673-674`).
- **G5 — venv y tests por archivo:** correr con `Stacky Agents/backend/.venv`, **por archivo**
  (contaminación cross-run conocida). Frontend: vitest **por archivo**.
- **G6 — Ratchet UI cero inline-style:** los `.tsx` nuevos/editados no agregan `style={{}}`; clases
  del `.module.css`. (Ojo: `TicketBoard.tsx` YA tiene `style={{}}` preexistentes en banners
  `:405-409` — **no** agregar más; el checkbox usa clase.)
- **G7 — `_CATEGORY_KEYS` obligatorio:** toda flag nueva va también al dict `_CATEGORY_KEYS` de
  `services/harness_flags.py`, en la MISMA tupla que contiene `STACKY_INCIDENT_DEV_RESOLVER_ENABLED`
  (`:318`), o `test_every_registry_flag_is_categorized` rompe CI a propósito.
- **G8 — post-hook sin app context:** el post-hook corre en el thread del runner/watcher **sin**
  request/app context. PROHIBIDO `jsonify`/`request` dentro del servicio del post-hook; sólo dicts,
  llamadas a services y logging. (Precedente: `incident_autopublish.py`.)
- **G9 — no clobber de `metadata_json`:** el runner escribe `AgentExecution.metadata_json`
  (`claude_code_cli_runner.py:1450` stampea `workspace_root`, `:1472` `cwd_fallback`). Por eso el
  intent del PR **NO** se guarda en `metadata_json` (habría carrera de escritura): se guarda en un
  **store en disco keyeado por `execution_id`** (F2), read/write sólo del post-hook y del endpoint.

---

## 4. Fases

Orden por dependencia: **F0 → F1 → F2 → F3 → F4 → F5 → F6**.

---

### F0 — Flag del arnés (patrón triple, 5 ediciones) + `dev_pr_enabled` en el status

**Objetivo (1 frase):** registrar el flag `STACKY_INCIDENT_DEV_PR_ENABLED` (bool, default **ON**,
`requires=STACKY_INCIDENT_DEV_RESOLVER_ENABLED`) con el patrón triple y exponerlo en
`incidents_status` para que el board muestre/oculte el checkbox.

**Archivos a editar:**
- `Stacky Agents/backend/config.py`
- `Stacky Agents/backend/services/harness_flags.py` (`_CATEGORY_KEYS` + `FlagSpec`)
- `Stacky Agents/backend/tests/test_harness_flags.py` (set `_CURATED_DEFAULTS_ON`)
- `Stacky Agents/backend/tests/test_harness_flags_requires.py` (mapa `requires` congelado)
- `Stacky Agents/backend/api/incidents.py` (`incidents_status` `:13` expone `dev_pr_enabled`)

**1) `config.py`** — insertar **inmediatamente después** del bloque de
`STACKY_INCIDENT_DEV_RESOLVER_ENABLED` (`:982-984`, verificado):

```python
    # Plan 177 — Auto-PR del Dev Resolutor de Incidencias. Default ON: sólo
    # dispara el commit+PR cuando el operador dejó el checkbox "Abrir PR"
    # marcado en la resolución (opt-out por-run). Kill-switch por UI: OFF oculta
    # el checkbox y no abre ningún PR (byte-idéntico a hoy).
    STACKY_INCIDENT_DEV_PR_ENABLED: bool = os.getenv(
        "STACKY_INCIDENT_DEV_PR_ENABLED", "true"
    ).lower() in ("1", "true", "yes")
```

**2) `harness_flags.py` — `_CATEGORY_KEYS`** (G7): en la MISMA tupla que ya contiene
`"STACKY_INCIDENT_DEV_RESOLVER_ENABLED"` (`:318`), agregar inmediatamente después:

```python
        "STACKY_INCIDENT_DEV_PR_ENABLED",          # Plan 177 — auto-PR del Dev Resolutor
```

**3) `harness_flags.py` — `FlagSpec`**: insertar **después** del `FlagSpec` de
`STACKY_INCIDENT_DEV_RESOLVER_ENABLED` (que cierra en `:3366`), antes del cierre de `FLAG_REGISTRY`
(`:3367`). `group="global"` (espejo del flag hermano); `requires` apunta al DEV_RESOLVER que NO
tiene `requires` propio (root) → arista **depth-1**, válida bajo `validate_requires_graph` (R4):

```python
    FlagSpec(
        key="STACKY_INCIDENT_DEV_PR_ENABLED",
        type="bool", default=True,
        label="Abrir PR al resolver incidencias",
        description="Tras resolver una Issue con el agente dev, abre automáticamente un Pull Request con el fix y los tests (podés desmarcar el checkbox al resolver). Requiere el Agente Dev Resolutor.",
        group="global", requires="STACKY_INCIDENT_DEV_RESOLVER_ENABLED",
    ),
```

**4) `tests/test_harness_flags.py` — `_CURATED_DEFAULTS_ON`** (`:673`, G4): agregar la clave (es
`default=True`):

```python
    "STACKY_INCIDENT_DEV_PR_ENABLED",
```

**5) `tests/test_harness_flags_requires.py` — mapa congelado** (`:206`, G3): agregar la arista:

```python
    "STACKY_INCIDENT_DEV_PR_ENABLED": "STACKY_INCIDENT_DEV_RESOLVER_ENABLED",  # Plan 177
```

**6) `api/incidents.py::incidents_status`** (`:13-28`, verificado): agregar el campo al dict que ya
devuelve `dev_resolver_enabled` (`:27`), mismo patrón `bool(getattr(_cfg, ..., False))`:

```python
        # Plan 177 — el board usa este campo para mostrar/ocultar el checkbox
        # "Abrir PR" junto al botón "Resolver con agente".
        "dev_pr_enabled": bool(getattr(_cfg, "STACKY_INCIDENT_DEV_PR_ENABLED", False)),
```

**NOTA (G2):** NO se agrega archivo de test nuevo en F0 → **no** se toca `HARNESS_TEST_FILES`. Los
meta-tests (`test_harness_flags.py`, `test_harness_flags_requires.py`) ya están registrados.

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_harness_flags.py tests/test_harness_flags_requires.py -q
```

**Criterio BINARIO:** ambos verdes (incluye `test_every_registry_flag_is_categorized`,
`test_default_known_only_for_curated`, `test_requires_map_is_frozen`). `GET /api/harness/flags`
devuelve el key nuevo. `GET /api/incidents/status` devuelve `dev_pr_enabled`.

**Impacto por runtime:** ninguno (definiciones). **Trabajo del operador:** ninguno.

---

### F1 — Fix del bug latente `ado_provider.commit_file` (`_base_project_url` → `_base_proj`)

**Objetivo (1 frase):** corregir el atributo inexistente que hace que `commit_file` de ADO lance
`AttributeError` **después** de que el push ya aterminó, disfrazándolo de `ado_push_failed`.

**Por qué es prerrequisito DURO:** el auto-PR de F4 usa `writer.commit_file(...)`. En ADO
(`AdoTrackerProvider.commit_file`, `ado_provider.py:146`), las URLs de trabajo usan
`client._base_proj` (verificado: `ado_client.py` define **sólo** `_base_proj`, 18 usos desde `:257`;
`_base_project_url` **no existe**). Pero al armar el `web_url` de retorno se usa
`client._base_project_url` en **dos** lugares (`ado_provider.py:213` rama `unchanged`, `:248` rama
push OK). En el cliente real eso lanza `AttributeError` tras el push exitoso; el `except` de `:256`
lo re-lanza como `TrackerApiError(kind="ado_push_failed")` → el flujo cree que falló **aunque el
commit landeó**. Los tests actuales no lo detectan porque `test_plan95_ado_parity.py` monkeypatchea
`_base_project_url` en el mock.

**Archivos a editar:**
- `Stacky Agents/backend/services/ado_provider.py` (2 ocurrencias: `:213`, `:248`)

**Cambio EXACTO:** reemplazar en ambas líneas `client._base_project_url` por `client._base_proj`.
El resultado sigue el mismo formato de link web ya usado por el resto del cliente:

```python
                        web_url = f"{client._base_proj}/_git/{repo_id}?path=/{path.lstrip('/')}&version=GB{branch}"
```
```python
            web_url = f"{client._base_proj}/_git/{repo_id}?path=/{path.lstrip('/')}&version=GB{branch}"
```

**Tests (TDD):** archivo nuevo `backend/tests/test_plan177_ado_commit_web_url.py`. Casos con un
`AdoClient` **fake mínimo** que define `_base_proj` (y **NO** `_base_project_url`) y un `_request`
mockeado que simula: (a) branch inexistente → crea ref; (b) item 404 → `add`; (c) push OK con
`commitId`. Espejar el arnés de `test_plan95_ado_parity.py` **pero sin** monkeypatchear
`_base_project_url` (esa es justamente la trampa):
1. `test_commit_file_add_returns_web_url_without_attribute_error`: `commit_file(...)` devuelve
   `status="create"` y `web_url` contiene `/_git/` y `version=GB<branch>` — **sin** `AttributeError`
   ni `ado_push_failed`.
2. `test_commit_file_unchanged_uses_base_proj`: item existe con contenido idéntico → `status="unchanged"`
   y `web_url` construido con `_base_proj` (no crashea).
Registrar en `HARNESS_TEST_FILES` (G2, ambos scripts).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_plan177_ado_commit_web_url.py tests/test_plan95_ado_parity.py -q
```

**Criterio BINARIO:** 2 casos nuevos verdes + `test_plan95_ado_parity.py` sigue verde. Si la parity
de ADO monkeypatcheaba `_base_project_url`, quitá ese monkeypatch (ya no hace falta) o dejalo
inocuo; el punto es que el cliente real ya no depende del atributo inexistente.

**Impacto por runtime:** ninguno (sólo el proveedor ADO). **Fallback:** N/A. **Trabajo del
operador:** ninguno.

---

### F2 — Servicio de diff del working tree + intent store en disco

**Objetivo (1 frase):** un servicio que (a) snapshotea el estado del repo del proyecto **antes** del
run y computa el **delta** que dejó el agente **después**, y (b) persiste el "intent" del PR
(`open_pr` + baseline + repo_root) keyeado por `execution_id`, sin tocar `metadata_json` (G9).

**Valor:** aísla EXACTAMENTE los archivos que ESTE run tocó (no barre cambios preexistentes del
operador) y lleva el consentimiento del checkbox del endpoint (F3) al post-hook (F4) sin carrera.

**Archivos a crear:**
- CREAR `Stacky Agents/backend/services/incident_dev_pr.py`

**Símbolos EXACTOS (nuevos en `incident_dev_pr.py`):**

```python
def resolve_repo_root(workspace_root: str | None) -> str | None
    # `git -C <workspace_root> rev-parse --show-toplevel` (workspace_root puede
    # ser SUBDIR del repo). Devuelve la ruta absoluta del repo o None si no es
    # un repo git / workspace_root vacío. Reusa el patrón _run_git de
    # pre_run_git.py:248 (credential.helper= vacío, GIT_TERMINAL_PROMPT=0,
    # CREATE_NO_WINDOW en Windows, timeout).

def remote_origin_url(repo_root: str) -> str | None
    # `git -C <repo_root> remote get-url origin` → URL del remoto 'origin' o None
    # (rc!=0 / sin origin / repo_root vacío). Reusa el mismo patrón _run_git
    # (credential.helper= vacío, GIT_TERMINAL_PROMPT=0, CREATE_NO_WINDOW en Windows,
    # timeout). [ADICIÓN ARQUITECTO] — insumo de la guardia de mapeo working-tree ↔
    # repo del tracker (F4) y de la anotación del origin en el PR.

def snapshot_worktree(repo_root: str) -> dict
    # {"head": <sha o "">, "entries": {rel_posix_path: sha1_hex_del_contenido}}
    # para TODOS los archivos dirty+untracked. Método:
    #   `git -C <repo> status --porcelain -z -uall`  → parsear XY + path (-z: NUL-separated).
    #   Para cada path NO borrado, sha1 del contenido del working tree (bytes).
    #   Los borrados (' D'/'D ') se registran como entries[path] = "__deleted__".
    # sha1 sólo para detectar cambios; NO es criptográfico.

def compute_changed_files(baseline: dict, current: dict) -> dict
    # Devuelve {"added_or_modified": [rel_posix,...], "deleted": [rel_posix,...]}
    # Regla (delta por HASH, no por presencia — C: evita barrer dirty preexistente):
    #   - path en current con sha != baseline.get(path)  → added_or_modified
    #     (incluye untracked nuevos: baseline no lo tiene; y dirty-preexistente
    #      que el agente RE-editó: el sha cambió).
    #   - path en baseline no-borrado y en current == "__deleted__"  → deleted.
    #   - path dirty en baseline con MISMO sha en current  → EXCLUIDO (era del
    #     operador, el agente no lo tocó).
    # Orden estable (sorted) para reproducibilidad de tests.

def classify_changed_files(paths: list[str]) -> dict
    # {"code": [...], "tests": [...]}. _is_test_path(p): lower(); True si el
    # basename matchea `test_*.py`/`*_test.py` o el path contiene `.test.`/`.spec.`
    # o un segmento `/tests/`,`/__tests__/`,`/test/`. Cierra K2.

# ── Intent store en disco (espejo de incident_store; keyeado por execution_id) ──
def _intent_path(execution_id: int) -> Path
    # runtime_paths.data_dir()/"incident_dev_pr"/f"{execution_id}.json" (mkdir parents).

def record_intent(execution_id: int, intent: dict) -> None
    # Escribe atómico (tmp+replace) el dict: {open_pr, repo_root, baseline, created_at}.

def get_intent(execution_id: int) -> dict | None
    # Lee el json o None.

def mark_intent(execution_id: int, **fields) -> None
    # Merge idempotente de campos de resultado: pr_id, pr_url, branch, status
    # ("opened"|"blocked_empty"|"error"|"skipped"), error, files_committed.
```

**Notas de implementación (literales):**
- `-z -uall` en `status --porcelain`: `-uall` lista archivos individuales de directorios untracked
  (no colapsa a carpeta); `-z` evita problemas de quoting/espacios en paths (separador NUL).
- Binarios: en F4, al leer el contenido para commitear, si los bytes no decodifican UTF-8 el archivo
  se **omite** con warning (el proveedor MR sólo maneja texto — `contentType rawtext`). En F2
  `snapshot_worktree` igual los hashea (para el delta); la exclusión binaria es del **lector** de F4.
- Deletes: `compute_changed_files` los reporta, pero F4 **no** los expresa en el PR (limitación REST,
  ver Riesgos) — se listan como advertencia en la descripción del PR.

**Tests (TDD):** archivo nuevo `backend/tests/test_incident_dev_diff.py`. Casos (usan un repo git
temporal real con `git init` + `git config user.email/name`, patrón de otros tests de git del repo):
1. `test_snapshot_and_delta_detects_new_untracked_file`: baseline snapshot; crear `a.py`; snapshot
   nuevo; `compute_changed_files` → `a.py` en `added_or_modified`.
2. `test_delta_ignores_preexisting_dirty_file_untouched`: `b.py` ya dirty en baseline; el agente NO
   lo toca; delta → `b.py` **no** aparece.
3. `test_delta_includes_preexisting_dirty_file_reedited`: `c.py` dirty en baseline; se re-edita
   (cambia el sha); delta → `c.py` en `added_or_modified`.
4. `test_delta_reports_deleted_file`: `d.py` trackeado; se borra; delta → `d.py` en `deleted`.
5. `test_classify_splits_tests_from_code`: `["src/x.py","backend/tests/test_x.py","web/x.test.ts"]`
   → `code=["src/x.py"]`, `tests` contiene los otros dos.
6. `test_resolve_repo_root_returns_toplevel_for_subdir`: workspace_root = subdir del repo → devuelve
   el toplevel; workspace_root vacío/no-git → None.
7. `test_intent_store_roundtrip_and_mark_idempotent`: `record_intent` + `get_intent` roundtrip;
   `mark_intent(pr_url=...)` dos veces no rompe y persiste el último merge.
8. `test_remote_origin_url_reads_origin` ([ADICIÓN ARQUITECTO]): repo git temporal con
   `git remote add origin https://example.test/org/repo.git` → `remote_origin_url` devuelve esa URL;
   repo sin `origin` → None; `repo_root` vacío/no-git → None.
Registrar en `HARNESS_TEST_FILES` (G2).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_incident_dev_diff.py -q
```

**Criterio BINARIO:** 8 casos verdes.

**Impacto por runtime:** ninguno (todo local, read-only del working tree). **Trabajo del operador:**
ninguno.

---

### F3 — `run_incident_dev`: leer `open_pr`, capturar baseline, registrar el intent

**Objetivo (1 frase):** en el endpoint que lanza el Dev Resolutor, si el flag está ON y el operador
dejó `open_pr` marcado, capturar el snapshot **baseline** del repo **antes** de lanzar el agente y
registrar el intent keyeado por el `execution_id` devuelto.

**Archivos a editar:**
- `Stacky Agents/backend/api/agents.py` (`run_incident_dev` `:1079`)

**Wiring EXACTO** (dentro de `run_incident_dev`, patrón `config.STACKY_...` de este archivo — G1):

1. Leer el consentimiento del payload (junto a `runtime_raw`/`project_name` `:1117-1118`):
```python
    # Plan 177 — consentimiento del checkbox "Abrir PR" (default premarcado en la
    # UI; el backend igual respeta lo que llegue). Sólo aplica si el flag está ON.
    open_pr = bool(payload.get("open_pr")) and bool(
        getattr(config, "STACKY_INCIDENT_DEV_PR_ENABLED", False)
    )
```

2. **Antes** de `agent_runner.run_agent(...)` (`:1152`), capturar el baseline (best-effort; nunca
   500). Resolver el `workspace_root` del proyecto vía `resolve_project_context`:
```python
    _pr_baseline = None
    _pr_repo_root = None
    if open_pr:
        try:
            from services import incident_dev_pr, project_context
            _ctx = project_context.resolve_project_context(project_name)
            _ws = _ctx.workspace_root if _ctx else None
            _pr_repo_root = incident_dev_pr.resolve_repo_root(_ws)
            if _pr_repo_root:
                _pr_baseline = incident_dev_pr.snapshot_worktree(_pr_repo_root)
        except Exception:  # noqa: BLE001 — el auto-PR es best-effort, nunca bloquea el run
            logger.info("run_incident_dev: no se pudo snapshotear baseline para auto-PR", exc_info=True)
            _pr_repo_root = None
            _pr_baseline = None
```

3. **Después** de obtener `execution_id` con éxito (`:1164`, tras el `try` de `run_agent`),
   registrar el intent (sólo si hubo baseline y repo):
```python
    if open_pr and _pr_repo_root and _pr_baseline is not None:
        try:
            from services import incident_dev_pr
            incident_dev_pr.record_intent(execution_id, {
                "open_pr": True,
                "repo_root": _pr_repo_root,
                "baseline": _pr_baseline,
            })
        except Exception:  # noqa: BLE001 — best-effort; sin intent, el post-hook simplemente no abre PR
            logger.info("run_incident_dev: no se pudo registrar intent de auto-PR exec=%s", execution_id, exc_info=True)
```

**Notas:**
- **Guard `cwd_fallback` (implícito):** `resolve_repo_root` devuelve None si `workspace_root` está
  vacío o no es un repo git → NO se registra intent → el post-hook nunca commiteará en el repo de
  Stacky. (El runner usa el dir de Stacky como fallback con `cwd_fallback=True` cuando
  `workspace_root` falta — `claude_code_cli_runner.py:2735-2762`; acá lo cortamos de raíz al exigir
  un repo git real del proyecto.)
- **Carrera (mínima, documentada):** el baseline se toma **antes** de `run_agent`; el intent se
  escribe **inmediatamente después** de que `run_agent` devuelve `execution_id`. La ventana entre
  ambos es de microsegundos de Python — el agente no puede completar un fix real en ese lapso. Ver
  Riesgos R6.
- **`open_pr` ausente:** si el frontend viejo no manda `open_pr`, `payload.get("open_pr")` es
  `None` → `open_pr=False` → comportamiento de hoy. Backward-compatible.

**Tests (TDD):** ampliar `backend/tests/test_incident_dev_agent.py` (existe, Plan 166 F4) — es donde
vive el arnés de `run-incident-dev`. Casos nuevos (mockear `agent_runner.run_agent` para devolver un
`execution_id` fijo, y `incident_dev_pr.snapshot_worktree`/`resolve_repo_root` para no requerir git
real):
1. `test_run_incident_dev_records_intent_when_open_pr_and_flag_on`: payload `open_pr=True`, flag ON,
   `resolve_repo_root` → un path, `snapshot_worktree` → un dict → `record_intent` llamado una vez con
   `execution_id`.
2. `test_run_incident_dev_no_intent_when_open_pr_false`: `open_pr` ausente/False → `record_intent`
   **no** se llama.
3. `test_run_incident_dev_no_intent_when_pr_flag_off`: `STACKY_INCIDENT_DEV_PR_ENABLED=False` +
   `open_pr=True` → **no** se registra intent (el flag manda).
4. `test_run_incident_dev_no_intent_when_not_a_git_repo`: `resolve_repo_root` → None → no intent.
(Registro en `HARNESS_TEST_FILES` ya existe para `test_incident_dev_agent.py`, Plan 166.)

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_incident_dev_agent.py -q
```

**Criterio BINARIO:** casos nuevos verdes + los 6 casos del Plan 166 F4 siguen verdes.

**Impacto por runtime:** el snapshot es agnóstico (mismo endpoint para los 3 runtimes).
**Fallback:** flag OFF o `open_pr` false → sin intent → sin PR. **Trabajo del operador:** ninguno.

---

### F4 — Post-hook `incident_dev_autocommit`: commit + Pull Request con los tests

**Objetivo (1 frase):** al terminar un run `incident_dev` con `completed`, si hay un intent con
`open_pr`, enumerar el delta, commitear los archivos (código + tests) a una rama nueva vía el
proveedor MR y abrir el PR, comentando el link en la Issue — idempotente y sin errores mudos.

**Valor:** cierra K1/K2/K3/K4. Es el corazón del plan.

**Archivos a crear/editar:**
- CREAR `Stacky Agents/backend/services/incident_dev_autocommit.py`
- EDITAR `Stacky Agents/backend/app.py` (registrar el post-hook, junto a `incident_autopublish`)

**`incident_dev_autocommit.py` (contrato, sin `jsonify`/`request` — G8):**

```python
"""Plan 177 — Auto-PR del Dev Resolutor de Incidencias. Post-hook agnóstico de
runtime: al terminar un run incident_dev 'completed' con intent open_pr, commitea
el delta del working tree (código + tests) a una rama y abre el PR vía el proveedor
MR (PAT del proyecto; sin git push local). NUNCA mergea/cierra/transiciona la Issue."""
import logging
logger = logging.getLogger("stacky.services.incident_dev_autocommit")

_BRANCH_PREFIX = "stacky/incidencia-"          # + {ticket_id}-exec-{execution_id}
_MAX_FILES = 60                                 # cap de archivos por PR (ver Riesgos)
_MAX_TEXT_BYTES = 1_000_000                     # C7 — cap de texto por archivo del auto-PR
                                                # (NO el de 10 MB del intake); binarios/enormes se omiten

def maybe_open_pr_for_incident_dev(*, ticket_id, execution_id, final_status, agent_type, error=None, **_):
    from config import config as _cfg
    if not getattr(_cfg, "STACKY_INCIDENT_DEV_PR_ENABLED", False):
        return
    if agent_type != "incident_dev" or final_status != "completed":
        return
    from services import incident_dev_pr
    intent = incident_dev_pr.get_intent(execution_id)
    if not intent or not intent.get("open_pr"):
        return
    if intent.get("status") in ("opened", "blocked_empty", "error", "skipped"):
        return  # idempotente: ya se procesó este execution_id

    # C4 — el post-hook recibe la PK LOCAL del Ticket (verificado api/agents.py:1096-1101
    # + run_agent(ticket_id=...)). Para comentar en el tracker hace falta ado_id; para
    # el proveedor MR, el stacky_project_name. Se cargan UNA sola vez.
    ado_id, project = _ticket_ado_id_and_project(ticket_id)   # (int|None, str|None)

    repo_root = intent.get("repo_root")
    baseline = intent.get("baseline") or {}
    try:
        current = incident_dev_pr.snapshot_worktree(repo_root)
        delta = incident_dev_pr.compute_changed_files(baseline, current)
        changed = delta.get("added_or_modified") or []
        deleted = delta.get("deleted") or []
        if not changed:
            # ⚠️ BLOQUEADO o diff vacío → NO se abre PR (K3).
            incident_dev_pr.mark_intent(execution_id, status="blocked_empty")
            _comment_issue_safe(ado_id, project, "🔧 El Dev Resolutor no dejó cambios de código, así que no se abrió ningún PR.")
            return
        if len(changed) > _MAX_FILES:
            incident_dev_pr.mark_intent(execution_id, status="skipped",
                                        error=f"demasiados archivos ({len(changed)} > {_MAX_FILES})")
            _comment_issue_safe(ado_id, project, f"🔧 El fix tocó {len(changed)} archivos (> {_MAX_FILES}); no se abrió PR automático. Revisá el working tree.")
            return

        # [ADICIÓN ARQUITECTO] Guardia de mapeo working-tree ↔ repo del tracker (C5).
        # Evita commitear el delta al repo EQUIVOCADO cuando workspace_root es un repo
        # git real pero su 'origin' apunta a OTRO repo/proyecto (hueco que el guard
        # cwd_fallback de F3 NO cubre). Best-effort NO bloqueante salvo mismatch
        # inequívoco. Siempre anota el origin para la revisión humana.
        origin = incident_dev_pr.remote_origin_url(repo_root)
        if _worktree_maps_to_wrong_repo(origin, project):
            incident_dev_pr.mark_intent(execution_id, status="skipped",
                                        error=f"origin del working tree ({origin}) no mapea al repo del tracker")
            _comment_issue_safe(ado_id, project, f"🔧 El working tree apunta a otro remoto ({origin}); no se abrió PR automático para no commitear en el repo equivocado. Revisá manualmente.")
            return

        classify = incident_dev_pr.classify_changed_files(changed)
        branch = f"{_BRANCH_PREFIX}{ticket_id}-exec-{execution_id}"
        title, description = _build_pr_body(ado_id, classify, deleted, origin)

        from services.repo_writer import get_repo_writer
        from services.merge_request_provider import get_merge_request_provider
        writer = get_repo_writer(project)
        mrp = get_merge_request_provider(project)

        committed = []
        skipped_binary = []
        commit_msg = f"fix(incidencia #{ado_id if ado_id is not None else ticket_id}): resolución del Dev Resolutor + tests"
        for rel in changed:
            content = _read_text_or_none(repo_root, rel)   # None si binario/no-utf8/ilegible/>_MAX_TEXT_BYTES
            if content is None:
                skipped_binary.append(rel)
                continue
            writer.commit_file(rel, content, branch, commit_msg)   # (path, content, branch, message) — crea la rama en el 1er call
            committed.append(rel)

        if not committed:
            incident_dev_pr.mark_intent(execution_id, status="skipped",
                                        error="todos los archivos eran binarios/ilegibles")
            _comment_issue_safe(ado_id, project, "🔧 Los cambios eran binarios; el PR automático (sólo texto) no aplica.")
            return

        target = _default_branch_for(mrp, project)          # api/devops_production.py:37, fallback "main"
        pr = mrp.create_merge_request(source_branch=branch, target_branch=target,
                                      title=title, description=description)
        pr_url = pr.get("web_url") or ""
        incident_dev_pr.mark_intent(execution_id, status="opened", pr_id=pr.get("id"),
                                    pr_url=pr_url, branch=branch, files_committed=committed, origin=origin)
        _comment_issue_safe(ado_id, project, f"🚀 PR abierto automáticamente con el fix y los tests: {pr_url}")
    except Exception as exc:  # noqa: BLE001 — K3/Plan 135: el fallo NUNCA queda mudo
        logger.warning("auto-PR incidencia exec=%s falló: %s", execution_id, exc, exc_info=True)
        try:
            incident_dev_pr.mark_intent(execution_id, status="error", error=str(exc))
            _comment_issue_safe(ado_id, project, f"⚠️ No se pudo abrir el PR automático: {exc}")
        except Exception:  # noqa: BLE001 — best-effort final
            pass

def register(register_post_hook):
    register_post_hook(maybe_open_pr_for_incident_dev)
```

**Helpers privados (mismo archivo, contrato literal):**
- `_ticket_ado_id_and_project(ticket_id) -> tuple[int | None, str | None]` (C3/C4): carga el `Ticket`
  por PK **una vez** (`from db import session_scope; from models import Ticket; with session_scope()
  as s: t = s.get(Ticket, ticket_id)`); devuelve `(t.ado_id, ctx.stacky_project_name)` donde
  `ctx = project_context.resolve_project_context(ticket=t)`; si `ctx` es None → `(ado_id, None)` (el
  proveedor usa el proyecto activo). Best-effort: ante cualquier excepción → `(None, None)`. **Ojo:**
  `ProjectContext` expone `stacky_project_name` y `workspace_root`, **NO** `.name` (verificado
  `project_context.py:46-51`).
- `_read_text_or_none(repo_root, rel_posix) -> str | None`: lee bytes de `repo_root/rel`; si hay
  `\x00` o el `decode("utf-8")` falla → None (binario); si el tamaño excede `_MAX_TEXT_BYTES`
  (`1_000_000`, C7 — cap **propio** del auto-PR, NO el de 10 MB del intake) → None + warning.
- `_default_branch_for(mrp, project) -> str` (C1): **reusa** `api/devops_production.py::_default_branch`
  (`api/devops_production.py:37`, verificado — **NO** existe `services/devops_production.py`). Firma
  real `_default_branch(provider, project)`: chequea `provider.name == "azure_devops"` y delega en
  `ado_pipeline_definitions._default_branch`; si no, hace el GET de GitLab. `mrp` (de
  `get_merge_request_provider`) **ES** el tracker provider (mismo objeto que `get_repo_writer`,
  `merge_request_provider.py:82-85`), así que tiene `.name`. Implementación literal:
  `try:` → `from api.devops_production import _default_branch` (import **lazy** dentro de la función,
  evita el cruce de capas a nivel de módulo) → `return _default_branch(mrp, project) or "main"`;
  `except Exception:` → `return "main"` (fallback DURO).
- `_worktree_maps_to_wrong_repo(origin, project) -> bool` ([ADICIÓN ARQUITECTO], C5): devuelve `True`
  **sólo** cuando se puede afirmar **inequívocamente** que el `origin` del working tree apunta a un
  repo distinto del repo del tracker del proyecto (cero falsos positivos por diseño). Método: si
  `origin` es vacío/None → `False` (no se puede afirmar → proceder, degradación = v1). Intentar
  obtener la URL base del proveedor **sin red** (`get_tracker_provider(project)._client._base_proj`
  para ADO; base URL para GitLab); parsear `host` de AMBOS con `urllib.parse.urlparse` (para remotos
  `git@host:org/repo` de SSH, extraer el host tras `@` y antes de `:`). Si AMBOS host parsean limpio y
  **difieren** → `True`; ante CUALQUIER duda (SSH sin host claro, provider no resoluble, parseo
  incierto) → `False`. **Nunca degrada por debajo de v1.**
- `_build_pr_body(ado_id, classify, deleted, origin) -> tuple[str, str]`: **title** =
  `f"[Incidencia #{ado_id}] Fix automático del Dev Resolutor"`; **description** en HTML/Markdown
  simple con secciones: "Resuelto por el **Dev Resolutor de Incidencias** (Stacky)", "**Cambios de
  código**" (lista `classify['code']`), "**Tests incluidos**" (lista `classify['tests']` — K2),
  "**Origen del working tree:** `{origin}`" (trazabilidad para la revisión — [ADICIÓN ARQUITECTO]), y
  si `deleted`: "**Archivos eliminados (no reflejados por la API REST, revisar manual)**". Enlace a la
  Issue por `ado_id`.
- `_comment_issue_safe(ado_id, project, body) -> None` (C2/C4): comenta en la Issue del tracker,
  best-effort (try/except mudo interno). **Ruta AGNÓSTICA de runtime** (verificado: `ado_provider.py:92`
  y `gitlab_provider.py:295` definen la MISMA firma `post_comment(item_id, body_html)`):
  `if ado_id is None:` → sólo loguear y `return`; si no → `from services.tracker_provider import
  get_tracker_provider; get_tracker_provider(project).post_comment(str(ado_id), body)`. **PROHIBIDO**
  usar `ado_client.post_comment` (ADO-específico → rompe paridad GitLab) o pasar la PK local. **Nunca**
  transiciona ni cierra.

**Registro en `app.py`** (junto a `incident_autopublish.register(...)`, `:718-719`, verificado):
```python
    from services import ticket_status, incident_autopublish, incident_dev_autocommit
    incident_autopublish.register(ticket_status.register_post_hook)
    incident_dev_autocommit.register(ticket_status.register_post_hook)
```

**Tests (TDD):** archivo nuevo `backend/tests/test_incident_dev_autocommit.py`. Mockear el proveedor
MR (`get_repo_writer`/`get_merge_request_provider` → fakes que registran llamadas), el comentario
agnóstico (`services.tracker_provider.get_tracker_provider` → fake con `post_comment(item_id,
body_html)` que registra llamadas), `_ticket_ado_id_and_project` (→ `(ado_id, project)` fijos),
`incident_dev_pr`
(`get_intent`/`snapshot_worktree`/`compute_changed_files`/`classify_changed_files`/`mark_intent`/`remote_origin_url`).
Espejar helpers de `test_incident_autopublish.py`. Casos:
1. `test_opens_pr_with_code_and_tests`: intent `open_pr`, `completed`, delta con
   `["src/fix.py","backend/tests/test_fix.py"]` → `commit_file` llamado 2 veces (misma `branch`),
   `create_merge_request` llamado 1 vez; `mark_intent(status="opened", pr_url=...)`; la `description`
   pasada a `create_merge_request` contiene "Tests incluidos" y `test_fix.py` (K2).
2. `test_noop_when_delta_empty`: delta vacío (⚠️ BLOQUEADO) → `create_merge_request` **no** llamado;
   `mark_intent(status="blocked_empty")`.
3. `test_noop_when_no_intent`: `get_intent` → None → no llama al proveedor.
4. `test_noop_when_agent_type_not_incident_dev`: `agent_type="developer"` → return temprano.
5. `test_noop_when_final_status_not_completed`: `final_status="failed"` → return temprano.
6. `test_idempotent_when_already_opened`: intent con `status="opened"` → no reabre.
7. `test_flag_off_is_noop`: `STACKY_INCIDENT_DEV_PR_ENABLED=False` → return temprano (byte-idéntico).
8. `test_error_is_not_silent`: `create_merge_request` lanza → `mark_intent(status="error", error=...)`
   y `_comment_issue_safe` llamado con el mensaje de error; **no** relanza (no rompe el runner).
9. `test_binary_files_skipped`: `_read_text_or_none` → None para el único archivo → `create_merge_request`
   **no** llamado; `mark_intent(status="skipped")`.
10. `test_comment_uses_tracker_ado_id_not_local_pk` (C2/C4): el hook recibe `ticket_id=5` (PK local) y
    `_ticket_ado_id_and_project` → `(12345, "proj")`; el `post_comment` del provider agnóstico se llama
    con `item_id="12345"` (str del ado_id), **NO** con `"5"`.
11. `test_skip_when_worktree_maps_to_wrong_repo` ([ADICIÓN ARQUITECTO], C5): `remote_origin_url` → un
    remoto de otro host/organización que el del provider mockeado (`_worktree_maps_to_wrong_repo` →
    True) → `create_merge_request` **no** llamado; `mark_intent(status="skipped")` con el error de
    mismatch; comentario en la Issue. Caso simétrico: mismo host → sí abre PR (cubierto por el caso 1).
Registrar en `HARNESS_TEST_FILES` (G2).

**Comando (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest tests/test_incident_dev_autocommit.py tests/test_incident_autopublish.py -q
```

**Criterio BINARIO:** 11 casos nuevos verdes + `test_incident_autopublish.py` sigue verde.

**Impacto por runtime:** el post-hook se dispara desde `on_execution_end` para **cualquier** runtime
(CLI + `manifest_watcher`) → paridad Codex/Claude/Copilot. **Fallback:** flag OFF o sin intent →
no-op. **Trabajo del operador:** ninguno (revisa/mergea el PR cuando quiere).

---

### F5 — Frontend: checkbox "Abrir PR" premarcado junto al botón "Resolver con agente"

**Objetivo (1 frase):** al lado del botón "🔧 Resolver con agente" del board, mostrar (sólo si
`dev_pr_enabled`) un checkbox **"Abrir PR"** premarcado cuyo valor viaja como `open_pr` a
`run-incident-dev`.

**Archivos a editar:**
- `Stacky Agents/frontend/src/api/endpoints.ts` (`runDevResolver` `:4220` — agregar `open_pr`)
- `Stacky Agents/frontend/src/incidents/incidentModel.ts` (`IncidentStatusDTO` `:13` — `dev_pr_enabled`)
- `Stacky Agents/frontend/src/pages/TicketBoard.tsx` (estado `devPrEnabled`, checkbox, payload)
- `Stacky Agents/frontend/src/pages/TicketBoard.module.css` (clase del checkbox — G6)
- CREAR `Stacky Agents/frontend/src/incidents/incidentDevPrModel.ts` (+ `.test.ts`) — modelo puro

**1) `endpoints.ts::runDevResolver`** (`:4220-4227`): agregar `open_pr?: boolean;` al tipo del
payload (el `api.post` ya serializa el objeto entero, no hay que tocar más).
```ts
  runDevResolver: (payload: {
    ticket_id: number;
    runtime?: import("../types").AgentRuntime;
    project?: string | null;
    model?: string | null;
    effort?: "low" | "medium" | "high" | "xhigh" | "max";
    open_pr?: boolean;                 // Plan 177
  }) =>
```

**2) `incidentModel.ts::IncidentStatusDTO`** (`:8-14`): agregar el campo espejo del backend F0:
```ts
  /** Plan 177 — con true, el board muestra el checkbox "Abrir PR" en las Issues. */
  dev_pr_enabled?: boolean;
```

**3) `incidentDevPrModel.ts` (modelo PURO, respeta el gap RTL/jsdom):**
```ts
/** Plan 177 — modelo puro del checkbox "Abrir PR" del board. Sin DOM. */
export const DEFAULT_OPEN_PR = true; // premarcado (directiva del operador)
export function shouldShowOpenPrCheckbox(args: {
  canResolve: boolean; devPrEnabled: boolean;
}): boolean {
  return args.canResolve && args.devPrEnabled;
}
```

**4) `TicketBoard.tsx`:**
- Estado global del board: junto a `devResolverEnabled` (`:769`), leer del **mismo**
  `Incidents.status()` (`:775`) el nuevo campo:
  ```tsx
  const [devPrEnabled, setDevPrEnabled] = useState(false);
  // ... dentro del efecto que ya hace setDevResolverEnabled(Boolean(s.dev_resolver_enabled)):
  setDevPrEnabled(Boolean(s.dev_pr_enabled));
  ```
  Pasar `devPrEnabled` por props a `EpicGroup` (`:627/630/743`) y a `TicketCard`
  (`:244/249/1147/1165`), espejo EXACTO de cómo ya se propaga `devResolverEnabled`.
- En `TicketCard`: estado local del checkbox, premarcado:
  ```tsx
  import { shouldShowOpenPrCheckbox, DEFAULT_OPEN_PR } from "../incidents/incidentDevPrModel";
  const [openPr, setOpenPr] = useState(DEFAULT_OPEN_PR);
  const showOpenPr = shouldShowOpenPrCheckbox({ canResolve: canResolveIncident, devPrEnabled: Boolean(devPrEnabled) });
  ```
- En `handleResolveWithAgent` (`:381`): pasar `open_pr` al payload:
  ```tsx
      const result = await Incidents.runDevResolver({
        ticket_id: ticket.id,
        runtime: agentRuntime,
        project: activeProjectName,
        open_pr: showOpenPr ? openPr : false,   // Plan 177
      });
  ```
  (Agregar `openPr`/`showOpenPr` a las deps del `useCallback` `:397`.)
- Render del checkbox: **junto** al botón `resolveBtn` (`:536-545`), sólo si `showOpenPr`. Clase del
  `.module.css` (G6, **sin** `style={{}}`):
  ```tsx
  {canResolveIncident && showOpenPr && (
    <label className={styles.openPrCheckbox} onClick={(e) => e.stopPropagation()}>
      <input
        type="checkbox"
        checked={openPr}
        onChange={(e) => setOpenPr(e.target.checked)}
        disabled={isResolvingIncident}
      />
      Abrir PR
    </label>
  )}
  ```

**5) `TicketBoard.module.css`:** agregar `.openPrCheckbox` (junto a `.resolveBtn` `:572`) — layout
inline con el botón, tipografía chica, cursor pointer. Sin reglas nuevas de color hardcodeado que
rompan un ratchet; espejar tokens ya usados en el archivo.

**Tests (TDD):** `frontend/src/incidents/incidentDevPrModel.test.ts` (vitest, 4 casos):
`test DEFAULT_OPEN_PR es true`; `test shouldShow true cuando canResolve && devPrEnabled`;
`test shouldShow false si devPrEnabled false`; `test shouldShow false si canResolve false`. El
wiring del checkbox/props se valida en el smoke manual (F6) — gap RTL/jsdom conocido.

**Comando:**
```bash
cd "Stacky Agents/frontend" && npx vitest run src/incidents/incidentDevPrModel.test.ts && npx tsc --noEmit
```

**Criterio BINARIO:** 4 casos verdes + `tsc --noEmit` limpio. Smoke manual: en una Issue del board
aparece "🔧 Resolver con agente" con un checkbox "Abrir PR" premarcado; resolver con el check ON
abre un PR; desmarcado no abre PR.

**Impacto por runtime:** el checkbox es UI; el `open_pr` viaja al backend agnóstico. **Fallback:**
`dev_pr_enabled=false` → el checkbox no se renderiza (comportamiento Plan 166). **Trabajo del
operador:** ninguno (un click; desmarcar es opcional).

---

### F6 — Cierre: ratchet, smokes y DoD

**Objetivo (1 frase):** dejar el plan verificable end-to-end y sin deuda de registro.

**Acciones:**
- Confirmar que **todos** los `test_*.py` nuevos (`test_plan177_ado_commit_web_url.py`,
  `test_incident_dev_diff.py`, `test_incident_dev_autocommit.py`) están en `HARNESS_TEST_FILES` en
  **ambos** `run_harness_tests.sh` y `.ps1` (G2). (`test_incident_dev_agent.py` ya está registrado
  desde el Plan 166 — no duplicar.)
- Smoke manual E2E (documentar en `plan-177-status`): en una Issue real del board, con el checkbox
  "Abrir PR" marcado, click "🔧 Resolver con agente" → el agente arregla y escribe tests → al
  terminar, aparece un PR en el tracker con el fix + los tests y un comentario con el link en la
  Issue. Repetir desmarcando el checkbox → no se abre PR. **No ejecutado por defecto** si implica
  tocar el repo/tracker real del operador (mismo criterio de riesgo del Plan 166: el operador decide
  cuándo correrlo).

**Comando de verificación agregada (Git Bash):**
```bash
cd "Stacky Agents/backend" && .venv/Scripts/python -m pytest \
  tests/test_harness_flags.py tests/test_harness_flags_requires.py \
  tests/test_plan177_ado_commit_web_url.py tests/test_incident_dev_diff.py \
  tests/test_incident_dev_agent.py tests/test_incident_dev_autocommit.py \
  tests/test_incident_autopublish.py tests/test_plan95_ado_parity.py -q
```
```bash
cd "Stacky Agents/frontend" && npx vitest run src/incidents/incidentDevPrModel.test.ts && npx tsc --noEmit
```

**Criterio BINARIO:** todo verde.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El diff barre cambios preexistentes del operador (working tree ya sucio antes del run). | F2 usa **delta por hash** contra un **baseline** tomado antes del run: un archivo dirty que el agente no toca queda EXCLUIDO (mismo sha). Sólo entran archivos nuevos o con sha cambiado por el run. |
| R2 | El commit REST se hace **sobre la default branch remota**, no sobre la base local del working tree; si el árbol local está desincronizado, el diff del PR puede incluir/omitir contexto. | Es una **propuesta** que el operador revisa antes de mergear; el smoke recomienda resolver desde un árbol al día. La rama se crea off default (`ado_provider.py:169-191`). Documentado como límite conocido; el camino "git push local fiel" quedó descartado por el operador (sin credenciales de push). |
| R3 | La API REST no expresa **borrados/renombres ni binarios**. | Los borrados se **listan** en la descripción del PR (revisión manual); los binarios se omiten con warning y, si sólo había binarios, no se abre PR (`status="skipped"`, comentario en la Issue). Un fix de incidencia típico es edición/alta de archivos de texto. |
| R4 | Se abre un PR con un fix de baja calidad sin que el operador lo vea. | No es merge: es un PR abierto que el operador revisa/cierra. El checkbox es desmarcable y el flag apagable. El agente ya pasó su contrato (verificar antes de creer, `incident_dev` §3bis.2 del Plan 166). |
| R5 | El post-hook corre síncrono en el thread del runner y podría colgarlo con llamadas REST lentas. | Las llamadas usan el `AdoClient/_request` con timeouts; `on_execution_end` **traga** excepciones del hook (`ticket_status.py:325-330`) → nunca rompe el run; los fallos se registran (no mudos, K3). Cap `_MAX_FILES=60` evita PRs gigantes. |
| R6 | Carrera baseline↔intent: el agente completa antes de que se escriba el intent. | Ventana de microsegundos (F3: `record_intent` inmediatamente tras `run_agent`); un fix real tarda segundos-minutos. Si aun así no hay intent al completar, el post-hook simplemente no abre PR (degradación segura, sin error). |
| R7 | Doble disparo de `on_execution_end` (rescue/cancel) reabre el PR. | Idempotencia por `execution_id`: el intent store guarda `status`; el hook corta si ya es `opened`/`blocked_empty`/`error`/`skipped`. Rama determinista `stacky/incidencia-{ticket}-exec-{exec}`. |
| R8 | El agente commiteó en el repo de **Stacky** en vez del proyecto (workspace_root vacío → fallback). | F3 exige un **repo git real del proyecto** vía `resolve_repo_root` (rev-parse); si no lo hay, no se registra intent → no hay auto-PR. Corta el fallback `cwd_fallback` de raíz. |
| R11 | El working tree es un repo git real pero su `origin` apunta a **OTRO repo/proyecto** que el del tracker (hueco que R8 NO cubre). | **[ADICIÓN ARQUITECTO] C5:** la guardia `_worktree_maps_to_wrong_repo` compara host/organización del `origin` vs la base del proveedor; ante mismatch inequívoco → `status="skipped"` + comentario (no abre PR). Ante duda → procede (no degrada v1). El `origin` se anota en la descripción del PR y el intent para la revisión humana. |
| R9 | Merge con la sesión paralela sobre `api/agents.py`/`TicketBoard.tsx`/`ado_provider.py`. | Cambios **aditivos** (funciones, ramas y campos nuevos); `git status` en frío antes de commitear; el fix de F1 es un reemplazo de 2 líneas puntuales. |
| R10 | El proyecto activo no tiene proveedor MR (tracker no-ADO/no-GitLab, o sin PAT). | `get_repo_writer`/`get_merge_request_provider` lanzan excepción tipada; el hook la captura → `status="error"` + comentario "no se pudo abrir el PR" (no mudo). Sin PR, la resolución del agente queda igual en el working tree para commit manual. |

---

## 6. Fuera de scope

- **Merge/aprobación/transición automática** de la Issue o del PR (sólo se abre; el operador
  decide). El Plan 166 ya excluye que el Dev Resolutor cierre/transicione.
- **`git push` local fiel** (con borrados/binarios): descartado por el operador (sin credenciales de
  push cableadas). Este plan es 100% REST/PAT.
- **Commit multi-archivo atómico** (un solo commit squasheado): `commit_file` es single-file (N
  archivos = N commits en la rama). Un `commit_files` batch queda para un plan futuro.
- **Embeber la narrativa `🚀` del agente** (secciones CAUSA RAIZ / TESTS EJECUTADOS del comentario)
  en la descripción del PR: requiere parsear el output del run por runtime (frágil). v1 arma la
  descripción desde los archivos cambiados (los tests **igual** viajan como archivos, K2). Mejora
  futura best-effort.
- **OCR/visión, catálogo de modelos, ledger de publicación**: otros planes.

---

## 7. Glosario + Orden de implementación + DoD

### Glosario
- **Dev Resolutor (`incident_dev`, Plan 166 F4/F5):** agente que toma una Issue y la resuelve en el
  repo (fix + tests + comentario `🚀`); NUNCA publica/transiciona. Endpoint `run-incident-dev`.
- **Proveedor MR:** abstracción tracker-agnóstica `merge_request_provider`/`repo_writer` con
  adaptadores ADO/GitLab; commitea archivos y abre PRs **por REST con el PAT** (sin git local).
- **Post-hook (`register_post_hook`):** callable agnóstico de runtime que corre al terminar cualquier
  ejecución de agente (`ticket_status.on_execution_end`). Precedente: `incident_autopublish.py`.
- **Intent store:** json en disco keyeado por `execution_id` (`data_dir()/incident_dev_pr/`) que
  lleva el consentimiento del checkbox + el baseline del working tree del endpoint al post-hook.
- **Delta por hash:** archivos cuyo sha de contenido cambió entre el baseline (pre-run) y el estado
  post-run; aísla lo que tocó el agente sin barrer lo dirty preexistente.
- **Patrón triple (flags):** `config.py` + `harness_flags.py` (`FlagSpec` + `_CATEGORY_KEYS`) +
  `_CURATED_DEFAULTS_ON` (si `default=True`) + arista `requires` congelada.

### Orden de implementación
1. **F0** — flag + `dev_pr_enabled` en status.
2. **F1** — fix `ado_provider.commit_file` (prerrequisito ADO).
3. **F2** — servicio de diff + intent store.
4. **F3** — `run_incident_dev`: baseline + intent.
5. **F4** — post-hook auto-commit + PR (núcleo).
6. **F5** — checkbox premarcado en el board.
7. **F6** — ratchet, smokes, DoD.

### Definición de Hecho (DoD) global
- [ ] `STACKY_INCIDENT_DEV_PR_ENABLED` existe (config + `FlagSpec` + `_CATEGORY_KEYS` +
      `_CURATED_DEFAULTS_ON` + arista `requires` congelada); `test_harness_flags*.py` verdes.
      `GET /api/incidents/status` devuelve `dev_pr_enabled`.
- [ ] `ado_provider.commit_file` ya no referencia `_base_project_url`; devuelve `web_url` sin
      `AttributeError` (`test_plan177_ado_commit_web_url.py` verde; parity ADO sigue verde).
- [ ] El servicio de diff aísla el delta por hash y separa código/tests; el intent store hace
      roundtrip idempotente (`test_incident_dev_diff.py` 7/7).
- [ ] `run_incident_dev` captura baseline y registra intent sólo con flag ON + `open_pr` + repo git
      real (`test_incident_dev_agent.py`, casos nuevos + los 6 del Plan 166 verdes).
- [ ] Al terminar un run `incident_dev` `completed` con intent, se commitean código **+ tests** a una
      rama y se abre **un** PR cuya descripción lista los tests; diff vacío/BLOQUEADO → no-op; errores
      no mudos; idempotente (`test_incident_dev_autocommit.py` 11/11; `test_incident_autopublish.py`
      sigue verde).
- [ ] El comentario en la Issue usa `ticket.ado_id` (no la PK local) por la ruta agnóstica
      `get_tracker_provider(project).post_comment(...)` — paridad ADO/GitLab (caso 10).
- [ ] [ADICIÓN ARQUITECTO] La guardia de mapeo working-tree↔tracker evita commitear al repo
      equivocado (mismatch inequívoco de `origin` → `status="skipped"` + comentario), y el `origin`
      queda anotado en la descripción del PR y en el intent (caso 11).
- [ ] El board muestra el checkbox "Abrir PR" premarcado en las Issues (sólo con `dev_pr_enabled`) y
      manda `open_pr` a `run-incident-dev` (`incidentDevPrModel.test.ts` 4/4; `tsc --noEmit` limpio).
- [ ] Todos los `test_*.py` nuevos registrados en `HARNESS_TEST_FILES` (ambos scripts).
- [ ] El auto-PR NUNCA mergea/cierra/transiciona la Issue ni aprueba el PR (verificado por lectura
      del diff: sólo `commit_file` + `create_merge_request` + comentario).
- [ ] Con `STACKY_INCIDENT_DEV_PR_ENABLED=OFF` (o checkbox desmarcado) el comportamiento es
      byte-idéntico al de hoy (casos `*_flag_off`/`open_pr false`).
- [ ] `plan-177-status` documentado con el resultado real de los tests y el smoke E2E (ejecutado o
      no, y por qué).

---

_Plan 177 v2 — Stacky Agents. Propuesto 2026-07-18 por directiva del operador; criticado por el juez
adversarial 2026-07-18 (5 anclas load-bearing verificadas contra el código; C1-C7 + [ADICIÓN
ARQUITECTO] aplicados). APROBADO-CON-CAMBIOS. Pendiente de `implementar-plan-stacky`._
