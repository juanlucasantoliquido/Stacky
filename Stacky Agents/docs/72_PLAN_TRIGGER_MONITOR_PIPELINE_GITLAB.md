# Plan 72 — Trigger y monitoreo de pipelines CI (HITL innegociable)

> **Estado:** PROPUESTO v3 (2ª ronda de juez adversarial). Veredicto v2 = RECHAZADO (1 bloqueante de registro de blueprint + 4 importantes); v3 los resuelve.
> **Pre-requisito:** Plan 71 (sub-puerto `CIProvider` con `infer_item_pipeline` + `monitor_pipeline` declarado + fábrica `get_ci_provider` + `ItemRef` + `CI_PORT_METHODS` congelado). — **DEBE estar implementado primero** (verificado 2026-06-27: NINGUNO de esos símbolos existe aún en `services/`; este plan no se puede empezar hasta que Plan 71 esté verde).
> **Roadmap:** Tercer eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer agnóstico → **trigger CI** → creador pipelines → migrador → deep links → eval).
> **Versión doc:** v3 (2026-06-27).
> **Dependencias:** Plan 71 (duro); Plan 70 (transitivo vía 71). No depende de 73/74/75/76.

> **CHANGELOG v2 → v3 (2ª crítica adversarial; verificada contra código real):**
> - **[C1 BLOQUEANTE — registro de blueprint mal ubicado + doble `/api` prefix → rutas 404]** v2 ordenaba "registrar `ci_bp` en `app.py` incondicionalmente (como `api_bp` en `app.py:187`)" con `ci_bp = Blueprint("ci", __name__, url_prefix="/api/ci")`. **Verificado:** `app.py:187` registra SOLO `api_bp`; TODOS los sub-blueprints de API (incluido `harness_flags`, el "patrón hermano" que el propio plan cita) se registran en **`api/__init__.py:44-82`** sobre `api_bp`, y `api_bp = Blueprint("api", __name__, url_prefix="/api")` (`api/__init__.py:43`). Registrar `ci_bp` con `url_prefix="/api/ci"` bajo `api_bp` produce **`/api/api/ci/...`** (doble prefijo) → todos los endpoints, tests y llamadas del frontend dan 404. Instrucción además contradictoria (dice "en app.py como api_bp" pero referencia a `harness_flags`, que NO está en app.py). **Fix:** `ci_bp = Blueprint("ci", __name__, url_prefix="/ci")` y registrarlo en **`api/__init__.py`** vía `api_bp.register_blueprint(ci_bp)` (final = `/api/ci/...`). Eliminada toda mención a registrar en `app.py`. Ver F2 + **[ADICIÓN ARQUITECTO v3]** (test centinela de rutas).
> - **[C2 IMPORTANTE — endpoint de flags mal citado: `/api/harness/flags` no existe]** v2 citaba `GET /api/harness/flags` en 6 lugares. **Verificado (`api/harness_flags.py:3,71`):** la ruta real es **`/api/harness-flags`** (con guion; `@bp.get("/harness-flags")` sobre `api_bp`). Un modelo menor codearía `fetch('/api/harness/flags')` → 404 → el botón F4 quedaría siempre deshabilitado. **Fix:** reemplazado por `/api/harness-flags` en C6, F4, glosario, DoD y notas.
> - **[C3 IMPORTANTE — F1 rompe el test congelado del Plan 71]** Plan 71 congela `CI_PORT_METHODS == ("infer_item_pipeline","monitor_pipeline")` con `test_ci_port_methods_is_frozen` (anti-drift, `71_PLAN...md:145,163`). F1 agrega `trigger_pipeline` (3er método) → ese test se pone **ROJO**. v2 no instruía actualizarlo. **Fix:** F1 incluye paso explícito: actualizar `test_ci_port_methods_is_frozen` a la 3-tupla con `trigger_pipeline` (mismo commit que extiende el Protocol). Sin esto, F1 deja el suite rojo.
> - **[C4 IMPORTANTE — F5 cap 429 referencia un store de polls activos inexistente (fantasma, igual que el viejo C5)]** F5 caso 5 afirmaba "429 si hay >5 polls activos" sin definir dónde se cuentan. **Fix:** store explícito `_ACTIVE_POLLS: dict[str,int]` module-level en `api/ci.py` con incremento al entrar / decremento en `finally`, cap `_MAX_ACTIVE_POLLS_PER_PIPELINE = 5`, y test determinista (pre-sembrar el contador).
> - **[C5 IMPORTANTE — [ADICIÓN ARQUITECTO] preview sin test backend + bug en el snippet literal]** El endpoint `trigger-preview` y `last_pipeline_for_ref` eran código backend nuevo SIN test nombrado (sólo F4 frontend, que puede no tener vitest) → viola el propio TDD del plan. Además el snippet llamaba `should_trigger(...)` **dos veces** con `sha=""`. **Fix:** snippet corregido a UNA llamada (`fire, existing = should_trigger(...)`); nuevo archivo `backend/tests/test_plan72_preview_endpoint.py` (4 casos) que testea el preview y `last_pipeline_for_ref` en ambos adapters; registrado en el ratchet.
> - **[C6 MENOR]** `_RECENT_TRIGGERS` no purga; se documenta poda perezosa por ventana (sin tabla nueva). `provider.name` se afirma ∈ `{"gitlab","azure_devops"}` (clave de `REQUIRED_SCOPES` y `ItemRef.tracker_type`) con un caso de test.
> - **[ADICIÓN ARQUITECTO v3 — test centinela de rutas reales contra `create_app()`]** Nuevo `backend/tests/test_plan72_routes_registered.py`: bootea la app REAL (`create_app()`) y afirma que `/api/ci/<project>/trigger`, `/api/ci/<project>/trigger-preview` y `/api/ci/<project>/pipeline/<pipeline_id>` existen en `app.url_map`. Hace IMPOSIBLE el falso-verde de la clase C1 (tests verdes sobre una app armada a mano mientras producción sirve la ruta con doble prefijo). Cero trabajo al operador, read-only, neutral a los 3 runtimes. Detalle en F2.

> **CHANGELOG v1 → v2 (1ª crítica adversarial; conservado para trazabilidad):**
> - **[C1' BLOQUEANTE]** Contrato `_client._request` mal citado (`body, status` + `if status==403`); real devuelve `(body, headers)` y ya lanza `TrackerApiError`. Fix: `body, _ = ...` + propagar.
> - **[C2' BLOQUEANTE]** Gating del blueprint en startup rompía el toggle por UI. Fix v2: registrar siempre + guard per-request (v3 corrige DÓNDE se registra, ver C1 arriba).
> - **[C3' BLOQUEANTE]** Gate de scope duro bloqueaba PAT con scope no introspectable. Fix: best-effort no bloqueante.
> - **[C4'/C5'/C6' IMPORTANTES]** try/except TrackerApiError; store de idempotencia `_RECENT_TRIGGERS`; reuso de endpoint de flags existente.
> - **[C7'/C8' MENORES]** glosario de los dos `trigger_pipeline`; `normalize_ref.kind` como hint.
> - **[ADICIÓN ARQUITECTO v2]** preview read-only HITL (`trigger-preview`).

---

## 1. Objetivo y KPI

Que Stacky pueda **disparar** (trigger) y **monitorear** pipelines CI desde la UI, con confirmación explícita del operador (HITL), sobre cualquier `CIProvider` (ADO o GitLab). Hoy `gitlab_provider.py:432 fetch_pipelines`/`:458 infer_pipeline` son solo-lectura; **no existe** `trigger_pipeline` en ningún adapter.

**KPI global (DoD):** el operador puede, desde la UI de Stacky, disparar un pipeline sobre un `ref` (branch/SHA) de un proyecto y ver su status, **sin salir de Stacky**, con `STACKY_PIPELINE_TRIGGER_ENABLED=true` y `confirm=True` explícito. Sin `confirm=True`, el endpoint rechaza con 400. Un PAT con scope `api` real dispara OK; un PAT sin `api` recibe el 403 real de GitLab (no un falso 400 preventivo cuando el scope no es verificable). Las rutas viven en `/api/ci/...` (verificable por el test centinela, [ADICIÓN ARQUITECTO v3]).

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy:

- `services/gitlab_provider.py:432 fetch_pipelines(ref)` lista pipelines vía `self._client._request_paginated("/projects/{proj}/pipelines", ...)`; `:458 infer_pipeline(ref)` infiere; **no hay** `trigger_pipeline` ni `retry_pipeline` ni `poll_pipeline` en el adapter GitLab.
- `services/gitlab_client.py:107 _request(method, path, *, params, json_body, files, _retry)` devuelve `(body, response_headers)` (firma anotada `-> tuple[object, dict]`, L116) y **lanza `TrackerApiError(status, msg, kind=...)`** ante no-2xx (L153-159). `:98 _project_path()` URL-encodea el path. `TrackerApiError` vive en `tracker_provider.py:48` con firma `(status, message, *, kind="unknown")`.
- **Sub-puerto `CIProvider` aún NO existe** (`get_ci_provider`/`ItemRef`/`CIProvider`/`monitor_pipeline`/`CI_PORT_METHODS` no aparecen en `services/` al 2026-06-27): los provee el Plan 71. Este plan **no arranca** hasta que 71 esté verde.
- ADO no exponía un trigger cómodo desde el backend de Stacky (requería REST de Azure Pipelines con scopes separados); GitLab lo permite con `POST /projects/:id/pipeline` scope `api`.
- Hoy, para correr CI de un ítem GitLab desde Stacky, el operador debe ir a la web de GitLab: fricción que rompe el centauro.
- Plan 71 deja el sub-puerto `CIProvider` listo con `monitor_pipeline` declarado (`NotImplementedError` en adapters, con comentario "lo implementa Plan 72 F1"); este plan lo **implementa** y **extiende** con `trigger_pipeline`.

---

## 3. Principios y guardarraíles (heredados + HITL absoluto)

- **HITL INNEGOCIABLE (riel absoluto de 72):** el trigger exige `confirm=True` explícito del operador. **Nunca auto-disparar** desde un agente o un job en background. El endpoint valida `confirm is True`; el botón UI muestra modal con `ref` + `project` + preview + warning antes de setear `confirm`.
- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API/UI; NO toca prompts ni runtime del agente. El trigger es **operador-driven** (UI/API), nunca agente-driven → no introduce autonomía en ningún runtime.
- **Cero trabajo extra al operador:** flag opt-in `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI"), leída **per-request** (mismo patrón y mismo mecanismo de refresh que la flag `STACKY_PIPELINE_PROVIDER_ENABLED` del Plan 71 — este plan NO introduce un mecanismo de refresh nuevo). Flag OFF = endpoint responde 404 vía guard per-request.
- **Mono-operador sin auth:** PAT GitLab en `client_profile`; **requiere scope `api`** para disparar. Validación de scope **best-effort, no bloqueante cuando no es verificable** (ver F0/F2, C3'). Para ADO, el adapter ADO lanza `NotImplementedError("trigger_pipeline ADO fuera de scope v1")` (ver F3). No hay RBAC ni roles (`current_user` es header sin validar; sería teatro).
- **No degradar / backward-compatible:** flag OFF → guard 404; ningún comportamiento existente cambia. El blueprint se registra siempre en `api/__init__.py` junto a los demás (sin tocar el orden ni los prefijos de los existentes).
- **TDD + funciones puras + ratchet + no falsos verdes.** La idempotencia, la normalización de `ref` y la validación de `confirm`/scopes son **funciones puras** testeables sin GitLab real. Las RUTAS reales se verifican contra `create_app()` (centinela, [ADICIÓN ARQUITECTO v3]) para que ningún path mal registrado pase verde.

---

## 4. Fases

### F0 — Validación de PAT scope (best-effort) + contrato de `ref` + idempotencia

**Objetivo:** definir y testear las 3 funciones puras que gobiernan el trigger antes de tocar la red: validación de scopes (no bloqueante si no verificable), normalización de `ref`, decisión de idempotencia.

**Archivos exactos F0:**
- `services/ci_trigger_rules.py` — **archivo nuevo** (3 funciones puras).
- `services/gitlab_provider.py` — referencia para scopes requeridos (no se modifica en F0).

**Símbolos exactos F0 (funciones PURAS, sin I/O):**

```python
# services/ci_trigger_rules.py
REQUIRED_SCOPES = {"gitlab": {"api"}, "azure_devops": {"vso.build_execute"}}

def validate_trigger_credentials(tracker_type: str, scopes: set[str] | None) -> tuple[bool, str]:
    """Devuelve (ok, mensaje). Best-effort y NO bloqueante cuando los scopes no son
    verificables (C3'): si scopes is None o set() -> (True, "scopes no verificables; se
    valida en runtime con el 403 real de GitLab"). Sólo bloquea con scopes CONOCIDOS y
    faltantes."""
    if not scopes:                      # None o vacío == no verificable -> no bloquear
        return True, "scopes no verificables; se valida en runtime"
    required = REQUIRED_SCOPES.get(tracker_type, set())
    missing = required - set(scopes)
    if missing:
        return False, f"PAT falta scope(s): {','.join(sorted(missing))} (requerido para trigger en {tracker_type})"
    return True, "ok"

def normalize_ref(ref: str) -> tuple[str, str]:
    """Normaliza ref a (kind, value). kind ∈ {"branch","sha","tag"} es un HINT de
    telemetría (C8'): GitLab resuelve el ref por sí mismo; el caller pasa SIEMPRE value,
    nunca ramifica comportamiento por kind.
    SHA: ^[0-9a-f]{7,40}$; tag: refs/tags/X; resto branch.
    Lanza ValueError si ref vacío o contiene caracteres prohibidos (espacios, '..', control)."""
    ...

def should_trigger(ref: str, sha: str, recent_triggers: list[dict], window_seconds: int = 60) -> tuple[bool, str | None]:
    """Idempotencia: si existe un trigger reciente para (ref, sha) dentro de la ventana,
    devuelve (False, existing_pipeline_id). Si no, (True, None). PURA.
    'recent' es una lista de dicts {"ref","sha","pipeline_id","ts"} (ts epoch segundos)."""
    ...
```

**Tests F0 (TDD primero):**
- Archivo: `backend/tests/test_plan72_trigger_rules.py`.
- Casos:
  1. `validate_trigger_credentials("gitlab", {"api"})` → `(True, "ok")`.
  2. `validate_trigger_credentials("gitlab", {"read_api"})` → `(False, msg con "api")`.
  3. `validate_trigger_credentials("azure_devops", {"vso.build_execute"})` → `(True, "ok")`.
  4. **[C3']** `validate_trigger_credentials("gitlab", None)` → `(True, ...)`; `validate_trigger_credentials("gitlab", set())` → `(True, ...)`. (No bloquear cuando no es verificable.)
  5. `normalize_ref("develop")` → `("branch", "develop")`.
  6. `normalize_ref("abc1234")` (7 hex) → `("sha", "abc1234")`; `"zzzzzzz"` → `("branch", "zzzzzzz")` (no es hex).
  7. `normalize_ref("")` → lanza `ValueError`; `normalize_ref("a b")` → lanza `ValueError`.
  8. `should_trigger("develop", "abc123", [], 60)` → `(True, None)`.
  9. `should_trigger("develop", "abc123", [{"ref":"develop","sha":"abc123","pipeline_id":"99","ts":now}], 60)` → `(False, "99")`.
  10. `should_trigger` con trigger fuera de ventana (>60s) → `(True, None)`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_trigger_rules.py -q`.

**Criterio binario F0:** los 10 casos pasan; las 3 funciones son puras (sin I/O, sin import requests).

**Impacto por runtime:** ninguno (archivo nuevo inerte).

**Flag F0:** ninguna.

**Trabajo del operador F0:** ninguno. (Para usar el trigger después: PAT GitLab debe tener scope `api`; si el scope no es verificable, el trigger se intenta y GitLab responde el 403 real si falta — documentado en la UI.)

---

### F1 — Extensión del sub-puerto `CIProvider` + implementación `monitor_pipeline` + actualizar freeze test del Plan 71

**Objetivo:** extender el `Protocol` con `trigger_pipeline`, implementar `monitor_pipeline` en ambos adapters, y **actualizar el `test_ci_port_methods_is_frozen` del Plan 71** (que se rompe al sumar el 3er método, C3). Los métodos client-level usan el contrato REAL de `_client._request` (C1').

**Archivos exactos F1:**
- `services/ci_provider.py` — agregar `trigger_pipeline` al `Protocol`; actualizar `CI_PORT_METHODS` a la 3-tupla.
- `services/ado_ci_provider.py` — implementar `monitor_pipeline`; `trigger_pipeline` lanza `NotImplementedError` (ADO fuera de scope v1).
- `services/gitlab_ci_provider.py` — implementar `monitor_pipeline`; `trigger_pipeline` se implementa en F2.
- `services/gitlab_provider.py` — agregar `trigger_pipeline(ref)` y `poll_pipeline(pipeline_id)` (POST + GET sobre `/projects/:id/pipeline[s]`).
- `backend/tests/test_plan71_*ci_provider*.py` (el archivo del Plan 71 que contiene `test_ci_port_methods_is_frozen`) — **actualizar** la aserción a la 3-tupla. **[C3]**

**Símbolos exactos F1 (extensión del Protocol, FIJADA):**

```python
# services/ci_provider.py — extensión
@runtime_checkable
class CIProvider(Protocol):
    name: str
    def infer_item_pipeline(self, item_ref: ItemRef) -> ItemPipelineResult: ...
    def monitor_pipeline(self, pipeline_id: str) -> dict: ...
    def trigger_pipeline(self, item_ref: ItemRef, ref: str) -> dict: ...   # NUEVO Plan 72

CI_PORT_METHODS = ("infer_item_pipeline", "monitor_pipeline", "trigger_pipeline")
```

```python
# services/gitlab_provider.py — nuevos métodos sobre el _client existente.
# CONTRATO REAL (verificado gitlab_client.py:107-166): _request devuelve (body, response_headers)
# y YA LANZA TrackerApiError(status, msg, kind=...) ante no-2xx. NO se compara status a mano (C1').
def trigger_pipeline(self, ref: str) -> dict:
    """POST /projects/:id/pipeline — dispara pipeline sobre el ref. Requiere scope api.
    Si GitLab responde 403, _request lanza TrackerApiError(403, ..., kind='forbidden');
    NO se captura aquí: se deja propagar para que el endpoint lo mapee a 403 (C1'/C4')."""
    proj_path = self._client._project_path()
    body, _ = self._client._request(
        "POST", f"/projects/{proj_path}/pipeline",
        json_body={"ref": ref},
    )
    return {"id": str(body.get("id") or ""), "status": body.get("status") or "",
            "ref": body.get("ref") or ref, "sha": body.get("sha") or "",
            "web_url": body.get("web_url") or ""}

def poll_pipeline(self, pipeline_id: str) -> dict:
    """GET /projects/:id/pipelines/:pipeline_id — estado actual."""
    proj_path = self._client._project_path()
    body, _ = self._client._request("GET", f"/projects/{proj_path}/pipelines/{pipeline_id}")
    return {"id": str(body.get("id") or ""), "status": body.get("status") or "",
            "ref": body.get("ref") or "", "sha": body.get("sha") or "",
            "web_url": body.get("web_url") or ""}
```

**Implementación `monitor_pipeline` en adapters (F1):**
- `GitLabCIProvider.monitor_pipeline(pipeline_id)` → delega a `self._delegate.poll_pipeline(pipeline_id)`.
- `AdoCIProvider.monitor_pipeline(pipeline_id)` → lanza `NotImplementedError("monitor_pipeline ADO fuera de scope v1")`.

**Tests F1:**
- Archivo: `backend/tests/test_plan72_ci_provider_trigger_port.py`.
- Casos:
  1. `CIProvider` (con los 3 métodos) pasa `isinstance(stub, CIProvider)`; stub sin `trigger_pipeline` NO pasa.
  2. `GitLabCIProvider.monitor_pipeline("99")` llama a `delegate.poll_pipeline("99")` **[Patrón mock: assert_called_once_with("99")]**.
  3. `AdoCIProvider.monitor_pipeline("99")` lanza `NotImplementedError`.
  4. `GitLabTrackerProvider.trigger_pipeline("develop")` construye POST con `json_body={"ref":"develop"}` **[Patrón mock sobre `self._client._request`, que devuelve `({"id":1,"status":"created","ref":"develop"}, {})`]**; el método devuelve `id="1"`, `status="created"`.
  5. **[C1']** Si `self._client._request` **lanza** `TrackerApiError(403, "no api scope", kind="forbidden")`, `trigger_pipeline` **propaga** ese `TrackerApiError` (status=403, kind="forbidden") sin capturarlo ni fabricarlo. (Simula el contrato real del client.)
  6. **[C3]** `CI_PORT_METHODS == ("infer_item_pipeline","monitor_pipeline","trigger_pipeline")` y el `test_ci_port_methods_is_frozen` del Plan 71 (actualizado) pasa con la 3-tupla. (Afirma que el contrato compartido quedó consistente, no roto.)
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_ci_provider_trigger_port.py -q`.
- Comando de no-regresión del Plan 71: correr también el archivo de tests del Plan 71 que contiene `test_ci_port_methods_is_frozen` y confirmarlo VERDE tras el update.

**Criterio binario F1:** los 6 casos pasan; `CI_PORT_METHODS` tiene 3 métodos; `test_ci_port_methods_is_frozen` del Plan 71 VERDE (actualizado, no eliminado); ningún método compara el 2º valor de `_request` a un status (C1').

**Impacto por runtime:** ninguno (sin callers UI/API aún).

**Trabajo del operador F1:** ninguno.

---

### F2 — Adapter `trigger_pipeline` en `GitLabCIProvider` + endpoint API con HITL + idempotencia + registro correcto del blueprint

**Objetivo:** cablear el trigger de GitLab al endpoint `POST /api/ci/<project>/trigger` con HITL (`confirm=True` obligatorio), idempotencia por `(ref, sha)`, validación de scopes best-effort (C3') y mapeo de `TrackerApiError` (C4'). El blueprint se registra SIEMPRE en `api/__init__.py` con `url_prefix="/ci"` (final = `/api/ci/...`, C1); la flag se evalúa per-request (C2').

**Archivos exactos F2:**
- `services/gitlab_ci_provider.py` — implementar `trigger_pipeline(item_ref, ref)` (delega a `delegate.trigger_pipeline(ref)`).
- `api/ci.py` — **blueprint nuevo** `ci_bp = Blueprint("ci", __name__, url_prefix="/ci")` con endpoint `POST /<project>/trigger` + store de idempotencia module-level (C5').
- `api/__init__.py` — **agregar el import** `from .ci import bp as ci_bp` (junto a los demás, L3-41) y **registrar** `api_bp.register_blueprint(ci_bp)` (junto a los demás, L44-82). **NO** tocar `app.py`. **[C1 — verificado: así se registran TODOS los sub-blueprints de API, no en app.py]**.
- `config.py` — `STACKY_PIPELINE_TRIGGER_ENABLED: bool = False`.
- `harness_defaults.env` — `STACKY_PIPELINE_TRIGGER_ENABLED=false`.

> **[C1 — Por qué NO `url_prefix="/api/ci"` y NO en app.py]:** `api/__init__.py:43` define `api_bp = Blueprint("api", __name__, url_prefix="/api")` y registra todos los sub-blueprints sobre él (L44-82). Un sub-blueprint con `url_prefix="/api/ci"` daría la ruta final `/api` + `/api/ci` = **`/api/api/ci`** (doble prefijo → 404). Por eso `ci_bp` lleva `url_prefix="/ci"` y se registra en `api_bp`, igual que `harness_flags` (`api/__init__.py:70`, sin prefijo propio, ruta `/harness-flags` → `/api/harness-flags`). El test centinela ([ADICIÓN ARQUITECTO v3]) verifica la ruta final real.

**Símbolos exactos F2 (store de idempotencia + endpoint con HITL absoluto):**

```python
# api/ci.py
from services.tracker_provider import TrackerApiError
from services.ci_provider import get_ci_provider, ItemRef
from services.ci_trigger_rules import normalize_ref, validate_trigger_credentials, should_trigger
import time

ci_bp = Blueprint("ci", __name__, url_prefix="/ci")   # final = /api/ci (registrado en api/__init__.py, C1)

# C5' — store de idempotencia in-process. Mono-operador single-process (memoria
# stacky-no-auth-substrate): un dict module-level es suficiente y no requiere DB.
# clave: (tracker_type, ref) -> {"ref","sha","pipeline_id","ts"}. C6: una sola entrada
# por (tracker_type, ref) → crecimiento acotado al nº de refs distintos; la ventana
# de should_trigger descarta las viejas, no hace falta tabla.
_RECENT_TRIGGERS: dict[tuple[str, str], dict] = {}

# C4 — contador de polls activos por pipeline (cap anti-N+1 sobre GitLab, F5).
_ACTIVE_POLLS: dict[str, int] = {}
_MAX_ACTIVE_POLLS_PER_PIPELINE = 5

def _recent_triggers(tracker_type: str, ref: str) -> list[dict]:
    e = _RECENT_TRIGGERS.get((tracker_type, ref))
    return [e] if e else []

def _record_trigger(tracker_type: str, ref: str, sha: str, pipeline_id: str) -> None:
    _RECENT_TRIGGERS[(tracker_type, ref)] = {"ref": ref, "sha": sha,
                                             "pipeline_id": pipeline_id, "ts": time.time()}

def _read_pat_scopes(provider) -> set[str] | None:
    """Best-effort (C3'): lee scopes del client_profile si están; si no son verificables,
    devuelve None (NO set vacío forzado a bloquear)."""
    ...   # retorna None cuando no hay metadata de scopes -> validate no bloquea

@ci_bp.post("/<project>/trigger")
def trigger_pipeline_route(project: str):
    if not config.STACKY_PIPELINE_TRIGGER_ENABLED:
        abort(404)   # guard per-request: flag OFF = 404 (C2'). El blueprint SIEMPRE está registrado.
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400   # RIEL ABSOLUTO
    try:
        _, ref_value = normalize_ref(body.get("ref") or "")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    provider = get_ci_provider(project)
    scopes = _read_pat_scopes(provider)                       # None si no verificable (C3')
    ok, msg = validate_trigger_credentials(provider.name, scopes)
    if not ok:
        return jsonify({"error": msg}), 400                   # sólo si scope CONOCIDO y faltante

    recent = _recent_triggers(provider.name, ref_value)
    fire, existing = should_trigger(ref_value, body.get("sha", ""), recent, window_seconds=60)
    if not fire:
        return jsonify({"pipeline_id": existing, "message": "idempotency: pipeline reciente reusado", "status": "reused"})

    item_ref = ItemRef(item_id=str(body.get("item_id", "")), tracker_type=provider.name, ref=ref_value)
    try:
        result = provider.trigger_pipeline(item_ref, ref_value)
    except TrackerApiError as e:                              # C4' — 403 real de GitLab, etc.
        return jsonify({"error": str(e), "kind": e.kind}), e.status
    except NotImplementedError as e:                          # ADO (F3)
        return jsonify({"error": str(e)}), 501
    _record_trigger(provider.name, ref_value, result.get("sha", ""), result["id"])
    return jsonify(result)
```

**Tests F2 (TDD, HITL crítico):**
- Archivo: `backend/tests/test_plan72_trigger_endpoint.py`.
- Casos:
  1. Flag OFF → `POST /api/ci/<project>/trigger` retorna **404** (guard per-request; blueprint registrado).
  2. Flag ON + body sin `confirm` → **400** con `"confirm=True requerido"`. **[RIEL ABSOLUTO — test VP-01]**
  3. Flag ON + `confirm=True` + `ref="develop"` + scopes válidos (o None) + sin trigger reciente → llama `provider.trigger_pipeline` **[Patrón mock: assert_called_once]**; response 200 con `pipeline_id`.
  4. Flag ON + scopes **conocidos** inválidos (`{"read_api"}` sin `api`) → **400** con mensaje que incluye `"api"`.
  5. **[C3']** Flag ON + `_read_pat_scopes` retorna `None` (no verificable) → NO bloquea: llama `provider.trigger_pipeline` (no 400 preventivo).
  6. Flag ON + `ref` vacío → 400 (ValueError → 400).
  7. Idempotencia: segundo trigger con mismo `(ref, sha)` en ventana → response 200 `"status":"reused"`, NO llama `provider.trigger_pipeline` **[mock: assert_not_called en 2da]**.
  8. **[C4']** Flag ON + provider lanza `TrackerApiError(403, ..., kind="forbidden")` → response **403** con `kind`.
  9. **[C5']** `_record_trigger("gitlab","develop","sha1","42")` luego `_recent_triggers("gitlab","develop")` retorna 1 entrada con `pipeline_id="42"`.
  10. **[C6]** `provider.name` usado como clave es exactamente `"gitlab"` (o `"azure_devops"`): un trigger GitLab con `confirm=True` construye `ItemRef(tracker_type="gitlab", ...)` (afirmar el valor pasado al mock de `trigger_pipeline`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_trigger_endpoint.py -q`.

**[ADICIÓN ARQUITECTO v3] — Test centinela de rutas reales:**
- Archivo: `backend/tests/test_plan72_routes_registered.py`.
- Caso único: bootea la app REAL y afirma las rutas finales exactas.

```python
def test_ci_routes_registered_under_api_ci():
    from app import create_app
    app = create_app()
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert "/api/ci/<project>/trigger" in rules          # C1 — no /api/api/ci
    assert "/api/ci/<project>/trigger-preview" in rules
    assert "/api/ci/<project>/pipeline/<pipeline_id>" in rules
```

- Justificación: hace IMPOSIBLE el falso-verde de la clase C1 (un test sobre una app armada a mano podría pasar mientras producción sirve `/api/api/ci`). Read-only, cero trabajo al operador, neutral a los 3 runtimes. Si `create_app()` requiere setup (init_db), reusar el fixture de app de los tests existentes de `api/` (p.ej. el patrón de `test_*_endpoint.py` ya presentes).

**Criterio binario F2:** los 10 casos de `test_plan72_trigger_endpoint.py` pasan + el test centinela pasa (rutas en `/api/ci/...`, no `/api/api/ci/...`). **Caso 2 es el gate de significancia del HITL** — sin él, el trigger sería autónomo.

**Impacto por runtime:** ninguno (capa API/UI).

**Flag F2:** `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**, `env_only=False` (UI HarnessFlagsPanel, categoría "Pipelines / CI"), leída per-request.

**Trabajo del operador F2:** ninguno (default OFF). Para usar: prender flag + PAT con scope `api` + clic explícito en modal.

---

### F3 — `AdoCIProvider.trigger_pipeline` (fuera de scope v1, declaración explícita)

**Objetivo:** declarar `AdoCIProvider.trigger_pipeline` como `NotImplementedError` con mensaje accionable. ADO trigger requiere REST de Azure Pipelines con scopes separados y no aporta valor sobre el flujo ADO existente (los pipelines ADO se disparan por CI push, no por API cómoda).

**Archivos exactos F3:**
- `services/ado_ci_provider.py` — `trigger_pipeline(self, item_ref, ref)` lanza `NotImplementedError("trigger_pipeline ADO fuera de scope v1 — usar push o Azure Pipelines REST directo")`.

**Tests F3:**
- Archivo: `backend/tests/test_plan72_ado_trigger_not_implemented.py`.
- Casos:
  1. `AdoCIProvider().trigger_pipeline(ItemRef(...), "main")` lanza `NotImplementedError` con mensaje que incluye `"v1"`.
  2. El endpoint `POST /api/ci/<proj-ado>/trigger` con `confirm=True` captura el `NotImplementedError` → response **501** con mensaje accionable (C4': el endpoint ya tiene `except NotImplementedError → 501`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_ado_trigger_not_implemented.py -q`.

**Criterio binario F3:** los 2 casos pasan; ADO no se rompe (flag OFF = 404; flag ON + ADO = 501 claro).

**Trabajo del operador F3:** ninguno.

---

### F4 — UI: botón "Disparar pipeline" con modal HITL informado + preview backend testeado

**Objetivo:** card del ítem con botón que abre modal de confirmación con **preview informado** (`ref` resuelto + último pipeline existente + aviso de idempotencia + warning "Esto dispara un pipeline real en GitLab") y, al confirmar, llama al endpoint con `confirm=True`.

**Archivos exactos F4:**
- `frontend/src/components/PipelineTriggerCard.tsx` — **nuevo**.
- `frontend/src/pages/DiagnosticsPage.tsx` (o donde se monten las cards de pipeline) — integrar la card.
- `frontend/src/api.ts` (o equivalente) — `triggerPipeline(project, ref, itemId, confirm)` → `POST /api/ci/<project>/trigger`; `triggerPreview(project, ref)` → `GET /api/ci/<project>/trigger-preview?ref=`.
- `api/ci.py` — endpoint read-only `GET /<project>/trigger-preview` (ver [ADICIÓN ARQUITECTO v2], corregido en v3 por C5) + helper `last_pipeline_for_ref` en ambos adapters.

**[ADICIÓN ARQUITECTO v2 / corregido C5] — Preview HITL informado (read-only, reusa `fetch_pipelines`):**

```python
# api/ci.py — read-only; mismo guard per-request de flag (C2'). NO dispara nada.
@ci_bp.get("/<project>/trigger-preview")
def trigger_preview_route(project: str):
    if not config.STACKY_PIPELINE_TRIGGER_ENABLED:
        abort(404)
    ref = request.args.get("ref") or ""
    try:
        kind, ref_value = normalize_ref(ref)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    provider = get_ci_provider(project)
    # Reusa fetch_pipelines (Plan 71, gitlab_provider.py:432) para mostrar el último pipeline del ref.
    last = provider.last_pipeline_for_ref(ref_value)   # thin read-only sobre fetch_pipelines(ref)
    last_sha = (last or {}).get("sha", "")
    recent = _recent_triggers(provider.name, ref_value)
    # C5 — UNA sola llamada a should_trigger (antes se llamaba 2 veces con sha="").
    fire, existing = should_trigger(ref_value, last_sha, recent, window_seconds=60)
    return jsonify({"kind": kind, "ref": ref_value, "last_pipeline": last,
                    "would_reuse": (not fire), "existing_pipeline_id": existing})
```

`GitLabCIProvider.last_pipeline_for_ref(ref)` y `AdoCIProvider.last_pipeline_for_ref(ref)` son **read-only**; GitLab reusa `fetch_pipelines(ref)[0]` si la lista no está vacía, si no `None`; ADO devuelve `None` (sin preview ADO en v1). Justificación: amplifica el consentimiento HITL (el operador confirma viendo el último pipeline y si se reusaría), es solo-lectura (cero riesgo de autonomía), reusa lo existente, cero trabajo extra (invisible hasta abrir el modal).

**Tests backend del preview (C5 — TDD del backend nuevo, NO sólo frontend):**
- Archivo: `backend/tests/test_plan72_preview_endpoint.py`.
- Casos:
  1. Flag OFF → `GET /api/ci/<project>/trigger-preview?ref=develop` → **404**.
  2. Flag ON + `ref=develop`, provider GitLab con `last_pipeline_for_ref` mockeado → `{"id":"7",...}` → response 200 con `kind="branch"`, `ref="develop"`, `last_pipeline.id=="7"`.
  3. **[C5]** Flag ON + existe trigger reciente para `(develop, sha-de-last)` → `would_reuse=True`, `existing_pipeline_id` no nulo (afirma que `should_trigger` se llama UNA vez con el `sha` del último pipeline, no `""`).
  4. `GitLabCIProvider.last_pipeline_for_ref("develop")` con `fetch_pipelines` mockeado a `[]` → `None`; con `[{"id":"7"}]` → `{"id":"7"}`. `AdoCIProvider.last_pipeline_for_ref(...)` → `None`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_preview_endpoint.py -q`.

**Símbolos exactos F4 (frontend):**
- `<PipelineTriggerCard project itemId ref />` — al montar lee el estado de la flag desde el endpoint **existente** `GET /api/harness-flags` (`api/harness_flags.py:71`, ruta real con guion, consumido ya por HarnessFlagsPanel) y deshabilita el botón si la flag está OFF (con tooltip). **No** se inventa `GET /api/ci/flags` ni se usa `/api/harness/flags` (que no existe, C2/C6').
- Click botón → `triggerPreview` y abre modal con `ref` resuelto + último pipeline + texto `"Vas a disparar un pipeline en <project> sobre <ref>. Confirmar."`.
- El modal setea `confirm: true` SÓLO al clic explícito en "Disparar".

**Tests F4 (frontend):**
- Archivo: `frontend/src/components/__tests__/PipelineTriggerCard.test.tsx` (vitest si está disponible; si no, test manual documentado — ver memoria `stacky-backend-dev-test-env`: vitest puede no estar instalado).
- Casos:
  1. Flag OFF (según `GET /api/harness-flags`) → botón deshabilitado con tooltip.
  2. Click botón → llama `triggerPreview` y abre modal con `ref` y `project` y el `last_pipeline` del preview.
  3. Click "Disparar" en modal → llama `triggerPipeline(..., confirm=true)`; NO se llama sin confirm.
  4. Response `status:"reused"` → toast informativo (no error).
  5. Response 403/400/501 → toast de error con mensaje del server (`error` + `kind`).
- Comando (si vitest): `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/components/__tests__/PipelineTriggerCard.test.tsx`. Si vitest no instalado, `npx tsc --noEmit` y dejar checklist manual firmado.

**Criterio binario F4:** los 4 casos backend de preview pasan; `tsc --noEmit` 0 errores; los 5 casos frontend pasan (o checklist manual firmado si vitest no disponible); el endpoint de preview es read-only (no dispara, no muta `_RECENT_TRIGGERS`).

**Impacto por runtime:** ninguno (UI; sólo expuesta al operador).

**Trabajo del operador F4:** opt-in (default OFF); para usar, prender flag y confirmar PAT scope `api`.

---

### F5 — Monitoreo: polling del status con cancelación + cap concurrencia real + telemetría + ratchet

**Objetivo:** tras trigger, la UI hace polling de `monitor_pipeline` (vía `GET /api/ci/<project>/pipeline/<id>`) con backoff y cancelación al cerrar la card; el backend protege a GitLab con un cap de polls concurrentes por pipeline (store real `_ACTIVE_POLLS`, C4); cada trigger queda registrado para observabilidad (reuso).

**Archivos exactos F5:**
- `api/ci.py` — endpoint `GET /<project>/pipeline/<pipeline_id>` que llama `provider.monitor_pipeline(pipeline_id)` con el mismo guard per-request, cap de concurrencia `_ACTIVE_POLLS` (C4) y `try/except TrackerApiError → e.status` / `except NotImplementedError → 501` (C4').
- `frontend/src/components/PipelineTriggerCard.tsx` — tras trigger, polling cada 5s (backoff a 15s tras 3 intentos) hasta status terminal (`success`/`failed`/`canceled`); cancela al desmontar.

**Símbolos exactos F5 (cap de concurrencia REAL, C4):**

```python
# api/ci.py
@ci_bp.get("/<project>/pipeline/<pipeline_id>")
def monitor_pipeline_route(project: str, pipeline_id: str):
    if not config.STACKY_PIPELINE_TRIGGER_ENABLED:
        abort(404)
    n = _ACTIVE_POLLS.get(pipeline_id, 0)
    if n >= _MAX_ACTIVE_POLLS_PER_PIPELINE:          # C4 — cap anti-N+1 sobre GitLab
        return jsonify({"error": "too many active polls for pipeline"}), 429
    _ACTIVE_POLLS[pipeline_id] = n + 1
    try:
        provider = get_ci_provider(project)
        result = provider.monitor_pipeline(pipeline_id)
        return jsonify({**result, "tracker_type": provider.name, "source": "ci"})
    except TrackerApiError as e:                      # C4' — 404/403/... reales de GitLab
        return jsonify({"error": str(e), "kind": e.kind}), e.status
    except NotImplementedError as e:                  # ADO
        return jsonify({"error": str(e)}), 501
    finally:
        _ACTIVE_POLLS[pipeline_id] = max(0, _ACTIVE_POLLS.get(pipeline_id, 1) - 1)
```

**Telemetría (reuso, no reinvención):** `_record_trigger` ya guarda `(tracker_type, ref, sha, pipeline_id, ts)` en `_RECENT_TRIGGERS`; el endpoint de monitor incluye `tracker_type` y `source` en el JSON. (No se crea una tabla nueva de auditoría en v1; si más adelante el Panel de Salud Operativa (Plan 46) quiere persistir triggers, reusa ese panel — fuera de scope v1.)

**Tests F5:**
- Archivo: `backend/tests/test_plan72_monitor_endpoint.py`.
- Casos:
  1. `GET /api/ci/<project>/pipeline/<id>` con flag ON → llama `provider.monitor_pipeline` **[Patrón mock]**; response con `status`, `web_url`, `tracker_type`.
  2. Flag OFF → 404 (guard per-request).
  3. `AdoCIProvider.monitor_pipeline` lanza `NotImplementedError` → endpoint **501** (C4').
  4. `provider.monitor_pipeline` lanza `TrackerApiError(404, "no existe pipeline")` → endpoint **404** con mensaje (C4').
  5. **[C4]** Cap de concurrencia: pre-sembrar `_ACTIVE_POLLS["42"] = 5` → `GET .../pipeline/42` retorna **429**; con `_ACTIVE_POLLS["42"] = 0` retorna 200. (Test determinista sobre el store real.)
  6. **[C4]** Tras un request 200, `_ACTIVE_POLLS["<id>"]` vuelve a 0 (el `finally` decrementa).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_monitor_endpoint.py -q`.

**Ratchet F5:** registrar TODOS los `test_plan72_*.py` (incluidos `test_plan72_preview_endpoint.py` y `test_plan72_routes_registered.py`) en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49 (memoria `stacky-ratchet-obliga-registrar-tests`).

**Criterio binario F5:** los 6 casos pasan; ratchet verde con TODOS los `test_plan72_*.py` registrados; flag aparece en `harness_defaults.env` y UI.

**Trabajo del operador F5:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Trigger silencioso fallido por scope** (R1). **Mitigación:** F0 valida `api` scope **best-effort**; si el scope es conocido y falta → 400 con mensaje (F2 caso 4); si NO es verificable → no bloquea y el 403 real de GitLab (vía `TrackerApiError`) llega como 403 al operador (F2 caso 8). No se descubre el fallo en un 500 silencioso. (C3'/C4')
2. **Pipelines duplicados** (R2). **Mitigación:** `should_trigger` (F0) idempotencia por `(ref, sha)` en ventana 60s; store `_RECENT_TRIGGERS` definido (C5'); F2 caso 7 afirma `"status":"reused"` y `assert_not_called` en 2da.
3. **Polling sobrecarga GitLab** (R3). **Mitigación:** F5 backoff 5s→15s + cancelación al desmontar + cap **real** 429 con store `_ACTIVE_POLLS` (C4), F5 casos 5-6.
4. **Trigger autónomo sin HITL** (R4 — el más crítico). **Mitigación:** endpoint exige `confirm=True`; F2 caso 2 es **gate de significancia**. Preview read-only refuerza el consentimiento informado ([ADICIÓN ARQUITECTO v2]). Riel absoluto.
5. **Contrato de `_client._request` mal usado** (R5, C1'). **Mitigación:** F1 usa `body, _ =` y deja propagar `TrackerApiError`; el test F1 caso 5 lo afirma. No hay comparación de status a mano.
6. **Flag editable por UI que no surte efecto** (R6, C2'). **Mitigación:** blueprint registrado SIEMPRE en `api/__init__.py`; flag leída per-request → prender por UI surte efecto sin reiniciar (mismo mecanismo que Plan 71).
7. **Rutas mal registradas / doble prefijo `/api/api/ci`** (R7, C1 — el bug que v2 no atrapó). **Mitigación:** `ci_bp` con `url_prefix="/ci"` registrado en `api_bp` (no en app.py, no `/api/ci`); **test centinela `test_plan72_routes_registered.py`** afirma las rutas finales reales contra `create_app()` ([ADICIÓN ARQUITECTO v3]).
8. **Romper el contrato congelado del Plan 71** (R8, C3). **Mitigación:** F1 actualiza `test_ci_port_methods_is_frozen` a la 3-tupla en el mismo commit; F1 caso 6 + no-regresión del Plan 71 lo afirman.
9. **ADO trigger fuera de scope v1.** **Mitigación:** F3 lo declara `NotImplementedError` y el endpoint retorna 501 claro (no 500 silencioso).
10. **3 runtimes.** **Mitigación:** el plan no toca prompts/runtime del agente; el trigger es operador-driven (no autonomía).

---

## 6. Fuera de scope

- **NO** generar pipelines YAML declarativos (Plan 73).
- **NO** migración ADO→GitLab (Plan 74).
- **NO** deep links visuales (Plan 75) — se reusa `web_url` devuelta pero la composición visual profunda es del 75.
- **NO** trigger de ADO por API (v1; requiere REST de Azure Pipelines con scopes separados; fuera de scope).
- **NO** `retry_pipeline` (se hace después de v1 si hay demanda).
- **NO** persistir un log de auditoría de triggers en tabla nueva (v1 usa el store in-process + telemetría existente; persistencia es del Panel 46 si se requiere).
- **NO** tocar el sub-puerto más allá de `trigger_pipeline` (es la única extensión del bloque 70-76; el freeze test del Plan 71 se actualiza, no se elimina).

---

## 7. Glosario

- **CIProvider:** sub-puerto (`services/ci_provider.py`, creado en Plan 71 F1). En este plan se extiende con `trigger_pipeline` y se implementa `monitor_pipeline`. `CI_PORT_METHODS = ("infer_item_pipeline","monitor_pipeline","trigger_pipeline")` tras F1; el `test_ci_port_methods_is_frozen` del Plan 71 se **actualiza** a esa 3-tupla (C3).
- **`trigger_pipeline` (DOS capas, C7'):** (a) **adapter** `GitLabCIProvider.trigger_pipeline(item_ref, ref) -> dict` (sub-puerto, F2) que delega en (b) **client-level** `GitLabTrackerProvider.trigger_pipeline(ref) -> dict` (`gitlab_provider.py`, F1) que hace el POST real. Misma relación que los dos `infer_pipeline` del Plan 71.
- **`monitor_pipeline(pipeline_id)`:** método del sub-puerto; GET estado del pipeline. GitLab delega a `poll_pipeline`; ADO lanza `NotImplementedError`.
- **`_client._request` (contrato real, C1'):** `gitlab_client.py:107`; firma `(method, path, *, params, json_body, files, _retry)`; devuelve `(body, response_headers)` (anotado `-> tuple[object, dict]`); **lanza `TrackerApiError` ante no-2xx** (L153-159). Nunca comparar el 2º valor a un status.
- **`TrackerApiError`:** `tracker_provider.py:48`; `(status, message, *, kind="unknown")`. El endpoint la mapea a `e.status` (C4').
- **HITL absoluto:** riel que exige `confirm=True` explícito del operador para cualquier trigger; reforzado por el preview informado.
- **`validate_trigger_credentials` / `normalize_ref` / `should_trigger`:** funciones PURAS de `services/ci_trigger_rules.py` (F0). `validate_trigger_credentials` es **no bloqueante** cuando los scopes no son verificables (C3'). `normalize_ref().kind` es un **hint** de telemetría (C8').
- **`_RECENT_TRIGGERS` / `_recent_triggers` / `_record_trigger`:** store de idempotencia in-process en `api/ci.py` (C5'); mono-operador single-process; acotado por nº de refs (C6).
- **`_ACTIVE_POLLS` / `_MAX_ACTIVE_POLLS_PER_PIPELINE`:** contador in-process de polls concurrentes por pipeline (C4); cap 429 en el endpoint de monitor; incrementa al entrar, decrementa en `finally`.
- **`REQUIRED_SCOPES`:** dict `{tracker_type: set(scopes)}`; GitLab requiere `{"api"}`. La clave es `provider.name` ∈ `{"gitlab","azure_devops"}` (C6).
- **`STACKY_PIPELINE_TRIGGER_ENABLED`:** flag nueva de este plan (default OFF, editable por UI, leída per-request). Flag OFF → guard 404 (blueprint registrado siempre, C2').
- **Registro del blueprint (C1):** `ci_bp = Blueprint("ci", __name__, url_prefix="/ci")` se importa y registra en `api/__init__.py` sobre `api_bp` (que tiene `url_prefix="/api"`) → ruta final `/api/ci/...`. **Nunca** `url_prefix="/api/ci"` (daría `/api/api/ci`) ni registrar en `app.py`.
- **`GET /api/harness-flags`:** endpoint **existente** (`api/harness_flags.py:71`, ruta con guion) del que la UI lee el estado de la flag (C2/C6' — no se inventa `/api/ci/flags` ni `/api/harness/flags`).
- **`trigger-preview`:** endpoint read-only ([ADICIÓN ARQUITECTO v2]); reusa `fetch_pipelines` (Plan 71) vía `last_pipeline_for_ref`; no dispara; testeado en backend (C5).
- **`test_plan72_routes_registered.py`:** centinela de rutas reales contra `create_app()` ([ADICIÓN ARQUITECTO v3]).

---

## 8. Orden de implementación

0. **Pre-flight:** verificar que Plan 71 está implementado y verde (existen `services/ci_provider.py` con `CIProvider`/`ItemRef`/`get_ci_provider`/`CI_PORT_METHODS` y los adapters `gitlab_ci_provider.py`/`ado_ci_provider.py`). Si NO, detener: este plan no se puede empezar.
1. **F0** — Funciones puras `ci_trigger_rules.py` + tabla de scopes (validación no bloqueante, C3').
2. **F1** — Extensión `CIProvider` con `trigger_pipeline`; implementación `monitor_pipeline` en adapters; métodos `trigger_pipeline`/`poll_pipeline` en `gitlab_provider.py` con el contrato REAL de `_request` (C1'); **actualizar `test_ci_port_methods_is_frozen` del Plan 71** (C3).
3. **F2** — Adapter `GitLabCIProvider.trigger_pipeline` + endpoint `POST /api/ci/<project>/trigger` con HITL + idempotencia (store C5') + cap polls store (C4) + `try/except TrackerApiError` (C4') + **blueprint registrado en `api/__init__.py` con `url_prefix="/ci"`** (C1) + guard per-request (C2') + flag + **test centinela de rutas** ([ADICIÓN ARQUITECTO v3]).
4. **F3** — `AdoCIProvider.trigger_pipeline` = `NotImplementedError` (501 claro).
5. **F4** — UI `PipelineTriggerCard` con modal HITL informado + preview read-only **con test backend** (C5); flag leída de `GET /api/harness-flags` (C2/C6').
6. **F5** — Endpoint `GET /api/ci/<project>/pipeline/<id>` + cap concurrencia real + polling UI + telemetría reuso + ratchet.

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Funciones puras `validate_trigger_credentials` (no bloqueante si no verificable), `normalize_ref`, `should_trigger` implementadas y testeadas (F0, 10 casos).
- [ ] **(b)** `CIProvider` extendido con `trigger_pipeline`; `monitor_pipeline` implementado en GitLab adapter; `trigger_pipeline`/`poll_pipeline` usan `body, _ = _request(...)` y propagan `TrackerApiError` (F1, C1').
- [ ] **(b2)** `test_ci_port_methods_is_frozen` del Plan 71 actualizado a la 3-tupla y VERDE (F1 caso 6, C3).
- [ ] **(c)** Endpoint `POST /api/ci/<project>/trigger` rechaza sin `confirm=True` con 400 (F2 caso 2 — **gate HITL**).
- [ ] **(d)** Idempotencia por `(ref, sha)` en ventana 60s con store `_RECENT_TRIGGERS` definido (F2 casos 7 y 9, C5').
- [ ] **(e)** Validación de PAT scope `api` **best-effort**: bloquea sólo con scope conocido y faltante; no verificable → no bloquea (F2 casos 4 y 5, C3').
- [ ] **(f)** Flag `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**; blueprint registrado en `api/__init__.py` con `url_prefix="/ci"`; flag OFF → 404 vía guard per-request; prender por UI surte efecto sin reiniciar (C1/C2').
- [ ] **(f2)** Rutas reales en `/api/ci/...` (no `/api/api/ci`) verificadas por `test_plan72_routes_registered.py` contra `create_app()` (C1, [ADICIÓN ARQUITECTO v3]).
- [ ] **(g)** `TrackerApiError` del provider se mapea a su `e.status` (403/404/...) y `NotImplementedError` (ADO) a 501 (F2 caso 8, F3 caso 2, F5 casos 3-4, C4').
- [ ] **(h)** UI `PipelineTriggerCard` con modal HITL informado (preview read-only **con test backend**, C5); flag leída de `GET /api/harness-flags` (C2/C6'); `tsc --noEmit` 0 errores.
- [ ] **(i)** Monitoreo con polling + backoff + cancelación + cap 429 **con store `_ACTIVE_POLLS` real** (F5 casos 5-6, C4).
- [ ] **(j)** Los 3 runtimes operativos sin cambios (trigger operador-driven, sin autonomía).
- [ ] **(k)** Ratchet verde (Plan 49 F4) con TODOS los `test_plan72_*.py` registrados (incluidos preview y routes).

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Pre-flight Plan 71:** este plan consume `services/ci_provider.py` (`CIProvider`, `ItemRef`, `get_ci_provider`, `CI_PORT_METHODS`) y `services/{gitlab,ado}_ci_provider.py`. Al 2026-06-27 NO existen. Verificá que Plan 71 esté verde ANTES de empezar (orden §8 paso 0).
- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`.
- **Registro del blueprint (C1 — CRÍTICO):** `ci_bp = Blueprint("ci", __name__, url_prefix="/ci")`. Importar y registrar en **`api/__init__.py`** (`from .ci import bp as ci_bp` + `api_bp.register_blueprint(ci_bp)`), igual que `harness_flags` (`api/__init__.py:70`). **Prohibido** `url_prefix="/api/ci"` (daría `/api/api/ci`) y **prohibido** registrar en `app.py` (ahí sólo va `api_bp`). Verificalo con `test_plan72_routes_registered.py`.
- **Contrato `_client._request` (C1' — CRÍTICO):** devuelve `(body, response_headers)` y **ya lanza** `TrackerApiError` ante no-2xx (`gitlab_client.py:153-159`). Usar SIEMPRE `body, _ = self._client._request(...)`. **Prohibido** `body, status = ...; if status == 403`: es incorrecto (status serían headers) y muerto (el 403 ya se lanzó).
- **Endpoint de flags (C2/C6'):** la ruta real es **`/api/harness-flags`** (con guion, `api/harness_flags.py:71`). **Prohibido** `/api/harness/flags` (no existe) y `/api/ci/flags` (inventado).
- **Freeze test Plan 71 (C3):** al sumar `trigger_pipeline` a `CI_PORT_METHODS`, actualizar la aserción de `test_ci_port_methods_is_frozen` (Plan 71) a la 3-tupla EN EL MISMO commit, o el suite queda rojo. No borrar el test.
- **Scopes (C3'):** `_read_pat_scopes` devuelve `None` cuando no hay metadata de scopes; `validate_trigger_credentials(provider.name, None)` retorna `(True, ...)`. Nunca forzar un set vacío que bloquee.
- **Mapeo de errores (C4'):** todo endpoint que llame al provider va envuelto en `try/except TrackerApiError as e: return jsonify({"error": str(e), "kind": e.kind}), e.status` y `except NotImplementedError: ... 501`.
- **Cap de polls (C4):** `_ACTIVE_POLLS[pipeline_id]` se incrementa antes de llamar al provider y se decrementa en `finally`; 429 si ya está en `_MAX_ACTIVE_POLLS_PER_PIPELINE` (5). Test determinista: pre-sembrar el contador.
- **Preview (C5):** UNA sola llamada a `should_trigger(ref_value, last_sha, recent, 60)`; `last_sha` sale de `last_pipeline_for_ref`. El preview es read-only: NO llama `_record_trigger`. Tiene test backend propio (`test_plan72_preview_endpoint.py`).
- **Patrón mock:** `mock_provider.trigger_pipeline.assert_called_once_with(ItemRef(item_id=..., tracker_type="gitlab", ref=ref_value), ref_value)`. Para afirmar NO-autónomo: `mock_provider.trigger_pipeline.assert_not_called()` cuando `confirm` falta o cuando idempotencia reusa. Construir `ItemRef` SIEMPRE con `ref=` explícito (Plan 71 FIX C7').
- **Mock pattern DB:** importar `db` a nivel módulo; parchear lazy-imports en el módulo origen (memoria `plan-28-lifecycle`).
- **Falsos verdes prohibidos:** el test F2 caso 2 (HITL gate) DEBE afirmar 400 sin `confirm`; el F1 caso 5 DEBE afirmar que `TrackerApiError` PROPAGA (no se fabrica); el F2 caso 5 DEBE afirmar que scope no verificable NO bloquea; el centinela de rutas DEBE correr contra `create_app()` real (no una app de juguete).
- **Si una fase revela un GAP no listado**, detener y actualizar este doc.
