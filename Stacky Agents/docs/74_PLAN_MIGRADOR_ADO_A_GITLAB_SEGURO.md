# Plan 74 — Migrador ADO → GitLab seguro e idempotente

> **Estado:** PROPUESTO v2 (criticado por juez adversarial 2026-06-28).
> **Pre-requisito:** Plan 70 (desacople de consumers del puerto `TrackerProvider`) — COMPLETO (commit 83d7e59d). Sin 70, el migrador escribiría acoplado a `AdoClient`; este plan asume que los consumers de `tickets.py` ya hablan por el puerto.
> **Dirección de dependencia (verificada):** 74 **NO** depende del Plan 73 (creador de pipelines). 74 solo lo **referencia para EXCLUIR** la migración de pipelines CI (ver §6). El roadmap implementa 74 ANTES de 73; cualquier lectura de "74 consume 73" es falsa. Dep dura única = Plan 70 (implementado).
> **Roadmap:** Quinto eslabón del bloque GitLab-Main 70-76 (desacople → pipeline infer agnóstico → trigger CI → creador pipelines → **migrador ADO→GitLab** → deep links → eval codebase-memory-mcp).
> **Versión doc:** v2 (2026-06-28). Reemplaza a v1 (2026-06-27) y al boceto v0.

> **CHANGELOG v1 → v2 (crítica adversarial):**
> - **C1 (BLOQUEANTE) doble-prefijo de rutas RESUELTO:** `api/__init__.py:43` define `api_bp = Blueprint("api", url_prefix="/api")` y los feature-bp se registran en `api/__init__.py` SIN `/api` propio. v1 decía "registrar `migrator_bp` en `app.py`" (que solo hace `app.register_blueprint(api_bp)`) y escribía rutas `/api/migrator/...` — exactamente el bug que ya rechazó a los planes 72/73. F9 ahora fija: `migrator_bp = Blueprint("migrator", __name__, url_prefix="/migrator")` registrado en `api/__init__.py` vía `api_bp.register_blueprint(migrator_bp)`. Nuevo centinela `test_plan74_routes_registered` (F11 bis).
> - **C2 (IMPORTANTE) op `link_parent` privada+redundante ELIMINADA:** `gitlab_provider.create_item` (`:228-229`) YA llama `_link_parent` cuando `item.parent_id` está seteado. v1 emitía una op separada que invocaba el método PRIVADO `dest._link_parent(...)` (no está en `PORT_METHODS`), violando el propio §3/§6 "consumidor del puerto". v2: los links se reconstruyen **en create_item vía `parent_id` mapeado** con **orden topológico** (Epic→Issue/Story→Task); no hay op `link_parent` ni se toca ningún método privado.
> - **C3 (IMPORTANTE) descarga binaria de attachments ESPECIFICADA:** `ado_client._request` (`:257`) devuelve `dict` (JSON) y NO sirve para binarios; no existe helper de descarga. F5 ahora define `download_attachment_to_temp` con GET autenticado binario explícito (header PAT, `stream`) y prohíbe reusar `_request`.
> - **C4 (IMPORTANTE) idempotencia robusta ante DB fresca/otra máquina/crash:** v1 consultaba solo el `migrator_map` local antes de crear → re-correr en una DB Stacky vacía o tras crash post-create/pre-upsert DUPLICABA. v2 agrega `hydrate_map_from_destination` **[ADICIÓN ARQUITECTO]** que reconstruye el mapeo desde el DESTINO (marker) antes de planear/ejecutar; el GitLab destino es la fuente de verdad, no el SQLite local.
> - **C5 (IMPORTANTE) persistencia del plan para drift ESPECIFICADA:** v1 comparaba contra "el plan_id almacenado" sin definir dónde se guarda. v2 agrega tabla `migrator_plan_snapshot` (hash + counts) para que `/execute` detecte drift (409) de verdad.
> - **C6 (MENOR) ratchet:** DoD (i) ya no hardcodea "9 archivos"; exige registrar **todos** los `test_plan74_*.py`.
> - Marcado `[a verificar tras implementar Plan 70]` donde el detalle fino depende del 70 (helper `_provider_for_ticket`, Plan 70 F2 — ya implementado).
> - Riel absoluto "read-only sobre origen ADO" operacionalizado con centinela AST (F11).

---

## 1. Objetivo y KPI

Migrar **todo** el contenido tracker de un proyecto ADO de origen a un proyecto GitLab de destino — épicas, issues, tasks, comentarios, attachments y links (parent/child) — de forma **segura** (read-only sobre el origen ADO), **idempotente** (re-corrible sin duplicar) y **trazable** (reporte de mapeo `ado_id ↔ gitlab_iid` descargable).

**KPI global (DoD):** dado un proyecto ADO de origen y un proyecto GitLab de destino, el operador ejecuta un **dry-run** desde la UI, revisa el reporte (counts por tipo, conflictos, warnings), confirma la migración HITL, y obtiene un mapeo 1:1 verificable; **re-correr el migrador no crea duplicados** (count destino estable tras 2da corrida, verificado por test F10).

---

## 2. Por qué ahora / gap que cierra

- Hoy migrar ADO→GitLab es 100% manual: cada work item se recrea a mano, los comentarios se pierden, los attachments no se migran, los links parent/child se rompen al cambiar los IDs.
- El Plan 65 construyó el puerto `TrackerProvider` con marker de idempotencia **ya implementado en ambos adapters**: `comment_exists(item_id, marker)` en `gitlab_provider.py:262`, `ado_provider.py:95`, `ado_client.py:809`. Este plan reusa ese marker como llave de idempotencia.
- El Plan 70 cierra la paridad de consumers (`tickets.py` ya habla por el puerto). El migrador **escribe por el mismo puerto** por el que ya se lee, sin acoplarse a `AdoClient` ni a `GitLabTrackerProvider` concretos.
- La degradación Free/Premium para épicas **ya existe** en `gitlab_provider._link_parent` (`gitlab_provider.py:99-115`): si `_epics_native` está OFF o el API devuelve 403, cae a issue-links. Este plan la vuelve explícita y configurable.
- Sin este plan, el roadmap GitLab queda en "convivencia" pero nunca en "migración real": el operador no puede abandonar ADO.

---

## 3. Principios y guardarraíles

- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): este plan NO toca el runtime del agente ni los prompts; el cambio vive en la capa de servicios/API. Los 3 runtimes siguen operativos sin cambios.
- **Cero trabajo extra al operador**: migración protegida por flag opt-in `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` default **OFF**, `env_only=False` (editable por UI en HarnessFlagsPanel). Con flag OFF el migrador es inerte (los endpoints devuelven 404 / 503).
- **Human-in-the-loop innegociable**: dry-run **obligatorio** antes de cualquier escritura en GitLab; el operador revisa el reporte y confirma explícitamente; nada autónomo.
- **Mono-operador sin auth**: las credenciales ADO PAT y GitLab token siguen viniendo del `client_profile` del proyecto; sin RBAC, sin login.
- **No degradar / backward-compatible**: no se modifica `TrackerProvider`, ni `gitlab_provider`, ni `ado_provider`; el migrador es un consumidor nuevo del puerto. Backward-compat total.
- **TDD + funciones puras + ratchet + no falsos verdes**: cada fase migra test-first; el ratchet meta del Plan 49 se mantiene verde registrando los tests nuevos.
- **Read-only sobre el origen ADO es riel ABSOLUTO**: el migrador jamás invoca `create_*`/`update_*`/`post_comment`/`upload_attachment`/`link_attachment` sobre el provider ADO. Centinela AST en F11 lo garantiza.
- **Idempotencia por marker**: cada item migrado recibe un comentario-marker `<!-- stacky-migrated:ado:{ado_id} -->`; antes de crear, `comment_exists(marker)` decide skip-vs-create.
- **Prohibido lo vago**: todo call site, archivo y símbolo citado con `archivo:línea`.

---

## 4. Fases

### F0 — Inventario (entregable: tabla tipo × método puerto lectura-ADO × método puerto escritura-GitLab × marker)

**Trabajo:** fijar el mapeo de tipos ADO → equivalente GitLab y los métodos del puerto usados para leer del origen y escribir en el destino. Los métodos son los de `TrackerProvider.PORT_METHODS` (`tracker_provider.py:79-98`); no se inventan métodos nuevos.

**Tabla F0 — Tipos a migrar (6 filas):**

| # | Tipo ADO | Equivalente GitLab | Método puerto lectura (origen ADO) | Método puerto escritura (destino GitLab) | Marker idempotencia | Notas |
|---|----------|--------------------|-------------------------------------|------------------------------------------|---------------------|-------|
| 1 | `Epic` | Premium: `epic` (group epic) / Free: `issue` + label `type::epic` | `fetch_open_items(TrackerQuery)` o WIQL ADO | `create_item(TrackerItem(item_type="epic"))` | `<!-- stacky-migrated:ado:{id} -->` en descripción | Política `STACKY_MIGRATOR_EPIC_POLICY` (ver F3) |
| 2 | `Issue` / `User Story` | `issue` + label `type::issue`/`type::story` | `fetch_open_items` / `get_item` | `create_item(TrackerItem(item_type="issue"))` | marker en descripción | `_type_label` ya mapea (`gitlab_provider.py:40`) |
| 3 | `Task` | `issue` + label `type::task` (Free) / sub-issue (Premium) | `get_item` + `find_child_by_marker` | `create_item(TrackerItem(item_type="task", parent_id=...))` | marker en descripción | Parent se re-apunta vía mapeo F1 |
| 4 | `Comment` (de cualquier work item) | `note` en el issue GitLab correspondiente | `fetch_all_comments(item_id)` | `post_comment(item_id, body_html)` | `comment_exists(item_id, marker)` antes de postear | Marker embebido en el body del note |
| 5 | `Attachment` | Upload binario al issue GitLab | `fetch_attachments(item_id)` + descarga ADO (vía URL del attachment) | `upload_attachment(file_path, file_name)` + `link_attachment(item_id, attach_result)` | re-fetch descripción: si el markdown ya está, skip | Hash post-subida verifica integridad |
| 6 | `Link` parent/child | Premium: epic-issue link / Free: issue-issue link | `get_item` (campo `parent`) | **`create_item(TrackerItem(parent_id=iid_mapeado))`** (el linkeo lo hace `create_item` internamente, ver `gitlab_provider.py:228-229`) | idempotente por orden topológico + map | Warnings para IDs no migrados; **NO** se llama `_link_parent` directamente |

> **DECISIÓN C2 (link en create-time, sin método privado):** `gitlab_provider.create_item` (`:207`) ya invoca `self._link_parent(...)` cuando `item.parent_id` está seteado (`:228-229`). Por lo tanto el migrador **NO emite una op `link_parent` separada** ni toca el método privado `_link_parent` (no está en `PORT_METHODS`; viola §3/§6). En su lugar, los links se reconstruyen **al crear**: se pasa `parent_id = existing_map[ado_parent_id]` (el `iid` GitLab ya mapeado) dentro del `TrackerItem` del `create_item`. Esto exige **orden topológico** (ver F2): se migran primero `Epic`, luego `Issue`/`User Story`, luego `Task`; al ejecutar, tras cada create se hace `upsert_mapping` para que los hijos siguientes resuelvan su padre. Un item cuyo padre **no** está en `existing_map` al momento de crearlo se crea **sin** `parent_id` (huérfano) y se acumula un warning; nunca se aborta.

**GAPs detectados (alimentan F1):**

- **GAP-A (links rotos por cambio de ID):** los links ADO referencian `ado_id`; en GitLab los items tienen `iid` distinto. **Decisión:** tabla de mapeo persistente `ado_id ↔ gitlab_iid` (F1); el link se establece **en `create_item` vía `parent_id` mapeado** (no en una op separada, ver DECISIÓN C2 arriba); los links a IDs no migrados se reportan como warnings (no se aborta). El **orden topológico** (Epic→Story/Issue→Task) garantiza que el padre exista en el mapeo antes de crear al hijo.
- **GAP-B (attachments binarios):** `fetch_attachments` ADO devuelve metadatos + URL de descarga (requiere auth ADO); GitLab `upload_attachment` recibe un `file_path` local. **Decisión:** F5 descarga el binario ADO a un temp file local, lo sube a GitLab, verifica hash, y limpia el temp file. El adapter ADO ya devuelve la URL; la descarga usa el mismo PAT del `client_profile`.
- **GAP-C (épicas en Free):** GitLab Free no tiene group epics. **Decisión:** política configurable `STACKY_MIGRATOR_EPIC_POLICY ∈ {premium_native, free_degrade, auto}` (default `auto`): `premium_native` fuerza epic nativo (falla si no hay licencia), `free_degrade` crea issue + label `type::epic` + comment-marker, `auto` prueba `_link_parent` y si recibe 403 cae a `free_degrade`. La detección de tier ya vive en `gitlab_provider._epics_native` (`gitlab_provider.py:36`) y `_link_parent` (`:99-115`); este plan la reusa sin tocar el provider.
- **GAP-D (metadatos originales: autor/fecha):** GitLab API no permite setear `author_id`/`created_at` en issues en SaaS (sí en self-managed admin). **Decisión:** el migrador preserva autor/fecha originales como **comment-marker** inicial (`<!-- stacky-meta:author={x};created={y} -->`) + un note visible "Migrado de ADO por {author} el {date}". No se intenta forzar `created_at` (frágil entre tiers). Documentado en F4.

**Criterio binario F0:** la tabla de arriba está completa (6 filas) y cada fila cita el método puerto exacto. **Cumplido en este doc.**

**Trabajo del operador F0:** ninguno.

---

### F1 — Tabla de mapeo `ado_id ↔ gitlab_iid` persistente

**Objetivo:** proveer una consulta barata `(ado_id) → gitlab_iid` para (a) re-corridas sin duplicar y (b) reconstruir links parent/child re-apuntando IDs.

**Trabajo:** función PURA de persistencia del mapeo. Store: tabla SQLite nueva en la DB de Stacky (`migrator_ado_gitlab_map`), versionada, consultable por `(stacky_project, ado_id)`.

**Esquema tabla:**
```sql
CREATE TABLE IF NOT EXISTS migrator_ado_gitlab_map (
    stacky_project TEXT NOT NULL,
    ado_id          TEXT NOT NULL,
    ado_type        TEXT NOT NULL,           -- Epic|Issue|Task|...
    gitlab_iid      TEXT NOT NULL,
    gitlab_web_url  TEXT NOT NULL,
    marker          TEXT NOT NULL,           -- <!-- stacky-migrated:ado:{ado_id} -->
    migrated_at     TEXT NOT NULL,           -- ISO8601 UTC
    migration_run   TEXT NOT NULL,           -- id de la corrida (dry-run o real)
    PRIMARY KEY (stacky_project, ado_id)
);
```

**Archivos exactos F1:**
- `backend/services/migrator_map.py` (NUEVO) — funciones PURAS de CRUD sobre la tabla:
  - `ensure_map_schema(db) -> None`
  - `upsert_mapping(db, *, stacky_project, ado_id, ado_type, gitlab_iid, gitlab_web_url, marker, migration_run) -> None`
  - `get_gitlab_iid(db, stacky_project, ado_id) -> str | None`
  - `get_full_mapping(db, stacky_project) -> list[dict]`
  - `bulk_upsert(db, stacky_project, rows) -> None`
- `backend/models.py` — sin cambios (la tabla vive en la misma DB SQLite del modelo).

**Tests F1 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_map.py`.
- Casos:
  1. `ensure_map_schema` es idempotente (llamar 2x no falla).
  2. `upsert_mapping` + `get_gitlab_iid` devuelve el `gitlab_iid` correcto.
  3. `upsert_mapping` sobre `(project, ado_id)` existente actualiza `gitlab_iid` (no duplica).
  4. `get_gitlab_iid` para ado_id inexistente → `None`.
  5. `bulk_upsert` inserta N filas en una transacción y son legibles por `get_full_mapping`.
  6. `get_full_mapping` ordena por `ado_id` ascendente (determinista).
  7. Aislamiento por `stacky_project`: mapping de proyecto A no filtra a proyecto B.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_map.py -q`.

**Criterio binario F1:** los 7 casos pasan; `migrator_map.py` no importa ni `AdoClient` ni `GitLabTrackerProvider` (puro SQLite).

**Impacto por runtime:** ninguno (capa de datos).

**Flag F1:** ninguna (el módulo es inerte hasta F2).

**Trabajo del operador F1:** ninguno.

---

### F2 — Orquestador del migrador (esqueleto read-only + dry-run gate)

**Objetivo:** función PURA `plan_migration(origin_provider, dest_provider, *, stacky_project, items_filter)` que lee del origen por el puerto y produce un **plan de migración** (lista de operaciones) **sin escribir nada**. Es el corazón del dry-run.

**Trabajo:**

```python
# backend/services/migrator_core.py (NUEVO)
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass(frozen=True)
class MigrationOp:
    # NOTA C2: NO existe op_kind "link_parent". El link se establece dentro
    # de "create_item" pasando dest_parent_ado_id resuelto a iid en F4.
    op_kind: Literal["create_item", "post_comment", "upload_attachment"]
    ado_id: str
    ado_type: str
    dest_parent_ado_id: Optional[str]   # ado_id del padre; F4 lo resuelve a iid vía map
    payload: dict                        # TrackerItem dict / comment body / attach meta
    marker: str

@dataclass(frozen=True)
class MigrationPlan:
    ops: list[MigrationOp]               # ORDENADAS topológicamente: Epic→Story/Issue→Task
    counts_by_type: dict[str, int]
    warnings: list[str]                  # ej: "padre ado_id 999 no migrado; item creado huérfano"

# Orden topológico fijo (C2): los padres se crean antes que los hijos.
_TYPE_ORDER: dict[str, int] = {"Epic": 0, "Issue": 1, "User Story": 1, "Task": 2}

def plan_migration(
    origin: "TrackerProvider",
    dest: "TrackerProvider",
    *,
    stacky_project: str,
    existing_map: dict[str, str],        # ado_id -> gitlab_iid (ya migrados; ver hydrate F4b)
) -> MigrationPlan:
    """Lee del origen por el puerto (fetch_open_items, fetch_all_comments,
    fetch_attachments) y produce el plan SIN escribir en dest.
    Para cada item del origen:
      - si ado_id in existing_map -> skip (ya migrado)
      - sino -> genera op create_item (con dest_parent_ado_id si tiene parent)
               + op post_comment por cada comentario
               + op upload_attachment por cada attachment.
    Las ops se ORDENAN por _TYPE_ORDER (Epic→Story/Issue→Task) para que F4 pueda
    resolver el parent_id del hijo contra el map ya poblado por el padre.
    Un padre ausente del origen Y del plan -> warning (item se creará huérfano en F4).
    NO emite ops de linkeo: el link viaja en el create_item (ver DECISIÓN C2)."""
```

**Invariante READ-ONLY (verificada por F11):** `plan_migration` solo invoca métodos `fetch_*`/`get_*` sobre `origin`. Nunca invoca `create_*`/`update_*`/`post_*`/`upload_*`/`link_*` sobre ningún provider.

**Archivos exactos F2:**
- `backend/services/migrator_core.py` (NUEVO) — `MigrationOp`, `MigrationPlan`, `plan_migration`, `_TYPE_ORDER`, helpers puros `_build_create_op` (incluye `dest_parent_ado_id`), `_build_comment_ops`, `_build_attachment_ops`, `_sort_ops_topologically`. **NO** existe `_build_link_ops` (eliminado por C2).
- No toca `TrackerProvider`, `ado_provider`, `gitlab_provider`.

**Tests F2 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_core.py`.
- Casos:
  1. `plan_migration` con origen mock (2 items, 3 comments, 1 attachment) → `MigrationPlan` con counts correctos.
  2. Item cuyo `ado_id` ya está en `existing_map` → no genera op (skip).
  3. Item con parent → la op `create_item` lleva `dest_parent_ado_id` = ado_id del padre (NO hay op `op_kind=="link_parent"` en el plan).
  4. Item con parent cuyo `ado_id` no está en `existing_map` ni en el plan → warning ("padre ... no migrado; huérfano"); la op `create_item` se genera igual con `dest_parent_ado_id=None`.
  5. **Orden topológico:** un origen con 1 Task (parent=Epic) + 1 Epic produce `ops` donde la op del Epic precede a la del Task (`_TYPE_ORDER`).
  6. **Patrón mock read-only:** `mock_origin.fetch_open_items.assert_called_once()` y `mock_dest` nunca fue llamado por `plan_migration`.
  7. `counts_by_type` determinista (ordenado por tipo alfabético).
  8. `plan_migration` es pura: 2 llamadas con mismo input → mismo plan (incluyendo el orden de `ops`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_core.py -q`.

**Criterio binario F2:** los 8 casos pasan; `plan_migration` es pura; el orden topológico se respeta (caso 5); el mock del destino nunca es invocado.

**Impacto por runtime:** ninguno.

**Flag F2:** ninguna (inerte hasta F4).

**Trabajo del operador F2:** ninguno.

---

### F3 — Política de épicas (Free vs Premium) configurable

**Objetivo:** resolver el supuesto crítico del boceto (tier GitLab). Operacionalizar la degradación `free_degrade` / `premium_native` / `auto`.

**Trabajo:** función PURA `resolve_epic_strategy(dest_provider, policy) -> EpicStrategy` que decide cómo migrar épicas. Reusa la detección existente en `gitlab_provider._epics_native` (no la duplica).

```python
# backend/services/migrator_epics.py (NUEVO)
from dataclasses import dataclass
from typing import Literal

EpicStrategy = Literal["premium_native", "free_degrade"]

@dataclass(frozen=True)
class EpicDecision:
    strategy: EpicStrategy
    item_type_for_create: str             # "epic" (premium) o "issue" (free)
    extra_labels: tuple[str, ...]         # ("type::epic",) en free
    reason: str

def resolve_epic_strategy(dest_provider, policy: str) -> EpicDecision:
    """policy ∈ {'auto','premium_native','free_degrade'}.
    - auto: lee dest_provider._epics_native (si existe) → premium_native o free_degrade.
    - premium_native: fuerza 'epic' (si luego falla 403, lo atrapa _link_parent).
    - free_degrade: siempre 'issue' + label type::epic.
    Nunca escribe; solo lee el flag del provider."""
```

**Archivos exactos F3:**
- `backend/services/migrator_epics.py` (NUEVO) — `EpicDecision`, `resolve_epic_strategy`.
- No toca `gitlab_provider`.

**Tests F3 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_epics.py`.
- Casos:
  1. `policy="auto"` + provider con `_epics_native=True` → `premium_native`.
  2. `policy="auto"` + provider con `_epics_native=False` → `free_degrade`.
  3. `policy="free_degrade"` → siempre `free_degrade` sin importar el provider.
  4. `policy="premium_native"` → siempre `premium_native`.
  5. Provider sin atributo `_epics_native` (mock genérico) + `auto` → `free_degrade` (default seguro).
  6. `resolve_epic_strategy` no invoca ningún método del provider (solo lee atributo).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_epics.py -q`.

**Criterio binario F3:** los 6 casos pasan; la función es pura.

**Impacto por runtime:** ninguno.

**Flag F3:** `STACKY_MIGRATOR_EPIC_POLICY` default `"auto"`, `env_only=False` (editable por UI, dropdown de 3 valores).

**Trabajo del operador F3:** ninguno (default `auto`); el operador sólo cambia el policy si sabe que su GitLab es Free.

---

### F4 — Ejecutor de migración (aplica el plan con idempotencia + marker)

**Objetivo:** `execute_migration(plan, dest_provider, db, *, stacky_project, migration_run)` aplica cada op del plan contra el destino, **consultando marker antes de crear** y **persistiendo el mapeo** tras cada creación exitosa.

**Trabajo:**

```python
# backend/services/migrator_executor.py (NUEVO)
@dataclass(frozen=True)
class MigrationResult:
    applied: int
    skipped: int
    failed: list[dict]          # {ado_id, op_kind, error}
    mapping_rows: list[dict]    # filas para bulk_upsert
    markers_used: list[str]
    orphaned: list[str]         # ado_ids creados sin parent (padre no mapeado)

def execute_migration(plan, dest_provider, db, *, stacky_project, migration_run, existing_map) -> MigrationResult:
    """existing_map se construye con hydrate_map_from_destination ANTES de llamar (ver F4b).
    Para cada op del plan (en el ORDEN topológico que ya trae el plan):
      - op_kind=create_item: si get_gitlab_iid(ado_id) existe (map ya hidratado) → skip;
        sino: resolver parent_id = existing_map.get(op.dest_parent_ado_id) (None si no mapeado;
        si None y había padre → registrar en orphaned[] + warning);
        dest_provider.create_item(TrackerItem(..., parent_id=parent_id_resuelto)) con marker en
        description_html (create_item enlaza al padre internamente, gitlab_provider.py:228-229);
        upsert_mapping(ado_id→iid) y actualizar existing_map en memoria para los hijos siguientes.
      - op_kind=post_comment: resolver dest_iid = existing_map[ado_id]; si
        dest_provider.comment_exists(dest_iid, marker) → skip; sino post_comment(dest_iid, body+marker).
      - op_kind=upload_attachment: si el markdown del attachment ya está en la descripción (re-fetch) → skip;
        sino migrate_attachment (F5): download ADO → upload GitLab → link_attachment.
    NO hay rama op_kind=link_parent (eliminada por C2). Cualquier error se acumula en failed[]
    (no aborta); al final, si failed>0, el resultado lleva el detalle.
    """

def hydrate_map_from_destination(dest_provider, db, *, stacky_project) -> dict[str, str]:
    """[ADICIÓN ARQUITECTO — cierra C4] Reconstruye el mapeo ado_id→iid desde el DESTINO
    (fuente de verdad), no desde el SQLite local. Lista los items del destino que portan el
    marker `<!-- stacky-migrated:ado:{id} -->` (vía dest_provider.fetch_open_items + parseo del
    marker en la descripción), parsea el ado_id, y hace upsert_mapping en migrator_map. Devuelve
    el map fusionado (local ∪ destino). Es READ-ONLY sobre el destino salvo el upsert local.
    Garantiza idempotencia aunque el SQLite de Stacky esté vacío (DB fresca / otra máquina /
    crash post-create-pre-upsert). Pura respecto al destino: sólo invoca fetch_*/get_*."""
```

**Invariante IDEMPOTENCIA:** ejecutar `execute_migration` 2x sobre el mismo plan deja el destino sin duplicados (verificado por F10). La garantía NO depende solo del `migrator_map` local: `hydrate_map_from_destination` (F4b) reconstruye el map desde el destino antes de cada corrida, cerrando la ventana "create OK / upsert falló" y el caso "DB Stacky vacía en otra máquina".

**Archivos exactos F4:**
- `backend/services/migrator_executor.py` (NUEVO) — `MigrationResult`, `execute_migration`, `hydrate_map_from_destination` (F4b), helpers `_apply_create` (resuelve `parent_id` desde el map), `_apply_comment`, `_apply_attachment`. **NO** existe `_apply_link` (eliminado por C2; el link va en `create_item`).
- Reusa `migrator_map.upsert_mapping` y `get_gitlab_iid` (F1) y `migrate_attachment` (F5).

**Tests F4 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_executor.py`.
- Casos (siempre con `mock_dest` y `mock_origin`):
  1. Plan con 2 creates → `execute_migration` llama `create_item` 2x **[Patrón mock: `mock_dest.create_item.assert_called` con TrackerItem]**; `applied == 2`; mapping persiste 2 filas.
  2. Re-correr el mismo plan (2da vez) con el mapping ya poblado → `skipped == 2`, `create_item` **NO** llamado de nuevo.
  3. Comment op cuyo marker ya existe → `post_comment` NO llamado **[Patrón mock: `comment_exists` retorna True, `assert_not_called`]**.
  4. Attachment op → secuencia download→upload→link_attachment; hash verificado; temp file limpiado.
  5. **Create con parent mapeado:** `create_item` se llama con `TrackerItem.parent_id == iid_mapeado` (el linkeo lo hace `create_item` internamente; el test NO espera ninguna llamada a `_link_parent`) **[Patrón mock: inspeccionar el `TrackerItem` pasado a `create_item`]**.
  6. **Create con parent NO mapeado:** el item se crea con `parent_id=None`, se agrega a `orphaned[]` y se acumula warning; no aborta.
  7. Una op falla (create_item levanta `TrackerApiError`) → acumula en `failed`, no aborta, las demás se aplican.
  8. **Invariant read-only origen:** `mock_origin` nunca fue invocado por `execute_migration` **[Patrón mock: `assert_not_called` en todos los métodos mutadores]**.
  9. **hydrate_map_from_destination:** con `mock_dest.fetch_open_items` devolviendo 2 items con marker → el map resultante tiene 2 entradas; `mock_dest` solo recibió `fetch_*` (read-only) **[gate C4]**.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_executor.py -q`.

**Criterio binario F4:** los 9 casos pasan; idempotencia verificada (caso 2); link en create-time sin método privado (caso 5); reconciliación desde destino (caso 9); origen nunca mutado (caso 8).

**Impacto por runtime:** ninguno.

**Flag F4:** ninguna (el ejecutor es invocado por F6 con flag ON).

**Trabajo del operador F4:** ninguno.

---

### F5 — Migración de attachments (descarga binaria + verificación hash)

**Objetivo:** bajar attachments del origen ADO y subirlos al destino GitLab sin pérdida, verificando integridad por hash.

**Trabajo:** función PURA de hash + helper de descarga/subida.

```python
# backend/services/migrator_attachments.py (NUEVO)
import os, base64, tempfile, requests   # requests YA es dependencia (ado_client/gitlab_client lo usan)

def compute_sha256(file_path: str) -> str: ...   # pura

def download_attachment_to_temp(attachment_meta: dict, *, ado_pat: str) -> str:
    """Descarga el binario ADO a un temp file. Retorna la ruta temporal. NO sube nada.

    C3 — IMPLEMENTACIÓN EXPLÍCITA. PROHIBIDO reusar `ado_client._request` (devuelve `dict`/JSON,
    NO sirve para binarios — ado_client.py:257). `attachment_meta` trae la URL de descarga (campo
    `url`/`downloadUrl`, lo que devuelva `fetch_attachments`, ado_client.py:431). Hacer GET binario:
        auth = base64.b64encode(f':{ado_pat}'.encode()).decode()   # PAT ADO va como user vacío
        with requests.get(attachment_meta['url'],
                          headers={'Authorization': f'Basic {auth}'},
                          stream=True, timeout=60) as r:
            r.raise_for_status()
            fd, path = tempfile.mkstemp(suffix='_' + attachment_meta.get('name', 'attach'))
            with os.fdopen(fd, 'wb') as fh:
                for chunk in r.iter_content(8192):
                    fh.write(chunk)
            return path
    El PAT viene del client_profile del proyecto ORIGEN. GET puro = read-only sobre el origen ADO."""

def migrate_attachment(attachment_meta, dest_provider, *, dest_iid, ado_pat) -> dict:
    """download → compute_sha256(local) → dest_provider.upload_attachment(temp, name)
       → compute_sha256(re-fetch del upload si dest lo expone) → link_attachment(dest_iid, result)
       → cleanup temp. Si los hashes difieren (cuando verificable), registra warning.
    Retorna {name, local_sha256, dest_markdown, verified: bool}."""
```

**Archivos exactos F5:**
- `backend/services/migrator_attachments.py` (NUEVO).
- Reusa `dest_provider.upload_attachment` (`gitlab_provider.py:268`) y `dest_provider.link_attachment` (`:280`).

**Tests F5 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_attachments.py`.
- Casos:
  1. `compute_sha256` sobre un archivo conocido → hash exacto determinista (vector de test fijo en `tests/fixtures/migrator/sample.txt`).
  2. `migrate_attachment` con `mock_dest` → llama `upload_attachment` y `link_attachment` en orden **[Patrón mock: `assert_has_calls`]**.
  3. `upload_attachment` levanta excepción → `migrate_attachment` retorna `verified=False` y no rompe.
  4. Cleanup: tras `migrate_attachment` (éxito o fallo), el temp file fue eliminado (verifica con `os.path.exists`).
  5. Idempotencia: si el markdown del attachment ya está en la descripción del issue (re-fetch), no se re-sube.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_attachments.py -q`.

**Criterio binario F5:** los 5 casos pasan; cleanup garantizado.

**Impacto por runtime:** ninguno.

**Trabajo del operador F5:** ninguno.

---

### F6 — API endpoint + wizard HITL (dry-run → reporte → confirmación → ejecución)

**Objetivo:** exponer el migrador como endpoints REST consumidos por un wizard de UI, con dry-run **obligatorio** antes de escritura.

**Trabajo:**

**Persistencia del plan (C5 — drift real).** El `plan_id` de v1 quedaba colgando ("compara con el plan_id almacenado" sin definir dónde). v2 fija una tabla:
```sql
CREATE TABLE IF NOT EXISTS migrator_plan_snapshot (
    plan_id        TEXT PRIMARY KEY,        -- uuid4 generado en POST /plan
    stacky_project TEXT NOT NULL,
    counts_json    TEXT NOT NULL,           -- json.dumps(counts_by_type) — base del drift
    plan_hash      TEXT NOT NULL,           -- sha256 de (sorted ado_ids + counts) del dry-run
    created_at     TEXT NOT NULL            -- ISO8601 UTC; TTL lógico de 30 min (no borra, compara)
);
```
`POST /plan` inserta la fila; `POST /execute` re-corre `plan_migration`, recomputa `plan_hash` y lo compara con `migrator_plan_snapshot[plan_id].plan_hash`: si difiere → 409. Vive en `migrator_map.py` (mismas funciones puras de F1): `save_plan_snapshot`, `get_plan_snapshot`.

```python
# backend/api/migrator.py (NUEVO blueprint)
migrator_bp = Blueprint("migrator", __name__, url_prefix="/migrator")  # C1: SIN "/api" (api_bp ya lo agrega)

POST /api/migrator/plan          # ruta efectiva = url_prefix de api_bp ("/api") + "/migrator" + "/plan"
  body: {stacky_project, items_filter?, epic_policy?}
  -> corre plan_migration (F2) SIN escribir; persiste migrator_plan_snapshot;
     retorna {plan_id, counts_by_type, warnings, ops_preview (truncado a 50), total_ops}
  Requiere STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=true (sino 503).

POST /api/migrator/execute
  body: {plan_id, confirmed: true}
  -> Si confirmed != true -> 400 (HITL gate).
  -> hydrate_map_from_destination (F4b); re-corre plan_migration y recomputa plan_hash;
     si plan_hash != migrator_plan_snapshot[plan_id].plan_hash -> 409 "el origen cambió, re-corré el plan".
  -> execute_migration (F4) con existing_map hidratado; retorna {applied, skipped, failed, orphaned, migration_run}.

GET  /api/migrator/health        # ruta efectiva /api/migrator/health (centinela F11 bis)
  -> 200 {ok:true} con flag ON; 503 con flag OFF.

GET  /api/migrator/{stacky_project}/mapping
  -> get_full_mapping (F1) en formato JSON + CSV descargable (header Accept: text/csv).

GET  /api/migrator/{stacky_project}/runs
  -> historial de corridas (migration_run, timestamp, applied/skipped/failed counts).
```

**Archivos exactos F6:**
- `backend/api/migrator.py` (NUEVO) — define `migrator_bp = Blueprint("migrator", __name__, url_prefix="/migrator")`. **NO** se registra en `app.py`; el registro va en `api/__init__.py` (F9, C1).
- `backend/config.py` — `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED: bool = False`, `env_only=False`.
- `backend/services/migrator_map.py` — `save_plan_snapshot`, `get_plan_snapshot` (tabla `migrator_plan_snapshot`).

**Tests F6 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_api.py`.
- Casos:
  1. `POST /plan` con flag OFF → 503.
  2. `POST /plan` con flag ON + origen mock → 200 con `counts_by_type` y `plan_id`; `migrator_plan_snapshot` tiene la fila.
  3. `POST /execute` sin `confirmed=true` → 400 (HITL gate).
  4. `POST /execute` con `confirmed=true` pero el origen cambió desde el plan (mock origen devuelve 1 item extra → `plan_hash` distinto) → 409.
  5. `POST /execute` con `confirmed=true` y plan válido (hash coincide) → 200 con `applied/skipped/failed/orphaned`.
  6. `GET /mapping` devuelve JSON con las filas del mapeo.
  7. `GET /mapping` con `Accept: text/csv` devuelve CSV descargable (mismo contenido, formato distinto).
  8. `GET /runs` lista las corridas ordenadas por timestamp desc.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_api.py -q`.

**Criterio binario F6:** los 8 casos pasan; dry-run obligatorio (caso 3); drift por `plan_hash` (caso 4); `migrator_bp` con `url_prefix="/migrator"` (sin doble `/api`).

**Impacto por runtime:** ninguno (endpoint nuevo).

**Flag F6:** `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` default **OFF**, `env_only=False` (UI).

**Trabajo del operador F6:** ninguno (default OFF).

---

### F7 — UI wizard de migración (origen → dry-run → reporte → confirmación → progreso → mapeo descargable)

**Objetivo:** un wizard paso-a-paso en la UI que orquesta el HITL. Reusa componentes existentes (DeepLink, OutputPanel, modal de confirmación).

**Pasos del wizard:**
1. **Selección:** origen (proyecto ADO) y destino (proyecto GitLab). Carga el `client_profile` del origen y verifica `credentials_present()` en ambos.
2. **Dry-run:** botón "Generar plan" → llama `POST /api/migrator/plan` → muestra tabla de counts por tipo + lista de warnings + preview de 50 ops.
3. **Confirmación HITL:** checkbox "Revisé el plan y quiero migrar" + botón "Ejecutar migración" (disabled hasta check). Llama `POST /api/migrator/execute` con `confirmed=true`.
4. **Progreso:** polling del `migration_run` (o SSE si existe) mostrando `applied/skipped/failed` en vivo.
5. **Resultado + mapeo descargable:** tabla final `ado_id ↔ gitlab_iid` con botón "Descargar CSV" ( llama `GET /mapping?Accept=text/csv`) y link clickable a cada item GitLab.

**Archivos exactos F7:**
- `frontend/src/pages/MigratorPage.tsx` (NUEVO).
- `frontend/src/components/MigratorWizard.tsx` (NUEVO) — orquesta los 5 pasos.
- `frontend/src/components/MigratorPlanPreview.tsx` (NUEVO) — tabla de counts + warnings.
- `frontend/src/components/MigratorMappingTable.tsx` (NUEVO) — tabla final con CSV download.

**Tests F7 (TDD primero, componentes):**
- Archivo: `frontend/src/components/__tests__/MigratorWizard.test.tsx` (NUEVO) — usa vitest si está disponible; sino test unitario sobre la lógica de pasos en `frontend/src/components/MigratorWizard.logic.ts`.
- Casos:
  1. Paso 2 "Generar plan" deshabilita el botón hasta que se elija origen+destino.
  2. Paso 3 "Ejecutar" deshabilitado hasta que el checkbox de revisión esté marcado.
  3. Tras plan con warnings, se muestran los warnings antes de permitir confirmar.
  4. Tras ejecución exitosa, la tabla de mapeo se llena y el botón "Descargar CSV" llama al endpoint correcto.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/components/__tests__/MigratorWizard.test.tsx` (si vitest instalado; ver memoria `stacky-backend-dev-test-env`).

**Criterio binario F7:** los 4 casos pasan (o test de lógica de pasos verde si vitest no está); `tsc` con 0 errores (`cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit`).

**Impacto por runtime:** ninguno (UI nueva).

**Trabajo del operador F7:** ninguno (default OFF).

---

### F8 — Verificación post-migración (count diffs por tipo, abortar si gap>0)

**Objetivo:** tras la ejecución, re-leer el destino y comparar counts por tipo contra el plan. Si hay gap>0, marcar la corrida como `needs_review`.

**Trabajo:** función PURA `verify_migration(plan, dest_provider, *, stacky_project, db) -> VerificationResult`.

```python
# backend/services/migrator_verify.py (NUEVO)
@dataclass(frozen=True)
class VerificationResult:
    expected_by_type: dict[str, int]
    actual_by_type: dict[str, int]
    gap_by_type: dict[str, int]
    passed: bool          # True sii todo gap == 0
    needs_review: list[str]   # tipos con gap

def verify_migration(plan, dest_provider, *, stacky_project, db) -> VerificationResult:
    """expected = plan.counts_by_type.
    actual = cuenta items en destino con marker stacky-migrated:ado:* (vía fetch_open_items
             filtrando por label type::, + comment_exists marker por item).
    gap = expected - actual.
    passed = todo gap == 0."""
```

**Archivos exactos F8:**
- `backend/services/migrator_verify.py` (NUEVO).

**Tests F8 (TDD primero):**
- Archivo: `backend/tests/test_plan74_migrator_verify.py`.
- Casos:
  1. `expected = {Epic:2, Issue:3}`, `actual = {Epic:2, Issue:3}` → `passed=True`.
  2. `actual = {Epic:1, Issue:3}` (falta 1 epic) → `passed=False`, `needs_review=["Epic"]`.
  3. `actual` con tipo extra no esperado → no rompe, `gap_by_type` lo marca negativo.
  4. `verify_migration` no escribe en destino **[Patrón mock: sólo fetch_* llamados]**.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_verify.py -q`.

**Criterio binario F8:** los 4 casos pasan; función pura.

**Impacto por runtime:** ninguno.

**Trabajo del operador F8:** ninguno.

---

### F9 — Integración en `app.py` + flag en `harness_defaults.env` + UI flag

**Trabajo:**
- **C1 — Registrar `migrator_bp` en `backend/api/__init__.py`** (NO en `app.py`). El patrón de la casa: `api_bp = Blueprint("api", __name__, url_prefix="/api")` (`api/__init__.py:43`) y cada feature-bp se registra con `api_bp.register_blueprint(<bp>)` SIN repetir `/api`. Agregar al bloque (junto a `pipelines_bp`, `tickets_bp`, etc.): `from .migrator import migrator_bp` y `api_bp.register_blueprint(migrator_bp)`. `migrator_bp` debe tener `url_prefix="/migrator"`. Resultado: rutas efectivas `/api/migrator/...` (UN solo `/api`). `app.py` NO se toca (ya hace `app.register_blueprint(api_bp)`).
- Agregar `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=false` y `STACKY_MIGRATOR_EPIC_POLICY=auto` a `backend/harness_defaults.env`.
- Exponer las 2 flags en HarnessFlagsPanel (categoría "Migrador ADO → GitLab"): toggle para `ENABLED` y dropdown de 3 valores para `EPIC_POLICY`.
- MigratorPage solo aparece en la navegación si `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED=true`.

**Archivos exactos F9:**
- `backend/api/__init__.py` (registro del blueprint — NO `app.py`).
- `backend/harness_defaults.env` (2 líneas nuevas).
- `frontend/src/components/HarnessFlagsPanel.tsx` (añadir 2 entries en categoría nueva).
- `frontend/src/App.tsx` o router (añadir ruta `/migrator` gated por flag).

**Tests F9:**
- Archivo: `backend/tests/test_plan74_migrator_wiring.py`.
- Casos:
  1. `app.test_client().get('/api/migrator/health')` con flag OFF → 503.
  2. Flag ON → `/api/migrator/health` → 200.
  3. `harness_defaults.env` contiene las 2 líneas (test de línea presente).
  4. `config.STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` lee `False` por defecto.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_wiring.py -q`.
- Frontend: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx tsc --noEmit` (0 errores).

**Criterio binario F9:** los 4 casos pasan; tsc 0 errores; flag default OFF confirmado; `migrator_bp` registrado en `api/__init__.py`.

**Trabajo del operador F9:** ninguno.

---

### F10 — Test de idempotencia end-to-end (correr 2x = sin duplicados)

**Objetivo:** demostrar empíricamente la invariante de idempotencia.

**Trabajo:** test de integración que corre el flujo completo 2 veces contra destinos mock y verifica que el count destino es estable.

**Archivos exactos F10:**
- `backend/tests/test_plan74_migrator_idempotency.py` (NUEVO) — test end-to-end con mocks.

**Tests F10 (TDD primero):**
- Casos:
  1. Setup: origen mock con 3 épicas + 5 issues + 10 comments + 2 attachments.
  2. **Corrida 1:** `plan_migration` → `execute_migration` → `verify_migration`. Verificar `applied == 8` (3+5 items) + `passed=True`.
  3. **Corrida 2 (mismo origen, mismo dest, mapping ya poblado):** `plan_migration` → `execute_migration` → `verify_migration`. Verificar `applied == 0`, `skipped == 8`, `passed=True`. **Count destino idéntico a Corrida 1.**
  4. **Corrida 3 (origen con 1 issue nuevo):** `applied == 1`, `skipped == 8`, `passed=True` con counts actualizados.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_idempotency.py -q`.

**Criterio binario F10:** los 4 casos pasan; el caso 2 vs 3 es el gate de significancia (idempotencia real, no trivial).

**Impacto por runtime:** ninguno.

**Trabajo del operador F10:** ninguno.

---

### F11 — Centinela AST read-only sobre origen + ratchet

**Objetivo:** garantizar que ningún código del migrador invoca métodos mutadores sobre el provider de origen.

**Trabajo:** test estático AST que escanea `backend/services/migrator_*.py` y `backend/api/migrator.py` y verifica que sobre la variable tipada como `origin` (o cualquier provider obtenido vía `get_tracker_provider(project)` cuando se lo marca como origen) NUNCA se invocan métodos del set `{create_item, update_item_state, update_item_assignee, post_comment, upload_attachment, link_attachment, create_work_item, update_work_item_*}`.

**Nuevo archivo:** `backend/tests/test_plan74_migrator_readonly_origin.py`.

**Patrón del test (2 controles):**
1. **AST scan:** parsear cada archivo `migrator_*.py`; para cada `Call` donde `func.attr` ∈ MUTATOR_SET y `func.value.id` coincide con un parámetro/variable anotado como origen, fallar.
2. **Import check:** `migrator_*.py` no importa `AdoClient` directamente (sólo via `get_tracker_provider`).

**Tests F11:**
- Casos:
  1. Ningún mutador invocado sobre `origin` en `migrator_core.py`, `migrator_executor.py`, `migrator_verify.py` → pass.
  2. Ningún `from services.ado_client import AdoClient` en archivos `migrator_*.py` → pass.
  3. Test canario: un snippet intencionalmente malo (en fixture) que llama `origin.create_item(...)` es detectado como violación → el centinela lo atrapa (gate de significancia).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_migrator_readonly_origin.py -q`.

**Centinela de rutas (F11 bis — C1, OBLIGATORIO por la trampa doble-prefijo de los planes 72/73):** test que arma la app y verifica que las rutas del migrador resuelven EXACTAMENTE con un solo `/api` (jamás `/api/api/migrator`).
- **Nuevo archivo:** `backend/tests/test_plan74_routes_registered.py`.
- Patrón: `rules = {r.rule for r in app.url_map.iter_rules()}`; afirmar que `"/api/migrator/health"` ∈ `rules` y que NINGUNA regla matchea `re.compile(r"^/api/api/")`. Afirmar también que `"/api/migrator/plan"` y `"/api/migrator/<stacky_project>/mapping"` existen con un solo prefijo.
- Casos:
  1. `/api/migrator/health` está registrada (un solo `/api`).
  2. No existe ninguna ruta con doble prefijo `/api/api/...` (gate de significancia: si alguien registra `migrator_bp` con `url_prefix="/api/migrator"` o lo cuelga mal, este test FALLA).
  3. `migrator_bp` está registrado bajo `api_bp` (`"migrator"` ∈ nombres de blueprints de la app).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan74_routes_registered.py -q`.

**Ratchet (F11 ter):** registrar **TODOS** los archivos `test_plan74_*.py` nuevos en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49 — incluyendo `test_plan74_routes_registered.py`. No hardcodear un número: el meta-test (Plan 49 F4) falla si queda algún `test_plan74_*.py` sin registrar. Archivo: `tests/conformance/test_harness_ratchet.py` (o el artefacto ratchet vigente).

**Criterio binario F11:** los 3 casos del centinela AST pasan; los 3 casos del centinela de rutas pasan (sin `/api/api/`); ratchet verde con todos los `test_plan74_*.py` registrados.

**Trabajo del operador F11:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Pérdida de datos en attachments.** Mitigación: F5 verifica hash post-subida; reintentos; reporte de fallidos en `failed[]`; cleanup garantizado de temp files.
2. **Duplicados por idempotencia rota (incl. DB Stacky vacía / otra máquina / crash post-create-pre-upsert).** Mitigación: marker obligatorio en cada item creado; `hydrate_map_from_destination` (F4b, **C4**) reconstruye el mapeo desde el DESTINO (fuente de verdad) antes de planear/ejecutar, así el migrador es idempotente aunque el SQLite local esté vacío; `migrator_map` consultado antes de crear; F10 corre el flujo 2x y afirma `applied==0` en la 2da corrida; F4 caso 9 prueba la hidratación.
3. **Migración parcial silenciosa.** Mitigación: F8 verifica count diffs por tipo; aborta como `needs_review` si gap>0; `failed[]` acumula errores por op sin abortar el resto.
4. **Escritura accidental en ADO (origen).** Mitigación: riel ABSOLUTO; F11 centinela AST que prohíbe mutadores sobre `origin`; F4 caso 8 (mock origen sin llamadas mutadoras); descarga de attachments (F5) es GET puro.
5. **Tier GitLab equivocado (Free vs Premium).** Mitigación: F3 política configurable `auto` (default) que reusa `_epics_native` + fallback 403 de `_link_parent` (interno de `create_item`); si el operador sabe que es Free, setea `free_degrade`.
6. **Links rotos por IDs no migrados.** Mitigación (**C2**): el link se establece en `create_item` vía `parent_id` mapeado (no por una op separada ni método privado), con orden topológico Epic→Story/Issue→Task; un padre ausente del mapeo → item creado huérfano + warning (no aborta); F4 caso 6 lo prueba.
7. **Drift del origen entre dry-run y ejecución.** Mitigación (**C5**): `/execute` recomputa `plan_hash` y lo compara con `migrator_plan_snapshot[plan_id]` (caso 4: 409 si difiere); la tabla persiste el snapshot del dry-run.
8. **3 runtimes.** Mitigación: el plan NO toca prompts ni runtime del agente; todo el cambio es capa de servicios/API/UI; los 3 runtimes siguen operativos.
9. **Falsos verdes en idempotencia.** Mitigación: F10 caso 2 vs caso 3 es el gate de significancia (si `applied` no baja a 0 en la 2da corrida, el test falla); patrón mock `assert_called`/`assert_not_called` en F4/F8/F11.

---

## 6. Fuera de scope

- **NO** migración inversa GitLab → ADO.
- **NO** migración de pipelines CI (eso estresa el `PipelineSpec` del Plan 73; los pipelines se listan en el reporte F0 pero su conversión se hace con 73).
- **NO** migración de historial Git (los commits viajan con el repo, no con work items).
- **NO** sincronización continua bidireccional (esto es una migración one-shot idempotente, no un espejo).
- **NO** forzar `created_at`/`author_id` en GitLab (frágil entre tiers; GAP-D preserva metadatos vía comment-marker).
- **NO** auth/RBAC (mono-operador, sin login).
- **NO** modificar `TrackerProvider`, `gitlab_provider`, `ado_provider` (el migrador es consumidor del puerto, no lo extiende).
- **NO** UX/notifications fuera del wizard (la capa perceptible general no se toca).

---

## 7. Glosario

- **TrackerProvider:** `Protocol` formal (`services/tracker_provider.py:56`) con 18 métodos que todo adapter de tracker debe implementar.
- **PORT_METHODS:** tupla canónica (`tracker_provider.py:79-98`).
- **`get_tracker_provider(project)`:** fábrica (`tracker_provider.py:105`) que retorna el adapter según `issue_tracker.type`.
- **Marker idempotencia:** comentario `<!-- stacky-migrated:ado:{ado_id} -->` embebido en la descripción (issues) o en el body (notes) de cada item migrado; consultado vía `comment_exists(item_id, marker)` antes de crear.
- **`comment_exists(item_id, marker)`:** método del puerto (`tracker_provider.py:69`); impl GitLab `gitlab_provider.py:262`, impl ADO `ado_provider.py:95`/`ado_client.py:809`.
- **`_project_path()`:** helper de `GitLabClient` (`services/gitlab_client.py:98`) que URL-encodea `grp/sub/proj` → `grp%2Fsub%2Fproj`.
- **`_epics_native`:** flag del `GitLabTrackerProvider` (`gitlab_provider.py:36`) que indica si se usan group epics nativos (Premium/Ultimate).
- **`_link_parent`:** método PRIVADO del `GitLabTrackerProvider` (`gitlab_provider.py:99`) que vincula hijo-padre; degrada 403 → issue-links automáticamente. **El migrador NO lo invoca** (C2): `create_item` ya lo llama internamente cuando `item.parent_id` está seteado (`gitlab_provider.py:228-229`).
- **Política épica:** `STACKY_MIGRATOR_EPIC_POLICY ∈ {auto, premium_native, free_degrade}` (default `auto`).
- **Plan de migración:** `MigrationPlan` (F2) = lista de `MigrationOp` + counts + warnings, producido SIN escribir.
- **Dry-run:** ejecución de `plan_migration` que produce el plan sin tocar el destino; obligatorio antes de `execute_migration`.
- **Mapeo `ado_id ↔ gitlab_iid`:** tabla `migrator_ado_gitlab_map` (F1) persistida en la DB SQLite de Stacky.
- **HITL gate:** `POST /execute` rechaza 400 sin `confirmed=true` explícito; el wizard exige checkbox de revisión.
- **Ratchet:** mecanismo del Plan 49 que obliga a registrar todo test nuevo en `HARNESS_TEST_FILES`; meta-test que falla si se agregan tests sin registrar.

---

## 8. Orden de implementación

1. **F0** — Inventario (cumplido en este doc, 6 filas).
2. **F1** — Mapeo persistente `migrator_map.py`.
3. **F2** — Orquestador `plan_migration` (read-only puro).
4. **F3** — Política épicas `resolve_epic_strategy` + flag `STACKY_MIGRATOR_EPIC_POLICY`.
5. **F4** — Ejecutor `execute_migration` (idempotente, marker).
6. **F5** — Attachments (hash + cleanup).
7. **F6** — API endpoints + HITL gate + drift detection.
8. **F7** — UI wizard (5 pasos).
9. **F8** — Verificación post-migración (count diffs).
10. **F9** — Wiring en `api/__init__.py` (NO `app.py`) + harness_defaults.env + HarnessFlagsPanel + ruta.
11. **F10** — Test idempotencia end-to-end (gate de significancia).
12. **F11** — Centinela AST read-only + ratchet.

Cada fase es auto-contenida y se puede implementar/commitear de forma independiente (cada una deja el sistema verde y backward-compatible).

> **Dependencia Plan 70:** los detalles finos de cómo el migrador obtiene el `origin_provider` y `dest_provider` vía `get_tracker_provider(project)` asumen que el Plan 70 ya migró los consumers de `tickets.py` al puerto. Si 70 introduce un helper `_provider_for_ticket` (Plan 70 F2), el migrador lo reusa; sino, llama directo a `get_tracker_provider`. `[a verificar tras implementar Plan 70]`. Los contratos del puerto (`PORT_METHODS`), el marker `comment_exists`, las flags, las fases F0..F11 y los tests están **fijados con evidencia de hoy** y no dependen de 70.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Tabla F0 completa y verificada (6 filas, cada fila cita método puerto exacto). — **Cumplido en este doc.**
- [ ] **(b)** `plan_migration` (F2) produce un plan SIN escribir (test F2 caso 6: mock dest nunca llamado) y ordenado topológicamente (caso 5).
- [ ] **(c)** `execute_migration` (F4) es idempotente (test F4 caso 2: 2da corrida `skipped == N`, `create_item` no llamado) incluso con DB local vacía gracias a `hydrate_map_from_destination` (caso 9).
- [ ] **(d)** Mapeo `ado_id ↔ gitlab_iid` persistente y consultable (F1) + descargable como CSV (F6).
- [ ] **(e)** Dry-run obligatorio (F6 caso 3: 400 sin `confirmed=true`); drift detection por `plan_hash` (F6 caso 4: 409 si origen cambió).
- [ ] **(f)** Verificación post-migración (F8) marca `needs_review` si gap>0.
- [ ] **(g)** Política épicas configurable (F3); reusa `_epics_native` + fallback `_link_parent` (interno de `create_item`, no llamado por el migrador).
- [ ] **(h)** Attachments migrados con descarga binaria autenticada + hash + cleanup (F5).
- [ ] **(i)** Centinela AST read-only (F11) verde; ratchet verde con **todos** los `test_plan74_*.py` registrados (sin hardcodear el número).
- [ ] **(j)** Test idempotencia end-to-end F10 verde (caso 2 vs caso 3 = gate de significancia).
- [ ] **(k)** Flag `STACKY_MIGRATOR_ADO_TO_GITLAB_ENABLED` default **OFF**; UI (wizard + HarnessFlagsPanel) visible solo con flag ON.
- [ ] **(l)** Los 3 runtimes (Codex, Claude Code, GitHub Copilot Pro) operativos sin cambios (el plan no toca prompts/runtime del agente).
- [ ] **(m)** `tsc` 0 errores en frontend.
- [ ] **(n)** **(C1)** Centinela de rutas (F11 bis) verde: `/api/migrator/*` con un solo `/api`, NINGUNA ruta `/api/api/...`; `migrator_bp` registrado en `api/__init__.py`.

---

## 10. Notas de implementación (para el modelo menor que ejecute esto)

- **Venv del repo:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`. El venv es py3.13 (ver memoria `stacky-backend-dev-test-env`); correr tests por archivo, no la suite completa.
- **Patrón mock (TDD):** importar `db` a nivel módulo; lazy-imports se parchean en el módulo origen (ver memoria `plan-28-lifecycle`). Para mockear providers, parchear `services.tracker_provider.get_tracker_provider`. **CRÍTICO:** en cada test "idempotencia / read-only", usar `Mock(name="...")` (nunca None) y afirmar con `mock_metodo.assert_called_once_with(...)` / `assert_not_called()` para evitar falsos verdes.
- **Cada commit deja el sistema verde y backward-compatible.** No acumular fases en un solo commit si una falla.
- **Falsos verdes prohibidos:** cada test de idempotencia debe afirmar que el mock del destino fue/no fue invocado.
- **Centinela AST (F11):** usar `ast.parse` sobre el texto fuente; no regex. El caso canario (snippet malo en fixture) es el gate de significancia.
- **Si una fase revela un GAP no listado en F0**, detener y actualizar este doc antes de seguir (no improvisar).
- **Marker idempotencia ya existe** en el puerto (`comment_exists`); no reimplementarlo en el migrador.
- **Detección de tier épicas ya existe** (`_epics_native` + `_link_parent` fallback 403); no duplicarla; reusarla vía `resolve_epic_strategy` (F3).
- **`_project_path()` ya URL-encodea** (`gitlab_client.py:98`); el migrador no debe recalcularlo.
