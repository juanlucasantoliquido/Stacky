# Plan 149 — Robustez de intake de artefactos + excepciones tipadas en endpoints

- **Estado:** IMPLEMENTADO F0..F7 (2026-07-16, commit 5d091726) · CRITICADO v1→v2 previo: APROBADO-CON-CAMBIOS
- **Fecha:** 2026-07-15 (v1) · 2026-07-15 (v2, juez adversarial)
- **Autor:** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8)
- **Serie:** 144–149 (derivada de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`).
- **Cierra:** **D5** (`pending-task.json` inválido: intake rechaza el artefacto → la Task no se crea) + **V6** (excepciones no manejadas en endpoints reales: `devops/console/*`, `agents/run`, `harness-flags`, `create-child-task`, `ci/failure-webhook`).
- **Cluster:** "robustez server-side ante entrada malformada y errores no atrapados". Ambos hallazgos convierten **fallos silenciosos** (task fantasma / 500 mudo) en **estados tipados, superficiados y recuperables** sin sacar al operador del lazo.

### CHANGELOG v1 → v2 (juez adversarial)

Anchors re-verificados contra working tree (todos `[V]` correctos): `app.py:508` handler, `artifact_intake.py:33/50/74` (`IntakeResult`/`validate_and_normalize`/`_intake_pending_task`), `output_watcher.py:845` (`key = str(pt_file)`), `tickets.py:2420/2575/3864` (`_scan_pending_tasks_for_epic`/`unblocker_board`/`create-child-task`), `tickets.py:282` (`_request_project_name` **sí** lee `body["project"]`), `harness_flags.py:225/234/679`, `test_harness_flags.py:467/628/700`.

- **C1 (BLOQUEANTE de espíritu, resuelto):** F1 logueaba TODA `StackyApiError` a nivel WARNING **sin traceback**, y F2 envolvía crashes genéricos (`except Exception → UpstreamError`) → un **bug real** en `run_remote`/dispatch se convertía en un 502/500 "esperado" WARNING sin traceback = error mudo (choca con Plan 135). **Fix:** el handler ahora discrimina por status: 5xx `StackyApiError` (Internal/Upstream/IntegrationUnavailable) se loguea a **ERROR con `exc=`** (traceback preservado vía `__cause__`); solo 4xx (validation/not_found/conflict) van a WARNING. F2 restringe el `except` a excepciones de transporte esperadas; los bugs genéricos **propagan** a la rama no-tipada (traceback intacto).
- **C2 (backward-compat, resuelto):** el envelope ponía `error = error_type` → cambiaba la SEMÁNTICA de la clave `.error` (hoy = mensaje humano `"Internal server error"`, pasaba a token `"internal"`), rompiendo cualquier UI que muestre `.error`. **Fix:** `.error` = **mensaje** (idéntico al legacy); el token va SOLO en `.error_type`. Ahora flag ON es superset puro (nunca cambia el significado de un campo existente) y ON/OFF son consistentes.
- **C3 (correctitud F5, resuelto):** F5 poppeaba `_SEEN_TERMINAL_PENDING` con `str((repo_root/rel).resolve())`, que en Windows puede divergir de cómo el watcher guardó la clave (`str(pt_file)` sin `.resolve()`) → pop silencioso no-op (verde en test, incorrecto en prod). **Fix:** nuevo helper público `output_watcher.clear_quarantine(pt_file)` que deriva la clave **idéntico** a `_quarantine_pending_once`; F5 lo llama (no toca el dict privado).
- **C4 (reuso, documentado):** coexistencia con la jerarquía existente `AdoApiError` + `_ado_sync_error_response` (`tickets.py:293`) documentada en §6: `StackyApiError` es la capa de **transporte** (handler transversal); `AdoApiError` sigue siendo de **dominio ADO** y se atrapa localmente ANTES del handler. No convergen en 149.
- **C5 (colisión de serie, mitigado):** R13 explicita los anchors compartidos (`harness_flags.py`, `config.py`, `test_harness_flags.py:467`) que 145/146/148 también editan → implementar en serie, no en paralelo.
- **C6 (ambigüedad para modelo menor, resuelto):** anchor `agents.py:339` re-marcado `[INF]` (el implementador debe localizar el sitio de dispatch por grep, no confiar en la línea); el test de dispatch declara el payload mínimo válido.
- **C7 / C8 (higiene):** F5 documenta que el frontend debe surfacear `create_child_task.ok`/errors (no solo el status HTTP); `_classify_json_failure` se promueve a símbolo público `classify_json_failure` (contrato compartido intake↔validador).
- **[ADICIÓN ARQUITECTO] F7:** endpoint diag read-only `GET /api/diag/intake-quarantine` que expone `quarantine_snapshot()` GLOBAL — cierra un gap real de F4 (el board es epic-scoped: un `pending-task.json` en cuarentena cuyo Epic no resuelve queda invisible incluso tras F4) y deja el gancho para el Centro de Notificaciones (Plan 152).

---

## 1. Objetivo + KPI/impacto

Endurecer dos superficies server-side donde hoy los fallos son **mudos**:

1. **D5 — Intake de `pending-task.json` (mejora b + c, y refuerzo de a).** Cuando el agente escribe un `pending-task.json` inválido (JSON vacío/truncado → `Expecting value`), el `output_watcher` lo **pone en cuarentena silenciosa** (`_quarantine_pending_once`, `services/output_watcher.py:845`) y la Task nunca se crea. El operador ve "el run no hizo nada". Este plan: (b) **clasifica** la causa exacta del fallo de intake (`empty` / `truncated` / `malformed`) con mensaje accionable; (c) **superficia** el archivo en cuarentena en el board "Desatascador" existente con esa causa exacta y agrega un botón **1-click "Re-procesar"** (human-in-the-loop); y refuerza (a) el hook pre-escritura de Claude que **ya existe** (F1.4) para que el feedback inline al agente use la misma clasificación.

2. **V6 — Excepciones no manejadas en endpoints.** Hoy existe un handler transversal (`@app.errorhandler(Exception)`, `app.py:508`) que loguea y devuelve `{"error": "Internal server error"}, 500` **mudo** (sin tipo, sin `exec_id`, sin discriminación por endpoint). Este plan introduce un **contrato de errores tipados** (`StackyApiError` + envelope `{ok, error, error_type, message, request_id, exec_id, endpoint, method}`), **enriquece** el handler transversal para emitir ese envelope (4xx/5xx tipado, nunca 500 mudo) correlacionado por `request_id`/`exec_id`, e **instrumenta** los endpoints prioritarios (`devops/console/*`, `agents/run`) para levantar errores tipados en sus fallos conocidos.

**KPIs / impacto esperado:**

| Métrica | Antes (evidencia reporte §3 D5 / §4 V6) | Después (objetivo) |
|---|---|---|
| `pending-task.json` inválido → Task no creada, sin señal en UI | 1 ERROR + 2 WARNING/incidente, cuarentena invisible | Archivo visible en Desatascador con causa exacta + botón "Re-procesar"; 0 tasks fantasma silenciosas |
| Mensaje de intake vs. mensaje del board | divergentes (board usa `json.loads` plano; intake usa reparador) | idénticos (board enruta por `artifact_intake`), `reason_code` estable |
| `500 mudo` en `devops/console/*` + `agents/run` | 6+4+4 unhandled con `{"error":"Internal server error"}` | envelope tipado con `error_type` + `exec_id` correlacionado; 0 respuestas sin tipo |
| Correlación traceback ↔ respuesta | manual (buscar el traceback siguiente) | `request_id` (ya existe) + `exec_id` en el envelope y en el log estructurado |

**Estos KPIs NO agregan trabajo al operador.** El intake y el envelope son automáticos; el único elemento manual es el botón "Re-procesar" (opt-in, ya alineado con el flujo Desatascador existente).

---

## 2. Por qué ahora / gap que cierra

- El patrón "**crea archivos pero no la task**" es un incidente recurrente documentado en memoria del ecosistema (mismatch ordinal vs. ADO id + JSON inválido). D5 es su manifestación por **JSON vacío/truncado**: el reparador de intake (`_intake_pending_task`, `artifact_intake.py:74`) prueba BOM/fences/objeto balanceado/comillas/comas, pero contra un archivo **vacío o truncado** no hay nada que reparar → `Expecting value` → cuarentena. Hoy esa cuarentena **no tiene salida en la UI**: el operador no ve qué archivo falló ni por qué, ni tiene forma de re-disparar el intake sin tocar el mtime a mano.
- V6: el handler transversal existe pero es **genérico**. Un 500 mudo no le dice al frontend si el fallo fue de validación (reintentable con otro input), de integración caída (503, reintentar luego) o un bug real (500). Y no lleva `exec_id`, así que el traceback y la respuesta viven separados. Esto degrada DX y observabilidad, y choca con el riel "cero errores mudos" de la serie 134-136.
- **Momento:** la serie 144-149 ataca en bloque los hallazgos de la auditoría. 149 es el cierre del cluster "robustez de entrada". No bloquea a nadie (ver §Orden), y reusa infraestructura ya presente (intake, desatascador, handler transversal, `stacky_logger`).

---

## 3. Principios y guardarraíles (codificados por fase)

1. **Paridad de 3 runtimes.** D5 (intake + board + re-intake) y V6 (capa HTTP) son **runtime-agnósticos**: aplican idénticos a Codex CLI, Claude Code CLI y GitHub Copilot Pro, porque operan sobre archivos file-based y sobre la capa Flask, no sobre el runner. La **única** pieza runtime-específica es el refuerzo (a) del hook pre-escritura, que **ya existe solo para Claude** (`claude_cli_hooks.py`, PostToolUse); Codex/Copilot **degradan** a la defensa file-based (F3+F4+F5). Cada fase declara su impacto por runtime.
2. **Cero trabajo extra al operador.** Todo automático o kill-switch default ON. El botón "Re-procesar" es opt-in dentro de un flujo (Desatascador) que ya existe y ya tiene botones equivalentes ("Crear Tasks", "Recrear Task borrada"). No dispara ninguna de las 4 excepciones duras: no bypasea revisión humana, no es destructivo/irreversible, no requiere prerequisito nuevo, no reduce seguridad.
3. **Human-in-the-loop.** El re-intake lo **dispara el operador** desde el board; Stacky nunca reintenta autónomamente un archivo que ya está en cuarentena estructural (esa es justamente la protección anti-loop de `_quarantine_pending_once`). Amplificamos, no reemplazamos.
4. **Mono-operador sin auth.** Nada de RBAC. El endpoint de re-intake usa `current_user()` solo para auditoría (header sin validar), igual que el resto.
5. **No degradar performance/seguridad/estabilidad/DX; backward-compatible.** El envelope tipado y el ruteo del board por intake van detrás de kill-switches default ON: con el switch OFF el comportamiento es **byte-idéntico** al actual. El envelope **conserva** la clave `"error"` para no romper consumidores del frontend que la leen hoy.

---

## 4. Fases

Convención de confianza en anchors: `[V]` verificado contra el working tree hoy · `[INF]` inferido · `[NV]` no verificable.

**Comando base de tests (venv real verificado):** desde la raíz del repo
`N:\GIT\RS\STACKY\Stacky\Stacky Agents`:

```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_XXX.py -q
```

> Correr **por archivo** (la suite completa contamina cross-file). `backend/.venv/Scripts/python.exe` existe y es py3.13 `[V]`.

---

### F0 — Contrato de errores tipados (`StackyApiError`) + kill-switch (fundacional V6)

**Objetivo:** crear la taxonomía de errores tipados y el helper de envelope que consumirán el handler transversal (F1) y los endpoints (F2, F5). **Valor:** una sola fuente de verdad para "cómo se ve un error de la API".

**Archivos:**
- CREAR `backend/api/errors.py`.
- EDITAR `backend/services/harness_flags.py` (FlagSpec nuevo).
- EDITAR `backend/config.py` (default runtime del flag).
- EDITAR `backend/tests/test_harness_flags.py` (`_CURATED_DEFAULTS_ON`).
- CREAR `backend/tests/test_plan149_typed_errors.py` (TDD).
- CREAR `backend/tests/test_plan149_flags.py` (TDD flags).

**`backend/api/errors.py` — contenido exacto (pseudocódigo fiel):**

```python
"""Plan 149 — Taxonomía de errores tipados de la API + envelope canónico."""
from __future__ import annotations
from flask import g

class StackyApiError(Exception):
    http_status: int = 500
    error_type: str = "internal"
    def __init__(self, message: str, *, http_status: int | None = None,
                 error_type: str | None = None, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        if http_status is not None: self.http_status = http_status
        if error_type is not None: self.error_type = error_type
        self.details = details or {}

class ValidationError(StackyApiError):        http_status = 422; error_type = "validation"
class ResourceNotFoundError(StackyApiError):  http_status = 404; error_type = "not_found"
class ConflictError(StackyApiError):          http_status = 409; error_type = "conflict"
class UpstreamError(StackyApiError):          http_status = 502; error_type = "upstream"
class IntegrationUnavailableError(StackyApiError): http_status = 503; error_type = "integration_unavailable"
class InternalError(StackyApiError):          http_status = 500; error_type = "internal"

def set_exec_id(exec_id) -> None:
    """Correlación: el endpoint la llama cuando conoce su execution_id.

    Defensivo: fuera de un request context (g inaccesible) es un no-op silencioso
    (C6): el asignar g.exec_id fuera de contexto lanza RuntimeError, que atrapamos.
    """
    try:
        g.exec_id = int(exec_id) if exec_id is not None else None
    except Exception:
        try: g.exec_id = None
        except Exception: pass  # sin request context → no-op

def build_error_envelope(*, error_type: str, message: str, request_id: str,
                         exec_id, endpoint: str, method: str,
                         details: dict | None = None) -> dict:
    # C2 BACKWARD-COMPAT: la clave `.error` CONSERVA la semántica legacy = mensaje
    # humano (hoy los consumidores que la muestran esperan un string legible como
    # "Internal server error"). El TOKEN de máquina va SOLO en `.error_type` (nuevo).
    # Así flag ON es superset puro: nunca cambia el significado de un campo existente.
    env = {
        "ok": False,
        "error": message,           # legacy: mensaje humano (idéntico a la forma OFF)
        "error_type": error_type,   # nuevo, explícito (token estable de máquina)
        "message": message,         # alias explícito de .error para consumidores nuevos
        "request_id": request_id or "",
        "exec_id": exec_id,
        "endpoint": endpoint,
        "method": method,
    }
    if details: env["details"] = details
    return env
```

**Flag nuevo — patrón triple (los 3 puntos exactos):**
1. `backend/services/harness_flags.py` — nuevo `FlagSpec` (colocar junto al bloque V1.3 de intake, cerca de la línea 677):
   ```python
   FlagSpec(
       key="STACKY_TYPED_ERROR_ENVELOPE_ENABLED",
       type="bool",
       label="Envelope de errores tipado (API)",
       description=("Plan 149 — Si ON, los errores no atrapados se devuelven como "
                    "envelope tipado {error_type, message, request_id, exec_id} en vez "
                    "de un 500 mudo. OFF = respuesta legacy byte-idéntica."),
       group="global",
       env_only=True,
       default=True,
   ),
   ```
   y agregar la key a la tupla de categoría `"observabilidad_notif"` (`harness_flags.py:234`).
2. `backend/config.py` — junto al bloque de flags (p.ej. tras la línea 697):
   ```python
   STACKY_TYPED_ERROR_ENVELOPE_ENABLED: bool = os.getenv(
       "STACKY_TYPED_ERROR_ENVELOPE_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   ```
3. `backend/tests/test_harness_flags.py` — agregar `"STACKY_TYPED_ERROR_ENVELOPE_ENABLED",` al set `_CURATED_DEFAULTS_ON` (línea 467).

> **Gotcha obligatorio:** si falta cualquiera de los 3 puntos, se rompe `test_default_known_only_for_curated` (`test_harness_flags.py:700`). Si falta la categoría, se rompe `test_every_registry_flag_is_categorized` (`test_harness_flags.py:628`). `[V]`

**Tests PRIMERO — `backend/tests/test_plan149_typed_errors.py` (parte F0):**
- `test_stackyapierror_defaults` → `StackyApiError("x").http_status == 500 and .error_type == "internal"`.
- `test_validation_error_maps_422` → `ValidationError("bad").http_status == 422 and .error_type == "validation"`.
- `test_build_error_envelope_shape` → el dict tiene exactamente las claves `{ok, error, error_type, message, request_id, exec_id, endpoint, method}` y `ok is False` y `error == message` (C2: `.error` es el mensaje humano, NO el token).
- `test_envelope_conserves_error_key_semantics` (C2) → con `message="campo x", error_type="validation"` ⇒ `env["error"] == "campo x"` (mensaje humano, legacy) y `env["error_type"] == "validation"` (token nuevo). Afirma explícitamente que `.error != error_type` cuando el mensaje difiere del token — así no rompemos UIs que muestran `.error`.

**Tests PRIMERO — `backend/tests/test_plan149_flags.py`:**
- `test_typed_error_flag_registered_and_on` → la key aparece en el registry con `default is True`.
- `test_typed_error_flag_default_in_config` → `config.config.STACKY_TYPED_ERROR_ENVELOPE_ENABLED is True` en entorno limpio.
- (se amplía en F4 con el segundo flag).

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_typed_errors.py backend/tests/test_plan149_flags.py backend/tests/test_harness_flags.py -q
```

**Criterio de aceptación binario:** los 3 archivos de test pasan; `test_default_known_only_for_curated` y `test_every_registry_flag_is_categorized` verdes.

**Flag que la protege:** `STACKY_TYPED_ERROR_ENVELOPE_ENABLED` (default ON, kill-switch env-only). El módulo `errors.py` es inerte hasta que F1 lo cablee.

**Impacto por runtime:** N/A (capa HTTP, idéntico a los 3). **Fallback:** con flag OFF, nada usa el envelope.

**Trabajo del operador: ninguno.**

---

### F1 — Enriquecer el handler transversal para emitir el envelope tipado (V6)

**Objetivo:** que `@app.errorhandler(Exception)` mapee `StackyApiError` a su status+envelope y convierta el 500 mudo genérico en un 500 **tipado y correlacionado**, sin tragarse el traceback. **Valor:** cero errores mudos en TODA la API, no solo en los endpoints instrumentados.

**Anchor `[V]` — estado ACTUAL (`backend/app.py:508-528`):**
```python
@app.errorhandler(Exception)
def _handle_unhandled_error(exc: Exception):
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return exc
    stacky_logger.error("http.middleware", "unhandled_exception", exc=exc,
        endpoint=request.path, method=request.method,
        user=request.headers.get("X-User-Email", "anonymous"),
        tags=["http", "unhandled_exception"])
    logger.exception("unhandled exception in %s %s", request.method, request.path)
    return jsonify({"error": "Internal server error", "request_id": g.get("request_id", "")}), 500
```

> **DISCREPANCIA con el anchor del reporte:** V6 sugiere "considera un handler transversal (error middleware) que capture, correlacione y tipifique" — pero **ese handler YA EXISTE**. Este plan lo **enriquece**, NO crea uno nuevo. Reportado en `anchorDiscrepancies`.

**Archivos:** EDITAR `backend/app.py` (el handler de la línea 508). Import de `api.errors` (lazy dentro del handler, para no acoplar el import top-level de app.py).

**Diff ilustrativo (reemplazo del cuerpo del handler):**
```python
@app.errorhandler(Exception)
def _handle_unhandled_error(exc: Exception):
    from werkzeug.exceptions import HTTPException
    if isinstance(exc, HTTPException):
        return exc  # 4xx/5xx de abort() → Flask los maneja (sin cambio)

    from api.errors import StackyApiError, build_error_envelope
    import config as _config
    typed_on = getattr(_config.config, "STACKY_TYPED_ERROR_ENVELOPE_ENABLED", True)
    rid = g.get("request_id", "")
    exec_id = g.get("exec_id")  # F2 lo setea; None si el endpoint no lo declaró
    endpoint, method = request.path, request.method
    user = request.headers.get("X-User-Email", "anonymous")

    if isinstance(exc, StackyApiError):
        # C1 — Discriminar por severidad, NO por "es tipado":
        #   • 4xx (validation/not_found/conflict) = error de CLIENTE esperado → WARNING sin traceback.
        #   • 5xx (internal/upstream/integration_unavailable) = bug o fallo real de
        #     dependencia que ops DEBE ver con detalle → ERROR con exc= (traceback vía __cause__).
        # Sin esto, un bug envuelto en InternalError/UpstreamError quedaría mudo (Plan 135).
        if exc.http_status >= 500:
            stacky_logger.error("http.middleware", "typed_api_error", exc=exc,
                error_type=exc.error_type, endpoint=endpoint, method=method,
                user=user, exec_id=exec_id, request_id=rid,
                tags=["http", "typed_error", exc.error_type])
            logger.exception("typed 5xx in %s %s [type=%s exec_id=%s]",
                method, endpoint, exc.error_type, exec_id)
        else:
            stacky_logger.warning("http.middleware", "typed_api_error",
                error_type=exc.error_type, endpoint=endpoint, method=method,
                user=user, exec_id=exec_id, request_id=rid,
                tags=["http", "typed_error", exc.error_type])
        if not typed_on:
            return jsonify({"error": exc.message, "request_id": rid}), exc.http_status
        env = build_error_envelope(error_type=exc.error_type, message=exc.message,
            request_id=rid, exec_id=exec_id, endpoint=endpoint, method=method,
            details=exc.details)
        return jsonify(env), exc.http_status

    # Excepción NO tipada: es un bug → mantener traceback completo (no tragarlo).
    stacky_logger.error("http.middleware", "unhandled_exception", exc=exc,
        endpoint=endpoint, method=method, user=user, exec_id=exec_id,
        request_id=rid, tags=["http", "unhandled_exception"])
    logger.exception("unhandled exception in %s %s [exec_id=%s]", method, endpoint, exec_id)
    if not typed_on:
        return jsonify({"error": "Internal server error", "request_id": rid}), 500
    env = build_error_envelope(error_type="internal", message="Internal server error",
        request_id=rid, exec_id=exec_id, endpoint=endpoint, method=method)
    return jsonify(env), 500
```

Casos borde:
- `HTTPException` (abort(400/404/…)) → passthrough intacto (no lo tipamos; ya es HTTP explícito). **No romper** el contrato existente de esos endpoints.
- `g.exec_id` ausente → `exec_id: null` en el envelope (correcto, no todos los requests tienen execution).
- Flag OFF → forma legacy exacta (`{"error": ..., "request_id": ...}`), backward-compat total.
- **C1 — 5xx tipado NUNCA es mudo:** `InternalError`/`UpstreamError`/`IntegrationUnavailableError` se loguean a ERROR con traceback; el `raise ... from exc` de F2 preserva la causa original en `__cause__`. Solo los 4xx (cliente) van a WARNING.
- **C2 — `.error` = mensaje humano** (idéntico a la forma OFF): un consumidor que hoy hace `alert(resp.error)` sigue viendo un string legible, no un token.
- El `stacky_logger` acepta `**kwargs` arbitrarios (`_emit`), así que `exec_id=`/`request_id=` no rompen su firma `[V]` (`services/stacky_logger.py:190`); el call actual (`app.py:518`) ya pasa `endpoint=/method=/user=/tags=` como kwargs.

**Tests PRIMERO — `backend/tests/test_plan149_typed_errors.py` (parte F1):**
Usar el `app` de test (patrón de `conftest`/`create_app`) y registrar rutas efímeras que lancen cada caso. Casos:
- `test_handler_maps_stackyapierror` → una ruta que hace `raise ValidationError("campo x")` responde 422 con `body["error_type"] == "validation"` y `body["message"] == "campo x"` y `body["error"] == "campo x"` (C2: `.error` = mensaje) y `body["ok"] is False`.
- `test_handler_typed_500_for_generic_exception` → una ruta que hace `raise RuntimeError("boom")` responde 500 con `body["error_type"] == "internal"` y `body["message"] == "Internal server error"` y `body["error"] == "Internal server error"` y `"request_id" in body`.
- `test_handler_5xx_logs_at_error_with_traceback` (C1) → ruta que hace `raise UpstreamError("db caída")`; capturar logs (`caplog` a nivel ERROR sobre `services.stacky_logger`/`logger`) y afirmar que se emitió un registro **ERROR** (no WARNING) para el 502. Contra-caso: `raise ValidationError("x")` NO produce un ERROR (solo WARNING). Blindaje anti-mudo de 5xx.
- `test_handler_includes_exec_id_when_set` → ruta que llama `set_exec_id(77)` y luego `raise UpstreamError("x")` → `body["exec_id"] == 77`.
- `test_handler_legacy_shape_when_flag_off` (monkeypatch `config.config.STACKY_TYPED_ERROR_ENVELOPE_ENABLED=False`) → body == `{"error": ..., "request_id": ...}` sin `error_type`; y `body["error"]` es el mensaje (idéntico a lo que devuelve el envelope ON en `.error`, C2).
- `test_http_exception_passthrough` → ruta que hace `abort(404)` sigue devolviendo el 404 de Flask, NO el envelope.

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_typed_errors.py -q
```

**Criterio de aceptación binario:** los 6 tests de F1 pasan; con flag OFF la forma es legacy; `abort()` sigue intacto; los 5xx tipados se loguean a ERROR con traceback (C1) y los 4xx a WARNING.

**Flag:** `STACKY_TYPED_ERROR_ENVELOPE_ENABLED` (default ON).

**Impacto por runtime:** N/A (capa HTTP). **Fallback:** flag OFF → handler legacy.

**Trabajo del operador: ninguno.**

---

### F2 — Instrumentar endpoints objetivo (V6): `devops/console/*`, `agents/run`, y correlación `exec_id`

**Objetivo:** que los fallos **conocidos** de estos endpoints levanten errores tipados (no dicts ad-hoc ni excepciones crudas), y que declaren su `exec_id` para correlación. **Valor:** las respuestas de los endpoints más ruidosos del reporte (`devops/console/conversations` 6×, `devops/console/exec` 4×, `agents/run` 4×) pasan a ser tipadas y trazables.

**Archivos:**
- EDITAR `backend/api/devops_remote_console.py` (rutas `exec_route`, `create_conversation`, `list_conversations`, `conversation_message`).
- EDITAR `backend/api/agents.py` (ruta `run`; **`[INF]` la línea 339 es orientativa** — C6: el implementador localiza el sitio de dispatch con `grep -n "def run" backend/api/agents.py` y donde se obtiene el `execution_id`, NO confía en el número de línea).
- (Cobertura pasiva) `backend/api/tickets.py` `create-child-task` y `backend/api/ci.py` `failure-webhook`: **no** requieren edición explícita — quedan cubiertos por el 500 tipado de F1. Se listan en §5 como "cubiertos por el handler transversal".

**Regla C1 — NO enmascarar bugs.** Al envolver dispatch/`run_remote` en tipos, capturar **solo** las excepciones **esperadas** de transporte/dominio (conexión, timeout, tipos de error del propio servicio). Dejar que las excepciones **inesperadas** (bugs: `AttributeError`, `TypeError`, `KeyError`, etc.) **propaguen** a la rama no-tipada del handler (F1), que las loguea a ERROR con traceback. Un `except Exception` ancho reetiquetaría un bug como "upstream esperado" y lo degradaría a un log manejable — exactamente el fallo mudo que 149 combate.

**Cambios exactos:**

1. **`agents.py::run`** — tras crear/obtener la `AgentExecution`, declarar el exec_id:
   ```python
   from api.errors import set_exec_id
   # ...cuando ya se conoce el execution_id del dispatch:
   set_exec_id(execution_id)
   ```
   Y donde hoy hay ramas de fallo que **deberían** ser tipadas pero hoy no lo son, envolver la sección de dispatch capturando SOLO lo esperado (C1):
   ```python
   try:
       execution_id = _dispatch_run(...)   # el bloque actual de lanzamiento
   except (RuntimeError, ValueError) as exc:   # esperadas: config/estado inválido
       from api.errors import InternalError
       raise InternalError(f"fallo al lanzar el run: {exc}") from exc
   # NO agregar `except Exception`: un bug (p.ej. AttributeError) DEBE propagar
   # a F1 y loguearse a ERROR con traceback, no volverse un InternalError "esperado".
   ```
   > Los `return jsonify({...}), 400/409` **existentes** (`unknown_runtime`, `missing_vscode_agent_filename`, `duplicate_run`) se **conservan** — ya son explícitos y tipados a su manera. No se tocan (backward-compat).

2. **`devops_remote_console.py::exec_route`** — mapear los fallos **esperados** de `run_remote` a tipos claros, SIN tragarse los bugs (C1):
   ```python
   from api.errors import IntegrationUnavailableError, UpstreamError
   try:
       result = run_remote(alias, command, mode=mode, conversation_id=conversation_id,
                           user=current_user(), timeout_s=timeout_s)
   except (ConnectionError, TimeoutError, OSError) as exc:   # transporte esperado → 502 tipado
       raise UpstreamError(f"remote_exec inaccesible: {exc}") from exc
   # (si remote_exec define su propia excepción de dominio, añadirla a este tuple;
   #  cualquier OTRA excepción propaga a F1 → 500 ERROR con traceback, NO 502 mudo)
   if conversation_id:
       set_exec_id(conversation_id)   # correlación por conversación
   ```
   El mapeo `error_key → status` existente (403/404/503/501/504/502) se mantiene (ya es correcto); la captura acotada solo evita que un fallo **de transporte** previsto explote como 500 mudo, sin ocultar bugs reales.

3. **`devops_remote_console.py::create_conversation` / `conversation_message`** — declarar exec_id tras `_launch_turn`:
   ```python
   if launch_error is not None:
       return launch_error
   set_exec_id(execution_id)
   ```
   y envolver el bloque DB (`session_scope`) para que un fallo de persistencia sea `InternalError` correlacionado en vez de 500 mudo.

4. **`devops_remote_console.py::list_conversations`** — el `session_scope` de lectura: si falla, `InternalError`. (Es el endpoint con 6× unhandled; su causa `[NV]` es probablemente el query DB.)

Casos borde:
- No cambiar los `return jsonify({...}), 4xx` que ya validan input (obligatorios ausentes, runtime inválido). Solo tipar lo que hoy **explota** o cae al 502/500 genérico.
- `set_exec_id(None)` es seguro (helper tolera None).

**Tests PRIMERO — `backend/tests/test_plan149_typed_errors.py` (parte F2):**
- `test_agents_run_typed_error_on_dispatch_failure` (C1+C6) → monkeypatch del dispatcher para que lance `RuntimeError` (esperado); POST `/api/agents/run` con el **payload mínimo válido** (el implementador lo deriva de la ruta `run`: al menos `{"agent": <slug válido>, "runtime": <runtime válido>, "ado_id": <int>}` — grep del cuerpo de `run` para los campos obligatorios) → 500 con `error_type == "internal"` y `exec_id` presente (o null si no llegó a crearse).
- `test_agents_run_bug_propagates_untyped_500` (C1) → monkeypatch del dispatcher para que lance `AttributeError("bug")` (INESPERADO) → 500 con `error_type == "internal"` PERO el log es de la rama `unhandled_exception` (ERROR + traceback), no un `typed_api_error` "esperado". Blindaje: un bug no se reetiqueta como fallo esperado.
- `test_devops_console_exec_upstream_typed` (C1) → flag `STACKY_DEVOPS_REMOTE_CONSOLE_ENABLED` + `STACKY_DEVOPS_SERVERS_ENABLED` ON, monkeypatch `run_remote` para `raise ConnectionError` (transporte esperado) → 502 con `error_type == "upstream"`.
- `test_devops_console_exec_bug_propagates_500` (C1) → monkeypatch `run_remote` para `raise TypeError("bug")` (inesperado) → 500 (no 502): el bug propaga a la rama no-tipada, NO se enmascara como upstream.
- `test_devops_console_conversations_list_typed_on_db_error` → monkeypatch `session_scope` para lanzar → 500 tipado con `endpoint == "/api/devops/console/conversations"`.

> Los tests deben correr con el **flag de cada feature ON** vía `monkeypatch.setenv`/`monkeypatch.setattr(config.config, ...)`, siguiendo el patrón de `test_plan105_remote_console_api.py` `[V existe]`.

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_typed_errors.py -q
```

**Criterio de aceptación binario:** los 5 tests de F2 pasan; ningún endpoint objetivo devuelve `{"error":"Internal server error"}` sin `error_type` cuando el flag está ON; un bug inesperado propaga a 500 con traceback (C1), NO se reetiqueta como 502/500 "esperado".

**Flag:** `STACKY_TYPED_ERROR_ENVELOPE_ENABLED` (default ON) gobierna la FORMA; la instrumentación (levantar tipos) es un fix de robustez always-on (con flag OFF, el tipo levantado degrada a la forma legacy vía F1).

**Impacto por runtime:** los endpoints sirven a los 3 runtimes por igual (el runtime lo elige el payload). Idéntico. **Fallback:** flag OFF → forma legacy.

**Trabajo del operador: ninguno.**

---

### F3 — Clasificación de la causa de fallo de intake (`reason_code`) (D5, mejora b)

**Objetivo:** que `artifact_intake` distinga `empty` / `truncated` / `malformed` y emita un mensaje accionable + un `reason_code` estable que la UI (F4) y el hook (F6) puedan renderizar. **Valor:** el operador y el agente saben EXACTAMENTE qué pasó ("archivo vacío" ≠ "JSON con coma de más").

**Anchor `[V]` — estado ACTUAL (`backend/services/artifact_intake.py`):**
- `IntakeResult` (dataclass frozen, línea 33) tiene `ok, normalized, repaired, repairs, errors`. **No** tiene `reason_code`.
- `_intake_pending_task` (línea 74) prueba reparaciones y en `json.loads` fallido (línea 111-120) devuelve error `"JSON inválido tras reparaciones (línea X, col Y): {msg}. Reescribí..."`. El `{msg}` para archivo vacío/truncado es `Expecting value`.

**Archivos:** EDITAR `backend/services/artifact_intake.py`. CREAR `backend/tests/test_plan149_intake_reason_codes.py`.

**Cambios exactos:**
1. Agregar campo a `IntakeResult`:
   ```python
   reason_code: str | None = None   # "empty" | "truncated" | "malformed" | "schema" | "anti_ordinal" | None
   ```
   y en `to_dict` incluir `"reason_code": self.reason_code`.
2. Nueva función pura **pública** (C8 — `classify_json_failure`, SIN underscore: es un contrato compartido que F6 importa desde `artifact_validator`; un símbolo `_privado` cruzando módulos es olor a diseño):
   ```python
   def classify_json_failure(text: str) -> str:
       """Clasifica un JSON no parseable: 'empty' | 'truncated' | 'malformed'.
       Contrato compartido: lo consumen artifact_intake (F3) y artifact_validator (F6)."""
       stripped = text.strip()
       if not stripped:
           return "empty"
       # más '{' que '}' ⇒ objeto sin cerrar ⇒ escritura truncada
       if stripped.count("{") > stripped.count("}"):
           return "truncated"
       return "malformed"
   ```
3. En el `except json.JSONDecodeError` de `_intake_pending_task`, setear `reason_code` y mensaje según clase (`code = classify_json_failure(text)`):
   ```python
   except json.JSONDecodeError as exc:
       code = classify_json_failure(text)
       hint = {
           "empty": "el archivo está vacío o solo tiene espacios; el agente no llegó a escribir el contenido. Reescribí el pending-task.json completo.",
           "truncated": "el JSON quedó truncado (objeto sin cerrar); probablemente la escritura se cortó. Reescribí el archivo completo con JSON válido.",
           "malformed": f"JSON inválido tras reparaciones (línea {exc.lineno}, col {exc.colno}): {exc.msg}. Reescribí el archivo completo con JSON válido.",
       }[code]
       return IntakeResult(ok=False, normalized=None, repaired=bool(repairs),
                           repairs=repairs, errors=[hint], reason_code=code)
   ```
4. En las ramas de schema/anti-ordinal (líneas 133-137, 122-126) setear `reason_code="schema"` y `reason_code="anti_ordinal"` respectivamente (aditivo, no cambia `ok`/`errors`).

Casos borde:
- Archivo con `"   \n  "` → `empty`.
- `{"title": "x"` (sin cierre) → `truncated`.
- `{"title": "x",}` con coma final → el reparador lo arregla (`_TRAILING_COMMA_RE`) → `ok` (sin reason_code).
- `{"a": }` (valor faltante, balanceado) → `malformed`.

**Tests PRIMERO — `backend/tests/test_plan149_intake_reason_codes.py`:**
```python
from services.artifact_intake import validate_and_normalize
def _r(raw): return validate_and_normalize(raw=raw, kind="pending_task_json")
def test_empty_file_reason_empty():      assert _r("   \n ").reason_code == "empty" and not _r("   ").ok
def test_truncated_object_reason_truncated(): assert _r('{"title": "x"').reason_code == "truncated"
def test_missing_value_reason_malformed(): assert _r('{"a": }').reason_code == "malformed"
def test_trailing_comma_still_repaired_ok():  # requiere schema mínimo → puede fallar por schema, no por JSON
    res = _r('{"title":"x",}'); assert res.reason_code in (None, "schema")  # NO "malformed"
def test_reason_code_in_to_dict():       assert "reason_code" in _r("").to_dict()
def test_valid_full_payload_no_reason(): ...  # payload con todos los required → ok, reason_code None
```

> Para `test_valid_full_payload_no_reason`, construir un dict con los campos de `artifact_validator._required_fields()` (`generated_at, generated_by, epic_id, rf_id, title, description_html, plan_de_pruebas_path, parent_link_type, status`, con `status="pending_manual_creation"`) `[V]`.

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_intake_reason_codes.py backend/tests/test_artifact_intake.py -q
```

**Criterio de aceptación binario:** ambos archivos verdes; `test_artifact_intake.py` (existente) sigue pasando (aditivo, sin romper contrato). `reason_code` presente en `to_dict`.

**Flag:** ninguno nuevo — cambio aditivo dentro del path ya protegido por `STACKY_ARTIFACT_INTAKE_ENABLED` (default ON `[V]`). **Justificación de no-flag:** es un enriquecimiento de un `IntakeResult` que hoy ya se produce; agregar un campo opcional y afinar un mensaje no cambia comportamiento observable salvo mejor texto. No hay comportamiento nuevo opt-in que aislar.

**Impacto por runtime:** runtime-agnóstico (intake corre sobre archivos de cualquier runtime). **Fallback:** con `STACKY_ARTIFACT_INTAKE_ENABLED` OFF, el intake no corre (path legacy `json.loads`), igual que hoy.

**Trabajo del operador: ninguno.**

---

### F4 — Superficie de cuarentena de intake en el Desatascador (D5, mejora c) + kill-switch

**Objetivo:** que los `pending-task.json` que el `output_watcher` puso en cuarentena estructural sean **visibles** en el board "Desatascador" con la causa EXACTA del intake (mismo mensaje que el log), y que el board y el intake dejen de divergir. **Valor:** el operador ve "este archivo fue rechazado por: archivo vacío" en la UI, no un warning perdido en el log.

**Anchors `[V]`:**
- `output_watcher._quarantine_pending_once` (`output_watcher.py:845`) guarda solo `_SEEN_TERMINAL_PENDING[path]=mtime_ns`; el **reason** se loguea pero **no se retiene** en memoria accesible.
- El board `GET /api/tickets/unblocker-board` (`tickets.py:2575`) ya muestra `parse_errors` con readiness `files_error` (`tickets.py:2748`), pero los computa con `json.loads` **plano** en `_scan_pending_tasks_for_epic` (`tickets.py:2443`), NO por intake → el mensaje difiere del rechazo real.

**Archivos:**
- EDITAR `backend/services/output_watcher.py` (retener reason + accessor público).
- EDITAR `backend/api/tickets.py` (`_scan_pending_tasks_for_epic`: rutear por intake cuando el flag está ON).
- EDITAR `backend/services/harness_flags.py`, `backend/config.py`, `backend/tests/test_harness_flags.py` (flag nuevo, patrón triple).
- CREAR `backend/tests/test_plan149_intake_quarantine_surface.py`.

**Flag nuevo — patrón triple (los 3 puntos exactos):**
1. `harness_flags.py` — `FlagSpec(key="STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", type="bool", label="Superficie de cuarentena de intake en Desatascador", description="Plan 149 — Si ON, el board Desatascador muestra pending-task.json rechazados por intake con su causa exacta (reason_code) y habilita el re-procesamiento 1-click. OFF = comportamiento legacy (json.loads plano).", group="global", env_only=True, default=True)` — colocar junto a `STACKY_ARTIFACT_INTAKE_ENABLED` (línea 678) y agregar la key a la categoría `"fiabilidad_ciclo_vida"` (`harness_flags.py:225`).
2. `config.py` — `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED: bool = os.getenv("STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", "true").lower() in ("1","true","yes")` (junto a la 695).
3. `test_harness_flags.py` — agregar `"STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED",` a `_CURATED_DEFAULTS_ON` (línea 467).

**Cambios exactos:**

1. **`output_watcher.py`** — retener el reason y exponerlo:
   ```python
   # junto a _SEEN_TERMINAL_PENDING (línea 826):
   _QUARANTINE_REASON: dict[str, str] = {}   # path -> mensaje de cuarentena

   # dentro de _quarantine_pending_once, al registrar:
   _SEEN_TERMINAL_PENDING[key] = mtime_ns
   _QUARANTINE_REASON[key] = reason

   def quarantine_snapshot() -> dict[str, dict]:
       """Snapshot read-only de la cuarentena para diag/board. path -> {reason, mtime_ns}."""
       return {k: {"reason": _QUARANTINE_REASON.get(k, ""), "mtime_ns": v}
               for k, v in _SEEN_TERMINAL_PENDING.items()}

   def clear_quarantine(pt_file: Path) -> bool:
       """C3 — Limpia la cuarentena de UN path derivando la clave EXACTAMENTE igual
       que _quarantine_pending_once (key = str(pt_file)). Devuelve True si había algo
       que limpiar. F5 DEBE usar esto en vez de poppear el dict privado con un path
       resuelto aparte: en Windows str((repo_root/rel).resolve()) puede divergir de
       cómo el watcher guardó la clave, dejando el pop en un no-op silencioso."""
       key = str(pt_file)
       existed = _SEEN_TERMINAL_PENDING.pop(key, None) is not None
       _QUARANTINE_REASON.pop(key, None)
       return existed
   ```
   > **C3 — consistencia de clave:** `_quarantine_pending_once` usa `key = str(pt_file)` `[V output_watcher.py:849]` con el `pt_file` que le pasa el watcher (derivado de `iter_epic_pending_task_files`, **sin** `.resolve()`). `clear_quarantine` reusa esa MISMA derivación. Si F5 necesita resolver el path para leerlo, debe pasarle a `clear_quarantine` el path **con la misma forma que ve el watcher** (relativo→`repo_root / rel`, sin `.resolve()`), no un `.resolve()` independiente.

2. **`tickets.py::_scan_pending_tasks_for_epic`** (línea 2440-2455) — cuando el flag está ON, computar el error vía intake para igualar el mensaje:
   ```python
   for pt_file in iter_epic_pending_task_files(repo_root, ado_id):
       raw = None
       try:
           raw = pt_file.read_text(encoding="utf-8-sig")
           payload = json.loads(raw)
       except Exception as exc:
           reason_code = None; msg = str(exc)[:300]
           if os.getenv("STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", "true").lower() in ("1","true","yes","on") and raw is not None:
               from services import artifact_intake
               res = artifact_intake.validate_and_normalize(
                   raw=raw, kind="pending_task_json",
                   ticket_context={"valid_ado_ids": [ado_id]})
               if not res.ok:
                   reason_code = res.reason_code
                   msg = "; ".join(res.errors) or msg
           logger.warning("pending-task: no se pudo parsear %s: %s", pt_file, exc)
           parse_errors.append({
               "rf_id": pt_file.parent.name,
               "pending_task_path": rel_err,   # como hoy
               "error": msg,
               "reason_code": reason_code,     # NUEVO
           })
           continue
   ```
   > El board (`unblocker_board`, línea 2722) ya arma un `blocker` legible por cada `parse_error`; ese texto ahora hereda el mensaje de intake (más preciso). No hace falta tocar el loop del board, solo el `error`/`reason_code` que consume.

Casos borde:
- Flag OFF → `reason_code=None` y `error=str(exc)` legacy (byte-idéntico al comportamiento actual).
- Archivo que `json.loads` acepta pero intake rechaza por schema: NO cae al `except` (json.loads no falla) → no se marca como parse_error acá. Correcto: ese caso es "schema", no "no parsea". (El board lo ve como pending normal; el rechazo real ocurre en el intake del watcher y quedará cubierto por el snapshot de cuarentena, opcionalmente cruzable en un futuro plan. Fuera de scope de 149.)

**Tests PRIMERO — `backend/tests/test_plan149_intake_quarantine_surface.py` (parte F4):**
- `test_quarantine_snapshot_records_reason` → forzar `_quarantine_pending_once(tmp_pt, "archivo vacío")` y assert `quarantine_snapshot()[str(tmp_pt)]["reason"] == "archivo vacío"`.
- `test_scan_parse_errors_carry_reason_code_when_flag_on` (monkeypatch flag ON) → crear un epic dir con un `pending-task.json` vacío en un `repo_root` temporal, llamar `_scan_pending_tasks_for_epic(repo_root, ado_id)` y assert que `parse_errors[0]["reason_code"] == "empty"`.
- `test_scan_parse_errors_legacy_when_flag_off` (flag OFF) → `parse_errors[0]["reason_code"] is None` y `error` es el `str(exc)` plano.

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_intake_quarantine_surface.py backend/tests/test_output_watcher.py backend/tests/test_unblocker_board.py -q
```

**Criterio de aceptación binario:** los tests nuevos pasan; `test_output_watcher.py` y `test_unblocker_board.py` (existentes) siguen verdes; con flag OFF el `parse_error` es byte-idéntico al actual.

**Flag:** `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (default ON, kill-switch env-only).

**Impacto por runtime:** runtime-agnóstico. **Fallback:** flag OFF → board legacy.

**Trabajo del operador: ninguno** (superficie automática).

---

### F5 — Endpoint de re-intake 1-click (D5, mejora c, human-in-the-loop)

**Objetivo:** dar al operador un botón para **re-procesar** un `pending-task.json` que corrigió (o pedir su re-evaluación), reusando el `create-child-task` idempotente existente. **Valor:** cierra el lazo humano: el operador ve el archivo en cuarentena (F4), lo arregla, y con 1 click Stacky reintenta el intake + la creación de la Task, sin esperar al mtime ni tocar env vars.

**Archivos:** EDITAR `backend/api/tickets.py` (nuevo endpoint). EDITAR el frontend del board (botón). CREAR test.

**Endpoint exacto — `backend/api/tickets.py` (nuevo, junto al bloque desatascador ~línea 2893):**
```python
@bp.post("/reintake-pending-task")
def reintake_pending_task():
    """Plan 149 — Re-procesa 1-click un pending-task.json (human-in-the-loop).

    Body: {"pending_task_path": "<rel_al_repo>", "epic_ado_id": <int>, "project": <str?>}
    - Valida por intake; si sigue inválido → 422 tipado con reason_code + errors.
    - Si es válido → limpia la cuarentena de ese path y llama al create-child-task
      idempotente existente. Devuelve el resultado.
    """
    from api.errors import ValidationError, ResourceNotFoundError, set_exec_id  # noqa
    import config as _config
    if not getattr(_config.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True):
        from flask import abort; abort(404)   # kill-switch: endpoint inerte

    body = request.get_json(force=True, silent=True) or {}
    rel = (body.get("pending_task_path") or "").strip()
    epic_ado_id = body.get("epic_ado_id")
    if not rel or epic_ado_id is None:
        raise ValidationError("pending_task_path y epic_ado_id son obligatorios")

    repo_root, _scan = _resolve_artifact_repo_root()
    pt_key = repo_root / rel                 # C3: MISMA forma que ve el watcher (sin .resolve())
    pt_resolved = pt_key.resolve()           # solo para lectura + guard anti-traversal
    # Guard anti path traversal: debe caer dentro del repo_root.
    if repo_root.resolve() not in pt_resolved.parents:
        raise ValidationError("pending_task_path fuera del repo")
    if not pt_resolved.is_file():
        raise ResourceNotFoundError(f"no existe el archivo: {rel}")

    from services import artifact_intake
    raw = pt_resolved.read_text(encoding="utf-8")
    res = artifact_intake.validate_and_normalize(
        raw=raw, kind="pending_task_json",
        ticket_context={"valid_ado_ids": [int(epic_ado_id)]})
    if not res.ok:
        raise ValidationError("el pending-task.json sigue inválido; corregilo y reintentá",
                              details={"reason_code": res.reason_code, "errors": res.errors})

    # C3 — Limpiar cuarentena vía helper público (clave derivada IGUAL que el watcher),
    # para permitir también el reproceso del watcher. pt_key NO está .resolve()-eado.
    from services.output_watcher import clear_quarantine
    clear_quarantine(pt_key)

    # Reusar el create-child-task idempotente (self-HTTP, mismo patrón que output_watcher).
    port = getattr(_config.config, "PORT", int(os.getenv("PORT", "5050")))
    resp = requests.post(
        f"http://127.0.0.1:{port}/api/tickets/by-ado/{int(epic_ado_id)}/create-child-task",
        json={"pending_task_path": rel, "operator_reason": "re-intake 1-click (Plan 149)",
              "completion_source": "operator_reintake",
              **({"project": body["project"]} if body.get("project") else {})},
        timeout=60)
    out = resp.json() if resp.headers.get("content-type","").startswith("application/json") else {}
    return jsonify({"ok": resp.status_code == 200 and out.get("ok") is not False,
                    "create_child_task": out, "status_code": resp.status_code}), (200 if resp.status_code == 200 else resp.status_code)
```

Casos borde:
- Path traversal (`../../`) → `ValidationError` 422 (guard `repo_root not in parents`).
- Archivo ausente → `ResourceNotFoundError` 404 tipado.
- Sigue inválido → 422 con `details.reason_code` + `details.errors` (el operador ve exactamente qué falta).
- `create-child-task` idempotente ya maneja "consumed" → devuelve idempotent (no duplica).
- Flag OFF → `abort(404)` (endpoint no existe efectivamente).

**Frontend (botón 1-click):** en el componente del board Desatascador que renderiza `parse_errors` (el que consume `GET /api/tickets/unblocker-board`), agregar un botón "Re-procesar" por cada `parse_error`/item con `reason_code`, que hace `POST /api/tickets/reintake-pending-task` con `{pending_task_path, epic_ado_id}` y muestra el `details.errors` si vuelve 422.
> **C7 — honestidad de estado (Plan 135):** la respuesta de F5 puede ser HTTP 200 con `body.ok == false` cuando `create-child-task` respondió 200 pero reportó `ok:false` en su cuerpo (fallo lógico blando / idempotente-consumed). El frontend DEBE surfacear `body.create_child_task.ok` y sus `errors`/`message`, **no** asumir éxito por el status 200. Un 200 con `ok:false` sin feedback visible sería un fallo mudo.
> Ubicar el componente con `grep -r "unblocker-board\|parse_errors\|files_error" frontend/src` `[INF]` (no verifiqué el archivo .tsx exacto; el implementador debe localizarlo — la capa .tsx del board ya existe porque el endpoint ya se consume). Test frontend por archivo con `npx vitest run <archivo>` si el componente tiene test; si no hay RTL/jsdom (gap estructural conocido del repo), el gate del botón es `tsc --noEmit` + smoke manual.

**Tests PRIMERO — `backend/tests/test_plan149_intake_quarantine_surface.py` (parte F5):**
- `test_reintake_404_when_flag_off` (flag OFF) → POST → 404.
- `test_reintake_422_when_still_invalid` → archivo vacío en repo temporal → 422 con `body["details"]["reason_code"] == "empty"`.
- `test_reintake_404_when_file_missing` → path a archivo inexistente → 404 `error_type == "not_found"`.
- `test_reintake_rejects_path_traversal` → `pending_task_path="../../etc/x"` → 422 `error_type == "validation"`.
- `test_reintake_calls_create_child_task_when_valid` → monkeypatch `requests.post` para capturar la llamada; archivo válido → assert que se llamó a `.../create-child-task` con el `pending_task_path` correcto. Sembrar la cuarentena vía `_quarantine_pending_once(repo_root / rel, "empty")` (misma forma de clave), y afirmar que tras el POST `quarantine_snapshot()` ya no contiene esa clave (C3: verifica el helper `clear_quarantine`, no un pop con path resuelto aparte).

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_intake_quarantine_surface.py -q
```

**Criterio de aceptación binario:** los 5 tests de F5 pasan; el endpoint respeta el kill-switch, tipa sus errores (via F0/F1) y limpia la cuarentena al re-procesar OK.

**Flag:** `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (default ON) gobierna el endpoint; los errores usan `STACKY_TYPED_ERROR_ENVELOPE_ENABLED`.

**Impacto por runtime:** runtime-agnóstico (opera sobre el archivo file-based que produjo cualquier runtime). **Fallback:** flag OFF → endpoint inerte (404), sin regresión.

**Trabajo del operador: opt-in (default ON)** — el botón es una acción manual del operador dentro del flujo Desatascador que ya usa. No dispara ninguna excepción dura (no bypasea revisión, no es destructivo, no requiere prerequisito, no reduce seguridad).

---

### F6 — (Opcional, best-effort) Paridad del refuerzo (a): feedback pre-escritura con `reason_code` (Claude) + degradación explícita

**Objetivo:** que el hook pre-escritura de Claude que **ya existe** (F1.4) le devuelva al agente el mensaje clasificado de F3 cuando escribe un `pending-task.json` vacío/truncado, para que lo reescriba ANTES de terminar el turno. **Valor:** en el runtime Claude, el archivo inválido nunca llega al intake (defensa temprana); en Codex/Copilot degrada a F3+F4+F5.

**Anchor `[V]` — el hook YA EXISTE:** `backend/services/claude_cli_hooks.py` genera un `PostToolUse` sobre `Write|Edit` que, al matchear `Agentes/outputs/**/pending-task.json`, llama a `POST /api/agents/validate-artifact` y si `valid==false` devuelve `exit 2 + stderr` al agente (`claude_cli_hooks.py:34-60`). El endpoint usa `artifact_validator.validate_pending_task_file` (`artifact_validator.py:136`), que hace su propio `json.loads` y devuelve `errors`.

> **DISCREPANCIA con el anchor del reporte:** la mejora (a) "validar JSON antes de persistir en el runtime del agente" **ya está implementada para Claude** (F1.4). Este plan NO la reinventa: solo alinea su MENSAJE con la clasificación de F3 y documenta la degradación. Reportado en `anchorDiscrepancies`.

**Archivos:** EDITAR `backend/services/artifact_validator.py` (`validate_pending_task_file`, línea 148-156) para incluir el hint clasificado. CREAR `backend/tests/test_plan149_prewrite_hook_message.py`.

**Cambio exacto (aditivo):** en el `except json.JSONDecodeError` de `validate_pending_task_file` (línea 150), reusar la clasificación:
```python
except json.JSONDecodeError as exc:
    from services.artifact_intake import classify_json_failure
    code = classify_json_failure(raw)
    result.valid = False
    result.errors.append({
        "empty": "el archivo está vacío; escribí el pending-task.json completo antes de terminar.",
        "truncated": "el JSON quedó truncado (objeto sin cerrar); reescribí el archivo completo.",
        "malformed": f"JSON inválido (línea {exc.lineno}, col {exc.colno}): {exc.msg}. Reescribí el archivo completo.",
    }[code])
    return result
```

**Degradación explícita por runtime:**
| Runtime | Refuerzo (a) pre-escritura | Defensa file-based (F3+F4+F5) |
|---|---|---|
| Claude Code CLI | **Sí** — hook PostToolUse (F1.4) con mensaje clasificado | Sí (fallback si el hook falla open / backend caído) |
| Codex CLI | **No** (sin hook) → degrada | **Sí** — intake + board + re-intake cubren el caso |
| GitHub Copilot Pro | **No** (sin hook) → degrada | **Sí** — idem |

**Tests PRIMERO — `backend/tests/test_plan149_prewrite_hook_message.py`:**
- `test_validate_pending_task_empty_message` → `validate_pending_task_file(<archivo vacío>, check_db=False)` → `valid is False` y algún error contiene "vacío".
- `test_validate_pending_task_truncated_message` → archivo `{"title":"x"` → error contiene "truncado".

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_prewrite_hook_message.py backend/tests/test_artifact_validator.py backend/tests/test_claude_cli_hooks.py -q
```

**Criterio de aceptación binario:** tests nuevos verdes; `test_artifact_validator.py` y `test_claude_cli_hooks.py` (existentes) siguen verdes.

**Flag:** ninguno nuevo (reusa el hook ya gobernado por su propia lógica y `STACKY_ARTIFACT_INTAKE_ENABLED`). **Justificación de no-flag:** enriquecimiento de mensaje de un validador existente, sin comportamiento nuevo.

**Impacto por runtime:** ver tabla. **Fallback:** el hook es fail-open (`claude_cli_hooks.py:53`); si el backend no responde, el agente no se bloquea y la defensa file-based (F3-F5) toma el relevo.

**Trabajo del operador: ninguno.**

> **F6 es OPCIONAL.** F3+F4+F5 ya cierran D5 de forma runtime-agnóstica. F6 solo mejora el mensaje inline en el runtime Claude. Si el presupuesto de implementación es ajustado, se puede diferir sin dejar D5 abierto.

---

### F7 — [ADICIÓN ARQUITECTO] Diag read-only global de cuarentena de intake

**Gap que cierra (real):** F4 superficia la cuarentena **solo** para los `pending-task.json` que caen bajo un Epic escaneado por `_scan_pending_tasks_for_epic(repo_root, ado_id)` (el board es **epic-scoped**). Un archivo puesto en cuarentena cuyo Epic **no resuelve** (huérfano, mal ubicado, dir de Epic borrado, o `ado_id` que el board no lista) queda **invisible incluso tras F4** — es exactamente el patrón "crea archivos pero no la task" en su forma más difícil de diagnosticar. F7 expone la cuarentena **GLOBAL** (todo lo que `_quarantine_pending_once` retuvo), independiente del Epic, en un endpoint diag read-only.

**Valor:** (1) el operador ve TODA la cuarentena en un solo lugar aunque el board no la muestre; (2) deja el **gancho de suscripción** para el Centro de Notificaciones (Plan 152), que puede agregar "N artefactos en cuarentena" sin recorrer el board; (3) costo casi nulo: el snapshot ya lo construye F4.

**Archivos:**
- EDITAR `backend/api/diag.py` (nuevo endpoint GET, junto a los diag existentes de `output_watcher` — `output_watcher_scan_now`/`output_watcher_stats` ya viven ahí `[V CLAUDE.md diag.py]`).
- CREAR test en `backend/tests/test_plan149_intake_quarantine_surface.py` (parte F7).

**Endpoint exacto — `backend/api/diag.py`:**
```python
@bp.get("/intake-quarantine")
def intake_quarantine():
    """Plan 149 F7 — Snapshot read-only GLOBAL de la cuarentena de intake.

    Complementa el board Desatascador (epic-scoped) con una vista total, incluidos
    archivos cuya Epic no resuelve. Read-only, sin efectos. Gobernado por el mismo
    kill-switch que la superficie del board.
    """
    import config as _config
    if not getattr(_config.config, "STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED", True):
        return jsonify({"enabled": False, "items": []})
    from services.output_watcher import quarantine_snapshot
    snap = quarantine_snapshot()
    items = [{"path": k, "reason": v.get("reason", ""), "mtime_ns": v.get("mtime_ns")}
             for k, v in snap.items()]
    return jsonify({"enabled": True, "count": len(items), "items": items})
```

Casos borde:
- Flag OFF → `{"enabled": False, "items": []}` (no expone nada; consistente con F4/F5 inertes).
- Cuarentena vacía → `{"enabled": True, "count": 0, "items": []}`.
- Read-only: no muta `_SEEN_TERMINAL_PENDING` ni dispara reproceso (para eso está F5).

**Tests PRIMERO — `backend/tests/test_plan149_intake_quarantine_surface.py` (parte F7):**
- `test_diag_intake_quarantine_lists_all_when_flag_on` → sembrar 2 paths con `_quarantine_pending_once`; `GET /api/diag/intake-quarantine` → `count == 2` y cada item trae `reason`.
- `test_diag_intake_quarantine_disabled_when_flag_off` (flag OFF) → `{"enabled": False, "items": []}`.

**Comando:**
```
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan149_intake_quarantine_surface.py backend/tests/test_diag.py -q
```
> Si no existe `test_diag.py`, correr solo el archivo de 149. Fixture: limpiar `_SEEN_TERMINAL_PENDING`/`_QUARANTINE_REASON` en setup/teardown (R7).

**Criterio de aceptación binario:** ambos tests pasan; el endpoint respeta el kill-switch y es read-only.

**Flag:** `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (default ON) — reusa el flag de F4, sin flag nuevo.

**Impacto por runtime:** runtime-agnóstico (opera sobre la cuarentena file-based). **Fallback:** flag OFF → `enabled:false`.

**Trabajo del operador: ninguno** (superficie automática; opcional un futuro widget en 152).

> **F7 es recomendado, no bloqueante de D5.** F3+F4+F5 cierran D5 para el caso epic-resoluble; F7 cubre el residuo huérfano y habilita 152. Bajo costo, alto valor de observabilidad.

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | Cambiar la forma del 500 rompe consumidores del frontend que leen `.error` | El envelope **conserva** `"error"` (= `error_type`) y agrega campos; kill-switch `STACKY_TYPED_ERROR_ENVELOPE_ENABLED` OFF revierte a forma legacy exacta. Test `test_handler_legacy_shape_when_flag_off`. |
| R2 | `HTTPException` (abort 4xx) accidentalmente tipado y roto | El handler mantiene el `isinstance(exc, HTTPException): return exc` **primero**. Test `test_http_exception_passthrough`. |
| R3 | El ruteo del board por intake (F4) agrega latencia al `unblocker-board` | Solo se ejecuta en el `except` (archivos que ya fallaron `json.loads`, minoría); el intake es puro-CPU sobre un archivo chico. Sin I/O extra (el `raw` ya está leído). |
| R4 | El re-intake (F5) crea Tasks duplicadas | Reusa el `create-child-task` **idempotente** (marca `consumed`); el propio watcher usa el mismo endpoint. `test_reintake_calls_create_child_task_when_valid` verifica la llamada, no la duplicación. |
| R5 | Path traversal en `reintake-pending-task` | Guard `repo_root not in pt_file.parents` + `ValidationError`. Test `test_reintake_rejects_path_traversal`. |
| R6 | `classify_json_failure` mal clasifica (p.ej. `{` dentro de un string truncado) | Heurística conservadora: `empty` es exacto; `truncated` vs `malformed` solo afecta el TEXTO del mensaje, nunca `ok`/`valid`. Ambos rechazan igual. |
| R7 | Módulo-global `_SEEN_TERMINAL_PENDING`/`_QUARANTINE_REASON` compartido entre tests contamina cross-file | Correr **por archivo** (regla del repo); los tests que tocan la cuarentena deben limpiar el dict en `setup/teardown` (fixture que hace `_SEEN_TERMINAL_PENDING.clear()`). |
| R8 | Import de `api.errors` desde `app.py` genera ciclo | Import **lazy dentro del handler** (no top-level), igual que el resto de imports diferidos en `app.py`. |
| R9 | Colisión con la sesión paralela activa en el mismo árbol/rama | El orquestador commitea; este plan solo escribe su .md. En implementación: `git add` con paths explícitos + re-verificar `git status` (gotcha conocido del ecosistema). |
| R10 | **(C1)** Envolver crashes en tipos enmascara bugs (los vuelve "esperados", WARNING sin traceback) → error mudo, choca con Plan 135 | F1 loguea los 5xx tipados a **ERROR con `exc=`** (traceback vía `__cause__`); F2 captura SOLO excepciones esperadas de transporte/dominio; los bugs (`AttributeError`/`TypeError`/…) **propagan** a la rama no-tipada. Tests `test_handler_5xx_logs_at_error_with_traceback`, `test_*_bug_propagates_*`. |
| R11 | **(C3)** El pop de cuarentena de F5 no matchea la clave que guardó el watcher (divergencia `str(pt.resolve())` vs `str(pt)` en Windows) → no-op silencioso, verde en test / roto en prod | Helper público `output_watcher.clear_quarantine(pt_file)` deriva la clave IGUAL que `_quarantine_pending_once`; F5 le pasa `repo_root / rel` (sin `.resolve()`). Test siembra con la misma forma y verifica vía `quarantine_snapshot()`. Impacto residual bajo: aunque no limpie, la Task ya se crea vía el `create-child-task` directo de F5. |
| R12 | **(C4)** Coexistencia con la jerarquía existente `AdoApiError` + `_ado_sync_error_response` (`tickets.py:293`) | Capas distintas: `StackyApiError` = transporte (handler transversal); `AdoApiError` = dominio ADO, atrapado **localmente** por sus rutas ANTES de llegar al handler. No convergen en 149 (ver §6). Si un `AdoApiError` escapara sin atrapar, cae en la rama no-tipada (500 ERROR con traceback) — comportamiento actual, sin regresión. |
| R13 | **(C5)** Colisión de merge con la serie 144-149 en archivos de registro compartidos | 149 edita `harness_flags.py` (+2 `FlagSpec`, +2 categorías), `config.py` (+2 defaults), `test_harness_flags.py:467` (`_CURATED_DEFAULTS_ON`). 145 (helper/agents_dir), 146 (import/Config), 148 (`integration_breaker` + flag) tocan los MISMOS archivos. **Implementar en serie, no en paralelo**; tras cada plan re-correr `test_harness_flags.py` completo por si otro agregó/quitó flags. |

---

## 6. Fuera de scope (explícito)

- **D1/D2/D3/D4** (trust de workspace, stall watchdog, reaper 120 min, `needs_review` inválido) → **Plan 144**. D4 debe cerrarse en 144 para que la transición a `needs_review` funcione; 149 no lo toca.
- **404 `pipeline/status`, strip ANSI, aislar pytest, dedup de warnings** → **Plan 145** (145 provee el helper de dedup).
- **V1 (import `Execution`), V4 (`CLAUDE_CODE_CLI_MODEL_FALLBACK` + re-deploy), V5 (mkdir SQLite ledger)** → **Plan 146**.
- **V2 (`outputs_dir`/`repo_root` sin segmento de proyecto), D8 (watchers inactivos)** → **Plan 147**.
- **D6 (502 LLM local/ADO), V3 (PAT expirado), V8 (Jira sin credenciales), D9 (api-version connectionData)** → **Plan 148**.
- **Cruce watcher-quarantine ↔ board para el caso "schema-inválido pero JSON parseable"**: hoy el board solo muestra los que NO parsean; el caso schema-inválido queda cubierto por el intake/log pero no por el board. Ampliar el board a "schema-inválido visible" es material de un plan futuro (no bloquea D5, cuyo síntoma es JSON no parseable).
- **Reescritura del frontend del Desatascador**: F5 agrega UN botón; no rediseña el board.
- **Cambiar el default de `STACKY_ARTIFACT_INTAKE_ENABLED`** (ya está ON).
- **(C4) Converger `AdoApiError` en `StackyApiError`.** Ya existe una jerarquía de dominio ADO (`AdoApiError`) con su handler dedicado `_ado_sync_error_response` (`tickets.py:293`, atrapado **localmente** en las rutas ADO). 149 **no** la reusa ni la absorbe: `StackyApiError` es la capa de **transporte HTTP** (handler transversal `app.py:508`), `AdoApiError` es de **dominio** y se resuelve antes de llegar al handler. Son ortogonales; unificarlas es material de un plan futuro de higiene, no de 149 (mezclarlas ahora ampliaría el scope y arriesgaría el contrato ADO existente). Decisión de reuso: crear `StackyApiError` es correcto porque **no hay** una jerarquía de transporte-HTTP genérica que reusar — `AdoApiError` es específica de ADO.

---

## 7. Glosario + Orden de implementación + DoD

### Glosario (términos Stacky usados en este plan)
- **Intake:** contrato universal de validación+reparación de outputs file-based (`services/artifact_intake.py`), punto único server-side para que nada inválido llegue a ADO.
- **`pending-task.json`:** artefacto que el agente funcional escribe por Epic/RF; el `output_watcher` (Modo A) lo consume para auto-crear Tasks hijas en ADO.
- **output_watcher (Modo A):** poller de `Agentes/outputs/` que auto-crea Tasks desde `pending-task.json` estables (`services/output_watcher.py`).
- **Cuarentena estructural:** mecanismo anti-loop (`_quarantine_pending_once`) que loguea UNA vez y omite un `pending-task.json` con fallo terminal hasta que cambie su mtime.
- **Desatascador / unblocker-board:** vista `GET /api/tickets/unblocker-board` que superficia artefactos listos/rotos para acción manual del operador.
- **Envelope tipado:** cuerpo JSON canónico de error `{ok, error, error_type, message, request_id, exec_id, endpoint, method}`.
- **`StackyApiError`:** jerarquía de excepciones de dominio que el handler transversal mapea a status HTTP + envelope.
- **Patrón triple de flags:** FlagSpec `default=True` + key en `_CURATED_DEFAULTS_ON` + default `"true"` en `config.py` (obligatorio para todo flag default ON).
- **Kill-switch env-only:** flag interno (no valor configurable por operador) que puede vivir solo en env var; igual se registra en el arnés para ser visible/toggleable en la UI.

### Orden de implementación (numerado, por dependencia)
1. **F0** — `api/errors.py` + flag `STACKY_TYPED_ERROR_ENVELOPE_ENABLED` (triple) + tests base. *(fundacional V6)*
2. **F1** — enriquecer `@app.errorhandler(Exception)` en `app.py`. *(dep. F0)*
3. **F2** — instrumentar `devops/console/*` + `agents/run` + `set_exec_id`. *(dep. F0+F1)*
4. **F3** — `reason_code` en `artifact_intake` + `classify_json_failure` (público, C8). *(independiente; cierra mejora b)*
5. **F4** — snapshot de cuarentena en `output_watcher` + ruteo del board por intake + flag `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED` (triple). *(dep. F3)*
6. **F5** — endpoint `POST /api/tickets/reintake-pending-task` + botón en el board (usa `clear_quarantine`, C3). *(dep. F0+F3+F4)*
7. **F6** *(opcional)* — alinear mensaje del validador pre-escritura (hook Claude) con `classify_json_failure` (F3). *(dep. F3)*
8. **F7** *([ADICIÓN ARQUITECTO], recomendado)* — endpoint diag `GET /api/diag/intake-quarantine` (snapshot global). *(dep. F4)*

> **Dependencias externas:** ninguna hard. 149 puede implementarse en cualquier momento tras 146/144 (recomendado por el orden global de la serie), pero no lo requiere: sus cambios son ortogonales a 144-148. Si 144 aún no cerró D4, F2 no se ve afectada (no toca estados terminales).

### Definición de Hecho (DoD) global
- [ ] `api/errors.py` creado con `StackyApiError` + 6 subclases + `build_error_envelope` + `set_exec_id`.
- [ ] Handler transversal (`app.py:508`) emite envelope tipado para `StackyApiError` y 500 tipado para excepciones crudas, con `HTTPException` passthrough intacto y forma legacy bajo flag OFF.
- [ ] **(C1)** 5xx tipados (Internal/Upstream/IntegrationUnavailable) se loguean a **ERROR con traceback**; 4xx a WARNING; ningún bug se reetiqueta como fallo "esperado" (tests de propagación verdes).
- [ ] **(C2)** El envelope conserva `.error` = **mensaje humano** (idéntico a la forma OFF); el token de máquina vive SOLO en `.error_type`.
- [ ] `devops/console/exec`, `devops/console/conversations` (GET+POST), `agents/run` instrumentados: fallos **esperados** → tipos; bugs inesperados → propagan; `exec_id` correlacionado.
- [ ] `IntakeResult.reason_code` presente; `empty`/`truncated`/`malformed` clasificados con mensaje accionable.
- [ ] Board Desatascador muestra `pending-task.json` inválidos con el mensaje/`reason_code` del intake (flag ON); `quarantine_snapshot()` disponible.
- [ ] Endpoint `reintake-pending-task` funcional: valida, tipa errores, limpia cuarentena **vía `clear_quarantine` (C3)**, reusa `create-child-task` idempotente, respeta kill-switch y guard anti-traversal.
- [ ] Botón "Re-procesar" cableado en el board (frontend) con `tsc --noEmit` limpio; **surfacea `create_child_task.ok`/errors, no solo el status HTTP (C7)**.
- [ ] *(opcional F6)* validador pre-escritura devuelve mensaje clasificado (usa `classify_json_failure` público, C8).
- [ ] *([ADICIÓN] F7)* endpoint diag `GET /api/diag/intake-quarantine` lista la cuarentena global read-only, respeta el kill-switch.
- [ ] **2 flags nuevos** (`STACKY_TYPED_ERROR_ENVELOPE_ENABLED`, `STACKY_INTAKE_QUARANTINE_SURFACE_ENABLED`) con patrón triple completo + categorizados; `test_default_known_only_for_curated` y `test_every_registry_flag_is_categorized` verdes.
- [ ] Todos los archivos de test de 149 verdes **corridos por archivo** con `backend/.venv/Scripts/python.exe`; suites existentes tocadas (`test_artifact_intake.py`, `test_output_watcher.py`, `test_unblocker_board.py`, `test_artifact_validator.py`, `test_harness_flags.py`, `test_plan105_remote_console_api.py`) sin regresión.
- [ ] Paridad de 3 runtimes verificada: D5 y V6 runtime-agnósticos; degradación de (a) documentada (Claude hook vs. Codex/Copilot file-based).
- [ ] Backward-compat: con ambos flags OFF, el comportamiento es byte-idéntico al actual.
```
