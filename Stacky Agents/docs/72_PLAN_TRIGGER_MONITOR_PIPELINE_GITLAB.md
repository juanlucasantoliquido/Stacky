# Plan 72 — Trigger y monitoreo de pipelines CI (HITL innegociable)

> **Estado:** PROPUESTO v2 (criticado por juez adversarial). Veredicto v1 = RECHAZADO (3 bloqueantes); v2 resuelve los 3.
> **Pre-requisito:** Plan 71 (sub-puerto `CIProvider` con `infer_item_pipeline` + `monitor_pipeline` definido). — **DEBE estar implementado primero**.
> **Roadmap:** Tercer eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer agnóstico → **trigger CI** → creador pipelines → migrador → deep links → eval).
> **Versión doc:** v2 (2026-06-27).
> **Dependencias:** Plan 71 (duro); Plan 70 (transitivo vía 71). No depende de 73/74/75/76.

> **CHANGELOG v1 → v2 (crítica adversarial; C# = hallazgo resuelto):**
> - **[C1 BLOQUEANTE — contrato de `_client._request` mal citado + rama 403 muerta]** El snippet F1 de `trigger_pipeline` hacía `body, status = self._client._request(...)` y `if status == 403`. **Verificado en `gitlab_client.py:107-166`:** `_request` devuelve `(body, response_headers)` (el 2º elemento son HEADERS, no status) y **ya lanza** `TrackerApiError(status, msg, kind=...)` ante cualquier respuesta no-2xx (L153-159). La rama `if status == 403` era código muerto e inducía a un modelo menor a copiar un bug. **Fix:** `trigger_pipeline`/`poll_pipeline` usan `body, _ = self._client._request(...)` y dejan **propagar** `TrackerApiError` (lo mapea el endpoint, C4). Test F1 caso 5 reescrito: un 403 del client **propaga** `TrackerApiError(status=403, kind="forbidden")` (no se fabrica a mano).
> - **[C2 BLOQUEANTE — gating de blueprint rompe el toggle por UI]** v1 ordenaba registrar `ci_bp` dentro de `if config.STACKY_PIPELINE_TRIGGER_ENABLED:` (gate en startup) Y a la vez `abort(404)` per-request en el handler. Contradictorio: `app.py:187` registra blueprints UNA vez en `create_app()` (no hay precedente de registro condicional); con la flag `env_only=False` "editable por UI", prender la flag NO registraría la ruta hasta reiniciar el backend → viola "editable por UI" y "cero trabajo extra". **Fix:** registrar `ci_bp` SIEMPRE (como todo blueprint) y dejar SOLO el guard per-request `if not config.STACKY_PIPELINE_TRIGGER_ENABLED: abort(404)` → dinámico, mismo patrón que las flags per-request del Plan 71. Eliminadas las instrucciones de registro condicional.
> - **[C3 BLOQUEANTE — gate de scope duro bloquea triggers legítimos]** v1 hacía `validate_trigger_credentials` un 400 duro si faltaba `api`, leyendo scopes vía `_read_pat_scopes`. Pero los scopes de un PAT GitLab **no son siempre introspectables** (el propio Plan 71 F0 L75 manda "no bloquear si no se puede verificar; degradar"). Si `_read_pat_scopes` devuelve vacío/desconocido → 400 SIEMPRE, bloqueando un PAT que sí tiene `api`. **Fix:** el gate sólo bloquea con scopes CONOCIDOS y faltantes; `scopes=None`/vacío-no-verificable ⇒ **no bloquea**, dispara y deja que el 403 real de GitLab sea la autoridad (ya lo lanza `_request` como `TrackerApiError` forbidden → 403 en el endpoint). Alineado con la degradación del Plan 71.
> - **[C4 IMPORTANTE — endpoint sin `try/except TrackerApiError` → 500 en vez de 403]** El snippet F2 llamaba `provider.trigger_pipeline(...)` sin captura; el test F2 caso 7 espera 403. **Fix:** `try/except TrackerApiError as e: return ..., e.status` en el endpoint de trigger y en el de monitor (F5).
> - **[C5 IMPORTANTE — store de idempotencia fantasma]** `_recent_triggers`/`_record_trigger` se usaban sin definir (sin archivo, símbolo, ni decisión de almacenamiento). **Fix:** store explícito module-level en `api/ci.py` (`_RECENT_TRIGGERS: dict`), justificado mono-operador single-process, con test de round-trip.
> - **[C6 IMPORTANTE — F4 inventaba `GET /api/ci/flags` + "o config global" vago]** **Verificado:** ya existe `GET /api/harness/flags` (`api/harness_flags.py:72`) que consume HarnessFlagsPanel. **Fix:** F4 reusa ese endpoint; eliminado el endpoint inventado y la frase vaga.
> - **[C7/C8 MENOR]** Glosario disambigua los DOS `trigger_pipeline` (adapter `(item_ref, ref)` vs client-level `(ref)`); `normalize_ref` `kind` documentado como hint (GitLab resuelve el `ref`, no se ramifica comportamiento por `kind`).
> - **[ADICIÓN ARQUITECTO]** F4 enriquece el modal HITL con un **preview read-only** (`GET /api/ci/<project>/trigger-preview?ref=`) que muestra `(kind, ref_value)`, el último pipeline existente para ese `ref` (reusa `fetch_pipelines`, Plan 71) y si la idempotencia reusaría — para que el operador confirme **informado**. Endurece el riel central (consentimiento HITL informado), read-only, cero trabajo extra, reusa lo existente. Detalle en F4.

---

## 1. Objetivo y KPI

Que Stacky pueda **disparar** (trigger) y **monitorear** pipelines CI desde la UI, con confirmación explícita del operador (HITL), sobre cualquier `CIProvider` (ADO o GitLab). Hoy `gitlab_provider.py:432 fetch_pipelines`/`:458 infer_pipeline` son solo-lectura; **no existe** `trigger_pipeline` en ningún adapter.

**KPI global (DoD):** el operador puede, desde la UI de Stacky, disparar un pipeline sobre un `ref` (branch/SHA) de un proyecto y ver su status, **sin salir de Stacky**, con `STACKY_PIPELINE_TRIGGER_ENABLED=true` y `confirm=True` explícito. Sin `confirm=True`, el endpoint rechaza con 400. Un PAT con scope `api` real dispara OK; un PAT sin `api` recibe el 403 real de GitLab (no un falso 400 preventivo cuando el scope no es verificable).

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy:

- `services/gitlab_provider.py:432 fetch_pipelines(ref)` lista pipelines vía `self._client._request_paginated("/projects/{proj}/pipelines", ...)`; `:458 infer_pipeline(ref)` infiere; **no hay** `trigger_pipeline` ni `retry_pipeline` ni `poll_pipeline` en el adapter GitLab.
- `services/gitlab_client.py:107 _request(method, path, *, params, json_body, files, _retry)` devuelve `(body, response_headers)` y **lanza `TrackerApiError(status, msg, kind=...)`** ante no-2xx (L153-159). `:98 _project_path()` URL-encodea el path. `TrackerApiError` vive en `tracker_provider.py:48` con firma `(status, message, *, kind)`.
- ADO no exponía un trigger cómodo desde el backend de Stacky (requería REST de Azure Pipelines con scopes separados); GitLab lo permite con `POST /projects/:id/pipeline` scope `api`.
- Hoy, para correr CI de un ítem GitLab desde Stacky, el operador debe ir a la web de GitLab: fricción que rompe el centauro.
- Plan 71 deja el sub-puerto `CIProvider` listo con `monitor_pipeline` declarado (`NotImplementedError` en adapters); este plan lo **implementa** y **extiende** con `trigger_pipeline`.

---

## 3. Principios y guardarraíles (heredados + HITL absoluto)

- **HITL INNEGOCIABLE (riel absoluto de 72):** el trigger exige `confirm=True` explícito del operador. **Nunca auto-disparar** desde un agente o un job en background. El endpoint valida `confirm is True`; el botón UI muestra modal con `ref` + `project` + preview + warning antes de setear `confirm`.
- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API/UI; NO toca prompts ni runtime del agente. El trigger es **operador-driven** (UI/API), nunca agente-driven → no introduce autonomía en ningún runtime.
- **Cero trabajo extra al operador:** flag opt-in `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI"), leída **per-request** (mismo patrón y mismo mecanismo de refresh que la flag `STACKY_PIPELINE_PROVIDER_ENABLED` del Plan 71 — este plan NO introduce un mecanismo de refresh nuevo). Flag OFF = endpoint responde 404 vía guard per-request.
- **Mono-operador sin auth:** PAT GitLab en `client_profile`; **requiere scope `api`** para disparar. Validación de scope **best-effort, no bloqueante cuando no es verificable** (ver F0/F2, C3). Para ADO, el adapter ADO lanza `NotImplementedError("trigger_pipeline ADO fuera de scope v1")` (ver F3). No hay RBAC ni roles (`current_user` es header sin validar; sería teatro).
- **No degradar / backward-compatible:** flag OFF → guard 404; ningún comportamiento existente cambia. El blueprint se registra siempre (sin tocar el orden de los demás).
- **TDD + funciones puras + ratchet + no falsos verdes.** La idempotencia, la normalización de `ref` y la validación de `confirm`/scopes son **funciones puras** testeables sin GitLab real.

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
    verificables (C3): si scopes is None o set() -> (True, "scopes no verificables; se
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
    telemetría (C8): GitLab resuelve el ref por sí mismo; el caller pasa SIEMPRE value,
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
  4. **[C3]** `validate_trigger_credentials("gitlab", None)` → `(True, ...)`; `validate_trigger_credentials("gitlab", set())` → `(True, ...)`. (No bloquear cuando no es verificable.)
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

### F1 — Extensión del sub-puerto `CIProvider` + implementación `monitor_pipeline`

**Objetivo:** extender el `Protocol` con `trigger_pipeline` e implementar `monitor_pipeline` en ambos adapters. Los métodos client-level usan el contrato REAL de `_client._request` (C1).

**Archivos exactos F1:**
- `services/ci_provider.py` — agregar `trigger_pipeline` al `Protocol`; actualizar `CI_PORT_METHODS`.
- `services/ado_ci_provider.py` — implementar `monitor_pipeline`; `trigger_pipeline` lanza `NotImplementedError` (ADO fuera de scope v1).
- `services/gitlab_ci_provider.py` — implementar `monitor_pipeline`; `trigger_pipeline` se implementa en F2.
- `services/gitlab_provider.py` — agregar `trigger_pipeline(ref)` y `poll_pipeline(pipeline_id)` (POST + GET sobre `/projects/:id/pipeline[s]`).

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
# y YA LANZA TrackerApiError(status, msg, kind=...) ante no-2xx. NO se compara status a mano (C1).
def trigger_pipeline(self, ref: str) -> dict:
    """POST /projects/:id/pipeline — dispara pipeline sobre el ref. Requiere scope api.
    Si GitLab responde 403, _request lanza TrackerApiError(403, ..., kind='forbidden');
    NO se captura aquí: se deja propagar para que el endpoint lo mapee a 403 (C1/C4)."""
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
  5. **[C1]** Si `self._client._request` **lanza** `TrackerApiError(403, "no api scope", kind="forbidden")`, `trigger_pipeline` **propaga** ese `TrackerApiError` (status=403, kind="forbidden") sin capturarlo ni fabricarlo. (Simula el contrato real del client.)
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_ci_provider_trigger_port.py -q`.

**Criterio binario F1:** los 5 casos pasan; `CI_PORT_METHODS` ahora tiene 3 métodos; ningún método compara el 2º valor de `_request` a un status (C1).

**Impacto por runtime:** ninguno (sin callers UI/API aún).

**Trabajo del operador F1:** ninguno.

---

### F2 — Adapter `trigger_pipeline` en `GitLabCIProvider` + endpoint API con HITL + idempotencia

**Objetivo:** cablear el trigger de GitLab al endpoint `POST /api/ci/<project>/trigger` con HITL (`confirm=True` obligatorio), idempotencia por `(ref, sha)`, validación de scopes best-effort (C3) y mapeo de `TrackerApiError` (C4). El blueprint se registra SIEMPRE; la flag se evalúa per-request (C2).

**Archivos exactos F2:**
- `services/gitlab_ci_provider.py` — implementar `trigger_pipeline(item_ref, ref)` (delega a `delegate.trigger_pipeline(ref)`).
- `api/ci.py` — **blueprint nuevo** `ci_bp` con endpoint `POST /<project>/trigger` + store de idempotencia module-level (C5).
- `app.py` — registrar el blueprint `ci_bp` **incondicionalmente** (como `api_bp` en `app.py:187`); el gating es per-request dentro del handler (C2). **NO** registrar dentro de un `if config...`.
- `config.py` — `STACKY_PIPELINE_TRIGGER_ENABLED: bool = False`.
- `harness_defaults.env` — `STACKY_PIPELINE_TRIGGER_ENABLED=false`.

**Símbolos exactos F2 (store de idempotencia + endpoint con HITL absoluto):**

```python
# api/ci.py
from services.tracker_provider import TrackerApiError
from services.ci_provider import get_ci_provider, ItemRef
from services.ci_trigger_rules import normalize_ref, validate_trigger_credentials, should_trigger
import time

ci_bp = Blueprint("ci", __name__, url_prefix="/api/ci")

# C5 — store de idempotencia in-process. Mono-operador single-process (memoria
# stacky-no-auth-substrate): un dict module-level es suficiente y no requiere DB.
# clave: (tracker_type, ref) -> {"sha","pipeline_id","ts"}
_RECENT_TRIGGERS: dict[tuple[str, str], dict] = {}

def _recent_triggers(tracker_type: str, ref: str) -> list[dict]:
    e = _RECENT_TRIGGERS.get((tracker_type, ref))
    return [e] if e else []

def _record_trigger(tracker_type: str, ref: str, sha: str, pipeline_id: str) -> None:
    _RECENT_TRIGGERS[(tracker_type, ref)] = {"ref": ref, "sha": sha,
                                             "pipeline_id": pipeline_id, "ts": time.time()}

def _read_pat_scopes(provider) -> set[str] | None:
    """Best-effort (C3): lee scopes del client_profile si están; si no son verificables,
    devuelve None (NO set vacío forzado a bloquear)."""
    ...   # retorna None cuando no hay metadata de scopes -> validate no bloquea

@ci_bp.post("/<project>/trigger")
def trigger_pipeline_route(project: str):
    if not config.STACKY_PIPELINE_TRIGGER_ENABLED:
        abort(404)   # guard per-request: flag OFF = 404 (C2). El blueprint SIEMPRE está registrado.
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400   # RIEL ABSOLUTO
    try:
        _, ref_value = normalize_ref(body.get("ref") or "")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    provider = get_ci_provider(project)
    scopes = _read_pat_scopes(provider)                       # None si no verificable (C3)
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
    except TrackerApiError as e:                              # C4 — 403 real de GitLab, etc.
        return jsonify({"error": str(e), "kind": e.kind}), e.status
    except NotImplementedError as e:                          # ADO (F3)
        return jsonify({"error": str(e)}), 501
    _record_trigger(provider.name, ref_value, result.get("sha", ""), result["id"])
    return jsonify(result)
```

**Tests F2 (TDD, HITL crítico):**
- Archivo: `backend/tests/test_plan72_trigger_endpoint.py`.
- Casos:
  1. Flag OFF → `POST /<project>/trigger` retorna **404** (guard per-request; blueprint registrado).
  2. Flag ON + body sin `confirm` → **400** con `"confirm=True requerido"`. **[RIEL ABSOLUTO — test VP-01]**
  3. Flag ON + `confirm=True` + `ref="develop"` + scopes válidos (o None) + sin trigger reciente → llama `provider.trigger_pipeline` **[Patrón mock: assert_called_once]**; response 200 con `pipeline_id`.
  4. Flag ON + scopes **conocidos** inválidos (`{"read_api"}` sin `api`) → **400** con mensaje que incluye `"api"`.
  5. **[C3]** Flag ON + `_read_pat_scopes` retorna `None` (no verificable) → NO bloquea: llama `provider.trigger_pipeline` (no 400 preventivo).
  6. Flag ON + `ref` vacío → 400 (ValueError → 400).
  7. Idempotencia: segundo trigger con mismo `(ref, sha)` en ventana → response 200 `"status":"reused"`, NO llama `provider.trigger_pipeline` **[mock: assert_not_called en 2da]**.
  8. **[C4]** Flag ON + provider lanza `TrackerApiError(403, ..., kind="forbidden")` → response **403** con `kind`.
  9. **[C5]** `_record_trigger("gitlab","develop","sha1","42")` luego `_recent_triggers("gitlab","develop")` retorna 1 entrada con `pipeline_id="42"`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_trigger_endpoint.py -q`.

**Criterio binario F2:** los 9 casos pasan. **Caso 2 es el gate de significancia del HITL** — sin él, el trigger sería autónomo.

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
  2. El endpoint `POST /api/ci/<proj-ado>/trigger` con `confirm=True` captura el `NotImplementedError` → response **501** con mensaje accionable (C4: el endpoint ya tiene `except NotImplementedError → 501`).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_ado_trigger_not_implemented.py -q`.

**Criterio binario F3:** los 2 casos pasan; ADO no se rompe (flag OFF = 404; flag ON + ADO = 501 claro).

**Trabajo del operador F3:** ninguno.

---

### F4 — UI: botón "Disparar pipeline" con modal HITL informado

**Objetivo:** card del ítem con botón que abre modal de confirmación con **preview informado** (`ref` resuelto + último pipeline existente + aviso de idempotencia + warning "Esto dispara un pipeline real en GitLab") y, al confirmar, llama al endpoint con `confirm=True`.

**Archivos exactos F4:**
- `frontend/src/components/PipelineTriggerCard.tsx` — **nuevo**.
- `frontend/src/pages/DiagnosticsPage.tsx` (o donde se monten las cards de pipeline) — integrar la card.
- `frontend/src/api.ts` (o equivalente) — `triggerPipeline(project, ref, itemId, confirm)` → `POST /api/ci/<project>/trigger`; `triggerPreview(project, ref)` → `GET /api/ci/<project>/trigger-preview?ref=`.
- `api/ci.py` — endpoint read-only `GET /<project>/trigger-preview` (ver [ADICIÓN ARQUITECTO]).

**[ADICIÓN ARQUITECTO] — Preview HITL informado (read-only, reusa `fetch_pipelines`):**

```python
# api/ci.py — read-only; mismo guard per-request de flag (C2). NO dispara nada.
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
    recent = _recent_triggers(provider.name, ref_value)
    would_reuse, existing = (not should_trigger(ref_value, "", recent)[0]), should_trigger(ref_value, "", recent)[1]
    return jsonify({"kind": kind, "ref": ref_value, "last_pipeline": last,
                    "would_reuse": would_reuse, "existing_pipeline_id": existing})
```

`GitLabCIProvider.last_pipeline_for_ref(ref)` y `AdoCIProvider.last_pipeline_for_ref(ref)` son **read-only**; GitLab reusa `fetch_pipelines(ref)[0]` o `None`; ADO devuelve `None` (sin preview ADO en v1). Justificación: amplifica el consentimiento HITL (el operador confirma viendo el último pipeline y si se reusaría), es solo-lectura (cero riesgo de autonomía), reusa lo existente, cero trabajo extra (invisible hasta abrir el modal).

**Símbolos exactos F4:**
- `<PipelineTriggerCard project itemId ref />` — al montar lee el estado de la flag desde el endpoint **existente** `GET /api/harness/flags` (`api/harness_flags.py:72`, consumido ya por HarnessFlagsPanel) y deshabilita el botón si la flag está OFF (con tooltip). **No** se inventa `GET /api/ci/flags` (C6).
- Click botón → `triggerPreview` y abre modal con `ref` resuelto + último pipeline + texto `"Vas a disparar un pipeline en <project> sobre <ref>. Confirmar."`.
- El modal setea `confirm: true` SÓLO al clic explícito en "Disparar".

**Tests F4:**
- Archivo: `frontend/src/components/__tests__/PipelineTriggerCard.test.tsx` (vitest si está disponible; si no, test manual documentado — ver memoria `stacky-backend-dev-test-env`: vitest puede no estar instalado).
- Casos:
  1. Flag OFF (según `GET /api/harness/flags`) → botón deshabilitado con tooltip.
  2. Click botón → llama `triggerPreview` y abre modal con `ref` y `project` y el `last_pipeline` del preview.
  3. Click "Disparar" en modal → llama `triggerPipeline(..., confirm=true)`; NO se llama sin confirm.
  4. Response `status:"reused"` → toast informativo (no error).
  5. Response 403/400/501 → toast de error con mensaje del server (`error` + `kind`).
- Comando (si vitest): `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/components/__tests__/PipelineTriggerCard.test.tsx`. Si vitest no instalado, `npx tsc --noEmit` y dejar checklist manual firmado.

**Criterio binario F4:** `tsc --noEmit` 0 errores; los 5 casos pasan (o checklist manual firmado si vitest no disponible); el endpoint de preview es read-only (no dispara).

**Impacto por runtime:** ninguno (UI; sólo expuesta al operador).

**Trabajo del operador F4:** opt-in (default OFF); para usar, prender flag y confirmar PAT scope `api`.

---

### F5 — Monitoreo: polling del status con cancelación + telemetría + ratchet

**Objetivo:** tras trigger, la UI hace polling de `monitor_pipeline` (vía `GET /api/ci/<project>/pipeline/<id>`) con backoff y cancelación al cerrar la card; cada trigger queda registrado para observabilidad (reuso).

**Archivos exactos F5:**
- `api/ci.py` — endpoint `GET /<project>/pipeline/<pipeline_id>` que llama `provider.monitor_pipeline(pipeline_id)` con el mismo guard per-request y `try/except TrackerApiError → e.status` / `except NotImplementedError → 501` (C4).
- `frontend/src/components/PipelineTriggerCard.tsx` — tras trigger, polling cada 5s (backoff a 15s tras 3 intentos) hasta status terminal (`success`/`failed`/`canceled`); cancela al desmontar.

**Telemetría (reuso, no reinvención):** `_record_trigger` ya guarda `(tracker_type, ref, sha, pipeline_id, ts)` en `_RECENT_TRIGGERS`; el endpoint de monitor incluye `tracker_type` y `source` en el JSON. (No se crea una tabla nueva de auditoría en v1; si más adelante el Panel de Salud Operativa (Plan 46) quiere persistir triggers, reusa ese panel — fuera de scope v1.)

**Tests F5:**
- Archivo: `backend/tests/test_plan72_monitor_endpoint.py`.
- Casos:
  1. `GET /<project>/pipeline/<id>` con flag ON → llama `provider.monitor_pipeline` **[Patrón mock]**; response con `status`, `web_url`, `tracker_type`.
  2. Flag OFF → 404 (guard per-request).
  3. `AdoCIProvider.monitor_pipeline` lanza `NotImplementedError` → endpoint **501** (C4).
  4. `provider.monitor_pipeline` lanza `TrackerApiError(404, "no existe pipeline")` → endpoint **404** con mensaje (C4).
  5. Cap de concurrencia: 429 si ya hay N (default 5) polls activos para el mismo pipeline (prevenir N+1 sobre GitLab).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_monitor_endpoint.py -q`.

**Ratchet F5:** registrar TODOS los `test_plan72_*.py` en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49 (memoria `stacky-ratchet-obliga-registrar-tests`).

**Criterio binario F5:** los 5 casos pasan; ratchet verde; flag aparece en `harness_defaults.env` y UI.

**Trabajo del operador F5:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Trigger silencioso fallido por scope** (R1). **Mitigación:** F0 valida `api` scope **best-effort**; si el scope es conocido y falta → 400 con mensaje (F2 caso 4); si NO es verificable → no bloquea y el 403 real de GitLab (vía `TrackerApiError`) llega como 403 al operador (F2 caso 8). No se descubre el fallo en un 500 silencioso. (C3/C4)
2. **Pipelines duplicados** (R2). **Mitigación:** `should_trigger` (F0) idempotencia por `(ref, sha)` en ventana 60s; store `_RECENT_TRIGGERS` definido (C5); F2 caso 7 afirma `"status":"reused"` y `assert_not_called` en 2da.
3. **Polling sobrecarga GitLab** (R3). **Mitigación:** F5 backoff 5s→15s + cancelación al desmontar + cap 429 si >5 polls activos.
4. **Trigger autónomo sin HITL** (R4 — el más crítico). **Mitigación:** endpoint exige `confirm=True`; F2 caso 2 es **gate de significancia**. Preview read-only refuerza el consentimiento informado ([ADICIÓN ARQUITECTO]). Riel absoluto.
5. **Contrato de `_client._request` mal usado** (R5, C1). **Mitigación:** F1 usa `body, _ =` y deja propagar `TrackerApiError`; el test F1 caso 5 lo afirma. No hay comparación de status a mano.
6. **Flag editable por UI que no surte efecto** (R6, C2). **Mitigación:** blueprint registrado SIEMPRE; flag leída per-request → prender por UI surte efecto sin reiniciar (mismo mecanismo que Plan 71).
7. **ADO trigger fuera de scope v1.** **Mitigación:** F3 lo declara `NotImplementedError` y el endpoint retorna 501 claro (no 500 silencioso).
8. **3 runtimes.** **Mitigación:** el plan no toca prompts/runtime del agente; el trigger es operador-driven (no autonomía).

---

## 6. Fuera de scope

- **NO** generar pipelines YAML declarativos (Plan 73).
- **NO** migración ADO→GitLab (Plan 74).
- **NO** deep links visuales (Plan 75) — se reusa `web_url` devuelta pero la composición visual profunda es del 75.
- **NO** trigger de ADO por API (v1; requiere REST de Azure Pipelines con scopes separados; fuera de scope).
- **NO** `retry_pipeline` (se hace después de v1 si hay demanda).
- **NO** persistir un log de auditoría de triggers en tabla nueva (v1 usa el store in-process + telemetría existente; persistencia es del Panel 46 si se requiere).
- **NO** tocar el sub-puerto más allá de `trigger_pipeline` (es la única extensión del bloque 70-76).

---

## 7. Glosario

- **CIProvider:** sub-puerto (`services/ci_provider.py`, creado en Plan 71 F1). En este plan se extiende con `trigger_pipeline` y se implementa `monitor_pipeline`. `CI_PORT_METHODS = ("infer_item_pipeline","monitor_pipeline","trigger_pipeline")` tras F1.
- **`trigger_pipeline` (DOS capas, C7):** (a) **adapter** `GitLabCIProvider.trigger_pipeline(item_ref, ref) -> dict` (sub-puerto, F2) que delega en (b) **client-level** `GitLabTrackerProvider.trigger_pipeline(ref) -> dict` (`gitlab_provider.py`, F1) que hace el POST real. Misma relación que los dos `infer_pipeline` del Plan 71.
- **`monitor_pipeline(pipeline_id)`:** método del sub-puerto; GET estado del pipeline. GitLab delega a `poll_pipeline`; ADO lanza `NotImplementedError`.
- **`_client._request` (contrato real, C1):** `gitlab_client.py:107`; firma `(method, path, *, params, json_body, files)`; devuelve `(body, response_headers)`; **lanza `TrackerApiError` ante no-2xx**. Nunca comparar el 2º valor a un status.
- **`TrackerApiError`:** `tracker_provider.py:48`; `(status, message, *, kind)`. El endpoint la mapea a `e.status` (C4).
- **HITL absoluto:** riel que exige `confirm=True` explícito del operador para cualquier trigger; reforzado por el preview informado.
- **`validate_trigger_credentials` / `normalize_ref` / `should_trigger`:** funciones PURAS de `services/ci_trigger_rules.py` (F0). `validate_trigger_credentials` es **no bloqueante** cuando los scopes no son verificables (C3). `normalize_ref().kind` es un **hint** de telemetría (C8).
- **`_RECENT_TRIGGERS` / `_recent_triggers` / `_record_trigger`:** store de idempotencia in-process en `api/ci.py` (C5); mono-operador single-process.
- **`REQUIRED_SCOPES`:** dict `{tracker_type: set(scopes)}`; GitLab requiere `{"api"}`.
- **`STACKY_PIPELINE_TRIGGER_ENABLED`:** flag nueva de este plan (default OFF, editable por UI, leída per-request). Flag OFF → guard 404 (blueprint registrado siempre, C2).
- **`GET /api/harness/flags`:** endpoint **existente** (`api/harness_flags.py:72`) del que la UI lee el estado de la flag (C6 — no se inventa `/api/ci/flags`).
- **`trigger-preview`:** endpoint read-only ([ADICIÓN ARQUITECTO]); reusa `fetch_pipelines` (Plan 71); no dispara.

---

## 8. Orden de implementación

1. **F0** — Funciones puras `ci_trigger_rules.py` + tabla de scopes (validación no bloqueante, C3).
2. **F1** — Extensión `CIProvider` con `trigger_pipeline`; implementación `monitor_pipeline` en adapters; métodos `trigger_pipeline`/`poll_pipeline` en `gitlab_provider.py` con el contrato REAL de `_request` (C1).
3. **F2** — Adapter `GitLabCIProvider.trigger_pipeline` + endpoint `POST /api/ci/<project>/trigger` con HITL + idempotencia (store C5) + `try/except TrackerApiError` (C4) + blueprint registrado siempre + guard per-request (C2) + flag.
4. **F3** — `AdoCIProvider.trigger_pipeline` = `NotImplementedError` (501 claro).
5. **F4** — UI `PipelineTriggerCard` con modal HITL informado + preview read-only ([ADICIÓN ARQUITECTO]); flag leída de `GET /api/harness/flags` (C6).
6. **F5** — Endpoint `GET /<project>/pipeline/<id>` + polling UI + telemetría reuso + ratchet.

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Funciones puras `validate_trigger_credentials` (no bloqueante si no verificable), `normalize_ref`, `should_trigger` implementadas y testeadas (F0, 10 casos).
- [ ] **(b)** `CIProvider` extendido con `trigger_pipeline`; `monitor_pipeline` implementado en GitLab adapter; `trigger_pipeline`/`poll_pipeline` usan `body, _ = _request(...)` y propagan `TrackerApiError` (F1, C1).
- [ ] **(c)** Endpoint `POST /api/ci/<project>/trigger` rechaza sin `confirm=True` con 400 (F2 caso 2 — **gate HITL**).
- [ ] **(d)** Idempotencia por `(ref, sha)` en ventana 60s con store `_RECENT_TRIGGERS` definido (F2 casos 7 y 9, C5).
- [ ] **(e)** Validación de PAT scope `api` **best-effort**: bloquea sólo con scope conocido y faltante; no verificable → no bloquea (F2 casos 4 y 5, C3).
- [ ] **(f)** Flag `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**; blueprint registrado siempre; flag OFF → 404 vía guard per-request; prender por UI surte efecto sin reiniciar (C2).
- [ ] **(g)** `TrackerApiError` del provider se mapea a su `e.status` (403/404/...) y `NotImplementedError` (ADO) a 501 (F2 caso 8, F3 caso 2, F5 casos 3-4, C4).
- [ ] **(h)** UI `PipelineTriggerCard` con modal HITL informado (preview read-only); flag leída de `GET /api/harness/flags`; `tsc --noEmit` 0 errores (C6 + [ADICIÓN]).
- [ ] **(i)** Monitoreo con polling + backoff + cancelación + cap 429 (F5).
- [ ] **(j)** Los 3 runtimes operativos sin cambios (trigger operador-driven, sin autonomía).
- [ ] **(k)** Ratchet verde (Plan 49 F4) con los archivos `test_plan72_*.py` registrados.

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`.
- **Contrato `_client._request` (C1 — CRÍTICO):** devuelve `(body, response_headers)` y **ya lanza** `TrackerApiError` ante no-2xx (`gitlab_client.py:153-159`). Usar SIEMPRE `body, _ = self._client._request(...)`. **Prohibido** `body, status = ...; if status == 403`: es incorrecto (status serían headers) y muerto (el 403 ya se lanzó).
- **Blueprint (C2):** registrar `ci_bp` en `app.py` **incondicionalmente**, junto al resto (`app.py:187`). El gating es SÓLO el `abort(404)` per-request dentro de cada handler. **Prohibido** `if config.X: app.register_blueprint(...)` (rompería el toggle por UI).
- **Scopes (C3):** `_read_pat_scopes` devuelve `None` cuando no hay metadata de scopes; `validate_trigger_credentials(provider.name, None)` retorna `(True, ...)`. Nunca forzar un set vacío que bloquee.
- **Mapeo de errores (C4):** todo endpoint que llame al provider va envuelto en `try/except TrackerApiError as e: return jsonify({"error": str(e), "kind": e.kind}), e.status` y `except NotImplementedError: ... 501`.
- **Patrón mock:** `mock_provider.trigger_pipeline.assert_called_once_with(ItemRef(...), ref_value)`. Para afirmar NO-autónomo: `mock_provider.trigger_pipeline.assert_not_called()` cuando `confirm` falta o cuando idempotencia reusa.
- **Mock pattern DB:** importar `db` a nivel módulo; parchear lazy-imports en el módulo origen (memoria `plan-28-lifecycle`).
- **Flag editable por UI:** reusar `GET /api/harness/flags` (`api/harness_flags.py:72`) — no inventar endpoints (C6).
- **Falsos verdes prohibidos:** el test F2 caso 2 (HITL gate) DEBE afirmar 400 sin `confirm`; el F1 caso 5 DEBE afirmar que `TrackerApiError` PROPAGA (no se fabrica); el F2 caso 5 DEBE afirmar que scope no verificable NO bloquea.
- **Si una fase revela un GAP no listado**, detener y actualizar este doc.
