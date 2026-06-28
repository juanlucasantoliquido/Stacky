# Plan 73 — Generador declarativo de pipelines ADO ↔ GitLab (PipelineSpec puro)

> **Estado:** PROPUESTO v2 (crítica adversarial; verificada contra código real 2026-06-28). Veredicto v1 = **RECHAZADO** (4 bloqueantes: contrato `_request` mal usado, registro de blueprint con doble prefijo + gating en startup, orden de dependencias circular/invertido con Plan 74, dependencia DURA espuria sobre Plan 72). v2 los resuelve.
> **Pre-requisito REAL (corregido C3/C4):** Plan **65** (TrackerProvider GitLab base — **IMPLEMENTADO**: `services/gitlab_provider.py` + `services/ado_provider.py` con `self._client` y `_client._project_path()` ya existen). **NO** depende de Plan 71/72 (este plan no consume `CIProvider`/`ItemRef`/`get_ci_provider`/`trigger_pipeline`/`monitor_pipeline`). **NO** depende de que Plan 74 se implemente antes (es al revés: 73 provee el contract `PipelineSpec`/renderers que el Plan 74 consume para convertir pipelines — ver `74_PLAN...md:588`).
> **Roadmap:** Cuarto eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer → trigger CI → **creador pipelines** → migrador → deep links → eval). **Orden de implementación corregido (C3):** el **Bloque A** (F0-F3: `PipelineSpec` + renderers + validador, PUROS, sin deps) puede implementarse **YA, de forma independiente**, y el Plan 74 lo consume; el **Bloque B** (F4-F6: commit + UI + round-trip) sólo necesita el provider base del Plan 65.
> **Versión doc:** v2 (2026-06-28).
> **Dependencias:** Plan 65 (duro, ya implementado). Plan 74 es **consumidor** de este plan, no prerequisito.

> **CHANGELOG v1 → v2 (crítica adversarial; verificada contra código real):**
> - **[C1 BLOQUEANTE — contrato `_request` mal usado en F4 (repite el C1' ya corregido en Plan 72)]** El snippet `commit_file` v1 hacía `body, status = self._client._request(...)` y luego `if status == 403: raise TrackerApiError(403, ...)`. **Verificado (`gitlab_client.py:116,159`):** `_request` está anotado `-> tuple[object, dict]` (devuelve `(body, response_headers)`, NO un status int) y **ya lanza** `TrackerApiError(resp.status_code, ..., kind=...)` ante no-2xx (L159). El `status` del v1 sería el dict de headers (nunca `== 403`) y el `raise` está muerto (el 403 ya se lanzó). **Fix:** `body, _ = self._client._request(...)`; **no** comparar el 2º valor; dejar propagar `TrackerApiError`; el endpoint F5 la mapea a `e.status`. Idéntico al riel del Plan 72 (`72_PLAN...md:500,552`).
> - **[C2 BLOQUEANTE — registro de blueprint en `app.py` + gating en startup → doble prefijo `/api/api/...` y toggle UI roto (repite C1+C2' del Plan 72)]** F5 v1 decía "`app.py` — registrar `pipeline_generator_bp` gated por `STACKY_PIPELINE_GENERATOR_ENABLED`". **Verificado (`api/__init__.py:43-82`):** `api_bp = Blueprint("api", __name__, url_prefix="/api")` y **TODOS** los sub-blueprints se registran sobre `api_bp` en `api/__init__.py` (ninguno en `app.py`). Un blueprint con `url_prefix="/api/pipeline-generator"` registrado bajo `api_bp` daría **`/api/api/pipeline-generator`** (404). Y "gated en el registro" rompe el toggle por UI (la flag no surte efecto sin reiniciar). **Fix:** `bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")`, importado y registrado en `api/__init__.py` sobre `api_bp` (ruta final `/api/pipeline-generator/...`), **registrado SIEMPRE** (no gated); el guard de la flag es **per-request** (`abort(404)` dentro de cada endpoint). + **[ADICIÓN ARQUITECTO v2]** test centinela de rutas reales.
> - **[C3 BLOQUEANTE — orden de dependencias circular/invertido con Plan 74]** v1 afirmaba "este plan se hace DESPUÉS de 74 (74 estresa el spec)" pero §2/§6/DoD decían "74 necesita el PipelineSpec de 73 como contract". **Verificado (`74_PLAN...md:588`):** el Plan 74 lista los pipelines en su reporte pero **delega su conversión a 73** ("su conversión se hace con 73") → **73 provee el contract, 73 va antes (o en paralelo), nunca después**. **Fix:** invertida la cabecera y §8; eliminado "después de 74"; declarado que 74 es consumidor de 73.
> - **[C4 BLOQUEANTE — dependencia DURA sobre Plan 72 espuria]** v1 declaraba Plan 72 como prerequisito duro. **Verificado:** NINGUNA fase F0-F6 importa/usa `CIProvider`, `ItemRef`, `get_ci_provider`, `trigger_pipeline` ni `monitor_pipeline` (símbolos del 71/72). F4 usa un sub-puerto **propio** `RepoWriter` + `commit_file` sobre `services/gitlab_provider.py`/`services/ado_provider.py` (Plan 65, **ya existen**). Bloquear 73 hasta tener 72 (no implementado) era un auto-bloqueo sin causa. **Fix:** removida la dep dura sobre 72; dep real = Plan 65 (ya implementado).
> - **[C5 IMPORTANTE — `_dict_to_spec` sin fase/símbolo/test (ambiguo para modelo menor)]** F5 v1 invocaba `_dict_to_spec(body)` (deserializa JSON→dataclasses `frozen` anidados con tuplas y defaults) sin definirlo, sin test, sin símbolo. **Fix:** función PURA `dict_to_spec(d) -> PipelineSpec` añadida a F0 (`pipeline_spec.py`, por cohesión con el dataclass) con símbolo exacto y casos de test nombrados (listas JSON → tuplas; campos faltantes → defaults; `raw_yaml`/`raw_yaml_target`).
> - **[C6 IMPORTANTE — round-trip F6 sub-especificado y potencialmente tautológico/imposible por renders lossy]** Los renderers son lossy por diseño: `trigger_branches` se OMITE en GitLab (F2, L "trigger_branches → omitido"); `condition` se traduce parcial; `pool_vm_image` (ADO) vs `image` (GitLab) no son intercambiables. Un round-trip con un único fixture canónico y `_specs_equivalent` total sería **imposible de poner verde** (o se haría tautológico ignorando todo). **Fix:** F6 define `_CORE_ROUNDTRIP_FIELDS` (núcleo seguro) y `_LOSSY_BY_DESIGN` por tracker; fixtures **separados** por tracker (ADO-shaped usa `pool_vm_image`; GitLab-shaped usa `image`); `_specs_equivalent(a, b, ignore_fields=...)` excluye explícitamente los lossy con justificación documentada (no silenciosa).
> - **[C7 IMPORTANTE — idempotencia F4 inconsistente: el snippet siempre hace POST pero el test caso 4 exige `_request.assert_not_called()`]** El texto (v1 L326) y el test caso 4 pedían "no commit si el contenido no cambió", pero el snippet `commit_file` siempre llamaba `_request`. **Fix:** `commit_file` lee el contenido actual vía `_detect_commit_action` y **corta antes del POST** si es idéntico (retorna `status:"unchanged"` sin llamar `_request`).
> - **[C8 IMPORTANTE — `get_repo_writer` fábrica sin resolución de provider especificada]** F4 v1 declaraba `get_repo_writer(project)` "fábrica espejo" sin decir cómo elige ADO vs GitLab. **Fix:** reusa la **misma** resolución por `tracker_type` del proyecto que el Plan 65 (`project_manager.get_active_tracker_config`/equivalente); no inventa mecanismo nuevo.
> - **[C9 IMPORTANTE — flag sin `env_only=False` ni registro en FLAG_REGISTRY → regla dura "editable por UI" no garantizada]** **Fix:** F5 registra `STACKY_PIPELINE_GENERATOR_ENABLED` en `services/harness_flags.py` FLAG_REGISTRY con `env_only=False`, categoría "Pipelines / CI", default `False` (espejo exacto de Plan 72/74).
> - **[C10 MENOR — PyYAML ya está]** **Verificado (`requirements.txt:10`): `PyYAML==6.0.3`.** Eliminada la incertidumbre "verificar / si no agregar"; R6 pasa a "dependencia ya presente".
> - **[C11 MENOR — `branch` default no slugificado]** `branch = f"feature/pipeline-{spec.name}"` produce un nombre de rama git inválido si `spec.name` tiene espacios/mayúsculas/símbolos. **Fix:** `_slug(spec.name)` (alfanumérico + guiones).
> - **[C12 MENOR — KPI global sobre-promete commit ADO]** El KPI v1 prometía "commiteado para ADO **y** GitLab" pero F4 permite ADO = `NotImplementedError` (501) en v1. **Fix:** KPI = render para ambos + **commit GitLab** (ADO: render-only v1; commit diferido, 501 claro).
> - **[ADICIÓN ARQUITECTO v2]** Test centinela `test_plan73_routes_registered.py` contra `create_app()` real (cierra C2: hace imposible el falso-verde del doble prefijo). + Reestructuración en **Bloque A (contract-first, F0-F3)** / **Bloque B (materialización, F4-F6)** para que el Plan 74 consuma el contract sin esperar la UI.

> **CHANGELOG boceto v0 → v1 (conservado para trazabilidad):**
> - **[DECISIÓN ARQUITECTÓNICA HEREDADA]** Este plan **NO extiende `CIProvider`**. `PipelineSpec` es un dataclass PURO tracker-agnóstico; los renderers son funciones puras; el commit del YAML usa `commit_file(path, content, branch, message)`, método que pertenece a un sub-puerto **`RepoWriter`** distinto de `CIProvider` (principio ISP).
> - **[SUBSET EXPLÍCITO]** F0 documenta la matriz de features soportadas por `PipelineSpec` v1 y el escape hatch (`raw_yaml`) para lo no cubierto.
> - **[ORDEN]** (corregido en v2 — ver C3).

---

## 1. Objetivo y KPI

Un `PipelineSpec` (dataclass puro, tracker-agnóstico) que se **renderiza** a YAML ADO (`azure-pipelines.yml`) o GitLab (`.gitlab-ci.yml`), con validación determinista, y se **commitea** vía la API del tracker con HITL explícito del operador. Hace que crear/migrar un pipeline sea trivial y robusto desde Stacky.

**KPI global (DoD) (corregido C12):** el operador describe un pipeline una vez (UI o YAML del spec) y obtiene **YAML válido renderizado para ADO y GitLab**, y para **GitLab** lo commitea en el repo de forma **idempotente**, con `STACKY_PIPELINE_GENERATOR_ENABLED=true` y `confirm=True` explícito en el commit. **ADO en v1 es render-only** (el `commit_file` ADO devuelve 501 claro; commit ADO diferido post-v1).

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy:

- No existe en `backend/` ningún módulo `pipeline_spec` ni renderers a YAML (glob `services/{pipeline_spec,pipeline_renderers}.py` vacío 2026-06-28). Los pipelines se escriben a mano en YAML ADO o GitLab, duplicando conocimiento y sin validación hasta runtime.
- Migrar pipelines ADO↔GitLab a mano es el trabajo más tedioso y error-prone del roadmap GitLab; el **Plan 74 (migrador) consume** un `PipelineSpec` como contract compartido para convertir pipelines sin duplicar lógica de render (`74_PLAN...md:588`). Por eso **73 provee el contract y va antes (o en paralelo) que 74** (C3).
- Los Planes 71/72 sólo consumen CI pre-existente (infer/trigger/monitor); no crean pipelines. Este plan cierra la creación declarativa **sin depender de 71/72** (C4): usa el provider base del Plan 65 + un sub-puerto `RepoWriter` propio.
- Un `PipelineSpec` puro permite validación determinista (schema), diff/preview, y reutilización por el Plan 74.

---

## 3. Principios y guardarraíles (heredados + HITL en commit)

- **HITL innegociable (en commit):** el commit del YAML al repo exige `confirm=True` explícito del operador (mismo riel que Plan 72). Default a feature branch + Merge Request (no directo a default branch sin guard). El generador es **operador-driven** (UI/API), **nunca agente-driven** → no introduce autonomía en ningún runtime.
- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API/UI; NO toca prompts ni runtime del agente.
- **Cero trabajo extra al operador:** flag opt-in `STACKY_PIPELINE_GENERATOR_ENABLED` default **OFF**, `env_only=False`, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI"). Leída **per-request** (mismo patrón que Plan 72; no se introduce mecanismo de refresh nuevo).
- **No degradar / backward-compatible:** flag OFF = guard 404 per-request; ningún comportamiento existente cambia. El blueprint se registra SIEMPRE en `api/__init__.py` junto a los demás (sin tocar orden ni prefijos de los existentes).
- **TDD + funciones PURAS + ratchet + no falsos verdes.** Los renderers y el validador son **puros** (sin I/O); el round-trip test es la guardia anti-divergencia silenciosa entre ADO y GitLab (F6, con núcleo round-trip-safe explícito, C6). Las RUTAS reales se verifican contra `create_app()` (centinela, [ADICIÓN ARQUITECTO v2]).
- **Mono-operador sin auth:** el PAT para commitear requiere scope `api` en GitLab (heredado del Plan 72 F0); `Code.Write` en ADO (no aplica v1, ADO render-only). Sin RBAC (`current_user` es header sin validar; sería teatro).

---

## 4. Fases

> **Bloque A (contract-first, sin deps — implementable YA, lo consume el Plan 74):** F0, F1, F2, F3.
> **Bloque B (materialización — requiere provider base del Plan 65):** F4, F5, F6.

### F0 — `PipelineSpec` (dataclass puro) + `dict_to_spec` + matriz de features soportadas

**Objetivo:** definir el dataclass puro, el deserializador puro, y el subset v1. Resuelve el supuesto crítico del boceto y C5.

**Archivos exactos F0:**
- `services/pipeline_spec.py` — **archivo nuevo** (dataclass + tipos + `dict_to_spec` + `ValidationError` + `_validate_spec`; por cohesión, la validación vive aquí, no en `renderers`).

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
    image: Optional[str] = None        # GitLab image
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
    raw_yaml_target: Optional[str] = None    # "ado" | "gitlab" | None

    def validate(self) -> list["ValidationError"]:
        return _validate_spec(self)   # función PURA (F3)
```

**Deserializador PURO (FIX C5) — símbolo exacto:**

```python
# services/pipeline_spec.py
def dict_to_spec(d: dict) -> PipelineSpec:
    """JSON/dict -> PipelineSpec. PURA. Listas JSON -> tuplas; campos ausentes -> defaults.
    No hace I/O ni valida (la validación es _validate_spec en F3)."""
    def _step(s: dict) -> Step:
        return Step(name=s.get("name", ""), script=s.get("script", ""),
                    working_directory=s.get("working_directory"),
                    condition=s.get("condition"), env=dict(s.get("env") or {}))
    def _job(j: dict) -> Job:
        return Job(name=j.get("name", ""),
                   steps=tuple(_step(s) for s in (j.get("steps") or [])),
                   image=j.get("image"), pool_vm_image=j.get("pool_vm_image"),
                   runner_tags=tuple(j.get("runner_tags") or ()),
                   variables=dict(j.get("variables") or {}),
                   artifacts=tuple(j.get("artifacts") or ()),
                   services=tuple(j.get("services") or ()))
    def _stage(st: dict) -> Stage:
        return Stage(name=st.get("name", ""),
                     jobs=tuple(_job(j) for j in (st.get("jobs") or [])),
                     condition=st.get("condition"))
    return PipelineSpec(name=d.get("name", ""),
                        stages=tuple(_stage(st) for st in (d.get("stages") or [])),
                        variables=dict(d.get("variables") or {}),
                        trigger_branches=tuple(d.get("trigger_branches") or ()),
                        raw_yaml=d.get("raw_yaml"), raw_yaml_target=d.get("raw_yaml_target"))
```

**Matriz de features v1 (resuelve supuesto crítico del boceto):**

| Feature ADO | Feature GitLab | Cobertura v1 | Nota |
|---|---|---|---|
| `stages` + `jobs` + `steps` | `stages` + `jobs` + `script` | **SÍ** | núcleo común. |
| `pool.vmImage` | `image:` | **SÍ** | `Job.pool_vm_image` / `Job.image`; cada renderer elige su campo. |
| `variables` (pipeline + job) | `variables` (global + job) | **SÍ** | dict simple string→string. |
| `condition` en step/job/stage | `rules`/`only/except` | **PARCIAL** | `condition` ADO crudo; `rules: if` simplificado en GitLab (sin `changes:`/`exists:`). |
| `trigger: branches` | flujo default GitLab (push dispara) | **SÍ (lossy GitLab)** | `trigger_branches` → ADO explícito; GitLab se omite (push es default) → **lossy-by-design en GitLab round-trip, F6**. |
| `runner tags`/`demands` | `tags` | **SÍ** | `Job.runner_tags`. |
| `artifacts: paths` | `artifacts: paths` | **SÍ** | lista de paths simples. |
| `services` (service containers) | `services:` | **PARCIAL** | lista de nombres sólo. |
| **Templates ADO** (`template:`) | — | **NO** | `raw_yaml`. |
| — | **`extends:`/`include:`** | **NO** | `raw_yaml`. |
| **`strategy.matrix`** | `matrix:` | **NO** | `raw_yaml`. |
| **Environments/deployments** | **environments** | **NO** | fuera de scope v1. |
| **Caches complejos** | **cache:** keys/policy | **NO** | sólo artifact paths simples. |

**Escape hatch `raw_yaml`:** si un pipeline necesita templates/matriz/environments, el operador setea `raw_yaml="..."` y `raw_yaml_target="gitlab"` (o `"ado"`); el renderer del tracker correspondiente emite el `raw_yaml` crudo sin transformar. El renderer del OTRO tracker lanza `ValidationError` — sin divergencia silenciosa.

**Tests F0:**
- Archivo: `backend/tests/test_plan73_pipeline_spec.py`.
- Casos:
  1. Construir `PipelineSpec` mínimo (1 stage, 1 job, 1 step) sin `raw_yaml`.
  2. Construir con `raw_yaml="..."` y `raw_yaml_target="gitlab"`.
  3. `Step.script` acepta multi-línea.
  4. Todos los dataclass son `frozen` (asignar atributo lanza `FrozenInstanceError`).
  5. `PipelineSpec.validate` existe y retorna lista (vacía para spec mínimo válido).
  6. **[C5]** `dict_to_spec({"name":"p","stages":[{"name":"s","jobs":[{"name":"j","steps":[{"name":"st","script":"echo"}]}]}]})` → `PipelineSpec` con `stages[0].jobs[0].steps[0].script=="echo"` y **todos los contenedores son `tuple`** (no list).
  7. **[C5]** `dict_to_spec({})` → `PipelineSpec(name="", stages=())` (defaults, sin excepción).
  8. **[C5]** `dict_to_spec` preserva `raw_yaml`/`raw_yaml_target`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_pipeline_spec.py -q`.

**Criterio binario F0:** los 8 casos pasan; `pipeline_spec.py` NO importa nada de ADO ni GitLab (sólo `typing`/`dataclasses`).

**Trabajo del operador F0:** ninguno.

---

### F1 — Renderer `to_ado_yaml(spec) -> str` (función PURA)

**Objetivo:** convertir `PipelineSpec` a YAML ADO válido (`azure-pipelines.yml`).

**Archivos exactos F1:**
- `services/pipeline_renderers.py` — **archivo nuevo** (funciones puras `to_ado_yaml`, `to_gitlab_yaml`).
- Usa `yaml.safe_dump` — **PyYAML ya está disponible** (`requirements.txt:10` `PyYAML==6.0.3`, verificado C10; no hace falta agregar nada).
- Importa `PipelineSpec`, `ValidationError` desde `services.pipeline_spec`.

**Símbolos exactos F1:**

```python
# services/pipeline_renderers.py
import yaml
from services.pipeline_spec import PipelineSpec, ValidationError

def to_ado_yaml(spec: PipelineSpec) -> str:
    """Convierte PipelineSpec a azure-pipelines.yml. PURA (sin I/O)."""
    if spec.raw_yaml and spec.raw_yaml_target == "ado":
        return spec.raw_yaml
    if spec.raw_yaml and spec.raw_yaml_target != "ado":
        raise ValidationError("raw_yaml", f"raw_yaml target={spec.raw_yaml_target} no portable a ado")
    doc = _spec_to_ado_doc(spec)   # PURA: spec -> dict YAML-ready
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
```

> **Nota (C1):** `ValidationError` se levanta como **excepción** en los renderers (caso raw_yaml no portable). Es el mismo dataclass `(field, message)` de F3; debe heredar de `Exception`. Ver F3.

**Mapeo ADO (F1):**
- `PipelineSpec.trigger_branches` → `trigger: branches: include: [...]`.
- `Stage` → `stage`; `Job` → `job`; `Step` → `script` con `displayName`.
- `Job.pool_vm_image` → `pool: vmImage: ...`.
- `Job.variables` → `variables:` dict.
- `Step.condition` → `condition:` crudo.
- `Job.artifacts` → `publish: <path>` con `artifact:` (v1).

**Tests F1:**
- Archivo: `backend/tests/test_plan73_render_ado.py`.
- Casos:
  1. Spec mínimo → YAML contiene `stages:`, `- stage:`, `- job:`, `- script:`.
  2. `trigger_branches=("main","develop")` → YAML contiene `trigger:` con `include` y `main`/`develop`.
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
        raise ValidationError("raw_yaml", f"raw_yaml target={spec.raw_yaml_target} no portable a gitlab")
    doc = _spec_to_gitlab_doc(spec)
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
```

**Mapeo GitLab (F2):**
- `PipelineSpec.stages` → lista de nombres en `stages:`; cada `Stage.jobs` se vuelca al root del doc con `<job_name>:` y `stage: <stage_name>`.
- `Job.image` → `image: ...`; si `image` es None y hay `pool_vm_image`, mapeo `ubuntu-latest`→`ubuntu:latest` (convención documentada).
- `Job.runner_tags` → `tags: [...]`.
- `Job.variables` → `variables:` por job.
- `Step.script` → `script:` (lista de líneas).
- `Step.condition` → `rules: [{if: "<condición traducida>"}]` simplificado; lo no traducible → `ValidationError` con `raw_yaml` sugerido.
- `Job.artifacts` → `artifacts: paths: [...]`.
- `Job.services` → `services: [...]`.
- `trigger_branches` → **omitido** (GitLab dispara por push por defecto) → **lossy-by-design** (F6 lo excluye del round-trip GitLab con justificación, C6).

**Tests F2:**
- Archivo: `backend/tests/test_plan73_render_gitlab.py`.
- Casos:
  1. Spec mínimo → YAML contiene `stages:`, un job con `stage:`, `script:`.
  2. `Job.image="python:3.11"` → YAML contiene `image: python:3.11`.
  3. `Job.runner_tags=("docker","linux")` → YAML contiene `tags:` con `docker`/`linux`.
  4. `Job.artifacts=("dist/","*.whl")` → YAML contiene `artifacts:` y `paths:`.
  5. `Step.condition="eq(variables['Build.SourceBranchName'], 'main')"` → traducido a `rules` con `$CI_COMMIT_BRANCH == "main"`.
  6. `Step.condition` intraducible (ej. referencias ADO internas no mapeables) → `ValidationError`.
  7. `raw_yaml` con `target="gitlab"` → retorna literal; con `target="ado"` → `ValidationError`.
  8. YAML producido parsea de vuelta (`yaml.safe_load`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_render_gitlab.py -q`.

**Criterio binario F2:** los 8 casos pasan; `to_gitlab_yaml` es pura.

**Trabajo del operador F2:** ninguno.

---

### F3 — Validador determinista `_validate_spec(spec) -> list[ValidationError]` (función PURA)

**Objetivo:** schema check determinista (sin LLM) antes de renderizar o commitear.

**Archivos exactos F3:**
- `services/pipeline_spec.py` — `ValidationError` + `_validate_spec` (cohesión con el dataclass; los renderers lo importan).

**Símbolos exactos F3:**

```python
# services/pipeline_spec.py
class ValidationError(Exception):
    """Excepción Y dato: (field, message). Heredá de Exception para poder raise en renderers (C1)."""
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(f"{field}: {message}")

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

> **Nota (C1):** `ValidationError` es a la vez dato (`.field`/`.message`) y `Exception` raisable. El endpoint F5 serializa `{"field": e.field, "message": e.message}` (no `e.__dict__`, que incluye `args`).

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
  8. `ValidationError("x","y")` es instancia de `Exception` (se puede `raise`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_validate.py -q`.

**Criterio binario F3:** los 8 casos pasan; `_validate_spec` es pura.

**Trabajo del operador F3:** ninguno.

> **Fin del Bloque A.** Tras F0-F3, el `PipelineSpec` + renderers + validador + deserializador están completos y PUROS. **El Plan 74 ya puede consumirlos** para convertir pipelines (`74_PLAN...md:588`), sin esperar el Bloque B.

---

### F4 — Commit del YAML vía sub-puerto `RepoWriter` (NO extiende `CIProvider`)

**Objetivo:** commitear el YAML renderizado al repo del tracker. **NO se extiende `CIProvider`**; el commit usa `commit_file` en un sub-puerto **`RepoWriter`** distinto (ISP).

**Archivos exactos F4:**
- `services/repo_writer.py` — **archivo nuevo** (sub-puerto `RepoWriter(Protocol)` + fábrica `get_repo_writer`).
- `services/gitlab_provider.py` — agregar `commit_file(path, content, branch, message)` + `_detect_commit_action(path, branch)` (GitLab Commits API `POST /projects/:id/repository/commits`).
- `services/ado_provider.py` — `commit_file` lanza `NotImplementedError` (v1 ADO render-only, C12; commit ADO diferido).

**Símbolos exactos F4 (sub-puerto + fábrica, FIX C8):**

```python
# services/repo_writer.py
from typing import Optional, Protocol, runtime_checkable

@runtime_checkable
class RepoWriter(Protocol):
    name: str
    def commit_file(self, path: str, content: str, branch: str, message: str) -> dict: ...

REPO_WRITER_METHODS = ("commit_file",)

def get_repo_writer(project: Optional[str] = None) -> RepoWriter:
    """Fábrica espejo. REUSA la MISMA resolución por tracker_type del Plan 65
    (project_manager.get_active_tracker_config / el helper que ya elige adapter
    GitLab vs ADO). Devuelve el adapter del provider activo del proyecto: el
    GitLabTrackerProvider o el AdoTrackerProvider ya existentes (no instancia nada nuevo).
    NO inventa un mecanismo de selección propio (C8)."""
    ...
```

```python
# services/gitlab_provider.py — nuevos métodos (contrato REAL de _request, FIX C1):
def _detect_commit_action(self, path: str, branch: str) -> tuple[str, str | None]:
    """Devuelve ("create", None) si el archivo no existe; ("update", contenido_actual) si existe.
    GET /projects/:id/repository/files/:path?ref=branch. Captura TrackerApiError(404) -> create."""
    from services.tracker_provider import TrackerApiError
    proj_path = self._client._project_path()
    try:
        body, _ = self._client._request(
            "GET", f"/projects/{proj_path}/repository/files/{self._client._encode_path(path)}",
            params={"ref": branch})
        # GitLab devuelve content base64; decodificar para comparar (helper existente o base64.b64decode).
        return "update", self._decode_file_content(body)
    except TrackerApiError as e:
        if e.status == 404:
            return "create", None
        raise

def commit_file(self, path: str, content: str, branch: str, message: str) -> dict:
    """POST /projects/:id/repository/commits — crea/actualiza archivo en 1 commit.
    FIX C1: body, _ = _request(...); NO comparar status; TrackerApiError ya se lanza y se deja propagar.
    FIX C7: si el contenido es idéntico al actual, NO commitea (idempotencia)."""
    proj_path = self._client._project_path()
    action, current = self._detect_commit_action(path, branch)
    if action == "update" and current == content:
        return {"sha": "", "branch": branch, "path": path, "web_url": "", "status": "unchanged"}  # idempotente
    body, _ = self._client._request(
        "POST", f"/projects/{proj_path}/repository/commits",
        json_body={"branch": branch, "commit_message": message,
                   "actions": [{"action": action, "file_path": path, "content": content}]},
    )
    return {"sha": str(body.get("id") or ""), "branch": branch, "path": path,
            "web_url": body.get("web_url", ""), "status": action}
```

> **Mapeo de errores (FIX C1):** un PAT sin scope `api` produce que `_request` lance `TrackerApiError(403, ..., kind="forbidden")`; `commit_file` **NO** lo captura — se deja propagar y el endpoint F5 lo mapea a `403`. Prohibido `body, status = ...; if status == 403` (status sería headers; el 403 ya se lanzó). Idéntico al riel del Plan 72 (`gitlab_client.py:159`).

**Tests F4:**
- Archivo: `backend/tests/test_plan73_repo_writer.py`.
- Casos:
  1. `RepoWriter` con `commit_file` pasa `isinstance(stub, RepoWriter)`; stub sin `commit_file` NO pasa.
  2. `GitLabTrackerProvider.commit_file("ci.yml","content","main","msg")` con `_detect_commit_action` mockeado a `("create", None)` → construye POST con `actions=[{"action":"create",...}]` **[mock sobre `_request`, que devuelve `({"id":"abc","web_url":"u"}, {})`]**; retorna `sha="abc"`, `status="create"`.
  3. **[C1]** Si `_request` **lanza** `TrackerApiError(403, "no api scope", kind="forbidden")`, `commit_file` **propaga** ese error (no lo fabrica ni compara status).
  4. **[C7]** Idempotencia: `_detect_commit_action` mockeado a `("update", "content")` y `commit_file(..., content="content", ...)` → retorna `status="unchanged"` y **`_request.assert_not_called()`** (sólo se llamó el GET de detección, no el POST de commit).
  5. `AdoTrackerProvider.commit_file(...)` → `NotImplementedError` con mensaje que incluye `"v1"` (C12, ADO render-only).
  6. **[C8]** `get_repo_writer(project)` con un proyecto GitLab devuelve el adapter cuyo `.name == "gitlab"` (afirmar que reusa la resolución del Plan 65, mockeando `get_active_tracker_config`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_repo_writer.py -q`.

**Criterio binario F4:** los 6 casos pasan; `RepoWriter` es independiente de `CIProvider`; `commit_file` usa `body, _ =` y deja propagar `TrackerApiError`; idempotencia corta antes del POST.

> **Nota contractual:** `commit_file` NO se agrega a `CIProvider`. Sub-puerto separado (ISP). No toca `CI_PORT_METHODS` (eso es del 71/72; este plan no lo importa, C4).

**Trabajo del operador F4:** ninguno.

---

### F5 — Endpoint API con HITL + flag editable por UI + UI editor + preview lado-a-lado

**Objetivo:** endpoint `POST /api/pipeline-generator/preview` (puro, sin commit) y `POST /api/pipeline-generator/commit` (con HITL `confirm=True`); flag editable por UI; UI con editor del spec + preview ADO|GitLab.

**Archivos exactos F5:**
- `api/pipeline_generator.py` — **blueprint nuevo** `bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")` con `POST /preview` y `POST /commit`. **(FIX C2: `url_prefix="/pipeline-generator"`, NO `/api/pipeline-generator`.)**
- `api/__init__.py` — **agregar** `from .pipeline_generator import bp as pipeline_generator_bp` (L3-41) y `api_bp.register_blueprint(pipeline_generator_bp)` (L44-82). **NO** tocar `app.py`; **registrar SIEMPRE** (no gated en el registro). **(FIX C2: así se registran TODOS los sub-blueprints, ver `api/__init__.py:43-82`.)**
- `config.py` — `STACKY_PIPELINE_GENERATOR_ENABLED: bool = False`.
- `services/harness_flags.py` — **registrar en FLAG_REGISTRY** `STACKY_PIPELINE_GENERATOR_ENABLED`, `env_only=False`, categoría `"Pipelines / CI"`, default `False`. **(FIX C9: garantiza editable por UI, espejo Plan 72/74.)**
- `harness_defaults.env` — `STACKY_PIPELINE_GENERATOR_ENABLED=false`.
- `frontend/src/components/PipelineGeneratorPanel.tsx` — **nuevo**: editor del spec + preview lado-a-lado (ADO | GitLab) + botón "Commitear" con modal HITL.

> **[C2 — Por qué `url_prefix="/pipeline-generator"` y NO en app.py]:** `api/__init__.py:43` define `api_bp = Blueprint("api", __name__, url_prefix="/api")` y registra todos los sub-blueprints sobre él (L44-82). Un sub-blueprint con `url_prefix="/api/pipeline-generator"` daría `/api` + `/api/pipeline-generator` = **`/api/api/pipeline-generator`** (404). Por eso `bp` lleva `url_prefix="/pipeline-generator"` → ruta final `/api/pipeline-generator/...`. El test centinela ([ADICIÓN ARQUITECTO v2]) lo verifica.

**Símbolos exactos F5 (endpoint preview — PURA; guard per-request, FIX C2):**

```python
# api/pipeline_generator.py
from flask import Blueprint, request, jsonify, abort
import config
from services.pipeline_spec import dict_to_spec
from services.pipeline_renderers import to_ado_yaml, to_gitlab_yaml
from services.repo_writer import get_repo_writer
from services.tracker_provider import TrackerApiError

bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")  # -> /api/pipeline-generator

@bp.post("/preview")
def preview_route():
    if not config.STACKY_PIPELINE_GENERATOR_ENABLED:
        abort(404)   # guard per-request (blueprint registrado SIEMPRE, C2)
    body = request.get_json(silent=True) or {}
    spec = dict_to_spec(body)   # PURA (F0)
    errors = spec.validate()
    if errors:
        return jsonify({"errors": [{"field": e.field, "message": e.message} for e in errors]}), 400
    return jsonify({"ado": to_ado_yaml(spec), "gitlab": to_gitlab_yaml(spec)})
```

**Símbolos exactos F5 (endpoint commit — HITL absoluto + branch slug, FIX C11):**

```python
import re
def _slug(name: str) -> str:
    """FIX C11: nombre de rama git válido a partir de spec.name."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower()).strip("-")
    return s or "pipeline"

@bp.post("/commit")
def commit_route():
    if not config.STACKY_PIPELINE_GENERATOR_ENABLED:
        abort(404)
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400   # RIEL ABSOLUTO
    spec = dict_to_spec(body)
    errors = spec.validate()
    if errors:
        return jsonify({"errors": [{"field": e.field, "message": e.message} for e in errors]}), 400
    target = body.get("target")   # "ado" | "gitlab"
    try:
        yaml_str = to_ado_yaml(spec) if target == "ado" else to_gitlab_yaml(spec)
    except TrackerApiError as e:                 # raw_yaml no portable, etc.
        return jsonify({"error": str(e)}), 400
    path = "azure-pipelines.yml" if target == "ado" else ".gitlab-ci.yml"
    branch = body.get("branch") or f"feature/pipeline-{_slug(spec.name)}"
    writer = get_repo_writer(body.get("project"))
    try:
        result = writer.commit_file(path=path, content=yaml_str, branch=branch,
                                    message=f"pipeline({spec.name}): update via Stacky")
    except TrackerApiError as e:                  # FIX C1 — 403/404 real de GitLab
        return jsonify({"error": str(e), "kind": e.kind}), e.status
    except NotImplementedError as e:              # ADO render-only v1 (C12)
        return jsonify({"error": str(e)}), 501
    return jsonify(result)
```

**Tests F5:**
- Archivo: `backend/tests/test_plan73_generator_endpoint.py`.
- Casos:
  1. Flag OFF → `/preview` y `/commit` 404 (guard per-request).
  2. `/preview` con spec válido → 200 con `ado` y `gitlab` strings.
  3. `/preview` con spec inválido (name vacío) → 400 con `errors` (cada uno con `field`/`message`).
  4. `/commit` sin `confirm` → **400** (HITL gate — **test VP de significancia**); `writer.commit_file` **assert_not_called**.
  5. `/commit` con `confirm=True`, `target="gitlab"` → llama `writer.commit_file` **[mock: assert_called_once]**; response con `sha`, `branch`, `status`.
  6. `/commit` con `target="gitlab"` y sin `branch` → `branch="feature/pipeline-<slug>"` (afirmar slug de un `name` con espacios/mayúsculas, C11).
  7. **[C1]** `/commit` con `confirm=True` y `writer.commit_file` que lanza `TrackerApiError(403, ..., kind="forbidden")` → response **403** con `kind`.
  8. **[C12]** `/commit` con `target="ado"` y writer ADO que lanza `NotImplementedError` → response **501** con mensaje accionable.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_generator_endpoint.py -q`.

**[ADICIÓN ARQUITECTO v2] — Test centinela de rutas reales (cierra C2):**
- Archivo: `backend/tests/test_plan73_routes_registered.py`.

```python
def test_pipeline_generator_routes_registered_under_api():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/pipeline-generator/preview" in rules   # C2 — no /api/api/pipeline-generator
    assert "/api/pipeline-generator/commit" in rules
```

- Justificación: hace IMPOSIBLE el falso-verde de la clase C2 (tests sobre una app armada a mano que pasan mientras producción sirve `/api/api/pipeline-generator`). Read-only, cero trabajo al operador, neutral a los 3 runtimes. Si `create_app()` requiere setup, reusar el fixture de app de los tests existentes de `api/`.

**Criterio binario F5:** los 8 casos + el centinela pasan. **Caso 4 es el gate HITL.** La flag aparece en el FLAG_REGISTRY con `env_only=False` (editable por UI).

**UI tests F5:**
- Archivo: `frontend/src/components/__tests__/PipelineGeneratorPanel.test.tsx` (vitest si disponible; si no, `tsc --noEmit` + checklist manual firmado — memoria `stacky-backend-dev-test-env`: vitest puede no estar instalado).
- Casos:
  1. Editor muestra campos name/stages/jobs/steps.
  2. Preview se actualiza al editar; lado ADO y lado GitLab (llama `POST /api/pipeline-generator/preview`).
  3. Botón "Commitear" abre modal con `target`, `branch`, warning "Esto commitea un archivo real en el repo".
  4. Clic "Confirmar" en modal → POST `/api/pipeline-generator/commit` con `confirm=true`; NO se llama sin confirm.
  5. Response `sha`/`status` → toast (success con link `web_url`; "sin cambios" si `status:"unchanged"`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` (+ vitest si disponible).

**Trabajo del operador F5:** opt-in (default OFF); para usar, prender flag por UI + confirmar PAT scope `api` + clic en modal.

---

### F6 — Round-trip test (idempotencia semántica con núcleo round-trip-safe) + ratchet

**Objetivo:** guardia anti-divergencia silenciosa: spec → YAML → parse → spec produce el mismo spec en el **núcleo round-trip-safe**, excluyendo explícitamente los campos lossy-by-design (FIX C6). Es el test más importante del plan.

**Archivos exactos F6:**
- `services/pipeline_renderers.py` — agregar `parse_ado_yaml(yaml_str) -> PipelineSpec` y `parse_gitlab_yaml(yaml_str) -> PipelineSpec` (PURAS, inversas de los renderers para el subset v1).
- `backend/tests/test_plan73_round_trip.py` — **nuevo**.

**Contrato de equivalencia (FIX C6 — explícito, no tautológico):**

```python
# Núcleo round-trip-safe común (ambos trackers preservan estos campos):
_CORE_ROUNDTRIP_FIELDS = ("name", "stages")  # stages incluye jobs/steps/script/variables/artifacts/runner_tags

# Lossy-by-design POR TRACKER (el renderer los pierde a propósito; el round-trip los excluye CON justificación):
_LOSSY_BY_DESIGN = {
    "ado":    (),                       # ADO preserva trigger_branches y pool_vm_image y condition crudo
    "gitlab": ("trigger_branches",),    # GitLab dispara por push: trigger_branches se OMITE (F2) -> no recuperable
}

def _specs_equivalent(a: PipelineSpec, b: PipelineSpec, ignore_fields: tuple[str, ...] = ()) -> bool:
    """Comparación semántica (no string-exacta). Ignora ignore_fields (los lossy-by-design del tracker)
    y normaliza None vs default (() / {})."""
    ...
```

> **Por qué fixtures separados por tracker (C6):** `pool_vm_image` es ADO-specific y `image` GitLab-specific; un único fixture canónico forzaría a un renderer a emitir un campo que no le corresponde. El round-trip ADO usa un fixture con `pool_vm_image`; el round-trip GitLab usa uno con `image`. Para `condition`, el fixture GitLab usa SÓLO condiciones traducibles-y-reversibles (las intraducibles ya están cubiertas por F2 caso 6, que afirma `ValidationError`, no round-trip). Esto hace el test **significativo** (protege el núcleo) sin ser **imposible** (no exige recuperar lo que se omite a propósito) ni **tautológico** (los exclusions están nombrados y justificados, no son un `ignore=all`).

**Tests F6:**
- Archivo: `backend/tests/test_plan73_round_trip.py`.
- Casos:
  1. Round-trip ADO: `_specs_equivalent(spec_ado, parse_ado_yaml(to_ado_yaml(spec_ado)))` con `ignore_fields=_LOSSY_BY_DESIGN["ado"]` (vacío) → True. Fixture ADO cubre stages/jobs/steps/variables/trigger_branches/pool_vm_image.
  2. Round-trip GitLab: `_specs_equivalent(spec_gl, parse_gitlab_yaml(to_gitlab_yaml(spec_gl)), ignore_fields=_LOSSY_BY_DESIGN["gitlab"])` → True. Fixture GitLab cubre stages/jobs/steps/variables/image/runner_tags/artifacts.
  3. **[C6 — el exclusion es real, no tautológico]** Un fixture GitLab CON `trigger_branches` no nulo round-trip-ea a un spec con `trigger_branches=()` (se perdió); el test afirma que **sin** el `ignore_fields` la comparación daría False, y **con** el ignore da True (prueba que el campo excluido es exactamente el lossy esperado, no un comodín que oculta otros bugs).
  4. Round-trip con `raw_yaml` target="gitlab": `to_gitlab_yaml` retorna el crudo y `parse_gitlab_yaml` lo recupera como `raw_yaml`; el ADO renderer del mismo spec lanza `ValidationError` (no diverge silenciosamente).
  5. `_specs_equivalent` normaliza None vs default (`()` / `{}`) en campos opcionales.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan73_round_trip.py -q`.

**Ratchet F6:** registrar TODOS los `test_plan73_*.py` (incluido `test_plan73_routes_registered.py`) en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49 (memoria `stacky-ratchet-obliga-registrar-tests`).

**Criterio binario F6:** los 5 casos pasan; ratchet verde; flag aparece en `harness_defaults.env` y en el FLAG_REGISTRY (UI).

**Trabajo del operador F6:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Subset demasiado chico o grande** (R1). **Mitigación:** F0 matriz explícita; `raw_yaml` escape hatch; round-trip F6 detecta divergencia en el núcleo.
2. **Commitear al default branch sin guard** (R2). **Mitigación:** HITL `confirm=True` (F5 caso 4 gate); default a feature branch slugificado (C11); el endpoint no commitea a `main` sin `branch` explícito del operador.
3. **Renderers que divergen silenciosamente** (R3). **Mitigación:** F6 round-trip con núcleo round-trip-safe y lossy-by-design nombrados (C6); el caso 3 prueba que el exclusion no oculta otros bugs.
4. **Spec creep** (R4). **Mitigación:** sección 6 fuera de scope; `raw_yaml` desvía lo no cubierto.
5. **Traducción `condition` ADO→GitLab incompleta** (R5). **Mitigación:** F2 caso 6: intraducible → `ValidationError` con sugerencia `raw_yaml`; nunca YAML silenciosamente roto.
6. **PyYAML** (R6). **Resuelto (C10):** `PyYAML==6.0.3` ya en `requirements.txt:10`. Sin acción.
7. **Contrato `_request` mal usado** (R7, C1). **Mitigación:** F4 usa `body, _ =` y deja propagar `TrackerApiError`; F4 casos 3-4 lo afirman; el endpoint mapea a `e.status`.
8. **Rutas mal registradas / doble prefijo `/api/api/...`** (R8, C2). **Mitigación:** `bp` con `url_prefix="/pipeline-generator"` registrado en `api_bp` (no en app.py, no `/api/...`); test centinela `test_plan73_routes_registered.py` ([ADICIÓN ARQUITECTO v2]).
9. **Flag editable por UI que no surte efecto** (R9, C2/C9). **Mitigación:** blueprint registrado SIEMPRE; flag leída per-request; registrada en FLAG_REGISTRY con `env_only=False`.
10. **Idempotencia rota (commit vacío / duplicado)** (R10, C7). **Mitigación:** `commit_file` corta antes del POST si el contenido es idéntico; F4 caso 4 afirma `_request.assert_not_called()`.
11. **3 runtimes** (R11). **Mitigación:** el plan no toca prompts/runtime del agente; generador operador-driven (sin autonomía).

---

## 6. Fuera de scope

- **NO** parseo inverso YAML → spec para pipelines arbitrarios complejos (sólo el subset v1 cubierto por F6 round-trip; el migrador Plan 74 maneja pipelines reales **consumiendo este contract**).
- **NO** templates/herencia compleja (`extends:`/`include:`/`template:`) — usar `raw_yaml`.
- **NO** matrix dinámica. **NO** environments/deployments. **NO** caches complejos.
- **NO** ejecución local de pipelines. **NO** validación contra runner real (sólo schema determinista).
- **NO** extender `CIProvider` (commit usa sub-puerto `RepoWriter` separado, C4).
- **NO** commit ADO en v1 (render ADO sí; `commit_file` ADO = 501 claro, C12).
- **NO** depender de Plan 71/72 (C4) ni implementarse después de Plan 74 (C3 — 73 provee el contract a 74).
- **NO** migración ADO→GitLab (Plan 74 — éste le provee el contract).

---

## 7. Glosario

- **PipelineSpec:** dataclass PURA (`services/pipeline_spec.py`, F0) tracker-agnóstico: `stages`, `jobs`, `steps`, `variables`, `trigger_branches`, `raw_yaml`.
- **`dict_to_spec`:** función PURA JSON/dict → `PipelineSpec` (F0, C5); listas → tuplas, defaults para faltantes.
- **CIProvider:** sub-puerto de Plan 71/72. **Este plan NO lo toca ni lo importa (C4).**
- **RepoWriter:** sub-puerto nuevo (`services/repo_writer.py`, F4) con `commit_file`. Separado de `CIProvider` por ISP. `get_repo_writer` reusa la resolución por `tracker_type` del Plan 65 (C8).
- **`to_ado_yaml` / `to_gitlab_yaml`:** funciones PURAS renderers (`services/pipeline_renderers.py`, F1/F2).
- **`parse_ado_yaml` / `parse_gitlab_yaml`:** funciones PURAS inversas (F6).
- **`_validate_spec` / `ValidationError`:** validación PURA (F3); `ValidationError` es dato `(field, message)` Y `Exception` raisable (C1).
- **`_CORE_ROUNDTRIP_FIELDS` / `_LOSSY_BY_DESIGN`:** contrato explícito de qué preserva el round-trip y qué se pierde a propósito por tracker (C6); `trigger_branches` es lossy en GitLab.
- **`commit_file` (contrato `_request` real, C1):** `body, _ = self._client._request(...)`; `_request` devuelve `(body, headers)` y **ya lanza** `TrackerApiError` (`gitlab_client.py:159`). Nunca `body, status = ...; if status == ...`.
- **Idempotencia commit (C7):** si el contenido actual del archivo == nuevo contenido → `status:"unchanged"` sin POST.
- **`STACKY_PIPELINE_GENERATOR_ENABLED`:** flag nueva (default OFF, `env_only=False`, FLAG_REGISTRY categoría "Pipelines / CI", editable por UI, leída per-request). Flag OFF → 404 vía guard per-request.
- **Registro del blueprint (C2):** `bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")` registrado en `api/__init__.py` sobre `api_bp` (`url_prefix="/api"`) → ruta final `/api/pipeline-generator/...`. **Nunca** `url_prefix="/api/pipeline-generator"` (daría `/api/api/...`) ni registrar en `app.py`.
- **`test_plan73_routes_registered.py`:** centinela de rutas reales contra `create_app()` ([ADICIÓN ARQUITECTO v2]).

---

## 8. Orden de implementación

> **Bloque A (contract-first; sin deps de 70/71/72/74; implementable YA; lo consume el Plan 74):**
1. **F0** — `PipelineSpec` + `dict_to_spec` + matriz de features v1 + escape hatch.
2. **F1** — `to_ado_yaml` (pura).
3. **F2** — `to_gitlab_yaml` (pura).
4. **F3** — `_validate_spec` + `ValidationError` (pura).

> **Bloque B (materialización; requiere provider base del Plan 65, ya implementado):**
5. **F4** — Sub-puerto `RepoWriter` + `get_repo_writer` (resolución Plan 65, C8) + `commit_file` GitLab (contrato `_request` real C1; idempotencia C7); ADO = 501 (C12).
6. **F5** — Endpoints `/preview` y `/commit` con HITL + `dict_to_spec` (C5) + blueprint registrado en `api/__init__.py` con `url_prefix="/pipeline-generator"` (C2) + guard per-request + flag en FLAG_REGISTRY `env_only=False` (C9) + branch slug (C11) + UI + **test centinela de rutas** ([ADICIÓN ARQUITECTO v2]).
7. **F6** — Round-trip test con núcleo round-trip-safe (C6) + `parse_*_yaml` + ratchet.

> **Orden de roadmap (CORREGIDO C3):** este plan **NO** se implementa después de 74. El Bloque A puede hacerse de forma independiente y temprana; el Plan 74 lo **consume** para convertir pipelines (`74_PLAN...md:588`). Si se implementan en paralelo, el Bloque A debe estar verde antes de que el Plan 74 cablee la conversión de pipelines.

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** `PipelineSpec` dataclass PURA sin deps de ADO/GitLab (F0); `dict_to_spec` PURA testeada (C5); matriz de features documentada.
- [ ] **(b)** `to_ado_yaml` y `to_gitlab_yaml` implementadas y testeadas (F1/F2); producen YAML que parsea de vuelta.
- [ ] **(c)** `_validate_spec` + `ValidationError` (Exception raisable, C1) implementadas (F3).
- [ ] **(d)** Sub-puerto `RepoWriter` + `get_repo_writer` (resolución Plan 65, C8); `commit_file` GitLab usa `body, _ = _request(...)` y propaga `TrackerApiError` (C1); idempotencia corta antes del POST (C7); ADO = `NotImplementedError`/501 (C12).
- [ ] **(e)** Endpoint `/preview` PURA; `/commit` con HITL `confirm=True` gate (F5 caso 4 — gate de significancia, `commit_file` assert_not_called sin confirm).
- [ ] **(f)** Blueprint registrado en `api/__init__.py` con `url_prefix="/pipeline-generator"` (no en app.py, no doble prefijo); flag OFF → 404 vía guard per-request (C2).
- [ ] **(f2)** Rutas reales `/api/pipeline-generator/...` verificadas por `test_plan73_routes_registered.py` contra `create_app()` (C2, [ADICIÓN ARQUITECTO v2]).
- [ ] **(g)** Flag `STACKY_PIPELINE_GENERATOR_ENABLED` default **OFF**, `env_only=False`, en FLAG_REGISTRY categoría "Pipelines / CI", editable por UI (C9).
- [ ] **(h)** UI `PipelineGeneratorPanel` con editor + preview lado-a-lado + modal HITL; `tsc --noEmit` 0 errores.
- [ ] **(i)** Round-trip test verde en ambos trackers con núcleo round-trip-safe + lossy-by-design nombrados (F6, C6) — anti-divergencia silenciosa significativa (no tautológica).
- [ ] **(j)** `raw_yaml` escape hatch funcional; el renderer no-target lanza `ValidationError`.
- [ ] **(k)** Branch default slugificado (C11); `_slug("My Pipeline")` produce nombre git válido.
- [ ] **(l)** Los 3 runtimes operativos sin cambios.
- [ ] **(m)** Ratchet verde (Plan 49 F4) con TODOS los `test_plan73_*.py` registrados.
- [ ] **(n)** **NO** se importa ningún símbolo de Plan 71/72 (C4); deps reales = Plan 65 (ya implementado).

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`.
- **PyYAML (C10):** ya está (`requirements.txt:10` `PyYAML==6.0.3`). `import yaml` funciona; no agregar nada.
- **Registro del blueprint (C2 — CRÍTICO):** `bp = Blueprint("pipeline_generator", __name__, url_prefix="/pipeline-generator")`. Importar y registrar en **`api/__init__.py`** (`from .pipeline_generator import bp as pipeline_generator_bp` + `api_bp.register_blueprint(pipeline_generator_bp)`), igual que los demás (L44-82). **Prohibido** `url_prefix="/api/pipeline-generator"` (daría `/api/api/...`) y **prohibido** registrar en `app.py`. Verificalo con `test_plan73_routes_registered.py`.
- **Contrato `_client._request` (C1 — CRÍTICO):** devuelve `(body, response_headers)` y **ya lanza** `TrackerApiError` ante no-2xx (`gitlab_client.py:159`). Usar SIEMPRE `body, _ = self._client._request(...)`. **Prohibido** `body, status = ...; if status == 403` (status serían headers; el 403 ya se lanzó). El endpoint mapea `except TrackerApiError as e: ... e.status`.
- **Idempotencia (C7):** `commit_file` llama `_detect_commit_action` (GET del archivo); si `("update", contenido)` y `contenido == content`, retorna `status:"unchanged"` SIN POST. Test caso 4: `_request.assert_not_called()` para el POST.
- **Resolución de provider (C8):** `get_repo_writer` reusa `project_manager.get_active_tracker_config`/el helper del Plan 65 que elige adapter GitLab vs ADO por `tracker_type`. No inventar selección nueva.
- **Flag editable por UI (C9):** registrar en `services/harness_flags.py` FLAG_REGISTRY con `env_only=False`, categoría "Pipelines / CI", default `False`. (Regla dura: toda config del operador es editable por UI.)
- **`dict_to_spec` (C5):** listas JSON → `tuple`; campos ausentes → defaults; preserva `raw_yaml`/`raw_yaml_target`. Serializar errores como `{"field": e.field, "message": e.message}` (no `e.__dict__`).
- **Round-trip (C6):** definir `_CORE_ROUNDTRIP_FIELDS` y `_LOSSY_BY_DESIGN` (GitLab pierde `trigger_branches`); fixtures separados por tracker; `_specs_equivalent(a,b,ignore_fields=...)`; el caso 3 prueba que el exclusion es exactamente el lossy esperado (no un comodín).
- **Branch slug (C11):** `_slug(spec.name)` → `[a-z0-9._-]`; default `feature/pipeline-<slug>`.
- **HITL (gate):** `/commit` sin `confirm is True` → 400 y `commit_file` NUNCA se llama (F5 caso 4). Riel absoluto.
- **Dependencias (C3/C4):** NO importar nada de `services/ci_provider.py` ni `services/{gitlab,ado}_ci_provider.py` (Plan 71/72, no requeridos). NO esperar al Plan 74 (este plan le provee el contract). Deps reales: `services/gitlab_provider.py` + `services/ado_provider.py` (Plan 65, ya existen).
- **Mock pattern DB:** importar `db` a nivel módulo; parchear lazy-imports en el módulo origen (memoria `plan-28-lifecycle`).
- **Falsos verdes prohibidos:** F5 caso 4 (HITL gate), F4 casos 3-4 (propagación `TrackerApiError` + idempotencia), F6 caso 3 (round-trip no tautológico) y el centinela de rutas son los gates críticos.
- **Si una fase revela un GAP no listado en F0 matriz**, detener, actualizar este doc y, si el subset cambia, re-auditar el round-trip F6.
- **Post-74:** cuando el migrador haya consumido el `PipelineSpec`, actualizar la matriz F0 con los features adicionales soportados y los gaps descubiertos antes de congelar v1.
