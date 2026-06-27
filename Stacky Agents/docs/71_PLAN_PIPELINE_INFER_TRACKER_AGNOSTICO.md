# Plan 71 — Pipeline-infer tracker-agnóstico (sub-puerto CIProvider)

> **Estado:** PROPUESTO v2 (corrección de C1..C9 + [ADICIÓN ARQUITECTO]).
> **Pre-requisito:** Plan 70 (consumers migrados al puerto `TrackerProvider`) — **DEBE estar implementado primero**. Verificado 2026-06-27: Plan 70 v2 existe en doc pero **NO implementado** (`_provider_for_ticket` ausente, `STACKY_TICKETS_PROVIDER_ENABLED` ausente en config.py). F6 queda gated tras Plan 70.
> **Roadmap:** Segundo eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer agnóstico → trigger CI → creador pipelines → migrador ADO→GitLab → deep links → eval).
> **Versión doc:** v2 (2026-06-27).
> **Dependencias:** Plan 70 (duro para F6; F1-F5 NO dependen de 70). No depende de 72-76. Plan 72 depende de éste.

> **CHANGELOG v1 → v2:**
> - **[FIX C1 BLOQUEANTE]** F2: wiring explícito de `ci_inference_cache` a `Base.metadata.create_all`. Stacky NO usa alembic; create_all (models.py:464/497) sólo ve tablas de módulos importados al arranque. Se añade fase F2-bis con import-registry + test de creación de tabla.
> - **[FIX C2 IMPORTANTE]** F3: `_legacy_to_result` tipa `PipelineInferenceResult` (clase, ado_pipeline_inference.py:109) NO dict; firma exacta documentada.
> - **[FIX C3 IMPORTANTE]** F4: keys reales del dict GitLab verificadas `source/status/ref/sha/web_url` (gitlab_provider.py:437-441); NO existe `confidence` ni `overall_progress` en el payload → `_pipelines_to_result` los DERIVA con regla determinista explícita.
> - **[FIX C4 IMPORTANTE]** F7: centinela reforzado con **gate de significancia anti-falso-verde** (test que FALLA si flag ON pero provider nunca llamado). Referencia corregida: `HARNESS_TEST_FILES` vive en `tests/harness_ratchet_allowlist.txt` (NO sh/ps1).
> - **[FIX C5 IMPORTANTE]** F5: `ItemRef(item_id=str(t.ado_id) if t.ado_id else str(t.id))` era semánticamente roto para GitLab (`t.id` local no existe en GitLab). Se usa `tracker_project_item_id` del Ticket (o `ado_id` para ADO) con regla explícita.
> - **[FIX C6 MENOR]** F1: `CI_PORT_METHODS` congelado + `test_ci_port_methods_is_frozen` (anti-drift del contrato compartido 71/72/73).
> - **[FIX C7 MENOR]** Patrón mock ItemRef(frozen): equality funciona; se norma "construir con `ref=None` explícito" para evitar falsos negativos.
> - **[FIX C8 MENOR]** F6: dependencia de Plan 70 explicitada como BLOQUEO (no "a verificar"); si 70 no está, F6 se POSPONE (no cae a fallback silencioso con flag ON = falso verde).
> - **[FIX C9 MENOR]** Batch endpoint: el provider se resuelve **por proyecto del ticket**, no por request; batch mixto (varios proyectos) resuelve provider por item y degrada a legacy los que no tengan tracker gitlab.
> - **[ADICIÓN ARQUITECTO]** **Telemetría de coverage por `tracker_type`** en endpoint (campo `ci_provider_coverage` en response + metric acumulada en `harness_health`). Permite al operador ver cuántos ítems atiende cada adapter y detectar degradación silenciosa a `source="llm"`. Además: **contract test del sub-puerto** (`test_ci_port_methods_is_frozen`) que valida el freeze del contrato compartido.

> **CHANGELOG boceto v0 → v1 (preservado):**
> - **[DECISIÓN ARQUITECTÓNICA]** Sub-puerto `CIProvider(Protocol)` SEPARADO (principio ISP), NO sobrecargar `TrackerProvider`.
> - **[CONTRATO COMPARTIDO 71/72/73]** `CIProvider` creado en F1 con 2 métodos en v1 (`infer_item_pipeline`, `monitor_pipeline`). Plan 72 agrega `trigger_pipeline`. Plan 73 NO toca `CIProvider`.
> - **[FIX B0-C1]** Tabla F0 con callers verificados in vivo.

---

## 1. Objetivo y KPI

Unificar la inferencia de pipeline de un ítem detrás del **sub-puerto formal `CIProvider`**, de modo que deja de ser ADO-only. Hoy `services/ado_pipeline_inference.py:319 infer_pipeline(ado_id: int, ...)` y `services/pipeline_status.py:199 get_pipeline_status(ticket_id, ado_comments=...)` están casados a ADO (requieren `ado_id` entero y comentarios con regex `RF-\d{3}`); `services/gitlab_provider.py:432 fetch_pipelines(ref) -> list[dict]` / `:458 infer_pipeline(ref) -> list[dict]` ya existen (verificadas sus keys: `source/status/ref/sha/web_url`, gitlab_provider.py:437-441 + docstring L460-464) pero **nadie los invoca** desde el flujo principal (`api/tickets.py`).

**KPI global (DoD):** un proyecto con `issue_tracker.type=gitlab` (y `STACKY_GITLAB_ENABLED=true`, `STACKY_PIPELINE_PROVIDER_ENABLED=true`) devuelve estado de pipeline para un ítem (por `ref` GitLab o por `ado_id` ADO) **sin construir `AdoClient` ni invocar `ado_pipeline_inference.infer_pipeline` en ningún punto del path migrado**. La fuente (`source="ci"` / `"ado_comment"` / `"llm"`) y `tracker_type` se exponen en el reporte, junto con `ci_provider_coverage` por tracker_type (**[ADICIÓN ARQUITECTO]**).

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy (2026-06-27):

- `services/pipeline_status.py:40 _COMMENT_PATTERNS` define regex ADO-específicas sobre HTML de comentarios: `RF-\d{3}` (L42), `ANÁLISIS TÉCNICO — ADO-` (L56). El `source` queda hardcodeado a `"ado_comment"` en `pipeline_status.py:177`.
- `services/pipeline_status.py:199 get_pipeline_status(ticket_id, ado_comments=...)` recibe comentarios ya ADO-formateados; su caller `api/tickets.py:567 client.fetch_comments(ado_id, top=30)` construye `AdoClient` para obtenerlos. Los callers de la familia son `tickets.py:440, 498, 571, 590` (`get_pipeline_summary` / `get_pipeline_status`).
- `services/ado_pipeline_inference.py:319 infer_pipeline(ado_id: int, ...)` tipa `ado_id: int` y cachea en `PipelineInferenceCache.ado_id: int` (`ado_pipeline_inference.py:73`); usa `INFERENCE_MODEL = "gpt-4o-mini"` (L50). Devuelve `PipelineInferenceResult` (clase, **NO** dict) definida en `ado_pipeline_inference.py:109` con atributo `ado_id: int` (L121). Sus callers son `tickets.py:673` (endpoint `/<id>/ado-pipeline-status`) y `tickets.py:715` (endpoint `/ado-pipeline-batch`).
- `services/gitlab_provider.py:432 fetch_pipelines(ref) -> list[dict]` / `:458 infer_pipeline(ref) -> list[dict]` existen y devuelven `[{"source","status","ref","sha","web_url"}]` (verificado L437-441); el docstring L460-464 admite que queda al consumer escarlar la inferencia LLM. **Ningún caller en `api/tickets.py`** los invoca hoy.

Resultado: la inferencia de pipeline está particionada; un ítem GitLab no tiene visibilidad de CI desde Stacky.

Sin este plan, el Plan 72 (trigger) y el Plan 73 (generador declarativo) están bloqueados: ambos consumen el sub-puerto `CIProvider` que se crea aquí.

---

## 3. Principios y guardarraíles (heredados del Plan 70)

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API; NO toca prompts ni runtime del agente.
- **Cero trabajo extra al operador**: flag opt-in `STACKY_PIPELINE_PROVIDER_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI"). Flag OFF = byte-idéntico.
- **Human-in-the-loop innegociable**: la bandera la prende el operador; este plan es **solo-lectura** (no trigger).
- **Mono-operador sin auth**: token GitLab en `client_profile`; el PAT requiere `read_api` para F4 (validar en F0/F4).
- **No degradar / backward-compatible**: `infer_pipeline` y `get_pipeline_status` legacy se conservan como fallback con flag OFF.
- **TDD + funciones puras + ratchet + no falsos verdes**: cada fase test-first; patrón mock `assert_called` en cada rama Flag ON + **gate de significancia** (FIX C4: si flag ON, el provider DEBE ser llamado al menos una vez; si no, el test FALLA — detecta wiring roto que produce falso verde silencioso).
- **Prohibido lo vago**: todo sitio, archivo y símbolo citado con `archivo:línea`.

---

## 4. Fases

### F0 — Inventario de callers y dependencias (entregable: tabla F0)

**Trabajo:** abrir cada caller de la familia `pipeline_status.*` / `ado_pipeline_inference.*`, anotar el símbolo exacto y la dependencia ADO concreta. Verificar el scope del PAT GitLab en F4 (`read_api`).

**Tabla F0 — callers verificados in vivo (2026-06-27):**

| # | Archivo:línea helper / caller | Símbolo invocado (args) | Dependencia ADO acoplada | Método `CIProvider` equivalente | Estado |
|---|-------------------------------|--------------------------|---------------------------|----------------------------------|--------|
| 1 | `api/tickets.py:440` | `get_pipeline_summary(t.id)` | None directo (BD local) — pero internamente `pipeline_status.get_pipeline_status(ticket_id, ado_comments=None)` (L255) | `ci_provider.summarize_item_pipeline(item_ref)` | OK (BD local, no ADO) |
| 2 | `api/tickets.py:498` | `get_pipeline_summary(t.id)` | Ídem #1 | Ídem #1 | OK |
| 3 | `api/tickets.py:571` | `get_pipeline_status(ticket_id, ado_comments=ado_comments)` | `ado_comments` obtenido vía `tickets.py:566 _ado_client_for_ticket(...).fetch_comments(ado_id, top=30)` | `ci_provider.infer_item_pipeline(item_ref)` + `provider.fetch_comments(item_id)` para comentarios | **GAP-CI1** (construye AdoClient para comentarios) |
| 4 | `api/tickets.py:590` | `get_pipeline_status(ticket_id, ado_comments=None)` | None directo (BD local) | `ci_provider.infer_item_pipeline(item_ref)` (sin comentarios) | OK (BD local) |
| 5 | `api/tickets.py:673` | `infer_pipeline(ado_id=ado_id, force_refresh=force, model=model, project_name=..., tracker_project=...)` | `ado_id: int`; `INFERENCE_MODEL`; cache `PipelineInferenceCache.ado_id`; devuelve **`PipelineInferenceResult`** (clase, ado_pipeline_inference.py:109) | `ci_provider.infer_item_pipeline(item_ref)` (adapter ADO envuelve `infer_pipeline`) | **GAP-CI2** (entero ADO + cache key ADO + tipo retorno clase) |
| 6 | `api/tickets.py:715` | `infer_pipeline(ado_id=ticket.ado_id, ...)` (batch) | Ídem #5; batch puede contener tickets de **distintos proyectos** (FIX C9) | Ídem #5 (resolución provider **por item**) | **GAP-CI2** |
| 7 | `services/gitlab_provider.py:432` | `fetch_pipelines(ref) -> list[dict]` (keys: source/status/ref/sha/web_url) | None (GitLab nativo) | `ci_provider.infer_item_pipeline(item_ref)` (adapter GitLab lo invoca) | OK (ya existe, falta consumir) |
| 8 | `services/gitlab_provider.py:458` | `infer_pipeline(ref) -> list[dict]` (mismas keys) | None | Ídem #7 | OK (falta consumir) |

**GAPs detectados (alimentan F1/F2):**

- **GAP-CI1** (`get_pipeline_status` necesita `ado_comments` ADO-formateados): `pipeline_status.py:160 _stages_from_comments` aplica `_COMMENT_PATTERNS` (regex `RF-\d{3}`, `ANÁLISIS TÉCNICO — ADO-`). **Decisión:** los patrones son ADO-específicos; cada adapter CI aporta su propia lista de patrones o un fallback neutro. F1 introduce `CommentPatternSet` (dataclass puro) que el adapter entrega al sub-puerto; el adapter ADO usa los actuales, el adapter GitLab usa patrones Markdown (`MERGE REQUEST`, `Pipeline #N passed`, etc.) o un fallback `source="llm"`.
- **GAP-CI2** (`infer_pipeline` cachea por `ado_id: int` y devuelve `PipelineInferenceResult` clase): `PipelineInferenceCache.ado_id` (L73) es un `Integer`. Un ítem GitLab no tiene `ado_id`. **Decisión:** F2 introduce una clave de cache agnóstica `(tracker_type, item_ref)` en una tabla nueva `ci_inference_cache` (NO se migra la tabla existente — se conserva como legacy ADO-only). El adapter ADO puede seguir usando la tabla vieja internamente. El tipo de retorno `PipelineInferenceResult` (NO dict) se mapea en `_legacy_to_result` (FIX C2 en F3).

**PAT scope F0:** GitLab `fetch_pipelines` requiere `read_api` (no `api`). **Acción F4:** `_check_pat_scopes` lee los scopes del token vía `/personal_access_tokens` (self-hosted) o metadata del `client_profile`; documenta el requisito en el campo `pipeline_provider_error` del response si falta. No bloquee F4 si no se puede verificar; degradar a `source="llm"` con `evidence="PAT scope no verificable"`.

**Criterio binario F0:** la tabla de arriba está completa (8 filas) y cada fila cita `archivo:línea` con el símbolo exacto. **Cumplido en este doc.**

**Trabajo del operador F0:** ninguno.

---

### F1 — Sub-puerto `CIProvider(Protocol)` + tipos compartidos + congelado de contrato

**Objetivo:** definir el contrato formal del sub-puerto de CI. Es **el contrato compartido de 71/72/73** y queda FIJADO y **CONGELADO** aquí (FIX C6).

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
# FIX C6: tupla CONGELADA — anti-drift del contrato compartido 71/72/73.
# Cualquier adición (Plan 72 agrega trigger_pipeline) requiere actualizar
# test_ci_port_methods_is_frozen explícitamente.
```

**Notas de contrato (FIJADAS para 71/72/73):**
- `infer_item_pipeline` es **solo-lectura** (71). El Plan 72 **agrega** `trigger_pipeline(item_ref, ref) -> dict` a este mismo `Protocol` (es la única extensión del sub-puerto en el bloque 70-76). Al hacerlo debe actualizar `CI_PORT_METHODS` y el test de freeze.
- `monitor_pipeline(pipeline_id)` se define aquí pero se **implementa** en F1 de Plan 72 (los adapters lanzan `NotImplementedError` en 71 con un comentario "lo implementa Plan 72 F1").
- El Plan 73 NO extiende `CIProvider`; usa `commit_file(...)` que pertenece a otro sub-puerto (`RepoWriter`) **fuera de scope del bloque 71-73**.

**Tests F1 (TDD primero):**
- Archivo: `backend/tests/test_plan71_ci_provider_protocol.py`.
- Casos:
  1. `CIProvider` es `runtime_checkable`; un stub con `name`, `infer_item_pipeline`, `monitor_pipeline` pasa `isinstance(x, CIProvider)`.
  2. Un stub sin `infer_item_pipeline` NO pasa `isinstance`.
  3. `ItemPipelineResult.to_dict()` serializa todos los campos (incluido `raw` y `stages` anidados).
  4. `ItemRef` es `frozen`; `tracker_type` y `item_id` son obligatorios, `ref` opcional. Equality: `ItemRef(item_id="42", tracker_type="gitlab") == ItemRef(item_id="42", tracker_type="gitlab", ref=None)` (FIX C7: construir siempre con `ref=None` explícito en callers para evitar falsos negativos en mocks).
  5. **[ADICIÓN ARQUITECTO / FIX C6]** `test_ci_port_methods_is_frozen`: `CI_PORT_METHODS == ("infer_item_pipeline", "monitor_pipeline")`. Si alguien agrega un método sin actualizar este test, FALLA (anti-drift del contrato compartido).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ci_provider_protocol.py -q`.

**Criterio binario F1:** los 5 casos pasan; `ci_provider.py` existe y NO importa nada de ADO ni GitLab (sólo `typing`/`dataclasses`).

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
from sqlalchemy import Integer, String, Text, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from models import Base   # Base centralizada en models.py

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

### F2-bis — Wiring de la tabla nueva a create_all (FIX C1 BLOQUEANTE)

**Problema (verificado):** Stacky NO usa alembic. Las tablas se crean vía `Base.metadata.create_all` al arranque (models.py:464/497). `create_all` **sólo ve las tablas de los módulos importados** antes de ejecutarse. Si `ci_inference_cache.py` no se importa en el boot, la tabla `ci_inference_cache` **NUNCA se crea** en DBs existentes → runtime error `no such table`.

**Trabajo F2-bis:**
1. Registrar el modelo en el import-registry del arranque. Verificar dónde `app.py` (o `models.py`) importa los modelos antes del `create_all`; agregar `import services.ci_inference_cache  # noqa: F401  # registro de CIInferenceCache en Base.metadata` en ese punto exacto (inspeccionar `backend/app.py` y el bloque de imports de modelos en `models.py` antes de `create_all` durante F2-bis; si el create_all se invoca desde `app.py`, el import va ahí).
2. El import debe ser **idempotente** (un `import` re-ejecutado es no-op) y **no romper el arranque** si la tabla ya existe (`create_all` es no-destructivo por diseño).

**Tests F2-bis (TDD primero):**
- Archivo: `backend/tests/test_plan71_ci_cache_table_created.py`.
- Casos:
  1. Tras `import services.ci_inference_cache` + `Base.metadata.create_all(bind=engine)` sobre una SQLite en memoria, la tabla `ci_inference_cache` existe (consulta a `sqlite_master` o `inspect(engine).has_table("ci_inference_cache")`).
  2. **Sin** el import del punto 1, `has_table` retorna `False` (test de regresión que documenta por qué el wiring es obligatorio).
  3. Idempotencia: dos `create_all` consecutivos no levantan error y la tabla queda única.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ci_cache_table_created.py -q`.

**Criterio binario F2-bis:** los 3 casos pasan. **SIN esta fase, F2 es humo** (la tabla no llega a la DB).

**Tests F2 (fábrica + helpers):**
- Archivo: `backend/tests/test_plan71_ci_cache.py`.
- Casos:
  1. `get_ci_provider("proj-ado")` retorna instancia con `.name == "azure_devops"`.
  2. `get_ci_provider("proj-gitlab")` con `STACKY_GITLAB_ENABLED=false` → `TrackerConfigError`.
  3. `get_ci_provider("proj-gitlab")` con flag true → `.name == "gitlab"`.
  4. `set_cached("gitlab","42","develop",{...},"ci")` + `get_cached(...)` retorna el dict; TTL expirado retorna `None` (mock `datetime`).
  5. Clave compuesta: `(gitlab, 42, develop)` y `(gitlab, 42, main)` son filas distintas.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ci_cache.py -q`.

**Criterio binario F2:** F2-bis verde + los 5 casos pasan; la tabla `pipeline_inference_cache` vieja NO se toca (legacy ADO-only).

**Impacto por runtime:** ninguno (sin callers aún).

**Flag F2:** ninguna (aún inerte).

**Trabajo del operador F2:** ninguno.

---

### F3 — Adapter ADO `AdoCIProvider`

**Objetivo:** envolver la inferencia ADO existente detrás del sub-puerto, **sin romperla**.

**Archivos exactos F3:**
- `services/ado_ci_provider.py` — **archivo nuevo**.
- `services/ado_pipeline_inference.py` — **no se modifica** (se invoca desde el adapter).

**Símbolos exactos F3 (FIX C2 — tipo retorno `PipelineInferenceResult` clase, NO dict):**

```python
# services/ado_ci_provider.py
from services.ado_pipeline_inference import infer_pipeline, PipelineInferenceResult

class AdoCIProvider:
    name = "azure_devops"
    def __init__(self, project: Optional[str] = None):
        self._project = project
    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        # item_ref.item_id es el ado_id como str; convierte a int para infer_pipeline
        ado_id = int(item_ref.item_id)
        # infer_pipeline devuelve PipelineInferenceResult (ado_pipeline_inference.py:109), NO dict.
        # Firma: infer_pipeline(ado_id:int, force_refresh:bool=False, model:str=INFERENCE_MODEL,
        #                       project_name:str|None=None, tracker_project:str|None=None)
        legacy: PipelineInferenceResult = infer_pipeline(ado_id=ado_id, project_name=self._project)
        return _legacy_to_result(legacy, item_ref)   # función PURA
    def monitor_pipeline(self, pipeline_id: str) -> dict:
        raise NotImplementedError("monitor_pipeline se implementa en Plan 72 F1")
```

`_legacy_to_result(legacy: PipelineInferenceResult, item_ref: ItemRef) -> ItemPipelineResult` es **función PURA**. Mapeo explícito (FIX C2):
- `legacy.ado_id` (int) → se descarta (ya está en `item_ref.item_id`).
- `legacy.stages` (atributo del dataclass, verificado existencia en ado_pipeline_inference.py:109-140) → se mapea 1:1 a `tuple[PipelineStageInfo(...)]`; cada stage hereda `source="llm"` (el legacy usa `INFERENCE_MODEL="gpt-4o-mini"`, L50) y `confidence` del legacy si lo expone, si no `confidence=0.5`.
- `legacy.overall_progress` (si existe) → se conserva; si no, se deriva como `mean(done for stage)`.
- `result.source = "llm"` (el legacy es LLM-based).
- `result.raw = legacy.to_dict()` (ado_pipeline_inference.py:132 expone `to_dict`).

**Tests F3:**
- Archivo: `backend/tests/test_plan71_ado_ci_provider.py`.
- Casos:
  1. `infer_item_pipeline(ItemRef(item_id="12345", tracker_type="azure_devops", ref=None))` llama a `infer_pipeline(ado_id=12345, project_name=...)` **[Patrón mock: `mock_infer.assert_called_once_with(ado_id=12345, project_name=ANY)` — FIX C2: kwargs exactos, `model` y `force_refresh` NO se pasan desde el adapter salvo que el caller original los provea; el adapter usa defaults]**.
  2. El resultado tiene `source="llm"` y `item_ref.tracker_type="azure_devops"`.
  3. `monitor_pipeline("x")` lanza `NotImplementedError`.
  4. `_legacy_to_result` es pura: mismo input → mismo output (dos llamadas idénticas).
  5. FIX C2: el adapter acepta un `PipelineInferenceResult` mock con `.stages`/`.overall_progress`/`.to_dict()` y NO levanta `AttributeError`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_ado_ci_provider.py -q`.

**Criterio binario F3:** los 5 casos pasan; `AdoCIProvider` NO construye `AdoClient` directamente (usa `infer_pipeline` legacy que ya lo hace internamente, pero no acopla más).

**PAT scope ADO F3:** el adapter ADO hereda el uso de credenciales del `infer_pipeline` legacy; no requiere validación nueva.

**Impacto por runtime:** ninguno (sin callers nuevos).

**Trabajo del operador F3:** ninguno.

---

### F4 — Adapter GitLab `GitLabCIProvider`

**Objetivo:** cablear `gitlab_provider.fetch_pipelines`/`infer_pipeline` (ya existentes) al sub-puerto.

**Archivos exactos F4:**
- `services/gitlab_ci_provider.py` — **archivo nuevo**.
- `services/gitlab_provider.py` — **no se modifica** (se invoca desde el adapter).

**Símbolos exactos F4 (FIX C3 — keys reales verificadas):**

```python
# services/gitlab_ci_provider.py
class GitLabCIProvider:
    name = "gitlab"
    def __init__(self, project: Optional[str] = None):
        self._project = project
        self._delegate = GitLabTrackerProvider(project=project)  # para fetch_pipelines/infer_pipeline
    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult:
        # item_ref.ref es la branch/sha GitLab; item_ref.item_id es el iid (no usado por fetch_pipelines).
        pipelines = self._delegate.infer_pipeline(ref=item_ref.ref)
        # FIX C3: pipelines es list[dict] con keys EXACTAS {source, status, ref, sha, web_url}
        # (gitlab_provider.py:437-441). NO hay 'confidence' ni 'overall_progress'.
        return _pipelines_to_result(pipelines, item_ref)   # PURA
    def monitor_pipeline(self, pipeline_id: str) -> dict:
        raise NotImplementedError("monitor_pipeline se implementa en Plan 72 F1")
```

`_pipelines_to_result(pipelines: list[dict], item_ref: ItemRef) -> ItemPipelineResult` es **función PURA** con regla **determinista explícita** (FIX C3, elimina ambigüedad):

```python
def _pipelines_to_result(pipelines, item_ref):
    if not pipelines:
        return ItemPipelineResult(item_ref=item_ref, stages=(), overall_progress=0.0,
                                  source="llm", raw={"reason": "no pipelines"})
    # Priorizar source="ci" si existe al menos uno
    ci_pipelines = [p for p in pipelines if p.get("source") == "ci"]
    chosen = ci_pipelines if ci_pipelines else pipelines
    # FIX C3: overall_progress se DERIVA del status de GitLab (NO viene en el dict):
    #   status "success" -> 1.0 ; "failed" -> 0.0 ; "running"/"pending" -> 0.5 ; otro -> 0.0
    STATUS_TO_PROGRESS = {"success": 1.0, "failed": 0.0, "running": 0.5, "pending": 0.5}
    progresses = [STATUS_TO_PROGRESS.get((p.get("status") or "").lower(), 0.0) for p in chosen]
    overall = sum(progresses) / len(progresses) if progresses else 0.0
    source = "ci" if ci_pipelines else "llm"
    stages = tuple(
        PipelineStageInfo(stage="ci", done=(p.get("status") == "success"),
                          source=source, confidence=1.0 if source == "ci" else 0.3,
                          evidence=f"gitlab status={p.get('status')}",
                          ref=p.get("ref"), web_url=p.get("web_url"))
        for p in chosen
    )
    return ItemPipelineResult(item_ref=item_ref, stages=stages,
                              overall_progress=overall, source=source, raw={"pipelines": chosen})
```

**Tests F4:**
- Archivo: `backend/tests/test_plan71_gitlab_ci_provider.py`.
- Casos:
  1. `infer_item_pipeline(ItemRef(item_id="42", tracker_type="gitlab", ref="develop"))` llama a `delegate.infer_pipeline(ref="develop")` **[Patrón mock: `mock_delegate.infer_pipeline.assert_called_once_with(ref="develop")`]**.
  2. FIX C3: con `delegate.infer_pipeline` retornando `[{"source":"ci","status":"success","ref":"develop","sha":"abc","web_url":"http://..."}]` → `result.source == "ci"` y `overall_progress == 1.0` (regla `STATUS_TO_PROGRESS["success"]=1.0`).
  3. FIX C3: con status `"running"` → `overall_progress == 0.5`.
  4. FIX C3: con `delegate.infer_pipeline` retornando `[{"source":"llm","status":"unknown","ref":"develop"}]` → `result.source == "llm"`, `overall_progress == 0.0`.
  5. FIX C3: con `delegate.infer_pipeline` retornando `[]` → `result.source == "llm"`, `overall_progress == 0.0`, `raw["reason"] == "no pipelines"`.
  6. `monitor_pipeline("x")` lanza `NotImplementedError`.
  7. `_pipelines_to_result` es pura.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_gitlab_ci_provider.py -q`.

**Criterio binario F4:** los 7 casos pasan; `GitLabCIProvider` no llama a `AdoClient` ni a `ado_pipeline_inference` en ningún punto.

**PAT scope GitLab F4:** si `_delegate.infer_pipeline` falla con 403 (falta `read_api`), capturar y devolver `ItemPipelineResult(source="llm", stages=(), overall_progress=0.0, evidence="PAT scope insuficiente")`. **No propagar 403 al caller** (degradar determinista).

**Impacto por runtime:** ninguno.

**Trabajo del operador F4:** ninguno.

---

### F5 — Cableado en `api/tickets.py` (caller #5 y #6: `infer_pipeline`) + flag opt-in

**Objetivo:** migrar los callers ADO-específicos de `infer_pipeline` (`tickets.py:673`, `tickets.py:715`) al sub-puerto, con fallback al path legacy cuando flag OFF.

**Archivos exactos F5:**
- `api/tickets.py` — endpoints `/<int:ticket_id>/ado-pipeline-status` (L652-683) y `/ado-pipeline-batch` (L686-727); agregar helper `_ci_provider_for_ticket(ticket) -> CIProvider | None` y `_item_ref_for_ticket(ticket) -> ItemRef | None`.
- `config.py` — nuevo atributo `STACKY_PIPELINE_PROVIDER_ENABLED: bool = False`.
- `harness_defaults.env` — línea `STACKY_PIPELINE_PROVIDER_ENABLED=false`.

**Símbolos exactos F5 (FIX C5 — ItemRef semánticamente correcto por tracker):**

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

def _item_ref_for_ticket(ticket) -> "ItemRef | None":
    """FIX C5 — Construye ItemRef con semántica correcta por tracker_type.
    ADO: item_id = str(ticket.ado_id)  (NO ticket.id local).
    GitLab: item_id = str(ticket.tracker_project_item_id or ticket.ado_id or '');
            ref se resuelve luego (branch por convención o None).
    Si no hay identificador usable, retorna None (caller cae a legacy o 404)."""
    ttype = _tracker_type_for(ticket)
    if ttype == "azure_devops":
        if not ticket.ado_id:
            return None
        return ItemRef(item_id=str(ticket.ado_id), tracker_type="azure_devops", ref=None)
    if ttype == "gitlab":
        iid = getattr(ticket, "tracker_project_item_id", None) or ticket.ado_id
        if not iid:
            return None
        # ref: GitLab usa branch por convención (configurable futuro); None dispara fallback en adapter
        return ItemRef(item_id=str(iid), tracker_type="gitlab", ref=None)
    return None

# Endpoint GET /<int:ticket_id>/ado-pipeline-status (L652):
provider = _ci_provider_for_ticket(t)
item_ref = _item_ref_for_ticket(t)
if provider is not None and item_ref is not None:
    result = provider.infer_item_pipeline(item_ref)
    return jsonify({**result.to_dict(), "tracker_type": item_ref.tracker_type,
                    "ci_provider_coverage": _coverage_snapshot()})  # [ADICIÓN ARQUITECTO]
# fallback legacy (flag OFF o item_ref None):
result = infer_pipeline(ado_id=ado_id, force_refresh=force, model=model, ...)
return jsonify(result.to_dict())
```

El endpoint `/ado-pipeline-batch` (L686) usa el mismo patrón **por ítem** (FIX C9): si el batch contiene tickets de proyectos mixtos, cada item resuelve su propio provider; los que no tengan `tracker_type=gitlab` caen a legacy. **No se asume un único provider para todo el batch.**

**Helpers PUROS nuevos F5:**
- `_tracker_type_for(ticket) -> str` (lee `client_profile` del proyecto y devuelve `"azure_devops"` o `"gitlab"`); cacheable por `project_name`.
- `_coverage_snapshot() -> dict` (**[ADICIÓN ARQUITECTO]**): retorna un dict `{"azure_devops": N, "gitlab": M}` con la cuenta acumulada de invocaciones por adapter en la sesión (contador en módulo, **no persistente** — sólo telemetría de observabilidad; se expone también en `harness_health`).

**Tests F5 (TDD, FIX C4 patrón mock + gate significancia):**
- Archivo: `backend/tests/test_plan71_pipeline_status_endpoint.py`.
- Casos:
  1. Flag OFF + endpoint `/<id>/ado-pipeline-status` → llama `infer_pipeline(ado_id=...)` legacy **[Patrón mock: `mock_infer.assert_called`]**; NO llama al provider **[`mock_provider.infer_item_pipeline.assert_not_called()`]**.
  2. Flag ON + proyecto ADO + ticket con `ado_id=12345` → llama `AdoCIProvider.infer_item_pipeline` con `ItemRef(item_id="12345", tracker_type="azure_devops", ref=None)` **[Patrón mock: `mock_provider.infer_item_pipeline.assert_called_once_with(ItemRef(item_id="12345", tracker_type="azure_devops", ref=None))` — FIX C7: `ref=None` explícito]**; NO llama legacy.
  3. **[GATE SIGNIFICANCIA / FIX C4]** Flag ON + proyecto gitlab + ticket GitLab válido → el provider GitLab ES llamado (`assert_called_once`); si el test detecta que flag ON pero **ningún** provider fue llamado, FALLA (detecta wiring roto / falso verde).
  4. FIX C5: Flag ON + ticket GitLab **sin** `tracker_project_item_id` ni `ado_id` → `_item_ref_for_ticket` retorna None → response con `source="llm", evidence="item_ref no resoluble"` (NO se construye `ItemRef` con `t.id` local).
  5. Flag ON + provider lanza excepción → response 500 con mensaje (no silent).
  6. FIX C9: `/ado-pipeline-batch` con Flag ON y 2 tickets de proyectos distintos (uno ADO, uno GitLab) → cada item pasa por su provider correspondiente; ambos providers llamados exactamente una vez.
  7. **[ADICIÓN ARQUITECTO]** Flag ON + response incluye `ci_provider_coverage` con claves por `tracker_type`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_pipeline_status_endpoint.py -q`.

**Criterio binario F5:** los 7 casos pasan; flag OFF → byte-idéntico al comportamiento pre-plan.

**Impacto por runtime:** ninguno (capa API; no toca prompts).

**Flag F5:** `STACKY_PIPELINE_PROVIDER_ENABLED` default **OFF**, `env_only=False` (UI HarnessFlagsPanel, categoría "Pipelines / CI").

**Trabajo del operador F5:** ninguno (default OFF). Opt-in por UI cuando quiera probar GitLab.

> **Nota F5:** el helper `_ci_provider_for_ticket` se define independiente del `_provider_for_ticket` del Plan 70 F2 (CIProvider ≠ TrackerProvider). F5 NO depende de Plan 70.

---

### F6 — Cableado de `pipeline_status.get_pipeline_status` (caller #3: comentarios ADO) — GATEADO TRAS PLAN 70

**Objetivo:** migrar `tickets.py:571 get_pipeline_status(ticket_id, ado_comments=...)` para que los comentarios provengan del `TrackerProvider` (Plan 70) y no de `AdoClient` directo, cuando flag ON.

**BLOQUEO (FIX C8):** verificado 2026-06-27, `_provider_for_ticket` NO existe (Plan 70 no implementado). **F6 NO se implementa hasta que Plan 70 F2 esté en producción.** A diferencia de v1 (que caía a fallback ADO silencioso con flag ON = falso verde), v2 **pospone F6 íntegramente**: si Plan 70 no está, F6 queda como no-implementado y el caller #3 sigue usando `_ado_client_for_ticket` **incluso con flag ON**, pero esto se documenta como `pipeline_comments_legacy=true` en el response (observabilidad honesta, no falso verde).

**Archivos exactos F6:**
- `api/tickets.py` — endpoint `/<int:ticket_id>/pipeline-status` (L549-572); usar `provider.fetch_comments(item_id)` del Plan 70 cuando `_ci_provider_for_ticket` retorne no-None **Y** `_provider_for_ticket` (Plan 70 F2) esté disponible.
- `services/pipeline_status.py` — **no se modifica** (sigue recibiendo `ado_comments: list[dict] | None`); el caller construye la lista.

**Símbolos exactos F6:**

```python
# Reemplaza tickets.py:563-567:
ci_provider = _ci_provider_for_ticket(t)
tp = _provider_for_ticket(ticket=t) if _HAS_PLAN70_PROVIDER else None   # FIX C8
if ci_provider is not None and tp is not None:
    # Plan 70 disponible: usar TrackerProvider para comentarios, no AdoClient directo
    ado_comments = tp.fetch_comments(str(ado_id))
    legacy_flag = False
else:
    # Plan 70 NO disponible o flag OFF: fallback ADO (honesto, no silencioso)
    client = _ado_client_for_ticket(ticket=t)
    ado_comments = client.fetch_comments(ado_id, top=30)
    legacy_flag = True
# el response incluye pipeline_comments_legacy=legacy_flag (FIX C8: observabilidad honesta)
```

`_HAS_PLAN70_PROVIDER` se resuelve con `try: from api.tickets import _provider_for_ticket; _HAS_PLAN70_PROVIDER = True except ImportError: _HAS_PLAN70_PROVIDER = False` a nivel módulo (determinista al arranque).

**Tests F6:**
- Archivo: `backend/tests/test_plan71_pipeline_status_comments.py`.
- Casos:
  1. Flag OFF → construye `AdoClient` y llama `fetch_comments(ado_id, top=30)` **[Patrón mock]**; `pipeline_comments_legacy=True`.
  2. Flag ON + `_HAS_PLAN70_PROVIDER=False` (Plan 70 ausente) → fallback ADO con `pipeline_comments_legacy=True` (FIX C8: NO falso verde; el response admite que siguió legacy).
  3. Flag ON + `_HAS_PLAN70_PROVIDER=True` (mock) → llama `TrackerProvider.fetch_comments(str(ado_id))` (no AdoClient) **[Patrón mock: `mock_tp.fetch_comments.assert_called_once_with(str(ado_id))`]**; `pipeline_comments_legacy=False`.
  4. `get_pipeline_status` recibe la lista y produce `PipelineStatus` idéntico en ambos branches (mismo input).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_pipeline_status_comments.py -q`.

**Criterio binario F6:** los 4 casos pasan; flag OFF byte-idéntico; flag ON sin Plan 70 = fallback honesto documentado (no falso verde).

**Trabajo del operador F6:** ninguno.

---

### F7 — Observabilidad + centinela + ratchet + telemetría coverage

**Objetivo:** telemetría (`source`, `tracker_type`, `ci_provider_coverage` en response + metric en `harness_health`) y centinela anti-recableo ADO en el path CI + **gate de significancia anti-falso-verde**.

**Archivos exactos F7:**
- `api/tickets.py` — los endpoints migrados incluyen `tracker_type`, `source` y `ci_provider_coverage` en el JSON response (**[ADICIÓN ARQUITECTO]**).
- `backend/tests/test_plan71_no_adoclient_in_ci_path.py` — **nuevo centinela**.

**Centinela F7 (FIX C4 reforzado):** en los endpoints `/<id>/ado-pipeline-status` y `/ado-pipeline-batch`, con flag ON, **no debe aparecer** `infer_pipeline(` (legacy) ni `AdoClient(` en el path ejecutado. Se valida con grep contextual sobre el AST del módulo `api.tickets` **más** un test que ejecuta el endpoint con flag ON y mock del provider y afirma `mock_infer_pipeline.assert_not_called()`. **Y además (gate de significancia, FIX C4):** el mismo test afirma `mock_provider.infer_item_pipeline.assert_called_once()` — si flag ON pero el provider nunca fue llamado, el test FALLA (detecta wiring roto que en v1 pasaba como falso verde silencioso).

**Tests F7:**
- Archivo: `backend/tests/test_plan71_no_adoclient_in_ci_path.py`.
- Casos:
  1. **[GATE SIGNIFICANCIA / FIX C4]** Flag ON + proyecto GitLab → `infer_pipeline` legacy NO fue llamada (`mock_infer.assert_not_called()`) **Y** el provider GitLab SÍ fue llamado (`mock_provider.infer_item_pipeline.assert_called_once()`). Ambas afirmaciones; si una falla, el test falla.
  2. Flag OFF → `infer_pipeline` SÍ fue llamada (control de significancia: confirma que el centinela realmente distingue ON/OFF).
  3. `tracker_type` y `source` están en el JSON response con flag ON.
  4. **[ADICIÓN ARQUITECTO]** `ci_provider_coverage` está en el JSON response y refleja la invocación reciente (GitLab +1 tras la llamada del caso 1).
  5. **[ADICIÓN ARQUITECTO]** `harness_health` expone `ci_provider_coverage` acumulado por `tracker_type` (test de existencia del campo en el endpoint de salud).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan71_no_adoclient_in_ci_path.py -q`.

**Ratchet F7 (FIX C4 referencia corregida):** registrar TODOS los archivos `test_plan71_*.py` en `tests/harness_ratchet_allowlist.txt` (NO en sh/ps1 — verificado: el ratchet del Plan 49 lee ese `.txt`). Meta-test del Plan 49 F4 debe quedar verde.

**Criterio binario F7:** los 5 casos pasan; ratchet verde; flag aparece en `harness_defaults.env` y en la UI.

**Trabajo del operador F7:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Patrones ADO no trasladables a GitLab** (GAP-CI1). **Mitigación:** cada adapter CI aporta su `CommentPatternSet` o fallback `source="llm"`; F4 usa patrones Markdown GitLab o degradación determinista.
2. **Cache con clave ADO** (GAP-CI2, `PipelineInferenceCache.ado_id: int`). **Mitigación:** tabla nueva `ci_inference_cache` con clave `(tracker_type, item_id, ref)`; la vieja se conserva legacy.
3. **Falso verde "GitLab devuelve pipeline unknown"** (R3 boceto). **Mitigación:** F4 casos 2-5 afirman `overall_progress` exacto por regla `STATUS_TO_PROGRESS` (FIX C3); F7 gate de significancia afirma que el provider fue llamado.
4. **PAT GitLab sin `read_api`**. **Mitigación:** F4 captura 403 y degrada a `source="llm"` con evidence; no propaga 403.
5. **Acoplamiento a Plan 70.** FIX C8: F6 está **gateado tras Plan 70** (no fallback silencioso). F5 NO depende de 70.
6. **Tabla nueva no llega a la DB** (FIX C1 BLOQUEANTE). **Mitigación:** F2-bis wiring explícito del import + test `test_plan71_ci_cache_table_created.py` que verifica `has_table`.
7. **3 runtimes.** **Mitigación:** el plan no toca prompts/runtime del agente; sólo capa de servicios/API.
8. **Wiring roto invisible** (falso verde). **Mitigación:** F5 caso 3 + F7 caso 1 son **gates de significancia** que FALLAN si flag ON pero ningún provider fue llamado.
9. **ItemRef semánticamente roto para GitLab** (FIX C5). **Mitigación:** `_item_ref_for_ticket` usa `tracker_project_item_id`/`ado_id`, nunca `t.id` local; test F5 caso 4 cubre el vacío.
10. **Batch mixto multi-proyecto** (FIX C9). **Mitigación:** provider se resuelve por item; test F5 caso 6 cubre batch mixto.
11. **Drift del contrato compartido 71/72/73** (FIX C6). **Mitigación:** `CI_PORT_METHODS` congelado + `test_ci_port_methods_is_frozen`.

---

## 6. Fuera de scope

- **NO** disparar/monitorear pipelines (Plan 72 — `monitor_pipeline` se define pero lanza `NotImplementedError` en 71).
- **NO** generar pipelines YAML declarativos (Plan 73).
- **NO** migración ADO→GitLab (Plan 74).
- **NO** deep links visuales a pipelines (Plan 75).
- **NO** migrar la tabla `pipeline_inference_cache` vieja (legacy ADO-only).
- **NO** reconstruir el puerto `TrackerProvider` (Plan 65) ni migrar consumers (Plan 70).
- **NO** persistir `ci_provider_coverage` (telemetría efímera de sesión; si se requiere persistencia, futuro plan).

---

## 7. Glosario

- **TrackerProvider:** `Protocol` formal (`services/tracker_provider.py:56`) con 18 métodos (`PORT_METHODS`, L79-98). NO se toca en este plan.
- **CIProvider:** nuevo `Protocol` (`services/ci_provider.py`, F1 de este plan) con 2 métodos en v1 (`infer_item_pipeline`, `monitor_pipeline`). El Plan 72 agrega `trigger_pipeline`. **Contrato compartido de 71/72/73, CONGELADO en F1 (FIX C6).**
- **`CI_PORT_METHODS`:** tupla canónica `("infer_item_pipeline", "monitor_pipeline")`. Congelada; anti-drift test en F1.
- **`ItemRef`:** dataclass agnóstica `(item_id, tracker_type, ref)` — referencia al ítem + ref de CI (branch/sha GitLab; None ADO). Construir siempre con `ref=None` explícito (FIX C7).
- **`ItemPipelineResult`:** dataclass resultado con `stages`, `source`, `overall_progress`, `raw`.
- **`_COMMENT_PATTERNS`:** dict de regex ADO-específicas (`pipeline_status.py:40`); cada adapter CI aporta las suyas o un fallback.
- **`infer_pipeline`:** dos símbolos — `ado_pipeline_inference.py:319` (ADO, `ado_id: int`, devuelve `PipelineInferenceResult` clase) y `gitlab_provider.py:458` (GitLab, `ref`, devuelve `list[dict]` keys `source/status/ref/sha/web_url`). F3/F4 los envuelven.
- **`fetch_pipelines`:** `gitlab_provider.py:432`, GitLab nativo, devuelve `list[dict]`.
- **`PipelineInferenceResult`:** clase (NO dict) definida en `ado_pipeline_inference.py:109`, atributo `ado_id: int` (L121), método `to_dict()` (L132). F3 la mapea vía `_legacy_to_result`.
- **`PipelineInferenceCache`:** modelo legacy ADO-only (`ado_pipeline_inference.py:69`, clave `ado_id`). NO se migra; tabla nueva `ci_inference_cache`.
- **`get_ci_provider`:** fábrica nueva espejo de `get_tracker_provider` (`tracker_provider.py:105`).
- **`STACKY_PIPELINE_PROVIDER_ENABLED`:** flag nueva de este plan (default OFF, editable por UI).
- **`ci_provider_coverage`:** telemetría **[ADICIÓN ARQUITECTO]** — dict `{"azure_devops": N, "gitlab": M}` con cuenta de invocaciones por adapter; se expone en response de endpoints migrados y en `harness_health`.

---

## 8. Orden de implementación

1. **F0** — Inventario (cumplido en este doc, 8 filas).
2. **F1** — Sub-puerto `CIProvider(Protocol)` + tipos `ItemRef`/`ItemPipelineResult`/`PipelineStageInfo` + `CI_PORT_METHODS` congelado.
3. **F2** — Fábrica `get_ci_provider` + tabla `ci_inference_cache`.
4. **F2-bis** — **(FIX C1 BLOQUEANTE)** Wiring de la tabla nueva a `Base.metadata.create_all` + test de creación.
5. **F3** — Adapter `AdoCIProvider` (envuelve `infer_pipeline` legacy; mapea `PipelineInferenceResult` clase).
6. **F4** — Adapter `GitLabCIProvider` (envuelve `fetch_pipelines`/`infer_pipeline` existentes; regla `STATUS_TO_PROGRESS` determinista).
7. **F5** — Cableado en `api/tickets.py` (callers #5/#6) + flag `STACKY_PIPELINE_PROVIDER_ENABLED` + telemetría coverage.
8. **F6** — Cableado `get_pipeline_status` (caller #3) — **GATEADO TRAS PLAN 70**.
9. **F7** — Observabilidad + centinela + gate significancia + ratchet.

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Tabla F0 completa y verificada (8 filas, cada fila cita `archivo:línea`). **Cumplido en este doc.**
- [ ] **(b)** Sub-puerto `CIProvider` creado con `infer_item_pipeline` + `monitor_pipeline` (F1); `CI_PORT_METHODS` congelado + test anti-drift verde.
- [ ] **(b')** `monitor_pipeline` definido en el `Protocol` y lanza `NotImplementedError` en ambos adapters (lo implementa Plan 72 F1).
- [ ] **(c)** F2-bis verde: tabla `ci_inference_cache` llega a la DB vía `create_all` (FIX C1 BLOQUEANTE).
- [ ] **(d)** Callers #5/#6 (`tickets.py:673`, `tickets.py:715`) migrados con branch provider + fallback legacy (F5).
- [ ] **(e)** Caller #3 (`tickets.py:571`) usa `TrackerProvider` cuando flag ON **Y** Plan 70 disponible (F6, gateado); fallback legacy honesto con `pipeline_comments_legacy=true` si no.
- [ ] **(f)** Flag `STACKY_PIPELINE_PROVIDER_ENABLED` default **OFF**; byte-idéntico con flag OFF (F5/F6 lo verifican).
- [ ] **(g)** Un proyecto `gitlab` con flag ON devuelve `tracker_type="gitlab"` y `source` en `{"ci","llm"}` sin construir `AdoClient` ni llamar `infer_pipeline` legacy (centinela F7 + gate significancia).
- [ ] **(h)** **[ADICIÓN ARQUITECTO]** `ci_provider_coverage` expuesto en response de endpoints migrados y en `harness_health`.
- [ ] **(i)** Los 3 runtimes operativos sin cambios.
- [ ] **(j)** Ratchet verde (Plan 49 F4) con los 8 archivos `test_plan71_*.py` registrados en `tests/harness_ratchet_allowlist.txt`.

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`. Venv py3.13; correr tests por archivo.
- **Patrón mock (FIX C4/C7):** `mock_provider.return_value = Mock(name="gitlab")` (nunca None) + `mock_provider.infer_item_pipeline.assert_called_once_with(ItemRef(item_id="42", tracker_type="gitlab", ref=None))` — construir `ItemRef` con `ref=None` EXPLÍCITO. Para afirmar que el legacy NO fue llamado: `mock_infer.assert_not_called()`. **Gate de significancia:** siempre incluir también `mock_provider.infer_item_pipeline.assert_called*` en tests Flag ON (si el provider no fue llamado, el wiring está roto).
- **Mock pattern DB:** importar `db` a nivel módulo; lazy-imports se parchean en el módulo origen (memoria `plan-28-lifecycle`).
- **Tabla nueva (FIX C1):** el modelo `CIInferenceCache` DEBE importarse en el boot antes de `Base.metadata.create_all`. F2-bis lo cablea y lo testea.
- **Tipo retorno legacy (FIX C2):** `infer_pipeline` ADO devuelve `PipelineInferenceResult` (clase), no dict. `_legacy_to_result` tipa ese parámetro.
- **Keys dict GitLab (FIX C3):** `source/status/ref/sha/web_url` — NUNCA `confidence`/`overall_progress`; se derivan en `_pipelines_to_result` vía `STATUS_TO_PROGRESS`.
- **ItemRef por tracker (FIX C5):** usar `tracker_project_item_id`/`ado_id`, nunca `t.id` local.
- **Cada commit deja el sistema verde y backward-compatible.**
- **Falsos verdes prohibidos:** cada test "Flag ON → provider llamado" afirma `assert_called` (gate significancia); cada test "Flag ON → legacy no llamado" afirma `assert_not_called`.
- **Si una fase revela un GAP no listado en F0**, detener y actualizar este doc antes de seguir.
- **Plan 70 (FIX C8):** F6 está gateado. Si Plan 70 no está implementado al llegar a F6, POSPONER F6 (no caer a fallback silencioso con flag ON).
