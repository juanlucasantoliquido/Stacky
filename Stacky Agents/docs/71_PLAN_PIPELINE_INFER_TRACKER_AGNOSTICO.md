# Plan 71 — Pipeline-infer tracker-agnóstico (sub-puerto CIProvider)

> **Estado:** PROPUESTO v1.
> **Pre-requisito:** Plan 70 (consumers migrados al puerto `TrackerProvider`) — **DEBE estar implementado primero**.
> **Roadmap:** Segundo eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer agnóstico → trigger CI → creador pipelines → migrador ADO→GitLab → deep links → eval).
> **Versión doc:** v1 (2026-06-27).
> **Dependencias:** Plan 70 (duro). No depende de 72-76. Plan 72 depende de éste.

> **CHANGELOG boceto v0 → v1:**
> - **[DECISIÓN ARQUITECTÓNCICA]** Crear sub-puerto `CIProvider(Protocol)` SEPARADO (principio ISP), NO sobrecargar `TrackerProvider`. Justificación: `TrackerProvider.PORT_METHODS` ya tiene 18 métodos de dominio tracker (items, comentarios, attachments, jerarquía); agregar 3-4 métodos de CI viola segregación de interfaces. `CIProvider` es coherente, chico y consumido únicamente por los planes 71/72/73.
> - **[CONTRATO COMPARTIDO 71/72/73]** `CIProvider` creado en F1 de este plan con 2 métodos en v1 (`infer_item_pipeline`, `monitor_pipeline`). El Plan 72 agrega `trigger_pipeline`. El Plan 73 NO toca `CIProvider` (usa `commit_file` que vive en otro sub-puerto `RepoWriter`, fuera de scope de 71). Todos los contratos están FIJADOS aquí con evidencia de hoy.
> - **[FIX B0-C1]** Tabla F0 con callers verificados in vivo (líneas exactas). No queda "[a verificar]" en callers existentes; el "[a verificar tras implementar Plan 70]" se reserva SOLO para el detalle fino post-migración 70.

---

## 1. Objetivo y KPI

Unificar la inferencia de pipeline de un ítem detrás del **sub-puerto formal `CIProvider`**, de modo que deja de ser ADO-only. Hoy `services/ado_pipeline_inference.py:319 infer_pipeline(ado_id: int, ...)` y `services/pipeline_status.py:199 get_pipeline_status(ticket_id, ado_comments=...)` están casados a ADO (requieren `ado_id` entero y comentarios con regex `RF-\d{3}`); `services/gitlab_provider.py:432 fetch_pipelines(ref)` / `:458 infer_pipeline(ref)` ya existen pero **nadie los invoca** desde el flujo principal (`api/tickets.py`).

**KPI global (DoD):** un proyecto con `issue_tracker.type=gitlab` (y `STACKY_GITLAB_ENABLED=true`, `STACKY_PIPELINE_PROVIDER_ENABLED=true`) devuelve estado de pipeline para un ítem (por `ref` GitLab o por `ado_id` ADO) **sin construir `AdoClient` ni invocar `ado_pipeline_inference.infer_pipeline` en ningún punto del path migrado**. La fuente (`source="ci"` / `"ado_comment"` / `"llm"`) y `tracker_type` se exponen en el reporte.

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy:

- `services/pipeline_status.py:40 _COMMENT_PATTERNS` define regex ADO-específicas sobre HTML de comentarios: `RF-\d{3}` (L42), `ANÁLISIS TÉCNICO — ADO-` (L56). El `source` queda hardcodeado a `"ado_comment"` en `pipeline_status.py:177`.
- `services/pipeline_status.py:199 get_pipeline_status(ticket_id, ado_comments=...)` recibe comentarios ya ADO-formateados; su caller `api/tickets.py:567 client.fetch_comments(ado_id, top=30)` construye `AdoClient` para obtenerlos. Los callers de la familia son `tickets.py:440, 498, 571, 590` (`get_pipeline_summary` / `get_pipeline_status`).
- `services/ado_pipeline_inference.py:319 infer_pipeline(ado_id: int, ...)` tipa `ado_id: int` y cachea en `PipelineInferenceCache.ado_id: int` (`ado_pipeline_inference.py:73`); usa `INFERENCE_MODEL = "gpt-4o-mini"` (L50). Sus callers son `tickets.py:673` (endpoint `/<id>/ado-pipeline-status`) y `tickets.py:715` (endpoint `/ado-pipeline-batch`).
- `services/gitlab_provider.py:432 fetch_pipelines(ref)` / `:458 infer_pipeline(ref)` existen y devuelven `[{source, status, ref, sha, web_url, ...}]`; el comentario L471-475 admite que queda al consumer escalar la inferencia LLM. **Ningún caller en `api/tickets.py`** los invoca hoy.

Resultado: la inferencia de pipeline está particionada; un ítem GitLab no tiene visibilidad de CI desde Stacky.

Sin este plan, el Plan 72 (trigger) y el Plan 73 (generador declarativo) están bloqueados: ambos consumen el sub-puerto `CIProvider` que se crea aquí.

---

## 3. Principios y guardarraíles (heredados del Plan 70)

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API; NO toca prompts ni runtime del agente.
- **Cero trabajo extra al operador**: flag opt-in `STACKY_PIPELINE_PROVIDER_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI"). Flag OFF = byte-idéntico.
- **Human-in-the-loop innegociable**: la bandera la prende el operador; este plan es **solo-lectura** (no trigger).
- **Mono-operador sin auth**: token GitLab en `client_profile`; el PAT requiere `read_api` para F3 (validar en F0).
- **No degradar / backward-compatible**: `infer_pipeline` y `get_pipeline_status` legacy se conservan como fallback con flag OFF.
- **TDD + funciones puras + ratchet + no falsos verdes**: cada fase test-first; patrón mock `assert_called` en cada rama Flag ON (FIX C4 heredado del Plan 70).
- **Prohibido lo vago**: todo sitio, archivo y símbolo citado con `archivo:línea`.

---

## 4. Fases

### F0 — Inventario de callers y dependencias (entregable: tabla F0)

**Trabajo:** abrir cada caller de la familia `pipeline_status.*` / `ado_pipeline_inference.*`, anotar el símbolo exacto y la dependencia ADO concreta. Verificar el scope del PAT GitLab en F3 (`read_api`).

**Tabla F0 — callers verificados in vivo (2026-06-27):**

| # | Archivo:línea helper / caller | Símbolo invocado (args) | Dependencia ADO acoplada | Método `CIProvider` equivalente | Estado |
|---|-------------------------------|--------------------------|---------------------------|----------------------------------|--------|
| 1 | `api/tickets.py:440` | `get_pipeline_summary(t.id)` | None directo (BD local) — pero internamente `pipeline_status.get_pipeline_status(ticket_id, ado_comments=None)` (L255) | `ci_provider.summarize_item_pipeline(item_ref)` | OK (BD local, no ADO) |
| 2 | `api/tickets.py:498` | `get_pipeline_summary(t.id)` | Ídem #1 | Ídem #1 | OK |
| 3 | `api/tickets.py:571` | `get_pipeline_status(ticket_id, ado_comments=ado_comments)` | `ado_comments` obtenido vía `tickets.py:566 _ado_client_for_ticket(...).fetch_comments(ado_id, top=30)` | `ci_provider.infer_item_pipeline(item_ref)` + `provider.fetch_comments(item_id)` para comentarios | **GAP-CI1** (construye AdoClient para comentarios) |
| 4 | `api/tickets.py:590` | `get_pipeline_status(ticket_id, ado_comments=None)` | None directo (BD local) | `ci_provider.infer_item_pipeline(item_ref)` (sin comentarios) | OK (BD local) |
| 5 | `api/tickets.py:673` | `infer_pipeline(ado_id=ado_id, force_refresh=force, model=model, project_name=..., tracker_project=...)` | `ado_id: int` (L567); `INFERENCE_MODEL`; cache `PipelineInferenceCache.ado_id` | `ci_provider.infer_item_pipeline(item_ref)` (adapter ADO envuelve `infer_pipeline`) | **GAP-CI2** (entero ADO + cache key ADO) |
| 6 | `api/tickets.py:715` | `infer_pipeline(ado_id=ticket.ado_id, ...)` (batch) | Ídem #5 | Ídem #5 | **GAP-CI2** |
| 7 | `services/gitlab_provider.py:432` | `fetch_pipelines(ref)` | None (GitLab nativo) | `ci_provider.infer_item_pipeline(item_ref)` (adapter GitLab lo invoca) | OK (ya existe, falta consumir) |
| 8 | `services/gitlab_provider.py:458` | `infer_pipeline(ref)` | None | Ídem #7 | OK (falta consumir) |

**GAPs detectados (alimentan F1/F2):**

- **GAP-CI1** (`get_pipeline_status` necesita `ado_comments` ADO-formateados): `pipeline_status.py:160 _stages_from_comments` aplica `_COMMENT_PATTERNS` (regex `RF-\d{3}`, `ANÁLISIS TÉCNICO — ADO-`). **Decisión:** los patrones son ADO-específicos; cada adapter CI aporta su propia lista de patrones o un fallback neutro. F1 introduce `CommentPatternSet` (dataclass puro) que el adapter entrega al sub-puerto; el adapter ADO usa los actuales, el adapter GitLab usa patrones Markdown (`MERGE REQUEST`, `Pipeline #N passed`, etc.) o un fallback `source="llm"`.
- **GAP-CI2** (`infer_pipeline` cachea por `ado_id: int`): `PipelineInferenceCache.ado_id` (L73) es un `Integer`. Un ítem GitLab no tiene `ado_id`. **Decisión:** F2 introduce una clave de cache agnóstica `(tracker_type, item_ref)` en una tabla nueva `ci_inference_cache` (NO se migra la tabla existente — se conserva como legacy ADO-only). El adapter ADO puede seguir usando la tabla vieja internamente.

**PAT scope F0:** GitLab `fetch_pipelines` requiere `read_api` (no `api`). **Acción F3:** `_check_pat_scopes` lee los scopes del token vía `/personal_access_tokens` (self-hosted) o metadata del `client_profile`; documenta el requisito en el campo `pipeline_provider_error` del response si falta. No bloquee F3 si no se puede verificar; degradar a `source="llm"` con `evidence="PAT scope no verificable"`.

**Criterio binario F0:** la tabla de arriba está completa (8 filas) y cada fila cita `archivo:línea` con el símbolo exacto. **Cumplido en este doc.**

**Trabajo del operador F0:** ninguno.

---

### F1 — Sub-puerto `CIProvider(Protocol)` + tipos compartidos

**Objetivo:** definir el contrato formal del sub-puerto de CI. Es **el contrato compartido de 71/72/73** y queda FIJADO aquí.

**Archivos exactos F1:**
- `services/ci_provider.py` — **archivo nuevo**.
- `services/tracker_provider.py` — **no se modifica** (ISP: CI vive en su propio puerto).

**Símbolos exactos F1 (contrato del sub-puerto, FIJADO):**

```python
# services/ci_provider.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable, Optional

@dataclass(frozen=True)
class ItemRef:
    """Referencia agnóstica a un ítem de tracker + su ref de CI."""
    item_id: str           # "12345" (ADO id) o "42" (GitLab iid)
    tracker_type: str      # "azure_devops" | "gitlab"
    ref: Optional[str] = None   # branch/sha GitLab; None en ADO (usa item_id)

@dataclass(frozen=True)
class PipelineStageInfo:
    stage: str
    done: bool
    source: str            # "ci" | "ado_comment" | "gitlab_note" | "llm" | "stacky_exec"
    confidence: float
    evidence: str | None
    ref: str | None
    web_url: str | None

@dataclass(frozen=True)
class ItemPipelineResult:
    item_ref: ItemRef
    stages: tuple[PipelineStageInfo, ...]
    overall_progress: float
    source: str            # "ci" | "llm" | "stacky_exec"
    raw: dict = field(default_factory=dict)   # payload crudo del tracker para telemetría

    def to_dict(self) -> dict: ...

@runtime_checkable
class CIProvider(Protocol):
    name: str   # "azure_devops" | "gitlab"

    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult: ...
    def monitor_pipeline(self, pipeline_id: str) -> dict: ...

CI_PORT_METHODS: tuple[str, ...] = ("infer_item_pipeline", "monitor_pipeline")
```

**Notas de contrato (FIJADAS para 71/72/73):**
- `infer_item_pipeline` es **solo-lectura** (71). El Plan 72 **agrega** `trigger_pipeline(item_ref, ref) -> dict` a este mismo `Protocol` (es la única extensión del sub-puerto en el bloque 70-76).
- `monitor_pipeline(pipeline_id)` se define aquí pero se **implementa** en F1 de Plan 72 (los adapters lanzan `NotImplementedError` en 71 con un comentario "lo implementa Plan 72 F1"). Esto evita redefinir el `Protocol` después.
- El Plan 73 NO extiende `CIProvider`; usa `commit_file(...)` que pertenece a otro sub-puerto (`RepoWriter`) **fuera de scope del bloque 71-73** (queda como nota en F0 de Plan 73, no se crea aquí).

**Tests F1 (TDD primero):**
- Archivo: `backend/tests/test_plan71_ci_provider_protocol.py`.
- Casos:
  1. `CIProvider` es `runtime_checkable`; un stub con `name`, `infer_item_pipeline`, `monitor_pipeline` pasa `isinstance(x, CIProvider)`.
  2. Un stub sin `infer_item_pipeline` NO pasa `isinstance`.
  3. `ItemPipelineResult.to_dict()` serializa todos los campos (incluido `raw` y `stages` anidados).
  4. `ItemRef` es `frozen`; `tracker_type` y `item_id` son obligatorios, `ref` opcional.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ci_provider_protocol.py -q`.

**Criterio binario F1:** los 4 casos pasan; `ci_provider.py` existe y NO importa nada de ADO ni GitLab (sólo `typing`/`dataclasses`).

**Impacto por runtime:** ninguno (archivo nuevo inerte, sin callers todavía).

**Flag F1:** ninguna (el puerto es puro, sin cablear).

**Trabajo del operador F1:** ninguno.

---

### F2 — Fábrica `get_ci_provider(project)` + tabla de cache agnóstica

**Objetivo:** fábrica espejo de `get_tracker_provider` (`tracker_provider.py:105`) que retorna el `CIProvider` según `issue_tracker.type`; tabla nueva de cache con clave agnóstica.

**Archivos exactos F2:**
- `services/ci_provider.py` — agregar `get_ci_provider(project: Optional[str])` y `TrackerConfigError` reexport o alias local.
- `services/ci_inference_cache.py` — **archivo nuevo** (modelo SQLAlchemy + helpers get/set).
- `models.py` — **no se modifica** (el modelo vive en `ci_inference_cache.py` para mantener el módulo auto-contenido; se registra en `Base` igualmente).

**Símbolos exactos F2:**

```python
# services/ci_provider.py
def get_ci_provider(project: Optional[str] = None) -> CIProvider:
    """Fábrica CIProvider espejo de get_tracker_provider (tracker_provider.py:105)."""
    ctx = resolve_project_context(project_name=project)
    ttype = (getattr(ctx, "tracker_type", None) or "azure_devops").strip().lower()
    if ttype == "gitlab":
        if not getattr(config, "STACKY_GITLAB_ENABLED", False):
            raise TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")
        from services.gitlab_ci_provider import GitLabCIProvider
        return GitLabCIProvider(project=project)
    if ttype == "azure_devops":
        from services.ado_ci_provider import AdoCIProvider
        return AdoCIProvider(project=project)
    raise TrackerConfigError(f"tracker '{ttype}' sin CIProvider")
```

```python
# services/ci_inference_cache.py
class CIInferenceCache(Base):
    __tablename__ = "ci_inference_cache"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tracker_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="ci")
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("ix_ci_cache_key", "tracker_type", "item_id", "ref"),)

def get_cached(tracker_type: str, item_id: str, ref: str | None, ttl_minutes: int = 60) -> dict | None: ...
def set_cached(tracker_type: str, item_id: str, ref: str | None, result: dict, source: str) -> None: ...
```

**Tests F2:**
- Archivo: `backend/tests/test_plan71_ci_cache.py`.
- Casos:
  1. `get_ci_provider("proj-ado")` retorna instancia con `.name == "azure_devops"`.
  2. `get_ci_provider("proj-gitlab")` con `STACKY_GITLAB_ENABLED=false` → `TrackerConfigError`.
  3. `get_ci_provider("proj-gitlab")` con flag true → `.name == "gitlab"`.
  4. `set_cached("gitlab","42","develop",{...},"ci")` + `get_cached(...)` retorna el dict; TTL expirado retorna `None` (mock `datetime`).
  5. Clave compuesta: `(gitlab, 42, develop)` y `(gitlab, 42, main)` son filas distintas.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ci_cache.py -q`.

**Criterio binario F2:** los 5 casos pasan; la tabla `pipeline_inference_cache` vieja NO se toca (legacy ADO-only).

**Impacto por runtime:** ninguno (sin callers aún).

**Flag F2:** ninguna (aún inerte).

**Trabajo del operador F2:** ninguno.

---

### F3 — Adapter ADO `AdoCIProvider`

**Objetivo:** envolver la inferencia ADO existente detrás del sub-puerto, **sin romperla**.

**Archivos exactos F3:**
- `services/ado_ci_provider.py` — **archivo nuevo**.
- `services/ado_pipeline_inference.py` — **no se modifica** (se invoca desde el adapter).

**Símbolos exactos F3:**

```python
# services/ado_ci_provider.py
class AdoCIProvider:
    name = "azure_devops"
    def __init__(self, project: Optional[str] = None):
        self._project = project
    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        # item_ref.item_id es el ado_id como str; convierte a int para infer_pipeline
        ado_id = int(item_ref.item_id)
        legacy = infer_pipeline(ado_id=ado_id, project_name=self._project)
        return _legacy_to_result(legacy, item_ref)   # función PURA
    def monitor_pipeline(self, pipeline_id: str) -> dict:
        raise NotImplementedError("monitor_pipeline se implementa en Plan 72 F1")
```

`_legacy_to_result(legacy, item_ref)` es **función PURA** que mapea `PipelineInferenceResult` (stages dict, source="llm") a `ItemPipelineResult` con `source="llm"`, preservando `stages` y `overall_progress`.

**Tests F3:**
- Archivo: `backend/tests/test_plan71_ado_ci_provider.py`.
- Casos:
  1. `infer_item_pipeline(ItemRef(item_id="12345", tracker_type="azure_devops"))` llama a `infer_pipeline(ado_id=12345, ...)` **[Patrón mock: `mock_infer.assert_called_once_with(ado_id=12345, ...)`]**.
  2. El resultado tiene `source="llm"` y `item_ref.tracker_type="azure_devops"`.
  3. `monitor_pipeline("x")` lanza `NotImplementedError`.
  4. `_legacy_to_result` es pura: mismo input → mismo output (dos llamadas idénticas).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ado_ci_provider.py -q`.

**Criterio binario F3:** los 4 casos pasan; `AdoCIProvider` NO construye `AdoClient` directamente (usa `infer_pipeline` legacy que ya lo hace internamente, pero no acopla más).

**PAT scope ADO F3:** el adapter ADO hereda el uso de credenciales del `infer_pipeline` legacy; no requiere validación nueva.

**Impacto por runtime:** ninguno (sin callers nuevos).

**Trabajo del operador F3:** ninguno.

---

### F4 — Adapter GitLab `GitLabCIProvider`

**Objetivo:** cablear `gitlab_provider.fetch_pipelines`/`infer_pipeline` (ya existentes) al sub-puerto.

**Archivos exactos F4:**
- `services/gitlab_ci_provider.py` — **archivo nuevo**.
- `services/gitlab_provider.py` — **no se modifica** (se invoca desde el adapter).

**Símbolos exactos F4:**

```python
# services/gitlab_ci_provider.py
class GitLabCIProvider:
    name = "gitlab"
    def __init__(self, project: Optional[str] = None):
        self._project = project
        self._delegate = GitLabTrackerProvider(project=project)  # para fetch_pipelines/infer_pipeline
    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        pipelines = self._delegate.infer_pipeline(ref=item_ref.ref)
        # pipelines: [{source:"ci"|"llm", status, ref, sha, web_url, ...}]
        return _pipelines_to_result(pipelines, item_ref)   # PURA
    def monitor_pipeline(self, pipeline_id: str) -> dict:
        raise NotImplementedError("monitor_pipeline se implementa en Plan 72 F1")
```

`_pipelines_to_result(pipelines, item_ref)` es **función PURA**: si hay pipelines con `source="ci"`, arma `ItemPipelineResult` con `source="ci"` y stages derivadas (mapeo `status` GitLab → `PipelineStageInfo`); si fallback `source="llm"`, devuelve `overall_progress=0.0`, `source="llm"`.

**Tests F4:**
- Archivo: `backend/tests/test_plan71_gitlab_ci_provider.py`.
- Casos:
  1. `infer_item_pipeline(ItemRef(item_id="42", tracker_type="gitlab", ref="develop"))` llama a `delegate.infer_pipeline(ref="develop")` **[Patrón mock: `mock_delegate.infer_pipeline.assert_called_once_with(ref="develop")`]**.
  2. Con `delegate.infer_pipeline` retornando `[{source:"ci", status:"success", ref:"develop", sha:"abc", web_url:"http://..."}]` → `result.source == "ci"` y `overall_progress > 0`.
  3. Con `delegate.infer_pipeline` retornando `[{source:"llm", status:"unknown", ref:"develop"}]` → `result.source == "llm"`, `overall_progress == 0.0`.
  4. `monitor_pipeline("x")` lanza `NotImplementedError`.
  5. `_pipelines_to_result` es pura.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_gitlab_ci_provider.py -q`.

**Criterio binario F4:** los 5 casos pasan; `GitLabCIProvider` no llama a `AdoClient` ni a `ado_pipeline_inference` en ningún punto.

**PAT scope GitLab F4:** si `_delegate.infer_pipeline` falla con 403 (falta `read_api`), capturar y devolver `ItemPipelineResult(source="llm", evidence="PAT scope insuficiente")`. **No propagar 403 al caller** (degradar determinista).

**Impacto por runtime:** ninguno.

**Trabajo del operador F4:** ninguno.

---

### F5 — Cableado en `api/tickets.py` (caller #5 y #6: `infer_pipeline`) + flag opt-in

**Objetivo:** migrar los callers ADO-específicos de `infer_pipeline` (`tickets.py:673`, `tickets.py:715`) al sub-puerto, con fallback al path legacy cuando flag OFF.

**Archivos exactos F5:**
- `api/tickets.py` — endpoints `/<int:ticket_id>/ado-pipeline-status` (L656-683) y `/ado-pipeline-batch` (L686-727); agregar helper `_ci_provider_for_ticket(ticket) -> CIProvider | None`.
- `config.py` — nuevo atributo `STACKY_PIPELINE_PROVIDER_ENABLED: bool = False`.
- `harness_defaults.env` — línea `STACKY_PIPELINE_PROVIDER_ENABLED=false`.

**Símbolos exactos F5 (patrón de migración, espejo del Plan 70 F2):**

```python
# api/tickets.py
def _ci_provider_for_ticket(ticket) -> "CIProvider | None":
    """Plan 71 — Devuelve el CIProvider si flag ON; None si OFF (fallback legacy)."""
    if not config.STACKY_PIPELINE_PROVIDER_ENABLED:
        return None
    try:
        return get_ci_provider(ticket.stacky_project_name)
    except TrackerConfigError:
        return None

# Endpoint GET /<int:ticket_id>/ado-pipeline-status (L656):
provider = _ci_provider_for_ticket(t)
if provider is not None:
    item_ref = ItemRef(item_id=str(t.ado_id) if t.ado_id else str(t.id),
                      tracker_type=_tracker_type_for(t), ref=None)
    result = provider.infer_item_pipeline(item_ref)
    return jsonify(result.to_dict())
# fallback legacy (flag OFF):
result = infer_pipeline(ado_id=ado_id, force_refresh=force, model=model, ...)
return jsonify(result.to_dict())
```

El endpoint `/ado-pipeline-batch` (L686) usa el mismo patrón por ítem.

**Helpers PUROS nuevos F5:** `_tracker_type_for(ticket) -> str` (lee `client_profile` del proyecto y devuelve `"azure_devops"` o `"gitlab"`); cacheable por `project_name`.

**Tests F5 (TDD, FIX C4 patrón mock):**
- Archivo: `backend/tests/test_plan71_pipeline_status_endpoint.py`.
- Casos:
  1. Flag OFF + endpoint `/<id>/ado-pipeline-status` → llama `infer_pipeline(ado_id=...)` legacy **[Patrón mock: `mock_infer.assert_called`]**; NO llama al provider.
  2. Flag ON + proyecto ADO → llama `AdoCIProvider.infer_item_pipeline` con `ItemRef(tracker_type="azure_devops")` **[Patrón mock: `mock_provider.infer_item_pipeline.assert_called_once`]**; NO llama legacy.
  3. Flag ON + proyecto gitlab → `.name == "gitlab"`.
  4. Flag ON + provider lanza excepción → response 500 con mensaje (no silent).
  5. `/ado-pipeline-batch` con Flag ON → cada ítem pasa por el provider.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_pipeline_status_endpoint.py -q`.

**Criterio binario F5:** los 5 casos pasan; flag OFF → byte-idéntico al comportamiento pre-plan.

**Impacto por runtime:** ninguno (capa API; no toca prompts).

**Flag F5:** `STACKY_PIPELINE_PROVIDER_ENABLED` default **OFF**, `env_only=False` (UI HarnessFlagsPanel, categoría "Pipelines / CI").

**Trabajo del operador F5:** ninguno (default OFF). Opt-in por UI cuando quiera probar GitLab.

> **[a verificar tras implementar Plan 70]:** el helper `_ci_provider_for_ticket` puede reusar `_provider_for_ticket` del Plan 70 F2 si la firma coincide; hoy se define independiente para no acoplar a 70. Si 70 ya deja `_provider_for_ticket(ticket=t)` expuesto, F5 puede envolverlo en `_ci_provider_for_ticket` como thin wrapper.

---

### F6 — Cableado de `pipeline_status.get_pipeline_status` (caller #3: comentarios ADO)

**Objetivo:** migrar `tickets.py:571 get_pipeline_status(ticket_id, ado_comments=...)` para que los comentarios provengan del `TrackerProvider` (Plan 70) y no de `AdoClient` directo, cuando flag ON.

**Archivos exactos F6:**
- `api/tickets.py` — endpoint `/<int:ticket_id>/pipeline-status` (L553-572); usar `provider.fetch_comments(item_id)` del Plan 70 cuando `_ci_provider_for_ticket` retorne no-None.
- `services/pipeline_status.py` — **no se modifica** (sigue recibiendo `ado_comments: list[dict] | None`); el caller construye la lista.

**Símbolos exactos F6:**

```python
# Reemplaza tickets.py:563-567:
ci_provider = _ci_provider_for_ticket(t)
if ci_provider is not None:
    # Usar TrackerProvider (Plan 70) para comentarios, no AdoClient directo
    tp = _provider_for_ticket(ticket=t)   # helper Plan 70 F2
    ado_comments = tp.fetch_comments(str(ado_id)) if tp else None
else:
    client = _ado_client_for_ticket(ticket=t)
    ado_comments = client.fetch_comments(ado_id, top=30)
```

**Tests F6:**
- Archivo: `backend/tests/test_plan71_pipeline_status_comments.py`.
- Casos:
  1. Flag OFF → construye `AdoClient` y llama `fetch_comments(ado_id, top=30)` **[Patrón mock]**.
  2. Flag ON → llama `TrackerProvider.fetch_comments(str(ado_id))` (no AdoClient) **[Patrón mock: `mock_tp.fetch_comments.assert_called_once_with(str(ado_id))`]**.
  3. `get_pipeline_status` recibe la lista y produce `PipelineStatus` idéntico en ambos branches (mismo input).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_pipeline_status_comments.py -q`.

**Criterio binario F6:** los 3 casos pasan; flag OFF byte-idéntico.

> **[a verificar tras implementar Plan 70]:** `_provider_for_ticket` (Plan 70 F2) debe estar disponible; si no, F6 cae al fallback ADO aun con flag ON (degradación documentada).

**Trabajo del operador F6:** ninguno.

---

### F7 — Observabilidad + centinela + ratchet

**Objetivo:** telemetría (`source`, `tracker_type` en response) y centinela anti-recableo ADO en el path CI.

**Archivos exactos F7:**
- `api/tickets.py` — los endpoints migrados incluyen `tracker_type` y `source` en el JSON response.
- `backend/tests/test_plan71_no_adoclient_in_ci_path.py` — **nuevo centinela**.

**Centinela F7:** en los endpoints `/<id>/ado-pipeline-status` y `/ado-pipeline-batch`, con flag ON, **no debe aparecer** `infer_pipeline(` (legacy) ni `AdoClient(` en el path ejecutado. Se valida con grep contextual sobre el AST del módulo `api.tickets` más un test que ejecuta el endpoint con flag ON y mock del provider y afirma `mock_infer_pipeline.assert_not_called()`.

**Tests F7:**
- Archivo: `backend/tests/test_plan71_no_adoclient_in_ci_path.py`.
- Casos:
  1. Flag ON → `infer_pipeline` legacy NO fue llamada en el path del endpoint **[Patrón mock: `mock_infer.assert_not_called()`]**.
  2. Flag OFF → `infer_pipeline` SÍ fue llamada (control de significancia).
  3. `tracker_type` y `source` están en el JSON response con flag ON.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_no_adoclient_in_ci_path.py -q`.

**Ratchet F7:** registrar TODOS los archivos `test_plan71_*.py` en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49; meta-test F4 verde.

**Criterio binario F7:** los 3 casos pasan; ratchet verde; flag aparece en `harness_defaults.env` y en la UI.

**Trabajo del operador F7:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Patrones ADO no trasladables a GitLab** (GAP-CI1). **Mitigación:** cada adapter CI aporta su `CommentPatternSet` o fallback `source="llm"`; F4 usa patrones Markdown GitLab o degradación determinista.
2. **Cache con clave ADO** (GAP-CI2, `PipelineInferenceCache.ado_id: int`). **Mitigación:** tabla nueva `ci_inference_cache` con clave `(tracker_type, item_id, ref)`; la vieja se conserva legacy.
3. **Falso verde "GitLab devuelve pipeline unknown"** (R3 boceto). **Mitigación:** F4 caso 2 afirma `overall_progress > 0` cuando `source="ci"`; F7 caso 3 afirma `tracker_type` en response.
4. **PAT GitLab sin `read_api`**. **Mitigación:** F4 captura 403 y degrada a `source="llm"` con evidence; no propaga 403.
5. **Acoplamiento a Plan 70.** Si `_provider_for_ticket` (Plan 70 F2) no está disponible, F6 cae a fallback ADO con flag ON (degradación documentada en F6). F5 no depende de 70 (define `_ci_provider_for_ticket` propio).
6. **3 runtimes.** **Mitigación:** el plan no toca prompts/runtime del agente; sólo capa de servicios/API.

---

## 6. Fuera de scope

- **NO** disparar/monitorear pipelines (Plan 72 — `monitor_pipeline` se define pero lanza `NotImplementedError` en 71).
- **NO** generar pipelines YAML declarativos (Plan 73).
- **NO** migración ADO→GitLab (Plan 74).
- **NO** deep links visuales a pipelines (Plan 75).
- **NO** migrar la tabla `pipeline_inference_cache` vieja (legacy ADO-only).
- **NO** reconstruir el puerto `TrackerProvider` (Plan 65) ni migrar consumers (Plan 70).

---

## 7. Glosario

- **TrackerProvider:** `Protocol` formal (`services/tracker_provider.py:56`) con 18 métodos (`PORT_METHODS`, L79-98). NO se toca en este plan.
- **CIProvider:** nuevo `Protocol` (`services/ci_provider.py`, F1 de este plan) con 2 métodos en v1 (`infer_item_pipeline`, `monitor_pipeline`). El Plan 72 agrega `trigger_pipeline`. **Contrato compartido de 71/72/73.**
- **`CI_PORT_METHODS`:** tupla canónica `("infer_item_pipeline", "monitor_pipeline")`.
- **`ItemRef`:** dataclass agnóstica `(item_id, tracker_type, ref)` — referencia al ítem + ref de CI (branch/sha GitLab; None ADO).
- **`ItemPipelineResult`:** dataclass resultado con `stages`, `source`, `overall_progress`, `raw`.
- **`_COMMENT_PATTERNS`:** dict de regex ADO-específicas (`pipeline_status.py:40`); cada adapter CI aporta las suyas o un fallback.
- **`infer_pipeline`:** dos símbolos con el mismo nombre — `ado_pipeline_inference.py:319` (ADO, `ado_id: int`) y `gitlab_provider.py:458` (GitLab, `ref`). F3/F4 los envuelven.
- **`fetch_pipelines`:** `gitlab_provider.py:432`, GitLab nativo.
- **`get_pipeline_status` / `get_pipeline_summary`:** `pipeline_status.py:199` / `:243`.
- **`PipelineInferenceCache`:** modelo legacy ADO-only (`ado_pipeline_inference.py:69`, clave `ado_id`). NO se migra; tabla nueva `ci_inference_cache`.
- **`get_ci_provider`:** fábrica nueva espejo de `get_tracker_provider` (`tracker_provider.py:105`).
- **`STACKY_PIPELINE_PROVIDER_ENABLED`:** flag nueva de este plan (default OFF, editable por UI).

---

## 8. Orden de implementación

1. **F0** — Inventario (cumplido en este doc, 8 filas).
2. **F1** — Sub-puerto `CIProvider(Protocol)` + tipos `ItemRef`/`ItemPipelineResult`/`PipelineStageInfo`.
3. **F2** — Fábrica `get_ci_provider` + tabla `ci_inference_cache`.
4. **F3** — Adapter `AdoCIProvider` (envuelve `infer_pipeline` legacy).
5. **F4** — Adapter `GitLabCIProvider` (envuelve `fetch_pipelines`/`infer_pipeline` existentes).
6. **F5** — Cableado en `api/tickets.py` (callers #5/#6: `/<id>/ado-pipeline-status` + `/ado-pipeline-batch`) + flag `STACKY_PIPELINE_PROVIDER_ENABLED`.
7. **F6** — Cableado `get_pipeline_status` (caller #3: comentarios vía `TrackerProvider`).
8. **F7** — Observabilidad + centinela + ratchet.

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Tabla F0 completa y verificada (8 filas, cada fila cita `archivo:línea`). **Cumplido en este doc.**
- [ ] **(b)** Sub-puerto `CIProvider` creado con `infer_item_pipeline` + `monitor_pipeline` (F1); adapters ADO y GitLab implementan `infer_item_pipeline` (F3/F4).
- [ ] **(b')** `monitor_pipeline` definido en el `Protocol` y lanza `NotImplementedError` en ambos adapters (lo implementa Plan 72 F1).
- [ ] **(c)** Callers #5/#6 (`tickets.py:673`, `tickets.py:715`) migrados con branch provider + fallback legacy (F5).
- [ ] **(d)** Caller #3 (`tickets.py:571`) obtiene comentarios vía `TrackerProvider` cuando flag ON (F6, gated por disponibilidad de Plan 70).
- [ ] **(e)** Flag `STACKY_PIPELINE_PROVIDER_ENABLED` default **OFF**; byte-idéntico con flag OFF (F5/F6 lo verifican).
- [ ] **(f)** Un proyecto `gitlab` con flag ON devuelve `tracker_type="gitlab"` y `source` en `{"ci","llm"}` sin construir `AdoClient` ni llamar `infer_pipeline` legacy (centinela F7).
- [ ] **(g)** Los 3 runtimes operativos sin cambios.
- [ ] **(h)** Ratchet verde (Plan 49 F4) con los 7 archivos `test_plan71_*.py` registrados.

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`. Venv py3.13; correr tests por archivo.
- **Patrón mock (FIX C4 heredado):** `mock_provider.return_value = Mock(name="gitlab")` (nunca None) + `mock_provider.infer_item_pipeline.assert_called_once_with(ItemRef(...))`. Para afirmar que el legacy NO fue llamado: `mock_infer.assert_not_called()`.
- **Mock pattern DB:** importar `db` a nivel módulo; lazy-imports se parchean en el módulo origen (memoria `plan-28-lifecycle`).
- **Cada commit deja el sistema verde y backward-compatible.**
- **Falsos verdes prohibidos:** cada test "Flag ON → provider llamado" afirma `assert_called`; cada test "Flag ON → legacy no llamado" afirma `assert_not_called`.
- **Si una fase revela un GAP no listado en F0**, detener y actualizar este doc antes de seguir.
- **Post-70:** si `_provider_for_ticket` (Plan 70 F2) ya está disponible, F6 puede reusarlo; si no, cae a fallback ADO documentado.
