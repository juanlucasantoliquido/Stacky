# Plan 96 — Doctor de pipelines: el fallo explicado en llano (ADO + GitLab)

**Estado:** CRITICADO (juez adversarial, listo para implementar)
**Versión:** v2 (v1 → v2, crítica adversarial 2026-07-06)
**Fecha:** 2026-07-05 (crítica: 2026-07-06)
**Veredicto del juez:** APROBADO-CON-CAMBIOS (0 bloqueantes, 5 importantes, 1 menor).
**Serie DevOps E2E:** plan 4 de 4 (93 preflight / 94 variables / 95 producción / 96 doctor).

## Changelog v1 → v2

- **C1 (IMPORTANTE, resuelto en F0/F5):** F0 decía "5 casos patrón" pero la flag
  declara `requires=` ⇒ faltaba la **6ª pata**: arista
  `STACKY_DEVOPS_DOCTOR_ENABLED → STACKY_DEVOPS_PANEL_ENABLED` en
  `_REQUIRES_MAP_FROZEN` (`tests/test_harness_flags_requires.py`, junto a las de
  88-95). Sin ella el meta-test R4 queda ROJO en silencio — misma omisión que 93
  C1 / 94 C1 / 95 C1 ya corrigieron en sus propios v2. F0 ahora es de 6 patas y
  F5 corre ese test explícitamente.
- **C2 (IMPORTANTE, resuelto en F4):** F4 v1 monta `<PipelineDoctorPanel
  ctx={ctx} .../>` dentro de `TriggerPipelineSection.tsx`, pero ese componente
  NO recibe `ctx` como prop hoy (`TriggerPipelineSectionProps` solo tiene
  `project`/`lastBranch`, verificado en el archivo real) y se monta desde
  `PipelineBuilderSection.tsx:481` sin pasarlo — aunque `ctx` SÍ está disponible
  ahí (`PipelineBuilderSection.tsx:51`). Un modelo menor implementando F4 al pie
  de la letra rompería `tsc` o tendría que inferir el prop-threading. F4 ahora
  especifica literalmente el cambio de prop + el call site.
- **C3 (IMPORTANTE, resuelto en F2):** la instrucción de F2 para el trace de
  GitLab delegaba la decisión ("usar la variante raw... el adapter documenta
  cuál usa tras leer el helper real") a tiempo de implementación — ambigüedad
  para modelos menores. Verificado contra el código real
  (`services/gitlab_client.py:107-175`): `_request` YA sniffea `Content-Type` y
  devuelve `resp.text` cuando la respuesta no es JSON (líneas 164-175) — no
  existe ni hace falta ninguna "variante raw". F2 ahora da la llamada literal.
- **C4 (IMPORTANTE, resuelto en §3/F3):** contradicción entre el Principio §3.1
  ("ADO sin run que inspeccionar ⇒ 409 honesto con CTA") y F2/F3, que no
  implementaban ningún path que produjera ese 409 — cualquier error caía en el
  catch-all genérico (502 `logs_unavailable`) o en el status crudo de
  `TrackerApiError`. Prometer un 409 que el código nunca construye es el tipo de
  brecha que un supervisor detecta después como "plan no implementado según su
  propio texto". Se ajustó el principio para describir el comportamiento REAL
  (propagación honesta del status real, nunca 409 inventado) en vez de un 409
  especial no cableado.
- **C5 (IMPORTANTE, resuelto en F3/F4):** el KPI §1 promete "0 fallos
  silenciosos", pero el cap defensivo `failed[:10]` de F3 descartaba los jobs
  11+ sin ninguna señal en la respuesta ni en la UI — un fallo silencioso de
  cobertura que contradice el propio KPI. F3 ahora expone
  `failed_jobs_total` y F4 muestra el aviso de truncado cuando corresponde.
- **C6 (MENOR, documentado):** un par de citas de línea de la tabla de
  evidencia tenían desvíos menores (p. ej. `DevOpsAgentApi` real vive en
  `endpoints.ts:3126`, no `:3122`) — grep-ables por símbolo, no bloquean, se
  corrigen para no sembrar desconfianza en supervisiones futuras.
- **[ADICIÓN ARQUITECTO] (nueva §4.1, opcional/diferible a v1.1):** conectar la
  clasificación de capa 1 con el sistema de "memoria que empuja" YA EXISTENTE
  (planes 48-54, `services/memory_prefix.py:10` `build_memory_prefix`) — se
  registra SOLO el `id` de la clase de fallo (nunca el log ni el snippet) como
  una lección de proyecto, para que la PRÓXIMA vez que un agente edite el
  pipeline de ese proyecto reciba un prefijo informativo ("este proyecto falló
  antes por: comando inexistente en el runner"). Cero subsistema nuevo (reusa
  el canal existente), cero secretos (solo un id de clase, nunca texto de log),
  cero carga al operador (automático, bajo la misma flag), no toca HITL
  (informativo, no mutante).
**Requisito textual del operador (riel #1):** compatible con **Azure DevOps Y GitLab
desde el día 1**.
**Dependencias:** plan 87 IMPLEMENTADO (`84a9ecb5` — TriggerPipelineSection con
monitor). Plan 90 IMPLEMENTADO (`5859ceba` — agente DevOps conversacional): la
**capa 2** de este plan lo consume OPCIONALMENTE (gate por `agent_enabled` del
health; si está OFF, la capa 1 heurística alcanza sola). Plan 95: la pata ADO de
logs necesita que exista un run/build ADO — si el proyecto ADO aún no puede
disparar (95 sin implementar/activar), este plan degrada honesto (**[C4]** el
error real del tracker propaga tal cual — nunca un 409 inventado; en la
práctica la UI ni siquiera muestra el botón porque no hay `pipeline_id`).
Verificado en working tree 2026-07-05:

| Pieza existente reusada | Evidencia (archivo:línea) |
|---|---|
| Monitor del panel (entrada UI del doctor) | `frontend/src/components/devops/TriggerPipelineSection.tsx` (polling vía `CIPipeline.monitor`, `endpoints.ts:2943`) |
| Rutas CI HITL tracker-agnósticas | `backend/api/ci.py:26,76,139,174` |
| Cliente REST GitLab (delegate) | `backend/services/gitlab_provider.py` (`_request`; `poll_pipeline:545`) |
| Cliente REST ADO con PAT | `backend/services/ado_client.py:257` (`_request`) |
| Fábrica por tracker_type (patrón) | `backend/services/ci_provider.py:107`; `CI_PORT_METHODS:100` CONGELADO (⇒ sub-puerto nuevo, patrón ISP `repo_writer.py:13`) |
| Agente DevOps conversacional (capa 2) | `backend/api/devops_agent.py:28` (`POST /api/devops/agent/conversations`), `:102` (`.../message`); UI `frontend/src/components/devops/DevOpsAgentSection.tsx`; namespace `DevOpsAgentApi` (`endpoints.ts:3126`, corregido **[C6]**) |
| Salud del panel con booleans aditivos (`agent_enabled` ya existe) | `backend/api/devops.py:25-38` |
| `FlagGateBanner` + contrato §3.12 | `frontend/src/components/devops/FlagGateBanner.tsx`, `frontend/src/pages/DevOpsPage.tsx:44,68` |
| Matriz de runtimes del chat (copilot ⇒ 400 controlado) | plan 90 §3.6 (`devops_chat_requires_cli_runtime`, `api/devops_agent.py`) |
| Patrón flag 5 patas + ratchet | `backend/config.py:857-859`, `harness_flags.py:177-183`, `run_harness_tests.ps1:103-125` |

---

## 1. Objetivo + KPI

Cuando el monitor muestra un pipeline **failed**, un botón **"¿Qué pasó?"** que:

- **Capa 1 (SIEMPRE, determinista, sin LLM):** baja por API los jobs fallidos y
  sus logs (GitLab job trace / ADO build timeline+logs), los pasa por un
  **clasificador heurístico PURO** (catálogo de regex de fallos comunes) y muestra
  por job una tarjeta en llano: *qué pasó* ("El comando `robocopy` no existe en el
  runner"), *el fragmento relevante del log* (colapsable) y *un hint de arreglo*
  ("Instalá la herramienta en el runner o usá un tag/pool que la tenga").
- **Capa 2 (OPCIONAL, gated):** botón **"Explicar con el agente DevOps"** —
  visible SOLO si `ctx.health.agent_enabled === true` (plan 90) — que abre una
  conversación del agente con un prompt armado (diagnóstico capa 1 + snippet +
  spec) para explicar y proponer el fix; cualquier acción mutante del agente sigue
  exigiendo su `CONFIRMO` (regla R-HITL del 90).

**KPI (aspiracional; criterios binarios en F5):**
- Del "job rojo" al "qué pasó en llano" en 1 click, en ADO y en GitLab.
- ≥ 10 clases de fallo comunes clasificadas por el catálogo (criterio binario F1).
- 0 fallos silenciosos: si el log no matchea nada, la tarjeta muestra las últimas
  líneas del log igual ("no reconocí el patrón, mirá el final del log") — nunca
  finge diagnóstico.
- Capa 2 degrada explícita: sin plan 90 activo, la capa 1 funciona completa.

## 2. Por qué ahora / gap que cierra

El monitor (72/87) dice *que* falló; para saber *por qué*, el operador no-experto
tiene que ir a la web del tracker, encontrar el job, leer un log de miles de
líneas y entender jerga de CI. Justo el usuario objetivo del panel ("muy muy
simple para usuarios sin conocimiento") es el que no puede hacer eso. Los logs
están a una llamada de API en ambos trackers y el 80% de los fallos reales cae en
un puñado de clases reconocibles por regex. La capa 2 aprovecha el agente del 90
ya implementado, sin duplicar ningún mecanismo de chat.

## 3. Principios y guardarraíles (NO negociables)

1. **PARIDAD ADO + GITLAB:** sub-puerto `CILogsProvider` con DOS adapters y
   fábrica por tracker_type; tests de ambos con mocks HTTP. Donde ADO no tenga
   run que inspeccionar (plan 95 pendiente), el error del tracker propaga
   HONESTO con su status y mensaje reales (404/502 según corresponda) —
   **[C4] nunca se inventa un 409 especial no cableado**: si en la práctica
   nunca hay `pipeline_id` para ADO sin el 95 (el monitor no lo genera), la UI
   simplemente no muestra el botón; ver F3 para el único catch-all real.
2. **Solo-lectura absoluto (capa 1):** el doctor lee logs; no re-lanza, no
   cancela, no escribe. Test centinela de no-escritura.
3. **HITL (capa 2):** abrir la conversación del agente es un click explícito; el
   agente hereda TODOS los guardrails del 90 (R-HITL/CONFIRMO, cap de modelo sin
   Opus, runtimes CLI). Este plan NO añade caminos mutantes.
4. **Sin LLM en la capa 1:** el clasificador es regex determinista — mismo
   resultado siempre, testeable, gratis. El LLM es SOLO capa 2 opt-in.
5. **Flag propia** `STACKY_DEVOPS_DOCTOR_ENABLED`: categoría `devops`,
   `env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, SIN `default=`,
   CON `label`/`group`, `PlainHelp`, `harness_defaults.env` + test. Default OFF;
   byte-idéntico con OFF (endpoint 404, botón ausente).
6. **No degradar:** `CI_PORT_METHODS` intacto (sub-puerto nuevo); contratos de
   72/87/90 intactos; logs truncados server-side (nunca payloads de MB a la UI).
7. **Secretos:** los logs pueden contener valores; el doctor NUNCA los persiste
   (ni DB ni client_profile ni archivos) — viven solo en la respuesta HTTP. El
   snippet enviado al agente (capa 2) es el MISMO que el operador ya ve.
8. **3 runtimes:** capa 1 = UI + Flask, impacto NINGUNO. Capa 2 hereda la matriz
   del 90: claude_code_cli / codex_cli OK; github_copilot ⇒ el 90 responde 400
   `devops_chat_requires_cli_runtime` ⇒ el doctor lo muestra y la capa 1 sigue
   siendo el fallback completo (declarado por fase).
9. **Mono-operador sin auth; cero trabajo extra; ratchet** en ambos scripts.

## 4. Fases

> Comandos de test: backend `.venv/Scripts/python.exe -m pytest tests/<archivo> -q`
> desde `Stacky Agents/backend`; frontend `npx tsc --noEmit` + `npx vitest run
> <archivo>`.

### F0 — Flag `STACKY_DEVOPS_DOCTOR_ENABLED` (6 patas — C1)

Misma mecánica EXACTA que 93/95 F0 v2 (espejo `test_plan91_servers_flag.py`).
`label="Doctor de pipelines (Plan 96)"`, description en llano: "Cuando un
pipeline falla, el botón '¿Qué pasó?' baja el log del job y te lo explica en
lenguaje llano; opcionalmente se lo pasa al agente DevOps. Solo lee, nunca
ejecuta. Default OFF."

Las 6 patas: (1) `config.py`; (2) `harness_flags.py` FlagSpec (SIN `default=`,
`env_only=False`, `requires="STACKY_DEVOPS_PANEL_ENABLED"`, `group="global"`);
(3) `PlainHelp`; (4) `harness_defaults.env` línea
`STACKY_DEVOPS_DOCTOR_ENABLED=false` en orden alfabético — nota: hay drift
PREEXISTENTE de ese archivo en el working tree (centinelas 87-91): solo
AGREGAR la línea nueva, NUNCA revertir líneas ajenas ni regenerar el archivo;
(5) test patrón; (6) **[C1] arista en `_REQUIRES_MAP_FROZEN`**
(`tests/test_harness_flags_requires.py`, junto a las de 88-95):
```python
"STACKY_DEVOPS_DOCTOR_ENABLED": "STACKY_DEVOPS_PANEL_ENABLED",  # Plan 96
```

**Tests PRIMERO** — `tests/test_plan96_doctor_flag.py` (5 casos patrón +
no-regresión meta-tests; nota plan 85: F0+F3 juntos si el wiring acusa).
No-regresión: `tests/test_harness_flags.py` + `tests/test_flag_wiring.py` +
`tests/test_harness_flags_requires.py` ([C1] R4 exige la arista).
**Ratchet:** registrar. **Criterio binario:** 5+3 verdes; default OFF.
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F1 — Clasificador PURO (`services/failure_doctor.py`)

**Objetivo:** catálogo de clases de fallo + clasificación determinista de un log.

**Archivo NUEVO:** `Stacky Agents/backend/services/failure_doctor.py`
```python
"""failure_doctor.py — Plan 96. PURO: sin I/O, sin config, sin LLM.
Clasifica el texto de un log de CI en clases de fallo conocidas."""
import re

_MAX_LOG_CHARS = 200_000       # se analiza el TAIL (los fallos viven al final)
_SNIPPET_CONTEXT = 15          # líneas antes/después del primer match
_FALLBACK_TAIL_LINES = 40

# Catálogo v1 — 12 clases. Cada entrada: id, regex (compilada, IGNORECASE),
# title en llano, hint accionable. ORDEN = prioridad (gana el primero que matchea
# por línea; un log puede acumular varias clases distintas).
FAILURE_PATTERNS: list[dict] = [
    {"id": "cmd_not_found",
     "regex": re.compile(r"(command not found|no se reconoce como un comando|not recognized as an internal or external command|'[^']+' is not recognized)", re.I),
     "title": "Un comando del script no existe en el runner",
     "hint": "Instala la herramienta en el runner/agent o usa un tag/pool que la tenga; revisa el nombre del comando."},
    {"id": "file_not_found",
     "regex": re.compile(r"(No such file or directory|no se puede encontrar (el archivo|la ruta)|The system cannot find the (file|path)|FileNotFoundError|DirectoryNotFoundException)", re.I),
     "title": "El script busca un archivo o carpeta que no existe",
     "hint": "Verifica la ruta (¿corre en el working_directory correcto?) y que el paso anterior haya generado el archivo. Si es una carpeta de ambiente, inicializala (seccion Ambientes)."},
    {"id": "permission_denied",
     "regex": re.compile(r"(Permission denied|Acceso denegado|Access (is )?denied|EACCES)", re.I),
     "title": "Permisos insuficientes",
     "hint": "El usuario del runner no puede acceder a esa ruta/recurso; ajusta permisos o usa otro runner."},
    {"id": "var_undefined",
     "regex": re.compile(r"(unbound variable|variable .{1,60} (no esta definida|is not defined)|The term '\$\w+' is not recognized|##\[error\].{0,80}variable)", re.I),
     "title": "Una variable no esta definida",
     "hint": "Definila en el spec o como variable segura del proyecto (seccion Variables, plan 94)."},
    {"id": "auth_failed",
     "regex": re.compile(r"(authentication failed|401 Unauthorized|403 Forbidden|invalid credentials|TF401019|HTTP Basic: Access denied)", re.I),
     "title": "Fallo de autenticacion contra un servicio",
     "hint": "Revisa el token/credencial que usa el paso (¿expiro?, ¿scope?); guardalo como variable segura."},
    {"id": "network",
     "regex": re.compile(r"(Connection (refused|timed out)|Could not resolve host|getaddrinfo|Name or service not known|ETIMEDOUT|ECONNREFUSED)", re.I),
     "title": "Problema de red desde el runner",
     "hint": "El runner no llega al host destino: verifica DNS/firewall/VPN del runner."},
    {"id": "timeout",
     "regex": re.compile(r"(job exceeded (the )?timeout|timeout exceeded|ha superado el tiempo|##\[error\].{0,40}timed? ?out)", re.I),
     "title": "El job se quedo sin tiempo",
     "hint": "Sube el timeout del job o parti el trabajo en pasos mas chicos."},
    {"id": "disk_space",
     "regex": re.compile(r"(No space left on device|not enough space|disco lleno|ENOSPC)", re.I),
     "title": "Sin espacio en disco en el runner",
     "hint": "Limpia workspaces/caches del runner o usa otro con mas disco."},
    {"id": "yaml_config",
     "regex": re.compile(r"(yaml invalid|syntax error.{0,40}yaml|mapping values are not allowed|##\[error\].{0,60}template)", re.I),
     "title": "Error de configuracion del pipeline (YAML)",
     "hint": "Corre el preflight '¿Va a funcionar?' (plan 93) para ver el error de lint exacto."},
    {"id": "test_failures",
     "regex": re.compile(r"(\d+ (test(s)?|pruebas?) failed|FAILED \(|AssertionError|Tests? run: .* Failures: [1-9])", re.I),
     "title": "Tests del proyecto fallaron",
     "hint": "No es un problema del pipeline: abri el detalle de tests y arregla el codigo."},
    {"id": "package_manager",
     "regex": re.compile(r"(npm ERR!|pip(3)? .{0,30}error|ERROR: Could not find a version|Unable to resolve dependency|MSB\d{4})", re.I),
     "title": "Fallo instalando dependencias / build",
     "hint": "Revisa versiones/locks del gestor de paquetes; suele ser dependencia inexistente o registry inaccesible."},
    {"id": "exit_code",
     "regex": re.compile(r"(exited with( exit)? code [1-9]\d*|##\[error\]Process completed with exit code [1-9]|ERROR: Job failed: exit code [1-9]\d*)", re.I),
     "title": "Un paso termino con codigo de error",
     "hint": "Mira el fragmento del log: el error real esta unas lineas antes del exit code."},
]

def classify_failure(log_text: str) -> dict:
    """Retorna {'matches': [{'id','title','hint','line_no'}...]  (dedup por id,
    orden de aparicion), 'snippet': str}.
    - Analiza solo el TAIL de _MAX_LOG_CHARS.
    - snippet: ±_SNIPPET_CONTEXT lineas alrededor del PRIMER match; sin matches ⇒
      ultimas _FALLBACK_TAIL_LINES lineas y matches=[] (el caller muestra el
      fallback honesto).
    - PURA, nunca lanza (log vacio ⇒ {'matches': [], 'snippet': ''})."""
```

**Tests PRIMERO** — `tests/test_plan96_failure_doctor.py`:
- `test_f1_catalog_has_min_12_classes` (len(FAILURE_PATTERNS) >= 12, ids únicos,
  todos con title/hint no vacíos).
- Un test por clase con un fragmento de log REAL representativo (12 tests
  parametrizados: `test_f1_classifies[cmd_not_found]` …
  `[exit_code]`) — cada uno asserta el id en matches y que el snippet contiene
  la línea del match.
- `test_f1_no_match_fallback_tail` (log sin patrones ⇒ matches=[] y snippet =
  últimas líneas).
- `test_f1_dedup_and_order` (log con 2 veces cmd_not_found y 1 file_not_found ⇒
  2 matches en orden de aparición).
- `test_f1_huge_log_tail_only` (log de 1M chars: el head no se analiza — un
  patrón plantado solo al inicio NO matchea; uno al final SÍ).
- `test_f1_empty_log_safe` / `test_f1_pure_no_mutation`.

**Ratchet:** registrar. **Criterio binario:** 18 tests verdes.
**Flag:** ninguna (puro). **Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F2 — Sub-puerto `CILogsProvider` + adapters GitLab y ADO

**Objetivo:** jobs fallidos y su log con contrato único.

**Archivo NUEVO:** `Stacky Agents/backend/services/ci_logs_provider.py`
```python
"""ci_logs_provider.py — Plan 96. Sub-puerto ISP (patrón repo_writer.py:13).
NO amplia CIProvider (CI_PORT_METHODS congelado, ci_provider.py:100)."""
from typing import Optional, Protocol, runtime_checkable

@runtime_checkable
class CILogsProvider(Protocol):
    name: str
    def list_failed_jobs(self, pipeline_id: str) -> list[dict]:
        """[{'job_id': str, 'name': str, 'stage': str}] — solo fallidos.
        Lanza TrackerApiError si el pipeline no existe/PAT sin scope."""
        ...
    def get_job_log(self, job_id: str) -> str:
        """Texto del log (el caller trunca vía failure_doctor)."""
        ...

LOGS_PORT_METHODS = ("list_failed_jobs", "get_job_log")

def get_ci_logs_provider(project: Optional[str] = None) -> CILogsProvider:
    """Fábrica espejo de get_ci_provider (ci_provider.py:107) por tracker_type."""
```

**Archivo NUEVO:** `Stacky Agents/backend/services/gitlab_ci_logs.py`
- `class GitLabCILogsProvider` (`name="gitlab"`; delegate
  `GitLabTrackerProvider(project_name=project)` y su `_request`):
  - `list_failed_jobs`: `GET /projects/:id/pipelines/{pipeline_id}/jobs?scope[]=failed`
    → `[{job_id: str(j["id"]), name: j["name"], stage: j["stage"]}]`.
  - `get_job_log`: `GET /projects/:id/jobs/{job_id}/trace` (respuesta text/plain).
    **[C3] Literal, sin variante raw:** `body, _ = self._client._request("GET",
    f"/projects/{{proj_path}}/jobs/{{job_id}}/trace")` alcanza — verificado en
    `services/gitlab_client.py:107-175`: `_request` ya sniffea `Content-Type` y
    devuelve `resp.text` cuando la respuesta no es JSON (líneas 164-175); `body`
    llega como `str` directamente, sin helper adicional.
- **Archivo NUEVO:** `Stacky Agents/backend/services/ado_ci_logs.py`
  - `class AdoCILogsProvider` (`name="azure_devops"`; `AdoClient._request`):
  - `list_failed_jobs`: `GET {base_proj}/_apis/build/builds/{pipeline_id}/timeline?api-version=7.1`
    → records con `type=="Task"` y `result` ∈ ("failed","canceled") →
    `[{job_id: str(record["log"]["id"]), name: record["name"],
    stage: record.get("parentId") or ""}]` (records sin `log` se omiten —
    defensivo). Nota: `pipeline_id` acá es el BUILD id que devuelve el
    monitor/trigger del plan 95 (mismo id, verificado en 95 F1.c).
  - `get_job_log`: `GET {base_proj}/_apis/build/builds/{build_id}/logs/{logId}?api-version=7.1`
    — como logId no alcanza solo, el adapter guarda `build_id` en el constructor…
    **decisión fijada:** `job_id` del contrato se codifica como
    `f"{build_id}:{log_id}"` en `list_failed_jobs` y `get_job_log` lo parsea
    (split en ":", 2 partes, ValueError → TrackerApiError 400). Documentado en
    ambos adapters (GitLab usa el id nativo, sin ":").

**Tests PRIMERO** — `tests/test_plan96_logs_providers.py` (mocks `_request`):
- `test_f2_factory_and_structural_conformance`.
- `test_f2_gitlab_failed_jobs_mapped` / `test_f2_gitlab_trace_text`.
- `test_f2_ado_timeline_failed_tasks_mapped` (fixture con records mixtos:
  Task failed con log, Task succeeded, Phase, Task failed SIN log — solo 1 en el
  resultado con job_id `"{build}:{log}"`).
- `test_f2_ado_log_composite_id_parsed` / `test_f2_ado_bad_id_400`.
- `test_f2_tracker_error_propagates` (404 del pipeline ⇒ TrackerApiError).

**Ratchet:** registrar. **Criterio binario:** 7 tests verdes; grep: cero imports
de `flask` en los 3 módulos nuevos.
**Flag:** ninguna. **Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F3 — Endpoint `POST /api/devops/doctor/diagnose` (solo-lectura)

**Objetivo:** orquestar F1+F2; nunca 500; nunca persistir logs.

**Archivo a editar:** `Stacky Agents/backend/api/devops.py`:
```python
@bp.post("/doctor/diagnose")
def doctor_diagnose_route():
    """Jobs fallidos + clasificación en llano. SOLO-LECTURA; el log NO se persiste."""
    if not getattr(_config.config, "STACKY_DEVOPS_DOCTOR_ENABLED", False):
        abort(404)
    body = request.get_json(silent=True) or {}
    project, pipeline_id = body.get("project"), body.get("pipeline_id")
    if not project or not pipeline_id:
        return jsonify({"error": "project y pipeline_id son obligatorios"}), 400
    from services.ci_logs_provider import get_ci_logs_provider
    from services.failure_doctor import classify_failure
    try:
        provider = get_ci_logs_provider(project)
        failed = provider.list_failed_jobs(str(pipeline_id))
    except TrackerApiError as e:
        return jsonify({"error": str(e), "kind": getattr(e, "kind", "")}), e.status
    except Exception as e:
        return jsonify({"error": str(e), "kind": "logs_unavailable"}), 502
    jobs = []
    for j in failed[:10]:                      # cap defensivo de jobs por request
        try:
            log = provider.get_job_log(j["job_id"])
            diagnosis = classify_failure(log)
        except Exception as e:                 # log inaccesible ⇒ honesto, sigue
            diagnosis = {"matches": [], "snippet": f"(no pude bajar el log: {e})"}
        jobs.append({**j, "diagnosis": diagnosis})
    return jsonify({"provider": provider.name, "jobs": jobs,
                    "no_failures_found": len(failed) == 0,
                    "failed_jobs_total": len(failed)})   # [C5] honestidad del cap
```
(`TrackerApiError` importado arriba como en `api/pipeline_generator.py:21`.)
**[C5]** `failed_jobs_total` puede ser mayor que `len(jobs)` (cap de 10); F4 usa
esa diferencia para avisar "mostrando 10 de N" — nunca desaparecer jobs sin señal
(cumple el KPI "0 fallos silenciosos" de §1).
**[C4]** Caso ADO sin plan 95: `get_ci_logs_provider` funciona igual (los ids
vienen del monitor); si el proyecto ADO nunca disparó desde Stacky, la UI ni
muestra el botón (no hay `pipeline_id`) — no hace falta guard extra. Si el
`build_id`/`log_id` codificado deja de existir (build purgado, etc.), el error
cae en el catch-all de arriba (502 `logs_unavailable`) o en el
`TrackerApiError` real que lance `AdoClient._request` — **nunca** un 409
artificial: es el mismo criterio de honestidad que el resto del endpoint.
Health: `"doctor_enabled": bool(getattr(cfg, "STACKY_DEVOPS_DOCTOR_ENABLED", False)),`
en `devops_health_route` (`api/devops.py:29-38`).

**Tests PRIMERO** — `tests/test_plan96_doctor_endpoint.py` (fixtures flag on/off;
provider mockeado vía `unittest.mock.patch("api.devops.get_ci_logs_provider", ...)`):
- `test_f3_flag_off_404` / `test_f3_missing_params_400`.
- `test_f3_happy_two_failed_jobs_classified` (fixture de logs con cmd_not_found y
  file_not_found ⇒ cada job con su diagnosis.matches correcto).
- `test_f3_no_failures_flag_true` (0 fallidos ⇒ `no_failures_found: true`).
- `test_f3_one_log_unreachable_partial_result` (get_job_log lanza en 1 de 2 ⇒
  200 con el otro job diagnosticado y el snippet honesto).
- `test_f3_tracker_error_status_propagated` (404 ⇒ 404 con kind).
- `test_f3_readonly_no_writes` (saver de client_profile + commit_file mockeados
  ⇒ assert_not_called — centinela).
- `test_f3_health_has_doctor_enabled` / `test_f3_route_registered`.
- `test_f3_failed_jobs_total_exposed_when_capped` **[C5]** (fixture con 12
  fallidos ⇒ `len(jobs) == 10` y `failed_jobs_total == 12`).

**Ratchet:** registrar. **Criterio binario:** 10 tests verdes.
**Flag:** `STACKY_DEVOPS_DOCTOR_ENABLED` (guard per-request).
**Runtimes:** sin impacto. **Trabajo del operador:** ninguno.

### F4 — Frontend: "¿Qué pasó?" en el monitor + puente al agente (capa 2)

**Objetivo:** tarjetas en llano a 1 click del job rojo; agente opcional.

**Archivo NUEVO:** `Stacky Agents/frontend/src/devops/doctorModel.ts` (puro):
- Tipos espejo (`DoctorJob {job_id, name, stage, diagnosis: {matches, snippet}}`).
- `buildAgentPrompt(project: string, jobs: DoctorJob[]): string` — plantilla FIJA
  (determinista, testeable):
  ```
  Fallo el pipeline del proyecto <project>. Diagnostico automatico:
  - Job "<name>": <title de cada match o "sin patron reconocido">
  Fragmento del log:
  <snippet del primer job>
  Explicame en llano la causa mas probable y proponeme el fix concreto.
  Recorda: cualquier accion mutante requiere mi CONFIRMO.
  ```
- `summaryLine(jobs): string` ("2 jobs fallaron: comando inexistente, archivo no
  encontrado") — para el encabezado.

**Archivo NUEVO:** `Stacky Agents/frontend/src/components/devops/PipelineDoctorPanel.tsx`
- Props `{ ctx: DevOpsSectionContext; project: string; pipelineId: string }`.
- Si `ctx.health.doctor_enabled !== true` ⇒ `FlagGateBanner` inline
  (`flagKey="STACKY_DEVOPS_DOCTOR_ENABLED"`).
- Botón **"¿Qué pasó?"** ⇒ `DevOps.doctorDiagnose(project, pipelineId)` ⇒ por
  job: tarjeta con `name`, títulos de matches (o el fallback honesto "No reconocí
  un patrón conocido — mirá el final del log"), hints, y `<details>` con el
  snippet en `<pre>`.
- **[C5]** Si `failed_jobs_total > jobs.length`, encabezado adicional
  "Mostrando {jobs.length} de {failed_jobs_total} jobs fallidos" — nunca ocultar
  el faltante en silencio.
- **Capa 2:** si `ctx.health.agent_enabled === true` ⇒ botón "Explicar con el
  agente DevOps" ⇒ `DevOpsAgentApi` (endpoints.ts:3126 **[C6]**) `startConversation` con
  `message = buildAgentPrompt(...)` ⇒ al 202, hint "Conversación abierta — seguila
  en la sección Agente DevOps" (el montaje persistente del 87 C10 conserva el
  chat al navegar). Si el 90 responde 400 `devops_chat_requires_cli_runtime`
  (copilot), mostrar el detail literal — la capa 1 ya está en pantalla.
  Si `agent_enabled !== true`, el botón NO se renderiza (cero promesas rotas).
- Errores async siempre visibles (C16).

**Archivos a editar:**
- `frontend/src/api/endpoints.ts` — en el namespace `DevOps` (:3072):
  `doctorDiagnose: (project: string, pipelineId: string) => api.post<...>(
  "/api/devops/doctor/diagnose", { project, pipeline_id: pipelineId })`.
- **[C2] `frontend/src/components/devops/TriggerPipelineSection.tsx`** — HOY
  `TriggerPipelineSectionProps` solo tiene `project`/`lastBranch` (verificado en
  el archivo real: no recibe `ctx`). Agregar `ctx: DevOpsSectionContext` a la
  interface y a la firma del componente (el import de `DevOpsSectionContext` ya
  existe en el archivo, línea 8 — solo falta usarlo como prop). Luego, cuando
  `monitorStatus?.status === 'failed'`, montar `<PipelineDoctorPanel ctx={ctx}
  project={project} pipelineId={pipelineId} />` debajo del estado.
- **[C2] `frontend/src/components/devops/PipelineBuilderSection.tsx:481`** —
  el único call site de `<TriggerPipelineSection .../>` HOY pasa solo
  `project`/`lastBranch`; agregar `ctx={ctx}` (el componente contenedor ya tiene
  `ctx: DevOpsSectionContext` disponible como prop, línea 51).
- `frontend/src/pages/DevOpsPage.tsx` — SIN cambios (§3.12).

**Tests** — `frontend/src/devops/doctorModel.test.ts` (vitest TS puro):
- `prompt_contains_project_titles_and_confirmo` (la plantilla incluye "CONFIRMO"
  — anti-drift con la regla R-HITL del 90).
- `prompt_fallback_sin_patron`.
- `summary_line_joins_titles`.
Componentes: gate `tsc`.

**Criterio binario:** vitest verde (3 tests) + `tsc` 0 errores; grep:
`PipelineDoctorPanel` en `TriggerPipelineSection.tsx`; **[C2]** grep `ctx` en
`TriggerPipelineSectionProps` (`TriggerPipelineSection.tsx`) y en el call site
`<TriggerPipelineSection` de `PipelineBuilderSection.tsx`; el botón del agente
está dentro de `{ctx.health.agent_enabled === true && ...}` (grep del literal
`agent_enabled` en `PipelineDoctorPanel.tsx`); `DevOpsPage.tsx` sin diff.
**Flag:** `doctor_enabled` (gate inline) + `agent_enabled` (capa 2).
**Runtimes:** capa 1 sin impacto; capa 2 hereda matriz del 90 (copilot degrada
con el 400 controlado). **Trabajo del operador:** opt-in.

### F5 — Cierre: no-regresión + checklist binario

**Comandos:**
```
cd "Stacky Agents/backend"
.venv/Scripts/python.exe -m pytest tests/test_plan96_doctor_flag.py tests/test_plan96_failure_doctor.py tests/test_plan96_logs_providers.py tests/test_plan96_doctor_endpoint.py -q
.venv/Scripts/python.exe -m pytest tests/test_plan87_devops_endpoints.py tests/test_plan90_devops_agent_endpoints.py tests/test_harness_flags.py tests/test_flag_wiring.py tests/test_harness_flags_requires.py -q
cd "../frontend"
npx vitest run src/devops/doctorModel.test.ts
npx tsc --noEmit
```

**Checklist binario:**
- [ ] Flag OFF ⇒ endpoint 404, botón ausente, byte-idéntico.
- [ ] PARIDAD: pipeline GitLab fallido ⇒ jobs+trace clasificados; build ADO
      fallido ⇒ timeline+logs clasificados (ids compuestos `build:log`).
- [ ] Log con "command not found" ⇒ tarjeta "Un comando del script no existe en
      el runner" con hint y snippet.
- [ ] Log sin patrón ⇒ fallback honesto con el final del log (nunca diagnóstico
      inventado).
- [ ] El doctor NUNCA escribe (centinela F3 verde); logs no persistidos.
- [ ] Capa 2: con `agent_enabled` ON abre conversación del 90 con la plantilla
      (contiene "CONFIRMO"); con OFF el botón no existe; con copilot muestra el
      400 del 90 y la capa 1 queda completa.
- [ ] **[C1]** Arista `DOCTOR → PANEL` en `_REQUIRES_MAP_FROZEN` y
      `test_harness_flags_requires.py` verde.
- [ ] **[C2]** `ctx` llega a `PipelineDoctorPanel` vía `TriggerPipelineSection`
      (prop agregada + call site en `PipelineBuilderSection.tsx:481` actualizado);
      `tsc` 0 errores confirma el threading.
- [ ] **[C5]** Con >10 jobs fallidos, `failed_jobs_total` viaja en la respuesta y
      la UI avisa el truncado — nunca desaparecen jobs sin señal.
- [ ] Tests registrados en ambos scripts de ratchet.

### 4.1 [ADICIÓN ARQUITECTO] — Lección de proyecto (opcional, diferible a v1.1)

**NO es parte del DoD de v1** (no infla F0-F5 ni sus criterios binarios); se deja
especificada para no perder la idea y para que un futuro plan la levante sin
re-descubrirla.

**Objetivo:** que el diagnóstico de capa 1 deje de ser un callejón sin salida —
la MISMA clase de fallo (`id` del catálogo, NUNCA el log/snippet) se registra
como una lección de proyecto reusando el sistema de "memoria que empuja" YA
EXISTENTE (planes 48-54; wiring real en `services/memory_prefix.py:10`
`build_memory_prefix`, consumido por los 3 runtimes). Así, la próxima vez que un
agente edite el pipeline de ese proyecto, el prefijo de memoria incluye algo
como "este proyecto falló antes por: comando inexistente en el runner" —
convierte un diagnóstico puntual en aprendizaje compuesto del proyecto, que es
exactamente el diferencial ya construido de Stacky.

**Guardrails (heredados, sin excepción):**
- Cero subsistema nuevo: se reusa el canal existente de rejection_lessons/memoria
  colaborativa; NO se crea una tabla ni un store nuevo.
- Cero secretos: se persiste solo el `id` de la clase (p. ej. `"cmd_not_found"`),
  nunca el log, nunca el snippet.
- Cero carga al operador: automático, bajo la misma flag `STACKY_DEVOPS_DOCTOR_ENABLED`
  (o un sub-flag propio con default OFF si se prefiere aislar el rollout).
- HITL intacto: es informativo (un prefijo de contexto), no dispara ninguna
  acción; el agente sigue exigiendo `CONFIRMO` para todo lo mutante.
- Paridad 3 runtimes: hereda la paridad ya lograda por el plan 54 para
  `build_memory_prefix` (los 3 runtimes ya la consumen idéntico).

## 5. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Logs gigantes (MB) revientan memoria/UI | Tail de 200k chars server-side + snippet acotado + cap 10 jobs por request |
| Falsos diagnósticos del regex | Orden de prioridad + fallback honesto sin match + 12 tests con logs reales por clase |
| Secretos visibles en logs | El doctor no persiste nada; muestra lo que el tracker ya muestra; capa 2 manda el MISMO snippet visible (sin ampliación de superficie) |
| ADO: mapping timeline→log frágil | Records sin `log` omitidos + id compuesto validado + tests de fixture mixto |
| Trace GitLab no-JSON | Resuelto **[C3]**: `_request` (`gitlab_client.py:107-175`) ya sniffea `Content-Type` y devuelve `resp.text`; no hace falta variante raw ni verificación adicional al implementar |
| Capa 2 sin plan 90 activo | Botón no renderizado si `agent_enabled !== true`; capa 1 autosuficiente |
| Drift de la regla CONFIRMO | Test de la plantilla exige el literal "CONFIRMO" |

## 6. Fuera de scope (v1)

- Auto-fix (el agente propone; el operador confirma — jamás fix automático).
- Análisis de pipelines "pending/stuck" (eso lo cubre el preflight del 93 con
  runners; el doctor es post-fallo).
- Historial/persistencia de diagnósticos (solo-lectura efímero).
- Clasificador con LLM en capa 1 (determinismo primero; el LLM ya está en capa 2).
- Artefactos/screenshots de jobs (solo log de texto v1).

## 7. Glosario

- **Job trace (GitLab)**: log crudo de un job (`GET /jobs/:id/trace`).
- **Timeline (ADO)**: árbol de records de un build con result y logId por Task.
- **Clase de fallo**: entrada del catálogo `FAILURE_PATTERNS` (regex + título en
  llano + hint).
- **Capa 1 / Capa 2**: diagnóstico determinista por regex / explicación
  conversacional vía agente del plan 90 (opt-in, gated).
- **Id compuesto ADO**: `"{build_id}:{log_id}"` — el contrato del sub-puerto usa
  un solo string de job_id para ambos trackers.
- **CONFIRMO**: palabra literal que el agente del 90 exige antes de cualquier
  acción mutante (R-HITL).

## 8. Orden de implementación

1. F0 — flag (6 patas).
2. F1 — clasificador puro + catálogo (12 clases).
3. F2 — sub-puerto + adapters gitlab/ado.
4. F3 — endpoint diagnose + health key.
5. F4 — `doctorModel.ts` + `PipelineDoctorPanel` + integración monitor + capa 2.
6. F5 — cierre.

## 9. Definición de Hecho (DoD)

- 40 tests backend nombrados (F0:5, F1:18, F2:7, F3:10 **[C5]**) verdes por
  archivo con el venv; no-regresión 87/90 + meta-tests (`test_harness_flags.py`,
  `test_flag_wiring.py`, `test_harness_flags_requires.py` **[C1]**) verdes.
- Vitest F4 verde (3 tests); `tsc` 0 errores; **[C2]** `ctx` threading verificado
  (`TriggerPipelineSection.tsx` + `PipelineBuilderSection.tsx:481`).
- Paridad ADO+GitLab por tests de ambos adapters (mocks HTTP).
- Capa 1 100% funcional sin el plan 90; capa 2 gated por `agent_enabled` y con
  la matriz de runtimes del 90 declarada.
- Flag OFF ⇒ byte-idéntico; `DevOpsPage.tsx` sin cambios; checklist F5 completo.
