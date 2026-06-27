# Plan 72 — Trigger y monitoreo de pipelines CI (HITL innegociable)

> **Estado:** PROPUESTO v1.
> **Pre-requisito:** Plan 71 (sub-puerto `CIProvider` con `infer_item_pipeline` + `monitor_pipeline` definido). — **DEBE estar implementado primero**.
> **Roadmap:** Tercer eslabón del bloque GitLab-Main 70-76 (desacople → pipeline-infer agnóstico → **trigger CI** → creador pipelines → migrador → deep links → eval).
> **Versión doc:** v1 (2026-06-27).
> **Dependencias:** Plan 71 (duro); Plan 70 (transitivo vía 71). No depende de 73/74/75/76.

> **CHANGELOG boceto v0 → v1:**
> - **[DECISIÓN ARQUITECTÓNICA HEREDADA]** Sub-puerto `CIProvider` creado en Plan 71. Este plan **extiende** ese `Protocol` con `trigger_pipeline(item_ref, ref) -> dict` (única extensión del sub-puerto en todo el bloque 70-76) e **implementa** `monitor_pipeline` (que en 71 lanza `NotImplementedError`).
> - **[HITL ABSOLUTA]** El trigger de pipeline **jamás es autónomo**. Riel duro: el endpoint `POST /api/ci/<project>/trigger` exige el header/body `confirm=True` seteado por la UI tras clic explícito del operador en el modal de confirmación. Sin `confirm=True` → 400. Documentado en F2.
> - **[FIX B0-PAT]** F0 valida el scope `api` del PAT GitLab ANTES de cualquier trigger; sin `api` → 400 con mensaje accionable. No se descubre el 403 en runtime.
> - **[FIX B0-IDEMPOTENCIA]** F2 introduce idempotencia por `(ref, sha)` en ventana de N segundos (default 60s); el segundo trigger dentro de la ventana retorna el `pipeline_id` existente (no dispara de nuevo).
> - **[FLAG ALIGN]** Flag renombrada a `STACKY_PIPELINE_TRIGGER_ENABLED` (consistente con el prompt y con `STACKY_PIPELINE_PROVIDER_ENABLED` de 71).

---

## 1. Objetivo y KPI

Que Stacky pueda **disparar** (trigger) y **monitorear** pipelines CI desde la UI, con confirmación explícita del operador (HITL), sobre cualquier `CIProvider` (ADO o GitLab). Hoy `gitlab_provider.py:432 fetch_pipelines`/`:458 infer_pipeline` son solo-lectura; **no existe** `trigger_pipeline` en ningún adapter.

**KPI global (DoD):** el operador puede, desde la UI de Stacky, disparar un pipeline sobre un `ref` (branch/SHA) de un proyecto y ver su status, **sin salir de Stacky**, con `STACKY_PIPELINE_TRIGGER_ENABLED=true` y `confirm=True` explícito. Sin `confirm=True`, el endpoint rechaza con 400.

---

## 2. Por qué ahora / gap que cierra

Verificado en código hoy:

- `services/gitlab_provider.py:432 fetch_pipelines(ref)` lista pipelines; `:458 infer_pipeline(ref)` infiere; **no hay** `trigger_pipeline` ni `retry_pipeline` ni `poll_pipeline` en el adapter GitLab.
- ADO no exponía un trigger cómodo desde el backend de Stacky (requería REST de Azure Pipelines con scopes separados); GitLab lo permite con `POST /projects/:id/pipeline` scope `api`.
- Hoy, para correr CI de un ítem GitLab desde Stacky, el operador debe ir a la web de GitLab: fricción que rompe el centauro.
- Plan 71 deja el sub-puerto `CIProvider` listo con `monitor_pipeline` declarado (`NotImplementedError` en adapters); este plan lo **implementa** y **extiende** con `trigger_pipeline`.

---

## 3. Principios y guardarraíles (heredados + HITL absoluto)

- **HITL INNEGOCIABLE (riel absoluto de 72):** el trigger exige `confirm=True` explícito del operador. **Nunca auto-disparar** desde un agente o un job en background. El endpoint valida `confirm is True`; el botón UI muestra modal con `ref` + `project` + warning antes de setear `confirm`.
- **3 runtimes con paridad** (Codex, Claude Code, GitHub Copilot Pro): el cambio vive en servicios/API/UI; NO toca prompts ni runtime del agente.
- **Cero trabajo extra al operador:** flag opt-in `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**, editable por UI (HarnessFlagsPanel, categoría "Pipelines / CI"). Flag OFF = endpoint 404 (no existe ruta).
- **Mono-operador sin auth:** PAT GitLab en `client_profile`; **requiere scope `api`** (validado en F0, no `read_api` como 71). Para ADO, se requiere un PAT con scope `Pipeline.ReadWrite` o equivalente (documentar; en v1 el adapter ADO lanza `NotImplementedError("trigger_pipeline ADO fuera de scope v1")` — ver F3).
- **No degradar / backward-compatible:** flag OFF → ruta no registrada; ningún comportamiento existente cambia.
- **TDD + funciones puras + ratchet + no falsos verdes.** La lógica de idempotencia, validación de `ref` y validación de `confirm` son **funciones puras** testeables sin GitLab real.

---

## 4. Fases

### F0 — Validación de PAT scope + contrato de `ref` + idempotencia

**Objetivo:** definir y testear las 3 funciones puras que gobiernan el trigger antes de tocar la red: validación de scopes, normalización de `ref`, decisión de idempotencia.

**Archivos exactos F0:**
- `services/ci_trigger_rules.py` — **archivo nuevo** (3 funciones puras).
- `services/gitlab_provider.py` — referencia para scopes requeridos.

**Símbolos exactos F0 (funciones PURAS, sin I/O):**

```python
# services/ci_trigger_rules.py
REQUIRED_SCOPES = {"gitlab": {"api"}, "azure_devops": {"vso.build_execute"}}

def validate_trigger_credentials(tracker_type: str, scopes: set[str]) -> tuple[bool, str]:
    """Devuelve (ok, mensaje). Si falta scope requerido, ok=False y mensaje accionable."""
    required = REQUIRED_SCOPES.get(tracker_type, set())
    missing = required - set(scopes or set())
    if missing:
        return False, f"PAT falta scope(s): {','.join(sorted(missing))} (requerido para trigger en {tracker_type})"
    return True, "ok"

def normalize_ref(ref: str) -> tuple[str, str]:
    """Normaliza ref a (kind, value). kind ∈ {"branch","sha","tag"}.
    SHA: ^[0-9a-f]{7,40}$; tag: refs/tags/X; resto branch.
    Lanza ValueError si ref vacío o contiene caracteres prohibidos."""
    ...

def should_trigger(ref: str, sha: str, recent_triggers: list[dict], window_seconds: int = 60) -> tuple[bool, str | None]:
    """Idempotencia: si existe un trigger reciente para (ref, sha) dentro de la ventana,
    devuelve (False, existing_pipeline_id). Si no, (True, None). PURA."""
    ...
```

**Tests F0 (TDD primero):**
- Archivo: `backend/tests/test_plan72_trigger_rules.py`.
- Casos:
  1. `validate_trigger_credentials("gitlab", {"api"})` → `(True, "ok")`.
  2. `validate_trigger_credentials("gitlab", {"read_api"})` → `(False, msg con "api")`.
  3. `validate_trigger_credentials("azure_devops", {"vso.build_execute"})` → `(True, ...)`.
  4. `normalize_ref("develop")` → `("branch", "develop")`.
  5. `normalize_ref("abc1234")` (7 hex) → `("sha", "abc1234")`; `"zzzzzzz"` → `("branch", "zzzzzzz")` (no es hex).
  6. `normalize_ref("")` → lanza `ValueError`.
  7. `should_trigger("develop", "abc123", [], 60)` → `(True, None)`.
  8. `should_trigger("develop", "abc123", [{"ref":"develop","sha":"abc123","pipeline_id":"99","ts":now}], 60)` → `(False, "99")`.
  9. `should_trigger` con trigger fuera de ventana (>60s) → `(True, None)`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_trigger_rules.py -q`.

**Criterio binario F0:** los 9 casos pasan; las 3 funciones son puras (sin I/O, sin import requests).

**Impacto por runtime:** ninguno (archivo nuevo inerte).

**Flag F0:** ninguna.

**Trabajo del operador F0:** ninguno. (Para usar el trigger después: PAT GitLab debe tener scope `api` — documentado en la UI.)

---

### F1 — Extensión del sub-puerto `CIProvider` + implementación `monitor_pipeline`

**Objetivo:** extender el `Protocol` con `trigger_pipeline` e implementar `monitor_pipeline` en ambos adapters.

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
# services/gitlab_provider.py — nuevos métodos sobre el _client existente:
def trigger_pipeline(self, ref: str) -> dict:
    """POST /projects/:id/pipeline — dispara pipeline sobre el ref. Requiere scope api."""
    proj_path = self._client._project_path()
    body, status = self._client._request(
        "POST", f"/projects/{proj_path}/pipeline",
        json_body={"ref": ref},
    )
    if status == 403:
        raise TrackerApiError(403, "403 de GitLab: PAT sin scope 'api'", kind="forbidden")
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
  2. `GitLabCIProvider.monitor_pipeline("99")` llama a `delegate.poll_pipeline("99")` **[Patrón mock: assert_called]**.
  3. `AdoCIProvider.monitor_pipeline("99")` lanza `NotImplementedError`.
  4. `GitLabTrackerProvider.trigger_pipeline("develop")` construye POST con `json_body={"ref":"develop"}` **[Patrón mock sobre `self._client._request`]**.
  5. `trigger_pipeline` con 403 → `TrackerApiError(403, ..., kind="forbidden")`.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_ci_provider_trigger_port.py -q`.

**Criterio binario F1:** los 5 casos pasan; `CI_PORT_METHODS` ahora tiene 3 métodos.

**Impacto por runtime:** ninguno (sin callers UI/API aún).

**Trabajo del operador F1:** ninguno.

---

### F2 — Adapter `trigger_pipeline` en `GitLabCIProvider` + endpoint API con HITL + idempotencia

**Objetivo:** cablear el trigger de GitLab al endpoint `POST /api/ci/<project>/trigger` con HITL (`confirm=True` obligatorio), idempotencia por `(ref, sha)` y validación de scopes.

**Archivos exactos F2:**
- `services/gitlab_ci_provider.py` — implementar `trigger_pipeline(item_ref, ref)` (delega a `delegate.trigger_pipeline(ref)`; registra `(ref, sha)` en cache de idempotencia).
- `api/ci.py` — **blueprint nuevo** con endpoint `POST /<project>/trigger`.
- `app.py` — registrar el blueprint `ci_bp` (gated por flag: si `STACKY_PIPELINE_TRIGGER_ENABLED=false`, el blueprint NO se registra → 404).
- `config.py` — `STACKY_PIPELINE_TRIGGER_ENABLED: bool = False`.
- `harness_defaults.env` — `STACKY_PIPELINE_TRIGGER_ENABLED=false`.

**Símbolos exactos F2 (endpoint con HITL absoluto):**

```python
# api/ci.py
@bp.post("/<project>/trigger")
def trigger_pipeline_route(project: str):
    if not config.STACKY_PIPELINE_TRIGGER_ENABLED:
        abort(404)   # flag OFF = ruta inexistente
    body = request.get_json(silent=True) or {}
    confirm = body.get("confirm") is True
    if not confirm:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400   # RIEL ABSOLUTO
    ref = body.get("ref") or ""
    try:
        kind, ref_value = normalize_ref(ref)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    provider = get_ci_provider(project)
    scopes = _read_pat_scopes(provider)   # helper que lee scopes del client_profile
    ok, msg = validate_trigger_credentials(provider.name, scopes)
    if not ok:
        return jsonify({"error": msg}), 400

    item_ref = ItemRef(item_id=str(body.get("item_id","")), tracker_type=provider.name, ref=ref_value)
    recent = _recent_triggers(provider.name, ref_value)   # lee cache idempotencia
    fire, existing = should_trigger(ref_value, body.get("sha",""), recent, window_seconds=60)
    if not fire:
        return jsonify({"pipeline_id": existing, "message": "idempotency: pipeline reciente reusado", "status": "reused"})
    result = provider.trigger_pipeline(item_ref, ref_value)
    _record_trigger(provider.name, ref_value, result.get("sha",""), result["id"])
    return jsonify(result)
```

**Tests F2 (TDD, HITL crítico):**
- Archivo: `backend/tests/test_plan72_trigger_endpoint.py`.
- Casos:
  1. Flag OFF → `POST /<project>/trigger` retorna **404** (ruta no registrada).
  2. Flag ON + body sin `confirm` → **400** con `"confirm=True requerido"`. **[RIEL ABSOLUTO — test VP-01]**
  3. Flag ON + `confirm=True` + `ref="develop"` + scopes válidos + sin trigger reciente → llama `provider.trigger_pipeline` **[Patrón mock: assert_called]**; response 200 con `pipeline_id`.
  4. Flag ON + scopes inválidos (`read_api` sin `api`) → **400** con mensaje que incluye `"api"`.
  5. Flag ON + `ref` vacío → 400 (ValueError propagado como 400).
  6. Idempotencia: segundo trigger con mismo `(ref, sha)` en ventana → response 200 `"status":"reused"`, NO llama `provider.trigger_pipeline` **[mock: assert_called_once en suite, o assert_not_called en 2da]**.
  7. Flag ON + provider lanza `TrackerApiError(403)` → response 403 con mensaje.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_trigger_endpoint.py -q`.

**Criterio binario F2:** los 7 casos pasan. **Caso 2 es el gate de significancia del HITL** — sin él, el trigger sería autónomo.

**Impacto por runtime:** ninguno (capa API/UI).

**Flag F2:** `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**, `env_only=False` (UI HarnessFlagsPanel, categoría "Pipelines / CI").

**Trabajo del operador F2:** ninguno (default OFF). Para usar: prender flag + confirmar PAT con scope `api` + clic explícito en modal.

---

### F3 — `AdoCIProvider.trigger_pipeline` (fuera de scope v1, declaración explícita)

**Objetivo:** declarar `AdoCIProvider.trigger_pipeline` como `NotImplementedError` con mensaje accionable. ADO trigger requiere REST de Azure Pipelines con scopes separados y no aporta valor sobre el flujo ADO existente (los pipelines ADO se disparan por CI push, no por API cómoda).

**Archivos exactos F3:**
- `services/ado_ci_provider.py` — `trigger_pipeline(self, item_ref, ref)` lanza `NotImplementedError("trigger_pipeline ADO fuera de scope v1 — usar push o Azure Pipelines REST directo")`.

**Tests F3:**
- Archivo: `backend/tests/test_plan72_ado_trigger_not_implemented.py`.
- Casos:
  1. `AdoCIProvider().trigger_pipeline(ItemRef(...), "main")` lanza `NotImplementedError` con mensaje que incluye `"v1"`.
  2. El endpoint `POST /api/ci/<proj-ado>/trigger` con `confirm=True` captura el `NotImplementedError` → response 501 con mensaje accionable.
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_ado_trigger_not_implemented.py -q`.

**Criterio binario F3:** los 2 casos pasan; ADO no se rompe (flag OFF = 404; flag ON + ADO = 501 claro).

**Trabajo del operador F3:** ninguno.

---

### F4 — UI: botón "Disparar pipeline" con modal HITL

**Objetivo:** card del ítem con botón que abre modal de confirmación (muestra `ref` + `project` + warning "Esto dispara un pipeline real en GitLab") y, al confirmar, llama al endpoint con `confirm=True`.

**Archivos exactos F4:**
- `frontend/src/components/PipelineTriggerCard.tsx` — **nuevo**.
- `frontend/src/pages/DiagnosticsPage.tsx` o donde aplique — integrar la card.
- `frontend/src/api.ts` (o equivalente) — `triggerPipeline(project, ref, itemId, confirm)` → `POST /api/ci/<project>/trigger`.

**Símbolos exactos F4:**
- `<PipelineTriggerCard project itemId ref />` — renderiza botón deshabilitado si flag OFF (lo detecta vía `GET /api/ci/flags` o config global), modal con texto `"Vas a disparar un pipeline en <project> sobre <ref>. Confirmar."` y botón `"Disparar"`.
- El modal setea `confirm: true` sólo al clic explícito.

**Tests F4:**
- Archivo: `frontend/src/components/__tests__/PipelineTriggerCard.test.tsx` (vitest si está disponible; si no, test manual documentado).
- Casos:
  1. Flag OFF → botón deshabilitado con tooltip.
  2. Click botón → abre modal con `ref` y `project`.
  3. Click "Disparar" en modal → llama `triggerPipeline(..., confirm=true)`; NO llama sin confirm.
  4. Response `status:"reused"` → toast informativo (no error).
  5. Response 403/400 → toast de error con mensaje del server.
- Comando (si vitest): `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\frontend"; npx vitest run src/components/__tests__/PipelineTriggerCard.test.tsx`. Si vitest no instalado (ver memoria `stacky-backend-dev-test-env`), `npx tsc --noEmit` y dejar test manual como checklist.

**Criterio binario F4:** `tsc --noEmit` 0 errores; los 5 casos pasan (o checklist manual firmado si vitest no disponible).

**Impacto por runtime:** ninguno (UI; sólo expedida al operador).

**Trabajo del operador F4:** opt-in (default OFF); para usar, debe prender flag y confirmar PAT scope `api`.

---

### F5 — Monitoreo: polling del status con cancelación + ratchet

**Objetivo:** tras trigger, la UI hace polling de `monitor_pipeline` (vía `GET /api/ci/<project>/pipeline/<id>`) con backoff y cancelación al cerrar la card.

**Archivos exactos F5:**
- `api/ci.py` — endpoint `GET /<project>/pipeline/<pipeline_id>` que llama `provider.monitor_pipeline(pipeline_id)`.
- `frontend/src/components/PipelineTriggerCard.tsx` — tras trigger, polling cada 5s (backoff a 15s tras 3 intentos) hasta status terminal (`success`/`failed`/`canceled`); cancela al desmontar.

**Tests F5:**
- Archivo: `backend/tests/test_plan72_monitor_endpoint.py`.
- Casos:
  1. `GET /<project>/pipeline/<id>` con flag ON → llama `provider.monitor_pipeline` **[Patrón mock]**; response con `status`, `web_url`.
  2. Flag OFF → 404.
  3. `AdoCIProvider.monitor_pipeline` lanza `NotImplementedError` → endpoint 501.
  4. Cap de concurrencia: 429 si ya hay N (default 5) polls activos para el mismo pipeline (prevenir N+1 sobre GitLab).
- Comando: `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest tests/test_plan72_monitor_endpoint.py -q`.

**Ratchet F5:** registrar TODOS los `test_plan72_*.py` en `HARNESS_TEST_FILES` (sh + ps1) del Plan 49.

**Criterio binario F5:** los 4 casos pasan; ratchet verde; flag aparece en `harness_defaults.env` y UI.

**Trabajo del operador F5:** ninguno.

---

## 5. Riesgos y mitigaciones

1. **Trigger silencioso fallido por scope** (R1 boceto). **Mitigación:** F0 valida `api` scope con `validate_trigger_credentials`; F2 caso 4 afirma el 400 con mensaje. No se descubre en runtime.
2. **Pipelines duplicados** (R2). **Mitigación:** `should_trigger` (F0) idempotencia por `(ref, sha)` en ventana 60s; F2 caso 6 afirma `"status":"reused"` y `assert_not_called` en 2da llamada.
3. **Polling sobrecarga GitLab** (R3). **Mitigación:** F5 backoff 5s→15s + cancelación al desmontar + cap 429 si >5 polls activos.
4. **Trigger autónomo sin HITL** (R4 — el más crítico). **Mitigación:** endpoint exige `confirm=True`; F2 caso 2 es **gate de significancia**. Sin `confirm`, 400. Riel absoluto.
5. **ADO trigger fuera de scope v1.** **Mitigación:** F3 lo declara `NotImplementedError` y el endpoint retorna 501 claro (no 500 silencioso).
6. **3 runtimes.** **Mitigación:** el plan no toca prompts/runtime del agente.

---

## 6. Fuera de scope

- **NO** generar pipelines YAML declarativos (Plan 73).
- **NO** migración ADO→GitLab (Plan 74).
- **NO** deep links visuales (Plan 75) — se reusa `web_url` devuelta pero la composición visual profunda es del 75.
- **NO** trigger de ADO por API (v1; requiere REST de Azure Pipelines con scopes separados; fuera de scope).
- **NO** `retry_pipeline` (se hace después de v1 si hay demanda).
- **NO** tocar el sub-puerto más allá de `trigger_pipeline` (es la única extensión del bloque 70-76).

---

## 7. Glosario

- **CIProvider:** sub-puerto (`services/ci_provider.py`, creado en Plan 71 F1). En este plan se extiende con `trigger_pipeline` y se implementa `monitor_pipeline`. `CI_PORT_METHODS = ("infer_item_pipeline","monitor_pipeline","trigger_pipeline")` tras F1.
- **`trigger_pipeline(item_ref, ref)`:** método del sub-puerto; dispara pipeline sobre `ref`. Requiere HITL en el endpoint.
- **`monitor_pipeline(pipeline_id)`:** método del sub-puerto; GET estado del pipeline.
- **HITL absoluto:** riel que exige `confirm=True` explícito del operador para cualquier trigger.
- **`validate_trigger_credentials` / `normalize_ref` / `should_trigger`:** funciones PURAS de `services/ci_trigger_rules.py` (F0).
- **`REQUIRED_SCOPES`:** dict `{tracker_type: set(scopes)}`; GitLab requiere `{"api"}`.
- **`STACKY_PIPELINE_TRIGGER_ENABLED`:** flag nueva de este plan (default OFF, editable por UI).
- **Idempotencia:** `(ref, sha)` no se dispara 2x en ventana de 60s; el segundo retorna `pipeline_id` existente.

---

## 8. Orden de implementación

1. **F0** — Funciones puras `ci_trigger_rules.py` + tabla de scopes.
2. **F1** — Extensión `CIProvider` con `trigger_pipeline`; implementación `monitor_pipeline` en adapters; métodos `trigger_pipeline`/`poll_pipeline` en `gitlab_provider.py`.
3. **F2** — Adapter `GitLabCIProvider.trigger_pipeline` + endpoint `POST /api/ci/<project>/trigger` con HITL + idempotencia + flag.
4. **F3** — `AdoCIProvider.trigger_pipeline` = `NotImplementedError` (501 claro).
5. **F4** — UI `PipelineTriggerCard` con modal HITL.
6. **F5** — Endpoint `GET /<project>/pipeline/<id>` + polling UI + ratchet.

Cada fase deja el sistema verde y backward-compatible.

---

## 9. DoD global (Definition of Done)

- [ ] **(a)** Funciones puras `validate_trigger_credentials`, `normalize_ref`, `should_trigger` implementadas y testeadas (F0, 9 casos).
- [ ] **(b)** `CIProvider` extendido con `trigger_pipeline`; `monitor_pipeline` implementado en GitLab adapter (F1).
- [ ] **(c)** Endpoint `POST /api/ci/<project>/trigger` rechaza sin `confirm=True` con 400 (F2 caso 2 — **gate HITL**).
- [ ] **(d)** Idempotencia por `(ref, sha)` en ventana 60s afirmada (F2 caso 6).
- [ ] **(e)** Validación de PAT scope `api` antes del trigger (F2 caso 4).
- [ ] **(f)** Flag `STACKY_PIPELINE_TRIGGER_ENABLED` default **OFF**; flag OFF → 404 (ruta no registrada).
- [ ] **(g)** ADO trigger devuelve 501 claro (`NotImplementedError`, F3).
- [ ] **(h)** UI `PipelineTriggerCard` con modal HITL; `tsc --noEmit` 0 errores.
- [ ] **(i)** Monitoreo con polling + backoff + cancelación + cap 429 (F5).
- [ ] **(j)** Los 3 runtimes operativos sin cambios.
- [ ] **(k)** Ratchet verde (Plan 49 F4) con los archivos `test_plan72_*.py` registrados.

---

## 10. Notas de implementación (para el modelo menor que ejecuta esto)

- **Venv:** `cd "N:\GIT\RS\STACKY\Stacky\Stacky Agents\backend"; .\.venv\Scripts\python.exe -m pytest <test> -q`.
- **Patrón mock (FIX C4):** `mock_provider.return_value = Mock(name="gitlab")`; `mock_provider.trigger_pipeline.assert_called_once_with(ItemRef(...), ref_value)`. Para afirmar NO-autónomo: `mock_provider.trigger_pipeline.assert_not_called()` cuando `confirm` falta.
- **Mock pattern DB:** importar `db` a nivel módulo; parchear lazy-imports en el módulo origen (memoria `plan-28-lifecycle`).
- **Blueprint registration gated por flag:** registrar `ci_bp` en `app.py` dentro de `if config.STACKY_PIPELINE_TRIGGER_ENABLED:` para que flag OFF = 404 (no 403 ni 405).
- **Cada commit deja el sistema verde y backward-compatible.**
- **Falsos verdes prohibidos:** el test F2 caso 2 (HITL gate) DEBE afirmar 400 sin `confirm`; si pasara sin el chequeo, el riel se rompe.
- **Si una fase revela un GAP no listado**, detener y actualizar este doc.
