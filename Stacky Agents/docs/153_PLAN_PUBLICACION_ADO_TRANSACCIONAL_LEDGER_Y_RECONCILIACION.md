# Plan 153 — Publicación ADO transaccional: ledger + reconciliación

> **Estado:** PROPUESTO v1 (2026-07-16) · **Autor:** StackyArchitectaUltraEficientCode
> **Origen:** debate adversarial 2026-07-16 con auditoría de logs del deploy (roadmap top-5, ítem R1). Toda la evidencia archivo:línea de este doc fue **re-verificada contra el árbol el 2026-07-16**; los números de línea son referencia de ese día — **toda edición se ancla por TEXTO normativo citado, no por número de línea**.
> **Orden en el roadmap:** este plan se implementa **primero**, junto con el plan del arnés veraz (son independientes entre sí; ninguno bloquea al otro).
> **Runtimes:** este plan es **backend + UI de diagnóstico**, agnóstico del runtime de agentes (Codex CLI, Claude Code CLI, GitHub Copilot Pro). El camino de publicación a ADO (`_attempt_publish` → `ado_publisher`) es el MISMO para los 3 runtimes, así que la paridad es automática. Se declara igual por fase.
> **Flags nuevas:** **NINGUNA.** Se reusa `STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED` (existente, `backend/config.py:747-749`, default efectivo `"true"`). Mismo contrato de flag, mecanismo nuevo. NO se toca `FLAG_REGISTRY`, NO se toca `_CURATED_DEFAULTS_ON`, NO hay panel de flags nuevo.
> **Human-in-the-loop:** el sweep de reconciliación **JAMÁS republica solo**. Solo marca y lista. El desbloqueo es SIEMPRE una acción humana 1-click (el humano dispara, el sistema ejecuta).

---

## 1. Objetivo + KPI / impacto esperado

**Objetivo (1 párrafo):** reemplazar el guard de idempotencia R1.3 basado en markers JSON no-atómicos (que hoy tiene tickets **bloqueados para siempre** en el deploy) por un **ledger transaccional en DB** (`publish_ledger`) donde el INSERT con UNIQUE es el lock; migrar los markers legacy al ledger; dar al operador **visibilidad total** (panel en Diagnóstico) y **desbloqueo humano 1-click** (re-publicar / descartar); y eliminar la pérdida semi-silenciosa de hijos de épica cuando el template ADO no define el tipo `Feature` (mapeo a tipo disponible + warning visible + HTTP ≠ 200 en pérdida parcial).

**KPIs binarios (comando exacto; pytest desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe`; vitest/tsc desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend`):**

- **KPI-1 — Ledger verde:** `.venv\Scripts\python.exe -m pytest tests/test_publish_ledger.py -q` → exit 0 (ciclo de vida, carrera, migración, sweep, endpoints).
- **KPI-2 — Contrato R1.3 actualizado verde:** `.venv\Scripts\python.exe -m pytest tests/test_publish_idempotent_guard.py -q` → exit 0 (los 2 tests que parchean el interior de `_attempt_publish` migran su patch target al ledger; el resto queda intacto).
- **KPI-3 — Mapeo de tipos verde:** `.venv\Scripts\python.exe -m pytest tests/test_epic_children_type_mapping.py -q` → exit 0 (template sin `Feature` crea hijos mapeados con warning; VS402323 irreproducible en test).
- **KPI-4 — Lógica del panel verde:** `npx vitest run src/services/__tests__/publishLedgerView.test.ts` → exit 0.
- **KPI-5 — Tipos verdes:** `npx tsc --noEmit` → exit 0.
- **KPI-6 — Ratchet de tests registrado:** `grep -c "test_publish_ledger.py" scripts/run_harness_tests.sh` → `1` y `grep -c "test_publish_ledger.py" scripts/run_harness_tests.ps1` → `1` (ídem para `test_epic_children_type_mapping.py`, y para `test_autopublish_rev_from_response.py` si se hace F4).
- **KPI-7 — Ratchet de deuda UI verde:** `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0 (el .tsx nuevo de F2 nace con 0 `style={}` inline).
- **KPI-8 — Smoke real (F5):** ADO-338, ADO-339 y ADO-340 aparecen en el panel del ledger y, tras la acción humana 1-click, cada uno queda en `posted` o en `failed` **con causa visible**. Cero tickets en limbo invisible.

**Impacto esperado:** 0 ejecuciones bloqueadas de por vida por marker huérfano (hoy: 3 confirmadas en el deploy); 0 hijos de épica perdidos sin aviso (hoy: VS402323 8 veces en logs con respuesta HTTP 200); el KPI `persist_failure_count` de harness-health pasa de métrica aproximada por scan de JSON a lectura exacta del ledger.

---

## 2. Por qué ahora / gap que cierra (evidencia verificada 2026-07-16)

### 2.1 L1 — El guard R1.3 escribe un marker que NADIE transiciona ni limpia (bloqueo real HOY)

- `backend/services/agent_completion_internal.py:556` — `_r13_check_publish_guard(execution_id)`: lee `metadata_dict["publish_intent"]["marker"] == "pending"` y devuelve True (replay).
- `backend/services/agent_completion_internal.py:580` — `_r13_write_publish_intent(execution_id)`: escribe `{"marker": "pending", "at": ...}` en `metadata_json`. **Ninguna función del repo escribe jamás otro valor de `marker` ni borra la key** (verificado por grep: los únicos writers/readers de `publish_intent` son estas dos funciones y `services/harness_health.py:474-490`).
- `backend/services/agent_completion_internal.py:631` (check) y `:644` (write), dentro de `_attempt_publish` (`:603`): son **dos transacciones separadas** de read-modify-write sobre un JSON — no hay lock; dos llamadas concurrentes pueden pasar ambas el check antes de que una escriba.
- **Consecuencia en producción:** si el POST falla (o el proceso muere) después del write del marker, el retry devuelve `idempotent_replay` con reason `"publish_intent marker existente (reintento sin re-POST)"` (`agent_completion_internal.py:638`) **para siempre**. Evidencia deploy 2026-07-16: **ADO-338 / ADO-339 / ADO-340 bloqueados HOY** con ese mensaje en logs, y la transición de estado ADO salteada.

### 2.2 L3 — Hijos de épica perdidos semi-silenciosos (VS402323 8x en logs)

- `backend/api/tickets.py:7635` — `work_item_type="Feature"` **hardcodeado** en el fallback ADO de `publish_epic_children` (llamada `ado.create_work_item(...)` que abre en `:7634`). Hay un segundo call-site hardcodeado en el branch provider: `:7578` (`_tracker_item_from_kwargs(work_item_type="Feature", ...)`).
- Cuando el template del proyecto ADO (p. ej. **Basic**: Epic/Issue/Task) no define el tipo `Feature`, ADO responde error **VS402323** — visto **8 veces** en los logs del deploy auditados el 2026-07-16.
- `backend/api/tickets.py:7724-7730` — el endpoint `create_epic_children` devuelve el error **dentro del body con HTTP 200** (`return jsonify({... "error": result.error, ...}), 200`). El operador no se entera de que la épica quedó sin hijos.

### 2.3 L7 — GET extra frágil de `System.Rev`

- `backend/api/tickets.py:6736-6741` — tras publicar la épica, `autopublish_epic_from_run` hace un `get_work_item(published.ado_id, fields=["System.Rev"])` **extra** para sellar el baseline de edit-learning, cuando la respuesta del POST de creación (`create_work_item`, `wi` en `:6399-6414`) **ya trae `rev`**. Un fallo de red en ese GET degrada el baseline (warning `:6741`).

### 2.4 Métrica aproximada en harness-health

- `backend/services/harness_health.py:474-490` — `persist_failure_count` se calcula escaneando `metadata_json` de TODAS las ejecuciones del período buscando `'"publish_intent"'` con `marker == "pending"`. Con el ledger, esta métrica pasa a ser una consulta exacta e indexada.

### 2.5 Infra existente que se REUSA (leída, no supuesta)

| Símbolo | Archivo:línea (2026-07-16) | Rol en 153 |
|---|---|---|
| `session_scope()` | `backend/db.py:302` | Toda transacción del ledger. |
| `Base.metadata.create_all(engine)` + `_migrate_add_columns()` | `backend/db.py:82-83`, llamado desde `init_db()` (`db.py:40`), invocado en `app.py:243` | La tabla nueva se crea sola, sin migración destructiva. Patrón: import del modelo dentro de `init_db()` (como `AdoWriteOperation`, `db.py:58`). |
| `AdoWriteOperation` (tabla `ado_write_operations`) | `backend/services/ado_write_outbox.py` | **Patrón a calcar** (modelo SQLAlchemy definido dentro del service, `Base` importada de `db`). OJO: es OTRA tabla con OTRO propósito (outbox de escrituras Task/comment/attachment); NO se toca ni se reusa su tabla. |
| `AgentHtmlPublish` (tabla `agent_html_publish`) | `backend/services/ado_publisher.py:122-168` | Registro histórico de publicaciones OK (`status == "ok"`, `execution_id`, `ado_id`). La migración F2 lo usa para clasificar markers legacy como `posted` vs `pending`. Además su dedupe interno (`UniqueConstraint execution_id+html_sha256`, `:164-167`) es defensa en profundidad contra doble POST. |
| `PublishResult` | `backend/services/ado_publisher.py:191-202` | Campos `ok/status/reason/ado_id/record_id` que el ledger persiste en `mark_posted`/`mark_failed`. `status ∈ ok\|skipped\|failed`. |
| `_attempt_publish` | `backend/services/agent_completion_internal.py:603-674` | Punto ÚNICO de integración del guard (F1). Ya lee la flag con el patrón correcto: `from config import config as _cfg` (`:625`). |
| `AgentExecution.metadata_json` / `metadata_dict` | `backend/models.py:219` / `:260-265` | Donde viven los markers legacy que la migración F2 lee. **NO existe `.metadata`** (nombre reservado SQLAlchemy). |
| `fetch_states()` | `backend/services/ado_client.py:393-414` | Ya llama a `_apis/wit/workitemtypes`; F3 agrega un método hermano que devuelve los NOMBRES de tipos. |
| Endpoint harness-health | `backend/api/metrics.py:353` (`def harness_health()`, importa `services.harness_health as hh` en `:367`) | Consumidor de la métrica migrada. |
| Registro de blueprints | `backend/api/__init__.py` (patrón `from .diag import bp as diag_bp`, `:17`, + registro más abajo en el mismo archivo) | Donde se registra el blueprint nuevo de F2. **Los blueprints se registran ahí, NO en `app.py`** (gotcha conocido). |
| `HarnessHealthCard` montada en Diagnóstico | `frontend/src/pages/DiagnosticsPage.tsx:203` | El panel F2 se monta inmediatamente debajo, en la misma página. |
| Patrón de data-fetch de tarjeta | `frontend/src/components/OperationalHealthCard.tsx` (useEffect + api.get, declarado ahí mismo: "igual que HarnessHealthCard.tsx") | Patrón a calcar para `PublishLedgerPanel.tsx`. |
| `Tickets.createEpicChildren` | `frontend/src/api/endpoints.ts:390-402`; consumidor único `frontend/src/components/EpicChildrenPanel.tsx:88` | F3 extiende el tipo de respuesta con `warnings?: string[]` (aditivo) y muestra warnings en el panel. |
| `_PublishedEpic` | `backend/api/tickets.py:6331-6335` (NamedTuple `ado_id/title/url`), construida en `:6414` y `:6870` | F4 le agrega `rev: int \| None = None`. |
| Patrón test con DB real | p. ej. `backend/tests/test_ado_publisher_attachments.py:11,21` | `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` ANTES de cualquier import de app + `init_db()` en el test. |

---

## 3. Principios y guardarraíles

1. **El INSERT es el lock.** `try_acquire` NUNCA hace SELECT-antes-de-INSERT: inserta directo y clasifica el `IntegrityError` del UNIQUE. Así el test secuencial ejercita EXACTAMENTE el mismo code path que una carrera real (dos INSERT sobre el mismo `execution_id` → uno gana, el otro recibe IntegrityError), sin threads ni flakiness.
2. **Human-in-the-loop innegociable.** El sweep solo **marca y lista** (`pending` viejo = stale). NO hay TTL auto-republicador, NO hay retry automático del ledger, NO hay daemon que postee. Re-publicar y descartar son SIEMPRE clicks del operador. El sistema ejecuta lo que el humano dispara.
3. **Cero trabajo extra para el operador.** Todo es invisible/automático: la tabla se crea sola (`create_all`), la migración de markers legacy corre sola una vez al arrancar (idempotente), el panel aparece solo en Diagnóstico y solo muestra filas cuando hay algo que mirar. Las acciones 1-click son opcionales (desbloqueo), nunca requeridas para el flujo normal. Ninguna de las 4 excepciones duras aplica: no se bypasea revisión humana, nada es destructivo/irreversible (descartar es recuperable re-publicando), no hay prerequisito no garantizado, no se reduce seguridad.
4. **Mismo contrato de flag, mecanismo nuevo.** `STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED` OFF ⇒ `_attempt_publish` byte-idéntico al comportamiento pre-R1.3 (ni marker ni ledger). ON (default) ⇒ guard por ledger. Cualquier excepción del ledger ⇒ fallback: se procede al POST sin guardia (igual que hoy cuando el check devuelve `None`), jamás se bloquea una publicación por un fallo del propio guard.
5. **Defensa en profundidad, no única línea.** Aunque el guard deje pasar un duplicado, `publish_from_execution` ya tiene su propio dedupe por `agent_html_publish` (registro `already`, `ado_publisher.py:355-363`) y el UNIQUE `execution_id+html_sha256`. El ledger reduce la ventana; el publisher la cierra.
6. **Mono-operador sin auth.** Nada de RBAC ni permisos en los endpoints nuevos; `current_user` no se valida en ningún lado del sustrato y este plan no pretende que lo haga.
7. **Backward-compatible.** La key `persist_failure_count` de harness-health conserva nombre y semántica (conteo de intentos de publicación sin resultado); los markers legacy en `metadata_json` NO se borran (historia inmutable) — la idempotencia de la migración es la existencia de la fila en el ledger, no una mutación del metadata. El endpoint `epic-children` mantiene el shape del body (solo AGREGA `warnings`) y usa 207 (2xx) para pérdida parcial, así el `api.post` del frontend no rompe.
8. **Sin daemons nuevos.** El "sweep" es una función PURA de lectura (`snapshot_stuck`) evaluada on-read por el endpoint GET y por harness-health. No hay thread. (Si en el futuro alguien lo convierte en daemon: gate obligatorio con `STACKY_TEST_MODE`, gotcha plan 146.)

---

## 4. Glosario (para un modelo menor que no conoce Stacky)

| Término | Definición |
|---|---|
| **R1.3** | Nombre interno del guard de idempotencia de publicación introducido por un plan anterior: "persistir intención antes del POST a ADO para que un retry no re-postee". Este plan reemplaza su MECANISMO (marker JSON) conservando su CONTRATO (misma flag, mismo objetivo). |
| **marker** | Objeto `{"marker": "pending", "at": "<iso>"}` bajo la key `publish_intent` dentro de `AgentExecution.metadata_json`. Es el mecanismo legacy defectuoso: nadie lo transiciona ni lo limpia. |
| **idempotent_replay** | Resultado de `_attempt_publish` cuando el guard detecta que ya hubo un intento: retorna sin re-postear, con `event: "publish.idempotent_replay"`. |
| **autopublish** | Flujo backend que publica automáticamente en ADO el resultado HTML de una ejecución de agente (épica desde brief, o comentario/artefacto), sin que el operador copie/pegue. |
| **épica-desde-brief** | Único flujo con bypass de revisión humana aceptado en Stacky: un brief del operador genera y publica una Épica en ADO automáticamente. Este plan NO cambia ese flujo más allá del tipo de work item de sus hijos (F3). |
| **workitemtypes** | Endpoint REST de Azure DevOps (`_apis/wit/workitemtypes`) que lista los tipos de work item definidos por el template de proceso del proyecto (p. ej. Epic, Feature, User Story, Task). |
| **template Basic / Agile** | Plantillas de proceso de ADO. **Agile** define Epic→Feature→User Story→Task. **Basic** define solo Epic→Issue→Task (NO tiene `Feature`) — crear un `Feature` ahí devuelve error VS402323. |
| **VS402323** | Código de error de ADO: el tipo de work item no existe en el proceso del proyecto. |
| **ledger** | Tabla `publish_ledger`: una fila por `execution_id` (UNIQUE) con el estado de su publicación (`pending`/`posted`/`failed`). El INSERT atómico de la fila ES el lock de idempotencia. |
| **stale** | Fila del ledger en `pending` cuya `updated_at` es más vieja que 30 minutos: el POST arrancó y nunca terminó (proceso muerto o excepción sin registrar). Se LISTA para el humano; jamás se re-postea sola. |
| **sweep / reconciliación** | Cálculo de solo-lectura (`snapshot_stuck`) que clasifica las filas del ledger en stale/failed para el panel y la métrica. No es un daemon y no ejecuta acciones. |
| **outbox (`ado_write_operations`)** | OTRA tabla preexistente para escrituras ADO de Tasks/comentarios/attachments con retries. NO confundir con el ledger de este plan; no se toca. |

---

## 5. Fases

> **Pre-flight OBLIGATORIO por fase que toque archivo caliente** (`backend/services/agent_completion_internal.py`, `backend/api/tickets.py`, `backend/services/harness_health.py`, `frontend/src/pages/DiagnosticsPage.tsx`, `frontend/src/api/endpoints.ts`): `git status -- "<ruta>"`. Si hay WIP ajeno, STOP y avisar al orquestador. Staging quirúrgico por path explícito. **El implementador NO commitea** (lo hace el orquestador).
>
> **Comandos:** pytest SIEMPRE por archivo desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend` con `.venv\Scripts\python.exe -m pytest tests/<archivo> -q` (el venv real verificado en disco es `backend\.venv`, py3.13). Vitest SIEMPRE por archivo desde `N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend` con `npx vitest run <archivo>`. Nunca suite completa (test-order pollution en ambos lados).

---

### F0 — Test rojo que reproduce el bloqueo real

**Objetivo (1 frase):** dejar en el repo un test que documente el deadlock actual (marker pending legacy + retry → `idempotent_replay` eterno) y un test rojo que exija el mecanismo nuevo. **Valor:** TDD honesto — el problema queda reproducido antes de tocar una línea de producción.

**Archivos:**
- NUEVO `backend/tests/test_publish_ledger.py`

**Contenido exacto inicial (2 tests):**

```python
"""Tests Plan 153 — publish_ledger transaccional + reconciliación."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# OBLIGATORIO antes de cualquier import de módulos de la app:
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


def test_marker_legacy_pending_bloquea_retry_hoy():
    """Documenta el bloqueo real (ADO-338/339/340): marker pending => replay eterno, 0 POSTs.

    NOTA F1: cuando _attempt_publish migre al ledger, este test se ACTUALIZA
    (ver F1 paso 4) para afirmar el equivalente vía ledger. Hasta entonces,
    afirma el comportamiento legacy tal cual existe.
    """
    from services.agent_completion_internal import _attempt_publish

    post_calls = []
    with patch("config.config") as mock_cfg:
        mock_cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED = True
        with patch(
            "services.agent_completion_internal._r13_check_publish_guard",
            return_value=True,
        ):
            with patch(
                "services.ado_publisher.publish_from_execution",
                side_effect=lambda *a, **k: post_calls.append(1),
            ):
                result = _attempt_publish(execution_id=338, triggered_by="retry")

    assert result.get("event") == "publish.idempotent_replay"
    assert post_calls == []  # el retry queda bloqueado sin re-POST — para siempre


def test_ledger_module_existe():
    """ROJO HOY por la razon correcta: el mecanismo transaccional no existe."""
    from services.publish_ledger import (  # ModuleNotFoundError hoy
        migrate_legacy_markers,
        try_acquire,
    )

    assert callable(try_acquire)
    assert callable(migrate_legacy_markers)
```

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_publish_ledger.py -q` → **1 passed, 1 failed**, y el failed es exactamente `ModuleNotFoundError: No module named 'services.publish_ledger'`. Registrar YA el archivo en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` y `backend/scripts/run_harness_tests.ps1` (mismo formato que las entradas vecinas).

**Flag:** N/A (solo test). **Runtimes:** N/A (test backend puro). **Trabajo del operador: ninguno.**

---

### F1 — Tabla `publish_ledger` + integración transaccional en `_attempt_publish`

**Objetivo (1 frase):** crear el ledger cuyo INSERT atómico reemplaza la carrera read-modify-write del marker, y transicionar a `posted`/`failed` en el éxito/except del POST. **Valor:** cierra L1 de raíz — un retry nunca más queda bloqueado invisible, y dos publicaciones concurrentes producen exactamente 1 POST.

**Archivos:**
- NUEVO `backend/services/publish_ledger.py`
- MODIFICADO `backend/services/agent_completion_internal.py` (solo el cuerpo de `_attempt_publish`, bloque `:623-674`; las funciones `_r13_check_publish_guard` y `_r13_write_publish_intent` QUEDAN — dejan de ser llamadas por `_attempt_publish` pero conservan sus tests de unidad y documentan el formato del marker legacy que F2 migra; actualizar su docstring con la palabra "legacy").
- MODIFICADO `backend/db.py` (una línea en `init_db()`: import del modelo, patrón `AdoWriteOperation` en `db.py:58`).
- MODIFICADO `backend/tests/test_publish_idempotent_guard.py` (solo los 2 tests que parchean el interior de `_attempt_publish`).
- MODIFICADO `backend/tests/test_publish_ledger.py` (crece con los tests de F1).

**Símbolos EXACTOS de `services/publish_ledger.py`:**

```python
"""publish_ledger.py — Plan 153. Ledger transaccional de publicaciones a ADO.

Reemplaza el mecanismo R1.3 de markers en metadata_json. El INSERT con UNIQUE
sobre execution_id ES el lock: no hay check previo, no hay carrera.
El desbloqueo de filas pending/failed es SIEMPRE una accion humana (api/publish_ledger).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, mapped_column

from db import Base, session_scope

logger = logging.getLogger("stacky.publish_ledger")

STATUS_PENDING = "pending"
STATUS_POSTED = "posted"
STATUS_FAILED = "failed"

STALE_MINUTES = 30  # umbral de "stale" para el sweep de solo-lectura


class PublishLedgerEntry(Base):
    __tablename__ = "publish_ledger"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execution_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pending | posted | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    ado_ids: Mapped[str | None] = mapped_column(Text)   # JSON list[int]
    error: Mapped[str | None] = mapped_column(Text)      # truncado a 500 chars
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="runtime")  # runtime | migration

    def to_dict(self) -> dict: ...  # id, execution_id, status, created_at/updated_at isoformat, ado_ids json.loads, error, source


def try_acquire(execution_id: int) -> str:
    """INSERT-primero. 'acquired' si esta llamada gano el lock;
    'replay_pending' | 'replay_posted' | 'replay_failed' | 'replay_unknown' si ya existia fila.
    Excepciones NO-IntegrityError PROPAGAN (el caller decide el fallback)."""


def mark_posted(execution_id: int, ado_id: int | None, record_id: int | None = None) -> bool: ...
def mark_failed(execution_id: int, error: str) -> bool: ...          # error[:500]
def release(execution_id: int) -> bool:
    """Borra la fila (usado en dos casos: publish 'skipped' que no debe dejar
    fantasma pending, y la accion humana re-publicar antes de reintentar)."""


def snapshot_stuck(stale_minutes: int = STALE_MINUTES) -> dict:
    """SOLO LECTURA (el 'sweep'). Devuelve:
    {"pending_stale": [to_dict...], "failed": [to_dict...],
     "counts": {"pending": n, "pending_stale": n, "failed": n, "posted": n}}
    pending_stale = status=='pending' AND updated_at < utcnow - stale_minutes."""


def count_persist_failures(since: datetime) -> int:
    """Metrica exacta para harness-health: filas status=='pending' con created_at >= since."""


def migrate_legacy_markers() -> dict:
    """One-shot idempotente (F2 la especifica; el stub puede crearse aca en F1
    devolviendo {'migrated': 0, 'skipped': 0} para que F0.test_ledger_module_existe pase)."""
```

**Implementación EXACTA de `try_acquire` (el corazón — copiar esta lógica):**

```python
def try_acquire(execution_id: int) -> str:
    try:
        with session_scope() as session:
            session.add(PublishLedgerEntry(
                execution_id=int(execution_id), status=STATUS_PENDING, source="runtime",
            ))
            session.flush()
        return "acquired"
    except IntegrityError:
        with session_scope() as session:
            row = (
                session.query(PublishLedgerEntry)
                .filter(PublishLedgerEntry.execution_id == int(execution_id))
                .one_or_none()
            )
            status = row.status if row is not None else "unknown"
        return f"replay_{status}"
```

**Edición EXACTA de `_attempt_publish`** (ancla de texto: el bloque que empieza en el comentario `# R1.3 — guardia de idempotencia: detecta replays sin re-postear.`, hoy `agent_completion_internal.py:623`). La lectura de flag (`from config import config as _cfg` / `_r13_enabled`) se conserva tal cual. Se reemplaza el bloque `if _r13_enabled:` completo (hoy `:630-644`) por:

```python
    _ledger_acquired = False
    if _r13_enabled:
        try:
            from services import publish_ledger as _ledger
            _acquire = _ledger.try_acquire(execution_id)
        except Exception:  # noqa: BLE001 — ledger no disponible => proceder sin guardia
            _acquire = None
        if _acquire is not None and _acquire != "acquired":
            logger.info(
                "[exec=%s] idempotent_replay via ledger (%s): no se re-postea",
                execution_id, _acquire,
            )
            return {
                "ok": False,
                "status": "idempotent_replay",
                "reason": f"publish_ledger {_acquire} (reintento sin re-POST; desbloqueo humano en Diagnostico)",
                "execution_id": execution_id,
                "event": "publish.idempotent_replay",
                "ledger": _acquire,
            }
        _ledger_acquired = _acquire == "acquired"
```

Y en los TRES desenlaces del POST (anclas de texto, hoy `:646-674`), agregar best-effort (cada bloque envuelto en `try/except Exception: pass` con `if _ledger_acquired:`):
- rama `except Exception as exc` de `publish_from_execution` → `_ledger.mark_failed(execution_id, str(exc))`
- rama `if pr.ok:` → `_ledger.mark_posted(execution_id, pr.ado_id, pr.record_id)`
- rama final `pr.ok == False` → si `pr.status == "skipped"` → `_ledger.release(execution_id)` (no dejar fantasma pending); si no → `_ledger.mark_failed(execution_id, pr.reason or pr.status)`

**Edición EXACTA de `backend/db.py`** — dentro de `init_db()`, junto a la línea `from services.ado_write_outbox import AdoWriteOperation` (`db.py:58`), agregar:

```python
    from services.publish_ledger import PublishLedgerEntry  # noqa: F401  (Plan 153 — ledger publicacion)
```

**Edición EXACTA de `backend/tests/test_publish_idempotent_guard.py`** (solo 2 tests; el resto NO se toca):
- `test_attempt_publish_idempotent_replay_detected` (hoy `:74-85`): reemplazar el patch `"services.agent_completion_internal._r13_check_publish_guard", return_value=True` por `"services.publish_ledger.try_acquire", return_value="replay_pending"`. El assert `result.get("event") == "publish.idempotent_replay"` queda igual.
- `test_attempt_publish_writes_intent_before_post` (hoy `:88-116`): reemplazar los dos patches `_r13_*` por `patch("services.publish_ledger.try_acquire", return_value="acquired")` y `patch("services.publish_ledger.mark_posted", side_effect=lambda eid, *a, **k: intent_written.append(eid) or True)`. Asserts (`10 in intent_written`, `result["ok"] is True`) quedan iguales.

**Y actualizar el test F0** `test_marker_legacy_pending_bloquea_retry_hoy` (como anuncia su docstring): el patch pasa de `_r13_check_publish_guard` a `"services.publish_ledger.try_acquire", return_value="replay_pending"`, mismo assert. Renombrarlo a `test_replay_pending_bloquea_retry_sin_repost`.

**Tests F1 (agregar a `tests/test_publish_ledger.py`; todos usan `init_db()` al inicio — patrón `test_ado_publisher_attachments.py:21`):**

| Test | Qué afirma |
|---|---|
| `test_try_acquire_gana_y_duplicado_clasifica` | 1ª llamada → `"acquired"`; 2ª llamada mismo id → `"replay_pending"`. |
| `test_lifecycle_posted` | acquire → `mark_posted(1, ado_id=99, record_id=5)` → fila `status=="posted"`, `ado_ids` contiene 99, 3ª acquire → `"replay_posted"`. |
| `test_lifecycle_failed` | acquire → `mark_failed(2, "boom")` → `status=="failed"`, `error=="boom"`; acquire → `"replay_failed"`. |
| `test_release_borra_y_permite_reacquire` | acquire → `release` → acquire de nuevo → `"acquired"`. |
| `test_carrera_dos_attempt_publish_solo_un_post` | Con flag ON y `publish_from_execution` mockeado (contador + `PublishResult` ok), llamar `_attempt_publish(execution_id=7, ...)` DOS veces → contador == 1; 2º resultado `event == "publish.idempotent_replay"` y `ledger == "replay_posted"`. (Mismo code path que una carrera real: ver §3.1.) |
| `test_publish_skipped_no_deja_fantasma` | publish mock devuelve `ok=False, status="skipped"` → tras `_attempt_publish` NO hay fila para ese execution_id (release aplicado). |
| `test_ledger_roto_fallback_procede_sin_guardia` | `patch("services.publish_ledger.try_acquire", side_effect=RuntimeError)` → el POST ocurre igual (contador == 1). |
| `test_flag_off_no_toca_ledger` | flag OFF + publish mock → 0 filas en `publish_ledger`. |

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_publish_ledger.py -q` → exit 0 **y** `.venv\Scripts\python.exe -m pytest tests/test_publish_idempotent_guard.py -q` → exit 0.

**Flag que la protege:** `STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED` (existente, default ON). **Runtimes:** camino compartido por los 3 (el guard vive debajo del runtime); paridad automática. **Trabajo del operador: ninguno** (tabla creada por `create_all`, sin config nueva).

---

### F2 — Migración one-shot de markers legacy + sweep de solo-lectura + panel humano 1-click + harness-health exacto

**Objetivo (1 frase):** migrar los markers legacy al ledger (clasificando `posted` vs `pending` contra `agent_html_publish`), exponer los stuck en un panel de Diagnóstico con acciones humanas re-publicar/descartar, y hacer que `persist_failure_count` lea el ledger. **Valor:** ADO-338/339/340 dejan de ser invisibles; el operador desbloquea con 1 click; la métrica pasa de aproximada a exacta.

**Archivos:**
- MODIFICADO `backend/services/publish_ledger.py` (implementación real de `migrate_legacy_markers`)
- MODIFICADO `backend/app.py` (1 llamada tras `init_db()`)
- NUEVO `backend/api/publish_ledger.py` (blueprint)
- MODIFICADO `backend/api/__init__.py` (import + registro del blueprint, patrón `diag_bp` `:17`)
- MODIFICADO `backend/services/harness_health.py` (bloque `:474-490`)
- MODIFICADO `frontend/src/api/endpoints.ts` (grupo `PublishLedger`)
- NUEVO `frontend/src/services/publishLedgerView.ts` + NUEVO `frontend/src/services/__tests__/publishLedgerView.test.ts`
- NUEVO `frontend/src/components/PublishLedgerPanel.tsx` + `PublishLedgerPanel.module.css`
- MODIFICADO `frontend/src/pages/DiagnosticsPage.tsx` (montar el panel)
- MODIFICADO `backend/tests/test_publish_ledger.py` (tests F2)

**`migrate_legacy_markers()` — implementación EXACTA:**

```python
def migrate_legacy_markers() -> dict:
    """One-shot idempotente. Lee markers legacy publish_intent 'pending' de
    AgentExecution.metadata_json y los materializa como filas del ledger.
    NUNCA muta metadata_json (historia inmutable): la idempotencia es la
    existencia de la fila (UNIQUE execution_id). NUNCA postea a ADO."""
    from models import AgentExecution
    from services.ado_publisher import AgentHtmlPublish

    migrated_posted = 0
    migrated_pending = 0
    skipped = 0
    with session_scope() as session:
        rows = (
            session.query(AgentExecution.id, AgentExecution.metadata_json)
            .filter(AgentExecution.metadata_json.contains('"publish_intent"'))
            .all()
        )
        existing_ids = {r.execution_id for r in session.query(PublishLedgerEntry.execution_id).all()}
        ok_publishes = {
            p.execution_id: p.ado_id
            for p in session.query(AgentHtmlPublish)
            .filter(AgentHtmlPublish.status == "ok")
            .all()
            if p.execution_id is not None
        }
        for exec_id, md_raw in rows:
            try:
                marker = (json.loads(md_raw or "{}").get("publish_intent") or {}).get("marker")
            except Exception:  # noqa: BLE001
                marker = None
            if marker != "pending" or exec_id in existing_ids:
                skipped += 1
                continue
            if exec_id in ok_publishes:
                session.add(PublishLedgerEntry(
                    execution_id=exec_id, status=STATUS_POSTED, source="migration",
                    ado_ids=json.dumps([ok_publishes[exec_id]]),
                ))
                migrated_posted += 1
            else:
                session.add(PublishLedgerEntry(
                    execution_id=exec_id, status=STATUS_PENDING, source="migration",
                ))
                migrated_pending += 1
    return {"migrated_posted": migrated_posted, "migrated_pending": migrated_pending, "skipped": skipped}
```

**Enganche en `backend/app.py`** — ancla de texto: la llamada `init_db()` (hoy `app.py:243`). Inmediatamente después, agregar:

```python
    # Plan 153 — migracion one-shot de markers legacy al publish_ledger (idempotente, sin red).
    if os.getenv("STACKY_TEST_MODE", "").strip() not in ("1", "true"):
        try:
            from services.publish_ledger import migrate_legacy_markers
            _mig = migrate_legacy_markers()
            if _mig.get("migrated_pending") or _mig.get("migrated_posted"):
                logging.getLogger("stacky.publish_ledger").info("migracion markers legacy: %s", _mig)
        except Exception:  # noqa: BLE001 — la migracion jamas impide arrancar
            logging.getLogger("stacky.publish_ledger").warning("migracion markers legacy fallo", exc_info=True)
```

(Es un scan LOCAL de la DB — cero red, cero ADO — así que no repite el gotcha de `_startup_sync`. El gate `STACKY_TEST_MODE` evita efectos colaterales en pytest; los tests la llaman explícito.)

**Blueprint `backend/api/publish_ledger.py` — rutas EXACTAS** (calcar estructura de `backend/api/diag.py`; blueprint `bp = Blueprint("publish_ledger", __name__, url_prefix="/api/publish-ledger")`; registrar en `backend/api/__init__.py` con `from .publish_ledger import bp as publish_ledger_bp` junto a sus vecinos y el `register_blueprint` correspondiente más abajo en el MISMO archivo — buscar `diag_bp` para ver el patrón; NUNCA en `app.py`):

| Ruta | Método | Comportamiento exacto |
|---|---|---|
| `""` | GET | Devuelve `{"enabled": <flag>, **snapshot_stuck()}` con HTTP 200. `enabled` se lee con `from config import config as cfg` → `cfg.STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED`. |
| `"/<int:execution_id>/republish"` | POST | ACCIÓN HUMANA. Si la fila no existe → 404 `{"error": "no_ledger_row"}`. Si `status == "posted"` → 409 `{"error": "already_posted"}`. Si no: `release(execution_id)`, luego `result = _attempt_publish(execution_id=execution_id, triggered_by="operator_republish")` (import: `from services.agent_completion_internal import _attempt_publish`), devolver `{"result": result, "ledger": <fila actual to_dict o None>}` con 200. |
| `"/<int:execution_id>/discard"` | POST | ACCIÓN HUMANA. Si la fila no existe → 404. Si `status == "posted"` → 409. Si no: `mark_failed(execution_id, "descartado por el operador")`, devolver `{"ledger": <fila to_dict>}` con 200. Recuperable: re-publicar sigue disponible sobre una fila failed. |

**`backend/services/harness_health.py`** — reemplazar el bloque completo que empieza en el comentario `# R2.1 — publish_intent (persist failures aproximados: markers sin resultado ok).` (hoy `:474-490`) por:

```python
    # R2.1 — persist failures EXACTOS desde publish_ledger (Plan 153; antes: scan de markers).
    try:
        from services.publish_ledger import count_persist_failures
        result["persist_failure_count"] = count_persist_failures(since)
    except Exception:  # noqa: BLE001
        result["persist_failure_count"] = "--"
```

(Misma key, mismo fallback `"--"` — el consumidor `api/metrics.py:353` y `HarnessHealthCard` no cambian.)

**Frontend:**
- `endpoints.ts`: agregar grupo `PublishLedger` con `list: () => api.get<...>("/api/publish-ledger")`, `republish: (executionId: number) => api.post<...>(\`/api/publish-ledger/${executionId}/republish\`, {})`, `discard: (executionId: number) => api.post<...>(\`/api/publish-ledger/${executionId}/discard\`, {})`. Tipos: `PublishLedgerItem { id: number; execution_id: number; status: "pending" | "posted" | "failed"; created_at: string; updated_at: string; ado_ids: number[] | null; error: string | null; source: string }` y `PublishLedgerSnapshot { enabled: boolean; pending_stale: PublishLedgerItem[]; failed: PublishLedgerItem[]; counts: Record<string, number> }`.
- NUEVO `frontend/src/services/publishLedgerView.ts` — helpers PUROS (sin DOM, sin fetch): `partitionLedger(snapshot): { actionable: PublishLedgerItem[]; empty: boolean }` (concatena `pending_stale` + `failed` ordenado por `updated_at` desc), `ledgerRowLabel(item): string` (p. ej. `"exec 338 · pending desde <updated_at local> · <error o 'sin error registrado'>"`), `canRepublish(item): boolean` (`status !== "posted"`). Lógica testeable sin RTL/jsdom (gap estructural conocido: no están en package.json).
- NUEVO `frontend/src/components/PublishLedgerPanel.tsx`: patrón useEffect + api.get calcado de `OperationalHealthCard.tsx`; si `partitionLedger(...).empty` → render `null` (el panel NO ocupa espacio cuando no hay stuck — cero ruido para el operador); si hay filas → tabla con `ledgerRowLabel` + 2 botones por fila: "Re-publicar" (llama `PublishLedger.republish`, disabled mientras está en vuelo, refresca al terminar) y "Descartar" (ídem con `discard`). **0 `style={}` inline; todo en `PublishLedgerPanel.module.css` con tokens de `theme.css`** (KPI-7; para anchos dinámicos usar ref+effect imperativo, gotcha uiDebtRatchet conocido).
- `DiagnosticsPage.tsx`: montar `<PublishLedgerPanel />` en la línea siguiente a `<HarnessHealthCard />` (ancla de texto, hoy `:203`).

**Tests F2 (agregar a `tests/test_publish_ledger.py`; los de endpoint usan `create_app()` + `app.test_client()` con `DATABASE_URL` in-memory ya seteado):**

| Test | Qué afirma |
|---|---|
| `test_migracion_marker_pending_sin_publicacion_queda_pending` | Ejecución con marker legacy y sin fila `agent_html_publish` ok → fila ledger `pending`, `source=="migration"`. |
| `test_migracion_marker_con_publicacion_ok_queda_posted` | Con fila `AgentHtmlPublish(status="ok", execution_id=X, ado_id=77, ...)` → ledger `posted` con `ado_ids==[77]`. |
| `test_migracion_idempotente` | Ejecutarla 2 veces → segunda corrida `migrated_* == 0`, mismas filas. |
| `test_migracion_no_muta_metadata` | El `metadata_json` de la ejecución es byte-idéntico antes/después. |
| `test_snapshot_stuck_clasifica` | Fila pending con `updated_at` forzada 31 min atrás → en `pending_stale`; fila failed → en `failed`; fila posted → solo en `counts`. |
| `test_endpoint_get_lista` | GET `/api/publish-ledger` → 200, body con `enabled`, `pending_stale`, `failed`, `counts`. |
| `test_endpoint_republish_desbloquea` | Fila pending stale + `patch("services.agent_completion_internal._attempt_publish", return_value={"ok": True, ...})` espiado → POST republish → 200, `_attempt_publish` llamado exactamente 1 vez con `triggered_by="operator_republish"`, fila vieja liberada. |
| `test_endpoint_republish_rechaza_posted` | Fila posted → POST republish → 409, `_attempt_publish` 0 llamadas. |
| `test_endpoint_discard_marca_failed` | Fila pending → POST discard → 200, fila `failed` con error `"descartado por el operador"`. |
| `test_harness_health_persist_failure_count_exacto` | 2 filas pending dentro de la ventana + 1 posted → `count_persist_failures(since) == 2`. |

**Criterios de aceptación BINARIOS:**
1. `.venv\Scripts\python.exe -m pytest tests/test_publish_ledger.py -q` → exit 0.
2. `npx vitest run src/services/__tests__/publishLedgerView.test.ts` → exit 0 (casos: partición ordena y concatena; empty true sin filas; `canRepublish` false solo para posted; `ledgerRowLabel` sin error usa el literal `"sin error registrado"`).
3. `npx tsc --noEmit` → exit 0.
4. `npx vitest run src/__tests__/uiDebtRatchet.test.ts` → exit 0.

**Flag:** la misma (`enabled` en el GET refleja su valor; las acciones humanas funcionan aunque el guard esté OFF porque operan sobre filas existentes). **Runtimes:** backend+UI compartidos por los 3; paridad automática. **Trabajo del operador: ninguno** — la migración corre sola al arrancar; el panel aparece solo cuando hay stuck; las acciones 1-click son opcionales (human-in-the-loop puro: el humano dispara, el sistema ejecuta).

---

### F3 — Workitemtypes descubiertos + mapeo `Feature`→tipo disponible + pérdida parcial visible (HTTP ≠ 200)

**Objetivo (1 frase):** descubrir (cacheado por proyecto) qué tipos define el template ADO, mapear `Feature` al tipo disponible cuando no existe, y hacer visible la pérdida parcial de hijos con `warnings` en el body y HTTP 207. **Valor:** cierra L3 — VS402323 irreproducible y el operador SIEMPRE se entera si la épica quedó sin hijos.

**Archivos:**
- MODIFICADO `backend/services/ado_client.py` (1 método nuevo junto a `fetch_states`, `:393-414`)
- MODIFICADO `backend/api/tickets.py` (resolver + uso en `publish_epic_children` + status code y `warnings` en `create_epic_children`)
- MODIFICADO `frontend/src/api/endpoints.ts` (tipo de respuesta de `createEpicChildren` + `warnings?: string[]`, aditivo)
- MODIFICADO `frontend/src/components/EpicChildrenPanel.tsx` (mostrar warnings si llegan; ancla de texto `const res = await Tickets.createEpicChildren({`, hoy `:88`)
- NUEVO `backend/tests/test_epic_children_type_mapping.py`

**Método nuevo EXACTO en `AdoClient`** (pegar inmediatamente después de `fetch_states`, reusando la MISMA URL que `fetch_states` usa en `:401-404`):

```python
    def fetch_work_item_type_names(self) -> list[str]:
        """Nombres de los work item types definidos por el proceso del proyecto.
        Ej.: template Agile -> ["Epic", "Feature", "User Story", "Task", ...];
        template Basic -> ["Epic", "Issue", "Task"]. Propaga AdoApiError."""
        url = (
            f"{self._base_proj}/_apis/wit/workitemtypes"
            f"?api-version={_API_VERSION}"
        )
        data = self._request("GET", url)
        return [
            (wit.get("name") or "").strip()
            for wit in (data.get("value") or [])
            if (wit.get("name") or "").strip()
        ]
```

**Resolver EXACTO en `backend/api/tickets.py`** (nivel de módulo, cerca de `publish_epic_children`; cache TTL 600 s por nombre de proyecto):

```python
_WIT_TYPES_CACHE: dict[str, tuple[float, list[str]]] = {}
_WIT_TYPES_TTL_SECONDS = 600
_FEATURE_FALLBACK_ORDER = ["User Story", "Issue", "Product Backlog Item", "Requirement"]


def _resolve_feature_type(client, project_name: str | None) -> tuple[str, str | None]:
    """(tipo_a_usar, warning|None). Ante CUALQUIER fallo de descubrimiento
    devuelve ("Feature", None) == comportamiento actual, sin romper nada."""
    cache_key = project_name or "__default__"
    now = _time.time()
    cached = _WIT_TYPES_CACHE.get(cache_key)
    if cached is not None and (now - cached[0]) < _WIT_TYPES_TTL_SECONDS:
        types = cached[1]
    else:
        try:
            types = client.fetch_work_item_type_names()
            _WIT_TYPES_CACHE[cache_key] = (now, types)
        except Exception:  # noqa: BLE001 — descubrimiento es best-effort
            return ("Feature", None)
    if "Feature" in types:
        return ("Feature", None)
    for candidate in _FEATURE_FALLBACK_ORDER:
        if candidate in types:
            return (
                candidate,
                f"el template ADO del proyecto no define 'Feature'; "
                f"los hijos de la epica se crean como '{candidate}'",
            )
    return (
        "Feature",
        "el template ADO no define 'Feature' ni un tipo alternativo conocido; "
        "la creacion de hijos puede fallar (VS402323)",
    )
```

(`import time as _time` si no existe ya un alias en el módulo; verificar con grep antes de agregar.)

**Uso en `publish_epic_children`:** al inicio de la función (ancla de texto: antes del comentario `# Plan 70 F8 — branch provider para publish_epic_children (GAP-E)`, hoy `:7563`), resolver UNA vez:

```python
    child_feature_type = "Feature"
    type_warning: str | None = None
    try:
        _type_client = ado if ado is not None else build_ado_client(project_name)
        child_feature_type, type_warning = _resolve_feature_type(_type_client, project_name)
    except Exception:  # noqa: BLE001 — tracker no-ADO o sin config => comportamiento actual
        pass
```

y reemplazar los DOS literales hardcodeados por la variable: `_tracker_item_from_kwargs(work_item_type=child_feature_type, ...)` (hoy `:7578`) y `ado.create_work_item(work_item_type=child_feature_type, ...)` (hoy `:7635`). Los `work_item_type="Task"` NO se tocan (Basic define Task). Extender el NamedTuple `_ChildrenPublishResult` con campo aditivo `warnings: list = []` y poblar `[type_warning]` cuando no sea None, en los `return` de ambos branches.

**Endpoint `create_epic_children`** — reemplazar el `return` final (ancla de texto: `return jsonify({` con `"created_ids": result.created_ids`, hoy `:7724-7730`) por:

```python
    warnings = list(getattr(result, "warnings", []) or [])
    status_code = 200 if result.error is None else 207  # 207 = perdida parcial VISIBLE (2xx: no rompe api.post)
    return jsonify({
        "enabled": True,
        "created_ids": result.created_ids,
        "reused_ids": result.reused_ids,
        "error": result.error,
        "skipped": result.skipped,
        "warnings": warnings,
    }), status_code
```

**GOTCHA OBLIGATORIO en este archivo:** si en cualquier punto de F3 hay que leer una flag de configuración dentro de `api/tickets.py`, la instancia es **`config.config`** (el atributo `config` del módulo `config`), NUNCA `getattr(config, FLAG)` sobre el módulo — eso devuelve siempre el default y mata el branch OFF (bit real de los planes 131 y 148). F3 tal como está especificada NO lee flags nuevas.

**Frontend:** en `endpoints.ts:396-402` agregar `warnings?: string[];` al tipo de respuesta de `createEpicChildren`. En `EpicChildrenPanel.tsx`, después de recibir `res`, si `res.warnings?.length` mostrar cada warning en el elemento de estado/aviso que el componente ya usa para `res.error` (reusar el MISMO patrón visual existente en el componente; no crear primitivas nuevas).

**Tests (`backend/tests/test_epic_children_type_mapping.py`, con `DATABASE_URL` in-memory al tope como en F0):**

| Test | Qué afirma |
|---|---|
| `test_template_agile_usa_feature` | Cliente fake con `fetch_work_item_type_names → ["Epic","Feature","User Story","Task"]` → `_resolve_feature_type` devuelve `("Feature", None)`. |
| `test_template_basic_mapea_a_issue` | Tipos `["Epic","Issue","Task"]` → `("Issue", warning != None)` (nota: "User Story" no está, "Issue" sí). |
| `test_template_scrum_mapea_a_pbi` | Tipos `["Epic","Product Backlog Item","Task"]` → `("Product Backlog Item", warning)`. |
| `test_descubrimiento_falla_fallback_feature` | `fetch_work_item_type_names` lanza → `("Feature", None)` — byte-idéntico a hoy. |
| `test_cache_por_proyecto` | 2 llamadas seguidas mismo proyecto → el fetch del cliente se invoca 1 sola vez (limpiar `_WIT_TYPES_CACHE` en el setup del test). |
| `test_publish_children_sin_feature_crea_mapeado_con_warning` | `publish_epic_children` con ado fake (tipos Basic; `create_work_item` graba kwargs) → todas las Features del plan se crean con `work_item_type == "Issue"` y `result.warnings` no vacío. VS402323 irreproducible: el tipo inexistente jamás se envía. |
| `test_endpoint_207_con_perdida_parcial` | `create_epic_children` vía test client con `publish_epic_children` parcheado devolviendo `error != None` → HTTP **207** y body con `error` y `warnings`. |
| `test_endpoint_200_sin_error` | Resultado sin error → HTTP 200, `warnings == []`. |

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_epic_children_type_mapping.py -q` → exit 0, y el archivo registrado en `HARNESS_TEST_FILES` (sh + ps1). Además `npx tsc --noEmit` → exit 0.

**Flag:** ninguna nueva; el fallback ante fallo de descubrimiento ES el comportamiento actual (degradación controlada). **Runtimes:** flujo épica-desde-brief compartido por los 3; paridad automática. En trackers no-ADO (GitLab) el resolver cae al fallback `("Feature", None)` y el provider traduce como hoy — degradación explícita, sin cambio de comportamiento. **Trabajo del operador: ninguno.**

---

### F4 (OPCIONAL) — `rev` desde la respuesta del POST; eliminar el GET extra

**Objetivo (1 frase):** usar el `rev` que la respuesta de creación del work item ya trae, y dejar el GET de `System.Rev` solo como fallback. **Valor:** cierra L7 — una llamada de red menos por autopublish y un punto de fallo menos para el baseline de edit-learning.

**Archivos:**
- MODIFICADO `backend/api/tickets.py` (`_PublishedEpic`, `_publish_epic_to_ado`, bloque de baseline en `autopublish_epic_from_run`)
- NUEVO `backend/tests/test_autopublish_rev_from_response.py`

**Cambios EXACTOS:**
1. `_PublishedEpic` (hoy `:6331-6335`): agregar campo aditivo `rev: int | None = None` (NamedTuple con default — no rompe los constructores existentes).
2. En `_publish_epic_to_ado`, en AMBOS branches (provider `:6388-6396` y ADO `:6398-6414`): capturar `_rev = wi.get("rev")` del dict de respuesta y construir `_PublishedEpic(..., rev=int(_rev) if _rev else None)`. Aplicar lo mismo en el segundo constructor de `:6870` (misma función patrón, flujo Issue).
3. En `autopublish_epic_from_run`, bloque de baseline (ancla de texto: `_wi_rev = _rev_client.get_work_item(published.ado_id, fields=["System.Rev"])`, hoy `:6737`): anteponer `if published.rev is not None: _baseline_rev = published.rev` y ejecutar el GET actual SOLO en el `else` (fallback cuando la respuesta no trajo rev — p. ej. providers que no lo exponen).

**Justificación de corrección:** entre el `create_work_item` (`:6690`) y el sellado del baseline (`:6733-6741`) el flujo de épica no ejecuta ninguna otra escritura ADO sobre ese work item (verificado leyendo el rango 2026-07-16), así que el `rev` de la respuesta de creación ES el rev vigente al sellar.

**Tests (`tests/test_autopublish_rev_from_response.py`):**
- `test_rev_de_respuesta_evita_get`: ado fake cuyo `create_work_item` devuelve `{"id": 1, "rev": 1, "fields": {...}, "_links": ...}` y cuyo `get_work_item` incrementa un contador → tras el flujo, `baseline_rev == 1` y contador `get_work_item == 0`.
- `test_sin_rev_en_respuesta_cae_al_get`: respuesta sin key `rev` → `get_work_item` llamado exactamente 1 vez (comportamiento actual preservado).

**Criterio de aceptación BINARIO:** `.venv\Scripts\python.exe -m pytest tests/test_autopublish_rev_from_response.py -q` → exit 0 (registrado en sh + ps1). **Flag:** ninguna (comportamiento equivalente + fallback). **Runtimes:** compartido; paridad automática. **Trabajo del operador: ninguno.**

---

### F5 — Smoke real: desbloquear ADO-338 / ADO-339 / ADO-340

**Objetivo (1 frase):** verificar contra el deploy vivo que la migración lista los 3 tickets bloqueados reales y que la acción humana 1-click los resuelve. **Valor:** la prueba de fuego con los datos que motivaron el plan.

**Procedimiento EXACTO (lo ejecuta el operador/orquestador sobre el deploy, DB viva en `DeployStackyAgents\data`):**
1. Desplegar el backend con F1+F2 (y F3; F4 si se hizo). Al arrancar, la migración one-shot corre sola; verificar en el log del deploy la línea `migracion markers legacy: {...}` con `migrated_pending >= 1`.
2. Abrir la página **Diagnóstico** de la UI → el `PublishLedgerPanel` muestra las ejecuciones correspondientes a ADO-338, ADO-339 y ADO-340 (status `pending`, source `migration`, stale).
3. Para cada una, el humano decide y clickea **Re-publicar** (o **Descartar** si ya no corresponde publicar).
4. Verificar el resultado en el mismo panel tras el refresco.

**Criterio de aceptación BINARIO (KPI-8):** los 3 quedan en `posted` (visibles con `ado_ids`) **o** en `failed` con `error` legible en el panel. Cero filas en limbo `pending` stale para esos 3. GET `/api/publish-ledger` lo confirma por API.

**Flag:** la existente. **Runtimes:** N/A (operación sobre el deploy). **Trabajo del operador:** SOLO la decisión 1-click por ticket — que es exactamente el human-in-the-loop que el plan garantiza, no una carga nueva (hoy el desbloqueo es imposible; con esto es un click).

---

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Ventana F1-sin-F2: si solo se desplegara F1, los markers legacy dejarían de bloquear y un retry podría re-postear algo ya publicado. | F1..F5 se despliegan JUNTOS (un solo deploy al final). Además, defensa en profundidad: `publish_from_execution` dedupea por `agent_html_publish` (`ado_publisher.py:355-363`) y por `UniqueConstraint execution_id+html_sha256` (`:164-167`). |
| `IntegrityError` dentro de `session_scope` deja la sesión sucia. | `try_acquire` captura FUERA del context manager (el `with` ya hizo rollback) y abre una sesión NUEVA para leer la fila — pseudocódigo exacto en F1; test `test_try_acquire_gana_y_duplicado_clasifica` lo cubre. |
| La migración clasifica mal un marker (posted vs pending). | Regla determinista única: existe `AgentHtmlPublish.status == "ok"` para ese `execution_id` ⇒ `posted`; si no ⇒ `pending` y lo decide un humano. Nunca se auto-postea en la migración. |
| Panel re-publicar clickeado dos veces rápido. | Botón disabled en vuelo (F2) + el propio ledger: el primer click re-adquiere (`acquired`) y el segundo `_attempt_publish` recibe `replay_*`. Exactamente 1 POST. |
| `checkout` del test toca la DB real. | Todos los tests fijan `DATABASE_URL=sqlite:///:memory:` ANTES de cualquier import de la app (patrón existente, p. ej. `test_ado_publisher_attachments.py:11`). |
| Crash nativo threads-daemon vs teardown SQLAlchemy en pytest (gotcha conocido). | Este plan NO crea threads: el sweep es on-read y el test de carrera es secuencial por diseño (§3.1). |
| El 207 confunde a un cliente HTTP estricto. | 207 es 2xx: `api.post` del frontend no lanza; el body conserva TODAS las keys previas y solo agrega `warnings`. |
| Drift de líneas por sesiones concurrentes en el mismo árbol. | Todas las ediciones se anclan por TEXTO normativo citado en cada fase; los números son referencia del 2026-07-16. Pre-flight `git status` por archivo caliente. |

---

## 7. Fuera de scope (explícito)

- **TTL auto-republicador**: NO existe ni existirá en este plan; `stale` solo se marca y lista.
- **Republicación automática** de cualquier tipo (retry en background, daemon, cron): prohibida — desbloqueo SIEMPRE humano.
- **Cambios al flujo épica-desde-brief** más allá del tipo de work item de los hijos (F3). El bypass de revisión humana de ese flujo queda exactamente como está.
- **Traducción de tipos en providers no-ADO** (GitLab): el resolver cae al fallback actual; si algún día hace falta, es otro plan.
- **Tocar `ado_write_operations`/outbox**: tabla distinta con propósito distinto; intacta.
- **RBAC/permisos en los endpoints nuevos**: Stacky es mono-operador sin auth real.
- **UI de configuración nueva**: no hay flags nuevas que configurar.

---

## 8. Advertencias para el implementador (gotchas duros, LEER ANTES DE EMPEZAR)

1. **`config.config` vs módulo `config`:** en `api/tickets.py` la instancia de flags es `config.config`; `getattr(config, FLAG)` sobre el MÓDULO devuelve siempre el default y mata el branch OFF (bit real de los planes 131 y 148). En `agent_completion_internal.py` el patrón correcto ya está escrito en `:625` (`from config import config as _cfg`) — calcarlo.
2. **`session_scope` vive en `db.py:302`** (NO en models.py). Los markers viven en `AgentExecution.metadata_json` (str JSON, `models.py:219`) con property `metadata_dict` (`models.py:260-265`). **NO existe `.metadata`** — es nombre reservado de SQLAlchemy.
3. **Sin daemons:** el sweep de este plan es una función pura on-read. Si durante la implementación alguien decide convertirlo en thread/daemon: gate OBLIGATORIO con `STACKY_TEST_MODE` (gotcha plan 146: un daemon sin gate crasheó pytest a nivel nativo).
4. **Ratchet de tests:** TODO `test_*.py` backend nuevo va registrado en `HARNESS_TEST_FILES` de `backend/scripts/run_harness_tests.sh` **Y** de `backend/scripts/run_harness_tests.ps1`, o el meta-test del ratchet cae. Son 2 archivos nuevos seguros (`test_publish_ledger.py`, `test_epic_children_type_mapping.py`) + 1 opcional (`test_autopublish_rev_from_response.py`). Verificar también que `test_publish_idempotent_guard.py` (modificado) ya esté registrado: `grep test_publish_idempotent_guard scripts/run_harness_tests.sh`.
5. **Prosa vs grep-gates:** los comentarios/docstrings del código NUEVO tienen PROHIBIDO contener literales que colisionen con los greps de verificación de este plan (p. ej. no escribir en un comentario del panel la cadena `style={` ni escribir en comentarios de `publish_ledger.py` frases que un gate futuro grepee). Gotcha recurrente (6 ocurrencias históricas): reescribir la prosa, el gate siempre gana.
6. **`DATABASE_URL` antes de los imports:** en cada test nuevo, `os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")` va ANTES de importar cualquier módulo de la app (si un import de app corre primero, el engine queda apuntando a la DB real).
7. **pytest por archivo / vitest por archivo:** la suite completa da falsos rojos por contaminación de orden en ambos lados. Comandos exactos en cada fase.
8. **No commitear, staging quirúrgico:** el orquestador commitea. `git add` SIEMPRE con paths explícitos (puede haber otra sesión viva en el mismo árbol). Nunca amend/reset/rebase/checkout.
9. **uiDebtRatchet:** el `.tsx` nuevo nace con alcance cero-deuda: 0 estilos inline; anchos dinámicos vía ref+effect imperativo si hicieran falta.

---

## 9. Orden de implementación

1. **F0** — test rojo (`test_publish_ledger.py` con sus 2 tests iniciales) + registro en sh/ps1. Verificar: 1 passed / 1 failed con `ModuleNotFoundError`.
2. **F1** — `services/publish_ledger.py` + edición de `_attempt_publish` + import en `init_db()` + actualización de los 2 tests de `test_publish_idempotent_guard.py` + tests F1. Verificar KPI-1 y KPI-2.
3. **F2** — `migrate_legacy_markers` real + enganche en `app.py` + blueprint + registro en `api/__init__.py` + harness_health + frontend (endpoints, helpers puros, panel, montaje) + tests F2. Verificar KPI-1, KPI-4, KPI-5, KPI-7.
4. **F3** — `fetch_work_item_type_names` + resolver + uso en `publish_epic_children` + 207/warnings en endpoint + frontend warnings + `test_epic_children_type_mapping.py` + registro sh/ps1. Verificar KPI-3, KPI-5, KPI-6.
5. **F4 (opcional)** — rev desde respuesta + `test_autopublish_rev_from_response.py` + registro sh/ps1.
6. **F5** — smoke real sobre el deploy (ADO-338/339/340). Verificar KPI-8.

---

## 10. Definición de Hecho (DoD) global

- [ ] KPI-1..KPI-7 verdes con los comandos exactos de §1 (KPI-3/KPI-6 incluyen F3; F4 solo si se implementó).
- [ ] `_attempt_publish` ya no llama a `_r13_check_publish_guard` ni a `_r13_write_publish_intent` (verificación: `grep -n "_r13_check_publish_guard\|_r13_write_publish_intent" services/agent_completion_internal.py` muestra solo las definiciones y ningún call-site dentro de `_attempt_publish`).
- [ ] `services/harness_health.py` ya no escanea `metadata_json` buscando `publish_intent` (verificación: `grep -c "publish_intent" services/harness_health.py` → 0).
- [ ] Ningún flag nuevo: `git diff -- backend/harness_flags.py` vacío.
- [ ] Los 2 (o 3) archivos de test nuevos registrados en `run_harness_tests.sh` y `run_harness_tests.ps1`.
- [ ] `git status` final limpio de archivos no relacionados; staging por paths explícitos; SIN commit del implementador.
- [ ] F5 ejecutada sobre el deploy: ADO-338/339/340 en `posted` o `failed`-visible. Cero limbo.
