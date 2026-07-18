# Plan 188 — DevOps: del fallo a la incidencia — evidencia determinista y modal prellenado (HITL)

- **Versión:** v1 (PROPUESTO)
- **Fecha:** 2026-07-18
- **Autor:** StackyArchitectaUltraEficientCode (pipeline proponer-plan-stacky)
- **Serie:** DevOps (compone el Centro de Despliegues 120 con el ciclo de incidencias 131/166)

---

## 1. Título, objetivo y KPI

**Objetivo (1 párrafo).** Cuando un despliegue falla en el Centro de Despliegues (estado `failed` o
`failed_smoke`, plan 120), hoy el operador tiene que reconstruir a mano qué pasó: abrir el run, copiar
logs, mirar el smoke, recordar la última versión buena, y recién después redactar una incidencia desde
cero en el resolutor (131/166). Este plan agrega un **constructor determinista de evidencia de fallo**
(`services/devops_evidence.py`): con un click en el run fallido, Stacky arma un paquete de evidencia
local y reproducible (resumen de 1 línea + markdown legible + JSON estructurado con el paso fallido,
colas de stdout/stderr, resultado del smoke, última versión buena e historial reciente, SIN secretos), y
abre el **modal de incidencias EXISTENTE prellenado** (texto + `evidencia.md` + `evidencia.json`
adjuntos). El operador revisa y decide en el mismo flujo HITL de siempre — nada se crea ni publica solo.
Del fallo al ticket documentado: segundos en vez de minutos, con evidencia completa y uniforme.

**KPI / impacto esperado (binarios, verificados por tests):**

| KPI | Métrica | Criterio binario |
|-----|---------|------------------|
| KPI-1 | Determinismo + velocidad + pureza | La evidencia del run golden se construye < 100 ms, con `socket` bloqueado (cero red), y es byte-a-byte idéntica entre 2 corridas con `generated_at` fijo |
| KPI-2 | Cero secretos | Fixture con claves `DEPLOY_TOKEN`/`DB_PASSWORD` en la config del target → NO aparecen ni en el markdown ni en el JSON (test) |
| KPI-3 | Caps respetados | `summary` ≤ 120 chars; texto para el modal ≤ 18.000 chars (margen bajo `MAX_TEXT_LEN` 20.000 de `incident_store.py:26`); markdown adjunto ≤ 100.000 chars; JSON ≤ 1 MB — los 4 verificados con un run gigante sintético |
| KPI-4 | Retrocompatibilidad del modal | `IncidentResolverModal` sin las props nuevas se comporta EXACTAMENTE igual (props opcionales; `tsc --noEmit` verde y test puro del init) |

**Ganancia robusta:** toda falla de deploy queda documentada con la MISMA calidad de evidencia, sin
depender de la memoria del operador; el ciclo de incidencias 166 (resolutor + agente dev) recibe input
estructurado en vez de prosa suelta.

**Onboarding casi nulo:** un botón que aparece SOLO en runs fallidos, dentro de la sección que el
operador ya usa; el resto es el modal de incidencias que ya conoce.

---

## 2. Por qué ahora / gap que cierra

Evidencia del estado actual (verificada en el repo):

- `api/devops_deployments.py` (plan 120) — Centro de Despliegues completo: `/overview` (:68),
  `/execute` (:195), `/rollback` (:245), `/runs/<run_id>` (:274), `/history` (:284), `/drift` (:296),
  ledger en `services/deploy_store.py` (`read_ledger` :144, `get_app` :63, `last_success_version`
  :186). Los runs fallidos guardan `steps` (con stdout/stderr por paso) y `smoke` (kind/ok/detail,
  `deploy_executor.py:229`). **Nada convierte ese material en una incidencia.**
- `api/incidents.py` (planes 131/166) — `POST /api/incidents` (:31) recibe multipart `text` +
  `files` + `auto_publish`; extensiones permitidas incluyen `.md` y `.json`
  (`services/incident_store.py:28-31`), `MAX_TEXT_LEN = 20_000` (:26), `MAX_FILES = 10` (:23).
  El modal `frontend/src/components/IncidentResolverModal.tsx` (props hoy: solo `onClose`, :59-61)
  maneja intake → preview → confirm → publicación, con `auto_publish` (166 F3) como decisión previa
  del operador. **Hoy siempre arranca VACÍO.**
- `frontend/src/components/devops/DeploymentsSection.tsx` — ya renderiza los estados `failed` /
  `failed_smoke` (:28-33). **No ofrece ninguna acción de triage.**
- Los planes de la serie paralela 177 (auto-PR del resolutor), 178 (radar de ambientes), 180-185
  (DB Compare) y el 186 (lint de pipelines) NO tocan el puente deploy-fallido → incidencia.

**Gap:** el Centro de Despliegues sabe TODO sobre el fallo y el ciclo de incidencias sabe qué hacer con
un reporte — pero no están conectados. Cerrarlo es pura composición de piezas existentes (cero
infraestructura nueva), con el patrón "evidence bundle" reutilizable para futuras fuentes (fallos de
pipeline CI, doctor 96) en v2.

---

## 3. Principios y guardarraíles (no negociables)

1. **3 runtimes con paridad total por construcción:** el constructor de evidencia es Python
   determinista + UI React; NO usa ningún runtime LLM. El resolutor que el operador dispare DESPUÉS
   usa el runtime que ya tenga configurado (166) — este plan no toca esa capa. Paridad idéntica en
   Codex CLI / Claude Code CLI / GitHub Copilot Pro, incluso sin ninguno configurado.
2. **Cero trabajo extra para el operador:** flag default **ON** (ninguna de las 4 excepciones duras
   aplica: la construcción de evidencia es solo-lectura LOCAL — lee el ledger en disco, cero red,
   cero mutación; la creación de la incidencia sigue pasando por el modal HITL existente). Sin pasos
   manuales nuevos, sin config nueva, backward-compatible total.
3. **Human-in-the-loop:** el botón SOLO construye y prellena; crear/publicar la incidencia queda en el
   flujo 131/166 con su preview y confirm (y `auto_publish` sigue siendo la preferencia que el
   operador ya decidió en 166 — este plan NI la lee NI la cambia).
4. **Mono-operador sin auth:** nada de roles.
5. **No degradar:** `IncidentResolverModal` recibe props OPCIONALES (default = comportamiento actual
   exacto); `DeploymentsSection` solo agrega un botón condicional; ningún endpoint existente cambia.
6. **Reusar, no reinventar:** ledger 120 (`deploy_store`), incidencias 131/166 (`POST /api/incidents`,
   modal, `GET /api/incidents/status`), logger estructurado (`stacky_logger`, patrón
   `api/incidents.py:74`), guard-pattern de flags (`devops_deployments.py:37`).
7. **Gotcha config:** en `api/devops_deployments.py` la instancia de flags es `_config.config`
   (import `import config as _config`, :15) — usar `getattr(_config.config, "FLAG", False)` como en
   `_master_on()` (:25-26). NUNCA `getattr(config, ...)` sobre el módulo.

---

## 4. Fases

### F0 — Flag, esqueleto del servicio y endpoint con guard (vertical slice)

**Objetivo:** dejar cableado flag → servicio → endpoint 404/200 con shape estable, probado E2E.
**Valor:** las fases siguientes solo rellenan el builder; el wiring queda verificado desde el día 1.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/harness_flags.py`
- CREAR `Stacky Agents/backend/services/devops_evidence.py`
- EDITAR `Stacky Agents/backend/api/devops_deployments.py`
- EDITAR `Stacky Agents/backend/tests/test_harness_flags_requires.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh`
- CREAR `Stacky Agents/backend/tests/test_plan188_evidence_flag.py`

**Cambios exactos:**

1. `harness_flags.py` — FlagSpec nueva al final del bloque DEVOPS (después de
   `STACKY_DEVOPS_CONNECTION_DOCTOR_ENABLED`, ~línea 2743; misma convención R4 profundidad-1 que
   `STACKY_DEVOPS_SECTION_DOCTOR_ENABLED` :2650-2674, que apunta `requires` al master del panel):

```python
FlagSpec(
    key="STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED",
    type="bool",
    label="Evidencia de fallos de despliegue",
    description="En un run fallido del Centro de Despliegues, arma el paquete de "
                "evidencia (resumen + markdown + JSON, sin secretos) y abre el modal "
                "de incidencias prellenado. Solo-lectura; crear la incidencia sigue "
                "siendo decisión del operador.",
    group="global",
    default=True,
    requires="STACKY_DEVOPS_PANEL_ENABLED",  # R4 profundidad-1 (patrón :2674)
),
```

2. `harness_flags.py` — agregar `"STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED"` a `_CURATED_DEFAULTS_ON`
   (bloque DEVOPS ~:200-216, comentario `# Plan 188 — evidencia de fallos de despliegue`).
   **Gotcha:** bool default ON fuera de esa lista rompe `test_default_known_only_for_curated`.

3. CREAR `services/devops_evidence.py`:

```python
"""services/devops_evidence.py — Plan 188. Evidencia determinista de fallos de deploy.

PURO respecto de la red: lee SOLO el ledger local vía services.deploy_store.
NUNCA importa requests/remote_exec/ci_variables. Sin LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

SCHEMA_VERSION = "188.1"

MAX_SUMMARY_CHARS = 120
MAX_MODAL_TEXT_CHARS = 18_000      # margen bajo MAX_TEXT_LEN=20_000 (incident_store.py:26)
MAX_MARKDOWN_CHARS = 100_000
MAX_JSON_BYTES = 1_000_000
TAIL_LINES = 60                    # cola de stdout/stderr por paso

# claves de config/entorno que JAMÁS entran a la evidencia (case-insensitive, por sufijo)
SECRET_KEY_SUFFIXES = ("_token", "_pat", "_password", "_secret", "_key", "_apikey")


@dataclass(frozen=True)
class EvidenceBundle:
    summary: str        # 1 línea ≤120 chars — título sugerido de la incidencia
    modal_text: str     # texto prellenado del modal (≤18.000 chars)
    markdown: str       # evidencia.md completa (≤100.000 chars)
    json_payload: dict  # evidencia.json estructurada (≤1 MB serializada)

    def to_dict(self) -> dict:
        return asdict(self)


def build_deploy_failure_evidence(
    app_id: str,
    target: str,
    run_id: str,
    now: datetime | None = None,   # inyectable para tests deterministas (KPI-1)
) -> EvidenceBundle | None:
    """None si el run no existe. F0: devuelve bundle mínimo con summary; F1 lo completa."""
    ...
```

4. `api/devops_deployments.py` — endpoint nuevo DESPUÉS de `history_route` (:284-293):

```python
@bp.post("/evidence")
def evidence_route():
    """Run fallido → paquete de evidencia (solo-lectura local). Plan 188."""
    _guard_master()  # flag del Centro (patrón :37-39)
    if not bool(getattr(_config.config, "STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED", False)):
        abort(404)
    body = request.get_json(silent=True) or {}
    app_id, target, run_id = body.get("app_id"), body.get("target"), body.get("run_id")
    if not app_id or not target or not run_id:
        return jsonify({"error": "app_id, target y run_id son obligatorios"}), 400
    from services.devops_evidence import build_deploy_failure_evidence
    bundle = build_deploy_failure_evidence(app_id, target, run_id)
    if bundle is None:
        return jsonify({"error": "run_not_found"}), 404
    from services.stacky_logger import logger as stacky_logger
    stacky_logger.info("devops_evidence", "evidence_built",
                       app_id=app_id, target=target, run_id=run_id)
    return jsonify({"evidence": bundle.to_dict()})
```

5. Edge `STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` en
   `tests/test_harness_flags_requires.py` (misma estructura que las aristas DEVOPS existentes).

6. `test_plan188_evidence_flag.py` a `HARNESS_TEST_FILES` en `scripts/run_harness_tests.sh`
   (**gotcha:** si falta, `test_harness_ratchet_meta.py` rojo).

**Tests PRIMERO** — `tests/test_plan188_evidence_flag.py`:
- `test_flag_declarada_bool_default_on` — FlagSpec existe, `type=="bool"`, `default is True`,
  `requires=="STACKY_DEVOPS_PANEL_ENABLED"`.
- `test_flag_en_curated_defaults_on`.
- `test_endpoint_404_evidence_flag_off` — master deployments ON + evidence OFF → 404.
- `test_endpoint_404_master_off` — master deployments OFF → 404 (aunque evidence ON).
- `test_endpoint_400_payload_incompleto` — sin `run_id` → 400.
- `test_endpoint_404_run_inexistente` — ids válidos en forma pero run inexistente → 404
  `run_not_found` (con ledger vacío monkeypatcheado: `deploy_store.read_ledger` → `[]`).

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan188_evidence_flag.py -q`
(cwd = `Stacky Agents\backend`; SIEMPRE por archivo).

**Criterio binario:** los 6 tests pasan Y `test_harness_ratchet_meta.py` sigue verde.

**Flag:** `STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED`, default **ON** (ninguna excepción dura: lectura
local pura; la acción con efecto — crear incidencia — sigue en el modal HITL existente).

**Runtimes:** idéntico en los 3 (sin LLM). Fallback: flag OFF → 404 y la UI no muestra el botón.

**Trabajo del operador:** ninguno.

---

### F1 — Builder real de evidencia (markdown + JSON + caps + cero secretos)

**Objetivo:** convertir el ledger entry fallido en el paquete completo, determinista y sin secretos.
**Valor:** la calidad del ticket resultante — evidencia uniforme, legible y estructurada.

**Archivos:**
- EDITAR `Stacky Agents/backend/services/devops_evidence.py`
- CREAR `Stacky Agents/backend/tests/test_plan188_evidence_builder.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Diseño interno (exacto):**

```python
def _lookup_run(app_id: str, target: str, run_id: str) -> dict | None:
    """Busca el entry por run_id en deploy_store.read_ledger(app_id, target, limit=200).
    Mismo criterio de lookup que la ruta /runs/<run_id> (devops_deployments.py:274):
    leer esa ruta ANTES de implementar y espejar el acceso."""

def _strip_secrets(obj):
    """Copia profunda de dict/list/str; en dicts, TODA clave cuyo lower() termine en
    SECRET_KEY_SUFFIXES se reemplaza por "<omitido>". Recursivo; tipos no dict/list pasan igual."""

def _tail(text: str, n: int = TAIL_LINES) -> str:
    """Últimas n líneas de text ('' si vacío); prefija '… (truncado)' si se cortó."""
```

`build_deploy_failure_evidence` (completo):
1. `entry = _lookup_run(...)`; `None` → return `None`. `app = deploy_store.get_app(app_id)`
   (`deploy_store.py:63`); si `None`, usar `{"id": app_id, "name": app_id}` (evidencia igual sirve).
2. `now = now or datetime.now(timezone.utc)`; `generated_at = now.isoformat()`.
3. `failed_step` = primer item de `entry["steps"]` con `ok` falsy (los steps se loguean en
   `deploy_executor.py:235` vía `update_ledger_entry`); si ninguno y `entry["smoke"]` con
   `ok == False` → el "paso fallido" es el smoke.
4. `last_ok = deploy_store.last_success_version(app_id, target)` (`deploy_store.py:186`).
5. `previous = deploy_store.read_ledger(app_id, target, limit=6)` excluyendo el propio run → hasta 5
   filas `{run_id, status, version, started_at}`.
6. `summary` (≤120 chars, truncar con "…"):
   `f"Despliegue fallido: {app['name']} → {target} ({entry['status']}, v{entry.get('version','?')})"`.
7. `json_payload` = `{"schema_version": SCHEMA_VERSION, "kind": "deploy_failure",
   "generated_at": generated_at, "app": {"id","name"}, "target": target,
   "run": _strip_secrets(entry), "failed_step": _strip_secrets(failed_step),
   "smoke": entry.get("smoke"), "last_success_version": last_ok, "previous_runs": previous}`.
   Si `len(json.dumps(json_payload).encode()) > MAX_JSON_BYTES` → reemplazar en `run.steps` cada
   stdout/stderr por su `_tail(20)` y re-medir (2.º intento SIEMPRE alcanza: los caps de texto
   dominan el tamaño).
8. `markdown` (es-AR, secciones EXACTAS en este orden; truncado global a MAX_MARKDOWN_CHARS):
   `# Fallo de despliegue — {app} → {target}` / `## Resumen` (tabla: estado, versión, inicio,
   duración, última versión OK) / `## Paso fallido` (nombre + ```text con _tail(stdout) y
   _tail(stderr)```) / `## Smoke` (kind, ok, detail — o "no llegó al smoke") / `## Historial
   reciente` (tabla de `previous`) / `## Siguientes pasos sugeridos` (3 bullets fijos: revisar
   Doctor de la sección; comparar drift del target; rollback disponible a v{last_ok} si existe).
9. `modal_text` = `summary + "\n\n" + markdown` truncado a MAX_MODAL_TEXT_CHARS con sufijo
   `"\n\n[Evidencia completa en evidencia.md adjunta]"` si se cortó.
10. Return `EvidenceBundle(summary, modal_text, markdown, json_payload)`.

**Tests PRIMERO** — `tests/test_plan188_evidence_builder.py` (fixture: entry golden INLINE con 3
steps — el 2.º fallido con 200 líneas de stdout —, smoke `{"kind":"http","ok":False,...}`, y cfg del
target con `DEPLOY_TOKEN` y `DB_PASSWORD`; `deploy_store` monkeypatcheado en memoria):
- `test_none_si_run_inexistente`.
- `test_summary_formato_y_cap_120`.
- `test_kpi1_determinista_y_sin_red` — `socket.socket` monkeypatcheado a raise; 2 llamadas con
  `now=datetime(2026,7,18,tzinfo=timezone.utc)` → bundles idénticos (`==` sobre `to_dict()`);
  duración total < 0.1 s.
- `test_kpi2_cero_secretos` — ni "DEPLOY_TOKEN" ni el valor sembrado aparecen en
  `markdown`/`modal_text`/`json.dumps(json_payload)`; en el JSON la clave vale `"<omitido>"`.
- `test_tail_60_lineas` — el stdout de 200 líneas queda en 60 + marca "… (truncado)".
- `test_kpi3_caps_con_run_gigante` — steps sintéticos de 3 MB → los 4 caps se cumplen
  (summary ≤120, modal_text ≤18.000, markdown ≤100.000, JSON ≤1 MB tras el 2.º intento).
- `test_fallo_por_smoke_sin_step_fallido` — steps todos ok + smoke ok=False → `failed_step` es el
  smoke y el markdown lo dice ("Falló el smoke").
- `test_secciones_markdown_exactas` — las 5 secciones `##` aparecen en orden.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan188_evidence_builder.py -q`

**Criterio binario:** los 8 tests pasan (KPI-1, KPI-2, KPI-3 completos).

**Flag:** la de F0 (el servicio es puro y no conoce flags). **Runtimes:** idéntico.
**Trabajo del operador:** ninguno.

---

### F2 — Endpoint completo + contrato de respuesta congelado

**Objetivo:** exponer el bundle por HTTP con contrato estable para la UI.
**Valor:** una sola fuente para el modal prellenado (y para futuras fuentes de evidencia en v2).

**Archivos:**
- EDITAR `Stacky Agents/backend/api/devops_deployments.py` (la ruta de F0 ya llama al builder; en
  esta fase solo se congela el contrato con tests de integración)
- CREAR `Stacky Agents/backend/tests/test_plan188_evidence_endpoint.py`
- EDITAR `Stacky Agents/backend/scripts/run_harness_tests.sh` (registrar el test)

**Contrato de respuesta (EXACTO, congelado):**

```json
{
  "evidence": {
    "summary": "Despliegue fallido: MiApp → PF-TEST (failed_smoke, v1.4.2)",
    "modal_text": "…(≤18000 chars)…",
    "markdown": "…(≤100000 chars)…",
    "json_payload": { "schema_version": "188.1", "kind": "deploy_failure", "...": "..." }
  }
}
```

**Tests PRIMERO** — `tests/test_plan188_evidence_endpoint.py` (Flask test client, patrón
`tests/test_plan87_devops_endpoints.py`; `deploy_store` monkeypatcheado con el fixture golden de F1):
- `test_200_shape_completo` — keys exactas `{summary, modal_text, markdown, json_payload}` y
  `json_payload.schema_version == "188.1"`.
- `test_404_run_not_found_con_ledger_real_vacio`.
- `test_400_faltan_campos` — cada uno de los 3 campos ausente → 400.
- `test_logger_llamado` — monkeypatch de `stacky_logger.info` → llamado con evento
  `evidence_built` y `run_id` correcto.

**Comando:** `venv\Scripts\python.exe -m pytest tests\test_plan188_evidence_endpoint.py -q`

**Criterio binario:** los 4 tests pasan.

**Flag:** la de F0. **Runtimes:** idéntico. **Trabajo del operador:** ninguno.

---

### F3 — Props opcionales del modal de incidencias (prellenado retrocompatible)

**Objetivo:** que `IncidentResolverModal` pueda abrirse con texto y adjuntos iniciales SIN cambiar
nada para sus usos actuales.
**Valor:** habilita este plan y cualquier futuro "abrir incidencia desde X" (patrón reutilizable).

**Archivos:**
- EDITAR `Stacky Agents/frontend/src/components/IncidentResolverModal.tsx`
- CREAR `Stacky Agents/frontend/src/components/incidentModalInit.ts` (helper puro)
- CREAR `Stacky Agents/frontend/src/components/incidentModalInit.test.ts`

**Cambios exactos:**

1. `incidentModalInit.ts` (puro, sin DOM):

```typescript
export interface IncidentModalInit { text: string; files: File[] }
export function resolveModalInit(
  initialText?: string,
  initialFiles?: File[],
): IncidentModalInit {
  return { text: initialText ?? '', files: initialFiles ?? [] };
}
```

2. `IncidentResolverModal.tsx` — la interfaz (:59-61) pasa a:

```typescript
interface IncidentResolverModalProps {
  onClose: () => void;
  initialText?: string;   // Plan 188 — prellenado opcional (default: vacío, igual que hoy)
  initialFiles?: File[];  // Plan 188 — adjuntos opcionales
}
```

   y los estados (:71-72) se inicializan con el helper:
   `const init = resolveModalInit(initialText, initialFiles);`
   `const [text, setText] = useState(init.text);`
   `const [files, setFiles] = useState<File[]>(init.files);`
   NINGÚN otro cambio: validaciones, límites (`MAX_FILES`, extensiones), preview, confirm y
   `auto_publish` (166) quedan intactos porque el prellenado entra por el MISMO estado que el
   tipeo/paste manual.

**Tests PRIMERO** — `incidentModalInit.test.ts` (vitest, **sin @testing-library** — gap conocido;
espejar estilo `RemediationCard.test.tsx`):
- sin args → `{text: '', files: []}` (KPI-4: comportamiento actual intacto).
- con texto → lo devuelve tal cual; con files → misma referencia y largo.

**Comando:** `npx vitest run src/components/incidentModalInit.test.ts`
(cwd = `Stacky Agents\frontend`; por archivo).

**Criterio binario:** los 2 tests pasan Y `npx tsc --noEmit` sin errores nuevos (KPI-4).

**Flag:** no aplica flag nueva (props opcionales inertes si nadie las pasa). **Runtimes:** UI pura.
**Trabajo del operador:** ninguno.

---

### F4 — Botón "Armar incidencia" en runs fallidos + adjuntos generados client-side

**Objetivo:** cerrar el vertical: click en el run fallido → modal prellenado con evidencia.
**Valor:** el flujo completo del plan, visible y usable en segundos.

**Archivos:**
- CREAR `Stacky Agents/frontend/src/components/devops/deployEvidence.ts` (helpers puros)
- CREAR `Stacky Agents/frontend/src/components/devops/deployEvidence.test.ts`
- EDITAR `Stacky Agents/frontend/src/components/devops/DeploymentsSection.tsx`

**Comportamiento exacto:**

1. `deployEvidence.ts` exporta (puras):

```typescript
export const FAILED_STATUSES = ['failed', 'failed_smoke'] as const;
export function isFailedStatus(s: string | undefined): boolean {
  return s === 'failed' || s === 'failed_smoke';
}
export function evidenceFileName(runId: string, ext: 'md' | 'json'): string {
  return `evidencia-${runId}.${ext}`;   // coincide con ALLOWED_EXTENSIONS (.md/.json)
}
export function evidenceToFiles(runId: string, markdown: string, jsonPayload: unknown): File[] {
  return [
    new File([markdown], evidenceFileName(runId, 'md'), { type: 'text/markdown' }),
    new File([JSON.stringify(jsonPayload, null, 2)], evidenceFileName(runId, 'json'),
             { type: 'application/json' }),
  ];
}
```

2. `DeploymentsSection.tsx`:
   - Donde se renderiza cada entry con su `effective_status` (los labels failed/failed_smoke ya
     existen en :28-33), agregar — SOLO si `isFailedStatus(status)` — un botón
     `"Armar incidencia…"` (clase del CSS module existente; **gotcha ratchet:** cero `style={{}}`).
   - El botón se muestra ADEMÁS solo si el resolutor está disponible: al montar la sección, un
     `fetch('/api/incidents/status')` único; si `!res.ok || !body.enabled` → nunca mostrar el botón
     (patrón del board 166, `api/incidents.py:13-28`).
   - onClick: `POST /api/devops/deployments/evidence` con `{app_id, target, run_id}`;
     si `!res.ok` → toast/mensaje inline "No se pudo armar la evidencia" y NADA más (el flujo
     actual no se degrada). Si ok:
     `setIncidentInit({ text: evidence.modal_text, files: evidenceToFiles(run_id, evidence.markdown, evidence.json_payload) })`
     y render de `<IncidentResolverModal initialText={…} initialFiles={…} onClose={…}/>`
     (import del componente EXISTENTE `frontend/src/components/IncidentResolverModal.tsx`).
   - HITL: el modal se abre en su paso de intake normal; el operador revisa, edita si quiere y
     recién ahí crea (y publica solo si su preferencia 166 ya lo hacía).

**Tests PRIMERO** — `deployEvidence.test.ts` (vitest, funciones puras):
- `isFailedStatus` — true para los 2 estados, false para `ok`/`running`/`undefined`.
- `evidenceFileName` — `evidencia-r123.md` / `evidencia-r123.json`.
- `evidenceToFiles` — devuelve 2 Files con nombres correctos y contenido JSON parseable
  (leer con `await f.text()` en el test — vitest soporta File en jsdom-less vía undici/Node ≥20;
  si `File` no existe en el entorno de test, usar `new Blob` + assert de nombres vía la función
  `evidenceFileName` únicamente y saltar la lectura, dejando comentario del límite).

**Comando:** `npx vitest run src/components/devops/deployEvidence.test.ts`

**Criterio binario:** los 3 tests pasan Y `npx tsc --noEmit` sin errores nuevos.

**Smoke manual (1 paso, opcional para el operador):** forzar un deploy fallido en un target de
prueba → aparece el botón → modal prellenado con `evidencia.md` y `evidencia.json` adjuntas.

**Flag:** `STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED` (sin ella el endpoint da 404 y el botón no se
renderiza — la UI chequea el 404 del primer intento y lo oculta el resto de la sesión).
**Runtimes:** UI pura; idéntico. **Trabajo del operador:** ninguno.

---

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|------------|
| Evidencia filtra un secreto (peor caso) | `_strip_secrets` recursivo por sufijo + KPI-2 con fixture sembrado; los valores de steps son stdout de comandos PROPIOS del deploy (ya visibles en el ledger local); la evidencia NO agrega fuentes nuevas |
| `modal_text` supera el límite del intake | Cap 18.000 < `MAX_TEXT_LEN` 20.000 (`incident_store.py:26`) + test KPI-3 con run gigante |
| Modal se rompe para usos actuales | Props opcionales + helper puro + KPI-4 (`tsc` + test de init); cero cambios en validaciones/flujo |
| `File` no disponible en el entorno de test de vitest | Fallback documentado en F4 (assert de nombres; lectura solo si `typeof File !== 'undefined'`) |
| Sesión paralela toca `devops_deployments.py` (serie 177-185 activa) | Cambio ADITIVO (ruta nueva tras `/history`); tras merge `python -m compileall` + grep de duplicado silencioso (gotcha conocido) |
| Ledger enorme hace lento el lookup | `read_ledger(limit=200)` acotado + KPI-1 (<100 ms) |
| Resolutor de incidencias OFF | El botón no se muestra (`GET /api/incidents/status` → enabled=false); cero errores visibles |

## 6. Fuera de scope (explícito)

- Evidencia de fallos de pipelines CI (monitor 103 / doctor 96) — el `EvidenceBundle` y el patrón
  quedan listos para esa v2 (`kind` ya discrimina), pero NO se implementa ahora.
- Drift EN VIVO dentro de la evidencia (requiere ejecución remota `read_only` — otra clase de
  operación; el markdown solo SUGIERE correr el drift existente `/devops/deployments/drift`).
- Diagnóstico IA embebido en la evidencia (el operador ya tiene `/diagnose` 120 y doctores 96/104).
- Auto-crear la incidencia sin pasar por el modal (bypass de revisión humana — prohibido salvo la
  única excepción aceptada épica-desde-brief, que NO es este caso).
- Botón en otras superficies (historial global, notificaciones) — v2.

## 7. Glosario (para modelos menores)

- **Centro de Despliegues (120):** apps + targets (local/servidores del registro 91) + ledger de runs
  con steps y smoke; `api/devops_deployments.py` + `services/deploy_store.py`.
- **Ledger:** archivo JSONL local con un entry por run (`run_id`, `status`, `steps[]`, `smoke`).
- **Smoke:** chequeo post-activación del deploy (`deploy_executor.py:223-229`); si falla, el run
  queda `failed_smoke`.
- **Resolutor de incidencias (131/166):** `POST /api/incidents` multipart (`text`, `files`,
  `auto_publish`) + `IncidentResolverModal` con intake → preview → confirm.
- **`auto_publish` (166):** preferencia del operador para saltar preview al crear incidencias; este
  plan NO la modifica.
- **EvidenceBundle:** `{summary, modal_text, markdown, json_payload}` — contrato congelado en F2.
- **HITL:** human-in-the-loop; acá: construir evidencia es libre (lectura), crear la incidencia
  SIEMPRE pasa por el modal.
- **`_CURATED_DEFAULTS_ON` / HARNESS_TEST_FILES / ratchet UI:** ver planes previos — lista blanca de
  flags ON, registro de tests del arnés (`scripts/run_harness_tests.sh`), y prohibición de
  `style={{}}` inline en `.tsx` nuevos.

## 8. Orden de implementación

1. F0 — flag + esqueleto servicio + endpoint con guards + tests de wiring.
2. F1 — builder completo (lookup, strip secrets, tails, caps, markdown, modal_text) + 8 tests.
3. F2 — contrato congelado del endpoint + 4 tests de integración.
4. F3 — props opcionales del modal + helper `resolveModalInit` + tests + `tsc`.
5. F4 — botón en `DeploymentsSection` + `deployEvidence.ts` + tests + smoke manual opcional.

Cada fase se commitea sola con sus tests verdes ANTES de la siguiente (TDD estricto, cero falsos
verdes).

## 9. Definición de Hecho (DoD) global

- [ ] Los 5 archivos de test (`test_plan188_evidence_flag.py`, `test_plan188_evidence_builder.py`,
      `test_plan188_evidence_endpoint.py`, `incidentModalInit.test.ts`, `deployEvidence.test.ts`)
      pasan POR ARCHIVO con el intérprete correcto (`venv\Scripts\python.exe -m pytest …` /
      `npx vitest run …`).
- [ ] `test_harness_ratchet_meta.py`, `test_harness_flags_requires.py` y
      `test_default_known_only_for_curated` siguen verdes.
- [ ] KPI-1..KPI-4 verificados por los tests nombrados.
- [ ] `npx tsc --noEmit` sin errores nuevos; `python -m compileall backend` limpio.
- [ ] Flag `STACKY_DEVOPS_FAILURE_EVIDENCE_ENABLED` visible/toggleable en la UI de flags, default ON.
- [ ] Con la flag OFF (o resolutor 131 OFF): cero diferencias observables vs. hoy.
- [ ] Ningún contrato existente modificado (`POST /api/incidents`, modal para usos actuales,
      rutas 120 previas intactas).
- [ ] `services/devops_evidence.py` sin imports de red (`requests`, `remote_exec`) — verificado por
      el test KPI-1 (socket bloqueado) y por grep en el propio test.
