# 148 — Degradación explícita de integraciones no configuradas (ADO / Jira / LLM local)

- **Estado:** PROPUESTO v1
- **Fecha:** 2026-07-15
- **Autor:** StackyArchitectaUltraEficientCode (perfil: normal, heredado de Opus 4.8)
- **Serie:** 144–149 (derivada de `docs/reportes/2026-07-15_AUDITORIA_LOGS_deploy_vs_dev.md`)
- **Cierra hallazgos:** **D6** (502 en LLM local y en identidad ADO), **V3** (Sync ADO falla ~975× por PAT expirado / proyecto inexistente), **V8** (Sync Jira saltado 448× sin credenciales), **D9** (identidad ADO no resuelta: api-version bajo preview 11×).

---

## 1. Objetivo + KPI

Cuando una integración externa **no está configurada, expiró o no está disponible** (PAT de Azure DevOps vencido, proyecto ADO inexistente, credenciales Jira ausentes, modelo local caído, identidad ADO irresoluble), Stacky hoy **reintenta en cada ciclo** — inundando el log con cientos/miles de warnings idénticos — y **devuelve 502 crudo a la UI**, rompiendo pantallas que deberían degradar limpio. Este plan introduce **un único patrón transversal de degradación explícita**: un **circuit-breaker persistido** que detecta el fallo terminal de configuración, **desactiva el reintento automático con backoff**, expone un **estado legible en la UI** (reutilizando la Caja Fuerte de secretos del plan 94) y hace que los endpoints afectados **respondan 200 con `available/linked:false` + `reason`** en vez de 502. Incluye el fix puntual de la `api-version` de `connectionData` (D9), que es la causa raíz de que la identidad ADO nunca resuelva.

**KPI / impacto esperado (medibles contra el mismo método de conteo del reporte, Anexo 8.1):**

| Métrica | Antes (reporte 2026-07-15) | Meta después |
|---|---|---|
| `sync ADO falló: ...PAT... expired` (WARNING) | 887 + 54 ≈ **941** | **≤ 1 por transición de estado** (breaker abre 1 vez; luego DEBUG) |
| `The following project does not exist` (WARNING) | 34 | **≤ 1 por transición** |
| `sync Jira saltado: Credenciales Jira no encontradas` (WARNING) | 448 | **≤ 1 por transición** |
| `No se pudo resolver identidad ADO para 'me'` (WARNING) | 11 | **0** (D9 corrige la api-version) |
| `POST /api/llm/insights/<id>/generate → 502` | ≥ 1 (modelo caído) | **0** cuando el LLM local es inalcanzable → **200 `available:false`** |
| `GET /api/tickets/ado-user → 502` | 2 | **0** cuando la identidad no resuelve → **200 `linked:false`** |

Cero regresión funcional: cuando la integración SÍ está sana, el comportamiento es idéntico al actual.

---

## 2. Por qué ahora / gap que cierra

El reporte de auditoría demostró que la **mitad del ruido de log de DEV** proviene de reintentos de integraciones mal configuradas (ADO PAT expirado 941×, Jira sin creds 448×), y que la UI recibe **502 mudos** en dos superficies calientes ("Mis tareas" vía `ado-user`, e "Insights locales" vía `llm/insights`). Hoy:

- `backend/app.py:_startup_sync` (`:55`) intenta el sync **en cada arranque de proceso** y solo hace `logger.warning("sync ADO falló: %s", e)` (`:137`) / `logger.warning("sync Jira saltado: %s", e)` (`:82`) — sin memoria entre corridas, así que cada restart (y cada `create_app()` de pytest — ver V7) re-loguea el mismo fallo. **[V]**
- La ruta periódica del board `POST /api/tickets/sync-v2` (`backend/api/tickets.py:5661`) reintenta cada 45 s (`frontend/src/hooks/useTicketSync.ts:38`) y responde **502** vía `_ado_sync_error_response` (`backend/api/tickets.py:293`, ambos branches retornan 502). **[V]**
- `GET /api/tickets/ado-user` (`backend/api/tickets.py:5499`) devuelve **502** ante `AdoApiError` (`:5543`). **[V]**
- `POST /api/llm/insights/<id>/generate` (`backend/api/local_llm_analysis.py:616`) devuelve **502** cuando el modelo local falla (`:639`). **[V]**
- `services/ado_client.py:get_authenticated_user` (`:354`) llama `connectionData` con `api-version={_API_VERSION}` = **`"7.1"`** (`:32`, `:366`), que ADO rechaza como preview → la identidad **nunca resuelve** (D9), contribuyendo a los 502 de `ado-user`. **[V]**

No existe **ningún** mecanismo de backoff/circuit-breaker ni superficie UI de "integración caída". Este es el gap: un patrón único, reutilizable y persistido para degradar integraciones no configuradas.

---

## 3. Principios y guardarraíles (codificados por fase)

1. **Paridad de 3 runtimes:** TODO lo de este plan es **runtime-agnóstico** (capa de tracker + LLM local + endpoints HTTP). No toca ni `services/claude_code_cli_runner.py` ni `services/codex_cli_runner.py` ni el bridge de Copilot. El circuit-breaker y la degradación aplican **idéntico** corran los agentes con Codex CLI, Claude Code CLI o GitHub Copilot Pro. **No hay fallback por runtime porque no hay divergencia por runtime.** (Se declara explícito en cada fase.)
2. **Cero trabajo extra al operador:** todo automático/invisible. El único elemento visible (banner de salud de integraciones) aparece **solo cuando hay un problema** y es informativo. **Excepción dura (c) — prerequisito no garantizado en instalación default:** el PAT de ADO, las credenciales de Jira y el servidor de LLM local son **credenciales/servicios externos** que el operador puede no tener; por eso el estado "no configurado/expirado" es un estado **esperado y degradado**, no un error. El banner de salud + el botón "Reintentar ahora" son la superficie mínima; renovar el PAT sigue siendo acción manual del operador **por diseño de seguridad** (nunca auto-inyectamos credenciales).
3. **Human-in-the-loop:** el breaker **nunca** modifica credenciales ni configuración del operador; solo deja de golpear un endpoint roto y le muestra qué renovar. El "Reintentar ahora" es una acción explícita del operador.
4. **Mono-operador sin auth:** sin RBAC. El estado del breaker es global por instancia (keyed por integración+proyecto), no por usuario.
5. **No degradar / backward-compatible / reusar:** reutiliza `AdoApiError.status_code` (`ado_client.py:62`), `_local_llm_reachable` (`local_insights.py:225`), `runtime_paths.data_dir()`, el registro de flags del arnés (`harness_flags.py`), y la Caja Fuerte (plan 94, `STACKY_DEVOPS_VARIABLES_ENABLED`). No inventa infra nueva de secretos ni de logging.

### Patrón de flags (cumplimiento estricto)

- **Una sola flag nueva:** `STACKY_INTEGRATION_DEGRADATION_ENABLED` (bool, **default ON**, kill-switch). Master que gobierna TODO el comportamiento nuevo (breaker de sync + 200-en-vez-de-502). Con la flag OFF, el sistema vuelve **byte-a-byte** al comportamiento actual (reintenta siempre, 502 crudos). Requiere el **patrón triple**:
  - (i) `FlagSpec(key="STACKY_INTEGRATION_DEGRADATION_ENABLED", type="bool", default=True, ...)` en `backend/services/harness_flags.py` (dentro de `FLAG_REGISTRY`, `:295`).
  - (ii) agregar `"STACKY_INTEGRATION_DEGRADATION_ENABLED"` a `_CURATED_DEFAULTS_ON` en `backend/tests/test_harness_flags.py` (`:467`).
  - (iii) `STACKY_INTEGRATION_DEGRADATION_ENABLED = os.getenv("STACKY_INTEGRATION_DEGRADATION_ENABLED", "true").lower() in ("1","true","yes")` en `backend/config.py` (junto a las flags de la clase `Config`, patrón de `:81`).
  - **Además** (regla dura Plan 63): agregar la key a `_CATEGORY_KEYS["fiabilidad_ciclo_vida"]` en `harness_flags.py` (`:225`) o `test_every_registry_flag_is_categorized` (`:628`) rompe CI.
- **Sin flag** (fix de bug verificado): el fix D9 de `api-version` (F0) **no** lleva flag — corrige código roto (la identidad hoy nunca resuelve), no agrega comportamiento opt-in. Justificado en F0.
- **Sin config nueva del operador por env cruda:** el único parámetro tuneable (ventana de backoff) queda como constante interna del módulo (no es una perilla que el operador deba tocar). Si en el futuro se quiere exponer, va por el arnés (UI), nunca solo env. Para v1 **no se agrega ninguna perilla nueva** → cero carga de config.

---

## 4. Fases

> **Entorno de tests (verificado 2026-07-15):**
> - Backend venv real: `backend/.venv/Scripts/python.exe`. **Correr pytest POR ARCHIVO** (la suite completa contamina cross-file).
>   Comando base: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_XXX.py -q`
> - Frontend: vitest instalado (`frontend/package.json` → `vitest ^4.1.9`). **Correr POR ARCHIVO**: `cd frontend && npx vitest run src/.../XXX.test.ts`

### Orden de dependencias

```
F0 (fix D9, independiente)  ─┐
F1 (breaker core)           ─┼─→ F2 (flag) ─→ F3 (ADO sync) ─→ F5 (200/502) ─→ F6 (UI)
                             └────────────────→ F4 (Jira sync) ┘
```

---

### F0 — Fix D9: `api-version` de `connectionData` bajo preview

**Objetivo (1 frase):** que la resolución de identidad ADO (`get_authenticated_user`) use la `api-version` que ADO acepta para `connectionData`, para que la identidad **resuelva** en vez de fallar como preview.
**Valor:** elimina los 11× `No se pudo resolver identidad ADO para 'me'` y corta en la raíz uno de los dos 502 de `ado-user` (D6).

**Archivo a editar (único):** `backend/services/ado_client.py`

**Cambio exacto:**
1. Agregar, junto a `_API_VERSION = "7.1"` (`:32`), una constante nueva:
   ```python
   _API_VERSION = "7.1"
   # D9 (auditoría 2026-07-15): connectionData es un recurso PREVIEW en ADO; con
   # api-version="7.1" a secas ADO responde "under preview. The -preview flag must
   # be supplied". El sufijo -preview lo resuelve. NO cambiar _API_VERSION global
   # (los endpoints GA wiql/workitems/attachments deben seguir en 7.1 sin sufijo).
   _CONNECTION_DATA_API_VERSION = "7.1-preview"
   ```
2. En `get_authenticated_user` (`:354`), reemplazar la línea `:366`:
   ```python
   # ANTES:
   url = f"{base_org}/_apis/connectionData?api-version={_API_VERSION}"
   # DESPUÉS:
   url = f"{base_org}/_apis/connectionData?api-version={_CONNECTION_DATA_API_VERSION}"
   ```

**Caso borde / fallback [INF]:** si el tenant ADO exigiera un preview versionado (`7.1-preview.1`), el mensaje de error de ADO lo indica textualmente; el fix deja la versión **en una constante única** para ajustarla en un solo lugar. El test (abajo) fija el contrato `-preview` en la URL, no una versión exacta.

**Tests PRIMERO (TDD):** archivo `backend/tests/test_ado_connection_data_api_version.py`
- `test_connection_data_url_uses_preview`: instanciar un `AdoClient` con un PAT dummy (sin red), monkeypatchear `AdoClient._request` para **capturar la URL** que recibe y devolver `{"authenticatedUser": {"uniqueName": "x@y.com", "providerDisplayName": "X"}}`; llamar `get_authenticated_user()`; **assert** que la URL capturada contiene `"/_apis/connectionData?api-version=7.1-preview"`.
- `test_ga_endpoints_still_ga`: assert (por lectura del fuente o por captura análoga en `fetch_states`) que un endpoint GA como `workitemtypes` **NO** lleva `-preview` (sigue `api-version=7.1`), garantizando que no rompimos GA.

Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_ado_connection_data_api_version.py -q`

**Criterio de aceptación (binario):** el test pasa (2 verdes). Verificación: el comando de arriba retorna exit 0 y `2 passed`.
**Flag:** ninguna (bug fix verificado — corrige URL rota; justificado arriba).
**Impacto por runtime:** N/A (capa cliente ADO, idéntico a Codex/Claude/Copilot). Sin fallback específico.
**Trabajo del operador:** ninguno.

---

### F1 — Núcleo del circuit-breaker persistido + clasificador de errores

**Objetivo (1 frase):** un módulo puro y testeable que **persiste** el estado abierto/cerrado de cada integración (con backoff) y **clasifica** el error entrante en una razón legible por máquina.
**Valor:** es la pieza reutilizable que F3/F4/F5/F6 consumen; sin ella, cada consumidor reinventaría el backoff.

**Archivo a crear (único):** `backend/services/integration_breaker.py`

**Contrato exacto:**

```python
"""services/integration_breaker.py — Circuit-breaker persistido para integraciones
no configuradas / caídas (auditoría 2026-07-15: V3 PAT ADO, V8 Jira, D6 LLM/ADO).

Persistido en data_dir()/integration_breaker.json para sobrevivir restarts (el
grueso de los ~941 warnings de V3 viene de re-arranques de proceso + create_app()
de pytest, no de un único daemon). Runtime-agnóstico: nada que ver con el runner
de agentes. NUNCA lanza: ante cualquier problema de IO degrada a "cerrado".
"""
from __future__ import annotations
import json, logging, time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from runtime_paths import data_dir

logger = logging.getLogger("stacky_agents.integration_breaker")

_FILENAME = "integration_breaker.json"

# Backoff: al abrir por fallo terminal de config, no reintentar por esta ventana.
# Constante interna (no perilla del operador en v1).
_BACKOFF_BASE_SEC = 15 * 60          # 15 min tras la 1ª apertura
_BACKOFF_MAX_SEC  = 6 * 60 * 60      # tope 6 h

# Razones (machine-readable). Manejan la copy de la UI y el mensaje de degradación.
REASON_PAT_EXPIRED        = "ado_pat_expired"
REASON_ADO_PROJECT_MISSING= "ado_project_not_found"
REASON_JIRA_NOT_CONFIGURED= "jira_not_configured"
REASON_LOCAL_LLM_DOWN     = "local_llm_unavailable"
REASON_ADO_IDENTITY_UNRESOLVED = "ado_identity_unresolved"
REASON_UNKNOWN            = "unknown"

def _now() -> float: return time.time()
def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")

def integration_key(integration: str, project: str | None) -> str:
    return f"{integration}::{(project or '').upper()}"

def _path() -> Path: return data_dir() / _FILENAME
def _load() -> dict:
    p = _path()
    if not p.exists(): return {}
    try:
        d = json.loads(p.read_text(encoding="utf-8"));  return d if isinstance(d, dict) else {}
    except Exception: return {}
def _save(d: dict) -> None:
    try:
        p = _path(); p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("integration_breaker: no se pudo persistir (degrado a memoria)", exc_info=True)

@dataclass(frozen=True)
class BreakerState:
    open: bool
    reason: str
    message: str
    fail_count: int
    opened_at: str | None
    retry_after: str | None
    seconds_until_retry: int   # 0 si cerrado o si ya pasó la ventana

def should_skip(integration: str, project: str | None) -> bool:
    """True = breaker abierto Y todavía dentro de la ventana de backoff → NO golpear la red."""
    e = _load().get(integration_key(integration, project))
    if not e or not e.get("open"): return False
    return _now() < float(e.get("retry_after_ts") or 0)

def record_failure(integration: str, project: str | None, reason: str, message: str) -> BreakerState:
    """Registra un fallo terminal de config: abre el breaker con backoff exponencial.
    Loguea WARNING SOLO en la transición cerrado→abierto (dedup); mientras siga
    abierto, DEBUG. Devuelve el estado resultante."""
    d = _load(); k = integration_key(integration, project)
    prev = d.get(k) or {}
    was_open = bool(prev.get("open"))
    fail_count = int(prev.get("fail_count") or 0) + 1
    backoff = min(_BACKOFF_BASE_SEC * (2 ** max(0, fail_count - 1)), _BACKOFF_MAX_SEC)
    now = _now(); retry_ts = now + backoff
    d[k] = {"open": True, "reason": reason, "message": message[:500], "fail_count": fail_count,
            "opened_at": prev.get("opened_at") or _iso(now), "opened_at_ts": prev.get("opened_at_ts") or now,
            "retry_after": _iso(retry_ts), "retry_after_ts": retry_ts,
            "last_error_at": _iso(now)}
    _save(d)
    if not was_open:
        logger.warning("integración '%s' (proyecto=%s) DESACTIVADA por %s: %s — reintento tras %s",
                       integration, project or "-", reason, message[:200], _iso(retry_ts))
    else:
        logger.debug("integración '%s' sigue abierta (fail_count=%d)", integration, fail_count)
    return get_state(integration, project)

def record_success(integration: str, project: str | None) -> None:
    """Cierra el breaker (reset) al primer éxito. Loguea INFO solo si venía abierto."""
    d = _load(); k = integration_key(integration, project)
    if d.get(k, {}).get("open"):
        logger.info("integración '%s' (proyecto=%s) RESTABLECIDA", integration, project or "-")
    if k in d: d.pop(k, None); _save(d)

def reset(integration: str, project: str | None) -> None:
    """Cierre manual (acción del operador: 'Reintentar ahora' / renovó credencial)."""
    d = _load(); k = integration_key(integration, project)
    if k in d: d.pop(k, None); _save(d)

def get_state(integration: str, project: str | None) -> BreakerState:
    e = _load().get(integration_key(integration, project))
    if not e or not e.get("open"):
        return BreakerState(False, "", "", 0, None, None, 0)
    retry_ts = float(e.get("retry_after_ts") or 0)
    return BreakerState(True, e.get("reason") or REASON_UNKNOWN, e.get("message") or "",
                        int(e.get("fail_count") or 0), e.get("opened_at"), e.get("retry_after"),
                        max(0, int(retry_ts - _now())))

def all_states() -> dict[str, BreakerState]:
    return {k: get_state(*k.split("::", 1)) for k in _load().keys()}
```

**Clasificador** — mismo módulo, función pura:

```python
def classify_ado_error(exc) -> tuple[str, str]:
    """(reason, message) a partir de un AdoApiError. Substrings verificados contra
    los mensajes reales del reporte (V3/D9)."""
    msg = str(getattr(exc, "detail", "") or "") + " " + str(exc)
    low = msg.lower()
    if "personal access token used has expired" in low or "access denied" in low:
        return REASON_PAT_EXPIRED, "El PAT de Azure DevOps expiró. Renovalo en la Caja Fuerte."
    if "does not exist" in low and "project" in low:
        return REASON_ADO_PROJECT_MISSING, "El proyecto ADO configurado no existe. Revisá el nombre en la config del proyecto."
    if getattr(exc, "status_code", None) in (401, 403):
        return REASON_PAT_EXPIRED, "ADO rechazó el PAT (401/403). Renovalo en la Caja Fuerte."
    return REASON_UNKNOWN, str(exc)[:200]
```

> **Nota de diseño clave [V]:** el string de log exacto `"sync ADO falló:"` / `"sync Jira saltado:"` vive **solo** en `app.py:_startup_sync` (arranque), y la ruta periódica del board usa `_ado_sync_error_response` (otro string). Por eso el estado del breaker **debe persistirse a disco** (no ser per-proceso): así el arranque siguiente (y cada `create_app()` de pytest) consulta `should_skip()` y no re-loguea. Esto es lo que colapsa los 941 warnings a ~1 por transición.

**Tests PRIMERO (TDD):** archivo `backend/tests/test_integration_breaker.py` (monkeypatchear `data_dir` a un `tmp_path` para aislar el JSON)
- `test_closed_by_default`: `should_skip("ado_sync", "RSPACIFICO")` → `False`; `get_state(...).open` → `False`.
- `test_record_failure_opens_and_skips`: `record_failure("ado_sync","RSPACIFICO",REASON_PAT_EXPIRED,"x")` → `open=True`; luego `should_skip(...)` → `True`.
- `test_warning_only_on_transition`: con `caplog`, dos `record_failure` seguidos → **exactamente 1** registro WARNING (el segundo es DEBUG).
- `test_backoff_doubles`: dos fallos → el `seconds_until_retry` del 2º ≥ el del 1º (chequear `retry_after_ts` crece).
- `test_retry_window_expires`: tras abrir, monkeypatchear `_now` para saltar más allá de `retry_after_ts` → `should_skip(...)` → `False` (half-open: permite un reintento).
- `test_record_success_closes`: abrir, luego `record_success(...)` → `should_skip(...)` False y `get_state(...).open` False.
- `test_reset_closes`: idem con `reset(...)`.
- `test_classify_pat_expired`: `AdoApiError("... The Personal Access Token used has expired.")` → `REASON_PAT_EXPIRED`.
- `test_classify_project_missing`: `AdoApiError("The following project does not exist: RSPACIFICO")` → `REASON_ADO_PROJECT_MISSING`.
- `test_persistence_across_reload`: abrir, recargar el módulo (o llamar `_load` fresco) → sigue abierto (verifica persistencia en disco).
- `test_io_failure_degrades_closed`: monkeypatchear `data_dir` a una ruta imposible → `should_skip` no lanza y devuelve `False`.

Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_integration_breaker.py -q`
**Criterio de aceptación (binario):** 11 verdes; exit 0.
**Flag:** ninguna (módulo de infraestructura; el comportamiento observable lo activan sus consumidores bajo la flag de F2). Justificado: no cambia nada por sí solo.
**Impacto por runtime:** N/A (infra pura). Sin fallback específico.
**Trabajo del operador:** ninguno.

---

### F2 — Flag master `STACKY_INTEGRATION_DEGRADATION_ENABLED` (patrón triple)

**Objetivo (1 frase):** registrar el kill-switch que gobierna todo el comportamiento nuevo (breaker + 200/502), default ON, con revert byte-a-byte al ponerse OFF.
**Valor:** reversibilidad total sin tocar código; cumple la regla dura de flags del repo.

**Archivos a editar (tres + un test):**

1. `backend/services/harness_flags.py` — dentro de `FLAG_REGISTRY` (`:295`), agregar un `FlagSpec` (junto a las de fiabilidad/ciclo de vida):
   ```python
   FlagSpec(
       key="STACKY_INTEGRATION_DEGRADATION_ENABLED",
       type="bool",
       default=True,  # kill-switch, default ON (curada en _CURATED_DEFAULTS_ON)
       label="Degradación explícita de integraciones no configuradas",
       description=(
           "Circuit-breaker + backoff para ADO/Jira/LLM local cuando no están "
           "configurados o caídos: deja de reintentar cada ciclo, muestra el estado "
           "en la UI y responde 200 available/linked:false en vez de 502. OFF = "
           "comportamiento previo (reintenta siempre, 502 crudos)."
       ),
       group="global",
       env_only=False,
   ),
   ```
2. `backend/services/harness_flags.py` — en `_CATEGORY_KEYS["fiabilidad_ciclo_vida"]` (`:225`), agregar la key:
   ```python
   "STACKY_INTEGRATION_DEGRADATION_ENABLED",  # Plan 148 — degradación de integraciones
   ```
3. `backend/config.py` — en la clase `Config` (patrón de `:81`), agregar:
   ```python
   # Plan 148 — Degradación explícita de integraciones no configuradas. Default ON
   # (kill-switch). Espejo del default=True de la FlagSpec homónima.
   STACKY_INTEGRATION_DEGRADATION_ENABLED = os.getenv(
       "STACKY_INTEGRATION_DEGRADATION_ENABLED", "true"
   ).lower() in ("1", "true", "yes")
   ```
4. `backend/tests/test_harness_flags.py` — en `_CURATED_DEFAULTS_ON` (`:467`), agregar:
   ```python
   "STACKY_INTEGRATION_DEGRADATION_ENABLED",   # Plan 148
   ```

**Tests PRIMERO (TDD):** los tests centinela YA existen y deben quedar verdes con los 4 puntos:
- `test_default_known_only_for_curated` (`backend/tests/test_harness_flags.py:700`) — falla si la FlagSpec tiene `default=True` pero la key NO está en `_CURATED_DEFAULTS_ON` (o viceversa).
- `test_every_registry_flag_is_categorized` (`:628`) — falla si la key no está en ningún `_CATEGORY_KEYS`.
- **Nuevo** `test_plan148_flag_default_on` en `backend/tests/test_plan148_integration_degradation.py`: `from config import Config; assert Config().STACKY_INTEGRATION_DEGRADATION_ENABLED is True` (con env limpio).

Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_harness_flags.py backend/tests/test_plan148_integration_degradation.py -q`
**Criterio de aceptación (binario):** ambos archivos verdes; exit 0. Si falta cualquiera de los 4 puntos, `test_default_known_only_for_curated` o `test_every_registry_flag_is_categorized` fallan → señal directa.
**Flag:** esta fase ES la flag.
**Impacto por runtime:** N/A (config global). Sin fallback.
**Trabajo del operador:** ninguno (opt-in con default ON; visible/toggleable desde el panel de flags del Arnés porque toda FlagSpec del registro se renderiza ahí — Plan 33/86).

---

### F3 — Cablear el breaker en el sync de ADO (V3)

**Objetivo (1 frase):** que el sync ADO consulte `should_skip` antes de golpear la red, y ante PAT expirado / proyecto inexistente registre el fallo en el breaker (dedup) en vez de re-warnear cada ciclo.
**Valor:** colapsa 941 warnings a ~1 por transición; deja de martillar ADO con un PAT muerto.

**Archivos a editar (dos):**

**(a) `backend/app.py` — `_startup_sync` (`:105-139`, branch ADO):**
Antes de construir el cliente y llamar `_ado_sync`, si la flag está ON, chequear el breaker; envolver el `except AdoApiError` para clasificar y registrar:
```python
# dentro del branch else (ADO), reemplazar el bloque try/except AdoApiError:
from services import integration_breaker as _brk
_degr = getattr(config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True)
if _degr and _brk.should_skip("ado_sync", target_project):
    logger.debug("sync ADO omitido: breaker abierto para %s", target_project)
else:
    try:
        from services.project_context import build_ado_client
        client = build_ado_client(project_name=active) if active else None
        result = _ado_sync(client=client)
        if _degr:
            _brk.record_success("ado_sync", target_project)
        logger.info("sync ADO ok: project=%s fetched=%d created=%d updated=%d removed=%d",
                    result["project"], result["fetched"], result["created"],
                    result["updated"], result["removed"])
    except AdoConfigError as e:
        logger.warning("sync ADO saltado: %s", e)
    except AdoApiError as e:
        if _degr:
            reason, message = _brk.classify_ado_error(e)
            _brk.record_failure("ado_sync", target_project, reason, message)  # WARNING solo en transición
        else:
            logger.warning("sync ADO falló: %s", e)
    except Exception:
        logger.exception("sync ADO error inesperado en arranque")
```
> Con la flag OFF, el `else` conserva `logger.warning("sync ADO falló: %s", e)` **idéntico** al actual (`app.py:137`) → revert byte-a-byte.

**(b) `backend/api/tickets.py` — ruta periódica `sync-v2` (`:5661`) y `sync` (`:702`):**
En `_ado_sync_error_response` (`:293`), cuando la flag está ON, además de responder, registrar el fallo en el breaker. Insertar al inicio de la función (antes de los returns), pero **solo** registrar (no cambiar el status todavía — el 200 lo hace F5 para `ado-user`; para `sync`/`sync-v2` mantener 502 porque el board ya hace backoff propio con `useTicketSync` y muestra `syncError`):
```python
def _ado_sync_error_response(exc, *, route_label, project_name):
    from config import config as _cfg
    if getattr(_cfg, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        from services import integration_breaker as _brk
        ctx0 = resolve_project_context(project_name=project_name)
        _tp = (ctx0.tracker_project if ctx0 else None) or project_name
        reason, message = _brk.classify_ado_error(exc)
        _brk.record_failure("ado_sync", _tp, reason, message)
    ...  # resto igual
```
> **Importante:** la ruta `sync-v2` sigue devolviendo 502 (el board la maneja); lo que cambia es que ahora **alimenta el breaker**, de modo que el próximo `_startup_sync` y el endpoint `ado-user` (F5) ya saben que ADO está caído. No se toca el flujo del board.

**Impacto por runtime:** N/A (capa tracker; corran los agentes con el runtime que sea, el sync ADO es el mismo). Sin fallback por runtime.

**Tests PRIMERO (TDD):** archivo `backend/tests/test_plan148_ado_sync_breaker.py`
- `test_startup_sync_records_failure_on_pat_expired`: monkeypatchear `_ado_sync` para lanzar `AdoApiError("... The Personal Access Token used has expired.", status_code=401)`; correr `_startup_sync(logger)` con proyecto activo dummy y `data_dir`→tmp; assert `integration_breaker.get_state("ado_sync", <proj>).open` True y `reason==REASON_PAT_EXPIRED`.
- `test_startup_sync_skips_when_open`: pre-abrir el breaker; monkeypatchear `_ado_sync` con un mock que registre si fue llamado; correr `_startup_sync`; assert que `_ado_sync` **no** se llamó.
- `test_flag_off_preserves_legacy_warning`: con `STACKY_INTEGRATION_DEGRADATION_ENABLED` monkeypatcheada a False, `_ado_sync` lanza `AdoApiError`; `caplog` debe contener `"sync ADO falló:"` y el breaker debe seguir cerrado.
- `test_sync_v2_feeds_breaker`: llamar `_ado_sync_error_response(AdoApiError(... expired, status_code=401), route_label="sync-v2", project_name="RSPACIFICO")`; assert status 502 (sin cambio) **y** breaker abierto.
- `test_success_closes_breaker`: pre-abrir; monkeypatchear `_ado_sync` para devolver un dict OK; `_startup_sync`; assert breaker cerrado.

Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan148_ado_sync_breaker.py -q`
**Criterio de aceptación (binario):** 5 verdes; exit 0.
**Flag:** `STACKY_INTEGRATION_DEGRADATION_ENABLED` (default ON). OFF → warning legacy intacto.
**Trabajo del operador:** ninguno.

---

### F4 — Cablear el breaker en el sync de Jira (V8)

**Objetivo (1 frase):** que el sync Jira, cuando no hay credenciales (`JiraConfigError`), registre el fallo una vez en el breaker y deje de warnear cada ciclo.
**Valor:** colapsa 448 warnings a ~1 por transición.

**Archivo a editar (único):** `backend/app.py` — `_startup_sync` (`:71-86`, branch Jira):
```python
if tracker_type == "jira":
    from services.jira_sync import sync_tickets as jira_sync
    from services.jira_client import JiraApiError, JiraConfigError
    from services import integration_breaker as _brk
    _degr = getattr(config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True)
    _jira_proj = (tracker.get("project") or "").strip() or None
    if _degr and _brk.should_skip("jira_sync", _jira_proj):
        logger.debug("sync Jira omitido: breaker abierto")
    else:
        try:
            result = jira_sync(tracker_config=tracker)
            if _degr:
                _brk.record_success("jira_sync", _jira_proj)
            logger.info("sync Jira ok: project=%s fetched=%d created=%d updated=%d removed=%d",
                        result["project"], result["fetched"], result["created"],
                        result["updated"], result["removed"])
        except JiraConfigError as e:
            if _degr:
                _brk.record_failure("jira_sync", _jira_proj,
                                    _brk.REASON_JIRA_NOT_CONFIGURED,
                                    "Credenciales Jira no configuradas. Cargalas en la Caja Fuerte.")
            else:
                logger.warning("sync Jira saltado: %s", e)
        except JiraApiError as e:
            logger.warning("sync Jira falló: %s", e)
        except Exception:
            logger.exception("sync Jira error inesperado en arranque")
```
> Con la flag OFF, `logger.warning("sync Jira saltado: %s", e)` queda **idéntico** al actual (`app.py:82`).

**Nota:** `JiraConfigError` es un fallo terminal de config (no transitorio) → abrir con backoff largo es correcto. `JiraApiError` (Jira caído transitoriamente) se deja como warning legacy (no lo silenciamos: puede ser un blip, no una desconfiguración).

**Impacto por runtime:** N/A (tracker). Sin fallback por runtime.

**Tests PRIMERO (TDD):** archivo `backend/tests/test_plan148_jira_sync_breaker.py`
- `test_jira_missing_creds_opens_breaker`: proyecto activo con `issue_tracker.type=="jira"`; monkeypatchear `jira_sync` para lanzar `JiraConfigError("Credenciales Jira no encontradas...")`; `_startup_sync`; assert breaker `jira_sync` abierto, `reason==REASON_JIRA_NOT_CONFIGURED`.
- `test_jira_skips_when_open`: pre-abrir; `jira_sync` mock; assert no llamado.
- `test_jira_flag_off_legacy_warning`: flag OFF → `caplog` contiene `"sync Jira saltado:"`.
- `test_jira_api_error_still_warns`: `JiraApiError` → warning `"sync Jira falló:"` y breaker cerrado (no lo abre un blip transitorio).

Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan148_jira_sync_breaker.py -q`
**Criterio de aceptación (binario):** 4 verdes; exit 0.
**Flag:** `STACKY_INTEGRATION_DEGRADATION_ENABLED` (default ON).
**Trabajo del operador:** ninguno.

---

### F5 — Degradación 200-en-vez-de-502 (D6: LLM local + identidad ADO)

**Objetivo (1 frase):** que `POST /api/llm/insights/<id>/generate` y `GET /api/tickets/ado-user` respondan **200 con `available/linked:false` + `reason`** cuando la causa es "integración no disponible", en vez de 502 que rompe la UI.
**Valor:** las pantallas "Insights locales" y "Mis tareas" degradan limpio (muestran "no disponible" en vez de romperse).

**Archivo (a) `backend/api/local_llm_analysis.py` — `generate_insight_route` (`:616-639`):**
Antes del `return jsonify(result), 502` final (`:639`), interceptar el caso "LLM local inalcanzable":
```python
    err = result.get("error")
    if err == "execution_not_found":
        return jsonify(result), 404
    if err == "insight_excluded":
        return jsonify(result), 409
    # D6 — degradación explícita: si la generación falló porque el modelo local
    # está caído/no instalado, NO 502 (rompe la UI). Responder 200 available:false.
    if getattr(_config.config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        from services.local_insights import _local_llm_reachable
        if not _local_llm_reachable():
            from services import integration_breaker as _brk
            _brk.record_failure("local_llm", None, _brk.REASON_LOCAL_LLM_DOWN,
                                "El modelo local no está disponible (servidor caído o modelo no instalado).")
            return jsonify({
                "ok": False, "available": False, "reason": _brk.REASON_LOCAL_LLM_DOWN,
                "message": "El modelo local no está disponible. Verificá que Ollama/servidor local esté corriendo.",
                "execution_id": execution_id,
            }), 200
    return jsonify(result), 502
```
> El 502 se conserva para errores **genuinos** (el modelo respondió basura pero está vivo): esos SÍ son fallo real, no "no disponible".

**Archivo (b) `backend/api/tickets.py` — `get_ado_user` (`:5540-5546`):**
Cambiar el branch `except (AdoApiError, _AdoApiError)` para que, con la flag ON, devuelva **200 linked:false** (alineado con el patrón que el propio endpoint ya usa en `:5548` cuando no hay `unique_name`):
```python
    except (AdoApiError, _AdoApiError) as exc:
        if getattr(config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
            from services import integration_breaker as _brk
            reason, message = _brk.classify_ado_error(exc)
            _brk.record_failure("ado_identity", project_name, reason, message)
            return jsonify({
                "ok": True, "linked": False, "degraded": True,
                "reason": reason, "message": message, "source": "ado",
                "stacky_user": stacky_user, "project": project_name,
                "ado_status_code": getattr(exc, "status_code", None),
            }), 200
        return _ado_sync_error_response(exc, route_label="ado-user", project_name=project_name)
```
> Con la flag OFF, cae al `_ado_sync_error_response` actual (502). El `except Exception` genérico (`:5544`) sigue devolviendo **500** para fallos verdaderamente inesperados (no lo tocamos).

**Frontend (mínimo):** el endpoint ya devolvía `linked:false` como caso válido (`:5548`), así que el consumidor de "Mis tareas" ya tolera `linked:false`. Verificar en `frontend/src/pages/TicketBoard.tsx` que no exista un `throw` ante `!ok` de `ado-user`; como el nuevo shape mantiene `ok:true, linked:false`, el board no rompe. **No se requiere cambio de frontend en F5** (la UI de banner llega en F6). [INF] sobre el consumidor exacto — el implementador debe confirmar con grep de `ado-user`/`adoUser` en `frontend/src` que se lee `linked`, no el status HTTP.

**Impacto por runtime:** N/A (endpoints HTTP, iguales para los 3 runtimes). Sin fallback por runtime.

**Tests PRIMERO (TDD):** archivo `backend/tests/test_plan148_graceful_degradation.py`
- `test_insights_llm_down_returns_200_available_false`: `STACKY_LOCAL_INSIGHTS_ENABLED`/`LOCAL_LLM_ENABLED` ON; monkeypatchear `generate_insight_for_execution` → `{"ok":False,"error":"generation_failed",...}` y `_local_llm_reachable` → False; POST al endpoint; assert status **200** y body `available is False`, `reason=="local_llm_unavailable"`.
- `test_insights_genuine_error_still_502`: `_local_llm_reachable` → True (modelo vivo) y `generate_insight_for_execution` → error genérico; assert status **502** (no degradamos un fallo real).
- `test_insights_flag_off_still_502`: flag master OFF → 502 aún con LLM caído (revert).
- `test_ado_user_api_error_returns_200_linked_false`: monkeypatchear el provider/cliente para lanzar `AdoApiError("...expired", status_code=401)`; GET `ado-user`; assert **200**, `linked is False`, `reason=="ado_pat_expired"`, y breaker `ado_identity` abierto.
- `test_ado_user_flag_off_502`: flag OFF → 502 (revert).
- `test_ado_user_unexpected_still_500`: forzar `Exception` genérica (no `AdoApiError`) → 500 sin tocar (no degradamos bugs).

Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan148_graceful_degradation.py -q`
**Criterio de aceptación (binario):** 6 verdes; exit 0. Además, `backend/tests/test_plan117_insights_api.py` debe seguir verde (los casos 404/409 no cambian).
Comando de regresión: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan117_insights_api.py -q`
**Flag:** `STACKY_INTEGRATION_DEGRADATION_ENABLED` (default ON).
**Trabajo del operador:** ninguno.

---

### F6 — Superficie UI: estado de integraciones + "Reintentar ahora" + limpieza al renovar credencial

**Objetivo (1 frase):** exponer el estado del breaker como un endpoint read-only + un banner discreto que solo aparece si hay una integración caída, con acción "Reintentar ahora" y link a la Caja Fuerte; y **limpiar el breaker** cuando el operador guarda credenciales.
**Valor:** convierte los warnings mudos en una superficie accionable ("PAT ADO expirado — renová en Caja Fuerte"), sin sacar al operador del lazo.

**Archivo (a) `backend/api/integrations.py` (nuevo blueprint):**
```python
"""api/integrations.py — Plan 148. Estado de salud de integraciones (read-only) +
reset manual. Registrado en backend/api/__init__.py (patrón del repo: los blueprints
se registran en __init__.py, NO en app.py)."""
from flask import Blueprint, jsonify, request
bp = Blueprint("integrations", __name__, url_prefix="/integrations")

_LABELS = {
    "ado_pat_expired": {"title": "PAT de Azure DevOps expirado",
        "action": "Renová el PAT en la Caja Fuerte", "vault": True},
    "ado_project_not_found": {"title": "Proyecto ADO inexistente",
        "action": "Revisá el nombre del proyecto en la config", "vault": False},
    "jira_not_configured": {"title": "Jira sin credenciales",
        "action": "Cargá las credenciales de Jira en la Caja Fuerte", "vault": True},
    "local_llm_unavailable": {"title": "Modelo local no disponible",
        "action": "Iniciá el servidor local (Ollama) o instalá el modelo", "vault": False},
    "ado_identity_unresolved": {"title": "Identidad ADO no resuelta",
        "action": "Renová el PAT en la Caja Fuerte", "vault": True},
}

@bp.get("/status")
def integrations_status():
    from config import config
    if not getattr(config, "STACKY_INTEGRATION_DEGRADATION_ENABLED", True):
        return jsonify({"enabled": False, "integrations": []})
    from services import integration_breaker as _brk
    out = []
    for key, st in _brk.all_states().items():
        if not st.open:  # solo reportar las caídas
            continue
        meta = _LABELS.get(st.reason, {"title": st.reason, "action": "", "vault": False})
        integ, _, project = key.partition("::")
        out.append({"key": key, "integration": integ, "project": project,
                    "reason": st.reason, "title": meta["title"], "action": meta["action"],
                    "vault": meta["vault"], "message": st.message,
                    "retry_after": st.retry_after, "seconds_until_retry": st.seconds_until_retry})
    return jsonify({"enabled": True, "integrations": out})

@bp.post("/<integration>/reset")
def integrations_reset(integration: str):
    """Acción HITL: el operador pide reintentar YA (tras renovar la credencial)."""
    from services import integration_breaker as _brk
    project = (request.args.get("project") or request.json.get("project") if request.is_json else None) if False else request.args.get("project")
    _brk.reset(integration, project)
    return jsonify({"ok": True, "integration": integration, "project": project})
```
> Registrar `bp` en `backend/api/__init__.py` (gotcha del repo: los blueprints se registran en `api/__init__.py`, **no** en `app.py`). Confirmar el patrón exacto leyendo cómo se registra, p. ej., el blueprint de `local_llm_analysis`.

**Archivo (b) limpieza al renovar credencial:** cuando el operador guarda un secreto de ADO/Jira desde la Caja Fuerte, limpiar el breaker para que el próximo sync reintente sin esperar el backoff. Buscar el write-site de secretos (grep `write_json_file`/`resolve_secret_in_payload` en `backend/api/global_config.py` y en el guardado de `auth/ado_auth.json` / `auth/jira_auth.json`). En ese punto (tras persistir), llamar:
```python
from services import integration_breaker as _brk
_brk.reset("ado_sync", project);   _brk.reset("ado_identity", project)   # o jira_sync según el secreto guardado
```
> **[INF]** el write-site exacto del secreto debe confirmarse por grep antes de editar; si no hay un único punto claro, el botón "Reintentar ahora" (endpoint reset) es suficiente como fallback HITL y esta sub-tarea puede quedar como mejora aditiva. **No inventar** un flujo nuevo de guardado.

**Archivo (c) frontend — `frontend/src/components/IntegrationHealthBanner.tsx` (nuevo):**
Componente que hace `GET /api/integrations/status` (refetch cada 60 s), y **si `integrations.length > 0`** renderiza una tira discreta (una fila por integración caída) con: `title`, `action`, botón "Reintentar ahora" (POST `/api/integrations/<integration>/reset?project=<project>` → invalida la query), y si `vault:true` un link a la Caja Fuerte (ruta existente del panel de variables/secretos — confirmar con grep del route de la Caja Fuerte, plan 94). Si `integrations` está vacío, **no renderiza nada** (cero ruido cuando todo está sano).
- Agregar el cliente en `frontend/src/api/endpoints.ts`: `Integrations.status()` y `Integrations.reset(integration, project)` usando `apiBase` (patrón de `useTicketSync.ts:90`).
- Montar `<IntegrationHealthBanner/>` en `frontend/src/pages/TicketBoard.tsx` (donde vive `useTicketSync`, la superficie natural para "ADO caído") — al tope del board. **[INF]** confirmar el punto de montaje leyendo `TicketBoard.tsx`.

**Impacto por runtime:** N/A (UI/HTTP). Sin fallback por runtime.

**Tests PRIMERO (TDD):**
- Backend `backend/tests/test_plan148_integrations_api.py`:
  - `test_status_empty_when_all_healthy`: sin breakers abiertos → `{"enabled":True,"integrations":[]}`.
  - `test_status_lists_open_breaker`: abrir `ado_sync` con PAT expirado → status lista 1 item con `reason=="ado_pat_expired"`, `vault is True`, `title` no vacío.
  - `test_status_disabled_when_flag_off`: flag OFF → `{"enabled":False,"integrations":[]}`.
  - `test_reset_closes_breaker`: abrir; POST `/integrations/ado_sync/reset?project=RSPACIFICO`; assert breaker cerrado (`get_state(...).open` False).
  Comando: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_plan148_integrations_api.py -q`
- Frontend `frontend/src/components/__tests__/IntegrationHealthBanner.test.tsx`:
  - `renders nothing when no integrations down` (mock fetch → `{enabled:true,integrations:[]}` → contenedor vacío).
  - `renders a row with action when an integration is down` (mock → 1 item → aparece el `title` y el botón "Reintentar ahora").
  > **Gotcha verificado (memoria):** `@testing-library/react` + `jsdom` NO están en `package.json` del frontend. Si el test de componente no puede correr por ese gap estructural, degradar a un **test de la función pura de mapeo** (p. ej. `shouldRender(integrations)`) en `frontend/src/components/__tests__/integrationHealth.logic.test.ts` con vitest (que sí corre), y dejar el smoke visual como verificación manual. Declararlo en el reporte de implementación (cero falsos verdes).
  Comando: `cd frontend && npx vitest run src/components/__tests__/IntegrationHealthBanner.test.tsx` (o el `.logic.test.ts` si aplica el fallback).

**Criterio de aceptación (binario):** backend 4 verdes (exit 0); frontend: el test de lógica pura verde (el de componente puede quedar como manual si el gap RTL/jsdom lo impide, declarado). Smoke manual: con un PAT expirado, el board muestra la tira "PAT de Azure DevOps expirado — Renová el PAT en la Caja Fuerte"; al hacer "Reintentar ahora" desaparece y se dispara un sync.
**Flag:** `STACKY_INTEGRATION_DEGRADATION_ENABLED` (default ON) — con OFF, `/status` responde `enabled:false` y el banner no muestra nada.
**Trabajo del operador:** ninguno para ver el estado; renovar la credencial es acción manual **por diseño de seguridad** (excepción dura (c), ya citada en §3).

---

## 5. Riesgos y mitigaciones

| # | Riesgo | Mitigación |
|---|---|---|
| R1 | El breaker abierto **enmascara** que ADO volvió antes del backoff. | Ventana half-open: pasado `retry_after_ts`, `should_skip` devuelve False y se reintenta; un éxito cierra el breaker. Además "Reintentar ahora" (F6) fuerza cierre inmediato. |
| R2 | 200-en-vez-de-502 **oculta fallos reales** al monitoreo. | Se degrada **solo** ante causas clasificadas como "no disponible/no configurado". Errores genuinos (LLM vivo pero responde mal; `Exception` inesperada) **siguen** en 502/500. El body lleva `degraded:true`/`reason` machine-readable. |
| R3 | `api-version=7.1-preview` podría no ser exactamente la que el tenant exige. | El fix está en **una constante única**; el test fija el contrato `-preview` (no una versión exacta). El error de ADO indica la versión precisa si hiciera falta `7.1-preview.1`. **[INF]** |
| R4 | Persistencia del breaker corrupta / disco no escribible. | `_load`/`_save` degradan a `{}`/no-op silencioso (test `test_io_failure_degrades_closed`); nunca lanzan → jamás rompen el arranque ni un request. |
| R5 | La flag OFF debe volver **exacto** al comportamiento previo. | Cada branch conserva el path legacy literal (`"sync ADO falló:"`, `"sync Jira saltado:"`, 502) tras `if _degr: ... else: <legacy>`. Tests `*_flag_off_*` lo fijan. |
| R6 | El write-site del secreto (F6-b) no es un único punto claro. | F6-b es **aditivo/opcional**; el botón "Reintentar ahora" (endpoint reset) cubre el caso HITL. No bloquea el plan. **[INF]** |
| R7 | Cross-ref 145 (dedup helper) aún no implementado. | El breaker **es** el mecanismo de dedup (WARNING solo en transición). No depende de 145; si 145 aporta un rate-limiter, se puede sumar luego sin cambiar contratos. |

---

## 6. Fuera de scope

- **D1/D2/D3/D4** (trust de workspace, stall watchdog, reaper, enum de estados terminales) → **Plan 144**. No se tocan aquí.
- **404 de `pipeline/status`, strip ANSI, aislar logging de pytest, rate-limit genérico de preflight** → **Plan 145**. Este plan **no** implementa el helper de dedup general; usa el breaker como dedup local.
- **Fix import `Execution`→`AgentExecution`, mkdir del SQLite ledger, re-deploy con `CLAUDE_CODE_CLI_MODEL_FALLBACK`** → **Plan 146**.
- **Resolución robusta de `outputs_dir`/`repo_root` + estado UI de watchers (V2/D8)** → **Plan 147**.
- **Intake de `pending-task.json` inválido (D5) + excepciones tipadas en endpoints devops/console y agents/run (V6)** → **Plan 149**.
- **No** se cambia el flujo del board (`useTicketSync` sigue con su backoff propio; `sync-v2` sigue en 502): solo se lo alimenta al breaker.
- **No** se auto-renuevan ni auto-inyectan credenciales (prohibido por seguridad/HITL).
- **No** se agrega ninguna perilla de config nueva para el operador (backoff = constante interna).

---

## 7. Glosario + Orden de implementación + DoD

### Glosario (términos Stacky usados)
- **Circuit-breaker / breaker:** estado persistido (abierto/cerrado) que evita reintentar una integración caída; con backoff exponencial y half-open.
- **Patrón triple de flag:** FlagSpec `default=True` + key en `_CURATED_DEFAULTS_ON` + default `"true"` en `config.py`; si falta uno, `test_default_known_only_for_curated` rompe.
- **Caja Fuerte:** panel de variables/secretos del plan 94 (`STACKY_DEVOPS_VARIABLES_ENABLED`), fuente única de credenciales; aquí solo se **linkea** (nunca se escribe automáticamente).
- **`_startup_sync`:** `backend/app.py:55`, sincroniza tickets del proyecto activo en cada `create_app()`; fuente de los strings `"sync ADO falló:"` / `"sync Jira saltado:"`.
- **`AdoApiError`:** `services/ado_client.py:62`, lleva `status_code`/`detail`; base de la clasificación de razones.
- **Degradación explícita:** responder 200 con `available/linked:false` + `reason` en vez de 5xx cuando la integración no está disponible.

### Orden de implementación (numerado)
1. **F0** — fix D9 `api-version` de `connectionData` (independiente; podés hacerlo primero para cortar los 11× de identidad).
2. **F1** — módulo `integration_breaker.py` + clasificador (infra; sin efecto observable aún).
3. **F2** — flag `STACKY_INTEGRATION_DEGRADATION_ENABLED` (patrón triple + categoría).
4. **F3** — cablear breaker en sync ADO (`app.py` + `_ado_sync_error_response`).
5. **F4** — cablear breaker en sync Jira (`app.py`).
6. **F5** — 200/502 en `insights` y `ado-user`.
7. **F6** — endpoint `/api/integrations/status` + `/reset` + banner UI + limpieza al renovar credencial (aditivo).

> Dependencias: F2 antes de F3/F4/F5/F6 (consumen la flag). F1 antes de F3/F4/F5/F6 (consumen el breaker). F0 es independiente. F6 depende de F1–F5.

### Definición de Hecho (DoD) global
- [ ] F0 verde: `test_ado_connection_data_api_version.py` (2/2); connectionData usa `-preview`, GA intactos.
- [ ] F1 verde: `test_integration_breaker.py` (11/11); breaker persiste, backoff, dedup, degrada a cerrado ante IO.
- [ ] F2 verde: `test_harness_flags.py` + `test_plan148_integration_degradation.py`; flag default ON, curada y categorizada.
- [ ] F3 verde: `test_plan148_ado_sync_breaker.py` (5/5); ADO abre/omite/cierra; flag OFF preserva warning legacy.
- [ ] F4 verde: `test_plan148_jira_sync_breaker.py` (4/4); Jira sin creds abre 1 vez; flag OFF legacy.
- [ ] F5 verde: `test_plan148_graceful_degradation.py` (6/6) + `test_plan117_insights_api.py` sin regresión; 200 solo ante "no disponible", 502/500 reales intactos.
- [ ] F6 verde: `test_plan148_integrations_api.py` (4/4); front: test de lógica pura verde (componente RTL/jsdom = manual si aplica el gap, declarado).
- [ ] **Cero regresión con flag OFF:** un smoke con `STACKY_INTEGRATION_DEGRADATION_ENABLED=false` reproduce el comportamiento previo (reintenta, 502).
- [ ] **Verificación por el agente principal (no delegada):** correr cada archivo de test por separado con `backend/.venv/Scripts/python.exe` y **pegar el output real** (regla anti-falso-verde). Vitest por archivo.
- [ ] **Paridad de runtimes declarada:** confirmado que ningún cambio toca `claude_code_cli_runner.py`/`codex_cli_runner.py`/bridge Copilot; el comportamiento es idéntico en los 3 runtimes.
- [ ] **Sin trabajo nuevo del operador:** ningún paso manual nuevo salvo la renovación de credenciales (excepción dura (c) citada).
- [ ] KPI verificable: tras un ciclo con ADO/Jira caídos, el conteo de warnings `"sync ADO falló"`/`"sync Jira saltado"` con la flag ON es **≤ 1 por transición** (vs 941/448 del reporte), medido con el método del Anexo 8.1.

---

### Anti-alucinación — marcas de confianza de este plan
- **[V]** `ado_client.py:32` `_API_VERSION="7.1"`; connectionData en `:366`; `get_authenticated_user` `:354`; `AdoApiError` `:62` con `status_code`; `_request` `:264` (signin→401 `:272`, HTTPError→`e.code` `:299`).
- **[V]** `app.py:55` `_startup_sync`; Jira skip `:82`; ADO fail `:137`; `_startup_sync(logger)` invocado en `create_app` (`:354`); no hay daemon de sync ADO periódico (loops en `app.py` = digest/memory_review/local_insights_sweep/ado_edit_sweep).
- **[V]** `api/tickets.py:293` `_ado_sync_error_response` (ambos branches 502); `:5499` `get_ado_user` (502 en `:5543`; ya devuelve `linked:false` 200 en `:5548`); `sync` `:702`, `sync-v2` `:5661`.
- **[V]** `api/local_llm_analysis.py:616` `generate_insight_route` (502 en `:639`); `local_insights.py:225` `_local_llm_reachable`, `:286` `generate_insight_for_execution` (returns dict, nunca lanza).
- **[V]** `jira_client.py:103` `JiraConfigError("Credenciales Jira no encontradas...")`.
- **[V]** flags: `harness_flags.py` FlagSpec `:21`, `_CATEGORY_KEYS` `:114`, `fiabilidad_ciclo_vida` `:225`, FLAG_REGISTRY `:295`; `test_harness_flags.py` `_CURATED_DEFAULTS_ON` `:467`, `test_every_registry_flag_is_categorized` `:628`, `test_default_known_only_for_curated` `:700`; `config.py` patrón `:81`/`:91`.
- **[V]** venv `backend/.venv/Scripts/python.exe`; vitest `^4.1.9` en `frontend/package.json`.
- **[INF]** valor exacto `7.1-preview` aceptado por el tenant (F0 R3); write-site único del secreto para F6-b; punto de montaje del banner y consumidor de `ado-user` en frontend (confirmar por grep antes de editar).
