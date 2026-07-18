# Plan 193 — DevOps: triage de fallos CI — jobs fallidos y log inline enmascarado (read-only)

- **Versión:** v1 (PROPUESTO)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
- **Serie:** DevOps (expone el puerto de logs del plan 96; hermano de 191 bitácora CI)

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Cuando un pipeline CI falla, hoy el operador tiene dos caminos: pedirle el
diagnóstico IA al doctor (96) o irse a la web del tracker a bucear logs. No existe el camino del
medio — **ver el log crudo del job fallido, ya, sin salir de Stacky**. La infraestructura está: el
puerto `CILogsProvider` (`services/ci_logs_provider.py:7-22`, plan 96) ofrece
`list_failed_jobs(pipeline_id)` y `get_job_log(job_id)` con providers ADO y GitLab — pero SOLO lo
consume el doctor internamente; no tiene superficie API ni UI. Este plan la agrega, read-only y
determinista: dos endpoints (`failed-jobs` y `log` con **tail acotado a 200 KB** y **masking de
tokens**) y un panel colapsable en la sección de trigger/monitoreo existente: pipeline fallido →
"Ver fallos…" → lista de jobs fallidos (nombre, stage, link web) → click → log inline con descarga.
Triage en segundos, con el doctor IA como siguiente paso opcional — no como único camino.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Cap del log | Un log de 1.000.000 chars devuelve tail ≤ 200.000 chars, `truncated: true` y `chars_total: 1000000` |
| KPI-2 | Masking | Un token con prefijo conocido dentro del log (aún cerca del corte del tail) sale como `<posible-secreto-omitido>` — el masking corre ANTES del tail sobre el texto completo |
| KPI-3 | Puerto congelado intacto | `LOGS_PORT_METHODS == ("list_failed_jobs", "get_job_log")` (guardia anti-extensión; `ci_logs_provider.py:22`) y CERO ediciones a los providers |
| KPI-4 | Errores mapeados | `TrackerConfigError` → 400 con mensaje; `TrackerApiError` → su status; NUNCA un 500 crudo (test con providers que lanzan) |
| KPI-5 | UI pura verificada | Helpers de filename/nota-de-truncado/fila testeados en vitest y `npx tsc --noEmit` sin errores nuevos |

**Ganancia robusta:** el ciclo "falló → por qué" baja de minutos (web del tracker, login, click
maze) a segundos, con los secretos enmascarados por defecto.

**Onboarding casi nulo:** un botón que aparece SOLO cuando el pipeline monitoreado está fallido, en
la sección que el operador ya usa.

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `services/ci_logs_provider.py:7-22` — puerto `CILogsProvider` con EXACTAMENTE 2 métodos:
  `list_failed_jobs(pipeline_id) -> [{'job_id','name','stage','web_url'}]` (solo fallidos, lanza
  `TrackerApiError`) y `get_job_log(job_id) -> str`. `LOGS_PORT_METHODS` congelado (:22).
- `services/ci_logs_provider.py:25-49` — fábrica `get_ci_logs_provider(project)`: GitLab exige
  `STACKY_GITLAB_ENABLED` (si no, `TrackerConfigError`), ADO por default, otro → error.
- `services/gitlab_ci_logs.py` / `services/ado_ci_logs.py` — providers implementados (plan 96).
- `api/ci.py` — CERO rutas de logs (verificado por grep): el puerto solo alimenta al doctor.
- `frontend/src/components/devops/TriggerPipelineSection.tsx` — la sección de trigger/monitoreo
  donde se ve el estado del pipeline (72).
- Vecinos que NO se pisan: 96 (doctor = capa IA POSTERIOR; este plan es la capa determinista
  previa), 191 (bitácora de corridas — cuando se implemente, sus filas `failed` pueden linkear a
  este triage: sinergia, no dependencia), 192 (resiliencia de conexión, serie paralela).

**Gap:** la única lectura de fallos CI es vía IA o vía browser externo. La capa determinista
"mostrame el log" no existe pese a que el backend ya sabe obtenerlo.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** backend Python + UI React, cero LLM. El
   doctor 96 (IA) queda como capa opcional posterior. Paridad ADO/GitLab por el puerto existente;
   tracker sin provider → error mapeado 400 (mismo comportamiento que el doctor hoy).
2. **Cero trabajo extra para el operador:** flag default **ON** (ninguna excepción dura: lectura
   remota de logs con credenciales YA configuradas del tracker — misma clase de lectura que el
   monitor 72 y el doctor 96 que ya operan; sin acciones, sin mutaciones).
3. **Human-in-the-loop:** todo read-only; nada que confirmar porque nada se ejecuta.
4. **Mono-operador sin auth:** nada de roles.
5. **No degradar:** el puerto y sus providers NO se tocan (KPI-3); rutas nuevas aditivas en
   `api/ci.py`; la sección UI solo suma un botón condicional.
6. **Reusar, no reinventar:** puerto 96 tal cual; patrón de guard per-request de `api/ci.py:82`;
   mapeo de errores espejando el EXISTENTE en las rutas de `api/ci.py` (leerlo antes); lista de
   prefijos de token de la casa (planes 188/190/191).
7. **Gotcha config:** instancia = `_config.config` (`api/ci.py:18,82`). **Gotcha tests:** correr
   por archivo (reload de config contamina — gotcha registrado).

---

## 4. Fases

### F0 — Flag + servicio puro de tail/masking + 2 endpoints read-only

**Objetivo:** exponer el puerto 96 por HTTP con cap y masking, sin tocar el puerto.
**Valor:** todo el backend del triage, verificable con providers fake.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- CREAR `Stacky Agents/backend/services/ci_log_view.py`
- EDITAR `Stacky Agents/backend/api/ci.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan193_ci_triage.py`

**Cambios exactos:**

1. `harness_flags.py` — FlagSpec al final del bloque DEVOPS (~:2743):

```python
FlagSpec(
    key="STACKY_CI_FAILURE_TRIAGE_ENABLED",
    type="bool",
    label="Triage de fallos CI (logs inline)",
    description="En un pipeline fallido, lista los jobs fallidos y muestra el log de "
                "cada uno dentro de Stacky (recortado y con tokens enmascarados). "
                "Solo lectura; el Doctor IA sigue disponible como paso siguiente.",
    group="global",
    default=True,
    requires="STACKY_PIPELINE_TRIGGER_ENABLED",  # la superficie vive en la sección de trigger/monitor (informativo)
),
```

2. Key a `_CURATED_DEFAULTS_ON` (~:200-216, comentario `# Plan 193 — triage de fallos CI`).
   **Gotcha** curated. Edge `STACKY_CI_FAILURE_TRIAGE_ENABLED → STACKY_PIPELINE_TRIGGER_ENABLED`
   en `tests/test_harness_flags_requires.py`.

3. CREAR `services/ci_log_view.py` (PURO — sin provider, sin red; el endpoint compone):

```python
"""services/ci_log_view.py — Plan 193. Tail acotado + masking de logs CI. PURO."""
from __future__ import annotations

import re

MAX_LOG_CHARS = 200_000
# Misma lista de la casa (188/190/191). Consolidar en un módulo común queda para
# cuando 2+ de esos planes estén implementados (nota, no dependencia).
TOKEN_VALUE_PREFIXES = ("ghp_", "github_pat_", "glpat-", "xoxb-", "xoxp-", "AKIA", "eyJhbGciOi")
MASK_PLACEHOLDER = "<posible-secreto-omitido>"

_TOKEN_RE = re.compile(
    "(" + "|".join(re.escape(p) for p in TOKEN_VALUE_PREFIXES) + r")[A-Za-z0-9_./+-]{8,}"
)


def tail_and_mask(text: str, max_chars: int = MAX_LOG_CHARS) -> dict:
    """ORDEN OBLIGATORIO (KPI-2): (1) mask sobre el texto COMPLETO — así un token que quedaría
    partido justo en el borde del tail no escapa; (2) tail de los últimos max_chars.
    Devuelve {"log": str, "truncated": bool, "chars_total": int} donde chars_total es el
    largo del texto ORIGINAL (pre-mask, pre-tail)."""
    total = len(text)
    masked = _TOKEN_RE.sub(MASK_PLACEHOLDER, text)
    truncated = len(masked) > max_chars
    return {
        "log": masked[-max_chars:] if truncated else masked,
        "truncated": truncated,
        "chars_total": total,
    }
```

4. `api/ci.py` — 2 rutas nuevas DESPUÉS de la ruta `/runs` si el plan 191 ya se implementó, o al
   final del archivo si no (ambos órdenes válidos; son rutas independientes):

```python
@bp.get("/<project>/pipeline/<pipeline_id>/failed-jobs")
def ci_failed_jobs_route(project: str, pipeline_id: str):
    """Jobs fallidos del pipeline (puerto 96, read-only). Plan 193."""
    if not getattr(_config.config, "STACKY_CI_FAILURE_TRIAGE_ENABLED", False):
        abort(404)
    from services.ci_logs_provider import get_ci_logs_provider
    # MAPEO DE ERRORES: leer cómo trigger_pipeline_route maneja TrackerConfigError /
    # TrackerApiError en ESTE archivo y espejar EXACTAMENTE ese patrón (mismos status y shape).
    provider = get_ci_logs_provider(project)
    jobs = provider.list_failed_jobs(str(pipeline_id))
    return jsonify({"jobs": jobs, "provider": provider.name})


@bp.get("/<project>/job/<job_id>/log")
def ci_job_log_route(project: str, job_id: str):
    """Log de un job, con tail 200K y masking (KPI-1/KPI-2). Plan 193."""
    if not getattr(_config.config, "STACKY_CI_FAILURE_TRIAGE_ENABLED", False):
        abort(404)
    from services.ci_logs_provider import get_ci_logs_provider
    from services.ci_log_view import tail_and_mask
    provider = get_ci_logs_provider(project)   # mismo mapeo de errores que arriba
    text = provider.get_job_log(str(job_id))
    return jsonify(tail_and_mask(text))
```

   Regla dura del mapeo (KPI-4): envolver las llamadas al provider con el MISMO try/except que ya
   usa `api/ci.py` para `TrackerConfigError` (→ 400 `{"error": str(exc)}`) y `TrackerApiError`
   (→ `e.status` o 502) — localizarlo leyendo el cuerpo de `trigger_pipeline_route`; si ese
   archivo no captura esas excepciones, usar el patrón de `api/devops_variables.py:19-42`
   (`_call_provider`) replicado localmente. NUNCA dejar propagar a un 500 genérico.

5. `test_plan193_ci_triage.py` a `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh`
   (**gotcha** meta-test).

**Tests PRIMERO** — `tests/test_plan193_ci_triage.py` (provider FAKE monkeypatcheando
`services.ci_logs_provider.get_ci_logs_provider` a un objeto con los 2 métodos; Flask test client):
- `test_flag_declarada_bool_default_on` — type/default/requires exactos.
- `test_flag_en_curated_defaults_on`.
- `test_endpoints_404_flag_off` — ambas rutas → 404.
- `test_failed_jobs_shape` — fake devuelve 2 jobs → passthrough con `provider` incluido.
- `test_kpi1_tail_200k` — log de 1.000.000 chars → `len(log) <= 200_000`, `truncated is True`,
  `chars_total == 1_000_000`.
- `test_kpi2_masking_pre_tail` — log = relleno de 300.000 chars + token (`"ghp_" + "x"*20`,
  literal PARTIDO — gotcha push-protection) ubicado a caballo del corte → el response NO contiene
  el token y SÍ contiene `<posible-secreto-omitido>`.
- `test_log_corto_sin_truncar` — 100 chars → `truncated is False`, log completo.
- `test_kpi4_tracker_config_error_400` — fábrica lanza `TrackerConfigError` → 400 con mensaje.
- `test_kpi4_tracker_api_error_status` — provider lanza `TrackerApiError` con status 404 → 404.
- `test_kpi3_puerto_congelado` — `LOGS_PORT_METHODS == ("list_failed_jobs", "get_job_log")`.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan193_ci_triage.py -q`
(cwd = `Stacky Agents\backend`; SIEMPRE por archivo — gotcha reload de config).

**Criterio binario:** los 10 tests pasan Y `test_harness_ratchet_meta.py` verde.

**Flag:** `STACKY_CI_FAILURE_TRIAGE_ENABLED` default **ON** (ninguna excepción dura: lectura con
credenciales ya configuradas, misma clase que monitor 72/doctor 96; cero mutaciones).

**Runtimes:** idéntico en los 3 (sin LLM). Fallback: flag OFF → 404 y la UI no muestra el botón;
tracker sin provider de logs → 400 mapeado (igual que el doctor hoy).

**Trabajo del operador:** ninguno.

---

### F1 — UI: botón "Ver fallos…", lista de jobs y log colapsable con descarga

**Objetivo:** triage visible donde ya se monitorea, en 2 clicks.
**Valor:** cierre del ciclo; el operador ve el log sin abrir el tracker.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/devops/ciFailureTriage.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/devops/ciFailureTriage.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/devops/TriggerPipelineSection.tsx`

**Comportamiento exacto:**

1. `ciFailureTriage.ts` (puro):

```typescript
export interface FailedJob { job_id: string; name: string; stage: string; web_url: string | null }
export function logFileName(jobId: string): string {
  return `ci-log-${jobId}.txt`;
}
export function truncationNote(truncated: boolean, charsTotal: number): string | null {
  if (!truncated) return null;
  return `Mostrando el final del log (${charsTotal.toLocaleString('es-AR')} caracteres en total).`;
}
export function jobLabel(j: FailedJob): string {
  return `${j.stage} · ${j.name}`;
}
```

2. `TriggerPipelineSection.tsx`:
   - Localizar por LECTURA dónde renderiza el estado del pipeline monitoreado (grep interno del
     componente por el fetch a `/pipeline/`); cuando ese estado es fallido (`failed`), render de un
     botón `"Ver fallos…"`.
   - Click → `GET /api/ci/<project>/pipeline/<id>/failed-jobs`; 404 (flag OFF) → ocultar el botón
     el resto de la sesión; error → mensaje inline "no se pudieron listar los jobs" (sin romper la
     sección). Lista: `jobLabel(j)` + link "abrir en el tracker" si `web_url`.
   - Click en un job → `GET /api/ci/<project>/job/<job_id>/log` → `<details open>` con `<pre>` del
     `log` (clase CSS module, max-height con scroll; **gotcha ratchet:** cero `style={{}}`), la
     línea de `truncationNote(...)` si aplica, y botón "Descargar" →
     `new Blob([log], {type: 'text/plain'})` + anchor con `download = logFileName(job_id)`.
   - Cada log se fetchea SOLO al expandir (lazy; sin N+1).

**Tests PRIMERO** — `ciFailureTriage.test.ts` (vitest, sin @testing-library — gap conocido):
- `logFileName` — `ci-log-123.txt`.
- `truncationNote` — null sin truncar; texto con separador de miles es-AR al truncar.
- `jobLabel` — `stage · name` exacto.

**Comando:** `npx vitest run src/components/devops/ciFailureTriage.test.ts`
(cwd = `Stacky Agents\frontend`; por archivo).

**Criterio binario:** los 3 tests pasan Y `npx tsc --noEmit` sin errores nuevos (KPI-5).

**Smoke manual (1 paso, opcional):** monitorear un pipeline fallido real → "Ver fallos…" → log
inline con descarga.

**Flag:** la de F0 (404 → botón ausente; sección idéntica a hoy). **Runtimes:** UI pura.
**Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Un token escapa el masking por el corte del tail (peor caso) | ORDEN obligatorio mask-completo→tail (KPI-2 con token a caballo del corte) |
| Log gigante tumba memoria | `get_job_log` ya devuelve str (puerto 96, usado por el doctor hoy — misma clase de carga); el response se acota a 200 K chars |
| Extensión accidental del puerto congelado | KPI-3: test de `LOGS_PORT_METHODS` + cero ediciones a providers |
| Error del tracker → 500 crudo | KPI-4: mapeo espejado del patrón existente (o `_call_provider` replicado); tests con ambas excepciones |
| GitLab deshabilitado / tracker sin logs | La fábrica ya lanza `TrackerConfigError` → 400 con mensaje claro (comportamiento idéntico al doctor) |
| Sesión paralela toca `api/ci.py` (191 pendiente + serie activa) | Rutas ADITIVAS al final; tras merge `python -m compileall` + grep duplicado silencioso (gotcha) |
| Contaminación de tests por reload de config | Correr por archivo (gotcha registrado) |

## 6. Fuera de scope (explícito)

- Logs de jobs EXITOSOS o de todos los jobs (el puerto congelado solo lista fallidos; extenderlo
  es otra decisión — v2 si se pide).
- Streaming/tail en vivo del log (v1 es snapshot por click).
- Búsqueda/highlight dentro del log (el operador puede descargar y buscar localmente).
- Integración con la bitácora 191 (cuando 191 se implemente, sus filas `failed` pueden abrir este
  triage — 1 línea de UI futura, no acá).
- Consolidación de `TOKEN_VALUE_PREFIXES` en módulo común (nota en 188/190/191/193; se hace cuando
  2+ estén implementados).

## 7. Glosario (para modelos menores)

- **Puerto `CILogsProvider` (96):** interfaz congelada de 2 métodos (`ci_logs_provider.py:7-22`);
  providers reales en `ado_ci_logs.py`/`gitlab_ci_logs.py`; fábrica `get_ci_logs_provider`.
- **Doctor (96):** diagnóstico IA de fallos; consume este mismo puerto; queda como paso opcional.
- **Tail:** últimos N caracteres del log (los fallos casi siempre están al final).
- **Masking:** reemplazo determinista de valores con prefijo de token conocido.
- **`TrackerConfigError` / `TrackerApiError`:** errores tipados del tracker (config vs API).
- **`_CURATED_DEFAULTS_ON` / HARNESS_TEST_FILES / ratchet UI / reload de config:** convenciones y
  gotchas de la casa (ver planes 186-191).

## 8. Orden de implementación

1. F0 — flag + `ci_log_view.py` + 2 endpoints + 10 tests.
2. F1 — helpers + botón/lista/log colapsable + 3 tests + `tsc`.

Cada fase se commitea sola con sus tests verdes ANTES de la siguiente (TDD estricto, cero falsos
verdes).

## 9. Definición de Hecho (DoD) global

- [ ] Los 2 archivos de test (`test_plan193_ci_triage.py`, `ciFailureTriage.test.ts`) pasan POR
      ARCHIVO con el intérprete correcto.
- [ ] `test_harness_ratchet_meta.py`, `test_harness_flags_requires.py` y
      `test_default_known_only_for_curated` siguen verdes.
- [ ] KPI-1..KPI-5 verificados por los tests nombrados.
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio.
- [ ] Flag `STACKY_CI_FAILURE_TRIAGE_ENABLED` visible/toggleable en la UI de flags, default ON.
- [ ] Con la flag OFF: cero diferencias observables vs. hoy (404 + botón ausente).
- [ ] `ci_logs_provider.py` y ambos providers SIN ediciones (diff vacío en esos 3 archivos).
- [ ] `services/ci_log_view.py` puro (grep: cero `requests`, cero `ci_logs_provider`).
