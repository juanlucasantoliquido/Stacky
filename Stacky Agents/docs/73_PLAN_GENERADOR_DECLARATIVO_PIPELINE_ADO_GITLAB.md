# Plan 73 — Generador declarativo de pipelines ADO ↔ GitLab (PipelineSpec puro)

> **Estado:** PROPUESTO v1.
> **Pre-requisito:** Plan 72 (trigger/monitor implementado) **Y** Plan 74 (migrador ADO→GitLab, que estresa el contract del `PipelineSpec` con casos reales). — **Este plan se hace DESPUÉS de 74.**
> **Roadmap:** Cuarto eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer → trigger CI → **creador pipelines** → migrador → deep links → eval). Nota de orden: el boceto del roadmap colocaba 73 antes que 74; la dependencia contractual (el spec madura con el migrador) **invierte el orden de implementación**: 74 antes que 73.
> **Versión doc:** v1 (2026-06-27).
> **Dependencias:** Plan 72 (duro); Plan 74 (duro — stress-testing del `PipelineSpec`); Plan 70/71 (transitivos).

> **CHANGELOG boceto v0 → v1:**
> - **[DECISIÓN ARQUITECTÓNICA HEREDADA]** Este plan **NO extiende `CIProvider`**. `PipelineSpec` es un dataclass PURA tracker-agnóstico; los renderers son funciones puras; el commit del YAML usa `commit_file(path, content, branch, message)`, método que pertenece a un sub-puerto **`RepoWriter`** distinto de `CIProvider` (principio ISP: escribir archivos al repo no es responsabilidad del sub-puerto de CI). `RepoWriter` queda **fuera de scope del bloque 71-73**; este plan declara la dependencia en F4 y la marca como `[a implementar — NO es parte de CIProvider]`.
> - **[SUBSET EXPLÍCITO]** F0 documenta la matriz de features soportadas por `PipelineSpec` v1 y el escape hatch (`raw_yaml`) para lo no cubierto. Esto resuelve el supuesto crítico del boceto ("¿qué cae fuera?").
> - **[ORDEN CORREGIDO]** 73 se implementa DESPUÉS de 74 (el migrador revela gaps del spec con pipelines ADO reales); documentado en cabecera y sección dependencias.

---

## 1. Objetivo y KPI

Un `PipelineSpec` (dataclass puro, tracker-agnóstico) que se **renderiza** a YAML ADO (`azure-pipelines.yml`) o GitLab (`.gitlab-ci.yml`), con validación determinista, y se **commitea** vía la API del tracker con HITL explícito del operador. Hace que crear/migrar un pipeline sea trivial y robusto desde Stacky.

**KPI global (DoD):** el operador describe un pipeline una vez (UI o YAML del spec) y obtiene YAML válido para ADO y GitLab, commiteado en el repo, idempotente, con `STACKY_PIPELINE_GENERATOR_ENABLED=true` y `confirm=True` explícito en el commit.

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy:

- No existe en `backend/` ningún módulo `pipeline_spec` ni renderers a YAML. Los pipelines se escriben a mano en YAML ADO o GitLab, duplicando conocimiento y sin validación hasta runtime.
- Migrar pipelines ADO↔GitLab a mano es el trabajo más tedioso y error-prone del roadmap GitLab; el Plan 74 (migrador) necesita un `PipelineSpec` como contract compartido para no duplicar lógica de render.
- Los Planes 71/72 sólo consumen CI pre-existente; no crean pipelines. Este plan cierra la creación declarativa.
- Un `PipelineSpec` puro permite validación determinista (schema), diff/preview, y reutilización por el Plan 74.

---

## 3. Principios y guardarraíles (heredados + HITL en commit)

- **HITL innegociable (en commit):** el commit del YAML al repo exige `confirm=True` explícito del operador (mismo riel que Plan 72). Default a feature branch + Merge Request (no directo a default branch sin guard).
- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API/UI; NO toca prompts ni runtime del agente.
- **Cero trabajo extra al operador:** flag opt-in `STACKY_PIPELINE_GENERATOR_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI").
- **No degradar / backward-compatible:** flag OFF = sin rutas registradas; ningún comportamiento existente cambia.
- **TDD + funciones PURAS + ratchet + no falsos verdes.** Los renderers y el validador son **puros** (sin I/O); el round-trip test es la guardia anti-divergencia silenciosa entre ADO y GitLab.
- **Mono-operador sin auth:** el PAT para commitear requiere scope `api` en GitLab (heredado del Plan 72 F0) y `Code.Write` en ADO.

---

## 4. Fases

### F0 — `PipelineSpec` (dataclass puro) + matriz de features soportadas

**Objetivo:** definir el dataclass puro y el subset v1. Resuelve el supuesto crítico del boceto.

**Archivos exactos F0:**
- `services/pipeline_spec.py` — **archivo nuevo** (dataclass + tipos).

**Símbolos exactos F0 (dataclass FIJADO, sin deps de ADO ni GitLab):**

```python
# services/pipeline_spec.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class Step:
    name: str
    script: str                 # bash/script multi-línea
    working_directory: Optional[str] = None
    condition: Optional[str] = None   # expresión cruda (ej. "eq(variables['Build.SourceBranchName'], 'main')")
    env: dict = field(default_factory=dict)

@dataclass(frozen=True)
class Job:
    name: str
    steps: tuple[Step, ...]
    image: Optional[str] = None        # GitLab image; ADO: pool vmImage
    pool_vm_image: Optional[str] = None   # ADO-specific (ej. "ubuntu-latest")
    runner_tags: tuple[str, ...] = ()     # GitLab tags / ADO demands
    variables: dict = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()       # paths a artifacts (sin cache)
    services: tuple[str, ...] = ()        # GitLab services / ADO container jobs — v1 solo lista de nombres

@dataclass(frozen=True)
class Stage:
    name: str
    jobs: tuple[Job, ...]
    condition: Optional[str] = None

@dataclass(frozen=True)
class PipelineSpec:
    name: str
    stages: tuple[Stage, ...]
    variables: dict = field(default_factory=dict)
    trigger_branches: tuple[str, ...] = ()   # branches que disparan el pipeline
    raw_yaml: Optional[str] = None           # ESCAPE HATCH: para features no cubiertas
    raw_yaml_target: Optional[str] = None    # "ado" | "gitlab" | None (a qué tracker aplica el raw)

    def validate(self) -> list["ValidationError"]:
        return _validate_spec(self)   # función PURA (F3)
```

**Matriz de features v1 (resuelve supuesto crítico del boceto):**

| Feature ADO | Feature GitLab | Cobertura v1 | Nota |
|---|---|---|---|
| `stages` + `jobs` + `steps` | `stages` + `jobs` + `script` | **SÍ** | núcleo común. |
| `pool.vmImage` | `image:` | **SÍ** | `Job.pool_vm_image` / `Job.image`; cada renderer elige su campo. |
| `variables` (pipeline + job) | `variables` (global + job) | **SÍ** | dict simple string→string. |
| `condition` en step/job/stage | `rules`/`only/except` | **PARCIAL** | se renderiza como `condition` ADO y como `rules: if` simplificado en GitLab (sin `changes:`/`exists:`). |
| `trigger: branches` | flujo default de GitLab (push dispara) | **SÍ** | `trigger_branches` → ADO explícito; GitLab se omite (push es default). |
| `runner tags`/`demands` | `tags` | **SÍ** | `Job.runner_tags`. |
| `artifacts: paths` | `artifacts: paths` | **SÍ** | lista de paths simples. |
| `services` (service containers) | `services:` | **PARCIAL** | lista de nombres sólo; sin healthcheck/variables complejas. |
| **Templates ADO** (`template:`) | — | **NO** | fuera de scope v1; usar `raw_yaml` si se necesita. |
| — | **`extends:`/`include:` GitLab** | **NO** | fuera de scope v1; `raw_yaml`. |
| **`strategy.matrix` dinámica** | `matrix:` dinámica | **NO** | fuera de scope v1; `raw_yaml`. |
| **Environments / deployments** | **environments** | **NO** | fuera de scope v1. |
| **Caches complejos** | **cache:** con keys/policy | **NO** | fuera de scope v1; sólo artifact paths simples. |

**Escape hatch `raw_yaml`:** si un pipeline necesita templates/matriz/environments, el operador setea `raw_yaml="..."` y `raw_yaml_target="gitlab"` (o `"ado"`); el renderer del tracker correspondiente emite el `raw_yaml` crudo sin transformar. El renderer del OTRO tracker lanza `ValidationError` ("raw_yaml target=gitlab no portable a ado") — sin divergencia silenciosa.

**Tests F0:**
- Archivo: `backend/tests/test_plan73_pipeline_spec.py`.
- Casos:
  1. Construir `PipelineSpec` mínimo (1 stage, 1 job, 1 step) sin `raw_yaml`.
  2. Construir con `raw_yaml="..."` y `raw_yaml_target="gitlab"`.
  3. `Step.script` acepta multi-línea.
  4. Todos los dataclass son `frozen`.
  5. `PipelineSpec.validate` existe y retorna lista (vacía para spec mínimo válido).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_pipeline_spec.py -q`.

**Criterio binario F0:** los 5 casos pasan; `pipeline_spec.py` NO importa nada de ADO ni GitLab (sólo `typing`/`dataclasses`).

**Trabajo del operador F0:** ninguno.

---

### F1 — Renderer `to_ado_yaml(spec) -> str` (función PURA)

**Objetivo:** convertir `PipelineSpec` a YAML ADO válido (`azure-pipelines.yml`).

**Archivos exactos F1:**
- `services/pipeline_renderers.py` — **archivo nuevo** (funciones puras `to_ado_yaml`, `to_gitlab_yaml`).
- Usa `yaml.safe_dump` (PyYAML — verificar disponibilidad en F1 setup).

**Símbolos exactos F1:**

```python
# services/pipeline_renderers.py
def to_ado_yaml(spec: PipelineSpec) -> str:
    """Convierte PipelineSpec a azure-pipelines.yml. PURA (sin I/O)."""
    if spec.raw_yaml and spec.raw_yaml_target == "ado":
        return spec.raw_yaml
    if spec.raw_yaml and spec.raw_yaml_target != "ado":
        raise ValidationError(f"raw_yaml target={spec.raw_yaml_target} no portable a ado")
    doc = _spec_to_ado_doc(spec)   # PURA: spec -> dict YAML-ready
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
```

**Mapeo ADO (F1):**
- `PipelineSpec.trigger_branches` → `trigger: branches: include: [...]`.
- `Stage` → `stage`; `Job` → `job`; `Step` → `script` con `displayName`.
- `Job.pool_vm_image` → `pool: vmImage: ...`.
- `Job.variables` → `variables:` dict.
- `Step.condition` → `condition:` crudo.
- `Job.artifacts` → `publish`/`download` (v1: `publish: <path>` con `artifact:`).

**Tests F1:**
- Archivo: `backend/tests/test_plan73_render_ado.py`.
- Casos:
  1. Spec mínimo → YAML contiene `stages:`, un `- stage:`, un `- job:`, un `- script:`.
  2. `trigger_branches=("main","develop")` → YAML contiene `trigger:` con `include: [main, develop]`.
  3. `Job.pool_vm_image="ubuntu-latest"` → YAML contiene `pool:` y `vmImage: ubuntu-latest`.
  4. `raw_yaml="custom"`, `raw_yaml_target="ado"` → retorna `"custom"` literal.
  5. `raw_yaml_target="gitlab"` → lanza `ValidationError`.
  6. El YAML producido parsea de vuelta con `yaml.safe_load` (sin errores).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_render_ado.py -q`.

**Criterio binario F1:** los 6 casos pasan; `to_ado_yaml` es pura (sin I/O).

**Trabajo del operador F1:** ninguno.

---

### F2 — Renderer `to_gitlab_yaml(spec) -> str` (función PURA)

**Objetivo:** convertir `PipelineSpec` a `.gitlab-ci.yml` válido.

**Archivos exactos F2:**
- `services/pipeline_renderers.py` — agregar `to_gitlab_yaml(spec)`.

**Símbolos exactos F2:**

```python
def to_gitlab_yaml(spec: PipelineSpec) -> str:
    if spec.raw_yaml and spec.raw_yaml_target == "gitlab":
        return spec.raw_yaml
    if spec.raw_yaml and spec.raw_yaml_target != "gitlab":
        raise ValidationError(f"raw_yaml target={spec.raw_yaml_target} no portable a gitlab")
    doc = _spec_to_gitlab_doc(spec)
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
```

**Mapeo GitLab (F2):**
- `PipelineSpec.stages` → lista de nombres en `stages:`; cada `Stage.jobs` se vuelca al root del doc con `<job_name>:` y `stage: <stage_name>`.
- `Job.image` → `image: ...`; `Job.pool_vm_image` → si `image` es None, mapeo `ubuntu-latest`→`ubuntu:latest` (convención).
- `Job.runner_tags` → `tags: [...]`.
- `Job.variables` → `variables:` por job.
- `Step.script` → `script:` (lista de líneas o string multi-línea).
- `Step.condition` → `rules: [{if: "<condición traducida>"}]` simplificado (traducción básica ADO→GitLab; lo no traducible → `ValidationError` con `raw_yaml` sugerido).
- `Job.artifacts` → `artifacts: paths: [...]`.
- `Job.services` → `services: [...]`.
- `trigger_branches` → omitido (GitLab dispara por push por defecto).

**Tests F2:**
- Archivo: `backend/tests/test_plan73_render_gitlab.py`.
- Casos:
  1. Spec mínimo → YAML contiene `stages:`, un job con `stage:`, `script:`.
  2. `Job.image="python:3.11"` → YAML contiene `image: python:3.11`.
  3. `Job.runner_tags=("docker","linux")` → YAML contiene `tags: [docker, linux]`.
  4. `Job.artifacts=("dist/","*.whl")` → YAML contiene `artifacts:` y `paths:`.
  5. `Step.condition="eq(variables['Build.SourceBranchName'], 'main')"` → traducido a `rules: [{if: '$CI_COMMIT_BRANCH == "main"'}]`.
  6. `Step.condition` intraducible (ej. referencias ADO internas) → `ValidationError`.
  7. `raw_yaml` con `target="gitlab"` → retorna literal; con `target="ado"` → `ValidationError`.
  8. YAML produce parsea de vuelta.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_render_gitlab.py -q`.

**Criterio binario F2:** los 8 casos pasan; `to_gitlab_yaml` es pura.

**Trabajo del operador F2:** ninguno.

---

### F3 — Validador determinista `validate(spec) -> list[ValidationError]` (función PURA)

**Objetivo:** schema check determinista (sin LLM) antes de renderizar o commitear.

**Archivos exactos F3:**
- `services/pipeline_renderers.py` — `_validate_spec(spec) -> list[ValidationError]` (aunque viva en `renderers`, es independiente de los renderers; o bien mover a `pipeline_spec.py` — decisión del implementador, preferir `pipeline_spec.py` para cohesión).

**Símbolos exactos F3:**

```python
@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str

def _validate_spec(spec: PipelineSpec) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not spec.name.strip():
        errors.append(ValidationError("name", "name vacío"))
    if not spec.stages:
        errors.append(ValidationError("stages", "sin stages"))
    for i, st in enumerate(spec.stages):
        if not st.jobs:
            errors.append(ValidationError(f"stages[{i}].jobs", "stage sin jobs"))
        for j, jb in enumerate(st.jobs):
            if not jb.steps:
                errors.append(ValidationError(f"stages[{i}].jobs[{j}].steps", "job sin steps"))
            for k, step in enumerate(jb.steps):
                if not step.script.strip():
                    errors.append(ValidationError(f"stages[{i}].jobs[{j}].steps[{k}].script", "step sin script"))
    if spec.raw_yaml and spec.raw_yaml_target not in ("ado", "gitlab", None):
        errors.append(ValidationError("raw_yaml_target", f"target inválido: {spec.raw_yaml_target}"))
    return errors
```

**Tests F3:**
- Archivo: `backend/tests/test_plan73_validate.py`.
- Casos:
  1. Spec válido → lista vacía.
  2. `name=""` → 1 error con `field="name"`.
  3. `stages=()` → error `field="stages"`.
  4. Stage sin jobs → error `field="stages[0].jobs"`.
  5. Job sin steps → error.
  6. Step con script vacío → error.
  7. `raw_yaml_target="invalid"` → error.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_validate.py -q`.

**Criterio binario F3:** los 7 casos pasan; `_validate_spec` es pura.

**Trabajo del operador F3:** ninguno.

---

### F4 — Commit del YAML vía sub-puerto `RepoWriter` (declaración de dependencia, NO extiende `CIProvider`)

**Objetivo:** commitear el YAML renderizado al repo del tracker. **NO se extiende `CIProvider`**; el commit usa un método `commit_file` que pertenece a un sub-puerto **`RepoWriter`** distinto (principio ISP: escribir archivos al repo no es CI).

**Archivos exactos F4:**
- `services/repo_writer.py` — **archivo nuevo** (sub-puerto `RepoWriter(Protocol)` + adapters ADO/GitLab).
- `services/gitlab_provider.py` — agregar `commit_file(path, content, branch, message)` que use la [GitLab Commits API](https://docs.gitlab.com/ee/api/commits.html) `POST /projects/:id/repository/commits` con `actions=[{action:"create"|"update", file_path, content}]`.
- `services/ado_provider.py` — `commit_file` ADO via [Git Push/Refs API](https://learn.microsoft.com/en-us/rest/api/azure/devops/git/) (en v1 puede lanzar `NotImplementedError` si la adopción es GitLab-first; documentar).

**Símbolos exactos F4 (sub-puerto NUEVO, separado de CIProvider):**

```python
# services/repo_writer.py
@runtime_checkable
class RepoWriter(Protocol):
    name: str
    def commit_file(self, path: str, content: str, branch: str, message: str) -> dict: ...

REPO_WRITER_METHODS = ("commit_file",)

def get_repo_writer(project: Optional[str] = None) -> RepoWriter: ...   # fábrica espejo
```

```python
# services/gitlab_provider.py — nuevo método:
def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
    """POST /projects/:id/repository/commits — crea/actualiza archivo en 1 commit."""
    proj_path = self._client._project_path()
    # Detectar si el archivo ya existe para elegir action create vs update
    action = self._detect_commit_action(path, branch)   # "create" | "update"
    body, status = self._client._request(
        "POST", f"/projects/{proj_path}/repository/commits",
        json_body={"branch": branch, "commit_message": message,
                   "actions": [{"action": action, "file_path": path, "content": content}]},
    )
    if status == 403:
        raise TrackerApiError(403, "403 GitLab commit: PAT sin scope 'api'", kind="forbidden")
    return {"sha": body.get("id") or "", "branch": branch, "path": path, "web_url": body.get("web_url","")}
```

**Idempotencia commit F4:** si `content` no cambió vs el archivo existente (mismo hash), retornar success sin commit (git NO crea commit vacío). `_detect_commit_action` lee el archivo actual y compara SHA.

**Tests F4:**
- Archivo: `backend/tests/test_plan73_repo_writer.py`.
- Casos:
  1. `RepoWriter` con `commit_file` pasa `isinstance(stub, RepoWriter)`.
  2. `GitLabTrackerProvider.commit_file("ci.yml", "content", "main", "msg")` construye POST con `actions=[{action:"create"|"update", ...}]` **[Patrón mock sobre `_request`]**.
  3. 403 → `TrackerApiError(403)`.
  4. Idempotencia: si el archivo ya tiene el mismo contenido → no se llama a `_request` (mock `_request.assert_not_called()`).
  5. `AdoTrackerProvider.commit_file` → `NotImplementedError` (v1 GitLab-first) O implementación real (decisión del implementador; si ADO no se cubre, documentar 501).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_repo_writer.py -q`.

**Criterio binario F4:** los 5 casos pasan; `RepoWriter` es independiente de `CIProvider`.

> **Nota contractual:** `commit_file` NO se agrega a `CIProvider`. Es un sub-puerto separado. Esto respeta ISP y mantiene `CI_PORT_METHODS` con sus 3 métodos (`infer_item_pipeline`, `monitor_pipeline`, `trigger_pipeline` — ver Plan 72 F1).

**Trabajo del operador F4:** ninguno.

---

### F5 — Endpoint API con HITL + UI de editor + preview lado-a-lado

**Objetivo:** endpoint `POST /api/pipeline-generator/preview` (puro, sin commit) y `POST /api/pipeline-generator/commit` (con HITL `confirm=True`); UI con editor del spec + preview ADO|GitLab.

**Archivos exactos F5:**
- `api/pipeline_generator.py` — **blueprint nuevo** con endpoints `POST /preview` y `POST /commit`.
- `app.py` — registrar `pipeline_generator_bp` gated por `STACKY_PIPELINE_GENERATOR_ENABLED`.
- `config.py` — `STACKY_PIPELINE_GENERATOR_ENABLED: bool = False`.
- `harness_defaults.env` — `STACKY_PIPELINE_GENERATOR_ENABLED=false`.
- `frontend/src/components/PipelineGeneratorPanel.tsx` — **nuevo**: editor del spec (formulario minimal + YAML spec), preview lado-a-lado (ADO | GitLab), botón "Commitear" con modal HITL.

**Símbolos exactos F5 (endpoint preview — PURA):**

```python
@bp.post("/preview")
def preview_route():
    if not config.STACKY_PIPELINE_GENERATOR_ENABLED:
        abort(404)
    body = request.get_json(silent=True) or {}
    spec = _dict_to_spec(body)   # PURA
    errors = spec.validate()
    if errors:
        return jsonify({"errors": [e.__dict__ for e in errors]}), 400
    return jsonify({"ado": to_ado_yaml(spec), "gitlab": to_gitlab_yaml(spec)})
```

**Símbolos exactos F5 (endpoint commit — HITL absoluto):**

```python
@bp.post("/commit")
def commit_route():
    if not config.STACKY_PIPELINE_GENERATOR_ENABLED:
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400   # RIEL ABSOLUTO
    spec = _dict_to_spec(body)
    errors = spec.validate()
    if errors:
        return jsonify({"errors": [...]}), 400
    target = body.get("target")   # "ado" | "gitlab"
    yaml_str = to_ado_yaml(spec) if target == "ado" else to_gitlab_yaml(spec)
    path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"
    branch = body.get("branch") or f"feature/pipeline-{spec.name}"
    writer = get_repo_writer(body.get("project"))
    result = writer.commit_file(path=path, content=yaml_str, branch=branch,
                                message=f"pipeline({spec.name}): update via Stacky")
    return jsonify(result)
```

**Tests F5:**
- Archivo: `backend/tests/test_plan73_generator_endpoint.py`.
- Casos:
  1. Flag OFF → `/preview` y `/commit` 404.
  2. `/preview` con spec válido → 200 con `ado` y `gitlab` strings.
  3. `/preview` con spec inválido (name vacío) → 400 con `errors`.
  4. `/commit` sin `confirm` → **400** (HITL gate — test VP).
  5. `/commit` con `confirm=True` → llama `writer.commit_file` **[Patrón mock: assert_called]**; response con `sha`, `branch`, `web_url`.
  6. `/commit` con `target="gitlab"` produce `.gitlab-ci.yml` y `branch="feature/pipeline-X"` por default.
  7. Validación de PAT scope `api` antes del commit (espejo Plan 72 F0).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_generator_endpoint.py -q`.

**Criterio binario F5:** los 7 casos pasan. **Caso 4 es gate HITL.**

**UI tests F5:**
- Archivo: `frontend/src/components/__tests__/PipelineGeneratorPanel.test.tsx` (vitest si disponible).
- Casos:
  1. Editor muestra campos name/stages/jobs/steps.
  2. Preview se actualiza al editar; lado ADO y lado GitLab.
  3. Botón "Commitear" abre modal con `target`, `branch`, warning.
  4. Clic "Confirmar" en modal → POST `/commit` con `confirm=true`.
  5. Response `sha` → toast success con link `web_url`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` (+ vitest si disponible).

**Trabajo del operador F5:** opt-in (default OFF); para usar, prender flag + confirmar PAT scope `api` + clic en modal.

---

### F6 — Round-trip test (idempotencia semántica) + ratchet

**Objetivo:** guardia anti-divergencia silenciosa: spec → YAML → parse → spec produce el mismo spec (semánticamente). Es el test más importante del plan.

**Archivos exactos F6:**
- `services/pipeline_renderers.py` — agregar `parse_ado_yaml(yaml_str) -> PipelineSpec` y `parse_gitlab_yaml(yaml_str) -> PipelineSpec` (funciones PURAS, inversas de los renderers).
- `backend/tests/test_plan73_round_trip.py` — **nuevo**.

**Símbolos exactos F6:**

```python
# Round-trip property test:
def test_round_trip_ado_preserves_spec():
    spec = _fixture_spec()   # spec canónico con stages/jobs/steps
    yaml_str = to_ado_yaml(spec)
    parsed = parse_ado_yaml(yaml_str)
    assert _specs_equivalent(spec, parsed)   # comparación semántica (no string-exacta)

def test_round_trip_gitlab_preserves_spec():
    spec = _fixture_spec()
    yaml_str = to_gitlab_yaml(spec)
    parsed = parse_gitlab_yaml(yaml_str)
    assert _specs_equivalent(spec, parsed)
```

**Tests F6:**
- Archivo: `backend/tests/test_plan73_round_trip.py`.
- Casos:
  1. Round-trip ADO preserva spec (stages, jobs, steps, variables, trigger_branches, pool).
  2. Round-trip GitLab preserva spec.
  3. Round-trip con `raw_yaml` target="gitlab" → el YAML GitLab parsea de vuelta; el ADO renderer lanza `ValidationError` (no diverge silenciosamente).
  4. `_specs_equivalent` cubre campos opcionales None vs default.
  5. Fixtures cubren: spec mínimo, spec con variables, spec con artifacts, spec con condition traducible.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q`.

**Ratchet F6:** registrar TODOS los `test_plan73_*.py` en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49.

**Criterio binario F6:** los 5 casos pasan; ratchet verde; flag aparece en `harness_defaults.env` y UI.

**Trabajo del operador F6:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Subset demasiado chico o demasiado grande** (R1 boceto). **Mitigación:** F0 matriz explícita; `raw_yaml` escape hatch para features no cubiertas; round-trip F6 detecta divergencia silenciosa.
2. **Commitear al default branch sin guard** (R2). **Mitigación:** HITL `confirm=True` (F5 caso 4 gate); default a feature branch + MR; el endpoint no commitea a `main` sin `branch` explícito override del operador.
3. **Renderers que divergen silenciosamente** (ADO válido, GitLab roto) (R3). **Mitigación:** F6 round-trip property en ambos trackers; cualquier divergencia se detecta en CI antes de merge.
4. **Spec creep** (parsear TODO ADO/GitLab) (R4). **Mitigación:** sección 6 fuera de scope explícita; `raw_yaml` desvía los casos no cubiertos.
5. **Traducción `condition` ADO→GitLab incompleta** (R5). **Mitigación:** F2 caso 6: traducción intraducible lanza `ValidationError` con sugerencia `raw_yaml`; nunca emite YAML silenciosamente roto.
6. **PyYAML no disponible.** **Mitigación:** F1 setup verifica `import yaml`; si no, agregar a `requirements.txt` (cambio mínimo).
7. **3 runtimes.** **Mitigación:** el plan no toca prompts/runtime del agente.

---

## 6. Fuera de scope

- **NO** parseo inverso YAML → spec para pipelines arbitrarios complejos (sólo el subset v1 cubierto por F6 round-trip; el migrador Plan 74 maneja pipelines reales).
- **NO** templates/herencia compleja ADO (`extends:`/`include:` GitLab, `template:` ADO) — usar `raw_yaml`.
- **NO** matrix dinámica.
- **NO** environments/deployments.
- **NO** caches complejos (con keys/policy).
- **NO** ejecución local de pipelines.
- **NO** validación contra runner real (sólo schema determinista).
- **NO** extender `CIProvider` (el commit usa sub-puerto `RepoWriter` separado).
- **NO** migración ADO→GitLab (Plan 74 — éste plan le provee el contract).

---

## 7. Glosario

- **PipelineSpec:** dataclass PURA (`services/pipeline_spec.py`, F0) que describe un pipeline tracker-agnóstico. Tiene `stages`, `jobs`, `steps`, `variables`, `trigger_branches`, `raw_yaml`.
- **CIProvider:** sub-puerto creado en Plan 71, extendido en Plan 72 con `trigger_pipeline`. **Este plan NO lo toca.**
- **RepoWriter:** nuevo sub-puerto (`services/repo_writer.py`, F4) con método `commit_file`. Separado de `CIProvider` por ISP.
- **`to_ado_yaml` / `to_gitlab_yaml`:** funciones PURAS renderers (`services/pipeline_renderers.py`, F1/F2).
- **`parse_ado_yaml` / `parse_gitlab_yaml`:** funciones PURAS inversas (F6).
- **`_validate_spec`:** función PURA de validación determinista (F3).
- **`raw_yaml` + `raw_yaml_target`:** escape hatch para features no cubiertas; el renderer del tracker target emite el crudo, el otro lanza `ValidationError`.
- **`ValidationError`:** dataclass `(field, message)` retornado por `_validate_spec`.
- **Round-trip test:** guardia anti-divergencia ADO↔GitLab (F6).
- **`STACKY_PIPELINE_GENERATOR_ENABLED`:** flag nueva de este plan (default OFF, editable por UI).

---

## 8. Orden de implementación

1. **F0** — `PipelineSpec` + matriz de features v1 + escape hatch.
2. **F1** — `to_ado_yaml` (pura).
3. **F2** — `to_gitlab_yaml` (pura).
4. **F3** — `_validate_spec` (pura).
5. **F4** — Sub-puerto `RepoWriter` + `commit_file` GitLab (ADO opcional v1).
6. **F5** — Endpoints `/preview` y `/commit` con HITL + UI editor+preview.
7. **F6** — Round-trip test + `parse_*_yaml` + ratchet.

> **Orden DEPENDENCIAS:** este plan se implementa DESPUÉS de 74 (el migrador estresa el `PipelineSpec` y revela gaps de subset antes de que se congele el contract).

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** `PipelineSpec` definido como dataclass PURA sin deps de ADO/GitLab (F0); matriz de features documentada.
- [ ] **(b)** `to_ado_yaml` y `to_gitlab_yaml` implementadas y testeadas (F1/F2); producen YAML que parsea de vuelta.
- [ ] **(c)** `_validate_spec` implementada (F3); todos los casos de error cubiertos.
- [ ] **(d)** Sub-puerto `RepoWriter` creado (F4); `commit_file` GitLab funciona; ADO declarado v1 (real o `NotImplementedError` 501 claro).
- [ ] **(e)** Endpoint `/preview` PURA (sin I/O); `/commit` con HITL `confirm=True` gate (F5 caso 4 — gate de significancia).
- [ ] **(f)** UI `PipelineGeneratorPanel` con editor + preview lado-a-lado + modal HITL; `tsc --noEmit` 0 errores.
- [ ] **(g)** Round-trip test verde en ambos trackers (F6) — anti-divergencia silenciosa.
- [ ] **(h)** Flag `STACKY_PIPELINE_GENERATOR_ENABLED` default **OFF**; flag OFF → 404.
- [ ] **(i)** `raw_yaml` escape hatch funcional; el renderer no-target lanza `ValidationError`.
- [ ] **(j)** Los 3 runtimes operativos sin cambios.
- [ ] **(k)** Ratchet verde (Plan 49 F4) con los archivos `test_plan73_*.py` registrados.
- [ ] **(l)** PipelineSpec ya stress-testeado por el Plan 74 (migrador) antes de congelar v1.

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`.
- **PyYAML:** verificar `python -c "import yaml"` en F1 setup; si no, agregar `pyyaml` a `requirements.txt`.
- **Patrón mock (FIX C4):** `mock_writer.commit_file.assert_called_once_with(path="...", content="...", branch="...", message="...")`. Para HITL gate: `mock_writer.commit_file.assert_not_called()` cuando `confirm` falta.
- **Mock pattern DB:** importar `db` a nivel módulo; parchear lazy-imports en el módulo origen.
- **Blueprint registration gated:** `if config.STACKY_PIPELINE_GENERATOR_ENABLED: app.register_blueprint(pipeline_generator_bp)` → flag OFF = 404.
- **Cada commit deja el sistema verde y backward-compatible.**
- **Falsos verdes prohibidos:** F5 caso 4 (HITL gate) y F6 round-trip son los gates críticos.
- **Si una fase revela un GAP no listado en F0 matriz**, detener, actualizar este doc y, si el subset cambia, re-auditar el round-trip F6.
- **Post-74:** cuando el migrador haya estresado el `PipelineSpec`, actualizar la matriz F0 con los features adicionales soportados y los gaps descubiertos antes de congelar v1.
