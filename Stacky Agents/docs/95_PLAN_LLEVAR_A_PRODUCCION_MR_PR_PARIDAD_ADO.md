# Plan 95 — "Llevar a producción": MR/PR con merge HITL + paridad ADO E2E real (commit/trigger/monitor)

**Estado:** CRITICADO
**Versión:** v1 → v2 (crítica adversarial aplicada)
**Fecha:** 2026-07-05
**Veredicto del juez:** APROBADO-CON-CAMBIOS (0 bloqueantes, 4 importantes, 4 menores).

## Changelog v1 → v2

- **C1 (IMPORTANTE, resuelto en F0/F5):** F0 decía "5 patas" pero la flag declara
  `requires=` ⇒ faltaba la **6ª pata**: arista
  `STACKY_DEVOPS_PRODUCTION_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` en
  `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py`, junto a las de
  88-93). Sin ella el meta-test R4 quedaba ROJO en silencio (misma omisión que
  93 C1 / 94 C1). F0 ahora es de 6 patas y F5 corre ese test.
- **C2 (IMPORTANTE, resuelto en F3/F4):** incoherencia de gating — §3.4 dice que
  la paridad ADO de F1 NO depende de la flag nueva, pero F4 v1 habilitaba el
  commit ADO del modal con `production_enabled === true`. Ahora el modal habilita
  por la capability aditiva `ado_commit_supported: true` en `devops_health_route`
  (existe solo en builds con F1); deploys viejos no tienen la key ⇒ disabled ⇒
  no-regresión binaria.
- **C3 (IMPORTANTE, resuelto en F1.a):** "leer cómo resuelve el módulo y COPIAR"
  era frase vaga. Ahora hay helpers literales `_resolve_repo_id` y
  `_default_branch` con reglas cerradas y tests propios.
- **C4 (IMPORTANTE, resuelto en F1):** el criterio decía 14 tests pero enumeraba
  13. Se agrega `test_f1_resolve_repo_id_rules` (cierra C3) ⇒ 14 reales.
- **C5 (MENOR, F4):** polling del MR con tope (60 polls / 5 min) + pausa con
  `document.hidden` + botón "Actualizar" manual.
- **C6 (MENOR, F0):** nota de drift preexistente de `harness_defaults.env`
  (espejo 93/94): solo AGREGAR la línea nueva, nunca regenerar el archivo.
- **C7 (MENOR, F2/§6):** declarado que el `pipeline_status` del PR ADO es el
  último build de la SOURCE branch; los PR validation builds (`refs/pull/*/merge`)
  quedan fuera de scope v1.
- **C8 (MENOR, F4):** asimetría HITL declarada a propósito: crear MR/PR usa
  `window.confirm` (reversible); mergear exige checkbox literal + confirm
  server-side. NO emparejar hacia abajo.
- **[ADICIÓN ARQUITECTO] (F4):** paso 4 opcional post-merge "Correr pipeline en
  la rama default" reusando los endpoints EXISTENTES de `/api/ci`
  (trigger/monitor del 87/72, paritarios post-F1). Cero backend nuevo; cierra el
  ciclo "mi proyecto publica de verdad".
**Serie DevOps E2E:** plan 3 de 4 (93 preflight / 94 variables / 95 producción / 96 doctor).
**Requisito textual del operador (riel #1):** compatible con **Azure DevOps Y GitLab
desde el día 1**. Este plan es la PIEDRA ANGULAR de esa paridad: además del flujo
MR/PR, **cierra los tres TODOs declarados de ADO** que hoy hacen que el panel DevOps
solo funcione E2E en GitLab:

| TODO ADO abierto (declarado en su plan de origen) | Evidencia |
|---|---|
| `commit_file` ADO ⇒ `NotImplementedError` ⇒ 501 render-only (plan 73 C12) | `backend/services/ado_provider.py:145-151`, `backend/api/pipeline_generator.py:86-89` |
| `trigger_pipeline` ADO ⇒ `NotImplementedError` (plan 72 "fuera de scope v1") | `backend/services/ado_ci_provider.py:31-35` |
| `monitor_pipeline` ADO ⇒ `NotImplementedError` + `last_pipeline_for_ref` ⇒ None | `backend/services/ado_ci_provider.py:25-29,37-39` |

**Dependencias:** plan 87 IMPLEMENTADO (`84a9ecb5`, host + CommitPipelineModal +
TriggerPipelineSection). Planes 93/94: integraciones aditivas (el helper
`services/ado_pipeline_definitions.py` es COMPARTIDO — lo crea el primero de
93/94/95 que se implemente, contenido base en 93 F2; este plan le AGREGA
`ensure_yaml_definition`). Verificado en working tree 2026-07-05:

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| Contrato RepoWriter (retorno `{sha,branch,path,web_url,status}`) | `backend/services/repo_writer.py:13-27`, `get_repo_writer:30` |
| Implementación GitLab de referencia (create/update/unchanged) | `backend/services/gitlab_provider.py:590` |
| Protocol CIProvider (métodos que este plan IMPLEMENTA para ADO, sin cambiar la firma) | `backend/services/ci_provider.py:83-100` (`CI_PORT_METHODS` intacto) |
| GitLab trigger/poll de referencia (contrato de retorno a espejar) | `backend/services/gitlab_provider.py:522` (`trigger_pipeline`), `:545` (`poll_pipeline`) |
| Rutas HITL trigger/monitor tracker-agnósticas (NO cambian) | `backend/api/ci.py:26,76,139,174` |
| Endpoint commit HITL (NO cambia de contrato; el 501 ADO muere solo) | `backend/api/pipeline_generator.py:52-89` |
| Cliente REST ADO con PAT | `backend/services/ado_client.py:257` (`_request`), `_API_VERSION` |
| Modal de commit del 87 (opción "ado" deshabilitada con nota 501) | `frontend/src/components/devops/CommitPipelineModal.tsx` |
| Sección trigger/monitor del 87 | `frontend/src/components/devops/TriggerPipelineSection.tsx` |
| Panel host §3.12 + FlagGateBanner + health aditivo | `frontend/src/pages/DevOpsPage.tsx:44,68`, `backend/api/devops.py:25-38` |
| Patrón flag 5 patas + ratchet | `backend/config.py:857-859`, `harness_flags.py:177-183`, `run_harness_tests.ps1:103-125` |

---

## 1. Objetivo + KPI

Cerrar el ciclo **"probé el pipeline en una rama" → "mi proyecto publica de
verdad"** sin salir del panel, en ambos trackers:

1. **Paridad ADO E2E (F1):** `commit_file` real (Git Pushes API), `trigger_pipeline`
   / `monitor_pipeline` / `last_pipeline_for_ref` reales (Pipelines Runs API) y
   `ensure_yaml_definition` (find-or-create de la pipeline definition, HITL).
   Con esto, TODO el flujo 87/88 existente (commit modal, trigger, monitor)
   funciona en ADO sin tocar sus contratos.
2. **Flujo "Llevar a producción" (F2-F4):** post-commit, 3 pasos HITL:
   (a) crear **Merge Request** (GitLab) / **Pull Request** (ADO) hacia la rama
   default; (b) ver el estado del pipeline del MR/PR en vivo; (c) **Mergear** con
   checkbox de confirmación literal. Nunca auto-merge.

**KPI (aspiracional; criterios binarios en F5):**
- Un pipeline creado en el panel llega a la rama default en ≤ 3 clicks post-commit
  (crear MR/PR → ver verde → mergear), en ADO y en GitLab.
- 0 visitas obligadas a la web del tracker para publicar.
- El commit ADO deja de responder 501: mismo contrato de retorno que GitLab
  (criterio binario F1).
- 0 merges sin confirmación explícita (HITL server-side, criterio binario F3).

## 2. Por qué ahora / gap que cierra

El commit del panel escribe en una **feature branch** (`pipeline_generator.py:70-71`)
— correcto para probar, pero el pipeline que el repo USA vive en la rama default, y
no hay ningún camino de UI para llegar ahí. Peor: en ADO ni siquiera hay commit
(501), ni trigger, ni monitor — la mitad del requisito "pipelines en ADO y en
GitLab" hoy no se cumple. Los planes 72/73 declararon esos TODOs "post-v1"; este
plan ES ese post-v1, más el tramo MR/PR que ningún plan cubrió.

## 3. Principios y guardarraíles (NO negociables)

1. **PARIDAD ADO + GITLAB:** cada capacidad con dos adapters y fábrica por
   tracker_type. La pata ADO no es "best effort": sus tests de adapter (mocks HTTP)
   cubren los mismos casos que los de GitLab.
2. **CERO cambios de contrato existentes:** `CI_PORT_METHODS`
   (`ci_provider.py:100`) intacto — F1 IMPLEMENTA métodos que ya existen en el
   Protocol (hoy lanzan NotImplementedError en ADO). `api/ci.py` y
   `api/pipeline_generator.py` NO se tocan (el 501 muere solo al desaparecer la
   excepción). El retorno de los métodos ADO se NORMALIZA al vocabulario que la UI
   del 87 ya consume del lado GitLab (status ∈ created/pending/running/success/
   failed/canceled).
3. **HITL en tres escalones:** crear la definition ADO exige `confirm:true`;
   crear MR/PR exige `confirm:true`; mergear exige `confirm:true` + checkbox UI
   con texto literal. Nada corre solo; no hay auto-merge ni merge-when-pipeline-
   succeeds (v1).
4. **Flag propia** `STACKY_DEVOPS_PRODUCTION_ENABLED`: categoría `devops`,
   `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, SIN `default=`,
   CON `label`/`group`, `PlainHelp`, `harness_defaults.env` + test,
   **Y la arista en `_REQUIRES_MAP_FROZEN` (C1 — 6ª pata, ver F0)**. Default OFF.
   **Matiz importante:** la paridad ADO de F1 (commit/trigger/monitor) NO va detrás
   de esta flag — completa contratos EXISTENTES ya gateados por sus propias flags
   (`STACKY_PIPELINE_GENERATOR_ENABLED` / `STACKY_PIPELINE_TRIGGER_ENABLED`).
   La flag nueva gatea SOLO el flujo MR/PR (endpoints `/api/devops/production/*`
   y UI). Se declara así de explícito para que un modelo menor no gatee de más.
5. **Byte-idéntico con flag OFF** para el flujo MR/PR; para F1, "byte-idéntico"
   no aplica (es completar un contrato roto): el criterio es NO-REGRESIÓN GitLab
   (tests de 72/73 verdes sin cambios) + ADO pasa de excepción a funcionar.
6. **Guard anti-CSRF (91 C5):** mutantes con `request.is_json`.
7. **3 runtimes:** UI + Flask; impacto NINGUNO (declarado por fase).
8. **Mono-operador sin auth; cero trabajo extra; ratchet** en ambos scripts.
9. **PAT scopes documentados y errores honestos:** ADO: Code (Read & Write) +
   Build (Read & Execute). GitLab: scope `api`. `TrackerApiError` con `kind` →
   visible en UI (patrón C16 del 87), jamás tragado.

## 4. Fases

> Comandos de test: backend `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> desde `Stacky Agents/backend`; frontend `npx tsc --noEmit` + `npx vitest run
> <archivo>`.

### F0 — Flag `STACKY_DEVOPS_PRODUCTION_ENABLED` (6 patas — C1)

Misma mecánica EXACTA que 93 F0 v2 (espejo `test_plan91_servers_flag.py`).
`label="Llevar a producción (Plan 95)"`, description en llano: "Crea el Merge
Request (GitLab) o Pull Request (ADO) del pipeline commiteado, muestra su pipeline
y permite mergear con confirmación. Default OFF: /api/devops/production/* da 404 y
el botón no aparece. Nota: la paridad ADO de commit/trigger/monitor NO depende de
esta flag (completa contratos existentes)."

Las 6 patas: (1) `config.py`; (2) `harness_flags.py` FlagSpec (SIN `default=`,
`env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, `group="global"`);
(3) `PlainHelp`; (4) `harness_defaults.env` línea
`STACKY_DEVOPS_PRODUCTION_ENABLED=false` en orden alfabético — **nota C6:** hay
drift PREEXISTENTE de ese archivo en el working tree (centinelas 87-91): solo
AGREGAR la línea nueva, NUNCA revertir líneas ajenas ni regenerar el archivo;
(5) test patrón; (6) **[C1] arista en `_REQUIRES_MAP_FROZEN`**
(`tests/test_harness_flags_requires.py`, junto a las de 88-93):
```python
"STACKY_DEVOPS_PRODUCTION_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 95
```

**Tests PRIMERO** — `tests/test_plan95_production_flag.py` (los 5 casos patrón +
no-regresión meta-tests; misma nota plan 85: F0+F3 juntos si el wiring acusa).
No-regresión: `tests/test_harness_flags.py` + `tests/test_flag_wiring.py` +
`tests/test_harness_flags_requires.py` ([C1] R4 exige la arista).
**Ratchet:** registrar. **Criterio binario:** 5+3 verdes; default OFF.
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F1 — Paridad ADO E2E: commit_file + definition + trigger/monitor/last_pipeline_for_ref

**Objetivo:** que ADO funcione con los MISMOS contratos que GitLab ya cumple.

**F1.a — `AdoProvider.commit_file` real** (editar
`Stacky Agents/backend/services/ado_provider.py:145-151`, REEMPLAZANDO el
NotImplementedError):
```python
def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
    """Plan 95 F1.a — commit real vía Git Pushes API (cierra el TODO del plan 73 C12).
    Contrato IDÉNTICO a gitlab_provider.py:590: {sha, branch, path, web_url, status}
    con status 'create'|'update'|'unchanged'. Lanza TrackerApiError (propaga status)."""
    # 1) repo_id: _resolve_repo_id(project) — helper NUEVO en el mismo módulo,
    #    reglas CERRADAS (C3), en este orden:
    #    (a) si el project_config define `repository` (nombre o id), matchear
    #        contra GET {base_proj}/_apis/git/repositories?api-version=7.1
    #        (por id exacto o name case-insensitive); sin match ⇒
    #        TrackerApiError(status=404, kind="ado_repo_not_found").
    #    (b) sin config y la lista tiene EXACTAMENTE 1 repo ⇒ ese.
    #    (c) sin config y >1 repos ⇒ TrackerApiError(status=400,
    #        kind="ado_repo_ambiguous", mensaje con los nombres disponibles).
    # 2) old_object_id del branch: GET .../repositories/{id}/refs?filter=heads/{branch}
    #    - branch existe → oldObjectId = objectId del ref.
    #    - branch NO existe → resolver la DEFAULT branch con _default_branch()
    #      (helper NUEVO del módulo, C3: GET .../repositories/{id} →
    #      campo `defaultBranch`, STRIP del prefijo "refs/heads/") y usar su
    #      objectId como base (el push crea la rama): refUpdate con name
    #      refs/heads/{branch} y oldObjectId = "0000000000000000000000000000000000000000"
    #      NO sirve para ramas con base; ADO exige crear la rama apuntando al commit
    #      base: primero POST refs [{name, oldObjectId: 40*"0", newObjectId: <sha base>}],
    #      luego push normal sobre la rama nueva.
    # 3) ¿create o update? GET .../items?path={path}&versionDescriptor.version={branch}
    #    → 200 ⇒ 'edit' (y si el content es idéntico ⇒ retornar status 'unchanged'
    #    SIN pushear, paridad FIX C7 gitlab); 404 ⇒ 'add'.
    # 4) POST .../repositories/{id}/pushes?api-version=7.1 con
    #    {"refUpdates":[{"name": f"refs/heads/{branch}", "oldObjectId": old}],
    #     "commits":[{"comment": message,
    #        "changes":[{"changeType": "add"|"edit",
    #                    "item": {"path": "/" + path.lstrip("/")},
    #                    "newContent": {"content": content, "contentType": "rawtext"}}]}]}
    # 5) Retorno: sha = commits[0].commitId de la respuesta; web_url = _links del
    #    push o f"{base_proj}/_git/{repo}?path=/{path}&version=GB{branch}".
```
Errores HTTP: `_request_with_retry`/`_request` ya lanzan con status — NO tragarlos
(paridad C1 del 73: el endpoint los convierte en su status real).

**F1.b — `ensure_yaml_definition`** (editar
`Stacky Agents/backend/services/ado_pipeline_definitions.py` — si no existe aún,
crearlo con el `find_yaml_definition` EXACTO del 93 F2 y agregar):
```python
def ensure_yaml_definition(project: str | None, yaml_path: str = "azure-pipelines.yml",
                           *, confirm: bool = False) -> dict:
    """find_yaml_definition; si existe → {'id', 'name', 'created': False}.
    Si NO existe: exige confirm=True (HITL — crear una definition es mutante);
    sin confirm lanza DefinitionConfirmRequired (excepción del módulo).
    Crea con POST {base_proj}/_apis/build/definitions?api-version=7.1:
    {"name": "stacky-" + <slug del proyecto/repo>, "type": "build",
     "queueStatus": "enabled",
     "repository": {"id": <repo_id>, "type": "TfsGit", "defaultBranch": "refs/heads/<default>"},
     "process": {"type": 2, "yamlFilename": yaml_path}}
    → {'id', 'name', 'created': True}."""
```

**F1.c — `AdoCIProvider` real** (editar
`Stacky Agents/backend/services/ado_ci_provider.py:25-39`, reemplazando los 3
NotImplementedError/None):
```python
def trigger_pipeline(self, item_ref: "ItemRef", ref: str) -> dict:
    """Plan 95 F1.c — Runs API. Resuelve la definition (find_yaml_definition; si
    None lanza TrackerApiError(status=409, kind='ado_definition_missing') con
    mensaje que apunta a 'Llevar a producción'/ensure). POST
    {base_proj}/_apis/pipelines/{definitionId}/runs?api-version=7.1 con
    {"resources": {"repositories": {"self": {"refName": f"refs/heads/{ref}"}}}}.
    Retorno NORMALIZADO al shape que la UI ya consume del lado GitLab
    (gitlab_provider.py:522): {"id": run.id, "status": _map_status(run),
     "ref": ref, "web_url": run._links.web.href}."""

def monitor_pipeline(self, pipeline_id: str) -> dict:
    """GET {base_proj}/_apis/build/builds/{id}?api-version=7.1 →
    {"id", "status": _map_status(build), "ref", "web_url"}.
    _map_status: ADO (status, result) → vocabulario GitLab:
    notStarted→created; inProgress→running; postponed→pending;
    completed+succeeded→success; completed+(failed|partiallySucceeded)→failed;
    completed+canceled→canceled. Tabla LITERAL en el módulo (dict), con test."""

def last_pipeline_for_ref(self, ref: str) -> dict | None:
    """GET {base_proj}/_apis/build/builds?branchName=refs/heads/{ref}&$top=1
    &queryOrder=queueTimeDescending → build normalizado o None."""
```

**Tests PRIMERO** — `tests/test_plan95_ado_parity.py` (mocks del `_request` de
`ado_client` en su módulo de ORIGEN; DB/HTTP jamás reales):
- `test_f1_commit_create_new_file` (404 en items ⇒ changeType add; body del push
  EXACTO; retorno con status "create").
- `test_f1_commit_update_existing` (200 en items con contenido distinto ⇒ edit,
  status "update").
- `test_f1_commit_unchanged_no_push` (contenido idéntico ⇒ status "unchanged" y
  el fake de push NO fue llamado — paridad C7 gitlab).
- `test_f1_commit_new_branch_creates_ref` (branch inexistente ⇒ POST refs previo
  con newObjectId = sha de la default).
- `test_f1_commit_tracker_error_propagates` (403 ⇒ TrackerApiError con status).
- `test_f1_resolve_repo_id_rules` [C3/C4] (parametrizado: config con match /
  config sin match ⇒ 404 kind / 1 repo sin config / >1 repos sin config ⇒ 400
  `ado_repo_ambiguous`; y `_default_branch` strippea `refs/heads/`).
- `test_f1_ensure_definition_found_no_create` / 
  `test_f1_ensure_definition_missing_requires_confirm` (sin confirm ⇒
  DefinitionConfirmRequired) / `test_f1_ensure_definition_creates_with_confirm`
  (body EXACTO del POST).
- `test_f1_trigger_posts_runs_api` (refName correcto; retorno normalizado).
- `test_f1_trigger_no_definition_409_kind`.
- `test_f1_monitor_maps_all_statuses` (parametrizado con la tabla completa de
  `_map_status` — 6 casos).
- `test_f1_last_pipeline_for_ref_top1_or_none`.
- **No-regresión de contrato:** correr también
  `tests/test_plan72_ci_provider_trigger_port.py` y
  `tests/test_plan73_generator_endpoint.py tests/test_plan73_repo_writer.py`
  SIN MODIFICARLOS (CI_PORT_METHODS y RepoWriter intactos).
- **Integración commit endpoint:** `test_f1_commit_route_ado_no_more_501` — con
  el provider ADO mockeado devolviendo el dict de éxito, POST
  `/api/pipeline-generator/commit` con `target:"ado"` + confirm ⇒ 200 (el catch
  de NotImplementedError de `pipeline_generator.py:86-89` queda muerto; NO
  borrarlo — robustez).

**Ratchet:** registrar. **Criterio binario:** 14 tests nuevos + no-regresión
72/73 verdes.
**Flag:** las EXISTENTES (`STACKY_PIPELINE_GENERATOR_ENABLED` /
`STACKY_PIPELINE_TRIGGER_ENABLED`) — ver §3.4. **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno (con sus flags ya ON, ADO simplemente empieza a
funcionar).

### F2 — Sub-puerto `MergeRequestProvider` + adapters GitLab y ADO

**Objetivo:** crear/consultar/mergear MR-PR con un contrato único.

**Archivo NUEVO:** `Stacky Agents/backend/services/merge_request_provider.py`
```python
"""merge_request_provider.py — Plan 95. Sub-puerto ISP (patrón repo_writer.py:13)."""
from typing import Optional, Protocol, runtime_checkable

@runtime_checkable
class MergeRequestProvider(Protocol):
    name: str
    def create_merge_request(self, source_branch: str, target_branch: str,
                             title: str, description: str) -> dict:
        """{'id': str, 'web_url': str, 'state': 'open'} (id: iid GitLab /
        pullRequestId ADO, SIEMPRE str). TrackerApiError si el tracker rechaza
        (p.ej. MR duplicado ⇒ propagar su mensaje)."""
        ...
    def get_merge_request(self, mr_id: str) -> dict:
        """{'id', 'state': 'open'|'merged'|'closed', 'pipeline_status':
        'success'|'failed'|'running'|'pending'|'canceled'|'none',
        'mergeable': bool, 'web_url'}."""
        ...
    def merge_merge_request(self, mr_id: str) -> dict:
        """{'id', 'state': 'merged'} o TrackerApiError (conflictos, policies)."""
        ...

MR_PORT_METHODS = ("create_merge_request", "get_merge_request", "merge_merge_request")

def get_merge_request_provider(project: Optional[str] = None) -> MergeRequestProvider:
    """Fábrica espejo de get_repo_writer (repo_writer.py:30): resuelve el tracker
    provider activo y valida isinstance MergeRequestProvider."""
```

**Archivo a editar:** `Stacky Agents/backend/services/gitlab_provider.py` —
agregar a `GitLabTrackerProvider` (junto a `commit_file:590`):
- `create_merge_request`: `POST /projects/:id/merge_requests`
  `{source_branch, target_branch, title, description}` → normalizar
  (`iid` como str, `web_url`, state "open").
- `get_merge_request`: `GET /projects/:id/merge_requests/:iid` →
  `pipeline_status` desde `head_pipeline.status` (ausente ⇒ "none");
  `mergeable` = `merge_status == "can_be_merged"` (si el campo moderno
  `detailed_merge_status` existe, `== "mergeable"` — soportar ambos).
- `merge_merge_request`: `PUT /projects/:id/merge_requests/:iid/merge` (sin
  `merge_when_pipeline_succeeds` — v1 no difiere el merge) → state "merged".

**Archivo a editar:** `Stacky Agents/backend/services/ado_provider.py` — agregar:
- `create_merge_request`: `POST {base_proj}/_apis/git/repositories/{repo}/pullrequests?api-version=7.1`
  `{"sourceRefName": f"refs/heads/{source}", "targetRefName": f"refs/heads/{target}",
  "title": title, "description": description}` → id = str(pullRequestId).
- `get_merge_request`: `GET .../pullrequests/{id}` → state map
  (active→open, completed→merged, abandoned→closed); `pipeline_status` = último
  build del sourceRef (`GET _apis/build/builds?branchName=<sourceRef>&$top=1` →
  `_map_status` de F1.c; sin builds ⇒ "none"); `mergeable` =
  `mergeStatus == "succeeded"`. **Nota C7:** se muestra el build de la SOURCE
  branch; los PR validation builds de branch policy (`refs/pull/{id}/merge`)
  quedan fuera de scope v1 (ver §6) — con policy activa el operador puede ver
  "none" acá y el build real en la web del PR (link siempre presente).
- `merge_merge_request`: GET del PR (necesita `lastMergeSourceCommit`) →
  `PATCH .../pullrequests/{id}` con `{"status": "completed",
  "lastMergeSourceCommit": {"commitId": <sha>},
  "completionOptions": {"mergeStrategy": "noFastForward",
                         "deleteSourceBranch": false}}`.

**Tests PRIMERO** — `tests/test_plan95_mr_providers.py` (mocks `_request` por
módulo de origen):
- `test_f2_factory_and_structural_conformance` (patrón repo_writer).
- GitLab: `test_f2_gitlab_create_mr_normalized`, `test_f2_gitlab_get_mr_pipeline_status`
  (con y sin head_pipeline), `test_f2_gitlab_merge_ok`,
  `test_f2_gitlab_merge_conflict_propagates` (405/406 ⇒ TrackerApiError).
- ADO: `test_f2_ado_create_pr_refnames`, `test_f2_ado_get_pr_state_map`
  (active/completed/abandoned), `test_f2_ado_get_pr_pipeline_from_builds`,
  `test_f2_ado_merge_patch_body_exact` (lastMergeSourceCommit + noFastForward),
  `test_f2_ado_merge_policy_rejection_propagates`.

**Ratchet:** registrar. **Criterio binario:** 10 tests verdes; `MR_PORT_METHODS`
nuevo (no toca `CI_PORT_METHODS` ni `REPO_WRITER_METHODS`).
**Flag:** ninguna (sin consumidores hasta F3). **Runtimes:** sin impacto.
**Trabajo del operador:** ninguno.

### F3 — Endpoints `/api/devops/production/*` (HITL server-side)

**Objetivo:** exponer el flujo con confirmaciones obligatorias.

**Archivo NUEVO:** `Stacky Agents/backend/api/devops_production.py` (blueprint
propio, prefix `/devops/production`; `_guard()` = flag 404 + is_json en mutantes,
patrón 91 C5):
- `POST "/mr"` body `{project, source_branch, target_branch?, title?, confirm:true}`:
  confirm obligatorio (400); `target_branch` default = default branch del repo
  (GitLab: GET project `default_branch`; ADO: repository `defaultBranch` — helper
  `_default_branch(provider, project)` en el mismo módulo, con test); `title`
  default `f"pipeline: {source_branch}"`. → 201 con el dict del provider.
  `TrackerApiError` ⇒ su status + `{"error", "kind"}`.
- `GET "/mr/<mr_id>"?project=` → dict de `get_merge_request` (polling de la UI).
- `POST "/mr/<mr_id>/merge"` body `{project, confirm:true}` → confirm obligatorio;
  → dict de `merge_merge_request`; conflictos/policies ⇒ status real del tracker
  con mensaje visible.
- `POST "/ado/ensure-definition"` body `{project, confirm:true}` →
  `ensure_yaml_definition(project, confirm=True)` (lo usa la UI cuando el trigger
  ADO devuelve `ado_definition_missing`); en proyectos GitLab ⇒ 400
  `{"error": "solo aplica a proyectos ADO"}`.

**Registro:** `api/__init__.py` (import + register, junto a los devops).
**Health:** en `devops_health_route` (`api/devops.py:29-38`), DOS keys aditivas:
- `"production_enabled": bool(getattr(cfg, "STACKY_DEVOPS_PRODUCTION_ENABLED", False)),`
- `"ado_commit_supported": True,` — **[C2] capability, NO flag:** literal `True`
  porque este build incluye F1 (el commit ADO real). Deploys viejos no tienen la
  key ⇒ el modal (F4) la lee ausente ⇒ opción ADO sigue disabled ⇒ no-regresión.
  Independiente de `production_enabled` (coherente con §3.4).

**Tests PRIMERO** — `tests/test_plan95_production_endpoints.py` (fixtures flag
on/off; providers mockeados vía `unittest.mock.patch(
"api.devops_production.get_merge_request_provider", ...)`):
- `test_f3_flag_off_all_routes_404`.
- `test_f3_non_json_post_400`.
- `test_f3_create_mr_without_confirm_400` / `test_f3_merge_without_confirm_400`
  (HITL server-side — el checkbox del frontend NO alcanza).
- `test_f3_create_mr_happy_201_default_target` (target ausente ⇒ default branch
  resuelta; provider recibió los args correctos).
- `test_f3_get_mr_polls_provider`.
- `test_f3_merge_happy` / `test_f3_merge_conflict_status_propagated`.
- `test_f3_ensure_definition_ado_only`.
- `test_f3_health_has_production_enabled` (asserta también
  `ado_commit_supported is True` — C2) / `test_f3_route_registered`.

**Ratchet:** registrar. **Criterio binario:** 11 tests verdes.
**Flag:** `STACKY_DEVOPS_PRODUCTION_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: flujo "Llevar a producción" + ADO habilitado en el modal de commit

**Objetivo:** los 3 pasos HITL visibles en llano; ADO deja de estar deshabilitado.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/productionModel.ts` (puro):
- Tipos espejo (`MrInfo {id, web_url, state, pipeline_status?, mergeable?}`).
- `mergeButtonEnabled(mr): boolean` = `state === "open" && mergeable === true`
  (el pipeline_status NO bloquea — se MUESTRA; decisión del operador, HITL).
- `pipelineStatusLabel(status): string` en llano ("está corriendo…", "pasó ✅",
  "falló ❌", "sin pipeline").
- `shouldContinuePolling(pollCount, state, documentHidden): boolean` [C5] =
  `state === "open" && !documentHidden && pollCount < 60` (lógica del tope,
  pura y testeable).

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/ProductionFlow.tsx`
- Props `{ ctx: DevOpsSectionContext; project: string; sourceBranch: string }`
  (sourceBranch = branch del último commit exitoso, que el 87 F5 ya recuerda).
- Gate inline: si `ctx.health.production_enabled !== true` ⇒ `FlagGateBanner`
  con `flagKey="STACKY_DEVOPS_PRODUCTION_ENABLED"`.
- Paso 1: botón "Crear Merge Request / Pull Request" (label según tracker si se
  conoce; genérico "Crear MR/PR" si no) + `window.confirm` ⇒
  `DevOpsProduction.createMr(...)` ⇒ muestra link `web_url`.
  **Nota C8 (asimetría HITL a propósito):** crear el MR/PR es reversible ⇒
  alcanza `window.confirm`; mergear NO ⇒ checkbox literal + confirm server-side.
  NO "emparejar" quitando el checkbox del paso 3.
- Paso 2: polling `getMr` cada 5s mientras `state === "open"`, **con tope (C5):**
  se pausa cuando `document.hidden === true` y se detiene tras 60 polls (~5 min);
  al detenerse queda un botón "Actualizar" que hace un `getMr` manual por click.
  Nunca pollea con state merged/closed.
- Paso 3: checkbox literal **"Confirmo el merge a la rama principal"** que
  habilita "Mergear" ⇒ `mergeMr(...)`; éxito ⇒ "🎉 Mergeado: el pipeline del
  proyecto quedó actualizado"; error ⇒ mensaje literal del backend.
- **[ADICIÓN ARQUITECTO] Paso 4 (opcional, post-merge):** botón "Correr pipeline
  en `<default branch>`" que reusa los endpoints EXISTENTES de `/api/ci`
  (`api/ci.py:26,76` — trigger + monitor del 87/72, ya paritarios en ADO
  post-F1) con `ref` = la target branch del MR mergeado, con su confirmación
  HITL existente; el estado se muestra con el mismo patrón de monitor del 87.
  Cero backend nuevo. Cierra el ciclo: el YAML mergeado corre de verdad en la
  rama del proyecto sin visitar el tracker.
- Caso ADO `ado_definition_missing` (del trigger o del preflight): botón
  "Crear la definición del pipeline en ADO" ⇒ confirm ⇒
  `DevOpsProduction.ensureAdoDefinition(project)`.
- Errores async siempre visibles (C16).

**Archivos a editar:**
- `frontend/src/api/endpoints.ts` — namespace `DevOpsProduction`
  (`createMr/getMr/mergeMr/ensureAdoDefinition`), junto a `DevOps` (:3072).
- `frontend/src/components/devops/PipelineBuilderSection.tsx` — tras un commit
  exitoso, montar `<ProductionFlow ctx={ctx} project={project}
  sourceBranch={lastCommitBranch} />` (visible SOLO con commit previo en la
  sesión). Reuso en `PublicationsSection.tsx` (mismo componente post-commit).
- `frontend/src/components/devops/CommitPipelineModal.tsx` — **[C2]** la opción
  `ado` habilita si y solo si `ctx.health.ado_commit_supported === true`
  (capability de F3 — presente solo en builds con F1; NO depende de
  `production_enabled`, coherente con §3.4). Tooltip: "commit ADO habilitado por
  el plan 95". Contra un backend viejo (key ausente) el modal queda EXACTAMENTE
  como hoy (nota 501) — no-regresión visual binaria.
- `frontend/src/pages/DevOpsPage.tsx` — SIN cambios (todo es sub-feature de la
  sección Pipelines/Publicaciones; §3.12).

**Tests** — `frontend/src/devops/productionModel.test.ts` (vitest TS puro):
`merge_enabled_only_open_and_mergeable`, `labels_en_llano`,
`status_none_handled`, `polling_stops_on_cap_hidden_or_not_open` [C5].
Componentes: gate `tsc`.

**Criterio binario:** vitest verde (4 tests) + `tsc` 0 errores; grep:
`ProductionFlow` presente en `PipelineBuilderSection.tsx` y
`PublicationsSection.tsx`; `DevOpsPage.tsx` sin diff; contra un health SIN
`ado_commit_supported` el modal de commit muestra la nota 501 actual (literal
presente en la rama disabled) [C2].
**Flag:** `production_enabled` (gate inline).
**Runtimes:** sin impacto. **Trabajo del operador:** opt-in.

### F5 — Cierre: no-regresión total + checklist binario

**Comandos:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan95_production_flag.py tests/test_plan95_ado_parity.py tests/test_plan95_mr_providers.py tests/test_plan95_production_endpoints.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan72_ci_provider_trigger_port.py tests/test_plan73_generator_endpoint.py tests/test_plan73_repo_writer.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_requires.py -q
cd "../frontend"
npx vitest run src/devops/productionModel.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] PARIDAD NÚCLEO: commit ADO devuelve `{sha,branch,path,web_url,status}` (no
      más 501); trigger/monitor ADO normalizados al vocabulario GitLab; tests de
      72/73 verdes SIN modificar (contratos intactos).
- [ ] Flag OFF ⇒ `/api/devops/production/*` 404, botón ausente, modal de commit
      idéntico a hoy.
- [ ] Crear MR (GitLab) y PR (ADO) desde la UI con confirm; GET muestra
      `pipeline_status` real en ambos.
- [ ] Merge imposible sin `confirm:true` server-side + checkbox literal en UI.
- [ ] ADO sin definition ⇒ `ado_definition_missing` con CTA y ensure con confirm.
- [ ] Conflictos/policies del tracker ⇒ error visible con el mensaje real (nunca
      500 genérico ni éxito falso).
- [ ] Arista `PRODUCTION → PANEL` en `_REQUIRES_MAP_FROZEN` y
      `test_harness_flags_requires.py` verde [C1].
- [ ] Modal de commit: opción ADO gobernada por `ado_commit_supported`, NO por
      `production_enabled` [C2].
- [ ] Paso 4 post-merge "Correr pipeline en la default" visible y reusando
      `/api/ci` existente [ADICIÓN ARQUITECTO].
- [ ] Tests registrados en ambos scripts de ratchet.

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Push ADO malformado (refUpdates/oldObjectId) rompe la rama | Cuerpos EXACTOS fijados en F1 + tests de body byte a byte + rama nueva vía POST refs previo |
| Divergencia de vocabulario de status ADO↔GitLab rompe la UI del 87 | `_map_status` con tabla literal + test parametrizado de los 6 estados |
| Merge con policies ADO (reviewers requeridos) | El PATCH falla con el mensaje de policy ⇒ visible en UI con link al PR (el operador resuelve en la web si su org lo exige — degradación honesta, no bypass) |
| MR duplicado (ya existe para esa rama) | TrackerApiError propagado con mensaje del tracker + link; v1 no auto-detecta |
| `pipeline_generator.py` cambiaría de contrato | NO se toca: el 501 muere solo al implementar commit_file; test de integración F1 lo verifica |
| Habilitar ADO en el modal antes de F1 implementado | El enable está atado a la capability `ado_commit_supported` del health (solo existe en builds que incluyen F1) — contra un backend viejo el modal no cambia [C2] |
| Polling del MR martilla el tracker | Tope 60 polls + pausa con `document.hidden` + botón manual [C5] |
| PAT sin scope Code RW / Build RX | TrackerApiError con status real ⇒ UI muestra el error; scopes en PlainHelp |
| Auto-merge accidental | No existe camino: merge requiere confirm server-side + checkbox; sin scheduling |

## 6. Fuera de scope (v1)

- Merge-when-pipeline-succeeds / auto-merge diferido (HITL estricto v1).
- Borrado de la source branch post-merge (deleteSourceBranch:false fijo).
- Resolución de conflictos desde la UI (link al tracker).
- Políticas de branch (reviewers, checks) — se respetan las del tracker, no se
  configuran desde Stacky.
- Multi-repo ADO por proyecto (v1 usa `_resolve_repo_id` — config → único →
  error honesto `ado_repo_ambiguous` [C3]).
- PR validation builds de ADO (`refs/pull/{id}/merge` por branch policy): el
  `pipeline_status` del PR muestra el build de la source branch; el de policy se
  ve en la web del PR vía link [C7].

## 7. Glosario

- **MR/PR**: Merge Request (GitLab) / Pull Request (ADO) — misma idea, dos APIs.
- **Pushes API (ADO)**: endpoint de commits programáticos
  (`_apis/git/repositories/{id}/pushes`).
- **Runs API (ADO)**: `_apis/pipelines/{definitionId}/runs` — dispara un run del
  pipeline YAML.
- **Pipeline definition (ADO)**: registro del pipeline que apunta al YAML del
  repo; GitLab no lo necesita (file-based).
- **`_map_status`**: tabla ADO(status,result)→vocabulario GitLab para que la UI
  del 87 no cambie.
- **noFastForward**: estrategia de merge ADO que crea merge commit (default v1).

## 8. Orden de implementación

1. F0 — flag (5 patas).
2. F1 — paridad ADO: commit_file + definitions + trigger/monitor/last_pipeline
   (con no-regresión 72/73).
3. F2 — sub-puerto MR/PR + adapters.
4. F3 — blueprint production + health key.
5. F4 — `productionModel.ts` + `ProductionFlow` + modal de commit ADO habilitado.
6. F5 — cierre.

## 9. Definición de Hecho (DoD)

- 40 tests backend nombrados (F0:5, F1:14 [C4: conteo verificado — 5 commit +
  1 resolve_repo_id + 3 ensure + 2 trigger + 1 monitor + 1 last + 1 integración],
  F2:10, F3:11) verdes por archivo con el venv; no-regresión 72/73/87 +
  meta-tests + `test_harness_flags_requires.py` [C1] verdes.
- Vitest F4 verde (4 tests); `tsc` 0 errores.
- ADO E2E real: commit → MR/PR → pipeline visible → merge, todo desde el panel
  (verificación manual binaria contra un proyecto ADO de prueba).
- GitLab E2E intacto y con el mismo flujo nuevo.
- HITL: cero mutaciones sin confirm server-side.
- Flag OFF ⇒ flujo MR/PR invisible y modal idéntico a hoy; `DevOpsPage.tsx` sin
  cambios.
